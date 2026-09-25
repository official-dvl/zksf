"""The two-moons data behind the quantum classification case, in one place.

Both quantum methods on
https://zksf.org/applications/ai-quantum-computing/quantum-classification/
and every classical baseline beside them read their data from here, so the
comparison is on identical points.

For a seed, numpy's default_rng(seed) draws the 22 training points first, then
the 40 test points. The variational classifier then draws its four starting
angles from the same generator, so the order of those calls is part of the
dataset's definition and must not change.

Features are scaled into [0, pi] on the TRAINING range only, so a test point
can land slightly outside it. That is how the published runs encoded them.
"""
from __future__ import annotations

import numpy as np

N_TRAIN, N_TEST, NOISE = 22, 40, 0.12


def moons(n: int, noise: float, rng: np.random.Generator):
    """Two interleaving half-circles, shuffled. Not linearly separable."""
    k = n // 2
    t_out = np.pi * rng.random(k)
    t_in = np.pi * rng.random(n - k)
    x = np.vstack([
        np.c_[np.cos(t_out), np.sin(t_out)],
        np.c_[1 - np.cos(t_in), 0.5 - np.sin(t_in)],
    ])
    y = np.r_[np.zeros(k, dtype=int), np.ones(n - k, dtype=int)]
    x = x + rng.normal(0, noise, x.shape)
    order = rng.permutation(n)
    return x[order], y[order]


def split(seed: int):
    """(xtr, ytr, xte, yte, rng): raw features, labels, and the generator
    positioned after the data, for anything that draws next."""
    rng = np.random.default_rng(seed)
    xtr, ytr = moons(N_TRAIN, NOISE, rng)
    xte, yte = moons(N_TEST, NOISE, rng)
    return xtr, ytr, xte, yte, rng


def to_angles(xtr: np.ndarray, *others: np.ndarray):
    """Min-max scale into [0, pi] on the training range."""
    lo, hi = xtr.min(0), xtr.max(0)
    return [(a - lo) / (hi - lo) * np.pi for a in (xtr, *others)]
