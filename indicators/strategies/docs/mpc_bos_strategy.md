# mpc_bos_strategy.pine — commentary

The prose that used to live inline in the Pine. Each entry is anchored from the
source by a `// [doc N]` line. Grep this file for `## [N]` to find one.

**Covers:** `mpc_bos_strategy.pine`, `mpc_bos_strategy_export.pine`

---

## [1] MPC BOS STRATEGY — the break-of-structure CONTINUATION setup

```
// ============================================================================
//  MPC BOS STRATEGY — the break-of-structure CONTINUATION setup
// ============================================================================
// Spec: docs/MPC_BOS_SPEC.md. Third strategy off the shared MPC-JARVIS engine,
// alongside mpc_strategy.pine (A+ SOS fade) and mpc_b_leg_strategy.pine.
//
// The engine block above the "STRATEGY EXECUTION" header is copied from
// mpc_strategy.pine and its LOGIC is byte-identical — do not let it drift. The
// A+ SEQUENCE TRACKER, the B-LEG tracker and the missed-setup callout were NOT
// copied: this strategy reads none of them, and the compile-token budget in this
// script family has already hit CE10117 and CE10295 twice.
//
// DO NOT re-slice this by line number. It was originally cut as "lines 1-3028 of
// mpc_strategy.pine", and that is already stale: on 2026-07-28 the parent
// consolidated every Strategy Execution input into ONE block near its line 328,
// which lands inside that range. The two files now differ in exactly three
// places, all of them intended:
//   1. this header + the strategy() title,
//   2. exec-input PLACEMENT — the parent declares its A+/B-LEG inputs up top;
//      this file declares its own BOS inputs down in the execution layer, and
//      keeps execConfSZ inline next to the Sniper engine that reads it,
//   3. the ~512-line A+ SEQUENCE / B-LEG tracker block, deliberately absent.
// Everything else — structure, fib, FVG, liquidity, sessions, RSI divergence,
// sniper — is identical, and that is the part that must stay identical.
//
// WHAT IT TRADES. A shift of structure (SOS) tells you the trend has turned.
// What comes after it is where the money is: the market prints one or more BREAK
// OF STRUCTURE events in that same direction until another SOS ends the run.
// Each BOS is a fresh continuation leg, and each leg gives a retracement you can
// buy (or sell) into. A+ fades the shift; this rides what the shift started.
// Not every BOS is real — some are the last poke before the reversal — so this
// is deliberately a FILTERED setup (F1-F10), not a "take them all" setup.
//
// THE DEFAULT SETUP, 2026-08-07 — MEASURED, and it REPLACES the 2026-07-31 spec
// defaults kept below. An SOS opens a regime; EVERY BOS in that direction arms a
// leg; a limit rests at fib 0.786 of that leg's retrace; the tap is the entry.
// The stop is the leg origin (fib 1.0) and price must be closing on the trend's
// own side of the session VWAP. No gap requirement, no displacement floor, no
// HTF bias gate.
// Twelve switches carry it: bosUseFvg OFF · bosEntryFib 0.786 · bosWhich "All" ·
// bosMinDispAtr 0.0 · bosVwapReq "Trend's side" · bosFibAnchor "Break leg" ·
// execTp1Pct 0 · execTp2Pct 0 · execTp3Pct 100 · bosSlModel "ATR" · bosSlAtr 1.3 ·
// execMinStopMode "% of price" (at execMinStopVal 0.10).
// The TP rungs landed 2026-08-07 (Run 6): BANKING EARLY COSTS MONEY — 30/30/20
// scored +58.2R where 0/0/100 scored +107.5R on the same trades. The stop still
// ratchets at TP1 and TP2 because the PRICES drive the staging whatever the rung
// SIZES are, so 0/0/100 is a protected hold, not a naked one.
// The last three landed the same day (Run 7) and are the biggest change here.
// 🔴 A FIB STOP IS A FRACTION OF THE LEG — fib 1.0 at a 0.786 entry risks 0.214
// of it — so a small leg produces a tiny stop MECHANICALLY, and since R is
// profit divided by stop, a tiny stop inflates every R in the book without one
// extra dollar being made. The old default's tightest tenth of stops is $0.64
// wide against a $0.22 spread; a 15-minute bar's low cannot tell you whether
// such a stop was touched. An ATR stop does not care how big the leg was.
// At a MATCHED 25% drawdown budget: 23.0x before, 65.4x after, and on 40 paired
// jitter replays the new default wins 32 and clears 4x on BOTH halves of the
// history in 28, against the old default's 4.
// ⚠ The R TOTAL FALLS (+107.5R → +54.4R) and that is not a loss: a wider stop
// makes each R a bigger dollar amount, so the same money is fewer R.
// ⚠ `bosFibAnchor` moved for a different reason — see its tooltip. It is the
// anchor the measurement used, not an anchor that beat the other one.
// Measured +14.5% over a matched random control (+4.1σ, 201 trades, PF 1.76,
// positive in 9 of 9 years) where the OLD defaults measured +2.8% at 1.7σ — i.e.
// what shipped before today was not distinguishable from random. Full record and
// every caveat: docs/MPC_BOS_OPTIMIZATION.md.
//
// 🔴 THE BIGGEST CHANGE IS THAT THE GAP ENTRY IS OFF, and it is the one to argue
// with first, because the FVG was the whole point of the 2026-07-31 spec. Two
// independent measurements say it is the losing half: the Python sweep found it
// 98 trades for −15.1R with no tail, and the engine study found a plain deep fib
// beats it four-fold. The gap decides WHERE the limit rests, and it rests too
// shallow for a continuation trade.
//
// THE PREVIOUS DEFAULT SETUP, 2026-07-31 (Aaron's spec), kept because the §10b
// numbers are its. An SOS opens a regime; a BOS with CLEAN DISPLACEMENT arms a
// leg; that break leaves an FVG; price retraces into 0.5-0.886 and taps the gap.
// That tap is the entry. The Sniper Zone is optional and can price a leg with no
// gap. Four switches carried it: bosUseFvg ON, execReqFVG ON, execConfSZ2 ON,
// bosMinDispAtr 0.5. The remaining filters (F1/F3/F4/F5/F6/F8) stay OFF as open
// questions, each switchable alone. See the block at GRP_EXEC for the reasoning.
// ⚠ F10 (session VWAP, 2026-08-06) is the ONE exception to "filters default OFF",
// and the exception has a reason rather than a preference behind it: every other
// filter here is an untested idea, and F10 is the only one that was MEASURED
// before it was switched on — 186,384 real M15 bars, +4.4% -> +6.8% edge over a
// matched random control, with the median stop 38% tighter. A filter with a
// measurement defaults on; a filter with an argument defaults off.
// ⚠ THE MEASUREMENT BEHIND TODAY'S DEFAULTS IS A SKELETON REPLAY, NOT THIS FILE.
// backtest/tools/trigger_edge.py drives the canonical structure + VWAP engines
// with a plain with-trend BOS, a fib limit and a fib stop, scored +2R-before-−1R.
// It does NOT model this file's TP ladder, its staged stop or its runner — so the
// DIRECTION transfers and the magnitude does not. The Strategy Tester is the only
// thing that can price the real ladder, and on 2026-08-07 Aaron confirmed the new
// defaults beat the old ones on his own chart. ⚠ That confirmation is DIRECTIONAL
// ONLY — the three numbers were not recorded, so no figure in this file describes
// a real TradingView run at these settings. Fill that in on the next run.
// ⚠ Everything in the §10b block further down was measured at the PREVIOUS
// defaults and describes a different strategy.
//
// THE PREVIOUS DEFAULT, 2026-07-29, kept because the numbers below are its. An
// SOS opens a regime; every BOS after it arms a leg; a limit rests at fib 0.618
// of that leg's retrace; the tap is the entry. No gap, no zone, no confirmation,
// no filters — a MEASUREMENT baseline for the raw BOS idea, never the target.
//
// WHY IT CHANGED. The first build shipped with F3 (leg-size floor), F4 (broken
// level must hold), F6 (2 trades per regime), F5/F5b (divergence) and a REQUIRED
// FVG all on. Over 365 days of XAUUSD 15m that took 13 trades for −2.65%. F4 was
// the main cause and it is a DESIGN CONFLICT rather than a bad number: the entry
// is a retrace to 0.618-0.886 of the leg, that band sits BELOW the broken swing
// on almost every leg, so F4 killed the setup a few bars before its own limit
// would have filled. It now defaults OFF with that written on its tooltip.
//
// IT IS THE A+ WITH THE ARM SWAPPED. Targets, staging, trail and sizing are the
// A+ ladder unchanged; the entry is now a plain fib by default. Three things
// differ from mpc_strategy.pine:
//   • the arm is a BOS after an SOS, not a sweep-or-divergence before one,
//   • liquidity sweeps are not used at all — no sweep arming, no sweep confluence,
//   • divergence is a KILL, not a veto-with-an-exemption: it blocks the entry,
//     pulls a resting limit, AND closes an open trade.
// Anything else that looks like an addition is a mistake — flag it, don't keep it.
// ----------------------------------------------------------------------------
// TRADE-CRITICAL INPUTS — these compute the values the execution block reads, so
// turning ANY of them off stops trades (they are marked "(REQUIRED)" in the
// settings panel). Keep ALL of them ON:
//   • "Hide Everything Except Market Structure"  -> must stay OFF (it force-kills every feature)
//   • "Show FVG (REQUIRED)"                      -> the entry edges (limit price)
//   • "Track RSI Divergence (REQUIRED)"          -> the divergence kill (F5/F5b)
//   • "Show External Fib (REQUIRED)"             -> gates the SNIPER-ZONE tracker,
//     which is entry method 3 and defaults ON here. The fib LEVELS themselves are
//     no longer read off it — the entry band, stop and targets are computed from
//     the structure engine's own anchors — but `_snTrack` sits behind showFibo, so
//     turning it off silently removes the no-FVG entry path.
// Liquidity is not read at all — this setup has no sweep arm.
// Everything else (Sessions, MV, Order Blocks, Internal/Cycle Fib, Sniper,
// structure labels) is cosmetic and defaults OFF.
// ⚠ VWAP IS NO LONGER IN THAT LIST. Since 2026-08-06 the session VWAP is a live
// GATE (F10, "Session VWAP filter" in Strategy Execution, default "Trend's side")
// and it refuses trades. It is the one formerly-cosmetic feature that now costs
// money when it is wrong. Set it to "Off" to reproduce any earlier run.
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

## [3] (The "Confirmation Table" group — 3 inputs + f_tablePosition + f_tableSi

```
// (The "Confirmation Table" group — 3 inputs + f_tablePosition + f_tableSize —
//  was DELETED 2026-07-31. The table itself was removed on 2026-07-24 to free
//  compile tokens, so every one of those settings had been doing nothing since:
//  declared, shown in the panel, read by no line of code.)
```

## [4] SMC SETTINGS (hardcoded)

```
//============================================================
//  SMC SETTINGS (hardcoded)
//============================================================
```

## [5] MARKET STRUCTURE LABEL SIZE

```
//============================================================
//  MARKET STRUCTURE LABEL SIZE
//============================================================
```

## [6] Swing-point labels are hidden by making their text transparent, not by s

```
// Swing-point labels are hidden by making their text transparent, not by skipping
// their creation. The label objects still exist and the engine's state is untouched,
// so structure tracking, fibs, OBs and the table behave identically either way.
```

## [7] (ORDER BLOCKS, VWAP and the Session Volume Profile / MV line were REMOVE

```
// (ORDER BLOCKS, VWAP and the Session Volume Profile / MV line were REMOVED
//  2026-07-25 — the script had gone over Pine's compiled-token cap again
//  (CE10117: 101484 > 100256) after the blocked-trade marker landed. All three
//  were purely cosmetic, defaulted OFF, and were read by NOTHING in the
//  execution layer — verified by grep: zero references after the STRATEGY
//  EXECUTION header. The B-LEG fork dropped the same three on 2026-07-24 for
//  the same reason. They live on in mpc_assistant.pine if the drawing is ever
//  wanted back.
//  ⚠ VWAP PARTLY CAME BACK 2026-08-06, and the distinction is the point: what
//  returned is one `ta.vwap(hlc3)`, one gate and one plot() in the F10 block of
//  the execution layer — NOT the settings block, colours and styles that were
//  cut here. The old VWAP cost tokens to DRAW something nothing read; the new
//  one costs almost none and is read by the arming condition. If CE10117
//  returns, delete the plot() first and the gate last.)
//============================================================
//  FAIR VALUE GAPS (FVG) INPUTS
//============================================================
```

## [8] Minimum gap size floor: a gap must be at least this % of price to count.

```
// Minimum gap size floor: a gap must be at least this % of price to count.
// No Auto-Threshold volatility scaling — a fixed floor, now user-tunable.
// FVG minimum-gap floor, SPLIT BY TIMEFRAME — ported from mpc_assistant.pine
// (its lines 149-151). This is why the assistant draws 5m gaps this file did not:
// a %-of-price floor does not scale down. 0.1% of gold at $3,300 is $3.30, wider
// than most WHOLE 5m bars, so one flat floor silently erased nearly every gap
// below 15m. 900 seconds = 15m.
// 2026-07-31 — the 15m+ floor is now the assistant's 0.04, NOT the A+'s 0.1.
// Aaron found a gap the chart clearly drew that this strategy refused to see. At
// gold $4,155 the two floors are $1.66 and $4.16 — the assistant draws anything
// over the first, the strategy discarded anything under the second, so a real gap
// inside the entry band was invisible to the entry ladder. The 0.1 was never a
// decision made FOR this file; it was inherited from mpc_strategy.pine, where it
// is load-bearing (the A+ 15m baseline and the mpc_sos_fade parity pin). Nothing
// in THIS file depends on it — there is no BOS parity harness and no BOS baseline
// worth preserving — so it is matched to the chart the setup is read off.
// ⚠ This MOVES every result this file has ever produced. See the header.
```

## [9] Middle-bar close-cleared test — the SECOND reason a gap on the chart was

```
// Middle-bar close-cleared test — the SECOND reason a gap on the chart was not a
// gap to this strategy, and it moved for the same reason as the floor above.
// mpc_assistant.pine has it OFF at every timeframe; this file had it ON at 15m+.
// A gap can clear the 0.04 floor and still be refused because bar B closed inside
// it, so fixing only the floor would have left half the discrepancy in place.
// Now OFF at every timeframe, matching the assistant exactly.
```

## [10] (DELETED 2026-07-31 — two whole groups that did nothing here)

```
//============================================================
//  (DELETED 2026-07-31 — two whole groups that did nothing here)
//============================================================
// "A+ Setup"  (aplusWindow) and "A+ Debug"  (debugShow23 / debugShow23Disarmed /
// debug23Filter / debugDays) both belonged to machinery this file never copied:
// the A+ SEQUENCE TRACKER and the missed-setup callout. Five inputs sat in the
// settings panel with nothing reading them. The BOS arm is a break of structure,
// so there is no sweep→SOS clock to bound and no 2-of-3 sequence to score.
```

## [11] RSI DIVERGENCE INPUTS

```
//============================================================
//  RSI DIVERGENCE INPUTS
//============================================================
```

## [12] (`divVeto` deleted 2026-07-31 — it was the A+'s veto switch and nothing 

```
// (`divVeto` deleted 2026-07-31 — it was the A+'s veto switch and nothing here
//  read it. The BOS veto is "F5 · Divergence blocks a new entry" in Strategy
//  Execution; the two levels below are what it reads.)
```

## [13] TRADING SESSIONS INPUTS

```
//============================================================
//  TRADING SESSIONS INPUTS
//============================================================
```

## [14] (Kill Zones & NY Range were REMOVED 2026-07-22 — the script had gone ove

```
// (Kill Zones & NY Range were REMOVED 2026-07-22 — the script had gone over
//  Pine's compiled-token cap (CE10117) and both were purely cosmetic, default
//  OFF, and read by nothing in the execution layer. They live on in
//  mpc_assistant.pine if the drawing is ever wanted back.)
```

## [15] LIQUIDITY LEVELS INPUTS

```
//============================================================
//  LIQUIDITY LEVELS INPUTS
//============================================================
```

## [16] INTERNAL FIB INPUTS

```
//============================================================
//  INTERNAL FIB INPUTS
//============================================================
```

## [17] FIBONACCI INPUTS

```
//============================================================
//  FIBONACCI INPUTS
//============================================================
```

## [18] MACRO FIB (full-cycle retracement across multiple BOS, locks in on trend

```
//============================================================
//  MACRO FIB (full-cycle retracement across multiple BOS, locks in on trend reversal)
//============================================================
```

## [19] SNIPER FIB INPUTS

```
//============================================================
//  SNIPER FIB INPUTS
//============================================================
```

## [20] Entry-confirmation toggle, declared HERE (not down in the Strategy Execu

```
// Entry-confirmation toggle, declared HERE (not down in the Strategy Execution
// block where it belongs by group) because the Sniper Fib engine a few hundred
// lines below has to read it, and Pine needs the declaration first. It still
// appears under "Strategy Execution" in the panel — group placement is by the
// group string, not by position in the file.
```

## [21] MARKET STRUCTURE OVERRIDE — applied after every other toggle above is

```
//============================================================
//  MARKET STRUCTURE OVERRIDE — applied after every other toggle above is
//  declared, before anything downstream uses them. When marketStructureOnly is
//  on, every non-structure feature is force-disabled regardless of its own
//  checkbox, so the chart shows only external/internal BOS/SOS/iBOS/iSOS.
//============================================================
//============================================================
//  MARKET STRUCTURE OVERRIDE (remaining flags) — the other 11 flags now derive
//  their override inline right next to their own input declaration (renamed
//  to <flag>Input), which is required because Pine's "active=" parameter on
//  other inputs must reference a pure, never-reassigned input bool; reassigning
//  the original variable via ":=" anywhere in the script poisons its type for
//  every "active=" use of it, even ones textually earlier in the file. These
//  one has no "active=" dependents elsewhere, so a plain override is safe.
```

## [22] SMC STRUCTURE TYPE

```
//============================================================
//  SMC STRUCTURE TYPE
//============================================================
```

## [23] Neither an active pullback high nor a confirmed ASH was available to

```
                // Neither an active pullback high nor a confirmed ASH was available to
                // promote — use the actual highest point since the last confirmed low so
                // a genuine swing high still gets confirmed instead of silently vanishing.
