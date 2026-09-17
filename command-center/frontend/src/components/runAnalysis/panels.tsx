/**
 * The run ANALYSIS panels — KPIs, equity, drawdown, daily P&L, direction split — shared by every
 * page that reads a trade book: a single backtest, a portfolio stack, and a broker account's real
 * history. Moved VERBATIM out of `pages/BacktestDetail.tsx` on 2026-09-17 so the account page could
 * use them without importing a page; nothing inside was reworded. See `frontend/notes/backtest-results.md` → *The analysis panels are shared*.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import {
  AreaChart,
  Area,
  ComposedChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Label,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
  ReferenceArea,
  ReferenceDot,
} from 'recharts'
import InfoTip from '@/components/InfoTip'
import { brokerName } from '@/lib/brokerName'
import { COST_LAYER_LABEL } from '@/lib/costLayers'
import type {
  BacktestDetail as Run,
  EquityPoint,
  DailyPnlPoint,
  SizedTimelineDay,
  SizingMode,
} from '@/types'
import { C } from '@/themes/chart'
import { REGIME_COLORS, REGIME_LABEL } from '@/lib/regime'
import { balTick, balanceTicks, dateMs, monthLabel, monthTicks, type XMode } from '@/lib/chartAxis'

// ── Formatters ────────────────────────────────────────────────────────────────

export function dollar(n: number | null | undefined, signed = false): string {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : signed ? '+' : ''
  return `${sign}$${abs.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export function pct(n: number | null | undefined): string {
  if (n == null) return '—'
  return `${(n * 100).toFixed(1)}%`
}

// Trade duration in the largest unit that still reads as a quantity. "1365 min" is a number the
// reader has to divide before it means anything; 22.8 h is the same fact already divided.
export function fmtHold(min: number | null | undefined): string {
  if (min == null) return '—'
  const a = Math.abs(min)
  if (a < 90) return `${min.toFixed(0)} min`
  if (a < 2880) return `${(min / 60).toFixed(1)} h`
  return `${(min / 1440).toFixed(1)} d`
}

// Renders a dollar amount ALWAYS at full precision, with thousand separators. When the string
// genuinely cannot fit it shrinks the TYPE, it does not abbreviate — `$14.4M` and `$846.3k` are
// harder to read than the number they replace, and reading them is the whole job of a headline
// figure (Aaron, 2026-08-01). `dollarShort` is deleted; nothing may reintroduce a `k`/`M` form here.
//
// ⚠ **It must measure against the hero ROW, not against itself, and that was the actual bug.**
// This span is a content-sized flex item (`flex: 0 1 auto`), so its own width IS the text's width —
// which made `need > avail - FIT_SLACK` true by exactly the slack, on every value, forever. That is
// why `+$14,387,475` rendered as `$14.4M` in a card with room for it twice over. `CardHero` marks
// the row `data-fit-box`; measuring anything content-sized reintroduces the bug silently, because
// the output still looks like a deliberate abbreviation. The repo already recorded this trap for
// PanelRow values ("do not use FitMoney here") — it applied to the hero too and was missed.
export const FIT_SLACK = 2
// Below this the headline would be smaller than the rows under it, which reads as an error rather
// than as a big number. At that point the card is too narrow for this metric at all.
export const FIT_MIN_SCALE = 0.6

export function FitMoney({
  n,
  signed = false,
}: {
  n: number | null | undefined
  signed?: boolean
}) {
  const wrapRef = useRef<HTMLSpanElement>(null)
  const ghostRef = useRef<HTMLSpanElement>(null)
  // {scale, width} together: a CSS transform leaves the layout box at its natural size, so without
  // pinning the width the unit label beside it ("net") would sit where the UNSCALED text ended.
  const [fit, setFit] = useState<{ scale: number; width: number } | null>(null)
  const full = dollar(n, signed)
  useEffect(() => {
    const wrap = wrapRef.current,
      ghost = ghostRef.current
    if (!wrap || !ghost) return
    const box = (wrap.closest('[data-fit-box]') as HTMLElement | null) ?? wrap
    const measure = () => {
      const avail = box.getBoundingClientRect().width - FIT_SLACK
      const need = ghost.getBoundingClientRect().width // always the UNSCALED width
      if (!(need > 0) || !(avail > 0) || need <= avail) return setFit(null)
      const scale = Math.max(FIT_MIN_SCALE, avail / need)
      setFit({ scale, width: need * scale })
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(box)
    ro.observe(ghost)
    return () => ro.disconnect()
  }, [full])
  if (n == null) return <span>—</span>
  return (
    <span
      ref={wrapRef}
      className="inline-block relative whitespace-nowrap"
      style={fit ? { width: `${fit.width}px` } : undefined}
    >
      <span
        ref={ghostRef}
        aria-hidden
        className="invisible absolute left-0 top-0 whitespace-nowrap pointer-events-none"
      >
        {full}
      </span>
      <span
        className="inline-block origin-left"
        style={fit ? { transform: `scale(${fit.scale})` } : undefined}
      >
        {full}
      </span>
    </span>
  )
}

// A bare 'YYYY-MM-DD' parses as UTC midnight and then prints in the VIEWER's timezone, which
// lands a day early anywhere west of Greenwich: the run header read "Jan 1, 2021 → Jul 27, 2026"
// for a run whose stored window is 2021-01-02 → 2026-07-28. Pin it to local midnight — the same
// guard chartDateLabel below already carried. The slice also tolerates a full ISO datetime.
export function fmtDate(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export function chartDateLabel(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  const yr = String(d.getFullYear()).slice(-2)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ` '${yr}`
}

// ── Calendar tick helpers ─────────────────────────────────────────────────────

export const _MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
]

// Endpoints show day ("May 30 '23"), interior quarters just month+year ("Apr '24")
export function calTickLabel(iso: string, isEndpoint: boolean): string {
  const d = new Date(iso.slice(0, 10) + 'T00:00:00')
  const m = _MONTHS[d.getMonth()]
  const yr = String(d.getFullYear()).slice(-2)
  return isEndpoint ? `${m} ${d.getDate()} '${yr}` : `${m} '${yr}`
}

// For index-based charts: tick positions at start, Q1/Q2/Q3/Q4 boundaries, end
export function calIndexTicks(pts: Array<{ index: number; date?: string | null }>): number[] {
  if (pts.length <= 1) return pts.map((p) => p.index)
  const first = pts[0].date,
    last = pts[pts.length - 1].date
  if (!first || !last) return [pts[0].index, pts[pts.length - 1].index]

  const dateToIdx = new Map<string, number>()
  for (const p of pts) {
    if (p.date && !dateToIdx.has(p.date)) dateToIdx.set(p.date, p.index)
  }
  const sorted = [...dateToIdx.keys()].sort()
  const nearest = (target: string) => {
    const d = sorted.find((s) => s >= target)
    return d != null ? dateToIdx.get(d) : undefined
  }

  const sy = new Date(first.slice(0, 10) + 'T00:00:00').getFullYear()
  const ey = new Date(last.slice(0, 10) + 'T00:00:00').getFullYear()
  const set = new Set<number>([pts[0].index, pts[pts.length - 1].index])
  for (let y = sy; y <= ey; y++)
    for (const m of ['01', '04', '07', '10']) {
      const idx = nearest(`${y}-${m}-01`)
      if (idx != null) set.add(idx)
    }
  return [...set].sort((a, b) => a - b)
}

// For date-keyed charts: tick values at start, Q1/Q2/Q3/Q4 boundaries, end
export function calDateTicks(data: DailyPnlPoint[]): string[] {
  if (data.length <= 1) return data.map((d) => d.date)
  const all = data.map((d) => d.date)
  const nearest = (target: string) => all.find((d) => d >= target)
  const sy = new Date(data[0].date + 'T00:00:00').getFullYear()
  const ey = new Date(data[data.length - 1].date + 'T00:00:00').getFullYear()
  const set = new Set<string>([data[0].date, data[data.length - 1].date])
  for (let y = sy; y <= ey; y++)
    for (const m of ['01', '04', '07', '10']) {
      const d = nearest(`${y}-${m}-01`)
      if (d) set.add(d)
    }
  return [...set].sort()
}

// ── Color helpers ─────────────────────────────────────────────────────────────

export function winRateCls(rate: number | null): string {
  if (rate == null) return 'text-text-tertiary'
  if (rate >= 0.6) return 'text-pos-text'
  if (rate >= 0.5) return 'text-warn-text'
  return 'text-neg-text'
}

export function winRateLabel(rate: number | null): string {
  if (rate == null) return 'win / total trades'
  if (rate >= 0.6) return 'strong'
  if (rate >= 0.5) return 'good'
  if (rate >= 0.45) return 'marginal — needs high R:R'
  return 'weak — needs high R:R'
}

// A ratio card's value: a number, ∞ when the denominator is legitimately zero (no losing trade / no
// drawdown), or a dash only when the input truly isn't there.
export function kpiNum(v: number | null): string {
  if (v == null) return '—'
  return Number.isFinite(v) ? v.toFixed(2) : '∞'
}

export function pfCls(pf: number | null): string {
  if (pf == null) return 'text-text-tertiary'
  if (pf >= 2.0) return 'text-pos-text'
  if (pf >= 1.5) return 'text-warn-text'
  return 'text-neg-text'
}

export function pfLabel(pf: number | null): string {
  if (pf == null) return 'gross wins ÷ gross losses'
  if (!Number.isFinite(pf)) return 'no losing trades'
  if (pf >= 2.0) return 'strong — wins 2× losses'
  if (pf >= 1.5) return 'good'
  if (pf >= 1.0) return 'marginal'
  return 'losing — below 1.0'
}

// Sharpe has no colour helper on purpose. It used to be graded green/amber/red by value,
// which reads as a verdict the number can't support: 0.91 is positive AND weak, and this
// run's own news filter moves it 0.91 → 2.98 by removing 3 of 142 trades. The panel prints
// sharpeLabel's word beside it instead. See the colour policy on PerformancePanel.

export function sharpeLabel(s: number | null, estimated: boolean): string {
  if (s == null) return 'risk-adjusted annual return'
  const base = s >= 2.0 ? 'excellent' : s >= 1.0 ? 'good' : s >= 0.5 ? 'marginal' : 'poor'
  return estimated ? `${base} (estimated)` : base
}

// Turns a value-colour class into an EXCEPTION colour: an ordinary value gets no colour at
// all. Lets the *Cls helpers stay the single definition of "what counts as bad" while the
// panel only paints the rows that cross it. See the colour policy on PerformancePanel.
export function exceptionCls(cls: string): string | undefined {
  return cls === 'text-text-primary' || cls === 'text-text-tertiary' ? undefined : cls
}

// ── Recovery factor ──────────────────────────────────────────────────────────
// Annualized net P&L ÷ max drawdown — both in dollars, so it needs no starting
// capital. (Previously mislabelled "Calmar"; real Calmar lives below.)

export function computeRecoveryFactor(
  netPnl: number | null,
  maxDrawdown: number | null,
  equity: EquityPoint[]
): number | null {
  if (netPnl == null || maxDrawdown == null) return null
  const absDd = Math.abs(maxDrawdown)
  if (absDd === 0 || equity.length < 2) return null
  // Slice to YYYY-MM-DD — MT5 equity dates are full ISO datetimes; appending T00:00:00 breaks parsing
  const firstDate = equity[0].date?.slice(0, 10)
  const lastDate = equity[equity.length - 1].date?.slice(0, 10)
  if (!firstDate || !lastDate) return null
  const days = (new Date(lastDate).getTime() - new Date(firstDate).getTime()) / 86_400_000
  if (days < 1) return null
  return (netPnl * (365 / days)) / absDd
}

// computeRecoveryFactor's value is folded into the Calmar tooltip (Recovery Factor was
// removed as a redundant card — it's the dollar twin of Calmar). The cls/label helpers it
// used as a card are gone with it.

// ── Equity rebasing (platform-agnostic) ──────────────────────────────────────
// Rebase an equity curve so it starts at `balance` and moves with the trades:
//   rebased[i] = balance + Σ profit[0..i]
// Cumulative P&L is derived from each point's `profit` field — which BOTH NT8 and MT5
// points carry — so the original base is irrelevant: NT8 curves start at 0 and MT5 curves
// start at a deposit, but summing per-trade profit normalizes both to the same P&L series.
// That makes a 50k NT8 run and a 50k MT5 run with identical trades produce identical scores.
//
// ⚠ The series OPENS on `balance` itself, before any trade. That anchor point is not cosmetic: a
// drawdown is measured from a peak, and the account's first peak is the money it started with.
// Without it a run whose first trade loses is measured from a peak that is already below the
// opening balance, so the opening loss is invisible — and `services/metrics.max_drawdown_pct`,
// which the Runs list renders, DOES prepend it. Two definitions of one number in two places is
// how the list and the detail page come to disagree about the same run.
export function rebaseEquity(equity: EquityPoint[], balance: number): number[] {
  const out: number[] = [balance]
  let cum = 0
  for (const e of equity) {
    cum += e.profit ?? 0
    out.push(balance + cum)
  }
  return out
}

// Max peak-to-trough drawdown (in dollars) of a value series. Translation-invariant, so the
// dollar drawdown is the same regardless of `balance` — but it's derived from the trades, not
// a platform-reported field, so identical trades give an identical number across NT8 and MT5.
export function maxDrawdownOf(series: number[]): number {
  let peak = -Infinity
  let maxDd = 0
  for (const v of series) {
    if (v > peak) peak = v
    const dd = peak - v
    if (dd > maxDd) maxDd = dd
  }
  return maxDd
}

// The WORST drawdown as a fraction of the equity it fell FROM — the account-ending measure. On a
// compounding run this is a different EPISODE from the biggest dollar drawdown, and the two must
// never be presented as one number: on the shipped sos_fade run the deepest dollar drop is
// $109,665 from a $330,303 peak (33.2%), while the worst percentage drop is 54.9% ($16,748 →
// $7,551, only $9,198). Reporting the big dollar figure as the percentage is what produced
// "1096.7% of capital" — the dollar drawdown divided by a static account_size the account had
// long outgrown. Returns the dollars and peak of the SAME episode so the card's sub-line can
// describe the drawdown its value actually names.
export function maxDrawdownPctOf(
  series: number[]
): { pct: number; dollars: number; peak: number } | null {
  let peak = -Infinity
  let worst: { pct: number; dollars: number; peak: number } | null = null
  for (const v of series) {
    if (v > peak) peak = v
    if (peak <= 0) continue // a non-positive peak has no meaningful percent
    const dd = peak - v
    const pct = dd / peak
    if (worst == null || pct > worst.pct) worst = { pct, dollars: dd, peak }
  }
  return worst
}

// ── Calmar ratio ─────────────────────────────────────────────────────────────
// Real Calmar = CAGR ÷ max-drawdown-as-fraction (same shape as
// algos/shared/shared_calmar.py). Both inputs are fractions of capital,
// and the compounding in CAGR means starting capital does NOT cancel out — it is
// genuinely required. With a balance supplied (from the ruleset's account_size or the
// what-if slider), the equity curve is rebased to that balance and the score computes.
//
// BOTH sides must compound or the ratio is nonsense. CAGR already does. The drawdown must
// therefore be measured against the equity it fell FROM, not against the STARTING balance —
// dividing a late-run dollar drawdown by the opening capital reports a fraction the account
// never experienced, and dragged this ratio down by the same factor. Measured on the shipped
// sos_fade run: 0.11 (red, "poor") against a static $10k, 2.25 ("good") against the peak.

export function computeCalmar(equity: EquityPoint[], balance: number | null): number | null {
  if (balance == null || balance <= 0 || equity.length < 2) return null
  const firstDate = equity[0].date?.slice(0, 10)
  const lastDate = equity[equity.length - 1].date?.slice(0, 10)
  if (!firstDate || !lastDate) return null
  const days = (new Date(lastDate).getTime() - new Date(firstDate).getTime()) / 86_400_000
  if (days < 1) return null
  // Derive net P&L and max drawdown from the rebased curve (trade-derived → platform-agnostic).
  const rebased = rebaseEquity(equity, balance)
  const netPnl = rebased[rebased.length - 1] - balance
  const dd = maxDrawdownPctOf(rebased)
  // Zero drawdown isn't "unknown" — it's an undefeated curve, so Calmar is genuinely infinite.
  // Report Infinity (the card prints ∞) rather than a dash that reads as missing data.
  if (dd == null || dd.pct === 0) return netPnl > 0 ? Infinity : null
  const years = days / 365
  const cagr = Math.pow(1 + netPnl / balance, 1 / Math.max(years, 0.1)) - 1
  return cagr / dd.pct
}

export function calmarCls(c: number | null): string {
  if (c == null) return 'text-text-tertiary'
  if (c >= 3.0) return 'text-pos-text'
  if (c >= 1.0) return 'text-warn-text'
  return 'text-neg-text'
}

export function calmarLabel(c: number | null): string {
  if (c == null) return 'set an account balance'
  if (!Number.isFinite(c)) return 'no drawdown to divide by'
  if (c >= 3.0) return 'excellent'
  if (c >= 1.5) return 'good'
  if (c >= 1.0) return 'marginal'
  return 'poor — drawdown outpaces return'
}

// ── Z-score (Wald–Wolfowitz runs test) ───────────────────────────────────────
// Tests whether the win/loss sequence streaks more (or less) than chance.
// Scratch trades (profit === 0) are excluded so the sequence is cleanly binary.
export function computeZScore(equity: EquityPoint[]): number | null {
  const seq = equity
    .map((e) => e.profit)
    .filter((p): p is number => p != null && p !== 0)
    .map((p) => p > 0)
  const n = seq.length
  if (n < 2) return null
  const n1 = seq.filter(Boolean).length // wins
  const n2 = n - n1 // losses
  if (n1 === 0 || n2 === 0) return null
  let runs = 1
  for (let i = 1; i < n; i++) if (seq[i] !== seq[i - 1]) runs++
  const mu = (2 * n1 * n2) / n + 1
  const variance = (2 * n1 * n2 * (2 * n1 * n2 - n)) / (n * n * (n - 1))
  if (variance <= 0) return null
  return (runs - mu) / Math.sqrt(variance)
}

export function zScoreCls(z: number | null): string {
  if (z == null) return 'text-text-tertiary'
  return Math.abs(z) > 2 ? 'text-warn-text' : 'text-text-primary'
}

// Why the runs test couldn't run, said in the strategy's own terms — a curve with no losing trade
// has no win/loss sequence to test, and that is information, not a missing value.
export function zScoreUnavailableLabel(equity: EquityPoint[]): string {
  const profits = equity.map((e) => e.profit).filter((p): p is number => p != null && p !== 0)
  if (profits.length < 2) return 'runs test — needs 2+ trades'
  const losses = profits.filter((p) => p < 0).length
  if (losses === 0) return `all ${profits.length} trades won — no streaks to test`
  if (losses === profits.length) return `all ${profits.length} trades lost — no streaks to test`
  return 'runs test — needs wins & losses'
}

export function zScoreLabel(z: number | null): string {
  if (z == null) return 'runs test — needs wins & losses'
  const a = Math.abs(z)
  if (a <= 1.5) return 'streaks look random'
  if (a <= 2) return 'mild streaking'
  return 'non-random streaking'
}

// ── Profit concentration over time ───────────────────────────────────────────
// Share of total gross profit earned in the single most profitable quarter of the test span.
// The span (first→last date) is split into 4 equal slices. High = the edge is clustered in one
// period — a classic curve-fit signal.
//
// MEASURED IN RETURNS, NOT DOLLARS, whenever the run compounded (fixed 2026-07-31). In dollars
// this metric reports the COMPOUNDING, not the clustering: on a run whose account grows 85x the
// final quarter must hold nearly all the dollars however evenly the edge is spread. Measured on
// sos_fade d2ab68f9e884 — dollar quarters $9k / $49k / $71k / $1,039k read 89% ("edge
// clustered — overfit risk"); the same trades as returns on the equity each was taken with read
// 40% ("spread across the test"). The amber was the metric describing the account, not the edge.
//
// The switch is whether the curve carries a real account base: a %-of-equity strategy compounds
// and must be normalized, while a cum-P&L-from-zero curve (the NT8 shape) is a unit-size run
// whose dollars already ARE comparable across periods. `equityBase` decides, and the backend's
// services/metrics.profit_concentration_pct applies the identical rule so the stored value and
// this one never disagree.
//
// Falls back to the daily dollar series when there is no curve at all (stack legs, old runs).
export function equityBase(equity: EquityPoint[]): number {
  if (equity.length === 0) return 0
  return (equity[0].equity ?? 0) - (equity[0].profit ?? 0)
}

export function computeProfitConcentration(
  daily: DailyPnlPoint[],
  equity: EquityPoint[] = []
): number | null {
  // Each entry contributes a WEIGHT: a return when the run compounded, else a dollar amount.
  const base = equityBase(equity)
  const points: Array<{ date: string; weight: number }> =
    base > 0
      ? equity.flatMap((e) => {
          const before = (e.equity ?? 0) - (e.profit ?? 0)
          return e.date && before > 0 ? [{ date: e.date, weight: (e.profit ?? 0) / before }] : []
        })
      : daily.filter((d) => d.date).map((d) => ({ date: d.date, weight: d.pnl }))

  if (points.length < 2) return null
  const t0 = new Date(points[0].date.slice(0, 10)).getTime()
  const t1 = new Date(points[points.length - 1].date.slice(0, 10)).getTime()
  const span = t1 - t0
  if (!(span > 0)) return null
  const q = [0, 0, 0, 0]
  let gross = 0
  for (const p of points) {
    if (p.weight <= 0) continue
    gross += p.weight
    let idx = Math.floor(((new Date(p.date.slice(0, 10)).getTime() - t0) / span) * 4)
    if (idx > 3) idx = 3
    if (idx < 0) idx = 0
    q[idx] += p.weight
  }
  if (!(gross > 0)) return null
  return (Math.max(...q) / gross) * 100
}

// ── The two trade-shape metrics (added 2026-08-01) ────────────────────────────
//
// An audit of run f866873aa862 found no arithmetic wrong on this page. What was wrong was what
// two headline numbers let a reader CONCLUDE, and neither is fixable by relabelling:
//
//   Win rate 67.3% is true, and 45 of the 111 "winners" made under a sixth of a typical loss —
//   every one of them exiting at the breakeven-stop buffer, which is the stop doing its job
//   correctly and is not an edge. The honest split is 40% won / 27% scratched / 33% lost.
//
//   Profit concentration 34.5% is the largest QUARTER's share — a question about TIME. The
//   reader hears the question about TRADES, and its answer on that run was 47%: five trades of
//   165 made nearly half of everything won. The two can disagree completely and both be right.
//
// Both weight by RETURN when the run compounded, for the same reason `computeProfitConcentration`
// does. Both are computed HERE rather than read off the run row, matching that function: the
// stored value is whatever basis was current when a run finished, and the news filter needs the
// numbers recomputed over a subset anyway.
export function tradeWeights(equity: EquityPoint[]): number[] {
  if (equity.length === 0) return []
  if (equityBase(equity) <= 0) return equity.map((e) => e.profit ?? 0)
  return equity.flatMap((e) => {
    const before = (e.equity ?? 0) - (e.profit ?? 0)
    return before > 0 ? [(e.profit ?? 0) / before] : []
  })
}

// A trade this far below the run's own typical loss neither won nor lost meaningfully.
export const SCRATCH_FRACTION = 0.15

export function median(xs: number[]): number {
  const a = [...xs].sort((x, y) => x - y)
  const mid = Math.floor(a.length / 2)
  return a.length % 2 ? a[mid] : (a[mid - 1] + a[mid]) / 2
}

// How many trades were effectively FLAT. The yardstick is the run's own median full loss, not a
// typed-in dollar figure: for a fixed-risk strategy that median IS 1R, and for any other it is
// still "what an ordinary adverse outcome costs here" — so it self-scales across strategies,
// instruments and account sizes with nothing to tune. Median rather than mean so one outsized
// loss cannot move the bar. `null` (not 0) when there are no losers to measure against: with no
// scale there is no honest answer, and 0 would read as "no scratches" — the opposite of
// "cannot tell". Mirrors services/metrics.scratch_count.
export function computeScratchCount(equity: EquityPoint[]): number | null {
  const w = tradeWeights(equity)
  const losses = w.filter((x) => x < 0).map(Math.abs)
  if (losses.length === 0) return null
  const scale = median(losses)
  if (!(scale > 0)) return null
  return w.filter((x) => Math.abs(x) < scale * SCRATCH_FRACTION).length
}

export const TRADE_CONCENTRATION_TOP_N = 5

// Share of GROSS PROFIT made by the biggest few winners. Mirrors
// services/metrics.trade_concentration_pct.
export function computeTradeConcentration(equity: EquityPoint[]): number | null {
  const wins = tradeWeights(equity)
    .filter((x) => x > 0)
    .sort((a, b) => b - a)
  const gross = wins.reduce((t, x) => t + x, 0)
  if (!(gross > 0)) return null
  return (wins.slice(0, TRADE_CONCENTRATION_TOP_N).reduce((t, x) => t + x, 0) / gross) * 100
}

export function tradeConcentrationLabel(c: number | null): string {
  if (c == null) return `top ${TRADE_CONCENTRATION_TOP_N} winners ÷ gross profit`
  if (c >= 50) return 'the edge rests on a handful of trades'
  if (c >= 30) return 'a few trades carry a lot of it'
  return 'spread across many trades'
}

export function concentrationCls(c: number | null): string {
  if (c == null) return 'text-text-tertiary'
  return c >= 60 ? 'text-warn-text' : 'text-text-primary'
}

export function concentrationLabel(c: number | null): string {
  if (c == null) return 'top quarter ÷ gross profit'
  if (c >= 60) return 'edge clustered — overfit risk'
  if (c >= 40) return 'somewhat concentrated'
  return 'spread across the test'
}

// ── Fallback KPI computation ──────────────────────────────────────────────────
// Derives Sharpe / Worst Day / Worst Streak from daily_pnl when the
// NT8 agent doesn't report them directly.

export const TRADING_DAYS_PER_YEAR = 252
export const SHARPE_LOW_SAMPLE_DAYS = 10

/**
 * Per-day P&L for EVERY weekday spanned by the series, flat days included as 0.
 *
 * Mirrors `backend/services/metrics.py:zero_filled_daily_values` exactly, and it is the whole
 * story behind the Sharpe bug fixed 2026-07-31. `daily_pnl` holds only days that CLOSED a trade —
 * flat days are absent by design, because the trailing-drawdown engine walks the days that exist.
 * Scoring that series as if it were the population asks "how good were the days it traded", then
 * annualizes by √252 as if it had traded 252 of them. On the shipped sos_fade run that reads
 * 2.98 against a true 0.91. A flat day is a real observation and belongs in the series.
 *
 * Weekends are skipped to match √252, but any date PRESENT in the input is kept even on a weekend,
 * so a Sunday-open forex fill is never silently dropped.
 */
