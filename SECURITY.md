# Security policy

## Reporting a vulnerability

Please report security issues privately to **info@zksf.org**. Do not open a public
GitHub issue for a security report.

Include where practical: affected component, reproduction steps, observed impact, and
any proof-of-concept material. We acknowledge reports within three business days.

## Scope

| In scope | Out of scope |
|---|---|
| This client library | Third-party dependencies (report upstream) |
| The public API at `api.zksf.org` | Denial of service or volumetric testing |
| Certificate verification endpoints | Social engineering of staff or users |
| Token handling and authentication | Findings from automated scanners without a demonstrated impact |

Do not conduct load testing, resource exhaustion testing, or any activity that would
degrade service for other users.

## API token handling

Tokens issued by <https://app.zksf.org> authorise billable operations. Users should:

- Supply the token through an environment variable, never a committed literal
- Rotate any token that has been exposed, including in a notebook output, a screenshot,
  or a support thread
- Use a separate token per environment so that revocation is narrowly scoped

The client transmits the token only as an `Authorization: Bearer` header to the
configured `base_url`, which defaults to `https://api.zksf.org`. This is verifiable in
`qsim_sdk/__init__.py`, which is the reason this client is published as source.

## Certificate integrity

Certificate pages are served without authentication so that third parties can verify
results. They are designed to carry no personally identifying information about the
account that produced the run. If you observe identifying data on a certificate page,
treat it as a security issue and report it through the address above.
