import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { X, Play, Info } from 'lucide-react'
import { AlertTriangle } from 'lucide-react'
import { useFirms, useTriggerBacktest, useRunningVpsJob } from '@/hooks/useLab'
import type { Strategy, Firm, ParamSchemaEntry } from '@/types'

// ── Date helpers ──────────────────────────────────────────────────────────────

function today(): string {
  return new Date().toISOString().split('T')[0]
}

function yearsAgo(n: number): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - n)
  return d.toISOString().split('T')[0]
}

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
  MES:  'Micro E-mini S&P 500',
  MNQ:  'Micro E-mini Nasdaq-100',
  MYM:  'Micro E-mini Dow Jones',
  M2K:  'Micro E-mini Russell 2000',
  MGC:  'Micro Gold',
  MCL:  'Micro Crude Oil',
  MBT:  'Micro Bitcoin',
  MET:  'Micro Ether',
}

const MT5_SYMBOLS = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'GBPJPY', 'AUDUSD', 'USDCAD', 'EURGBP']

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

function paramTooltipText(entry: ParamSchemaEntry): string {
  if (entry.description) return entry.description
  const parts: string[] = []
  if (entry.min != null && entry.max != null) parts.push(`Range: ${entry.min}–${entry.max}`)
  else if (entry.min != null) parts.push(`Min: ${entry.min}`)
  else if (entry.max != null) parts.push(`Max: ${entry.max}`)
  parts.push(`Default: ${entry.default}`)
  parts.push(`Type: ${entry.type}`)
  return parts.join(' · ')
}

// ── Param input ───────────────────────────────────────────────────────────────

