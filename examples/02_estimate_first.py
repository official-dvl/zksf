"""Check price and feasibility before spending anything.

    python examples/02_estimate_first.py

estimate() is free and instant. It returns the engine that would be selected, the
predicted runtime, the predicted cost, and the reason for that selection. Calling it
before run() is the recommended pattern for any circuit whose cost is not already
known, and it is the only way to discover that a circuit would be rejected without
submitting it.
"""
import os

from qiskit import QuantumCircuit

import qsim_sdk

# A 40-qubit GHZ state: far past the exact statevector boundary, but highly
# structured, so a tensor-network method handles it comfortably.
n = 40
qc = QuantumCircuit(n)
qc.h(0)
for i in range(n - 1):
    qc.cx(i, i + 1)
qc.measure_all()

client = qsim_sdk.Client(token=os.environ["ZKSF_TOKEN"])

est = client.estimate(qc, shots=1000)
print("engine           :", est.get("engine"))
print("predicted seconds:", est.get("predicted_seconds"))
print("predicted cost   : $", est.get("predicted_cost_usd"))
print("reason           :", est.get("reason"))

budget_usd = 0.05
if (est.get("predicted_cost_usd") or 0) > budget_usd:
    raise SystemExit(f"Estimated cost exceeds the {budget_usd} USD budget, not running.")

job = client.run(qc, shots=1000)
print("counts           :", job["result"]["counts"])
