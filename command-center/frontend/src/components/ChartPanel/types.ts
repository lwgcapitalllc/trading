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

/** Base-timeframe OHLC bar.
 *
 *  `volume` is the bar's TICK volume, as the feed reported it, and it is OPTIONAL in the strong
 *  sense: absent means we do not have it (a bar cache written before the pipeline carried volume,
 *  or a runner whose feed has none), never that the bar traded nothing. klinecharts renders the
 *  absence as `n/a` in its OHLC readout, which is the honest answer; a fabricated 0 would read as
 *  a dead session. Nothing PLOTS it today — the session VWAP arrives as a computed series — so it
 *  is on the wire for the readout, and for whatever draws a volume pane next. */
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
  name: string // display label, e.g. "Tokyo"
  tz: string // IANA timezone, e.g. "Asia/Tokyo"
  start: string // "HH:MM" local to `tz`
  end: string // "HH:MM" local to `tz`
  color: string // hex / rgba — the session box tint
}

export type TradeDir = 'long' | 'short'

/** One profit-take rung: the price it banked at + a display label (TP1/TP2/TP3/Exit). */
export interface ChartProfitLeg {
  price: number
  label: string
}

/** One rung of a trade's exit ladder: the price it sits at, plus whether the trade actually
 *  places an ORDER there. `banks: false` means nothing is ever sold at that price and touching it
 *  only steps the stop — so it is not a target and must not be drawn with a target's name.
 *  ⚠ `banks` ABSENT means the strategy did not report it, which is not the same as `false`: every
 *  run stored before 2026-08-21 carries bare prices, and reading those as "banks nothing" would
 *  relabel every historical chart off a measurement nobody made. */
export interface ChartTpRung {
  price: number
  banks?: boolean
}

/** One rung of a trade's own fib leg: a ratio and the price the STRATEGY read for it. */
export interface ChartFibLevel {
  ratio: number
  price: number
}

/** The fib LEG a trade was priced off — recorded by the strategy when it placed the order, not
 *  recomputed here. `levels` is the whole ladder at the prices the strategy had in hand, so the
 *  chart and the bot can never disagree about where a level sat.
 *
 *  `entryRatio` / `deepestRatio` are what the ladder cannot say on its own and are the reason this
 *  exists: where the fill landed ON the leg (0.702 = it filled at the 70.2% retrace) and how far
 *  the retracement ran afterwards. `deepestRatio` legitimately exceeds 1 on a trade that traded
 *  through the leg origin.
 *
 *  `startTime` is the bar the leg began on, which is where the drawing starts — a ladder beginning
 *  at the entry would hide the retracement that produced it. Absent ⇒ start at the entry.
 *
 *  OPTIONAL on the trade: a runner or strategy that records no fib carries none, and the panel's
 *  Trade fibs toggle then never appears. */
export interface ChartTradeFib {
  levels: ChartFibLevel[]
  entryRatio?: number
  deepestRatio?: number
  startTime?: EpochMs
}

/** How a closed trade is graded. `scratch` means it landed inside the run's scratch band — near
 *  enough to flat that calling it a win or a loss says more than the trade did. */
export type TradeOutcome = 'won' | 'scratch' | 'lost'

/** One scale-in lot — a POSITION in its own right, and shaped like one.
 *
 *  A lot is bought at its own price, runs its own distance, goes its own distance against, and
 *  comes off somewhere. Until 2026-08-19 the record was the first three fields and the chart could
 *  therefore draw only *a lot was bought here*; the questions a reader actually asks of a trade —
 *  how far did it run, what was its drawdown, where did it exit — had no answer in the data.
 *
 *  ⚠ Everything past `qty` is OPTIONAL and absent together: a run stored before the strategy
 *  recorded them carries the first three keys and nothing backfills it, so the `Scale-in detail`
 *  layer stays empty for it and the plain `Add` line is all there is. **Absent is not zero** — a
 *  lot with no `exitPrice` is one nothing closed, not one that exited at 0.00. */
