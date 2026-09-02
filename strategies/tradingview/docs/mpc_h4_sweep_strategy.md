# mpc_h4_sweep_strategy.pine — commentary

The prose that used to live inline in the Pine. Each entry is anchored from the
source by a `// [doc N]` line. Grep this file for `## [N]` to find one.

**Covers:** `mpc_h4_sweep_strategy.pine`, `mpc_h4_sweep_strategy_export.pine`

---

## [1] MPC H4 SWEEP — liquidity sweep → candlestick confirmation → LTF close en

```
// ============================================================================
//  MPC H4 SWEEP — liquidity sweep → candlestick confirmation → LTF close entry
// ============================================================================
// Aaron's own setup, written from his description on 2026-08-05. THREE timeframes,
// one job each:
//
//   LIQUIDITY (H4)     a new H4 opens; the PREVIOUS H4's high and low become the
//                      two levels. Price mitigating one of them starts a setup.
//                      High taken  → we want to SELL (fade the grab).
//                      Low taken   → we want to BUY.
//   CONFIRMATION (15m) the FIRST qualifying candlestick pattern to close AFTER the
//                      sweep, on the fade side. Its CLOSE becomes the trigger line
//                      (Aaron draws this by hand and labels it "15m.C.C").
//   ENTRY (chart, 5m)  the first chart candle to CLOSE beyond that line. That close
//                      IS the entry. Stop beyond the confirmation pattern's extreme.
//   EXIT               half off at 1:1, stop to breakeven on that same touch, and the
//                      rest rides a %-of-price ratchet with no target at all.
//
// ── WHY THERE IS NO 1:2 ANY MORE (Aaron, 2026-08-05) ─────────────────────────
// This file shipped with a fixed `rrRatio` of 2.0 and it is gone. The H4 sweep study
// (docs/H4_SWEEP_STUDY.md, Part 2) measured the SAME event set through both exits: a fixed
// 2R ceiling makes +0.117 expected R and a runner makes +0.409. The ceiling was throwing
// away two thirds of the edge, because a handful of trades that run a very long way carry
// the whole book — best single trade +25.4R, top five 71% of the profit. A+ Run 9 measured
// the identical shape on a different strategy (11 of 164 trades carried 106R of 109R), so
// this is the second independent time a fixed target has been the thing capping what pays.
// Raising 1:2 to 1:3 or 1:5 does not fix it; it moves the ceiling.
//
// ⚠ SO THE WIN RATE WILL FALL AND THAT IS NOT A REGRESSION. A runner gives back its open
// profit on the way out by construction, and the study's winning config wins 41% of the
// time. Read the expectancy and the drawdown, never the win rate — a 1:1-and-stop build
// wins far more often and makes less.
// ⚠ TP1 STILL EXISTS, and at 1:1, which is Aaron's own rule: half off at 1R takes the
// trade to a free ride and is what makes a 41% win rate survivable to hold through. It is
// also the one thing the study did NOT measure — every config there was all-or-nothing at
// the trail. So the 50% rung is a stated preference, not a measured optimum; sweep it.
//
// ⚠ THE CHART TIMEFRAME IS THE ENTRY TIMEFRAME. Run this on 5m. Pine reads HIGHER
// timeframes cleanly and lower ones badly (a 15m chart asking for 5m sees only the
// last 5m value inside the forming bar), so the entry has to be the chart itself and
// the other two are pulled up.
//
// ── SCOPE (Aaron, 2026-08-05) ────────────────────────────────────────────────
// ONE FILE. No export mirror, no cfg_ columns, no Python port, and nothing added to
// mpc_assistant.pine. This exists to answer one question — does the sequence produce
// trades, and are they worth anything — in the TradingView Strategy Tester. If it
// proves out, the port is a separate job with its own parity harness, and it will be
// a retrofit; that cost is known and accepted.
//
// ── WHAT IS NEW HERE, AND WHY IT HAD TO BE WRITTEN ───────────────────────────
// Nothing in this repo detects a Harami or an Engulfing. Not mpc_assistant.pine, not
// any engine, not any strategy. The labels on Aaron's chart come from a SEPARATE
// public indicator — "Candlestick Patterns Identified, update 1-17-26" by repo32 —
// and the fifteen definitions in the CANDLESTICK block below are ported from it
// VERBATIM, with exactly one deliberate change (see THE TREND FILTER IS GONE).
//
// Ported rather than re-derived on purpose. Aaron has been reading this setup off
// that indicator's labels for weeks; a Harami written from the textbook would mark
// different candles, and every disagreement would then read as a strategy result
// rather than a definition mismatch. That is this repo's most-repeated defect —
// two implementations of one idea, quietly disagreeing — and porting the source
// is the only thing that forecloses it.
//
// ── THE TREND FILTER IS GONE, AND IT IS THE ONE CHANGE FROM THE SOURCE ───────
// Every pattern in repo32's script ends with `open[trend] < open` (bearish) or
// `open[trend] > open` (bullish) — "was the open N bars ago below/above this one",
// N being a panel input defaulting to 5. It is a proxy for "price came up into this
// candle", and Aaron's call (2026-08-05) is that it is the wrong tool:
//
//   "Candlesticks should only be read at entry points for my setups, and if
//    liquidity has been swept."
//
// He is right, and the reason is worth keeping. The H4 sweep answers the same
// question PROPERLY — price did not merely rise, it took out a specific four-hour
// high and the stops resting behind it. A bars-ago price comparison is a weaker
// version of something the sequence already establishes. Worse, it was near-INERT
// here: you only look for a bearish pattern once the H4 high is swept, at which
// point price is at a high, so `open[5] < open` passes almost every time. It cost
// signals everywhere else and bought nothing here.
//
// ⚠ SO THIS STRATEGY WILL MARK CANDLES AARON'S OWN CHART DOES NOT. The filter only
// ever REMOVED patterns, so dropping it ADDS them back. That is intended, and it is
// why `showConfLabel` defaults ON — put this beside the indicator and the difference
// is visible candle by candle rather than inferred from a trade count.
//
// ⚠ THE LOCATION GATE REPLACES IT, AND IT IS DELIBERATELY NOT BAKED INTO DETECTION.
// Every pattern is detected on every 15m bar; the SWEEP decides which ones are read.
// Detection and permission stay separate for the same reason engines/news/ separates
// them ("the engine reports, the bot decides") and the FVG engine emits every gap
// with its direction flag and lets the consumer choose. Gate the detector instead and
// (a) this setup's gate stops serving the REV setup, which wants a fib band and a
// gap, not a sweep, and (b) the counterfactual is destroyed — you could never measure
// how many candles the location filter refused, which is the only way to learn
// whether it helps. The CANDLESTICK block below is self-contained for exactly this
// reason: wiring it into A+ later is copying one block and passing a different
// location, not untangling it from H4 logic it was written inside.
//
// ── WHAT CAME FROM THE "SWEEP AND ENGULF" SCRIPT, AND WHAT DID NOT ───────────
// Aaron brought a third-party script on 2026-08-05. Three of its ideas landed here and
// the rest was refused; recording both halves, because the refusals are the reusable part.
//
// TAKEN: (1) its signal, as the SWEEP + ENGULF pattern — one candle taking the previous
// candle's extreme and closing clean through the other side. It is genuinely stronger than
// repo32's Engulfing, which measures only against the previous candle's OPEN and ignores
// its wicks. (2) an ATR STOP as an alternative to the pattern extreme. (3) its
// previous-candle direction filter, generalised to name BOTH readings rather than only the
// one that script shipped.
//
// REFUSED, and why each would be a regression here:
//   · Its INVERT switch. Note it shipped defaulting to TRUE — the author is trading the
//     opposite of the thing the script is named after, which is a RESULT rather than a bug
//     and agrees with docs/H4_SWEEP_STUDY.md finding continuation dead and the fade real.
//     But with invert on, its EMA gates the PATTERN rather than the TRADE, so a short ends
//     up requiring price ABOVE the EMA. That is the exact defect `useEma`'s tooltip below
//     already names — it was written about this script.
//   · FIXED CONTRACT SIZING (`default_qty_value = 1`). Every trade then risks a different
//     amount, R stops meaning anything, and the curve is dominated by whichever trades
//     happened to carry the widest stops.
//   · Its DUPLICATE EXIT ENGINE — a hand-rolled `inTrade`/`hitTP`/`hitSL` state machine
//     running alongside `strategy.exit`, with the boxes drawn off the hand-rolled one, so
//     the picture and the Strategy Tester can disagree about the same trade.
//   · NO `process_orders_on_close`. It prices the stop and target off the close and then
//     fills at the next bar's OPEN, so its advertised 1:2 is measured against a price it
//     never filled at. See ORDER FILLS below.
//   · Its FIXED R:R, for the reason stated above.
//
// ── EIGHT OF THE FIFTEEN REPO32 PATTERNS CANNOT FIRE ON GOLD, AND THEY SHIP ANYWAY ──
// Gold's intraday opens equal the previous close except at the 18:00 NY reopen and
// the Sunday open. Substitute `open == close[1]` and eight patterns become
// arithmetically impossible:
//   Hanging Man    `high[1] < open`, but open == close[1] <= high[1]
//   Evening Star   `min(open[1],close[1]) > close[2]`, but open[1] == close[2]
//   Morning Star   the mirror
//   Shooting Star  `open > close[1]`
//   Piercing Line  `open < low[1]`, but open == close[1] >= low[1]
//   Bullish Belt   `open < lowest(10)[1]`, plus `low == open` exactly
//   Bull Kicker    `open >= open[1]` after a down candle
//   Bear Kicker    `open <= open[1]` after an up candle
// Every one needs a GAP. They are not deleted and not disabled in code — they get
// toggles like the rest, defaulted OFF, so the zero can be confirmed rather than
// taken on trust. A pattern that silently never fires is indistinguishable from a
// broken one, and this repo has been bitten by exactly that shape before.
//
// ⚠ HAMMER AND INVERTED HAMMER ARE USED BY SHAPE, NOT BY THEIR CLASSICAL NAME, and
// that will look like a bug if this note is not read. Both are classically bullish.
// Here the INVERTED HAMMER (long UPPER wick) is offered as a BEARISH confirmation and
// the HAMMER (long LOWER wick) as a bullish one. The reason is the location gate: an
// inverted hammer sitting on a freshly swept H4 high is a rejection of that high —
// it is the Shooting Star candle, which cannot fire here because it demands a gap.
// Neither carries a trend filter or a colour requirement in the source, so away from
// a location they are noise; the sweep is what makes them signal.
//
// ── ORDER FILLS ──────────────────────────────────────────────────────────────
// `process_orders_on_close = true`. Aaron's rule is that the entry IS the close of
// the chart candle that closed beyond the line, and his own worked example prices it
// there (5m close 4255.97, stop 4264.35 — 8.38 of risk, so TP1 lands at 4247.59).
// Without this flag Pine fills a market order at the NEXT bar's open while
// the stop and target are still computed off the close, which is the defect in the
// script from the video Aaron took this idea from: an advertised 1:2 measured against
// a price the strategy never filled at. The honest way to price the real-world gap
// between "the close" and "your fill a second later" is Properties → Slippage, not a
// different fill model.
// ============================================================================
```

