"""Merge two models' predictions into one method (monolingual control: zh model ∪ en model).

    uv run python py/merge_preds.py <out-name> <pred-dir-a> <pred-dir-b>

Both models run on every document (no language routing: mixed text needs both). Where spans
overlap, the higher-scoring one wins. Writes .cache/preds/model-<out-name>/ and .cache/ext-preds/...
"""

import sys

from common import ROOT, read_jsonl, write_jsonl


def merge(a, b):
    out = []
    for e in sorted(a + b, key=lambda e: -e.get("score", 1)):
        if not any(k["start"] < e["end"] and e["start"] < k["end"] for k in out):
            out.append(e)
    return sorted(out, key=lambda e: e["start"])


def main(name, da, db):
    for kind in ("preds", "ext-preds"):
        base = ROOT / ".cache" / kind
        if not (base / da).exists():
            continue
        for p in sorted((base / da).glob("*.jsonl")):
            other = {r["id"]: r["entities"] for r in read_jsonl(base / db / p.name)}
            rows = [{"id": r["id"], "entities": merge(r["entities"], other.get(r["id"], []))} for r in read_jsonl(p)]
            write_jsonl(base / f"model-{name}" / p.name, rows)
        print(f"{kind}: merged {da} + {db} -> model-{name}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