export interface ChartTradeAdd {
  price: number
  ms: EpochMs
  qty: number
  mfePrice?: number // deepest FAVOURABLE price this lot reached, measured from ITS OWN fill
  maePrice?: number // deepest ADVERSE price this lot reached — the lot's drawdown, not the base's
  exitPrice?: number // where the lot came off
  exitTime?: EpochMs // when it came off
  exitReason?: string // the exit leg that took it (`L-ATP` = the adds' own target, `L-SL`, …)
  pnl?: number // the lot's own P&L, in account currency
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
  pnl: number // trade net P&L — the fallback outcome test when `outcome` is absent
  /** WON / SCRATCH / LOST as the BACKEND graded it, against the run's own median full loss — the
   *  same bar the run's `scratch_count` KPI uses. OPTIONAL: a run with no losing trade cannot be
   *  graded and carries none, and the chart then falls back to the sign of `pnl`.
   *
   *  A scratch is a THIRD state, not a nicer word for a small loss. `pnl > 0` alone calls a trade
   *  that netted exactly $0.00 a LOSS — which is what a scale-in add handing back the profit its
   *  stop had locked produces (8 trades on run 295a6ff29d21). */
  outcome?: TradeOutcome
  /** Scale-in lots bought AFTER the entry, one per fill. Absent on every trade that never added.
   *
   *  Load-bearing for reading the box, not decoration: `entryPrice`, `exitPrice` and `pnl` alone
   *  can describe a short exiting BELOW its entry for a P&L of zero, and the missing half of that
   *  arithmetic is these lots — bought further into profit, closed at the same exit. */
  adds?: ChartTradeAdd[]
  /** Which BOOK this trade belongs to. `primary` is the strategy's own setup; `secondary` is the
   *  fast-feed sniper re-entry; `recovery` is a counter-trade the loss-recovery rule took after a loss.
   *
   *  ⚠ It changes the TAG in the outcome chip and nothing else. Every kind is drawn with the same
   *  profit-depth figures off the same fields, because a recovery trade is a trade — it has an
   *  entry, an excursion, an exit and a P&L, and drawing it any other way would be a second
   *  rendering of the same thing, free to drift. A kind that arrived here without its excursion
   *  fields used to degrade to a bare rectangle, which read as a different KIND of thing rather
   *  than as a thinner record. */
  kind?: 'primary' | 'secondary' | 'recovery'
  /** For a `secondary` only: what the trade it FOLLOWED did — `breakeven` is a scratch, `stopped`
   *  is a full stop-out. It decides the tag (`BE+` / `SL+`), because which of the two happened is
   *  the reason there is a second trade on the leg at all.
   *
   *  ⚠ ABSENT means the run could not tell, not "breakeven". A re-entry can be armed through a
   *  precondition that asks nothing of the trade before it, and a run stored before 2026-08-21
   *  carries no `after` at all — both degrade to the plain `SEC` tag. */
  after?: 'breakeven' | 'stopped' | 'closed'
  exitReason?: string // carried in data; never drawn on the chart
  // Profit-depth fields — all optional; absent ⇒ the trade falls back to the plain box.
  mfePrice?: number // deepest FAVOURABLE price the hold reached (bottom of the green for a short)
  maePrice?: number // deepest ADVERSE price the hold reached (drives a loser's red depth)
  profitLegs?: ChartProfitLeg[] // where profit was actually taken → one labelled dotted line each
  stopPrice?: number // initial 1R stop → a bubble + dotted risk line
  // The exit ladder in the STRATEGY's own order — never sorted by distance. A re-entry prices its
  // first rung off risk and its second off a fib, so the second is routinely the nearer of the two.
  tpTargets?: Array<number | ChartTpRung> // bare number tolerated (a run stored before 2026-08-21)
  fib?: ChartTradeFib // the fib leg this trade was priced off → the Trade fibs layer
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
  dir: TradeDir // the side that was refused — tag sits below for a long, above for a short
  price: number // where the entry limit would have rested
  reasons: ChartBlockReason[]
  /** Portfolio stack only — the strategy whose rule refused it. Absent on a single-run spec, which
   *  is what keeps every stack affordance invisible on an ordinary backtest.
   *
   *  ⚠ A block belongs to ONE strategy and is never merged with another leg's, unlike a gap or a
   *  liquidity level: two legs refusing on the same bar are two separate facts, and the whole
   *  question this layer answers is WHOSE rule spoke. */
  layer?: string
}

/** A setup that got PARTWAY and then died without ever becoming a trade — the companion of a
 *  block, and a different question. A block was a trade the strategy had fully ready and one of
 *  its rules refused. A miss never got that far: it met some of the strategy's confluences and
 *  the rest never arrived. Neither places an order, so neither is in any trade list.
 *
 *  `met` / `of` is the score the tag prints ("2/3"). `metLines` are pre-formatted strings the
 *  panel renders verbatim on hover — the panel has no idea what a confluence is, which is what
 *  keeps it strategy-agnostic; `reasons` is the missing piece, shaped exactly like a block's so
 *  both render and filter through the same code.
 *
 *  `near` is the STRATEGY's own judgement that this miss is worth looking at. The panel never
 *  interprets it — it reads `ChartSpec.missNoise`, which the emitter derives from it. */
