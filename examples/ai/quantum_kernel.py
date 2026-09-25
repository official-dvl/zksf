"""A quantum kernel SVM on the variational classifier's own data.

The quantum kernel on
https://zksf.org/applications/ai-quantum-computing/quantum-classification/

No training of the circuit at all. A feature map embeds each data point, the
kernel entry between two points is the overlap of their embeddings, and a
classical SVM does the learning on that matrix.

    K(x, y) = |<0| U(y)^dagger U(x) |0>|^2

measured as the probability of the all-zeros string after running U(x) and then
the inverse of U(y). No parameters move, so there is no gradient and no
optimiser: the strict upper triangle of the 22x22 training matrix plus the
40x22 test block is 1,111 independent circuits a seed.

The data, the split and the [0, pi] feature scaling are the variational
classifier's (two_moons.py), so both quantum methods and every baseline sit in
one table.

    python quantum_kernel.py 1            # seed 1, 2,048 shots a circuit, as published
    python quantum_kernel.py 1 --exact    # the same kernel as exact expectations

WHAT REPRODUCES

The seed fixes the data. With shots, the service samples the measurements and
that sampling takes no seed, so each kernel entry moves by up to a few hundredths
between runs (the published runs' largest error against the exact kernel was
0.037); on all three published seeds the SVM's accuracy was the same as the
exact kernel's. With --exact each circuit is sent with the observable
|00><00| = (II + IZ + ZI + ZZ) / 4 and the engine returns it computed from the
statevector, so a run returns the same kernel, and the same accuracy, every
time. kernel_control.py computes that exact kernel locally for free.

Priced with estimate_batch before anything is submitted, and the charge is read
from the account balance before and after.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import time

import numpy as np
from qiskit import QuantumCircuit
from sklearn.svm import SVC

import qsim_sdk
from two_moons import N_TEST, N_TRAIN, split, to_angles

ENGINE = "exact.cpu"
SHOTS = 2048
CHUNK = 200                   # the service's per-batch limit
P00 = [[0.25, "II"], [0.25, "IZ"], [0.25, "ZI"], [0.25, "ZZ"]]


def feature_map(a) -> QuantumCircuit:
    """A ZZ feature map, depth 2: the standard choice in the QSVM literature.

    The entangling ZZ term is the part with no classical analogue. Without it
    the map factorises and the kernel collapses to a product of single-qubit
    overlaps, which is a classical kernel computed expensively.
    """
    qc = QuantumCircuit(2)
    for _ in range(2):
        qc.h(0)
        qc.h(1)
        qc.rz(2.0 * a[0], 0)
        qc.rz(2.0 * a[1], 1)
        qc.cx(0, 1)
        qc.rz(2.0 * (np.pi - a[0]) * (np.pi - a[1]), 1)
        qc.cx(0, 1)
    return qc


def overlap_circuit(a, b) -> QuantumCircuit:
    """U(a) then U(b)^dagger, measured. P(00) is the kernel entry."""
    qc = feature_map(a).compose(feature_map(b).inverse())
    qc.measure_all()
    return qc


def pairs():
    """The train kernel is symmetric with a unit diagonal, so only its strict
    upper triangle is computed. Half the circuits for the same matrix."""
    train = [(i, j) for i in range(N_TRAIN) for j in range(i + 1, N_TRAIN)]
    test = [(i, j) for i in range(N_TEST) for j in range(N_TRAIN)]
    return train, test


def matrices(values, train_pairs, test_pairs):
    Ktr = np.eye(N_TRAIN)
    for (i, j), v in zip(train_pairs, values[:len(train_pairs)]):
        Ktr[i, j] = Ktr[j, i] = v
    Kte = np.zeros((N_TEST, N_TRAIN))
    for (i, j), v in zip(test_pairs, values[len(train_pairs):]):
        Kte[i, j] = v
    return Ktr, Kte


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("seed", type=int, nargs="?", default=1)
    ap.add_argument("--exact", action="store_true", help="exact expectations instead of shots")
    args = ap.parse_args()

    token = os.environ.get("ZKSF_API_TOKEN")
    if not token:
        raise SystemExit("set ZKSF_API_TOKEN to an API key (console: Profile > Create API key)")

    xtr, ytr, xte, yte, _ = split(args.seed)
    Xtr, Xte = to_angles(xtr, xte)
    train_pairs, test_pairs = pairs()
    circuits = [overlap_circuit(Xtr[i], Xtr[j]) for i, j in train_pairs]
    circuits += [overlap_circuit(Xte[i], Xtr[j]) for i, j in test_pairs]
    print(f"seed {args.seed}: {len(train_pairs)} train pairs + {len(test_pairs)} test "
          f"pairs = {len(circuits)} circuits, {'exact' if args.exact else f'{SHOTS} shots'}")

    client = qsim_sdk.Client(token=token)
    est = client.estimate_batch(circuits, shots=SHOTS, engine=ENGINE)
    print(f"  quoted ${est['total_usd']:.4f}")
    before = client.balance()

    started = time.time()
    values: list[float] = []
    for start in range(0, len(circuits), CHUNK):
        part = circuits[start:start + CHUNK]
        if args.exact:
            job = client.run_batch(part, engine=ENGINE, observable=P00, timeout=900.0)
        else:
            job = client.run_batch(part, shots=SHOTS, engine=ENGINE, timeout=900.0)
        for item in job["results"]:
            res = item.get("result") or {}
            if args.exact:
                values.append(float(res["expectation"]))
            else:
                counts = res.get("counts") or {}
                total = sum(counts.values())
                values.append(counts.get("00", 0) / total if total else float("nan"))
        print(f"    {start + len(part)}/{len(circuits)}")
    elapsed = time.time() - started
    after = client.balance()

    Ktr, Kte = matrices(values, train_pairs, test_pairs)
    q_acc = float(SVC(kernel="precomputed").fit(Ktr, ytr).score(Kte, yte))
    # The RBF baseline sees the raw features, untuned, as the classical
    # baselines beside the variational classifier are.
    rbf = float(SVC(kernel="rbf").fit(xtr, ytr).score(xte, yte))

    out = {
        "seed": args.seed, "engine": ENGINE, "shots": None if args.exact else SHOTS,
        "exact": args.exact, "n_train": N_TRAIN, "n_test": N_TEST,
        "circuits": len(circuits), "seconds": round(elapsed, 1),
        "quoted_usd": est["total_usd"],
        "charged_usd": round(before - after, 6) if before is not None and after is not None else None,
        "quantum_kernel_svm": q_acc, "rbf_svm": rbf,
    }
    print(json.dumps(out, indent=1))
    tag = "exact" if args.exact else f"shots{SHOTS}"
    pathlib.Path(__file__).with_name(f"kernel_seed_{args.seed}_{tag}.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
