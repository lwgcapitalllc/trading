import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, ChevronDown, ChevronUp, AlertTriangle,
  CheckCircle, XCircle, Minus, Info, Square, RefreshCw, RotateCcw,
} from 'lucide-react'
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import { useBacktestRun, useRunLog, useLabProgress, useStopBacktest, useReloadCharts, useRetryBacktest } from '@/hooks/useLab'
import type { BacktestDetail as Run, EvaluationDetail, EquityPoint, DailyPnlPoint } from '@/types'
import { C } from '@/themes/chart'
import { WorthinessBadge } from '@/components/WorthinessBadge'
import { OptimizeButton } from '@/components/OptimizeButton'

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
  const d  = new Date(iso + 'T00:00:00')
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

  const sy = new Date(first + 'T00:00:00').getFullYear()
  const ey = new Date(last  + 'T00:00:00').getFullYear()
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
  const firstDate = equity[0].date
  const lastDate  = equity[equity.length - 1].date
  if (!firstDate || !lastDate) return null
  const days = (new Date(lastDate + 'T00:00:00').getTime() - new Date(firstDate + 'T00:00:00').getTime()) / 86_400_000
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
// VPS agent doesn't report them directly.

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

// ── Equity curve ──────────────────────────────────────────────────────────────

function fmtChartDate(d?: string): string {
  if (!d) return ''
  const dt = new Date(d + 'T12:00:00')
  const yr = String(dt.getFullYear()).slice(-2)
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ` '${yr}`
}

