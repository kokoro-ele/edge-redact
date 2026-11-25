/**
 * Run the shipped TS runtime (src/model/cpu.ts) over the benchmark, so `pnpm bench` scores exactly what
 * users get, not just the PyTorch model.
 *
 *   node src/tspredict.ts <model.erdm> <label> [--ext]
 *
 * Writes .cache/preds/model-<label>/<set>.jsonl (or .cache/ext-preds/...) in the format of py/predict.py.
 */
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { loadModel, predict } from '../../src/model/cpu.ts'

const [path, label] = process.argv.slice(2)
if (!path || !label)
  throw new Error('usage: node src/tspredict.ts <model.erdm> <label> [--ext]')
const ext = process.argv.includes('--ext')
const root = new URL('../.cache/', import.meta.url).pathname
const src = join(root, ext ? 'ext' : 'bench')
const out = join(root, ext ? 'ext-preds' : 'preds', `model-${label}`)
mkdirSync(out, { recursive: true })
const m = loadModel(readFileSync(path))
for (const f of readdirSync(src).filter(f => f.endsWith('.jsonl')).sort()) {
  const t0 = performance.now()
  let units = 0
  const rows = readFileSync(join(src, f), 'utf8').split('\n').filter(Boolean).map((line) => {
    const d = JSON.parse(line) as { id: string, text: string }
    units += d.text.length
    const entities = predict(m, d.text).map(s => ({ start: s.start, end: s.end, type: s.type, score: Math.round(s.score * 1e4) / 1e4 }))
    return JSON.stringify({ id: d.id, entities })
  })
  writeFileSync(join(out, f), `${rows.join('\n')}\n`)
  console.log(`model-${label} ${f}: ${rows.length} docs, ${units} units in ${((performance.now() - t0) / 1000).toFixed(1)}s`)
}
