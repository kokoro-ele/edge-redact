"""Train the character tagger on chosen training sources (one M1 stage per call).

    uv run --extra train python py/train.py <name> --sources nemotron:1,openpii:1 [--steps 6000]
        [--buckets 65536 --emb 32 --hidden 96]

Each source in .cache/train/<source>.jsonl becomes one stream of UTF-16 code units (documents
separated by padding); a batch draws each window's source by weight, then a random offset.
The dev split (.cache/dev/) picks the best checkpoint; the benchmark is never read here.
Output: .cache/models/<name>/{model.pt, config.json, log.jsonl}.
"""

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import torch

from common import ROOT, read_jsonl
from model import IGNORE_TAG, PAD, TAGS, Tagger, bucketize, encode, features, tag_ids

TRAIN = ROOT / ".cache" / "train"
DEV = ROOT / ".cache" / "dev"
MODELS = ROOT / ".cache" / "models"
CTX = 2  # features look 2 code units to each side


def stream(path: Path, limit_chars: int = 0, langs=None):
    """Concatenate documents into (units, tags) with 8 pad units between documents."""
    us, ys, n = [], [], 0
    gap_u, gap_y = np.full(8, PAD, np.uint32), np.full(8, IGNORE_TAG, np.int64)
    for r in read_jsonl(path):
        if langs and r["lang"] not in langs:
            continue
        u = encode(r["text"])
        us += [u, gap_u]
        ys += [tag_ids(len(u), r["entities"], r.get("ignore", [])), gap_y]
        n += len(u)
        if limit_chars and n >= limit_chars:
            break
    if not us:
        return np.full(8, PAD, np.uint32), np.full(8, IGNORE_TAG, np.int64)
    return np.concatenate(us), np.concatenate(ys)


def batch(streams, weights, rng, bs, T, buckets):
    feats = np.empty((bs, T, 6), np.int64)
    tags = np.empty((bs, T), np.int64)
    which = rng.choice(len(streams), size=bs, p=weights)
    for b, k in enumerate(which):
        u, y = streams[k]
        s = int(rng.integers(0, max(1, len(u) - T)))
        win = np.zeros(T + 2 * CTX, np.uint32)
        lo, hi = max(0, s - CTX), min(len(u), s + T + CTX)
        win[lo - (s - CTX):hi - (s - CTX)] = u[lo:hi]
        feats[b] = bucketize(features(win)[CTX:CTX + T], buckets)
        t = np.full(T, IGNORE_TAG, np.int64)
        seg = y[s:s + T]
        t[:len(seg)] = seg
        tags[b] = t
    return torch.from_numpy(feats), torch.from_numpy(tags)


@torch.no_grad()
def dev_loss(model, dev_streams, dev, buckets, T=512):
    """Mean token loss over fixed windows of every dev stream (deterministic)."""
    model.eval()
    tot, n = 0.0, 0
    for u, y in dev_streams:
        for s in range(0, min(len(u), 400_000), T):
            win = np.zeros(T + 2 * CTX, np.uint32)
            lo, hi = max(0, s - CTX), min(len(u), s + T + CTX)
            win[lo - (s - CTX):hi - (s - CTX)] = u[lo:hi]
            f = torch.from_numpy(bucketize(features(win)[CTX:CTX + T], buckets))[None].to(dev)
            t = np.full(T, IGNORE_TAG, np.int64)
            seg = y[s:s + T]
            t[:len(seg)] = seg
            t = torch.from_numpy(t)[None].to(dev)
            k = (t != IGNORE_TAG).sum().item()
            if k:
                tot += torch.nn.functional.cross_entropy(model(f).flatten(0, 1), t.flatten(), ignore_index=IGNORE_TAG, reduction="sum").item()
                n += k
    model.train()
    return tot / max(n, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--sources", required=True, help="source:weight,... from .cache/train")
    ap.add_argument("--steps", type=int, default=6000)
    ap.add_argument("--bs", type=int, default=64)
    ap.add_argument("--T", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--buckets", type=int, default=1 << 16)
    ap.add_argument("--emb", type=int, default=32)
    ap.add_argument("--hidden", type=int, default=96)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--sep", action="store_true", help="depthwise-separable conv blocks")
    ap.add_argument("--dilations", default="1,2,4,8,1,2,4,8")
    ap.add_argument("--init", default="", help="start from .cache/models/<name>/model.pt (same architecture)")
    ap.add_argument("--qat4", action="store_true", help="int4 fake-quantized embedding table (QAT)")
    ap.add_argument("--langs", default="", help="keep only these record langs, e.g. zh,mixed (monolingual control)")
    a = ap.parse_args()
    langs = set(a.langs.split(",")) if a.langs else None

    torch.manual_seed(a.seed)
    rng = np.random.default_rng(a.seed)
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    srcs = [(s.split(":")[0], float(s.split(":")[1]) if ":" in s else 1.0) for s in a.sources.split(",")]
    t0 = time.time()
    streams = [stream(TRAIN / f"{s}.jsonl", langs=langs) for s, _ in srcs]
    dev_streams = [stream(DEV / f"{s}.jsonl", langs=langs) for s, _ in srcs]
    keep = [i for i, (u, _) in enumerate(streams) if len(u) > 8]  # a source may have no records in these langs
    srcs, streams, dev_streams = [srcs[i] for i in keep], [streams[i] for i in keep], [dev_streams[i] for i in keep]
    w = np.array([wt for _, wt in srcs]) / sum(wt for _, wt in srcs)
    print(f"loaded {[(s, len(u)) for (s, _), (u, _) in zip(srcs, streams)]} in {time.time() - t0:.0f}s", flush=True)

    model = Tagger(a.buckets, a.emb, a.hidden, [int(d) for d in a.dilations.split(",")], a.sep).to(dev)
    if a.init:
        model.load_state_dict(torch.load(MODELS / a.init / "model.pt", map_location="cpu"))
    model.qat_emb_bits = 4 if a.qat4 else 0
    print(f"params {model.n_params():,} (~{model.n_params() / 1e6:.2f} MB at int8)", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1, s / 300) * 0.5 * (1 + math.cos(math.pi * min(s, a.steps) / a.steps)))
    out = MODELS / a.name
    out.mkdir(parents=True, exist_ok=True)
    cfg = {**model.cfg, "sources": a.sources, "steps": a.steps, "bs": a.bs, "T": a.T, "lr": a.lr, "seed": a.seed, "langs": a.langs, "init": a.init, "qat4": a.qat4, "tags": TAGS}
    (out / "config.json").write_text(json.dumps(cfg, indent=1))
    log = open(out / "log.jsonl", "w")
    best, t0, run = float("inf"), time.time(), 0.0
    for step in range(1, a.steps + 1):
        f, t = batch(streams, w, rng, a.bs, a.T, a.buckets)
        loss = torch.nn.functional.cross_entropy(model(f.to(dev)).flatten(0, 1), t.to(dev).flatten(), ignore_index=IGNORE_TAG)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
        run = 0.98 * run + 0.02 * loss.item() if step > 1 else loss.item()
        if step % 500 == 0 or step == a.steps:
            dl = dev_loss(model, dev_streams, dev, a.buckets)
            if dl < best:
                best = dl
                torch.save(model.state_dict(), out / "model.pt")
            rec = {"step": step, "train": round(run, 4), "dev": round(dl, 4), "best": round(best, 4), "sec": round(time.time() - t0)}
            log.write(json.dumps(rec) + "\n")
            log.flush()
            print(rec, flush=True)


if __name__ == "__main__":
    main()
