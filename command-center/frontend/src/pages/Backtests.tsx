import { useState, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { RefreshCw, Play, ChevronRight, Trash2 } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useBacktestRuns, useStrategies, useFirms,
  useScanStrategies, useLabProgress, useDeleteRun,
} from '@/hooks/useLab'
import { EmptyState } from '@/components/EmptyState'
import { RunBacktestModal } from '@/components/RunBacktestModal'
import { api } from '@/api/client'
import { toast } from 'sonner'
import type { BacktestSummary, Strategy, Firm, VerdictSummary } from '@/types'

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  })
}

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

const STATUS_STYLE: Record<string, string> = {
  complete:       'bg-pos-muted text-pos-text',
  running:        'bg-accent-muted text-accent',
  failed_timeout: 'bg-neg-muted text-neg-text',
  failed_unknown: 'bg-neg-muted text-neg-text',
  failed:         'bg-neg-muted text-neg-text',
}

function StatusPill({ status }: { status: string }) {
  const isFailed = status.startsWith('failed')
  const label    = isFailed ? 'failed' : status
  const cls      = STATUS_STYLE[status] ?? 'bg-warn-muted text-warn-text'
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
  const size  = (parts[1] ?? '').replace('k', '').replace('K', '')
  const tier  = parts[2] === 'eval' ? 'Eval' : parts[2] === 'funded' ? 'Funded' : (parts[2] ?? '')
  return `${brand}${size} ${tier}`
}

const VERDICT_PILL_STYLE: Record<string, string> = {
  PASS:    'bg-pos-muted text-pos-text',
  WARN:    'bg-warn-muted text-warn-text',
  DISCARD: 'bg-neg-muted text-neg-text',
}

