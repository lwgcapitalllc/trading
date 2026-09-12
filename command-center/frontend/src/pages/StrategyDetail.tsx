import { useState, useRef, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Play, Pencil, Check, X, ChevronRight } from 'lucide-react'
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
import type { ParamCondValue, ParamSchemaEntry, StrategyStep } from '@/types'

/** Stacks shown before "+N more" — two rows of chips. */
const STACKS_SHOWN = 4

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

/** One condition value in words: a list reads "A or B", and `{ gt: n }` reads "above n".
 *  🔴 It printed `String(val)` for all three shapes until 2026-09-11, so the comparison shape
 *  reached the screen as "[object Object]". The shapes are `paramConditions.ts`'s own. */
function wantText(ref: ParamSchemaEntry | undefined, val: ParamCondValue): string {
  if (Array.isArray(val)) return val.map((v) => wantText(ref, v)).join(' or ')
  if (val !== null && typeof val === 'object') return 'gt' in val ? `above ${val.gt}` : '?'
  if (ref && isBoolLike(ref)) {
    const s = boolStates(ref)
    return val === true || val === 'true' ? s.on : s.off
  }
  return String(val)
}

/** "only when X = Y" text for a param's show_if condition. */
function conditionText(p: ParamSchemaEntry, byName: Map<string, ParamSchemaEntry>): string | null {
  if (!p.show_if) return null
  const parts = Object.entries(p.show_if).map(([name, val]) => {
    const ref = byName.get(name)
    const lbl = ref ? paramLabel(ref) : name
    const isGt = val !== null && typeof val === 'object' && !Array.isArray(val)
    return isGt ? `${lbl} is ${wantText(ref, val)}` : `${lbl} = ${wantText(ref, val)}`
  })
  return `only when ${parts.join(' · ')}`
}

/** A long description, clamped to three lines with a toggle. Several run to a paragraph of
 *  measured results, which pushed every row under them off the screen. */
