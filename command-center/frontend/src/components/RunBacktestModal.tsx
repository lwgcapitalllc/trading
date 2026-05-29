import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { X, Play } from 'lucide-react'
import { useFirms, useTriggerBacktest } from '@/hooks/useLab'
import type { Strategy, ParamSchemaEntry } from '@/types'

// ── Default dates ─────────────────────────────────────────────────────────────

function defaultDates(): { start: string; end: string } {
  const end = new Date()
  end.setDate(end.getDate() - 1)
  const start = new Date(end)
  start.setFullYear(end.getFullYear() - 1)
  return {
    end:   end.toISOString().split('T')[0],
    start: start.toISOString().split('T')[0],
  }
}

// ── Param input ───────────────────────────────────────────────────────────────

function ParamInput({
  entry,
  value,
  onChange,
}: {
  entry: ParamSchemaEntry
  value: number | boolean | string
  onChange: (v: number | boolean | string) => void
}) {
  const baseInput = 'bg-bg-sunken border border-border-subtle rounded-md px-3 py-[6px] text-[13px] text-text-primary w-full focus:outline-none focus:border-accent transition-colors'

  const t = entry.type.toLowerCase()

  if (t === 'bool' || t === 'boolean') {
    return (
      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={e => onChange(e.target.checked)}
          className="w-4 h-4 rounded accent-accent cursor-pointer"
        />
        <span className="text-[13px] text-text-secondary">{entry.display_name}</span>
      </label>
    )
  }

  return (
    <div>
      <label className="block text-[11px] text-text-secondary mb-1">{entry.display_name}</label>
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
        className={baseInput}
      />
      {(entry.min != null || entry.max != null) && (
        <div className="text-[10px] text-text-tertiary mt-[2px]">
          {entry.min != null && entry.max != null
            ? `${entry.min} – ${entry.max}`
            : entry.min != null ? `min ${entry.min}` : `max ${entry.max}`}
        </div>
      )}
    </div>
  )
}

// ── Modal ─────────────────────────────────────────────────────────────────────

interface Props {
  strategy: Strategy
  onClose: () => void
}

