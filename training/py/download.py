"""Download pinned dataset files into training/.cache/raw/<source>/ (git-ignored).

openpii validation.jsonl is 1 GB; it is streamed and only zh / en rows are kept.
"""

import json
import sys
import urllib.request
from pathlib import Path

from sources import SOURCES

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / ".cache" / "raw"
KEEP_LANGS = {"zh", "en"}


def url(repo: str, rev: str, path: str) -> str:
    return f"https://huggingface.co/datasets/{repo}/resolve/{rev}/{path}"


def fetch(src_url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(src_url) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.rename(dest)


def fetch_filtered_jsonl(src_url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    kept = total = 0
    with urllib.request.urlopen(src_url) as r, open(tmp, "w", encoding="utf-8") as f:
        for raw in r:
            total += 1
            row = json.loads(raw)
            if row.get("language") not in KEEP_LANGS:
                continue
            kept += 1
            f.write(json.dumps({k: row[k] for k in ("uid", "language", "region", "source_text", "privacy_mask")}, ensure_ascii=False) + "\n")
    tmp.rename(dest)
    print(f"  kept {kept} of {total} rows", flush=True)


def main(names: list[str]) -> None:
    for name in names or SOURCES:
        s = SOURCES[name]
        for path in s["files"]:
            dest = RAW / name / Path(path).name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                continue
            print(f"{name}: {path}", flush=True)
            u = url(s["repo"], s["revision"], path)
            if name == "openpii":
                fetch_filtered_jsonl(u, dest)
            else:
                fetch(u, dest)


if __name__ == "__main__":
    main(sys.argv[1:])
