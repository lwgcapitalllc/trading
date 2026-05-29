import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, ChevronDown, ChevronUp, AlertTriangle,
  CheckCircle, XCircle, Minus,
} from 'lucide-react'
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import { useBacktestRun, useRunLog } from '@/hooks/useLab'
import { StatCard } from '@/components/StatCard'
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

// ── Status helpers ────────────────────────────────────────────────────────────

const VERDICT_CONFIG = {
  PASS:    { label: 'PASS',    bg: 'bg-pos-muted',  text: 'text-pos-text',  border: 'border-pos-text/30',  Icon: CheckCircle },
  WARN:    { label: 'WARN',    bg: 'bg-warn-muted', text: 'text-warn-text', border: 'border-warn-text/30', Icon: Minus       },
  DISCARD: { label: 'DISCARD', bg: 'bg-neg-muted',  text: 'text-neg-text',  border: 'border-neg-text/30',  Icon: XCircle     },
} as const

// ── Evaluation card ───────────────────────────────────────────────────────────

function EvalCard({ ev }: { ev: EvaluationDetail }) {
  const cfg = VERDICT_CONFIG[ev.verdict as keyof typeof VERDICT_CONFIG] ?? VERDICT_CONFIG.DISCARD
  const { Icon } = cfg

  return (
    <div className={`bg-bg-surface border border-border-subtle rounded-lg p-4 border-l-2 ${cfg.border}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[14px] font-semibold">{ev.firm_name}</div>
          <div className="text-[11px] text-text-tertiary font-mono mt-[1px]">{ev.firm_id}</div>
        </div>
        <span className={`flex items-center gap-1 px-[10px] py-[3px] rounded-pill text-[11px] font-bold uppercase tracking-[0.5px] ${cfg.bg} ${cfg.text}`}>
          <Icon size={11} />
          {cfg.label}
        </span>
      </div>

      {/* Checks */}
      <div className="space-y-[6px]">
        <EvalRow
          label="Drawdown"
          pass={ev.drawdown_pass}
          value={`$${ev.firm_max_loss_eod.toLocaleString()} limit`}
        />
        {ev.firm_profit_target > 0 && (
          <EvalRow
            label="Target"
            pass={ev.target_pass}
            value={`$${ev.firm_profit_target.toLocaleString()} target`}
          />
        )}
        {ev.consistency_pass != null && ev.firm_consistency_pct != null && (
          <EvalRow
            label="Consistency"
            pass={ev.consistency_pass}
            value={`≤ ${ev.firm_consistency_pct}% largest day`}
            extra={ev.largest_day_share_pct != null
              ? `${ev.largest_day_share_pct.toFixed(1)}% actual`
              : undefined}
          />
        )}
        {ev.simulated_eval_days != null && (
          <div className="text-[11px] text-text-tertiary mt-1">
            {ev.simulated_eval_days} simulated eval days
          </div>
        )}
      </div>

      {/* Notes */}
      {ev.notes && (
        <p className="text-[11px] text-text-tertiary mt-3 leading-[1.5]">{ev.notes}</p>
      )}
    </div>
  )
}

function EvalRow({
  label, pass, value, extra,
}: { label: string; pass: boolean; value: string; extra?: string }) {
  return (
    <div className="flex items-center gap-2 text-[12px]">
      {pass
        ? <CheckCircle size={12} className="text-pos-text flex-shrink-0" />
        : <XCircle    size={12} className="text-neg-text flex-shrink-0" />
      }
      <span className="text-text-secondary w-24 flex-shrink-0">{label}</span>
      <span className={pass ? 'text-pos-text' : 'text-neg-text'}>{value}</span>
      {extra && <span className="text-text-tertiary">({extra})</span>}
    </div>
  )
}

// ── KPI grid ──────────────────────────────────────────────────────────────────

function KpiGrid({ run }: { run: Run }) {
  const pnlSign = run.net_pnl == null ? 'neutral' : run.net_pnl >= 0 ? 'pos' : 'neg'
  const ddSign  = 'neg'

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <StatCard
        label="Net P&L"
        value={dollar(run.net_pnl, true)}
        subVariant={pnlSign as 'pos' | 'neg' | 'neutral'}
        sub={run.win_rate != null ? `${pct(run.win_rate)} win rate` : undefined}
      />
      <StatCard
        label="Max Drawdown"
        value={dollar(run.max_drawdown)}
        subVariant={ddSign}
        sub="peak-to-trough"
      />
      <StatCard
        label="Win Rate"
        value={pct(run.win_rate)}
        sub={run.trade_count != null ? `${run.trade_count} trades` : undefined}
      />
      <StatCard
        label="Profit Factor"
        value={run.profit_factor != null ? run.profit_factor.toFixed(2) : '—'}
        sub={run.avg_win != null && run.avg_loss != null
          ? `avg ${dollar(run.avg_win, true)} / ${dollar(run.avg_loss)}`
          : undefined}
      />
      <StatCard
        label="Trade Count"
        value={run.trade_count ?? '—'}
        sub={run.avg_trade_duration_min != null
          ? `avg ${run.avg_trade_duration_min.toFixed(0)} min/trade`
          : undefined}
      />
      <StatCard
        label="Sharpe"
        value={run.sharpe != null ? run.sharpe.toFixed(2) : '—'}
        sub={run.sortino != null ? `Sortino ${run.sortino.toFixed(2)}` : undefined}
      />
      <StatCard
        label="Worst Day"
        value={dollar(run.worst_day_pnl)}
        subVariant="neg"
      />
      <StatCard
        label="Worst Streak"
        value={run.worst_losing_streak != null ? `${run.worst_losing_streak} L` : '—'}
        sub="consecutive losses"
      />
    </div>
  )
}

// ── Equity curve ──────────────────────────────────────────────────────────────

function EquityCurveChart({ data }: { data: EquityPoint[] }) {
  if (!data.length) {
    return (
      <div className="h-[280px] flex items-center justify-center text-text-tertiary text-[13px]">
        No equity curve data
      </div>
    )
  }

  const min = Math.min(...data.map(d => d.equity))
  const max = Math.max(...data.map(d => d.equity))
  const pad = (max - min) * 0.05 || 100

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
        <XAxis
          dataKey="index"
          tick={{ fill: '#6b7280', fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => (data.length > 100 ? (v % 50 === 0 ? String(v) : '') : String(v))}
        />
        <YAxis
          domain={[min - pad, max + pad]}
          tick={{ fill: '#6b7280', fontSize: 11 }}
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
        <Line
          type="monotone"
          dataKey="equity"
          stroke="#00e5ff"
          strokeWidth={1.5}
          dot={false}
          activeDot={{ r: 3, fill: '#00e5ff' }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

// ── Daily P&L chart ───────────────────────────────────────────────────────────

function DailyPnlChart({ data, netPnl }: { data: DailyPnlPoint[]; netPnl: number | null }) {
  if (!data.length) {
    return (
      <div className="h-[320px] flex items-center justify-center text-text-tertiary text-[13px]">
        No daily P&L data
      </div>
    )
  }

  // Horizontal reference line at 50% of total profit (shows consistent vs lumpy gains)
  const halfTarget = netPnl != null && netPnl > 0 ? netPnl * 0.5 : null

  // Truncate date labels when there are many days
  const labelEvery = data.length > 60 ? 30 : data.length > 30 ? 10 : 1

  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }} barCategoryGap="20%">
        <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fill: '#6b7280', fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(d: string, i: number) =>
            i % labelEvery === 0 ? chartDateLabel(d) : ''
          }
        />
        <YAxis
          tick={{ fill: '#6b7280', fontSize: 11 }}
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
        {halfTarget != null && (
          <ReferenceLine
            y={halfTarget}
            stroke="#ffb30060"
            strokeDasharray="4 4"
            label={{ value: '50% target', fill: '#ffb300', fontSize: 10, position: 'insideTopRight' }}
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

// ── Running banner ────────────────────────────────────────────────────────────

function RunningBanner({ pct }: { pct: number }) {
  return (
    <div className="bg-accent-muted border border-accent/30 rounded-lg px-4 py-3 flex items-center gap-3 mb-6">
      <span className="w-2 h-2 rounded-full bg-accent animate-pulse flex-shrink-0" />
      <div className="flex-1">
        <div className="text-[13px] font-medium text-accent">Backtest running…</div>
        <div className="mt-2 h-[3px] bg-bg-surface-2 rounded-full overflow-hidden">
          <div
            className="h-full bg-accent rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      <span className="text-accent font-mono tabular-nums text-[13px]">{pct}%</span>
    </div>
  )
}

// ── Failure banner ────────────────────────────────────────────────────────────

const FAILURE_GUIDANCE: Record<string, string> = {
  failed_timeout:
    'The VPS agent stopped responding mid-run. Verify NT8 is running and the Strategy Analyzer is open in the RDP session. Re-run when ready.',
  failed_unknown:
    'An unexpected error occurred. Check the logs below and the VPS agent log for details.',
}

function FailureBanner({ run }: { run: Run }) {
  const guidance = FAILURE_GUIDANCE[run.status] ?? FAILURE_GUIDANCE.failed_unknown
  return (
    <div className="bg-neg-muted border border-neg-text/30 rounded-lg px-4 py-4 mb-6">
      <div className="flex items-start gap-3">
        <AlertTriangle size={16} className="text-neg-text flex-shrink-0 mt-[1px]" />
        <div>
          <div className="text-[13px] font-semibold text-neg-text mb-1">
            Run failed — {run.status}
          </div>
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
      <div className="h-[280px] bg-bg-surface rounded-lg" />
      <div className="h-[320px] bg-bg-surface rounded-lg" />
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function BacktestDetail() {
  const { runId } = useParams<{ runId: string }>()
  const navigate  = useNavigate()
  const { data: run, isLoading } = useBacktestRun(runId ?? null)

  const isRunning = run?.status === 'running'
  const isFailed  = run?.status.startsWith('failed') ?? false
  const isComplete = run?.status === 'complete'

  return (
    <div>
      {/* Back nav */}
      <button
        onClick={() => navigate('/backtests')}
        className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
      >
        <ArrowLeft size={14} /> Backtests
      </button>

      {isLoading && <Skeleton />}

      {run && (
        <div className="space-y-8">
          {/* ── Header ──────────────────────────────────────────────────────── */}
          <div>
            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-h1 font-semibold leading-tight">
                  {run.strategy_name || run.strategy_id}
                </h1>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-[13px] text-text-secondary">
                  <span className="font-mono">{run.instrument}</span>
                  <span className="text-text-tertiary">·</span>
                  <span>{fmtDate(run.start_date)} → {fmtDate(run.end_date)}</span>
                  <span className="text-text-tertiary">·</span>
                  <span>{run.bar_value}m bars</span>
                  {run.commission_per_side && (
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

          {/* ── Running banner ───────────────────────────────────────────────── */}
          {isRunning && <RunningBanner pct={0} />}

          {/* ── Failure banner ───────────────────────────────────────────────── */}
          {isFailed && <FailureBanner run={run} />}

          {/* ── Evaluations ─────────────────────────────────────────────────── */}
          {run.evaluations.length > 0 && (
            <div>
              <SectionLabel>Per-firm evaluation</SectionLabel>
              <div className={`grid gap-3 ${
                run.evaluations.length === 1
                  ? 'grid-cols-1 max-w-sm'
                  : run.evaluations.length === 2
                  ? 'grid-cols-1 sm:grid-cols-2'
                  : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-2'
              }`}>
                {run.evaluations.map(ev => (
                  <EvalCard key={ev.eval_id} ev={ev} />
                ))}
              </div>
            </div>
          )}

          {/* ── KPI grid or failure substitute ──────────────────────────────── */}
          {isComplete && (
            <div>
              <SectionLabel>Performance KPIs</SectionLabel>
              <KpiGrid run={run} />
            </div>
          )}

          {/* ── Charts (only when data present) ─────────────────────────────── */}
          {isComplete && run.daily_pnl.length > 0 && (
            <div>
              <SectionLabel>Daily P&amp;L</SectionLabel>
              <div className="bg-bg-surface border border-border-subtle rounded-lg px-3 py-4">
                <DailyPnlChart data={run.daily_pnl} netPnl={run.net_pnl} />
              </div>
            </div>
          )}

          {isComplete && run.equity_curve.length > 0 && (
            <div>
              <SectionLabel>Equity curve</SectionLabel>
              <div className="bg-bg-surface border border-border-subtle rounded-lg px-3 py-4">
                <EquityCurveChart data={run.equity_curve} />
              </div>
            </div>
          )}

          {/* ── Logs ────────────────────────────────────────────────────────── */}
          {runId && (
            <LogsSection runId={runId} autoExpand={isFailed} />
          )}
        </div>
      )}
    </div>
  )
}

// ── Status badge (header) ─────────────────────────────────────────────────────

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
    <span className={`inline-flex items-center gap-1 px-3 py-[4px] rounded-pill text-[12px] font-semibold uppercase tracking-[0.4px] flex-shrink-0 ${cls}`}>
      {status === 'running' && (
        <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse" />
      )}
      {label}
    </span>
  )
}
