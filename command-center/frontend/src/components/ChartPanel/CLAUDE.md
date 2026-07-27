# CLAUDE.md — ChartPanel (backtest candlestick panel)

**Purpose:** A strategy-agnostic candlestick chart for the backtest page, built on klinecharts v9. It renders whatever a `ChartSpec` declares and contains **zero** strategy-specific logic.
**Scope:** This folder only. The host page is `pages/BacktestDetail.tsx`.
**Status:** Live — all build steps done. Renders real runs end-to-end: candles, sessions, trades, strategy-structure overlays, the ATR indicator, and the measurement tool.
**Last reviewed:** 2026-07-27 (the Analysis dropdown: Trades + Winners/Losers and Blocked + its
per-reason filters, all moved out of Layers)

---

## The one rule

No strategy or instrument names, and no strategy concepts (sessions, ranges, breakout levels), are hardcoded in this component. The panel draws **only** what the spec carries. Adding a new strategy later means the lab emits a different spec — the code in this folder does not change.

---

## Files

```
ChartPanel/
├── index.tsx          default export ChartPanel({ spec? }) — inits klinecharts, draws candles + overlays
├── types.ts           ChartSpec — the contract the lab emits per run (THE source of truth)
├── chartStyles.ts     klinecharts style object, derived from the app theme (no hardcoded hex)
├── overlays.ts        custom klinecharts overlay templates (registerChartOverlays, idempotent)
├── indicators.ts      shipped-series indicator: ensureSeriesIndicator + mapSeriesToCandles (pure)
├── sessions.ts        session placement math: tz + broker offset → broker-axis windows (DST-aware)
├── fixtures/audjpy.ts  AUDJPY_FIXTURE — hand-written stand-in spec until Step 7 wires real specs
└── CLAUDE.md          this file
```

---

## The contract (`types.ts`)

