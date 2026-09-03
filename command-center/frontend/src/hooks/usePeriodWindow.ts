import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { EquityPoint } from '@/types'
import { cutPeriod, dateOf } from '@/components/periodWindow'

export { cutPeriod, dateOf }

// ── A PERIOD of a finished book, read as if it were the whole book ────────────────────────────
//
// The URL state and the bounds. The arithmetic — the filter and the REBASE — lives in
// `components/periodWindow.ts`, which owns those rules; do not restate them here.
//
// Aaron, 2026-08-16, asked for this on a single backtest: *"just have a filter on the backtest
// details page where I could look at trades within a specific period… and once I select that
// period, then everything on the page adjusts."* On 2026-09-03 he asked why the stack page had
// no such thing.
//
// 🔴 IT IS SHARED BECAUSE THE SECOND PAGE WOULD OTHERWISE COPY THE REBASE, AND A COPIED REBASE IS
// THE WORST KIND. Both pages multiply every dollar they show by the constant this returns. Two
// implementations means two pages that can silently disagree about what a window is worth while
// both look right — the same shape as the rule/evaluator pair that already drifted across the
// python/javascript boundary here. `BacktestDetail` and `StackDetail` share ONE.
export interface PeriodWindow {
  enabled: boolean
  from: string
  to: string
  setRange: (from: string, to: string) => void
  clear: () => void
  minDate: string
  maxDate: string
  spanFrom: string
  spanTo: string
  kept: EquityPoint[]
  scale: number
  openBalance: number | null
  windowBalance: number | null
  totalTrades: number
  set: boolean
  active: boolean
  emptyWindow: boolean
  /** The window rebuilt as a curve a chart can draw, rebased onto the book's own opening deposit. */
  rebasedCurve: EquityPoint[] | null
}

/**
 * `points` must be the book's TRADES in time order. `minDate`/`maxDate` bound the picker and are
 * the book's REQUESTED window — its identity — while `spanFrom`/`spanTo` report the span actually
 * traded, so "the whole book" and "the window I typed" cannot silently become different things.
 */
export function usePeriodWindow(
  points: EquityPoint[],
  minDate: string,
  maxDate: string
): PeriodWindow {
  // Page-level view state lives in the URL, per the frontend's standing rule: a window you picked
  // has to survive a refresh, a Back out of the price chart, and being sent to somebody else. Both
  // writes MERGE — `setSearchParams({from})` alone drops every other param, which is how a tab
  // switch silently clears a filter (already recorded on the Bots page).
  const [searchParams, setSearchParams] = useSearchParams()
  const from = searchParams.get('from') || ''
  const to = searchParams.get('to') || ''

  const setRange = useCallback(
    (nextFrom: string, nextTo: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (nextFrom) next.set('from', nextFrom)
          else next.delete('from')
          if (nextTo) next.set('to', nextTo)
          else next.delete('to')
          return next
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )
  const clear = useCallback(() => setRange('', ''), [setRange])

  // A book whose trades are not all dated cannot be windowed at all — an undated trade would be
  // dropped by every comparison and silently leave the window, which is a wrong number rather than
  // a missing feature. The control disables itself instead.
  const enabled = points.length > 0 && points.every((p) => !!p.date)

  const cut = useMemo(
    () => (enabled ? cutPeriod(points, from, to) : null),
    [enabled, points, from, to]
  )

  return {
    enabled,
    from,
    to,
    setRange,
    clear,
    minDate,
    maxDate,
    // The TRADED span, which is what a preset like "last 12 months" should snap to.
    spanFrom: points.length ? dateOf(points[0]) : '',
    spanTo: points.length ? dateOf(points[points.length - 1]) : '',
    kept: cut?.kept ?? points,
    scale: cut?.scale ?? 1,
    openBalance: cut?.openBalance ?? null,
    // What the account really held entering the window — stated on the pill beside the rebased
    // figure, because "$10,000" on a 2023 window is a restatement and the reader has to be able to
    // tell it from the balance that was actually there.
    windowBalance: cut?.windowBalance ?? null,
    totalTrades: points.length,
    set: !!from || !!to,
    // `active` needs the rebase to have happened: a window covering everything, or one that cannot
    // be rebased, must leave the page identical to the unfiltered book.
    active: cut?.curve != null,
    rebasedCurve: cut?.curve ?? null,
    // Set but produced nothing — a window with no trades in it. A real answer (the strategy stood
    // still), and it must not read as the filter being off.
    emptyWindow: enabled && (!!from || !!to) && (cut?.kept.length ?? 0) === 0,
  }
}
