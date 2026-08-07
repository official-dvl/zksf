# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
