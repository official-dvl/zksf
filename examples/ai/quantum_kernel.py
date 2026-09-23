"""A quantum kernel SVM against production, on the same data Run A used.

Run A trained a variational classifier. This is the other half of the quantum
machine learning literature: no training of the circuit at all. A feature map
embeds each data point, the kernel entry between two points is the overlap of
their embeddings, and a classical SVM does the learning on that matrix.

    K(x, y) = |<0| U(y)^dagger U(x) |0>|^2

measured as the probability of the all-zeros string after running U(x) and then
the inverse of U(y). No parameters move, so there is no gradient and no
optimiser: it is N(N+1)/2 independent circuits and a batch endpoint, which is
why this is the cheapest credible quantum ML result available here.

Deliberately the SAME dataset, the same seeds and the same train/test split as
Run A, so the two numbers sit in one table and the comparison is real rather
than rhetorical.

Priced with /estimate/batch before anything is submitted, and the true cost is
read from the account balance before and after rather than computed.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector
from sklearn.datasets import make_moons
from sklearn.svm import SVC

import qsim_sdk  # noqa: E402

# From the environment, so this file carries no path to a secrets store.
TOKEN = os.environ.get("ZKSF_API_TOKEN")
if not TOKEN:
    raise SystemExit("set ZKSF_API_TOKEN to an API key (console: Profile > Create API key)")

ENGINE = "exact.cpu"
SHOTS = 2048
N_TRAIN = 22          # Run A's split, exactly
N_TEST = 40
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 1

x = ParameterVector("x", 2)


def feature_map(params) -> QuantumCircuit:
    """A ZZ feature map, depth 2: the standard choice in the QSVM literature.

    The entangling ZZ term is the part with no classical analogue. Without it
    the map factorises and the kernel collapses to a product of single-qubit
    overlaps, which is a classical kernel computed expensively.
    """
    qc = QuantumCircuit(2)
    for _ in range(2):
        qc.h(0)
        qc.h(1)
        qc.rz(2.0 * params[0], 0)
        qc.rz(2.0 * params[1], 1)
        qc.cx(0, 1)
        qc.rz(2.0 * (np.pi - params[0]) * (np.pi - params[1]), 1)
        qc.cx(0, 1)
    return qc


def overlap_circuit(a, b) -> QuantumCircuit:
    """U(a) then U(b)^dagger, measured. P(00) is the kernel entry."""
    fm = feature_map(x)
    qc = fm.assign_parameters({x[0]: a[0], x[1]: a[1]})
    qc = qc.compose(fm.assign_parameters({x[0]: b[0], x[1]: b[1]}).inverse())
    qc.measure_all()
    return qc


def main() -> None:
    X, y = make_moons(n_samples=N_TRAIN + N_TEST, noise=0.2, random_state=SEED)
    X = X * (np.pi / 2.0)                       # into a sensible angle range
    Xtr, ytr = X[:N_TRAIN], y[:N_TRAIN]
    Xte, yte = X[N_TRAIN:], y[N_TRAIN:]

    # The train kernel is symmetric with a unit diagonal, so only the strict
    # upper triangle is submitted. Half the circuits for the same matrix.
    train_pairs = [(i, j) for i in range(N_TRAIN) for j in range(i + 1, N_TRAIN)]
    test_pairs = [(i, j) for i in range(N_TEST) for j in range(N_TRAIN)]

    circuits = [overlap_circuit(Xtr[i], Xtr[j]) for i, j in train_pairs]
    circuits += [overlap_circuit(Xte[i], Xtr[j]) for i, j in test_pairs]
    print(f"seed {SEED}: {len(train_pairs)} train pairs + {len(test_pairs)} test "
          f"pairs = {len(circuits)} circuits")

    client = qsim_sdk.Client(token=TOKEN)

    # per_point_usd is one figure PER POINT, not an average: the floor is
    # charged per circuit, so the list is what makes that visible.
    est = client.estimate_batch(circuits, shots=SHOTS, engine=ENGINE)
    per_point = est["per_point_usd"]
    print(f"  quoted: ${est['total_usd']:.4f} over {est['points']} points in "
          f"{est['batches']} requests (${per_point[0]:.6f} a point)")

    before = client.balance()
    print(f"  balance before: ${before:.4f}")

    started = time.time()
    results: list[float] = []
    CHUNK = 200
    for start in range(0, len(circuits), CHUNK):
        part = circuits[start:start + CHUNK]
        job = client.run_batch(part, shots=SHOTS, engine=ENGINE, timeout=900.0)
        for item in job["results"]:
            counts = (item.get("result") or {}).get("counts") or {}
            total = sum(counts.values())
            results.append(counts.get("00", 0) / total if total else float("nan"))
        print(f"    {start + len(part)}/{len(circuits)}")
    elapsed = time.time() - started

    after = client.balance()
    charged = (before - after) if (before is not None and after is not None) else None
    print(f"  balance after:  ${after:.4f}   charged ${charged:.4f}")

    Ktr = np.eye(N_TRAIN)
    for (i, j), v in zip(train_pairs, results[:len(train_pairs)]):
        Ktr[i, j] = Ktr[j, i] = v
    Kte = np.zeros((N_TEST, N_TRAIN))
    for (i, j), v in zip(test_pairs, results[len(train_pairs):]):
        Kte[i, j] = v

    svc = SVC(kernel="precomputed").fit(Ktr, ytr)
    q_acc = float(svc.score(Kte, yte))

    classical = {}
    for name, kern in (("RBF", "rbf"), ("linear", "linear")):
        c = SVC(kernel=kern).fit(Xtr, ytr)
        classical[name] = float(c.score(Xte, yte))

    out = {
        "seed": SEED, "engine": ENGINE, "shots": SHOTS,
        "n_train": N_TRAIN, "n_test": N_TEST,
        "circuits": len(circuits), "seconds": round(elapsed, 1),
        "quoted_usd": est["total_usd"], "charged_usd": charged,
        "quantum_kernel_svm": q_acc, "classical": classical,
        "kernel_offdiag_mean": float(Ktr[np.triu_indices(N_TRAIN, 1)].mean()),
    }
    print(json.dumps(out, indent=1))
    pathlib.Path(__file__).with_name(f"kernel_seed_{SEED}.json").write_text(
        json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
