import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Play, Trash2, RefreshCw, ChevronRight } from 'lucide-react'
import { useStrategy, useBacktestRuns, useDeleteRun } from '@/hooks/useLab'
import { RunBacktestModal } from '@/components/RunBacktestModal'
import { EmptyState } from '@/components/EmptyState'
import type { BacktestSummary, VerdictSummary } from '@/types'

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtPeriod(start: string, end: string): string {
  const s = new Date(start).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  const e = new Date(end).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  return `${s} – ${e}`
}

function fmtMoney(n: number | null): string {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const prefix = n < 0 ? '-' : '+'
  if (abs >= 1_000) return `${prefix}$${(abs / 1_000).toFixed(1)}k`
  return `${prefix}$${abs.toFixed(0)}`
}

// ── Status pill ───────────────────────────────────────────────────────────────

const STATUS_STYLE: Record<string, string> = {
  complete:       'bg-pos-muted text-pos-text',
  running:        'bg-accent-muted text-accent',
  failed_timeout: 'bg-neg-muted text-neg-text',
  failed_unknown: 'bg-neg-muted text-neg-text',
}

function StatusPill({ status }: { status: string }) {
  const cls = STATUS_STYLE[status] ?? 'bg-warn-muted text-warn-text'
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-[2px] rounded-pill text-[11px] font-semibold uppercase tracking-[0.4px] ${cls}`}>
      {status === 'running' && <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse" />}
      {status.startsWith('failed') ? 'failed' : status}
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
  const visible  = verdicts.slice(0, 3)
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
      {overflow > 0 && <span className="text-[10px] text-text-tertiary">+{overflow} more</span>}
    </div>
  )
}

// ── Delete modal ──────────────────────────────────────────────────────────────

function ConfirmDeleteModal({
  onConfirm, onCancel, isPending,
}: {
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={e => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[380px] shadow-2xl">
        <div className="px-5 py-4 border-b border-border-subtle">
          <div className="text-[15px] font-semibold">Delete this run?</div>
        </div>
        <div className="px-5 py-4">
          <p className="text-[13px] text-text-secondary">
            Its evaluations and result files will also be removed. This cannot be undone.
          </p>
        </div>
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle">
          <button onClick={onCancel} className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">
            Cancel
          </button>
          <button
            onClick={onConfirm} disabled={isPending}
            className="px-4 py-[7px] rounded-md text-[13px] font-medium bg-neg-text text-white hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {isPending ? 'Deleting…' : 'Delete run'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Param schema display ──────────────────────────────────────────────────────

function ParamSchemaTable({ schema }: { schema: Array<{ name: string; type: string; min?: number; max?: number; default: unknown; display_name: string }> }) {
  if (!schema.length) return null
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border-subtle">
            <th className="text-left px-4 py-2 text-text-tertiary font-medium">Parameter</th>
            <th className="text-left px-4 py-2 text-text-tertiary font-medium">Type</th>
            <th className="text-left px-4 py-2 text-text-tertiary font-medium">Default</th>
            <th className="text-left px-4 py-2 text-text-tertiary font-medium">Range</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {schema.map(p => (
            <tr key={p.name} className="hover:bg-bg-hover transition-colors">
              <td className="px-4 py-2">
                <div className="font-medium text-text-primary">{p.display_name}</div>
                <div className="text-[10px] text-text-tertiary font-mono">{p.name}</div>
              </td>
              <td className="px-4 py-2 text-text-secondary font-mono">{p.type}</td>
              <td className="px-4 py-2 text-text-secondary font-mono tabular-nums">
                {String(p.default)}
              </td>
              <td className="px-4 py-2 text-text-tertiary">
                {p.min != null && p.max != null ? `${p.min}–${p.max}` : p.min != null ? `≥ ${p.min}` : p.max != null ? `≤ ${p.max}` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Runs table (strategy-filtered) ───────────────────────────────────────────

function StrategyRunsTable({
  strategyId,
}: {
  strategyId: string
}) {
  const navigate  = useNavigate()
  const deleteRun = useDeleteRun()
  const { data: runs, isLoading, refetch, isFetching } = useBacktestRuns({ strategy_id: strategyId })
  const [deleteRunId, setDeleteRunId] = useState<string | null>(null)

  const handleDelete = () => {
    if (!deleteRunId) return
    deleteRun.mutate(deleteRunId, { onSuccess: () => setDeleteRunId(null) })
  }

  if (isLoading) {
    return (
      <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden animate-pulse">
        {[0,1,2].map(i => (
          <div key={i} className="flex gap-4 px-4 py-3 border-b border-border-subtle last:border-0">
            <div className="h-4 w-24 bg-bg-hover rounded" />
            <div className="h-4 w-32 bg-bg-hover rounded" />
            <div className="h-4 w-20 bg-bg-hover rounded" />
          </div>
        ))}
      </div>
    )
  }

  if (!runs?.length) {
    return (
      <EmptyState
        icon={<Play size={20} />}
        title="No runs yet for this strategy"
        description='Click "Run Backtest" above to start your first experiment.'
      />
    )
  }

  return (
    <>
      <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 border-b border-border-subtle">
          <span className="text-[12px] text-text-tertiary">{runs.length} run{runs.length !== 1 ? 's' : ''}</span>
          <button
            onClick={() => refetch()} disabled={isFetching}
            className="flex items-center gap-1 text-[11px] text-text-tertiary hover:text-text-secondary transition-colors disabled:opacity-40"
          >
            <RefreshCw size={11} className={isFetching ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-border-subtle">
              <th className="text-left px-4 py-3 text-text-tertiary font-medium">Instrument</th>
              <th className="text-left px-4 py-3 text-text-tertiary font-medium">Period</th>
              <th className="text-left px-4 py-3 text-text-tertiary font-medium">Status</th>
              <th className="text-left px-4 py-3 text-text-tertiary font-medium">Net P&L</th>
              <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max DD</th>
              <th className="text-left px-4 py-3 text-text-tertiary font-medium">Verdicts</th>
              <th className="px-3 py-3 w-16" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {runs.map(run => (
              <StrategyRunRow
                key={run.run_id}
                run={run}
                onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
                onDelete={e => { e.stopPropagation(); setDeleteRunId(run.run_id) }}
              />
            ))}
          </tbody>
        </table>
      </div>

      {deleteRunId && (
        <ConfirmDeleteModal
          onConfirm={handleDelete}
          onCancel={() => setDeleteRunId(null)}
          isPending={deleteRun.isPending}
        />
      )}
    </>
  )
}

function StrategyRunRow({
  run, onClick, onDelete,
}: {
  run: BacktestSummary
  onClick: () => void
  onDelete: (e: React.MouseEvent) => void
}) {
  const pnlClass = run.net_pnl == null ? '' : run.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'
  return (
    <tr onClick={onClick} className="hover:bg-bg-hover cursor-pointer transition-colors">
      <td className="px-4 py-3 font-mono text-text-secondary">{run.instrument}</td>
      <td className="px-4 py-3 text-text-secondary">
        {run.status !== 'running' && run.completed_at
          ? fmtPeriod(run.created_at, run.completed_at)
          : fmtDate(run.created_at)}
      </td>
      <td className="px-4 py-3"><StatusPill status={run.status} /></td>
      <td className={`px-4 py-3 font-mono tabular-nums ${pnlClass}`}>{fmtMoney(run.net_pnl)}</td>
      <td className="px-4 py-3 font-mono tabular-nums text-neg-text">
        {run.max_drawdown != null ? `$${run.max_drawdown.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'}
      </td>
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

// ── Page ──────────────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">
      {children}
    </h2>
  )
}

