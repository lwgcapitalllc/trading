# mpc_d_strategy.pine — commentary

The prose that used to live inline in the Pine. Each entry is anchored from the
source by a `// [doc N]` line. Grep this file for `## [N]` to find one.

**Covers:** `mpc_d_strategy.pine`, `mpc_d_strategy_export.pine`

---

## [1] MPC D STRATEGY — "D as in dog, the dirty one" (Aaron, 2026-08-06).

```
// MPC D STRATEGY — "D as in dog, the dirty one" (Aaron, 2026-08-06).
//
// A mature trend gets shaken out against itself and then resumes. Three steps:
//   1. A trend is established and MATURE — an SOS opens it, then it prints at least one BOS.
//   2. A COUNTER-trend SOS fires. This is the shakeout: price closes through the trend's
//      last protected swing and prints a genuine LL (in an uptrend) or HH (in a downtrend).
//   3. A WITH-trend SOS fires, straight back into the original direction. THAT IS THE ENTRY.
// The stop sits beyond the extreme the counter leg reached. It is the only price in the
// sequence that carries information: through it, the shakeout was a real reversal.
//
// ⚠ THE NON-OBVIOUS PART, AND IT IS THE WHOLE IMPLEMENTATION.
// An SOS strictly ALTERNATES direction by construction — a bull SOS requires st.dir == -1
// and sets it to 1, so the next SOS can only be a bear one. "An SOS then an opposite SOS"
// is therefore ALWAYS true and can never be a trigger; every consecutive pair on every
// chart satisfies it. What actually separates this sequence from ordinary structure is an
// ASYMMETRY IN MATURITY between the two legs either side of the counter-SOS:
//   the trend being RETURNED to must have printed >= dTrendBosMin BOS (it was a trend)
//   the counter leg in between must have printed <= dCtrBosMax  BOS   (it was a shakeout)
// Drop either test and this fires on every SECOND SOS on the chart. Those two numbers ARE
// the strategy. See docs/MPC_D_STRATEGY_SPEC.md.
//
// ⚠ MEASURED ON AARON'S OWN FOUR EXAMPLES: entering at the return-SOS CLOSE with the stop
// at the counter extreme gives roughly 0.5R to 1.2R. All four were directionally right and
// only one cleared 1R. The cause is structural — an SOS confirms at the TOP of the reclaim
// leg, so the entry is at the expensive end and the stop is the whole leg away. That is the
// same problem A+ solves by resting a limit on the retrace instead of buying the break, so
// "Retrace" is offered as an entry mode. Which one pays is a MEASUREMENT, not an argument.
// 🔴 THE DEFAULT IS NOW "VWAP side" (Aaron, 2026-08-06), OFF A MARKED-UP CHART, AND IT
// MOVES EVERY RESULT. He marked the trade this mode exists to catch — XAUUSD 19-23 Aug:
// bullish structure, a bear SOS printing the LL at ~3,996 (the shakeout), price basing
// along VWAP, then a close back above it at ~4,012, stop behind the LL, run to 4,166.
// `execSlMode` stays "Sweep extreme", which is that stop. ⚠ Pin "SOS close" with rungs
// 30/30/40 and TP3 = 3 to reproduce the 218-trade / +14.03R baseline of the same morning.
//
// The structure engine below (type SMCStructure through the external execution block) is
// lifted BYTE-FOR-BYTE from indicators/engines/structure_engine.pine, itself the external half of
// mpc_assistant.pine. It is not re-implemented here — a second structure engine is
// forbidden by CLAUDE.md and would be the thing that silently drifts.
//
// ⚠ EVERYTHING BELOW THE ENGINE FOLLOWS mpc_strategy.pine's CONVENTIONS (Aaron, 2026-08-06).
// Same five input groups — "D Setup" for the sequence gates (as A+ uses "A+ Setup"),
// "Strategy Execution" for everything that decides what a trade DOES, plus "D Debug",
// "Result Stats" and "Diagnostic Log". Same d-prefix / exec-prefix split, same "   ↳ " for a
// sub-input with `active =` on its parent, same tooltip rule: what it does, what ON vs OFF
// means, and the one fact that changes the decision — never a measurement essay, those live
// in the CLAUDE.md files. The exit ladder is a PORT of that file's, not a lookalike:
// f_dRatchet is f_swingRatchet unchanged, and the staged stop, the TP2 floor modes, the
// three trail methods, the time stop and the close-on-opposite-SOS all keep their shapes and
// their defaults. Anywhere this file deliberately diverges, the divergence is commented at
// the site — see the exit-rung re-issue guard.
// ⚠ THIS IS A strategy(), NOT AN indicator(). That is what puts a Properties tab and a
// Strategy Tester on the chart; an indicator has neither, which is what the first build of
// this file got wrong.
// ⚠ process_orders_on_close is ON so the "SOS close" entry fills at the CLOSE of the bar
// that confirmed the SOS — the price the marker draws and the price the four reference
// examples were measured at. With it off the fill is the NEXT bar's open, and every R in
// docs/MPC_D_STRATEGY_SPEC.md would then be describing a different trade.
// ⚠ margin 0.2% = 500x, the same pin as mpc_strategy.pine. Gold near $4,000 under a
// percent-of-equity risk model sizes past a cash account, and TradingView REJECTS an order
// it cannot margin rather than shrinking it — so leverage set too low shows up as a strategy
// that quietly takes fewer trades, never as an error.
// ⚠ max_bars_back IS NOT COSMETIC AND MUST NOT BE DROPPED. `dVwapSlope` reads
// `dVwap[execVwapSlopeBars]` — a history offset taken from an INPUT, not a literal — and Pine
// sizes each series' history buffer by watching the offsets it sees on the first bars. At the
// shipped 4 it would size for 4, so raising the slope input toward its own maxval of 200 would
// throw "the requested historical offset is beyond the historical buffer's limit" AT RUNTIME,
// on a knob a reader turns precisely while tuning. 300 covers the whole declared range.
// The failure is the shape this repo keeps recording: correct at the default, broken the first
// time somebody uses the lever the default exists to be tuned away from.
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

## [3] SMC SETTINGS (hardcoded)

```
//============================================================
//  SMC SETTINGS (hardcoded)
//============================================================
```

## [4] MARKET STRUCTURE — input selection (mirrors mpc_assistant.pine's GRP_STR

```
//============================================================
//  MARKET STRUCTURE — input selection (mirrors mpc_assistant.pine's GRP_STRUCT)
//============================================================
```

## [5] Swing-point labels are hidden by making their text transparent, not by s

```
// Swing-point labels are hidden by making their text transparent, not by skipping
// their creation. The label objects still exist and the engine's state is untouched,
// so structure tracking, fibs, OBs and the table behave identically either way.
```

## [6] SMC STRUCTURE TYPE

```
//============================================================
//  SMC STRUCTURE TYPE
//============================================================
```

## [7] Neither an active pullback high nor a confirmed ASH was available to

```
                // Neither an active pullback high nor a confirmed ASH was available to
                // promote — use the actual highest point since the last confirmed low so
                // a genuine swing high still gets confirmed instead of silently vanishing.
