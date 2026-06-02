import { useParams, useNavigate } from 'react-router-dom'
import { Trash2, ArrowLeft, RefreshCw } from 'lucide-react'
import { useStressTest, useDeleteStressTest } from '@/hooks/useStressTests'
import { useRulesets } from '@/hooks/useLab'
import { StatCard } from '@/components/StatCard'
import MonteCarloFan from '@/components/MonteCarloFan'
import DrawdownDistribution from '@/components/DrawdownDistribution'
import WalkForwardChart from '@/components/WalkForwardChart'
import SensitivityRadar from '@/components/SensitivityRadar'
import RobustnessGradeBadge from '@/components/RobustnessGradeBadge'

function StatusPill({ status }: { status: string }) {
  const base = 'text-[11px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px]'
  if (status === 'complete')        return <span className={`${base} bg-pos-muted text-pos-text`}>Complete</span>
  if (status.startsWith('failed'))  return <span className={`${base} bg-neg-muted text-neg-text`}>Failed</span>
  return <span className={`${base} bg-warn-muted text-warn-text`}>Running…</span>
}

function ProbBar({ prob, label, variant }: { prob: number; label: string; variant: 'breach' | 'pass' }) {
  const pct = Math.round(prob * 100)
  const barCls = variant === 'breach'
    ? pct > 50 ? 'bg-neg' : pct > 10 ? 'bg-warn' : 'bg-pos'
    : pct > 50 ? 'bg-pos' : 'bg-warn'
  return (
    <div className="space-y-[5px]">
      <div className="flex justify-between text-[12px]">
        <span className="text-text-secondary">{label}</span>
        <span className="font-mono font-semibold text-text-primary">{pct}%</span>
      </div>
      <div className="h-[6px] bg-bg-sunken rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${barCls}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function fmt$(n: number | null | undefined): string {
  if (n == null) return '—'
  const sign = n < 0 ? '-' : ''
  return `${sign}$${Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export default function StressTestDetail() {
  const { stressTestId } = useParams<{ stressTestId: string }>()
  const navigate = useNavigate()
  const { data: st, isLoading } = useStressTest(stressTestId ?? null)
  const { data: rulesets } = useRulesets()
  const deleteTest = useDeleteStressTest()

  if (isLoading) return <div className="text-text-secondary text-[13px] pt-8">Loading…</div>
  if (!st) return <div className="text-text-secondary text-[13px] pt-8">Stress test not found</div>

  const ruleset = rulesets?.find(r => r.id === st.ruleset_id)
  const isRunning = !st.status.startsWith('failed') && st.status !== 'complete'

  return (
    <div className="space-y-8">

      {/* ── Back ──────────────────────────────────────────────────────────────── */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
      >
        <ArrowLeft size={14} /> Stress Tests
      </button>

      {/* ── Header ────────────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 flex-wrap mb-2">
            <h1 className="text-h1 font-semibold leading-tight">Stress Test</h1>
            <StatusPill status={st.status} />
            {st.grade && <RobustnessGradeBadge grade={st.grade} size="md" />}
            {isRunning && <RefreshCw size={14} className="text-accent animate-spin" />}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {st.strategy_name && (
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-secondary">
                {st.strategy_name}
              </span>
            )}
            {st.instrument && (
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono bg-accent/10 text-accent border border-accent/20">
                {st.instrument}
              </span>
            )}
            {ruleset && (
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-tertiary">
                vs {ruleset.name}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => {
            if (confirm('Delete this stress test?')) {
              deleteTest.mutate(st.stress_test_id, { onSuccess: () => navigate(-1) })
            }
          }}
          className="p-2 rounded text-text-tertiary hover:text-neg-text hover:bg-neg-muted transition-colors"
        >
          <Trash2 size={16} />
        </button>
      </div>

      {/* ── Grade reasons ─────────────────────────────────────────────────────── */}
      {st.grade_reasons && st.grade_reasons.length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-2">
          <p className="text-[12px] font-semibold uppercase tracking-[0.5px] text-text-tertiary">Grade Reasons</p>
          <ul className="space-y-1.5">
            {st.grade_reasons.map((r, i) => (
              <li key={i} className="text-[13px] text-text-secondary flex items-start gap-2">
                <span className="text-accent mt-[3px] flex-shrink-0">·</span>{r}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ── MC stats grid ─────────────────────────────────────────────────────── */}
      {st.status === 'complete' && st.median_final_pnl != null && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-[10px]">
          <StatCard
            label="Median PnL"
            value={fmt$(st.median_final_pnl)}
            subVariant={st.median_final_pnl >= 0 ? 'pos' : 'neg'}
          />
          <StatCard
            label="Worst 5% PnL"
            value={fmt$(st.pct5_final_pnl)}
            subVariant={st.pct5_final_pnl != null && st.pct5_final_pnl >= 0 ? 'pos' : 'neg'}
          />
          <StatCard
            label="Worst 5% Drawdown"
            value={fmt$(st.pct5_max_dd)}
            sub={ruleset ? `limit ${fmt$(ruleset.max_loss_eod)}` : undefined}
            subVariant={ruleset && st.pct5_max_dd != null && st.pct5_max_dd <= (ruleset.max_loss_eod ?? Infinity) ? 'pos' : 'neg'}
          />
          <StatCard
            label="Worst 1% Drawdown"
            value={fmt$(st.pct1_max_dd)}
            subVariant="neutral"
          />
        </div>
      )}

      {/* ── Probability bars ──────────────────────────────────────────────────── */}
      {st.prob_breach != null && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-4">
          <p className="text-[12px] font-semibold uppercase tracking-[0.5px] text-text-tertiary">Probability Metrics</p>
          <ProbBar prob={st.prob_breach}     label="Probability of breaching ruleset limit" variant="breach" />
          <ProbBar prob={st.prob_pass_eval ?? 0} label="Probability of passing eval"        variant="pass"   />
        </div>
      )}

      {/* ── Monte Carlo fan ───────────────────────────────────────────────────── */}
      {st.equity_paths && st.equity_paths.length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-3">
          <div className="flex items-baseline justify-between">
            <p className="text-[12px] font-semibold uppercase tracking-[0.5px] text-text-tertiary">Equity Path Fan</p>
            <span className="text-[11px] text-text-tertiary">100 simulations · p10/p25/p50/p75/p90</span>
          </div>
          <MonteCarloFan
            paths={st.equity_paths}
            ruleset={ruleset}
            tradeCount={st.equity_paths[0]?.length ?? 0}
          />
        </div>
      )}

      {/* ── Drawdown distribution ─────────────────────────────────────────────── */}
      {st.distribution && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-3">
          <div className="flex items-baseline justify-between">
            <p className="text-[12px] font-semibold uppercase tracking-[0.5px] text-text-tertiary">Max Drawdown Distribution</p>
            {ruleset && <span className="text-[11px] text-text-tertiary">Red = over limit</span>}
          </div>
          <DrawdownDistribution
            distribution={st.distribution.max_dd}
            maxLoss={ruleset?.max_loss_eod}
          />
        </div>
      )}

      {/* ── Walk-forward ──────────────────────────────────────────────────────── */}
      {st.walk_forward_summary && st.walk_forward_summary.length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-3">
          <div className="flex items-baseline justify-between">
            <p className="text-[12px] font-semibold uppercase tracking-[0.5px] text-text-tertiary">Walk-Forward Analysis</p>
            {st.walk_forward_degradation != null && (
              <span className="text-[11px] text-text-tertiary font-mono">
                IS→OOS degradation: {(st.walk_forward_degradation * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <WalkForwardChart windows={st.walk_forward_summary} />
        </div>
      )}

      {/* ── Sensitivity ───────────────────────────────────────────────────────── */}
      {st.sensitivity_summary && Object.keys(st.sensitivity_summary).length > 0 && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-3">
          <div className="flex items-baseline justify-between">
            <p className="text-[12px] font-semibold uppercase tracking-[0.5px] text-text-tertiary">Parameter Sensitivity</p>
            {st.sensitivity_max_degradation != null && (
              <span className="text-[11px] text-text-tertiary font-mono">
                Worst case: {(st.sensitivity_max_degradation * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <SensitivityRadar sensitivity={st.sensitivity_summary} />
        </div>
      )}

      {/* ── Error ─────────────────────────────────────────────────────────────── */}
      {st.error_message && (
        <div className="rounded-lg border border-neg-text/30 bg-neg-muted p-4">
          <p className="text-[13px] text-neg-text font-mono">{st.error_message}</p>
        </div>
      )}

    </div>
  )
}
