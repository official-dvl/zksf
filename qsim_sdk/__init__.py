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

The account itself is reachable from code too, so a script never has to open
the console:

    client.pending()                  # every job that has not finished
    client.cancel(job_id)             # a hardware job still in its queue
    client.summary()["spend_usd"]     # net spend this month

The credential is an API key from the console (Profile, Create API key), valid
for 30 days. Pass it as `token=`, or set ZKSF_TOKEN and pass nothing.
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Iterator, Sequence
from datetime import datetime, timezone
from typing import Any

import httpx
from qiskit import QuantumCircuit, qasm2


class JobRejected(RuntimeError):
    pass


class JobFailed(RuntimeError):
    pass


class CancelRefused(RuntimeError):
    """A cancel the service declined, carrying its reason: the job has already
    started on the device, has finished, or runs where cancelling is not offered."""


def _detail(resp: Any) -> str:
    """The service's own explanation from an error response."""
    try:
        detail = resp.json().get("detail")
    except ValueError:
        detail = None
    return str(detail) if detail else resp.text


def _job_id(resp: Any) -> str:
    """The id from a submission, or the rejection it turned out to be.

    A submission-time rejection is not an HTTP error. It is a 200 carrying
    ``{"id": ..., "status": "rejected", "reason": "33 qubits needs 128 GiB ..."}``.
    Returning only the id threw that reason away, and the caller then polled an
    id the service declines to serve, so a perfectly clear refusal reached the
    user as a bare ``HTTPStatusError: 404 Not Found``.

    Every submit_* method routes its response through here, so all seven paths
    behave the same way and a new one cannot quietly opt out.
    """
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") == "rejected":
        # `reason` is the service's own explanation and is always set on this
        # path; the fallback exists so a future status shape cannot turn a
        # rejection into a confusing KeyError.
        raise JobRejected(body.get("reason") or "job rejected")
    return body["id"]


DEFAULT_BASE_URL = "https://api.zksf.org"

#: How long a job may sit before the SDK says so on stderr. The first job sent
#: to an engine after a quiet period takes noticeably longer to start, and a
#: notebook cell that has printed nothing for this long reads as a broken
#: service. Once per wait, never per poll.
SLOW_JOB_SECONDS = float(os.environ.get("ZKSF_SLOW_JOB_SECONDS", "15"))

#: Points the service accepts in one batch. Used here to chunk a long sweep
#: when PRICING it: a submission is capped because one job holds its points,
#: and a quote has no such limit, so asking about 12,000 circuits should return
#: a total rather than a refusal.
MAX_BATCH_CIRCUITS = 200

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
        try:
            return qasm2.dumps(circuit)
        except Exception:
            # A dynamic circuit (if/while on measured bits) has no OpenQASM 2.0
            # form. The service takes OpenQASM 3 in the same field and runs it
            # on the Aer engines (exact.cpu, noisy.cpu, mps.aer.cpu).
            from qiskit import qasm3

            return qasm3.dumps(circuit)
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


def _solve_body(
    hamiltonian: Sequence[Sequence[Any]],
    qubits: int,
    ansatz: str,
    reps: int,
    max_iterations: int,
    shots: int,
    engine: str | None,
    seed: int | None,
    params: dict[str, Any],
) -> dict[str, Any]:
    """One request body for a ground-state search, shared by submitting and pricing it."""
    return {
        "hamiltonian": [list(t) for t in hamiltonian],
        "qubits": qubits,
        "ansatz": ansatz,
        "reps": reps,
        "max_iterations": max_iterations,
        "shots": shots,
        "engine": engine,
        "seed": seed,
        "params": params,
    }


