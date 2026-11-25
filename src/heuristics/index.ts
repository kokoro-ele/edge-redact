import type { Entity, EntityType } from '../types.ts'
import { detectRules, resolveOverlaps } from '../rules/index.ts'
import { RISK } from '../types.ts'
import { EN_FIRST_NAMES, JA_SURNAMES, ZH_SURNAMES_1, ZH_SURNAMES_2 } from './lexicon.ts'

const HAN = '\\u4e00-\\u9fff'
const HIRA = '\\u3040-\\u309f'
const KATA = '\\u30a0-\\u30ff'

const ZH_SUR = `(?:${ZH_SURNAMES_2.join('|')}|[${ZH_SURNAMES_1}])`
const JA_SUR = `(?:${[...JA_SURNAMES].sort((a, b) => b.length - a.length).join('|')})`
const EN_FIRST = `(?:${EN_FIRST_NAMES.join('|')})`
const CAP = '[A-Z][a-z]+(?:-[A-Z][a-z]+)?'
const EN_STOP = new Set(['The', 'This', 'That', 'There', 'Please', 'Thanks', 'Thank', 'Team', 'All', 'Everyone', 'Sir', 'Madam', 'There', 'Here', 'What', 'When', 'How', 'Why', 'Can', 'Could', 'Would', 'Will', 'Our', 'My', 'Your', 'Not', 'Just', 'Going', 'Sorry', 'Happy', 'Customer', 'Support', 'Order', 'Project'])

const ZH_HONORIFIC = '(?:先生|女士|小姐|老师|同学|医生|大夫|教授|经理|总监|总|律师|阿姨|叔叔|师傅|主任|部长|处长|科长)'
const JA_HONORIFIC = '(?:さん|様|さま|氏|君|くん|ちゃん|先生|部長|課長|社長|係長|殿|専務|常務)'
const ZH_STOP_AFTER = /[反说在的是了和与跟要让把被给向从对也都已就还会能来去发打问,，。.:：\s（()、）)!！?？;；"“”'’]/

interface Pat {
  type: EntityType
  re: RegExp
  /** Capture group that holds the entity; 0 = whole match. */
  group?: number
  score: number
  post?: (value: string, m: RegExpExecArray, text: string) => string | null
}

/** `config.db_password`, `$(cmd)`, `-stdin`, `reset)`: code that mentions a password, not a password. */
export function looksLikeCodeRef(v: string): boolean {
  return /^[-$({[<]/.test(v) || /^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+[)\]},;]*$/.test(v) || /^[A-Za-z]+[)\]}>'",;:]+$/.test(v)
}

/** Chinese given names are 1 or 2 characters; pick the length that ends at a likely boundary. */
function zhNameCut(value: string, m: RegExpExecArray, text: string): string | null {
  const sur = ZH_SURNAMES_2.find(s => value.startsWith(s)) ?? value[0]!
  const at = m.index + m[0].length - value.length
  const after = (n: number) => text[at + sur.length + n] ?? ' '
  if (ZH_STOP_AFTER.test(after(1)))
    return value.slice(0, sur.length + 1)
  if (ZH_STOP_AFTER.test(after(2)))
    return value.slice(0, sur.length + 2)
  return value.slice(0, sur.length + 1)
}

