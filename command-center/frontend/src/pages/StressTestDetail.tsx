import { useState, useEffect, Fragment } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Trash2, ArrowLeft, RefreshCw, Check, AlertTriangle, Square, Upload } from 'lucide-react'
import { useStressTest, useDeleteStressTest, useCancelStressTest } from '@/hooks/useStressTests'
import { useRulesets, useBacktestRun } from '@/hooks/useLab'
import MonteCarloFan from '@/components/MonteCarloFan'
import DrawdownDistribution from '@/components/DrawdownDistribution'
import WalkForwardChart from '@/components/WalkForwardChart'
import SensitivityRadar from '@/components/SensitivityRadar'
import { ChartTabPanel, ChartModal } from '@/components/ChartTabPanel'
import StickyHeader from '@/components/StickyHeader'
import InfoTip from '@/components/InfoTip'
import { SettingsImportModal } from '@/components/SettingsImportModal'

// ── MetricCard ────────────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  valueCls = '',
  sub,
  subCls = 'text-text-tertiary',
  tooltip,
  small = false,
}: {
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
      <div
        className={`${small ? 'text-[17px]' : 'text-[24px]'} font-semibold mt-[6px] tracking-[-0.5px] font-mono ${valueCls}`}
      >
        {value}
      </div>
      {sub && <div className={`text-[11px] mt-[3px] leading-snug ${subCls}`}>{sub}</div>}
    </div>
  )
}

// ── ProbCard ──────────────────────────────────────────────────────────────────
// A probability shown as a KPI card (big % + a thin fill bar) so it sits alongside the
// other Monte Carlo stat cards instead of in a separate block.