export function RunBacktestModal({ strategy, onClose }: Props) {
  const navigate  = useNavigate()
  const trigger   = useTriggerBacktest()
  const { data: firms, isLoading: firmsLoading } = useFirms()

  const dates = useMemo(() => defaultDates(), [])

  // ── Form state ──────────────────────────────────────────────────────────────
  const [instrument, setInstrument]       = useState(strategy.default_instrument ?? '')
  const [startDate, setStartDate]         = useState(dates.start)
  const [endDate, setEndDate]             = useState(dates.end)
  const [commPerSide, setCommPerSide]     = useState(2.25)
  const [slippageTicks, setSlippageTicks] = useState(1)

  // Initialise params from schema defaults
  const [params, setParams] = useState<Record<string, number | boolean | string>>(() => {
    const init: Record<string, number | boolean | string> = {}
    for (const e of strategy.param_schema) {
      init[e.name] = e.default as number | boolean | string
    }
    return init
  })

  // Firms: all pre-selected once loaded
  const [selectedFirms, setSelectedFirms] = useState<Set<string>>(new Set())
  useEffect(() => {
    if (firms?.length) setSelectedFirms(new Set(firms.map(f => f.id)))
  }, [firms])

  const toggleFirm = (id: string) => {
    setSelectedFirms(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  // ── Group params by group field ─────────────────────────────────────────────
  const paramGroups = useMemo(() => {
    const groups = new Map<string, ParamSchemaEntry[]>()
    for (const e of strategy.param_schema) {
      const g = e.group || 'General'
      if (!groups.has(g)) groups.set(g, [])
      groups.get(g)!.push(e)
    }
    return groups
  }, [strategy.param_schema])

  // ── Validation ──────────────────────────────────────────────────────────────
  const canSubmit =
    instrument.trim() !== '' &&
    startDate !== '' &&
    endDate !== '' &&
    startDate < endDate &&
    selectedFirms.size > 0 &&
    !trigger.isPending

  // ── Submit ──────────────────────────────────────────────────────────────────
  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return

    trigger.mutate(
      {
        strategy_id:        strategy.id,
        instrument:         instrument.trim(),
        params:             params as Record<string, unknown>,
        bar_type:           'Minute',
        bar_value:          5,
        start_date:         startDate,
        end_date:           endDate,
        commission_per_side: commPerSide,
        slippage_ticks:     slippageTicks,
        evaluate_firms:     Array.from(selectedFirms),
      },
      {
        onSuccess: (data) => {
          onClose()
          navigate(`/backtests/runs/${data.run_id}`)
        },
      },
    )
  }

  // ── Close on backdrop click ─────────────────────────────────────────────────
  function handleBackdrop(e: React.MouseEvent<HTMLDivElement>) {
    if (e.target === e.currentTarget) onClose()
  }

  // ── Close on Escape ─────────────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const inputCls = 'bg-bg-sunken border border-border-subtle rounded-md px-3 py-[6px] text-[13px] text-text-primary w-full focus:outline-none focus:border-accent transition-colors'
  const labelCls = 'block text-[11px] text-text-secondary mb-1'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={handleBackdrop}
    >
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[520px] max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle flex-shrink-0">
          <div>
            <div className="text-[15px] font-semibold">Run Backtest</div>
            <div className="text-[12px] text-text-tertiary mt-[1px] font-mono">{strategy.name}</div>
          </div>
          <button
            onClick={onClose}
            className="text-text-tertiary hover:text-text-primary transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Scrollable form body */}
        <form onSubmit={handleSubmit} className="overflow-y-auto flex-1 px-5 py-4 space-y-5">

          {/* Instrument + date range */}
          <div className="grid grid-cols-1 gap-4">
            <div>
              <label className={labelCls}>Instrument</label>
              <input
                type="text"
                value={instrument}
                onChange={e => setInstrument(e.target.value)}
                placeholder="e.g. MNQ 06-26"
                className={inputCls}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelCls}>Start date</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={e => setStartDate(e.target.value)}
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls}>End date</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={e => setEndDate(e.target.value)}
                  className={inputCls}
                />
              </div>
            </div>
            {startDate && endDate && startDate >= endDate && (
              <p className="text-[11px] text-neg-text -mt-2">Start date must be before end date.</p>
            )}
          </div>

          {/* Params */}
          {strategy.param_schema.length > 0 && (
            <div>
              <div className="text-[11px] font-semibold text-text-tertiary uppercase tracking-[0.6px] mb-3">
                Strategy params
              </div>
              <div className="space-y-4">
                {Array.from(paramGroups.entries()).map(([group, entries]) => (
                  <div key={group}>
                    {paramGroups.size > 1 && (
                      <div className="text-[10px] text-text-tertiary uppercase tracking-[0.5px] mb-2">
                        {group}
                      </div>
                    )}
                    <div className="space-y-3">
                      {entries.map(e => (
                        <ParamInput
                          key={e.name}
                          entry={e}
                          value={params[e.name] ?? e.default as number | boolean | string}
                          onChange={v => setParams(p => ({ ...p, [e.name]: v }))}
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Firms */}
          <div>
            <div className="text-[11px] font-semibold text-text-tertiary uppercase tracking-[0.6px] mb-3">
              Firms to evaluate
            </div>
            {firmsLoading ? (
              <div className="text-[12px] text-text-tertiary">Loading firms…</div>
            ) : !firms?.length ? (
              <div className="text-[12px] text-text-tertiary">No firms configured.</div>
            ) : (
              <div className="space-y-2">
                {firms.map(firm => (
                  <label
                    key={firm.id}
                    className="flex items-center gap-3 cursor-pointer group"
                  >
                    <input
                      type="checkbox"
                      checked={selectedFirms.has(firm.id)}
                      onChange={() => toggleFirm(firm.id)}
                      className="w-4 h-4 rounded accent-accent cursor-pointer flex-shrink-0"
                    />
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-[13px] text-text-primary truncate">{firm.name}</span>
                      <span className={`inline-flex px-[6px] py-[1px] rounded-pill text-[10px] font-semibold uppercase tracking-[0.4px] flex-shrink-0 ${
                        firm.account_tier === 'funded'
                          ? 'bg-pos-muted text-pos-text'
                          : 'bg-warn-muted text-warn-text'
                      }`}>
                        {firm.account_tier}
                      </span>
                      <span className="text-[11px] text-text-tertiary flex-shrink-0">
                        ${firm.max_loss_eod.toLocaleString()} DD
                      </span>
                    </div>
                  </label>
                ))}
              </div>
            )}
            {selectedFirms.size === 0 && (
              <p className="text-[11px] text-neg-text mt-2">Select at least one firm.</p>
            )}
          </div>

          {/* Advanced */}
          <details>
            <summary className="text-[11px] font-semibold text-text-tertiary uppercase tracking-[0.6px] cursor-pointer select-none">
              Advanced
            </summary>
            <div className="grid grid-cols-2 gap-3 mt-3">
              <div>
                <label className={labelCls}>Commission / side ($)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={commPerSide}
                  onChange={e => setCommPerSide(parseFloat(e.target.value) || 0)}
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls}>Slippage (ticks)</label>
                <input
                  type="number"
                  step="1"
                  min="0"
                  value={slippageTicks}
                  onChange={e => setSlippageTicks(parseInt(e.target.value, 10) || 0)}
                  className={inputCls}
                />
              </div>
            </div>
          </details>
        </form>

        {/* Footer */}
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
