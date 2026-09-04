# b_leg_strategy.pine — commentary

The prose that used to live inline in the Pine. Each entry is anchored from the
source by a `// [doc N]` line. Grep this file for `## [N]` to find one.

**Covers:** `b_leg_strategy.pine`, `b_leg_strategy_export.pine`

---

## [1] B-LEG STRATEGY — the late-retrace setup, split out to run PARALLEL t

```
// ============================================================================
//  B-LEG STRATEGY — the late-retrace setup, split out to run PARALLEL to SOS Fade
// ============================================================================
// FORKED FROM sos_fade_strategy.pine (the "SOS Fade Strategy"). Same byte-identical
// MPC-JARVIS engine + SOS Fade SEQUENCE TRACKER — because the B LEG arms off the SOS Fade
// sequence STATE (the SOS whose retrace arrived late). The ONLY change vs the
// parent is the EXECUTION layer: SOS Fade entries are disabled and the B LEG is the
// strategy's sole entry type. Everything upstream (engine + SOS Fade arm/SOS/latch
// tracking + the "SOS Fade has priority" gate) is kept so the B LEG fires on EXACTLY
// the bars it fires in the parent — this file is the provable baseline for the
// standalone B-LEG bot, to be tuned (own entry / stop / TP models) AFTER parity.
//
// The B LEG: an SOS Fade SOS fires, price expands and prints a continuation BOS BEFORE
// it ever retraces, so the SOS Fade reversal leg dies at 2/3 (no retrace). On the HTF
// that is ONE clean leg and the retrace DOES arrive, late — into the frozen
// Sniper-Zone band (0.382-0.5) of the original SOS leg. Entry = a resting limit
// at the 0.5 edge (the tap IS the entry); SL beyond fib 1.0 (leg origin); TP
// ladder = broken swing extreme -> expansion extreme -> runner.
//
// WHY it still runs the whole SOS Fade machine: bLegArm reads aplus*_sosBar + the
// half/618 latches + fibo_dir + the structure legs. That is a READ dependency on
// the shared SOS Fade sequence tracker (like depending on an engine), NOT on the SOS Fade
// entry logic. Do not let the engine above the execution block drift from
// mpc_jarvis.pine / sos_fade_strategy.pine.
// ----------------------------------------------------------------------------
// TRADE-CRITICAL INPUTS — these compute the values the execution block reads, so
// turning ANY of them off stops trades (they are marked "(REQUIRED)" in the
// settings panel). Keep ALL of them ON:
//   • "Hide Everything Except Market Structure"  -> must stay OFF (it force-kills every feature)
//   • "Show External Fib (REQUIRED)"             -> SL / TP / entry price levels
//   • "Show FVG (REQUIRED)"                      -> the entry edges (limit price)
//   • "Show All Liquidity Levels (REQUIRED)"     -> arms setups via sweeps
//   • "Track RSI Divergence (REQUIRED)"          -> arms setups via divergence + veto
// Everything else (Sessions, Kill Zones, VWAP, MV, Order Blocks, Internal/Cycle
// Fib, Sniper, structure labels) is cosmetic and defaults OFF — safe to toggle
// freely, it never affects trade firing.
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

## [3] SMC SETTINGS (hardcoded)

```
//============================================================
//  SMC SETTINGS (hardcoded)
//============================================================
```

## [4] MARKET STRUCTURE LABEL SIZE

```
//============================================================
//  MARKET STRUCTURE LABEL SIZE
//============================================================
```

## [5] Swing-point labels are hidden by making their text transparent, not by s

```
// Swing-point labels are hidden by making their text transparent, not by skipping
// their creation. The label objects still exist and the engine's state is untouched,
// so structure tracking, fibs, OBs and the table behave identically either way.
```

## [6] FAIR VALUE GAPS (FVG) INPUTS

```
//============================================================
//  FAIR VALUE GAPS (FVG) INPUTS
//============================================================
```

## [7] SOS FADE SEQUENCE INPUTS

```
//============================================================
//  SOS FADE SEQUENCE INPUTS
//============================================================
// (5 dead SOS Fade inputs removed 2026-07-21 — aplusDivOnly / aplusHtfWarn /
//  aplusHtfBlock / aplusReqInt / aplusIgnoreWindow were declared but never
//  read anywhere in this file. Deleted to buy compile tokens for the
//  post-SOS divergence veto exemption. Arming is controlled by the
//  execArmSweep / execArmDiv toggles in the Execution group instead.)
```

## [8] SOS Fade DEBUG (bar-replay diagnostics — no effect on trades)

```
//============================================================
//  SOS Fade DEBUG (bar-replay diagnostics — no effect on trades)
//============================================================
```

## [9] RSI DIVERGENCE INPUTS

```
//============================================================
//  RSI DIVERGENCE INPUTS
//============================================================
```

## [10] TRADING SESSIONS INPUTS

```
//============================================================
//  TRADING SESSIONS INPUTS
//============================================================
```

## [11] (Kill Zones & NY Range were REMOVED 2026-07-22 — the script had gone ove

```
// (Kill Zones & NY Range were REMOVED 2026-07-22 — the script had gone over
//  Pine's compiled-token cap (CE10117) and both were purely cosmetic, default
//  OFF, and read by nothing in the execution layer. They live on in
//  mpc_jarvis.pine if the drawing is ever wanted back.)
```

## [12] LIQUIDITY LEVELS INPUTS

```
//============================================================
//  LIQUIDITY LEVELS INPUTS
//============================================================
```

## [13] INTERNAL FIB INPUTS

```
//============================================================
//  INTERNAL FIB INPUTS
//============================================================
```

## [14] FIBONACCI INPUTS

```
//============================================================
//  FIBONACCI INPUTS
//============================================================
```

## [15] MACRO FIB (full-cycle retracement across multiple BOS, locks in on trend

```
//============================================================
//  MACRO FIB (full-cycle retracement across multiple BOS, locks in on trend reversal)
//============================================================
```

## [16] SNIPER FIB INPUTS

```
//============================================================
//  SNIPER FIB INPUTS
//============================================================
```

## [17] STRATEGY EXECUTION INPUTS

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
//   2. Pine needs a declaration BEFORE its first read. The Sniper engine and
//      BLEG_MAX both read inputs from this block, which is why the whole block
//      sits up here rather than beside the execution logic at the bottom of the
//      file. The execution block still OWNS the behaviour — it just no longer
//      owns the declarations.
//
// The block is ordered the way a trade actually happens: what trades → what arms
// it → where the limit rests → what can refuse it → size and stop → targets →
// runner → drawing. Read it top to bottom and you have followed one trade.
// Kept in LOCKSTEP with sos_fade_strategy.pine's block of the same name — same eight
// sections, same order. This fork simply has fewer levers (no SL fib dropdown, no
// minimum-stop floor, no % ratchet on the runner trail).
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
```

## [18] ── 3. WHERE THE LIMIT RESTS (entry price) ──────────────────────────────