```

## [8] EXECUTION — EXTERNAL STRUCTURE

```
//============================================================
//  EXECUTION — EXTERNAL STRUCTURE
//============================================================
// External structure engine — majorLength=15, blue/red, prefix ""
```

## [9] EXECUTION — INTERNAL STRUCTURE

```
//============================================================
//  EXECUTION — INTERNAL STRUCTURE
//============================================================
// Internal structure — Step 2: pullback tracking to confirm iSH / iSL
```

## [10] D SETUP — the sequence gates

```
//============================================================
//  D SETUP — the sequence gates
//============================================================
// Named and grouped after mpc_strategy.pine: the SETUP owns its own group with a d-prefix
// (as A+ uses aplus*), and everything that decides what a trade DOES lives under
// "Strategy Execution" with an exec- prefix. Keeping the two apart is what lets a gate be
// tuned without touching the trade, and read without hunting.
// The two gates that ARE the strategy — see the header on why an opposite-direction SOS
// pair is not a signal by itself.
// Deliberately NOT 0. Two of the four reference examples show a counter leg that broke
// structure in its own direction before turning back, so a zero refuses half of them.
// In BARS, so it does NOT transfer between timeframes. 400 is ~4 days on 15m, ~33 hours on
// 5m. The reference examples ran from about 3 hours to about 33.
```

## [11] STRATEGY EXECUTION

```
//============================================================
//  STRATEGY EXECUTION
//============================================================
// ⚠ DECLARATION ORDER IS NOW FROZEN. TradingView keys a chart's saved input values off the
// order of declaration within each TYPE, so inserting a string or a float above an existing
// one silently resets every later input of that type on every chart running this script.
// Add new inputs at the END of their type's run, never in the middle. mpc_strategy.pine
// records the same trap at its own time-stop pair.
```

## [12] ── WHERE THE STOP GOES. Four anchors, and they are genuinely different t

```
// ── WHERE THE STOP GOES. Four anchors, and they are genuinely different trades. ──
//   SWEEP EXTREME    — the high/low the shakeout reached. The honest invalidation: through
//                      it, the shakeout was a real reversal. Widest, so the smallest
//                      position and the fewest stop-outs.
//   COUNTER-SOS LINE — the level the counter-trend SOS BROKE and price then reclaimed.
//                      Tighter, and clean in its own right: back below it and the reclaim
//                      is void. It sits INSIDE the shakeout, so a wick back in stops you
//                      out where the sweep stop holds.
//   BETWEEN THE TWO  — slide between them. 0% = the SOS line, 100% = the sweep extreme.
//   % OF ENTRY-TO-SWEEP — ignores structure entirely. For when both structural stops are
//                      simply too wide to size against.
// ⚠ A tighter stop is NOT a better trade. It buys a bigger position on the same risk budget
// and pays for it in stop-outs on setups that later worked, and those do not cancel at a
// fixed rate — which wins is a measurement per instrument and timeframe.
```

## [13] ⚠ THE MINIMUM STOP GUARD IS ON BY DEFAULT AND MUST STAY THAT WAY WHILE A

```
// ⚠ THE MINIMUM STOP GUARD IS ON BY DEFAULT AND MUST STAY THAT WAY WHILE ANY TIGHT STOP
// ANCHOR IS REACHABLE. Size is risk DIVIDED BY stop distance, so a stop that collapses onto
// the entry does not risk less — it builds an enormous position. This file ships three
// anchors that can land arbitrarily close to the entry ('% of entry-to-sweep' at 5% is a
// twentieth of the leg), which is exactly the shape that detonated A+ Run 4 and BOS Run 1
// (worst trade -14.33R). It is an ENTRY FILTER: a refused setup is skipped, never resized.
```

## [14] ⚠ A RUNG SIZED 0% IS SKIPPED, NEVER PLACED. strategy.exit() reads qty_pe

```
// ⚠ A RUNG SIZED 0% IS SKIPPED, NEVER PLACED. strategy.exit() reads qty_percent = 0 as
// "unspecified" and falls back to closing the WHOLE position at that limit — the exact
// opposite of "bank nothing here", and it is REACHABLE now that these ship at 0 — the
// guard is the only thing between this default and every trade closing whole at TP1.
// 🔴 BOTH RUNGS WENT 30 → 0 AND TP3 3.0 → 0 (Aaron, 2026-08-06), because the ladder was
// the binding constraint, not the entry. Measured over 8.3 years the largest winner was
// +2.11R against the rungs' own arithmetic ceiling of 0.3x1 + 0.3x2 + 0.4x3 = 2.10, with
// 16 trades sitting exactly on it. Re-measured on Aaron's own marked chart: 1R is $16,
// the move was worth 9.62R, and the shipped ladder took 2.10R of it — 7.53R left on the
// table on the one trade the strategy exists to catch. D pairs a CONTINUATION premise
// with a scale-out exit; A+ ships 0/0 for exactly this reason, because its money is in
// the tail. ⚠ The TP1 and TP2 PRICES still do their work at 0% — TP1 stages the stop to
// breakeven and TP2 hands the runner to the trail — so execTp1R/execTp2R must stay > 0.
```

## [15] ── THE RUNNER TRAIL, ported from mpc_strategy.pine's exit ladder ──

```
// ── THE RUNNER TRAIL, ported from mpc_strategy.pine's exit ladder ──
// Same three methods and the same default. Structure alone parks the stop at the last
// confirmed swing, which BREATHES with the trend but lags — in a strong leg the swing ends
// up a long way behind and that is where a runner's give-back comes from. The ratchet keeps
// the same anchor and climbs one step per step of favourable move, so it is never LOOSER
// than the plain structure trail, only equal or tighter.
```

## [16] D DEBUG

```
//============================================================
//  D DEBUG
//============================================================
```

## [17] RESULT STATS

```
//============================================================
//  RESULT STATS
//============================================================
```

## [18] VWAP — the pro-trend side test

```
//============================================================
//  VWAP — the pro-trend side test
//============================================================
// ⚠ THE DECLARATION-SLOT NOTE THAT SAT HERE IS OBSOLETE. It said these inputs had to stay
// at the end of the file — after `execDiagLog`, the last input of every type — because
// moving them up into the exec panel would shift every later bool and int and silently
// reset them on every tuned chart, so the paste needed no "Reset settings to defaults".
// That was true until 2026-08-12, when every input in this file moved into one consolidated
// panel block and `execDiagLog` was deleted with the diagnostic log. The pass resets saved
// values once, knowingly; there is no slot left here to protect.
//
// WHAT THIS IS FOR (Aaron, 2026-08-06). The D sequence's entry is the with-trend SOS, and
// an SOS confirms at the TOP of the reclaim leg — so the entry is at the expensive end and
// the stop is the whole leg away. That is measured, not suspected: the four reference
// examples returned 0.5R to 1.2R, and the first full-history run capped every winner at the
// ladder's arithmetic ceiling of 2.11R against full -1R losers. VWAP is the proposed way in
// EARLIER: after the shakeout, take the trade when the close is back on the pro-trend side
// of VWAP, without waiting for the SOS to confirm it.
//
// ⚠ IT IS A STATE TEST, NOT A CROSS EVENT, AND THAT IS AARON'S EXPLICIT CALL. "If it is
// already supported by the VWAP and the VWAP is pro-trend, and it does not have to cross
// back over, take those trades." So a shakeout that dipped under VWAP and reclaimed it and
// a shakeout that never lost it are the SAME signal — both are simply "the close is on the
// trend's side of the line". Writing this as `ta.crossover` would silently refuse every
// setup of the second kind, which is half of what was asked for.
// Drawn by DEFAULT, and that is a decision rather than a convenience. The moment a rule reads
// VWAP, "the VWAP" becomes a claim about a specific line, and this repo's most-repeated
// defect is two places disagreeing about one number while both look right. Showing the exact
// series the gate reads makes the two impossible to confuse on the chart.
// ── THE RECLAIM (Aaron, 2026-08-06) — this is what makes it the setup on the chart ──
// ⚠ THE "MUST STAY AT THE END OF THE FILE" NOTE HERE IS OBSOLETE, and is replaced rather
// than deleted. `execVwapReclaim` was appended after the last `input.bool` so that adding
// it shifted no saved chart value. Correct until 2026-08-12, when every input moved into
// one consolidated panel block — it now lives in `5 · Entry`, with the entry mode it
// modifies, and that pass resets saved values once by design.
//
// WHAT IT FIXES, and it is the difference between the picture and what the file shipped:
// "VWAP side" tested only whether the close was CURRENTLY on the trend's side of the line.
// A 15m shakeout SOS very often prints while price is still above VWAP, so the state was
// already true on the bar after the counter-SOS and the trade opened THERE — no basing, no
// reclaim, nothing that looks like the setup. Every bar for the next dCtrBarsMax got the
// same free look, so a trade could also open a day later on an unrelated bar that happened
// to close on the right side.
// The setup is a ROUND TRIP: price must LOSE the line (base on it) and then CLOSE BACK
// across it. That is two events on two different bars, so it needs a latch.
//
// ⚠ A LATCH, NOT ta.crossover, and the distinction is load-bearing. A crossover is true on
// exactly ONE bar, so any other gate refusing that bar — a stop too tight, a position still
// open — would lose the setup for good. The latch remembers that VWAP was lost and lets the
// entry fire on the first bar the rest of the gates also agree, which is what "wait for the
// reclaim" actually means.
```

## [19] THE ANNOTATION PALETTE — copied from mpc_strategy.pine, never chosen her

```
//============================================================
//  THE ANNOTATION PALETTE — copied from mpc_strategy.pine, never chosen here
//============================================================
// ⚠ EVERY COLOUR A TRADE IS DRAWN IN IS THE A+ BOT'S (Aaron, 2026-08-12): "all those colors
// are not consistent across all the pines. They should be the same colors. Use MPC, the A+
// strategy as a standard." One result means one colour on every chart in this repo, so a
// reader moving between strategies never has to re-learn what green is. **Change a value
// here only by changing `mpc_strategy.pine` first and copying it down.**
//
// 🔴 THIS FILE WAS USING THE WRONG ONE OF A+'s TWO PALETTES, WHICH IS THE WHOLE REASON IT
// LOOKED DIFFERENT. A+ carries two and they are not interchangeable:
//   the TABLE palette   #00E676 / #FF5252 — bright, for the status panel's bull/bear text
//   the POSITION palette #26A69A / #EF5350 — every trade drawing
// This file applied the TABLE palette to its TRADES, so a D winner drew in the green A+ uses
// for a table row and never in the green A+ uses for a winner. Both palettes are still here;
// what changed is only which one a TRADE reads.
```

## [20] ⚠ GREY WHILE THE TRADE IS STILL OPEN, and that is a rule rather than a s

```
// ⚠ GREY WHILE THE TRADE IS STILL OPEN, and that is a rule rather than a spare colour: the
// result is not known yet, and colouring the callout by DIRECTION — which this file used to
// do — is a claim the chart cannot back up. Direction is already on the label in words and
// under the candle as a triangle.
```

## [21] ⚠ A+ HAS NO "TARGET NOT REACHED YET" STATE, because it draws its bands a

```
// ⚠ A+ HAS NO "TARGET NOT REACHED YET" STATE, because it draws its bands at real FILLS on
// the close bar. This file draws all three upfront and brightens each one as it is reached,
// which is extra information and is kept — so an unreached block is the same HUE, one step
// fainter than any A+ rung. Faint = not reached; the three A+ depths = reached.
```

## [22] A+'s solid entry-marker pair, and it is DRAWN here as of 2026-08-12 — th

```
// A+'s solid entry-marker pair, and it is DRAWN here as of 2026-08-12 — the triangles under
// each fill. Solid (@0), unlike every other trade colour, because these are the one annotation
// that has to be findable when the result box is a thin scratch.
```

## [23] ── The STATE PANEL palette — A+'s JARVIS table colours, and correct wher

```
// ── The STATE PANEL palette — A+'s JARVIS table colours, and correct where they are used. ──
// Deliberately kept APART from the trade colours: a table row is not a trade result, and
// merging the two is the exact mistake this block exists to undo.
```

## [24] D SEQUENCE — state machine

```
//============================================================
//  D SEQUENCE — state machine
//============================================================
// dTrendDir / dTrendBos describe the trend the LAST SOS killed. At the moment the NEXT SOS
// is checked they still hold that value, which is exactly the trend TWO SOS back — the one
// the sequence would be returning to. That one-SOS lag is the whole trick; see the header.
```

## [25] Running extremes of the leg since that SOS. dLegLo/dLegHi are the leg's 

```
// Running extremes of the leg since that SOS. dLegLo/dLegHi are the leg's own extreme (the
// sweep anchor); dRclHi/dRclLo are the RECOVERY off it, and they RESET every time the
// extreme is exceeded — so at the entry they describe the reclaim leg alone rather than the
// whole swing, which is what a retrace entry has to be measured against.
```

## [26] The PRICE the last SOS broke — the horizontal structure line drawn on th

```
// The PRICE the last SOS broke — the horizontal structure line drawn on the chart at that
// break. Carried on the same one-SOS lag, so at the entry it still holds the level the
// COUNTER-SOS took out, which is what the "Counter-SOS line" anchor uses. It is the
// engine's own number (st.bull_bos_high / st.bear_bos_low), never re-derived from prices.
```

## [27] ⚠ ONE ENTRY PER SEQUENCE, AND WITHOUT THIS THE VWAP MODE TRADES THE SAME

```
// ⚠ ONE ENTRY PER SEQUENCE, AND WITHOUT THIS THE VWAP MODE TRADES THE SAME SHAKEOUT OVER
// AND OVER. The SOS entry is self-limiting — an SOS fires on one bar, so it can only fire
// once. The VWAP test is a STATE, true on every bar for as long as price stays on that side
// of the line, so the only thing stopping a re-entry is `bBusy`, and `bBusy` goes false the
// moment the trade closes. A sequence that stopped out would immediately re-enter at a worse
// price, and keep doing it until the bar cap expired. Released only by the shift below.
```

## [28] Has price CLOSED on the WRONG side of VWAP since the counter-SOS — the f

```
// Has price CLOSED on the WRONG side of VWAP since the counter-SOS — the first half of the
// reclaim. Latched once, cleared only by the shift below, so the two halves may land any
// number of bars apart: price loses the line on Monday's shakeout and takes it back on
// Tuesday's open, and that is still one round trip. See execVwapReclaim for the reasoning.
// It is tracked UNCONDITIONALLY, whatever execVwapReclaim is set to — a latch that only
// runs while its own switch is on cannot be switched on mid-chart without lying about the
// bars it never watched, and the state panel reads it either way.
```

## [29] A BOS that is NOT an SOS. The engine sets bull_bos on every bull_sos bar

```
// A BOS that is NOT an SOS. The engine sets bull_bos on every bull_sos bar as well, so this
// guard is load-bearing — without it every SOS would count itself as a continuation of the
// trend it just started, and dCurBos could never read 0.
```

## [30] ⚠ THE SESSION VWAP, AND IT IS DELIBERATELY THE ONE ON AARON'S CHART.

```
// ⚠ THE SESSION VWAP, AND IT IS DELIBERATELY THE ONE ON AARON'S CHART.
// `ta.vwap(hlc3)` is the single line mpc_assistant.pine draws (its line 2274) and the one
// engines/vwap/ is the canonical Python port of — session-anchored, re-anchored at the
// trading-day open, volume-weighted. Anchoring a private VWAP at the shakeout instead would
// be a SECOND VWAP implementation, which CLAUDE.md forbids outright, and it would also not
// be the line the request was about: "already supported by the VWAP" describes a level that
// has been sitting under price, which an anchor placed at the shakeout cannot be.
// ⚠ It needs the bar's VOLUME. On XAUUSD that is tick volume, which is what Pine reads, so
// this is free here — but a symbol with no volume data makes ta.vwap raise rather than
// return na, and the whole script dies with it.
// ⚠ IT RESETS DAILY, AND THE SHAKEOUT CAN OUTLIVE THE RESET. dCtrBarsMax allows 133 bars
// (~33h on 15m), so a sequence may straddle the 18:00 New York roll and be judged against a
// VWAP anchored AFTER its own shakeout began. That is not a bug to be fixed here — it is
// what the line on the chart actually does, and a filter that silently used a different
// VWAP from the one being looked at would be the worse failure.
```

## [31] The pro-trend side test, as ONE helper so the entry mode and the filter 

```
// The pro-trend side test, as ONE helper so the entry mode and the filter can never come to
// different answers about the same bar. `dir` is the trade's direction, not the chart's.
// ⚠ A `na` VWAP (no volume yet on the session's first bar) returns FALSE, never true —
// "cannot ask" and "no" must not be the same value, and of the two available answers the
// safe one for a gate is the refusal. It costs at most the first bar of a session.
// ⚠ THE SLOPE IS TAKEN OUT HERE, AT GLOBAL SCOPE, AND MUST NOT BE MOVED INSIDE THE HELPER.
// `dVwap[execVwapSlopeBars]` is a history reference, and the helper is called from inside
// two conditional blocks — a bar where neither runs would not evaluate it. Reading a series'
// history on some bars and not others is the shape Pine gives inconsistent answers for, and
// it fails as a wrong NUMBER rather than an error. Computed unconditionally, the helper is
// left as pure arithmetic over globals and is safe to call from anywhere.
```

## [32] ⚠ The line BREAKS at each trading-day anchor on its own — ta.vwap return

```
// ⚠ The line BREAKS at each trading-day anchor on its own — ta.vwap returns na across the
// reset — which is correct and is why this is a plot() rather than a polyline. It is also
// the visible proof of the daily-reset caveat noted above: where the line restarts is where
// a shakeout's VWAP stopped being the one it began under.
```

## [33] DRAWING — object pools

```
//============================================================
//  DRAWING — object pools
//============================================================
// A FIXED STRIDE of five boxes and five labels per TRADE: the shakeout, the risk block and
// three reward blocks; the entry callout and one marker per target, plus a leader line. An
// object that is switched off or not yet earned is created TRANSPARENT rather than skipped,
// because the fixed stride is what lets the oldest trade be evicted as one unit — a variable
// one splits a trade across an eviction and leaves orphaned blocks explaining nothing.
// ⚠ Everything is drawn at the FILL, not at the signal. Under "Retrace" the two are
// different bars, and a position block starting before the position existed would be
// drawing a trade nobody was in.
```

## [34] D SEQUENCE — the fire, and why a setup was refused

```
//============================================================
//  D SEQUENCE — the fire, and why a setup was refused
//============================================================
// Reason PRECEDENCE — the first gate that would refuse the setup is the one reported, so a
// tag can never blame a downstream gate for an upstream refusal.
//   8 account bust (first — it refuses everything, so no later reason is the real one)
//   1 direction off · 2 trend too young · 3 shakeout became a trend · 4 shakeout stale
//   9 wrong side of VWAP · 5 stop too tight · 6 stop on the wrong side · 7 already in a position
// ⚠ 9 is NUMBERED last and RANKED fifth, and the two are independent on purpose. The number
// is a wire format — `px_blk` in the export twin and the B| log lines carry it, and an
// archived export must keep decoding the way it did the day it was taken, so an existing
// code can never be renumbered. Its POSITION in the chain is just which reason gets reported
// when several apply, and VWAP belongs with the setup gates (2/3/4) rather than with the
// sizing gates (5/6), because it describes the setup and not the order.
// ⚠ Code 9 is raised by the FILTER only (execVwapReq, on the SOS-close and Retrace modes).
// Under "VWAP side" the test is the TRIGGER rather than a gate, so a bar on the wrong side
// is not a refused setup — it is a bar where no setup exists yet, and reporting it would
// write one refusal per bar for the whole window and drown the log it was meant to serve.
// ── Log formatters ──
// `na` renders as an EMPTY field, never as "NaN" and never as 0. A parser has to be able to
// tell "this value did not exist" from "this value was zero", and str.tostring(na) gives
// "NaN" which reads as neither. Same rule the export columns follow.
```

## [35] The shakeout's own geometry, handed to the execution block so the shaded

```
// The shakeout's own geometry, handed to the execution block so the shaded box can be drawn
// at the FILL rather than here. Under "Retrace" the fill can be many bars later, by which
// time dSosBar and the leg extremes have been reset by the next SOS.
```

## [36] ── The CANDIDATE record, set for EVERY candidate — fired or refused ──

```
// ── The CANDIDATE record, set for EVERY candidate — fired or refused ──
// These exist so the diagnostic log can carry, for each setup the sequence ever saw, the
// three gate INPUTS and the geometry the entry was priced off. They are read at decision
// time, before the unconditional shift at the bottom of the block overwrites them, and
// they are per-bar (not `var`) so a stale one can never be logged against a later bar.
// ⚠ Write-only bookkeeping: nothing below reads the six dCand* fields to make a decision.
// dCandDir, added beside them, is the ONE exception and is read by the tag and the log.
// ⚠ dCandDir REPLACES reading `st.bull_sos` to decide a candidate's direction, and that
// substitution is load-bearing rather than tidy. The block tag and the B| log line both used
// to infer the side from the SOS that fired on the same bar — which is correct only because
// every candidate USED to arrive on an SOS bar. A VWAP-side candidate does not, so on those
// bars `st.bull_sos` is false and every candidate, long or short, would have been drawn and
// logged as a SHORT. Silent, and wrong in exactly the half of the cases nobody checks.
```

## [37] "Ready" is okDir ALONE — the one structural fact the sequence is built o

```
    // "Ready" is okDir ALONE — the one structural fact the sequence is built on, that this
    // SOS returns to the trend from two SOS back. Every other gate is a CHOICE, and those
    // are precisely what the block tag exists to report. Folding any of them into ready
    // would hide the refusals worth seeing.
    // ⚠ "VWAP side" takes the sequence OUT of this block entirely — it is a mode, not an
    // extra chance. Letting the with-trend SOS fire as a fallback when the VWAP entry never
    // triggered would blend two entry models into one column of results, and the whole
    // reason both exist is to be measured against each other.
