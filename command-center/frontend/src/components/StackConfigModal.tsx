import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Layers, X, Play, Loader2 } from 'lucide-react'
import {
  useStrategies,
  useTriggerStack,
  useRunningVpsJob,
  useStackPreview,
  useHistoryLimit,
  useBrokerProfiles,
} from '@/hooks/useLab'
import { PeriodPicker, today, yearsAgo } from '@/components/PeriodPicker'
import { Divider, InfoTooltip, SectionHead, inputCls, labelCls } from '@/components/ModalKit'
import { useDebounced } from '@/lib/useDebounced'
import type { StackMode } from '@/types'

const BAR_PRESETS: [number, string][] = [
  [5, '5m'],
  [15, '15m'],
  [30, '30m'],
  [60, '1H'],
  [240, '4H'],
]

// A frame's label, resolved off the ONE preset list above. A strategy may declare a frame that
// is not a preset (nothing stops it), so this falls back to plain minutes rather than blank.
function barLabel(minutes: number): string {
  return BAR_PRESETS.find(([v]) => v === minutes)?.[1] ?? `${minutes}m`
}

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
  // The frame each leg actually RAN on, keyed by strategy id. Same reason as the params above: a
  // rerun that dropped this would silently re-run a 5m leg on the stack's fallback frame and call
  // it the same stack.
  barValuesByStrategy?: Record<string, number>
  // What the stack being rerun was CHARGED. ⚠ A rerun reproduces the stack it is rerunning, not
  // today's default — a stack stored before 2026-09-02 ran gross, and quietly defaulting it back
  // ON would make the "same" stack a different experiment. `undefined` = no opinion, so a new
  // stack gets the charged default.
  chargeCosts?: boolean
  brokerProfile?: string
}

