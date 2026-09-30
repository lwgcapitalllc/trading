#!/usr/bin/env python3
"""build_extreme_leg.py — assemble extreme_leg_strategy.pine.

The file embeds the external structure state machine TWICE — once on the chart's own 5-minute bars
(the change of character that arms the trade) and once on 15-minute bars aggregated in code (the
trend, and the swing that is the target). The second copy is DERIVED by
`derive_htf_structure.py`, never retyped, so the two cannot drift silently.

Run `derive_htf_structure.py` first, then this. Both are idempotent. `--check` writes nothing and
exits 1 if the committed parent differs from what this would write.

It writes the strategy you trade, then hands it to `build_export_twins.py` for its EXPORT TWIN —
the same file with a block of `plot()` calls appended that write the per-bar decision stream into a
CSV, so `compare_extreme_leg.py` can read the Pine's mind bar by bar rather than guessing from a
trade list. ⚠ The bodies are IDENTICAL by construction: the twin is the same string with a
different title and a tail. This file generated its twin first; since 2026-09-10 the shared builder
generates all six the same way, because a twin that has drifted from its parent proves parity
against a file nobody trades. The block itself is `export_blocks/extreme_leg_strategy.pine`.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STRAT = HERE.parent
SRC = STRAT / "h4_sweep_strategy.pine"
DERIVED = HERE / "_derived_structure_15.pine"
OUT = STRAT / "extreme_leg_strategy.pine"

START = "type SMCStructure"
END = "// [doc 18] EXECUTION — EXTERNAL STRUCTURE"

src = SRC.read_text()
native = src[src.index(START) : src.index(END)].rstrip() + "\n"
derived = DERIVED.read_text()
# the derived file's own DO-NOT-EDIT banner is about the file, not about the embed
derived = derived.split(
    "// ─────────────────────────────────────────────────────────────────────────────\n"
)[-1]

HEAD = """// This Pine Script® code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/ MPL-2.0
//@version=6
// [doc 1] EXTREME LEG — the run INTO the shift of structure, not the fade after it  -> docs/extreme_leg_strategy.md
strategy("Extreme Leg", overlay = true, initial_capital = 10000,
  default_qty_type = strategy.fixed, default_qty_value = 1, pyramiding = 0,
  calc_on_every_tick = false, process_orders_on_close = true,
  max_lines_count = 500, max_labels_count = 500, max_boxes_count = 500)

// [doc 2] RUN THIS ON A 5-MINUTE CHART. The 15-minute half is aggregated in code, so the
// chart timeframe is not a preference — it is the frame the trigger is measured on.
// [doc 3] THE INPUT PANEL — twelve numbered sections, house contract  -> docs/extreme_leg_strategy.md

G1 = "1 · Confirmation Table"
G2 = "2 · Market Structure"
G3 = "3 · What trades"
G4 = "4 · What arms it"
G6 = "6 · Stop & targets"
G7 = "7 · Filters"
G8 = "8 · Chart annotations"
G11 = "11 · Drawing: Liquidity"
G12 = "12 · Debug"

// ── 2 · Market structure ────────────────────────────────────────
// [doc 4] ⚠ TWO of the house's four toggles are absent here, deliberately  -> docs/extreme_leg_strategy.md
bool showExternal    = input.bool(true,  "Show External Structure", group = G2, display = display.none)
bool showSwingLabels = input.bool(false, "Show Swing Point Labels", group = G2, tooltip = "Off hides the swing point labels, leaving just BOS and SOS. Nothing else changes.", display = display.none)
bool showHtfSwing    = input.bool(true,  "Show the 15-minute swing being aimed at", group = G2, tooltip = "Draws the higher-timeframe swing the setup is measured against. The take profit sits PART of the way to it — see the take profit setting under Stop & targets.")

// ── 3 · What trades ─────────────────────────────────────────────
bool   execLongs  = input.bool(true, "Trade longs",  group = G3, tooltip = "Lets long setups trade. Off = shorts only.")
bool   execShorts = input.bool(true, "Trade shorts", group = G3, tooltip = "Lets short setups trade. Off = longs only.")
string sizeMode   = input.string("Risk % of equity", "Position sizing", options = ["Risk % of equity", "Fixed contracts"], group = G3, tooltip = "Risk % of equity makes every trade exactly 1R, so results compound. Fixed contracts uses the same quantity whatever the stop.")
float  riskPct    = input.float(1.0, "   ↳ Risk % per trade", minval = 0.01, maxval = 100, step = 0.1, group = G3, active = sizeMode == "Risk % of equity", tooltip = "Every trade risks this much of equity, so every trade is 1R and the R numbers mean the same thing throughout.")
float  fixedQty   = input.float(1.0, "   ↳ Contracts", minval = 0.01, step = 0.01, group = G3, active = sizeMode == "Fixed contracts")

// ── 4 · What arms it ────────────────────────────────────────────
int  sweptMinutes = input.int(180, "A level must have been swept within (minutes)", minval = 15, maxval = 1440, step = 15, group = G4, tooltip = "How recently liquidity must have been taken for a change of character to count. Nothing arms without a sweep.")
bool reqCounterTrend = input.bool(true, "Only against the 15-minute trend", group = G4, tooltip = "On = the swing being aimed at must be a change of character rather than a continuation. Off doubles the trade count and halves the quality.")
bool useH4Level      = input.bool(true, "Arm on a 4-hour level", group = G4, tooltip = "The previous 4-hour candle's high and low. The most frequent level, and the weakest of the ones that work.")
bool useSessionLevel = input.bool(true, "Arm on a session level", group = G4, tooltip = "The last completed Asia, London or New York session's high and low. One of the two strongest.")
bool useDailyLevel   = input.bool(true, "Arm on the previous day's level", group = G4, tooltip = "Yesterday's high and low. The strongest single family measured.")
bool useWeeklyLevel  = input.bool(true, "Arm on the previous week's level", group = G4, tooltip = "Last week's high and low. Too rare on its own to have been measured either way.")
int  minFamilies     = input.int(1, "Levels that must agree", minval = 1, maxval = 4, group = G4, tooltip = "How many different kinds of level must have been swept together. Two is better than one and cuts the trade count in half.")
bool skipFriday      = input.bool(true, "Never open a trade on a Friday", group = G4, tooltip = "Friday setups were measured as free: 40 of them over eight years returned +1.1R between them, while accounting for 25 of the losses. Skipping them left the money unchanged and cut the worst losing run from 9.7 to 7.9 times the risk. The day is read in UTC, which is how it was measured.")