## [2] THE INPUT PANEL — one consolidated block, twelve numbered sections

```
//============================================================================
//  THE INPUT PANEL — one consolidated block, twelve numbered sections
//============================================================================
// Every strategy Pine in this repo uses the SAME numbered sections in the SAME order,
// so section 5 is Entry whichever file you open. A strategy with no fibs simply has no
// `9 · Drawing: fibs`; the numbering does NOT close up, because the number is the address.
//
// THE RULE THAT DECIDES A SECTION: ask what a setting CHANGES, never what it is ABOUT.
// It goes in 3-7 if it can move a trade, and 8-12 if it can only move a pixel.
//
// 🔴 THAT IS WHY THE FVG SETTINGS LIVE IN `5 · Entry` RATHER THAN AN "FVG" GROUP. Both
// min-gap floors, the middle-bar close test, the max-active cap and keep-until-broken all
// change WHICH GAPS EXIST, and therefore which entries fire — as does `eqExemptFvg`, which
// used to sit under Liquidity Levels. Grouping by NAME would have demoted five
// trade-deciding knobs to the bottom of the panel beside the fib colours, and nothing
// would have errored. A group named for an OBJECT attracts anything that mentions it;
// a group named for a JOB gives a new toggle exactly one honest home.
//
// ⚠ THIS BLOCK IS THE PANEL. Order here IS the order on screen: TradingView sorts groups
// by where each group's first input is declared and sorts within a group by declaration
// order. Do not scatter a new input back out to its use site — put it in its section here.
//
// ⚠ AN INPUT USED IN ANOTHER'S `active =` MUST BE DECLARED ABOVE IT. The section order
// already satisfies every such pair; keep it that way when adding one.
//
// ⚠ ADDING, REMOVING OR REORDERING AN INPUT RESETS SAVED CHART VALUES — TradingView keys
// them off declaration order within each type. `indicators/docs/PINE_INPUT_DEFAULTS.md` exists
// so that a pass like this can be PROVEN cosmetic by re-dumping and diffing rather than
// argued to be.
//============================================================================
```

