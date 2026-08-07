"""Request a measured ZCC-v0.1 error bound, then export a verifiable certificate.

    python examples/03_certified_bound.py

The MPS engine tracks discarded Schmidt weight during contraction and converts it into
a single-run bound on the output distribution, measured within the run rather than
extrapolated across runs. This is opt-in per job because it costs more than the
default convergence check.

See docs/CERTIFICATION.md for what the bound does and does not assert.
"""
import os

from qiskit import QuantumCircuit

import qsim_sdk

n = 12
qc = QuantumCircuit(n)
qc.h(0)
for i in range(n - 1):
    qc.cx(i, i + 1)
qc.measure_all()

client = qsim_sdk.Client(token=os.environ["ZKSF_TOKEN"])

job = client.run(qc, shots=1000, engine="mps.quimb.cpu", certified=True)

print("counts    :", job["result"]["counts"])
print("error_info:", job["result"]["error_info"])

# error_info carries the protocol tag, the mode, the discarded weight, and the bound.
# For a 12-qubit GHZ on this engine, published reference figures are a discarded
# weight of 2.22e-16 and an error bound of 2.11e-08.

# A certificate is minted from the completed job and is then readable by anyone,
# with no authentication, at https://api.zksf.org/certify/<cert_id>
print("\nJob id:", job.get("id"))
print("Mint a certificate from the console, or POST /jobs/<id>/certificate")