```

## [38] The counter-SOS's own broken level, still un-overwritten at this instant

```
        // The counter-SOS's own broken level, still un-overwritten at this instant. It is
        // always on the far side of the entry and always inside the sweep — the counter-SOS
        // bar closed THROUGH it and then went further — so "Between the two" interpolates
        // in a known direction and cannot invert.
```

## [39] The minimum stop floor. Computed from the COUNT of the distance rather t

```
        // The minimum stop floor. Computed from the COUNT of the distance rather than by
        // sizing first and checking after — a guard that has to build the thing it guards
        // against IS the event. ATR is read from a global series, never inside a branch.
```

## [40] ⚠ THE ACCOUNT CAN BE GONE, AND UNGUARDED THAT KILLS THE WHOLE RUN.

```
        // ⚠ THE ACCOUNT CAN BE GONE, AND UNGUARDED THAT KILLS THE WHOLE RUN.
        // Size is equity x risk% / distance. Once equity goes negative the quotient does
        // too, and TradingView does not skip a negative-qty order — it ABORTS THE SCRIPT
        // ("Invalid `qty` value (-0.1) in the `strategy.entry()` call"), so the Strategy
        // Tester shows no report at all and the blow-up that caused it is invisible.
        // Found 2026-08-06 on the first full-history run: at 10% risk from 2020 the account
        // busts partway through, and the only symptom was an error banner about qty.
        // Reported as a refusal instead, FIRST in the precedence chain — a bust account
        // refuses every setup, so naming any later gate would be describing a decision that
        // was never reached.