export function zeroFilledDailyValues(daily_pnl: DailyPnlPoint[]): number[] {
  const byDate = new Map<string, number>()
  for (const d of daily_pnl) {
    if (!d.date) continue
    const key = d.date.slice(0, 10)
    byDate.set(key, (byDate.get(key) ?? 0) + (d.pnl ?? 0))
  }
  if (byDate.size < 2) return [...byDate.values()]

  const keys = [...byDate.keys()].sort()
  const last = keys[keys.length - 1]
  // Local midnight, the same guard fmtDate carries — a bare 'YYYY-MM-DD' parses as UTC and steps
  // the calendar a day early anywhere west of Greenwich.
  const cur = new Date(`${keys[0]}T00:00:00`)
  const out: number[] = []
  for (;;) {
    const key = `${cur.getFullYear()}-${String(cur.getMonth() + 1).padStart(2, '0')}-${String(cur.getDate()).padStart(2, '0')}`
    const weekday = cur.getDay() >= 1 && cur.getDay() <= 5
    if (byDate.has(key) || weekday) out.push(byDate.get(key) ?? 0)
    if (key >= last) break
    cur.setDate(cur.getDate() + 1)
  }
  return out
}

/** Annualized daily Sharpe. The ONE frontend definition — see zeroFilledDailyValues for why. */
export function dailySharpe(daily_pnl: DailyPnlPoint[]): number | null {
  const vals = zeroFilledDailyValues(daily_pnl)
  if (vals.length < 2) return null
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length
  const variance = vals.reduce((a, b) => a + (b - mean) ** 2, 0) / (vals.length - 1)
  const sd = Math.sqrt(variance)
  return sd > 0 ? (mean / sd) * Math.sqrt(TRADING_DAYS_PER_YEAR) : null
}

