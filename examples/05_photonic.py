"""Run a photonic program: Hong-Ou-Mandel interference on linear optics.

    pip install perceval-quandela
    python examples/05_photonic.py

Photonic hardware has no qubits and no gates. Photons enter chosen modes, interfere
through beamsplitters and phase shifters, and the answer is which modes they leave by.
A program is therefore two things, a circuit and the photons entering it, because
unlike a gate circuit it does not carry its own initial state.

The experiment here is the photonic counterpart of a Bell state. Two indistinguishable
photons meeting on a balanced beamsplitter must leave together: both take one output or
both take the other, and the coincidence term |1,0,1>, one photon each way, is exactly
zero. That zero is the whole measurement. The fraction of runs that bunch is a direct
fidelity number, needing no reference distribution to compare against.
"""
import os

import perceval as pcvl
from perceval.components import BS, PERM

import qsim_sdk

# Three modes. The permutation brings the photons in modes 0 and 2 together, then a
# balanced beamsplitter interferes them. Modes 0 and 2 rather than 0 and 1 because
# Belenos has single-photon sources on alternating modes, so a program written this way
# runs unchanged on hardware.
circuit = pcvl.Circuit(3) // (1, PERM([1, 0])) // (0, BS.H())

client = qsim_sdk.Client(token=os.environ["ZKSF_TOKEN"])

# The input state can be a plain occupation list: one photon into mode 0, none into
# mode 1, one into mode 2. A perceval.BasicState works too, as does either serialised.
job = client.run_photonic(circuit, [1, 0, 1], shots=1000)

counts = job["result"]["counts"]
print("counts    :", counts)
print("error_info:", job["result"]["error_info"])

coincidences = sum(v for k, v in counts.items() if k.count("1") == 2)
bunched = sum(counts.values()) - coincidences
print(f"bunched   : {bunched}/{sum(counts.values())}")
print(f"coincidences: {coincidences}  (exactly 0 in simulation)")

# On the exact simulator the coincidence term is identically zero, so error_info
# reports no approximation error and only shot noise applies.
assert coincidences == 0, counts

# The same program on real hardware:
#
#     job = client.run_photonic(circuit, [1, 0, 1], shots=1000,
#                               engine="qpu.quandela.belenos")
#
# Photons are lost, sources are imperfect, and the coincidence term stops being zero.
# Three runs on Belenos bunched 95.4%, 97.0% and 97.7% of the time. The device
# also returns its own declared single-photon purity, indistinguishability and
# transmittance with the result, so a run can state what the hardware claimed next to
# what it did. Belenos accepts photons only on its connected input modes, and a program
# that puts one elsewhere is refused before submission rather than after you have paid.
