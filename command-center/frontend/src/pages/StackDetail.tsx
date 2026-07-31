import { useMemo, useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, Loader2, XCircle, Layers, Trash2, Square, Play } from 'lucide-react'
import StickyHeader from '@/components/StickyHeader'
import { useStack, useDeleteStack, useCancelStack, useStackChartSpec, useRunCandles } from '@/hooks/useLab'
import { ChartTabPanel, ChartModal } from '@/components/ChartTabPanel'
import { StackConfigModal } from '@/components/StackConfigModal'
import { XModeToggle } from '@/components/XModeToggle'
import { RegimeOverlayToggle } from '@/components/RegimeOverlayToggle'
import { getXMode, setXModePref, regimeBandsFromTimeline, regimeBandsByIndex, type XMode } from '@/lib/chartAxis'
import {
  PerformancePanel, computeFallbacks, worstLosingStreakOf, EquityCurveChart, DrawdownChart, DailyPnlChart,
  DirectionBreakdown, PriceChartView, SeriesToggle, type FallbackMetrics,
} from '@/pages/BacktestDetail'
import { C } from '@/themes/chart'
import type { StackStrategyLeg, BacktestDetail as RunDetail, EquityPoint, DailyPnlPoint } from '@/types'

// ── Formatters ────────────────────────────────────────────────────────────────

