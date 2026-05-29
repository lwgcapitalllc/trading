import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw, Play, ChevronRight } from 'lucide-react'
import {
  useBacktestRuns, useStrategies, useFirms, useScanStrategies, useLabProgress,
} from '@/hooks/useLab'
import { EmptyState } from '@/components/EmptyState'
import { RunBacktestModal } from '@/components/RunBacktestModal'
import type { BacktestSummary, Strategy, Firm } from '@/types'

// ── Helpers ───────────────────────────────────────────────────────────────────

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

// ── Status pill ───────────────────────────────────────────────────────────────

const STATUS_STYLE: Record<string, string> = {
  complete:        'bg-pos-muted text-pos-text',
  running:         'bg-accent-muted text-accent',
  failed_timeout:  'bg-neg-muted text-neg-text',
  failed_unknown:  'bg-neg-muted text-neg-text',
  failed:          'bg-neg-muted text-neg-text',
}

function StatusPill({ status }: { status: string }) {
  const isFailed = status.startsWith('failed')
  const label    = isFailed ? 'failed' : status
  const cls      = STATUS_STYLE[status] ?? 'bg-warn-muted text-warn-text'
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-[2px] rounded-pill text-[11px] font-semibold uppercase tracking-[0.4px] ${cls}`}>
      {status === 'running' && (
        <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse" />
      )}
      {label}
    </span>
  )
}

// ── Verdict dots ──────────────────────────────────────────────────────────────

const VERDICT_COLOR: Record<string, string> = {
  PASS:    'bg-pos-text',
  WARN:    'bg-warn-text',
  DISCARD: 'bg-neg-text',
}

function VerdictDots({ verdicts }: { verdicts: BacktestSummary['verdicts'] }) {
  if (!verdicts.length) return <span className="text-text-tertiary text-[11px]">—</span>
  return (
    <div className="flex gap-[4px] items-center flex-wrap">
      {verdicts.map(v => (
        <span
          key={v.firm_id}
          title={`${v.firm_id}: ${v.verdict}`}
          className={`w-2 h-2 rounded-full ${VERDICT_COLOR[v.verdict] ?? 'bg-text-tertiary'}`}
        />
      ))}
    </div>
  )
}

// ── Tab bar ───────────────────────────────────────────────────────────────────

type Tab = 'runs' | 'strategies' | 'firms'

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'runs',       label: 'Runs'       },
  { id: 'strategies', label: 'Strategies' },
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
  const progress  = useLabProgress()
  const { data: runs, isLoading, refetch, isFetching } = useBacktestRuns()

  const isRunning = progress.data?.status === 'running'

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="text-[13px] text-text-secondary">
            {runs ? `${runs.length} run${runs.length !== 1 ? 's' : ''}` : ''}
          </span>
          {isRunning && (
            <span className="flex items-center gap-1 text-[12px] text-accent">
              <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse" />
              {progress.data?.pct}% — {progress.data?.strategy_id} {progress.data?.instrument}
            </span>
          )}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1 text-[12px] text-text-tertiary hover:text-text-secondary transition-colors disabled:opacity-40"
        >
          <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
          Refresh
        </button>
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
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Strategy</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Instrument</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Date range</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Status</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Net P&L</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max DD</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Win%</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Trades</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Verdicts</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {runs.map(run => (
                <RunRow
                  key={run.run_id}
                  run={run}
                  onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function RunRow({ run, onClick }: { run: BacktestSummary; onClick: () => void }) {
  const pnlClass = run.net_pnl == null ? '' : run.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'
  return (
    <tr
      onClick={onClick}
      className="hover:bg-bg-hover cursor-pointer transition-colors"
    >
      <td className="px-4 py-3 font-medium">
        {run.strategy_name || run.strategy_id}
      </td>
      <td className="px-4 py-3 font-mono text-text-secondary">{run.instrument}</td>
      <td className="px-4 py-3 text-text-secondary">{fmtDate(run.created_at)}</td>
      <td className="px-4 py-3"><StatusPill status={run.status} /></td>
      <td className={`px-4 py-3 font-mono tabular-nums ${pnlClass}`}>
        {fmtMoney(run.net_pnl)}
      </td>
      <td className="px-4 py-3 font-mono tabular-nums text-neg-text">
        {run.max_drawdown != null ? `$${run.max_drawdown.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'}
      </td>
      <td className="px-4 py-3 font-mono tabular-nums">
        {fmtPct(run.win_rate)}
      </td>
      <td className="px-4 py-3 tabular-nums">
        {run.trade_count ?? '—'}
      </td>
      <td className="px-4 py-3">
        <VerdictDots verdicts={run.verdicts} />
      </td>
      <td className="px-4 py-3 text-text-tertiary">
        <ChevronRight size={14} />
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
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Default instrument</th>
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

function StrategyRow({ strategy: s, onRun }: { strategy: Strategy; onRun: () => void }) {
  return (
    <tr className="hover:bg-bg-hover transition-colors">
      <td className="px-4 py-3 font-medium">{s.name}</td>
      <td className="px-4 py-3 font-mono text-text-secondary text-[12px]">{s.class_name}</td>
      <td className="px-4 py-3 font-mono text-text-secondary">
        {s.default_instrument ?? <span className="text-text-tertiary">—</span>}
      </td>
      <td className="px-4 py-3 text-text-secondary">{s.param_schema.length}</td>
      <td className="px-4 py-3 tabular-nums">{s.run_count}</td>
      <td className="px-4 py-3">
        <button
          onClick={onRun}
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
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Account size</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Profit target</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max DD (EOD)</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Drawdown type</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Consistency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {firms.map(firm => (
                <FirmRow key={firm.id} firm={firm} />
              ))}
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
      <td className="px-4 py-3 font-mono tabular-nums">
        ${firm.account_size.toLocaleString()}
      </td>
      <td className="px-4 py-3 font-mono tabular-nums text-pos-text">
        {firm.profit_target > 0 ? `$${firm.profit_target.toLocaleString()}` : '—'}
      </td>
      <td className="px-4 py-3 font-mono tabular-nums text-neg-text">
        ${firm.max_loss_eod.toLocaleString()}
      </td>
      <td className="px-4 py-3 text-text-secondary capitalize">
        {firm.drawdown_type}
      </td>
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
  const [tab, setTab] = useState<Tab>('runs')

  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Backtests</h1>
      </div>

      <TabBar active={tab} onChange={setTab} />

      {tab === 'runs'       && <RunsTab />}
      {tab === 'strategies' && <StrategiesTab />}
      {tab === 'firms'      && <FirmsTab />}
    </div>
  )
}