## [3] ── 2 · Market structure ────────────────────────────────────────

```
// ── 2 · Market structure ────────────────────────────────────────
// ⚠ THIS SECTION IS PURE DRAWING IN THIS FILE, AND THAT IS THE ONE THING TO KNOW ABOUT IT.
// Every other strategy here READS the structure engine — A+ prices its fibs off it, D's whole
// sequence is built out of SOS events. This one does not: it trades an H4 liquidity sweep
// confirmed by a candlestick pattern, and it consumes no swing, no BOS and no SOS. The engine
// was ported in on 2026-08-12 so that section 2 is identical on all five charts (Aaron: "on all
// of my strategies, the market structure should be the exact same"), and it can therefore never
// move a trade in this file — flip any of these four and the trade list is unchanged.
```

## [4] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  THE ANNOTATION PALETTE — copied from mpc_strategy.pine, never chosen here
// ════════════════════════════════════════════════════════════════════════════
// ⚠ EVERY COLOUR A TRADE IS DRAWN IN IS THE A+ BOT'S (Aaron, 2026-08-12): "all those colors
// are not consistent across all the pines. They should be the same colors. Use MPC, the A+
// strategy as a standard." One result means one colour on every chart in this repo, so a
// reader moving between strategies never has to re-learn what green is. **Change a value
// here only by changing `mpc_strategy.pine` first and copying it down.**
//
// This file previously had NO colour constants at all — every value was a hex literal at its
// use site, which is why it drifted without anybody being able to see that it had. The hues
// were mostly already A+'s; the TRANSPARENCIES were not, so the same green read as a
// different shade on each file.
```

## [5] 🔴 THIS FILE HAD NO BREAKEVEN STATE AT ALL, so a +0.02R scratch drew as a

```
// 🔴 THIS FILE HAD NO BREAKEVEN STATE AT ALL, so a +0.02R scratch drew as a full WIN and a
// −0.02R scratch as a full LOSS — the two loudest colours on the chart, for a trade that
// made nothing. Every other strategy here grades against a band and paints the middle
// orange. A+ exposes the band as an input (`execBeBandR`); this is its DEFAULT as a
// constant instead, because adding an input mid-paste resets every saved value on the
// chart and the value has never been tuned on this strategy anyway. Promote it to an input
// when the rest of this file's annotations are brought up to A+'s set.
```

## [6] ⚠ THE TRIGGER LINE AND ITS LABEL ARE ORANGE, AND ORANGE IS A+'s BREAKEVE

```
// ⚠ THE TRIGGER LINE AND ITS LABEL ARE ORANGE, AND ORANGE IS A+'s BREAKEVEN COLOUR. That
// collision is REAL and is left alone deliberately: recolouring the trigger is a choice
// about this strategy's own chart, not a copy of A+, and A+ has no trigger to copy from.
// It is recorded in indicators/CLAUDE.md as an open question rather than silently resolved.
```

## [7] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  1 · THE SEQUENCE
// ════════════════════════════════════════════════════════════════════════════
// The ENTRY timeframe is the CHART. There is no input for it, deliberately — an input
// would be a claim the code cannot honour, since Pine cannot read a lower timeframe
// reliably. Run the chart at 5m and the entry is 5m.
```

## [8] ── The three switches that turn this into a plain pattern strategy ─────

```
// ── The three switches that turn this into a plain pattern strategy ──────────
// Added 2026-08-05 so the "Sweep and Engulf" script Aaron brought can be reproduced in
// this file instead of run beside it. All three default to the H4 sequence, so the file
// is unchanged until they are moved.
//
// ⚠ WITH `reqSweep` OFF THIS IS THE CONTROL, AND THAT IS THE POINT. The H4 gate is the
// one claim this strategy makes that a plain candlestick strategy does not. Turning it
// off and changing nothing else measures exactly what the location is worth.
```

