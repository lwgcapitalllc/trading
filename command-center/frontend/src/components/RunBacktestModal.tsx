import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { X, Play, Info, ChevronDown, ChevronRight } from 'lucide-react'
import { AlertTriangle } from 'lucide-react'
import {
  useFirms,
  useTriggerBacktest,
  useRunningVpsJob,
  useHistoryLimit,
  useBrokerProfiles,
} from '@/hooks/useLab'
import { ParamEditor, isChanged, visibleParams, type ParamValue } from '@/components/ParamEditor'
import { PeriodPicker, PresetBtn, today, yearsAgo } from '@/components/PeriodPicker'
import { isNt8Runner, runnerScope, runningJobFor, RUNNER_LABEL, runnerMarket } from '@/lib/runner'
import type { Strategy, Firm, SizingMode, BrokerProfile } from '@/types'

// ── Date helpers ──────────────────────────────────────────────────────────────

// Quarterly futures roll months: Mar (3), Jun (6), Sep (9), Dec (12)
function currentFrontMonth(): string {
  const d = new Date()
  const year = d.getFullYear()
  const month = d.getMonth() + 1
  const quarters = [3, 6, 9, 12]
  let q = quarters.find((m) => m >= month)
  let y = year
  if (!q) {
    q = 3
    y = year + 1
  }
  return `${String(q).padStart(2, '0')}-${String(y).slice(-2)}`
}

function parseSuggestedInstrument(s: string | null, frontMonth: string) {
  if (!s) return { symbol: '', month: frontMonth }
  const parts = s.trim().split(/\s+/)
  if (parts.length >= 2) return { symbol: parts[0], month: parts.slice(1).join(' ') }
  return { symbol: parts[0], month: frontMonth }
}

// ── Firm grouping helpers ─────────────────────────────────────────────────────

function firmBrandName(firmName: string): string {
  const idx = firmName.indexOf(' $')
  return idx > 0 ? firmName.slice(0, idx) : firmName
}

function firmChallengeName(firmName: string): string {
  const idx = firmName.indexOf(' $')
  return idx > 0 ? firmName.slice(idx + 1) : firmName
}

const INSTRUMENT_NAMES: Record<string, string> = {
  // Micro E-mini equity index
  MES: 'Micro E-mini S&P 500',
  MNQ: 'Micro E-mini Nasdaq-100',
  MYM: 'Micro E-mini Dow Jones',
  M2K: 'Micro E-mini Russell 2000',
  // Full-size E-mini equity index
  ES: 'E-mini S&P 500',
  NQ: 'E-mini Nasdaq-100',
  YM: 'E-mini Dow Jones',
  RTY: 'E-mini Russell 2000',
  // Metals
  MGC: 'Micro Gold',
  GC: 'Gold',
  MSI: 'Micro Silver',
  SI: 'Silver',
  // Energy
  MCL: 'Micro Crude Oil',
  CL: 'Crude Oil',
  NG: 'Natural Gas',
  // Crypto
  MBT: 'Micro Bitcoin',
  MET: 'Micro Ether',
  BTC: 'Bitcoin',
  ETH: 'Ether',
  // Fixed income
  ZB: '30-Year T-Bond',
  ZN: '10-Year T-Note',
  ZF: '5-Year T-Note',
  ZT: '2-Year T-Note',
}