const PATS: Pat[] = [
  // ---- PERSON: zh ----
  { type: 'PERSON', re: new RegExp(`(${ZH_SUR}[${HAN}]{0,2}?)${ZH_HONORIFIC}`, 'g'), group: 1, score: 0.7 },
  {
    type: 'PERSON',
    re: new RegExp(`(?:我叫|我是|名叫|叫做|姓名[:：]?\\s*|联系人[:：]?\\s*|收件人[:：]?\\s*|收货人[:：]?\\s*|开户名[:：]?\\s*|负责人[:：]?\\s*|客户|患者|房东|同事|朋友|老婆|老公|妈妈|爸爸|候选人|mentor\\s*是\\s*|candidate\\s+)(${ZH_SUR}[${HAN}]{1,2})`, 'g'),
    group: 1,
    score: 0.65,
    post: zhNameCut,
  },
  // ---- PERSON: ja ----
  { type: 'PERSON', re: new RegExp(`(${JA_SUR}(?:[ \\u3000]?[${HAN}${HIRA}]{1,3})?)[ \\u3000]?${JA_HONORIFIC}`, 'g'), group: 1, score: 0.7 },
  { type: 'PERSON', re: new RegExp(`([${KATA}]{2,8}(?:[・ ][${KATA}]{2,8})?)${JA_HONORIFIC}`, 'g'), group: 1, score: 0.5 },
  { type: 'PERSON', re: new RegExp(`(?:氏名|お名前|名前|担当者?|宛名|名義|申込者)[:：は\\s]\\s*(${JA_SUR}(?:[ \\u3000]?[${HAN}${HIRA}]{1,3})?)`, 'g'), group: 1, score: 0.65 },
  // ---- PERSON: romaji / en ----
  { type: 'PERSON', re: new RegExp(`(${CAP}(?: ${CAP})?)(?:[- ](?:san|sama|kun|chan|sensei)\\b|\\s?${JA_HONORIFIC})`, 'g'), group: 1, score: 0.7 },
  { type: 'PERSON', re: new RegExp(`\\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\\.?\\s+(${CAP}(?:\\s${CAP})?)`, 'g'), group: 1, score: 0.75 },
  {
    type: 'PERSON',
    re: new RegExp(`\\b(?:[Mm]y name is|I'm|I am|[Nn]ame[:=]\\s*|Dear|Hi|Hello|Hey|[Cc]andidate|[Cc]ustomer|[Ii]ntern|[Ll]andlord|[Cc]olleague|[Cc]ontact|Author:|[Cc]ardholder|[Ss]incerely,?|[Rr]egards,?)\\s+(${CAP}(?:\\s${CAP}){0,2})`, 'g'),
    group: 1,
    score: 0.6,
    post: v => (EN_STOP.has(v.split(' ')[0]!) ? null : v),
  },
  { type: 'PERSON', re: new RegExp(`\\b(${EN_FIRST}(?:\\s${CAP}){1,2})\\b`, 'g'), group: 1, score: 0.55 },
  // `name: X` only when the key is a whole word (not container_name) and X looks like a personal name
  { type: 'PERSON', re: /(?<![\w.-])["']?(?:[Nn]ame|NAME|[Ff]ull_?[Nn]ame|姓名|氏名)["']?\s*[:=：]\s*["']?([\u3040-\u30ff\u4e00-\u9fff]{2,8}|(?:[\u4e00-\u9fff·]{1,6}|[A-Z][a-z'’-]+(?:-[A-Z][a-z'’-]+)?)(?: (?:[\u4e00-\u9fff·]{1,6}|[A-Z][a-z'’-]+(?:-[A-Z][a-z'’-]+)?)){0,3})(?=[\s"',;，；、。（(|/]|$)/gm, group: 1, score: 0.65 },

  // ---- ADDRESS ----
  {
    type: 'ADDRESS',
    re: new RegExp(`(?:[${HAN}]{2,6}(?:省|自治区))?(?:[${HAN}]{2,6}市)?[${HAN}]{1,6}(?:区|县|旗)[${HAN}\\dA-Za-z]{1,20}?\\d+(?:号|號|弄)(?:\\d+(?:号楼|栋|幢|单元|室|楼|层|座))*`, 'g'),
    score: 0.7,
  },
  {
    type: 'ADDRESS',
    re: new RegExp(`(?:〒?\\d{3}-\\d{4}[ \\u3000]*)?(?:東京都|北海道|大阪府|京都府|[${HAN}]{2,3}県)[${HAN}${HIRA}${KATA}]{1,12}?(?:市|区|町|村|郡)[${HAN}${HIRA}${KATA}\\d]{0,12}?(?:\\d+丁目\\d+番(?:地)?(?:\\d+号?)?|\\d+番地?(?:\\d+号?)?|\\d+(?:-\\d+){1,2})(?:[ \\u3000]*[${KATA}${HAN}A-Za-z]{1,12}\\d{1,4}号室)?`, 'g'),
    score: 0.7,
  },
  {
    type: 'ADDRESS',
    re: /\b\d{1,5}\s(?:[A-Z][a-z]+\s){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Boulevard|Lane|Ln|Dr|Drive|Way|Ct|Court|Pl|Place|Terrace|Harbors?|Pike|Parkway|Pkwy|Square|Sq)\b\.?(?:,?\s(?:Suite|Apt|Unit|#)\s?\w+)?(?:,\s[A-Z][a-z]+(?:\s[A-Z][a-z]+)?)?(?:,\s[A-Z]{2}(?:\s\d{5}(?:-\d{4})?)?)?/g,
    score: 0.7,
  },

  // ---- ORG ----
  {
    type: 'ORG',
    re: new RegExp(`(?:^|(?<=[在的是于和与给向从，,。\\s(（「“"]))([${HAN}A-Za-z]{2,8}(?:股份有限公司|有限责任公司|有限公司|集团|研究院|工作室))`, 'g'),
    group: 1,
    score: 0.6,
  },
  { type: 'ORG', re: new RegExp(`(?:株式会社|有限会社|合同会社)[${KATA}${HAN}A-Za-z]{1,12}|[${KATA}${HAN}A-Za-z]{1,12}(?:株式会社|有限会社|合同会社)`, 'g'), score: 0.6 },
  { type: 'ORG', re: /\b(?:[A-Z][\w&]*\s){1,3}(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Co\., Ltd\.|GmbH|Labs|Technologies|Holdings)(?![\w])/g, score: 0.6 },

  // ---- PROJECT ----
  { type: 'PROJECT', re: /\b(?:Project|Operation|[Cc]odename|[Cc]ode name)\s+[A-Z][\w-]+/g, score: 0.6 },
  { type: 'PROJECT', re: new RegExp(`(?:项目代号|代号|コードネーム)\\s*[「“"]?[${HAN}${KATA}A-Za-z-]{1,10}[」”"]?|プロジェクト[・\\s]?[${KATA}A-Za-z]{2,10}`, 'g'), score: 0.6 },

  // ---- context-keyed identifiers ----
  {
    type: 'NATIONAL_ID',
    re: /(?:(?<![A-Za-z])(?:passport(?: (?:no\.?|number))?|driver'?s? licen[cs]e(?: (?:no\.?|number))?|SSN|social security(?: number)?|tax ?id|TIN|ID ?card(?: (?:no\.?|number))?|national id(?: number)?)(?![A-Za-z])|护照(?:号码?)?|旅券番号|パスポート(?:番号)?|驾驶证(?:号)?|驾照(?:号)?|運転免許証?(?:番号)?|社保号|社会保险号|社会保障番号|税号|纳税人识别号|证件号(?:码)?|身份证(?:号码?)?)[\s:：#=*]*(?:是|は|为|:)?\s*([A-Za-z0-9][A-Za-z0-9-]{5,19})/gi,
    group: 1,
    score: 0.7,
  },
  {
    type: 'PHONE',
    re: /(?:(?<![A-Za-z])(?:phone|tel|fax|mobile|cell|call(?: us)? at|reach (?:me|us) at)(?![A-Za-z])|電話(?:番号)?|携帯|TEL|电话|手机|联系方式|座机)[^\d+(\n]{0,16}([+(]?\d[\d ().-]{5,18}\d)/gi,
    group: 1,
    score: 0.6,
  },
  {
    type: 'SECRET',
    re: /(?:(?<![A-Za-z])(?:PIN|CVV2?|CVC|security code|passcode)(?![A-Za-z])|暗証番号|安全码|验证码|セキュリティコード)[\s:：*=]*(?:is|は|是)?\s*(\d{3,8})(?!\d)/gi,
    group: 1,
    score: 0.7,
  },
  {
    type: 'SECRET',
    re: /(?:(?<![A-Za-z])password(?![A-Za-z_-])|密码|パスワード)\s*(?:is|was|は|是|为)?\s*[,:：=]?\s*([!-~]{6,40}?)(?=[\s,，。;；"'*]|[.](?:\s|$)|$)/gi,
    group: 1,
    score: 0.6,
    // looks like a password: has a digit or symbol, or mixed case
    post: v => (!looksLikeCodeRef(v) && (/\d|[^\w]/.test(v) || (/[a-z]/.test(v) && /[A-Z]/.test(v))) ? v : null),
  },
  {
    type: 'BANK_ACCOUNT',
    re: /(?:口座番号|账号|帐号|银行账户|銀行口座|振込先|account (?:no\.?|number|#)|acct\.?(?: no\.?)?)[\s:：#=]*(?:是|は|为)?\s*(\d[\d -]{5,20}\d)/gi,
    group: 1,
    score: 0.7,
  },
]

/** Baseline 2: layer-1 rules plus dictionary and context heuristics. */
export function detectHeuristic(text: string): Entity[] {
  const found: Entity[] = detectRules(text)
  for (const p of COMPILED) {
    p.re.lastIndex = 0
    let m: RegExpExecArray | null
    // eslint-disable-next-line no-cond-assign
    while ((m = p.re.exec(text))) {
      if (m[0].length === 0) {
        p.re.lastIndex++
        continue
      }
      const g = p.group ?? 0
      const idx = m.indices?.[g]
      if (!idx)
        continue
      const raw = m[g]!
      const v = p.post ? p.post(raw, m, text) : raw
      if (!v)
        continue
      const start = idx[0]
      found.push({ start, end: start + v.length, type: p.type, risk: RISK[p.type], score: p.score, source: 'heuristic' })
    }
  }
  return resolveOverlaps(found)
}

const COMPILED: Pat[] = PATS.map(p => ({ ...p, re: new RegExp(p.re.source, `${p.re.flags}d`) }))
