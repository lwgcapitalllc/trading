import { useState, useCallback, useMemo, Fragment } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { RefreshCw, Play, ChevronRight, ChevronDown, Layers, Sliders, Trash2, Activity } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useBacktestRuns, useLabProgress, useDeleteRun, useRetryBacktest, useRunningVpsJob,
  useOptimizations, useDeleteOptimization, useSweeps, useDeleteSweep,
} from '@/hooks/useLab'
import { useRunningStressLock } from '@/hooks/useStressTests'
import { EmptyState } from '@/components/EmptyState'
import { WorthinessBadge } from '@/components/WorthinessBadge'
import { StatusPill } from '@/components/StatusPill'
import { api } from '@/api/client'
import { toast } from 'sonner'
import type { BacktestSummary, VerdictSummary, WorthinessScore } from '@/types'

// ── Market helpers ────────────────────────────────────────────────────────────

type MarketFilter = 'all' | 'futures' | 'forex'

function isForexInstrument(instrument: string): boolean {
  // Forex pairs are exactly 6 uppercase letters (EURUSD, XAUUSD, etc.)
  return /^[A-Z]{6}$/.test(instrument.split(' ')[0])
}

function MarketFilterBar({ value, onChange }: { value: MarketFilter; onChange: (v: MarketFilter) => void }) {
  const opts: Array<{ id: MarketFilter; label: string }> = [
    { id: 'all',     label: 'All' },
    { id: 'futures', label: 'Futures' },
    { id: 'forex',   label: 'Forex' },
  ]
  return (
    <div className="flex gap-[2px] bg-bg-sunken rounded-md p-[3px]">
      {opts.map(o => (
        <button key={o.id} onClick={() => onChange(o.id)}
          className={`px-2.5 py-[3px] rounded text-[11px] font-medium transition-colors ${
            value === o.id ? 'bg-bg-surface text-text-primary shadow-sm' : 'text-text-tertiary hover:text-text-secondary'
          }`}
        >{o.label}</button>
      ))}
    </div>
  )
}

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
          key={v.ruleset_id}
          title={v.ruleset_id}
          className={`inline-flex items-center px-[6px] py-[2px] rounded text-[10px] font-semibold font-mono ${challengeCls(v.ruleset_id)}`}
        >
          {firmShortName(v.ruleset_id)}
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
  count, onConfirm, onCancel, isPending, customMessage, confirmLabel,
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
          <button onClick={onCancel} className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">Cancel</button>
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

