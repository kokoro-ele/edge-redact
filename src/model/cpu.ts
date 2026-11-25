/**
 * CPU reference implementation of the character tagger (training/py/model.py), zero dependencies.
 *
 * Pipeline: UTF-16 code units → 6 hashed n-gram features per unit → summed embeddings → linear →
 * 8 dilated residual conv blocks (LayerNorm → conv k=3 → GELU) → linear → softmax over BIOES tags →
 * decode (tier thresholds + Latin/digit token snapping) → spans.
 *
 * Must match the Python code exactly: hashing is uint32 arithmetic (Math.imul + >>> 0), decoding
 * follows `decode()` line by line. Float math is float32 storage with float64 accumulation, so
 * logits agree with PyTorch to ~1e-5.
 */

import type { EntityType, Risk } from '../types.ts'

export interface ModelHeader {
  version: number
  name: string
  /** sep: depthwise-separable blocks (depthwise conv k=3, then pointwise H×H linear) */
  config: { buckets: number, emb: number, hidden: number, dilations: number[], sep?: boolean }
  thresholds: Record<Risk, number>
  types: EntityType[]
  tags: string[]
  tensors: Record<string, { shape: number[], dtype: 'f32' | 'i8' | 'i4', offset: number, scale?: number }>
}

export interface Model {
  header: ModelHeader
  /** dequantized float32 weights by tensor name */
  w: Record<string, Float32Array>
}

export interface Span { start: number, end: number, type: EntityType, score: number }

export class ModelFormatError extends Error {}

const MAGIC = 0x4D445245 // "ERDM" little endian

/** Parse an .erdm file. Throws ModelFormatError on anything malformed (never returns a partial model). */
export function loadModel(buf: ArrayBuffer | Uint8Array): Model {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf)
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  if (bytes.byteLength < 8 || dv.getUint32(0, true) !== MAGIC)
    throw new ModelFormatError('not an ERDM model file')
  const hlen = dv.getUint32(4, true)
  if (8 + hlen > bytes.byteLength)
    throw new ModelFormatError('truncated header')
  let header: ModelHeader
  try {
    header = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(8, 8 + hlen)))
  }
  catch {
    throw new ModelFormatError('bad header JSON')
  }
  if (header.version !== 1)
    throw new ModelFormatError(`unsupported model version ${header.version}`)
  const base = 8 + hlen + ((16 - ((8 + hlen) % 16)) % 16)
  const { buckets, emb, hidden, dilations } = header.config
  const nTags = header.tags.length
  const expect: Record<string, number[]> = {
    'emb.weight': [buckets, emb],
    'proj.weight': [hidden, emb],
    'proj.bias': [hidden],
    'out.weight': [nTags, hidden],
    'out.bias': [nTags],
  }
  dilations.forEach((_, i) => {
    expect[`convs.${i}.weight`] = [hidden, header.config.sep ? 1 : hidden, 3]
    expect[`convs.${i}.bias`] = [hidden]
    if (header.config.sep) {
      expect[`pws.${i}.weight`] = [hidden, hidden]
      expect[`pws.${i}.bias`] = [hidden]
    }
    expect[`norms.${i}.weight`] = [hidden]
    expect[`norms.${i}.bias`] = [hidden]
  })
  const w: Record<string, Float32Array> = {}
  for (const [name, shape] of Object.entries(expect)) {
    const t = header.tensors[name]
    if (!t || t.shape.length !== shape.length || t.shape.some((d, i) => d !== shape[i]))
      throw new ModelFormatError(`tensor ${name}: missing or wrong shape`)
    const n = shape.reduce((a, b) => a * b, 1)
    const out = new Float32Array(n)
    const at = base + t.offset
    if (t.dtype === 'f32') {
      if (at + 4 * n > bytes.byteLength)
        throw new ModelFormatError(`tensor ${name}: out of bounds`)
      for (let i = 0; i < n; i++)
        out[i] = dv.getFloat32(at + 4 * i, true)
    }
    else if (t.dtype === 'i8') {
      const rows = shape[0]!
      const per = n / rows
      const sat = base + (t.scale ?? -1)
      if (t.scale === undefined || at + n > bytes.byteLength || sat + 4 * rows > bytes.byteLength)
        throw new ModelFormatError(`tensor ${name}: out of bounds`)
      for (let r = 0; r < rows; r++) {
        const s = dv.getFloat32(sat + 4 * r, true)
        for (let j = 0; j < per; j++)
          out[r * per + j] = dv.getInt8(at + r * per + j) * s
      }
    }
    else if (t.dtype === 'i4') {
      // two's-complement nibbles, low nibble first, per-row scales
      const rows = shape[0]!
      const per = n / rows
      const sat = base + (t.scale ?? -1)
      if (t.scale === undefined || at + Math.ceil(n / 2) > bytes.byteLength || sat + 4 * rows > bytes.byteLength)
        throw new ModelFormatError(`tensor ${name}: out of bounds`)
      for (let r = 0; r < rows; r++) {
        const s = dv.getFloat32(sat + 4 * r, true)
        for (let j = 0; j < per; j++) {
          const idx = r * per + j
          const byte = bytes[at + (idx >> 1)]!
          const nib = idx & 1 ? byte >> 4 : byte & 0xF
          out[idx] = (nib >= 8 ? nib - 16 : nib) * s
        }
      }
    }
    else {
      throw new ModelFormatError(`tensor ${name}: unknown dtype`)
    }
    for (let i = 0; i < n; i++) {
      if (!Number.isFinite(out[i]!))
        throw new ModelFormatError(`tensor ${name}: non-finite weight`)
    }
    w[name] = out
  }
  return { header, w }
}