// ── 6 · Stop & targets ──────────────────────────────────────────
int   extremeMinutes = input.int(120, "Look back for the extreme (minutes)", minval = 15, maxval = 720, step = 15, group = G6, tooltip = "The stop goes beyond the lowest low (or highest high) of this window. That extreme is what the trade is betting has held.")
float stopBufferAtr  = input.float(0.20, "Stop buffer (ATR)", minval = 0.0, maxval = 1.0, step = 0.01, group = G6, tooltip = "Extra room beyond the extreme, as a fraction of the average range. 0 puts the stop exactly on the extreme. 0.20 was measured as the best of 0.00 to 0.50 and the curve either side of it is smooth.")
float tpFrac         = input.float(0.5, "Take profit at this much of the way to the swing", minval = 0.1, maxval = 1.0, step = 0.05, group = G6, tooltip = "1.0 aims at the swing itself. 0.5 books half the distance and was measured as the best of 0.35 to 0.65 — it wins far more often, and because only one position is held at a time, getting out sooner frees the slot for the next setup.")
bool  useBreakeven   = input.bool(false, "Move the stop to breakeven", group = G6, tooltip = "Off by default. Moving it early converts winners into scratches; moving it late is worth almost nothing.")
float beArmFrac      = input.float(0.7, "   ↳ Arm at this much of the way to the target", minval = 0.1, maxval = 0.99, step = 0.05, group = G6, active = useBreakeven, tooltip = "How far price must travel before the stop moves up. Below about two thirds this costs money.")

// ── 7 · Filters ─────────────────────────────────────────────────
float minR       = input.float(2.0, "Refuse a target nearer than (R)", minval = 0.0, maxval = 20.0, step = 0.5, group = G7, tooltip = "Refuses a setup whose swing is closer than this many stops. Without it most setups have no room to pay.")
float minStopUsd = input.float(0.0, "Minimum stop distance ($)", minval = 0.0, step = 0.1, group = G7, tooltip = "Refuses a stop tighter than this. A tight stop does not make the risk small, it makes the position large. 0 switches it off.")

// ── 8 · Chart annotations ───────────────────────────────────────
// [doc 3a] SOS Fade's controls, in SOS Fade's order, at SOS Fade's defaults  -> docs/extreme_leg_strategy.md
bool   execShowConfLabel = input.bool(true, "Show entry confluence label", group = G8, tooltip = "Prints one label per trade. Hover it for the full breakdown; it recolours by result and shows the R on close.")
string execLabelWhich    = input.string("All", "   ↳ keep labels for which results", options = ["All", "Wins only", "Losses only", "Losses + breakevens", "None"], group = G8, active = execShowConfLabel, tooltip = "Which trades keep their label once the result is known. The rest are deleted on the bar the trade closes.")
float  execLabelOff      = input.float(6, "   ↳ label distance from price (ATR)", group = G8, minval = 1, maxval = 40, step = 1, active = execShowConfLabel, tooltip = "How far the label sits from the entry, in ATRs. Push it out so the hover opens over empty space instead of the candles.")
bool   execShowPosBox    = input.bool(true, "Show position box (result)", group = G8, tooltip = "Draws one box per trade showing the result: green to the take-profit fill, red to the exit on a loss.")
bool   execShowExitLines = input.bool(true, "   ↳ Label the target band", group = G8, active = execShowPosBox, tooltip = "Tags the take-profit fill at its real price. Off = the green band still paints, just untagged.")
float  execBeBandR       = input.float(0.15, "Breakeven band (R)", group = G8, minval = 0, step = 0.05, tooltip = "A trade finishing within this many R of flat counts as a breakeven rather than a win or a loss.")
bool   showBlocked       = input.bool(true, "Mark blocked trades on chart (pink)", group = G8, tooltip = "Drops a pink tag whenever a setup armed and one of your rules refused it. Hover it for the reason.")
bool   showMissed        = input.bool(true, "Show missed setups (3 of 4 or better)", group = G8, tooltip = "Marks a 5-minute change of character that never traded but met at least 3 of the 4 things a trade needs, listing what was missing.")
string missFilter        = input.string("Near misses only", "Which misses to draw", options = ["Near misses only", "All misses", "4-of-4 only"], group = G8, tooltip = "Which misses to draw. Near misses only keeps the chart readable.")
int    debugDays         = input.int(3, "Only draw debug callouts from the last N days (0 = all)", group = G8, minval = 0, maxval = 365, tooltip = "Only draw callouts from the last N days. 0 = the whole history.")
bool   showSweeps        = input.bool(false, "Mark the sweep that armed it", group = G8, tooltip = "Prints a small grey tag on every bar that took a level. Drawing only.")

// ── 11 · Drawing: Liquidity ─────────────────────────────────────
bool showLevels = input.bool(false, "Draw the levels", group = G11, tooltip = "Draws the highs and lows this strategy watches. Drawing only — it changes nothing.")

// ── 12 · Debug ──────────────────────────────────────────────────
bool showDebug = input.bool(false, "Debug labels", group = G12)

// [doc 5] MARKET STRUCTURE — shared settings  -> docs/extreme_leg_strategy.md
color bullColor  = color.blue
color bearColor  = color.red
int   majorLength = 15
string structLabelSize = "Small"
float  pbBuffer        = 0.0

f_structSize() =>
    not showExternal ? size.auto : structLabelSize == "Tiny" ? size.tiny : structLabelSize == "Normal" ? size.normal : structLabelSize == "Large" ? size.large : structLabelSize == "Huge" ? size.huge : size.small

f_swingCol(color c) =>
    showSwingLabels ? c : color(na)

