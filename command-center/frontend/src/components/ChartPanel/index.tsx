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
import { useEffect, useMemo, useRef, useState } from 'react'
import { IndicatorSeries, dispose, init, type Chart, type KLineData } from 'klinecharts'
import type { ChartCandle, ChartSpec } from './types'
import { chartStyles } from './chartStyles'
import { AUDJPY_FIXTURE } from './fixtures/audjpy'
import { BOX, DAY_BREAK, HLINE, SESSION_BOX, TRADE, VLINE, registerChartOverlays } from './overlays'
import { ensureSeriesIndicator } from './indicators'
import { sessionWindows } from './sessions'
import theme from '@/themes/electric-indigo'

const CHART_HEIGHT = 460
const DAY_MS = 24 * 60 * 60 * 1000
const TRADE_COLOR = theme.series[3] // blue, for trade arrows / lines / exit dots
const DEFAULT_OVERLAY_COLOR = theme.textTertiary // fallback when a spec overlay omits a color
const DAY_BREAK_COLOR = theme.textTertiary // muted vertical line for daily session breaks
const INDICATOR_PALETTE = [theme.gold, theme.series[4], theme.accent, theme.series[1]] // line colors

// Display-timeframe ladder for the segmented control. Filtered per spec.baseTimeframe so we
// never offer a TF finer than the strategy's own bars.
const DISPLAY_TFS = [
  { label: 'M5', min: 5 },
  { label: 'M15', min: 15 },
  { label: 'M30', min: 30 },
  { label: 'H1', min: 60 },
] as const

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

