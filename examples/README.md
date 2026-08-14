# Examples

Seven notebooks and four scripts. Every notebook opens in Colab with nothing installed,
and in each one the part that builds a circuit and reads a published certificate needs no
account and costs nothing. Running a new job is opt-in at the end of each notebook, and
priced with a free `estimate()` call first.

## Start here

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/quickstart.ipynb)
&nbsp;**[quickstart.ipynb](quickstart.ipynb)**

Reads four real completed runs straight from the public API: an exact stabilizer
simulation, an approximate run carrying a measured error bound of 2.11e-08, a 192-qubit
Pauli propagation result, and a Bell state executed on IonQ Forte-1 hardware at 0.977
fidelity. Four accuracy regimes, side by side, none of them simulated for the occasion.

## Algorithm tutorials

Each notebook builds the circuit in Qiskit, then reads the certificate for the run that
produced the published result, so the number in the article is the number you see.

| Notebook | What it covers | Written up |
|---|---|---|
| [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/ghz-bell-state.ipynb) [ghz-bell-state](tutorials/ghz-bell-state.ipynb) | Entanglement: three qubits that always agree | [Article](https://zksf.org/blog/quantum-entanglement-ghz-bell-state/) |
| [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/grover-search.ipynb) [grover-search](tutorials/grover-search.ipynb) | Amplitude amplification, exact at this size | [Article](https://zksf.org/blog/grover-search-algorithm-tutorial/) |
| [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/qaoa-maxcut.ipynb) [qaoa-maxcut](tutorials/qaoa-maxcut.ipynb) | Combinatorial optimization on a four-node ring | [Article](https://zksf.org/blog/qaoa-maxcut-optimization-tutorial/) |
| [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/vqe-h2.ipynb) [vqe-h2](tutorials/vqe-h2.ipynb) | Ground-state energy of H2, via an observable | [Article](https://zksf.org/blog/vqe-h2-molecule-ground-state/) |
| [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/bernstein-vazirani.ipynb) [bernstein-vazirani](tutorials/bernstein-vazirani.ipynb) | A hidden bitstring recovered in one query | [Article](https://zksf.org/blog/bernstein-vazirani-algorithm/) |
| [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/official-dvl/zksf/blob/main/examples/tutorials/quantum-teleportation.ipynb) [quantum-teleportation](tutorials/quantum-teleportation.ipynb) | Moving a state using entanglement alone | [Article](https://zksf.org/blog/quantum-teleportation-circuit/) |

## Scripts

Plain Python, no notebook. These need a token in `ZKSF_TOKEN`.

| Script | What it shows |
|---|---|
| [01_bell_state.py](01_bell_state.py) | The shortest path from a Qiskit circuit to a result |
| [02_estimate_first.py](02_estimate_first.py) | Pricing a job before running it, and refusing it over budget |
| [03_certified_bound.py](03_certified_bound.py) | Requesting a measured ZCC-v0.1 bound with `certified=True` |
| [04_real_hardware.py](04_real_hardware.py) | Submitting to a real quantum processor |

## Checking a result you did not produce

Every certificate referenced above is public and unauthenticated. Anyone can check one
without an account, and without going through this service at all:

```bash
pip install zcc-verify
zcc-verify fe529e21d7404ff3
```

`zcc-verify` recomputes the declared bound from the measurement the certificate reports
and requires the two to agree. It establishes that a certificate is well formed and
self-consistent, which is not the same as establishing that the measurement was honestly
made. See [zksf-zcc-verify](https://github.com/official-dvl/zksf-zcc-verify).

## Related

- [Certification](https://zksf.org/quantum-computing-certification/), and the
  [specification paper](https://doi.org/10.5281/zenodo.21851381)
- [Documentation](https://zksf.org/docs/)
- [qiskit-zksf](https://pypi.org/project/qiskit-zksf/), to run existing Qiskit programs
  on these engines by naming a different backend
