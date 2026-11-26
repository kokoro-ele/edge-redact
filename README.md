# edge-redact

**中文** | [English](README.en.md)

在本地给中文、英文和中英混合文本脱敏。把文本粘贴给 ChatGPT、Claude、DeepSeek 之类的 AI **之前**，先把姓名、手机号、身份证、地址、密钥换成占位符；AI 回复后再把真实信息填回去。全程在你自己的电脑上运行，数据不出本机。

**在线体验：** https://edge-redact.vercel.app

<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="https://edge-redact.vercel.app/demo-dark.gif"><img alt="粘贴文本，复制脱敏结果，再还原 AI 的回复" src="https://edge-redact.vercel.app/demo-light.gif" width="720"></picture></p>

```sh
npm i edge-redact
```

## 快速上手

```ts
import { redact, restore } from 'edge-redact'

// 1. 在本地脱敏
const { text, mapping } = await redact('客户王建国反馈订单没收到，电话 138 0013 8000，帮我写一段回复')
// text    → "客户[PERSON_1]反馈订单没收到，电话 [PHONE_1]，帮我写一段回复"
// mapping → { "[PERSON_1]": "王建国", "[PHONE_1]": "138 0013 8000" }

// 2. 把 text 发给任意大模型，它只会看到占位符
const reply = await yourLLM(text)
// reply   → "您好，我们已联系 [PHONE_1] 确认物流，[PERSON_1] 的订单今天补发。"

// 3. 在本地把真实信息填回去
restore(reply, mapping)
// → "您好，我们已联系 138 0013 8000 确认物流，王建国 的订单今天补发。"
```

`yourLLM` 指你自己已经在用的调用方式（OpenAI、Anthropic、DeepSeek、本地模型都行）。edge-redact 本身不调用任何接口。

模型（1.35 MB）随包发布，第一次调用时自动加载。支持 Node ≥ 20、浏览器和 Web Worker，没有运行时依赖。

## API

### `redact(text, options?)` → `Promise<{ text, entities, mapping }>`

找出个人信息，并替换成带编号的占位符。

- `text`：脱敏后的文本。
- `mapping`：占位符 → 原始值。留在你自己这边，`restore` 时要用。
- `entities`：找到的所有实体，包括没有被替换的（见 `tiers`）。

选项（都可以不传）：

| 选项 | 默认值 | 作用 |
| --- | --- | --- |
| `tiers` | `['high', 'medium']` | 替换哪些风险等级。加上 `'low'` 会把公司名、项目名也遮住。 |
| `select` | – | `(entity) => boolean`，逐个决定替不替换，优先于 `tiers`。适合界面里让用户取消勾选某一项。 |
| `entities` | – | 直接复用之前对同一段文本 `detect()` 的结果，不再重复识别。 |
| `model` | 内置模型 | 传 `false` 只用规则和启发式（不加载模型，更快，但召回更低）。 |

### `restore(reply, mapping)` → `string`

把 `reply` 里的占位符换回原始值。`mapping` 里没有的占位符保持原样。

### `detect(text, options?)` → `Promise<Entity[]>`

只识别、不替换，适合在界面上做高亮。

```ts
await detect('Contact Alice Wong at alice@example.com, Acme Corp')
// [
//   { start: 8,  end: 18, type: 'PERSON', risk: 'medium', score: 0.6,  source: 'heuristic' },
//   { start: 22, end: 39, type: 'EMAIL',  risk: 'medium', score: 0.99, source: 'rule' },
//   { start: 41, end: 50, type: 'ORG',    risk: 'low',    score: 0.6,  source: 'heuristic' },
// ]
```

`start` / `end` 是字符串下标（不含 end）。`source` 表示是哪一层识别出来的。

### 实体类型

| 风险 | 类型 | 默认替换 |
| --- | --- | :---: |
| 高 | `CN_ID`（身份证）、`CREDIT_CARD`（信用卡）、`BANK_ACCOUNT`（银行卡）、`JP_MYNUMBER`、`SECRET`（API key、token、密码） | 是 |
| 中 | `PERSON`（姓名）、`PHONE`（电话）、`EMAIL`（邮箱）、`ADDRESS`（地址）、`IP`、`NATIONAL_ID`（护照、驾照等证件号）、`OTHER_ID`（其他编号） | 是 |
| 低 | `ORG`（公司 / 机构）、`PROJECT`（项目名） | 否 |

