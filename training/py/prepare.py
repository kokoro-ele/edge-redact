"""Build benchmark sets into training/.cache/bench/*.jsonl and the committed manifest.

Benchmark sources come only from held-out splits:
- nemotron_en: the `test` parquet file (training reads only `train`).
- openpii: validation.jsonl (training reads train.jsonl).
- pii_bench_zh: evaluation only, never training.
- templates: templates with hash(id) % 2 == 0 (training reads the other half).
"""

import ast
import json
import re
from pathlib import Path

import pyarrow.parquet as pq

from common import BENCH, EXT, MANIFESTS, RAW, ROOT, h, read_jsonl, synth_is_test, to_record, write_jsonl
from fakes import NEUTRAL_SLOTS, PII_SLOTS, Fakes
from labels import GRETEL, IGNORE, NEMOTRON, OPENPII, PII_BENCH_ZH, merge_parts

SIZES = {
    "en-nemotron": 300, "en-openpii": 300,
    "zh-openpii": 300, "zh-piibench": 300, "zh-piibench-chat": 300,
    "zh-tmpl": 150, "en-tmpl": 150, "mixed-tmpl": 400,
    "neg-tmpl": 1500,
    "zh-synth": 150, "mixed-synth": 180,
}
SLOT_RE = re.compile(r"\{([A-Z_]+)\}")
stats: dict[str, dict] = {}


