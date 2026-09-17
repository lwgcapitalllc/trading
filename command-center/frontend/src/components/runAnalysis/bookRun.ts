/**
 * A TRADE BOOK read as a run — the shape the analysis panels take — for a page that has trades
 * but no backtest row: a broker account's real history.
 *
 * ⚠ The stack page builds the same object inline (`StackDetail.composeCombined`), with its own
 * window and leg handling on top. The arithmetic is the same on purpose; folding that page onto
 * this helper is a separate change, deliberately not made alongside the account view.
 */
import type { BacktestDetail as Run, DailyPnlPoint, EquityPoint } from '@/types'
import { computeFallbacks, worstLosingStreakOf, type FallbackMetrics } from './panels'

/** One row per UTC day that closed a trade, in date order — the backend's `daily_pnl` shape. */
export function dailyPnlOf(points: EquityPoint[]): DailyPnlPoint[] {
  const byDay = new Map<string, number>()
  for (const p of points) {
    const day = (p.date ?? '').slice(0, 10)
    if (!day) continue
    byDay.set(day, (byDay.get(day) ?? 0) + (p.profit ?? 0))
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, pnl]) => ({ date, pnl }))
}

/**
 * The book re-based onto `base` with every non-trade balance move taken out: `equity` becomes
 * `base + the trades' running P&L`. A drawdown chart reads `equity` directly, so without this a
 * withdrawal would draw as a loss.
 */
export function tradingEquity(points: EquityPoint[], base: number): EquityPoint[] {
  let cum = 0
  return points.map((p) => {
    cum += p.profit ?? 0
    return { ...p, equity: base + cum }
  })
}

export function runFromBook(points: EquityPoint[]): { run: Run; fallback: FallbackMetrics } {
  const profits = points.map((t) => t.profit ?? 0)
  const wins = profits.filter((p) => p > 0)
  const losses = profits.filter((p) => p < 0)
  const grossWin = wins.reduce((a, b) => a + b, 0)
  const grossLoss = Math.abs(losses.reduce((a, b) => a + b, 0))
  const net = profits.reduce((a, b) => a + b, 0)
  let peak = -Infinity
  let maxDd = 0
  let bal = 0
  for (const p of profits) {
    bal += p
    peak = Math.max(peak, bal, 0)
    maxDd = Math.max(maxDd, peak - bal)
  }
  const spans = points
    .filter((p) => p.entry_ms != null && p.exit_ms != null)
    .map((p) => (p.exit_ms! - p.entry_ms!) / 60_000)
    .filter((m) => m >= 0)
  const daily = dailyPnlOf(points)
  const fallback = computeFallbacks(daily)
  const run = {
    net_pnl: points.length ? net : null,
    trade_count: points.length,
    win_rate: points.length ? wins.length / points.length : null,
    win_count: wins.length,
    profit_factor: grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? Infinity : null,
    avg_win: wins.length ? grossWin / wins.length : null,
    avg_loss: losses.length ? -grossLoss / losses.length : null,
    max_drawdown: maxDd || null,
    sharpe: fallback.sharpe,
    platform_sharpe: null,
    sharpe_low_sample: daily.length < 10,
    worst_day_pnl: fallback.worstDay,
    worst_losing_streak: worstLosingStreakOf(profits),
    avg_trade_duration_min: spans.length ? spans.reduce((a, b) => a + b, 0) / spans.length : null,
    profit_concentration_pct: null,
    daily_pnl: daily,
    cost_layers: null,
    broker_profile: null,
  } as unknown as Run
  return { run, fallback }
}
