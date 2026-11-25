/** Debug helper: node training/src/misses.ts <rules|heuristic> <TYPE|fp> [set-prefix] [limit] */
import type { BenchDoc, Pred } from './score.ts'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { detectHeuristic } from '../../src/heuristics/index.ts'
import { detectRules } from '../../src/rules/index.ts'
import { emptyCounts, scoreDoc } from './score.ts'

const [method = 'rules', what = 'fp', prefix = '', limitArg = '20'] = process.argv.slice(2)
const BENCH = new URL('../.cache/bench', import.meta.url).pathname
const detect = method === 'rules' ? detectRules : detectHeuristic
let shown = 0
const limit = +limitArg
for (const f of readdirSync(BENCH).filter(f => f.startsWith(prefix))) {
  for (const line of readFileSync(join(BENCH, f), 'utf8').split('\n').filter(Boolean)) {
    const d = JSON.parse(line) as BenchDoc
    const preds: Pred[] = detect(d.text)
    if (what === 'fp') {
      for (const p of preds) {
        const c = emptyCounts()
        scoreDoc(d, [p], c)
        if (c.fp.high + c.fp.medium + c.fp.low > 0 && shown++ < limit)
          console.log(`${f} ${p.type}: ${JSON.stringify(d.text.slice(p.start, p.end))}  ctx=${JSON.stringify(d.text.slice(Math.max(0, p.start - 25), p.end + 15))}`)
      }
      continue
    }
    for (const g of d.entities.filter(g => g.type === what)) {
      const c = emptyCounts()
      scoreDoc({ ...d, entities: [g] }, preds, c)
      const found = c.found.high + c.found.medium + c.found.low
      if (!found && shown++ < limit) {
        const near = preds.filter(p => p.start < g.end + 5 && g.start - 5 < p.end).map(p => `${p.type}:${d.text.slice(p.start, p.end)}`)
        console.log(`${f} MISS ${JSON.stringify(d.text.slice(g.start, g.end))} ctx=${JSON.stringify(d.text.slice(Math.max(0, g.start - 20), g.end + 10))} near=${JSON.stringify(near)}`)
      }
    }
  }
}
