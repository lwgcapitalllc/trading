# mpc_strategy.pine — commentary

The prose that used to live inline in the Pine. Each entry is anchored from the
source by a `// [doc N]` line. Grep this file for `## [N]` to find one.

**Covers:** `mpc_strategy.pine`, `mpc_strategy_export.pine`

---

## [1] MPC A+ STRATEGY — backtest wrapper around the MPC-JARVIS engine

```
// ============================================================================
//  MPC A+ STRATEGY — backtest wrapper around the MPC-JARVIS engine
// ============================================================================
// Same market-structure / fib / liquidity / FVG / RSI-divergence engine as
// mpc_assistant.pine (kept byte-identical so the A+ sequence stays at parity),
// converted from indicator() to strategy() and given an execution layer at the
// end of the file. It trades ONLY the confirmed A+ reversal sequence:
//   sweep-or-divergence  ->  SOS (shift of structure)  ->  retrace into the
//   0.5-0.886 fib of that leg WITH a live FVG overlapping the zone.
// Exits: SL beyond fib 1.0 (leg origin), scaled fib-target ladder 30/30/40 at
// TP1 (0.5) / TP2 (0.382) / TP3 (0.0 = swing extreme). Sizing: fixed % risk.
// The execution block is the ONLY addition — do not let the engine above it
// drift from mpc_assistant.pine.
// ----------------------------------------------------------------------------
// TRADE-CRITICAL INPUTS — these compute the values the execution block reads, so
// turning ANY of them off stops trades (they are marked "(REQUIRED)" in the
// settings panel). Keep ALL of them ON:
//   • "Hide Everything Except Market Structure"  -> must stay OFF (it force-kills every feature)
//   • "Show External Fib (REQUIRED)"             -> SL / TP / entry price levels
//   • "Show FVG (REQUIRED)"                      -> the entry edges (limit price)
//   • "Show All Liquidity Levels (REQUIRED)"     -> arms setups via sweeps
//   • "Track RSI Divergence (REQUIRED)"          -> arms setups via divergence + veto
// Everything else (Sessions, Internal Fib, Sniper, structure labels) is cosmetic
// and defaults OFF — safe to toggle freely, it never affects trade firing.
// Kill Zones, VWAP, MV, Order Blocks and the Cycle Fib DRAWING have been deleted
// outright (2026-07-22 / 07-24 / 07-25 / 08-02) to stay under Pine's compile
// caps. The Cycle Fib's TRACKING survives and is not optional — it is the A+
// sequence's HTF POI. All of them still draw in mpc_assistant.pine.
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

## [3] Four corners, not nine (Aaron, 2026-08-04) — synced from mpc_assistant.p

```
// Four corners, not nine (Aaron, 2026-08-04) — synced from mpc_assistant.pine. The six
// middle/centre positions parked the table over the candles, which is the one place a
// status panel must never sit, and "Top Center" was the DEFAULT here. Text size loses
// "Huge" for the same reason and now defaults to Small.
```

## [4] The `=>` fallback on each is doing real work now that options have been 

```
// The `=>` fallback on each is doing real work now that options have been removed: a chart
// saved with "Top Center" or "Huge" still holds that string, and it lands here rather than
// on a position or size the panel no longer offers. That matters more in this file than in
// the indicator — "Top Center" was the shipped default, so every saved chart holds it.
```

## [5] SMC SETTINGS (hardcoded)

```
//============================================================
//  SMC SETTINGS (hardcoded)
//============================================================
```

## [6] MARKET STRUCTURE LABEL SIZE

```
//============================================================
//  MARKET STRUCTURE LABEL SIZE
//============================================================
```

## [7] Swing-point labels are hidden by making their text transparent, not by s

```
// Swing-point labels are hidden by making their text transparent, not by skipping
// their creation. The label objects still exist and the engine's state is untouched,
// so structure tracking, fibs, OBs and the table behave identically either way.
```

## [8] (ORDER BLOCKS, VWAP and the Session Volume Profile / MV line were REMOVE

```
// (ORDER BLOCKS, VWAP and the Session Volume Profile / MV line were REMOVED
//  2026-07-25 — the script had gone over Pine's compiled-token cap again
//  (CE10117: 101484 > 100256) after the blocked-trade marker landed. All three
//  were purely cosmetic, defaulted OFF, and were read by NOTHING in the
//  execution layer — verified by grep: zero references after the STRATEGY
//  EXECUTION header. The B-LEG fork dropped the same three on 2026-07-24 for
//  the same reason. They live on in mpc_assistant.pine if the drawing is ever
//  wanted back.)
//============================================================
//  FAIR VALUE GAPS (FVG) INPUTS
//============================================================
```

## [9] Minimum gap size floor: a gap must be at least this % of price to count.

```
// Minimum gap size floor: a gap must be at least this % of price to count.
// No Auto-Threshold volatility scaling — a fixed floor, now user-tunable.
// FVG minimum-gap floor, SPLIT BY TIMEFRAME — ported from mpc_assistant.pine
// (its lines 149-151). This is why the assistant draws 5m gaps this file did not:
// a %-of-price floor does not scale down. 0.1% of gold at $3,300 is $3.30, wider
// than most WHOLE 5m bars, so one flat floor silently erased nearly every gap
// below 15m. 900 seconds = 15m.
// The 15m-and-above value stays 0.1 and is deliberately NOT the assistant's 0.04:
// at 15m this file's behaviour must not move — it is the A+ baseline and the
// mpc_sos_fade parity reference. ONLY sub-15m changes.
```

## [10] Middle-bar close-cleared test. mpc_assistant.pine has this OFF at every

```
// Middle-bar close-cleared test. mpc_assistant.pine has this OFF at every
// timeframe (fvgRequireClose = false); this file hardcoded it ON. Split the same
// way as the floor: forced off below 15m so low-timeframe gaps match the
// assistant, on at 15m+ so the A+ baseline and the Python parity pin
// (EngineConfig.fvg_require_close = True) are untouched.
```

## [11] A+ SETUP SEQUENCE INPUTS

```
//============================================================
//  A+ SETUP SEQUENCE INPUTS
//============================================================
// (5 dead A+ inputs removed 2026-07-21 — aplusDivOnly / aplusHtfWarn /
//  aplusHtfBlock / aplusReqInt / aplusIgnoreWindow were declared but never
//  read anywhere in this file. Deleted to buy compile tokens for the
//  post-SOS divergence veto exemption. Arming is controlled by the
//  execArmSweep / execArmDiv toggles in the Execution group instead.)
```

## [12] A+ DEBUG (bar-replay diagnostics — no effect on trades)

```
//============================================================
//  A+ DEBUG (bar-replay diagnostics — no effect on trades)
//============================================================
```

## [13] RSI DIVERGENCE INPUTS

```
//============================================================
//  RSI DIVERGENCE INPUTS
//============================================================
```

## [14] TRADING SESSIONS INPUTS

```
//============================================================
//  TRADING SESSIONS INPUTS
//============================================================
```

## [15] (Kill Zones & NY Range were REMOVED 2026-07-22 — the script had gone ove

```
// (Kill Zones & NY Range were REMOVED 2026-07-22 — the script had gone over
//  Pine's compiled-token cap (CE10117) and both were purely cosmetic, default
//  OFF, and read by nothing in the execution layer. They live on in
//  mpc_assistant.pine if the drawing is ever wanted back.)
```

## [16] LIQUIDITY LEVELS INPUTS

```
//============================================================
//  LIQUIDITY LEVELS INPUTS
//============================================================
```

## [17] INTERNAL FIB INPUTS

```
//============================================================
//  INTERNAL FIB INPUTS
//============================================================
```

## [18] FIBONACCI INPUTS

```
//============================================================
//  FIBONACCI INPUTS
//============================================================
```

## [19] MACRO / CYCLE FIB — DRAWING REMOVED 2026-08-02 (Aaron's call)

```
//============================================================
//  MACRO / CYCLE FIB — DRAWING REMOVED 2026-08-02 (Aaron's call)
//============================================================
// The whole "Cycle Fib" input group is gone: 27 inputs (the master toggle, line
// extension, the draw-up-to-timeframe cap, and a show / colour / style trio for
// each of the eight levels) plus the drawing block, its two style helpers, its
// eight line+label handles and the touched-flags that only ever coloured them.
// Cosmetic, defaulted OFF, and read by NOTHING in the execution layer — the same
// test the Kill Zones, VWAP, Order Blocks and SVP removals were made on.
//
// ⚠ THE TRACKING STAYS, AND MUST NOT BE REMOVED WITH IT. The cycle's anchors
// (macro_origin / macro_extreme, locked and extended further down) are the A+
// sequence's HTF POI: poiLongNow / poiShortNow are computed off them, and the
// B-LEG log line reports its premium/discount zone off them too. Only the
// DRAWING was deleted, so every value the strategy reads is byte-identical and
// no trade moves.
```

## [20] SNIPER FIB INPUTS

```
//============================================================
//  SNIPER FIB INPUTS
//============================================================
```

## [21] STRATEGY EXECUTION INPUTS

```
//============================================================
//  STRATEGY EXECUTION INPUTS
//============================================================
// EVERY Strategy Execution input is declared HERE, in one block, and NOWHERE
// else. That is deliberate and it is load-bearing:
//
//   1. ORDER IN THE PANEL IS ORDER OF DECLARATION IN THE FILE. Before 2026-07-28
//      two of these lived hundreds of lines away — execConfSZ next to the Sniper
//      engine that reads it, bLegMaxDays next to the B-leg staleness check — so
//      they landed at the TOP of the Execution panel, above "Trade longs", with
//      no context. Consolidating here is the only way to control the order.
//   2. Pine needs a declaration BEFORE its first read. The Sniper engine (~line
//      2900) and BLEG_MAX (~line 3430) both read inputs from this block, which is
//      why the whole block sits up here rather than beside the execution logic at
//      the bottom of the file. The execution block still OWNS the behaviour — it
//      just no longer owns the declarations.
//
// The block is ordered the way a trade actually happens: what trades → what arms
// it → where the limit rests → what can refuse it → size and stop → targets →
// runner → drawing. Read it top to bottom and you have followed one trade.
//
// A CHILD input is prefixed "↳" and carries `active = <its parent>`, so it greys
// out and locks the moment its parent makes it irrelevant. `active` needs a pure
// INPUT bool — never reassign one of these with ":=" or every `active` that
// references it stops compiling.
//
// Exceptions worth knowing, because they look like children and are not:
//   • "Runner trail step" has TWO masters (Fixed-step mode AND the "One trail
//     step behind" TP2 floor), so it is NOT gated on the trail method.
//   • The three FVG entry toggles still price an entry with "Require FVG" OFF —
//     that input only adds a fib fallback, it does not disable the gap logic.
//   • "Minimum stop distance" is an ENTRY filter, unrelated to the runner trail.
```

## [22] ── 3. WHERE THE LIMIT RESTS (entry price) ──────────────────────────────

```
// ── 3. WHERE THE LIMIT RESTS (entry price) ─────────────────────────────────
// These four are SIBLINGS, not a parent and three children. With "Require FVG"
// OFF a qualifying gap still prices the entry exactly as before — that toggle
// only adds the 0.618 fib as a FALLBACK when no gap qualifies. So none of the
// three gap rules below is greyed out by it; they all stay live either way.
// (execFvg50 — "Entry (least favorable): FVG must touch the 0.5 line" — REMOVED
//  2026-08-02, Aaron's call: never used. It was the bottom-tier fallback that let
//  a gap STRADDLING 0.5 rest its limit AT 0.5, and it defaulted OFF for its whole
//  life, so nothing historical moves. Recover from git if the shallowest entry
//  tier is ever wanted back — it was one input and one loop.)
```

## [23] ── 5. SIZE & STOP ──────────────────────────────────────────────────────

```
// ── 5. SIZE & STOP ─────────────────────────────────────────────────────────
// ⚠ An "SL follows entry depth" input (0.886 for shallow entries, 1.0 for deep
// ones) was added on 2026-08-02 and REMOVED the same day. It measured much worse
// live, and the repo's own Run 11 sweep says why: at a fixed 10% risk the whole
// book is 109.5R at 0.886 and 75.7R at 1.0. A wider stop with fib targets that do
// not move means every winner is worth fewer R while every loss is still −1R.
// Do not re-add it without re-reading that run.
// The entry band runs 0.5-0.886 and the stop is ALSO 0.886, so the band's own deep
// end contradicts the stop: an entry at 0.786 leaves a stop of 0.100 of the leg,
// and an entry AT 0.886 leaves ZERO. That is why 0.886 had to be excluded as a
// snap target — a workaround for the contradiction rather than a fix for it. This
// toggle fixes it: an entry AT OR PAST 0.786 drops its stop to the leg origin
// (1.0), which is the only level genuinely beyond the whole entry band. Entries
// SHALLOWER than 0.786 — 0.702 included — are untouched.
// ⚠ 0.786 IS THE BOUNDARY ON PURPOSE, AND IT HAS ALREADY BEEN WRONG TWICE.
// A version reverted on 2026-08-02 put 0.702 AND 0.786 in the wide-stop group and
// measured much worse; a first cut of this toggle used "deeper than 0.702", which
// swept up raw gap-edge entries around 0.75 as well. Aaron's call, both times:
// 0.702 against an 0.886 stop is still 0.184 of the leg, which is a real stop and
// worth 3.82R on the runner — widening it to 1.0 cuts that to 2.36R for nothing.
// Only 0.786-and-deeper is thin enough to be worth paying for. Sweep before moving.
// Minimum stop distance — refuse a setup whose stop lands so close to the entry
// that the position is degenerate. The $-risk is unchanged but SIZE balloons,
// ordinary noise takes you out, and price can travel PAST the stop inside the
// entry bar, so the realised loss beats the 1R you agreed to. Defaults OFF, so
// the shipped baseline is unchanged until you flip it.
// This is an ENTRY-TIME filter — it decides whether an order is placed at all. It
// has nothing to do with the runner trail further down, which only starts once
// TP2 is hit. Both work at once; neither disables the other.
```

## [24] ── 6. TARGETS (the TP ladder) ──────────────────────────────────────────

```
// ── 6. TARGETS (the TP ladder) ─────────────────────────────────────────────
// ⚠ A "shallow-entry TP2 level" input offering 0.236 instead of 0.0 was added on
// 2026-08-02 and REMOVED the same day — it measured worse. 0.236 is a NEARER
// target, and with the 0/0 rungs a nearer TP2 banks nothing sooner; it just hands
// the runner to the trail sooner, because touching TP2 is what installs the stop
// floor. Every tightening experiment in this strategy's history has cost 20-90%
// for that same reason. The runner is the edge. Shallow TP2 is fiboP7 (0.0).
```

## [25] ── 7. THE RUNNER — everything here starts only AFTER TP2 is hit ────────

```
// ── 7. THE RUNNER — everything here starts only AFTER TP2 is hit ───────────
// NOT a child of the trail method — it has TWO masters. 'Fixed step' trails off it,
// and the "One trail step behind" TP2 floor above measures off it too. Greying it
// on the trail method would silently disable a live setting, so it is never greyed.
```

## [26] ── 8. DRAWING (cosmetic — none of this changes a trade) ────────────────

```
// ── 8. DRAWING (cosmetic — none of this changes a trade) ───────────────────
// ── The no-FVG fallback's arm gate — DECLARED HERE ON PURPOSE, NOT beside execReqFVG ──────────
// TradingView keys a chart's saved input values off DECLARATION ORDER within each type, so
// inserting a string next to `execReqFVG` (the 7th of 37 strings in this file) would shift the
// thirty that follow and silently reset every one of them on a saved chart. This is the LAST
// input.string declared before the entry ladder that reads it (line ~4340), so it shifts exactly
// ONE later input — `execTimeStopMode` — and nothing else. Same reasoning as the time-stop pair
// at the bottom of this file, and it must not be "tidied" up beside its sibling.
// ⚠ After pasting this build, check the Time stop input still reads "Before TP1 only" / 36.
```

## [27] `marketStructureOnly` IS GONE, 2026-08-12, AND ITS REMOVAL IS A SAFETY F

```
//============================================================
//  `marketStructureOnly` IS GONE, 2026-08-12, AND ITS REMOVAL IS A SAFETY FIX
//  RATHER THAN A TIDY-UP. It force-disabled `showFibo` and `showFVG`, and those
//  two gate the blocks that COMPUTE fiboP1..fiboP7 and create the gap boxes —
//  i.e. every entry, stop and target price in this file. Ticking a checkbox
//  titled "Hide Everything Except Market Structure" therefore stopped the bot
//  trading, silently, with nothing anywhere reporting it. The three flags it
//  reached that decide trades are permanent calculation now (see their own
//  declarations); the drawing it used to hide is switched with `drawFibs` and
//  `showSessions`, which is all a display override could honestly have offered.
//============================================================
```

## [28] SMC STRUCTURE TYPE

```
//============================================================
//  SMC STRUCTURE TYPE
//============================================================
```

## [29] Neither an active pullback high nor a confirmed ASH was available to

```
                // Neither an active pullback high nor a confirmed ASH was available to
                // promote — use the actual highest point since the last confirmed low so
                // a genuine swing high still gets confirmed instead of silently vanishing.