/**
 * Longest run of consecutive losing TRADES, from a list of per-trade P&L.
 *
 * Takes trades, never days, because the row it feeds is labelled in trades — the backend's
 * `backtest/output.py:_worst_losing_streak` walks the trade list. Counting consecutive losing
 * DAYS here and letting it land in that row is how the panel reported one unit while printing
 * the other, which is why `FallbackMetrics` no longer carries a streak at all.
 */
export function worstLosingStreakOf(pnls: number[]): number | null {
  if (!pnls.length) return null
  let max = 0,
    cur = 0
  for (const p of pnls) {
    if (p < 0) {
      cur++
      if (cur > max) max = cur
    } else cur = 0
  }
  return max
}

export interface FallbackMetrics {
  worstDay: number | null
  sharpe: number | null
}

export function computeFallbacks(daily_pnl: DailyPnlPoint[]): FallbackMetrics {
  if (!daily_pnl.length) return { worstDay: null, sharpe: null }

  // Sample size is still counted in ACTIVE days — zero-filling adds observations to the series
  // but not evidence, so it must not talk a 4-day run past the low-sample gate.
  const activeDays = daily_pnl.filter((d) => (d.pnl ?? 0) !== 0).length

  return {
    worstDay: Math.min(...daily_pnl.map((d) => d.pnl)),
    sharpe: activeDays >= SHARPE_LOW_SAMPLE_DAYS ? dailySharpe(daily_pnl) : null,
  }
}

// ── Derived metrics ──────────────────────────────────────────────────────────

// Every number the panel shows, derived from one run. Pulled out of the component so the
// SAME expressions can be evaluated a second time against a comparison run — that is what
// lets the news filter print a delta on each row instead of shipping a second copy of the
// panel. Adding a metric here and forgetting the card is harmless; the reverse is what drifts.
export function deriveKpis(
  run: Run,
  fallback: FallbackMetrics,
  equity: EquityPoint[],
  balance: number | null
) {
  const sharpe = run.sharpe ?? fallback.sharpe
  const worstDay = run.worst_day_pnl ?? fallback.worstDay
  // No fallback: a streak must come from a TRADE list or not at all. Both synthesizers
  // (buildFilteredRun, StackDetail.composeCombined) set it via worstLosingStreakOf.
  const worstStreak = run.worst_losing_streak
  const recoveryFactor = computeRecoveryFactor(run.net_pnl, run.max_drawdown, equity)
  // Capital-based scores rebase the equity to `balance` (the ruleset's account_size, or the
  // what-if slider). Both compute off the same stored run — no re-run, no backend.
  const calmar = computeCalmar(equity, balance)
  // Expectancy. $/trade is always available; R needs per-trade risk, which stored trades
  // don't carry (profit only), so expectancy_r is not computable — left out honestly.
  const expectancyUsd =
    run.net_pnl != null && run.trade_count ? run.net_pnl / run.trade_count : null
  const zScore = computeZScore(equity)
  // Profit factor: the backend stores null when gross losses are 0 (divide-by-zero). That case
  // is an undefeated run, not unknown data — recover it from the trades and print ∞.
  const tradeProfits = equity.map((e) => e.profit).filter((p): p is number => p != null && p !== 0)
  const grossLoss = tradeProfits.filter((p) => p < 0).reduce((a, b) => a + Math.abs(b), 0)
  const pfValue =
    run.profit_factor ?? (tradeProfits.length > 0 && grossLoss === 0 ? Infinity : null)
  // Profit concentration: largest quarter's share of gross profit, in RETURNS on a compounding
  // run. Computed here rather than read from run.profit_concentration_pct: the stored column is
  // whatever basis was current when the run FINISHED, so preferring it would show a mix of the
  // old dollar figure and the new one depending on a run's age. Same formula both sides
  // (services/metrics.profit_concentration_pct), so a re-stamped row agrees with this.
  const profitConc = computeProfitConcentration(run.daily_pnl ?? [], equity)
  // The two trade-shape companions — see their definitions above for what each stops a reader
  // concluding. Same client-side-recompute rule as profitConc, and for the same reasons.
  const scratches = computeScratchCount(equity)
  const tradeConc = computeTradeConcentration(equity)
  // Max drawdown as a % of the equity it fell FROM (peak-relative), which is the drawdown that
  // would actually have ended the account. NOT the dollar drawdown over a static account_size:
  // that reported 1096.7% on a run whose $109,665 drop came off a $330,303 peak, because the
  // account had grown 33x away from the balance the denominator was frozen at.
  // Null only when no balance is available (no ruleset / no trades).
  const ddWorst =
    balance != null && balance > 0 && equity.length >= 2
      ? maxDrawdownPctOf(rebaseEquity(equity, balance))
      : null
  const maxDdPct = ddWorst != null ? ddWorst.pct * 100 : null
  // The dollars of that SAME episode — what the card's caption describes. A different, usually
  // larger, dollar drawdown exists later in a compounding run; it is reported separately, never
  // beside the percentage it does not correspond to.
  const ddAtWorstPct = ddWorst?.dollars ?? null
  const ddPeak = ddWorst?.peak ?? null
  // Deepest drawdown in DOLLARS (trade-derived; falls back to the run's stored value). This is
  // the prop-firm view — a firm caps dollars — and the comparison fallback when there's no balance.
  const tradeDd = equity.length >= 2 ? maxDrawdownOf(rebaseEquity(equity, 0)) : null
  const ddDollar = tradeDd ?? (run.max_drawdown != null ? Math.abs(run.max_drawdown) : null)

  const rrRatio =
    run.avg_win != null && run.avg_loss != null && run.avg_loss !== 0
      ? run.avg_win / Math.abs(run.avg_loss)
      : null

  return {
    netPnl: run.net_pnl,
    winRate: run.win_rate,
    avgDur: run.avg_trade_duration_min,
    sharpe,
    worstDay,
    worstStreak,
    recoveryFactor,
    calmar,
    expectancyUsd,
    zScore,
    pfValue,
    profitConc,
    maxDdPct,
    ddDollar,
    ddAtWorstPct,
    ddPeak,
    rrRatio,
    scratches,
    tradeConc,
  }
}
export type DerivedKpis = ReturnType<typeof deriveKpis>

// ── Time underwater ──────────────────────────────────────────────────────────
// Share of the test's CALENDAR span spent below the previous equity high. Max drawdown says how
// DEEP the hole was; this says how long you sat in it, which is the half that decides whether a
// strategy is holdable. Rebased to 0 so it never depends on the account balance.
//
// Weighted by elapsed days, not by row count (fixed 2026-07-31). `daily_pnl` holds only the days
// that closed a trade — flat days are deliberately absent (backtest/output.py) — so counting rows
// answered "what share of ACTIVE days were underwater" while the label said "of days". The gap is
// not cosmetic on a selective strategy: sos_fade trades ~2x a month, so a row is worth two
// weeks of calendar. It read 67% by rows and 70% by the clock. Equity between two closes sits at
// the earlier close's level, which is what each day of that gap is judged against.
export function computeTimeUnderwater(daily: DailyPnlPoint[]): number | null {
  const dated = daily.filter((d) => d.date)
  if (dated.length < 2) return null
  const dayOf = (d: string) => new Date(`${d.slice(0, 10)}T00:00:00`).getTime()
  const total = (dayOf(dated[dated.length - 1].date) - dayOf(dated[0].date)) / DAY_MS
  if (!(total > 0)) return null
  let bal = 0,
    peak = 0,
    under = 0,
    prev = dayOf(dated[0].date)
  for (const d of dated) {
    const t = dayOf(d.date)
    // The span ENDING at this close was held at the previous close's level.
    if (bal < peak) under += (t - prev) / DAY_MS
    bal += d.pnl ?? 0
    if (bal > peak) peak = bal
    prev = t
  }
  return under / total
}

// ── Performance panel — three questions ──────────────────────────────────────
//
// Twelve metrics are not twelve peers. They answer three questions: what did it MAKE, what
// did it RISK, and can I TRUST it. One card per question, one hero number each, its
// supporting rows beneath.
//
// That grouping is what deleted the two problems this panel had. The 6+6 "More metrics"
// expand is gone (three wide cards hold every metric at once, so nothing hides behind a
// chevron), and with it the fixed pixel heights KPI_ROW_H 196/228 that the whole layout was
// pinned to in order to match the evaluation card — a constant height on variable content
// is what cropped the taller cards. Rows flow now; nothing is clipped. The evaluation card
// itself became the ribbon above, which is what stopped `unconstrained` rendering 300×196px
// of empty box (it states no rules, so it had no rows to draw).
//
// COLOUR POLICY — colour marks the exception, not the sign:
//   · the three hero numbers carry colour (they are each card's verdict)
//   · every delta is coloured in both directions — a change is the signal the news filter
//     was opened to find, and its direction is the point
//   · a supporting row stays neutral unless it is an EXCEPTION: an unexpected sign, or a
//     value at a threshold that should stop you
// Sign-colouring every row was the obvious alternative and it fails three ways: on a
// strategy that works nearly every row is positive, so green ranks nothing; Worst Day and
// Deepest-in-$ can only ever be negative, so red on them is decoration on a definition; and
// Sharpe 0.91 is positive AND weak, so green would call it good. Where a number is soft,
// the row says so in words (`· weak`) instead of lying with a colour.

// A drawdown meter's track is snapped to one of these ceilings rather than scaled to the
// run, so two runs of the same strategy stay visually comparable. Smallest ceiling that
// holds the largest marker with ~8% headroom.
export const METER_CEILINGS = [25, 50, 75, 100]
export function meterCeiling(...vals: Array<number | null | undefined>): number {
  const m = Math.max(0, ...vals.filter((v): v is number => v != null && isFinite(v)))
  return METER_CEILINGS.find((c) => m <= c * 0.92) ?? 100
}

// The observed drawdown as a bar, with two optional references: the ruleset's stated limit
// (gold tick) and the stress test's worst-1% simulated drawdown (hatched extension past the
// solid fill). Both are drawn ONLY when real — a percentage drawdown means nothing on its
// own, but neither reference may ever be invented to give it one. No stress test → no
// hatch, and the caption says so rather than implying the tail is zero.
export function DrawdownMeter({
  pct,
  limitPct,
  tailPct,
}: {
  pct: number
  limitPct: number | null
  tailPct: number | null
}) {
  const ceiling = meterCeiling(pct, limitPct, tailPct)
  const x = (v: number) => `${Math.min(100, (v / ceiling) * 100)}%`
  const breached = limitPct != null && pct >= limitPct
  const hasTail = tailPct != null && tailPct > pct
  return (
    <div className="mt-2.5">
      {/* The padding-top reserves room for the limit LABEL, so it is charged only when there is
          a limit to label — on a ruleset stating none it was 15px of blank card. The track clips
          its own fill, so the tick and label are siblings OUTSIDE it or they'd be cut off at the
          rounded edge. */}
      <div className={`relative ${limitPct != null ? 'pt-[14px]' : ''}`}>
        {limitPct != null && (
          <span
            className="absolute top-0 -translate-x-1/2 font-mono text-[9.5px] text-gold-text whitespace-nowrap"
            style={{ left: x(limitPct) }}
          >
            limit {limitPct.toFixed(0)}%
          </span>
        )}
        <div className="relative h-4 rounded-[4px] bg-bg-sunken border border-border-subtle overflow-hidden">
          <div
            className={`absolute inset-y-0 left-0 border-r-2 border-neg-text ${breached ? 'bg-neg-text/40' : 'bg-neg-text/20'}`}
            style={{ width: x(pct) }}
          />
          {hasTail && (
            <div
              className="absolute inset-y-0 bg-[repeating-linear-gradient(135deg,currentColor_0_2px,transparent_2px_6px)] text-neg-text/40"
              style={{ left: x(pct), width: x(tailPct! - pct) }}
            />
          )}
        </div>
        {limitPct != null && (
          <span
            className="absolute w-[2px] bg-gold-text"
            style={{ left: x(limitPct), top: 10, bottom: -3 }}
          />
        )}
      </div>
      <div className="flex justify-between mt-[3px] font-mono text-[9.5px] leading-none text-text-tertiary tabular-nums">
        <span>0%</span>
        <span>{(ceiling / 2).toFixed(0)}%</span>
        <span>{ceiling}%</span>
      </div>
    </div>
  )
}

export type PanelRow = {
  key: string
  label: string
  /** Usually a formatted number. A node so a pass/fail rule can render its tick or cross here. */
  value: React.ReactNode
  /**
   * What the metric IS, and what this run's value means — on the label's ⓘ, never beside the
   * value. Row suffixes used to carry both ("4 days · consecutive losing", "3.63 · strong —
   * wins 2× losses") and they cost twice: they define a term the reader already knows after the
   * first read, and they make the right column ragged, since the value column is only as tidy as
   * its longest sentence. With the definition on hover the right column holds numbers only and
   * lines up. The soft-value warnings the suffixes carried are not lost — they end each tip, and
   * the one that must stop you (a weak Sharpe, a clustered edge) also colours the value.
   */
  tip: string
  /** Exception colour ONLY — omit and the row stays neutral. See the colour policy above. */
  cls?: string
  cmp?: (k: DerivedKpis) => number | null | undefined
  fmt?: (delta: number) => string
  goodWhen?: 'higher' | 'lower' | 'none'
  /**
   * Renders the row as a button. A stack's Verdict card lists one row per strategy leg and
   * toggling it in or out recomputes every number beside it, so the control has to BE the row —
   * a second control elsewhere is a second place the panel and the roster can disagree about
   * what is being counted.
   */
  onClick?: () => void
  /** A swatch or icon before the label — a leg's colour, so the row matches its chart line. */
  lead?: React.ReactNode
  /** This row is switched OFF. Dims the WHOLE row, not just the value: an excluded leg is not a
   *  soft number, it is a row that is not in the totals above. */
  muted?: boolean
  /** A declared test seam, for a row a browser check has to find by more than its words. */
  testId?: string
}

