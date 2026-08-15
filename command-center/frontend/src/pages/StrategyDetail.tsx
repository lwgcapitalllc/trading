import { useState, useRef, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Play, Pencil, Check, X, ArrowRight, ChevronRight } from 'lucide-react'
import {
  useStrategy,
  useBacktestRuns,
  useUpdateStrategyDescription,
  useStacks,
} from '@/hooks/useLab'
import { RunBacktestModal } from '@/components/RunBacktestModal'
import { EmptyState } from '@/components/EmptyState'
import { RunnerBadge } from '@/components/RunnerBadge'
import { runnerScope, runnerMarket, RUNNER_FULL_LABEL } from '@/lib/runner'
import type { ParamSchemaEntry, StrategyStep } from '@/types'

const CORRELATED_PAIRS: [string, string][] = [
  ['MES', 'MNQ'],
  ['ES', 'NQ'],
  ['GC', 'MGC'],
  ['CL', 'MCL'],
  ['MYM', 'M2K'],
  ['ES', 'MES'],
  ['NQ', 'MNQ'],
]

const CATEGORY_LABEL: Record<string, string> = {
  mean_reversion: 'Mean reversion',
  breakout: 'Breakout',
  momentum: 'Momentum',
}

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtMoney(n: number | null): string {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const prefix = n < 0 ? '-' : '+'
  if (abs >= 1_000) return `${prefix}$${(abs / 1_000).toFixed(1)}k`
  return `${prefix}$${abs.toFixed(0)}`
}

function slug(s: string): string {
  return 'grp-' + s.replace(/[^a-z0-9]+/gi, '-').toLowerCase()
}

// ── Param helpers (all driven by the meta.json overlay) ───────────────────────

function paramLabel(p: ParamSchemaEntry): string {
  return p.label ?? p.display_name
}
function paramDesc(p: ParamSchemaEntry): string | undefined {
  return p.desc ?? p.description
}
function isBoolLike(p: ParamSchemaEntry): boolean {
  return p.type === 'bool' || p.widget === 'toggle' || p.widget === 'switch'
}
function boolDefault(p: ParamSchemaEntry): boolean {
  return p.default === true || p.default === 'true'
}
function boolStates(p: ParamSchemaEntry): { off: string; on: string } {
  return p.options ?? { off: 'Off', on: 'On' }
}

/** The headline default value, as a string (state label for booleans). */
function defaultValue(p: ParamSchemaEntry): string {
  if (isBoolLike(p)) {
    const s = boolStates(p)
    return boolDefault(p) ? s.on : s.off
  }
  return String(p.default ?? '—')
}

/** "only when X = Y" text for a param's show_if condition. */
function conditionText(p: ParamSchemaEntry, byName: Map<string, ParamSchemaEntry>): string | null {
  if (!p.show_if) return null
  const parts = Object.entries(p.show_if).map(([name, val]) => {
    const ref = byName.get(name)
    const lbl = ref ? paramLabel(ref) : name
    if (ref && isBoolLike(ref)) {
      const s = boolStates(ref)
      return `${lbl} = ${val === true || val === 'true' ? s.on : s.off}`
    }
    return `${lbl} = ${String(val)}`
  })
  return `only when ${parts.join(' · ')}`
}

// ── Grouping ──────────────────────────────────────────────────────────────────

interface Group {
  name: string
  params: ParamSchemaEntry[]
  coreCount: number
}

function groupParams(schema: ParamSchemaEntry[]): Group[] {
  const order: string[] = []
  const map = new Map<string, ParamSchemaEntry[]>()
  for (const p of schema) {
    if (p.category === 'foundational') continue
    // ⚠ A SETTLED param is dropped here unconditionally, unlike in `ParamEditor` — this page
    // describes the strategy rather than configuring a run, so there is no per-run value that
    // could be sitting off its default and go unseen. The count is reported below the table.
    if (p.hidden) continue
    const g = p.group || 'Parameters'
    if (!map.has(g)) {
      map.set(g, [])
      order.push(g)
    }
    map.get(g)!.push(p)
  }
  return order.map((name) => ({
    name,
    params: map.get(name)!,
    coreCount: map.get(name)!.filter((p) => p.core).length,
  }))
}

