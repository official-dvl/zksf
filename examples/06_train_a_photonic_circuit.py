"""Train a photonic circuit: a quantum layer inside an ordinary torch loop.

This is the shape every photonic machine-learning result has, including the
generative-model demonstrations the manufacturers advertise. A parameterised
optical mesh produces a probability distribution over detection patterns, that
distribution is the layer's output, a classical loss says how far it is from
what you wanted, and an optimiser walks the phase and beamsplitter angles until
the two agree. Nothing about it is a single button press: the run below issues
one job per forward pass and one job per gradient, which is why real training
runs fill a provider's queue for hours.

Here the target is deliberately one whose right answer is known, so the run can
be checked rather than admired: minimise the chance of two photons leaving a
beamsplitter separately. Hong-Ou-Mandel interference says that probability is
exactly zero at the balanced point, so a correct gradient must walk theta to
pi/2 and the loss must fall to the shot-noise floor.

Swap `engine=` for "qpu.quandela.belenos" to run the same loop on real photonic
hardware. Do the arithmetic first: every forward is one job and every backward
is two jobs per parameter, so 200 steps of a 6-parameter mesh is 2,600 tasks.
Settle the model in simulation, then spend the hardware budget on the trained
point. That is not a limitation of this service; it is why the manufacturers'
own frameworks train against simulators too.

    pip install qsim-sdk perceval-quandela torch
"""
from __future__ import annotations

import math

import perceval as pcvl
import torch

import qsim_sdk
from qsim_sdk.ml import PhotonicLayer

client = qsim_sdk.Client(token="YOUR_TOKEN")

# One trainable beamsplitter. A real model uses a mesh of them, and every
# pcvl.P(...) in it becomes a trainable parameter of the layer.
circuit = pcvl.Circuit(2) // (0, pcvl.BS(theta=pcvl.P("theta")))

layer = PhotonicLayer(
    client,
    circuit,
    [1, 1],                       # one photon into each input mode
    shots=4000,
    engine="photonic.slos.cpu",   # "qpu.quandela.belenos" for the real device
    init=[0.9],                   # start well away from the answer
    outcomes=["|1,1>", "|2,0>", "|0,2>"],
)
opt = torch.optim.SGD(layer.parameters(), lr=0.3)

for step in range(12):
    opt.zero_grad()
    probs = layer()               # P(|1,1>), P(|2,0>), P(|0,2>)
    loss = probs[0]               # suppress the coincidence term
    loss.backward()
    opt.step()
    print(f"step {step:2d}  theta {float(layer.theta):.4f}  P(|1,1>) {float(loss):.4f}")

print(f"\nconverged to theta = {float(layer.theta):.4f}, pi/2 = {math.pi / 2:.4f}")

# What the run cost, and what it would have cost on hardware. Every job here
# carries a free estimate, and the sweep endpoint charges per evaluated point,
# so the arithmetic is not a guess.
print("forward passes: 12 jobs of 1 point")
print("backward passes: 12 jobs of 2 points (one parameter, two displacements)")