```

## [30] TRADING SESSIONS TYPES & METHODS

```
//============================================================
//  TRADING SESSIONS TYPES & METHODS
//============================================================
```

## [31] SHARED CONSTANTS & SECURITY CALLS

```
//============================================================
//  SHARED CONSTANTS & SECURITY CALLS
//============================================================
```

## [32] ── HTF Directional Bias (adapted from LuxAlgo's HTF Bias Tracker) ──

```
// ── HTF Directional Bias (adapted from LuxAlgo's HTF Bias Tracker) ──
// Compares an "action" period's high/low/close against a "context" period's high/low
// to classify Bullish / Bearish / Neutral, with sweep detection.
```

## [33] Shared by Daily/Weekly/Monthly/Asia/London/NY liquidity levels: checks f

```
// Shared by Daily/Weekly/Monthly/Asia/London/NY liquidity levels: checks for
// mitigation, updates the line/label color+style+extent in place, and returns
// the (possibly updated) mitigated/mitigatedBar state.
```

## [34] Sessions: current week only by default (from Sunday 00:00 New York), or

```
// Sessions: current week only by default (from Sunday 00:00 New York), or
// unlimited history when Show All History is on. Anchored to the calendar week
// rather than a rolling 7 days, so mid-week it doesn't bleed into last week.
```

## [35] EXECUTION — EXTERNAL + INTERNAL STRUCTURE

```
//============================================================
//  EXECUTION — EXTERNAL + INTERNAL STRUCTURE
//============================================================
// External structure engine always runs — fib, macro fib, OBs all depend on it
```

## [36] Captures the latest confirmed internal swing point (price + location), s

```
// Captures the latest confirmed internal swing point (price + location), so the
// External Fib can adopt it as its anchor if it's more extreme than the external
// structure's own point — used only for the fib pull, nothing else.
```

## [37] ── Stop internal tracking on external SOS ───────────────

```
// ── Stop internal tracking on external SOS ───────────────
// True on any bar where the external structure breaks — the current internal
// swing is finished. Used further down to clear the table's INT row so it can
// never show an iBOS/iSOS whose drawing has already been wiped from the chart.
```

## [38] EQUAL HIGHS / LOWS (EQH / EQL) — liquidity pools

```
//============================================================
//  EQUAL HIGHS / LOWS (EQH / EQL) — liquidity pools
//============================================================
// Ported line-for-line from mpc_assistant.pine on 2026-08-01. Before that date NO
// strategy file had an EQ engine — not this one, not mpc_strategy.pine, not
// mpc_b_leg_strategy.pine, not either export. It was never a decision: the block
// landed in the assistant on 2026-07-17 (a0b8e1d) and simply never flowed back
// down the fork, the same drift that left the FVG floor and cap out of sync.
//
// EQH = two consecutive swing highs within a tolerance of each other = a stacked
// pool of buy-side liquidity resting just above; EQL is the mirror below. Drawn as
// a horizontal line from the FIRST pivot, extended right, until price CLOSES
// through it (the liquidity is taken).
//
// Detection is LOCKED to the assistant's constants — no panel inputs for pivot
// width, tolerance or cap — so the indicator and the strategy can never draw
// different levels. The canonical Python port is engines/equal_highs_lows/
// (Pine-parity green 2026-07-19). Do not build a second implementation.
//
// ⚠ THE EXEMPTION DEFAULTS OFF HERE, AND THE ASSISTANT HARDCODES IT ON. That is
// deliberate, and it is the only part of this block that can change a trade. With
// it on, a gap sitting on an EQ level survives the FVG cap and the directional
// filter — so WHICH gaps exist changes, so which entries fire changes. Two things
// would break silently if it shipped on: every historical result for this file,
// and Pine<->Python parity — the fair_value_gaps engine accepts eq_levels/eq_tol
// but backtest/replay/EngineStack does not wire them yet, and no cfg_ column
// carries this input into the export builds. Flip it for an experiment; do not
// trust a parity run taken with it on.
```

## [39] An unmitigated EQ level can outlive its pivot by thousands of bars, and 

```
// An unmitigated EQ level can outlive its pivot by thousands of bars, and Pine
// throws once a line's x1 ages past the drawing buffer — so the origin is clamped
// this far back. Same guard, same number, as the liquidity levels use.
```

## [40] ── EQ APPEARANCE, SYNCED FROM mpc_assistant.pine (Aaron, 2026-08-04) ──

```
            // ── EQ APPEARANCE, SYNCED FROM mpc_assistant.pine (Aaron, 2026-08-04) ──
            // DRAWING ONLY, and that boundary is the whole point of this edit: the
            // indicator's pass ALSO changed what an EQ level IS (a wick takes it, not a
            // close) and its three detection constants. None of that is here. Those move
            // trades through eqExemptFvg — they change which gaps exist, so they change
            // which entries fire — and Python still reads a close, so porting them would
            // put compare_strategy.py red. The two files stay forked on DETECTION and
            // agree on APPEARANCE.
            // SOLID, not dotted, and the line ENDS AT THE LIVE CANDLE rather than running
            // i_lineExtend bars past it. An EQ level is a pool, not a forecast: extending
            // it into empty space reads as a level that is still being offered.
```

## [41] style_label_left with an INVISIBLE box (color = na), not style_none.

```
            // style_label_left with an INVISIBLE box (color = na), not style_none.
            // style_none centres its text ON the anchor, so half the glyph sits above the
            // level and it reads as an offset tag floating over the line. style_label_left
            // anchors the label's LEFT edge at the point and centres the text vertically on
            // it — the tag starts exactly where the line ends and sits ON the level, which
            // is what "at the end of the line" means. The na box keeps the plain-text look.
```

## [42] FAIR VALUE GAPS — persist until mitigated

```
//============================================================
//  FAIR VALUE GAPS — persist until mitigated
//============================================================
// A bullish FVG is the void between candle A's high and candle C's low when the
// displacement candle B between them was strong enough that the two never overlap
// (low > high[2]). Bearish is the mirror.
// Lifecycle: gaps are NOT wiped on BOS/SOS — the impulse leg that breaks structure
// is exactly what leaves the gaps, and the retracement back into them is the fib
// entry confluence. A gap is deleted the moment price taps it; chart clutter
// is bounded by the Max Active FVGs cap (oldest dropped first). The optional
// directional filter hides (not deletes) gaps that oppose the current external
// structure direction, so they reappear if direction flips back.
```

## [43] ── Detection (confirmed bars only, so live wicks can't paint phantom gap

```
// ── Detection (confirmed bars only, so live wicks can't paint phantom gaps) ──
// The FVG is the 3-candle imbalance itself (LuxAlgo definition): bar A and bar C
// never overlap and the middle bar's close cleared the gap. No "clean impulse"
// body/colour rule — any 3 bars that leave a big-enough gap qualify.
// Threshold is the timeframe-split %-of-price floor (see fvgThreshPct above).
```

## [44] Cap: drop oldest gaps beyond the limit

```
    // Cap: drop oldest gaps beyond the limit
    // Cap: drop the oldest NON-EQ gap beyond the limit. With eqExemptFvg OFF (the
    // default here) the scan finds index 0 on its first test, so this is exactly
    // the old array.shift and nothing moves. With it ON, a gap sitting on an
    // EQH/EQL is skipped over and survives until it is actually mitigated.
    // ── THE CAP COUNTS NON-EQ GAPS ONLY (Aaron, 2026-08-03) ──
    // The exemption used to be a SWAP, not an addition, and that made it self-cancelling.
    // The cap was measured over EVERY gap while the drop scan skipped the exempt ones, so an
    // EQ-backed gap held a slot: keeping it evicted the newest ordinary gap in its place.
    // Measured on 40,000 real M15 bars, that is exactly what it did — the A+ bot lost 2 setups
    // and gained none, because the gaps it protected cost it the gaps it would have traded.
    // So `fvgMaxCount` now bounds the ORDINARY gaps only and an exempt gap rides ON TOP of
    // them. The count is what a reader already assumes it is: seven recent gaps, plus however
    // many are pinned by resting liquidity, each living until price mitigates it.
    // ⚠ The live total is therefore UNBOUNDED by this input — it is bounded by the EQ engine
    // instead (eqMax levels per side, each dying on a close through it). That is the intended
    // trade: the cap exists to stop clutter, and a gap backed by a live liquidity pool is the
    // opposite of clutter. Turn eqExemptFvg OFF to get the plain FIFO back.
```

## [45] Kill condition depends on the "keep until broken" toggle:

```
        // Kill condition depends on the "keep until broken" toggle:
        //   OFF (default) → tap-delete: dies the moment price touches the near edge.
        //   ON            → survives taps; dies only when a candle CLOSES fully past
        //                   the FAR edge (broken through the opposite side).
        // Skipped on the creation bar itself: a bullish gap's top IS that bar's
        // low, so without this guard every gap would self-delete instantly.
```

## [46] RSI DIVERGENCE — regular divergence at the extremes

```
//============================================================
//  RSI DIVERGENCE — regular divergence at the extremes
//============================================================
// Bullish: price prints a LOWER low while RSI prints a HIGHER low, with the RSI
// low coming from oversold. Bearish is the mirror from overbought. Pivots are
// confirmed divPivotLen bars after the extreme (non-repainting by design).
```

## [47] Live confluence flags for the A+ setup row

```
// Live confluence flags for the A+ setup row
// Divergence relevance is tied to structure, not just a bar count. A divergence
// that fired several legs ago — with BOS/SOS events since — is stale even if
// still within the bar window: price has already moved on, and citing it as a
// veto reason (e.g. an old bullish divergence from the bottom blocking a fresh
// short at a NEW top with its own current bearish divergence) is misleading.
// So a divergence stays live only until the NEXT external break after it fired,
// with the bar count as an outer safety cap on top of that.
```

## [48] DAILY LEVELS

```
//============================================================
//  DAILY LEVELS
//============================================================
```

## [49] WEEKLY LEVELS

```
//============================================================
//  WEEKLY LEVELS
//============================================================
```

## [50] PREVIOUS WEEKLY CLOSE (PWC)

```
//============================================================
//  PREVIOUS WEEKLY CLOSE (PWC)
//============================================================
```

## [51] H4 LIQUIDITY SWEEP TRACKER

```
//============================================================
//  H4 LIQUIDITY SWEEP TRACKER
//============================================================
```

## [52] SESSION H/L TRACKING

```
//============================================================
//  SESSION H/L TRACKING
//============================================================
```

## [53] LABEL COLLISION DETECTION

```
//============================================================
//  LABEL COLLISION DETECTION
//============================================================
// Wrapped in a function (gate included) so the main body pays for one statement
// rather than ~35 — see the CE10295 note on f_drawTable.
```

## [54] ── A LABEL NOBODY CAN SEE MAY NOT RESERVE A SLOT ─────────────────────

```
        // ── A LABEL NOBODY CAN SEE MAY NOT RESERVE A SLOT ─────────────────────
        // The nudge below walks the labels bottom-up and pushes each one at least
        // lblOff above the one under it. A MITIGATED daily/weekly/session level is
        // hidden (f_liqMitigate blanks its textcolor) but its label OBJECT still
        // exists — so it was still being pushed into this list, still taking a slot,
        // and still shoving every visible label above it up by a full lblOff with
        // nothing on screen to explain the gap. That is why one tag sits further
        // from its line than its neighbours, and why H4 H and H4 L — which are never
        // hidden, only greyed — could end up at different distances from their own
        // lines: a hidden Asia/Ldn level under one of them and not the other.
        // ⚠ H4 and PWC are deliberately NOT filtered: a swept H4 stays on the chart
        // in grey, so it is visible and genuinely does need its space.
        // ── PDH / PDL WIN A TIE ─────────────────────────────────────────────
        // A session high sitting at the SAME price as the previous day's high is
        // ONE level, and printing both stacks "NY L" under "PDL" for a line only
        // one of them needs to name. The daily label is the one kept — it is the
        // bigger, older pool — and the session label is hidden the same way a
        // mitigated level is hidden (textcolor na), then left OUT of the nudge
        // below, so the collision pass does not space the survivors around an
        // invisible label.
        // ⚠ The tolerance is ONE TICK, not a visual gap. Both numbers are maxima
        // over the same bar highs, so a genuine duplicate is EXACT; a level a few
        // ticks away is a DIFFERENT level and the nudge already handles it.
        // ⚠ It reads d_hLbl / d_lLbl and not just the prices: once a mitigated
        // PDH has been deleted on a new day there is nothing left to defer to,
        // and the session label has to come back.
```

## [55] ⚠ And it defers only to a VISIBLE daily label. A mitigated PDH is

```
        // ⚠ And it defers only to a VISIBLE daily label. A mitigated PDH is
        // hidden but its label object lives until the next new-day wipe, so
        // without this term a swept, invisible PDH went on suppressing a
        // perfectly visible session tag at the same price — the level lost
        // its name with nothing on screen holding the place.
```

## [56] prevY is advanced BEFORE the set_y call so the loop's last statement is

```
            // prevY is advanced BEFORE the set_y call so the loop's last statement is
            // the void set_y, not a float assignment. Both branches of this if must
            // agree on type, because the if is the function's return expression
            // (CE10235) — as a main-body statement it never had to.
