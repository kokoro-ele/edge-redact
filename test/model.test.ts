import assert from 'node:assert/strict'
import { existsSync, readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'
import { features, loadModel, logits, ModelFormatError, predict } from '../src/model/cpu.ts'

// Fixtures come from `uv run --extra train python py/export.py <name>` (git-ignored cache); the parity
// tests skip when none have been exported yet.
const EXPORT = new URL('../training/.cache/export/', import.meta.url).pathname
const fixtureFiles = existsSync(EXPORT) ? readdirSync(EXPORT).filter(f => f.endsWith('.fixtures.json')) : []

interface Fixture { text: string, features: number[][], logits: number[][], spans: [number, number, string][] }

for (const f of fixtureFiles) {
  const { model: path, fixtures } = JSON.parse(readFileSync(join(EXPORT, f), 'utf8')) as { model: string, fixtures: Fixture[] }
  const m = loadModel(readFileSync(path))
  const nTags = m.header.tags.length

  test(`${f}: features match Python bit for bit`, () => {
    for (const fx of fixtures) {
      const got = features(fx.text)
      fx.features.forEach((row, i) => assert.deepEqual([...got.subarray(i * 6, i * 6 + 6)], row, `${JSON.stringify(fx.text.slice(0, 20))} unit ${i}`))
    }
  })

  test(`${f}: logits within 1e-4 of PyTorch, spans identical`, () => {
    for (const fx of fixtures) {
      const lg = logits(m, fx.text)
      let worst = 0
      fx.logits.forEach((row, t) => row.forEach((v, c) => {
        worst = Math.max(worst, Math.abs(lg[t * nTags + c]! - v))
      }))
      assert.ok(worst <= 1e-4, `${JSON.stringify(fx.text.slice(0, 20))}: max logit error ${worst}`)
      assert.deepEqual(predict(m, fx.text).map(s => [s.start, s.end, s.type]), fx.spans)
    }
  })

  test(`${f}: corrupt model files are rejected, never half-loaded`, () => {
    const good = new Uint8Array(readFileSync(path))
    assert.throws(() => loadModel(good.subarray(0, 4)), ModelFormatError)
    assert.throws(() => loadModel(good.subarray(0, good.length - 100)), ModelFormatError)
    const badMagic = good.slice()
    badMagic[0] = 0
    assert.throws(() => loadModel(badMagic), ModelFormatError)
    const badHeader = good.slice()
    badHeader[12] = 0xFF
    assert.throws(() => loadModel(badHeader), ModelFormatError)
    const nan = good.slice()
    const dv = new DataView(nan.buffer)
    const hlen = dv.getUint32(4, true)
    const base = 8 + hlen + ((16 - ((8 + hlen) % 16)) % 16)
    const t = m.header.tensors['proj.bias']!
    if (t.dtype === 'f32') {
      dv.setFloat32(base + t.offset, Number.NaN, true)
      assert.throws(() => loadModel(nan), ModelFormatError)
    }
  })
}
