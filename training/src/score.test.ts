import type { BenchDoc } from './score.ts'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { test } from 'node:test'
import { emptyCounts, fpPer1k, precision, recall, scoreDoc } from './score.ts'

const doc: BenchDoc = {
  id: 't',
  set: 'x',
  lang: 'en',
  text: 'Call Ann Lee at 555-0100 or Bob',
  entities: [{ start: 5, end: 12, type: 'PERSON' }, { start: 16, end: 24, type: 'PHONE' }],
  ignore: [{ start: 28, end: 31 }],
}

test('gold as predictions scores 100%', () => {
  const c = emptyCounts()
  scoreDoc(doc, doc.entities, c)
  assert.equal(recall(c, 'medium'), 1)
  assert.equal(precision(c, 'medium'), 1)
  assert.equal(fpPer1k(c), 0)
})

test('partial cover is a miss; lower tier does not cover', () => {
  const c = emptyCounts()
  scoreDoc(doc, [{ start: 5, end: 8, type: 'PERSON' }, { start: 16, end: 24, type: 'ORG' }], c)
  assert.equal(c.found.medium, 0)
})

test('higher tier covers; ignored span is neutral; stray span is FP', () => {
  const c = emptyCounts()
  scoreDoc(doc, [{ start: 5, end: 12, type: 'SECRET' }, { start: 28, end: 31, type: 'PERSON' }, { start: 0, end: 4, type: 'PERSON' }], c)
  assert.equal(c.found.medium, 1)
  assert.equal(c.fp.medium, 1)
  assert.equal(c.fp.high, 0)
})

test('every benchmark set scores 100% against its own gold', { skip: !readdirSync(new URL('../.cache', import.meta.url)).includes('bench') }, () => {
  const dir = new URL('../.cache/bench/', import.meta.url)
  for (const f of readdirSync(dir)) {
    const c = emptyCounts()
    for (const l of readFileSync(new URL(f, dir), 'utf8').split('\n').filter(Boolean)) {
      const d = JSON.parse(l) as BenchDoc
      scoreDoc(d, d.entities, c)
    }
    for (const r of ['high', 'medium', 'low'] as const) {
      if (c.gold[r])
        assert.equal(recall(c, r), 1, `${f} ${r}`)
    }
    assert.equal(c.fp.high + c.fp.medium + c.fp.low, 0, f)
  }
})
