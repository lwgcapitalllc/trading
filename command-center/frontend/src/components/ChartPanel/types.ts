/**
 * ChartSpec — the contract the backtest lab emits per run, and the only thing the
 * ChartPanel knows how to read. The panel renders whatever the spec declares and
 * contains ZERO strategy-specific logic: no instrument names, no session names, no
 * breakout/range concepts are hardcoded. Adding a new strategy later means its spec
 * lists different `sessions`/`overlays`/`indicators` — the chart code does not change.
 *
 * All times are epoch MILLISECONDS — KLineChart's native time unit. Convert at the
 * emitter (the lab), never inside the browser.
 */

/** Epoch milliseconds. KLineChart's native time unit. */
export type EpochMs = number

/** Base-timeframe OHLC bar. `volume` optional. */
export interface ChartCandle {
  time: EpochMs
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

/** A market session window, placed from `tz` + the spec's broker GMT offset. */
export interface ChartSession {
  name: string   // display label, e.g. "Tokyo"
  tz: string     // IANA timezone, e.g. "Asia/Tokyo"
  start: string  // "HH:MM" local to `tz`
  end: string    // "HH:MM" local to `tz`
  color: string  // hex / rgba — the session box tint
}

export type TradeDir = 'long' | 'short'

/** One round-trip trade: entry → exit. */
export interface ChartTrade {
  id: string
  dir: TradeDir
  entryTime: EpochMs
  entryPrice: number
  exitTime: EpochMs
  exitPrice: number
  exitReason?: string  // carried in data; never drawn on the chart
}

/** Generic styling hints shared by overlays. All optional — the panel has defaults. */
export interface OverlayStyle {
  color?: string
  fillColor?: string
  lineStyle?: 'solid' | 'dashed'
  lineWidth?: number
}

/** A filled rectangle spanning a time and price range (e.g. a range box). */
export interface BoxOverlay {
  type: 'box'
  group: string
  t0: EpochMs
  t1: EpochMs
  top: number
  bottom: number
  style?: OverlayStyle
}

/** A horizontal price level over a time span (e.g. a buy/sell level). */
export interface HLineOverlay {
  type: 'hline'
  group: string
  t0: EpochMs
  t1: EpochMs
  price: number
  label?: string
  style?: OverlayStyle
}

/** A vertical time marker (e.g. a session break). */
export interface VLineOverlay {
  type: 'vline'
  group: string
  t: EpochMs
  style?: OverlayStyle
}

export type ChartOverlay = BoxOverlay | HLineOverlay | VLineOverlay

/**
 * An indicator series shipped FROM the run — not recomputed in the browser, so the
 * chart shows exactly what the strategy saw. `pane: "main"` overlays the price; `"sub"`
 * gets its own pane below.
 */
export interface ChartIndicator {
  name: string
  params?: Record<string, unknown>
  pane: 'main' | 'sub'
  series: Array<{ time: EpochMs; value: number }>
}

export interface ChartSpec {
  instrument: string            // e.g. "AUDJPY.s"
  baseTimeframe: string         // finest TF the strategy used, e.g. "M5"
  brokerGmtOffsetHours: number  // for correct session placement
  candles: ChartCandle[]        // base-TF OHLC
  sessions: ChartSession[]
  trades: ChartTrade[]
  overlays: ChartOverlay[]      // generic strategy structure, each tagged with a `group`
  indicators: ChartIndicator[]
}