## [9] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  2 · CONFIRMATION CANDLES
// ════════════════════════════════════════════════════════════════════════════
// Fifteen from repo32's indicator plus Sweep + Engulf, split by which side of the trade
// they can confirm. Doji appears on BOTH — it carries no direction of its own, so at a
// swept high it reads bearish and at a swept low bullish, which is the location gate
// doing the work.
// DEFAULT ON: the four per side that can actually fire on a continuous instrument.
// DEFAULT OFF: the eight that need a gap (see the header), each named so the zero is
// checkable rather than assumed.
```

## [10] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  3 · RISK
// ════════════════════════════════════════════════════════════════════════════
```

## [11] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  4 · FILTERS — every one OFF by default
// ════════════════════════════════════════════════════════════════════════════
// Off is not timidity, it is the only way the filter can be judged. A filter that
// ships ON means the unfiltered result is never seen, so nobody can say what it was
// worth. Baseline first, then one switch at a time.
```

## [12] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  5 · DRAWING — none of this changes a trade
// ════════════════════════════════════════════════════════════════════════════
```

## [13] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  MARKET STRUCTURE — the canonical engine, DRAWING ONLY in this file
// ════════════════════════════════════════════════════════════════════════════
// Lifted BYTE-FOR-BYTE from the since-deleted strategies/tradingview/mpc_d_strategy.pine
// (removed 2026-08-15 — recover from git history), which lifted it from
// indicators/engines/structure_engine.pine, itself the external+internal half of mpc_assistant.pine.
// It is not re-implemented here — a second structure engine is forbidden by CLAUDE.md and
// would be the thing that silently drifts.
//
// ⚠ NOTHING BELOW THE ENGINE READS IT. This strategy trades an H4 sweep confirmed by a
// candlestick pattern; it consumes no swing, no BOS and no SOS, so this whole block draws and
// decides nothing. It is here so section 2 is the same four toggles on every chart in the repo.
// If a future rule in this file DOES start reading `st`, say so at the rule — the moment one
// does, this stops being a drawing block and the toggles stop being free.
//============================================================
//  SMC SETTINGS (hardcoded)
//============================================================
```

## [14] MARKET STRUCTURE — input selection (mirrors mpc_assistant.pine's GRP_STR

```
//============================================================
//  MARKET STRUCTURE — input selection (mirrors mpc_assistant.pine's GRP_STRUCT)
//============================================================
```

## [15] Swing-point labels are hidden by making their text transparent, not by s

```
// Swing-point labels are hidden by making their text transparent, not by skipping
// their creation. The label objects still exist and the engine's state is untouched,
// so structure tracking, fibs, OBs and the table behave identically either way.
```

## [16] SMC STRUCTURE TYPE

```
//============================================================
//  SMC STRUCTURE TYPE
//============================================================
```

## [17] Neither an active pullback high nor a confirmed ASH was available to

```
                // Neither an active pullback high nor a confirmed ASH was available to
                // promote — use the actual highest point since the last confirmed low so
                // a genuine swing high still gets confirmed instead of silently vanishing.
```

## [18] EXECUTION — EXTERNAL STRUCTURE

```
//============================================================
//  EXECUTION — EXTERNAL STRUCTURE
//============================================================
// External structure engine — majorLength=15, blue/red, prefix ""
```

## [19] EXECUTION — INTERNAL STRUCTURE

```
//============================================================
//  EXECUTION — INTERNAL STRUCTURE
//============================================================
// Internal structure — Step 2: pullback tracking to confirm iSH / iSL
```

## [20] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  CANDLESTICKS — ported from repo32, self-contained, location-agnostic
// ════════════════════════════════════════════════════════════════════════════
// Runs on whatever timeframe it is called from. It knows nothing about sweeps, fibs
// or gaps and must not learn: this block is meant to be lifted into the A+ file
// unchanged and handed a different location.
//
// Returns a CODE rather than a name so the tuple crossing request.security stays
// numeric. Precedence runs strongest-first, and it decides the STOP as well as the
// label — a two-candle pattern is measured across both candles, a three-candle Star
// across all three, and a single-candle wick or Doji across its own range only.
// Taking `max(high, high[1])` for a one-candle pattern would put the stop on an
// unrelated neighbour, which is a wider stop bought for nothing.
//
//   11 Sweep + Engulf (ranked first — strictly the strongest)
//   1 Harami · 2 Engulfing · 3 Wick rejection · 4 Doji · 5 Kicker
//   6 Star   · 7 Hanging Man · 8 Shooting Star · 9 Piercing · 10 Belt
// `lag` is how far back the answer is read. 1 = the last CLOSED bar, which is the
// non-repainting read for a HIGHER timeframe. 0 = this bar, which is correct and safe only
// when the caller is on the same timeframe. `simple int` is required — Pine will not accept
// a series value as a history offset.
```

## [21] ── The one pattern here that is NOT repo32's ───────────────────────────

```
    // ── The one pattern here that is NOT repo32's ────────────────────────────
    // Took out the previous candle's extreme and closed clean through the other side.
    // It is a SWEEP measured against the previous candle, nested inside the H4 sweep the
    // setup already required — two grabs at one location, not a duplicate of one.
    // Deliberately says nothing about the previous candle's colour or body, unlike the
    // Engulfing below: what matters is that its wick was taken and its whole range lost.
```

## [22] BOTH extremes of each pattern's span. The high is the stop for a short a

```
    // BOTH extremes of each pattern's span. The high is the stop for a short and the low
    // is the stop for a long, so the Invert switch needs the other one — without it an
    // inverted trade would have to stop at a price on the wrong side of its own entry.
```

## [23] Everything is returned one bar back. Combined with lookahead_on at the c

```
    // Everything is returned one bar back. Combined with lookahead_on at the call
    // site this is Pine's canonical non-repainting higher-timeframe read: it hands
    // over the LAST CLOSED confirmation bar, identical on history and in realtime.
    // Without it the forming 15m bar's pattern flickers true and false intrabar and a
    // latch would catch a candle that never existed.
    // ATR rides out on this tuple rather than being taken on the chart, because it stands
    // in for the SIZE OF THE 15m PATTERN. A 5m ATR would be roughly a third of the right
    // scale and would produce stops far tighter than the candle they replace — which is
    // the collapsing-stop hazard, not a tighter risk.
```