```

## [57] FIBONACCI DRAWING

```
//============================================================
//  FIBONACCI DRAWING
//============================================================
```

## [58] Inbound touch of the 0.5 level during the RETRACEMENT toward the entry z

```
// Inbound touch of the 0.5 level during the RETRACEMENT toward the entry zone —
// the A+ sequence's EARLY entry tier. Distinct from fibo2Touched, which tests the
// same price on the way back OUT (as TP1) and is gated behind 0.618.
```

## [59] The BAR price first tagged 0.5 on this leg — i.e. the bar price entered 

```
// The BAR price first tagged 0.5 on this leg — i.e. the bar price entered the entry
// zone. Read only by execFvgPreZone, to decide whether a gap pre-dates the retrace or
// was printed by it. Latched once and reset with the leg (see fiboOriginChanged below),
// so it is scoped to exactly the fib whose 0.5-0.886 band the gap is judged against.
```

## [60] Skip ALL touched checks on the same bar the origin changed, OR the same 

```
    // Skip ALL touched checks on the same bar the origin changed, OR the same bar
    // the extending anchor (fibo_ash/fibo_asl) itself moved — that anchor tracks
    // live wicks during a pullback watch, not confirmed closes, so without this
    // guard a fresh wick-high can retroactively satisfy the very TP3 level it
    // just created, hiding the fib with no real BOS/SOS behind it.
```

## [61] Gate: coloring only activates once 0.618 is reached.

```
        // Gate: coloring only activates once 0.618 is reached.
        // fibo618EverReached is only set TRUE at the END of this block (after all checks run),
        // so TP level checks never fire on the same bar that 0.618 was first hit.
```

## [62] macro_dir tracks the OVERALL trend direction we are currently in.

```
// macro_dir tracks the OVERALL trend direction we are currently in.
//   1  = overall trend is up (we are accumulating the highest high of the whole up-cycle)
//  -1  = overall trend is down (we are accumulating the lowest low of the whole down-cycle)
// The origin (opposite anchor) is fixed only when the trend actually reverses (st.dir flips),
// not on every internal BOS/SOS within the same direction. This lets the fib span multiple
// BOS legs that all belong to the same larger move (e.g. wave 1->2->3 as one up-cycle).
```

## [63] (The eight line/label handles, the eight touched-flags, macro_prev_extre

```
// (The eight line/label handles, the eight touched-flags, macro_prev_extreme and
//  macro_prev_st_dir were REMOVED 2026-08-02 with the Cycle Fib drawing — every
//  one of them existed only to draw or colour a line. macro_origin/_extreme and
//  their _loc bars stay: the A+ HTF POI reads them.)
```

## [64] ── EXACT RULE (per latest instructions) ──

```
// ── EXACT RULE (per latest instructions) ──
// BOTTOM anchor (extreme LL):
//   - Locks the instant st.asl is confirmed as a genuine LL (st.new_swing_low fires and the
//     confirmed low is lower than the prior confirmed low).
//   - Once locked, it NEVER moves again for this cycle -- not even if a deeper low occurs
//     later while the top is still extending.
//   - The ONLY way the bottom changes is if an even deeper confirmed LL prints later --
//     that starts a BRAND NEW cycle (the old fib's top lock is discarded, a new bottom locks
//     on the fresh LL, and the top starts over unlocked).
//
// TOP anchor (extreme HH):
//   - Locks the first time a bearish SOS (st.bear_sos) fires alongside a confirmed HH
//     (st.ash, confirmed via st.new_swing_high, higher than the prior confirmed high).
//   - After that initial lock, it is allowed to extend FURTHER only when a subsequent
//     bullish BOS (st.bull_bos) confirms an even higher high -- i.e. price comes back up,
//     breaks structure again, and makes a new HH beyond the locked one.
//   - It does NOT track every new high live -- only on these specific qualifying events.
```

## [65] Cycle Fib TRACKING always runs, on every timeframe — its discount zone I

```
// Cycle Fib TRACKING always runs, on every timeframe — its discount zone IS the
// HTF POI the A+ sequence reads. The drawing that used to sit alongside it (and
// the timeframe cap that gated it) was removed 2026-08-02; this block is what
// survived, and it is load-bearing.
```

## [66] ── Track the most recent bearish SOS and start tracking the low from tha

```
    // ── Track the most recent bearish SOS and start tracking the low from that point ──
    // Seeded once from the very first bar (fallback) so the first bullish SOS can
    // lock immediately instead of waiting for a prior bearish SOS to seed the tracker.
```

## [67] ── While waiting for a bullish SOS, keep updating the lowest low since b

```
    // ── While waiting for a bullish SOS, keep updating the lowest low since bear SOS ──
    // This gives us the true cycle low — the deepest point made after the bearish reversal,
    // not the structure engine's historical scan which can reach far into the past.
```

## [68] (The "HIDE when price closes back above the locked top" block went with 

```
// (The "HIDE when price closes back above the locked top" block went with the
//  drawing on 2026-08-02, and macro_visible with it. It only ever hid LINES — it
//  was never read by the A+ POI or the B-LEG context line, both of which gate on
//  macro_origin_locked alone, so nothing the strategy reads changes.)
```

## [69] INTERNAL FIB

```
//============================================================
//  INTERNAL FIB
//============================================================
```

## [70] Direction aware levels

```
        // Direction aware levels
        // Bullish: 0=top(iH), 1=bottom(iL), levels go DOWN from top
        // Bearish: 0=bottom(iL), 1=top(iH), levels go UP from bottom
```

## [71] SNIPER FIB

```
//============================================================
//  SNIPER FIB
//============================================================
// The zone must be TRACKED whenever it can confirm a trade, even if its drawing
// is switched off — otherwise sniperZoneTop/Bot stay na and the confirmation
// silently never fires. Drawing stays gated on showSniperFib alone.
```

## [72] PLOTTING

```
//============================================================
//  PLOTTING
//============================================================
```

## [73] MPC - JARVIS CONFIRMATION TABLE

```
//============================================================
//  MPC - JARVIS CONFIRMATION TABLE
//============================================================
// RESTORED 2026-08-02 (Aaron's call — he reads it during bar replay). It was cut
// 2026-07-24 for compile tokens (CE10117); the 28 unused toggles and the Cycle Fib
// drawing removed earlier today freed ~207 lines, which is where the budget for it
// came from. Recovered from `b25789d~1`, NOT rewritten from memory — this is the A+
// file's OWN table, not the near-identical fork that survives in
// `mpc_b_leg_strategy.pine`, so its rows describe A+ state exactly as they used to.
// ⚠ COSMETIC ONLY: every line below READS state and writes none of it back, so no
// fill, exit or stat can move. The one thing that is NOT free is compile budget — if
// CE10117 returns, this block is the first thing to cut again.
// ── PALETTE REFRESH (Aaron, 2026-08-04) — synced from mpc_assistant.pine ──
// The company blue and yellow stay; everything around them was re-picked so the table
// reads as one panel instead of a grid of coloured text. Three changes carry it:
//   1. The BODY is a softened charcoal (#0B0E14) rather than near-black, and the HEADER
//      is the only true black on the table — so the header separates by itself and the
//      frame no longer has to do it with a heavy yellow border.
//   2. The FRAME is the blue at 70%, one pixel, matching the internal borders. The old
//      2px yellow frame outranked the header text it was drawing attention to.
//   3. The INFO column is a muted slate (#94A3B8) rather than white-at-40%. A transparent
//      white takes its tint from whatever is behind it; a solid grey does not, so the
//      third column now reads the same over the chart as over the table's own fill.
// The bull/bear pair moved to the brighter modern pair because they now sit on a TINTED
// cell rather than on flat charcoal — see f_jRow4 for that.
```

## [74] The header's own blue — a bright cyan, and the ONLY place it appears. It

```
// The header's own blue — a bright cyan, and the ONLY place it appears. It is what
// separates the branding cell from the two yellow column headings beside it, now that
// they no longer sit in a coloured band.
```

## [75] The LIQ BSL row's own red — a hotter one than the bearish red, deliberat

```
// The LIQ BSL row's own red — a hotter one than the bearish red, deliberately. A swept
// pool is an EVENT that just happened, not a running bias like the Weekly/Daily rows, so
// it should not sit at the same visual weight as two rows that are describing trend.
```

## [76] ── 2. STRUCTURE slots — most recent external and internal ──

```
// ── 2. STRUCTURE slots — most recent external and internal ──
// RESTORED 2026-08-02 with the table. The SNIPER-ZONE slot was NOT restored: the
// table never read `sz_status` / `sniperZoneActive`, so it was dead weight even
// before the cut.
```

## [77] An external break ends the current internal swing and (unless historic i

```
// An external break ends the current internal swing and (unless historic internals
// are enabled) wipes its drawings from the chart. Clear the table's INT state on the
// same bar so the row can never show an iBOS/iSOS that has no drawing behind it.
```

## [78] Valid whenever a live internal break exists for the CURRENT external swi

```
// Valid whenever a live internal break exists for the CURRENT external swing.
// (The external-break clear above is what scopes it — no fib-origin comparison
// needed, since fiboStartIndex tracks the swing anchor, not the break bar, and
// could sit far enough back to let a stale internal break slip through.)
```

## [79] ── Draw table ──

```
// ── Draw table ──
// FOUR columns now — GROUP · row · STATUS · INFO (Aaron, 2026-08-04, synced from
// mpc_assistant.pine). The first column is a spanning tag (SETUP / BIAS / LIQ / STR)
// printed ONCE on the group's first row and blank on the rest, so the rows read as four
// bands rather than one long list.
// THE GRID STAYS ON. It was briefly borderless in the indicator on the reasoning that a
// blank group cell reads as its own box, so the tag could visually own the rows beneath
// it. True, and not what was wanted — the grid is what makes this readable as a TABLE.
// The grouping comes from the TAG ALONE; a blank cell in a bordered grid still groups, it
// just reads as an indent rather than a merged band. Borders are the blue at 70%, the
// same colour as the frame, so the grid separates without competing with the tinted
// status cells.
```

## [80] ── THE STATUS CELL IS TINTED WITH ITS OWN COLOUR (Aaron, 2026-08-04) ──

```
// ── THE STATUS CELL IS TINTED WITH ITS OWN COLOUR (Aaron, 2026-08-04) ──
// The middle column used to be coloured TEXT on the same flat fill as everything else, so
// a row's state had to be read off the words. It now sits on a wash of its own colour and
// the state is visible before a single word is.
// ONE RULE — `color.new(vc, 87)` — rather than a status→background lookup, and that is a
// deliberate departure from the reference table this came off. The reference keys its
// tint off the status TEXT, and this table's statuses are not a fixed vocabulary: they
// are "▲ READY LONG", "▲ AWAIT FVG SHORT", "EXTREME", "2/3 LONG", "Pass", "Swept". A
// lookup would need extending every time a row gains a state, and the one it missed would
// silently render untinted — the same class of "a label nobody is checking" this repo
// keeps meeting. Deriving from the colour the row already decided cannot fall out of step.
// `grp` is the GROUP tag and is passed EMPTY on every row but the first of its group.
// It cannot be latched inside this function — Pine lets a function read a global but
// never write one (CE10088, the error `ob_export.pine` hit on 2026-07-31) — so the caller
// owns the once-only rule. A+ SETUP and Weekly can hardcode theirs because they always
// print; LIQ and the EXT/INT pair need a real latch, since either of their two rows can
// be the one that appears. See the `gLiq` / `gMs` locals there.
```

## [81] A+ SETUP SEQUENCE — sweep → SOS → fib entry, IN ORDER

```
//============================================================
//  A+ SETUP SEQUENCE — sweep → SOS → fib entry, IN ORDER
//============================================================
// The A+ model is a sequence, not a checklist. Each stage only counts if the
// previous one is already done:
//   1. SWEEP — liquidity taken at a tracked HTF pool (H4 / PD / session H-L).
//      Those levels ARE the points of interest, so a sweep firing means price
//      both reached the POI and grabbed the resting stops there.
//   2. MSS — an external SOS that fires AFTER the sweep, within the window.
//   3. ENTRY — the SOS leg's fib retracement:
//        0.5 tapped   -> A+ EARLY  (early entry tier)
//        0.618 reached -> A+ READY (full entry zone, E1-E3)
//      A live clean FVG overlapping the entry zone is flagged as confluence.
// The sequence dies on: opposite SOS, close past the fib 1.0 (leg invalidated),
// or TP3 hit (cycle complete). It then waits for the next sweep.
```

## [82] Debug only — remembers WHICH source currently holds the Stage-1 slot on 

```
// Debug only — remembers WHICH source currently holds the Stage-1 slot on each
// side, so the 2-of-3 debug marker can label the arm correctly. Read-only
// bookkeeping; nothing here feeds the engine or trade logic.
```

## [83] One missed-setup callout = ONE SMALL ORANGE TAG. Single static colour

```
// One missed-setup callout = ONE SMALL ORANGE TAG. Single static colour
// throughout — the tag, the leader lines and the would-be-entry line all match,
// so nothing on it has to be decoded.
//
// The chart shows ONE LINE ("▲ 2/3"). The full MET / MISSING breakdown, the
// blocker and the would-be entry price live in the label's TOOLTIP — hover it.
// This is the difference between a readable chart and a wall of paragraphs: no
// information is lost, it is just one mouse-over away (and the Pine Log still
// carries the same text verbatim for a full off-chart audit).
//
// Leader lines run from the tag out to the exact bar each achieved stage
// happened on. The dashed horizontal line marks the price the entry limit would
// have rested at — its price is in the tooltip rather than a second label.
// The tag is placed well clear of the candles by the caller, and consecutive
// tags are staggered vertically so two near each other never overlap.
```

## [84] ── MISSED-SETUP watch state ────────────────────────────────────────────

```
// ── MISSED-SETUP watch state ─────────────────────────────────────────────────
// Everything one side needs to remember about a live setup, held as a single
// OBJECT rather than thirteen loose `var`s. Pine objects are passed by reference,
// so the two functions below can mutate this state from inside a function — which
// is the whole point: the tracking and the callout together are ~90 statements,
// and the main body has a hard cap on how many it may hold (CE10295). Same
// pattern as PosBox / TradeLbl further down.
```

## [85] Track the live setup, then draw the callout when it dies without trading

```
// Track the live setup, then draw the callout when it dies without trading.
// Returns the log line (empty string when nothing was reported), so the chart box
// and the Pine Log can never tell different stories — they are built from one
// string. Every gate is a PARAMETER, not a global read, so what counts as a
// confluence is decided by the caller from the live strategy inputs.
```

## [86] A NEAR miss is one worth looking at: it either met all three and still

```
            // A NEAR miss is one worth looking at: it either met all three and still
            // did not fill, or it got price into the zone and failed only on the FVG.
            // "Price never retraced" is the ordinary outcome of most setups and is
            // what floods the chart, so the default view leaves it out.
```

## [87] Stagger: every third callout on this side sits back at the base

```
                // Stagger: every third callout on this side sits back at the base
                // height, so two that land near each other never print on top of
                // one another even after the vertical clearance is applied.
