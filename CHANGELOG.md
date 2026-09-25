# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.13.0]

### Added
- **`Client.estimate_photonic()`, `Client.estimate_sequence()` and
  `Client.estimate_mis()`.** Free quotes for linear-optics circuits, Pulser
  sequences and maximum independent set, taking exactly what the matching
  `submit_*` takes. The SDK could submit all three and price none of them.
- **`ConnectionLost`**, raised when the connection keeps dropping while waiting
  for a job. It carries `job_id`, and its message says how to read the job again.

### Fixed
- **A dropped connection while waiting no longer loses the job.** `run()`,
  `run_batch()` and every other call that waits now read the job again after a
  reset, protocol error, timeout or 5xx, with a backoff, instead of raising the
  transport error. A read failing is not the job failing. Previously the error
  carried no job id, so a job that went on to finish could not be found.
- `JobRejected` and `JobFailed` raised while waiting now carry `job_id`.

## [0.12.0]

### Changed
- Released as a minor version: 0.11.2 added a capability (dynamic circuits sent as
  OpenQASM 3) and a method (`estimate_tomography`). Same code as 0.11.2;
  `CITATION.cff` now carries the released version.

## [0.11.2]

### Added
- **Dynamic circuits.** A Qiskit circuit with mid-circuit control flow
  (`if_test`, `while_loop`, `for_loop`, `switch` on measured bits) has no
  OpenQASM 2.0 form, so the SDK now sends it as OpenQASM 3. The service runs it
  on `exact.cpu`, `noisy.cpu` and `mps.aer.cpu`. Circuits without control flow
  are sent as 2.0 exactly as before.
- **`Client.estimate_tomography()`.** A free quote for a state reconstruction,
  taking exactly what `submit_tomography()` takes and priced by the service the
  way it will charge: metered on runtime, with the per-job floor. The console
  could already quote a reconstruction and the SDK could not, so a script had
  no way to learn the price before submitting. `submit_tomography()` now builds
  its request with the same helper, so the quote and the charge cannot drift.

## [0.11.1]

### Changed
- **`docs/CERTIFICATION.md` documents ZQEC-v0.1.** 0.11.0 shipped the methods
  and announced the protocol in this changelog while the specification beside
  them still described two protocols and titled itself after them. The new
  section 4 covers what the interval asserts and why it is Wilson's, the three
  assumptions recorded on every certificate (the noise model, the decoder, and
  memory rather than computation), why colour and qLDPC codes are refused
  rather than decoded, why the subject hash excludes the shot count, and a
  worked example transcribed from a live certificate rather than composed.
  Sections 4 through 7 renumbered to 5 through 8, and the two internal
  cross-references that moved with them corrected.
- A ninth entry in the limitations section: a logical error rate is a property
  of a code AND its decoder under a stated noise model, so it does not transfer
  to hardware whose errors are correlated, leaky or drifting, and it bounds
  memory rather than computation.
- `CITATION.cff` describes three certification protocols rather than two, and
  gains quantum error correction, surface code and logical qubits as keywords.

### Notes
- No code changes. The Python surface is identical to 0.11.0.

## [0.11.0]

### Added
- **Quantum error correction.** `qec()`, `submit_qec()` and `estimate_qec()`
  hold a logical qubit in a code for a number of rounds under circuit-level
  noise and count how often it comes back wrong.

  ```python
  job = client.qec("surface", distance=5, shots=100_000, physical_error=1e-3)
  job["result"]["confidence_interval_95"]   # [0.0, 3.69e-05]
  ```

  **Read the interval, not the rate.** A logical error rate is a proportion
  measured from a finite number of shots, so at a hundred thousand shots with
  no failures it reads 0. The statement that can be made is that the rate is
  below the top of the interval, and that is what the certificate carries. The
  interval is Wilson's, which stays correct at zero where the textbook one
  collapses to [0, 0] and claims a perfect code from a finite experiment.

  Codes are `surface`, `surface_x`, `surface_unrotated` and `repetition`,
  decoded by minimum-weight perfect matching. Colour and qLDPC codes are
  refused rather than decoded that way: matching is the wrong decoder for them
  and a wrong decoder returns a number indistinguishable from a right one.

  The circuits come from `stim.Circuit.generated`, the reference generators the
  field checks against, rather than being written here. A hand-rolled syndrome
  extraction circuit that is subtly wrong still runs, still decodes and still
  produces a confident number.