export interface ChartMiss {
  id: string
  time: EpochMs
  dir: TradeDir // the side that was set up — tag sits below for a long, above for a short
  price: number // where the entry limit would have rested, had it got that far
  met: number
  of: number
  near: boolean
  metLines: string[]
  reasons: ChartBlockReason[]
  /** Portfolio stack only — the strategy whose setup this was. Same rule as `ChartBlock.layer`. */
  layer?: string
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
type OverlayRequires = {
  requires?: string[]
  /** Portfolio stack only — which strategies' setups caused this overlay to be drawn. Absent on a
   *  single-run spec, and on a stack's structure overlays, which are computed from the candles and
   *  belong to no leg.
   *
   *  ⚠ **A LIST, and the overlay draws while ANY of them is shown.** A gap, an order block and a
   *  liquidity level are facts about the MARKET, selected for drawing by whichever leg fired near
   *  them — so two legs reporting one gap is ONE drawing carrying both names, and hiding one leg
   *  must not remove a gap the other leg also fired into. That is the opposite rule from a block or
   *  a miss, which belongs to exactly one strategy. */
  layers?: string[]
}

/** A filled rectangle spanning a time and price range (e.g. a range box, an order block).
 *  `label` names the zone in its corner — `labelAlign: 'right'` parks it at the box's right edge,
 *  which is what a zone anchored on a candle needs (its LEFT edge is the candle itself, so a tag
 *  there sits on price). Both absent = an unlabelled box, which is what a fair value gap is. */
export interface BoxOverlay extends OverlayRequires {
  type: 'box'
  group: string
  t0: EpochMs
  t1: EpochMs
  top: number
  bottom: number
  label?: string
  labelAlign?: 'left' | 'right'
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

/** ONE candle repainted, to mark it out from the bars around it — today, the candlestick pattern
 *  that turned price at a setup (see the backend's `candle_overlays.py`).
 *
 *  It carries the bar's own OHLC rather than a price range, because it REDRAWS the candle: the
 *  overlay plane sits above the candle layer, so painting the same body and wick in another colour
 *  is what changes a candle's colour — klinecharts has no per-bar style. A box hugging high→low
 *  would be a different picture (a tinted zone), and would hide the bar it is meant to point at.
 *
 *  `label` names the best pattern on the bar and `patterns` names ALL of them — 7.4% of bars carry
 *  more than one, because a single candle can satisfy several definitions at once (every Hanging Man
 *  is also a Hammer by construction). ⚠ The tag used to print `+1` for the rest, which reads as a
 *  claim about the PATTERN rather than about the BAR — reported as *"how could a pattern have more
 *  than one name?"* — so the chart joins `patterns` instead.
 *
 *  `patternDir` is +1/-1/0 exactly as the source Pine DRAWS it: which way the pattern points. It
 *  feeds the direction filter and never decides whether the candle is drawn.
 *
 *  `spans` are the indices of the anchors whose span covers this bar; `deepestOf` are those it is
 *  the REVERSAL of. Both come from the backend because a span is a bar RANGE and the spec ships only
 *  the marks — nothing here could work either out. ⚠ `deepestOf` is a list rather than a flag: one
 *  bar can be the turn of one setup and an ordinary mark inside another's span. */
export interface CandleOverlay extends OverlayRequires {
  type: 'candle'
  group: string
  t: EpochMs
  open: number
  high: number
  low: number
  close: number
  label?: string
  patternDir?: number
  patterns?: string[]
  spans?: number[]
  deepestOf?: number[]
  /** `{anchor index: the pattern to NAME that anchor with}`, keyed by the index stringified.
   *
   *  One bar can be the deepest of two anchors that want OPPOSITE directions — a losing trade wants
   *  the candle that beat it, a 3/3 miss on the same leg wants the one it could have entered on — so
   *  the bar's single `label` is whichever anchor reached it first and is nobody's answer in
   *  particular. Read this for a trade's chip and fall back to `label`. */
  deepestNames?: Record<string, string>
  /** The named pattern's direction relative to the SETUP — never re-derive it from `patternDir`. */
  align?: 'with' | 'neutral' | 'against'
  style?: OverlayStyle
}

export type ChartOverlay = BoxOverlay | HLineOverlay | VLineOverlay | LabelOverlay | CandleOverlay

/**
 * An indicator series shipped FROM the run — not recomputed in the browser, so the
 * chart shows exactly what the strategy saw. `pane: "main"` overlays the price; `"sub"`
 * gets its own pane below.
 */
export interface ChartIndicator {
  name: string
  params?: Record<string, unknown>
  pane: 'main' | 'sub'
  /** Start switched ON? Absent ⇒ true, which is what every indicator predating this field expects
   *  (the ATR sub-pane has always opened on). An ANALYSIS layer should ship `false` — the chart
   *  opens on the run, and each extra reading is something the reader asks for, which is the rule
   *  Fair Value Gaps, Order Blocks and Fibs already follow. */
  defaultOn?: boolean
  series: Array<{ time: EpochMs; value: number }>
}

export interface ChartSpec {
  instrument: string // e.g. "AUDJPY.s"
  // The bars SHIPPED in `candles` — always the timeframe the run TRADED. A long run is capped by
  // trimming the WINDOW (newest slice), never by coarsening the bars.
  baseTimeframe: string
  // Same value; kept because an older CACHED spec may carry a coarsened `baseTimeframe` with the
  // run's real timeframe here, and the panel opens on this one.
  runTimeframe?: string
  // Epoch ms of the run's START. `candles` may begin later (the window cap), and the panel pages the
  // gap in as you scroll left, stopping here. Absent ⇒ no paging (nothing older is claimed to exist).
  historyStartMs?: number | null
  brokerGmtOffsetHours: number // for correct session placement
  candles: ChartCandle[] // base-TF OHLC
  sessions: ChartSession[]
  trades: ChartTrade[]
  // Refused setups. OPTIONAL — a runner that can't report them (NT8/MT5) omits the key, which is
  // what makes the Blocked layer vanish rather than render an empty, misleading toggle.
  blocks?: ChartBlock[]
  // Setups that died partway. Same optionality, same reason.
  misses?: ChartMiss[]
  // Reason labels the Missed layer starts with UNTICKED — the emitter's recommendation, derived
  // from each miss's own `near` flag. Just strings to the panel: it hides them on first render
  // and the reader ticks them back on. Absent/empty ⇒ every reason starts visible.
  missNoise?: string[]
  overlays: ChartOverlay[] // generic strategy structure, each tagged with a `group`
  indicators: ChartIndicator[]
}

/** One fetched window of bars, as `onRequestCandles` returns it — the DRILL-DOWN path only.
 *
 *  ⚠ It used to carry that window's ANALYSIS as well (`blocks`/`misses`/`missNoise` beside the
 *  overlays), because the spec shipped ~17 months of a long run and the panel PAGED the rest in
 *  over the network, so every layer had to be recomputed per window or it went silently empty past
 *  the shipped candles. The spec carries the whole run as of 2026-08-06 — analysis included — so
 *  paging older history is an in-memory slice and those three fields are gone. */
export interface ChartPage {
  candles: ChartCandle[]
  /** Market structure computed ON THESE BARS, at THIS timeframe.
   *
   *  🔴 **Restored 2026-08-08, and its absence was a live defect rather than a missing feature.**
   *  A drill-down replaces the candles and nothing replaced the overlays, so the panel drew the
   *  run's BASE-timeframe structure on top of finer bars — M15 swings over M5 candles, every label
   *  at a price that is not a swing on anything on screen. Reported against a 15m run drilled to
   *  M5: the chart said `SOS @4242.99` where the M5 answer, and TradingView's, is `4224.73`.
   *  Structure is a property of the BARS, so it has to be recomputed whenever they change. */
  overlays: ChartOverlay[]
  /** Whether the feed could be ASKED — NOT whether it had anything.
   *
   *  ⚠ It was `bool(candles)` on the backend until 2026-08-07, i.e. the same fact as
   *  `candles.length === 0`, so a caller could not tell a dead MT5 agent from a broker that simply
   *  has no 1-minute history that far back. The drill-down could only hedge, and printed *"no data
   *  here (feed offline, or none this far back?)"* — asking the reader the question the fetch had
   *  already answered. `available: true` with an empty `candles` is now a real answer. */
  available: boolean
  /** What went wrong when `available` is false. Null otherwise. */
  feedError: string | null
  dataStartMs: number | null
  hardEdge: boolean
}
