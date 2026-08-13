# Certification protocols: ZCC-v0.1 and ZHF-v0.1

This document describes what ZKSF certificates assert, how they are produced, and
what they do not claim. It is a reference for users of `qsim-sdk`. The normative
specification is maintained at <https://zksf.org/blog/quantum-error-bars/>.

---

## 1. Problem statement

Beyond roughly 30 qubits, exact statevector simulation is infeasible: the state vector
requires `2^n` complex amplitudes, so each added qubit doubles memory. Every method
that operates past that boundary is approximate, and each introduces error through a
different mechanism:

| Method | Approximation | Error source |
|---|---|---|
| Matrix product state (MPS) | Bond dimension truncation | Discarded Schmidt weight |
| Pauli propagation | Operator weight truncation | Dropped Pauli terms |
| Real quantum hardware | None, but the device is noisy | Gate error, decoherence, readout error |

A returned distribution therefore carries an unstated distance from the ideal
distribution. The protocols below make that distance explicit and, critically, make it
checkable by someone who did not perform the run.

## 2. ZCC-v0.1: certification of simulated results

**Applies to:** results produced by classical simulation engines, specifically
`exact.cpu`, `exact.gpu`, `clifford`, `mps.quimb.cpu`, `mps.aer.cpu`, and `pauli.cpu`.

**Does not apply to:** `noisy.cpu`. See section 2.4.

**Asserts:** a bound on the deviation of the returned distribution from the
distribution that an exact simulation of the same circuit would have produced.

### 2.1 Modes

ZCC-v0.1 operates in two modes, and the mode is recorded on the certificate.

**Default mode (convergence check).** A fast diagnostic run at more than one
approximation setting. Agreement between settings is evidence of convergence. This is
a diagnostic, not a proof, and the certificate records it as such.

**Certified mode (measured bound).** Opted into per job. On the MPS engine, the
discarded Schmidt weight accumulated across truncations is tracked during the
contraction and converted into a single-run bound on the output distribution. The
discarded weight is measured within the run rather than estimated or extrapolated,
and each individual truncation is optimal by Eckart-Young. The conversion to a
per-outcome bound assumes truncation errors accumulate incoherently; see section 5.4
for the worst case and for the measurements showing that assumption failing in deep
circuits, which is why this is stated as an empirically supported bound rather than a
proof.

### 2.2 Worked example

A 24-qubit QAOA MaxCut ring at `p=3` on `mps.quimb.cpu` with `certified=true` and
`max_bond=48`, a setting at which the bond cap binds and truncation genuinely
discards weight:

```
Engine           : mps.quimb.cpu
Protocol         : ZCC-v0.1
Mode             : certified (measured single-run truncation bound)
Discarded weight : 5.617e-09
Error bound      : 1.06e-04
```

The bound of `1.06e-04` is the quantity to reason about. It states that each returned
outcome probability lies within that distance of the exact value for this circuit,
under the assumptions in section 5. The full certificate is public at
<https://api.zksf.org/certify/3d409b6562194a2e>.

A circuit the simulator can represent exactly reports a discarded weight at or near
machine precision, which certifies an exact computation rather than demonstrating the
bound. The example above is chosen deliberately so the bound is doing real work.

### 2.3 Engine coverage

| Engine | ZCC-v0.1 | Strongest available statement |
|---|---|---|
| `exact.cpu` | Yes | Exact, no approximation error |
| `exact.gpu` | Yes | Exact, no approximation error |
| `clifford` | Yes | Exact within the stabilizer formalism |
| `mps.quimb.cpu` | Yes | Rigorous single-run truncation bound in certified mode |
| `mps.aer.cpu` | Yes | Convergence diagnostic |
| `pauli.cpu` | Yes | Convergence diagnostic on truncated operator weight |
| `noisy.cpu` | **No** | Not applicable, see below |

### 2.4 Why noise-preview runs are not certified

The `noisy.cpu` engine applies a device noise model, superconducting by default, with
optional zero-noise error mitigation. Its output deliberately approximates the
behaviour of a noisy physical machine rather than the ideal distribution.

ZCC-v0.1 bounds the distance between a returned distribution and the exact one. For a
noise-preview run that distance is not an error, it is the intended result. Certifying
it would be a category mistake, so no certificate is issued for these runs.

Use `noisy.cpu` to anticipate how a circuit will behave on hardware. Use `qpu.rigetti`
or `qpu.ionq` with ZHF-v0.1 when a measured, certifiable fidelity is required.

## 3. ZHF-v0.1: certification of hardware results

**Applies to:** results returned by real quantum processors.

**Asserts:** a measured fidelity of the hardware output against the exact ideal
distribution for the same circuit.

