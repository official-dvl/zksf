"""Free local control for the production kernel run.

The production run scored 0.475 against an RBF kernel's 0.85. Below chance on a
balanced binary problem is not a result, it is a symptom, and there are three
candidate causes that the production number alone cannot tell apart:

  1. the feature map genuinely does not separate this data,
  2. shot noise made the 22x22 kernel matrix non-PSD and broke the SVM,
  3. the circuit I wrote does not compute the kernel I think it does.

This computes the SAME kernel exactly, by statevector, with no shots and no
submissions, so it costs nothing and isolates all three. If exact also scores
0.475 then cause 1 or 3; if exact scores well then cause 2 and the production
number is an artefact of my own measurement rather than a property of the
method.

The unit-diagonal check settles cause 3 on its own: K(x, x) must be exactly 1
for any valid overlap kernel, because U(x)^dagger U(x) is the identity.
"""
from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import ParameterVector
from qiskit.quantum_info import Statevector
from sklearn.datasets import make_moons
from sklearn.svm import SVC

N_TRAIN, N_TEST, SEED = 22, 40, 1
x = ParameterVector("x", 2)


def feature_map(params, depth: int = 2) -> QuantumCircuit:
    qc = QuantumCircuit(2)
    for _ in range(depth):
        qc.h(0)
        qc.h(1)
        qc.rz(2.0 * params[0], 0)
        qc.rz(2.0 * params[1], 1)
        qc.cx(0, 1)
        qc.rz(2.0 * (np.pi - params[0]) * (np.pi - params[1]), 1)
        qc.cx(0, 1)
    return qc


def state(a, depth: int) -> np.ndarray:
    fm = feature_map(x, depth)
    return Statevector(fm.assign_parameters({x[0]: a[0], x[1]: a[1]})).data


def run(depth: int, scale: float) -> None:
    X, y = make_moons(n_samples=N_TRAIN + N_TEST, noise=0.2, random_state=SEED)
    X = X * scale
    Xtr, ytr, Xte, yte = X[:N_TRAIN], y[:N_TRAIN], X[N_TRAIN:], y[N_TRAIN:]

    Str = np.array([state(a, depth) for a in Xtr])
    Ste = np.array([state(a, depth) for a in Xte])
    Ktr = np.abs(Str.conj() @ Str.T) ** 2          # exact, no shots
    Kte = np.abs(Ste.conj() @ Str.T) ** 2

    diag = float(np.abs(np.diag(Ktr) - 1.0).max())
    off = Ktr[np.triu_indices(N_TRAIN, 1)]
    q = float(SVC(kernel="precomputed").fit(Ktr, ytr).score(Kte, yte))
    rbf = float(SVC(kernel="rbf").fit(Xtr, ytr).score(Xte, yte))

    print(f"depth={depth} scale={scale:.3f}  exact QSVM {q:.3f}   RBF {rbf:.3f}   "
          f"|K_ii - 1| max {diag:.2e}   off-diag mean {off.mean():.3f} "
          f"sd {off.std():.3f}")


print("Is the circuit right? K_ii must be exactly 1.\n")
for depth in (1, 2):
    for scale in (np.pi / 2, 1.0, 0.5, 0.25):
        run(depth, scale)
