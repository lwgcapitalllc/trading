// Shared display helpers for the economic-calendar surfaces (the Calendar page + the Overview
// preview). Pure formatting/data only — no business logic, no fetching.
import type { Impact } from '@/types'

// Country flag per currency (regional-indicator emoji). Shown instead of the ISO code.
export const CURRENCY_FLAG: Record<string, string> = {
  USD: '🇺🇸', EUR: '🇪🇺', GBP: '🇬🇧', JPY: '🇯🇵', CAD: '🇨🇦',
  AUD: '🇦🇺', NZD: '🇳🇿', CHF: '🇨🇭', CNY: '🇨🇳',
}
export const flagOf = (currency: string) => CURRENCY_FLAG[currency] ?? currency

export const IMPACT_DOT: Record<Impact, string> = {
  HIGH: 'bg-neg-text',
  MEDIUM: 'bg-warn-text',
  LOW: 'bg-text-tertiary',
  NONE: 'bg-text-tertiary/50',
}
export const IMPACT_LABEL: Record<Impact, string> = {
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low',
  NONE: 'None',
}

// ⚠ Cached `Intl` formatters, not `toLocaleTimeString` per call. Constructing a formatter is the
// expensive half of these APIs, and the Calendar page re-renders every second off the server clock
// with a whole week — ~200 events, measured — on screen. Per-call construction made that ~200 new
// formatters a second for text that changes once a minute.
const _timeFmt = new Intl.DateTimeFormat([], { hour: '2-digit', minute: '2-digit' })
const _dayFmt = new Intl.DateTimeFormat([], { weekday: 'long', month: 'short', day: 'numeric' })
const _rangeFmt = new Intl.DateTimeFormat([], { month: 'short', day: 'numeric' })

export const fmtTime = (ms: number) => _timeFmt.format(ms)

/** "Monday, Aug 10" — a day-group header. */
export const fmtDay = (ms: number) => _dayFmt.format(ms)

/** "Aug 10 – Aug 16" for the week starting at `fromMs` (inclusive of both ends shown). */
export function fmtWeekRange(fromMs: number): string {
  const end = new Date(fromMs)
  end.setDate(end.getDate() + 6)
  return `${_rangeFmt.format(fromMs)} – ${_rangeFmt.format(end)}`
}

/** Local midnight on the Monday of the week `offset` weeks from today.
 *
 * ⚠ ONE definition, used by the Calendar page AND the Overview preview, because the pair
 * `(weekStart, weekEnd)` IS the calendar query's cache key: the two pages agreeing to the
 * millisecond is what makes them share a single 33 KB fetch instead of issuing two. A second
 * private copy would look identical and split the cache the day either one drifted. */
export function localWeekStart(offset = 0): number {
  const d = new Date()
  const mondayIdx = (d.getDay() + 6) % 7 // 0 = Monday
  d.setHours(0, 0, 0, 0)
  d.setDate(d.getDate() - mondayIdx + offset * 7)
  return d.getTime()
}

/** Local midnight on the Monday AFTER the week starting at `fromMs`.
 *
 * ⚠ Date arithmetic, never `fromMs + 7 * 86_400_000`: a week containing a DST changeover is
 * 7 days ± an hour, so the constant lands at 23:00 or 01:00 and the window loses or borrows
 * an hour of events twice a year. */
export function localWeekEnd(fromMs: number): number {
  const d = new Date(fromMs)
  d.setDate(d.getDate() + 7)
  return d.getTime()
}

/** Which day of the week starting at `weekStartMs` a timestamp falls on: 0 = Mon … 6 = Sun.
 *
 * ⚠ ONE definition, shared by the Calendar page and the Overview preview, because the Overview
 * links INTO the page with `?day=<this>` — two private copies is two ways to compute an index one
 * page writes and the other reads.
 *
 * The `round` absorbs DST: a week containing a changeover puts a local midnight 23 or 25 hours from
 * the last one, so the raw quotient lands on 2.958 rather than 3. Returns a value outside 0…6 for a
 * timestamp that is not in that week, and callers must range-check rather than assume. */
export function dayIndexOf(ms: number, weekStartMs: number): number {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  return Math.round((d.getTime() - weekStartMs) / 86_400_000)
}

export function fmtCountdown(deltaMs: number): string {
  const s = Math.max(0, Math.floor(deltaMs / 1000))
  const d = Math.floor(s / 86_400)
  const h = Math.floor((s % 86_400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  // Days, because the week view legitimately counts down to something six days out and `152h 12m`
  // is a number the reader has to divide before it means anything.
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s % 60}s`
  return `${s}s`
}
