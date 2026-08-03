import { Fragment, Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import {
  ArrowLeft, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, AlertTriangle,
  CheckCircle, XCircle, Minus, Info, Square, RefreshCw, RotateCcw, Activity, Play,
  Copy, Check, SlidersHorizontal, Minimize2, Newspaper,
} from 'lucide-react'
import {
  AreaChart, Area, ComposedChart, Line, BarChart, Bar, PieChart, Pie, Label,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine, ReferenceArea, ReferenceDot,
} from 'recharts'
import { useBacktestRun, useBacktestRuns, useRunLog, useLabProgress, useStopBacktest, useReloadCharts, useRetryBacktest, useRunningVpsJob, useStrategy, useRulesets, useChartSpec, useRefreshChartSpec, useRunCandles, useRunNews, useHistoryLimit } from '@/hooks/useLab'
import InfoTip from '@/components/InfoTip'
import { PeriodPicker } from '@/components/PeriodPicker'
import { isNt8Runner, runnerScope, runnerMarket, runningJobFor, RUNNER_LABEL } from '@/lib/runner'
import { useStressTests, useRunStressTest, useRunningStressLock } from '@/hooks/useStressTests'
import type { BacktestDetail as Run, EvaluationDetail, EquityPoint, DailyPnlPoint, ParamSchemaEntry, SizedTimelineDay, NewsTradeTag, SizingMode } from '@/types'
import { C } from '@/themes/chart'
import { REGIME_COLORS, REGIME_LABEL } from '@/lib/regime'
import { balanceTicks, dateMs, getXMode, monthLabel, monthTicks, regimeBandsByIndex, regimeBandsFromTimeline, setXModePref, type XMode } from '@/lib/chartAxis'
import { XModeToggle } from '@/components/XModeToggle'
import { RegimeOverlayToggle } from '@/components/RegimeOverlayToggle'

import { ChartTabPanel, ChartModal } from '@/components/ChartTabPanel'
import type { ChartSpec } from '@/components/ChartPanel/types'
import { OptimizeButton } from '@/components/OptimizeButton'
import RobustnessGradeBadge from '@/components/RobustnessGradeBadge'
import { StatusPill } from '@/components/StatusPill'
import { useStickyBanner } from '@/components/StickyHeader'

// Lazy so klinecharts + the chart fixture only load when the Price chart section opens.
const ChartPanel = lazy(() => import('@/components/ChartPanel'))

// Stress-test sample-size gate — mirror backend services/stress_tester.py. Below this the whole
// test is blocked (the A-F grade leans on Monte Carlo tail percentiles that small samples can't
// estimate). Backend enforces it (422); this drives the disabled button so it's explicit.
const MIN_TRADES_FOR_STRESS = 100

// ── Formatters ────────────────────────────────────────────────────────────────

/** Display names for the cost layers a python run can charge. Reading order matches the Run
 *  modal's, so the page and the form name the same thing the same way. */
const COST_LAYER_LABEL: Record<string, string> = {
  spread: 'spread',
  swap: 'overnight swap',
  commission: 'commission',
  slippage: 'slippage',
  bid_ask_fills: 'bid/ask fills',
}

function dollar(n: number | null | undefined, signed = false): string {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : signed ? '+' : ''
  return `${sign}$${abs.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

function pct(n: number | null | undefined): string {
  if (n == null) return '—'
  return `${(n * 100).toFixed(1)}%`
}

// Trade duration in the largest unit that still reads as a quantity. "1365 min" is a number the
// reader has to divide before it means anything; 22.8 h is the same fact already divided.
function fmtHold(min: number | null | undefined): string {
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
const FIT_SLACK = 2
// Below this the headline would be smaller than the rows under it, which reads as an error rather
// than as a big number. At that point the card is too narrow for this metric at all.
const FIT_MIN_SCALE = 0.6

function FitMoney({ n, signed = false }: { n: number | null | undefined; signed?: boolean }) {
  const wrapRef = useRef<HTMLSpanElement>(null)
  const ghostRef = useRef<HTMLSpanElement>(null)
  // {scale, width} together: a CSS transform leaves the layout box at its natural size, so without
  // pinning the width the unit label beside it ("net") would sit where the UNSCALED text ended.
  const [fit, setFit] = useState<{ scale: number; width: number } | null>(null)
  const full = dollar(n, signed)
  useEffect(() => {
    const wrap = wrapRef.current, ghost = ghostRef.current
    if (!wrap || !ghost) return
    const box = (wrap.closest('[data-fit-box]') as HTMLElement | null) ?? wrap
    const measure = () => {
      const avail = box.getBoundingClientRect().width - FIT_SLACK
      const need = ghost.getBoundingClientRect().width      // always the UNSCALED width
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
    <span ref={wrapRef} className="inline-block relative whitespace-nowrap"
          style={fit ? { width: `${fit.width}px` } : undefined}>
      <span ref={ghostRef} aria-hidden
            className="invisible absolute left-0 top-0 whitespace-nowrap pointer-events-none">{full}</span>
      <span className="inline-block origin-left"
            style={fit ? { transform: `scale(${fit.scale})` } : undefined}>{full}</span>
    </span>
  )
}

// A bare 'YYYY-MM-DD' parses as UTC midnight and then prints in the VIEWER's timezone, which
// lands a day early anywhere west of Greenwich: the run header read "Jan 1, 2021 → Jul 27, 2026"
// for a run whose stored window is 2021-01-02 → 2026-07-28. Pin it to local midnight — the same
// guard chartDateLabel below already carried. The slice also tolerates a full ISO datetime.
function fmtDate(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  })
}

function chartDateLabel(iso: string): string {
  const d = new Date(iso + 'T00:00:00')
  const yr = String(d.getFullYear()).slice(-2)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ` '${yr}`
}

// ── Calendar tick helpers ─────────────────────────────────────────────────────

const _MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

// Endpoints show day ("May 30 '23"), interior quarters just month+year ("Apr '24")
function calTickLabel(iso: string, isEndpoint: boolean): string {
  const d  = new Date(iso.slice(0, 10) + 'T00:00:00')
  const m  = _MONTHS[d.getMonth()]
  const yr = String(d.getFullYear()).slice(-2)
  return isEndpoint ? `${m} ${d.getDate()} '${yr}` : `${m} '${yr}`
}

// For index-based charts: tick positions at start, Q1/Q2/Q3/Q4 boundaries, end
function calIndexTicks(pts: Array<{ index: number; date?: string | null }>): number[] {
  if (pts.length <= 1) return pts.map(p => p.index)
  const first = pts[0].date, last = pts[pts.length - 1].date
  if (!first || !last) return [pts[0].index, pts[pts.length - 1].index]

  const dateToIdx = new Map<string, number>()
  for (const p of pts) {
    if (p.date && !dateToIdx.has(p.date)) dateToIdx.set(p.date, p.index)
  }
  const sorted = [...dateToIdx.keys()].sort()
  const nearest = (target: string) => { const d = sorted.find(s => s >= target); return d != null ? dateToIdx.get(d) : undefined }

  const sy = new Date(first.slice(0, 10) + 'T00:00:00').getFullYear()
  const ey = new Date(last.slice(0, 10)  + 'T00:00:00').getFullYear()
  const set = new Set<number>([pts[0].index, pts[pts.length - 1].index])
  for (let y = sy; y <= ey; y++)
    for (const m of ['01', '04', '07', '10']) { const idx = nearest(`${y}-${m}-01`); if (idx != null) set.add(idx) }
  return [...set].sort((a, b) => a - b)
}

// For date-keyed charts: tick values at start, Q1/Q2/Q3/Q4 boundaries, end
function calDateTicks(data: DailyPnlPoint[]): string[] {
  if (data.length <= 1) return data.map(d => d.date)
  const all = data.map(d => d.date)
  const nearest = (target: string) => all.find(d => d >= target)
  const sy = new Date(data[0].date + 'T00:00:00').getFullYear()
  const ey = new Date(data[data.length - 1].date + 'T00:00:00').getFullYear()
  const set = new Set<string>([data[0].date, data[data.length - 1].date])
  for (let y = sy; y <= ey; y++)
    for (const m of ['01', '04', '07', '10']) { const d = nearest(`${y}-${m}-01`); if (d) set.add(d) }
  return [...set].sort()
}

// ── Color helpers ─────────────────────────────────────────────────────────────

function winRateCls(rate: number | null): string {
  if (rate == null) return 'text-text-tertiary'
  if (rate >= 0.60) return 'text-pos-text'
  if (rate >= 0.50) return 'text-warn-text'
  return 'text-neg-text'
}

function winRateLabel(rate: number | null): string {
  if (rate == null) return 'win / total trades'
  if (rate >= 0.60) return 'strong'
  if (rate >= 0.50) return 'good'
  if (rate >= 0.45) return 'marginal — needs high R:R'
  return 'weak — needs high R:R'
}

// A ratio card's value: a number, ∞ when the denominator is legitimately zero (no losing trade / no
// drawdown), or a dash only when the input truly isn't there.
function kpiNum(v: number | null): string {
  if (v == null) return '—'
  return Number.isFinite(v) ? v.toFixed(2) : '∞'
}

function pfCls(pf: number | null): string {
  if (pf == null) return 'text-text-tertiary'
  if (pf >= 2.0) return 'text-pos-text'
  if (pf >= 1.5) return 'text-warn-text'
  return 'text-neg-text'
}

function pfLabel(pf: number | null): string {
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

function sharpeLabel(s: number | null, estimated: boolean): string {
  if (s == null) return 'risk-adjusted annual return'
  const base =
    s >= 2.0 ? 'excellent' :
    s >= 1.0 ? 'good' :
    s >= 0.5 ? 'marginal' : 'poor'
  return estimated ? `${base} (estimated)` : base
}

// Turns a value-colour class into an EXCEPTION colour: an ordinary value gets no colour at
// all. Lets the *Cls helpers stay the single definition of "what counts as bad" while the
// panel only paints the rows that cross it. See the colour policy on PerformancePanel.
function exceptionCls(cls: string): string | undefined {
  return (cls === 'text-text-primary' || cls === 'text-text-tertiary') ? undefined : cls
}

// ── Recovery factor ──────────────────────────────────────────────────────────
// Annualized net P&L ÷ max drawdown — both in dollars, so it needs no starting
// capital. (Previously mislabelled "Calmar"; real Calmar lives below.)

function computeRecoveryFactor(
  netPnl: number | null,
  maxDrawdown: number | null,
  equity: EquityPoint[],
): number | null {
  if (netPnl == null || maxDrawdown == null) return null
  const absDd = Math.abs(maxDrawdown)
  if (absDd === 0 || equity.length < 2) return null
  // Slice to YYYY-MM-DD — MT5 equity dates are full ISO datetimes; appending T00:00:00 breaks parsing
  const firstDate = equity[0].date?.slice(0, 10)
  const lastDate  = equity[equity.length - 1].date?.slice(0, 10)
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
function rebaseEquity(equity: EquityPoint[], balance: number): number[] {
  const out: number[] = []
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
function maxDrawdownOf(series: number[]): number {
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
// never be presented as one number: on the shipped mpc_sos_fade run the deepest dollar drop is
// $109,665 from a $330,303 peak (33.2%), while the worst percentage drop is 54.9% ($16,748 →
// $7,551, only $9,198). Reporting the big dollar figure as the percentage is what produced
// "1096.7% of capital" — the dollar drawdown divided by a static account_size the account had
// long outgrown. Returns the dollars and peak of the SAME episode so the card's sub-line can
// describe the drawdown its value actually names.
function maxDrawdownPctOf(series: number[]): { pct: number; dollars: number; peak: number } | null {
  let peak = -Infinity
  let worst: { pct: number; dollars: number; peak: number } | null = null
  for (const v of series) {
    if (v > peak) peak = v
    if (peak <= 0) continue                       // a non-positive peak has no meaningful percent
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
// mpc_sos_fade run: 0.11 (red, "poor") against a static $10k, 2.25 ("good") against the peak.

function computeCalmar(equity: EquityPoint[], balance: number | null): number | null {
  if (balance == null || balance <= 0 || equity.length < 2) return null
  const firstDate = equity[0].date?.slice(0, 10)
  const lastDate  = equity[equity.length - 1].date?.slice(0, 10)
  if (!firstDate || !lastDate) return null
  const days = (new Date(lastDate).getTime() - new Date(firstDate).getTime()) / 86_400_000
  if (days < 1) return null
  // Derive net P&L and max drawdown from the rebased curve (trade-derived → platform-agnostic).
  const rebased = rebaseEquity(equity, balance)
  const netPnl  = rebased[rebased.length - 1] - balance
  const dd      = maxDrawdownPctOf(rebased)
  // Zero drawdown isn't "unknown" — it's an undefeated curve, so Calmar is genuinely infinite.
  // Report Infinity (the card prints ∞) rather than a dash that reads as missing data.
  if (dd == null || dd.pct === 0) return netPnl > 0 ? Infinity : null
  const years   = days / 365
  const cagr    = Math.pow(1 + netPnl / balance, 1 / Math.max(years, 0.1)) - 1
  return cagr / dd.pct
}

function calmarCls(c: number | null): string {
  if (c == null) return 'text-text-tertiary'
  if (c >= 3.0) return 'text-pos-text'
  if (c >= 1.0) return 'text-warn-text'
  return 'text-neg-text'
}

function calmarLabel(c: number | null): string {
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
function computeZScore(equity: EquityPoint[]): number | null {
  const seq = equity
    .map(e => e.profit)
    .filter((p): p is number => p != null && p !== 0)
    .map(p => p > 0)
  const n = seq.length
  if (n < 2) return null
  const n1 = seq.filter(Boolean).length   // wins
  const n2 = n - n1                        // losses
  if (n1 === 0 || n2 === 0) return null
  let runs = 1
  for (let i = 1; i < n; i++) if (seq[i] !== seq[i - 1]) runs++
  const mu = (2 * n1 * n2) / n + 1
  const variance = (2 * n1 * n2 * (2 * n1 * n2 - n)) / (n * n * (n - 1))
  if (variance <= 0) return null
  return (runs - mu) / Math.sqrt(variance)
}

function zScoreCls(z: number | null): string {
  if (z == null) return 'text-text-tertiary'
  return Math.abs(z) > 2 ? 'text-warn-text' : 'text-text-primary'
}

// Why the runs test couldn't run, said in the strategy's own terms — a curve with no losing trade
// has no win/loss sequence to test, and that is information, not a missing value.
function zScoreUnavailableLabel(equity: EquityPoint[]): string {
  const profits = equity.map(e => e.profit).filter((p): p is number => p != null && p !== 0)
  if (profits.length < 2) return 'runs test — needs 2+ trades'
  const losses = profits.filter(p => p < 0).length
  if (losses === 0) return `all ${profits.length} trades won — no streaks to test`
  if (losses === profits.length) return `all ${profits.length} trades lost — no streaks to test`
  return 'runs test — needs wins & losses'
}

function zScoreLabel(z: number | null): string {
  if (z == null) return 'runs test — needs wins & losses'
  const a = Math.abs(z)
  if (a <= 1.5) return 'streaks look random'
  if (a <= 2)   return 'mild streaking'
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
// mpc_sos_fade d2ab68f9e884 — dollar quarters $9k / $49k / $71k / $1,039k read 89% ("edge
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
function equityBase(equity: EquityPoint[]): number {
  if (equity.length === 0) return 0
  return (equity[0].equity ?? 0) - (equity[0].profit ?? 0)
}

function computeProfitConcentration(daily: DailyPnlPoint[], equity: EquityPoint[] = []): number | null {
  // Each entry contributes a WEIGHT: a return when the run compounded, else a dollar amount.
  const base = equityBase(equity)
  const points: Array<{ date: string; weight: number }> = base > 0
    ? equity.flatMap(e => {
        const before = (e.equity ?? 0) - (e.profit ?? 0)
        return (e.date && before > 0) ? [{ date: e.date, weight: (e.profit ?? 0) / before }] : []
      })
    : daily.filter(d => d.date).map(d => ({ date: d.date, weight: d.pnl }))

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
function tradeWeights(equity: EquityPoint[]): number[] {
  if (equity.length === 0) return []
  if (equityBase(equity) <= 0) return equity.map(e => e.profit ?? 0)
  return equity.flatMap(e => {
    const before = (e.equity ?? 0) - (e.profit ?? 0)
    return before > 0 ? [(e.profit ?? 0) / before] : []
  })
}

// A trade this far below the run's own typical loss neither won nor lost meaningfully.
const SCRATCH_FRACTION = 0.15

function median(xs: number[]): number {
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
function computeScratchCount(equity: EquityPoint[]): number | null {
  const w = tradeWeights(equity)
  const losses = w.filter(x => x < 0).map(Math.abs)
  if (losses.length === 0) return null
  const scale = median(losses)
  if (!(scale > 0)) return null
  return w.filter(x => Math.abs(x) < scale * SCRATCH_FRACTION).length
}

const TRADE_CONCENTRATION_TOP_N = 5

// Share of GROSS PROFIT made by the biggest few winners. Mirrors
// services/metrics.trade_concentration_pct.
function computeTradeConcentration(equity: EquityPoint[]): number | null {
  const wins = tradeWeights(equity).filter(x => x > 0).sort((a, b) => b - a)
  const gross = wins.reduce((t, x) => t + x, 0)
  if (!(gross > 0)) return null
  return (wins.slice(0, TRADE_CONCENTRATION_TOP_N).reduce((t, x) => t + x, 0) / gross) * 100
}

function tradeConcentrationLabel(c: number | null): string {
  if (c == null) return `top ${TRADE_CONCENTRATION_TOP_N} winners ÷ gross profit`
  if (c >= 50) return 'the edge rests on a handful of trades'
  if (c >= 30) return 'a few trades carry a lot of it'
  return 'spread across many trades'
}

function concentrationCls(c: number | null): string {
  if (c == null) return 'text-text-tertiary'
  return c >= 60 ? 'text-warn-text' : 'text-text-primary'
}

function concentrationLabel(c: number | null): string {
  if (c == null) return 'top quarter ÷ gross profit'
  if (c >= 60) return 'edge clustered — overfit risk'
  if (c >= 40) return 'somewhat concentrated'
  return 'spread across the test'
}

// ── Fallback KPI computation ──────────────────────────────────────────────────
// Derives Sharpe / Worst Day / Worst Streak from daily_pnl when the
// NT8 agent doesn't report them directly.

const TRADING_DAYS_PER_YEAR = 252
const SHARPE_LOW_SAMPLE_DAYS = 10

/**
 * Per-day P&L for EVERY weekday spanned by the series, flat days included as 0.
 *
 * Mirrors `backend/services/metrics.py:zero_filled_daily_values` exactly, and it is the whole
 * story behind the Sharpe bug fixed 2026-07-31. `daily_pnl` holds only days that CLOSED a trade —
 * flat days are absent by design, because the trailing-drawdown engine walks the days that exist.
 * Scoring that series as if it were the population asks "how good were the days it traded", then
 * annualizes by √252 as if it had traded 252 of them. On the shipped mpc_sos_fade run that reads
 * 2.98 against a true 0.91. A flat day is a real observation and belongs in the series.
 *
 * Weekends are skipped to match √252, but any date PRESENT in the input is kept even on a weekend,
 * so a Sunday-open forex fill is never silently dropped.
 */
function zeroFilledDailyValues(daily_pnl: DailyPnlPoint[]): number[] {
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
  let max = 0, cur = 0
  for (const p of pnls) {
    if (p < 0) { cur++; if (cur > max) max = cur }
    else cur = 0
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
  const activeDays = daily_pnl.filter(d => (d.pnl ?? 0) !== 0).length

  return {
    worstDay: Math.min(...daily_pnl.map(d => d.pnl)),
    sharpe: activeDays >= SHARPE_LOW_SAMPLE_DAYS ? dailySharpe(daily_pnl) : null,
  }
}

// ── Derived metrics ──────────────────────────────────────────────────────────

// Every number the panel shows, derived from one run. Pulled out of the component so the
// SAME expressions can be evaluated a second time against a comparison run — that is what
// lets the news filter print a delta on each row instead of shipping a second copy of the
// panel. Adding a metric here and forgetting the card is harmless; the reverse is what drifts.
function deriveKpis(run: Run, fallback: FallbackMetrics, equity: EquityPoint[], balance: number | null) {
  const sharpe      = run.sharpe              ?? fallback.sharpe
  const worstDay    = run.worst_day_pnl       ?? fallback.worstDay
  // No fallback: a streak must come from a TRADE list or not at all. Both synthesizers
  // (buildFilteredRun, StackDetail.composeCombined) set it via worstLosingStreakOf.
  const worstStreak = run.worst_losing_streak
  const recoveryFactor = computeRecoveryFactor(run.net_pnl, run.max_drawdown, equity)
  // Capital-based scores rebase the equity to `balance` (the ruleset's account_size, or the
  // what-if slider). Both compute off the same stored run — no re-run, no backend.
  const calmar = computeCalmar(equity, balance)
  // Expectancy. $/trade is always available; R needs per-trade risk, which stored trades
  // don't carry (profit only), so expectancy_r is not computable — left out honestly.
  const expectancyUsd = (run.net_pnl != null && run.trade_count)
    ? run.net_pnl / run.trade_count
    : null
  const zScore = computeZScore(equity)
  // Profit factor: the backend stores null when gross losses are 0 (divide-by-zero). That case
  // is an undefeated run, not unknown data — recover it from the trades and print ∞.
  const tradeProfits = equity.map(e => e.profit).filter((p): p is number => p != null && p !== 0)
  const grossLoss = tradeProfits.filter(p => p < 0).reduce((a, b) => a + Math.abs(b), 0)
  const pfValue = run.profit_factor
    ?? (tradeProfits.length > 0 && grossLoss === 0 ? Infinity : null)
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
  const ddWorst  = (balance != null && balance > 0 && equity.length >= 2)
    ? maxDrawdownPctOf(rebaseEquity(equity, balance))
    : null
  const maxDdPct = ddWorst != null ? ddWorst.pct * 100 : null
  // The dollars of that SAME episode — what the card's caption describes. A different, usually
  // larger, dollar drawdown exists later in a compounding run; it is reported separately, never
  // beside the percentage it does not correspond to.
  const ddAtWorstPct = ddWorst?.dollars ?? null
  const ddPeak       = ddWorst?.peak ?? null
  // Deepest drawdown in DOLLARS (trade-derived; falls back to the run's stored value). This is
  // the prop-firm view — a firm caps dollars — and the comparison fallback when there's no balance.
  const tradeDd  = equity.length >= 2 ? maxDrawdownOf(rebaseEquity(equity, 0)) : null
  const ddDollar = tradeDd ?? (run.max_drawdown != null ? Math.abs(run.max_drawdown) : null)

  const rrRatio = (run.avg_win != null && run.avg_loss != null && run.avg_loss !== 0)
    ? run.avg_win / Math.abs(run.avg_loss) : null

  return {
    netPnl: run.net_pnl, winRate: run.win_rate, avgDur: run.avg_trade_duration_min,
    sharpe, worstDay, worstStreak, recoveryFactor, calmar, expectancyUsd, zScore,
    pfValue, profitConc, maxDdPct, ddDollar, ddAtWorstPct, ddPeak, rrRatio,
    scratches, tradeConc,
  }
}
type DerivedKpis = ReturnType<typeof deriveKpis>

// ── Time underwater ──────────────────────────────────────────────────────────
// Share of the test's CALENDAR span spent below the previous equity high. Max drawdown says how
// DEEP the hole was; this says how long you sat in it, which is the half that decides whether a
// strategy is holdable. Rebased to 0 so it never depends on the account balance.
//
// Weighted by elapsed days, not by row count (fixed 2026-07-31). `daily_pnl` holds only the days
// that closed a trade — flat days are deliberately absent (backtest/output.py) — so counting rows
// answered "what share of ACTIVE days were underwater" while the label said "of days". The gap is
// not cosmetic on a selective strategy: mpc_sos_fade trades ~2x a month, so a row is worth two
// weeks of calendar. It read 67% by rows and 70% by the clock. Equity between two closes sits at
// the earlier close's level, which is what each day of that gap is judged against.
function computeTimeUnderwater(daily: DailyPnlPoint[]): number | null {
  const dated = daily.filter(d => d.date)
  if (dated.length < 2) return null
  const dayOf = (d: string) => new Date(`${d.slice(0, 10)}T00:00:00`).getTime()
  const total = (dayOf(dated[dated.length - 1].date) - dayOf(dated[0].date)) / DAY_MS
  if (!(total > 0)) return null
  let bal = 0, peak = 0, under = 0, prev = dayOf(dated[0].date)
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
const METER_CEILINGS = [25, 50, 75, 100]
function meterCeiling(...vals: Array<number | null | undefined>): number {
  const m = Math.max(0, ...vals.filter((v): v is number => v != null && isFinite(v)))
  return METER_CEILINGS.find(c => m <= c * 0.92) ?? 100
}

// The observed drawdown as a bar, with two optional references: the ruleset's stated limit
// (gold tick) and the stress test's worst-1% simulated drawdown (hatched extension past the
// solid fill). Both are drawn ONLY when real — a percentage drawdown means nothing on its
// own, but neither reference may ever be invented to give it one. No stress test → no
// hatch, and the caption says so rather than implying the tail is zero.
function DrawdownMeter({ pct, limitPct, tailPct }: {
  pct: number; limitPct: number | null; tailPct: number | null
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
          <span className="absolute w-[2px] bg-gold-text" style={{ left: x(limitPct), top: 10, bottom: -3 }} />
        )}
      </div>
      <div className="flex justify-between mt-[3px] font-mono text-[9.5px] leading-none text-text-tertiary tabular-nums">
        <span>0%</span><span>{(ceiling / 2).toFixed(0)}%</span><span>{ceiling}%</span>
      </div>
    </div>
  )
}

type PanelRow = {
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
function panelCardCls(collapsed: boolean, filtered: boolean, topBorder: string): string {
  return `flex flex-col min-w-0 rounded-xl border border-border-subtle px-4 pt-[13px] ${
    collapsed ? 'pb-[12px]' : 'pb-[6px]'} ${filtered ? 'bg-accent/[0.06]' : 'bg-bg-surface'} ${topBorder}`
}

/** Title and question share ONE line. The question is orientation you read once; on its own row
 *  it charged ~16px of card height per card, forever, for a sentence nobody re-reads. The narrow
 *  fourth card has no room for one at all, so it passes the slot to its aside instead. */
function CardHead({ title, question, aside }: {
  title: string; question?: string; aside?: React.ReactNode
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="flex items-baseline gap-2 min-w-0">
        <span className="text-[10px] font-bold uppercase tracking-[0.9px] text-text-secondary shrink-0">{title}</span>
        {question && <span className="text-[10.5px] text-text-tertiary truncate">{question}</span>}
      </span>
      {aside}
    </div>
  )
}

function CardHero({ value, unit, cls, tip }: {
  value: React.ReactNode; unit: React.ReactNode; cls: string; tip: string
}) {
  return (
    <div data-fit-box className="flex items-baseline gap-2.5 flex-wrap mt-2 mb-0.5">
      <span className={`text-[34px] font-bold font-mono leading-none tracking-[-0.8px] tabular-nums ${cls}`}>{value}</span>
      <span className="text-[12px] text-text-tertiary">{unit}<InfoTip text={tip} /></span>
    </div>
  )
}

/** Label + ⓘ on the left, value on the right, nothing else. See PanelRow.tip for why. */
function PanelRows({ rows, delta }: {
  rows: PanelRow[]; delta?: (r: PanelRow) => React.ReactNode
}) {
  return (
    <div className="mt-auto pt-2.5 border-t border-border-subtle">
      {rows.map((r, i) => (
        <div key={r.key}
          className={`flex items-baseline justify-between gap-3 py-[4px] text-[12px] leading-[1.3] ${i < rows.length - 1 ? 'border-b border-border-subtle/60' : ''}`}>
          <span className="flex items-center text-text-tertiary min-w-0">
            <span className="truncate">{r.label}</span><InfoTip text={r.tip} />
          </span>
          <span className={`font-mono tabular-nums text-right whitespace-nowrap ${r.cls ?? 'text-text-primary'}`}>
            {r.value}{delta?.(r)}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Panel ────────────────────────────────────────────────────────────────────

export function PerformancePanel({
  run, fallback, equity = [], balance = null, compare = null, filtered = false,
  tailPct = null, limitPct = null, ribbon = null, verdict = null, collapsed = false,
}: {
  run: Run; fallback: FallbackMetrics; equity?: EquityPoint[]; balance?: number | null
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
  const d  = deriveKpis(run, fallback, equity, balance)
  const dc = compare ? deriveKpis(compare.run, compare.fallback, compare.equity, balance) : null

  const { sharpe, worstDay, worstStreak, calmar, expectancyUsd, zScore,
          pfValue, profitConc, maxDdPct, ddDollar, ddAtWorstPct, ddPeak,
          scratches, tradeConc } = d
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
  const multiple = (balance != null && balance > 0 && run.net_pnl != null)
    ? (balance + run.net_pnl) / balance
    : null
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
  const wins = run.win_count ?? (run.win_rate != null && run.trade_count != null
    ? Math.round(run.win_rate * run.trade_count) : null)
  const losses = (wins != null && run.trade_count != null) ? run.trade_count - wins : null
  const rr = (run.avg_win != null && run.avg_loss != null && run.avg_loss !== 0)
    ? run.avg_win / Math.abs(run.avg_loss) : null

  const madeRows: PanelRow[] = [
    // Net is the HERO now, so it is not repeated here. The multiple takes its place — the same
    // number the hero used to be, demoted because it is only meaningful beside the balance it
    // multiplies, which is now the caption directly above this list.
    { key: 'mult', label: 'Return on capital',
      value: multiple != null ? `${multiple.toFixed(1)}x` : '—',
      tip: `Final balance ÷ starting balance${startBal != null && startBal > 0 ? ` — what ${dollar(startBal)} became` : ''}. Moves with the Account balance slider, since it is measured against whatever capital you tell it. ⚠ At a fixed % risk per trade this is the number most distorted by compounding: a dollar not earned early is a dollar that never compounds, so a small cost early costs many times itself by the end. Compare strategies in R, not here.` },
    { key: 'per', label: 'Per trade', value: expectancyUsd != null ? dollar(expectancyUsd, true) : '—',
      cls: expectancyUsd != null && expectancyUsd < 0 ? 'text-neg-text' : undefined,
      tip: 'Expectancy: net P&L ÷ trade count — what one average trade was worth. Dollars only; expectancy in R needs the risk taken per trade, which stored trades do not carry.',
      cmp: k => k.expectancyUsd, fmt: fmtMoney },
    { key: 'rr', label: 'Avg win / loss', value: rr != null ? `${rr.toFixed(2)}:1` : '—',
      tip: `Average winning trade ÷ average losing trade. Together with the win rate this is the whole edge${
        run.avg_win != null && run.avg_loss != null ? `: ${dollar(run.avg_win, true)} per win against ${dollar(run.avg_loss)} per loss` : ''}.`,
      cmp: k => k.rrRatio, fmt: fmtRatio, goodWhen: 'higher' },
    { key: 'wr', label: 'Win rate', value: pct(run.win_rate),
      tip: `Share of trades that closed profitable${wins != null && losses != null ? ` — ${wins} wins, ${losses} losses` : ''}. A low win rate is not a fault on its own; read it against the average win/loss above.${scratches != null && scratches > 0 ? ` Read it against the scratch count below too — ${scratches} of these barely moved.` : ''} This run: ${winRateLabel(run.win_rate)}.`,
      cmp: k => k.winRate, fmt: fmtPct01 },
    // The row the win rate needed. A trade that made a sixth of a losing trade counts as a full
    // win above; on the shipped run that is 45 of 111 "winners", every one exiting at the
    // breakeven-stop buffer. Shown as the honest three-way split so the reader gets the shape,
    // not just a count. Exception colour past a quarter of the book — at that point the headline
    // win rate is describing something other than winning.
    { key: 'scr', label: 'Won / scratched / lost',
      value: (scratches != null && wins != null && losses != null && run.trade_count)
        ? `${wins - scratches} / ${scratches} / ${losses}` : '—',
      cls: (scratches != null && run.trade_count && scratches / run.trade_count >= 0.25)
        ? 'text-warn-text' : undefined,
      tip: `The win rate above counts any trade that closed a cent up as a win. A SCRATCH is one whose result came to less than ${Math.round(SCRATCH_FRACTION * 100)}% of this run's median losing trade — usually a stop moved to breakeven doing exactly its job, which is real risk control and is not an edge.${
        scratches != null && wins != null && run.trade_count
          ? ` Here ${pct((wins - scratches) / run.trade_count)} genuinely won, ${pct(scratches / run.trade_count)} scratched.`
          : ' No losing trade in this run, so there is no scale to measure a scratch against.'}` },
    { key: 'pf', label: 'Profit factor', value: kpiNum(pfValue),
      // Exception: below 1.0 the strategy loses money — the one PF value that must shout.
      cls: pfValue != null && isFinite(pfValue) && pfValue < 1 ? 'text-neg-text' : undefined,
      tip: `Gross wins ÷ gross losses. Above 2.0 is strong, 1.5 good, below 1.0 loses money. This run: ${pfLabel(pfValue)}.`,
      cmp: k => k.pfValue, fmt: fmtRatio },
    // Costs were charged but INVISIBLE until 2026-08-01: the run row carried the settings and
    // nothing reported what they came to. The row only appears on a priced run — printing
    // "$0" on every unpriced one would read as "trading was free" rather than "nothing was
    // priced". The tooltip carries the compounding warning because the raw charge is small and
    // its effect on the net is not.
    ...(costsTotal !== 0 ? [{
      key: 'costs', label: 'Costs charged', value: dollar(costsTotal),
      tip: `Commission, spread, slippage and swap actually charged across every fill, already deducted from Net above. ⚠ Read this against the RETURN, not the net dollars: at a fixed % risk the account compounds, so a dollar of cost paid early also costs every dollar it would have grown into. On this strategy ${dollar(Math.abs(costsTotal))} of charges moves the final balance by many times that.`,
    } as PanelRow] : []),
    // WHICH costs were charged, not just what they came to. A run that charged nothing and a run
    // made before the switches existed look identical from the total alone — and this lab's
    // recurring defect is exactly a number on screen whose provenance nothing states. `null`
    // means "made before layered costs", which is not the same answer as "charged nothing".
    ...(run.cost_layers != null ? [{
      key: 'costlayers', label: 'Costs charged for',
      value: run.cost_layers.length
        ? run.cost_layers.map(l => COST_LAYER_LABEL[l] ?? l).join(', ')
        : 'nothing',
      tip: run.cost_layers.length
        ? `The cost layers this run had switched on${run.broker_profile ? `, priced off the ${run.broker_profile} account` : ''}. Anything not listed was not charged at all.`
        : 'This run was deliberately frictionless — no spread, no swap, no commission, no slippage. That is the default, and it is what makes the result directly comparable to the TradingView Strategy Tester.',
    } as PanelRow] : []),
  ]

  const riskedRows: PanelRow[] = [
    { key: 'dd$', label: 'Deepest drop', value: ddDollar != null ? `−${dollar(ddDollar)}` : '—',
      tip: `The largest peak-to-trough fall measured in dollars. On a compounding run this is usually a DIFFERENT episode from the percentage above — a later, shallower fall off a much bigger account${
        ddDollar != null && maxDdPct != null && ddAtWorstPct != null && ddDollar > ddAtWorstPct
          ? `. Here the worst percentage cost ${dollar(ddAtWorstPct)} while the worst dollar figure is ${dollar(ddDollar)}` : ''}. The percentage is what would have ended the account; this is what it would have felt like.`,
      cmp: k => k.ddDollar, fmt: fmtMoney, goodWhen: 'lower' },
    { key: 'wd', label: 'Worst day', value: dollar(worstDay),
      tip: 'The single worst calendar day, summing every trade that closed on it.',
      cmp: k => k.worstDay, fmt: fmtMoney },
    // The unit is TRADES. backtest/output.py:_worst_losing_streak walks the trade list, not the
    // day list — it was labelled "days" here, which on a strategy trading twice a month reads as
    // a far worse run of luck than it was (4 losing trades spanned 2 consecutive losing days).
    // Exception at ≥6 only: 3 losses in a row is ordinary on a selective strategy, and colouring
    // it would make the amber mean nothing by the time a real streak showed up.
    { key: 'ws', label: 'Worst streak', value: worstStreak != null ? `${worstStreak} trades` : '—',
      cls: worstStreak != null && worstStreak >= 6 ? 'text-neg-text' : undefined,
      tip: 'The longest run of consecutive losing trades. Counted in trades, not days — a selective strategy can take weeks to produce four of them.',
      cmp: k => k.worstStreak, fmt: fmtCount, goodWhen: 'lower' },
    { key: 'uw', label: 'Time underwater', value: underwater != null ? `${(underwater * 100).toFixed(0)}%` : '—',
      tip: 'Share of the test\'s calendar span spent below the previous equity high. Max drawdown says how deep the hole was; this says how long you sat in it — the half that decides whether a strategy is holdable.',
      goodWhen: 'lower' },
  ]

  const trustedRows: PanelRow[] = [
    { key: 'conc', label: 'Profit concentration',
      value: profitConc != null ? `${profitConc.toFixed(0)}%` : '—',
      // Exception: ≥60% in one quarter is the classic curve-fit signal.
      cls: exceptionCls(concentrationCls(profitConc)),
      tip: `Share of gross profit earned in the single best quarter of the test span. Above 60% the edge is clustered in one window rather than repeatable — the classic curve-fit signal. Measured in returns, not dollars: on a compounding account the last quarter holds most of the dollars however evenly the edge is spread.${profitConc != null ? ` This run: ${concentrationLabel(profitConc)}.` : ''}`,
      cmp: k => k.profitConc, fmt: fmtPctPt, goodWhen: 'lower' },
    // The row above splits the span into QUARTERS, so it answers "did the edge show up in one
    // period". Readers hear the trade question, and the two can disagree completely: run
    // f866873aa862 is 34% by quarter (spread evenly over 6.6 years) while 5 of its 165 trades
    // made 47% of everything won. Not a defect on its own — a runner-based strategy is supposed
    // to be fat-tailed — but it is what says the edge lives in the tail.
    { key: 'tconc', label: `Top ${TRADE_CONCENTRATION_TOP_N} trades`,
      value: tradeConc != null ? `${tradeConc.toFixed(0)}%` : '—',
      cls: tradeConc != null && tradeConc >= 50 ? 'text-warn-text' : undefined,
      tip: `Share of gross profit made by the ${TRADE_CONCENTRATION_TOP_N} biggest winners. The row above asks whether the edge clustered in one PERIOD; this asks whether it came from a handful of TRADES, and a run can be spread evenly across the years while resting on five of them. High is not automatically bad — a strategy that rides runners is meant to be fat-tailed — but it tells you the edge lives in the tail, so size the risk for that.${tradeConc != null ? ` This run: ${tradeConcentrationLabel(tradeConc)}.` : ''}`,
      goodWhen: 'lower' },
    { key: 'sharpe', label: 'Sharpe', value: sharpe != null ? sharpe.toFixed(2) : '—',
      // Amber below 1.0 — an EXCEPTION colour, not a sign colour. Green for "positive" would
      // call 0.91 good; amber for "weak" is the threshold that should stop you, which is the
      // policy every other coloured row here follows.
      cls: sharpe != null && sharpe < 1 ? 'text-warn-text' : undefined,
      tip: `Return per unit of volatility, annualized from daily P&L. Above 2 is excellent, 1 is good, below 0.5 is poor. Every weekday in the run's span counts, flat days included as zero — a strategy that trades 20 days a year is not a 250-day strategy, and scoring only its active days inflated this figure roughly 3x (0.91 read as 2.98 until 2026-07-31). This run: ${sharpe != null ? sharpeLabel(sharpe, sharpeEst) : 'not computed'}.`,
      cmp: k => k.sharpe, fmt: fmtRatio },
    { key: 'z', label: 'Z-score', value: zScore != null ? zScore.toFixed(2) : '—',
      cls: exceptionCls(zScoreCls(zScore)),
      tip: `Wald–Wolfowitz runs test on the win/loss sequence: does it streak more than chance? Near 0 means the order looks random, which is what an honest edge produces. Past ±2 the wins and losses clump, and an equity curve built on clumps is fragile. This run: ${zScore != null ? zScoreLabel(zScore) : zScoreUnavailableLabel(equity)}.`,
      cmp: k => k.zScore, fmt: fmtRatio, goodWhen: 'none' },
    { key: 'dur', label: 'Avg hold', value: fmtHold(run.avg_trade_duration_min),
      tip: 'Average time a position was open, entry to exit. Read it against the bar size — a hold of a few bars is a different strategy from one that carries overnight.',
      cmp: k => k.avgDur, fmt: (x: number) => `${x >= 0 ? '+' : ''}${fmtHold(Math.abs(x))}`, goodWhen: 'none' },
  ]

  // The delta answers the question the news filter was opened to ask, so it is the one thing
  // allowed to sit beside a value. Rows that did not move say nothing — printing "unchanged vs
  // unfiltered" on every row was eight lines of text to communicate that nothing happened.
  const rowDelta = (r: PanelRow): React.ReactNode => {
    if (!dc || !r.cmp) return null
    const to = r.cmp(d), from = r.cmp(dc)
    if (to == null || from == null || !isFinite(to) || !isFinite(from)) return null
    const delta = to - from
    if (Math.abs(delta) < 1e-9) return null
    const good = r.goodWhen === 'lower' ? delta < 0 : delta > 0
    const cls = r.goodWhen === 'none' ? 'text-text-secondary' : good ? 'text-pos-text' : 'text-neg-text'
    return <span className={`${cls} tabular-nums`}> {(r.fmt ?? fmtRatio)(delta)}</span>
  }

  const rows = (list: PanelRow[]) => <PanelRows rows={list} delta={rowDelta} />

  // Hero delta: shown beside the big number, in the unit that number is stated in.
  const heroDelta = (to: number | null | undefined, from: number | null | undefined,
                     fmt: (x: number) => string, goodWhen: 'higher' | 'lower') => {
    if (!dc) return null
    if (to == null || from == null || !isFinite(to) || !isFinite(from)) return null
    const delta = to - from
    if (Math.abs(delta) < 1e-9) return <span className="text-[12px] text-text-tertiary">unchanged</span>
    const good = goodWhen === 'lower' ? delta < 0 : delta > 0
    return <span className={`text-[12px] tabular-nums ${good ? 'text-pos-text' : 'text-neg-text'}`}>{fmt(delta)}</span>
  }

  const cardCls = (top: string) => panelCardCls(collapsed, filtered, top)
  const head = (title: string, question: string, aside?: React.ReactNode) =>
    <CardHead title={title} question={question} aside={aside} />
  const hero = (value: React.ReactNode, unit: React.ReactNode, cls: string, tip: string) =>
    <CardHero value={value} unit={unit} cls={cls} tip={tip} />

  const madeTip = "Total profit and loss in dollars across every closed trade, after whatever commission and slippage the run was priced with. The starting balance is beneath it and the multiple is the first row, so what this grew FROM is on screen. ⚠ Dollars on a compounding account are not comparable between runs — a fixed % risk per trade makes the end figure exponential in the edge, so a small change early shows up as a huge change here. Rank strategies by R or profit factor; read this to know what the run was worth."
  const riskedTip = "Worst peak-to-trough drop as a % of the equity it fell FROM — the drawdown that would actually have ended the account. Measured against the running peak, not the starting balance: on a compounding run the account grows away from its opening capital, so dividing a late dollar drawdown by a static account_size reports a percentage that never happened (this read 1096.7% before 2026-07-30). The bar's gold tick is the selected ruleset's stated limit; the hatched extension past the fill is the worst-1% drawdown the stress test simulated. Each is drawn only when it actually exists."
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

        <div className={cardCls('border-t-2 border-t-pos-text/50')}>
          {head('Made', 'What came out of it')}
          {hero(
            <FitMoney n={run.net_pnl} signed />,
            'net',
            (run.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text',
            madeTip,
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

        <div className={cardCls('border-t-2 border-t-neg-text/50')}>
          {head('Risked', 'What it cost to hold',
            limitPct != null
              ? <span className="font-mono text-[10px] text-gold-text">vs {limitPct.toFixed(0)}% limit</span>
              : <span className="text-[10px] text-text-tertiary">no limit set</span>)}
          {hero(
            maxDdPct != null ? `${maxDdPct.toFixed(1)}%` : '—',
            'worst drawdown', maxDdPct != null ? 'text-neg-text' : 'text-text-tertiary', riskedTip,
          )}
          {/* The meter survives the collapse — it is the only thing on the page that says
              whether a drawdown number is acceptable, and it costs ~40px. */}
          {maxDdPct != null
            ? <DrawdownMeter pct={maxDdPct} limitPct={limitPct} tailPct={tailPct} />
            : <div className="mt-3.5 text-[11px] text-text-tertiary">Set an account balance to measure drawdown as a percentage.</div>}
          {!collapsed && (
            <div className="text-[10.5px] text-text-tertiary leading-[1.35] mt-1.5">
              {maxDdPct != null && ddAtWorstPct != null && ddPeak != null
                ? <>−{dollar(ddAtWorstPct)} off a {dollar(ddPeak)} peak.{' '}</>
                : null}
              {limitPct != null && maxDdPct != null && (maxDdPct >= limitPct
                ? <span className="text-neg-text">Breaches the {limitPct.toFixed(0)}% limit.{' '}</span>
                : <>Clears by {(limitPct - maxDdPct).toFixed(1)} pts.{' '}</>)}
              {tailPct != null
                ? <>Worst-1% simulated: {tailPct.toFixed(1)}%.</>
                : <>No stress test — the tail is unknown, not zero.</>}
            </div>
          )}
          {!collapsed && rows(riskedRows)}
        </div>

        <div className={cardCls('border-t-2 border-t-accent/45')}>
          {/* No trade count here — it is the verdict card's hero, two columns across. Printing
              it twice on one row made the second copy read as a different number. */}
          {head('Trusted', 'Whether to believe it')}
          {hero(kpiNum(calmar), 'Calmar', calmarCls(calmar), trustedTip)}
          {dc
            ? <div className="mb-1">{heroDelta(d.calmar, dc.calmar, fmtRatio, 'higher')}</div>
            : <div className="text-[11px] text-text-tertiary leading-snug mt-2">{calmarLabel(calmar)}</div>}
          {!collapsed && rows(trustedRows)}
        </div>

      </div>
    </div>
  )
}
// ── Regime overlay — colored line design ──────────────────────────────────────

const _OVERLAY_KEY = 'regime_overlay_enabled'
function getOverlayPref(): boolean {
  try { return localStorage.getItem(_OVERLAY_KEY) !== 'false' } catch { return true }
}
function setOverlayPref(v: boolean) {
  try { localStorage.setItem(_OVERLAY_KEY, String(v)) } catch { /* quota */ }
}

// Per-series equity-chart toggles (histogram / excursions / run-ups & drawdowns). Default OFF so the
// chart stays clean until the user opts in; each persists like the regime overlay.
function getBoolPref(key: string): boolean {
  try { return localStorage.getItem(key) === 'true' } catch { return false }
}
function setBoolPref(key: string, v: boolean) {
  try { localStorage.setItem(key, String(v)) } catch { /* quota */ }
}
const _HIST_KEY = 'equity_histogram_enabled'
const _RUD_KEY  = 'equity_runup_drawdown_enabled'

// Performance panel collapse. Defaults COLLAPSED (hence its own getter — getBoolPref defaults
// off): expanded, the panel plus its header fills the fold on a laptop and pushes the equity
// curve entirely off screen, and the headline and the curve are read together. The three hero
// numbers and the drawdown meter survive the collapse, so the default still answers "how did
// this run do" without a click.
const _PERF_COLLAPSED_KEY = 'performance_panel_collapsed'
function getPerfCollapsed(): boolean {
  try { return localStorage.getItem(_PERF_COLLAPSED_KEY) !== 'false' } catch { return true }
}

interface RegimeBand { x1: number; x2: number; regime: string }

// Run-ups & drawdowns ribbon: each point is a "run-up" (equity at/above its running peak — green)
// or a "drawdown" (below the prior peak — red). Contiguous same-state points merge into one band;
// TradingView draws this as a thin colour strip along the bottom of the equity panel.
interface RudBand { x1: number; x2: number; up: boolean }
function computeRunupDrawdownBands(data: EquityPoint[], xOf: (p: EquityPoint) => number): RudBand[] {
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
function computeSizedRegimeBands(timeline: SizedTimelineDay[], dailyPnl: DailyPnlPoint[]): RegimeBand[] {
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
function trimToLastActive(tl: SizedTimelineDay[]): SizedTimelineDay[] {
  let last = -1
  for (let i = tl.length - 1; i >= 0; i--) {
    if (tl[i].trades_taken > 0) { last = i; break }
  }
  return last >= 0 ? tl.slice(0, last + 1) : tl
}

// ── Equity curve ──────────────────────────────────────────────────────────────

function fmtChartDate(d?: string): string {
  if (!d) return ''
  const dt = new Date(d.slice(0, 10) + 'T12:00:00')
  const yr = String(dt.getFullYear()).slice(-2)
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ` '${yr}`
}

const _money0 = (v: number) => `${v >= 0 ? '+' : '−'}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`

const DAY_MS = 86_400_000

export function EquityCurveChart({ data, bands = [], showHistogram = false, showRunupDrawdown = false, height = 300, xMode = 'date', windowStart = null, overlayLines = [] }: {
  data: EquityPoint[]; bands?: RegimeBand[]
  showHistogram?: boolean; showRunupDrawdown?: boolean; height?: number
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
  const hasExc = data.some(d => d.favorable != null || d.adverse != null)
  const showExcursions = showHistogram && hasExc
  const showProfitBars = showHistogram && !hasExc

  // Break-even = the STARTING BALANCE, not the first trade's equity. The curve is anchored on the
  // account's opening balance and the first point already includes trade #1's P&L, so subtract it
  // back out: startEq = opening balance. Green above it, red below, and the flip lands exactly on
  // this horizontal line — regardless of what the starting balance is.
  const startEq    = (data[0]?.equity ?? 0) - (data[0]?.profit ?? 0)
  // Anchor the curve on the STARTING BALANCE: prepend a synthetic point at the opening balance so
  // the line visibly leaves the start line (TradingView does this). The anchor carries no trade —
  // it draws no dot, no histogram bar, and its tooltip just reports the starting balance.
  const byDate     = xMode === 'date'
  const firstIdx   = data[0]?.index ?? 1
  const firstMs    = dateMs(data[0]?.date) ?? Date.now()
  // `x` is the plotted position: a real timestamp in date mode, the trade number otherwise. Every
  // band/ribbon below is expressed in the same units, so switching mode moves the whole chart
  // together.
  const anchorX = byDate
    ? Math.min(dateMs(windowStart) ?? firstMs - DAY_MS, firstMs - DAY_MS)
    : firstIdx - 1
  const chartData: (EquityPoint & { _anchor?: boolean; x: number })[] = [
    // The anchor also seeds every overlay line at the starting balance, so the strategy lines leave
    // the same origin as the portfolio line instead of appearing to start at their first trade.
    { index: firstIdx - 1, equity: startEq, _anchor: true, x: anchorX,
      ...Object.fromEntries(overlayLines.map(ol => [ol.id, startEq])) },
    ...data.map(d => ({ ...d, x: byDate ? (dateMs(d.date) ?? firstMs) : d.index })),
  ]
  // Overlay values count toward the y-range too — a strategy line can dip below the portfolio's low.
  const allValues  = [
    ...data.map(d => d.equity),
    ...overlayLines.flatMap(ol => data.map(d => (d as unknown as Record<string, unknown>)[ol.id]).filter((v): v is number => typeof v === 'number')),
  ]
  const min = Math.min(...allValues)
  const max = Math.max(...allValues)
  const pad = (max - min) * 0.1 || 500
  const yMin = Math.min(startEq, min) - pad
  const yMax = max + pad

  // The colour-split offset must map to the FILLED SHAPE's bounding box — the data extremes incl.
  // startEq, NOT the padded axis domain. Using the padded domain drifts the green/red boundary off
  // the start line and bleeds a faint red tint into the positive region.
  const dMin = Math.min(startEq, min)
  const dMax = Math.max(startEq, max)
  const startOffset = Math.min(1, Math.max(0, (dMax - startEq) / ((dMax - dMin) || 1)))
  const eqTicks    = byDate
    ? monthTicks(anchorX, chartData[chartData.length - 1].x)
    : calIndexTicks(data)

  // Y ticks anchored ON the starting balance so it's always labelled, evenly spaced around it.
  const yTicks = balanceTicks(startEq, yMin, yMax)

  // Profit histogram rides its own hidden axis, scaled to a bottom strip: domain [-barMax, 6×barMax]
  // puts the zero baseline ~14% up so green bars rise and red bars drop within the bottom band.
  const barMax = showProfitBars
    ? Math.max(1, ...data.map(d => Math.abs(d.profit ?? 0)))
    : 1

  // Run-up / drawdown ribbon segments, and a thin band at the very bottom of the plot to draw it in.
  // Pull the first segment left to the anchor so the ribbon spans the full axis (the curve starts at
  // the anchor point, one step left of the first trade).
  const rudBands = showRunupDrawdown
    ? computeRunupDrawdownBands(data, d => (byDate ? (dateMs(d.date) ?? firstMs) : d.index))
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
  const shown = bands.filter(b => b.regime !== 'UNKNOWN')
  const plotBands = shown.map((b, i) => ({
    ...b,
    x1: i === 0 ? Math.min(b.x1, anchorX) : b.x1,
    x2: i === shown.length - 1 ? Math.max(b.x2, lastX) : b.x2,
  }))
  const rudY2 = yMin + (yMax - yMin) * 0.025

  return (
    <ResponsiveContainer key={`${bands.length}-${showHistogram}-${showExcursions}-${showRunupDrawdown}-${xMode}`} width="100%" height={height}>
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
            <stop offset={0}                     stopColor={C.pos} stopOpacity={0.22} />
            <stop offset={Math.max(0, startOffset - 0.0001)} stopColor={C.pos} stopOpacity={0.03} />
            <stop offset={startOffset}           stopColor={C.neg} stopOpacity={0.03} />
            <stop offset={1}                     stopColor={C.neg} stopOpacity={0.20} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
        {/* Regime context as faint full-height background bands — skip UNKNOWN so the chart shows
            exactly the regimes in the legend (a run tags only the regimes it actually saw). */}
        {plotBands.map((b, i) => (
          // ifOverflow="visible": the first/last band are deliberately pushed to the plot edges, and
          // Recharts' default is to DISCARD a reference area whose bound sits outside the domain.
          <ReferenceArea key={`r${i}`} x1={b.x1} x2={b.x2} ifOverflow="visible"
            fill={REGIME_COLORS[b.regime] ?? REGIME_COLORS.UNKNOWN} fillOpacity={0.1} stroke="none" />
        ))}
        <XAxis
          dataKey="x"
          ticks={eqTicks}
          // Date mode: a true time axis (regime bands then span their real calendar width).
          // Trade mode: point scale keeps the line flush to the axis whether or not the histogram
          // bars are on — a bar series otherwise switches the axis to band scale, which pads both
          // sides and shifts the curve right, opening a gap between the y-axis and the start line.
          {...(byDate
            ? { type: 'number' as const, scale: 'time' as const, domain: ['dataMin', 'dataMax'] as [string, string] }
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
          tickFormatter={(v: number) => {
            if (Math.abs(v) < 1000) return `$${Math.round(v)}`
            const k = v / 1000
            return `$${Number.isInteger(k) ? k : k.toFixed(1)}k`
          }}
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
            const eq = payload.find((p: { dataKey?: string | number }) => p.dataKey === 'equity') ?? payload[0]
            if (!eq) return null
            const pt = (eq as { payload?: EquityPoint & { _anchor?: boolean } }).payload
            const v  = ((eq as { value?: number }).value ?? 0)
            if (pt?._anchor) return (
              <div style={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}>
                <p style={{ color: C.axisTick, marginBottom: 4 }}>Starting balance</p>
                <p style={{ color: '#e5e7eb' }}>${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}</p>
              </div>
            )
            const dateStr = pt?.date ? ` · ${fmtChartDate(pt.date)}` : ''
            const dirStr  = pt?.direction ? ` · ${pt.direction}` : ''
            const hasFav = pt?.favorable != null || pt?.adverse != null
            return (
              <div style={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}>
                <p style={{ color: C.axisTick, marginBottom: 4 }}>Trade #{pt?.index}{dateStr}{dirStr}</p>
                <p style={{ color: '#e5e7eb' }}>
                  Balance&nbsp;${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </p>
                {pt?.profit != null && (
                  <p style={{ color: (pt.profit ?? 0) >= 0 ? C.pos : C.neg }}>This trade&nbsp;{_money0(pt.profit)}</p>
                )}
                {hasFav && (
                  <>
                    <p style={{ color: C.pos }}>Favorable excursion&nbsp;{_money0(pt?.favorable ?? 0)}</p>
                    <p style={{ color: C.neg }}>Adverse excursion&nbsp;{_money0(pt?.adverse ?? 0)}</p>
                  </>
                )}
              </div>
            )
          }}
        />
        <ReferenceLine y={startEq} stroke={C.refLine} strokeDasharray="4 4" />
        {/* Run-ups & drawdowns ribbon: a thin strip along the very bottom, green while the equity is
            making new highs, red while it sits under a prior peak. */}
        {rudBands.map((b, i) => (
          <ReferenceArea key={`rud${i}`} x1={b.x1} x2={b.x2} y1={yMin} y2={rudY2}
            fill={b.up ? C.pos : C.neg} fillOpacity={0.85} stroke="none" />
        ))}
        {/* Per-trade realised profit histogram (runs without excursion data) — muted so the line reads on top. */}
        {showProfitBars && (
          <Bar yAxisId="bars" dataKey="profit" isAnimationActive={false} maxBarSize={28}>
            {chartData.map((d, i) => <Cell key={i} fill={(d.profit ?? 0) >= 0 ? C.pos : C.neg} fillOpacity={0.35} />)}
          </Bar>
        )}
        {/* Combined trade-excursion bar (TradingView-style): translucent green halo up to the favorable
            excursion, translucent red halo down to the adverse, and a solid net-result core between —
            one bar per trade, in true dollars anchored on the starting-balance line so the bars sit on
            the same baseline as the equity curve. Driven off a hidden bar (exc axis, base 0 = the
            starting-balance line) whose pixel height gives the $-per-pixel scale for the custom shape. */}
        {showExcursions && (
          <Bar yAxisId="exc" dataKey={(d: EquityPoint) => Math.max(d.favorable ?? 0, -(d.adverse ?? 0), 0)}
            isAnimationActive={false} maxBarSize={28}
            shape={(props: { x?: number; y?: number; width?: number; height?: number; payload?: EquityPoint & { _anchor?: boolean } }) => {
              const { x = 0, y = 0, width = 0, height = 0, payload } = props
              const fav = payload?.favorable ?? 0
              const adv = payload?.adverse ?? 0
              const profit = payload?.profit ?? 0
              const scale = Math.max(fav, -adv, 0)
              if (payload?._anchor || scale <= 0 || height <= 0) return <g />
              const ppd   = height / scale        // pixels per dollar (bar spans startEq → startEq+scale)
              const zeroY = y + height             // pixel of the starting-balance line
              const w  = width                     // fill the category slot (Recharts already sized it)
              const bx = x
              const favY  = zeroY - fav * ppd
              const advY  = zeroY - adv * ppd      // adv ≤ 0 → below the line
              const profY = zeroY - profit * ppd
              return (
                <g>
                  {fav > 0 && <rect x={bx} y={favY} width={w} height={zeroY - favY} fill={C.pos} fillOpacity={0.28} />}
                  {adv < 0 && <rect x={bx} y={zeroY} width={w} height={advY - zeroY} fill={C.neg} fillOpacity={0.28} />}
                  {profit >= 0
                    ? <rect x={bx} y={profY} width={w} height={Math.max(0, zeroY - profY)} fill={C.pos} fillOpacity={0.6} />
                    : <rect x={bx} y={zeroY} width={w} height={Math.max(0, profY - zeroY)} fill={C.neg} fillOpacity={0.6} />}
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
          dot={(props: { cx?: number; cy?: number; index?: number; payload?: EquityPoint & { _anchor?: boolean } }) => {
            const { cx, cy, payload, index } = props
            if (cx == null || cy == null || payload?._anchor) return <g key={index} />
            const up = (payload?.equity ?? 0) >= startEq
            return <circle key={index} cx={cx} cy={cy} r={3} fill={up ? C.pos : C.neg} stroke={C.tooltipBg} strokeWidth={1} />
          }}
          // Hover dot must match the point's own colour (red below the start line, green above) —
          // a fixed colour showed green even on underwater points.
          activeDot={(props: { cx?: number; cy?: number; index?: number; payload?: EquityPoint & { _anchor?: boolean } }) => {
            const { cx, cy, payload, index } = props
            if (cx == null || cy == null || payload?._anchor) return <g key={index} />
            const up = (payload?.equity ?? 0) >= startEq
            return <circle key={index} cx={cx} cy={cy} r={4.5} fill={up ? C.pos : C.neg} stroke={C.tooltipBg} strokeWidth={1.5} />
          }}
          baseValue={startEq}
          isAnimationActive={false}
        />
        {/* Per-strategy overlay lines (portfolio stack). Keyed on fields the caller attached to
            each point, so they ride the same x-axis as the main curve. connectNulls skips the
            synthetic start anchor (which carries no overlay values). */}
        {overlayLines.map(ol => (
          <Line key={ol.id} type="monotone" dataKey={ol.id} stroke={ol.color} strokeWidth={1.5}
            isAnimationActive={false} connectNulls
            // A dot only on the points that are THIS line's own trades — every point carries every
            // leg's running balance, so without the owner check each line would dot on every trade.
            dot={(props: { cx?: number; cy?: number; index?: number; payload?: { _legOwner?: string } }) => {
              const { cx, cy, payload, index } = props
              if (cx == null || cy == null || payload?._legOwner !== ol.id) return <g key={index} />
              return <circle key={index} cx={cx} cy={cy} r={2.5} fill={ol.color} stroke={C.tooltipBg} strokeWidth={1} />
            }}
            activeDot={(props: { cx?: number; cy?: number; index?: number; payload?: { _legOwner?: string } }) => {
              const { cx, cy, payload, index } = props
              if (cx == null || cy == null || payload?._legOwner !== ol.id) return <g key={index} />
              return <circle key={index} cx={cx} cy={cy} r={4} fill={ol.color} stroke={C.tooltipBg} strokeWidth={1.5} />
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

function SizedEquityCurveChart({ data, bands = [], height = 300 }: {
  data: SizedTimelineDay[]; bands?: RegimeBand[]; height?: number
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
  const endBal   = rows[rows.length - 1].balance
  const profitable = endBal >= startBal
  const lineColor  = profitable ? C.pos : C.neg

  const vals = rows.flatMap(r => [r.balance, ...(r.floor != null ? [r.floor] : [])])
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const pad = (max - min) * 0.08 || 500

  // Mark days where a breach happened or the engine halted trading.
  const breachIdx = rows.findIndex(r => r.floor != null && r.balance < r.floor)
  const haltDays  = rows.filter(r => r.halt)

  // X ticks: first, ~quarterly, last (calendar-spaced, matching the other charts).
  const step = Math.max(1, Math.floor(rows.length / 5))
  const xTicks = rows.filter((_, i) => i === 0 || i === rows.length - 1 || i % step === 0).map(r => r.i)

  return (
    <ResponsiveContainer key={bands.length ? 'regime' : 'base'} width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <defs>
          <linearGradient id="sizedFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor={lineColor} stopOpacity={0.18} />
            <stop offset="95%" stopColor={lineColor} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
        {bands.map((b, i) => (
          <ReferenceArea key={i} x1={b.x1} x2={b.x2} fill={REGIME_COLORS[b.regime] ?? REGIME_COLORS.UNKNOWN} fillOpacity={0.1} stroke="none" />
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
          tickFormatter={(v: number) => {
            const k = v / 1000
            return `$${Number.isInteger(k) ? k : k.toFixed(1)}k`
          }}
          width={56}
        />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const r = payload[0]?.payload as (typeof rows)[number] | undefined
            if (!r) return null
            return (
              <div style={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}>
                <p style={{ color: C.axisTick, marginBottom: 4 }}>{fmtChartDate(r.date)}</p>
                <p style={{ color: '#e5e7eb' }}>Balance&nbsp;${r.balance.toLocaleString('en-US', { maximumFractionDigits: 0 })}</p>
                {r.floor != null && (
                  <p style={{ color: C.neg }}>Floor&nbsp;${r.floor.toLocaleString('en-US', { maximumFractionDigits: 0 })}</p>
                )}
                {r.buffer != null && (
                  <p style={{ color: C.axisTick }}>Buffer&nbsp;${r.buffer.toLocaleString('en-US', { maximumFractionDigits: 0 })}</p>
                )}
                <p style={{ color: C.axisTick }}>{r.trades} trade{r.trades === 1 ? '' : 's'} · {r.contracts} contracts</p>
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
        {haltDays.map(d => (
          <ReferenceDot key={`h${d.i}`} x={d.i} y={d.balance} r={3} fill={C.gold} stroke="none" />
        ))}
        {breachIdx >= 0 && (
          <ReferenceDot x={rows[breachIdx].i} y={rows[breachIdx].balance} r={4.5} fill={C.neg} stroke={C.tooltipBg} strokeWidth={1.5} />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// The sized-run label, in one place — three surfaces show it and they must agree.
function sizingModeLabel(mode: SizingMode, manualPct?: number | null): string {
  if (mode === 'manual') return `Manual ${manualPct ?? '?'}%`
  return mode === 'bullet' ? 'Bullet' : 'Consistent'
}

function SizedCurveLegend({ mode, manualPct, profitable = true }:
    { mode: SizingMode; manualPct?: number | null; profitable?: boolean }) {
  return (
    <div className="flex items-center gap-4 mt-2 text-[11px] text-text-tertiary">
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-3 h-[2px] rounded-full" style={{ background: profitable ? C.pos : C.neg }} />
        End-of-day balance
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-3 border-t-2 border-dashed" style={{ borderColor: C.neg }} />
        Trailing risk floor (breach = fail)
      </span>
      <span className="ml-auto font-medium text-text-secondary">
        Engine-sized · {sizingModeLabel(mode, manualPct)}
      </span>
    </div>
  )
}

// ── Drawdown chart ────────────────────────────────────────────────────────────

export function DrawdownChart({ equity, limitLines, height = 140 }: {
  equity: EquityPoint[]
  limitLines?: Array<{ limit: number; label: string; pass: boolean }>
  height?: number
}) {
  if (!equity.length) return null

  let peak = equity[0].equity
  const ddData = equity.map(pt => {
    if (pt.equity > peak) peak = pt.equity
    const dd = peak !== 0 ? pt.equity - peak : 0
    return { index: pt.index, drawdown: Math.round(dd), date: pt.date }
  })

  const worst  = Math.min(...ddData.map(d => d.drawdown))
  const ddTicks = calIndexTicks(ddData)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={ddData} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
        <defs>
          <linearGradient id="ddGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor={C.neg} stopOpacity={0.12} />
            <stop offset="95%" stopColor={C.neg} stopOpacity={0.30} />
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
            return calTickLabel(date, v === ddData[0].index || v === ddData[ddData.length - 1].index)
          }}
        />
        <YAxis
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => v === 0 ? '$0' : `$${(v / 1000).toFixed(0)}k`}
          width={56}
          domain={[worst * 1.1, 0]}
        />
        <Tooltip
          contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}
          formatter={(v: number) => [`$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`, 'Drawdown']}
          labelFormatter={(_: unknown, payload: Array<{ payload?: { index: number; date?: string } }>) => {
            const pt = payload?.[0]?.payload
            if (!pt) return ''
            const dateStr = pt.date ? ` · ${fmtChartDate(pt.date)}` : ''
            return `Trade #${pt.index}${dateStr}`
          }}
        />
        <ReferenceLine y={0} stroke={C.refLine} />
        {limitLines?.map(ll => (
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

function RegimeLegend({ bands }: { bands: RegimeBand[] }) {
  const regimes = [...new Set(bands.map(b => b.regime))].filter(r => r !== 'UNKNOWN')
  if (!regimes.length) return null
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 px-2 mt-2 mb-1">
      {regimes.map(regime => (
        <div key={regime} className="flex items-center gap-1.5">
          <div style={{ width: 12, height: 12, background: REGIME_COLORS[regime] ?? REGIME_COLORS.UNKNOWN, borderRadius: 3 }} />
          <span className="text-[10px] text-text-tertiary">{REGIME_LABEL[regime] ?? regime}</span>
        </div>
      ))}
    </div>
  )
}

// Generic on/off pill for an equity-chart series (histogram / excursions / run-ups & drawdowns).
export function SeriesToggle({ label, on, onChange }: { label: string; on: boolean; onChange: (v: boolean) => void }) {
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
  const trades = equity.filter(pt => pt.direction && pt.profit != null)
  if (!trades.length) return null

  const sides = ['Long', 'Short'] as const
  const stats = sides.map(dir => {
    const group    = trades.filter(pt => pt.direction === dir)
    const wins     = group.filter(pt => (pt.profit ?? 0) > 0).length
    const losses   = group.length - wins
    const totalPnl = group.reduce((s, pt) => s + (pt.profit ?? 0), 0)
    const avgTrade = group.length ? totalPnl / group.length : 0
    return { dir, count: group.length, wins, losses, totalPnl, avgTrade }
  }).filter(s => s.count > 0)

  return (
    <div className="grid grid-cols-2 gap-4">
      {stats.map((s, i) => {
        const winPct = Math.round((s.wins / s.count) * 100)
        const pnlCls = s.totalPnl >= 0 ? 'text-pos-text' : 'text-neg-text'
        // Lost first so the animation sweeps red → green (losing to winning)
        const data = [
          { name: 'Lost', value: s.losses },
          { name: 'Won',  value: s.wins },
        ]
        return (
          <div key={s.dir} className="flex flex-col items-center gap-1">
            <div className="text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.5px]">{s.dir}</div>
            <div className={`text-[15px] font-semibold font-mono tabular-nums ${pnlCls}`}>{dollar(s.totalPnl, true)}</div>
            <ResponsiveContainer width="100%" height={118}>
              <PieChart>
                <Pie
                  data={data}
                  cx="50%" cy="50%"
                  innerRadius={36} outerRadius={52}
                  startAngle={90} endAngle={-270}
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
                  <Label value={`${winPct}%`} position="center" fill="#e6edf3" fontSize={16} fontWeight={700} />
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="text-[10px] text-text-tertiary">{s.count} trades · avg {dollar(s.avgTrade, true)}/trade</div>
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

export function DailyPnlChart({ data, netPnl, height = 260 }: { data: DailyPnlPoint[]; netPnl: number | null; height?: number }) {
  if (!data.length) {
    return (
      <div className="h-[160px] flex flex-col items-center justify-center gap-2 text-center px-6">
        <div className="text-text-secondary text-[13px] font-medium">No daily P&L data yet</div>
        <div className="text-text-tertiary text-[11px]">Available once the backtest report has been parsed.</div>
      </div>
    )
  }

  const halfTarget = netPnl != null && netPnl > 0 ? netPnl * 0.5 : null
  const pnlTicks  = calDateTicks(data)

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
          tickFormatter={(d: string) => calTickLabel(d, d === data[0].date || d === data[data.length - 1].date)}
        />
        <YAxis
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
          width={52}
        />
        <Tooltip
          cursor={{ fill: 'rgba(255,255,255,0.04)' }}
          contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}
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
            label={{ value: '50% of target', fill: C.gold, fontSize: 10, position: 'insideTopRight' }}
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

// ── Evaluation card ───────────────────────────────────────────────────────────

function isPersonal(ev: EvaluationDetail): boolean {
  return ev.ruleset_type === 'personal' || ev.ruleset_type === 'demo'
}

// breach_count counts fired personal DISCARD conditions (0–2); drawdown_pass says
// whether the drawdown condition was one of them — the remainder is the streak.
function personalStreakPass(ev: EvaluationDetail): boolean {
  return ev.breach_count - (ev.drawdown_pass ? 0 : 1) <= 0
}

// Compact ruleset chip that doubles as the firm switcher. Lives in BOTH header layouts (full and
// condensed sticky) so you can page firms without scrolling back to the eval card, and shows only
// the SELECTED firm — listing all four overflowed into the action buttons. Chevrons appear only for
// multi-firm runs; a single-firm run is just the name.
function HeaderRulesetChip({ evals, selected, onSelect, compact = false }: {
  evals: EvaluationDetail[]; selected: number; onSelect: (i: number) => void; compact?: boolean
}) {
  if (!evals.length) return null
  const idx = Math.min(selected, evals.length - 1)
  const multi = evals.length > 1
  const py = compact ? 'py-[1px]' : 'py-[2px]'
  // Tighter left/right padding when chevrons sit inside the pill; symmetric when it's just a name.
  const px = multi
    ? (compact ? 'pl-1 pr-1.5' : 'pl-1.5 pr-2')
    : (compact ? 'px-1.5' : 'px-2')
  const chev = "flex items-center text-warn-text/50 hover:text-warn-text transition-colors flex-shrink-0"
  return (
    <span className={`inline-flex items-center gap-1 rounded text-[11px] font-semibold font-mono bg-warn-muted border border-warn-text/20 text-warn-text flex-shrink-0 ${py} ${px}`}>
      {multi && (
        <button className={chev} aria-label="Previous firm"
          onClick={() => onSelect((idx - 1 + evals.length) % evals.length)}>
          <ChevronLeft size={13} />
        </button>
      )}
      <span className="truncate max-w-[200px]">{evals[idx].ruleset_id}</span>
      {multi && (
        <>
          <span className="text-warn-text/50 tabular-nums flex-shrink-0">{idx + 1}/{evals.length}</span>
          <button className={chev} aria-label="Next firm"
            onClick={() => onSelect((idx + 1) % evals.length)}>
            <ChevronRight size={13} />
          </button>
        </>
      )}
    </span>
  )
}

// ── Verdict card ─────────────────────────────────────────────────────────────
// The FOURTH card, right of Trusted. It was a full-width bar above the three, and before that
// a fixed 300×196px evaluation panel — which `unconstrained` (no rules by design) had nothing
// to fill, so it rendered empty next to a green PASS. The bar fixed that by costing no height
// when it had little to say; a card that shares the row costs none at all, which is a whole
// row (44px + its gap) off the panel in both states.
//
// Moving it is only safe because the CONTENT changed shape with it. As a bar the rules were
// inline pills, laid out by wrap — fine at 1330px, five lines at a quarter of that, and since
// the grid is items-stretch a tall fourth card drags the other three with it. As rows they are
// 24px each whatever they say, and each rule's explanation moves from a `title` attribute
// nobody discovers to the same ⓘ every other row on this panel uses.
//
// The trade count is the card's HERO: it is the sample size every other number on the page
// rests on, so it gets the same 34px the other three heroes get, plus the cadence (trades per
// month) that the repo's own design target is stated in.

const VERDICT_CHIP: Record<string, { label: string; cls: string; top: string; Icon: typeof CheckCircle }> = {
  PASS:    { label: 'Pass',       cls: 'bg-pos-muted text-pos-text',        top: 'border-t-pos-text/50',      Icon: CheckCircle },
  WARN:    { label: 'Warn',       cls: 'bg-warn-muted text-warn-text',      top: 'border-t-warn-text/50',     Icon: Minus },
  DISCARD: { label: 'Discard',    cls: 'bg-neg-muted text-neg-text',        top: 'border-t-neg-text/50',      Icon: XCircle },
  // Not a grade — the absence of one. `unconstrained` states no limit, so nothing was
  // checked and there is nothing to pass. Neutral on purpose: a green tick here used to
  // claim a verdict the backend explicitly refuses to give (services/evaluator.py).
  // border-strong, not border-default: as a card's top edge the latter is indistinguishable from
  // the card's own border, so the one card in four without a colour read as unfinished rather
  // than as neutral. Neutral still has to be visible to mean anything.
  INFO:    { label: 'Not graded', cls: 'bg-bg-sunken text-text-tertiary',   top: 'border-t-border-strong',    Icon: Info },
}

const UNGRADED_TIP = "Every grade is a statement about drawdown against a limit. This ruleset deliberately sets none — no daily cap, no drawdown floor — so zero checks ran and there is nothing to pass or fail. It reports the strategy's raw behaviour instead. Pick a ruleset with a stated limit to grade this run: `personal_forex_risk` is this one's gradeable twin, the same raw behaviour with one stated bar."

/** One row per stated rule, pass or fail. Empty when the ruleset states none. */
function verdictRuleRows(ev: EvaluationDetail): PanelRow[] {
  const mark = (pass: boolean): PanelRow['value'] =>
    pass ? <CheckCircle size={13} className="inline" /> : <XCircle size={13} className="inline" />
  const cls = (pass: boolean) => pass ? 'text-pos-text' : 'text-neg-text'
  const out: PanelRow[] = []

  if (isPersonal(ev)) {
    if (ev.personal_max_drawdown_from_peak_pct != null) {
      out.push({ key: 'dd', label: `Drawdown ≤ ${ev.personal_max_drawdown_from_peak_pct}%`,
        value: mark(ev.drawdown_pass), cls: cls(ev.drawdown_pass),
        tip: 'Measured peak-relative, at end of day.' })
    }
    if (ev.personal_daily_loss_cap != null && ev.personal_max_consecutive_loss_days != null) {
      const pass = personalStreakPass(ev)
      out.push({ key: 'streak', label: `< ${ev.personal_max_consecutive_loss_days} capped days`,
        value: mark(pass), cls: cls(pass),
        tip: `Days in a row that hit the −$${ev.personal_daily_loss_cap.toLocaleString()} daily loss cap.` })
    }
    return out
  }

  out.push({ key: 'dd', label: `Daily DD ≤ $${ev.firm_max_loss_eod.toLocaleString()}`,
    value: mark(ev.drawdown_pass), cls: cls(ev.drawdown_pass),
    tip: 'End-of-day trailing max loss — the firm\'s hard floor.' })
  if (ev.firm_profit_target > 0) {
    out.push({ key: 'tgt', label: `Target $${ev.firm_profit_target.toLocaleString()}`,
      value: mark(ev.target_pass), cls: cls(ev.target_pass),
      tip: 'Net P&L required to pass the evaluation.' })
  }
  if (ev.consistency_pass != null && ev.firm_consistency_pct != null) {
    out.push({ key: 'con',
      label: `Consistency ${ev.largest_day_share_pct != null ? `${ev.largest_day_share_pct.toFixed(0)}%` : ''}`.trim(),
      value: mark(ev.consistency_pass), cls: cls(ev.consistency_pass),
      tip: `No single day may hold more than ${ev.firm_consistency_pct}% of total P&L.` })
  }
  return out
}

// Sample size + cadence. Trades per month is the unit CLAUDE.md's Trading Philosophy states
// the design target in ("a couple of times a month"), so the panel reports it in that unit
// rather than leaving the reader to divide.
function TradeCountAnchor({ count, of, spanDays }: {
  count: number; of?: number | null; spanDays: number | null
}) {
  const months = spanDays != null && spanDays > 0 ? spanDays / 30.44 : null
  const perMonth = months != null && months >= 1 ? count / months : null
  const years = months != null ? months / 12 : null
  return (
    <div className="ml-auto flex items-center gap-2.5 pl-4 border-l border-border-subtle shrink-0">
      <span className="text-[25px] font-bold font-mono leading-none text-accent tabular-nums">{count}</span>
      <span className="flex flex-col leading-[1.25]">
        <span className="text-[11px] font-bold uppercase tracking-[0.9px] text-text-secondary">
          {of != null && of !== count ? `of ${of} trades` : 'Trades'}
        </span>
        {(years != null || perMonth != null) && (
          <span className="font-mono text-[10px] text-text-tertiary">
            {years != null && years >= 1 ? `${years.toFixed(1)} yrs` : months != null ? `${months.toFixed(0)} mo` : ''}
            {years != null && perMonth != null ? ' · ' : ''}
            {perMonth != null ? `≈${perMonth < 1 ? perMonth.toFixed(1) : perMonth.toFixed(0)}/month` : ''}
          </span>
        )}
      </span>
    </div>
  )
}

function VerdictCard({ ev, tradeCount, totalTrades, spanDays, filtered, collapsed }: {
  ev: EvaluationDetail | null
  tradeCount: number | null
  totalTrades?: number | null
  spanDays: number | null
  /** Performance beside this is news-filtered; the firm verdict is not. Say so, don't imply it. */
  filtered: boolean
  collapsed: boolean
}) {
  const cfg = ev ? (VERDICT_CHIP[ev.verdict] ?? VERDICT_CHIP.DISCARD) : null
  // A profitable run that fails a firm rule is amber, not red — same rule the old card used.
  const top = cfg
    ? (ev!.verdict === 'DISCARD' && (ev!.net_pnl ?? 0) > 0 ? VERDICT_CHIP.WARN.top : cfg.top)
    : 'border-t-accent/45'
  const ungraded = ev?.verdict === 'INFO'

  const months = spanDays != null && spanDays > 0 ? spanDays / 30.44 : null
  const years = months != null ? months / 12 : null
  const perMonth = months != null && months >= 1 && tradeCount != null ? tradeCount / months : null
  const cadence = [
    years != null && years >= 1 ? `${years.toFixed(1)} yrs` : months != null ? `${months.toFixed(0)} mo` : null,
    perMonth != null ? `≈${perMonth < 1 ? perMonth.toFixed(1) : perMonth.toFixed(0)}/month` : null,
  ].filter(Boolean).join(' · ')

  const rows: PanelRow[] = []
  // Was a `verdict unfiltered` badge on the bar. As a row it states the number instead of
  // asking you to decode a label, and it sits where the reader is already reading numbers.
  if (filtered && totalTrades != null) {
    rows.push({ key: 'graded', label: 'Graded on', value: `all ${totalTrades}`,
      tip: 'Firm rules are evaluated on every trade, server-side — there is no news-filtered verdict. This card grades the full run even while the Performance numbers beside it have news and holiday trades removed.' })
  }
  if (ev && ungraded) {
    rows.push({ key: 'checks', label: 'Checks run', value: 'none',
      cls: 'text-text-tertiary', tip: UNGRADED_TIP })
  } else if (ev) {
    rows.push(...verdictRuleRows(ev))
  }

  return (
    <div className={panelCardCls(collapsed, filtered, `border-t-2 ${top}`)}>
      <CardHead
        title="Verdict"
        aside={cfg && (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-[3px] text-[10px] font-bold uppercase tracking-[0.4px] shrink-0 ${cfg.cls}`}>
            <cfg.Icon size={10} />{cfg.label}
          </span>
        )}
      />
      <CardHero
        value={tradeCount ?? '—'}
        unit={totalTrades != null && totalTrades !== tradeCount ? `of ${totalTrades} trades` : 'trades'}
        cls="text-accent"
        tip="How many trades this verdict and every number beside it rest on. Sample size is a portfolio property in this repo, not a strategy one — a selective strategy is DESIGNED to trade a couple of times a month, so read the cadence below rather than the count alone (CLAUDE.md → Trading Philosophy)."
      />
      {/* The ruleset name is identity, not measurement, so it sits here where it can truncate
          rather than in the right-hand column, which is nowrap and would push the card wide. */}
      <div className="text-[11px] text-text-tertiary leading-[1.35] mt-2 truncate"
        title={ev?.ruleset_name ?? undefined}>
        {ev ? ev.ruleset_name : 'No ruleset evaluated'}
      </div>
      {cadence && <div className="font-mono text-[10.5px] text-text-tertiary">{cadence}</div>}
      {!collapsed && rows.length > 0 && <PanelRows rows={rows} />}
    </div>
  )
}

// Optimizer parameter sets have no equity curve and no firm verdicts yet, so there is
// nothing to grade — the ribbon carries the prompt to run a real backtest instead.
function UnscoredRibbon({ tradeCount, onRunFullBacktest, busy }: {
  tradeCount?: number | null; onRunFullBacktest: () => void; busy?: boolean
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border-subtle border-l-[3px] border-l-border-default bg-bg-surface pl-4 pr-2.5 py-2.5">
      <span className="inline-flex items-center gap-1.5 rounded-full bg-bg-sunken px-3 py-[4px] text-[11px] font-bold uppercase tracking-[0.4px] text-text-tertiary shrink-0">
        <Info size={11} />Unscored
      </span>
      <span className="text-[12.5px] text-text-secondary">
        Optimizer parameter set — no equity curve, trade-level data or firm evaluation yet.
      </span>
      <button
        onClick={onRunFullBacktest}
        disabled={busy}
        className="inline-flex items-center gap-1.5 rounded border border-accent/30 bg-accent/5 px-3 py-1 text-[12px] font-semibold text-accent transition-colors hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
        Run Full Backtest
      </button>
      {tradeCount != null && <TradeCountAnchor count={tradeCount} spanDays={null} />}
    </div>
  )
}

// ── Running banner ────────────────────────────────────────────────────────────

const NT8_RUN_STEPS = [
  { label: 'Connect',   startPct: 0  },
  { label: 'Configure', startPct: 20 },
  { label: 'Run',       startPct: 30 },
  { label: 'Results',   startPct: 70 },
  { label: 'Evaluate',  startPct: 95 },
  { label: 'Tagging',   startPct: 97 },
]

const PYTHON_RUN_STEPS = [
  { label: 'Load bars', startPct: 0  },
  { label: 'Replay',    startPct: 15 },
  { label: 'Results',   startPct: 95 },
]

const MT5_RUN_STEPS = [
  { label: 'Launch',  startPct: 0  },
  { label: 'Testing', startPct: 10 },
  { label: 'Results', startPct: 90 },
  { label: 'Tagging', startPct: 95 },
]

function useElapsed(startedAt: string | null): string {
  const [secs, setSecs] = useState(0)
  useEffect(() => {
    const origin = startedAt ? parseFloat(startedAt) * 1000 : Date.now()
    setSecs(Math.floor((Date.now() - origin) / 1000))
    const id = setInterval(() => setSecs(Math.floor((Date.now() - origin) / 1000)), 1000)
    return () => clearInterval(id)
  }, [startedAt])
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

// ── Milestone log parser ──────────────────────────────────────────────────────

interface Milestone { time: string; text: string; accent: boolean }

const NT8_MILESTONE_PATTERNS: Array<{
  re: RegExp
  format: (m: RegExpMatchArray, line: string) => { text: string; accent: boolean }
}> = [
  {
    re: /Connected \(via process name\)/,
    format: () => ({ text: 'NT8 connected', accent: true }),
  },
  {
    re: /Strategy Analyzer found/,
    format: () => ({ text: 'Strategy Analyzer open', accent: true }),
  },
  {
    re: /Run clicked/,
    format: () => ({ text: 'Backtest executing', accent: false }),
  },
  {
    re: /could not select strategy '(.+)'/,
    format: (m) => ({ text: `Strategy not found: ${m[1]}`, accent: false }),
  },
  {
    re: /\[trades\] Parsed (\d+) trades, (\d+) trading days/,
    format: (m) => ({ text: `Parsed ${m[1]} trades · ${m[2]} days`, accent: false }),
  },
  {
    re: /Trades=(\d+)\s+NetPnL=([\d.-]+)\s+PF=([\d.]+)\s+MaxDD=([\d.]+)/,
    format: (m) => {
      const pnl = parseFloat(m[2])
      const sign = pnl >= 0 ? '+' : ''
      return {
        text: `${m[1]} trades · P&L ${sign}$${Math.abs(pnl).toLocaleString('en-US', { maximumFractionDigits: 0 })} · PF ${parseFloat(m[3]).toFixed(2)} · DD $${parseFloat(m[4]).toFixed(0)}`,
        accent: pnl >= 0,
      }
    },
  },
]

const MT5_MILESTONE_PATTERNS: Array<{
  re: RegExp
  format: (m: RegExpMatchArray, line: string) => { text: string; accent: boolean }
}> = [
  {
    re: /Launched terminal64\.exe|Launching MT5/i,
    format: () => ({ text: 'MT5 terminal launched', accent: true }),
  },
  {
    re: /Strategy Tester running|backtest started/i,
    format: () => ({ text: 'Strategy Tester running', accent: false }),
  },
  {
    re: /Parsing.*report|report.*parsed/i,
    format: () => ({ text: 'Parsing report', accent: false }),
  },
]

function parseMilestones(logText: string, runner: string): Milestone[] {
  const patterns = runner === 'mt5' ? MT5_MILESTONE_PATTERNS : NT8_MILESTONE_PATTERNS
  const results: Milestone[] = []
  for (const raw of logText.split('\n')) {
    const lineMatch = raw.match(/^\[(\d{2}:\d{2}:\d{2})\]\s+(.+)$/)
    if (!lineMatch) continue
    const [, time, content] = lineMatch
    for (const { re, format } of patterns) {
      const m = content.match(re)
      if (m) {
        results.push({ time, ...format(m, content) })
        break
      }
    }
  }
  return results
}

// ── Running banner ────────────────────────────────────────────────────────────

function RunningBanner({ pct, message, startedAt, onStop, runId, runner, steps = NT8_RUN_STEPS }: {
  pct: number
  message: string
  startedAt: string | null
  onStop: () => void
  runId: string
  runner: string
  steps?: typeof NT8_RUN_STEPS
}) {
  const elapsed   = useElapsed(startedAt)
  const activeIdx = steps.reduce((best, step, i) => pct >= step.startPct ? i : best, 0)
  const { data: logText = '' } = useRunLog(runId, 500, true)
  const milestones = useMemo(() => parseMilestones(logText, runner), [logText, runner])

  return (
    <div className="bg-accent-muted border border-accent/30 rounded-lg px-4 pt-4 pb-4 space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-accent uppercase tracking-[0.6px]">Running</span>
        <span className="text-[11px] font-mono text-accent tabular-nums">{Math.round(pct)}%</span>
      </div>

      {/* Stage pipeline — connectors are the progress bar */}
      <div className="flex items-start">
        {steps.map((step, i) => {
          const done   = i < activeIdx
          const active = i === activeIdx
          const isLast = i === steps.length - 1
          const segFill = isLast ? 0 : Math.min(1, Math.max(0,
            (pct - step.startPct) / (steps[i + 1].startPct - step.startPct)
          ))
          return (
            <Fragment key={step.label}>
              <div className="flex flex-col items-center gap-[6px]">
                <span
                  className={[
                    'w-[9px] h-[9px] rounded-full flex-shrink-0 transition-all duration-300',
                    done || active ? 'bg-accent' : 'border border-border-default bg-transparent',
                  ].join(' ')}
                  style={active ? { boxShadow: '0 0 0 4px rgba(0,229,255,0.15), 0 0 12px rgba(0,229,255,0.45)' } : undefined}
                />
                <span className={[
                  'text-[9px] whitespace-nowrap uppercase tracking-wide leading-none',
                  done   ? 'text-accent/60' :
                  active ? 'text-accent font-semibold' :
                           'text-text-tertiary/50',
                ].join(' ')}>
                  {step.label}
                </span>
              </div>
              {!isLast && (
                <div className="flex-1 h-[3px] mt-[3.75px] bg-bg-sunken rounded-full overflow-hidden relative">
                  <div
                    className="absolute inset-y-0 left-0 bg-accent rounded-full transition-all duration-700 ease-out"
                    style={{ width: `${segFill * 100}%` }}
                  />
                </div>
              )}
            </Fragment>
          )
        })}
      </div>

      {/* Milestone log */}
      {milestones.length > 0 && (
        <div className="space-y-[5px]">
          {milestones.map((m, i) => (
            <div key={i} className="flex items-baseline gap-3 font-mono text-[11px] leading-snug">
              <span className="text-text-tertiary flex-shrink-0">{m.time}</span>
              <span className={m.accent ? 'text-accent' : 'text-text-secondary'}>{m.text}</span>
            </div>
          ))}
        </div>
      )}

      {/* Message + elapsed + stop */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="w-[5px] h-[5px] rounded-full bg-accent animate-pulse flex-shrink-0" />
          <span className="text-[12px] text-text-secondary">{message || 'Starting\u2026'}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[11px] text-text-tertiary font-mono tabular-nums">{elapsed}</span>
          <button
            onClick={onStop}
            className="flex items-center gap-[5px] px-[10px] py-[5px] rounded-md text-[12px] font-medium bg-neg-muted border border-neg-text/30 text-neg-text hover:bg-neg-text/20 transition-colors"
          >
            <Square size={10} fill="currentColor" />
            Stop
          </button>
        </div>
      </div>

    </div>
  )
}

// ── Failure banner ────────────────────────────────────────────────────────────

function getFailureGuidance(status: string, runner: string): string {
  if (status === 'failed_strategy_not_found') {
    return 'NT8 could not find the strategy in the Strategy Analyzer dropdown. Open NinjaScript Editor and press F5 to recompile, then retry.'
  }
  const scope = runnerScope(runner)
  if (status === 'failed_timeout') {
    if (scope === 'python') return 'The local run stopped making progress. Check the run logs below, then re-run.'
    return scope === 'mt5'
      ? 'The MT5 agent stopped responding mid-run. Check the MT5 agent log on the VPS, then re-run.'
      : 'The NT8 agent stopped responding mid-run. Verify NT8 is running and the Strategy Analyzer is open in the RDP session, then re-run.'
  }
  if (scope === 'python') return 'An unexpected error occurred. Check the run logs below for details.'
  return scope === 'mt5'
    ? 'An unexpected error occurred. Check the run logs below and the MT5 agent log for details.'
    : 'An unexpected error occurred. Check the run logs below and the NT8 agent log for details.'
}

function FailureBanner({ run, onRetry, retrying }: { run: Run; onRetry?: () => void; retrying?: boolean }) {
  const guidance = getFailureGuidance(run.status, run.runner ?? 'ninjatrader')
  return (
    <div className="bg-neg-muted border border-neg-text/30 rounded-lg px-4 py-4">
      <div className="flex items-start gap-3">
        <AlertTriangle size={15} className="text-neg-text flex-shrink-0 mt-[1px]" />
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-semibold text-neg-text mb-1">Run failed — {run.status}</div>
          {run.error_message && (
            <div className="text-[12px] font-mono text-neg-text/80 mb-3 whitespace-pre-wrap break-all">
              {run.error_message}
            </div>
          )}
          <div className="text-[12px] text-text-secondary">{guidance}</div>
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            disabled={retrying}
            className="flex-shrink-0 flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium bg-bg-surface border border-border-default text-text-secondary hover:text-text-primary hover:border-border-default/80 disabled:opacity-50 transition-colors"
          >
            <RotateCcw size={12} className={retrying ? 'animate-spin' : ''} />
            {retrying ? 'Starting…' : 'Retry'}
          </button>
        )}
      </div>
    </div>
  )
}

// ── Logs section ──────────────────────────────────────────────────────────────

function LogsSection({ runId, autoExpand, isRunning, isComplete, isFailed }: {
  runId: string
  autoExpand: boolean
  isRunning: boolean
  isComplete?: boolean
  isFailed?: boolean
}) {
  const [open, setOpen] = useState(autoExpand)
  const [copied, setCopied] = useState(false)
  const { data: log, isFetching } = useRunLog(open ? runId : null, 200, isRunning)

  function copyLog(e: React.MouseEvent) {
    e.stopPropagation()
    if (!log) return
    navigator.clipboard.writeText(log)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="bg-bg-sunken border border-border-subtle rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-[10px] border-b border-border-subtle hover:bg-bg-hover/40 transition-colors"
      >
        <div className="flex items-center gap-[10px]">
          {isRunning ? (
            <span className="relative flex h-[8px] w-[8px] flex-shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60" />
              <span className="relative inline-flex rounded-full h-[8px] w-[8px] bg-accent" />
            </span>
          ) : isComplete ? (
            <span className="w-[8px] h-[8px] rounded-full bg-accent flex-shrink-0" />
          ) : isFailed ? (
            <span className="w-[8px] h-[8px] rounded-full bg-neg-text flex-shrink-0" />
          ) : (
            <span className="w-[8px] h-[8px] rounded-full bg-text-tertiary/30 flex-shrink-0" />
          )}
          <span className="text-small font-semibold font-mono tracking-wide uppercase text-text-secondary">
            Run Logs
          </span>
          {isRunning && (
            <span className="text-micro text-text-tertiary font-mono">· live</span>
          )}
          {isComplete && !isRunning && (
            <span className="text-micro text-accent font-mono">· complete</span>
          )}
          {isFailed && !isRunning && (
            <span className="text-micro text-neg-text font-mono">· failed</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {log && (
            <span
              role="button"
              onClick={copyLog}
              title="Copy log"
              className="p-1 rounded hover:bg-bg-hover text-text-tertiary hover:text-text-secondary transition-colors"
            >
              {copied ? <Check size={13} className="text-accent" /> : <Copy size={13} />}
            </span>
          )}
          {open ? <ChevronUp size={14} className="text-text-tertiary" /> : <ChevronDown size={14} className="text-text-tertiary" />}
        </div>
      </button>
      {open && (
        <div>
          {isFetching && !log ? (
            <div className="px-4 py-3 text-[12px] text-text-tertiary font-mono">Loading…</div>
          ) : log ? (
            <pre className="px-4 py-3 text-[11px] font-mono text-text-secondary leading-[1.6] overflow-x-auto whitespace-pre-wrap max-h-[400px] overflow-y-auto">
              {log}
            </pre>
          ) : (
            <div className="px-4 py-3 text-[12px] text-text-tertiary font-mono">No log output.</div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Section label ─────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">
      {children}
    </h2>
  )
}

function ChartLoadingSkeleton({ height }: { height: number }) {
  const bars = [42, 61, 38, 74, 55, 88, 49, 72, 64, 91, 46, 68, 81, 53, 77, 59, 84, 44, 70, 57, 86, 51]
  const barsH = Math.round(height * 0.68)
  return (
    <div style={{ height }} className="relative overflow-hidden">
      {[25, 50, 75].map(p => (
        <div key={p} className="absolute left-0 right-0 h-px bg-border-subtle/25" style={{ top: `${p}%` }} />
      ))}
      <div className="absolute bottom-8 left-2 right-2 flex items-end gap-[3px]" style={{ height: barsH }}>
        {bars.map((h, i) => (
          <div
            key={i}
            className="flex-1 min-w-0 rounded-sm bg-white/[0.07] animate-pulse"
            style={{ height: `${h}%`, animationDelay: `${(i * 75) % 700}ms` }}
          />
        ))}
      </div>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-[12px] text-text-tertiary">Loading chart…</span>
      </div>
    </div>
  )
}

// Candlestick panel body (klinecharts). Lazy: the chart library and the run's ChartSpec (a heavy
// candle fetch) load only when `active` — i.e. when the Price tab in the primary chart is selected.
function PriceChartPanel({ runId, height = 520, isFullscreen = false, onFullscreenClose }: {
  runId: string
  height?: number
  isFullscreen?: boolean
  onFullscreenClose?: () => void
}) {
  const { data: spec, isLoading, isError } = useChartSpec(runId)
  const requestCandles = useRunCandles(runId)
  return (
    <PriceChartView
      spec={spec} isLoading={isLoading} isError={isError} requestCandles={requestCandles}
      height={height} isFullscreen={isFullscreen} onFullscreenClose={onFullscreenClose}
    />
  )
}

// The runId-agnostic price-chart body: same klinecharts panel, structure layers, fib/measurement
// tools, and fullscreen chrome, driven by an already-fetched ChartSpec. BacktestDetail feeds it a
// single run's spec; StackDetail feeds it the merged stack spec (trades layered by strategy) — both
// get identical functionality. `requestCandles` wires M1/M5 drill-down; pass undefined to disable.
export function PriceChartView({ spec, isLoading, isError, requestCandles, height = 520, isFullscreen = false, onFullscreenClose }: {
  spec: ChartSpec | undefined
  isLoading: boolean
  isError: boolean
  requestCandles?: ReturnType<typeof useRunCandles>
  height?: number
  isFullscreen?: boolean
  onFullscreenClose?: () => void
}) {
  const fsBodyRef = useRef<HTMLDivElement>(null)
  const [fsBodyH, setFsBodyH] = useState(0)

  // Measure the fullscreen body height once the overlay is open.
  useEffect(() => {
    if (!isFullscreen) return
    const el = fsBodyRef.current
    if (!el) return
    const update = () => setFsBodyH(el.clientHeight)
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [isFullscreen])

  // Escape key to close fullscreen.
  useEffect(() => {
    if (!isFullscreen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onFullscreenClose?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isFullscreen, onFullscreenClose])

  // When fullscreen: body clientHeight minus its padding (pt-2/pb-2 ~16px), the ChartPanel header
  // row (now the single top bar — TF/Layers/Copy + the injected Price title & exit X, ~40px with its
  // border-b), and a small safety buffer. Without subtracting the header the chart overflows and
  // overflow-hidden clips the klinecharts x-axis.
  const effectiveH = isFullscreen
    ? (fsBodyH > 0 ? Math.max(200, fsBodyH - 64) : Math.max(200, window.innerHeight - 120))
    : height

  const box = (msg: string, cls = 'text-text-tertiary') => (
    <div style={{ height: effectiveH }} className={`flex items-center justify-center text-[12px] ${cls}`}>{msg}</div>
  )

  // chartBody is always at the same tree position inside the body div so the klinecharts
  // instance (ChartPanel) is never unmounted when toggling between inline and fullscreen.
  const chartBody = isLoading ? <ChartLoadingSkeleton height={effectiveH} />
    : isError ? box("Couldn't load chart data for this run.", 'text-neg-text')
    : !spec || spec.candles.length === 0 ? box('No price data available for this run.')
    : (
      <>
        {spec.baseTimeframe === 'D1' && !isFullscreen && (
          <div className="mb-2 text-[11px] text-warn-text">
            Showing daily candles — intraday history wasn't available from the data agent for this run.
          </div>
        )}
        <Suspense fallback={<ChartLoadingSkeleton height={effectiveH} />}>
          {/* Drill-down (1m/5m) only for intraday runs — a D1 (NT8 daily) run has no sub-base bars.
              Fullscreen: fold the "Price" title + exit X onto the panel's own top row (header
              slots), so TF/Layers/Copy and the exit all share one bar instead of stacking two. */}
          <ChartPanel
            spec={spec}
            height={effectiveH}
            onRequestCandles={spec.baseTimeframe !== 'D1' ? requestCandles : undefined}
            // Snapshot button on the expanded chart only — same rule as every other chart here.
            showCopy={isFullscreen}
            headerClassName={isFullscreen ? 'border-b border-border-subtle pb-2' : undefined}
            headerLeading={isFullscreen
              ? <span className="text-[15px] font-bold uppercase tracking-wide text-text-primary ml-1 mr-2">{spec.instrument}</span>
              : undefined}
            headerTrailing={isFullscreen
              ? (
                <button onClick={onFullscreenClose} title="Minimize (Esc)" className="text-text-tertiary hover:text-text-primary">
                  <Minimize2 size={18} />
                </button>
              )
              : undefined}
          />
        </Suspense>
      </>
    )

  return (
    <div className={isFullscreen ? 'fixed inset-0 z-[90] bg-bg-base flex flex-col' : ''}>
      {/* Minimal left/right padding in fullscreen to maximise chart space (the price gets its own
          small inset via headerLeading's ml-1; the tool strip sits just inside the edge). */}
      <div ref={fsBodyRef} className={isFullscreen ? 'flex-1 min-h-0 overflow-hidden pl-2 pr-2 pt-2 pb-2' : ''}>
        {chartBody}
      </div>
    </div>
  )
}

// ── Tabbed chart panel + fullscreen modal ────────────────────────────────────
// ChartTabPanel + ChartModal now live in components/ChartTabPanel.tsx (shared with
// StressTestDetail). Imported at the top of this file.

// ── Loading skeleton ──────────────────────────────────────────────────────────

function Skeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="h-6 w-64 bg-bg-surface rounded" />
      <div className="grid grid-cols-4 gap-3">
        {[0,1,2,3].map(i => <div key={i} className="h-20 bg-bg-surface rounded-lg" />)}
      </div>
      <div className="h-[320px] bg-bg-surface rounded-lg" />
      <div className="h-[260px] bg-bg-surface rounded-lg" />
    </div>
  )
}

// ── Status badge ──────────────────────────────────────────────────────────────


// ── Chart verdict banner ──────────────────────────────────────────────────────

// ── Performance by Regime ────────────────────────────────────────────────────

function PerformanceByRegimeTable({ run }: { run: Run }) {
  // Built server-side by metrics.compute_regime_breakdown — the single source of truth.
  const rows = run.regime_breakdown
  if (!rows.length) return null
  const worstOverall = run.daily_pnl.length ? Math.min(...run.daily_pnl.map(d => d.pnl)) : null

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-border-subtle">
        <div className="text-[10px] font-semibold text-text-secondary uppercase tracking-[0.6px]">Performance by Regime</div>
        <div className="text-[10px] text-text-tertiary mt-[2px]">How the strategy performs in each market condition.</div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-border-subtle">
              {['Regime','Days','Trades','Net P&L','Win Rate','Prof. Factor','Worst Day'].map(h => (
                <th key={h} className={`text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.5px] px-5 py-3 ${h === 'Regime' ? 'text-left' : 'text-right'}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const color = REGIME_COLORS[row.regime] ?? REGIME_COLORS.UNKNOWN
              return (
                <tr key={i} className={i < rows.length - 1 ? 'border-b border-border-subtle/60' : ''}>
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2">
                      <div style={{ width: 11, height: 11, background: color, borderRadius: 3, flexShrink: 0 }} />
                      <span className="text-text-secondary">{REGIME_LABEL[row.regime] ?? row.regime}</span>
                    </div>
                  </td>
                  <td className="text-right px-5 py-3.5 text-text-secondary tabular-nums">{row.days}</td>
                  <td className="text-right px-5 py-3.5 text-text-secondary tabular-nums">{row.trades}</td>
                  <td className={`text-right px-5 py-3.5 tabular-nums font-medium ${row.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>{dollar(row.net_pnl, true)}</td>
                  <td className={`text-right px-5 py-3.5 tabular-nums ${winRateCls(row.win_rate)}`}>{row.win_rate != null ? `${(row.win_rate * 100).toFixed(1)}%` : '—'}</td>
                  <td className={`text-right px-5 py-3.5 tabular-nums ${pfCls(row.profit_factor)}`}>{row.profit_factor != null ? row.profit_factor.toFixed(2) : '—'}</td>
                  <td className={`text-right px-5 py-3.5 tabular-nums ${row.worst_day != null && row.worst_day < 0 ? 'text-neg-text' : 'text-text-secondary'}`}>{row.worst_day != null ? dollar(row.worst_day) : '—'}</td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr className="border-t border-border-subtle bg-bg-elevated/30">
              <td className="px-5 py-3.5 text-[11px] font-semibold text-text-secondary">Overall</td>
              <td className="text-right px-5 py-3.5 text-[11px] font-medium text-text-secondary tabular-nums">{run.daily_pnl.length}</td>
              <td className="text-right px-5 py-3.5 text-[11px] font-medium text-text-secondary tabular-nums">{run.trade_count ?? run.equity_curve.length}</td>
              <td className={`text-right px-5 py-3.5 text-[11px] font-semibold tabular-nums ${(run.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>{dollar(run.net_pnl, true)}</td>
              <td className={`text-right px-5 py-3.5 text-[11px] font-medium tabular-nums ${winRateCls(run.win_rate)}`}>{run.win_rate != null ? `${(run.win_rate * 100).toFixed(1)}%` : '—'}</td>
              <td className={`text-right px-5 py-3.5 text-[11px] font-medium tabular-nums ${pfCls(run.profit_factor)}`}>{run.profit_factor != null ? run.profit_factor.toFixed(2) : '—'}</td>
              <td className={`text-right px-5 py-3.5 text-[11px] font-medium tabular-nums ${worstOverall != null && worstOverall < 0 ? 'text-neg-text' : 'text-text-secondary'}`}>{worstOverall != null ? dollar(worstOverall) : '—'}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

// ── Sized timeline table ──────────────────────────────────────────────────────
// The dynamic-sizing engine's day-by-day audit, day for day: how many contracts it
// sized, the day's sized P&L, the end-of-day balance, the trailing risk floor and the
// buffer to it, and any halt/breach. Reads run.sized_timeline (engine_timeline.json);
// shown only for engine-sized runs. Collapsible — a sized run can be hundreds of days.

function SizedTimelineTable({ run }: { run: Run }) {
  const rows = run.sized_timeline
  const [open, setOpen] = useState(false)
  if (!rows.length) return null

  const haltDays   = rows.filter(d => d.halt_reason).length
  const tradedDays = rows.filter(d => d.trades_taken > 0).length
  const finalBal   = rows[rows.length - 1].eod_balance

  const headCells = ['Date', 'Trades', 'Contracts', 'Day P&L', 'EOD Balance', 'Risk Floor', 'Buffer', 'Status']

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full px-4 py-3 border-b border-border-subtle flex items-center justify-between text-left hover:bg-bg-elevated/30 transition-colors"
      >
        <div>
          <div className="text-[10px] font-semibold text-text-secondary uppercase tracking-[0.6px]">Sizing Timeline</div>
          <div className="text-[10px] text-text-tertiary mt-[2px]">
            {rows.length} day{rows.length === 1 ? '' : 's'} · {tradedDays} traded
            {haltDays > 0 && <span className="text-gold-text"> · {haltDays} halted</span>}
            {' '}· what the engine sized, day by day.
          </div>
        </div>
        {open ? <ChevronUp size={15} className="text-text-tertiary" /> : <ChevronDown size={15} className="text-text-tertiary" />}
      </button>
      {open && (
        <div className="overflow-auto max-h-[480px]">
          <table className="w-full text-[13px]">
            <thead className="sticky top-0 bg-bg-surface z-10">
              <tr className="border-b border-border-subtle">
                {headCells.map(h => (
                  <th key={h} className={`text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.5px] px-5 py-3 ${h === 'Date' ? 'text-left' : h === 'Status' ? 'text-center' : 'text-right'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((d, i) => {
                const breached = d.risk_floor != null && d.eod_balance < d.risk_floor
                const rowTint  = breached ? 'bg-neg-muted/30' : d.halt_reason ? 'bg-gold-muted/20' : ''
                return (
                  <tr key={i} className={`${i < rows.length - 1 ? 'border-b border-border-subtle/60' : ''} ${rowTint}`}>
                    <td className="px-5 py-3 text-left text-text-secondary tabular-nums whitespace-nowrap">{fmtChartDate(d.date)}</td>
                    <td className="px-5 py-3 text-right text-text-secondary tabular-nums">{d.trades_taken}</td>
                    <td className="px-5 py-3 text-right text-text-secondary tabular-nums">{d.contracts_total}</td>
                    <td className={`px-5 py-3 text-right tabular-nums font-medium ${d.day_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>{dollar(d.day_pnl, true)}</td>
                    <td className="px-5 py-3 text-right text-text-secondary tabular-nums">{dollar(d.eod_balance)}</td>
                    <td className="px-5 py-3 text-right text-text-tertiary tabular-nums">{d.risk_floor != null ? dollar(d.risk_floor) : '—'}</td>
                    <td className={`px-5 py-3 text-right tabular-nums ${d.floor_distance != null && d.floor_distance <= 0 ? 'text-neg-text' : 'text-text-secondary'}`}>{d.floor_distance != null ? dollar(d.floor_distance) : '—'}</td>
                    <td className="px-5 py-3 text-center">
                      {breached ? (
                        <span className="text-[10px] font-semibold uppercase tracking-[0.5px] px-2 py-0.5 rounded bg-neg-muted text-neg-text border border-neg/40">Breach</span>
                      ) : d.halt_reason ? (
                        <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-gold-muted text-gold-text border border-gold-text/20" title={d.halt_reason}>{d.halt_reason}</span>
                      ) : (
                        <span className="text-text-tertiary">—</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot>
              <tr className="border-t border-border-subtle bg-bg-elevated/30">
                <td className="px-5 py-3 text-[11px] font-semibold text-text-secondary">Final</td>
                <td className="text-right px-5 py-3 text-[11px] font-medium text-text-secondary tabular-nums">{run.trade_count ?? '—'}</td>
                <td className="px-5 py-3" />
                <td className={`text-right px-5 py-3 text-[11px] font-semibold tabular-nums ${(run.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>{dollar(run.net_pnl, true)}</td>
                <td className="text-right px-5 py-3 text-[11px] font-semibold text-text-secondary tabular-nums">{dollar(finalBal)}</td>
                <td className="px-5 py-3" />
                <td className="px-5 py-3" />
                <td className="px-5 py-3" />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  )
}

// ── Run Stress Test Modal ─────────────────────────────────────────────────────

function RunStressTestModal({ run, onClose, navigate }: { run: Run; onClose: () => void; navigate: (path: string) => void }) {
  const runTest = useRunStressTest()

  const primaryEval = run.evaluations?.[0]
  const rulesetId   = primaryEval?.ruleset_id ?? undefined

  const isNativeWF = !!run.optimization_id && run.runner !== 'mt5'
  const estMin     = isNativeWF ? 45 : 80

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-bg-surface border border-border-default rounded-xl p-6 w-full max-w-md space-y-4" onClick={e => e.stopPropagation()}>
        <h2 className="text-base font-semibold text-text-primary">Run Stress Test</h2>

        {primaryEval ? (
          <div className="space-y-1">
            <p className="text-xs text-text-secondary">Evaluating against</p>
            <span className="inline-block text-xs font-mono font-semibold px-2 py-0.5 rounded bg-warn-muted border border-warn-text/20 text-warn-text">
              {primaryEval.ruleset_name}
            </span>
          </div>
        ) : (
          <p className="text-xs text-text-tertiary">No ruleset — Monte Carlo only.</p>
        )}

        <p className="text-xs text-text-secondary">
          Runs Monte Carlo, walk-forward, and sensitivity analysis.
          Estimated ~{estMin} min. Platform must be idle.
        </p>

        <div className="flex gap-2 pt-2">
          <button
            onClick={() => {
              runTest.mutate({
                run_id: run.run_id,
                ruleset_id: rulesetId,
                include_walk_forward: true,
                include_sensitivity: true,
                num_simulations: 10_000,
                num_bootstrap: 1_000,
                walk_forward_windows: 5,
              }, { onSuccess: (data) => { onClose(); navigate(`/stress-tests/${data.stress_test_id}`) } })
            }}
            disabled={runTest.isPending}
            className="flex-1 py-1.5 text-sm bg-accent text-bg-base rounded font-medium hover:opacity-90 disabled:opacity-50"
          >
            {runTest.isPending ? 'Starting…' : 'Run Stress Test'}
          </button>
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-text-secondary border border-border-subtle rounded hover:bg-bg-hover">Cancel</button>
        </div>
      </div>
    </div>
  )
}

// Shown when running a full backtest on an optimizer combo that has no ruleset to score against
// (the backend couldn't inherit one). The user picks the market-appropriate ruleset(s); the run is
// then re-fired and scored. Mirrors the Run Backtest modal's "evaluate against" choice.
function FullBacktestEvalModal({ run, busy, onConfirm, onClose }: {
  run: Run
  busy: boolean
  onConfirm: (rulesetIds: string[]) => void
  onClose: () => void
}) {
  const { data: rulesets = [] } = useRulesets()
  // Forex (MT5/Python) runs evaluate against forex rulesets; futures (NT8) against the prop rows.
  const isFutures = runnerMarket(run.runner) === 'futures'
  const options = useMemo(
    () => rulesets.filter(r => (isFutures ? r.market !== 'forex' : r.market === 'forex')),
    [rulesets, isFutures],
  )
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const toggle = (id: string) => setSelected(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-bg-surface border border-border-default rounded-xl p-6 w-full max-w-md space-y-4" onClick={e => e.stopPropagation()}>
        <div>
          <h2 className="text-base font-semibold text-text-primary">Run Full Backtest</h2>
          <p className="text-xs text-text-secondary mt-1">
            This optimizer parameter set has no ruleset attached. Pick which {isFutures ? 'futures' : 'forex'} ruleset(s)
            to score it against.
          </p>
        </div>

        {options.length === 0 ? (
          <p className="text-xs text-text-tertiary">No {isFutures ? 'futures' : 'forex'} rulesets available.</p>
        ) : (
          <div className="space-y-1.5 max-h-[40vh] overflow-y-auto">
            {options.map(r => (
              <label
                key={r.id}
                className="flex items-center gap-2.5 px-3 py-2 rounded border border-border-subtle hover:bg-bg-hover cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selected.has(r.id)}
                  onChange={() => toggle(r.id)}
                  className="w-3.5 h-3.5 rounded accent-accent cursor-pointer"
                />
                <span className="text-[13px] text-text-primary">{r.name}</span>
              </label>
            ))}
          </div>
        )}

        <div className="flex gap-2 pt-2">
          <button
            onClick={() => onConfirm(Array.from(selected))}
            disabled={busy || selected.size === 0}
            className="flex-1 py-1.5 text-sm bg-accent text-bg-base rounded font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {busy ? 'Starting…' : 'Run Full Backtest'}
          </button>
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-text-secondary border border-border-subtle rounded hover:bg-bg-hover">Cancel</button>
        </div>
      </div>
    </div>
  )
}

// Rerun a standalone run, with the option to move the backtest window first (the common reason to
// rerun is "same setup, more history"). Pre-filled with the run's current period, so straight
// Enter/click reruns exactly what it says on the header chip. The run is reset and refilled IN
// PLACE — same run_id, its old result is replaced — which is what Rerun has always done; the new
// period is persisted with it so the record never describes a window it wasn't run over.
// Sweep children and optimizer combos share one period across the whole set, so they never get
// here (the backend rejects a period override on them too).
function RerunModal({ run, busy, onConfirm, onClose }: {
  run: Run
  busy: boolean
  onConfirm: (start: string, end: string) => void
  onClose: () => void
}) {
  const [start, setStart] = useState(run.start_date)
  const [end, setEnd]     = useState(run.end_date)
  // Same measured floor the new-run modal uses — a rerun picks a new window, so it needs
  // the identical guard rather than inheriting the original run's (possibly wider) period.
  const { data: historyLimit } = useHistoryLimit(
    run.instrument || null, run.bar_type || 'Minute', run.bar_value ?? 15, run.runner)
  const floor = historyLimit?.earliest_date ?? null
  const valid = !!start && !!end && start < end && !(floor && start < floor)
  const moved = start !== run.start_date || end !== run.end_date

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-bg-surface border border-border-default rounded-xl p-6 w-full max-w-md space-y-4" onClick={e => e.stopPropagation()}>
        <div>
          <h2 className="text-base font-semibold text-text-primary">Rerun Backtest</h2>
          <p className="text-xs text-text-secondary mt-1">
            {run.strategy_name} · {run.instrument} — same parameters, same rulesets. Adjust the period to
            test over more (or less) history.
          </p>
        </div>

        <div>
          <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">Period</div>
          <PeriodPicker start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e) }} limit={historyLimit} />
        </div>

        {moved && (
          <p className="text-[11px] text-warn-text">
            This replaces the existing result for {fmtDate(run.start_date)} → {fmtDate(run.end_date)}.
          </p>
        )}

        <div className="flex gap-2 pt-2">
          <button
            onClick={() => onConfirm(start, end)}
            disabled={busy || !valid}
            className="flex-1 py-1.5 text-sm bg-accent text-bg-base rounded font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {busy ? 'Starting…' : 'Rerun'}
          </button>
          <button onClick={onClose} className="px-4 py-1.5 text-sm text-text-secondary border border-border-subtle rounded hover:bg-bg-hover">Cancel</button>
        </div>
      </div>
    </div>
  )
}

// ── Parameters side panel ─────────────────────────────────────────────────────

function ParamsSidePanel({ run, paramSchema, baselineParams, collapsed, onToggle, balance, defaultBalance, onBalanceChange, headerH = 0 }: {
  run: Run
  paramSchema?: ParamSchemaEntry[]
  baselineParams?: Record<string, unknown>
  collapsed: boolean
  onToggle: () => void
  balance?: number | null
  defaultBalance?: number | null
  onBalanceChange?: (v: number | null) => void
  headerH?: number
}) {
  const schemaByName = new Map((paramSchema ?? []).map(s => [s.name, s]))
  const isFoundational = (k: string) => schemaByName.get(k)?.category === 'foundational'
  const entries = Object.entries(run.params || {})
  if (!entries.length) return null
  const tunable      = entries.filter(([k]) => !isFoundational(k))
  const foundational = entries.filter(([k]) => isFoundational(k))
  const changedCount = baselineParams
    ? tunable.filter(([k, v]) => String(v) !== String(baselineParams[k])).length
    : 0

  // The outer column is the full page-height surface (flush against the nav sidebar,
  // divided from the content by border-r). The inner block is sticky so the params
  // stay visible at the top while the page scrolls.
  if (collapsed) {
    return (
      <div className="flex-shrink-0 bg-bg-surface border-r border-border-subtle">
        <button
          onClick={onToggle}
          title="Show parameters"
          style={{ top: Math.max(headerH - 22, 0) }}
          className="sticky flex flex-col items-center gap-2 py-4 px-2 w-full hover:bg-bg-hover transition-colors"
        >
          <ChevronRight size={14} className="text-text-tertiary" />
          <span className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-tertiary [writing-mode:vertical-rl]">Parameters</span>
          {changedCount > 0 && <span className="w-[6px] h-[6px] rounded-full bg-accent" title={`${changedCount} changed vs baseline`} />}
        </button>
      </div>
    )
  }

  return (
    <div className="flex-shrink-0 w-[248px] bg-bg-surface border-r border-border-subtle">
      <div className="sticky flex flex-col" style={{ top: Math.max(headerH - 22, 0), maxHeight: `calc(100vh - 56px - ${headerH}px)` }}>
        <div className="px-3 py-[10px] border-b border-border-subtle flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">Parameters</span>
            {baselineParams && changedCount > 0 && (
              <span className="text-[10px] text-accent whitespace-nowrap">{changedCount} changed</span>
            )}
          </div>
          <button onClick={onToggle} title="Collapse" className="text-text-tertiary hover:text-text-secondary flex-shrink-0">
            <ChevronLeft size={14} />
          </button>
        </div>
        <div className="overflow-y-auto px-2.5 py-2 space-y-[4px]">
          {tunable.map(([k, v]) => {
            const changed = baselineParams != null && String(v) !== String(baselineParams[k])
            return (
              <div
                key={k}
                className={`flex items-center justify-between gap-2 px-2 py-[5px] rounded ${changed ? 'bg-accent/5 border border-accent/30' : ''}`}
                title={schemaByName.get(k)?.description}
              >
                <span className="text-[11px] font-mono text-text-tertiary truncate">{k}</span>
                <span className="text-[12px] font-mono font-semibold text-text-primary flex-shrink-0 text-right">
                  {changed && <span className="text-[10px] text-text-tertiary line-through mr-1">{String(baselineParams![k])}</span>}
                  {String(v)}
                </span>
              </div>
            )
          })}
          {foundational.length > 0 && (
            <details className="pt-2 mt-1 border-t border-border-subtle/40">
              <summary className="text-[10px] text-text-tertiary cursor-pointer select-none px-2">Foundational · {foundational.length}</summary>
              <div className="mt-1.5 space-y-[3px]">
                {foundational.map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between gap-2 px-2">
                    <span className="text-[10px] font-mono text-text-tertiary truncate" title={k}>{k}</span>
                    <span className="text-[10px] font-mono text-text-secondary flex-shrink-0">{String(v)}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
        {/* Account-balance what-if — rebases the Max DD % KPI (moved here from that card). */}
        {onBalanceChange && defaultBalance != null && balance != null && (
          <div className="px-3 py-3 border-t border-border-subtle flex-shrink-0">
            <div className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-tertiary mb-2">Account balance · rebases Max DD %</div>
            <div className="flex items-center gap-2">
              <input
                type="range" min={5000} max={250000} step={5000}
                value={Math.min(250000, Math.max(5000, balance))}
                onChange={e => onBalanceChange(Number(e.target.value))}
                className="flex-1 accent-accent cursor-pointer"
              />
              <span className="text-[11px] font-mono font-semibold tabular-nums text-text-primary whitespace-nowrap">${(balance / 1000).toFixed(0)}k</span>
            </div>
            <div className="mt-1 text-right">
              {balance === defaultBalance
                ? <span className="text-[9px] text-text-tertiary">default</span>
                : <button onClick={() => onBalanceChange(null)} className="text-[9px] text-accent hover:underline">reset to ${(defaultBalance / 1000).toFixed(0)}k</button>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── News filter (post-run) ──────────────────────────────────────────────────────
// The backtest runs RAW (the strategy trades straight through news). This card is the post-run
// view: remove trades that opened inside a high-impact news window (15 min before → 30 min after)
// or on a bank holiday, and watch the KPIs + equity curve update live. Pure client-side arithmetic
// on the raw trade curve — no re-run. Bank-holiday trades are ALWAYS removed (Aaron's rule); the
// toggle only governs news-window trades. Operates on run.equity_curve (the raw, firm-independent
// curve — the only one carrying entry_ms; per-firm sized curves are day-granular and unaffected).

// The kept trades rebuilt as a RUN — the same shape `KpiGrid` already takes, so the filter drives
// the page's real 12 KPIs instead of a duplicated five. This is exactly the transform `effRun` does
// for per-firm switching and `StackDetail.composeCombined` does for a portfolio: shallow-clone,
// override what the trades determine, then NULL every field that is derived from `daily_pnl` so the
// existing recompute path (computeFallbacks / computeProfitConcentration) redoes it off the filtered
// series. Nulling is load-bearing — a left-behind `sharpe` would be the raw run's, sitting in a grid
// labelled filtered.
function buildFilteredRun(run: Run, kept: EquityPoint[], curve: EquityPoint[]): Run {
  const pnls   = kept.map(t => t.profit ?? 0)
  const wins   = pnls.filter(p => p > 0)
  const losses = pnls.filter(p => p < 0)
  const grossWin  = wins.reduce((a, b) => a + b, 0)
  const grossLoss = Math.abs(losses.reduce((a, b) => a + b, 0))

  // Daily P&L regrouped from the kept trades. Regime tags are carried over by DATE from the raw
  // series, so the regime overlay and the per-regime table keep working (a regime is a property of
  // the market on a date — removing a trade cannot change it).
  const regimeByDate = new Map((run.daily_pnl ?? []).map(d => [d.date, d.regime_tag]))
  const byDay = new Map<string, number>()
  for (const t of kept) if (t.date) byDay.set(t.date, (byDay.get(t.date) ?? 0) + (t.profit ?? 0))
  const daily: DailyPnlPoint[] = [...byDay.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([date, pnl]) => ({ date, pnl, regime_tag: regimeByDate.get(date) }))

  let cum = 0, peak = 0, maxDd = 0
  for (const p of pnls) { cum += p; peak = Math.max(peak, cum); maxDd = Math.max(maxDd, peak - cum) }

  return {
    ...run,
    net_pnl:      pnls.reduce((a, b) => a + b, 0),
    trade_count:  kept.length,
    win_rate:     kept.length ? wins.length / kept.length : 0,
    // Same convention as the backend: null when there is no denominator. KpiGrid recovers ∞ from the
    // trade list itself, so an undefeated filtered run still prints ∞ rather than a dash.
    profit_factor: grossLoss > 0 ? grossWin / grossLoss : null,
    max_drawdown:  maxDd,
    avg_win:       wins.length   ? grossWin / wins.length : null,
    avg_loss:      losses.length ? losses.reduce((a, b) => a + b, 0) / losses.length : null,
    equity_curve:  curve,
    daily_pnl:     daily,
    // Recomputed downstream from the filtered daily series.
    worst_day_pnl: null,
    sharpe: null,
    // NOT from the daily series: the row is labelled in trades, so it is counted off the kept
    // trades here. Nulling it and letting a daily-row fallback answer put consecutive losing DAYS
    // in a row that says "N trades" — which is what it did until 2026-07-31.
    worst_losing_streak: worstLosingStreakOf(pnls),
    profit_concentration_pct: null,
    // Recomputed on the filtered day count, not carried over and not zeroed — the flag means "too
    // few days that actually traded for the Sharpe to mean anything", and removing trades can only
    // push a run TOWARDS that, so inheriting `false` would silence the warning exactly where it
    // starts to matter. Threshold mirrors the backend's `active_day_count < 10`.
    sharpe_low_sample: daily.length < 10,
    avg_trade_duration_min: avgDurationOf(kept),
    // NOT recomputable, and not guessed: NT8/MT5's own Sharpe for the whole run has no filtered
    // version. Reads as "—" while filtered, which is the honest answer.
    platform_sharpe: null,
  }
}

// Average time in a position, over whatever trades are handed in. ALL of them must carry both
// timestamps or the answer is null — an average over the subset that happens to have times is a
// different statistic wearing this one's label, and there is no way to see that on the card. NT8
// and MT5 curves carry neither time, so those runs get a dash exactly as they do unfiltered.
function avgDurationOf(trades: EquityPoint[]): number | null {
  if (!trades.length) return null
  let total = 0
  for (const t of trades) {
    if (t.entry_ms == null || t.exit_ms == null) return null
    total += t.exit_ms - t.entry_ms
  }
  return total / trades.length / 60000
}

// ONE exclusion rule as a row: tick, name, the trades it costs, and any settings it owns nested
// underneath. The count is what the rule MATCHES, shown ticked or not — so the row is also the price
// tag on turning it on. Both rules render through this; neither is hidden, which is the whole point.
// The panel this replaced applied the holiday rule invisibly, so the pill could report trades being
// removed while the only switch on screen said the news ones were kept.
function ExcludeRule({ checked, onChange, label, note, count, tone, children }: {
  checked: boolean; onChange: (next: boolean) => void
  label: string; note?: string; count: number; tone: 'holiday' | 'news'; children?: React.ReactNode
}) {
  return (
    <div className={`rounded-md border px-2.5 py-2 ${checked ? 'border-border-default bg-bg-sunken' : 'border-border-subtle'}`}>
      <button
        type="button"
        onClick={() => onChange(!checked)}
        className="w-full flex items-center gap-2 text-left cursor-pointer group"
      >
        <span className={`w-3.5 h-3.5 rounded-[3px] border flex items-center justify-center shrink-0 transition-colors ${
          checked ? 'bg-accent border-accent' : 'border-border-default group-hover:border-text-tertiary'}`}>
          {checked && <Check size={10} className="text-bg-base" strokeWidth={3} />}
        </span>
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${tone === 'holiday' ? 'bg-neg-text' : 'bg-gold-text'}`} />
        <span className="text-[12px] text-text-primary flex-1 min-w-0">
          {label}
          {note && <span className="text-text-tertiary"> · {note}</span>}
        </span>
        <span className="text-[12px] tabular-nums text-text-secondary shrink-0">
          {count} {count === 1 ? 'trade' : 'trades'}
        </span>
      </button>
      {children && checked && <div className="mt-2 pl-[22px] space-y-1.5">{children}</div>}
    </div>
  )
}

export type NewsFilter = ReturnType<typeof useNewsFilter>

// The filter's whole state, owned by the PAGE rather than by any one control, because THREE things
// read it: the pill on the Performance header, the Performance KPI grid (which recomputes off
// `filteredRun`), and the main Equity chart (which redraws on `filteredCurve`). It has shed a copy
// of the run's numbers twice for the same reason — first its own 200px equity curve, then its own
// five KPI tiles. Each time the answer was the same: reshape the page's real readout, don't ship a
// smaller second one beside it.
function useNewsFilter(run: Run | undefined) {
  // BOTH rules default OFF (2026-08-01, Aaron's call). The page opens on the run EXACTLY AS TRADED
  // and every number on it is the backtest's own — turning a rule on is then a deliberate what-if
  // rather than something already applied before you looked.
  //
  // This replaces two different defaults, and the reason is the same for both: a filtered default
  // means the headline figure on screen is not the run's result, and nothing about a checkbox
  // further down the page makes that obvious. Holidays defaulted ON (they were hardcoded always-on
  // until 2026-07-30 and merely became visible then), and news followed the strategy's own
  // `avoid_news` flag, so the default silently differed BETWEEN strategies — two runs of the same
  // window could open on different trade counts with no indication why.
  //
  // `strategy.avoid_news` is still real metadata off the strategy's meta.json; it just no longer
  // decides what you see first. Do not re-wire it here without asking — "the page shows the run"
  // is the property being protected.
  const [removeNewsChoice, setRemoveNewsChoice] = useState<boolean | null>(null)
  const removeNews = removeNewsChoice ?? false
  const [removeHolidays, setRemoveHolidays] = useState(false)
  const [pre, setPre]   = useState(15)                 // block window before an event (minutes)
  const [post, setPost] = useState(30)                 // block window after an event (minutes)
  const enabled = (run?.equity_curve.length ?? 0) > 0
  const { data: report, isLoading } = useRunNews(run?.run_id ?? null, pre, post, enabled)

  // Raw trades = curve points carrying a per-trade P&L (a leading balance anchor, if any, has none).
  const rawTrades = useMemo(
    () => (run?.equity_curve ?? []).filter(p => p.profit != null || p.direction),
    [run?.equity_curve],
  )

  // Apply both rules in one pass. The COUNTS are what each rule matches, not what it removed — a
  // rule's row shows its price whether or not it is currently ticked, so you can see what turning it
  // on would cost before you turn it on. A trade matching both is counted as a holiday only, so the
  // two counts never double-count the same trade against the total.
  const view = useMemo(() => {
    const tag = new Map<number, NewsTradeTag>()
    for (const t of report?.trades ?? []) if (t.index != null) tag.set(t.index, t)
    const kept: EquityPoint[] = []
    let holidayCount = 0, newsCount = 0
    for (const p of rawTrades) {
      const tg = tag.get(p.index)
      if (tg?.in_holiday)   { holidayCount++; if (removeHolidays) continue }
      else if (tg?.in_news) { newsCount++;    if (removeNews)     continue }
      kept.push(p)
    }
    return { kept, holidayCount, newsCount }
  }, [rawTrades, report, removeNews, removeHolidays])

  // The kept trades rebuilt as a curve the MAIN equity chart can draw. It must be rebuilt on the
  // same BALANCE basis as the original — that chart derives its starting balance from the first
  // point (`equity - profit`), anchors the y-axis on it and colour-splits the line there, so a curve
  // restarted at 0 (what the old mini chart drew) would silently rebase the whole panel to zero.
  // Leading non-trade anchor points are carried through untouched; trades are renumbered so trade-#
  // mode counts the trades actually shown.
  const filteredCurve = useMemo<EquityPoint[] | null>(() => {
    const removed = rawTrades.length - view.kept.length
    if (!removed) return null                       // nothing taken out — the real curve is correct
    const anchors = (run?.equity_curve ?? []).filter(p => p.profit == null && !p.direction)
    const startBal = rawTrades[0].equity - (rawTrades[0].profit ?? 0)
    const from = anchors.length ? anchors[anchors.length - 1].index + 1 : 1
    let cum = 0
    return [
      ...anchors,
      ...view.kept.map((p, i) => ({ ...p, index: from + i, equity: startBal + (cum += (p.profit ?? 0)) })),
    ]
  }, [rawTrades, view.kept, run?.equity_curve])

  const hasEntryTimes = rawTrades.some(p => p.entry_ms != null)
  const active = !!report?.has_data && hasEntryTimes && filteredCurve != null

  // The whole run rebuilt on the kept trades — what the page's KPI grid reads while the filter is on.
  const filteredRun = useMemo(
    () => (run && filteredCurve ? buildFilteredRun(run, view.kept, filteredCurve) : null),
    [run, view.kept, filteredCurve],
  )

  return {
    enabled, isLoading, report, pre, setPre, post, setPost,
    removeNews, setRemoveNewsChoice, removeHolidays, setRemoveHolidays,
    ...view, filteredCurve, filteredRun, hasEntryTimes,
    totalTrades: rawTrades.length,   // the run as traded — the denominator of "N of M counted"
    // How many trades the CURRENT settings take out. Derived from the kept list rather than summed
    // from the two counts: the counts are per-RULE and a trade can match both, so adding them would
    // over-report. Lives here because the pill and the Performance header both state it, and two
    // copies of this expression is exactly how they would come to disagree.
    excluded: rawTrades.length - view.kept.length,
    isNt8: isNt8Runner(run?.runner),   // only NT8 has a "Reload charts" that can backfill trade times
    // `active` = the filter is actually removing trades right now, so the main chart is showing the
    // FILTERED run and has to say so. Everything else on the page still reports the raw backtest.
    active,
    // `usable` = the calendar answered and the trades carry times, so the knobs mean something.
    usable:     !!report?.has_data && hasEntryTimes,
    noData:     !isLoading && !!report && !report.has_data,
    oldRun:     !isLoading && !!report && report.has_data && !hasEntryTimes,
    nothingHit: !isLoading && !!report && report.has_data && hasEntryTimes
                && view.holidayCount === 0 && view.newsCount === 0,
  }
}

function NewsFilterPill({ news, blocked = null }: { news: NewsFilter; blocked?: string | null }) {
  const {
    isLoading, pre, setPre, post, setPost,
    removeNews, setRemoveNewsChoice, removeHolidays, setRemoveHolidays,
    holidayCount, newsCount, totalTrades, excluded, noData, oldRun, nothingHit, usable,
  } = news

  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  // Click-outside / Escape to dismiss. The popover holds live controls, so it must NOT close on an
  // inner click the way a menu would — dragging a slider is a mousedown inside it.
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  // The pill counts what is OUT of the numbers beside it. Always a count of excluded trades, never
  // a state word: "News kept" read as "nothing removed" while 3 holiday trades were being removed
  // by a rule the UI never showed. One number, one meaning, in every state.
  const label = blocked ? 'Excluding n/a'
    : isLoading ? 'Checking calendar…'
    : noData  ? 'No calendar data'
    : oldRun  ? 'No trade times'
    : excluded ? `Excluding ${excluded} ${excluded === 1 ? 'trade' : 'trades'}`
    : 'Excluding nothing'

  const disabled = !!blocked || isLoading || !usable

  return (
    <div ref={wrapRef} className="relative shrink-0">
      <button
        onClick={() => setOpen(o => !o)}
        disabled={disabled}
        title={blocked ?? undefined}
        className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${
          excluded > 0 ? 'border-accent/40 bg-accent/15 text-accent'
                       : 'border-border-subtle bg-bg-sunken text-text-secondary hover:text-text-primary'}`}
      >
        <Newspaper size={12} className="shrink-0" />
        <span className="tabular-nums">{label}</span>
        <ChevronDown size={12} className={`shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        // Right-anchored so a wide popover on a right-aligned pill can't run off the column.
        // BOTH exclusion rules are listed, each with its own trade count. The old panel showed one
        // News Keep/Remove switch and silently applied a second rule (holidays, always on) that had
        // no control and no row — so the pill could read "news kept" while trades were still being
        // removed, which is unreadable rather than merely terse. A rule that affects the numbers
        // gets a line, even when it is not yours to change.
        <div className="absolute right-0 top-[calc(100%+6px)] z-50 w-[330px] rounded-lg border border-border-default bg-bg-surface shadow-2xl shadow-black/50 p-3 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">
              Exclude from these numbers
            </span>
            <InfoTip text="The backtest ran RAW — the strategy traded straight through news. This is arithmetic on the finished trade list, not a re-run, so it is instant. It reshapes the Performance numbers and the Equity chart only; the firm Evaluation, the price chart and the regime table still report every trade." />
          </div>

          <ExcludeRule
            checked={removeHolidays}
            onChange={setRemoveHolidays}
            label="Bank holidays"
            note="on by default"
            count={holidayCount}
            tone="holiday"
          />

          <ExcludeRule
            checked={removeNews}
            onChange={setRemoveNewsChoice}
            label="High-impact news"
            count={newsCount}
            tone="news"
          >
            {/* The blackout window either side of a release, nested under the rule it belongs to so
                it can't read as a global setting. Both re-tag live off the backend. */}
            <label className="flex items-center gap-2 text-[11px] text-text-tertiary">
              <span className="w-10 shrink-0">Before</span>
              <input type="range" min={0} max={120} step={5} value={pre}
                onChange={e => setPre(Number(e.target.value))}
                className="flex-1 accent-accent cursor-pointer" />
              <span className="w-8 text-right tabular-nums text-text-primary font-medium">{pre}m</span>
            </label>
            <label className="flex items-center gap-2 text-[11px] text-text-tertiary">
              <span className="w-10 shrink-0">After</span>
              <input type="range" min={0} max={120} step={5} value={post}
                onChange={e => setPost(Number(e.target.value))}
                className="flex-1 accent-accent cursor-pointer" />
              <span className="w-8 text-right tabular-nums text-text-primary font-medium">{post}m</span>
            </label>
          </ExcludeRule>

          <div className="border-t border-border-subtle pt-2.5 text-[12px] text-text-secondary">
            {nothingHit
              ? 'No release or holiday landed on a trade — nothing to exclude.'
              : <><span className="tabular-nums font-medium text-text-primary">{totalTrades - excluded}</span>
                  {' of '}
                  <span className="tabular-nums">{totalTrades}</span>
                  {' trades counted'}</>}
          </div>
        </div>
      )}
    </div>
  )
}

// The Performance section label, with the news filter's pill on the right of it. The label row
// already spanned the column with nothing in it, so the whole control costs zero vertical space —
// and putting it HERE rather than in a section of its own is what removed the duplicated KPI tiles:
// the filter reshapes these numbers, so it belongs on their header.
function PerformanceHeader({ news, blocked, filtered, collapsed, onToggle }: {
  news: NewsFilter; blocked: string | null; filtered: boolean
  collapsed: boolean; onToggle: () => void
}) {
  return (
    <div className="flex items-center justify-between gap-3 mb-2">
      {/* The suffix names the SIZE of the exclusion, not the fact of it. "news filtered" told you a
          filter existed without saying what it did or how much it moved — and it was wrong half the
          time, since holidays are excluded whether or not the news rule is on. */}
      <button
        onClick={onToggle}
        title={collapsed ? 'Show the supporting metrics' : 'Hero numbers only'}
        className="flex items-center gap-1.5 text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] transition-colors hover:text-text-primary"
      >
        <ChevronDown size={13} className={`transition-transform ${collapsed ? '-rotate-90' : ''}`} />
        Performance
        {filtered && (
          <span className="text-accent normal-case tracking-normal font-medium">
            · {news.totalTrades - news.excluded} of {news.totalTrades} trades
          </span>
        )}
      </button>
      {news.enabled && <NewsFilterPill news={news} blocked={blocked} />}
    </div>
  )
}

// The states where the filter cannot run at all get a one-line explanation under the grid rather
// than a popover nobody can open — the pill is disabled, so it has nowhere to put this.
function NewsFilterNote({ news }: { news: NewsFilter }) {
  const { noData, oldRun, isNt8 } = news
  if (!noData && !oldRun) return null
  return (
    <div className="flex items-start gap-2 text-[11px] text-text-tertiary">
      <Info size={12} className={`mt-[2px] shrink-0 ${oldRun ? 'text-warn-text' : 'text-text-tertiary'}`} />
      {noData
        ? <span>News filter is off: no calendar data cached for these months. Backfill with <code className="text-text-secondary">engines/news/tools/backfill.py</code>.</span>
        : <span>News filter is off: this run recorded no trade times. {isNt8
            ? <><span className="text-text-secondary font-medium">Reload charts</span> or rerun it to enable it.</>
            : <><span className="text-text-secondary font-medium">Rerun it</span> to enable it.</>}</span>}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function BacktestDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate     = useNavigate()
  // A leg opened from a stack carries the stack id in nav state, so Back returns to that stack
  // instead of the Runs list.
  const location     = useLocation()
  const fromStack    = (location.state as { fromStack?: string } | null)?.fromStack ?? null
  const { data: run, isLoading } = useBacktestRun(runId ?? null)
  // A tuning iteration is a standalone run derived from a baseline (source_run_id set,
  // not a sweep/optimization child). Fetch its baseline to wire up breadcrumbs.
  const isTuneIteration = !!run?.source_run_id && !run?.optimization_id && !run?.sweep_id
  const { data: tuneBaseline } = useBacktestRun(isTuneIteration ? run!.source_run_id : null)
  // Tuning iterations already run FROM this run. Unfiltered so it shares the Runs list's cache
  // entry rather than opening a second one. Without this the only way to discover that a run had
  // ever been tuned was to go back to the Runs list and spot the nested rows.
  const { data: allRuns } = useBacktestRuns()
  const tuneCount = useMemo(
    () => (allRuns ?? []).filter(r => r.source_run_id === runId && !r.sweep_id && !r.optimization_id).length,
    [allRuns, runId],
  )
  const { data: strategy } = useStrategy(run?.strategy_id ?? null)
  // Owned here, not in the card, so the main Equity chart can redraw on the kept trades (see
  // useNewsFilter). The card renders the controls and the before/after comparison off this too.
  const news = useNewsFilter(run)
  const [paramsCollapsed, setParamsCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem('bt_params_panel') === 'collapsed' } catch { return false }
  })
  const toggleParams = () => setParamsCollapsed(c => {
    const next = !c
    try { localStorage.setItem('bt_params_panel', next ? 'collapsed' : 'open') } catch { /* quota */ }
    return next
  })
  const { ref: headerRef, scrolled, height: headerH, collapse } = useStickyBanner()
  const { data: progress }       = useLabProgress()
  const stopBacktest             = useStopBacktest()
  const reloadCharts             = useReloadCharts()
  const refreshChartSpec         = useRefreshChartSpec()
  const retryBacktest            = useRetryBacktest()
  const { data: runningJob }     = useRunningVpsJob()
  const { data: stressTests }    = useStressTests(run?.run_id)
  const { data: stressLock }     = useRunningStressLock()
  const latestStress             = stressTests?.[0]
  const [showStressModal, setShowStressModal] = useState(false)
  const [showEvalPicker, setShowEvalPicker] = useState(false)
  const [showRerun, setShowRerun] = useState(false)
  const [overlayOn, setOverlayOn] = useState(getOverlayPref)
  const handleOverlayToggle = useCallback((v: boolean) => { setOverlayOn(v); setOverlayPref(v) }, [])
  // Equity-chart series toggles (TradingView-style panel): profit histogram, trade excursions,
  // run-up/drawdown period shading. Each persists across runs.
  // One bottom-bar toggle (like TradingView). On runs with per-trade excursion (Python runner) it
  // shows the combined trade-excursion bar — solid net result + translucent favorable/adverse halo;
  // on other runs it falls back to plain per-trade profit bars. Run-ups & drawdowns is its own thing.
  const [histOn, setHistOn] = useState(() => getBoolPref(_HIST_KEY))
  const toggleHist = useCallback((v: boolean) => { setHistOn(v); setBoolPref(_HIST_KEY, v) }, [])
  const [rudOn, setRudOn] = useState(() => getBoolPref(_RUD_KEY))
  const toggleRud = useCallback((v: boolean) => { setRudOn(v); setBoolPref(_RUD_KEY, v) }, [])
  // Equity x-axis: calendar (default) or trade number. Calendar is canonical — it's the axis the
  // tuning workbench compares runs on, and the only one where a flat month reads as a flat month.
  const [xMode, setXMode] = useState<XMode>(getXMode)
  const toggleXMode = useCallback((v: XMode) => { setXMode(v); setXModePref(v) }, [])
  const hasExcursionData = useMemo(
    () => run?.equity_curve.some(p => p.favorable != null || p.adverse != null) ?? false,
    [run?.equity_curve],
  )
  // Primary chart tab (the big charts) + secondary tab (supporting charts). Price lazy-loads.
  const [primaryTab, setPrimaryTab] = useState<'equity' | 'sized' | 'price' | 'breakdown'>('equity')
  const [fullscreenChart, setFullscreenChart] = useState<string | null>(null)
  // When a run is scored against several firms, show ONE at a time (a wall of cards is
  // confusing). This selects which firm's evaluation card is shown; defaults to the first
  // and resets when the run changes. Performance follows the same firm once sizing lands.
  const [selectedEvalIdx, setSelectedEvalIdx] = useState(0)
  useEffect(() => { setSelectedEvalIdx(0) }, [run?.run_id])

  // Capital-based scores (Calmar, Max DD %) rebase the run to an account balance. Default to the
  // primary evaluated ruleset's account_size; the slider is a view-time what-if override only.
  const { data: rulesets } = useRulesets()
  const rulesetBalance = rulesets?.find(r => r.id === run?.evaluations?.[0]?.ruleset_id)?.account_size ?? null
  const [balanceOverride, setBalanceOverride] = useState<number | null>(null)
  useEffect(() => { setBalanceOverride(null) }, [run?.run_id])
  const balance = balanceOverride ?? rulesetBalance

  // The firm whose evaluation is currently shown in the verdict ribbon.
  const selectedEval = (run && run.evaluations.length)
    ? run.evaluations[Math.min(selectedEvalIdx, run.evaluations.length - 1)]
    : null

  // The drawdown meter's simulated tail — the worst-1% drawdown Monte Carlo produced.
  // Gated on dd_basis === 'percent': the dollar basis is not comparable to a peak-relative
  // percentage on a compounding run, and tests run before 2026-07-30 have no percent columns
  // at all. Null means "not measured", and the meter says exactly that rather than drawing a
  // tail of zero — an unmeasured tail is unknown, not absent.
  const stressTailPct = (latestStress?.dd_basis === 'percent' && latestStress.pct1_max_dd_pct != null)
    ? latestStress.pct1_max_dd_pct
    : null

  const [perfCollapsed, setPerfCollapsed] = useState(getPerfCollapsed)
  const togglePerfCollapsed = useCallback(() => {
    setPerfCollapsed(prev => {
      const next = !prev
      try { localStorage.setItem(_PERF_COLLAPSED_KEY, String(next)) } catch { /* quota */ }
      return next
    })
  }, [])

  // Calendar span of the run, for the ribbon's trades-per-month cadence.
  const runSpanDays = useMemo(() => {
    const daily = run?.daily_pnl ?? []
    if (daily.length < 2) return null
    const t0 = new Date(daily[0].date.slice(0, 10)).getTime()
    const t1 = new Date(daily[daily.length - 1].date.slice(0, 10)).getTime()
    const days = (t1 - t0) / 86_400_000
    return days > 0 ? days : null
  }, [run?.daily_pnl])

  // Engine-sized runs size the SAME strategy differently per firm (each firm's own contract
  // ladder / drawdown floor), so every firm has its OWN net P&L, daily P&L and sized timeline.
  // Swap the selected firm's sized results into a shallow copy so the KPI cards, the Sized-account
  // chart and the timeline table all follow the firm the user is viewing. Unit-size runs (and
  // older runs with no per-firm sizing) carry no `net_pnl` on the eval → effRun stays the headline.
  const effRun = useMemo<Run | undefined>(() => {
    if (!run) return run
    const ev = selectedEval
    if (!ev || ev.net_pnl == null) return run
    const sizedTl = trimToLastActive(ev.sized_timeline?.length ? ev.sized_timeline : run.sized_timeline)
    const cutoff = sizedTl.length ? sizedTl[sizedTl.length - 1].date : ''
    return {
      ...run,
      net_pnl: ev.net_pnl,
      max_drawdown: ev.max_drawdown,
      profit_factor: ev.profit_factor,
      win_rate: ev.win_rate,
      trade_count: ev.trade_count,
      avg_win: ev.avg_win,
      avg_loss: ev.avg_loss,
      // Trim the frozen post-breach tail so the sized chart + timeline stop where trading stopped.
      sized_timeline: sizedTl,
      // Daily P&L trimmed to the same cutoff so its chart ends with the others (and the daily-derived
      // KPIs — worst day / streak / Sharpe / concentration — don't count dead post-breach flat days).
      daily_pnl: cutoff
        ? (ev.daily_pnl?.length ? ev.daily_pnl : run.daily_pnl).filter(d => d.date <= cutoff)
        : (ev.daily_pnl?.length ? ev.daily_pnl : run.daily_pnl),
      // Sized trade-by-trade curve for THIS firm — drives its Drawdown, Long/Short, Calmar,
      // Max DD % and Z-Score. The Equity/"Strategy (1 unit)" tab keeps the raw run.equity_curve.
      equity_curve: ev.equity_curve?.length ? ev.equity_curve : run.equity_curve,
      // Metrics derived from daily P&L: null the persisted primary-firm values so they recompute
      // from THIS firm's sized daily P&L (worst day / streak / Sharpe via `fallback`, profit conc).
      worst_day_pnl: null,
      worst_losing_streak: null,
      sharpe: null,
      platform_sharpe: null,
      sharpe_low_sample: false,
      profit_concentration_pct: null,
    }
  }, [run, selectedEval])

  // ── What the Performance grid reads ─────────────────────────────────────────
  // The news filter drives the page's REAL 12 KPIs — there is no second set of tiles anywhere.
  //
  // It can only do that off the raw, one-unit trade curve. A per-firm SIZED curve is path
  // dependent: removing trade #7 changes the balance going into #8, which changes its position
  // size, which changes every trade after it. That is a re-run, not arithmetic — and the sized
  // curve is re-indexed 1..N over only the trades that firm took, so the news tags (keyed on raw
  // indices) would not even line up. So when a firm's sizing is actually overriding the numbers,
  // the filter is refused outright rather than applied to something it does not describe.
  const newsBlocked = (run && effRun && effRun.equity_curve !== run.equity_curve)
    ? 'Not available while a firm’s sized numbers are shown — position sizes depend on the trades before them, so removing one needs a re-run, not arithmetic.'
    : null
  const newsOnKpis = news.active && !newsBlocked && news.filteredRun != null
  const kpiRun     = newsOnKpis ? news.filteredRun! : effRun

  const fallback = useMemo(
    () => computeFallbacks(kpiRun?.daily_pnl ?? []),
    [kpiRun?.daily_pnl],
  )
  // The unfiltered side of every card's "vs unfiltered" delta.
  const rawFallback = useMemo(
    () => computeFallbacks(effRun?.daily_pnl ?? []),
    [effRun?.daily_pnl],
  )
  const kpiCompare = (newsOnKpis && effRun)
    ? { run: effRun, fallback: rawFallback, equity: effRun.equity_curve }
    : null

  const hasRealRegimeTags = useMemo(
    () => run?.daily_pnl.some(d => d.regime_tag && d.regime_tag !== 'UNKNOWN') ?? false,
    [run?.daily_pnl],
  )

  // What the main Equity chart draws: the news/holiday-filtered curve while that filter is removing
  // trades, otherwise the run's real curve. `filteredCurve` is null unless something was actually
  // taken out, so the ordinary case is the untouched curve — reference-identical, nothing rebuilt.
  // Gated on the SAME condition as the KPI grid. Holidays are removed without anyone touching the
  // toggle, so on a firm-sized run — where the grid refuses the filter — the chart would otherwise
  // quietly draw a filtered curve under numbers that aren't, with a disabled pill and nothing
  // saying why. One switch drives both.
  const equityCurve = (newsOnKpis ? news.filteredCurve : null) ?? run?.equity_curve ?? []

  // Regime bands for the main equity chart, in whatever units its x-axis is using.
  // DATE mode reads the run's FULL-CALENDAR timeline — every trading day in the window, classified
  // server-side — so the bands show the market's real regime calendar and match the tuning
  // workbench exactly. Runs completed before the backend emitted a timeline fall back to the old
  // per-trade-day derivation. TRADE mode always uses the per-trade one (only it is indexed by trade).
  const regimeBands = useMemo(
    () => {
      if (!overlayOn || !run) return []
      // One source of truth for "what regime was this date": the run's FULL-CALENDAR timeline when
      // it has one, else whatever tags its traded days carry (runs completed before the timeline
      // existed). Then project it onto whichever axis the chart is on.
      const map = new Map<string, string>()
      for (const d of run.regime_timeline ?? []) map.set(d.date, d.regime)
      if (!map.size) for (const d of run.daily_pnl) if (d.regime_tag) map.set(d.date, d.regime_tag)
      if (!map.size) return []
      return xMode === 'trade'
        // Trade-# bands are indexed off the CURVE, so they must read the same curve the chart is
        // drawing — the filtered one when the news filter is removing trades, or every band after
        // the first removal sits one trade to the right of the trade it describes.
        ? regimeBandsByIndex(equityCurve, map)
        : regimeBandsFromTimeline([...map.entries()].map(([date, regime]) => ({ date, regime })))
    },
    [overlayOn, xMode, run?.regime_timeline, equityCurve, run?.daily_pnl],
  )

  // Regime is a market property (same calendar days for every firm), so tag lookup uses the
  // primary run's tagged daily P&L; day positions come from the selected firm's sized timeline.
  const sizedRegimeBands = useMemo(
    () => (overlayOn && hasRealRegimeTags && run && effRun?.sized_timeline.length)
      ? computeSizedRegimeBands(effRun.sized_timeline, run.daily_pnl)
      : [],
    [overlayOn, hasRealRegimeTags, effRun?.sized_timeline, run?.daily_pnl],
  )

  // Did the SELECTED firm breach its trailing drawdown floor? If so the account is dead — trading
  // stops at the breach, which is why the sized/breakdown charts end there. Surface the date so the
  // page explains its own cutoff instead of just looking truncated.
  const breachInfo = useMemo(() => {
    const ev = selectedEval
    if (!ev || ev.drawdown_pass !== false) return null
    const day = (ev.sized_timeline || []).find(t => t.risk_floor != null && t.eod_balance < t.risk_floor)
    return { date: day?.date ?? null }
  }, [selectedEval])

  const isRunning  = run?.status === 'running'
  const isFailed   = run?.status.startsWith('failed') ?? false
  const isComplete    = run?.status === 'complete'
  const scope         = runnerScope(run?.runner)
  const isNt8         = isNt8Runner(run?.runner)
  // Optimization combo run: exists in the grid export but has never been fully backtested
  const isOptCombo    = !!run?.optimization_id && !run?.equity_curve?.length && isComplete
  const stressBlocked = runnerMarket(run?.runner) === 'futures'
    ? (stressLock?.futures ?? false)
    : (stressLock?.forex ?? false)
  const jobBusy       = !!runningJobFor(runningJob, run?.runner)?.running

  // Rerun / full-backtest. For an optimizer combo with no inheritable ruleset the backend replies
  // status="needs_ruleset" instead of starting — we then open a picker and re-fire with the choice.
  const runFullBacktest = useCallback(() => {
    if (!run) return
    retryBacktest.mutate(run.run_id, {
      onSuccess: (data) => { if (data.status === 'needs_ruleset') setShowEvalPicker(true) },
    })
  }, [run, retryBacktest])

  const confirmFullBacktest = useCallback((rulesetIds: string[]) => {
    if (!run) return
    retryBacktest.mutate(
      { runId: run.run_id, evaluateRulesets: rulesetIds },
      { onSuccess: () => setShowEvalPicker(false) },
    )
  }, [run, retryBacktest])

  // A standalone run owns its own period, so its rerun goes through the modal (pick the window
  // first). Sweep children and optimizer combos inherit the set's period — they re-fire directly.
  const ownsPeriod = !!run && !run.sweep_id && !run.optimization_id
  const confirmRerun = useCallback((start: string, end: string) => {
    if (!run) return
    retryBacktest.mutate(
      { runId: run.run_id, startDate: start, endDate: end },
      { onSuccess: () => setShowRerun(false) },
    )
  }, [run, retryBacktest])

  const progressMatches = progress?.job_id === run?.run_id
  const runPct       = isRunning ? (progressMatches ? (progress?.pct ?? 0) : 0) : 0
  const runMessage   = isRunning ? (progressMatches ? (progress?.message ?? 'Starting…') : 'Starting…') : ''
  const runStartedAt = isRunning ? (progressMatches ? (progress?.started_at ?? null) : null) : null

  const backLabel = fromStack ? 'Stack'
    : isTuneIteration ? 'Tuning workbench'
    : run?.optimization_id ? 'Optimization'
    : run?.sweep_id ? 'Sweep'
    : 'Backtests'
  const backPath  = fromStack ? `/backtests/stacks/${fromStack}`
    : isTuneIteration ? `/backtests/runs/${run!.source_run_id}/tune`
    : run?.optimization_id ? `/optimizations/${run.optimization_id}`
    : run?.sweep_id ? `/backtests/sweeps/${run.sweep_id}`
    : '/backtests'

  return (
    // Full-bleed page (cancel main's p-[22px]): a full-width header row on top, then a
    // flex row that shares the space below it between the params panel and the content.
    <div className="-m-[22px] flex flex-col min-h-[calc(100vh-56px)]">
      {/* ── Full-width header — condenses to a single row once scrolled ────── */}
      <div
        ref={headerRef}
        className={`sticky -top-[22px] z-30 bg-bg-base px-[22px] pt-[22px] transition-[padding] duration-200 ${scrolled ? 'pb-3 shadow-[0_10px_18px_-14px_rgba(0,0,0,0.8)]' : 'pb-8'}`}
      >
        {!scrolled && (
          <button
            onClick={() => navigate(backPath)}
            className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
          >
            <ArrowLeft size={14} /> {backLabel}
          </button>
        )}

        {isLoading && <Skeleton />}

        {run && (
          <div>
            <div className="flex items-center justify-between gap-4">
              {scrolled ? (
                <div className="flex items-center gap-2 min-w-0">
                  <button onClick={() => navigate(backPath)} title={backLabel} className="flex items-center text-text-tertiary hover:text-text-secondary transition-colors flex-shrink-0">
                    <ArrowLeft size={14} />
                  </button>
                  <h1
                    className="text-[15px] font-semibold leading-tight truncate min-w-0 cursor-pointer hover:text-accent transition-colors"
                    onClick={() => navigate(`/strategies/${run.strategy_id}`)}
                    title="Go to strategy"
                  >
                    {run.strategy_name || run.strategy_id}
                  </h1>
                  <span className="inline-flex items-center px-1.5 py-[1px] rounded text-[11px] font-semibold font-mono bg-accent/10 text-accent border border-accent/20 flex-shrink-0">
                    {run.instrument}
                  </span>
                  <span className="inline-flex items-center px-1.5 py-[1px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-secondary font-mono flex-shrink-0 truncate max-[1100px]:hidden">
                    {fmtDate(run.start_date)} → {fmtDate(run.end_date)}
                  </span>
                  {run.evaluations.length > 0 && (
                    <div className="max-[900px]:hidden">
                      <HeaderRulesetChip evals={run.evaluations} selected={selectedEvalIdx} onSelect={setSelectedEvalIdx} compact />
                    </div>
                  )}
                  {run.sized && (
                    <span
                      className="inline-flex items-center px-1.5 py-[1px] rounded text-[11px] font-semibold bg-accent/10 text-accent border border-accent/20 flex-shrink-0 max-[1100px]:hidden"
                      title="Sizing engine set contract size for this run."
                    >
                      Sized · {sizingModeLabel(run.sizing_mode, run.manual_risk_pct)}
                    </span>
                  )}
                </div>
              ) : (
              <div>
                <div className="flex items-center gap-3 flex-wrap mb-2">
                  <h1
                    className="text-h1 font-semibold leading-tight cursor-pointer hover:text-accent transition-colors"
                    onClick={() => navigate(`/strategies/${run.strategy_id}`)}
                    title="Go to strategy"
                  >
                    {run.strategy_name || run.strategy_id}
                  </h1>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono bg-accent/10 text-accent border border-accent/20">
                    {run.instrument}
                  </span>
                  <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-secondary font-mono">
                    {fmtDate(run.start_date)} → {fmtDate(run.end_date)}
                  </span>
                  {run.evaluations.length > 0 && (
                    <HeaderRulesetChip evals={run.evaluations} selected={selectedEvalIdx} onSelect={setSelectedEvalIdx} />
                  )}
                  {run.sized && (
                    <span
                      className="inline-flex items-center gap-1 px-2 py-[3px] rounded text-[11px] font-semibold bg-accent/10 text-accent border border-accent/20"
                      title="The sizing engine set contract size from each ruleset's contract ladder and room left — this run reflects real prop-firm sizing, not unit size."
                    >
                      Engine-sized · {sizingModeLabel(run.sizing_mode, run.manual_risk_pct)}
                    </span>
                  )}
                  {isTuneIteration && (
                    <span className="inline-flex items-center gap-1.5 px-2 py-[3px] rounded text-[11px] font-semibold bg-accent/10 text-accent border border-accent/20">
                      <SlidersHorizontal size={11} />
                      Tuning iteration
                      <button onClick={() => navigate(`/backtests/runs/${run.source_run_id}/tune`)} className="underline decoration-dotted underline-offset-2 hover:opacity-80">
                        open workbench
                      </button>
                      {tuneBaseline?.optimization_id && (
                        <>
                          <span className="text-accent/40">·</span>
                          <button onClick={() => navigate(`/optimizations/${tuneBaseline.optimization_id}`)} className="underline decoration-dotted underline-offset-2 hover:opacity-80">
                            optimization
                          </button>
                        </>
                      )}
                    </span>
                  )}
                </div>
              </div>
              )}
              <div className="flex items-center gap-2 flex-shrink-0">
                {!isRunning && (
                  <button
                    onClick={() => ownsPeriod ? setShowRerun(true) : runFullBacktest()}
                    disabled={retryBacktest.isPending || jobBusy}
                    className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-bg-hover disabled:opacity-40"
                    title={jobBusy
                      ? `${RUNNER_LABEL[scope]} is busy — wait for the current job to finish`
                      : run.optimization_id && !run.equity_curve?.length
                        ? 'Run a full backtest on this parameter set to get charts and trade data'
                        : `${run.status.startsWith('failed') ? 'Retry' : 'Rerun'} this backtest${ownsPeriod ? ' — pick the period first' : ''}`}
                  >
                    {retryBacktest.isPending
                      ? <RefreshCw size={14} className="animate-spin" />
                      : <Play size={14} />}
                    {run.status.startsWith('failed') ? 'Retry' : run.optimization_id && !run.equity_curve?.length ? 'Full Backtest' : 'Rerun'}
                  </button>
                )}
                {run.status === 'complete' && (run.trade_count ?? 0) > 0 && (
                  <button
                    onClick={() => navigate(`/backtests/runs/${run.run_id}/tune`)}
                    className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-bg-hover"
                    title={tuneCount
                      ? `Open the tuning workbench — ${tuneCount} iteration${tuneCount !== 1 ? 's' : ''} already run from this backtest`
                      : 'Tweak parameters and compare iterations'}
                  >
                    <SlidersHorizontal size={14} /> Tune
                    {tuneCount > 0 && (
                      <span className="px-1.5 py-[1px] rounded-full text-[10px] font-semibold bg-accent/15 text-accent tabular-nums">
                        {tuneCount}
                      </span>
                    )}
                  </button>
                )}
                {(run.trade_count ?? 0) > 0 && <OptimizeButton run={run} />}
                {run?.status === 'complete' && (run.trade_count ?? 0) > 0 && (() => {
                  const stressRunning = latestStress && latestStress.status !== 'complete' && !latestStress.status.startsWith('failed')
                  if (stressRunning) return (
                    <button
                      onClick={() => navigate(`/stress-tests/${latestStress.stress_test_id}`)}
                      className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded border border-accent/30 bg-accent/5 text-accent hover:bg-accent/10 transition-colors"
                    >
                      <Activity size={14} className="animate-pulse flex-shrink-0" />
                      In progress
                    </button>
                  )
                  const tc = run.trade_count ?? 0
                  const tooFewForStress = tc < MIN_TRADES_FOR_STRESS
                  return (
                    <button
                      onClick={() => !stressBlocked && !tooFewForStress && setShowStressModal(true)}
                      disabled={stressBlocked || tooFewForStress}
                      title={
                        tooFewForStress
                          ? `Needs ≥${MIN_TRADES_FOR_STRESS} trades to stress test — this run has ${tc}. Get more trades from more data first (longer period, more instruments, or a smaller timeframe).`
                          : stressBlocked ? `A ${runnerMarket(run?.runner)} stress test is already running` : undefined
                      }
                      className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-bg-hover disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <Activity size={14} />
                      Stress Test
                      {latestStress?.grade && <RobustnessGradeBadge grade={latestStress.grade} size="sm" />}
                    </button>
                  )
                })()}
                {isRunning && <StatusPill status={run.status} size="md" />}
              </div>
              {showStressModal && run && <RunStressTestModal run={run} onClose={() => setShowStressModal(false)} navigate={navigate} />}
              {showEvalPicker && run && (
                <FullBacktestEvalModal
                  run={run}
                  busy={retryBacktest.isPending}
                  onConfirm={confirmFullBacktest}
                  onClose={() => setShowEvalPicker(false)}
                />
              )}
              {showRerun && run && (
                <RerunModal
                  run={run}
                  busy={retryBacktest.isPending}
                  onConfirm={confirmRerun}
                  onClose={() => setShowRerun(false)}
                />
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Body: params panel (left) shares the space below the header with the content (right) ── */}
      {run && (
        <div className="flex items-stretch flex-1 min-h-0">
          <ParamsSidePanel
            run={run}
            paramSchema={strategy?.param_schema}
            baselineParams={isTuneIteration ? tuneBaseline?.params : undefined}
            collapsed={paramsCollapsed}
            onToggle={toggleParams}
            balance={balance}
            defaultBalance={rulesetBalance}
            onBalanceChange={setBalanceOverride}
            headerH={headerH}
          />
          <div className="flex-1 min-w-0 px-[22px] pb-[22px] space-y-8">

          {/* ── Banners ───────────────────────────────────────────────────── */}
          {isRunning && <RunningBanner pct={runPct} message={runMessage} startedAt={runStartedAt} onStop={() => stopBacktest.mutate(run.run_id)} runId={run.run_id} runner={run.runner ?? 'ninjatrader'} steps={scope === 'mt5' ? MT5_RUN_STEPS : scope === 'python' ? PYTHON_RUN_STEPS : NT8_RUN_STEPS} />}
          {isFailed && <FailureBanner run={run} />}
          {/* ── Evaluation + Performance ──────────────────────────────────── */}
          {/* One row of four question cards: Made, Risked, Trusted, Verdict. The evaluation used
              to be a fixed-height COLUMN beside a 6+6 KPI grid, then a full-width ribbon above
              three cards — see PerformancePanel and VerdictCard for why both are gone. An
              optimizer combo has no verdict to card up, so it keeps the bar, which is a prompt to
              run a real backtest rather than a grade and earns its width. */}
          {isComplete && (
            <div className="space-y-2.5">
              <PerformanceHeader
                news={news} blocked={newsBlocked} filtered={newsOnKpis}
                collapsed={perfCollapsed} onToggle={togglePerfCollapsed}
              />
              <PerformancePanel
                run={kpiRun!} fallback={fallback} equity={kpiRun!.equity_curve}
                balance={balance} compare={kpiCompare} filtered={newsOnKpis}
                limitPct={selectedEval?.personal_max_drawdown_from_peak_pct ?? null}
                tailPct={stressTailPct}
                collapsed={perfCollapsed}
                ribbon={isOptCombo ? (
                  <UnscoredRibbon
                    tradeCount={run.trade_count}
                    onRunFullBacktest={runFullBacktest}
                    busy={retryBacktest.isPending || jobBusy}
                  />
                ) : null}
                verdict={isOptCombo ? null : (
                  <VerdictCard
                    ev={selectedEval}
                    tradeCount={kpiRun?.trade_count ?? run.trade_count}
                    totalTrades={run.trade_count}
                    spanDays={runSpanDays}
                    filtered={newsOnKpis}
                    collapsed={perfCollapsed}
                  />
                )}
              />
              <NewsFilterNote news={news} />
            </div>
          )}

          {/* The News & holiday filter no longer has a section of its own. It was carrying a
              duplicate copy of five KPIs the Performance grid already showed; it now lives as a
              pill on that grid's header and reshapes the real twelve. */}
          {/* ── Charts ────────────────────────────────────────────────────── */}
          {isComplete && !isOptCombo && (() => {
            const hasCharts = run.equity_curve.length > 0

            // Drawdown limit line follows the SELECTED firm (the chart plots that firm's sized
            // curve). Personal/demo have no trailing EOD rule — firm_max_loss_eod is the 0 sentinel
            // and must never render as a "$0 limit" reference line.
            const evalLimits: Array<{ limit: number; label: string; pass: boolean }> = []
            if (selectedEval && !isPersonal(selectedEval) && selectedEval.firm_max_loss_eod) {
              evalLimits.push({
                limit: selectedEval.firm_max_loss_eod,
                label: selectedEval.ruleset_name,
                pass: selectedEval.drawdown_pass,
              })
            }

            // The Sized tab appears only for engine-sized runs (a reshaped strategy emitted
            // engine_trades → the engine produced a day-by-day timeline). Inert for every unit-size run.
            const hasSized = run.sized && effRun!.sized_timeline.length > 0
            const firmName = selectedEval?.ruleset_name || 'the selected firm'
            const endsAtBreach = breachInfo ? ' Ends where the account breached.' : ''
            const SUBS: Record<string, string> = {
              equity: hasSized
                ? 'The bare strategy at a flat 1 unit — no sizing. This is the raw edge: is there one at all?'
                : 'Steadily rising = good. Big peak then long decline = giving back gains.',
              sized: hasSized
                ? `${firmName}'s real sized account: end-of-day balance vs the trailing risk floor. Gap = buffer; crossing = breach.${endsAtBreach}`
                : 'The real sized account: end-of-day balance vs the trailing risk floor. Gap = buffer; crossing = breach.',
              price: 'Candlesticks with trade context.',
              breakdown: hasSized
                ? `Sized to ${firmName} — drawdown, daily P&L, and long vs short.${endsAtBreach}`
                : 'Drawdown, daily P&L, and long vs short — the supporting detail.',
            }
            const TITLES: Record<string, string> = {
              equity: hasSized ? 'Strategy (1 unit)' : 'Equity curve', sized: 'Sized account', price: 'Price', breakdown: 'Breakdown',
            }
            const hasDirection = effRun!.equity_curve.some(p => p.direction)
            const primaryTabs: ReadonlyArray<readonly [string, string]> = [
              ['equity', hasSized ? 'Strategy (1 unit)' : 'Equity'],
              ...(hasSized ? [['sized', 'Sized account'] as const] : []),
              ['price', 'Price'],
              ['breakdown', 'Breakdown'],
            ]
            const subLabel = (t: string) => <div className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-secondary mb-1.5">{t}</div>

            // Explains the cutoff: a breached account stops trading, so the sized + breakdown charts
            // end at the breach instead of running to the end of the requested range.
            const breachNote = breachInfo ? (
              <div className="flex items-start gap-2 mb-3 px-3 py-2 rounded-md bg-neg-muted border border-neg-text/20 text-neg-text text-[12px] leading-snug">
                <AlertTriangle size={13} className="flex-shrink-0 mt-[1px]" />
                <span>
                  <span className="font-semibold">{firmName} breached its drawdown limit{breachInfo.date ? ` on ${fmtDate(breachInfo.date)}` : ''}.</span>{' '}
                  The account failed there, so trading stopped — these charts end at the breach, not at the end of the test.
                </span>
              </div>
            ) : null

            // isModal=true means this render call is from inside ChartModal (equity/breakdown only).
            // Price chart manages its own fullscreen internally via position:fixed so the single
            // klinecharts instance is never disposed/re-inited during the fullscreen toggle.
            // View controls for a chart tab — rendered BOTH inline and in the fullscreen header.
            // Fullscreen is where a chart is actually read, so every control must exist there too
            // (the axis switch especially: expanding to compare against a date is the whole point).
            // Actions (Refresh / Rebuild) deliberately stay inline — they're not view state.
            const chartControls = (key: string): React.ReactNode => (
              <>
                {key === 'equity' && (
                  <SeriesToggle label={hasExcursionData ? 'Trade excursions' : 'Histogram'} on={histOn} onChange={toggleHist} />
                )}
                {key === 'equity' && (
                  <SeriesToggle label="Run-ups & drawdowns" on={rudOn} onChange={toggleRud} />
                )}
                {key === 'equity' && (
                  <XModeToggle value={xMode} onChange={toggleXMode} />
                )}
                {(key === 'equity' || key === 'sized') && hasRealRegimeTags && (
                  <RegimeOverlayToggle on={overlayOn} onChange={handleOverlayToggle} />
                )}
              </>
            )

            const renderChart = (key: string, h: number, isModal = false): React.ReactNode => {
              switch (key) {
                case 'equity':
                  return (
                    <>
                      <EquityCurveChart
                        data={equityCurve}
                        bands={regimeBands}
                        showHistogram={histOn}
                        showRunupDrawdown={rudOn}
                        height={h}
                        xMode={xMode}
                        windowStart={run.start_date}
                      />
                      {overlayOn && regimeBands.length > 0 && <RegimeLegend bands={regimeBands} />}
                    </>
                  )
                case 'sized':
                  return (
                    <>
                      {breachNote}
                      <SizedEquityCurveChart data={effRun!.sized_timeline} bands={sizedRegimeBands} height={h} />
                      <SizedCurveLegend
                        mode={run.sizing_mode}
                        manualPct={run.manual_risk_pct}
                        profitable={effRun!.sized_timeline[effRun!.sized_timeline.length - 1].eod_balance >= effRun!.sized_timeline[0].eod_balance}
                      />
                      {overlayOn && sizedRegimeBands.length > 0 && <RegimeLegend bands={sizedRegimeBands} />}
                    </>
                  )
                case 'price': {
                  // Price chart manages its own fullscreen via position:fixed — never rendered
                  // inside ChartModal. isModal=true means we're in a modal (equity/breakdown):
                  // skip the price chart entirely there.
                  if (isModal) return null
                  return runId ? (
                    <PriceChartPanel
                      runId={runId}
                      height={h}
                      isFullscreen={fullscreenChart === 'price'}
                      onFullscreenClose={() => setFullscreenChart(null)}
                    />
                  ) : null
                }
                case 'breakdown': {
                  // All three supporting charts share the tab's height: drawdown full-width on top,
                  // then daily P&L + long vs short side by side. Scales up when the tab is expanded.
                  const hDraw = Math.max(140, Math.round((h - 56) * 0.45))
                  const hRow = Math.max(160, Math.round((h - 56) * 0.55))
                  return (
                    <div className="space-y-8">
                      {breachNote}
                      <div>
                        {subLabel('Drawdown from peak')}
                        <DrawdownChart equity={effRun!.equity_curve} limitLines={evalLimits} height={hDraw} />
                      </div>
                      <div className={hasDirection ? 'grid gap-6 lg:grid-cols-2' : ''}>
                        <div>
                          {subLabel('Daily P&L')}
                          <DailyPnlChart data={effRun!.daily_pnl} netPnl={effRun!.net_pnl} height={hRow} />
                        </div>
                        {hasDirection && (
                          <div>
                            {subLabel('Long vs Short')}
                            <DirectionBreakdown equity={effRun!.equity_curve} />
                          </div>
                        )}
                      </div>
                    </div>
                  )
                }
                default:
                  return null
              }
            }

            return (
              <div className="space-y-4">
                <div className="flex items-start justify-between">
                  <SectionLabel>Charts</SectionLabel>
                  {!hasCharts && isNt8 && (
                    <button
                      onClick={() => runId && reloadCharts.mutate(runId)}
                      disabled={reloadCharts.isPending}
                      className="flex items-center gap-[6px] px-3 py-[5px] rounded-md text-[12px] font-medium bg-accent-muted border border-accent/30 text-accent hover:bg-accent/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <RefreshCw size={12} className={reloadCharts.isPending ? 'animate-spin' : ''} />
                      {reloadCharts.isPending ? 'Exporting from NT8…' : 'Load chart data from NT8'}
                    </button>
                  )}
                </div>

                {!hasCharts ? (
                  <div className="bg-bg-surface border border-border-subtle rounded-lg flex flex-col items-center justify-center gap-2 py-16 text-center px-6">
                    <div className="text-text-secondary text-[13px] font-medium">No chart data yet</div>
                    <div className="text-text-tertiary text-[11px] leading-relaxed max-w-xs">
                      {scope === 'mt5'
                        ? 'Chart data is parsed from the MT5 report at completion. If empty, the report may not have included trade data.'
                        : scope === 'python'
                        ? 'Chart data is built locally at completion from the same cached bars the run replayed. If empty, the run made no trades.'
                        : 'Click "Load chart data from NT8" — requires NT8 Strategy Analyzer open with this run\'s results loaded.'}
                    </div>
                  </div>
                ) : (
                  <>
                    {/* One tabbed panel: Equity / Price / Breakdown (the 3 supporting charts together) */}
                    <ChartTabPanel
                      tabs={primaryTabs}
                      active={primaryTab}
                      onActive={k => setPrimaryTab(k as 'equity' | 'sized' | 'price' | 'breakdown')}
                      sub={SUBS[primaryTab]}
                      height={520}
                      onExpand={() => setFullscreenChart(primaryTab)}
                      render={renderChart}
                      right={<>
                        {chartControls(primaryTab)}
                        {isNt8 && (
                          <button
                            onClick={() => runId && reloadCharts.mutate(runId)}
                            disabled={reloadCharts.isPending}
                            className="flex items-center gap-[6px] px-2 py-[4px] rounded text-[11px] text-text-tertiary hover:text-text-secondary transition-colors disabled:opacity-50"
                          >
                            <RefreshCw size={11} className={reloadCharts.isPending ? 'animate-spin' : ''} />
                            Refresh
                          </button>
                        )}
                        {!isNt8 && primaryTab === 'price' && (
                          <button
                            onClick={() => runId && refreshChartSpec.mutate(runId)}
                            disabled={refreshChartSpec.isPending}
                            title="Rebuild chart data (re-fetches candles + recomputes structure)"
                            className="flex items-center gap-[6px] px-2 py-[4px] rounded text-[11px] text-text-tertiary hover:text-text-secondary transition-colors disabled:opacity-50"
                          >
                            <RefreshCw size={11} className={refreshChartSpec.isPending ? 'animate-spin' : ''} />
                            Rebuild chart
                          </button>
                        )}
                      </>}
                    />

                    {/* Performance by Regime — permanent panel */}
                    {hasRealRegimeTags && <PerformanceByRegimeTable run={run} />}

                    {/* Sizing timeline — engine's day-by-day audit; sized runs only */}
                    {hasSized && <SizedTimelineTable run={effRun!} />}

                    {fullscreenChart && fullscreenChart !== 'price' && (
                      <ChartModal
                        title={TITLES[fullscreenChart] ?? 'Chart'}
                        onClose={() => setFullscreenChart(null)}
                        render={h => renderChart(fullscreenChart, h, true)}
                        controls={chartControls(fullscreenChart)}
                      />
                    )}
                  </>
                )}
              </div>
            )
          })()}

          {/* ── Logs ─────────────────────────────────────────────────────── */}
          {runId && !isOptCombo && <LogsSection runId={runId} autoExpand={isFailed || isRunning} isRunning={isRunning} isComplete={isComplete} isFailed={isFailed} />}
          </div>
        </div>
      )}

      {/* Holds total scroll height constant while the banner is condensed (see useStickyBanner) so
          scrollTop is never clamped — prevents the condense flicker on short pages. */}
      <div aria-hidden className="flex-shrink-0" style={{ height: collapse }} />
    </div>
  )
}
