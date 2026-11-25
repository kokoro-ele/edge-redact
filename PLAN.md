# edge-redact — PLAN

在浏览器里本地运行的 PII 脱敏小模型（中 / 英）。用户把文本贴进 ChatGPT / Claude 之前，先在本机把个人信息遮住；数据不出本机。

方法论沿用 [antfu/gpu-icons-search](https://github.com/antfu/gpu-icons-search)：先有数据和 benchmark，先测不用模型的强基线；训练数据分阶段加，benchmark 涨了才保留；量化感知训练；CPU 参考实现与 WGSL 输出对齐；有明确的上线门槛。

## 状态

- **M0 完成**：数据下载、benchmark、规则基线、规则 + 启发式基线、teacher 参考基线。`pnpm bench` 一条命令出表，结果见 [`training/data/results/m0-baselines.md`](training/data/results/m0-baselines.md)。
- 2026-11-24 范围调整：只做中文和英文（含中英混写），去掉日语。日语数据集、日语 benchmark、日语模板已移除。
- M1–M4 未开始；没有写模型代码。

## 已定决策（来自需求）

| 项 | 决定 |
| --- | --- |
| 检测分层 | 第 1 层：规则 + 校验（邮箱、电话、信用卡 Luhn、身份证校验位、IP、API key / token / JWT / DB 连接串）。第 2 层：小模型，处理依赖上下文的实体（人名、地址、公司、项目代号）。 |
| 模型形式 | 字符级 token classification，BIOES 标签。 |
| 特征 | 哈希的字符片段：单字 + 字 bigram + 字 trigram，无 tokenizer。 |
| 风险分级 | 高（身份证、银行卡、密钥）：自动遮盖。中（人名、地址、电话）：低阈值，高亮给用户确认。低（公司、项目代号）：高阈值，仅提示。 |
| 失败处理 | fail closed：检测出错或崩溃时，绝不放行原文。 |
| 语言 | 中文、英文，中英混写是常态。默认一个混合模型；对照实验：同总大小的两个单语模型。 |
| 大小 | 在 100 KB – 3 MB 之间训练多个尺寸，取不掉分的最小者。 |
| 运行时 | TypeScript CPU 参考实现为默认后端；手写 WGSL 为可选后端；两者在容差内一致。运行时零依赖。 |
| 工具链 | pnpm workspace；Python 用 uv；训练用 PyTorch。 |

## 默认决定（2026-11-24 已全部确认）

以下默认值你已确认（“都可以”）。改动只影响标注映射或评分脚本，不需要重做数据。

1. **仓库名** `edge-redact`。
2. **实体分类与分级**（`src/types.ts`）：
   - 高：`CN_ID`、`CREDIT_CARD`、`BANK_ACCOUNT`（含 IBAN）、`SECRET`（密钥、token、密码、PIN、CVV）。
   - 中：`PERSON`、`ADDRESS`、`PHONE`、`EMAIL`、`IP`、`OTHER_ID`（车牌、病历号、MAC、设备号）、`NATIONAL_ID`（护照、驾照、SSN、税号等）。`NATIONAL_ID` 没有校验位、常常没有固定格式，无上下文时 99.5% 召回做不到，所以降为中风险：高亮给用户确认，不自动遮盖（2026-11-24 确认）。
   - 低：`ORG`、`PROJECT`。
   - 需求里没给 EMAIL、IP 定级，我放在中风险。CVV / PIN 放进 `SECRET`（高）。
3. **不计分的标签**（IGNORE：既不要求检出，检出也不算误报）：用户名、客户号、员工号等内部 ID；日期、年龄、性别、职业、URL、国家、银行名。理由：这些在 LLM 对话里很常见，强制遮盖会毁掉可用性；但它们由数据集标注，模型检出不应被罚。
4. **地址合并**：数据集里的街道、门牌、城市等碎片合并成一个 `ADDRESS`；只有包含门牌或楼号等锚点时才算地址，否则整组 IGNORE（“东京都”单独出现不算 PII）。人名的姓、名碎片在间隔 ≤ 2 个空白或 `・`、`·` 时合并成一个 `PERSON`。
5. **评分规则**（`training/src/score.ts`）：
   - 按实体 span 计：金标实体的每个非空白字符都被同级或更高级的预测覆盖，才算检出；部分覆盖算漏。
   - 预测至少一半字符落在金标或 IGNORE 上、且碰到金标，算 TP；只落在 IGNORE 上不计；其余算 FP。
   - 高风险召回下限 99.5%，先过下限再比精度；中、低风险报 R / P / F2；无 PII 集报 FP / 千字。
6. **偏移统一用 UTF-16**（与 JS 字符串一致），Python 侧转换。
7. **数据用途**：Gretel 只用于训练（金标不全，不能计分）；pii-bench-zh 只用于评测（卡片写明仅限研究与评测）。
8. **随机生成的电话号码可以接受**：它们不入库（只在 `.cache` 里生成）；入库的模板只有槽位。身份证号用 2050–2099 出生年份，卡号只用测试 BIN，邮箱只用保留域名，IP 只用文档段或内网段。
9. **内网 IP（10.x、192.168.x）也标为 IP**（中风险，高亮确认）。理由：内网拓扑泄露同样敏感；误报成本低。
10. **Teacher 蒸馏**：已确认可以用 teacher（含 nvidia/gliner-PII，NVIDIA Open Model License）的输出给训练数据打伪标。只标训练数据，绝不碰 benchmark；伪标数据作为 M1 的一个独立阶段，benchmark 涨了才保留。发布模型时在 MODEL_CARD 里注明用过哪些 teacher。
11. **信用卡召回同时报“校验有效”子集**：Nemotron 里约 2/3 的卡号过不了 Luhn（数据集造数问题）。规则层故意要求 Luhn，所以总召回会偏低；上线门槛按校验有效子集算。
12. **Benchmark 规模**：每个来源 300–400 篇，模板集每语言 150 篇、混合 400 篇、负例 1500 篇（见 `training/data/manifests/bench.json`）。
13. **中文合成数据**：让 Claude 写**模板**（槽位，不写值），值由 `fakes.py` 填。这样模型不可能写出真实个人信息，金标偏移也是精确的。脚本：`training/py/synth_zh.py`（Batch API）。已确认要跑（约 600 条模板，claude-opus-5-5）；需要本机有 Claude API 凭据。重点补中英混写，mixed-tmpl 测试集偏小。

## 目录结构

```
edge-redact/
├── PLAN.md                     本文件
├── THIRD_PARTY_NOTICES.md      数据集、模型的许可与出处
├── package.json                根包（运行时零依赖）；pnpm m0 / data / teacher / bench / test
├── pnpm-workspace.yaml
├── src/                        运行时（TypeScript，零依赖）
│   ├── index.ts
│   ├── types.ts                实体分类、风险分级
│   ├── rules/                  第 1 层：正则 + 校验位
│   │   ├── index.ts
│   │   └── checksums.ts        Luhn、GB 11643、My Number、IBAN
│   ├── heuristics/             基线 2：姓氏词典 + 敬称 / 上下文线索（不进最终产品，只作对照）
│   └── model/                  M2：CPU 参考推理；M3：WGSL
├── test/                       运行时单测（node --test）
├── training/
│   ├── package.json            pnpm data / teacher / bench
│   ├── pyproject.toml          uv 项目；extras: teacher、synth
│   ├── py/
│   │   ├── sources.py          数据源与固定的 revision
│   │   ├── download.py         下载到 .cache/raw/
│   │   ├── labels.py           各数据集标签 → 本项目分类
│   │   ├── fakes.py            假数据生成器（种子固定）
│   │   ├── prepare.py          生成 benchmark：.cache/bench/*.jsonl
│   │   ├── check_isolation.py  benchmark 不进训练数据的检查
│   │   ├── teacher.py          跑 teacher 模型，缓存预测
│   │   └── synth_zh.py         中文模板合成（Claude Batch API）
│   ├── src/
│   │   ├── score.ts            span 级评分
│   │   ├── bench.ts            打印基线表（--write 存档）
│   │   └── misses.ts           查漏检 / 误报的调试工具
│   ├── data/
│   │   ├── templates/          pii.tsv（90 条）、neg.tsv（80 条硬负例）
│   │   ├── synth/              合成的中文模板（入库，只有槽位）
│   │   ├── manifests/          benchmark 清单、模板划分
│   │   └── results/            每个里程碑的结果表
│   └── .cache/                 下载与生成的数据（git 忽略）
└── playground/                 M4：浏览器演示页
```

## Benchmark

| 集合 | 语言 | 篇数 | 来源 | 说明 |
| --- | --- | ---: | --- | --- |
| en-nemotron | en | 300 | Nemotron-PII test | |
| en-openpii | en | 300 | openpii validation | |
| zh-openpii | zh | 300 | openpii validation | 机翻痕迹重，质量差 |
| zh-piibench / zh-piibench-chat | zh | 300 + 300 | pii-bench-zh | 仅评测 |
| zh / en-tmpl | 各语言 | 150 × 2 | 测试划分的模板 + 假值 | |
| mixed-tmpl | mixed | 400 | 测试划分的模板 + 假值 | 中英混写，主要场景；测试模板只有 11 条，偏小 |
| redactionbench（外部） | en | 200 | RedactionBench，官方 R-Score 评分（`pnpm rbench`） | 不分类型；真实网页文档占一半；可与其排行榜对比；仅评测 |
| neg-tmpl | 混合 | 1500 | 硬负例模板 | 日志、堆栈、代码、路径、版本号、订单号、型号、虚构角色名；无 PII |

**隔离**：模板按 `hash(id) % 2` 分训练 / 测试（记录在 `template-splits.json`）；`check_isolation.py` 检查模板划分、Nemotron-en train/test 不重叠，训练数据建成后再检查 id、规范化全文、64 字窗口三层不重合。`pnpm data` 每次都跑这个检查。

## 里程碑

### M0 — 数据、benchmark、全部基线 ✅

- [x] 数据源许可核查，固定 revision，写入 THIRD_PARTY_NOTICES.md
- [x] 标签映射、地址 / 人名合并、UTF-16 偏移、偏移一致性检查（全部集合 0 不一致）
- [x] 模板与假数据生成器（去掉日语后 pii 49 条、neg 51 条）
- [x] span 级评分 + 单测（金标当预测 = 100%）
- [x] 基线：规则；规则 + 启发式；teacher × 3
- [x] `pnpm bench` 一条命令出表

完成标准：一条命令输出分语言、分风险级的基线表。✅

### M1 — 训练数据 + 第一个模型

- 训练数据管线：Nemotron-en train、openpii train（zh/en）、Gretel、训练划分的模板、合成中文模板、硬负例。
- 分阶段加数据，每阶段跑 benchmark，涨了才保留，记录在 `training/data/results/m1-stages.md`：
  1. Nemotron（en）
  2. + openpii
  3. + 模板（训练划分）
  4. + 合成中文
  5. + 硬负例加权
  6. + teacher 伪标注（第 10 条已确认）
- 模型：哈希 n-gram embedding → 小型 CNN 或 BiGRU → BIOES。PyTorch。
- 尺寸扫描：100 KB、300 KB、1 MB、3 MB（int8 量化后）。
- 对照实验：混合模型 vs 两个单语模型（总大小相同）。

完成标准（**闸门**）：在中风险实体上，模型 + 规则的 F2 明显高于规则 + 启发式。具体为 zh、mixed 各提升 ≥ 10 个百分点，en 不下降，负例 FP / 千字不超过 0.5。达不到就停下来讨论。

### M2 — 量化感知训练 + CPU 参考实现

- int8（可试 int4）QAT；导出权重格式（二进制 + JSON 头）。
- `src/model/cpu.ts`：纯 TS 推理，零依赖。
- 一致性：TS 与 PyTorch（量化模拟）的 logits 误差 ≤ 1e-4，标签序列 100% 一致。
- 组合检测：规则优先；模型只补第 2 层实体；按风险分级给阈值。
- fail closed：`redact()` 出错时抛异常，不返回部分结果；故障注入测试覆盖（权重损坏、超长输入、异常字符）。

完成标准：TS 实现在 benchmark 上的分数与 PyTorch 一致；~~1 万字 < 50 ms~~ → **1 万字 < 400 ms、2 千字 < 80 ms（M5 Pro，单线程，在 Web Worker 中运行）**。

> 2026-11-25 改目标（已确认）：纯 JS 单线程只有 ~1–2 GMAC/s，s5（h96 全卷积）1 万字 1.6 s。改用深度可分离卷积 ds48（h48，8 层），再对 embedding 做 int4 QAT：`models/zh-en-ds48-int4.erdm`，1.35 MB，1 万字 172 ms、2 千字 34 ms，zh / en / mixed 87.1 / 93.1 / 97.3，FP 0.09/千字（比 s5 只低 0.4 / 0.5 / 0.5）。TS 运行时 bench 分数与 PyTorch 一致。int8 PTQ 不掉分；int4 PTQ 掉 0.4（zh），QAT 补回。详见 [`training/data/results/m2-speed.md`](training/data/results/m2-speed.md)。

### M3 — WGSL 后端（可选）

- 手写 WGSL kernel；与 CPU 参考实现在容差内一致（logits 误差 ≤ 1e-3，标签一致率 ≥ 99.99%）。
- 只有长文本明显更快时才默认启用。

### M4 — 上线门槛 + 演示

- **上线门槛**：
  - 高风险：校验有效子集召回 ≥ 99.5%（各语言），且负例上高风险误报为 0。
  - 中风险：F2 达到 M1 闸门，且不低于 M1 结果。
  - 负例 FP / 千字 ≤ 0.5。
  - 包大小 ≤ 选定尺寸；运行时无依赖；fail closed 测试通过。
- MODEL_CARD.md：数据、指标、已知失败模式、许可与署名。
- playground：静态网页，粘贴 → 高亮 → 确认 → 复制脱敏文本。

## 风险

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 中文开放数据质量差（openpii zh 是机翻，名字和号码不真实） | 中文模型学到的是数据集的伪影 | 合成模板补数据；zh benchmark 以 pii-bench-zh 和模板集为主，openpii zh 单独报 |
| 模板集偏向启发式：模板和启发式都是我写的 | 启发式在 *-tmpl 集上的分数虚高 | 分来源报表；闸门要求在非模板集上也成立 |
| 硬负例集也是我写的 | 规则在负例上 0 误报可能是过拟合 | M1 加入真实开源代码、日志片段作负例（只取无 PII 的许可友好来源） |
| 数据集金标的伪影（卡号不过 Luhn、http_cookie 范围过宽、护照号无格式） | 高风险召回下限无法用规则达到 | 分“校验有效”子集报；上线门槛按有效子集；NATIONAL_ID 靠模型 + 上下文 |
| 高风险下限 99.5% 对上下文型 ID（护照、驾照、税号）很难 | 上线门槛过不去 | 这些 ID 若无上下文，可降为中风险高亮；需要讨论 |
| Teacher 只懂英文，或许可不允许蒸馏 | 无法用伪标注扩数据 | 先测 teacher 在 zh 上的分数（M0 已测）；许可不清就不用 |
| 字符级小模型对长距离上下文弱（“负责人是……”） | 中风险召回上限 | 尺寸扫描里比较 CNN 感受野与 BiGRU；必要时加规则线索特征 |

## 测量结果

### M0（2026-11-24，范围调整为中英后重跑）

完整表：[`training/data/results/m0-baselines.md`](training/data/results/m0-baselines.md)。中风险 F2 与负例误报：

| 方法 | zh | en | mixed | 负例 FP / 千字 |
| --- | ---: | ---: | ---: | ---: |
| 规则 | 34.8 | 35.4 | 42.3 | 0.00 |
| 规则 + 启发式 | 53.9 | 56.7 | 82.6 | 0.00 |
| 规则 + gliner-multi-pii | **85.4** | 71.1 | **99.4** | 8.81 |
| 规则 + nvidia/gliner-PII | 67.2 | **72.3** | 86.8 | 11.81 |
| 规则 + ai4privacy | 47.1 | 59.4 | 55.5 | 14.34 |

（2026-11-25 更新：NATIONAL_ID 降为中风险；修正 en-nemotron 的重复 id——Nemotron 一个 uid 对应两行，预测按 id 对齐时串了文档，之前 en 列的 teacher 分数有误。bench.ts 现在遇到重复 id 直接报错。）

结论：
- 没有任何方法过高风险召回下限（99.5%）。主要缺口是 NATIONAL_ID（护照、驾照等无固定格式）、BANK_ACCOUNT、SECRET，以及数据集里过不了 Luhn 的卡号。校验有效的卡号、身份证，规则召回为 98.6–100%。
- Teacher 在中风险上明显强于启发式（真实数据集上尤其明显），但在硬负例上每千字 9–14 个误报：commit SHA、端口号当密钥，订单号当证件号，型号当 ID，虚构角色名当人名。这正是小模型 + 硬负例训练要解决的。
- 启发式在 *-tmpl 上分数偏高（模板和启发式都是我写的）；看真实数据集各行更可信。去掉日语后 mixed-tmpl 只剩 11 条测试模板，接近饱和（99.4），M1 前要用合成模板扩充。
- ai4privacy 模型需要自己聚合 token（pipeline 自带聚合会把词切碎），修正后仍几乎不识别人名。
- 规则层里的 My Number、日本电话等规则暂时保留（不影响中英分数，负例 0 误报）；M2 组装运行时再决定是否删。

### RedactionBench（外部，en，2026-11-24）

`pnpm rbench`，官方 R-Score，200 篇（一半为真实网页文档）。完整表：[`training/data/results/redactionbench.md`](training/data/results/redactionbench.md)。所有检出一律遮盖，阈值固定、不在该集上调。

| 方法 | R-Score | Mandatory 覆盖 | 排行榜同模型（阈值在该集上调过） |
| --- | ---: | ---: | ---: |
| 规则 | 0.261 | 33.8% | |
| 规则 + 启发式 | 0.365 | 40.1% | |
| nvidia/gliner-PII | 0.487 | 55.2% | 0.339 |
| 规则 + nvidia/gliner-PII | **0.507** | 61.8% | |
| gliner-multi-pii | 0.293 | 28.1% | 0.309 |
| ai4privacy multilingual | 0.214 | 35.6% | 0.180 |

- gliner-multi 和 ai4privacy 与排行榜接近，说明评分接入正确；nvidia 比排行榜高 0.15，可能来自分块（约 364 token）和标签提示词不同，未核实。
- 规则 + 启发式（0 参数）已高于排行榜上的 nvidia/gliner-PII（0.339）和 gliner-multi（0.309）。
- 参照：OpenAI Privacy Filter 0.533，Claude Opus 5.5 0.832。M1 小模型 + 规则的英文目标：明显高于 0.365，争取接近 0.5。
- 接入时发现并修了启发式在代码里的误报（`container_name:` 当人名、`password=config.x` 当密钥），R-Score 0.352 → 0.365。
