"""Circuits for permutations of basis states, without going through a matrix.

WHY THIS EXISTS. A permutation of the 2^n basis states is a perfectly ordinary
reversible operation, and the obvious way to hand one to Qiskit is to build the
2^n x 2^n permutation matrix and wrap it in a UnitaryGate. That works and it does
not scale: UnitaryGate throws away the fact that the matrix is a permutation, so
transpilation falls back on Quantum Shannon Decomposition, which costs on the
order of 4^n CNOTs and, at nine or ten qubits, does not finish in any time worth
waiting for.

The ECDLP experiment hit exactly this. Each "add a fixed curve point" step is a
permutation, and building one as a controlled UnitaryGate meant synthesising a
dense (n+1)-qubit unitary per step. It completed to 7 bits of key and hung at 8.
The published gate counts show the same thing from the other side: 328, 1,924,
10,090, 49,758 and 235,470 two-qubit gates at 3 to 7 bits is a ratio of 5.87,
5.24, 4.93 and 4.73, and 4*(n+1)/n (which is what QSD predicts for this shape)
gives 5.33, 5.00, 4.80 and 4.67. That scaling was the decomposition, not the
algorithm.

WHAT THIS DOES INSTEAD. Transformation-based synthesis (Miller, Maslov and Dueck,
DAC 2003). Walk the basis states in increasing order and, for each one whose
image is wrong, emit multiply-controlled X gates that correct it while leaving
every state already placed alone. The output is a list of MCX gates, so the cost
follows the permutation's own structure rather than the dimension of a matrix.

WHAT IT IS NOT. This is not a route to attacking real keys, and nothing here
changes that. Constructing the permutation at all means enumerating the group,
which at 256 bits IS the attack; see the ECDLP experiment's own note. What it
changes is that the circuit a study needs can now be built at sizes where the old
path stalled, and that the gates counted are the algorithm's rather than the
decomposition's.
"""
from __future__ import annotations

from qiskit import QuantumCircuit

#: One gate: flip `target` on any state whose `controls` bits are all 1.
#: An empty control mask is an unconditional X. Both are self-inverse, which is
#: what lets the synthesis below run the collected list backwards.
Gate = tuple[int, int]  # (control_mask, target_bit)


def _bits(mask: int) -> list[int]:
    out, b = [], 0
    while mask:
        if mask & 1:
            out.append(b)
        mask >>= 1
        b += 1
    return out


def synth_permutation(perm: list[int]) -> list[Gate]:
    """MCX gates whose product maps |i> to |perm[i]| for every i.

    Transformation-based synthesis. `work` starts as the permutation and is
    driven to the identity by composing gates onto its output side; the gates
    that did it, reversed, are the circuit.

    The invariant that makes it terminate is that after step i, every state at
    or below i maps to itself, and no later step disturbs them. Setting bits
    uses the current image's own 1-bits as controls and clearing them uses the
    target's, which is what keeps the already-placed states out of reach.
    """
    size = len(perm)
    width = max(1, (size - 1).bit_length())
    if size != 1 << width:
        raise ValueError(f"permutation length {size} is not a power of two")
    if sorted(perm) != list(range(size)):
        raise ValueError("not a permutation")

    work = list(perm)
    # Where each value currently sits, so a gate can be applied without
    # rewriting the whole table for every one of the 2^n entries.
    where = [0] * size
    for idx, val in enumerate(work):
        where[val] = idx

    def apply(mask: int, target: int) -> None:
        """Compose MCX(mask, target) onto the output side of `work`."""
        bit = 1 << target
        for value in range(size):
            if value & mask == mask and not value & bit:
                partner = value | bit
                i, j = where[value], where[partner]
                work[i], work[j] = work[j], work[i]
                where[value], where[partner] = j, i

    gates: list[Gate] = []
    for i in range(size):
        v = work[i]
        if v == i:
            continue
        # Bits i needs that its image lacks. Controlling on the image's own
        # 1-bits reaches the image and nothing already placed below i.
        for b in _bits(i & ~v):
            gates.append((v, b))
            apply(v, b)
            v |= 1 << b
        # Bits the image carries that i does not. Now that v covers i, i's
        # 1-bits are a safe control set for clearing the rest.
        for b in _bits(~i & v & (size - 1)):
            gates.append((i, b))
            apply(i, b)
            v &= ~(1 << b)

    # `work` is the identity and gates_k o ... o gates_1 o perm = id, so
    # perm = gates_1 o ... o gates_k. Function composition applies the rightmost
    # first, and a circuit applies its first gate first, so the circuit is the
    # collected list reversed.
    gates.reverse()
    return gates


def permutation_circuit(perm: list[int], name: str = "perm") -> QuantumCircuit:
    """A circuit on ceil(log2(len(perm))) qubits sending |i> to |perm[i]>."""
    width = max(1, (len(perm) - 1).bit_length())
    qc = QuantumCircuit(width, name=name)
    _emit(qc, synth_permutation(perm), list(range(width)), control=None)
    return qc


def controlled_permutation_gate(perm: list[int], label: str):
    """The same permutation, applied only when one extra control qubit is 1.

    Returned as an instruction on width+1 qubits, control first, which is the
    order `QuantumCircuit.append` wants for a controlled operation.

    Adding the control to every gate's control set is the whole construction:
    each MCX already fires only on a matching pattern, so requiring one more bit
    leaves the identity behind when the control is 0. Doing it this way is what
    avoids `UnitaryGate(...).control(1)`, which is where the dense synthesis got
    in and where 8 bits stopped finishing.
    """
    width = max(1, (len(perm) - 1).bit_length())
    qc = QuantumCircuit(1 + width, name=label)
    _emit(qc, synth_permutation(perm), list(range(1, 1 + width)), control=0)
    return qc.to_gate(label=label)


def _emit(qc: QuantumCircuit, gates: list[Gate], qubits: list[int],
          control: int | None) -> None:
    for mask, target in gates:
        controls = [qubits[b] for b in _bits(mask)]
        if control is not None:
            controls.append(control)
        if controls:
            qc.mcx(controls, qubits[target])
        else:
            qc.x(qubits[target])