// ── Card anatomy ─────────────────────────────────────────────────────────────
// Every card on this panel is the same four parts: a head, a hero, an optional caption, and a
// list of rows. They live at module scope because the VERDICT is one of those cards now, and a
// second private copy of these styles is exactly how it would drift out of line with the three
// beside it. Shared shape is the reason the verdict survived leaving its full-width ribbon: a
// row is 24px whatever it says, where the pills it used to be wrapped unpredictably at a
// quarter of the width.

/** Expanded, the last row's own padding is the card's bottom margin; collapsed, the meter's
 *  scale labels would otherwise sit on the border. */
export function panelCardCls(collapsed: boolean, filtered: boolean, topBorder: string): string {
  return `flex flex-col min-w-0 rounded-xl border border-border-subtle px-4 pt-[13px] ${
    collapsed ? 'pb-[12px]' : 'pb-[6px]'
  } ${filtered ? 'bg-accent/[0.06]' : 'bg-bg-surface'} ${topBorder}`
}

/** Title and question share ONE line. The question is orientation you read once; on its own row
 *  it charged ~16px of card height per card, forever, for a sentence nobody re-reads. The narrow
 *  fourth card has no room for one at all, so it passes the slot to its aside instead. */
export function CardHead({
  title,
  question,
  aside,
}: {
  title: string
  question?: string
  aside?: React.ReactNode
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="flex items-baseline gap-2 min-w-0">
        <span className="text-[10px] font-bold uppercase tracking-[0.9px] text-text-secondary shrink-0">
          {title}
        </span>
        {question && <span className="text-[10.5px] text-text-tertiary truncate">{question}</span>}
      </span>
      {aside}
    </div>
  )
}

export function CardHero({
  value,
  unit,
  cls,
  tip,
}: {
  value: React.ReactNode
  unit: React.ReactNode
  cls: string
  tip: string
}) {
  return (
    <div data-fit-box className="flex items-baseline gap-2.5 flex-wrap mt-2 mb-0.5">
      <span
        className={`text-[34px] font-bold font-mono leading-none tracking-[-0.8px] tabular-nums ${cls}`}
      >
        {value}
      </span>
      <span className="text-[12px] text-text-tertiary">
        {unit}
        <InfoTip text={tip} />
      </span>
    </div>
  )
}

/** Label + ⓘ on the left, value on the right, nothing else. See PanelRow.tip for why.
 *  A row carrying `onClick` renders as a button in the SAME shape — extending this rather than
 *  forking it is what keeps a stack's toggleable leg rows at the 24px every other row is. */
export function PanelRows({
  rows,
  delta,
}: {
  rows: PanelRow[]
  delta?: (r: PanelRow) => React.ReactNode
}) {
  return (
    <div className="mt-auto pt-2.5 border-t border-border-subtle">
      {rows.map((r, i) => {
        const cls = `flex w-full items-baseline justify-between gap-3 py-[4px] text-[12px] leading-[1.3] ${
          i < rows.length - 1 ? 'border-b border-border-subtle/60' : ''
        }`
        const body = (
          <>
            <span
              className={`flex items-center min-w-0 ${r.muted ? 'text-text-tertiary/55' : 'text-text-tertiary'}`}
            >
              {r.lead}
              <span className="truncate">{r.label}</span>
              <InfoTip text={r.tip} />
            </span>
            <span
              className={`font-mono tabular-nums text-right whitespace-nowrap ${
                r.cls ?? (r.muted ? 'text-text-tertiary/55' : 'text-text-primary')
              }`}
            >
              {r.value}
              {delta?.(r)}
            </span>
          </>
        )
        return r.onClick ? (
          <button
            key={r.key}
            type="button"
            data-testid={r.testId}
            onClick={r.onClick}
            className={`${cls} text-left transition-colors hover:text-text-primary`}
          >
            {body}
          </button>
        ) : (
          <div key={r.key} data-testid={r.testId} className={cls}>
            {body}
          </div>
        )
      })}
    </div>
  )
}

// ── Panel ────────────────────────────────────────────────────────────────────

