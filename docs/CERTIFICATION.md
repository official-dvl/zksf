# Certification protocols: ZCC-v0.1, ZHF-v0.1 and ZQEC-v0.1

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
per-outcome bound assumes truncation errors accumulate incoherently; see section 6.4
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
under the assumptions in section 6. The full certificate is public at
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

The protocol is modality-agnostic: Hellinger fidelity needs counts, an exact reference
and a hashable program, and every processor here supplies all three. So certificates are
issued for superconducting, trapped-ion, photonic and neutral-atom runs alike, each
compared against its own exact local engine, and a neutral-atom sequence is compared
against `analog.pulser.cpu` rather than against a gate simulator.

That reference is also the ceiling. A neutral-atom run wider than 14 atoms, or a photonic
program past 12 modes, returns results and **no certificate**, because nothing can
compute the distribution to compare it against. The limit belongs to the simulator, not
to the hardware, which is why the processors accept far more than the certifiable range.

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

## 4. ZQEC-v0.1: certification of a logical error rate

**Applies to:** quantum error correction memory experiments.

**Asserts:** the logical error rate measured for a stated code, distance, round
count and noise model, **with a two-sided 95% confidence interval**.

The other two protocols answer "how far from ideal is this result". This one answers a
different question, and the one every fault-tolerance roadmap is quoted in: how well
does a code hold a logical qubit, and therefore how many physical qubits does one
logical qubit cost at a given physical error rate.

### 4.1 The interval is the assertion

A logical error rate is a proportion estimated from a finite number of shots. Reporting
`errors / shots` alone is the failure this whole document exists to refuse: at 100,000
shots with no failures that quotient is exactly 0, and no finite experiment can
establish that a code never fails.

The certificate therefore carries a **Wilson score interval**, not the point estimate
alone. Wilson's interval is derived from the score test rather than from a normal
approximation, so it remains correct at zero successes and at small counts, where
`p +/- z*sqrt(p(1-p)/n)` collapses to `[0, 0]`.

**The upper bound is the number to quote.** A result of "0.0 logical error rate" is not
a claim this protocol makes; "below 3.69e-05 at 95% confidence, over 100,000 shots" is.

### 4.2 What is certified, and what is assumed

Certified: the decoded outcome of the stated circuit under the stated noise model,
counted over the stated number of shots.

Assumed, and recorded on the certificate so the assumption is inspectable:

1. **The noise model is circuit-level depolarizing** at the stated rate, which is the
   model published logical error rates are quoted against. It is not a model of any
   named vendor's device, and a rate measured here does not transfer to hardware whose
   errors are correlated, leaky or drifting.
2. **The decoder is minimum-weight perfect matching.** A logical error rate is a
   property of a code *and its decoder*. A better decoder on the same data returns a
   lower rate, so the decoder is part of the claim rather than an implementation
   detail.
3. **Memory only.** Prepare a logical state, hold it for the stated rounds, read it
   out. No logical gates, no lattice surgery, no magic state distillation, so a rate
   here does not bound the error of a computation performed on that qubit.

### 4.3 Codes, and the ones that are refused

Certified: the rotated surface code in Z and in X, the unrotated surface code, and the
repetition code.

**Colour codes and qLDPC codes are refused rather than decoded.** Their errors do not
decompose into pairs of detectors, so matching is the wrong decoder for them, and a
wrong decoder does not fail: it returns a plausible number in the right range that
happens to be worse than the code's true performance. A refusal is the only honest
output available.

Circuits are generated by `stim.Circuit.generated`, the reference implementations the
field checks against, rather than written here. A hand-rolled syndrome extraction
circuit that is subtly wrong still runs, still decodes, and still yields a confident
number.

### 4.4 The subject hash excludes the shot count

`circuit_sha256` covers the code, the distance, the rounds, the physical error rate and
the measurement error rate. `hash_subject` reads **"Code and noise model"**.

It deliberately does **not** cover the number of shots. Two runs of the same experiment
at different shot counts are the same experiment measured to different precision, and
they hash the same, so a reader can see at a glance that a narrower interval came from
more shots rather than from a different setup.

### 4.5 Worked example

A distance-5 rotated surface code at a physical error rate of 0.1%, held for 5 rounds:

```
Engine                  : exact.cpu
Protocol                : ZQEC-v0.1
Certificate type        : Logical Error Rate
Code                    : surface (rotated, Z memory)
Distance                : 5
Rounds                  : 5
Physical error rate     : 0.001
Decoder                 : minimum-weight perfect matching (pymatching)
Detectors               : 120
Shots                   : 20000
Logical errors          : 4
Logical error rate      : 0.0002
95% confidence interval : [7.778e-05, 5.142e-04]
Hash subject            : Code and noise model
```

Live at `https://api.zksf.org/certify/b358005dc6724273`, readable without an account
like every other certificate here.

Four failures in twenty thousand shots is why the interval spans a factor of about
seven. That is the honest width at this sample size, and it is the reason the interval
rather than `0.0002` is the number the protocol asserts.

### 4.6 Suppression, and what is measured versus extrapolated

Several certified runs at different distances determine a **suppression factor**: how
much each two steps of code distance divide the logical error rate at a given physical
error rate. From it follow the distance and the physical qubit count that reach a
target logical error rate.

Those answers carry a `basis` field stating which half was measured and which was
extrapolated along the measured slope. A distance that produced no failures is
**excluded from the fit** rather than replaced by its confidence bound, because
substituting a bound for a missing measurement converts a measurement into an
assumption silently. A fit with one usable point is refused: a slope needs two.

At or above the code's threshold, where the suppression factor is at or below 1, the
answer is that **no number of physical qubits reaches the target** until the physical
error rate falls. That is a result, not an error condition.

Physical qubit counts are the qubits the generated circuit operates on. They are not
`stim.Circuit.generated(...).num_qubits`, which is the largest qubit index plus one: a
rotated surface code is laid out on a coordinate grid whose corners are never used, so
that field reports 26 for a distance-3 code that touches 17. A rotated code of distance
`d` uses `2d^2 - 1` physical qubits and an unrotated one `(2d-1)^2`.

## 5. Certificate lifecycle and independent verification

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

## 6. Assumptions and limitations

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
8. **A logical error rate is a property of a code AND its decoder**, measured under a
   stated noise model. A ZQEC-v0.1 figure does not transfer to hardware whose errors
   are correlated, leaky or drifting, and it bounds memory rather than computation:
   no logical gate has been performed on that qubit.
9. **Version 0.1 is not frozen.** Protocol identifiers pin the version deliberately.
   Specifications below 1.0 may change, and certificates remain interpretable because
   the version travels with them.

## 7. Rejection as a design property

A circuit whose result could not be certified to a useful degree is rejected before
execution, and the client raises `qsim_sdk.JobRejected` carrying the reason and the
change that would make the job feasible.

This is intentional. Returning a result with a vacuous error bar is worse than
returning no result, because the former is indistinguishable from a useful one at a
glance.

## 8. References

- Protocol specification and benchmarks: <https://zksf.org/blog/quantum-error-bars/>
- Engine selection guidance: <https://zksf.org/blog/cpu-gpu-qpu-when-to-use/>
- Tensor network background: <https://zksf.org/blog/tensor-networks-explained/>
- The exact-simulation boundary: <https://zksf.org/blog/the-34-qubit-wall/>
