"""Run B, rebuilt: a photonic generator trained on a linear-optics simulator.

WHY THIS FILE EXISTS. The original photonic generative leg (published 18 Sep
2026 as P(target) 0.993 / 0.835 / 0.802 / 0.754 / 0.085 across five random
starts) could not be reproduced. Its program was never committed, its converged
weights were never saved, and the training was unseeded, so the five starts were
five numbers nobody could get back. See "Reproducibility: the training was never
seeded" in AI QUANTUM.md.

This is therefore a NEW experiment on the same shape, not a re-run, and it
replaces the old figures rather than confirming them. Everything the old one
lacked is here: the circuit is in this file, every start is seeded, and the
converged weights are written to photonic_qgan_results.json.

THE SHAPE. Three modes with two photons entering modes 0 and 2, which is the
input Belenos can actually produce: its single-photon sources sit on alternating
modes, so the same program runs on hardware unchanged. Three trainable
beamsplitters span U(3). The target mirrors the gate QGAN on the same page,
0.4 / 0.1 / 0.1 / 0.4, so the photonic row and the gate rows are scored the same
way and can sit in one table.

Two numbers are reported per start:
  TVD       to the target, the same metric every gate row on this page uses
  P(target) the mass landing on the four supported outcomes, which is the
            metric the retired row used, kept so the two can be compared
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys

import perceval as pcvl
import torch

import qsim_sdk
from qsim_sdk.ml import PhotonicLayer

SHOTS = 1000
STEPS = 30
STARTS = 5
ENGINE = "photonic.slos.cpu"

#: Every Fock state two photons can occupy across three modes, in a fixed order.
#: Fixed at construction because which states appear varies with shot noise.
OUTCOMES = ["|2,0,0>", "|1,1,0>", "|1,0,1>", "|0,2,0>", "|0,1,1>", "|0,0,2>"]

#: The gate QGAN's target, carried onto the photonic outcomes: the two bunched
#: states take 0.4 each and the two mixed states 0.1 each, so the same
#: 0.4 / 0.1 / 0.1 / 0.4 shape is being learned by both halves of the case.
TARGET = torch.tensor([0.4, 0.1, 0.0, 0.0, 0.1, 0.4])
SUPPORT = [i for i, v in enumerate(TARGET.tolist()) if v > 0]


def generator() -> pcvl.Circuit:
    """Three trainable beamsplitters, which span U(3) up to phases."""
    return (
        pcvl.Circuit(3)
        // (0, pcvl.BS(theta=pcvl.P("t0")))
        // (1, pcvl.BS(theta=pcvl.P("t1")))
        // (0, pcvl.BS(theta=pcvl.P("t2")))
    )


def tvd(p: torch.Tensor, q: torch.Tensor) -> float:
    return float((p - q).abs().sum() / 2)


def train_one(client, seed: int) -> dict:
    """One seeded start. The seed is the only thing that differs between them."""
    torch.manual_seed(seed)
    init = (torch.rand(3) * 2.0).tolist()          # drawn, but drawn reproducibly
    layer = PhotonicLayer(
        client, generator(), [1, 0, 1],
        shots=SHOTS, engine=ENGINE, eps=0.25, init=init,
        outcomes=OUTCOMES,
    )
    opt = torch.optim.Adam(layer.parameters(), lr=0.20)
    first = None
    for step in range(STEPS):
        probs = layer()
        loss = (probs - TARGET).abs().sum() / 2     # total variation distance
        if first is None:
            first = float(loss)
        opt.zero_grad()
        loss.backward()
        opt.step()
        print(f"    seed {seed} step {step:2d}  TVD {float(loss):.4f}", flush=True)

    final = layer().detach()
    # One tensor holding every angle, not one tensor per angle, so flatten.
    weights = [float(v) for p in layer.parameters() for v in p.detach().flatten()]
    return {
        "seed": seed,
        "init": init,
        "weights": weights,
        "tvd_before": first,
        "tvd_after": tvd(final, TARGET),
        "p_target": float(final[SUPPORT].sum()),
        "distribution": {o: round(float(v), 4) for o, v in zip(OUTCOMES, final.tolist())},
    }


def token() -> str:
    """From the environment, so this file carries no path to a secrets store.

    The repo's convention is that anything reading credentials stays untracked
    (see run_with_keys.py, "LOCAL ONLY, gitignored"). Reading an env var instead
    is what lets this script be committed, which is the entire point: the
    experiment it replaced was lost because it never was.
    """
    tok = os.environ.get("ZKSF_API_TOKEN")
    if not tok:
        raise SystemExit(
            "set ZKSF_API_TOKEN to an API key from the console (Profile -> API keys)"
        )
    return tok


def main() -> None:
    client = qsim_sdk.Client(token=token())

    runs = []
    for seed in range(STARTS):
        print(f"  start {seed + 1} of {STARTS}", flush=True)
        runs.append(train_one(client, seed))

    best = max(runs, key=lambda r: r["p_target"])
    out = {
        "engine": ENGINE,
        "shots": SHOTS,
        "steps": STEPS,
        "starts": STARTS,
        "seeds": list(range(STARTS)),
        "target": {o: float(v) for o, v in zip(OUTCOMES, TARGET.tolist())},
        "input_state": "|1,0,1>",
        "runs": runs,
        "best_seed": best["seed"],
        "best_weights": best["weights"],
    }
    here = pathlib.Path(__file__).parent
    (here / "photonic_qgan_results.json").write_text(json.dumps(out, indent=1), encoding="utf8")
    print("\n  P(target) by seed:", [round(r["p_target"], 4) for r in runs])
    print("  TVD by seed:      ", [round(r["tvd_after"], 4) for r in runs])
    print(f"  best seed {best['seed']}, weights {best['weights']}")


if __name__ == "__main__":
    main()
