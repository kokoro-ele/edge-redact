/**
 * Scores every method on RedactionBench (en, untyped, 200 documents) with the dataset's own
 * R-Score scorer, so the numbers are comparable to its leaderboard. Usage: pnpm rbench [--write]
 *
 * Needs `pnpm data` (downloads the set into .cache/raw/redactionbench and writes .cache/ext/redactionbench.jsonl).
 * Teacher predictions come from `uv run --extra teacher python py/teacher.py <name> --ext`.
 *
 * Every detected entity is submitted as a redaction, whatever its tier. Thresholds are fixed, not
 * tuned on this set (the leaderboard tunes each model's threshold on the benchmark itself).
 */
import type { Entity } from '../../src/types.ts'
import { execFileSync } from 'node:child_process'
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { detectHeuristic } from '../../src/heuristics/index.ts'
import { detectRules, fillGaps, resolveOverlaps, tidySpans } from '../../src/rules/index.ts'
import { RISK } from '../../src/types.ts'

const ROOT = new URL('..', import.meta.url).pathname
const RAW = join(ROOT, '.cache/raw/redactionbench')
const DOCS = join(ROOT, '.cache/ext/redactionbench.jsonl')
const PREDS = join(ROOT, '.cache/ext-preds')
const OUT = join(ROOT, '.cache/rbench')

interface Doc { id: string, text: string }
interface Span { start: number, end: number, type: Entity['type'], score?: number }

const readJsonl = <T>(p: string): T[] => readFileSync(p, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l) as T)

if (!existsSync(DOCS)) {
  console.error('missing .cache/ext/redactionbench.jsonl; run `pnpm data` first')
  process.exit(1)
}
const docs = readJsonl<Doc>(DOCS)

/** UTF-16 offset -> code point offset (the scorer counts code points). */
function cpMap(text: string): Int32Array {
  const m = new Int32Array(text.length + 1)
  let cp = 0
  for (let i = 0; i < text.length; i++) {
    m[i] = cp
    const c = text.charCodeAt(i)
    if (c >= 0xD800 && c <= 0xDBFF && i + 1 < text.length) {
      m[++i] = cp
    }
    cp++
  }
  m[text.length] = cp
  return m
}

type Predictor = (d: Doc) => Span[]
const methods: [string, Predictor][] = [
  ['rules', d => detectRules(d.text)],
  ['rules+heuristics', d => detectHeuristic(d.text)],
  ['shipped (no model)', d => tidySpans(d.text, detectHeuristic(d.text))],
]
if (existsSync(PREDS)) {
  for (const name of readdirSync(PREDS).sort()) {
    const f = join(PREDS, name, 'redactionbench.jsonl')
    if (!existsSync(f))
      continue
    const byId = new Map(readJsonl<{ id: string, entities: Span[] }>(f).map(r => [r.id, r.entities]))
    const teach = (d: Doc): Entity[] => (byId.get(d.id) ?? []).map(p => ({ ...p, risk: RISK[p.type], score: p.score ?? 1, source: 'model' }))
    const kind = name.startsWith('model-') ? 'model' : 'teacher'
    const short = name.replace(/^model-/, '')
    methods.push([`${kind}:${short}`, teach])
    methods.push([`rules+${kind}:${short}`, d => resolveOverlaps([...detectRules(d.text), ...teach(d)])])
    // shipping shape: rules + heuristics first, the model only fills gaps
    methods.push([`full+${kind}:${short}`, d => fillGaps(detectHeuristic(d.text), teach(d))])
    methods.push([`shipped+${kind}:${short}`, d => tidySpans(d.text, fillGaps(detectHeuristic(d.text), teach(d)))])
  }
}

mkdirSync(OUT, { recursive: true })
const rows: { method: string, mean: number, cats: Record<string, number>, mand: number, fpRuns: number, ms: number }[] = []
for (const [method, predict] of methods) {
  const t0 = performance.now()
  const lines = docs.map((d) => {
    const m = cpMap(d.text)
    const preds = predict(d)
      .map(p => ({ start: m[p.start]!, end: m[p.end]! }))
      .filter(p => p.start < p.end)
    return JSON.stringify({ document_id: d.id, predictions: preds })
  })
  const ms = performance.now() - t0
  const file = join(OUT, `${method.replace(/[^\w+-]/g, '_')}.ndjson`)
  writeFileSync(file, `${lines.join('\n')}\n`)
  // The official scorer is stdlib-only Python; it imports its sibling module, so run it from its directory.
  const report = JSON.parse(execFileSync('python3', ['-E', '-s', 'score.py', '--dataset', 'documents.ndjson', '--predictions', file], { cwd: RAW, maxBuffer: 1 << 28 }).toString())
  const ds = report.document_scores as { mandatory_coverage_sum: number, mandatory_total: number, background_false_positive_count: number }[]
  const mandTotal = ds.reduce((a, r) => a + r.mandatory_total, 0)
  rows.push({
    method,
    mean: report.mean_rscore,
    cats: report.per_category,
    mand: ds.reduce((a, r) => a + r.mandatory_coverage_sum, 0) / mandTotal,
    fpRuns: ds.reduce((a, r) => a + r.background_false_positive_count, 0),
    ms,
  })
}

const cats = Object.keys(rows[0]!.cats)
const pct = (x: number) => x.toFixed(3)
const out: string[] = [
  '# RedactionBench (en)',
  '',
  `R-Score from the dataset's own scorer (revision 77684d7e), ${docs.length} documents, ${docs.reduce((a, d) => a + d.text.length, 0).toLocaleString('en')} characters. Every detected entity is redacted regardless of tier; thresholds are not tuned on this set. Leaderboard for reference: Claude Opus 5.5 0.832, OpenAI Privacy Filter 0.533, nvidia/gliner-PII 0.339, gliner_multi_pii-v1 0.309, ai4privacy multilingual 0.180 (thresholds tuned on the benchmark).`,
  '',
  `| Method | R-Score | Mandatory coverage | Background FP runs | ${cats.join(' | ')} |`,
  `| --- | ---: | ---: | ---: | ${cats.map(() => '---:').join(' | ')} |`,
  ...rows.map(r => `| ${r.method} | **${pct(r.mean)}** | ${(100 * r.mand).toFixed(1)}% | ${r.fpRuns} | ${cats.map(c => pct(r.cats[c]!)).join(' | ')} |`),
  '',
]
console.log(out.join('\n'))
if (process.argv.includes('--write')) {
  const dest = join(ROOT, 'data/results/redactionbench.md')
  writeFileSync(dest, out.join('\n'))
  console.log(`wrote ${dest}`)
}
