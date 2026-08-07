# Contributing

Thank you for considering a contribution.

## What this repository is

The **client library only**. Simulation engines, the routing policy, and certification
computation run server-side and are not part of this repository. Issues about engine
behaviour, pricing, or certificate contents are still welcome here, they will simply be
triaged rather than fixed by a pull request.

## Useful contributions

| Type | Notes |
|---|---|
| Bug reports | Include Python version, `qsim-sdk` version, Qiskit version, and a minimal circuit that reproduces |
| Framework compatibility | Failures converting Cirq, PennyLane, pyQuil, or Braket circuits |
| Documentation | Corrections and clarifications, particularly in `docs/CERTIFICATION.md` |
| Examples | Self-contained scripts that demonstrate a real workflow |
| Typing and ergonomics | The client is deliberately small, changes should keep it so |

## Reporting a bug

Open an issue with:

1. What you ran, as a minimal reproducible snippet
2. What you expected
3. What happened, including the full traceback
4. Versions: `python -V`, `pip show qsim-sdk qiskit`

Redact your API token. If a token has appeared in any output you are pasting, rotate
it in the console first.

## Pull requests

1. Open an issue first for anything beyond a small fix, so effort is not wasted
2. One logical change per pull request
3. Match the existing style: type hints, no dependencies added without discussion
4. Update `CHANGELOG.md` under "Unreleased"
5. Confirm the package imports and installs cleanly

The client has two runtime dependencies by design. Proposals that add a third should
explain why the functionality cannot live server-side or in an optional extra.

## Security issues

Do not open a public issue. See [`SECURITY.md`](SECURITY.md).

## Code of conduct

Be civil and assume good faith. Technical disagreement is welcome, personal remarks
are not. Maintainers may close or lock threads that stop being productive.

## License

Contributions are accepted under the MIT license of this repository.
