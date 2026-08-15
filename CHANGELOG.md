# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
