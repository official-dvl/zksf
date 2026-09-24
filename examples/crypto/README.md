# Elliptic-curve key recovery with Shor's algorithm

`ecdlp_gpu.py` recovers a private key from its public key on a real elliptic
curve, building the circuit from public data only. It reproduces the key
recoveries on [zksf.org/applications/cryptography](https://zksf.org/applications/cryptography/).

```bash
pip install qsim-sdk
export ZKSF_API_TOKEN=...          # console: Profile > Create API key
python ecdlp_gpu.py                # 7-bit key on exact.gpu
python ecdlp_gpu.py 5 exact.cpu    # any size from 3 bits, any engine
```

The script prices the run with `client.estimate()` before submitting it.

| Key | Qubits | Two-qubit gates | Engine | Result |
|---|---|---|---|---|
| 7 bits | 21 | 163,192 | `exact.gpu` | secret 67 recovered from 24 usable shots of 64, 66 s |

Everything is fixed, so the run is reproducible: the curve is the first cyclic
curve of order 2^n that `ecdlp_curves.find_cyclic_curve` finds, and the secret
is `order // 2 + 3`, made odd. Only the 64 shots vary, and any usable shot
points at the same key.

`permutation.py` builds each "add a curve point" step as a permutation of basis
states rather than as a dense unitary, which is what lets 7 and 8 bits build in
seconds. `ecdlp_curves.py` is the curve arithmetic.