// ---- features (training/py/model.py: fmix, comb, char_class, features) ----

const M = 0x9E3779B1
const SALTS = [0x1B873593, 0xCC9E2D51, 0x85EBCA6B, 0xC2B2AE35, 0x27D4EB2F, 0x165667B1]
export const N_FEATURES = 6

function fmix(x: number): number {
  x ^= x >>> 16
  x = Math.imul(x, 0x85EBCA6B)
  x ^= x >>> 13
  x = Math.imul(x, 0xC2B2AE35)
  x ^= x >>> 16
  return x >>> 0
}

function comb(h: number, v: number): number {
  return fmix(Math.imul((h ^ v) >>> 0, M))
}

export function charClass(u: number): number {
  if (u === 0)
    return 0
  if (u === 32 || u === 9 || u === 10 || u === 13 || u === 0x3000)
    return 1
  if (u >= 48 && u <= 57)
    return 2
  if (u >= 65 && u <= 90)
    return 3
  if ((u >= 97 && u <= 122) || (u >= 0xC0 && u <= 0x24F))
    return 4
  if ((u >= 0x4E00 && u <= 0x9FFF) || (u >= 0x3400 && u <= 0x4DBF))
    return 5
  if ((u >= 0x3040 && u <= 0x30FF) || (u >= 0xAC00 && u <= 0xD7AF))
    return 6
  return 7
}

/** uint32 feature hashes, row-major (n × N_FEATURES). */
export function features(text: string): Uint32Array {
  const n = text.length
  const p = new Uint32Array(n + 4)
  for (let i = 0; i < n; i++)
    p[i + 2] = text.charCodeAt(i)
  const fold = (u: number) => (u >= 48 && u <= 57 ? 48 : u)
  const low = (u: number) => (u >= 65 && u <= 90 ? u + 32 : u)
  const cls = new Uint32Array(n + 4)
  for (let i = 0; i < n + 4; i++)
    cls[i] = charClass(p[i]!)
  const out = new Uint32Array(n * N_FEATURES)
  for (let i = 0; i < n; i++) {
    const c = i + 2
    const u = p[c]!
    const l1 = p[c - 1]!
    const r1 = p[c + 1]!
    const o = i * N_FEATURES
    out[o] = comb(SALTS[0]!, u)
    out[o + 1] = comb(comb(SALTS[1]!, fold(l1)), fold(u))
    out[o + 2] = comb(comb(SALTS[2]!, fold(u)), fold(r1))
    out[o + 3] = comb(comb(comb(SALTS[3]!, fold(l1)), fold(u)), fold(r1))
    const shape = cls[c - 2]! * 4096 + cls[c - 1]! * 512 + cls[c]! * 64 + cls[c + 1]! * 8 + cls[c + 2]!
    out[o + 4] = comb(SALTS[4]!, shape)
    out[o + 5] = comb(comb(SALTS[5]!, low(u)), cls[c - 1]! * 8 + cls[c + 1]!)
  }
  return out
}

// ---- network ----