## [24] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  HIGHER-TIMEFRAME READS
// ════════════════════════════════════════════════════════════════════════════
// The LEVELS come up from the liquidity timeframe, but the SWEEP is detected on the
// chart's own bars — so a level taken at 15:07 is known at 15:07, not at the H4
// close. Same split mpc_assistant.pine uses for its H4 tracker.
```

## [25] TWO reads, and the pairing of lag with lookahead is what makes both of t

```
// TWO reads, and the pairing of lag with lookahead is what makes both of them honest.
// Delayed  = lag 1 + lookahead ON  — Pine's canonical non-repainting higher-timeframe read.
// Live     = lag 0 + lookahead OFF — this bar's own value, never a peek at a forming one.
// Pairing them the other way round is the classic repaint bug: lag 0 with lookahead ON
// hands history a bar that had not finished, and the backtest prints results nobody could
// have traded. Both are computed and one is selected, because `lookahead` must be a
// constant and so cannot be switched by an input.
```

## [26] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  SETUP STATE — one window, one setup
// ════════════════════════════════════════════════════════════════════════════
// Everything here is scoped to a single liquidity candle and wiped when the next one
// opens. An OPEN TRADE is deliberately NOT wiped (Aaron, 2026-08-05): the window
// bounds the SETUP, not the position. Once the entry has triggered only the stop or
// the target closes it, and a new H4 arriving mid-trade simply starts a fresh setup
// that the one-position rule will refuse while the old trade is alive.
```

## [27] The direction the ORDER goes, which is the pattern's side unless Invert 

```
// The direction the ORDER goes, which is the pattern's side unless Invert is on.
// `setupDir` stays the PATTERN side throughout — it is what the levels, the labels and
// the pattern names are keyed to, and flipping it would make the chart describe a candle
// that never fired.
```

## [28] ⚠ The state wipe is gated on `reqSweep`. Without that gate a new H4 cand

```
// ⚠ The state wipe is gated on `reqSweep`. Without that gate a new H4 candle would still
// arrive every four hours and destroy a setup the free-running path had just armed, which
// would look like patterns being ignored at random.
```

## [29] ── THE SWEEP ───────────────────────────────────────────────────────────

```
// ── THE SWEEP ───────────────────────────────────────────────────────────────
// A WICK takes the level, not a close. A sweep is price reaching the stops resting
// beyond a high; whether the candle closed back inside describes what happened AFTER
// the liquidity was taken, not whether it was taken. Same reading mpc_assistant.pine
// applies to its EQH/EQL levels and its order blocks.
// ⚠ FIRST SWEEP OWNS THE WINDOW. If the high goes and later the low goes too, the
// window is still the short setup — "for every new H4 there is A setup", singular.
// Both on one bar is unresolvable at chart resolution, so the high wins by order.
```

## [30] ── THE CONFIRMATION ────────────────────────────────────────────────────

```
// ── THE CONFIRMATION ────────────────────────────────────────────────────────
// The FIRST qualifying pattern to close after the sweep wins, and nothing later moves
// the line (Aaron, 2026-08-05). A line that re-anchored on every new pattern would
// walk down with price and either never trigger or trigger progressively worse.
// ⚠ `cTime > sweepT` is what enforces the ORDER, and it is a genuine test rather than
// a formality: the pattern is read on the confirmation timeframe while the sweep is
// detected on the chart, so without it a 15m candle that closed BEFORE the sweep
// could arm a setup the sweep had not yet created.
```

## [31] ── THE SAME STEP WITH NO SWEEP REQUIRED ────────────────────────────────

```
// ── THE SAME STEP WITH NO SWEEP REQUIRED ────────────────────────────────────
// The control path. Every confirmation bar is a fresh setup: the pattern supplies the
// direction, there is no window, and nothing carries over. `firedWindow` is cleared each
// time because it exists to enforce ONE setup per H4 window, and there are no windows here.
// ⚠ The new arm is built into LOCALS and only committed if a pattern actually fired.
// Writing the state first and filling it in second would mean a confirmation bar with no
// pattern — the common case — silently deleted a setup that was still waiting for its
// trigger, and the setup would live about three chart bars instead of until it is replaced.
```

## [32] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  ENTRY
// ════════════════════════════════════════════════════════════════════════════
// ONE AT A TIME (Aaron, 2026-08-05). `strategy.position_size == 0` is the whole rule:
// a setup that fires while a trade is running is skipped, never stacked. Stacking is
// the only variant where the risk per trade stops being what the input says it is.
```

## [33] f_ratchet — the runner's trail, ported from `f_swingRatchet` in mpc_stra

```
// f_ratchet — the runner's trail, ported from `f_swingRatchet` in mpc_strategy.pine with
// the one change this file forces: A+ anchors on the last confirmed swing, and there is no
// structure engine here, so the anchor is the breakeven stop. From that anchor the stop
// climbs one `pct`-of-price step for every step of favourable move.
// It returns the ANCHOR until the move is one full step past it, so the trail can never be
// looser than breakeven — only equal or tighter. That is what makes it safe to call from
// the moment TP1 is touched.
```

## [34] ⚠ Keyed to ccTradeDir, NOT setupDir — with Invert on they are opposites,

```
// ⚠ Keyed to ccTradeDir, NOT setupDir — with Invert on they are opposites, and the trigger
// has to follow the ORDER. The line test flips with it: a trade that is short wants a close
// below the line whichever pattern armed it.
```

## [35] `tStop` is the trade's FROZEN opening stop and is never rewritten — it i

```
// `tStop` is the trade's FROZEN opening stop and is never rewritten — it is the 1R
// yardstick every R number here is measured against, and the price the log reports.
// The LIVE stop is `curStop` below, recomputed each bar from the stage.
```

## [36] ⚠ THE TRIGGER IS ONE SHOT, WHETHER OR NOT IT BECOMES A TRADE. `firedWind