```

## [24] TRADING SESSIONS TYPES & METHODS

```
//============================================================
//  TRADING SESSIONS TYPES & METHODS
//============================================================
```

## [25] SHARED CONSTANTS & SECURITY CALLS

```
//============================================================
//  SHARED CONSTANTS & SECURITY CALLS
//============================================================
```

## [26] ── HTF Directional Bias (adapted from LuxAlgo's HTF Bias Tracker) ──

```
// ── HTF Directional Bias (adapted from LuxAlgo's HTF Bias Tracker) ──
// Compares an "action" period's high/low/close against a "context" period's high/low
// to classify Bullish / Bearish / Neutral, with sweep detection.
```

## [27] Shared by Daily/Weekly/Monthly/Asia/London/NY liquidity levels: checks f

```
// Shared by Daily/Weekly/Monthly/Asia/London/NY liquidity levels: checks for
// mitigation, updates the line/label color+style+extent in place, and returns
// the (possibly updated) mitigated/mitigatedBar state.
```

## [28] Sessions: current week only by default (from Sunday 00:00 New York), or

```
// Sessions: current week only by default (from Sunday 00:00 New York), or
// unlimited history when Show All History is on. Anchored to the calendar week
// rather than a rolling 7 days, so mid-week it doesn't bleed into last week.
```

## [29] EXECUTION — EXTERNAL + INTERNAL STRUCTURE

```
//============================================================
//  EXECUTION — EXTERNAL + INTERNAL STRUCTURE
//============================================================
// External structure engine always runs — fib, macro fib, OBs all depend on it
```

## [30] Captures the latest confirmed internal swing point (price + location), s

```
// Captures the latest confirmed internal swing point (price + location), so the
// External Fib can adopt it as its anchor if it's more extreme than the external
// structure's own point — used only for the fib pull, nothing else.
```

## [31] ── Stop internal tracking on external SOS ───────────────

```
// ── Stop internal tracking on external SOS ───────────────
// True on any bar where the external structure breaks — the current internal
// swing is finished. Used further down to clear the table's INT row so it can
// never show an iBOS/iSOS whose drawing has already been wiped from the chart.
```

## [32] EQUAL HIGHS / LOWS (EQH / EQL) — liquidity pools

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

## [33] An unmitigated EQ level can outlive its pivot by thousands of bars, and 

```
// An unmitigated EQ level can outlive its pivot by thousands of bars, and Pine
// throws once a line's x1 ages past the drawing buffer — so the origin is clamped
// this far back. Same guard, same number, as the liquidity levels use.
```

## [34] FAIR VALUE GAPS — persist until mitigated

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

## [35] ── Detection (confirmed bars only, so live wicks can't paint phantom gap

```
// ── Detection (confirmed bars only, so live wicks can't paint phantom gaps) ──
// The FVG is the 3-candle imbalance itself (LuxAlgo definition): bar A and bar C
// never overlap and the middle bar's close cleared the gap. No "clean impulse"
// body/colour rule — any 3 bars that leave a big-enough gap qualify.
// Threshold is the timeframe-split %-of-price floor (see fvgThreshPct above).
```

## [36] Cap: drop oldest gaps beyond the limit

```
    // Cap: drop oldest gaps beyond the limit
    // Cap: drop the oldest NON-EQ gap beyond the limit. With eqExemptFvg OFF (the
    // default here) the scan finds index 0 on its first test, so this is exactly
    // the old array.shift and nothing moves. With it ON, a gap sitting on an
    // EQH/EQL is skipped over and survives until it is actually mitigated.
