"""Run a trained tagger over the benchmark (and external sets) for `pnpm bench` / `pnpm rbench`.

    uv run --extra train python py/predict.py <name> [--ext] [--thr high=0.5,medium=0.3,low=0.6]

Writes .cache/preds/model-<name>/<set>.jsonl (or .cache/ext-preds/... with --ext), UTF-16 offsets.
Thresholds follow PLAN.md: medium-risk uses a low threshold (highlight for the user to confirm),
low-risk a high one (hint only).
"""

import argparse
import json
import time

import numpy as np
import torch

from common import BENCH, EXT, ROOT, read_jsonl, write_jsonl
from model import Tagger, bucketize, decode, encode, features

MODELS = ROOT / ".cache" / "models"
CHUNK, OVERLAP = 2048, 64


@torch.no_grad()
def probs_for(model, units: np.ndarray, buckets: int, dev) -> np.ndarray:
    """Softmax tag probabilities for every code unit; long texts run in overlapping chunks."""
    f_all = bucketize(features(units), buckets)
    n = len(units)
    out = np.zeros((n, model.out.out_features), np.float32)
    s = 0
    while s < n:
        lo, hi = max(0, s - OVERLAP), min(n, s + CHUNK + OVERLAP)
        p = torch.softmax(model(torch.from_numpy(f_all[lo:hi])[None].to(dev)), -1)[0].cpu().numpy()
        out[s:min(n, s + CHUNK)] = p[s - lo:s - lo + min(CHUNK, n - s)]
        s += CHUNK
    return out


def load(name, dev):
    cfg = json.loads((MODELS / name / "config.json").read_text())
    m = Tagger(cfg["buckets"], cfg["emb"], cfg["hidden"], cfg["dilations"], cfg.get("sep", False))
    m.load_state_dict(torch.load(MODELS / name / "model.pt", map_location="cpu"))
    m.qat_emb_bits = 4 if cfg.get("qat4") else 0  # QAT models are evaluated as they ship
    return m.to(dev).eval(), cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--ext", action="store_true")
    ap.add_argument("--thr", default="", help="high=..,medium=..,low=..; default: thresholds.json from py/tune.py, else 0.5/0.3/0.6")
    a = ap.parse_args()
    tuned = MODELS / a.name / "thresholds.json"
    if a.thr:
        thr = {k: float(v) for k, v in (kv.split("=") for kv in a.thr.split(","))}
    elif tuned.exists():
        thr = {k: v for k, v in json.loads(tuned.read_text()).items() if k in ("high", "medium", "low")}
    else:
        thr = {"high": 0.5, "medium": 0.3, "low": 0.6}
    print("thresholds", thr, flush=True)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    model, cfg = load(a.name, dev)
    src = EXT if a.ext else BENCH
    out = ROOT / ".cache" / ("ext-preds" if a.ext else "preds") / f"model-{a.name}"
    out.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.glob("*.jsonl")):
        t0, rows, chars = time.time(), [], 0
        for d in read_jsonl(p):
            u = encode(d["text"])
            chars += len(u)
            spans = decode(probs_for(model, u, cfg["buckets"], dev), thr, u) if len(u) else []
            rows.append({"id": d["id"], "entities": [{"start": s, "end": e, "type": t, "score": round(sc, 4)} for s, e, t, sc in spans]})
        write_jsonl(out / p.name, rows)
        print(f"model-{a.name} {p.stem}: {len(rows)} docs, {chars} units in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