// Local midnight, not UTC — a bare 'YYYY-MM-DD' otherwise renders a day early west of
// Greenwich. Same fix in BacktestDetail/SweepDetail/OptimizationDetail/StressTestDetail.
function fmtDate(iso: string) {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
function fmtMoney(v: number, signed = true): string {
  const sign = v >= 0 ? (signed ? '+' : '') : '-'
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}
function dateMsOf(s?: string): number { return s ? new Date(s).getTime() : 0 }

// Strategy-line palette. Deliberately EXCLUDES C.pos/C.neg — the portfolio line is C.pos, so a leg
// must never be able to draw in the same green (or in the loss red).
const LEG_COLORS = C.series.filter(c => c !== C.pos && c !== C.neg)

// ── Combined-portfolio payload ─────────────────────────────────────────────────
// A stack IS a portfolio: the union of its enabled legs' trades over one shared account. From that
// we synthesize a single backtest-shaped `run` + a portfolio equity curve, so StackDetail can reuse
// BacktestDetail's exact KpiGrid and chart components — pixel-identical KPIs and charts. Recomputes
// on every toggle (client-side, no re-backtest).

// The overlay-tagged equity point: a portfolio trade that ALSO carries each leg's running balance
// as a `leg_<id>` field, so the real EquityCurveChart can draw a line per strategy on the same axis.
// `_legOwner` names the overlay line this point's trade actually belongs to, so each strategy line
// dots only on its OWN trades (every point carries every leg's balance).
type ComboPoint = EquityPoint & { _legOwner?: string } & Partial<Record<`leg_${string}`, number>>

interface Combined {
  run: RunDetail
  equity: ComboPoint[]
  dailyPnl: DailyPnlPoint[]
  perLegCounts: { strategy_id: string; strategy_name: string; count: number }[]
  balance: number
  fallback: FallbackMetrics
  hasResults: boolean
  hasDirection: boolean
  activeCount: number
  completeCount: number
}

function composeCombined(legs: StackStrategyLeg[], enabled: Set<string>): Combined {
  const active = legs.filter(l => enabled.has(l.strategy_id) && l.status === 'complete')

  // Portfolio daily P&L = per-date sum across enabled legs.
  const dailyMap = new Map<string, number>()
  for (const leg of active) for (const d of leg.daily_pnl) dailyMap.set(d.date, (dailyMap.get(d.date) ?? 0) + d.pnl)
  const dailyPnl: DailyPnlPoint[] = Array.from(dailyMap.entries())
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([date, pnl]) => ({ date, pnl }))

  // ONE shared account. Every leg was backtested against the SAME opening balance, so the portfolio
  // starts THERE — not at the sum of the legs. Summing showed $20k for two legs of a $10k account and
  // halved every balance-relative KPI. (A stack configures all legs together so their starts agree;
  // max is the safe pick if a reused run ever carried a different one.)
  const legStart = new Map<string, number>()
  for (const leg of active) {
    const e0 = leg.equity_curve[0]
    legStart.set(leg.strategy_id, e0 ? (e0.equity ?? 0) - (e0.profit ?? 0) : 10_000)
  }
  const balance = legStart.size ? Math.max(...legStart.values()) : 10_000

  // Union of every leg's trades in time order → one portfolio equity curve. Each point also records
  // EVERY leg's running balance (the overlay lines), so a strategy's line rides the same x-axis.
  const tagged = active.flatMap(l => l.equity_curve.filter(p => p.direction).map(p => ({ p, legId: l.strategy_id })))
  tagged.sort((a, b) => (a.p.entry_ms ?? dateMsOf(a.p.date)) - (b.p.entry_ms ?? dateMsOf(b.p.date)))
  // Every strategy line starts on the SAME point as the portfolio line (the combined opening
  // balance) and then rides its own cumulative P&L — "what this leg alone did to the account".
  // Starting each leg at its own 10k slice would draw the lines below the portfolio's start line.
  const legBal = new Map<string, number>(active.map(l => [l.strategy_id, balance]))
  let bal = balance
  const equity: ComboPoint[] = tagged.map(({ p, legId }, i) => {
    bal += p.profit ?? 0
    legBal.set(legId, legBal.get(legId)! + (p.profit ?? 0))
    const pt: ComboPoint = {
      index: i + 1, equity: Number(bal.toFixed(2)), date: p.date, entry_ms: p.entry_ms,
      direction: p.direction, profit: p.profit, favorable: p.favorable, adverse: p.adverse, exit_name: p.exit_name,
      _legOwner: `leg_${legId}`,
    }
    for (const leg of active) pt[`leg_${leg.strategy_id}`] = Number(legBal.get(leg.strategy_id)!.toFixed(2))
    return pt
  })

  const perLegCounts = active.map(l => ({
    strategy_id: l.strategy_id,
    strategy_name: l.strategy_name,
    count: l.equity_curve.filter(p => p.direction).length,
  }))

  // KPIs from the union of trades.
  const trades = tagged.map(t => t.p)
  const profits = trades.map(t => t.profit ?? 0)
  const wins = profits.filter(p => p > 0)
  const losses = profits.filter(p => p < 0)
  const grossWin = wins.reduce((a, b) => a + b, 0)
  const grossLoss = Math.abs(losses.reduce((a, b) => a + b, 0))
  const net = profits.reduce((a, b) => a + b, 0)
  const winRate = trades.length ? wins.length / trades.length : null
  // No losing trade = no denominator, not unknown: report ∞ so the card matches a single backtest.
  const pf = grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : null)
  const avgWin = wins.length ? grossWin / wins.length : null
  const avgLoss = losses.length ? losses.reduce((a, b) => a + b, 0) / losses.length : null

  // Portfolio dollar drawdown (peak-to-trough of the combined equity).
  let peak = -Infinity, maxDd = 0
  for (const e of equity) { peak = Math.max(peak, e.equity); maxDd = Math.max(maxDd, peak - e.equity) }

  // Portfolio avg trade duration = each leg's own average weighted by how many trades it contributed
  // (legs that never reported a duration sit out of both sums rather than dragging it to zero).
  const durLegs = active.filter(l => l.avg_trade_duration_min != null)
  const durTrades = durLegs.reduce((a, l) => a + l.equity_curve.filter(p => p.direction).length, 0)
  const avgDuration = durTrades > 0
    ? durLegs.reduce((a, l) => a + l.avg_trade_duration_min! * l.equity_curve.filter(p => p.direction).length, 0) / durTrades
    : null

  // Sharpe comes from computeFallbacks — this was a third private copy of the formula, and like
  // the one in computeFallbacks it scored only the days that traded, so a stack printed 13.06.
  // Flat weekdays are real observations; the shared helper zero-fills them the way the backend does.
  const fallback = computeFallbacks(dailyPnl)

  // Synthetic backtest-shaped run carrying exactly the fields KpiGrid reads.
  const run = {
    net_pnl: net,
    trade_count: trades.length,
    win_rate: winRate,
    profit_factor: pf,
    avg_win: avgWin,
    avg_loss: avgLoss,
    max_drawdown: maxDd || null,
    sharpe: fallback.sharpe,
    platform_sharpe: null,
    sharpe_low_sample: dailyPnl.length < 10 ? 1 : 0,
    worst_day_pnl: fallback.worstDay,
    // Counted off the portfolio's TRADES, which is the unit the row is labelled in. `profits` is
    // in entry order (tagged is sorted above), which a streak requires.
    worst_losing_streak: worstLosingStreakOf(profits),
    avg_trade_duration_min: avgDuration,
    profit_concentration_pct: null,
    daily_pnl: dailyPnl,
  } as unknown as RunDetail

  return {
    run, equity, dailyPnl, perLegCounts, balance, fallback,
    hasResults: dailyPnl.length > 0,
    hasDirection: trades.some(t => t.direction),
    activeCount: active.length,
    completeCount: legs.filter(l => l.status === 'complete').length,
  }
}

