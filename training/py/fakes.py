"""Fake PII values for template data. Safety rules (no real personal data):

- CN resident ID numbers use birth years 2050-2099, so no living person can hold one.
- Card numbers use published test BINs only.
- Email domains are reserved names (RFC 2606 / RFC 6761): example.com/.net/.org, *.example, *.test.
- IP addresses are documentation ranges (RFC 5737 / RFC 3849) or private ranges.
- Secrets are random strings in the shape of real tokens; none is a valid credential.
- Names are random combinations of common surnames and given names, linked to no one.
- Phone numbers and My Numbers are random. They are not linked to any name, and generated
  data stays in the git-ignored cache; only templates are committed.
"""

import base64
import json
import random
import string

ZH_SURNAMES = list("王李张刘陈杨黄赵吴周徐孙马朱胡郭何林罗高郑梁谢宋唐许韩冯邓曹彭曾肖田董潘袁蔡蒋余于杜叶程魏苏吕丁任卢姚沈钟姜崔谭陆范汪廖石金韦贾夏付方邹熊白孟秦邱侯江尹薛闫段雷龙黎史陶贺毛郝顾龚邵万覃武钱戴严") + ["欧阳", "司马", "上官", "诸葛"]
ZH_GIVEN = list("伟芳娜敏静丽强磊军洋勇艳杰娟涛明超秀霞平刚桂子涵浩宇欣怡梓轩雨晨博文嘉思佳一诺俊鹏婷雪琳晓东海华建国志红玉兰凯斌辉波鑫宁悦瑶瑞泽昊然睿晴")

JA_SURNAMES = [
    ("佐藤", "Sato"), ("鈴木", "Suzuki"), ("高橋", "Takahashi"), ("田中", "Tanaka"), ("伊藤", "Ito"),
    ("渡辺", "Watanabe"), ("山本", "Yamamoto"), ("中村", "Nakamura"), ("小林", "Kobayashi"), ("加藤", "Kato"),
    ("吉田", "Yoshida"), ("山田", "Yamada"), ("佐々木", "Sasaki"), ("山口", "Yamaguchi"), ("松本", "Matsumoto"),
    ("井上", "Inoue"), ("木村", "Kimura"), ("林", "Hayashi"), ("斎藤", "Saito"), ("清水", "Shimizu"),
    ("山崎", "Yamazaki"), ("森", "Mori"), ("池田", "Ikeda"), ("橋本", "Hashimoto"), ("阿部", "Abe"),
    ("石川", "Ishikawa"), ("山下", "Yamashita"), ("中島", "Nakajima"), ("石井", "Ishii"), ("小川", "Ogawa"),
    ("前田", "Maeda"), ("岡田", "Okada"), ("長谷川", "Hasegawa"), ("藤田", "Fujita"), ("後藤", "Goto"),
    ("近藤", "Kondo"), ("村上", "Murakami"), ("遠藤", "Endo"), ("青木", "Aoki"), ("坂本", "Sakamoto"),
    ("西村", "Nishimura"), ("福田", "Fukuda"), ("太田", "Ota"), ("三浦", "Miura"), ("藤原", "Fujiwara"),
]
JA_GIVEN = [
    ("翔太", "Shota"), ("蓮", "Ren"), ("大翔", "Hiroto"), ("陽菜", "Hina"), ("結衣", "Yui"), ("美咲", "Misaki"),
    ("健太", "Kenta"), ("直樹", "Naoki"), ("由美", "Yumi"), ("恵", "Megumi"), ("拓也", "Takuya"), ("愛", "Ai"),
    ("さくら", "Sakura"), ("翼", "Tsubasa"), ("陽斗", "Haruto"), ("葵", "Aoi"), ("優子", "Yuko"), ("誠", "Makoto"),
    ("修", "Osamu"), ("明美", "Akemi"), ("隆", "Takashi"), ("真由美", "Mayumi"), ("和也", "Kazuya"), ("彩", "Aya"),
]
EN_FIRST = "James Mary John Patricia Robert Jennifer Michael Linda William Elizabeth David Barbara Richard Susan Joseph Jessica Thomas Sarah Charles Karen Daniel Emily Matthew Olivia Anthony Emma Mark Sophia Paul Grace Kevin Chloe Brian Hannah Ryan Megan Ethan Laura Nathan Rachel".split()
EN_LAST = "Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez Lopez Wilson Anderson Taylor Moore Jackson Martin Lee Thompson White Harris Clark Lewis Walker Hall Allen Young King Wright Scott Green Baker Adams Nelson Carter Mitchell Roberts Turner".split()

