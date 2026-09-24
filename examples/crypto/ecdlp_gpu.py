"""Shor's discrete-logarithm algorithm against a real elliptic curve, on ZKSF.

Recovers a private key d from the public key Q = dP, building the circuit from
public data only. The secret is used once, at the end, to check the answer.
Reproduces the 7-bit GPU run on https://zksf.org/applications/cryptography/:
21 qubits, 64 shots, private key 67 recovered.

    pip install qsim-sdk
    export ZKSF_API_TOKEN=...          # console: Profile > Create API key
    python ecdlp_gpu.py                # 7 bits on exact.gpu
    python ecdlp_gpu.py 5 exact.cpu    # any size from 3 bits, any engine

Circuit, for a curve whose group is cyclic of order r = 2^n:

    |a>  n qubits, Hadamard'd         exponent register for the generator
    |b>  n qubits, Hadamard'd         exponent register for the public key
    |e>  n qubits, starts at infinity holds a curve point

    controlled on a_i: add (2^i)P to |e>;  controlled on b_j: add (2^j)Q to |e>
    inverse QFT on |a> and |b>, measure both

Because r is exactly the register dimension the transform is exact, so every
outcome satisfies y = d*x (mod r), and d = y * x^-1 whenever x is odd. Building
each "add a point" permutation enumerates the group, so this demonstrates the
algorithm and measures its width and depth; at 256 bits the enumeration would
itself be the attack.
"""
from __future__ import annotations

import os
import sys

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, transpile
from qiskit.circuit.library import QFT

import ecdlp_curves as ec
import qsim_sdk
from permutation import controlled_permutation_gate

SHOTS = 64


def build(curve: ec.Curve, d: int) -> tuple[QuantumCircuit, ec.Point]:
    n = curve.bits
    Q = ec.mul(d, curve.gen, curve.a, curve.p)
    a_reg, b_reg, e_reg = QuantumRegister(n, "a"), QuantumRegister(n, "b"), QuantumRegister(n, "e")
    # Not "x" and "y": OpenQASM 2.0 has one namespace, and qelib1 already has
    # gates called x and y, so registers with those names are refused.
    ca, cb = ClassicalRegister(n, "xr"), ClassicalRegister(n, "yr")
    qc = QuantumCircuit(a_reg, b_reg, e_reg, ca, cb)
    qc.h(a_reg)
    qc.h(b_reg)
    for i in range(n):
        R = ec.mul(1 << i, curve.gen, curve.a, curve.p)
        qc.append(controlled_permutation_gate(ec.add_point_permutation(curve, R, n), f"+2^{i}P"),
                  [a_reg[i], *e_reg])
    for j in range(n):
        R = ec.mul(1 << j, Q, curve.a, curve.p)
        qc.append(controlled_permutation_gate(ec.add_point_permutation(curve, R, n), f"+2^{j}Q"),
                  [b_reg[j], *e_reg])
    qc.append(QFT(n, inverse=True, do_swaps=True).to_gate(label="IQFT"), a_reg)
    qc.append(QFT(n, inverse=True, do_swaps=True).to_gate(label="IQFT"), b_reg)
    qc.measure(a_reg, ca)
    qc.measure(b_reg, cb)
    return qc, Q


def recover(counts: dict[str, int], curve: ec.Curve, Q: ec.Point) -> tuple[int | None, int, int]:
    """The best-supported key consistent with the shots, and how many shots were usable."""
    r = curve.order
    votes: dict[int, int] = {}
    usable, total = 0, sum(counts.values())
    for bits, c in counts.items():
        y_s, x_s = bits.split()            # the last register prints first
        x, y = int(x_s, 2), int(y_s, 2)
        if x % 2 == 0:                     # x must be invertible mod a power of two
            continue
        usable += c
        d = y * pow(x, -1, r) % r
        votes[d] = votes.get(d, 0) + c
    if not votes:
        return None, usable, total
    best = max(votes, key=votes.get)
    return (best if ec.mul(best, curve.gen, curve.a, curve.p) == Q else None), usable, total


def main() -> None:
    bits = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    engine = sys.argv[2] if len(sys.argv) > 2 else "exact.gpu"
    curve = ec.find_cyclic_curve(2 ** bits)
    d = curve.order // 2 + 3                # not small, not a power of two, odd
    while d % 2 == 0:
        d += 1
    qc, Q = build(curve, d)
    flat = transpile(qc, basis_gates=["cx", "u"], optimization_level=1)
    print(f"{bits}-bit key over F_{curve.p}: {flat.num_qubits} qubits, "
          f"{flat.count_ops().get('cx', 0):,} two-qubit gates")

    client = qsim_sdk.Client(token=os.environ.get("ZKSF_API_TOKEN"))
    est = client.estimate(flat, shots=SHOTS, engine=engine)
    print(f"quote: ${est['predicted_cost_usd']:.4f}, about {est['predicted_seconds']:.0f} s")

    job = client.run(flat, shots=SHOTS, engine=engine, timeout=3600)
    found, usable, total = recover(job["result"]["counts"], curve, Q)
    print(f"secret {d}, recovered {found}, from {usable} usable shots of {total}")


if __name__ == "__main__":
    main()
