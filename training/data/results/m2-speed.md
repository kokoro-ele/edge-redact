# M2 CPU reference: parity and speed (2026-11-25)

`src/model/cpu.ts` matches PyTorch: features bit for bit, logits ≤ 1e-4, decoded spans identical
(test/model.test.ts, fixtures from py/export.py). Corrupt model files throw ModelFormatError.

Speed, `node bench/speed.ts`, 10,000 UTF-16 units of mixed zh/en, Apple M5 Pro, Node 24, single thread,
float32 weights (int8 storage would not change compute):

| Model | hidden | MAC per unit (convs) | 10k units | medium F2 zh / en / mixed | FP/1k |
| --- | ---: | ---: | ---: | --- | ---: |
| s5-xs | 48 | 55 k | 467 ms | 83.6 / 93.5 / 96.4 | 0.69 |
| s5-sm | 64 | 98 k | 788 ms | 87.3 / 93.8 / 97.4 | 1.06 |
| s5 | 96 | 221 k | 1,680 ms | 87.5 / 93.6 / 97.8 | 0.11 |

Plain JS reaches ~1.3 GMAC/s; the PLAN target (10k < 50 ms) needs ~45 GMAC/s for s5. Not reachable by
code tuning alone: needs a much smaller compute budget, SIMD (WASM), or a relaxed target.

## Cheaper conv stacks (same s5 data, 64k × 32 embedding kept)

`ds*` = depthwise-separable blocks (`--sep`); pointwise matmul register-blocked over 4 positions in cpu.ts.
All timings re-measured together on an idle machine (an earlier run of the ds rows was ~2x slow: it was
taken while other jobs were still running). Parity tests pass for every export.
full+model, medium F2; gate = zh/mixed +10 over rules+heuristics (55.7 / 86.1), en no drop, FP/1k ≤ 0.5.

| Model | 10k units | zh / en / mixed | FP/1k | R-Score | gate |
| --- | ---: | --- | ---: | ---: | --- |
| s5 (full conv, h96) | 1,625 ms | 87.5 / 93.6 / 97.8 | 0.11 | 0.433 | pass |
| s5-xs (full conv, h48, 16k buckets) | 450 ms | 83.6 / 93.5 / 96.4 | 0.69 | 0.401 | fail |
| fc48 (full conv, h48) | 457 ms | 88.3 / 93.1 / 97.2 | 0.08 | 0.425 | pass |
| ds96 | 479 ms | 87.3 / 93.3 / 97.1 | 0.06 | 0.438 | pass |
| ds64 | 263 ms | 86.8 / 93.1 / 96.8 | 0.64 | 0.429 | fail (FP) |
| ds64x6 (6 layers) | 202 ms | 86.1 / 92.2 / 95.1 | 0.66 | 0.418 | fail (mixed +9.0, FP) |
| ds48 | 172 ms | 86.7 / 92.9 / 96.9 | 0.14 | 0.418 | pass |

## Quantization (ds48, scored through the TS runtime: `pnpm predict:ts`, then `pnpm bench`)

| Variant | file | zh / en / mixed | FP/1k | R-Score |
| --- | ---: | --- | ---: | ---: |
| PyTorch float | — | 86.7 / 92.9 / 96.9 | 0.14 | 0.418 |
| TS float32 | 9.0 MB | 86.7 / 92.9 / 96.9 | 0.14 | 0.418 (identical to PyTorch) |
| TS int8 PTQ | 2.4 MB | 86.7 / 92.9 / 96.9 | 0.15 | 0.419 |
| TS int4-emb PTQ | 1.35 MB | 86.3 / 92.9 / 96.9 | 0.13 | 0.424 |
| **TS int4-emb QAT (ds48q4)** | **1.35 MB** | **87.1 / 93.1 / 97.3** | **0.09** | 0.426 |

int4 = embedding table only (per-row, -7..7); other weights int8. ds48q4 = ds48 + 2,000 steps of fine-tuning
with fake-quantized int4 embedding (`--init ds48 --qat4`). Caveat: it is also 2,000 extra training steps, so
part of the gain over float ds48 may be extra training, not QAT. Shipped as `models/zh-en-ds48-int4.erdm`:
10k units 172 ms, 2k units 34 ms, load 12 ms (Node 24, M5 Pro, single thread).
