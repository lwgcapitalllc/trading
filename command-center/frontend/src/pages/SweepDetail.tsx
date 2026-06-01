import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, Loader2, XCircle, AlertTriangle, RotateCcw, Square, Trash2 } from 'lucide-react'
import { WorthinessBadge } from '@/components/WorthinessBadge'
import { useSweep, useDeleteSweep, useRetrySweep, useCancelSweep, useRetryBacktest, useRunningVpsJob, useFirms, useReevaluateSweep } from '@/hooks/useLab'
import type { BacktestSummary, SweepDetail as Sweep } from '@/types'

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtDuration(seconds: number): string {
  if (seconds < 60)  return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

function firmShortName(firmId: string): string {
  const parts = firmId.split('_')
  if (parts.length < 3) return firmId
  const brandMap: Record<string, string> = { lucidflex: 'LF', apex: 'Apex', tradeify: 'TF' }
  const brand = brandMap[parts[0]] ?? parts[0].slice(0, 2).toUpperCase()
  const size  = (parts[1] ?? '').toUpperCase()
  const tier  = parts[2] === 'eval' ? 'Eval' : parts[2] === 'funded' ? 'Funded' : (parts[2] ?? '')
  return `${brand}${size} ${tier}`
}

function firmChipCls(firmId: string): string {
  if (firmId.includes('_eval'))   return 'bg-warn-muted text-warn-text border border-warn-text/20'
  if (firmId.includes('_funded')) return 'bg-pos-muted text-pos-text border border-pos-text/20'
  return 'bg-bg-surface border border-border-subtle text-text-tertiary'
}

// ── Live elapsed timer ────────────────────────────────────────────────────────

function useElapsed(startIso: string | null, endIso: string | null, running: boolean) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!startIso) return
    const start = new Date(startIso).getTime()
    if (!running && endIso) {
      setElapsed(Math.round((new Date(endIso).getTime() - start) / 1000))
      return
    }
    const tick = () => setElapsed(Math.round((Date.now() - start) / 1000))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [startIso, endIso, running])
  return elapsed
}

// ── Progress card ─────────────────────────────────────────────────────────────

