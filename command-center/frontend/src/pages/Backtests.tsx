import { useState, useCallback, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { RefreshCw, Play, ChevronRight, ChevronDown, Trash2, Layers, Sliders } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useBacktestRuns, useStrategies, useFirms,
  useScanStrategies, useLabProgress, useDeleteRun,
  useOptimizations, useDeleteOptimization, useSweeps, useDeleteSweep,
} from '@/hooks/useLab'
import { EmptyState } from '@/components/EmptyState'
import { RunBacktestModal } from '@/components/RunBacktestModal'
import { WorthinessBadge } from '@/components/WorthinessBadge'
import { api } from '@/api/client'
import { toast } from 'sonner'
import type { BacktestSummary, Strategy, Firm, VerdictSummary, WorthinessScore } from '@/types'

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtMoney(n: number | null): string {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const prefix = n < 0 ? '-' : '+'
  if (abs >= 1_000) return `${prefix}$${(abs / 1_000).toFixed(1)}k`
  return `${prefix}$${abs.toFixed(0)}`
}

function fmtPct(n: number | null): string {
  if (n == null) return '—'
  return `${(n * 100).toFixed(1)}%`
}

function fmtDateRange(start: string, end: string): string {
  const days = (new Date(end).getTime() - new Date(start).getTime()) / 86_400_000
  const years = days / 365.25
  if (years >= 1) return `${years.toFixed(1)} yrs`
  const months = days / 30.44
  if (months >= 1) return `${Math.round(months)} mo`
  return `${Math.round(days)} days`
}

function fmtDuration(createdAt: string, completedAt: string | null): string {
  if (!completedAt) return '—'
  const secs = Math.round((new Date(completedAt).getTime() - new Date(createdAt).getTime()) / 1000)
  if (secs < 0) return '—'
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60)
  const s = secs % 60
  if (m < 60) return s > 0 ? `${m}m ${s}s` : `${m}m`
  const h = Math.floor(m / 60)
  const rm = m % 60
  return rm > 0 ? `${h}h ${rm}m` : `${h}h`
}

// ── Status pill ───────────────────────────────────────────────────────────────

function StatusPill({ status }: { status: string }) {
  const isFailed = status.startsWith('failed')
  const label    = isFailed ? 'failed' : status
  const cls      = status === 'complete'  ? 'bg-pos-muted text-pos-text'
    : status === 'running'   ? 'bg-accent-muted text-accent'
    : isFailed               ? 'bg-neg-muted text-neg-text'
    : 'bg-bg-hover text-text-secondary'
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-[2px] rounded-pill text-[11px] font-semibold uppercase tracking-[0.4px] ${cls}`}>
      {status === 'running' && <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse" />}
      {label}
    </span>
  )
}

// ── Verdict pills ─────────────────────────────────────────────────────────────

function firmShortName(firmId: string): string {
  const parts = firmId.split('_')
  if (parts.length < 3) return firmId
  const brandMap: Record<string, string> = { lucidflex: 'LF', apex: 'Apex', tradeify: 'TF' }
  const brand = brandMap[parts[0]] ?? parts[0].slice(0, 2).toUpperCase()
  const size  = (parts[1] ?? '').toUpperCase()
  const tier  = parts[2] === 'eval' ? 'Eval' : parts[2] === 'funded' ? 'Funded' : (parts[2] ?? '')
  return `${brand}${size} ${tier}`
}

function challengeCls(firmId: string): string {
  if (firmId.includes('_eval'))   return 'bg-warn-muted text-warn-text'
  if (firmId.includes('_funded')) return 'bg-pos-muted text-pos-text'
  return 'bg-bg-hover text-text-secondary'
}

function ChallengePills({ verdicts }: { verdicts: VerdictSummary[] }) {
  if (!verdicts.length) return <span className="text-text-tertiary text-[11px]">—</span>
  const visible  = verdicts.slice(0, 2)
  const overflow = verdicts.length - visible.length
  return (
    <div className="flex gap-[4px] items-center flex-wrap">
      {visible.map(v => (
        <span
          key={v.firm_id}
          title={v.firm_id}
          className={`inline-flex items-center px-[6px] py-[2px] rounded text-[10px] font-semibold font-mono ${challengeCls(v.firm_id)}`}
        >
          {firmShortName(v.firm_id)}
        </span>
      ))}
      {overflow > 0 && (
        <span className="text-[10px] text-text-tertiary">+{overflow}</span>
      )}
    </div>
  )
}

// ── Delete confirmation modal ─────────────────────────────────────────────────

function ConfirmDeleteModal({
  count,
  onConfirm,
  onCancel,
  isPending,
  customMessage,
  confirmLabel,
}: {
  count: number
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
  customMessage?: string
  confirmLabel?: string
}) {
  const defaultMsg = count === 1
    ? 'Its evaluations and result files will also be removed.'
    : `All ${count} runs' evaluations and result files will also be removed.`
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={e => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[400px] shadow-2xl">
        <div className="px-5 py-4 border-b border-border-subtle">
          <div className="text-[15px] font-semibold">
            Delete {count === 1 ? 'this' : count} {count === 1 ? 'item' : 'items'}?
          </div>
        </div>
        <div className="px-5 py-4">
          <p className="text-[13px] text-text-secondary">
            {customMessage ?? defaultMsg}{' '}This cannot be undone.
          </p>
        </div>
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle">
          <button
            onClick={onCancel}
            className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className="px-4 py-[7px] rounded-md text-[13px] font-medium bg-neg-muted text-neg-text border border-neg/40 hover:bg-neg/15 disabled:opacity-50 transition-colors"
          >
            {isPending ? 'Deleting…' : (confirmLabel ?? (count === 1 ? 'Delete' : `Delete ${count}`))}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Tab bar ───────────────────────────────────────────────────────────────────

type Tab = 'strategies' | 'runs' | 'sweeps' | 'optimizations' | 'firms'

function TabBar({
  active, onChange, runsCount, sweepsCount, optsCount,
  runsActive, sweepsActive, optsActive,
}: {
  active: Tab
  onChange: (t: Tab) => void
  runsCount?: number
  sweepsCount?: number
  optsCount?: number
  runsActive?: boolean
  sweepsActive?: boolean
  optsActive?: boolean
}) {
  const tabs: Array<{ id: Tab; label: string; count?: number; active?: boolean }> = [
    { id: 'strategies',    label: 'Strategies' },
    { id: 'runs',          label: 'Runs',          count: runsCount,   active: runsActive },
    { id: 'sweeps',        label: 'Sweeps',         count: sweepsCount, active: sweepsActive },
    { id: 'optimizations', label: 'Optimizations', count: optsCount,   active: optsActive },
    { id: 'firms',         label: 'Firms' },
  ]
  return (
    <div className="flex gap-0 border-b border-border-subtle mb-6">
      {tabs.map(t => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`flex items-center gap-1.5 px-4 py-2 text-[13px] font-medium transition-colors -mb-px border-b-2 ${
            active === t.id
              ? 'text-text-primary border-accent'
              : 'text-text-tertiary border-transparent hover:text-text-secondary'
          }`}
        >
          {t.label}
          {t.count != null && (
            <span className={`text-[11px] font-mono tabular-nums px-[5px] py-[1px] rounded-full ${
              active === t.id ? 'bg-accent/15 text-accent' : 'bg-bg-hover text-text-tertiary'
            }`}>
              {t.count}
            </span>
          )}
          {t.active && (
            <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse flex-shrink-0" />
          )}
        </button>
      ))}
    </div>
  )
}

