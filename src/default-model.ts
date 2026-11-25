/**
 * The bundled model, loaded on first use and cached.
 *
 * The weights ship next to the code (`models/` in the package) and are found with
 * `new URL(..., import.meta.url)`, which bundlers such as Vite and webpack turn into an asset URL.
 * In Node the file is read from disk; in the browser it is fetched.
 *
 * A failed load is not cached, so the next call tries again, and it always throws: there is no
 * fallback to rules only (fail closed).
 */

import type { Model } from './model/cpu.ts'
import { loadModel } from './model/cpu.ts'
import { RedactError } from './redact.ts'

export const DEFAULT_MODEL_URL: URL = new URL('../models/zh-en-ds48-int4.erdm', import.meta.url)

let cached: Promise<Model> | undefined

async function readBytes(url: URL): Promise<ArrayBuffer | Uint8Array> {
  if (url.protocol === 'file:') {
    // kept out of static analysis so browser bundles never pull in a Node built-in
    const mod = 'node:fs/promises'
    const fs = await import(/* @vite-ignore */ /* webpackIgnore: true */ mod) as { readFile: (u: URL) => Promise<Uint8Array> }
    return fs.readFile(url)
  }
  const r = await fetch(url)
  if (!r.ok)
    throw new Error(`HTTP ${r.status}`)
  return r.arrayBuffer()
}

/**
 * Load a model file. Without an argument, loads the bundled model once and reuses it.
 * Pass a URL (or path-like URL string) to load weights from somewhere else, e.g. your own CDN.
 */
export function loadDefaultModel(url?: string | URL): Promise<Model> {
  if (url !== undefined)
    return load(new URL(url, (globalThis as { location?: { href: string } }).location?.href ?? DEFAULT_MODEL_URL))
  cached ??= load(DEFAULT_MODEL_URL).catch((e) => {
    cached = undefined
    throw e
  })
  return cached
}

async function load(url: URL): Promise<Model> {
  try {
    return loadModel(await readBytes(url))
  }
  catch (e) {
    throw new RedactError(`could not load model from ${url.href}: ${(e as Error)?.message ?? e}`, { cause: e })
  }
}