```

## [88] HTF POI — the Cycle Fib's zones, tracked on every timeframe (drawing sta

```
// HTF POI — the Cycle Fib's zones, tracked on every timeframe (drawing stays gated):
// longs care about the DISCOUNT (0.618-0.886 of the cycle), shorts about the
// PREMIUM (0.382 up to the extreme). Latched while a sweep is armed, so a deeper
// tag of the zone after the sweep still counts.
```

## [89] Stage 1 — arm on the EXACT bar a NEW sweep or NEW divergence fires (true

```
// Stage 1 — arm on the EXACT bar a NEW sweep or NEW divergence fires (true edge
// triggers, not "is this condition currently true"). recentSSL_bar/recentBSL_bar
// are recomputed fresh each bar from the liquidity sources and only CHANGE VALUE
// on the bar a genuinely more recent sweep becomes the newest one; lastBullDivBar/
// lastBearDivBar likewise only change on the bar a new divergence confirms. Edge-
// triggering this way means there is no stale state to accidentally re-arm from —
// the event has to newly happen, not merely still be "active".
// Session-gap detector — first bar after a market close (e.g. daily 17:00-18:00)
// has a time jump much larger than the normal bar spacing.
```

## [90] Daily-level sweeps go stale after one day — a "Day Low" sweep from 3 day

```
// Daily-level sweeps go stale after one day — a "Day Low" sweep from 3 days ago
// is no longer meaningful fuel for a fresh setup. Only the PREVIOUS day's sweep
// (or newer) counts; H4/session sweeps are inherently short-lived already and
// aren't capped here.
```

## [91] A SWEEP arms only when nothing is already tracking on this side — a rota

```
// A SWEEP arms only when nothing is already tracking on this side — a rotating
// liquidity source (e.g. the daily flipping from Day-Low-swept to Day-High-swept
// at the session boundary) changes recentSSL_bar constantly, and must not
// re-trigger or refresh a live arm.
//
// A DIVERGENCE is different: it may take over a slot a sweep is merely HOLDING at
// stage 1, refreshing the clock to its own timestamp. Without this, a sweep squats
// on the slot doing nothing, the divergence behind it is discarded, and Stage 2
// below then measures its window against the stale SWEEP time — so a live
// divergence never reaches stage 2 and never trades. The one thing a divergence
// may NOT disturb is a LOCKED setup (stage 2, SOS already in), hence sosBar only.
```

## [92] Retro-link — a divergence pivot only CONFIRMS divPivotLen bars after the

```
// Retro-link — a divergence pivot only CONFIRMS divPivotLen bars after the low it
// marks. On a fast V-reversal the SOS fires inside that lag, so by the time the
// divergence arms Stage 1 the SOS has already come and gone and the forward-only
// Stage 2 check below never sees it — the setup sticks at 1/3 forever. If the last
// bull SOS landed at or after the divergence's pivot bar (so the sequence really
// did run div -> SOS) and is still inside the staleness window, adopt it.
// Named (unlike the assistant's, which can be an inline `if`) because the
// execution layer's arm-source snapshot has to know a retro-link happened.
```

## [93] Clear a stale arm — sweep/div fired but no SOS followed within the windo

```
// Clear a stale arm — sweep/div fired but no SOS followed within the window.
// Without this, aplusL_sweepBar stays set FOREVER even after the A+ row has
// already fallen back to "Pass" (the display checks the window; this variable
// didn't), which permanently blocked CONT from ever arming again.
// Skipped on a session-gap bar: `time` jumps by far more than the normal bar
// spacing there and the daily security bar rolls, which was falsely tripping
// this clear and resetting live arms across the 17:00-18:00 close.
```

## [94] A+ leg resolution: completion (TP3), invalidation (close past 1.0 or fib

```
// A+ leg resolution: completion (TP3), invalidation (close past 1.0 or fib
// flipped), or a CONTINUATION BOS once the SOS stage was already reached. That
// last case is the one you're describing: the SOS fires, price never completes
// the retrace, and instead breaks structure again in the same direction — the
// leg has moved on without ever giving the fib entry, so the A+'s premise is
// over and the leg is dropped. Critically this must exclude the SOS's
// OWN bar: your structure engine flags bull_bos = true on every bull_sos bar
// too (they're not mutually exclusive), so without "not st.bull_sos" here, the
// very bar that arms stage 2 would immediately kill itself.
// B LEG capture — read HERE, BEFORE the death block clears aplus*_sosBar/latches.
// The EXACT case the B LEG owns: the REV is about to die on a continuation BOS
// while still at 2/3 (no retrace — neither the 0.5 nor the 0.618 latch is set).
// A death for any OTHER reason (TP3 done, fib flipped, 1.0 broken) is a real
// failure and does NOT arm a B leg.
```

## [95] B LEG SETUP — the SOS whose retrace arrived late

```
//============================================================
//  B LEG SETUP — the SOS whose retrace arrived late
//============================================================
// Ported from mpc_assistant.pine (tracker only — no chart box; the strategy's
// own trade drawing visualises the fill). An SOS fires, price expands and prints
// a continuation BOS BEFORE it ever retraces, so the REV leg above just died at
// 2/3 ("no retracement"). On a higher timeframe that is ONE clean leg and the
// retrace DOES arrive, later — into the Sniper-Zone band (0.382-0.5) frozen at
// the ORIGINAL SOS. The B leg freezes that band and waits for price to trade
// back into it. Runs fully PARALLEL to the A+ engine: it only READS st.* and the
// bLegArm flags captured above, and never writes A+ state.
```

## [96] Freeze the SZ band on every SOS — the SAME 0.382/0.5 maths the drawn Sni

```
// Freeze the SZ band on every SOS — the SAME 0.382/0.5 maths the drawn Sniper
// Zone uses. inv = the leg origin (fib 1.0): a close past it means the reversal
// failed outright. DEEPEST BAND WINS: a fresh same-side SOS while a leg is live
// and UNTAPPED keeps whichever band is FARTHER from price (the deeper retrace
// target), migrating the watch rather than resetting it; the target (expansion
// extreme = TP reference) is extended, never rewound. A TAPPED leg never blocks
// a replacement.
```

## [97] Death: a close past the leg origin (1.0), or the staleness cap. NO SOS i

```
// Death: a close past the leg origin (1.0), or the staleness cap. NO SOS in
// either direction kills an untapped leg (a same-side one only MIGRATES the band
// above; the opposite one is often the retrace itself).
// Staleness is user-tunable in DAYS (1-3) but converted to a BAR count (day ÷ the
// chart timeframe), so weekends and the daily close still don't burn the clock —
// what matters is how much TRADING has passed. On 15m: 1 day ≈ 96 bars, 2 ≈ 192,
// 3 ≈ 288. The `bLegMaxDays` INPUT moved to the consolidated Strategy Execution
// block near the top of the file on 2026-07-28 (it used to be declared right here,
// which put it at the top of the Execution panel above "Trade longs"); only the
// bar-count conversion is left here, next to the check that reads it.
```

## [98] (CONT — the continuation trade type — was removed from this file 2026-07

```
// (CONT — the continuation trade type — was removed from this file 2026-07-21.
//  It was display-only here: nothing in the execution layer ever read
//  contL_bosBar / contS_bosBar / contL_stage / contS_stage, so deleting it
//  changes no trade, fill or stat. Removed to free compile tokens.)
```

## [99] Stage 3 — entry zone progress on the SOS leg's fib

```
// Stage 3 — entry zone progress on the SOS leg's fib
// EARLY = 0.5 tapped inbound, READY = 0.618 reached (E1-E3 zone live)
// Latch the A+'s own 0.5/0.618 progress while its SOS is live. These persist
// through a fib-origin redraw (which happens at the session gap and would
// otherwise reset the global fiboHalfReached/618 flags, dropping EARLY→2/3).
```

## [100] ── A+ veto, SOS-aware ──────────────────────────────────────────────────

```
// ── A+ veto, SOS-aware ────────────────────────────────────────────────────
// A divergence that prints AFTER the SOS does NOT veto its own setup. Once
// stage 2 is live the setup is deliberately waiting on a retrace, and an
// opposing divergence formed during that retrace is the pullback itself —
// weakness in the counter-move, not a reversal of the leg we just broke with.
// (Real case: bullish SOS, bear div fires on the pull back into the fib band,
// entry blocked.) Only a divergence already live at or before the SOS bar
// still blocks the side; before stage 2 (no SOS yet) nothing changes.
// Extreme RSI keeps blocking LIVE — this exemption covers divergence only.
```

## [101] ── MISSED-SETUP watch — opened the moment a setup confirms Arm + SOS, an

```
// ── MISSED-SETUP watch — opened the moment a setup confirms Arm + SOS, and held
// open until that setup either BECOMES A TRADE or DIES. It is deliberately NOT
// closed when price reaches the retrace zone any more. That was the old bug:
// stage 3 was treated as success, so a setup that got all the way to the zone and
// then failed to enter (no live FVG to rest a limit on, a veto, the final hour,
// a leg that died before the limit was touched) vanished off the chart with no
// explanation at all. Reaching the zone is only half of confluence #3 — having
// something to enter from is the other half.
//
// Snapshot the arm/SOS bars here because the engine clears aplus*_sweepBar /
// aplus*_sosBar the instant the sequence dies, so by the time we detect the death
// it is too late to ask it where those bars were. The arm SOURCE and the sweep's
// name are snapshotted too, so the callout can name the exact confluence.
// Armed on the first bar the stage reaches 2 OR HIGHER — a fast leg can print the
// SOS and tag the 0.5 on the same bar, jumping straight from stage 1 to stage 3,
// and an "== 2" test would silently never open the watch for it.
```

## [102] ── execFvgPreZone — did this gap exist BEFORE price entered the zone? ──

```
// ── execFvgPreZone — did this gap exist BEFORE price entered the zone? ───────
// A gap is only confluence if it was already sitting in the band when price arrived.
// One printed by the reversal candle AFTER price is already inside the 0.5-0.886 band
// is the retrace confirming itself, and it re-prices the resting limit to a level the
// setup never justified. `na(fiboHalfBar)` = price has not reached the zone yet, so
// every gap trivially pre-dates it and the gate is inert. STRICTLY earlier: a gap born
// on the zone-entry bar was still forming as price arrived, so it was not "present".
// Read by BOTH gap consumers below — the confluence flag and the entry-edge loop — so a
// gap the entry may not use can never be labelled as the confluence that armed it. Add
// the call to any future consumer of fvgTops/fvgBots, or that path becomes a way around
// this gate. (The old execFvg50 0.5-straddle fallback was a third consumer; it was
// removed with the input on 2026-08-02.)
```

## [103] The whole render lives in a function, including its own barstate gate, s

```
// The whole render lives in a function, including its own barstate gate, so the
// main body pays for exactly ONE statement instead of ~60. Pine caps how many
// statements the main body may hold (CE10295: "The main body of the script is
// too long"), and this table is by far the largest block in it. Same trick as
// f_drawStats / f_posBox below. Everything it reads is a global declared above.
```

## [104] Header

```
        // Header
        // "JARVIS", not "MPC- JARVIS" — the long form was the widest string in this
        // column, so the branding was setting the width of every group tag under it. The
        // watermark still carries the full name.
        // SOURCE → INFO (Aaron, 2026-08-04). "Source" was accurate for the LIQ pair and
        // the two bias rows, where the column really does name where the read came from,
        // but it was never what the column held on the A+ SETUP row, which carries the
        // confluence tags. "Info" is the honest name for a column that is whatever that
        // row still needs to tell you.
        // The branding sits over the GROUP column and column 1's header is deliberately
        // EMPTY — the row labels under it (A+, W, D, BSL, EXT) are named by their group
        // tag, so a heading there would be inventing a word for a column that does not
        // need one. JARVIS is the one cyan on the table; STATUS and INFO stay yellow,
        // which is what tells the reader the branding is not a column heading.
```

## [105] Was gated on `marketStructureOnly`, deleted 2026-08-12 — these rows are

```
        // Was gated on `marketStructureOnly`, deleted 2026-08-12 — these rows are
        // the point of the table, and the flag that hid them also stopped the bot
        // trading. `true` keeps the block's indentation and its `r` counter intact.
```

## [106] A+ SETUP — the reversal sequence ONLY (sweep → SOS → entry). Once TP3

```
            // A+ SETUP — the reversal sequence ONLY (sweep → SOS → entry). Once TP3
            // completes, this row goes back to Pass; what tracks afterward is the CONT
            // row below — a different trade type, displayed separately so the two can
            // never be confused. Divergence/extreme-RSI veto: a side with live opposing
            // divergence or an extreme RSI reading is suppressed and flagged instead of
            // displayed as a tradeable setup, even if the entry zone is reached.
            // FVG is a REQUIRED confirmation for READY (not just a tag) — reaching 0.618
            // without a live matching FVG holds the row at "awaiting FVG" instead of
            // declaring the setup ready. POI (Cycle Fib discount/premium) is a separate,
            // optional confirmation — it does not substitute for the FVG requirement.
```

## [107] WEEKLY — Established Context (last closed week vs the one before). Opens

```
            // WEEKLY — Established Context (last closed week vs the one before). Opens the
            // BIAS group, and it is unconditional, so the tag is hardcoded rather than
            // latched.
```

## [108] LIQ — EITHER row can be the one that prints, so the group tag is a real

```
            // LIQ — EITHER row can be the one that prints, so the group tag is a real
            // latch rather than a hardcode: it rides on whichever appears first and is
            // blanked after.
            // ⚠ The STATUS column says "Swept", not "BSL"/"SSL". Those words moved to the
            // row label, and leaving them in both places printed `LIQ | BSL | BSL | Day
            // High` — the same word twice with no second meaning. The status column's job
            // is what HAPPENED, and what happened is the pool was taken; WHICH pool is the
            // row label and WHERE it was is the Info column. Nothing is lost, and the
            // colour still carries the side.
```

## [109] Wipe any leftover cells below the last drawn row. Without this, a tick

```
        // Wipe any leftover cells below the last drawn row. Without this, a tick
        // that draws FEWER rows than the previous one leaves the old rows visible
        // (e.g. a ghost duplicate of the final row after a row above disappears).
        // 3, not 2 — the wipe must reach the new fourth column, or a shrinking table
        // leaves a ghost Info cell hanging off the bottom right with no row beside it.