// ── Runs tab ──────────────────────────────────────────────────────────────────

function RunsTab() {
  const navigate  = useNavigate()
  const qc        = useQueryClient()
  const progress  = useLabProgress()
  const deleteRun = useDeleteRun()

  const [statusFilter, setStatusFilter]       = useState('')
  const [selectedIds, setSelectedIds]         = useState<Set<string>>(new Set())
  const [deleteRunId, setDeleteRunId]         = useState<string | null>(null)
  const [bulkDeleting, setBulkDeleting]       = useState(false)
  const [showBulkConfirm, setShowBulkConfirm] = useState(false)
  const [collapsedRuns, setCollapsedRuns]     = useState<Set<string>>(new Set())

  const toggleCollapse = (id: string) =>
    setCollapsedRuns(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const { data: allRuns, isLoading, refetch, isFetching } = useBacktestRuns(
    statusFilter ? { status: statusFilter } : undefined
  )
  const { data: allOpts }   = useOptimizations()
  const { data: allSweeps } = useSweeps()

  // sweep_ids that have a known source run — their child runs are shown nested, not as flat rows
  const linkedSweepIds = useMemo(() => {
    const set = new Set<string>()
    allSweeps?.forEach(sw => { if (sw.source_run_id) set.add(sw.sweep_id) })
    return set
  }, [allSweeps])

  // Hide: opt child runs always; sweep child runs only when the sweep is linked (shows nested)
  const runs = useMemo(
    () => allRuns?.filter(r => !r.optimization_id && !(r.sweep_id && linkedSweepIds.has(r.sweep_id))),
    [allRuns, linkedSweepIds]
  )

  // Map: source_run_id → optimizations started from that run
  const optsBySourceRun = useMemo(() => {
    const map = new Map<string, typeof allOpts>()
    if (!allOpts) return map
    for (const opt of allOpts) {
      if (!opt.source_run_id) continue
      const existing = map.get(opt.source_run_id) ?? []
      existing.push(opt)
      map.set(opt.source_run_id, existing)
    }
    return map
  }, [allOpts])

  // Map: source_run_id → sweeps started from that run
  const sweepsBySourceRun = useMemo(() => {
    const map = new Map<string, NonNullable<typeof allSweeps>>()
    if (!allSweeps) return map
    for (const sw of allSweeps) {
      if (!sw.source_run_id) continue
      const existing = map.get(sw.source_run_id) ?? []
      existing.push(sw)
      map.set(sw.source_run_id, existing)
    }
    return map
  }, [allSweeps])

  // Cascade delete message for a run
  const cascadeMessage = useCallback((runId: string) => {
    const opts   = optsBySourceRun.get(runId) ?? []
    const sweeps = sweepsBySourceRun.get(runId) ?? []
    const parts: string[] = []
    if (opts.length)   parts.push(`${opts.length} optimization${opts.length !== 1 ? 's' : ''}`)
    if (sweeps.length) parts.push(`${sweeps.length} sweep${sweeps.length !== 1 ? 's' : ''}`)
    if (!parts.length) return undefined
    return `This run has ${parts.join(' and ')} attached — they and all their results will also be permanently deleted.`
  }, [optsBySourceRun, sweepsBySourceRun])

  const isRunning = progress.data?.status === 'running'

  const toggleSelect = (id: string) =>
    setSelectedIds(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const toggleSelectAll = () => {
    if (!runs) return
    if (selectedIds.size === runs.length) setSelectedIds(new Set())
    else setSelectedIds(new Set(runs.map((r: BacktestSummary) => r.run_id)))
  }

  const handleSingleDelete = useCallback(() => {
    if (!deleteRunId) return
    deleteRun.mutate(deleteRunId, {
      onSuccess: () => {
        setDeleteRunId(null)
        setSelectedIds(prev => { const n = new Set(prev); n.delete(deleteRunId); return n })
      },
    })
  }, [deleteRunId, deleteRun])

  const handleBulkDelete = useCallback(async () => {
    setBulkDeleting(true)
    const ids = Array.from(selectedIds)
    try {
      const results = await Promise.allSettled(ids.map(id => api.delete<void>(`/backtests/runs/${id}`)))
      const failed = results.filter(r => r.status === 'rejected').length
      const succeeded = ids.length - failed
      qc.invalidateQueries({ queryKey: ['lab', 'runs'] })
      qc.invalidateQueries({ queryKey: ['lab', 'sweeps'] })
      qc.invalidateQueries({ queryKey: ['lab', 'optimizations'] })
      if (failed === 0) {
        toast.success(`${ids.length} run${ids.length !== 1 ? 's' : ''} deleted`)
      } else if (succeeded > 0) {
        toast.error(`${succeeded} deleted, ${failed} not found`)
      } else {
        toast.error('Delete failed — runs not found')
      }
      setSelectedIds(new Set())
      setShowBulkConfirm(false)
    } finally {
      setBulkDeleting(false)
    }
  }, [selectedIds, qc])

  const allChecked = runs != null && runs.length > 0 && selectedIds.size === runs.length

  return (
    <div>
      {/* Header row */}
      <div className="flex items-center justify-between mb-4 gap-3">
        <div className="flex items-center gap-3">
          <span className="text-[13px] text-text-secondary">
            {runs ? `${runs.length} run${runs.length !== 1 ? 's' : ''}` : ''}
          </span>
          {isRunning && (
            <span className="flex items-center gap-1 text-[12px] text-accent">
              <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse" />
              {progress.data?.pct}% — {progress.data?.strategy_id} {progress.data?.instrument}
            </span>
          )}
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
        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); setSelectedIds(new Set()) }}
            className="bg-bg-sunken border border-border-subtle rounded-md px-2 py-[5px] text-[12px] text-text-secondary focus:outline-none focus:border-accent transition-colors"
          >
            <option value="">All statuses</option>
            <option value="complete">Complete</option>
            <option value="running">Running</option>
            <option value="failed">Failed</option>
          </select>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1 text-[12px] text-text-tertiary hover:text-text-secondary transition-colors disabled:opacity-40"
          >
            <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {isLoading ? (
        <RunsTableSkeleton />
      ) : !runs?.length ? (
        <EmptyState
          icon={<Play size={20} />}
          title="No backtest runs yet"
          description="Go to the Strategies tab, pick a strategy, and click Run Backtest."
        />
      ) : (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="px-3 py-3 w-8">
                  <input
                    type="checkbox"
                    checked={allChecked}
                    onChange={toggleSelectAll}
                    className="w-3.5 h-3.5 rounded accent-accent cursor-pointer"
                  />
                </th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Strategy</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Instrument</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Date Range</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Status</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Score</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Duration</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Net P&L</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max DD</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Win%</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Challenge</th>
                <th className="px-3 py-3 w-16" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {runs.map(run => {
                const childSweeps = sweepsBySourceRun.get(run.run_id) ?? []
                const childOpts   = optsBySourceRun.get(run.run_id) ?? []
                const hasChildren = childSweeps.length > 0 || childOpts.length > 0
                const isCollapsed = collapsedRuns.has(run.run_id)
                return (
                  <>
                    <RunRow
                      key={run.run_id}
                      run={run}
                      selected={selectedIds.has(run.run_id)}
                      onSelect={() => toggleSelect(run.run_id)}
                      onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
                      onDelete={e => { e.stopPropagation(); setDeleteRunId(run.run_id) }}
                      hasChildren={hasChildren}
                      isCollapsed={isCollapsed}
                      onToggleCollapse={() => toggleCollapse(run.run_id)}
                    />
                    {!isCollapsed && childSweeps.map(sw => (
                      <SweepNestRow
                        key={sw.sweep_id}
                        sweep={sw}
                        colSpan={12}
                        onClick={() => navigate(`/backtests/sweeps/${sw.sweep_id}`)}
                      />
                    ))}
                    {!isCollapsed && childOpts.map(opt => (
                      <OptimizationNestRow
                        key={opt.optimization_id}
                        opt={opt}
                        colSpan={12}
                        onClick={() => navigate(`/backtests/optimizations/${opt.optimization_id}`)}
                      />
                    ))}
                  </>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Single delete confirm */}
      {deleteRunId && (
        <ConfirmDeleteModal
          count={1}
          onConfirm={handleSingleDelete}
          onCancel={() => setDeleteRunId(null)}
          isPending={deleteRun.isPending}
          customMessage={cascadeMessage(deleteRunId)}
        />
      )}

      {/* Bulk delete confirm */}
      {showBulkConfirm && (
        <ConfirmDeleteModal
          count={selectedIds.size}
          onConfirm={handleBulkDelete}
          onCancel={() => setShowBulkConfirm(false)}
          isPending={bulkDeleting}
        />
      )}
    </div>
  )
}

// ── Nested optimization row (shown under the source run) ─────────────────────

function OptimizationNestRow({
  opt, colSpan, onClick,
}: {
  opt: import('@/types').OptimizationSummary
  colSpan: number
  onClick: () => void
}) {
  const st = fmtOptStatus(opt.status)
  const totalRuns = opt.estimated_runs
  const doneRuns  = opt.completed_runs
  return (
    <tr
      onClick={onClick}
      className="hover:bg-bg-hover cursor-pointer transition-colors bg-gold-muted/5 border-l-2 border-l-gold-text/35"
    >
      <td className="px-3 py-2" />
      <td className="px-4 py-2" colSpan={3}>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gold-text/60 font-mono">↳</span>
          <span className="text-[11px] font-semibold text-gold-text">Optimization</span>
          <span className="text-[11px] text-text-tertiary font-mono">{opt.instrument}</span>
          <span className="text-[10px] text-text-tertiary">
            · {doneRuns}/{totalRuns} runs
          </span>
        </div>
      </td>
      <td className="px-4 py-2">
        <span className={`inline-flex px-2 py-[2px] rounded-pill text-[10px] font-semibold uppercase tracking-[0.4px] ${st.cls}`}>
          {st.label}
        </span>
      </td>
      <td colSpan={colSpan - 5} className="px-4 py-2 text-right">
        <span className="text-[11px] text-accent">View →</span>
      </td>
    </tr>
  )
}

// ── Nested sweep row (shown under the source run) ─────────────────────────────

function SweepNestRow({
  sweep, colSpan, onClick,
}: {
  sweep: import('@/types').SweepSummary
  colSpan: number
  onClick: () => void
}) {
  function fmtSweepSt(s: string) {
    if (s === 'complete')       return { label: 'Complete', cls: 'bg-pos-muted text-pos-text' }
    if (s === 'running')        return { label: 'Running',  cls: 'bg-accent/10 text-accent' }
    if (s === 'partial')        return { label: 'Partial',  cls: 'bg-warn-muted text-warn-text' }
    if (s.startsWith('failed')) return { label: 'Failed',   cls: 'bg-neg-muted text-neg-text' }
    return { label: s, cls: 'bg-bg-hover text-text-secondary' }
  }
  const st = fmtSweepSt(sweep.status)
  return (
    <tr
      onClick={onClick}
      className="hover:bg-bg-hover cursor-pointer transition-colors bg-accent/[0.03] border-l-2 border-l-accent/30"
    >
      <td className="px-3 py-2" />
      <td className="px-4 py-2" colSpan={3}>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-accent/50 font-mono">↳</span>
          <span className="text-[11px] font-semibold text-accent/80">Sweep</span>
          <span className="text-[10px] text-text-tertiary">
            {sweep.total_instruments} instruments
          </span>
          {sweep.status === 'running' && (
            <span className="text-[10px] text-text-tertiary">
              · {sweep.completed_instruments}/{sweep.total_instruments} done
            </span>
          )}
        </div>
      </td>
      <td className="px-4 py-2">
        <span className={`inline-flex items-center gap-1 px-2 py-[2px] rounded-pill text-[10px] font-semibold uppercase tracking-[0.4px] ${st.cls}`}>
          {sweep.status === 'running' && <span className="w-[4px] h-[4px] rounded-full bg-accent animate-pulse" />}
          {st.label}
        </span>
      </td>
      <td colSpan={colSpan - 5} className="px-4 py-2 text-right">
        <span className="text-[11px] text-accent">View →</span>
      </td>
    </tr>
  )
}

// ── Run row ───────────────────────────────────────────────────────────────────

function RunRow({
  run, selected, onSelect, onClick, onDelete, hasChildren, isCollapsed, onToggleCollapse,
}: {
  run: BacktestSummary
  selected: boolean
  onSelect: () => void
  onClick: () => void
  onDelete: (e: React.MouseEvent) => void
  hasChildren?: boolean
  isCollapsed?: boolean
  onToggleCollapse?: () => void
}) {
  const navigate = useNavigate()
  const pnlClass = run.net_pnl == null ? '' : run.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'
  const isOptChild = !!run.optimization_id
  const isSweepChild = !!run.sweep_id
  return (
    <tr
      onClick={onClick}
      className={`hover:bg-bg-hover cursor-pointer transition-colors ${selected ? 'bg-accent/5' : ''} ${isOptChild ? 'border-l-2 border-l-gold-text/40' : isSweepChild ? 'border-l-2 border-l-accent/40' : ''}`}
    >
      <td className="px-3 py-3" onClick={e => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          onChange={onSelect}
          className="w-3.5 h-3.5 rounded accent-accent cursor-pointer"
        />
      </td>
      <td className="px-4 py-3 font-medium">
        <div className="flex items-center gap-1.5 flex-wrap">
          {hasChildren && (
            <button
              onClick={e => { e.stopPropagation(); onToggleCollapse?.() }}
              className="flex-shrink-0 text-text-tertiary hover:text-text-secondary transition-colors"
              title={isCollapsed ? 'Expand children' : 'Collapse children'}
            >
              {isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
            </button>
          )}
          {run.strategy_name || run.strategy_id}
          {run.sweep_id && (
            <span
              onClick={e => { e.stopPropagation(); navigate(`/backtests/sweeps/${run.sweep_id}`) }}
              title={`Sweep: ${run.sweep_id}`}
              className="inline-flex items-center gap-[3px] px-[5px] py-[2px] rounded text-[10px] font-semibold bg-accent/10 text-accent cursor-pointer hover:bg-accent/20 transition-colors"
            >
              <Layers size={8} />
              SWEEP
            </span>
          )}
          {run.optimization_id && (
            <span
              onClick={e => { e.stopPropagation(); navigate(`/backtests/optimizations/${run.optimization_id}`) }}
              title={`Optimization: ${run.optimization_id}`}
              className="inline-flex items-center gap-[3px] px-[5px] py-[2px] rounded text-[10px] font-semibold bg-gold-muted text-gold-text cursor-pointer hover:opacity-80 transition-opacity"
            >
              <Sliders size={8} />
              OPT
            </span>
          )}
        </div>
      </td>
      <td className="px-4 py-3 font-mono text-text-secondary">{run.instrument}</td>
      <td className="px-4 py-3 text-text-secondary font-mono tabular-nums">
        {run.start_date && run.end_date ? fmtDateRange(run.start_date, run.end_date) : '—'}
      </td>
      <td className="px-4 py-3"><StatusPill status={run.status} /></td>
      <td className="px-4 py-3"><WorthinessBadge worthiness={run.worthiness} /></td>
      <td className="px-4 py-3 font-mono tabular-nums text-text-secondary">
        {fmtDuration(run.created_at, run.completed_at)}
      </td>
      <td className={`px-4 py-3 font-mono tabular-nums ${pnlClass}`}>
        {fmtMoney(run.net_pnl)}
      </td>
      <td className="px-4 py-3 font-mono tabular-nums text-neg-text">
        {run.max_drawdown != null ? `$${run.max_drawdown.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'}
      </td>
      <td className="px-4 py-3 font-mono tabular-nums">{fmtPct(run.win_rate)}</td>
      <td className="px-4 py-3"><ChallengePills verdicts={run.verdicts} /></td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-1 justify-end">
          <button
            onClick={onDelete}
            className="p-[5px] rounded text-text-tertiary hover:text-neg-text hover:bg-neg-muted transition-colors"
            title="Delete run"
          >
            <Trash2 size={13} />
          </button>
          <ChevronRight size={14} className="text-text-tertiary" />
        </div>
      </td>
    </tr>
  )
}

function RunsTableSkeleton() {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden animate-pulse">
      {[0,1,2].map(i => (
        <div key={i} className="flex gap-4 px-4 py-3 border-b border-border-subtle last:border-0">
          <div className="h-4 w-32 bg-bg-hover rounded" />
          <div className="h-4 w-20 bg-bg-hover rounded" />
          <div className="h-4 w-24 bg-bg-hover rounded" />
          <div className="h-4 w-16 bg-bg-hover rounded" />
        </div>
      ))}
    </div>
  )
}

// ── Strategies tab ────────────────────────────────────────────────────────────

function StrategiesTab() {
  const navigate  = useNavigate()
  const { data: strategies, isLoading } = useStrategies()
  const scan = useScanStrategies()
  const [runStrategy, setRunStrategy] = useState<Strategy | null>(null)

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <span className="text-[13px] text-text-secondary">
          {strategies ? `${strategies.length} registered` : ''}
        </span>
        <button
          onClick={() => scan.mutate()}
          disabled={scan.isPending}
          className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium bg-accent text-bg-base hover:opacity-90 transition-opacity disabled:opacity-50"
        >
          <RefreshCw size={12} className={scan.isPending ? 'animate-spin' : ''} />
          Scan Strategies
        </button>
      </div>

      {isLoading ? (
        <StrategiesSkeleton />
      ) : !strategies?.length ? (
        <EmptyState
          icon={<RefreshCw size={20} />}
          title="No strategies registered"
          description='Click "Scan Strategies" to discover NinjaTrader strategy classes in the algos folder.'
        />
      ) : (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Name</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Class</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Suggested Instrument</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Params</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Runs</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {strategies.map(s => (
                <StrategyRow
                  key={s.id}
                  strategy={s}
                  onView={() => navigate(`/backtests/strategies/${s.id}`)}
                  onRun={() => setRunStrategy(s)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {runStrategy && (
        <RunBacktestModal
          strategy={runStrategy}
          onClose={() => setRunStrategy(null)}
        />
      )}
    </div>
  )
}

function StrategyRow({
  strategy: s,
  onView,
  onRun,
}: {
  strategy: Strategy
  onView: () => void
  onRun: () => void
}) {
  return (
    <tr
      onClick={onView}
      className="hover:bg-bg-hover cursor-pointer transition-colors"
    >
      <td className="px-4 py-3 font-medium">
        <div className="flex items-center gap-1">
          {s.name}
          <ChevronRight size={13} className="text-text-tertiary opacity-60" />
        </div>
      </td>
      <td className="px-4 py-3 font-mono text-text-secondary text-[12px]">{s.class_name}</td>
      <td className="px-4 py-3 font-mono text-text-secondary">
        {s.suggested_instrument ?? <span className="text-text-tertiary">—</span>}
      </td>
      <td className="px-4 py-3 text-text-secondary">{s.param_schema.length}</td>
      <td className="px-4 py-3 tabular-nums">{s.run_count}</td>
      <td className="px-4 py-3">
        <button
          onClick={e => { e.stopPropagation(); onRun() }}
          className="flex items-center gap-1 px-[10px] py-[4px] rounded-md text-[11px] font-medium bg-accent/10 text-accent border border-accent/20 hover:bg-accent/20 transition-colors"
        >
          <Play size={10} />
          Run
        </button>
      </td>
    </tr>
  )
}

function StrategiesSkeleton() {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden animate-pulse">
      {[0,1,2].map(i => (
        <div key={i} className="flex gap-4 px-4 py-3 border-b border-border-subtle last:border-0">
          <div className="h-4 w-40 bg-bg-hover rounded" />
          <div className="h-4 w-48 bg-bg-hover rounded" />
          <div className="h-4 w-24 bg-bg-hover rounded" />
        </div>
      ))}
    </div>
  )
}

// ── Firms tab ─────────────────────────────────────────────────────────────────

function FirmsTab() {
  const { data: firms, isLoading } = useFirms()

  if (isLoading) return <FirmsSkeleton />
  if (!firms?.length) return (
    <EmptyState
      icon={<Play size={20} />}
      title="No firms configured"
      description="Firm profiles are seeded automatically from bot.json on backend startup."
    />
  )

  const evalFirms   = firms.filter(f => f.account_tier === 'eval')
  const fundedFirms = firms.filter(f => f.account_tier === 'funded')

  return (
    <div className="space-y-6">
      {evalFirms.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[11px] font-semibold uppercase tracking-[0.6px] text-warn-text px-2 py-[2px] rounded bg-warn-muted/50">
              Evaluation Challenges
            </span>
            <span className="text-[11px] text-text-tertiary">{evalFirms.length} account{evalFirms.length !== 1 ? 's' : ''}</span>
          </div>
          <FirmTable firms={evalFirms} showTarget />
        </div>
      )}
      {fundedFirms.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[11px] font-semibold uppercase tracking-[0.6px] text-pos-text px-2 py-[2px] rounded bg-pos-muted/50">
              Funded Accounts
            </span>
            <span className="text-[11px] text-text-tertiary">{fundedFirms.length} account{fundedFirms.length !== 1 ? 's' : ''}</span>
          </div>
          <FirmTable firms={fundedFirms} showTarget={false} />
        </div>
      )}
    </div>
  )
}

function FirmTable({ firms, showTarget }: { firms: Firm[]; showTarget: boolean }) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-border-subtle">
            <th className="text-left px-4 py-3 text-text-tertiary font-medium">Firm</th>
            <th className="text-left px-4 py-3 text-text-tertiary font-medium">Account Size</th>
            {showTarget && <th className="text-left px-4 py-3 text-text-tertiary font-medium">Profit Target</th>}
            <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max DD (EOD)</th>
            <th className="text-left px-4 py-3 text-text-tertiary font-medium">Drawdown Type</th>
            {showTarget && <th className="text-left px-4 py-3 text-text-tertiary font-medium">Consistency</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {firms.map(firm => <FirmRow key={firm.id} firm={firm} showTarget={showTarget} />)}
        </tbody>
      </table>
    </div>
  )
}

function FirmRow({ firm, showTarget }: { firm: Firm; showTarget: boolean }) {
  return (
    <tr className="hover:bg-bg-hover transition-colors">
      <td className="px-4 py-3">
        <div className="font-medium">{firm.name}</div>
        <div className="text-[11px] text-text-tertiary font-mono">{firm.id}</div>
      </td>
      <td className="px-4 py-3 font-mono tabular-nums">${firm.account_size.toLocaleString()}</td>
      {showTarget && (
        <td className="px-4 py-3 font-mono tabular-nums text-pos-text">
          {firm.profit_target > 0 ? `$${firm.profit_target.toLocaleString()}` : '—'}
        </td>
      )}
      <td className="px-4 py-3 font-mono tabular-nums text-neg-text">
        ${firm.max_loss_eod.toLocaleString()}
      </td>
      <td className="px-4 py-3 text-text-secondary capitalize">{firm.drawdown_type.replace(/_/g, ' ')}</td>
      {showTarget && (
        <td className="px-4 py-3 text-text-secondary">
          {firm.consistency_pct != null ? `≤ ${firm.consistency_pct}%` : <span className="text-text-tertiary">—</span>}
        </td>
      )}
    </tr>
  )
}

function FirmsSkeleton() {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden animate-pulse">
      {[0,1,2,3].map(i => (
        <div key={i} className="flex gap-4 px-4 py-3 border-b border-border-subtle last:border-0">
          <div className="h-4 w-36 bg-bg-hover rounded" />
          <div className="h-4 w-16 bg-bg-hover rounded" />
          <div className="h-4 w-24 bg-bg-hover rounded" />
          <div className="h-4 w-24 bg-bg-hover rounded" />
        </div>
      ))}
    </div>
  )
}

// ── Sweeps tab ────────────────────────────────────────────────────────────────

function SweepsTab() {
  const navigate    = useNavigate()
  const deleteSweep = useDeleteSweep()
  const { data: sweeps, isLoading } = useSweeps()

  const [deleteSweepId, setDeleteSweepId] = useState<string | null>(null)

  function fmtSweepStatus(s: string) {
    if (s === 'complete')              return { label: 'Complete',  cls: 'bg-pos-muted text-pos-text' }
    if (s === 'running')               return { label: 'Running',   cls: 'bg-accent/10 text-accent' }
    if (s === 'partial')               return { label: 'Partial',   cls: 'bg-warn-muted text-warn-text' }
    if (s.startsWith('failed'))        return { label: 'Failed',    cls: 'bg-neg-muted text-neg-text' }
    return { label: s, cls: 'bg-bg-hover text-text-secondary' }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <span className="text-[13px] text-text-secondary">
          {sweeps ? `${sweeps.length} sweep${sweeps.length !== 1 ? 's' : ''}` : ''}
        </span>
      </div>

      {isLoading ? (
        <RunsTableSkeleton />
      ) : !sweeps?.length ? (
        <EmptyState
          icon={<Layers size={20} />}
          title="No sweeps yet"
          description='Run a strategy across multiple instruments from a backtest detail page.'
        />
      ) : (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Strategy</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Date Range</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Progress</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Status</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Score</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Challenge</th>
                <th className="px-3 py-3 w-20" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {sweeps.map(sw => {
                const st = fmtSweepStatus(sw.status)
                return (
                  <tr
                    key={sw.sweep_id}
                    onClick={() => navigate(`/backtests/sweeps/${sw.sweep_id}`)}
                    className="hover:bg-bg-hover cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-medium">{sw.strategy_name}</td>
                    <td className="px-4 py-3 text-text-secondary font-mono tabular-nums">
                      {fmtDateRange(sw.start_date, sw.end_date)}
                    </td>
                    <td className="px-4 py-3 font-mono tabular-nums text-text-secondary">
                      {sw.completed_instruments}/{sw.total_instruments}
                      {sw.failed_instruments > 0 && (
                        <span className="ml-1 text-neg-text text-[11px]">({sw.failed_instruments} failed)</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-[2px] rounded-pill text-[11px] font-semibold uppercase tracking-[0.4px] ${st.cls}`}>
                        {sw.status === 'running' && <span className="w-[5px] h-[5px] rounded-full bg-accent animate-pulse" />}
                        {st.label}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <WorthinessBadge worthiness={sw.best_worthiness ? { tier: sw.best_worthiness as WorthinessScore['tier'], reason: null, computed_against_firm: null } : null} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-[4px] items-center flex-wrap">
                        {sw.firm_ids.slice(0, 2).map(f => (
                          <span key={f} className={`inline-flex items-center px-[6px] py-[2px] rounded text-[10px] font-semibold font-mono ${challengeCls(f)}`}>
                            {firmShortName(f)}
                          </span>
                        ))}
                        {sw.firm_ids.length > 2 && (
                          <span className="text-[10px] text-text-tertiary">+{sw.firm_ids.length - 2}</span>
                        )}
                        {sw.firm_ids.length === 0 && (
                          <span className="text-text-tertiary text-[11px]">—</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1 justify-end">
                        <button
                          onClick={e => {
                            e.stopPropagation()
                            setDeleteSweepId(sw.sweep_id)
                          }}
                          disabled={sw.status === 'running'}
                          className="p-[5px] rounded text-text-tertiary hover:text-neg-text hover:bg-neg-muted transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                          title={sw.status === 'running' ? 'Wait for sweep to finish before deleting' : 'Delete sweep'}
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

      {deleteSweepId && (
        <ConfirmDeleteModal
          count={1}
          onConfirm={() => deleteSweep.mutate(deleteSweepId, { onSettled: () => setDeleteSweepId(null) })}
          onCancel={() => setDeleteSweepId(null)}
          isPending={deleteSweep.isPending}
          customMessage="This will permanently delete the sweep and all its instrument runs, evaluations, and result files."
        />
      )}
    </div>
  )
}

// ── Optimizations tab ──────────────────────────────────────────────────────────

function fmtOptStatus(s: string) {
  if (s === 'complete')        return { label: 'Complete',  cls: 'bg-pos-muted text-pos-text' }
  if (s === 'running')         return { label: 'Running',   cls: 'bg-accent/10 text-accent' }
  if (s.startsWith('failed'))  return { label: 'Failed',    cls: 'bg-neg-muted text-neg-text' }
  return { label: s, cls: 'bg-bg-hover text-text-secondary' }
}

function OptimizationsTab() {
  const navigate   = useNavigate()
  const deleteOpt  = useDeleteOptimization()
  const { data: opts, isLoading } = useOptimizations()

  const [deleteOptId, setDeleteOptId] = useState<string | null>(null)

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <span className="text-[13px] text-text-secondary">
          {opts ? `${opts.length} optimization${opts.length !== 1 ? 's' : ''}` : ''}
        </span>
      </div>

      {isLoading ? (
        <RunsTableSkeleton />
      ) : !opts?.length ? (
        <EmptyState
          icon={<Sliders size={20} />}
          title="No optimizations yet"
          description='Click "Optimize from this run" on a completed backtest to start a parameter sweep.'
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
                    onClick={() => navigate(`/backtests/optimizations/${opt.optimization_id}`)}
                    className="hover:bg-bg-hover cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3 font-medium">{opt.strategy_id}</td>
                    <td className="px-4 py-3 font-mono text-text-secondary">{opt.instrument}</td>
                    <td className="px-4 py-3 text-text-secondary text-[12px]">{opt.firm_id}</td>
                    <td className="px-4 py-3 capitalize text-text-secondary">{opt.mode}</td>
                    <td className="px-4 py-3 capitalize text-text-secondary">{opt.search_method}</td>
                    <td className="px-4 py-3 font-mono tabular-nums text-text-secondary">
                      {opt.completed_runs}/{opt.estimated_runs}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex px-2 py-[2px] rounded-pill text-[11px] font-semibold uppercase tracking-[0.4px] ${st.cls}`}>
                        {st.label}
                      </span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1 justify-end">
                        <button
                          onClick={e => {
                            e.stopPropagation()
                            setDeleteOptId(opt.optimization_id)
                          }}
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

// ── Page shell ────────────────────────────────────────────────────────────────

export function Backtests() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (searchParams.get('tab') ?? 'strategies') as Tab
  const setTab = (t: Tab) => setSearchParams({ tab: t }, { replace: true })

  // Counts and active-job flags for tab labels
  const { data: allRuns }   = useBacktestRuns()
  const { data: allOpts }   = useOptimizations()
  const { data: allSweeps } = useSweeps()
  const runsCount    = allRuns?.filter(r => !r.optimization_id && !r.sweep_id).length
  const optsCount    = allOpts?.length
  const sweepsCount  = allSweeps?.length
  const runsActive   = allRuns?.some(r => !r.optimization_id && !r.sweep_id && r.status === 'running')
  const sweepsActive = allSweeps?.some(s => s.status === 'running')
  const optsActive   = allOpts?.some(o => o.status === 'running')

  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Backtests</h1>
      </div>

      <TabBar
        active={tab} onChange={setTab}
        runsCount={runsCount} sweepsCount={sweepsCount} optsCount={optsCount}
        runsActive={runsActive} sweepsActive={sweepsActive} optsActive={optsActive}
      />

      {tab === 'strategies'    && <StrategiesTab />}
      {tab === 'runs'          && <RunsTab />}
      {tab === 'sweeps'        && <SweepsTab />}
      {tab === 'optimizations' && <OptimizationsTab />}
      {tab === 'firms'         && <FirmsTab />}
    </div>
  )
}