Hardware does not approximate, it is noisy. There is no truncation parameter to bound.
The meaningful question is therefore not "how far might this be from ideal" but "how
far is it, measured". ZHF-v0.1 answers the latter.

### 3.1 Direct verification mode

Where a reference distribution is obtainable, the hardware counts are compared against
it and the **Hellinger fidelity** is reported. This constrains direct mode to circuit
sizes for which a reference can be computed.

### 3.2 Worked example

A 2-qubit Bell state on `qpu.ionq` (IonQ Forte-1):

```
Engine              : qpu.ionq
Device              : IonQ Forte-1
Protocol            : ZHF-v0.1
Verification mode   : direct
Counts              : {"00": 54, "11": 44, "01": 2}
Hellinger fidelity  : 0.9774
```

The `01` counts are the observable signature of device noise: an ideal Bell state
produces only `00` and `11`.

## 4. Certificate lifecycle and independent verification

A certificate is minted from a completed job and receives a stable identifier.

```
POST https://api.zksf.org/jobs/<job_id>/certificate
     -> { cert_id, protocol, verify_url, download_url }
```

It is then retrievable **without authentication**, which is the property that makes it
useful as evidence:

```
GET https://api.zksf.org/certify/<cert_id>        # HTML verification page
GET https://api.zksf.org/certify/<cert_id>/json   # the record itself, as JSON
GET https://api.zksf.org/certify/<cert_id>/pdf    # PDF
```

The HTML page and the PDF are renderings; the JSON is the record they are rendered
from. It is the form to read when a certificate is being checked by a program rather
than by a person, and it is what an independent validator should consume.

Each certificate records the engine, method, shot count, device where applicable, the
protocol and version, the verification mode, and the reported bound or fidelity. Every
certificate includes a section stating how that specific result was produced. No
certificate is issued without one.

Certificate pages carry no personally identifying information about the account that
performed the run.

## 5. Assumptions and limitations

Declared explicitly. A certification claim is only as credible as its stated boundary.

1. **Circuit correctness is out of scope.** A bound describes the fidelity of the
   simulation to the submitted circuit. It says nothing about whether the submitted
   circuit expresses the intended computation.
2. **Shot noise is separate.** Finite sampling error is reported independently of the
   approximation bound and is not folded into it.
3. **Certified mode is engine-dependent.** Single-run measured bounds are available on
   the quimb MPS engine. Other engines report convergence diagnostics, which do not
   carry the same force, and `noisy.cpu` is outside the protocol entirely.
4. **The MPS bound assumes incoherent accumulation, and that assumption can fail.**
   Writing eps for the total discarded weight, the reported per-outcome bound is
   sqrt(2*eps). Each individual truncation is optimal by Eckart-Young and eps is
   measured exactly, but across N sequential truncations the adversarial accumulation
   is the sum of sqrt(eps_i), which can exceed sqrt(2*sum_i eps_i) by a factor of up
   to sqrt(N/2). We have measured deep circuits in which eps understates the true
   infidelity by a factor of 7, so the condition is not always met and the bound does
   not follow from that derivation alone. Pauli propagation does not share this
   caveat: its bound is an additive triangle inequality over discarded coefficient
   mass. Where a hard ceiling is required, use an exact or stabilizer engine.
5. **The per-outcome bound is an empirical result.** It was never exceeded across 334
   runs checked against exact simulation, 290 of them constructed specifically to
   falsify it, approaching at closest 49% of its value. Verification requires an exact
   reference, so those checks reach 20 qubits while the engine is used well beyond
   that size. No direct evidence about the bound exists above 20 qubits, and none is
   obtainable by this method.
6. **Hardware fidelity is not predictive.** A ZHF-v0.1 figure characterises one
   execution on one device at one time. Queue position, calibration drift, and
   ambient conditions all move it. It is a record, not a forecast.
7. **Direct verification requires a reference.** Where no reference distribution is
   obtainable, direct mode is unavailable.
8. **Version 0.1 is not frozen.** Protocol identifiers pin the version deliberately.
   Specifications below 1.0 may change, and certificates remain interpretable because
   the version travels with them.

## 6. Rejection as a design property

A circuit whose result could not be certified to a useful degree is rejected before
execution, and the client raises `qsim_sdk.JobRejected` carrying the reason and the
change that would make the job feasible.

This is intentional. Returning a result with a vacuous error bar is worse than
returning no result, because the former is indistinguishable from a useful one at a
glance.

## 7. References

- Protocol specification and benchmarks: <https://zksf.org/blog/quantum-error-bars/>
- Engine selection guidance: <https://zksf.org/blog/cpu-gpu-qpu-when-to-use/>
- Tensor network background: <https://zksf.org/blog/tensor-networks-explained/>
- The exact-simulation boundary: <https://zksf.org/blog/the-34-qubit-wall/>