```
// ⚠ THE TRIGGER IS ONE SHOT, WHETHER OR NOT IT BECOMES A TRADE. `firedWindow` is set
// on the trigger itself, not on the order — so a close beyond the line that a filter
// REFUSES kills the setup rather than leaving it armed to retry on the next bar. The
// rule is "the FIRST close beyond the line"; a retry would enter deeper on a later
// candle and quietly stop being that rule.
```

## [37] ── PARITY RECORD — WRITE-ONLY ──────────────────────────────────────────

```
// ── PARITY RECORD — WRITE-ONLY ───────────────────────────────────────────────
// NOTHING in this file reads these four. They exist so `mpc_h4_sweep_strategy_export.pine`
// can COPY the refusal this gate made, rather than re-deriving it from prices further down
// the file. `okMin` / `okTrig` / `emaOk*` are locals inside the two trigger blocks and are
// gone by the time anything else runs, so without this the export would have to recompute
// them — a SECOND implementation of the gate, which is exactly what every other export twin
// in this repo is built to avoid. A copied value cannot disagree with the thing it copied.
//
// hTrigCode: 0 = the trigger was TAKEN · 1 = stop distance not positive (an `na` ATR, or a
// pattern extreme on the wrong side of the close) · 2 = stop too tight for `minStopPct` ·
// 3 = the trigger candle closed too far past the line for `maxTrigPct` · 4 = the EMA filter.
// ⚠ 5 = the trade DIRECTION is switched off. Numbered last and ranked FIRST: a code is a WIRE
// FORMAT that px_blk carries into an export already on disk, so an existing number can never be
// renumbered — only its place in the chain moves, and a disabled side refuses before anything else.
// Ordered as the `if` reads them, so the code names the FIRST rule that refused rather than
// whichever one happens to be checked last.
```

## [38] ⚠ THE SIDE HAS TO BE RECORDED RATHER THAN INFERRED, and the deleted `mpc_d_strategy.

```
// ⚠ THE SIDE HAS TO BE RECORDED RATHER THAN INFERRED, and the deleted `mpc_d_strategy.pine` already paid for
// learning that. Its blocked tag read the direction off the SOS that fired on the same bar, which
// was correct only while every candidate arrived on one — and the moment a second entry mode
// existed, every candidate drew as a SHORT. Here the equivalent shortcut would be reading
// `trigShort`, which is a per-bar local: correct today, and silent the day a refusal is reported
// from anywhere but these two blocks.
```

## [39] ⚠ A DISABLED SIDE DOES NOT CONSUME THE WINDOW, unlike every other refusa

```
    // ⚠ A DISABLED SIDE DOES NOT CONSUME THE WINDOW, unlike every other refusal here. A
    // stop-too-tight refusal is about this setup; 'shorts off' is about every short in the run,
    // and burning the window would silently remove LONGS that shared it — so a long-only
    // measurement would not be the long book.
```

## [40] R is measured off the size ACTUALLY sent, not off the size we wanted, so

```
        // R is measured off the size ACTUALLY sent, not off the size we wanted, so the R
        // labels stay honest under fixed sizing instead of quietly describing a different
        // position from the one the tester opened.
```

## [41] ══ BLOCKED-SETUP TAG ═══════════════════════════════════════════════════

```
// ══ BLOCKED-SETUP TAG ═══════════════════════════════════════════════════════
// A confirmation candle fired inside a live sweep window — the one structural fact this
// strategy is built on — and a gate refused it. These are the only setups that are invisible
// everywhere else: no order is sent, so nothing is drawn, no row reaches the trade list, and
// the Strategy Tester cannot know they existed. That makes it impossible to judge whether a
// gate is protecting the account or costing it. Now each one prints a PINK tag with the reason
// on hover and a dotted leader to the price the entry would have taken — so you can flip the
// gate off, re-run, and compare.
//
// ⚠ IT READS `hTrigCode`, WHICH THE TRIGGER BLOCKS ALREADY WROTE, and does not re-derive
// anything. `okMin` / `okTrig` / `emaOk*` are locals inside those blocks, so recomputing the
// refusal here would be a SECOND implementation of the gate that can disagree with the gate —
// the trap the export twin's own header records. The tag and the export's px_blk therefore
// cannot tell different stories, because they read one variable.
//
// ⚠ NO DEDUPE, unlike A+'s marker, and it is not an omission: a trigger fires at most ONCE per
// H4 window (`firedWindow`), so one refusal is already one bar. A+ needs its sosBar+code key
// because a setup there can stay refused for twenty consecutive bars.
//
// ⚠ `hTrigBar == bar_index` is what scopes it to THIS bar. The four `hTrig*` fields are `var`
// and keep the last trigger's values for ever, so without that test the tag would redraw the
// same refusal on every bar until the next trigger replaced it.
```

## [42] ── Stage the stop ──────────────────────────────────────────────────────

```
// ── Stage the stop ──────────────────────────────────────────────────────────
// ⚠ `bar_index > tBar` EXCLUDES THE ENTRY BAR, and it is load-bearing. The entry fills at
// this bar's CLOSE (process_orders_on_close), so everything the candle did before that
// close happened while the trade did not exist — reading its extreme as favourable
// movement is how `BUG_exit_fill_price_mismatch.md` promoted a stop to breakeven on a move
// the position was never in, which then sits on the wrong side of the market and blows the
// trade out at the next bar's open. A+ guards this with `position_size[1]`; that test is
// wrong here, because with fills on the close `position_size` is still 0 when the script
// runs on the entry bar, so `[1]` would also skip the first REAL bar of the trade.
// Every later bar counts: the trade held through all of it.
```

