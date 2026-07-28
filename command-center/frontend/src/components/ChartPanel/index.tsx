/**
 * ChartPanel — strategy-agnostic backtest chart (klinecharts v9).
 *
 * Renders whatever a `ChartSpec` declares (see ./types). Contains ZERO strategy-specific
 * logic: no instrument names, no session names, no breakout/range concepts. Adding a new
 * strategy means its spec lists different overlays — this file does not change.
 *
 * Lazy-mounted: imported via React.lazy from the backtest page so klinecharts + the fixture
 * only load once the panel's section is opened (page performance).
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AlignJustify, Camera, Check, ChevronDown, Eye, EyeOff, RotateCcw, Ruler, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { DomPosition, IndicatorSeries, LoadDataType, dispose, init, type Chart, type KLineData } from 'klinecharts'
import type { ChartBlock, ChartCandle, ChartSpec } from './types'
import { chartStyles } from './chartStyles'
import { AUDJPY_FIXTURE } from './fixtures/audjpy'
import { BLOCK, BOX, DATA_EDGE, DAY_BREAK, FIB, HLINE, LABEL, type LabelItem, SESSION_BOX, STRUCTURE_GROUPS, STRUCTURE_GROUP_COLOR, TRADE, VLINE, registerChartOverlays } from './overlays'
import { ensureSeriesIndicator } from './indicators'
import { sessionWindows } from './sessions'
import theme from '@/themes/electric-indigo'

interface MeasureRect {
  x: number; y: number; w: number; h: number
  startTs: number; endTs: number
  startVal: number; endVal: number
}
interface LockedMeasurement extends MeasureRect { id: string }

function fmtDuration(ms: number): string {
  const m = Math.round(ms / 60_000)
  const d = Math.floor(m / 1440)
  const h = Math.floor((m % 1440) / 60)
  const min = m % 60
  if (d > 0) return h > 0 ? `${d}d ${h}h` : `${d}d`
  if (h > 0) return min > 0 ? `${h}h ${min}m` : `${h}h`
  return `${min}m`
}

function fmtDiff(v: number): string {
  const a = Math.abs(v)
  return a >= 100 ? a.toFixed(2) : a >= 1 ? a.toFixed(4) : a.toFixed(5)
}

const CHART_HEIGHT = 520
const DAY_MS = 24 * 60 * 60 * 1000
const TRADE_WIN_COLOR = theme.pos          // green box — trade reached target (pnl > 0)
const TRADE_LOSS_COLOR = theme.neg         // red box — trade hit its stop (pnl <= 0)
// Profit-fill mint — deliberately LIGHTER than the candle up-colour (theme.pos) so the
// profit-depth band never blends into the green candles inside it (Aaron 2026-07-20).
const TRADE_PROFIT_FILL = '#8ef2b8'
// Blocked setups get their OWN colour, off the win/loss axis entirely — a refused trade is not a
// loser, and painting it red would read as one. Pink, matching the Pine's `TRADE BLOCKED` tag.
// One scroll-left page of older history, in BARS — so a page costs the same at every timeframe
// (~1 MB of JSON) instead of ballooning on a fine one.
const PAGE_BARS = 12_000
const BLOCK_COLOR = '#ff2e9a'
const BLOCK_TIP_W = 240                    // hover-card width; feeds the viewport clamp
const BLOCK_TIP_H = 180                    // ~its height with two reasons listed; same clamp
const DEFAULT_OVERLAY_COLOR = theme.textTertiary // fallback when a spec overlay omits a color
const DAY_BREAK_COLOR = theme.textTertiary // muted vertical line for daily session breaks
const INDICATOR_PALETTE = [theme.gold, theme.series[4], theme.accent, theme.series[1]] // line colors

type TfOption = { label: string; min: number }

/** One row in a header dropdown: a coloured dot, a label, an optional count, a tick when on.
 *  `sub` indents it under the row above (a filter of that layer rather than a peer of it). */
interface MenuItem {
  key: string
  label: string
  color: string
  on: boolean
  toggle: () => void
  sub?: boolean
  count?: number
}

/** The header's multi-select dropdown — Layers, Analysis and Strategies are all this component
 *  with different items, so a row can never render three different ways. It owns its own open
 *  state + click-outside close, and deliberately stays OPEN while toggling (these menus are used
 *  to compare combinations, not to make one choice). */