type Tab = 'runs' | 'sweeps' | 'optimizations'

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
    { id: 'runs',          label: 'Runs',          count: runsCount,   active: runsActive },
    { id: 'sweeps',        label: 'Sweeps',        count: sweepsCount, active: sweepsActive },
    { id: 'optimizations', label: 'Optimizations', count: optsCount,   active: optsActive },
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
  const [marketFilter, setMarketFilter]       = useState<MarketFilter>('all')
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
  const { data: allOpts }    = useOptimizations()
  const { data: allSweeps }  = useSweeps()
  const { data: stressLock } = useRunningStressLock()
  const stressRunIds = useMemo(() => new Set(stressLock?.run_ids ?? []), [stressLock])

  const linkedSweepIds = useMemo(() => {
    const set = new Set<string>()
    allSweeps?.forEach(sw => { if (sw.source_run_id) set.add(sw.sweep_id) })
    return set
  }, [allSweeps])

  const optById = useMemo(() => {
    const map = new Map<string, NonNullable<typeof allOpts>[0]>()
    allOpts?.forEach(o => map.set(o.optimization_id, o))
    return map
  }, [allOpts])

  // Running full backtests of optimization winners — nest under the parent run instead of top-level
  const fullBtRunsByParent = useMemo(() => {
    const map = new Map<string, import('@/types').BacktestSummary[]>()
    if (!allRuns) return map
    for (const r of allRuns) {
      if (!r.optimization_id || r.status !== 'running') continue
      const parentId = optById.get(r.optimization_id)?.source_run_id
      if (!parentId) continue
      const existing = map.get(parentId) ?? []
      existing.push(r)
      map.set(parentId, existing)
    }
    return map
  }, [allRuns, optById])

  const fullBtNestIds = useMemo(() => {
    const set = new Set<string>()
    for (const runs of fullBtRunsByParent.values())
      for (const r of runs) set.add(r.run_id)
    return set
  }, [fullBtRunsByParent])

  const runs = useMemo(
    () => allRuns
      ?.filter(r => (!r.optimization_id || r.status === 'running') && !(r.sweep_id && linkedSweepIds.has(r.sweep_id)))
      ?.filter(r => !fullBtNestIds.has(r.run_id))
      ?.filter(r => marketFilter === 'all' || (isForexInstrument(r.instrument) ? 'forex' : 'futures') === marketFilter),
    [allRuns, linkedSweepIds, fullBtNestIds, marketFilter]
  )

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
          <MarketFilterBar value={marketFilter} onChange={v => { setMarketFilter(v); setSelectedIds(new Set()) }} />
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
          description="Go to Strategies, pick a strategy, and click Run Backtest."
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
                const childSweeps  = sweepsBySourceRun.get(run.run_id) ?? []
                const childOpts    = optsBySourceRun.get(run.run_id) ?? []
                const childFullBts = fullBtRunsByParent.get(run.run_id) ?? []
                const hasChildren  = childSweeps.length > 0 || childOpts.length > 0 || childFullBts.length > 0
                const isCollapsed  = collapsedRuns.has(run.run_id)
                return (
                  <Fragment key={run.run_id}>
                    <RunRow
                      run={run}
                      selected={selectedIds.has(run.run_id)}
                      onSelect={() => toggleSelect(run.run_id)}
                      onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
                      hasChildren={hasChildren}
                      isCollapsed={isCollapsed}
                      onToggleCollapse={() => toggleCollapse(run.run_id)}
                      hasRunningStress={stressRunIds.has(run.run_id)}
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
                        hasRunningStress={!!opt.best_run_id && stressRunIds.has(opt.best_run_id)}
                      />
                    ))}
                    {!isCollapsed && childFullBts.map(r => (
                      <FullBacktestNestRow
                        key={r.run_id}
                        colSpan={12}
                        onClick={() => navigate(`/backtests/runs/${r.run_id}`)}
                      />
                    ))}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {deleteRunId && (
        <ConfirmDeleteModal
          count={1}
          onConfirm={handleSingleDelete}
          onCancel={() => setDeleteRunId(null)}
          isPending={deleteRun.isPending}
          customMessage={cascadeMessage(deleteRunId)}
        />
      )}

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

// ── Nested optimization row ───────────────────────────────────────────────────

function fmtOptStatus(s: string) {
  if (s === 'complete')       return { label: 'Complete', cls: 'bg-pos-muted text-pos-text' }
  if (s === 'running')        return { label: 'Running',  cls: 'bg-accent/10 text-accent' }
  if (s.startsWith('failed')) return { label: 'Failed',   cls: 'bg-neg-muted text-neg-text' }
  return { label: s, cls: 'bg-bg-hover text-text-secondary' }
}

function OptimizationNestRow({
  opt, colSpan, onClick, hasRunningStress,
}: {
  opt: import('@/types').OptimizationSummary
  colSpan: number
  onClick: () => void
  hasRunningStress?: boolean
}) {
  const st = fmtOptStatus(opt.status)
  return (
    <tr onClick={onClick} className="hover:bg-bg-hover cursor-pointer transition-colors bg-gold-muted/5 border-l-2 border-l-gold-text/35">
      <td className="px-3 py-2" />
      <td className="px-4 py-2" colSpan={3}>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gold-text/60 font-mono">↳</span>
          <span className="text-[11px] font-semibold text-gold-text">Optimization</span>
          <span className="text-[10px] text-text-tertiary">{opt.completed_runs}/{opt.estimated_runs} runs</span>
          {opt.status === 'running' && (
            <span className="w-[6px] h-[6px] rounded-full bg-gold-text animate-pulse flex-shrink-0" title="Optimization in progress" />
          )}
          {hasRunningStress && (
            <span title="Stress test in progress"
              className="inline-flex items-center gap-[3px] px-[5px] py-[2px] rounded text-[10px] font-semibold bg-accent/10 text-accent">
              <Activity size={8} className="animate-pulse" />
              STRESS TESTING
            </span>
          )}
        </div>
      </td>
      <td className="px-4 py-2">
        <span className={`inline-flex px-2 py-[2px] rounded-pill text-[10px] font-semibold uppercase tracking-[0.4px] ${st.cls}`}>{st.label}</span>
      </td>
      <td colSpan={colSpan - 5} className="px-4 py-2 text-right">
        <span className="text-[11px] text-accent">View →</span>
      </td>
    </tr>
  )
}