```
// ── 3. WHERE THE LIMIT RESTS (entry price) ────────────────────────────────────
// These four are SIBLINGS, not a parent and three children. With "Require FVG"
// OFF a qualifying gap still prices the entry exactly as before — that toggle
// only adds the 0.618 fib as a FALLBACK when no gap qualifies. So none of the
// three gap rules below is greyed out by it; they all stay live either way.
```

## [19] ── 7. THE RUNNER — everything here starts only AFTER TP2 is hit ────────

```
// ── 7. THE RUNNER — everything here starts only AFTER TP2 is hit ──────────────
// NOT a child of the trail method — it has TWO masters. 'Fixed step' trails off it,
// and the "One trail step behind" TP2 floor above measures off it too. Greying it
// on the trail method would silently disable a live setting, so it is never greyed.
```

## [20] MARKET STRUCTURE OVERRIDE — applied after every other toggle above is

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

## [21] SMC STRUCTURE TYPE

```
//============================================================
//  SMC STRUCTURE TYPE
//============================================================
```

## [22] Neither an active pullback high nor a confirmed ASH was available to

```
                // Neither an active pullback high nor a confirmed ASH was available to
                // promote — use the actual highest point since the last confirmed low so
                // a genuine swing high still gets confirmed instead of silently vanishing.
```

## [23] TRADING SESSIONS TYPES & METHODS

```
//============================================================
//  TRADING SESSIONS TYPES & METHODS
//============================================================
```

## [24] SHARED CONSTANTS & SECURITY CALLS

```
//============================================================
//  SHARED CONSTANTS & SECURITY CALLS
//============================================================
```

## [25] ── HTF Directional Bias (adapted from LuxAlgo's HTF Bias Tracker) ──

```
// ── HTF Directional Bias (adapted from LuxAlgo's HTF Bias Tracker) ──
// Compares an "action" period's high/low/close against a "context" period's high/low
// to classify Bullish / Bearish / Neutral, with sweep detection.
```

## [26] Shared by Daily/Weekly/Monthly/Asia/London/NY liquidity levels: checks f

```
// Shared by Daily/Weekly/Monthly/Asia/London/NY liquidity levels: checks for
// mitigation, updates the line/label color+style+extent in place, and returns
// the (possibly updated) mitigated/mitigatedBar state.
```

## [27] Sessions: current week only by default (from Sunday 00:00 New York), or

```
// Sessions: current week only by default (from Sunday 00:00 New York), or
// unlimited history when Show All History is on. Anchored to the calendar week
// rather than a rolling 7 days, so mid-week it doesn't bleed into last week.
```

## [28] EXECUTION — EXTERNAL + INTERNAL STRUCTURE

```
//============================================================
//  EXECUTION — EXTERNAL + INTERNAL STRUCTURE
//============================================================
// External structure engine always runs — fib, macro fib, OBs all depend on it
```

## [29] Captures the latest confirmed internal swing point (price + location), s

```
// Captures the latest confirmed internal swing point (price + location), so the
// External Fib can adopt it as its anchor if it's more extreme than the external
// structure's own point — used only for the fib pull, nothing else.
```

## [30] ── Stop internal tracking on external SOS ───────────────

```
// ── Stop internal tracking on external SOS ───────────────
// True on any bar where the external structure breaks — the current internal
// swing is finished. Used further down to clear the table's INT row so it can
// never show an iBOS/iSOS whose drawing has already been wiped from the chart.
```

## [31] EQUAL HIGHS / LOWS (EQH / EQL) — liquidity pools

```
//============================================================
//  EQUAL HIGHS / LOWS (EQH / EQL) — liquidity pools
//============================================================
// Ported line-for-line from mpc_jarvis.pine on 2026-08-01. Before that date NO
// strategy file had an EQ engine — not this one, not sos_fade_strategy.pine, not
// b_leg_strategy.pine, not either export. It was never a decision: the block
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

## [32] An unmitigated EQ level can outlive its pivot by thousands of bars, and 

```
// An unmitigated EQ level can outlive its pivot by thousands of bars, and Pine
// throws once a line's x1 ages past the drawing buffer — so the origin is clamped
// this far back. Same guard, same number, as the liquidity levels use.
```

## [33] FAIR VALUE GAPS — persist until mitigated

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

## [34] ── Detection (confirmed bars only, so live wicks can't paint phantom gap

```
// ── Detection (confirmed bars only, so live wicks can't paint phantom gaps) ──
// The FVG is the 3-candle imbalance itself (LuxAlgo definition): bar A and bar C
// never overlap and the middle bar's close cleared the gap. No "clean impulse"
// body/colour rule — any 3 bars that leave a big-enough gap qualify.
// Threshold is the user-set %-of-price floor (see fvgThreshPct input above).
```

## [35] Cap: drop oldest gaps beyond the limit

```
    // Cap: drop oldest gaps beyond the limit
    // Cap: drop the oldest NON-EQ gap beyond the limit. With eqExemptFvg OFF (the
    // default here) the scan finds index 0 on its first test, so this is exactly
    // the old array.shift and nothing moves. With it ON, a gap sitting on an
    // EQH/EQL is skipped over and survives until it is actually mitigated.
```

## [36] Kill condition depends on the "keep until broken" toggle:

```
        // Kill condition depends on the "keep until broken" toggle:
        //   OFF (default) → tap-delete: dies the moment price touches the near edge.
        //   ON            → survives taps; dies only when a candle CLOSES fully past
        //                   the FAR edge (broken through the opposite side).
        // Skipped on the creation bar itself: a bullish gap's top IS that bar's
        // low, so without this guard every gap would self-delete instantly.
```

## [37] RSI DIVERGENCE — regular divergence at the extremes

```
//============================================================
//  RSI DIVERGENCE — regular divergence at the extremes
//============================================================
// Bullish: price prints a LOWER low while RSI prints a HIGHER low, with the RSI
// low coming from oversold. Bearish is the mirror from overbought. Pivots are
// confirmed divPivotLen bars after the extreme (non-repainting by design).
```

## [38] Live confluence flags for the SOS Fade setup row

```
// Live confluence flags for the SOS Fade setup row
// Divergence relevance is tied to structure, not just a bar count. A divergence
// that fired several legs ago — with BOS/SOS events since — is stale even if
// still within the bar window: price has already moved on, and citing it as a
// veto reason (e.g. an old bullish divergence from the bottom blocking a fresh
// short at a NEW top with its own current bearish divergence) is misleading.
// So a divergence stays live only until the NEXT external break after it fired,
// with the bar count as an outer safety cap on top of that.
```

## [39] DAILY LEVELS

```
//============================================================
//  DAILY LEVELS
//============================================================
```

## [40] WEEKLY LEVELS

```
//============================================================
//  WEEKLY LEVELS
//============================================================
```

## [41] PREVIOUS WEEKLY CLOSE (PWC)

```
//============================================================
//  PREVIOUS WEEKLY CLOSE (PWC)
//============================================================
```

## [42] H4 LIQUIDITY SWEEP TRACKER

```
//============================================================
//  H4 LIQUIDITY SWEEP TRACKER
//============================================================
```

## [43] SESSION H/L TRACKING

```
//============================================================
//  SESSION H/L TRACKING
//============================================================
```

## [44] LABEL COLLISION DETECTION

```
//============================================================
//  LABEL COLLISION DETECTION
//============================================================
// Wrapped in a function (gate included) so the main body pays for one statement
// rather than ~35 — see the CE10295 note on f_drawTable.
```

## [45] ── A LABEL NOBODY CAN SEE MAY NOT RESERVE A SLOT ─────────────────────

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

## [46] ⚠ And it defers only to a VISIBLE daily label. A mitigated PDH is

```
        // ⚠ And it defers only to a VISIBLE daily label. A mitigated PDH is
        // hidden but its label object lives until the next new-day wipe, so
        // without this term a swept, invisible PDH went on suppressing a
        // perfectly visible session tag at the same price — the level lost
        // its name with nothing on screen holding the place.