```

## [41] The VWAP FILTER. Read on the entry bar, because that is the bar whose cl

```
        // The VWAP FILTER. Read on the entry bar, because that is the bar whose close the
        // question is about. Inert unless switched on, so the 2026-08-06 baseline is
        // unmoved — and deliberately NOT applied when the mode is "VWAP side", where the
        // same test is the trigger and this block does not run at all.
```

## [42] Every candidate carries its gates and its geometry, whatever the verdict

```
        // Every candidate carries its gates and its geometry, whatever the verdict. A
        // refusal with no numbers attached cannot be re-priced offline, and re-pricing the
        // refusals is the whole reason the gates are tunable.
```

## [43] ── The first half of the reclaim: did price LOSE the line ──

```
// ── The first half of the reclaim: did price LOSE the line ──
// Runs AFTER the shift on purpose, so on an SOS bar it reads the direction that bar just
// established rather than the one it killed. That ordering is what lets the shakeout's own
// SOS candle count as the start of losing VWAP, which is usually exactly where it starts.
// Evaluated on EVERY bar, including SOS bars, because a round trip is a fact about price
// and not about which bar happens to carry a structure event.
```

## [44] ── THE VWAP-SIDE ENTRY: the sequence taken WITHOUT waiting for the with-

```
// ── THE VWAP-SIDE ENTRY: the sequence taken WITHOUT waiting for the with-trend SOS ──
// This is the only block in the file that can open a trade on an ORDINARY bar, and that is
// the entire point of it — the with-trend SOS confirms at the top of the reclaim leg, so
// waiting for it is what makes the entry expensive and the stop wide.
//
// ⚠ IT IS SKIPPED ON EVERY SOS BAR, and the reason is the shift directly above. By the time
// this runs on such a bar the shift has already executed, so dTrendDir describes the trend
// that SOS just KILLED — the opposite side — and the leg extremes have been reset to this
// bar's own high and low. Evaluating here would arm a trade against the move that just
// confirmed, sized off a one-bar leg. On every other bar the state is exactly what the SOS
// path would read, which is what lets both paths share one gate chain.
//
// ⚠ WHAT KEEPS IT FROM ARMING BACKWARDS IS dTrendBosMin, not a check of its own. After a
// with-trend SOS the shift sets dTrendBos to the SHAKEOUT's BOS count, which is 0 or 1 by
// construction — so at the shipped dTrendBosMin = 1 a bare shakeout cannot pose as a mature
// trend. At dTrendBosMin = 0 that protection is gone and this will happily arm counter to a
// trend that has just resumed. That setting was already documented as loose; it is LOOSER
// here than it is on the SOS path, because this path gets a fresh look every bar.
```

## [45] The trigger. Unlike the SOS path there is no event to hang a candidate o

```
    // The trigger. Unlike the SOS path there is no event to hang a candidate on, so a bar on
    // the wrong side of the line is simply not a candidate — see the note on code 9 above
    // for why it is not reported as a refusal.
    // ⚠ `dVwapLost` is the RECLAIM half and it is what makes this the setup on the chart
    // rather than "the first bar after the shakeout that happens to close on the right side".
    // A sequence that never loses VWAP now takes no trade at all, which is correct: there was
    // no pullback, so there was nothing to enter on. See execVwapReclaim.