- **`qec_scaling()`, `submit_qec_scaling()` and `estimate_qec_scaling()`: how
  many physical qubits is one logical qubit at YOUR error rate.** Every roadmap
  in this industry is quoted in logical qubits and almost nobody will answer
  that for a specific device.

  ```python
  job = client.qec_scaling(physical_error=1e-3, target_logical_error_rate=1e-9)
  res = job["result"]
  res["suppression"]["lambda"]   # measured across distances 3, 5 and 7
  res["distance"], res["physical_qubits"]
  res["basis"]                   # which half is measured, which extrapolated
  ```

  **Read `basis`.** The suppression factor is measured from real runs, the
  distance that follows from it is arithmetic, and a target below anything
  those runs could observe is reached by extrapolating along the measured
  slope. Saying which is which is the difference between this and a figure
  copied from a roadmap.

  A distance that produced no failures is excluded from the fit rather than
  replaced by its confidence bound, because substituting a bound for a missing
  measurement turns a measurement into an assumption without saying so. One
  usable point is refused outright: a slope needs two.

  **At or above threshold the answer is that there is no such number** until
  the physical error rate comes down. That is a result, not a failure.

- **ZQEC-v0.1**, a third certificate protocol beside ZCC-v0.1 and ZHF-v0.1,
  carrying the logical error rate with its interval, the code, the distance,
  the rounds, the noise model and the decoder. Its subject hash covers the code
  and the noise model and deliberately not the shot count, so the same
  experiment run again at more shots hashes the same.

### Notes
- Memory only: prepare, hold for some rounds, read out. Logical gates, lattice
  surgery and magic state distillation are not here.
- The noise is circuit-level depolarizing, which is the model these rates are
  published against. It is not a model of any particular vendor's device.
- Physical qubit counts are the qubits a circuit operates on, which is not
  `stim.Circuit.generated(...).num_qubits`: that is the largest index plus one,
  and a rotated surface code leaves grid slots empty. A rotated code of
  distance d uses 2d^2-1 and an unrotated one (2d-1)^2, so neither formula
  covers both and neither is hard-coded; the count is derived from the
  circuits.

## [0.10.0]

### Added
- `qsim_sdk.ml.CircuitLayer`, a parameterised Qiskit circuit as a torch
  `nn.Module`. The gate-circuit member of a family that previously had only
  `PhotonicLayer` and `SequenceLayer`, which left out the form most quantum
  machine learning is written in: variational classifiers, circuit Born
  machines, the generator half of a GAN, the sub-generators of a patch GAN.
  Writing one meant hand-rolling central differences, batching and an autograd
  Function first, about 150 lines before any of the model.

  Parameters are bound client-side, because OpenQASM 2 cannot carry an unbound
  one, so the wire only ever sees bound circuits.

- **Data inputs.** `inputs=` names the circuit parameters that carry a data
  point; every other parameter is a trainable weight. Without the split, an
  encoding angle would be optimised as though it were a weight, which is wrong
  rather than merely awkward, and a classifier could not be expressed at all.
  The two halves are assembled by name, so declaring an input reorders nothing.

- **Minibatches.** `forward(x)` takes `(features,)` and returns a probability
  vector, or `(batch, features)` and returns `(batch, outcomes)`. A whole
  minibatch is ONE submission and its gradient is ONE more, whatever the batch
  size: B samples over P weights is B points forward and B x 2P backward. Sent
  a sample at a time the same step is 2B submissions, each paying its own queue
  entry and its own per-circuit minimum.

  Know what a step costs before a long run: 32 samples over 8 weights is 544
  circuits per step. `estimate_batch` prices it.