```

## [110] MPC- JARVIS WATERMARK

```
//============================================================
//  MPC- JARVIS WATERMARK
//============================================================
```

## [111] STRATEGY EXECUTION — A+ sequence entries + scaled fib-target exits

```
//============================================================
//  STRATEGY EXECUTION — A+ sequence entries + scaled fib-target exits
//============================================================
// This is the ONLY block that is not part of the mpc_assistant.pine engine.
// It reads the A+ state the engine already computes and turns it into orders.
//
// ENTRY (per your spec): the setup must be armed all the way to the SOS
// (aplus*_sosBar set = sweep-or-div THEN shift of structure), the fib must
// point the same way (fibo_dir), price must be trading inside the 0.5-0.886
// retrace band, and a live FVG must overlap that band (aplus*_fvg). The RSI
// divergence/extreme veto (longVetoA/shortVetoA) blocks the side when active —
// but a divergence that printed AFTER the SOS does not veto its own setup
// (that's the retrace, not a reversal); extreme RSI still blocks live.
//
// The Stage-1 trigger is SPLIT by two toggles — "Arm on liquidity sweep" and
// "Arm on RSI divergence" — so the same stack can be backtested with either
// trigger in isolation. See the arm-source filter further down. Both on = the
// original sweep-OR-divergence behaviour; both off = no trades.
//
// EXITS: SL just beyond fib 1.0 (the leg origin — the same level the engine
// uses to invalidate the leg). The target ladder DEPENDS ON HOW DEEP THE ENTRY
// FILLED, because TP1 may never sit on (or above) the entry price:
//
//   SHALLOW entry — the limit rested at the 0.5 clamp (edge above the 0.618 fib):
//       TP1 = 0.382 (fiboP1)      TP2 = 0.0 (fiboP7)      TP3 = runner
//   DEEP entry — the limit rested at 0.618 / 0.702 / 0.786 / 0.886:
//       TP1 = 0.5   (fiboP2)      TP2 = 0.382 (fiboP1)    TP3 = runner
//
// TP3 is always a RUNNER — no fixed limit, it rides the trailing stop.
// Percentages default 30/30/40.
//
// A shallow entry must NOT use 0.5 as TP1. The entry limit is clamped AT 0.5, so
// a 0.5 TP1 would sit exactly on the entry price: the trade would "hit TP1" on
// its own fill bar, instantly stage the stop to breakeven, and die a scratch.
// That was the bug. The deep ladder is safe because a deep entry is a full fib
// step (0.5 -> 0.618 or more) below TP1.
//
// All three legs carry ONE shared stop that STAGES up as targets are touched:
//     stage 0  entry       → stop beyond fib 1.0
//     stage 1  TP1 hit     → stop to breakeven + a tick buffer
//     stage 2  TP2 hit     → stop to the TP1 price (locks the first target)
//     stage 3  running past TP2 by >= one trail step → stop to TP2, then ratchets
//              up one trail step for every further trail step of favourable move.
//
// SIZING: fixed fraction of equity risked per trade, sized off the SL distance
// so every trade risks the same R. NOTE the contract math assumes 1.0 of price
// = 1 unit of quote currency per contract (true for XAUUSD/most CFDs); revisit
// syminfo.pointvalue if you run this on an instrument where that is not the case.
```

## [112] INPUTS MOVED 2026-07-28 — every Strategy Execution input now lives in ON

```
// INPUTS MOVED 2026-07-28 — every Strategy Execution input now lives in ONE block
// near the top of the file (search "STRATEGY EXECUTION INPUTS"), ordered the way a
// trade happens and with each dependent setting greyed out by its parent. They had
// to move rather than be reordered in place: two of them (execConfSZ, bLegMaxDays)
// are read by engine code far above this point, and Pine needs the declaration
// first, so leaving the rest here would always strand those two at the top of the
// panel. Nothing about the LOGIC below changed — this block still owns the
// behaviour, it just no longer owns the declarations.
//
// Adding a new execution input? Declare it in that block, in the section it
// belongs to, and give it `active =` if another input can make it irrelevant.
```

## [113] (Fixed R:R exit lever REMOVED 2026-07-25 — the strict single-target exit

```
// (Fixed R:R exit lever REMOVED 2026-07-25 — the strict single-target exit
//  underperformed the scaled fib ladder in testing, so every trade is back on
//  the normal TP1/TP2/runner ladder + staged stop. The four execAplusRR /
//  execBLegRR / *RRmult inputs and the L-RR/S-RR exit branches are gone.)
```

## [114] ── Breakeven band ──────────────────────────────────────────────────────

```
// ── Breakeven band ────────────────────────────────────────────────────────────
// TradingView's "Breakevens: 0" is an artifact: our breakeven stop sits a few
// ticks BEYOND entry (to cover commission), so a breakeven trade books a tiny
// profit and TradingView files it as a winner. The trade label and the diagnostic
// log grade honestly instead — anything inside +/- this band is a BREAKEVEN.
```

## [115] Frozen trade levels — snapshotted while armed so live fib recomputation 

```
// Frozen trade levels — snapshotted while armed so live fib recomputation on
// later bars cannot drag the stop/targets of an open trade (the leg's fib is
// stable during a retrace; it only moves when the leg dies, which cancels us).
```

## [116] B-LEG execution state — a B leg reuses the "Long"/"Short" entry id and a

```
// B-LEG execution state — a B leg reuses the "Long"/"Short" entry id and all the
// frozen SL/TP/label/posBox machinery below, so only two extra things are needed:
// a per-B-leg "already traded" guard and a flag routing the fill to it.
```

## [117] Position-box state — one growing box per trade, painted by result on clo

```
// Position-box state — one growing box per trade, painted by result on close.
// Held as a single OBJECT rather than nine loose vars: Pine objects are passed by
// reference, so f_posBox() further down can mutate these fields from inside a
// function. Nine `var` declarations and the ~35 statements that drove them would
// otherwise sit in the main body, which Pine caps (CE10295).
```

## [118] The entry confluence label is kept as a HANDLE rather than fired and for

```
// The entry confluence label is kept as a HANDLE rather than fired and forgotten,
// so the bar the trade closes can rewrite it with the outcome — a colour-coded
// WIN / LOSS / BREAKEVEN result and the R it made, on top of the confluences
// that armed it. Same object-in-a-function trick as PosBox, same CE10295 reason.
```

## [119] Stop anchor — the fib price the SL is placed at, per the "Stop fib level

```
// Stop anchor — the fib price the SL is placed at, per the "Stop fib level" input,
// the same for every trade. All choices sit on the deep side of 0.5, so the stop
// is beyond the entry band; four of the five also sit INSIDE it, which is the
// hazard that dropdown carries. 0.886 (default) is the deep edge of the band.
// execSlDeep (2026-08-02) makes the anchor depend on WHERE THE LIMIT FILLED, which
// is why this now takes the entry edge. AT OR PAST the 0.786 line -> fib 1.0, the
// leg origin, the only level beyond the whole 0.5-0.886 entry band. 0.702 and
// everything shallower keeps the chosen level. `na(_edge)` is treated as shallow,
// so a missing edge can never silently widen a stop.
// The test is inclusive (<= / >=) because 0.786 is a SNAP TARGET: rule 3 assigns
// fiboP5 to the edge directly, with no arithmetic in between, so the comparison is
// exact and an entry resting ON 0.786 is inside the rule rather than one tick shy.
```

## [120] The minimum-stop floor, in PRICE, for whichever mode is selected. `ta.at

```
// The minimum-stop floor, in PRICE, for whichever mode is selected. `ta.atr` has
// to run on EVERY bar to stay a valid series, so it is hoisted out of the
// function — a ta.* call inside a conditionally-called function silently skips
// bars and returns a different number than the same call on the main body.
```

## [121] The FIB-SNAP entry price (2026-08-02) — where a qualifying gap's resting

```
// The FIB-SNAP entry price (2026-08-02) — where a qualifying gap's resting limit
// actually sits, or `na` for "leave it at the gap's own clamped edge". Returns
// one price for the whole entry model, because its three rules are decided off
// the same two numbers and Pine's statement budget in this file is tight.
//
// The gap is first CLAMPED into the 0.5-0.886 band: _near = the shallowest
// tradeable price (long = gap top, short = gap bottom), _far = the deepest. A
// gap running past either end is therefore judged on the part of it that can
// actually be entered, never on the part outside the band.
//
// Three levels are then read off the ladder, all with 0.886 excluded (see the ⚠):
//   _L = the SHALLOWEST level at or deeper than _near. Because the ladder is
//        ordered, if that one is not ALSO at or shallower than _far then no level
//        is inside the gap at all — every deeper one is further past _far. So one
//        comparison decides "does the body hold a level".
//   _S = the nearest level SHALLOWER than the gap (price reaches it first).
//   _D = the nearest level DEEPER than the gap (price reaches it last, and only
//        after trading through the whole imbalance).
//
// and the toggles resolve them. Rule 1 is independent; rules 2 / 3 / Method 3 all
// answer the SAME question (where does a FLOATING gap rest?) so they cascade,
// each greying the one below it:
//   1. execFibOverlap and a level is INSIDE the gap  -> rest on _L.
//   2. else the gap FLOATS between two levels, and only if it is deeper than
//      0.618, in this order:
//        execFibDeepEdge -> _far, the gap's OWN deep edge (the default);
//        execFibNearest  -> whichever of _S / _D is closer (ties go to _S);
//        execDeepFib     -> _S, always, which is Method 3 exactly;
//        none            -> na, the plain shallow gap edge.
//   3. a gap shallower than 0.618 that holds no level is untouched by all three —
//      it keeps the exact-edge entry it has always had.
//
// ⚠ WHY THIS IS A LADDER, NOT ONE RULE. Method 3 only ever looked at _S, so a gap
// sitting a hair short of 0.702 was still entered at 0.618 — the limit filled well
// above the gap and price then ran past 0.702 anyway. Aaron caught it on the
// 30 Jul 2026 trade. The two fixes trade off against each other and BOTH are here
// so they can be measured against each other rather than argued about:
//   _far (rule 2) is inside the gap, so price entering the imbalance AT ALL fills
//        you. Deeper than _S, and it never costs a fill. This is the default.
//   _D   (rule 3) is past the gap, so it is deeper still — but a setup that only
//        pings the gap and turns never fills. It buys entry price with fill rate.
// Neither is free and neither is proven; run all three and compare.
//
// ⚠ _far FALLS BACK TO _S WHEN THE GAP REACHES THE BAND FLOOR. A gap floating
// between 0.786 and 0.886 clamps its deep edge onto fiboP6 — which is the STOP —
// so the guard below (`_far > fiboP6`, mirrored for shorts) sends it to 0.786
// instead. Without it that gap is a zero stop distance and a cancelled order.
//
// ⚠ 0.886 IS DELIBERATELY NOT A SNAP TARGET in any of the three rules. The stop
// is a FIXED fib (execSlLevel, default 0.886), so an entry resting AT 0.886 has a
// stop distance of zero: `slDist > 0` fails, `strategy.cancel()` fires, and the
// setup vanishes with no trade and no tag. Stopping every scan at 0.786 hands
// those gaps exactly what Method 3 already gave them, so no rule here can ever
// remove a trade. (0.886 only becomes enterable if the stop moves to 1.0 — tried
// on 2026-08-02 and reverted, see the execSlLevel comment.)
```

## [122] ── Entry EDGE — the exact price a resting limit sits at ────────────────

```
// ── Entry EDGE — the exact price a resting limit sits at ───────────────────
// We do NOT wait for a bar to close inside the zone. We rest a limit at the
// near edge of the FVG that overlaps the 0.5-0.886 band, so a WICK to that edge
// fills intrabar (and fills even though the FVG box is deleted the instant it is
// tapped — the order is already placed). The edge is clamped into the band so we
// never buy above 0.5 / sell below 0.5. If several FVGs qualify, we use the one
// price reaches FIRST on the retrace (highest edge for longs, lowest for shorts).
// With "Require FVG" off, the edge falls back to the 0.618 fib (E1) line.
```

## [123] Pre-zone gate: with execFvgPreZone on, a gap the retrace itself printed 

```
        // Pre-zone gate: with execFvgPreZone on, a gap the retrace itself printed cannot
        // price this entry. It is ANDed onto both sides rather than skipping the loop
        // iteration, so with the toggle off the condition is the original one exactly.
```

## [124] ── SNIPER ZONE — the SECOND accepted confirmation ──────────────────────

```
// ── SNIPER ZONE — the SECOND accepted confirmation ─────────────────────────
// The SZ is the break leg's 0.5-0.618 pocket, so it already lives inside the
// 0.5-0.886 entry band. It is a FALLBACK only: the loop above runs first, so a
// leg that has a qualifying FVG is priced off that gap exactly as before and no
// existing result moves. The SZ only fills in on a leg that had no gap at all —
// the legs the "NO FVG missed" counter has been booking.
// The limit rests at the FAR side of the pocket (the deep end of the retrace),
// clamped so it can never sit shallower than 0.5, and the zone is ignored if it
// falls past 0.886 or belongs to a different direction. The sz_bar guard stops a
// zone left over from an earlier leg pricing this trade: it must have been
// anchored at or after the SOS this setup is riding.
```

## [125] (The no-FVG fallback — "no qualifying gap, so rest at the 0.618" — used 

```
// (The no-FVG fallback — "no qualifying gap, so rest at the 0.618" — used to sit HERE. It was
//  MOVED 2026-08-10 to just after the arm-source snapshot below, because `execNoGapArm` gates it
//  on sosL_swp / sosL_div and those are not computed until then. Nothing between the two points
//  reads longEdge / shortEdge, so at execNoGapArm = "Any" the move is behaviour-neutral.)
```

## [126] (The "FVG TOUCHES 0.5" fallback loop was REMOVED 2026-08-02 with its exe

```
// (The "FVG TOUCHES 0.5" fallback loop was REMOVED 2026-08-02 with its execFvg50
//  input — see the note in the STRATEGY EXECUTION INPUTS block. It was the last
//  and shallowest tier of the entry ladder, gated OFF by default for its whole
//  life, so every historical result reproduces unchanged.)
```

## [127] ── Arm-source filter — isolate WHICH Stage-1 confluence is allowed to ar

```
// ── Arm-source filter — isolate WHICH Stage-1 confluence is allowed to arm ────
// The engine treats a sweep and a divergence as interchangeable Stage-1 triggers
// and collapses both into ONE variable (aplus*_sweepBar), so by the time an SOS
// fires the origin of the arm is gone. We recover it here rather than editing the
// engine (which must stay byte-identical to mpc_assistant.pine): keep the two arm
// bars apart, and on the SOS bar snapshot which sources were still inside the
// staleness window. A setup then only trades if a source you left ENABLED was one
// of them. Everything downstream — SOS, fib zone, FVG, veto, TP ladder — is
// untouched, so the only thing these toggles change is the trigger.
// Note both sources can be live on the same SOS; that setup trades under either
// toggle alone, which is correct — it genuinely had both.
// The window is measured in TIME (see aplusWindow), so each arm is remembered by
// timestamp as well as bar — the bar index alone cannot be compared against a
// minutes-based window.
```

## [128] Retro-linked SOS: the snapshot above never ran for it, because on the SO

```
// Retro-linked SOS: the snapshot above never ran for it, because on the SOS bar the
// divergence had not confirmed yet. Take the snapshot now, measured against the SOS
// bar rather than this one, so a divergence-armed setup can actually trade.
```

## [129] ── The no-FVG fallback (moved here 2026-08-10 — see the note in the entr

```
// ── The no-FVG fallback (moved here 2026-08-10 — see the note in the entry ladder above) ──────
// No qualifying gap on the leg, so rest the limit at the 0.618. `execNoGapArm` decides WHICH of
// those setups may: "Any" is the original rule exactly, so the default is byte-identical and no
// historical result moves. The gate reads the RAW sosL_swp / sosL_div, NOT useSwpL / useDivL —
// it asks what the market did at the SOS, not which triggers you left enabled, so it stays
// meaningful with "Arm on RSI divergence" off (which is the shipped default).
```

## [130] A source only counts if you ENABLED it AND it was live at the SOS. The t

```
// A source only counts if you ENABLED it AND it was live at the SOS. The trade
// decision and the confluence label read these same two flags, so the label can
// never credit a confluence the trade did not use: with "Arm on liquidity sweep"
// off, a sweep that happened to be sitting there is not part of this trade's
// story and must not appear on it.
```

## [131] (The missed-setup callout used to fire here. It now lives further down, 

```
// (The missed-setup callout used to fire here. It now lives further down, after
//  the veto / late-day / HTF gates are declared, so it can name which one of them
//  actually blocked the entry — see "MISSED-SETUP CALLOUT" below.)
```

## [132] Confluence text — every line is printed because ITS OWN flag is true on 

```
// Confluence text — every line is printed because ITS OWN flag is true on the bar
// the order was placed, never because the feature exists in the script. Nothing
// in here is a fixed template.
// Body of the entry label. The direction header is NOT part of this — it is
// prepended by f_confOpen and rewritten with the result by f_confClose, so the
// top line of the box is always the trade type.
//
// Every line is printed because ITS OWN flag is true, and every price is the
// price this trade actually placed. Nothing here is a fixed template: the TP
// rungs name the fib level the ladder really used (deep entries run 0.5 → 0.382,
// shallow ones 0.382 → 0.0) and print that level's price alongside it, so the
// label can never claim a target the ladder did not set.
```

