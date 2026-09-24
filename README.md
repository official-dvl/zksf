# qsim-sdk

[![CI](https://github.com/official-dvl/zksf/actions/workflows/ci.yml/badge.svg)](https://github.com/official-dvl/zksf/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/qsim-sdk.svg)](https://pypi.org/project/qsim-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/qsim-sdk.svg)](https://pypi.org/project/qsim-sdk/)
[![Qiskit](https://img.shields.io/badge/Qiskit-%E2%89%A5%201.0-6133BD?logo=qiskit&logoColor=white)](https://github.com/Qiskit/qiskit)
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

This repository contains the **client library only**. It is a thin HTTP wrapper:
authentication, program serialisation (OpenQASM 2, Pulser and Perceval), the job,
account and certificate endpoints, and polling.

| In this repository | Not in this repository |
|---|---|
| HTTP client (`qsim_sdk/`) | Simulation engines |
| Packaging metadata | The routing policy implementation |
| Usage examples | Certification computation |
| Protocol documentation | Service infrastructure |

The simulation engines, the router, and the certification computation execute
server-side and are not open source. The client is published so that users can read
exactly what is transmitted before supplying an API key.

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

To use a quantum program as a differentiable PyTorch layer (`qsim_sdk.ml`), install the
`ml` extra. torch is not a dependency of the base package, because most users of this
client never train anything and it is a large install:

```bash
pip install "qsim-sdk[ml]"
```

Create an API key in the console at <https://app.zksf.org> (Profile, then **Create API
key**). A key is valid for 30 days, is shown once, and can be revoked there at any time.
Pass it as `token=`, or set the `ZKSF_TOKEN` environment variable and pass nothing:

```bash
export ZKSF_TOKEN=zksf_...
```

## 4. Quick start

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/quickstart.ipynb)

The notebook above runs in the browser with nothing installed. Its first half needs no
account and spends nothing: it reads four real, already-completed certified runs from the
public API, covering exact simulation, an approximate run with a measured bound, a
192-qubit Pauli propagation result, and a Bell state executed on IonQ Forte-1 hardware.
The second half runs new jobs with your own API key.

Six algorithm tutorials follow the same pattern, one per notebook: build the circuit, then
read the certificate for the run that produced the published result. See
[`examples/`](examples/) for all seven, or jump straight in:
[GHZ and Bell states](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/ghz-bell-state.ipynb) ·
[Grover](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/grover-search.ipynb) ·
[QAOA MaxCut](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/qaoa-maxcut.ipynb) ·
[VQE H2](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/vqe-h2.ipynb) ·
[Bernstein-Vazirani](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/bernstein-vazirani.ipynb) ·
[Teleportation](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/quantum-teleportation.ipynb)

The seventh is not a gate algorithm and is listed separately for that reason:
[Rydberg antiferromagnetic chain](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/rydberg-antiferromagnetic-chain.ipynb)
builds a pulse schedule on a neutral-atom register rather than a circuit, so the thing
you vary is the geometry and the drive, not a sequence of gates.

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
| `estimate(circuit, shots, engine=None)` | Predicted engine, runtime, and price for ONE circuit, or the reason it is infeasible | Free |
| `estimate_batch(circuits, shots, engine=None)` | The same for a whole sweep: total, per point, and how many batches it takes | Free |
| `submit(circuit, shots, engine=None, ...)` | Enqueue a job, returns a job id | Billed on completion |
| `job(job_id)` | Poll a job record | Free |
| `run(circuit, shots, engine=None, ...)` | `submit` followed by polling until terminal state | Billed on completion |
| `submit_sequence(sequence, shots, ...)` | Enqueue a neutral-atom Pulser sequence, returns a job id | Billed on completion |
| `run_sequence(sequence, shots, ...)` | `submit_sequence` followed by polling | Billed on completion |
| `submit_photonic(circuit, input_state, shots, ...)` | Enqueue a linear-optics circuit and its input photons, returns a job id | Billed on completion |
| `run_photonic(circuit, input_state, shots, ...)` | `submit_photonic` followed by polling | Billed on completion |
| `submit_batch(circuits, shots, ...)` | Enqueue many gate circuits as one job | Billed per circuit |
| `run_batch(circuits, shots, ...)` | `submit_batch` followed by polling | Billed per circuit |
| `run_sweep(circuit, bindings, ...)` | Bind one parameterised Qiskit circuit at many values and run them as one job | Billed per point |
| `submit_parametric_sweep(program, bindings, ...)` | Enqueue one parameterised Pulser or Perceval program and a list of bindings | Billed per point |
| `run_parametric_sweep(program, bindings, ...)` | `submit_parametric_sweep` followed by polling | Billed per point |
| `solve(hamiltonian, qubits, ...)` / `submit_solve(...)` | A ground-state problem rather than a program: the service runs the variational loop | Billed per evaluation |
| `run_mis(vertices, ...)` / `submit_mis(...)` | Maximum independent set on a neutral-atom register | Billed as one analog job |
| `estimate_solve(hamiltonian, qubits, ...)` | The price of a ground-state search before submitting it | Free |
| `pending()` | Every job on the account that has not finished | Free |
| `jobs(limit, cursor)` / `iter_jobs()` | The account's job history, newest first | Free |
| `cancel(job_id)` | Cancel a hardware job still waiting in its provider's queue | Refunded once the provider confirms it never ran |
| `summary(since=None)` | Jobs run per tier, and net spend since the start of the month | Free |
| `balance()` | Available credit in USD | Free |
| `certificate(job_id, index=None)` | Issue a finished job's public certificate: verify URL and PDF | Free |

`Client(base_url="https://api.zksf.org", token=None)`. The base URL is overridable for
self-hosted or staging deployments, and `token` falls back to the `ZKSF_TOKEN` environment
variable.

### 5.0 Neutral-atom sequences

One engine does not take a circuit. Neutral-atom hardware is programmed as a register
of atoms and a schedule of laser pulses, which has no gate decomposition, so it takes a
[Pulser](https://pulser.readthedocs.io/) sequence through its own call. Routing does not
apply either: there are no circuit features to inspect, so these jobs name their engine.

```python
from pulser import Pulse, Register, Sequence
from pulser.devices import AnalogDevice

reg = Register.square(2, spacing=6.0).with_automatic_layout(AnalogDevice)
seq = Sequence(reg, AnalogDevice)
seq.declare_channel("ising", "rydberg_global")
seq.add(Pulse.ConstantPulse(1000, 6.0, 0.0, 0.0), "ising")

job = client.run_sequence(seq, shots=1000)
print(job["result"]["counts"])      # a bit reads 1 when that atom ended in Rydberg
```

Pulser is not a dependency of this package. If you do not have it installed, pass the
sequence's abstract representation as a JSON string instead. `estimate()` takes gate
circuits only, so there is no SDK price check for a sequence yet.

The same sequence runs on real neutral-atom hardware by naming a different engine.
`analog.pulser.cpu` is the exact local reference, capped at 14 atoms; the two processors
go far wider than anything that can be simulated exactly, so a run above that ceiling
returns results and no ZHF certificate:

```python
job = client.run_sequence(seq, shots=100, engine="qpu.quera.aquila")   # up to 256 atoms
job = client.run_sequence(seq, shots=20,  engine="qpu.pasqal.fresnel") # up to 100 atoms
```

Two practical differences from the gate QPUs, both worth knowing before submitting.
Aquila runs only inside QuEra's published execution windows, so a submission outside one
is accepted and waits rather than failing. FRESNEL bills machine time rather than shots,
at roughly four seconds of QPU wall clock per shot, so the 1,024-shot default that is
nearly free elsewhere would be a very expensive job here; shot counts are capped
server-side for that reason, and the refusal says so.

### 5.0.1 Photonic linear optics

Nor does photonic hardware take a circuit in the gate sense. Quandela sells Belenos as a
12-qubit machine (MosaiQ 12), and dual-rail encoding does spend two of its 24 modes on
each qubit, but the interface exposed here is the optics underneath: there are no gates,
and photons enter chosen modes, interfere through beamsplitters and phase shifters,
and the answer is which modes they leave by. A program is therefore two things, a
[Perceval](https://perceval.quandela.net/) circuit and the input photons, because unlike
a gate circuit it does not carry its own initial state. Both are hashed, so two runs
that differ only in where the photons entered cannot share a certificate.

```python
import perceval as pcvl
from perceval.components import BS, PERM

# Hong-Ou-Mandel: two photons meet on a balanced beamsplitter
circuit = pcvl.Circuit(3) // (1, PERM([1, 0])) // (0, BS.H())

job = client.run_photonic(circuit, [1, 0, 1], shots=1000)
print(job["result"]["counts"])      # {'|2,0,0>': 492, '|0,2,0>': 508}
```

Indistinguishable photons must bunch: both leave by the same mode, and the coincidence
term `|1,0,1>` is zero. That makes the coincidence fraction a direct fidelity measure,
which is what a photonic certificate reports.

The input state accepts an occupation list as above, a `perceval.BasicState`, or either
one already serialised. Perceval is not a dependency of this package, and the list form
needs it only for the circuit. Pass `engine="qpu.quandela.belenos"` to run on real
hardware, which accepts photons only on its connected input modes and refuses anything
else before submission rather than after you have paid. As with sequences there is no
`estimate()` counterpart yet.

### 5.0.2 Parameter sweeps and training loops

A single submission is rarely the workload. A variational solver, a quantum kernel or a
photonic generative model is one *parameterised* program evaluated hundreds or thousands
of times while an optimiser walks its parameters. Sent one job at a time that is
thousands of round trips and thousands of queue entries, so the whole step goes as one
job instead.

Gate circuits send one bound circuit per point, because OpenQASM 2 cannot express a free
parameter. Pulser sequences and Perceval circuits can, so they send the program once and
a list of bindings, applied server-side. Each bound point hashes to its own value, so a
certificate still identifies exactly which parameters produced it.

```python
import numpy, perceval as pcvl

circuit = pcvl.Circuit(2) // (0, pcvl.BS(theta=pcvl.P("theta")))
job = client.run_parametric_sweep(
    circuit,
    [{"theta": t} for t in numpy.linspace(0, numpy.pi, 40)],
    input_state=[1, 1],
    engine="photonic.slos.cpu",
)
job["results"][7]["result"]["counts"]      # the run for bindings[7]
```

The same call takes a Pulser sequence, whose variables come from
`seq.declare_variable(...)`. Sweeps run on simulation engines: each provider task is
queued and billed individually, so batching to a QPU would hide the per-task cost behind
one job id rather than save anything. Settle the sweep in simulation, then send the
surviving point to the machine.

**As a torch layer.** `qsim_sdk.ml` wraps a quantum program as an `nn.Module`, so it
becomes a differentiable layer in an ordinary PyTorch model. There are three, one per
kind of program: `CircuitLayer` for a gate circuit, `PhotonicLayer` for a linear-optical
mesh, `SequenceLayer` for an analog pulse sequence. They differ only in what they
submit, so a model written against one ports to another by changing the constructor.

The forward pass is one job; the backward pass is one job carrying two points per
parameter.

```python
from qsim_sdk.ml import PhotonicLayer          # pip install qsim-sdk[ml]

layer = PhotonicLayer(client, circuit, [1, 1], shots=4000)
opt = torch.optim.SGD(layer.parameters(), lr=0.3)
for step in range(200):
    opt.zero_grad()
    criterion(layer(), target).backward()      # layer() = probability per outcome
    opt.step()
```

**A model that reads data declares which parameters carry it.** Without that split every
angle in the circuit is a trainable weight, so an encoding angle would be optimised as
though it were one. Name the data parameters and the rest are the weights:

```python
from qiskit.circuit import ParameterVector
from qsim_sdk.ml import CircuitLayer

x = ParameterVector("x", 2)                    # the data point
w = ParameterVector("w", 4)                    # the trainable part
qc = QuantumCircuit(2)
qc.ry(x[0], 0); qc.ry(x[1], 1)
qc.ry(w[0], 0); qc.ry(w[1], 1); qc.cx(0, 1)
qc.ry(w[2], 0); qc.ry(w[3], 1)
qc.measure_all()

layer = CircuitLayer(client, qc, inputs=[p.name for p in x], shots=1024)
probs = layer(X)                               # X is (batch, 2) -> (batch, outcomes)
```

A whole minibatch is one job and its gradient is one more, whatever the batch size: `B`
samples over `P` weights is `B` points forward and `B * 2P` backward. Sent one sample at
a time the same step is `2B` submissions, each paying its own queue entry and its own
per-circuit minimum. Know what a step costs before a long run, with `estimate_batch`: 32
samples over 8 weights is 544 circuits per step.

Gradients are central differences, not the parameter-shift rule: the shift rule is exact
only where an output is a sinusoid of the parameter, which is true of a Pauli rotation
and false of a beamsplitter angle or a pulse amplitude. Shot noise sets the floor on how
small a gradient you can resolve, so an optimiser that stalls at low shot counts is
usually reading noise rather than a flat landscape.

Gradients are taken with respect to the weights, not the inputs. An input carrying
`requires_grad` is refused rather than silently given no gradient, because a classical
network placed in front of the layer would otherwise never train while appearing to.

### 5.0.3 Ground states, one at a time or many

`solve()` takes a Hamiltonian rather than a circuit and runs the variational loop
server-side, on a neural network quantum state. Read
`result["ground_state"]["ceiling"]` rather than `result["energy"]`: the variational
principle puts the true ground state at or below the energy found, and the ceiling adds
the run's own error bound to give a number the true answer cannot exceed.

**`ansatz="rbm_symm"`** imposes translation symmetry on the network, which is the biggest
accuracy lever available here. On a six-spin transverse-field Ising ring it reached
0.0018 above the exact ground state where the default network reached 0.0067, using a
sixth of the parameters. It is **refused unless your Hamiltonian actually has that
symmetry**, checked rather than assumed: a symmetric network cannot represent the ground
state of a Hamiltonian that breaks the symmetry, so it would converge above the true
energy and report a ceiling that is honest and useless.

**`run_solve_batch()` runs many Hamiltonians on ONE machine**, which matters on a TPU:
roughly 522 seconds of every job is the machine being created and deleted, against about
113 seconds of work. A phase diagram sent one Hamiltonian at a time spends four fifths of
its money on provisioning; sent together, that is paid once.

```python
problems = [{"qubits": 8, "hamiltonian": h(j)} for j in couplings]
est = client.estimate_solve_batch(problems, engine="neural.tpu")   # free
job = client.run_solve_batch(problems, engine="neural.tpu")
```

Price it first. The total is neither one point's price nor N of them: provisioning does
not multiply and the per-circuit minimum does, so `estimate_solve_batch` returns the
per-point breakdown as well as the total. Each point is independent, a point that fails
is reported in place with its reason, and anything that produced no result is refunded.
A point's own settings override the batch's, so a sweep over the ansatz is one
submission.

### 5.0.4 State reconstruction

`run_tomography()` fits a state to measurement records from a device.

```python
client.estimate_tomography(n_spins, bases, outcomes)   # free, same body as the run
job = client.run_tomography(n_spins, bases, outcomes)
job["result"]["agreement"]["agreed"]        # of how many were checked
```

`bases[i]` is the basis shot `i` was measured in, one character per qubit over X, Y and
Z; `outcomes[i]` is what came back, as `+1` and `-1` rather than 0 and 1.

A reconstruction is **not eligible for ZKSF certification and does not carry a fidelity
bound**. It carries measured agreement instead: the reconstruction reproduces the measured
expectations to within a stated interval at a stated confidence, scored on records the fit
never saw and reported under `agreement`.

The submission is **refused when your bases cannot determine a state**. An
under-determined fit converges perfectly well onto the wrong state and nothing downstream
can tell: measured on a Bell state at identical settings, five bases gave fidelity 0.51
and all nine gave 0.98.

### 5.0.5 Error correction

`qec()` holds a logical qubit in a code under circuit-level noise and counts how often
it comes back wrong.

```python
client.estimate_qec("surface", distance=5, shots=100_000)          # free
job = client.qec("surface", distance=5, shots=100_000, physical_error=1e-3)
job["result"]["confidence_interval_95"]      # [0.0, 3.69e-05]
```

**Read the interval, not the rate.** A logical error rate is a proportion measured from
a finite number of shots, so at a hundred thousand shots with no failures it reads 0.
The statement that can be made is that the rate is below the top of the interval, and
that is the number the certificate carries.

`qec_scaling()` answers the question every roadmap is quoted in and almost nobody will
answer for a specific device: **how many physical qubits is one logical qubit at your
error rate.**

```python
job = client.qec_scaling(physical_error=1e-3, target_logical_error_rate=1e-9)
res = job["result"]
res["suppression"]["lambda"]      # measured across distances 3, 5 and 7
res["physical_qubits"]            # what one logical qubit costs
res["basis"]                      # measured, or extrapolated from what
```

**Read `basis`.** The suppression factor is measured from real runs, the distance that
follows from it is arithmetic, and a target below anything those runs could observe is
reached by extrapolating along the measured slope. At or above threshold the answer is
that no number of physical qubits reaches the target until the error rate comes down,
which is a result rather than a failure.

Codes are `surface`, `surface_x`, `surface_unrotated` and `repetition`, decoded by
minimum-weight perfect matching. Colour and qLDPC codes are refused rather than decoded
that way: matching is the wrong decoder for them, and a wrong decoder returns a number
indistinguishable from a right one. This measures **memory only**: prepare, hold, read
out. Logical gates and lattice surgery are not offered.

### 5.1 Cost control

`estimate()` is free, instant, and returns the engine that would be selected, the
predicted wall-clock seconds, the predicted cost in USD, and the reason for that
selection. Calling it before `run()` is the recommended pattern for any circuit whose
cost is not already known.

**`estimate()` prices one circuit. A sweep is priced by `estimate_batch()`.** The
minimum charge applies per circuit, so a 600-point sweep is 600 minimums, and
reading the single-circuit figure as the cost of the sweep understates it by a
factor of the point count:

```python
est = client.estimate_batch(circuits, shots=1024, engine="exact.cpu")
est["total_usd"]      # what the account will be debited
est["per_point_usd"]  # and where it goes; a sweep is not uniform
est["batches"]        # how many submissions run_batch will take
```

Sweeps longer than one batch are chunked and summed, so asking about 12,000
circuits returns the real total rather than a refusal.

### 5.1.1 The first job on an idle engine

The first job sent to an engine after a quiet period takes noticeably longer to
start than the ones that follow it. Later jobs on the same engine are faster.

The SDK prints one line to stderr once a job has waited more than 15 seconds, so
a notebook cell that has printed nothing is not mistaken for a broken service.
`ZKSF_SLOW_JOB_SECONDS` changes the threshold, and `Client(on_poll=...)` drives
your own progress output instead.

### 5.2 Failure semantics

The client raises rather than returning a result that cannot be trusted:

| Exception | Condition |
|---|---|
| `qsim_sdk.JobRejected` | The circuit is intractable or infeasible under the request. The message states why, and what change would make it feasible |
| `qsim_sdk.JobFailed` | An engine error or a hardware-provider error |
| `qsim_sdk.CancelRefused` | `cancel()` was declined: the job has started, has finished, or runs where cancelling is not offered. The message says which |
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
| GPU | `exact.gpu` | Aer CUDA statevector | Exact, to 32 qubits |
| CPU | `analog.pulser.cpu` | Rydberg dynamics (QuTiP) | Neutral-atom analog. Takes a Pulser sequence, not a circuit, so it is never routed to and is named explicitly. Exact: the state is integrated without truncation, and the register is capped at 14 atoms. See section 5.0 |
| QPU | `qpu.rigetti` | Real hardware | Rigetti Cepheus superconducting processor, 108 qubits. Billed at provider cost |
| QPU | `qpu.ionq` | Real hardware | IonQ Forte Enterprise 1 trapped-ion processor, 36 qubits, 100 to 5,000 shots. Billed at provider cost |
| QPU | `qpu.iqm.garnet` | Real hardware | IQM Garnet superconducting processor, 20 qubits, up to 20,000 shots. Billed at provider cost |
| QPU | `qpu.iqm.emerald` | Real hardware | IQM Emerald superconducting processor, 54 qubits, up to 20,000 shots. Billed at provider cost |
| CPU | `photonic.slos.cpu` | Linear optics (Perceval SLOS) | Photonic. Takes a circuit and an input Fock state, not a gate circuit, so it is never routed to and is named explicitly. Exact, and capped at 12 modes: cost grows with the ways the photons can distribute over the modes, so modes alone understate it. See section 5.0.1 |
| QPU | `qpu.aqt.ibex` | Real hardware | AQT IBEX Q1 trapped-ion processor, 12 qubits, up to 2,000 shots. Billed at provider cost |
| QPU | `qpu.quandela.belenos` | Real hardware | Quandela Belenos photonic processor (sold as MosaiQ 12, a 12-qubit machine): up to 24 modes and 12 photons, two modes per qubit under dual-rail encoding, inputs on connected modes only. Billed at provider cost |
| QPU | `qpu.quera.aquila` | Real hardware | QuEra Aquila neutral-atom processor, up to 256 atoms. Takes the same Pulser sequence as `analog.pulser.cpu`, not a gate circuit, so it is named explicitly. Runs only inside QuEra's published execution windows: a submission outside one is accepted and waits. Billed at provider cost |
| QPU | `qpu.pasqal.fresnel` | Real hardware | Pasqal FRESNEL neutral-atom processor, up to 100 atoms. Also takes a Pulser sequence. Bills **machine time rather than shots**, so a shot is roughly four seconds of QPU wall clock and the usual 1,024-shot default would be an expensive job; shot counts are capped server-side for that reason. Billed at provider cost |
| CPU | `neural.cpu` | Neural-network wavefunction (variational Monte Carlo) | Ground states rather than circuits: takes a Hamiltonian through `solve()`, up to 40 spins. A circuit sent to it is refused |
| TPU | `neural.tpu` | The same method on a Google TPU | The same results and bound as `neural.cpu`. Billed by runtime, with start-up included in the quoted price and unused seconds refunded; price it first with `estimate_solve()` |

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
| **ZCC-Estimate-v0.2** | Error-mitigated values (`mitigate=True`) | A statistical uncertainty on the mitigated value, not a bound |

ZCC-v0.1 covers `exact.cpu`, `exact.gpu`, `clifford`, `mps.quimb.cpu`, `mps.aer.cpu`,
and `pauli.cpu`. It does **not** cover `noisy.cpu`, for the reason given in section 8.

A `run_tomography()` result is **not eligible for either protocol**: the reconstruction
does not carry a fidelity bound, so requesting a certificate returns 409. Its measured
agreement with held-out records is reported on the job instead, under `agreement`.

A batched solve has one bound per point rather than one for the batch, because each point
is an independent search. Name the point to certify with `?index=N`, exactly as for a
circuit batch.

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
6. Protocol versions are pinned in the identifier (`v0.1`, `v0.2`). Version numbers below 1.0
   indicate that the specifications are not yet frozen.
7. **Parameter sweeps run on simulation engines only.** Hardware is refused rather than
   silently fanned out: each provider task is queued and billed individually, so a
   "batch" to a QPU would hide the per-task cost behind one job id. Training loops
   against real hardware are driven from your own code, one submission per evaluation.
8. **`qsim_sdk.ml` gradients are central differences, not the parameter-shift rule.**
   The shift rule is exact only where an output is a sinusoid of the parameter, which
   holds for a Pauli rotation and not for a beamsplitter angle or a pulse amplitude.
   The estimate therefore carries a step-size error as well as shot noise.

## 9. Citation

If this service or its certification protocols contribute to published work, please
cite the protocol note. Machine-readable metadata is in [`CITATION.cff`](https://github.com/official-dvl/zksf/blob/main/CITATION.cff).

## 10. Contributing and security

- Contribution guidance: [`CONTRIBUTING.md`](https://github.com/official-dvl/zksf/blob/main/CONTRIBUTING.md)
- Vulnerability disclosure: [`SECURITY.md`](https://github.com/official-dvl/zksf/blob/main/SECURITY.md).
  Please do not open a public issue for a security report.

## 11. License

MIT. See [`LICENSE`](https://github.com/official-dvl/zksf/blob/main/LICENSE).