"""

MID = """
// [doc 6] EXECUTION — EXTERNAL STRUCTURE ON THE CHART'S OWN BARS
// This instance is the TRIGGER. Its change of character is what arms a trade.
var st = SMCStructure.new(majorLength)
ph = ta.pivothigh(high, majorLength, majorLength)
pl = ta.pivotlow(low,  majorLength, majorLength)
color extBullCol = showExternal ? bullColor : color(na)
color extBearCol = showExternal ? bearColor : color(na)
st.process(ph, pl, "", extBullCol, extBearCol)
if not na(st.ash_line)
    line.set_x2(st.ash_line, bar_index)
if not na(st.asl_line)
    line.set_x2(st.asl_line, bar_index)

// [doc 7] THE 15-MINUTE HALF — aggregated in code, never requested  -> docs/extreme_leg_strategy.md
// ⚠ Aggregation rather than `request.security` is deliberate. The state machine has to be FED, and
// a security call returns a value; feeding it three closed 5-minute bars at a time is the only way
// it sees the same bars a 15-minute chart would, in the same order, with no lookahead anywhere.
var float aggO = na
var float aggH = na
var float aggL = na
var float aggC = na
int t15 = time("15")
bool newPeriod = na(t15[1]) or t15 != t15[1]
var float doneO = na
var float doneH = na
var float doneL = na
var float doneC = na
bool periodClosed = false
if newPeriod
    if not na(aggO)
        doneO := aggO
        doneH := aggH
        doneL := aggL
        doneC := aggC
        periodClosed := true
    aggO := open
    aggH := high
    aggL := low
    aggC := close
else
    aggH := math.max(aggH, high)
    aggL := math.min(aggL, low)
    aggC := close

// [doc 8] 15-minute pivots, detected over the aggregated series
// `ta.pivothigh` reads the CHART's series, so it cannot be used here — the aggregate is not a
// series. This is the same rule applied by hand over a rolling window of completed 15m bars.
var float[] hh15 = array.new_float()
var float[] ll15 = array.new_float()
var int[]   bi15 = array.new_int()
float ph15 = na
float pl15 = na
int   pivBar = na
if periodClosed
    array.push(hh15, doneH)
    array.push(ll15, doneL)
    array.push(bi15, bar_index)
    int cap = majorLength * 2 + 1
    if array.size(hh15) > cap
        array.shift(hh15)
        array.shift(ll15)
        array.shift(bi15)
    if array.size(hh15) == cap
        float candH = array.get(hh15, majorLength)
        float candL = array.get(ll15, majorLength)
        pivBar := array.get(bi15, majorLength)
        bool isHigh = true
        bool isLow  = true
        for k = 0 to cap - 1
            if k != majorLength
                if array.get(hh15, k) >= candH
                    isHigh := false
                if array.get(ll15, k) <= candL
                    isLow := false
        ph15 := isHigh ? candH : na
        pl15 := isLow  ? candL : na

var st15 = SMCStructure15.new(majorLength)
if periodClosed
    st15.process15(ph15, pl15, "H", showHtfSwing ? bullColor : color(na), showHtfSwing ? bearColor : color(na), doneO, doneH, doneL, doneC, pivBar)
if showHtfSwing
    if not na(st15.ash_line)
        line.set_x2(st15.ash_line, bar_index)
    if not na(st15.asl_line)
        line.set_x2(st15.asl_line, bar_index)

// [doc 9] THE LEVELS — previous period highs and lows, and the last completed session's
// ⚠ `[1]` paired with `lookahead_on` is the non-repainting idiom for a PREVIOUS completed period.
// Either one alone repaints; the pair is what makes it safe.
f_prevHigh(string tf) => request.security(syminfo.tickerid, tf, high[1], lookahead = barmerge.lookahead_on)
f_prevLow(string tf)  => request.security(syminfo.tickerid, tf, low[1],  lookahead = barmerge.lookahead_on)
float h4H = f_prevHigh("240")
float h4L = f_prevLow("240")
float dH  = f_prevHigh("D")
float dL  = f_prevLow("D")
float wH  = f_prevHigh("W")
float wL  = f_prevLow("W")

// The last completed session's extremes, tracked on the chart rather than requested — a session is
// a clock window, not a timeframe, so there is nothing to request.
f_sess(string spec, string tz) =>
    bool inSess = not na(time(timeframe.period, spec, tz))
    var float runH = na
    var float runL = na
    var float lastH = na
    var float lastL = na
    if inSess
        runH := na(runH) or not inSess[1] ? high : math.max(runH, high)
        runL := na(runL) or not inSess[1] ? low  : math.min(runL, low)
    else if not inSess and inSess[1]
        lastH := runH
        lastL := runL
        runH := na
        runL := na
    [lastH, lastL]

// [doc 9a] 🔴 EACH WINDOW IS STATED IN ITS OWN CITY'S CLOCK, AND THE TIMEZONE IS NOT OPTIONAL
// This read three fixed strings with NO timezone until 2026-09-01, and a session string with no
// timezone resolves in the SYMBOL'S EXCHANGE CLOCK — New York for gold, daylight saving and all.
// So all three windows sat 4-5 hours later than their names, two of them tracked no real session
// at all, and the one labelled "London" was in fact the New York session under a wrong name.
// MEASURED over 38,747 M15 bars: the old "London" high and low equalled the house New York
// session's on 100.0% of bars, and the other eight pairings agreed on 0.0-8.0%.
// The parent this was ported from — `indicators/engines/mpc_jarvis.pine` — passes the timezone
// explicitly and always has; the port dropped the argument. `engines/sessions/` carries the same
// three windows and is what every measurement behind this strategy was taken through, so the fix
// makes the chart agree with its own parent AND with the numbers at the same time.
// ⚠ It CHANGES WHAT THIS TRADES. It is a correction, not a tuning, and it was not chosen by which
// version made more money — re-optimising around it would be picking a clock for its P&L.
[asiaH, asiaL] = f_sess("0900-1800", "Asia/Tokyo")
[ldnH,  ldnL]  = f_sess("0800-1700", "Europe/London")
[nyH,   nyL]   = f_sess("0800-1700", "America/New_York")