export function PerformancePanel({
  run,
  fallback,
  equity = [],
  balance = null,
  compare = null,
  filtered = false,
  tailPct = null,
  limitPct = null,
  ribbon = null,
  verdict = null,
  collapsed = false,
}: {
  run: Run
  fallback: FallbackMetrics
  equity?: EquityPoint[]
  balance?: number | null
  // When set, every row's delta is measured against this run instead of showing its caption.
  // The news filter IS this comparison — there is no second copy of the numbers anywhere.
  compare?: { run: Run; fallback: FallbackMetrics; equity: EquityPoint[] } | null
  filtered?: boolean
  /** Worst-1% simulated drawdown, percent. Null unless a stress test measured one. */
  tailPct?: number | null
  /** The selected ruleset's stated peak-drawdown limit, percent. Null when it states none. */
  limitPct?: number | null
  /**
   * A full-width bar ABOVE the cards. Two callers still want one: a stack's strategy legend is
   * genuinely horizontal (one entry per leg, with its colour), and an optimizer combo has no
   * verdict at all — just a prompt to run a real backtest, which deserves the width. A graded
   * run passes `verdict` instead and gets that row back.
   */
  ribbon?: React.ReactNode
  /** A fourth CARD, right of Trusted. Mutually exclusive with `ribbon` in practice. */
  verdict?: React.ReactNode
  /**
   * Hero numbers + the drawdown meter only — the supporting rows and the meter's caption fold
   * away. Roughly halves the panel, which is what puts the equity curve on the same screen as
   * the headline. The three heroes ARE the summary, so nothing load-bearing hides here.
   */
  collapsed?: boolean
}) {
  const d = deriveKpis(run, fallback, equity, balance)
  const dc = compare ? deriveKpis(compare.run, compare.fallback, compare.equity, balance) : null

  const {
    sharpe,
    worstDay,
    worstStreak,
    calmar,
    expectancyUsd,
    zScore,
    pfValue,
    profitConc,
    maxDdPct,
    ddDollar,
    ddAtWorstPct,
    ddPeak,
    scratches,
    tradeConc,
  } = d
  const sharpeEst = run.sharpe == null && fallback.sharpe != null
  const underwater = computeTimeUnderwater(run.daily_pnl ?? [])

  // The headline is the DOLLARS (Aaron's call, 2026-08-01 — "1439.7x on capital doesn't mean
  // anything to me"). The multiple moved to a row beneath it. A multiple is only meaningful once
  // you know what it multiplied, and the starting balance appeared NOWHERE on this page, so as a
  // hero it was a number with no referent. Now the dollars answer "what came out of it" directly
  // and the multiple sits next to the balance it is a multiple OF.
  //
  // ⚠ Keep the caveat on the multiple's tooltip: at a fixed % risk per trade the dollar figure is
  // the number most distorted by compounding — see the Costs row below, where $50k of charged
  // slippage costs $1.6M of net purely because early dollars stop compounding.
  const multiple =
    balance != null && balance > 0 && run.net_pnl != null ? (balance + run.net_pnl) / balance : null
  // The balance the curve actually STARTED from, taken off the curve itself rather than the
  // ruleset — a python run opens on its own deposit, and that is what the multiple divides by.
  const startBal = equity.length > 0 ? (equity[0].equity ?? 0) - (equity[0].profit ?? 0) : null
  // What friction actually cost. Only meaningful since runs can be priced (2026-08-01); a run
  // that stated no costs sums to 0, which is "nothing was priced", not "trading was free".
  const costsTotal = equity.reduce((t, e) => t + (e.costs_usd ?? 0), 0)

  const fmtMoney = (x: number) => dollar(x, true)
  const fmtRatio = (x: number) => `${x >= 0 ? '+' : ''}${x.toFixed(2)}`
  const fmtPct01 = (x: number) => `${x >= 0 ? '+' : ''}${(x * 100).toFixed(1)}%`
  const fmtPctPt = (x: number) => `${x >= 0 ? '+' : ''}${x.toFixed(1)}%`
  const fmtCount = (x: number) => `${x >= 0 ? '+' : ''}${x}`

  // W/L counts: the backend stores win_count, so use it. Deriving them from the rate (which this
  // did) re-rounds a number that was rounded once already — 0.6338 × 142 lands on 90 here only
  // because the rate happens to carry 4 decimals.
  const wins =
    run.win_count ??
    (run.win_rate != null && run.trade_count != null
      ? Math.round(run.win_rate * run.trade_count)
      : null)
  const losses = wins != null && run.trade_count != null ? run.trade_count - wins : null
  const rr =
    run.avg_win != null && run.avg_loss != null && run.avg_loss !== 0
      ? run.avg_win / Math.abs(run.avg_loss)
      : null

  const madeRows: PanelRow[] = [
    // Net is the HERO now, so it is not repeated here. The multiple takes its place — the same
    // number the hero used to be, demoted because it is only meaningful beside the balance it
    // multiplies, which is now the caption directly above this list.
    {
      key: 'mult',
      label: 'Return on capital',
      value: multiple != null ? `${multiple.toFixed(1)}x` : '—',
      tip: `Final balance ÷ starting balance${startBal != null && startBal > 0 ? ` — what ${dollar(startBal)} became` : ''}. Moves with the Account balance slider, since it is measured against whatever capital you tell it. ⚠ At a fixed % risk per trade this is the number most distorted by compounding: a dollar not earned early is a dollar that never compounds, so a small cost early costs many times itself by the end. Compare strategies in R, not here.`,
    },
    {
      key: 'per',
      label: 'Per trade',
      value: expectancyUsd != null ? dollar(expectancyUsd, true) : '—',
      cls: expectancyUsd != null && expectancyUsd < 0 ? 'text-neg-text' : undefined,
      tip: 'Expectancy: net P&L ÷ trade count — what one average trade was worth. Dollars only; expectancy in R needs the risk taken per trade, which stored trades do not carry.',
      cmp: (k) => k.expectancyUsd,
      fmt: fmtMoney,
    },
    {
      key: 'rr',
      label: 'Avg win / loss',
      value: rr != null ? `${rr.toFixed(2)}:1` : '—',
      tip: `Average winning trade ÷ average losing trade. Together with the win rate this is the whole edge${
        run.avg_win != null && run.avg_loss != null
          ? `: ${dollar(run.avg_win, true)} per win against ${dollar(run.avg_loss)} per loss`
          : ''
      }.`,
      cmp: (k) => k.rrRatio,
      fmt: fmtRatio,
      goodWhen: 'higher',
    },
    {
      key: 'wr',
      label: 'Win rate',
      value: pct(run.win_rate),
      tip: `Share of trades that closed profitable${wins != null && losses != null ? ` — ${wins} wins, ${losses} losses` : ''}. A low win rate is not a fault on its own; read it against the average win/loss above.${scratches != null && scratches > 0 ? ` Read it against the scratch count below too — ${scratches} of these barely moved.` : ''} This run: ${winRateLabel(run.win_rate)}.`,
      cmp: (k) => k.winRate,
      fmt: fmtPct01,
    },
    // The row the win rate needed. A trade that made a sixth of a losing trade counts as a full
    // win above; on the shipped run that is 45 of 111 "winners", every one exiting at the
    // breakeven-stop buffer. Shown as the honest three-way split so the reader gets the shape,
    // not just a count. Each figure carries its own colour (won green, scratched amber, lost red).
    {
      key: 'scr',
      label: 'Won / scratched / lost',
      value:
        scratches != null && wins != null && losses != null && run.trade_count ? (
          <>
            <span className="text-pos-text">{wins - scratches}</span>
            {' / '}
            <span className="text-warn-text">{scratches}</span>
            {' / '}
            <span className="text-neg-text">{losses}</span>
          </>
        ) : (
          '—'
        ),
      tip: `The win rate above counts any trade that closed a cent up as a win. A SCRATCH is one whose result came to less than ${Math.round(SCRATCH_FRACTION * 100)}% of this run's median losing trade — usually a stop moved to breakeven doing exactly its job, which is real risk control and is not an edge.${
        scratches != null && wins != null && run.trade_count
          ? ` Here ${pct((wins - scratches) / run.trade_count)} genuinely won, ${pct(scratches / run.trade_count)} scratched.`
          : ' No losing trade in this run, so there is no scale to measure a scratch against.'
      }`,
    },
    {
      key: 'pf',
      label: 'Profit factor',
      value: kpiNum(pfValue),
      // Exception: below 1.0 the strategy loses money — the one PF value that must shout.
      cls: pfValue != null && isFinite(pfValue) && pfValue < 1 ? 'text-neg-text' : undefined,
      tip: `Gross wins ÷ gross losses. Above 2.0 is strong, 1.5 good, below 1.0 loses money. This run: ${pfLabel(pfValue)}.`,
      cmp: (k) => k.pfValue,
      fmt: fmtRatio,
    },
    // Costs were charged but INVISIBLE until 2026-08-01: the run row carried the settings and
    // nothing reported what they came to. The row only appears on a priced run — printing
    // "$0" on every unpriced one would read as "trading was free" rather than "nothing was
    // priced".
    //
    // ⚠ **It is called FEES, not "costs", because it is not the number the Net above moved by.**
    // The fees are what left the account; the Net moves by far more, since a fee paid early also
    // costs everything it would have compounded into. Measured on run `75ccc776d10c`: $332,371 of
    // fees, $18,200,741 off the final balance — 55x. Naming this row "Costs charged" invited
    // exactly the subtraction that makes those two look like a contradiction, and it was reported
    // as a bug from the screen. The tooltip states the relationship rather than leaving it implied.
    ...(costsTotal !== 0
      ? [
          {
            key: 'costs',
            label: 'Fees charged',
            value: dollar(costsTotal),
            tip: `Commission, spread, slippage and swap actually handed to the broker across every fill, already deducted from Net above. ⚠ This is NOT the amount the Net moved by, and the gap is usually large: at a fixed % risk the account compounds, so a dollar of fee paid early also costs every dollar it would have grown into over every trade after it. Expect the balance impact to be many times this figure — that is compounding, not a bigger fee. ⚠ It also cannot tell you about the setups that never filled, which real fills remove. The honest answer to what friction cost is the free twin of this run — the "Run this free" button on the Performance header — never a subtraction from this figure.`,
          } as PanelRow,
        ]
      : []),
    // WHICH costs were charged, not just what they came to. A run that charged nothing and a run
    // made before the switches existed look identical from the total alone — and this lab's
    // recurring defect is exactly a number on screen whose provenance nothing states. `null`
    // means "made before layered costs", which is not the same answer as "charged nothing".
    ...(run.cost_layers != null
      ? [
          {
            key: 'costlayers',
            label: 'Costs charged for',
            value: run.cost_layers.length
              ? run.cost_layers.map((l) => COST_LAYER_LABEL[l] ?? l).join(', ')
              : 'nothing',
            tip: run.cost_layers.length
              ? `The cost layers this run had switched on${run.broker_profile ? `, priced off the ${brokerName(run.broker_profile)} account` : ''}. Anything not listed was not charged at all.`
              : 'This run was deliberately frictionless — no spread, no swap, no commission, no slippage. ⚠ It is a GROSS figure: a diagnostic for how much of the edge is friction, never an answer to whether the strategy works. It is also not comparable trade-for-trade to a charged run, because real fills change which setups exist rather than only what they pay. Charged is the default since 2026-08-24; use the "Run this charged" button on the Performance header for the tradeable twin.',
          } as PanelRow,
        ]
      : []),
  ]

  const riskedRows: PanelRow[] = [
    {
      key: 'dd$',
      label: 'Deepest drop',
      value: ddDollar != null ? `−${dollar(ddDollar)}` : '—',
      tip: `The largest peak-to-trough fall measured in dollars. On a compounding run this is usually a DIFFERENT episode from the percentage above — a later, shallower fall off a much bigger account${
        ddDollar != null && maxDdPct != null && ddAtWorstPct != null && ddDollar > ddAtWorstPct
          ? `. Here the worst percentage cost ${dollar(ddAtWorstPct)} while the worst dollar figure is ${dollar(ddDollar)}`
          : ''
      }. The percentage is what would have ended the account; this is what it would have felt like.`,
      cmp: (k) => k.ddDollar,
      fmt: fmtMoney,
      goodWhen: 'lower',
    },
    {
      key: 'wd',
      label: 'Worst day',
      value: dollar(worstDay),
      tip: 'The single worst calendar day, summing every trade that closed on it.',
      cmp: (k) => k.worstDay,
      fmt: fmtMoney,
    },
    // The unit is TRADES. backtest/output.py:_worst_losing_streak walks the trade list, not the
    // day list — it was labelled "days" here, which on a strategy trading twice a month reads as
    // a far worse run of luck than it was (4 losing trades spanned 2 consecutive losing days).
    // Exception at ≥6 only: 3 losses in a row is ordinary on a selective strategy, and colouring
    // it would make the amber mean nothing by the time a real streak showed up.
    {
      key: 'ws',
      label: 'Worst streak',
      value: worstStreak != null ? `${worstStreak} trades` : '—',
      cls: worstStreak != null && worstStreak >= 6 ? 'text-neg-text' : undefined,
      tip: 'The longest run of consecutive losing trades. Counted in trades, not days — a selective strategy can take weeks to produce four of them.',
      cmp: (k) => k.worstStreak,
      fmt: fmtCount,
      goodWhen: 'lower',
    },
    {
      key: 'uw',
      label: 'Time underwater',
      value: underwater != null ? `${(underwater * 100).toFixed(0)}%` : '—',
      tip: "Share of the test's calendar span spent below the previous equity high. Max drawdown says how deep the hole was; this says how long you sat in it — the half that decides whether a strategy is holdable.",
      goodWhen: 'lower',
    },
  ]

  const trustedRows: PanelRow[] = [
    {
      key: 'conc',
      label: 'Profit concentration',
      value: profitConc != null ? `${profitConc.toFixed(0)}%` : '—',
      // Exception: ≥60% in one quarter is the classic curve-fit signal.
      cls: exceptionCls(concentrationCls(profitConc)),
      tip: `Share of gross profit earned in the single best quarter of the test span. Above 60% the edge is clustered in one window rather than repeatable — the classic curve-fit signal. Measured in returns, not dollars: on a compounding account the last quarter holds most of the dollars however evenly the edge is spread.${profitConc != null ? ` This run: ${concentrationLabel(profitConc)}.` : ''}`,
      cmp: (k) => k.profitConc,
      fmt: fmtPctPt,
      goodWhen: 'lower',
    },
    // The row above splits the span into QUARTERS, so it answers "did the edge show up in one
    // period". Readers hear the trade question, and the two can disagree completely: run
    // f866873aa862 is 34% by quarter (spread evenly over 6.6 years) while 5 of its 165 trades
    // made 47% of everything won. Not a defect on its own — a runner-based strategy is supposed
    // to be fat-tailed — but it is what says the edge lives in the tail.
    {
      key: 'tconc',
      label: `Top ${TRADE_CONCENTRATION_TOP_N} trades`,
      value: tradeConc != null ? `${tradeConc.toFixed(0)}%` : '—',
      cls: tradeConc != null && tradeConc >= 50 ? 'text-warn-text' : undefined,
      tip: `Share of gross profit made by the ${TRADE_CONCENTRATION_TOP_N} biggest winners. The row above asks whether the edge clustered in one PERIOD; this asks whether it came from a handful of TRADES, and a run can be spread evenly across the years while resting on five of them. High is not automatically bad — a strategy that rides runners is meant to be fat-tailed — but it tells you the edge lives in the tail, so size the risk for that.${tradeConc != null ? ` This run: ${tradeConcentrationLabel(tradeConc)}.` : ''}`,
      goodWhen: 'lower',
    },
    {
      key: 'sharpe',
      label: 'Sharpe',
      value: sharpe != null ? sharpe.toFixed(2) : '—',
      // Amber below 1.0 — an EXCEPTION colour, not a sign colour. Green for "positive" would
      // call 0.91 good; amber for "weak" is the threshold that should stop you, which is the
      // policy every other coloured row here follows.
      cls: sharpe != null && sharpe < 1 ? 'text-warn-text' : undefined,
      tip: `Return per unit of volatility, annualized from daily P&L. Above 2 is excellent, 1 is good, below 0.5 is poor. Every weekday in the run's span counts, flat days included as zero — a strategy that trades 20 days a year is not a 250-day strategy, and scoring only its active days inflated this figure roughly 3x (0.91 read as 2.98 until 2026-07-31). This run: ${sharpe != null ? sharpeLabel(sharpe, sharpeEst) : 'not computed'}.`,
      cmp: (k) => k.sharpe,
      fmt: fmtRatio,
    },
    {
      key: 'z',
      label: 'Z-score',
      value: zScore != null ? zScore.toFixed(2) : '—',
      cls: exceptionCls(zScoreCls(zScore)),
      tip: `Wald–Wolfowitz runs test on the win/loss sequence: does it streak more than chance? Near 0 means the order looks random, which is what an honest edge produces. Past ±2 the wins and losses clump, and an equity curve built on clumps is fragile. This run: ${zScore != null ? zScoreLabel(zScore) : zScoreUnavailableLabel(equity)}.`,
      cmp: (k) => k.zScore,
      fmt: fmtRatio,
      goodWhen: 'none',
    },
    {
      key: 'dur',
      label: 'Avg hold',
      value: fmtHold(run.avg_trade_duration_min),
      tip: 'Average time a position was open, entry to exit. Read it against the bar size — a hold of a few bars is a different strategy from one that carries overnight.',
      cmp: (k) => k.avgDur,
      fmt: (x: number) => `${x >= 0 ? '+' : ''}${fmtHold(Math.abs(x))}`,
      goodWhen: 'none',
    },
  ]

  // The delta answers the question the news filter was opened to ask, so it is the one thing
  // allowed to sit beside a value. Rows that did not move say nothing — printing "unchanged vs
  // unfiltered" on every row was eight lines of text to communicate that nothing happened.
  const rowDelta = (r: PanelRow): React.ReactNode => {
    if (!dc || !r.cmp) return null
    const to = r.cmp(d),
      from = r.cmp(dc)
    if (to == null || from == null || !isFinite(to) || !isFinite(from)) return null
    const delta = to - from
    if (Math.abs(delta) < 1e-9) return null
    const good = r.goodWhen === 'lower' ? delta < 0 : delta > 0
    const cls =
      r.goodWhen === 'none' ? 'text-text-secondary' : good ? 'text-pos-text' : 'text-neg-text'
    return <span className={`${cls} tabular-nums`}> {(r.fmt ?? fmtRatio)(delta)}</span>
  }

  const rows = (list: PanelRow[]) => <PanelRows rows={list} delta={rowDelta} />

  // Hero delta: shown beside the big number, in the unit that number is stated in.
  const heroDelta = (
    to: number | null | undefined,
    from: number | null | undefined,
    fmt: (x: number) => string,
    goodWhen: 'higher' | 'lower'
  ) => {
    if (!dc) return null
    if (to == null || from == null || !isFinite(to) || !isFinite(from)) return null
    const delta = to - from
    if (Math.abs(delta) < 1e-9)
      return <span className="text-[12px] text-text-tertiary">unchanged</span>
    const good = goodWhen === 'lower' ? delta < 0 : delta > 0
    return (
      <span className={`text-[12px] tabular-nums ${good ? 'text-pos-text' : 'text-neg-text'}`}>
        {fmt(delta)}
      </span>
    )
  }

  const cardCls = (top: string) => panelCardCls(collapsed, filtered, top)
  const head = (title: string, question: string, aside?: React.ReactNode) => (
    <CardHead title={title} question={question} aside={aside} />
  )
  const hero = (value: React.ReactNode, unit: React.ReactNode, cls: string, tip: string) => (
    <CardHero value={value} unit={unit} cls={cls} tip={tip} />
  )

  const madeTip =
    'Total profit and loss in dollars across every closed trade, after whatever commission and slippage the run was priced with. The starting balance is beneath it and the multiple is the first row, so what this grew FROM is on screen. ⚠ Dollars on a compounding account are not comparable between runs — a fixed % risk per trade makes the end figure exponential in the edge, so a small change early shows up as a huge change here. Rank strategies by R or profit factor; read this to know what the run was worth.'
  const riskedTip =
    "Worst peak-to-trough drop as a % of the equity it fell FROM — the drawdown that would actually have ended the account. Measured against the running peak, not the starting balance: on a compounding run the account grows away from its opening capital, so dividing a late dollar drawdown by a static account_size reports a percentage that never happened (this read 1096.7% before 2026-07-30). The bar's gold tick is the selected ruleset's stated limit; the hatched extension past the fill is the worst-1% drawdown the stress test simulated. Each is drawn only when it actually exists. The DENOMINATOR is the Account balance in the params panel — the evaluated ruleset's account size, or the run's own opening balance when it was graded against none — so this figure moves with that slider while the dollars beside it do not."
  const trustedTip = `Annualized return (CAGR) ÷ worst peak-relative drawdown — return earned per unit of pain. Both halves compound, so this DOES move with the Account balance slider; they do not cancel. Above 2 is strong, below 0.5 weak.${d.recoveryFactor != null ? ` Its dollar twin, annualized net P&L ÷ deepest dollar drawdown, is ${d.recoveryFactor.toFixed(2)} (the old Recovery Factor).` : ''} The rows beneath are the reasons to distrust the number above them: profit clustered in one quarter, a soft Sharpe, or streaking that isn't random.`

  // Four cards when a verdict joins the row, three otherwise. The verdict is narrower because it
  // carries one number and a short rule list where the others carry five figures and a meter —
  // and every point it gives back is a point the three that do the reading get to keep.
  // The narrowing is weighted only from xl, where the verdict card lands at ~285px. Between lg
  // and xl it takes an EQUAL quarter instead: weighted there it would sit near 148px, and the
  // longest real rule label ("Daily DD ≤ $5,000") measures 118px + its ⓘ and tick, so it would
  // truncate to nothing useful. Below lg the row breaks to two — four across a laptop-width
  // column is not a card, it's a column of stumps.
  const grid = verdict
    ? 'md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-[0.8fr_1fr_1fr_1fr]'
    : 'md:grid-cols-3'

  return (
    <div className="space-y-2.5">
      {ribbon}
      <div className={`grid gap-2.5 items-stretch ${grid}`}>
        {/* First, not last: the grade and the sample size are what you check BEFORE reading the
            three numbers to their right, and it inherits the position the ribbon's own verdict
            chip held at the panel's top-left. */}
        {verdict}

        {/* The three result cards share ONE neutral top edge (2026-09-11). Each carried a fixed
            colour — green over MADE even when the run lost money — which is colour on identity,
            not on the result. The hero number carries the verdict; the Verdict card's edge still
            follows a real pass / warn / discard. */}
        <div className={cardCls('border-t-2 border-t-border-strong')}>
          {head('Made', 'What came out of it')}
          {hero(
            <FitMoney n={run.net_pnl} signed />,
            'net',
            (run.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text',
            madeTip
          )}
          {dc && <div className="mb-1">{heroDelta(d.netPnl, dc.netPnl, fmtMoney, 'higher')}</div>}
          {/* The starting balance, which this page never stated anywhere — so "1439.7x" was a
              multiple of a number the reader could not see. It is a caption, not a row: it is
              the run's INPUT, not a result, and it survives the collapse for the same reason
              (the multiple in the rows below is meaningless without it). */}
          {startBal != null && startBal > 0 && (
            <div className="mt-2 mb-1 font-mono text-[11px] text-text-tertiary">
              from {dollar(startBal)}
            </div>
          )}
          {!collapsed && rows(madeRows)}
        </div>

        <div className={cardCls('border-t-2 border-t-border-strong')}>
          {head(
            'Risked',
            'What it cost to hold',
            limitPct != null ? (
              <span className="font-mono text-[10px] text-gold-text">
                vs {limitPct.toFixed(0)}% limit
              </span>
            ) : (
              <span className="text-[10px] text-text-tertiary">no limit set</span>
            )
          )}
          {hero(
            maxDdPct != null ? `${maxDdPct.toFixed(1)}%` : '—',
            'worst drawdown',
            maxDdPct != null ? 'text-neg-text' : 'text-text-tertiary',
            riskedTip
          )}
          {/* The meter survives the collapse — it is the only thing on the page that says
              whether a drawdown number is acceptable, and it costs ~40px. */}
          {maxDdPct != null ? (
            <DrawdownMeter pct={maxDdPct} limitPct={limitPct} tailPct={tailPct} />
          ) : (
            /* This used to read "Set an account balance to measure drawdown as a percentage" on
               every run with no evaluated ruleset — an instruction the page gave no way to follow,
               since the slider only renders once a default exists. The default now falls back to
               the run's OWN opening balance, so the only case left is a run with no equity curve
               at all, and the honest wording says that rather than asking for an input. */
            <div className="mt-3.5 text-[11px] text-text-tertiary">
              This run stored no equity curve, so a drawdown percentage cannot be measured.
            </div>
          )}
          {!collapsed && (
            <div className="text-[10.5px] text-text-tertiary leading-[1.35] mt-1.5">
              {maxDdPct != null && ddAtWorstPct != null && ddPeak != null ? (
                <>
                  −{dollar(ddAtWorstPct)} off a {dollar(ddPeak)} peak.{' '}
                </>
              ) : null}
              {limitPct != null &&
                maxDdPct != null &&
                (maxDdPct >= limitPct ? (
                  <span className="text-neg-text">Breaches the {limitPct.toFixed(0)}% limit. </span>
                ) : (
                  <>Clears by {(limitPct - maxDdPct).toFixed(1)} pts. </>
                ))}
              {tailPct != null ? (
                <>Worst-1% simulated: {tailPct.toFixed(1)}%.</>
              ) : (
                <>No stress test — the tail is unknown, not zero.</>
              )}
            </div>
          )}
          {!collapsed && rows(riskedRows)}
        </div>

        <div className={cardCls('border-t-2 border-t-border-strong')}>
          {/* No trade count here — it is the verdict card's hero, two columns across. Printing
              it twice on one row made the second copy read as a different number. */}
          {head('Trusted', 'Whether to believe it')}
          {hero(kpiNum(calmar), 'Calmar', calmarCls(calmar), trustedTip)}
          {dc ? (
            <div className="mb-1">{heroDelta(d.calmar, dc.calmar, fmtRatio, 'higher')}</div>
          ) : (
            <div className="text-[11px] text-text-tertiary leading-snug mt-2">
              {calmarLabel(calmar)}
            </div>
          )}
          {!collapsed && rows(trustedRows)}
        </div>
      </div>
    </div>
  )
}
// ── Regime overlay — colored line design ──────────────────────────────────────
// The preference lives with its control (`components/RegimeOverlayToggle` → `useRegimeOverlay`),
// not here: this page's private copy was one of three, and the other two never persisted at all.

// Per-series equity-chart toggles (histogram / excursions / run-ups & drawdowns). Default OFF so the
// chart stays clean until the user opts in; each persists like the regime overlay.
export function getBoolPref(key: string): boolean {
  try {
    return localStorage.getItem(key) === 'true'
  } catch {
    return false
  }
}
export function setBoolPref(key: string, v: boolean) {
  try {
    localStorage.setItem(key, String(v))
  } catch {
    /* quota */
  }
}
export const _HIST_KEY = 'equity_histogram_enabled'
export const _RUD_KEY = 'equity_runup_drawdown_enabled'

// Performance panel collapse. Defaults COLLAPSED (hence its own getter — getBoolPref defaults
// off): expanded, the panel plus its header fills the fold on a laptop and pushes the equity
// curve entirely off screen, and the headline and the curve are read together. The three hero
// numbers and the drawdown meter survive the collapse, so the default still answers "how did
// this run do" without a click.
export const _PERF_COLLAPSED_KEY = 'performance_panel_collapsed'
export function getPerfCollapsed(): boolean {
  try {
    return localStorage.getItem(_PERF_COLLAPSED_KEY) !== 'false'
  } catch {
    return true
  }
}

/** ONE preference behind ONE key, shared by this page and StackDetail. A stack renders the same
 *  panel, so a second copy of this state would mean the same control remembered two answers
 *  depending on which page you last pressed it on. */
export function usePerfCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(getPerfCollapsed)
  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem(_PERF_COLLAPSED_KEY, String(next))
      } catch {
        /* quota */
      }
      return next
    })
  }, [])
  return [collapsed, toggle]
}