// The per-trade risk knob. Resolved against each leg's OWN schema, so a strategy that does not
// declare it simply gets no box rather than a control that writes a field it has never heard of.
// ⚠ Named ONCE here: this is the only place the stack UI needs to know a field by name, and a
// second copy of the name is how the two come to disagree.
const RISK_FIELD = 'exec_risk_pct'

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
  // The stack's FALLBACK frame — what a leg runs on when its package declares none and the
  // reader has not picked. Kept rather than removed: a strategy that has never stated a frame has
  // to land somewhere, and a rerun of an older stack must reproduce exactly what it ran.
  // ⚠ NOT state, and that is the point: nothing on this form sets it any more. Every leg picks
  // its own frame below, and this is only what a leg falls back to when its package declares
  // none — plus what a rerun of a stack stored before per-leg frames has to reproduce.
  const barValue = initial?.barValue ?? 15
  // 🔴 THE FRAME EACH LEG RUNS ON, and only the ones the reader has actually CHANGED. A strategy
  // states the frame it was measured on (`extreme_leg` 5m, `sos_fade` 15m) and that is
  // what a leg gets unless it is overridden here. Until 2026-09-03 this form had ONE frame for
  // the whole stack, so putting those two on one account replayed one of them on a frame nobody
  // has ever measured it on — and the combined table said portfolio.
  // ⚠ Holds only EDITS, deliberately, the same shape as the per-leg risk box above: seeded from
  // the declarations it would go stale the moment a package's declaration moved, and a rerun
  // would then carry a frame from a strategy that has since been re-measured.
  const [legBar, setLegBar] = useState<Record<string, number>>(initial?.barValuesByStrategy ?? {})
  // 0/0 matches the Pine strategies (all pinned commission=0, slippage=0). The Python fill engine
  // applies real cost via the account profile (vantage_demo = 0), so these display values stay honest.
  // 🔴 NOT A CONTROL, and not state — `routers/_costs.py` reads commission off the BROKER
  // ACCOUNT and has ignored whatever was typed here since the cost switch landed. The box
  // asked for a number, showed it back, and changed nothing. It is still SENT, because a
  // rerun of a stack stored before that has to reproduce the figure it was stored with.
  const commPerSide = initial?.commPerSide ?? 0
  const [slippageTicks, setSlippageTicks] = useState(initial?.slippageTicks ?? 0)
  // A NEW stack is always shared; a RERUN keeps whatever the stored stack was, so rerunning one of
  // the three existing screens does not silently turn it into a different experiment.
  const [mode] = useState<StackMode>(initial?.mode ?? 'shared')
  const [accountSize, setAccountSize] = useState(initial?.accountSize ?? 10_000)
  const [riskCapPct, setRiskCapPct] = useState(initial?.riskCapPct ?? 10)
  const [entryFloorPct, setEntryFloorPct] = useState(initial?.entryFloorPct ?? 0)
  const shared = mode === 'shared'

  // ── Broker account, and what the stack is CHARGED ────────────────────────────
  // 🔴 Neither existed on this form until 2026-09-02, and the single-run form has had both for
  // weeks. A stack fell through to the two typed figures below — which default to zero — so
  // **every stack this lab has produced is a gross number sitting where the answer goes.**
  // ⚠ `null` until the profiles arrive, so nothing is submitted against a guess; the effect below
  // fills it once, and only while the reader has not chosen for themselves. Same shape as the Run
  // modal, deliberately — two forms that default differently is how one of them starts lying.
  const [brokerProfile, setBrokerProfile] = useState<string | null>(initial?.brokerProfile ?? null)
  const { data: brokerProfiles } = useBrokerProfiles()
  const attachedProfile = brokerProfiles?.find((b) => b.attached) ?? null
  useEffect(() => {
    if (brokerProfile != null || !brokerProfiles?.length) return
    setBrokerProfile(attachedProfile?.id ?? brokerProfiles[0].id)
  }, [brokerProfile, brokerProfiles, attachedProfile])
  const broker = brokerProfiles?.find((b) => b.id === brokerProfile) ?? null
  // ⚠ Three answers, not two. `null` = the agent could not be asked, which must never render as a
  // mismatch — the same rule the health dots follow.
  const brokerMatches: boolean | null =
    !broker || !attachedProfile ? null : broker.id === attachedProfile.id
  // A tier whose spread has never been read carries the refusal sentinel rather than a number, and
  // the backend REFUSES to run it charged. Say so before the button, not in a 400 after the click.
  const brokerUnpriced = broker != null && broker.spread < 0
  // ── Switching broker REWRITES the symbol in the box ──────────────────────────
  // 🔴 **The instrument is the strategy's and the suffix is the broker's, and nobody should have
  // to hold both in their head.** Every strategy here suggests a bare gold name — correctly,
  // because a strategy does not belong to a broker — while PU Prime quotes it with a suffix and
  // Vantage bare. The Run modal has rewritten the field since 2026-08-26; this form got the
  // broker picker on 2026-09-02 and never got the rewrite, so a stack under PU Prime asked for a
  // symbol that broker does not quote and died four layers down in the bar loader with a message
  // naming the window and the timeframe and never the field that was wrong.
  //
  // ⚠ **Keyed on the BROKER only** — not on the symbol. Rebasing on every keystroke would append
  // a suffix before somebody had finished typing the base.
  //
  // ⚠ **An EFFECT rather than the select's `onChange`, and it must stay one.** onChange fires
  // only when a HUMAN picks a broker, and the common case is the broker arriving on its own once
  // the profiles load and the default lands on the attached terminal — open the modal, press Run.
  //
  // ⚠ **A null suffix is UNRECORDED, never bare**, so the symbol is left exactly as typed:
  // stripping on a guess hands the terminal a symbol nobody has seen it quote.
  //
  // ⚠ **The BACKEND binds** — `routers/stacks.py` resolves again at creation and stores the
  // RESOLVED name. This is the half that makes the answer visible, never the half that
  // guarantees it.
  const suffix = broker?.symbol_suffix
  useEffect(() => {
    if (suffix == null) return
    setInstrument((prev) => (prev ? `${prev.split('.')[0]}${suffix}` : prev))
  }, [suffix])
  const brokerNamingUnknown = broker != null && broker.symbol_suffix == null
  const [chargeCosts, setChargeCosts] = useState(initial?.chargeCosts ?? true)

  // ── Per-leg risk ─────────────────────────────────────────────────────────────
  // Only holds legs the reader has actually EDITED. An untouched leg must send no override at
  // all: an override disables reuse for that leg, so pre-filling every one would silently turn
  // every screen rerun into a full replay.
  const [legRisk, setLegRisk] = useState<Record<string, number>>({})
  // What a leg risks today — its rerun override if it has one, else its stored default. This is
  // the number the box shows and the baseline an edit is compared against.
  const baselineRisk = (id: string): number | undefined => {
    const from = initial?.paramsByStrategy?.[id]?.[RISK_FIELD] ?? null
    if (typeof from === 'number') return from
    const d = pyStrategies.find((s) => s.id === id)?.default_params?.[RISK_FIELD]
    return typeof d === 'number' ? d : undefined
  }

  // What each SELECTED leg actually runs on: the reader's edit, else the frame the package says
  // it was measured on, else the stack fallback. One expression, so the picker, the window check
  // and the request cannot disagree about what a leg is about to be measured on.
  const barByLeg = useMemo(() => {
    const out: Record<string, number> = {}
    for (const st of pyStrategies) {
      if (!selected.has(st.id)) continue
      out[st.id] = legBar[st.id] ?? st.suggested_bar_value ?? barValue
    }
    return out
  }, [pyStrategies, selected, legBar, barValue])

  // 🔴 THE WINDOW IS BOUNDED BY THE FINEST FRAME IN THE STACK, because a broker holds less
  // history the finer the bars — so the legal start is the LATEST floor across the frames, never
  // the coarsest leg's. A window only the 15m leg can reach does not error: the 5m leg simply
  // does not exist over the early months, the 15m one compounds ALONE there, and every later
  // trade of BOTH is sized off a balance one leg built unopposed. The backend refuses it per leg;
  // this is the half that says so before the click.
  const finestBar = useMemo(() => {
    const vals = Object.values(barByLeg)
    return vals.length ? Math.min(...vals) : barValue
  }, [barByLeg, barValue])

  // Do the legs disagree about their frame? Worth saying out loud when they do: a mixed stack is
  // legal and is the point of per-leg frames, but it changes what the window has to satisfy.
  const mixedFrames = new Set(Object.values(barByLeg)).size > 1

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
  //
  // 🔴 **AN OVERRIDE REPLACES A LEG'S WHOLE SETTINGS — IT DOES NOT MERGE WITH THEM.** The backend
  // reads `params_by_strategy[id] OR the strategy's stored defaults`, never both, so sending just
  // the one field the reader edited would run that leg with ONE setting and silently drop every
  // other. Nothing would fail: the leg replays, produces trades, and lands in the table looking
  // ordinary. So an edited leg sends its COMPLETE set with the one field swapped in.
  //
  // ⚠ **An edit back to the leg's own baseline sends NOTHING**, because any override disables
  // reuse for that leg — typing the number that was already there would silently cost a reuse and
  // turn an instant stack into a full replay.
  const paramsByStrategy = useMemo(() => {
    const src = initial?.paramsByStrategy
    const out: Record<string, Record<string, unknown>> = {}
    for (const id of selected) {
      const base = src?.[id] ?? pyStrategies.find((s) => s.id === id)?.default_params ?? null
      const edited = legRisk[id]
      const baseline = baselineRisk(id)
      if (edited !== undefined && edited !== baseline && base) {
        out[id] = { ...base, [RISK_FIELD]: edited }
      } else if (src?.[id]) {
        out[id] = src[id]
      }
    }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial?.paramsByStrategy, selected, legRisk, pyStrategies])

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
    finestBar,
    'python',
    feedParams
  )

  const previewBody = useMemo(
    () => ({
      strategy_ids: Array.from(selected),
      instrument: instrument.trim(),
      bar_type: 'Minute',
      bar_value: barValue,
      // Sent to the PREVIEW as well as the launch: a leg's frame is part of the reuse identity,
      // so a preview that did not carry it would badge a 15m run green "Reuse" for a leg the
      // launch then replays on 5m.
      bar_values_by_strategy: barByLeg,
      start_date: start,
      end_date: end,
      commission_per_side: commPerSide,
      slippage_ticks: slippageTicks,
      mode,
      // Sent to the PREVIEW as well as to the launch, because an override disables reuse for that
      // leg — a preview that did not know about it would badge the leg green "Reuse" and then watch
      // it re-run.
      params_by_strategy: paramsByStrategy,
      charge_costs: chargeCosts,
      // Same reason, one level up: the cost basis is part of the reuse identity since 2026-09-02,
      // so a preview that did not carry it would badge a free-book run reusable for a charged
      // stack. ⚠ `broker_profile` is omitted rather than sent null while the profiles are still
      // loading — the request model defaults it, and a null would refuse the whole stack with a
      // message about an unknown broker, which is a contract mismatch reported as a broker fault.
      ...(brokerProfile ? { broker_profile: brokerProfile } : {}),
    }),
    [
      selected,
      instrument,
      barValue,
      barByLeg,
      start,
      end,
      commPerSide,
      slippageTicks,
      mode,
      paramsByStrategy,
      chargeCosts,
      brokerProfile,
    ]
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
  const canRun =
    settingsReady &&
    !triggerStack.isPending &&
    (!pythonBusy || nothingToRun) &&
    // A broker whose spread has never been measured refuses at the backend rather than borrowing a
    // sibling tier's number — PU Prime's tiers measured 2.7x apart. Stopping here means the answer
    // arrives before the click instead of as a 400 after it.
    !(chargeCosts && brokerUnpriced)

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
      {/* 🔴 THE SAME SHELL AS THE RUN MODAL — 1180px, 92vh, header / scrolling body / footer.
          It was 520px, which is why this form read as a different app from the one beside it:
          every control was stacked in one narrow column, so the account, the legs and the costs
          arrived as an undifferentiated ribbon and nothing could sit next to what it belongs
          with. Reported from the screen 2026-09-03. */}
      <div
        data-testid="stack-modal"
        className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[1180px] max-h-[92vh] flex flex-col shadow-2xl"
      >
        {/* ── Header ─────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border-subtle flex-shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <Layers size={16} className="text-gold-text flex-shrink-0" />
            <span className="text-[15px] font-semibold truncate">{title}</span>
            {/* The mode is a BADGE, the way the run modal badges its market. It is the single most
                consequential fact about a stack and it used to be buried in a paragraph. */}
            <span
              className={`text-[10px] px-2 py-[2px] rounded font-semibold uppercase tracking-[0.5px] border flex-shrink-0 ${
                shared
                  ? 'bg-accent/10 text-accent border-accent/20'
                  : 'bg-warn-muted text-warn-text border-warn-text/30'
              }`}
            >
              {shared ? 'Shared account' : 'Screen'}
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-text-tertiary hover:text-text-primary transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* ── Scrollable body ────────────────────────────────────────────────── */}
        <div className="overflow-y-auto flex-1 px-5 py-4 space-y-4">
          <p
            className="text-[12px] text-text-secondary leading-snug"
            data-testid="stack-mode-blurb"
          >
            {shared
              ? 'Layer 2 or more Python strategies onto ONE balance with ONE risk budget they compete for, replayed together on one clock — so you can see where a strategy was shrunk or blocked because another was already holding the capacity. Every leg is re-run; nothing is reused.'
              : 'This stack is a SCREEN: each strategy ran on its own full account and the results were added together, so no strategy could ever block another. Rerunning keeps it a screen. New stacks are shared accounts.'}
          </p>

          {/* ── Setup — the three facts every leg shares, on ONE row ────────────
              Broker first because everything under it depends on it: it decides which broker's
              bars are replayed, what the run is charged, AND how the instrument beside it is
              spelled. Instrument and period used to be four sections apart with the strategy
              list between them, so the window and the symbol could not be read as one decision. */}
          <div className="grid grid-cols-1 md:grid-cols-[minmax(180px,240px)_minmax(150px,200px)_minmax(340px,1fr)] gap-x-4 gap-y-3 items-start">
            <div className="min-w-0" data-testid="stack-broker">
              <label className={labelCls}>Broker account</label>
              <select
                value={brokerProfile ?? ''}
                onChange={(e) => setBrokerProfile(e.target.value)}
                className={inputCls}
              >
                {(brokerProfiles ?? []).map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.id}
                    {b.attached ? ' — connected now' : ''}
                  </option>
                ))}
              </select>
            </div>

            <div className="min-w-0">
              <label className={labelCls}>Instrument</label>
              <input
                value={instrument}
                onChange={(e) => setInstrument(e.target.value.toUpperCase())}
                placeholder="e.g. XAUUSD"
                className={`${inputCls} font-mono`}
              />
              {/* Three states, not two: silence here would read as "this broker quotes it bare",
                  which is a guess, and a guessed symbol is what the rewrite exists to prevent. */}
              {brokerNamingUnknown && (
                <div className="mt-[4px] text-[10px] text-warn-text leading-snug">
                  Nobody has recorded how {brokerProfile} spells its symbols, so this is sent
                  exactly as typed.
                </div>
              )}
            </div>

            <div className="min-w-0">
              <div className="flex items-center mb-1">
                <label className={labelCls.replace(' mb-1', '')}>Period</label>
                <InfoTooltip content="One window for every leg. It is bounded by the FINEST timeframe in the stack, because a broker holds less history the finer the bars — where the fast leg's bars do not reach, the slower leg would compound on its own." />
              </div>
              <PeriodPicker
                compact
                start={start}
                end={end}
                onChange={(s, e) => {
                  setStart(s)
                  setEnd(e)
                }}
                limit={historyLimit}
              />
            </div>
          </div>

          <Divider />

          {/* ── The legs ───────────────────────────────────────────────────────
              🔴 ONE LEG IS ONE ROW, carrying everything that is true of that leg. Its timeframe
              lived in a section of its own further down the form while its risk sat under the
              row — the same leg's two settings in two places, which is how you end up reading a
              stack you did not configure. */}
          <div>
            <SectionHead
              label="Strategies"
              tooltip="Each leg keeps its own timeframe and its own risk per trade. The timeframe starts on the frame that bot was measured on; another frame is a legal run and simply a different experiment."
            />
            {pyStrategies.length === 0 ? (
              <div className="text-[12px] text-text-tertiary py-3">
                No Python strategies found. Scan strategies first.
              </div>
            ) : (
              <>
                {/* Column headings, so the two numbers on each row are not a guess. */}
                <div className="flex items-center gap-2 px-3 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.5px] text-text-tertiary">
                  <span className="flex-1">Pick at least 2</span>
                  <span className="w-[96px] text-center flex-shrink-0">Timeframe</span>
                  <span className="w-[104px] text-center flex-shrink-0">Risk / trade</span>
                </div>
                <div className="space-y-1.5">
                  {pyStrategies.map((s) => {
                    const on = selected.has(s.id)
                    const action = on ? actionByStrategy.get(s.id) : undefined
                    const base = baselineRisk(s.id)
                    const shownRisk = legRisk[s.id] ?? base
                    const edited = legRisk[s.id] !== undefined && legRisk[s.id] !== base
                    const offMeasured =
                      s.suggested_bar_value != null && barByLeg[s.id] !== s.suggested_bar_value
                    return (
                      <div key={s.id}>
                        {/* ⚠ The ROW is a div and only the NAME is the button. An input inside a
                            button is invalid markup and every keystroke would toggle the leg off
                            — which is why these controls used to be exiled to their own block. */}
                        <div
                          className={`flex items-center gap-2 rounded-lg border transition-colors ${
                            on
                              ? 'border-accent/40 bg-accent/5'
                              : 'border-border-subtle bg-bg-sunken hover:border-border-default'
                          }`}
                        >
                          <button
                            onClick={() => toggle(s.id)}
                            className="flex items-center gap-2.5 flex-1 min-w-0 px-3 py-2 text-left"
                          >
                            <span
                              className={`w-4 h-4 rounded flex items-center justify-center flex-shrink-0 border ${on ? 'bg-accent border-accent' : 'border-border-default'}`}
                            >
                              {on && <span className="text-bg-base text-[10px] font-bold">✓</span>}
                            </span>
                            <span className="flex-1 min-w-0">
                              <span className="text-[13px] font-medium text-text-primary">
                                {s.name}
                              </span>
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

                          {/* The leg's own two settings, on the leg's own row. Present only when
                              the leg is IN — a control for a strategy nobody picked is a setting
                              with nowhere to go. */}
                          <div className="flex items-center gap-2 pr-3 py-2 flex-shrink-0">
                            {on ? (
                              <select
                                value={barByLeg[s.id]}
                                onChange={(e) =>
                                  setLegBar((prev) => ({ ...prev, [s.id]: Number(e.target.value) }))
                                }
                                title={
                                  s.suggested_bar_value != null
                                    ? `Measured on ${barLabel(s.suggested_bar_value)}`
                                    : 'This strategy states no measured timeframe'
                                }
                                className={`${inputCls} w-[96px] py-[4px] ${offMeasured ? 'border-warn-text/50 text-warn-text' : ''}`}
                              >
                                {BAR_PRESETS.map(([v, label]) => (
                                  <option key={v} value={v}>
                                    {label}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <span className="w-[96px]" />
                            )}
                            {on && shownRisk !== undefined ? (
                              <div className="relative w-[104px]">
                                <input
                                  type="number"
                                  step="0.5"
                                  min="0.1"
                                  value={shownRisk}
                                  onChange={(e) =>
                                    setLegRisk((prev) => ({
                                      ...prev,
                                      [s.id]: Number(e.target.value),
                                    }))
                                  }
                                  className={`${inputCls} py-[4px] pr-6 font-mono ${edited ? 'border-warn-text/50' : ''}`}
                                />
                                <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-text-tertiary pointer-events-none">
                                  %
                                </span>
                              </div>
                            ) : (
                              <span className="w-[104px]" />
                            )}
                          </div>
                        </div>

                        {/* Why a row is not on its defaults. Both of these change what the leg IS
                            measured on, so neither may be silent. */}
                        {on && (offMeasured || edited) && (
                          <div className="pl-9 pt-1 flex flex-wrap gap-x-4 text-[10px] text-warn-text">
                            {offMeasured && (
                              <span>
                                {s.name} was measured on {barLabel(s.suggested_bar_value as number)}{' '}
                                — this is a different experiment
                              </span>
                            )}
                            {edited && <span>risk was {base} · this leg runs fresh</span>}
                          </div>
                        )}
                      </div>
                    )
                  })}

                  {/* 🔴 THE RECOVERY LEG IS ADDED HERE, UNDER ITS PARENT, AND NOWHERE ELSE. It has
                      no setups of its own, so a picker row for it could build a stack with nothing
                      to read — an empty book that looks exactly like a rule that found nothing.
                      Nesting it under the leg whose losses it follows makes the dependency
                      impossible to get wrong rather than something the backend has to refuse.
                      ⚠ It shows no timeframe of its own: it is PINNED to its parent's frame,
                      because it counts its wait in the parent's bars. */}
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
                          title="It has no setups of its own — after that strategy loses, it takes a smaller trade the other way. It competes for the same risk budget, so it can shrink or block the leg it follows. It runs on its parent's timeframe."
                        >
                          Extra leg
                        </span>
                      </button>
                    </div>
                  )}
                </div>
              </>
            )}

            {mixedFrames && (
              <p className="text-[11px] text-text-tertiary mt-2 leading-snug">
                Two timeframes on one account: the faster leg steps several times inside the slower
                one&apos;s bar. The window above has to be one the {barLabel(finestBar)} bars reach
                — where they do not, the slower leg would compound on its own and size every later
                trade off a balance it built unopposed.
              </p>
            )}
          </div>

          <Divider />

          {/* ── How it runs: the account it shares, and what it is charged ──────
              Side by side, because they are the two halves of one question and each is short.
              Stacked in a 520px column they read as two more items on a list of eight. */}
          <div className={`grid gap-5 ${shared ? 'md:grid-cols-2' : 'grid-cols-1'}`}>
            {shared && (
              <div data-testid="stack-account-fields">
                <SectionHead
                  label="The shared account"
                  tooltip="One balance and one risk budget for every leg. This is what makes a stack a portfolio rather than a sum of separate runs."
                />
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className={labelCls}>Balance ($)</label>
                    <input
                      type="number"
                      step="100"
                      min="1"
                      value={accountSize}
                      onChange={(e) => setAccountSize(Number(e.target.value))}
                      className={`${inputCls} font-mono`}
                    />
                  </div>
                  <div>
                    <label className={labelCls}>Risk cap (%)</label>
                    <input
                      type="number"
                      step="0.5"
                      min="0.5"
                      value={riskCapPct}
                      onChange={(e) => setRiskCapPct(Number(e.target.value))}
                      className={`${inputCls} font-mono`}
                    />
                  </div>
                  <div>
                    <label className={labelCls}>Entry floor (%)</label>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      value={entryFloorPct}
                      onChange={(e) => setEntryFloorPct(Number(e.target.value))}
                      className={`${inputCls} font-mono`}
                    />
                  </div>
                </div>
                <p className="text-[11px] text-text-tertiary mt-1.5 leading-snug">
                  The cap is the most OPEN risk all strategies may hold at once, as a % of the
                  <strong className="text-text-secondary"> live </strong> balance — and an open
                  trade only reserves risk down to its{' '}
                  <strong className="text-text-secondary">current</strong> stop, so a stop moved to
                  breakeven frees its room. An entry with no room is shrunk to fit, or skipped if
                  what is left falls under the floor.
                </p>
                {!accountValid && (
                  <p className="text-[11px] text-neg-text mt-1.5">
                    Balance and risk cap must both be above zero — a cap of zero refuses every
                    entry, which is a stopped bot rather than a portfolio.
                  </p>
                )}
              </div>
            )}

            {/* ── Costs — ONE switch, on by default ─────────────────────────────
                🔴 Every stack this lab ran before 2026-09-02 was GROSS while its page showed a
                cost row: a stack carried no broker and no layers, so it fell through to two typed
                figures that default to zero. The switch sends a BOOLEAN and the backend resolves
                what that charges — the policy lives on the side that bills it. */}
            <div data-testid="stack-costs">
              <SectionHead
                label="Costs"
                tooltip="Every figure charged here is MEASURED on the broker account above — they are facts about that account, not settings. A free run is a diagnostic that says how much of the edge is friction."
              />
              <div className="flex items-start gap-2.5">
                <button
                  type="button"
                  role="switch"
                  aria-checked={chargeCosts}
                  onClick={() => setChargeCosts((v) => !v)}
                  className={`mt-[2px] w-8 h-[18px] rounded-full flex-shrink-0 transition-colors relative ${
                    chargeCosts ? 'bg-accent' : 'bg-border-default'
                  }`}
                >
                  <span
                    className={`absolute top-[2px] w-[14px] h-[14px] rounded-full bg-bg-base transition-all ${
                      chargeCosts ? 'left-[16px]' : 'left-[2px]'
                    }`}
                  />
                </button>
                <span className="min-w-0">
                  <span className="block text-[12px] text-text-primary">
                    {chargeCosts
                      ? "Charge this account's real costs"
                      : 'Run gross — charge nothing'}
                  </span>
                  <span className="block text-[11px] text-text-tertiary leading-snug">
                    {chargeCosts
                      ? 'Spread on every fill, commission and overnight financing, all measured on the account above.'
                      : 'A diagnostic only. It answers how much of the edge is friction, never whether the stack works.'}
                  </span>
                </span>
              </div>
              {!chargeCosts && (
                <p className="mt-2 text-[11px] text-warn-text bg-warn-muted rounded px-2 py-1.5 leading-snug">
                  This stack will report a gross figure, and it is not comparable to a charged one —
                  real fills change which setups exist, not just what they pay.
                </p>
              )}
              {/* ⚠ WARNS, never blocks. Measuring against a broker you are not pointed at is a
                  legitimate thing to do deliberately. */}
              {chargeCosts && brokerMatches === false && (
                <p className="mt-2 text-[11px] text-warn-text bg-warn-muted rounded px-2 py-1.5 leading-snug">
                  This charges {brokerProfile}&apos;s costs over bars from {attachedProfile?.id},
                  which is the terminal actually connected. Same stack, two brokers — pick{' '}
                  {attachedProfile?.id} unless you mean to compare.
                </p>
              )}
              {chargeCosts && brokerMatches === null && !!brokerProfiles?.length && (
                <p className="mt-2 text-[11px] text-text-tertiary leading-snug">
                  Can&apos;t tell which terminal is connected, so nothing here confirms these costs
                  match the bars this stack will replay.
                </p>
              )}
              {/* This one DOES block, because the backend refuses it — a tier nobody has measured
                  would otherwise borrow a sibling's number, and PU Prime's measured 2.7x apart. */}
              {chargeCosts && brokerUnpriced && (
                <p className="mt-2 text-[11px] text-neg-text bg-warn-muted rounded px-2 py-1.5 leading-snug">
                  This account&apos;s spread has never been measured, so it cannot be run charged.
                  Measure it first, or pick an account that has been.
                </p>
              )}

              {/* 🔴 SLIPPAGE IS THE ONE TYPED COST, AND COMMISSION IS NOT A FIELD AT ALL.
                  Commission is a MEASURED fact about the broker account — `routers/_costs.py`
                  reads it off the account and has ignored whatever was typed here since the day
                  the switch landed. So the box asked the reader for a number, showed it back to
                  them, and changed nothing: the worst kind of control, and it is rule 7 in
                  miniature. Slippage stays because it is the one cost nobody has measured, and
                  charging it is somebody saying a guess out loud. */}
              {chargeCosts && !brokerUnpriced && (
                <div className="mt-2 px-2.5 py-2 rounded border border-border-subtle/50 bg-bg-sunken">
                  <span className="flex items-center gap-1.5 mb-1">
                    <span className="text-[12px] text-text-primary">Slippage</span>
                    <span className="text-[9px] uppercase tracking-[0.4px] px-1 py-[1px] rounded bg-warn-muted text-warn-text">
                      a guess
                    </span>
                  </span>
                  <span className="block text-[11px] text-text-tertiary leading-snug mb-1.5">
                    Nobody has measured this. Leave it at 0 unless you mean to charge an assumption;
                    it is charged on market exits only.
                  </span>
                  <div className="max-w-[220px]">
                    <input
                      type="number"
                      step="1"
                      min="0"
                      value={slippageTicks}
                      onChange={(e) => setSlippageTicks(Number(e.target.value))}
                      className={`${inputCls} font-mono`}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* ── What pressing the button will actually do ─────────────────────── */}
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

        {/* ── Footer ─────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-end gap-3 px-5 py-3 border-t border-border-subtle flex-shrink-0">
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
