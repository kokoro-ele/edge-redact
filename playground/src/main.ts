import type { Entity, EntityType } from '../../src/index.ts'
import type { Req, Res } from './worker.ts'
import { redactSync, restore, RISK } from '../../src/index.ts'

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T
const input = $<HTMLTextAreaElement>('input')
const backdrop = $('backdrop')
const output = $('output')
const copyBtn = $<HTMLButtonElement>('copy')
const list = $('entities')
const reply = $<HTMLTextAreaElement>('reply')
const restored = $('restored')

const LABEL: Record<EntityType, string> = {
  CN_ID: '身份证号',
  JP_MYNUMBER: 'My Number',
  CREDIT_CARD: '银行卡号',
  BANK_ACCOUNT: '银行账号',
  NATIONAL_ID: '证件号',
  SECRET: '密钥',
  PERSON: '人名',
  ADDRESS: '地址',
  PHONE: '电话',
  EMAIL: '邮箱',
  IP: 'IP',
  OTHER_ID: '编号',
  ORG: '机构',
  PROJECT: '项目',
}
const SOURCE: Record<Entity['source'], string> = { rule: '规则', heuristic: '启发式', model: '模型' }
const TIER = { high: 0, medium: 1, low: 2 } as const

const EXAMPLES: [string, string][] = [
  ['客服工单', '客户刘洋说登录不了，手机 139 1234 5678，邮箱 liuyang@example.com'],
  ['中英混写', '跟 Kevin Zhang 约了周五 call，他的 email 是 kevin.zhang@example.org'],
  ['快递信息', '收件人陈静，浙江省杭州市西湖区文三路90号，电话 13800138000'],
  ['服务器日志', 'login failed for zhaolei@example.com from 203.0.113.7, token: sk-live-9f8e7d6c5b4a3210zyxw'],
  ['付款', '卡号 4111 1111 1111 1111，身份证 11010519491231002X'],
  ['英文邮件', 'Hi, this is Emily Carter from Northwind Labs. Reach me at +1 415 555 0199.'],
  ['面试', '候选人张敏，现就职于星河数据科技有限公司，电话 186 0000 1234'],
  ['这些不遮', '订单号 744449438908532518，版本 v3.2.1，commit e1d19fa6'],
]

// ---- worker ----
const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })
let nextId = 0
const waiting = new Map<number, { ok: (r: { entities: Entity[], ms: number }) => void, err: (e: Error) => void }>()
let fatal = ''

function setStatus(kind: '' | 'ok' | 'err', text: string) {
  $('status').className = `status ${kind}`
  $('status-text').textContent = text
}

worker.onmessage = (ev: MessageEvent<Res>) => {
  const m = ev.data
  if (m.type === 'ready') {
    setStatus('ok', `本地模型 · ${(m.bytes / 1e6).toFixed(2)} MB`)
  }
  else if (m.type === 'fatal') {
    fail(`模型加载失败：${m.message}`)
  }
  else {
    const w = waiting.get(m.id)
    waiting.delete(m.id)
    if (m.type === 'result')
      w?.ok(m)
    else
      w?.err(new Error(m.message))
  }
}
worker.onerror = e => fail(`检测进程崩溃：${e.message || '未知错误'}`)

function detect(text: string) {
  return new Promise<{ entities: Entity[], ms: number }>((ok, err) => {
    const id = ++nextId
    waiting.set(id, { ok, err })
    worker.postMessage({ id, text } satisfies Req)
  })
}

function marks(el: HTMLElement, text: string, ents: Entity[]) {
  el.replaceChildren()
  let pos = 0
  for (const e of [...ents].sort((a, b) => a.start - b.start)) {
    if (e.start < pos)
      continue
    el.append(text.slice(pos, e.start))
    const m = document.createElement('mark')
    m.className = e.risk
    m.textContent = text.slice(e.start, e.end)
    el.append(m)
    pos = e.end
  }
  el.append(text.slice(pos))
}

/** Fail closed: no copyable output after any error. */
function fail(message: string) {
  fatal = message
  setStatus('err', '出错')
  copyBtn.disabled = true
  output.className = 'output err'
  output.textContent = `${message}\n为了安全，没有生成结果。请刷新页面重试。`
  $('meta').textContent = ''
}

// ---- state ----
let shown = { text: '', entities: [] as Entity[] }
let mapping: Record<string, string> = {}
let redacted = ''
let lastMs = 0
let tab: 'out' | 'restore' = 'out'
const overrides = new Map<string, boolean>() // type + value -> redact?
const key = (e: Entity, text: string) => `${e.type}\0${text.slice(e.start, e.end)}`
const isOn = (e: Entity, text: string) => overrides.get(key(e, text)) ?? e.risk !== 'low'
const toggle = (e: Entity, text: string) => {
  overrides.set(key(e, text), !isOn(e, text))
  render()
}

function paintBackdrop() {
  const text = input.value
  const keep = shown.entities.filter(e => text.slice(e.start, e.end) === shown.text.slice(e.start, e.end))
  marks(backdrop, `${text}\n`, keep)
  $('input-meta').textContent = `${text.length.toLocaleString()} 字`
}