ZH_PLACES = [
    ("北京市", "朝阳区"), ("北京市", "海淀区"), ("上海市", "浦东新区"), ("上海市", "徐汇区"),
    ("广东省深圳市", "南山区"), ("广东省广州市", "天河区"), ("浙江省杭州市", "西湖区"), ("四川省成都市", "武侯区"),
    ("江苏省南京市", "鼓楼区"), ("湖北省武汉市", "洪山区"), ("陕西省西安市", "雁塔区"), ("山东省青岛市", "市南区"),
]
ZH_ROADS = ["长青路", "新华街", "建设大道", "文化路", "和平里", "光明路", "友谊大街", "科技园南路", "学府路", "滨江大道", "云栖路", "青年路"]
JA_PLACES = [
    ("東京都", "世田谷区"), ("東京都", "杉並区"), ("大阪府", "大阪市北区"), ("神奈川県", "横浜市港北区"),
    ("愛知県", "名古屋市中区"), ("福岡県", "福岡市博多区"), ("北海道", "札幌市中央区"), ("京都府", "京都市左京区"),
    ("千葉県", "船橋市"), ("埼玉県", "さいたま市浦和区"),
]
JA_TOWNS = ["桜丘", "緑町", "本町", "旭町", "若葉", "東雲", "中央", "栄町", "宮前", "南台"]
JA_BUILDINGS = ["メゾン桜", "グリーンハイツ", "コーポ若葉", "サンライズ", "パークサイド"]
EN_STREETS = ["Maple", "Oak", "Pine", "Cedar", "Elm", "Lakeview", "Hillcrest", "Sunset", "River", "Willow", "Highland", "Park"]
EN_STREET_TYPES = ["St", "Street", "Ave", "Avenue", "Rd", "Road", "Blvd", "Lane", "Drive", "Way"]
EN_CITIES = [("Springfield", "IL"), ("Riverside", "CA"), ("Franklin", "TN"), ("Greenville", "SC"), ("Madison", "WI"), ("Salem", "OR"), ("Fairview", "TX"), ("Georgetown", "KY")]

ORG_ZH_STEMS = ["云帆", "星河", "蓝鲸", "启明", "青松", "沐光", "极点", "鸿远", "飞鱼", "数澜"]
ORG_ZH_SUFFIX = ["科技有限公司", "信息技术有限公司", "网络科技股份有限公司", "集团", "贸易有限公司"]
ORG_JA_STEMS = ["アオバ", "ミナト", "ひかり", "サクラギ", "ホクト", "ツバサ", "カエデ", "シンセイ"]
ORG_JA_FORMS = ["株式会社{}", "{}株式会社", "{}システムズ株式会社", "合同会社{}", "{}テック株式会社"]
ORG_EN_STEMS = ["Bluefin", "Northwind", "Brightpath", "Cobalt Peak", "Silverline", "Ironleaf", "Quillstone", "Larkspur"]
ORG_EN_SUFFIX = ["Inc.", "LLC", "Ltd.", "Labs", "Technologies", "Co., Ltd.", "Corp."]
PROJECTS = [
    "Project Falcon", "Project Nightjar", "Operation Bluebird", "Project Kestrel", "Atlas-7",
    "代号青鸟", "代号「北极星」", "星火计划", "プロジェクト・アオバ", "コードネーム「月光」", "Project Mistral-X",
]

EMAIL_DOMAINS = ["example.com", "example.net", "example.org", "mail.example.com", "corp.example", "dev.example", "mail.test"]
TEST_BINS = ["400000", "424242", "555555", "222300", "378282", "601111", "356600", "620000"]

FICTIONAL = ["孙悟空", "猪八戒", "林黛玉", "贾宝玉", "Sherlock Holmes", "Harry Potter", "Frodo", "Pikachu", "江戸川コナン", "うずまきナルト", "ルフィ", "ドラえもん", "Mario", "Luke Skywalker"]


