import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sliders, ChevronRight, Trash2 } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import { useOptimizations, useBacktestRuns } from '@/hooks/useLab'
import { EmptyState } from '@/components/EmptyState'
import { ConfirmDeleteModal, RunsTableSkeleton, fmtOptStatus } from '@/pages/Backtests'

export function Optimizations() {
  const navigate  = useNavigate()
  const qc = useQueryClient()
  const { data: opts, isLoading } = useOptimizations()
  const { data: allRuns } = useBacktestRuns()
  const hasRuns = (allRuns?.filter(r => (!r.optimization_id || r.status === 'running') && !r.sweep_id).length ?? 0) > 0

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [showBulkConfirm, setShowBulkConfirm] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)

  // Running optimizations can't be deleted — cancel first. They're not selectable.
  const selectable = opts?.filter(o => o.status !== 'running') ?? []
  const toggleSelect = (id: string) =>
    setSelectedIds(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  const toggleSelectAll = () => {
    if (selectedIds.size === selectable.length) setSelectedIds(new Set())
    else setSelectedIds(new Set(selectable.map(o => o.optimization_id)))
  }
  const allChecked = selectable.length > 0 && selectedIds.size === selectable.length

  const handleBulkDelete = async () => {
    setBulkDeleting(true)
    const ids = Array.from(selectedIds)
    try {
      const results = await Promise.allSettled(ids.map(id => api.delete<void>(`/optimizations/${id}`)))
      const failed = results.filter(r => r.status === 'rejected').length
      qc.invalidateQueries({ queryKey: ['lab', 'optimizations'] })
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
      if (failed === 0) toast.success(`${ids.length} optimization${ids.length !== 1 ? 's' : ''} deleted`)
      else toast.error(`${ids.length - failed} deleted, ${failed} failed`)
      setSelectedIds(new Set())
      setShowBulkConfirm(false)
    } finally {
      setBulkDeleting(false)
    }
  }

  return (
    <div>
      <div className="flex items-end justify-between gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Optimizations</h1>
        <div className="flex items-center gap-3">
          {selectedIds.size > 0 && (
            <button
              onClick={() => setShowBulkConfirm(true)}
              className="flex items-center gap-1 px-[10px] py-[4px] rounded-md text-[12px] font-medium bg-neg-muted text-neg-text border border-neg-text/20 hover:bg-neg-text/20 transition-colors"
            >
              <Trash2 size={11} />
              Delete {selectedIds.size}
            </button>
          )}
          {opts && opts.length > 0 && (
            <span className="text-[13px] text-text-secondary">
              {`${opts.length} optimization${opts.length !== 1 ? 's' : ''}`}
            </span>
          )}
        </div>
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
                <th className="px-3 py-3 w-8">
                  <input type="checkbox" checked={allChecked} onChange={toggleSelectAll} className="w-3.5 h-3.5 rounded accent-accent cursor-pointer" />
                </th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Strategy</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Instrument</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Firm</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Mode</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Method</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Progress</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Status</th>
                <th className="px-3 py-3 w-10" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {opts.map(opt => {
                const st = fmtOptStatus(opt.status)
                const isRunning = opt.status === 'running'
                return (
                  <tr
                    key={opt.optimization_id}
                    onClick={() => navigate(`/optimizations/${opt.optimization_id}`)}
                    className="hover:bg-bg-hover cursor-pointer transition-colors"
                  >
                    <td className="px-3 py-3" onClick={e => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(opt.optimization_id)}
                        onChange={() => toggleSelect(opt.optimization_id)}
                        disabled={isRunning}
                        title={isRunning ? 'Cancel first, then delete' : undefined}
                        className="w-3.5 h-3.5 rounded accent-accent cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
                      />
                    </td>
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
                      <ChevronRight size={14} className="text-text-tertiary" />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {showBulkConfirm && (
        <ConfirmDeleteModal
          count={selectedIds.size}
          onConfirm={handleBulkDelete}
          onCancel={() => setShowBulkConfirm(false)}
          isPending={bulkDeleting}
          customMessage="This will permanently delete the selected optimizations and all their child runs, evaluations, and result files."
        />
      )}
    </div>
  )
}