```

## [46] ⚠ THE MINIMUM-STOP GUARD MATTERS MORE ON THIS PATH THAN ON ANY OTHER IN 

```
        // ⚠ THE MINIMUM-STOP GUARD MATTERS MORE ON THIS PATH THAN ON ANY OTHER IN THE FILE,
        // and it is worth being explicit about why. Entering early means entering CLOSE to
        // the sweep extreme — that is the benefit — and the stop is anchored at that same
        // extreme. So the better this entry is, the smaller `dist` gets, and `qty = risk /
        // dist` grows without limit as it shrinks. On the SOS path the whole reclaim leg
        // sits between the entry and the stop and the hazard is structurally rare; here it
        // is the NORMAL case. Do not run this mode with execMinStopMode = "Off".
```

## [47] ── The blocked-setup tag ──

```
// ── The blocked-setup tag ──
// Bounded by debugDays so an old history does not become a wall of pink. Every real trade
// keeps its callout however old — only these are trimmed.
```

## [48] Plain ASCII, no quotes and no newlines, so it drops straight into a webh

```
// Plain ASCII, no quotes and no newlines, so it drops straight into a webhook body.
// Fires on BAR CLOSE: the engine's break test reads the LIVE close, so an SOS can appear and
// vanish intrabar, and an alert that did that would be worse than no alert at all.
```

## [49] EXECUTION

```
//============================================================
//  EXECUTION
//============================================================
// One position at a time (pyramiding = 0). The sequence fires a few times a month at the
// default gates, so a second concurrent trade would almost always be the same swing read
// twice rather than a genuinely separate setup.
```

## [50] ⚠ tMaxAdv is the mirror of tMaxFav and is READ BY NOTHING except the log

```
// ⚠ tMaxAdv is the mirror of tMaxFav and is READ BY NOTHING except the log. It exists
// because the trade list reports a trade's best and worst price but never their ORDER, and
// the order is what decides whether an earlier stop would have clipped a winner or saved a
// loser. Tracked on the same guarded bar range as tMaxFav for the same reason: the fill bar
// of a resting limit is approached from the wrong side, so its extremes are not the trade's.
```

## [51] ── The CLOSE: score the trade in R, repaint the callout, honour the keep

```
// ── The CLOSE: score the trade in R, repaint the callout, honour the keep filter ──
// 🔴 THIS BLOCK MUST RUN BEFORE `if dFired`, AND IT USED TO RUN AFTER IT.
// That ordering froze the strategy dead on 2020-05-07 and it stayed frozen for the
// remaining SIX YEARS of an eight-year run — found 2026-08-06 in the trade list, not by
// the code reading. The shape is a SAME-BAR FLIP: a position closes and the next sequence
// fires on the very same bar. When that happened, `if dFired` set the new trade up first
// (tDir := 1, entry placed), and then this block — sitting at the bottom of the file, and
// correctly seeing `position_size == 0` — scored the OLD trade and finished by resetting
// `tDir := 0`. That wiped the direction of a trade that had just been placed.
// From the next bar the FILL block and the whole exit block are both gated on `tDir != 0`,
// so NEITHER EVER RAN AGAIN: the position sat open with no stop, no targets and no time
// stop, `bBusy` was permanently true, and every later setup was refused with code 7.
// ⚠ It fired ONCE in eight years — exactly one same-bar flip in the entire history — and
// that one occurrence cost 6 of the 8 years. A path taken on 1 bar in 200,000 is still a
// path, and the ordering of two blocks is not a detail.
// ⚠ Scoring must ALSO precede the setup for a second reason: `if dFired` overwrites
// tRiskUsd and tNpAt, which are exactly what the R grade divides by. Run after it and the
// closing trade is scored against the NEW trade's risk — a wrong number in the label, the
// log and the Result Stats, silently.
```

## [52] The LEADER LINE is recoloured with the label, which this file did not do

```
    // The LEADER LINE is recoloured with the label, which this file did not do — it left the
    // line grey on every closed trade while the label turned green or red. A+ repaints both,
    // and it has to: the line is what ties the callout to the candle it belongs to, so a
    // grey line running into a red label reads as two annotations rather than one.
```

## [53] ── The TRADE record. ONE line per trade, pipe-delimited, everything on i

```
    // ── The TRADE record. ONE line per trade, pipe-delimited, everything on it. ──
    // It replaces the old ENTRY + RESULT pair, which is not tidying: Pine Logs keeps only
    // the most recent N messages, so on an eight-year run the front of the paste is what
    // gets dropped. Halving the lines halves how much history is lost, and the entry facts
    // are worth nothing without the outcome anyway.
    // ⚠ mfeR / maeR are the reason this exists. The Strategy Tester's trade list reports a
    // trade's best and worst price but never their ORDER, and the order is exactly what
    // decides whether staging the stop earlier would have protected a loser or clipped a
    // winner. These two are measured from the FILL forward, so they answer it.