// ── Param table row ───────────────────────────────────────────────────────────

function ParamRow({ p, byName }: { p: ParamSchemaEntry; byName: Map<string, ParamSchemaEntry> }) {
  const cond = conditionText(p, byName)
  const desc = paramDesc(p)
  const states = boolStates(p)
  return (
    <tr className="border-t border-border-subtle first:border-t-0 hover:bg-bg-hover transition-colors">
      <td className="px-4 py-3 align-top w-[24%]">
        <div className="text-[13px] font-semibold flex items-center gap-1.5">
          {paramLabel(p)}
          {p.core && (
            <span className="text-accent text-[11px]" title="Essential — changes behaviour most">
              ★
            </span>
          )}
        </div>
        <div className="text-[10px] text-text-tertiary font-mono mt-0.5">{p.name}</div>
        {cond && (
          <div className="inline-block text-[9.5px] text-gold-text bg-gold-muted border border-gold-text/25 rounded px-1.5 py-px mt-1">
            {cond}
          </div>
        )}
      </td>
      <td className="px-4 py-3 align-top text-[12px] text-text-secondary leading-[1.5] max-w-[400px]">
        {desc ?? '—'}
      </td>
      <td className="px-4 py-3 align-top whitespace-nowrap">
        <span className="text-[13px] font-semibold text-accent-text">
          {isBoolLike(p) ? (
            defaultValue(p)
          ) : (
            <>
              {String(p.default ?? '—')}
              {p.unit && (
                <span className="text-text-tertiary font-medium text-[11px]"> {p.unit}</span>
              )}
            </>
          )}
        </span>
      </td>
      <td className="px-4 py-3 align-top text-[11px] text-text-tertiary leading-[1.45] max-w-[230px]">
        {isBoolLike(p) ? (
          <span>
            <b className="text-text-secondary">Off</b> {states.off} ·{' '}
            <b className="text-text-secondary">On</b> {states.on}
          </span>
        ) : p.guide ? (
          <>
            <span className="text-accent-text block">↓ {p.guide[0]}</span>
            <span className="text-gold-text block">↑ {p.guide[1]}</span>
          </>
        ) : (
          '—'
        )}
      </td>
    </tr>
  )
}

// ── Collapsible group of params ───────────────────────────────────────────────