```

## [37] Kill condition depends on the "keep until broken" toggle:

```
        // Kill condition depends on the "keep until broken" toggle:
        //   OFF (default) → tap-delete: dies the moment price touches the near edge.
        //   ON            → survives taps; dies only when a candle CLOSES fully past
        //                   the FAR edge (broken through the opposite side).
        // Skipped on the creation bar itself: a bullish gap's top IS that bar's
        // low, so without this guard every gap would self-delete instantly.
```

## [38] RSI DIVERGENCE — regular divergence at the extremes

```
//============================================================
//  RSI DIVERGENCE — regular divergence at the extremes
//============================================================
// Bullish: price prints a LOWER low while RSI prints a HIGHER low, with the RSI
// low coming from oversold. Bearish is the mirror from overbought. Pivots are
// confirmed divPivotLen bars after the extreme (non-repainting by design).
```

## [39] Live confluence flags for the A+ setup row

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

## [40] DAILY LEVELS

```
//============================================================
//  DAILY LEVELS
//============================================================
```

## [41] WEEKLY LEVELS

```
//============================================================
//  WEEKLY LEVELS
//============================================================
```

## [42] PREVIOUS WEEKLY CLOSE (PWC)

```
//============================================================
//  PREVIOUS WEEKLY CLOSE (PWC)
//============================================================
```

## [43] H4 LIQUIDITY SWEEP TRACKER

```
//============================================================
//  H4 LIQUIDITY SWEEP TRACKER
//============================================================
```

## [44] SESSION H/L TRACKING

```
//============================================================
//  SESSION H/L TRACKING
//============================================================
```

## [45] LABEL COLLISION DETECTION

```
//============================================================
//  LABEL COLLISION DETECTION
//============================================================
// Wrapped in a function (gate included) so the main body pays for one statement
// rather than ~35 — see the CE10295 note on f_drawTable.
```

## [46] ── A LABEL NOBODY CAN SEE MAY NOT RESERVE A SLOT ─────────────────────

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

## [47] ⚠ And it defers only to a VISIBLE daily label. A mitigated PDH is

```
        // ⚠ And it defers only to a VISIBLE daily label. A mitigated PDH is
        // hidden but its label object lives until the next new-day wipe, so
        // without this term a swept, invisible PDH went on suppressing a
        // perfectly visible session tag at the same price — the level lost
        // its name with nothing on screen holding the place.
