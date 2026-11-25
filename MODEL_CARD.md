# Model card: zh-en-ds48-int4

The model bundled with `edge-redact` (`models/zh-en-ds48-int4.erdm`, 1.35 MB).

## Model

- Input: UTF-16 units; 6 hashed char n-gram features per position → embedding 65,536 × 32.
- 8 residual depthwise-separable conv blocks (hidden 48, dilations 1, 2, 4, 8, 1, 2, 4, 8).
- Output: BIOES tags over 13 entity types.
- Quantization: embedding int4 (QAT, per-row scales), other weights int8.
- Runtime: pure TypeScript (`src/model/cpu.ts`), parity with PyTorch checked on the full benchmark.

The model is one layer of three. Rules and heuristics run first; the model only adds spans where nothing was found.

## Training data

| Source | Licence | Use |
| --- | --- | --- |
| [nvidia/Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII), train split | CC BY 4.0 | en |
| [ai4privacy/pii-masking-openpii-1.5m](https://huggingface.co/datasets/ai4privacy/pii-masking-openpii-1.5m), train split | CC BY 4.0 | zh, en |
| Templates written for this project (`training/data/templates`, `training/data/synth`) | MIT (this repo) | zh, en, mixed; slots only |
| Hard negatives written for this project | MIT (this repo) | false-positive control |

Template values are filled by `training/py/fakes.py` with fake data (ID birth years 2050–2099, test card BINs, RFC 2606 email domains, documentation IP ranges). No teacher-model pseudo-labels were used.

Attribution (CC BY 4.0): “Nemotron-PII” by NVIDIA; “OpenPII-1.5M” by Ai Suisse SA (ai4privacy). Changes: spans were mapped to this project's label set and combined with the data above.

Benchmark sets (pii-bench-zh, RedactionBench, the test/validation splits above, held-out templates) were never used for training; `training/py/check_isolation.py` checks ids, normalized text and 64-char windows.

## Metrics

Medium-risk F2, shipped combination (rules + heuristics + model):

| | zh | en | mixed | FP / 1k chars (negatives) | RedactionBench R |
| --- | ---: | ---: | ---: | ---: | ---: |
| rules + heuristics | 55.7 | 56.7 | 86.1 | 0.00 | 0.365 |
| edge-redact | 87.1 | 93.1 | 97.3 | 0.09 | 0.44 |

Speed on an M5 Pro, one thread: 10k chars 172 ms, 2k chars 34 ms.

## Known failure modes

- Chinese names right before a verb (“用户刘洋反馈”) can be missed.
- Short or partial addresses (a single province character) and broken-up key fragments.
- Chat-style Chinese (`zh-piibench-chat`) is the weakest set, roughly two thirds medium recall.
- Context-only IDs (passport, driver's licence without a label) are hard for all layers.

Always review the redacted text before sending it.
