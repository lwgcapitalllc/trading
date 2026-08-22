import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Layers, X, Play, Loader2 } from 'lucide-react'
import {
  useStrategies,
  useTriggerStack,
  useRunningVpsJob,
  useStackPreview,
  useHistoryLimit,
} from '@/hooks/useLab'
import { PeriodPicker, today, yearsAgo } from '@/components/PeriodPicker'
import { useDebounced } from '@/lib/useDebounced'
import type { StackMode } from '@/types'

const BAR_PRESETS: [number, string][] = [
  [5, '5m'],
  [15, '15m'],
  [30, '30m'],
  [60, '1H'],
  [240, '4H'],
]

export interface StackConfigInitial {
  strategyIds?: string[]
  instrument?: string
  barValue?: number
  commPerSide?: number
  slippageTicks?: number
  start?: string
  end?: string
  mode?: StackMode
  accountSize?: number
  riskCapPct?: number
  entryFloorPct?: number
  // Per-leg param overrides, keyed by strategy id. A RERUN must pass what each leg actually ran
  // with — the backend falls back to the strategy's stored `default_params` for any leg it is not
  // given, so omitting this turns "rerun" into "run today's defaults" with nothing on screen
  // saying so. It is the stack's version of carrying the baseline's costs into a tuning child.
  paramsByStrategy?: Record<string, Record<string, unknown>>
}

// 🔴 THE MODE PICKER IS GONE AND EVERY NEW STACK IS A SHARED ACCOUNT (2026-08-10, Aaron's call):
// *"I would never ever ever wanna do a screen. I would always wanna do a shared account, because
// that's what a stack IS — we're sharing the same resource. I wanna know how two strategies affect
// each other and where some trades are dropped because others have taken up all the capacity."*
//
// A `screen` runs each leg on its own full account and adds the results up, so nothing can ever
// block anything — it answers a question he does not have. Offering it as an equal choice made the
// one mode he wants a coin flip, and it is the mode a `?? 'screen'` default silently picked.
//
// ⚠ The BACKEND still understands both and this is deliberately not a removal: three stacks in the
// lab are screens, `StackDetail` renders them with their `Screen · upper bound` chip, and a rerun
// of one carries its own mode forward through `initial.mode`. What is gone is the way to make a
// NEW one. Deleting screen support outright would rewrite what those stored rows mean.

