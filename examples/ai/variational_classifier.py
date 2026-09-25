"""A variational quantum classifier on two moons, against classical baselines.

The script behind the variational classifier on
https://zksf.org/applications/ai-quantum-computing/quantum-classification/

Two qubits and four trainable angles. Each point's two features are written in
as RY rotations, then one trainable layer: RY on each qubit, a CNOT, RY on each
qubit again. The label is read from <Z> on qubit 0. Training is 20 steps of
plain gradient descent (learning rate 0.35) on mean squared error, with
central-difference gradients (step 0.2): every step evaluates each of the 22
training points at the current angles and at both shifts of all four, so 198
circuits a step and 4,000 for the whole run including the 40 test points.

Logistic regression, k-NN (k=5) and a one-hidden-layer MLP (8 tanh units) run
beside it on the identical split. They are written out in numpy rather than
imported, so their numbers do not depend on a library version.

    python variational_classifier.py 1               # seed 1: exact expectations on exact.cpu
    python variational_classifier.py 1 --shots 1024  # the published 1,024-shot configuration
    python variational_classifier.py 1 --local       # the exact run computed here, free

WHAT THE SEED FIXES, AND WHAT REPRODUCES

The seed fixes everything the script draws: the 22 training and 40 test points
(two_moons.py), then the four starting angles from the same generator, then the
baselines' initial weights from default_rng(seed) again.

Without --shots, each circuit is sent with the observable Z on qubit 0 and the
engine returns <Z> computed from the statevector, not sampled. Nothing random
is left, so every run of a seed returns the same accuracies to the last digit,
on the service or with --local, which does the same arithmetic here.

With --shots the service samples the measurements, and that sampling takes no
seed. A run lands within shot noise of the published 1,024-shot figures (one
standard deviation on each <Z> is 1/sqrt(1024) = 0.031), not on them.

Needs ZKSF_API_TOKEN unless --local. Priced before anything is submitted, and
the charge is read from the balance before and after.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import time

import numpy as np

from two_moons import N_TEST, N_TRAIN, split, to_angles

STEPS = 20
LR = 0.35
EPS = 0.20                    # central-difference step
ENGINE = "exact.cpu"
BATCH_MAX = 200               # the service's per-batch limit; the SDK does not chunk
Z0 = [[1.0, "IZ"]]            # Z on qubit 0: Qiskit labels qubit 0 rightmost


def circuit(x: np.ndarray, th: np.ndarray) -> str:
    """Angle-encode two features, then one variational layer. Angles are
    written to six decimals, which is part of what the published runs sent."""
    return (
        'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[2];\ncreg c[2];\n'
        f"ry({x[0]:.6f}) q[0];\nry({x[1]:.6f}) q[1];\n"
        f"ry({th[0]:.6f}) q[0];\nry({th[1]:.6f}) q[1];\n"
        "cx q[0],q[1];\n"
        f"ry({th[2]:.6f}) q[0];\nry({th[3]:.6f}) q[1];\n"
        "measure q -> c;\n"
    )


def z0_from_counts(counts: dict[str, int]) -> float:
    """<Z> on qubit 0 from sampled bitstrings. Qiskit writes qubit 0 last."""
    total = sum(counts.values())
    if not total:
        return 0.0
    plus = sum(v for k, v in counts.items() if k[-1] == "0")
    return (2 * plus - total) / total


class Evaluator:
    """<Z> on qubit 0 for a list of circuits, by one of three routes."""

    def __init__(self, shots: int | None, local: bool):
        self.shots, self.local, self.jobs = shots, local, 0
        if local:
            from qiskit import qasm2
            from qiskit.quantum_info import SparsePauliOp, Statevector
            self._loads, self._sv = qasm2.loads, Statevector
            self._op = SparsePauliOp.from_list([("IZ", 1.0)])
        else:
            import qsim_sdk
            token = os.environ.get("ZKSF_API_TOKEN")
            if not token:
                raise SystemExit("set ZKSF_API_TOKEN to an API key (console: Profile > Create API key), or pass --local")
            self.client = qsim_sdk.Client(token=token)

    def __call__(self, circuits: list[str]) -> list[float]:
        if self.local:
            # The engine's own arithmetic: the statevector of the circuit with
            # its measurements removed, <IZ> on it, rounded to 12 decimals.
            out = []
            for c in circuits:
                bare = self._loads(c).remove_final_measurements(inplace=False)
                out.append(round(float(self._sv(bare).expectation_value(self._op).real), 12))
            return out
        out = []
        for i in range(0, len(circuits), BATCH_MAX):
            part = circuits[i:i + BATCH_MAX]
            if self.shots:
                job = self.client.run_batch(part, shots=self.shots, engine=ENGINE, timeout=900.0)
            else:
                job = self.client.run_batch(part, engine=ENGINE, observable=Z0, timeout=900.0)
            self.jobs += 1
            for item in job.get("results") or []:
                res = item.get("result") or {}
                out.append(z0_from_counts(res.get("counts") or {}) if self.shots
                           else float(res["expectation"]))
        return out


# ------------------------------------------------------ classical baselines
def logistic(xtr, ytr, xte, yte, rng):
    """Linear. Included to show the task needs non-linearity."""
    w, b = rng.normal(0, 0.1, 2), 0.0
    for _ in range(2000):
        p = 1 / (1 + np.exp(-(xtr @ w + b)))
        g = p - ytr
        w -= 0.1 * (xtr.T @ g) / len(ytr)
        b -= 0.1 * g.mean()
    pred = (1 / (1 + np.exp(-(xte @ w + b))) > 0.5).astype(int)
    return float((pred == yte).mean()), 2


def knn(xtr, ytr, xte, yte, k=5):
    """Non-linear, no training at all."""
    d = ((xte[:, None, :] - xtr[None, :, :]) ** 2).sum(-1)
    nn = np.argsort(d, axis=1)[:, :k]
    pred = (ytr[nn].mean(1) > 0.5).astype(int)
    return float((pred == yte).mean()), 0


def mlp(xtr, ytr, xte, yte, rng, hidden=8, steps=3000):
    """One hidden layer of tanh units."""
    w1, b1 = rng.normal(0, 0.5, (2, hidden)), np.zeros(hidden)
    w2, b2 = rng.normal(0, 0.5, hidden), 0.0
    for _ in range(steps):
        h = np.tanh(xtr @ w1 + b1)
        p = 1 / (1 + np.exp(-(h @ w2 + b2)))
        d2 = p - ytr
        gw2, gb2 = h.T @ d2 / len(ytr), d2.mean()
        d1 = np.outer(d2, w2) * (1 - h ** 2)
        gw1, gb1 = xtr.T @ d1 / len(ytr), d1.mean(0)
        w1 -= 0.5 * gw1; b1 -= 0.5 * gb1; w2 -= 0.5 * gw2; b2 -= 0.5 * gb2
    h = np.tanh(xte @ w1 + b1)
    pred = (1 / (1 + np.exp(-(h @ w2 + b2))) > 0.5).astype(int)
    return float((pred == yte).mean()), 2 * hidden + hidden + 1


# ------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("seed", type=int, nargs="?", default=1)
    ap.add_argument("--shots", type=int, default=None,
                    help="sample this many shots per circuit instead of exact expectations")
    ap.add_argument("--local", action="store_true", help="compute the exact run here, no submission")
    args = ap.parse_args()
    if args.local and args.shots:
        raise SystemExit("--local computes exact expectations; it does not sample shots")

    seed = args.seed
    xtr, ytr, xte, yte, rng = split(seed)
    xtr_q, xte_q = to_angles(xtr, xte)
    theta = rng.normal(0, 0.5, 4)           # drawn after the data, from the same generator
    P = len(theta)
    route = "local, exact" if args.local else (f"{ENGINE}, {args.shots} shots" if args.shots
                                               else f"{ENGINE}, exact expectations")
    print(f"two moons, seed {seed}: {N_TRAIN} train, {N_TEST} test | {route}")

    ev = Evaluator(args.shots, args.local)
    n_circuits = STEPS * N_TRAIN * (1 + 2 * P) + N_TEST
    before = None
    if not args.local:
        probe = [circuit(xtr_q[0], theta)] * n_circuits
        est = ev.client.estimate_batch(probe, shots=args.shots or 1024, engine=ENGINE)
        print(f"  quoted ${est['total_usd']:.4f} for {n_circuits} circuits")
        before = ev.client.balance()

    history, t0 = [], time.time()
    for step in range(STEPS):
        circuits, plan = [], []
        for i, x in enumerate(xtr_q):
            circuits.append(circuit(x, theta)); plan.append(("f", i, -1))
            for p in range(P):
                for sgn in (+1, -1):
                    t = theta.copy(); t[p] += sgn * EPS
                    circuits.append(circuit(x, t)); plan.append(("g", i, p if sgn > 0 else ~p))
        vals = ev(circuits)
        if len(vals) != len(circuits):
            raise SystemExit(f"step {step}: got {len(vals)} of {len(circuits)} results")

        fwd = np.zeros(N_TRAIN)
        gplus, gminus = np.zeros((N_TRAIN, P)), np.zeros((N_TRAIN, P))
        for v, (kind, i, p) in zip(vals, plan):
            if kind == "f":
                fwd[i] = v
            elif p >= 0:
                gplus[i, p] = v
            else:
                gminus[i, ~p] = v

        pred = (fwd + 1) / 2                       # <Z> in [-1, 1] to a probability
        loss = float(((pred - ytr) ** 2).mean())
        dL = 2 * (pred - ytr) / N_TRAIN
        grad = np.array([(dL * (gplus[:, p] - gminus[:, p]) / (2 * EPS) / 2).sum() for p in range(P)])
        theta -= LR * grad
        acc = float(((fwd > 0).astype(int) == ytr).mean())
        history.append({"step": step, "loss": loss, "train_acc": acc})
        print(f"  step {step:2d}  loss {loss:.4f}  train accuracy {acc:.3f}")

    test = np.array(ev([circuit(x, theta) for x in xte_q]))
    q_acc = float(((test > 0).astype(int) == yte).mean())
    seconds = time.time() - t0

    rng2 = np.random.default_rng(seed)
    classical = {}
    for name, fn in (("logistic regression", lambda: logistic(xtr, ytr, xte, yte, rng2)),
                     ("k-NN (k=5)", lambda: knn(xtr, ytr, xte, yte)),
                     ("MLP (8 hidden)", lambda: mlp(xtr, ytr, xte, yte, rng2))):
        acc, nparam = fn()
        classical[name] = {"test_accuracy": acc, "params": nparam}

    out = {
        "seed": seed, "route": route, "n_train": N_TRAIN, "n_test": N_TEST,
        "circuits": n_circuits, "seconds": round(seconds, 1),
        "variational_classifier": {"test_accuracy": q_acc, "params": P,
                                   "final_angles": [round(float(t), 12) for t in theta]},
        "classical": classical, "history": history,
    }
    if before is not None:
        after = ev.client.balance()
        out["charged_usd"] = round(before - after, 6) if after is not None else None

    print(f"\n{'model':24} test accuracy")
    print(f"{'variational classifier':24} {q_acc:.3f}")
    for name, r in classical.items():
        print(f"{name:24} {r['test_accuracy']:.3f}")
    tag = "local" if args.local else (f"shots{args.shots}" if args.shots else "exact")
    path = pathlib.Path(__file__).with_name(f"classifier_seed_{seed}_{tag}.json")
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"written to {path.name}")


if __name__ == "__main__":
    main()