```

## [48] prevY is advanced BEFORE the set_y call so the loop's last statement is

```
            // prevY is advanced BEFORE the set_y call so the loop's last statement is
            // the void set_y, not a float assignment. Both branches of this if must
            // agree on type, because the if is the function's return expression
            // (CE10235) — as a main-body statement it never had to.
```

## [49] FIBONACCI DRAWING

```
//============================================================
//  FIBONACCI DRAWING
//============================================================
```

## [50] Inbound touch of the 0.5 level during the RETRACEMENT toward the entry z

```
// Inbound touch of the 0.5 level during the RETRACEMENT toward the entry zone —
// the A+ sequence's EARLY entry tier. Distinct from fibo2Touched, which tests the
// same price on the way back OUT (as TP1) and is gated behind 0.618.
```

## [51] Skip ALL touched checks on the same bar the origin changed, OR the same 

```
    // Skip ALL touched checks on the same bar the origin changed, OR the same bar
    // the extending anchor (fibo_ash/fibo_asl) itself moved — that anchor tracks
    // live wicks during a pullback watch, not confirmed closes, so without this
    // guard a fresh wick-high can retroactively satisfy the very TP3 level it
    // just created, hiding the fib with no real BOS/SOS behind it.
```

## [52] Gate: coloring only activates once 0.618 is reached.

```
        // Gate: coloring only activates once 0.618 is reached.
        // fibo618EverReached is only set TRUE at the END of this block (after all checks run),
        // so TP level checks never fire on the same bar that 0.618 was first hit.
```

## [53] macro_dir tracks the OVERALL trend direction we are currently in.

```
// macro_dir tracks the OVERALL trend direction we are currently in.
//   1  = overall trend is up (we are accumulating the highest high of the whole up-cycle)
//  -1  = overall trend is down (we are accumulating the lowest low of the whole down-cycle)
// The origin (opposite anchor) is fixed only when the trend actually reverses (st.dir flips),
// not on every internal BOS/SOS within the same direction. This lets the fib span multiple
// BOS legs that all belong to the same larger move (e.g. wave 1->2->3 as one up-cycle).
```

## [54] ── EXACT RULE (per latest instructions) ──

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

## [55] Cycle Fib TRACKING always runs — its discount zone doubles as the HTF PO

```
// Cycle Fib TRACKING always runs — its discount zone doubles as the HTF POI for
// the A+ sequence on ANY timeframe. Only the DRAWING is gated to 5m-and-under
// charts (macroFibAllowed), where the fib's scale fits the chart.
```

## [56] ── Track the most recent bearish SOS and start tracking the low from tha

```
    // ── Track the most recent bearish SOS and start tracking the low from that point ──
    // Seeded once from the very first bar (fallback) so the first bullish SOS can
    // lock immediately instead of waiting for a prior bearish SOS to seed the tracker.
```

## [57] ── While waiting for a bullish SOS, keep updating the lowest low since b

```
    // ── While waiting for a bullish SOS, keep updating the lowest low since bear SOS ──
    // This gives us the true cycle low — the deepest point made after the bearish reversal,
    // not the structure engine's historical scan which can reach far into the past.
```

## [58] INTERNAL FIB

```
//============================================================
//  INTERNAL FIB
//============================================================
```

## [59] Direction aware levels

```
        // Direction aware levels
        // Bullish: 0=top(iH), 1=bottom(iL), levels go DOWN from top
        // Bearish: 0=bottom(iL), 1=top(iH), levels go UP from bottom
