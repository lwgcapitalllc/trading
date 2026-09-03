/**
 * Custom klinecharts overlay templates — all generic and data-driven (no strategy logic).
 * Each template renders from the points + `extendData` it is given; the panel decides what to
 * create from the spec. `registerChartOverlays()` is idempotent and called once on mount.
 */
import {
  registerOverlay,
  type OverlayCreateFiguresCallbackParams,
  type OverlayFigure,
} from 'klinecharts'
import { adverseFloor, exitMarker, exitSide, stoppedOut, type Sign } from './tradeGeometry'

/** What `registerOverlay` accepts. Named because the trade template is held in a CONST before it
 *  is registered (twice, under two names) — and a template written inline is contextually typed
 *  by that call, while one assigned to a bare const is not: its callback params silently become
 *  `any`. The annotation is what keeps the extraction type-safe. */
type OverlayTemplateArg = Parameters<typeof registerOverlay>[0]

/** A rectangle hugging the candles inside a session window (Step 3). */
export const SESSION_BOX = 'lwgSessionBox'

/** Entry arrow + dashed line to exit + exit dot for one trade (Step 4). */
export const TRADE = 'lwgTrade'

/** The FALLBACK tag a PRIMARY trade wears when its strategy declares none of its own.
 *
 *  🔴 It was the only tag until 2026-09-02 — `A+` is `mpc_sos_fade`'s word for ITS setup, and this
 *  panel draws every strategy's trades, so three other bots' charts carried a fourth bot's label.
 *  The fix the old note here asked for is now built: a strategy declares `chart_tag`, the scanner
 *  carries it to the strategies table, and it reaches the panel as `spec.tradeTag`.
 *  ⚠ This constant survives as the fallback rather than being deleted, because a package that has
 *  not declared a tag yet must not lose its chip: untagged is NOT an option — Aaron's ask was to
 *  tell the books apart at a glance, and "no tag" is only readable as "primary" once you already
 *  know that is the rule.
 *  ⚠ So a chart still reading `A+` means EITHER the A+ bot OR a strategy that has not declared its
 *  own word. Declaring one is a change to that strategy's package, which rule 22 gates behind its
 *  parity harness — that is why they did not all land together. */
export const PRIMARY_TAG = 'A+'
/** A SCALE-IN LOT, drawn by the trade renderer itself — same box, same `Furthest`/`Deepest`/
 *  exit labels, same outcome colouring. A separate overlay NAME rather than a separate
 *  template, so the `Scale-in detail` toggle can clear it without touching the trades. */
export const TRADE_ADD = 'lwgTradeAdd'

/** Generic strategy-structure overlays (Step 5), driven entirely by spec.overlays. */
export const BOX = 'lwgBox'
export const HLINE = 'lwgHline'
export const VLINE = 'lwgVline'

/** Point-anchored text label (Step 7c) — market-structure break tags (BOS/SOS/iBOS) and
 *  swing-point labels (HH/HL/LH/LL/ASH/ASL + internal iSH…). */
export const LABEL = 'lwgLabel'

/** Market-structure overlay groups (emitted by backend `structure_overlays.py`) — the four
 *  TradingView toggles from `indicators/engines/structure_engine.pine`, same names, same order. Kept in one
 *  place so the panel can (a) default them OFF — unlike other overlay groups — and (b) order them
 *  together in the Layers menu. MUST match the GROUP_* names in the backend module.
 *  They NEST like the Pine's: the dependencies ride on each overlay's `requires` list, not here. */
export const STRUCTURE_GROUPS = [
  'External Structure',
  'Internal Structure',
  'Historic Internal Structure',
  'Swing Point Labels',
] as const

/** Layers-menu dot colour for a structure group that the current run emitted NOTHING into — so all
 *  four toggles can still be listed. Matches the backend's per-group colours (external = the strong
 *  bull/bear pair, internal = the muted pair). */
export const STRUCTURE_GROUP_COLOR: Record<(typeof STRUCTURE_GROUPS)[number], string> = {
  'External Structure': '#26a69a',
  'Internal Structure': '#80cbc4',
  'Historic Internal Structure': '#80cbc4',
  'Swing Point Labels': '#26a69a',
}

/** Overlay groups that belong in the **Analysis** dropdown rather than Structure, because they
 *  describe the CONTEXT a signal fired in rather than what the market drew as a whole. Both of
 *  today's entries are emitted by the backend only around trades / blocked setups / missed setups —
 *  so they answer "what was open when this fired", the Analysis question, not "what shape is the
 *  market in". Like the structure groups they default OFF and are listed with a count. MUST match
 *  the GROUP_* names in the backend `fvg_overlays.py` / `ob_overlays.py`.
 *
 *  ⚠ ORDER MATTERS BEYOND THE MENU: `DEBUG_ON_GROUPS` in `index.tsx` reads `ANALYSIS_GROUPS[0]`, so
 *  a new layer goes on the END unless it is genuinely meant to join Deep debug. */
/** The candle-repaint group, named on its own because the panel has to reason about it: a
 *  candlestick pattern is a property of ONE timeframe's bars, so this layer is only meaningful at
 *  the timeframe it was computed on. Every other analysis group is a price/time zone and survives a
 *  resample unchanged. MUST match `GROUP_CANDLES` in the backend `candle_overlays.py`. */
export const GROUP_CANDLE_MARKS = 'Candlestick Reversals'

export const ANALYSIS_GROUPS = [
  'Fair Value Gaps',
  'Order Blocks',
  'Liquidity — Daily/Weekly',
  'Liquidity — Sessions',
  'Liquidity — H4',
  GROUP_CANDLE_MARKS,
] as const

/** Analysis-menu dot colour per group — each matches what its layer actually draws, so a row's dot
 *  is a swatch of the boxes it switches on. FVG is the neutral grey of its borderless boxes; Order
 *  Blocks is mpc's `OB_ACCENT` orange outline. Both are distinct from Blocked pink / Missed amber,
 *  and from each other, so the rows tell apart at a glance. */
export const ANALYSIS_GROUP_COLOR: Record<(typeof ANALYSIS_GROUPS)[number], string> = {
  'Fair Value Gaps': '#94a3b8',
  'Order Blocks': '#E65100',
  // The three liquidity tiers. H4 is mpc's own `H4_ACTIVE_COLOR` reproduced exactly — it is the
  // colour those levels are read in on the TradingView chart. The other two are NOT mpc's, which
  // draws them in black: this chart renders on a dark background, so black is invisible and each
  // takes a hue picked away from everything already here (structure teal, gap slate, block orange).
  // ⚠ A SWEPT level is drawn grey and dashed whatever its tier, so these dots describe the LIVE
  // levels only — which is right, because the dot's job is to say which rows a layer is drawing,
  // and a spent pool has stopped being one of them.
  'Liquidity — Daily/Weekly': '#38bdf8',
  'Liquidity — Sessions': '#a78bfa',
  'Liquidity — H4': '#FF6B35',
  // The navy the candles are painted. ⚠ A true navy (#1e3a8a and darker) all but disappears against
  // this theme's near-black plot, so this is the most navy-reading blue that still stands out from
  // the green/red candles it sits between — which is the entire job of the layer.
  'Candlestick Reversals': '#2f5fe0',
}

/** ONE candle repainted in another colour — today, the candlestick pattern that turned price at a
 *  setup. It REDRAWS the bar rather than boxing it: klinecharts has no per-bar style, and the
 *  overlay plane sits above the candle layer, so painting the same body and wick over the top is
 *  what "change this candle's colour" means here. */
export const CANDLE_MARK = 'lwgCandleMark'

/** Daily session-break marker (Step 6) — a vline drawn under a separate name so the generic
 *  vline group and the day breaks can be removed/toggled independently. */
export const DAY_BREAK = 'lwgDayBreak'

/** Drill-down data edge — a red dashed "no earlier data" line at the broker's oldest available bar
 *  for the current sub-base TF (a TRUE feed limit, not our render cap). */
export const DATA_EDGE = 'lwgDataEdge'

/** Loading edge — a dashed line at the OLDEST loaded bar, with the empty strip behind it shaded and
 *  labelled, drawn while a scroll-left page of older history is in flight. */
export const LOADING_EDGE = 'lwgLoadingEdge'

/** A refused setup — the strategy had the trade ready and one of its OWN rules stopped it. */
export const BLOCK = 'lwgBlock'

/** A setup that got PARTWAY — met some of the strategy's confluences, then died unfilled. */
export const MISS = 'lwgMiss'

/** The marker the Step navigator is parked on — a vline under its own name so it survives every
 *  other layer's rebuild and can never be wiped by the generic vline group's `removeOverlay`.
 *  It exists because stepping CENTRES a marker rather than isolating it: with three trades on
 *  screen, "which one did it take me to" has no answer without something pointing at it. */
export const FOCUS = 'lwgFocus'

/** User-drawn Fibonacci retracement tool (2 anchor points → horizontal levels + price labels). */
export const FIB = 'lwgFib'

/** A TRADE's own fib leg — the ladder the strategy priced that entry, stop and targets off,
 *  recorded at order placement and shipped on the trade. Deliberately a separate template from
 *  `FIB` rather than a configured instance of it, for the same reason `MISS` and `BLOCK` are two
 *  names: this one is DATA, not a drawing. It must not be draggable, selectable, deletable, or
 *  affected by the fib editor — a reader who retunes their own ladder has not changed what the bot
 *  measured. It also needs no fib MATHS: every level arrives as an explicit (ratio, price) pair,
 *  so nothing in the browser can arrive at a different price from the strategy. */
export const TRADE_FIB = 'lwgTradeFib'

/** One rung of the fib ladder. `visible: false` keeps a level in the user's configured set while
 *  leaving it off the chart — the difference between "I don't use this one right now" and "delete
 *  it", exactly as the checkbox in TradingView's fib settings behaves. */
export interface FibLevel {
  ratio: number
  color: string
  visible?: boolean
}
interface FibExtend {
  levels?: FibLevel[]
  precision?: number
  chipBg?: string
}