function Skeleton() {
  return (
    <div className="animate-pulse space-y-6">
      <div className="h-6 w-48 bg-bg-surface rounded" />
      <div className="h-4 w-64 bg-bg-surface rounded" />
      <div className="h-[120px] bg-bg-surface rounded-lg" />
    </div>
  )
}

export function StrategyDetail() {
  const { strategyId } = useParams<{ strategyId: string }>()
  const navigate = useNavigate()
  const [showModal, setShowModal] = useState(false)

  const { data: strategy, isLoading } = useStrategy(strategyId ?? null)

  if (isLoading) {
    return (
      <div>
        <button
          onClick={() => navigate('/backtests')}
          className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
        >
          <ArrowLeft size={14} /> Backtests
        </button>
        <Skeleton />
      </div>
    )
  }

  if (!strategy) {
    return (
      <div>
        <button
          onClick={() => navigate('/backtests')}
          className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
        >
          <ArrowLeft size={14} /> Backtests
        </button>
        <EmptyState icon={<Play size={20} />} title="Strategy not found" description="This strategy may have been removed." />
      </div>
    )
  }

  return (
    <div>
      {/* Back nav */}
      <button
        onClick={() => navigate('/backtests')}
        className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
      >
        <ArrowLeft size={14} /> Backtests
      </button>

      <div className="space-y-8">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-h1 font-semibold leading-tight">{strategy.name}</h1>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-[13px] text-text-secondary">
              <span className="font-mono">{strategy.class_name}</span>
              {strategy.category && (
                <>
                  <span className="text-text-tertiary">·</span>
                  <span className="capitalize">{strategy.category}</span>
                </>
              )}
              {strategy.suggested_instrument && (
                <>
                  <span className="text-text-tertiary">·</span>
                  <span className="font-mono">Suggested: {strategy.suggested_instrument}</span>
                </>
              )}
            </div>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-[6px] px-4 py-[8px] rounded-md text-[13px] font-medium bg-accent text-bg-base hover:opacity-90 transition-opacity flex-shrink-0"
          >
            <Play size={13} />
            Run Backtest
          </button>
        </div>

        {/* Param schema */}
        {strategy.param_schema.length > 0 && (
          <div>
            <SectionLabel>Parameters</SectionLabel>
            <ParamSchemaTable schema={strategy.param_schema as Array<{ name: string; type: string; min?: number; max?: number; default: unknown; display_name: string }>} />
          </div>
        )}

        {/* Runs for this strategy */}
        <div>
          <SectionLabel>Runs for this strategy</SectionLabel>
          {strategyId && <StrategyRunsTable strategyId={strategyId} />}
        </div>
      </div>

      {showModal && (
        <RunBacktestModal
          strategy={strategy}
          onClose={() => setShowModal(false)}
          onSuccess={runId => {
            setShowModal(false)
            navigate(`/backtests/runs/${runId}`)
          }}
        />
      )}
    </div>
  )
}