/** erf with |error| < 1.2e-7 (Numerical Recipes erfc, Chebyshev fit). */
function erf(x: number): number {
  const z = Math.abs(x)
  const t = 1 / (1 + 0.5 * z)
  const r = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418
    + t * (-0.18628806 + t * (0.27886807 + t * (-1.13520398 + t * (1.48851587
      + t * (-0.82215223 + t * 0.17087277)))))))))
  return x >= 0 ? 1 - r : r - 1
}

const gelu = (x: number) => 0.5 * x * (1 + erf(x * Math.SQRT1_2))

const transposed = new WeakMap<Model, Float32Array[]>()

/** Conv weights re-laid out as [k][out][in] (PyTorch stores [out][in][k]); cached per model. */
function convKOI(m: Model, l: number): Float32Array {
  let all = transposed.get(m)
  if (!all) {
    const H = m.header.config.hidden
    all = m.header.config.dilations.map((_, li) => {
      const src = m.w[`convs.${li}.weight`]!
      const dst = new Float32Array(src.length)
      for (let o = 0; o < H; o++) {
        for (let i = 0; i < H; i++) {
          for (let k = 0; k < 3; k++)
            dst[(k * H + o) * H + i] = src[(o * H + i) * 3 + k]!
        }
      }
      return dst
    })
    transposed.set(m, all)
  }
  return all[l]!
}

/** x += gelu(pointwise(depthwise(y))) for one depthwise-separable block. */
function separableBlock(m: Model, l: number, d: number, x: Float32Array, y: Float32Array, T: number): void {
  const H = m.header.config.hidden
  const dw = m.w[`convs.${l}.weight`]! // [H][1][3]
  const db = m.w[`convs.${l}.bias`]!
  const pw = m.w[`pws.${l}.weight`]! // [out][in]
  const pb = m.w[`pws.${l}.bias`]!
  // depthwise for all positions first, then the pointwise matmul 4 positions at a time so each
  // weight load feeds 4 multiply-adds
  const h = new Float32Array((T + 3) * H)
  for (let t = 0; t < T; t++) {
    const prev = t - d >= 0 ? (t - d) * H : -1
    const cur = t * H
    const next = t + d < T ? (t + d) * H : -1
    for (let c = 0; c < H; c++) {
      let v = db[c]! + dw[c * 3 + 1]! * y[cur + c]!
      if (prev >= 0)
        v += dw[c * 3]! * y[prev + c]!
      if (next >= 0)
        v += dw[c * 3 + 2]! * y[next + c]!
      h[cur + c] = v
    }
  }
  for (let t = 0; t < T; t += 4) {
    const r0 = t * H
    const r1 = r0 + H
    const r2 = r1 + H
    const r3 = r2 + H
    for (let o = 0; o < H; o++) {
      const wr = o * H
      let s0 = pb[o]!
      let s1 = s0
      let s2 = s0
      let s3 = s0
      for (let i = 0; i < H; i++) {
        const w = pw[wr + i]!
        s0 += w * h[r0 + i]!
        s1 += w * h[r1 + i]!
        s2 += w * h[r2 + i]!
        s3 += w * h[r3 + i]!
      }
      x[r0 + o] = x[r0 + o]! + gelu(s0)
      if (t + 1 < T)
        x[r1 + o] = x[r1 + o]! + gelu(s1)
      if (t + 2 < T)
        x[r2 + o] = x[r2 + o]! + gelu(s2)
      if (t + 3 < T)
        x[r3 + o] = x[r3 + o]! + gelu(s3)
    }
  }
}

const CHUNK = 2048
const OVERLAP = 64

