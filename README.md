# qsim-sdk

[![CI](https://github.com/official-dvl/zksf/actions/workflows/ci.yml/badge.svg)](https://github.com/official-dvl/zksf/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/qsim-sdk.svg)](https://pypi.org/project/qsim-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/qsim-sdk.svg)](https://pypi.org/project/qsim-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://github.com/official-dvl/zksf/blob/main/LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21836619.svg)](https://doi.org/10.5281/zenodo.21836619)

Official Python client for **ZKSF** (Zero Kelvin Simulation Foundry): a cloud service
that executes quantum circuits on classical simulators, GPU accelerators, or real
quantum processors, and attaches a documented accuracy statement to every approximate
result.

- Website: <https://zksf.org>
- Console: <https://app.zksf.org>
- Documentation: <https://zksf.org/docs>
- API root: `https://api.zksf.org`

---

## 1. Motivation

Classical simulation of quantum circuits is exact only in a narrow regime. Exact
statevector methods terminate near 30 to 32 qubits because state size grows as
`2^n`. Beyond that, every practical method is approximate: tensor networks truncate
the bond dimension, Pauli propagation truncates operator weight, and real hardware
substitutes device noise for the ideal distribution.

An approximate result without an error statement is not a measurement, it is an
assertion. The purpose of this service, and of the certification protocols documented
in [`docs/CERTIFICATION.md`](https://github.com/official-dvl/zksf/blob/main/docs/CERTIFICATION.md), is to return a quantity alongside
each result that states how far it may be from the truth, and to make that quantity
independently checkable by a third party.

## 2. Scope of this repository

This repository contains the **client library only**. It is a thin HTTP wrapper of
roughly 120 lines: authentication, circuit serialisation to OpenQASM 2, four endpoint
calls, and a polling loop.

| In this repository | Not in this repository |
|---|---|
| HTTP client (`qsim_sdk/`) | Simulation engines |
| Packaging metadata | The routing policy implementation |
| Usage examples | Certification computation |
| Protocol documentation | Service infrastructure |

The simulation engines, the router, and the certification computation execute
server-side and are not open source. The client is published so that users can read
exactly what is transmitted before supplying an API token.

## 3. Installation

```bash
pip install qsim-sdk
```

Requires Python 3.10 or newer. Dependencies are `httpx` and `qiskit`.

To submit circuits written in Cirq, PennyLane, pyQuil, or Amazon Braket, install the
optional transpiler extra, which routes them through qBraid into Qiskit:

```bash
pip install "qsim-sdk[multiframework]"
```

Obtain an API token from the console at <https://app.zksf.org> (sign in, then
"Copy API token").

## 4. Quick start

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/quickstart.ipynb)

The notebook above runs in the browser with nothing installed. Its first half needs no
account and spends nothing: it reads four real, already-completed certified runs from the
public API, covering exact simulation, an approximate run with a measured bound, a
192-qubit Pauli propagation result, and a Bell state executed on IonQ Forte-1 hardware.
The second half runs new jobs against your own token.

Six algorithm tutorials follow the same pattern, one per notebook: build the circuit, then
read the certificate for the run that produced the published result. See
[`examples/`](examples/) for all seven, or jump straight in:
[GHZ and Bell states](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/ghz-bell-state.ipynb) ·
[Grover](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/grover-search.ipynb) ·
[QAOA MaxCut](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/qaoa-maxcut.ipynb) ·
[VQE H2](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/vqe-h2.ipynb) ·
[Bernstein-Vazirani](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/bernstein-vazirani.ipynb) ·
[Teleportation](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/quantum-teleportation.ipynb)

```python
import qsim_sdk
from qiskit import QuantumCircuit

qc = QuantumCircuit(3)
qc.h(0)
qc.cx(0, 1)
qc.cx(1, 2)
qc.measure_all()

client = qsim_sdk.Client(token="YOUR_TOKEN")
job = client.run(qc, shots=1000)

print(job["result"]["counts"])      # outcome histogram
print(job["result"]["error_info"])  # accuracy statement for this run
```

Further examples are in [`examples/`](https://github.com/official-dvl/zksf/tree/main/examples).

## 5. API surface

| Method | Purpose | Cost |
|---|---|---|
| `estimate(circuit, shots, engine=None)` | Predicted engine, runtime, and price, or the reason the circuit is infeasible | Free |
| `submit(circuit, shots, engine=None, ...)` | Enqueue a job, returns a job id | Billed on completion |
| `job(job_id)` | Poll a job record | Free |
| `run(circuit, shots, engine=None, ...)` | `submit` followed by polling until terminal state | Billed on completion |

`Client(base_url="https://api.zksf.org", token=None)`. The base URL is overridable for
self-hosted or staging deployments.

### 5.1 Cost control

`estimate()` is free, instant, and returns the engine that would be selected, the
predicted wall-clock seconds, the predicted cost in USD, and the reason for that
selection. Calling it before `run()` is the recommended pattern for any circuit whose
cost is not already known.

### 5.2 Failure semantics

The client raises rather than returning a result that cannot be trusted:

| Exception | Condition |
|---|---|
| `qsim_sdk.JobRejected` | The circuit is intractable or infeasible under the request. The message states why, and what change would make it feasible |
| `qsim_sdk.JobFailed` | An engine error or a hardware-provider error |
| `TimeoutError` | The job did not reach a terminal state within `timeout` seconds |

Rejection is deliberate. A circuit that would return an inconclusive answer is refused
with a diagnostic rather than executed and reported with a meaningless error bar.

### 5.3 Non-blocking submission

Hardware jobs may wait in a provider queue for minutes to hours. `run()` polls until
the result attaches. For long-running hardware work, separate the two phases:

```python
job_id = client.submit(qc, shots=1000, engine="qpu.rigetti")
job = client.job(job_id)  # poll at your convenience
```

## 6. Engines

A rule-based router selects the cheapest engine adequate for the submitted circuit.
No language model or learned policy participates in engine selection or in simulation.
Selection can be overridden with the `engine` argument.

| Class | Engine | Method | Regime and constraints |
|---|---|---|---|
| CPU | `exact.cpu` | Aer statevector | Exact. Hard ceiling at 30 qubits, set by RAM |
| CPU | `clifford` | Stim | Exact for Clifford and stabilizer circuits, scales to thousands of qubits. Rejects non-Clifford gates |
| CPU | `mps.quimb.cpu` | Tensor network (quimb) | Matrix product state, past 100 qubits. Accuracy depends on circuit entanglement. The only engine offering measured single-run bounds |
| CPU | `mps.aer.cpu` | Tensor network (Aer) | An independent MPS implementation, retained for cross-checking against the quimb engine |
| CPU | `pauli.cpu` | Pauli propagation | Expectation values rather than sampled counts. Supported gates: `h`, `cx`, `cz`, `swap`, `rx`, `ry`, `rz`, `rzz`, `rxx`, `ryy`, `x`, `y`, `z`, `s`, `t`, and their inverses |
| CPU | `noisy.cpu` | Density matrix or statevector with a noise model | Device-noise preview, superconducting model by default, optional zero-noise error mitigation. Same 30-qubit ceiling. **Not certifiable, see section 7** |
| GPU | `exact.gpu` | Aer CUDA statevector | Exact. Ceiling is deployment-configured via `QSIM_GPU_MAX_QUBITS` |
| QPU | `qpu.rigetti` | Real hardware | Rigetti Cepheus superconducting processor. Billed at provider cost |
| QPU | `qpu.ionq` | Real hardware | IonQ Forte-1 trapped-ion processor. Billed at provider cost |

Two MPS implementations are maintained deliberately. Agreement between independent
implementations of the same approximation is evidence that neither carries an
implementation-specific error, which is a different question from whether the
approximation itself is tight.

Refer to <https://zksf.org/docs> for current qubit ceilings, which are deployment
configuration rather than properties of the methods.

## 7. Certification

Two protocols are defined. Both are described in full, with worked figures, in
[`docs/CERTIFICATION.md`](https://github.com/official-dvl/zksf/blob/main/docs/CERTIFICATION.md).

| Protocol | Applies to | Reports |
|---|---|---|
| **ZCC-v0.1** | Simulated results | An error bound on the returned distribution |
| **ZHF-v0.1** | Quantum-hardware results | Measured fidelity against the exact ideal distribution |

ZCC-v0.1 covers `exact.cpu`, `exact.gpu`, `clifford`, `mps.quimb.cpu`, `mps.aer.cpu`,
and `pauli.cpu`. It does **not** cover `noisy.cpu`, for the reason given in section 8.

Every job may be exported as a signed certificate carrying a stable identifier. The
certificate is retrievable without authentication, so a reader who was not party to
the original run can check it:

```
GET https://api.zksf.org/certify/<cert_id>       # HTML verification page
GET https://api.zksf.org/certify/<cert_id>/pdf   # PDF
```

## 8. Limitations

Stated explicitly, because a certification claim is only as credible as its declared
boundaries:

1. A ZCC-v0.1 bound quantifies the error introduced by the approximation used in that
   specific run. It does not bound error arising from an incorrectly specified circuit,
   nor from finite sampling, which is reported separately as shot noise.
2. Rigorous single-run bounds are available on the quimb MPS engine. Other engines
   report a convergence-based accuracy statement, which is diagnostic rather than a
   proof.
3. **Noise-preview runs are not certifiable.** The `noisy.cpu` engine simulates a
   device noise model, so its output deliberately approximates a noisy machine rather
   than the ideal distribution. There is no ideal reference for a bound to be taken
   against, and no certificate is issued for these runs.
4. A ZHF-v0.1 fidelity is a measurement of one hardware run against a reference
   distribution. It characterises that execution on that device at that time. It does
   not predict the fidelity of a subsequent run.
5. Direct verification requires an obtainable reference distribution, which constrains
   the circuit sizes for which ZHF-v0.1 can be evaluated in its direct mode.
6. Protocol versions are pinned in the identifier (`v0.1`). Version numbers below 1.0
   indicate that the specifications are not yet frozen.

## 9. Citation

If this service or its certification protocols contribute to published work, please
cite the protocol note. Machine-readable metadata is in [`CITATION.cff`](https://github.com/official-dvl/zksf/blob/main/CITATION.cff).

## 10. Contributing and security

- Contribution guidance: [`CONTRIBUTING.md`](https://github.com/official-dvl/zksf/blob/main/CONTRIBUTING.md)
- Vulnerability disclosure: [`SECURITY.md`](https://github.com/official-dvl/zksf/blob/main/SECURITY.md).
  Please do not open a public issue for a security report.

## 11. License

MIT. See [`LICENSE`](https://github.com/official-dvl/zksf/blob/main/LICENSE).
