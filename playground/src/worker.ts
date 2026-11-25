/// <reference lib="webworker" />
/**
 * Detection runs here so a long paste never blocks the page. The model is fetched once; if it cannot be
 * loaded every request fails (fail closed: no silent fallback to rules only).
 */
import type { Entity, Model } from '../../src/index.ts'
import { detectSync, loadModel } from '../../src/index.ts'

export type Req = { id: number, text: string }
export type Res =
  | { type: 'ready', bytes: number, ms: number }
  | { type: 'fatal', message: string }
  | { type: 'result', id: number, entities: Entity[], ms: number }
  | { type: 'error', id: number, message: string }

const post = (m: Res) => postMessage(m)
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))

let model: Model | undefined
const ready = (async () => {
  const t0 = performance.now()
  const r = await fetch(new URL('/model.erdm', location.origin))
  if (!r.ok)
    throw new Error(`model download failed: HTTP ${r.status}`)
  const buf = await r.arrayBuffer()
  model = loadModel(buf)
  post({ type: 'ready', bytes: buf.byteLength, ms: performance.now() - t0 })
})()
ready.catch(e => post({ type: 'fatal', message: msg(e) }))

onmessage = async (ev: MessageEvent<Req>) => {
  const { id, text } = ev.data
  try {
    await ready
    const t0 = performance.now()
    const entities = detectSync(text, { model })
    post({ type: 'result', id, entities, ms: performance.now() - t0 })
  }
  catch (e) {
    post({ type: 'error', id, message: msg(e) })
  }
}