- **`run_solve_batch` / `submit_solve_batch` / `estimate_solve_batch`.** Many
  ground states on ONE machine. On a TPU roughly 522 seconds of every job is
  the machine being created and deleted, against about 113 seconds of work, so
  a phase diagram sent one Hamiltonian at a time spends four fifths of its
  money on provisioning. Sent together it is paid once, and the estimate shows
  the per-point breakdown because the total is neither one job's price nor N of
  them: provisioning does not multiply and the per-circuit minimum does.

  Each point is independent. One that fails is reported in place with its
  reason and the others still return; anything that produced no result is
  refunded. `params` applies to every point and a point's own value wins, so a
  sweep over the ansatz is one submission.

- **`ansatz="rbm_symm"`** on any ground-state call: a translation-symmetric
  network. On a 6-spin transverse-field Ising ring it landed 0.0018 above the
  exact ground state against the plain network's 0.0067, with a sixth of the
  parameters. It is REFUSED unless the Hamiltonian actually has that symmetry,
  checked rather than assumed, because a symmetric network cannot represent the
  ground state of a Hamiltonian that breaks the symmetry and would report a
  ceiling that is honest and far too high.

- **`run_tomography` / `submit_tomography`.** Reconstruct the state a device
  prepared, from its measurement records.

  A reconstruction is not eligible for ZKSF certification and does not carry a
  fidelity bound; `result["certifiable"]` is False and requesting a certificate
  returns 409. It carries measured agreement instead, under `agreement`: every
  observable reproduced to within a stated interval at a stated confidence,
  scored on records the fit never saw.

  The submission is refused when the bases cannot determine a state. An
  under-determined fit converges perfectly well onto the wrong state and nothing
  downstream can tell: measured on a Bell state at identical settings, five
  bases gave fidelity 0.51 and all nine gave 0.98.

### Notes
- Gradients are taken with respect to the weights, not the inputs. An input
  tensor carrying `requires_grad` is refused with a clear error rather than
  silently given no gradient, because a classical network placed in front of
  the layer would otherwise never train while appearing to.
- `CircuitLayer` refuses a circuit with no measurements at construction. The
  failure it would otherwise produce is empty counts, which reads as a broken
  engine rather than as a circuit that was never asked for an answer.
- The outcome list is learned from one probe at the initial parameters, with
  data parameters probed at zero. A circuit initialised near a basis state may
  not produce most of its bitstrings in that single run, so pass `outcomes=`
  whenever the output space is known, which for n measured qubits is every
  n-bit string.

## [0.9.0]

### Added
- `estimate_batch(circuits, ...)`, a free pre-run price for a whole sweep
  rather than for one circuit. `estimate()` prices a single circuit and the
  minimum is charged per circuit, so a 600-point sweep is 600 minimums and the
  multiplication was the caller's to remember. It returns `total_usd`, the
  per-point breakdown (a sweep is not uniform: a tensor-network or
  linear-optics run costs what its bound values make it cost), and `batches`,
  the number of submissions the sweep will take. Sweeps longer than the
  service's per-batch limit are chunked and summed, because the sweep worth
  pricing is exactly the long one.
- `Client(on_poll=...)`, called as `on_poll(job_id, status, elapsed_seconds)`
  on every poll while a job waits, for callers building progress output.

### Changed
- A job that has waited more than 15 seconds now prints one line to stderr
  saying so, once per wait rather than per poll. The first job sent to an engine
  after a quiet period takes noticeably longer to start, and a notebook cell
  that has printed nothing for half a minute reads as a broken service. stderr
  so it never contaminates piped stdout; `ZKSF_SLOW_JOB_SECONDS` changes the
  threshold.

### Fixed
- `PhotonicLayer` and `SequenceLayer` raise at construction when the program
  produces no outcomes, instead of building a layer whose every gradient is
  zero. A register built with `Register.from_coordinates` is refused by the
  service with a precise diagnostic; the layer discarded it, constructed
  happily, and then trained forever without moving. The failure tolerance that
  belongs in the gradient sweep, where one bad point among 2P must not throw
  away the rest, had been applied to the single probe run that learns the
  outcome list, where an empty result means the layer is permanently dead. The
  service's own reason is now carried out in the exception.

## [0.8.0]

