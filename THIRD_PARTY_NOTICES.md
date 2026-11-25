# Third-party notices

The repository contains no third-party data. `pnpm data` downloads the datasets below into `training/.cache/` (git-ignored), at the pinned revisions in `training/py/sources.py`. Licences were checked on the dataset and model cards on 2026-11-24. None of the sources used needs a login or click-through agreement.

## Datasets

| Source | Revision | Licence | Use here | Notes |
| --- | --- | --- | --- | --- |
| [nvidia/Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII) | `b70ffaf5` | CC BY 4.0 | en benchmark (test parquet), training (train parquet) | Synthetic. Both parquet files hold 100k rows, not the 50k/50k the card states; they do not overlap. About two thirds of the credit-card values fail the Luhn check. |
| [ai4privacy/pii-masking-openpii-1.5m](https://huggingface.co/datasets/ai4privacy/pii-masking-openpii-1.5m) | `a785eb52` | CC BY 4.0, © 2026 Ai Suisse SA | zh / en benchmark (validation split), training (train split) | Synthetic and largely machine-translated; zh quality is low (see PLAN.md). The gated 200k / 400k "extended" sets are not used. |
| [gretelai/synthetic_pii_finance_multilingual](https://huggingface.co/datasets/gretelai/synthetic_pii_finance_multilingual) | `7b844d16` | Apache-2.0 | training only | Gold labels are incomplete, so it is not used for scoring. |
| [RedactionBench/RedactionBench](https://huggingface.co/datasets/RedactionBench/RedactionBench) (`documents.ndjson` and the official scorer `score.py`, `rscore_v2*.py`) | `77684d7e` | CC BY 4.0 | en external benchmark only (`pnpm rbench`) | 101 public-web documents (randomized values) and 99 synthetic. Never used for training; isolation check covers it. |
| [wan9yu/pii-bench-zh](https://huggingface.co/datasets/wan9yu/pii-bench-zh) (`pii_bench_zh.jsonl`, `pii_bench_zh_chat.jsonl`) | `c350b948` | Apache-2.0; card says "research and evaluation only" | zh benchmark only | Never used for training. |

Attribution required by CC BY 4.0: "Nemotron-PII" by NVIDIA; "RedactionBench" by the RedactionBench authors; "OpenPII-1.5M" by Ai Suisse SA (ai4privacy). If a trained model is published, its model card repeats these attributions.

## Teacher models (evaluation baseline; distillation not yet decided)

| Model | Revision | Licence | Note |
| --- | --- | --- | --- |
| [nvidia/gliner-PII](https://huggingface.co/nvidia/gliner-PII) | `bd23e8ef` | NVIDIA Open Model License | English-trained. Whether its outputs may label our training data is an open question (PLAN.md, "默认决定，待确认"). |
| [urchade/gliner_multi_pii-v1](https://huggingface.co/urchade/gliner_multi_pii-v1) | `1fcf13e8` | Apache-2.0 | Multilingual GLiNER. |
| [ai4privacy/llama-ai4privacy-multilingual-categorical-anonymiser-openpii](https://huggingface.co/ai4privacy/llama-ai4privacy-multilingual-categorical-anonymiser-openpii) | `83ef30d5` | MIT | Card lists European languages only. |

## Synthetic data written in this repository

- `training/data/templates/*.tsv`: written by Claude (claude-opus-5-5). The templates hold slots, not values.
- `training/data/synth/zh-templates.jsonl` (once generated): written by Claude via `training/py/synth_zh.py`. It also holds slots only and is scrubbed for literal values.
- Values are filled at build time by `training/py/fakes.py`. Chinese ID numbers use birth years 2050–2099, cards use test BINs, emails use reserved domains (RFC 2606), and IPs use documentation or private ranges.