```

## [60] SNIPER FIB

```
//============================================================
//  SNIPER FIB
//============================================================
// The zone must be TRACKED whenever it can confirm a trade, even if its drawing
// is switched off — otherwise sniperZoneTop/Bot stay na and the confirmation
// silently never fires. Drawing stays gated on showSniperFib alone.
```

## [61] PLOTTING

```
//============================================================
//  PLOTTING
//============================================================
```

## [62] MPC - JARVIS CONFIRMATION TABLE

```
//============================================================
//  MPC - JARVIS CONFIRMATION TABLE
//============================================================
// (Confirmation table REMOVED 2026-07-24 to free compile tokens — CE10117. The
//  setup state it displayed on-chart is all in the Pine Logs. Only JARVIS_BLACK
//  survives, for the watermark below.)
```

## [63] MPC- JARVIS WATERMARK

```
//============================================================
//  MPC- JARVIS WATERMARK
//============================================================
```

## [64] STRATEGY EXECUTION — BOS continuation entries + the shared exit ladder

```
//============================================================
//  STRATEGY EXECUTION — BOS continuation entries + the shared exit ladder
//============================================================
// This is the ONLY block that is not part of the mpc_assistant.pine engine.
// Spec: docs/MPC_BOS_SPEC.md. It is the A+ strategy with the ARM swapped:
//
//   A+   : sweep-or-divergence -> SOS -> fade the shift.
//   BOS  : SOS sets a regime -> each later BOS in that direction is a fresh
//          continuation leg -> buy/sell its retrace.
//
// Three things differ from mpc_strategy.pine and nothing else:
//   1. the arm is a BOS after an SOS (no sweep arming, no sweep confluence),
//   2. divergence is a KILL, not a veto-with-exemption — it blocks the entry,
//      pulls a resting limit, and (optionally) closes an open trade,
//   3. the stop model is a dropdown (spec §6) instead of a fib-level dropdown.
// Entries, targets, staging, trail and sizing are the A+ ladder, unchanged.
//
// ── Two legs, two fibs (spec §2) ─────────────────────────────────────────────
//   BREAK leg     = bos_low -> bos_high, frozen at the BOS bar. Its 0.382-0.5
//                   pocket is the drawn Sniper Zone.
//   EXPANSION leg = bos_low -> the running extreme after the break. This is what
//                   the drawn External fib measures, and its 0.5-0.886 band is
//                   the A+ entry band. DEFAULT anchor — the band the whole A+
//                   entry machinery already prices off.
// `bosFibAnchor` picks which one prices the trade. The levels are computed here
// from fibo_ash / fibo_asl directly rather than read off fiboP*, so the entry
// band no longer depends on "Show External Fib" being on.
//
// ── Deviations from the spec, called out per §0 ──────────────────────────────
// • Spec §3 lists `fibo7Touched` as a death. That latch is GLOBAL and per-fib-
//   ORIGIN, not per-BOS: in a run of three breaks the origin never changes, so
//   the latch set by break #1's round trip would kill breaks #2 and #3 on their
//   arm bar. It is re-implemented per-anchor here (bos*_half + a return to the
//   anchor's own 0.0), which is what the spec means by "on the anchor leg".
// • `execMinStopMode` / `execMinStopVal` are carried over from the A+ risk block
//   and are NOT in the spec's §8 input list. They default Off, so the baseline
//   run is exactly the spec's baseline; they exist so the same tuning lever is
//   available on all three bots.
// • The divergence CLOSE (§4a) fires on a confirmed opposing divergence only,
//   not on extreme RSI. An overbought RSI is the normal state of a healthy long
//   continuation — closing on it would flatten the runner on every winner. The
//   entry BLOCK still reads both, exactly as §4a specifies.
//============================================================
```

## [65] ── 2. WHAT ARMS IT (the break) ─────────────────────────────────────────

```
// ── 2. WHAT ARMS IT (the break) ────────────────────────────────────────────
// Spec §4 calls these F1/F2/F3/F4/F6/F9. The numbers are kept in comments only —
// the panel reads in plain English, like mpc_strategy.pine's does.
```

## [66] ── 3. WHERE THE LIMIT RESTS (entry price) ──────────────────────────────

```
// ── 3. WHERE THE LIMIT RESTS (entry price) ─────────────────────────────────
// The five ↳ rules below are all children of "Price the entry off a gap": with
// that off there is no gap in the ladder for any of them to modify, so all five
// grey out together. That is NOT how mpc_strategy.pine treats its equivalents —
// there they are siblings, because its Require-FVG toggle only adds a fallback
// and leaves the gap rules live. Here the master toggle really does switch the
// whole gap path off, so nesting them is the honest reading.
```

## [67] ⚠ `bosVwapReq` IS A DROPDOWN RATHER THAN A CHECKBOX FOR A REASON THAT NO

```
// ⚠ `bosVwapReq` IS A DROPDOWN RATHER THAN A CHECKBOX FOR A REASON THAT NO LONGER APPLIES,
// AND THE TYPE IS KEPT ANYWAY. The note here used to explain that a bool declared at this
// line would have shifted the file's last `input.bool` and silently reset it on every tuned
// chart, while a string shifted nothing — so the dropdown bought a paste that needed no
// "Reset settings to defaults". That constraint died on 2026-08-12 when every input moved
// into one consolidated panel block, which resets saved values once by design. The TYPE is
// deliberately NOT changed now: `cfg_*` codes are a WIRE FORMAT, and an export already on
// disk carries the number this dropdown emits.
```

## [68] STAGE 0/1 — REGIME, then the BOS that arms it

```
//============================================================
//  STAGE 0/1 — REGIME, then the BOS that arms it
//============================================================
// The regime is self-locking: once direction is bullish, a bull break is a BOS
// and a bear break is an SOS, so a "bull BOS in a bear trend" cannot exist. At
// the start of history the engine seeds a direction with no SOS behind it, so
// bosReg* stays false until a real SOS fires and those seeded breaks never trade.
//
// NOTE the engine sets bull_bos = true on every bull_sos bar too — they are not
// mutually exclusive — so every BOS test below reads `bull_bos and not bull_sos`.
```

## [69] Session-gap detector — the first bar after a market close (e.g. daily

```
// Session-gap detector — the first bar after a market close (e.g. daily
// 17:00-18:00) has a time jump much larger than the normal bar spacing. Structure
// events printed on it are gap artifacts, not breaks.
```

## [70] Stage 0 — an SOS opens its own regime and closes the opposite one.

```
// Stage 0 — an SOS opens its own regime and closes the opposite one.
//
// OPENING and CLOSING are gated DIFFERENTLY on purpose, and this was a bug until
// 2026-07-29. Both used to sit behind `not sessionGapBar`, so an SOS printing on
// the first bar after the daily close did neither. The half that mattered was the
// CLOSE: a bear SOS on a gap bar left `bosL_on` true, and the armed long kept its
// buy-limit resting straight through into the new bearish regime, where it could
// still fill on the way down. That is a trade with no BOS of its own behind it —
// exactly the out-of-sequence entry this comment now exists to prevent.
//
//   OPEN  stays gap-guarded — a structure event printed on a gap bar is a time-jump
//         artifact, and arming a fresh regime off one is how you trade a phantom.
//   CLOSE fires ALWAYS — refusing to believe an SOS cannot make it untrue, and if
//         the shift is real the arm on the other side is already dead. Killing on a
//         possible artifact costs one setup; keeping it costs a wrong-way trade.
```

## [71] Stage 1 — the BOS. The counter increments even when the filters refuse t

```
// Stage 1 — the BOS. The counter increments even when the filters refuse the
// leg, so the ordinal a trade reports is its true position in the run.
// The NEWEST leg owns the setup: an arm is dropped before the new one is tested,
// which mirrors the drawn fib re-anchoring the same way.
```

## [72] THE ANCHOR FIB — the leg the whole ladder is priced off

```
//============================================================
//  THE ANCHOR FIB — the leg the whole ladder is priced off
//============================================================
// One helper, both directions: `ext` is the leg's 0.0 (the extreme it ran to),
// `org` its 1.0 (where the leg started). Long: ext = high, org = low. Short:
// ext = low, org = high. This is the identical arithmetic the engine's fiboP*
// uses (ash - range*v / asl + range*v), just anchored per-setup.
```

## [73] THE SHALLOW END OF THE ENTRY BAND, in price. Every rule that used to har

```
// THE SHALLOW END OF THE ENTRY BAND, in price. Every rule that used to hardcode
// 0.5 — the gap's band test, the entry clamp, the fully-past test, the Sniper
// Zone clamp, the straddle fallback and the plain-fib clamp — reads this instead,
// so opening the band moves all six together and they cannot drift apart.
// The DEEP end (lP6 / sP6, fib 0.886) is fixed and is not affected.
```

## [74] DEATH — the arm is dropped, no trade

```
//============================================================
//  DEATH — the arm is dropped, no trade
//============================================================
// Any of: the opposite SOS (the regime is over — handled in Stage 0 above), a
// newer same-side BOS (re-anchor, Stage 1 above), the cycle completing on the
// anchor leg, a close past the anchor's 1.0, F4's broken-level test, or the
// staleness cap.
//
// The cycle-complete test is the per-anchor version of the engine's global
// `fibo7Touched`: the shallow end of the entry band has been tapped (the retrace
// happened) AND price has since returned to the anchor's 0.0. The global latch
// cannot be used — it is keyed to the fib ORIGIN, which does not change across a
// run of breaks, so break #1's round trip would kill breaks #2 and #3 on their
// arm bar. It reads lTop / sTop rather than a hardcoded 0.5 so that "the retrace
// happened" means the same thing here as it does to the entry ladder — otherwise
// opening the band to 0.382 would leave a filled-at-0.382 leg that this test
// still believes never retraced.
```

## [75] STAGE 3 — ENTRY: the A+ ladder, unchanged, on the BOS leg

```
//============================================================
//  STAGE 3 — ENTRY: the A+ ladder, unchanged, on the BOS leg
//============================================================
// A resting LIMIT at the entry price. The tap is the entry — we never wait for a
// bar to close inside the band (a wick fills the order, and the order survives
// the FVG box being deleted on the tap because the order is already placed).
//
// AT THE SHIPPED DEFAULTS `bosUseFvg` and `execReqFVG` are BOTH ON, so the plain
// fib fallback at the bottom of this ladder is never reached: a gap (or the
// Sniper Zone) prices every entry, and a leg with neither does not trade.
// `bosEntryFib` is inert in that configuration — see its tooltip.
//
// With `bosUseFvg` ON the A+ ladder takes over and the first source that prices
// the leg wins:
//   1. FVG edge (clamped to lTop; whole gap past lTop with execFvgDeepOnly on)
//   2. deep-fib re-price — Method 3
//   3. Sniper Zone — only on a leg with no qualifying gap, and only a zone
//      anchored at or after THIS BOS's bar
//   4. gap straddling lTop -> limit at lTop
//   5. the plain fib — unless execReqFVG says no gap means no trade
// lTop / sTop is the shallow floor: no candidate may ever rest shallower than it,
// and anything past 0.886 is rejected. It is fib 0.5 by default and fib 0.382 when
// "Shallowest the entry may rest" is opened up — see the lTop declaration above.
```

## [76] Position size = risk / stop distance, and it MUST be guarded on equity.

```
// Position size = risk / stop distance, and it MUST be guarded on equity.
//
// `strategy.equity` can go NEGATIVE here. `margin_long/short = 0.2` is 500x, so a
// position's loss is not bounded by the account, and at the default 10% risk this
// strategy does blow up — the Python replay over 7.9 years found profit factor
// below 1.0 in all 82 configurations tested and one of them ended at −$3,186 on a
// $100k start (strategies/python/mpc_bos/mpc_bos_optimization.md, Run 1).
//
// Once equity is negative, `equity * risk% / slDist` is negative, and Pine ABORTS
// the whole run on that bar with "Invalid `qty` value" — so the report shows an
// error instead of the blown account that actually caused it. Returning `na` here
// makes the setup refuse instead: a dead account does not take the next trade,
// which is both the honest simulation and the thing that lets the run finish.
```

## [77] Method 3 — the entry price for a DEEP gap whose NEAR EDGE sits past 0.61

```
// Method 3 — the entry price for a DEEP gap whose NEAR EDGE sits past 0.618, or
// na when the near edge is shallower (those keep the exact-edge entry). ONLY the
// near edge decides it: a real gap is often tall enough to span 0.702/0.786, and
// what the body crosses is irrelevant.
```

## [78] The chosen fib entry price, per side, CLAMPED to the band's shallow end 

```
// The chosen fib entry price, per side, CLAMPED to the band's shallow end — so
// picking 0.382 here while the band still stops at 0.5 quietly gives you 0.5
// rather than an entry outside the band the rest of the ladder enforces.
```

## [79] Sniper Zone — the break leg's 0.382-0.5 pocket, re-anchored on every BOS

```
// Sniper Zone — the break leg's 0.382-0.5 pocket, re-anchored on every BOS. Used
// only on a leg where no qualifying gap exists, and only if the zone belongs to
// THIS break (sz_bar >= the anchor's bar) rather than being left over from an
// earlier leg. The limit rests at the FAR side of the pocket.
```

## [80] The least-favorable gap entry: a gap whose body STRADDLES the band's sha

```
// The least-favorable gap entry: a gap whose body STRADDLES the band's shallow
// end. Ranks below every other gap source, so it only prices a leg none of them
// did. Note that with the band opened to 0.382 most gaps that used to straddle
// 0.5 now sit fully INSIDE the band, so rule 1 catches them first and this one
// fires far less often.
```

## [81] ── THE DEFAULT ENTRY — the plain fib level, last in the ladder so any en

```
// ── THE DEFAULT ENTRY — the plain fib level, last in the ladder so any enabled
//    confirmation above wins. SKIPPED ENTIRELY at the shipped defaults, where a
//    gap is both used AND required — this is the fallback for the looser build.
```

## [82] GATES — the filters that refuse a ready setup

```
//============================================================
//  GATES — the filters that refuse a ready setup
//============================================================
// F5 — the divergence KILL. Live, both directions, NO post-SOS exemption. This
// is re-evaluated every bar the limit rests, so a divergence appearing during the
// retrace PULLS the order (longArmed goes false -> strategy.cancel below), and a
// divergence going stale lets it be re-placed while the leg is otherwise alive.
```

## [83] F10 — SESSION VWAP, the pro-trend side. Added 2026-08-06.

```
// F10 — SESSION VWAP, the pro-trend side. Added 2026-08-06.
// (F9 is STALENESS / bosMaxDays in docs/MPC_BOS_SPEC.md §4 — this is F10, not F9.)
// ⚠ IT IS THE SESSION VWAP AND DELIBERATELY THE ONE ON THE CHART. `ta.vwap(hlc3)` is the
// single line mpc_assistant.pine draws and the one engines/vwap/ is the canonical Python
// port of — session-anchored, re-anchored at the trading-day open, volume-weighted.
// Anchoring a private VWAP at the break instead would be a SECOND VWAP implementation,
// which CLAUDE.md forbids outright, and it would not be the line anyone is looking at.
// ⚠ It needs the bar's VOLUME. On XAUUSD that is tick volume, which is what Pine reads, so
// it is free here — but a symbol with no volume data makes ta.vwap RAISE rather than return
// na, and the whole script dies with it. This is the one line that ties the file to a
// volume-bearing feed.
// ⚠ VWAP was removed from this file 2026-07-25 for compile tokens, and what came back is
// only the VALUE plus one line of plot — NOT the settings block, the colours or the styles
// that were cut with it. If CE10117 returns, the drawing is what goes again, never the gate.
```

## [84] ⚠ A `na` VWAP (no volume yet on the session's first bar) returns FALSE, 

```
// ⚠ A `na` VWAP (no volume yet on the session's first bar) returns FALSE, never true.
// "cannot ask" and "no" must not be the same value, and of the two available answers the
// safe one for a gate about to place money is the refusal. It costs at most one bar a day.
// ⚠ THE TEST IS THE BAR'S CLOSE, WHICH IS WHY IT IS FREE OF LOOK-AHEAD. `longArmed` is
// recomputed at every bar's close and rests or cancels the limit for the NEXT bar, so the
// side being read is always a closed bar's, never the side of the bar the fill happens on.
// Reading the fill bar's own close would select bars that recovered by their close — that
// error inflated the measured edge from +6.8% to +15.9% before it was caught.
```

## [85] ⚠ The line BREAKS at each trading-day anchor on its own — ta.vwap return

```
// ⚠ The line BREAKS at each trading-day anchor on its own — ta.vwap returns na across the
// reset — which is correct, and is why this is a plot() rather than a polyline. Drawn only
// while the filter is live: a rule you cannot see is a rule you cannot check, and an
// always-on line would clutter the chart of somebody running the filter Off.
```

## [86] ORDERS

```
//============================================================
//  ORDERS
//============================================================
```

## [87] Stop anchor per the model dropdown, buffer applied outside. Split in two

```
// Stop anchor per the model dropdown, buffer applied outside. Split in two so
// the `switch` is a function's LAST statement — the form the rest of this file
// already uses and the one Pine is happiest with.
```

## [88] Entry DEPTH is derived from where the limit actually landed, never chose

```
// Entry DEPTH is derived from where the limit actually landed, never chosen. The
// rule it enforces: TP1 must never be a level the entry already rests at or past,
// or the trade "hits TP1" on its own fill bar, stages the stop to breakeven and
// dies a scratch. So each depth gets its own two lower rungs.
//   2  DEEP     entry 0.618 or deeper
//   1  STANDARD entry between 0.5 and 0.618 (the 0.5 clamp lands here)
//   0  SHALLOW  entry shallower than 0.5 — only reachable with the band opened
//               to 0.382, and the reason lP118 / sP118 exist.
```

## [89] ⚠ `vwapBlock*` is re-read on every bar the limit rests, exactly like the

```
// ⚠ `vwapBlock*` is re-read on every bar the limit rests, exactly like the divergence kill
// above it — so price closing back through VWAP PULLS a resting order, and closing back on
// the trend's side lets it be placed again while the leg is otherwise alive. That is the
// deliberate reading of a STATE: the filter describes where price is now, not something it
// did once. A one-shot check at arming time would let a setup fill hours later on the wrong
// side of the very line that qualified it.
```

## [90] TP3 is ALWAYS fib 0.000 — the leg extreme, the level the External Fib

```
    // TP3 is ALWAYS fib 0.000 — the leg extreme, the level the External Fib
    // itself labels TP3. Only the two rungs below it move, one step per depth:
    //   DEEP     (entry 0.618+)   TP1 0.500  TP2 0.382
    //   STANDARD (entry at 0.5)   TP1 0.382  TP2 0.236
    //   SHALLOW  (entry at 0.382) TP1 0.236  TP2 0.118
    // Each row shifts because the limit already rests AT its own would-be TP1 — a
    // target there fills on the trade's own fill bar, stages the stop to breakeven
    // and scratches it. The extra rung below keeps three real targets either way.
