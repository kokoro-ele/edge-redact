import type { EntityType, Risk } from '../../src/types.ts'
import { RISK, RISK_RANK } from '../../src/types.ts'

export interface Span { start: number, end: number }
export interface GoldEntity extends Span { type: EntityType, valid?: boolean }
export interface BenchDoc {
  id: string
  set: string
  lang: 'zh' | 'en' | 'mixed'
  text: string
  entities: GoldEntity[]
  ignore: Span[]
}
export interface Pred extends Span { type: EntityType, score?: number }

export interface Counts {
  /** gold entities per tier, and how many were fully covered */
  gold: Record<Risk, number>
  found: Record<Risk, number>
  /** predictions per tier */
  tp: Record<Risk, number>
  fp: Record<Risk, number>
  /** keys: TYPE, or TYPE:valid / TYPE:invalid for types with a check digit */
  goldByType: Partial<Record<string, number>>
  foundByType: Partial<Record<string, number>>
  chars: number
  docs: number
}

const zero = (): Record<Risk, number> => ({ high: 0, medium: 0, low: 0 })
export const emptyCounts = (): Counts => ({ gold: zero(), found: zero(), tp: zero(), fp: zero(), goldByType: {}, foundByType: {}, chars: 0, docs: 0 })

const isSpace = (c: string) => /\s/.test(c)

/**
 * A gold entity is found only when predictions of the same or higher risk tier cover every
 * non-whitespace character of it. A partial cover is a miss.
 *
 * A prediction is a true positive if at least half of its non-whitespace characters fall on
 * gold or ignored spans and it touches a gold entity; it is neutral if it falls on ignored spans
 * only; otherwise it is a false positive.
 */
export function scoreDoc(doc: BenchDoc, preds: Pred[], c: Counts): void {
  const { text } = doc
  c.chars += text.length
  c.docs++
  for (const g of doc.entities) {
    const tier = RISK[g.type]
    c.gold[tier]++
    const keys = g.valid === undefined ? [g.type] : [g.type, `${g.type}:${g.valid ? 'valid' : 'invalid'}`]
    for (const k of keys)
      c.goldByType[k] = (c.goldByType[k] ?? 0) + 1
    const covering = preds.filter(p => RISK_RANK[RISK[p.type]] >= RISK_RANK[tier] && p.start < g.end && g.start < p.end)
    let ok = true
    for (let i = g.start; i < g.end && ok; i++) {
      if (isSpace(text[i]!))
        continue
      if (!covering.some(p => p.start <= i && i < p.end))
        ok = false
    }
    if (ok) {
      c.found[tier]++
      for (const k of keys)
        c.foundByType[k] = (c.foundByType[k] ?? 0) + 1
    }
  }
  for (const p of preds) {
    const tier = RISK[p.type]
    let n = 0
    let onAny = 0
    let onGold = 0
    for (let i = p.start; i < p.end; i++) {
      if (isSpace(text[i]!))
        continue
      n++
      const inGold = doc.entities.some(g => g.start <= i && i < g.end)
      if (inGold)
        onGold++
      if (inGold || doc.ignore.some(s => s.start <= i && i < s.end))
        onAny++
    }
    if (n === 0)
      continue
    if (onAny / n >= 0.5) {
      if (onGold > 0)
        c.tp[tier]++
    }
    else {
      c.fp[tier]++
    }
  }
}

export function addCounts(a: Counts, b: Counts): Counts {
  const out = emptyCounts()
  for (const k of ['gold', 'found', 'tp', 'fp'] as const) {
    for (const r of ['high', 'medium', 'low'] as const)
      out[k][r] = a[k][r] + b[k][r]
  }
  for (const k of ['goldByType', 'foundByType'] as const) {
    for (const src of [a[k], b[k]]) {
      for (const [t, v] of Object.entries(src))
        out[k][t] = (out[k][t] ?? 0) + v!
    }
  }
  out.chars = a.chars + b.chars
  out.docs = a.docs + b.docs
  return out
}

export const recall = (c: Counts, r: Risk) => (c.gold[r] ? c.found[r] / c.gold[r] : Number.NaN)
export const precision = (c: Counts, r: Risk) => (c.tp[r] + c.fp[r] ? c.tp[r] / (c.tp[r] + c.fp[r]) : Number.NaN)
export function f2(c: Counts, r: Risk): number {
  const p = precision(c, r)
  const R = recall(c, r)
  if (!(p + R))
    return Number.isNaN(p + R) ? Number.NaN : 0
  return (5 * p * R) / (4 * p + R)
}
export const fpPer1k = (c: Counts) => ((c.fp.high + c.fp.medium + c.fp.low) / c.chars) * 1000
