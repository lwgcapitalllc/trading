import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Layers, X, Play, Loader2 } from 'lucide-react'
import { useStrategies, useTriggerStack, useRunningVpsJob, useStackPreview, useHistoryLimit } from '@/hooks/useLab'
import { PeriodPicker, today, yearsAgo } from '@/components/PeriodPicker'
import type { StackMode } from '@/types'

const BAR_PRESETS: [number, string][] = [[5, '5m'], [15, '15m'], [30, '30m'], [60, '1H'], [240, '4H']]

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
}

// The two things a stack can BE. They answer different questions, so the modal states the
// difference in the reader's terms rather than assuming the word "shared" carries it.
const MODES: { key: StackMode; label: string; blurb: string }[] = [
  {
    key: 'screen',
    label: 'Screen',
    blurb: 'Each strategy runs on its own full account and the results are added together. ' +
      'Fast, reuses finished runs — and an UPPER BOUND, because no strategy can ever block another.',
  },
  {
    key: 'shared',
    label: 'Shared account',
    blurb: 'One balance and one risk budget the strategies compete for, replayed together on one ' +
      'clock. This is the demo-account question. Every leg is re-run — nothing is reused.',
  },
]

// Shared config surface for BOTH "New stack" (Backtests → Stacks) and "Rerun stack" (StackDetail).
// One component so the two can never drift — a rerun exposes EXACTLY what creation does. Submitting
// always creates a NEW stack (smart-reuse means unchanged legs are reused, not re-run) and navigates
// to it. `initial` prefills every field from an existing stack for the rerun case.
export function StackConfigModal({ title = 'New portfolio stack', submitLabel = 'Run stack', initial, onClose }: {
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

  const pyStrategies = useMemo(
    () => (strategies ?? []).filter(s => s.runner === 'python'),
    [strategies],
  )

  const [selected, setSelected] = useState<Set<string>>(new Set(initial?.strategyIds ?? []))
  const [instrument, setInstrument] = useState(initial?.instrument ?? '')
  const [start, setStart] = useState(initial?.start ?? yearsAgo(1))
  const [end, setEnd] = useState(initial?.end ?? today())
  const [barValue, setBarValue] = useState(initial?.barValue ?? 15)
  // Stacks are python-only, so the runner is fixed.
  const { data: historyLimit } = useHistoryLimit(instrument || null, 'Minute', barValue, 'python')
  // 0/0 matches the Pine strategies (all pinned commission=0, slippage=0). The Python fill engine
  // applies real cost via the account profile (vantage_demo = 0), so these display values stay honest.
  const [commPerSide, setCommPerSide] = useState(initial?.commPerSide ?? 0)
  const [slippageTicks, setSlippageTicks] = useState(initial?.slippageTicks ?? 0)
  const [mode, setMode] = useState<StackMode>(initial?.mode ?? 'screen')
  const [accountSize, setAccountSize] = useState(initial?.accountSize ?? 10_000)
  const [riskCapPct, setRiskCapPct] = useState(initial?.riskCapPct ?? 10)
  const [entryFloorPct, setEntryFloorPct] = useState(initial?.entryFloorPct ?? 0)
  const shared = mode === 'shared'

  // Default the instrument to the first selected strategy's suggestion (New-stack case only).
  useEffect(() => {
    if (instrument) return
    const first = pyStrategies.find(s => selected.has(s.id))
    if (first?.suggested_instrument) setInstrument(first.suggested_instrument)
  }, [selected, pyStrategies, instrument])

  const toggle = (id: string) => setSelected(prev => {
    const next = new Set(prev)
    next.has(id) ? next.delete(id) : next.add(id)
    return next
  })

  const validPeriod = !!start && !!end && start < end
  // A cap of zero refuses every entry, so a "portfolio" under it takes no trades at all — the
  // backend refuses it and the button must not offer it either. Account size is guarded the same
  // way: a leg sizes off the balance, so zero produces zero-size positions.
  const accountValid = !shared || (riskCapPct > 0 && accountSize > 0)
  const settingsReady = selected.size >= 2 && !!instrument.trim() && validPeriod && accountValid

  const previewBody = useMemo(() => ({
    strategy_ids: Array.from(selected),
    instrument: instrument.trim(),
    bar_type: 'Minute',
    bar_value: barValue,
    start_date: start,
    end_date: end,
    commission_per_side: commPerSide,
    slippage_ticks: slippageTicks,
    mode,
  }), [selected, instrument, barValue, start, end, commPerSide, slippageTicks, mode])
  const { data: preview } = useStackPreview(previewBody, settingsReady)
  const actionByStrategy = useMemo(() => {
    const m = new Map<string, 'reuse' | 'run'>()
    preview?.legs.forEach(l => m.set(l.strategy_id, l.action))
    return m
  }, [preview])

  const canRun = settingsReady && !triggerStack.isPending &&
    (!pythonBusy || (preview != null && preview.run_count === 0))

  const submit = () => {
    if (!canRun) return
    triggerStack.mutate(
      {
        ...previewBody,
        strategy_ids: Array.from(selected),
        // Sent only in shared mode. On a screen the backend stores NULL for all three, because a
        // screen has no account — every leg traded its own — and a number here would be recorded
        // as a setting the run never had.
        ...(shared ? { account_size: accountSize, risk_cap_pct: riskCapPct,
                       entry_floor_pct: entryFloorPct } : {}),
      },
      { onSuccess: (res) => { onClose(); navigate(`/backtests/stacks/${res.stack_id}`) } },
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[520px] shadow-2xl flex flex-col max-h-[88vh]">
        <div className="px-5 py-4 border-b border-border-subtle flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-2">
            <Layers size={16} className="text-gold-text" />
            <div className="text-[15px] font-semibold">{title}</div>
          </div>
          <button onClick={onClose} className="text-text-tertiary hover:text-text-primary transition-colors"><X size={16} /></button>
        </div>

        <div className="px-5 py-4 overflow-y-auto space-y-5">
          <p className="text-[12px] text-text-secondary">
            Layer 2 or more Python strategies over one shared instrument and window to see combined
            P&L.
          </p>

          <div>
            <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">
              What this stack measures
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {MODES.map(m => (
                <button
                  key={m.key}
                  data-testid={`stack-mode-${m.key}`}
                  onClick={() => setMode(m.key)}
                  className={`px-3 py-2 rounded-lg text-[12px] font-medium border text-left transition-colors ${
                    mode === m.key
                      ? 'border-accent bg-accent/10 text-accent'
                      : 'border-border-subtle bg-bg-sunken text-text-secondary hover:border-border-default'
                  }`}
                >{m.label}</button>
              ))}
            </div>
            <p className="text-[11px] text-text-tertiary mt-1.5">
              {MODES.find(m => m.key === mode)!.blurb}
            </p>
          </div>

          {shared && (
            <div data-testid="stack-account-fields">
              <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">
                The shared account
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <div className="text-[11px] text-text-tertiary mb-1.5">Balance ($)</div>
                  <input
                    type="number" step="100" min="1" value={accountSize}
                    onChange={e => setAccountSize(Number(e.target.value))}
                    className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
                  />
                </div>
                <div>
                  <div className="text-[11px] text-text-tertiary mb-1.5">Risk cap (%)</div>
                  <input
                    type="number" step="0.5" min="0.5" value={riskCapPct}
                    onChange={e => setRiskCapPct(Number(e.target.value))}
                    className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
                  />
                </div>
                <div>
                  <div className="text-[11px] text-text-tertiary mb-1.5">Entry floor (%)</div>
                  <input
                    type="number" step="0.1" min="0" value={entryFloorPct}
                    onChange={e => setEntryFloorPct(Number(e.target.value))}
                    className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
                  />
                </div>
              </div>
              <p className="text-[11px] text-text-tertiary mt-1.5">
                The cap is the most OPEN risk all strategies may hold at once, as a % of the
                <strong className="text-text-secondary"> live </strong> balance — and an open trade
                only reserves risk down to its <strong className="text-text-secondary">current</strong> stop,
                so a stop moved to breakeven frees its room. An entry with no room is shrunk to fit,
                or skipped if what is left falls under the floor.
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
              Strategies <span className="text-text-tertiary normal-case font-normal">· pick at least 2</span>
            </div>
            {pyStrategies.length === 0 ? (
              <div className="text-[12px] text-text-tertiary py-3">No Python strategies found. Scan strategies first.</div>
            ) : (
              <div className="space-y-1.5">
                {pyStrategies.map(s => {
                  const on = selected.has(s.id)
                  const action = on ? actionByStrategy.get(s.id) : undefined
                  return (
                    <button
                      key={s.id}
                      onClick={() => toggle(s.id)}
                      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg border text-left transition-colors ${
                        on ? 'border-accent/40 bg-accent/5' : 'border-border-subtle bg-bg-sunken hover:border-border-default'
                      }`}
                    >
                      <span className={`w-4 h-4 rounded flex items-center justify-center flex-shrink-0 border ${on ? 'bg-accent border-accent' : 'border-border-default'}`}>
                        {on && <span className="text-bg-base text-[10px] font-bold">✓</span>}
                      </span>
                      <span className="flex-1 min-w-0">
                        <span className="text-[13px] font-medium text-text-primary">{s.name}</span>
                        {s.suggested_instrument && <span className="ml-2 text-[11px] text-text-tertiary font-mono">{s.suggested_instrument}</span>}
                      </span>
                      {action === 'reuse' && (
                        <span className="flex-shrink-0 text-[10px] font-semibold uppercase tracking-[0.4px] text-pos-text bg-pos-muted/40 border border-pos-text/20 rounded px-1.5 py-0.5" title="An existing completed run matches these exact settings — it will be reused, not re-run.">Reuse</span>
                      )}
                      {action === 'run' && (
                        <span className="flex-shrink-0 text-[10px] font-semibold uppercase tracking-[0.4px] text-warn-text bg-warn-muted/30 border border-warn-text/20 rounded px-1.5 py-0.5" title="No matching run exists — this leg will be backtested fresh at the chosen timeframe and costs.">Run</span>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
          </div>

          <div>
            <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">Instrument</div>
            <input
              value={instrument}
              onChange={e => setInstrument(e.target.value)}
              placeholder="e.g. XAUUSD"
              className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
            />
            <p className="text-[11px] text-text-tertiary mt-1.5">Every strategy in the stack runs on this one instrument, timeframe, and cost profile — so its P&amp;L matches the standalone run you designed.</p>
          </div>

          <div>
            <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">Timeframe</div>
            <div className="flex gap-1.5">
              {BAR_PRESETS.map(([v, label]) => (
                <button
                  key={v}
                  onClick={() => setBarValue(v)}
                  className={`px-3 py-1.5 rounded-md text-[12px] font-medium border transition-colors ${
                    barValue === v ? 'border-accent bg-accent/10 text-accent' : 'border-border-subtle bg-bg-sunken text-text-secondary hover:border-border-default'
                  }`}
                >{label}</button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">Commission / side</div>
              <input
                type="number" step="0.01" min="0" value={commPerSide}
                onChange={e => setCommPerSide(Number(e.target.value))}
                className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
              />
            </div>
            <div>
              <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">Slippage (ticks)</div>
              <input
                type="number" step="1" min="0" value={slippageTicks}
                onChange={e => setSlippageTicks(Number(e.target.value))}
                className="w-full bg-bg-sunken border border-border-subtle rounded-md px-3 py-2 text-[13px] font-mono focus:outline-none focus:border-accent transition-colors"
              />
            </div>
          </div>

          <div>
            <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.6px] mb-2">Period</div>
            <PeriodPicker start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e) }} limit={historyLimit} />
          </div>

          {settingsReady && shared && (
            <div className="text-[12px] text-text-secondary bg-bg-sunken border border-border-subtle rounded-lg px-3 py-2">
              <span className="text-warn-text font-semibold">{selected.size + 1} replays</span>
              {' '}— the strategies together, then each one <strong className="text-text-secondary">alone</strong> as
              the control. Without the solo run a difference is a mixture of <em>the cap bit</em> and
              <em> the shared balance re-sized everything</em>, and nothing afterwards separates them.
            </div>
          )}

          {settingsReady && !shared && preview && (
            <div className="text-[12px] text-text-secondary bg-bg-sunken border border-border-subtle rounded-lg px-3 py-2">
              {preview.reuse_count > 0 && (
                <span><span className="text-pos-text font-semibold">{preview.reuse_count}</span> reused from existing runs</span>
              )}
              {preview.reuse_count > 0 && preview.run_count > 0 && <span className="text-text-tertiary"> · </span>}
              {preview.run_count > 0 && (
                <span><span className="text-warn-text font-semibold">{preview.run_count}</span> to backtest now</span>
              )}
              {preview.run_count === 0 && <span className="text-text-tertiary"> · assembled instantly, no re-run</span>}
            </div>
          )}

          {pythonBusy && preview != null && preview.run_count > 0 && (
            <div className="flex items-center gap-2 text-[12px] text-warn-text bg-warn-muted/30 border border-warn-text/20 rounded-lg px-3 py-2">
              <Loader2 size={13} className="animate-spin" /> A Python job is already running — the legs that need a fresh run must wait.
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle flex-shrink-0">
          <button onClick={onClose} className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">Cancel</button>
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
