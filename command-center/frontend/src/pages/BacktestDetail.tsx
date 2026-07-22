import { Fragment, Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, AlertTriangle,
  CheckCircle, XCircle, Minus, Info, Square, RefreshCw, RotateCcw, Activity, Layers, Play,
  Copy, Check, SlidersHorizontal, Minimize2, Newspaper,
} from 'lucide-react'
import {
  AreaChart, Area, ComposedChart, Line, BarChart, Bar, PieChart, Pie, Label,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine, ReferenceArea, ReferenceDot,
} from 'recharts'
import { useBacktestRun, useRunLog, useLabProgress, useStopBacktest, useReloadCharts, useRetryBacktest, useRunningVpsJob, useStrategy, useRulesets, useChartSpec, useRefreshChartSpec, useRunCandles, useRunNews } from '@/hooks/useLab'
import InfoTip from '@/components/InfoTip'
import { PeriodPicker } from '@/components/PeriodPicker'
import { isNt8Runner, runnerScope, runnerMarket, runningJobFor, RUNNER_LABEL } from '@/lib/runner'
import { useStressTests, useRunStressTest, useRunningStressLock } from '@/hooks/useStressTests'
import type { BacktestDetail as Run, EvaluationDetail, EquityPoint, DailyPnlPoint, ParamSchemaEntry, SizedTimelineDay, NewsTradeTag, SizingMode } from '@/types'
import { C } from '@/themes/chart'
import { REGIME_COLORS, REGIME_LABEL } from '@/lib/regime'

import { ChartTabPanel, ChartModal } from '@/components/ChartTabPanel'
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

function dollarShort(n: number | null | undefined, signed = false): string {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : signed ? '+' : ''
  if (abs >= 1000) return `${sign}$${(abs / 1000).toFixed(1)}k`
  return `${sign}$${abs.toFixed(0)}`
}

// Renders a dollar amount at full precision when it fits its cell, abbreviating to $11.5k only when
// the full string would overflow (the big KPI numbers crop in a narrow card). It never rounds harder
// than one decimal — $12k for $11,525 reads as a different number. A hidden copy of each form is
// measured against the cell, so it switches back to full whenever space returns — e.g. when the grid
// expands and the value font shrinks. Observes the cell and both copies.
// FIT_SLACK keeps the last glyph off the card's padding edge instead of touching the border. The
// headline money card also gets a wider grid column (KPI_COLS) so the exact figure fits at 34px.
const FIT_SLACK = 2