### 出错时

所有函数都 **fail closed**：模型文件损坏、输入超过 `MAX_INPUT`、或任何内部错误，都会抛出 `RedactError`。不会返回原文或只脱敏了一部分的文本，也不会悄悄退回到只用规则。

### 进阶用法

```ts
import { detectSync, loadDefaultModel, loadModel, redactSync } from 'edge-redact'

// 从你自己的 CDN 加载模型，而不是用包里自带的文件
const model = await loadDefaultModel('https://cdn.example.com/model.erdm')

// 或者自己加载，再调用同步版本（比如在 Web Worker 里）
const model2 = loadModel(await (await fetch(url)).arrayBuffer())
redactSync(text, { model: model2 })
detectSync(text, { model: model2 })
```

模型文件也以 `edge-redact/model.erdm` 导出。支持 `new URL(…, import.meta.url)` 的打包工具（Vite、webpack 5、Rollup）会自动把它复制到产物里。

在浏览器控制台里快速试用（GitHub、ChatGPT 这类 CSP 严格的页面会拦截）：

```js
const { redact } = await import('https://cdn.jsdelivr.net/npm/edge-redact/dist/index.js')
```

## 原理

三层依次运行。后一层只补前一层漏掉的，不会推翻前一层的结果。

1. **规则 + 校验位**：身份证（校验码）、银行卡（Luhn）、邮箱、手机号、IP、API key。
2. **启发式**：上下文线索，比如“联系人”“收件人”“Dear …”、带标签的字段。
3. **字符级模型**：找出没有任何提示词的姓名、地址和编号。

## 准确率

### 评测集

4,030 条留出文档，外加一个外部基准。都没有用于训练，阈值在单独的验证集上调；`training/py/check_isolation.py` 会按 id、归一化文本和每个 64 字窗口检查有没有泄漏。

