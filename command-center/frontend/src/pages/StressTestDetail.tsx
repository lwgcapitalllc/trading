import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Trash2, ArrowLeft, RefreshCw, Info, Check } from 'lucide-react'
import { useStressTest, useDeleteStressTest } from '@/hooks/useStressTests'
import { useRulesets, useBacktestRun } from '@/hooks/useLab'
import MonteCarloFan from '@/components/MonteCarloFan'
import DrawdownDistribution from '@/components/DrawdownDistribution'
import WalkForwardChart from '@/components/WalkForwardChart'
import SensitivityRadar from '@/components/SensitivityRadar'
import { ChartTabPanel, ChartModal } from '@/components/ChartTabPanel'
import StickyHeader from '@/components/StickyHeader'


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

function MetricCard({ label, value, valueCls = '', sub, subCls = 'text-text-tertiary', tooltip, small = false }: {
  label: string
  value: React.ReactNode
  valueCls?: string
  sub?: React.ReactNode
  subCls?: string
  tooltip?: string
  small?: boolean
}) {
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg px-[15px] py-[14px] h-full flex flex-col justify-center">
      <div className="flex items-center text-[10px] text-text-secondary uppercase tracking-[0.6px]">
        {label}
        {tooltip && <InfoTip text={tooltip} />}
      </div>
      <div className={`${small ? 'text-[17px]' : 'text-[24px]'} font-semibold mt-[6px] tracking-[-0.5px] font-mono ${valueCls}`}>{value}</div>
      {sub && <div className={`text-[11px] mt-[3px] leading-snug ${subCls}`}>{sub}</div>}
    </div>
  )
}

// ── ProbCard ──────────────────────────────────────────────────────────────────
// A probability shown as a KPI card (big % + a thin fill bar) so it sits alongside the
// other Monte Carlo stat cards instead of in a separate block.

