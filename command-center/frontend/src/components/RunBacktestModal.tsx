import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { X, Play, Info } from 'lucide-react'
import { AlertTriangle } from 'lucide-react'
import { useFirms, useTriggerBacktest, useRunningVpsJob } from '@/hooks/useLab'
import { ParamEditor } from '@/components/ParamEditor'
import { PeriodPicker, PresetBtn, today, yearsAgo } from '@/components/PeriodPicker'
import { isNt8Runner, runnerScope, runningJobFor, RUNNER_LABEL, runnerMarket } from '@/lib/runner'
import type { Strategy, Firm, SizingMode } from '@/types'

// ── Date helpers ──────────────────────────────────────────────────────────────

// Quarterly futures roll months: Mar (3), Jun (6), Sep (9), Dec (12)
function currentFrontMonth(): string {
  const d = new Date()
  const year = d.getFullYear()
  const month = d.getMonth() + 1
  const quarters = [3, 6, 9, 12]
  let q = quarters.find(m => m >= month)
  let y = year
  if (!q) { q = 3; y = year + 1 }
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
  MES:  'Micro E-mini S&P 500',
  MNQ:  'Micro E-mini Nasdaq-100',
  MYM:  'Micro E-mini Dow Jones',
  M2K:  'Micro E-mini Russell 2000',
  // Full-size E-mini equity index
  ES:   'E-mini S&P 500',
  NQ:   'E-mini Nasdaq-100',
  YM:   'E-mini Dow Jones',
  RTY:  'E-mini Russell 2000',
  // Metals
  MGC:  'Micro Gold',
  GC:   'Gold',
  MSI:  'Micro Silver',
  SI:   'Silver',
  // Energy
  MCL:  'Micro Crude Oil',
  CL:   'Crude Oil',
  NG:   'Natural Gas',
  // Crypto
  MBT:  'Micro Bitcoin',
  MET:  'Micro Ether',
  BTC:  'Bitcoin',
  ETH:  'Ether',
  // Fixed income
  ZB:   '30-Year T-Bond',
  ZN:   '10-Year T-Note',
  ZF:   '5-Year T-Note',
  ZT:   '2-Year T-Note',
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
const BROKER_SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'GBPJPY', 'AUDUSD', 'USDCAD', 'EURGBP', 'AUDJPY', 'CADJPY']

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
      <span className={`absolute ${anchorCls} bottom-[calc(100%+5px)] z-50 hidden group-hover/tip:block w-56 rounded-md bg-bg-surface border border-border-default px-2.5 py-2 text-[11px] text-text-secondary shadow-xl pointer-events-none leading-relaxed`}>
        {content}
      </span>
    </span>
  )
}

// ── Small UI pieces ───────────────────────────────────────────────────────────

