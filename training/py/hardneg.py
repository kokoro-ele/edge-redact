"""Programmatic hard negatives: technical text full of numbers, ids and names that are NOT personal data.

The M1 models fired on order/invoice numbers, hashes, versions, SQL, query strings, log lines and
fictional characters. This writes short snippets of those kinds (zh / en / mixed), written fresh here
rather than copied from the benchmark's neg templates. Half the documents also carry one filled
*train* PII template, so the model sees both sides of the boundary in one context.
"""

import random

from fakes import Fakes


def _hex(r, n):
    return "".join(r.choice("0123456789abcdef") for _ in range(n))


def _num(r, lo, hi):
    return str(r.randint(lo, hi))


def _digits(r, n):
    return str(r.randint(1, 9)) + "".join(r.choice("0123456789") for _ in range(n - 1))


def _ver(r):
    return ".".join(str(r.randint(0, 20)) for _ in range(r.choice([2, 3, 3, 4])))


def _date(r):
    return f"20{r.randint(18, 27)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}"


def snippets(r: random.Random):
    """Each entry: (lang, fn) returning a text with no PII."""
    D, H, V, N = (lambda n: _digits(r, n)), (lambda n: _hex(r, n)), (lambda: _ver(r)), (lambda a, b: _num(r, a, b))
    return [
        ("zh", lambda: f"订单{r.choice(['号', '编号', ' ID', '号：'])} {D(r.choice([12, 15, 16, 18, 19]))} 还在{r.choice(['配送中', '待发货', '退款中'])}，能帮我催一下吗"),
        ("zh", lambda: f"发票{r.choice(['号码', '代码', '号'])}{r.choice([' ', '：'])}{D(r.choice([8, 12, 16, 20]))}，金额 {N(10, 99999)}.{N(10, 99)} 元"),
        ("zh", lambda: f"快递单号 {r.choice(['SF', 'YT', 'JD', 'ZTO'])}{D(r.choice([10, 12, 13]))} 显示已签收"),
        ("zh", lambda: f"工单 #{N(1000, 999999)} 已关闭，耗时 {N(1, 72)} 小时"),
        ("zh", lambda: f"{r.choice(['服务器', '容器', '进程'])}内存占用 {N(100, 99999)}MB，CPU {N(1, 100)}%，{r.choice(['被 OOMKilled 了', '退出码 ' + N(1, 255), '一直重启'])}"),
        ("zh", lambda: f"第{N(1, 99999)}{r.choice(['章', '回', '集', '页'])}：{r.choice(['孙悟空', '林黛玉', '诸葛亮', '哈利·波特', '福尔摩斯', '贾宝玉'])}{r.choice(['来到了', '离开了', '回到'])}{r.choice(['长安', '大观园', '霍格沃茨', '贝克街', '花果山'])}"),
        ("zh", lambda: f"从 {V()} 升级到 {V()} 之后{r.choice(['构建失败', '测试挂了', '页面白屏'])}"),
        ("zh", lambda: f"版本号 v{V()}，构建号 {N(100, 99999)}，提交 {H(r.choice([7, 8, 40]))}"),
        ("zh", lambda: f"价格从 ¥{N(1, 9999)} 降到了 ¥{N(1, 9999)}，库存 {N(0, 99999)} 件"),
        ("zh", lambda: f"这道题的答案是 {N(100000, 99999999)}，我算的是 {N(100000, 99999999)}，哪里错了"),
        ("zh", lambda: f"{_date(r)} {N(0, 23):0>2}:{N(0, 59):0>2}:{N(0, 59):0>2} 的日志里有 {N(1, 9999)} 条 ERROR"),
        ("zh", lambda: f"会议室 {r.choice('ABCDEF')}{N(100, 1999)}，{N(1, 12)} 楼，{N(2, 30)} 人"),
        ("zh", lambda: f"股票代码 {N(600000, 603999)} 今天涨了 {N(1, 10)}.{N(1, 99)}%"),
        ("en", lambda: f"Order {r.choice(['#', 'ID ', 'no. ', ''])}{D(r.choice([10, 12, 16, 18]))} is still {r.choice(['pending', 'processing', 'in transit'])}"),
        ("en", lambda: f"Invoice {r.choice(['#', 'number ', 'INV-'])}{D(r.choice([6, 10, 16]))} total ${N(1, 99999)}.{N(10, 99)}"),
        ("en", lambda: f"commit {H(40)}\nAuthor: {r.choice(['ci-bot', 'dependabot[bot]', 'renovate[bot]', 'github-actions'])}\nDate: {_date(r)}"),
        ("en", lambda: f"segfault at address 0x{H(16)} in {r.choice(['libc.so.6', 'libssl.so.3', 'node', 'python3.12'])}"),
        ("en", lambda: f"SELECT * FROM {r.choice(['orders', 'events', 'logs', 'sessions'])} WHERE created_at > '{_date(r)}' LIMIT {N(1, 99999)};"),
        ("en", lambda: f"GET /api/v{N(1, 3)}/{r.choice(['items', 'orders', 'search'])}?page={N(1, 999)}&limit={N(10, 500)}&sku={r.choice(['iPhone 15 Pro', 'Pixel 9', 'MacBook Air M3', 'ThinkPad T14'])}&qty={N(1, 99999)} returned {r.choice(['200', '404', '500', '429'])}"),
        ("en", lambda: f"Benchmark: p50={N(1, 9999)}ms p95={N(1, 9999)}ms p99={N(1, 99999)}ms throughput={N(100, 99999)} req/s"),
        ("en", lambda: f"npm ERR! peer dep conflict between {r.choice(['react', 'vite', 'eslint', 'typescript'])}@{V()} and {V()}"),
        ("en", lambda: f"Chapter {N(1, 9999)}: {r.choice(['Sherlock Holmes', 'Elizabeth Bennet', 'Harry Potter', 'Captain Ahab', 'Hermione Granger'])} {r.choice(['looked at the letter', 'walked into the hall', 'said nothing'])}."),
        ("en", lambda: f"uuid {H(8)}-{H(4)}-{H(4)}-{H(4)}-{H(12)} not found in table {r.choice(['jobs', 'tasks', 'uploads'])}"),
        ("en", lambda: f"container {r.choice(['api', 'web', 'worker'])}-{H(12)} in pod {r.choice(['api', 'web', 'worker'])}-{H(10)}-{H(5)} restarted {N(1, 99)} times"),
        ("en", lambda: f"status=FAILED retries={N(1, 99999)} exit_code={N(1, 255)} duration={N(1, 9999)}s"),
        ("en", lambda: f"the sha256 is {H(64)}"),
        ("en", lambda: f"function {r.choice(['findUserByEmail', 'getPhoneNumber', 'parseAddress', 'validateCardNumber', 'hashPassword'])}({r.choice(['email', 'input', 'value', 'raw'])}) {{ return {r.choice(['null', 'undefined', 'true'])} }}"),
        ("en", lambda: f"{r.choice(['user_id', 'account_id', 'customer_name', 'email_address', 'phone_number'])} column is {r.choice(['VARCHAR(255)', 'BIGINT', 'TEXT NOT NULL', 'UUID'])}"),
        ("en", lambda: f"Room {N(100, 1999)}, floor {N(1, 40)}, capacity {N(2, 40)}"),
        ("en", lambda: f"ISBN 978-{N(0, 9)}-{N(100, 999)}-{N(10000, 99999)}-{N(0, 9)} costs ${N(5, 99)}.{N(10, 99)}"),
        ("mixed", lambda: f"这个 query string 有问题：?order_id={r.choice(['ORD', 'SO', 'PO'])}-{_date(r).replace('-', '')}-{D(6)}&sku={r.choice(['iPhone 15 Pro', 'Galaxy S24'])}&qty={N(1, 99999)}"),
        ("mixed", lambda: f"跑 benchmark 的结果：p50={N(1, 9999)}ms，p99={N(1, 99999)}ms，比 v{V()} 慢了 {N(1, 99)}%"),
        ("mixed", lambda: f"git log 里 commit {H(r.choice([7, 40]))} 引入了这个 bug，revert 掉就好了"),
        ("mixed", lambda: f"Docker 镜像 {r.choice(['node', 'python', 'nginx', 'postgres'])}:{V()} 的 digest 是 sha256:{H(64)}"),
        ("mixed", lambda: f"把 {r.choice(['user_email', 'phone', 'address_line1', 'id_card_no'])} 字段改成 nullable，migration 编号 {N(1, 999):0>4}"),
        ("mixed", lambda: f"报错 Error code {N(1000, 99999)}：{r.choice(['connection reset', 'timeout', 'permission denied'])}，重试了 {N(1, 99)} 次"),
        ("mixed", lambda: f"在 {r.choice(['127.0.0.1', 'localhost', '0.0.0.0'])}:{N(1024, 65535)} 起的 dev server，版本 {V()}"),
    ]


def hardneg_docs(n: int, seed: int, pii_tmpls, fill):
    """Yield (lang, text, spans). pii_tmpls: train-split PII templates for the mixed-in half."""
    r = random.Random(seed)
    fk = Fakes(seed=seed)
    bank = snippets(r)
    by_lang = {l: [f for lg, f in bank if lg == l] for l in ("zh", "en", "mixed")}
    for _ in range(n):
        lang = r.choice(["zh", "en", "mixed"])
        pool = by_lang[lang] + (by_lang["zh"] + by_lang["en"] if lang == "mixed" else [])
        parts = [r.choice(pool)() for _ in range(r.randint(1, 4))]
        sep = r.choice(["\n", "\n\n", " ", "；" if lang != "en" else "; "])
        spans = []
        if pii_tmpls and r.random() < 0.5:
            cands = [t for t in pii_tmpls if t["lang"] == lang or lang == "mixed"]
            text, sp = fill(r.choice(cands)["text"], fk)
            k = r.randint(0, len(parts))
            before = sep.join(parts[:k]) + (sep if k else "")
            spans = [(s + len(before), e + len(before), t) for s, e, t in sp]
            parts = parts[:k] + [text] + parts[k:]
        yield lang, sep.join(parts), spans