## [133] ── Armed conditions — setup to SOS, fib aligned, an edge exists, not vet

```
// ── Armed conditions — setup to SOS, fib aligned, an edge exists, not vetoed,
//    flat, and this leg not already traded ──
// Final-hour block: no new entries 16:00-17:00 NY (gold closes 17:00, reopens 18:00).
```

## [134] ── HTF exhaustion filter (loss-mitigation test #1) ─────────────────────

```
// ── HTF exhaustion filter (loss-mitigation test #1) ──────────────────────────
// The engine already grades each HTF bias as a breakout CLOSURE ("Close > Prev
// High" / "Close < Prev Low") or an exhaustion SWEEP ("Swept High" / "Swept
// Low"). We only ever want to fade the sweep, never fight a fresh breakout: a
// short (fading a high) is blocked when the HTF just closed ABOVE its prior high;
// a long (fading a low) when it just closed BELOW its prior low. Swept states
// never block. Read the desc strings so a sweep and a closure are told apart.
```

## [135] ── HTF-bias confluence (Daily + Weekly working TOGETHER) ───────────────

```
// ── HTF-bias confluence (Daily + Weekly working TOGETHER) ────────────────────
// Each timeframe carries a requirement judged against the trade's direction.
// "agree" = the TF bias matches the trade (Bullish for a long, Bearish for a
// short); "oppose" = the TF bias is against it. Returns TRUE = this TF blocks
// the trade. Neutral satisfies only "Must not oppose". Combine the two legs to
// express a forming reversal (Weekly opposes, Daily agrees) or full alignment
// (both agree) — the relationship between the two, not either one alone.
```

## [136] ── MISSED-DUE-TO-NO-FVG counter ────────────────────────────────────────

```
// ── MISSED-DUE-TO-NO-FVG counter ──────────────────────────────────────────────
// A "missed" setup = every trade gate is satisfiable EXCEPT the FVG. Same
// condition as longArmed/shortArmed but with na(edge) instead of not na(edge),
// AND price actually inside the entry band (aplus*_half = 0.5 tapped) so we only
// count genuine near-misses, not every pre-retrace bar. A per-leg latch survives
// the death bar (the engine clears aplus*_sosBar / aplus*_618 the instant the
// leg dies); the miss is booked when the leg dies still latched. If an FVG edge
// EVER appears the latch clears — that is a no-fill, not an FVG-missing miss.
// (The on-chart "NO FVG" labels were REMOVED 2026-07-22. They duplicated the
//  missed-setup callout, which already names FVG as the missing confluence, and
//  the compile-token budget is better spent on the trade bands. The COUNTERS
//  below stay — the diagnostic log still reports every one of these misses.)
```

## [137] ══ MISSED-SETUP CALLOUT ════════════════════════════════════════════════

```
// ══ MISSED-SETUP CALLOUT ══════════════════════════════════════════════════════
// Fires when a setup that reached at least 2 of the 3 confluences dies WITHOUT
// ever becoming a trade — for ANY reason, not just the old "never reached the
// zone" case. What counts as a confluence is read live from the strategy inputs,
// so the callout always describes the strategy you are actually running:
//
//   1 ARM   — only an ENABLED arm source counts. With "Arm on liquidity sweep"
//             off, a sweep-armed setup lists Arm as MISSING and says exactly
//             that; same for divergence. Both enabled and both live prints both.
//   2 SOS   — always met here: the watch only opens once the SOS has landed.
//   3 ZONE  — price had to retrace into the 0.5-0.886 band AND, while "Require
//             FVG overlap" is on, a gap had to be live to rest the limit on.
//             Turn that input off and reaching the band alone satisfies it.
//
// A setup that met all three and STILL did not fill is the most important case —
// it is the one that used to vanish silently — so it is drawn too, headed
// "3 OF 3 · NO ENTRY", with the real blocker named: the veto, the final-hour
// rule, the HTF bias filter, or "limit rested but price never touched it".
//
// The would-be entry price is the FVG edge if one ever qualified, otherwise the
// 0.618 (E1) fib — exactly where the limit would have rested either way.
//
// Placement: the box is pinned a clear 4 ATR beyond the recent range so it can
// never sit on top of the candles, and the leader lines connect it back to the
// bars that matter.
```

## [138] ══ BLOCKED-TRADE MARKER ════════════════════════════════════════════════

```
// ══ BLOCKED-TRADE MARKER ══════════════════════════════════════════════════════
// A setup that was READY to rest its entry limit — armed through to the SOS, fib
// pointing the right way, a live entry edge to rest on, flat, this leg not yet
// traded — and was stopped by one of YOUR OWN TOGGLES rather than by price.
//
// These are the only trades that are invisible everywhere else: no order is ever
// placed, so nothing is drawn, no row lands in the trade list, and the Strategy
// Tester cannot know they existed. That makes it impossible to judge whether a
// blocking rule is protecting you or costing you. Now each one prints a PINK tag
// with the reason on hover, and a dotted leader down to the exact price the limit
// would have rested at — so you can flip the rule off, re-run, and compare.
//
// ONE TAG PER SETUP PER REASON: the dedupe key is the SOS bar plus the reason
// code, so a setup blocked for twenty bars running is one tag, not twenty — but
// if the reason CHANGES (the veto clears and the final hour then blocks it) that
// is a genuinely different refusal and gets its own tag.
```

## [139] Reason PRECEDENCE — the first rule that would refuse the order is the on

```
// Reason PRECEDENCE — the first rule that would refuse the order is the one
// reported, so a tag can never blame a downstream gate for an upstream refusal.
//   1 direction off · 2 arm source off · 3 final hour · 4 veto · 5 HTF breakout · 6 HTF bias · 7 stop too tight
```

## [140] ks carries the last (sosBar*10 + code) reported per side — the dedupe ke

```
// ks carries the last (sosBar*10 + code) reported per side — the dedupe key.
// Trailing `int _blkDone = 0` for the same CE10235 reason as f_posBox: without it
// the drawing chain becomes the function's return expression.
```

## [141] "Ready" deliberately omits every toggle gate — those ARE the blockers we

```
// "Ready" deliberately omits every toggle gate — those ARE the blockers we are
// reporting. It asserts only the things price and the engine decide: the SOS is
// in, the fib agrees, an edge exists to rest on, we are flat, and this leg has
// not already been traded.
```

## [142] The min-stop refusal happens at order placement below; it is recomputed 

```
// The min-stop refusal happens at order placement below; it is recomputed here so
// a setup refused on PRICE gets a chart tag like every other refusal. `> 0` keeps
// an inverted stop (dist <= 0, already handled by its own cancel) from being
// mislabelled as a floor refusal. na propagates, so a missing fib tags nothing.
```

## [143] ── Ladder select — which rungs this trade gets depends on how DEEP the r

```
// ── Ladder select — which rungs this trade gets depends on how DEEP the resting
//    limit sits. "Deep" = at or beyond the 0.618 fib (E1), i.e. one of the lower
//    eligible entry levels (0.618 / 0.702 / 0.786 / 0.886). A deep entry is a full
//    fib step below 0.5, so 0.5 is a legitimate TP1 for it. A shallow entry rests
//    ON the 0.5 clamp, so 0.5 is the entry price itself and TP1 must skip to 0.382.
//    (With "Require FVG" off the edge falls back to 0.618 exactly — that is deep.)
```

## [144] ── B-LEG arm — the frozen SZ band is live, untapped and valid, we're fla

```
// ── B-LEG arm — the frozen SZ band is live, untapped and valid, we're flat and
//    this band has not already been traded. A+ has priority: while a fresh A+ leg
//    is armed on the same side it owns the "Long"/"Short" limit and the B leg
//    stands down. Honours Trade longs/shorts + the final-hour block; it does NOT
//    use the arm-source, FVG or veto gates (the band tap is the whole trigger).
```

## [145] ── B-LEG entries — rest a limit at the frozen band's near (0.5) edge, re

```
// ── B-LEG entries — rest a limit at the frozen band's near (0.5) edge, reusing
//    the "Long"/"Short" id so the fill / exits / posBox / label all flow through
//    the same machinery. SL beyond the leg origin (fib 1.0). Ladder reuses the A+
//    shallow rungs from the frozen band: TP1 = the broken swing extreme (fib 0.0
//    of the band = 2·edge − origin), TP2 = the expansion extreme (bLeg*_tgt), TP3
//    = runner. pendIsBLeg* routes the fill to the B-leg "already traded" guard. ──
// B-LEG diagnostic context — appended to the entry conf so each B-leg log line
// carries the HTF bias, session and cycle zone at fill, to profile the losers.
```

## [146] ── Mark the leg traded once the resting limit FILLS; snapshot the entry 

```
// ── Mark the leg traded once the resting limit FILLS; snapshot the entry price
//    and reset the stop stage. Reset stage to 0 whenever we are flat. ──
// Offset the confluence label well clear of the candles (longs below, shorts
// above) and drop a thin line from the entry price to the label so it still
// points at the exact entry without covering the price action. The multiplier is
// an input because it is the ONLY control over where the hover tooltip opens —
// TradingView anchors the tooltip to the label and exposes no placement API.
```

## [147] While the trade is OPEN the label is grey — the result is not known yet 

```
// While the trade is OPEN the label is grey — the result is not known yet and
// colouring it by direction would be a claim the chart cannot back up. Direction
// is already on the label in words ("▲ LONG") and under the candle as a triangle.
//
// The chart shows ONE LINE. The arm source, SOS age, FVG/POI/DIV flags and the
// full entry / stop / TP ladder with real prices are in the label's TOOLTIP.
```

## [148] On the bar the trade closes: recolour by RESULT and append the R. Green 

```
// On the bar the trade closes: recolour by RESULT and append the R. Green won,
// red lost, ORANGE breakeven — a trade that went out and came back to entry is a
// breakeven, not a win, and the colour has to say so. Graded against the SAME
// breakeven band the diagnostic log uses, so the label and the log can never
// disagree about the same trade.
// The result filter is applied here rather than at entry because the result is
// what it filters on — a label that fails it is deleted the moment it is graded.
```

## [149] ── Grade the trade the bar it closes: WIN / LOSS / BREAKEVEN in R, not i

```
// ── Grade the trade the bar it closes: WIN / LOSS / BREAKEVEN in R, not in cents ─
// Graded once and handed to the entry label and the diagnostic log, so the two
// can never tell different stories about the same trade.
```

## [150] ── Position box — the trade drawn as STACKED BANDS, not as loose lines ─

```
// ── Position box — the trade drawn as STACKED BANDS, not as loose lines ──────
// A trade scales out in up to three pieces, so one box can never describe it. It
// is drawn as a stack of bands, each one the slice of price a single piece was
// actually paid for:
//     entry → TP1 fill    darkest green    the first third, banked
//     TP1   → TP2 fill    mid green        the second third
//     TP2   → runner fill lightest green   what the trail squeezed out
// Read the stack from the bottom up (top down on a short) and the gradient tells
// you how far the trade ran before each piece came off, with no text to decode.
// A faded RED band behind them shows how far price went AGAINST the trade first —
// the heat you had to sit through to get paid.
// A trade that banked nothing is a single red band, entry → the stop fill. One
// that came back to entry is a lone orange line. Losing has one colour, winning
// has one colour, and the shade is the only thing that varies.
//
// EVERY band comes from the strategy's own closed-trade log, at the price the
// engine REALLY filled — never a fib level it merely aimed at — so the drawing
// can never claim profit the P&L does not have. Nothing is drawn from the trade's
// high-water mark: price spiking to a target and reversing before the limit fills
// pays you nothing.
```

## [151] One banked target: its slice of the move, a faint dashed line at the exa

```
// One banked target: its slice of the move, a faint dashed line at the exact fill
// price, and its tag. Every tag is anchored at the SAME x (lx = the trade's right
// edge), so TP1/TP2/TP3 stack in one column off to the side instead of scattering
// across the candles at the bar each happened to fill on.
// (`from` / `to` are NOT usable as parameter names — `to` is the for-loop keyword
//  and the parser rejects the whole declaration, blaming the first parameter.)
```

## [152] 2. Bank any exits that filled. They are RECORDED here and DRAWN on close

```
        // 2. Bank any exits that filled. They are RECORDED here and DRAWN on close,
        //    which is what lets all three tags share one right-hand edge. Runs before
        //    the paint below, so a trade that opens and closes on one bar still works.
```

## [153] A function's LAST statement is its return value, and the three branches

```
        // A function's LAST statement is its return value, and the three branches
        // above create a box / a box / a line — Pine refuses to pick a type for
        // that (CE10235). This constant sits after them so the drawing chain is
        // never the return expression. It is not busywork: remove it and the
        // script stops compiling.
```

## [154] Always-visible entry markers (the long/short position indicator itself) 

```
// Always-visible entry markers (the long/short position indicator itself) — a
// triangle at every fill, so you can never miss where a trade opened even when
// the result box is a thin scratch.
```

## [155] ── Advance the stop stage as each target is touched THIS bar, and ratche

```
// ── Advance the stop stage as each target is touched THIS bar, and ratchet the
//    runner past TP2. We react at the bar's close, so the tighter stop only ever
//    governs FUTURE price (no look-ahead).
//      Stage 1 (TP1 touched) → stop to breakeven + buffer
//      Stage 2 (TP2 touched) → stop to the TP1 price
//      Runner: once price is one full trail step beyond TP2, the stop sits at TP2
//              and climbs one step for every further step of favourable movement.
// Stage 1 must stay tied to the TP1 TOUCH, not to a fixed R distance. TP1 is a
// limit order: keying breakeven off TP1 guarantees the partial is banked before
// the rest of the position is protected. An R trigger can fire on a wick BEFORE
// TP1 fills, which protects a position that has taken no profit at all — tested
// over 3.5y on XAUUSD 15m, every R variant (0.25/0.5/1R and off) underperformed
// this rule, so do not "decouple" them again.
```

## [156] f_swingRatchet — the structure trail that does not stand still. Same anc

```
// f_swingRatchet — the structure trail that does not stand still. Same anchor as the
// Structure trail (last confirmed swing ± buffer), but from there the stop climbs one
// `pct`-of-price step for every step of favourable move. The plain Structure trail sits
// at the swing however far price runs, which is where the runner's give-back comes from:
// the swing is a LAGGING anchor and in a strong leg it ends up a long way behind. Falls
// back to the bare anchor until the move is one full step past it, so it is never LOOSER
// than the Structure trail — only equal or tighter.
```

## [157] lSL / sSL are only ever written while flat (longArmed requires position_

```
// lSL / sSL are only ever written while flat (longArmed requires position_size == 0),
// so entry-to-stop is frozen for the life of the trade and is a safe 1R yardstick.
// ── The FILL bar cannot stage the stop (BUG_exit_fill_price_mismatch.md) ────
// `position_size[1] > 0` = we were ALREADY long last bar, i.e. this is not the fill bar.
// A resting limit is reached by price coming to it from the wrong side — a buy limit fills on
// the way DOWN, a sell limit on the way UP — so the fill bar's FAVOURABLE extreme is where the
// market was before the trade existed, not profit the trade made. Staging off it lifted the stop
// to breakeven on a trade that had gone nowhere, and breakeven is then on the WRONG SIDE of the
// market, so TradingView market-closes every leg at the next bar's open at a price that is
// neither the stop nor any target. The exit orders are not live on the fill bar either (one-bar
// delay), so nothing could have banked there. Written as a bare condition rather than a helper
// bool on purpose: this file is near Pine's main-body statement cap (CE10295).
```

