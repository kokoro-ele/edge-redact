import type { Entity, EntityType } from '../types.ts'
import { RISK, RISK_RANK } from '../types.ts'
import { cardPrefixOk, cnIdValid, digitsOf, ibanValid, luhn, myNumberValid } from './checksums.ts'

interface Rule {
  type: EntityType
  re: RegExp
  /** Returns a score in 0..1, or 0 to reject. May narrow the span with [start, end] relative to the match. */
  check?: (m: RegExpExecArray, text: string) => number | [number, number, number]
  score?: number
}

const sepsConsistent = (s: string) => new Set(s.replace(/\d/g, '')).size <= 1

const MY_NUMBER_CONTEXT = /(?:マイナンバー|個人番号|my\s*number|个人编号)/i
const CARD_CONTEXT = /(?:card|カード|卡|visa|master|amex|jcb|银联|クレジット)/i
/** Words before a number that mark it as a business reference, not a personal one. */
const REF_CONTEXT = /(?:order|invoice|tracking|ticket|sku|订单|单号|发票|运单|工单|注文|請求書|伝票|問い合わせ番号)[^\n]{0,6}$/i
/** "version 2.9.7 and …", "版本 1.2.3 到 …": the next dotted number is a version too. */
const VERSION_RANGE = /(?:version|ver\.?|版本|バージョン)\s*v?\d+(?:\.\d+)+\s*(?:and|to|->|→|~|～|到|至|から|-)\s*$/i
const VERSION_CONTEXT = /(?:version|ver\.?|v|版本|バージョン|固件|firmware|build|release|@)\s*$/i