def parse_spans(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return ast.literal_eval(v)
    return v


def map_spans(text, spans, table, key_label="label"):
    out = []
    for s in spans:
        lab = table.get(s[key_label], IGNORE)
        out.append((s["start"], s["end"], lab))
    return merge_parts(text, out)


def check_offsets(name, text, spans):
    bad = sum(1 for s in spans if "text" in s and text[s["start"]:s["end"]].lower() != str(s["text"]).lower())
    stats.setdefault(name, {"offset_mismatch": 0})["offset_mismatch"] += bad


def take(rows, n, key):
    return sorted(rows, key=lambda r: h(key(r)))[:n]


def nemotron_en():
    t = pq.read_table(RAW / "nemotron_en/test-00000-of-00001.parquet").to_pylist()
    # a uid names a document spec that appears in two rows (often two formats), so the row number
    # makes the id unique; selection still sorts by uid (stable), keeping the same 300 rows
    for i, r in enumerate(t):
        r["_row"] = i
    for r in take(t, SIZES["en-nemotron"], lambda r: r["uid"]):
        sp = parse_spans(r["spans"])
        check_offsets("en-nemotron", r["text"], sp)
        yield to_record(f"nemotron_en:{r['uid']}:{r['_row']}", "en-nemotron", "en", r["text"], map_spans(r["text"], sp, NEMOTRON))


def openpii(lang):
    rows = [r for r in read_jsonl(RAW / "openpii/validation.jsonl") if r["language"] == lang]
    name = f"{lang}-openpii"
    for r in take(rows, SIZES[name], lambda r: r["uid"]):
        sp = r["privacy_mask"]
        check_offsets(name, r["source_text"], [{**s, "text": s["value"]} for s in sp])
        yield to_record(f"openpii:{r['uid']}", name, lang, r["source_text"], map_spans(r["source_text"], sp, OPENPII))


def pii_bench_zh(file, name):
    rows = list(read_jsonl(RAW / "pii_bench_zh" / file))
    for r in take(rows, SIZES[name], lambda r: r["id"]):
        sp = [{"start": e["start"], "end": e["end"], "label": e["type"], "text": e["text"]} for e in r["entities"]]
        check_offsets(name, r["text"], sp)
        yield to_record(f"pii_bench_zh:{r['id']}", name, "zh", r["text"], map_spans(r["text"], sp, PII_BENCH_ZH))


def load_templates(file):
    out = []
    for line in (ROOT / "data/templates" / file).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        tid, lang, tmpl = line.split("\t", 2)
        out.append({"id": tid, "lang": lang, "text": tmpl.replace("\\n", "\n"), "split": "test" if h(tid) % 2 == 0 else "train"})
    return out


def fill(tmpl: str, fk: Fakes):
    text, spans, pos = [], [], 0
    cur = 0
    for m in SLOT_RE.finditer(tmpl):
        slot = m.group(1)
        if slot not in PII_SLOTS and slot not in NEUTRAL_SLOTS:
            continue
        text.append(tmpl[pos:m.start()])
        cur += m.start() - pos
        if slot in PII_SLOTS:
            typ, fn = PII_SLOTS[slot]
            v = fn(fk)
            spans.append((cur, cur + len(v), typ))
        else:
            v = fk.neutral(slot)
            if slot == "UID":
                spans.append((cur, cur + len(v), IGNORE))
        text.append(v)
        cur += len(v)
        pos = m.end()
    text.append(tmpl[pos:])
    return "".join(text), spans


def template_set(file, name, langs, split="test"):
    tmpls = [t for t in load_templates(file) if t["split"] == split and t["lang"] in langs]
    fk = Fakes(seed=h(name) % (2**32))
    for i in range(SIZES[name]):
        t = tmpls[i % len(tmpls)]
        text, spans = fill(t["text"], fk)
        yield to_record(f"tmpl:{t['id']}:{i}", name, t["lang"], text, spans)


def synth_set(name, lang):
    """Held-out Claude-written templates (common.synth_is_test), several fills each."""
    path = ROOT / "data" / "synth" / "zh-templates.jsonl"
    if not path.exists():
        return
    tmpls = [r for r in read_jsonl(path) if r["lang"] == lang and synth_is_test(r["id"])]
    fk = Fakes(seed=h(name) % (2**32))
    for i in range(SIZES[name]):
        t = tmpls[i % len(tmpls)]
        text, spans = fill(t["text"], fk)
        yield to_record(f"synth:{t['id']}:{i}", name, lang, text, spans)


def main():
    sets = {
        "en-nemotron": nemotron_en(), "en-openpii": openpii("en"),
        "zh-openpii": openpii("zh"),
        "zh-piibench": pii_bench_zh("pii_bench_zh.jsonl", "zh-piibench"),
        "zh-piibench-chat": pii_bench_zh("pii_bench_zh_chat.jsonl", "zh-piibench-chat"),
        "zh-tmpl": template_set("pii.tsv", "zh-tmpl", {"zh"}),
        "en-tmpl": template_set("pii.tsv", "en-tmpl", {"en"}),
        "mixed-tmpl": template_set("pii.tsv", "mixed-tmpl", {"mixed"}),
        "neg-tmpl": template_set("neg.tsv", "neg-tmpl", {"zh", "en", "mixed"}),
        "zh-synth": synth_set("zh-synth", "zh"),
        "mixed-synth": synth_set("mixed-synth", "mixed"),
    }
    manifest = {}
    for name, rows in sets.items():
        rows = list(rows)
        write_jsonl(BENCH / f"{name}.jsonl", rows)
        manifest[name] = [r["id"] for r in rows]
        n_ent = sum(len(r["entities"]) for r in rows)
        print(f"{name:18} docs={len(rows):4} entities={n_ent:5} chars={sum(len(r['text']) for r in rows)} {stats.get(name, '')}")
    ext = []
    rb = RAW / "redactionbench/documents.ndjson"
    if rb.exists():
        ext = [{"id": d["document_id"], "lang": "en", "text": d["text"]} for d in read_jsonl(rb)]
        write_jsonl(EXT / "redactionbench.jsonl", ext)
        manifest["ext:redactionbench"] = [r["id"] for r in ext]
        print(f"{'redactionbench (ext)':18} docs={len(ext):4} chars={sum(len(r['text']) for r in ext)} (scored by pnpm rbench)")
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    (MANIFESTS / "bench.json").write_text(json.dumps(manifest, indent=0, ensure_ascii=False) + "\n")
    splits = {f: {s: [t["id"] for t in load_templates(f) if t["split"] == s] for s in ("train", "test")} for f in ("pii.tsv", "neg.tsv")}
    (MANIFESTS / "template-splits.json").write_text(json.dumps(splits, indent=1) + "\n")


if __name__ == "__main__":
    main()
