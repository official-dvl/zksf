"""qsim SDK: three lines to run a circuit:

    import qsim_sdk
    client = qsim_sdk.Client("http://localhost:8000")
    result = client.run(qiskit_circuit)

    result["result"]["counts"]        # outcomes
    result["result"]["error_info"]    # how much to trust them  <- the point

A parameter sweep goes in one request rather than one per point:

    job = client.run_sweep(parameterized_circuit, [{theta: v} for v in values])
    qsim_sdk.expectations(job)        # one per value, None where it failed
"""
from __future__ import annotations

import time
from collections.abc import Sequence
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

    # ------------------------------------------------------------- batches

    def submit_batch(
        self,
        circuits: Sequence[Any],
        shots: int = 1024,
        engine: str | None = None,
        observable: list | None = None,
        **params: Any,
    ) -> str:
        """Submit many circuits as one job. Every circuit shares the engine,
        shots, params and observable: a sweep varies the circuit, not the way
        it is run."""
        resp = self._http.post(
            "/jobs/batch",
            json={
                "circuits": [_to_qasm2(c) for c in circuits],
                "shots": shots,
                "engine": engine,
                "observable": observable,
                "params": params,
            },
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def run_batch(
        self,
        circuits: Sequence[Any],
        shots: int = 1024,
        engine: str | None = None,
        observable: list | None = None,
        poll_seconds: float = 0.2,
        timeout: float = 600.0,
        **params: Any,
    ) -> dict[str, Any]:
        """Submit many circuits and wait for all of them.

        Unlike `run`, this does not raise when a circuit fails. A sweep's cost
        depends on the entanglement each parameter value produces, so some
        bindings can exhaust memory while the rest are fine, and an optimizer
        wants those reported as bad points rather than as an exception. Read
        `job["summary"]` for the tally and `job["results"][i]["status"]` for
        each one. Only the evaluations that returned a result are charged.
        """
        job_id = self.submit_batch(
            circuits, shots=shots, engine=engine, observable=observable, **params
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.job(job_id)
            if job["status"] == "done":
                return job
            if job["status"] == "rejected":
                raise JobRejected(job.get("reason"))
            if job["status"] == "error":
                raise JobFailed(job.get("error"))
            time.sleep(poll_seconds)
        raise TimeoutError(f"batch {job_id} still running after {timeout}s")

    def run_sweep(
        self,
        circuit: QuantumCircuit,
        bindings: Sequence[Any],
        shots: int = 1024,
        engine: str | None = None,
        observable: list | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run one parameterized circuit at many parameter values.

            theta = Parameter("theta")
            qc = QuantumCircuit(2); qc.h(0); qc.rz(theta, 0); qc.measure_all()
            job = client.run_sweep(qc, [{theta: v} for v in values])

        Each binding is anything `QuantumCircuit.assign_parameters` accepts: a
        mapping of Parameter to value, or a sequence in `circuit.parameters`
        order. Binding happens here because OpenQASM 2 cannot carry an unbound
        parameter, so the wire always sees bound circuits.

        Qiskit only. For another framework, bind with its own API and pass the
        bound circuits to `run_batch`.
        """
        if not isinstance(circuit, QuantumCircuit):
            raise TypeError(
                f"run_sweep needs a qiskit QuantumCircuit to bind parameters, got "
                f"{type(circuit).__name__}. Bind with your framework's own API and "
                f"pass the bound circuits to run_batch instead."
            )
        if not circuit.parameters:
            raise ValueError(
                "circuit has no free parameters to sweep; use run_batch if you "
                "meant to send several different circuits"
            )
        bound = [circuit.assign_parameters(b) for b in bindings]
        return self.run_batch(
            bound, shots=shots, engine=engine, observable=observable, **kwargs
        )


def expectations(job: dict[str, Any]) -> list[float | None]:
    """The expectation values of a finished batch, in submission order, with
    None where an evaluation returned no result.

    None rather than a skipped entry so the list still lines up with the
    parameter values you sent, which is what an optimizer needs to map a
    failure back to the point that caused it."""
    return [
        (item.get("result") or {}).get("expectation") if item["status"] == "done" else None
        for item in (job.get("results") or [])
    ]


def counts(job: dict[str, Any]) -> list[dict[str, int] | None]:
    """The counts of a finished batch, in submission order, None where an
    evaluation returned no result."""
    return [
        (item.get("result") or {}).get("counts") if item["status"] == "done" else None
        for item in (job.get("results") or [])
    ]

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