/** The section header's collapse control. Shared so a stack's Performance section and a run's are
 *  the same control — same words, same chevron, same hit area — rather than two look-alikes. */
export function PerfCollapseToggle({
  collapsed,
  onToggle,
  suffix,
}: {
  collapsed: boolean
  onToggle: () => void
  suffix?: React.ReactNode
}) {
  return (
    <button
      onClick={onToggle}
      title={collapsed ? 'Show the supporting metrics' : 'Show only the headline numbers'}
      // A declared TEST SEAM. The suffix is the page's only statement of what the numbers under it
      // count, and a page-wide text match for "N of M trades" also finds the news pill's own
      // wording — the vacuous-pass trap this folder has recorded five times.
      data-testid="perf-collapse-toggle"
      className="flex items-center gap-1.5 text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] transition-colors hover:text-text-primary"
    >
      <ChevronDown size={13} className={`transition-transform ${collapsed ? '-rotate-90' : ''}`} />
      Performance
      {suffix}
    </button>
  )
}

export interface RegimeBand {
  x1: number
  x2: number
  regime: string
}

// Run-ups & drawdowns ribbon: each point is a "run-up" (equity at/above its running peak — green)
// or a "drawdown" (below the prior peak — red). Contiguous same-state points merge into one band;
// TradingView draws this as a thin colour strip along the bottom of the equity panel.
export interface RudBand {
  x1: number
  x2: number
  up: boolean
}
export function computeRunupDrawdownBands(
  data: EquityPoint[],
  xOf: (p: EquityPoint) => number
): RudBand[] {
  const bands: RudBand[] = []
  let peak = -Infinity
  let cur: RudBand | null = null
  for (const pt of data) {
    const up = pt.equity >= peak
    if (up) peak = pt.equity
    const x = xOf(pt)
    if (!cur || cur.up !== up) {
      cur = { x1: x, x2: x, up }
      bands.push(cur)
    } else {
      cur.x2 = x
    }
  }
  for (let i = 0; i < bands.length - 1; i++) bands[i].x2 = bands[i + 1].x1
  return bands
}

// Same idea, but indexed by the sized timeline's day position — the SizedEquityCurveChart
// plots on day-index i, not the equity curve's trade index, so it needs its own bands.
export function computeSizedRegimeBands(
  timeline: SizedTimelineDay[],
  dailyPnl: DailyPnlPoint[]
): RegimeBand[] {
  const dateToRegime = new Map<string, string>()
  for (const d of dailyPnl) dateToRegime.set(d.date, d.regime_tag ?? 'UNKNOWN')
  const bands: RegimeBand[] = []
  let cur: RegimeBand | null = null
  timeline.forEach((day, i) => {
    const dateKey = day.date?.slice(0, 10)
    const regime = dateKey ? (dateToRegime.get(dateKey) ?? 'UNKNOWN') : 'UNKNOWN'
    if (!cur || cur.regime !== regime) {
      cur = { x1: i, x2: i, regime }
      bands.push(cur)
    } else {
      cur.x2 = i
    }
  })
  for (let i = 0; i < bands.length - 1; i++) bands[i].x2 = bands[i + 1].x1
  return bands
}

// Drop the dead flat tail after trading stops. A breached account freezes its balance for the
// rest of the requested date range, which otherwise draws a long flat line to the end (and pads
// the timeline table with hundreds of no-trade rows). End the sized view at the last day that
// actually traded, so the chart stops where trading stopped.
export function trimToLastActive(tl: SizedTimelineDay[]): SizedTimelineDay[] {
  let last = -1
  for (let i = tl.length - 1; i >= 0; i--) {
    if (tl[i].trades_taken > 0) {
      last = i
      break
    }
  }
  return last >= 0 ? tl.slice(0, last + 1) : tl
}

// ── Equity curve ──────────────────────────────────────────────────────────────

export function fmtChartDate(d?: string): string {
  if (!d) return ''
  const dt = new Date(d.slice(0, 10) + 'T12:00:00')
  const yr = String(dt.getFullYear()).slice(-2)
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ` '${yr}`
}

export const _money0 = (v: number) =>
  `${v >= 0 ? '+' : '−'}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`

export const DAY_MS = 86_400_000