function ProbCard({
  prob,
  label,
  variant,
  tooltip,
}: {
  prob: number
  label: string
  variant: 'breach' | 'pass'
  tooltip?: string
}) {
  const pct = Math.round(prob * 100)
  const barCls =
    variant === 'breach'
      ? pct > 50
        ? 'bg-neg'
        : pct > 10
          ? 'bg-warn'
          : 'bg-pos'
      : pct >= 50
        ? 'bg-pos'
        : 'bg-warn'
  const valCls =
    variant === 'breach'
      ? pct > 50
        ? 'text-neg-text'
        : pct > 10
          ? 'text-warn-text'
          : 'text-pos-text'
      : pct >= 50
        ? 'text-pos-text'
        : 'text-warn-text'
  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg px-[15px] py-[14px] h-full flex flex-col justify-center">
      <div className="flex items-center text-[10px] text-text-secondary uppercase tracking-[0.6px]">
        {label}
        {tooltip && <InfoTip text={tooltip} />}
      </div>
      <div className={`text-[24px] font-semibold mt-[6px] tracking-[-0.5px] font-mono ${valCls}`}>
        {pct}%
      </div>
      <div className="h-[5px] bg-bg-sunken rounded-full overflow-hidden mt-[10px]">
        <div
          className={`h-full rounded-full transition-all ${barCls}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ── SectionHeader ─────────────────────────────────────────────────────────────

function SectionHeader({
  label,
  right,
  tooltip,
}: {
  label: string
  right?: React.ReactNode
  tooltip?: string
}) {
  return (
    <div className="flex items-baseline justify-between">
      <div className="flex items-center">
        <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px]">
          {label}
        </p>
        {tooltip && <InfoTip text={tooltip} />}
      </div>
      {right && <span className="text-[11px] text-text-tertiary">{right}</span>}
    </div>
  )
}

// ── Header-metric verdicts ──────────────────────────────────────────────────────
// Grading thresholds turn a raw ratio (degradation, breach prob — lower is better) into a pct + word +
// colour, so a metric card or summary tile shows good-vs-bad at a glance instead of an unanchored number.
function gradeWord(
  value: number | null | undefined,
  solidBelow: number,
  okBelow: number
): { pct: number; word: string; cls: string } | null {
  if (value == null) return null
  const pct = Math.round(value * 100)
  const [word, cls] =
    value < solidBelow
      ? ['robust', 'text-pos-text']
      : value < okBelow
        ? ['acceptable', 'text-warn-text']
        : ['fragile', 'text-neg-text']
  return { pct, word, cls }
}

// One headline summary tile per analysis, shown in the grade card so all three verdicts read at a glance.
function VerdictTile({
  label,
  value,
  word,
  cls,
}: {
  label: string
  value: string
  word: string
  cls: string
}) {
  return (
    <div className="rounded-md border border-border-subtle bg-bg-sunken px-3 py-2 flex-1 min-w-0">
      <div className="text-[9px] uppercase tracking-[0.5px] text-text-tertiary truncate">
        {label}
      </div>
      <div className={`text-[18px] font-semibold font-mono leading-tight mt-[2px] ${cls}`}>
        {value}
      </div>
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
  const cancelTest = useCancelStressTest()

  const isRunning = st ? !st.status.startsWith('failed') && st.status !== 'complete' : false
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [copySettings, setCopySettings] = useState(false)
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

  const ruleset = rulesets?.find((r) => r.id === st.ruleset_id)

  // Which phases this test actually involves. `phases_requested` is authoritative when present —
  // it is written before anything can fail, so a phase that crashed still shows in the pipeline
  // instead of vanishing. Older rows fall back to inferring it from the results.
  // ⚠ `hasSens` used to be `hasWF || …`, so a walk-forward-only test drew a Sensitivity step that
  // could never complete.
  const requested = st.phases_requested
  const hasWF = requested
    ? requested.includes('walk_forward')
    : st.walk_forward_summary != null || st.status === 'running_wf'
  const hasSens = requested
    ? requested.includes('sensitivity')
    : st.sensitivity_summary != null || st.status === 'running_sens'
  function fmtDuration(startSec: number | null, endSec: number | null): string | null {
    if (!startSec) return null
    const secs = (endSec ?? nowSec) - startSec
    if (secs < 60) return `${secs}s`
    return `${Math.floor(secs / 60)}m ${secs % 60}s`
  }
  const totalElapsed = fmtDuration(st.created_at, st.completed_at)

  // done fallbacks: use status when phase timestamps aren't available (pre-migration tests)
  const mcDone = st.mc_completed_at != null || st.status !== 'running'
  const wfDone = st.wf_completed_at != null || st.walk_forward_summary != null
  const sensDone = st.sensitivity_summary != null

  type PipelineStep = {
    key: string
    label: string
    sub: string
    timer: string | null
    done: boolean
    active: boolean
  }
  const pipelineSteps: PipelineStep[] = [
    {
      key: 'mc',
      label: 'Monte Carlo',
      sub: '10k simulations',
      timer: fmtDuration(st.created_at, st.mc_completed_at),
      done: mcDone,
      active: st.status === 'running',
    },
    ...(hasWF
      ? [
          {
            key: 'wf',
            label: 'Walk-forward',
            sub: 'In-sample vs out-of-sample',
            timer: fmtDuration(st.mc_completed_at, st.wf_completed_at),
            done: wfDone,
            active: st.status === 'running_wf',
          },
        ]
      : []),
    ...(hasSens
      ? [
          {
            key: 'sens',
            label: 'Sensitivity',
            sub: 'Parameter stability',
            timer: fmtDuration(
              st.wf_completed_at ?? st.mc_completed_at,
              st.status === 'complete' ? st.completed_at : null
            ),
            done: sensDone,
            active: st.status === 'running_sens',
          },
        ]
      : []),
    {
      key: 'grade',
      label: 'Grade',
      sub: 'A – F',
      timer: null,
      done: st.grade != null,
      active: false,
    },
  ]

  const gradeCls =
    st.grade === 'A' || st.grade === 'B'
      ? 'text-pos-text bg-pos-muted'
      : st.grade === 'C'
        ? 'text-warn-text bg-warn-muted'
        : 'text-neg-text bg-neg-muted'

  const medianCls =
    st.median_final_pnl == null ? '' : st.median_final_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'
  const pct5Cls =
    st.pct5_final_pnl == null ? '' : st.pct5_final_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'

  // The dollar drawdown limit the charts and cards compare against. Mirrors the backend's
  // effective_dd_limit_usd: personal/demo translate their %-from-peak rule to dollars, prop
  // uses max_loss_eod. Critically, personal rows carry max_loss_eod = 0 (sentinel), so passing
  // it raw would draw a "$0 limit" and mark every bar over-limit.
  const isPersonal = ruleset?.ruleset_type === 'personal' || ruleset?.ruleset_type === 'demo'
  const ddLimit: number | null = !ruleset
    ? null
    : isPersonal
      ? ruleset.max_drawdown_from_peak_pct && ruleset.account_size
        ? (ruleset.account_size * ruleset.max_drawdown_from_peak_pct) / 100
        : null
      : ruleset.max_loss_eod || null

  // ── The BASIS the grade read, and therefore the basis this page must show ────────────────────
  // 🔴 The backend switches to a PERCENT drawdown as soon as a run compounds — a fixed dollar
  // limit stops being comparable to an account that has grown away from the size it was written
  // for — records which basis it used in `dd_basis`, and grades on that. This page read NEITHER
  // `dd_basis` nor the percent columns: it printed dollars against a dollar limit and coloured
  // them over/under while the letter beside them had been decided on percentages. On a compounding
  // run the two can disagree outright, so a red "over limit" could sit next to an A.
  //
  // `effective_dd_limit_pct` mirrored: personal/demo state the percent, prop rows derive it (a
  // $5,000 trailing max loss on a $50,000 account is 10%).
  const onPercent = st.dd_basis === 'percent' && st.pct1_max_dd_pct != null
  const ddLimitPct: number | null = !ruleset
    ? null
    : isPersonal
      ? (ruleset.max_drawdown_from_peak_pct ?? null)
      : ddLimit && ruleset.account_size
        ? (ddLimit / ruleset.account_size) * 100
        : null

  /** A drawdown value + limit in whichever unit the grade actually used. */
  const dd = (dollars: number | null | undefined, pct: number | null | undefined) => {
    const value = onPercent ? pct : dollars
    const limit = onPercent ? ddLimitPct : ddLimit
    return {
      value,
      limit,
      text: value == null ? '—' : onPercent ? `${value.toFixed(1)}%` : fmt$(value),
      limitText:
        limit == null ? null : onPercent ? `limit ${limit.toFixed(0)}%` : `limit ${fmt$(limit)}`,
      over: limit != null && value != null && value > limit,
    }
  }
  const dd5 = dd(st.pct5_max_dd, st.pct5_max_dd_pct)
  const dd1 = dd(st.pct1_max_dd, st.pct1_max_dd_pct)
  const basisNote = onPercent
    ? 'Measured as a PERCENT of the running peak, because this run compounds — a fixed dollar limit is not comparable to an account that has grown away from the size it was written for. This is the basis the grade read.'
    : 'Measured in DOLLARS, because this run holds position size constant. This is the basis the grade read.'

  // Local midnight, not UTC — a bare 'YYYY-MM-DD' otherwise renders a day early west of
  // Greenwich. Same fix in BacktestDetail/SweepDetail/OptimizationDetail/StackDetail.
  function fmtDate(iso: string) {
    return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: '2-digit',
    })
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
  const mcHasCharts = (st.equity_paths?.length ?? 0) > 0 || st.distribution != null
  const wfHasCharts = !!(st.walk_forward_summary && st.walk_forward_summary.length > 0)
  const sensHasCharts = !!(st.sensitivity_summary && Object.keys(st.sensitivity_summary).length > 0)

  const mcStats = st.status === 'complete' && st.median_final_pnl != null

  // ── Per-analysis KPIs ─────────────────────────────────────────────────────────
  // Each tab surfaces its own headline numbers right above its chart. Walk-forward and
  // sensitivity KPIs are derived from the summaries already on the record.
  const wfWindows = st.walk_forward_summary ?? []
  const wfAvg = (pick: (w: (typeof wfWindows)[number]) => number | null | undefined) => {
    const vals = wfWindows.map(pick).filter((v): v is number => v != null)
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
  }
  // The NATIVE (optimizer-derived) walk-forward has no trade-level data, so it degrades on PROFIT
  // FACTOR and leaves every Sharpe null. Reading `is_sharpe` regardless gave that path a KPI row of
  // dashes over a chart of zero bars. Detect the path from the summary's own shape, as grading does.
  const wfIsPf =
    wfWindows.length > 0 &&
    wfWindows.every((w) => w.is_sharpe == null) &&
    wfWindows.some((w) => w.is_pf != null)
  const wfAvgIS = wfIsPf ? wfAvg((w) => w.is_pf) : wfAvg((w) => w.is_sharpe)
  const wfAvgOOS = wfIsPf ? wfAvg((w) => w.oos_pf) : wfAvg((w) => w.oos_sharpe)
  // Mirrors stress_tester._WF_MIN_TRADES_PER_WINDOW. A window under it on EITHER side is excluded
  // from the degradation, which is why this page has to show the counts at all.
  const WF_MIN_TRADES_PER_WINDOW = 20
  const wfThinCount = wfWindows.filter(
    (w) =>
      (w.is_trades != null && w.is_trades < WF_MIN_TRADES_PER_WINDOW) ||
      (w.oos_trades != null && w.oos_trades < WF_MIN_TRADES_PER_WINDOW)
  ).length
  const wfOosTrades = wfWindows.map((w) => w.oos_trades).filter((v): v is number => v != null)
  const wfOosTradeText = wfOosTrades.length
    ? Math.min(...wfOosTrades) === Math.max(...wfOosTrades)
      ? String(wfOosTrades[0])
      : `${Math.min(...wfOosTrades)}–${Math.max(...wfOosTrades)}`
    : '—'

  // Flatten the sensitivity grid into SIGNED % changes.
  // 🔴 `degradation` is an absolute magnitude (|new − base| / base), and this used to render it as
  // `-degradation * 100` — inventing a direction. A parameter shift that IMPROVED profit factor
  // was therefore drawn and labelled as a loss, "Median Change" was negative by construction, and
  // the "Worst-Case Change" card (positive) and "Most Fragile Param" card (negative) printed the
  // same quantity with opposite signs side by side. The backend now measures `pf_delta_pct`, which
  // keeps the sign; `magnitude` stays the thing that is ranked, since a shift is evidence whichever
  // way it moved.
  const sensShifts: { label: string; signed: number | null; magnitude: number }[] = []
  if (st.sensitivity_summary) {
    for (const [param, shifts] of Object.entries(st.sensitivity_summary)) {
      for (const [shift, info] of Object.entries(shifts)) {
        // Preference order: the measured signed change, then a legacy record's own signed P&L
        // delta, then the magnitude with NO sign asserted.
        const signed = info.pf_delta_pct ?? info.pnl_delta_pct ?? null
        const magnitude =
          info.degradation != null
            ? info.degradation * 100
            : signed != null
              ? Math.abs(signed)
              : null
        if (magnitude != null) sensShifts.push({ label: `${param} ${shift}`, signed, magnitude })
      }
    }
  }
  // Ranked on MAGNITUDE — the biggest mover is the biggest fragility whichever way it went.
  const sensWorst = sensShifts.length
    ? sensShifts.reduce((a, b) => (b.magnitude > a.magnitude ? b : a))
    : null
  const sensMedian = sensShifts.length
    ? [...sensShifts.map((s) => s.magnitude)].sort((a, b) => a - b)[
        Math.floor(sensShifts.length / 2)
      ]
    : null
  const sensParamCount = st.sensitivity_summary ? Object.keys(st.sensitivity_summary).length : 0
  const sensShiftLabels = [
    ...new Set(Object.values(st.sensitivity_summary ?? {}).flatMap((s) => Object.keys(s))),
  ]
  const fmtSigned = (n: number | null | undefined) =>
    n == null ? '—' : `${n > 0 ? '+' : ''}${n.toFixed(0)}%`
  const fmtSharpe = (n: number | null | undefined) => (n == null ? '—' : n.toFixed(2))

  // Headline verdict per analysis for the grade-card summary tiles.
  const mcVerdict = gradeWord(st.prob_breach, 0.05, 0.2)
  const wfVerdict = gradeWord(st.walk_forward_degradation, 0.2, 0.3)
  const sensVerdict = gradeWord(st.sensitivity_max_degradation, 0.25, 0.4)

  const chartTabs: [string, string][] = [
    ...(mcHasCharts ? [['mc', 'Monte Carlo'] as [string, string]] : []),
    ...(wfHasCharts ? [['wf', 'Walk-Forward'] as [string, string]] : []),
    ...(sensHasCharts ? [['sens', 'Sensitivity'] as [string, string]] : []),
  ]
  // Fall back to the first available tab if the remembered one isn't present (e.g. while still running).
  const activeChart = chartTabs.find(([k]) => k === chartTab)?.[0] ?? chartTabs[0]?.[0] ?? ''

  const chartTitleByKey: Record<string, string> = {
    mc: 'Monte Carlo',
    wf: 'Walk-Forward',
    sens: 'Parameter Sensitivity',
  }
  const chartSubByKey: Record<string, string> = {
    mc: 'The equity fan shows the spread of 100 simulated runs; the histogram shows how deep the worst drawdown got across all 10,000 simulations.',
    wf: "Splits the period into windows and tests each on data the strategy wasn't tuned on. Out-of-sample Sharpe near in-sample = holds up; a big drop = overfit to history.",
    sens: 'Each parameter is nudged and the strategy re-run. Bars near zero = robust across settings; long bars = the edge depends on one exact value.',
  }
  // Right-of-tabs slot: MC shows chart info; WF/Sens verdicts now live in their KPI cards below, so
  // they don't repeat here.
  const chartRightByKey: Record<string, React.ReactNode> = {
    mc: '100 simulations · p10–p90',
    wf: undefined,
    sens: undefined,
  }

  // Per-tab KPI cards, rendered directly above that tab's chart so the numbers and the chart line up.
  const kpiBlock = (key: string): React.ReactNode => {
    if (key === 'mc') {
      return (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-[10px] mb-4">
          {mcStats && (
            <>
              <MetricCard
                label="Median PnL"
                value={fmt$(st.median_final_pnl)}
                valueCls={medianCls}
                tooltip="The middle outcome across all 10,000 simulations — half ended better, half worse. Positive = profitable in a typical scenario."
              />
              <MetricCard
                label="Worst 5% PnL"
                value={fmt$(st.pct5_final_pnl)}
                valueCls={pct5Cls}
                tooltip="The 5th percentile final P&L — only 5% of simulations did worse. Shows the tail risk of a bad but realistic trade sequence."
              />
              <MetricCard
                label="Worst 5% Drawdown"
                value={dd5.text}
                sub={dd5.limitText ?? undefined}
                subCls={dd5.over ? 'text-neg-text' : 'text-pos-text'}
                tooltip={`The 5th-percentile maximum drawdown — only 5% of simulations hit a larger one. If this exceeds the ruleset limit, you'd breach in bad-luck scenarios. ${basisNote}`}
              />
              <MetricCard
                label="Worst 1% Drawdown"
                value={dd1.text}
                sub={dd1.limitText ?? undefined}
                subCls={dd1.over ? 'text-neg-text' : 'text-pos-text'}
                tooltip={`The 1st-percentile maximum drawdown — the extreme tail. Only 1% of simulations were worse. ${basisNote}`}
              />
            </>
          )}
          {/* Null is NOT zero. `prob_pass_eval` is null when there was nothing to pass — no
              drawdown limit on the ruleset, or no profit target — and `?? 0` rendered that as
              "0%", i.e. "this strategy never passes" about a measurement never taken. The backend
              made both fields nullable for exactly this reason. */}
          {st.prob_breach != null && (
            <ProbCard
              label="Prob. Breach"
              prob={st.prob_breach}
              variant="breach"
              tooltip={`Across every simulation, how often the strategy breaches the drawdown limit. Lower = safer. ${basisNote}`}
            />
          )}
          {st.prob_pass_eval != null && (
            <ProbCard
              label={isPersonal ? 'Prob. Stay Safe' : 'Prob. Pass'}
              prob={st.prob_pass_eval}
              variant="pass"
              tooltip={
                isPersonal
                  ? 'How often the strategy stays under the drawdown limit across every simulation.'
                  : 'How often the strategy passes the eval (hits target without breaching) across every simulation.'
              }
            />
          )}
          {mcStats && st.prob_breach == null && (
            <MetricCard
              label="Prob. Breach"
              value="n/a"
              valueCls="text-text-tertiary"
              sub="no limit to breach"
              small
              tooltip="This ruleset states no drawdown limit, so there is nothing for a simulation to breach. That is a third answer — not 0% and not 100% — and the grade is withheld for the same reason."
            />
          )}
        </div>
      )
    }
    if (key === 'wf') {
      return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-[10px] mb-4">
          <MetricCard
            label="IS→OOS Degradation"
            value={wfVerdict ? `${wfVerdict.pct}%` : 'n/a'}
            valueCls={wfVerdict?.cls ?? ''}
            sub={wfVerdict?.word ?? 'not assessable'}
            subCls={wfVerdict?.cls ?? 'text-text-tertiary'}
            tooltip="How much the metric drops from each window's first 70% to its unseen last 30%. NOTE: the SAME fixed parameters are run on both halves — nothing is re-tuned between them — so this measures whether the edge HELD UP in the later period. It does not detect overfitting, which would need the optimizer re-run on each in-sample half. 'Not assessable' means no window had both a real in-sample edge and enough trades on each side."
          />
          {/* Trade counts are the whole verdict on a low-frequency strategy — a window with fewer
              than 20 on either side is excluded, and here that is usually every window. The field
              existed in the engine and was dropped by the API model, so this could never be shown. */}
          <MetricCard
            label="Out-of-Sample Trades"
            value={wfOosTradeText}
            valueCls={wfThinCount > 0 ? 'text-warn-text' : ''}
            sub={
              wfThinCount > 0
                ? `${wfThinCount} of ${wfWindows.length} windows too thin`
                : 'all windows have enough'
            }
            subCls={wfThinCount > 0 ? 'text-warn-text' : 'text-pos-text'}
            small
            tooltip={`Trades closed by each window's unseen last 30%. Below ${WF_MIN_TRADES_PER_WINDOW} on either side, one trade's luck moves the Sharpe more than the strategy does, so that window is excluded rather than averaged in. Fix it with FEWER, longer windows — not by loosening the test.`}
          />
          <MetricCard
            label="Avg In-Sample"
            value={fmtSharpe(wfAvgIS)}
            sub={wfIsPf ? 'profit factor' : 'Sharpe'}
            tooltip="Average across each window's in-sample (first 70%) segment. The optimizer-derived native path has no trade-level data, so it reports PROFIT FACTOR and no Sharpe at all — the label says which you are looking at."
          />
          <MetricCard
            label="Avg Out-of-Sample"
            value={fmtSharpe(wfAvgOOS)}
            sub={wfIsPf ? 'profit factor' : 'Sharpe'}
            tooltip="Average across each window's out-of-sample (last 30%) segment — the honest, unseen-data result."
          />
        </div>
      )
    }
    if (key === 'sens') {
      return (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-[10px] mb-4">
          <MetricCard
            label="Biggest Move"
            value={sensVerdict ? `${sensVerdict.pct}%` : 'n/a'}
            valueCls={sensVerdict?.cls ?? ''}
            sub={sensVerdict?.word ?? 'not measured'}
            subCls={sensVerdict?.cls ?? 'text-text-tertiary'}
            tooltip="The largest change in profit factor produced by nudging any single parameter, as a magnitude. Bigger = the edge hinges on one exact value. A shift that IMPROVES the result counts just as much — it is equally evidence that the result moves."
          />
          <MetricCard
            label="Most Sensitive Param"
            value={sensWorst?.label ?? '—'}
            small
            valueCls="text-warn-text"
            sub={
              sensWorst
                ? `${fmtSigned(sensWorst.signed)} vs baseline${sensWorst.signed == null ? '' : ''}`
                : undefined
            }
            tooltip="The parameter shift that moved profit factor the most. The percentage is SIGNED — negative is a drop, positive an improvement — because a magnitude drawn as a loss is a direction nobody measured."
          />
          <MetricCard
            label="Params Tested"
            value={String(sensParamCount)}
            sub={sensShiftLabels.length ? sensShiftLabels.join(' / ') : undefined}
            tooltip="How many strategy parameters were actually perturbed and re-run. Params behind a switch this run has OFF are excluded — no shift of them could change the result — as are shifts that fall outside a parameter's own bounds or land back on the baseline."
          />
          <MetricCard
            label="Median Move"
            value={sensMedian == null ? '—' : `${sensMedian.toFixed(0)}%`}
            sub="across shifts"
            tooltip="The middle magnitude across all parameter shifts. Near zero = broadly robust; large = the result moves wherever you push it."
          />
        </div>
      )
    }
    return null
  }

  const renderChart = (key: string, h: number): React.ReactNode => {
    if (key === 'mc') {
      const hasFan = st.equity_paths != null && st.equity_paths.length > 0
      const hasDist = st.distribution != null
      const both = hasFan && hasDist
      // Both stack in one tab. The fan is the hero, so give it ~⅔ of the room; the histogram is a
      // secondary read. Subtract the two sub-headers + the fan's legend so the pair fits without clipping.
      const avail = h - 96
      const fanH = both ? Math.max(280, Math.round(avail * 0.64)) : h
      const distH = both ? Math.max(170, Math.round(avail * 0.36)) : h
      return (
        <div className="space-y-5">
          {hasFan && (
            <div className="space-y-2">
              <SectionHeader
                label="Equity Path Fan"
                tooltip="100 of the simulated runs drawn as cumulative-P&L curves (starting at $0). Green = luckier orderings, cyan = median, red = unluckier. A profit target is drawn when the ruleset states one. There is deliberately NO drawdown-limit line: a drawdown is peak-to-trough, not a level of cumulative P&L, so a line below zero would let a fan that breaches repeatedly look safe. The histogram below measures the drawdown itself."
              />
              <MonteCarloFan
                paths={st.equity_paths!}
                ruleset={{ profit_target: ruleset?.profit_target }}
                tradeCount={st.equity_paths![0]?.length ?? 0}
                height={fanH}
              />
            </div>
          )}
          {hasDist && (
            <div className="space-y-2">
              <SectionHeader
                label="Max Drawdown Distribution"
                right={dd1.limit != null ? 'Red = over limit' : undefined}
                tooltip={`How many simulations ended with each size of worst drawdown. Bars further right = deeper drawdowns. Red bars exceeded the limit — you want the pile sitting LEFT of the limit line. ${basisNote}`}
              />
              {/* Drawn in the unit the GRADE read. The percent histogram exists only on a
                  compounding run, which is exactly when the dollar one is the wrong picture. */}
              <DrawdownDistribution
                distribution={(onPercent && st.distribution!.max_dd_pct) || st.distribution!.max_dd}
                maxLoss={onPercent && st.distribution!.max_dd_pct ? ddLimitPct : ddLimit}
                unit={onPercent && st.distribution!.max_dd_pct ? 'percent' : 'dollars'}
                height={distH}
              />
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
        {st.grade ? (
          <div className={`flex-shrink-0 w-16 flex items-center justify-center ${gradeCls}`}>
            <span className="text-[36px] font-black leading-none">{st.grade}</span>
          </div>
        ) : (
          /* A test that finished WITHOUT a letter is a first-class outcome (the ruleset states no
             drawdown limit, and every grade is a statement about drawdown vs a limit). It used to
             render as a card with no letter and no explanation, which reads as a broken page. */
          st.status === 'complete' && (
            <div className="flex-shrink-0 w-16 flex flex-col items-center justify-center bg-bg-sunken text-text-tertiary">
              <span className="text-[20px] font-black leading-none">—</span>
              <span className="text-[9px] uppercase tracking-[0.4px] mt-1">not graded</span>
            </div>
          )
        )}
        <div className="flex-1 min-w-0 px-4 py-3 flex flex-col gap-2">
          <h1 className="text-h1 font-semibold leading-tight">
            {st.strategy_name || 'Stress Test'}
          </h1>
          <div className="flex flex-wrap gap-1.5 items-center">
            {ruleset && (
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold bg-gold-muted text-gold-text">
                {ruleset.name}
              </span>
            )}
            {/* Which unit every drawdown on this page is in, and therefore which unit the letter
                was decided in. Without it a reader cannot tell whether "62.1" is dollars or
                percent, and the two lead to opposite conclusions. */}
            {mcStats && (
              <span
                className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium font-mono bg-bg-sunken border border-border-subtle text-text-secondary"
                title={basisNote}
              >
                drawdown in {onPercent ? '%' : '$'}
              </span>
            )}
            {isRunning && <RefreshCw size={13} className="text-accent animate-spin" />}
          </div>
          {/* Headline verdict from each analysis — the whole test at a glance */}
          {(mcVerdict || wfVerdict || sensVerdict) && (
            <div className="flex gap-2 mt-auto pt-1">
              {mcVerdict && (
                <VerdictTile
                  label="Monte Carlo"
                  value={`${mcVerdict.pct}%`}
                  word={`breach risk · ${mcVerdict.word}`}
                  cls={mcVerdict.cls}
                />
              )}
              {wfVerdict && (
                <VerdictTile
                  label="Walk-Forward"
                  value={`${wfVerdict.pct}%`}
                  word={`degradation · ${wfVerdict.word}`}
                  cls={wfVerdict.cls}
                />
              )}
              {sensVerdict && (
                <VerdictTile
                  label="Sensitivity"
                  value={`${sensVerdict.pct}%`}
                  word={`worst case · ${sensVerdict.word}`}
                  cls={sensVerdict.cls}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )

  // ── Why this grade ────────────────────────────────────────────────────────────
  // 🔴 `grade_reasons` was computed, stored, shipped over the wire — and rendered NOWHERE. So
  // every sentence the engine writes to explain itself was thrown away: "Not graded — this ruleset
  // has no drawdown limit", "Capped at B — an A needs walk-forward evidence and this run produced
  // none", "the windows closed too few trades each. Re-run with fewer walk-forward windows". The
  // last one names the fix, which makes it the most useful text the whole feature produces.
  const phaseFailures = Object.entries(st.phase_failures ?? {})
  const reasonsCard =
    st.grade_reasons?.length || phaseFailures.length || st.results_error ? (
      <div className="rounded-lg border border-border-subtle bg-bg-surface px-4 py-3 space-y-2">
        <SectionHeader
          label={st.grade ? `Why ${st.grade}` : 'Why this test is not graded'}
          tooltip="The engine's own reasoning, in the same unit the grade was decided in. Where a result could not be measured it says so rather than substituting a number."
        />
        {phaseFailures.map(([phase, why]) => (
          <div key={phase} className="flex gap-2 items-start text-[12px] text-neg-text">
            <AlertTriangle size={12} className="mt-[3px] flex-shrink-0" />
            <span>
              <span className="font-semibold capitalize">{phase.replace('_', '-')}</span> failed:{' '}
              {why}
            </span>
          </div>
        ))}
        {st.results_error && (
          <div className="flex gap-2 items-start text-[12px] text-warn-text">
            <AlertTriangle size={12} className="mt-[3px] flex-shrink-0" />
            <span>{st.results_error}</span>
          </div>
        )}
        <ul className="space-y-1">
          {(st.grade_reasons ?? []).map((r, i) => (
            <li key={i} className="flex gap-2 items-start text-[12px] text-text-secondary">
              <span className="text-text-tertiary mt-[1px]">·</span>
              <span>{r}</span>
            </li>
          ))}
        </ul>
      </div>
    ) : null

  const pipeline = isRunning ? (
    <div className="rounded-lg border border-accent/20 bg-accent/5 px-5 py-4 space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.6px] text-text-secondary">
          Running
        </span>
        <div className="flex items-center gap-3">
          <span className="text-[11px] font-mono text-text-tertiary">
            Total elapsed: <span className="text-accent">{totalElapsed}</span>
          </span>
          {/* Walk-forward plus sensitivity is 60+ real backtests holding the platform lock. There
              was no way to stop one short of restarting the backend — the same gap the optimizer
              closed on 2026-08-04. */}
          <button
            onClick={() => cancelTest.mutate(st.stress_test_id)}
            disabled={cancelTest.isPending}
            className="flex items-center gap-1.5 px-[10px] py-[4px] rounded-md text-[12px] font-medium bg-neg-muted text-neg-text border border-neg-text/20 hover:bg-neg-text/20 transition-colors disabled:opacity-50"
          >
            <Square size={10} />
            {cancelTest.isPending ? 'Stopping…' : 'Stop'}
          </button>
        </div>
      </div>
      <div className="flex items-start">
        {/* A Fragment returned from map() needs the key ON the fragment — keys on its children do
            not satisfy React and it warns on every render. */}
        {pipelineSteps.map((step, i) => (
          <Fragment key={step.key}>
            {i > 0 && (
              <div
                className={`flex-1 h-px mt-3 mx-2 ${pipelineSteps[i - 1].done ? 'bg-accent/40' : 'bg-border-subtle'}`}
              />
            )}
            <div className="flex flex-col items-center gap-[6px] w-[88px] flex-shrink-0">
              <div
                className={`w-6 h-6 rounded-full border flex items-center justify-center ${
                  step.active
                    ? 'border-accent bg-accent/10'
                    : step.done
                      ? 'border-pos bg-pos-muted'
                      : 'border-border-default bg-bg-surface'
                }`}
              >
                {step.done ? (
                  <Check size={11} className="text-pos-text" />
                ) : step.active ? (
                  <span className="w-[7px] h-[7px] rounded-full bg-accent animate-pulse" />
                ) : (
                  <span className="w-[6px] h-[6px] rounded-full bg-border-default" />
                )}
              </div>
              <div className="text-center">
                <div
                  className={`text-[11px] font-semibold leading-none ${step.active ? 'text-accent' : step.done ? 'text-text-primary' : 'text-text-tertiary'}`}
                >
                  {step.label}
                </div>
                <div className="text-[10px] text-text-tertiary mt-[3px] leading-none">
                  {step.sub}
                </div>
                {step.timer && (
                  <div
                    className={`text-[10px] font-mono mt-[4px] leading-none ${step.active ? 'text-accent/70' : 'text-text-tertiary'}`}
                  >
                    {step.active ? '⏱ ' : ''}
                    {step.timer}
                  </div>
                )}
              </div>
            </div>
          </Fragment>
        ))}
      </div>
    </div>
  ) : null

  const sourceCard = run ? (
    <div className="rounded-lg border border-border-subtle bg-bg-surface px-4 py-3 h-full">
      <div className="flex items-stretch gap-6 h-full">
        <div className="flex-1 min-w-0 space-y-2">
          <div className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-tertiary">
            Source Backtest
          </div>
          <div className="text-[17px] font-semibold text-text-primary truncate">
            {run.strategy_name}
          </div>
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
              <div className={`text-[18px] font-semibold font-mono ${pnlCls}`}>
                {dollar(run.net_pnl)}
              </div>
              <div className="text-[10px] text-text-tertiary uppercase tracking-[0.5px]">
                Net P&L
              </div>
            </div>
            <div className="text-right">
              <div className="text-[18px] font-semibold font-mono text-text-primary">
                {run.trade_count ?? '—'}
              </div>
              <div className="text-[10px] text-text-tertiary uppercase tracking-[0.5px]">
                Trades
              </div>
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
          {(scrolled) => (
            <div
              className={`flex items-center justify-between gap-3 ${scrolled ? 'mb-4' : 'mb-5'}`}
            >
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
                    <h1 className="text-[14px] font-semibold truncate">
                      {st.strategy_name || 'Stress Test'}
                    </h1>
                    {st.instrument && (
                      <span className="inline-flex items-center px-1.5 py-[1px] rounded text-[11px] font-semibold font-mono bg-accent/10 text-accent border border-accent/20 flex-shrink-0">
                        {st.instrument}
                      </span>
                    )}
                  </>
                )}
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {/* The third hop of backtest → stress test → demo → live. Offered on a FINISHED
                    test only: a running one's settings are the same, but a control that appears
                    mid-run invites copying a result nobody has read yet. Grade is deliberately
                    NOT a gate — the backend warns on a weak or absent one and still allows it,
                    because blocking would put a legitimately good low-trade config out of reach. */}
                {st.status === 'complete' && (
                  <button
                    onClick={() => setCopySettings(true)}
                    className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium text-text-secondary hover:text-text-primary border border-border-subtle hover:border-border-default transition-colors"
                  >
                    <Upload size={12} />
                    Copy settings to a bot
                  </button>
                )}
                <button
                  onClick={() => setConfirmDelete(true)}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium text-text-tertiary hover:text-neg-text hover:bg-neg-muted border border-transparent hover:border-neg-text/20 transition-colors"
                >
                  <Trash2 size={12} />
                  Delete
                </button>
              </div>
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

        {/* Why this grade — the engine's own reasoning, previously computed and never shown */}
        {reasonsCard}

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

      {copySettings && stressTestId && (
        <SettingsImportModal
          stressTestId={stressTestId}
          strategyName={st.strategy_name}
          grade={st.grade}
          onClose={() => setCopySettings(false)}
        />
      )}

      {confirmDelete && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={() => setConfirmDelete(false)}
        >
          <div
            className="bg-bg-surface border border-border-default rounded-xl p-6 w-full max-w-sm space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-base font-semibold text-text-primary">Delete stress test?</h2>
            <p className="text-sm text-text-secondary">
              This will permanently remove the stress test and all its child runs for{' '}
              <span className="text-text-primary font-medium">{st.strategy_name}</span>. This cannot
              be undone.
            </p>
            <div className="flex gap-2 pt-1">
              <button
                onClick={() =>
                  deleteTest.mutate(st.stress_test_id, { onSuccess: () => navigate(-1) })
                }
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