## [158] Runner trail candidate — the fixed-step ratchet, a structure trail parke

```
// Runner trail candidate — the fixed-step ratchet, a structure trail parked at the last
// confirmed swing (st.last_conf_low/high), or that same swing anchor with a % ratchet
// climbing off it. na = not engaged yet.
```

## [159] TP2 stop floor — the protective baseline the instant TP2 hits, before th

```
// TP2 stop floor — the protective baseline the instant TP2 hits, before the runner
// trail takes over. Default snaps to TP1; the alternatives delay that jump for room.
// "One trail step behind" never drops below breakeven, so it can't hand back a loss.
```

## [174] `pyramiding = 5` — the scale-in toggle's one unavoidable compile-time cost

```
// 🔴 `pyramiding = 5` IS THE SCALE-IN TOGGLE'S ONE UNAVOIDABLE COMPILE-TIME COST, and it
// is 5 rather than 0 for one reason: the base entry plus `execScaleAdds` (max 4) adds.
// It CANNOT be driven by an input — `strategy()` is evaluated once at compile time — so it
// is raised permanently and the toggle is enforced in the add logic instead.
// ⚠ WITH `execScaleIn` OFF NOTHING CHANGES, and that is checked rather than assumed: every
// `strategy.entry` that opens a trade is gated on `strategy.position_size == 0` (see
// `longArmed` / `shortArmed`), so the base entry cannot stack on itself whatever this says.
// The only other entries are the L-ADD*/S-ADD* ids below, and each is gated on execScaleIn.
```

## [175] The three scale-in inputs are declared LAST on purpose, and belong to group 6

```
// 🔴 THESE THREE SIT AT THE END OF THE PANEL BLOCK RATHER THAN NEXT TO THE OTHER STOP
// SETTINGS, AND MOVING THEM UP WOULD COST AARON HIS SAVED CHART. TradingView keys a saved
// input value off DECLARATION ORDER within each type, not off the title or the group — so
// inserting a bool beside the other exit toggles silently re-keys every bool declared
// after it, and a live chart comes back with its checkboxes shuffled. `group = G6` puts
// them in the right BOX on the panel regardless of where they are declared, so the display
// is correct and nothing already saved moves. Append here; never insert above.
```

## [176] Scale-in state — every add is sized off the OPENING quantity, never the live one

```
// 🔴 `lBaseQty` IS THE SIZE THE TRADE OPENED WITH, AND EVERY ADD IS SIZED OFF IT rather
// than off `strategy.position_size`. Sizing off the live position would compound: add #2
// would budget against base+add#1, add #3 against base+add#1+add#2, and the "an add can
// never create a loser" guarantee would be spent several times over on one trade.
// ⚠ `lAddStop` is the stop the LAST add was sized against, and the next add is refused
// until the trail has moved past it. Without that a stalling runner re-adds on every bar
// at the same locked profit, which is the same over-spend by a slower route.
```

## [177] SCALE-IN — add to a runner the trail is already protecting

```
// The whole rule, and it is a SIZING rule rather than a timing one:
//
//     locked  = (stop - entry) * baseQty        profit the stop already guarantees
//     perUnit = (close - stop)                  what one extra unit risks to that SAME stop
//     addQty  = locked / perUnit                so the add's worst case == the locked profit
//
// Stop out immediately after adding and the two cancel: the base banks `locked`, the add
// gives back at most `locked`, and the trade closes at worst flat. An add can shrink a
// winner. It cannot manufacture a loser.
//
// 🔴 WHY THE TRAIL AND NOT A TARGET. At TP2 the stop is only at TP1, so `locked` is small
// while `close - stop` is large — the affordable add is a rounding error and the idea looks
// worthless. Once the trail has ratcheted up near price the same arithmetic permits a LARGE
// add. So the rule self-regulates: a trending runner buys size, a stalling one buys nothing,
// and no extra "is this trade still good" test is needed.
//
// 🔴 THERE IS NO STRUCTURAL TRIGGER IN HERE AT ALL, AND THAT IS AN OPEN DESIGN QUESTION
// RATHER THAN AN OVERSIGHT (Aaron, 2026-08-16: "I don't know what market structures I'm
// looking at to add into"). The rule asks only "can I afford this", never "is this a good
// place". Structure does enter INDIRECTLY — the trail is parked on the last confirmed swing
// (f_swingRatchet), so an add fires roughly when a new HL/LH confirms — but that is a side
// effect of the trail's own anchor, not a rule anyone chose. It also enters at MARKET on the
// bar the trail moves, which is the worst price of the leg, where the BASE entry rests a
// limit in a discount zone and waits. Adding on a fresh BOS, on a retest of the broken
// level, or at a limit on the new leg's retrace are all untested alternatives.
//
// ⚠ ONE STOP FOR EVERYTHING. Each add gets its own entry id purely so Pine can size it, and
// every one of them exits on `lStop` — the same trail the base rides. Per-tranche stops would
// make this two trades wearing one ticket and would destroy the R column.
// ⚠ THE GUARANTEE HOLDS TO THE STOP, NOT THROUGH A GAP. Price that jumps straight past the
// stop fills the whole combined size at the open, and 3x the size loses 3x. Nothing here
// protects against that and nothing can.
// ⚠ `strategy.position_size[1]` GUARDS THE FILL BAR: the bar a trade opens on has no trail
// yet, and its favourable extreme is the approach to the limit rather than a move the trade
// made — the same reason the stage machine above carries the identical guard.
// ⚠ MEASURED 2026-08-16 (XAUUSD 15m, 2018-09-13 -> 2026-08-14, PU Prime ECN costs charged):
// off 128.26R / 6.03R maxDD; 2 adds 211.59R / 8.72R maxDD, worst trade unchanged at -2.06R.
// Removing the affordability test and adding a flat 1x instead cost 11 extra losing trades,
// which is what the `locked / perUnit` line is buying.
```

## [178] Every add needs its OWN exit and its OWN close — `from_entry` matches one id

```
// 🔴 EVERY ADD RIDES THE SAME `lStop`, and each needs its OWN exit call because an add
// carries its own entry id. `from_entry` is matched exactly, so `L-RUN` protects the
// base and nothing else — without those lines an add would sit in the book with no stop
// at all, which is the opposite of what this feature claims to do.
// ⚠ `strategy.close` MATCHES ONE ENTRY ID TOO. The base leaving on an opposite SOS while
// the adds stayed open would leave a naked pyramid running against a fresh bearish
// structure — the single worst state this feature could produce. Same for the clock.
```

## [160] ── The TIME STOP — the one exit lever driven by the clock, not by price 

```
// ── The TIME STOP — the one exit lever driven by the clock, not by price ─────────
// ⚠ THE NOTE THAT USED TO SIT HERE IS GONE AND ITS ADVICE IS NOW BACKWARDS. It said these
// two inputs were declared at this line ON PURPOSE — as the LAST string and float in the
// file — so that adding them shifted no saved chart value, and that moving them up to the
// execution panel must never be "tidied up". That reasoning was correct for its day and
// died on 2026-08-12, when every input in this file moved into one consolidated panel
// block and the whole panel was renumbered. `execTimeStopMode` / `execTimeStopHrs` now
// live in `6 · Stop & targets` with the rest of the exit ladder. Saved values were reset
// once by that pass, deliberately and knowingly; there is no slot left to protect here.
```

## [161] ── Manage open long: TP1/TP2 scale-outs + runner, staged stop ──

```
// ── Manage open long: TP1/TP2 scale-outs + runner, staged stop ──
// A rung sized 0% is SKIPPED, never placed. strategy.exit() treats qty_percent = 0 as
// "unspecified" and falls back to closing the WHOLE position at that limit, so calling it
// with 0 would turn "bank nothing here" into "bank everything here" — the exact opposite.
// Skipping leaves the runner leg as the only exit, which is what 0% means. The TP PRICES
// still drive the staged stop (lStage/sStage above) whatever the rung sizes are.
```

## [162] PARITY EXPORT — per-bar DECISION STREAM  (for compare_strategy.py)  _(only in mpc_strategy_export.pine)_

