import { useState, useMemo, useRef, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { RefreshCw, Play, ChevronRight, Pencil, X, Upload, Trash2, ExternalLink, CloudUpload } from 'lucide-react'
import {
  useStrategies, useFirms,
  useScanStrategies, useUpdateRuleset,
  useStrategyFiles, useStrategyFileSyncStatus,
  useUploadStrategyFile, useDeleteStrategyFile,
  useTriggerCompile, useCompileStatus,
  useTriggerCompileMt5, useCompileStatusMt5,
  useDeployStrategy, useRunningVpsJob,
} from '@/hooks/useLab'
import { EmptyState } from '@/components/EmptyState'
import { RunBacktestModal } from '@/components/RunBacktestModal'
import RobustnessGradeBadge from '@/components/RobustnessGradeBadge'
import { useStrategyBestGrades } from '@/hooks/useStressTests'
import { RulesetTypeBadge } from '@/components/RulesetTypeBadge'
import { RunnerBadge } from '@/components/RunnerBadge'
import { toast } from 'sonner'
import type { Strategy, Ruleset, StrategyFile } from '@/types'

// ── Tab bar ───────────────────────────────────────────────────────────────────

type Tab = 'strategies' | 'rulesets' | 'deployed'

function TabBar({ active, onChange, counts }: {
  active: Tab
  onChange: (t: Tab) => void
  counts: Partial<Record<Tab, number>>
}) {
  const tabs: Array<{ id: Tab; label: string }> = [
    { id: 'strategies', label: 'Strategies' },
    { id: 'rulesets',   label: 'Rulesets' },
    { id: 'deployed',   label: 'Deployed' },
  ]
  return (
    <div className="flex gap-0 border-b border-border-subtle mb-6">
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

function strategyMarket(runner: string): 'futures' | 'forex' {
  return runner === 'mt5' ? 'forex' : 'futures'
}

function StrategiesTab() {
  const navigate = useNavigate()
  const { data: strategies, isLoading } = useStrategies()
  const { data: syncStatus, refetch: refetchSync } = useStrategyFileSyncStatus()
  const { data: strategyGrades } = useStrategyBestGrades()
  useRunningVpsJob()
  const scan = useScanStrategies()
  const deploy = useDeployStrategy()
  const compileMut = useTriggerCompile()
  const compileMt5Mut = useTriggerCompileMt5()
  const [activeCompileId, setActiveCompileId] = useState<string | null>(null)
  const [activeMt5CompileId, setActiveMt5CompileId] = useState<string | null>(null)
  const [runStrategy, setRunStrategy] = useState<Strategy | null>(null)
  const [deployingId, setDeployingId] = useState<string | null>(null)
  const [marketFilter, setMarketFilter] = useState<MarketFilter>('all')

  const syncMap = useMemo(() => {
    const m: Record<string, boolean> = {}
    syncStatus?.forEach(s => { m[s.strategy_id] = s.in_sync })
    return m
  }, [syncStatus])

  const compiledMap = useMemo(() => {
    const m: Record<string, boolean | null> = {}
    syncStatus?.forEach(s => { m[s.strategy_id] = s.is_compiled })
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
      const pa = a.runner === 'mt5' ? 'MT5' : 'NT8'
      const pb = b.runner === 'mt5' ? 'MT5' : 'NT8'
      return pa.localeCompare(pb) || a.class_name.localeCompare(b.class_name)
    }),
    [visible]
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
          description='Click "Scan Strategies" to discover strategy classes in the strategies folder.'
        />
      ) : (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border-subtle">
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
                  inSync={syncMap[s.id]}
                  isCompiled={compiledMap[s.id]}
                  isDeploying={deployingId === s.id}
                  bestGrade={strategyGrades?.[s.id]}
                  onView={() => navigate(`/strategies/${s.id}`)}
                  onRun={() => setRunStrategy(s)}
                  onDeploy={() => handleDeploy(s.id)}
                  onCompile={() => handleCompile(s.runner)}
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
  strategy: s, inSync, isCompiled, isDeploying, bestGrade, onView, onRun, onDeploy, onCompile,
}: {
  strategy: Strategy
  inSync?: boolean
  isCompiled?: boolean | null
  isDeploying: boolean
  bestGrade?: { grade: string; stress_test_id: string }
  onView: () => void
  onRun: () => void
  onDeploy: () => void
  onCompile: () => void
}) {
  const navigate = useNavigate()
  return (
    <tr onClick={onView} className="hover:bg-bg-hover cursor-pointer transition-colors">
      <td className="px-4 py-3 font-medium">
        <div className="flex items-center gap-1">
          {s.class_name}
          <ChevronRight size={13} className="text-text-tertiary opacity-60" />
        </div>
      </td>
      <td className="px-4 py-3"><RunnerBadge runner={s.runner} /></td>
      <td className="px-4 py-3 text-text-secondary">{s.param_schema.length}</td>
      <td className="px-4 py-3 tabular-nums">{s.run_count}</td>
      <td className="px-4 py-3">
        {inSync === undefined ? null : !inSync ? (
          <span className="text-[11px] px-1.5 py-[2px] rounded-full bg-warn-muted text-warn-text border border-warn-text/20">● Needs deploy</span>
        ) : isCompiled === false ? (
          <span className="text-[11px] px-1.5 py-[2px] rounded-full bg-warn-muted text-warn-text border border-warn-text/20">● Needs compile</span>
        ) : (
          <span className="text-[11px] px-1.5 py-[2px] rounded-full bg-pos-muted text-pos-text border border-pos-text/20">● In sync</span>
        )}
      </td>
      <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
        {bestGrade ? (
          <button
            onClick={() => navigate(`/stress-tests/${bestGrade.stress_test_id}`)}
            title="View best stress test result"
            className="hover:opacity-80 transition-opacity"
          >
            <RobustnessGradeBadge grade={bestGrade.grade as any} size="sm" />
          </button>
        ) : (
          <span className="text-[11px] text-text-tertiary">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2" onClick={e => e.stopPropagation()}>
          {!inSync && (
            <button
              onClick={onDeploy}
              disabled={isDeploying}
              className="flex items-center gap-1 px-[10px] py-[4px] rounded-md text-[11px] font-medium bg-accent text-bg-base hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {isDeploying ? <RefreshCw size={10} className="animate-spin" /> : <CloudUpload size={10} />}
              Deploy
            </button>
          )}
          {inSync && isCompiled === false && (
            <button
              onClick={onCompile}
              className="flex items-center gap-1 px-[10px] py-[4px] rounded-md text-[11px] font-medium bg-warn-muted text-warn-text border border-warn-text/30 hover:opacity-80 transition-opacity"
            >
              <RefreshCw size={10} />
              Compile
            </button>
          )}
          {inSync && isCompiled !== false && (
            <button
              onClick={onRun}
              className="flex items-center gap-1 px-[10px] py-[4px] rounded-md text-[11px] font-medium bg-accent/10 text-accent border border-accent/20 hover:bg-accent/20 transition-colors"
            >
              <Play size={10} />
              Run
            </button>
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

// ── Rulesets tab ──────────────────────────────────────────────────────────────

const FIRM_BRAND_NAMES: Record<string, string> = {
  lucidflex:  'LucidFlex',
  tradeify:   'Tradeify',
  fundednext: 'FundedNext',
  apex:       'Apex',
}

function firmBrand(firmId: string): string {
  const prefix = firmId.split('_')[0]
  return FIRM_BRAND_NAMES[prefix] ?? (prefix.charAt(0).toUpperCase() + prefix.slice(1))
}

// ── Foundational config edit modal ────────────────────────────────────────────

function FoundationalEditModal({ ruleset, onClose }: { ruleset: Ruleset; onClose: () => void }) {
  const update = useUpdateRuleset()
  const inputCls = 'bg-bg-sunken border border-border-subtle rounded px-2.5 py-[5px] text-[12px] text-text-primary w-full focus:outline-none focus:border-accent transition-colors'
  const labelCls = 'text-[11px] text-text-secondary block mb-1'

  const [form, setForm] = useState({
    risk_per_trade_pct:          String(ruleset.risk_per_trade_pct ?? ''),
    max_consecutive_losses:      String(ruleset.max_consecutive_losses ?? ''),
    daily_halt_fraction:         String(ruleset.daily_halt_fraction ?? ''),
    earliest_entry_time_et:      ruleset.earliest_entry_time_et ?? '',
    latest_entry_time_et:        ruleset.latest_entry_time_et ?? '',
    days_of_week_allowed:        (ruleset.days_of_week_allowed ?? []).join(','),
    daily_profit_target:         String(ruleset.daily_profit_target ?? ''),
    daily_profit_lock_pct:       String(ruleset.daily_profit_lock_pct != null ? ruleset.daily_profit_lock_pct * 100 : ''),
    default_commission_per_side: String(ruleset.default_commission_per_side ?? ''),
    default_slippage_ticks:      String(ruleset.default_slippage_ticks ?? ''),
  })

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(prev => ({ ...prev, [k]: e.target.value }))

  function handleSave() {
    const pct = parseFloat(form.daily_profit_lock_pct)
    if (form.daily_profit_lock_pct !== '' && (pct < 0 || pct > 100)) {
      toast.error('Lock-in % must be between 0 and 100'); return
    }
    const timeRe = /^([01]\d|2[0-3]):[0-5]\d$/
    for (const [field, val] of [['Earliest entry', form.earliest_entry_time_et], ['Latest entry', form.latest_entry_time_et]] as const) {
      if (val && !timeRe.test(val)) { toast.error(`${field} time must be HH:MM`); return }
    }
    const validDays = new Set(['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'])
    const days = form.days_of_week_allowed.split(',').map(d => d.trim().toLowerCase()).filter(Boolean)
    if (days.some(d => !validDays.has(d))) {
      toast.error('Days must be comma-separated: mon,tue,wed,thu,fri'); return
    }
    const lock = form.daily_profit_lock_pct !== '' ? parseFloat(form.daily_profit_lock_pct) / 100 : null
    update.mutate({
      rulesetId: ruleset.id,
      body: {
        ...ruleset,
        risk_per_trade_pct:          form.risk_per_trade_pct !== '' ? parseFloat(form.risk_per_trade_pct) : null,
        max_consecutive_losses:      form.max_consecutive_losses !== '' ? parseInt(form.max_consecutive_losses, 10) : null,
        daily_halt_fraction:         form.daily_halt_fraction !== '' ? parseFloat(form.daily_halt_fraction) : null,
        earliest_entry_time_et:      form.earliest_entry_time_et || null,
        latest_entry_time_et:        form.latest_entry_time_et || null,
        days_of_week_allowed:        days,
        daily_profit_target:         form.daily_profit_target !== '' ? parseInt(form.daily_profit_target, 10) : null,
        daily_profit_lock_pct:       lock,
        default_commission_per_side: form.default_commission_per_side !== '' ? parseFloat(form.default_commission_per_side) : null,
        default_slippage_ticks:      form.default_slippage_ticks !== '' ? parseInt(form.default_slippage_ticks, 10) : null,
      },
    }, { onSuccess: onClose })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[520px] max-h-[85vh] flex flex-col shadow-2xl">
        <div className="px-5 py-4 border-b border-border-subtle flex items-center justify-between flex-shrink-0">
          <div>
            <div className="text-[14px] font-semibold">Edit Foundational Config</div>
            <div className="text-[11px] text-text-tertiary font-mono mt-0.5">{ruleset.id}</div>
          </div>
          <button onClick={onClose} className="text-text-tertiary hover:text-text-primary transition-colors"><X size={16} /></button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          <div>
            <div className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wide mb-2">Capital &amp; Risk</div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className={labelCls}>Risk % per Trade</label><input type="number" step="0.1" min="0" max="5" className={inputCls} value={form.risk_per_trade_pct} onChange={set('risk_per_trade_pct')} placeholder="0.5" /></div>
              <div><label className={labelCls}>Daily Halt Fraction (0–1)</label><input type="number" step="0.05" min="0" max="1" className={inputCls} value={form.daily_halt_fraction} onChange={set('daily_halt_fraction')} placeholder="0.6" /></div>
              <div><label className={labelCls}>Max Consecutive Losses</label><input type="number" step="1" min="0" className={inputCls} value={form.max_consecutive_losses} onChange={set('max_consecutive_losses')} placeholder="3" /></div>
            </div>
          </div>
          <div>
            <div className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wide mb-2">Trading Hours &amp; Days</div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className={labelCls}>Earliest Entry ET (HH:MM)</label><input type="text" className={inputCls} value={form.earliest_entry_time_et} onChange={set('earliest_entry_time_et')} placeholder="09:30" /></div>
              <div><label className={labelCls}>Latest Entry ET (HH:MM)</label><input type="text" className={inputCls} value={form.latest_entry_time_et} onChange={set('latest_entry_time_et')} placeholder="15:00" /></div>
              <div className="col-span-2"><label className={labelCls}>Days Allowed (comma-separated: mon,tue,wed,thu,fri)</label><input type="text" className={inputCls} value={form.days_of_week_allowed} onChange={set('days_of_week_allowed')} placeholder="mon,tue,wed,thu,fri" /></div>
            </div>
          </div>
          <div>
            <div className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wide mb-2">Daily Goals</div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className={labelCls}>Daily Profit Target ($)</label><input type="number" step="50" min="0" className={inputCls} value={form.daily_profit_target} onChange={set('daily_profit_target')} placeholder="1500" /></div>
              <div><label className={labelCls}>Lock-In At (% of target)</label><input type="number" step="5" min="0" max="100" className={inputCls} value={form.daily_profit_lock_pct} onChange={set('daily_profit_lock_pct')} placeholder="80" /></div>
            </div>
          </div>
          <div>
            <div className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wide mb-2">Execution Defaults</div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className={labelCls}>Commission / Side ($)</label><input type="number" step="0.25" min="0" className={inputCls} value={form.default_commission_per_side} onChange={set('default_commission_per_side')} placeholder="2.25" /></div>
              <div><label className={labelCls}>Slippage (ticks)</label><input type="number" step="1" min="0" className={inputCls} value={form.default_slippage_ticks} onChange={set('default_slippage_ticks')} placeholder="1" /></div>
            </div>
          </div>
        </div>
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle flex-shrink-0">
          <button onClick={onClose} className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">Cancel</button>
          <button onClick={handleSave} disabled={update.isPending} className="px-4 py-[7px] rounded-md text-[13px] font-medium bg-accent text-bg-base hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed">
            {update.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  )
}

function RulesetsTab() {
  const { data: rulesets, isLoading } = useFirms()
  const [brandFilter, setBrandFilter] = useState<string | null>(null)

  if (isLoading) return <FirmsSkeleton />
  if (!rulesets?.length) return (
    <EmptyState
      icon={<Play size={20} />}
      title="No rulesets configured"
      description="Rulesets are seeded automatically on backend startup."
    />
  )

  const propRulesets = rulesets.filter(r => r.ruleset_type === 'prop_eval' || r.ruleset_type === 'prop_funded')
  const otherRulesets = rulesets.filter(r => r.ruleset_type !== 'prop_eval' && r.ruleset_type !== 'prop_funded')
  const brands = [...new Set(propRulesets.map(r => firmBrand(r.id)))]
  const visible = brandFilter ? [brandFilter] : brands

  return (
    <div className="space-y-6">
      {propRulesets.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="text-[11px] font-semibold text-text-tertiary uppercase tracking-wide">Prop Firm Challenges</span>
            {brands.length > 1 && (
              <div className="flex items-center gap-1">
                <button onClick={() => setBrandFilter(null)} className={`px-2.5 py-[3px] rounded text-[11px] font-medium transition-colors ${brandFilter === null ? 'bg-accent/15 text-accent' : 'text-text-tertiary hover:text-text-secondary hover:bg-bg-hover'}`}>All</button>
                {brands.map(b => (
                  <button key={b} onClick={() => setBrandFilter(brandFilter === b ? null : b)} className={`px-2.5 py-[3px] rounded text-[11px] font-medium transition-colors ${brandFilter === b ? 'bg-accent/15 text-accent' : 'text-text-tertiary hover:text-text-secondary hover:bg-bg-hover'}`}>{b}</button>
                ))}
              </div>
            )}
          </div>
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Ruleset</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Type</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Account Size</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Profit Target</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Max DD (EOD)</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Consistency</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((brand, bi) => (
                  <>
                    <tr key={`hdr-${brand}`} className={`${bi > 0 ? 'border-t-2 border-border-default' : ''} bg-accent/5 border-l-2 border-l-accent`}>
                      <td colSpan={6} className="px-4 py-2">
                        <span className="text-[12px] font-semibold text-accent uppercase tracking-[0.4px]">{brand}</span>
                      </td>
                    </tr>
                    {propRulesets.filter(r => firmBrand(r.id) === brand).map(r => (
                      <RulesetRow key={r.id} ruleset={r} />
                    ))}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {otherRulesets.length > 0 && (
        <div>
          <div className="mb-3">
            <span className="text-[11px] font-semibold text-text-tertiary uppercase tracking-wide">Personal &amp; Demo Accounts</span>
          </div>
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border-subtle">
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Ruleset</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Type</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Account Size</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Daily Cap</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Weekly Cap</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium">Daily Goal</th>
                </tr>
              </thead>
              <tbody>
                {otherRulesets.map(r => (
                  <RulesetRow key={r.id} ruleset={r} personal />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function RulesetRow({ ruleset, personal = false }: { ruleset: Ruleset; personal?: boolean }) {
  const [editing, setEditing] = useState(false)
  return (
    <>
      {editing && <FoundationalEditModal ruleset={ruleset} onClose={() => setEditing(false)} />}
      <tr className="hover:bg-bg-hover transition-colors">
        <td className="px-4 py-3">
          <div className="flex items-center gap-1.5">
            <span className="font-medium">{ruleset.name}</span>
            {ruleset.market === 'forex' && (
              <span className="text-[10px] font-bold px-1 py-[1px] rounded bg-blue-500/12 text-blue-400 border border-blue-500/20">FX</span>
            )}
            {ruleset.docs_url && (
              <a href={ruleset.docs_url} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()} title="View rules documentation" className="text-text-tertiary hover:text-accent transition-colors">
                <ExternalLink size={11} />
              </a>
            )}
            <button onClick={e => { e.stopPropagation(); setEditing(true) }} title="Edit foundational config" className="text-text-tertiary hover:text-accent transition-colors ml-0.5">
              <Pencil size={10} />
            </button>
          </div>
          <div className="text-[11px] text-text-tertiary font-mono">{ruleset.id}</div>
        </td>
        <td className="px-4 py-3"><RulesetTypeBadge ruleset_type={ruleset.ruleset_type} size="sm" /></td>
        <td className="px-4 py-3 font-mono tabular-nums">${ruleset.account_size.toLocaleString()}</td>
        {!personal ? (
          <>
            <td className="px-4 py-3 font-mono tabular-nums text-pos-text">{ruleset.profit_target > 0 ? `$${ruleset.profit_target.toLocaleString()}` : <span className="text-text-tertiary">—</span>}</td>
            <td className="px-4 py-3 font-mono tabular-nums text-neg-text">${ruleset.max_loss_eod.toLocaleString()}</td>
            <td className="px-4 py-3 text-text-secondary">{ruleset.consistency_pct != null ? `≤ ${ruleset.consistency_pct}%` : <span className="text-text-tertiary">—</span>}</td>
          </>
        ) : (
          <>
            <td className="px-4 py-3 font-mono tabular-nums text-neg-text">{ruleset.daily_loss_cap != null ? `$${ruleset.daily_loss_cap.toLocaleString()}` : <span className="text-text-tertiary">—</span>}</td>
            <td className="px-4 py-3 font-mono tabular-nums text-neg-text">{ruleset.weekly_loss_cap != null ? `$${ruleset.weekly_loss_cap.toLocaleString()}` : <span className="text-text-tertiary">—</span>}</td>
            <td className="px-4 py-3 font-mono tabular-nums text-pos-text">{ruleset.daily_profit_goal != null ? `$${ruleset.daily_profit_goal.toLocaleString()}` : <span className="text-text-tertiary">—</span>}</td>
          </>
        )}
      </tr>
    </>
  )
}

function FirmsSkeleton() {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden animate-pulse">
      {[0, 1, 2, 3].map(i => (
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

// ── Files tab ─────────────────────────────────────────────────────────────────

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}


function FileStatusBadge({ filename, vpsFiles }: { filename: string; vpsFiles: StrategyFile[] }) {
  const vpsFile = vpsFiles.find(f => f.filename === filename)
  if (!vpsFile) return <span className="text-[11px] px-2 py-[2px] rounded-full bg-neg-muted text-neg-text border border-neg-text/20">● Missing</span>
  return <span className="text-[11px] px-2 py-[2px] rounded-full bg-pos-muted text-pos-text border border-pos-text/20">● In sync</span>
}

function CompileModal({ compileJobId, onClose, title = 'Compiling NinjaScript', usePollHook }: {
  compileJobId: string
  onClose: () => void
  title?: string
  usePollHook: (id: string | null) => { data: import('@/types').CompileJobStatus | undefined }
}) {
  const { data: job } = usePollHook(compileJobId)
  const elapsed = job?.started_at ? Math.round((Date.now() / 1000) - job.started_at) : 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-bg-surface border border-border-default rounded-xl p-6 w-[480px] shadow-xl">
        <h3 className="text-text-primary font-semibold mb-4">{title}</h3>
        {(!job || job.status === 'running') && (
          <div className="text-text-secondary text-[13px] space-y-1">
            <div className="flex items-center gap-2">
              <RefreshCw size={14} className="animate-spin text-accent" />
              <span>Compiling… (Elapsed: {elapsed}s)</span>
            </div>
            <p className="text-text-tertiary text-[12px]">When complete, results will appear here.</p>
          </div>
        )}
        {job?.status === 'success' && (
          <div className="space-y-2">
            <p className="text-pos-text text-[13px]">✓ All strategies compiled successfully.</p>
            {job.warnings.length > 0 && <p className="text-warn-text text-[12px]">Warnings: {job.warnings.length}</p>}
          </div>
        )}
        {job?.status === 'failed' && (
          <div className="space-y-2">
            <p className="text-neg-text text-[13px]">✗ Compilation failed.</p>
            {job.errors.map((e, i) => (
              <pre key={i} className="text-[11px] bg-bg-sunken rounded p-2 text-neg-text whitespace-pre-wrap">{e}</pre>
            ))}
          </div>
        )}
        {job?.status && job.status !== 'running' && (
          <div className="flex justify-end mt-5">
            <button onClick={onClose} className="px-4 py-2 rounded-lg border border-border-subtle text-text-secondary text-[13px] hover:text-text-primary">Close</button>
          </div>
        )}
      </div>
    </div>
  )
}

function FilesTab() {
  const { data: files, isLoading, refetch, dataUpdatedAt } = useStrategyFiles()
  const { data: syncStatus } = useStrategyFileSyncStatus()
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
  const ourFiles = useMemo(
    () => (files ?? []).filter(f => ourFilenames.has(f.filename)),
    [files, ourFilenames]
  )

  const hasMt5Files = useMemo(() => ourFiles.some(f => f.platform === 'MT5'), [ourFiles])

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

  const handleFiles = (droppedFiles: FileList | null) => {
    if (!droppedFiles?.length) return
    const f = droppedFiles[0]
    if (!f.name.endsWith('.cs') && !f.name.endsWith('.mq5')) { toast.error('Only .cs or .mq5 files are allowed'); return }
    const existing = files?.find(vf => vf.filename === f.name)
    if (existing) {
      setOverwriteConfirm({ file: f, filename: f.name })
    } else {
      uploadMut.mutate({ filename: f.name, file: f, overwrite: false })
    }
  }

  const confirmOverwrite = () => {
    if (!overwriteConfirm) return
    uploadMut.mutate({ filename: overwriteConfirm.filename, file: overwriteConfirm.file, overwrite: true })
    setOverwriteConfirm(null)
  }

  useEffect(() => {
    const el = dropRef.current
    if (!el) return
    const onDragOver = (e: DragEvent) => { e.preventDefault(); setDragging(true) }
    const onDragLeave = () => setDragging(false)
    const onDrop = (e: DragEvent) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer?.files ?? null) }
    el.addEventListener('dragover', onDragOver)
    el.addEventListener('dragleave', onDragLeave)
    el.addEventListener('drop', onDrop)
    return () => {
      el.removeEventListener('dragover', onDragOver)
      el.removeEventListener('dragleave', onDragLeave)
      el.removeEventListener('drop', onDrop)
    }
  }, [files])

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <span className="text-text-secondary text-[13px]">Last refreshed: {lastRefreshed}</span>
        <div className="flex items-center gap-2">
          <button onClick={() => refetch()} className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-bg-surface border border-border-subtle text-text-secondary hover:text-text-primary text-[13px]">
            <RefreshCw size={13} /> Refresh
          </button>
          <button
            onClick={startCompile}
            disabled={compileMut.isPending}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-accent/10 border border-accent/30 text-accent hover:bg-accent/20 text-[13px] disabled:opacity-50"
          >
            <RefreshCw size={13} className={compileMut.isPending ? 'animate-spin' : ''} />
            Compile NT8
          </button>
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
        <input ref={fileInputRef} type="file" accept=".cs,.mq5" className="hidden" onChange={e => handleFiles(e.target.files)} />
        {uploadMut.isPending && (
          <div className="absolute inset-0 bg-bg-base/60 flex items-center justify-center rounded-lg">
            <span className="text-accent text-[13px]">Uploading…</span>
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="text-text-tertiary text-[13px]">Loading files…</div>
      ) : !ourFiles.length ? (
        <EmptyState icon={<Upload size={24} />} title="No files deployed" description="Drop a strategy file above to deploy it." />
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
                  <td className="px-4 py-3"><FileStatusBadge filename={f.filename} vpsFiles={files ?? []} /></td>
                  <td className="px-4 py-3">
                    {!f.filename.startsWith('@') && (
                      <button
                        onClick={() => setConfirmDelete(f.filename)}
                        className="p-1 rounded text-text-tertiary hover:text-neg-text hover:bg-neg-muted transition-colors"
                        title="Delete file from VPS"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
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

      {activeCompileId && (
        <CompileModal
          compileJobId={activeCompileId}
          onClose={() => setActiveCompileId(null)}
          title="Compiling NinjaScript"
          usePollHook={useCompileStatus}
        />
      )}
      {activeMt5CompileId && (
        <CompileModal
          compileJobId={activeMt5CompileId}
          onClose={() => setActiveMt5CompileId(null)}
          title="Compiling MQL5 (MetaEditor)"
          usePollHook={useCompileStatusMt5}
        />
      )}
    </div>
  )
}

// ── Page shell ────────────────────────────────────────────────────────────────

export function Strategies() {
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (searchParams.get('tab') ?? 'strategies') as Tab
  const setTab = (t: Tab) => setSearchParams({ tab: t }, { replace: true })

  const { data: strategies } = useStrategies()
  const { data: rulesets } = useFirms()
  const { data: files } = useStrategyFiles()
  const { data: syncStatus } = useStrategyFileSyncStatus()

  const deployedCount = useMemo(() => {
    if (!files || !syncStatus) return undefined
    const ourFilenames = new Set(syncStatus.map(s => s.expected_filename))
    return files.filter(f => ourFilenames.has(f.filename)).length
  }, [files, syncStatus])

  const counts: Partial<Record<Tab, number>> = {
    strategies: strategies?.length,
    rulesets:   rulesets?.length,
    deployed:   deployedCount,
  }

  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Strategies</h1>
      </div>
      <TabBar active={tab} onChange={setTab} counts={counts} />
      {tab === 'strategies' && <StrategiesTab />}
      {tab === 'rulesets'   && <RulesetsTab />}
      {tab === 'deployed'   && <FilesTab />}
    </div>
  )
}