function ClampedText({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  if (text.length <= 260) return <>{text}</>
  return (
    <>
      <div className={open ? '' : 'line-clamp-3'}>{text}</div>
      <button
        onClick={() => setOpen((v) => !v)}
        className="mt-0.5 text-[11px] text-accent-text hover:underline"
      >
        {open ? 'Less' : 'More'}
      </button>
    </>
  )
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
        {/* The code name is on hover rather than printed under every label — it is for someone
            reading the source, and on screen it gave every row a second heading. */}
        <div className="text-[13px] font-semibold flex items-center gap-1.5" title={p.name}>
          {paramLabel(p)}
          {p.core && (
            <span className="text-gold-text text-[11px]" title="Essential — changes behaviour most">
              ★
            </span>
          )}
        </div>
        {cond && (
          <div className="inline-block text-[9.5px] text-gold-text bg-gold-muted border border-gold-text/25 rounded px-1.5 py-px mt-1">
            {cond}
          </div>
        )}
      </td>
      <td className="px-4 py-3 align-top text-[12px] text-text-secondary leading-[1.5] max-w-[400px]">
        {desc ? <ClampedText text={desc} /> : '—'}
      </td>
      <td className="px-4 py-3 align-top whitespace-nowrap">
        <span className="text-[13px] font-semibold text-text-primary">
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
            {/* The arrow says the direction; colour on both halves ranked neither (2026-09-11). */}
            <span className="text-text-secondary block">↓ {p.guide[0]}</span>
            <span className="text-text-secondary block">↑ {p.guide[1]}</span>
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
    <div className="border border-border-subtle rounded-xl bg-bg-surface overflow-hidden mb-2.5">
      <button
        onClick={onToggle}
        className={`w-full flex items-center gap-3 px-4 py-3 bg-bg-sunken hover:bg-bg-surface-2 text-left transition-colors ${isOpen ? 'border-b border-border-default' : ''}`}
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
  const [showAllStacks, setShowAllStacks] = useState(false)
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

  const saveDesc = () => {
    updateDesc.mutate({ strategyId: strategy.id, description: descDraft })
    setEditingDesc(false)
  }
  const setAll = (v: boolean) => setOpenGroups(Object.fromEntries(groups.map((g) => [g.name, v])))
  const startEditDesc = () => {
    setDescDraft(strategy.description ?? '')
    setEditingDesc(true)
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
        {/* 🔴 A rule flagged `requires_source` has NO SETUPS OF ITS OWN — it arms off another
            leg's closed trades. Run alone it returns an EMPTY book, which on every page here
            reads exactly like a rule that found no setups: no error, no warning, a run that
            completes and grades. The list page already swaps its Run for this, and the backend
            refuses it outright (`routers/_source_guard.py`) — this page had its own Run button
            and was the way round both. DISABLED, never hidden: a control that vanishes reads as
            a feature that does not exist. */}
        {strategy.requires_source ? (
          <button
            disabled
            title="This rule has no setups of its own — it only trades after another strategy loses. Add it inside a stack, under the strategy whose losses it should recover."
            className="flex items-center gap-1.5 px-4 py-2 rounded-md text-[13px] font-semibold bg-bg-sunken text-text-tertiary border border-border-subtle cursor-not-allowed flex-shrink-0"
          >
            Needs a parent
          </button>
        ) : (
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-md text-[13px] font-semibold bg-accent text-bg-base hover:opacity-90 transition-opacity flex-shrink-0"
          >
            <Play size={13} /> Run Backtest
          </button>
        )}
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
        {/* The same count as the Runs column on the Strategies list, so the two pages agree. */}
        <span className="inline-flex items-center gap-1.5 border border-border-subtle bg-bg-surface rounded-md px-2.5 py-1 text-[12px]">
          <span className="text-[10px] uppercase tracking-[0.5px] text-text-tertiary font-semibold">
            Backtests
          </span>
          <span className="font-semibold">{strategy.run_count}</span>
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
          <div className="flex flex-wrap items-center gap-2">
            {(showAllStacks ? stacksWithThis : stacksWithThis.slice(0, STACKS_SHOWN)).map((st) => (
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
            {stacksWithThis.length > STACKS_SHOWN && (
              <button
                onClick={() => setShowAllStacks((v) => !v)}
                className="text-[12px] text-text-tertiary hover:text-text-secondary px-1"
              >
                {showAllStacks ? 'Show fewer' : `+${stacksWithThis.length - STACKS_SHOWN} more`}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Overview */}
      <div className="border border-border-subtle rounded-2xl bg-gradient-to-b from-bg-surface to-bg-sunken mb-7 overflow-hidden">
        <div className="px-[22px] py-5">
          <div className="flex items-center justify-between mb-2">
            <p className="text-[10.5px] font-bold uppercase tracking-[0.6px] text-text-tertiary">
              What it does
            </p>
            {!editingDesc && !strategy.description && (
              <button
                onClick={startEditDesc}
                className="flex items-center gap-1 text-[11px] text-text-tertiary hover:text-text-secondary transition-colors"
              >
                <Pencil size={11} /> Add a description
              </button>
            )}
          </div>
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
            strategy.description && (
              <button
                onClick={startEditDesc}
                className="group flex items-start gap-2 text-left mb-2"
              >
                <span className="text-[14px] text-text-secondary leading-[1.65] max-w-[820px]">
                  {strategy.description}
                </span>
                <Pencil
                  size={12}
                  className="opacity-0 group-hover:opacity-50 transition-opacity flex-shrink-0 mt-1.5"
                />
              </button>
            )
          )}

          {/* The edge is the lead paragraph, not a box of its own under the steps. As a separate
              "The edge" section it retold the four steps in prose (2026-09-11); the meta files'
              edges were cut to what the steps do not already say. */}
          {strategy.edge && (
            <p className="text-[14px] text-text-secondary leading-[1.65] max-w-[820px]">
              {strategy.edge}
            </p>
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
      </div>

      {/* Parameters, full width. A side panel beside them said everything twice (2026-09-11): a
          jump list naming every group (the collapsed group headers already are that list), an
          "essentials at a glance" card restating the ★ rows (the ★ Essentials only button shows
          exactly those), and a runs card whose "best net P&L" compared runs taken on different
          windows and sizes. The run count moved to the header chips. */}
      <div>
        <div>
          <div className="h-[30px] flex items-center justify-between mb-3">
            <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px]">
              {visibleParams.length} parameters
              {essentialCount > 0 && (
                <span className="text-accent"> · ★ {essentialCount} essential</span>
              )}
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
          </div>

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
                {settledParams.length} settled setting{settledParams.length > 1 ? 's' : ''}, fixed
                at {settledParams.length > 1 ? 'their defaults' : 'its default'}
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