```

## [91] BLOCKED-TRADE MARKER

```
//============================================================
//  BLOCKED-TRADE MARKER
//============================================================
// A setup that was READY to rest its limit — armed on a live BOS, an entry edge
// to rest on, flat, this leg not yet traded — and was stopped by one of YOUR OWN
// TOGGLES rather than by price. These are the only trades invisible everywhere
// else: no order is placed, so nothing is drawn and the Strategy Tester cannot
// know they existed. Count the tags, flip the rule off, re-run, compare.
// ONE TAG PER SETUP PER REASON — the dedupe key is the BOS bar plus the code.
// (`showBlockTag` moved up into the Strategy Execution block, section 8, so every
//  drawing toggle lives together instead of one sitting on its own down here.)
```

## [92] Reason PRECEDENCE — the first rule that would refuse the order is the on

```
// Reason PRECEDENCE — the first rule that would refuse the order is the one
// reported, so a tag can never blame a downstream gate for an upstream refusal.
// ⚠ Code 7 is APPENDED rather than slotted in at its precedence position, so codes 1-6 keep
// the meaning every earlier run and every screenshot already gave them. Only its place in
// the ternary moved — VWAP is a market-context refusal, so it is reported alongside the HTF
// bias gate and ahead of the counting gates below it.
```

## [93] FILL — mark the leg traded, freeze the trade's yardsticks

```
//============================================================
//  FILL — mark the leg traded, freeze the trade's yardsticks
//============================================================
```

## [94] On the bar the trade closes: recolour by RESULT and append the R. Green 

```
// On the bar the trade closes: recolour by RESULT and append the R. Green won,
// red lost, ORANGE breakeven — a trade that went out and came back to entry is a
// breakeven, not a win, and the colour has to say so.
```

## [95] POSITION BOX — the trade drawn as stacked bands

```
//============================================================
//  POSITION BOX — the trade drawn as stacked bands
//============================================================
// Every band comes from the strategy's own closed-trade log, at the price the
// engine REALLY filled — never a fib level it merely aimed at — so the drawing
// can never claim profit the P&L does not have.
```

## [96] A function's LAST statement is its return value, and the three branches

```
        // A function's LAST statement is its return value, and the three branches
        // above create a box / a box / a line — Pine refuses to pick a type for
        // that (CE10235). Remove this constant and the script stops compiling.
