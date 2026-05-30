import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, ChevronDown, ChevronUp, AlertTriangle,
  CheckCircle, XCircle, Minus, Info, Square,
} from 'lucide-react'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import { useBacktestRun, useRunLog, useLabProgress, useStopBacktest } from '@/hooks/useLab'
import type { BacktestDetail as Run, EvaluationDetail, EquityPoint, DailyPnlPoint } from '@/types'

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
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
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
    <div className="bg-bg-surface border border-border-subtle rounded-lg px-[15px] py-[14px]">
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

function KpiGrid({ run, fallback }: { run: Run; fallback: FallbackMetrics }) {
  const pnlCls = run.net_pnl == null ? '' : run.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'

  const sharpe      = run.sharpe             ?? fallback.sharpe
  const worstDay    = run.worst_day_pnl      ?? fallback.worstDay
  const worstStreak = run.worst_losing_streak ?? fallback.worstStreak
  const sharpeEst   = run.sharpe == null && fallback.sharpe != null

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
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
    </div>
  )
}

// ── Equity curve ──────────────────────────────────────────────────────────────

function EquityCurveChart({ data }: { data: EquityPoint[] }) {
  if (!data.length) {
    return (
      <div className="h-[220px] flex flex-col items-center justify-center gap-2 text-center px-6">
        <div className="text-text-secondary text-[13px] font-medium">No equity curve yet</div>
        <div className="text-text-tertiary text-[11px] leading-relaxed max-w-xs">
          NT8 exports summary statistics only. Re-run the backtest — the runner will attempt to extract per-trade data from the NT8 Trades tab.
        </div>
      </div>
    )
  }

  const min = Math.min(...data.map(d => d.equity))
  const max = Math.max(...data.map(d => d.equity))
  const pad = (max - min) * 0.08 || 200
  const startEquity = data[0].equity
  const endEquity   = data[data.length - 1].equity
  const profitable  = endEquity >= startEquity
  const curveColor  = profitable ? '#00ff7f' : '#ff3b5c'

  return (
    <ResponsiveContainer width="100%" height={320}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
        <defs>
          <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor={curveColor} stopOpacity={0.18} />
            <stop offset="95%" stopColor={curveColor} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#ffffff07" />
        <XAxis
          dataKey="index"
          tick={{ fill: '#6b7280', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => data.length > 100 ? (v % 50 === 0 ? `#${v}` : '') : `#${v}`}
        />
        <YAxis
          domain={[min - pad, max + pad]}
          tick={{ fill: '#6b7280', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
          width={52}
        />
        <Tooltip
          contentStyle={{ background: '#181828', border: '1px solid #2a2a4a', borderRadius: 6, fontSize: 12 }}
          labelStyle={{ color: '#9ca3af' }}
          formatter={(v: number) => [`$${v.toLocaleString('en-US', { maximumFractionDigits: 0 })}`, 'Equity']}
          labelFormatter={(i: number) => `Trade #${i}`}
        />
        <ReferenceLine
          y={startEquity}
          stroke="#ffffff18"
          strokeDasharray="4 4"
        />
        <Area
          type="monotone"
          dataKey="equity"
          stroke={curveColor}
          strokeWidth={2}
          fill="url(#eqGrad)"
          dot={false}
          activeDot={{ r: 4, fill: curveColor, stroke: 'transparent' }}
        />
      </AreaChart>
    </ResponsiveContainer>
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
  const labelEvery = data.length > 60 ? 30 : data.length > 30 ? 10 : 1

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }} barCategoryGap="20%">
        <CartesianGrid strokeDasharray="3 3" stroke="#ffffff07" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fill: '#6b7280', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(d: string, i: number) => i % labelEvery === 0 ? chartDateLabel(d) : ''}
        />
        <YAxis
          tick={{ fill: '#6b7280', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
          width={52}
        />
        <Tooltip
          contentStyle={{ background: '#181828', border: '1px solid #2a2a4a', borderRadius: 6, fontSize: 12 }}
          labelStyle={{ color: '#9ca3af' }}
          formatter={(v: number) => [dollar(v, true), 'P&L']}
          labelFormatter={(d: string) => chartDateLabel(d)}
        />
        <ReferenceLine y={0} stroke="#ffffff20" />
        {halfTarget != null && (
          <ReferenceLine
            y={halfTarget}
            stroke="#ffb30050"
            strokeDasharray="4 4"
            label={{ value: '50% of target', fill: '#ffb300', fontSize: 10, position: 'insideTopRight' }}
          />
        )}
        <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.pnl >= 0 ? '#00ff7f' : '#ff3b5c'} fillOpacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

// ── Win/Loss donut ────────────────────────────────────────────────────────────

function WinLossChart({ winCount, totalTrades }: { winCount: number; totalTrades: number }) {
  const lossCount = totalTrades - winCount
  const data = [
    { name: 'Wins',   value: winCount  },
    { name: 'Losses', value: lossCount },
  ]
  const COLORS = ['#00ff7f', '#ff3b5c']
  const OPACITY = [0.85, 0.75]

  return (
    <>
      <ResponsiveContainer width="100%" height={160}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={52}
            outerRadius={72}
            dataKey="value"
            stroke="transparent"
            paddingAngle={2}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i]} fillOpacity={OPACITY[i]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: '#1a1b2e',
              border: '1px solid #4a4a6a',
              borderRadius: 8,
              fontSize: 13,
              padding: '6px 12px',
              boxShadow: '0 4px 16px rgba(0,0,0,0.6)',
            }}
            labelStyle={{ display: 'none' }}
            itemStyle={{ color: '#e5e7eb', fontWeight: 600 }}
            formatter={(v: number, n: string) => [`${v} trades`, n]}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex justify-center gap-6 text-[11px] -mt-2">
        <span className="flex items-center gap-[5px]">
          <span className="w-[8px] h-[8px] rounded-full bg-pos-text inline-block" />
          <span className="text-pos-text font-semibold">{winCount}</span>
          <span className="text-text-tertiary">wins</span>
        </span>
        <span className="flex items-center gap-[5px]">
          <span className="w-[8px] h-[8px] rounded-full bg-neg-text inline-block" />
          <span className="text-neg-text font-semibold">{lossCount}</span>
          <span className="text-text-tertiary">losses</span>
        </span>
      </div>
    </>
  )
}