function ProbCard({ prob, label, variant, tooltip }: { prob: number; label: string; variant: 'breach' | 'pass'; tooltip?: string }) {
  const pct = Math.round(prob * 100)
  const barCls = variant === 'breach'
    ? pct > 50 ? 'bg-neg' : pct > 10 ? 'bg-warn' : 'bg-pos'
    : pct >= 50 ? 'bg-pos' : 'bg-warn'
  const valCls = variant === 'breach'
    ? pct > 50 ? 'text-neg-text' : pct > 10 ? 'text-warn-text' : 'text-pos-text'
    : pct >= 50 ? 'text-pos-text' : 'text-warn-text'
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg px-[15px] py-[14px] h-full flex flex-col justify-center">
      <div className="flex items-center text-[10px] text-text-secondary uppercase tracking-[0.6px]">
        {label}
        {tooltip && <InfoTip text={tooltip} />}
      </div>
      <div className={`text-[24px] font-semibold mt-[6px] tracking-[-0.5px] font-mono ${valCls}`}>{pct}%</div>
      <div className="h-[5px] bg-bg-sunken rounded-full overflow-hidden mt-[10px]">
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

// ── Header-metric verdicts ──────────────────────────────────────────────────────
// Grading thresholds turn a raw ratio (degradation, breach prob — lower is better) into a pct + word +
// colour, so a metric card or summary tile shows good-vs-bad at a glance instead of an unanchored number.
function gradeWord(value: number | null | undefined, solidBelow: number, okBelow: number): { pct: number; word: string; cls: string } | null {
  if (value == null) return null
  const pct = Math.round(value * 100)
  const [word, cls] = value < solidBelow ? ['robust', 'text-pos-text']
    : value < okBelow ? ['acceptable', 'text-warn-text']
    : ['fragile', 'text-neg-text']
  return { pct, word, cls }
}

// One headline summary tile per analysis, shown in the grade card so all three verdicts read at a glance.
function VerdictTile({ label, value, word, cls }: { label: string; value: string; word: string; cls: string }) {
  return (
    <div className="rounded-md border border-border-subtle bg-bg-sunken px-3 py-2 flex-1 min-w-0">
      <div className="text-[9px] uppercase tracking-[0.5px] text-text-tertiary truncate">{label}</div>
      <div className={`text-[18px] font-semibold font-mono leading-tight mt-[2px] ${cls}`}>{value}</div>
      <div className={`text-[10px] leading-tight ${cls}`}>{word}</div>
    </div>
  )
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
  const [chartTab, setChartTab] = useState('mc')
  const [fullscreen, setFullscreen] = useState(false)
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

  function fmtDate(iso: string) {
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })
  }
  function dollar(n: number | null | undefined) {
    if (n == null) return '—'
    const sign = n >= 0 ? '+' : '-'
    return `${sign}$${Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
  }
  const pnlCls = run?.net_pnl != null && run.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'

  // ── Chart tabs ────────────────────────────────────────────────────────────────
  // Collapse the four stress charts into one tabbed panel so only the active one
  // renders at a time (mirrors BacktestDetail's Equity/Price/Breakdown pattern instead
  // of stacking every chart vertically). Tabs appear only when their data exists.
  const mcHasCharts   = (st.equity_paths?.length ?? 0) > 0 || st.distribution != null
  const wfHasCharts   = !!(st.walk_forward_summary && st.walk_forward_summary.length > 0)
  const sensHasCharts = !!(st.sensitivity_summary && Object.keys(st.sensitivity_summary).length > 0)

  const mcStats = st.status === 'complete' && st.median_final_pnl != null

  // ── Per-analysis KPIs ─────────────────────────────────────────────────────────
  // Each tab surfaces its own headline numbers right above its chart. Walk-forward and
  // sensitivity KPIs are derived from the summaries already on the record.
  const wfWindows = st.walk_forward_summary ?? []
  const wfAvg = (pick: (w: typeof wfWindows[number]) => number | null | undefined) => {
    const vals = wfWindows.map(pick).filter((v): v is number => v != null)
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
  }
  const wfAvgIS = wfAvg(w => w.is_sharpe)
  const wfAvgOOS = wfAvg(w => w.oos_sharpe)

  // Flatten the sensitivity grid into signed % changes to find the most fragile shift and the median.
  const sensShifts: { label: string; pct: number }[] = []
  if (st.sensitivity_summary) {
    for (const [param, shifts] of Object.entries(st.sensitivity_summary)) {
      for (const [shift, info] of Object.entries(shifts)) {
        const pct = info.pnl_delta_pct != null ? info.pnl_delta_pct
          : info.degradation != null ? -info.degradation * 100 : null
        if (pct != null) sensShifts.push({ label: `${param} ${shift}`, pct })
      }
    }
  }
  const sensWorst = sensShifts.length ? sensShifts.reduce((a, b) => (b.pct < a.pct ? b : a)) : null
  const sensMedian = sensShifts.length
    ? [...sensShifts.map(s => s.pct)].sort((a, b) => a - b)[Math.floor(sensShifts.length / 2)]
    : null
  const sensParamCount = st.sensitivity_summary ? Object.keys(st.sensitivity_summary).length : 0
  const fmtPct = (n: number | null) => n == null ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(0)}%`
  const fmtSharpe = (n: number | null) => n == null ? '—' : n.toFixed(2)

  // Headline verdict per analysis for the grade-card summary tiles.
  const mcVerdict = gradeWord(st.prob_breach, 0.05, 0.20)
  const wfVerdict = gradeWord(st.walk_forward_degradation, 0.20, 0.30)
  const sensVerdict = gradeWord(st.sensitivity_max_degradation, 0.25, 0.40)

  const chartTabs: [string, string][] = [
    ...(mcHasCharts   ? [['mc',   'Monte Carlo']  as [string, string]] : []),
    ...(wfHasCharts   ? [['wf',   'Walk-Forward'] as [string, string]] : []),
    ...(sensHasCharts ? [['sens', 'Sensitivity']  as [string, string]] : []),
  ]
  // Fall back to the first available tab if the remembered one isn't present (e.g. while still running).
  const activeChart = chartTabs.find(([k]) => k === chartTab)?.[0] ?? chartTabs[0]?.[0] ?? ''

  const chartTitleByKey: Record<string, string> = {
    mc: 'Monte Carlo', wf: 'Walk-Forward', sens: 'Parameter Sensitivity',
  }
  const chartSubByKey: Record<string, string> = {
    mc:   'The equity fan shows the spread of 100 simulated runs; the histogram shows how deep the worst drawdown got across all 10,000 simulations.',
    wf:   "Splits the period into windows and tests each on data the strategy wasn't tuned on. Out-of-sample Sharpe near in-sample = holds up; a big drop = overfit to history.",
    sens: 'Each parameter is nudged and the strategy re-run. Bars near zero = robust across settings; long bars = the edge depends on one exact value.',
  }
  // Right-of-tabs slot: MC shows chart info; WF/Sens verdicts now live in their KPI cards below, so
  // they don't repeat here.
  const chartRightByKey: Record<string, React.ReactNode> = {
    mc:   '100 simulations · p10–p90',
    wf:   undefined,
    sens: undefined,
  }

  // Per-tab KPI cards, rendered directly above that tab's chart so the numbers and the chart line up.
  const kpiBlock = (key: string): React.ReactNode => {
    if (key === 'mc') {
      return (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-[10px] mb-4">
          {mcStats && <>
            <MetricCard label="Median PnL" value={fmt$(st.median_final_pnl)} valueCls={medianCls}
              tooltip="The middle outcome across all 10,000 simulations — half ended better, half worse. Positive = profitable in a typical scenario." />
            <MetricCard label="Worst 5% PnL" value={fmt$(st.pct5_final_pnl)} valueCls={pct5Cls}
              tooltip="The 5th percentile final P&L — only 5% of simulations did worse. Shows the tail risk of a bad but realistic trade sequence." />
            <MetricCard label="Worst 5% Drawdown" value={fmt$(st.pct5_max_dd)}
              sub={ddLimit != null ? `limit ${fmt$(ddLimit)}` : undefined} subCls={ddOverLimit ? 'text-neg-text' : 'text-pos-text'}
              tooltip="The 5th-percentile maximum drawdown — only 5% of simulations hit a larger drawdown. If this exceeds the ruleset limit, you'd breach in bad-luck scenarios." />
            <MetricCard label="Worst 1% Drawdown" value={fmt$(st.pct1_max_dd)}
              sub={ddLimit != null ? `limit ${fmt$(ddLimit)}` : undefined} subCls={dd1OverLimit ? 'text-neg-text' : 'text-pos-text'}
              tooltip="The 1st-percentile maximum drawdown — the extreme tail. Only 1% of simulations were worse." />
          </>}
          {st.prob_breach != null && <>
            <ProbCard label="Prob. Breach" prob={st.prob_breach} variant="breach"
              tooltip="Across all 10,000 simulations, how often the strategy breaches the drawdown limit. Lower = safer." />
            <ProbCard label={isPersonal ? 'Prob. Stay Safe' : 'Prob. Pass'} prob={st.prob_pass_eval ?? 0} variant="pass"
              tooltip={isPersonal
                ? 'How often the strategy stays under the drawdown limit across all 10,000 simulations.'
                : 'How often the strategy passes the eval (hits target without breaching) across all 10,000 simulations.'} />
          </>}
        </div>
      )
    }
    if (key === 'wf') {
      return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-[10px] mb-4">
          <MetricCard label="IS→OOS Degradation" value={wfVerdict ? `${wfVerdict.pct}%` : 'n/a'} valueCls={wfVerdict?.cls ?? ''}
            sub={wfVerdict?.word ?? 'IS Sharpe ≤ 0'} subCls={wfVerdict?.cls ?? 'text-text-tertiary'}
            tooltip="How much Sharpe drops from in-sample (tuned) to out-of-sample (unseen) across windows. Higher = more overfit. Only meaningful when in-sample Sharpe is positive." />
          <MetricCard label="Avg In-Sample Sharpe" value={fmtSharpe(wfAvgIS)} sub="tuned on"
            tooltip="Average Sharpe across each window's in-sample (first 70%) segment — the part the strategy was effectively fit to." />
          <MetricCard label="Avg Out-of-Sample" value={fmtSharpe(wfAvgOOS)} sub="unseen"
            tooltip="Average Sharpe across each window's out-of-sample (last 30%) segment — the honest, unseen-data result." />
          <MetricCard label="Windows Tested" value={String(wfWindows.length)} sub="70 / 30 split"
            tooltip="Number of walk-forward windows the period was split into; each trained on its first 70% and tested on the unseen last 30%." />
        </div>
      )
    }
    if (key === 'sens') {
      return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-[10px] mb-4">
          <MetricCard label="Worst-Case Change" value={sensVerdict ? `${sensVerdict.pct}%` : 'n/a'} valueCls={sensVerdict?.cls ?? ''}
            sub={sensVerdict?.word ?? '—'} subCls={sensVerdict?.cls ?? 'text-text-tertiary'}
            tooltip="The largest performance drop seen when any single parameter is nudged. Bigger = the edge hinges on one exact value." />
          <MetricCard label="Most Fragile Param" value={sensWorst?.label ?? '—'} small valueCls="text-warn-text"
            sub={sensWorst ? `${fmtPct(sensWorst.pct)} vs baseline` : undefined}
            tooltip="The parameter shift that hurt performance the most — the strategy's biggest single point of fragility." />
          <MetricCard label="Params Tested" value={String(sensParamCount)} sub="±10% each"
            tooltip="How many strategy parameters were perturbed and re-run to probe stability." />
          <MetricCard label="Median Change" value={fmtPct(sensMedian)} valueCls={sensMedian != null && sensMedian < 0 ? 'text-neg-text' : ''}
            sub="across shifts"
            tooltip="The middle performance change across all parameter shifts. Near zero = broadly robust; strongly negative = generally fragile." />
        </div>
      )
    }
    return null
  }

  const renderChart = (key: string, h: number): React.ReactNode => {
    if (key === 'mc') {
      const hasFan  = st.equity_paths != null && st.equity_paths.length > 0
      const hasDist = st.distribution != null
      const both    = hasFan && hasDist
      // Both stack in one tab. The fan is the hero, so give it ~⅔ of the room; the histogram is a
      // secondary read. Subtract the two sub-headers + the fan's legend so the pair fits without clipping.
      const avail   = h - 96
      const fanH    = both ? Math.max(280, Math.round(avail * 0.64)) : h
      const distH   = both ? Math.max(170, Math.round(avail * 0.36)) : h
      return (
        <div className="space-y-5">
          {hasFan && (
            <div className="space-y-2">
              <SectionHeader
                label="Equity Path Fan"
                tooltip="100 of the simulated runs drawn as cumulative-P&L curves (starting at $0). Green = luckier orderings, cyan = median, red = unluckier. Dashed lines mark the drawdown limit and profit target."
              />
              <MonteCarloFan
                paths={st.equity_paths!}
                ruleset={{ max_loss_eod: ddLimit ?? undefined, profit_target: ruleset?.profit_target }}
                tradeCount={st.equity_paths![0]?.length ?? 0}
                height={fanH}
              />
            </div>
          )}
          {hasDist && (
            <div className="space-y-2">
              <SectionHeader
                label="Max Drawdown Distribution"
                right={ddLimit != null ? 'Red = over limit' : undefined}
                tooltip="How many of the 10,000 simulations ended with each size of worst drawdown. Bars further right = deeper drawdowns. Red bars exceeded the limit — you want the pile sitting LEFT of the limit line."
              />
              <DrawdownDistribution distribution={st.distribution!.max_dd} maxLoss={ddLimit} height={distH} />
            </div>
          )}
        </div>
      )
    }
    if (key === 'wf' && st.walk_forward_summary) {
      return <WalkForwardChart windows={st.walk_forward_summary} height={h} />
    }
    if (key === 'sens' && st.sensitivity_summary) {
      return <SensitivityRadar sensitivity={st.sensitivity_summary} height={h} />
    }
    return null
  }

  // ── Header block pieces ─────────────────────────────────────────────────────
  // Extracted as elements so they slot into either layout without duplicating markup:
  // the two-column block (grade over source on the left) when MC numbers exist, or a
  // plain stack (grade · pipeline · source) while a run is still computing them.
  const gradeCard = (
    <div className="rounded-lg border border-border-subtle bg-bg-surface overflow-hidden h-full">
      <div className="flex h-full">
        {st.grade && (
          <div className={`flex-shrink-0 w-16 flex items-center justify-center ${gradeCls}`}>
            <span className="text-[36px] font-black leading-none">{st.grade}</span>
          </div>
        )}
        <div className="flex-1 min-w-0 px-4 py-3 flex flex-col gap-2">
          <h1 className="text-h1 font-semibold leading-tight">{st.strategy_name || 'Stress Test'}</h1>
          <div className="flex flex-wrap gap-1.5 items-center">
            {ruleset && (
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold bg-gold-muted text-gold-text">
                {ruleset.name}
              </span>
            )}
            {isRunning && <RefreshCw size={13} className="text-accent animate-spin" />}
          </div>
          {/* Headline verdict from each analysis — the whole test at a glance */}
          {(mcVerdict || wfVerdict || sensVerdict) && (
            <div className="flex gap-2 mt-auto pt-1">
              {mcVerdict && <VerdictTile label="Monte Carlo" value={`${mcVerdict.pct}%`} word={`breach risk · ${mcVerdict.word}`} cls={mcVerdict.cls} />}
              {wfVerdict && <VerdictTile label="Walk-Forward" value={`${wfVerdict.pct}%`} word={`degradation · ${wfVerdict.word}`} cls={wfVerdict.cls} />}
              {sensVerdict && <VerdictTile label="Sensitivity" value={`${sensVerdict.pct}%`} word={`worst case · ${sensVerdict.word}`} cls={sensVerdict.cls} />}
            </div>
          )}
        </div>
      </div>
    </div>
  )

  const pipeline = isRunning ? (
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
  ) : null

  const sourceCard = run ? (
    <div className="rounded-lg border border-border-subtle bg-bg-surface px-4 py-3 h-full">
      <div className="flex items-stretch gap-6 h-full">
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
  ) : null

  return (
    <>
    <div className="space-y-8">

      {/* ── Back + Delete (delete placement mirrors OptimizationDetail) ─────────── */}
      <StickyHeader>
        {scrolled => (
          <div className={`flex items-center justify-between gap-3 ${scrolled ? 'mb-4' : 'mb-5'}`}>
            <div className="flex items-center gap-2.5 min-w-0">
              <button
                onClick={() => navigate(-1)}
                className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary transition-colors flex-shrink-0"
              >
                <ArrowLeft size={14} /> {!scrolled && 'Stress Tests'}
              </button>
              {scrolled && (
                <>
                  <span className="text-text-tertiary flex-shrink-0">·</span>
                  <h1 className="text-[14px] font-semibold truncate">{st.strategy_name || 'Stress Test'}</h1>
                  {st.instrument && (
                    <span className="inline-flex items-center px-1.5 py-[1px] rounded text-[11px] font-semibold font-mono bg-accent/10 text-accent border border-accent/20 flex-shrink-0">
                      {st.instrument}
                    </span>
                  )}
                </>
              )}
            </div>
            <button
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium text-text-tertiary hover:text-neg-text hover:bg-neg-muted border border-transparent hover:border-neg-text/20 transition-colors flex-shrink-0"
            >
              <Trash2 size={12} />
              Delete
            </button>
          </div>
        )}
      </StickyHeader>

      {/* ══ Context row — grade (with per-analysis verdicts) + source backtest ════ */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
        {gradeCard}
        {sourceCard}
      </div>

      {/* Pipeline progress (running only) — full width below the context row */}
      {pipeline}

      {/* ══ Analysis workspace — one tabbed panel; each tab = its KPIs above its chart ══ */}
      {chartTabs.length > 0 && (
        <ChartTabPanel
          tabs={chartTabs}
          active={activeChart}
          onActive={setChartTab}
          height={activeChart === 'mc' ? 640 : 440}
          sub={chartSubByKey[activeChart]}
          right={chartRightByKey[activeChart]}
          aboveChart={kpiBlock(activeChart)}
          onExpand={() => setFullscreen(true)}
          render={renderChart}
        />
      )}

      {/* ── Error ─────────────────────────────────────────────────────────────── */}
      {st.error_message && (
        <div className="rounded-lg border border-neg-text/30 bg-neg-muted p-4">
          <p className="text-[13px] text-neg-text font-mono">{st.error_message}</p>
        </div>
      )}

    </div>

    {fullscreen && activeChart && (
      <ChartModal
        title={chartTitleByKey[activeChart]}
        onClose={() => setFullscreen(false)}
        render={(h) => renderChart(activeChart, h)}
      />
    )}

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