const RULES: Rule[] = [
  // ---- secrets ----
  {
    type: 'SECRET',
    re: /-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----[\s\S]+?-----END (?:[A-Z]+ )*PRIVATE KEY-----/g,
  },
  { type: 'SECRET', re: /\beyJ[\w-]{8,}\.eyJ[\w-]{8,}\.[\w-]{10,}/g },
  {
    type: 'SECRET',
    re: /(?<![\w-])(?:sk-(?:proj-|ant-(?:api\d\d-)?)?[\w-]{20,}|sk_(?:live|test)_\w{16,}|[rp]k_(?:live|test)_\w{16,}|gh[pousr]_\w{36,}|github_pat_\w{40,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|AIza[\w-]{35}|xox[abprs]-[\w-]{10,}|glpat-[\w-]{20}|hf_\w{30,}|npm_\w{36})(?![\w-])/g,
  },
  {
    type: 'SECRET',
    re: /(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|rediss?|amqps?|mssql|sqlserver):\/\/[^\s:@/]+:[^\s@/]+@[^\s"'<>]+/g,
  },
  {
    // Authorization: Bearer <token>
    type: 'SECRET',
    re: /\bBearer\s+([\w.~+/-]{16,}=*)/g,
    check: m => [0.95, m.index + m[0].length - m[1]!.length, m.index + m[0].length],
  },
  {
    // key=value / key: "value" for secret-like keys
    type: 'SECRET',
    re: /\b(?:pass(?:word|wd)?|pwd|secret|client_secret|api[_-]?key|access[_-]?key|auth[_-]?token|token|private[_-]?key|密码|パスワード)["'*]{0,2}\s*(?:[:=：]|是|は)\**\s*["']?([^\s"'`,;&<>*\u3000-\u303F\u4E00-\u9FFF\uFF00-\uFFEF]{6,})/gi,
    check: (m) => {
      const v = m[1]!
      if (/^(?:\*+|x+|null|none|undefined|true|false|changeme|password|your[_-].*|<.*>|\$\{.*\}|process\.env.*|os\.environ.*)$/i.test(v))
        return 0
      if (!/\d/.test(v) && !/[^\w]/.test(v) && v.length < 12)
        return 0
      if (/^[-$({[<]/.test(v) || /^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+[)\]},;]*$/.test(v))
        return 0 // code that references a value: config.db_password, $(cmd)
      const end = m.index + m[0].length
      return [0.85, end - v.length, end]
    },
  },
  // ---- high-risk numbers ----
  {
    type: 'CN_ID',
    re: /(?<![\dA-Za-z])[1-9]\d{5}[ -]?(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[ -]?\d{3}[\dXx](?!\d)/g,
    check: m => (sepsConsistent(m[0].slice(0, -1)) && cnIdValid(m[0].replace(/[ -]/g, '')) ? 0.99 : 0),
  },
  {
    type: 'JP_MYNUMBER',
    re: /(?<![\d-])\d{4}[ -]?\d{4}[ -]?\d{4}(?![\d-])/g,
    check: (m, text) => {
      if (!sepsConsistent(m[0]) || !myNumberValid(digitsOf(m[0])))
        return 0
      const before = text.slice(Math.max(0, m.index - 24), m.index)
      if (MY_NUMBER_CONTEXT.test(before))
        return 0.99
      return REF_CONTEXT.test(before) ? 0 : 0.6
    },
  },
  {
    type: 'CREDIT_CARD',
    re: /(?<![\w-])\d(?:[ -]?\d){12,18}(?![\d-])/g,
    check: (m, text) => {
      const d = digitsOf(m[0])
      if (!sepsConsistent(m[0]) || !luhn(d) || !cardPrefixOk(d))
        return 0
      if (/^(\d)\1+$/.test(d))
        return 0
      const before = text.slice(Math.max(0, m.index - 24), m.index)
      if (CARD_CONTEXT.test(before))
        return 0.97
      if (REF_CONTEXT.test(before))
        return 0
      return /[ -]/.test(m[0]) ? 0.95 : 0.75
    },
  },
  {
    type: 'BANK_ACCOUNT',
    re: /\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b/g,
    check: m => (ibanValid(m[0]) ? 0.98 : 0),
  },
  {
    type: 'NATIONAL_ID',
    re: /(?<![\d-])(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}(?![\d-])/g,
    score: 0.8,
  },
  // ---- medium ----
  {
    type: 'EMAIL',
    re: /(?<![\w.+\u00C0-\u024F-])[\w\u00C0-\u024F][\w.%+\u00C0-\u024F-]{0,63}@(?:[A-Za-z0-9-]+\.)+([A-Za-z]{2,24})(?![\w-])/g,
    check: m => (/^(?:png|jpe?g|gif|svg|webp|js|ts|css|map)$/i.test(m[1]!) ? 0 : 0.99),
  },
  {
    // CN mobile
    type: 'PHONE',
    re: /(?<![\d+])(?:(?:\+|00)86[ -]?)?1[3-9]\d(?:[ -]?\d{4}){2}(?!\d)/g,
    check: m => (sepsConsistent(m[0].replace(/^(?:\+|00)86[ -]?/, '')) ? 0.95 : 0),
  },
  {
    // CN landline 0xx-xxxxxxxx
    type: 'PHONE',
    re: /(?<![\d-])\(?0\d{2,3}\)?[ -]\d{7,8}(?![\d-])/g,
    score: 0.85,
  },
  {
    // JP
    type: 'PHONE',
    re: /(?<![\d+-])(?:\+81[ -]?|0)(?:[789]0[ -]?\d{4}[ -]?\d{4}|\d{1,4}[ -]\d{1,4}[ -]\d{4})(?![\d-])/g,
    check: (m) => {
      const intl = m[0].startsWith('+81')
      const d = digitsOf(intl ? m[0].slice(3) : m[0])
      const n = d.length + (intl ? 1 : 0)
      return n === 10 || n === 11 ? 0.9 : 0
    },
  },
  {
    // NANP and generic international with separators
    type: 'PHONE',
    re: /(?<![\w+-])(?:\+1[ .-]?)?(?:\(\d{3}\)\s?|\d{3}[ .-])\d{3}[ .-]\d{4}(?![\d-])/g,
    score: 0.85,
  },
  {
    type: 'PHONE',
    re: /(?<![\w+])\+\d{1,3}(?:[ .-]?\(?\d{1,4}\)?){2,5}(?![\d-])/g,
    check: (m) => {
      const n = digitsOf(m[0]).length
      return n >= 8 && n <= 15 ? 0.85 : 0
    },
  },
  {
    // CN licence plate, incl. 8-character new-energy plates
    type: 'OTHER_ID',
    re: /(?<![\w一-鿿])[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-HJ-NP-Z]·?[A-HJ-NP-Z0-9]{5,6}(?![A-Za-z0-9])/g,
    score: 0.9,
  },
  {
    type: 'IP',
    re: /(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\w]|\.\d)/g,
    check: (m, text) => {
      if (/^(?:0\.0\.0\.0|127\.|255\.)/.test(m[0]))
        return 0
      const before = text.slice(Math.max(0, m.index - 48), m.index)
      return VERSION_CONTEXT.test(before.slice(-12)) || VERSION_RANGE.test(before) ? 0 : 0.9
    },
  },
  {
    type: 'IP',
    re: /(?<![\w:])(?:[0-9A-Fa-f]{1,4}:){1,7}(?::|(?::[0-9A-Fa-f]{1,4}){1,7}|[0-9A-Fa-f]{1,4})(?![\w:])/g,
    check: (m) => {
      const s = m[0]
      const dbl = s.split('::').length - 1
      if (dbl > 1)
        return 0
      const groups = s.split(':').filter(Boolean)
      if (dbl === 0 && groups.length !== 8)
        return 0
      if (groups.length < 2 || s === '::1')
        return 0
      if (groups.every(g => /^\d{1,2}$/.test(g)))
        return 0
      return 0.9
    },
  },
]

/** Layer 1: format rules with checksums. Pure, synchronous, no model. */
export function detectRules(text: string): Entity[] {
  const found: Entity[] = []
  for (const rule of RULES) {
    rule.re.lastIndex = 0
    let m: RegExpExecArray | null
    // eslint-disable-next-line no-cond-assign
    while ((m = rule.re.exec(text))) {
      let start = m.index
      let end = m.index + m[0].length
      let score = rule.score ?? 0.95
      if (rule.check) {
        const r = rule.check(m, text)
        if (Array.isArray(r))
          [score, start, end] = r
        else
          score = r
      }
      if (score > 0)
        found.push({ start, end, type: rule.type, risk: RISK[rule.type], score, source: 'rule' })
      if (m[0].length === 0)
        rule.re.lastIndex++
    }
  }
  return resolveOverlaps(found)
}

/** Keep the strongest entity where spans overlap: higher risk, then longer, then higher score. */
/**
 * Product order: `base` (rules + heuristics) is authoritative; a model span is added only where it
 * overlaps nothing in `base`. The model can add recall but cannot retype or overwrite a rule hit.
 */
export function fillGaps(base: Entity[], extra: Entity[]): Entity[] {
  const kept = [...base]
  for (const e of resolveOverlaps(extra)) {
    if (!base.some(k => k.start < e.end && e.start < k.end))
      kept.push(e)
  }
  return kept.sort((a, b) => a.start - b.start)
}

export function resolveOverlaps(ents: Entity[]): Entity[] {
  const sorted = [...ents].sort((a, b) =>
    RISK_RANK[b.risk] - RISK_RANK[a.risk]
    || (b.end - b.start) - (a.end - a.start)
    || b.score - a.score)
  const kept: Entity[] = []
  for (const e of sorted) {
    if (!kept.some(k => k.start < e.end && e.start < k.end))
      kept.push(e)
  }
  return kept.sort((a, b) => a.start - b.start)
}

const OPEN = '(（[【「『〈《"“\''
const CLOSE = ')）]】」』〉》"”\''
const EDGE_PUNCT = /[\s\p{P}]/u
/** zh lead-ins a span should not start with ("他住在上海市…", "在星河公司") */
const LEAD_IN = /^(?:[他她我你它]们?)?(?:住在|位于|来自|就职于|任职于|寄到|送到|发到|在|于)/

/**
 * Trim span edges: whitespace and punctuation (a token's trailing full stop, a model span that took the
 * 「 of 「北极星」), unless a bracket is balanced inside the span ("(415) 555-0132"); and zh lead-in
 * words before ADDRESS / ORG. Spans that become empty are dropped.
 */
export function tidySpans(text: string, entities: Entity[]): Entity[] {
  const out: Entity[] = []
  for (const e of entities) {
    let { start, end } = e
    if (e.type === 'ADDRESS' || e.type === 'ORG') {
      const m = LEAD_IN.exec(text.slice(start, end))
      if (m && end - start - m[0].length >= 4)
        start += m[0].length
    }
    for (;;) {
      const c = text[start]
      if (start >= end || !c || !EDGE_PUNCT.test(c))
        break
      const k = OPEN.indexOf(c)
      if (k >= 0 && text.slice(start + 1, end).includes(CLOSE[k]!))
        break
      start++
    }
    for (;;) {
      const c = text[end - 1]
      if (end <= start || !c || !EDGE_PUNCT.test(c))
        break
      const k = CLOSE.indexOf(c)
      if (k >= 0 && text.slice(start, end - 1).includes(OPEN[k]!))
        break
      end--
    }
    if (end > start)
      out.push(start === e.start && end === e.end ? e : { ...e, start, end })
  }
  return out
}