// ── Payoff chart (CSS bars — no recharts) ────────────────────────────────────

function PayoffChart({
  avgWin, avgLoss, winRate,
}: { avgWin: number; avgLoss: number; winRate: number }) {
  const absLoss = Math.abs(avgLoss)
  const max = Math.max(avgWin, absLoss)
  const ev  = winRate * avgWin + (1 - winRate) * avgLoss

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-baseline justify-between mb-[6px]">
          <span className="text-[11px] text-text-secondary">Avg Win</span>
          <span className="text-[13px] text-pos-text font-semibold font-mono">${avgWin.toFixed(0)}</span>
        </div>
        <div className="h-[5px] bg-bg-sunken rounded-full overflow-hidden">
          <div className="h-full bg-pos-text/80 rounded-full transition-all"
            style={{ width: `${(avgWin / max) * 100}%` }} />
        </div>
      </div>
      <div>
        <div className="flex items-baseline justify-between mb-[6px]">
          <span className="text-[11px] text-text-secondary">Avg Loss</span>
          <span className="text-[13px] text-neg-text font-semibold font-mono">-${absLoss.toFixed(0)}</span>
        </div>
        <div className="h-[5px] bg-bg-sunken rounded-full overflow-hidden">
          <div className="h-full bg-neg-text/80 rounded-full transition-all"
            style={{ width: `${(absLoss / max) * 100}%` }} />
        </div>
      </div>
      <div className="flex items-center justify-between pt-2 border-t border-border-subtle">
        <span className="text-[11px] text-text-tertiary">Expected value / trade</span>
        <span className={`text-[13px] font-semibold font-mono ${ev >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>
          {ev >= 0 ? `+$${ev.toFixed(2)}` : `-$${Math.abs(ev).toFixed(2)}`}
        </span>
      </div>
    </div>
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
    <div className={`bg-bg-surface border border-border-subtle border-l-[3px] ${cfg.border} rounded-lg overflow-hidden`}>
      {/* Header */}
      <div className="px-4 pt-4 pb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-[13px] font-semibold text-text-primary leading-tight">{ev.firm_name}</div>
          <div className="text-[11px] text-text-tertiary font-mono mt-1">{ev.firm_id}</div>
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
const CHART_BULL = '#00c8b4'
const CHART_BEAR = '#e05c72'
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
        ctx.strokeStyle = 'rgba(0,200,180,0.12)'; ctx.lineWidth = 4
        ctx.beginPath(); ctx.moveTo(cursorX, 0); ctx.lineTo(cursorX, CH); ctx.stroke()
        ctx.strokeStyle = 'rgba(0,200,180,0.65)'; ctx.lineWidth = 1
        ctx.beginPath(); ctx.moveTo(cursorX, 0); ctx.lineTo(cursorX, CH); ctx.stroke()

        // % pill — just right of cursor
        const label = `${Math.round(cp)}%`
        ctx.font = 'bold 10.5px "SF Mono","Fira Code",monospace'
        const tw = ctx.measureText(label).width
        const px = cursorX + 5
        ctx.fillStyle = 'rgba(0,28,24,0.85)'
        ctx.strokeStyle = 'rgba(0,200,180,0.35)'; ctx.lineWidth = 1
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
                  style={active ? { boxShadow: '0 0 0 4px rgba(0,200,180,0.15), 0 0 12px rgba(0,200,180,0.45)' } : undefined}
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

function FailureBanner({ run }: { run: Run }) {
  const guidance = FAILURE_GUIDANCE[run.status] ?? FAILURE_GUIDANCE.failed_unknown
  return (
    <div className="bg-neg-muted border border-neg-text/30 rounded-lg px-4 py-4">
      <div className="flex items-start gap-3">
        <AlertTriangle size={15} className="text-neg-text flex-shrink-0 mt-[1px]" />
        <div>
          <div className="text-[13px] font-semibold text-neg-text mb-1">Run failed — {run.status}</div>
          {run.error_message && (
            <div className="text-[12px] font-mono text-neg-text/80 mb-3 whitespace-pre-wrap break-all">
              {run.error_message}
            </div>
          )}
          <div className="text-[12px] text-text-secondary">{guidance}</div>
        </div>
      </div>
    </div>
  )
}

// ── Logs section ──────────────────────────────────────────────────────────────

function LogsSection({ runId, autoExpand, isRunning }: { runId: string; autoExpand: boolean; isRunning: boolean }) {
  const [open, setOpen] = useState(autoExpand)
  const { data: log, isFetching } = useRunLog(open ? runId : null, 200, isRunning)

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-[13px] text-text-secondary hover:text-text-primary transition-colors"
      >
        <span className="font-medium">Run logs</span>
        {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {open && (
        <div className="border-t border-border-subtle">
          {isFetching && !log ? (
            <div className="px-4 py-3 text-[12px] text-text-tertiary">Loading…</div>
          ) : log ? (
            <pre className="px-4 py-3 text-[11px] font-mono text-text-secondary leading-[1.6] overflow-x-auto whitespace-pre-wrap max-h-[400px] overflow-y-auto">
              {log}
            </pre>
          ) : (
            <div className="px-4 py-3 text-[12px] text-text-tertiary">No log available.</div>
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

const STATUS_BADGE: Record<string, string> = {
  complete:          'bg-pos-muted text-pos-text',
  running:           'bg-accent-muted text-accent',
  failed_timeout:    'bg-neg-muted text-neg-text',
  failed_unknown:    'bg-neg-muted text-neg-text',
  failed_cancelled:  'bg-warn-muted text-warn-text',
}

function StatusBadge({ status }: { status: string }) {
  const isFailed = status.startsWith('failed')
  const label    = isFailed ? 'failed' : status
  const cls      = STATUS_BADGE[status] ?? 'bg-warn-muted text-warn-text'
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

// ── Page ──────────────────────────────────────────────────────────────────────

export function BacktestDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate  = useNavigate()
  const { data: run, isLoading } = useBacktestRun(runId ?? null)
  const { data: progress }       = useLabProgress()
  const stopBacktest             = useStopBacktest()

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

  return (
    <div>
      <button
        onClick={() => navigate('/backtests')}
        className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
      >
        <ArrowLeft size={14} /> Backtests
      </button>

      {isLoading && <Skeleton />}

      {run && (
        <div className="space-y-8">
          {/* ── Header ───────────────────────────────────────────────────── */}
          <div>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-h1 font-semibold leading-tight">
                  {run.strategy_name || run.strategy_id}
                </h1>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-[13px] text-text-secondary">
                  <span className="font-mono text-accent">{run.instrument}</span>
                  <span className="text-text-tertiary">·</span>
                  <span>{fmtDate(run.start_date)} → {fmtDate(run.end_date)}</span>
                  <span className="text-text-tertiary">·</span>
                  <span>{run.bar_value}m bars</span>
                  {run.commission_per_side > 0 && (
                    <>
                      <span className="text-text-tertiary">·</span>
                      <span>${run.commission_per_side}/side commission</span>
                    </>
                  )}
                </div>
              </div>
              {!isRunning && <StatusBadge status={run.status} />}
            </div>
          </div>

          {/* ── Banners ───────────────────────────────────────────────────── */}
          {isRunning && <RunningBanner pct={runPct} message={runMessage} startedAt={runStartedAt} onStop={() => stopBacktest.mutate(run.run_id)} />}
          {isFailed  && <FailureBanner run={run} />}

          {/* ── Firm evaluations (verdict first) ──────────────────────────── */}
          {isComplete && run.evaluations.length > 0 && (
            <div>
              <SectionLabel>Evaluation</SectionLabel>
              <div className={`grid gap-3 ${
                run.evaluations.length === 1
                  ? 'grid-cols-1 max-w-sm'
                  : 'grid-cols-1 sm:grid-cols-2'
              }`}>
                {run.evaluations.map(ev => (
                  <EvalCard key={ev.eval_id} ev={ev} />
                ))}
              </div>
            </div>
          )}

          {/* ── Performance KPIs (why) ────────────────────────────────────── */}
          {isComplete && (
            <div>
              <SectionLabel>Performance</SectionLabel>
              <KpiGrid run={run} fallback={fallback} />
            </div>
          )}

          {/* ── Trade breakdown (visual) ──────────────────────────────────── */}
          {isComplete && run.win_count != null && run.trade_count != null && (
            <div>
              <SectionLabel>Trade breakdown</SectionLabel>
              <div className="bg-bg-surface border border-border-subtle rounded-lg px-6 py-5">
                {run.avg_win != null && run.avg_loss != null ? (
                  <div className="grid grid-cols-[1fr_1px_1fr] gap-6">
                    <div>
                      <div className="text-[10px] text-text-secondary uppercase tracking-[0.6px] mb-2">Win / Loss Split</div>
                      <WinLossChart winCount={run.win_count} totalTrades={run.trade_count} />
                    </div>
                    <div className="bg-border-subtle" />
                    <div className="flex flex-col justify-center py-2">
                      <div className="text-[10px] text-text-secondary uppercase tracking-[0.6px] mb-5">Payoff Comparison</div>
                      <PayoffChart avgWin={run.avg_win} avgLoss={run.avg_loss} winRate={run.win_rate ?? 0} />
                    </div>
                  </div>
                ) : (
                  <div className="max-w-xs">
                    <div className="text-[10px] text-text-secondary uppercase tracking-[0.6px] mb-2">Win / Loss Split</div>
                    <WinLossChart winCount={run.win_count} totalTrades={run.trade_count} />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Equity curve ──────────────────────────────────────────────── */}
          {isComplete && (
            <div>
              <SectionLabel>Equity curve</SectionLabel>
              <div className="bg-bg-surface border border-border-subtle rounded-lg px-3 py-4">
                <EquityCurveChart data={run.equity_curve} />
              </div>
            </div>
          )}

          {/* ── Daily P&L bars ────────────────────────────────────────────── */}
          {isComplete && (
            <div>
              <SectionLabel>Daily P&amp;L</SectionLabel>
              <div className="bg-bg-surface border border-border-subtle rounded-lg px-3 py-4">
                <DailyPnlChart data={run.daily_pnl} netPnl={run.net_pnl} />
              </div>
            </div>
          )}

          {/* ── Logs ─────────────────────────────────────────────────────── */}
          {runId && <LogsSection runId={runId} autoExpand={isFailed || isRunning} isRunning={isRunning} />}
        </div>
      )}
    </div>
  )
}
