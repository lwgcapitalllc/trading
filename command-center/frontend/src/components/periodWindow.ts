import type { EquityPoint } from '@/types'

// ── The PERIOD window, as arithmetic ─────────────────────────────────────────────────────────
//
// No React, no URL, no page. `hooks/usePeriodWindow.ts` wraps this with the URL state and the
// bounds; `BacktestDetail` and `StackDetail` both reach it through that hook.
//
// 🔴 IT IS A SEPARATE MODULE FOR ONE REASON: LOGIC WITH NO SEAM A TEST CAN GRAB IS LOGIC NOBODY
// CHECKS. Left inside the hook this was reachable only from a browser — the exact shape that let
// the trade box draw a wrong adverse band on real trades for as long as it lived inside a chart
// callback. `scripts/check_period_window.mjs` drives it directly and is a step of
// `scripts/run_all_tests.sh`. Keep this file free of VALUE imports, or that check cannot load it.
//
// 🔴 THE REBASE IS EXACT ARITHMETIC, NOT A MODEL, AND THAT IS ONLY TRUE BECAUSE IT IS LINEAR.
// A trade's dollar result is a fixed fraction of the balance it was taken with, so scaling every
// profit in the window by one constant — the book's OPENING balance over the balance the account
// actually held entering the window — reproduces a replay-from-scratch to the cent. MEASURED on
// run `831ec44195ce`: replaying `balance *= 1 + r x (risk_usd / balance_before)` from $10,000 over
// all 167 trades lands at $159,080,061 against a real $159,079,955 — 0.00007% apart, i.e. floating
// point. There is no second definition of the account here and nothing is invented.
//
// ⚠ EVERY RATIO IS THEREFORE UNCHANGED BY THE REBASE — profit factor, win rate, R, Sharpe, max
// drawdown PERCENT. Only the dollar labels move. If a ratio ever differs between a rebased and an
// unrebased window, the scale has stopped being a single constant and something is wrong; do not
// "fix" it by special-casing the ratio.
//
// ⚠ IT IS NOT A RE-RUN, AND THE DIFFERENCE IS REAL. A rerun of 2023→2026 warms its engines up from
// 2023 and sizes from the deposit the whole way; this window carries the full warm-up from the
// book's real start and holds each trade's ACTUAL risk fraction, which drifts. The two agree on
// shape and on R and will not agree trade-for-trade. That is a feature — the window is what the
// strategy really did with a fully warmed engine — but it is not the number a rerun prints.

export const dateOf = (p: EquityPoint) => (p.date ?? '').slice(0, 10)

export interface PeriodCut {
  kept: EquityPoint[]
  /** The window is set AND it actually removes something. A window covering everything is not. */
  narrowed: boolean
  /** `null` when no rebase was possible — the caller must then leave the book untouched. */
  scale: number | null
  curve: EquityPoint[] | null
  openBalance: number | null
  windowBalance: number | null
}

/**
 * `points` must be the book's TRADES in time order, each carrying a date, an equity and a profit.
 *
 * Returns `narrowed: false` when the window is unset or covers everything — the caller then leaves
 * the page reference-identical to the unfiltered book rather than routing it through a rebuild that
 * changes nothing.
 */
export function cutPeriod(points: EquityPoint[], from: string, to: string): PeriodCut {
  const openBalance = points.length ? points[0].equity - (points[0].profit ?? 0) : null
  if (!points.length || (!from && !to))
    return {
      kept: points,
      narrowed: false,
      scale: null,
      curve: null,
      openBalance,
      windowBalance: openBalance,
    }

  const kept = points.filter((p) => {
    const d = dateOf(p)
    if (!d) return false
    if (from && d < from) return false
    if (to && d > to) return false
    return true
  })
  const narrowed = kept.length !== points.length
  const windowBalance = kept.length ? kept[0].equity - (kept[0].profit ?? 0) : null

  // A window whose entering balance is zero or negative cannot be rebased — the scale is undefined,
  // and inventing one would be the "refuse, don't guess" rule broken on the one number every dollar
  // on the page is then multiplied by. Refused, and the pill says so.
  const rebasable =
    narrowed &&
    kept.length > 0 &&
    openBalance != null &&
    openBalance > 0 &&
    windowBalance != null &&
    windowBalance > 0
  if (!rebasable) return { kept, narrowed, scale: null, curve: null, openBalance, windowBalance }

  const scale = openBalance / windowBalance
  let cum = 0
  const curve = kept.map((p, i) => {
    const profit = (p.profit ?? 0) * scale
    cum += profit
    return {
      ...p,
      index: i + 1,
      equity: openBalance + cum,
      profit,
      // Every dollar-denominated field on the point scales by the SAME constant, or the excursion
      // halo stops containing its own net result — the exact shape the cost filter already had to
      // clamp for. `r` is deliberately untouched: it is P&L over the risk the trade was sized to,
      // so it is invariant under a change of account size, which is why both pages lead with it.
      ...(p.favorable != null ? { favorable: p.favorable * scale } : {}),
      ...(p.adverse != null ? { adverse: p.adverse * scale } : {}),
      ...(p.costs_usd != null ? { costs_usd: p.costs_usd * scale } : {}),
    }
  })
  return { kept, narrowed, scale, curve, openBalance, windowBalance }
}
