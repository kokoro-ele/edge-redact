/**
 * Prints the M0 baseline table. Usage: pnpm bench [--write]
 *
 * Methods:
 * - rules:      layer 1 only (src/rules)
 * - heuristic:  rules + surname dictionaries + context cues (src/heuristics)
 * - teacher:*:  predictions cached by `pnpm teacher` in training/.cache/preds/<name>/<set>.jsonl
 */
import type { Entity, EntityType, Risk } from '../../src/types.ts'
import type { BenchDoc, Counts, Pred } from './score.ts'
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { detectHeuristic } from '../../src/heuristics/index.ts'
import { detectRules, fillGaps, resolveOverlaps, tidySpans } from '../../src/rules/index.ts'
import { RISK } from '../../src/types.ts'
import { addCounts, emptyCounts, f2, fpPer1k, precision, recall, scoreDoc } from './score.ts'

const ROOT = new URL('..', import.meta.url).pathname
const BENCH = join(ROOT, '.cache/bench')
const PREDS = join(ROOT, '.cache/preds')
const LANGS = ['zh', 'en', 'mixed'] as const
const HIGH_FLOOR = 0.995

function readJsonl<T>(path: string): T[] {
  return readFileSync(path, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l) as T)
}

const sets = readdirSync(BENCH).filter(f => f.endsWith('.jsonl')).map(f => f.slice(0, -6)).sort()
const docs: Record<string, BenchDoc[]> = Object.fromEntries(sets.map(s => [s, readJsonl<BenchDoc>(join(BENCH, `${s}.jsonl`))]))
// predictions are joined by id, so a repeated id would silently score one document's spans against another
for (const [s, ds] of Object.entries(docs)) {
  const seen = new Set<string>()
  for (const d of ds) {
    if (seen.has(d.id))
      throw new Error(`duplicate id ${d.id} in ${s}`)
    seen.add(d.id)
  }
}

type Predictor = (doc: BenchDoc) => Pred[]
const methods: [string, Predictor | null][] = [
  ['rules', d => detectRules(d.text)],
  ['rules+heuristics', d => detectHeuristic(d.text)],
  ['shipped (no model)', d => tidySpans(d.text, detectHeuristic(d.text))],
]
if (existsSync(PREDS)) {
  for (const name of readdirSync(PREDS).sort()) {
    const dir = join(PREDS, name)
    const byId = new Map<string, Pred[]>()
    let complete = true
    for (const s of sets) {
      const f = join(dir, `${s}.jsonl`)
      if (!existsSync(f)) {
        complete = false
        continue
      }
      for (const r of readJsonl<{ id: string, entities: Pred[] }>(f))
        byId.set(r.id, r.entities)
      // stale predictions (e.g. ids changed when a set was rebuilt) count as missing, not as "found nothing"
      if (docs[s]!.some(d => !byId.has(d.id)))
        complete = false
    }
    const tag = `${name}${complete ? '' : ' (partial)'}`
    const teach = (d: BenchDoc): Entity[] => (byId.get(d.id) ?? []).map(p => ({ ...p, risk: RISK[p.type], score: p.score ?? 1, source: 'model' }))
    // our own models are saved as model-<name>; everything else is a teacher
    const kind = name.startsWith('model-') ? 'model' : 'teacher'
    const short = name.replace(/^model-/, '')
    methods.push([`${kind}:${short}${complete ? '' : ' (partial)'}`, teach])
    // the product shape: rules first, model fills in
    methods.push([`rules+${kind}:${short}${complete ? '' : ' (partial)'}`, d => resolveOverlaps([...detectRules(d.text), ...teach(d)])])
    // shipping shape: rules + heuristics first, the model only fills gaps
    methods.push([`full+${kind}:${short}${complete ? '' : ' (partial)'}`, d => fillGaps(detectHeuristic(d.text), teach(d))])
    methods.push([`shipped+${kind}:${short}${complete ? '' : ' (partial)'}`, d => tidySpans(d.text, fillGaps(detectHeuristic(d.text), teach(d)))])
  }
}

// method -> set -> counts
const results = new Map<string, Map<string, Counts>>()
const timing = new Map<string, number>()
for (const [name, predict] of methods) {
  const perSet = new Map<string, Counts>()
  const t0 = performance.now()
  for (const s of sets) {
    const c = emptyCounts()
    for (const d of docs[s]!) {
      const preds = predict!(d)
      // teachers may skip sets; treat missing as no prediction only for complete runs
      scoreDoc(d, preds, c)
    }
    perSet.set(s, c)
  }
  timing.set(name, performance.now() - t0)
  results.set(name, perSet)
}

const pct = (x: number) => (Number.isNaN(x) ? '–' : `${(x * 100).toFixed(1)}%`)
const isNeg = (s: string) => s.startsWith('neg-')
const langOfSet = (s: string) => s.split('-')[0] as typeof LANGS[number]

function poolBy(perSet: Map<string, Counts>, pred: (s: string, d?: BenchDoc) => boolean): Counts {
  let c = emptyCounts()
  for (const [s, v] of perSet) {
    if (pred(s))
      c = addCounts(c, v)
  }
  return c
}

