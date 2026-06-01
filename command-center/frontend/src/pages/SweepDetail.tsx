import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Layers, Trash2 } from 'lucide-react'
import { WorthinessBadge } from '@/components/WorthinessBadge'
import { useSweep, useDeleteSweep } from '@/hooks/useLab'

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtMoney(n: number | null) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  return `${n < 0 ? '-' : '+'}$${abs.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

const STATUS_CLS: Record<string, string> = {
  complete: 'bg-pos-muted text-pos-text',
  running:  'bg-accent/10 text-accent',
}

export function SweepDetail() {
  const { sweepId } = useParams<{ sweepId: string }>()
  const navigate    = useNavigate()
  const { data: sweep, isLoading, refetch, isFetching } = useSweep(sweepId ?? null)
  const deleteSweep = useDeleteSweep()

  const [confirmDelete, setConfirmDelete] = useState(false)

  const isRunning = sweep && sweep.completed_instruments < sweep.total_instruments

  // Auto-refresh while sweep is still running
  // (handled by refetchInterval in useSweep hook)

  return (
    <div>
      <button
        onClick={() => navigate('/backtests?tab=sweeps')}
        className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
      >
        <ArrowLeft size={14} /> Sweeps
      </button>

      {isLoading && (
        <div className="animate-pulse space-y-4">
          <div className="h-6 w-56 bg-bg-surface rounded" />
          <div className="h-4 w-80 bg-bg-surface rounded" />
          <div className="h-[200px] bg-bg-surface rounded-lg" />
        </div>
      )}

      {sweep && (
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <Layers size={18} className="text-accent" />
                <h1 className="text-h1 font-semibold">Instrument Sweep</h1>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-[13px] text-text-secondary">
                <span className="font-mono text-text-primary">{sweep.strategy_name || sweep.strategy_id}</span>
                <span className="text-text-tertiary">·</span>
                <span>{fmtDate(sweep.start_date)} → {fmtDate(sweep.end_date)}</span>
                <span className="text-text-tertiary">·</span>
                <span className="font-mono text-[11px] text-text-tertiary">{sweepId}</span>
              </div>
            </div>
            <div className="flex items-center gap-3 flex-shrink-0">
              <div className="text-right">
                <div className="text-[13px] font-semibold text-text-primary">
                  {sweep.completed_instruments} / {sweep.total_instruments} complete
                </div>
                {isRunning && (
                  <button
                    onClick={() => refetch()}
                    disabled={isFetching}
                    className="text-[11px] text-accent hover:underline mt-1 disabled:opacity-50"
                  >
                    {isFetching ? 'Refreshing…' : 'Refresh'}
                  </button>
                )}
              </div>
              {!isRunning && (
                <button
                  onClick={() => setConfirmDelete(true)}
                  className="p-[6px] rounded text-text-tertiary hover:text-neg-text hover:bg-neg-muted transition-colors"
                  title="Delete sweep"
                >
                  <Trash2 size={15} />
                </button>
              )}
            </div>
          </div>

          {confirmDelete && (
            <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
              <div className="bg-bg-surface border border-border-subtle rounded-lg p-6 max-w-sm w-full space-y-4">
                <h2 className="text-[15px] font-semibold text-text-primary">Delete sweep?</h2>
                <p className="text-[13px] text-text-secondary">
                  This will permanently delete the sweep and all its instrument runs, evaluations, and result files.
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={() => setConfirmDelete(false)}
                    className="px-4 py-2 text-[13px] rounded-lg border border-border-subtle hover:bg-bg-hover transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => deleteSweep.mutate(sweepId!, {
                      onSuccess: () => navigate('/backtests?tab=sweeps'),
                    })}
                    disabled={deleteSweep.isPending}
                    className="px-4 py-2 text-[13px] rounded-lg bg-neg-muted text-neg-text hover:opacity-80 transition-opacity disabled:opacity-50"
                  >
                    {deleteSweep.isPending ? 'Deleting…' : 'Delete'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Progress bar */}
          <div className="w-full bg-bg-surface rounded-full h-[6px] overflow-hidden">
            <div
              className="h-full bg-accent transition-all duration-500"
              style={{ width: `${sweep.total_instruments > 0 ? (sweep.completed_instruments / sweep.total_instruments) * 100 : 0}%` }}
            />
          </div>

          {/* Results table — sorted by worthiness (best first) */}
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Instrument</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Status</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Score</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Net P&L</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max DD</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">PF</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Trades</th>
                  <th className="px-3 py-3 w-20" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {[...sweep.runs]
                  .sort((a, b) => {
                    const order: Record<string, number> = {
                      TIER_1_STRESS_TEST: 0, TIER_2_OPTIMIZE: 1, TIER_3_DISCARD: 2,
                    }
                    const ao = order[a.worthiness?.tier ?? ''] ?? 3
                    const bo = order[b.worthiness?.tier ?? ''] ?? 3
                    if (ao !== bo) return ao - bo
                    return (b.net_pnl ?? -Infinity) - (a.net_pnl ?? -Infinity)
                  })
                  .map(run => {
                    const statusCls = STATUS_CLS[run.status] ?? 'bg-warn-muted text-warn-text'
                    const pnlCls = run.net_pnl == null ? '' : run.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'
                    return (
                      <tr
                        key={run.run_id}
                        onClick={() => run.status === 'complete' && navigate(`/backtests/runs/${run.run_id}`)}
                        className={run.status === 'complete' ? 'hover:bg-bg-hover cursor-pointer' : ''}
                      >
                        <td className="px-4 py-3 font-mono font-medium">{run.instrument}</td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center gap-1 px-2 py-[2px] rounded-pill text-[11px] font-semibold uppercase tracking-[0.4px] ${statusCls}`}>
                            {run.status === 'running' && <span className="w-[5px] h-[5px] rounded-full bg-accent animate-pulse" />}
                            {run.status}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <WorthinessBadge worthiness={run.worthiness} />
                        </td>
                        <td className={`px-4 py-3 font-mono tabular-nums ${pnlCls}`}>
                          {fmtMoney(run.net_pnl)}
                        </td>
                        <td className="px-4 py-3 font-mono tabular-nums text-neg-text">
                          {run.max_drawdown != null ? `$${run.max_drawdown.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'}
                        </td>
                        <td className="px-4 py-3 font-mono tabular-nums text-text-secondary">
                          {run.profit_factor?.toFixed(2) ?? '—'}
                        </td>
                        <td className="px-4 py-3 tabular-nums text-text-secondary">
                          {run.trade_count ?? '—'}
                        </td>
                        <td className="px-3 py-3 text-right">
                          {run.status === 'complete' && (
                            <span className="text-[11px] text-accent hover:underline">View →</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
              </tbody>
            </table>
          </div>

          {/* Firm IDs */}
          {sweep.firm_ids.length > 0 && (
            <p className="text-[11px] text-text-tertiary">
              Evaluated against: {sweep.firm_ids.join(', ')}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
