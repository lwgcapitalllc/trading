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

export function fmtCountdown(deltaMs: number): string {
  const s = Math.max(0, Math.floor(deltaMs / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m ${s % 60}s`
  return `${s}s`
}
