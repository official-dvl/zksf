# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
