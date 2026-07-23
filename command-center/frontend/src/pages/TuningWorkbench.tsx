import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceArea, ReferenceLine,
} from 'recharts'
import { ArrowLeft, Play, RotateCcw, AlertTriangle, Star, Loader2, ChevronLeft, ChevronRight, Maximize2, Minimize2, Camera, Check } from 'lucide-react'
import { copyChartAsPng } from '@/lib/chartImage'
import { balTick, balanceTicks, dateMs, getXMode, monthLabel, monthTicks, regimeBandsByIndex, regimeBandsFromTimeline, setXModePref, tradeTicks, type XMode } from '@/lib/chartAxis'
import { XModeToggle } from '@/components/XModeToggle'
import { RegimeOverlayToggle } from '@/components/RegimeOverlayToggle'
import { useBacktestRun, useStrategy, useBacktestRuns, useTriggerBacktest, useRunningVpsJob, useLabProgress } from '@/hooks/useLab'
import { ParamEditor, ParamCoach, type ParamValue } from '@/components/ParamEditor'
import { useStickyBanner } from '@/components/StickyHeader'
import { api } from '@/api/client'
import { C } from '@/themes/chart'
import { REGIME_COLORS, REGIME_LABEL, REGIME_ORDER } from '@/lib/regime'
import { runnerScope, runningJobFor, RUNNER_LABEL } from '@/lib/runner'
import type { BacktestDetail, BacktestSummary, DailyPnlPoint, ParamSchemaEntry } from '@/types'

// ── Param helpers ───────────────────────────────────────────────────────────────

function isFoundational(schema: ParamSchemaEntry | undefined): boolean {
  return schema?.category === 'foundational'
}

// ── Money / number formatters ─────────────────────────────────────────────────

function money(n: number | null | undefined): string {
  if (n == null) return '—'
  const sign = n >= 0 ? '+' : '-'
  return `${sign}$${Math.round(Math.abs(n)).toLocaleString('en-US')}`
}
function moneyAbs(n: number | null | undefined): string {
  if (n == null) return '—'
  return `$${Math.round(Math.abs(n)).toLocaleString('en-US')}`
}
function pct(n: number | null | undefined): string {
  return n == null ? '—' : `${(n * 100).toFixed(1)}%`
}
// ── Regime bands (shared timeline from the baseline's daily pnl) ────────────────

interface Band { x1: number; x2: number; regime: string }
const ts = (date: string): number => dateMs(date) ?? NaN

// Account balance after each trade, as a timestamp→balance map — straight off the run's own
// equity_curve, the same points the BacktestDetail equity chart plots. Keyed by trade open time
// when the runner reports it, otherwise by the trade's date (several trades closing on one date
// collapse to that date's final balance, which is what a daily curve would have shown anyway).
function balByTime(d: BacktestDetail): Map<number, number> {
  const m = new Map<number, number>()
  for (const p of d.equity_curve) {
    const t = p.entry_ms ?? (p.date ? ts(p.date) : null)
    if (t == null || !Number.isFinite(t)) continue
    m.set(t, p.equity)
  }
  return m
}

// The same curve keyed by TRADE NUMBER, for the Trade # axis. Two runs with different trade counts
// share the axis by ordinal — the shorter one's line simply holds its final balance once it's out
// of trades, which is the honest reading (it was done, the account sat there).
function balByIndex(d: BacktestDetail): Map<number, number> {
  const m = new Map<number, number>()
  for (const p of d.equity_curve) m.set(p.index, p.equity)
  return m
}

// Net pnl per regime for one run.
function pnlByRegime(daily: DailyPnlPoint[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const d of daily) {
    const r = d.regime_tag ?? 'UNKNOWN'
    out[r] = (out[r] ?? 0) + d.pnl
  }
  return out
}

const LINE_PALETTE = ['#d9a441', '#22c55e', '#ec4899', '#a855f7', '#f97316', '#3b82f6', '#14b8a6', '#eab308']

// ── Chart dots ──────────────────────────────────────────────────────────────────

type DotProps = { cx?: number; cy?: number; index?: number; payload?: Record<string, number | boolean> }

// A dot only where the run actually traded (`<id>__pt`), coloured by which side of the starting
// balance it closed on — the forward-filled rows in between are another run's trade days.
function tradeDot(p: DotProps, id: string, startBal: number, r: number) {
  const { cx, cy, payload, index } = p
  if (cx == null || cy == null || !payload?.[`${id}__pt`]) return <g key={index} />
  const up = ((payload[id] as number) ?? 0) >= startBal
  return <circle key={index} cx={cx} cy={cy} r={r} fill={up ? C.pos : C.neg} stroke={C.tooltipBg} strokeWidth={r > 3 ? 1.5 : 1} />
}

// ── Delta cell ──────────────────────────────────────────────────────────────────