// [doc 10] SWEEP TRACKING — a level counts once, the first time price takes it
// ⚠ A level that has already been taken is dead until it is replaced. Without that, one level
// re-arms the strategy on every bar it sits under, and "a sweep happened" stops meaning anything.
var int lowSweepBar  = na
var int highSweepBar = na
var int lowFamilies  = 0
var int highFamilies = 0

// A level is TAKEN when price goes through it, once per level.
//
// 🔴 `needClose` EXISTS BECAUSE THIS FILE DISAGREED WITH ITS OWN PARENT (found by the first real
// parity run, 2026-09-02). Every family was tracked on a WICK. `engines/liquidity/` — which is
// 100% parity-validated against `indicators/engines/mpc_jarvis.pine` — takes a WEEKLY level
// only on a CLOSE through it, and the daily and lower families on a wick. The house engine and
// the parent indicator agreed with each other; this strategy file was the odd one out.
// ⚠ The direction was decided by the house standard, NOT by which rule made more money — the
// same call as the session-clock fix the day before. Do not re-optimise around it.
f_track(float lvl, bool isHigh, bool enabled, bool needClose = false) =>
    var float held = na
    var bool  taken = false
    bool fired = false
    if enabled and not na(lvl)
        if na(held) or lvl != held
            held := lvl
            taken := false
        if not taken
            float above = needClose ? close : high
            float below = needClose ? close : low
            if isHigh and above > held
                taken := true
                fired := true
            if not isHigh and below < held
                taken := true
                fired := true
    fired

bool swH4H  = f_track(h4H,  true,  useH4Level)
bool swH4L  = f_track(h4L,  false, useH4Level)
bool swDH   = f_track(dH,   true,  useDailyLevel)
bool swDL   = f_track(dL,   false, useDailyLevel)
bool swWH   = f_track(wH,   true,  useWeeklyLevel, true)   // weekly: CLOSE through, per the engine
bool swWL   = f_track(wL,   false, useWeeklyLevel, true)
bool swAsH  = f_track(asiaH, true,  useSessionLevel)
bool swAsL  = f_track(asiaL, false, useSessionLevel)
bool swLdH  = f_track(ldnH,  true,  useSessionLevel)
bool swLdL  = f_track(ldnL,  false, useSessionLevel)
bool swNyH  = f_track(nyH,   true,  useSessionLevel)
bool swNyL  = f_track(nyL,   false, useSessionLevel)

bool sessLowSwept  = swAsL or swLdL or swNyL
bool sessHighSwept = swAsH or swLdH or swNyH
int  lowFamNow  = (swH4L ? 1 : 0) + (sessLowSwept ? 1 : 0) + (swDL ? 1 : 0) + (swWL ? 1 : 0)
int  highFamNow = (swH4H ? 1 : 0) + (sessHighSwept ? 1 : 0) + (swDH ? 1 : 0) + (swWH ? 1 : 0)

int barsBack = math.max(1, math.round(sweptMinutes / math.max(1, timeframe.in_seconds() / 60)))
if lowFamNow > 0
    lowSweepBar := bar_index
    lowFamilies := lowFamNow
else if not na(lowSweepBar) and bar_index - lowSweepBar > barsBack
    lowFamilies := 0
if highFamNow > 0
    highSweepBar := bar_index
    highFamilies := highFamNow
else if not na(highSweepBar) and bar_index - highSweepBar > barsBack
    highFamilies := 0

bool lowArmed  = not na(lowSweepBar)  and bar_index - lowSweepBar  <= barsBack and lowFamilies  >= minFamilies
bool highArmed = not na(highSweepBar) and bar_index - highSweepBar <= barsBack and highFamilies >= minFamilies