function lookupInstrumentName(sym: string): string {
  if (INSTRUMENT_NAMES[sym]) return INSTRUMENT_NAMES[sym]
  // Continuous contract: @MNQ #C → MNQ
  const m = sym.match(/^@([A-Z0-9]+)(?:\s+#C)?$/)
  if (m && INSTRUMENT_NAMES[m[1]]) return `${INSTRUMENT_NAMES[m[1]]} (continuous)`
  return ''
}

// Vantage demo symbol names — no ".s" suffix (that was PU Prime). Backtests pull data ONLY from
// MT5_Lab, which is logged into the Vantage demo (see algos/CLAUDE.md), so these must be the Vantage
// names or the data pull caches Vantage bars under a wrong PU-Prime key. Confirmed against the live
// terminal 2026-07-22 via the agent's /symbol_info (all ten resolve plain).
const BROKER_SYMBOLS = [
  'EURUSD',
  'GBPUSD',
  'USDJPY',
  'XAUUSD',
  'GBPJPY',
  'AUDUSD',
  'USDCAD',
  'EURGBP',
  'AUDJPY',
  'CADJPY',
]

function getAllowedSymbols(firms: Firm[]): string[] {
  const set = new Set<string>()
  for (const f of firms) {
    for (const inst of f.allowed_instruments) set.add(inst)
  }
  return Array.from(set).sort()
}

// ── Tooltip ───────────────────────────────────────────────────────────────────

function InfoTooltip({ content, side = 'right' }: { content: string; side?: 'right' | 'left' }) {
  // 'right' → tooltip opens rightward from the icon (left-side icons)
  // 'left'  → tooltip opens leftward from the icon (right-side icons)
  const anchorCls = side === 'right' ? 'left-0' : 'right-0'
  return (
    <span className="relative group/tip inline-flex items-center ml-1 flex-shrink-0">
      <Info
        size={10}
        className="text-text-tertiary group-hover/tip:text-accent cursor-help transition-colors"
      />
      <span
        className={`absolute ${anchorCls} bottom-[calc(100%+5px)] z-50 hidden group-hover/tip:block w-56 rounded-md bg-bg-surface border border-border-default px-2.5 py-2 text-[11px] text-text-secondary shadow-xl pointer-events-none leading-relaxed`}
      >
        {content}
      </span>
    </span>
  )
}

// ── Small UI pieces ───────────────────────────────────────────────────────────

/**
 * A section title. With `onToggle` it becomes the section's collapse control.
 *
 * ⚠ A collapsed section MUST pass `summary` — the header is then the only thing standing for
 * everything folded away, and a reader who cannot see what a hidden section is set to will open
 * every one of them, which is worse than never having collapsed anything.
 */
function SectionHead({
  label,
  tooltip,
  open,
  onToggle,
  summary,
}: {
  label: string
  tooltip?: string
  open?: boolean
  onToggle?: () => void
  summary?: string
}) {
  const head = (
    <>
      {label}
      {tooltip && <InfoTooltip content={tooltip} />}
    </>
  )
  const cls =
    'flex items-center gap-1 text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.7px]'
  if (!onToggle) return <div className={`${cls} mb-3`}>{head}</div>
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className={`${cls} w-full ${open ? 'mb-3' : 'mb-0'} hover:text-text-secondary transition-colors`}
    >
      {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
      {head}
      {summary && (
        <span className="ml-auto normal-case tracking-normal font-normal text-[11px] text-text-tertiary truncate">
          {summary}
        </span>
      )}
    </button>
  )
}

/** Account-currency swap for ONE lot for ONE night, from the broker's quoted POINTS.
 *  The broker's own formula: points x contract size x 10^-digits. Doing it here rather than
 *  shipping a pre-multiplied number keeps the served profile a faithful copy of the
 *  Specification window — the same reason the spread is served raw. Digits is 2 on gold, and
 *  is the one term not on `BrokerProfile`; it is fixed at 2 for every profile we quote. */
function swapPerNight(b: BrokerProfile, side: 'long' | 'short'): number {
  const pts = (side === 'long' ? b.swap_long_points : b.swap_short_points) ?? 0
  return pts * b.contract_size * 0.01
}

function Divider() {
  return <div className="border-t border-border-subtle" />
}

// ── Modal ─────────────────────────────────────────────────────────────────────

interface Props {
  strategy: Strategy
  onClose: () => void
  /** If provided, called with the new run_id instead of navigating. */
  onSuccess?: (runId: string) => void
}

export function RunBacktestModal({ strategy, onClose, onSuccess }: Props) {
  const navigate = useNavigate()
  const trigger = useTriggerBacktest()
  const { data: firms = [], isLoading: firmsLoading } = useFirms()
  const { data: runningJob } = useRunningVpsJob()

  // NT8 is the only futures platform: contract months, prop-challenge rulesets, and injected
  // foundational params are all NT8-only. MT5 and Python both trade the broker's spot symbols.
  const scope = runnerScope(strategy.runner)
  const isNt8 = isNt8Runner(strategy.runner)
  // Python is the one runner whose cost units we OWN (backtest/fills.AccountProfile), so it is
  // the one that can state them exactly rather than in the platform's general terms.
  const isPython = strategy.runner === 'python'
  const isFutures = runnerMarket(strategy.runner) === 'futures'

  const inputCls =
    'bg-bg-sunken border border-border-subtle rounded-md px-3 py-[6px] text-[13px] text-text-primary w-full focus:outline-none focus:border-accent transition-colors'
  const labelCls = 'block text-[11px] text-text-secondary mb-1'

  // ── Instrument ───────────────────────────────────────────────────────────────
  const frontMonth = useMemo(() => currentFrontMonth(), [])
  const futuresFirms = useMemo(() => firms.filter((f) => f.market !== 'forex'), [firms])
  const forexFirms = useMemo(() => firms.filter((f) => f.market === 'forex'), [firms])
  const allowedSymbols = useMemo(() => getAllowedSymbols(futuresFirms), [futuresFirms])

  const parsed = useMemo(
    () => parseSuggestedInstrument(strategy.suggested_instrument, frontMonth),
    [strategy.suggested_instrument, frontMonth]
  )

  const [instrumentSymbol, setInstrumentSymbol] = useState(
    isNt8 ? parsed.symbol : scope === 'python' ? parsed.symbol || 'XAUUSD' : 'EURUSD'
  )
  const [contractMonth, setContractMonth] = useState(parsed.month)

  // NT8 only: once firms load, ensure symbol is in allowed list
  useEffect(() => {
    if (!isNt8) return
    if (allowedSymbols.length === 0) return
    if (!instrumentSymbol || !allowedSymbols.includes(instrumentSymbol)) {
      setInstrumentSymbol(allowedSymbols[0])
    }
  }, [allowedSymbols]) // eslint-disable-line react-hooks/exhaustive-deps

  const instrument = !isNt8
    ? instrumentSymbol
    : contractMonth.trim()
      ? `${instrumentSymbol} ${contractMonth.trim()}`
      : instrumentSymbol

  // ── Period ───────────────────────────────────────────────────────────────────
  const [startDate, setStartDate] = useState(() => yearsAgo(1))
  const [endDate, setEndDate] = useState(() => today())

  // ── Bar size ─────────────────────────────────────────────────────────────────
  const BAR_PRESETS = isNt8 ? [1, 3, 5, 15, 30] : [5, 15, 30, 60, 240]
  const [barValue, setBarValue] = useState(isNt8 ? 5 : scope === 'python' ? 15 : 60)

  // ── Sizing mode — how the engine sizes each trade from the room left ───────────
  // A self-sizing strategy sizes its own trades off its own risk % param — the engine never
  // touches it, so there is no mode to pick and the whole section is hidden.
  const selfSizing = strategy.self_sizing === true
  const [sizingMode, setSizingMode] = useState<SizingMode>('consistent')
  const [manualPct, setManualPct] = useState('1.0')
  const manualPctNum = parseFloat(manualPct)
  const manualPctValid =
    sizingMode !== 'manual' || (!isNaN(manualPctNum) && manualPctNum > 0 && manualPctNum <= 100)

  function barLabel(v: number) {
    if (v < 60) return `${v}m`
    const h = v / 60
    return `${h}h`
  }

  // ── Strategy params (strategy_logic only — foundational injected by dispatcher) ─
  const [params, setParams] = useState<Record<string, number | boolean | string>>(() => {
    const init: Record<string, number | boolean | string> = {}
    for (const e of strategy.param_schema) {
      if (e.category !== 'foundational') {
        init[e.name] = e.default as number | boolean | string
      }
    }
    return init
  })

  // How far back this instrument + timeframe actually has bars. Depends on barValue, so it
  // re-reads when the bar size changes — a broker can hold years of 15m and months of 1m.
  //
  // ⚠ It also depends on the PARAMS, which is why it sits below them rather than beside the
  // other window controls: a run with `exec_secondary` on loads a 1m feed too, and that feed's
  // history is shallower. Ticking that switch moves the earliest date this picker will accept,
  // and until 2026-08-15 it did not — the run was accepted here and refused at 8%.
  const { data: historyLimit } = useHistoryLimit(
    instrument || null,
    'Minute',
    barValue,
    strategy.runner,
    params
  )

  // ── Firm grouping ────────────────────────────────────────────────────────────
  const firmsByBrand = useMemo(() => {
    const map = new Map<string, Firm[]>()
    for (const f of futuresFirms) {
      const brand = firmBrandName(f.name)
      if (!map.has(brand)) map.set(brand, [])
      map.get(brand)!.push(f)
    }
    return map
  }, [futuresFirms])

  const brandNames = useMemo(() => Array.from(firmsByBrand.keys()), [firmsByBrand])
  const [selectedBrand, setSelectedBrand] = useState<string>('')

  useEffect(() => {
    if (brandNames.length > 0 && !selectedBrand) setSelectedBrand(brandNames[0])
  }, [brandNames, selectedBrand])

  const [selectedFirms, setSelectedFirms] = useState<Set<string>>(new Set())

  const brandFirms = selectedBrand ? (firmsByBrand.get(selectedBrand) ?? []) : []
  const allBrandSelected = brandFirms.length > 0 && brandFirms.every((f) => selectedFirms.has(f.id))

  const toggleFirm = (id: string) =>
    setSelectedFirms((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const toggleAllBrand = () => {
    if (allBrandSelected) {
      setSelectedFirms((prev) => {
        const next = new Set(prev)
        brandFirms.forEach((f) => next.delete(f.id))
        return next
      })
    } else {
      setSelectedFirms((prev) => {
        const next = new Set(prev)
        brandFirms.forEach((f) => next.add(f.id))
        return next
      })
    }
  }

  // ── Primary ruleset (first selected — drives foundational config display) ─────
  // Looked up across BOTH lists on purpose (fixed 2026-08-01). It searched `futuresFirms` only,
  // so on a forex run — where the selection is always a forex ruleset — this was null, the effect
  // below never fired, and the cost fields shipped their initial state instead of the ruleset's
  // 0/0. That is how run f866873aa862 came to be stored with a FUTURES prop-firm cost profile.
  const primaryRuleset = useMemo(() => {
    if (selectedFirms.size === 0) return null
    const firstId = Array.from(selectedFirms)[0]
    return (
      futuresFirms.find((f) => f.id === firstId) ?? forexFirms.find((f) => f.id === firstId) ?? null
    )
  }, [selectedFirms, futuresFirms, forexFirms])

  // ── Advanced — pre-filled from primary ruleset, user-editable ────────────────
  // 0/0 is the floor, not a placeholder: a cost you did not state must never be charged, and
  // the old 2.25/1 was a FUTURES prop-firm figure landing on forex and Python runs.
  const [commPerSide, setCommPerSide] = useState(0)
  const [slippageTicks, setSlippageTicks] = useState(0)

  // ── Costs (python runner) — ONE SWITCH, and it defaults to ON ───────────────
  // 🔴 Aaron's call (2026-08-24), reversing the 2026-08-02 design that lived here. That version
  // offered five tickboxes with everything off, so the first number any run produced was the
  // frictionless one — a figure you cannot trade, sitting where the answer goes. It also asked
  // the operator to reassemble a cost policy from memory on every single run, and a rule that
  // lives in somebody's memory is a rule that gets broken on a Friday.
  //
  // ⚠ **The switch does not send layers — it sends a BOOLEAN, and the backend resolves it**
  // (`python_runner.charged_layers`). The policy has to live on the side that charges it, or the
  // page and the run can describe different physics. That is rule 7: a label is a claim about
  // code somewhere else.
  //
  // ⚠ Slippage is the one thing still separate, and deliberately so — it is the only cost here
  // nobody has measured, so it rides its own optional figure rather than the switch.
  const [chargeCosts, setChargeCosts] = useState(true)
  const [brokerProfile, setBrokerProfile] = useState('vantage_demo')
  const { data: brokerProfiles } = useBrokerProfiles()
  const broker = brokerProfiles?.find((b) => b.id === brokerProfile) ?? null
  // A tier whose spread has never been read carries the refusal sentinel rather than a number,
  // and the backend REFUSES to run it charged. The modal has to say so before the button is
  // pressed — a 400 arriving after a click is the answer in the wrong place.
  const brokerUnpriced = broker != null && broker.spread < 0
  // Opens when costs are OFF, because that is the state that needs explaining. A charged run is
  // the default and says so in one summary line.
  const [costsOpen, setCostsOpen] = useState(false)
  // ⚠ Counted over `visibleParams`, the SAME set the summary lists, so the number can never
  // point at a row the reader cannot find. A settled param moved off its default is visible
  // again, so it counts here too.
  const changedCount = useMemo(
    () =>
      visibleParams(strategy.param_schema, params as Record<string, ParamValue>).filter((p) =>
        isChanged(p, (params as Record<string, ParamValue>)[p.name])
      ).length,
    [strategy.param_schema, params]
  )

  // What "costs on" actually charges, for THIS broker. Every figure is derived from the SERVED
  // profile and never retyped — see `useBrokerProfiles`. This mirrors `python_runner.CHARGED_LAYERS`
  // and exists so the page states what the run will be billed rather than implying it.
  // ⚠ If that constant gains a layer, this list has to gain a line. It is a display of a policy
  // that lives on the backend, not a second copy of the policy.
  const chargedRows: { label: string; detail: string; tag?: string }[] = [
    {
      label: 'Bid/ask on every fill',
      tag: 'moves trades',
      detail: broker
        ? `buys transact $${broker.spread.toFixed(2)} higher — some longs never fill, some stops do`
        : 'buys transact at the ask',
    },
    {
      label: 'Commission',
      detail: broker
        ? `$${broker.commission_per_side_per_lot.toFixed(2)} per side per lot, measured on this account`
        : 'measured per account',
    },
    {
      label: 'Overnight swap',
      detail:
        broker?.swap_long_points != null
          ? `$${swapPerNight(broker, 'long').toFixed(2)} a night per lot long, ` +
            `$${swapPerNight(broker, 'short').toFixed(2)} short`
          : 'this account prices no financing',
    },
  ]

  // The two typed cost figures, defined ONCE. A python run renders each under its own layer row
  // (`costInputs`); NT8/MT5 have no layers and render both in their own Costs section. Two copies
  // of an input is two places a tooltip or a step can drift.
  const commissionInput = (
    <>
      <div className="flex items-center mb-1">
        <label className={labelCls.replace(' mb-1', '')}>Commission / side ($)</label>
        <InfoTooltip
          content={
            isPython
              ? 'Dollars per LOT, per side — a lot being 100 units (100 oz of gold). Charged on the entry and on every exit rung. Leave at 0 for a demo account, which charges none; a live Vantage RAW ECN is $3.00/side/lot.'
              : !isNt8
                ? 'Commission per side in account currency. Applied to every fill.'
                : 'Round-trip cost per contract, per side. NinjaTrader typically charges ~$2.25/side for micro futures at most brokers. Applied to every fill.'
          }
        />
      </div>
      <input
        type="number"
        step="0.01"
        min="0"
        value={commPerSide}
        onChange={(e) => setCommPerSide(parseFloat(e.target.value) || 0)}
        className={inputCls}
      />
    </>
  )
  const slippageInput = (
    <>
      <div className="flex items-center mb-1">
        <label className={labelCls.replace(' mb-1', '')}>Slippage (ticks)</label>
        <InfoTooltip
          content={
            isPython
              ? 'Ticks of adverse slippage on MARKET exits only — a stop, or a force-close. Entries and take-profit rungs are resting limits, which fill at your price or better or not at all, so they never slip. 1 tick = $0.01 on gold.'
              : !isNt8
                ? 'Additional points deducted per fill to model spread and slippage. Conservative backtests use 1–3 points for major forex pairs.'
                : 'Additional ticks deducted per fill to model market impact and bid/ask spread. 1 tick = $0.50 for MNQ, $1.25 for MES. Conservative backtests use 1–2 ticks.'
          }
          side="left"
        />
      </div>
      <input
        type="number"
        step="1"
        min="0"
        value={slippageTicks}
        onChange={(e) => setSlippageTicks(parseInt(e.target.value, 10) || 0)}
        className={inputCls}
      />
    </>
  )

  useEffect(() => {
    if (primaryRuleset?.default_commission_per_side != null) {
      setCommPerSide(primaryRuleset.default_commission_per_side)
    }
    if (primaryRuleset?.default_slippage_ticks != null) {
      setSlippageTicks(primaryRuleset.default_slippage_ticks)
    }
  }, [primaryRuleset?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Validation ───────────────────────────────────────────────────────────────
  const blockingJob = runningJobFor(runningJob, strategy.runner)
  const jobBlocked = !!blockingJob?.running
  // Forex runs evaluate against the personal forex ruleset(s); futures against prop
  // challenges. Both require ≥1 selection, but never block when none exist for the platform.
  const evalRequiredMet = isNt8
    ? selectedFirms.size > 0
    : selectedFirms.size > 0 || forexFirms.length === 0
  const canSubmit =
    instrumentSymbol !== '' &&
    startDate !== '' &&
    endDate !== '' &&
    startDate < endDate &&
    evalRequiredMet &&
    manualPctValid &&
    // A tier with no measured spread cannot be run charged, and the backend refuses it. Blocking
    // the button is the same refusal in the place the reader is looking.
    !(isPython && chargeCosts && brokerUnpriced) &&
    !trigger.isPending &&
    !jobBlocked

  // ── Submit ───────────────────────────────────────────────────────────────────
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    trigger.mutate(
      {
        strategy_id: strategy.id,
        instrument,
        params: params as Record<string, unknown>,
        bar_type: 'Minute',
        bar_value: barValue,
        start_date: startDate,
        end_date: endDate,
        commission_per_side: commPerSide,
        slippage_ticks: slippageTicks,
        // ⚠ `null` for NT8/MT5, NEVER `[]`. The layered-cost switches are python-only, and `[]`
        // is an explicit "this run deliberately charged nothing" — so an NT8 run stored with `[]`
        // had the detail page print "This run was deliberately frictionless" over a run whose
        // tester really did charge the commission and slippage below. `null` is the honest
        // answer: this run does not use layers, and the two legacy fields say what it charged.
        cost_layers: null,
        // 🔴 The switch, and the modal sends ONLY this — the backend resolves it into the layers
        // it charges. Sending a layer list from here would make the page the authority on a
        // policy the runner owns, which is how a label ends up claiming something no code does.
        // ⚠ `null` for NT8/MT5: they have no layer contract at all, and `charge_costs` must not
        // manufacture one for them.
        charge_costs: isPython ? chargeCosts : null,
        broker_profile: brokerProfile,
        evaluate_rulesets: Array.from(selectedFirms),
        sizing_mode: sizingMode,
        manual_risk_pct: sizingMode === 'manual' ? manualPctNum : null,
      },
      {
        onSuccess: (data) => {
          onClose()
          if (onSuccess) onSuccess(data.run_id)
          else navigate(`/backtests/runs/${data.run_id}`)
        },
      }
    )
  }

  // ── Escape key ───────────────────────────────────────────────────────────────
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {/* ⚠ WIDER THAN THE OTHER MODALS ON PURPOSE (1180px). This one carries a strategy's whole
          settings surface, and at 900px the summary below could only fit two columns — which put
          the thing the reader opens this for below the fold. */}
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[1180px] max-h-[92vh] flex flex-col shadow-2xl">
        {/* ── Header — the STRATEGY NAME lives here, not in a row of its own ────
            It is read-only, so a full-width input for it was ~70px spent restating the title of
            the thing you clicked Run on. */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border-subtle flex-shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[15px] font-semibold flex-shrink-0">Run</span>
            <span className="text-[15px] font-semibold text-accent truncate">
              {strategy.name || strategy.class_name}
            </span>
            <span
              className={`text-[10px] px-2 py-[2px] rounded font-semibold uppercase tracking-[0.5px] border ${
                isFutures
                  ? 'bg-accent/10 text-accent border-accent/20'
                  : 'bg-warn-muted text-warn-text border-warn-text/30'
              }`}
            >
              {isFutures ? 'Futures' : 'Forex'}
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-text-tertiary hover:text-text-primary transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* ── Running job warning ─────────────────────────────────────────────── */}
        {jobBlocked && (
          <div className="mx-5 mt-4 flex items-start gap-2 px-3 py-2.5 rounded-md bg-warn-muted/40 border border-warn-text/20">
            <AlertTriangle size={13} className="text-warn-text flex-shrink-0 mt-[1px]" />
            <p className="text-[12px] text-warn-text leading-snug">
              <span className="font-semibold">{RUNNER_LABEL[scope]} is busy:</span>{' '}
              {blockingJob?.description} — wait for it to finish before starting a new run.
            </p>
          </div>
        )}

        {/* ── Stale-schema warning — source changed since the last Scan ─────────── */}
        {strategy.needs_scan && (
          <div className="mx-5 mt-4 flex items-start gap-2 px-3 py-2.5 rounded-md bg-warn-muted/40 border border-warn-text/20">
            <AlertTriangle size={13} className="text-warn-text flex-shrink-0 mt-[1px]" />
            <p className="text-[12px] text-warn-text leading-snug">
              <span className="font-semibold">Parameters may be out of date:</span> this strategy's
              source changed since the last scan. Close this, click{' '}
              <span className="font-semibold">Scan Strategies</span>, then reopen — otherwise the
              toggles and defaults below are stale.
            </p>
          </div>
        )}

        {/* ── Scrollable body ─────────────────────────────────────────────────── */}
        <form onSubmit={handleSubmit} className="overflow-y-auto flex-1 px-5 py-4 space-y-4">
          {/* ── Setup — instrument, bar size and period on ONE row ─────────────────
              These were four stacked sections with four uppercase headings, and between them
              they cost ~340px before the first strategy setting appeared. Nothing was dropped:
              the instrument's ten preset chips became the input's own dropdown list (so a
              broker symbol can still be TYPED), the bar presets became a select, and the period
              keeps its quick ranges beside the dates. */}
          <div className="grid grid-cols-1 md:grid-cols-[minmax(140px,200px)_110px_minmax(360px,1fr)] gap-x-4 gap-y-3 items-start">
            {/* Instrument */}
            <div className="min-w-0">
              {!isNt8 ? (
                <>
                  <label className={labelCls}>Instrument</label>
                  {/* A LIST, not a select: the preset chips were the only way to pick one, and a
                      select would take away typing a symbol they do not cover. */}
                  <input
                    type="text"
                    list="run-broker-symbols"
                    value={instrumentSymbol}
                    onChange={(e) => setInstrumentSymbol(e.target.value.toUpperCase())}
                    placeholder="EURUSD"
                    className={inputCls}
                  />
                  <datalist id="run-broker-symbols">
                    {BROKER_SYMBOLS.map((sym) => (
                      <option key={sym} value={sym} />
                    ))}
                  </datalist>
                </>
              ) : (
                <>
                  <div className="grid grid-cols-[1fr_auto] gap-2 items-start">
                    <div>
                      <label className={labelCls}>Symbol</label>
                      {firmsLoading ? (
                        <div className={`${inputCls} text-text-tertiary`}>Loading…</div>
                      ) : allowedSymbols.length === 0 ? (
                        <div className={`${inputCls} text-text-tertiary`}>
                          No rulesets configured
                        </div>
                      ) : (
                        <select
                          value={instrumentSymbol}
                          onChange={(e) => setInstrumentSymbol(e.target.value)}
                          className={inputCls}
                        >
                          {allowedSymbols.map((sym) => {
                            const name = lookupInstrumentName(sym)
                            return (
                              <option key={sym} value={sym}>
                                {name ? `${sym} — ${name}` : sym}
                              </option>
                            )
                          })}
                        </select>
                      )}
                    </div>
                    <div className="w-[90px]">
                      <div className="flex items-center mb-1">
                        <label className={labelCls.replace(' mb-1', '')}>Contract</label>
                        <InfoTooltip
                          content="NinjaTrader contract month in MM-YY format. Defaults to the current front-month quarterly contract. Contract-specific data typically begins 3–6 months before expiry."
                          side="left"
                        />
                      </div>
                      <input
                        type="text"
                        value={contractMonth}
                        onChange={(e) => setContractMonth(e.target.value)}
                        placeholder="06-26"
                        className={inputCls}
                      />
                    </div>
                  </div>
                  {instrumentSymbol && (
                    <div className="flex items-center justify-between mt-[4px]">
                      {lookupInstrumentName(instrumentSymbol) && (
                        <span className="text-[10px] text-text-tertiary">
                          {lookupInstrumentName(instrumentSymbol)}
                        </span>
                      )}
                      <span className="text-[10px] text-text-tertiary ml-auto">
                        Submits as:{' '}
                        <span className="font-mono text-text-secondary">{instrument}</span>
                      </span>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Bar size */}
            <div className="min-w-0">
              <div className="flex items-center mb-1">
                <label className={labelCls.replace(' mb-1', '')}>Bar size</label>
                <InfoTooltip
                  content={
                    !isNt8
                      ? 'Candle interval the strategy is replayed on. Strategy parameters (e.g. lookback periods) are in bar-counts — retune them when changing bar size.'
                      : 'Candle interval fed to the strategy. Smaller bars = more trades, more noise, higher commission drag. Larger bars = fewer, cleaner signals. Strategy parameters (e.g. lookback periods) are in bar-counts, not minutes — retune them when changing bar size.'
                  }
                />
              </div>
              <select
                value={barValue}
                onChange={(e) => setBarValue(Number(e.target.value))}
                className={inputCls}
              >
                {BAR_PRESETS.map((v) => (
                  <option key={v} value={v}>
                    {barLabel(v)}
                  </option>
                ))}
              </select>
            </div>

            {/* Period */}
            <div className="min-w-0">
              <div className="flex items-center mb-1">
                <label className={labelCls.replace(' mb-1', '')}>Period</label>
                <InfoTooltip content="Data availability varies by contract. Specific contracts (e.g. MNQ 06-26) only have data from when that contract opened — typically 3–6 months before expiry. For multi-year backtests, use a NinjaTrader continuous contract (e.g. @MNQ #C) and adjust the symbol above." />
              </div>
              <PeriodPicker
                compact
                start={startDate}
                end={endDate}
                onChange={(s, e) => {
                  setStartDate(s)
                  setEndDate(e)
                }}
                limit={historyLimit}
              />
            </div>
          </div>

          {/* Sizing Mode — who decides the size. Hidden when the strategy decides. */}
          {!selfSizing && (
            <div>
              <SectionHead
                label="Sizing Mode"
                tooltip="Who decides how big each trade is. Automatic = the ruleset's rules decide. Manual = you set the risk % and it doesn't move. Applies to strategies that trade unit size and let the engine size them (e.g. ORB)."
              />
              <div className="flex gap-2">
                <PresetBtn
                  label="Automatic"
                  active={sizingMode !== 'manual'}
                  onClick={() => setSizingMode('consistent')}
                />
                <PresetBtn
                  label="Manual"
                  active={sizingMode === 'manual'}
                  onClick={() => setSizingMode('manual')}
                />
              </div>

              {sizingMode === 'manual' ? (
                <div className="mt-2.5">
                  <label className={labelCls}>Risk % per trade</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      step="0.1"
                      min="0.1"
                      max="100"
                      value={manualPct}
                      onChange={(e) => setManualPct(e.target.value)}
                      className={`${inputCls} max-w-[120px]`}
                    />
                    <span className="text-[12px] text-text-tertiary">
                      % of balance, every trade
                    </span>
                  </div>
                  {!manualPctValid && (
                    <p className="text-[11px] text-neg-text mt-1.5">
                      Enter a risk % between 0 and 100.
                    </p>
                  )}
                  <p className="text-[10px] text-text-tertiary mt-2 leading-relaxed">
                    Risks exactly this much of the balance on every trade. The account's hard rules
                    still clamp it — on a ruleset with a drawdown floor or contract ladder you may
                    get less. Pair with{' '}
                    <span className="text-text-secondary">Unconstrained (No Limits)</span> for no
                    clamps at all.
                  </p>
                </div>
              ) : (
                <>
                  <div className="flex gap-2 mt-2.5">
                    <PresetBtn
                      label="Consistent"
                      active={sizingMode === 'consistent'}
                      onClick={() => setSizingMode('consistent')}
                    />
                    <PresetBtn
                      label="Bullet"
                      active={sizingMode === 'bullet'}
                      onClick={() => setSizingMode('bullet')}
                    />
                  </div>
                  <p className="text-[10px] text-text-tertiary mt-2 leading-relaxed">
                    {sizingMode === 'consistent'
                      ? 'Sizes each trade off room ÷ 7 — steady, spreads risk across trades. Best for clearing a consistency rule.'
                      : 'Sizes each trade to the most the firm’s contract ladder allows — fastest to target, higher variance.'}
                  </p>
                </>
              )}
            </div>
          )}

          {!selfSizing && <Divider />}

          {/* Evaluate Against — prop firm challenges for futures, personal ruleset(s) for forex */}
          <div>
            <SectionHead label="Evaluate Against" />
            {!isNt8 ? (
              firmsLoading ? (
                <div className="text-[12px] text-text-tertiary">Loading rulesets…</div>
              ) : forexFirms.length === 0 ? (
                <div className="text-[12px] text-text-tertiary">No forex rulesets configured.</div>
              ) : (
                <div className="space-y-2">
                  {forexFirms.map((f) => (
                    <label key={f.id} className="flex items-center gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedFirms.has(f.id)}
                        onChange={() => toggleFirm(f.id)}
                        className="w-4 h-4 rounded accent-accent flex-shrink-0"
                      />
                      <span className="text-[13px] text-text-primary flex-1">{f.name}</span>
                      <span
                        className={`text-[10px] px-[5px] py-[2px] rounded-pill font-semibold uppercase tracking-[0.3px] flex-shrink-0 ${
                          f.account_tier === 'funded'
                            ? 'bg-pos-muted text-pos-text'
                            : 'bg-warn-muted text-warn-text'
                        }`}
                      >
                        {f.account_tier}
                      </span>
                    </label>
                  ))}
                  {selectedFirms.size === 0 && (
                    <p className="text-[11px] text-neg-text mt-2">Select at least one ruleset.</p>
                  )}
                </div>
              )
            ) : firmsLoading ? (
              <div className="text-[12px] text-text-tertiary">Loading rulesets…</div>
            ) : futuresFirms.length === 0 ? (
              <div className="text-[12px] text-text-tertiary">
                No prop firm challenges configured.
              </div>
            ) : (
              <div className="space-y-4">
                {/* Prop firm selector — dropdown scales to any number of brands */}
                {brandNames.length > 1 ? (
                  <select
                    value={selectedBrand}
                    onChange={(e) => {
                      setSelectedBrand(e.target.value)
                      setSelectedFirms(new Set())
                    }}
                    className={inputCls}
                  >
                    {brandNames.map((brand) => (
                      <option key={brand} value={brand}>
                        {brand}
                      </option>
                    ))}
                  </select>
                ) : brandNames.length === 1 ? (
                  <div className="text-[13px] font-medium text-text-primary">{brandNames[0]}</div>
                ) : null}

                {/* Challenge checkboxes */}
                <div>
                  {brandNames.length > 1 && (
                    <div className="text-[11px] text-text-tertiary mb-2">Challenge</div>
                  )}
                  <div className="space-y-2">
                    {brandFirms.map((f) => (
                      <label key={f.id} className="flex items-center gap-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedFirms.has(f.id)}
                          onChange={() => toggleFirm(f.id)}
                          className="w-4 h-4 rounded accent-accent flex-shrink-0"
                        />
                        <span className="text-[13px] text-text-primary flex-1">
                          {firmChallengeName(f.name)}
                        </span>
                        <span
                          className={`text-[10px] px-[5px] py-[2px] rounded-pill font-semibold uppercase tracking-[0.3px] flex-shrink-0 ${
                            f.account_tier === 'funded'
                              ? 'bg-pos-muted text-pos-text'
                              : 'bg-warn-muted text-warn-text'
                          }`}
                        >
                          {f.account_tier}
                        </span>
                      </label>
                    ))}
                  </div>

                  {/* "Both" convenience — only when 2+ challenges */}
                  {brandFirms.length >= 2 && (
                    <label className="flex items-center gap-3 cursor-pointer mt-3 pt-3 border-t border-border-subtle">
                      <input
                        type="checkbox"
                        checked={allBrandSelected}
                        onChange={toggleAllBrand}
                        className="w-4 h-4 rounded accent-accent flex-shrink-0"
                      />
                      <span className="text-[12px] text-text-secondary">
                        Both Evaluation and Funded{' '}
                        <span className="text-text-tertiary">(recommended)</span>
                      </span>
                    </label>
                  )}
                </div>
              </div>
            )}
            {isNt8 && !firmsLoading && selectedFirms.size === 0 && (
              <p className="text-[11px] text-neg-text mt-2">Select at least one challenge.</p>
            )}
          </div>

          {/* ── Strategy settings — READ them by default, EDIT on request ──────────
              Aaron, 2026-08-15: *"I hate going through all these settings to figure out what is
              my default strategy settings. I should have a concise section that... shows them to
              me. And then only if I wanna change that, then I go into the parameters."* So the
              modal opens on the summary and the editor is one click away.
              ⚠ The count of CHANGED settings is on the header either way, because the summary is
              the thing a reader trusts to tell them nothing unusual is set. */}
          {strategy.param_schema.length > 0 && (
            <>
              <Divider />
              <div>
                <div className="flex items-center justify-between mb-2.5">
                  <SectionHead label="Strategy Settings" />
                  {changedCount > 0 && (
                    <span
                      data-testid="run-params-changed"
                      className="text-[11px] text-accent font-medium"
                    >
                      {changedCount} changed from default
                    </span>
                  )}
                </div>
                <ParamEditor
                  schema={strategy.param_schema}
                  mode="run"
                  layout="compact"
                  values={params}
                  onChange={(name, val) => setParams((p) => ({ ...p, [name]: val }))}
                />
              </div>
            </>
          )}

          {/* Foundational config — NT8 only (NinjaScript injection, not applicable to MT5) */}
          {isNt8 && primaryRuleset && (
            <>
              <Divider />
              <div>
                <div className="flex items-center justify-between mb-2">
                  <SectionHead label="Foundational Config" />
                  <span className="text-[11px] text-text-tertiary">
                    from{' '}
                    <span className="text-text-secondary font-medium">{primaryRuleset.name}</span>
                  </span>
                </div>
                <p className="text-[11px] text-text-tertiary mb-3">
                  <span className="text-text-secondary font-medium">
                    Firm-controlled — set at run time by the ruleset, read-only.
                  </span>{' '}
                  Injected into the strategy automatically; to change them, edit the ruleset.
                </p>
                <div className="grid grid-cols-2 gap-1.5">
                  {[
                    [
                      'Account Size',
                      primaryRuleset.account_size != null
                        ? `$${primaryRuleset.account_size.toLocaleString()}`
                        : '—',
                    ],
                    [
                      'Risk / Trade',
                      primaryRuleset.risk_per_trade_pct != null
                        ? `${primaryRuleset.risk_per_trade_pct}%`
                        : '—',
                    ],
                    [
                      'Max Daily Loss',
                      primaryRuleset.daily_loss_cap != null
                        ? `$${primaryRuleset.daily_loss_cap.toLocaleString()}`
                        : '—',
                    ],
                    [
                      'Halt Fraction',
                      primaryRuleset.daily_halt_fraction != null
                        ? String(primaryRuleset.daily_halt_fraction)
                        : '—',
                    ],
                    [
                      'Max Consec. Losses',
                      primaryRuleset.max_consecutive_losses != null
                        ? String(primaryRuleset.max_consecutive_losses)
                        : '—',
                    ],
                    ['Force Flat ET', primaryRuleset.force_flat_time_et ?? '—'],
                    [
                      'Entry Hours ET',
                      primaryRuleset.earliest_entry_time_et && primaryRuleset.latest_entry_time_et
                        ? `${primaryRuleset.earliest_entry_time_et} – ${primaryRuleset.latest_entry_time_et}`
                        : '—',
                    ],
                    ['Days Allowed', primaryRuleset.days_of_week_allowed?.join(', ') || '—'],
                    [
                      'Daily Target',
                      primaryRuleset.daily_profit_target != null
                        ? `$${primaryRuleset.daily_profit_target.toLocaleString()}`
                        : '—',
                    ],
                    [
                      'Lock-In At',
                      primaryRuleset.daily_profit_lock_pct != null
                        ? `${(primaryRuleset.daily_profit_lock_pct * 100).toFixed(0)}% of target`
                        : '—',
                    ],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="flex items-center justify-between px-2.5 py-1.5 rounded bg-bg-sunken border border-border-subtle/50"
                    >
                      <span className="text-[11px] text-text-tertiary">{label}</span>
                      <span className="text-[11px] font-mono text-text-secondary tabular-nums">
                        {value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {isPython && (
            <>
              <Divider />

              {/* Costs — ONE switch, on by default (2026-08-24) */}
              <div>
                <SectionHead
                  label="Costs"
                  tooltip="A charged run is what you can trade; a free run is a diagnostic that tells you how much of the edge is friction. Every figure is measured off the broker account below — they are facts, not settings."
                  open={costsOpen}
                  onToggle={() => setCostsOpen((o) => !o)}
                  summary={chargeCosts ? `charged · ${brokerProfile}` : 'GROSS — no costs charged'}
                />

                {/* 🔴 The switch sits OUTSIDE the fold. Everything below it is explanation, and a
                    run's single most important physical fact must not be one click away behind a
                    collapsed heading — that is how the old design let every run ship frictionless
                    without anybody deciding to. */}
                <div className="flex items-start gap-2.5 mb-2">
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
                        ? 'The result is net of friction — the number you can actually trade.'
                        : 'A diagnostic only. It answers how much of the edge is friction, never whether the strategy works.'}
                    </span>
                  </span>
                </div>

                {!chargeCosts && (
                  <p className="mb-2 text-[11px] text-warn-text bg-warn-muted rounded px-2 py-1.5 leading-snug">
                    This run will report a gross figure. It is not comparable to a charged run —
                    real fills change which setups exist, not just what they pay.
                  </p>
                )}

                <div className="flex items-center gap-2 mb-2.5">
                  <label className="text-[11px] text-text-secondary flex-shrink-0">
                    Broker account
                  </label>
                  <select
                    value={brokerProfile}
                    onChange={(e) => setBrokerProfile(e.target.value)}
                    className={`${inputCls} max-w-[220px]`}
                  >
                    {(brokerProfiles ?? []).map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.id}
                      </option>
                    ))}
                  </select>
                </div>

                {/* A tier nobody has measured refuses rather than borrowing a sibling's figure —
                    PU Prime's tiers measured 2.7x apart. Said here, before the button. */}
                {chargeCosts && brokerUnpriced && (
                  <p className="mb-2 text-[11px] text-warn-text bg-warn-muted rounded px-2 py-1.5 leading-snug">
                    This account&apos;s spread has never been measured, so it cannot be run charged.
                    Measure it first, or pick an account that has been.
                  </p>
                )}

                {costsOpen && chargeCosts && !brokerUnpriced && (
                  <div className="space-y-1">
                    {chargedRows.map((row) => (
                      <div
                        key={row.label}
                        className="flex items-start gap-2.5 px-2.5 py-2 rounded border border-border-subtle/50 bg-bg-sunken"
                      >
                        <span className="min-w-0">
                          <span className="flex items-center gap-1.5">
                            <span className="text-[12px] text-text-primary">{row.label}</span>
                            {row.tag && (
                              <span className="text-[9px] uppercase tracking-[0.4px] px-1 py-[1px] rounded bg-warn-muted text-warn-text">
                                {row.tag}
                              </span>
                            )}
                          </span>
                          <span className="block text-[11px] text-text-tertiary leading-snug">
                            {row.detail}
                          </span>
                        </span>
                      </div>
                    ))}

                    {/* 🔴 Slippage is the ONE cost that stays a separate, typed opt-in, and the
                        tag says why. Every other figure above is measured; this one is a guess,
                        and folding a guess in beside three measurements would make them
                        indistinguishable on the page. 0 means it is not charged at all. */}
                    <div className="px-2.5 py-2 rounded border border-border-subtle/50 bg-bg-sunken">
                      <span className="flex items-center gap-1.5 mb-1">
                        <span className="text-[12px] text-text-primary">Slippage</span>
                        <span className="text-[9px] uppercase tracking-[0.4px] px-1 py-[1px] rounded bg-warn-muted text-warn-text">
                          a guess
                        </span>
                      </span>
                      <span className="block text-[11px] text-text-tertiary leading-snug mb-1.5">
                        Nobody has measured this. Leave it at 0 unless you mean to charge an
                        assumption; it is charged on market exits only.
                      </span>
                      <div className="max-w-[220px]">{slippageInput}</div>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {/* 🔴 "Advanced" was these two fields and NOTHING ELSE, and both are costs — so on the
              python runner they now live inside the Costs section, under the layer that charges
              them. NT8 and MT5 have no layers at all (their tester charges these two directly, and
              `cost_layers` is sent as null), so there is nowhere else for them to go and the
              section stays exactly as it was for those runners. */}
          {!isPython && (
            <>
              <Divider />
              <div>
                <SectionHead label="Costs" />
                <div className="grid grid-cols-2 gap-3">
                  <div>{commissionInput}</div>
                  <div>{slippageInput}</div>
                </div>
              </div>
            </>
          )}
        </form>

        {/* ── Footer ──────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle flex-shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="flex items-center gap-[6px] px-4 py-[7px] rounded-md text-[13px] font-medium bg-accent text-bg-base hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Play size={12} />
            {trigger.isPending ? 'Starting…' : 'Run Backtest'}
          </button>
        </div>
      </div>
    </div>
  )
}
