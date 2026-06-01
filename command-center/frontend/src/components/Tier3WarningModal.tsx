import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Layers } from 'lucide-react'
import { WorthinessBadge } from '@/components/WorthinessBadge'
import { useInstrumentSummary, useTriggerSweep } from '@/hooks/useLab'
import type { BacktestDetail, SweepRequest } from '@/types'

interface Props {
  run: BacktestDetail
  onClose: () => void
  onOptimizeAnyway: () => void
}

function withContractMonth(instruments: string[], sourceInstrument: string): string[] {
  const parts = sourceInstrument.trim().split(/\s+/)
  if (parts.length < 2) return instruments
  const contract = parts.slice(1).join(' ')
  return instruments.map(inst => inst.trim().includes(' ') ? inst : `${inst} ${contract}`)
}

export function Tier3WarningModal({ run, onClose, onOptimizeAnyway }: Props) {
  const navigate  = useNavigate()
  const firmIds   = run.evaluations.map(e => e.firm_id)
  const primaryFirmId = firmIds[0] ?? undefined

  const { data: summary, isLoading } = useInstrumentSummary(
    run.strategy_id,
    primaryFirmId,
    run.start_date,
    run.end_date,
  )

  const triggerSweep = useTriggerSweep()

  const handleSweepUntested = () => {
    if (!summary?.untested_instruments.length) return
    const req: SweepRequest = {
      strategy_id:        run.strategy_id,
      params:             run.params,
      bar_type:           run.bar_type,
      bar_value:          run.bar_value,
      start_date:         run.start_date,
      end_date:           run.end_date,
      commission_per_side: run.commission_per_side,
      slippage_ticks:     run.slippage_ticks,
      firm_ids:           firmIds,
      instruments:        withContractMonth(summary.untested_instruments, run.instrument),
      source_run_id:      run.run_id,
    }
    triggerSweep.mutate(req, {
      onSuccess: (data) => {
        onClose()
        navigate(`/backtests/sweeps/${data.sweep_id}`)
      },
    })
  }

  const handleRunSweepAll = () => {
    if (!summary) return
    const allInstruments = [
      ...summary.instrument_results.map(r => r.instrument),
      ...summary.untested_instruments,
    ]
    const req: SweepRequest = {
      strategy_id:        run.strategy_id,
      params:             run.params,
      bar_type:           run.bar_type,
      bar_value:          run.bar_value,
      start_date:         run.start_date,
      end_date:           run.end_date,
      commission_per_side: run.commission_per_side,
      slippage_ticks:     run.slippage_ticks,
      firm_ids:           firmIds,
      instruments:        withContractMonth(allInstruments, run.instrument),
      source_run_id:      run.run_id,
    }
    triggerSweep.mutate(req, {
      onSuccess: (data) => {
        onClose()
        navigate(`/backtests/sweeps/${data.sweep_id}`)
      },
    })
  }

  const reason = run.worthiness?.reason?.replace(/_/g, ' ') ?? 'failed quality thresholds'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[560px] shadow-2xl">
        {/* Header */}
        <div className="px-5 py-4 border-b border-border-subtle flex items-center gap-2">
          <AlertTriangle size={16} className="text-warn-text" />
          <div className="text-[15px] font-semibold">Optimize Tier 3 Strategy</div>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          <p className="text-[13px] text-text-secondary">
            This strategy scored{' '}
            <WorthinessBadge worthiness={run.worthiness} />{' '}
            on <span className="font-mono text-text-primary">{run.instrument}</span>.{' '}
            Reason: <span className="text-warn-text">{reason}</span>.
          </p>
          <p className="text-[13px] text-text-secondary">
            Optimizing a Tier 3 strategy rarely changes the outcome. Before optimizing,
            consider testing other instruments.
          </p>

          {/* Instrument results table */}
          {isLoading ? (
            <div className="h-24 bg-bg-hover animate-pulse rounded-md" />
          ) : summary && (summary.instrument_results.length > 0 || summary.untested_instruments.length > 0) ? (
            <div className="border border-border-subtle rounded-lg overflow-hidden">
              <div className="px-3 py-2 bg-bg-sunken border-b border-border-subtle text-[11px] font-semibold text-text-tertiary uppercase tracking-wide">
                Past results across instruments
              </div>
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-border-subtle">
                    <th className="text-left px-3 py-2 text-text-tertiary font-medium">Instrument</th>
                    <th className="text-left px-3 py-2 text-text-tertiary font-medium">Worthiness</th>
                    <th className="text-left px-3 py-2 text-text-tertiary font-medium">Tested</th>
                    <th className="px-3 py-2 w-20" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {summary.instrument_results.map(r => (
                    <tr key={r.instrument} className="hover:bg-bg-hover">
                      <td className="px-3 py-2 font-mono">
                        {r.instrument}
                        {r.instrument.split(' ')[0] === run.instrument.split(' ')[0] && (
                          <span className="ml-1 text-text-tertiary text-[10px]">(this)</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <WorthinessBadge worthiness={r.best_worthiness ? { tier: r.best_worthiness as 'TIER_1_STRESS_TEST' | 'TIER_2_OPTIMIZE' | 'TIER_3_DISCARD', reason: null, computed_against_firm: null } : null} />
                      </td>
                      <td className="px-3 py-2 text-text-tertiary">
                        {r.tested_at ? new Date(r.tested_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—'}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {r.best_run_id && (
                          <button
                            onClick={() => { onClose(); navigate(`/backtests/runs/${r.best_run_id}`) }}
                            className="px-2 py-[2px] rounded text-[11px] bg-accent/10 text-accent border border-accent/20 hover:bg-accent/20"
                          >
                            View →
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {summary.untested_instruments.map(inst => (
                    <tr key={inst} className="hover:bg-bg-hover">
                      <td className="px-3 py-2 font-mono">{inst}</td>
                      <td className="px-3 py-2 text-text-tertiary text-[11px]">not tested</td>
                      <td className="px-3 py-2" />
                      <td className="px-3 py-2" />
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Sweep untested button */}
              {summary.untested_instruments.length > 0 && (
                <div className="px-3 py-3 border-t border-border-subtle">
                  <button
                    onClick={handleSweepUntested}
                    disabled={triggerSweep.isPending}
                    className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-md text-[12px] font-medium bg-accent/10 text-accent border border-accent/20 hover:bg-accent/20 disabled:opacity-50 transition-colors"
                  >
                    <Layers size={13} />
                    Run on {summary.untested_instruments.length} untested instrument{summary.untested_instruments.length !== 1 ? 's' : ''}
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-bg-sunken border border-border-subtle rounded-lg px-4 py-3 text-[13px] text-text-secondary">
              This strategy has only been tested on {run.instrument}. Consider running it on
              other instruments before optimizing.
              <button
                onClick={handleRunSweepAll}
                disabled={triggerSweep.isPending}
                className="mt-2 flex items-center gap-2 px-3 py-2 rounded-md text-[12px] font-medium bg-accent/10 text-accent border border-accent/20 hover:bg-accent/20 disabled:opacity-50"
              >
                <Layers size={13} />
                Run sweep on all instruments
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-border-subtle">
          <p className="text-[12px] text-text-tertiary mb-3">
            Still want to optimize on {run.instrument}?
          </p>
          <div className="flex items-center justify-end gap-3">
            <button
              onClick={onClose}
              className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={onOptimizeAnyway}
              className="px-4 py-[7px] rounded-md text-[13px] font-medium bg-warn-muted text-warn-text border border-warn-text/30 hover:bg-warn-text/15 transition-colors"
            >
              Optimize {run.instrument} anyway
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