class Fakes:
    def __init__(self, seed: int):
        self.r = random.Random(seed)

    def pick(self, xs):
        return self.r.choice(xs)

    def digits(self, n: int) -> str:
        return "".join(self.r.choice(string.digits) for _ in range(n))

    def alnum(self, n: int, chars: str = string.ascii_letters + string.digits) -> str:
        return "".join(self.r.choice(chars) for _ in range(n))

    # names
    def name_zh(self):
        return self.pick(ZH_SURNAMES) + "".join(self.pick(ZH_GIVEN) for _ in range(self.r.choice([1, 2])))

    def surname_zh(self):
        return self.pick(ZH_SURNAMES)

    def name_ja(self):
        s, g = self.pick(JA_SURNAMES)[0], self.pick(JA_GIVEN)[0]
        return s + self.pick(["", " ", "　"]) + g

    def surname_ja(self):
        return self.pick(JA_SURNAMES)[0]

    def romaji_surname(self):
        return self.pick(JA_SURNAMES)[1]

    def romaji_name(self):
        return f"{self.pick(JA_GIVEN)[1]} {self.pick(JA_SURNAMES)[1]}"

    def name_en(self):
        return f"{self.pick(EN_FIRST)} {self.pick(EN_LAST)}"

    def first_en(self):
        return self.pick(EN_FIRST)

    def last_en(self):
        return self.pick(EN_LAST)

    # contact
    def email(self):
        local = self.pick([
            lambda: self.pick(JA_SURNAMES)[1].lower(),
            lambda: f"{self.pick(EN_FIRST).lower()}.{self.pick(EN_LAST).lower()}",
            lambda: f"{self.pick(JA_GIVEN)[1].lower()}_{self.digits(2)}",
            lambda: self.alnum(self.r.randint(5, 10), string.ascii_lowercase + string.digits),
            lambda: f"{self.pick(['wang', 'li', 'zhang', 'liu', 'chen'])}{self.digits(4)}",
        ])()
        return f"{local}@{self.pick(EMAIL_DOMAINS)}"

    def phone_cn(self):
        d = "1" + self.pick("3456789") + self.digits(9)
        return self.pick([d, f"{d[:3]}-{d[3:7]}-{d[7:]}", f"{d[:3]} {d[3:7]} {d[7:]}", f"+86 {d}", f"0{self.pick(['10', '21', '755', '571'])}-{self.digits(8)}"])

    def phone_jp(self):
        return self.pick([
            f"0{self.pick('789')}0-{self.digits(4)}-{self.digits(4)}",
            f"0{self.pick('789')}0{self.digits(8)}",
            f"03-{self.digits(4)}-{self.digits(4)}",
            f"06-{self.digits(4)}-{self.digits(4)}",
            f"+81 {self.pick('789')}0-{self.digits(4)}-{self.digits(4)}",
        ])

    def phone_us(self):
        a = self.pick(["415", "212", "646", "503", "617", "312"])
        return self.pick([f"({a}) 555-01{self.digits(2)}", f"{a}-{self.digits(3)}-{self.digits(4)}", f"+1 {a} {self.digits(3)} {self.digits(4)}", f"{a}.{self.digits(3)}.{self.digits(4)}"])

    # numbers with check digits
    def cn_id(self):
        area = self.pick(["110105", "310104", "440305", "330106", "510107", "320106", "420111"])
        y = self.r.randint(2050, 2099)
        m = self.r.randint(1, 12)
        d = self.r.randint(1, 28)
        body = f"{area}{y}{m:02d}{d:02d}{self.digits(3)}"
        w = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        return body + "10X98765432"[sum(int(c) * k for c, k in zip(body, w)) % 11]

    def mynumber(self):
        b = self.digits(11)
        s = sum(int(b[11 - n]) * (n + 1 if n <= 6 else n - 5) for n in range(1, 12))
        r = s % 11
        n = b + str(0 if r <= 1 else 11 - r)
        return self.pick([n, f"{n[:4]} {n[4:8]} {n[8:]}", f"{n[:4]}-{n[4:8]}-{n[8:]}"])

    def card(self):
        bin_ = self.pick(TEST_BINS)
        n = 15 if bin_.startswith("3782") else 16
        body = bin_ + self.digits(n - len(bin_) - 1)
        total = 0
        for i, c in enumerate(reversed(body)):
            v = int(c)
            if i % 2 == 0:
                v *= 2
                v = v - 9 if v > 9 else v
            total += v
        full = body + str((10 - total % 10) % 10)
        if n == 16:
            return self.pick([full, " ".join(full[i:i + 4] for i in range(0, 16, 4)), "-".join(full[i:i + 4] for i in range(0, 16, 4))])
        return full

    def ssn(self):
        return f"{self.r.randint(100, 665)}-{self.r.randint(10, 99)}-{self.r.randint(1000, 9999)}"

    def bank_jp(self):
        return self.digits(7)

    def ip(self):
        return self.pick([
            f"192.0.2.{self.r.randint(1, 254)}", f"198.51.100.{self.r.randint(1, 254)}", f"203.0.113.{self.r.randint(1, 254)}",
            f"10.{self.r.randint(0, 255)}.{self.r.randint(0, 255)}.{self.r.randint(1, 254)}",
            f"2001:db8::{self.r.randint(1, 0xffff):x}", f"2001:db8:{self.r.randint(1, 0xffff):x}::{self.r.randint(1, 0xff):x}",
        ])

    # secrets
    def secret(self):
        a = string.ascii_letters + string.digits
        return self.pick([
            lambda: "sk-proj-" + self.alnum(48, a + "_-"),
            lambda: "sk-ant-api03-" + self.alnum(64, a + "_-"),
            lambda: "AKIA" + self.alnum(16, string.ascii_uppercase + string.digits),
            lambda: "ghp_" + self.alnum(36),
            lambda: "github_pat_" + self.alnum(22) + "_" + self.alnum(59),
            lambda: "xoxb-" + self.digits(12) + "-" + self.digits(13) + "-" + self.alnum(24),
            lambda: "sk_live_" + self.alnum(24),
            lambda: "AIza" + self.alnum(35, a + "_-"),
            lambda: "glpat-" + self.alnum(20, a + "_-"),
            lambda: "hf_" + self.alnum(34),
            lambda: "npm_" + self.alnum(36),
            self.jwt,
        ])()

    def jwt(self):
        def b64(o):
            return base64.urlsafe_b64encode(json.dumps(o, separators=(",", ":")).encode()).decode().rstrip("=")
        return f"{b64({'alg': 'HS256', 'typ': 'JWT'})}.{b64({'sub': self.digits(6), 'iat': 1700000000 + self.r.randint(0, 10**7)})}.{self.alnum(43, string.ascii_letters + string.digits + '_-')}"

    def password(self):
        return self.alnum(self.r.randint(10, 18), string.ascii_letters + string.digits + "!@#%^&*")

    def dburl(self):
        scheme = self.pick(["postgres", "postgresql", "mysql", "mongodb+srv", "redis"])
        user = self.pick(["app", "admin", "svc_api", "root", "deploy"])
        host = self.pick(["db.internal.example", "10.0.3.12", "cluster0.mongo.example", "cache.dev.example"])
        return f"{scheme}://{user}:{self.alnum(14)}@{host}:{self.pick(['5432', '3306', '27017', '6379'])}/{self.pick(['prod', 'app', 'main'])}"

    # addresses
    def addr_zh(self):
        p, d = self.pick(ZH_PLACES)
        s = f"{p}{d}{self.pick(ZH_ROADS)}{self.r.randint(1, 999)}号"
        if self.r.random() < 0.5:
            s += f"{self.r.randint(1, 30)}栋{self.r.randint(1, 6)}单元{self.r.randint(1, 30)}{self.r.randint(1, 4):02d}室"
        return s

    def addr_ja(self):
        p, c = self.pick(JA_PLACES)
        t = self.pick(JA_TOWNS)
        tail = self.pick([f"{self.r.randint(1, 5)}丁目{self.r.randint(1, 30)}番{self.r.randint(1, 20)}号", f"{self.r.randint(1, 5)}-{self.r.randint(1, 30)}-{self.r.randint(1, 20)}"])
        s = f"{p}{c}{t}{tail}"
        if self.r.random() < 0.4:
            s += f" {self.pick(JA_BUILDINGS)}{self.r.randint(1, 9)}{self.r.randint(1, 12):02d}号室"
        if self.r.random() < 0.3:
            s = f"〒{self.digits(3)}-{self.digits(4)} " + s
        return s

    def addr_en(self):
        c, st = self.pick(EN_CITIES)
        return f"{self.r.randint(10, 9999)} {self.pick(EN_STREETS)} {self.pick(EN_STREET_TYPES)}, {c}, {st} {self.digits(5)}"

    def org_zh(self):
        return self.pick(ORG_ZH_STEMS) + self.pick(ORG_ZH_SUFFIX)

    def org_ja(self):
        return self.pick(ORG_JA_FORMS).format(self.pick(ORG_JA_STEMS))

    def org_en(self):
        return f"{self.pick(ORG_EN_STEMS)} {self.pick(ORG_EN_SUFFIX)}"

    def project(self):
        return self.pick(PROJECTS)

    # neutral values (never PII)
    def neutral(self, kind: str) -> str:
        r = self.r
        if kind == "INT":
            return str(r.randint(1, 99999))
        if kind == "UID":
            return str(r.randint(1000, 999999))
        if kind == "VER":
            return self.pick([f"{r.randint(0, 5)}.{r.randint(0, 30)}.{r.randint(0, 20)}", f"v{r.randint(1, 4)}.{r.randint(0, 12)}.{r.randint(0, 9)}", f"{r.randint(1, 9)}.{r.randint(0, 9)}.{r.randint(0, 9)}.{r.randint(0, 999)}"])
        if kind == "SHA":
            return self.alnum(self.pick([7, 12, 40]), "0123456789abcdef")
        if kind == "UUID":
            h = self.alnum(32, "0123456789abcdef")
            return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
        if kind == "ORDER":
            return self.pick([f"ORD-{r.randint(2023, 2026)}{r.randint(1, 12):02d}{r.randint(1, 28):02d}-{self.digits(6)}", self.digits(12), self.digits(16), f"#{self.digits(8)}", f"INV{self.digits(10)}", self.digits(18)])
        if kind == "SKU":
            return self.pick([f"{self.alnum(2, string.ascii_uppercase)}-{self.digits(4)}{self.alnum(1, string.ascii_uppercase)}", f"RTX {self.pick(['4070', '4090', '5080'])}", f"iPhone {r.randint(12, 17)} Pro", f"ThinkPad X1 Gen {r.randint(9, 13)}", f"SM-S{self.digits(3)}{self.pick('BNU')}", f"WH-1000XM{r.randint(3, 6)}"])
        if kind == "TS":
            return f"{r.randint(2023, 2026)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}T{r.randint(0, 23):02d}:{r.randint(0, 59):02d}:{r.randint(0, 59):02d}.{self.digits(3)}Z"
        if kind == "PORT":
            return str(self.pick([3000, 5173, 8080, 8443, 5432, 6379, 9200, 27017]))
        if kind == "HEX":
            return "0x" + self.alnum(self.pick([4, 8, 16]), "0123456789abcdef")
        if kind == "FICT":
            return self.pick(FICTIONAL)
        if kind == "LOCALIP":
            return self.pick(["127.0.0.1", "0.0.0.0", "localhost", "::1"])
        if kind == "MS":
            return str(r.randint(3, 9000))
        raise KeyError(kind)