```

## [47] prevY is advanced BEFORE the set_y call so the loop's last statement is

```
            // prevY is advanced BEFORE the set_y call so the loop's last statement is
            // the void set_y, not a float assignment. Both branches of this if must
            // agree on type, because the if is the function's return expression
            // (CE10235) — as a main-body statement it never had to.
```

## [48] FIBONACCI DRAWING

```
//============================================================
//  FIBONACCI DRAWING
//============================================================
```

## [49] Inbound touch of the 0.5 level during the RETRACEMENT toward the entry z

```
// Inbound touch of the 0.5 level during the RETRACEMENT toward the entry zone —
// the SOS Fade sequence's EARLY entry tier. Distinct from fibo2Touched, which tests the
// same price on the way back OUT (as TP1) and is gated behind 0.618.
```

## [50] Skip ALL touched checks on the same bar the origin changed, OR the same 

```
    // Skip ALL touched checks on the same bar the origin changed, OR the same bar
    // the extending anchor (fibo_ash/fibo_asl) itself moved — that anchor tracks
    // live wicks during a pullback watch, not confirmed closes, so without this
    // guard a fresh wick-high can retroactively satisfy the very TP3 level it
    // just created, hiding the fib with no real BOS/SOS behind it.
```

## [51] Gate: coloring only activates once 0.618 is reached.

```
        // Gate: coloring only activates once 0.618 is reached.
        // fibo618EverReached is only set TRUE at the END of this block (after all checks run),
        // so TP level checks never fire on the same bar that 0.618 was first hit.
```

## [52] macro_dir tracks the OVERALL trend direction we are currently in.

```
// macro_dir tracks the OVERALL trend direction we are currently in.
//   1  = overall trend is up (we are accumulating the highest high of the whole up-cycle)
//  -1  = overall trend is down (we are accumulating the lowest low of the whole down-cycle)
// The origin (opposite anchor) is fixed only when the trend actually reverses (st.dir flips),
// not on every internal BOS/SOS within the same direction. This lets the fib span multiple
// BOS legs that all belong to the same larger move (e.g. wave 1->2->3 as one up-cycle).
```

## [53] ── EXACT RULE (per latest instructions) ──

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

## [54] Cycle Fib TRACKING always runs — its discount zone doubles as the HTF PO

```
// Cycle Fib TRACKING always runs — its discount zone doubles as the HTF POI for
// the SOS Fade sequence on ANY timeframe. Only the DRAWING is gated to 5m-and-under
// charts (macroFibAllowed), where the fib's scale fits the chart.
```

## [55] ── Track the most recent bearish SOS and start tracking the low from tha

```
    // ── Track the most recent bearish SOS and start tracking the low from that point ──
    // Seeded once from the very first bar (fallback) so the first bullish SOS can
    // lock immediately instead of waiting for a prior bearish SOS to seed the tracker.
```

## [56] ── While waiting for a bullish SOS, keep updating the lowest low since b

```
    // ── While waiting for a bullish SOS, keep updating the lowest low since bear SOS ──
    // This gives us the true cycle low — the deepest point made after the bearish reversal,
    // not the structure engine's historical scan which can reach far into the past.
```

## [57] INTERNAL FIB

```
//============================================================
//  INTERNAL FIB
//============================================================
```

## [58] Direction aware levels

```
        // Direction aware levels
        // Bullish: 0=top(iH), 1=bottom(iL), levels go DOWN from top
        // Bearish: 0=bottom(iL), 1=top(iH), levels go UP from bottom
```

## [59] SNIPER FIB

```
//============================================================
//  SNIPER FIB
//============================================================
// The zone must be TRACKED whenever it can confirm a trade, even if its drawing
// is switched off — otherwise sniperZoneTop/Bot stay na and the confirmation
// silently never fires. Drawing stays gated on showSniperFib alone.
```

## [60] PLOTTING

```
//============================================================
//  PLOTTING
//============================================================
```

## [61] MPC - JARVIS CONFIRMATION TABLE

```
//============================================================
//  MPC - JARVIS CONFIRMATION TABLE
//============================================================
```

## [62] An external break ends the current internal swing and (unless historic i

```
// An external break ends the current internal swing and (unless historic internals
// are enabled) wipes its drawings from the chart. Clear the table's INT state on the
// same bar so the row can never show an iBOS/iSOS that has no drawing behind it.
```

## [63] Valid whenever a live internal break exists for the CURRENT external swi

```
// Valid whenever a live internal break exists for the CURRENT external swing.
// (The external-break clear above is what scopes it — no fib-origin comparison
// needed, since fiboStartIndex tracks the swing anchor, not the break bar, and
// could sit far enough back to let a stale internal break slip through.)
```

## [64] SOS FADE SEQUENCE — sweep → SOS → fib entry, IN ORDER

```
//============================================================
//  SOS FADE SEQUENCE — sweep → SOS → fib entry, IN ORDER
//============================================================
// The SOS Fade model is a sequence, not a checklist. Each stage only counts if the
// previous one is already done:
//   1. SWEEP — liquidity taken at a tracked HTF pool (H4 / PD / session H-L).
//      Those levels ARE the points of interest, so a sweep firing means price
//      both reached the POI and grabbed the resting stops there.
//   2. MSS — an external SOS that fires AFTER the sweep, within the window.
//   3. ENTRY — the SOS leg's fib retracement:
//        0.5 tapped   -> SOS FADE EARLY  (early entry tier)
//        0.618 reached -> SOS Fade READY (full entry zone, E1-E3)
//      A live clean FVG overlapping the entry zone is flagged as confluence.
// The sequence dies on: opposite SOS, close past the fib 1.0 (leg invalidated),
// or TP3 hit (cycle complete). It then waits for the next sweep.
```

## [65] Debug only — remembers WHICH source currently holds the Stage-1 slot on 

```
// Debug only — remembers WHICH source currently holds the Stage-1 slot on each
// side, so the 2-of-3 debug marker can label the arm correctly. Read-only
// bookkeeping; nothing here feeds the engine or trade logic.
```

## [66] One missed-setup callout = ONE SMALL ORANGE TAG. Single static colour

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

## [67] ── MISSED-SETUP watch state ────────────────────────────────────────────

```
// ── MISSED-SETUP watch state ─────────────────────────────────────────────────
// Everything one side needs to remember about a live setup, held as a single
// OBJECT rather than thirteen loose `var`s. Pine objects are passed by reference,
// so the two functions below can mutate this state from inside a function — which
// is the whole point: the tracking and the callout together are ~90 statements,
// and the main body has a hard cap on how many it may hold (CE10295). Same
// pattern as PosBox / TradeLbl further down.
```

## [68] Track the live setup, then draw the callout when it dies without trading

```
// Track the live setup, then draw the callout when it dies without trading.
// Returns the log line (empty string when nothing was reported), so the chart box
// and the Pine Log can never tell different stories — they are built from one
// string. Every gate is a PARAMETER, not a global read, so what counts as a
// confluence is decided by the caller from the live strategy inputs.
```

## [69] A NEAR miss is one worth looking at: it either met all three and still

```
            // A NEAR miss is one worth looking at: it either met all three and still
            // did not fill, or it got price into the zone and failed only on the FVG.
            // "Price never retraced" is the ordinary outcome of most setups and is
            // what floods the chart, so the default view leaves it out.