function Delta({ value, good }: { value: number | null; good: boolean | null }) {
  if (value == null) return null
  const cls = good == null ? 'text-text-tertiary' : good ? 'text-pos-text' : 'text-neg-text'
  const sign = value > 0 ? '+' : ''
  return <span className={`text-[10px] font-mono ${cls}`}>{sign}{value.toFixed(2)}</span>
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function TuningWorkbench() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()

  const { data: baseline, isLoading } = useBacktestRun(runId ?? null)
  const { data: strategy } = useStrategy(baseline?.strategy_id ?? null)
  const { data: allRuns } = useBacktestRuns()
  const { data: runningJob } = useRunningVpsJob()
  const { data: progress } = useLabProgress()
  const trigger = useTriggerBacktest()

  const [edits, setEdits] = useState<Record<string, ParamValue>>({})
  const [coachParam, setCoachParam] = useState<string | null>(null)
  const [showRegime, setShowRegime] = useState(true)
  // Same stored preference the run page's equity chart uses, so the two never disagree.
  const [xMode, setXMode] = useState<XMode>(getXMode)
  const toggleXMode = (v: XMode) => { setXMode(v); setXModePref(v) }
  const [chartFs, setChartFs] = useState(false)
  const fsChartRef = useRef<HTMLDivElement>(null)
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!chartFs) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setChartFs(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [chartFs])
  const [panelCollapsed, setPanelCollapsed] = useState<boolean>(() => {
    try { return localStorage.getItem('tune_params_panel') === 'collapsed' } catch { return false }
  })
  const togglePanel = () => setPanelCollapsed(c => {
    const next = !c
    try { localStorage.setItem('tune_params_panel', next ? 'collapsed' : 'open') } catch { /* quota */ }
    return next
  })
  const { ref: headerRef, scrolled, height: headerH, collapse } = useStickyBanner()

  const schemaByName = useMemo(() => {
    const m = new Map<string, ParamSchemaEntry>()
    for (const s of strategy?.param_schema ?? []) m.set(s.name, s)
    return m
  }, [strategy])

  // Current editable values = baseline overlaid with the user's edits (typed).
  const values = useMemo(
    () => ({ ...(baseline?.params ?? {}), ...edits }) as Record<string, ParamValue>,
    [baseline, edits],
  )

  const foundational = useMemo(() => {
    if (!baseline) return [] as [string, unknown][]
    return Object.entries(baseline.params).filter(([k]) => isFoundational(schemaByName.get(k)))
  }, [baseline, schemaByName])

  // Iterations = runs derived from this baseline.
  const iterations = useMemo(
    () => (allRuns ?? []).filter(r => r.source_run_id === runId).sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [allRuns, runId],
  )

  // All runs to show in the leaderboard / overlay: baseline first, then iterations.
  const baselineSummary: BacktestSummary | null = useMemo(() => {
    if (!baseline) return null
    return allRuns?.find(r => r.run_id === baseline.run_id) ?? null
  }, [allRuns, baseline])

  const leaderboard = useMemo(() => {
    const rows: BacktestSummary[] = []
    if (baselineSummary) rows.push(baselineSummary)
    rows.push(...iterations)
    return rows
  }, [baselineSummary, iterations])

  const bestPf = useMemo(() => {
    const complete = leaderboard.filter(r => r.status === 'complete' && r.profit_factor != null)
    if (!complete.length) return null
    return complete.reduce((a, b) => (b.profit_factor ?? -Infinity) > (a.profit_factor ?? -Infinity) ? b : a).run_id
  }, [leaderboard])

  // Live single-run progress for the iteration currently running (lab_progress.json).
  const runningIter = leaderboard.find(r => r.status === 'running') ?? null
  const liveJobId = progress?.status === 'running' ? progress.job_id : null

  // Fetch full detail (for daily_pnl) of every complete run, for the overlay + regime breakdown.
  const completeIds = useMemo(
    () => leaderboard.filter(r => r.status === 'complete').map(r => r.run_id),
    [leaderboard],
  )
  const detailQueries = useQueries({
    queries: completeIds.map(id => ({
      queryKey: ['lab', 'run', id],
      queryFn: () => api.get<BacktestDetail>(`/backtests/runs/${id}`),
      staleTime: 60_000,
    })),
  })
  const details = useMemo(
    () => detailQueries.map(q => q.data).filter((d): d is BacktestDetail => !!d),
    [detailQueries],
  )

  // Assign each run a stable color. The baseline line itself is drawn green-above /
  // red-below the starting balance (like the equity chart), so its legend/table swatch is
  // its overall result colour; iterations cycle the palette so they stay distinguishable.
  const colorFor = useMemo(() => {
    const m = new Map<string, string>()
    let i = 0
    for (const r of leaderboard) {
      if (r.run_id === baseline?.run_id) m.set(r.run_id, (r.net_pnl ?? 0) >= 0 ? C.pos : C.neg)
      else m.set(r.run_id, LINE_PALETTE[i++ % LINE_PALETTE.length])
    }
    return m
  }, [leaderboard, baseline])

  const labelFor = (id: string) => (id === baseline?.run_id ? 'Baseline' : `Tweak ${id.slice(0, 6)}`)

  // Overlay dataset — ACCOUNT BALANCE per run, so this chart reads exactly like the equity
  // curve on BacktestDetail: same starting balance on the axis, same break-even reference,
  // same green-above/red-below split on the baseline. (It used to plot cumulative P&L from
  // $0, which meant the y-axis never showed the account's real balance, and each run's line
  // simply began wherever it happened to take its first trade.)
  const chart = useMemo(() => {
    // Source = each run's OWN equity_curve — the exact points the BacktestDetail equity chart
    // draws, balance included. (Re-deriving the curve from daily_pnl gave subtly different
    // vertices, which is why the baseline here didn't trace the same path as on the run page.)
    const byDate = xMode === 'date'
    const series = details
      .map(d => ({ id: d.run_id, bal: byDate ? balByTime(d) : balByIndex(d) }))
      .filter(s => s.bal.size > 0)
    const allTs = new Set<number>()
    series.forEach(s => s.bal.forEach((_, t) => allTs.add(t)))
    if (!allTs.size) return null

    // Starting balance, derived the same way the equity chart does it: the first trade's
    // closing equity minus that trade's own P&L. Prefer the baseline's own curve.
    const startOf = (d: BacktestDetail | undefined): number | null => {
      const p = d?.equity_curve?.[0]
      return p ? (p.equity ?? 0) - (p.profit ?? 0) : null
    }
    const startBal =
      startOf(details.find(d => d.run_id === baseline?.run_id && d.equity_curve?.length))
      ?? startOf(details.find(d => d.equity_curve?.length))
      ?? 0

    // Anchor every line on the run's start date at the starting balance, so they all leave the
    // same point on the left edge instead of each one appearing part-way across the chart.
    const sortedTs = [...allTs].sort((a, b) => a - b)
    // Anchor: the window opening in date mode, "trade 0" in trade mode.
    const anchorTs = byDate ? (baseline ? ts(baseline.start_date) : NaN) : 0
    if (Number.isFinite(anchorTs) && anchorTs < sortedTs[0]) sortedTs.unshift(anchorTs)

    // Forward-fill: a run's balance HOLDS on a day it didn't trade. Leaving nulls and letting
    // `connectNulls` bridge them drew a straight diagonal across flat stretches — a slow bleed
    // or climb that never happened. `<id>__pt` marks the rows that are a REAL trade for that
    // run, so only those get a dot (as on the equity chart, one dot = one trade).
    const last = new Map<string, number>(series.map(s => [s.id, startBal]))
    const data = sortedTs.map(t => {
      const row: Record<string, number | boolean> = { t }
      for (const s of series) {
        const hit = s.bal.has(t)
        if (hit) last.set(s.id, s.bal.get(t)!)
        row[s.id] = last.get(s.id)!
        row[`${s.id}__pt`] = hit
      }
      return row
    })

    const stats = new Map<string, { min: number; max: number; end: number }>()
    for (const s of series) {
      const vals = data.map(r => r[s.id] as number)
      stats.set(s.id, { min: Math.min(...vals), max: Math.max(...vals), end: vals[vals.length - 1] })
    }
    const lows = [...stats.values()].map(v => v.min)
    const highs = [...stats.values()].map(v => v.max)
    const min = Math.min(startBal, ...lows)
    const max = Math.max(startBal, ...highs)
    const pad = (max - min) * 0.1 || 500
    const yMin = min - pad
    const yMax = max + pad

    // Ticks anchored ON the starting balance so it's always labelled — as on the equity chart.
    const yTicks = balanceTicks(startBal, yMin, yMax)

    // Green/red split offset — same math as BacktestDetail: mapped to the FILLED shape's
    // bounding box (data extremes INCLUDING the starting balance, since the area is anchored
    // there), never the padded axis domain, or the colour flip drifts off the break-even line.
    const bStats = stats.get(baseline?.run_id ?? '')
    const dMin = Math.min(startBal, bStats?.min ?? startBal)
    const dMax = Math.max(startBal, bStats?.max ?? startBal)
    const split = Math.min(1, Math.max(0, (dMax - startBal) / ((dMax - dMin) || 1)))

    // Regime bands come from the FULL-CALENDAR timeline (every trading day in the window,
    // classified server-side), not from the days a run happened to trade — regime is a property of
    // the market on a date. The baseline's timeline is the one truth here, and it's the same list
    // BacktestDetail bands from, which is what makes the two charts agree.
    // Fallback for runs completed before the backend emitted a timeline: merge whatever tagged
    // days the loaded runs do carry, so the chart isn't left blank.
    const dateToRegime = new Map<string, string>()
    const withTimeline = details.find(d => d.run_id === baseline?.run_id && d.regime_timeline?.length)
      ?? details.find(d => d.regime_timeline?.length)
    if (withTimeline) {
      for (const d of withTimeline.regime_timeline) dateToRegime.set(d.date, d.regime)
    } else {
      for (const d of details) for (const p of d.daily_pnl) if (p.regime_tag) dateToRegime.set(p.date, p.regime_tag)
    }
    const baseCurve = details.find(d => d.run_id === baseline?.run_id)?.equity_curve ?? []
    const bands: Band[] = byDate
      ? regimeBandsFromTimeline([...dateToRegime.entries()].map(([date, regime]) => ({ date, regime })))
      : regimeBandsByIndex(baseCurve, dateToRegime)
    // Stretch the first/last band to the chart edges so there's no uncoloured margin.
    if (bands.length) {
      bands[0].x1 = Math.min(bands[0].x1, sortedTs[0])
      bands[bands.length - 1].x2 = Math.max(bands[bands.length - 1].x2, sortedTs[sortedTs.length - 1])
    }

    return {
      data, bands, startBal, split,
      yDomain: [yMin, yMax] as [number, number],
      yTicks,
      byDate,
      xTicks: byDate
        ? monthTicks(sortedTs[0], sortedTs[sortedTs.length - 1])
        : tradeTicks(sortedTs[sortedTs.length - 1]),
    }
  }, [details, baseline, xMode])

  const overlayData = chart?.data ?? []

  // Per-regime net pnl per run.
  const regimeMatrix = useMemo(() => {
    const byRun = new Map<string, Record<string, number>>()
    for (const d of details) byRun.set(d.run_id, pnlByRegime(d.daily_pnl))
    const regimes = REGIME_ORDER.filter(r => details.some(d => byRun.get(d.run_id)?.[r] != null))
    return { byRun, regimes }
  }, [details])

  if (isLoading || !baseline) {
    return <div className="text-[13px] text-text-tertiary py-20 text-center">Loading run…</div>
  }

  const jobBlocked = !!runningJobFor(runningJob, baseline.runner)?.running
  const rulesetIds = baseline.evaluations.map(e => e.ruleset_id)

  const baseParams = baseline.params as Record<string, unknown>
  const dirtyKeys = Object.keys(edits).filter(k => String(edits[k]) !== String(baseParams[k]))
  const isDirty = dirtyKeys.length > 0

  const onChangeParam = (name: string, value: ParamValue) => setEdits(prev => ({ ...prev, [name]: value }))
  const resetParams = () => setEdits({})

  const runIteration = () => {
    const params: Record<string, unknown> = { ...baseline.params, ...edits }
    trigger.mutate({
      strategy_id:         baseline.strategy_id,
      instrument:          baseline.instrument,
      params,
      bar_type:            baseline.bar_type,
      bar_value:           baseline.bar_value,
      start_date:          baseline.start_date,
      end_date:            baseline.end_date,
      commission_per_side: baseline.commission_per_side,
      slippage_ticks:      baseline.slippage_ticks,
      evaluate_rulesets:   rulesetIds,
      source_run_id:       baseline.run_id,
    }, {
      onSuccess: () => setEdits({}),
    })
  }

  const baseMetric = (k: 'net_pnl' | 'profit_factor' | 'max_drawdown') => baselineSummary?.[k] ?? null

  const copyChart = async () => {
    if (await copyChartAsPng(fsChartRef.current)) {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    }
  }

  // Equity overlay chart, rendered at a given height (reused inline + fullscreen).
  // The baseline is drawn as the SAME object BacktestDetail draws — a monotone Area anchored on
  // the starting balance with the split stroke + fill — so the two charts trace an identical
  // path. Iterations ride on top as dashed lines (they need to stay tellable apart).
  const renderOverlay = (height: number) => chart && (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={chart.data} margin={{ top: 8, right: 12, bottom: 0, left: 4 }}>
        <defs>
          {/* Baseline stroke: green above the starting balance, red below, hard edge at the split. */}
          <linearGradient id="tuneBaseStroke" x1="0" y1="0" x2="0" y2="1">
            <stop offset={chart.split} stopColor={C.pos} />
            <stop offset={chart.split} stopColor={C.neg} />
          </linearGradient>
          {/* Fill: green above the start line, red below, hard edge at the same offset. */}
          <linearGradient id="tuneBaseFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset={0} stopColor={C.pos} stopOpacity={0.22} />
            <stop offset={Math.max(0, chart.split - 0.0001)} stopColor={C.pos} stopOpacity={0.03} />
            <stop offset={chart.split} stopColor={C.neg} stopOpacity={0.03} />
            <stop offset={1} stopColor={C.neg} stopOpacity={0.20} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} vertical={false} />
        {showRegime && chart.bands.map((b, i) => (
          <ReferenceArea key={i} x1={b.x1} x2={b.x2} ifOverflow="visible"
            fill={REGIME_COLORS[b.regime] ?? REGIME_COLORS.UNKNOWN} fillOpacity={0.1} stroke="none" />
        ))}
        <XAxis
          dataKey="t" type="number" domain={['dataMin', 'dataMax']}
          {...(chart.byDate ? { scale: 'time' as const } : {})}
          ticks={chart.xTicks}
          tickFormatter={(v: number) => (chart.byDate ? monthLabel(v) : `#${v}`)}
          tick={{ fill: C.axisTick, fontSize: 10 }} axisLine={false} tickLine={false}
        />
        <YAxis
          domain={chart.yDomain} ticks={chart.yTicks} tickFormatter={balTick}
          tick={{ fill: C.axisTick, fontSize: 10 }} axisLine={false} tickLine={false} width={56}
        />
        <Tooltip
          contentStyle={{ background: C.tooltipBg, border: `1px solid ${C.tooltipBorder}`, borderRadius: 8, fontSize: 12, padding: '8px 12px' }}
          labelStyle={{ color: C.axisTick }}
          itemStyle={{ color: '#e5e7eb' }}
          labelFormatter={t => (chart.byDate
            ? new Date(t as number).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
            : `Trade #${t}`)}
          // Balance first, then the gain on the account so far — the two numbers a comparison needs.
          formatter={(v: number, name: string) => [`${balTick(v)}  (${money(v - chart.startBal)})`, labelFor(name)]}
        />
        {/* Break-even = the starting balance, same dashed reference as the equity chart. */}
        <ReferenceLine y={chart.startBal} stroke={C.refLine} strokeDasharray="4 4" />
        {/* Baseline first so its translucent fill can't wash out the iteration lines on top. */}
        <Area
          type="monotone" dataKey={baseline.run_id} isAnimationActive={false}
          stroke="url(#tuneBaseStroke)" strokeWidth={2.5} fill="url(#tuneBaseFill)"
          baseValue={chart.startBal}
          // One dot per actual trade (not per forward-filled row), coloured by which side of the
          // starting balance it landed — exactly as on the equity chart.
          dot={(p: DotProps) => tradeDot(p, baseline.run_id, chart.startBal, 3)}
          activeDot={(p: DotProps) => tradeDot(p, baseline.run_id, chart.startBal, 4.5)}
        />
        {completeIds.filter(id => id !== baseline.run_id).map(id => (
          <Line
            key={id} type="monotone" dataKey={id} isAnimationActive={false}
            stroke={colorFor.get(id)} strokeWidth={1.5} dot={false} strokeDasharray="4 2"
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  )

  return (
    <div className="-m-[22px] flex flex-col min-h-[calc(100vh-56px)]">
      <div
        ref={headerRef}
        className={`sticky -top-[22px] z-30 bg-bg-base px-[22px] pt-[22px] transition-[padding] duration-200 ${scrolled ? 'pb-3 shadow-[0_10px_18px_-14px_rgba(0,0,0,0.8)]' : 'pb-4'}`}
      >
      {/* Header — condenses to a single row once scrolled */}
      {scrolled ? (
        <div className="flex items-center gap-2 text-[13px] min-w-0">
          <button
            onClick={() => navigate(`/backtests/runs/${baseline.run_id}`)}
            title="Back to run"
            className="flex items-center text-text-tertiary hover:text-text-secondary transition-colors flex-shrink-0"
          >
            <ArrowLeft size={14} />
          </button>
          <span className="font-semibold text-[14px] flex-shrink-0">Tune Parameters</span>
          <span className="text-text-tertiary flex-shrink-0">·</span>
          <span className="font-semibold text-text-secondary truncate flex-shrink min-w-0">{baseline.strategy_name}</span>
          <span className="font-semibold font-mono bg-accent/10 text-accent border border-accent/20 px-1.5 py-[1px] rounded text-[11px] flex-shrink-0">{baseline.instrument}</span>
          <span className="font-medium font-mono bg-bg-surface border border-border-subtle text-text-secondary px-1.5 py-[1px] rounded text-[11px] flex-shrink-0 max-[1100px]:hidden">{baseline.start_date} → {baseline.end_date}</span>
          {rulesetIds.length > 0 && (
            <span className="font-semibold font-mono bg-warn-muted border border-warn-text/20 text-warn-text px-1.5 py-[1px] rounded text-[11px] flex-shrink-0 max-[900px]:hidden">{rulesetIds.join(', ')}</span>
          )}
        </div>
      ) : (
        <>
          <button
            onClick={() => navigate(`/backtests/runs/${baseline.run_id}`)}
            className="flex items-center gap-1.5 text-[12px] text-text-tertiary hover:text-text-secondary transition-colors mb-3"
          >
            <ArrowLeft size={13} /> Back to run
          </button>
          <div className="flex items-baseline gap-3 mb-2">
            <h1 className="text-h1 font-semibold">Tune Parameters</h1>
            <span className="text-[15px] font-semibold text-text-secondary">{baseline.strategy_name}</span>
          </div>
          <div className="flex items-center gap-1.5 mb-5 flex-wrap text-[12px]">
            <span className="font-semibold font-mono bg-accent/10 text-accent border border-accent/20 px-2 py-[2px] rounded">{baseline.instrument}</span>
            <span className="font-medium font-mono bg-bg-surface border border-border-subtle text-text-secondary px-2 py-[2px] rounded">{baseline.start_date} → {baseline.end_date}</span>
            {rulesetIds.length > 0 ? (
              rulesetIds.map(id => (
                <span key={id} className="font-semibold font-mono bg-warn-muted border border-warn-text/20 text-warn-text px-2 py-[2px] rounded">{id}</span>
              ))
            ) : (
              <span className="font-medium font-mono bg-bg-surface border border-border-subtle text-text-tertiary px-2 py-[2px] rounded">No ruleset</span>
            )}
          </div>
        </>
      )}
      </div>

      <div className="flex items-stretch flex-1 min-h-0">

        {/* ── Param editor — full-height dockable side column (mirrors BacktestDetail) ── */}
        <div className={`flex-shrink-0 bg-bg-surface border-r border-border-subtle transition-[width] duration-200 ${panelCollapsed ? 'w-[44px]' : 'w-[440px]'}`}>
          <div className="sticky flex flex-col" style={{ top: Math.max(headerH - 22, 0), maxHeight: `calc(100vh - 56px - ${headerH}px)` }}>
            {panelCollapsed ? (
              <button
                onClick={togglePanel}
                title="Show parameters"
                className="w-full flex flex-col items-center gap-2.5 py-4 hover:bg-bg-hover transition-colors"
              >
                <ChevronRight size={14} className="text-text-tertiary" />
                <span className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-tertiary [writing-mode:vertical-rl]">Parameters</span>
                {dirtyKeys.length > 0 && <span className="w-[6px] h-[6px] rounded-full bg-accent" title={`${dirtyKeys.length} changed`} />}
              </button>
            ) : (
              <>
                <div className="px-[13px] py-[10px] border-b border-border-subtle flex items-center justify-between flex-shrink-0">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary flex items-center gap-2">
                    Parameters
                    {dirtyKeys.length > 0 && <span className="text-accent normal-case tracking-normal font-medium">· {dirtyKeys.length} changed</span>}
                  </span>
                  <div className="flex items-center gap-3">
                    <button onClick={resetParams} disabled={!isDirty}
                      className="flex items-center gap-1 text-[11px] text-text-tertiary hover:text-text-secondary transition-colors disabled:opacity-30 disabled:cursor-not-allowed">
                      <RotateCcw size={11} /> Reset
                    </button>
                    <button onClick={togglePanel} title="Collapse" className="text-text-tertiary hover:text-text-secondary">
                      <ChevronLeft size={15} />
                    </button>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto px-1.5 py-2">
                  <ParamEditor
                    schema={strategy?.param_schema ?? []}
                    mode="tune"
                    explainer="coach"
                    values={values}
                    onChange={onChangeParam}
                    onFocusChange={setCoachParam}
                    baseline={baseParams}
                  />
                  {foundational.length > 0 && (
                    <details className="mt-2.5 px-2.5">
                      <summary className="text-[11px] text-text-tertiary cursor-pointer select-none">Foundational config (read-only) · {foundational.length}</summary>
                      <div className="mt-2 space-y-[5px]">
                        {foundational.map(([k, v]) => (
                          <div key={k} className="flex items-center justify-between text-[11px]">
                            <span className="font-mono text-text-tertiary truncate" title={k}>{k}</span>
                            <span className="font-mono text-text-secondary">{String(v)}</span>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>

                {/* Pinned coach — always-on guidance for the focused param; rows above never shift */}
                <div className="px-[13px] py-[11px] border-t border-border-subtle flex-shrink-0 bg-gradient-to-b from-accent/[0.04] to-transparent">
                  <ParamCoach schema={strategy?.param_schema ?? []} values={values} focusName={coachParam} />
                </div>

                <div className="px-[13px] py-[11px] border-t border-border-subtle flex-shrink-0">
                  {jobBlocked && (
                    <div className="flex items-start gap-2 mb-2 px-2.5 py-2 rounded-md bg-warn-muted/40 border border-warn-text/20">
                      <AlertTriangle size={12} className="text-warn-text flex-shrink-0 mt-[1px]" />
                      <p className="text-[11px] text-warn-text leading-snug">{RUNNER_LABEL[runnerScope(baseline.runner)]} is busy — wait for the current job to finish.</p>
                    </div>
                  )}
                  <button
                    onClick={runIteration}
                    disabled={!isDirty || jobBlocked || trigger.isPending}
                    className="w-full flex items-center justify-center gap-1.5 bg-accent text-bg-base font-semibold text-[12px] py-2 rounded-md hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
                  >
                    <Play size={13} />
                    {trigger.isPending ? 'Starting…' : isDirty ? `Run with ${dirtyKeys.length} change${dirtyKeys.length !== 1 ? 's' : ''}` : 'Change a param to run'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        {/* ── Results (the hero) — no top padding so ITERATIONS lines up with PARAMETERS ── */}
        <div className="flex-1 min-w-0 space-y-[14px] px-[22px] pb-[22px]">

          {/* Leaderboard */}
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
            <div className="px-[15px] py-[10px] border-b border-border-subtle flex items-baseline justify-between gap-3">
              <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">Iterations ({leaderboard.length})</span>
              <span className="text-[11px] text-text-tertiary">Ranked by profit factor · <Star size={9} className="inline text-gold-text" fill="currentColor" /> best · Δ vs baseline</span>
            </div>

            {/* Live progress for the running iteration — watch it here, no need to leave */}
            {runningIter && (
              <button
                onClick={() => navigate(`/backtests/runs/${runningIter.run_id}`)}
                className="w-full text-left px-[15px] py-[9px] border-b border-border-subtle bg-accent/5 hover:bg-accent/10 transition-colors"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2 text-[12px] text-accent min-w-0">
                    <Loader2 size={13} className="animate-spin flex-shrink-0" />
                    <span className="truncate">
                      Running {labelFor(runningIter.run_id)}
                      {liveJobId === runningIter.run_id && progress ? ` — ${progress.pct}% · ${progress.message}` : '…'}
                    </span>
                  </div>
                  <span className="text-[11px] text-text-tertiary flex-shrink-0">View log →</span>
                </div>
                {liveJobId === runningIter.run_id && progress && (
                  <div className="mt-1.5 w-full bg-bg-sunken rounded-full h-[4px] overflow-hidden">
                    <div className="h-full bg-accent transition-all duration-700" style={{ width: `${progress.pct}%` }} />
                  </div>
                )}
              </button>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="border-b border-border-subtle bg-bg-sunken">
                    <th className="text-left px-3 py-2 text-text-tertiary font-medium w-6" />
                    <th className="text-left px-3 py-2 text-text-tertiary font-medium">Run</th>
                    <th className="text-left px-3 py-2 text-text-tertiary font-medium">Net P&L</th>
                    <th className="text-left px-3 py-2 text-text-tertiary font-medium">Max DD</th>
                    <th className="text-left px-3 py-2 text-text-tertiary font-medium">PF</th>
                    <th className="text-left px-3 py-2 text-text-tertiary font-medium">Win%</th>
                    <th className="text-left px-3 py-2 text-text-tertiary font-medium">Trades</th>
                    <th className="text-left px-3 py-2 text-text-tertiary font-medium">Changes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {leaderboard.map(r => {
                    const isBaseline = r.run_id === baseline.run_id
                    const isBest = r.run_id === bestPf
                    const changes = Object.entries(r.params || {}).filter(([k, v]) => {
                      if (isBaseline || isFoundational(schemaByName.get(k))) return false
                      return String(v) !== String(baseline.params[k])
                    })
                    const pnlDelta = !isBaseline && r.net_pnl != null && baseMetric('net_pnl') != null ? r.net_pnl - (baseMetric('net_pnl') as number) : null
                    const pfDelta  = !isBaseline && r.profit_factor != null && baseMetric('profit_factor') != null ? r.profit_factor - (baseMetric('profit_factor') as number) : null
                    const ddDelta  = !isBaseline && r.max_drawdown != null && baseMetric('max_drawdown') != null ? r.max_drawdown - (baseMetric('max_drawdown') as number) : null
                    return (
                      <tr
                        key={r.run_id}
                        onClick={() => navigate(`/backtests/runs/${r.run_id}`)}
                        className={`hover:bg-bg-hover cursor-pointer transition-colors [&>td]:align-top ${isBest ? 'bg-gold-muted/10' : ''}`}
                      >
                        <td className="px-3 py-[9px]">
                          <span className="inline-block w-[10px] h-[10px] rounded-full" style={{ background: colorFor.get(r.run_id) }} />
                        </td>
                        <td className="px-3 py-[9px] font-medium whitespace-nowrap">
                          <span className="flex items-center gap-1.5">
                            {isBest && <Star size={11} className="text-gold-text" fill="currentColor" />}
                            {isBaseline ? 'Baseline' : labelFor(r.run_id)}
                            {r.status === 'running' && (
                              <span className="text-[10px] text-accent">· running{liveJobId === r.run_id && progress ? ` ${progress.pct}%` : ''}</span>
                            )}
                            {r.status.startsWith('failed') && <span className="text-[10px] text-neg-text">· failed</span>}
                          </span>
                        </td>
                        <td className="px-3 py-[9px] font-mono tabular-nums">
                          <span className={(r.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'}>{money(r.net_pnl)}</span>
                          {pnlDelta != null && <span className="ml-1.5"><Delta value={pnlDelta} good={pnlDelta >= 0} /></span>}
                        </td>
                        <td className="px-3 py-[9px] font-mono tabular-nums text-neg-text">
                          {moneyAbs(r.max_drawdown)}
                          {ddDelta != null && Math.abs(ddDelta) >= 1 && <span className="ml-1.5"><Delta value={ddDelta} good={ddDelta <= 0} /></span>}
                        </td>
                        <td className="px-3 py-[9px] font-mono tabular-nums">
                          {r.profit_factor?.toFixed(2) ?? '—'}
                          {pfDelta != null && <span className="ml-1.5"><Delta value={pfDelta} good={pfDelta >= 0} /></span>}
                        </td>
                        <td className="px-3 py-[9px] font-mono tabular-nums text-text-secondary">{pct(r.win_rate)}</td>
                        <td className="px-3 py-[9px] font-mono tabular-nums text-text-secondary">{r.trade_count ?? '—'}</td>
                        <td className="px-3 py-[9px] text-[11px] font-mono align-top">
                          {isBaseline ? <span className="text-text-tertiary">—</span>
                            : changes.length === 0 ? <span className="text-text-tertiary">none</span> : (
                              <div className="flex flex-col gap-[2px]">
                                {changes.map(([k, v]) => (
                                  <span key={k} className="whitespace-nowrap">
                                    <span className="text-text-tertiary">{schemaByName.get(k)?.label || k} </span>
                                    <span className="text-text-tertiary line-through">{String(baseline.params[k])}</span>
                                    <span className="text-accent">→{String(v)}</span>
                                  </span>
                                ))}
                              </div>
                            )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Equity overlay */}
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
            <div className="px-[15px] py-[10px] border-b border-border-subtle flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">Equity overlay</span>
              <div className="flex items-center gap-2">
                <XModeToggle value={xMode} onChange={toggleXMode} />
                <RegimeOverlayToggle on={showRegime} onChange={setShowRegime} />
                {overlayData.length > 0 && (
                  <button onClick={() => setChartFs(true)} title="Fullscreen"
                    className="flex items-center gap-1 text-[11px] text-text-tertiary hover:text-text-secondary transition-colors">
                    <Maximize2 size={13} />
                  </button>
                )}
              </div>
            </div>
            <div className="px-[10px] py-[12px]">
              {overlayData.length === 0 ? (
                <p className="text-[12px] text-text-tertiary text-center py-12">No completed runs to chart yet. Tweak a param and run an iteration.</p>
              ) : (
                <>
                  {renderOverlay(440)}
                  {/* Legend */}
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 px-2">
                    {completeIds.map(id => (
                      <span key={id} className="flex items-center gap-1.5 text-[11px] text-text-tertiary">
                        <span className="w-3 h-[2px]" style={{ background: colorFor.get(id) }} />
                        {labelFor(id)}
                      </span>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Per-regime comparison */}
          {regimeMatrix.regimes.length > 0 && details.length > 0 && (
            <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
              <div className="px-[15px] py-[10px] border-b border-border-subtle">
                <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">Net P&L by regime</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-border-subtle bg-bg-sunken">
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Regime</th>
                      {completeIds.map(id => (
                        <th key={id} className="text-left px-3 py-2 text-text-tertiary font-medium whitespace-nowrap">
                          <span className="flex items-center gap-1.5">
                            <span className="w-[8px] h-[8px] rounded-full" style={{ background: colorFor.get(id) }} />
                            {labelFor(id)}
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {regimeMatrix.regimes.map(rg => (
                      <tr key={rg}>
                        <td className="px-3 py-[8px]">
                          <span className="flex items-center gap-1.5">
                            <span className="w-[10px] h-[10px] rounded-sm" style={{ background: REGIME_COLORS[rg] }} />
                            <span className="text-text-secondary">{REGIME_LABEL[rg] ?? rg}</span>
                          </span>
                        </td>
                        {completeIds.map(id => {
                          const v = regimeMatrix.byRun.get(id)?.[rg]
                          return (
                            <td key={id} className={`px-3 py-[8px] font-mono tabular-nums ${v == null ? 'text-text-tertiary' : v >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>
                              {v == null ? '—' : money(v)}
                            </td>
                          )
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Holds total scroll height constant while the banner is condensed (see useStickyBanner) so
          scrollTop is never clamped — that clamp is what made the condense flicker on this page. */}
      <div aria-hidden className="flex-shrink-0" style={{ height: collapse }} />

      {/* Fullscreen equity overlay */}
      {chartFs && (
        <div className="fixed inset-0 z-50 bg-bg-base flex flex-col">
          <div className="flex items-center justify-between px-5 py-3 border-b border-border-subtle flex-shrink-0">
            <span className="text-[12px] font-semibold uppercase tracking-[0.7px] text-text-secondary">Equity overlay — {baseline.strategy_name} · {baseline.instrument}</span>
            <div className="flex items-center gap-2">
              <XModeToggle value={xMode} onChange={toggleXMode} />
              <RegimeOverlayToggle on={showRegime} onChange={setShowRegime} />
              <button onClick={copyChart} title={copied ? 'Copied' : 'Copy chart image to clipboard'}
                className="text-text-tertiary hover:text-text-primary transition-colors">
                {copied ? <Check size={18} className="text-accent" /> : <Camera size={18} />}
              </button>
              <button onClick={() => setChartFs(false)} title="Minimize (Esc)" className="text-text-tertiary hover:text-text-primary transition-colors">
                <Minimize2 size={18} />
              </button>
            </div>
          </div>
          <div ref={fsChartRef} className="flex-1 min-h-0 px-5 py-4">
            {renderOverlay(Math.max(300, window.innerHeight - 120))}
          </div>
        </div>
      )}
    </div>
  )
}