function ProgressCard({ sweep, onCancel, onRetry, cancelling, retrying, jobBlocked }: {
  sweep: Sweep
  onCancel: () => void
  onRetry: () => void
  cancelling: boolean
  retrying: boolean
  jobBlocked: boolean
}) {
  const isRunning   = sweep.status === 'running'
  const isCancelled = sweep.status === 'failed_cancelled'
  const isComplete  = sweep.status === 'complete'

  const total         = sweep.total_instruments
  const completeCount = sweep.completed_instruments
  const failedCount   = sweep.runs.filter(r => r.status.startsWith('failed')).length

  const completePct = total > 0 ? (completeCount / total) * 100 : 0
  const failedPct   = total > 0 ? (failedCount   / total) * 100 : 0
  const overallPct  = Math.round(completePct + failedPct)

  const hasFailures  = failedCount > 0
  const allFailed    = failedCount === total && total > 0
  const failingBadly = isRunning && failedCount > 0

  const elapsed = useElapsed(sweep.created_at, sweep.completed_at, isRunning)

  const statusLabel = isRunning ? 'Running' : isComplete ? 'Complete' : isCancelled ? 'Cancelled' : allFailed ? 'Failed' : hasFailures ? 'Partial' : 'Failed'
  const borderCls = isComplete && !hasFailures ? 'border-pos-text/20 bg-pos-muted/30'
    : allFailed || isCancelled ? 'border-neg-text/20 bg-neg-muted'
    : hasFailures ? 'border-warn-text/25 bg-warn-muted/20'
    : 'border-border-default bg-bg-surface'

  return (
    <div className={`rounded-xl border px-6 py-5 ${borderCls}`}>
      {/* Top row: status left, elapsed + actions right */}
      <div className="flex items-start justify-between gap-6">
        {/* Left: status + progress bar + counts */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            {isRunning   && <Loader2      size={14} className="text-accent animate-spin flex-shrink-0" />}
            {isComplete  && !hasFailures  && <CheckCircle2  size={14} className="text-pos-text flex-shrink-0" />}
            {isComplete  && hasFailures   && <AlertTriangle size={14} className="text-warn-text flex-shrink-0" />}
            {!isRunning  && !isComplete   && <XCircle       size={14} className="text-neg-text flex-shrink-0" />}
            <span className={`text-[13px] font-semibold ${
              isRunning ? 'text-accent'
              : isComplete && !hasFailures ? 'text-pos-text'
              : isComplete && hasFailures  ? 'text-warn-text'
              : 'text-neg-text'
            }`}>
              {statusLabel}
            </span>
            {isRunning && <span className="text-[11px] text-text-tertiary">· auto-refreshing</span>}
          </div>

          <div className="w-full bg-bg-sunken rounded-full h-[7px] overflow-hidden mb-2 flex">
            <div className="h-full bg-pos-text transition-all duration-700" style={{ width: `${completePct}%` }} />
            <div className="h-full bg-neg-text/70 transition-all duration-700" style={{ width: `${failedPct}%` }} />
          </div>

          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-4 text-[12px]">
              <span className="text-text-secondary">
                <span className="font-mono font-semibold text-pos-text">{completeCount}</span>
                <span className="text-text-tertiary"> complete</span>
              </span>
              {failedCount > 0 && (
                <span className="text-text-secondary">
                  <span className="font-mono font-semibold text-neg-text">{failedCount}</span>
                  <span className="text-text-tertiary"> failed</span>
                </span>
              )}
            </div>
            <span className="text-[12px] font-mono font-semibold tabular-nums text-text-secondary">
              {overallPct}%
            </span>
          </div>
        </div>

        {/* Right: elapsed + action buttons */}
        <div className="flex-shrink-0 flex flex-col items-end gap-3">
          <div className="text-right">
            <div className="text-[11px] text-text-tertiary mb-0.5">
              {isComplete ? 'Duration' : isRunning ? 'Elapsed' : 'Ran for'}
            </div>
            <div className="text-[20px] font-mono font-semibold text-text-primary tabular-nums leading-none">
              {fmtDuration(elapsed)}
            </div>
          </div>
          <div className="flex flex-col gap-2 items-end">
            {isRunning && (
              <button onClick={onCancel} disabled={cancelling}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium border border-neg-text/30 text-neg-text hover:bg-neg-muted disabled:opacity-50 transition-colors">
                <Square size={11} />
                {cancelling ? 'Cancelling…' : 'Cancel'}
              </button>
            )}
            {hasFailures && (
              <button onClick={onRetry} disabled={retrying || jobBlocked}
                title={jobBlocked ? 'Another NT8 job is running — wait for it to finish' : undefined}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium border border-accent/30 text-accent hover:bg-accent/10 disabled:opacity-50 transition-colors">
                <RotateCcw size={11} className={retrying ? 'animate-spin' : ''} />
                {retrying ? (isRunning ? 'Queuing…' : 'Starting…') : `Retry ${failedCount} failed`}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Instrument tracker — full width below */}
      <div className="mt-4 pt-4 border-t border-border-subtle flex flex-wrap gap-1.5">
        {sweep.runs.map(r => {
          const done   = r.status === 'complete'
          const failed = r.status.startsWith('failed')
          return (
            <span
              key={r.run_id}
              className={`inline-flex items-center gap-[5px] px-2 py-[3px] rounded text-[11px] font-mono border ${
                done   ? 'border-pos-text/25 bg-pos-muted/20 text-pos-text' :
                failed ? 'border-neg-text/25 bg-neg-muted text-neg-text' :
                         'border-border-subtle text-text-tertiary'
              }`}
            >
              {done   && <CheckCircle2 size={9} className="flex-shrink-0" />}
              {failed && <XCircle      size={9} className="flex-shrink-0" />}
              {!done && !failed && <Loader2 size={9} className={`flex-shrink-0 ${isRunning ? 'animate-spin text-accent' : ''}`} />}
              {r.instrument}
            </span>
          )
        })}
      </div>

      {/* Footer note or failure warning */}
      {failingBadly && (
        <div className="mt-3 flex items-start gap-2">
          <AlertTriangle size={13} className="text-warn-text flex-shrink-0 mt-[1px]" />
          <p className="text-[12px] text-warn-text">
            {failedCount} instrument{failedCount !== 1 ? 's are' : ' is'} failing.
            Check that NT8 is open with the Strategy Analyzer window active on the VPS.
          </p>
        </div>
      )}
      {!failingBadly && isRunning && (
        <p className="text-[11px] text-text-tertiary mt-3">
          Each instrument runs as a separate backtest on the VPS. Safe to close — results are saved as each run completes.
        </p>
      )}
    </div>
  )
}

// ── Failed runs table ─────────────────────────────────────────────────────────

function FailedRunsTable({ runs, navigate, retryRun, jobBlocked }: {
  runs: BacktestSummary[]
  navigate: ReturnType<typeof useNavigate>
  retryRun: ReturnType<typeof useRetryBacktest>
  jobBlocked: boolean
}) {
  if (runs.length === 0) return null
  return (
    <div>
      <h2 className="text-[11px] font-semibold text-neg-text uppercase tracking-[0.7px] mb-3">
        Failed runs ({runs.length})
      </h2>
      <div className="bg-bg-surface border border-border-subtle rounded-xl overflow-hidden overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-border-subtle bg-bg-sunken">
              <th className="text-left px-3 py-2 text-text-tertiary font-medium">Instrument</th>
              <th className="text-left px-3 py-2 text-text-tertiary font-medium">Status</th>
              <th className="text-left px-3 py-2 text-text-tertiary font-medium">Error</th>
              <th className="px-3 py-2 w-24" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {runs.map(run => (
              <tr
                key={run.run_id}
                onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
                className="hover:bg-bg-hover cursor-pointer transition-colors"
              >
                <td className="px-3 py-[9px] font-mono font-semibold text-text-primary">{run.instrument}</td>
                <td className="px-3 py-[9px] font-mono text-neg-text text-[11px]">{run.status}</td>
                <td className="px-3 py-[9px] text-text-tertiary text-[11px] max-w-[360px] truncate">
                  {run.error_message ?? '—'}
                </td>
                <td className="px-3 py-[9px]">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={(e) => { e.stopPropagation(); retryRun.mutate(run.run_id) }}
                      disabled={retryRun.isPending || jobBlocked}
                      title={jobBlocked ? 'Another NT8 job is running — wait for it to finish' : 'Retry this run'}
                      className="p-[4px] rounded text-text-tertiary hover:text-accent hover:bg-accent/10 disabled:opacity-40 transition-colors"
                    >
                      <RotateCcw size={11} className={retryRun.isPending && retryRun.variables === run.run_id ? 'animate-spin' : ''} />
                    </button>
                    <span className="text-[11px] text-accent">View →</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Results table ─────────────────────────────────────────────────────────────

function ResultsTable({ runs, navigate }: {
  runs: BacktestSummary[]
  navigate: ReturnType<typeof useNavigate>
}) {
  const sorted = [...runs].sort((a, b) => {
    const order: Record<string, number> = { TIER_1_STRESS_TEST: 0, TIER_2_OPTIMIZE: 1, TIER_3_DISCARD: 2 }
    const ao = order[a.worthiness?.tier ?? ''] ?? 3
    const bo = order[b.worthiness?.tier ?? ''] ?? 3
    if (ao !== bo) return ao - bo
    return (b.net_pnl ?? -Infinity) - (a.net_pnl ?? -Infinity)
  })

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-xl overflow-hidden overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border-subtle bg-bg-sunken">
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">Instrument</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">P&L</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">Max DD</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">Profit Factor</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">Trades</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">Score</th>
            <th className="px-3 py-2 w-16" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {sorted.map(run => {
            const pnlCls = (run.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'
            return (
              <tr
                key={run.run_id}
                onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
                className="hover:bg-bg-hover cursor-pointer transition-colors"
              >
                <td className="px-3 py-[9px] font-mono font-semibold text-text-primary">{run.instrument}</td>
                <td className={`px-3 py-[9px] font-mono tabular-nums ${pnlCls}`}>
                  {run.net_pnl != null ? `${run.net_pnl >= 0 ? '+' : ''}$${Math.abs(run.net_pnl).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'}
                </td>
                <td className="px-3 py-[9px] font-mono tabular-nums text-neg-text">
                  {run.max_drawdown != null ? `$${run.max_drawdown.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'}
                </td>
                <td className="px-3 py-[9px] font-mono tabular-nums">
                  {run.profit_factor?.toFixed(2) ?? '—'}
                </td>
                <td className="px-3 py-[9px] tabular-nums text-text-secondary">
                  {run.trade_count ?? '—'}
                </td>
                <td className="px-3 py-[9px]">
                  <WorthinessBadge worthiness={run.worthiness} />
                </td>
                <td className="px-3 py-[9px] text-right">
                  <span className="text-[11px] text-accent">View →</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function SweepDetail() {
  const { sweepId }  = useParams<{ sweepId: string }>()
  const navigate     = useNavigate()
  const { data: sweep, isLoading } = useSweep(sweepId ?? null)
  const deleteSweep    = useDeleteSweep()
  const retrySweep     = useRetrySweep()
  const cancelSweep    = useCancelSweep()
  const retryRun       = useRetryBacktest()
  const reevalSweep    = useReevaluateSweep()
  const { data: firms }          = useFirms()
  const { data: runningJob }     = useRunningVpsJob()
  const jobBlocked = !!runningJob?.running

  const [confirmDelete, setConfirmDelete] = useState(false)
  const [evalFirmId, setEvalFirmId]       = useState('')

  const isRunning    = sweep?.status === 'running'
  const completeRuns = sweep?.runs.filter(r => r.status === 'complete') ?? []
  const failedRuns   = sweep?.runs.filter(r => r.status.startsWith('failed')) ?? []

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <button
          onClick={() => navigate('/backtests?tab=sweeps')}
          className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary transition-colors"
        >
          <ArrowLeft size={14} /> Sweeps
        </button>
        {sweep && !isRunning && (
          <button
            onClick={() => setConfirmDelete(true)}
            className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium text-text-tertiary hover:text-neg-text hover:bg-neg-muted border border-transparent hover:border-neg-text/20 transition-colors"
          >
            <Trash2 size={12} />
            Delete
          </button>
        )}
      </div>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onClick={e => { if (e.target === e.currentTarget) setConfirmDelete(false) }}>
          <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[400px] shadow-2xl">
            <div className="px-5 py-4 border-b border-border-subtle">
              <div className="text-[15px] font-semibold">Delete this sweep?</div>
            </div>
            <div className="px-5 py-4">
              <p className="text-[13px] text-text-secondary">
                All {sweep?.total_instruments} instrument runs, their evaluations, and result files will be permanently removed. This cannot be undone.
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle">
              <button onClick={() => setConfirmDelete(false)} className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">
                Cancel
              </button>
              <button
                onClick={() => deleteSweep.mutate(sweepId!, { onSuccess: () => navigate('/backtests?tab=sweeps') })}
                disabled={deleteSweep.isPending}
                className="px-4 py-[7px] rounded-md text-[13px] font-medium bg-neg-muted text-neg-text border border-neg/40 hover:bg-neg/15 disabled:opacity-50 transition-colors"
              >
                {deleteSweep.isPending ? 'Deleting…' : 'Delete sweep'}
              </button>
            </div>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="animate-pulse space-y-4">
          <div className="h-7 w-72 bg-bg-surface rounded" />
          <div className="h-4 w-48 bg-bg-surface rounded" />
          <div className="h-[120px] bg-bg-surface rounded-xl" />
        </div>
      )}

      {sweep && (
        <div className="space-y-6">
          {/* Header */}
          <div>
            <h1 className="text-h1 font-semibold leading-tight mb-2">
              {sweep.strategy_name || sweep.strategy_id}
            </h1>
            <div className="flex flex-wrap gap-1.5">
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold bg-accent/10 text-accent border border-accent/20">
                {sweep.total_instruments}-instrument Sweep
              </span>
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-secondary font-mono">
                {fmtDate(sweep.start_date)} → {fmtDate(sweep.end_date)}
              </span>
              {sweep.firm_ids.map(f => (
                <span key={f} className={`inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono ${firmChipCls(f)}`}>
                  {firmShortName(f)}
                </span>
              ))}
            </div>
          </div>

          {/* Progress */}
          <ProgressCard
            sweep={sweep}
            onCancel={() => cancelSweep.mutate(sweepId!)}
            onRetry={() => retrySweep.mutate(sweepId!)}
            cancelling={cancelSweep.isPending}
            retrying={retrySweep.isPending}
            jobBlocked={jobBlocked}
          />

          {/* Re-evaluate prompt — shown when sweep has no firm evaluations */}
          {completeRuns.length > 0 && sweep.firm_ids.length === 0 && !isRunning && (
            <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-warn-muted/30 border border-warn-text/20">
              <AlertTriangle size={14} className="text-warn-text flex-shrink-0" />
              <span className="text-[12px] text-warn-text flex-1">
                This sweep was run without firm evaluation — Score and Challenge will be empty.
              </span>
              <select
                value={evalFirmId}
                onChange={e => setEvalFirmId(e.target.value)}
                className="bg-bg-sunken border border-border-subtle rounded px-2 py-[5px] text-[12px] focus:outline-none focus:border-accent min-w-[140px]"
              >
                <option value="">Select firm…</option>
                {firms?.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
              <button
                onClick={() => {
                  if (!evalFirmId || !sweepId) return
                  reevalSweep.mutate({ sweepId, firm_ids: [evalFirmId] })
                }}
                disabled={!evalFirmId || reevalSweep.isPending}
                className="px-3 py-[5px] rounded text-[12px] font-semibold bg-accent text-bg-base hover:opacity-90 disabled:opacity-40 transition-opacity"
              >
                {reevalSweep.isPending ? 'Scoring…' : 'Score'}
              </button>
            </div>
          )}

          {/* Results table */}
          {completeRuns.length > 0 && (
            <div>
              <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">
                {isRunning
                  ? `Results so far — ${completeRuns.length} of ${sweep.total_instruments} complete`
                  : `Results — ${completeRuns.length} of ${sweep.total_instruments} instruments`}
              </h2>
              <ResultsTable runs={completeRuns} navigate={navigate} />
            </div>
          )}

          {/* Failed runs */}
          <FailedRunsTable runs={failedRuns} navigate={navigate} retryRun={retryRun} jobBlocked={jobBlocked} />
        </div>
      )}
    </div>
  )
}