function SectionHead({ label, tooltip }: { label: string; tooltip?: string }) {
  return (
    <div className="flex items-center gap-1 text-[10px] font-semibold text-text-tertiary uppercase tracking-[0.7px] mb-3">
      {label}
      {tooltip && <InfoTooltip content={tooltip} />}
    </div>
  )
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
  const trigger  = useTriggerBacktest()
  const { data: firms = [], isLoading: firmsLoading } = useFirms()
  const { data: runningJob } = useRunningVpsJob()

  // NT8 is the only futures platform: contract months, prop-challenge rulesets, and injected
  // foundational params are all NT8-only. MT5 and Python both trade the broker's spot symbols.
  const scope     = runnerScope(strategy.runner)
  const isNt8     = isNt8Runner(strategy.runner)
  const isFutures = runnerMarket(strategy.runner) === 'futures'

  const inputCls = 'bg-bg-sunken border border-border-subtle rounded-md px-3 py-[6px] text-[13px] text-text-primary w-full focus:outline-none focus:border-accent transition-colors'
  const labelCls = 'block text-[11px] text-text-secondary mb-1'

  // ── Instrument ───────────────────────────────────────────────────────────────
  const frontMonth = useMemo(() => currentFrontMonth(), [])
  const futuresFirms = useMemo(() => firms.filter(f => f.market !== 'forex'), [firms])
  const forexFirms   = useMemo(() => firms.filter(f => f.market === 'forex'), [firms])
  const allowedSymbols = useMemo(() => getAllowedSymbols(futuresFirms), [futuresFirms])

  const parsed = useMemo(
    () => parseSuggestedInstrument(strategy.suggested_instrument, frontMonth),
    [strategy.suggested_instrument, frontMonth],
  )

  const [instrumentSymbol, setInstrumentSymbol] = useState(
    isNt8 ? parsed.symbol : scope === 'python' ? (parsed.symbol || 'XAUUSD') : 'EURUSD'
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
  const [endDate, setEndDate]     = useState(() => today())

  // ── Bar size ─────────────────────────────────────────────────────────────────
  const BAR_PRESETS = isNt8 ? [1, 3, 5, 15, 30] : [5, 15, 30, 60, 240]
  const [barValue, setBarValue] = useState(isNt8 ? 5 : scope === 'python' ? 15 : 60)

  // ── Sizing mode — how the engine sizes each trade from the room left ───────────
  // A self-sizing strategy sizes its own trades off its own risk % param — the engine never
  // touches it, so there is no mode to pick and the whole section is hidden.
  const selfSizing = strategy.self_sizing === true
  const [sizingMode, setSizingMode] = useState<SizingMode>('consistent')
  const [manualPct, setManualPct]   = useState('1.0')
  const manualPctNum = parseFloat(manualPct)
  const manualPctValid = sizingMode !== 'manual' || (!isNaN(manualPctNum) && manualPctNum > 0 && manualPctNum <= 100)

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
  const allBrandSelected = brandFirms.length > 0 && brandFirms.every(f => selectedFirms.has(f.id))

  const toggleFirm = (id: string) =>
    setSelectedFirms(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const toggleAllBrand = () => {
    if (allBrandSelected) {
      setSelectedFirms(prev => {
        const next = new Set(prev)
        brandFirms.forEach(f => next.delete(f.id))
        return next
      })
    } else {
      setSelectedFirms(prev => {
        const next = new Set(prev)
        brandFirms.forEach(f => next.add(f.id))
        return next
      })
    }
  }

  // ── Primary ruleset (first selected — drives foundational config display) ─────
  const primaryRuleset = useMemo(() => {
    if (selectedFirms.size === 0) return null
    const firstId = Array.from(selectedFirms)[0]
    return futuresFirms.find(f => f.id === firstId) ?? null
  }, [selectedFirms, futuresFirms])

  // ── Advanced — pre-filled from primary ruleset, user-editable ────────────────
  const [commPerSide, setCommPerSide]     = useState(2.25)
  const [slippageTicks, setSlippageTicks] = useState(1)

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
  const jobBlocked  = !!blockingJob?.running
  // Forex runs evaluate against the personal forex ruleset(s); futures against prop
  // challenges. Both require ≥1 selection, but never block when none exist for the platform.
  const evalRequiredMet = isNt8
    ? selectedFirms.size > 0
    : (selectedFirms.size > 0 || forexFirms.length === 0)
  const canSubmit =
    instrumentSymbol !== '' &&
    startDate !== '' && endDate !== '' && startDate < endDate &&
    evalRequiredMet &&
    manualPctValid &&
    !trigger.isPending &&
    !jobBlocked

  // ── Submit ───────────────────────────────────────────────────────────────────
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    trigger.mutate(
      {
        strategy_id:         strategy.id,
        instrument,
        params:              params as Record<string, unknown>,
        bar_type:            'Minute',
        bar_value:           barValue,
        start_date:          startDate,
        end_date:            endDate,
        commission_per_side: commPerSide,
        slippage_ticks:      slippageTicks,
        evaluate_rulesets:   Array.from(selectedFirms),
        sizing_mode:         sizingMode,
        manual_risk_pct:     sizingMode === 'manual' ? manualPctNum : null,
      },
      {
        onSuccess: (data) => {
          onClose()
          if (onSuccess) onSuccess(data.run_id)
          else navigate(`/backtests/runs/${data.run_id}`)
        },
      },
    )
  }

  // ── Escape key ───────────────────────────────────────────────────────────────
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[900px] max-h-[90vh] flex flex-col shadow-2xl">

        {/* ── Header ──────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle flex-shrink-0">
          <div className="flex items-center gap-2">
            <div className="text-[15px] font-semibold">Run Backtest</div>
            <span className={`text-[10px] px-2 py-[2px] rounded font-semibold uppercase tracking-[0.5px] border ${
              isFutures
                ? 'bg-accent/10 text-accent border-accent/20'
                : 'bg-warn-muted text-warn-text border-warn-text/30'
            }`}>
              {isFutures ? 'Futures' : 'Forex'}
            </span>
          </div>
          <button onClick={onClose} className="text-text-tertiary hover:text-text-primary transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* ── Running job warning ─────────────────────────────────────────────── */}
        {jobBlocked && (
          <div className="mx-5 mt-4 flex items-start gap-2 px-3 py-2.5 rounded-md bg-warn-muted/40 border border-warn-text/20">
            <AlertTriangle size={13} className="text-warn-text flex-shrink-0 mt-[1px]" />
            <p className="text-[12px] text-warn-text leading-snug">
              <span className="font-semibold">{RUNNER_LABEL[scope]} is busy:</span> {blockingJob?.description} — wait for it to finish before starting a new run.
            </p>
          </div>
        )}

        {/* ── Stale-schema warning — source changed since the last Scan ─────────── */}
        {strategy.needs_scan && (
          <div className="mx-5 mt-4 flex items-start gap-2 px-3 py-2.5 rounded-md bg-warn-muted/40 border border-warn-text/20">
            <AlertTriangle size={13} className="text-warn-text flex-shrink-0 mt-[1px]" />
            <p className="text-[12px] text-warn-text leading-snug">
              <span className="font-semibold">Parameters may be out of date:</span> this strategy's source changed since the last scan. Close this, click <span className="font-semibold">Scan Strategies</span>, then reopen — otherwise the toggles and defaults below are stale.
            </p>
          </div>
        )}

        {/* ── Scrollable body ─────────────────────────────────────────────────── */}
        <form onSubmit={handleSubmit} className="overflow-y-auto flex-1 px-5 py-5 space-y-5">

          {/* Strategy (read-only) */}
          <div>
            <SectionHead label="Strategy" />
            <div className="bg-bg-sunken border border-border-subtle rounded-md px-3 py-[6px] text-[13px] font-mono text-text-secondary">
              {strategy.name || strategy.class_name}
            </div>
          </div>

          {/* Instrument */}
          <div>
            <SectionHead label="Instrument" />
            {!isNt8 ? (
              <>
                <input
                  type="text"
                  value={instrumentSymbol}
                  onChange={e => setInstrumentSymbol(e.target.value.toUpperCase())}
                  placeholder="EURUSD"
                  className={inputCls}
                />
                <div className="flex gap-1.5 mt-2 flex-wrap">
                  {BROKER_SYMBOLS.map(sym => (
                    <PresetBtn
                      key={sym}
                      label={sym}
                      active={instrumentSymbol === sym}
                      onClick={() => setInstrumentSymbol(sym)}
                    />
                  ))}
                </div>
              </>
            ) : (
              <>
                <div className="grid grid-cols-[1fr_auto] gap-2 items-start">
                  <div>
                    <label className={labelCls}>Symbol</label>
                    {firmsLoading ? (
                      <div className={`${inputCls} text-text-tertiary`}>Loading…</div>
                    ) : allowedSymbols.length === 0 ? (
                      <div className={`${inputCls} text-text-tertiary`}>No rulesets configured</div>
                    ) : (
                      <select
                        value={instrumentSymbol}
                        onChange={e => setInstrumentSymbol(e.target.value)}
                        className={inputCls}
                      >
                        {allowedSymbols.map(sym => {
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
                      <InfoTooltip content="NinjaTrader contract month in MM-YY format. Defaults to the current front-month quarterly contract. Contract-specific data typically begins 3–6 months before expiry." side="left" />
                    </div>
                    <input
                      type="text"
                      value={contractMonth}
                      onChange={e => setContractMonth(e.target.value)}
                      placeholder="06-26"
                      className={inputCls}
                    />
                  </div>
                </div>
                {instrumentSymbol && (
                  <div className="flex items-center justify-between mt-[4px]">
                    {lookupInstrumentName(instrumentSymbol) && (
                      <span className="text-[10px] text-text-tertiary">{lookupInstrumentName(instrumentSymbol)}</span>
                    )}
                    <span className="text-[10px] text-text-tertiary ml-auto">
                      Submits as: <span className="font-mono text-text-secondary">{instrument}</span>
                    </span>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Period */}
          <div>
            <SectionHead
              label="Period"
              tooltip="Data availability varies by contract. Specific contracts (e.g. MNQ 06-26) only have data from when that contract opened — typically 3–6 months before expiry. For multi-year backtests, use a NinjaTrader continuous contract (e.g. @MNQ #C) and adjust the symbol above."
            />
            <PeriodPicker
              start={startDate}
              end={endDate}
              onChange={(s, e) => { setStartDate(s); setEndDate(e) }}
            />
          </div>

          {/* Bar Size */}
          <div>
            <SectionHead
              label="Bar Size"
              tooltip={!isNt8
                ? "Candle interval the strategy is replayed on. Strategy parameters (e.g. lookback periods) are in bar-counts — retune them when changing bar size."
                : "Candle interval fed to the strategy. Smaller bars = more trades, more noise, higher commission drag. Larger bars = fewer, cleaner signals. Strategy parameters (e.g. lookback periods) are in bar-counts, not minutes — retune them when changing bar size."}
            />
            <div className="flex gap-2">
              {BAR_PRESETS.map(v => (
                <PresetBtn
                  key={v}
                  label={barLabel(v)}
                  active={barValue === v}
                  onClick={() => setBarValue(v)}
                />
              ))}
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
                      type="number" step="0.1" min="0.1" max="100"
                      value={manualPct}
                      onChange={e => setManualPct(e.target.value)}
                      className={`${inputCls} max-w-[120px]`}
                    />
                    <span className="text-[12px] text-text-tertiary">% of balance, every trade</span>
                  </div>
                  {!manualPctValid && (
                    <p className="text-[11px] text-neg-text mt-1.5">Enter a risk % between 0 and 100.</p>
                  )}
                  <p className="text-[10px] text-text-tertiary mt-2 leading-relaxed">
                    Risks exactly this much of the balance on every trade. The account's hard rules still
                    clamp it — on a ruleset with a drawdown floor or contract ladder you may get less.
                    Pair with <span className="text-text-secondary">Unconstrained (No Limits)</span> for
                    no clamps at all.
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
                  {forexFirms.map(f => (
                    <label key={f.id} className="flex items-center gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={selectedFirms.has(f.id)}
                        onChange={() => toggleFirm(f.id)}
                        className="w-4 h-4 rounded accent-accent flex-shrink-0"
                      />
                      <span className="text-[13px] text-text-primary flex-1">{f.name}</span>
                      <span className={`text-[10px] px-[5px] py-[2px] rounded-pill font-semibold uppercase tracking-[0.3px] flex-shrink-0 ${
                        f.account_tier === 'funded' ? 'bg-pos-muted text-pos-text' : 'bg-warn-muted text-warn-text'
                      }`}>
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
              <div className="text-[12px] text-text-tertiary">No prop firm challenges configured.</div>
            ) : (
              <div className="space-y-4">
                {/* Prop firm selector — dropdown scales to any number of brands */}
                {brandNames.length > 1 ? (
                  <select
                    value={selectedBrand}
                    onChange={e => { setSelectedBrand(e.target.value); setSelectedFirms(new Set()) }}
                    className={inputCls}
                  >
                    {brandNames.map(brand => (
                      <option key={brand} value={brand}>{brand}</option>
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
                    {brandFirms.map(f => (
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
                        <span className={`text-[10px] px-[5px] py-[2px] rounded-pill font-semibold uppercase tracking-[0.3px] flex-shrink-0 ${
                          f.account_tier === 'funded' ? 'bg-pos-muted text-pos-text' : 'bg-warn-muted text-warn-text'
                        }`}>
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

          {/* Strategy parameters */}
          {strategy.param_schema.length > 0 && (
            <>
              <Divider />
              <div>
                <SectionHead label="Strategy Parameters" />
                <ParamEditor
                  schema={strategy.param_schema}
                  mode="run"
                  values={params}
                  onChange={(name, val) => setParams(p => ({ ...p, [name]: val }))}
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
                    from <span className="text-text-secondary font-medium">{primaryRuleset.name}</span>
                  </span>
                </div>
                <p className="text-[11px] text-text-tertiary mb-3">
                  <span className="text-text-secondary font-medium">Firm-controlled — set at run time by the ruleset, read-only.</span>{' '}
                  Injected into the strategy automatically; to change them, edit the ruleset.
                </p>
                <div className="grid grid-cols-2 gap-1.5">
                  {[
                    ['Account Size',        primaryRuleset.account_size != null ? `$${primaryRuleset.account_size.toLocaleString()}` : '—'],
                    ['Risk / Trade',        primaryRuleset.risk_per_trade_pct != null ? `${primaryRuleset.risk_per_trade_pct}%` : '—'],
                    ['Max Daily Loss',      primaryRuleset.daily_loss_cap != null ? `$${primaryRuleset.daily_loss_cap.toLocaleString()}` : '—'],
                    ['Halt Fraction',       primaryRuleset.daily_halt_fraction != null ? String(primaryRuleset.daily_halt_fraction) : '—'],
                    ['Max Consec. Losses',  primaryRuleset.max_consecutive_losses != null ? String(primaryRuleset.max_consecutive_losses) : '—'],
                    ['Force Flat ET',       primaryRuleset.force_flat_time_et ?? '—'],
                    ['Entry Hours ET',      (primaryRuleset.earliest_entry_time_et && primaryRuleset.latest_entry_time_et)
                                              ? `${primaryRuleset.earliest_entry_time_et} – ${primaryRuleset.latest_entry_time_et}`
                                              : '—'],
                    ['Days Allowed',        primaryRuleset.days_of_week_allowed?.join(', ') || '—'],
                    ['Daily Target',        primaryRuleset.daily_profit_target != null ? `$${primaryRuleset.daily_profit_target.toLocaleString()}` : '—'],
                    ['Lock-In At',          primaryRuleset.daily_profit_lock_pct != null ? `${(primaryRuleset.daily_profit_lock_pct * 100).toFixed(0)}% of target` : '—'],
                  ].map(([label, value]) => (
                    <div key={label} className="flex items-center justify-between px-2.5 py-1.5 rounded bg-bg-sunken border border-border-subtle/50">
                      <span className="text-[11px] text-text-tertiary">{label}</span>
                      <span className="text-[11px] font-mono text-text-secondary tabular-nums">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          <Divider />

          {/* Advanced */}
          <div>
            <SectionHead label="Advanced" />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="flex items-center mb-1">
                  <label className={labelCls.replace(' mb-1', '')}>Commission / side ($)</label>
                  <InfoTooltip content={!isNt8 ? "Commission per side in account currency. Applied to every fill." : "Round-trip cost per contract, per side. NinjaTrader typically charges ~$2.25/side for micro futures at most brokers. Applied to every fill."} />
                </div>
                <input
                  type="number" step="0.01" min="0" value={commPerSide}
                  onChange={e => setCommPerSide(parseFloat(e.target.value) || 0)}
                  className={inputCls}
                />
              </div>
              <div>
                <div className="flex items-center mb-1">
                  <label className={labelCls.replace(' mb-1', '')}>Slippage (ticks)</label>
                  <InfoTooltip content={!isNt8 ? "Additional points deducted per fill to model spread and slippage. Conservative backtests use 1–3 points for major forex pairs." : "Additional ticks deducted per fill to model market impact and bid/ask spread. 1 tick = $0.50 for MNQ, $1.25 for MES. Conservative backtests use 1–2 ticks."} side="left" />
                </div>
                <input
                  type="number" step="1" min="0" value={slippageTicks}
                  onChange={e => setSlippageTicks(parseInt(e.target.value, 10) || 0)}
                  className={inputCls}
                />
              </div>
            </div>
          </div>

        </form>

        {/* ── Footer ──────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle flex-shrink-0">
          <button
            type="button" onClick={onClose}
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