```

## [54] Clear any resting order first. A previous Retrace entry may still be on 

```
    // Clear any resting order first. A previous Retrace entry may still be on the book, and
    // if this setup is the OTHER way round the two ids differ — so without this the strategy
    // would sit with a live buy limit and a live sell limit at once and take whichever price
    // reached first, which is not a decision anything in here made.
```

## [55] Retrace rests a LIMIT at the fib; SOS close is a market order that fills

```
    // Retrace rests a LIMIT at the fib; SOS close is a market order that fills at this bar's
    // close because of process_orders_on_close.
    // ⚠ `q > 0` is belt-and-braces on top of block code 8, and it is not redundant: code 8
    // only guards the "Risk % of equity" path, while "Fixed contracts" reaches here with a
    // bust account, and a na equity would slip past a `>= 0` test. A non-positive qty does
    // not skip the order — it ABORTS THE SCRIPT and destroys the whole report, so the cheap
    // check is worth having twice.
```

## [56] Kill a resting limit that never filled. Three ways it dies and all three

```
// Kill a resting limit that never filled. Three ways it dies and all three matter: price ran
// away and never came back, price reached the STOP first (the setup was invalidated before it
// was ever entered), or a newer SOS superseded the sequence. Without these the order stays on
// the book and can fill days later on a move that has nothing to do with this setup.
// bar_index > tOrdBar excludes the bar the order was PLACED — under process_orders_on_close a
// market entry has not filled yet when this runs on that bar.
```

## [57] No `fdc` any more. The open callout was coloured by DIRECTION here and A

```
    // No `fdc` any more. The open callout was coloured by DIRECTION here and A+ paints it
    // GREY until the result is known — see POS_OPEN. Direction is already in the label text.
    // The shakeout spans the counter-SOS to the bar the sequence COMPLETED — not to the
    // fill, which under "Retrace" is later and would stretch the box over the reclaim as
    // well, drawing a shakeout that never happened.
```

## [58] The callout. One line on the chart so it does not sit on the candles, an

```
    // The callout. One line on the chart so it does not sit on the candles, and the whole
    // breakdown in the TOOLTIP — every number the trade was built from, so a setup can be
    // audited on hover instead of by re-deriving it. Pushed execLabelOff ATRs away with a
    // leader line back, which is the only lever on where the tooltip opens.
```

## [59] Created EMPTY and transparent, then filled in on the bar each target is 

```
    // Created EMPTY and transparent, then filled in on the bar each target is reached. They
    // exist from the start so the per-trade object count is fixed and the eviction can drop
    // a whole trade as one unit.
```

## [60] (The ENTRY log line was REMOVED 2026-08-06 and folded into the single T|

```
    // (The ENTRY log line was REMOVED 2026-08-06 and folded into the single T| record the
    //  close block writes. Pine Logs retains only the most recent N messages, so on a
    //  multi-year run the OLDEST lines are the ones silently dropped — two lines per trade
    //  meant losing twice as much history, for facts that are useless without the outcome.)
```

## [61] ── Entry triangles — the always-visible marker at every fill (ported fro

```
// ── Entry triangles — the always-visible marker at every fill (ported from mpc_strategy.pine)
// A triangle under each long fill and over each short one, so you can never miss WHERE a trade
// opened. That is the whole reason it exists and is not covered by the position blocks: a trade
// that scratches paints a risk block a few pixels tall and reads as no trade at all.
// ⚠ `plotshape` is a GLOBAL-SCOPE call and cannot live inside the fill block above — it is
// declared once and evaluated on every bar, which is why the condition is written out here
// rather than being set as a flag inside that `if`.
// ⚠ It is the SAME edge test the fill block uses (`position_size != 0` while `[1] == 0`), so a
// triangle can never appear on a bar the tracker did not treat as a fill.
// ⚠ Gated on `execShowPosBox`, matching A+ — the triangles are part of the position drawing, so
// switching the blocks off switches these off with them rather than leaving orphaned markers.
```

## [62] ── f_dRatchet — ported from mpc_strategy.pine's f_swingRatchet, unchange

```
// ── f_dRatchet — ported from mpc_strategy.pine's f_swingRatchet, unchanged in behaviour.
// Same anchor as the plain structure trail (last confirmed swing ± buffer), but from there
// the stop climbs one pct-of-price step for every step of favourable move. The plain trail
// sits at the swing however far price runs, and a swing is a LAGGING anchor — in a strong
// leg it ends up a long way behind, which is where the runner's give-back comes from. Falls
// back to the bare anchor until the move is one full step past it, so it is never LOOSER
// than the structure trail, only equal or tighter.
```

## [63] ⚠ THE FILL BAR MAY NOT STAGE THE STOP, AND MAY NOT FEED tMaxFav.

```
    // ⚠ THE FILL BAR MAY NOT STAGE THE STOP, AND MAY NOT FEED tMaxFav.
    // A resting limit is reached by price coming to it from the WRONG side — a buy limit
    // fills on the way down — so the fill bar's favourable extreme is where the market was
    // before the trade existed, not profit the trade made. Staging off it lifts the stop to
    // breakeven on a trade that has gone nowhere, which puts it through the market and
    // market-closes every leg at the next bar's open at a price that is neither the stop nor
    // any target. This is BUG_exit_fill_price_mismatch, fixed across five Pine files on
    // 2026-08-01 — do not relax it. The exit orders are not live on the fill bar either, so
    // nothing could have banked there.
```

## [64] The TP2 stop FLOOR — the protective baseline the instant TP2 is reached,

```
    // The TP2 stop FLOOR — the protective baseline the instant TP2 is reached, before the
    // trail takes over. "One trail step behind" never drops below breakeven, so it cannot
    // hand back a loss.
```

## [65] ── The position drawing, updated live ──

```
    // ── The position drawing, updated live ──
    // na-guarded and guarded SEPARATELY from the exits below: a drawing call on an na id is
    // a runtime error that takes the whole script down, and an order that stopped being
    // issued because a BOX could not be drawn would turn a chart bug into a trading bug.
```

## [66] ⚠ A RUNG IS NOT RE-ISSUED ONCE ITS TARGET HAS BEEN TOUCHED. Calling stra

```
    // ⚠ A RUNG IS NOT RE-ISSUED ONCE ITS TARGET HAS BEEN TOUCHED. Calling strategy.exit with
    // an id whose order already FILLED places a NEW order rather than modifying the old one,
    // so a re-issued TP1 would bank another slice of the remainder every single bar after.
    // ⚠ This is a DELIBERATE divergence from mpc_strategy.pine, which re-issues every bar
    // unguarded. It gets away with it because it ships both rungs at 0% and the rung is then
    // skipped entirely — the bug is unreachable at its defaults and reachable at these.
```

## [67] The remainder. Declared as its own float rather than inlined as a ternar

```
    // The remainder. Declared as its own float rather than inlined as a ternary against na,
    // which Pine will not always infer a type for. na = no limit, so the runner is resolved
    // by the trailing stop alone when TP3 is switched off.
```

## [68] ── The REFUSAL record. Same shape as the trade record, so one parser rea

```
// ── The REFUSAL record. Same shape as the trade record, so one parser reads both. ──
// It carries the gates and the geometry, which is what makes a refused setup RE-PRICEABLE:
// with the sweep extreme, the reclaim extreme and the counter-SOS line you can compute
// offline what any stop anchor and any retrace level would have given it. A refusal logged
// as prose ("blocked: trend too young") can be counted and nothing else.
// ⚠ The header is emitted ONCE, on the first bar, so a pasted log is self-describing and
// cannot be read against the wrong column order six weeks from now.
//============================================================
//  STATE PANEL
//============================================================
// Reports the GATES, not just the outcome. A tool that only ever says "no setup" cannot tell
// you whether the market is quiet or whether you have set a gate to refuse everything — and
// those two need opposite responses.
```

## [69] The VWAP read, and it reports the ANSWER for the side the sequence would

```
    // The VWAP read, and it reports the ANSWER for the side the sequence would trade — not
    // "price is above VWAP", which the reader would then have to combine with the direction
    // themselves and would get wrong on exactly the short setups.