// Equity-chart legend — the combined curve + a swatch per enabled strategy line.
function StackEquityLegend({ activeLegs, colorFor }: { activeLegs: StackStrategyLeg[]; colorFor: (id: string) => string }) {
  return (
    <div className="flex items-center gap-4 mb-1 flex-wrap">
      <span className="flex items-center gap-1.5 text-[11px] text-text-tertiary">
        <span className="w-4 h-[2.5px] rounded" style={{ background: C.pos }} /> Portfolio
      </span>
      {activeLegs.map(leg => (
        <span key={leg.strategy_id} className="flex items-center gap-1.5 text-[11px] text-text-tertiary">
          <span className="w-4 h-[2px] rounded" style={{ background: colorFor(leg.strategy_id) }} />
          {leg.strategy_name}
        </span>
      ))}
    </div>
  )
}

// ── Toggle chips ──────────────────────────────────────────────────────────────

function StrategyChips({ legs, enabled, colorFor, onToggle }: {
  legs: StackStrategyLeg[]
  enabled: Set<string>
  colorFor: (id: string) => string
  onToggle: (id: string) => void
}) {
  const activeCount = legs.filter(l => enabled.has(l.strategy_id)).length
  return (
    <div className="flex flex-wrap gap-2">
      {legs.map(leg => {
        const on = enabled.has(leg.strategy_id)
        const isLastOn = on && activeCount === 1
        const done = leg.status === 'complete'
        const failed = leg.status.startsWith('failed')
        return (
          <button
            key={leg.strategy_id}
            onClick={() => !isLastOn && done && onToggle(leg.strategy_id)}
            disabled={isLastOn || !done}
            title={
              !done ? (failed ? (leg.error_message ?? 'This run failed') : 'Still running…')
                : isLastOn ? 'At least one strategy must stay on'
                : on ? 'Click to remove from the portfolio' : 'Click to add to the portfolio'
            }
            className={`group inline-flex items-center gap-2 pl-2 pr-2.5 py-[5px] rounded-md text-[12px] font-medium border transition-colors ${
              on ? 'bg-bg-surface border-border-default text-text-primary' : 'bg-bg-sunken border-border-subtle text-text-tertiary'
            } ${isLastOn || !done ? 'cursor-default' : 'hover:border-accent/40 cursor-pointer'}`}
          >
            <span
              className="w-2.5 h-2.5 rounded-[3px] flex-shrink-0"
              style={{ backgroundColor: on ? colorFor(leg.strategy_id) : 'transparent', border: on ? 'none' : `1.5px solid ${C.axisTick}` }}
            />
            <span className="truncate max-w-[180px]">{leg.strategy_name}</span>
            {done && leg.net_pnl != null && (
              <span className={`font-mono tabular-nums text-[11px] ${leg.net_pnl >= 0 ? 'text-pos-text' : 'text-neg-text'} ${on ? '' : 'opacity-60'}`}>
                {fmtMoney(leg.net_pnl)}
              </span>
            )}
            {!done && !failed && <Loader2 size={11} className="animate-spin text-accent flex-shrink-0" />}
            {failed && <XCircle size={11} className="text-neg-text flex-shrink-0" />}
          </button>
        )
      })}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

// Fixed heights so the trades card and the KPI grid line up (mirrors BacktestDetail's eval/KPI match).
// The stack's stand-in for a backtest's VERDICT ribbon: per-strategy trade breakdown inline,
// combined total anchored right in the same slot the backtest puts its trade count. Was a
// fixed-height card beside the old KPI grid; both that grid and its pinned height are gone.
function StackTradesRibbon({ perLegCounts, total, colorFor }: {
  perLegCounts: { strategy_id: string; strategy_name: string; count: number }[]
  total: number
  colorFor: (id: string) => string
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border-subtle border-l-[3px] border-l-accent/60 bg-bg-surface pl-4 pr-2.5 py-2.5">
      <span className="text-[10px] font-bold uppercase tracking-[0.9px] text-text-tertiary">By strategy</span>
      {perLegCounts.map(l => (
        <span key={l.strategy_id} className="flex items-center gap-1.5 min-w-0">
          <span className="w-2.5 h-2.5 rounded-[3px] flex-shrink-0" style={{ backgroundColor: colorFor(l.strategy_id) }} />
          <span className="text-[12px] text-text-secondary truncate max-w-[180px]">{l.strategy_name}</span>
          <span className="text-[12px] font-mono tabular-nums text-text-primary">{l.count}</span>
        </span>
      ))}
      <span className="ml-auto flex items-baseline gap-2.5 pl-4 border-l border-border-subtle shrink-0">
        <span className="text-[29px] font-bold font-mono leading-none text-accent tabular-nums">{total}</span>
        <span className="text-[11px] font-bold uppercase tracking-[0.9px] text-text-secondary">Trades</span>
      </span>
    </div>
  )
}

const CHART_TABS = [['equity', 'Equity'], ['price', 'Price'], ['breakdown', 'Breakdown']] as const
const CHART_SUBS: Record<string, string> = {
  equity: 'Steadily rising = good. Big peak then long decline = giving back gains.',
  price: 'Candles with each enabled strategy\'s trades layered in its colour. Structure, fib + measurement tools included.',
  breakdown: 'Drawdown from peak, daily P&L, and long vs short — for the combined portfolio.',
}

export function StackDetail() {
  const { stackId } = useParams<{ stackId: string }>()
  const navigate = useNavigate()
  const { data: stack, isLoading } = useStack(stackId ?? null)
  const deleteStack = useDeleteStack()
  const cancelStack = useCancelStack()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [showRerun, setShowRerun] = useState(false)

  const isRunning = stack?.status === 'running'
  const legs = useMemo(() => stack?.strategies ?? [], [stack])
  const stackTitle = legs.map(l => l.strategy_name).join(' + ')

  // Enabled set — every completed leg starts on. Rebuilds when the completed set changes.
  const completeIds = useMemo(
    () => legs.filter(l => l.status === 'complete').map(l => l.strategy_id).join(','),
    [legs],
  )
  const [enabled, setEnabled] = useState<Set<string>>(new Set())
  useEffect(() => { setEnabled(new Set(completeIds ? completeIds.split(',') : [])) }, [completeIds])

  const colorFor = useMemo(() => {
    const idx = new Map(legs.map((l, i) => [l.strategy_id, i]))
    return (id: string) => LEG_COLORS[(idx.get(id) ?? 0) % LEG_COLORS.length]
  }, [legs])

  const combined = useMemo(() => composeCombined(legs, enabled), [legs, enabled])
  const hasResults = combined.hasResults

  const toggle = (id: string) => setEnabled(prev => {
    const next = new Set(prev)
    if (next.has(id)) { if (next.size > 1) next.delete(id) } else next.add(id)
    return next
  })

  const activeLegs = legs.filter(l => enabled.has(l.strategy_id) && l.status === 'complete')

  // ── Chart state — same toggles as a single backtest ──
  const [chartTab, setChartTab] = useState<string>('equity')
  const [fullscreen, setFullscreen] = useState<string | null>(null)
  const [histOn, setHistOn] = useState(false)
  const [rudOn, setRudOn] = useState(false)
  const [overlayOn, setOverlayOn] = useState(true)
  const [xMode, setXMode] = useState<XMode>(getXMode)
  const toggleXMode = useCallback((v: XMode) => { setXMode(v); setXModePref(v) }, [])

  // Per-strategy overlay lines on the equity chart (fields tagged onto each point by composeCombined).
  const overlayLines = useMemo(
    () => activeLegs.map(l => ({ id: `leg_${l.strategy_id}`, color: colorFor(l.strategy_id), name: l.strategy_name })),
    [activeLegs, colorFor],
  )
  const hasExcursion = combined.equity.some(d => d.favorable != null || d.adverse != null)

  // Regime bands from the stack's full-calendar timeline (a market property, same as a backtest).
  const hasRegimes = (stack?.regime_timeline?.length ?? 0) > 0
  const regimeBands = useMemo(() => {
    if (!overlayOn || !stack?.regime_timeline?.length) return []
    return xMode === 'trade'
      ? regimeBandsByIndex(combined.equity, new Map(stack.regime_timeline.map(d => [d.date, d.regime])))
      : regimeBandsFromTimeline(stack.regime_timeline)
  }, [overlayOn, xMode, stack?.regime_timeline, combined.equity])

  // Merged price-chart spec — loads once results exist (candles come from the base leg's cached spec).
  const { data: rawSpec, isLoading: specLoading, isError: specError } = useStackChartSpec(stackId ?? null, completeIds, hasResults)
  const requestCandles = useRunCandles(rawSpec?.base_run_id ?? null)
  const priceSpec = useMemo(() => {
    if (!rawSpec) return undefined
    // Each trade carries its strategy's colour AND name — the chart prints the name in the trade's
    // outcome chip ("SOS Fade · Won") and derives its Strategies dropdown from these same fields.
    const nameOf = new Map(rawSpec.layers.map(l => [l.strategy_id, l.strategy_name]))
    const trades = rawSpec.trades
      .filter(t => t.layer && enabled.has(t.layer))
      .map(t => ({ ...t, layerColor: colorFor(t.layer!), layerName: nameOf.get(t.layer!) ?? t.layer }))
    return { ...rawSpec, trades }
  }, [rawSpec, enabled, colorFor])

  const chartControls = (key: string) => key === 'equity' ? (
    <>
      <SeriesToggle label={hasExcursion ? 'Trade excursions' : 'Histogram'} on={histOn} onChange={setHistOn} />
      <SeriesToggle label="Run-ups & drawdowns" on={rudOn} onChange={setRudOn} />
      <XModeToggle value={xMode} onChange={toggleXMode} />
      {hasRegimes && <RegimeOverlayToggle on={overlayOn} onChange={setOverlayOn} />}
    </>
  ) : null

  const renderChart = (key: string, h: number, isModal = false) => {
    switch (key) {
      case 'equity':
        // Real EquityCurveChart on the COMBINED portfolio (so it inherits every backtest toggle —
        // excursions, run-ups, date/trade, regimes, expand) with a line per enabled strategy overlaid.
        return (
          <>
            <StackEquityLegend activeLegs={activeLegs} colorFor={colorFor} />
            <EquityCurveChart
              data={combined.equity}
              overlayLines={overlayLines}
              bands={regimeBands}
              showHistogram={histOn}
              showRunupDrawdown={rudOn}
              xMode={xMode}
              windowStart={stack?.start_date ?? null}
              height={h}
            />
          </>
        )
      case 'price': {
        if (isModal) return null   // price manages its own fullscreen (position:fixed)
        return (
          <PriceChartView
            spec={priceSpec}
            isLoading={specLoading}
            isError={specError}
            requestCandles={priceSpec?.baseTimeframe !== 'D1' ? requestCandles : undefined}
            height={h}
            isFullscreen={fullscreen === 'price'}
            onFullscreenClose={() => setFullscreen(null)}
          />
        )
      }
      case 'breakdown': {
        const hDraw = Math.max(140, Math.round((h - 56) * 0.45))
        const hRow = Math.max(160, Math.round((h - 56) * 0.55))
        return (
          <div className="space-y-8">
            <div>
              <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-2">Drawdown from peak</div>
              <DrawdownChart equity={combined.equity} height={hDraw} />
            </div>
            <div className={combined.hasDirection ? 'grid gap-6 lg:grid-cols-2' : ''}>
              <div>
                <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-2">Daily P&L</div>
                <DailyPnlChart data={combined.dailyPnl} netPnl={combined.run.net_pnl} height={hRow} />
              </div>
              {combined.hasDirection && (
                <div>
                  <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-2">Long vs Short</div>
                  <DirectionBreakdown equity={combined.equity} />
                </div>
              )}
            </div>
          </div>
        )
      }
      default:
        return null
    }
  }

  return (
    <div>
      <StickyHeader>
        {scrolled => (
          <div className={`flex items-center justify-between gap-3 ${scrolled ? 'mb-4' : 'mb-5'}`}>
            <div className="flex items-center gap-2.5 min-w-0">
              <button
                onClick={() => navigate('/backtests?tab=stacks')}
                className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary transition-colors flex-shrink-0"
              >
                <ArrowLeft size={14} /> {!scrolled && 'Stacks'}
              </button>
              {scrolled && stack && (
                <>
                  <span className="text-text-tertiary flex-shrink-0">·</span>
                  <h1 className="text-[14px] font-semibold truncate">{stackTitle}</h1>
                </>
              )}
            </div>
            {stack && !isRunning && (
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => setShowRerun(true)}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium text-text-secondary hover:text-text-primary border border-border-default hover:bg-bg-hover transition-colors"
                >
                  <Play size={12} /> Rerun
                </button>
                <button
                  onClick={() => setConfirmDelete(true)}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium text-text-tertiary hover:text-neg-text hover:bg-neg-muted border border-transparent hover:border-neg-text/20 transition-colors"
                >
                  <Trash2 size={12} /> Delete
                </button>
              </div>
            )}
          </div>
        )}
      </StickyHeader>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onClick={e => { if (e.target === e.currentTarget) setConfirmDelete(false) }}>
          <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[400px] shadow-2xl">
            <div className="px-5 py-4 border-b border-border-subtle"><div className="text-[15px] font-semibold">Delete this stack?</div></div>
            <div className="px-5 py-4">
              <p className="text-[13px] text-text-secondary">
                The stack and any runs it created will be removed. Reused standalone runs stay in your Runs tab. This cannot be undone.
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle">
              <button onClick={() => setConfirmDelete(false)} className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">Cancel</button>
              <button
                onClick={() => deleteStack.mutate(stackId!, { onSuccess: () => navigate('/backtests?tab=stacks') })}
                disabled={deleteStack.isPending}
                className="px-4 py-[7px] rounded-md text-[13px] font-medium bg-neg-muted text-neg-text border border-neg/40 hover:bg-neg/15 disabled:opacity-50 transition-colors"
              >
                {deleteStack.isPending ? 'Deleting…' : 'Delete stack'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showRerun && stack && (
        <StackConfigModal
          title="Rerun stack"
          submitLabel="Rerun stack"
          initial={{
            strategyIds: legs.map(l => l.strategy_id),
            instrument: stack.instrument,
            barValue: stack.bar_value,
            commPerSide: stack.commission_per_side,
            slippageTicks: stack.slippage_ticks,
            start: stack.start_date,
            end: stack.end_date,
          }}
          onClose={() => setShowRerun(false)}
        />
      )}

      {isLoading && (
        <div className="animate-pulse space-y-4">
          <div className="h-7 w-80 bg-bg-surface rounded" />
          <div className="h-4 w-56 bg-bg-surface rounded" />
          <div className="h-[300px] bg-bg-surface rounded-xl" />
        </div>
      )}

      {stack && (
        <div className="space-y-6">
          {/* Header */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Layers size={18} className="text-gold-text" />
              <h1 className="text-h1 font-semibold leading-tight">{stackTitle}</h1>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono bg-gold-muted text-gold-text border border-gold-text/20">
                {stack.total_strategies}-strategy Stack
              </span>
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-secondary font-mono">{stack.instrument}</span>
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-secondary font-mono">
                {fmtDate(stack.start_date)} → {fmtDate(stack.end_date)}
              </span>
            </div>
          </div>

          {/* Running / cancel banner */}
          {isRunning && (
            <div className="flex items-center justify-between gap-4 rounded-lg border border-accent/20 bg-accent/5 px-4 py-3">
              <div className="flex items-center gap-2 text-[13px] text-accent">
                <Loader2 size={14} className="animate-spin" />
                Running — {stack.completed_strategies} of {stack.total_strategies} strategies complete
                <span className="text-text-tertiary text-[11px]">· auto-refreshing</span>
              </div>
              <button
                onClick={() => cancelStack.mutate(stackId!)}
                disabled={cancelStack.isPending}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium border border-neg-text/30 text-neg-text hover:bg-neg-muted disabled:opacity-50 transition-colors"
              >
                <Square size={11} /> {cancelStack.isPending ? 'Cancelling…' : 'Cancel'}
              </button>
            </div>
          )}

          {/* Trades + Performance — identical two-column layout to a single backtest. The left card
              takes the EVALUATION card's slot: per-strategy trade breakdown on top, the combined
              total at the bottom. The KPI grid on the right is height-matched, More/Fewer grows both. */}
          {/* Same three-question panel as a single backtest, so the numbers are computed and
              read identically. A stack has no firm verdict, so the ribbon slot carries the
              per-strategy trade breakdown instead — the stack's answer to "what is this made
              of", in the row where a backtest states its verdict. */}
          {hasResults && (
            <div>
              <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">Performance</h2>
              <PerformancePanel
                run={combined.run} fallback={combined.fallback} equity={combined.equity}
                balance={combined.balance}
                ribbon={
                  <StackTradesRibbon
                    perLegCounts={combined.perLegCounts}
                    total={combined.run.trade_count ?? 0}
                    colorFor={colorFor}
                  />
                }
              />
            </div>
          )}

          {/* Strategy toggle chips — drive the combined KPIs AND the charts */}
          {legs.length > 0 && (
            <div>
              <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-2.5">Strategies in this stack</h2>
              <StrategyChips legs={legs} enabled={enabled} colorFor={colorFor} onToggle={toggle} />
            </div>
          )}

          {/* Charts — Equity / Price / Breakdown, exactly like a single backtest */}
          {hasResults ? (
            <div className="space-y-4">
              <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px]">Charts</div>
              <ChartTabPanel
                tabs={CHART_TABS}
                active={chartTab}
                onActive={setChartTab}
                sub={CHART_SUBS[chartTab]}
                height={520}
                onExpand={() => setFullscreen(chartTab)}
                render={(k, h) => renderChart(k, h)}
                right={chartControls(chartTab)}
              />
              {fullscreen && fullscreen !== 'price' && (
                <ChartModal
                  title={fullscreen === 'equity' ? 'Equity Curve' : 'Breakdown'}
                  onClose={() => setFullscreen(null)}
                  render={h => renderChart(fullscreen, h, true)}
                  controls={chartControls(fullscreen)}
                />
              )}
            </div>
          ) : !isRunning ? (
            <div className="rounded-xl border border-border-subtle bg-bg-surface px-6 py-10 text-center text-[13px] text-text-tertiary">
              No completed strategy runs to compose. {legs.some(l => l.status.startsWith('failed')) && 'Some runs failed — check the chips above.'}
            </div>
          ) : (
            <div className="rounded-xl border border-border-subtle bg-bg-surface px-6 py-10 text-center text-[13px] text-text-tertiary">
              Waiting for the first strategy to finish…
            </div>
          )}

          {/* Per-strategy table — each row opens that leg's own backtest (back returns here) */}
          {legs.some(l => l.status === 'complete') && (
            <div>
              <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">Per-strategy results</h2>
              <div className="bg-bg-surface border border-border-subtle rounded-xl overflow-hidden overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-border-subtle bg-bg-sunken">
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Strategy</th>
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Net P&L</th>
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Max DD</th>
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Sharpe</th>
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Trades</th>
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Status</th>
                      <th className="px-3 py-2 w-16" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {legs.map(leg => {
                      const done = leg.status === 'complete'
                      const failed = leg.status.startsWith('failed')
                      return (
                        <tr
                          key={leg.run_id}
                          onClick={() => done && navigate(`/backtests/runs/${leg.run_id}`, { state: { fromStack: stackId, fromStackTitle: stackTitle } })}
                          className={`transition-colors ${done ? 'hover:bg-bg-hover cursor-pointer' : ''}`}
                        >
                          <td className="px-3 py-[9px] font-semibold text-text-primary">
                            <span className="inline-flex items-center gap-2">
                              <span className="w-2.5 h-2.5 rounded-[3px] flex-shrink-0" style={{ backgroundColor: colorFor(leg.strategy_id) }} />
                              {leg.strategy_name}
                            </span>
                          </td>
                          <td className={`px-3 py-[9px] font-mono tabular-nums ${(leg.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>
                            {leg.net_pnl != null ? fmtMoney(leg.net_pnl) : '—'}
                          </td>
                          <td className="px-3 py-[9px] font-mono tabular-nums text-neg-text">
                            {leg.max_drawdown != null ? fmtMoney(-Math.abs(leg.max_drawdown), false) : '—'}
                          </td>
                          <td className="px-3 py-[9px] font-mono tabular-nums text-text-secondary">
                            {leg.sharpe != null ? leg.sharpe.toFixed(2) : '—'}
                          </td>
                          <td className="px-3 py-[9px] tabular-nums text-text-secondary">{leg.trade_count ?? '—'}</td>
                          <td className="px-3 py-[9px]">
                            {done && <span className="inline-flex items-center gap-1.5 text-[11px] text-accent"><CheckCircle2 size={11} /> complete</span>}
                            {failed && <span className="inline-flex items-center gap-1.5 text-[11px] text-neg-text" title={leg.error_message ?? ''}><XCircle size={11} /> failed</span>}
                            {!done && !failed && <span className="inline-flex items-center gap-1.5 text-[11px] text-text-tertiary"><Loader2 size={11} className="animate-spin" /> running</span>}
                          </td>
                          <td className="px-3 py-[9px] text-right">{done && <span className="text-[11px] text-accent">View →</span>}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
