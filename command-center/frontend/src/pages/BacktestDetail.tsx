import { useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, ChevronDown, ChevronUp, AlertTriangle,
  CheckCircle, XCircle, Minus,
} from 'lucide-react'
import {
  AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import { useBacktestRun, useRunLog } from '@/hooks/useLab'
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

// ── MetricCard ────────────────────────────────────────────────────────────────

function MetricCard({ label, value, valueCls = '', sub, subCls = 'text-text-tertiary' }: {
  label: string
  value: React.ReactNode
  valueCls?: string
  sub?: React.ReactNode
  subCls?: string
}) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg px-[15px] py-[14px]">
      <div className="text-[10px] text-text-secondary uppercase tracking-[0.6px]">{label}</div>
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
        sub={
          run.avg_win != null && run.avg_loss != null
            ? `avg ${dollar(run.avg_win, true)} win · ${dollar(run.avg_loss)} loss`
            : run.trade_count != null ? `${run.trade_count} trades` : undefined
        }
      />
      <MetricCard
        label="Max Drawdown"
        value={dollar(run.max_drawdown)}
        valueCls="text-neg-text"
        sub="largest equity decline from peak"
      />
      <MetricCard
        label="Win Rate"
        value={pct(run.win_rate)}
        valueCls={winRateCls(run.win_rate)}
        sub={winRateLabel(run.win_rate)}
      />
      <MetricCard
        label="Profit Factor"
        value={run.profit_factor != null ? run.profit_factor.toFixed(2) : '—'}
        valueCls={pfCls(run.profit_factor)}
        sub={pfLabel(run.profit_factor)}
      />
      <MetricCard
        label="Trade Count"
        value={run.trade_count ?? '—'}
        sub={
          run.win_count != null && run.trade_count != null
            ? (
              <span>
                <span className="text-pos-text">{run.win_count}W</span>
                <span className="text-text-tertiary"> · </span>
                <span className="text-neg-text">{run.trade_count - run.win_count}L</span>
              </span>
            )
            : run.avg_trade_duration_min != null
            ? `avg ${run.avg_trade_duration_min.toFixed(0)} min / trade`
            : undefined
        }
      />
      <MetricCard
        label="Sharpe (annlzd)"
        value={sharpe != null ? sharpe.toFixed(2) : '—'}
        valueCls={sharpeCls(sharpe)}
        sub={sharpeLabel(sharpe, sharpeEst)}
      />
      <MetricCard
        label="Worst Day"
        value={dollar(worstDay)}
        valueCls={worstDay != null && worstDay < 0 ? 'text-neg-text' : ''}
        sub={worstDay == null ? 'largest single-day loss' : 'single-day low'}
      />
      <MetricCard
        label="Worst Streak"
        value={worstStreak != null ? `${worstStreak} L` : '—'}
        valueCls={worstStreakCls(worstStreak)}
        sub="consecutive losing days"
      />
    </div>
  )
}

// ── Equity curve ──────────────────────────────────────────────────────────────

function EquityCurveChart({ data }: { data: EquityPoint[] }) {
  if (!data.length) {
    return (
      <div className="h-[320px] flex items-center justify-center text-text-tertiary text-[13px]">
        No equity curve data
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
      <div className="h-[260px] flex items-center justify-center text-text-tertiary text-[13px]">
        No daily P&L data
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

function RunningBanner({ pct: p }: { pct: number }) {
  return (
    <div className="bg-accent-muted border border-accent/30 rounded-lg px-4 py-3 flex items-center gap-3">
      <span className="w-2 h-2 rounded-full bg-accent animate-pulse flex-shrink-0" />
      <div className="flex-1">
        <div className="text-[13px] font-medium text-accent">Backtest running…</div>
        <div className="mt-2 h-[3px] bg-bg-surface-2 rounded-full overflow-hidden">
          <div className="h-full bg-accent rounded-full transition-all duration-500" style={{ width: `${p}%` }} />
        </div>
      </div>
      <span className="text-accent font-mono tabular-nums text-[13px]">{p}%</span>
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

function LogsSection({ runId, autoExpand }: { runId: string; autoExpand: boolean }) {
  const [open, setOpen] = useState(autoExpand)
  const { data: log, isFetching } = useRunLog(open ? runId : null)

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
  complete:       'bg-pos-muted text-pos-text',
  running:        'bg-accent-muted text-accent',
  failed_timeout: 'bg-neg-muted text-neg-text',
  failed_unknown: 'bg-neg-muted text-neg-text',
}

function StatusBadge({ status }: { status: string }) {
  const isFailed = status.startsWith('failed')
  const label    = isFailed ? 'failed' : status
  const cls      = STATUS_BADGE[status] ?? 'bg-warn-muted text-warn-text'
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-[4px] rounded-full text-[12px] font-semibold uppercase tracking-[0.4px] flex-shrink-0 ${cls}`}>
      {status === 'running' && <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse" />}
      {label}
    </span>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function BacktestDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate  = useNavigate()
  const { data: run, isLoading } = useBacktestRun(runId ?? null)

  const fallback = useMemo(
    () => computeFallbacks(run?.daily_pnl ?? []),
    [run?.daily_pnl],
  )

  const isRunning  = run?.status === 'running'
  const isFailed   = run?.status.startsWith('failed') ?? false
  const isComplete = run?.status === 'complete'

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
              <StatusBadge status={run.status} />
            </div>
          </div>

          {/* ── Banners ───────────────────────────────────────────────────── */}
          {isRunning && <RunningBanner pct={0} />}
          {isFailed  && <FailureBanner run={run} />}

          {/* ── Performance metrics ───────────────────────────────────────── */}
          {isComplete && (
            <div>
              <SectionLabel>Performance</SectionLabel>
              <KpiGrid run={run} fallback={fallback} />
            </div>
          )}

          {/* ── Equity curve (hero) ───────────────────────────────────────── */}
          {isComplete && run.equity_curve.length > 0 && (
            <div>
              <SectionLabel>Equity curve — trade-by-trade</SectionLabel>
              <div className="bg-bg-surface border border-border-subtle rounded-lg px-3 py-4">
                <EquityCurveChart data={run.equity_curve} />
              </div>
            </div>
          )}

          {/* ── Daily P&L bars ────────────────────────────────────────────── */}
          {isComplete && run.daily_pnl.length > 0 && (
            <div>
              <SectionLabel>Daily P&amp;L</SectionLabel>
              <div className="bg-bg-surface border border-border-subtle rounded-lg px-3 py-4">
                <DailyPnlChart data={run.daily_pnl} netPnl={run.net_pnl} />
              </div>
            </div>
          )}

          {/* ── Firm evaluations ──────────────────────────────────────────── */}
          {run.evaluations.length > 0 && (
            <div>
              <SectionLabel>Per-firm evaluation</SectionLabel>
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

          {/* ── Logs ─────────────────────────────────────────────────────── */}
          {runId && <LogsSection runId={runId} autoExpand={isFailed} />}
        </div>
      )}
    </div>
  )
}
