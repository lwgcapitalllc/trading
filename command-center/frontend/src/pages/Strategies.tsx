import { useState, useMemo, useRef, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { RefreshCw, Play, ChevronRight, Upload, Trash2, CloudUpload, CheckCircle2, XCircle, AlertTriangle, Layers, WifiOff, X } from 'lucide-react'
import {
  useStrategies,
  useScanStrategies, useReconcileStrategies,
  useStrategyFiles, useStrategyFileSyncStatus,
  useUploadStrategyFile, useDeleteStrategyFile,
  useTriggerCompile, useCompileStatus,
  useTriggerCompileMt5, useCompileStatusMt5,
  useDeployStrategy, useRunningVpsJob,
} from '@/hooks/useLab'
import { ConfirmDeleteModal } from '@/pages/Backtests'
import { EmptyState } from '@/components/EmptyState'
import { RunBacktestModal } from '@/components/RunBacktestModal'
import { StackConfigModal } from '@/components/StackConfigModal'
import RobustnessGradeBadge from '@/components/RobustnessGradeBadge'
import { useStrategyBestGrades } from '@/hooks/useStressTests'
import { RunnerBadge } from '@/components/RunnerBadge'
import { runnerScope, runnerMarket, RUNNER_LABEL } from '@/lib/runner'
import StickyHeader from '@/components/StickyHeader'
import { toast } from 'sonner'
import type { Strategy, StrategyFileSyncStatus } from '@/types'

// ── An unreachable agent is a STATE, and states get rendered ──────────────────
// Both file endpoints reach the VPS through the SSH tunnel, so they are the
// first thing to fail when an agent is down. They used to toast on every poll
// (≈6 a minute, plus a burst on every window focus) and, worse, their failure
// left the page rendering confident answers: "No files deployed" over an
// unreachable box, and every strategy row losing its status pill and offering a
// Run button. Both hooks are `silent` now and the failure is drawn here.

/** One dependency the page could not reach, stated where the reader is looking. */
function AgentDownBanner({ what, detail, className = '' }: {
  what: string; detail?: string | null; className?: string
}) {
  return (
    <div className={`flex items-start gap-2.5 px-3.5 py-2.5 rounded-lg border border-warn-text/25 bg-warn-muted ${className}`}>
      <WifiOff size={14} className="text-warn-text shrink-0 mt-[2px]" />
      <div className="min-w-0">
        <p className="text-[12.5px] text-warn-text font-medium">
          Can’t reach the {what} — showing what this app already knows.
        </p>
        <p className="text-[11.5px] text-warn-text/80 leading-[1.45] mt-0.5">
          Deploy and compile state below come from the local source and this app’s own deploy
          record, so they are still accurate. What is actually ON the VPS is unknown until the
          agent answers.{detail ? ` (${detail})` : ''}
        </p>
      </div>
    </div>
  )
}

// ── Tab bar ───────────────────────────────────────────────────────────────────

type Tab = 'strategies' | 'deployed'

function TabBar({ active, onChange, counts }: {
  active: Tab
  onChange: (t: Tab) => void
  counts: Partial<Record<Tab, number>>
}) {
  const tabs: Array<{ id: Tab; label: string }> = [
    { id: 'strategies', label: 'Strategies' },
    { id: 'deployed',   label: 'Deployed' },
  ]
  return (
    <div className="flex items-center gap-0 border-b border-border-subtle mb-6">
      {tabs.map(t => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={`flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium border-b-2 -mb-px transition-colors ${
            active === t.id
              ? 'border-accent text-accent'
              : 'border-transparent text-text-secondary hover:text-text-primary'
          }`}
        >
          {t.label}
          {counts[t.id] != null && (
            <span className={`text-[11px] font-semibold px-1.5 py-[1px] rounded-full min-w-[18px] text-center tabular-nums ${
              active === t.id
                ? 'bg-accent/15 text-accent'
                : 'bg-bg-surface-2 text-text-tertiary'
            }`}>
              {counts[t.id]}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

// ── Market filter ─────────────────────────────────────────────────────────────

function MarketFilterBar({ value, onChange }: { value: MarketFilter; onChange: (v: MarketFilter) => void }) {
  const opts: Array<{ id: MarketFilter; label: string }> = [
    { id: 'all',     label: 'All' },
    { id: 'futures', label: 'Futures' },
    { id: 'forex',   label: 'Forex' },
  ]
  return (
    <div className="flex gap-[2px] bg-bg-sunken rounded-md p-[3px]">
      {opts.map(o => (
        <button
          key={o.id}
          onClick={() => onChange(o.id)}
          className={`px-2.5 py-[3px] rounded text-[11px] font-medium transition-colors ${
            value === o.id
              ? 'bg-bg-surface text-text-primary shadow-sm'
              : 'text-text-tertiary hover:text-text-secondary'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

// ── Strategies tab ────────────────────────────────────────────────────────────

type MarketFilter = 'all' | 'futures' | 'forex'

const strategyMarket = runnerMarket   // MT5 and Python are both forex; only NT8 is futures

const GRADES = ['A', 'B', 'C', 'D', 'F'] as const
type Grade = typeof GRADES[number]
/** Narrow the grades endpoint's bare `string` to the badge's own union. */
function asGrade(g: string): Grade | null {
  return (GRADES as readonly string[]).includes(g) ? (g as Grade) : null
}

function StrategiesTab() {
  const navigate = useNavigate()
  const { data: strategies, isLoading } = useStrategies()
  const { data: sync, refetch: refetchSync, isError: syncFailed } = useStrategyFileSyncStatus()
  const syncStatus = sync?.statuses
  const { data: strategyGrades } = useStrategyBestGrades()
  useRunningVpsJob()
  const scan = useScanStrategies()
  const reconcile = useReconcileStrategies()
  const [confirmReconcile, setConfirmReconcile] = useState(false)
  // Orphans come off the STRATEGY ROWS, not off the last scan's result. Reading
  // `scan.data?.orphans` meant an orphan was invisible on a fresh page load and
  // stayed invisible until somebody happened to press Scan — whether a source
  // file exists on disk is answerable at any moment, so it rides on the row.
  const orphans = useMemo(
    () => (strategies ?? []).filter(s => s.is_orphan).map(s => s.id),
    [strategies],
  )
  const deploy = useDeployStrategy()
  const compileMut = useTriggerCompile()
  const compileMt5Mut = useTriggerCompileMt5()
  const [activeCompileId, setActiveCompileId] = useState<string | null>(null)
  const [activeMt5CompileId, setActiveMt5CompileId] = useState<string | null>(null)
  const [runStrategy, setRunStrategy] = useState<Strategy | null>(null)
  const [deployingId, setDeployingId] = useState<string | null>(null)
  // In the URL, not `useState` — this folder's own rule for page-level filter
  // state, and it means a refresh or a shared link keeps the view you were on.
  const [searchParams, setSearchParams] = useSearchParams()
  const raw = searchParams.get('market')
  const marketFilter: MarketFilter = raw === 'futures' || raw === 'forex' ? raw : 'all'
  const setMarketFilter = (m: MarketFilter) => setSearchParams(prev => {
    const next = new URLSearchParams(prev)
    if (m === 'all') next.delete('market'); else next.set('market', m)
    return next
  }, { replace: true })
  // Portfolio stacking, straight off this list — tick 2+ PYTHON strategies and hand them to the
  // SAME `StackConfigModal` the Backtests → Stacks tab uses, so a stack is configured identically
  // wherever you start it. Stacking is python-only (the runner the stack engine replays), so a
  // non-python row simply has no checkbox.
  const [stackSel, setStackSel] = useState<Set<string>>(new Set())
  const [stackOpen, setStackOpen] = useState(false)

  const syncByStrategy = useMemo(() => {
    const m: Record<string, StrategyFileSyncStatus> = {}
    syncStatus?.forEach(s => { m[s.strategy_id] = s })
    return m
  }, [syncStatus])

  const visible = useMemo(() =>
    (strategies ?? []).filter(s =>
      marketFilter === 'all' || strategyMarket(s.runner) === marketFilter
    ),
    [strategies, marketFilter]
  )

  const sorted = useMemo(() =>
    [...visible].sort((a, b) => {
      // Group by platform, then by the name actually shown in the row.
      const pa = RUNNER_LABEL[runnerScope(a.runner)]
      const pb = RUNNER_LABEL[runnerScope(b.runner)]
      return pa.localeCompare(pb) || (a.name || a.class_name).localeCompare(b.name || b.class_name)
    }),
    [visible]
  )

  // Stackable = the python rows currently VISIBLE (a filtered-out row can't be ticked, so it must
  // not count toward the selection either).
  const stackable = useMemo(() => sorted.filter(s => s.runner === 'python'), [sorted])
  const toggleStack = (id: string) => setStackSel(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })
  const stackCount = useMemo(
    () => stackable.filter(s => stackSel.has(s.id)).length,
    [stackable, stackSel],
  )

  const handleDeploy = async (strategyId: string) => {
    setDeployingId(strategyId)
    try {
      await deploy.mutateAsync(strategyId)
    } finally {
      setDeployingId(null)
    }
  }

  const handleCompile = async (runner: string) => {
    try {
      if (runner === 'mt5') {
        const result = await compileMt5Mut.mutateAsync()
        setActiveMt5CompileId(result.compile_job_id)
      } else {
        const result = await compileMut.mutateAsync()
        setActiveCompileId(result.compile_job_id)
      }
    } catch {
      // toast shown by hook
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="text-[13px] text-text-secondary">
            {strategies ? `${visible.length} of ${strategies.length}` : ''}
          </span>
          <MarketFilterBar value={marketFilter} onChange={setMarketFilter} />
        </div>
        <div className="flex items-center gap-2">
          {/* Appears once 2+ python strategies are ticked — same destination as Backtests → Stacks →
              New Stack, just reached from the strategy you were already looking at. */}
          {stackable.length >= 2 && (
            <button
              onClick={() => setStackOpen(true)}
              disabled={stackCount < 2}
              title={stackCount < 2 ? 'Tick 2 or more Python strategies to stack them' : `Stack ${stackCount} strategies over one instrument, timeframe and window`}
              className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium bg-gold-muted text-gold-text border border-gold-text/20 hover:bg-gold-text/15 transition-colors disabled:opacity-40 disabled:hover:bg-gold-muted"
            >
              <Layers size={12} />
              {stackCount >= 2 ? `Stack ${stackCount} strategies` : 'Stack strategies'}
            </button>
          )}
          {orphans.length > 0 && (
            <button
              onClick={() => setConfirmReconcile(true)}
              disabled={reconcile.isPending}
              title="Remove strategies whose source file was deleted — DB row + the deployed file on the VPS"
              className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium bg-neg-muted text-neg-text border border-neg/40 hover:bg-neg/15 transition-colors disabled:opacity-50"
            >
              <Trash2 size={12} />
              Reconcile ({orphans.length})
            </button>
          )}
          <button
            onClick={() => scan.mutate()}
            disabled={scan.isPending}
            className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium bg-accent text-bg-base hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            <RefreshCw size={12} className={scan.isPending ? 'animate-spin' : ''} />
            Scan Strategies
          </button>
        </div>
      </div>

      {confirmReconcile && (
        <ConfirmDeleteModal
          count={orphans.length}
          isPending={reconcile.isPending}
          confirmLabel={reconcile.isPending ? 'Removing…' : `Remove ${orphans.length}`}
          customMessage={`These strategies have no source file in the repo: ${orphans.join(', ')}. Each will be removed from the database and its deployed .cs/.mq5 deleted from the VPS.`}
          onCancel={() => setConfirmReconcile(false)}
          onConfirm={async () => {
            await reconcile.mutateAsync()
            scan.reset()
            setConfirmReconcile(false)
          }}
        />
      )}

      {/* Whichever agent could not be reached, named. `syncFailed` is the whole
          request dying (backend down); `nt8_error`/`mt5_error` are one platform
          failing while the rows still arrive. */}
      {(syncFailed || sync?.nt8_error || sync?.mt5_error) && (
        <AgentDownBanner
          className="mb-4"
          what={syncFailed ? 'backend'
            : sync?.nt8_error && sync?.mt5_error ? 'NT8 or MT5 agent'
            : sync?.nt8_error ? 'NT8 agent' : 'MT5 agent'}
          detail={sync?.nt8_error ?? sync?.mt5_error}
        />
      )}

      {isLoading ? (
        <StrategiesSkeleton />
      ) : !strategies?.length ? (
        <EmptyState
          icon={<RefreshCw size={20} />}
          title="No strategies registered"
          description='Click "Scan Strategies" to discover strategy classes in the strategies folder.'
        />
      ) : (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border-subtle">
                {stackable.length >= 2 && <th className="w-9 pl-4 py-3" title="Select Python strategies to stack" />}
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Name</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Platform</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Params</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Runs</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Status</th>
                <th className="text-left px-4 py-3 text-text-tertiary font-medium">Best Grade</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {sorted.map(s => (
                <StrategyRow
                  key={s.id}
                  strategy={s}
                  sync={syncByStrategy[s.id]}
                  isDeploying={deployingId === s.id}
                  bestGrade={strategyGrades?.[s.id]}
                  onView={() => navigate(`/strategies/${s.id}`)}
                  onRun={() => setRunStrategy(s)}
                  onDeploy={() => handleDeploy(s.id)}
                  onCompile={() => handleCompile(s.runner)}
                  onScan={() => scan.mutate()}
                  scanning={scan.isPending}
                  stackCol={stackable.length >= 2}
                  stackChecked={stackSel.has(s.id)}
                  onStackToggle={s.runner === 'python' ? () => toggleStack(s.id) : undefined}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {stackOpen && (
        <StackConfigModal
          initial={{ strategyIds: stackable.filter(s => stackSel.has(s.id)).map(s => s.id) }}
          onClose={() => { setStackOpen(false); setStackSel(new Set()) }}
        />
      )}
      {runStrategy && (
        <RunBacktestModal
          strategy={runStrategy}
          onClose={() => setRunStrategy(null)}
        />
      )}
      {activeCompileId && (
        <CompileModal
          compileJobId={activeCompileId}
          onClose={() => { setActiveCompileId(null); refetchSync() }}
          usePollHook={useCompileStatus}
        />
      )}
      {activeMt5CompileId && (
        <CompileModal
          compileJobId={activeMt5CompileId}
          title="Compiling MT5 Strategy"
          onClose={() => { setActiveMt5CompileId(null); refetchSync() }}
          usePollHook={useCompileStatusMt5}
        />
      )}
    </div>
  )
}

function StrategyRow({
  strategy: s, sync, isDeploying, bestGrade, onView, onRun, onDeploy, onCompile, onScan, scanning,
  stackCol, stackChecked, onStackToggle,
}: {
  strategy: Strategy
  sync?: StrategyFileSyncStatus
  isDeploying: boolean
  bestGrade?: { grade: string; stress_test_id: string }
  onView: () => void
  onRun: () => void
  onDeploy: () => void
  onCompile: () => void
  onScan: () => void
  scanning: boolean
  /** Stack-select column is showing at all (2+ python strategies are listed). */
  stackCol: boolean
  stackChecked: boolean
  /** Undefined on a non-python row — stacking only replays python strategies. */
  onStackToggle?: () => void
}) {
  const navigate = useNavigate()
  const needsDeploy  = sync?.needs_deploy
  const needsCompile = sync?.needs_compile
  const curVer = sync?.current_version
  const depVer = sync?.deployed_version
  // ⚠ WHAT IS RUNNING IS THE COMPILED VERSION, full stop. NT8 executes
  // `NinjaTrader.Custom.dll` and MT5 executes the `.ex5`; neither loads a source
  // file. This used to read `needsCompile ? deployed_version : compiled ?? deployed`,
  // which is wrong in exactly the branch it exists for — with a compile pending
  // it named the version you just uploaded as "running v N" while the platform
  // was still executing the previously compiled one.
  const liveVer = sync?.compiled_version ?? null
  // `=== false` — `null` means the agent could not be asked, and rendering that
  // as a missing deployment invents an alarm.
  const missingOnVps = sync?.file_exists_on_vps === false
  const isPython = s.runner === 'python'
  return (
    <tr
      onClick={onView}
      // Reachable by keyboard: the row is the only way into a strategy's page,
      // and a click handler on a `tr` is invisible to tab navigation.
      tabIndex={0}
      role="link"
      aria-label={`Open ${s.name || s.class_name}`}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onView() } }}
      className="hover:bg-bg-hover cursor-pointer transition-colors focus:outline-none focus-visible:bg-bg-hover focus-visible:ring-1 focus-visible:ring-accent/50"
    >
      {stackCol && (
        <td className="w-9 pl-4 py-3" onClick={e => e.stopPropagation()}>
          {onStackToggle && (
            <input
              type="checkbox"
              checked={stackChecked}
              onChange={onStackToggle}
              title="Include in a portfolio stack"
              className="w-3.5 h-3.5 accent-gold-text cursor-pointer align-middle"
            />
          )}
        </td>
      )}
      <td className="px-4 py-3 font-medium">
        <div className="flex items-center gap-1">
          {/* The strategy's NAME — matches StrategyDetail's heading. Showing class_name here
              meant the list said "MpcSosFadeStrategy" while the detail page said "MPC SOS Fade". */}
          {s.name || s.class_name}
          <ChevronRight size={13} className="text-text-tertiary opacity-60" />
        </div>
      </td>
      <td className="px-4 py-3"><RunnerBadge runner={s.runner} /></td>
      <td className="px-4 py-3 text-text-secondary">{s.param_schema.length}</td>
      <td className="px-4 py-3 tabular-nums">{s.run_count}</td>
      <td className="px-4 py-3">
        {/* Source changed since the last Scan — the param schema (and, for VPS runners, the
            deploy/compile state) is stale until re-scanned. Shown for ALL runners; for Python
            it's the only status pill (no deploy/compile). Click to Scan Strategies now. */}
        {s.needs_scan && (
          <button
            onClick={e => { e.stopPropagation(); onScan() }}
            disabled={scanning}
            title="This strategy's source changed since the last scan. Click to Scan Strategies and refresh its parameters."
            className="text-[11px] px-1.5 py-[2px] mb-1 rounded-full bg-warn-muted text-warn-text border border-warn-text/20 hover:bg-warn-muted/70 transition-colors flex items-center gap-1"
          >
            <RefreshCw size={10} className={scanning ? 'animate-spin' : ''} />
            {scanning ? 'Scanning…' : 'Needs scan'}
          </button>
        )}
        {sync === undefined ? null : (
          <div className="flex flex-wrap items-center gap-1.5">
            {curVer != null && (
              <span
                title={`Local v${curVer}${liveVer != null ? ` · compiled v${liveVer} is what runs`
                  : depVer != null ? ' · deployed but never compiled, so nothing of it is running'
                  : ' · not deployed'}`}
                className="text-[11px] font-mono tabular-nums px-1.5 py-[2px] rounded-full bg-bg-sunken text-text-secondary border border-border-subtle"
              >v{curVer}</span>
            )}
            {/* ⚠ ONE PILL, and the branches are ORDERED WORST-FIRST. The first
                attempt drew "Missing on VPS" as an extra chip BESIDE the
                hash-derived one, which put a green "In sync" next to a red
                "Missing on VPS" on the same row — the contradiction this fix
                exists to remove, reintroduced one line lower. Caught by
                `tests/strategies.spec.ts`, not by reading it back. */}
            {needsDeploy ? (
              <span title={depVer != null ? `Deployed v${depVer}, local is v${curVer}` : 'Never deployed'}
                className="text-[11px] px-1.5 py-[2px] rounded-full bg-warn-muted text-warn-text border border-warn-text/20">● Needs deploy</span>
            ) : missingOnVps ? (
              // The deploy record agrees with the local source while the file
              // itself has been deleted off the box by hand. Every hash-derived
              // pill would read green over nothing; `file_exists_on_vps` was
              // computed by the backend for exactly this and rendered NOWHERE
              // until 2026-08-06.
              <span title={`${sync.expected_filename} is not in the VPS strategy folder. Deploy it again.`}
                className="text-[11px] px-1.5 py-[2px] rounded-full bg-neg-muted text-neg-text border border-neg-text/25">● Missing on VPS</span>
            ) : needsCompile ? (
              <span className="text-[11px] px-1.5 py-[2px] rounded-full bg-warn-muted text-warn-text border border-warn-text/20">● Needs compile</span>
            ) : sync.file_exists_on_vps == null ? (
              // The hashes agree, but nobody could confirm the file is there.
              // "In sync" would be a claim about a VPS this app cannot see.
              <span title="The deploy record matches the local source, but the agent could not be reached to confirm the file is on the VPS."
                className="text-[11px] px-1.5 py-[2px] rounded-full bg-bg-sunken text-text-tertiary border border-border-subtle">● VPS unknown</span>
            ) : (
              <span className="text-[11px] px-1.5 py-[2px] rounded-full bg-pos-muted text-pos-text border border-pos-text/20">● In sync</span>
            )}
          </div>
        )}
      </td>
      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
        {bestGrade ? (
          <button
            onClick={() => navigate(`/stress-tests/${bestGrade.stress_test_id}`)}
            title="View best stress test result"
            className="hover:opacity-80 transition-opacity"
          >
            {/* The endpoint types `grade` as a bare string; narrow it rather
                than `as any` (this folder's no-`any` rule). An unrecognised
                letter renders nothing instead of an unstyled pill. */}
            <RobustnessGradeBadge grade={asGrade(bestGrade.grade)} size="sm" />
          </button>
        ) : (
          <span className="text-[11px] text-text-tertiary">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
          {/* ⚠ A DEPLOYING RUNNER WITH NO SYNC ROW MUST NOT OFFER "Run".
              `needsDeploy`/`needsCompile` are undefined when the sync request
              itself failed, and `undefined` is falsy — so this used to fall
              through to Run for a strategy that had never been deployed, and
              submit a backtest to an agent that was not there. A python
              strategy legitimately has no sync row (it runs in-process). */}
          {isPython || sync !== undefined ? (
            <>
              {(needsDeploy || missingOnVps) && (
                <button
                  onClick={onDeploy}
                  disabled={isDeploying}
                  title={missingOnVps && !needsDeploy
                    ? 'The deploy record matches, but the file is gone from the VPS — send it again.'
                    : undefined}
                  className="flex items-center gap-1 px-[10px] py-[4px] rounded-md text-[11px] font-medium bg-accent text-bg-base hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {isDeploying ? <RefreshCw size={10} className="animate-spin" /> : <CloudUpload size={10} />}
                  {missingOnVps && !needsDeploy ? 'Redeploy' : 'Deploy'}
                </button>
              )}
              {!needsDeploy && !missingOnVps && needsCompile && (
                <button
                  onClick={onCompile}
                  title="Compiles EVERY strategy on this platform, not only this one — the platform builds them together."
                  className="flex items-center gap-1 px-[10px] py-[4px] rounded-md text-[11px] font-medium bg-warn-muted text-warn-text border border-warn-text/30 hover:opacity-80 transition-opacity"
                >
                  <RefreshCw size={10} />
                  Compile all
                </button>
              )}
              {!needsDeploy && !missingOnVps && !needsCompile && (
                <button
                  onClick={onRun}
                  className="flex items-center gap-1 px-[10px] py-[4px] rounded-md text-[11px] font-medium bg-accent/10 text-accent border border-accent/20 hover:bg-accent/20 transition-colors"
                >
                  <Play size={10} />
                  Run
                </button>
              )}
            </>
          ) : (
            <span
              title="This strategy's deploy state could not be read, so there is nothing safe to offer here."
              className="text-[11px] text-text-tertiary"
            >unknown</span>
          )}
        </div>
      </td>
    </tr>
  )
}

function StrategiesSkeleton() {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden animate-pulse">
      {[0, 1, 2].map(i => (
        <div key={i} className="flex gap-4 px-4 py-3 border-b border-border-subtle last:border-0">
          <div className="h-4 w-40 bg-bg-hover rounded" />
          <div className="h-4 w-48 bg-bg-hover rounded" />
          <div className="h-4 w-24 bg-bg-hover rounded" />
        </div>
      ))}
    </div>
  )
}

// ── (Rulesets moved to pages/Rulesets.tsx — own top-level nav item) ──────────

// ── Files tab ─────────────────────────────────────────────────────────────────

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}


/** Status for one row of the Deployed table.
 *
 * ⚠ It takes no `vpsFiles` any more. It used to re-`find` the row's own file in
 * the listing the row was BUILT from, so the "Missing" branch was unreachable —
 * and its final `else` rendered a green "In sync" whenever `sync` was undefined,
 * i.e. it defaulted to healthy for a strategy it knew nothing about. */
function FileStatusBadge({ sync }: { sync?: StrategyFileSyncStatus }) {
  if (!sync) {
    return <span title="This file is on the VPS but matches no registered strategy, so there is nothing to compare it against."
      className="text-[11px] px-2 py-[2px] rounded-full bg-bg-sunken text-text-tertiary border border-border-subtle">● Unregistered</span>
  }
  const ver = sync.current_version
  const chip = ver != null
    ? <span className="text-[11px] font-mono tabular-nums px-1.5 py-[2px] rounded-full bg-bg-sunken text-text-secondary border border-border-subtle">v{ver}</span>
    : null
  // Content-aware, matching the Strategies tab — presence alone is not "in sync".
  const pill = sync.needs_deploy
    ? <span className="text-[11px] px-2 py-[2px] rounded-full bg-warn-muted text-warn-text border border-warn-text/20">● Needs deploy</span>
    : sync.needs_compile
    ? <span className="text-[11px] px-2 py-[2px] rounded-full bg-warn-muted text-warn-text border border-warn-text/20">● Needs compile</span>
    : <span className="text-[11px] px-2 py-[2px] rounded-full bg-pos-muted text-pos-text border border-pos-text/20">● In sync</span>
  return <div className="flex items-center gap-1.5">{chip}{pill}</div>
}

// Round status badge shown in the modal header — spinner / check / X.
function StatusIcon({ status }: { status?: 'running' | 'success' | 'failed' }) {
  if (status === 'success')
    return <div className="shrink-0 mt-0.5 size-7 rounded-full bg-pos-muted flex items-center justify-center"><CheckCircle2 size={18} className="text-pos-text" /></div>
  if (status === 'failed')
    return <div className="shrink-0 mt-0.5 size-7 rounded-full bg-neg-muted flex items-center justify-center"><XCircle size={18} className="text-neg-text" /></div>
  return <div className="shrink-0 mt-0.5 size-7 rounded-full bg-bg-sunken flex items-center justify-center"><RefreshCw size={16} className="text-accent animate-spin" /></div>
}

// A titled, color-coded block of compiler lines (errors or warnings). Each line is a
// monospace row so CS codes and line/column numbers stay aligned and readable.
function CompileSection({ label, count, tone, lines }: {
  label: string
  count: number
  tone: 'neg' | 'warn'
  lines: string[]
}) {
  const accent = tone === 'neg' ? 'text-neg-text' : 'text-warn-text'
  const Icon = tone === 'neg' ? XCircle : AlertTriangle
  return (
    <div className="space-y-2">
      <div className={`flex items-center gap-1.5 text-[12px] font-medium ${accent}`}>
        <Icon size={13} />
        <span>{count} {label}</span>
      </div>
      <div className="space-y-1.5">
        {lines.map((line, i) => (
          <div key={i} className="flex gap-2 bg-bg-sunken rounded-lg p-2.5">
            <span className="text-text-tertiary text-[11px] tabular-nums select-none shrink-0 w-5 text-right">{i + 1}</span>
            <pre className={`text-[11px] leading-relaxed whitespace-pre-wrap break-words font-mono ${accent} m-0`}>{line}</pre>
          </div>
        ))}
      </div>
    </div>
  )
}

function CompileModal({ compileJobId, onClose, title = 'Compiling NinjaScript', usePollHook }: {
  compileJobId: string
  onClose: () => void
  title?: string
  usePollHook: (id: string | null) => {
    data: import('@/types').CompileJobStatus | undefined
    isError?: boolean
    error?: unknown
  }
}) {
  // ⚠ `isError` IS READ, and that is the whole fix. The poll 502s whenever the
  // agent is unreachable, which left `job` undefined for ever → `running` true
  // → the footer holding the ONLY close button never rendered → the modal was
  // unclosable and the elapsed counter ticked up indefinitely. Page reload was
  // the only way out. Same class as the Costs pill's swallowed `isError`.
  const { data: job, isError, error } = usePollHook(compileJobId)
  const errMsg = error instanceof Error ? error.message : null

  // Tick once a second while the compile is running so the elapsed counter advances
  // smoothly. Without this, `elapsed` only recomputes when the poll hook re-fetches,
  // so it jumps in poll-sized steps. We anchor to the server's started_at when known,
  // falling back to when this modal mounted.
  const mountedAt = useRef(Date.now() / 1000)
  const [now, setNow] = useState(Date.now() / 1000)
  const running = !isError && (!job || job.status === 'running')
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => clearInterval(id)
  }, [running])

  // Escape closes it, like every other dismissible surface in the app. A modal
  // whose only exit is a conditional footer button is one failed request away
  // from trapping the reader.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const startedAt = job?.started_at ?? mountedAt.current
  const endAt = running ? now : (job?.completed_at ?? now)
  const elapsed = Math.max(0, Math.round(endAt - startedAt))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-6">
      <div className="bg-bg-surface border border-border-default rounded-2xl w-[640px] max-w-full max-h-[85vh] shadow-2xl flex flex-col overflow-hidden">
        {/* Header — status icon + title + one-line summary. The close button is
            ALWAYS here, whatever the job is doing; the footer's Close is a
            convenience, not the only exit. */}
        <div className="flex items-start gap-3 p-5 shrink-0 border-b border-border-subtle">
          <StatusIcon status={isError ? 'failed' : job?.status} />
          <div className="min-w-0 flex-1">
            <h3 className="text-text-primary font-semibold text-[15px] leading-tight">{title}</h3>
            <p className="text-[12px] mt-0.5 text-text-tertiary">
              {isError && 'Lost contact with the compiler — the compile may still be running on the VPS.'}
              {!isError && (!job || job.status === 'running') && `Compiling… ${elapsed}s elapsed`}
              {!isError && job?.status === 'success' && (
                job.warnings.length > 0
                  ? `Compiled with ${job.warnings.length} warning${job.warnings.length === 1 ? '' : 's'}`
                  : 'All strategies compiled successfully'
              )}
              {!isError && job?.status === 'failed' && `Failed — ${job.errors.length} error${job.errors.length === 1 ? '' : 's'}`}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 p-1 rounded text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body — scrollable detail */}
        <div className="px-5 py-4 overflow-y-auto grow min-h-0 space-y-4">
          {isError && (
            <div className="space-y-2">
              <p className="text-[13px] text-text-secondary">
                The compile was started, but this app can no longer read its status. Nothing here
                says whether it succeeded — check the NT8 agent, then re-open this from the
                Deployed tab.
              </p>
              {errMsg && (
                <pre className="text-[11px] leading-relaxed whitespace-pre-wrap break-words font-mono text-neg-text bg-bg-sunken rounded-lg p-2.5 m-0">{errMsg}</pre>
              )}
            </div>
          )}

          {!isError && (!job || job.status === 'running') && (
            <div className="space-y-2.5" aria-label="Compiling">
              {[0, 1, 2].map((i) => (
                <div key={i} className="flex gap-2 bg-bg-sunken rounded-lg p-2.5">
                  <div className="h-3 w-5 rounded bg-bg-hover shrink-0 animate-pulse" style={{ animationDelay: `${i * 150}ms` }} />
                  <div className="h-3 rounded bg-bg-hover animate-pulse" style={{ width: `${70 - i * 18}%`, animationDelay: `${i * 150}ms` }} />
                </div>
              ))}
            </div>
          )}

          {job?.status === 'success' && job.warnings.length === 0 && (
            <p className="text-[13px] text-text-secondary">No errors, no warnings. You're good to run a backtest.</p>
          )}

          {job?.status === 'failed' && job.errors.length > 0 && (
            <CompileSection
              label={`Error${job.errors.length === 1 ? '' : 's'}`}
              count={job.errors.length}
              tone="neg"
              lines={job.errors}
            />
          )}

          {job?.warnings && job.warnings.length > 0 && (
            <CompileSection
              label={`Warning${job.warnings.length === 1 ? '' : 's'}`}
              count={job.warnings.length}
              tone="warn"
              lines={job.warnings}
            />
          )}
        </div>

        {/* Footer */}
        {(isError || (job?.status && job.status !== 'running')) && (
          <div className="flex justify-end p-4 shrink-0 border-t border-border-subtle">
            <button onClick={onClose} className="px-4 py-2 rounded-lg bg-bg-sunken border border-border-subtle text-text-secondary text-[13px] hover:text-text-primary hover:border-border-default transition-colors">Close</button>
          </div>
        )}
      </div>
    </div>
  )
}

function FilesTab() {
  const { data: listing, isLoading, isError, refetch, dataUpdatedAt } = useStrategyFiles()
  const files = listing?.files
  const { data: sync, refetch: refetchSync } = useStrategyFileSyncStatus()
  const syncStatus = sync?.statuses
  const uploadMut = useUploadStrategyFile()
  const deleteMut = useDeleteStrategyFile()
  const compileMut = useTriggerCompile()
  const compileMt5Mut = useTriggerCompileMt5()
  const dropRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [overwriteConfirm, setOverwriteConfirm] = useState<{ file: File; filename: string } | null>(null)
  const [activeCompileId, setActiveCompileId] = useState<string | null>(null)
  const [activeMt5CompileId, setActiveMt5CompileId] = useState<string | null>(null)

  // Only show files that match a registered strategy — excludes platform defaults
  const ourFilenames = useMemo(
    () => new Set(syncStatus?.map(s => s.expected_filename) ?? []),
    [syncStatus]
  )
  const syncByFilename = useMemo(() => {
    const m: Record<string, StrategyFileSyncStatus> = {}
    syncStatus?.forEach(s => { m[s.expected_filename] = s })
    return m
  }, [syncStatus])
  const ourFiles = useMemo(
    () => (files ?? []).filter(f => ourFilenames.has(f.filename)),
    [files, ourFilenames]
  )

  const hasMt5Files = useMemo(() => ourFiles.some(f => f.platform === 'MT5'), [ourFiles])
  // Symmetry with the MT5 button: offering "Compile NT8" with no NT8 file on the
  // box is a control whose only outcome is a wasted pywinauto pass.
  const hasNt8Files = useMemo(() => ourFiles.some(f => f.platform === 'NT8'), [ourFiles])

  const sortedFiles = useMemo(() =>
    [...ourFiles].sort((a, b) =>
      a.platform.localeCompare(b.platform) || a.filename.localeCompare(b.filename)
    ),
    [ourFiles]
  )

  const lastRefreshed = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '—'

  const startCompile = async () => {
    try {
      const result = await compileMut.mutateAsync()
      setActiveCompileId(result.compile_job_id)
    } catch {
      // toast shown by hook
    }
  }

  const startCompileMt5 = async () => {
    try {
      const result = await compileMt5Mut.mutateAsync()
      setActiveMt5CompileId(result.compile_job_id)
    } catch {
      // toast shown by hook
    }
  }

  const handleFiles = useCallback((droppedFiles: FileList | null) => {
    if (!droppedFiles?.length) return
    // One at a time is the contract (the endpoint takes one file), but dropping
    // three and having two vanish with no message is not — say so.
    if (droppedFiles.length > 1) {
      toast.error(`Drop one file at a time — uploading ${droppedFiles[0].name} only.`)
    }
    const f = droppedFiles[0]
    if (!f.name.endsWith('.cs') && !f.name.endsWith('.mq5')) { toast.error('Only .cs or .mq5 files are allowed'); return }
    const existing = files?.find(vf => vf.filename === f.name)
    if (existing) {
      setOverwriteConfirm({ file: f, filename: f.name })
    } else {
      uploadMut.mutate({ filename: f.name, file: f, overwrite: false })
    }
  }, [files, uploadMut])

  const confirmOverwrite = () => {
    if (!overwriteConfirm) return
    uploadMut.mutate({ filename: overwriteConfirm.filename, file: overwriteConfirm.file, overwrite: true })
    setOverwriteConfirm(null)
  }

  useEffect(() => {
    const el = dropRef.current
    if (!el) return
    const onDragOver = (e: DragEvent) => { e.preventDefault(); setDragging(true) }
    // ⚠ `dragleave` fires when the pointer crosses onto a CHILD element, so a
    // bare handler makes the highlight flicker as you move across the zone's own
    // text. `relatedTarget` is where the pointer went — only clear when it left
    // the zone entirely.
    const onDragLeave = (e: DragEvent) => {
      const to = e.relatedTarget as Node | null
      if (!to || !el.contains(to)) setDragging(false)
    }
    const onDrop = (e: DragEvent) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer?.files ?? null) }
    el.addEventListener('dragover', onDragOver)
    el.addEventListener('dragleave', onDragLeave)
    el.addEventListener('drop', onDrop)
    return () => {
      el.removeEventListener('dragover', onDragOver)
      el.removeEventListener('dragleave', onDragLeave)
      el.removeEventListener('drop', onDrop)
    }
  }, [handleFiles])

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <span className="text-text-secondary text-[13px]">Last refreshed: {lastRefreshed}</span>
        <div className="flex items-center gap-2">
          <button onClick={() => refetch()} className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-bg-surface border border-border-subtle text-text-secondary hover:text-text-primary text-[13px]">
            <RefreshCw size={13} /> Refresh
          </button>
          {hasNt8Files && (
            <button
              onClick={startCompile}
              disabled={compileMut.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent/10 border border-accent/30 text-accent hover:bg-accent/20 text-[13px] disabled:opacity-50"
            >
              <RefreshCw size={13} className={compileMut.isPending ? 'animate-spin' : ''} />
              Compile NT8
            </button>
          )}
          {hasMt5Files && (
            <button
              onClick={startCompileMt5}
              disabled={compileMt5Mut.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-purple-500/10 border border-purple-500/30 text-purple-400 hover:bg-purple-500/20 text-[13px] disabled:opacity-50"
            >
              <RefreshCw size={13} className={compileMt5Mut.isPending ? 'animate-spin' : ''} />
              Compile MT5
            </button>
          )}
        </div>
      </div>

      <div
        ref={dropRef}
        onClick={() => fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-lg p-8 mb-6 text-center cursor-pointer transition-colors ${
          dragging ? 'border-accent bg-accent/5' : 'border-border-default hover:border-accent/50'
        }`}
      >
        <Upload size={24} className="mx-auto mb-2 text-text-tertiary" />
        <p className="text-text-secondary text-[13px]">Drop a <span className="font-mono">.cs</span> or <span className="font-mono">.mq5</span> file here to upload, or click to browse</p>
        {/* ⚠ `value = ''` after handling, or picking the SAME file twice fires no
            change event at all and the second attempt silently does nothing —
            which is exactly what happens after a failed upload or a cancelled
            overwrite, i.e. the times you most want to retry. */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".cs,.mq5"
          className="hidden"
          onChange={e => { handleFiles(e.target.files); e.target.value = '' }}
        />
        {uploadMut.isPending && (
          <div className="absolute inset-0 bg-bg-base/60 flex items-center justify-center rounded-lg">
            <span className="text-accent text-[13px]">Uploading…</span>
          </div>
        )}
      </div>

      {/* ⚠ AN EMPTY LIST AND AN UNREACHABLE BOX ARE DIFFERENT FACTS. Until
          2026-08-06 both rendered "No files deployed — drop a strategy file
          above to deploy it", so a dead NT8 agent read as a VPS with nothing on
          it. The envelope names which platform failed and the banner says so
          before the list is drawn. */}
      {(isError || listing?.nt8_error || listing?.mt5_error) && (
        <AgentDownBanner
          className="mb-4"
          what={isError ? 'backend'
            : listing?.nt8_error && listing?.mt5_error ? 'NT8 or MT5 agent'
            : listing?.nt8_error ? 'NT8 agent' : 'MT5 agent'}
          detail={listing?.nt8_error ?? listing?.mt5_error}
        />
      )}

      {isLoading ? (
        <div className="text-text-tertiary text-[13px]">Loading files…</div>
      ) : isError ? (
        <EmptyState
          icon={<WifiOff size={24} />}
          title="Can’t read the VPS strategy folder"
          description="This is not the same as an empty folder — nothing here says what is or isn’t deployed."
        />
      ) : !ourFiles.length ? (
        <EmptyState
          icon={<Upload size={24} />}
          title={listing?.nt8_error || listing?.mt5_error
            ? 'No files from the platform that answered'
            : 'No files deployed'}
          description={listing?.nt8_error || listing?.mt5_error
            ? 'One agent is unreachable, so this list is partial — see the banner above.'
            : 'Drop a strategy file above to deploy it.'}
        />
      ) : (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border-subtle text-text-tertiary text-left">
                <th className="px-4 py-2.5 font-medium">Filename</th>
                <th className="px-4 py-2.5 font-medium">Platform</th>
                <th className="px-4 py-2.5 font-medium">Size</th>
                <th className="px-4 py-2.5 font-medium">Modified</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 w-10" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {sortedFiles.map(f => (
                <tr key={f.filename} className="hover:bg-bg-sunken">
                  <td className="px-4 py-3 font-mono text-text-primary">{f.filename}</td>
                  <td className="px-4 py-3"><RunnerBadge runner={f.platform} /></td>
                  <td className="px-4 py-3 tabular-nums text-text-secondary">{fmtBytes(f.size_bytes)}</td>
                  <td className="px-4 py-3 tabular-nums text-text-secondary">{new Date(f.modified_at).toLocaleString()}</td>
                  <td className="px-4 py-3"><FileStatusBadge sync={syncByFilename[f.filename]} /></td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => setConfirmDelete(f.filename)}
                      className="p-1 rounded text-text-tertiary hover:text-neg-text hover:bg-neg-muted transition-colors"
                      title="Delete file from VPS"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {overwriteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-bg-surface border border-border-default rounded-xl p-6 w-[400px] shadow-xl">
            <h3 className="text-text-primary font-semibold mb-2">Overwrite file?</h3>
            <p className="text-text-secondary text-[13px] mb-5">
              <span className="font-mono text-text-primary">{overwriteConfirm.filename}</span> already exists on the VPS. Overwrite it?
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setOverwriteConfirm(null)} className="px-4 py-2 rounded-lg border border-border-subtle text-text-secondary text-[13px] hover:text-text-primary">Cancel</button>
              <button onClick={confirmOverwrite} className="px-4 py-2 rounded-lg bg-warn-muted text-warn-text border border-warn-text/20 text-[13px] hover:opacity-80">Overwrite</button>
            </div>
          </div>
        </div>
      )}

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-bg-surface border border-border-default rounded-xl p-6 w-[400px] shadow-xl">
            <h3 className="text-text-primary font-semibold mb-2">Delete file?</h3>
            <p className="text-text-secondary text-[13px] mb-5">
              Delete <span className="font-mono text-text-primary">{confirmDelete}</span> from the VPS? This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirmDelete(null)} className="px-4 py-2 rounded-lg border border-border-subtle text-text-secondary text-[13px] hover:text-text-primary">Cancel</button>
              <button
                onClick={() => { deleteMut.mutate(confirmDelete!); setConfirmDelete(null) }}
                className="px-4 py-2 rounded-lg bg-neg-muted text-neg-text border border-neg-text/20 text-[13px] hover:opacity-80"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* A compile changes what is COMPILED on the box, so the sync rows are
          stale the moment it finishes — the Strategies tab refetched and this
          one did not, which is one action with two behaviours. */}
      {activeCompileId && (
        <CompileModal
          compileJobId={activeCompileId}
          onClose={() => { setActiveCompileId(null); refetchSync() }}
          title="Compiling NinjaScript"
          usePollHook={useCompileStatus}
        />
      )}
      {activeMt5CompileId && (
        <CompileModal
          compileJobId={activeMt5CompileId}
          onClose={() => { setActiveMt5CompileId(null); refetchSync() }}
          title="Compiling MQL5 (MetaEditor)"
          usePollHook={useCompileStatusMt5}
        />
      )}
    </div>
  )
}

// ── Page shell ────────────────────────────────────────────────────────────────

export function Strategies() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const rawTab = searchParams.get('tab')
  const tab = (rawTab === 'deployed' ? 'deployed' : 'strategies') as Tab
  // ⚠ MERGE, never rebuild. `setSearchParams({tab})` replaces the WHOLE query
  // string, so switching tabs silently dropped `market` — the same defect the
  // Bots page fixed for its `?bot=` selection.
  const setTab = (t: Tab) => setSearchParams(prev => {
    const next = new URLSearchParams(prev)
    next.set('tab', t)
    return next
  }, { replace: true })

  // Rulesets moved to their own top-level page — redirect old deep links.
  useEffect(() => {
    if (rawTab === 'rulesets') navigate('/rulesets', { replace: true })
  }, [rawTab, navigate])

  const { data: strategies } = useStrategies()
  // ⚠ These two are the DEPLOYED tab's data, and the shell subscribes to them
  // only to number its badge — two VPS round trips a minute (~0.82s each,
  // measured) to render one integer. They are deliberately NOT gated on the
  // active tab: TanStack shares one cache entry per key, so `FilesTab` would
  // fetch them anyway the moment you switch, and gating here would only add a
  // spinner on arrival. The cost is real and it is the badge's price.
  const { data: listing } = useStrategyFiles()
  const { data: sync } = useStrategyFileSyncStatus()

  const deployedCount = useMemo(() => {
    if (!listing?.files || !sync?.statuses) return undefined
    const ourFilenames = new Set(sync.statuses.map(s => s.expected_filename))
    return listing.files.filter(f => ourFilenames.has(f.filename)).length
  }, [listing, sync])

  const counts: Partial<Record<Tab, number>> = {
    strategies: strategies?.length,
    deployed:   deployedCount,
  }

  return (
    <div>
      <StickyHeader>
        {scrolled => (
          <>
            <div className={`flex items-end gap-3 transition-all duration-200 ${scrolled ? 'mb-2.5' : 'mb-[18px]'}`}>
              <h1 className={`font-semibold transition-all duration-200 ${scrolled ? 'text-[16px]' : 'text-h1'}`}>Strategies</h1>
            </div>
            <TabBar active={tab} onChange={setTab} counts={counts} />
          </>
        )}
      </StickyHeader>
      {tab === 'strategies' && <StrategiesTab />}
      {tab === 'deployed'   && <FilesTab />}
    </div>
  )
}
