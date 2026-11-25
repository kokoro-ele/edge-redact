"""Build training data into training/.cache/train/<source>.jsonl and a dev split into .cache/dev/.

    uv run python py/build_train.py [source ...]

Sources (each is one M1 stage, see PLAN.md):
- nemotron:   Nemotron-PII `train` parquet (en). The benchmark reads only the `test` file.
- openpii:    openpii train.jsonl, zh and en. The benchmark reads only validation.jsonl.
- gretel:     Gretel finance, English train file. Gold is incomplete, so it is a separate stage.
- templates:  the train half of data/templates/*.tsv, filled with fake values.
- synth:      data/synth/zh-templates.jsonl (Claude-written slot templates), filled with fake values.
- hardneg:    py/hardneg.py, technical text with numbers/ids that are not PII (half carry one train PII template).

Records use the benchmark format (UTF-16 offsets, `entities`, `ignore`). About 5% of each source
(hash(id) % 20 == 0) goes to .cache/dev/<source>.jsonl for early stopping and threshold choice; the
benchmark is never used for either.

Any document whose normalised text equals a benchmark text, or that shares a 64-character window
with one, is dropped here and counted; py/check_isolation.py then re-checks the written files.
"""

import json
import sys

import pyarrow.parquet as pq

from check_isolation import WIN, bench_windows, norm, windows
from common import BENCH, EXT, RAW, ROOT, h, read_jsonl, synth_is_test, to_record, write_jsonl
from fakes import Fakes
from hardneg import hardneg_docs
from labels import GRETEL, NEMOTRON, OPENPII
from prepare import fill, load_templates, map_spans, parse_spans

TRAIN = ROOT / ".cache" / "train"
DEV = ROOT / ".cache" / "dev"
SYNTH = ROOT / "data" / "synth" / "zh-templates.jsonl"

NEMOTRON_DOCS = 30_000
OPENPII_PER_LANG = 40_000
FILLS_PER_TEMPLATE = 60
HARDNEG_DOCS = 30_000


def _zh_en(spans):
    # zh / en scope: My Number labels (rare in en data) train as a generic national id
    return [(s, e, "NATIONAL_ID" if t == "JP_MYNUMBER" else t) for s, e, t in spans]


def nemotron():
    t = pq.read_table(RAW / "nemotron_en/train-00000-of-00001.parquet", columns=["uid", "text", "spans"]).to_pylist()
    for i, r in enumerate(t):
        r["_row"] = i
    t.sort(key=lambda r: h(r["uid"]))
    for r in t[:NEMOTRON_DOCS]:
        yield to_record(f"nemotron_en:{r['uid']}:{r['_row']}", "nemotron", "en", r["text"], _zh_en(map_spans(r["text"], parse_spans(r["spans"]), NEMOTRON)))


def openpii():
    n = {"zh": 0, "en": 0}
    for r in read_jsonl(RAW / "openpii/train.jsonl"):
        lang = r["language"]
        if lang not in n or n[lang] >= OPENPII_PER_LANG:
            continue
        n[lang] += 1
        yield to_record(f"openpii:{r['uid']}", "openpii", lang, r["source_text"], map_spans(r["source_text"], r["privacy_mask"], OPENPII))
        if all(v >= OPENPII_PER_LANG for v in n.values()):
            break


def gretel():
    t = pq.read_table(RAW / "gretel_fin/English_train-00000-of-00001.parquet", columns=["__index_level_0__", "generated_text", "pii_spans"]).to_pylist()
    for r in t:
        text = r["generated_text"]
        yield to_record(f"gretel:{r['__index_level_0__']}", "gretel", "en", text, map_spans(text, json.loads(r["pii_spans"]), GRETEL))


def _filled(tmpls, name):
    fk = Fakes(seed=h(name) % (2**32))
    for t in tmpls:
        for i in range(FILLS_PER_TEMPLATE):
            text, spans = fill(t["text"], fk)
            yield to_record(f"{name}:{t['id']}:{i}", name, t["lang"], text, _zh_en(spans))


def templates():
    for f in ("pii.tsv", "neg.tsv"):
        yield from _filled([t for t in load_templates(f) if t["split"] == "train"], "tmpl")


def synth():
    if not SYNTH.exists():
        print("  no data/synth/zh-templates.jsonl yet; run py/synth_zh.py first")
        return
    keep = [r for r in read_jsonl(SYNTH) if not synth_is_test(r["id"])]  # the rest is zh-synth / mixed-synth
    yield from _filled([{"id": r["id"], "lang": r["lang"], "text": r["text"]} for r in keep], "synth")


def hardneg():
    pii = [t for t in load_templates("pii.tsv") if t["split"] == "train"]
    for i, (lang, text, spans) in enumerate(hardneg_docs(HARDNEG_DOCS, 7, pii, fill)):
        yield to_record(f"hardneg:{i}", "hardneg", lang, text, _zh_en(spans))


SOURCES = {"nemotron": nemotron, "openpii": openpii, "gretel": gretel, "templates": templates, "synth": synth, "hardneg": hardneg}


def main(names):
    bench = [d for p in sorted(BENCH.glob("*.jsonl")) + sorted(EXT.glob("*.jsonl")) for d in read_jsonl(p)]
    ids = {d["id"] for d in bench}
    texts = {norm(d["text"]) for d in bench}
    wins = bench_windows(bench)
    for name in names or SOURCES:
        train, dev, dropped = [], [], 0
        for r in SOURCES[name]():
            if r["id"] in ids or norm(r["text"]) in texts or windows(r["text"], WIN // 2) & wins:
                dropped += 1
                continue
            (dev if h(r["id"]) % 20 == 0 else train).append(r)
        if not train:
            continue
        write_jsonl(TRAIN / f"{name}.jsonl", train)
        write_jsonl(DEV / f"{name}.jsonl", dev)
        ents = sum(len(r["entities"]) for r in train)
        langs = {}
        for r in train:
            langs[r["lang"]] = langs.get(r["lang"], 0) + 1
        print(f"{name:10} train={len(train):6} dev={len(dev):5} entities={ents:7} chars={sum(len(r['text']) for r in train):10} langs={langs} dropped_overlap={dropped}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