```

## [97] EXITS — the shared ladder, unchanged

```
//============================================================
//  EXITS — the shared ladder, unchanged
//============================================================
//   stage 0  entry    -> the stop model
//   stage 1  TP1 hit  -> breakeven + buffer
//   stage 2  TP2 hit  -> the TP2 stop floor, then the runner trail
// Stage 1 stays tied to the TP1 TOUCH, not to a fixed R distance: TP1 is a limit
// order, so keying breakeven off it guarantees the partial is banked before the
// rest of the position is protected. Do not decouple them.
```

## [98] ── The FILL bar cannot stage the stop (BUG_exit_fill_price_mismatch.md) 

```
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

## [99] ── the MOVING stop ─────────────────────────────────────────────────────

```
// ── the MOVING stop ────────────────────────────────────────────────────────
// A trail that runs from the bar after the fill, not from TP2. It is applied
// with math.max (long) / math.min (short) against the staged stop, so it can
// only ever TIGHTEN — breakeven and the TP2 floor are never loosened by it, and
// it composes with the section-7 runner trail rather than replacing it.
// Dead on the fill bar on purpose: lMaxFav is seeded with that bar's FULL high,
// which includes price action the position was never in, so trailing off it
// would stage a stop the trade never actually earned.
```

## [100] A rung sized 0% is SKIPPED, never placed. strategy.exit() treats qty_per

```
// A rung sized 0% is SKIPPED, never placed. strategy.exit() treats qty_percent = 0
// as "unspecified" and falls back to closing the WHOLE position at that limit —
// the exact opposite of "bank nothing here". The TP PRICES still drive the staged
// stop whatever the rung sizes are.
```

## [101] §4a — the divergence KILL on an OPEN trade. An opposing divergence means

```
    // §4a — the divergence KILL on an OPEN trade. An opposing divergence means the
    // move is overextended and setting up the NEXT shift of structure, and a
    // continuation trade is the worst thing to be holding into that.
```

## [102] cat /tmp/blk >> <export>  _(only in mpc_bos_strategy_export.pine)_

