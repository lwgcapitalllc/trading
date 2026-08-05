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

export const fmtTime = (ms: number) =>
  new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

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

export function fmtCountdown(deltaMs: number): string {
  const s = Math.max(0, Math.floor(deltaMs / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s % 60}s`
  return `${s}s`
}