function ParamInput({
  entry,
  value,
  onChange,
  tooltipSide = 'right',
}: {
  entry: ParamSchemaEntry
  value: number | boolean | string
  onChange: (v: number | boolean | string) => void
  tooltipSide?: 'right' | 'left'
}) {
  const inputCls = 'bg-bg-sunken border border-border-subtle rounded-md px-3 py-[6px] text-[13px] text-text-primary w-full focus:outline-none focus:border-accent transition-colors'
  const t = entry.type.toLowerCase()
  const tooltip = paramTooltipText(entry)

  if (t === 'bool' || t === 'boolean') {
    return (
      <label className="flex items-center gap-2 cursor-pointer col-span-2">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={e => onChange(e.target.checked)}
          className="w-4 h-4 rounded accent-accent"
        />
        <span className="text-[13px] text-text-secondary">{entry.display_name}</span>
        <InfoTooltip content={tooltip} side="right" />
      </label>
    )
  }

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <div className="flex items-center">
          <label className="text-[11px] text-text-secondary">{entry.display_name}</label>
          <InfoTooltip content={tooltip} side={tooltipSide} />
        </div>
        {(entry.min != null || entry.max != null) && (
          <span className="text-[10px] text-text-tertiary">
            {entry.min != null && entry.max != null
              ? `${entry.min}–${entry.max}`
              : entry.min != null ? `≥ ${entry.min}` : `≤ ${entry.max}`}
          </span>
        )}
      </div>
      <input
        type="number"
        step={t === 'int' ? 1 : 'any'}
        min={entry.min}
        max={entry.max}
        value={value as number}
        onChange={e => {
          const v = t === 'int' ? parseInt(e.target.value, 10) : parseFloat(e.target.value)
          onChange(isNaN(v) ? (entry.default as number) : v)
        }}
        className={inputCls}
      />
    </div>
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

function PresetBtn({ label, active, onClick }: { label: string; active?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-[10px] py-[3px] rounded text-[11px] border transition-colors ${
        active
          ? 'text-accent bg-accent/10 border-accent/50'
          : 'text-text-tertiary hover:text-accent hover:bg-accent/10 border-border-subtle hover:border-accent/30'
      }`}
    >
      {label}
    </button>
  )
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

  const isMt5 = strategy.runner === 'mt5'

  const inputCls = 'bg-bg-sunken border border-border-subtle rounded-md px-3 py-[6px] text-[13px] text-text-primary w-full focus:outline-none focus:border-accent transition-colors'
  const dateCls  = `${inputCls} [&::-webkit-calendar-picker-indicator]:invert [&::-webkit-calendar-picker-indicator]:opacity-50 [&::-webkit-calendar-picker-indicator]:cursor-pointer`
  const labelCls = 'block text-[11px] text-text-secondary mb-1'

  // ── Instrument ───────────────────────────────────────────────────────────────
  const frontMonth = useMemo(() => currentFrontMonth(), [])
  const allowedSymbols = useMemo(() => getAllowedSymbols(firms), [firms])

  const parsed = useMemo(
    () => parseSuggestedInstrument(strategy.suggested_instrument, frontMonth),
    [strategy.suggested_instrument, frontMonth],
  )

  const [instrumentSymbol, setInstrumentSymbol] = useState(
    isMt5 ? 'EURUSD' : parsed.symbol
  )
  const [contractMonth, setContractMonth] = useState(parsed.month)

  // NT8 only: once firms load, ensure symbol is in allowed list
  useEffect(() => {
    if (isMt5) return
    if (allowedSymbols.length === 0) return
    if (!instrumentSymbol || !allowedSymbols.includes(instrumentSymbol)) {
      setInstrumentSymbol(allowedSymbols[0])
    }
  }, [allowedSymbols]) // eslint-disable-line react-hooks/exhaustive-deps

  const instrument = isMt5
    ? instrumentSymbol
    : contractMonth.trim()
      ? `${instrumentSymbol} ${contractMonth.trim()}`
      : instrumentSymbol

  // ── Period ───────────────────────────────────────────────────────────────────
  const todayStr = useMemo(() => today(), [])
  const presets = useMemo(() => [
    { label: '1Y',  start: yearsAgo(1),    end: todayStr },
    { label: '3Y',  start: yearsAgo(3),    end: todayStr },
    { label: '5Y',  start: yearsAgo(5),    end: todayStr },
    { label: 'All', start: '2019-01-01',   end: todayStr },
  ], [todayStr])

  const [startDate, setStartDate] = useState(() => yearsAgo(1))
  const [endDate, setEndDate]     = useState(() => today())

  const activePreset = useMemo(() => {
    const match = presets.find(p => p.start === startDate && p.end === endDate)
    return match?.label ?? null
  }, [presets, startDate, endDate])

  // ── Bar size ─────────────────────────────────────────────────────────────────
  const BAR_PRESETS = isMt5 ? [5, 15, 30, 60, 240] : [1, 3, 5, 15, 30]
  const [barValue, setBarValue] = useState(isMt5 ? 60 : 5)

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
    for (const f of firms) {
      const brand = firmBrandName(f.name)
      if (!map.has(brand)) map.set(brand, [])
      map.get(brand)!.push(f)
    }
    return map
  }, [firms])

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
    return firms.find(f => f.id === firstId) ?? null
  }, [selectedFirms, firms])

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

  // ── Param groups (strategy_logic only — foundational hidden from user) ────────
  const paramGroups = useMemo(() => {
    const map = new Map<string, ParamSchemaEntry[]>()
    for (const e of strategy.param_schema) {
      if (e.category === 'foundational') continue
      const g = e.group || 'General'
      if (!map.has(g)) map.set(g, [])
      map.get(g)!.push(e)
    }
    return map
  }, [strategy.param_schema])

  // ── Validation ───────────────────────────────────────────────────────────────
  const jobBlocked = !!runningJob?.running
  const canSubmit =
    instrumentSymbol !== '' &&
    startDate !== '' && endDate !== '' && startDate < endDate &&
    (isMt5 || selectedFirms.size > 0) &&
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
        evaluate_rulesets:   isMt5 ? [] : Array.from(selectedFirms),
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
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[680px] max-h-[90vh] flex flex-col shadow-2xl">

        {/* ── Header ──────────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle flex-shrink-0">
          <div className="text-[15px] font-semibold">Run Backtest</div>
          <button onClick={onClose} className="text-text-tertiary hover:text-text-primary transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* ── Running job warning ─────────────────────────────────────────────── */}
        {jobBlocked && (
          <div className="mx-5 mt-4 flex items-start gap-2 px-3 py-2.5 rounded-md bg-warn-muted/40 border border-warn-text/20">
            <AlertTriangle size={13} className="text-warn-text flex-shrink-0 mt-[1px]" />
            <p className="text-[12px] text-warn-text leading-snug">
              <span className="font-semibold">A backtest is already running:</span> {runningJob?.description} — wait for it to finish before starting a new run.
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
            {isMt5 ? (
              <>
                <input
                  type="text"
                  value={instrumentSymbol}
                  onChange={e => setInstrumentSymbol(e.target.value.toUpperCase())}
                  placeholder="EURUSD"
                  className={inputCls}
                />
                <div className="flex gap-1.5 mt-2 flex-wrap">
                  {MT5_SYMBOLS.map(sym => (
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
                        {allowedSymbols.map(sym => (
                          <option key={sym} value={sym}>
                            {sym}{INSTRUMENT_NAMES[sym] ? ` — ${INSTRUMENT_NAMES[sym]}` : ''}
                          </option>
                        ))}
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
                    {INSTRUMENT_NAMES[instrumentSymbol] && (
                      <span className="text-[10px] text-text-tertiary">{INSTRUMENT_NAMES[instrumentSymbol]}</span>
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
            <div className="grid grid-cols-[1fr_16px_1fr] items-center gap-1 mb-2">
              <input
                type="date" value={startDate}
                onChange={e => setStartDate(e.target.value)}
                className={dateCls}
              />
              <span className="text-text-tertiary text-center text-[12px]">→</span>
              <input
                type="date" value={endDate}
                onChange={e => setEndDate(e.target.value)}
                className={dateCls}
              />
            </div>
            {startDate && endDate && startDate >= endDate && (
              <p className="text-[11px] text-neg-text mb-2">Start must be before end.</p>
            )}
            <div className="flex gap-2">
              {presets.map(p => (
                <PresetBtn
                  key={p.label}
                  label={p.label}
                  active={activePreset === p.label}
                  onClick={() => { setStartDate(p.start); setEndDate(p.end) }}
                />
              ))}
            </div>
          </div>

          {/* Bar Size */}
          <div>
            <SectionHead
              label="Bar Size"
              tooltip={isMt5
                ? "Candle interval for the MT5 Strategy Tester. Strategy parameters (e.g. lookback periods) are in bar-counts — retune them when changing bar size."
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

          <Divider />

          {/* Evaluate Against — NT8 only (prop firm challenges are futures-specific) */}
          {!isMt5 && <div>
            <SectionHead label="Evaluate Against" />
            {firmsLoading ? (
              <div className="text-[12px] text-text-tertiary">Loading rulesets…</div>
            ) : firms.length === 0 ? (
              <div className="text-[12px] text-text-tertiary">No rulesets configured.</div>
            ) : (
              <div className="space-y-4">
                {/* Prop firm radio — only shown when multiple brands */}
                {brandNames.length > 1 && (
                  <div>
                    <div className="text-[11px] text-text-tertiary mb-2">Prop firm challenges</div>
                    <div className="space-y-[6px]">
                      {brandNames.map(brand => (
                        <label key={brand} className="flex items-center gap-2 cursor-pointer">
                          <input
                            type="radio" name="brand"
                            checked={selectedBrand === brand}
                            onChange={() => {
                              setSelectedBrand(brand)
                              setSelectedFirms(new Set())
                            }}
                            className="accent-accent"
                          />
                          <span className="text-[13px] text-text-primary">{brand}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {/* Single brand: show name as header */}
                {brandNames.length === 1 && (
                  <div className="text-[13px] font-medium text-text-primary">
                    {brandNames[0]}
                  </div>
                )}

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
            {!firmsLoading && selectedFirms.size === 0 && (
              <p className="text-[11px] text-neg-text mt-2">Select at least one challenge.</p>
            )}
          </div>}

          {/* Strategy parameters */}
          {strategy.param_schema.length > 0 && (
            <>
              <Divider />
              <div>
                <SectionHead label="Strategy Parameters" />
                <div className="space-y-4">
                  {Array.from(paramGroups.entries()).map(([group, entries]) => (
                    <div key={group}>
                      {paramGroups.size > 1 && (
                        <div className="text-[10px] text-text-tertiary uppercase tracking-[0.5px] mb-2">
                          {group}
                        </div>
                      )}
                      <div className="grid grid-cols-2 gap-3">
                        {entries.map((e, i) => (
                          <ParamInput
                            key={e.name}
                            entry={e}
                            value={params[e.name] ?? e.default as number | boolean | string}
                            onChange={v => setParams(p => ({ ...p, [e.name]: v }))}
                            tooltipSide={i % 2 === 1 ? 'left' : 'right'}
                          />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* Foundational config — NT8 only (NinjaScript injection, not applicable to MT5) */}
          {!isMt5 && primaryRuleset && (
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
                  These values are injected automatically. To change them, edit the ruleset.
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
                  <InfoTooltip content={isMt5 ? "Commission per side in account currency. Applied to every fill by the MT5 Strategy Tester." : "Round-trip cost per contract, per side. NinjaTrader typically charges ~$2.25/side for micro futures at most brokers. Applied to every fill."} />
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
                  <InfoTooltip content={isMt5 ? "Additional points deducted per fill to model spread and slippage. Conservative backtests use 1–3 points for major forex pairs." : "Additional ticks deducted per fill to model market impact and bid/ask spread. 1 tick = $0.50 for MNQ, $1.25 for MES. Conservative backtests use 1–2 ticks."} side="left" />
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
