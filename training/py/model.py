"""Character-level tagger: hashed char n-gram features -> dilated residual CNN -> BIOES tags.

Everything the runtime must reproduce is in this file and kept simple enough to port to TypeScript
bit for bit (M2):
- `features()` uses only uint32 arithmetic (multiply, xor, shift), so `Math.imul` + `>>> 0` match it.
- Text is processed as UTF-16 code units, like JS strings, so offsets need no conversion.
"""

import numpy as np
import torch
from torch import nn

TYPES = ["PERSON", "ADDRESS", "PHONE", "EMAIL", "IP", "OTHER_ID", "NATIONAL_ID", "CN_ID",
         "CREDIT_CARD", "BANK_ACCOUNT", "SECRET", "ORG", "PROJECT"]
TAGS = ["O"] + [f"{p}-{t}" for t in TYPES for p in "BIES"]
TAG_ID = {t: i for i, t in enumerate(TAGS)}
IGNORE_TAG = -100
N_FEATURES = 6
PAD = 0  # code unit used beyond the text edges

M = np.uint32(0x9E3779B1)
SALTS = np.array([0x1B873593, 0xCC9E2D51, 0x85EBCA6B, 0xC2B2AE35, 0x27D4EB2F, 0x165667B1], dtype=np.uint32)


def fmix(x: np.ndarray) -> np.ndarray:
    """murmur3 finaliser on uint32 arrays."""
    x = x ^ (x >> np.uint32(16))
    x = x * np.uint32(0x85EBCA6B)
    x = x ^ (x >> np.uint32(13))
    x = x * np.uint32(0xC2B2AE35)
    return x ^ (x >> np.uint32(16))


def comb(h: np.ndarray, v: np.ndarray) -> np.ndarray:
    return fmix((h ^ v) * M)


def char_class(u: np.ndarray) -> np.ndarray:
    """0 pad, 1 space, 2 digit, 3 upper, 4 lower, 5 CJK, 6 kana/hangul/other letters, 7 punct/symbol."""
    c = np.full(u.shape, 7, dtype=np.uint32)
    c[u == PAD] = 0
    c[(u == 32) | (u == 9) | (u == 10) | (u == 13) | (u == 0x3000)] = 1
    c[(u >= 48) & (u <= 57)] = 2
    c[(u >= 65) & (u <= 90)] = 3
    c[(u >= 97) & (u <= 122)] = 4
    c[((u >= 0xC0) & (u <= 0x24F))] = 4
    c[((u >= 0x4E00) & (u <= 0x9FFF)) | ((u >= 0x3400) & (u <= 0x4DBF))] = 5
    c[((u >= 0x3040) & (u <= 0x30FF)) | ((u >= 0xAC00) & (u <= 0xD7AF))] = 6
    return c


def features(units: np.ndarray) -> np.ndarray:
    """units: uint32 UTF-16 code units, shape (n,). Returns uint32 hashes, shape (n, N_FEATURES).

    f0 unigram (exact), f1 left bigram, f2 right bigram, f3 centred trigram (digits folded to '0'
    in f1-f3), f4 char-class 5-gram (shape), f5 lowercased unigram + class of neighbours.
    """
    n = len(units)
    p = np.zeros(n + 4, dtype=np.uint32)
    p[2:n + 2] = units
    fold = p.copy()
    fold[(fold >= 48) & (fold <= 57)] = 48
    low = p.copy()
    up = (low >= 65) & (low <= 90)
    low[up] += np.uint32(32)
    cls = char_class(p)
    c = slice(2, n + 2)
    l1, r1, l2, r2 = slice(1, n + 1), slice(3, n + 3), slice(0, n), slice(4, n + 4)
    out = np.empty((n, N_FEATURES), dtype=np.uint32)
    out[:, 0] = comb(np.full(n, SALTS[0], np.uint32), p[c])
    out[:, 1] = comb(comb(np.full(n, SALTS[1], np.uint32), fold[l1]), fold[c])
    out[:, 2] = comb(comb(np.full(n, SALTS[2], np.uint32), fold[c]), fold[r1])
    out[:, 3] = comb(comb(comb(np.full(n, SALTS[3], np.uint32), fold[l1]), fold[c]), fold[r1])
    shape = cls[l2] * np.uint32(4096) + cls[l1] * np.uint32(512) + cls[c] * np.uint32(64) + cls[r1] * np.uint32(8) + cls[r2]
    out[:, 4] = comb(np.full(n, SALTS[4], np.uint32), shape)
    out[:, 5] = comb(comb(np.full(n, SALTS[5], np.uint32), low[c]), cls[l1] * np.uint32(8) + cls[r1])
    return out


def encode(text: str) -> np.ndarray:
    """UTF-16 code units of `text` as uint32 (matches JS charCodeAt)."""
    return np.frombuffer(text.encode("utf-16-le"), dtype=np.uint16).astype(np.uint32)


def tag_ids(n: int, entities, ignore) -> np.ndarray:
    """BIOES tag per code unit; IGNORE spans get IGNORE_TAG (no loss)."""
    y = np.zeros(n, dtype=np.int64)
    for s in ignore:
        y[s["start"]:s["end"]] = IGNORE_TAG
    for e in entities:
        t, s, end = e["type"], e["start"], e["end"]
        if t not in TYPES or end <= s:
            continue
        if end - s == 1:
            y[s] = TAG_ID[f"S-{t}"]
        else:
            y[s] = TAG_ID[f"B-{t}"]
            y[s + 1:end - 1] = TAG_ID[f"I-{t}"]
            y[end - 1] = TAG_ID[f"E-{t}"]
    return y