### Added
- Job and account management from code, so nothing needs the console.
  `pending()` lists every unfinished job, `jobs()` and `iter_jobs()` walk the
  job history newest first, `cancel(job_id)` asks the provider to cancel a
  hardware job that has not started, `summary()` returns jobs run per tier and
  net spend since the start of the month, `balance()` returns available credit,
  and `certificate(job_id)` issues a finished job's public certificate.
- `CancelRefused`, raised by `cancel()` carrying the service's reason when a job
  can no longer be cancelled. A cancelled job is refunded once the provider
  confirms it never ran.
- `estimate_solve()`, the price of a ground-state search before submitting it,
  with the same arguments as `submit_solve()`.

### Changed
- `Client()` reads `ZKSF_TOKEN` from the environment when no `token` is passed,
  as `qiskit-zksf` and `pennylane-zksf` already do. An explicit `token` wins.
- The credential to use is an API key, created in the console under Profile and
  valid for 30 days. It is passed exactly where a token was.

### Documentation
- The README engine table lists the two neural engines, names IonQ's current
  device (Forte Enterprise 1), and states the GPU engine's limit without
  describing how its jobs are placed. The certification table adds
  ZCC-Estimate-v0.2, the statement a mitigated value carries.
- Where to get a credential now points at API keys (Profile, Create API key) in
  the README and the Rydberg notebook, and the scope section describes the
  client as it now is rather than a 120-line wrapper of four endpoints.
- CITATION.cff carries the release version.

## [0.7.1]

### Fixed
- A submission that the service rejects now raises `JobRejected` carrying the
  service's own explanation, instead of surfacing as a bare
  `HTTPStatusError: 404 Not Found` several steps later.

  A submission-time rejection is not an HTTP error. It is a `200` carrying
  `{"id": ..., "status": "rejected", "reason": "33 qubits needs 128 GiB ..."}`.
  Every `submit_*` returned only the id and discarded the rest, so the caller
  went on to poll an id the service declines to serve, and the 404 from that
  poll was the first thing they saw. The reason was in their hands the whole
  time.

  This also makes the existing `JobRejected` branch in the polling loop
  reachable; for submission-time rejections it was dead code, because the poll
  raised before the status could be read.

  All seven submission methods route through one helper, so `submit`,
  `submit_batch`, `submit_solve`, `submit_mis`, `submit_parametric_sweep`,
  `submit_sequence` and `submit_photonic` behave identically and a new one
  cannot quietly opt out.

### Documentation
- The engine table listed fifteen of the seventeen engines: both neutral-atom
  processors, `qpu.quera.aquila` and `qpu.pasqal.fresnel`, were missing. A
  reader could learn that neutral-atom sequences simulate, and not that the same
  sequence runs on real hardware, which is an entire modality.

  Section 5.0 now shows the one-line change that sends a Pulser sequence to
  either processor, and states the two things that differ from the gate QPUs:
  Aquila runs only inside its published execution windows, and FRESNEL bills
  machine time rather than shots.
- `docs/CERTIFICATION.md` now states that ZHF-v0.1 is modality-agnostic and
  issues certificates for superconducting, trapped-ion, photonic and
  neutral-atom runs alike, each against its own exact local reference. It also
  names the consequence: past the reference engine's ceiling a run returns
  results and no certificate, and that limit belongs to the simulator rather
  than to the hardware.

## [0.7.0]

### Added
- `Client.solve(hamiltonian, qubits, ...)` and `Client.submit_solve(...)`: a
  ground-state problem rather than a program. The ansatz is named instead of
  sent, because OpenQASM 2 cannot express an unbound parameter, and the service
  runs the variational loop. Read `result["ground_state"]["ceiling"]` rather
  than `result["energy"]`: the variational principle puts the true ground state
  at or below the energy found, and the ceiling adds the simulation's own error
  bound to give a number the true answer cannot exceed. A run reports no
  ceiling when the engine reported no bound, rather than assuming one.