function ToggleMenu({ title, items, minWidth = 172 }: {
  title: string
  items: MenuItem[]
  minWidth?: number
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])
  const activeCount = items.filter(it => it.on).length
  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(o => !o)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border-subtle bg-bg-sunken text-[11px] font-medium text-text-secondary hover:text-text-primary transition-colors"
      >
        {title}
        <span className="font-mono text-text-tertiary">{activeCount}/{items.length}</span>
        <ChevronDown className={`w-3 h-3 text-text-tertiary transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute left-0 mt-1 rounded-md border border-border-subtle bg-bg-surface py-1 shadow-lg" style={{ zIndex: 50, minWidth }}>
          {items.map(it => (
            <button
              key={it.key}
              onClick={it.toggle}
              className={`flex w-full items-center gap-2 py-1.5 pr-3 text-left text-[11px] font-medium transition-colors hover:bg-bg-sunken ${it.sub ? 'pl-7' : 'pl-3'}`}
            >
              <span
                className="w-2 h-2 rounded-full flex-shrink-0"
                style={{ background: it.on ? it.color : 'transparent', boxShadow: `inset 0 0 0 1px ${it.color}`, opacity: it.on ? 1 : 0.5 }}
              />
              <span className={it.on ? 'text-text-primary' : 'text-text-tertiary'}>{it.label}</span>
              {it.count != null && <span className="font-mono text-text-tertiary">{it.count}</span>}
              {it.on && <Check className="w-3 h-3 ml-auto flex-shrink-0 text-accent" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// Display-timeframe ladder for the segmented control. Filtered per spec.baseTimeframe so we
// never offer a TF finer than the strategy's own bars (those come from the drill-down below).
const DISPLAY_TFS: readonly TfOption[] = [
  { label: 'M5', min: 5 },
  { label: 'M15', min: 15 },
  { label: 'M30', min: 30 },
  { label: 'H1', min: 60 },
]

// Drill-down timeframes BELOW the chart's base bars — pulled live from the broker (they can't be
// resampled UP from the base). Offered only when an `onRequestCandles` fetcher is wired.
//
// The ladder deliberately covers every intraday TF, not just M1/M5, because the chart's base is NOT
// always the run's own bar size: `chart_spec._fit_timeframe` steps a long run's base UP to keep the
// shipped candle count sane (a 6.5-year 15m run ships H4). Without M15/M30/H1 here, that run could
// not be viewed at the timeframe it actually TRADED — the one view that matters most.
const FETCH_TFS: readonly TfOption[] = [
  { label: 'M1', min: 1 },
  { label: 'M5', min: 5 },
  { label: 'M15', min: 15 },
  { label: 'M30', min: 30 },
  { label: 'H1', min: 60 },
]

// How far back to REQUEST each drill-down TF. For M1/M5 this is deliberately MORE than the broker's
// known depth (~30d / ~240d) so the fetch reaches the feed's true edge, which the backend reports as
// a hard limit (the red "no earlier data" line). From M15 up the broker has years, so the binding
// limit is the backend's own 60k-candle drill cap instead — these values sit just under it, which is
// what a full-depth request would be clamped to anyway (and a clamped request correctly draws NO red
// edge, since the boundary is ours, not the broker's).
const FETCH_TF_LOOKBACK_DAYS: Record<number, number> = {
  1: 45, 5: 270, 15: 850, 30: 1700, 60: 3400,
}

/** "M5" → 5, "M15" → 15, "H1" → 60, "H4" → 240, "D1" → 1440. Falls back to 5. */
function parseTfMinutes(tf: string): number {
  const m = /^([MHD])(\d+)$/.exec(tf.trim().toUpperCase())
  if (!m) return 5
  const n = Number(m[2])
  return m[1] === 'H' ? n * 60 : m[1] === 'D' ? n * 1440 : n
}

/** Candle `time` (epoch ms) → klinecharts `timestamp`. Pure field map. */
function candlesToKLine(candles: ChartCandle[]): KLineData[] {
  return candles.map(c => ({
    timestamp: c.time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: c.volume,
  }))
}

/**
 * Aggregate base-TF candles up to `targetMs`-wide bars for display. Buckets are epoch-aligned
 * (floor(time / targetMs)). Higher-TF candles are DISPLAY aggregations only — the strategy's
 * own TF (spec.baseTimeframe) remains the source of truth. Input must be sorted ascending.
 */
function resample(candles: ChartCandle[], targetMs: number): ChartCandle[] {
  const out: ChartCandle[] = []
  let bucket: ChartCandle | null = null
  let bucketStart = -1
  for (const c of candles) {
    const start = Math.floor(c.time / targetMs) * targetMs
    if (bucket === null || start !== bucketStart) {
      if (bucket) out.push(bucket)
      bucketStart = start
      bucket = { time: start, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume ?? 0 }
    } else {
      bucket.high = Math.max(bucket.high, c.high)
      bucket.low = Math.min(bucket.low, c.low)
      bucket.close = c.close
      bucket.volume = (bucket.volume ?? 0) + (c.volume ?? 0)
    }
  }
  if (bucket) out.push(bucket)
  return out
}

export default function ChartPanel({
  spec = AUDJPY_FIXTURE,
  height = CHART_HEIGHT,
  onRequestCandles,
  headerLeading,
  headerTrailing,
  headerClassName,
  showCopy = false,
}: {
  spec?: ChartSpec
  height?: number
  /**
   * Drill-down data source: fetch finer-than-base candles for a bounded window (e.g. 1m under a
   * 15m run, to see a trade's exact entry). When provided, the timeframe control offers sub-base
   * TFs (1m/5m) that pull the visible window live; omitted (e.g. the fixture) → panel behaves as
   * before. `available: false` means the feed can't serve that window (1m older than the broker keeps).
   */
  onRequestCandles?: (tf: string, fromMs: number, toMs: number) => Promise<{ candles: ChartCandle[]; available: boolean; dataStartMs: number | null; hardEdge: boolean }>
  /**
   * Optional header-bar slots so a host can fold its OWN chrome onto the panel's single top row
   * (rather than stacking a second bar above it). `headerLeading` renders at the far left, before
   * the timeframe control; `headerTrailing` at the far right, after Copy. `headerClassName` is
   * appended to the header row (e.g. a `border-b` when it doubles as a modal title bar). Used by
   * the fullscreen wrapper to put its "Price" title + exit X on the same row as TF/Layers/Copy.
   */
  headerLeading?: ReactNode
  headerTrailing?: ReactNode
  headerClassName?: string
  /** Show the snapshot (camera) button. FULLSCREEN ONLY by convention — the whole app puts
   *  copy-as-image on the expanded chart, never the inline one. */
  showCopy?: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<Chart | null>(null)

  const baseMin = useMemo(() => parseTfMinutes(spec.baseTimeframe), [spec.baseTimeframe])
  const options = useMemo<TfOption[]>(() => {
    const up = DISPLAY_TFS.filter(tf => tf.min >= baseMin && tf.min % baseMin === 0).map(tf => ({ label: tf.label, min: tf.min }))
    const base: TfOption[] = up.length ? up : [{ label: spec.baseTimeframe.toUpperCase(), min: baseMin }]
    // Sub-base TFs (below the run's own bars) are DRILL-DOWN — can't be resampled from the base,
    // so only offered when a fetcher is wired to pull them live.
    const down: TfOption[] = onRequestCandles ? FETCH_TFS.filter(tf => tf.min < baseMin) : []
    return [...down, ...base]
  }, [baseMin, spec.baseTimeframe, onRequestCandles])

  // The timeframe the run actually TRADED — the chart's default view, because that is the only
  // timeframe its trades and blocked setups line up with bar-for-bar. It is often FINER than the
  // shipped `baseTimeframe` (the emitter steps a long run up to keep the payload sane), in which case
  // opening on it means opening in drill-down. Falls back to the shipped bars when the run TF isn't
  // offered — no fetcher wired, or a spec cached before `runTimeframe` existed.
  const openMin = useMemo(() => {
    const want = parseTfMinutes(spec.runTimeframe ?? spec.baseTimeframe)
    return options.some(o => o.min === want) ? want : baseMin
  }, [spec.runTimeframe, spec.baseTimeframe, options, baseMin])

  // Selected display TF (minutes). Component-local UI state.
  const [selectedMin, setSelectedMin] = useState<number>(() => openMin)
  // Timeframe dropdown (TradingView-style) open state + click-outside to close.
  const [tfOpen, setTfOpen] = useState(false)
  const tfRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!tfOpen) return
    const onDown = (e: MouseEvent) => {
      if (tfRef.current && !tfRef.current.contains(e.target as Node)) setTfOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [tfOpen])

  // Reset selection to the run's own TF when the spec (and thus its options) changes.
  useEffect(() => {
    setSelectedMin(openMin)
  }, [openMin])

  // Drill-down (sub-base) fetch state. `isFetchMode` = a TF finer than the run's own bars is
  // selected; then `fetched` (pulled live for the visible window) replaces the resampled candles.
  const [fetched, setFetched] = useState<ChartCandle[]>([])
  const [fetchStatus, setFetchStatus] = useState<'idle' | 'loading' | 'ok' | 'empty' | 'error'>('idle')
  // The broker's TRUE oldest bar for the active drill-down TF (M1 ~30d back, M5 ~240d) — drawn as a
  // red dashed "no earlier data" line. null = no hard edge (feed has more, or nothing loaded).
  const [dataEdge, setDataEdge] = useState<{ ts: number; tf: number } | null>(null)
  // In-session cache per drill-down TF. A completed run's window is fixed, so once pulled the full
  // sub-base depth never changes — re-selecting the TF shows it instantly (no re-fetch flash). The
  // backend also caches the bars to disk, so even a cold reload only hits the broker once.
  const fetchCacheRef = useRef<Map<number, { candles: ChartCandle[]; edge: number | null }>>(new Map())
  const fetchTokenRef = useRef(0)
  const isFetchMode = onRequestCandles != null && selectedMin < baseMin

  // The candles the chart is built from: the spec's shipped window, GROWN by older pages paged in as
  // you scroll left. The spec deliberately ships only the newest slice of a long run (see
  // `chart_spec._capped_start`), so this is how the rest of the run's history becomes reachable
  // without a 15 MB payload on open. Reset whenever the spec changes.
  const [baseCandles, setBaseCandles] = useState<ChartCandle[]>(spec.candles)
  useEffect(() => { setBaseCandles(spec.candles) }, [spec.candles])
  // Read by the load callback, which is registered once on mount and would otherwise close over the
  // first render's candles forever.
  const baseCandlesRef = useRef(baseCandles)
  useEffect(() => { baseCandlesRef.current = baseCandles }, [baseCandles])

  const displayCandles = useMemo(() => {
    // In drill-down, show the SHIPPED bars until the finer ones land. They arrive in the spec, so
    // they paint on the first frame; the drill-down is a network pull. Returning `fetched` straight
    // out means an empty chart for the length of that pull — and since the panel now OPENS in
    // drill-down (the run's own TF is usually finer than the shipped bars), that turned every chart
    // open into a blank screen where it used to be instant. Coarse bars now, correct bars in a
    // moment, never nothing.
    if (isFetchMode) return fetched.length ? fetched : baseCandles
    return selectedMin === baseMin ? baseCandles : resample(baseCandles, selectedMin * 60_000)
  }, [isFetchMode, fetched, baseCandles, selectedMin, baseMin])
  // True while the chart is showing shipped bars that are NOT the selected TF — the header says so,
  // because bars that don't match the TF button would otherwise be a silent lie.
  const showingPlaceholder = isFetchMode && fetched.length === 0 && baseCandles.length > 0

  // Time bounds of the LOADED candles (ascending). Overlays anchored OUTSIDE this range must not be
  // drawn: klinecharts clamps an out-of-range point to the plot edge, so in a drill-down TF (whose
  // data only goes back to the broker's edge) every older trade/session/day-break piles up in the
  // empty no-data region. Only the red DATA_EDGE line lives out there. Null when no candles loaded.
  const [loadedLoTs, loadedHiTs] = useMemo<[number | null, number | null]>(
    () => displayCandles.length
      ? [displayCandles[0].time, displayCandles[displayCandles.length - 1].time]
      : [null, null],
    [displayCandles],
  )

  // Pull a drill-down TF's FULL broker depth in one shot (ending at the run's last bar), so the chart
  // shows every sub-base bar the feed still holds — the user scrolls left until the red edge line.
  // The backend reports that true edge; we cache the result per TF (the run's window is fixed) so
  // re-selecting is instant.
  const runFetch = async (min: number) => {
    if (!onRequestCandles) return
    const cached = fetchCacheRef.current.get(min)
    if (cached) {
      setFetched(cached.candles)
      setDataEdge(cached.edge != null ? { ts: cached.edge, tf: min } : null)
      setFetchStatus(cached.candles.length ? 'ok' : 'empty')
      return
    }
    const end = spec.candles[spec.candles.length - 1]?.time ?? Date.now()
    const from = end - (FETCH_TF_LOOKBACK_DAYS[min] ?? 30) * DAY_MS
    const label = FETCH_TFS.find(tf => tf.min === min)?.label ?? `M${min}`
    const token = ++fetchTokenRef.current
    setFetchStatus('loading')
    try {
      const res = await onRequestCandles(label, from, end)
      if (token !== fetchTokenRef.current) return // a newer fetch superseded this one
      const edge = res.hardEdge && res.dataStartMs != null ? res.dataStartMs : null
      fetchCacheRef.current.set(min, { candles: res.candles, edge })
      setFetched(res.candles)
      setDataEdge(edge != null ? { ts: edge, tf: min } : null)
      setFetchStatus(res.candles.length ? 'ok' : 'empty')
    } catch {
      if (token === fetchTokenRef.current) setFetchStatus('error')
    }
  }

  // ── Paging older history (scroll left) ───────────────────────────────────────
  // The spec ships only the newest slice of a long run. klinecharts asks for more the moment you
  // scroll past the left edge, and this answers with one page from the run's own feed. The page is
  // sized in BARS, not days, so it costs the same at every timeframe.
  const loadOlder = useCallback(async (): Promise<{ bars: ChartCandle[]; more: boolean }> => {
    const oldest = baseCandlesRef.current[0]?.time
    const start = spec.historyStartMs
    // No fetcher, nothing loaded, or already at the run's start ⇒ nothing older is claimed to exist.
    if (!onRequestCandles || oldest == null || start == null || oldest <= start) {
      return { bars: [], more: false }
    }
    const perDay = (1440 / baseMin) * (5 / 7)          // ~forex: 5 trading days/week, 24h
    const to = oldest - 1
    const from = Math.max(start, to - Math.ceil(PAGE_BARS / perDay) * DAY_MS)
    const res = await onRequestCandles(spec.baseTimeframe.toUpperCase(), from, to)
    // Guard the merge: a feed that returns an overlapping window would otherwise duplicate bars.
    const bars = res.candles.filter(c => c.time < oldest)
    return { bars, more: bars.length > 0 && from > start }
  }, [onRequestCandles, spec.historyStartMs, spec.baseTimeframe, baseMin])
  const loadOlderRef = useRef(loadOlder)
  useEffect(() => { loadOlderRef.current = loadOlder }, [loadOlder])
  // A drill-down TF loads its own full depth in one shot, so paging must not fire there — it would
  // splice base-TF bars into a 1m chart.
  const pagingOffRef = useRef(false)
  useEffect(() => { pagingOffRef.current = isFetchMode }, [isFetchMode])
  // Set when a candle change came from a PAGE rather than a TF/spec switch. klinecharts has already
  // merged those bars and holds the scroll position; re-running `applyNewData` would throw both away
  // and snap the view back — the jump-on-every-page bug.
  const skipApplyRef = useRef(false)

  // Session boxes are derived from the BASE candles (high/low envelope is TF-invariant) and
  // anchored by timestamp, so they stay put across timeframe switches. Show on ALL candle days.
  const sessionBoxes = useMemo(
    () => spec.sessions.map(s => ({
      name: s.name,
      color: s.color,
      windows: sessionWindows(baseCandles, s, spec.brokerGmtOffsetHours),
    })),
    [baseCandles, spec.sessions, spec.brokerGmtOffsetHours],
  )

  // Per-session visibility (component-local UI state). Defaults all OFF — the chart opens on just
  // the trades; sessions are opt-in from the on-chart legend. Resets with the spec.
  const [sessionsOn, setSessionsOn] = useState<Record<string, boolean>>(
    () => Object.fromEntries(spec.sessions.map(s => [s.name, false] as [string, boolean])) as Record<string, boolean>,
  )
  useEffect(() => {
    setSessionsOn(Object.fromEntries(spec.sessions.map(s => [s.name, false] as [string, boolean])) as Record<string, boolean>)
  }, [spec.sessions])
  const toggleSession = (name: string) => setSessionsOn(v => ({ ...v, [name]: !v[name] }))
  const setAllSessions = (on: boolean) => setSessionsOn(Object.fromEntries(spec.sessions.map(s => [s.name, on])) as Record<string, boolean>)
  // On-chart "Sessions" legend popover (TradingView indicator-legend style) open state + outside-close.
  const [sessionsLegendOpen, setSessionsLegendOpen] = useState(false)
  const sessionsLegendRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!sessionsLegendOpen) return
    const onDown = (e: MouseEvent) => {
      if (sessionsLegendRef.current && !sessionsLegendRef.current.contains(e.target as Node)) setSessionsLegendOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [sessionsLegendOpen])

  // Trades: one on/off toggle for all of them, driven from the right-click chart menu.
  const [tradesOn, setTradesOn] = useState(true)

  // Outcome filters — winners and losers toggle independently, so the chart can show just the
  // winners or just the losers. Both default ON (a run opens on every trade). Same win test as the
  // overlay's colour rule (`pnl > 0`), so a trade's chip colour and its filter can never disagree.
  const [winnersOn, setWinnersOn] = useState(true)
  const [losersOn, setLosersOn] = useState(true)
  const outcomeCounts = useMemo(() => {
    const wins = spec.trades.reduce((n, tr) => n + (tr.pnl > 0 ? 1 : 0), 0)
    return { wins, losses: spec.trades.length - wins }
  }, [spec.trades])

  // Blocked setups — the trades that never happened. Default OFF: they are a diagnostic view
  // ("is this rule protecting me or costing me?"), not part of reading the run's result, and on a
  // long run there are more of them than there are trades.
  // NORMALISED on read. A `chart_spec.json` is CACHED per run, so a spec built before `reasons`
  // became a list is still on disk carrying a single `label`/`reason` pair — and every read below
  // (`b.reasons.length`, the filter roster, the hover card) would throw on it, taking the whole
  // panel down. A stale cache must degrade, never crash.
  const blocks = useMemo<ChartBlock[]>(() => (spec.blocks ?? []).map(b => {
    const legacy = b as unknown as { label?: string; reason?: string }
    return {
      ...b,
      reasons: b.reasons?.length ? b.reasons
        : legacy.label ? [{ label: legacy.label, reason: legacy.reason ?? '' }]
        : [],
    }
  }).filter(b => b.reasons.length > 0), [spec.blocks])
  const [blocksOn, setBlocksOn] = useState(false)
  // The hovered block's text + where to float it. klinecharts fires the hover on its own canvas, so
  // the card is a plain DOM node placed at the cursor. It reads the event's PAGE coordinates and
  // renders viewport-`fixed` (the right-click menu's pattern) rather than positioning inside the
  // chart wrapper: the overlay event's `x`/`y` are pane-relative, so any wrapper padding or a second
  // pane would silently offset the card. Page coords have one origin, in every layout and fullscreen.
  const [blockTip, setBlockTip] = useState<{ x: number; y: number; b: ChartBlock } | null>(null)

  // Per-reason filters. The roster is DERIVED from the blocks themselves — first-seen order, keyed
  // on the strategy's own label — so the panel stays strategy-agnostic: it sees reasons as data,
  // exactly like overlay groups and stack layers, and a strategy with a different rule set needs no
  // change here. Counts are how many setups EACH rule refused, which is the number the whole layer
  // exists to produce ("is this rule protecting me or costing me?").
  const blockReasons = useMemo(() => {
    const counts = new Map<string, number>()
    for (const b of blocks) for (const r of b.reasons) counts.set(r.label, (counts.get(r.label) ?? 0) + 1)
    return Array.from(counts, ([label, count]) => ({ label, count }))
  }, [blocks])
  // Reasons hidden from the chart. A stale label from a spec change is inert, so no reconciliation.
  const [hiddenReasons, setHiddenReasons] = useState<Set<string>>(new Set())
  const toggleReason = (label: string) => setHiddenReasons(prev => {
    const next = new Set(prev)
    if (next.has(label)) next.delete(label); else next.add(label)
    return next
  })
  // A block draws while ANY of its reasons is still on. Requiring ALL would make "show me the veto
  // blocks" hide the ones the final hour was also refusing — which are still veto blocks.
  const blockVisible = useCallback(
    (b: ChartBlock) => b.reasons.some(r => !hiddenReasons.has(r.label)),
    [hiddenReasons],
  )
  const shownBlockCount = useMemo(
    () => blocks.reduce((n, b) => n + (blockVisible(b) ? 1 : 0), 0),
    [blocks, blockVisible],
  )
  useEffect(() => { setBlockTip(null) }, [blocks, blocksOn, hiddenReasons])

  // Portfolio-stack layers. The roster is DERIVED from the trades themselves (`layer`/`layerName`/
  // `layerColor`), so the panel stays strategy-agnostic — it sees layers as data, exactly like
  // overlay groups. Empty on a single-run spec, which is what hides the Strategies dropdown.
  const tradeLayers = useMemo(() => {
    const seen = new Map<string, { id: string; name: string; color: string }>()
    for (const tr of spec.trades) {
      if (!tr.layer || seen.has(tr.layer)) continue
      seen.set(tr.layer, { id: tr.layer, name: tr.layerName ?? tr.layer, color: tr.layerColor ?? DEFAULT_OVERLAY_COLOR })
    }
    return Array.from(seen.values())
  }, [spec.trades])
  // Layers hidden from the chart (isolate one strategy). Ids only — a stale id from a spec change
  // is inert, so no reconciliation needed.
  const [hiddenLayers, setHiddenLayers] = useState<Set<string>>(new Set())
  const toggleLayer = (id: string) => setHiddenLayers(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  // Generic overlays (box/hline/vline) carry strategy structure, grouped by `group`. Each group
  // is independently toggleable. The chart never knows which strategy produced them.
  const overlayGroups = useMemo(() => {
    const seen = new Map<string, string>() // group → representative (first) color
    for (const ov of spec.overlays) {
      if (!seen.has(ov.group)) seen.set(ov.group, ov.style?.color ?? DEFAULT_OVERLAY_COLOR)
    }
    // Market structure always shows ALL FOUR toggles once the run carries any structure at all —
    // they're the Pine's four checkboxes, and a checkbox that vanishes when its layer happens to be
    // empty reads as a missing feature. "Internal Structure" is the one this bites: it holds only the
    // CURRENT external leg, which is legitimately empty on most runs (everything older is Historic).
    if (STRUCTURE_GROUPS.some(g => seen.has(g))) {
      for (const g of STRUCTURE_GROUPS) if (!seen.has(g)) seen.set(g, STRUCTURE_GROUP_COLOR[g])
    }
    // Non-structure groups first (in first-seen order), then the market-structure groups in their
    // fixed canonical order so the four Layers toggles always read External → Internal → Historic →
    // Swing Labels, regardless of which fired first in the spec.
    const all = Array.from(seen, ([name, color]) => ({ name, color }))
    const structureOrder = (n: string) => STRUCTURE_GROUPS.indexOf(n as typeof STRUCTURE_GROUPS[number])
    const nonStruct = all.filter(g => structureOrder(g.name) < 0)
    const struct = all.filter(g => structureOrder(g.name) >= 0).sort((a, b) => structureOrder(a.name) - structureOrder(b.name))
    return [...nonStruct, ...struct]
  }, [spec.overlays])

  // Every overlay group defaults ON, EXCEPT the market-structure groups — those are opt-in (a chart
  // would be unreadable with all of BOS/SOS/swings/internal drawn by default), toggled from Structure.
  const groupDefault = (name: string): boolean => !STRUCTURE_GROUPS.includes(name as typeof STRUCTURE_GROUPS[number])
  const [groupsOn, setGroupsOn] = useState<Record<string, boolean>>(
    () => Object.fromEntries(overlayGroups.map(g => [g.name, groupDefault(g.name)] as [string, boolean])) as Record<string, boolean>,
  )
  useEffect(() => {
    setGroupsOn(Object.fromEntries(overlayGroups.map(g => [g.name, groupDefault(g.name)] as [string, boolean])) as Record<string, boolean>)
  }, [overlayGroups])
  const toggleGroup = (name: string) => setGroupsOn(v => ({ ...v, [name]: !v[name] }))

  // Daily breaks: one vertical line at the start of each TRADING DAY present in the data — a
  // regular daily grid like TradingView, independent of where trades landed (the old code scoped
  // these to trade days, which is why they looked irregularly spaced). Each line is anchored to
  // that day's FIRST candle so it always lands on a real bar (weekend/holiday days have no candle
  // and so no line — separators sit between consecutive trading days). The opening day is skipped.
  const dailyBreaks = useMemo(() => {
    if (baseCandles.length === 0) return []
    const firstOfDay = new Map<number, number>()   // dayStart(UTC) → first candle time that day
    for (const c of baseCandles) {
      const day = Math.floor(c.time / DAY_MS) * DAY_MS
      if (!firstOfDay.has(day)) firstOfDay.set(day, c.time)
    }
    return Array.from(firstOfDay.values()).sort((a, b) => a - b).slice(1)
  }, [baseCandles])
  const [dayBreaksOn, setDayBreaksOn] = useState(false)

  // The on-chart Sessions legend governs everything CLOCK-driven — the session windows AND the daily
  // session breaks. One roster so the pill's count, the dot and Show/Hide-all all describe the same
  // set; counting day breaks in the pill but leaving them out of "all" would be a quiet lie.
  const clockLayerCount = useMemo(() => {
    const extra = dailyBreaks.length > 0 ? 1 : 0
    return {
      on: spec.sessions.filter(s => sessionsOn[s.name]).length + (dayBreaksOn && extra ? 1 : 0),
      total: spec.sessions.length + extra,
    }
  }, [spec.sessions, sessionsOn, dayBreaksOn, dailyBreaks.length])
  const anyClockLayerOn = clockLayerCount.on > 0
  const setAllClockLayers = (on: boolean) => { setAllSessions(on); setDayBreaksOn(on) }

  // Indicators (shipped series). One on/off per indicator; sub-pane ids tracked for removal.
  const [indicatorsOn, setIndicatorsOn] = useState<Record<string, boolean>>(
    () => Object.fromEntries(spec.indicators.map(i => [i.name, true] as [string, boolean])) as Record<string, boolean>,
  )
  useEffect(() => {
    setIndicatorsOn(Object.fromEntries(spec.indicators.map(i => [i.name, true] as [string, boolean])) as Record<string, boolean>)
  }, [spec.indicators])
  const toggleIndicator = (name: string) => setIndicatorsOn(v => ({ ...v, [name]: !v[name] }))
  const indicatorPanesRef = useRef<Map<string, string>>(new Map()) // indicator name → pane id

  // Measurement tool: click to anchor, move to preview, click to lock. One at a time.
  // Clicking a locked measurement clears it. Events bubble from the canvas so klinecharts
  // crosshair still draws — no capture layer needed.
  const [measureMode, setMeasureMode] = useState(false)
  const [measurement, setMeasurement] = useState<LockedMeasurement | null>(null)
  const [anchor, setAnchor] = useState<{ x: number; y: number; ts: number; val: number } | null>(null)
  const [liveDrag, setLiveDrag] = useState<MeasureRect | null>(null)

  // Fibonacci drawings — the source of truth is React state (each = id + its two anchor points as
  // timestamp/value), so the tool survives TF switches / data reloads (which clear klinecharts
  // overlays). A persistence effect re-creates them from state after every data change.
  const [fibs, setFibs] = useState<{ id: string; points: { timestamp: number; value: number }[] }[]>([])
  const selectedFibRef = useRef<string | null>(null)  // fib currently selected (for the Delete key)
  const ctxFibRef = useRef<string | null>(null)       // fib the right-click landed on (→ "Delete this fib")
  // Default zoom/scroll captured at init, restored by "Reset chart view" (right-click menu).
  const defaultBarSpaceRef = useRef<number | null>(null)
  const defaultOffsetRef = useRef<number | null>(null)
  // Right-click context menu (viewport-fixed at the cursor). null = closed. `fibId` = the fib the
  // cursor was over when it opened (→ "Delete this fib"); null when opened over empty chart.
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; fibId: string | null } | null>(null)

  // Price decimals for the fib level labels, inferred from the instrument's magnitude
  // (gold/JPY ~2dp, FX majors ~5dp). Good enough for a label; not used for any math.
  const pricePrecision = useMemo(() => {
    const p = spec.candles[spec.candles.length - 1]?.close ?? 1
    return p >= 20 ? 2 : 5
  }, [spec.candles])

  // Escape: cancel anchor / clear measurement and exit measure mode
  useEffect(() => {
    if (!measureMode) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setMeasureMode(false); setAnchor(null); setLiveDrag(null); setMeasurement(null) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [measureMode])

  const pixelToChart = (clientX: number, clientY: number) => {
    const el = containerRef.current
    if (!el || !chartRef.current) return null
    const rect = el.getBoundingClientRect()
    const x = clientX - rect.left
    const y = clientY - rect.top
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const res = (chartRef.current as any)?.convertFromPixel?.([{ x, y }], { paneId: 'candle_pane' })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw = (Array.isArray(res) ? res[0] : res) as any
    if (!raw) return null
    // timestamp is null when x maps to a data index outside the loaded range (e.g. y-axis area).
    // Fall back to the nearest candle's timestamp using the raw dataIndex klinecharts always sets.
    let ts: number | undefined = raw.timestamp
    if (!ts && typeof raw.dataIndex === 'number' && raw.dataIndex >= 0) {
      const idx = Math.min(raw.dataIndex, displayCandles.length - 1)
      ts = displayCandles[idx]?.time
    }
    if (!ts || raw.value == null) return null
    return { x, y, ts, val: raw.value as number }
  }

  const makeMeasureRect = (
    a: { x: number; y: number; ts: number; val: number },
    b: { x: number; y: number; ts: number; val: number },
  ): MeasureRect => ({
    x: Math.min(a.x, b.x), y: Math.min(a.y, b.y),
    w: Math.abs(b.x - a.x), h: Math.abs(b.y - a.y),
    startTs: a.ts, endTs: b.ts,
    startVal: a.val, endVal: b.val,
  })

  // Click inside the chart wrapper: clear locked measurement → anchor → lock.
  const handleChartClick = (e: React.MouseEvent) => {
    if (!measureMode) return
    if (!anchor && measurement) { setMeasurement(null); return }
    const pt = pixelToChart(e.clientX, e.clientY)
    if (!pt) return
    if (!anchor) {
      setAnchor(pt)
      setLiveDrag(null)
    } else {
      const r = makeMeasureRect(anchor, pt)
      if (r.w >= 5) setMeasurement({ id: crypto.randomUUID(), ...r })
      setAnchor(null)
      setLiveDrag(null)
    }
  }

  // Move inside the chart wrapper: update live preview while anchor is set.
  const handleChartMove = (e: React.MouseEvent) => {
    if (!measureMode || !anchor) return
    const pt = pixelToChart(e.clientX, e.clientY)
    if (!pt) return
    setLiveDrag(makeMeasureRect(anchor, pt))
  }

  // Chart inset, MEASURED from klinecharts: the right price-axis WIDTH and the bottom time-axis
  // HEIGHT of the plot. Used to line the header's Copy button up flush with the y-axis line and to
  // cap the left tool strip at the x-axis line — so the chrome forms clean right angles with the
  // plot rectangle instead of floating over the price scale / past the time axis.
  const [chartInset, setChartInset] = useState<{ axisW: number; xAxisH: number }>({ axisW: 0, xAxisH: 0 })
  const measureInset = useCallback(() => {
    const chart = chartRef.current
    if (!chart) return
    const axisW = Math.round(chart.getSize('candle_pane', DomPosition.YAxis)?.width ?? 0)
    const xAxisH = Math.round(chart.getSize('x_axis_pane', DomPosition.Root)?.height ?? 0)
    setChartInset(prev => (prev.axisW === axisW && prev.xAxisH === xAxisH ? prev : { axisW, xAxisH }))
  }, [])

  // Init once on mount; dispose on unmount. Data is applied by the effect below.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    registerChartOverlays()
    const chart = init(el)
    if (!chart) return
    chartRef.current = chart
    chart.setStyles(chartStyles)
    defaultBarSpaceRef.current = chart.getBarSpace()          // remembered for "Reset chart view"
    defaultOffsetRef.current = chart.getOffsetRightDistance()

    // Scroll-left paging. Registered ONCE (klinecharts keeps one callback) and delegating through
    // refs, so it always sees the current candles/timeframe instead of the first render's.
    chart.setLoadDataCallback(({ type, callback }) => {
      if (type !== LoadDataType.Forward || pagingOffRef.current) {
        callback([], type === LoadDataType.Forward)
        return
      }
      void loadOlderRef.current().then(({ bars, more }) => {
        if (bars.length) {
          skipApplyRef.current = true
          setBaseCandles(prev => [...bars, ...prev])
        }
        callback(candlesToKLine(bars), more)
      }).catch(() => callback([], false))
    })

    const ro = new ResizeObserver(() => { chart.resize(); measureInset() })
    ro.observe(el)
    requestAnimationFrame(measureInset)
    return () => {
      ro.disconnect()
      dispose(el)
      chartRef.current = null
      indicatorPanesRef.current.clear()
    }
  }, [measureInset])

  // (Re)feed candles whenever the displayed timeframe (or spec) changes — no re-init. Re-measure the
  // inset after: a new price range can widen/narrow the y-axis (digit count).
  useEffect(() => {
    if (!chartRef.current) return
    // A PAGE is already merged by klinecharts (which also kept the scroll position) — re-applying
    // would reset the view on every page. Everything else is a real data swap and must re-apply.
    if (skipApplyRef.current) skipApplyRef.current = false
    else chartRef.current.applyNewData(candlesToKLine(displayCandles))
    const id = requestAnimationFrame(measureInset)
    return () => cancelAnimationFrame(id)
  }, [displayCandles, measureInset])

  // Drill-down: when a sub-base TF is selected, pull its full broker depth; clear on leave.
  useEffect(() => {
    if (!isFetchMode) {
      setFetched([])
      setFetchStatus('idle')
      setDataEdge(null)
      return
    }
    runFetch(selectedMin)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFetchMode, selectedMin])

  // The chart now OPENS in drill-down (the run's own TF is usually finer than the shipped bars), so
  // a feed that can't serve it would leave a blank chart where the shipped candles used to be. Fall
  // back to those once, and only for the AUTO-chosen TF — a TF the user picked keeps its honest
  // "no data" message instead of silently jumping somewhere they didn't ask for.
  const autoFellBackRef = useRef(false)
  useEffect(() => { autoFellBackRef.current = false }, [openMin])
  useEffect(() => {
    if (autoFellBackRef.current || selectedMin !== openMin || openMin === baseMin) return
    if (fetchStatus !== 'empty' && fetchStatus !== 'error') return
    autoFellBackRef.current = true
    setSelectedMin(baseMin)
  }, [fetchStatus, selectedMin, openMin, baseMin])

  // Rebuild session overlays after data changes (applyNewData can clear them) or a toggle.
  // Declared AFTER the data effect so candles are present when overlays are created.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: SESSION_BOX })
    for (const s of sessionBoxes) {
      if (!sessionsOn[s.name]) continue
      for (const w of s.windows) {
        // Skip a session window that falls entirely outside the loaded candles (no-data region).
        if (loadedLoTs == null || loadedHiTs == null || w.t1 < loadedLoTs || w.t0 > loadedHiTs) continue
        chart.createOverlay({
          name: SESSION_BOX,
          lock: true,
          points: [
            { timestamp: w.t0, value: w.top },
            { timestamp: w.t1, value: w.bottom },
          ],
          extendData: { color: s.color },
        })
      }
    }
  }, [sessionBoxes, sessionsOn, displayCandles, loadedLoTs, loadedHiTs])  // sessionBoxes already covers all days

  // Rebuild trade overlays after data changes or a toggle (same anchoring rationale as sessions).
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: TRADE })
    if (!tradesOn) return
    for (const tr of spec.trades) {
      // Only draw a trade whose ENTRY is within the loaded candles — one older than the data edge
      // would otherwise clamp its markers onto the plot's left edge (the no-data region).
      if (loadedLoTs == null || loadedHiTs == null) break
      if (tr.entryTime < loadedLoTs || tr.entryTime > loadedHiTs) continue
      if (tr.layer && hiddenLayers.has(tr.layer)) continue   // isolated via the Strategies dropdown
      if (!(tr.pnl > 0 ? winnersOn : losersOn)) continue     // Winners/Losers filters (Analysis menu)
      chart.createOverlay({
        name: TRADE,
        lock: true,
        points: [
          { timestamp: tr.entryTime, value: tr.entryPrice },
          { timestamp: tr.exitTime, value: tr.exitPrice },
        ],
        extendData: {
          dir: tr.dir,
          kind: tr.kind,
          pnl: tr.pnl,
          color: tr.pnl > 0 ? TRADE_WIN_COLOR : TRADE_LOSS_COLOR,  // outcome (win green / loss red)
          dirColor: tr.dir === 'long' ? theme.pos : theme.neg,     // entry arrow (buy green / sell red)
          // Profit-depth inputs — prices, converted to pixels in the overlay via the y-axis.
          // Absent fields make the overlay fall back to the plain entry→exit box.
          entryPrice: tr.entryPrice,
          exitPrice: tr.exitPrice,
          mfePrice: tr.mfePrice,
          maePrice: tr.maePrice,
          profitLegs: tr.profitLegs,
          stopPrice: tr.stopPrice,
          tpTargets: tr.tpTargets,     // TP ladder — first UNHIT one drawn faintly (near-miss view)
          favColor: TRADE_PROFIT_FILL, // light mint — profit fill + take-profit lines
          advColor: TRADE_LOSS_COLOR,  // red — adverse side + the stop
          // Portfolio stack: the entry marker takes the strategy's layer colour so overlapping
          // strategies read apart; a single-run trade has no layer → neutral, unchanged.
          entryColor: tr.layerColor ?? theme.textSecondary,
          layerColor: tr.layerColor,   // outcome-chip border + dot accent (stack only)
          layerName: tr.layerName,     // named in the outcome chip: "SOS Fade · Won" (stack only)
          chipBg: theme.bgSurface,     // dark chip behind the side labels (legible over candles)
          neutralColor: theme.textTertiary,
        },
      })
    }
  }, [spec.trades, tradesOn, winnersOn, losersOn, hiddenLayers, displayCandles, loadedLoTs, loadedHiTs])

  // Blocked setups — same rebuild-on-data-change rationale as the trades effect. Each marker
  // carries its own hover handlers, which is what turns the tag into "why didn't this trade":
  // klinecharts hands back the event's pixel coordinates, and the card is rendered in React.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: BLOCK })
    setBlockTip(null)
    if (!blocksOn) return
    for (const b of blocks) {
      // Clipped to the loaded candles, like every other auto-generated overlay — klinecharts
      // clamps an out-of-range point onto the plot edge, which would pile every older marker
      // into the no-data region left of the drill-down edge.
      if (loadedLoTs == null || loadedHiTs == null) break
      if (b.time < loadedLoTs || b.time > loadedHiTs) continue
      if (!blockVisible(b)) continue                       // per-reason filters
      chart.createOverlay({
        name: BLOCK,
        lock: true,
        points: [{ timestamp: b.time, value: b.price }],
        extendData: { dir: b.dir, count: b.reasons.length, color: BLOCK_COLOR, textColor: theme.bgBase },
        onMouseEnter: (e) => {
          setBlockTip({
            x: (e.pageX ?? 0) - window.scrollX,
            y: (e.pageY ?? 0) - window.scrollY,
            b,
          })
          return true
        },
        onMouseLeave: () => { setBlockTip(null); return true },
      })
    }
  }, [blocks, blocksOn, blockVisible, displayCandles, loadedLoTs, loadedHiTs])

  // Fibonacci drawings — re-created from state after any data change (applyNewData clears overlays,
  // same rationale as the trade/session effects), so a fib survives TF switches. Each carries
  // per-instance callbacks: onSelected marks it for the Delete key; onPressedMoveEnd writes an
  // anchor-drag back to state so the move persists too.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: FIB })
    for (const f of fibs) {
      chart.createOverlay({
        name: FIB,
        id: f.id,
        points: f.points,
        extendData: { precision: pricePrecision, chipBg: theme.bgSurface },
        onSelected: () => { selectedFibRef.current = f.id; return false },
        onDeselected: () => { if (selectedFibRef.current === f.id) selectedFibRef.current = null; return false },
        // klinecharts REMOVES an overlay on right-click when onRightClick returns falsy — return true
        // to keep the fib, and stash its id so the React context menu offers "Delete this fib" instead.
        onRightClick: () => { ctxFibRef.current = f.id; return true },
        onPressedMoveEnd: e => {
          const pts = (e.overlay.points ?? [])
            .filter(p => typeof p.timestamp === 'number' && typeof p.value === 'number')
            .map(p => ({ timestamp: p.timestamp as number, value: p.value as number }))
          if (pts.length >= 2) setFibs(prev => prev.map(x => (x.id === f.id ? { ...x, points: pts } : x)))
          return false
        },
      })
    }
  }, [fibs, displayCandles, pricePrecision])

  // Rebuild generic overlays (box/hline/vline) by group, after data changes or a group toggle.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: BOX })
    chart.removeOverlay({ name: HLINE })
    chart.removeOverlay({ name: VLINE })
    chart.removeOverlay({ name: LABEL })
    const dummyValue = baseCandles[0]?.close ?? 0 // vline ignores y; needs a valid number
    // All visible structure labels go into ONE overlay so they de-collide together (see LABEL in
    // overlays.ts). Collected here, created after the loop.
    const labelPoints: { timestamp: number; value: number }[] = []
    const labelItems: LabelItem[] = []
    for (const ov of spec.overlays) {
      if (!groupsOn[ov.group]) continue
      // Nested layers: an overlay can also depend on OTHER groups being on (see `requires` in
      // types.ts). This is what makes the four market-structure toggles nest exactly like the
      // TradingView ones — e.g. swing tags vanish with the structure that owns them, and historic
      // internal content needs "Internal Structure" on as well as its own toggle.
      if (ov.requires?.some(g => groupsOn[g] === false)) continue
      // Skip any structure overlay outside the loaded candles (no-data region).
      if (loadedLoTs == null || loadedHiTs == null) break
      const oStart = ov.type === 'vline' || ov.type === 'label' ? ov.t : ov.t0
      const oEnd = ov.type === 'vline' || ov.type === 'label' ? ov.t : ov.t1
      if (oEnd < loadedLoTs || oStart > loadedHiTs) continue
      const style = {
        color: ov.style?.color ?? DEFAULT_OVERLAY_COLOR,
        fillColor: ov.style?.fillColor,
        lineStyle: ov.style?.lineStyle,
        lineWidth: ov.style?.lineWidth,
      }
      if (ov.type === 'box') {
        chart.createOverlay({
          name: BOX,
          lock: true,
          points: [
            { timestamp: ov.t0, value: ov.top },
            { timestamp: ov.t1, value: ov.bottom },
          ],
          extendData: style,
        })
      } else if (ov.type === 'hline') {
        chart.createOverlay({
          name: HLINE,
          lock: true,
          points: [
            { timestamp: ov.t0, value: ov.price },
            { timestamp: ov.t1, value: ov.price },
          ],
          extendData: { ...style, label: ov.label },
        })
      } else if (ov.type === 'vline') {
        chart.createOverlay({
          name: VLINE,
          lock: true,
          points: [{ timestamp: ov.t, value: dummyValue }],
          extendData: style,
        })
      } else if (ov.type === 'label') {
        labelPoints.push({ timestamp: ov.t, value: ov.price })
        labelItems.push({ text: ov.text, color: style.color, placement: ov.placement })
      }
    }
    if (labelPoints.length) {
      chart.createOverlay({ name: LABEL, lock: true, points: labelPoints, extendData: { items: labelItems } })
    }
  }, [spec.overlays, baseCandles, groupsOn, displayCandles, loadedLoTs, loadedHiTs])

  // Daily session-break vlines. Rebuilt after data changes (applyNewData can clear overlays).
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: DAY_BREAK })
    if (!dayBreaksOn) return
    const dummyValue = baseCandles[0]?.close ?? 0
    for (const t of dailyBreaks) {
      // Skip a day break outside the loaded candles (no-data region).
      if (loadedLoTs == null || loadedHiTs == null || t < loadedLoTs || t > loadedHiTs) continue
      chart.createOverlay({
        name: DAY_BREAK,
        lock: true,
        points: [{ timestamp: t, value: dummyValue }],
        extendData: { color: DAY_BREAK_COLOR, lineStyle: 'dashed', lineWidth: 1 },
      })
    }
  }, [dailyBreaks, dayBreaksOn, displayCandles, baseCandles, loadedLoTs, loadedHiTs])

  // Drill-down data edge — a red dashed "no earlier data" line at the broker's oldest bar for the
  // active sub-base TF, so a true feed limit reads as a hard wall (not a blank chart). Rebuilt after
  // data changes (applyNewData clears overlays), same as the other vline overlays.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: DATA_EDGE })
    if (!dataEdge || dataEdge.tf !== selectedMin) return
    // Named off the ACTIVE drill-down TF, so every rung of the ladder reads correctly.
    const tfLabel = FETCH_TFS.find(tf => tf.min === selectedMin)?.label
    const label = tfLabel ? `No earlier ${tfLabel} data` : 'No earlier data'
    chart.createOverlay({
      name: DATA_EDGE,
      lock: true,
      points: [{ timestamp: dataEdge.ts, value: displayCandles[0]?.close ?? 0 }],
      extendData: { color: theme.neg, label },
    })
  }, [dataEdge, selectedMin, displayCandles])

  // Indicators (shipped series). Created once per spec/visibility; klinecharts re-runs the
  // indicator calc automatically on TF switch, so this does NOT depend on displayCandles.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    for (const [name, paneId] of indicatorPanesRef.current) chart.removeIndicator(paneId, name)
    indicatorPanesRef.current.clear()
    spec.indicators.forEach((ind, i) => {
      if (!indicatorsOn[ind.name]) return
      ensureSeriesIndicator(ind.name)
      const create = {
        name: ind.name,
        shortName: ind.name,
        series: ind.pane === 'main' ? IndicatorSeries.Price : IndicatorSeries.Normal,
        extendData: { series: ind.series, color: INDICATOR_PALETTE[i % INDICATOR_PALETTE.length] },
      }
      if (ind.pane === 'main') {
        chart.createIndicator(create, true, { id: 'candle_pane' })
        indicatorPanesRef.current.set(ind.name, 'candle_pane')
      } else {
        const paneId = chart.createIndicator(create, false, { height: 90 })
        if (paneId) indicatorPanesRef.current.set(ind.name, paneId)
      }
    })
  }, [spec.indicators, indicatorsOn])

  const measureStats = (rect: MeasureRect) => {
    if (rect.w < 5) return null
    const priceDiff = rect.endVal - rect.startVal
    const lo = Math.min(rect.startTs, rect.endTs)
    const hi = Math.max(rect.startTs, rect.endTs)
    return {
      priceDiff,
      pctChange: (priceDiff / rect.startVal) * 100,
      bars: displayCandles.filter(c => c.time >= lo && c.time <= hi).length,
      durMs: Math.abs(rect.endTs - rect.startTs),
      up: priceDiff >= 0,
    }
  }

  const renderMeasRect = (rect: MeasureRect, key: string, strokeOpacity: number) => {
    const up = rect.endVal >= rect.startVal
    const fill = up ? 'rgba(38,166,154,0.2)' : 'rgba(239,83,80,0.2)'
    const stroke = up ? `rgba(38,166,154,${strokeOpacity})` : `rgba(239,83,80,${strokeOpacity})`
    const textColor = up ? '#26a69a' : '#ef5350'
    const stats = measureStats(rect)
    const labelW = 160
    const containerW = containerRef.current?.clientWidth ?? 9999
    const labelLeft = rect.x + rect.w + 8 + labelW > containerW ? rect.x - labelW - 8 : rect.x + rect.w + 8
    return (
      <Fragment key={key}>
        <div style={{ position: 'absolute', left: rect.x, top: rect.y, width: Math.max(rect.w, 1), height: Math.max(rect.h, 1), background: fill, border: `1px solid ${stroke}` }} />
        {stats && (
          <div style={{ position: 'absolute', left: labelLeft, top: rect.y, width: labelW, background: '#1e222d', border: `1px solid ${stroke}`, borderRadius: 5, padding: '5px 9px', fontSize: 11, fontFamily: 'ui-monospace, monospace', lineHeight: 1.7, whiteSpace: 'nowrap', color: '#e2e8f0' }}>
            <div style={{ color: textColor }}>{up ? '↑' : '↓'} {up ? '+' : '−'}{fmtDiff(stats.priceDiff)} ({up ? '+' : '−'}{Math.abs(stats.pctChange).toFixed(2)}%)</div>
            <div style={{ color: '#94a3b8' }}>{stats.bars} bar{stats.bars !== 1 ? 's' : ''} · {fmtDuration(stats.durMs)}</div>
          </div>
        )}
      </Fragment>
    )
  }

  // Copy the current chart view as a PNG — like TradingView's snapshot button. klinecharts
  // renders the canvas (candles + every overlay: trades, sessions, indicators) to a data URL;
  // we copy it to the clipboard so it pastes straight into a chat, and fall back to a download
  // when the browser blocks clipboard image writes. The React measurement layer is a separate
  // DOM overlay and is deliberately not part of the snapshot.
  const [copied, setCopied] = useState(false)
  const copyChartImage = async () => {
    const chart = chartRef.current
    if (!chart) return
    let url: string
    try {
      url = chart.getConvertPictureUrl(true, 'png', theme.bgBase)
    } catch {
      toast.error('Could not render the chart image')
      return
    }
    const toBlob = fetch(url).then(r => r.blob()) // pass the Promise to ClipboardItem (Safari-safe)
    try {
      const canClipboard = typeof ClipboardItem !== 'undefined' && !!navigator.clipboard?.write
      if (!canClipboard) throw new Error('clipboard unavailable')
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': toBlob })])
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
      toast.success('Chart copied — paste it into the chat')
    } catch {
      const blob = await toBlob
      const href = URL.createObjectURL(blob)
      const tf = options.find(o => o.min === selectedMin)?.label ?? spec.baseTimeframe.toUpperCase()
      const a = document.createElement('a')
      a.href = href
      a.download = `${spec.instrument}-${tf}.png`
      a.click()
      URL.revokeObjectURL(href)
      toast.message('Clipboard blocked — image downloaded instead')
    }
  }

  // Reset chart view (right-click menu) — restore the zoom/scroll captured at init, like TradingView.
  const resetView = () => {
    const chart = chartRef.current
    if (!chart) return
    if (defaultBarSpaceRef.current != null) chart.setBarSpace(defaultBarSpaceRef.current)
    if (defaultOffsetRef.current != null) chart.setOffsetRightDistance(defaultOffsetRef.current)
    chart.scrollToRealTime()
  }

  // Fibonacci tool — arm klinecharts' native 2-click draw. On completion lift the two anchor points
  // into React state (the source of truth); the persistence effect re-creates it (and drops the
  // transient drawing overlay). Exits measure mode first so the two tools never fight for clicks.
  const startFib = () => {
    const chart = chartRef.current
    if (!chart) return
    setMeasureMode(false); setAnchor(null); setLiveDrag(null); setMeasurement(null)
    chart.createOverlay({
      name: FIB,
      extendData: { precision: pricePrecision, chipBg: theme.bgSurface },
      onDrawEnd: e => {
        const pts = (e.overlay.points ?? [])
          .filter(p => typeof p.timestamp === 'number' && typeof p.value === 'number')
          .map(p => ({ timestamp: p.timestamp as number, value: p.value as number }))
        if (pts.length >= 2) setFibs(prev => [...prev, { id: crypto.randomUUID(), points: pts.slice(0, 2) }])
        return false
      },
    })
  }

  const removeFib = (id: string) => {
    if (selectedFibRef.current === id) selectedFibRef.current = null
    if (ctxFibRef.current === id) ctxFibRef.current = null
    setFibs(prev => prev.filter(f => f.id !== id))
  }

  // Delete/Backspace removes the selected fib (ignored while typing); Escape closes the menu.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null
      const tag = (el?.tagName ?? '').toLowerCase()
      const typing = tag === 'input' || tag === 'textarea' || !!el?.isContentEditable
      if (!typing && (e.key === 'Delete' || e.key === 'Backspace') && selectedFibRef.current) {
        const id = selectedFibRef.current
        selectedFibRef.current = null
        setFibs(prev => prev.filter(f => f.id !== id))
        e.preventDefault()
      }
      if (e.key === 'Escape') setCtxMenu(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Close the right-click menu on any click/press outside it (the menu stops its own mousedown).
  useEffect(() => {
    if (!ctxMenu) return
    const close = () => setCtxMenu(null)
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [ctxMenu])

  return (
    <div>
      {/* Header — TradingView layout: symbol/interval controls top-LEFT (timeframe + layers),
          the snapshot (Copy) top-RIGHT by the fullscreen exit. Chart TOOLS live on the vertical
          strip down the left edge of the chart body (below), not in this row. A host may inject its
          own title/exit via headerLeading/headerTrailing so its chrome shares this single top row. */}
      <div className={`relative flex items-center justify-between gap-2 flex-wrap mb-2 ${headerClassName ?? ''}`}>
        {/* Left cluster: optional host title + timeframe dropdown + layers dropdown + fetch status. */}
        <div className="flex items-center gap-2">
          {headerLeading}
          {/* Timeframe dropdown (TradingView-style): a button showing the current TF, opening a
              selectable list. Drill-down TFs (below the run's base) sit above a divider from the
              display TFs. */}
          <div ref={tfRef} className="relative">
            <button
              onClick={() => setTfOpen(o => !o)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border-subtle bg-bg-sunken text-[11px] font-mono font-medium text-text-secondary hover:text-text-primary transition-colors"
            >
              {options.find(o => o.min === selectedMin)?.label ?? spec.baseTimeframe.toUpperCase()}
              <ChevronDown className={`w-3 h-3 text-text-tertiary transition-transform ${tfOpen ? 'rotate-180' : ''}`} />
            </button>
            {tfOpen && (
              <div
                className="absolute left-0 mt-1 min-w-[92px] rounded-md border border-border-subtle bg-bg-surface py-1 shadow-lg"
                style={{ zIndex: 50 }}
              >
                {options.map((tf, i) => {
                  // a thin rule between the sub-base drill-down TFs and the run's own display TFs
                  const divider = i > 0 && options[i - 1].min < baseMin && tf.min >= baseMin
                  return (
                    <Fragment key={tf.label}>
                      {divider && <div className="my-1 border-t border-border-subtle" />}
                      <button
                        onClick={() => { setSelectedMin(tf.min); setTfOpen(false) }}
                        className={`block w-full px-3 py-1.5 text-left text-[11px] font-mono font-medium transition-colors ${
                          tf.min === selectedMin
                            ? 'bg-accent/10 text-accent'
                            : 'text-text-tertiary hover:bg-bg-sunken hover:text-text-secondary'
                        }`}
                      >
                        {tf.label}
                      </button>
                    </Fragment>
                  )
                })}
              </div>
            )}
          </div>

          {/* Analysis: what the strategy DID with its signals — the trades it took (split by
              outcome) and the setups its own rules refused (split by reason). Deliberately its own
              dropdown, separate from Structure: Structure is what the MARKET drew, Analysis is what
              to interrogate about the run. Trades ALSO toggles from the right-click chart menu —
              both drive the same `tradesOn` state. */}
          {(spec.trades.length > 0 || blocks.length > 0) && (
            <ToggleMenu
              title="Analysis"
              minWidth={188}
              items={[
                ...(spec.trades.length > 0 ? [{ key: 'trades', label: 'Trades', color: TRADE_WIN_COLOR, on: tradesOn, toggle: () => setTradesOn(o => !o), count: spec.trades.length }] : []),
                // Winners/Losers are SUB-toggles of Trades — indented, and only listed while trades
                // are on (with trades hidden they'd be inert switches). Each carries its count so the
                // split is readable without opening the trades table.
                ...(spec.trades.length > 0 && tradesOn ? [
                  { key: 'winners', label: 'Winners', color: TRADE_WIN_COLOR, on: winnersOn, toggle: () => setWinnersOn(o => !o), sub: true, count: outcomeCounts.wins },
                  { key: 'losers', label: 'Losers', color: TRADE_LOSS_COLOR, on: losersOn, toggle: () => setLosersOn(o => !o), sub: true, count: outcomeCounts.losses },
                ] : []),
                // Blocked sits under Trades — same subject (what happened to a signal), opposite
                // answer. Listed only when the run reports any: a runner that can't tell us would
                // otherwise show a permanently empty toggle.
                ...(blocks.length > 0 ? [{ key: 'blocks', label: 'Blocked', color: BLOCK_COLOR, on: blocksOn, toggle: () => setBlocksOn(o => !o), count: shownBlockCount }] : []),
                // …and one sub-toggle per REASON, so a rule can be isolated ("show me only what the
                // veto refused") or excluded. Each count is how many setups that rule refused — the
                // number this whole layer exists to produce. Same "only while the parent is on" rule
                // as Winners/Losers.
                ...(blocksOn ? blockReasons.map(r => ({
                  key: `blk-${r.label}`, label: r.label, color: BLOCK_COLOR,
                  on: !hiddenReasons.has(r.label), toggle: () => toggleReason(r.label),
                  sub: true, count: r.count,
                })) : []),
              ]}
            />
          )}

          {/* Structure: what the MARKET drew — the strategy-structure "bricks" and shipped indicators.
              Everything clock-driven (sessions, day breaks) lives in the on-chart legend instead. */}
          <ToggleMenu
            title="Structure"
            items={[
              ...overlayGroups.map(g => ({ key: `g-${g.name}`, label: g.name, color: g.color, on: groupsOn[g.name], toggle: () => toggleGroup(g.name) })),
              ...spec.indicators.map((ind, i) => ({ key: `i-${ind.name}`, label: ind.name, color: INDICATOR_PALETTE[i % INDICATOR_PALETTE.length], on: indicatorsOn[ind.name], toggle: () => toggleIndicator(ind.name) })),
            ]}
          />

          {/* Strategies: its OWN dropdown (not folded into Analysis — a stack's legs are a different
              kind of thing from a run's own trades). Appears only when the spec carries layered
              trades, i.e. a portfolio stack; a single-run chart never sees it. Toggling isolates one
              strategy's trades on the chart. */}
          {tradeLayers.length > 0 && (
            <ToggleMenu
              title="Strategies"
              minWidth={180}
              items={tradeLayers.map(l => ({
                key: l.id, label: l.name, color: l.color,
                on: !hiddenLayers.has(l.id), toggle: () => toggleLayer(l.id),
              }))}
            />
          )}

          {isFetchMode && (() => {
            // The TF itself is already shown in the dropdown — don't echo it here. Only surface a
            // STATE worth calling out (loading / feed offline / failed / at the broker's data edge).
            const warn = fetchStatus === 'empty' || fetchStatus === 'error'
            // While loading, the chart is showing the SHIPPED bars rather than nothing — say which,
            // because bars that don't match the TF button would otherwise be a silent lie.
            const text = fetchStatus === 'loading'
                ? (showingPlaceholder
                    ? `showing ${spec.baseTimeframe.toUpperCase()} — loading all available bars…`
                    : 'loading all available bars…')
              : fetchStatus === 'empty' ? 'no data (feed offline?)'
              : fetchStatus === 'error' ? 'fetch failed'
              : dataEdge ? 'all the broker still has'
              : ''
            if (!text) return null
            return <span className="text-[11px] font-mono" style={{ color: warn ? theme.gold : theme.textTertiary }}>{text}</span>
          })()}
        </div>

        {/* Right cluster: the snapshot (Copy) button — camera icon only, right-inset by the chart's
            y-axis WIDTH so its right edge lands exactly on the price-axis line (a clean right angle),
            not over the price scale. The host's exit X (headerTrailing) is pinned to the far corner,
            beyond it. */}
        <div className="flex items-center gap-2" style={{ paddingRight: chartInset.axisW }}>
          {showCopy && (
            <button
              onClick={copyChartImage}
              title={copied ? 'Copied' : 'Copy chart image to clipboard'}
              className="inline-flex items-center justify-center w-8 h-8 text-text-tertiary hover:text-text-secondary transition-colors"
            >
              {copied ? <Check className="w-[18px] h-[18px] text-accent" /> : <Camera className="w-[18px] h-[18px]" />}
            </button>
          )}
        </div>
        {headerTrailing && (
          // Centred over the price-axis (y-axis) COLUMN on the right — the rightmost `axisW` px —
          // so the minimize button sits above the price scale, not jammed in the corner.
          <div
            className="absolute top-1/2 -translate-y-1/2 flex items-center justify-center"
            style={{ right: 0, width: Math.max(chartInset.axisW, 28) }}
          >
            {headerTrailing}
          </div>
        )}
      </div>

      {/* Chart body = a vertical TOOL STRIP (far left, like TradingView's drawing toolbar) + the
          chart. The toolbar sits OUTSIDE the measure-capturing wrapper on purpose, so clicking a
          tool button never registers as a measurement click. */}
      <div className="flex">
        <div
          className="flex flex-col items-center gap-1 py-2 border-r border-border-subtle bg-bg-sunken flex-shrink-0"
          style={{ width: 40 }}
        >
          <button
            onClick={() => { setMeasureMode(m => !m); setAnchor(null); setLiveDrag(null); setMeasurement(null) }}
            title="Measure — click to anchor, move, click to lock. Click a measurement to clear."
            className={`flex items-center justify-center w-8 h-8 rounded-md border transition-colors ${
              measureMode
                ? 'border-accent/60 text-accent bg-accent/10'
                : 'border-transparent text-text-tertiary hover:text-text-secondary hover:bg-bg-surface'
            }`}
          >
            <Ruler className="w-5 h-5" />
          </button>
          <button
            onClick={startFib}
            title="Fibonacci retracement — click one swing, then the other. Right-click a fib → Delete this fib (or select it + Delete)."
            className="flex items-center justify-center w-8 h-8 rounded-md border border-transparent text-text-tertiary hover:text-text-secondary hover:bg-bg-surface transition-colors"
          >
            <AlignJustify className="w-5 h-5" />
          </button>
          {/* More tools land here. */}
        </div>

        <div
          className="flex-1"
          style={{ position: 'relative' }}
          onClick={handleChartClick}
          onMouseMove={handleChartMove}
          onContextMenu={e => {
            e.preventDefault()
            // klinecharts' right-click (mousedown, button 2) fires BEFORE this DOM contextmenu, so a
            // right-click ON a fib has already stashed its id in ctxFibRef. Read + clear it: a fib
            // right-click → fib-only menu; an empty right-click (ref null) → chart-only menu.
            const fibId = ctxFibRef.current
            ctxFibRef.current = null
            const MENU_W = 190, MENU_H = 96
            setCtxMenu({
              x: Math.min(e.clientX, window.innerWidth - MENU_W),
              y: Math.min(e.clientY, window.innerHeight - MENU_H),
              fibId,
            })
          }}
        >
          <div ref={containerRef} className="w-full" style={{ height }} />

          {/* Measurement display layer — pointer-events:none so klinecharts canvas gets all events
              (crosshair, scrolling, etc.) and our onClick/onMouseMove handlers fire via bubbling */}
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, pointerEvents: 'none', zIndex: 1 }}>
            {measurement && renderMeasRect(measurement, measurement.id, 1)}
            {liveDrag && renderMeasRect(liveDrag, 'live', 0.85)}
          </div>

          {/* Blocked-setup hover card — the "why didn't this trade" answer. `pointerEvents: none`
              so it can never eat the hover that spawned it (which would flicker it on and off), and
              viewport-`fixed` + clamped like the right-click menu, so a marker at the right or
              bottom edge of the chart still shows its whole card. */}
          {blockTip && (
            <div
              style={{
                position: 'fixed',
                left: Math.max(6, Math.min(blockTip.x + 14, window.innerWidth - BLOCK_TIP_W - 6)),
                top: Math.max(6, Math.min(blockTip.y + 12, window.innerHeight - BLOCK_TIP_H - 6)),
                width: BLOCK_TIP_W,
                pointerEvents: 'none',
                zIndex: 60,
              }}
              className="rounded-md border border-border-subtle bg-bg-surface px-2.5 py-2 shadow-lg"
            >
              <div className="text-[11px] font-semibold" style={{ color: BLOCK_COLOR }}>
                {blockTip.b.dir === 'long' ? '▲ Long' : '▼ Short'} blocked
                {blockTip.b.reasons.length > 1 && ` — ${blockTip.b.reasons.length} rules`}
              </div>
              {/* Every rule that was refusing it, in the strategy's own precedence order (primary
                  first) — the tag only carries the COUNT, so this is where the reasons live. */}
              {blockTip.b.reasons.map((r, i) => (
                <div key={i} className="mt-1.5">
                  <div className="text-[11px] font-medium text-text-primary">{r.label}</div>
                  <div className="text-[11px] leading-snug text-text-secondary">{r.reason}</div>
                </div>
              ))}
              <div className="mt-1.5 border-t border-border-subtle pt-1.5 text-[10px] text-text-tertiary">
                Limit would have rested at{' '}
                <span className="font-mono tabular-nums text-text-secondary">
                  {blockTip.b.price.toFixed(pricePrecision)}
                </span>
              </div>
            </div>
          )}

          {/* On-chart "Sessions" legend (TradingView indicator-legend style) — everything CLOCK-driven
              lives here: the session windows and the daily session breaks. Day breaks used to sit in
              the header dropdown, which put the two halves of "when did the day/session start" in two
              different places. Sits on LINE 2, directly under the pinned OHLC readout (line 1), so it
              no longer covers the statistics.
              stopPropagation so a click here never trips measure-mode anchoring. */}
          {(spec.sessions.length > 0 || dailyBreaks.length > 0) && (
            <div
              ref={sessionsLegendRef}
              className="absolute"
              style={{ top: 32, left: 8, zIndex: 2 }}
              onClick={e => e.stopPropagation()}
            >
              <button
                onClick={() => setSessionsLegendOpen(o => !o)}
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md border border-border-subtle bg-bg-surface text-[11px] font-medium text-text-secondary hover:text-text-primary transition-colors shadow-sm"
              >
                <span className="w-2 h-2 rounded-full" style={{ background: anyClockLayerOn ? theme.accent : 'transparent', boxShadow: `inset 0 0 0 1px ${theme.accent}` }} />
                Sessions
                <span className="font-mono text-text-tertiary">{clockLayerCount.on}/{clockLayerCount.total}</span>
                <ChevronDown className={`w-3 h-3 text-text-tertiary transition-transform ${sessionsLegendOpen ? 'rotate-180' : ''}`} />
              </button>
              {sessionsLegendOpen && (
                <div className="mt-1 min-w-[168px] rounded-md border border-border-subtle bg-bg-surface py-1 shadow-lg">
                  <button
                    onClick={() => setAllClockLayers(!anyClockLayerOn)}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium text-text-secondary hover:bg-bg-sunken hover:text-text-primary transition-colors"
                  >
                    {anyClockLayerOn ? <EyeOff className="w-3 h-3 text-text-tertiary" /> : <Eye className="w-3 h-3 text-text-tertiary" />}
                    {anyClockLayerOn ? 'Hide all' : 'Show all'}
                  </button>
                  <div className="my-1 border-t border-border-subtle" />
                  {spec.sessions.map(s => (
                    <button
                      key={s.name}
                      onClick={() => toggleSession(s.name)}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium transition-colors hover:bg-bg-sunken"
                    >
                      <span
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{ background: sessionsOn[s.name] ? s.color : 'transparent', boxShadow: `inset 0 0 0 1px ${s.color}`, opacity: sessionsOn[s.name] ? 1 : 0.5 }}
                      />
                      <span className={sessionsOn[s.name] ? 'text-text-primary' : 'text-text-tertiary'}>{s.name}</span>
                      {sessionsOn[s.name] && <Check className="w-3 h-3 ml-auto flex-shrink-0 text-accent" />}
                    </button>
                  ))}
                  {/* Day breaks — the DAILY session boundary, so it belongs with the session windows
                      rather than in the header. Ruled off because it draws a different shape (a
                      vertical line, not a box). */}
                  {dailyBreaks.length > 0 && (
                    <>
                      {spec.sessions.length > 0 && <div className="my-1 border-t border-border-subtle" />}
                      <button
                        onClick={() => setDayBreaksOn(o => !o)}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium transition-colors hover:bg-bg-sunken"
                      >
                        <span
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{ background: dayBreaksOn ? DAY_BREAK_COLOR : 'transparent', boxShadow: `inset 0 0 0 1px ${DAY_BREAK_COLOR}`, opacity: dayBreaksOn ? 1 : 0.5 }}
                        />
                        <span className={dayBreaksOn ? 'text-text-primary' : 'text-text-tertiary'}>Day breaks</span>
                        {dayBreaksOn && <Check className="w-3 h-3 ml-auto flex-shrink-0 text-accent" />}
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Right-click context menu (viewport-fixed at the cursor) — TradingView-style. Stops its own
          mousedown so a click inside doesn't trip the outside-close listener. */}
      {ctxMenu && (
        <div
          onMouseDown={e => e.stopPropagation()}
          className="fixed min-w-[172px] rounded-md border border-border-subtle bg-bg-surface py-1 shadow-xl"
          style={{ left: ctxMenu.x, top: ctxMenu.y, zIndex: 60 }}
        >
          {ctxMenu.fibId ? (
            // Right-clicked ON a fib → fib-only menu (managing a fib is its own context; deleting one
            // at a time, per Aaron — no reset, no bulk remove here).
            <button
              onClick={() => { removeFib(ctxMenu.fibId!); setCtxMenu(null) }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium text-neg-text hover:bg-bg-sunken transition-colors"
            >
              <Trash2 className="w-3 h-3" /> Delete this fib
            </button>
          ) : (
            // Right-clicked on empty chart → chart-only menu: reset the view + show/hide trades.
            <>
              <button
                onClick={() => { resetView(); setCtxMenu(null) }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium text-text-secondary hover:bg-bg-sunken hover:text-text-primary transition-colors"
              >
                <RotateCcw className="w-3 h-3 text-text-tertiary" /> Reset chart view
              </button>
              {spec.trades.length > 0 && (
                <button
                  onClick={() => { setTradesOn(o => !o); setCtxMenu(null) }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium text-text-secondary hover:bg-bg-sunken hover:text-text-primary transition-colors"
                >
                  {tradesOn ? <EyeOff className="w-3 h-3 text-text-tertiary" /> : <Eye className="w-3 h-3 text-text-tertiary" />}
                  {tradesOn ? 'Hide trades' : 'Show trades'}
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
