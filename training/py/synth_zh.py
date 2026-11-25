"""Synthesise Chinese (and zh-mixed) *templates* with the Claude Message Batches API.

    uv run --extra synth python py/synth_zh.py submit  [--n 400]   # writes .cache/synth/batch.json
    uv run --extra synth python py/synth_zh.py collect             # writes data/synth/zh-templates.jsonl

Why templates and not finished text: the model writes slots such as {NAME_ZH} or {PHONE_CN} instead of
values, and training/py/fakes.py fills them later. The model therefore never writes a personal value, so
the committed output cannot hold real PII, and the gold offsets are exact. Every template is scrubbed
(see `scrub`) before it is written; rejected ones are counted, not kept.

Synthesised templates go to training only. They get fresh ids (s0001...) and never enter the benchmark;
py/check_isolation.py verifies that once training data is built.

Needs a Claude API key: ANTHROPIC_API_KEY in the environment or in training/.env (git-ignored). Not run in M0.
"""

import argparse
import json
import re
import sys
import time

from common import ROOT
from fakes import NEUTRAL_SLOTS, PII_SLOTS

MODEL = "claude-opus-5-5"
OUT = ROOT / "data" / "synth" / "zh-templates.jsonl"
STATE = ROOT / ".cache" / "synth" / "batch.json"
# zh / en scope (2026-11-24): Japanese-only slots are neither offered nor accepted.
JA_SLOTS = {"NAME_JA", "SURNAME_JA", "ADDR_JA", "ORG_JA", "PHONE_JP", "BANK_JP", "MYNUMBER"}
PII_OFFERED = sorted(set(PII_SLOTS) - JA_SLOTS)
SLOTS = set(PII_OFFERED) | NEUTRAL_SLOTS

# Scenario × register grid. Each request asks for 10 templates in one scenario.
SCENARIOS = [
    "客服工单（电商退款、物流投诉）", "HR 入职材料与员工信息核对", "医院挂号与病历沟通", "银行与信用卡客服对话",
    "租房合同与物业通知", "快递单与收件信息", "微信群聊天记录（工作群）", "运维告警与排障记录（含日志）",
    "代码 review 与配置文件（含密钥泄露）", "数据库连接串与部署脚本", "会议纪要（含项目代号）", "销售线索与 CRM 备注",
    "学校报名与家长联系", "差旅报销与机票订单", "法律咨询与合同条款", "跨国项目邮件（中文夹英文）",
    "中英混写的技术支持对话", "政务办事（社保、公积金、户籍）", "保险理赔", "招聘简历片段",
]
REGISTERS = ["口语、随意，有错别字和省略", "正式书面", "半结构化（表单、键值对、表格行）"]

SYSTEM = f"""你在为一个端侧 PII 脱敏模型生成训练模板。输出若干条中文为主、常夹英文的文本模板（不含日语）。

规则：
1. 任何个人信息都必须写成槽位，绝不写出具体值。可用的个人信息槽位：{", ".join(PII_OFFERED)}。
2. 非个人信息的编号、版本等也用槽位：{", ".join(sorted(NEUTRAL_SLOTS))}（FICT 是虚构角色名，例如小说人物）。
3. 文本中不能出现任何具体的人名、电话、邮箱、证件号、卡号、地址、IP、密钥。不确定是否属于个人信息时，用槽位。
4. 每条模板 20 到 200 字，可以含换行（写成 \\n）。槽位写成 {{NAME_ZH}} 这种形式，大写，花括号。
5. 包括难例：同一句里有多个实体、实体紧挨标点、称呼（先生/女士/老师/总）、只有姓的称呼（{{SURNAME_ZH}}总）、
   以及看起来像个人信息但其实不是的内容（订单号 {{ORDER}}、版本号 {{VER}}、虚构人物 {{FICT}}）。
6. 大约三成的模板不含任何个人信息槽位，只含非个人信息槽位或纯文本，用作负样本。"""

