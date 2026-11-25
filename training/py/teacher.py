"""Run teacher models over the benchmark and cache predictions for `pnpm bench`.

    uv run --extra teacher python py/teacher.py <name> [--limit N] [--ext]

Output: training/.cache/preds/<name>/<set>.jsonl with {id, entities: [{start, end, type, score}]}
(UTF-16 offsets, taxonomy types). The benchmark is never used for training; this only scores.

CJK text has no spaces. GLiNER's default word splitter would make a whole Chinese sentence one
"word", so this script splits CJK into single characters and keeps Latin runs whole.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from common import BENCH, EXT, ROOT, read_jsonl, u16_offsets, write_jsonl

PREDS = ROOT / ".cache" / "preds"
TOKEN_RE = re.compile(r"[぀-ヿ㐀-鿿豈-﫿ｦ-ﾟ]|[A-Za-z0-9À-ɏ]+(?:[-_.'@][A-Za-z0-9À-ɏ]+)*|\S")

# --- label prompts and their taxonomy types ---
GLINER_NVIDIA = {
    "first_name": "PERSON", "last_name": "PERSON", "street_address": "ADDRESS", "postcode": "ADDRESS",
    "email": "EMAIL", "phone_number": "PHONE", "fax_number": "PHONE", "ipv4": "IP", "ipv6": "IP",
    "credit_debit_card": "CREDIT_CARD", "account_number": "BANK_ACCOUNT", "ssn": "NATIONAL_ID",
    "national_id": "NATIONAL_ID", "tax_id": "NATIONAL_ID", "password": "SECRET", "api_key": "SECRET",
    "pin": "SECRET", "cvv": "SECRET", "company_name": "ORG", "medical_record_number": "OTHER_ID",
    "license_plate": "OTHER_ID", "vehicle_identifier": "OTHER_ID",
}
GLINER_MULTI = {
    "person": "PERSON", "address": "ADDRESS", "email": "EMAIL", "phone number": "PHONE",
    "ip address": "IP", "credit card number": "CREDIT_CARD", "bank account number": "BANK_ACCOUNT",
    "iban": "BANK_ACCOUNT", "passport number": "NATIONAL_ID", "social security number": "NATIONAL_ID",
    "identity card number": "NATIONAL_ID", "driver's license number": "NATIONAL_ID",
    "tax identification number": "NATIONAL_ID", "cvv": "SECRET", "organization": "ORG",
    "license plate number": "OTHER_ID",
}
AI4PRIVACY = {
    "GIVENNAME": "PERSON", "SURNAME": "PERSON", "STREET": "ADDRESS", "BUILDINGNUM": "ADDRESS",
    "ZIPCODE": "ADDRESS", "CITY": "ADDRESS", "EMAIL": "EMAIL", "TELEPHONENUM": "PHONE",
    "CREDITCARDNUMBER": "CREDIT_CARD", "IDCARDNUM": "NATIONAL_ID", "SOCIALNUM": "NATIONAL_ID",
    "PASSPORTNUM": "NATIONAL_ID", "DRIVERLICENSENUM": "NATIONAL_ID", "TAXNUM": "NATIONAL_ID",
    "ACCOUNTNUM": "BANK_ACCOUNT", "PASSWORD": "SECRET",
}

TEACHERS = {
    "gliner-pii-nvidia": ("gliner", "nvidia/gliner-PII", "bd23e8ef4425fd04e34c5204ab49ffaa706eae79", GLINER_NVIDIA, 0.4),
    "gliner-multi-pii": ("gliner", "urchade/gliner_multi_pii-v1", "1fcf13e85f4eef5394e1fcd406cf2ca9ea82351d", GLINER_MULTI, 0.4),
    "ai4privacy-modernbert": ("hf", "ai4privacy/llama-ai4privacy-multilingual-categorical-anonymiser-openpii", "83ef30d5e7c9d113ad80ce745b564cdd2320c5d5", AI4PRIVACY, 0.5),
}


class CjkSplitter:
    def __call__(self, text):
        for m in TOKEN_RE.finditer(text):
            yield m.group(), m.start(), m.end()


def chunks(text: str, max_tokens: int):
    """Yield (offset, chunk) with at most max_tokens tokens, cut at line or sentence ends when possible."""
    toks = [(m.start(), m.end()) for m in TOKEN_RE.finditer(text)]
    i = 0
    while i < len(toks):
        j = min(i + max_tokens, len(toks))
        if j < len(toks):
            # back off to a boundary
            for k in range(j, i + max_tokens // 2, -1):
                if text[toks[k - 1][0]] in "。．.!?！？\n" or "\n" in text[toks[k - 1][1]:toks[k][0]]:
                    j = k
                    break
        s, e = toks[i][0], toks[j - 1][1]
        yield s, text[s:e]
        i = j


def run_gliner(repo, rev, labels, threshold, docs):
    from gliner import GLiNER
    import torch

    model = GLiNER.from_pretrained(repo, revision=rev)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(dev)
    model.eval()
    dp = model.data_processor
    dp.words_splitter = CjkSplitter()
    max_tokens = min(getattr(model.config, "max_len", 384), 384) - 20
    names = list(labels)
    for d in docs:
        ents = []
        for off, chunk in chunks(d["text"], max_tokens):
            with torch.no_grad():
                for p in model.predict_entities(chunk, names, threshold=threshold, flat_ner=True):
                    ents.append((off + p["start"], off + p["end"], labels[p["label"]], float(p["score"])))
        yield d, ents


def run_hf(repo, rev, labels, threshold, docs):
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

    tok = AutoTokenizer.from_pretrained(repo, revision=rev)
    model = AutoModelForTokenClassification.from_pretrained(repo, revision=rev)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    # The pipeline's own aggregation fragments BPE words ("ter@", "."), so aggregate raw tokens here:
    # widen each token to its Latin word, then merge same-type neighbours separated by little punctuation.
    pipe = pipeline("token-classification", model=model, tokenizer=tok, aggregation_strategy="none", device=dev)
    word = re.compile(r"[A-Za-z0-9À-ɏ]")
    for d in docs:
        ents = []
        for off, chunk in chunks(d["text"], 400):
            toks = []
            for p in pipe(chunk):
                lab = p["entity"].removeprefix("B-").removeprefix("I-")
                if lab not in labels or p["score"] < threshold:
                    continue
                s, e = p["start"], p["end"]
                while s < e and chunk[s].isspace():
                    s += 1
                while s > 0 and word.match(chunk[s - 1]) and word.match(chunk[s]):
                    s -= 1
                while e < len(chunk) and e > s and word.match(chunk[e]) and word.match(chunk[e - 1]):
                    e += 1
                if s < e:
                    toks.append([s, e, labels[lab], float(p["score"])])
            toks.sort()
            merged = []
            for t in toks:
                if merged and merged[-1][2] == t[2] and t[0] - merged[-1][1] <= 3 and re.fullmatch(r"[\s.,@\-/()+:]*", chunk[merged[-1][1]:t[0]] if t[0] > merged[-1][1] else ""):
                    merged[-1][1] = max(merged[-1][1], t[1])
                    merged[-1][3] = max(merged[-1][3], t[3])
                else:
                    merged.append(t)
            ents += [(off + s, off + e, typ, sc) for s, e, typ, sc in merged]
        yield d, ents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", choices=TEACHERS)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sets", default="")
    ap.add_argument("--ext", action="store_true", help="run on external benchmarks in .cache/ext instead")
    a = ap.parse_args()
    kind, repo, rev, labels, thr = TEACHERS[a.name]
    src = EXT if a.ext else BENCH
    out_dir = (ROOT / ".cache" / "ext-preds" if a.ext else PREDS) / a.name
    out_dir.mkdir(parents=True, exist_ok=True)
    sets = sorted(p.stem for p in src.glob("*.jsonl"))
    if a.sets:
        sets = [s for s in sets if s in a.sets.split(",")]
    run = run_gliner if kind == "gliner" else run_hf
    for s in sets:
        dest = out_dir / f"{s}.jsonl"
        docs = list(read_jsonl(src / f"{s}.jsonl"))
        # cached predictions are reused only if they cover exactly this set's ids (ids can change on rebuild)
        if dest.exists() and not a.limit and {r["id"] for r in read_jsonl(dest)} == {d["id"] for d in docs}:
            continue
        if a.limit:
            docs = docs[: a.limit]
        t0 = time.time()
        rows = []
        for d, ents in run(repo, rev, labels, thr, docs):
            m = u16_offsets(d["text"])
            rows.append({"id": d["id"], "entities": [{"start": m[s_], "end": m[e], "type": t, "score": round(sc, 4)} for s_, e, t, sc in ents]})
        write_jsonl(dest, rows)
        print(f"{a.name} {s}: {len(rows)} docs in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