// ── Nested full-backtest row (winner run from an optimization) ────────────────

function FullBacktestNestRow({ colSpan, onClick }: {
  colSpan: number
  onClick: () => void
}) {
  return (
    <tr onClick={onClick} className="hover:bg-bg-hover cursor-pointer transition-colors bg-gold-muted/5 border-l-2 border-l-gold-text/35">
      <td className="px-3 py-2" />
      <td className="px-4 py-2" colSpan={3}>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-gold-text/60 font-mono">↳</span>
          <span className="text-[11px] font-semibold text-gold-text">Full Backtest</span>
          <span className="w-[6px] h-[6px] rounded-full bg-gold-text animate-pulse flex-shrink-0" title="Running" />
        </div>
      </td>
      <td className="px-4 py-2">
        <span className="inline-flex items-center gap-1 px-2 py-[2px] rounded-pill text-[10px] font-semibold uppercase tracking-[0.4px] bg-accent/10 text-accent">
          <span className="w-[4px] h-[4px] rounded-full bg-accent animate-pulse" />
          Running
        </span>
      </td>
      <td colSpan={colSpan - 5} className="px-4 py-2 text-right">
        <span className="text-[11px] text-accent">View →</span>
      </td>
    </tr>
  )
}

// ── Nested sweep row ──────────────────────────────────────────────────────────

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
    <tr onClick={onClick} className="hover:bg-bg-hover cursor-pointer transition-colors bg-accent/[0.03] border-l-2 border-l-accent/30">
      <td className="px-3 py-2" />
      <td className="px-4 py-2" colSpan={3}>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-accent/50 font-mono">↳</span>
          <span className="text-[11px] font-semibold text-accent/80">Sweep</span>
          <span className="text-[10px] text-text-tertiary">{sweep.total_instruments} instruments</span>
          {sweep.status === 'running' && (
            <span className="text-[10px] text-text-tertiary">· {sweep.completed_instruments}/{sweep.total_instruments} done</span>
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
  run, selected, onSelect, onClick, hasChildren, isCollapsed, onToggleCollapse, hasRunningStress,
}: {
  run: BacktestSummary
  selected: boolean
  onSelect: () => void
  onClick: () => void
  hasChildren?: boolean
  isCollapsed?: boolean
  onToggleCollapse?: () => void
  hasRunningStress?: boolean
}) {
  const navigate = useNavigate()
  const retry = useRetryBacktest()
  const { data: runningJob } = useRunningVpsJob()
  const isMt5 = run.runner === 'mt5'
  const platformLocked = isMt5 ? !!runningJob?.mt5?.running : !!runningJob?.nt8?.running
  const pnlClass = run.net_pnl == null ? '' : run.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'
  const isOptChild   = !!run.optimization_id
  const isSweepChild = !!run.sweep_id
  return (
    <tr
      onClick={onClick}
      className={`hover:bg-bg-hover cursor-pointer transition-colors ${selected ? 'bg-accent/5' : ''} ${isOptChild ? 'border-l-2 border-l-gold-text/40' : isSweepChild ? 'border-l-2 border-l-accent/40' : ''}`}
    >
      <td className="px-3 py-3" onClick={e => e.stopPropagation()}>
        <input type="checkbox" checked={selected} onChange={onSelect} className="w-3.5 h-3.5 rounded accent-accent cursor-pointer" />
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
          <span>{run.strategy_name || run.strategy_id}</span>
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
          {hasRunningStress && (
            <span
              title="Stress test in progress"
              className="inline-flex items-center gap-[3px] px-[5px] py-[2px] rounded text-[10px] font-semibold bg-accent/10 text-accent"
            >
              <Activity size={8} className="animate-pulse" />
              STRESS TESTING
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
      <td className="px-4 py-3 font-mono tabular-nums text-text-secondary">{fmtDuration(run.created_at, run.completed_at)}</td>
      <td className={`px-4 py-3 font-mono tabular-nums ${pnlClass}`}>{fmtMoney(run.net_pnl)}</td>
      <td className="px-4 py-3 font-mono tabular-nums text-neg-text">
        {run.max_drawdown != null ? `$${run.max_drawdown.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'}
      </td>
      <td className="px-4 py-3 font-mono tabular-nums">{fmtPct(run.win_rate)}</td>
      <td className="px-4 py-3"><ChallengePills verdicts={run.verdicts} /></td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-1 justify-end">
          <button
            onClick={e => { e.stopPropagation(); retry.mutate(run.run_id) }}
            disabled={retry.isPending || platformLocked}
            className="p-[5px] rounded text-text-tertiary hover:text-accent hover:bg-accent/10 transition-colors disabled:opacity-40"
            title={platformLocked ? `${isMt5 ? 'MT5' : 'NT8'} is busy — wait for the current job to finish` : run.status.startsWith('failed') ? 'Retry' : 'Rerun'}
          >
            <Play size={13} />
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
      {[0, 1, 2].map(i => (
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

// ── Sweeps tab ────────────────────────────────────────────────────────────────

function SweepsTab() {
  const navigate    = useNavigate()
  const deleteSweep = useDeleteSweep()
  const { data: sweeps, isLoading } = useSweeps()
  const [deleteSweepId, setDeleteSweepId] = useState<string | null>(null)

  function fmtSweepStatus(s: string) {
    if (s === 'complete')       return { label: 'Complete', cls: 'bg-pos-muted text-pos-text' }
    if (s === 'running')        return { label: 'Running',  cls: 'bg-accent/10 text-accent' }
    if (s === 'partial')        return { label: 'Partial',  cls: 'bg-warn-muted text-warn-text' }
    if (s.startsWith('failed')) return { label: 'Failed',   cls: 'bg-neg-muted text-neg-text' }
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
        <EmptyState icon={<Layers size={20} />} title="No sweeps yet" description="Run a strategy across multiple instruments from a backtest detail page." />
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
                    <td className="px-4 py-3 text-text-secondary font-mono tabular-nums">{fmtDateRange(sw.start_date, sw.end_date)}</td>
                    <td className="px-4 py-3 font-mono tabular-nums text-text-secondary">
                      {sw.completed_instruments}/{sw.total_instruments}
                      {sw.failed_instruments > 0 && <span className="ml-1 text-neg-text text-[11px]">({sw.failed_instruments} failed)</span>}
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
                        {sw.ruleset_ids.slice(0, 2).map(f => (
                          <span key={f} className={`inline-flex items-center px-[6px] py-[2px] rounded text-[10px] font-semibold font-mono ${challengeCls(f)}`}>{firmShortName(f)}</span>
                        ))}
                        {sw.ruleset_ids.length > 2 && <span className="text-[10px] text-text-tertiary">+{sw.ruleset_ids.length - 2}</span>}
                        {sw.ruleset_ids.length === 0 && <span className="text-text-tertiary text-[11px]">—</span>}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1 justify-end">
                        <button
                          onClick={e => { e.stopPropagation(); setDeleteSweepId(sw.sweep_id) }}
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

// ── Optimizations tab ─────────────────────────────────────────────────────────

function OptimizationsTab() {
  const navigate  = useNavigate()
  const deleteOpt = useDeleteOptimization()
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
        <EmptyState icon={<Sliders size={20} />} title="No optimizations yet" description='Click "Optimize" on a completed backtest to start a native optimization run.' />
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

// ── Page shell ────────────────────────────────────────────────────────────────

export function Backtests() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (searchParams.get('tab') ?? 'runs') as Tab
  const setTab = (t: Tab) => setSearchParams({ tab: t }, { replace: true })

  const { data: allRuns }   = useBacktestRuns()
  const { data: allOpts }   = useOptimizations()
  const { data: allSweeps } = useSweeps()
  const runsCount    = allRuns?.filter(r => (!r.optimization_id || r.status === 'running') && !r.sweep_id).length
  const optsCount    = allOpts?.length
  const sweepsCount  = allSweeps?.length
  const runsActive   = allRuns?.some(r => !r.sweep_id && r.status === 'running')
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

      {tab === 'runs'          && <RunsTab />}
      {tab === 'sweeps'        && <SweepsTab />}
      {tab === 'optimizations' && <OptimizationsTab />}
    </div>
  )
}