```

## [70] Stagger: every third callout on this side sits back at the base

```
                // Stagger: every third callout on this side sits back at the base
                // height, so two that land near each other never print on top of
                // one another even after the vertical clearance is applied.
```

## [71] HTF POI — the Cycle Fib's zones, tracked on every timeframe (drawing sta

```
// HTF POI — the Cycle Fib's zones, tracked on every timeframe (drawing stays gated):
// longs care about the DISCOUNT (0.618-0.886 of the cycle), shorts about the
// PREMIUM (0.382 up to the extreme). Latched while a sweep is armed, so a deeper
// tag of the zone after the sweep still counts.
```

## [72] Stage 1 — arm on the EXACT bar a NEW sweep or NEW divergence fires (true

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

## [73] Daily-level sweeps go stale after one day — a "Day Low" sweep from 3 day

```
// Daily-level sweeps go stale after one day — a "Day Low" sweep from 3 days ago
// is no longer meaningful fuel for a fresh setup. Only the PREVIOUS day's sweep
// (or newer) counts; H4/session sweeps are inherently short-lived already and
// aren't capped here.
```

## [74] A SWEEP arms only when nothing is already tracking on this side — a rota

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

## [75] Retro-link — a divergence pivot only CONFIRMS divPivotLen bars after the

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

## [76] Clear a stale arm — sweep/div fired but no SOS followed within the windo

```
// Clear a stale arm — sweep/div fired but no SOS followed within the window.
// Without this, aplusL_sweepBar stays set FOREVER even after the SOS Fade row has
// already fallen back to "Pass" (the display checks the window; this variable
// didn't), which permanently blocked CONT from ever arming again.
// Skipped on a session-gap bar: `time` jumps by far more than the normal bar
// spacing there and the daily security bar rolls, which was falsely tripping
// this clear and resetting live arms across the 17:00-18:00 close.
```

## [77] SOS Fade leg resolution: completion (TP3), invalidation (close past 1.0 or fib

```
// SOS Fade leg resolution: completion (TP3), invalidation (close past 1.0 or fib
// flipped), or a CONTINUATION BOS once the SOS stage was already reached. That
// last case is the one you're describing: the SOS fires, price never completes
// the retrace, and instead breaks structure again in the same direction — the
// leg has moved on without ever giving the fib entry, so the SOS Fade's premise is
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

## [78] B LEG SETUP — the SOS whose retrace arrived late

```
//============================================================
//  B LEG SETUP — the SOS whose retrace arrived late
//============================================================
// Ported from mpc_jarvis.pine (tracker only — no chart box; the strategy's
// own trade drawing visualises the fill). An SOS fires, price expands and prints
// a continuation BOS BEFORE it ever retraces, so the REV leg above just died at
// 2/3 ("no retracement"). On a higher timeframe that is ONE clean leg and the
// retrace DOES arrive, later — into the Sniper-Zone band (0.382-0.5) frozen at
// the ORIGINAL SOS. The B leg freezes that band and waits for price to trade
// back into it. Runs fully PARALLEL to the SOS Fade engine: it only READS st.* and the
// bLegArm flags captured above, and never writes SOS Fade state.
```

## [79] Freeze the SZ band on every SOS — the SAME 0.382/0.5 maths the drawn Sni

```
// Freeze the SZ band on every SOS — the SAME 0.382/0.5 maths the drawn Sniper
// Zone uses. inv = the leg origin (fib 1.0): a close past it means the reversal
// failed outright. DEEPEST BAND WINS: a fresh same-side SOS while a leg is live
// and UNTAPPED keeps whichever band is FARTHER from price (the deeper retrace
// target), migrating the watch rather than resetting it; the target (expansion
// extreme = TP reference) is extended, never rewound. A TAPPED leg never blocks
// a replacement.
```

## [80] Death: a close past the leg origin (1.0), or the staleness cap. NO SOS i

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

## [81] (CONT — the continuation trade type — was removed from this file 2026-07

```
// (CONT — the continuation trade type — was removed from this file 2026-07-21.
//  It was display-only here: nothing in the execution layer ever read
//  contL_bosBar / contS_bosBar / contL_stage / contS_stage, so deleting it
//  changes no trade, fill or stat. Removed to free compile tokens.)
```

## [82] Stage 3 — entry zone progress on the SOS leg's fib

```
// Stage 3 — entry zone progress on the SOS leg's fib
// EARLY = 0.5 tapped inbound, READY = 0.618 reached (E1-E3 zone live)
// Latch the SOS Fade's own 0.5/0.618 progress while its SOS is live. These persist
// through a fib-origin redraw (which happens at the session gap and would
// otherwise reset the global fiboHalfReached/618 flags, dropping EARLY→2/3).
```

## [83] ── SOS Fade veto, SOS-aware ──────────────────────────────────────────────────

```
// ── SOS Fade veto, SOS-aware ────────────────────────────────────────────────────
// A divergence that prints AFTER the SOS does NOT veto its own setup. Once
// stage 2 is live the setup is deliberately waiting on a retrace, and an
// opposing divergence formed during that retrace is the pullback itself —
// weakness in the counter-move, not a reversal of the leg we just broke with.
// (Real case: bullish SOS, bear div fires on the pull back into the fib band,
// entry blocked.) Only a divergence already live at or before the SOS bar
// still blocks the side; before stage 2 (no SOS yet) nothing changes.
// Extreme RSI keeps blocking LIVE — this exemption covers divergence only.
```

## [84] ── MISSED-SETUP watch — opened the moment a setup confirms Arm + SOS, an

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

## [85] The whole render lives in a function, including its own barstate gate, s

```
// The whole render lives in a function, including its own barstate gate, so the
// main body pays for exactly ONE statement instead of ~60. Pine caps how many
// statements the main body may hold (CE10295: "The main body of the script is
// too long"), and this table is by far the largest block in it. Same trick as
// f_drawStats / f_posBox below. Everything it reads is a global declared above.
```

## [86] SOS FADE — the reversal sequence ONLY (sweep → SOS → entry). Once TP3