`ChartSpec` carries: `instrument`, `baseTimeframe`, `brokerGmtOffsetHours`, `candles`,
`sessions[]`, `trades[]`, `blocks[]` (OPTIONAL — refused setups), `overlays[]`
(`box`/`hline`/`vline`/`label`, each tagged with a `group`),
`indicators[]`. **All times are epoch milliseconds** (klinecharts' native unit) — convert at
the emitter, never in the browser. Indicator series are shipped from the run, **not recomputed
here**, so the chart shows exactly what the strategy saw.

---

## Conventions

- **Lazy-mounted.** `BacktestDetail.tsx` imports the panel via `React.lazy` inside a collapsed
  "Price chart" section. klinecharts (~205 kB) and the fixture only load when the section opens
  — verified as a separate build chunk. Keep it this way; never import this folder eagerly from
  a page.
- **Theme.** Colors come from the app theme via `chartStyles.ts` (it reads `@/themes/electric-indigo`,
  the same source `@/themes/chart` uses for Recharts). No raw hex in components. Grid is off.
- **klinecharts data shape.** Spec candles use `time`; klinecharts wants `timestamp`. The
  `candlesToKLine` mapper in `index.tsx` is the single conversion point.
- **Timeframe — up = display, down = drill-down.** The segmented control offers two kinds of TF.
  **At or above the base** (`DISPLAY_TFS`, filtered to TFs ≥ and divisible by the spec's base TF):
  `resample` aggregates base bars up (epoch-aligned buckets) — display only, `spec.baseTimeframe`
  stays the source of truth. **Below the base** (`FETCH_TFS` = 1m/5m): these can't be resampled up,
  so they are **drill-down** — offered ONLY when the host passes an `onRequestCandles(tf, fromMs,
  toMs)` fetcher (BacktestDetail wires it to `GET /backtests/runs/{id}/candles`, gated to intraday
  runs — a D1/NT8 run has no sub-base bars). Selecting one enters `isFetchMode`: the panel pulls the
  TF's **full broker depth in ONE shot** (`FETCH_TF_LOOKBACK_DAYS` — 45d for M1, 270d for M5,
  deliberately MORE than the broker keeps so the fetch reaches the true feed edge), ending at the
  run's last bar; `displayCandles` becomes those `fetched` candles. No pan-driven refetch — the whole
  depth is loaded, so scrolling within it is free. Results are cached per-TF in-session
  (`fetchCacheRef`; a completed run's window is fixed, so it never restales) on top of the backend's
  own disk cache — re-selecting a TF is instant, and a cold reload hits the broker once.
  - **The red "no earlier data" edge.** The backend returns `data_start_ms` + `hard_edge`: `hard_edge`
    is True only when the oldest bar is the broker's TRUE limit (feed has nothing older, not our render
    cap — `_DRILL_CANDLE_CAP` 60k sits above M1/M5 depth so it never binds and can't fake a boundary).
    When set, the panel draws the `DATA_EDGE` overlay — a **red dashed full-height line** with a label
    ("No earlier 1-minute data" / "No earlier 5-minute data") at that bar. So a hard feed limit reads
    as a wall you scroll into, never a blank chart. `available: false` (empty candles) now means the
    feed is genuinely unreachable (agent offline) — shown as "no M1 available (data feed offline?)".
  - **Overlays are clipped to the loaded candles.** klinecharts clamps an overlay point whose
    timestamp is outside the data to the plot edge, so without this every trade/session/day-break
    older than a drill-down TF's data edge would pile its markers up in the empty no-data region. All
    auto-generated overlays (trades — by ENTRY time; sessions; day breaks; generic box/hline/vline
    structure) are filtered to `[loadedLoTs, loadedHiTs]` (the loaded candles' time bounds) before
    creation, so NOTHING draws left of the red edge line. User-drawn fibs are exempt (the user placed
    them). In display mode the candles cover the whole run, so the filter is a no-op there.
  - Switching TF re-applies data; it must NOT re-init the chart, so overlays (anchored by timestamp,
    incl. trade markers) survive the switch and land ON the 1m/5m candles — that's the sniper-entry
    view. The `DATA_EDGE` overlay is rebuilt after each data change like the other vline overlays.
- **Overlays are registered once, created per-spec.** Custom templates live in `overlays.ts`
  (`registerChartOverlays()`, guarded so StrictMode/remounts don't double-register). The panel
  creates instances with `points` (anchored by `timestamp`) + `extendData` (colors/labels).
  `applyNewData` can clear overlays, so the overlay-build effect runs AFTER the data effect and
  re-creates everything on every TF switch / toggle. Geometry is derived from BASE candles so it
  is TF-invariant.
- **Sessions are data, placed DST-correctly.** `sessions.ts` converts a session's local time
  (its IANA `tz`) → true UTC (via `Intl`, reading the real offset per date) → broker axis
  (`+ brokerGmtOffsetHours`). Verified: London shifts BST↔GMT across the year; Tokyo is fixed.
  Boxes hug the high/low of the candles inside each window. **Managed from an on-chart "Sessions"
  legend** (TradingView indicator-legend style) pinned top-left over the plot — a pill showing the
  active count that opens a popover with a Show/Hide-all toggle + a per-session row each. NOT in the
  Layers dropdown. To keep that top-left corner clear for the legend, klinecharts' own candle + indicator
  tooltips are set `showRule: 'follow_cross'` in `chartStyles.ts` (the OHLC/indicator legend appears on
  crosshair hover instead of being permanently pinned).
- **Trades** (`TRADE` overlay): a **profit-depth view**, not a plain box. From the entry it fills
  **both sides**. The FAVOURABLE run is two shades of a LIGHT mint (`favColor`, deliberately lighter
  than the candle up-colour so the band never blends into the green candles inside it) — SOLID
  entry→where profit was actually banked (`profitLegs`, else the exit on a win), FAINT on to the
  deepest point it ran (`mfePrice`) without banking. The ADVERSE run mirrors it in red (`advColor`):
  a **winner** shows one FAINT band entry→`maePrice` (the drawdown it sat through and recovered),
  a **loser** a DARKER band entry→**stop** (up to the stop line) plus a faint tail if price ran
  past the stop (gap/slippage) on to `maePrice`. Each level (stop,
  each profit-take, the entry) is a **thin dotted line** with a **small dot** at the left edge and a
  compact **rounded label** (`SL`/`TP1`/`TP2`/`TP3`/`Exit`/`Entry`; the TP/Exit label comes from the
  leg's exit id via `chart_spec._leg_label`, one style for every rung — no per-TP colours). **The
  entry is the exception: no line across, just a short tick where the green begins** (the fill edge is
  the entry). Labels are collected, **de-collided top→down** (so a TP that sits right by the entry
  never stacks on it), then drawn just OUTSIDE the box to the left, flipping inside only if they would
  clip the pane edge. **Gotcha — a klinecharts `text` figure paints its OWN background:** `TextStyle`
  carries `backgroundColor`/`borderColor`/`borderRadius`/padding and the DEFAULT overlay text style is
  a solid BLUE chip, so a bare `text` figure renders as an ugly blue tag. The labels therefore style
  the text figure directly (subtle dark `backgroundColor`, rounded, thin border) — never a separate
  `rect` behind a bare `text`. The deepest-run (`mfePrice`) line is a faint unlabelled guide (it's just
  the top of the faint band). All prices arrive via `extendData`
  and are converted to pixels with the callback's **`yAxis.convertToPixel`** (the two overlay points
  give the entry/exit x-span) — so a variable number of legs needs no extra points. `overlays.ts`
  stays theme-free (fav/adv/entry/chip colours are passed in). **Degrades gracefully:** a trade
  lacking the rich fields (`mfePrice`/`profitLegs` — an NT8/MT5 run, or an old Python run whose stored
  `equity_curve.json` predates them) falls back to the original entry→exit outcome box (win green /
  loss red, dashed border + a direction triangle for a 1m secondary). The rich fields are emitted by
  `backtest/output.py` (`mfe_price`/`mae_price`/`stop_price`/`legs`, all reporting-only — parity-safe)
  → `chart_spec` (which filters `legs` to real profit-takes beyond a 0.1R scratch band, so a
  breakeven-stop fill is never drawn as profit, and attaches each surviving leg's label). One on/off
  toggle for all trades (`tradesOn`), driven from BOTH the **Analysis** dropdown AND the right-click
  chart menu — same state, either surface flips it. **Winners / Losers outcome filters** (`winnersOn` /
  `losersOn`, both default ON) sit under it as INDENTED sub-rows in Analysis, each with its
  count, so a run can be read as all-winners or all-losers without hunting trade by trade. They're
  listed only while `tradesOn` — with trades hidden they'd be inert switches — and the win test is
  `pnl > 0`, the SAME expression as the overlay's win/loss colour, so a trade's chip colour and the
  filter that shows it can never disagree. A single **outcome chip** (`Won` green / `Lost` red, from `pnl`'s sign) sits
  horizontally **centred** over the trade, just BEYOND its **resolved extreme** — a win past the
  furthest favourable point (`mfePrice`), a loss past the furthest adverse point (`maePrice`, behind
  the stop) — so it always points the way the trade resolved (above a long win / below a long loss,
  mirrored for a short). Added because, once a winner also shows a red drawdown band, the result is no
  longer obvious from colour alone. It's a derived verdict, NOT the raw exit reason — no exit-reason
  text (`stop`/`S-RUN`/…) is ever drawn.
- **Blocked setups** (`BLOCK` overlay, spec `blocks[]`) — **the trades that never happened.** A setup
  the strategy had READY and one of its OWN rules refused places no order, so it appears in no trade
  list, no equity curve and no broker report; without this layer there is no way to judge whether a
  blocking rule protects the account or costs it.
  - **The LINE is the marker.** The overlay's single anchor is the EXACT price the entry limit would
    have rested at: a dot sits on it and a dashed pink line runs from it to the tag. **The tag is
    parked at the PANE EDGE** — bottom for a refused long, top for a refused short (the way the trade
    would have moved) — never near the price, so it can never sit on the candles; that is also why the
    line has to be long. The tag is clamped so it can never cross the level it points at (possible
    when the price sits right at the pane edge), which would make the line double back.
  - **The tag text is UNIFORM: `Blocked`, plus a count when several rules refused the same setup**
    (`Blocked 2`). Every tag looking identical is what makes the layer scannable at a glance, and the
    reasons are one hover away. Do not put reason text back on the chip.
  - **Hover** gives the side, EVERY rule that was refusing it (label + full sentence, primary first)
    and the would-be entry price. The card is a React node in the SAME `pointer-events:none` plane as
    the measurement layer (a card that ate its own hover would flicker), placed from the event's
    **`pageX`/`pageY`** and rendered viewport-`fixed` + clamped like the right-click menu — the overlay
    event's `x`/`y` are PANE-relative, so wrapper padding or a second pane would silently offset it.
    The `BLOCK` template is the ONE here that is deliberately not `ignoreEvent` (klinecharts only fires
    hover on figures that accept events), and its dot and line accept events too, so the LINE is
    hoverable, not just the chip.
  - **`reasons` is a LIST** because several rules can refuse one setup. The panel derives its
    per-reason filter roster from those labels (first-seen order, with counts), exactly as it derives
    stack layers from trades — so it stays strategy-agnostic and a different rule set needs no chart
    change. A block draws while **ANY** of its reasons is still on: requiring ALL would make "show me
    the veto blocks" hide the ones the final hour was also refusing, and those are still veto blocks.
  - **Pink is off the win/loss axis on purpose:** a refused trade is not a loser, and red would read as
    one. Lives in the **Analysis** dropdown, **default OFF** — a diagnostic view, not part of reading
    the run, and a long run has more refusals than trades. Listed only when the run reports any, so an
    NT8/MT5 run (which cannot report them) shows no permanently-empty switch.
- **Portfolio-stack layering** (`layer` / `layerName` / `layerColor` on a trade — all absent on a
  single-run spec, which is what makes every stack affordance vanish for a normal backtest). With
  several strategies' trades on ONE chart, the outcome alone doesn't say WHOSE trade it was, so the
  outcome chip becomes **`<strategy> · Won`** with a filled dot in the strategy's colour just left of
  it and its border in that colour — the same swatch the stack's equity lines and toggle chips use, so
  the eye matches trade → strategy without reading text. The entry marker takes the layer colour too.
  A **Strategies dropdown** sits beside Analysis (deliberately NOT folded into it — Aaron's call: a
  stack's legs are a different kind of thing from a run's own trades) and hides one strategy's trades
  (`hiddenLayers`), for when overlapping trades need isolating. **The roster is DERIVED from the
  trades themselves**, so the panel stays strategy-agnostic — it sees layers as data, exactly like
  overlay groups, and needs no new props and no knowledge of stacks. A **near-miss next-TP** guide: if the trade banked its earlier
  rungs but never tagged the FOLLOWING target, that target (`tpTargets`, the full TP ladder — emitted
  by `execution.py` → `output.py` `tp_targets` → `chart_spec`, reporting-only/parity-safe) is drawn as
  a FAINT dashed line + faint label, but ONLY when the furthest favourable run (`mfePrice`) covered
  ≥ `NEXT_TP_SHOW_FRAC` (0.33) of the gap to it — so you can see how close a runner came to the next TP
  without a far-away target cluttering a trade that barely moved. Supported figure types are
  `circle/line/polygon/rect/text` (verified via `getSupportedFigures`). **Chart price marks:** the
  candle `priceMark.high`/`.low` (highest/lowest-visible-price tags) are turned OFF in `chartStyles.ts`
  — they render on the exact visual extreme, which is where the outcome chip sits, so they collided;
  the last-price line stays on.
- **Generic overlays** (`BOX` / `HLINE` / `VLINE`): render `spec.overlays`, grouped by `group`,
  each group independently toggleable. This is what carries strategy structure (range box,
  buy/sell levels, breakout marker in the fixture) — the chart never knows which strategy made
  them. Style (`color`/`fillColor`/`lineStyle`/`lineWidth`) + `label` come from the spec via
  `extendData`. `vline` spans the pane height (`bounding.height`); its point `value` is a dummy
  (only `x`/timestamp matters).
- **Point labels** (`LABEL`): flat coloured text tags for market structure (no box/border/background —
  Aaron's call, and it matches the Pine's `color(na)` label background). **All visible
  structure labels live in ONE `LABEL` overlay** — its `points` are the anchors and `extendData.items`
  the parallel `{text,color,placement}` array — because klinecharts maps every point to a coordinate,
  so the callback sees them together and **de-collides them in pixel space** (greedy left→right: a chip
  slides away from its anchor — up for a high tag, down for a low — until it clears every placed chip).
  A per-label overlay could never do this (it can't see its neighbours). Only on-screen chips are laid
  out, so it stays cheap. `placement` (`above`/`below`/`center`) sets the initial nudge + slide
  direction. The render effect collects the labels during the group loop and creates the single overlay
  after it.
- **Market-structure overlays (Step 7c).** The canonical `engines/market_structure/` engine is replayed
  over the run's candles **server-side** (`backend/services/structure_overlays.py`, imported by bare
  name — never a second engine) and emitted as generic `hline` + `label` overlays in **four groups that
  are the four TradingView toggles**, same names and order as `indicators/structure_engine.pine`:
  `External Structure` (BOS/SOS break lines + tags, and the active unbroken swing rays),
  `Internal Structure` (iBOS/iSOS for the current external leg), `Historic Internal Structure` (the
  same for older legs), `Swing Point Labels` (HH/HL/LH/LL/ASH/ASL + internal iSH/iSL/…).
  The group names are pinned in `STRUCTURE_GROUPS` (`overlays.ts`) so the panel can (a) default them
  **OFF** — a chart with all structure drawn is unreadable — while every other group defaults ON, and
  (b) order the four together at the end of the Layers menu. **All four are listed whenever a run
  carries any structure at all, even when a group is EMPTY** — they're the Pine's four checkboxes, and
  one that vanishes reads as a missing feature. `Internal Structure` is the one this bites: it holds
  only the CURRENT external leg, so it's legitimately empty on most finished runs (everything older is
  Historic). Empty groups get their dot colour from `STRUCTURE_GROUP_COLOR`.
  **The four toggles NEST exactly like the Pine's**, via each overlay's optional `requires` list (a
  generic `ChartOverlay` field: every named group must ALSO be on for the overlay to draw). Pine hides
  ASH/ASL/HH/HL with `showExternal` regardless of the swing-label toggle, runs the whole internal
  engine only under `showInternal`, and treats internal history as a SUB-filter of it — so an external
  swing tag `requires` External, an internal swing tag `requires` Internal (+ Historic when it belongs
  to an older leg), and a historic internal break `requires` Internal. Switching a structure off can
  therefore never leave its swing tags floating, and Historic is not a peer layer. Computed on the **displayed/base TF** (v1):
  the lines align 1:1 with the bars on screen, and drill-down (M1/M5) shows price only — no per-window
  structure recompute yet. Colour convention follows the source Pine: a swing-HIGH label is bearish-red
  (resting sell-side liquidity), a swing-LOW label bullish-teal; a break takes its direction's colour.
  **Break lines run wick-to-wick** — anchored at the swing that broke so they start on that candle's
  actual wick. External lines use `bull_bos_h_loc`/`bear_bos_l_loc` (the origin candle's high/low equals
  the line price — verified). Internal lines use the engine's `ifib_seed_ash/asl` + `_loc` (the internal
  leg anchors, which land exactly on the wick), NOT `int_break_origin_loc` — that's the order-block scan
  origin and floats off the wick (the bug that made internal lines miss their candles).
  **Label coordinates mirror the Pine** so the chart reads like TradingView: a **break tag**
  (BOS/SOS/iBOS/iSOS) anchors at the **horizontal midpoint of its break line** (`_mid` =
  Pine's `mid_x`), which lands in the gap the impulse leg left — clear of the candle cluster at the
  break bar (the fix for tags sitting on top of the bars); a **swing tag** anchors AT its swing bar,
  above a high / below a low. The frontend's `LABEL` nudge (~13px, ≈ chip half-height) is the pixel
  echo of Pine's newline offset, then pixel de-collision keeps dense clusters legible.
  Current-vs-historic split boundaries on the **second-to-last external break** (a leg starts at a
  BOS/SOS) — robust to the pivot-confirmation cluster that piles swings at the data's end; an empty
  "current" is honest (no internal has printed since the last break). Per-group overlay count is capped
  (`_MAX_PER_GROUP` 1200, newest kept) so a very long run can't spawn tens of thousands of overlays.
  **Existing runs need a chart refresh** to pick up structure (the `chart_spec.json` is cached).
- **Indicators are shipped, not recomputed.** `indicators.ts` registers one klinecharts indicator
  template per indicator NAME (so multiple on a pane don't collide). Its `calc` doesn't compute
  anything — `mapSeriesToCandles` looks the shipped value up by timestamp (last shipped point in
  each displayed bar's window = value as of bar close), so higher-TF display is correct and
  klinecharts re-runs calc automatically on TF switch (the indicator effect does NOT depend on
  `displayCandles`). `pane:'main'` overlays the price (`IndicatorSeries.Price`, candle pane);
  `pane:'sub'` gets its own pane. Sub-pane ids are tracked in a ref for clean removal. Colors come
  from `INDICATOR_PALETTE` (theme).
- **Daily session breaks** (`DAY_BREAK`): vlines at each interior broker-day boundary (candle
  epochs are broker wall-clock, so boundaries fall on `DAY_MS` multiples; the left edge is
  skipped). Separate overlay name from `VLINE` so the two toggle independently. Own toggle.
- **Two header dropdowns, split by QUESTION, not by mechanism** (Aaron's call, 2026-07-27).
  **Analysis** = what the strategy DID with its signals — Trades (+ the Winners / Losers sub-filters)
  and Blocked (+ one sub-filter per reason). **Layers** = what to DRAW on the market — the four
  market-structure groups, indicators, day breaks. **Strategies** (stacks only) is a third. Trades and
  Blocked used to sit in Layers; they were moved because "which trades do I want to interrogate" and
  "which market structure do I want drawn" are different questions, and mixing them made a long menu
  where the two most-used rows were buried among structure groups.
- **All three dropdowns are ONE `ToggleMenu` component** (button with an `on/total` count + a list of
  dot/label/count/tick rows, `sub: true` indenting a filter under its parent). It owns its own open
  state and click-outside close, so adding a fourth menu is one call. Never hand-roll a fourth — three
  hand-rolled copies is exactly what this replaced, and they had already drifted (the Strategies list
  had no counts and different padding).
- **All layer toggles** use one `ToggleChip` component (colored dot + label).
- **Header + tool-strip layout (TradingView).** The header row carries the **symbol/interval**
  controls top-**LEFT** — timeframe dropdown, then Layers, then the drill-down fetch status — and
  the **snapshot (Copy)** button top-**RIGHT**. The header exposes three optional slot props so a
  host can fold ITS chrome onto this SAME single row rather than stacking a second bar above it:
  `headerLeading` (far left, before TF), `headerTrailing` (far right, after Copy), and
  `headerClassName` (appended to the row — e.g. a `border-b` when it doubles as a modal title bar).
  `PriceChartPanel` uses them in fullscreen to put its **instrument title (`spec.instrument`) + a
  minimize button** (`Minimize2`, the two-arrows-inward icon) on the same row as TF/Layers/Copy (it no
  longer renders a separate top bar) — so everything lives on one top row.
  Inline, the slots are unset and the header is just TF/Layers/Copy. Chart **tools** do NOT live in the header — they
  sit on a vertical **tool strip** (40px, `border-r`, `bg-bg-sunken`) down the far-left edge of the
  chart body, like TV's drawing toolbar. Currently Measure + Fibonacci (**icon-only** ruler /
  align-lines buttons); it's built to hold more. It runs the **FULL chart height** (default flex
  stretch, no explicit height) — all the way down past the x-axis, in its own 40px column left of the
  plot (so it never covers the x-axis labels, which start inside the canvas). **The strip is a flex
  sibling OUTSIDE the measure-capturing wrapper on purpose** — a tool button's click must not bubble
  into `handleChartClick` (that would drop a measurement anchor on the button). The chart itself is
  the flex-1 wrapper; the measurement overlay is `inset-0` of it and shares the chart's origin, so
  `pixelToChart` (which measures off `containerRef`) stays coordinate-consistent.
  **Copy aligned to the plot (`chartInset.axisW`, MEASURED).** Copy is a **borderless** flat camera
  icon; its right edge lines up flush with the y-axis (price-scale) line, not over the price scale —
  inset via the header right cluster's `paddingRight = axisW`, where `axisW` comes from klinecharts
  `chart.getSize('candle_pane', DomPosition.YAxis).width`, re-measured on init, resize (via the
  `ResizeObserver`), and each data/TF change (a new price range can change the y-axis digit width).
  (`chartInset.xAxisH` is still measured but unused now the strip is full-height.) `headerTrailing`
  (the minimize button) is
  **centred over the price-axis COLUMN** — an `absolute right-0` box of `width: axisW` with
  `justify-center` — so it sits above the price scale, not jammed in the corner, BEYOND the
  axis-aligned Copy. In fullscreen the body padding is trimmed to `pl-2 pr-2 pt-2 pb-2` (from `px-5`)
  to maximise chart space; the instrument title keeps a small `ml-1` so it isn't jammed to the edge.
  Tool-strip + Copy icons are sized ~18–20px (a touch bigger than the default 16px).
- **Copy image** (`copyChartImage` in `index.tsx`): the TradingView-style snapshot button, top-right
  of the header (see layout above). `chart.getConvertPictureUrl(true, 'png', theme.bgBase)` renders the canvas — candles plus
  every klinecharts overlay (trades, sessions, indicators, day breaks) — to a PNG data URL, which is
  copied to the clipboard via `navigator.clipboard.write([new ClipboardItem(...)])` so it pastes
  straight into a chat. The blob is passed to `ClipboardItem` as a **Promise** (keeps the user gesture
  alive on Safari). If clipboard image-write is unavailable/blocked it falls back to downloading the
  PNG (`<instrument>-<tf>.png`). The React measurement layer is a separate DOM overlay and is NOT in
  the snapshot (it's an interactive helper, not chart content).
- **Measurement tool** (`measureMode` state in `index.tsx`): its toggle button lives on the left tool strip (see layout above). TradingView-style click-to-anchor → move-to-preview → click-to-lock interaction. One measurement at a time (`measurement: LockedMeasurement | null`). The overlay div uses `pointerEvents: none` so klinecharts canvas receives all mouse events (crosshair stays live); click/mousemove handlers attach to the outer wrapper div and fire via bubbling. Label shows 2 rows: price change in points + percent (direction-colored) and bar count + duration (muted). Clicking anywhere while a measurement is locked clears it. Escape exits measure mode and clears all state.
- **Fibonacci tool** (`FIB` overlay + tool-strip button): a real, draggable, klinecharts-**native**
  drawing (not a DOM overlay like Measure), so it re-anchors on pan/zoom. The button arms
  `chart.createOverlay({ name: FIB })` → the user click-drags two swing points; on `onDrawEnd` the two
  anchor points (timestamp/value) are lifted into React state (`fibs`), which is **the source of
  truth** so a fib survives TF switches / data reloads (a `[fibs, displayCandles, pricePrecision]`
  effect re-creates them from state, mirroring the trade/session effects — `applyNewData` clears
  overlays). Each configured **level** draws a thin (`size: 0.5` → 1 physical px on retina) horizontal
  line spanning **exactly the box the user dragged** (both anchor x's — so width AND height follow the
  drag, NOT projected to the pane edge) plus a right-aligned `<ratio> (<price>)` label — decimal ratio
  + parenthesised price (e.g. `0.886 (3987.45)`), styled as the **same dark rounded chip as the trade
  level labels** (`chipBg` via `extendData`, `withAlpha` border in the level colour) so it reads over
  candles. Prices come from `overlay.points[i].value` via `yAxis.convertToPixel`, so they track the
  axis. Levels/colours are **Aaron's set** (`DEFAULT_FIB_LEVELS` in `overlays.ts`): 0/1 neutral grey,
  0.382/0.5 green, 0.618/0.702/0.786 blue, 0.886 red — edit that one array to retune. `precision`
  (label decimals) is inferred from instrument magnitude in `index.tsx`. **Delete (gotcha):**
  klinecharts REMOVES an overlay on right-click whenever its `onRightClick` returns falsy (source:
  `_figureMouseRightClickEvent`) — which silently deleted a fib on right-click. The fix: the fib's
  `onRightClick` returns **true** (keeps it) and stashes the fib id in `ctxFibRef` for the menu.
  klinecharts fires that right-click on `mousedown` (button 2) BEFORE the DOM `contextmenu`, so the
  React menu reads a fresh `ctxFibRef`. `onSelected` also marks a fib for the **Delete/Backspace** key
  (ignored while typing); `onPressedMoveEnd` writes an anchor-drag back to state.
- **Right-click menu** (`ctxMenu` state, incl. `fibId`): the chart body's `onContextMenu` opens a
  small viewport-`fixed` menu at the cursor (clamped), TradingView-style, and is **context-split** (per
  Aaron — fibs and the chart are separate concerns): right-click **on a fib** → a fib-only menu with
  just **"Delete this fib"** (deletes that one; no reset, no bulk-remove — clean up one at a time);
  right-click **on empty chart** → a chart-only menu with **"Reset chart view"** (restores the
  zoom/scroll — `setBarSpace` / `setOffsetRightDistance` / `scrollToRealTime` — captured into refs at
  init) and **Show/Hide trades**. The menu closes on Escape or any outside mousedown (it
  `stopPropagation`s its own mousedown so a click on an item isn't swallowed).
- **Decision (2026-06-14):** no per-trade trade table exists on the backtest page yet (trades
  are collapsed into `equity_curve` points — no per-trade entry/exit). Per Aaron, the clickable
  trade list + row→zoom is **deferred to Step 7**, when the real spec emitter provides per-trade
  data. Step 4 ships the chart overlay + toggle only.
- **Lifecycle.** Chart is `init()`-ed once on mount and `dispose()`-ed on unmount; a
  `ResizeObserver` calls `chart.resize()`. Data is (re)applied in a `spec`-keyed effect so the
  spec can change without re-initialising.

---

## Status

All build steps complete (1–6, 7a, 7b, 8). The panel renders real per-run specs end-to-end:
candles, timeframe switch, sessions, trades, generic structure overlays (box/hline/vline),
shipped indicators (EMA main-pane / ATR sub-pane), daily breaks, the TradingView-style measurement
tool, a draggable Fibonacci tool (Aaron's levels/colours, price labels), and a right-click menu
(Reset chart view / remove fibs). Backend emitter is `services/chart_spec.py`. Build history is in git.