- `Client.run_mis(vertices, ...)` and `Client.submit_mis(...)`: maximum
  independent set on a neutral-atom register. Positions in micrometres, not a
  graph: an edge exists exactly where two atoms fall inside the blockade
  radius, so the geometry is the problem and the family that maps without a
  layout step is the unit-disk graphs. The answer arrives on `result["mis"]`
  with `valid_fraction`, the share of shots that obeyed every edge.

Both endpoints predate this release; neither had a client method, so the two
workloads shaped like what people actually want — give us a problem, get an
answer — were reachable only by hand-writing HTTP.

### Notes
- `verbatim=True` on `run`/`submit` asks a gate QPU to execute the circuit
  exactly as written rather than compiling it first, which is what
  hardware characterisation needs. It travels in `params`, so it has worked
  since params existed; it is documented now because the backend honours it.
  The circuit must already be in that device's native gates, and the provider
  rejects it unbilled otherwise.

## [0.6.0]

### Added
- `Client.run_parametric_sweep(program, bindings, ...)` and
  `Client.submit_parametric_sweep(...)`: one parameterised program plus a list
  of parameter dictionaries, evaluated as a single job. Pulser sequences declare
  their parameters with `declare_variable`, Perceval circuits with `pcvl.P`, and
  each binding is applied server-side.
- `qsim_sdk.ml`, with `PhotonicLayer` and `SequenceLayer`: a parameterised
  quantum program as a PyTorch `nn.Module`, so a circuit becomes a
  differentiable layer inside an ordinary training loop. `pip install
  qsim-sdk[ml]`, or bring your own torch; the base package does not carry it.
- `examples/06_train_a_photonic_circuit.py`, which trains a beamsplitter angle
  to the Hong-Ou-Mandel minimum and can be pointed at real hardware by changing
  one argument.

A single submission is rarely the workload. A variational solver, a quantum
kernel or a photonic generative model is one program evaluated hundreds or
thousands of times while an optimiser walks its parameters, and sent one job at
a time that is thousands of round trips and thousands of queue entries. A
500-point photonic step used to mean serialising 500 near-identical circuits on
every iteration; it is now one circuit and 500 small dictionaries.

Each bound point is re-serialised before it runs, so it hashes to its own value
and can carry its own certificate. Points that shared a circuit hash would make
every certificate in a sweep indistinguishable.

**Gradients are central differences, not the parameter-shift rule.** The shift
rule is exact only where an output is a sinusoid of the parameter, which holds
for a Pauli rotation in a gate circuit and does not hold for a beamsplitter
angle in an optical mesh or a pulse amplitude in an analog sequence. Central
differences cost the same two evaluations per parameter and are correct for
both; `eps` defaults to 0.01 and is worth raising when shot noise at your shot
count swamps the difference.

### Notes
- Sweeps run on simulation engines. Hardware is refused deliberately: each
  provider task is queued and billed individually, so batching to a QPU would
  hide the per-task cost behind one job id rather than save anything. Settle the
  sweep in simulation and send the surviving point to the machine.
- A binding that names a parameter the program does not declare is refused at
  submission. Left through, it would bind nothing and run the default point N
  times, which reads as a converged optimiser rather than a bug.

## [0.5.0]

### Added
- `Client.run_photonic(circuit, input_state, ...)` and
  `Client.submit_photonic(...)`: photonic linear-optics programs, run on the
  `photonic.slos.cpu` simulator or on Quandela Belenos. The service has accepted
  these since the photonic engines shipped, but only over raw HTTP, so the one
  modality that needed the SDK most was the one it could not reach.
- The input state accepts a `perceval.BasicState`, its serialised string, a bare
  `"|1,0,1>"`, or a plain occupation list `[1, 0, 1]`. Perceval is not a
  dependency of this package and the list form does not need it.

A photonic program is a circuit *and* an input Fock state. A gate circuit
carries its initial state implicitly and a Pulser sequence carries its register,
but a linear-optics circuit says nothing about how many photons enter or where,
so both halves are arguments and both are covered by the program hash. Two runs
that differ only in where the photons entered therefore cannot share a
certificate.

### Documentation
- README section 5.0.1 covers the photonic path, and the section 6 engine table
  gains `photonic.slos.cpu` and `qpu.quandela.belenos`.

