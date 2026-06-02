import { useParams, useNavigate } from 'react-router-dom'
import { Trash2, ArrowLeft, RefreshCw } from 'lucide-react'
import { useStressTest, useDeleteStressTest } from '@/hooks/useStressTests'
import { useRulesets } from '@/hooks/useLab'
import MonteCarloFan from '@/components/MonteCarloFan'
import DrawdownDistribution from '@/components/DrawdownDistribution'
import WalkForwardChart from '@/components/WalkForwardChart'
import SensitivityRadar from '@/components/SensitivityRadar'
import RobustnessGradeBadge from '@/components/RobustnessGradeBadge'

function StatusPill({ status }: { status: string }) {
  const base = 'text-xs font-medium px-2 py-0.5 rounded-full'
  if (status === 'complete') return <span className={`${base} bg-pos-muted text-pos-text`}>Complete</span>
  if (status.startsWith('failed')) return <span className={`${base} bg-neg-muted text-neg-text`}>Failed</span>
  return <span className={`${base} bg-warn-muted text-warn-text`}>Running…</span>
}

function ProbBar({ prob, label }: { prob: number; label: string }) {
  const pct = Math.round(prob * 100)
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-text-secondary">
        <span>{label}</span>
        <span className="font-mono text-text-primary">{pct}%</span>
      </div>
      <div className="h-2 bg-bg-sunken rounded-full overflow-hidden">
        <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export default function StressTestDetail() {
  const { stressTestId } = useParams<{ stressTestId: string }>()
  const navigate = useNavigate()
  const { data: st, isLoading } = useStressTest(stressTestId ?? null)
  const { data: rulesets } = useRulesets()
  const deleteTest = useDeleteStressTest()

  if (isLoading) return <div className="p-8 text-text-secondary">Loading…</div>
  if (!st) return <div className="p-8 text-text-secondary">Stress test not found</div>

  const ruleset = rulesets?.find(r => r.id === st.ruleset_id)
  const isRunning = !st.status.startsWith('failed') && st.status !== 'complete'

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <button onClick={() => navigate(-1)} className="flex items-center gap-1 text-xs text-text-tertiary hover:text-text-secondary mb-2">
            <ArrowLeft size={12} /> Back
          </button>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-text-primary">Stress Test</h1>
            <StatusPill status={st.status} />
            {st.grade && <RobustnessGradeBadge grade={st.grade} size="lg" />}
            {isRunning && <RefreshCw size={14} className="text-accent animate-spin" />}
          </div>
          <p className="text-sm text-text-secondary font-mono">{st.strategy_name} · {st.instrument}</p>
          {ruleset && <p className="text-xs text-text-tertiary">Evaluated against: {ruleset.name}</p>}
        </div>
        <button
          onClick={() => {
            if (confirm('Delete this stress test?')) {
              deleteTest.mutate(st.stress_test_id, { onSuccess: () => navigate(-1) })
            }
          }}
          className="p-2 rounded text-text-tertiary hover:text-neg-text hover:bg-neg-muted"
        >
          <Trash2 size={16} />
        </button>
      </div>

      {/* Grade reasons */}
      {st.grade_reasons && st.grade_reasons.length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-2">
          <p className="text-sm font-semibold text-text-primary">Grade Reasons</p>
          <ul className="space-y-1">
            {st.grade_reasons.map((r, i) => (
              <li key={i} className="text-sm text-text-secondary flex items-start gap-2">
                <span className="text-accent mt-0.5">·</span>{r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* MC stats */}
      {st.status === 'complete' && st.median_final_pnl != null && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Median PnL',     value: `$${st.median_final_pnl?.toFixed(0)}` },
            { label: 'Worst 5% PnL',   value: `$${st.pct5_final_pnl?.toFixed(0)}` },
            { label: 'Worst 5% DD',    value: `$${st.pct5_max_dd?.toFixed(0)}` },
            { label: 'Worst 1% DD',    value: `$${st.pct1_max_dd?.toFixed(0)}` },
          ].map(({ label, value }) => (
            <div key={label} className="rounded-lg border border-border-subtle bg-bg-surface p-3">
              <p className="text-xs text-text-tertiary">{label}</p>
              <p className="text-lg font-mono font-semibold text-text-primary">{value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Probability bars */}
      {st.prob_breach != null && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-3">
          <p className="text-sm font-semibold text-text-primary">Probability Metrics</p>
          <ProbBar prob={st.prob_breach} label="Probability of breaching ruleset limit" />
          <ProbBar prob={st.prob_pass_eval ?? 0} label="Probability of passing eval" />
        </div>
      )}

      {/* Monte Carlo fan */}
      {st.equity_paths && st.equity_paths.length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-2">
          <p className="text-sm font-semibold text-text-primary">Equity Path Fan (100 simulations)</p>
          <MonteCarloFan
            paths={st.equity_paths}
            ruleset={ruleset}
            tradeCount={st.equity_paths[0]?.length ?? 0}
          />
        </div>
      )}

      {/* Drawdown distribution */}
      {st.distribution && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-2">
          <p className="text-sm font-semibold text-text-primary">Max Drawdown Distribution</p>
          <DrawdownDistribution
            distribution={st.distribution.max_dd}
            maxLoss={ruleset?.max_loss_eod}
          />
        </div>
      )}

      {/* Walk-forward */}
      {st.walk_forward_summary && st.walk_forward_summary.length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-text-primary">Walk-Forward Analysis</p>
            {st.walk_forward_degradation != null && (
              <span className="text-xs text-text-secondary font-mono">
                IS→OOS degradation: {(st.walk_forward_degradation * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <WalkForwardChart windows={st.walk_forward_summary} />
        </div>
      )}

      {/* Sensitivity */}
      {st.sensitivity_summary && Object.keys(st.sensitivity_summary).length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-text-primary">Parameter Sensitivity</p>
            {st.sensitivity_max_degradation != null && (
              <span className="text-xs text-text-secondary font-mono">
                Worst case: {(st.sensitivity_max_degradation * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <SensitivityRadar sensitivity={st.sensitivity_summary} />
        </div>
      )}

      {/* Error */}
      {st.error_message && (
        <div className="rounded-lg border border-neg-text/30 bg-neg-muted p-4">
          <p className="text-sm text-neg-text font-mono">{st.error_message}</p>
        </div>
      )}
    </div>
  )
}
