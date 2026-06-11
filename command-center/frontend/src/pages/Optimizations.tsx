import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sliders, ChevronRight, Trash2 } from 'lucide-react'
import { useOptimizations, useDeleteOptimization, useBacktestRuns } from '@/hooks/useLab'
import { EmptyState } from '@/components/EmptyState'
import { ConfirmDeleteModal, RunsTableSkeleton, fmtOptStatus } from '@/pages/Backtests'

export function Optimizations() {
  const navigate  = useNavigate()
  const deleteOpt = useDeleteOptimization()
  const { data: opts, isLoading } = useOptimizations()
  const { data: allRuns } = useBacktestRuns()
  const hasRuns = (allRuns?.filter(r => (!r.optimization_id || r.status === 'running') && !r.sweep_id).length ?? 0) > 0
  const [deleteOptId, setDeleteOptId] = useState<string | null>(null)

  return (
    <div>
      <div className="flex items-end justify-between gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Optimizations</h1>
        {opts && opts.length > 0 && (
          <span className="text-[13px] text-text-secondary">
            {`${opts.length} optimization${opts.length !== 1 ? 's' : ''}`}
          </span>
        )}
      </div>

      {isLoading ? (
        <RunsTableSkeleton />
      ) : !opts?.length ? (
        <EmptyState
          icon={<Sliders size={20} />}
          title="No optimizations yet"
          description={hasRuns
            ? 'Click "Optimize" on a completed run to start a native optimization.'
            : 'Run a backtest first, then click "Optimize" on a completed run to start a native optimization.'}
          action={
            <button
              onClick={() => navigate(hasRuns ? '/backtests?tab=runs' : '/strategies')}
              className="flex items-center gap-1.5 bg-accent text-bg-base font-semibold text-[12px] px-3.5 py-2 rounded-md hover:opacity-90 transition-opacity"
            >
              {hasRuns ? 'View Runs' : 'Browse Strategies'}
              <ChevronRight size={14} />
            </button>
          }
        />
      ) : (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Strategy</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Instrument</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Firm</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Mode</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Method</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Progress</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Status</th>
                <th className="px-3 py-3 w-20" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {opts.map(opt => {
                const st = fmtOptStatus(opt.status)
                return (
                  <tr
                    key={opt.optimization_id}
                    onClick={() => navigate(`/optimizations/${opt.optimization_id}`)}
                    className="hover:bg-bg-hover cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-medium">{opt.strategy_id}</td>
                    <td className="px-4 py-3 font-mono text-text-secondary">{opt.instrument}</td>
                    <td className="px-4 py-3 text-text-secondary text-[12px]">{opt.ruleset_id ?? '—'}</td>
                    <td className="px-4 py-3 capitalize text-text-secondary">{opt.mode}</td>
                    <td className="px-4 py-3 capitalize text-text-secondary">{opt.search_method}</td>
                    <td className="px-4 py-3 font-mono tabular-nums text-text-secondary">{opt.completed_runs}/{opt.estimated_runs}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-[2px] rounded-pill text-[11px] font-semibold uppercase tracking-[0.4px] ${st.cls}`}>{st.label}</span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1 justify-end">
                        <button
                          onClick={e => { e.stopPropagation(); setDeleteOptId(opt.optimization_id) }}
                          disabled={opt.status === 'running'}
                          className="p-[5px] rounded text-text-tertiary hover:text-neg-text hover:bg-neg-muted transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                          title={opt.status === 'running' ? 'Cancel first, then delete' : 'Delete optimization'}
                        >
                          <Trash2 size={13} />
                        </button>
                        <ChevronRight size={14} className="text-text-tertiary" />
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {deleteOptId && (
        <ConfirmDeleteModal
          count={1}
          onConfirm={() => deleteOpt.mutate(deleteOptId, { onSuccess: () => setDeleteOptId(null), onSettled: () => setDeleteOptId(null) })}
          onCancel={() => setDeleteOptId(null)}
          isPending={deleteOpt.isPending}
          customMessage="This will permanently delete the optimization and all its child runs, evaluations, and result files."
        />
      )}
    </div>
  )
}