```
            // SOS FADE — the reversal sequence ONLY (sweep → SOS → entry). Once TP3
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

## [87] Wipe any leftover cells below the last drawn row. Without this, a tick

```
        // Wipe any leftover cells below the last drawn row. Without this, a tick
        // that draws FEWER rows than the previous one leaves the old rows visible
        // (e.g. a ghost duplicate of the final row after a row above disappears).
```

## [88] MPC- JARVIS WATERMARK

```
//============================================================
//  MPC- JARVIS WATERMARK
//============================================================
```

## [89] STRATEGY EXECUTION — SOS Fade sequence entries + scaled fib-target exits

```
//============================================================
//  STRATEGY EXECUTION — SOS Fade sequence entries + scaled fib-target exits
//============================================================
// This is the ONLY block that is not part of the mpc_jarvis.pine engine.
// It reads the SOS Fade state the engine already computes and turns it into orders.
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

## [90] INPUTS MOVED 2026-07-28 — every Strategy Execution input now lives in ON

```
// INPUTS MOVED 2026-07-28 — every Strategy Execution input now lives in ONE block
// near the top of the file (search "STRATEGY EXECUTION INPUTS"), ordered the way a
// trade happens and with each dependent setting greyed out by its parent. They had
// to move rather than be reordered in place: two of them (execConfSZ, bLegMaxDays)
// are read by engine code far above this point, and Pine needs the declaration
// first, so leaving the rest here would always strand those two at the top of the
// panel. Nothing about the LOGIC below changed — this block still owns the
// behaviour, it just no longer owns the declarations. Mirrors sos_fade_strategy.pine.
//
// Adding a new execution input? Declare it in that block, in the section it
// belongs to, and give it `active =` if another input can make it irrelevant.
```

## [91] ── Breakeven band ──────────────────────────────────────────────────────

```
// ── Breakeven band ────────────────────────────────────────────────────────────
// TradingView's "Breakevens: 0" is an artifact: our breakeven stop sits a few
// ticks BEYOND entry (to cover commission), so a breakeven trade books a tiny
// profit and TradingView files it as a winner. The trade label and the diagnostic
// log grade honestly instead — anything inside +/- this band is a BREAKEVEN.
```

## [92] Frozen trade levels — snapshotted while armed so live fib recomputation 

```
// Frozen trade levels — snapshotted while armed so live fib recomputation on
// later bars cannot drag the stop/targets of an open trade (the leg's fib is
// stable during a retrace; it only moves when the leg dies, which cancels us).
```

## [93] B-LEG execution state — a B leg reuses the "Long"/"Short" entry id and a

```
// B-LEG execution state — a B leg reuses the "Long"/"Short" entry id and all the
// frozen SL/TP/label/posBox machinery below, so only two extra things are needed:
// a per-B-leg "already traded" guard and a flag routing the fill to it.
```

## [94] Position-box state — one growing box per trade, painted by result on clo

```
// Position-box state — one growing box per trade, painted by result on close.
// Held as a single OBJECT rather than nine loose vars: Pine objects are passed by
// reference, so f_posBox() further down can mutate these fields from inside a
// function. Nine `var` declarations and the ~35 statements that drove them would
// otherwise sit in the main body, which Pine caps (CE10295).
```

## [95] The entry confluence label is kept as a HANDLE rather than fired and for

```
// The entry confluence label is kept as a HANDLE rather than fired and forgotten,
// so the bar the trade closes can rewrite it with the outcome — a colour-coded
// WIN / LOSS / BREAKEVEN result and the R it made, on top of the confluences
// that armed it. Same object-in-a-function trick as PosBox, same CE10295 reason.
```

## [96] Method 3 (execDeepFib) — the entry price for a DEEP gap whose NEAR EDGE 

```
// Method 3 (execDeepFib) — the entry price for a DEEP gap whose NEAR EDGE sits
// below the 0.618 line, or na when the near edge is shallower than 0.618 (those
// keep the normal exact-edge entry). The re-priced entry is the fib level just
// SHALLOWER than the gap's near edge — the level price reaches first on the way
// in. ONLY the near edge's position decides it: a real gap is often tall enough
// to span 0.702/0.786, and an earlier "gap body contains a level" exception was
// WRONG — it silently disqualified exactly these deep, multi-level gaps (the miss
// this is built to catch). What the body crosses is irrelevant; where the near
// edge lands is everything. Long near edge = gap top (_gT); short = gap bottom.
```

## [97] ── Entry EDGE — the exact price a resting limit sits at ────────────────

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

## [98] ── SNIPER ZONE — the SECOND accepted confirmation ──────────────────────

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

## [99] ── FVG TOUCHES 0.5 — the LEAST-FAVORABLE entry, a bottom-tier fallback ─

```
// ── FVG TOUCHES 0.5 — the LEAST-FAVORABLE entry, a bottom-tier fallback ──────
// A gap that STRADDLES the 0.5 line — the 0.5 must fall INSIDE the gap body
// (gap bottom at/below 0.5 AND gap top at/above 0.5), not merely an edge near
// it. This is the shallowest possible entry, so it ranks LAST: it only prices a
// leg that no more-favorable source above already did (deep FVG edge, deep-fib
// re-price, Sniper Zone, reqFVG-off). The limit rests AT 0.5 (the level the gap
// touches). With "Gap must sit fully past 0.5" on, straddling gaps are otherwise
// rejected by the main loop, so this is the only path that trades them.
```

## [100] ── Arm-source filter — isolate WHICH Stage-1 confluence is allowed to ar