// The FACTORY ladder — Aaron's Fibonacci retracement levels + colours (his TradingView setup).
// 0 & 1 share a neutral grey; the retracement zone runs green (shallow) → blue (the OTE band) →
// red (deep 0.886). This is the starting point and the "Reset" target, NOT the live set: the ladder
// is user-editable per drawing and as the tool default — see `fibLevels.ts` and `FibSettings.tsx`.
export const DEFAULT_FIB_LEVELS: FibLevel[] = [
  { ratio: 0, color: '#9598a1' }, // neutral (same as 1)
  { ratio: 0.382, color: '#22c55e' }, // green
  { ratio: 0.5, color: '#22c55e' }, // green
  { ratio: 0.618, color: '#2962ff' }, // blue
  { ratio: 0.702, color: '#2962ff' }, // blue
  { ratio: 0.786, color: '#2962ff' }, // blue
  { ratio: 0.886, color: '#ef5350' }, // red
  { ratio: 1, color: '#9598a1' }, // neutral (same as 0)
]

/** Ratio → factory colour, for a TRADE's fib. It reads the FACTORY set and never the user's
 *  configured ladder: the levels a trade was priced on are a fact about that trade, so retuning
 *  the drawing tool must not restyle them — but a 0.618 drawn by the bot should still look like a
 *  0.618 you drew yourself, which is what sharing the constant buys. */
const FACTORY_LEVEL_COLOR = new Map(DEFAULT_FIB_LEVELS.map((l) => [l.ratio, l.color]))
/** A ratio the factory set doesn't name (a strategy with its own ladder) — grey, not invisible. */
const UNNAMED_LEVEL_COLOR = '#9598a1'

/** One rung of a trade's recorded fib: the ratio and the price the STRATEGY read for it. */
export interface TradeFibLevel {
  ratio: number
  price: number
}
interface TradeFibExtend {
  levels?: TradeFibLevel[]
  chipBg?: string
}

/** Style + label passed to generic overlays via `extendData`. Mirrors spec OverlayStyle. */
interface OverlayExtend {
  color?: string
  fillColor?: string
  lineStyle?: 'solid' | 'dashed'
  lineWidth?: number
  label?: string
  labelAlign?: 'left' | 'right'
}

/** One structure text label — the batched LABEL overlay carries an array of these in `extendData.items`,
 *  parallel to its `points`, so all chips de-collide together in the callback. */
export interface LabelItem {
  text: string
  color: string
  placement?: 'above' | 'below' | 'center'
}

/** Everything the profit-depth TRADE overlay reads. All prices optional — the overlay
 *  degrades to the plain outcome box when the rich fields (mfe / legs) are absent. */
interface TradeExtend {
  dir?: 'long' | 'short'
  kind?: 'primary' | 'secondary' | 'recovery'
  after?: 'breakeven' | 'stopped' | 'closed'
  pnl?: number
  outcome?: 'won' | 'scratch' | 'lost' // graded by the backend; absent ⇒ fall back to `pnl > 0`
  adds?: { price: number; ms: number; qty: number }[] // scale-in lots bought after the entry
  addsDetailed?: boolean // the `Scale-in detail` layer is drawing each lot as its own box, so the
  // plain `Add` lines below are suppressed — two labels on one pixel row read as two fills
  addColor?: string // scale-in AMBER. An add used to draw in the entry's own colour on the grounds
  // that it IS an entry — true, and it made the one line on the box that is not the trade you
  // opened look exactly like the line that is (Aaron's call, 2026-08-20). Falls back to
  // `entryColor` so a host that never sets it keeps the old picture rather than losing the lines.
  color?: string // outcome colour (win green / loss red) — the fallback box
  scratchColor?: string // the SCRATCH verdict's colour, for the outcome chip. Passed in rather
  // than picked here so `index.tsx`'s `outcomeColor` stays the ONE place the chart grades a colour
  // — the box, the Step navigator pill and the Show filters all read it, and a literal here would
  // let the chip disagree with them about the same trade.
  dirColor?: string // entry-arrow colour (long green / short red) — fallback box only
  favColor?: string // favourable-side green (the profit fill / lines — a LIGHT mint, kept
  // distinct from the candle up-colour so the band never blends into green candles)
  advColor?: string // adverse-side red (loser fill + the stop)
  entryColor?: string // entry bubble + line + chip (neutral)
  chipBg?: string // side-label chip background (dark, for legibility over candles)
  neutralColor?: string
  layerColor?: string // portfolio-stack accent — tints the outcome chip border so overlapping
  // strategies read apart (absent on a single-run chart)
  layerName?: string // strategy name printed IN the outcome chip ("SOS Fade · Won") — the stack's
  // primary "who won this one" signal (absent on a single-run chart)
  precision?: number // instrument price decimals — every side label states its own price
  // `false` drops the number from every side label, leaving `Entry` / `SL` / `TP1` alone. A reader
  // preference (Chart settings), NOT a data change — the levels drawn are identical either way.
  // Undefined means ON, so a caller that has not been updated keeps the shipped behaviour.
  showPrices?: boolean
  // `false` drops every ANNOTATION: the side chips and the verdict word. What NAMES the trade
  // survives — see the outcome chip. Same rule as `showPrices`: a reader preference, and the
  // figures the labels sat beside are drawn identically either way, so nothing here changes what
  // the chart is saying about the trade, only how much of it is spelled out.
  showLabels?: boolean
  /** The candlestick reversal at this trade's turn, BY NAME (`Hammer`), or `no candle`. `undefined`
   *  = the layer is off, i.e. NOT ASKED — and it must not render as "no candle". Same rule as
   *  `mt5_link` everywhere else here: never let "no" and "cannot ask" be the same value.
   *  ⚠ A name, not a tick: `Won · ✓` reads as *confirmed win*, which is a different claim. */
  patternName?: string
  /** The word THIS strategy calls its own setup, off the spec (`tradeTag`). `undefined` = the
   *  package declared none, and the chip falls back to `PRIMARY_TAG` — see the note on that
   *  constant for why a fallback rather than no tag at all. Primary trades only: a re-entry and a
   *  recovery leg already wear tags naming what they ARE, which is the more useful fact there. */
  tag?: string
  entryPrice?: number
  exitPrice?: number
  mfePrice?: number
  maePrice?: number
  // Every FILL the trade came off at, not only the profitable ones — `banked` says which took
  // profit. ⚠ `banked` ABSENT reads as TRUE: a run stored before the flag carried only the
  // profitable rungs. A bare number is tolerated (older cached specs).
  profitLegs?: Array<number | { price: number; label: string; banked?: boolean }>
  stopPrice?: number
  // The exit ladder in the STRATEGY's own order — NOT nearest-first. `{price, banks}`; a bare
  // number is tolerated (a run stored before the banking flag existed). `banks === false` marks a
  // rung the trade places no order at, which is not a target — see the ladder block below.
  tpTargets?: Array<number | { price: number; banks?: boolean }>
  /** Room, in BARS, between this trade's entry and the nearest drawn trade on each side —
   *  `barsToPrev` back to the last bar any earlier trade was still open on, `barsToNext` forward to
   *  the next trade's entry. `undefined` = nothing drawn on that side, i.e. unlimited room.
   *
   *  They are BARS rather than pixels on purpose: how much room a chip actually has depends on the
   *  zoom, and the host cannot know it. Bars × the current bar width IS the room, and it is
   *  recomputed on every frame, so the same pair of trades can park their chips on opposite sides
   *  zoomed out and both on the default side zoomed in. That is the behaviour Aaron asked for
   *  (2026-08-23): the chips on a re-entry that starts where the trade before it ended were landing
   *  on that trade's box and on its own chips, and *"they'll need to be dynamic."*
   *
   *  ⚠ `barsToPrev` is measured to the FURTHEST-RIGHT bar of everything drawn before it, not to the
   *  trade immediately before it in entry order. On a stack a long hold entered early can still be
   *  open across the next two entries, and measuring to the nearest ENTRY would report clear air
   *  through the middle of a box that is plainly there. */
  barsToPrev?: number
  barsToNext?: number
}

/** What a WOULD-BE-ENTRY marker (BLOCK / MISS) reads. The `text` is decided by the host, not
 *  here, so one template serves both layers and the wording lives in one place. The reasons are
 *  never drawn — they live in the host's hover card. `row` parks the tag one step further from
 *  the pane edge, so two layers shown together don't stack their tags on each other. */
interface MarkerExtend {
  dir?: 'long' | 'short'
  text?: string
  color?: string
  textColor?: string
  row?: number
}

// Where a marker tag parks, in px from the pane edge. The top must clear the pinned OHLC readout
// (one ~20px line at the very top) with visible air under it; the bottom only has to clear the
// time axis. Raise these if either edge grows another row of chrome.
const MARKER_TAG_INSET_TOP = 56
const MARKER_TAG_INSET_BOTTOM = 44
// One tag's height + air, for the `row` offset that keeps two marker layers off each other.
const MARKER_TAG_ROW_H = 20

// The would-be-entry line, in px either side of the marker's bar. Deliberately SHORT — it marks a
// price on a bar, not a level that held for a while — and weighted forward, the way a resting order
// waits. Fixed pixels rather than a bar count so it stays legible at every zoom.
const MARKER_ENTRY_LINE_BACK = 8
const MARKER_ENTRY_LINE_FWD = 46

// How wide the blank strip must be before the "loading" label goes INSIDE it. Below this the label
// sits just inside the data instead, where there is always room for it.
const LOADING_LABEL_MIN_GAP = 190