function FitMoney({ n, signed = false }: { n: number | null | undefined; signed?: boolean }) {
  const wrapRef = useRef<HTMLSpanElement>(null)
  const fullRef = useRef<HTMLSpanElement>(null)
  const abbrRef = useRef<HTMLSpanElement>(null)
  const [short, setShort] = useState(false)
  const full = dollar(n, signed)
  const abbr = dollarShort(n, signed)
  useEffect(() => {
    const wrap = wrapRef.current, fullEl = fullRef.current
    if (!wrap || !fullEl) return
    const measure = () => {
      const cell = wrap.getBoundingClientRect().width - FIT_SLACK
      setShort(fullEl.getBoundingClientRect().width > cell)
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(wrap)
    ro.observe(fullEl)
    if (abbrRef.current) ro.observe(abbrRef.current)
    return () => ro.disconnect()
  }, [full, abbr])
  if (n == null) return <span>—</span>
  return (
    <span ref={wrapRef} className="block relative whitespace-nowrap">
      <span ref={fullRef} aria-hidden className="invisible absolute left-0 top-0 whitespace-nowrap pointer-events-none">{full}</span>
      <span ref={abbrRef} aria-hidden className="invisible absolute left-0 top-0 whitespace-nowrap pointer-events-none">{abbr}</span>
      <span title={short ? full : undefined}>{short ? abbr : full}</span>
    </span>
  )
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
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

function pfCls(pf: number | null): string {
  if (pf == null) return 'text-text-tertiary'
  if (pf >= 2.0) return 'text-pos-text'
  if (pf >= 1.5) return 'text-warn-text'
  return 'text-neg-text'
}

function pfLabel(pf: number | null): string {
  if (pf == null) return 'gross wins ÷ gross losses'
  if (pf >= 2.0) return 'strong — wins 2× losses'
  if (pf >= 1.5) return 'good'
  if (pf >= 1.0) return 'marginal'
  return 'losing — below 1.0'
}

function sharpeCls(s: number | null): string {
  if (s == null) return 'text-text-tertiary'
  if (s >= 1.0) return 'text-pos-text'
  if (s >= 0.5) return 'text-warn-text'
  return 'text-neg-text'
}

function sharpeLabel(s: number | null, estimated: boolean): string {
  if (s == null) return 'risk-adjusted annual return'
  const base =
    s >= 2.0 ? 'excellent' :
    s >= 1.0 ? 'good' :
    s >= 0.5 ? 'marginal' : 'poor'
  return estimated ? `${base} (estimated)` : base
}

function worstStreakCls(n: number | null): string {
  if (n == null) return 'text-text-tertiary'
  if (n >= 6) return 'text-neg-text'
  if (n >= 3) return 'text-warn-text'
  return 'text-text-primary'
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

// ── Calmar ratio ─────────────────────────────────────────────────────────────
// Real Calmar = CAGR ÷ max-drawdown-as-fraction (same shape as
// algos/shared/shared_calmar.py). Both inputs are fractions of starting capital,
// and the compounding in CAGR means starting capital does NOT cancel out — it is
// genuinely required. With a balance supplied (from the ruleset's account_size or the
// what-if slider), the equity curve is rebased to that balance and the score computes.

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
  const dd      = maxDrawdownOf(rebased)
  if (dd === 0) return null
  const years   = days / 365
  const cagr    = Math.pow(1 + netPnl / balance, 1 / Math.max(years, 0.1)) - 1
  return cagr / (dd / balance)
}

function calmarCls(c: number | null): string {
  if (c == null) return 'text-text-tertiary'
  if (c >= 3.0) return 'text-pos-text'
  if (c >= 1.0) return 'text-warn-text'
  return 'text-neg-text'
}

function calmarLabel(c: number | null): string {
  if (c == null) return 'set an account balance'
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

function zScoreLabel(z: number | null): string {
  if (z == null) return 'runs test — needs wins & losses'
  const a = Math.abs(z)
  if (a <= 1.5) return 'streaks look random'
  if (a <= 2)   return 'mild streaking'
  return 'non-random streaking'
}

// ── Profit concentration over time ───────────────────────────────────────────
// Share of total gross profit (sum of positive daily P&L) earned in the single most
// profitable calendar quarter of the test span. The span (first→last date) is split into
// 4 equal slices. High = the edge is clustered in one period — a classic curve-fit signal.
function computeProfitConcentration(daily: DailyPnlPoint[]): number | null {
  const dated = daily.filter(d => d.date)
  if (dated.length < 2) return null
  const t0 = new Date(dated[0].date.slice(0, 10)).getTime()
  const t1 = new Date(dated[dated.length - 1].date.slice(0, 10)).getTime()
  const span = t1 - t0
  if (!(span > 0)) return null
  const q = [0, 0, 0, 0]
  let gross = 0
  for (const d of dated) {
    if (d.pnl <= 0) continue
    gross += d.pnl
    let idx = Math.floor(((new Date(d.date.slice(0, 10)).getTime() - t0) / span) * 4)
    if (idx > 3) idx = 3
    if (idx < 0) idx = 0
    q[idx] += d.pnl
  }
  if (!(gross > 0)) return null
  return (Math.max(...q) / gross) * 100
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

interface FallbackMetrics {
  worstDay: number | null
  worstStreak: number | null
  sharpe: number | null
}

function computeFallbacks(daily_pnl: DailyPnlPoint[]): FallbackMetrics {
  if (!daily_pnl.length) return { worstDay: null, worstStreak: null, sharpe: null }

  const pnls = daily_pnl.map(d => d.pnl)

  const worstDay = Math.min(...pnls)

  let maxStreak = 0, cur = 0
  for (const p of pnls) {
    if (p < 0) { cur++; maxStreak = Math.max(maxStreak, cur) }
    else cur = 0
  }

  let sharpe: number | null = null
  const n = pnls.length
  if (n >= 10) {
    const mean = pnls.reduce((a, b) => a + b, 0) / n
    const variance = pnls.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1)
    const std = Math.sqrt(variance)
    if (std > 0) sharpe = (mean / std) * Math.sqrt(252)
  }

  return { worstDay, worstStreak: maxStreak, sharpe }
}

// ── KPI grid ──────────────────────────────────────────────────────────────────

// Fixed pixel heights shared by the eval card and the KPI grid on lg. COLLAPSED sits at the short
// height (one KPI row, sized to fit the tallest verdict card); EXPANDED grows both columns together
// so the two KPI rows each get enough room (no crop) while still matching the eval card exactly.
// Fixed per state → paging evaluations never grows/shrinks the row.
const KPI_ROW_H = 196
const KPI_ROW_H_EXPANDED = 228

type KpiTone = 'good' | 'bad' | 'warn' | 'neutral'
const KPI_TONE_BORDER: Record<KpiTone, string> = {
  good:    'border-l-pos-text/60',
  bad:     'border-l-neg-text/60',
  warn:    'border-l-warn-text/60',
  neutral: 'border-l-border-default',
}
// Left-accent tone derived from the value's text-colour class, so the accent always agrees with
// the number's colour — one source of sentiment.
function kpiTone(valueCls?: string): KpiTone {
  if (!valueCls) return 'neutral'
  if (valueCls.includes('pos'))  return 'good'
  if (valueCls.includes('neg'))  return 'bad'
  if (valueCls.includes('warn')) return 'warn'
  return 'neutral'
}

// Six KPI columns, but the first is wider. Column one carries the money values (Net P&L, and Profit
// Concentration/Expectancy on the second row) — a 5-figure "+$11,525" needs ~30% more room than a
// "72.7%" to render at the collapsed row's 34px without running into the card's padding. Widening
// the column is what buys that room; the type stays the same size in every card. Both rows use this
// template so the two grids stay aligned.
const KPI_COLS = 'grid-cols-[1.4fr_repeat(5,minmax(0,1fr))]'

function KpiGrid({ run, fallback, equity = [], balance = null, showMore = false, fixedHeight = null }: {
  run: Run; fallback: FallbackMetrics; equity?: EquityPoint[]; balance?: number | null
  showMore?: boolean; fixedHeight?: number | null
}) {
  const pnlCls = run.net_pnl == null ? '' : run.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'

  const sharpe      = run.sharpe             ?? fallback.sharpe
  const worstDay    = run.worst_day_pnl      ?? fallback.worstDay
  const worstStreak = run.worst_losing_streak ?? fallback.worstStreak
  const sharpeEst   = run.sharpe == null && fallback.sharpe != null
  // Canonical daily-√252 Sharpe shown as the value; platform's own value + low-sample as sub.
  const sharpeSub   = (
    <span>
      {sharpeLabel(sharpe, sharpeEst)}
      {run.platform_sharpe != null && (
        <span className="text-text-tertiary"> · platform: {run.platform_sharpe.toFixed(2)}</span>
      )}
      {run.sharpe_low_sample && <span className="text-warn-text"> · low sample &lt;10d</span>}
    </span>
  )
  const recoveryFactor = computeRecoveryFactor(run.net_pnl, run.max_drawdown, equity)
  // Capital-based scores rebase the equity to `balance` (the ruleset's account_size, or the
  // what-if slider). Both compute off the same stored run — no re-run, no backend.
  const calmar      = computeCalmar(equity, balance)

  // 7a — expectancy. $/trade is always available; R needs per-trade risk, which stored
  // trades don't carry (profit only), so expectancy_r is not computable — left out honestly.
  const expectancyUsd = (run.net_pnl != null && run.trade_count)
    ? run.net_pnl / run.trade_count
    : null
  // 7b — Wald–Wolfowitz z-score over the win/loss sequence.
  const zScore = computeZScore(equity)
  // 7c — profit concentration: largest quarter's share of gross profit. Prefer the
  // backend-persisted value (authoritative, feeds grading); fall back to the client calc
  // for older runs predating the column. Both use the identical formula, so they agree.
  const profitConc = run.profit_concentration_pct ?? computeProfitConcentration(run.daily_pnl ?? [])
  // 7d — max drawdown as % of capital. Uses the trade-derived drawdown (platform-agnostic)
  // over the chosen balance. Null only when no balance is available (no ruleset / no trades).
  const tradeDd  = equity.length >= 2 ? maxDrawdownOf(rebaseEquity(equity, 0)) : null
  const maxDdPct = (balance != null && balance > 0 && tradeDd != null)
    ? (tradeDd / balance) * 100
    : null
  // Dollar drawdown for the merged Max-DD card (trade-derived; falls back to the run's value).
  const ddDollar = tradeDd ?? (run.max_drawdown != null ? Math.abs(run.max_drawdown) : null)
  // Reward:risk for Expectancy's sub-line (Avg Win / Avg Loss folded in here).
  const rr = (run.avg_win != null && run.avg_loss != null && run.avg_loss !== 0)
    ? (run.avg_win / Math.abs(run.avg_loss)).toFixed(2) : null

  // ── Flat KPI layout: 6 core cards always shown, 6 "more" revealed in the same 6-col grid ──
  // Big-number cards with a sentiment-coloured left accent (matches the eval cards). Trade Count
  // moves out to the standout beside the verdict, not here.
  const calmarTip = `Annualized return (CAGR) ÷ max drawdown, both as a % of capital — so it cancels out: Calmar is capital-independent BY DESIGN and does NOT move with the Account balance slider. It reduces to ≈ annualized net P&L ÷ drawdown${recoveryFactor != null ? ` (= ${recoveryFactor.toFixed(2)} — the old Recovery Factor)` : ''}. The definitive risk-adjusted metric for funded traders; trade-derived, so NT8 and MT5 agree.`
  const expectancySub = (run.avg_win != null && run.avg_loss != null)
    ? `avg +$${run.avg_win.toFixed(0)} / -$${Math.abs(run.avg_loss).toFixed(0)}${rr ? ` · ${rr}:1 R:R` : ''}`
    : 'per trade'

  type KMetric = { key: string; label: string; value: React.ReactNode; valueCls?: string; tone?: KpiTone; sub?: React.ReactNode; tooltip?: string }

  // Core — always shown.
  const core: KMetric[] = [
    { key: 'netpnl', label: 'Net P&L', value: <FitMoney n={run.net_pnl} signed />, valueCls: pnlCls,
      sub: (balance != null && balance > 0 && run.net_pnl != null) ? `${(run.net_pnl / balance * 100).toFixed(1)}% return` : 'net of commissions',
      tooltip: "Total profit or loss after commissions. The bottom line." },
    { key: 'sharpe', label: 'Sharpe (annlzd)', value: sharpe != null ? sharpe.toFixed(2) : '—', valueCls: sharpeCls(sharpe), sub: sharpeSub,
      tooltip: "Return per unit of risk, annualized (daily P&L × √252) — the canonical definition shared with the optimizer and walk-forward. Days with no trade count as flat $0, so a strategy that sits out most days is scored on the whole period, not just the days it traded. 'platform' shows NT8/MT5's own reported Sharpe for reference (Python runs have no platform, so it's blank); note TradingView's Sharpe is monthly and NOT annualized — multiply it by √12 ≈ 3.46 to compare. Good ≥1.0, strong ≥2.0. Negative means the strategy loses more than doing nothing. 'low sample' flags fewer than 10 days that actually traded, where the value is statistically noisy." },
    { key: 'winrate', label: 'Win Rate', value: pct(run.win_rate), valueCls: winRateCls(run.win_rate), sub: winRateLabel(run.win_rate),
      tooltip: "% of trades that closed in profit. Good ≥60%, fair ≥50%, weak <50%. High win rate alone doesn't guarantee profitability — size of wins vs losses matters too." },
    { key: 'maxdd', label: 'Max DD % of Capital',
      value: maxDdPct != null ? `${maxDdPct.toFixed(1)}%` : '—',
      valueCls: maxDdPct != null ? 'text-neg-text' : 'text-text-tertiary', tone: 'neutral',
      sub: ddDollar != null ? `$${Math.round(ddDollar).toLocaleString()} peak-to-trough${maxDdPct == null ? ' · set a balance for %' : ''}` : 'set an account balance',
      tooltip: "Max drawdown — the largest peak-to-trough drop, shown both in dollars (sub-line) and as a % of the account balance (the value; ruleset's account_size, adjustable via the Account balance slider). Prop firms cap this hard. The dollar drawdown is trade-derived, identical across NT8 and MT5. Lower is better." },
    { key: 'pf', label: 'Profit Factor', value: run.profit_factor != null ? run.profit_factor.toFixed(2) : '—', valueCls: pfCls(run.profit_factor), sub: pfLabel(run.profit_factor),
      tooltip: "Gross wins ÷ gross losses. Below 1.0 is a losing strategy. Good ≥1.5, strong ≥2.0." },
    { key: 'calmar', label: 'Calmar Ratio', value: calmar != null ? calmar.toFixed(2) : '—', valueCls: calmarCls(calmar), sub: calmarLabel(calmar), tooltip: calmarTip },
  ]

  // More — revealed in the same grid, directly beneath the core row.
  const more: KMetric[] = [
    { key: 'profconc', label: 'Profit Concentration',
      value: profitConc != null ? `${profitConc.toFixed(0)}%` : '—',
      valueCls: concentrationCls(profitConc), sub: concentrationLabel(profitConc),
      tooltip: "Share of total gross profit (sum of positive daily P&L) earned in the single most profitable calendar quarter of the test span (split into 4 equal date slices). High means the edge is clustered in one period — a classic sign of curve-fitting to a recent regime. ≥60% is a red flag." },
    { key: 'expectancy', label: 'Expectancy', value: expectancyUsd != null ? `$${expectancyUsd.toFixed(2)}` : '—',
      valueCls: expectancyUsd != null ? (expectancyUsd >= 0 ? 'text-pos-text' : 'text-neg-text') : '', sub: expectancySub,
      tooltip: "Average net P&L per trade (net P&L ÷ trade count) — your edge per position. Sub-line shows avg win / avg loss and the win:loss (reward:risk) ratio. R-multiple expectancy needs per-trade risk, which stored trades don't carry (profit only), so it's omitted rather than guessed." },
    { key: 'zscore', label: 'Z-Score', value: zScore != null ? zScore.toFixed(2) : '—', valueCls: zScoreCls(zScore), sub: zScoreLabel(zScore),
      tooltip: "Wald–Wolfowitz runs test over the win/loss sequence. Measures whether wins and losses streak more than random chance. Within ±1.5 is healthy; beyond ±2 signals non-random streaking (positive = fewer runs / longer streaks, negative = alternating more than chance)." },
    { key: 'avgtrade', label: 'Avg Trade', value: run.avg_trade_duration_min != null ? `${run.avg_trade_duration_min.toFixed(0)} min` : '—',
      sub: run.avg_trade_duration_min != null ? 'avg duration / trade' : 'duration unavailable',
      tooltip: "Average time in a position per trade. The MT5 Strategy Tester report includes only trade-close times (no entry time), so duration can't be computed for MT5 runs — it shows as “—”." },
    { key: 'worstday', label: 'Worst Day', value: <FitMoney n={worstDay} />, valueCls: worstDay != null && worstDay < 0 ? 'text-neg-text' : '', sub: 'single worst trading day',
      tooltip: "Largest single-day loss. Compare this to your prop firm's daily loss limit — exceeding it would have failed the challenge that day." },
    { key: 'worststreak', label: 'Worst Streak', value: worstStreak != null ? `${worstStreak} L` : '—', valueCls: worstStreakCls(worstStreak), sub: 'consecutive losing days',
      tooltip: "Longest consecutive run of losing days. Tests whether you'd stay disciplined under sustained drawdown. ≥6 days is a red flag." },
  ]

  const card = (m: KMetric, fixedCard = false, valSize = 'text-[26px] lg:text-[30px]') => (
    <div
      key={m.key}
      className={`flex flex-col justify-center bg-bg-surface border border-border-subtle border-l-[3px] ${KPI_TONE_BORDER[m.tone ?? kpiTone(m.valueCls)]} rounded-xl px-4 py-3 overflow-hidden transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/30 ${fixedCard ? 'h-full min-h-[88px]' : 'min-h-[100px]'}`}
    >
      <div className="flex items-center text-[9px] font-bold uppercase tracking-[0.8px] text-text-tertiary">
        {m.label}{m.tooltip && <InfoTip text={m.tooltip} />}
      </div>
      <div className={`${valSize} font-bold tracking-[-0.6px] font-mono leading-none mt-1.5 transition-[font-size] duration-300 ${m.valueCls ?? ''}`}>{m.value}</div>
      <div className="text-[10px] text-text-tertiary mt-1 leading-snug min-h-[14px]">{m.sub}</div>
    </div>
  )

  // On lg the grid is pinned to the shared fixed height (fixedHeight), which already reflects the
  // collapsed/expanded state (the parent grows it when More metrics opens). Two row-grids with
  // explicit heights: collapsed → core row = full height; expanded → both rows at half height
  // summing (with the gap) to exactly the same total, so the grid and eval card always match.
  // Heights animate. Off lg → normal flow.
  const fh = fixedHeight
  if (fh != null) {
    const gap = 12
    const half = Math.max(0, (fh - gap) / 2)
    return (
      <div className="flex flex-col" style={{ height: fh }}>
        <div
          className={`grid ${KPI_COLS} gap-x-3 shrink-0`}
          style={{ height: showMore ? half : fh, transition: 'height 0.3s ease' }}
        >
          {core.map(m => card(m, true, showMore ? 'text-[26px]' : 'text-[34px]'))}
        </div>
        <div
          className={`grid ${KPI_COLS} gap-x-3 shrink-0 overflow-hidden`}
          style={{ height: showMore ? half : 0, marginTop: showMore ? gap : 0, transition: 'height 0.3s ease, margin-top 0.3s ease' }}
        >
          {more.map(m => card(m, true, 'text-[26px]'))}
        </div>
      </div>
    )
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      {core.map(m => card(m))}
      {showMore && more.map(m => card(m))}
    </div>
  )
}

// Lives in the Performance header (not below the grid) so the KPI grid can fill the column and
// stay the same height as the eval card.
function MoreMetricsToggle({ open, onToggle, count }: { open: boolean; onToggle: () => void; count: number }) {
  return (
    <button
      onClick={onToggle}
      className="inline-flex items-center gap-1.5 text-[12px] text-text-secondary hover:text-text-primary"
    >
      <ChevronRight size={13} className={`transition-transform ${open ? 'rotate-90' : ''}`} />
      {open ? 'Fewer metrics' : `More metrics (${count})`}
    </button>
  )
}

// Standout trade count — used in the no-evaluation fallback (the eval card carries it otherwise).
function TradeCountStandout({ count }: { count: number }) {
  return (
    <div className="bg-bg-surface border border-border-subtle border-l-[3px] border-l-accent rounded-lg px-4 py-3 flex items-center gap-3">
      <div className="text-[30px] font-bold font-mono leading-none text-accent tabular-nums">{count}</div>
      <div className="text-[11px] font-bold uppercase tracking-[0.6px] text-text-secondary">Trades</div>
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

interface RegimeBand { x1: number; x2: number; regime: string }

// Run-ups & drawdowns ribbon: each point is a "run-up" (equity at/above its running peak — green)
// or a "drawdown" (below the prior peak — red). Contiguous same-state points merge into one band;
// TradingView draws this as a thin colour strip along the bottom of the equity panel.
interface RudBand { x1: number; x2: number; up: boolean }
function computeRunupDrawdownBands(data: EquityPoint[]): RudBand[] {
  const bands: RudBand[] = []
  let peak = -Infinity
  let cur: RudBand | null = null
  for (const pt of data) {
    const up = pt.equity >= peak
    if (up) peak = pt.equity
    if (!cur || cur.up !== up) {
      cur = { x1: pt.index, x2: pt.index, up }
      bands.push(cur)
    } else {
      cur.x2 = pt.index
    }
  }
  for (let i = 0; i < bands.length - 1; i++) bands[i].x2 = bands[i + 1].x1
  return bands
}

function computeRegimeBands(equity: EquityPoint[], dailyPnl: DailyPnlPoint[]): RegimeBand[] {
  const dateToRegime = new Map<string, string>()
  for (const d of dailyPnl) dateToRegime.set(d.date, d.regime_tag ?? 'UNKNOWN')
  const bands: RegimeBand[] = []
  let cur: RegimeBand | null = null
  for (const trade of equity) {
    const dateKey = trade.date?.slice(0, 10)
    const regime = dateKey ? (dateToRegime.get(dateKey) ?? 'UNKNOWN') : 'UNKNOWN'
    if (!cur || cur.regime !== regime) {
      cur = { x1: trade.index, x2: trade.index, regime }
      bands.push(cur)
    } else {
      cur.x2 = trade.index
    }
  }
  // Tile the bands so they're contiguous (no gaps between regimes) — matches the tune page.
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

// A "nice" round tick step (1/2/5 × 10ⁿ) near the requested size.
function niceStep(raw: number): number {
  if (raw <= 0) return 1
  const mag = Math.pow(10, Math.floor(Math.log10(raw)))
  const n = raw / mag
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag
}

function EquityCurveChart({ data, bands = [], showHistogram = false, showRunupDrawdown = false, height = 300 }: {
  data: EquityPoint[]; bands?: RegimeBand[]
  showHistogram?: boolean; showRunupDrawdown?: boolean; height?: number
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
  const firstIdx   = data[0]?.index ?? 1
  const chartData: (EquityPoint & { _anchor?: boolean })[] =
    [{ index: firstIdx - 1, equity: startEq, _anchor: true }, ...data]
  const allValues  = data.map(d => d.equity)
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
  const eqTicks    = calIndexTicks(data)

  // Y ticks anchored ON the starting balance so it's always labelled, evenly spaced around it.
  const step = niceStep((yMax - yMin) / 5)
  const yTicks: number[] = [startEq]
  for (let t = startEq + step; t <= yMax; t += step) yTicks.push(t)
  for (let t = startEq - step; t >= yMin; t -= step) yTicks.unshift(t)

  // Profit histogram rides its own hidden axis, scaled to a bottom strip: domain [-barMax, 6×barMax]
  // puts the zero baseline ~14% up so green bars rise and red bars drop within the bottom band.
  const barMax = showProfitBars
    ? Math.max(1, ...data.map(d => Math.abs(d.profit ?? 0)))
    : 1

  // Run-up / drawdown ribbon segments, and a thin band at the very bottom of the plot to draw it in.
  // Pull the first segment left to the anchor so the ribbon spans the full axis (the curve starts at
  // the anchor point, one step left of the first trade).
  const rudBands = showRunupDrawdown ? computeRunupDrawdownBands(data) : []
  if (rudBands.length) rudBands[0].x1 = firstIdx - 1
  const rudY2 = yMin + (yMax - yMin) * 0.025

  return (
    <ResponsiveContainer key={`${bands.length}-${showHistogram}-${showExcursions}-${showRunupDrawdown}`} width="100%" height={height}>
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
        {bands.filter(b => b.regime !== 'UNKNOWN').map((b, i) => (
          <ReferenceArea key={`r${i}`} x1={b.x1} x2={b.x2} fill={REGIME_COLORS[b.regime] ?? REGIME_COLORS.UNKNOWN} fillOpacity={0.1} stroke="none" />
        ))}
        <XAxis
          dataKey="index"
          ticks={eqTicks}
          // Point scale keeps the line flush to the axis whether or not the histogram bars are on —
          // a bar series otherwise switches the axis to band scale, which pads both sides and shifts
          // the curve right, opening a gap between the y-axis and the starting balance.
          scale="point"
          padding={{ left: 0, right: 0 }}
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => {
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

function DrawdownChart({ equity, limitLines, height = 140 }: {
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

function RegimeOverlayToggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!on)}
      className={`flex items-center gap-1.5 px-2 py-[4px] rounded text-[11px] transition-colors ${
        on
          ? 'text-accent bg-accent/10 border border-accent/25'
          : 'text-text-tertiary hover:text-text-secondary border border-border-subtle'
      }`}
    >
      <Layers size={11} />
      Regimes
    </button>
  )
}

// Generic on/off pill for an equity-chart series (histogram / excursions / run-ups & drawdowns).
function SeriesToggle({ label, on, onChange }: { label: string; on: boolean; onChange: (v: boolean) => void }) {
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

function DirectionBreakdown({ equity }: { equity: EquityPoint[] }) {
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

function DailyPnlChart({ data, netPnl, height = 260 }: { data: DailyPnlPoint[]; netPnl: number | null; height?: number }) {
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

const VERDICT_CONFIG = {
  PASS:    { label: 'PASS',    bg: 'bg-pos-muted',  text: 'text-pos-text',  border: 'border-l-pos-text/50',  Icon: CheckCircle },
  WARN:    { label: 'WARN',    bg: 'bg-warn-muted', text: 'text-warn-text', border: 'border-l-warn-text/50', Icon: Minus       },
  DISCARD: { label: 'DISCARD', bg: 'bg-neg-muted',  text: 'text-neg-text',  border: 'border-l-neg-text/50',  Icon: XCircle     },
  INFO:    { label: 'INFO',    bg: 'bg-bg-sunken',  text: 'text-text-tertiary', border: 'border-l-border-default', Icon: Info   },
} as const

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

function EvalCard({ ev, netPnl, tradeCount, showName = true }: { ev: EvaluationDetail; netPnl?: number | null; tradeCount?: number | null; showName?: boolean }) {
  const cfg = VERDICT_CONFIG[ev.verdict as keyof typeof VERDICT_CONFIG] ?? VERDICT_CONFIG.DISCARD
  // Profitable runs that fail a firm rule get amber styling (not red) — keep the DISCARD label.
  const isWarnColor = cfg === VERDICT_CONFIG.DISCARD && (netPnl ?? 0) > 0
  const colorCfg    = isWarnColor ? VERDICT_CONFIG.WARN : cfg
  const { Icon }    = cfg

  return (
    <div className={`bg-bg-surface border border-border-subtle border-l-[3px] ${colorCfg.border} rounded-lg overflow-hidden h-full flex flex-col`}>
      {/* Header */}
      <div className="px-4 pt-3.5 pb-2.5 flex items-start justify-between gap-3">
        {showName && (
          <div className="text-[13px] font-semibold text-text-primary leading-tight">{ev.ruleset_name}</div>
        )}
        <span className={`inline-flex items-center gap-[5px] px-3 py-[5px] rounded-full text-[11px] font-bold uppercase tracking-[0.4px] flex-shrink-0 ${colorCfg.bg} ${colorCfg.text}`}>
          <Icon size={11} />
          {cfg.label}
        </span>
      </div>

      <div className="mx-4 border-t border-border-subtle" />

      {/* Rule checks. Personal/demo cards show the personal rules — never the prop
          chips: firm_max_loss_eod is 0 there (sentinel = no trailing EOD rule), and
          trailing MLL / consistency / contract cap don't apply. Old INFO rows
          (pre-verdict evaluations) still show no chips. */}
      {ev.verdict !== 'INFO' && (isPersonal(ev) ? (
        <div className="px-4 py-2.5 space-y-2">
          {ev.personal_max_drawdown_from_peak_pct != null && (
            <EvalRow
              label="Drawdown from peak"
              pass={ev.drawdown_pass}
              value={`≤ ${ev.personal_max_drawdown_from_peak_pct}% from equity peak`}
            />
          )}
          {ev.personal_daily_loss_cap != null && ev.personal_max_consecutive_loss_days != null && (
            <EvalRow
              label="Consecutive capped days"
              pass={personalStreakPass(ev)}
              value={`< ${ev.personal_max_consecutive_loss_days} days in a row at −$${ev.personal_daily_loss_cap.toLocaleString()}`}
            />
          )}
        </div>
      ) : (
        <div className="px-4 py-2.5 space-y-2">
          <EvalRow
            label="Daily drawdown"
            pass={ev.drawdown_pass}
            value={`≤ $${ev.firm_max_loss_eod.toLocaleString()} loss / day`}
          />
          {ev.firm_profit_target > 0 && (
            <EvalRow
              label="Profit target"
              pass={ev.target_pass}
              value={`$${ev.firm_profit_target.toLocaleString()} required`}
            />
          )}
          {ev.consistency_pass != null && ev.firm_consistency_pct != null && (
            <EvalRow
              label="Consistency"
              pass={ev.consistency_pass}
              value={`No day > ${ev.firm_consistency_pct}% of total P&L`}
              extra={ev.largest_day_share_pct != null
                ? `actual: ${ev.largest_day_share_pct.toFixed(1)}%`
                : undefined}
            />
          )}
        </div>
      ))}

      {/* Footer — standout trade count (replaces the redundant net-P&L / drawdown notes) */}
      {tradeCount != null && (
        <div className="mt-auto flex items-baseline gap-2.5 px-4 py-3 bg-accent/5 border-t border-accent/20">
          <span className="text-[40px] font-extrabold font-mono leading-none text-accent tabular-nums">{tradeCount}</span>
          <span className="text-[12px] font-bold uppercase tracking-[0.8px] text-text-secondary">Trades</span>
        </div>
      )}
    </div>
  )
}

// Placeholder for the Evaluation column when the run is an optimizer parameter set that has never
// been fully backtested (no equity curve / trade-level data / firm verdicts yet). Keeps the same
// two-column layout as a full backtest, but instead of a verdict it prompts a full backtest. Mirrors
// EvalCard's shell (header + body + trade-count footer) so it matches height and feel.
function UnscoredEvalCard({ tradeCount, onRunFullBacktest, busy }: { tradeCount?: number | null; onRunFullBacktest: () => void; busy?: boolean }) {
  return (
    <div className="bg-bg-surface border border-border-subtle border-l-[3px] border-l-border-default rounded-lg overflow-hidden h-full flex flex-col">
      {/* Header */}
      <div className="px-4 pt-3.5 pb-2.5 flex items-start justify-between gap-3">
        <div className="text-[13px] font-semibold text-text-primary leading-tight">Not yet scored</div>
        <span className="inline-flex items-center gap-[5px] px-3 py-[5px] rounded-full text-[11px] font-bold uppercase tracking-[0.4px] flex-shrink-0 bg-bg-sunken text-text-tertiary">
          <Info size={11} />
          UNSCORED
        </span>
      </div>

      <div className="mx-4 border-t border-border-subtle" />

      {/* Body — explain why it's unscored + CTA */}
      <div className="px-4 py-3 space-y-3">
        <p className="text-[12px] text-text-secondary leading-relaxed">
          This is an optimizer parameter set. Run a full backtest to get the equity curve, trade-level
          data, and firm evaluations.
        </p>
        <button
          onClick={onRunFullBacktest}
          disabled={busy}
          className="flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded border border-accent/30 bg-accent/5 text-accent hover:bg-accent/10 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
          Run Full Backtest
        </button>
      </div>

      {/* Footer — same trade-count standout as EvalCard */}
      {tradeCount != null && (
        <div className="mt-auto flex items-baseline gap-2.5 px-4 py-3 bg-accent/5 border-t border-accent/20">
          <span className="text-[40px] font-extrabold font-mono leading-none text-accent tabular-nums">{tradeCount}</span>
          <span className="text-[12px] font-bold uppercase tracking-[0.8px] text-text-secondary">Trades</span>
        </div>
      )}
    </div>
  )
}

function EvalRow({
  label, pass, value, extra,
}: { label: string; pass: boolean; value: string; extra?: string }) {
  return (
    <div className="flex items-start gap-[10px] text-[12px]">
      {pass
        ? <CheckCircle size={13} className="text-pos-text flex-shrink-0 mt-[1px]" />
        : <XCircle    size={13} className="text-neg-text flex-shrink-0 mt-[1px]" />
      }
      <div className="flex-1 min-w-0">
        <span className="text-text-tertiary">{label} — </span>
        <span className={pass ? 'text-text-primary' : 'text-neg-text'}>{value}</span>
        {extra && <span className="text-text-tertiary ml-2">({extra})</span>}
      </div>
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
  const valid = !!start && !!end && start < end
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
          <PeriodPicker start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e) }} />
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

type NewsKpis = { net: number; winRate: number; pf: number; maxDd: number; trades: number }

function newsKpisFrom(trades: EquityPoint[]): NewsKpis {
  const pnls = trades.map(t => t.profit ?? 0)
  const wins = pnls.filter(p => p > 0)
  const grossWin  = wins.reduce((a, b) => a + b, 0)
  const grossLoss = Math.abs(pnls.filter(p => p < 0).reduce((a, b) => a + b, 0))
  let cum = 0, peak = 0, maxDd = 0
  for (const p of pnls) { cum += p; peak = Math.max(peak, cum); maxDd = Math.max(maxDd, peak - cum) }
  return {
    net: pnls.reduce((a, b) => a + b, 0),
    winRate: trades.length ? wins.length / trades.length : 0,
    pf: grossLoss > 0 ? grossWin / grossLoss : (grossWin || 0),
    maxDd,
    trades: trades.length,
  }
}

function NewsDelta({ from, to, kind, goodWhen = 'higher' }: {
  from: number; to: number; kind: 'money' | 'pct' | 'pf' | 'num'; goodWhen?: 'higher' | 'lower'
}) {
  const d = to - from
  if (Math.abs(d) < (kind === 'pf' ? 5e-3 : 1e-9)) return <span className="text-text-tertiary">·</span>
  const good = goodWhen === 'higher' ? d > 0 : d < 0
  const cls = good ? 'text-pos-text' : 'text-neg-text'
  const sign = d >= 0 ? '+' : ''
  const body = kind === 'money' ? dollar(d, true)
    : kind === 'pct' ? `${sign}${(d * 100).toFixed(1)}%`
    : kind === 'pf' ? `${sign}${d.toFixed(2)}`
    : `${sign}${d}`
  return <span className={`tabular-nums ${cls}`}>{body}</span>
}

function NewsMiniKpi({ label, value, from, to, kind, goodWhen }: {
  label: string; value: React.ReactNode; from: number; to: number
  kind: 'money' | 'pct' | 'pf' | 'num'; goodWhen?: 'higher' | 'lower'
}) {
  return (
    <div className="rounded-md border border-border-subtle bg-bg-sunken px-3 py-2 min-w-0">
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className="text-[15px] font-semibold tabular-nums text-text-primary truncate">{value}</div>
      <div className="text-[11px] mt-0.5"><NewsDelta from={from} to={to} kind={kind} goodWhen={goodWhen} /></div>
    </div>
  )
}

function NewsFilterCard({ run, avoidNews }: { run: Run; avoidNews: boolean }) {
  // null = follow the strategy's own default (avoidNews); once the user clicks, their choice sticks.
  const [removeNewsChoice, setRemoveNewsChoice] = useState<boolean | null>(null)
  const removeNews = removeNewsChoice ?? avoidNews
  const [pre, setPre]   = useState(15)                 // block window before an event (minutes)
  const [post, setPost] = useState(30)                 // block window after an event (minutes)
  const enabled = run.equity_curve.length > 0
  const { data: report, isLoading } = useRunNews(run.run_id, pre, post, enabled)

  // Raw trades = curve points carrying a per-trade P&L (a leading balance anchor, if any, has none).
  const rawTrades = useMemo(
    () => run.equity_curve.filter(p => p.profit != null || p.direction),
    [run.equity_curve],
  )

  // Apply the filter: holidays always out, news out only when toggled. Rebuild the cumulative
  // equity for the filtered chart. One pass, keyed on the tags + the toggle.
  const view = useMemo(() => {
    const tag = new Map<number, NewsTradeTag>()
    for (const t of report?.trades ?? []) if (t.index != null) tag.set(t.index, t)
    const kept: EquityPoint[] = []
    let holidayCount = 0, newsCount = 0
    for (const p of rawTrades) {
      const tg = tag.get(p.index)
      if (tg?.in_holiday) { holidayCount++; continue }              // always removed
      if (tg?.in_news)   { newsCount++; if (removeNews) continue }  // removed only when toggled on
      kept.push(p)
    }
    let cum = 0
    const curve = kept.map((p, i) => ({ ...p, index: i + 1, equity: (cum += (p.profit ?? 0)) }))
    return { kept, curve, holidayCount, newsCount }
  }, [rawTrades, report, removeNews])

  const baseline = useMemo(() => newsKpisFrom(rawTrades), [rawTrades])   // raw backtest (everything in)
  const filtered = useMemo(() => newsKpisFrom(view.kept), [view.kept])   // after the filter

  if (!enabled) return null

  const hasEntryTimes = rawTrades.some(p => p.entry_ms != null)
  const noData    = !isLoading && report && !report.has_data
  const oldRun    = !isLoading && report && report.has_data && !hasEntryTimes
  const nothingHit = !isLoading && report && report.has_data && hasEntryTimes
                     && view.holidayCount === 0 && view.newsCount === 0

  return (
    <div className="space-y-3">
      <SectionLabel>News &amp; Holiday Filter</SectionLabel>
      <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 min-w-0">
            <Newspaper size={15} className="text-accent shrink-0" />
            <span className="text-[13px] font-medium text-text-primary">
              Remove trades around high-impact news
            </span>
          </div>
          {/* News-window toggle. Holidays are not on this toggle — always excluded. */}
          {report?.has_data && hasEntryTimes && (
            <div className="inline-flex rounded-md border border-border-subtle overflow-hidden shrink-0">
              {(['Included', 'Removed'] as const).map(opt => {
                const active = (opt === 'Removed') === removeNews
                return (
                  <button key={opt} onClick={() => setRemoveNewsChoice(opt === 'Removed')}
                    className={`px-3 py-1.5 text-[12px] font-medium transition-colors ${
                      active ? 'bg-accent text-bg-base' : 'bg-bg-sunken text-text-secondary hover:text-text-primary'}`}>
                    News {opt}
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {isLoading && <div className="text-[12px] text-text-tertiary">Checking the calendar…</div>}

        {noData && (
          <div className="flex items-start gap-2 text-[12px] text-text-secondary">
            <Info size={14} className="text-text-tertiary mt-0.5 shrink-0" />
            <span>No news data cached for this period yet. Run <code className="text-text-primary">engines/news/tools/backfill.py</code> for these months to turn the filter on. Until then the backtest is shown unfiltered.</span>
          </div>
        )}

        {oldRun && (
          <div className="flex items-start gap-2 text-[12px] text-text-secondary">
            <Info size={14} className="text-warn-text mt-0.5 shrink-0" />
            <span>This run was made before trade times were recorded. Hit <span className="text-text-primary font-medium">Reload charts</span> (or rerun it) to record each trade's time and enable the filter.</span>
          </div>
        )}

        {report?.has_data && hasEntryTimes && (
          <>
            {/* Window sliders — drag to change how long before/after a release to block; re-tags live. */}
            <div className="flex items-center gap-x-6 gap-y-2 flex-wrap">
              <label className="flex items-center gap-2 text-[12px] text-text-secondary">
                <span className="w-20 shrink-0">Before news</span>
                <input type="range" min={0} max={120} step={5} value={pre}
                  onChange={e => setPre(Number(e.target.value))}
                  className="w-40 accent-accent cursor-pointer" />
                <span className="w-10 tabular-nums text-text-primary font-medium">{pre}m</span>
              </label>
              <label className="flex items-center gap-2 text-[12px] text-text-secondary">
                <span className="w-20 shrink-0">After news</span>
                <input type="range" min={0} max={120} step={5} value={post}
                  onChange={e => setPost(Number(e.target.value))}
                  className="w-40 accent-accent cursor-pointer" />
                <span className="w-10 tabular-nums text-text-primary font-medium">{post}m</span>
              </label>
            </div>
            {nothingHit ? (
              <div className="text-[12px] text-text-tertiary">No news releases or bank holidays landed on any trade in this window.</div>
            ) : (
              <>
              <div className="flex items-center gap-4 text-[12px] text-text-secondary flex-wrap">
                <span>
                  <span className="text-neg-text font-medium tabular-nums">{view.holidayCount}</span> bank-holiday {view.holidayCount === 1 ? 'trade' : 'trades'} always excluded
                </span>
                <span className="text-text-tertiary">·</span>
                <span>
                  <span className="text-gold-text font-medium tabular-nums">{view.newsCount}</span> news-window {view.newsCount === 1 ? 'trade' : 'trades'} {removeNews ? 'removed' : 'kept'}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
                <NewsMiniKpi label="Net P&L" value={<FitMoney n={filtered.net} signed />}
                  from={baseline.net} to={filtered.net} kind="money" />
                <NewsMiniKpi label="Win Rate" value={pct(filtered.winRate)}
                  from={baseline.winRate} to={filtered.winRate} kind="pct" />
                <NewsMiniKpi label="Profit Factor" value={filtered.pf.toFixed(2)}
                  from={baseline.pf} to={filtered.pf} kind="pf" />
                <NewsMiniKpi label="Max DD" value={dollar(filtered.maxDd)}
                  from={baseline.maxDd} to={filtered.maxDd} kind="money" goodWhen="lower" />
                <NewsMiniKpi label="Trades" value={filtered.trades}
                  from={baseline.trades} to={filtered.trades} kind="num" />
              </div>
              {view.curve.length > 0 && (
                <div>
                  <div className="text-[11px] text-text-tertiary mb-1">
                    Filtered equity curve {removeNews ? '(news + holidays removed)' : '(holidays removed)'}
                  </div>
                  <EquityCurveChart data={view.curve} height={200} />
                </div>
              )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function BacktestDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate     = useNavigate()
  const { data: run, isLoading } = useBacktestRun(runId ?? null)
  // A tuning iteration is a standalone run derived from a baseline (source_run_id set,
  // not a sweep/optimization child). Fetch its baseline to wire up breadcrumbs.
  const isTuneIteration = !!run?.source_run_id && !run?.optimization_id && !run?.sweep_id
  const { data: tuneBaseline } = useBacktestRun(isTuneIteration ? run!.source_run_id : null)
  const { data: strategy } = useStrategy(run?.strategy_id ?? null)
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
  const hasExcursionData = useMemo(
    () => run?.equity_curve.some(p => p.favorable != null || p.adverse != null) ?? false,
    [run?.equity_curve],
  )
  // Primary chart tab (the big charts) + secondary tab (supporting charts). Price lazy-loads.
  const [primaryTab, setPrimaryTab] = useState<'equity' | 'sized' | 'price' | 'breakdown'>('equity')
  const [fullscreenChart, setFullscreenChart] = useState<string | null>(null)
  const [showMoreKpis, setShowMoreKpis] = useState(false)
  // Shared eval-card / KPI-grid height: short when collapsed, taller when More metrics is open so
  // both grow together and the two KPI rows get enough room (no crop) while staying the same height.
  const kpiRowH = showMoreKpis ? KPI_ROW_H_EXPANDED : KPI_ROW_H
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

  // The firm whose evaluation card is currently shown.
  const selectedEval = (run && run.evaluations.length)
    ? run.evaluations[Math.min(selectedEvalIdx, run.evaluations.length - 1)]
    : null

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

  const fallback = useMemo(
    () => computeFallbacks(effRun?.daily_pnl ?? []),
    [effRun?.daily_pnl],
  )

  const hasRealRegimeTags = useMemo(
    () => run?.daily_pnl.some(d => d.regime_tag && d.regime_tag !== 'UNKNOWN') ?? false,
    [run?.daily_pnl],
  )

  const regimeBands = useMemo(
    () => (overlayOn && hasRealRegimeTags && run)
      ? computeRegimeBands(run.equity_curve, run.daily_pnl)
      : [],
    [overlayOn, hasRealRegimeTags, run?.equity_curve, run?.daily_pnl],
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

  // The eval card and KPI grid share ONE fixed height on lg so paging through evaluations never
  // grows or shrinks the row. Was JS-measured off the eval card, but each verdict has a different
  // number of rule lines (PASS = 1, DISCARD = 2–3), so the grid stretched/squished per verdict.
  // Fixed height sized to fit the tallest verdict; shorter verdicts just leave headroom.
  const [isLg, setIsLg] = useState(() => window.matchMedia('(min-width: 1024px)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)')
    const on = () => setIsLg(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])

  const progressMatches = progress?.job_id === run?.run_id
  const runPct       = isRunning ? (progressMatches ? (progress?.pct ?? 0) : 0) : 0
  const runMessage   = isRunning ? (progressMatches ? (progress?.message ?? 'Starting…') : 'Starting…') : ''
  const runStartedAt = isRunning ? (progressMatches ? (progress?.started_at ?? null) : null) : null

  const backLabel = isTuneIteration ? 'Tuning workbench'
    : run?.optimization_id ? 'Optimization'
    : run?.sweep_id ? 'Sweep'
    : 'Backtests'
  const backPath  = isTuneIteration ? `/backtests/runs/${run!.source_run_id}/tune`
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
                    title="Tweak parameters and compare iterations"
                  >
                    <SlidersHorizontal size={14} /> Tune
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
          {/* ── Evaluations + Performance (side by side) ──────────────────── */}
          {isComplete && (
            // Two-column Evaluation + Performance for real backtests AND optimizer combos. A combo
            // has no firm verdicts yet, so its Evaluation column is an UnscoredEvalCard prompting a
            // full backtest — same layout, just unscored. Only a plain run with no evaluations and
            // no combo origin falls through to the full-width Performance-only layout.
            run.evaluations.length > 0 || isOptCombo ? (
              <div className="space-y-3">
                <div className="grid gap-6 lg:grid-cols-[minmax(280px,360px)_1fr] items-start">
                  {/* Left: ONE firm evaluation card — height measured so the KPI grid can match it.
                      Multi-firm runs switch via the compact counter on the header line (no growth). */}
                  <div className="flex flex-col">
                    <div className="flex items-center justify-between mb-3">
                      <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px]">Evaluation</h2>
                      {/* Firm switching now lives on the header ruleset chip (always visible, even
                          scrolled) — no second switcher here. */}
                    </div>
                    <div className="flex flex-col gap-3" style={isLg ? { height: kpiRowH, transition: 'height 0.3s ease' } : undefined}>
                      {isOptCombo ? (
                        <UnscoredEvalCard
                          tradeCount={run.trade_count}
                          onRunFullBacktest={runFullBacktest}
                          busy={retryBacktest.isPending || jobBusy}
                        />
                      ) : (() => {
                        // One firm at a time. Clamp the index in case the eval list shrank.
                        const idx = Math.min(selectedEvalIdx, run.evaluations.length - 1)
                        const ev = run.evaluations[idx]
                        return (
                          <EvalCard key={ev.eval_id} ev={ev} netPnl={ev.net_pnl ?? run.net_pnl}
                            tradeCount={ev.trade_count ?? run.trade_count} showName={run.evaluations.length > 1} />
                        )
                      })()}
                    </div>
                  </div>
                  {/* Right: flat KPIs pinned to the eval card's measured pixel height. */}
                  <div className="flex flex-col min-w-0">
                    <SectionLabel>Performance</SectionLabel>
                    <KpiGrid run={effRun!} fallback={fallback} equity={effRun!.equity_curve}
                      balance={balance} showMore={showMoreKpis} fixedHeight={isLg ? kpiRowH : null} />
                  </div>
                </div>
                {/* "More metrics" below the cards (left-aligned) — outside the grid so it doesn't
                    eat into the height that's matched to the eval card. */}
                <MoreMetricsToggle open={showMoreKpis} onToggle={() => setShowMoreKpis(s => !s)} count={6} />
              </div>
            ) : (
              <div className="space-y-3">
                <div>
                  <SectionLabel>Performance</SectionLabel>
                  {run.trade_count != null && <div className="mb-3"><TradeCountStandout count={run.trade_count} /></div>}
                  <KpiGrid run={effRun!} fallback={fallback} equity={effRun!.equity_curve}
                    balance={balance} showMore={showMoreKpis} />
                </div>
                <MoreMetricsToggle open={showMoreKpis} onToggle={() => setShowMoreKpis(s => !s)} count={6} />
              </div>
            )
          )}

          {/* ── News & holiday filter (post-run view) ─────────────────────── */}
          {isComplete && !isOptCombo && run.equity_curve.length > 0 && (
            <NewsFilterCard run={run} avoidNews={strategy?.avoid_news ?? false} />
          )}

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
            const renderChart = (key: string, h: number, isModal = false): React.ReactNode => {
              switch (key) {
                case 'equity':
                  return (
                    <>
                      <EquityCurveChart
                        data={run.equity_curve}
                        bands={regimeBands}
                        showHistogram={histOn}
                        showRunupDrawdown={rudOn}
                        height={h}
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
                        {primaryTab === 'equity' && (
                          <SeriesToggle label={hasExcursionData ? 'Trade excursions' : 'Histogram'} on={histOn} onChange={toggleHist} />
                        )}
                        {primaryTab === 'equity' && (
                          <SeriesToggle label="Run-ups & drawdowns" on={rudOn} onChange={toggleRud} />
                        )}
                        {(primaryTab === 'equity' || primaryTab === 'sized') && hasRealRegimeTags && (
                          <RegimeOverlayToggle on={overlayOn} onChange={handleOverlayToggle} />
                        )}
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