class Tagger(nn.Module):
    """sep=False: full conv blocks (3·H² MAC per unit per layer).
    sep=True: depthwise-separable blocks, depthwise dilated conv k=3 then a pointwise H×H linear
    (H² + 3H per layer): about 3x less compute for the same width."""

    def __init__(self, buckets: int = 1 << 16, emb: int = 32, hidden: int = 96, dilations=(1, 2, 4, 8, 1, 2, 4, 8), sep: bool = False):
        super().__init__()
        self.buckets = buckets
        self.sep = sep
        self.cfg = {"buckets": buckets, "emb": emb, "hidden": hidden, "dilations": list(dilations), "sep": sep}
        self.emb = nn.Embedding(buckets, emb)
        nn.init.normal_(self.emb.weight, std=0.1)
        self.proj = nn.Linear(emb, hidden)
        groups = hidden if sep else 1
        self.convs = nn.ModuleList(nn.Conv1d(hidden, hidden, 3, padding=d, dilation=d, groups=groups) for d in dilations)
        self.pws = nn.ModuleList(nn.Linear(hidden, hidden) for _ in dilations) if sep else None
        self.norms = nn.ModuleList(nn.LayerNorm(hidden) for _ in dilations)
        self.out = nn.Linear(hidden, len(TAGS))
        self.qat_emb_bits = 0  # set to 4 for quantization-aware fine-tuning of the embedding table

    def forward(self, feats: torch.Tensor) -> torch.Tensor:
        """feats: (B, T, N_FEATURES) int64 bucket ids -> logits (B, T, n_tags)."""
        w = self.emb.weight
        if self.qat_emb_bits:
            # fake per-row symmetric quantization with a straight-through gradient (matches py/export.py)
            qmax = 2 ** (self.qat_emb_bits - 1) - 1
            scale = (w.detach().abs().amax(1, keepdim=True) / qmax).clamp_min(1e-12)
            w = w + ((w / scale).round().clamp(-qmax, qmax) * scale - w).detach()
        x = self.proj(torch.nn.functional.embedding(feats, w).sum(2))
        for i, (conv, norm) in enumerate(zip(self.convs, self.norms)):
            h = conv(norm(x).transpose(1, 2)).transpose(1, 2)
            if self.sep:
                h = self.pws[i](h)
            x = x + torch.nn.functional.gelu(h)
        return self.out(x)

    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters())


def bucketize(f: np.ndarray, buckets: int) -> np.ndarray:
    return (f % np.uint32(buckets)).astype(np.int64)


RISK = {"CN_ID": "high", "CREDIT_CARD": "high", "BANK_ACCOUNT": "high", "SECRET": "high",
        "PERSON": "medium", "ADDRESS": "medium", "PHONE": "medium", "EMAIL": "medium", "IP": "medium",
        "OTHER_ID": "medium", "NATIONAL_ID": "medium", "ORG": "low", "PROJECT": "low"}


def decode(probs: np.ndarray, thresholds: dict[str, float], units: np.ndarray | None = None):
    """probs: (n, n_tags). A code unit is inside an entity when 1 - P(O) passes the threshold of the
    tier of its most likely type; runs of the same type form spans, split where the argmax tag is B or S.
    With `units`, every Latin/digit token (run of [0-9A-Za-z]) is all-or-nothing: kept whole, with
    its majority type, when at least half of it is inside, dropped otherwise. Masking half a word or
    a few digits of a number is never useful. Returns [(start, end, type, score)]."""
    n = len(probs)
    p_ent = 1.0 - probs[:, 0]
    by_type = probs[:, 1:].reshape(n, len(TYPES), 4)
    typ = by_type.sum(2).argmax(1)
    pos = by_type[np.arange(n), typ].argmax(1)  # 0 B, 1 I, 2 E, 3 S
    thr = np.array([thresholds[RISK[t]] for t in TYPES])[typ]
    inside = p_ent >= thr
    if units is not None and n:
        cls = char_class(units)
        word = (cls >= 2) & (cls <= 4)
        i = 0
        while i < n:
            if not word[i]:
                i += 1
                continue
            j = i
            while j < n and word[j]:
                j += 1
            k = int(inside[i:j].sum())
            if 0 < k < (j - i) / 2:
                inside[i:j] = False
            elif k:
                t = np.bincount(typ[i:j][inside[i:j]], minlength=len(TYPES)).argmax()
                inside[i:j], typ[i:j] = True, t
                pos[i + 1:j] = 1  # no split inside the token
                if pos[i] == 3:
                    pos[i] = 0  # S would end the span after one unit
                elif pos[i] == 2:
                    pos[i] = 1
            i = j
    spans, i = [], 0
    while i < n:
        if not inside[i]:
            i += 1
            continue
        j = i + 1
        while j < n and inside[j] and typ[j] == typ[i] and pos[j] not in (0, 3) and pos[j - 1] not in (2, 3):
            j += 1
        spans.append((i, j, TYPES[typ[i]], float(p_ent[i:j].mean())))
        i = j
    return spans
