"""Pick decode thresholds on the dev split (never the benchmark).

    uv run --extra train python py/tune.py <name> [--fp-max 0.3]

For each (high, medium, low) threshold grid point: medium recall = share of gold medium entities
whose units are >= 90% covered by predicted spans, precision = share of predicted medium spans that
overlap gold, F2 from those; FP/1k = predicted spans per 1,000 units on dev documents with no gold
entities. Chooses the best medium F2 with FP/1k <= --fp-max and writes it to
.cache/models/<name>/thresholds.json, which predict.py reads by default.
"""

import argparse
import itertools
import json

import numpy as np
import torch

from common import ROOT, read_jsonl
from model import RISK, decode, encode
from predict import MODELS, load, probs_for

DEV = ROOT / ".cache" / "dev"
PER_SOURCE = 1500


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--fp-max", type=float, default=0.3)
    a = ap.parse_args()
    langs = set(filter(None, json.loads((MODELS / a.name / "config.json").read_text()).get("langs", "").split(","))) or None
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    model, cfg = load(a.name, dev)
    docs = []
    for p in sorted(DEV.glob("*.jsonl")):
        if p.stem == "gretel":  # gold is incomplete; it would punish correct finds
            continue
        for d in [d for d in read_jsonl(p) if not langs or d["lang"] in langs][:PER_SOURCE]:
            u = encode(d["text"])
            if len(u):
                docs.append((u, probs_for(model, u, cfg["buckets"], dev), d["entities"]))
    neg_units = sum(len(u) for u, _, g in docs if not g)
    print(f"{len(docs)} dev docs, {neg_units} units in docs without PII", flush=True)

    grid = {"high": [0.5, 0.7, 0.85], "medium": [0.3, 0.5, 0.7, 0.8, 0.85, 0.9, 0.95], "low": [0.6, 0.8, 0.9]}
    rows = []
    for hi, me, lo in itertools.product(grid["high"], grid["medium"], grid["low"]):
        thr = {"high": hi, "medium": me, "low": lo}
        hit = tot = tp = npred = fp = 0
        for u, pr, gold in docs:
            spans = decode(pr, thr, u)
            cov = np.zeros(len(u), bool)
            for s, e, _, _ in spans:
                cov[s:e] = True
            gmask = np.zeros(len(u), bool)
            for g in gold:
                gmask[g["start"]:g["end"]] = True
                if RISK.get(g["type"]) == "medium":
                    tot += 1
                    hit += cov[g["start"]:g["end"]].mean() >= 0.9
            for s, e, t, _ in spans:
                if not gold:
                    fp += 1
                if RISK[t] == "medium":
                    npred += 1
                    tp += gmask[s:e].any()
        r, p = hit / max(tot, 1), tp / max(npred, 1)
        f2 = 5 * p * r / max(4 * p + r, 1e-9)
        rows.append({**thr, "recall": round(float(r), 4), "precision": round(float(p), 4), "f2": round(float(f2), 4), "fp_per_1k": round(1000 * fp / max(neg_units, 1), 3)})
    ok = [r for r in rows if r["fp_per_1k"] <= a.fp_max] or sorted(rows, key=lambda r: r["fp_per_1k"])[:1]
    best = max(ok, key=lambda r: r["f2"])
    for r in sorted(rows, key=lambda r: -r["f2"])[:8]:
        print(r)
    print("chosen", best)
    (MODELS / a.name / "thresholds.json").write_text(json.dumps(best, indent=1))


if __name__ == "__main__":
    main()