function EquityCurveChart({ data }: { data: EquityPoint[] }) {
  if (!data.length) return null

  const startEq   = data[0]?.equity ?? 0
  const endEq     = data[data.length - 1]?.equity ?? 0
  const profitable = endEq >= startEq
  const allValues  = data.map(d => d.equity)
  const min = Math.min(...allValues)
  const max = Math.max(...allValues)
  const pad = (max - min) * 0.1 || 500
  const yMin = Math.min(startEq, min) - pad
  const yMax = max + pad

  // Split into above/below zero baseline for dual-color fill
  const curveColor = profitable ? C.pos : C.neg

  const eqTicks = calIndexTicks(data)

  return (
    <ResponsiveContainer width="100%" height={300}>
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
        <Tooltip
          contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 13, padding: '8px 12px' }}
          labelStyle={{ color: C.axisTick }}
          itemStyle={{ color: '#e5e7eb' }}
          formatter={(v: number, _: string, props: { payload?: EquityPoint }) => {
            const pt = props.payload
            return [
              `${v >= 0 ? '+' : ''}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
              pt?.direction ? `Equity (${pt.direction})` : 'Equity',
            ]
          }}
          labelFormatter={(_: unknown, payload: Array<{ payload?: EquityPoint }>) => {
            const pt = payload?.[0]?.payload
            if (!pt) return ''
            const dateStr = pt.date ? ` · ${fmtChartDate(pt.date)}` : ''
            return `Trade #${pt.index}${dateStr}`
          }}
        />
        <ReferenceLine y={startEq} stroke={C.refLine} strokeDasharray="4 4" />
        {startEq !== 0 && <ReferenceLine y={0} stroke={C.refLineDim} />}
        <Area
          type="monotone"
          dataKey="equity"
          stroke={curveColor}
          strokeWidth={1.5}
          fill={endEq >= 0 ? 'url(#eqPos)' : 'url(#eqNeg)'}
          dot={false}
          activeDot={{ r: 4, fill: curveColor, stroke: 'transparent' }}
          baseValue={startEq}
        />
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

// ── Direction breakdown ───────────────────────────────────────────────────────

function DirectionBreakdown({ equity }: { equity: EquityPoint[] }) {
  const trades = equity.filter(pt => pt.direction && pt.profit != null)
  if (!trades.length) return null

  const sides = ['Long', 'Short'] as const
  const stats = sides.map(dir => {
    const group   = trades.filter(pt => pt.direction === dir)
    const wins    = group.filter(pt => (pt.profit ?? 0) > 0).length
    const losses  = group.length - wins
    const totalPnl = group.reduce((s, pt) => s + (pt.profit ?? 0), 0)
    const avgTrade = group.length ? totalPnl / group.length : 0
    return { dir, count: group.length, wins, losses, totalPnl, avgTrade }
  })

  return (
    <div className="grid grid-cols-2 gap-6">
      {stats.map(s => {
        if (!s.count) return null
        const winPct = (s.wins / s.count) * 100
        const pnlCls = s.totalPnl >= 0 ? 'text-pos-text' : 'text-neg-text'
        return (
          <div key={s.dir} className="space-y-3">
            <div className="flex items-baseline justify-between">
              <span className="text-[13px] font-semibold text-text-primary">{s.dir}</span>
              <span className={`text-[14px] font-semibold font-mono ${pnlCls}`}>{dollar(s.totalPnl, true)}</span>
            </div>
            <div className="text-[11px] text-text-tertiary">
              {s.count} trades · avg {dollar(s.avgTrade, true)}/trade
            </div>
            {/* Split bar: green = won, red = lost */}
            <div className="h-[8px] flex rounded-full overflow-hidden">
              <div className="h-full bg-pos-text/75" style={{ width: `${winPct}%` }} />
              <div className="h-full bg-neg-text/65 flex-1" />
            </div>
            <div className="flex justify-between text-[12px] font-semibold">
              <span className="text-pos-text">{s.wins} won</span>
              <span className="text-neg-text">{s.losses} lost</span>
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
        <div className="text-text-tertiary text-[11px]">Available once per-trade data is extracted from NT8.</div>
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

function EvalCard({ ev }: { ev: EvaluationDetail }) {
  const cfg = VERDICT_CONFIG[ev.verdict as keyof typeof VERDICT_CONFIG] ?? VERDICT_CONFIG.DISCARD
  const { Icon } = cfg

  return (
    <div className={`bg-bg-surface border border-border-subtle border-l-[3px] ${cfg.border} rounded-lg overflow-hidden h-full flex flex-col`}>
      {/* Header */}
      <div className="px-4 pt-4 pb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-[13px] font-semibold text-text-primary leading-tight">{ev.ruleset_name}</div>
          <div className="text-[11px] text-text-tertiary font-mono mt-1">{ev.ruleset_id}</div>
        </div>
        <span className={`inline-flex items-center gap-[5px] px-3 py-[5px] rounded-full text-[11px] font-bold uppercase tracking-[0.4px] flex-shrink-0 ${cfg.bg} ${cfg.text}`}>
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

const RUN_STEPS = [
  { label: 'Connect',   startPct: 0  },
  { label: 'Configure', startPct: 20 },
  { label: 'Run',       startPct: 30 },
  { label: 'Results',   startPct: 70 },
  { label: 'Evaluate',  startPct: 95 },
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

// Candlestick chart constants — defined once at module level
const CHART_BULL = C.accent
const CHART_BEAR = C.neg
const CHART_PAD  = 5

const CHART_CANDLES = ((): Array<{ o: number; c: number; h: number; l: number }> => {
  let s = 0xC0FFEE42
  const r = () => { s ^= s << 13; s ^= s >> 17; s ^= s << 5; return (s >>> 0) / 0xffffffff }
  const bars: Array<{ o: number; c: number; h: number; l: number }> = []
  let p = 0.42
  const script: Array<[number, number, number]> = [
    [4, +0.060, 0.075],  // Connect:   gentle uptrend
    [3, +0.008, 0.050],  // Configure: sideways
    [5, -0.090, 0.080],  // Run:       sharp dip
    [6, +0.095, 0.085],  // Run:       strong recovery
    [5, +0.038, 0.065],  // Results:   steady climb
    [3, +0.022, 0.050],  // Evaluate:  final push
  ]
  for (const [n, trend, vol] of script) {
    for (let i = 0; i < n; i++) {
      const o  = p
      const mv = trend + (r() - 0.5) * vol
      const c  = Math.max(0.06, Math.min(0.94, o + mv))
      const hi = Math.max(o, c) + (0.3 + r() * 0.7) * vol * 0.9
      const lo = Math.min(o, c) - (0.3 + r() * 0.7) * vol * 0.9
      bars.push({ o, c, h: Math.min(0.96, hi), l: Math.max(0.04, lo) })
      p = c
    }
  }
  return bars
})()
const CHART_N    = CHART_CANDLES.length  // 26
const CHART_LOOP = 4800                  // ms per sweep cycle

function RunningBanner({ pct, message, startedAt, onStop }: {
  pct: number
  message: string
  startedAt: string | null
  onStop: () => void
}) {
  const elapsed   = useElapsed(startedAt)
  const activeIdx = RUN_STEPS.reduce((best, step, i) => pct >= step.startPct ? i : best, 0)

  const canvasRef   = useRef<HTMLCanvasElement>(null)
  const chartRowRef = useRef<HTMLDivElement>(null)
  const stagesRef   = useRef<HTMLDivElement>(null)
  const pctRef      = useRef(pct)
  const cwRef       = useRef(0)
  const dotXsRef    = useRef<number[]>([])

  // Keep pct ref current without restarting the animation loop
  useEffect(() => { pctRef.current = pct }, [pct])

  const measureAndAlign = useCallback(() => {
    const canvas = canvasRef.current
    const row    = chartRowRef.current
    const stages = stagesRef.current
    if (!canvas || !row || !stages) return
    const dots = Array.from(stages.querySelectorAll('[data-dot]')) as HTMLElement[]
    if (dots.length < 2) return
    const rowR = row.getBoundingClientRect()
    const fR   = dots[0].getBoundingClientRect()
    const lR   = dots[dots.length - 1].getBoundingClientRect()
    const left  = fR.left + fR.width  / 2 - rowR.left
    const right = lR.left + lR.width  / 2 - rowR.left
    canvas.style.left = `${left}px`
    const newCW = Math.round(right - left)
    if (newCW !== cwRef.current) { canvas.width = newCW; cwRef.current = newCW }
    const canvasLeft = parseFloat(canvas.style.left) || 0
    dotXsRef.current = dots.map(d => {
      const dr = d.getBoundingClientRect()
      return dr.left + dr.width / 2 - rowR.left - canvasLeft
    })
  }, [])

  useEffect(() => {
    measureAndAlign()
    window.addEventListener('resize', measureAndAlign)
    return () => window.removeEventListener('resize', measureAndAlign)
  }, [measureAndAlign])

  // Canvas animation loop — starts once, reads pct from ref each frame
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    const CH  = canvas.height
    let rafId: number

    function draw(ts: number) {
      const CW  = cwRef.current
      if (CW === 0) { rafId = requestAnimationFrame(draw); return }

      const cp = pctRef.current
      ctx.clearRect(0, 0, CW, CH)

      const rawIdx  = Math.min(cp / 100 * CHART_N, CHART_N)
      const cursorX = cp / 100 * CW
      const slotW   = CW / CHART_N
      const bodyW   = Math.max(3, Math.floor(slotW * 0.42))

      // Loop sweep: animIdx cycles 0 → rawIdx with ease-in-out, then restarts
      const t         = (ts % CHART_LOOP) / CHART_LOOP
      const eased     = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t
      const animIdx   = eased * rawIdx
      const fullCount  = Math.floor(animIdx)
      const activeProg = animIdx - fullCount

      // Dynamic y-scale anchored to real rawIdx so it never jumps mid-loop
      const visSlice  = CHART_CANDLES.slice(0, Math.max(4, Math.ceil(rawIdx)))
      const rawLo     = Math.min(...visSlice.map(c => c.l))
      const rawHi     = Math.max(...visSlice.map(c => c.h))
      const mid       = (rawLo + rawHi) / 2
      const half      = Math.max(0.07, (rawHi - rawLo) / 2 + 0.012)
      const priceMin  = mid - half
      const priceRng  = half * 2
      const toY       = (v: number) => CHART_PAD + (1 - (v - priceMin) / priceRng) * (CH - CHART_PAD * 2)

      // Checkpoint dashed lines at exact dot positions
      dotXsRef.current.forEach((dx, i) => {
        if (i === 0) return
        const passed = cursorX >= dx - 1
        ctx.strokeStyle = passed ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.06)'
        ctx.setLineDash([2, 4])
        ctx.lineWidth = 1
        ctx.beginPath(); ctx.moveTo(dx, 0); ctx.lineTo(dx, CH); ctx.stroke()
        ctx.setLineDash([])
      })

      // Candles — stop before any candle bleeds past the cursor line
      for (let i = 0; i < CHART_N; i++) {
        let prog: number
        if      (i < fullCount)    prog = 1
        else if (i === fullCount)  { prog = activeProg; if (prog <= 0.01) continue }
        else break

        const c        = CHART_CANDLES[i]
        const cx       = slotW * i + slotW / 2
        if (cx >= cursorX) break   // candle center at or past cursor — stop

        const isBull   = c.c >= c.o
        const clr      = isBull ? CHART_BULL : CHART_BEAR
        const isActive = i === fullCount

        const openY  = toY(c.o)
        const closeY = toY(c.c)
        const highY  = toY(c.h)
        const lowY   = toY(c.l)
        const bodyT  = Math.min(openY, closeY)
        const bodyB  = Math.max(openY, closeY)
        const bodyH  = Math.max(2, bodyB - bodyT)
        const midY   = (bodyT + bodyB) / 2

        // Cap body width so right edge never passes cursorX
        const cappedW = Math.min(bodyW, Math.max(1, cursorX - (cx - bodyW / 2)))

        const wickP = Math.min(1, prog / 0.25)
        if (wickP > 0) {
          ctx.strokeStyle = clr + (isActive ? 'ff' : 'bb'); ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(cx, midY); ctx.lineTo(cx, midY - (midY - highY) * wickP)
          ctx.moveTo(cx, midY); ctx.lineTo(cx, midY + (lowY  - midY) * wickP)
          ctx.stroke()
        }
        const bodyP = Math.max(0, (prog - 0.25) / 0.75)
        if (bodyP > 0) {
          ctx.fillStyle = clr + 'ff'
          ctx.fillRect(cx - cappedW / 2, isBull ? bodyB - bodyH * bodyP : bodyT, cappedW, bodyH * bodyP)
        }
      }

      // Cursor line
      if (cp > 0 && cp < 100) {
        ctx.strokeStyle = 'rgba(0,229,255,0.12)'; ctx.lineWidth = 4
        ctx.beginPath(); ctx.moveTo(cursorX, 0); ctx.lineTo(cursorX, CH); ctx.stroke()
        ctx.strokeStyle = 'rgba(0,229,255,0.65)'; ctx.lineWidth = 1
        ctx.beginPath(); ctx.moveTo(cursorX, 0); ctx.lineTo(cursorX, CH); ctx.stroke()

        // % pill — just right of cursor
        const label = `${Math.round(cp)}%`
        ctx.font = 'bold 10.5px "SF Mono","Fira Code",monospace'
        const tw = ctx.measureText(label).width
        const px = cursorX + 5
        ctx.fillStyle = 'rgba(0,42,51,0.90)'
        ctx.strokeStyle = 'rgba(0,229,255,0.35)'; ctx.lineWidth = 1
        ctx.beginPath();
        (ctx as unknown as { roundRect: (...a: unknown[]) => void })
          .roundRect(px - 3, 3, tw + 8, 16, 4)
        ctx.fill(); ctx.stroke()
        ctx.fillStyle = CHART_BULL; ctx.textAlign = 'left'
        ctx.fillText(label, px + 1, 15)
      }

      rafId = requestAnimationFrame(draw)
    }

    rafId = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(rafId)
  }, [])

  return (
    <div className="bg-accent-muted border border-accent/30 rounded-lg px-4 pt-3 pb-4">
      {/* Candlestick chart — canvas spans between first and last dot */}
      <div ref={chartRowRef} className="relative h-[100px] mb-2">
        <canvas ref={canvasRef} height={90} className="absolute bottom-0" />
      </div>

      {/* Stage pipeline */}
      <div ref={stagesRef} className="flex items-start">
        {RUN_STEPS.map((step, i) => {
          const done   = i < activeIdx
          const active = i === activeIdx
          return (
            <Fragment key={step.label}>
              <div className="flex flex-col items-center gap-[6px]">
                <span
                  data-dot=""
                  className={[
                    'w-[9px] h-[9px] rounded-full flex-shrink-0 transition-all duration-300',
                    done   ? 'bg-accent/80' :
                    active ? 'bg-accent' :
                             'border border-border-default bg-transparent',
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
              {i < RUN_STEPS.length - 1 && (
                <div className={[
                  'flex-1 h-[1.5px] mt-[3.75px]',
                  done ? 'bg-accent/40' : 'bg-border-subtle',
                ].join(' ')} />
              )}
            </Fragment>
          )
        })}
      </div>

      {/* Message + elapsed + stop */}
      <div className="flex items-center justify-between mt-3">
        <div className="flex items-center gap-2">
          <span className="w-[5px] h-[5px] rounded-full bg-accent animate-pulse flex-shrink-0" />
          <span className="text-[12px] text-text-secondary">{message || 'Starting…'}</span>
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

const FAILURE_GUIDANCE: Record<string, string> = {
  failed_timeout:
    'The VPS agent stopped responding mid-run. Verify NT8 is running and the Strategy Analyzer is open in the RDP session, then re-run.',
  failed_unknown:
    'An unexpected error occurred. Check the run logs below and the VPS agent log for details.',
}

function FailureBanner({ run, onRetry, retrying }: { run: Run; onRetry?: () => void; retrying?: boolean }) {
  const guidance = FAILURE_GUIDANCE[run.status] ?? FAILURE_GUIDANCE.failed_unknown
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
  const { data: log, isFetching } = useRunLog(open ? runId : null, 200, isRunning)

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
        {open ? <ChevronUp size={14} className="text-text-tertiary" /> : <ChevronDown size={14} className="text-text-tertiary" />}
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

function StatusBadge({ status }: { status: string }) {
  const isFailed = status.startsWith('failed')
  const label    = isFailed ? 'failed' : status
  const cls      = status === 'complete' ? 'bg-pos-muted text-pos-text'
    : status === 'running'  ? 'bg-accent-muted text-accent'
    : isFailed              ? 'bg-neg-muted text-neg-text'
    : 'bg-bg-hover text-text-secondary'
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-[4px] rounded-full text-[12px] font-semibold uppercase tracking-[0.4px] flex-shrink-0 ${cls}`}>
      {status === 'running' && (
        <span className="animate-bounce inline-block leading-none" style={{ animationDuration: '0.45s' }}>
          🏃
        </span>
      )}
      {label}
    </span>
  )
}

// ── Chart verdict banner ──────────────────────────────────────────────────────

function ChartVerdict({ run }: { run: Run }) {
  if (!run.equity_curve.length || !run.evaluations.length) return null

  const netPnl   = run.net_pnl ?? 0
  const isProfit = netPnl > 0
  const ddFails  = run.evaluations.filter(e => !e.drawdown_pass)
  const ddOk     = ddFails.length === 0
  const conFails = run.evaluations.filter(e => e.consistency_pass === false)
  const conOk    = conFails.length === 0

  let level: 'green' | 'yellow' | 'red'
  let summary: string
  if (!isProfit) {
    level = 'red';     summary = 'Net negative — not viable'
  } else if (!ddOk) {
    level = 'red';     summary = 'Profitable but breaches firm drawdown limits'
  } else if (!conOk) {
    level = 'yellow';  summary = 'Profitable and within drawdown, but fails consistency rule'
  } else {
    level = 'green';   summary = 'Profitable, within drawdown limits, and consistent'
  }

  const dot  = { green: '#00ff7f', yellow: '#ffb300', red: '#ff3b5c' }[level]
  const txt  = { green: 'text-pos-text', yellow: 'text-warn-text', red: 'text-neg-text' }[level]
  const bg   = { green: 'bg-pos-muted border-pos-text/20', yellow: 'bg-warn-muted border-warn-text/20', red: 'bg-neg-muted border-neg-text/20' }[level]

  const checks = [
    { label: 'Equity',      ok: isProfit, val: isProfit ? `+${dollar(netPnl)}` : dollar(netPnl) },
    { label: 'Drawdown',    ok: ddOk,     val: ddOk  ? 'Within all limits' : `${ddFails.length} breach${ddFails.length > 1 ? 'es' : ''}` },
    { label: 'Consistency', ok: conOk,    val: conOk ? 'OK'                : `${conFails.length} fail${conFails.length > 1 ? 's' : ''}` },
  ]

  return (
    <div className={`border rounded-lg px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2 ${bg}`}>
      <div className="flex items-center gap-2">
        <span className="w-[9px] h-[9px] rounded-full flex-shrink-0"
          style={{ background: dot, boxShadow: `0 0 6px ${dot}` }} />
        <span className={`text-[12px] font-semibold ${txt}`}>{summary}</span>
      </div>
      <div className="flex items-center gap-5 ml-auto">
        {checks.map(c => (
          <div key={c.label} className="flex items-center gap-[5px] text-[11px]">
            {c.ok
              ? <CheckCircle size={11} className="text-pos-text flex-shrink-0" />
              : <XCircle    size={11} className="text-neg-text flex-shrink-0" />}
            <span className="text-text-tertiary">{c.label}:</span>
            <span className={`${c.ok ? 'text-text-primary font-mono' : 'text-neg-text'}`}>{c.val}</span>
          </div>
        ))}
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

  const fallback = useMemo(
    () => computeFallbacks(run?.daily_pnl ?? []),
    [run?.daily_pnl],
  )

  const isRunning  = run?.status === 'running'
  const isFailed   = run?.status.startsWith('failed') ?? false
  const isComplete = run?.status === 'complete'

  const runPct       = isRunning ? (progress?.pct ?? 0) : 0
  const runMessage   = isRunning ? (progress?.message ?? 'Starting…') : ''
  const runStartedAt = isRunning ? (progress?.started_at ?? null) : null

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
                  <h1 className="text-h1 font-semibold leading-tight">
                    {run.strategy_name || run.strategy_id}
                  </h1>
                  {run.worthiness && (
                    <WorthinessBadge worthiness={run.worthiness} size="md" />
                  )}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono bg-accent/10 text-accent border border-accent/20">
                    {run.instrument}
                  </span>
                  <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-secondary font-mono">
                    {fmtDate(run.start_date)} → {fmtDate(run.end_date)}
                  </span>
                  {run.evaluations.length > 0 && (
                    <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-tertiary font-mono">
                      {run.evaluations.map(e => e.ruleset_id).join(', ')}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <OptimizeButton run={run} />
                {!isRunning && <StatusBadge status={run.status} />}
              </div>
            </div>
          </div>

          {/* ── Banners ───────────────────────────────────────────────────── */}
          {isRunning && <RunningBanner pct={runPct} message={runMessage} startedAt={runStartedAt} onStop={() => stopBacktest.mutate(run.run_id)} />}
          {isFailed && (
            <FailureBanner
              run={run}
              onRetry={!run.sweep_id && !run.optimization_id
                ? () => retryBacktest.mutate(run.run_id, {
                    onSuccess: (data) => navigate(`/backtests/runs/${data.run_id}`),
                  })
                : undefined}
              retrying={retryBacktest.isPending}
            />
          )}

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
                    {run.evaluations.map(ev => <EvalCard key={ev.eval_id} ev={ev} />)}
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
            const firstDate = run.equity_curve[0]?.date
            const lastDate  = run.equity_curve[run.equity_curve.length - 1]?.date

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
                    {hasCharts && firstDate && lastDate && (
                      <p className="text-[11px] text-text-tertiary -mt-2 mb-3">
                        {run.equity_curve.length.toLocaleString()} trades · {fmtDate(firstDate)} → {fmtDate(lastDate)}
                      </p>
                    )}
                  </div>
                  {!hasCharts && (
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

                {!hasCharts ? (
                  <div className="bg-bg-surface border border-border-subtle rounded-lg flex flex-col items-center justify-center gap-2 py-16 text-center px-6">
                    <div className="text-text-secondary text-[13px] font-medium">No chart data yet</div>
                    <div className="text-text-tertiary text-[11px] leading-relaxed max-w-xs">
                      Click "Load chart data from NT8" — requires NT8 Strategy Analyzer open with this run's results loaded.
                    </div>
                  </div>
                ) : (
                  <>
                    {/* Traffic-light verdict */}
                    <ChartVerdict run={run} />

                    {/* Equity curve */}
                    <div className="bg-bg-surface border border-border-subtle rounded-lg px-3 pt-4 pb-2">
                      <div className="text-[10px] font-semibold text-text-secondary uppercase tracking-[0.6px] px-1">Equity curve</div>
                      <div className="text-[10px] text-text-tertiary px-1 mt-[3px] mb-2">Steadily rising = good. Big peak then long decline = giving back gains.</div>
                      <EquityCurveChart data={run.equity_curve} />
                    </div>

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
