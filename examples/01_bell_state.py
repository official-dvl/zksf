"""Minimal run: a two-qubit Bell state on the default routed engine.

    export ZKSF_TOKEN=...        # or set ZKSF_TOKEN=... on Windows
    python examples/01_bell_state.py

The router selects the cheapest adequate engine. For a Clifford circuit such as this
one, that is the stabilizer engine, and the cost is a fraction of a cent.
"""
import os

from qiskit import QuantumCircuit

import qsim_sdk

qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)
qc.measure_all()

client = qsim_sdk.Client(token=os.environ["ZKSF_TOKEN"])
job = client.run(qc, shots=1000)

print("engine    :", job["result"].get("engine"))
print("counts    :", job["result"]["counts"])
print("error_info:", job["result"]["error_info"])