```

## [70] "reclaimed" is the state the entry actually needs — price is on the tren

```
    // "reclaimed" is the state the entry actually needs — price is on the trend's side AND
    // it had lost the line first. "pro-trend" alone means the side is right but the round
    // trip never happened, which under execVwapReclaim is NOT a trade. Naming them the same
    // thing is what let the old build look armed when it had nothing to enter on.
```

## [71] ⚠ The VWAP term is listed LAST in this chain and that mirrors the block-

```
    // ⚠ The VWAP term is listed LAST in this chain and that mirrors the block-code
    // precedence deliberately: the panel and the tag must never name different reasons for
    // one refusal. It is also only shown when VWAP can actually refuse something — under the
    // other two modes with the filter off, VWAP is being displayed, not consulted.
```

## [72] The two VWAP waits are DIFFERENT states and the panel must not merge the

```
    // The two VWAP waits are DIFFERENT states and the panel must not merge them: "lose" means
    // the pullback has not happened yet, "reclaim" means it has and price has not come back.
    // One of them is early in the setup and one is the bar before the entry.
```

## [73] PARITY / ANALYSIS EXPORT — per-bar DECISION STREAM  _(only in mpc_d_strategy_export.pine)_

```
//============================================================================
//  PARITY / ANALYSIS EXPORT — per-bar DECISION STREAM
//============================================================================
// This file is `mpc_d_strategy.pine` + THIS appended block, and NOTHING else changed.
// The body above is byte-identical to the parent apart from line 72's title.
//
// ⚠ REGENERATE WITH THIS EXACT RECIPE — and CHECK THE PLOT COUNT AFTERWARDS.
//     B=$(grep -n 'PARITY / ANALYSIS EXPORT' <export> | head -1 | cut -d: -f1)
//     sed -n "$((B-2)),\$p" <export> > /tmp/blk
//     cp indicators/strategies/mpc_d_strategy.pine <export>
//     sed -i '' '72s/strategy("MPC D Strategy"/strategy("MPC D Strategy Export"/' <export>
//     cat /tmp/blk >> <export>
//     grep -c '^plot(' <export>      # MUST be 51
// (48 → 51 on 2026-08-06 with the VWAP work: px_vwap and cfg_vwap_slope_bars were added to
//  this block, and the PARENT gained one visible plot of its own — the VWAP line — which
//  arrives here for free through the copy. Bump this number whenever either side gains a
//  plot, or the check stops being a check.)
// The count check is not ceremony. On 2026-08-06 the extraction grep was anchored on the
// `//====` rule line, which does not contain the words it was matching, so it produced an
// EMPTY block — and every downstream check still passed, because a bare copy of the parent
// is byte-identical to the parent and compiles perfectly. It just silently exported nothing.
// A regeneration that loses the whole point of the file must fail loudly; count the plots.
//
// WHY IT EXISTS. The Strategy Tester's trade list records FILLS. It cannot say what the
// gates refused, how far a trade ran before it handed the move back, or what a different
// stop anchor would have produced. Those are the three questions this strategy is being
// tuned on, so they get columns.
//
// ⚠ GOTCHA, inherited from every other export in this repo: a plotted column MUST use a
// transparent colour, never `display.none` — TradingView DROPS display.none series from
// the CSV. Every plot here uses _INV.
//
// ── READING THE STREAM ──────────────────────────────────────────────────────
// Most columns are na except on the bars where they mean something, so the CSV filters
// down to a few hundred rows.
//
// CANDIDATE BARS — any bar where px_cand_dir is non-na. ⚠ THAT IS NO LONGER THE SAME THING
//   AS "A BAR WHERE AN SOS FIRED", and reading it that way is now the easiest mistake to
//   make with this file. Under execEntryMode = "VWAP side" a candidate arrives on an
//   ORDINARY bar — no SOS on it, so px_sos carries only bit 4 (dFired) and none of the SOS
//   bits. Filter the CSV on px_cand_dir, never on px_sos.
//
//   Every value is the parent's OWN record, taken at decision time and copied, never
//   re-derived here: px_cand_dir, px_ctr_ext, px_rcl_ext, px_sos_lvl and the three px_gate_*
//   columns all come straight off dCandDir / dCandCtr / dCandRcl / dCandSos / dCandTBos /
//   dCandCBos / dCandBars. That is exact by construction rather than by argument — there is
//   no second implementation here that could disagree with the gate.
//
//   The authoritative dCtrHi / dCtrLo / dCtrSos are still plotted on FIRED bars (px_fire_*),
//   and on any fired bar they must agree with px_ctr_ext / px_sos_lvl. That cross-check now
//   guards a copy rather than a reconstruction, so it should be trivially true — if it ever
//   is not, something upstream in the parent has moved.
//
// THE POINT OF px_ctr_ext / px_rcl_ext / px_sos_lvl. With those three plus px_cand_entry
// you can compute OFFLINE what every stop anchor and every retrace level would have priced,
// on every candidate the strategy ever saw, without re-running TradingView:
//   Sweep extreme       = px_ctr_ext
//   Counter-SOS line    = px_sos_lvl
//   Between the two @p  = px_sos_lvl + (px_ctr_ext - px_sos_lvl) * p/100
//   Retrace @f (entry)  = px_rcl_ext - (px_rcl_ext - px_ctr_ext) * f   [long; mirrored short]
// That turns one export into a sweep instead of one configuration.
//
// px_mfe_r / px_mae_r are the running favourable and adverse excursion of the OPEN trade,
// in R, per bar. They are what the trade list cannot give you, and they are what settles
// whether a winner's drawdown came BEFORE or AFTER it reached a staging level — the one
// unknown that bounds the whole exit-ladder result. Both EXCLUDE the fill bar, for the same
// reason the parent's tMaxFav does (BUG_exit_fill_price_mismatch).
//
// px_stage is tracked here rather than read from tStage, because the parent resets tStage
// to 0 on the close bar and the close bar is exactly where the final stage matters.
```

## [74] ── Candidate geometry: DELETED 2026-08-06, and the deletion is the fix ─  _(only in mpc_d_strategy_export.pine)_

```
// ── Candidate geometry: DELETED 2026-08-06, and the deletion is the fix ─────
// `f_xCand()` lived here and rebuilt the candidate's direction and leg extremes from
// `st.bull_sos` plus `[1]` lookups. It is gone, not repaired: the parent publishes
// dCandDir / dCandCtr / dCandRcl for every candidate at decision time, so there was never a
// second claim worth maintaining — only a second claim that could disagree. See the note at
// the px_cand_* plots for what it got wrong once a candidate could arrive off an SOS bar.
// ⚠ Do not reintroduce a derivation here. Anything the columns need, the parent should
// record and this block should copy.
```

## [75] ── Trade tracker — export-owned, so the parent's close-bar resets cannot  _(only in mpc_d_strategy_export.pine)_

```
// ── Trade tracker — export-owned, so the parent's close-bar resets cannot erase it ──
// Returns [fillPx, oneR, stage, mfeR, maeR, closedR]. Every value survives the bar the
// trade closes on, which is the bar the parent has already zeroed tStage / tDir / tFillBar.
```

## [76] Ternary, not math.max — math.max returns a float and _stg is an int, whi  _(only in mpc_d_strategy_export.pine)_

```
        // Ternary, not math.max — math.max returns a float and _stg is an int, which is a
        // type error rather than a silent widening. Same reason the plots below build a
        // float local instead of putting an int in a ternary against na.
```

## [77] stgOut is declared float FIRST. `_live ? _stg : na` with an int _stg lea  _(only in mpc_d_strategy_export.pine)_

```
    // _stgOut is declared float FIRST. `_live ? _stg : na` with an int _stg leaves Pine to
    // infer a type for the na branch, and it does not always pick float — which is a paste-
    // time compile error, not a wrong number, so it is cheap to prevent and expensive to hit.