class Client:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: str | None = None,
        on_poll: Any = None,
    ):
        """`token` is an API key from the console (Profile, Create API key). Left
        out, it is read from the ZKSF_TOKEN environment variable, which keeps the
        key out of source files.

        `on_poll(job_id, status, elapsed_seconds)` is called on every poll while
        a job is waiting, for callers building a progress bar.
        """
        token = token or os.environ.get("ZKSF_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._http = httpx.Client(base_url=base_url, headers=headers, timeout=600.0)
        self.on_poll = on_poll

    def _polling(self, job_id: str, status: str, elapsed: float, warned: bool) -> bool:
        """Report that a job is still waiting. Returns whether it has warned yet.

        Two audiences, and the callback alone does not serve both. `on_poll`
        helps a caller who already suspects there is something to wire up. The
        person who actually needs this is the newcomer watching a notebook cell
        that has not printed anything for half a minute, and deciding the
        service is broken. The first job sent to an engine after a quiet period
        takes noticeably longer to start, so that silence is expected and
        completely invisible.

        Once per wait, not per poll, and on stderr so it never contaminates
        piped stdout.
        """
        if self.on_poll is not None:
            try:
                self.on_poll(job_id, status, elapsed)
            except Exception:  # noqa: BLE001 - a progress bar must not kill a job
                pass
        if not warned and elapsed >= SLOW_JOB_SECONDS:
            print(
                f"[qsim-sdk] job {job_id} is still {status} after {elapsed:.0f}s. "
                f"The first job sent to an engine after a quiet period takes "
                f"longer to start; later jobs are faster.",
                file=sys.stderr,
                flush=True,
            )
            return True
        return warned

    def estimate(
        self, circuit: Any, shots: int = 1024, engine: str | None = None
    ) -> dict[str, Any]:
        """Free pre-run check: engine, predicted runtime and cost, or why not.
        Accepts Qiskit, Cirq, PennyLane, pyQuil or Braket circuits."""
        resp = self._http.post(
            "/estimate",
            json={"qasm2": _to_qasm2(circuit), "shots": shots, "engine": engine},
        )
        resp.raise_for_status()
        return resp.json()

    def estimate_batch(
        self,
        circuits: Sequence[Any] | None = None,
        shots: int = 1024,
        engine: str | None = None,
        *,
        program: str | None = None,
        bindings: Sequence[dict] | None = None,
        program_kind: str = "qasm2",
    ) -> dict[str, Any]:
        """Free pre-run check for a whole sweep, not one circuit.

            est = client.estimate_batch(circuits, engine="exact.cpu")
            est["total_usd"]        # what the account will be debited
            est["per_point_usd"]    # and where it goes

        `estimate` prices ONE circuit, and the minimum is charged per circuit,
        so a 600-point sweep is 600 floors. Multiplying it yourself is the step
        that is easy to miss and expensive to miss: use this instead whenever
        you are about to call `run_batch` or `run_sweep`.

        Takes the same two shapes `run_batch` does: a list of circuits, or one
        parameterised `program` plus `bindings`.

        Sweeps longer than the service's per-batch limit are chunked and summed
        here. A submission is capped because one job holds its points; a QUOTE
        has no such constraint, and the sweep worth pricing is exactly the long
        one. Asking about 12,000 circuits and getting a refusal would send the
        caller back to multiplying by hand, which is the mistake this method
        exists to remove.
        """
        points: list = ([] if program is not None
                        else [_to_qasm2(c) for c in (circuits or [])])
        binds: list = list(bindings or []) if program is not None else []
        n = len(binds) if program is not None else len(points)
        if n == 0:
            raise ValueError("estimate_batch needs circuits, or a program and bindings")

        total, per_point, engine_seen = 0.0, [], None
        for start in range(0, n, MAX_BATCH_CIRCUITS):
            body: dict[str, Any] = {"shots": shots, "engine": engine,
                                    "program_kind": program_kind}
            if program is not None:
                body["program"] = program
                body["bindings"] = binds[start:start + MAX_BATCH_CIRCUITS]
            else:
                body["circuits"] = points[start:start + MAX_BATCH_CIRCUITS]
            resp = self._http.post("/estimate/batch", json=body)
            resp.raise_for_status()
            chunk = resp.json()
            total += chunk["total_usd"]
            per_point.extend(chunk["per_point_usd"])
            engine_seen = chunk["engine"]

        chunks = (n + MAX_BATCH_CIRCUITS - 1) // MAX_BATCH_CIRCUITS
        return {
            "engine": engine_seen,
            "points": n,
            "total_usd": round(total, 6),
            "per_point_usd": per_point,
            "shots": shots,
            # A submission of this sweep is this many jobs, which is worth
            # knowing before you write the loop that sends them.
            "batches": chunks,
            "reason": f"{n} points"
                      + (f" on '{engine_seen}'" if engine_seen else "")
                      + (f", priced in {chunks} requests" if chunks > 1 else ""),
        }

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
        return _job_id(resp)

    def job(self, job_id: str) -> dict[str, Any]:
        resp = self._http.get(f"/jobs/{job_id}")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------ jobs and account

    def pending(self) -> dict[str, Any]:
        """Every job on the account that has not finished, across its whole
        history: ``{"count": N, "jobs": [...]}``."""
        resp = self._http.get("/jobs/pending")
        resp.raise_for_status()
        return resp.json()

    def jobs(self, limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        """One page of the account's jobs, newest first:
        ``{"jobs": [...], "next_cursor": ...}``. Pass `next_cursor` back as
        `cursor` for the page before; it is None once the history is exhausted.
        `iter_jobs` does the walking for you."""
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        resp = self._http.get("/jobs", params=params)
        resp.raise_for_status()
        return resp.json()

    def iter_jobs(self, page_size: int = 50) -> Iterator[dict[str, Any]]:
        """Every job on the account, newest first, fetched a page at a time."""
        cursor: str | None = None
        while True:
            page = self.jobs(limit=page_size, cursor=cursor)
            yield from page.get("jobs") or []
            cursor = page.get("next_cursor")
            if not cursor:
                return

    def cancel(self, job_id: str) -> dict[str, Any]:
        """Ask the provider to cancel a hardware job still waiting in its queue.

        Returns the job with `cancel_requested_at` set. The charge is refunded
        once the provider confirms the job never ran; a job that starts before
        the cancel reaches the device finishes and is charged as normal, and the
        job says so. Raises CancelRefused with the reason when the job cannot be
        cancelled.
        """
        resp = self._http.post(f"/jobs/{job_id}/cancel")
        if resp.status_code == 409:
            raise CancelRefused(_detail(resp))
        resp.raise_for_status()
        return resp.json()

    def summary(self, since: float | None = None) -> dict[str, Any]:
        """Jobs run per tier over the account's whole history, and net spend
        since `since`.

        `since` is epoch seconds and defaults to the start of the current month
        in UTC. The console sends the start of the viewer's local month, which a
        script cannot know, so pass it when your month is not UTC's.
        """
        if since is None:
            now = datetime.now(timezone.utc)
            since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
        resp = self._http.get("/jobs/summary", params={"since": int(since)})
        resp.raise_for_status()
        return resp.json()

    def balance(self) -> float | None:
        """Available credit in USD, or None where billing is not enabled."""
        resp = self._http.get("/billing/balance")
        resp.raise_for_status()
        return resp.json().get("balance_usd")

    def certificate(self, job_id: str, index: int | None = None) -> dict[str, Any]:
        """Issue the public certificate for a finished job.

        Returns `cert_id`, `protocol`, `verify_url` and `download_url` (the PDF).
        Both URLs resolve without an account. For a batch, `index` names the
        evaluation to certify, since the points of a sweep do not share a bound.
        """
        params = {"index": index} if index is not None else None
        resp = self._http.post(f"/jobs/{job_id}/certificate", params=params)
        resp.raise_for_status()
        body = resp.json()
        download = body.get("download_url")
        if isinstance(download, str) and download.startswith("/"):
            body["download_url"] = str(self._http.base_url).rstrip("/") + download
        return body

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
        return _job_id(resp)

    # ------------------------------------------------------------- problems

    def submit_solve(
        self,
        hamiltonian: Sequence[Sequence[Any]],
        qubits: int,
        *,
        ansatz: str = "real_amplitudes",
        reps: int = 2,
        max_iterations: int = 60,
        shots: int = 1024,
        engine: str | None = None,
        seed: int | None = None,
        **params: Any,
    ) -> str:
        """Find a ground-state estimate for a Hamiltonian; returns a job id.

        A problem rather than a program: the ansatz is named instead of sent,
        because OpenQASM 2 cannot express an unbound parameter, and the service
        runs the variational loop. Every term must name every qubit, padding
        with I.

        The optimiser is SPSA, which costs two circuit evaluations per
        iteration whatever the parameter count, plus one final run at the best
        point: `max_iterations=60` is 121 charged evaluations.
        """
        resp = self._http.post(
            "/solve",
            json=_solve_body(hamiltonian, qubits, ansatz, reps, max_iterations, shots, engine, seed, params),
        )
        return _job_id(resp)

    def estimate_solve(
        self,
        hamiltonian: Sequence[Sequence[Any]],
        qubits: int,
        *,
        ansatz: str = "real_amplitudes",
        reps: int = 2,
        max_iterations: int = 60,
        shots: int = 1024,
        engine: str | None = None,
        seed: int | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """What a ground-state search would cost, before submitting it.

        Same arguments as `submit_solve`, and free. `estimate` prices a single
        circuit, whereas a search is many evaluations chosen by the optimiser
        and, on the neural engines, metered runtime, so it is priced here.
        """
        resp = self._http.post(
            "/solve/estimate",
            json=_solve_body(hamiltonian, qubits, ansatz, reps, max_iterations, shots, engine, seed, params),
        )
        resp.raise_for_status()
        return resp.json()

    def solve(
        self,
        hamiltonian: Sequence[Sequence[Any]],
        qubits: int,
        *,
        poll_seconds: float = 0.5,
        timeout: float = 1800.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submit a ground-state problem and wait for the answer.

        Read `result["ground_state"]["ceiling"]` rather than `result["energy"]`:
        the variational principle puts the true ground state at or below the
        energy found, and the ceiling adds the simulation's own error bound to
        give a number the true answer cannot exceed. A run reports no ceiling
        when the engine reported no bound, rather than assuming one.
        """
        job_id = self.submit_solve(hamiltonian, qubits, **kwargs)
        return self._wait(job_id, poll_seconds, timeout)

    def _qec_body(
        self,
        code: str,
        distance: int,
        rounds: int | None,
        shots: int,
        physical_error: float,
        measurement_error: float | None,
        seed: int | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "code": code,
            "distance": distance,
            "shots": shots,
            "physical_error": physical_error,
        }
        if rounds is not None:
            body["rounds"] = rounds
        if measurement_error is not None:
            body["measurement_error"] = measurement_error
        if seed is not None:
            body["seed"] = seed
        return body

    def estimate_qec(
        self,
        code: str = "surface",
        distance: int = 3,
        *,
        rounds: int | None = None,
        shots: int = 10_000,
        physical_error: float = 1e-3,
        measurement_error: float | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """What a memory experiment would cost, before submitting it. Free.

        Worth calling: the same endpoint spans a run that finishes in under a
        second and one that holds a worker for a quarter of an hour, and the
        difference is distance times rounds times shots rather than any one
        of them.
        """
        resp = self._http.post(
            "/qec/estimate",
            json=self._qec_body(code, distance, rounds, shots, physical_error,
                                measurement_error, seed),
        )
        resp.raise_for_status()
        return resp.json()

    def submit_qec(
        self,
        code: str = "surface",
        distance: int = 3,
        *,
        rounds: int | None = None,
        shots: int = 10_000,
        physical_error: float = 1e-3,
        measurement_error: float | None = None,
        seed: int | None = None,
    ) -> str:
        """Hold a logical qubit in a code and measure how often it fails.

        `rounds` defaults to `distance`, which is the convention these numbers
        are published at: fewer rounds flatters the code, because time-like
        errors have had less opportunity to accumulate.
        """
        resp = self._http.post(
            "/qec",
            json=self._qec_body(code, distance, rounds, shots, physical_error,
                                measurement_error, seed),
        )
        # Through _job_id like every other submit_*, so a submission-time
        # refusal arrives as its reason rather than as a 404 on the next poll.
        return _job_id(resp)

    def qec(
        self,
        code: str = "surface",
        distance: int = 3,
        *,
        poll_seconds: float = 0.5,
        timeout: float = 1800.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run a memory experiment and wait for the logical error rate.

            job = client.qec("surface", distance=5, shots=100_000)
            lo, hi = job["result"]["confidence_interval_95"]

        READ THE INTERVAL, NOT THE RATE. `logical_error_rate` is a proportion
        from a finite number of shots. At a hundred thousand shots with no
        failures it is 0.0, and the honest statement is not that the code never
        fails, it is that its failure rate is below `hi`. That is the number to
        quote and the number the certificate carries.
        """
        job_id = self.submit_qec(code, distance, **kwargs)
        return self._wait(job_id, poll_seconds, timeout)

    def _scaling_body(
        self,
        code: str,
        distances: Sequence[int],
        shots: int,
        physical_error: float,
        target: float | None,
        seed: int | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "code": code,
            "distances": list(distances),
            "shots": shots,
            "physical_error": physical_error,
        }
        if target is not None:
            body["target_logical_error_rate"] = target
        if seed is not None:
            body["seed"] = seed
        return body

    def estimate_qec_scaling(
        self,
        code: str = "surface",
        distances: Sequence[int] = (3, 5, 7),
        *,
        shots: int = 50_000,
        physical_error: float = 1e-3,
        target_logical_error_rate: float | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """What measuring the suppression factor would cost. Free."""
        resp = self._http.post(
            "/qec/scaling/estimate",
            json=self._scaling_body(
                code, distances, shots, physical_error, target_logical_error_rate, seed
            ),
        )
        resp.raise_for_status()
        return resp.json()

    def submit_qec_scaling(
        self,
        code: str = "surface",
        distances: Sequence[int] = (3, 5, 7),
        *,
        shots: int = 50_000,
        physical_error: float = 1e-3,
        target_logical_error_rate: float | None = None,
        seed: int | None = None,
    ) -> str:
        """Measure whether distance helps at this error rate, and what it costs."""
        resp = self._http.post(
            "/qec/scaling",
            json=self._scaling_body(
                code, distances, shots, physical_error, target_logical_error_rate, seed
            ),
        )
        return _job_id(resp)

    def qec_scaling(
        self,
        code: str = "surface",
        distances: Sequence[int] = (3, 5, 7),
        *,
        poll_seconds: float = 0.5,
        timeout: float = 3600.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Measure the suppression factor, and optionally the qubit count.

            job = client.qec_scaling(target_logical_error_rate=1e-9,
                                     physical_error=1e-3)
            res = job["result"]
            res["suppression"]["lambda"]   # 2.1, measured on three runs
            res["physical_qubits"]         # what one logical qubit costs
            res["basis"]                   # measured, or extrapolated from what

        THE TWO QUESTIONS A BUYER ACTUALLY HAS, out of one set of runs. Does
        distance help on my device, and how many physical qubits is a logical
        one at my error rate. Read `basis`: the suppression factor is measured,
        the distance that follows from it is arithmetic, and a target below
        anything these runs could observe is reached by extrapolation. At or
        above threshold the answer is that there is no such number, which is a
        result rather than a failure.
        """
        job_id = self.submit_qec_scaling(code, distances, **kwargs)
        return self._wait(job_id, poll_seconds, timeout)

    def _tomography_body(
        self,
        n_spins: int,
        bases: Sequence[str],
        outcomes: Sequence[Sequence[int]],
        engine: str | None,
        max_seconds: float | None,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "n_spins": int(n_spins),
            "bases": [str(b).upper() for b in bases],
            "outcomes": [[int(v) for v in shot] for shot in outcomes],
            "engine": engine,
            "max_seconds": max_seconds,
            "params": params,
        }

    def estimate_tomography(
        self,
        n_spins: int,
        bases: Sequence[str],
        outcomes: Sequence[Sequence[int]],
        *,
        engine: str | None = None,
        max_seconds: float | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """What a reconstruction would cost, before submitting it. Free.

        Takes exactly what `submit_tomography` takes and prices it the way the
        service will charge it, so the quote and the charge cannot drift apart:
        metered on runtime, with the per-job floor.

            est = client.estimate_tomography(2, bases, outcomes)
            est["predicted_cost_usd"], est["predicted_seconds"]
        """
        resp = self._http.post(
            "/tomography/estimate",
            json=self._tomography_body(n_spins, bases, outcomes, engine,
                                       max_seconds, params),
        )
        resp.raise_for_status()
        return resp.json()

    def submit_tomography(
        self,
        n_spins: int,
        bases: Sequence[str],
        outcomes: Sequence[Sequence[int]],
        *,
        engine: str | None = None,
        max_seconds: float | None = None,
        **params: Any,
    ) -> str:
        """Reconstruct the state a device prepared, from its shots.

            job = client.run_tomography(2, bases, outcomes)
            job["result"]["agreement"]["agreed"]      # of how many checked

        `bases[i]` is the basis shot i was measured in, one character per qubit
        over X, Y and Z; `outcomes[i]` is what came back, as +1 and -1 rather
        than 0 and 1.

        READ THIS BEFORE USING THE ANSWER. A maximum-likelihood fit has no
        equivalent of the variational principle, so **nothing here bounds the
        distance between the reconstruction and the state your device actually
        prepared**, and `result["certifiable"]` is always False. What IS bounded
        is agreement with records the fit never saw: the reconstruction
        reproduces the measured expectations to within a stated interval at a
        stated confidence.

        The submission is REFUSED when the bases cannot determine a state, and
        that refusal is the most useful thing here. An under-determined fit
        converges perfectly well onto the wrong state and nothing downstream can
        tell: measured on a Bell state, five bases gave fidelity 0.51 and all
        nine gave 0.98 at identical settings.
        """
        resp = self._http.post(
            "/tomography",
            json=self._tomography_body(n_spins, bases, outcomes, engine,
                                       max_seconds, params),
        )
        return _job_id(resp)

    def run_tomography(
        self,
        n_spins: int,
        bases: Sequence[str],
        outcomes: Sequence[Sequence[int]],
        *,
        poll_seconds: float = 0.5,
        timeout: float = 3600.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submit measurement records and wait for the reconstruction."""
        job_id = self.submit_tomography(n_spins, bases, outcomes, **kwargs)
        return self._wait(job_id, poll_seconds, timeout)

    def submit_solve_batch(
        self,
        problems: Sequence[dict[str, Any]],
        *,
        engine: str | None = None,
        max_seconds: float | None = None,
        **params: Any,
    ) -> str:
        """Many ground states on ONE machine; returns a job id.

            problems = [{"qubits": 8, "hamiltonian": h(j)} for j in couplings]
            job = client.run_solve_batch(problems, engine="neural.tpu")

        WHY THIS IS NOT A LOOP OVER `solve`. On a TPU roughly 522 seconds of
        every job is the machine being created and deleted, against about 113
        seconds of work. A phase diagram sent one Hamiltonian at a time spends
        four fifths of its money on provisioning; sent here that is paid once.
        `neural.cpu` accepts the same call and returns the same shape, because
        there is nothing to provision and therefore nothing to save, so the
        engine is a choice rather than a rewrite.

        Each point is independent. One that fails is reported in place with its
        reason and the others still return, and a point that never starts
        before the machine's wall-clock ceiling comes back as `skipped`.
        Anything that produced no result is refunded.

        `params` applies to every point and a point's own value wins, so a
        sweep over the ansatz width is one submission:

            problems = [{"qubits": 8, "hamiltonian": h, "alpha": a}
                        for a in (1, 2, 4, 8)]

        Price it first with `estimate_solve_batch`. The total is not one
        point's price times the number of points: provisioning does not
        multiply, and the per-circuit minimum does.
        """
        resp = self._http.post(
            "/solve/batch",
            json={
                "problems": [dict(p) for p in problems],
                "engine": engine,
                "max_seconds": max_seconds,
                "params": params,
            },
        )
        return _job_id(resp)

    def estimate_solve_batch(
        self,
        problems: Sequence[dict[str, Any]],
        *,
        engine: str | None = None,
        max_seconds: float | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """What a batch of ground-state searches would cost. Free.

            est = client.estimate_solve_batch(problems, engine="neural.tpu")
            est["total_usd"]           # what the account is debited at submit
            est["per_point_usd"]       # and where it goes
            est["predicted_seconds"]   # how long the machine is held

        Worth calling rather than multiplying: provisioning is charged once for
        the whole batch while the per-circuit minimum is charged per point, so
        the total is neither one job's price nor N of them.
        """
        resp = self._http.post(
            "/solve/batch/estimate",
            json={
                "problems": [dict(p) for p in problems],
                "engine": engine,
                "max_seconds": max_seconds,
                "params": params,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def run_solve_batch(
        self,
        problems: Sequence[dict[str, Any]],
        *,
        poll_seconds: float = 0.5,
        timeout: float = 3600.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submit many ground-state problems and wait for all of them.

        `job["result"]["results"]` comes back in submission order, so point i
        is the answer to `problems[i]`. Check each one's `status` before its
        `energy`: a failed point is reported rather than raised, the same way
        a circuit batch reports one, because an optimiser or a sweep wants a
        bad point marked rather than the whole run lost.

        The default timeout is an hour rather than the half hour `solve` uses,
        because a batch is many searches on one machine.
        """
        job_id = self.submit_solve_batch(problems, **kwargs)
        return self._wait(job_id, poll_seconds, timeout)

    def submit_mis(
        self,
        vertices: Sequence[Sequence[float]],
        *,
        weights: Sequence[float] | None = None,
        shots: int = 100,
        engine: str | None = None,
        blockade_um: float = 7.5,
        duration_ns: int = 4_000,
    ) -> str:
        """Maximum independent set on a neutral-atom register; returns a job id.

        Positions in micrometres, not a graph: on this hardware an edge exists
        exactly where two atoms fall inside the blockade radius, so the geometry
        is the problem. An arbitrary graph has to be laid out into positions
        that reproduce it first, which this does not do for you.

        The answer arrives on `result["mis"]`, with `valid_fraction` reporting
        the share of shots that obeyed every edge. Optional non-negative
        `weights` give the weighted problem.
        """
        resp = self._http.post(
            "/mis",
            json={
                "vertices": [list(v) for v in vertices],
                "weights": list(weights) if weights is not None else None,
                "shots": shots,
                "engine": engine,
                "blockade_um": blockade_um,
                "duration_ns": duration_ns,
            },
        )
        return _job_id(resp)

    def run_mis(
        self,
        vertices: Sequence[Sequence[float]],
        *,
        poll_seconds: float = 0.5,
        timeout: float = 1800.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submit an independent-set problem and wait for the answer."""
        job_id = self.submit_mis(vertices, **kwargs)
        return self._wait(job_id, poll_seconds, timeout)

    def submit_parametric_sweep(
        self,
        program: Any,
        bindings: Sequence[dict[str, float]],
        *,
        kind: str | None = None,
        input_state: Any = None,
        shots: int = 1024,
        engine: str | None = None,
        **params: Any,
    ) -> str:
        """Submit one parameterised program and a list of parameter values.

        The counterpart of `submit_batch` for the two kinds that can carry free
        parameters. A Pulser sequence declares them with `declare_variable`, a
        Perceval circuit with `pcvl.P("name")`, and each binding is applied
        server-side, so an optimiser step sends one program and N small
        dictionaries rather than N serialised programs.

        `kind` is inferred from the program: pass a Perceval circuit with
        `input_state`, or a Pulser sequence on its own.
        """
        if kind is None:
            kind = "photonic" if input_state is not None else "pulser"
        source = (
            _to_photonic(program, input_state) if kind == "photonic" else _to_pulser(program)
        )
        resp = self._http.post(
            "/jobs/batch",
            json={
                "program_kind": kind,
                "program": source,
                "bindings": [dict(b) for b in bindings],
                "shots": shots,
                "engine": engine,
                "params": params,
            },
        )
        return _job_id(resp)

    def run_parametric_sweep(
        self,
        program: Any,
        bindings: Sequence[dict[str, float]],
        *,
        kind: str | None = None,
        input_state: Any = None,
        shots: int = 1024,
        engine: str | None = None,
        poll_seconds: float = 0.2,
        timeout: float = 600.0,
        **params: Any,
    ) -> dict[str, Any]:
        """Submit a parameterised sweep and wait for every point.

        Results come back in binding order, so `job["results"][i]` is the run
        for `bindings[i]`. Like `run_batch`, a failed point is reported rather
        than raised: an optimiser treats it as a bad point and carries on.
        """
        job_id = self.submit_parametric_sweep(
            program, bindings, kind=kind, input_state=input_state,
            shots=shots, engine=engine, **params,
        )
        return self._wait_all(job_id, poll_seconds, timeout)

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
        return self._wait_all(job_id, poll_seconds, timeout)

    def _wait_all(self, job_id: str, poll_seconds: float, timeout: float) -> dict[str, Any]:
        """Poll a multi-point job. Unlike `_wait`, a failed *point* is not an
        error: only the job as a whole failing is."""
        started = time.monotonic()
        deadline = started + timeout
        warned = False
        while time.monotonic() < deadline:
            job = self.job(job_id)
            if job["status"] == "done":
                return job
            if job["status"] == "rejected":
                raise JobRejected(job.get("reason"))
            if job["status"] == "error":
                raise JobFailed(job.get("error"))
            warned = self._polling(
                job_id, job["status"], time.monotonic() - started, warned
            )
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
        started = time.monotonic()
        deadline = started + timeout
        warned = False
        while time.monotonic() < deadline:
            job = self.job(job_id)
            if job["status"] == "done":
                return job
            if job["status"] == "rejected":
                raise JobRejected(job["reason"])
            if job["status"] == "error":
                raise JobFailed(job["error"])
            warned = self._polling(
                job_id, job["status"], time.monotonic() - started, warned
            )
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
        Accepts Qiskit, Cirq, PennyLane, pyQuil or Braket circuits."""
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
        return _job_id(resp)

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
        return _job_id(resp)

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