/** Logits (n × nTags, row-major) for the code units [lo, hi) of `feats`. */
function forward(m: Model, feats: Uint32Array, lo: number, hi: number): Float32Array {
  const { buckets, emb, hidden: H, dilations } = m.header.config
  const nTags = m.header.tags.length
  const T = hi - lo
  const E = m.w['emb.weight']!
  const e = new Float64Array(emb)
  const x = new Float32Array(T * H)
  const pw = m.w['proj.weight']!
  const pb = m.w['proj.bias']!
  for (let t = 0; t < T; t++) {
    e.fill(0)
    for (let f = 0; f < N_FEATURES; f++) {
      const row = (feats[(lo + t) * N_FEATURES + f]! % buckets) * emb
      for (let j = 0; j < emb; j++)
        e[j] = e[j]! + E[row + j]!
    }
    for (let o = 0; o < H; o++) {
      let s = pb[o]!
      const wr = o * emb
      for (let j = 0; j < emb; j++)
        s += pw[wr + j]! * e[j]!
      x[t * H + o] = s
    }
  }
  const y = new Float32Array(T * H)
  for (let l = 0; l < dilations.length; l++) {
    const d = dilations[l]!
    const g = m.w[`norms.${l}.weight`]!
    const b = m.w[`norms.${l}.bias`]!
    for (let t = 0; t < T; t++) {
      let mean = 0
      for (let i = 0; i < H; i++)
        mean += x[t * H + i]!
      mean /= H
      let v = 0
      for (let i = 0; i < H; i++) {
        const z = x[t * H + i]! - mean
        v += z * z
      }
      const inv = 1 / Math.sqrt(v / H + 1e-5)
      for (let i = 0; i < H; i++)
        y[t * H + i] = (x[t * H + i]! - mean) * inv * g[i]! + b[i]!
    }
    if (m.header.config.sep) {
      separableBlock(m, l, d, x, y, T)
      continue
    }
    const cw = convKOI(m, l) // [k][out][in], contiguous over `in`
    const cb = m.w[`convs.${l}.bias`]!
    const acc = new Float32Array(H)
    for (let t = 0; t < T; t++) {
      acc.set(cb)
      for (let k = 0; k < 3; k++) {
        const tt = t + (k - 1) * d
        if (tt < 0 || tt >= T)
          continue
        const yr = tt * H
        for (let o = 0; o < H; o++) {
          const wr = (k * H + o) * H
          let s0 = 0
          let s1 = 0
          let s2 = 0
          let s3 = 0
          let i = 0
          for (; i + 3 < H; i += 4) {
            s0 += cw[wr + i]! * y[yr + i]!
            s1 += cw[wr + i + 1]! * y[yr + i + 1]!
            s2 += cw[wr + i + 2]! * y[yr + i + 2]!
            s3 += cw[wr + i + 3]! * y[yr + i + 3]!
          }
          for (; i < H; i++)
            s0 += cw[wr + i]! * y[yr + i]!
          acc[o] = acc[o]! + (s0 + s1) + (s2 + s3)
        }
      }
      for (let o = 0; o < H; o++)
        x[t * H + o] = x[t * H + o]! + gelu(acc[o]!)
    }
  }
  const ow = m.w['out.weight']!
  const ob = m.w['out.bias']!
  const logits = new Float32Array(T * nTags)
  for (let t = 0; t < T; t++) {
    for (let c = 0; c < nTags; c++) {
      let s = ob[c]!
      for (let i = 0; i < H; i++)
        s += ow[c * H + i]! * x[t * H + i]!
      logits[t * nTags + c] = s
    }
  }
  return logits
}

/** Logits for every code unit of `text`, computed in overlapping chunks like training/py/predict.py. */
export function logits(m: Model, text: string): Float32Array {
  const n = text.length
  const nTags = m.header.tags.length
  const feats = features(text)
  const out = new Float32Array(n * nTags)
  for (let s = 0; s < n; s += CHUNK) {
    const lo = Math.max(0, s - OVERLAP)
    const hi = Math.min(n, s + CHUNK + OVERLAP)
    const part = forward(m, feats, lo, hi)
    const take = Math.min(CHUNK, n - s)
    out.set(part.subarray((s - lo) * nTags, (s - lo + take) * nTags), s * nTags)
  }
  return out
}

function softmaxRows(lg: Float32Array, nTags: number): Float64Array {
  const p = new Float64Array(lg.length)
  for (let r = 0; r < lg.length; r += nTags) {
    let mx = -Infinity
    for (let c = 0; c < nTags; c++)
      mx = Math.max(mx, lg[r + c]!)
    let z = 0
    for (let c = 0; c < nTags; c++) {
      const v = Math.exp(lg[r + c]! - mx)
      p[r + c] = v
      z += v
    }
    for (let c = 0; c < nTags; c++)
      p[r + c]! /= z
  }
  return p
}

const RISK_OF: Record<string, Risk> = {
  CN_ID: 'high', CREDIT_CARD: 'high', BANK_ACCOUNT: 'high', SECRET: 'high',
  PERSON: 'medium', ADDRESS: 'medium', PHONE: 'medium', EMAIL: 'medium', IP: 'medium', OTHER_ID: 'medium', NATIONAL_ID: 'medium',
  ORG: 'low', PROJECT: 'low',
}