/** '#rrggbb' / '#rgb' → 'rgba(r,g,b,a)'. Non-hex input is returned unchanged. */
export function withAlpha(color: string, a: number): string {
  if (!color.startsWith('#')) return color
  const h = color.slice(1)
  const full =
    h.length === 3
      ? h
          .split('')
          .map((c) => c + c)
          .join('')
      : h
  const r = parseInt(full.slice(0, 2), 16)
  const g = parseInt(full.slice(2, 4), 16)
  const b = parseInt(full.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}

/** Bare coloured text — no chip, no border, no background.
 *
 *  ⚠ klinecharts' DEFAULT overlay-text style is a solid BLUE chip (`#1677FF` background AND border),
 *  and OMITTING those fields falls back to it — so a `text` figure that wants plain text has to
 *  clear them explicitly. This lives at module scope because the trap is invisible until something
 *  is actually drawn: the generic BOX and HLINE label paths both shipped carrying it, dormant for
 *  months, until the order-block layer became the first emitter to put a `label` on a box and its
 *  "OB" tag came out as a blue pill. Every bare text figure here spreads this. */
const FLAT_TEXT = {
  size: 10,
  weight: 'bold',
  backgroundColor: 'transparent',
  borderColor: 'transparent',
  borderSize: 0,
  paddingLeft: 0,
  paddingRight: 0,
  paddingTop: 0,
  paddingBottom: 0,
} as const

let registered = false

export function registerChartOverlays(): void {
  if (registered) return
  registered = true

  registerOverlay({
    name: SESSION_BOX,
    totalStep: 2,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay }) => {
      if (coordinates.length < 2) return []
      const [a, b] = coordinates
      const x = Math.min(a.x, b.x)
      const y = Math.min(a.y, b.y)
      const width = Math.max(1, Math.abs(b.x - a.x))
      const height = Math.max(1, Math.abs(b.y - a.y))
      const data = (overlay.extendData ?? {}) as { color?: string; label?: string }
      const color = data.color ?? '#888888'

      const figures: OverlayFigure[] = [
        {
          type: 'rect',
          attrs: { x, y, width, height },
          styles: {
            style: 'stroke_fill',
            color: withAlpha(color, 0.1),
            borderColor: withAlpha(color, 0.45),
            borderSize: 1,
            borderStyle: 'solid',
          },
          ignoreEvent: true,
        },
      ]
      return figures
    },
  })

  // Profit-depth trade view. From the entry it fills BOTH sides of the trade. Favourable (green):
  // solid entry→where profit was actually banked (`profitLegs` / the exit), faint on to the deepest
  // point it ran (`mfePrice`) without banking. Adverse (red): the mirror — a winner shows one FAINT
  // band entry→`maePrice` (the drawdown it sat through and recovered), a loser a DARKER band
  // entry→stop (up to the stop line) with a faint tail if price ran past the stop. It draws a green
  // line at each real profit-take; entry / stop / deepest are guide lines. When the rich fields are
  // absent it degrades to the plain entry→exit outcome box, so it works for any runner/strategy.
  // Prices → pixels via the callback's `yAxis`; the two overlay points give the entry/exit x-span.
  // ⚠ Registered TWICE, under two names, from ONE template — the same trick `VLINE`/`DAY_BREAK`/
  // `FOCUS` use below. A scale-in lot is drawn by the identical renderer because a lot IS a
  // trade: it has an entry, an excursion, an exit and a P&L, and drawing it any other way would
  // be a SECOND implementation of the profit-depth view, free to drift from this one. The two
  // names exist only so the panel can add and remove the two layers independently.
  const tradeTemplate: OverlayTemplateArg = {
    name: TRADE,
    totalStep: 2,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay, yAxis, barSpace, bounding }) => {
      if (coordinates.length < 2) return []
      const [entry, exit] = coordinates
      const d = (overlay.extendData ?? {}) as TradeExtend
      const favColor = d.favColor ?? '#00ff7f'
      const advColor = d.advColor ?? '#ff3b5c'
      const outcome = d.color ?? favColor
      const arrowColor = d.dirColor ?? outcome
      const isLong = d.dir !== 'short'
      // The tag a trade wears. A trade's SHAPE cannot say which book it came from, and that is
      // the one fact worth stating on it; everything else about how it is drawn is identical,
      // deliberately. `null` for an unknown kind — a tag nobody can read is worse than none.
      //
      // 🔴 A RE-ENTRY IS TAGGED BY WHAT THE TRADE IT FOLLOWED DID, not by which trigger armed it.
      // The whole reason the re-entry layer exists is that a trade that SCRATCHED and a trade that
      // was STOPPED OUT are different situations wanting different re-entries, and Aaron's ask
      // (2026-08-21) was exactly this: "so I could tell the difference between a secondary that
      // was re-entering from a breakeven versus one re-entering from the primary at a stop loss."
      // One `SEC` on both cannot answer that, and on a run with both triggers on there are 107 of
      // them on the chart.
      //
      // ⚠ `after` ABSENT falls back to `SEC` rather than picking a side. A re-entry can be armed
      // through a precondition that asks nothing of the primary at all, and a chip guessing
      // `BE+` there would be a fact invented for a label. Same rule the whole repo runs on:
      // never let "no" and "cannot ask" be one value.
      const kindTag =
        d.kind === 'secondary'
          ? d.after === 'stopped'
            ? 'SL+'
            : d.after === 'breakeven'
              ? 'BE+'
              : 'SEC'
          : d.kind === 'recovery'
            ? 'REC'
            : d.kind === 'primary' || d.kind === undefined
              ? d.tag || PRIMARY_TAG
              : null
      const sign: Sign = isLong ? 1 : -1 // favourable ⇔ (price − entry) * sign > 0

      const x0 = Math.min(entry.x, exit.x)
      const x1 = Math.max(entry.x, exit.x)
      const w = Math.max(1, x1 - x0)
      const yOf = (p?: number): number | null =>
        yAxis && typeof p === 'number' ? yAxis.convertToPixel(p) : null

      // Small entry marker (orientation carries direction): long = up-triangle below the bar,
      // short = down-triangle above it.
      const HALF = 6,
        HEIGHT = 9,
        GAP = 4
      const arrowFig = (): OverlayFigure => ({
        type: 'polygon',
        attrs: {
          coordinates: [
            { x: entry.x, y: isLong ? entry.y + GAP : entry.y - GAP },
            { x: entry.x - HALF, y: isLong ? entry.y + GAP + HEIGHT : entry.y - GAP - HEIGHT },
            { x: entry.x + HALF, y: isLong ? entry.y + GAP + HEIGHT : entry.y - GAP - HEIGHT },
          ],
        },
        styles: { style: 'fill', color: arrowColor },
        ignoreEvent: true,
      })

      // Which BOOK a trade came from is the one fact about it that its shape cannot state — a
      // SECONDARY is the fast-feed sniper RE-ENTRY on a leg the primary already traded, a RECOVERY is the
      // counter-trade the loss-recovery rule took after a loss. Both have also been drawn with a
      // dashed box border, which is invisible in practice: a dashed border only reads as
      // "different" when a solid one is next to it, and neither kind is common enough for there
      // usually to be one on screen.
      //
      // Tagged at the ENTRY rather than folded into the Won/Lost chip, deliberately. The question a
      // reader has is "why is there a SECOND trade on this leg", which is a question about the
      // entry; how it resolved is a separate fact that already has its own chip (Aaron's call,
      // 2026-08-06: "win or lose doesn't matter").
      //
      // ⚠ It sits beyond the arrow tip on the DEGRADED path only. The first version put it there on
      // the rich path too and it was unreadable on real data (Aaron, 2026-08-06): directly under the
      // entry point is exactly where the `Entry` / `SL` / `Deepest` price chips already stack, so on
      // a tight trade — and a re-entry is tight by construction, that is the whole idea — the tag
      // landed on top of them. The rich path folds it into the outcome chip instead, which is
      // centred beyond the trade's extreme and is the one label with clear air around it.
      const secTagFig = (): OverlayFigure => ({
        type: 'text',
        attrs: {
          x: entry.x,
          y: isLong ? entry.y + GAP + HEIGHT + 9 : entry.y - GAP - HEIGHT - 9,
          text: kindTag ?? '',
          align: 'center',
          baseline: 'middle',
        },
        styles: {
          style: 'stroke_fill',
          color: arrowColor,
          size: 9,
          weight: 'bold',
          backgroundColor: withAlpha(d.chipBg ?? '#0d0d1a', 0.82),
          borderColor: withAlpha(arrowColor, 0.85),
          borderSize: 1,
          borderStyle: 'solid',
          borderRadius: 3,
          paddingLeft: 4,
          paddingRight: 4,
          paddingTop: 1,
          paddingBottom: 1,
        },
        ignoreEvent: true,
      })

      // Each leg is one FILL — {price, label, banked} from chart_spec; tolerate a bare number too
      // (older cached specs) by auto-labelling in exit order (TP1, TP2, …, last = Exit).
      // ⚠ `banked` ABSENT reads as TRUE. A run stored before the flag existed carried only the
      // profitable rungs, so defaulting to false would repaint every historical profit-take as a
      // plain exit — a claim about size that nobody measured.
      const legs = (d.profitLegs ?? [])
        .map((l, i, a): { price: number; label: string; banked: boolean } =>
          typeof l === 'number'
            ? {
                price: l,
                label: i === a.length - 1 && a.length > 1 ? 'Exit' : `TP${i + 1}`,
                banked: true,
              }
            : { ...l, banked: l?.banked !== false }
        )
        .filter((l) => l && typeof l.price === 'number')
      const legPrices = legs.map((l) => l.price)
      // Where the trade came off, and whether that price already has a line on it. Resolved HERE
      // because the `SL` chip is drawn before the legs are and has to know whether to name it.
      const exitAt = exitMarker({
        exitPrice: d.exitPrice,
        legPrices,
        stopPrice: d.stopPrice,
      })
      // banked = deepest price where real profit was taken; a trade with no fills on record banks
      // at its exit price, but only if it made money.
      // ⚠ Off the BANKED fills, not off every fill. Since every fill reaches the chart, taking the
      // extreme of all of them would let a breakeven-stop exit set the top of the green band and
      // read as a profit-take.
      const bankedPrices = legs.filter((l) => l.banked).map((l) => l.price)
      const bankedPrice: number | null = bankedPrices.length
        ? isLong
          ? Math.max(...bankedPrices)
          : Math.min(...bankedPrices)
        : legPrices.length
          ? null
          : typeof d.pnl === 'number' && d.pnl > 0 && typeof d.exitPrice === 'number'
            ? d.exitPrice
            : null
      const mfePrice: number | undefined =
        typeof d.mfePrice === 'number'
          ? d.mfePrice
          : bankedPrice != null
            ? bankedPrice
            : d.exitPrice
      const rich =
        yAxis != null &&
        typeof mfePrice === 'number' &&
        (legs.length > 0 || typeof d.mfePrice === 'number')

      if (!rich) {
        // Degrade: the plain entry→exit outcome box + entry arrow (a data-poor NT8/MT5 trade).
        const y = Math.min(entry.y, exit.y)
        const h = Math.max(1, Math.abs(exit.y - entry.y))
        return [
          {
            type: 'rect',
            attrs: { x: x0, y, width: w, height: h },
            styles: {
              style: 'stroke_fill',
              color: withAlpha(outcome, 0.16),
              borderColor: withAlpha(outcome, 0.9),
              borderSize: 1,
              borderStyle: kindTag ? 'dashed' : 'solid',
              borderDashedValue: [4, 4],
            },
            ignoreEvent: true,
          },
          arrowFig(),
          // Tagged on the data-poor path too. An NT8/MT5 trade carries no kind today, but a
          // marker that only appears on the rich path would read as "primary" rather than as
          // "this renderer had less to work with" — the absence would be a claim.
          ...(kindTag ? [secTagFig()] : []),
        ]
      }

      const profitColor = favColor // light mint — profit fill + level lines
      const entryColor = d.entryColor ?? '#c9cdd6'
      const stopColor = advColor
      const labelBg = withAlpha(d.chipBg ?? '#0d0d1a', 0.82) // subtle dark behind the side labels

      const figures: OverlayFigure[] = []
      const rect = (yA: number, yB: number, color: string) =>
        figures.push({
          type: 'rect',
          attrs: { x: x0, y: Math.min(yA, yB), width: w, height: Math.max(1, Math.abs(yB - yA)) },
          styles: { style: 'fill', color },
          ignoreEvent: true,
        })
      // A thin dotted line across the trade at a price level.
      const crossLine = (p: number | undefined, color: string, size = 1) => {
        const y = yOf(p)
        if (y == null) return
        figures.push({
          type: 'line',
          attrs: {
            coordinates: [
              { x: x0, y },
              { x: x1, y },
            ],
          },
          styles: { color, size, style: 'dashed', dashedValue: [2, 3] },
          ignoreEvent: true,
        })
      }
      // A small marker dot on a level, at the trade's left edge (the "bubble").
      const dot = (p: number | undefined, color: string) => {
        const y = yOf(p)
        if (y == null) return
        figures.push({
          type: 'circle',
          attrs: { x: x0, y, r: 3 },
          styles: { style: 'fill', color },
          ignoreEvent: true,
        })
      }
      // Side labels are collected first, de-collided, then drawn — so a cluster of close levels
      // (e.g. TP1 near the entry) never stacks on itself.
      //
      // EVERY label carries its PRICE (Aaron's call, 2026-08-03). A bare `SL` says a level exists
      // and makes you read it off the axis; the annotations are the trade's own record of what
      // happened, so each states the number it happened at.
      //
      // That call is now a SETTING rather than a rule (`showPrices`, Chart settings → Trades). The
      // reason is the re-entry: its box is short by construction, so the chips stack on top of
      // each other, and the price is most of each chip's width. Undefined keeps the price, so the
      // shipped reading is unchanged for anything that has not been updated to pass it.
      const px = (p: number) => p.toFixed(d.precision ?? 2)
      const withPrice = d.showPrices !== false
      // …and the whole annotation layer is itself a setting (Chart settings → Trades, 2026-08-20).
      // Aaron's ask, in his words: *"I will just be able to eye it off of the colour."* Every level
      // keeps its LINE and its DOT — only the words go — so the trade is read by shape and colour,
      // which is what a chart full of them is read by anyway once you know the layout.
      //
      // ⚠ It is collected at ONE choke point on purpose. A trade grew its annotations one call at a
      // time (`SL`, then the legs, then `Furthest`/`Deepest`, then the adds, then the TP ladder),
      // and a toggle wired at each call site would be a list that the NEXT annotation is free to be
      // left off — silently, because nothing fails when a label keeps drawing.
      const withLabels = d.showLabels !== false
      const labels: { y: number; text: string; color: string }[] = []
      const addLabel = (p: number | undefined, text: string, color: string) => {
        if (!withLabels) return
        const y = yOf(p)
        if (y == null) return
        labels.push({ y, text: withPrice ? `${text} ${px(p as number)}` : text, color })
      }

      const entryY = entry.y
      const yMfe = yOf(mfePrice)!
      const entryP = d.entryPrice
      // Favourable fill (light mint): SOLID entry→banked (took profit), FAINT banked→mfe (ran, unbanked).
      if (
        bankedPrice != null &&
        typeof entryP === 'number' &&
        (bankedPrice - entryP) * sign > 1e-9
      ) {
        const yBank = yOf(bankedPrice)!
        rect(entryY, yBank, withAlpha(profitColor, 0.22))
        if ((mfePrice - bankedPrice) * sign > 1e-9) rect(yBank, yMfe, withAlpha(profitColor, 0.07))
      } else if (typeof entryP === 'number' && (mfePrice - entryP) * sign > 1e-9) {
        // nothing banked (e.g. a loser that ran into profit, then stopped) → all faint green
        rect(entryY, yMfe, withAlpha(profitColor, 0.1))
      }
      // Adverse red — the mirror of the favourable green, on the loss side, so the drawdown the
      // trade sat through reads as clearly as the profit it ran. A LOSER actually gave it back:
      // a DARKER band entry→stop (up to the stop line), plus a faint tail if price ran past the
      // stop (gap/slippage) on to the true worst (`maePrice`). A WINNER only sat through the
      // drawdown and recovered it: one FAINT band entry→mae — the "runner" equivalent, showing
      // how deep it went against before working out.
      const isLoser = typeof d.pnl === 'number' && d.pnl < 0
      // 🔴 THE BAND ENDS WHERE PRICE ACTUALLY WENT. Its floor is the worst price the trade traded,
      // and it reaches the stop ONLY when the stop actually filled — the two rules and the reasons
      // they exist live in `tradeGeometry.ts::adverseFloor`, where they can be checked without a
      // browser. The alpha is the only thing decided here: DARK when the trade ended net negative
      // (it gave the drawdown back), FAINT when it recovered and closed up.
      //
      // ⚠ Both are read from the PRICES, never the exit reason. A stop-out's reason string is the
      // BRACKET that closed (`S-TP1` on a trade that lost 1.0R at its stop), so keying on it would
      // silently miss most of them.
      const wasStopped = stoppedOut(d.exitPrice, d.stopPrice, sign)
      const floor = adverseFloor({
        entryPrice: entryP as number,
        stopPrice: d.stopPrice,
        maePrice: d.maePrice,
        exitPrice: d.exitPrice,
        sign,
      })
      if (floor != null) rect(entryY, yOf(floor)!, withAlpha(advColor, isLoser ? 0.22 : 0.1))

      // How far the trade RAN — the two ends of the hold, one each way, and the pair of annotations
      // this layer was missing (Aaron's call, 2026-08-03). `Best` is the top edge of the faint green
      // band (unlabelled until now); `DD` is its adverse mirror and had no marker at all.
      //
      // 🔴 They read `Furthest` / `Deepest` until 2026-08-21. Both are the widest chips a trade
      // draws, both sit in the cluster the de-collider is already fighting, and neither word says
      // more than its short form does. `DD` is Aaron's own; `Best` was chosen over `Reached` /
      // `Peak` because it reads the same on a long and a short — the favourable extreme of a short
      // is the LOWEST price, so `Peak` invites the wrong half of the chart and `Reached` leaves
      // "reached what?" unanswered.
      //
      // Each is drawn only where it says something the labels beside it don't. `Best` needs a
      // REAL `mfePrice` (it falls back to the banked/exit price, which the Exit chip already
      // states) and it must have run PAST what was banked, which is exactly when the faint unbanked
      // band exists. `DD` needs to have gone adversely past the entry. Without those guards a
      // trade that never moved against itself prints `DD` on the entry's own pixel row.
      const runColor = withAlpha(profitColor, 0.7)
      if (typeof d.mfePrice === 'number' && (d.mfePrice - (bankedPrice ?? entryP!)) * sign > 1e-9) {
        crossLine(d.mfePrice, withAlpha(profitColor, 0.4))
        dot(d.mfePrice, runColor)
        addLabel(d.mfePrice, 'Best', runColor)
      } else {
        crossLine(mfePrice, withAlpha(profitColor, 0.4)) // guide only — Exit already names it
      }
      if (
        !wasStopped &&
        typeof d.maePrice === 'number' &&
        typeof entryP === 'number' &&
        (d.maePrice - entryP) * sign < -1e-9
      ) {
        const deepColor = withAlpha(stopColor, 0.75)
        crossLine(d.maePrice, withAlpha(stopColor, 0.4))
        dot(d.maePrice, deepColor)
        addLabel(d.maePrice, 'DD', deepColor)
      }
      // Stop: dotted line across + dot + "SL".
      crossLine(d.stopPrice, withAlpha(stopColor, 0.85))
      dot(d.stopPrice, stopColor)
      addLabel(d.stopPrice, exitAt === 'stop' ? 'SL / Exit' : 'SL', stopColor)
      // The trade's own exit LADDER — every rung it aimed at, drawn faint whether or not price
      // reached it. Read the block below the legs for why it is never gated.
      const targets = (d.tpTargets ?? [])
        .map((t) => (typeof t === 'number' ? { price: t } : t))
        .filter((t) => t && typeof t.price === 'number')
      // Which rung, if any, sits at a given price — so a level that is BOTH a target and where the
      // trade came off reads as ONE chip naming both (`TP2 / Exit`) instead of one of the two
      // silently winning the pixel row. Aaron, 2026-08-21: *"If TP2 and exit is the same dash
      // line, just update the label to say TP2 / Exit, so I could know."* Without it the reader
      // cannot tell "it exited AT its target" from "it exited somewhere the ladder never named",
      // which is the question the whole layer exists to answer.
      const rungAt = (price: number): string | null => {
        const i = targets.findIndex((t) => Math.abs(t.price - price) < 1e-9)
        return i < 0 ? null : `TP${i + 1}`
      }
      // Each real profit-take: a thin dotted mint line + a dot + its label (TP1/TP2/TP3/Exit). A
      // plain win with no per-rung detail draws one "Exit" at the banked price.
      //
      // 🔴 THE EXIT IS ALWAYS ONE OF THEM. Where a trade came off is a fact about the trade, not a
      // reward for making money — `tradeGeometry.ts::exitMarker` carries the rule and the trade it
      // was invisible on. It resolves to `stop` when the stop is where it ended (the `SL` chip
      // above becomes `SL / Exit` rather than a second red line on the same pixel row) and to
      // `leg` when a profit leg already draws that price.
      //
      // ⚠ Its colour is PRICE against the entry, never P&L. A breakeven-stop exit sits above a
      // long's entry and still nets a loss once costs come out; colouring by P&L would paint a
      // level price cleared as if price had not.
      const sideColor = (price: number) => {
        const side = exitSide(entryP as number, price, sign)
        return side === 'adverse' ? stopColor : side === 'flat' ? entryColor : profitColor
      }
      const drawnLegs: { price: number; label: string; color: string }[] = legs.map((l) => ({
        price: l.price,
        label: l.label,
        // A fill that BANKED is mint whichever way it sits; one that banked nothing is coloured by
        // where it landed against the entry, because that is the only thing it says.
        color: l.banked ? profitColor : sideColor(l.price),
      }))
      if (exitAt === 'draw') {
        drawnLegs.push({
          price: d.exitPrice as number,
          label: 'Exit',
          color: sideColor(d.exitPrice as number),
        })
      }
      // ⚠ Off `drawnLegs`, NOT `legs` — a plain win carries no rung detail and its only drawn
      // price is the exit, which is exactly the trade where `TP2 / Exit` has to work.
      const drawnPrices = drawnLegs.map((l) => l.price)
      for (const lg of drawnLegs) {
        crossLine(lg.price, lg.color)
        dot(lg.price, lg.color)
        const rung = rungAt(lg.price)
        addLabel(lg.price, rung && rung !== lg.label ? `${rung} / ${lg.label}` : lg.label, lg.color)
      }
      // SCALE-IN adds: one dotted line + dot + `Add` per lot, in the ENTRY colour, because that is
      // what they are — further entries, at a later price. Drawn whenever the trade carries them,
      // with no toggle: they are not an extra view of the trade, they are part of what it held, and
      // a box that hides them can show a short exiting BELOW its entry for a P&L of zero. Several
      // lots at one price collapse to a single labelled line (`Add ×3`) rather than stacking three
      // chips on the same pixel row.
      // …unless the `Scale-in detail` layer is on, in which case every lot is already drawn as a
      // full box with its own `Entry` label at exactly this price, and these would double it.
      const addRows = new Map<number, number>()
      for (const a of d.addsDetailed ? [] : (d.adds ?? [])) {
        if (typeof a?.price !== 'number') continue
        addRows.set(a.price, (addRows.get(a.price) ?? 0) + 1)
      }
      const addColor = d.addColor ?? entryColor
      for (const [price, count] of addRows) {
        crossLine(price, withAlpha(addColor, 0.55))
        dot(price, addColor)
        addLabel(price, count > 1 ? `Add ×${count}` : 'Add', addColor)
      }

      // Entry: NO line across — just a short tick where the green begins, a dot, and the label.
      figures.push({
        type: 'line',
        attrs: {
          coordinates: [
            { x: x0, y: entryY },
            { x: x0 + 16, y: entryY },
          ],
        },
        styles: { color: entryColor, size: 1.5, style: 'solid', dashedValue: [] },
        ignoreEvent: true,
      })
      dot(entryP, entryColor)
      addLabel(entryP, 'Entry', entryColor)

      // The TP LADDER — every target the trade aimed at, drawn as a FAINT line + dot + `TP1`/`TP2`/…
      // whether or not price ever reached it. Reading how far the runner still had to go is the whole
      // point of the layer, and it has to be answerable on EVERY trade.
      //
      // 🔴 It used to be gated: only the NEXT unhit target, and only when `mfePrice` had covered ≥ 33%
      // of the gap to it (`NEXT_TP_SHOW_FRAC`), the reasoning being that a far-away target clutters a
      // trade that barely moved. What that actually produced was two trades on ONE run, both shorts,
      // both "hit TP1 → armed breakeven → came back → scratched at BE", where one showed `TP2` and the
      // other showed nothing — and nothing on the chart said which of "the target was miles away" and
      // "this trade carries no targets" you were looking at. **A layer that draws itself only
      // sometimes cannot be read as absence-means-something**, so the reader has to go and check
      // anyway, which is the cost the gate was supposed to save. Aaron's call, 2026-08-20.
      //
      // ⚠ A target a real profit LEG already draws is skipped — that line is solid and says something
      // stronger (it BANKED there), and two figures on one pixel row read as two fills. The `1e-9` is
      // a float-equality guard, NOT a "near enough" band: a leg price and its target are the same
      // strategy field, so they either match exactly or the leg belongs somewhere else.
      //
      // 🔴 EVERY RUNG IS NAMED `TP1`/`TP2`, INCLUDING ONE THAT BANKS NOTHING — and the reverse was
      // tried for half a day on 2026-08-21. A rung whose size is 0 places no order and only steps
      // the stop, so it was drawn as `Stop tightens` in a neutral colour. Aaron, seeing it on every
      // A+ trade (both rungs of a primary bank 0% at the shipped ladder, so it was the ONLY thing
      // those charts said): *"Why is it that my A+ strategies now have annotation Stop Titans? I
      // don't even know what it is. It should just show a faint dashed line where TP1 was and where
      // TP2 was, so I could better understand why we exited at certain levels."*
      // **The number IS the information.** Whether size comes off there is a settings fact, true of
      // every trade in the run at once; where the rung SAT is a fact about this trade and is what a
      // reader is reconstructing. And it is already said without words: a rung is a FAINT dotted
      // line, a banked leg is SOLID. **A chip that has to be looked up is worth less than one that
      // is slightly incomplete** — the earlier reasoning optimised for a claim nobody was making.
      // ⚠ `banks` is still carried on the data and is still never defaulted (see `types.ts`); this
      // layer simply does not spend a chip on it.
      // ⚠ Numbering is by LADDER POSITION, which is the strategy's order and not nearest-first: a
      // re-entry prices its first rung off risk and its second off a fib, so `TP2` can legitimately
      // sit nearer the entry than `TP1` (23 of the 45 re-entries on run 687c8df2a523; every main
      // entry is correctly ordered). Sorting them here would renumber the strategy's own rungs.
      for (let i = 0; i < targets.length; i++) {
        const { price } = targets[i]
        if (drawnPrices.some((p) => Math.abs(p - price) < 1e-9)) continue
        crossLine(price, withAlpha(profitColor, 0.5))
        dot(price, withAlpha(profitColor, 0.5))
        addLabel(price, `TP${i + 1}`, withAlpha(profitColor, 0.7))
      }

      // De-collide the labels top→down (min 15px apart), then draw each as a compact rounded chip
      // beside the entry — by default just OUTSIDE the box to the left, flipping to the right of the
      // entry when the trade before this one is sitting in that space.
      labels.sort((a, b) => a.y - b.y)
      const MIN_GAP = 15
      for (let i = 1; i < labels.length; i++) {
        if (labels[i].y - labels[i - 1].y < MIN_GAP) labels[i].y = labels[i - 1].y + MIN_GAP
      }
      const LBL_GAP = 9
      // `border` overrides the chip's border colour (else it echoes the text colour) — the stack
      // view passes each strategy's layer colour so an overlapping trade's outcome chip reads apart.
      const chip = (
        x: number,
        y: number,
        text: string,
        color: string,
        align: 'left' | 'right' | 'center',
        border?: string
      ) =>
        figures.push({
          type: 'text',
          attrs: { x, y, text, align, baseline: 'middle' },
          styles: {
            style: 'stroke_fill',
            color,
            size: 10,
            weight: 'bold',
            backgroundColor: labelBg,
            borderColor: withAlpha(border ?? color, border ? 0.85 : 0.4),
            borderSize: 1,
            borderStyle: 'solid',
            borderRadius: 3,
            paddingLeft: 5,
            paddingRight: 5,
            paddingTop: 2,
            paddingBottom: 2,
          },
          ignoreEvent: true,
        })
      // WHICH SIDE OF THE ENTRY THE CHIPS PARK ON — decided per trade, per frame.
      //
      // 🔴 The default is the left, and on its own it is wrong for the case this chart is full of: a
      // re-entry opens on the bar the trade before it closed, so its chips are drawn straight onto
      // that trade's box and onto that trade's own chips. Aaron, 2026-08-23, looking at an A+ loss
      // with its stop-loss re-entry next to it: *"if two trades line up next to each other and the
      // annotations kind of overlap, move the next trade's annotations to your right as opposed to
      // the left."* The EARLIER trade keeps the left — it is the one with clear air behind it — and
      // the one arriving into the crowd is the one that moves.
      //
      // The room on each side is `bars × the current bar width`, so this is a decision about
      // PIXELS and is re-taken on every zoom: the same two trades that need opposite sides zoomed
      // out both keep the left once the bars are wide enough. ⚠ It is measured against the WIDEST
      // chip and applied to ALL of them, never per chip — a column that changes sides halfway down
      // reads as two different trades' annotations rather than one trade's.
      //
      // ⚠ When NEITHER side fits, it takes the roomier one rather than giving up and stacking on
      // the left. A cramped chip that is merely close to something is readable; one drawn on top of
      // another is not, and the left is where the collision has already been proven to be.
      const widest = labels.reduce((m, l) => Math.max(m, l.text.length * 6.3 + 12), 0)
      const need = widest + LBL_GAP
      const bar = barSpace?.bar ?? 0
      // `undefined` neighbour = nothing drawn that side = unlimited room. A NEGATIVE gap is a
      // neighbour still open across this entry, which is less than no room — it must not read as
      // plenty, so it is kept as the negative number it is.
      const roomLeft = d.barsToPrev == null ? Infinity : d.barsToPrev * bar
      const roomRight = d.barsToNext == null ? Infinity : d.barsToNext * bar
      // The pane edges still win. A chip off the left of the plot is unreadable whatever is beside
      // it, and the right edge is the same fact mirrored — which the old code only checked one way.
      const paneW = bounding?.width ?? 0
      const clipsLeft = x0 - need < 2
      const clipsRight = paneW > 0 && x0 + need > paneW - 2
      const onRight = clipsLeft
        ? !clipsRight
        : clipsRight
          ? false
          : roomLeft < need && roomRight > roomLeft
      for (const { y, text, color } of labels) {
        chip(onRight ? x0 + LBL_GAP : x0 - LBL_GAP, y, text, color, onRight ? 'left' : 'right')
      }

      // Outcome chip — a small "Won"/"Lost" tag, same subtle style as the level labels. Now that a
      // winner ALSO shows a red drawdown band, the result isn't obvious from colour alone, so it's
      // stated once per trade. It sits horizontally CENTRED over the trade, just BEYOND the trade's
      // resolved extreme — a WIN past the furthest favourable point (`mfePrice`), a LOSS past the
      // furthest adverse point (`maePrice`, behind the stop) — so it always points the way the trade
      // resolved: above a long win / below a long loss, mirrored for a short.
      if (typeof d.pnl === 'number' || d.outcome) {
        // THREE states, and the third is not a nicer word for a small loss. `pnl > 0` alone grades
        // a trade that netted exactly $0.00 as a LOSS — which is precisely what a scale-in add
        // handing back the profit its stop had locked produces (8 trades on run 295a6ff29d21, and
        // the reason this state exists). The verdict is the BACKEND's, graded against the run's own
        // median full loss, so the chip and the run's `scratch_count` KPI can never disagree; the
        // sign is only the fallback for a run that could not be graded at all.
        const verdict = d.outcome ?? ((d.pnl ?? 0) > 0 ? 'won' : 'lost')
        const won = verdict === 'won'
        // A scratch resolved by giving profit back, so it is parked on the ADVERSE side with the
        // losses — the chip always points the way the trade ended up.
        // ⚠ A loser's chip parks at its deepest adverse point — but NOT past the stop on a trade
        // the stop closed. This is the mark that made somebody ask: on a 1.0R stopped-out short it
        // sat a full 1.2R ABOVE its own `SL` line, which reads as a trade that kept losing after
        // it was closed. Same rule as the `DD` marker above, and the same reason.
        const deepY = wasStopped ? d.stopPrice : (d.maePrice ?? d.stopPrice)
        const extY = won ? yMfe : (yOf(deepY) ?? exit.y)
        const outPix = won ? -sign : sign // beyond the extreme, away from entry (px: up = −)
        // On a portfolio stack the chip also NAMES the strategy ("SOS Fade · Won") — with several
        // strategies' trades on one chart, the outcome alone doesn't say whose trade it was.
        // A re-entry says so here rather than at the entry — see `secTagFig`. It reads
        // "SEC · Won", so the fact that it IS a re-entry comes first and survives being skimmed.
        const outcome = won ? 'Won' : verdict === 'scratch' ? 'Scratch' : 'Lost'
        // …and the reversal candle at this trade's turn, BY NAME. ⚠ `undefined` prints NOTHING —
        // the layer is off, so the run has not been asked, and `no candle` there would state a
        // measurement nobody took.
        //
        // 🔴 **With annotations off this chip is cut to what NAMES the trade, and is dropped
        // entirely when there is no name.** The verdict word goes with the side chips — a win is
        // already the green and a loss the red, which is the reading Aaron asked for — but WHICH
        // trade this is cannot be read off the drawing at all: on a stack that is the strategy, and
        // on a single run it is the `SEC` / `REC` book tag that separates a re-entry or a recovery
        // from the setup it followed. The pattern name goes too: it is an annotation about what
        // happened at the turn, in the same family as `Furthest` and `Deepest`, and it has its own
        // control one section down in the same panel.
        const parts = withLabels
          ? [d.layerName, kindTag, outcome, d.patternName]
          : [d.layerName, kindTag]
        const text = parts.filter(Boolean).join(' · ')
        // Nothing left to say ⇒ no chip. An empty one still draws its dark rounded box, which on a
        // chart stripped of every other label is the only thing left to look at.
        if (!text) return figures
        const cx = (x0 + x1) / 2
        const cy = extY + outPix * 12
        // A scratch is neither green nor red — it gets its OWN colour (orange), so a flat trade
        // stops being counted by eye as a loss when the run's own KPI row does not, and stays
        // findable in a run full of wins and losses. ⚠ It used to fall back to `entryColor`, which
        // on a single-run spec is the same grey as the entry marker and every unlayered chip — a
        // third verdict drawn in the chart's default neutral does not read as a third verdict.
        // `scratchColor` is absent on an older cached spec, and that grey is still the right thing
        // to degrade to.
        const verdictColor =
          verdict === 'won'
            ? profitColor
            : verdict === 'scratch'
              ? (d.scratchColor ?? entryColor)
              : stopColor
        chip(cx, cy, text, verdictColor, 'center', d.layerColor)
        // A filled dot in the strategy's colour just left of the chip — the same swatch the equity
        // chart and the toggle chips use, so the eye matches trade → strategy without reading text.
        if (d.layerName && d.layerColor) {
          const halfW = (text.length * 6.3 + 12) / 2
          figures.push({
            type: 'circle',
            attrs: { x: cx - halfW - 5, y: cy, r: 3 },
            styles: { style: 'fill', color: d.layerColor },
            ignoreEvent: true,
          })
        }
      }

      return figures
    },
  }
  registerOverlay(tradeTemplate)
  registerOverlay({ ...tradeTemplate, name: TRADE_ADD })

  // ── Fibonacci retracement (USER-DRAWN) ────────────────────────────────────────
  // Two anchor points (swing A → swing B) define the price range, and the DIRECTION matters:
  // **1 sits on the first anchor (where the drag started), 0 on the second (where it ended)**.
  // Drag from a swing low up to a swing high and 1 is the low, 0 the high — the leg's ORIGIN is 1
  // and its EXTREME is 0, which is how a retracement is read (price retraces from 0 back toward 1)
  // and what every fib in this repo means: `mpc_strategy.pine` prices the same way
  // (`fiboP7 = ash - range*0.0` = the extreme, `fiboP10 = ash - range*1.0` = the origin), so a
  // hand-drawn fib and the bot's own levels line up. Each configured level draws a
  // thin horizontal line spanning EXACTLY the box the user dragged (both anchor x's — width AND
  // height follow the drag) plus a right-aligned "<ratio> (<price>)" chip in the level's colour.
  // Unlike the other overlays this one is NOT lock:true — it's interactive: drawn, selected/moved by
  // its anchor handles, and its lines respond to hover/click so a right-click can delete it. Only the
  // labels ignore events (they sit on the lines). Levels/precision/chip bg come via `extendData`.
  registerOverlay({
    name: FIB,
    totalStep: 3, // 2 points + 1
    needDefaultPointFigure: true, // anchor handles for select/move
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay, yAxis }) => {
      if (coordinates.length < 2 || !yAxis) return []
      const [a, b] = coordinates
      const p0 = overlay.points[0]?.value
      const p1 = overlay.points[1]?.value
      if (typeof p0 !== 'number' || typeof p1 !== 'number') return []
      const d = (overlay.extendData ?? {}) as FibExtend
      // Tested with `Array.isArray`, NOT `.length` — an EMPTY configured ladder means the user
      // switched every level off, and must draw nothing. Falling back to the factory set there
      // would answer "delete them all" with "here are the originals back".
      const levels = (Array.isArray(d.levels) ? d.levels : DEFAULT_FIB_LEVELS).filter(
        (l) => l.visible !== false
      )
      const precision = d.precision ?? 2
      const chipBg = withAlpha(d.chipBg ?? '#0d0d1a', 0.82)
      const xLeft = Math.min(a.x, b.x)
      const xRight = Math.max(a.x, b.x)
      const figures: OverlayFigure[] = []
      for (const lvl of levels) {
        // p0 = ratio 1 (the leg's origin, where the drag started), p1 = ratio 0 (its extreme).
        // Deliberately NOT `p0 + (p1 - p0) * ratio`, which anchors 0 on the first click and puts
        // the whole ladder on backwards. Ratios past 1 / below 0 still draw extensions for free —
        // this is a straight-line map either way, it just runs the other direction.
        const price = p1 + (p0 - p1) * lvl.ratio
        const y = yAxis.convertToPixel(price)
        figures.push({
          type: 'line',
          attrs: {
            coordinates: [
              { x: xLeft, y },
              { x: xRight, y },
            ],
          },
          styles: { color: lvl.color, size: 0.5, style: 'solid' },
        })
        // Label = decimal ratio + price in parens, e.g. "0.886 (3987.45)" — same dark rounded chip as
        // the trade level labels (SL/TP1…), so it reads over candles instead of a bare colour string.
        figures.push({
          type: 'text',
          attrs: {
            x: xRight,
            y,
            text: `${lvl.ratio} (${price.toFixed(precision)})`,
            align: 'right',
            baseline: 'middle',
          },
          styles: {
            style: 'stroke_fill',
            color: lvl.color,
            size: 10,
            weight: 'bold',
            backgroundColor: chipBg,
            borderColor: withAlpha(lvl.color, 0.4),
            borderSize: 1,
            borderStyle: 'solid',
            borderRadius: 3,
            paddingLeft: 5,
            paddingRight: 5,
            paddingTop: 2,
            paddingBottom: 2,
          },
          ignoreEvent: true,
        })
      }
      return figures
    },
  })

  // ── A trade's own fib leg (data, not a drawing — see TRADE_FIB) ────────────────
  // Two points give the x-span only: the bar the LEG started on → the trade's exit, so the ladder
  // reaches back through the retracement that produced the entry rather than starting at the fill.
  // Every y comes from a level's own recorded price, so there is no fib maths here at all.
  registerOverlay({
    name: TRADE_FIB,
    totalStep: 2,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay, yAxis }) => {
      if (coordinates.length < 2 || !yAxis) return []
      const d = (overlay.extendData ?? {}) as TradeFibExtend
      const levels = Array.isArray(d.levels) ? d.levels : []
      if (!levels.length) return []
      const chipBg = withAlpha(d.chipBg ?? '#0d0d1a', 0.82)
      const xLeft = Math.min(coordinates[0].x, coordinates[1].x)
      const xRight = Math.max(coordinates[0].x, coordinates[1].x)
      const figures: OverlayFigure[] = []

      for (const lvl of levels) {
        const color = FACTORY_LEVEL_COLOR.get(lvl.ratio) ?? UNNAMED_LEVEL_COLOR
        const y = yAxis.convertToPixel(lvl.price)
        figures.push({
          type: 'line',
          attrs: {
            coordinates: [
              { x: xLeft, y },
              { x: xRight, y },
            ],
          },
          styles: { color, size: 0.5, style: 'solid' },
          ignoreEvent: true,
        })
        // The RATIO alone, right-aligned at the leg's end — the side a hand-drawn fib labels, so
        // the bot's ladder reads the same way as one you placed (Aaron's call, 2026-08-03).
        // Deliberately NO price beside it, unlike the fib TOOL: the price is already on the axis
        // and on the trade's own annotations, and the ratio is the whole question here ("which
        // retracement did it enter at"), so the chip stays narrow enough for several ladders at once.
        figures.push({
          type: 'text',
          attrs: { x: xRight, y, text: `${lvl.ratio}`, align: 'right', baseline: 'middle' },
          styles: {
            style: 'stroke_fill',
            color,
            size: 9,
            weight: 'normal',
            backgroundColor: chipBg,
            borderColor: withAlpha(color, 0.4),
            borderSize: 1,
            borderStyle: 'solid',
            borderRadius: 3,
            paddingLeft: 4,
            paddingRight: 4,
            paddingTop: 1,
            paddingBottom: 1,
          },
          ignoreEvent: true,
        })
      }

      // This layer draws the LADDER and nothing else. It used to add its own `entry <ratio>` and
      // `deepest <ratio>` chips; both are gone (Aaron's call, 2026-08-03) — the trade beneath it
      // already annotates its own entry, and where it ran to now belongs with the rest of the
      // trade's annotations (`Deepest` / `Furthest` in the TRADE template) rather than being told
      // twice, at the same price, by two different layers.
      return figures
    },
  })

  // ── Generic strategy-structure overlays (box / hline / vline) ──────────────────
  registerOverlay({
    name: BOX,
    totalStep: 2,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay }) => {
      if (coordinates.length < 2) return []
      const [a, b] = coordinates
      const x = Math.min(a.x, b.x)
      const y = Math.min(a.y, b.y)
      const width = Math.max(1, Math.abs(b.x - a.x))
      const height = Math.max(1, Math.abs(b.y - a.y))
      const d = (overlay.extendData ?? {}) as OverlayExtend
      const color = d.color ?? '#888888'
      // `lineWidth: 0` means NO BORDER — a filled area and nothing else. Generic, not FVG-specific:
      // some sources draw a bordered region (a session/ORB range) and some draw a bare tint, and
      // Pine says so with `border_color = color(na)`. klinecharts needs the rect's `style` switched
      // for it; a 0 border SIZE alone still strokes a hairline.
      const bordered = (d.lineWidth ?? 1) > 0
      const figures: OverlayFigure[] = [
        {
          type: 'rect',
          attrs: { x, y, width, height },
          styles: {
            style: bordered ? 'stroke_fill' : 'fill',
            color: d.fillColor ?? withAlpha(color, 0.12),
            borderColor: withAlpha(color, 0.5),
            borderSize: d.lineWidth ?? 1,
            borderStyle: d.lineStyle === 'dashed' ? 'dashed' : 'solid',
            borderDashedValue: [4, 4],
          },
          ignoreEvent: true,
        },
      ]
      if (d.label) {
        // `labelAlign: 'right'` parks the tag at the box's RIGHT edge instead of its left. Generic,
        // not OB-specific: a box whose left edge is its ANCHOR candle has the candles sitting right
        // there, so a left-aligned tag lands on price, while the right edge of a fixed-width zone is
        // usually empty space (mpc_assistant.pine says exactly this — `text_halign = align_right`).
        const right = d.labelAlign === 'right'
        figures.push({
          type: 'text',
          attrs: {
            x: right ? x + width - 4 : x + 4,
            y: y + 3,
            text: d.label,
            align: right ? 'right' : 'left',
            baseline: 'top',
          },
          styles: { ...FLAT_TEXT, color },
          ignoreEvent: true,
        })
      }
      return figures
    },
  })

  // ── One candle, repainted ──────────────────────────────────────────────────────
  // Four points, all at the SAME timestamp, carrying high / low / open / close — so the callback
  // gets one x and four y's and can rebuild the bar. It draws what klinecharts draws: a wick line
  // high→low, and a body rect `barSpace.gapBar` wide (the same width the candle layer uses, read
  // from the chart rather than guessed, so the repaint lands exactly on the bar at every zoom).
  //
  // ⚠ It paints OVER the real candle rather than replacing it, which is the only way to do this —
  // so the body must be OPAQUE, or the original colour shows through and the mark reads as a tint.
  registerOverlay({
    name: CANDLE_MARK,
    totalStep: 2,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay, barSpace }) => {
      if (coordinates.length < 4) return []
      const [hi, lo, op, cl] = coordinates
      const d = (overlay.extendData ?? {}) as OverlayExtend
      const body = d.fillColor ?? '#2f5fe0'
      const edge = d.color ?? body
      const x = hi.x
      // `gapBar` is the candle BODY width (klinecharts' own `_gapBarSpace`); `bar` includes the gap
      // between candles, so using it would paint over the neighbours.
      const w = Math.max(1, barSpace.gapBar)
      const half = w / 2
      const top = Math.min(op.y, cl.y)
      // A doji's body is zero-height and would otherwise vanish — which is the one pattern most
      // worth seeing, so it gets a minimum of 1px exactly as the candle layer gives it.
      const h = Math.max(1, Math.abs(cl.y - op.y))
      const figures: OverlayFigure[] = [
        {
          // The WICK — drawn as a thin rect rather than a line so it takes the same pixel snapping
          // as the body and cannot land a half-pixel off it. 1px at any zoom, like the candle layer.
          type: 'rect',
          attrs: { x: x - 0.5, y: hi.y, width: 1, height: Math.max(1, lo.y - hi.y) },
          styles: { style: 'fill', color: edge },
          ignoreEvent: true,
        },
        {
          type: 'rect',
          attrs: { x: x - half, y: top, width: w, height: h },
          styles: { style: 'stroke_fill', color: body, borderColor: edge, borderSize: 1 },
          ignoreEvent: true,
        },
      ]
      if (d.label) {
        figures.push({
          type: 'text',
          attrs: {
            // Above the high, and centred on the bar — the candle IS the marker, so the tag only
            // has to name the pattern; parking it beside the bar would point at nothing.
            x,
            y: hi.y - 5,
            text: d.label,
            align: 'center',
            baseline: 'bottom',
          },
          styles: { ...FLAT_TEXT, color: edge },
          ignoreEvent: true,
        })
      }
      return figures
    },
  })

  registerOverlay({
    name: HLINE,
    totalStep: 2,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay }) => {
      if (coordinates.length < 2) return []
      const [a, b] = coordinates // both points share the price → same y
      const d = (overlay.extendData ?? {}) as OverlayExtend
      const color = d.color ?? '#888888'
      const figures: OverlayFigure[] = [
        {
          type: 'line',
          attrs: {
            coordinates: [
              { x: a.x, y: a.y },
              { x: b.x, y: a.y },
            ],
          },
          styles: {
            color,
            size: d.lineWidth ?? 1,
            style: d.lineStyle === 'dashed' ? 'dashed' : 'solid',
            dashedValue: [4, 4],
          },
          ignoreEvent: true,
        },
      ]
      if (d.label) {
        figures.push({
          type: 'text',
          attrs: {
            x: Math.max(a.x, b.x) - 4,
            y: a.y - 3,
            text: d.label,
            align: 'right',
            baseline: 'bottom',
          },
          styles: { ...FLAT_TEXT, color },
          ignoreEvent: true,
        })
      }
      return figures
    },
  })

  // VLINE and DAY_BREAK render identically (a full-height vertical line) but under distinct
  // names so they can be toggled / removed independently.
  const vline = {
    totalStep: 1,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({
      coordinates,
      bounding,
      overlay,
    }: OverlayCreateFiguresCallbackParams): OverlayFigure[] => {
      if (coordinates.length < 1) return []
      const a = coordinates[0]
      const d = (overlay.extendData ?? {}) as OverlayExtend
      const color = d.color ?? '#888888'
      return [
        {
          type: 'line',
          attrs: {
            coordinates: [
              { x: a.x, y: 0 },
              { x: a.x, y: bounding.height },
            ],
          },
          styles: {
            color,
            size: d.lineWidth ?? 1,
            style: d.lineStyle === 'dashed' ? 'dashed' : 'solid',
            dashedValue: [4, 4],
          },
          ignoreEvent: true,
        },
      ]
    },
  }
  registerOverlay({ name: VLINE, ...vline })
  registerOverlay({ name: DAY_BREAK, ...vline })
  registerOverlay({ name: FOCUS, ...vline })

  // ── Point-anchored text labels (market-structure tags), de-collided ───────────
  // ONE overlay holds EVERY visible structure label (its `points` are the anchors, `extendData.items`
  // the parallel text/colour/placement). klinecharts maps every point to a coordinate, so the callback
  // sees them all at once and can push overlapping chips apart in PIXEL space (like the trade overlay's
  // level labels) — the only way to de-collide across separate labels, since a per-label overlay can't
  // see its neighbours. `placement` sets the initial nudge + which way a chip slides to get clear (a
  // high tag slides up, a low tag down) so it never covers its own candle.
  registerOverlay({
    name: LABEL,
    totalStep: 1,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({
      coordinates,
      overlay,
      bounding,
    }: OverlayCreateFiguresCallbackParams): OverlayFigure[] => {
      const items = ((overlay.extendData ?? {}) as { items?: LabelItem[] }).items ?? []
      if (!items.length) return []
      const CHAR_W = 6.2,
        PAD = 10,
        H = 15,
        GAP = 2 // chip metrics (must track the text styles below)
      type Box = { x: number; y: number; half: number; text: string; color: string; up: boolean }
      const boxes: Box[] = []
      for (let i = 0; i < items.length && i < coordinates.length; i++) {
        const c = coordinates[i]
        const it = items[i]
        if (!c || !it?.text) continue
        const w = it.text.length * CHAR_W + PAD
        if (c.x < -w || c.x > bounding.width + w) continue // off-screen — skip (don't pile at the edge)
        const up = it.placement !== 'below'
        // Initial nudge OFF the anchor (wick tip / break line), ~ chip half-height + margin so the
        // chip clears the candle instead of resting on it — the pixel echo of Pine's newline offset.
        const y0 = c.y + (it.placement === 'above' ? -13 : it.placement === 'below' ? 13 : 0)
        boxes.push({ x: c.x, y: y0, half: w / 2, text: it.text, color: it.color ?? '#888888', up })
      }
      // Greedy left→right packing: each chip slides away from its anchor until it clears every
      // already-placed chip it overlaps in x. Only visible chips are processed, so this stays cheap.
      boxes.sort((a, b) => a.x - b.x || a.y - b.y)
      const placed: Box[] = []
      for (const b of boxes) {
        for (let guard = 0; guard < 80; guard++) {
          let hit = false
          for (const p of placed) {
            if (Math.abs(p.x - b.x) < p.half + b.half && Math.abs(p.y - b.y) < H) {
              const push = H - Math.abs(p.y - b.y) + GAP
              b.y += b.up ? -push : push
              hit = true
              break
            }
          }
          if (!hit) break
        }
        placed.push(b)
      }
      // Flat text — no chip/box/border/background (Aaron's call; also matches the Pine, which uses
      // color(na) for the label background). See `FLAT_TEXT` for the klinecharts default this is
      // clearing, and why it is shared rather than repeated here.
      return placed.map((b): OverlayFigure => ({
        type: 'text',
        attrs: { x: b.x, y: b.y, text: b.text, align: 'center', baseline: 'middle' },
        styles: { ...FLAT_TEXT, color: b.color },
        ignoreEvent: true,
      }))
    },
  })

  // ── Would-be-entry markers — the trades that never happened ──────────────────
  // TWO layers share ONE template: BLOCK (the strategy had the trade ready and its own rule
  // refused it) and MISS (the setup got partway and died). They answer different questions but
  // draw the identical thing — "here, on this candle, at this price, a trade almost was" — so
  // forking the template would guarantee the two drift apart in look and in bugs.
  //
  // The ANCHOR is the exact price the entry limit would have rested at: a dot sits on it and a
  // dotted line runs from it to the tag. That line is the whole point of the marker.
  //
  // The tag is parked at the PANE EDGE (bottom for a long, top for a short — the way the trade
  // would have moved), never near the price, so it can't sit on the candles. That is also why the
  // line has to be long: it spans from the tag all the way back to the level.
  //
  // The tag TEXT comes from the host (`extendData.text`) and is uniform within a layer —
  // "Blocked" / "2 of 3". It is deliberately never the reason: every tag looking the same is what
  // makes a layer scannable, and the detail is one hover away.
  //
  // Deliberately NOT `ignoreEvent` (unlike every other overlay here): the whole point is the hover,
  // and klinecharts only fires onMouseEnter/onMouseLeave on figures that accept events. The dot and
  // the line accept events too, so the line itself is hoverable, not just the chip.
  const marker = {
    totalStep: 1,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({
      coordinates,
      bounding,
      overlay,
    }: OverlayCreateFiguresCallbackParams): OverlayFigure[] => {
      if (coordinates.length < 1) return []
      const a = coordinates[0]
      const d = (overlay.extendData ?? {}) as MarkerExtend
      const color = d.color ?? '#ff2e9a'
      const down = d.dir !== 'short' // a LONG parks its tag at the bottom
      // Inset from the pane edge to the chip. Asymmetric because the two edges are not equally
      // busy: the TOP carries the pinned OHLC readout (and the Sessions legend under it), so a tag
      // parked tight against it lands ON that text; the BOTTOM only has to clear the time axis.
      // `row` steps a second layer's tags clear of the first when both are shown together.
      const inset =
        (down ? MARKER_TAG_INSET_BOTTOM : MARKER_TAG_INSET_TOP) + (d.row ?? 0) * MARKER_TAG_ROW_H
      const yTag = down ? bounding.height - inset : inset
      // Never let the tag cross the level it points at (possible when the price sits right at the
      // pane edge) — the line would double back and read as pointing the wrong way.
      const y = down ? Math.max(yTag, a.y + 14) : Math.min(yTag, a.y - 14)
      return [
        // THE RESTING LIMIT — a short horizontal dashed line AT the would-be entry price, drawn the
        // way a working order is drawn everywhere else, so the marker reads as "the limit sat here
        // and price never got a chance at it" rather than just "something happened on this bar".
        // Mostly forward in time from the bar, because that is the direction a resting order waits.
        {
          type: 'line',
          attrs: {
            coordinates: [
              { x: a.x - MARKER_ENTRY_LINE_BACK, y: a.y },
              { x: a.x + MARKER_ENTRY_LINE_FWD, y: a.y },
            ],
          },
          styles: { color, size: 1, style: 'dashed', dashedValue: [4, 3] },
        },
        // the dot pins the exact BAR on that level (the line alone spans several)
        {
          type: 'circle',
          attrs: { x: a.x, y: a.y, r: 2.5 },
          styles: { style: 'fill', color },
        },
        // …and the leader that ties the level to its tag
        {
          type: 'line',
          attrs: {
            coordinates: [
              { x: a.x, y: a.y },
              { x: a.x, y },
            ],
          },
          styles: { color, size: 1, style: 'dashed', dashedValue: [3, 3] },
        },
        {
          type: 'text',
          attrs: {
            x: a.x,
            y,
            text: d.text ?? '',
            align: 'center',
            baseline: down ? 'top' : 'bottom',
          },
          styles: {
            color: d.textColor ?? '#101014',
            size: 10,
            weight: 'bold',
            backgroundColor: color,
            borderColor: color,
            borderSize: 1,
            borderRadius: 3,
            paddingLeft: 5,
            paddingRight: 5,
            paddingTop: 2,
            paddingBottom: 2,
          },
        },
      ]
    },
  }
  registerOverlay({ name: BLOCK, ...marker })
  registerOverlay({ name: MISS, ...marker })

  // Drill-down data edge — a red dashed FULL-HEIGHT line at the broker's oldest available bar for the
  // current sub-base TF, with a dark label chip to its RIGHT (where data still exists). Marks a TRUE
  // feed limit so a hard "no more data" boundary reads as a wall, not a blank chart.
  registerOverlay({
    name: DATA_EDGE,
    totalStep: 1,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({
      coordinates,
      bounding,
      overlay,
    }: OverlayCreateFiguresCallbackParams): OverlayFigure[] => {
      if (coordinates.length < 1) return []
      const a = coordinates[0]
      const d = (overlay.extendData ?? {}) as OverlayExtend
      const color = d.color ?? '#ef5350'
      const figures: OverlayFigure[] = [
        {
          type: 'line',
          attrs: {
            coordinates: [
              { x: a.x, y: 0 },
              { x: a.x, y: bounding.height },
            ],
          },
          styles: { color, size: 1, style: 'dashed', dashedValue: [5, 4] },
          ignoreEvent: true,
        },
      ]
      if (d.label) {
        figures.push({
          type: 'text',
          attrs: { x: a.x + 6, y: 8, text: d.label, align: 'left', baseline: 'top' },
          styles: {
            style: 'stroke_fill',
            color,
            size: 10,
            weight: 'bold',
            backgroundColor: withAlpha('#0d0d1a', 0.82),
            borderColor: withAlpha(color, 0.5),
            borderSize: 1,
            borderStyle: 'solid',
            borderRadius: 3,
            paddingLeft: 5,
            paddingRight: 5,
            paddingTop: 2,
            paddingBottom: 2,
          },
          ignoreEvent: true,
        })
      }
      return figures
    },
  })

  // Loading edge — DATA_EDGE's companion and its opposite: that one marks a WALL (nothing older
  // exists), this one marks a WAIT (older bars are on their way). Scrolling past the loaded bars
  // otherwise gives a blank strip that reads exactly like the end of the run's data, which is the
  // bug this fixes. The strip is SHADED, not just lined, because a bare line leaves the reader
  // guessing which side of it is loading.
  registerOverlay({
    name: LOADING_EDGE,
    totalStep: 1,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({
      coordinates,
      bounding,
      overlay,
    }: OverlayCreateFiguresCallbackParams): OverlayFigure[] => {
      if (coordinates.length < 1) return []
      const a = coordinates[0]
      const d = (overlay.extendData ?? {}) as OverlayExtend
      const color = d.color ?? '#2962ff'
      const figures: OverlayFigure[] = []
      if (a.x > 1) {
        figures.push({
          type: 'rect',
          attrs: { x: 0, y: 0, width: a.x, height: bounding.height },
          styles: { style: 'fill', color: withAlpha(color, 0.07) },
          ignoreEvent: true,
        })
      }
      figures.push({
        type: 'line',
        attrs: {
          coordinates: [
            { x: a.x, y: 0 },
            { x: a.x, y: bounding.height },
          ],
        },
        styles: { color, size: 1, style: 'dashed', dashedValue: [5, 4] },
        ignoreEvent: true,
      })
      if (d.label) {
        // Centred in the strip once there is room; until then parked just inside the data, on the
        // same side DATA_EDGE labels — never half off the pane.
        const inGap = a.x >= LOADING_LABEL_MIN_GAP
        figures.push({
          type: 'text',
          attrs: {
            x: inGap ? Math.round(a.x / 2) : a.x + 6,
            y: Math.round(bounding.height / 2),
            text: d.label,
            align: inGap ? 'center' : 'left',
            baseline: 'middle',
          },
          styles: {
            style: 'stroke_fill',
            color,
            size: 11,
            weight: 'bold',
            backgroundColor: withAlpha('#0d0d1a', 0.82),
            borderColor: withAlpha(color, 0.5),
            borderSize: 1,
            borderStyle: 'solid',
            borderRadius: 3,
            paddingLeft: 7,
            paddingRight: 7,
            paddingTop: 4,
            paddingBottom: 4,
          },
          ignoreEvent: true,
        })
      }
      return figures
    },
  })
}
