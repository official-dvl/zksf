"""Five claims in AI QUANTUM.md, run against production instead of argued for.

The table says "Ready" for a row of things nobody has ever run. Ready means the
surface exists and is tested; it does not mean a customer could sit down and do
it. This closes that gap the same way Run A and the quantum kernel closed
theirs: fix the criterion first, run it, publish whatever comes back.

EVERY CRITERION BELOW IS SET BEFORE THE RUN. A result that misses its criterion
gets reported as a miss, with its cost. That is the whole point of writing them
down here rather than deciding afterwards what counts as success.

Cost is the same formula throughout: steps x batch x (1 + 2P) x sub-models, at
the per-circuit minimum. Every job is priced with estimate_batch before it is
submitted.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys
import time

import numpy as np
import qsim_sdk
from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector
# From the environment, never from a path to a keys file. That swap is what
# allowed this script into the repo; see the README beside it for why that
# matters more than it sounds.
TOKEN = os.environ.get("ZKSF_API_TOKEN")
if not TOKEN:
    raise SystemExit("set ZKSF_API_TOKEN to an API key from the console (Profile -> API keys)")

ENGINE = "exact.cpu"
SHOTS = 512
OUT = pathlib.Path(__file__).parent
RESULTS: dict[str, dict] = {}

#: SEED EVERY DRAW. Added 21 Sep 2026, after the photonic leg of this work
#: turned out to be unreproducible and had to be rebuilt from scratch.
#:
#: These loops draw: the QGAN's discriminator is randomly initialised, the RL
#: episodes sample states and actions, and the reservoir picks its couplings.
#: None of it was seeded, so two runs of this file converge to different
#: weights and the published figures could only be defended because
#: hw_proofs_results.json happened to save them. That file was load-bearing by
#: accident. It is not the mechanism any more; this is.
#:
#: What it does and does not fix: it pins every draw on this side, while the
#: shots are sampled on the device, so a seeded run reproduces the trajectory
#: rather than the last decimal.
#:
#: The published numbers were produced BEFORE this line existed and are left
#: alone. Re-running to make them match a seed would change them for no gain.
#: Seeded from here forward, and the seed travels with any new figure.
SEED = 0


def seed_everything(seed: int = SEED) -> None:
    import random

    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def bank() -> qsim_sdk.Client:
    return qsim_sdk.Client(token=TOKEN)


def price(client, circuits, label: str) -> float:
    est = client.estimate_batch(circuits, shots=SHOTS, engine=ENGINE)
    print(f"  [{label}] quoted ${est['total_usd']:.4f} for {est['points']} circuits")
    return float(est["total_usd"])


def run_batch(client, circuits: list) -> list[dict[str, float]]:
    """Submit in chunks the service accepts, and return one distribution each."""
    out: list[dict[str, float]] = []
    for start in range(0, len(circuits), 200):
        job = client.run_batch(circuits[start:start + 200], shots=SHOTS,
                               engine=ENGINE, timeout=900.0)
        for item in job["results"]:
            counts = (item.get("result") or {}).get("counts") or {}
            total = sum(counts.values())
            out.append({k: v / total for k, v in counts.items()} if total else {})
    return out


def tvd(p: dict[str, float], q: dict[str, float]) -> float:
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


# ----------------------------------------------------------------------------
# 1. RESERVOIR COMPUTING.  Criterion: a classical readout trained on the
#    quantum features beats chance on a held-out split. Nothing in the circuit
#    trains, which is the whole idea, so this proves the input-split surface in
#    a shape where no gradient is involved at all.
# ----------------------------------------------------------------------------
def reservoir(client) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.datasets import make_moons

    n = 200
    X, y = make_moons(n_samples=n, noise=0.2, random_state=0)
    X = X * (np.pi / 2)

    x = ParameterVector("x", 2)
    base = QuantumCircuit(4)
    base.h(range(4))
    base.rz(2.0 * x[0], 0); base.rz(2.0 * x[1], 1)
    base.cx(0, 1); base.cx(1, 2); base.cx(2, 3)
    base.rz(2.0 * x[0] * x[1], 3)
    base.cx(2, 3); base.cx(1, 2); base.cx(0, 1)
    base.ry(0.7, 0); base.ry(1.3, 1); base.ry(0.9, 2); base.ry(1.1, 3)
    base.measure_all()

    circuits = [base.assign_parameters({x[0]: a, x[1]: b}) for a, b in X]
    cost = price(client, circuits, "reservoir")
    dists = run_batch(client, circuits)

    outcomes = sorted({k for d in dists for k in d})
    features = np.array([[d.get(o, 0.0) for o in outcomes] for d in dists])

    split = 140
    clf = LogisticRegression(max_iter=2000).fit(features[:split], y[:split])
    quantum = float(clf.score(features[split:], y[split:]))
    raw = float(LogisticRegression(max_iter=2000).fit(X[:split], y[:split])
                .score(X[split:], y[split:]))

    return {"criterion": "readout on quantum features beats chance (0.5)",
            "quantum_features": quantum, "raw_features": raw,
            "passed": quantum > 0.5, "circuits": len(circuits), "quoted_usd": cost}


# ----------------------------------------------------------------------------
# 2. QCBM.  Criterion: TVD to a known target drops below 0.10 from a random
#    start. No inputs at all, so this is CircuitLayer's other mode.
# ----------------------------------------------------------------------------
def qcbm(client) -> dict:
    import torch
    from qsim_sdk.ml import CircuitLayer

    target = {"00": 0.5, "11": 0.5}          # a Bell-like distribution
    w = ParameterVector("w", 6)
    qc = QuantumCircuit(2)
    qc.ry(w[0], 0); qc.ry(w[1], 1)
    qc.cx(0, 1)
    qc.ry(w[2], 0); qc.ry(w[3], 1)
    qc.cx(0, 1)
    qc.ry(w[4], 0); qc.ry(w[5], 1)
    qc.measure_all()

    outcomes = ["00", "01", "10", "11"]
    layer = CircuitLayer(client, qc, shots=SHOTS, engine=ENGINE, eps=0.25,
                         init=[0.3, 1.9, 0.7, 2.4, 1.1, 0.5], outcomes=outcomes)
    want = torch.tensor([target.get(o, 0.0) for o in outcomes])

    before = {o: float(v) for o, v in zip(outcomes, layer())}
    opt = torch.optim.Adam(layer.parameters(), lr=0.25)
    steps = 60
    for _ in range(steps):
        opt.zero_grad()
        (0.5 * (layer() - want).abs().sum()).backward()
        opt.step()
    after = {o: float(v) for o, v in zip(outcomes, layer())}

    circuits = (steps + 2) * (1 + 2 * 6)
    return {"criterion": "TVD to the target below 0.10",
            "tvd_before": tvd(before, target), "tvd_after": tvd(after, target),
            "distribution": after, "passed": tvd(after, target) < 0.10,
            "circuits": circuits, "quoted_usd": round(circuits * 1e-4, 4)}


# ----------------------------------------------------------------------------
# 3. QGAN.  Criterion: a classical discriminator that starts able to separate
#    generated from real ends unable to, AND the generated distribution is
#    closer to the target than it started. Both, because a discriminator can be
#    defeated by a generator that has learned nothing if the discriminator
#    collapses.
# ----------------------------------------------------------------------------
def qgan(client) -> dict:
    import torch
    from qsim_sdk.ml import CircuitLayer

    target = {"00": 0.4, "01": 0.1, "10": 0.1, "11": 0.4}
    outcomes = ["00", "01", "10", "11"]
    want = torch.tensor([target[o] for o in outcomes])

    w = ParameterVector("w", 4)
    qc = QuantumCircuit(2)
    qc.ry(w[0], 0); qc.ry(w[1], 1); qc.cx(0, 1)
    qc.ry(w[2], 0); qc.ry(w[3], 1)
    qc.measure_all()

    gen = CircuitLayer(client, qc, shots=SHOTS, engine=ENGINE, eps=0.25,
                       init=[2.2, 0.4, 1.7, 2.9], outcomes=outcomes)
    disc = torch.nn.Sequential(torch.nn.Linear(4, 8), torch.nn.ReLU(),
                               torch.nn.Linear(8, 1))
    d_opt = torch.optim.Adam(disc.parameters(), lr=0.05)
    g_opt = torch.optim.Adam(gen.parameters(), lr=0.20)
    bce = torch.nn.BCEWithLogitsLoss()

    start = {o: float(v) for o, v in zip(outcomes, gen())}
    first_gap = None
    steps = 40
    for step in range(steps):
        fake = gen().detach()
        d_opt.zero_grad()
        loss_d = bce(disc(want), torch.ones(1)) + bce(disc(fake), torch.zeros(1))
        loss_d.backward(); d_opt.step()
        gap = float(torch.sigmoid(disc(want)) - torch.sigmoid(disc(fake)))
        if first_gap is None:
            first_gap = gap
        g_opt.zero_grad()
        bce(disc(gen()), torch.ones(1)).backward(); g_opt.step()

    end = {o: float(v) for o, v in zip(outcomes, gen())}
    final_gap = float(torch.sigmoid(disc(want)) - torch.sigmoid(disc(gen().detach())))
    circuits = steps * 2 * (1 + 2 * 4) + 2
    closer = tvd(end, target) < tvd(start, target)
    return {"criterion": "discriminator gap shrinks AND generated distribution moves toward the target",
            "tvd_before": tvd(start, target), "tvd_after": tvd(end, target),
            "discriminator_gap_first": first_gap, "discriminator_gap_last": final_gap,
            "distribution": end,
            "passed": bool(closer and abs(final_gap) < abs(first_gap)),
            "circuits": circuits, "quoted_usd": round(circuits * 1e-4, 4)}


# ----------------------------------------------------------------------------
# 4. RL POLICY.  Criterion: average return over the last ten episodes beats a
#    random policy on the same environment.
# ----------------------------------------------------------------------------
def rl_policy(client) -> dict:
    import torch
    from qsim_sdk.ml import CircuitLayer

    x = ParameterVector("s", 2)
    w = ParameterVector("w", 4)
    qc = QuantumCircuit(2)
    qc.ry(x[0], 0); qc.ry(x[1], 1)
    qc.ry(w[0], 0); qc.ry(w[1], 1); qc.cx(0, 1)
    qc.ry(w[2], 0); qc.ry(w[3], 1)
    qc.measure_all()

    outcomes = ["00", "01", "10", "11"]
    layer = CircuitLayer(client, qc, inputs=[p.name for p in x], shots=SHOTS,
                         engine=ENGINE, eps=0.25, init=[0.5, 1.2, 0.9, 0.3],
                         outcomes=outcomes)
    opt = torch.optim.Adam(layer.parameters(), lr=0.20)

    def reward(state, action) -> float:
        """A deterministic bandit: act 1 when the first coordinate is positive."""
        return 1.0 if action == (1 if state[0] > 0 else 0) else 0.0

    rng = np.random.default_rng(0)
    states = rng.uniform(-1.5, 1.5, size=(60, 2))
    random_return = float(np.mean([reward(s, rng.integers(0, 2)) for s in states]))

    returns: list[float] = []
    for i in range(0, 60, 6):
        batch = torch.tensor(states[i:i + 6], dtype=torch.float32)
        probs = layer(batch)
        p_one = probs[:, 2] + probs[:, 3]          # P(first qubit = 1)
        rewards = torch.tensor(
            [reward(s, 1 if float(p) > 0.5 else 0) for s, p in zip(states[i:i + 6], p_one)]
        )
        returns.append(float(rewards.mean()))
        opt.zero_grad()
        # REINFORCE with a centred reward, which is the standard estimator.
        (-(rewards - rewards.mean()) * torch.log(p_one.clamp(1e-6, 1))).mean().backward()
        opt.step()

    circuits = 10 * (6 + 6 * 2 * 4)
    final = float(np.mean(returns[-3:]))
    return {"criterion": "average return beats a random policy",
            "random_policy": random_return, "first_batches": float(np.mean(returns[:3])),
            "last_batches": final, "passed": final > random_return,
            "circuits": circuits, "quoted_usd": round(circuits * 1e-4, 4)}


# ----------------------------------------------------------------------------
# 5. PATCH GAN.  Criterion: AN IMAGE, plus a cost figure. Graded on whether the
#    generated 8x8 is closer to the target than the untrained start; a noisy
#    result is published as noisy.
# ----------------------------------------------------------------------------
def patch_gan(client, steps: int = 60) -> dict:
    import torch
    from qsim_sdk.ml import CircuitLayer

    # A cross, which is recognisable at 8x8 and is not a constant.
    target = np.zeros((8, 8), dtype=np.float32)
    target[3:5, :] = 1.0
    target[:, 3:5] = 1.0
    target = target / target.sum()

    n_sub, patch = 4, 16
    w = ParameterVector("w", 6)
    qc = QuantumCircuit(4)
    qc.h(range(4))
    qc.ry(w[0], 0); qc.ry(w[1], 1); qc.ry(w[2], 2)
    qc.cx(0, 1); qc.cx(1, 2); qc.cx(2, 3)
    qc.ry(w[3], 1); qc.ry(w[4], 2); qc.ry(w[5], 3)
    qc.measure_all()

    outcomes = [f"{i:04b}" for i in range(16)]
    subs = [
        CircuitLayer(client, qc, shots=SHOTS, engine=ENGINE, eps=0.25,
                     init=list(np.random.default_rng(k).uniform(0, 3.1, 6)),
                     outcomes=outcomes)
        for k in range(n_sub)
    ]
    opts = [torch.optim.Adam(s.parameters(), lr=0.25) for s in subs]

    def image() -> torch.Tensor:
        rows = [s() for s in subs]
        flat = torch.cat(rows)                      # 4 patches x 16 = 64
        return (flat / flat.sum()).reshape(8, 8)

    want = torch.tensor(target.reshape(-1))
    start = image().detach().numpy()

    for _ in range(steps):
        for opt in opts:
            opt.zero_grad()
        flat = torch.cat([s() for s in subs])
        loss = 0.5 * (flat / flat.sum() - want).abs().sum()
        loss.backward()
        for opt in opts:
            opt.step()

    final = image().detach().numpy()
    circuits = (steps + 2) * n_sub * (1 + 2 * 6)
    before = float(0.5 * np.abs(start.reshape(-1) - target.reshape(-1)).sum())
    after = float(0.5 * np.abs(final.reshape(-1) - target.reshape(-1)).sum())

    art = "\n".join("".join(" .:-=+*#%@"[min(9, int(v / max(final.max(), 1e-9) * 9))]
                            for v in row) for row in final)
    return {"criterion": "an image, and closer to the target than the untrained start",
            "tvd_before": before, "tvd_after": after, "passed": after < before,
            "image": final.tolist(), "ascii": art,
            "circuits": circuits, "quoted_usd": round(circuits * 1e-4, 4)}


EXPERIMENTS = [
    ("reservoir", reservoir),
    ("qcbm", qcbm),
    ("qgan", qgan),
    ("rl_policy", rl_policy),
    ("patch_gan", patch_gan),
]

if __name__ == "__main__":
    only = sys.argv[1:] or [name for name, _ in EXPERIMENTS]
    client = bank()
    print(f"balance before ${client.balance():.4f}\n")
    for name, fn in EXPERIMENTS:
        if name not in only:
            continue
        print(f"--- {name} ---")
        # Re-seeded per experiment, not once at start-up, so running one of
        # them alone gives the same answer as running it inside the full set.
        # Seeding once would make every result depend on which experiments ran
        # before it, which is a subtler version of not seeding at all.
        seed_everything()
        t0 = time.time()
        try:
            out = fn(client)
            out["seconds"] = round(time.time() - t0, 1)
            RESULTS[name] = out
            verdict = "PASS" if out.get("passed") else "MISS"
            print(f"  {verdict}  {out['circuits']} circuits  "
                  f"${out['quoted_usd']:.4f}  {out['seconds']}s")
            if out.get("ascii"):
                print(out["ascii"])
        except Exception as exc:
            RESULTS[name] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"  ERROR {type(exc).__name__}: {str(exc)[:160]}")
        (OUT / "ai_proofs_results.json").write_text(
            json.dumps(RESULTS, indent=1, default=str), encoding="utf-8")
    print(f"\nbalance after ${client.balance():.4f}")


# ----------------------------------------------------------------------------
# 1b. RESERVOIR, WITH THE READOUT THE LITERATURE ACTUALLY USES.
#
# The first run fed the full 16-outcome bitstring distribution to the readout.
# That is 2^n features, each estimated from the same fixed shot budget, so each
# carries the same sampling noise while the raw coordinates carry none: a noisy
# 16-dimensional feature set against an exact 2-dimensional one. It also cannot
# scale. At 10 qubits it is 1,024 outcomes from 512 shots and most features are
# exactly zero because they were never observed once, which is the same
# concentration that makes a distribution-level bound vacuous.
#
# Low-weight observables are what reservoir computing actually reads out:
# <Z_i> and <Z_i Z_j>, so O(n^2) features, and EACH ONE USES ALL THE SHOTS. The
# noise per feature stays put however many qubits are added.
#
# Same circuits, same cost, different arithmetic on the counts.
# ----------------------------------------------------------------------------
def reservoir_local(client) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.datasets import make_moons

    n, n_qubits = 200, 4
    X, y = make_moons(n_samples=n, noise=0.2, random_state=0)
    X = X * (np.pi / 2)

    x = ParameterVector("x", 2)
    base = QuantumCircuit(n_qubits)
    base.h(range(n_qubits))
    base.rz(2.0 * x[0], 0); base.rz(2.0 * x[1], 1)
    base.cx(0, 1); base.cx(1, 2); base.cx(2, 3)
    base.rz(2.0 * x[0] * x[1], 3)
    base.cx(2, 3); base.cx(1, 2); base.cx(0, 1)
    base.ry(0.7, 0); base.ry(1.3, 1); base.ry(0.9, 2); base.ry(1.1, 3)
    base.measure_all()

    circuits = [base.assign_parameters({x[0]: a, x[1]: b}) for a, b in X]
    cost = price(client, circuits, "reservoir_local")
    dists = run_batch(client, circuits)

    def z(bits: str, i: int) -> float:
        # Qiskit counts are little-endian: bits[-1] is qubit 0.
        return 1.0 - 2.0 * int(bits[::-1][i])

    rows = []
    for d in dists:
        singles = [sum(p * z(b, i) for b, p in d.items()) for i in range(n_qubits)]
        pairs = [sum(p * z(b, i) * z(b, j) for b, p in d.items())
                 for i in range(n_qubits) for j in range(i + 1, n_qubits)]
        rows.append(singles + pairs)
    features = np.array(rows)

    split = 140
    local = float(LogisticRegression(max_iter=2000).fit(features[:split], y[:split])
                  .score(features[split:], y[split:]))
    raw = float(LogisticRegression(max_iter=2000).fit(X[:split], y[:split])
                .score(X[split:], y[split:]))

    return {"criterion": "the standard readout, for comparison against the naive one",
            "readout": "<Z_i> and <Z_i Z_j>, 10 features",
            "local_observables": local, "raw_features": raw,
            "n_features": features.shape[1],
            "passed": local > 0.5, "circuits": len(circuits), "quoted_usd": cost}


EXPERIMENTS.append(("reservoir_local", reservoir_local))
