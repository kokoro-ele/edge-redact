"""Export a trained tagger to the runtime weight format, plus parity fixtures for the TS tests.

    uv run --extra train python py/export.py <name> [--int8] [--out ../models/<name>.erdm]

Format (little endian):
    "ERDM" | u32 header_len | header JSON (utf-8) | zero pad to 16 | tensor data (16-byte aligned)
Header: {"version": 1, "config": {...}, "thresholds": {...}, "types": [...],
         "tensors": {name: {"shape": [...], "dtype": "f32" | "i8", "offset": n, "scale": offset_of_f32_scales}}}
i8 tensors are symmetric per output row (first dim): w = q * scale[row]. Biases and LayerNorm stay f32.
i4 (embedding only, --int4): same, q in -7..7, two's-complement nibbles packed low nibble first.

Fixtures (training/.cache/export/<name>.fixtures.json): a few texts with the PyTorch logits and decoded
spans, which test/model.test.ts compares against src/model/cpu.ts.
"""

import argparse
import json
import struct

import numpy as np
import torch

from common import ROOT
from model import TAGS, TYPES, bucketize, decode, encode, features
from predict import MODELS, load

EXPORT = ROOT / ".cache" / "export"
FIXTURE_TEXTS = [
    "",
    "a",
    "客户张伟反馈登录失败，手机号 138 0013 8000，log 里是 401 Unauthorized，帮我看看",
    "Hi Sarah, please send the contract to sarah.chen@example.com by Friday. Call me at (415) 555-0132.",
    "订单号 744449438908532518 一直显示处理中，系统版本 3.2.1，commit e1d19fa6a653020d0b9c585139c99c604bf69869",
    "收件人：李娜\n地址：上海市浦东新区世纪大道100号\n电话：13912345678 😀 谢谢！",
    "混合 text with emoji 👍🏻 and surrogate 𠀋 chars, IP 10.0.0.12, user 王小明 / Bob Smith",
    "x" * 5000 + " 张三 13800138000 " + "y" * 3000,
]


def quantize_rows(w: np.ndarray, qmax: int = 127):
    flat = w.reshape(w.shape[0], -1)
    scale = np.abs(flat).max(1) / qmax
    scale[scale == 0] = 1.0
    q = np.clip(np.round(flat / scale[:, None]), -qmax, qmax).astype(np.int8)
    return q.reshape(w.shape), scale.astype(np.float32)


def qmax_for(k: str, v: np.ndarray, bits: int):
    """None = keep f32. int4 applies to the embedding table only (it is ~all of the file)."""
    if bits == 32 or not k.endswith("weight") or v.ndim < 2:
        return None
    return 7 if bits == 4 and k == "emb.weight" else 127


def dequantized_state(state, bits: int):
    """What the runtime will compute with: weights rounded through int8/int4."""
    out = {}
    for k, v in state.items():
        v = v.detach().cpu().float().numpy()
        qm = qmax_for(k, v, bits)
        if qm:
            q, s = quantize_rows(v, qm)
            v = (q.reshape(q.shape[0], -1).astype(np.float32) * s[:, None]).reshape(v.shape)
        out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--int8", action="store_true")
    ap.add_argument("--int4", action="store_true", help="int4 embedding table, int8 elsewhere")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    bits = 4 if a.int4 else 8 if a.int8 else 32
    suffix = {4: "-int4", 8: "-int8", 32: ""}[bits]
    model, cfg = load(a.name, "cpu")
    thr_path = MODELS / a.name / "thresholds.json"
    thr = {k: v for k, v in json.loads(thr_path.read_text()).items() if k in ("high", "medium", "low")}
    state = model.state_dict()

    blobs, tensors, off = [], {}, 0

    def add(buf: bytes):
        nonlocal off
        pad = (-off) % 16
        blobs.append(b"\0" * pad)
        off += pad
        start = off
        blobs.append(buf)
        off += len(buf)
        return start

    for k, v in state.items():
        v = v.detach().cpu().float().numpy()
        qm = qmax_for(k, v, bits)
        if qm == 7:
            q, s = quantize_rows(v, 7)
            n = (q.reshape(-1).astype(np.int16) & 0xF).astype(np.uint8)  # two's-complement nibbles
            if len(n) % 2:
                n = np.append(n, 0)
            o = add((n[0::2] | (n[1::2] << 4)).astype(np.uint8).tobytes())  # low nibble first
            so = add(s.astype("<f4").tobytes())
            tensors[k] = {"shape": list(v.shape), "dtype": "i4", "offset": o, "scale": so}
        elif qm:
            q, s = quantize_rows(v)
            o = add(q.tobytes())
            so = add(s.astype("<f4").tobytes())
            tensors[k] = {"shape": list(v.shape), "dtype": "i8", "offset": o, "scale": so}
        else:
            tensors[k] = {"shape": list(v.shape), "dtype": "f32", "offset": add(v.astype("<f4").tobytes())}

    header = {"version": 1, "name": a.name, "config": {**{k: cfg[k] for k in ("buckets", "emb", "hidden", "dilations")}, "sep": cfg.get("sep", False)},
              "thresholds": thr, "types": TYPES, "tags": TAGS, "tensors": tensors}
    hb = json.dumps(header, separators=(",", ":")).encode()
    pre = b"ERDM" + struct.pack("<I", len(hb)) + hb
    pre += b"\0" * ((-len(pre)) % 16)
    data = pre + b"".join(blobs)
    out = a.out or str(EXPORT / f"{a.name}{suffix}.erdm")
    from pathlib import Path
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(data)
    print(f"wrote {out}: {len(data):,} bytes")

    # fixtures: logits from the exact weights the runtime sees
    model.load_state_dict({k: torch.from_numpy(v) for k, v in dequantized_state(state, bits).items()})
    model.eval()
    fx = []
    with torch.no_grad():
        for t in FIXTURE_TEXTS:
            u = encode(t)
            if len(u):
                f = bucketize(features(u), cfg["buckets"])
                logits = model(torch.from_numpy(f)[None])[0].numpy()
                probs = torch.softmax(torch.from_numpy(logits), -1).numpy()
                spans = decode(probs, thr, u)
            else:
                logits, spans = np.zeros((0, len(TAGS)), np.float32), []
            fx.append({"text": t, "features": features(u)[:64].tolist() if len(u) else [],
                       "logits": np.round(logits, 6).tolist(),
                       "spans": [[s, e, ty] for s, e, ty, _ in spans]})
    fp = EXPORT / f"{a.name}{suffix}.fixtures.json"
    fp.write_text(json.dumps({"model": out, "fixtures": fx}))
    print(f"wrote {fp}")


if __name__ == "__main__":
    main()