/** Negative set is mixed-language: score per doc language. */
function negByLang(predict: Predictor | null, name: string): Record<string, Counts> {
  const out: Record<string, Counts> = {}
  for (const s of sets.filter(isNeg)) {
    for (const d of docs[s]!) {
      const c = (out[d.lang] ??= emptyCounts())
      scoreDoc(d, predict ? predict(d) : [], c)
    }
  }
  void name
  return out
}

const lines: string[] = []
const out = (s = '') => lines.push(s)

const totals = Object.fromEntries(sets.map(s => [s, docs[s]!.length]))
out(`# M0 baseline results`)
out()
out(`Generated by \`pnpm bench\` on ${new Date().toISOString().slice(0, 10)}. Benchmark sets: ${sets.map(s => `${s} (${totals[s]})`).join(', ')}.`)
out()
out(`Counting: per entity span. A gold entity counts as found only when predictions of the same or a higher risk tier cover all its non-space characters. High risk has a recall floor of ${pct(HIGH_FLOOR)}.`)
out()

for (const lang of LANGS) {
  out(`## ${lang}`)
  out()
  out('| Method | High R | High P | Floor | Med R | Med P | Med F2 | Low R | Low P | Low F2 |')
  out('| --- | ---: | ---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: |')
  for (const [name] of methods) {
    const c = poolBy(results.get(name)!, s => !isNeg(s) && langOfSet(s) === lang)
    const hr = recall(c, 'high')
    out(`| ${name} | ${pct(hr)} | ${pct(precision(c, 'high'))} | ${Number.isNaN(hr) ? '–' : hr >= HIGH_FLOOR ? 'pass' : 'FAIL'} | ${pct(recall(c, 'medium'))} | ${pct(precision(c, 'medium'))} | ${pct(f2(c, 'medium'))} | ${pct(recall(c, 'low'))} | ${pct(precision(c, 'low'))} | ${pct(f2(c, 'low'))} |`)
  }
  const g = poolBy(results.get('rules')!, s => !isNeg(s) && langOfSet(s) === lang)
  out()
  out(`Gold entities: high ${g.gold.high}, medium ${g.gold.medium}, low ${g.gold.low}.`)
  out()
}

out('## False positives on text with no PII')
out()
out('False positives per 1,000 characters on the hard-negative set (logs, stack traces, code, paths, versions, order numbers, product models, fictional names).')
out()
out(`| Method | ${LANGS.join(' | ')} | all | high-risk FPs | medium | low |`)
out(`| --- | ${LANGS.map(() => '---:').join(' | ')} | ---: | ---: | ---: | ---: |`)
for (const [name, predict] of methods) {
  const p: Predictor = predict ?? (() => [])
  const nb = negByLang(p, name)
  let all = emptyCounts()
  for (const c of Object.values(nb)) all = addCounts(all, c)
  out(`| ${name} | ${LANGS.map(l => (nb[l] ? fpPer1k(nb[l]).toFixed(2) : '–')).join(' | ')} | ${fpPer1k(all).toFixed(2)} | ${all.fp.high} | ${all.fp.medium} | ${all.fp.low} |`)
}
{
  let chars = 0
  let n = 0
  for (const s of sets.filter(isNeg)) {
    for (const d of docs[s]!) {
      chars += d.text.length
      n++
    }
  }
  out()
  out(`The set has ${n} documents and ${chars.toLocaleString('en')} characters.`)
}
out()

out('## By benchmark set')
out()
out('Recall per tier, and medium-tier precision.')
out()
out(`| Set | ${methods.map(([n]) => n).join(' | ')} |`)
out(`| --- | ${methods.map(() => '---').join(' | ')} |`)
for (const s of sets.filter(s => !isNeg(s))) {
  out(`| ${s} | ${methods.map(([n]) => {
    const c = results.get(n)!.get(s)!
    return `H ${pct(recall(c, 'high'))} · M ${pct(recall(c, 'medium'))} · L ${pct(recall(c, 'low'))} · MP ${pct(precision(c, 'medium'))}`
  }).join(' | ')} |`)
}
out()

out('## Recall per entity type, all positive sets')
out()
const types = Object.keys(RISK) as EntityType[]
out(`| Type | Tier | Gold | ${methods.map(([n]) => n).join(' | ')} |`)
out(`| --- | --- | ---: | ${methods.map(() => '---:').join(' | ')} |`)
const allPos = new Map(methods.map(([n]) => [n, poolBy(results.get(n)!, s => !isNeg(s))]))
for (const t of types) {
  for (const key of [t, `${t}:valid`, `${t}:invalid`]) {
    const gold = allPos.get('rules')!.goldByType[key] ?? 0
    if (!gold)
      continue
    const label = key === t ? t : `↳ checksum ${key.split(':')[1]}`
    out(`| ${label} | ${RISK[t] as Risk} | ${gold} | ${methods.map(([n]) => pct((allPos.get(n)!.foundByType[key] ?? 0) / gold)).join(' | ')} |`)
  }
}
out()
out('## Time')
out()
for (const [n, ms] of timing) {
  if (!n.startsWith('teacher'))
    out(`- ${n}: ${ms.toFixed(0)} ms for all ${Object.values(totals).reduce((a, b) => a + b, 0)} documents.`)
}

const md = lines.join('\n')
console.log(md)
if (process.argv.includes('--write'))
  writeFileSync(join(ROOT, 'data/results/m0-baselines.md'), `${md}\n`)