/** A colored-dot on/off chip used for every layer toggle (sessions, trades, overlays, etc.). */
function ToggleChip({ label, color, on, onClick }: { label: string; color: string; on: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-medium border transition-colors ${
        on ? 'border-border-default text-text-secondary hover:text-text-primary' : 'border-border-subtle text-text-tertiary'
      }`}
    >
      <span className="w-2 h-2 rounded-full" style={{ background: color, opacity: on ? 1 : 0.35 }} />
      {label}
    </button>
  )
}

export default function ChartPanel({ spec = AUDJPY_FIXTURE }: { spec?: ChartSpec }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<Chart | null>(null)

  const baseMin = useMemo(() => parseTfMinutes(spec.baseTimeframe), [spec.baseTimeframe])
  const options = useMemo(() => {
    const opts = DISPLAY_TFS.filter(tf => tf.min >= baseMin && tf.min % baseMin === 0)
    return opts.length ? opts : [{ label: spec.baseTimeframe.toUpperCase(), min: baseMin }]
  }, [baseMin, spec.baseTimeframe])

  // Selected display TF (minutes). Component-local UI state, not server/page state.
  const [selectedMin, setSelectedMin] = useState<number>(() => options[0].min)
  // Reset selection to the base TF when the spec (and thus its options) changes.
  useEffect(() => {
    setSelectedMin(options.find(o => o.min === baseMin)?.min ?? options[0].min)
  }, [options, baseMin])

  const displayCandles = useMemo(
    () => (selectedMin === baseMin ? spec.candles : resample(spec.candles, selectedMin * 60_000)),
    [spec.candles, selectedMin, baseMin],
  )

  // Session boxes are derived from the BASE candles (high/low envelope is TF-invariant) and
  // anchored by timestamp, so they stay put across timeframe switches.
  const sessionBoxes = useMemo(
    () => spec.sessions.map(s => ({
      name: s.name,
      color: s.color,
      windows: sessionWindows(spec.candles, s, spec.brokerGmtOffsetHours),
    })),
    [spec.candles, spec.sessions, spec.brokerGmtOffsetHours],
  )

  // Per-session visibility (component-local UI state). Defaults all on; resets with the spec.
  const [sessionsOn, setSessionsOn] = useState<Record<string, boolean>>(
    () => Object.fromEntries(spec.sessions.map(s => [s.name, true] as [string, boolean])) as Record<string, boolean>,
  )
  useEffect(() => {
    setSessionsOn(Object.fromEntries(spec.sessions.map(s => [s.name, true] as [string, boolean])) as Record<string, boolean>)
  }, [spec.sessions])
  const toggleSession = (name: string) => setSessionsOn(v => ({ ...v, [name]: !v[name] }))

  // Trades: one on/off toggle for all of them (a clickable trade list comes in Step 7).
  const [tradesOn, setTradesOn] = useState(true)

  // Generic overlays (box/hline/vline) carry strategy structure, grouped by `group`. Each group
  // is independently toggleable. The chart never knows which strategy produced them.
  const overlayGroups = useMemo(() => {
    const seen = new Map<string, string>() // group → representative (first) color
    for (const ov of spec.overlays) {
      if (!seen.has(ov.group)) seen.set(ov.group, ov.style?.color ?? DEFAULT_OVERLAY_COLOR)
    }
    return Array.from(seen, ([name, color]) => ({ name, color }))
  }, [spec.overlays])

  const [groupsOn, setGroupsOn] = useState<Record<string, boolean>>(
    () => Object.fromEntries(overlayGroups.map(g => [g.name, true] as [string, boolean])) as Record<string, boolean>,
  )
  useEffect(() => {
    setGroupsOn(Object.fromEntries(overlayGroups.map(g => [g.name, true] as [string, boolean])) as Record<string, boolean>)
  }, [overlayGroups])
  const toggleGroup = (name: string) => setGroupsOn(v => ({ ...v, [name]: !v[name] }))

  // Daily session breaks: vertical lines at each interior broker-day boundary (candle epochs
  // are broker wall-clock, so day boundaries fall on DAY_MS multiples). Left edge is skipped.
  const dailyBreaks = useMemo(() => {
    if (spec.candles.length === 0) return []
    const tMin = spec.candles[0].time
    const tMax = spec.candles[spec.candles.length - 1].time
    const out: number[] = []
    let b = Math.ceil(tMin / DAY_MS) * DAY_MS
    if (b === tMin) b += DAY_MS // skip the boundary sitting on the very first bar
    for (; b <= tMax; b += DAY_MS) out.push(b)
    return out
  }, [spec.candles])
  const [dayBreaksOn, setDayBreaksOn] = useState(true)

  // Indicators (shipped series). One on/off per indicator; sub-pane ids tracked for removal.
  const [indicatorsOn, setIndicatorsOn] = useState<Record<string, boolean>>(
    () => Object.fromEntries(spec.indicators.map(i => [i.name, true] as [string, boolean])) as Record<string, boolean>,
  )
  useEffect(() => {
    setIndicatorsOn(Object.fromEntries(spec.indicators.map(i => [i.name, true] as [string, boolean])) as Record<string, boolean>)
  }, [spec.indicators])
  const toggleIndicator = (name: string) => setIndicatorsOn(v => ({ ...v, [name]: !v[name] }))
  const indicatorPanesRef = useRef<Map<string, string>>(new Map()) // indicator name → pane id

  // Init once on mount; dispose on unmount. Data is applied by the effect below.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    registerChartOverlays()
    const chart = init(el)
    if (!chart) return
    chartRef.current = chart
    chart.setStyles(chartStyles)

    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(el)
    return () => {
      ro.disconnect()
      dispose(el)
      chartRef.current = null
      indicatorPanesRef.current.clear()
    }
  }, [])

  // (Re)feed candles whenever the displayed timeframe (or spec) changes — no re-init.
  useEffect(() => {
    chartRef.current?.applyNewData(candlesToKLine(displayCandles))
  }, [displayCandles])

  // Rebuild session overlays after data changes (applyNewData can clear them) or a toggle.
  // Declared AFTER the data effect so candles are present when overlays are created.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: SESSION_BOX })
    for (const s of sessionBoxes) {
      if (!sessionsOn[s.name]) continue
      for (const w of s.windows) {
        chart.createOverlay({
          name: SESSION_BOX,
          lock: true,
          points: [
            { timestamp: w.t0, value: w.top },
            { timestamp: w.t1, value: w.bottom },
          ],
          extendData: { color: s.color, label: s.name },
        })
      }
    }
  }, [sessionBoxes, sessionsOn, displayCandles])

  // Rebuild trade overlays after data changes or a toggle (same anchoring rationale as sessions).
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: TRADE })
    if (!tradesOn) return
    for (const tr of spec.trades) {
      chart.createOverlay({
        name: TRADE,
        lock: true,
        points: [
          { timestamp: tr.entryTime, value: tr.entryPrice },
          { timestamp: tr.exitTime, value: tr.exitPrice },
        ],
        extendData: { dir: tr.dir, color: TRADE_COLOR },
      })
    }
  }, [spec.trades, tradesOn, displayCandles])

  // Rebuild generic overlays (box/hline/vline) by group, after data changes or a group toggle.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: BOX })
    chart.removeOverlay({ name: HLINE })
    chart.removeOverlay({ name: VLINE })
    const dummyValue = spec.candles[0]?.close ?? 0 // vline ignores y; needs a valid number
    for (const ov of spec.overlays) {
      if (!groupsOn[ov.group]) continue
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
      }
    }
  }, [spec.overlays, spec.candles, groupsOn, displayCandles])

  // Daily session-break vlines. Rebuilt after data changes (applyNewData can clear overlays).
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: DAY_BREAK })
    if (!dayBreaksOn) return
    const dummyValue = spec.candles[0]?.close ?? 0
    for (const t of dailyBreaks) {
      chart.createOverlay({
        name: DAY_BREAK,
        lock: true,
        points: [{ timestamp: t, value: dummyValue }],
        extendData: { color: DAY_BREAK_COLOR, lineStyle: 'dashed', lineWidth: 1 },
      })
    }
  }, [dailyBreaks, dayBreaksOn, displayCandles, spec.candles])

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

  return (
    <div>
      <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
        {/* Layer toggles (left): sessions, trades, overlay groups, indicators, day breaks */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {spec.sessions.map(s => (
            <ToggleChip key={`s-${s.name}`} label={s.name} color={s.color} on={sessionsOn[s.name]} onClick={() => toggleSession(s.name)} />
          ))}
          {spec.trades.length > 0 && (
            <ToggleChip label="Trades" color={TRADE_COLOR} on={tradesOn} onClick={() => setTradesOn(o => !o)} />
          )}
          {overlayGroups.map(g => (
            <ToggleChip key={`g-${g.name}`} label={g.name} color={g.color} on={groupsOn[g.name]} onClick={() => toggleGroup(g.name)} />
          ))}
          {spec.indicators.map((ind, i) => (
            <ToggleChip
              key={`i-${ind.name}`}
              label={ind.name}
              color={INDICATOR_PALETTE[i % INDICATOR_PALETTE.length]}
              on={indicatorsOn[ind.name]}
              onClick={() => toggleIndicator(ind.name)}
            />
          ))}
          {dailyBreaks.length > 0 && (
            <ToggleChip label="Day breaks" color={DAY_BREAK_COLOR} on={dayBreaksOn} onClick={() => setDayBreaksOn(o => !o)} />
          )}
        </div>

        {/* Timeframe segmented control (right) */}
        <div className="inline-flex items-center gap-0.5 rounded-md border border-border-subtle bg-bg-sunken p-0.5">
          {options.map(tf => (
            <button
              key={tf.label}
              onClick={() => setSelectedMin(tf.min)}
              className={`px-2.5 py-1 rounded text-[11px] font-mono font-medium transition-colors ${
                tf.min === selectedMin ? 'bg-accent/15 text-accent' : 'text-text-tertiary hover:text-text-secondary'
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </div>
      <div ref={containerRef} className="w-full" style={{ height: CHART_HEIGHT }} />
    </div>
  )
}
