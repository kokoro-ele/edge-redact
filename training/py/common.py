import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / ".cache" / "raw"
BENCH = ROOT / ".cache" / "bench"
EXT = ROOT / ".cache" / "ext"  # external benchmarks with their own scorer (not in pnpm bench)
TRAIN = ROOT / ".cache" / "train"
MANIFESTS = ROOT / "data" / "manifests"


def h(s: str) -> int:
    return int.from_bytes(hashlib.sha256(str(s).encode()).digest()[:8], "big")


def u16_offsets(text: str) -> list[int]:
    """Map code point index -> UTF-16 index (len(text)+1 entries)."""
    out = [0] * (len(text) + 1)
    n = 0
    for i, ch in enumerate(text):
        out[i] = n
        n += 2 if ord(ch) > 0xFFFF else 1
    out[len(text)] = n
    return out


def _luhn(d: str) -> bool:
    t = 0
    for i, c in enumerate(reversed(d)):
        v = int(c)
        if i % 2:
            v = v * 2 - 9 if v > 4 else v * 2
        t += v
    return t % 10 == 0


def checksum_valid(typ: str, value: str) -> bool | None:
    """True / False for types with a check digit, None for the rest."""
    d = "".join(ch for ch in value if ch.isdigit() or ch in "Xx")
    if typ == "CREDIT_CARD":
        return d.isdigit() and 13 <= len(d) <= 19 and _luhn(d)
    if typ == "CN_ID":
        if len(d) != 18 or not d[:17].isdigit():
            return False
        w = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        return "10X98765432"[sum(int(c) * k for c, k in zip(d, w)) % 11] == d[17].upper()
    if typ == "JP_MYNUMBER":
        if len(d) != 12 or not d.isdigit():
            return False
        r = sum(int(d[11 - n]) * (n + 1 if n <= 6 else n - 5) for n in range(1, 12)) % 11
        return int(d[11]) == (0 if r <= 1 else 11 - r)
    return None


def to_record(rid: str, set_name: str, lang: str, text: str, spans: list[tuple[int, int, str]]) -> dict:
    """spans in code points with final labels (taxonomy type or IGNORE)."""
    m = u16_offsets(text)
    ents, ign = [], []
    for s, e, lab in spans:
        # trim whitespace inside the span
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if s >= e:
            continue
        item = {"start": m[s], "end": m[e]}
        if lab == "IGNORE":
            ign.append(item)
        else:
            item["type"] = lab
            v = checksum_valid(lab, text[s:e])
            if v is not None:
                item["valid"] = v
            ents.append(item)
    ents.sort(key=lambda x: x["start"])
    return {"id": rid, "set": set_name, "lang": lang, "text": text, "entities": ents, "ignore": ign}


def write_jsonl(path: Path, rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def synth_is_test(tmpl_id: str) -> bool:
    """Claude-written templates (data/synth/zh-templates.jsonl): 1 in 5 is held out for the benchmark."""
    return h(f"synth:{tmpl_id}") % 5 == 0
