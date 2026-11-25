# edge-redact

On-device PII redaction for Chinese, English and mixed text. Mask names, phone numbers, IDs, addresses and keys **before** you paste text into ChatGPT or Claude, then put the real values back into the reply. Nothing leaves the machine.

**Playground:** https://edge-redact.vercel.app

<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="https://edge-redact.vercel.app/demo-dark.gif"><img alt="Paste text, copy the redacted version, restore the AI reply" src="https://edge-redact.vercel.app/demo-light.gif" width="720"></picture></p>

```sh
npm i edge-redact
```

## Quick start

```ts
import { redact, restore } from 'edge-redact'

// 1. redact locally
const { text, mapping } = await redact('客户王建国反馈订单没收到，电话 138 0013 8000，帮我写一段回复')
// text    → "客户[PERSON_1]反馈订单没收到，电话 [PHONE_1]，帮我写一段回复"
// mapping → { "[PERSON_1]": "王建国", "[PHONE_1]": "138 0013 8000" }

// 2. send `text` to any LLM; it only ever sees the placeholders
const reply = await yourLLM(text)
// reply   → "您好，我们已联系 [PHONE_1] 确认物流，[PERSON_1] 的订单今天补发。"

// 3. put the real values back, locally
restore(reply, mapping)
// → "您好，我们已联系 138 0013 8000 确认物流，王建国 的订单今天补发。"
```

`yourLLM` stands for whatever you already use (OpenAI, Anthropic, a local model). edge-redact does not call any API.

The model (1.35 MB) ships in the package and is loaded on the first call. Node ≥ 20, browsers and Web Workers; zero runtime dependencies.

## API

### `redact(text, options?)` → `Promise<{ text, entities, mapping }>`

Finds PII and replaces it with numbered placeholders.

- `text`: the redacted text.
- `mapping`: placeholder → original value. Keep it on your side; you need it for `restore`.
- `entities`: everything found, including the ones that were not replaced (see `tiers`).

Options (all optional):

| Option | Default | What it does |
| --- | --- | --- |
| `tiers` | `['high', 'medium']` | Which risk tiers to replace. Add `'low'` to also hide company and project names. |
| `select` | – | `(entity) => boolean`, decides per entity. Overrides `tiers`. Use it when a user un-ticks an item in your UI. |
| `entities` | – | Reuse the result of an earlier `detect()` on the same text instead of detecting again. |
| `model` | bundled model | `false` = rules and heuristics only (no model, smaller and faster, lower recall). |

### `restore(reply, mapping)` → `string`

Replaces every placeholder in `reply` with its original value. Placeholders not in `mapping` are left as they are.

### `detect(text, options?)` → `Promise<Entity[]>`

Only finds, does not replace. Useful for highlighting in a UI.

```ts
await detect('Contact Alice Wong at alice@example.com, Acme Corp')
// [
//   { start: 8,  end: 18, type: 'PERSON', risk: 'medium', score: 0.6,  source: 'heuristic' },
//   { start: 22, end: 39, type: 'EMAIL',  risk: 'medium', score: 0.99, source: 'rule' },
//   { start: 41, end: 50, type: 'ORG',    risk: 'low',    score: 0.6,  source: 'heuristic' },
// ]
```

`start` / `end` are string offsets (end exclusive). `source` says which layer found it.

### Entity types

| Risk | Types | Replaced by default |
| --- | --- | :---: |
| high | `CN_ID` (身份证), `CREDIT_CARD`, `BANK_ACCOUNT`, `JP_MYNUMBER`, `SECRET` (API keys, tokens, passwords) | yes |
| medium | `PERSON`, `PHONE`, `EMAIL`, `ADDRESS`, `IP`, `NATIONAL_ID` (passport, licence, SSN …), `OTHER_ID` | yes |
| low | `ORG`, `PROJECT` | no |

### Errors

Every function **fails closed**: a broken model file, input over `MAX_INPUT`, or any internal error throws `RedactError`. It never returns the original text or a partly redacted one, and it never silently falls back to rules only.

### Advanced

```ts
import { detectSync, loadDefaultModel, loadModel, redactSync } from 'edge-redact'

// load the weights from your own CDN instead of the bundled file
const model = await loadDefaultModel('https://cdn.example.com/model.erdm')

// or load them yourself, then call the sync versions (e.g. inside a Web Worker)
const model2 = loadModel(await (await fetch(url)).arrayBuffer())
redactSync(text, { model: model2 })
detectSync(text, { model: model2 })
```

The weights are also exported as `edge-redact/model.erdm`. Bundlers that understand `new URL(…, import.meta.url)` (Vite, webpack 5, Rollup) copy the file automatically.

Quick try in a browser console (pages with a strict CSP, such as GitHub or ChatGPT, block this):

```js
const { redact } = await import('https://cdn.jsdelivr.net/npm/edge-redact/dist/index.js')
```

## How it works

Three layers, in order. A later layer only fills gaps; it never overrides an earlier hit.

1. **Rules + checksums**: 身份证 (check digit), bank cards (Luhn), emails, phones, IPs, API keys.
2. **Heuristics**: context cues such as “联系人”, “收件人”, “Dear …”, labelled fields.
3. **Char-level model**: catches names, addresses and IDs written without any cue.

## Accuracy

### Benchmarks

4,030 held-out documents plus one external benchmark. None of them were used for training, and thresholds were tuned on a separate dev split; `training/py/check_isolation.py` checks ids, normalized text and every 64-char window.