### Notes
- An occupation list is tagged `:PCVL:BasicState:` before it is sent. Perceval's
  `deserialize()` returns any string it does not recognise unchanged, so an
  untagged `"|1,0,1>"` is not rejected on arrival: it reaches the engine as a
  `str` and fails several frames deep. The SDK tags it, and also tags a bare
  `"|1,0,1>"` you pass yourself.
- There is no `estimate()` counterpart yet, for the same reason sequences have
  none: the cost model reads gate-circuit features these programs do not have.

## [0.4.1]

### Documentation
- The engine table in section 6 listed nine engines and omitted four the service
  runs: `qpu.iqm.garnet`, `qpu.iqm.emerald`, `qpu.aqt.ibex` and
  `analog.pulser.cpu`. The IQM and AQT devices had been available for some time
  without appearing here. Constraints in the new rows are read from the service's
  device table rather than transcribed, so the quoted ceilings are the ones
  actually enforced.

No code changes. Released so the corrected README reaches PyPI, which renders it
from the published distribution rather than from the repository.

## [0.4.0]

### Fixed
- `Client.run(circuit)` was missing from the package. A `def run` had been
  indented one level too deep and ended up nested inside `counts()` after its
  return statement, so it parsed, it imported, and it simply was not a method.
  `client.run(circuit)` is the first example in this README and in the module
  docstring, so anyone following the quickstart hit `AttributeError`. Present
  and tested from this release.

### Added
- `run_sequence(sequence)` and `submit_sequence(sequence)` for neutral-atom
  analog work. A Pulser sequence is a register of atoms and a schedule of laser
  pulses rather than a circuit, so it has no gate decomposition and its own
  entry point. Pass a `pulser.Sequence` or its abstract representation as a
  JSON string; Pulser is not a dependency of this package.
- `ANALOG_ENGINE`, the default engine for those calls. Analog jobs always name
  their engine: routing inspects gate-circuit features, and a pulse schedule
  has none of them.

## [0.3.0]

### Added
- `run_sweep(circuit, bindings)`: one parameterized circuit at many parameter
  values, sent as a single request. VQE and QAOA are structurally sweeps, and
  gradient methods need two circuit evaluations per parameter per step, so sent
  one at a time a 20-parameter, 50-step run is 2,000 separate submissions.
  Measured against the service, a 20-point sweep runs an order of magnitude
  faster batched than issued one job at a time.
- `run_batch(circuits)` and `submit_batch(circuits)` for circuits that are not a
  parameter sweep. Binding happens client-side because OpenQASM 2 cannot carry
  an unbound parameter.
- `expectations(job)` and `counts(job)`: the results of a finished batch in
  submission order, with `None` where an evaluation returned no result, so the
  list still lines up with the values that were sent.

### Notes
- A batch does not raise when an individual circuit fails. A sweep's cost
  depends on the entanglement each parameter value produces rather than on the
  circuit's structure, so some bindings can exhaust memory while the rest
  succeed; an optimizer wants those reported as bad points, not as an exception
  that aborts the run. Read `job["summary"]` for the tally.
- Only the evaluations that returned a result are charged.

## [0.2.0]

### Added
- Public source repository. The client is now readable before a token is supplied.
- Optional `multiframework` extra: accepts Cirq, PennyLane, pyQuil, and Amazon Braket
  circuits by transpiling through qBraid into Qiskit.
- `Source`, `Issues`, and `Changelog` project URLs in package metadata.
- `docs/CERTIFICATION.md`: reference for ZCC-v0.1 and ZHF-v0.1, including stated
  assumptions and limitations.
- `examples/`: runnable scripts for estimation, certified simulation, and hardware.
- `CITATION.cff`, `CONTRIBUTING.md`, `SECURITY.md`.

### Changed
- Expanded PyPI keywords and trove classifiers.

## [0.1.0]

### Added
- Initial release: `Client` with `estimate`, `submit`, `job`, and `run`.
- `JobRejected` and `JobFailed` exceptions carrying the server-side reason.
- Automatic engine routing with explicit override via the `engine` argument.