function GroupTable({
  group,
  byName,
  open,
  essOnly,
  onToggle,
}: {
  group: Group
  byName: Map<string, ParamSchemaEntry>
  open: boolean
  essOnly: boolean
  onToggle: () => void
}) {
  const rows = essOnly ? group.params.filter((p) => p.core) : group.params
  const isOpen = essOnly ? true : open
  return (
    <div
      id={slug(group.name)}
      className="border border-border-subtle rounded-xl bg-bg-surface overflow-hidden mb-2.5 scroll-mt-16"
    >
      <button
        onClick={onToggle}
        className={`w-full flex items-center gap-3 px-4 py-3 bg-bg-sunken hover:bg-bg-surface2 text-left transition-colors ${isOpen ? 'border-b border-border-default' : ''}`}
      >
        <ChevronRight
          size={15}
          className={`text-text-secondary transition-transform ${isOpen ? 'rotate-90' : ''}`}
        />
        <span className="text-[13.5px] font-semibold text-text-primary">{group.name}</span>
        <span className="ml-auto flex items-center gap-2 text-[11px] text-text-tertiary">
          {group.coreCount > 0 && (
            <span className="text-accent-text bg-accent-muted border border-accent/25 rounded-pill px-2 py-px font-semibold">
              {group.coreCount} ★
            </span>
          )}
          <span>
            {group.params.length} param{group.params.length !== 1 ? 's' : ''}
          </span>
        </span>
      </button>
      {isOpen && (
        <table className="w-full">
          <thead>
            <tr>
              <th className="text-left px-4 py-2 text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.5px] border-b border-border-subtle">
                Parameter
              </th>
              <th className="text-left px-4 py-2 text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.5px] border-b border-border-subtle">
                What it does
              </th>
              <th className="text-left px-4 py-2 text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.5px] border-b border-border-subtle">
                Default
              </th>
              <th className="text-left px-4 py-2 text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.5px] border-b border-border-subtle">
                Tuning effect
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <ParamRow key={p.name} p={p} byName={byName} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ── Aside cards ───────────────────────────────────────────────────────────────

function AsideCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-xl overflow-hidden">
      <h3 className="text-[10.5px] font-bold text-text-secondary uppercase tracking-[0.7px] px-3.5 py-2.5 bg-bg-sunken border-b border-border-subtle">
        {title}
      </h3>
      <div className="px-3.5 py-1.5">{children}</div>
    </div>
  )
}

function ColHead({ children }: { children: React.ReactNode }) {
  // Fixed height so the side panel and the param column start on exactly the same line.
  return <div className="h-[30px] flex items-center justify-between mb-3">{children}</div>
}

// ── Page ──────────────────────────────────────────────────────────────────────

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
  const [editingDesc, setEditingDesc] = useState(false)
  const [descDraft, setDescDraft] = useState('')
  const [essOnly, setEssOnly] = useState(false)
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})
  const descInputRef = useRef<HTMLTextAreaElement>(null)
  const updateDesc = useUpdateStrategyDescription()

  const { data: strategy, isLoading } = useStrategy(strategyId ?? null)
  const { data: runs } = useBacktestRuns(strategyId ? { strategy_id: strategyId } : undefined)
  // Shares the Stacks tab's own cache entry — this is a lookup over a list the app already holds,
  // not a new endpoint, so it costs nothing on a page that is already open elsewhere.
  const { data: allStacks } = useStacks()
  const stacksWithThis = useMemo(
    () => (allStacks ?? []).filter((s) => s.strategy_ids?.includes(strategyId ?? '')),
    [allStacks, strategyId]
  )

  const groups = useMemo(() => (strategy ? groupParams(strategy.param_schema) : []), [strategy])
  const byName = useMemo(
    () => new Map((strategy?.param_schema ?? []).map((p) => [p.name, p])),
    [strategy]
  )

  // Default open state: groups that hold an essential param. Set once per strategy.
  useEffect(() => {
    if (!strategy) return
    setOpenGroups(
      Object.fromEntries(groupParams(strategy.param_schema).map((g) => [g.name, g.coreCount > 0]))
    )
  }, [strategy?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (editingDesc) descInputRef.current?.focus()
  }, [editingDesc])

  if (isLoading) {
    return (
      <div>
        <button
          onClick={() => navigate('/strategies')}
          className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
        >
          <ArrowLeft size={14} /> Strategies
        </button>
        <Skeleton />
      </div>
    )
  }
  if (!strategy) {
    return (
      <div>
        <button
          onClick={() => navigate('/strategies')}
          className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
        >
          <ArrowLeft size={14} /> Strategies
        </button>
        <EmptyState
          icon={<Play size={20} />}
          title="Strategy not found"
          description="This strategy may have been removed."
        />
      </div>
    )
  }

  const market = runnerMarket(strategy.runner)
  const visibleParams = strategy.param_schema.filter(
    (p) => p.category !== 'foundational' && !p.hidden
  )
  const settledParams = strategy.param_schema.filter(
    (p) => p.category !== 'foundational' && p.hidden
  )
  const essentialCount = visibleParams.filter((p) => p.core).length
  const essentials = visibleParams.filter((p) => p.core)
  const categoryLabel = strategy.category
    ? (CATEGORY_LABEL[strategy.category] ?? strategy.category.replace(/_/g, ' '))
    : null
  const steps: StrategyStep[] = strategy.steps ?? []

  const completedInstruments = [
    ...new Set((runs?.filter((r) => r.status === 'complete') ?? []).map((r) => r.instrument)),
  ]
  const correlatedPairs = CORRELATED_PAIRS.filter(
    ([a, b]) => completedInstruments.includes(a) && completedInstruments.includes(b)
  )

  const total = runs?.length ?? 0
  const completed = runs?.filter((r) => r.status === 'complete' && r.net_pnl != null) ?? []
  const bestPnl = completed.length ? Math.max(...completed.map((r) => r.net_pnl as number)) : null
  const instrumentCount = new Set((runs ?? []).map((r) => r.instrument)).size

  const saveDesc = () => {
    updateDesc.mutate({ strategyId: strategy.id, description: descDraft })
    setEditingDesc(false)
  }
  const setAll = (v: boolean) => setOpenGroups(Object.fromEntries(groups.map((g) => [g.name, v])))
  const jumpTo = (name: string) => {
    setOpenGroups((prev) => ({ ...prev, [name]: true }))
    document.getElementById(slug(name))?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div>
      <button
        onClick={() => navigate('/strategies')}
        className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
      >
        <ArrowLeft size={14} /> Strategies
      </button>

      {/* Header */}
      <div className="flex items-center justify-between gap-4 mb-3.5">
        <h1 className="text-[22px] font-bold leading-tight">{strategy.name}</h1>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-1.5 px-4 py-2 rounded-md text-[13px] font-semibold bg-accent text-bg-base hover:opacity-90 transition-opacity flex-shrink-0"
        >
          <Play size={13} /> Run Backtest
        </button>
      </div>

      {/* Labeled chips — no ambiguity about what each value means */}
      <div className="flex flex-wrap gap-2 mb-6">
        {categoryLabel && (
          <span className="inline-flex items-center gap-1.5 border border-border-subtle bg-bg-surface rounded-md px-2.5 py-1 text-[12px]">
            <span className="text-[10px] uppercase tracking-[0.5px] text-text-tertiary font-semibold">
              Type
            </span>
            <span className="font-semibold text-warn-text">{categoryLabel}</span>
          </span>
        )}
        <span className="inline-flex items-center gap-1.5 border border-border-subtle bg-bg-surface rounded-md px-2.5 py-1 text-[12px]">
          <span className="text-[10px] uppercase tracking-[0.5px] text-text-tertiary font-semibold">
            Runs on
          </span>
          <RunnerBadge runner={strategy.runner} size={15} className="rounded" />
          <span className="font-semibold">{RUNNER_FULL_LABEL[runnerScope(strategy.runner)]}</span>
        </span>
        <span className="inline-flex items-center gap-1.5 border border-border-subtle bg-bg-surface rounded-md px-2.5 py-1 text-[12px]">
          <span className="text-[10px] uppercase tracking-[0.5px] text-text-tertiary font-semibold">
            Market
          </span>
          <span className="font-semibold capitalize">{market}</span>
        </span>
        <span className="inline-flex items-center gap-1.5 border border-border-subtle bg-bg-surface rounded-md px-2.5 py-1 text-[12px]">
          <span className="text-[10px] uppercase tracking-[0.5px] text-text-tertiary font-semibold">
            Parameters
          </span>
          <span className="font-semibold">
            {visibleParams.length}
            {essentialCount ? ` · ${essentialCount} essential` : ''}
          </span>
        </span>
      </div>

      {/* Which portfolio stacks this strategy is in.
          The Strategies LIST can START a stack (tick 2+ python rows) and nothing anywhere could
          answer the reverse — given a strategy, what has it already been run alongside? That is
          the question this page exists for, and on a repo whose stated design is that sample size
          arrives at the PORTFOLIO level it is the one a reader asks before running anything.
          ⚠ Matched on `strategy_ids`, never on the joined display names. */}
      {stacksWithThis.length > 0 && (
        <div className="mb-7" data-testid="strategy-stacks">
          <p className="text-[10.5px] font-bold uppercase tracking-[0.6px] text-text-tertiary mb-2">
            In {stacksWithThis.length} portfolio stack{stacksWithThis.length === 1 ? '' : 's'}
          </p>
          <div className="flex flex-wrap gap-2">
            {stacksWithThis.map((st) => (
              <button
                key={st.stack_id}
                onClick={() => navigate(`/backtests/stacks/${st.stack_id}`)}
                className="inline-flex items-center gap-2 border border-border-subtle bg-bg-surface hover:bg-bg-hover
                           rounded-md px-2.5 py-1.5 text-[12px] transition-colors"
              >
                {/* ⚠ The WINDOW and the MODE are on the chip, not just the leg names. Driven
                    against the live lab, all three of this strategy's stacks are the same two
                    legs on XAUUSD — so a chip naming only those is three identical buttons and
                    the reader cannot tell which one they are opening. */}
                <span className="font-medium">{st.strategy_names}</span>
                <span className="text-text-tertiary font-mono tabular-nums">
                  {st.instrument} · {st.start_date} → {st.end_date}
                </span>
                <span
                  className={`text-[10px] uppercase tracking-[0.4px] font-semibold ${
                    st.mode === 'shared' ? 'text-accent' : 'text-text-tertiary'
                  }`}
                >
                  {st.mode === 'shared' ? 'Shared' : 'Screen'}
                </span>
                <ChevronRight size={12} className="text-text-tertiary" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Overview */}
      <div className="border border-border-subtle rounded-2xl bg-gradient-to-b from-bg-surface to-bg-sunken mb-7 overflow-hidden">
        <div className="px-[22px] py-5">
          <p className="text-[10.5px] font-bold uppercase tracking-[0.6px] text-text-tertiary mb-2">
            What it does
          </p>
          {editingDesc ? (
            <div>
              <textarea
                ref={descInputRef}
                value={descDraft}
                onChange={(e) => setDescDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) saveDesc()
                  if (e.key === 'Escape') setEditingDesc(false)
                }}
                rows={3}
                placeholder="Describe what this strategy does…"
                className="w-full bg-bg-sunken border border-border-default rounded-md px-3 py-2 text-[14px] text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent transition-colors resize-none leading-[1.6] max-w-[820px]"
              />
              <div className="flex items-center gap-2 mt-2">
                <button
                  onClick={saveDesc}
                  className="p-1.5 rounded text-pos-text hover:bg-pos-muted transition-colors"
                >
                  <Check size={14} />
                </button>
                <button
                  onClick={() => setEditingDesc(false)}
                  className="p-1.5 rounded text-text-tertiary hover:bg-bg-hover transition-colors"
                >
                  <X size={14} />
                </button>
                <span className="text-[11px] text-text-tertiary">⌘+Enter to save</span>
              </div>
            </div>
          ) : (
            <button
              onClick={() => {
                setDescDraft(strategy.description ?? '')
                setEditingDesc(true)
              }}
              className="group flex items-start gap-2 text-left"
            >
              {strategy.description ? (
                <span className="text-[14px] text-text-secondary leading-[1.65] max-w-[820px]">
                  {strategy.description}
                </span>
              ) : (
                <span className="text-[14px] text-text-tertiary italic">
                  Add a description of what this strategy does…
                </span>
              )}
              <Pencil
                size={12}
                className="opacity-0 group-hover:opacity-50 transition-opacity flex-shrink-0 mt-1.5"
              />
            </button>
          )}

          {steps.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-4">
              {steps.map((s, i) => (
                <div key={i} className="contents">
                  <div className="flex-1 min-w-[150px] bg-bg-base border border-border-subtle rounded-[10px] px-3.5 py-3">
                    {s.label && (
                      <div className="text-[10px] font-bold text-accent tracking-[0.5px] uppercase">
                        {s.label}
                      </div>
                    )}
                    <div className="text-[12.5px] font-semibold mt-0.5">{s.title}</div>
                    {s.detail && (
                      <div className="text-[11.5px] text-text-tertiary leading-[1.45] mt-0.5">
                        {s.detail}
                      </div>
                    )}
                  </div>
                  {i < steps.length - 1 && (
                    <div className="flex items-center text-text-tertiary text-base">→</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {strategy.edge && (
          <div className="border-t border-border-subtle bg-gradient-to-b from-accent/[0.05] to-transparent px-[22px] py-4">
            <p className="text-[10.5px] font-bold uppercase tracking-[0.6px] text-accent-text mb-1.5">
              The edge
            </p>
            <p className="text-[13px] text-text-secondary leading-[1.6] max-w-[820px]">
              {strategy.edge}
            </p>
          </div>
        )}
      </div>

      {/* Two-column: side panel + grouped params */}
      <div className="grid lg:grid-cols-[288px_1fr] gap-6 items-start">
        {/* Left side panel */}
        <aside className="lg:sticky lg:top-2">
          <ColHead>
            <span className="hidden lg:block text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px]">
              Quick reference
            </span>
          </ColHead>

          <div className="flex flex-col gap-3.5">
            <AsideCard title="Jump to group">
              {groups.map((g) => (
                <button
                  key={g.name}
                  onClick={() => jumpTo(g.name)}
                  className="w-full flex justify-between items-center text-[12.5px] text-text-secondary hover:text-text-primary hover:bg-bg-hover rounded-md px-2 py-1.5 -mx-1.5 transition-colors"
                >
                  <span>{g.name}</span>
                  <span className="text-[10.5px] text-text-tertiary flex items-center gap-1.5">
                    {g.coreCount > 0 && <span className="text-accent-text">★{g.coreCount}</span>}
                    {g.params.length}
                  </span>
                </button>
              ))}
            </AsideCard>

            {essentials.length > 0 && (
              <AsideCard title="★ Essentials at a glance">
                {essentials.map((p) => (
                  <div
                    key={p.name}
                    className="flex justify-between items-baseline gap-2.5 text-[12px] py-1.5 border-t border-border-subtle first:border-t-0"
                  >
                    <span className="text-text-secondary">{paramLabel(p)}</span>
                    <span className="font-semibold text-accent-text text-[11.5px] whitespace-nowrap">
                      {defaultValue(p)}
                      {!isBoolLike(p) && p.unit ? ` ${p.unit}` : ''}
                    </span>
                  </div>
                ))}
              </AsideCard>
            )}

            <AsideCard title="Backtest runs">
              {total === 0 ? (
                <p className="text-[12.5px] text-text-tertiary py-1">
                  No runs yet. Click <span className="text-text-secondary">Run Backtest</span> to
                  start.
                </p>
              ) : (
                <>
                  <div className="flex justify-between text-[12.5px] py-1.5 border-t border-border-subtle first:border-t-0">
                    <span>Total runs</span>
                    <span className="font-semibold">{total}</span>
                  </div>
                  <div className="flex justify-between text-[12.5px] py-1.5 border-t border-border-subtle">
                    <span>Best net P&L</span>
                    <span
                      className={`font-semibold ${bestPnl != null && bestPnl >= 0 ? 'text-pos-text' : 'text-neg-text'}`}
                    >
                      {fmtMoney(bestPnl)}
                    </span>
                  </div>
                  <div className="flex justify-between text-[12.5px] py-1.5 border-t border-border-subtle">
                    <span>Instruments</span>
                    <span className="font-semibold">{instrumentCount}</span>
                  </div>
                </>
              )}
              <button
                onClick={() => navigate(`/backtests?tab=runs&market=${market}`)}
                className="flex items-center justify-center gap-1.5 w-full mt-2.5 mb-1 px-3 py-2 rounded-md text-[12px] text-text-secondary border border-border-default hover:border-accent hover:text-accent transition-colors"
              >
                View all {market} runs <ArrowRight size={13} />
              </button>
            </AsideCard>
          </div>
        </aside>

        {/* Right: grouped param tables */}
        <div>
          <ColHead>
            <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px]">
              Parameters · <span className="text-accent">★ essentials</span>
            </span>
            <div className="flex gap-1.5">
              <button
                onClick={() => setEssOnly((v) => !v)}
                className={`text-[11px] rounded-md px-2.5 py-1.5 border transition-colors ${essOnly ? 'bg-accent-muted border-accent/40 text-accent-text' : 'border-border-subtle bg-bg-surface text-text-secondary hover:border-accent hover:text-accent'}`}
              >
                ★ Essentials only
              </button>
              <button
                onClick={() => setAll(true)}
                disabled={essOnly}
                className="text-[11px] rounded-md px-2.5 py-1.5 border border-border-subtle bg-bg-surface text-text-secondary hover:border-accent hover:text-accent transition-colors disabled:opacity-40"
              >
                Expand all
              </button>
              <button
                onClick={() => setAll(false)}
                disabled={essOnly}
                className="text-[11px] rounded-md px-2.5 py-1.5 border border-border-subtle bg-bg-surface text-text-secondary hover:border-accent hover:text-accent transition-colors disabled:opacity-40"
              >
                Collapse all
              </button>
            </div>
          </ColHead>

          {visibleParams.length > 0 ? (
            groups.map((g) => (
              <GroupTable
                key={g.name}
                group={g}
                byName={byName}
                essOnly={essOnly}
                open={openGroups[g.name] ?? false}
                onToggle={() => setOpenGroups((prev) => ({ ...prev, [g.name]: !prev[g.name] }))}
              />
            ))
          ) : (
            <p className="text-[13px] text-text-tertiary">
              This strategy exposes no tunable parameters.
            </p>
          )}

          {/* ⚠ NAMED, not just counted. This page is the reference for what the strategy IS, and
              a settled param is still a rule the strategy applies — it is only the QUESTION that
              is closed, not the behaviour. Listing them is what stops the next reader (or the
              next port) concluding the strategy no longer has these levers. */}
          {settledParams.length > 0 && (
            <details className="mt-3 rounded-xl border border-border-subtle bg-bg-sunken/40 px-3.5 py-2.5">
              <summary
                data-testid="settled-params"
                className="cursor-pointer text-[12px] text-text-secondary"
              >
                {settledParams.length} settled setting{settledParams.length > 1 ? 's' : ''} — still
                in the strategy, still applied at{' '}
                {settledParams.length > 1 ? 'their defaults' : 'its default'}, kept off this table
              </summary>
              <ul className="mt-2 space-y-1">
                {settledParams.map((p) => (
                  <li key={p.name} className="text-[11.5px] text-text-tertiary">
                    <span className="text-text-secondary">{p.label || p.display_name}</span>{' '}
                    <span className="opacity-70">
                      ({p.name}) = {String(p.default)}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>

      {/* Correlated instrument note */}
      {correlatedPairs.length > 0 && (
        <div className="rounded-lg border border-warn-text/30 bg-warn-muted p-4 mt-8">
          <p className="text-sm text-warn-text font-medium mb-1">Correlated instrument note</p>
          {correlatedPairs.map(([a, b], i) => (
            <p key={i} className="text-xs text-warn-text/80">
              {a} and {b} are highly correlated. For independent confirmation, test on an
              uncorrelated instrument.
            </p>
          ))}
        </div>
      )}

      {showModal && (
        <RunBacktestModal
          strategy={strategy}
          onClose={() => setShowModal(false)}
          onSuccess={(runId) => {
            setShowModal(false)
            navigate(`/backtests/runs/${runId}`)
          }}
        />
      )}
    </div>
  )
}
