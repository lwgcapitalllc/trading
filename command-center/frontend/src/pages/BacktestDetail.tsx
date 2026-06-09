import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft, ChevronDown, ChevronUp, AlertTriangle,
  CheckCircle, XCircle, Minus, Info, Square, RefreshCw, RotateCcw, Activity, Tag, Layers, Play,
  Copy, Check,
} from 'lucide-react'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Label,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import { toast } from 'sonner'
import { useBacktestRun, useRunLog, useLabProgress, useStopBacktest, useReloadCharts, useRetryBacktest, useBackfillRegime, useBackfillStatus, useRunningVpsJob } from '@/hooks/useLab'
import { useStressTests, useRunStressTest, useRunningStressLock } from '@/hooks/useStressTests'
import type { BacktestDetail as Run, EvaluationDetail, EquityPoint, DailyPnlPoint } from '@/types'
import { C } from '@/themes/chart'

import { OptimizeButton } from '@/components/OptimizeButton'
import RobustnessGradeBadge from '@/components/RobustnessGradeBadge'
import { StatusPill } from '@/components/StatusPill'

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

// ── Calmar ratio ─────────────────────────────────────────────────────────────

function computeCalmar(
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

function calmarCls(c: number | null): string {
  if (c == null) return 'text-text-tertiary'
  if (c >= 3.0) return 'text-pos-text'
  if (c >= 1.0) return 'text-warn-text'
  return 'text-neg-text'
}

function calmarLabel(c: number | null): string {
  if (c == null) return 'annlzd return ÷ max drawdown'
  if (c >= 3.0) return 'excellent'
  if (c >= 1.5) return 'good'
  if (c >= 1.0) return 'marginal'
  return 'poor — drawdown outpaces return'
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

function InfoTip({ text }: { text: string }) {
  return (
    <span className="relative group/tip inline-flex items-center ml-[5px] cursor-help flex-shrink-0">
      <Info size={9} className="text-text-tertiary/50 group-hover/tip:text-accent transition-colors" />
      <span className="absolute bottom-[calc(100%+8px)] left-0 z-50 hidden group-hover/tip:block w-48 rounded-lg bg-bg-base border border-border-default px-3 py-2.5 text-[11px] text-text-secondary shadow-2xl pointer-events-none leading-relaxed normal-case tracking-normal font-normal">
        {text}
      </span>
    </span>
  )
}

// ── MetricCard ────────────────────────────────────────────────────────────────

function MetricCard({ label, value, valueCls = '', sub, subCls = 'text-text-tertiary', tooltip }: {
  label: string
  value: React.ReactNode
  valueCls?: string
  sub?: React.ReactNode
  subCls?: string
  tooltip?: string
}) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg px-[15px] py-[14px] h-full flex flex-col justify-center">
      <div className="flex items-center text-[10px] text-text-secondary uppercase tracking-[0.6px]">
        {label}
        {tooltip && <InfoTip text={tooltip} />}
      </div>
      <div className={`text-[24px] font-semibold mt-[6px] tracking-[-0.5px] font-mono ${valueCls}`}>{value}</div>
      {sub && <div className={`text-[11px] mt-[3px] leading-snug ${subCls}`}>{sub}</div>}
    </div>
  )
}

// ── KPI grid ──────────────────────────────────────────────────────────────────

