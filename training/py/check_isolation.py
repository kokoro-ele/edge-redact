"""Fail if any benchmark document could leak into training data.

    uv run python py/check_isolation.py

Checks:
1. Template splits: no template id is in both train and test, and benchmark template docs use test templates only.
2. Source splits: Nemotron-en benchmark text does not appear in the Nemotron-en train parquet.
3. Training data (training/.cache/train/*.jsonl, once M1 builds it), against the benchmark and the
   external sets in .cache/ext: no benchmark id, no benchmark text
   after whitespace/case normalisation, and no shared 64-character window with any benchmark text.
"""

import json
import re
import sys

import pyarrow.parquet as pq

from common import BENCH, EXT, MANIFESTS, RAW, TRAIN, h, read_jsonl, synth_is_test

WIN = 64


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def windows(s: str, step: int):
    """Hashes of normalised WIN-char windows. The benchmark side uses every offset (step 1) and the
    training side every WIN // 2, so any shared passage of 1.5 * WIN characters is caught wherever it starts."""
    s = norm(s)
    return {hash(w) for i in range(0, max(1, len(s) - WIN + 1), step) if len(set(w := s[i:i + WIN])) >= 10}


def bench_windows(bench) -> set[int]:
    """Windows of benchmark texts, minus boilerplate: windows found in 3 or more benchmark documents
    (XML namespaces, licence text) say nothing about leakage. Low-diversity windows (`-----`) are
    already skipped by windows()."""
    df: dict[int, int] = {}
    for d in bench:
        if not d.get("set", "").startswith("neg-") or len(d["text"]) >= WIN:
            for w in windows(d["text"], 1):
                df[w] = df.get(w, 0) + 1
    return {w for w, n in df.items() if n < 3}


def main() -> int:
    errors: list[str] = []
    bench = [d for p in sorted(BENCH.glob("*.jsonl")) + sorted(EXT.glob("*.jsonl")) for d in read_jsonl(p)]
    print(f"benchmark: {len(bench)} docs")

    # 1. templates
    splits = json.loads((MANIFESTS / "template-splits.json").read_text())
    test_ids = set()
    for f, sp in splits.items():
        both = set(sp["train"]) & set(sp["test"])
        if both:
            errors.append(f"{f}: templates in both splits: {sorted(both)}")
        test_ids |= set(sp["test"])
    for d in bench:
        if d["id"].startswith("tmpl:") and d["id"].split(":")[1] not in test_ids:
            errors.append(f"{d['id']} uses a training template")

    # 1b. Claude-written templates: held-out ones only in the benchmark, the rest only in training
    for d in bench:
        if d["id"].startswith("synth:") and not synth_is_test(d["id"][6:].rsplit(":", 1)[0]):
            errors.append(f"{d['id']} uses a training synth template")
    synth_train = TRAIN / "synth.jsonl"
    if synth_train.exists():
        for r in read_jsonl(synth_train):
            if synth_is_test(r["id"][6:].rsplit(":", 1)[0]):
                errors.append(f"synth.jsonl: {r['id']} uses a held-out template")

    # 2. source splits
    en_train = RAW / "nemotron_en/train-00000-of-00001.parquet"
    if en_train.exists():
        train_texts = {norm(t) for t in pq.read_table(en_train, columns=["text"]).column("text").to_pylist()}
        n = sum(1 for d in bench if d["id"].startswith("nemotron_en:") and norm(d["text"]) in train_texts)
        if n:
            errors.append(f"{n} nemotron-en benchmark texts also appear in the train parquet")

    # 3. training data
    train_files = sorted(TRAIN.glob("*.jsonl")) if TRAIN.exists() else []
    if train_files:
        ids = {d["id"] for d in bench}
        texts = {norm(d["text"]) for d in bench}
        wins = bench_windows(bench)
        for p in train_files:
            for r in read_jsonl(p):
                if r["id"] in ids:
                    errors.append(f"{p.name}: benchmark id {r['id']}")
                elif norm(r["text"]) in texts:
                    errors.append(f"{p.name}: benchmark text in {r['id']}")
                elif windows(r["text"], WIN // 2) & wins:
                    errors.append(f"{p.name}: {r['id']} shares a {WIN}-char window with the benchmark")
        print(f"training files checked: {len(train_files)}")
    else:
        print("no training data yet (built in M1); split checks only")

    for e in errors[:50]:
        print("LEAK", e)
    print("isolation:", "FAIL" if errors else "ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
