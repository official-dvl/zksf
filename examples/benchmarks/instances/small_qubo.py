"""The random 16-variable QUBOs behind the logistics and manufacturing tables.

The mps.quimb.cpu, exact.cpu, exact.gpu, IQM Garnet and IQM Emerald rows on
zksf.org/applications/logistics and /manufacturing are scored on these two
instances. They are random QUBOs of the size a machine can hold, with no routing
or scheduling structure in them: the real problems need 10,000 and 268,425
qubits and fit nothing. The Rigetti rows use the structured 4-vehicle and 4-job
instances in sector_instances.py instead.

    python small_qubo.py

prints -18.7897 for seed 20260902 (logistics) and -15.6952 for seed 20260903
(manufacturing), the exact optima the tables quote.
"""
import itertools

import numpy as np


def small_qubo(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    W = rng.uniform(-1, 1, (n, n))
    W = (W + W.T) / 2
    np.fill_diagonal(W, rng.uniform(-1, 1, n))
    return W


def exact_minimum(W: np.ndarray) -> float:
    """x^T W x minimised over every bitstring, which 16 variables allows."""
    X = np.array(list(itertools.product([0, 1], repeat=W.shape[0])))
    return float(np.einsum("ij,jk,ik->i", X, W, X).min())


if __name__ == "__main__":
    for page, seed in (("logistics", 20260902), ("manufacturing", 20260903)):
        print(f"{page:<14} seed {seed}: exact optimum {exact_minimum(small_qubo(16, seed)):.4f}")