function render() {
  if (fatal)
    return
  const { text, entities } = shown
  const r = redactSync(text, { entities, select: e => isOn(e, text) })
  redacted = r.text
  mapping = r.mapping

  // output: walk the original, redacted entities become placeholder chips
  output.className = 'output'
  output.replaceChildren()
  if (!text) {
    output.innerHTML = '<span class="empty">脱敏结果</span>'
  }
  else {
    const counters: Record<string, number> = {}
    const seen = new Map<string, string>()
    let pos = 0
    for (const e of entities) {
      output.append(text.slice(pos, e.start))
      const value = text.slice(e.start, e.end)
      const b = document.createElement('button')
      b.type = 'button'
      if (isOn(e, text)) {
        const k = key(e, text)
        let ph = seen.get(k)
        if (!ph) {
          counters[e.type] = (counters[e.type] ?? 0) + 1
          ph = `[${e.type}_${counters[e.type]}]`
          seen.set(k, ph)
        }
        b.className = `ph ${e.risk}`
        b.textContent = ph
        b.title = value
      }
      else {
        b.className = 'reveal'
        b.textContent = value
      }
      b.onclick = () => toggle(e, text)
      output.append(b)
      pos = e.end
    }
    output.append(text.slice(pos))
  }

  // detected list
  list.replaceChildren()
  $('count').textContent = String(entities.length)
  if (!entities.length) {
    const li = document.createElement('li')
    li.className = 'empty'
    li.textContent = text ? '未发现个人信息' : '—'
    list.append(li)
  }
  for (const e of [...entities].sort((a, b) => TIER[a.risk] - TIER[b.risk] || a.start - b.start)) {
    const on = isOn(e, text)
    const li = document.createElement('li')
    li.className = `ent${on ? '' : ' off'}`
    const dot = document.createElement('i')
    dot.className = `dot ${e.risk}`
    const body = document.createElement('span')
    body.className = 'body'
    const type = document.createElement('span')
    type.className = 'type'
    type.textContent = `${LABEL[e.type] ?? e.type} · ${SOURCE[e.source]}`
    const value = document.createElement('span')
    value.className = 'value'
    value.textContent = text.slice(e.start, e.end)
    value.title = value.textContent
    body.append(type, value)
    const sw = document.createElement('input')
    sw.type = 'checkbox'
    sw.className = 'switch'
    sw.checked = on
    sw.setAttribute('aria-label', `遮盖 ${value.textContent}`)
    sw.onclick = ev => ev.stopPropagation()
    sw.onchange = () => toggle(e, text)
    li.onclick = () => toggle(e, text)
    li.append(dot, body, sw)
    list.append(li)
  }

  const n = entities.filter(e => isOn(e, text)).length
  $('meta').textContent = text ? `遮盖 ${n} 处 · ${lastMs < 10 ? lastMs.toFixed(1) : Math.round(lastMs)} ms` : ''
  renderRestore()
  updateCopy()
}

/** Same text as restore(), with the values that came back highlighted. */
function renderRestored(t: string) {
  restored.replaceChildren()
  let pos = 0
  for (const m of t.matchAll(/\[([A-Z_]+)_\d+\]/g)) {
    const value = mapping[m[0]]
    if (value === undefined)
      continue
    restored.append(t.slice(pos, m.index))
    const mk = document.createElement('mark')
    mk.className = RISK[m[1] as EntityType] ?? 'medium'
    mk.textContent = value
    restored.append(mk)
    pos = m.index + m[0].length
  }
  restored.append(t.slice(pos))
}

function renderRestore() {
  const t = reply.value
  if (!t)
    restored.innerHTML = '<span class="empty">还原后的文本</span>'
  else
    renderRestored(t)
  updateCopy()
}

function updateCopy() {
  copyBtn.disabled = tab === 'out'
    ? !!fatal || !shown.text || input.value !== shown.text
    : !reply.value
}

let seq = 0
let timer: ReturnType<typeof setTimeout> | undefined
function onInput() {
  paintBackdrop()
  if (fatal)
    return
  updateCopy() // output no longer matches the input until detection returns
  output.classList.add('stale')
  clearTimeout(timer)
  timer = setTimeout(async () => {
    const text = input.value
    const my = ++seq
    try {
      const { entities, ms } = await detect(text)
      if (my !== seq)
        return
      shown = { text, entities }
      lastMs = ms
      paintBackdrop()
      render()
    }
    catch (e) {
      if (my === seq)
        fail(`检测出错：${(e as Error).message}`)
    }
  }, 60)
}

function setTab(t: 'out' | 'restore') {
  tab = t
  $('tab-out').setAttribute('aria-selected', String(t === 'out'))
  $('tab-restore').setAttribute('aria-selected', String(t === 'restore'))
  $('view-out').hidden = t !== 'out'
  $('view-restore').hidden = t !== 'restore'
  updateCopy()
}

async function copy() {
  if (copyBtn.disabled)
    return
  if (tab === 'out' && (fatal || input.value !== shown.text))
    return
  await navigator.clipboard.writeText(tab === 'out' ? redacted : restore(reply.value, mapping))
  copyBtn.textContent = '已复制'
  setTimeout(() => (copyBtn.textContent = '复制'), 1200)
}

input.addEventListener('input', onInput)
reply.addEventListener('input', renderRestore)
copyBtn.onclick = () => void copy()
$('tab-out').onclick = () => setTab('out')
$('tab-restore').onclick = () => setTab('restore')
$('clear').onclick = () => {
  input.value = ''
  onInput()
  input.focus()
}

function load(text: string) {
  input.value = text
  onInput()
  setTab('out')
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const grid = $('examples')
for (const [title, text] of EXAMPLES) {
  const b = document.createElement('button')
  b.type = 'button'
  b.className = 'ex'
  const t = document.createElement('span')
  t.className = 't'
  t.textContent = title
  const x = document.createElement('span')
  x.className = 'x'
  x.textContent = text
  b.append(t, x)
  b.onclick = () => load(text)
  grid.append(b)
  detect(text).then(r => marks(x, text, r.entities)).catch(() => {})
}

load(EXAMPLES[0]![1])