## [43] Stage 1 is tied to the TP1 TOUCH, not to an R distance. TP1 is a limit o

```
// Stage 1 is tied to the TP1 TOUCH, not to an R distance. TP1 is a limit order, so keying
// breakeven off the touch is what guarantees the partial banks BEFORE the rest of the
// position is protected — an R trigger can fire on a wick that never filled the limit and
// then protects a trade that has taken no profit at all.
```

## [44] The brackets are re-issued every bar so the stop can move. Two details, 

```
// The brackets are re-issued every bar so the stop can move. Two details, both of which
// leave a real hole if they are "tidied":
//
// ⚠ `or tookLong` PLACES THE BRACKET ON THE ENTRY BAR, and without it the trade spends its
// first bar with no stop. `process_orders_on_close` fills the entry at THIS bar's close, so
// `strategy.position_size` is still 0 while the script runs here — a position-size test
// alone would not place an exit until the next bar's close, and anything the market did in
// between would have gone unguarded. Pine accepts an exit for an entry order that has not
// filled yet, so issuing both on the same bar is the correct shape.
//
// ⚠ TP1 STOPS BEING RE-ISSUED ONCE TOUCHED. `strategy.exit` with an id whose order already
// FILLED places a NEW order rather than modifying the old one, so a re-issued rung would
// bank another slice of the runner every bar, at a limit the market is already past. The
// A+ file re-issues its rungs unconditionally and gets away with it only because its rungs
// ship at 0% and the call is skipped entirely — do not copy that shape here.
```

## [45] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  DRAWING THE TRADE
// ════════════════════════════════════════════════════════════════════════════
// Red from entry to the opening stop, green from entry to TP1 — the picture from Aaron's
// own position tool. Both boxes are frozen at the PLAN, so they still describe what was
// risked and where the half came off even after the stop has moved.
// ⚠ THERE IS NO BOX FOR THE RUNNER, and that is the honest drawing rather than a missing
// one: TP2 is a trail, so the runner has no target price to draw a box to. What it has is
// a stop that moves, and that is the dashed line — watch it leave the entry and climb.
```

## [46] The moving stop, one segment per staged bar — the staircase IS the trail

```
// The moving stop, one segment per staged bar — the staircase IS the trail, and watching
// it is the only way to judge whether the ratchet step is too loose. Drawn only while
// staged, so it costs nothing on the trades that never reach TP1.
// ⚠ Segments past `max_lines_count` are dropped oldest-first by TradingView, so on a long
// backtest the early trades lose their staircase. The trade boxes are unaffected.
```

## [47] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  RESULT
// ════════════════════════════════════════════════════════════════════════════
// Graded in R against the dollars actually put at risk, so a win and a loss are
// comparable across a $2 stop and a $20 one. That is the entire reason the sizing is
// percent-of-equity rather than a fixed lot.
```

## [48] ════════════════════════════════════════════════════════════════════════

```
// ════════════════════════════════════════════════════════════════════════════
//  LOG
// ════════════════════════════════════════════════════════════════════════════
// Every line carries the PATTERN. Harami and Engulfing are exact complements on a
// continuous instrument, so one tagged run answers "which pattern is carrying this"
// by slicing — no second and third run needed.
```

## [49] Entry markers, so a trade is never invisible even when the boxes are swi

```
// Entry markers, so a trade is never invisible even when the boxes are switched off.
// Keyed off tookShort/tookLong, NOT off strategy.position_size: with
// process_orders_on_close the fill lands at this bar's close, AFTER the script has
// run, so position_size is still 0 here and a size test would draw the marker one
// bar late — or, on a trade that opens and closes quickly, not at all.
```

## [50] ════════════════════════════════════════════════════════════════════════  _(only in mpc_h4_sweep_strategy_export.pine)_