PII_SLOTS = {
    "NAME_ZH": ("PERSON", Fakes.name_zh), "SURNAME_ZH": ("PERSON", Fakes.surname_zh),
    "NAME_JA": ("PERSON", Fakes.name_ja), "SURNAME_JA": ("PERSON", Fakes.surname_ja),
    "ROMAJI": ("PERSON", Fakes.romaji_surname), "ROMAJI_NAME": ("PERSON", Fakes.romaji_name),
    "NAME_EN": ("PERSON", Fakes.name_en), "FIRST_EN": ("PERSON", Fakes.first_en), "LAST_EN": ("PERSON", Fakes.last_en),
    "EMAIL": ("EMAIL", Fakes.email),
    "PHONE_CN": ("PHONE", Fakes.phone_cn), "PHONE_JP": ("PHONE", Fakes.phone_jp), "PHONE_US": ("PHONE", Fakes.phone_us),
    "CN_ID": ("CN_ID", Fakes.cn_id), "MYNUMBER": ("JP_MYNUMBER", Fakes.mynumber), "CARD": ("CREDIT_CARD", Fakes.card),
    "SSN": ("NATIONAL_ID", Fakes.ssn), "BANK_JP": ("BANK_ACCOUNT", Fakes.bank_jp),
    "SECRET": ("SECRET", Fakes.secret), "JWT": ("SECRET", Fakes.jwt), "PASSWORD": ("SECRET", Fakes.password), "DBURL": ("SECRET", Fakes.dburl),
    "IP": ("IP", Fakes.ip),
    "ADDR_ZH": ("ADDRESS", Fakes.addr_zh), "ADDR_JA": ("ADDRESS", Fakes.addr_ja), "ADDR_EN": ("ADDRESS", Fakes.addr_en),
    "ORG_ZH": ("ORG", Fakes.org_zh), "ORG_JA": ("ORG", Fakes.org_ja), "ORG_EN": ("ORG", Fakes.org_en),
    "PROJECT": ("PROJECT", Fakes.project),
}
NEUTRAL_SLOTS = {"INT", "UID", "VER", "SHA", "UUID", "ORDER", "SKU", "TS", "PORT", "HEX", "FICT", "LOCALIP", "MS"}
