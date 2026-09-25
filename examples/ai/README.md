# AI on ZKSF: the scripts behind the published results

Every AI case under [zksf.org/applications/ai-quantum-computing](https://zksf.org/applications/ai-quantum-computing/)
was produced by a script in this folder. The raw results and the saved weights
are here too, so a published number can be checked against the file it came from.

## Setup

```bash
pip install "qsim-sdk[ml]" scikit-learn perceval-quandela
export ZKSF_API_TOKEN=...     # console: Profile > Create API key
```

The scripts submit real jobs to your account. Price anything first with
`client.estimate()` or `client.estimate_batch()`: the SDK never does it for you.

## What each script reproduces

| Case | Command | Circuits | Cost | Published |
|---|---|---|---|---|
| Reservoir computing, local observables | `python ai_proofs.py reservoir_local` | 200 | $0.0200 | 0.817 |
| Reservoir computing, bitstring readout | `python ai_proofs.py reservoir` | 200 | $0.0200 | 0.783 |
| QCBM, a generative model | `python ai_proofs.py qcbm` | 806 | $0.0806 | TVD 0.459 to 0.0117 |
| QGAN, gate circuit | `python ai_proofs.py qgan` | 722 | $0.0722 | TVD 0.269 to 0.146 |
| Quantum RL policy | `python ai_proofs.py rl_policy` | 540 | $0.0540 | 0.611 against 0.533 random |
| Patch GAN image generation | `python ai_proofs.py patch_gan` | 3,224 | $0.3224 | the 8x8 cross |
| Variational classifier, seed 1, 2 or 3, exact | `python variational_classifier.py 1` | 4,000 | $0.4000 | 0.925 / 0.850 / 0.700 |
| Variational classifier, 1,024 shots | `python variational_classifier.py 1 --shots 1024` | 4,000 | $0.4000 | 0.925 / 0.825 / 0.700 |
| Variational classifier, exact, on your machine | `python variational_classifier.py 1 --local` | none | free | 0.925 / 0.850 / 0.700 |
| Quantum kernel SVM, seed 1, 2 or 3 | `python quantum_kernel.py 1` | 1,111 | $0.1111 | 0.675 / 0.750 / 0.750 |
| Quantum kernel, exact | `python quantum_kernel.py 1 --exact` | 1,111 | $0.1111 | 0.675 / 0.750 / 0.750 |
| Quantum kernel, exact, on your machine, plus the scaling sweep | `python kernel_control.py` | none | free | 0.675 / 0.750 / 0.750 |
| Photonic QGAN, five seeded starts | `python photonic_qgan.py` | see script | $0.1096 | see below |
| Photonic QGAN on Quandela Belenos | `python photonic_belenos.py` | 2 runs | $0.4584 a run | P(target) 0.974 |

Costs are what the published runs were charged. Every simulator circuit here is
charged the $0.0001 floor.

## What "reproduce" means here

- **Shots are sampled fresh on every run.** A rerun lands close to a published
  number, not on its last decimal. `exact.cpu` and `exact.gpu` compute the same
  distribution, so either tier reproduces a simulator row.
- **The gate training runs in `ai_proofs.py` were not seeded when the published
  numbers were produced.** The script seeds itself now (`SEED = 0`), so two of
  your runs start alike, but no seed recreates the published trajectory exactly.
- **The photonic QGAN is seeded per start.** `torch.manual_seed(0)` to `(4)` fix
  each start's initial angles. Seeds 0 to 4 gave P(target) 0.875, 1.000, 0.989,
  0.932 and 0.766 (`photonic_qgan_results.json`).
- **The classifier and the kernel share one seeded dataset** (`two_moons.py`).
  `default_rng(seed)` draws 22 training points, then 40 test points, then the
  classifier's four starting angles; features are scaled into [0, pi] on the
  training range. The classical baselines are seeded from `default_rng(seed)` too.
- **Exact mode reproduces to the digit.** `variational_classifier.py` without
  `--shots`, and `quantum_kernel.py --exact`, send an observable, so `exact.cpu`
  computes each value from the statevector instead of sampling it. Nothing random
  is left, and `--local` / `kernel_control.py` do the same arithmetic on your
  machine. The shot-based figures (classifier at 1,024 shots, kernel at 2,048)
  re-run to within shot noise; on the kernel the sampled and exact accuracies
  were equal on all three seeds.

## The hardware rows

The QCBM, QGAN and RL hardware rows ran circuits whose weights are saved here, so
you can submit the same circuit to the same device:

- `qcbm_weights.json`: the QCBM circuit sent to Rigetti and IQM Garnet
- `hw_proofs_results.json`: the QGAN generator weights (`qgan.weights`), the RL
  policy weights (`rl_policy.weights`), and each device's measured distribution
- `patchgan_weights.json`: the four patch generators

The QGAN hardware rows ran a second training of the same model; its converged
circuit was run on each device to compare outputs. Those are the weights in
`hw_proofs_results.json`, not the end of the training run in
`ai_proofs_results.json`.

Batches run on simulation engines only. A hardware engine takes one circuit per
job, so send each saved circuit on its own with `client.run(...)`.
