import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Trash2, ArrowLeft, RefreshCw, Info, Check, Shuffle, CalendarRange, Sliders } from 'lucide-react'
import { useStressTest, useDeleteStressTest } from '@/hooks/useStressTests'
import { useRulesets, useBacktestRun } from '@/hooks/useLab'
import MonteCarloFan from '@/components/MonteCarloFan'
import DrawdownDistribution from '@/components/DrawdownDistribution'
import WalkForwardChart from '@/components/WalkForwardChart'
import SensitivityRadar from '@/components/SensitivityRadar'


// ── InfoTip ───────────────────────────────────────────────────────────────────

function InfoTip({ text }: { text: string }) {
  return (
    <span className="relative group/tip inline-flex items-center ml-[5px] cursor-help flex-shrink-0">
      <Info size={9} className="text-text-tertiary/50 group-hover/tip:text-accent transition-colors" />
      <span className="absolute bottom-[calc(100%+8px)] left-0 z-50 hidden group-hover/tip:block w-52 rounded-lg bg-bg-base border border-border-default px-3 py-2.5 text-[11px] text-text-secondary shadow-2xl pointer-events-none leading-relaxed normal-case tracking-normal font-normal">
        {text}
      </span>
    </span>
  )
}

// ── MetricCard ────────────────────────────────────────────────────────────────

function MetricCard({ label, value, valueCls = '', sub, subCls = 'text-text-tertiary', tooltip }: {
  label: string
  value: React.ReactNode
  valueCls?: string
  sub?: React.ReactNode
  subCls?: string
  tooltip?: string
}) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg px-[15px] py-[14px] h-full flex flex-col justify-center">
      <div className="flex items-center text-[10px] text-text-secondary uppercase tracking-[0.6px]">
        {label}
        {tooltip && <InfoTip text={tooltip} />}
      </div>
      <div className={`text-[24px] font-semibold mt-[6px] tracking-[-0.5px] font-mono ${valueCls}`}>{value}</div>
      {sub && <div className={`text-[11px] mt-[3px] leading-snug ${subCls}`}>{sub}</div>}
    </div>
  )
}

// ── ProbBar ───────────────────────────────────────────────────────────────────

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

// ── SectionHeader ─────────────────────────────────────────────────────────────

function SectionHeader({ label, right, tooltip }: { label: string; right?: React.ReactNode; tooltip?: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <div className="flex items-center">
        <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px]">{label}</p>
        {tooltip && <InfoTip text={tooltip} />}
      </div>
      {right && <span className="text-[11px] text-text-tertiary">{right}</span>}
    </div>
  )
}

// ── AnalysisSection ───────────────────────────────────────────────────────────
// Groups the page into its three distinct analyses so a reader knows that the Monte
// Carlo block (stats + probabilities + fan + drawdown) is ONE simulation viewed four
// ways, while Walk-Forward and Sensitivity are separate tests. Each carries a one-line
// "what this answers" so the trader doesn't have to infer it.

function AnalysisSection({ icon, title, desc, children }: {
  icon: React.ReactNode
  title: string
  desc: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-start gap-[10px]">
        <span className="flex-shrink-0 mt-[2px] text-accent">{icon}</span>
        <div className="min-w-0">
          <h2 className="text-[14px] font-semibold text-text-primary leading-tight">{title}</h2>
          <p className="text-[12px] text-text-tertiary mt-[2px] leading-snug">{desc}</p>
        </div>
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  )
}

// ── Header-metric verdicts ──────────────────────────────────────────────────────
// Turn a raw degradation ratio into "{n}% · word" coloured by the grading thresholds,
// so the trader sees good-vs-bad at a glance instead of an unanchored number.

function gradedRight(value: number | null | undefined, solidBelow: number, okBelow: number, prefix: string, naText: string) {
  if (value == null) return <span className="text-text-tertiary">{naText}</span>
  const pct = (value * 100).toFixed(0)
  const [word, cls] = value < solidBelow ? ['robust', 'text-pos-text']
    : value < okBelow ? ['acceptable', 'text-warn-text']
    : ['fragile', 'text-neg-text']
  return <span className={cls}>{prefix}{pct}% · {word}</span>
}

// ── Formatters ────────────────────────────────────────────────────────────────