```

## [78] ── Real exit fills this bar, by rung ───────────────────────────────────  _(only in mpc_d_strategy_export.pine)_

```
// ── Real exit fills this bar, by rung ───────────────────────────────────────
// The PRICE the engine actually got, never the level it aimed at. A non-na px_exit_run on a
// bar where px_stage is 0 is a stop-out or a forced close (time stop / opposite SOS), which
// is how those are told apart offline.
```

## [79] ── DECISION STREAM ─────────────────────────────────────────────────────  _(only in mpc_d_strategy_export.pine)_

```
// ── DECISION STREAM ─────────────────────────────────────────────────────────
// px_sos (packed) = bull_sos·1 + bear_sos·2 + dFired·4 + limit_resting·8 + fill_bar·16 + close_bar·32
//   "limit_resting" only ever appears under Entry = Retrace; under SOS close the fill is the
//   signal bar. Counting bars where bit 8 is set and no bit 16 follows IS the unfilled-limit
//   rate, which is the entire cost of the Retrace entry and is invisible in the trade list.
```

## [80] The refusal code, identical to the pink chart tag and the [BLOCK] log li  _(only in mpc_d_strategy_export.pine)_

```
// The refusal code, identical to the pink chart tag and the [BLOCK] log line:
//   0 none · 1 direction off · 2 trend too young · 3 shakeout became a trend
//   4 shakeout stale · 5 stop too tight · 6 stop wrong side · 7 already in a position
//   8 ACCOUNT BUST — equity <= 0. Once this appears it appears on every candidate after it,
//     and that run of 8s marks the exact bar the strategy died. Nothing later is a signal.
// Each is built as a float LOCAL before it is plotted. Every one is an int in a ternary
// against na, which is the one shape Pine will not reliably type.
// 🔴 THESE NOW READ THE PARENT'S OWN RECORD AND NO LONGER RECONSTRUCT ANYTHING (2026-08-06).
// They used to be rebuilt here from `st.bull_sos` plus a set of `[1]` lookups, on the premise
// that every candidate arrives on an SOS bar and the shift has already destroyed the values
// the gate read. Both halves of that premise broke the moment "VWAP side" existed:
//   (a) a VWAP-side candidate arrives on an ORDINARY bar, so `st.bull_sos` is false and the
//       reconstruction returned direction 0 — which would have blanked px_cand_dir,
//       px_ctr_ext, px_rcl_ext, px_sos_lvl and all three px_gate_* columns on EVERY
//       candidate of the new mode. The export would have gone on producing a clean CSV that
//       simply had nothing in it, which is the failure this file is least able to detect.
//   (b) `[1]` is only equivalent to "before the shift" on a bar where the shift RAN. On a
//       non-SOS bar nothing shifted, and `dCurBos` can have been incremented by a plain BOS
//       earlier in the same bar — so `dCurBos[1]` would report the value the gate did NOT
//       read, on exactly the bars where a BOS and a candidate coincide.
// The parent records dCandDir / dCandCtr / dCandRcl / dCandSos / dCandTBos / dCandCBos /
// dCandBars for EVERY candidate, fired or refused, read at decision time and before any
// shift. Those are the authoritative values; copying them cannot drift from what the gate
// saw, where a reconstruction has to be re-proved against every new way a candidate can
// arise. px_fire_* below still carries the parent's fire-time geometry, so the two remain
// cross-checkable on any fired bar.
```

## [81] ⚠ px_vwap IS PLOTTED ON EVERY BAR, UNGATED, AND IS NOT THE SAME COLUMN A  _(only in mpc_d_strategy_export.pine)_

```
// ⚠ px_vwap IS PLOTTED ON EVERY BAR, UNGATED, AND IS NOT THE SAME COLUMN AS THE BODY'S
// VISIBLE "VWAP" PLOT — that one is gated on execShowVwap and is `na` whenever the line is
// switched off, so a parser must never read it.
// ⚠ This is the column that makes the VWAP rule RE-PRICEABLE OFFLINE, which is the whole
// design of this block. With the value on every bar you can reconstruct the side test at any
// candidate bar, and the slope over ANY lookback, from a run taken with the gate switched
// OFF entirely — so one export answers "would a VWAP filter have helped?" instead of
// requiring a second run to ask it. Storing only the boolean answer would have thrown away
// exactly the information the question needs.
```

## [82] ── CONFIG ──────────────────────────────────────────────────────────────  _(only in mpc_d_strategy_export.pine)_

```
// ── CONFIG ──────────────────────────────────────────────────────────────────
// Every input that can change a trade gets a column, so a stored export is self-describing
// and two of them can never be compared without noticing they ran different settings.
//   cfg_bits  = execLongs·1 + execShorts·2 + execCloseOppSOS·4
//               + execVwapReq·8 + execVwapSlope·16
//   cfg_modes = entry·1 + slAnchor·10 + minStop·100 + sizing·1000
//               + tp2Floor·10000 + runnerTrail·100000 + timeStop·1000000
//     entry:       0 SOS close · 1 Retrace · 2 VWAP side
//     slAnchor:    0 Sweep extreme · 1 Counter-SOS line · 2 Between the two · 3 % of entry-to-sweep
//     minStop:     0 Off · 1 % of price · 2 Fixed $ · 3 x ATR(14)
//     sizing:      0 Risk % of equity · 1 Fixed contracts
//     tp2Floor:    0 TP1 price · 1 Breakeven · 2 One trail step behind
//     runnerTrail: 0 Fixed step · 1 Structure (swing) · 2 Structure + % ratchet
//     timeStop:    0 Off · 1 Before TP1 only · 2 Always
// The numerics are plotted RAW, one column each, and deliberately NOT packed: they are
// floats, any pack that fits several into one float64 has to round, and a silently rounded
// threshold mis-describes the run — the exact failure this block exists to prevent.
// ⚠ cfg_ctr_bars_max is in BARS, so it means a different amount of TIME on every timeframe.
// A 5m export and a 15m export carrying the same 400 are NOT the same strategy.
// ⚠ THE NEW BITS AND THE NEW ENTRY VALUE ARE BOTH BACKWARD-SAFE, AND THAT IS WHY THEY WERE
// APPENDED RATHER THAN RESHUFFLED. An export taken before 2026-08-06 carries bits 8 and 16
// CLEAR, which decodes to both VWAP gates OFF — which is exactly what it ran, because they
// did not exist. Likewise entry ∈ {0,1} keeps its old meaning and only the new value 2 is
// added. A stored export must go on decoding the way it did the day it was taken; that is
// the whole contract of these columns, and it is why an existing code is never renumbered.
```

## [83] 🔴 THREE-WAY, NOT TWO-WAY, AND THE OLD FORM WAS ALREADY WRONG THE MOMENT   _(only in mpc_d_strategy_export.pine)_

```
// 🔴 THREE-WAY, NOT TWO-WAY, AND THE OLD FORM WAS ALREADY WRONG THE MOMENT "VWAP side"
// EXISTED. `execEntryMode == "SOS close" ? 0 : 1` sends BOTH other modes to 1, so a VWAP
// run would have been stored, and later read, as a Retrace run — a whole different entry
// model, reported with total confidence. This is the `execRunnerTrail` trap of 2026-07-26
// exactly: a code that collapses a widened dropdown does not fail, it lies. **Whenever an
// option is added to any input, find its cfg digit in the same commit.**
```

## [84] Raw, like every other numeric here, and for the same reason. ⚠ It is in   _(only in mpc_d_strategy_export.pine)_

```
// Raw, like every other numeric here, and for the same reason. ⚠ It is in BARS — a 5m and a
// 15m export both carrying 4 are measuring the slope over different amounts of TIME, the
// same warning cfg_ctr_bars_max carries.
```