export function EquityCurveChart({
  data,
  bands = [],
  showHistogram = false,
  showRunupDrawdown = false,
  height = 300,
  xMode = 'date',
  windowStart = null,
  overlayLines = [],
  markers = [],
}: {
  data: EquityPoint[]
  /** Vertical marks for events that moved the balance WITHOUT being a trade — a broker account's
   *  deposits and withdrawals. `tradeIndex` is the first trade after the event, which is where the
   *  mark sits in trade mode. Empty for a backtest, which has no such events. */
  markers?: { date: string; tradeIndex: number; label: string; color: string }[]
  bands?: RegimeBand[]
  showHistogram?: boolean
  showRunupDrawdown?: boolean
  height?: number
  /** Extra lines drawn on top of the main equity curve, keyed on a field the caller has already
   *  attached to each `data` point (so they share the exact x-axis in both date and trade mode).
   *  Used by the portfolio stack to overlay a line per strategy. Empty for a single backtest. */
  overlayLines?: { id: string; color: string; name?: string }[]
  /** 'date' (default) plots the real calendar — quiet months look quiet, regime bands get their
   *  true width, and the tuning workbench's overlay traces the identical path. 'trade' spaces every
   *  trade evenly, which is the view for per-trade forensics (streaks, excursions). */
  xMode?: XMode
  /** Run window start — where the starting-balance anchor sits in 'date' mode (the account existed
   *  from the window opening, not from the first trade). Falls back to a day before trade #1. */
  windowStart?: string | null
}) {
  if (!data.length) return null

  // Runs from the Python runner carry per-trade excursion (favorable/adverse). When present, the
  // bottom-bar toggle draws the combined TradingView-style excursion bar; otherwise plain profit bars.
  const hasExc = data.some((d) => d.favorable != null || d.adverse != null)
  const showExcursions = showHistogram && hasExc
  const showProfitBars = showHistogram && !hasExc

  // Break-even = the STARTING BALANCE, not the first trade's equity. The curve is anchored on the
  // account's opening balance and the first point already includes trade #1's P&L, so subtract it
  // back out: startEq = opening balance. Green above it, red below, and the flip lands exactly on
  // this horizontal line — regardless of what the starting balance is.
  const startEq = (data[0]?.equity ?? 0) - (data[0]?.profit ?? 0)
  // Anchor the curve on the STARTING BALANCE: prepend a synthetic point at the opening balance so
  // the line visibly leaves the start line (TradingView does this). The anchor carries no trade —
  // it draws no dot, no histogram bar, and its tooltip just reports the starting balance.
  const byDate = xMode === 'date'
  const firstIdx = data[0]?.index ?? 1
  const firstMs = dateMs(data[0]?.date) ?? Date.now()
  // `x` is the plotted position: a real timestamp in date mode, the trade number otherwise. Every
  // band/ribbon below is expressed in the same units, so switching mode moves the whole chart
  // together.
  const anchorX = byDate
    ? Math.min(dateMs(windowStart) ?? firstMs - DAY_MS, firstMs - DAY_MS)
    : firstIdx - 1
  const chartData: (EquityPoint & { _anchor?: boolean; x: number })[] = [
    // The anchor also seeds every overlay line at the starting balance, so the strategy lines leave
    // the same origin as the portfolio line instead of appearing to start at their first trade.
    {
      index: firstIdx - 1,
      equity: startEq,
      _anchor: true,
      x: anchorX,
      ...Object.fromEntries(overlayLines.map((ol) => [ol.id, startEq])),
    },
    ...data.map((d) => ({ ...d, x: byDate ? (dateMs(d.date) ?? firstMs) : d.index })),
  ]
  // Overlay values count toward the y-range too — a strategy line can dip below the portfolio's low.
  const allValues = [
    ...data.map((d) => d.equity),
    ...overlayLines.flatMap((ol) =>
      data
        .map((d) => (d as unknown as Record<string, unknown>)[ol.id])
        .filter((v): v is number => typeof v === 'number')
    ),
  ]
  const min = Math.min(...allValues)
  const max = Math.max(...allValues)
  const pad = (max - min) * 0.1 || 500
  const yMin = Math.min(startEq, min) - pad
  const yMax = max + pad

  // The colour-split offset must map to the FILLED SHAPE's bounding box — the data extremes incl.
  // startEq, NOT the padded axis domain. Using the padded domain drifts the green/red boundary off
  // the start line and bleeds a faint red tint into the positive region.
  // ⚠ The BALANCE line's own values only: an overlay line below it (a growth line, a strategy leg)
  // widened this range and moved the split off the start line, painting a winning curve red.
  const eqValues = data.map((d) => d.equity)
  const dMin = Math.min(startEq, ...eqValues)
  const dMax = Math.max(startEq, ...eqValues)
  const startOffset = Math.min(1, Math.max(0, (dMax - startEq) / (dMax - dMin || 1)))
  const eqTicks = byDate
    ? monthTicks(anchorX, chartData[chartData.length - 1].x)
    : calIndexTicks(data)

  // Y ticks anchored ON the starting balance so it's always labelled, evenly spaced around it.
  const yTicks = balanceTicks(startEq, yMin, yMax)

  // Profit histogram rides its own hidden axis, scaled to a bottom strip: domain [-barMax, 6×barMax]
  // puts the zero baseline ~14% up so green bars rise and red bars drop within the bottom band.
  const barMax = showProfitBars ? Math.max(1, ...data.map((d) => Math.abs(d.profit ?? 0))) : 1

  // Run-up / drawdown ribbon segments, and a thin band at the very bottom of the plot to draw it in.
  // Pull the first segment left to the anchor so the ribbon spans the full axis (the curve starts at
  // the anchor point, one step left of the first trade).
  const rudBands = showRunupDrawdown
    ? computeRunupDrawdownBands(data, (d) => (byDate ? (dateMs(d.date) ?? firstMs) : d.index))
    : []
  if (rudBands.length) rudBands[0].x1 = anchorX

  // Regime bands must span the WHOLE plot. The curve starts at the anchor (a step left of trade #1
  // in trade mode, the window open in date mode), but the bands are built from trading days — so
  // without this the strip before the first band renders uncoloured, reading as "no regime here"
  // when really the market had one and the run just hadn't traded yet. Same at the right edge.
  // FILTER FIRST, then stretch: UNKNOWN bands are dropped from the render, so stretching before
  // the filter could hand the extension to a band that never draws — leaving the leading strip
  // uncoloured anyway (a gap one or two trades wide, which is why it looked size-dependent).
  const lastX = chartData[chartData.length - 1].x
  const shown = bands.filter((b) => b.regime !== 'UNKNOWN')
  const plotBands = shown.map((b, i) => ({
    ...b,
    x1: i === 0 ? Math.min(b.x1, anchorX) : b.x1,
    x2: i === shown.length - 1 ? Math.max(b.x2, lastX) : b.x2,
  }))
  const rudY2 = yMin + (yMax - yMin) * 0.025

  return (
    <ResponsiveContainer
      key={`${bands.length}-${showHistogram}-${showExcursions}-${showRunupDrawdown}-${xMode}`}
      width="100%"
      height={height}
    >
      <ComposedChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <defs>
          {/* Line stroke: green above break-even, red below, hard edge at the start-balance offset. */}
          <linearGradient id="eqStroke" x1="0" y1="0" x2="0" y2="1">
            <stop offset={startOffset} stopColor={C.pos} />
            <stop offset={startOffset} stopColor={C.neg} />
          </linearGradient>
          {/* Fill: green above the start line, red below, hard edge at the same offset. Kept out of
              the positive region above the split so there's no red tint where the account is up. */}
          <linearGradient id="eqFillSplit" x1="0" y1="0" x2="0" y2="1">
            <stop offset={0} stopColor={C.pos} stopOpacity={0.22} />
            <stop offset={Math.max(0, startOffset - 0.0001)} stopColor={C.pos} stopOpacity={0.03} />
            <stop offset={startOffset} stopColor={C.neg} stopOpacity={0.03} />
            <stop offset={1} stopColor={C.neg} stopOpacity={0.2} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
        {/* Regime context as faint full-height background bands — skip UNKNOWN so the chart shows
            exactly the regimes in the legend (a run tags only the regimes it actually saw). */}
        {plotBands.map((b, i) => (
          // ifOverflow="visible": the first/last band are deliberately pushed to the plot edges, and
          // Recharts' default is to DISCARD a reference area whose bound sits outside the domain.
          <ReferenceArea
            key={`r${i}`}
            x1={b.x1}
            x2={b.x2}
            ifOverflow="visible"
            fill={REGIME_COLORS[b.regime] ?? REGIME_COLORS.UNKNOWN}
            fillOpacity={0.1}
            stroke="none"
          />
        ))}
        <XAxis
          dataKey="x"
          ticks={eqTicks}
          // Date mode: a true time axis (regime bands then span their real calendar width).
          // Trade mode: point scale keeps the line flush to the axis whether or not the histogram
          // bars are on — a bar series otherwise switches the axis to band scale, which pads both
          // sides and shifts the curve right, opening a gap between the y-axis and the start line.
          {...(byDate
            ? {
                type: 'number' as const,
                scale: 'time' as const,
                domain: ['dataMin', 'dataMax'] as [string, string],
              }
            : { scale: 'point' as const })}
          padding={{ left: 0, right: 0 }}
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => {
            if (byDate) return monthLabel(v)
            const date = data[v - 1]?.date
            if (!date) return ''
            return calTickLabel(date, v === data[0].index || v === data[data.length - 1].index)
          }}
        />
        <YAxis
          domain={[yMin, yMax]}
          ticks={yTicks}
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          // Account balance, not a gain — no "+" prefix. The starting balance is always one of these.
          tickFormatter={balTick}
          width={56}
        />
        {/* Hidden axis for the bottom bar strip: zero baseline ~14% up so bars hug the bottom. */}
        <YAxis yAxisId="bars" hide domain={[-barMax, barMax * 6]} />
        {/* Hidden axis for excursion bars: the balance axis shifted so its zero lands exactly on the
            starting-balance line, in real dollars — the bars sit on the same baseline as the curve. */}
        <YAxis yAxisId="exc" hide domain={[yMin - startEq, yMax - startEq]} />
        {/* Custom tooltip: equity + (when present) favorable/adverse excursion for the trade. */}
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const eq =
              payload.find((p: { dataKey?: string | number }) => p.dataKey === 'equity') ??
              payload[0]
            if (!eq) return null
            const pt = (eq as { payload?: EquityPoint & { _anchor?: boolean } }).payload
            const v = (eq as { value?: number }).value ?? 0
            if (pt?._anchor)
              return (
                <div
                  style={{
                    background: C.tooltipBg,
                    border: `1px solid ${C.tooltipBorder}`,
                    borderRadius: 8,
                    fontSize: 13,
                    padding: '8px 12px',
                  }}
                >
                  <p style={{ color: C.axisTick, marginBottom: 4 }}>Starting balance</p>
                  <p style={{ color: '#e5e7eb' }}>
                    ${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                  </p>
                </div>
              )
            const dateStr = pt?.date ? ` · ${fmtChartDate(pt.date)}` : ''
            const dirStr = pt?.direction ? ` · ${pt.direction}` : ''
            const hasFav = pt?.favorable != null || pt?.adverse != null
            return (
              <div
                style={{
                  background: C.tooltipBg,
                  border: `1px solid ${C.tooltipBorder}`,
                  borderRadius: 8,
                  fontSize: 13,
                  padding: '8px 12px',
                }}
              >
                <p style={{ color: C.axisTick, marginBottom: 4 }}>
                  Trade #{pt?.index}
                  {dateStr}
                  {dirStr}
                </p>
                <p style={{ color: '#e5e7eb' }}>
                  Balance&nbsp;${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </p>
                {pt?.profit != null && (
                  <p style={{ color: (pt.profit ?? 0) >= 0 ? C.pos : C.neg }}>
                    This trade&nbsp;{_money0(pt.profit)}
                  </p>
                )}
                {hasFav && (
                  <>
                    <p style={{ color: C.pos }}>
                      Favorable excursion&nbsp;{_money0(pt?.favorable ?? 0)}
                    </p>
                    <p style={{ color: C.neg }}>
                      Adverse excursion&nbsp;{_money0(pt?.adverse ?? 0)}
                    </p>
                  </>
                )}
              </div>
            )
          }}
        />
        <ReferenceLine y={startEq} stroke={C.refLine} strokeDasharray="4 4" />
        {markers.map((m, i) => (
          <ReferenceLine
            key={`mk${i}`}
            x={byDate ? (dateMs(m.date) ?? undefined) : m.tradeIndex}
            stroke={m.color}
            strokeDasharray="2 3"
            label={{ value: m.label, fill: m.color, fontSize: 10, position: 'insideTopLeft' }}
          />
        ))}
        {/* Run-ups & drawdowns ribbon: a thin strip along the very bottom, green while the equity is
            making new highs, red while it sits under a prior peak. */}
        {rudBands.map((b, i) => (
          <ReferenceArea
            key={`rud${i}`}
            x1={b.x1}
            x2={b.x2}
            y1={yMin}
            y2={rudY2}
            fill={b.up ? C.pos : C.neg}
            fillOpacity={0.85}
            stroke="none"
          />
        ))}
        {/* Per-trade realised profit histogram (runs without excursion data) — muted so the line reads on top. */}
        {showProfitBars && (
          <Bar yAxisId="bars" dataKey="profit" isAnimationActive={false} maxBarSize={28}>
            {chartData.map((d, i) => (
              <Cell key={i} fill={(d.profit ?? 0) >= 0 ? C.pos : C.neg} fillOpacity={0.35} />
            ))}
          </Bar>
        )}
        {/* Combined trade-excursion bar (TradingView-style): translucent green halo up to the favorable
            excursion, translucent red halo down to the adverse, and a solid net-result core between —
            one bar per trade, in true dollars anchored on the starting-balance line so the bars sit on
            the same baseline as the equity curve. Driven off a hidden bar (exc axis, base 0 = the
            starting-balance line) whose pixel height gives the $-per-pixel scale for the custom shape. */}
        {showExcursions && (
          <Bar
            yAxisId="exc"
            dataKey={(d: EquityPoint) => Math.max(d.favorable ?? 0, -(d.adverse ?? 0), 0)}
            isAnimationActive={false}
            maxBarSize={28}
            shape={(props: {
              x?: number
              y?: number
              width?: number
              height?: number
              payload?: EquityPoint & { _anchor?: boolean }
            }) => {
              const { x = 0, y = 0, width = 0, height = 0, payload } = props
              const fav = payload?.favorable ?? 0
              const adv = payload?.adverse ?? 0
              const profit = payload?.profit ?? 0
              const scale = Math.max(fav, -adv, 0)
              if (payload?._anchor || scale <= 0 || height <= 0) return <g />
              const ppd = height / scale // pixels per dollar (bar spans startEq → startEq+scale)
              const zeroY = y + height // pixel of the starting-balance line
              const w = width // fill the category slot (Recharts already sized it)
              const bx = x
              const favY = zeroY - fav * ppd
              const advY = zeroY - adv * ppd // adv ≤ 0 → below the line
              const profY = zeroY - profit * ppd
              return (
                <g>
                  {fav > 0 && (
                    <rect
                      x={bx}
                      y={favY}
                      width={w}
                      height={zeroY - favY}
                      fill={C.pos}
                      fillOpacity={0.28}
                    />
                  )}
                  {adv < 0 && (
                    <rect
                      x={bx}
                      y={zeroY}
                      width={w}
                      height={advY - zeroY}
                      fill={C.neg}
                      fillOpacity={0.28}
                    />
                  )}
                  {profit >= 0 ? (
                    <rect
                      x={bx}
                      y={profY}
                      width={w}
                      height={Math.max(0, zeroY - profY)}
                      fill={C.pos}
                      fillOpacity={0.6}
                    />
                  ) : (
                    <rect
                      x={bx}
                      y={zeroY}
                      width={w}
                      height={Math.max(0, profY - zeroY)}
                      fill={C.neg}
                      fillOpacity={0.6}
                    />
                  )}
                </g>
              )
            }}
          />
        )}
        <Area
          type="monotone"
          dataKey="equity"
          stroke="url(#eqStroke)"
          strokeWidth={2.5}
          fill="url(#eqFillSplit)"
          // A dot on every trade point (TradingView-style), coloured green/red by whether that point
          // sits above or below the starting balance. A dark stroke ring lifts each dot off the
          // histogram bars so the line takes visual precedence — hover any dot for the excursions.
          dot={(props: {
            cx?: number
            cy?: number
            index?: number
            payload?: EquityPoint & { _anchor?: boolean }
          }) => {
            const { cx, cy, payload, index } = props
            if (cx == null || cy == null || payload?._anchor) return <g key={index} />
            const up = (payload?.equity ?? 0) >= startEq
            return (
              <circle
                key={index}
                cx={cx}
                cy={cy}
                r={3}
                fill={up ? C.pos : C.neg}
                stroke={C.tooltipBg}
                strokeWidth={1}
              />
            )
          }}
          // Hover dot must match the point's own colour (red below the start line, green above) —
          // a fixed colour showed green even on underwater points.
          activeDot={(props: {
            cx?: number
            cy?: number
            index?: number
            payload?: EquityPoint & { _anchor?: boolean }
          }) => {
            const { cx, cy, payload, index } = props
            if (cx == null || cy == null || payload?._anchor) return <g key={index} />
            const up = (payload?.equity ?? 0) >= startEq
            return (
              <circle
                key={index}
                cx={cx}
                cy={cy}
                r={4.5}
                fill={up ? C.pos : C.neg}
                stroke={C.tooltipBg}
                strokeWidth={1.5}
              />
            )
          }}
          baseValue={startEq}
          isAnimationActive={false}
        />
        {/* Per-strategy overlay lines (portfolio stack). Keyed on fields the caller attached to
            each point, so they ride the same x-axis as the main curve. connectNulls skips the
            synthetic start anchor (which carries no overlay values). */}
        {overlayLines.map((ol) => (
          <Line
            key={ol.id}
            type="monotone"
            dataKey={ol.id}
            stroke={ol.color}
            strokeWidth={1.5}
            isAnimationActive={false}
            connectNulls
            // A dot only on the points that are THIS line's own trades — every point carries every
            // leg's running balance, so without the owner check each line would dot on every trade.
            dot={(props: {
              cx?: number
              cy?: number
              index?: number
              payload?: { _legOwner?: string }
            }) => {
              const { cx, cy, payload, index } = props
              if (cx == null || cy == null || payload?._legOwner !== ol.id) return <g key={index} />
              return (
                <circle
                  key={index}
                  cx={cx}
                  cy={cy}
                  r={2.5}
                  fill={ol.color}
                  stroke={C.tooltipBg}
                  strokeWidth={1}
                />
              )
            }}
            activeDot={(props: {
              cx?: number
              cy?: number
              index?: number
              payload?: { _legOwner?: string }
            }) => {
              const { cx, cy, payload, index } = props
              if (cx == null || cy == null || payload?._legOwner !== ol.id) return <g key={index} />
              return (
                <circle
                  key={index}
                  cx={cx}
                  cy={cy}
                  r={4}
                  fill={ol.color}
                  stroke={C.tooltipBg}
                  strokeWidth={1.5}
                />
              )
            }}
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── Sized equity curve (dynamic-sizing engine) ───────────────────────────────
// Day-by-day from the engine's timeline: end-of-day balance vs the trailing risk
// floor (the firm's max-loss line). The gap between them is the buffer the engine
// sized against; balance crossing the floor is a breach. Unlike the per-trade
// equity curve above, this is the REAL sized account — what actually traded.

export function SizedEquityCurveChart({
  data,
  bands = [],
  height = 300,
}: {
  data: SizedTimelineDay[]
  bands?: RegimeBand[]
  height?: number
}) {
  if (!data.length) return null

  const rows = data.map((d, i) => ({
    i,
    date: d.date,
    balance: d.eod_balance,
    floor: d.risk_floor,
    buffer: d.floor_distance,
    trades: d.trades_taken,
    contracts: d.contracts_total,
    halt: d.halt_reason,
  }))

  const startBal = rows[0].balance
  const endBal = rows[rows.length - 1].balance
  const profitable = endBal >= startBal
  const lineColor = profitable ? C.pos : C.neg

  const vals = rows.flatMap((r) => [r.balance, ...(r.floor != null ? [r.floor] : [])])
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const pad = (max - min) * 0.08 || 500

  // Mark days where a breach happened or the engine halted trading.
  const breachIdx = rows.findIndex((r) => r.floor != null && r.balance < r.floor)
  const haltDays = rows.filter((r) => r.halt)

  // X ticks: first, ~quarterly, last (calendar-spaced, matching the other charts).
  const step = Math.max(1, Math.floor(rows.length / 5))
  const xTicks = rows
    .filter((_, i) => i === 0 || i === rows.length - 1 || i % step === 0)
    .map((r) => r.i)

  return (
    <ResponsiveContainer key={bands.length ? 'regime' : 'base'} width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <defs>
          <linearGradient id="sizedFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={lineColor} stopOpacity={0.18} />
            <stop offset="95%" stopColor={lineColor} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
        {bands.map((b, i) => (
          <ReferenceArea
            key={i}
            x1={b.x1}
            x2={b.x2}
            fill={REGIME_COLORS[b.regime] ?? REGIME_COLORS.UNKNOWN}
            fillOpacity={0.1}
            stroke="none"
          />
        ))}
        <XAxis
          dataKey="i"
          ticks={xTicks}
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => fmtChartDate(rows[v]?.date)}
        />
        <YAxis
          domain={[min - pad, max + pad]}
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={balTick}
          width={56}
        />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const r = payload[0]?.payload as (typeof rows)[number] | undefined
            if (!r) return null
            return (
              <div
                style={{
                  background: C.tooltipBg,
                  border: `1px solid ${C.tooltipBorder}`,
                  borderRadius: 8,
                  fontSize: 13,
                  padding: '8px 12px',
                }}
              >
                <p style={{ color: C.axisTick, marginBottom: 4 }}>{fmtChartDate(r.date)}</p>
                <p style={{ color: '#e5e7eb' }}>
                  Balance&nbsp;${r.balance.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </p>
                {r.floor != null && (
                  <p style={{ color: C.neg }}>
                    Floor&nbsp;${r.floor.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                  </p>
                )}
                {r.buffer != null && (
                  <p style={{ color: C.axisTick }}>
                    Buffer&nbsp;${r.buffer.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                  </p>
                )}
                <p style={{ color: C.axisTick }}>
                  {r.trades} trade{r.trades === 1 ? '' : 's'} · {r.contracts} contracts
                </p>
                {r.halt && <p style={{ color: C.gold }}>Halted: {r.halt}</p>}
              </div>
            )
          }}
        />
        <ReferenceLine y={startBal} stroke={C.refLine} strokeDasharray="4 4" />
        <Area
          type="monotone"
          dataKey="balance"
          stroke={lineColor}
          strokeWidth={1.5}
          fill="url(#sizedFill)"
          dot={false}
          activeDot={{ r: 4, fill: lineColor, stroke: 'transparent' }}
          baseValue="dataMin"
          animationDuration={1500}
        />
        <Line
          type="stepAfter"
          dataKey="floor"
          stroke={C.neg}
          strokeWidth={1.25}
          strokeDasharray="5 4"
          dot={false}
          connectNulls
          animationDuration={1500}
        />
        {/* Mark halt days and the breach day so the why-it-stopped reads at a glance. */}
        {haltDays.map((d) => (
          <ReferenceDot key={`h${d.i}`} x={d.i} y={d.balance} r={3} fill={C.gold} stroke="none" />
        ))}
        {breachIdx >= 0 && (
          <ReferenceDot
            x={rows[breachIdx].i}
            y={rows[breachIdx].balance}
            r={4.5}
            fill={C.neg}
            stroke={C.tooltipBg}
            strokeWidth={1.5}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// The sized-run label, in one place — three surfaces show it and they must agree.
export function sizingModeLabel(mode: SizingMode, manualPct?: number | null): string {
  if (mode === 'manual') return `Manual ${manualPct ?? '?'}%`
  return mode === 'bullet' ? 'Bullet' : 'Consistent'
}

export function SizedCurveLegend({
  mode,
  manualPct,
  profitable = true,
}: {
  mode: SizingMode
  manualPct?: number | null
  profitable?: boolean
}) {
  return (
    <div className="flex items-center gap-4 mt-2 text-[11px] text-text-tertiary">
      <span className="flex items-center gap-1.5">
        <span
          className="inline-block w-3 h-[2px] rounded-full"
          style={{ background: profitable ? C.pos : C.neg }}
        />
        End-of-day balance
      </span>
      <span className="flex items-center gap-1.5">
        <span
          className="inline-block w-3 border-t-2 border-dashed"
          style={{ borderColor: C.neg }}
        />
        Trailing risk floor (breach = fail)
      </span>
      <span className="ml-auto font-medium text-text-secondary">
        Engine-sized · {sizingModeLabel(mode, manualPct)}
      </span>
    </div>
  )
}

// ── Drawdown chart ────────────────────────────────────────────────────────────

export function DrawdownChart({
  equity,
  limitLines,
  height = 140,
}: {
  equity: EquityPoint[]
  limitLines?: Array<{ limit: number; label: string; pass: boolean }>
  height?: number
}) {
  if (!equity.length) return null

  let peak = equity[0].equity
  const ddData = equity.map((pt) => {
    if (pt.equity > peak) peak = pt.equity
    const dd = peak !== 0 ? pt.equity - peak : 0
    return { index: pt.index, drawdown: Math.round(dd), date: pt.date }
  })

  const worst = Math.min(...ddData.map((d) => d.drawdown))
  const ddTicks = calIndexTicks(ddData)
  // Explicit ROUND ticks. Recharts derives its own from the padded domain, which is `worst * 1.1`
  // and therefore never round — it was labelling a nine-figure run -$45.1M / -$30.1M / -$15.1M.
  // Zero is the anchor here the way the opening balance is on the equity chart: it is the line the
  // reader measures every other tick against.
  const ddYTicks = balanceTicks(0, worst * 1.1, 0)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={ddData} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
        <defs>
          <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={C.neg} stopOpacity={0.12} />
            <stop offset="95%" stopColor={C.neg} stopOpacity={0.3} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
        <XAxis
          dataKey="index"
          ticks={ddTicks}
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => {
            const date = ddData[v - 1]?.date
            if (!date) return ''
            return calTickLabel(
              date,
              v === ddData[0].index || v === ddData[ddData.length - 1].index
            )
          }}
        />
        <YAxis
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={balTick}
          width={56}
          ticks={ddYTicks}
          domain={[worst * 1.1, 0]}
        />
        <Tooltip
          contentStyle={{
            background: C.tooltipBg,
            border: `1px solid ${C.tooltipBorder}`,
            borderRadius: 8,
            fontSize: 13,
            padding: '8px 12px',
          }}
          formatter={(v: number) => [
            `$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
            'Drawdown',
          ]}
          labelFormatter={(
            _: unknown,
            payload: Array<{ payload?: { index: number; date?: string } }>
          ) => {
            const pt = payload?.[0]?.payload
            if (!pt) return ''
            const dateStr = pt.date ? ` · ${fmtChartDate(pt.date)}` : ''
            return `Trade #${pt.index}${dateStr}`
          }}
        />
        <ReferenceLine y={0} stroke={C.refLine} />
        {limitLines?.map((ll) => (
          <ReferenceLine
            key={ll.limit}
            y={-ll.limit}
            stroke={ll.pass ? `${C.pos}55` : `${C.neg}99`}
            strokeDasharray="5 3"
            label={{
              value: `$${ll.limit >= 1000 ? `${(ll.limit / 1000).toFixed(0)}k` : ll.limit} limit`,
              fill: ll.pass ? `${C.pos}99` : C.neg,
              fontSize: 9,
              position: 'insideTopRight',
            }}
          />
        ))}
        <Area
          type="monotone"
          dataKey="drawdown"
          stroke={C.neg}
          strokeWidth={1.5}
          fill="url(#ddGrad)"
          dot={false}
          activeDot={{ r: 3, fill: C.neg, stroke: 'transparent' }}
          baseValue={0}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ── Regime legend + overlay toggle ───────────────────────────────────────────

export function RegimeLegend({ bands }: { bands: RegimeBand[] }) {
  const regimes = [...new Set(bands.map((b) => b.regime))].filter((r) => r !== 'UNKNOWN')
  if (!regimes.length) return null
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 px-2 mt-2 mb-1">
      {regimes.map((regime) => (
        <div key={regime} className="flex items-center gap-1.5">
          <div
            style={{
              width: 12,
              height: 12,
              background: REGIME_COLORS[regime] ?? REGIME_COLORS.UNKNOWN,
              borderRadius: 3,
            }}
          />
          <span className="text-[10px] text-text-tertiary">{REGIME_LABEL[regime] ?? regime}</span>
        </div>
      ))}
    </div>
  )
}

// Generic on/off pill for an equity-chart series (histogram / excursions / run-ups & drawdowns).
export function SeriesToggle({
  label,
  on,
  onChange,
}: {
  label: string
  on: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      onClick={() => onChange(!on)}
      className={`flex items-center gap-1.5 px-2 py-[4px] rounded text-[11px] transition-colors ${
        on
          ? 'text-accent bg-accent/10 border border-accent/25'
          : 'text-text-tertiary hover:text-text-secondary border border-border-subtle'
      }`}
    >
      {label}
    </button>
  )
}

// ── Direction breakdown ───────────────────────────────────────────────────────

export function DirectionBreakdown({ equity }: { equity: EquityPoint[] }) {
  const trades = equity.filter((pt) => pt.direction && pt.profit != null)
  if (!trades.length) return null

  const sides = ['Long', 'Short'] as const
  const stats = sides
    .map((dir) => {
      const group = trades.filter((pt) => pt.direction === dir)
      const wins = group.filter((pt) => (pt.profit ?? 0) > 0).length
      const losses = group.length - wins
      const totalPnl = group.reduce((s, pt) => s + (pt.profit ?? 0), 0)
      const avgTrade = group.length ? totalPnl / group.length : 0
      return { dir, count: group.length, wins, losses, totalPnl, avgTrade }
    })
    .filter((s) => s.count > 0)

  return (
    <div className="grid grid-cols-2 gap-4">
      {stats.map((s, i) => {
        const winPct = Math.round((s.wins / s.count) * 100)
        const pnlCls = s.totalPnl >= 0 ? 'text-pos-text' : 'text-neg-text'
        // Lost first so the animation sweeps red → green (losing to winning)
        const data = [
          { name: 'Lost', value: s.losses },
          { name: 'Won', value: s.wins },
        ]
        return (
          <div key={s.dir} className="flex flex-col items-center gap-1">
            <div className="text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.5px]">
              {s.dir}
            </div>
            <div className={`text-[15px] font-semibold font-mono tabular-nums ${pnlCls}`}>
              {dollar(s.totalPnl, true)}
            </div>
            <ResponsiveContainer width="100%" height={118}>
              <PieChart>
                <Pie
                  data={data}
                  cx="50%"
                  cy="50%"
                  innerRadius={36}
                  outerRadius={52}
                  startAngle={90}
                  endAngle={-270}
                  paddingAngle={2}
                  dataKey="value"
                  strokeWidth={0}
                  isAnimationActive={true}
                  animationBegin={i * 150}
                  animationDuration={900}
                  animationEasing="ease-out"
                >
                  <Cell fill={C.neg} fillOpacity={0.75} />
                  <Cell fill={C.pos} fillOpacity={0.85} />
                  <Label
                    value={`${winPct}%`}
                    position="center"
                    fill="#e6edf3"
                    fontSize={16}
                    fontWeight={700}
                  />
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="text-[10px] text-text-tertiary">
              {s.count} trades · avg {dollar(s.avgTrade, true)}/trade
            </div>
            <div className="flex gap-5 text-[11px] font-semibold mt-[2px]">
              <span className="text-neg-text">{s.losses} lost</span>
              <span className="text-pos-text">{s.wins} won</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Daily P&L chart ───────────────────────────────────────────────────────────

export function DailyPnlChart({
  data,
  netPnl,
  height = 260,
}: {
  data: DailyPnlPoint[]
  netPnl: number | null
  height?: number
}) {
  if (!data.length) {
    return (
      <div className="h-[160px] flex flex-col items-center justify-center gap-2 text-center px-6">
        <div className="text-text-secondary text-[13px] font-medium">No daily P&L data yet</div>
        <div className="text-text-tertiary text-[11px]">
          Available once the backtest report has been parsed.
        </div>
      </div>
    )
  }

  const halfTarget = netPnl != null && netPnl > 0 ? netPnl * 0.5 : null
  const pnlTicks = calDateTicks(data)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }} barCategoryGap="20%">
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} vertical={false} />
        <XAxis
          dataKey="date"
          ticks={pnlTicks}
          padding={{ left: 24, right: 8 }}
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(d: string) =>
            calTickLabel(d, d === data[0].date || d === data[data.length - 1].date)
          }
        />
        <YAxis
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={balTick}
          width={52}
        />
        <Tooltip
          cursor={{ fill: 'rgba(255,255,255,0.04)' }}
          contentStyle={{
            background: C.tooltipBg,
            border: `1px solid ${C.tooltipBorder}`,
            borderRadius: 8,
            fontSize: 13,
            padding: '8px 12px',
          }}
          labelStyle={{ color: C.axisTick }}
          itemStyle={{ color: '#e5e7eb' }}
          formatter={(v: number) => [dollar(v, true), 'P&L']}
          labelFormatter={(d: string) => chartDateLabel(d)}
        />
        <ReferenceLine y={0} stroke={C.refLine} />
        {halfTarget != null && (
          <ReferenceLine
            y={halfTarget}
            stroke={`${C.gold}50`}
            strokeDasharray="4 4"
            label={{
              value: '50% of target',
              fill: C.gold,
              fontSize: 10,
              position: 'insideTopRight',
            }}
          />
        )}
        <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.pnl >= 0 ? C.pos : C.neg} fillOpacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Section label ─────────────────────────────────────────────────────────────

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">
      {children}
    </h2>
  )
}