function fmt$(n: number | null | undefined): string {
  if (n == null) return '—'
  const sign = n < 0 ? '-' : ''
  return `${sign}$${Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function StressTestDetail() {
  const { stressTestId } = useParams<{ stressTestId: string }>()
  const navigate = useNavigate()
  const { data: st, isLoading } = useStressTest(stressTestId ?? null)
  const { data: rulesets } = useRulesets()
  const { data: run } = useBacktestRun(st?.run_id ?? null)
  const deleteTest = useDeleteStressTest()

  const isRunning = st ? !st.status.startsWith('failed') && st.status !== 'complete' : false
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [nowSec, setNowSec] = useState(() => Math.floor(Date.now() / 1000))
  useEffect(() => {
    if (!isRunning) return
    const id = setInterval(() => setNowSec(Math.floor(Date.now() / 1000)), 1000)
    return () => clearInterval(id)
  }, [isRunning])

  if (isLoading) return <div className="text-text-secondary text-[13px] pt-8">Loading…</div>
  if (!st) return <div className="text-text-secondary text-[13px] pt-8">Stress test not found</div>

  const ruleset = rulesets?.find(r => r.id === st.ruleset_id)

  const hasWF   = st.walk_forward_summary != null || st.status === 'running_wf'
  const hasSens = hasWF || st.sensitivity_summary  != null || st.status === 'running_sens'
  function fmtDuration(startSec: number | null, endSec: number | null): string | null {
    if (!startSec) return null
    const secs = (endSec ?? nowSec) - startSec
    if (secs < 60) return `${secs}s`
    return `${Math.floor(secs / 60)}m ${secs % 60}s`
  }
  const totalElapsed = fmtDuration(st.created_at, st.completed_at)

  // done fallbacks: use status when phase timestamps aren't available (pre-migration tests)
  const mcDone   = st.mc_completed_at != null || st.status !== 'running'
  const wfDone   = st.wf_completed_at != null || st.walk_forward_summary != null
  const sensDone = st.sensitivity_summary != null

  type PipelineStep = { key: string; label: string; sub: string; timer: string | null; done: boolean; active: boolean }
  const pipelineSteps: PipelineStep[] = [
    {
      key: 'mc',
      label: 'Monte Carlo',
      sub: '10k simulations',
      timer: fmtDuration(st.created_at, st.mc_completed_at),
      done: mcDone,
      active: st.status === 'running',
    },
    ...(hasWF ? [{
      key: 'wf',
      label: 'Walk-forward',
      sub: 'In-sample vs out-of-sample',
      timer: fmtDuration(st.mc_completed_at, st.wf_completed_at),
      done: wfDone,
      active: st.status === 'running_wf',
    }] : []),
    ...(hasSens ? [{
      key: 'sens',
      label: 'Sensitivity',
      sub: 'Parameter stability',
      timer: fmtDuration(st.wf_completed_at ?? st.mc_completed_at, st.status === 'complete' ? st.completed_at : null),
      done: sensDone,
      active: st.status === 'running_sens',
    }] : []),
    {
      key: 'grade',
      label: 'Grade',
      sub: 'A – F',
      timer: null,
      done: st.grade != null,
      active: false,
    },
  ]

  const gradeCls = st.grade === 'A' || st.grade === 'B' ? 'text-pos-text bg-pos-muted'
    : st.grade === 'C' ? 'text-warn-text bg-warn-muted'
    : 'text-neg-text bg-neg-muted'

  const medianCls  = st.median_final_pnl == null ? '' : st.median_final_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'
  const pct5Cls    = st.pct5_final_pnl   == null ? '' : st.pct5_final_pnl   >= 0 ? 'text-pos-text' : 'text-neg-text'

  // The dollar drawdown limit the charts and cards compare against. Mirrors the backend's
  // effective_dd_limit_usd: personal/demo translate their %-from-peak rule to dollars, prop
  // uses max_loss_eod. Critically, personal rows carry max_loss_eod = 0 (sentinel), so passing
  // it raw would draw a "$0 limit" and mark every bar over-limit.
  const isPersonal = ruleset?.ruleset_type === 'personal' || ruleset?.ruleset_type === 'demo'
  const ddLimit: number | null = !ruleset ? null
    : isPersonal
      ? (ruleset.max_drawdown_from_peak_pct && ruleset.account_size
          ? ruleset.account_size * ruleset.max_drawdown_from_peak_pct / 100 : null)
      : (ruleset.max_loss_eod || null)
  const ddOverLimit  = ddLimit != null && st.pct5_max_dd != null && st.pct5_max_dd > ddLimit
  const dd1OverLimit = ddLimit != null && st.pct1_max_dd != null && st.pct1_max_dd > ddLimit
  const passLabel = isPersonal ? 'Probability of staying under drawdown limit' : 'Probability of passing eval'

  function fmtDate(iso: string) {
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
  }
  function dollar(n: number | null | undefined) {
    if (n == null) return '—'
    const sign = n >= 0 ? '+' : '-'
    return `${sign}$${Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
  }
  const pnlCls = run?.net_pnl != null && run.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'

  return (
    <>
    <div className="space-y-8">

      {/* ── Back ──────────────────────────────────────────────────────────────── */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
      >
        <ArrowLeft size={14} /> Stress Tests
      </button>

      {/* ── Grade column card — header + reasons ──────────────────────────────── */}
      <div className="rounded-lg border border-border-subtle bg-bg-surface overflow-hidden">
        <div className="flex">
          {st.grade && (
            <div className={`flex-shrink-0 w-16 flex items-center justify-center ${gradeCls}`}>
              <span className="text-[36px] font-black leading-none">{st.grade}</span>
            </div>
          )}
          <div className="flex-1 min-w-0 px-4 py-3 space-y-2">
            <div className="flex items-start justify-between gap-3">
              <h1 className="text-h1 font-semibold leading-tight">{st.strategy_name || 'Stress Test'}</h1>
              <button
                onClick={() => setConfirmDelete(true)}
                className="p-2 rounded text-text-tertiary hover:text-neg-text hover:bg-neg-muted transition-colors flex-shrink-0"
              >
                <Trash2 size={16} />
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5 items-center">
              {ruleset && (
                <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold bg-gold-muted text-gold-text">
                  {ruleset.name}
                </span>
              )}
              {isRunning && <RefreshCw size={13} className="text-accent animate-spin" />}
            </div>
            {st.grade_reasons && st.grade_reasons.length > 0 && (
              <ul className="space-y-1.5 pt-1">
                {st.grade_reasons.map((r, i) => (
                  <li key={i} className="text-[13px] text-text-secondary flex items-start gap-2">
                    <span className="text-text-tertiary mt-[3px] flex-shrink-0">·</span>{r}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {/* ── Pipeline progress (running only) ──────────────────────────────────── */}
      {isRunning && (
        <div className="rounded-lg border border-accent/20 bg-accent/5 px-5 py-4 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-[0.6px] text-text-secondary">Running</span>
            <span className="text-[11px] font-mono text-text-tertiary">Total elapsed: <span className="text-accent">{totalElapsed}</span></span>
          </div>
          <div className="flex items-start">
            {pipelineSteps.map((step, i) => (
              <>
                {i > 0 && (
                  <div key={`line-${step.key}`}
                    className={`flex-1 h-px mt-3 mx-2 ${pipelineSteps[i - 1].done ? 'bg-accent/40' : 'bg-border-subtle'}`}
                  />
                )}
                <div key={step.key} className="flex flex-col items-center gap-[6px] w-[88px] flex-shrink-0">
                  <div className={`w-6 h-6 rounded-full border flex items-center justify-center ${
                    step.active ? 'border-accent bg-accent/10' :
                    step.done   ? 'border-pos bg-pos-muted'    :
                                  'border-border-default bg-bg-surface'
                  }`}>
                    {step.done
                      ? <Check size={11} className="text-pos-text" />
                      : step.active
                        ? <span className="w-[7px] h-[7px] rounded-full bg-accent animate-pulse" />
                        : <span className="w-[6px] h-[6px] rounded-full bg-border-default" />
                    }
                  </div>
                  <div className="text-center">
                    <div className={`text-[11px] font-semibold leading-none ${step.active ? 'text-accent' : step.done ? 'text-text-primary' : 'text-text-tertiary'}`}>
                      {step.label}
                    </div>
                    <div className="text-[10px] text-text-tertiary mt-[3px] leading-none">{step.sub}</div>
                    {step.timer && (
                      <div className={`text-[10px] font-mono mt-[4px] leading-none ${step.active ? 'text-accent/70' : 'text-text-tertiary'}`}>
                        {step.active ? '⏱ ' : ''}{step.timer}
                      </div>
                    )}
                  </div>
                </div>
              </>
            ))}
          </div>
        </div>
      )}

      {/* ── Source backtest card ───────────────────────────────────────────────── */}
      {run && (
        <div className="rounded-lg border border-border-subtle bg-bg-surface px-4 py-3">
          <div className="flex items-stretch gap-6">
            <div className="flex-1 min-w-0 space-y-2">
              <div className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-tertiary">Source Backtest</div>
              <div className="text-[17px] font-semibold text-text-primary truncate">{run.strategy_name}</div>
              <div className="flex flex-wrap gap-1.5">
                <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono bg-accent/10 text-accent border border-accent/20">
                  {run.instrument}
                </span>
                <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium font-mono bg-bg-surface border border-border-subtle text-text-secondary">
                  {fmtDate(run.start_date)} → {fmtDate(run.end_date)}
                </span>
              </div>
            </div>
            <div className="border-l border-border-subtle pl-6 flex flex-col justify-between items-end flex-shrink-0">
              <div className="flex gap-5">
                <div className="text-right">
                  <div className={`text-[18px] font-semibold font-mono ${pnlCls}`}>{dollar(run.net_pnl)}</div>
                  <div className="text-[10px] text-text-tertiary uppercase tracking-[0.5px]">Net P&L</div>
                </div>
                <div className="text-right">
                  <div className="text-[18px] font-semibold font-mono text-text-primary">{run.trade_count ?? '—'}</div>
                  <div className="text-[10px] text-text-tertiary uppercase tracking-[0.5px]">Trades</div>
                </div>
              </div>
              <button
                onClick={() => navigate(`/backtests/runs/${st.run_id}`)}
                className="flex items-center gap-1.5 px-3 py-[6px] rounded text-[12px] font-medium bg-bg-sunken border border-border-subtle text-text-secondary hover:text-text-primary hover:border-border-default transition-colors"
              >
                View Run <ArrowLeft size={12} className="rotate-180" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ══ Monte Carlo ═══════════════════════════════════════════════════════════ */}
      {(st.prob_breach != null || (st.status === 'complete' && st.median_final_pnl != null) || (st.equity_paths?.length ?? 0) > 0 || st.distribution) && (
        <AnalysisSection
          icon={<Shuffle size={16} />}
          title="Monte Carlo"
          desc="Replays your trades 10,000 times in different orders to map the range of outcomes and how often you'd breach the limit. The stats, probabilities, and both charts below are all this one simulation."
        >
          {/* Stats grid */}
          {st.status === 'complete' && st.median_final_pnl != null && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-[10px]">
              <MetricCard
                label="Median PnL"
                value={fmt$(st.median_final_pnl)}
                valueCls={medianCls}
                tooltip="The middle outcome across all 10,000 simulations — half ended better, half worse. Positive = strategy is profitable in a typical scenario."
              />
              <MetricCard
                label="Worst 5% PnL"
                value={fmt$(st.pct5_final_pnl)}
                valueCls={pct5Cls}
                tooltip="The 5th percentile final P&L — only 5% of simulations did worse than this. Shows the tail risk of a bad but realistic trade sequence."
              />
              <MetricCard
                label="Worst 5% Drawdown"
                value={fmt$(st.pct5_max_dd)}
                sub={ddLimit != null ? `limit ${fmt$(ddLimit)}` : undefined}
                subCls={ddOverLimit ? 'text-neg-text' : 'text-pos-text'}
                tooltip="The 5th-percentile maximum drawdown — only 5% of simulations hit a larger drawdown than this. Compare to the ruleset's drawdown limit; if this exceeds it, you'd breach in bad-luck scenarios."
              />
              <MetricCard
                label="Worst 1% Drawdown"
                value={fmt$(st.pct1_max_dd)}
                sub={ddLimit != null ? `limit ${fmt$(ddLimit)}` : undefined}
                subCls={dd1OverLimit ? 'text-neg-text' : 'text-pos-text'}
                tooltip="The 1st-percentile maximum drawdown — the extreme tail. Only 1% of simulations were worse. Useful for stress-testing black-swan sequences."
              />
            </div>
          )}

          {/* Probability bars — the fastest read on the page */}
          {st.prob_breach != null && (
            <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-4">
              <SectionHeader
                label="Probability Metrics"
                tooltip="Across all 10,000 simulations: how often the strategy breaches the drawdown limit, and how often it passes (prop: hits the target without breaching; personal: simply never breaches)."
              />
              <ProbBar prob={st.prob_breach}        label="Probability of breaching ruleset limit" variant="breach" />
              <ProbBar prob={st.prob_pass_eval ?? 0} label={passLabel}                              variant="pass"   />
            </div>
          )}

          {/* Equity path fan */}
          {st.equity_paths && st.equity_paths.length > 0 && (
            <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-3">
              <SectionHeader
                label="Equity Path Fan"
                right="100 simulations · p10–p90"
                tooltip="100 of the simulated runs drawn as cumulative-P&L curves (starting at $0). Green = luckier orderings, cyan = median, red = unluckier. Dashed lines mark the drawdown limit and profit target. Want the bands trending up and staying above the limit line."
              />
              <MonteCarloFan
                paths={st.equity_paths}
                ruleset={{ max_loss_eod: ddLimit ?? undefined, profit_target: ruleset?.profit_target }}
                tradeCount={st.equity_paths[0]?.length ?? 0}
              />
            </div>
          )}

          {/* Drawdown distribution */}
          {st.distribution && (
            <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-3">
              <SectionHeader
                label="Max Drawdown Distribution"
                right={ddLimit != null ? 'Red = over limit' : undefined}
                tooltip="How many of the 10,000 simulations ended with each size of worst drawdown. Bars further right = deeper drawdowns. Red bars exceeded the limit — you want the pile sitting LEFT of the limit line."
              />
              <DrawdownDistribution
                distribution={st.distribution.max_dd}
                maxLoss={ddLimit}
              />
            </div>
          )}
        </AnalysisSection>
      )}

      {/* ══ Walk-Forward ══════════════════════════════════════════════════════════ */}
      {st.walk_forward_summary && st.walk_forward_summary.length > 0 && (
        <AnalysisSection
          icon={<CalendarRange size={16} />}
          title="Walk-Forward"
          desc="Splits the period into windows and tests each on data the strategy wasn't tuned on. Out-of-sample Sharpe near in-sample = holds up. A big drop = overfit to history."
        >
          <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-3">
            <SectionHeader
              label="In-Sample vs Out-of-Sample Sharpe"
              right={gradedRight(st.walk_forward_degradation, 0.20, 0.30, 'degradation ', 'n/a · IS Sharpe ≤ 0')}
              tooltip="Each window is trained on its first 70% (In-Sample) and tested on the unseen last 30% (Out-of-Sample). Similar bars = robust; out-of-sample collapsing = overfit. Only meaningful when in-sample Sharpe is positive."
            />
            <WalkForwardChart windows={st.walk_forward_summary} />
          </div>
        </AnalysisSection>
      )}

      {/* ══ Sensitivity ═══════════════════════════════════════════════════════════ */}
      {st.sensitivity_summary && Object.keys(st.sensitivity_summary).length > 0 && (
        <AnalysisSection
          icon={<Sliders size={16} />}
          title="Parameter Sensitivity"
          desc="Nudges each strategy parameter and re-runs to see how fragile the result is. Small bars = sturdy across settings; large bars = the edge depends on one exact value."
        >
          <div className="rounded-lg border border-border-subtle bg-bg-surface p-4 space-y-3">
            <SectionHeader
              label="Performance change per parameter"
              right={gradedRight(st.sensitivity_max_degradation, 0.25, 0.40, 'worst case ', 'n/a')}
              tooltip="Each parameter is shifted and the strategy re-run; the bar shows how much performance moved versus baseline (negative/red = worse). Bars near zero = robust. Grid-sourced tests show one direction per parameter."
            />
            <SensitivityRadar sensitivity={st.sensitivity_summary} />
          </div>
        </AnalysisSection>
      )}

      {/* ── Error ─────────────────────────────────────────────────────────────── */}
      {st.error_message && (
        <div className="rounded-lg border border-neg-text/30 bg-neg-muted p-4">
          <p className="text-[13px] text-neg-text font-mono">{st.error_message}</p>
        </div>
      )}

    </div>

    {confirmDelete && (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setConfirmDelete(false)}>
        <div className="bg-bg-surface border border-border-default rounded-xl p-6 w-full max-w-sm space-y-4" onClick={e => e.stopPropagation()}>
          <h2 className="text-base font-semibold text-text-primary">Delete stress test?</h2>
          <p className="text-sm text-text-secondary">
            This will permanently remove the stress test and all its child runs for <span className="text-text-primary font-medium">{st.strategy_name}</span>. This cannot be undone.
          </p>
          <div className="flex gap-2 pt-1">
            <button
              onClick={() => deleteTest.mutate(st.stress_test_id, { onSuccess: () => navigate(-1) })}
              disabled={deleteTest.isPending}
              className="flex-1 py-1.5 text-sm bg-neg-text text-white rounded font-medium hover:opacity-90 disabled:opacity-50"
            >
              {deleteTest.isPending ? 'Deleting…' : 'Delete'}
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="px-4 py-1.5 text-sm text-text-secondary border border-border-subtle rounded hover:bg-bg-hover"
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    )}
    </>
  )
}
