/**
 * Public detection / redaction API.
 *
 * Order (PLAN.md): rules + checksums first, then heuristics; the model only fills gaps (it can add a
 * span where nothing was found, never retype or shrink a rule hit). Tiers: high is redacted, medium is
 * redacted by default too (the UI shows it for confirmation), low is reported but left in place.
 *
 * Fail closed: any error inside detection is thrown as RedactError. There is no code path that
 * returns the original text, or a partly redacted text, after something went wrong.
 */

import type { Model } from './model/cpu.ts'
import type { Entity, Risk } from './types.ts'
import { loadDefaultModel } from './default-model.ts'
import { detectHeuristic } from './heuristics/index.ts'
import { predict } from './model/cpu.ts'
import { fillGaps, tidySpans } from './rules/index.ts'
import { RISK } from './types.ts'

/** Longest input accepted, in UTF-16 code units (~1 MB of text). Longer input throws. */
export const MAX_INPUT = 1_000_000

export class RedactError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options)
    this.name = 'RedactError'
  }
}

export interface DetectOptions {
  /**
   * Async `detect` / `redact`: omit to use the bundled model (loaded once, cached); pass a Model from
   * loadModel() to use your own; pass `false` to run rules and heuristics only.
   * Sync `detectSync` / `redactSync`: pass a Model, or nothing (or `false`) for rules and heuristics only.
   */
  model?: Model | false
}

export interface RedactOptions extends DetectOptions {
  /** tiers to replace; default high + medium */
  tiers?: Risk[]
  /** per-entity override (e.g. the user un-ticked one); takes precedence over `tiers` */
  select?: (e: Entity) => boolean
  /** reuse entities from an earlier detect() on the same text instead of detecting again */
  entities?: Entity[]
}

export interface RedactResult {
  /** text with placeholders such as [PERSON_1] */
  text: string
  /** everything found, including tiers that were not replaced */
  entities: Entity[]
  /** placeholder → original value, for restoring a reply locally */
  mapping: Record<string, string>
}

function guarded<T>(what: string, fn: () => T): T {
  try {
    return fn()
  }
  catch (e) {
    throw e instanceof RedactError ? e : new RedactError(`${what} failed: ${(e as Error)?.message ?? e}`, { cause: e })
  }
}

/** Synchronous detection. Without `model` only rules and heuristics run. */
export function detectSync(text: string, opts: DetectOptions = {}): Entity[] {
  return guarded('detection', () => {
    if (typeof text !== 'string')
      throw new RedactError('input must be a string')
    if (text.length > MAX_INPUT)
      throw new RedactError(`input too long: ${text.length} > ${MAX_INPUT} UTF-16 units`)
    const base = detectHeuristic(text)
    if (!opts.model)
      return tidySpans(text, base)
    const fromModel: Entity[] = predict(opts.model, text).map(s => ({ ...s, risk: RISK[s.type], source: 'model' }))
    const out = tidySpans(text, fillGaps(base, fromModel))
    for (const e of out) {
      if (!(e.start >= 0 && e.end <= text.length && e.start < e.end))
        throw new RedactError(`invalid span ${e.start}-${e.end}`)
    }
    return out
  })
}

/** Synchronous redaction. Without `model` (or `entities`) only rules and heuristics run. */
export function redactSync(text: string, opts: RedactOptions = {}): RedactResult {
  const entities = opts.entities ?? detectSync(text, opts)
  return guarded('redaction', () => {
    if (typeof text !== 'string')
      throw new RedactError('input must be a string')
    const tiers = new Set(opts.tiers ?? ['high', 'medium'])
    const mapping: Record<string, string> = {}
    const byValue = new Map<string, string>()
    const counters: Record<string, number> = {}
    let out = ''
    let pos = 0
    for (const e of entities) {
      if (!(e.start >= 0 && e.end <= text.length && e.start < e.end && e.start >= pos))
        throw new RedactError(`invalid or overlapping span ${e.start}-${e.end}`)
      if (!(opts.select ? opts.select(e) : tiers.has(e.risk)))
        continue
      const value = text.slice(e.start, e.end)
      const key = `${e.type}\0${value}`
      let ph = byValue.get(key)
      if (!ph) {
        counters[e.type] = (counters[e.type] ?? 0) + 1
        ph = `[${e.type}_${counters[e.type]}]`
        byValue.set(key, ph)
        mapping[ph] = value
      }
      out += text.slice(pos, e.start) + ph
      pos = e.end
    }
    return { text: out + text.slice(pos), entities, mapping }
  })
}

async function withModel<T extends DetectOptions>(opts: T): Promise<T> {
  return opts.model === undefined ? { ...opts, model: await loadDefaultModel() } : opts
}

/** Find PII. Loads the bundled model on first call unless `model` is given (or `false`). */
export async function detect(text: string, opts: DetectOptions = {}): Promise<Entity[]> {
  return detectSync(text, await withModel(opts))
}

/** Replace PII with placeholders. Loads the bundled model on first call unless `model` or `entities` is given. */
export async function redact(text: string, opts: RedactOptions = {}): Promise<RedactResult> {
  return redactSync(text, opts.entities ? opts : await withModel(opts))
}

/** Put original values back into a reply that contains placeholders. */
export function restore(text: string, mapping: Record<string, string>): string {
  return text.replace(/\[[A-Z_]+_\d+\]/g, ph => mapping[ph] ?? ph)
}