```
// ── Arm-source filter — isolate WHICH Stage-1 confluence is allowed to arm ────
// The engine treats a sweep and a divergence as interchangeable Stage-1 triggers
// and collapses both into ONE variable (aplus*_sweepBar), so by the time an SOS
// fires the origin of the arm is gone. We recover it here rather than editing the
// engine (which must stay byte-identical to mpc_jarvis.pine): keep the two arm
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

## [101] Retro-linked SOS: the snapshot above never ran for it, because on the SO

```
// Retro-linked SOS: the snapshot above never ran for it, because on the SOS bar the
// divergence had not confirmed yet. Take the snapshot now, measured against the SOS
// bar rather than this one, so a divergence-armed setup can actually trade.
```

## [102] A source only counts if you ENABLED it AND it was live at the SOS. The t

```
// A source only counts if you ENABLED it AND it was live at the SOS. The trade
// decision and the confluence label read these same two flags, so the label can
// never credit a confluence the trade did not use: with "Arm on liquidity sweep"
// off, a sweep that happened to be sitting there is not part of this trade's
// story and must not appear on it.
```

## [103] (The missed-setup callout used to fire here. It now lives further down, 

```
// (The missed-setup callout used to fire here. It now lives further down, after
//  the veto / late-day / HTF gates are declared, so it can name which one of them
//  actually blocked the entry — see "MISSED-SETUP CALLOUT" below.)
```

## [104] ── Armed conditions — setup to SOS, fib aligned, an edge exists, not vet

```
// ── Armed conditions — setup to SOS, fib aligned, an edge exists, not vetoed,
//    flat, and this leg not already traded ──
// Final-hour block: no new entries 16:00-17:00 NY (gold closes 17:00, reopens 18:00).
```

## [105] ── HTF exhaustion filter (loss-mitigation test #1) ─────────────────────

```
// ── HTF exhaustion filter (loss-mitigation test #1) ──────────────────────────
// The engine already grades each HTF bias as a breakout CLOSURE ("Close > Prev
// High" / "Close < Prev Low") or an exhaustion SWEEP ("Swept High" / "Swept
// Low"). We only ever want to fade the sweep, never fight a fresh breakout: a
// short (fading a high) is blocked when the HTF just closed ABOVE its prior high;
// a long (fading a low) when it just closed BELOW its prior low. Swept states
// never block. Read the desc strings so a sweep and a closure are told apart.
```

## [106] ── HTF-bias confluence (Daily + Weekly working TOGETHER) ───────────────

```
// ── HTF-bias confluence (Daily + Weekly working TOGETHER) ────────────────────
// Each timeframe carries a requirement judged against the trade's direction.
// "agree" = the TF bias matches the trade (Bullish for a long, Bearish for a
// short); "oppose" = the TF bias is against it. Returns TRUE = this TF blocks
// the trade. Neutral satisfies only "Must not oppose". Combine the two legs to
// express a forming reversal (Weekly opposes, Daily agrees) or full alignment
// (both agree) — the relationship between the two, not either one alone.
```

## [107] ── MISSED-DUE-TO-NO-FVG counter ────────────────────────────────────────

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

## [108] ══ MISSED-SETUP CALLOUT ════════════════════════════════════════════════

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

## [109] ── B-LEG arm — the frozen SZ band is live, untapped and valid, we're fla

```
// ── B-LEG arm — the frozen SZ band is live, untapped and valid, we're flat and
//    this band has not already been traded. SOS Fade has priority: while a fresh SOS Fade leg
//    is armed on the same side it owns the "Long"/"Short" limit and the B leg
//    stands down. Honours Trade longs/shorts + the final-hour block; it does NOT
//    use the arm-source, FVG or veto gates (the band tap is the whole trigger).
```

## [110] ══ BLOCKED-TRADE MARKER ════════════════════════════════════════════════

```
// ══ BLOCKED-TRADE MARKER ══════════════════════════════════════════════════════
// A B leg that was READY to rest its limit — the frozen band is live and untapped,
// its geometry is complete, we are flat, this band has not already been traded —
// and was stopped by one of YOUR OWN TOGGLES rather than by price.
//
// These are the only trades invisible everywhere else: no order is placed, so
// nothing is drawn, no row lands in the trade list, and the Strategy Tester cannot
// know they existed. Each one now prints a PINK tag with the reason on hover and a
// dotted leader down to the exact price the limit would have rested at — so you can
// flip the rule off, re-run, and compare.
//
// 🔴 THE CODE SET IS THIS FORK'S OWN AND IS DELIBERATELY NOT THE SOS Fade ONE. That file's
// codes name the arm source, the divergence veto and the two HTF filters, and NONE of
// them can refuse a B leg — the band tap is the whole trigger here, which the arm
// condition above says in words. Porting SOS Fade's codes across would print sentences that
// are the opposite of true in this file. What IS shared, and is the whole point of the
// exercise, is the DISPLAY: same pink, same "TRADE BLOCKED" text, same tooltip shape,
// same one-tag-per-setup-per-reason dedupe. The chart reads identically; only the
// reasons differ, because the refusals differ.
//
// ONE TAG PER BAND PER REASON: the dedupe key is the band's own bar plus the reason
// code, so a band blocked for twenty bars is one tag, not twenty — but if the reason
// CHANGES (SOS Fade stands down and the final hour then blocks it) that is a genuinely
// different refusal and gets its own tag.
//
// ⚠ THE SAVED-SLOT NOTE THAT SAT HERE IS OBSOLETE AND IS RECORDED AS SUCH RATHER THAN
// QUIETLY DELETED. It said declaring this input at its use site cost exactly one saved
// slot — `execDiagLog`, the only later bool — and told you to re-check "Log every trade
// to Pine Logs" after pasting. Both facts died hours later on 2026-08-12: the diagnostic
// log was deleted outright, and the whole panel moved into one consolidated block, which
// resets every saved value once by design. `showBlockTag` now lives in
// `8 · Chart annotations` with the other annotation switches; this declaration is a
// leftover at its old site and is scheduled to move into that block with the rest.
```

## [111] ⚠ THE LADDER TEST IS HOISTED OUT OF THE ENTRY BLOCK AND THE ENTRY BLOCK 

```
// ⚠ THE LADDER TEST IS HOISTED OUT OF THE ENTRY BLOCK AND THE ENTRY BLOCK NOW READS
// THESE BOOLS. It used to be an inline condition inside `if bLegLongArm`, so a band
// whose ladder does not price was cancelled silently — the one refusal here that is
// about the SETUP rather than about a switch you already know you flipped, and the
// only one you could not have found by reading your own inputs. Hoisting rather than
// re-deriving it at the tag is what stops the tag and the order disagreeing: there is
// ONE expression and two readers, not two expressions that happen to match today.
```

## [112] Reason PRECEDENCE — the first rule that would refuse the order is the on

```
// Reason PRECEDENCE — the first rule that would refuse the order is the one reported,
// so a tag can never blame a downstream gate for an upstream refusal. Ordered from the
// most upstream switch to the thing computed last, at placement.
//   1 B-leg entries off · 2 direction off · 3 SOS Fade has priority · 4 final hour · 5 ladder
```

## [113] ks carries the last (bandBar*10 + code) reported per side — the dedupe k

```
// ks carries the last (bandBar*10 + code) reported per side — the dedupe key.
// Trailing `int _blkDone = 0` for the same CE10235 reason as f_posBox: without it the
// drawing chain becomes the function's return expression and the branches disagree on type.
```

## [114] "Ready" deliberately omits every toggle gate — those ARE the blockers be

```
// "Ready" deliberately omits every toggle gate — those ARE the blockers being reported.
// It asserts only what price and the engine decide: a band is live, it has not been
// tapped, its three prices exist, we are flat, and this band has not already traded.
```

## [115] ── Long: SOS Fade ENTRY DISABLED in the B-LEG fork ───────────────────────────

```
// ── Long: SOS Fade ENTRY DISABLED in the B-LEG fork ──────────────────────────────
// longArmed is still computed above, so the "SOS Fade has priority" gate on the B-LEG
// arm still stands a B-LEG down when an SOS Fade would have armed this side — the
// baseline behaviour of the parent's B leg. The difference here is only that SOS Fade
// never PLACES an order: when it owns the side we pull any resting B-LEG limit
// (the parent's SOS Fade would have overwritten the slot), which is the same
// stand-down outcome. All the SOS Fade SL/TP/qty/conf maths is dropped as dead code.
```

## [116] ── B-LEG entries — rest a limit at the frozen band's near (0.5) edge, re

```
// ── B-LEG entries — rest a limit at the frozen band's near (0.5) edge, reusing
//    the "Long"/"Short" id so the fill / exits / posBox / label all flow through
//    the same machinery. SL beyond the leg origin (fib 1.0). Ladder reuses the SOS Fade
//    shallow rungs from the frozen band: TP1 = the broken swing extreme (fib 0.0
//    of the band = 2·edge − origin), TP2 = the expansion extreme (bLeg*_tgt), TP3
//    = runner. pendIsBLeg* routes the fill to the B-leg "already traded" guard. ──
// B-LEG diagnostic context — appended to the entry conf so each B-leg log line
// carries the HTF bias, session and cycle zone at fill, to profile the losers.
```

## [117] ⚠ Reads the hoisted `bLegL_ok` rather than repeating the three compariso

```
    // ⚠ Reads the hoisted `bLegL_ok` rather than repeating the three comparisons. The
    // blocked-trade tag above reports code 5 off this SAME bool, so the chart cannot
    // claim a refusal the order did not make, or miss one it did.
