import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { test } from 'node:test'
import { detect, detectSync, loadDefaultModel, loadModel, MAX_INPUT, redact, RedactError, redactSync, restore } from '../src/index.ts'

const MODEL = new URL('../models/zh-en-ds48-int4.erdm', import.meta.url).pathname
const model = existsSync(MODEL) ? loadModel(readFileSync(MODEL)) : undefined

test('redact replaces high and medium tiers, same value same placeholder, restore round-trips', () => {
  const text = '把 api_key=sk-test-abcdefghijklmnop1234 发给 alice@example.com，抄送 alice@example.com'
  const r = redactSync(text, { model })
  assert.ok(!r.text.includes('alice@example.com'))
  assert.ok(!r.text.includes('sk-test-abcdefghijklmnop1234'))
  assert.equal(r.text.match(/\[EMAIL_1\]/g)?.length, 2)
  assert.equal(restore(r.text, r.mapping), text)
})

test('fail closed: too long input throws instead of returning text', () => {
  assert.throws(() => redactSync('a'.repeat(MAX_INPUT + 1)), RedactError)
})

test('fail closed: a broken model throws, no partial result', () => {
  if (!model)
    return
  const broken = { header: model.header, w: { ...model.w, 'out.weight': new Float32Array(3) } }
  assert.throws(() => redactSync('张三的电话是 13800138000', { model: broken }), RedactError)
})

test('fail closed: non-string input throws', () => {
  assert.throws(() => redactSync(undefined as unknown as string), RedactError)
})

test('odd characters: lone surrogates, NUL, ZWJ emoji, RTL marks do not crash and spans stay in range', () => {
  const nasty = ['\uD800abc\uDFFF', '\0\0\0', '👩‍👩‍👧‍👦 张三 👍🏻', '‮abc‬ 13800138000', '﻿​', '𠀋𠀋𠀋 李四', '\r\n\t'.repeat(100)]
  for (const t of nasty) {
    for (const e of detectSync(t, { model }))
      assert.ok(e.start >= 0 && e.end <= t.length && e.start < e.end)
    redactSync(t, { model })
  }
})

test('empty input', () => {
  assert.deepEqual(redactSync('', { model }), { text: '', entities: [], mapping: {} })
})

test('async redact loads the bundled model once and uses it', async () => {
  const text = '客户刘洋说登录不了，手机 139 1234 5678'
  const r = await redact(text)
  assert.ok(!r.text.includes('刘洋'), r.text)
  assert.ok(r.entities.some(e => e.source === 'model' || e.type === 'PERSON'))
  assert.equal(await loadDefaultModel(), await loadDefaultModel())
  assert.deepEqual((await detect(text)).map(e => e.type), detectSync(text, { model: await loadDefaultModel() }).map(e => e.type))
})

test('async redact with model: false runs rules only; a bad model URL throws', async () => {
  const r = await redact('电话 13800138000', { model: false })
  assert.equal(r.text, '电话 [PHONE_1]')
  await assert.rejects(loadDefaultModel(new URL('./nope.erdm', import.meta.url)), RedactError)
})
