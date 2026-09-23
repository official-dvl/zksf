"""The hardware leg: the converged generator, submitted to Quandela Belenos.

SHOT COUNT IS THE WHOLE DESIGN DECISION HERE. Belenos bills EUR 0.30 a job
whatever the sample count, so 100,000 shots costs $0.4584 against $0.3449 for
1,000: eleven cents for a hundred times the statistics. That matters more on a
photonic device than anywhere else on the platform, because detection is
heralded and most attempts never yield a surviving photon pair. The 7 Sep
Hong-Ou-Mandel run recorded 241 usable coincidences out of 10,000 attempts, so a
1,000-shot run would have measured roughly two dozen events and could not
separate device error from sampling error at all.

Two runs rather than one, for $0.92 of a $3.50 ceiling. The second is not a
better number, it is the only way to say whether the first is repeatable, and no
other row in this table can say that.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

import perceval as pcvl

HERE = pathlib.Path(__file__).parent
API = "https://api.zksf.org"
SHOTS = 100_000
RUNS = 2
OUTCOMES = ["|2,0,0>", "|1,1,0>", "|1,0,1>", "|0,2,0>", "|0,1,1>", "|0,0,2>"]
TARGET = {"|2,0,0>": 0.4, "|1,1,0>": 0.1, "|0,1,1>": 0.1, "|0,0,2>": 0.4}

# From the environment, so this file carries no path to a secrets store and can
# therefore live in the repo. The experiment this one replaced was lost because
# it never did.
token = os.environ.get("ZKSF_API_TOKEN")
if not token:
    raise SystemExit("set ZKSF_API_TOKEN to an API key from the console (Profile -> API keys)")
H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def call(path: str, payload: dict | None = None, method: str | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, headers=H, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=180))
    except urllib.error.HTTPError as e:
        return {"_err": f"{e.code} {e.read().decode()[:300]}"}


def tvd(p: dict[str, float]) -> float:
    keys = set(p) | set(TARGET)
    return 0.5 * sum(abs(p.get(k, 0.0) - TARGET.get(k, 0.0)) for k in keys)


def photons(state: str) -> int:
    return sum(int(x) for x in state.strip("|>").split(","))


def coincidences(counts: dict[str, int]) -> dict[str, int]:
    """Two-photon detections only.

    POST-SELECTION IS NOT OPTIONAL HERE, and reading the raw counts instead is
    the mistake this function exists to prevent. Detection is heralded: most
    attempts lose a photon on the way and land in a one-photon state, so the
    raw distribution measures the transmission of the device rather than
    anything the generator learned. Measured 21 Sep 2026: 2,686 two-photon
    events in 100,000 attempts, 2.69%, against 241 in 10,000 on the 7 Sep
    Hong-Ou-Mandel run. Scored raw, a perfectly trained circuit would post a
    TVD near 0.97 and the number would be about the loss.
    """
    return {k: v for k, v in counts.items() if photons(k) == 2}


def main() -> None:
    res = json.loads((HERE / "photonic_qgan_results.json").read_text(encoding="utf8"))
    w = res["best_weights"]
    print(f"converged weights from seed {res['best_seed']}: {[round(x, 4) for x in w]}")

    circuit = (
        pcvl.Circuit(3)
        // (0, pcvl.BS(theta=w[0]))
        // (1, pcvl.BS(theta=w[1]))
        // (0, pcvl.BS(theta=w[2]))
    )
    program = json.dumps({
        "circuit": pcvl.serialization.serialize(circuit),
        "input": pcvl.serialization.serialize(pcvl.BasicState([1, 0, 1])),
    })

    quote = call("/estimate", {"photonic": program, "shots": SHOTS,
                               "engine": "qpu.quandela.belenos", "params": {}})
    if "_err" in quote:
        sys.exit(f"estimate failed: {quote['_err']}")
    each = quote["predicted_cost_usd"]
    print(f"quote: ${each:.4f} per run, {RUNS} runs = ${each * RUNS:.4f}")
    if each * RUNS > 3.50:
        sys.exit("over the authorised ceiling, stopping")

    out = []
    for i in range(RUNS):
        j = call("/jobs", {"photonic": program, "shots": SHOTS,
                           "engine": "qpu.quandela.belenos", "params": {}})
        if "_err" in j:
            print(f"  run {i + 1}: SUBMIT FAILED {j['_err']}")
            continue
        jid = j["id"]
        print(f"  run {i + 1}: job {jid} submitted", flush=True)
        while j.get("status") not in ("done", "failed", "error", "cancelled"):
            time.sleep(5)
            j = call(f"/jobs/{jid}")
        charged = (j.get("charged_micro") or 0) / 1e6
        counts = (j.get("result") or {}).get("counts") or {}
        attempts = sum(counts.values()) or 1
        two = coincidences(counts)
        detected = sum(two.values()) or 1
        probs = {k: v / detected for k, v in two.items()}
        cert = call(f"/jobs/{jid}/certificate", {}, method="POST")
        rec = {
            "job_id": jid, "status": j.get("status"), "charged_usd": charged,
            "shots": SHOTS, "counts": counts,
            "attempts": attempts, "coincidences": detected,
            "heralding_rate": round(detected / attempts, 5),
            "probs": {k: round(v, 4) for k, v in probs.items()},
            "tvd": round(tvd(probs), 4),
            "p_target": round(sum(probs.get(k, 0.0) for k in TARGET), 4),
            "cert": cert.get("cert_id"),
        }
        out.append(rec)
        print(f"     {j.get('status')}  ${charged:.4f}  {detected} coincidences in "
              f"{attempts} attempts ({100 * detected / attempts:.2f}%)  "
              f"TVD {rec['tvd']}  P(target) {rec['p_target']}  cert {rec['cert']}")

    (HERE / "photonic_belenos_results.json").write_text(json.dumps(out, indent=1), encoding="utf8")
    if out:
        print("\nTVD across runs:", [r["tvd"] for r in out])
        print("P(target) across runs:", [r["p_target"] for r in out])
        print(f"total charged: ${sum(r['charged_usd'] for r in out):.4f}")


if __name__ == "__main__":
    main()
