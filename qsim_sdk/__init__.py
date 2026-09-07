"""qsim SDK: three lines to run a circuit:

    import qsim_sdk
    client = qsim_sdk.Client("http://localhost:8000")
    result = client.run(qiskit_circuit)

    result["result"]["counts"]        # outcomes
    result["result"]["error_info"]    # how much to trust them  <- the point

A parameter sweep goes in one request rather than one per point:

    job = client.run_sweep(parameterized_circuit, [{theta: v} for v in values])
    qsim_sdk.expectations(job)        # one per value, None where it failed

Neutral-atom analog work is a register and a pulse schedule rather than a
circuit, so it has its own entry point:

    job = client.run_sequence(pulser_sequence)

Photonic work is a linear-optics circuit and the photons entering it, which
is two things rather than one, so it takes both:

    job = client.run_photonic(perceval_circuit, [1, 0, 1])
"""
from __future__ import annotations

import json
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

#: The local exact analog engine. Analog jobs always name their engine: routing
#: inspects gate-circuit features, and a pulse schedule has none of them.
ANALOG_ENGINE = "analog.pulser.cpu"


def _to_pulser(sequence: Any) -> str:
    """Normalize a Pulser sequence to its abstract representation.

    Accepts a `pulser.Sequence` or an already-serialised JSON string, and reaches
    the object by duck typing rather than importing pulser. That keeps pulser out
    of this SDK's dependencies: someone who has it passes the object, someone who
    does not passes the JSON.
    """
    if isinstance(sequence, str):
        return sequence
    to_abstract_repr = getattr(sequence, "to_abstract_repr", None)
    if to_abstract_repr is None:
        raise TypeError(
            f"expected a pulser.Sequence or its abstract-repr JSON string, got "
            f"{type(sequence).__name__}. Build one with pulser, then pass either "
            f"the Sequence or sequence.to_abstract_repr()."
        )
    return to_abstract_repr()


#: The local exact photonic engine. Photonic jobs name their engine for the
#: same reason analog ones do: routing reads gate-circuit features, and a
#: linear-optics circuit has none of them.
PHOTONIC_ENGINE = "photonic.slos.cpu"


def _serialise_perceval(obj: Any, what: str) -> str:
    """Serialise a Perceval object, or pass through an already-serialised one.

    Perceval stays out of this SDK's dependencies, exactly as pulser does: a
    caller who has it passes objects, a caller who does not passes the strings
    perceval.serialization.serialize() produced elsewhere.
    """
    if isinstance(obj, str):
        return obj
    try:
        from perceval.serialization import serialize
    except ImportError as exc:
        raise TypeError(
            f"got {type(obj).__name__} for the {what}, and perceval is not "
            f"installed to serialise it. Either pip install perceval-quandela, "
            f"or pass the string perceval.serialization.serialize() returns."
        ) from exc
    return serialize(obj)


#: Perceval's serialisation tag for a Fock state, hardcoded so an occupation
#: list can be sent without perceval installed.
#:
#: It has to be exactly this. perceval's deserialize() returns any string it
#: does not recognise unchanged, so a bare "|1,0,1>" is not rejected at the
#: door: it arrives at the engine as a str and fails several frames deep with
#: "Could not find signature for with_input: <str>". Tagging it here is what
#: makes the difference between a Fock state and a lookalike string.
_FOCK_TAG = ":PCVL:BasicState:"


def _to_fock_state(state: Any) -> str:
    """Normalize an input Fock state to the form the service deserialises.

    Accepts a perceval.BasicState, its serialised string, a bare "|1,0,1>", or
    a plain occupation list: [1, 0, 1] is one photon into mode 0 and one into
    mode 2. The list form is the reason this is worth a helper, since it lets
    someone describe the input without perceval installed at all.
    """
    if isinstance(state, str):
        if state.startswith(":PCVL:"):
            return state
        if state.startswith("|") and state.endswith(">"):
            return _FOCK_TAG + state
        raise TypeError(
            f"expected a Fock state like '|1,0,1>', an occupation list like "
            f"[1, 0, 1], or the string perceval.serialization.serialize() "
            f"returns; got {state!r}"
        )
    # Before the Sequence branch: a Fock state is indexable, so it would
    # otherwise be treated as an occupation list. Let the object serialise
    # itself rather than reconstructing its text here.
    if hasattr(state, "n") and hasattr(state, "m"):
        return _serialise_perceval(state, "input state")
    if isinstance(state, Sequence):
        if not state or not all(isinstance(n, int) and n >= 0 for n in state):
            raise TypeError(
                f"an occupation list must be non-empty and all non-negative "
                f"ints, one per mode, e.g. [1, 0, 1]; got {state!r}"
            )
        return _FOCK_TAG + "|" + ",".join(str(n) for n in state) + ">"
    return _serialise_perceval(state, "input state")