function VerdictPills({ verdicts }: { verdicts: VerdictSummary[] }) {
  if (!verdicts.length) return <span className="text-text-tertiary text-[11px]">—</span>
  const visible  = verdicts.slice(0, 2)
  const overflow = verdicts.length - visible.length
  return (
    <div className="flex gap-[4px] items-center flex-wrap">
      {visible.map(v => (
        <span
          key={v.firm_id}
          title={v.notes ?? `${firmShortName(v.firm_id)}: ${v.verdict}`}
          className={`inline-flex items-center px-[6px] py-[2px] rounded text-[10px] font-semibold ${VERDICT_PILL_STYLE[v.verdict] ?? 'bg-bg-hover text-text-tertiary'}`}
        >
          {firmShortName(v.firm_id)}: {v.verdict}
        </span>
      ))}
      {overflow > 0 && (
        <span className="text-[10px] text-text-tertiary">+{overflow} more</span>
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
}: {
  count: number
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={e => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[400px] shadow-2xl">
        <div className="px-5 py-4 border-b border-border-subtle">
          <div className="text-[15px] font-semibold">
            Delete {count === 1 ? 'this run' : `${count} runs`}?
          </div>
        </div>
        <div className="px-5 py-4">
          <p className="text-[13px] text-text-secondary">
            {count === 1
              ? 'Its evaluations and result files will also be removed.'
              : `All ${count} runs' evaluations and result files will also be removed.`}
            {' '}This cannot be undone.
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
            {isPending ? 'Deleting…' : count === 1 ? 'Delete run' : `Delete ${count} runs`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Tab bar ───────────────────────────────────────────────────────────────────

type Tab = 'strategies' | 'runs' | 'firms'

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'strategies', label: 'Strategies' },
  { id: 'runs',       label: 'Runs'       },
  { id: 'firms',      label: 'Firms'      },
]

function TabBar({ active, onChange }: { active: Tab; onChange: (t: Tab) => void }) {
  return (
    <div className="flex gap-0 border-b border-border-subtle mb-6">
      {TABS.map(t => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`px-4 py-2 text-[13px] font-medium transition-colors -mb-px border-b-2 ${
            active === t.id
              ? 'text-text-primary border-accent'
              : 'text-text-tertiary border-transparent hover:text-text-secondary'
          }`}
        >
          {t.label}
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

  const [statusFilter, setStatusFilter] = useState('')
  const [selectedIds, setSelectedIds]   = useState<Set<string>>(new Set())
  const [deleteRunId, setDeleteRunId]   = useState<string | null>(null)
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [showBulkConfirm, setShowBulkConfirm] = useState(false)

  const { data: runs, isLoading, refetch, isFetching } = useBacktestRuns(
    statusFilter ? { status: statusFilter } : undefined
  )

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
    else setSelectedIds(new Set(runs.map(r => r.run_id)))
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
          {/* Status filter */}
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
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Duration</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Net P&L</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max DD</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Win%</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Verdicts</th>
                <th className="px-3 py-3 w-16" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {runs.map(run => (
                <RunRow
                  key={run.run_id}
                  run={run}
                  selected={selectedIds.has(run.run_id)}
                  onSelect={() => toggleSelect(run.run_id)}
                  onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
                  onDelete={e => { e.stopPropagation(); setDeleteRunId(run.run_id) }}
                />
              ))}
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

function RunRow({
  run, selected, onSelect, onClick, onDelete,
}: {
  run: BacktestSummary
  selected: boolean
  onSelect: () => void
  onClick: () => void
  onDelete: (e: React.MouseEvent) => void
}) {
  const pnlClass = run.net_pnl == null ? '' : run.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'
  return (
    <tr
      onClick={onClick}
      className={`hover:bg-bg-hover cursor-pointer transition-colors ${selected ? 'bg-accent/5' : ''}`}
    >
      <td className="px-3 py-3" onClick={e => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          onChange={onSelect}
          className="w-3.5 h-3.5 rounded accent-accent cursor-pointer"
        />
      </td>
      <td className="px-4 py-3 font-medium">{run.strategy_name || run.strategy_id}</td>
      <td className="px-4 py-3 font-mono text-text-secondary">{run.instrument}</td>
      <td className="px-4 py-3 text-text-secondary">{fmtDate(run.created_at)}</td>
      <td className="px-4 py-3"><StatusPill status={run.status} /></td>
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
      <td className="px-4 py-3"><VerdictPills verdicts={run.verdicts} /></td>
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

const TIER_STYLE: Record<string, string> = {
  eval:   'bg-warn-muted text-warn-text',
  funded: 'bg-pos-muted text-pos-text',
}

function FirmsTab() {
  const { data: firms, isLoading } = useFirms()

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <span className="text-[13px] text-text-secondary">
          {firms ? `${firms.length} firm${firms.length !== 1 ? 's' : ''}` : ''}
        </span>
      </div>

      {isLoading ? (
        <FirmsSkeleton />
      ) : !firms?.length ? (
        <EmptyState
          icon={<Play size={20} />}
          title="No firms configured"
          description="Firm profiles are seeded automatically from bot.json on backend startup."
        />
      ) : (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Firm</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Tier</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Account Size</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Profit Target</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max DD (EOD)</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Drawdown Type</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Consistency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {firms.map(firm => <FirmRow key={firm.id} firm={firm} />)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function FirmRow({ firm }: { firm: Firm }) {
  return (
    <tr className="hover:bg-bg-hover transition-colors">
      <td className="px-4 py-3">
        <div className="font-medium">{firm.name}</div>
        <div className="text-[11px] text-text-tertiary font-mono">{firm.id}</div>
      </td>
      <td className="px-4 py-3">
        <span className={`inline-flex px-2 py-[2px] rounded-pill text-[11px] font-semibold uppercase tracking-[0.4px] ${TIER_STYLE[firm.account_tier] ?? 'bg-bg-surface-2 text-text-tertiary'}`}>
          {firm.account_tier}
        </span>
      </td>
      <td className="px-4 py-3 font-mono tabular-nums">${firm.account_size.toLocaleString()}</td>
      <td className="px-4 py-3 font-mono tabular-nums text-pos-text">
        {firm.profit_target > 0 ? `$${firm.profit_target.toLocaleString()}` : '—'}
      </td>
      <td className="px-4 py-3 font-mono tabular-nums text-neg-text">
        ${firm.max_loss_eod.toLocaleString()}
      </td>
      <td className="px-4 py-3 text-text-secondary capitalize">{firm.drawdown_type}</td>
      <td className="px-4 py-3 text-text-secondary">
        {firm.consistency_pct != null ? `≤ ${firm.consistency_pct}%` : <span className="text-text-tertiary">—</span>}
      </td>
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

// ── Page shell ────────────────────────────────────────────────────────────────

export function Backtests() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (searchParams.get('tab') ?? 'strategies') as Tab
  const setTab = (t: Tab) => setSearchParams({ tab: t }, { replace: true })

  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Backtests</h1>
      </div>

      <TabBar active={tab} onChange={setTab} />

      {tab === 'strategies' && <StrategiesTab />}
      {tab === 'runs'       && <RunsTab />}
      {tab === 'firms'      && <FirmsTab />}
    </div>
  )
}
