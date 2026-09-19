"""Logistics and manufacturing instances, generated so they can be published.

WHY THIS FILE EXISTS. The published logistics and manufacturing rows were
measured on instances that were never saved: no generator, no seed, nothing in
the repo or the notebooks. Anyone trying to reproduce those numbers could not,
and the docs' reproduce section for both sectors says "your QUBO matrix", which
teaches the method and hands over no instance.

So both instances are rebuilt here, seeded and exhaustively solved, and every
device row is measured against them together. 16 binaries each, which is 65,536
assignments: small enough to know the true optimum, large enough that hardware
has to work for it.

Run: python sector_instances.py            # build, solve exactly, print
     python sector_instances.py --measure  # also submit to the three devices
"""
from __future__ import annotations

import itertools
import json
import pathlib
import sys
import time

import numpy as np

SEED = 20260919
HERE = pathlib.Path(__file__).parent


def logistics_instance(seed: int = SEED):
    """Vehicle routing as an assignment QUBO: 4 vehicles, 4 stops, one each.

    Cost is the distance a vehicle drives to its stop. The constraint is that
    every stop is served exactly once and every vehicle takes exactly one stop,
    both as penalties, which is the standard QUBO form the sector page describes.
    """
    rng = np.random.default_rng(seed)
    v, s = 4, 4
    depots = rng.uniform(0, 10, (v, 2))
    stops = rng.uniform(0, 10, (s, 2))
    dist = np.linalg.norm(depots[:, None, :] - stops[None, :, :], axis=2)

    n = v * s
    pen = float(dist.max()) * 4.0
    Q = np.zeros((n, n))
    idx = lambda a, b: a * s + b  # noqa: E731
    for a in range(v):
        for b in range(s):
            Q[idx(a, b), idx(a, b)] = float(dist[a, b]) - 2 * pen
    for a in range(v):  # one stop per vehicle
        for b1 in range(s):
            for b2 in range(b1 + 1, s):
                Q[idx(a, b1), idx(a, b2)] += pen
                Q[idx(a, b2), idx(a, b1)] += pen
    for b in range(s):  # one vehicle per stop
        for a1 in range(v):
            for a2 in range(a1 + 1, v):
                Q[idx(a1, b), idx(a2, b)] += pen
                Q[idx(a2, b), idx(a1, b)] += pen

    def feasible(x):
        m = x.reshape(v, s)
        return bool((m.sum(axis=1) == 1).all() and (m.sum(axis=0) == 1).all())

    def objective(x):
        return float((x.reshape(v, s) * dist).sum())

    meta = {"vehicles": v, "stops": s, "distances": dist.round(6).tolist()}
    return Q, feasible, objective, meta


def manufacturing_instance(seed: int = SEED):
    """Job-shop as a QUBO: 4 jobs, 4 time slots, one slot each.

    Cost is each job's lateness against its due slot. Two jobs sharing a machine
    in the same slot is a conflict and is penalised, which is what makes it
    harder than a plain assignment.
    """
    rng = np.random.default_rng(seed + 1)
    j, t = 4, 4
    due = rng.integers(0, t, j)
    machine = rng.integers(0, 2, j)      # two machines
    weight = rng.uniform(1, 4, j)

    n = j * t
    lateness = np.array([[weight[a] * max(0, b - due[a]) for b in range(t)] for a in range(j)])
    pen = float(lateness.max() + 1) * 4.0
    Q = np.zeros((n, n))
    idx = lambda a, b: a * t + b  # noqa: E731
    for a in range(j):
        for b in range(t):
            Q[idx(a, b), idx(a, b)] = float(lateness[a, b]) - 2 * pen
    for a in range(j):  # one slot per job
        for b1 in range(t):
            for b2 in range(b1 + 1, t):
                Q[idx(a, b1), idx(a, b2)] += pen
                Q[idx(a, b2), idx(a, b1)] += pen
    for b in range(t):  # no two jobs on one machine in one slot
        for a1 in range(j):
            for a2 in range(a1 + 1, j):
                if machine[a1] == machine[a2]:
                    Q[idx(a1, b), idx(a2, b)] += pen
                    Q[idx(a2, b), idx(a1, b)] += pen

    def feasible(x):
        m = x.reshape(j, t)
        if not (m.sum(axis=1) == 1).all():
            return False
        for b in range(t):
            slot = [a for a in range(j) if m[a, b]]
            if len({machine[a] for a in slot}) != len(slot):
                return False
        return True

    def objective(x):
        return float((x.reshape(j, t) * lateness).sum())

    meta = {"jobs": j, "slots": t, "due": due.tolist(), "machine": machine.tolist(),
            "weight": weight.round(6).tolist()}
    return Q, feasible, objective, meta


def solve_exactly(n, feasible, objective):
    best, best_x = np.inf, None
    for bits in itertools.product([0, 1], repeat=n):
        x = np.array(bits, int)
        if feasible(x):
            v = objective(x)
            if v < best:
                best, best_x = v, x
    return best, best_x


def main() -> None:
    out = {"seed": SEED, "sectors": {}}
    for name, build in (("logistics", logistics_instance), ("manufacturing", manufacturing_instance)):
        Q, feasible, objective, meta = build()
        n = Q.shape[0]
        t0 = time.perf_counter()
        best, best_x = solve_exactly(n, feasible, objective)
        meta.update({
            "qubits": n,
            "exhaustive_optimum": round(best, 6),
            "optimal_assignment": best_x.tolist(),
            "exhaustive_seconds": round(time.perf_counter() - t0, 3),
            "Q": np.round(Q, 6).tolist(),
        })
        out["sectors"][name] = meta
        print(f"{name}: {n} qubits, optimum {best:.6f} in {meta['exhaustive_seconds']}s")
    (HERE / "sector_instances.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"written {HERE / 'sector_instances.json'}")


if __name__ == "__main__":
    main()