```
//============================================================================
//  PARITY EXPORT — per-bar DECISION STREAM  (for compare_strategy.py)
//============================================================================
// This file is `mpc_strategy.pine` + THIS appended block, nothing else changed. The
// trade logic above must stay BYTE-IDENTICAL to `mpc_strategy.pine` — when your brother
// re-pastes the strategy, regenerate this file (copy the strategy, re-append this block).
//
// REGENERATED 2026-07-30 from `mpc_strategy.pine`, to pick up the MINIMUM STOP DISTANCE
// filter (`execMinStopMode` / `execMinStopVal`, Pine 423-432 + 3796-3807 + 4167-4172 +
// 4204/4221) and the block reason code 7 that reports it. The previous copy predated all of
// it, which was the one KNOWN Pine↔Python divergence on the A+ pair: the parent could refuse
// a setup on stop distance, this export carried no column saying so, and compare_strategy.py
// therefore reported GREEN while diffing against a config it could not read. Two new columns
// close it — `cfg_min_stop` (the mode) and `cfg_min_stop_val` (the floor). Nothing else moved:
// the body below is byte-identical to the parent's lines 1-4581 apart from line 29's title.
//
// Earlier — REGENERATED 2026-07-26 from `mpc_strategy.pine` (post-SVP-orphan fix). The previous copy
// was from 2026-07-22 and had drifted on FIVE trade-affecting changes, so any diff it
// produced was July-22 drift, not a bug:
//   • the whole B LEG setup — tracker, `bLegArmL/S` capture, the two entry blocks, and the
//     `execAplus` / `execBLeg` / `bLegMaxDays` inputs (`execAplus` also joined longArmed)
//   • `execFvg50` — the least-favorable straddles-0.5 entry fallback
//   • `execRunnerTrail` + `execStructTrailBufTk` — the structure (swing) runner trail, now
//     the DEFAULT method, replacing the fixed-step ratchet
//   • `execTp2StopMode` — the TP2 stop floor (TP1 price / Breakeven / one step behind)
//   • the fixed R:R exit lever, removed
// It also still carried the JARVIS confirmation table, which the parent dropped 2026-07-24.
//
// Regenerate the same way — the split points are exact:
//   sed -n '1,<line before the DIAGNOSTIC LOG header>p' mpc_strategy.pine  > new
//   sed -n '<the two blank lines before this PARITY EXPORT header>,$p' this-file >> new
// then (a) restore `strategy("MPC A+ Strategy Export"` on line 29 — the ONLY intended
// difference from the parent — and (b) re-check that every identifier this block reads
// still exists upstream (they are all globals declared before the exits).
// (As of the 2026-07-30 regen the split was `sed -n '1,4581p'` on the parent and
//  `sed -n '4550,$p'` on the previous copy of this file. Both move whenever either file
//  changes length — find them, never reuse these numbers blind.)
//
// GAP CLOSED 2026-07-26. The regen above left six toggles with no column, and one of them
// (`execRunnerTrail`) had ALREADY defaulted to "Structure (swing)" — so an export taken in
// between told compare_strategy.py nothing about the trail the Pine actually ran, and the
// Python bot silently fell back to the fixed-step default. Any parity diff from that window
// is drift, not a bug. Now carried: `execAplus` / `execBLeg` / `execFvg50` as cfg_bits bits
// 16384 / 32768 / 65536, plus `cfg_exitmode` (the two exit dropdowns) and one raw column
// each for the six exit numerics + the scratch band. EVERY trade-affecting input has a
// column again — the standing rule is that a new one lands here and in compare_strategy.py
// in the same commit as the Pine change.
//
// The base strategy already sits just under Pine's main-body statement cap (CE10295 —
// that is WHY its big renders are wrapped in f_drawTable / f_posBox). The token-heavy
// Diagnostic Log block is removed in this export copy to fit under Pine's token cap. So this
// block MUST stay tiny: the per-bar values are computed inside functions, and the columns
// are PACKED — a dozen booleans into one integer, etc. — so there are ~14 plots, not ~40.
// `compare_strategy.py` unpacks them with the exact same scheme; keep the two in lockstep.
//
// GOTCHA (from the engine exports): a plotted column MUST use a transparent colour, never
// `display.none` — TradingView drops display.none series from the CSV export.
//
// Run: put this on a 5m XAUUSD chart (5m exercises the Macro fib), set your toggles,
// "Export chart data" to CSV, then:
//   python strategies/python/mpc_sos_fade/tools/compare_strategy.py <that.csv> --warmup N
```

## [163] DECISION STREAM (packed — compare_strategy.py unpacks with the same sche  _(only in mpc_strategy_export.pine)_

```
// DECISION STREAM (packed — compare_strategy.py unpacks with the same scheme):
//   px_dec_bits = longArmed·1 + shortArmed·2 + longVetoA·4 + shortVetoA·8 + (entryDir==1?16:entryDir==-1?32:0)
//   (longVetoA/shortVetoA are the SOS-AWARE vetoes — a divergence printing AFTER the
//    SOS no longer blocks its own setup. Renamed from longVeto/shortVeto 2026-07-21.)
//   px_stages   = aplusL_stage·10 + aplusS_stage
//   px_edge     = the active side's entry edge (longEdge and shortEdge are mutually exclusive by fibo_dir)
```

## [164] BLOCKED TRADES (packed) — the setups that were ready to rest a limit and  _(only in mpc_strategy_export.pine)_

```
// BLOCKED TRADES (packed) — the setups that were ready to rest a limit and were
// refused by a toggle, so no order exists and nothing else in the export or the
// trade list records them. Same codes the pink chart tag and the [BLOCK] log use:
//   px_block = longCode + shortCode·10
//   code: 0 none · 1 direction off · 2 arm source off · 3 final hour
//         4 divergence/extreme veto · 5 HTF breakout · 6 HTF bias
// Non-zero on EVERY bar the block holds (not deduped like the tag), so an offline
// reader can measure how LONG each refusal lasted as well as count them.
```

## [165] CONFIG (packed). cfg_bits packs 16 booleans (4096 = execConfSZ, 2026-07-  _(only in mpc_strategy_export.pine)_

```
// CONFIG (packed). cfg_bits packs 16 booleans (4096 = execConfSZ, 2026-07-22; 8192 = execDeepFib,
// 2026-07-23; 16384 = execAplus, 32768 = execBLeg, both 2026-07-26);
// cfg_strcodes packs the 4 HTF/SL string dropdowns; cfg_divints packs the 5 divergence ints;
// cfg_exitmode packs the 2 EXIT dropdowns and cfg_exitnums the 5 exit-ladder numerics
// (both added 2026-07-26, when the structure runner trail landed and became the default).
// Every toggle that changes a trade decision now has a column — keep it that way.
// ⚠ BIT 65536 IS RETIRED, NOT FREE. It carried execFvg50 until that input was deleted from the
// parent on 2026-08-02, so it now reads 0 on every bar and compare_strategy.py decodes
// exec_fvg_50 = False (its "refuse an export taken with it on" guard can therefore never fire —
// harmless, and left in place so an OLD export still hits it). Do NOT reuse 65536 for a new
// toggle: an archived export would decode the new flag as whatever execFvg50 was set to.
// The 2026-08-02 entry model added FIVE bits above it — 131072 execFibOverlap, 262144
// execFibDeepEdge, 524288 execFibNearest, 1048576 execFvgPreZone, 2097152 execSlDeep. Every one
// of them re-prices the entry limit or the stop, so an export without them would configure the
// Python bot to a DIFFERENT entry model and report the difference as a logic bug. That is the
// same trap `execRunnerTrail` set in July, and it is why they land in the same commit as the Pine.
// ⚠ An export taken BEFORE 2026-08-02 has all five bits clear, which decodes to overlap/deep-edge
// /nearest/pre-zone/sl-deep all OFF. For the first four that is exactly right — the rules did not
// exist, so the bot ran the plain gap edge, which is what `exec_fib_nearest = False` reproduces.
// So old exports stay readable; do NOT "helpfully" default a missing bit to the Python default.
```

## [166] EXIT LADDER — the levers that decide where the stop and the partials sit  _(only in mpc_strategy_export.pine)_

```
// EXIT LADDER — the levers that decide where the stop and the partials sit. The two
// dropdowns pack into one int; the six numerics are plotted RAW, one column each.
//   cfg_exitmode = (Fixed step?0 : Structure (swing)?1 : Structure + % ratchet?2)*10
//                  + (TP1 price?0 : Breakeven?1 : one-step?2)
// The runner-trail slot went BINARY→TERNARY on 2026-07-28 when "Structure + % ratchet"
// landed AND became the default. An export taken before that date encodes the old
// `Fixed step?0:1`, whose 1 still decodes to "Structure (swing)" — correct, because that
// is what those exports actually ran. Only a 2 is new, so old exports stay readable.
// They are NOT packed because they are floats: any pack that fits five of them in one
// float64 has to round, and a silently rounded buffer mis-configures the Python bot —
// which is the exact failure this block exists to prevent. A bare `plot(ident)` is also
// cheaper in tokens than the arithmetic a pack would need, so nothing is lost.
```

## [167] MINIMUM STOP DISTANCE (2026-07-30) — an ENTRY filter, so it is deliberat  _(only in mpc_strategy_export.pine)_

```
// MINIMUM STOP DISTANCE (2026-07-30) — an ENTRY filter, so it is deliberately NOT folded
// into cfg_exitmode: that column is the two EXIT dropdowns, and mixing an entry gate into
// it would make both harder to read and the decoder harder to trust. The mode is a code,
// the floor is plotted RAW for the same reason the exit numerics are — it is a float, and
// a packed float that rounds mis-configures the bot silently.
//   cfg_min_stop = Off?0 : % of price?1 : Fixed $?2 : x ATR(14)?3
// An export with NO cfg_min_stop column predates this and ran the guard OFF (it did not
// exist), which is exactly what compare_strategy.py assumes when the column is absent.
```

## [168] TIME STOP (2026-08-05) — an EXIT lever, but kept out of cfg_exitmode for  _(only in mpc_strategy_export.pine)_

```
// TIME STOP (2026-08-05) — an EXIT lever, but kept out of cfg_exitmode for the same reason
// the min-stop guard is: that column is the two ladder DROPDOWNS, and a third meaning packed
// into it would make the decoder guess. The mode is a code, the hours are RAW (a float).
//   cfg_time_stop = Off?0 : Before TP1 only?1 : Always?2
// An export with NO cfg_time_stop column predates this and ran the lever OFF (it did not
// exist), which is exactly what compare_strategy.py assumes when the column is absent —
// never the Python default, which is also Off today but need not stay that way.
```

## [169] NO-FVG ARM GATE (2026-08-10) — `execNoGapArm`. It gates the FALLBACK ent  _(only in mpc_strategy_export.pine)_

```
// NO-FVG ARM GATE (2026-08-10) — `execNoGapArm`. It gates the FALLBACK entry only, so it can
// only ever matter on an export taken with execReqFVG OFF (cfg_bits bit 16 clear). It decides
// WHICH SETUPS EXIST on that branch, not where a limit rests, so it belongs in its own column
// rather than in cfg_bits: it is a dropdown, and packing a third state into a bit is how a
// decoder starts guessing.
//   cfg_nogap_arm = Any?0 : Sweep + RSI div?1
// An export with NO cfg_nogap_arm column predates this and ran the ORIGINAL fallback, which is
// "Any" — so that is what compare_strategy.py assumes when the column is absent. It happens to
// equal the Python default today; the assumption is about what the PINE did, never about what
// the Python defaults to, and the two must not be allowed to drift into one statement.
// ⚠ A green run at execReqFVG ON proves NOTHING about this lever — neither side enters the
// branch. Export once with execReqFVG OFF and cfg_nogap_arm 0, and once with it 1.
```

## [170] EQ/FVG COUPLING (2026-08-06) — `eqExemptFvg`. A gap sitting on an active  _(only in mpc_strategy_export.pine)_

```
// EQ/FVG COUPLING (2026-08-06) — `eqExemptFvg`. A gap sitting on an active EQH/EQL is exempt
// from the FVG cap and lives until price mitigates it, so `fvgMaxCount` bounds the ORDINARY
// gaps only. It decides WHICH GAPS EXIST, so it decides which entries fire.
//
// 🔴 THIS COLUMN EXISTS BECAUSE ITS ABSENCE COST THREE DAYS. The input defaulted ON here on
// 2026-08-03 (b1b461b) while the Python side wired no EQ engine into the FVG engine at all, so
// the two evicted different gaps — and with nothing carrying the setting, compare_strategy.py
// diffed two different strategies and reported the difference as an entry-rule bug. It took a
// bar-by-bar dump of the gap list to find: at bar 11031 of the 21,999-bar export Pine still
// held a bearish gap born 143 bars earlier and rested at its edge (4965.73) while Python,
// having FIFO-dropped it, snapped to fib 0.702 (4990.02). Same class as `execRunnerTrail` in
// 2026-07-26 and `cfg_min_stop` in 2026-07-30: a trade-affecting input with no column is
// invisible to the gate BY CONSTRUCTION, and the gate stays green while it lies.
//
// The detection constants are NOT exported — eqPivotLen / eqAtrMult / eqMax are hardcoded in
// the Pine (2 / 0.1 / 6) rather than exposed, precisely so the indicator and the strategy
// cannot draw different levels; the Python engine's defaults are the same three numbers.
// Export them the day either side makes one an input, and not before.
//   cfg_eq_exempt = 0 (off) : 1 (on)
// An export with NO cfg_eq_exempt column predates this. compare_strategy.py configures the
// bot OFF in that case, which is what those exports RAN — never the Python pin, which is on.
```

## [171] DIAGNOSTIC (temporary — pins the A+ Stage-1 arming gap vs the Python bot  _(only in mpc_strategy_export.pine)_

```
// DIAGNOSTIC (temporary — pins the A+ Stage-1 arming gap vs the Python bot at H4/
// session boundaries; remove once parity is green). Everything the arming block at
// ~3718 reads or sets, so Python's reconstructed liquidity can be diffed bar-for-bar.
// Every bar field is stored (value+1) so 0 = "none" and the packing never goes negative.
//   dbg_recent_bars = (recentSSL_bar+1) *1e6 + (recentBSL_bar+1)          [0 => none]
//   dbg_recent_src  = SSL-slot code *10 + BSL-slot code
//                     (""=0, H4=1, Day=2, Asia=3, Ldn=4, NY=5 — same order both sides)
//   dbg_sweep_bits  = newSweepL·1 + newSweepS·2 + dailyTooOldL·4 + dailyTooOldS·8 + sessionGapBar·16
//   dbg_armL_bars   = (na?0:aplusL_sweepBar+1) *1e6 + (na?0:aplusL_sosBar+1)  [0 => na]
//   dbg_armS_bars   = (na?0:aplusS_sweepBar+1) *1e6 + (na?0:aplusS_sosBar+1)
```

## [172] DIVERGENCE INTERNALS (temporary — the arm gap above traces to a bear div  _(only in mpc_strategy_export.pine)_

```
// DIVERGENCE INTERNALS (temporary — the arm gap above traces to a bear divergence
// Python fires that Pine doesn't; these expose Pine's own divergence state so the
// RSI/pivot split can be pinned). Bars now align (full history), so raw, na = -1.
//   dbg_div_bars   = lastBullDivBar (bull-fuel) *1e6-shifted + lastBearDivBar   [-1 = na]
//   dbg_div_ph     = divPhRsi   — the RSI pivot-HIGH confirmed THIS bar (na most bars)
//   dbg_div_prevhi = divPrevRsiHigh — the running "previous" RSI pivot high the gate reads
```

## [173] FIB LIVE-ANCHOR (temporary — an arm gap traces to the fib entry band; th  _(only in mpc_strategy_export.pine)_

```
// FIB LIVE-ANCHOR (temporary — an arm gap traces to the fib entry band; the gap top
// sits right on the P6 boundary and Python's band shifts for one bar. These expose
// Pine's own per-bar anchor + the two band edges the FVG-overlap gate reads, so the
// live-anchor divergence can be pinned. Raw prices, na = empty cell.
//   dbg_fib_ash / dbg_fib_asl = the live extending anchor high/low (tracks pb_extreme)
//   dbg_fib_p2  = fiboP2 (0.5, shallow band edge)   dbg_fib_p6 = fiboP6 (0.886, deep edge)
```


## [179] SCALE-IN (2026-08-17) — four columns, because an input with no column is invisible to the gate

```
// [doc 179] SCALE-IN (2026-08-17) — four columns, because a trade-affecting input with no
// cfg_* column is invisible to compare_strategy.py BY CONSTRUCTION — and the gate does not go
// quiet, it goes WRONG, diffing two different strategies and blaming whichever code the
// symptom lands in. This repo has met that exact shape three times: execRunnerTrail
// (2026-07-26), cfg_min_stop (2026-07-30) and eqExemptFvg (2026-08-06, three days and a
// misdiagnosis). All FOUR inputs are carried, not just the on/off switch: the mode decides
// WHERE the add rests, and adds/cap decide how much — configure the Python from any one of
// them wrongly and the diff is drift reported as a bug.
// ⚠ cfg_scale_adds and cfg_scale_cap are plotted RAW rather than packed. Any pack that fits
// them into one float has to round, and a silently rounded cap mis-sizes every add — the same
// reasoning the six exit numerics are already plotted raw for.
```

## [180] A resting add is counted when it FILLS, not when it is placed

```
// 🔴 `lAddN` INCREMENTS ON THE FILL. A BOS-retest add is a RESTING LIMIT, so it can sit
// unfilled for many bars, and counting it at placement would burn one of `execScaleAdds`
// on an order the market never came back for.
// The fill is detected by the position GROWING, which is unambiguous here: the block is
// gated on `strategy.position_size[1] > 0` (so the base entry's own fill cannot reach it)
// and on `lStage >= 2` (so TP1 and TP2 are already taken and no partial exit remains).
// ⚠ Placing again while one rests re-uses the SAME entry id, which REPLACES the resting
// order rather than adding a second. That is the "a fresher break supersedes an older
// limit" rule, and Pine gives it for free.
```

## [181] The order TYPE is the guarantee — BOS retest rests a limit, Trail cannot

```
// 🔴 THE AFFORDABILITY RULE SIZES AN ADD AGAINST THE PRICE IT IS BOUGHT AT. A market order
// is sized at one price and filled at the NEXT BAR'S OPEN, so anything that moves against
// you in between is size the guarantee never covered.
// MEASURED, and it broke the one property this feature was accepted for: as a market order
// the adds turned winners of +3.41R and +1.34R into losses of -2.50R and -2.15R, against an
// un-scaled worst of -2.06R over the same 182 trades.
// A resting limit closes it. The fill price is known before the order is sent, so the size
// is exact; and price that GAPS through a buy limit fills at the OPEN, i.e. BETTER than the
// limit. Every error term points the safe way.
// ⚠ The size is frozen at PLACEMENT and deliberately not refreshed while the order rests.
// Also the safe direction: the stop only ratchets favourably, so by fill time `locked` has
// grown and `perUnit` has shrunk and the resting size is smaller than what would now be
// permitted, never larger.
// ⚠ "Trail" is a MARKET rule by nature — its trigger is `close`, and a limit there would
// wait for a pullback that is the opposite of what the mode means. So Trail still carries
// the trigger-to-fill gap. It measured ZERO breaches over 182 trades because close-to-next-
// open is small, and zero observed is not the same as zero possible. Say so rather than
// letting the next reader inherit BOS retest's guarantee by association.
```

## [182] A resting add must be CANCELLED when its trade ends

```
// 🔴 A LIMIT ORDER OUTLIVES THE POSITION THAT PLACED IT. Leave one resting after the trade
// closes and it fills later on its own, opening a NEW position with no entry logic behind
// it, no stop sized for it and no setup that asked for it.
// It is deliberately a positive check on being flat rather than a hook on each exit path:
// this strategy closes on a stop, three ladder rungs, an opposite SOS and a time stop, and
// an ignore-list of exits is one new exit away from being wrong.
```

## [183] Where the scale-in adds BANK — a standing level beyond the newest add

```
// The adds had no exit of their own: they rode the base trade's trailing stop and closed
// pro-rata with its ladder. `execScaleTpMode` gives them a target of their own.
//
// TWO CONDITIONS, AND EACH IS LOAD-BEARING:
//   * the level must be UNMITIGATED — a swept level is not somewhere to aim at, it is a
//     price we are already past. Hence `not w_hMit` / `not d_hMit` / `not h4HighSwept`.
//   * it must sit BEYOND `lAddLastPx`, the price the NEWEST add was bought at, so every lot
//     the target closes is closed in profit. Banking one lot at a loss to bank another at a
//     gain is not what this input is for.
//
// It is the NEWEST add rather than the worst-priced one because Trail-mode adds fill at
// successively higher prices (the ratchet only moves one way), so the two are the same
// level — and Pine can name the newest fill via `strategy.opentrades.entry_price` without
// keeping a running extreme. MEASURED equal on the full book rather than argued.
//
// It rides on the EXISTING per-add `strategy.exit` calls as a `limit`, which makes each add
// a proper OCO bracket: stop or target, whichever price reaches first. A `na` limit is no
// limit at all, so "Ride" leaves those exits byte-identical to what they were.
//
// 🔴 `lAddN` IS NOT DECREMENTED WHEN THE ADDS BANK, and the Python side zeroes its lots in
// place rather than emptying the list for the same reason. The ladder is capped on the
// number of adds BOUGHT, so giving the slot back would let a trade add again after banking
// — a different strategy ("scale in and out repeatedly") that nothing here has measured.
//
// ⚠ MEASURED 2026-08-19 (Run 22, re-measured after the resting-order fix): every target
// LOSES to riding, in order of how often it fires — Ride 194.15R (0 banks), prev week
// 168.51R (16), prev day 157.57R (25), H4 146.09R (47). It defaults to "Prev week H/L" on
// Aaron's explicit call, and THAT DEFAULT IS UNDER REVIEW: he chose it on a 4.38R gap said
// to sit inside the strategy's 15.06R jitter, and the true gap is 25.64R, outside it.
// Session H/L is not offered — it measured worst and would need six more mirrored variables.
//
// 🔴 THE `limit` IS SET FROM THE BAR'S CLOSE AND IS LIVE ON THE NEXT BAR — which Pine gives
// you for free, and which the Python mirror initially did not. Re-resolving the level as
// price touches it made "Prev day H/L" and "H4 H/L" bank ZERO times in eight years: day and
// H4 levels die on a WICK, so the level was already gone on the exact bar the order would
// have filled. Week levels die on a CLOSE through and were immune, which is why only the
// two modes nobody was watching were broken. Do not "simplify" this to a live lookup.
```
