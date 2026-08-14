import { useState } from 'react'
import { Activity, Trash2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/api/client'
import { useStressTests } from '@/hooks/useStressTests'
import { EmptyState } from '@/components/EmptyState'
import RobustnessGradeBadge from '@/components/RobustnessGradeBadge'
import GradeLegend from '@/components/GradeLegend'
import StickyHeader from '@/components/StickyHeader'
import { ConfirmDeleteModal } from '@/pages/Backtests'

export function StressTests() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: tests, isLoading } = useStressTests()

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [showBulkConfirm, setShowBulkConfirm] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)

  const toggleSelect = (id: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  const toggleSelectAll = () => {
    if (!tests) return
    if (selectedIds.size === tests.length) setSelectedIds(new Set())
    else setSelectedIds(new Set(tests.map((t) => t.stress_test_id)))
  }
  const allChecked = tests != null && tests.length > 0 && selectedIds.size === tests.length

  const handleBulkDelete = async () => {
    setBulkDeleting(true)
    const ids = Array.from(selectedIds)
    try {
      const results = await Promise.allSettled(
        ids.map((id) => api.delete<void>(`/stress-tests/${id}`))
      )
      const failed = results.filter((r) => r.status === 'rejected').length
      qc.invalidateQueries({ queryKey: ['stress-tests'] })
      if (failed === 0)
        toast.success(`${ids.length} stress test${ids.length !== 1 ? 's' : ''} deleted`)
      else toast.error(`${ids.length - failed} deleted, ${failed} failed`)
      setSelectedIds(new Set())
      setShowBulkConfirm(false)
    } finally {
      setBulkDeleting(false)
    }
  }

  return (
    <div>
      <StickyHeader>
        {(scrolled) => (
          <>
            <div
              className={`flex items-center justify-between gap-3 transition-all duration-200 ${scrolled ? 'mb-2.5' : 'mb-[18px]'}`}
            >
              <div className="flex items-center gap-2.5">
                <h1
                  className={`${scrolled ? 'text-[16px]' : 'text-h1'} font-semibold transition-all duration-200`}
                >
                  Stress Tests
                </h1>
                {tests && tests.length > 0 && (
                  <span className="text-[12px] font-semibold font-mono tabular-nums px-2 py-[2px] rounded-full bg-accent/15 text-accent">
                    {tests.length}
                  </span>
                )}
              </div>
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
              </div>
            </div>

            {!isLoading && !!tests?.length && (
              <div className="mb-4">
                <GradeLegend forceCollapsed={scrolled} />
              </div>
            )}
          </>
        )}
      </StickyHeader>

      {isLoading && <div className="p-6 text-text-secondary text-sm">Loading…</div>}

      {!isLoading && !tests?.length && (
        <EmptyState
          icon={<Activity size={22} />}
          title="No stress tests yet"
          description="Open any completed backtest and click 'Stress Test' to run one."
        />
      )}

      {!isLoading && !!tests?.length && (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-left">
                <th className="pb-2 pt-3 px-4 w-8">
                  <input
                    type="checkbox"
                    checked={allChecked}
                    onChange={toggleSelectAll}
                    className="w-3.5 h-3.5 rounded accent-accent cursor-pointer"
                  />
                </th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Grade</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Strategy</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Instrument</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Status</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Worst 1% DD</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Prob Breach</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Prob Pass</th>
                <th className="pb-2 pt-3 pr-4 text-text-tertiary font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {tests.map((t) => (
                <tr
                  key={t.stress_test_id}
                  className="border-b border-border-subtle/50 hover:bg-bg-hover cursor-pointer"
                  onClick={() => navigate(`/stress-tests/${t.stress_test_id}`)}
                >
                  <td className="py-2 px-4" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(t.stress_test_id)}
                      onChange={() => toggleSelect(t.stress_test_id)}
                      className="w-3.5 h-3.5 rounded accent-accent cursor-pointer"
                    />
                  </td>
                  <td className="py-2 pr-4">
                    {t.grade ? (
                      <RobustnessGradeBadge grade={t.grade} />
                    ) : /* A COMPLETED test with no letter is a real outcome — the ruleset states no
                         drawdown limit, and every grade is a statement about drawdown vs a limit.
                         An em-dash made that look identical to a test still running. */
                    t.status === 'complete' ? (
                      <span
                        className="text-text-tertiary text-[11px] px-1.5 py-[1px] rounded bg-bg-sunken border border-border-subtle"
                        title="Completed, but not gradeable — this ruleset states no drawdown limit"
                      >
                        not graded
                      </span>
                    ) : (
                      <span className="text-text-tertiary text-xs">—</span>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-text-primary">
                    {t.strategy_name ?? t.strategy_id}
                  </td>
                  <td className="py-2 pr-4 font-mono text-accent">{t.instrument}</td>
                  <td className="py-2 pr-4">
                    {(() => {
                      const s = t.status
                      const label =
                        s === 'complete'
                          ? 'Complete'
                          : s === 'running'
                            ? 'Running'
                            : s === 'running_wf'
                              ? 'Walk-forward'
                              : s === 'running_sens'
                                ? 'Sensitivity'
                                : s.startsWith('failed')
                                  ? 'Failed'
                                  : s
                      const cls =
                        s === 'complete'
                          ? 'bg-pos-muted text-pos-text'
                          : s.startsWith('failed')
                            ? 'bg-neg-muted text-neg-text'
                            : 'bg-accent/10 text-accent'
                      return (
                        <span
                          className={`inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full ${cls}`}
                        >
                          {s.startsWith('running') && (
                            <span className="w-[5px] h-[5px] rounded-full bg-accent animate-pulse" />
                          )}
                          {label}
                        </span>
                      )
                    })()}
                  </td>
                  {/* The tail in the unit the GRADE read. This list showed the two probabilities
                      and no drawdown at all, so the one number a stress test exists to produce was
                      only visible one click in — and a dollar drawdown listed beside a compounded
                      profit reads an order of magnitude too small, the defect the Runs list fixed
                      on 2026-08-01. */}
                  <td className="py-2 pr-4 font-mono text-text-secondary">
                    {t.dd_basis === 'percent' && t.pct1_max_dd_pct != null ? (
                      <span title="Percent of the running peak — this run compounds, so a fixed dollar limit is not comparable to it">
                        {t.pct1_max_dd_pct.toFixed(1)}%
                      </span>
                    ) : t.pct1_max_dd != null ? (
                      <span title="Dollars — this run holds position size constant">
                        ${Math.round(t.pct1_max_dd).toLocaleString('en-US')}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                  {/* null ≠ 0. A ruleset stating no drawdown limit has nothing to breach and
                      nothing to pass, which is a third answer. */}
                  <td className="py-2 pr-4 font-mono text-text-secondary">
                    {t.prob_breach != null ? (
                      `${(t.prob_breach * 100).toFixed(1)}%`
                    ) : (
                      <span
                        className="text-text-tertiary"
                        title="No drawdown limit on this ruleset — there is nothing to breach"
                      >
                        n/a
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-4 font-mono text-text-secondary">
                    {t.prob_pass_eval != null ? (
                      `${(t.prob_pass_eval * 100).toFixed(1)}%`
                    ) : (
                      <span
                        className="text-text-tertiary"
                        title="No drawdown limit or no profit target on this ruleset — there is nothing to pass"
                      >
                        n/a
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-text-tertiary text-xs">
                    {new Date(t.created_at * 1000).toLocaleDateString()}
                  </td>
                </tr>
              ))}
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
          customMessage="This will permanently delete the selected stress tests and all their child runs."
        />
      )}
    </div>
  )
}
