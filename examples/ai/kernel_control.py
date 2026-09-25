"""The quantum kernel computed exactly, locally, for free.

The control for quantum_kernel.py. It builds the same ZZ feature map on the same
data (two_moons.py), takes each kernel entry from the statevector instead of
from shots, and trains the same SVM, so it:

  1. reproduces the published kernel accuracies to the digit, since nothing in
     it is random once the seed has fixed the data;
  2. checks the circuit computes the kernel it claims to: K(x, x) must be
     exactly 1 for any valid overlap kernel, because U(x)^dagger U(x) is the
     identity;
  3. shows how much the result depends on the input scaling, a constant that
     carries no information about the problem: the published runs scale the
     features into [0, pi], and the sweep below tries narrower ranges and a
     depth-1 map.

    python kernel_control.py
"""
from __future__ import annotations

import numpy as np
from qiskit.quantum_info import Statevector
from sklearn.svm import SVC

from two_moons import split, to_angles


def feature_map_state(a, depth: int) -> np.ndarray:
    """The ZZ feature map of quantum_kernel.py, as a statevector."""
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(2)
    for _ in range(depth):
        qc.h(0)
        qc.h(1)
        qc.rz(2.0 * a[0], 0)
        qc.rz(2.0 * a[1], 1)
        qc.cx(0, 1)
        qc.rz(2.0 * (np.pi - a[0]) * (np.pi - a[1]), 1)
        qc.cx(0, 1)
    return Statevector(qc).data


def exact_kernel_accuracy(seed: int, depth: int = 2, top: float = np.pi):
    xtr, ytr, xte, yte, _ = split(seed)
    Xtr, Xte = (a * (top / np.pi) for a in to_angles(xtr, xte))
    Str = np.array([feature_map_state(a, depth) for a in Xtr])
    Ste = np.array([feature_map_state(a, depth) for a in Xte])
    Ktr = np.abs(Str.conj() @ Str.T) ** 2
    Kte = np.abs(Ste.conj() @ Str.T) ** 2
    diag = float(np.abs(np.diag(Ktr) - 1.0).max())
    acc = float(SVC(kernel="precomputed").fit(Ktr, ytr).score(Kte, yte))
    rbf = float(SVC(kernel="rbf").fit(xtr, ytr).score(xte, yte))
    return acc, rbf, diag


def main() -> None:
    print("The published setting: depth 2, features scaled into [0, pi].")
    for seed in (1, 2, 3):
        acc, rbf, diag = exact_kernel_accuracy(seed)
        print(f"  seed {seed}: exact quantum kernel {acc:.3f}   RBF {rbf:.3f}   |K_ii - 1| max {diag:.1e}")

    print("\nThe same data, seed 1, other scalings and depths:")
    for depth in (1, 2):
        for name, top in (("pi", np.pi), ("pi/2", np.pi / 2), ("1", 1.0), ("1/2", 0.5)):
            acc, _, _ = exact_kernel_accuracy(1, depth, top)
            print(f"  depth {depth}, features in [0, {name:>4}]: {acc:.3f}")


if __name__ == "__main__":
    main()
