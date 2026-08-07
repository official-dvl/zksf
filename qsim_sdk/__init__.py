"""qsim SDK: three lines to run a circuit:

    import qsim_sdk
    client = qsim_sdk.Client("http://localhost:8000")
    result = client.run(qiskit_circuit)

    result["result"]["counts"]        # outcomes
    result["result"]["error_info"]    # how much to trust them  <- the point
"""
from __future__ import annotations

import time
from typing import Any

import httpx
from qiskit import QuantumCircuit, qasm2


class JobRejected(RuntimeError):
    pass


class JobFailed(RuntimeError):
    pass


DEFAULT_BASE_URL = "https://api.zksf.org"


def _to_qasm2(circuit: Any) -> str:
    """Normalize any supported circuit to a QASM2 string.

    Qiskit circuits go straight through. Cirq, PennyLane, pyQuil and Braket
    circuits are converted to Qiskit first via the qBraid transpiler (an
    optional dependency: pip install qsim-sdk[multiframework]).
    """
    if isinstance(circuit, QuantumCircuit):
        return qasm2.dumps(circuit)
    try:
        import qbraid
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise TypeError(
            f"circuit type {type(circuit).__name__} needs the qBraid transpiler; "
            f"install it with: pip install qsim-sdk[multiframework], or pass a "
            f"qiskit QuantumCircuit"
        ) from exc
    qiskit_circuit = qbraid.transpile(circuit, "qiskit")
    return qasm2.dumps(qiskit_circuit)


class Client:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, token: str | None = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._http = httpx.Client(base_url=base_url, headers=headers, timeout=600.0)

    def estimate(
        self, circuit: Any, shots: int = 1024, engine: str | None = None
    ) -> dict[str, Any]:
        """Free pre-run check: engine, predicted runtime and cost, or why not.
        Accepts qiskit, Cirq, PennyLane, pyQuil or Braket circuits."""
        resp = self._http.post(
            "/estimate",
            json={"qasm2": _to_qasm2(circuit), "shots": shots, "engine": engine},
        )
        resp.raise_for_status()
        return resp.json()

    def submit(
        self,
        circuit: Any,
        shots: int = 1024,
        engine: str | None = None,
        observable: list | None = None,
        **params: Any,
    ) -> str:
        resp = self._http.post(
            "/jobs",
            json={
                "qasm2": _to_qasm2(circuit),
                "shots": shots,
                "engine": engine,
                "observable": observable,
                "params": params,
            },
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def job(self, job_id: str) -> dict[str, Any]:
        resp = self._http.get(f"/jobs/{job_id}")
        resp.raise_for_status()
        return resp.json()

    def run(
        self,
        circuit: Any,
        shots: int = 1024,
        engine: str | None = None,
        observable: list | None = None,
        poll_seconds: float = 0.2,
        timeout: float = 600.0,
        **params: Any,
    ) -> dict[str, Any]:
        """Submit and wait. Raises JobRejected/JobFailed with the reason.
        Accepts qiskit, Cirq, PennyLane, pyQuil or Braket circuits."""
        job_id = self.submit(
            circuit, shots=shots, engine=engine, observable=observable, **params
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.job(job_id)
            if job["status"] == "done":
                return job
            if job["status"] == "rejected":
                raise JobRejected(job["reason"])
            if job["status"] == "error":
                raise JobFailed(job["error"])
            time.sleep(poll_seconds)
        raise TimeoutError(f"job {job_id} still running after {timeout}s")
