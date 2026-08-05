import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sliders, AlertTriangle, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { Tier3WarningModal } from '@/components/Tier3WarningModal'
import { ParamEditor, sweepChoices, type ParamValue } from '@/components/ParamEditor'
import { useTriggerOptimization, useFirms, useRunningVpsJob, useOptimizations, useParamTypes, useStrategy } from '@/hooks/useLab'
import { isNt8Runner, runnerScope, runningJobFor, RUNNER_LABEL } from '@/lib/runner'
import type { BacktestDetail, ParamAxisSpec } from '@/types'

interface Props {
  run: BacktestDetail
}

type AxisEdit =
  | { mode: 'range'; min: string; max: string; step: string }
  | { mode: 'fixed'; value: string }
  | { mode: 'list'; values: string[] }

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

// Why a range can't be counted — shown per axis, and the reason Go is blocked. A range that
// only "shows — combos" is one the user reads as still typing; an inverted min/max is a
// finished, wrong answer and the backend rejects it. Say which.
function rangeProblem(min: string, max: string, step: string): string | null {
  const lo = parseFloat(min), hi = parseFloat(max), incr = parseFloat(step)
  if (isNaN(lo) || isNaN(hi) || isNaN(incr)) return 'incomplete'
  if (incr <= 0) return 'step must be greater than 0'
  if (lo > hi)   return 'max is below min'
  return null
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
  // Ruleset/mode/regime are NT8-only (they drive injected foundational params); MT5 and
  // Python both run raw. The lock, separately, is per-runner.
  const isNt8       = isNt8Runner(run.runner)
  const blockingJob = runningJobFor(runningJob, run.runner)
  const jobBlocked  = !!blockingJob?.running
  const runnerLabel = RUNNER_LABEL[runnerScope(run.runner)]

  const evalFirm = run.evaluations[0]
  const [firmId, setFirmId]         = useState(evalFirm?.ruleset_id ?? '')
  const [mode, setMode]             = useState<'eval' | 'funded'>('eval')

  const selectedFirm = firms?.find(f => f.id === firmId)
  const isPropFirm = selectedFirm?.ruleset_type === 'prop_eval' || selectedFirm?.ruleset_type === 'prop_funded'
  const [regimeFilter, setRegimeFilter] = useState<string>('')

  // Minimum trades a combo needs before it is allowed to WIN. Profit factor has no opinion
  // about sample size, so without a floor two lucky trades at PF 8.0 outrank two hundred at
  // PF 2.0 and the optimizer hands you the two. 30 is a starting point, not a rule — it is
  // editable here and shown on the results page, which is what keeps it from being a silent
  // narrowing. The API's own default is 0: nothing is assumed of a caller that says nothing.
  const [minTrades, setMinTrades] = useState('30')
  const minTradesNum = Math.max(0, Math.floor(Number(minTrades) || 0))

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
    setMinTrades('30')
  }
  // True once the user has changed anything from the opened-run defaults.
  const isDirty =
    Object.values(axes).some(a => a.mode !== 'fixed') ||
    firmId !== (evalFirm?.ruleset_id ?? '') ||
    mode !== 'eval' ||
    regimeFilter !== '' ||
    minTrades !== '30'

  const rangeParamCount = Object.values(axes).filter(a => a.mode !== 'fixed').length

  // Total backtests = cartesian product of every swept range's value count.
  // `incomplete` flags ranges still being typed; `rangeErrors` flags ones that are finished
  // and wrong (step 0, max below min) — those used to be lumped together as "— combos" with
  // the Go button still enabled, so the run started and died minutes later.
  let comboCount = 1
  let comboIncomplete = false
  const rangeErrors: Record<string, string> = {}
  for (const [name, ax] of Object.entries(axes)) {
    if (ax.mode === 'list') { comboCount *= Math.max(1, ax.values.length); continue }
    if (ax.mode !== 'range') continue
    const problem = rangeProblem(ax.min, ax.max, ax.step)
    if (problem && problem !== 'incomplete') rangeErrors[name] = problem
    const c = rangeValueCount(ax.min, ax.max, ax.step)
    if (c == null) { comboIncomplete = true; continue }
    comboCount *= c
  }

  // Roughly how long the grid will take, from the source run's own measured duration. Only a
  // Python sweep is predictable this way — it replays the SAME bars this run replayed, on this
  // box, across cores. NT8 and MT5 load data once and parallelise inside their own tester, so
  // per-combo cost there is not this run's cost and no estimate is offered.
  const runSeconds = run.started_at && run.completed_at
    ? Math.max(1, (new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000)
    : null
  const cores = Math.max(1, (navigator.hardwareConcurrency || 4) - 1)
  const estSeconds = run.runner === 'python' && runSeconds && !comboIncomplete
    ? (runSeconds * comboCount) / cores
    : null
  const fmtEta = (s: number) =>
    s < 90 ? `~${Math.round(s)}s`
    : s < 5400 ? `~${Math.round(s / 60)} min`
    : s < 172800 ? `~${(s / 3600).toFixed(1)} hours`
    : `~${(s / 86400).toFixed(1)} days`
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

  // A dropdown / on-off param is swept as its own value SET, and only the Python runner can walk
  // one — NT8 and MT5 hand a Start/Step/End range to their own tester (the backend refuses a list
  // for them too, so this is not the only guard).
  const listSweepOk = run.runner === 'python'
  const choicesOf = (name: string) => {
    const p = strategy?.param_schema?.find(x => x.name === name)
    return p ? sweepChoices(p) : []
  }

  const toggleAxis = (name: string) => {
    const cur = axes[name]
    if (cur && cur.mode !== 'fixed') {
      // Demote back to fixed
      const back = cur.mode === 'range' ? cur.min : String(run.params[name] ?? '')
      setAxes(prev => ({ ...prev, [name]: { mode: 'fixed', value: back } }))
      return
    }
    const choices = listSweepOk ? choicesOf(name) : []
    if (choices.length >= 2) {
      // Start with EVERY option ticked, then untick what you don't want — one click is a complete
      // sweep, which is the point of a closed set.
      setAxes(prev => ({ ...prev, [name]: { mode: 'list', values: choices.map(c => c.value) } }))
      return
    }
    // Promote to range: use current value as default for min/max. `cur` can be
    // absent when optimizing from a run whose params predate a schema param.
    const numVal = Number(cur?.value ?? run.params[name] ?? 0)
    setAxes(prev => ({
      ...prev,
      [name]: { mode: 'range', min: String(numVal), max: String(numVal + 10), step: '5' },
    }))
  }

  // Tick / untick one value of a list axis. Never empties it: a swept param with nothing selected
  // expands to zero combinations, so the whole optimization would run nothing.
  const toggleListValue = (name: string, value: string) => {
    const all = choicesOf(name).map(c => c.value)
    setAxes(prev => {
      const cur = prev[name]
      if (cur?.mode !== 'list') return prev
      const has = cur.values.includes(value)
      if (has && cur.values.length === 1) return prev
      const next = has ? cur.values.filter(x => x !== value) : [...cur.values, value]
      // Keep the schema's order rather than click order, so the grid reads the way the panel does.
      return { ...prev, [name]: { mode: 'list', values: all.length ? all.filter(x => next.includes(x)) : next } }
    })
  }

  const updateAxis = (name: string, field: string, value: string) => {
    setAxes(prev => ({ ...prev, [name]: { ...prev[name], [field]: value } as AxisEdit }))
  }

  const handleGo = () => {
    if (isNt8 && !firmId) { toast.error('Select a ruleset'); return }

    const param_grid: Record<string, ParamAxisSpec> = {}
    for (const [k, ax] of Object.entries(axes)) {
      if (ax.mode === 'range') {
        param_grid[k] = { min: Number(ax.min), max: Number(ax.max), step: Number(ax.step) }
      } else if (ax.mode === 'list') {
        // A bool ships as a real boolean — the strategy's config field is typed, and the string
        // "false" is truthy everywhere it would land.
        const isBool = strategy?.param_schema?.find(p => p.name === k)?.type === 'bool'
        param_grid[k] = isBool ? ax.values.map(v => v === 'true') : ax.values
      }
    }

    if (!Object.keys(param_grid).length) {
      toast.error('Mark at least one parameter to sweep')
      return
    }
    if (Object.keys(intErrors).length) {
      toast.error('Fix whole-number errors before running')
      return
    }
    if (Object.keys(rangeErrors).length) {
      toast.error('Fix the invalid ranges before running')
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
      ruleset_id:         isNt8 ? firmId : null,
      mode:               isNt8 && isPropFirm ? mode : 'raw',
      search_method:      'native',
      param_grid,
      regime_filter:      isNt8 ? (regimeFilter || null) : null,
      source_run_id:      run.run_id,
      // Inherit the source run's cost contract. Without this the whole grid was ranked on a
      // FREE book and its winner then compared against a run that had spread and swap charged
      // — two numbers produced under different physics, presented as a comparison.
      cost_layers:        run.cost_layers,
      broker_profile:     run.broker_profile,
      min_trades:         minTradesNum,
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
              <span className="font-semibold">{runnerLabel} is busy:</span> {blockingJob?.description} — wait for it to finish.
            </p>
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          {/* Config — NT8 shows ruleset/mode/regime; MT5 shows nothing above the param grid */}
          <div className="grid grid-cols-3 gap-3">
            {isNt8 && (
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
            {isNt8 && (
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
            <div className="col-span-3">
              <label className="block text-[11px] text-text-tertiary mb-1 uppercase tracking-wide font-medium">
                Minimum trades to win
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={0}
                  step={1}
                  value={minTrades}
                  onChange={e => setMinTrades(e.target.value)}
                  className="w-24 bg-bg-sunken border border-border-subtle rounded-md px-2 py-[6px] text-[12px] font-mono focus:outline-none focus:border-accent"
                />
                <span className="text-[11px] text-text-tertiary leading-snug">
                  {minTradesNum === 0
                    ? 'No floor — the highest profit factor wins, even on two trades.'
                    : `Combos under ${minTradesNum} trades still run and still show in the table — they just can't be the ★ winner.`}
                </span>
              </div>
            </div>
          </div>

          {/* Cost inheritance — what this grid will be charged, stated rather than assumed */}
          <div className="flex items-start gap-2 px-3 py-2 rounded-md bg-bg-sunken border border-border-subtle">
            <span className="text-[11px] text-text-tertiary leading-snug">
              {run.runner !== 'python'
                ? <>Costs come from the {runnerLabel} tester's own settings — commission ${run.commission_per_side}/side, {run.slippage_ticks} tick slippage.</>
                : run.cost_layers?.length
                ? <>Every combo is charged the same costs as this run — <span className="text-text-secondary font-medium">{run.cost_layers.join(', ')}</span> on <span className="font-mono">{run.broker_profile}</span>. The winner is comparable to the run you launched from.</>
                : <>This run charged <span className="text-text-secondary font-medium">no costs</span>, so the grid runs free too. A free winner is not comparable to a priced run.</>}
            </span>
          </div>

          {/* Param editor (shared) — mark a parameter to sweep it across a range */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[12px] font-semibold text-text-secondary">Parameters</span>
              <span className="text-[11px] text-text-tertiary">
                {listSweepOk
                  ? 'Mark a parameter to sweep it — a range for numbers, a value set for dropdowns'
                  : 'Mark a parameter to sweep it across a range'}
              </span>
            </div>
            <ParamEditor
              schema={strategy?.param_schema ?? []}
              mode="optimize"
              values={run.params as Record<string, ParamValue>}
              axes={axes}
              onToggleAxis={toggleAxis}
              onUpdateAxis={updateAxis}
              intErrors={intErrors}
              allowListSweep={listSweepOk}
              onToggleListValue={toggleListValue}
            />
          </div>

          {Object.keys(rangeErrors).length > 0 && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-md bg-neg-muted border border-neg-text/20">
              <AlertTriangle size={13} className="text-neg-text flex-shrink-0 mt-[1px]" />
              <p className="text-[12px] text-neg-text leading-snug">
                {Object.entries(rangeErrors).map(([k, why]) => `${k}: ${why}`).join(' · ')}
              </p>
            </div>
          )}

          {rangeParamCount > 0 && (
            <p className="text-[11px] text-text-tertiary">
              {rangeParamCount} parameter{rangeParamCount !== 1 ? 's' : ''} will be swept using the native optimizer.
              {estSeconds != null && <>
                {' '}At this run's own speed that is roughly{' '}
                <span className={estSeconds > 6 * 3600 ? 'text-warn-text font-semibold' : 'text-text-secondary font-medium'}>
                  {fmtEta(estSeconds)}
                </span>
                {' '}on {cores} core{cores !== 1 ? 's' : ''}.
              </>}
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
            title={
              comboIncomplete ? 'One of the ranges is not filled in yet'
              : Object.keys(rangeErrors).length ? 'One of the ranges is invalid'
              : undefined
            }
            // comboIncomplete and rangeErrors are both blocking now. They were shown as
            // "— combos" and nothing else, so Go stayed enabled and the backend was handed a
            // grid it could not expand.
            disabled={
              triggerOpt.isPending || rangeParamCount === 0 || jobBlocked ||
              comboIncomplete || Object.keys(rangeErrors).length > 0 ||
              Object.keys(intErrors).length > 0
            }
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
  const blockingJob = runningJobFor(runningJob, run.runner)
  const jobBlocked  = !!blockingJob?.running

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
        title={jobBlocked ? `${RUNNER_LABEL[runnerScope(run.runner)]} is busy: ${blockingJob?.description}` : undefined}
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