def _to_photonic(circuit: Any, input_state: Any) -> str:
    """Normalize a Perceval circuit and its input state into one program.

    A photonic program is two things, not one. A gate circuit carries its
    initial state implicitly and a Pulser sequence carries its register, but a
    linear-optics circuit says nothing about how many photons enter or where,
    so the input is part of the program rather than a setting on the run. Both
    halves go into the JSON the service hashes, which is why two runs that
    differ only in where the photons entered cannot share a certificate.
    """
    return json.dumps(
        {
            "circuit": _serialise_perceval(circuit, "circuit"),
            "input": _to_fock_state(input_state),
        }
    )


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

    # --------------------------------------------------------------- waiting

    def _wait(self, job_id: str, poll_seconds: float, timeout: float) -> dict[str, Any]:
        """Poll until the job reaches a terminal state, or raise saying why."""
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
        return self._wait(job_id, poll_seconds, timeout)

    # ------------------------------------------------- analog (neutral atom)

    def submit_sequence(
        self,
        sequence: Any,
        shots: int = 1024,
        engine: str = ANALOG_ENGINE,
        **params: Any,
    ) -> str:
        """Submit a Pulser sequence to an analog neutral-atom engine.

        Analog work is not a circuit: it is a register of atoms and a pulse
        schedule, so it takes its own submission path and names its engine
        rather than being routed by circuit features.
        """
        resp = self._http.post(
            "/jobs",
            json={
                "pulser": _to_pulser(sequence),
                "shots": shots,
                "engine": engine,
                "params": params,
            },
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def run_sequence(
        self,
        sequence: Any,
        shots: int = 1024,
        engine: str = ANALOG_ENGINE,
        poll_seconds: float = 0.2,
        timeout: float = 600.0,
        **params: Any,
    ) -> dict[str, Any]:
        """Submit a Pulser sequence and wait for the result."""
        job_id = self.submit_sequence(sequence, shots=shots, engine=engine, **params)
        return self._wait(job_id, poll_seconds, timeout)

    # ------------------------------------------------------------- photonic

    def submit_photonic(
        self,
        circuit: Any,
        input_state: Any,
        shots: int = 1024,
        engine: str = PHOTONIC_ENGINE,
        **params: Any,
    ) -> str:
        """Submit a linear-optics circuit and its input photons.

        `circuit` is a perceval.Circuit (or its serialised string) and
        `input_state` is where the photons enter: a perceval.BasicState, its
        serialised string, or an occupation list such as [1, 0, 1].

        Both are required and both are hashed, because a linear-optics circuit
        does not carry its own initial state. Like analog work this names its
        engine rather than being routed, since routing reads gate-circuit
        features that a photonic program does not have. Pass
        engine="qpu.quandela.belenos" to run on real hardware, which accepts
        photons only on its connected input modes.
        """
        resp = self._http.post(
            "/jobs",
            json={
                "photonic": _to_photonic(circuit, input_state),
                "shots": shots,
                "engine": engine,
                "params": params,
            },
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def run_photonic(
        self,
        circuit: Any,
        input_state: Any,
        shots: int = 1024,
        engine: str = PHOTONIC_ENGINE,
        poll_seconds: float = 0.2,
        timeout: float = 600.0,
        **params: Any,
    ) -> dict[str, Any]:
        """Submit a photonic program and wait for the result."""
        job_id = self.submit_photonic(
            circuit, input_state, shots=shots, engine=engine, **params
        )
        return self._wait(job_id, poll_seconds, timeout)


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