function KpiGrid({ run, fallback, equity = [], stretch = false }: {
  run: Run; fallback: FallbackMetrics; equity?: EquityPoint[]; stretch?: boolean
}) {
  const pnlCls = run.net_pnl == null ? '' : run.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'

  const sharpe      = run.sharpe             ?? fallback.sharpe
  const worstDay    = run.worst_day_pnl      ?? fallback.worstDay
  const worstStreak = run.worst_losing_streak ?? fallback.worstStreak
  const sharpeEst   = run.sharpe == null && fallback.sharpe != null
  const calmar      = computeCalmar(run.net_pnl, run.max_drawdown, equity)

  return (
    <div className={`grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 ${stretch ? 'h-full auto-rows-fr' : ''}`}>
      <MetricCard
        label="Net P&L"
        value={dollar(run.net_pnl, true)}
        valueCls={pnlCls}
        tooltip="Total profit or loss after commissions. The bottom line."
      />
      <MetricCard
        label="Max Drawdown"
        value={dollar(run.max_drawdown)}
        valueCls="text-neg-text"
        sub="largest peak-to-trough drop"
        tooltip="Biggest balance drop from peak to trough before recovery. e.g. $120k → $75k = $45k drawdown. Prop firms cap this hard — breaching it fails the challenge. Lower is better."
      />
      <MetricCard
        label="Win Rate"
        value={pct(run.win_rate)}
        valueCls={winRateCls(run.win_rate)}
        sub={winRateLabel(run.win_rate)}
        tooltip="% of trades that closed in profit. Good ≥60%, fair ≥50%, weak <50%. High win rate alone doesn't guarantee profitability — size of wins vs losses matters too."
      />
      <MetricCard
        label="Profit Factor"
        value={run.profit_factor != null ? run.profit_factor.toFixed(2) : '—'}
        valueCls={pfCls(run.profit_factor)}
        sub={pfLabel(run.profit_factor)}
        tooltip="Gross wins ÷ gross losses. Below 1.0 is a losing strategy. Good ≥1.5, strong ≥2.0."
      />
      <MetricCard
        label="Trade Count"
        value={run.trade_count ?? '—'}
        sub={
          run.avg_trade_duration_min != null
            ? `avg ${run.avg_trade_duration_min.toFixed(0)} min / trade`
            : undefined
        }
        tooltip="Total completed trades. More trades = more statistically reliable results."
      />
      <MetricCard
        label="Sharpe (annlzd)"
        value={sharpe != null ? sharpe.toFixed(2) : '—'}
        valueCls={sharpeCls(sharpe)}
        sub={sharpeLabel(sharpe, sharpeEst)}
        tooltip="Return per unit of risk, annualized. Good ≥1.0, strong ≥2.0. Negative means the strategy loses more than doing nothing."
      />
      <MetricCard
        label="Worst Day"
        value={dollar(worstDay)}
        valueCls={worstDay != null && worstDay < 0 ? 'text-neg-text' : ''}
        sub="single worst trading day"
        tooltip="Largest single-day loss. Compare this to your prop firm's daily loss limit — exceeding it would have failed the challenge that day."
      />
      <MetricCard
        label="Worst Streak"
        value={worstStreak != null ? `${worstStreak} L` : '—'}
        valueCls={worstStreakCls(worstStreak)}
        sub="consecutive losing days"
        tooltip="Longest consecutive run of losing days. Tests whether you'd stay disciplined under sustained drawdown. ≥6 days is a red flag."
      />
      <MetricCard
        label="Avg Win"
        value={run.avg_win != null ? `$${run.avg_win.toFixed(0)}` : '—'}
        valueCls="text-pos-text"
        tooltip="Average profit per winning trade."
      />
      <MetricCard
        label="Avg Loss"
        value={run.avg_loss != null ? `-$${Math.abs(run.avg_loss).toFixed(0)}` : '—'}
        valueCls="text-neg-text"
        sub={run.avg_win != null && run.avg_loss != null
          ? `R:R ${(run.avg_win / Math.abs(run.avg_loss)).toFixed(2)}:1`
          : undefined}
        tooltip="Average loss per losing trade. Sub-line shows the win:loss ratio (reward:risk). Above 1.0 means wins are larger than losses."
      />
      <MetricCard
        label="Calmar Ratio"
        value={calmar != null ? calmar.toFixed(2) : '—'}
        valueCls={calmarCls(calmar)}
        sub={calmarLabel(calmar)}
        tooltip="Annualized return divided by max drawdown. The definitive risk-adjusted metric for funded traders — it penalizes large drawdowns directly. ≥3.0 is excellent, ≥1.0 is decent, <1.0 means your drawdown is larger than your annualized gains."
      />
    </div>
  )
}

