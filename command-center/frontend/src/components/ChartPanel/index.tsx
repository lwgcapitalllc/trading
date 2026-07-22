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
import { DomPosition, IndicatorSeries, dispose, init, type Chart, type KLineData } from 'klinecharts'
import type { ChartCandle, ChartSpec } from './types'
import { chartStyles } from './chartStyles'
import { AUDJPY_FIXTURE } from './fixtures/audjpy'
import { BOX, DATA_EDGE, DAY_BREAK, FIB, HLINE, LABEL, type LabelItem, SESSION_BOX, STRUCTURE_GROUPS, STRUCTURE_GROUP_COLOR, TRADE, VLINE, registerChartOverlays } from './overlays'
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
const DEFAULT_OVERLAY_COLOR = theme.textTertiary // fallback when a spec overlay omits a color
const DAY_BREAK_COLOR = theme.textTertiary // muted vertical line for daily session breaks
const INDICATOR_PALETTE = [theme.gold, theme.series[4], theme.accent, theme.series[1]] // line colors

type TfOption = { label: string; min: number }

// Display-timeframe ladder for the segmented control. Filtered per spec.baseTimeframe so we
// never offer a TF finer than the strategy's own bars (those come from the drill-down below).
const DISPLAY_TFS: readonly TfOption[] = [
  { label: 'M5', min: 5 },
  { label: 'M15', min: 15 },
  { label: 'M30', min: 30 },
  { label: 'H1', min: 60 },
]

// Drill-down timeframes BELOW the run's base bars — pulled live from the broker (they can't be
// resampled UP from the base). Offered only when an `onRequestCandles` fetcher is wired.
const FETCH_TFS: readonly TfOption[] = [
  { label: 'M1', min: 1 },
  { label: 'M5', min: 5 },
]