| 集合 | 条数 | 来源 |
| --- | ---: | --- |
| 中文 | 1,200 | [pii-bench-zh](https://huggingface.co/datasets/wan9yu/pii-bench-zh)（文档 + 聊天）、OpenPII-1.5M 测试集（中文）、留出模板 |
| 英文 | 750 | [Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII) 测试集、OpenPII-1.5M 测试集（英文）、留出模板 |
| 中英混合 | 580 | 留出的中英混写模板 |
| 负样本 | 1,500 | 不含个人信息的文本：日志、报错堆栈、代码、路径、版本号、订单号 |
| [RedactionBench](https://huggingface.co/datasets/RedactionBench/RedactionBench) | 200 | 英文，270 万字符，用它自带的 R-Score 打分 |

**指标。** 中风险实体的 F2（召回权重高于精确率，因为漏掉一个名字比多遮一处更糟）。一个实体只有每个字都被遮住才算找到。误报 / 千字 = 在负样本上每 1,000 个字符的误报数。

### 结果

每一行都跑在同一套规则 + 启发式之上，所以比较的只是模型这一层。

| | 大小 | 中文 | 英文 | 混合 | 误报 / 千字 | RedactionBench R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 仅规则 + 启发式 | 0 | 55.7 | 56.7 | 86.1 | 0.00 | 0.365 |
| + [GLiNER multi PII](https://huggingface.co/urchade/gliner_multi_pii-v1) | ~1.2 GB | **88.9** | 80.2 | **98.4** | 8.81 | 0.360 |
| + [NVIDIA GLiNER-PII](https://huggingface.co/nvidia/gliner-PII) | ~1.8 GB | 75.5 | 89.6 | 92.8 | 11.81 | **0.499** |
| **+ edge-redact 模型** | **1.35 MB** | 87.1 | **93.1** | 97.3 | **0.09** | 0.426 |

大小是 Hugging Face 仓库的下载体积。GLiNER 模型用同样的文本、按推荐阈值（0.4）运行。

结论：

- 体积约为 GLiNER 模型的千分之一，中文、英文、混合的召回相近或更好，在代码和日志上的误报少约 100 倍。
- 在 RedactionBench（各类英文长文档）上 NVIDIA GLiNER-PII 更好。作为参考，公开排行榜上 Claude Opus 5.5 是 0.832，OpenAI Privacy Filter 是 0.533，两者都大得多。
- 最弱的是中文聊天（`zh-piibench-chat`），中风险召回大约三分之二。

速度（单线程、纯 JS、Apple M5 Pro）：1 万字 172 ms，2 千字 34 ms，模型加载 12 ms。

它一定会有漏网之鱼，发送前请自己再看一眼。

## 训练思路

目标：模型要小到能直接放进 npm 包（< 3 MB），快到能边打字边跑，并且在中风险实体上明显超过规则 + 启发式。

**数据。** 只用开放许可的数据和为本项目编写的数据：

- [Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII) 训练集（英文）和 [OpenPII-1.5M](https://huggingface.co/datasets/ai4privacy/pii-masking-openpii-1.5m) 训练集（中英文），均为 CC BY 4.0，标签映射到上面的 13 种类型。
- 为本项目编写的中文、英文、中英混合模板（部分由 Claude 编写）。模板里只有槽位，值用假数据填充（身份证出生年份 2050–2099、测试卡号、RFC 2606 保留域名、文档专用 IP 段），不含任何真实个人信息。
- 负样本（代码、日志、订单号、虚构人物），用来压低误报。

每种数据作为单独一个阶段加入，只有在基准上有提升才保留：

| 阶段 | 数据 | 中文 | 英文 | 混合 | 误报 / 千字 |
| --- | --- | ---: | ---: | ---: | ---: |
| s4 | Nemotron + OpenPII + 模板 + 负样本 | 84.7 | 93.2 | 91.5 | 0.41 |
| s5 | + Claude 编写的中文、中英混合模板 | 87.5 | 93.6 | 97.8 | 0.11 |

没有使用大模型生成的伪标签；上面的 GLiNER 模型只作为对比基线。

**模型。** 不用分词器，也不用 Transformer：

- 每个字符取 6 个哈希字符 n-gram 特征 → 65,536 × 32 的嵌入表（占 99% 的参数）。
- 8 个残差深度可分离卷积块，隐藏维度 48，空洞率 1-2-4-8 重复两次（感受野约 60 个字符）。
- 线性层输出 13 种类型的 BIOES 标签；各风险等级的解码阈值在验证集上调。

一个中英通用模型胜过分开的中文、英文两个模型，即使给后者配上完美的语言路由也一样，因为中英混写的文本没法路由。

**压小、提速。**

| 步骤 | 1 万字 | 文件 | 中文 / 英文 / 混合 |
| --- | ---: | ---: | --- |
| 普通卷积，隐藏维度 96 | 1,625 ms | 9.3 MB（float） | 87.5 / 93.6 / 97.8 |
| 深度可分离卷积，隐藏维度 48 | 172 ms | 9.0 MB（float） | 86.7 / 92.9 / 96.9 |
| int8 权重 | 172 ms | 2.4 MB | 86.7 / 92.9 / 96.9 |
| 嵌入表 int4（量化感知训练） | 172 ms | **1.35 MB** | **87.1 / 93.1 / 97.3** |

推理是纯 TypeScript 实现（`src/model/cpu.ts`），在完整基准上与 PyTorch 结果一致。

复现：`training/` 里有数据管线（`pnpm data`）、训练（`training/py/train.py`）和评测（`pnpm bench`）。数据集是下载的，从不提交进仓库。完整数据见 [`training/data/results/`](training/data/results) 和 [MODEL_CARD.md](MODEL_CARD.md)。

## 目录结构

- `src/`：运行时（规则、启发式、CPU 模型、脱敏 API）
- `playground/`：网页演示
- `training/`：数据管线、训练和评测（Python + TS）

## 许可证

MIT。内置模型使用 CC BY 4.0 数据训练，署名信息见 [MODEL_CARD.md](MODEL_CARD.md) 和 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