/** training/py/model.py `decode()`, including Latin/digit token snapping. */
export function decode(text: string, probs: Float64Array, types: EntityType[], thresholds: Record<Risk, number>): Span[] {
  const n = text.length
  const K = types.length
  const nTags = 1 + 4 * K
  const pEnt = new Float64Array(n)
  const typ = new Int32Array(n)
  const pos = new Int32Array(n)
  const inside = new Uint8Array(n)
  for (let i = 0; i < n; i++) {
    const r = i * nTags
    pEnt[i] = 1 - probs[r]!
    let best = -1
    let bt = 0
    for (let k = 0; k < K; k++) {
      const s = probs[r + 1 + 4 * k]! + probs[r + 2 + 4 * k]! + probs[r + 3 + 4 * k]! + probs[r + 4 + 4 * k]!
      if (s > best) {
        best = s
        bt = k
      }
    }
    typ[i] = bt
    let bp = 0
    for (let q = 1; q < 4; q++) {
      if (probs[r + 1 + 4 * bt + q]! > probs[r + 1 + 4 * bt + bp]!)
        bp = q
    }
    pos[i] = bp
    inside[i] = pEnt[i]! >= thresholds[RISK_OF[types[bt]!]!] ? 1 : 0
  }
  // token snapping
  let i = 0
  while (i < n) {
    const c = charClass(text.charCodeAt(i))
    if (c < 2 || c > 4) {
      i++
      continue
    }
    let j = i
    while (j < n) {
      const cj = charClass(text.charCodeAt(j))
      if (cj < 2 || cj > 4)
        break
      j++
    }
    let k = 0
    for (let q = i; q < j; q++)
      k += inside[q]!
    if (k > 0 && k < (j - i) / 2) {
      inside.fill(0, i, j)
    }
    else if (k > 0) {
      const count = new Int32Array(K)
      for (let q = i; q < j; q++) {
        if (inside[q])
          count[typ[q]!]!++
      }
      let t = 0
      for (let q = 1; q < K; q++) {
        if (count[q]! > count[t]!)
          t = q
      }
      inside.fill(1, i, j)
      typ.fill(t, i, j)
      pos.fill(1, i + 1, j)
      if (pos[i] === 3)
        pos[i] = 0
      else if (pos[i] === 2)
        pos[i] = 1
    }
    i = j
  }
  const spans: Span[] = []
  i = 0
  while (i < n) {
    if (!inside[i]) {
      i++
      continue
    }
    let j = i + 1
    while (j < n && inside[j] && typ[j] === typ[i] && pos[j] !== 0 && pos[j] !== 3 && pos[j - 1] !== 2 && pos[j - 1] !== 3)
      j++
    let s = 0
    for (let q = i; q < j; q++)
      s += pEnt[q]!
    spans.push({ start: i, end: j, type: types[typ[i]!]!, score: s / (j - i) })
    i = j
  }
  return spans
}

/** Model spans for `text`. */
export function predict(m: Model, text: string, thresholds: Record<Risk, number> = m.header.thresholds): Span[] {
  if (text.length === 0)
    return []
  checkModel(m)
  const nTags = m.header.tags.length
  const lg = logits(m, text)
  // NaN compares false against every threshold, which would silently mean "no PII found"
  for (let i = 0; i < lg.length; i++) {
    if (!Number.isFinite(lg[i]!))
      throw new ModelFormatError('model produced a non-finite logit')
  }
  return decode(text, softmaxRows(lg, nTags), m.header.types, thresholds)
}

/** Weight sizes must match the header (a Model object can be built or mutated outside loadModel). */
function checkModel(m: Model): void {
  const { buckets, emb, hidden: H, dilations, sep } = m.header.config
  const nTags = m.header.tags.length
  if (nTags !== 1 + 4 * m.header.types.length)
    throw new ModelFormatError('tags do not match types')
  const need: [string, number][] = [['emb.weight', buckets * emb], ['proj.weight', H * emb], ['proj.bias', H], ['out.weight', nTags * H], ['out.bias', nTags]]
  dilations.forEach((_, l) => {
    need.push([`convs.${l}.weight`, H * (sep ? 1 : H) * 3], [`convs.${l}.bias`, H], [`norms.${l}.weight`, H], [`norms.${l}.bias`, H])
    if (sep)
      need.push([`pws.${l}.weight`, H * H], [`pws.${l}.bias`, H])
  })
  for (const [k, n] of need) {
    if (m.w[k]?.length !== n)
      throw new ModelFormatError(`tensor ${k}: expected ${n} values`)
  }
}
