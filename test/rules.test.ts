import assert from 'node:assert/strict'
import { test } from 'node:test'
import { detectHeuristic, detectRules } from '../src/index.ts'
import { cnIdValid, luhn, myNumberCheckDigit, myNumberValid } from '../src/rules/checksums.ts'

// All values are synthetic: test card BINs, CN IDs with birth years 2050+, documentation IPs.
const types = (t: string, f = detectRules) => f(t).map(e => `${e.type}:${t.slice(e.start, e.end)}`)

test('checksums', () => {
  assert.ok(luhn('4111111111111111'))
  assert.ok(!luhn('4111111111111112'))
  const base = '11010520500101123'
  const w = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
  const id = base + '10X98765432'[[...base].reduce((s, c, i) => s + Number(c) * w[i]!, 0) % 11]
  assert.ok(cnIdValid(id))
  assert.ok(!cnIdValid(`${base}${id.at(-1) === '0' ? '1' : '0'}`))
  const mn = `12345678901${myNumberCheckDigit('12345678901')}`
  assert.ok(myNumberValid(mn))
})

test('high-risk rules', () => {
  assert.deepEqual(types('卡号 4111 1111 1111 1111 已绑定'), ['CREDIT_CARD:4111 1111 1111 1111'])
  assert.deepEqual(types('key: sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAA'), ['SECRET:sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAAAAAA'])
  assert.deepEqual(types('postgres://app:s3cret@db.example.com:5432/x'), ['SECRET:postgres://app:s3cret@db.example.com:5432/x'])
})

test('medium-risk rules', () => {
  assert.deepEqual(types('mail taro@example.com now'), ['EMAIL:taro@example.com'])
  assert.deepEqual(types('手机 138 0013 8000'), ['PHONE:138 0013 8000'])
  assert.deepEqual(types('host 192.0.2.10 down'), ['IP:192.0.2.10'])
})

test('hard negatives stay clean', () => {
  for (const t of [
    'upgrade from version 4.3.7.194 to 4.4.0.1',
    'react@6.9.1.128 is broken',
    '订单号 4111111111111111 已发货',
    'at com.example.Foo.bar(Foo.java:42)',
    'logo@2x.png',
  ])
    assert.deepEqual(types(t, detectHeuristic), [], t)
})

test('heuristics find names with honorifics', () => {
  assert.ok(types('王小明先生您好', detectHeuristic).includes('PERSON:王小明'))
  assert.ok(types('佐藤様、ご確認ください', detectHeuristic).some(s => s.startsWith('PERSON:佐藤')))
})

test('code that mentions names or passwords is not PII', () => {
  for (const s of [
    '#     container_name: postgres\n',
    '        password=config.snowflake_password,\n',
    'aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $(ECR_REG)',
    "to_jsonb(OLD) - 'password_hash',",
    '/* login, register, password reset) */',
  ]) assert.deepEqual(detectHeuristic(s).filter(e => e.type === 'PERSON' || e.type === 'SECRET'), [], s)
  assert.equal(detectHeuristic('name: Jane Doe\n').filter(e => e.type === 'PERSON').length, 1)
  assert.equal(detectHeuristic('姓名：王小明\n').filter(e => e.type === 'PERSON').length, 1)
  assert.equal(detectHeuristic('my password is Tr0ub4dor&3 ok').filter(e => e.type === 'SECRET').length, 1)
})

test('a labelled secret stops at CJK text and full-width punctuation', () => {
  assert.deepEqual(types('token=sk-live-9f8e7d6c5b4a3210zyxw，来自 203.0.113.7'), ['SECRET:sk-live-9f8e7d6c5b4a3210zyxw', 'IP:203.0.113.7'])
  assert.deepEqual(types('password: Abc12345，记得改'), ['SECRET:Abc12345'])
})