```
// ════════════════════════════════════════════════════════════════════════════
//  PARITY / ANALYSIS EXPORT — per-bar DECISION STREAM
// ════════════════════════════════════════════════════════════════════════════
// This file is `mpc_h4_sweep_strategy.pine` + THIS appended block, and NOTHING else
// changed. The body above is byte-identical to the parent apart from line 166's title.
//
// ⚠ REGENERATE WITH THIS EXACT RECIPE — and CHECK THE PLOT COUNT AFTERWARDS.
//     B=$(grep -n 'PARITY / ANALYSIS EXPORT' <export> | head -1 | cut -d: -f1)
//     sed -n "$((B-2)),\$p" <export> > /tmp/blk
//     cp strategies/tradingview/mpc_h4_sweep_strategy.pine <export>
//     sed -i '' '166s/strategy("MPC H4 Sweep"/strategy("MPC H4 Sweep Export"/' <export>
//     cat /tmp/blk >> <export>
//     grep -c '^plot(' <export>      # MUST be 43  (42 here + the parent's Trend EMA)
// The count check is not ceremony. On 2026-08-06 the equivalent grep in the D export was
// anchored on the `//====` rule line, which does not contain the words it was matching, so
// it produced an EMPTY block — and every downstream check still passed, because a bare copy
// of the parent is byte-identical to the parent and compiles perfectly. It just silently
// exported nothing. A regeneration that loses the whole point of the file must fail loudly.
//
// ⚠ THIS FILE IS NEWER THAN THE PARENT'S OWN "SCOPE" HEADER, WHICH SAYS THERE IS NO EXPORT
// MIRROR. That paragraph was written 2026-08-05 when the strategy was a one-file question;
// Aaron asked for the twin on 2026-08-12 so the H4 sweep gets the same treatment as every
// other strategy here. There is still NO Python port and NO `compare_h4.py` — this export
// is the PREREQUISITE for one, not a substitute.
//
// WHY IT EXISTS. The Strategy Tester's trade list records FILLS. It cannot say which setups
// armed and never triggered, which triggers a filter REFUSED and why, how far a trade ran
// before it handed the move back, or what a different stop mode would have priced. On a
// strategy whose whole design question is "does the sequence produce anything worth having",
// those are the only interesting questions, so they get columns.
//
// ⚠ GOTCHA, inherited from every other export in this repo: a plotted column MUST use a
// transparent colour, never `display.none` — TradingView DROPS display.none series from the
// CSV. Every plot here uses _INV.
//
// ⚠ SECOND GOTCHA, and this one cost a day on the BOS export (2026-08-07): "TradingView
// exports volume" IS NOT TRUE. The CSV carries a Volume column only if the Volume STUDY is
// on the reader's chart, so it is a fact about somebody's chart layout rather than about the
// export format. `px_volume` is plotted here for that reason. Do not delete it as redundant.
//
// ⚠ THE TWO TIMEFRAMES AND THE EMA TIMEFRAME CANNOT BE EXPORTED. `tfLiq`, `tfConf` and
// `emaTf` are `input.timeframe` strings and `plot()` takes only a number, so no `cfg_*`
// column can carry them. A reader MUST record them alongside the CSV by hand. This is the
// one part of the configuration the file cannot state about itself, and it is also the part
// that changes what the strategy IS — an H4/15m run and an H1/5m run are different studies.
//
// ── READING THE STREAM ──────────────────────────────────────────────────────
// Most columns are na except on the bars where they mean something, so the CSV filters down
// to a few hundred rows out of a full export.
//
// px_seq is the bit field that tells you which kind of bar you are looking at:
//     1  a new liquidity candle opened — the levels rolled and any untriggered setup died
//     2  a level was swept this bar (the setup's direction was decided here)
//     4  a confirmation pattern armed this bar (`armedNow`)
//     8  a trigger fired this bar — TAKEN OR REFUSED, read px_blk to tell them apart
//     16 an entry filled this bar
//     32 the position closed this bar
//
// THE REFUSAL COLUMNS. px_blk is the parent's OWN `hTrigCode`, taken at decision time and
// copied — not re-derived here. That is exact by construction rather than by argument: there
// is no second implementation in this file that could disagree with the gate. 0 = the trigger
// was taken · 1 = stop distance not positive · 2 = stop too tight (minStopPct) · 3 = trigger
// candle too far past the line (maxTrigPct) · 4 = the EMA filter. px_cand_entry and
// px_cand_stop are set for a REFUSED trigger exactly as for a taken one, which is what lets a
// refusal be re-priced offline instead of merely counted.
//
// ⚠ A ZERO IN px_blk IS A REAL ANSWER AND AN EMPTY CELL IS NOT. The column is na on every bar
// that had no trigger; 0 means a trigger fired and passed every gate. Filter on px_seq bit 8,
// never on `px_blk > 0`, or every taken trade vanishes from the count.
//
// THE POINT OF px_cc_line / px_cc_stop / px_cand_entry. With those three on every trigger the
// strategy ever saw, you can compute OFFLINE what the other stop mode would have priced and
// what a different `maxTrigPct` cap would have refused, without re-running TradingView:
//     stop distance, pattern mode = |px_cand_entry - px_cc_stop| (+ the tick buffer)
//     how far past the line       = |px_cand_entry - px_cc_line|
//     that as a % of the stop     = the above / the stop distance * 100   ← what maxTrigPct caps
// That turns one export into a sweep of the entry filter instead of one configuration.
//
// px_mfe_r / px_mae_r are the running favourable and adverse excursion of the OPEN trade, in
// R, per bar. They are what the trade list cannot give you, and on THIS strategy they are the
// whole argument: the file ships a runner with no target, so the only way to judge the trail
// is to see how much of the favourable excursion it handed back. Both EXCLUDE the fill bar,
// for the same reason the parent's `tMaxFav` does — with `process_orders_on_close` the entry
// fills at this bar's close, so everything the candle did before that happened while the trade
// did not exist. (BUG_exit_fill_price_mismatch.)
//
// px_stage is read STRAIGHT off `tStage` rather than tracked separately here, and that is safe
// in this file specifically: `tStage` is only ever reset at the next ENTRY, so it still holds
// the final stage on the close bar. ⚠ The deleted `mpc_d_strategy_export.pine` tracked its own copy because
// that parent zeroes its stage on the close bar — do not copy this shortcut across without
// checking which shape the parent has.
```

## [51] ── Bar classification ──────────────────────────────────────────────────  _(only in mpc_h4_sweep_strategy_export.pine)_

```
// ── Bar classification ──────────────────────────────────────────────────────
// Built as a float local first. Pine does not reliably type an int-in-a-ternary against `na`,
// and four columns of the D export had to be rewritten this way at paste time.
```

## [52] ════════════════════════════════════════════════════════════════════════  _(only in mpc_h4_sweep_strategy_export.pine)_

```
// ════════════════════════════════════════════════════════════════════════════
//  DECISION COLUMNS
// ════════════════════════════════════════════════════════════════════════════
```

## [53] ════════════════════════════════════════════════════════════════════════  _(only in mpc_h4_sweep_strategy_export.pine)_

```
// ════════════════════════════════════════════════════════════════════════════
//  CONFIG COLUMNS — so a comparator configures the Python FROM the export
// ════════════════════════════════════════════════════════════════════════════
// ⚠ Codes are a WIRE FORMAT. An export already on disk carries the NUMBER, so renumbering one
// is silent — the file still reads and now claims a configuration it never ran. Append, never
// renumber, and never reuse a retired code.
```

## [54] The fifteen pattern toggles, packed in the order they are declared. Kept  _(only in mpc_h4_sweep_strategy_export.pine)_

```
// The fifteen pattern toggles, packed in the order they are declared. Kept OUT of cfg_bits
// deliberately: they are one family, they are the thing most likely to be swept, and a reader
// decoding them should not have to mask around five unrelated sequence switches.
```

