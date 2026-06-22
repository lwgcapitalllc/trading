import { Fragment, Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, ChevronDown, ChevronUp, ChevronLeft, ChevronRight, AlertTriangle,
  CheckCircle, XCircle, Minus, Info, Square, RefreshCw, RotateCcw, Activity, Layers, Play,
  Copy, Check, SlidersHorizontal, X,
} from 'lucide-react'
import {
  AreaChart, Area, ComposedChart, Line, BarChart, Bar, PieChart, Pie, Label,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine, ReferenceArea, ReferenceDot,
} from 'recharts'
import { useBacktestRun, useRunLog, useLabProgress, useStopBacktest, useReloadCharts, useRetryBacktest, useRunningVpsJob, useStrategy, useRulesets, useChartSpec, useRefreshChartSpec } from '@/hooks/useLab'
import { useStressTests, useRunStressTest, useRunningStressLock } from '@/hooks/useStressTests'
import type { BacktestDetail as Run, EvaluationDetail, EquityPoint, DailyPnlPoint, ParamSchemaEntry, SizedTimelineDay } from '@/types'
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

// Renders a dollar amount at full precision when it fits its cell, abbreviating to $3.2k only when
// the full string would overflow (the big KPI numbers crop in a narrow card). A hidden full-width
// copy is measured against the cell, so it switches back to full whenever space returns — e.g. when
// the grid expands and the value font shrinks. Observes both the cell and the copy to catch either.
function FitMoney({ n, signed = false }: { n: number | null | undefined; signed?: boolean }) {
  const wrapRef = useRef<HTMLSpanElement>(null)
  const fullRef = useRef<HTMLSpanElement>(null)
  const [short, setShort] = useState(false)
  const full = dollar(n, signed)
  const abbr = dollarShort(n, signed)
  useEffect(() => {
    const wrap = wrapRef.current, fullEl = fullRef.current
    if (!wrap || !fullEl) return
    const measure = () => setShort(fullEl.offsetWidth > wrap.offsetWidth + 1)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(wrap)
    ro.observe(fullEl)
    return () => ro.disconnect()
  }, [full])
  if (n == null) return <span>—</span>
  return (
    <span ref={wrapRef} className="block relative whitespace-nowrap">
      <span ref={fullRef} aria-hidden className="invisible absolute left-0 top-0 whitespace-nowrap pointer-events-none">{full}</span>
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

// ── InfoTip ───────────────────────────────────────────────────────────────────

// Tooltip is portalled to <body> with fixed positioning so the KPI card's overflow-hidden
// (needed for the collapse/height clipping) can't crop it.
function InfoTip({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const [tip, setTip] = useState<{ top: number; left: number } | null>(null)
  const show = () => {
    const r = ref.current?.getBoundingClientRect()
    if (r) setTip({ top: r.top - 8, left: r.left })
  }
  return (
    <span
      ref={ref}
      onMouseEnter={show}
      onMouseLeave={() => setTip(null)}
      className="relative inline-flex items-center ml-[5px] cursor-help flex-shrink-0"
    >
      <Info size={9} className="text-text-tertiary/50 hover:text-accent transition-colors" />
      {tip && createPortal(
        <span
          style={{ position: 'fixed', top: tip.top, left: tip.left, transform: 'translateY(-100%)' }}
          className="z-[100] w-48 rounded-lg bg-bg-base border border-border-default px-3 py-2.5 text-[11px] text-text-secondary shadow-2xl pointer-events-none leading-relaxed normal-case tracking-normal font-normal"
        >
          {text}
        </span>,
        document.body,
      )}
    </span>
  )
}

// ── KPI grid ──────────────────────────────────────────────────────────────────

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
      tooltip: "Return per unit of risk, annualized (daily P&L × √252) — the canonical definition shared with the optimizer and walk-forward. 'platform' shows NT8/MT5's own reported Sharpe for reference. Good ≥1.0, strong ≥2.0. Negative means the strategy loses more than doing nothing. 'low sample' flags fewer than 10 trading days, where the value is statistically noisy." },
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
      className={`flex flex-col justify-center bg-bg-surface border border-border-subtle border-l-[3px] ${KPI_TONE_BORDER[m.tone ?? kpiTone(m.valueCls)]} rounded-xl px-4 py-3 overflow-hidden transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/30 ${fixedCard ? 'h-full min-h-[100px]' : 'min-h-[100px]'}`}
    >
      <div className="flex items-center text-[9px] font-bold uppercase tracking-[0.8px] text-text-tertiary">
        {m.label}{m.tooltip && <InfoTip text={m.tooltip} />}
      </div>
      <div className={`${valSize} font-bold tracking-[-0.6px] font-mono leading-none mt-2 transition-[font-size] duration-300 ${m.valueCls ?? ''}`}>{m.value}</div>
      <div className="text-[10px] text-text-tertiary mt-1.5 leading-snug min-h-[14px]">{m.sub}</div>
    </div>
  )

  // On lg the grid is pinned to the eval card's measured pixel height (fixedHeight). Two row-grids
  // with explicit heights: collapsed → core row = full height; expanded → both rows at half height
  // summing (with the gap) to exactly the same total. Heights animate. Off lg → normal flow.
  const fh = fixedHeight
  if (fh != null) {
    const gap = 12
    const half = Math.max(0, (fh - gap) / 2)
    return (
      <div className="flex flex-col" style={{ height: fh, overflow: 'hidden' }}>
        <div
          className="grid grid-cols-6 gap-x-3 shrink-0"
          style={{ height: showMore ? half : fh, gridTemplateRows: '1fr', transition: 'height 0.3s ease' }}
        >
          {core.map(m => card(m, true, showMore ? 'text-[26px]' : 'text-[38px]'))}
        </div>
        <div
          className="grid grid-cols-6 gap-x-3 shrink-0 overflow-hidden"
          style={{ height: showMore ? half : 0, marginTop: showMore ? gap : 0, gridTemplateRows: '1fr', transition: 'height 0.3s ease, margin-top 0.3s ease' }}
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

interface RegimeBand { x1: number; x2: number; regime: string }

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

// ── Equity curve ──────────────────────────────────────────────────────────────

function fmtChartDate(d?: string): string {
  if (!d) return ''
  const dt = new Date(d.slice(0, 10) + 'T12:00:00')
  const yr = String(dt.getFullYear()).slice(-2)
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ` '${yr}`
}

function EquityCurveChart({ data, bands = [], height = 300 }: { data: EquityPoint[]; bands?: RegimeBand[]; height?: number }) {
  if (!data.length) return null

  const startEq    = data[0]?.equity ?? 0
  const endEq      = data[data.length - 1]?.equity ?? 0
  const profitable = endEq >= startEq
  const allValues  = data.map(d => d.equity)
  const min = Math.min(...allValues)
  const max = Math.max(...allValues)
  const pad = (max - min) * 0.1 || 500
  const yMin = Math.min(startEq, min) - pad
  const yMax = max + pad

  const curveColor = profitable ? C.pos : C.neg
  const eqTicks    = calIndexTicks(data)

  return (
    <ResponsiveContainer key={bands.length ? 'regime' : 'base'} width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <defs>
          <linearGradient id="eqPos" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor={C.pos} stopOpacity={0.22} />
            <stop offset="95%" stopColor={C.pos} stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="eqNeg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor={C.neg} stopOpacity={0.05} />
            <stop offset="95%" stopColor={C.neg} stopOpacity={0.22} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
        {/* Regime context as faint background bands — same treatment as the tune page. */}
        {bands.map((b, i) => (
          <ReferenceArea key={i} x1={b.x1} x2={b.x2} fill={REGIME_COLORS[b.regime] ?? REGIME_COLORS.UNKNOWN} fillOpacity={0.1} stroke="none" />
        ))}
        <XAxis
          dataKey="index"
          ticks={eqTicks}
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
          tick={{ fill: C.axisTick, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => v === 0 ? '$0' : `${v >= 0 ? '+' : ''}$${(v / 1000).toFixed(0)}k`}
          width={56}
        />
        {/* Custom tooltip: always shows the 'equity' entry, ignores _sN segment keys */}
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null
            const eq = payload.find((p: { dataKey?: string | number }) => p.dataKey === 'equity') ?? payload[0]
            if (!eq) return null
            const pt = (eq as { payload?: EquityPoint }).payload
            const v  = ((eq as { value?: number }).value ?? 0)
            const dateStr = pt?.date ? ` · ${fmtChartDate(pt.date)}` : ''
            return (
              <div style={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}>
                <p style={{ color: C.axisTick, marginBottom: 4 }}>Trade #{pt?.index}{dateStr}</p>
                <p style={{ color: '#e5e7eb' }}>
                  {pt?.direction ? `Equity (${pt.direction})` : 'Equity'}&nbsp;
                  {v >= 0 ? '+' : ''}${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </p>
              </div>
            )
          }}
        />
        <ReferenceLine y={startEq} stroke={C.refLine} strokeDasharray="4 4" />
        {startEq !== 0 && <ReferenceLine y={0} stroke={C.refLineDim} />}
        <Area
          type="monotone"
          dataKey="equity"
          stroke={curveColor}
          strokeWidth={1.5}
          fill={profitable ? 'url(#eqPos)' : 'url(#eqNeg)'}
          dot={false}
          activeDot={{ r: 4, fill: curveColor, stroke: 'transparent' }}
          baseValue={startEq}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ── Sized equity curve (dynamic-sizing engine) ───────────────────────────────
// Day-by-day from the engine's timeline: end-of-day balance vs the trailing risk
// floor (the firm's max-loss line). The gap between them is the buffer the engine
// sized against; balance crossing the floor is a breach. Unlike the per-trade
// equity curve above, this is the REAL sized account — what actually traded.

function SizedEquityCurveChart({ data, height = 300 }: {
  data: SizedTimelineDay[]; height?: number
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
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <defs>
          <linearGradient id="sizedFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor={lineColor} stopOpacity={0.18} />
            <stop offset="95%" stopColor={lineColor} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
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
          tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
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
          isAnimationActive={false}
        />
        <Line
          type="stepAfter"
          dataKey="floor"
          stroke={C.neg}
          strokeWidth={1.25}
          strokeDasharray="5 4"
          dot={false}
          connectNulls
          isAnimationActive={false}
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

function SizedCurveLegend({ mode }: { mode: 'consistent' | 'bullet' }) {
  return (
    <div className="flex items-center gap-4 mt-2 text-[11px] text-text-tertiary">
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-3 h-[2px] rounded-full" style={{ background: C.pos }} />
        End-of-day balance
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block w-3 border-t-2 border-dashed" style={{ borderColor: C.neg }} />
        Trailing risk floor (breach = fail)
      </span>
      <span className="ml-auto font-medium text-text-secondary">
        Engine-sized · {mode === 'bullet' ? 'Bullet' : 'Consistent'}
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

// Firm switcher — shown only when a run is scored against 2+ rulesets. A compact "1/N" counter
// with prev/next arrows that lives ON the Evaluation header line, so switching firms never grows
// the card or KPI height (one verdict shows at a time; the firm name is inside the card).
function EvalSwitcher({ count, selected, onSelect }: {
  count: number; selected: number; onSelect: (i: number) => void
}) {
  const btn = "p-0.5 rounded text-text-tertiary hover:text-text-primary hover:bg-bg-surface transition-colors"
  return (
    <div className="flex items-center gap-1">
      <button className={btn} aria-label="Previous firm"
        onClick={() => onSelect((selected - 1 + count) % count)}>
        <ChevronLeft size={14} />
      </button>
      <span className="text-[11px] font-mono tabular-nums text-text-secondary">{selected + 1}/{count}</span>
      <button className={btn} aria-label="Next firm"
        onClick={() => onSelect((selected + 1) % count)}>
        <ChevronRight size={14} />
      </button>
    </div>
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
  if (status === 'failed_timeout') {
    return runner === 'mt5'
      ? 'The MT5 agent stopped responding mid-run. Check the MT5 agent log on the VPS, then re-run.'
      : 'The NT8 agent stopped responding mid-run. Verify NT8 is running and the Strategy Analyzer is open in the RDP session, then re-run.'
  }
  return runner === 'mt5'
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

  // When fullscreen: body clientHeight minus py-4 padding (32px), the ChartPanel
  // header row (~36px including mb-2), and a small buffer. Without subtracting the
  // header the chart overflows and overflow-hidden clips the klinecharts x-axis.
  const effectiveH = isFullscreen
    ? (fsBodyH > 0 ? Math.max(200, fsBodyH - 80) : Math.max(200, window.innerHeight - 140))
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
          <ChartPanel spec={spec} height={effectiveH} />
        </Suspense>
      </>
    )

  return (
    <div className={isFullscreen ? 'fixed inset-0 z-[90] bg-bg-base flex flex-col' : ''}>
      {isFullscreen && (
        <div className="flex items-center justify-between px-5 py-3 border-b border-border-subtle flex-shrink-0">
          <span className="text-[12px] font-semibold uppercase tracking-[0.7px] text-text-secondary">Price</span>
          <button onClick={onFullscreenClose} title="Close (Esc)" className="text-text-tertiary hover:text-text-primary">
            <X size={18} />
          </button>
        </div>
      )}
      <div ref={fsBodyRef} className={isFullscreen ? 'flex-1 min-h-0 overflow-hidden px-5 py-4' : ''}>
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
  const isMt5 = run.runner === 'mt5'
  // Forex (MT5) runs evaluate against forex rulesets; futures (NT8) against the prop/futures rows.
  const options = useMemo(
    () => rulesets.filter(r => (isMt5 ? r.market === 'forex' : r.market !== 'forex')),
    [rulesets, isMt5],
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
            This optimizer parameter set has no ruleset attached. Pick which {isMt5 ? 'forex' : 'futures'} ruleset(s)
            to score it against.
          </p>
        </div>

        {options.length === 0 ? (
          <p className="text-xs text-text-tertiary">No {isMt5 ? 'forex' : 'futures'} rulesets available.</p>
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
  const [overlayOn, setOverlayOn] = useState(getOverlayPref)
  const handleOverlayToggle = useCallback((v: boolean) => { setOverlayOn(v); setOverlayPref(v) }, [])
  // Primary chart tab (the big charts) + secondary tab (supporting charts). Price lazy-loads.
  const [primaryTab, setPrimaryTab] = useState<'equity' | 'sized' | 'price' | 'breakdown'>('equity')
  const [fullscreenChart, setFullscreenChart] = useState<string | null>(null)
  const [showMoreKpis, setShowMoreKpis] = useState(false)
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

  const fallback = useMemo(
    () => computeFallbacks(run?.daily_pnl ?? []),
    [run?.daily_pnl],
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

  const isRunning  = run?.status === 'running'
  const isFailed   = run?.status.startsWith('failed') ?? false
  const isComplete    = run?.status === 'complete'
  const isMt5         = run?.runner === 'mt5'
  // Optimization combo run: exists in the grid export but has never been fully backtested
  const isOptCombo    = !!run?.optimization_id && !run?.equity_curve?.length && isComplete
  const stressBlocked = isMt5 ? (stressLock?.forex ?? false) : (stressLock?.futures ?? false)
  const jobBusy       = isMt5 ? !!runningJob?.mt5?.running : !!runningJob?.nt8?.running

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

  // Match the KPI grid height to the eval card (lg only). The eval card's height is measured in JS
  // and passed as fixedHeight so both rows (collapsed: one tall, expanded: two half-height) sum to
  // the same total. Pure-CSS stretch caused a grow-then-shrink reflow on toggle.
  const [evalH, setEvalH] = useState<number | null>(null)
  const [isLg, setIsLg] = useState(() => window.matchMedia('(min-width: 1024px)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)')
    const on = () => setIsLg(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  const evalRoRef = useRef<ResizeObserver | null>(null)
  const measureEvalRef = useCallback((el: HTMLDivElement | null) => {
    evalRoRef.current?.disconnect()
    if (!el) { setEvalH(null); return }
    setEvalH(el.offsetHeight)
    const ro = new ResizeObserver(() => setEvalH(el.offsetHeight))
    ro.observe(el)
    evalRoRef.current = ro
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
            <div className="flex items-start justify-between gap-4">
              {scrolled ? (
                <div className="flex items-center gap-2 min-w-0">
                  <button onClick={() => navigate(backPath)} title={backLabel} className="flex items-center text-text-tertiary hover:text-text-secondary transition-colors flex-shrink-0">
                    <ArrowLeft size={14} />
                  </button>
                  <h1
                    className="text-[15px] font-semibold leading-tight truncate cursor-pointer hover:text-accent transition-colors flex-shrink-0"
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
                    <span className="inline-flex items-center px-1.5 py-[1px] rounded text-[11px] font-semibold font-mono bg-warn-muted border border-warn-text/20 text-warn-text flex-shrink-0 truncate max-[900px]:hidden">
                      {run.evaluations.map(e => e.ruleset_id).join(', ')}
                    </span>
                  )}
                  {run.sized && (
                    <span
                      className="inline-flex items-center px-1.5 py-[1px] rounded text-[11px] font-semibold bg-accent/10 text-accent border border-accent/20 flex-shrink-0 max-[1100px]:hidden"
                      title="Sizing engine set contract size from the ruleset's ladder and room left."
                    >
                      Sized · {run.sizing_mode === 'bullet' ? 'Bullet' : 'Consistent'}
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
                    <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono bg-warn-muted border border-warn-text/20 text-warn-text">
                      {run.evaluations.map(e => e.ruleset_id).join(', ')}
                    </span>
                  )}
                  {run.sized && (
                    <span
                      className="inline-flex items-center gap-1 px-2 py-[3px] rounded text-[11px] font-semibold bg-accent/10 text-accent border border-accent/20"
                      title="The sizing engine set contract size from each ruleset's contract ladder and room left — this run reflects real prop-firm sizing, not unit size."
                    >
                      Engine-sized · {run.sizing_mode === 'bullet' ? 'Bullet' : 'Consistent'}
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
                    onClick={runFullBacktest}
                    disabled={retryBacktest.isPending || jobBusy}
                    className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-bg-hover disabled:opacity-40"
                    title={(isMt5 ? !!runningJob?.mt5?.running : !!runningJob?.nt8?.running) ? `${isMt5 ? 'MT5' : 'NT8'} is busy — wait for the current job to finish` : run.status.startsWith('failed') ? 'Retry this backtest' : run.optimization_id && !run.equity_curve?.length ? 'Run a full backtest on this parameter set to get charts and trade data' : 'Rerun this backtest'}
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
                          : stressBlocked ? `A ${isMt5 ? 'forex' : 'futures'} stress test is already running` : undefined
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
          {isRunning && <RunningBanner pct={runPct} message={runMessage} startedAt={runStartedAt} onStop={() => stopBacktest.mutate(run.run_id)} runId={run.run_id} runner={run.runner ?? 'ninjatrader'} steps={isMt5 ? MT5_RUN_STEPS : NT8_RUN_STEPS} />}
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
                      {!isOptCombo && run.evaluations.length > 1 && (
                        <EvalSwitcher count={run.evaluations.length}
                          selected={Math.min(selectedEvalIdx, run.evaluations.length - 1)}
                          onSelect={setSelectedEvalIdx} />
                      )}
                    </div>
                    <div className="flex flex-col gap-3" ref={measureEvalRef}>
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
                          <EvalCard key={ev.eval_id} ev={ev} netPnl={run.net_pnl}
                            tradeCount={run.trade_count} showName={run.evaluations.length > 1} />
                        )
                      })()}
                    </div>
                  </div>
                  {/* Right: flat KPIs pinned to the eval card's measured pixel height. */}
                  <div className="flex flex-col min-w-0">
                    <SectionLabel>Performance</SectionLabel>
                    <KpiGrid run={run} fallback={fallback} equity={run.equity_curve}
                      balance={balance} showMore={showMoreKpis} fixedHeight={isLg ? evalH : null} />
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
                  <KpiGrid run={run} fallback={fallback} equity={run.equity_curve}
                    balance={balance} showMore={showMoreKpis} />
                </div>
                <MoreMetricsToggle open={showMoreKpis} onToggle={() => setShowMoreKpis(s => !s)} count={6} />
              </div>
            )
          )}

          {/* ── Charts ────────────────────────────────────────────────────── */}
          {isComplete && !isOptCombo && (() => {
            const hasCharts = run.equity_curve.length > 0

            const seenLimits = new Set<number>()
            const evalLimits: Array<{ limit: number; label: string; pass: boolean }> = []
            for (const e of run.evaluations) {
              // Personal/demo have no trailing EOD rule — firm_max_loss_eod is the 0
              // sentinel and must never render as a "$0 limit" reference line.
              if (isPersonal(e)) continue
              if (!seenLimits.has(e.firm_max_loss_eod)) {
                seenLimits.add(e.firm_max_loss_eod)
                const same = run.evaluations.filter(x => x.firm_max_loss_eod === e.firm_max_loss_eod && !isPersonal(x))
                evalLimits.push({ limit: e.firm_max_loss_eod, label: e.ruleset_name, pass: same.every(x => x.drawdown_pass) })
              }
            }

            const SUBS: Record<string, string> = {
              equity: 'Steadily rising = good. Big peak then long decline = giving back gains.',
              sized: 'The real sized account: end-of-day balance vs the trailing risk floor. Gap = buffer; crossing = breach.',
              price: 'Candlesticks with trade context.',
              breakdown: 'Drawdown, daily P&L, and long vs short — the supporting detail.',
            }
            const TITLES: Record<string, string> = {
              equity: 'Equity curve', sized: 'Sized equity', price: 'Price', breakdown: 'Breakdown',
            }
            const hasDirection = run.equity_curve.some(p => p.direction)
            // The Sized tab appears only for engine-sized runs (a reshaped strategy emitted
            // engine_trades → the engine produced a day-by-day timeline). Inert for every unit-size run.
            const hasSized = run.sized && run.sized_timeline.length > 0
            const primaryTabs: ReadonlyArray<readonly [string, string]> = [
              ['equity', 'Equity'],
              ...(hasSized ? [['sized', 'Sized'] as const] : []),
              ['price', 'Price'],
              ['breakdown', 'Breakdown'],
            ]
            const subLabel = (t: string) => <div className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-secondary mb-1.5">{t}</div>

            // isModal=true means this render call is from inside ChartModal (equity/breakdown only).
            // Price chart manages its own fullscreen internally via position:fixed so the single
            // klinecharts instance is never disposed/re-inited during the fullscreen toggle.
            const renderChart = (key: string, h: number, isModal = false): React.ReactNode => {
              switch (key) {
                case 'equity':
                  return (
                    <>
                      <EquityCurveChart data={run.equity_curve} bands={regimeBands} height={h} />
                      {overlayOn && regimeBands.length > 0 && <RegimeLegend bands={regimeBands} />}
                    </>
                  )
                case 'sized':
                  return (
                    <>
                      <SizedEquityCurveChart data={run.sized_timeline} height={h} />
                      <SizedCurveLegend mode={run.sizing_mode} />
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
                      <div>
                        {subLabel('Drawdown from peak')}
                        <DrawdownChart equity={run.equity_curve} limitLines={evalLimits} height={hDraw} />
                      </div>
                      <div className={hasDirection ? 'grid gap-6 lg:grid-cols-2' : ''}>
                        <div>
                          {subLabel('Daily P&L')}
                          <DailyPnlChart data={run.daily_pnl} netPnl={run.net_pnl} height={hRow} />
                        </div>
                        {hasDirection && (
                          <div>
                            {subLabel('Long vs Short')}
                            <DirectionBreakdown equity={run.equity_curve} />
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
                  {!hasCharts && !isMt5 && (
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
                      {isMt5
                        ? 'Chart data is parsed from the MT5 report at completion. If empty, the report may not have included trade data.'
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
                        {primaryTab === 'equity' && hasRealRegimeTags && (
                          <RegimeOverlayToggle on={overlayOn} onChange={handleOverlayToggle} />
                        )}
                        {!isMt5 && (
                          <button
                            onClick={() => runId && reloadCharts.mutate(runId)}
                            disabled={reloadCharts.isPending}
                            className="flex items-center gap-[6px] px-2 py-[4px] rounded text-[11px] text-text-tertiary hover:text-text-secondary transition-colors disabled:opacity-50"
                          >
                            <RefreshCw size={11} className={reloadCharts.isPending ? 'animate-spin' : ''} />
                            Refresh
                          </button>
                        )}
                        {isMt5 && primaryTab === 'price' && (
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
