/**
 * What a finished run was actually replayed with, in the words a HUMAN reads.
 *
 * 🔴 ONE implementation, two surfaces. The single-run page's parameters rail and the stack
 * page's Settings card answer the SAME question — *what settings produced this book?* — and
 * they answered it in two different vocabularies: the rail in plain English since 2026-08-20,
 * the stack card in raw field names for its whole life (`exec_bleg`, `be_arm_frac`,
 * `div_veto`). Aaron, 2026-09-06: *"these settings show the actual code variable names. So
 * when I look at them, I don't know what's on or what's off."* A second copy of the words is
 * how one surface starts teaching a different name for the same setting, so the classification
 * lives here and each page owns only its LAYOUT.
 *
 * ⚠ Nothing here DROPS a param. A run report that silently omits an input is a worse defect
 * than a long list — the folds below (`settled`, `foundational`) move a row, never delete it,
 * and every caller must render all three buckets.
 */
import {
  fillTokens,
  isOutOfPlay,
  isSettled,
  prettyName,
  shortLabelOf,
  valueLabel,
  type ParamValue,
} from '@/components/ParamEditor'
import type { ParamSchemaEntry } from '@/types'

/** One setting as it was sent: the field name it is keyed by, and the value it carried. */
export type SettingRow = [string, unknown]

export interface RunSettingsView {
  /** The live settings, in the strategy metadata's OWN group order — the order the setups are
   *  actually decided in. Re-sorting alphabetically scrambles that back into a hunt. */
  groups: Array<{ group: string; rows: SettingRow[] }>
  /** Folded away, never dropped: a parent switch is off, or testing settled the question. */
  settled: SettingRow[]
  /** The contract and the fills — symbol, tick size, point value, account profile. */
  foundational: SettingRow[]
  /** How many live settings differ from the baseline passed in (0 when none was). */
  changedCount: number
  changed(name: string, value: unknown): boolean
  /** The words for a setting. Falls back to a tidied field name when no schema entry exists. */
  nameOf(name: string): string
  /** The value in the editor's own words — a bool as its two option labels, a number with its
   *  unit. `String(v)` gives `true`/`false`, which says nothing about which way is ON. */
  valueOf(name: string, value: unknown): string
  /** The one-line explanation, for a hover. Empty when the strategy carries no metadata. */
  descOf(name: string): string
  /** Total settings the run carried, across all three buckets. */
  total: number
}

/**
 * Classify one run's params against its strategy's schema.
 *
 * `schema` missing (a strategy scanned before its metadata existed, or a leg whose strategy row
 * has not loaded yet) degrades to tidied field names and raw values — readable, never blank.
 * `baselineParams` is optional and only drives the "changed" marks a tuning comparison needs.
 */
export function buildRunSettingsView(
  params: Record<string, unknown> | undefined | null,
  schema: ParamSchemaEntry[] | undefined | null,
  baselineParams?: Record<string, unknown> | null
): RunSettingsView {
  const values = (params ?? {}) as Record<string, ParamValue>
  // Option labels carry `{other_param}` tokens, so they are filled ONCE against this run's own
  // values before anything is read off them — otherwise a toggle reads `{exec_sl_level}` on one
  // surface while the editor two clicks away reads `0.886`.
  const filled = fillTokens(schema ?? [], values)
  const byName = new Map(filled.map((s) => [s.name, s]))

  const nameOf = (k: string) => {
    const p = byName.get(k)
    return p ? shortLabelOf(p) : prettyName(k)
  }
  const valueOf = (k: string, v: unknown) => valueLabel(byName.get(k), v)
  const descOf = (k: string) => byName.get(k)?.desc || byName.get(k)?.description || ''
  // An unmapped param lands in "Other" rather than vanishing — the record must stay complete.
  const groupOf = (k: string) => byName.get(k)?.group || 'Other'
  const isFoundational = (k: string) => byName.get(k)?.category === 'foundational'
  const changed = (k: string, v: unknown) =>
    baselineParams != null && String(v) !== String(baselineParams[k])

  // Both folds carry the same escape: a value moved off the tune BASELINE stays in the main
  // list, or the "N changed" count names a row the reader cannot find.
  const settledKey = (k: string, v: unknown) => {
    const p = byName.get(k)
    if (!p || !isSettled(p, v as ParamValue)) return false
    return !changed(k, v)
  }
  // 🔴 A SETTING WHOSE PARENT IS OFF DID NOTHING ON THIS RUN, so it does not belong in the list
  // you read to see what the run did. Asked of `isOutOfPlay`, imported rather than re-written,
  // so no surface can disagree with the editor about which cascade is live.
  const outOfPlayKey = (k: string, v: unknown) => {
    const p = byName.get(k)
    if (!p || !isOutOfPlay(p, filled, values)) return false
    return !changed(k, v)
  }
  const folded = (k: string, v: unknown) => settledKey(k, v) || outOfPlayKey(k, v)

  const entries = Object.entries(params ?? {})
  const live = entries.filter(([k, v]) => !isFoundational(k) && !folded(k, v))
  const settled = entries.filter(([k, v]) => !isFoundational(k) && folded(k, v))
  const foundational = entries.filter(([k]) => isFoundational(k))

  // A Map preserves insertion order, and the entries arrive in the schema's order.
  const order = new Map<string, SettingRow[]>()
  for (const [k, v] of live) {
    const g = groupOf(k)
    if (!order.has(g)) order.set(g, [])
    order.get(g)!.push([k, v])
  }

  return {
    groups: [...order.entries()].map(([group, rows]) => ({ group, rows })),
    settled,
    foundational,
    changedCount: live.filter(([k, v]) => changed(k, v)).length,
    changed,
    nameOf,
    valueOf,
    descOf,
    total: entries.length,
  }
}

/** The caption under each fold. Shared so the two surfaces cannot explain the same fold
 *  differently — a reader who learns what "Already decided" means on one page has learned it. */
export const SETTLED_CAPTION =
  'Nothing to decide here — a parent setting is off, or testing settled it. All still sent with the run.'
export const FOUNDATIONAL_CAPTION = 'What was traded and how it filled, not how it decided.'
export const SETTLED_HEADING = 'Already decided'
export const FOUNDATIONAL_HEADING = 'Instrument & broker'