if showSweeps and (lowFamNow > 0 or highFamNow > 0)
    label.new(bar_index, lowFamNow > 0 ? low : high, "swept", style = lowFamNow > 0 ? label.style_label_up : label.style_label_down, color = color.new(#999999, 45), textcolor = color.new(#101014, 0), size = size.tiny)

// [doc 11] THE SETUP  -> docs/extreme_leg_strategy.md
int lookbackBars = math.max(1, math.round(extremeMinutes / math.max(1, timeframe.in_seconds() / 60)))
float atrNow = ta.atr(50)
float extremeLow  = ta.lowest(low,  lookbackBars)
float extremeHigh = ta.highest(high, lookbackBars)

bool htfBear = st15.dir == -1
bool htfBull = st15.dir == 1

// [doc 12c] THE CALENDAR REFUSAL IS READ IN UTC, NOT IN THE CHART'S TIMEZONE
// It was measured in UTC, and a chart opened in New York would otherwise refuse a different set of
// bars than the one the number describes - silently, and only for part of the day.
bool isFriday = dayofweek(time, "UTC") == dayofweek.friday

bool rawLong  = st.bull_sos and execLongs  and lowArmed  and (not reqCounterTrend or htfBear)
bool rawShort = st.bear_sos and execShorts and highArmed and (not reqCounterTrend or htfBull)

float tgtLong  = st15.ash
float tgtShort = st15.asl
float entryPx  = close
float stopLong  = extremeLow  - stopBufferAtr * atrNow
float stopShort = extremeHigh + stopBufferAtr * atrNow
float riskLong  = entryPx - stopLong
float riskShort = stopShort - entryPx
float rLong  = riskLong  > 0 and not na(tgtLong)  ? (tgtLong  - entryPx) / riskLong  : na
float rShort = riskShort > 0 and not na(tgtShort) ? (entryPx - tgtShort) / riskShort : na

// [doc 12b] THE SWING IS WHAT THE SETUP IS MEASURED AGAINST; THE TAKE PROFIT IS PART OF THE WAY TO IT
// `rLong`/`rShort` above stay measured on the WHOLE distance to the swing, because that is what the
// minimum-target refusal is judging — how much room the setup has. `tpFrac` then decides where the
// order actually rests. Reducing the measured R instead would refuse setups on the size of the exit
// we chose rather than on the size of the move available, and the two are different questions.
float tpLong  = entryPx + (tgtLong  - entryPx) * tpFrac
float tpShort = entryPx - (entryPx - tgtShort) * tpFrac

// [doc 12d] THE REFUSAL LADDER IS WRITTEN ONCE, AS A NUMBER, AND THE TEXT IS DERIVED FROM IT
// The chart wants a sentence and the export twin wants a code. Writing the ladder twice is how
// two halves of one rule drift apart in silence — this repo has already measured that happening
// between a Python evaluator and its JavaScript twin. The number is the rule; `f_blkText` is a
// rendering of it. 0 means nothing refused it.
//   1 Friday · 2 no swing · 3 swing on the wrong side · 4 extreme on the wrong side
//   5 stop under the floor · 6 target nearer than the minimum
int blkLong  = 0
int blkShort = 0
if rawLong
    blkLong := skipFriday and isFriday ? 1 : na(tgtLong) ? 2 : tgtLong <= entryPx ? 3 : riskLong <= 0 ? 4 : minStopUsd > 0 and riskLong < minStopUsd ? 5 : rLong < minR ? 6 : 0
if rawShort
    blkShort := skipFriday and isFriday ? 1 : na(tgtShort) ? 2 : tgtShort >= entryPx ? 3 : riskShort <= 0 ? 4 : minStopUsd > 0 and riskShort < minStopUsd ? 5 : rShort < minR ? 6 : 0

f_blkText(int code, bool isLong) =>
    code == 1 ? "Friday - refused by the calendar" : code == 2 ? "no 15m swing to aim at" : code == 3 ? (isLong ? "the swing is already below us" : "the swing is already above us") : code == 4 ? (isLong ? "the extreme is above the entry" : "the extreme is below the entry") : code == 5 ? "stop tighter than the floor" : code == 6 ? "the swing is nearer than " + str.tostring(minR, "#.#") + "R" : string(na)

string blockLong  = blkLong  > 0 ? f_blkText(blkLong,  true)  : na
string blockShort = blkShort > 0 ? f_blkText(blkShort, false) : na

bool goLong  = rawLong  and blkLong  == 0
bool goShort = rawShort and blkShort == 0

// [doc 12] EXECUTION
// ⚠ ONE POSITION AT A TIME, and it is not a preference. Every number behind this file was measured
// with one slot; allowing a second changes the population the result describes.
f_qty(float risk) =>
    sizeMode == "Fixed contracts" or risk <= 0 ? fixedQty : (strategy.equity * riskPct / 100.0) / risk

var float tStop = na
var float tTgt  = na
var bool  beArmed = false

// [doc 12a] THE BAR THE ENTRY IS PLACED ON STILL READS FLAT, AND THAT COST AN ACCOUNT
// `process_orders_on_close` fills the entry AFTER this script has finished running for the bar,
// so `strategy.position_size` is still 0 everywhere below on the bar that opens the trade. These
// two flags are the only way this bar can tell "flat" from "just entered". Without them the reset
// at the bottom wiped the stop and the target back to na on the very bar they were set, the
// bracket went out empty on the next bar, and the position was never protected and never closed.
// The sibling `h4_sweep_strategy.pine` has carried the same pair since it was written.
bool tookLong  = false
bool tookShort = false
// A setup that TRADED was never refused (2026-09-30, the rule every bot shares). Each tag is kept
// with the sweep that armed it; the entry erases that sweep's tags and a traded sweep draws no
// more. Mirrors the Python order layer. Drawing only — no decision reads these.
var array<label> refLbl = array.new<label>()
var array<line>  refLn  = array.new<line>()
var array<int>   refKey = array.new<int>()     // sweep bar * 2 + side (0 long, 1 short)
var int tradedKeyL = na
var int tradedKeyS = na
f_refErase(int key) =>
    int i = array.size(refKey) - 1
    while i >= 0
        if array.get(refKey, i) == key
            label.delete(array.remove(refLbl, i))
            line.delete(array.remove(refLn, i))
            array.remove(refKey, i)
        i -= 1
    i

if goLong and strategy.position_size == 0
    strategy.entry("L", strategy.long, qty = f_qty(riskLong))
    tStop := stopLong
    tTgt  := tpLong
    beArmed := false
    tookLong := true
    tradedKeyL := lowSweepBar * 2
    f_refErase(tradedKeyL)
if goShort and strategy.position_size == 0
    strategy.entry("S", strategy.short, qty = f_qty(riskShort))
    tStop := stopShort
    tTgt  := tpShort
    beArmed := false
    tookShort := true
    tradedKeyS := highSweepBar * 2 + 1
    f_refErase(tradedKeyS)

if strategy.position_size != 0 and useBreakeven and not na(tTgt) and not na(tStop)
    float span = math.abs(tTgt - strategy.position_avg_price)
    if span > 0
        bool reached = strategy.position_size > 0 ? high >= strategy.position_avg_price + beArmFrac * span : low <= strategy.position_avg_price - beArmFrac * span
        if reached and not beArmed
            beArmed := true
            tStop := strategy.position_avg_price

// The bracket goes out on the ENTRY bar too, so it is live for the next bar's range rather than
// the one after that. `or tookLong` is what makes that possible — see [doc 12a].
if strategy.position_size > 0 or tookLong
    strategy.exit("L-x", from_entry = "L", stop = tStop, limit = tTgt)
if strategy.position_size < 0 or tookShort
    strategy.exit("S-x", from_entry = "S", stop = tStop, limit = tTgt)
// Flat AND we did not just enter. Dropping the second half is the bug in [doc 12a].
if strategy.position_size == 0 and not tookLong and not tookShort
    tStop := na
    tTgt  := na
    beArmed := false

// [doc 13] ANNOTATIONS — DRAWING ONLY. Nothing below is read by an order, a stop or a size  -> docs/extreme_leg_strategy.md
// Every trade colour is copied from sos_fade_strategy.pine, the house standard. Change it there first.
color POS_RED    = color.new(#EF5350, 62)
color POS_OPEN   = color.new(#787B86, 80)
color POS_ORANGE = color.new(#FF9800, 0)
color POS_GREENB = color.new(#26A69A, 0)   // solid borders so even a thin box is visible
color POS_REDB   = color.new(#EF5350, 0)
color POS_G1     = color.new(#26A69A, 55)  // the one target band — this file has no TP2 or TP3
color POS_DD     = color.new(#EF5350, 88)  // drawdown: behind everything, barely there
color TP_ANNOT   = color.new(#26A69A, 40)  // the target tag and its line
color BLK_PINK   = color.new(#FF2E9A, 12)
color BLK_PINKL  = color.new(#FF2E9A, 0)
color MISS_ORN   = color.new(#FF9800, 12)
color MISS_ORNL  = color.new(#FF9800, 0)
color LBL_TXT    = color.new(#101014, 0)

float annAtr    = ta.atr(14)
float annLo     = ta.lowest(low, 20)
float annHi     = ta.highest(high, 20)
bool  annRecent = debugDays == 0 or time >= timenow - debugDays * 86400000
bool  annFlat   = strategy.position_size == 0 and not tookLong and not tookShort

// Which kinds of level the latest sweep on each side took, and where — for the hovers only.
f_famTxt(bool h4, bool sess, bool day, bool week) =>
    string s = (h4 ? ", 4-hour" : "") + (sess ? ", session" : "") + (day ? ", previous day" : "") + (week ? ", previous week" : "")
    str.length(s) > 0 ? str.substring(s, 2) : "none"
var string lowFamTxt  = ""
var string highFamTxt = ""
var float  lowSweepPx  = na
var float  highSweepPx = na
if lowFamNow > 0
    lowFamTxt  := f_famTxt(swH4L, sessLowSwept, swDL, swWL)
    lowSweepPx := low
if highFamNow > 0
    highFamTxt  := f_famTxt(swH4H, sessHighSwept, swDH, swWH)
    highSweepPx := high

// [doc 13a] THE TRADE IS READ FROM THE EMULATOR'S OWN TRADE LIST, NOT FROM THE POSITION SIZE  -> docs/extreme_leg_strategy.md
// A trade that opens on one close and exits inside the next bar never shows a non-zero position.
var int    snapBar  = na    // bar the entry order went out on
var float  snapStop = na    // the stop it opened with — 1R
var float  snapTgt  = na    // the take profit it rested
var string snapBody = ""
var int    openBar  = na    // entry bar of the trade drawn open, na when none is
var label  tLbl     = na
var line   tLn      = na
var box    tBox     = na
var int    elSeen   = 0     // closed trades already drawn
int        fillDir  = 0     // a trade that filled on the PREVIOUS bar's close became visible here

f_elOpen(int dir, int x, float px, string body) =>
    string head = dir > 0 ? "▲ LONG" : "▼ SHORT"
    float  ly   = dir > 0 ? px - annAtr * execLabelOff : px + annAtr * execLabelOff
    line   ln   = line.new(x, px, x, ly, color = color.new(#787B86, 0), width = 1)
    label  lb   = label.new(x, ly, head, tooltip = head + "\\n" + body, color = color.new(#787B86, 12), textcolor = LBL_TXT, style = dir > 0 ? label.style_label_up : label.style_label_down, size = size.small)
    [lb, ln]

// On the bar the trade closes: recolour by RESULT and append the R, or delete it per the filter.
f_elGrade(label lb, line ln, int dir, float r, float net, string body) =>
    if not na(lb)
        bool   be   = not na(r) and math.abs(r) <= execBeBandR
        bool   won  = not be and (na(r) ? net > 0 : r > 0)
        string res  = be ? "BREAKEVEN" : won ? "WIN" : "LOSS"
        bool   keep = execLabelWhich == "All" or (execLabelWhich == "Wins only" and won) or (execLabelWhich == "Losses only" and not won and not be) or (execLabelWhich == "Losses + breakevens" and not won)
        if keep
            string line1 = (dir > 0 ? "▲ LONG" : "▼ SHORT") + "  ·  " + res + (na(r) ? "" : "  " + (r >= 0 ? "+" : "") + str.tostring(r, "#.##") + "R")
            label.set_text(lb, line1)
            label.set_tooltip(lb, line1 + "\\n" + body)
            label.set_color(lb, be ? color.new(#FF9800, 12) : won ? color.new(#26A69A, 12) : color.new(#EF5350, 12))
            line.set_color(ln, be ? color.new(#FF9800, 0) : won ? color.new(#26A69A, 0) : color.new(#EF5350, 0))
        else
            label.delete(lb)
            line.delete(ln)
    int _gDone = 0

// [doc 13b] The closed trade drawn as bands: drawdown behind, then ONE green band to the fill  -> docs/extreme_leg_strategy.md
f_elBox(int x1, int x2, int dir, float entry, float stop, float tgt, float best, float worst, float net) =>
    int lx = x2 + 4
    if dir > 0 ? worst < entry : worst > entry
        box.new(x1, math.max(entry, worst), x2, math.min(entry, worst), bgcolor = POS_DD, border_color = color(na))
    bool atTgt = not na(tgt) and (dir > 0 ? best >= tgt - syminfo.mintick : best <= tgt + syminfo.mintick)
    if atTgt
        box.new(x1, math.max(entry, best), x2, math.min(entry, best), bgcolor = POS_G1, border_color = color(na))
        if execShowExitLines
            line.new(x1, best, lx, best, color = TP_ANNOT, style = line.style_dashed, width = 1)
            label.new(lx, best, " TP", color = color(na), textcolor = TP_ANNOT, style = label.style_label_left, size = size.small)
    else if net < 0
        float redTo = na(best) ? stop : best
        box.new(x1, math.max(entry, redTo), x2, math.min(entry, redTo), bgcolor = POS_RED, border_color = POS_REDB)
    else
        line.new(x1, entry, x2, entry, color = POS_ORANGE, width = 2)
    int _bDone = 0

bool annLabels = execShowConfLabel and execLabelWhich != "None"

// Closed first: a trade can close and the next one be ordered on the same bar.
if strategy.closedtrades > elSeen
    for i = elSeen to strategy.closedtrades - 1
        int   eb    = strategy.closedtrades.entry_bar_index(i)
        float ep    = strategy.closedtrades.entry_price(i)
        float sz    = strategy.closedtrades.size(i)
        int   dir   = sz > 0 ? 1 : -1
        bool  mine  = not na(snapBar) and eb == snapBar
        float stop0 = mine ? snapStop : na
        float riskU = na(stop0) ? na : math.abs(sz) * math.abs(ep - stop0) * syminfo.pointvalue
        float net   = strategy.closedtrades.profit(i)
        float r     = na(riskU) or riskU <= 0 ? na : net / riskU
        float xPx   = strategy.closedtrades.exit_price(i)
        float worst = ep - dir * math.abs(strategy.closedtrades.max_drawdown(i)) / (math.abs(sz) * syminfo.pointvalue)
        string body = mine ? snapBody : ""
        if na(openBar) or eb != openBar
            // never seen open: it filled on one close and exited inside the next bar
            if eb == bar_index - 1
                fillDir := dir
            if annLabels
                [lb0, ln0] = f_elOpen(dir, eb, ep, body)
                tLbl := lb0
                tLn  := ln0
        f_elGrade(tLbl, tLn, dir, r, net, body)
        if not na(tBox)
            box.delete(tBox)
        if execShowPosBox
            f_elBox(eb, strategy.closedtrades.exit_bar_index(i), dir, ep, stop0, mine ? snapTgt : na, xPx, worst, net)
        tLbl    := na
        tLn     := na
        tBox    := na
        openBar := na
    elSeen := strategy.closedtrades

// Opened: the emulator holds a trade not drawn yet. Grey until the result is known.
if strategy.opentrades > 0
    int   eb = strategy.opentrades.entry_bar_index(0)
    float ep = strategy.opentrades.entry_price(0)
    if na(openBar) or eb != openBar
        openBar := eb
        int dir = strategy.opentrades.size(0) > 0 ? 1 : -1
        if eb == bar_index - 1
            fillDir := dir
        if annLabels
            [lb1, ln1] = f_elOpen(dir, eb, ep, not na(snapBar) and eb == snapBar ? snapBody : "")
            tLbl := lb1
            tLn  := ln1
        if execShowPosBox
            tBox := box.new(eb, math.max(ep, close), bar_index, math.min(ep, close), bgcolor = POS_OPEN, border_color = color.new(#787B86, 0), border_width = 1)
    else if not na(tBox)
        box.set_right(tBox, bar_index)
        box.set_top(tBox, math.max(ep, close))
        box.set_bottom(tBox, math.min(ep, close))

// [doc 13c] The triangles sit on the ENTRY bar: offset -1, because the fill is seen one bar later  -> docs/extreme_leg_strategy.md
plotshape(execShowPosBox and fillDir > 0, title = "Long entry",  style = shape.triangleup,   location = location.belowbar, color = POS_GREENB, size = size.small, offset = -1)
plotshape(execShowPosBox and fillDir < 0, title = "Short entry", style = shape.triangledown, location = location.abovebar, color = POS_REDB,   size = size.small, offset = -1)

// Blocked: the arming gates passed and a rule in the refusal ladder said no. Reads blkLong /
// blkShort, the same numbers the export writes, so the tag and the CSV cannot disagree.
int refK = not na(blockLong) ? lowSweepBar * 2 : highSweepBar * 2 + 1
int refT = not na(blockLong) ? tradedKeyL : tradedKeyS
if showBlocked and (not na(blockLong) or not na(blockShort)) and (na(refT) or refK != refT)
    bool   isL = not na(blockLong)
    float  yB  = isL ? annLo - annAtr * 2 : annHi + annAtr * 2
    array.push(refKey, refK)
    array.push(refLn, line.new(bar_index, entryPx, bar_index, yB, color = BLK_PINKL, style = line.style_dotted, width = 1))
    array.push(refLbl, label.new(bar_index, yB, (isL ? "▲" : "▼") + " TRADE BLOCKED", tooltip = (isL ? "▲ LONG" : "▼ SHORT") + " blocked\\n──────────────────\\n" + (isL ? blockLong : blockShort) + "\\n──────────────────\\nWould have entered at " + str.tostring(entryPx, format.mintick), color = BLK_PINK, textcolor = LBL_TXT, style = isL ? label.style_label_up : label.style_label_down, size = size.small))

// [doc 13d] MISSED SETUP — a change of character that never traded, scored 4 ways  -> docs/extreme_leg_strategy.md
// Levels · SOS · 15m trend · room to the swing. The SOS is always met: it is the bar being scored.
f_roomCode(float tgt, float risk, float r, bool isLong) =>
    na(tgt) ? 2 : (isLong ? tgt <= entryPx : tgt >= entryPx) ? 3 : risk <= 0 ? 4 : r < minR ? 6 : 0

f_miss(bool isLong, bool sos, int fam, int sweepBar, float sweepPx, string famTxt, bool trendOk, int room, float r, int rule, int tradedKey, float y) =>
    bool inWin = not na(sweepBar) and bar_index - sweepBar <= barsBack
    int  famN  = inWin ? fam : 0
    int  key   = inWin ? sweepBar * 2 + (isLong ? 0 : 1) : -1
    if showMissed and sos and annRecent and annFlat and (isLong ? execLongs : execShorts) and (key == -1 or na(tradedKey) or key != tradedKey)
        bool lvlMet  = famN >= minFamilies
        bool roomMet = room == 0
        int  metN    = (lvlMet ? 1 : 0) + 1 + (trendOk ? 1 : 0) + (roomMet ? 1 : 0)
        bool near    = metN == 4 or (metN == 3 and ((not lvlMet and famN > 0) or room == 6))
        bool pass    = missFilter == "All misses" ? true : missFilter == "4-of-4 only" ? metN == 4 : near
        if metN >= 3 and pass
            string lvlTxt = str.tostring(famN) + " of " + str.tostring(minFamilies) + " needed" + (famN > 0 ? " · " + famTxt : "")
            string met = "MET\\n  SOS     5-minute change of character"
            string mss = "MISSING"
            if lvlMet
                met := met + "\\n  Levels  " + lvlTxt
            else
                mss := mss + "\\n  Levels  " + (famN > 0 ? lvlTxt : "nothing swept in the last " + str.tostring(sweptMinutes) + " minutes")
            if trendOk
                met := met + "\\n  Trend   " + (reqCounterTrend ? "against the 15-minute trend" : "not required")
            else
                mss := mss + "\\n  Trend   " + (isLong ? "the 15-minute trend is not down" : "the 15-minute trend is not up")
            if roomMet
                met := met + "\\n  Room    swing " + str.tostring(r, "#.#") + "R away"
            else
                mss := mss + "\\n  Room    " + f_blkText(room, isLong)
            if metN == 4
                mss := mss + "\\n  Entry   " + (rule > 0 ? f_blkText(rule, isLong) : "no entry")
            string tag = (isLong ? "▲ " : "▼ ") + str.tostring(metN) + "/4" + (metN == 4 ? " ✗" : "")
            string hdr = (isLong ? "▲ LONG   " : "▼ SHORT   ") + str.tostring(metN) + " OF 4" + (metN == 4 ? "   NO ENTRY" : "")
            string tip = hdr + "\\n──────────────────\\n" + met + "\\n" + mss + "\\n──────────────────\\n  Would have entered at " + str.tostring(entryPx, format.mintick)
            array.push(refKey, key)
            array.push(refLbl, label.new(bar_index, y, tag, tooltip = tip, color = MISS_ORN, textcolor = LBL_TXT, style = label.style_label_center, size = size.small))
            line ln = na
            if inWin and not na(sweepPx)
                ln := line.new(bar_index, y, sweepBar, sweepPx, color = MISS_ORNL, style = line.style_arrow_right, width = 1)
            array.push(refLn, ln)
    int _mDone = 0

// 4 of 4 means the arming gates passed, so the refusal ladder ran: its own code is the reason.
f_miss(true,  st.bull_sos, lowFamilies,  lowSweepBar,  lowSweepPx,  lowFamTxt,  not reqCounterTrend or htfBear, f_roomCode(tgtLong,  riskLong,  rLong,  true),  rLong,  blkLong,  tradedKeyL, annLo - annAtr * 4)
f_miss(false, st.bear_sos, highFamilies, highSweepBar, highSweepPx, highFamTxt, not reqCounterTrend or htfBull, f_roomCode(tgtShort, riskShort, rShort, false), rShort, blkShort, tradedKeyS, annHi + annAtr * 4)

// Keep the tag lists bounded. Pine has already recycled anything this old off the chart.
if array.size(refKey) > 600
    array.shift(refKey)
    array.shift(refLbl)
    array.shift(refLn)

// Snapshot the order LAST, so a trade that closed on this bar was graded against its own entry.
if tookLong or tookShort
    snapBar  := bar_index
    snapStop := tStop
    snapTgt  := tTgt
    int fam = tookLong ? lowFamilies : highFamilies
    snapBody := "──────────────────\\nTake profit  " + str.tostring(tTgt, format.mintick) + "  (" + str.tostring((tookLong ? rLong : rShort) * tpFrac, "#.##") + "R booked)\\nSwing        " + str.tostring(tookLong ? tgtLong : tgtShort, format.mintick) + "  (" + str.tostring(tookLong ? rLong : rShort, "#.##") + "R available)\\nStop         " + str.tostring(tStop, format.mintick) + "\\nLevels swept " + str.tostring(fam) + " · " + (tookLong ? lowFamTxt : highFamTxt)

// ⚠ Declared at top level, not inside the `if`. Pine refuses a function declaration inside a
// conditional block, and the failure is a compile error rather than a quiet no-op.
f_lvl(float p, color c, string txt, bool on) =>
    if on and not na(p)
        line.new(bar_index - 100, p, bar_index + 10, p, color = color.new(c, 60), style = line.style_dotted)
        label.new(bar_index + 10, p, txt, style = label.style_label_left, color = color(na), textcolor = color.new(c, 30), size = size.tiny)

bool drawLevels = showLevels and barstate.islast
f_lvl(h4H, #FF6B35, "H4 H", drawLevels)
f_lvl(h4L, #FF6B35, "H4 L", drawLevels)
f_lvl(dH, color.black, "PDH", drawLevels)
f_lvl(dL, color.black, "PDL", drawLevels)
f_lvl(wH, color.black, "PWH", drawLevels)
f_lvl(wL, color.black, "PWL", drawLevels)

if showDebug and barstate.islast
    label.new(bar_index, high, "15m dir " + str.tostring(st15.dir) + "\\n15m swing H " + str.tostring(st15.ash, format.mintick) + "\\n15m swing L " + str.tostring(st15.asl, format.mintick), style = label.style_label_down, color = color.new(color.black, 30), textcolor = color.white, size = size.small)
"""

body = HEAD + native + "\n" + derived + MID

# `--check` regenerates in memory and diffs against the committed parent, writing nothing. Added
# 2026-09-30: the parent had been hand-edited (the refused-tag erase) while this builder was not,
# so the next regeneration would have silently deleted a shipped fix.
if "--check" in sys.argv[1:]:
    if OUT.read_text() != body:
        print(f"{OUT.name} is STALE or hand-edited - make the change here, then run this without --check")
        sys.exit(1)
    print(f"{OUT.name} matches its builder")
    sys.exit(0)

OUT.write_text(body)

# The twin is the SAME body with " Export" on the title and the export block on the end, built by
# the shared twin builder that builds every twin here the same way. The block lives in
# export_blocks/extreme_leg_strategy.pine — edit it there, never in the twin. The builder also
# refuses a twin over Pine's 64-plot cap, which this script used to check for itself.
sys.path.insert(0, str(HERE))
from build_export_twins import write_twin  # noqa: E402

OUT_EXPORT = write_twin(OUT.stem)
for f in (OUT, OUT_EXPORT):
    print(f"wrote {f.name} — {len(f.read_text().splitlines())} lines")
