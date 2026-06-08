import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Download, CheckCircle2, Loader2, XCircle, AlertTriangle, RotateCcw, Square, Trash2, Activity } from 'lucide-react'
import { WorthinessBadge } from '@/components/WorthinessBadge'
import { useOptimization, useCancelOptimization, useRetryOptimization, useDeleteOptimization, useRetryBacktest, useRunningVpsJob } from '@/hooks/useLab'
import { useRunningStressLock, useStressTests } from '@/hooks/useStressTests'
import type { BacktestSummary, OptimizationDetail as Opt } from '@/types'

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

function fmtSearchMethod(m: string) {
  if (m === 'brute')   return 'Brute Force'
  if (m === 'genetic') return 'Genetic'
  return 'Auto'
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

// ── CSV export ────────────────────────────────────────────────────────────────

function exportCsv(runs: BacktestSummary[], paramKeys: string[]) {
  const headers = ['rank', ...paramKeys, 'net_pnl', 'max_drawdown', 'profit_factor', 'win_rate', 'trade_count', 'sharpe', 'worthiness']
  const rows = runs
    .filter(r => r.status === 'complete')
    .sort((a, b) => (b.profit_factor ?? -Infinity) - (a.profit_factor ?? -Infinity))
    .map((r, i) => [
      i + 1,
      ...paramKeys.map(k => r.params?.[k] ?? ''),
      r.net_pnl ?? '', r.max_drawdown ?? '', r.profit_factor ?? '',
      r.win_rate ?? '', r.trade_count ?? '', r.sharpe ?? '',
      r.worthiness?.tier ?? '',
    ].join(','))
  const csv   = [headers.join(','), ...rows].join('\n')
  const blob  = new Blob([csv], { type: 'text/csv' })
  const url   = URL.createObjectURL(blob)
  const a     = document.createElement('a')
  a.href = url; a.download = 'optimization_results.csv'; a.click()
  URL.revokeObjectURL(url)
}

// ── Progress card ─────────────────────────────────────────────────────────────

function ProgressCard({ opt, onCancel, onRetry, cancelling, retrying, jobBlocked }: {
  opt: Opt
  onCancel: () => void
  onRetry: () => void
  cancelling: boolean
  retrying: boolean
  jobBlocked: boolean
}) {
  const isRunning  = opt.status === 'running'
  const isCancelled = opt.status === 'failed_cancelled'
  const isComplete = opt.status === 'complete'

  const completeCount = opt.runs.filter(r => r.status === 'complete').length
  const failedCount   = opt.runs.filter(r => r.status.startsWith('failed')).length
  const total         = opt.estimated_runs

  const completePct = total > 0 ? (completeCount / total) * 100 : 0
  const failedPct   = total > 0 ? (failedCount   / total) * 100 : 0
  const overallPct  = Math.round(completePct + failedPct)

  const hasFailures   = failedCount > 0
  const allFailed     = failedCount === total && total > 0
  const failingBadly  = isRunning && failedCount > 0

  const elapsed = useElapsed(opt.created_at, opt.completed_at ?? null, isRunning)

  const statusLabel = isRunning ? 'Running' : isComplete ? 'Complete' : isCancelled ? 'Cancelled' : 'Failed'
  const borderCls   = isComplete && !hasFailures ? 'border-accent/20 bg-accent/5'
    : allFailed || isCancelled ? 'border-neg-text/20 bg-neg-muted'
    : hasFailures && isComplete ? 'border-warn-text/25 bg-warn-muted/20'
    : 'border-border-default bg-bg-surface'

  return (
    <div className={`rounded-xl border px-6 py-5 ${borderCls}`}>
      <div className="flex items-start justify-between gap-6">
        {/* Left: status + progress */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            {isRunning   && <Loader2     size={14} className="text-accent animate-spin flex-shrink-0" />}
            {isComplete  && !hasFailures && <CheckCircle2 size={14} className="text-accent flex-shrink-0" />}
            {isComplete  && hasFailures  && <AlertTriangle size={14} className="text-warn-text flex-shrink-0" />}
            {!isRunning  && !isComplete  && <XCircle size={14} className="text-neg-text flex-shrink-0" />}
            <span className={`text-[13px] font-semibold ${
              isRunning ? 'text-accent'
              : isComplete && !hasFailures ? 'text-accent'
              : isComplete && hasFailures  ? 'text-warn-text'
              : 'text-neg-text'
            }`}>
              {statusLabel}
            </span>
            {isRunning && <span className="text-[11px] text-text-tertiary">· auto-refreshing</span>}
          </div>

          {/* Segmented progress bar */}
          <div className="w-full bg-bg-sunken rounded-full h-[7px] overflow-hidden mb-2 flex">
            <div
              className="h-full bg-accent transition-all duration-700"
              style={{ width: `${completePct}%` }}
            />
            <div
              className="h-full bg-neg-text/70 transition-all duration-700"
              style={{ width: `${failedPct}%` }}
            />
          </div>

          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-4 text-[12px]">
              <span className="text-text-secondary">
                <span className="font-mono font-semibold text-accent">{completeCount}</span>
                <span className="text-text-tertiary"> passed</span>
              </span>
              {failedCount > 0 && (
                <span className="text-text-secondary">
                  <span className="font-mono font-semibold text-neg-text">{failedCount}</span>
                  <span className="text-text-tertiary"> failed</span>
                </span>
              )}
              <span className="text-text-tertiary">
                of {total} combinations
              </span>
            </div>
            <span className="text-[12px] font-mono font-semibold tabular-nums text-text-secondary">
              {overallPct}%
            </span>
          </div>

          {/* Inline failure warning while running */}
          {failingBadly && (
            <div className="mt-3 pt-3 border-t border-border-subtle flex items-start gap-2">
              <AlertTriangle size={13} className="text-warn-text flex-shrink-0 mt-[1px]" />
              <p className="text-[12px] text-warn-text">
                {failedCount} run{failedCount !== 1 ? 's are' : ' is'} failing.
                Check that NT8 is open with the Strategy Analyzer window active on the VPS.
                You can cancel now and retry once NT8 is ready.
              </p>
            </div>
          )}

          {!failingBadly && isRunning && (
            <p className="text-[11px] text-text-tertiary mt-3 pt-3 border-t border-border-subtle">
              Each combination runs as a separate backtest on the VPS (up to 4 at a time). Safe to close — results are saved as each run completes.
            </p>
          )}
        </div>

        {/* Right: timing + actions */}
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
              <button
                onClick={onCancel}
                disabled={cancelling}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium border border-neg-text/30 text-neg-text hover:bg-neg-muted disabled:opacity-50 transition-colors"
              >
                <Square size={11} />
                {cancelling ? 'Cancelling…' : 'Cancel'}
              </button>
            )}
            {hasFailures && !isRunning && (
              <button
                onClick={onRetry}
                disabled={retrying || jobBlocked}
                title={jobBlocked ? 'Another NT8 job is running — wait for it to finish' : undefined}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium border border-accent/30 text-accent hover:bg-accent/10 disabled:opacity-50 transition-colors"
              >
                <RotateCcw size={11} className={retrying ? 'animate-spin' : ''} />
                {retrying ? 'Starting…' : `Retry ${failedCount} failed`}
              </button>
            )}
            {hasFailures && isRunning && (
              <button
                onClick={onRetry}
                disabled={retrying || jobBlocked}
                title={jobBlocked ? 'Another NT8 job is running — wait for it to finish' : undefined}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium border border-accent/30 text-accent hover:bg-accent/10 disabled:opacity-50 transition-colors"
              >
                <RotateCcw size={11} className={retrying ? 'animate-spin' : ''} />
                {retrying ? 'Queuing…' : `Retry ${failedCount} failed`}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Failed runs table ─────────────────────────────────────────────────────────

function FailedRunsTable({ runs, sweptKeys, navigate, retryRun, jobBlocked }: {
  runs: BacktestSummary[]
  sweptKeys: string[]
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
              {sweptKeys.map(k => (
                <th key={k} className="text-left px-3 py-2 text-text-tertiary font-medium font-mono">{k}</th>
              ))}
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
                {sweptKeys.map(k => (
                  <td key={k} className="px-3 py-[9px] font-mono font-semibold text-text-primary">
                    {String(run.params?.[k] ?? '—')}
                  </td>
                ))}
                <td className="px-3 py-[9px] font-mono text-neg-text text-[11px]">
                  {run.status}
                </td>
                <td className="px-3 py-[9px] text-text-tertiary text-[11px] max-w-[320px] truncate">
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

function ResultsTable({ runs, sweptKeys, navigate, bestRunId }: {
  runs: BacktestSummary[]
  sweptKeys: string[]
  navigate: ReturnType<typeof useNavigate>
  bestRunId?: string
}) {
  const sorted = [...runs].sort((a, b) => (b.profit_factor ?? -Infinity) - (a.profit_factor ?? -Infinity))
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-xl overflow-hidden overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border-subtle bg-bg-sunken">
            <th className="text-left px-3 py-2 text-text-tertiary font-medium w-10">#</th>
            {sweptKeys.map(k => (
              <th key={k} className="text-left px-3 py-2 text-text-tertiary font-medium font-mono">{k}</th>
            ))}
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">P&L</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">Max DD</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">PF</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">Trades</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">Score</th>
            <th className="px-3 py-2 w-16" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {sorted.map((run, i) => {
            const isBest  = bestRunId ? run.run_id === bestRunId : i === 0
            const pnlCls  = (run.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'
            return (
              <tr
                key={run.run_id}
                onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
                className={`hover:bg-bg-hover cursor-pointer transition-colors ${isBest ? 'border-l-2 border-l-gold-text bg-gold-muted/10' : ''}`}
              >
                <td className="px-3 py-[9px] tabular-nums">
                  {isBest
                    ? <span className="text-gold-text font-bold">★</span>
                    : <span className="text-text-tertiary">{i + 1}</span>}
                </td>
                {sweptKeys.map(k => (
                  <td key={k} className={`px-3 py-[9px] font-mono font-semibold ${isBest ? 'text-gold-text' : 'text-text-primary'}`}>
                    {String(run.params?.[k] ?? '—')}
                  </td>
                ))}
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

export function OptimizationDetail() {
  const { optimizationId } = useParams<{ optimizationId: string }>()
  const navigate            = useNavigate()
  const { data: opt, isLoading } = useOptimization(optimizationId ?? null)
  const cancelOpt  = useCancelOptimization()
  const retryOpt   = useRetryOptimization()
  const deleteOpt  = useDeleteOptimization()
  const retryRun   = useRetryBacktest()
  const { data: runningJob } = useRunningVpsJob()
  const jobBlocked = !!runningJob?.nt8?.running

  const { data: stressLock } = useRunningStressLock()
  const stressRunIds = useMemo(() => new Set(stressLock?.run_ids ?? []), [stressLock])
  const bestRunId = opt?.best_run_id ?? undefined
  const hasRunningStress = !!bestRunId && stressRunIds.has(bestRunId)
  const { data: bestRunStressTests } = useStressTests(hasRunningStress ? bestRunId : undefined)
  const latestStress = bestRunStressTests?.find(s => !s.status.startsWith('failed') && s.status !== 'complete')

  const [confirmDelete, setConfirmDelete] = useState(false)

  const paramKeys = opt ? Object.keys(opt.param_grid) : []
  const sweptKeys = paramKeys.filter(k => {
    const spec = opt?.param_grid[k]
    return Array.isArray(spec) ? spec.length > 1 : typeof spec === 'object' && spec !== null
  })

  const isRunning    = opt?.status === 'running'
  const completeRuns = opt?.runs.filter(r => r.status === 'complete') ?? []
  const failedRuns   = opt?.runs.filter(r => r.status.startsWith('failed')) ?? []

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <button
          onClick={() => navigate('/backtests?tab=optimizations')}
          className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary transition-colors"
        >
          <ArrowLeft size={14} /> Optimizations
        </button>
        {opt && !isRunning && (
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
              <div className="text-[15px] font-semibold">Delete this optimization?</div>
            </div>
            <div className="px-5 py-4">
              <p className="text-[13px] text-text-secondary">
                All {opt?.estimated_runs} child runs, their evaluations, and result files will be permanently removed. This cannot be undone.
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle">
              <button onClick={() => setConfirmDelete(false)} className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">
                Cancel
              </button>
              <button
                onClick={() => deleteOpt.mutate(optimizationId!, { onSuccess: () => navigate('/backtests?tab=optimizations') })}
                disabled={deleteOpt.isPending}
                className="px-4 py-[7px] rounded-md text-[13px] font-medium bg-neg-muted text-neg-text border border-neg/40 hover:bg-neg/15 disabled:opacity-50 transition-colors"
              >
                {deleteOpt.isPending ? 'Deleting…' : 'Delete optimization'}
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

      {opt && (
        <div className="space-y-6">
          {/* Header */}
          <div>
            <h1 className="text-h1 font-semibold leading-tight mb-2">
              {opt.strategy_name || opt.strategy_id}
            </h1>
            <div className="flex flex-wrap gap-1.5">
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono bg-accent/10 text-accent border border-accent/20">
                {opt.instrument}
              </span>
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-secondary font-mono">
                {fmtDate(opt.start_date)} → {fmtDate(opt.end_date)}
              </span>
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium font-mono bg-bg-surface border border-border-subtle text-text-secondary">
                {opt.mode} · {fmtSearchMethod(opt.search_method)}
              </span>
              {opt.ruleset_id ? (
                <span className={`inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono ${firmChipCls(opt.ruleset_id)}`}>
                  {firmShortName(opt.ruleset_id)}
                </span>
              ) : (
                <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium font-mono bg-bg-surface border border-border-subtle text-text-tertiary">
                  Raw PF
                </span>
              )}
              {opt.regime_filter && (
                <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium font-mono bg-bg-surface border border-border-subtle text-text-tertiary">
                  Regime: {opt.regime_filter.replace('_', ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase())}
                </span>
              )}
            </div>
          </div>

          {/* Progress */}
          <ProgressCard
            opt={opt}
            onCancel={() => cancelOpt.mutate(optimizationId!)}
            onRetry={() => retryOpt.mutate(optimizationId!)}
            cancelling={cancelOpt.isPending}
            retrying={retryOpt.isPending}
            jobBlocked={jobBlocked}
          />

          {latestStress && (
            <button
              onClick={() => navigate(`/stress-tests/${latestStress.stress_test_id}`)}
              className="w-full flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg border border-accent/20 bg-accent/5 text-left hover:bg-accent/10 transition-colors"
            >
              <div className="flex items-center gap-2 text-sm text-accent">
                <Activity size={14} className="animate-pulse flex-shrink-0" />
                Stress test in progress on winner run
              </div>
              <span className="text-xs text-text-tertiary">View →</span>
            </button>
          )}

          {/* Results table — shows while running and when complete */}
          {completeRuns.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px]">
                  {isRunning
                    ? `Results so far — ${completeRuns.length} of ${opt.estimated_runs} complete`
                    : `Results — ${completeRuns.length} of ${opt.estimated_runs} combinations`}
                </h2>
                <button
                  onClick={() => exportCsv(opt.runs, paramKeys)}
                  className="flex items-center gap-2 px-3 py-[5px] rounded-md text-[11px] text-text-secondary hover:text-text-primary bg-bg-surface border border-border-subtle hover:border-border-default transition-colors"
                >
                  <Download size={12} />
                  Export CSV
                </button>
              </div>
              <ResultsTable
                runs={completeRuns}
                sweptKeys={sweptKeys}
                navigate={navigate}
                bestRunId={opt.best_run_id ?? undefined}
              />
            </div>
          )}

          {/* Failed runs — debugging info, always below results */}
          <FailedRunsTable runs={failedRuns} sweptKeys={sweptKeys} navigate={navigate} retryRun={retryRun} jobBlocked={jobBlocked} />
        </div>
      )}
    </div>
  )
}