// How far back to REQUEST each drill-down TF — deliberately MORE than the broker's known depth
// (~30d of M1, ~240d of M5) so the fetch always reaches the feed's true edge, which the backend then
// reports as a hard limit (the red "no earlier data" line). The backend caps the candle volume.
const FETCH_TF_LOOKBACK_DAYS: Record<number, number> = { 1: 45, 5: 270 }

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

  // Selected display TF (minutes). Component-local UI state. Defaults to the base TF (not
  // options[0], which is now the finest drill-down TF).
  const [selectedMin, setSelectedMin] = useState<number>(() => baseMin)
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

  // Layers multi-select dropdown open state + click-outside to close (stays open while toggling).
  const [layersOpen, setLayersOpen] = useState(false)
  const layersRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!layersOpen) return
    const onDown = (e: MouseEvent) => {
      if (layersRef.current && !layersRef.current.contains(e.target as Node)) setLayersOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [layersOpen])
  // Reset selection to the base TF when the spec (and thus its options) changes.
  useEffect(() => {
    setSelectedMin(options.find(o => o.min === baseMin)?.min ?? options[0].min)
  }, [options, baseMin])

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

  const displayCandles = useMemo(() => {
    if (isFetchMode) return fetched
    return selectedMin === baseMin ? spec.candles : resample(spec.candles, selectedMin * 60_000)
  }, [isFetchMode, fetched, spec.candles, selectedMin, baseMin])

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
    const label = min === 1 ? 'M1' : min === 5 ? 'M5' : `M${min}`
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

  // Session boxes are derived from the BASE candles (high/low envelope is TF-invariant) and
  // anchored by timestamp, so they stay put across timeframe switches. Show on ALL candle days.
  const sessionBoxes = useMemo(
    () => spec.sessions.map(s => ({
      name: s.name,
      color: s.color,
      windows: sessionWindows(spec.candles, s, spec.brokerGmtOffsetHours),
    })),
    [spec.candles, spec.sessions, spec.brokerGmtOffsetHours],
  )

  // Per-session visibility (component-local UI state). Defaults all OFF — the chart opens on just
  // the trades; sessions are opt-in from the Layers dropdown. Resets with the spec.
  const [sessionsOn, setSessionsOn] = useState<Record<string, boolean>>(
    () => Object.fromEntries(spec.sessions.map(s => [s.name, false] as [string, boolean])) as Record<string, boolean>,
  )
  useEffect(() => {
    setSessionsOn(Object.fromEntries(spec.sessions.map(s => [s.name, false] as [string, boolean])) as Record<string, boolean>)
  }, [spec.sessions])
  const toggleSession = (name: string) => setSessionsOn(v => ({ ...v, [name]: !v[name] }))
  const setAllSessions = (on: boolean) => setSessionsOn(Object.fromEntries(spec.sessions.map(s => [s.name, on])) as Record<string, boolean>)
  const anySessionOn = spec.sessions.some(s => sessionsOn[s.name])
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
  // would be unreadable with all of BOS/SOS/swings/internal drawn by default), toggled from Layers.
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
    if (spec.candles.length === 0) return []
    const firstOfDay = new Map<number, number>()   // dayStart(UTC) → first candle time that day
    for (const c of spec.candles) {
      const day = Math.floor(c.time / DAY_MS) * DAY_MS
      if (!firstOfDay.has(day)) firstOfDay.set(day, c.time)
    }
    return Array.from(firstOfDay.values()).sort((a, b) => a - b).slice(1)
  }, [spec.candles])
  const [dayBreaksOn, setDayBreaksOn] = useState(false)

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
    chartRef.current.applyNewData(candlesToKLine(displayCandles))
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
          entryColor: theme.textSecondary, // neutral — entry bubble/line/chip
          chipBg: theme.bgSurface,     // dark chip behind the side labels (legible over candles)
          neutralColor: theme.textTertiary,
        },
      })
    }
  }, [spec.trades, tradesOn, displayCandles, loadedLoTs, loadedHiTs])

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
    const dummyValue = spec.candles[0]?.close ?? 0 // vline ignores y; needs a valid number
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
  }, [spec.overlays, spec.candles, groupsOn, displayCandles, loadedLoTs, loadedHiTs])

  // Daily session-break vlines. Rebuilt after data changes (applyNewData can clear overlays).
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: DAY_BREAK })
    if (!dayBreaksOn) return
    const dummyValue = spec.candles[0]?.close ?? 0
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
  }, [dailyBreaks, dayBreaksOn, displayCandles, spec.candles, loadedLoTs, loadedHiTs])

  // Drill-down data edge — a red dashed "no earlier data" line at the broker's oldest bar for the
  // active sub-base TF, so a true feed limit reads as a hard wall (not a blank chart). Rebuilt after
  // data changes (applyNewData clears overlays), same as the other vline overlays.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: DATA_EDGE })
    if (!dataEdge || dataEdge.tf !== selectedMin) return
    const label = selectedMin === 1 ? 'No earlier 1-minute data'
      : selectedMin === 5 ? 'No earlier 5-minute data'
      : 'No earlier data'
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

          {/* Layers: multi-select dropdown for Trades, the strategy-structure "bricks", indicators,
              and day breaks. Sessions live in their own on-chart legend (below). Trades ALSO toggles
              from the right-click chart menu — both drive the same `tradesOn` state. Toggling keeps
              the menu open. */}
          <div ref={layersRef} className="relative">
            {(() => {
              const items = [
                ...(spec.trades.length > 0 ? [{ key: 'trades', label: 'Trades', color: TRADE_WIN_COLOR, on: tradesOn, toggle: () => setTradesOn(o => !o) }] : []),
                ...overlayGroups.map(g => ({ key: `g-${g.name}`, label: g.name, color: g.color, on: groupsOn[g.name], toggle: () => toggleGroup(g.name) })),
                ...spec.indicators.map((ind, i) => ({ key: `i-${ind.name}`, label: ind.name, color: INDICATOR_PALETTE[i % INDICATOR_PALETTE.length], on: indicatorsOn[ind.name], toggle: () => toggleIndicator(ind.name) })),
                ...(dailyBreaks.length > 0 ? [{ key: 'daybreaks', label: 'Day breaks', color: DAY_BREAK_COLOR, on: dayBreaksOn, toggle: () => setDayBreaksOn(o => !o) }] : []),
              ]
              const activeCount = items.filter(it => it.on).length
              return (
                <>
                  <button
                    onClick={() => setLayersOpen(o => !o)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border-subtle bg-bg-sunken text-[11px] font-medium text-text-secondary hover:text-text-primary transition-colors"
                  >
                    Layers
                    <span className="font-mono text-text-tertiary">{activeCount}/{items.length}</span>
                    <ChevronDown className={`w-3 h-3 text-text-tertiary transition-transform ${layersOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {layersOpen && (
                    <div className="absolute left-0 mt-1 min-w-[172px] rounded-md border border-border-subtle bg-bg-surface py-1 shadow-lg" style={{ zIndex: 50 }}>
                      {items.map(it => (
                        <button
                          key={it.key}
                          onClick={it.toggle}
                          className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium transition-colors hover:bg-bg-sunken"
                        >
                          <span
                            className="w-2 h-2 rounded-full flex-shrink-0"
                            style={{ background: it.on ? it.color : 'transparent', boxShadow: `inset 0 0 0 1px ${it.color}`, opacity: it.on ? 1 : 0.5 }}
                          />
                          <span className={it.on ? 'text-text-primary' : 'text-text-tertiary'}>{it.label}</span>
                          {it.on && <Check className="w-3 h-3 ml-auto flex-shrink-0 text-accent" />}
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )
            })()}
          </div>

          {isFetchMode && (() => {
            // The TF itself is already shown in the dropdown — don't echo it here. Only surface a
            // STATE worth calling out (loading / feed offline / failed / at the broker's data edge).
            const warn = fetchStatus === 'empty' || fetchStatus === 'error'
            const text = fetchStatus === 'loading' ? 'loading all available bars…'
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
          <button
            onClick={copyChartImage}
            title={copied ? 'Copied' : 'Copy chart image to clipboard'}
            className="inline-flex items-center justify-center w-8 h-8 text-text-tertiary hover:text-text-secondary transition-colors"
          >
            {copied ? <Check className="w-[18px] h-[18px] text-accent" /> : <Camera className="w-[18px] h-[18px]" />}
          </button>
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

          {/* On-chart "Sessions" legend (TradingView indicator-legend style) — the one place sessions
              are managed now that they're out of the Layers dropdown. Sits on LINE 2, directly under
              the pinned OHLC readout (line 1), so it no longer covers the statistics.
              stopPropagation so a click here never trips measure-mode anchoring. */}
          {spec.sessions.length > 0 && (
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
                <span className="w-2 h-2 rounded-full" style={{ background: anySessionOn ? theme.accent : 'transparent', boxShadow: `inset 0 0 0 1px ${theme.accent}` }} />
                Sessions
                <span className="font-mono text-text-tertiary">{spec.sessions.filter(s => sessionsOn[s.name]).length}/{spec.sessions.length}</span>
                <ChevronDown className={`w-3 h-3 text-text-tertiary transition-transform ${sessionsLegendOpen ? 'rotate-180' : ''}`} />
              </button>
              {sessionsLegendOpen && (
                <div className="mt-1 min-w-[168px] rounded-md border border-border-subtle bg-bg-surface py-1 shadow-lg">
                  <button
                    onClick={() => setAllSessions(!anySessionOn)}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium text-text-secondary hover:bg-bg-sunken hover:text-text-primary transition-colors"
                  >
                    {anySessionOn ? <EyeOff className="w-3 h-3 text-text-tertiary" /> : <Eye className="w-3 h-3 text-text-tertiary" />}
                    {anySessionOn ? 'Hide all' : 'Show all'}
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
