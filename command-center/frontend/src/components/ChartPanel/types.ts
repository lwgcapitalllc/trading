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

/** One profit-take rung: the price it banked at + a display label (TP1/TP2/TP3/Exit). */
export interface ChartProfitLeg {
  price: number
  label: string
}

/** One round-trip trade: entry → exit, drawn as a profit-depth view.
 *
 *  Two shades of green show how far price went in the trade's favour: SOLID from entry to where
 *  profit was actually banked (`profitLegs` / the exit), FAINT from there to the deepest point it
 *  ran (`mfePrice`) without banking. A green line marks each real profit-take. A loser also draws
 *  red toward its worst adverse price (`maePrice`). The rich fields are OPTIONAL — a trade without
 *  them degrades to the plain entry→exit box (any runner, any strategy). */
export interface ChartTrade {
  id: string
  dir: TradeDir
  entryTime: EpochMs
  entryPrice: number
  exitTime: EpochMs
  exitPrice: number
  pnl: number           // trade net P&L — sign picks the outcome colour (win green / loss red)
  kind?: 'primary' | 'secondary'  // 15m primary vs 1m sniper re-entry; solid vs dashed border
  exitReason?: string   // carried in data; never drawn on the chart
  // Profit-depth fields — all optional; absent ⇒ the trade falls back to the plain box.
  mfePrice?: number             // deepest FAVOURABLE price the hold reached (bottom of the green for a short)
  maePrice?: number             // deepest ADVERSE price the hold reached (drives a loser's red depth)
  profitLegs?: ChartProfitLeg[] // where profit was actually taken → one labelled dotted line each
  stopPrice?: number            // initial 1R stop → a bubble + dotted risk line
  tpTargets?: number[]          // TP target ladder (nearest→furthest); first UNHIT one drawn faintly
  // Portfolio-stack layering — OPTIONAL, absent on a single-run spec. `layer` names the strategy the
  // trade belongs to (so a host can filter to the toggled-on strategies); `layerColor` tints the
  // entry marker + outcome chip so overlapping strategies read apart; `layerName` is the human name
  // printed IN the outcome chip ("SOS Fade · Won"). A single-run chart omits all three.
  layer?: string
  layerColor?: string
  layerName?: string
}

/** One rule that was refusing a setup. `label` is the short name the per-reason filter is keyed on;
 *  `reason` is the full sentence shown on hover. Both are the STRATEGY's own words. */
export interface ChartBlockReason {
  label: string
  reason: string
}

/** A setup the strategy had ready and its OWN rules refused — no order was placed, so it exists in
 *  no trade list and no equity curve. Drawn as a dotted line pointing at `price` (the exact level
 *  the entry would have rested at) with a uniform "Blocked" tag parked clear of the candles; the
 *  reasons are on hover.
 *
 *  `reasons` is a LIST because several rules can refuse the same setup at once — that is what lets
 *  the panel filter by reason without lying (a setup blocked by the veto stays a veto block even
 *  when something else was also blocking it). Ordered by the strategy's precedence, primary first.
 *
 *  Generic on purpose: the panel renders these strings verbatim, derives its filter roster from
 *  them, and knows nothing about what any particular rule means — so a strategy with an entirely
 *  different rule set needs no chart change. */
export interface ChartBlock {
  id: string
  time: EpochMs
  dir: TradeDir      // the side that was refused — tag sits below for a long, above for a short
  price: number      // where the entry limit would have rested
  reasons: ChartBlockReason[]
}

/** Generic styling hints shared by overlays. All optional — the panel has defaults. */
export interface OverlayStyle {
  color?: string
  fillColor?: string
  lineStyle?: 'solid' | 'dashed'
  lineWidth?: number
}

/** Extra groups that must ALSO be toggled on for this overlay to draw — the emitter's way of
 *  expressing a NESTED layer without inventing a second toggle. The market-structure overlays use
 *  it to mirror the TradingView toggles: a swing-point tag needs its owning structure on
 *  ("External Structure" / "Internal Structure"), and historic internal content needs
 *  "Internal Structure" on top of its own group. Absent = the overlay's own group is the only gate. */
type OverlayRequires = { requires?: string[] }

/** A filled rectangle spanning a time and price range (e.g. a range box). */
export interface BoxOverlay extends OverlayRequires {
  type: 'box'
  group: string
  t0: EpochMs
  t1: EpochMs
  top: number
  bottom: number
  style?: OverlayStyle
}

/** A horizontal price level over a time span (e.g. a buy/sell level). */
export interface HLineOverlay extends OverlayRequires {
  type: 'hline'
  group: string
  t0: EpochMs
  t1: EpochMs
  price: number
  label?: string
  style?: OverlayStyle
}

/** A vertical time marker (e.g. a session break). */
export interface VLineOverlay extends OverlayRequires {
  type: 'vline'
  group: string
  t: EpochMs
  style?: OverlayStyle
}

/** A text label pinned at a single (time, price) point — e.g. a BOS/SOS break tag or an
 *  HH/HL/LH/LL swing-point label from the market-structure engine. `placement` nudges it above /
 *  below the anchor (a high label sits above the price, a low label below). */
export interface LabelOverlay extends OverlayRequires {
  type: 'label'
  group: string
  t: EpochMs
  price: number
  text: string
  placement?: 'above' | 'below' | 'center'
  style?: OverlayStyle
}

export type ChartOverlay = BoxOverlay | HLineOverlay | VLineOverlay | LabelOverlay

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
  // Refused setups. OPTIONAL — a runner that can't report them (NT8/MT5) omits the key, which is
  // what makes the Blocked layer vanish rather than render an empty, misleading toggle.
  blocks?: ChartBlock[]
  overlays: ChartOverlay[]      // generic strategy structure, each tagged with a `group`
  indicators: ChartIndicator[]
}