// Shared config surface for BOTH "New stack" (Backtests → Stacks) and "Rerun stack" (StackDetail).
// One component so the two can never drift — a rerun exposes EXACTLY what creation does. Submitting
// always creates a NEW stack (smart-reuse means unchanged legs are reused, not re-run) and navigates
// to it. `initial` prefills every field from an existing stack for the rerun case.
export function StackConfigModal({
  title = 'New portfolio stack',
  submitLabel = 'Run stack',
  initial,
  onClose,
}: {
  title?: string
  submitLabel?: string
  initial?: StackConfigInitial
  onClose: () => void
}) {
  const navigate = useNavigate()
  const { data: strategies } = useStrategies()
  const triggerStack = useTriggerStack()
  const { data: runningJob } = useRunningVpsJob()
  const pythonBusy = !!runningJob?.python?.running

  // 🔴 A strategy flagged `requires_source` has NO SETUPS of its own — it arms off another leg's
  // closed trades. Picking it here would build a stack with nothing to read, which returns an
  // empty book that looks exactly like a rule that found no setups. It is added by ticking it
  // under its parent instead (see `recoveryFor`), never chosen from this list.
  const pyStrategies = useMemo(
    () => (strategies ?? []).filter((s) => s.runner === 'python' && !s.requires_source),
    [strategies]
  )
  const recoveryRule = useMemo(
    () => (strategies ?? []).find((s) => s.id === 'loss_recovery'),
    [strategies]
  )

  const [selected, setSelected] = useState<Set<string>>(new Set(initial?.strategyIds ?? []))
  // At most ONE recovery leg per stack, so this is the PARENT's id rather than a set. The
  // shared account keys an open position by leg NAME, and two recovery legs would both be
  // `loss_recovery` — a duplicate silently overwrites a live reservation and the cap
  // under-counts the open risk while reporting itself enforced.
  const [recoveryFor, setRecoveryFor] = useState<string | null>(null)
  const [instrument, setInstrument] = useState(initial?.instrument ?? '')
  const [start, setStart] = useState(initial?.start ?? yearsAgo(1))
  const [end, setEnd] = useState(initial?.end ?? today())
  const [barValue, setBarValue] = useState(initial?.barValue ?? 15)
  // 0/0 matches the Pine strategies (all pinned commission=0, slippage=0). The Python fill engine
  // applies real cost via the account profile (vantage_demo = 0), so these display values stay honest.
  const [commPerSide, setCommPerSide] = useState(initial?.commPerSide ?? 0)
  const [slippageTicks, setSlippageTicks] = useState(initial?.slippageTicks ?? 0)
  // A NEW stack is always shared; a RERUN keeps whatever the stored stack was, so rerunning one of
  // the three existing screens does not silently turn it into a different experiment.
  const [mode] = useState<StackMode>(initial?.mode ?? 'shared')
  const [accountSize, setAccountSize] = useState(initial?.accountSize ?? 10_000)
  const [riskCapPct, setRiskCapPct] = useState(initial?.riskCapPct ?? 10)
  const [entryFloorPct, setEntryFloorPct] = useState(initial?.entryFloorPct ?? 0)
  const shared = mode === 'shared'

  // Default the instrument to the first selected strategy's suggestion (New-stack case only).
  useEffect(() => {
    if (instrument) return
    const first = pyStrategies.find((s) => selected.has(s.id))
    if (first?.suggested_instrument) setInstrument(first.suggested_instrument)
  }, [selected, pyStrategies, instrument])

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      // Unticking a leg must take its recovery with it. Left behind, the request names a parent
      // that is not in the stack — the backend refuses it, but only after the reader has filled
      // the rest of the form, and the refusal reads as a bug rather than as a stale tick.
      if (!next.has(id)) setRecoveryFor((cur) => (cur === id ? null : cur))
      return next
    })

  const validPeriod = !!start && !!end && start < end
  // A cap of zero refuses every entry, so a "portfolio" under it takes no trades at all — the
  // backend refuses it and the button must not offer it either. Account size is guarded the same
  // way: a leg sizes off the balance, so zero produces zero-size positions.
  const accountValid = !shared || (riskCapPct > 0 && accountSize > 0)
  // 🔴 TWO **LEGS**, NOT TWO STRATEGIES. A recovery is a full leg — its own reservation, its own
  // trades, its own KPIs — so one strategy plus a recovery on it IS a stack, and it is the one the
  // recovery leg exists to make possible. Counting only ticked strategies greyed out exactly that
  // case, and the backend refused it too. The backend counts the same way (`_validate_stack_strategies`).
  const legCount = selected.size + (shared && recoveryFor ? 1 : 0)
  const settingsReady = legCount >= 2 && !!instrument.trim() && validPeriod && accountValid

  // Scoped to the legs that are actually SELECTED. The backend ignores an override for a strategy
  // outside `strategy_ids`, so this changes no result — but it does change the preview's query key,
  // and an unticked leg leaving its override behind would mint a new key for a body that means the
  // same thing.
  const paramsByStrategy = useMemo(() => {
    const src = initial?.paramsByStrategy
    if (!src) return {}
    const out: Record<string, Record<string, unknown>> = {}
    for (const id of selected) if (src[id]) out[id] = src[id]
    return out
  }, [initial?.paramsByStrategy, selected])

  // The UNION of every selected leg's feed flags, which is exactly the floor a stack needs: the
  // legs share one window, so it is legal only if EVERY leg can be served, and one leg loading a
  // 1m feed bounds the whole stack. A SHARED stack pins `exec_secondary` off (the backend does the
  // same before it runs), so it is not bounded by a feed that path never loads.
  const feedParams = useMemo(() => {
    const out: Record<string, unknown> = {}
    for (const st of pyStrategies) {
      if (!selected.has(st.id)) continue
      const p = { ...(st.default_params ?? {}), ...(paramsByStrategy[st.id] ?? {}) }
      for (const [k, v] of Object.entries(p)) if (v === true) out[k] = true
    }
    if (shared) delete out.exec_secondary
    return out
  }, [pyStrategies, selected, paramsByStrategy, shared])

  // Stacks are python-only, so the runner is fixed.
  const { data: historyLimit } = useHistoryLimit(
    instrument || null,
    'Minute',
    barValue,
    'python',
    feedParams
  )

  const previewBody = useMemo(
    () => ({
      strategy_ids: Array.from(selected),
      instrument: instrument.trim(),
      bar_type: 'Minute',
      bar_value: barValue,
      start_date: start,
      end_date: end,
      commission_per_side: commPerSide,
      slippage_ticks: slippageTicks,
      mode,
      // Sent to the PREVIEW as well as to the launch, because an override disables reuse for that
      // leg — a preview that did not know about it would badge the leg green "Reuse" and then watch
      // it re-run.
      params_by_strategy: paramsByStrategy,
    }),
    [selected, instrument, barValue, start, end, commPerSide, slippageTicks, mode, paramsByStrategy]
  )

  // ⚠ NOT asked in shared mode, and the answer is not merely unused there — it is KNOWN. A shared
  // stack reuses nothing by construction (`routers/stacks.py` refuses to drop a finished standalone
  // run, measured un-contended, into a contended portfolio), so every leg always runs. Asking would
  // be a POST that can only ever come back saying so.
  //
  // ⚠ It is also DEBOUNCED, because the query key is the whole body — so typing `XAUUSD` into the
  // instrument field minted six keys and fired six POSTs, five of them for a symbol nobody finished
  // spelling. A screen's rerun is the only path that still asks.
  const askPreview = settingsReady && !shared
  const debouncedBody = useDebounced(previewBody, 350)
  const { data: preview } = useStackPreview(debouncedBody, askPreview)
  const actionByStrategy = useMemo(() => {
    const m = new Map<string, 'reuse' | 'run'>()
    preview?.legs.forEach((l) => m.set(l.strategy_id, l.action))
    return m
  }, [preview])

  // ⚠ Derived from the MODE first, never from `preview == null`. The old expression was accidentally
  // right for a shared stack only because the preview happened to be in flight; the moment it is not
  // fetched at all, "we have no answer" and "nothing needs running" must not collapse into one.
  const nothingToRun = !shared && preview != null && preview.run_count === 0
  const canRun = settingsReady && !triggerStack.isPending && (!pythonBusy || nothingToRun)

  const submit = () => {
    if (!canRun) return
    triggerStack.mutate(
      {
        ...previewBody,
        strategy_ids: Array.from(selected),
        // Sent only in shared mode. On a screen the backend stores NULL for all three, because a
        // screen has no account — every leg traded its own — and a number here would be recorded
        // as a setting the run never had.
        ...(shared
          ? { account_size: accountSize, risk_cap_pct: riskCapPct, entry_floor_pct: entryFloorPct }
          : {}),
        // The recovery leg, if one was ticked. SHARED ONLY — on a screen every leg trades its own
        // full account, so a recovery could never take room off its parent, which is the entire
        // question it exists to answer. The backend refuses it there; this never sends it.
        ...(shared && recoveryFor ? { recovery_parent: recoveryFor } : {}),
      },
      {
        onSuccess: (res) => {
          onClose()
          navigate(`/backtests/stacks/${res.stack_id}`)
        },
      }
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[520px] shadow-2xl flex flex-col max-h-[88vh]">
        <div className="px-5 py-4 border-b border-border-subtle flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2">
            <Layers size={16} className="text-gold-text" />
            <div className="text-[15px] font-semibold">{title}</div>
          </div>
          <button
            onClick={onClose}
            className="text-text-tertiary hover:text-text-primary transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 overflow-y-auto space-y-5">
          <p className="text-[12px] text-text-secondary" data-testid="stack-mode-blurb">
            {shared
              ? 'Layer 2 or more Python strategies onto ONE balance with ONE risk budget they compete for, replayed together on one clock — so you can see where a strategy was shrunk or blocked because another was already holding the capacity. Every leg is re-run; nothing is reused.'
              : 'This stack is a SCREEN: each strategy ran on its own full account and the results were added together, so no strategy could ever block another. Rerunning keeps it a screen. New stacks are shared accounts.'}
          </p>

          {shared && (
            <div data-testid="stack-account-fields">
              <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">
                The shared account
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <div className="text-[11px] text-text-tertiary mb-1.5">Balance ($)</div>
                  <input
                    type="number"
                    step="100"
                    min="1"
                    value={accountSize}
                    onChange={(e) => setAccountSize(Number(e.target.value))}
                    className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
                  />
                </div>
                <div>
                  <div className="text-[11px] text-text-tertiary mb-1.5">Risk cap (%)</div>
                  <input
                    type="number"
                    step="0.5"
                    min="0.5"
                    value={riskCapPct}
                    onChange={(e) => setRiskCapPct(Number(e.target.value))}
                    className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
                  />
                </div>
                <div>
                  <div className="text-[11px] text-text-tertiary mb-1.5">Entry floor (%)</div>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    value={entryFloorPct}
                    onChange={(e) => setEntryFloorPct(Number(e.target.value))}
                    className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
                  />
                </div>
              </div>
              <p className="text-[11px] text-text-tertiary mt-1.5">
                The cap is the most OPEN risk all strategies may hold at once, as a % of the
                <strong className="text-text-secondary"> live </strong> balance — and an open trade
                only reserves risk down to its{' '}
                <strong className="text-text-secondary">current</strong> stop, so a stop moved to
                breakeven frees its room. An entry with no room is shrunk to fit, or skipped if what
                is left falls under the floor.
              </p>
              {!accountValid && (
                <p className="text-[11px] text-neg-text mt-1.5">
                  Balance and risk cap must both be above zero — a cap of zero refuses every entry,
                  which is a stopped bot rather than a portfolio.
                </p>
              )}
            </div>
          )}

          <div>
            <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">
              Strategies{' '}
              <span className="text-text-tertiary normal-case font-normal">· pick at least 2</span>
            </div>
            {pyStrategies.length === 0 ? (
              <div className="text-[12px] text-text-tertiary py-3">
                No Python strategies found. Scan strategies first.
              </div>
            ) : (
              <div className="space-y-1.5">
                {pyStrategies.map((s) => {
                  const on = selected.has(s.id)
                  const action = on ? actionByStrategy.get(s.id) : undefined
                  return (
                    <button
                      key={s.id}
                      onClick={() => toggle(s.id)}
                      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg border text-left transition-colors ${
                        on
                          ? 'border-accent/40 bg-accent/5'
                          : 'border-border-subtle bg-bg-sunken hover:border-border-default'
                      }`}
                    >
                      <span
                        className={`w-4 h-4 rounded flex items-center justify-center flex-shrink-0 border ${on ? 'bg-accent border-accent' : 'border-border-default'}`}
                      >
                        {on && <span className="text-bg-base text-[10px] font-bold">✓</span>}
                      </span>
                      <span className="flex-1 min-w-0">
                        <span className="text-[13px] font-medium text-text-primary">{s.name}</span>
                        {s.suggested_instrument && (
                          <span className="ml-2 text-[11px] text-text-tertiary font-mono">
                            {s.suggested_instrument}
                          </span>
                        )}
                      </span>
                      {action === 'reuse' && (
                        <span
                          className="flex-shrink-0 text-[10px] font-semibold uppercase tracking-[0.4px] text-pos-text bg-pos-muted/40 border border-pos-text/20 rounded px-1.5 py-0.5"
                          title="An existing completed run matches these exact settings — it will be reused, not re-run."
                        >
                          Reuse
                        </span>
                      )}
                      {action === 'run' && (
                        <span
                          className="flex-shrink-0 text-[10px] font-semibold uppercase tracking-[0.4px] text-warn-text bg-warn-muted/30 border border-warn-text/20 rounded px-1.5 py-0.5"
                          title="No matching run exists — this leg will be backtested fresh at the chosen timeframe and costs."
                        >
                          Run
                        </span>
                      )}
                    </button>
                  )
                })}
                {/* 🔴 THE RECOVERY LEG IS ADDED HERE, UNDER ITS PARENT, AND NOWHERE ELSE. It has
                    no setups of its own, so a picker row for it could build a stack with nothing
                    to read — an empty book that looks exactly like a rule that found nothing.
                    Nesting it under the leg whose losses it follows makes the dependency
                    impossible to get wrong rather than something the backend has to refuse. */}
                {shared && recoveryRule && selected.size > 0 && (
                  <div className="pl-6 pt-0.5">
                    <button
                      onClick={() => {
                        const parent = recoveryFor
                          ? null
                          : (Array.from(selected).find((id) =>
                              pyStrategies.some((p) => p.id === id)
                            ) ?? null)
                        setRecoveryFor(parent)
                      }}
                      data-testid="recovery-toggle"
                      className={`w-full flex items-center gap-2.5 px-3 py-1.5 rounded-lg border text-left transition-colors ${
                        recoveryFor
                          ? 'border-accent/40 bg-accent/5'
                          : 'border-border-subtle bg-bg-sunken hover:border-border-default'
                      }`}
                    >
                      <span
                        className={`w-4 h-4 rounded flex items-center justify-center flex-shrink-0 border ${recoveryFor ? 'bg-accent border-accent' : 'border-border-default'}`}
                      >
                        {recoveryFor && (
                          <span className="text-bg-base text-[10px] font-bold">✓</span>
                        )}
                      </span>
                      <span className="flex-1 min-w-0">
                        <span className="text-[12px] text-text-secondary">
                          Also run loss recovery on{' '}
                          {pyStrategies.find(
                            (p) => p.id === (recoveryFor ?? Array.from(selected)[0])
                          )?.name ?? 'the first leg'}
                          &apos;s losses
                        </span>
                      </span>
                      <span
                        className="flex-shrink-0 text-[10px] font-semibold uppercase tracking-[0.4px] text-text-tertiary border border-border-subtle rounded px-1.5 py-0.5"
                        title="It has no setups of its own — after that strategy loses, it takes a smaller trade the other way. It competes for the same risk budget, so it can shrink or block the leg it follows."
                      >
                        Extra leg
                      </span>
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          <div>
            <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">
              Instrument
            </div>
            <input
              value={instrument}
              onChange={(e) => setInstrument(e.target.value)}
              placeholder="e.g. XAUUSD"
              className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
            />
            <p className="text-[11px] text-text-tertiary mt-1.5">
              Every strategy in the stack runs on this one instrument, timeframe, and cost profile —
              so its P&amp;L matches the standalone run you designed.
            </p>
          </div>

          <div>
            <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">
              Timeframe
            </div>
            <div className="flex gap-1.5">
              {BAR_PRESETS.map(([v, label]) => (
                <button
                  key={v}
                  onClick={() => setBarValue(v)}
                  className={`px-3 py-1.5 rounded-md text-[12px] font-medium border transition-colors ${
                    barValue === v
                      ? 'border-accent bg-accent/10 text-accent'
                      : 'border-border-subtle bg-bg-sunken text-text-secondary hover:border-border-default'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">
                Commission / side
              </div>
              <input
                type="number"
                step="0.01"
                min="0"
                value={commPerSide}
                onChange={(e) => setCommPerSide(Number(e.target.value))}
                className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
              />
            </div>
            <div>
              <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">
                Slippage (ticks)
              </div>
              <input
                type="number"
                step="1"
                min="0"
                value={slippageTicks}
                onChange={(e) => setSlippageTicks(Number(e.target.value))}
                className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
              />
            </div>
          </div>

          <div>
            <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">
              Period
            </div>
            <PeriodPicker
              start={start}
              end={end}
              onChange={(s, e) => {
                setStart(s)
                setEnd(e)
              }}
              limit={historyLimit}
            />
          </div>

          {settingsReady && shared && (
            <div className="text-[12px] text-text-secondary bg-bg-sunken border border-border-subtle rounded-lg px-3 py-2">
              <span className="text-warn-text font-semibold">{selected.size + 1} replays</span> —
              the strategies together, then each one{' '}
              <strong className="text-text-secondary">alone</strong> as the control. Without the
              solo run a difference is a mixture of <em>the cap bit</em> and
              <em> the shared balance re-sized everything</em>, and nothing afterwards separates
              them.
            </div>
          )}

          {settingsReady && !shared && preview && (
            <div className="text-[12px] text-text-secondary bg-bg-sunken border border-border-subtle rounded-lg px-3 py-2">
              {preview.reuse_count > 0 && (
                <span>
                  <span className="text-pos-text font-semibold">{preview.reuse_count}</span> reused
                  from existing runs
                </span>
              )}
              {preview.reuse_count > 0 && preview.run_count > 0 && (
                <span className="text-text-tertiary"> · </span>
              )}
              {preview.run_count > 0 && (
                <span>
                  <span className="text-warn-text font-semibold">{preview.run_count}</span> to
                  backtest now
                </span>
              )}
              {preview.run_count === 0 && (
                <span className="text-text-tertiary"> · assembled instantly, no re-run</span>
              )}
            </div>
          )}

          {pythonBusy && !nothingToRun && (
            <div className="flex items-center gap-2 text-[12px] text-warn-text bg-warn-muted/30 border border-warn-text/20 rounded-lg px-3 py-2">
              <Loader2 size={13} className="animate-spin" /> A Python job is already running — the
              legs that need a fresh run must wait.
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle flex-shrink-0">
          <button
            onClick={onClose}
            className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={!canRun}
            className="flex items-center gap-1.5 px-4 py-[7px] rounded-md text-[13px] font-semibold bg-accent text-bg-base hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
          >
            <Play size={13} />
            {triggerStack.isPending
              ? 'Starting…'
              : preview && preview.run_count === 0 && selected.size >= 2
                ? 'Create stack'
                : `${submitLabel}${selected.size >= 2 ? ` (${selected.size})` : ''}`}
          </button>
        </div>
      </div>
    </div>
  )
}