```
//     cat /tmp/blk >> <export>
//     grep -c '^plot(' <export>      # MUST be 60  (5 inherited + 55 here)
// The count check is not ceremony. On 2026-08-06 the D export's extraction grep was
// anchored on the `//====` rule line, which does not contain the words it was matching,
// so it produced an EMPTY block — and every downstream check still passed, because a bare
// copy of the parent is byte-identical to the parent and compiles perfectly. It just
// silently exported nothing. A regeneration that loses the point of the file must fail
// loudly; count the plots.
//
// ⚠ PINE CAPS A SCRIPT AT 64 plot() CALLS. The first build of this block came to 69 and
// was caught by the count check above, not by a compiler. It is now 60, and the ten columns
// cut were the ones either DERIVABLE from an event already in the stream (bosCnt*/bosTrd*
// follow from px_struct fires, qty from risk/stop) or belonging to a path the shipped
// defaults never enter (px_sz_* — the Sniper Zone prices nothing while bosUseFvg is OFF).
// ⚠ RE-ADD px_sz_top / px_sz_bot BEFORE TRUSTING ANY PARITY RUN WITH bosUseFvg ON — without
// them the gap ladder's zone branch is unverified, and a green gate would be green about a
// branch neither side entered. This block is built to 60, four under the cap, so the
// parent can gain a few plots without the export becoming uncompilable. If you need more
// columns, PACK them into an existing bitfield rather than adding a plot.
//
// ⚠ CE10117 (compile tokens) IS THE OTHER CEILING AND THIS FILE HAS HIT IT TWICE. If the
// export will not compile, the fix is NOT to cut decision columns — it is to strip cosmetic
// DRAWING from the export only. The twin must match the parent's DECISIONS, not its chart.
//
// ⚠ GOTCHA, inherited from every other export in this repo: a plotted column MUST use a
// transparent colour, never `display.none` — TradingView DROPS display.none series from
// the CSV. Every plot here uses _INV.
//
// ⚠ NO RAW BAR INDICES. `bosL_bar` is Pine's `bar_index`, which counts from the first bar
// the CHART loaded, not from the export's first row — so it is export-window-relative and
// diffing it raw is correct only by the accident of a full-history export. That trap cost a
// whole afternoon on the B-LEG harness (2,409 comparisons failing at one flat offset of
// 15,362). Ages are exported instead: `bar_index - bosL_bar` is window-independent.
//
// ── WHY IT EXISTS ───────────────────────────────────────────────────────────
// The Strategy Tester records FILLS. It cannot say which setups the gates refused, which
// leg priced a trade, or what the entry ladder chose — and those are the questions this
// strategy is being tuned on. `strategies/python/mpc_bos/` was DELETED on 2026-08-04
// precisely because no file like this existed, so its 82-configuration sweep described a
// port nobody could verify. This is what makes the rebuilt port checkable.
//
// ── READING THE STREAM ──────────────────────────────────────────────────────
// Most columns are `na` except on bars where they mean something, so the CSV filters down.
// The ANCHOR columns (px_l_ext / px_l_org / px_s_ext / px_s_org) are the load-bearing ones:
// every fib level the strategy uses is `ext + (org - ext) * v`, so exporting the two
// endpoints lets the comparator recompute all ten levels instead of spending ten columns
// on each side. If those two agree bar-for-bar, the whole ladder agrees.
//============================================================================
```

## [103] ── STRUCTURE + ARM STATE ───────────────────────────────────────────────  _(only in mpc_bos_strategy_export.pine)_

```
// ── STRUCTURE + ARM STATE ───────────────────────────────────────────────────
// One bitfield for the events, one for the arm. Bits, not columns, because the plot cap is
// 64 and a boolean does not deserve a column of its own.
//   px_struct  1 bull_bos · 2 bear_bos · 4 bull_sos · 8 bear_sos · 16 sessionGapBar
//             32 bosFireL · 64 bosFireS
//   px_arm     1 bosL_on · 2 bosS_on · 4 bosRegL · 8 bosRegS
//             16 longArmed · 32 shortArmed · 64 in-position-long · 128 in-position-short
//            256 fill-bar · 512 close-bar
```

## [104] AGE, never the raw bar index — see the warning at the top of this block.  _(only in mpc_bos_strategy_export.pine)_

```
// AGE, never the raw bar index — see the warning at the top of this block.
// ⚠ BUILT AS FLOAT LOCALS FIRST, and that is not style. `bar_index - bosL_bar` is an INT, and
// an int in a ternary against `na` does not type reliably in Pine — it fails at PASTE time,
// which is exactly how this file failed its first load. The D export carries the same note
// for four of its own columns. Assign into a `float` var and Pine promotes cleanly.
```

## [105] ── THE ANCHOR — four numbers that regenerate every level ───────────────  _(only in mpc_bos_strategy_export.pine)_

```
// ── THE ANCHOR — four numbers that regenerate every level ────────────────────
// Whichever anchor the run used. lExt/lOrg are `na` when the long side has no live anchor,
// which is itself a fact worth diffing (it is what makes lFibsReady false).
```

## [106] ── THE GATES — why a ready setup was refused ───────────────────────────  _(only in mpc_bos_strategy_export.pine)_

```
// ── THE GATES — why a ready setup was refused ────────────────────────────────
// The block CODES are the parent's own (f_blkCode), so a mismatch here names the rule.
//   px_gate  1 lateDay · 2 htfLong · 4 htfShort · 8 vwapLong · 16 vwapShort
//           32 vetoL · 64 vetoS · 128 lBlkReady · 256 sBlkReady
```

## [107] ⚠ THE VOLUME IS PLOTTED, NOT ASSUMED, and this file shipped without it b  _(only in mpc_bos_strategy_export.pine)_

```
// ⚠ THE VOLUME IS PLOTTED, NOT ASSUMED, and this file shipped without it by mistake.
// TradingView's "Export chart data" carries a Volume column ONLY if the Volume STUDY is on
// the chart — measured across ~40 exports in engines/, exactly one has volume and it is the
// one whose Pine plots it. So "TradingView exports it" is a claim about the reader's chart
// layout, not about the export, and the first real BOS export arrived with no volume at all.
// The session-VWAP gate (bosVwapReq, default ON) is the only rule here that needs it, and
// without it compare_bos.py can only REFUSE — replaying against an absent VWAP would block
// every setup and the empty book would read as agreement.
// vwap_export.pine and svp_export.pine already carry `px_volume` for exactly this reason;
// this is that convention, not a new one. Do not remove it to buy back a plot slot.
```

## [108] ── THE TRADE ───────────────────────────────────────────────────────────  _(only in mpc_bos_strategy_export.pine)_

```
// ── THE TRADE ────────────────────────────────────────────────────────────────
// Frozen at the fill and carried, so the comparator can check the whole ladder was priced
// identically — not merely that both sides opened a trade on the same bar.
```

## [109] ── CONFIG — the run describes ITSELF, which is what stops a green gate l  _(only in mpc_bos_strategy_export.pine)_

```
// ── CONFIG — the run describes ITSELF, which is what stops a green gate lying ─
// `compare_bos.py` CONFIGURES THE PYTHON FROM THESE COLUMNS. That is the whole point: a
// parity run taken with the two sides on different settings is green about nothing, and
// this repo has met that trap by name ("green on a branch neither side entered").
//   cfg_bits  1 execLongs · 2 execShorts · 4 bosUseFvg · 8 execReqFVG · 16 execFvgDeepOnly
//            32 execDeepFib · 64 execConfSZ2 · 128 execFvg50 · 256 bosReqHold
//           512 bosRespectVeto · 1024 execNoLateDay · 2048 bosTp3Measured
//          4096 bosCloseOppDiv · 8192 fvgRequireClose · 16384 fvgKeepUntilBroken
//         32768 eqExemptFvg · 65536 bosShallow · 131072 bosExpAnchor
//        262144 vwap-on · 524288 useStructTrail
```

## [110] Enums packed as DECIMAL DIGITS, each field < 10, so decoding is division  _(only in mpc_bos_strategy_export.pine)_

```
// Enums packed as DECIMAL DIGITS, each field < 10, so decoding is division and modulo
// rather than a lookup nobody can check.
//   cfg_enum1 = entryFib + 10*which + 100*slModel + 1000*minStopMode + 10000*moveStop
//   cfg_enum2 = tp2StopMode + 10*htfWeekly + 100*htfDaily
```