```

## [118] ── Mark the leg traded once the resting limit FILLS; snapshot the entry 

```
// ── Mark the leg traded once the resting limit FILLS; snapshot the entry price
//    and reset the stop stage. Reset stage to 0 whenever we are flat. ──
// Offset the confluence label well clear of the candles (longs below, shorts
// above) and drop a thin line from the entry price to the label so it still
// points at the exact entry without covering the price action. The multiplier is
// an input because it is the ONLY control over where the hover tooltip opens —
// TradingView anchors the tooltip to the label and exposes no placement API.
```

## [119] While the trade is OPEN the label is grey — the result is not known yet 

```
// While the trade is OPEN the label is grey — the result is not known yet and
// colouring it by direction would be a claim the chart cannot back up. Direction
// is already on the label in words ("▲ LONG") and under the candle as a triangle.
//
// The chart shows ONE LINE. The arm source, SOS age, FVG/POI/DIV flags and the
// full entry / stop / TP ladder with real prices are in the label's TOOLTIP.
```

## [120] On the bar the trade closes: recolour by RESULT and append the R. Green 

```
// On the bar the trade closes: recolour by RESULT and append the R. Green won,
// red lost, ORANGE breakeven — a trade that went out and came back to entry is a
// breakeven, not a win, and the colour has to say so. Graded against the SAME
// breakeven band the diagnostic log uses, so the label and the log can never
// disagree about the same trade.
// The result filter is applied here rather than at entry because the result is
// what it filters on — a label that fails it is deleted the moment it is graded.
```

## [121] ── Grade the trade the bar it closes: WIN / LOSS / BREAKEVEN in R, not i

```
// ── Grade the trade the bar it closes: WIN / LOSS / BREAKEVEN in R, not in cents ─
// Graded once and handed to the entry label and the diagnostic log, so the two
// can never tell different stories about the same trade.
```

## [122] ── Position box — the trade drawn as STACKED BANDS, not as loose lines ─

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

## [123] One banked target: its slice of the move, a faint dashed line at the exa

```
// One banked target: its slice of the move, a faint dashed line at the exact fill
// price, and its tag. Every tag is anchored at the SAME x (lx = the trade's right
// edge), so TP1/TP2/TP3 stack in one column off to the side instead of scattering
// across the candles at the bar each happened to fill on.
// (`from` / `to` are NOT usable as parameter names — `to` is the for-loop keyword
//  and the parser rejects the whole declaration, blaming the first parameter.)
```

## [124] 2. Bank any exits that filled. They are RECORDED here and DRAWN on close

```
        // 2. Bank any exits that filled. They are RECORDED here and DRAWN on close,
        //    which is what lets all three tags share one right-hand edge. Runs before
        //    the paint below, so a trade that opens and closes on one bar still works.
```

## [125] A function's LAST statement is its return value, and the three branches

```
        // A function's LAST statement is its return value, and the three branches
        // above create a box / a box / a line — Pine refuses to pick a type for
        // that (CE10235). This constant sits after them so the drawing chain is
        // never the return expression. It is not busywork: remove it and the
        // script stops compiling.