SCHEMA = {
    "type": "object",
    "properties": {
        "templates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"lang": {"type": "string", "enum": ["zh", "mixed"]}, "text": {"type": "string"}},
                "required": ["lang", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["templates"],
    "additionalProperties": False,
}

SLOT_RE = re.compile(r"\{([A-Z_]+)\}")
# Anything that looks like a literal value outside a slot.
LEAK_RES = [
    re.compile(r"\d{6,}"),                      # long digit runs: IDs, phones, cards
    re.compile(r"\d{3,4}[- ]\d{4}"),            # grouped phone digits
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),     # emails
    re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),  # IPv4
    re.compile(r"(?:sk-|AKIA|ghp_|eyJ)[\w-]{8,}"),
    re.compile(r"[一-鿿]{1,3}(?:先生|女士|小姐|老师|经理|总)(?![一-鿿]*\})"),  # literal name + honorific
]


def scrub(text: str) -> str | None:
    """Return the reason a template is rejected, or None if it is safe to keep."""
    slots = SLOT_RE.findall(text)
    if any(s not in SLOTS for s in slots):
        return "unknown slot"
    bare = SLOT_RE.sub("", text)
    for r in LEAK_RES:
        if r.search(bare):
            return f"literal value: {r.pattern[:24]}"
    if not 20 <= len(text) <= 400:
        return "length"
    return None


def requests():
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    for i, sc in enumerate(SCENARIOS):
        for j, reg in enumerate(REGISTERS):
            yield Request(
                custom_id=f"zh-{i:02d}-{j}",
                params=MessageCreateParamsNonStreaming(
                    model=MODEL,
                    max_tokens=16000,
                    output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
                    system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": f"场景：{sc}\n语体：{reg}\n生成 10 条模板。"}],
                ),
            )


def load_env():
    """Read ANTHROPIC_API_KEY from training/.env (git-ignored) if it is not already in the environment."""
    import os

    f = ROOT / ".env"
    if "ANTHROPIC_API_KEY" not in os.environ and f.exists():
        for line in f.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "ANTHROPIC_API_KEY":
                os.environ["ANTHROPIC_API_KEY"] = v.strip().strip('"\'')


def submit(n: int):
    import anthropic

    reqs = list(requests())
    reqs = (reqs * (n // len(reqs) + 1))[: max(1, n // 10)]
    # duplicate scenario requests need unique custom ids
    for k, r in enumerate(reqs):
        r["custom_id"] = f"{r['custom_id']}-{k}"
    batch = anthropic.Anthropic().messages.batches.create(requests=reqs)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"id": batch.id, "model": MODEL, "requests": len(reqs)}))
    print(f"batch {batch.id}: {len(reqs)} requests")


def collect():
    import anthropic

    client = anthropic.Anthropic()
    st = json.loads(STATE.read_text())
    while (b := client.messages.batches.retrieve(st["id"])).processing_status != "ended":
        print(f"waiting: {b.request_counts.processing} processing")
        time.sleep(60)
    kept, rejected, seen = [], {}, set()
    for res in sorted(client.messages.batches.results(st["id"]), key=lambda r: r.custom_id):
        if res.result.type != "succeeded":
            rejected[f"request {res.result.type}"] = rejected.get(f"request {res.result.type}", 0) + 1
            continue
        msg = res.result.message
        if msg.stop_reason != "end_turn":
            rejected[f"stop {msg.stop_reason}"] = rejected.get(f"stop {msg.stop_reason}", 0) + 1
            continue
        text = next(b.text for b in msg.content if b.type == "text")
        for t in json.loads(text)["templates"]:
            body = t["text"].replace("\\n", "\n")
            why = scrub(body)
            if why is None and body in seen:
                why = "duplicate"
            if why:
                rejected[why] = rejected.get(why, 0) + 1
                continue
            seen.add(body)
            kept.append({"id": f"s{len(kept) + 1:04d}", "lang": t["lang"], "text": body, "source": res.custom_id, "model": st["model"]})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"kept {len(kept)} templates -> {OUT.relative_to(ROOT)}; rejected {rejected}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["submit", "collect"])
    ap.add_argument("--n", type=int, default=600, help="approximate number of templates")
    a = ap.parse_args()
    load_env()
    submit(a.n) if a.cmd == "submit" else collect()


if __name__ == "__main__":
    sys.exit(main())