| Set | Docs | Source |
| --- | ---: | --- |
| zh | 1,200 | [pii-bench-zh](https://huggingface.co/datasets/wan9yu/pii-bench-zh) (documents + chat), OpenPII-1.5M test (zh), held-out templates |
| en | 750 | [Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII) test, OpenPII-1.5M test (en), held-out templates |
| mixed | 580 | held-out zh/en code-switching templates |
| negatives | 1,500 | text with no PII: logs, stack traces, code, paths, versions, order numbers |
| [RedactionBench](https://huggingface.co/datasets/RedactionBench/RedactionBench) | 200 | English, 2.7 M chars, scored with its own R-Score |

**Metric.** Medium-risk F2 (recall weighted over precision, because a missed name is worse than an extra mask). An entity only counts as found if every character of it is covered. FP / 1k = false positives per 1,000 characters on the negatives set.

### Results

All rows run behind the same rules + heuristics layer, so the comparison is about the model part only.

| | Size | zh | en | mixed | FP / 1k | RedactionBench R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| rules + heuristics only | 0 | 55.7 | 56.7 | 86.1 | 0.00 | 0.365 |
| + [GLiNER multi PII](https://huggingface.co/urchade/gliner_multi_pii-v1) | ~1.2 GB | **88.9** | 80.2 | **98.4** | 8.81 | 0.360 |
| + [NVIDIA GLiNER-PII](https://huggingface.co/nvidia/gliner-PII) | ~1.8 GB | 75.5 | 89.6 | 92.8 | 11.81 | **0.499** |
| **+ edge-redact model** | **1.35 MB** | 87.1 | **93.1** | 97.3 | **0.09** | 0.426 |

Sizes are the Hugging Face repo download. GLiNER models were run on the same text with their recommended threshold (0.4).

What this says:

- Roughly 1/1000 the size of the GLiNER models, with similar or better recall on zh / en / mixed, and ~100× fewer false positives on code and logs.
- On RedactionBench (long English documents of many kinds) NVIDIA GLiNER-PII is better. For reference, the public leaderboard lists Claude Opus 5.5 at 0.832 and OpenAI Privacy Filter at 0.533, both much larger.
- The weakest set is Chinese chat (`zh-piibench-chat`), about two thirds medium recall.

Speed (single thread, plain JS, Apple M5 Pro): 10k chars 172 ms, 2k chars 34 ms, model load 12 ms.

It will miss things. Look before you send.

## Training

The goal: a model small enough to ship inside an npm package (< 3 MB) and fast enough to run as you type, that clearly beats rules + heuristics on medium-risk entities.

**Data.** Only openly licensed data and data written for this project:

- [Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII) train (en) and [OpenPII-1.5M](https://huggingface.co/datasets/ai4privacy/pii-masking-openpii-1.5m) train (zh + en), both CC BY 4.0, labels mapped to the 13 types above.
- Templates for zh, en and mixed text, written for this project (partly with Claude). They contain only slots; values are filled with fake data (ID birth years 2050–2099, test card numbers, RFC 2606 domains, documentation IP ranges). No real personal data.
- Hard negatives (code, logs, order numbers, fictional characters) to keep false positives down.

Each source was added as a separate stage and kept only if it helped on the benchmark:

| Stage | Data | zh | en | mixed | FP / 1k |
| --- | --- | ---: | ---: | ---: | ---: |
| s4 | Nemotron + OpenPII + templates + hard negatives | 84.7 | 93.2 | 91.5 | 0.41 |
| s5 | + Claude-written zh and zh/en templates | 87.5 | 93.6 | 97.8 | 0.11 |

No pseudo-labels from larger models were used; the GLiNER models above are only baselines.

**Model.** No tokenizer and no transformer:

- Each character gets 6 hashed char n-gram features → a 65,536 × 32 embedding table (99% of the parameters).
- 8 residual depthwise-separable conv blocks, hidden size 48, dilations 1-2-4-8 twice (receptive field ≈ 60 chars).
- A linear layer outputs BIOES tags for the 13 types; decode thresholds per risk tier are tuned on the dev split.

One model for both languages beat two separate zh / en models, even with a perfect language router, because mixed text has no good route.

**Making it small and fast.**

| Step | 10k chars | File | zh / en / mixed |
| --- | ---: | ---: | --- |
| full conv, hidden 96 | 1,625 ms | 9.3 MB float | 87.5 / 93.6 / 97.8 |
| depthwise-separable, hidden 48 | 172 ms | 9.0 MB float | 86.7 / 92.9 / 96.9 |
| int8 weights | 172 ms | 2.4 MB | 86.7 / 92.9 / 96.9 |
| int4 embedding (QAT) | 172 ms | **1.35 MB** | **87.1 / 93.1 / 97.3** |

Inference is plain TypeScript (`src/model/cpu.ts`) and matches PyTorch on the full benchmark.

Reproduce: `training/` has the data pipeline (`pnpm data`), training (`training/py/train.py`) and benchmarks (`pnpm bench`). Datasets are downloaded, never committed. Full numbers: [`training/data/results/`](training/data/results) and [MODEL_CARD.md](MODEL_CARD.md).

## Repository

- `src/`: runtime (rules, heuristics, CPU model, redact API)
- `playground/`: the web demo
- `training/`: data pipeline, training and benchmarks (Python + TS)

## License

MIT. The bundled model was trained on CC BY 4.0 data; see [MODEL_CARD.md](MODEL_CARD.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution.