```

## [126] Always-visible entry markers (the long/short position indicator itself) 

```
// Always-visible entry markers (the long/short position indicator itself) — a
// triangle at every fill, so you can never miss where a trade opened even when
// the result box is a thin scratch.
```

## [127] ── Advance the stop stage as each target is touched THIS bar, and ratche

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

## [128] f_swingRatchet — the structure trail that does not stand still. Same anc

```
// f_swingRatchet — the structure trail that does not stand still. Same anchor as the
// Structure trail (last confirmed swing ± buffer), but from there the stop climbs one
// `pct`-of-price step for every step of favourable move. The plain Structure trail sits
// at the swing however far price runs, which is where the runner's give-back comes from:
// the swing is a LAGGING anchor and in a strong leg it ends up a long way behind. Falls
// back to the bare anchor until the move is one full step past it, so it is never LOOSER
// than the Structure trail — only equal or tighter. Copied verbatim from sos_fade_strategy.pine
// so the two forks keep ONE exit ladder; do not let the two copies drift.
```

## [129] lSL / sSL are only ever written while flat (longArmed requires position_

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

## [130] Runner trail candidate — the fixed-step ratchet, a structure trail parke

```
// Runner trail candidate — the fixed-step ratchet, a structure trail parked at the last
// confirmed swing (st.last_conf_low/high), or that same swing anchor with a % ratchet
// climbing off it. na = not engaged yet. (Ported from sos_fade_strategy.pine: the structure
// trail + TP2 floor 2026-07-26, the % ratchet 2026-07-28.)
```

## [131] ── The TIME STOP — the one exit lever driven by the clock, not by price 

```
// ── The TIME STOP — the one exit lever driven by the clock, not by price ─────────
// ⚠ THE NOTE THAT SAT HERE IS NOW BACKWARDS AND IS REPLACED RATHER THAN DELETED. It said
// these two inputs were declared at this line deliberately — as the file's last string
// and float — so adding them shifted no saved chart value, and that moving them up to the
// exec panel must never be "tidied up". Correct for its day; it died on 2026-08-12, when
// every input in this file moved into one consolidated panel block and the panel was
// renumbered. `execTimeStopMode` / `execTimeStopHrs` now live in `6 · Stop & targets`
// with the rest of the ladder, and that pass reset saved values once, knowingly.
// Ported from `sos_fade_strategy.pine` in the same commit; both forks share ONE exit ladder.
```

## [132] ── Manage open long: TP1 / TP2 scale-outs + a runner that only trails ──

```
// ── Manage open long: TP1 / TP2 scale-outs + a runner that only trails ──
// A rung sized 0% is SKIPPED, never placed. strategy.exit() treats qty_percent = 0 as
// "unspecified" and falls back to closing the WHOLE position at that limit, so calling it
// with 0 would turn "bank nothing here" into "bank everything here" — the exact opposite.
// Skipping leaves the runner leg as the only exit, which is what 0% means. The TP PRICES
// still drive the staged stop (lStage/sStage above) whatever the rung sizes are.
```

## [133] PARITY EXPORT — the B-LEG decision stream as plotted columns  _(only in b_leg_strategy_export.pine)_

```
//============================================================
//  PARITY EXPORT — the B-LEG decision stream as plotted columns
//============================================================
// THIS FILE = b_leg_strategy.pine + THIS appended block, nothing else changed
// except the strategy() title on line 40. The instrumented twin of the B-LEG
// strategy, the same way sos_fade_strategy_export.pine is the SOS Fade strategy's twin.
//
// Export it to CSV from a 15m XAUUSD chart ("Export chart data"), then:
//   command-center/backend/.venv/bin/python \
//     strategies/python/b_leg/tools/compare_bleg.py <that.csv> --warmup N
// Exit 0 = the Python bot's decision stream is bar-for-bar identical to this Pine.
//
// REGENERATE whenever b_leg_strategy.pine changes — the split point is exact:
//   sed -n '1,4580p' strategies/tradingview/b_leg_strategy.pine > strategies/tradingview/b_leg_strategy_export.pine
//   (4580 = `strategy.close("Short", comment = "opp SOS")`, the last line before the
//    DIAGNOSTIC LOG header at 4583 — re-grep it, this number moves on every edit)
//   then re-append this block and restore the line-40 title.
// The Diagnostic Log block is dropped in the export copy to stay under Pine's
// compiled-token cap (CE10117), exactly as the SOS Fade export does.
//
// WHAT IS DIFFERENT FROM THE SOS Fade EXPORT, and why the columns are not the same:
//   • `px_dec_bits`'s arm bits are the B-LEG arm (bLegLongArm/bLegShortArm), NOT
//     longArmed/shortArmed. In this fork SOS Fade never places an order — it only holds
//     priority — so diffing longArmed would test a decision that never happens.
//   • `px_edge` is the frozen band's 0.5 edge (bLegL_top / bLegS_bot), the price the
//     limit actually rests at, not an FVG edge.
//   • The `bl_*` columns are the B-LEG TRACKER's own state. They are the point of
//     this harness: the tracker is where all the new logic lives (band freeze,
//     deepest-band migration, target track, tap, staleness death), and a bug there
//     shows up as a wrong band price MANY bars before it becomes a wrong trade.
//     Without them a mismatch tells you only "a trade differs", not why.
//   • `cfg_strcodes` has no execSlLevel in this fork (the B-LEG's stop is its band
//     ORIGIN, not a fib on the SOS Fade leg), so the SL slot is pinned to the "1.0" code.
//     The shared decoder in compare_strategy.py then reads exec_sl_level = "1.0",
//     which is correct-and-unused here. Keep the slot rather than repacking, so one
//     decoder serves both exports.
//
// GOTCHA (from every other export in this repo): a plotted column MUST use a
// transparent colour, never `display.none` — TradingView drops display.none series
// from the CSV export. Keep the block small and PACKED (the base strategy already
// sits near Pine's main-body statement cap, CE10295).
```

## [134] DECISION STREAM (packed — compare_bleg.py unpacks with the same scheme):  _(only in b_leg_strategy_export.pine)_

```
// DECISION STREAM (packed — compare_bleg.py unpacks with the same scheme):
//   px_dec_bits = bLegLongArm·1 + bLegShortArm·2 + (entryDir==1?4:entryDir==-1?8:0)
//   px_edge     = the armed side's resting-limit price (the band's 0.5 edge)
//   px_stages   = aplusL_stage·10 + aplusS_stage — the SOS Fade sequence still runs (the
//                 B leg arms off its death), so a drift there is the FIRST place a
//                 B-LEG mismatch will actually originate.
```

## [135] The frozen ladder of the OPEN trade. The B LEG computes its own TP1/TP2   _(only in b_leg_strategy_export.pine)_

```
// The frozen ladder of the OPEN trade. The B LEG computes its own TP1/TP2 off the
// band (TP1 = 2·edge − origin, TP2 = the expansion extreme) instead of reading fib
// levels, so these are load-bearing and get their own columns.
```

## [136] B-LEG TRACKER STATE — the whole point of this harness (see the note abov  _(only in b_leg_strategy_export.pine)_

```
// B-LEG TRACKER STATE — the whole point of this harness (see the note above).
//   bl_bits = l_on·1 + l_tap·2 + s_on·4 + s_tap·8
//   bl_bars = (bLegL_bar+1)·1e6 + (bLegS_bar+1)   [0 in a slot => na]
```

## [137] CONFIG (packed) — the SAME scheme sos_fade_strategy_export.pine uses, so  _(only in b_leg_strategy_export.pine)_

```
// CONFIG (packed) — the SAME scheme sos_fade_strategy_export.pine uses, so
// compare_strategy.config_from_export decodes both. cfg_bits packs 17 booleans;
// bit 16384 is execAplus, which in THIS fork means "SOS Fade holds priority", and bit
// 32768 is execBLeg, which here defaults ON. cfg_strcodes' SL slot is pinned to
// the "1.0" code (4) — see the note above. cfg_bleg_days is this fork's only extra.
// cfg_exitmode's TENS digit is the runner trail method, and since 2026-07-28 it is a
// THREE-way code (0 fixed / 1 structure / 2 structure + % ratchet) exactly as the SOS Fade
// export packs it — it used to collapse everything non-fixed to 1, which would have
// decoded the ratchet as the plain structure trail and diffed a ratcheted Python
// against a ratcheted Pine while calling both "Structure (swing)". cfg_trail_pct
// carries the ratchet step alongside it.
```

## [138] TIME STOP (2026-08-05) — the shared exit ladder's clock lever, carried h  _(only in b_leg_strategy_export.pine)_

```
// TIME STOP (2026-08-05) — the shared exit ladder's clock lever, carried here so
// `compare_bleg.py` configures the Python side FROM the export rather than from a default.
// Same encoding as the SOS Fade export, and deliberately NOT folded into cfg_exitmode (that column
// is the two ladder dropdowns).
//   cfg_time_stop = Off?0 : Before TP1 only?1 : Always?2
// An export with NO cfg_time_stop column predates this and ran the lever OFF.
```

## [139] EQ/FVG COUPLING (2026-08-06) — `eqExemptFvg`, a gap on an active EQH/EQL  _(only in b_leg_strategy_export.pine)_

```
// EQ/FVG COUPLING (2026-08-06) — `eqExemptFvg`, a gap on an active EQH/EQL surviving the FVG
// cap. It decides WHICH GAPS EXIST, so it decides which entries fire.
// ⚠ It defaults **false** in this fork and **true** in `sos_fade_strategy.pine`, and that fork is
// real, not drift — which is exactly why the column has to exist HERE too. `b_leg` pins the
// Python side off to match, so today both sides read 0; the column is what makes that a
// MEASURED agreement rather than two defaults that happen to line up. The SOS Fade pair went red for
// three days on this input precisely because nothing carried it.
//   cfg_eq_exempt = 0 (off) : 1 (on)
// An export with NO cfg_eq_exempt column predates this and ran it OFF.
```

