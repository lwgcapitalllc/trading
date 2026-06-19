import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sliders, AlertTriangle, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { Tier3WarningModal } from '@/components/Tier3WarningModal'
import { ParamEditor, type ParamValue } from '@/components/ParamEditor'
import { useTriggerOptimization, useFirms, useRunningVpsJob, useOptimizations, useParamTypes, useStrategy } from '@/hooks/useLab'
import type { BacktestDetail, ParamAxisSpec } from '@/types'

interface Props {
  run: BacktestDetail
}

type AxisEdit =
  | { mode: 'range'; min: string; max: string; step: string }
  | { mode: 'fixed'; value: string }

// ── Range value counting ───────────────────────────────────────────────────────

// Number of values a range produces — matches RangePreview's inclusive loop.
// Returns null when the range is incomplete or invalid.
function rangeValueCount(min: string, max: string, step: string): number | null {
  const lo   = parseFloat(min)
  const hi   = parseFloat(max)
  const incr = parseFloat(step)
  if (isNaN(lo) || isNaN(hi) || isNaN(incr) || incr <= 0 || lo > hi) return null
  return Math.floor((hi - lo) / incr + 1e-9) + 1
}

// ── Optimizer modal ────────────────────────────────────────────────────────────

function OptimizerModal({
  run,
  onClose,
}: {
  run: BacktestDetail
  onClose: () => void
}) {
  const navigate      = useNavigate()
  const { data: firms } = useFirms()
  const triggerOpt    = useTriggerOptimization()
  const { data: runningJob } = useRunningVpsJob()
  const { data: paramTypes } = useParamTypes(run.strategy_id)
  const { data: strategy } = useStrategy(run.strategy_id)
  const isMt5 = run.runner === 'mt5'
  const jobBlocked = isMt5 ? !!runningJob?.mt5?.running : !!runningJob?.nt8?.running

  const evalFirm = run.evaluations[0]
  const [firmId, setFirmId]         = useState(evalFirm?.ruleset_id ?? '')
  const [mode, setMode]             = useState<'eval' | 'funded'>('eval')

  const selectedFirm = firms?.find(f => f.id === firmId)
  const isPropFirm = selectedFirm?.ruleset_type === 'prop_eval' || selectedFirm?.ruleset_type === 'prop_funded'
  const [regimeFilter, setRegimeFilter] = useState<string>('')

  // Foundational params are injected from the ruleset — never exposed in the optimizer grid.
  const FOUNDATIONAL_PARAMS = new Set([
    'AccountSize', 'RiskPerTradePct', 'MaxDailyLoss', 'DailyHaltFraction',
    'MaxConsecutiveLosses', 'CommissionPerSide', 'ForceFlatTimeET',
    'EarliestEntryTimeET', 'LatestEntryTimeET', 'DaysOfWeekAllowed',
    'DailyProfitTarget', 'DailyProfitLockPct',
  ])

  // Build initial axis state from strategy_logic params only
  const buildInitialAxes = (): Record<string, AxisEdit> => {
    const init: Record<string, AxisEdit> = {}
    for (const [k, v] of Object.entries(run.params)) {
      if (!FOUNDATIONAL_PARAMS.has(k)) {
        init[k] = { mode: 'fixed', value: String(v) }
      }
    }
    return init
  }
  const [axes, setAxes] = useState<Record<string, AxisEdit>>(buildInitialAxes)

  const handleReset = () => {
    setAxes(buildInitialAxes())
    setFirmId(evalFirm?.ruleset_id ?? '')
    setMode('eval')
    setRegimeFilter('')
  }
  // True once the user has changed anything from the opened-run defaults.
  const isDirty =
    Object.values(axes).some(a => a.mode === 'range') ||
    firmId !== (evalFirm?.ruleset_id ?? '') ||
    mode !== 'eval' ||
    regimeFilter !== ''

  const rangeParamCount = Object.values(axes).filter(a => a.mode === 'range').length

  // Total backtests = cartesian product of every swept range's value count.
  // `incomplete` flags ranges still being typed (min/max/step not yet valid).
  let comboCount = 1
  let comboIncomplete = false
  for (const ax of Object.values(axes)) {
    if (ax.mode !== 'range') continue
    const c = rangeValueCount(ax.min, ax.max, ax.step)
    if (c == null) { comboIncomplete = true; continue }
    comboCount *= c
  }
  // Color thresholds — each combo is a full backtest, so nudge the user to taper.
  const comboTone =
    comboCount > 1000 ? { text: 'text-neg-text',  bg: 'bg-neg-muted',  border: 'border-neg-text/20'  }
    : comboCount > 250 ? { text: 'text-warn-text', bg: 'bg-warn-muted', border: 'border-warn-text/20' }
    : { text: 'text-accent', bg: 'bg-accent/10', border: 'border-accent/20' }

  const intErrors: Record<string, string> = {}
  for (const [name, ax] of Object.entries(axes)) {
    if (ax.mode !== 'range' || paramTypes?.[name] !== 'int') continue
    const lo = parseFloat(ax.min), hi = parseFloat(ax.max), st = parseFloat(ax.step)
    if (isNaN(lo) || isNaN(hi) || isNaN(st) || st <= 0) continue
    const hasDecimal = [lo, hi, st].some(v => !Number.isInteger(v))
    if (hasDecimal) intErrors[name] = 'Must be whole numbers — this param is an integer in the strategy'
  }

  const toggleAxis = (name: string) => {
    const cur = axes[name]
    if (!cur || cur.mode === 'fixed') {
      // Promote to range: use current value as default for min/max. `cur` can be
      // absent when optimizing from a run whose params predate a schema param.
      const numVal = Number(cur?.value ?? run.params[name] ?? 0)
      setAxes(prev => ({
        ...prev,
        [name]: { mode: 'range', min: String(numVal), max: String(numVal + 10), step: '5' },
      }))
    } else {
      // Demote back to fixed
      setAxes(prev => ({
        ...prev,
        [name]: { mode: 'fixed', value: prev[name].mode === 'range' ? prev[name].min : String(run.params[name] ?? '') },
      }))
    }
  }

  const updateAxis = (name: string, field: string, value: string) => {
    setAxes(prev => ({ ...prev, [name]: { ...prev[name], [field]: value } as AxisEdit }))
  }

  const handleGo = () => {
    if (!isMt5 && !firmId) { toast.error('Select a ruleset'); return }

    const param_grid: Record<string, ParamAxisSpec> = {}
    for (const [k, ax] of Object.entries(axes)) {
      if (ax.mode === 'range') {
        param_grid[k] = { min: Number(ax.min), max: Number(ax.max), step: Number(ax.step) }
      }
    }

    if (!Object.keys(param_grid).length) {
      toast.error('Expand at least one parameter into a range')
      return
    }
    if (Object.keys(intErrors).length) {
      toast.error('Fix whole-number errors before running')
      return
    }

    triggerOpt.mutate({
      strategy_id:        run.strategy_id,
      instrument:         run.instrument,
      bar_type:           run.bar_type,
      bar_value:          run.bar_value,
      start_date:         run.start_date,
      end_date:           run.end_date,
      commission_per_side: run.commission_per_side,
      slippage_ticks:     run.slippage_ticks,
      ruleset_id:         isMt5 ? null : firmId,
      mode:               isMt5 ? 'raw' : isPropFirm ? mode : 'raw',
      search_method:      'native',
      param_grid,
      regime_filter:      isMt5 ? null : (regimeFilter || null),
      source_run_id:      run.run_id,
    }, {
      onSuccess: (data) => {
        onClose()
        navigate(`/optimizations/${data.optimization_id}`)
      },
    })
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[900px] max-h-[85vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="px-5 py-4 border-b border-border-subtle flex-shrink-0">
          <div className="text-[15px] font-semibold">Optimize from this run</div>
          <div className="text-[12px] text-text-tertiary mt-0.5">
            {run.strategy_name} · {run.instrument} · {run.start_date} → {run.end_date}
          </div>
        </div>

        {/* Running job warning */}
        {jobBlocked && (
          <div className="mx-5 mt-4 flex items-start gap-2 px-3 py-2.5 rounded-md bg-warn-muted/40 border border-warn-text/20">
            <AlertTriangle size={13} className="text-warn-text flex-shrink-0 mt-[1px]" />
            <p className="text-[12px] text-warn-text leading-snug">
              <span className="font-semibold">{isMt5 ? 'MT5' : 'NT8'} is busy:</span> {(isMt5 ? runningJob?.mt5 : runningJob?.nt8)?.description} — wait for it to finish.
            </p>
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {/* Config — NT8 shows ruleset/mode/regime; MT5 shows nothing above the param grid */}
          <div className="grid grid-cols-3 gap-3">
            {!isMt5 && (
              <>
                <div className={isPropFirm ? '' : 'col-span-3'}>
                  <label className="block text-[11px] text-text-tertiary mb-1 uppercase tracking-wide font-medium">Ruleset</label>
                  <select
                    value={firmId}
                    onChange={e => setFirmId(e.target.value)}
                    className="w-full bg-bg-sunken border border-border-subtle rounded-md px-2 py-[6px] text-[12px] focus:outline-none focus:border-accent"
                  >
                    <option value="">Select ruleset…</option>
                    {firms?.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
                  </select>
                </div>
                {isPropFirm && (
                  <div>
                    <label className="block text-[11px] text-text-tertiary mb-1 uppercase tracking-wide font-medium">Mode</label>
                    <select
                      value={mode}
                      onChange={e => setMode(e.target.value as 'eval' | 'funded')}
                      className="w-full bg-bg-sunken border border-border-subtle rounded-md px-2 py-[6px] text-[12px] focus:outline-none focus:border-accent"
                    >
                      <option value="eval">Eval</option>
                      <option value="funded">Funded</option>
                    </select>
                  </div>
                )}
              </>
            )}
            {!isMt5 && (
              <div className="col-span-3">
                <label className="block text-[11px] text-text-tertiary mb-1 uppercase tracking-wide font-medium">
                  Regime Filter <span className="normal-case font-normal">(optional — score only trades in this regime)</span>
                </label>
                <select
                  value={regimeFilter}
                  onChange={e => setRegimeFilter(e.target.value)}
                  className="w-full bg-bg-sunken border border-border-subtle rounded-md px-2 py-[6px] text-[12px] focus:outline-none focus:border-accent"
                >
                  <option value="">No filter — score all trades</option>
                  <option value="TRENDING">Trending</option>
                  <option value="TRANSITIONING">Transitioning</option>
                  <option value="RANGING">Ranging</option>
                  <option value="HIGH_VOLATILITY">High Volatility</option>
                  <option value="LOW_VOLATILITY">Low Volatility</option>
                </select>
              </div>
            )}
          </div>

          {/* Param editor (shared) — mark a parameter to sweep it across a range */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[12px] font-semibold text-text-secondary">Parameters</span>
              <span className="text-[11px] text-text-tertiary">Mark a parameter to sweep it across a range</span>
            </div>
            <ParamEditor
              schema={strategy?.param_schema ?? []}
              mode="optimize"
              values={run.params as Record<string, ParamValue>}
              axes={axes}
              onToggleAxis={toggleAxis}
              onUpdateAxis={updateAxis}
              intErrors={intErrors}
            />
          </div>

          {rangeParamCount > 0 && (
            <p className="text-[11px] text-text-tertiary">
              {rangeParamCount} parameter{rangeParamCount !== 1 ? 's' : ''} will be swept using the native optimizer.
              {comboCount > 1000 && !comboIncomplete && ' That is a lot of combinations — consider widening the step or trimming a range.'}
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-border-subtle flex-shrink-0 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {rangeParamCount > 0 && (
              <span
                className={`inline-flex items-center gap-1.5 px-2.5 py-[5px] rounded-md text-[12px] font-mono tabular-nums border ${comboTone.text} ${comboTone.bg} ${comboTone.border}`}
                title="Total backtests the optimizer will run — the product of every swept range"
              >
                <Sliders size={11} />
                {comboIncomplete
                  ? '— combos'
                  : `${comboCount.toLocaleString('en-US')} combo${comboCount !== 1 ? 's' : ''}`}
              </span>
            )}
            <button
              onClick={handleReset}
              disabled={!isDirty}
              className="flex items-center gap-1 text-[12px] text-text-tertiary hover:text-text-secondary transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              title="Restore parameters and options to the values from this run"
            >
              <RotateCcw size={12} />
              Reset
            </button>
          </div>
          <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleGo}
            disabled={triggerOpt.isPending || rangeParamCount === 0 || jobBlocked || Object.keys(intErrors).length > 0}
            className="px-5 py-[7px] rounded-md text-[13px] font-semibold bg-accent text-bg-base hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {triggerOpt.isPending ? 'Starting…' : 'Go'}
          </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Tier 1 soft confirm modal ─────────────────────────────────────────────────

function Tier1ConfirmModal({
  run,
  onConfirm,
  onClose,
}: {
  run: BacktestDetail
  onConfirm: () => void
  onClose: () => void
}) {
  const pf = run.profit_factor?.toFixed(2) ?? '—'
  const dd = run.max_drawdown != null ? `$${run.max_drawdown.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[420px] shadow-2xl">
        <div className="px-5 py-4 border-b border-border-subtle">
          <div className="text-[15px] font-semibold">Strong strategy — optimize anyway?</div>
        </div>
        <div className="px-5 py-4">
          <p className="text-[13px] text-text-secondary">
            This strategy scored <span className="text-pos-text font-semibold">Tier 1 (STRESS TEST)</span>{' '}
            with a profit factor of <span className="font-mono">{pf}</span> and max drawdown of{' '}
            <span className="font-mono">{dd}</span>.
          </p>
          <p className="text-[13px] text-text-secondary mt-2">
            Optimization may lead to overfitting on the training period. Proceed only if you intend
            to stress-test in M3 afterward.
          </p>
        </div>
        <div className="px-5 py-4 border-t border-border-subtle flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-[7px] rounded-md text-[13px] font-medium bg-pos-muted text-pos-text border border-pos-text/30 hover:bg-pos-text/15 transition-colors"
          >
            Proceed with optimization
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main OptimizeButton ────────────────────────────────────────────────────────

type ModalState = 'none' | 'tier1-confirm' | 'tier3-warning' | 'optimizer'

export function OptimizeButton({ run }: Props) {
  const [modal, setModal] = useState<ModalState>('none')
  const navigate = useNavigate()
  const { data: runningJob } = useRunningVpsJob()
  const { data: optimizations } = useOptimizations(run.strategy_id)
  const isMt5Platform = run.runner === 'mt5'
  const jobBlocked = isMt5Platform ? !!runningJob?.mt5?.running : !!runningJob?.nt8?.running

  const runningOpt = optimizations?.find(
    o => o.source_run_id === run.run_id &&
         o.status !== 'complete' &&
         !o.status.startsWith('failed') &&
         o.status !== 'cancelled'
  )

  if (run.status !== 'complete') return null

  if (runningOpt) {
    return (
      <button
        onClick={() => navigate(`/optimizations/${runningOpt.optimization_id}`)}
        className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium bg-gold-muted text-gold-text border border-gold-text/20 hover:bg-gold-text/15 transition-colors"
      >
        <Sliders size={12} className="animate-pulse flex-shrink-0" />
        Optimization in progress
      </button>
    )
  }

  const tier = run.worthiness?.tier

  const handleClick = () => {
    if (jobBlocked) return
    if (tier === 'TIER_1_STRESS_TEST') {
      setModal('tier1-confirm')
    } else if (tier === 'TIER_3_DISCARD') {
      setModal('tier3-warning')
    } else {
      setModal('optimizer')
    }
  }

  return (
    <>
      <button
        onClick={handleClick}
        disabled={jobBlocked}
        title={jobBlocked ? `${isMt5Platform ? 'MT5' : 'NT8'} is busy: ${(isMt5Platform ? runningJob?.mt5 : runningJob?.nt8)?.description}` : undefined}
        className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium bg-gold-muted text-gold-text border border-gold-text/20 hover:bg-gold-text/15 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        <Sliders size={12} />
        Optimize
      </button>

      {modal === 'tier1-confirm' && (
        <Tier1ConfirmModal
          run={run}
          onConfirm={() => setModal('optimizer')}
          onClose={() => setModal('none')}
        />
      )}

      {modal === 'tier3-warning' && (
        <Tier3WarningModal
          run={run}
          onClose={() => setModal('none')}
          onOptimizeAnyway={() => setModal('optimizer')}
        />
      )}

      {modal === 'optimizer' && (
        <OptimizerModal
          run={run}
          onClose={() => setModal('none')}
        />
      )}
    </>
  )
}