// ── Regime overlay — colored line design ──────────────────────────────────────

const REGIME_COLORS: Record<string, string> = {
  TRENDING:        '#06b6d4',
  TRANSITIONING:   '#8b5cf6',
  RANGING:         '#f59e0b',
  HIGH_VOLATILITY: '#ef4444',
  LOW_VOLATILITY:  '#64748b',
  UNKNOWN:         '#6b7280',
}

const REGIME_LABEL: Record<string, string> = {
  TRENDING: 'Trending', RANGING: 'Ranging', HIGH_VOLATILITY: 'High Volatility',
  LOW_VOLATILITY: 'Low Volatility', TRANSITIONING: 'Transitioning', UNKNOWN: 'Unknown',
}

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
  return bands
}

// ── Equity curve ──────────────────────────────────────────────────────────────

function fmtChartDate(d?: string): string {
  if (!d) return ''
  const dt = new Date(d.slice(0, 10) + 'T12:00:00')
  const yr = String(dt.getFullYear()).slice(-2)
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ` '${yr}`
}

type AugPoint = EquityPoint & { [k: string]: unknown }

function EquityCurveChart({ data, bands = [] }: { data: EquityPoint[]; bands?: RegimeBand[] }) {
  // Build per-segment data keys for the colored line approach.
  // Each segment extends one point into the next band so adjacent segments connect seamlessly.
  const augData: AugPoint[] = useMemo(() => {
    if (!bands.length) return data as AugPoint[]
    return data.map(pt => {
      const extra: Record<string, number | null> = {}
      for (let i = 0; i < bands.length; i++) {
        const hi = i < bands.length - 1 ? bands[i + 1].x1 : bands[i].x2
        extra[`_s${i}`] = (pt.index >= bands[i].x1 && pt.index <= hi) ? pt.equity : null
      }
      return { ...pt, ...extra }
    })
  }, [data, bands])

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
  const hasBands   = bands.length > 0

  return (
    <ResponsiveContainer key={hasBands ? 'regime' : 'base'} width="100%" height={300}>
      <AreaChart data={augData} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
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
        {/* Without overlay: normal single-color area + fill */}
        {!hasBands && (
          <Area
            type="monotone"
            dataKey="equity"
            stroke={curveColor}
            strokeWidth={1.5}
            fill={endEq >= startEq ? 'url(#eqPos)' : 'url(#eqNeg)'}
            dot={false}
            activeDot={{ r: 4, fill: curveColor, stroke: 'transparent' }}
            baseValue={startEq}
          />
        )}
        {/* With overlay: base Area keeps the gradient fill; per-segment Areas draw colored lines on top */}
        {hasBands && (
          <>
            <Area
              type="monotone" dataKey="equity"
              stroke="none" fill={endEq >= startEq ? 'url(#eqPos)' : 'url(#eqNeg)'}
              dot={false} activeDot={false} baseValue={startEq}
            />
            {bands.map((band, i) => {
              const color = REGIME_COLORS[band.regime] ?? REGIME_COLORS.UNKNOWN
              return (
                <Area
                  key={i}
                  type="monotone"
                  dataKey={`_s${i}`}
                  stroke={color}
                  strokeWidth={2}
                  fill="transparent"
                  dot={false}
                  activeDot={{ r: 4, fill: color, stroke: 'transparent' }}
                  connectNulls={false}
                />
              )
            })}
          </>
        )}
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ── Drawdown chart ────────────────────────────────────────────────────────────

function DrawdownChart({ equity, limitLines }: {
  equity: EquityPoint[]
  limitLines?: Array<{ limit: number; label: string; pass: boolean }>
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
    <ResponsiveContainer width="100%" height={140}>
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
          <div style={{ width: 20, height: 2, background: REGIME_COLORS[regime] ?? REGIME_COLORS.UNKNOWN, borderRadius: 1 }} />
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
            <div className={`text-[18px] font-semibold font-mono tabular-nums ${pnlCls}`}>{dollar(s.totalPnl, true)}</div>
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie
                  data={data}
                  cx="50%" cy="50%"
                  innerRadius={50} outerRadius={70}
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
                  <Label value={`${winPct}%`} position="center" fill="#e6edf3" fontSize={20} fontWeight={700} />
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

function DailyPnlChart({ data, netPnl }: { data: DailyPnlPoint[]; netPnl: number | null }) {
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
    <ResponsiveContainer width="100%" height={260}>
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

const VERDICT_CONFIG = {
  PASS:    { label: 'PASS',    bg: 'bg-pos-muted',  text: 'text-pos-text',  border: 'border-l-pos-text/50',  Icon: CheckCircle },
  WARN:    { label: 'WARN',    bg: 'bg-warn-muted', text: 'text-warn-text', border: 'border-l-warn-text/50', Icon: Minus       },
  DISCARD: { label: 'DISCARD', bg: 'bg-neg-muted',  text: 'text-neg-text',  border: 'border-l-neg-text/50',  Icon: XCircle     },
} as const

function EvalCard({ ev, netPnl }: { ev: EvaluationDetail; netPnl?: number | null }) {
  const cfg = VERDICT_CONFIG[ev.verdict as keyof typeof VERDICT_CONFIG] ?? VERDICT_CONFIG.DISCARD
  // Profitable runs that fail a firm rule get amber styling (not red) — keep the DISCARD label.
  const isWarnColor = cfg === VERDICT_CONFIG.DISCARD && (netPnl ?? 0) > 0
  const colorCfg    = isWarnColor ? VERDICT_CONFIG.WARN : cfg
  const { Icon }    = cfg

  return (
    <div className={`bg-bg-surface border border-border-subtle border-l-[3px] ${colorCfg.border} rounded-lg overflow-hidden h-full flex flex-col`}>
      {/* Header */}
      <div className="px-4 pt-4 pb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-[13px] font-semibold text-text-primary leading-tight">{ev.ruleset_name}</div>
          <div className="text-[11px] text-text-tertiary font-mono mt-1">{ev.ruleset_id}</div>
        </div>
        <span className={`inline-flex items-center gap-[5px] px-3 py-[5px] rounded-full text-[11px] font-bold uppercase tracking-[0.4px] flex-shrink-0 ${colorCfg.bg} ${colorCfg.text}`}>
          <Icon size={11} />
          {cfg.label}
        </span>
      </div>

      <div className="mx-4 border-t border-border-subtle" />

      {/* Rule checks */}
      <div className="px-4 py-3 space-y-[10px]">
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

      {/* Footer */}
      {(ev.simulated_eval_days != null || ev.notes) && (
        <div className="px-4 pb-4 space-y-1">
          {ev.simulated_eval_days != null && (
            <div className="text-[11px] text-text-tertiary">{ev.simulated_eval_days} simulated eval days</div>
          )}
          {ev.notes && (
            <p className="text-[11px] text-text-tertiary leading-relaxed">{ev.notes}</p>
          )}
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
    re: /terminal64\.exe|Launching MT5/i,
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

interface RegimeRow {
  regime: string; days: number; trades: number; netPnl: number
  winRate: number | null; profitFactor: number | null; worstDay: number | null
}

function computeRegimeBreakdown(run: Run): RegimeRow[] {
  const { equity_curve, daily_pnl } = run
  if (!equity_curve.length || !daily_pnl.length) return []

  const dateToRegime  = new Map<string, string>()
  const regimeDays    = new Map<string, Set<string>>()
  const regimeDailyPnl = new Map<string, number[]>()

  for (const d of daily_pnl) {
    const regime = d.regime_tag ?? 'UNKNOWN'
    dateToRegime.set(d.date, regime)
    if (!regimeDays.has(regime)) regimeDays.set(regime, new Set())
    regimeDays.get(regime)!.add(d.date)
    if (!regimeDailyPnl.has(regime)) regimeDailyPnl.set(regime, [])
    regimeDailyPnl.get(regime)!.push(d.pnl)
  }

  const stats = new Map<string, { netPnl: number; wins: number; grossWins: number; grossLosses: number; trades: number }>()
  for (let i = 0; i < equity_curve.length; i++) {
    const trade  = equity_curve[i]
    const regime = trade.date ? (dateToRegime.get(trade.date) ?? 'UNKNOWN') : 'UNKNOWN'
    const pnl    = i === 0 ? trade.equity : trade.equity - equity_curve[i - 1].equity
    if (!stats.has(regime)) stats.set(regime, { netPnl: 0, wins: 0, grossWins: 0, grossLosses: 0, trades: 0 })
    const s = stats.get(regime)!
    s.netPnl += pnl; s.trades++
    if (pnl > 0) { s.wins++; s.grossWins += pnl } else if (pnl < 0) { s.grossLosses += Math.abs(pnl) }
  }

  const rows: RegimeRow[] = []
  for (const [regime, s] of stats) {
    const dp = regimeDailyPnl.get(regime) ?? []
    rows.push({
      regime, days: regimeDays.get(regime)?.size ?? 0, trades: s.trades, netPnl: s.netPnl,
      winRate: s.trades > 0 ? s.wins / s.trades : null,
      profitFactor: s.grossLosses > 0 ? s.grossWins / s.grossLosses : null,
      worstDay: dp.length ? Math.min(...dp) : null,
    })
  }
  rows.sort((a, b) => b.days - a.days)
  const ui = rows.findIndex(r => r.regime === 'UNKNOWN')
  if (ui > 0) rows.push(rows.splice(ui, 1)[0])
  return rows
}

function PerformanceByRegimeTable({ run }: { run: Run }) {
  const rows = useMemo(() => computeRegimeBreakdown(run), [run])
  if (!rows.length) return null
  const worstOverall = run.daily_pnl.length ? Math.min(...run.daily_pnl.map(d => d.pnl)) : null

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-border-subtle">
        <div className="text-[10px] font-semibold text-text-secondary uppercase tracking-[0.6px]">Performance by Regime</div>
        <div className="text-[10px] text-text-tertiary mt-[2px]">How the strategy performs in each market condition.</div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-border-subtle">
              {['Regime','Days','Trades','Net P&L','Win Rate','Prof. Factor','Worst Day'].map(h => (
                <th key={h} className={`text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.5px] px-4 py-2 ${h === 'Regime' ? 'text-left' : 'text-right'}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const color = REGIME_COLORS[row.regime] ?? REGIME_COLORS.UNKNOWN
              return (
                <tr key={i} className={i < rows.length - 1 ? 'border-b border-border-subtle/60' : ''}>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <div style={{ width: 16, height: 2, background: color, borderRadius: 1, flexShrink: 0 }} />
                      <span className="text-text-secondary">{REGIME_LABEL[row.regime] ?? row.regime}</span>
                    </div>
                  </td>
                  <td className="text-right px-4 py-2.5 text-text-secondary tabular-nums">{row.days}</td>
                  <td className="text-right px-4 py-2.5 text-text-secondary tabular-nums">{row.trades}</td>
                  <td className={`text-right px-4 py-2.5 tabular-nums font-medium ${row.netPnl >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>{dollar(row.netPnl, true)}</td>
                  <td className={`text-right px-4 py-2.5 tabular-nums ${winRateCls(row.winRate)}`}>{row.winRate != null ? `${(row.winRate * 100).toFixed(1)}%` : '—'}</td>
                  <td className={`text-right px-4 py-2.5 tabular-nums ${pfCls(row.profitFactor)}`}>{row.profitFactor != null ? row.profitFactor.toFixed(2) : '—'}</td>
                  <td className={`text-right px-4 py-2.5 tabular-nums ${row.worstDay != null && row.worstDay < 0 ? 'text-neg-text' : 'text-text-secondary'}`}>{row.worstDay != null ? dollar(row.worstDay) : '—'}</td>
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr className="border-t border-border-subtle bg-bg-elevated/30">
              <td className="px-4 py-2.5 text-[11px] font-semibold text-text-secondary">Overall</td>
              <td className="text-right px-4 py-2.5 text-[11px] font-medium text-text-secondary tabular-nums">{run.daily_pnl.length}</td>
              <td className="text-right px-4 py-2.5 text-[11px] font-medium text-text-secondary tabular-nums">{run.trade_count ?? run.equity_curve.length}</td>
              <td className={`text-right px-4 py-2.5 text-[11px] font-semibold tabular-nums ${(run.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>{dollar(run.net_pnl, true)}</td>
              <td className={`text-right px-4 py-2.5 text-[11px] font-medium tabular-nums ${winRateCls(run.win_rate)}`}>{run.win_rate != null ? `${(run.win_rate * 100).toFixed(1)}%` : '—'}</td>
              <td className={`text-right px-4 py-2.5 text-[11px] font-medium tabular-nums ${pfCls(run.profit_factor)}`}>{run.profit_factor != null ? run.profit_factor.toFixed(2) : '—'}</td>
              <td className={`text-right px-4 py-2.5 text-[11px] font-medium tabular-nums ${worstOverall != null && worstOverall < 0 ? 'text-neg-text' : 'text-text-secondary'}`}>{worstOverall != null ? dollar(worstOverall) : '—'}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

// ── Backfill regime button ────────────────────────────────────────────────────

function BackfillRegimeButton({ run }: { run: Run }) {
  const queryClient = useQueryClient()
  const backfill    = useBackfillRegime()
  const hasRealTags = run.daily_pnl.some(d => d.regime_tag && d.regime_tag !== 'UNKNOWN')
  const [polling, setPolling] = useState(false)
  const { data: status } = useBackfillStatus(run.run_id, polling)

  useEffect(() => {
    if (status?.status === 'complete') {
      setPolling(false)
      queryClient.invalidateQueries({ queryKey: ['lab', 'run', run.run_id] })
      if ((status.tagged ?? 0) > 0) {
        toast.success(`${status.tagged}/${status.total} days tagged`)
      } else {
        toast.warning('Tagging finished but no regime data — OHLC unavailable for this symbol')
      }
    } else if (status?.status === 'failed') {
      setPolling(false)
      toast.error('Backfill failed')
    }
  }, [status?.status, run.run_id, queryClient])

  if (hasRealTags || run.status !== 'complete') return null

  const isRunning = status?.status === 'running' || polling
  return (
    <button
      onClick={() => backfill.mutate(run.run_id, {
        onSuccess: () => setPolling(true),
        onError:   (e: unknown) => toast.error(`Tag failed: ${(e as { detail?: string })?.detail ?? 'Unknown error'}`),
      })}
      disabled={isRunning || backfill.isPending}
      className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-bg-hover disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <Tag size={14} />
      {isRunning
        ? (status?.total ? `Tagging ${status.tagged}/${status.total}…` : 'Tagging…')
        : 'Tag Regimes'}
    </button>
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

// ── Page ──────────────────────────────────────────────────────────────────────

export function BacktestDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate     = useNavigate()
  const { data: run, isLoading } = useBacktestRun(runId ?? null)
  const { data: progress }       = useLabProgress()
  const stopBacktest             = useStopBacktest()
  const reloadCharts             = useReloadCharts()
  const retryBacktest            = useRetryBacktest()
  const { data: runningJob }     = useRunningVpsJob()
  const { data: stressTests }    = useStressTests(run?.run_id)
  const { data: stressLock }     = useRunningStressLock()
  const latestStress             = stressTests?.[0]
  const [showStressModal, setShowStressModal] = useState(false)
  const [overlayOn, setOverlayOn] = useState(getOverlayPref)
  const handleOverlayToggle = useCallback((v: boolean) => { setOverlayOn(v); setOverlayPref(v) }, [])

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
  const stressBlocked = isMt5 ? (stressLock?.forex ?? false) : (stressLock?.futures ?? false)

  const progressMatches = progress?.job_id === run?.run_id
  const runPct       = isRunning ? (progressMatches ? (progress?.pct ?? 0) : 0) : 0
  const runMessage   = isRunning ? (progressMatches ? (progress?.message ?? 'Starting…') : 'Starting…') : ''
  const runStartedAt = isRunning ? (progressMatches ? (progress?.started_at ?? null) : null) : null

  const backLabel = run?.optimization_id ? 'Optimization'
    : run?.sweep_id ? 'Sweep'
    : 'Backtests'
  const backPath  = run?.optimization_id ? `/backtests/optimizations/${run.optimization_id}`
    : run?.sweep_id ? `/backtests/sweeps/${run.sweep_id}`
    : '/backtests'

  return (
    <div>
      <button
        onClick={() => navigate(backPath)}
        className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
      >
        <ArrowLeft size={14} /> {backLabel}
      </button>

      {isLoading && <Skeleton />}

      {run && (
        <div className="space-y-8">
          {/* ── Header ───────────────────────────────────────────────────── */}
          <div>
            <div className="flex items-start justify-between gap-4">
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
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {!isRunning && (
                  <button
                    onClick={() => retryBacktest.mutate(run.run_id)}
                    disabled={retryBacktest.isPending || (isMt5 ? !!runningJob?.mt5?.running : !!runningJob?.nt8?.running)}
                    className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded border border-border-subtle text-text-secondary hover:text-text-primary hover:bg-bg-hover disabled:opacity-40"
                    title={(isMt5 ? !!runningJob?.mt5?.running : !!runningJob?.nt8?.running) ? `${isMt5 ? 'MT5' : 'NT8'} is busy — wait for the current job to finish` : run.status.startsWith('failed') ? 'Retry this backtest' : run.optimization_id && !run.equity_curve?.length ? 'Run a full backtest on this parameter set to get charts and trade data' : 'Rerun this backtest'}
                  >
                    {retryBacktest.isPending
                      ? <RefreshCw size={14} className="animate-spin" />
                      : <Play size={14} />}
                    {run.status.startsWith('failed') ? 'Retry' : run.optimization_id && !run.equity_curve?.length ? 'Full Backtest' : 'Rerun'}
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
                  return (
                    <button
                      onClick={() => !stressBlocked && setShowStressModal(true)}
                      disabled={stressBlocked}
                      title={stressBlocked ? `A ${isMt5 ? 'forex' : 'futures'} stress test is already running` : undefined}
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
            </div>
          </div>

          {/* ── Banners ───────────────────────────────────────────────────── */}
          {isRunning && <RunningBanner pct={runPct} message={runMessage} startedAt={runStartedAt} onStop={() => stopBacktest.mutate(run.run_id)} runId={run.run_id} runner={run.runner ?? 'ninjatrader'} steps={isMt5 ? MT5_RUN_STEPS : NT8_RUN_STEPS} />}
          {isFailed && <FailureBanner run={run} />}
          {/* ── Evaluations + Performance (side by side) ──────────────────── */}
          {isComplete && (
            <div className={run.evaluations.length > 0
              ? 'grid gap-6 lg:grid-cols-[minmax(260px,380px)_1fr]'
              : ''}>

              {/* Left: firm evaluation cards — stretches to match KPI height */}
              {run.evaluations.length > 0 && (
                <div className="flex flex-col">
                  <SectionLabel>Evaluation</SectionLabel>
                  <div className="flex flex-col gap-3 flex-1">
                    {run.evaluations.map(ev => <EvalCard key={ev.eval_id} ev={ev} netPnl={run.net_pnl} />)}
                  </div>
                </div>
              )}

              {/* Right: KPIs — flex-col so grid can stretch to match eval card */}
              <div className={run.evaluations.length > 0 ? 'flex flex-col' : ''}>
                <SectionLabel>Performance</SectionLabel>
                {run.evaluations.length > 0 ? (
                  <div className="flex-1">
                    <KpiGrid run={run} fallback={fallback} equity={run.equity_curve} stretch />
                  </div>
                ) : (
                  <KpiGrid run={run} fallback={fallback} equity={run.equity_curve} />
                )}
              </div>
            </div>
          )}

          {/* ── Charts ────────────────────────────────────────────────────── */}
          {isComplete && (() => {
            const hasCharts = run.equity_curve.length > 0

            const seenLimits = new Set<number>()
            const evalLimits: Array<{ limit: number; label: string; pass: boolean }> = []
            for (const e of run.evaluations) {
              if (!seenLimits.has(e.firm_max_loss_eod)) {
                seenLimits.add(e.firm_max_loss_eod)
                const same = run.evaluations.filter(x => x.firm_max_loss_eod === e.firm_max_loss_eod)
                evalLimits.push({ limit: e.firm_max_loss_eod, label: e.ruleset_name, pass: same.every(x => x.drawdown_pass) })
              }
            }

            return (
              <div className="space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <SectionLabel>Charts</SectionLabel>
                  </div>
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
                  {hasCharts && (
                    <div className="flex items-center gap-2">
                      {hasRealRegimeTags && (
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
                    </div>
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
                    {/* Equity curve */}
                    <div className="bg-bg-surface border border-border-subtle rounded-lg px-3 pt-4 pb-2">
                      <div className="text-[10px] font-semibold text-text-secondary uppercase tracking-[0.6px] px-1">Equity curve</div>
                      <div className="text-[10px] text-text-tertiary px-1 mt-[3px] mb-2">Steadily rising = good. Big peak then long decline = giving back gains.</div>
                      <EquityCurveChart data={run.equity_curve} bands={regimeBands} />
                      {overlayOn && regimeBands.length > 0 && <RegimeLegend bands={regimeBands} />}
                    </div>

                    {/* Performance by Regime — immediately below equity curve when overlay is on */}
                    {hasRealRegimeTags && (
                      <div style={{
                        maxHeight: overlayOn ? '1000px' : '0',
                        opacity: overlayOn ? 1 : 0,
                        overflow: 'hidden',
                        transition: 'max-height 0.35s ease, opacity 0.25s ease',
                      }}>
                        <PerformanceByRegimeTable run={run} />
                      </div>
                    )}

                    {/* Drawdown */}
                    <div className="bg-bg-surface border border-border-subtle rounded-lg px-3 pt-4 pb-2">
                      <div className="text-[10px] font-semibold text-text-secondary uppercase tracking-[0.6px] px-1">Drawdown from peak</div>
                      <div className="text-[10px] text-text-tertiary px-1 mt-[3px] mb-1">Shallow and short = good. Dips exceeding the firm's drawdown limit = instant fail.</div>
                      <DrawdownChart equity={run.equity_curve} limitLines={evalLimits} />
                    </div>

                    {/* Daily P&L — full width */}
                    <div className="bg-bg-surface border border-border-subtle rounded-lg px-3 pt-4 pb-2">
                      <div className="text-[10px] font-semibold text-text-secondary uppercase tracking-[0.6px] px-1">Daily P&amp;L</div>
                      <div className="text-[10px] text-text-tertiary px-1 mt-[3px] mb-2">Consistent moderate bars = good. Giant single bars = high daily-limit risk.</div>
                      <DailyPnlChart data={run.daily_pnl} netPnl={run.net_pnl} />
                    </div>

                    {/* Long vs Short — below daily P&L */}
                    {run.equity_curve.some(p => p.direction) && (
                      <div className="bg-bg-surface border border-border-subtle rounded-lg px-5 pt-4 pb-5">
                        <div className="text-[10px] font-semibold text-text-secondary uppercase tracking-[0.6px]">Long vs Short</div>
                        <div className="text-[10px] text-text-tertiary mt-[3px] mb-4">Both profitable = robust. One side losing = fragile, market-dependent edge.</div>
                        <DirectionBreakdown equity={run.equity_curve} />
                      </div>
                    )}
                  </>
                )}
              </div>
            )
          })()}

          {/* ── Logs ─────────────────────────────────────────────────────── */}
          {runId && <LogsSection runId={runId} autoExpand={isFailed || isRunning} isRunning={isRunning} isComplete={isComplete} isFailed={isFailed} />}
        </div>
      )}
    </div>
  )
}
