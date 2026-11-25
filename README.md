# edge-redact

On-device PII redaction for Chinese, English and mixed text. Mask names, phone numbers, IDs, addresses and keys **before** you paste text into ChatGPT or Claude, then put the real values back into the reply. Nothing leaves the machine.

在本地遮盖中英文个人信息，发给 AI 之前先脱敏，回复回来再还原。

**Playground:** https://edge-redact.vercel.app

```sh
npm i edge-redact
```

```ts
import { redact, restore } from 'edge-redact'

const { text, mapping } = await redact('客户王建国，电话 138 0013 8000')
// text    → "客户[PERSON_1]，电话 [PHONE_1]"
// mapping → { "[PERSON_1]": "王建国", "[PHONE_1]": "138 0013 8000" }

restore(reply, mapping)
```

The model (1.35 MB) ships in the package and loads on the first call. Works in Node ≥ 20, browsers and Web Workers; zero runtime dependencies.

## How it works

1. **Rules + checksums**: ID cards, bank cards (Luhn), emails, phones, IPs, API keys.
2. **Heuristics**: context cues such as “联系人”, “收件人”, “Dear …”.
3. **Char-level model**: hashed n-gram embedding → dilated depthwise-separable CNN → BIOES. Only fills gaps the first two layers left; it never overrides a rule hit.

Every entity has a risk tier. `high` and `medium` are replaced by default; `low` (org and project names) is reported but kept.

**Fail closed:** any error (broken model, bad input, too long) throws `RedactError`. There is no code path that returns the original or a partly redacted text after something went wrong, and no silent fallback to rules only.

## API

```ts
// async, bundled model loaded once and cached
await redact(text, { tiers?, select?, entities?, model? })   // → { text, entities, mapping }
await detect(text, { model? })                              // → Entity[]
restore(reply, mapping)

// model: false → rules + heuristics only
await redact(text, { model: false })

// sync, bring your own model (e.g. inside a Web Worker)
const model = loadModel(await (await fetch(url)).arrayBuffer())
redactSync(text, { model })
detectSync(text, { model })

// load the weights from your own URL instead of the bundled file
const model = await loadDefaultModel('https://cdn.example.com/model.erdm')
```

The weights are also exported as `edge-redact/model.erdm`. Bundlers that understand `new URL(…, import.meta.url)` (Vite, webpack 5, Rollup, esbuild with a plugin) copy the file automatically.

## Accuracy

Medium-risk F2 on held-out benchmarks (rules + heuristics + model), negatives FP per 1k chars:

| | zh | en | mixed | FP / 1k |
| --- | ---: | ---: | ---: | ---: |
| rules + heuristics | 55.7 | 56.7 | 86.1 | 0.00 |
| **edge-redact** | **87.1** | **93.1** | **97.3** | **0.09** |

Speed (single thread, plain JS): 10k chars ≈ 170 ms, 2k chars ≈ 35 ms.

It will miss things. Look before you send. See [MODEL_CARD.md](MODEL_CARD.md) for data, metrics and known failure modes.

## Repository

- `src/`: runtime (rules, heuristics, CPU model, redact API)
- `playground/`: the web demo
- `training/`: data pipeline, training and benchmarks (Python + TS). Datasets are downloaded by `pnpm data` and never committed.

## License

MIT. The bundled model was trained on CC BY 4.0 data; see [MODEL_CARD.md](MODEL_CARD.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for attribution.
