"""Submit to a real quantum processor and read the measured fidelity.

    python examples/04_real_hardware.py

Hardware jobs are billed at provider cost and may sit in a device queue for minutes to
hours, so this example uses the non-blocking submit/poll flow rather than run().

The returned counts are real measurements from a physical device. They will not match
the ideal distribution, and the ZHF-v0.1 fidelity states by how much.
"""
import os
import time

from qiskit import QuantumCircuit

import qsim_sdk

qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)
qc.measure_all()

client = qsim_sdk.Client(token=os.environ["ZKSF_TOKEN"])

# Confirm the price before committing to a hardware run.
est = client.estimate(qc, shots=100, engine="qpu.ionq")
print("predicted cost: $", est.get("predicted_cost_usd"))

job_id = client.submit(qc, shots=100, engine="qpu.ionq")
print("submitted:", job_id)

while True:
    job = client.job(job_id)
    status = job["status"]
    print("status:", status)
    if status in ("done", "rejected", "error"):
        break
    time.sleep(30)

if job["status"] == "done":
    print("counts    :", job["result"]["counts"])
    print("error_info:", job["result"]["error_info"])
    # For a 2-qubit Bell state on IonQ Forte-1, a published reference run gave
    # counts {"00": 54, "11": 44, "01": 2} at 0.9774 Hellinger fidelity.
    # The "01" outcomes are device noise: an ideal Bell state cannot produce them.
else:
    print("terminal status:", job["status"], job.get("reason") or job.get("error"))
