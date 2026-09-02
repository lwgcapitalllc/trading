#!/usr/bin/env python3
"""build_extreme_leg.py — assemble mpc_extreme_leg_strategy.pine.

The file embeds the external structure state machine TWICE — once on the chart's own 5-minute bars
(the change of character that arms the trade) and once on 15-minute bars aggregated in code (the
trend, and the swing that is the target). The second copy is DERIVED by
`derive_htf_structure.py`, never retyped, so the two cannot drift silently.

Run `derive_htf_structure.py` first, then this. Both are idempotent.

It writes TWO files from one body: the strategy you trade, and its EXPORT TWIN, which is the same
file with a block of `plot()` calls appended that write the per-bar decision stream into a CSV.
The twin exists so `compare_extreme_leg.py` can read the Pine's mind bar by bar rather than
guessing from a trade list. ⚠ The bodies are IDENTICAL by construction — the twin is not a copy
that has to be kept in step, it is the same string with a different title and a tail. That is the
whole reason it is generated: the sibling strategies here keep their twins by hand, and a twin
that has drifted from its parent proves parity against a file nobody trades.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
STRAT = HERE.parent
SRC = STRAT / "mpc_h4_sweep_strategy.pine"
DERIVED = HERE / "_derived_structure_15.pine"
OUT = STRAT / "mpc_extreme_leg_strategy.pine"
OUT_EXPORT = STRAT / "mpc_extreme_leg_strategy_export.pine"

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
// [doc 1] MPC EXTREME LEG — the run INTO the shift of structure, not the fade after it  -> docs/mpc_extreme_leg_strategy.md
strategy("MPC Extreme Leg", overlay = true, initial_capital = 10000,
  default_qty_type = strategy.fixed, default_qty_value = 1, pyramiding = 0,
  calc_on_every_tick = false, process_orders_on_close = true,
  max_lines_count = 500, max_labels_count = 500, max_boxes_count = 500)

// [doc 2] RUN THIS ON A 5-MINUTE CHART. The 15-minute half is aggregated in code, so the
// chart timeframe is not a preference — it is the frame the trigger is measured on.
// [doc 3] THE INPUT PANEL — twelve numbered sections, house contract  -> docs/mpc_extreme_leg_strategy.md

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
// [doc 4] ⚠ TWO of the house's four toggles are absent here, deliberately  -> docs/mpc_extreme_leg_strategy.md
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
bool showEntries = input.bool(true,  "Entry markers", group = G8)
bool showBlocked = input.bool(true,  "Refused setups", group = G8, tooltip = "Tags a setup that armed and was then refused, with the reason.")
bool showSweeps  = input.bool(false, "Mark the sweep that armed it", group = G8)

// ── 11 · Drawing: Liquidity ─────────────────────────────────────
bool showLevels = input.bool(false, "Draw the levels", group = G11, tooltip = "Draws the highs and lows this strategy watches. Drawing only — it changes nothing.")

// ── 12 · Debug ──────────────────────────────────────────────────
bool showDebug = input.bool(false, "Debug labels", group = G12)

// [doc 5] MARKET STRUCTURE — shared settings  -> docs/mpc_extreme_leg_strategy.md
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

// [doc 7] THE 15-MINUTE HALF — aggregated in code, never requested  -> docs/mpc_extreme_leg_strategy.md
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
// The parent this was ported from — `indicators/engines/mpc_assistant.pine` — passes the timezone
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

f_track(float lvl, bool isHigh, bool enabled) =>
    var float held = na
    var bool  taken = false
    bool fired = false
    if enabled and not na(lvl)
        if na(held) or lvl != held
            held := lvl
            taken := false
        if not taken
            if isHigh and high > held
                taken := true
                fired := true
            if not isHigh and low < held
                taken := true
                fired := true
    fired

bool swH4H  = f_track(h4H,  true,  useH4Level)
bool swH4L  = f_track(h4L,  false, useH4Level)
bool swDH   = f_track(dH,   true,  useDailyLevel)
bool swDL   = f_track(dL,   false, useDailyLevel)
bool swWH   = f_track(wH,   true,  useWeeklyLevel)
bool swWL   = f_track(wL,   false, useWeeklyLevel)
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
    label.new(bar_index, lowFamNow > 0 ? low : high, "swept", style = lowFamNow > 0 ? label.style_label_up : label.style_label_down, color = color.new(color.gray, 70), textcolor = color.gray, size = size.tiny)

// [doc 11] THE SETUP  -> docs/mpc_extreme_leg_strategy.md
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
// The sibling `mpc_h4_sweep_strategy.pine` has carried the same pair since it was written.
bool tookLong  = false
bool tookShort = false

if goLong and strategy.position_size == 0
    strategy.entry("L", strategy.long, qty = f_qty(riskLong))
    tStop := stopLong
    tTgt  := tpLong
    beArmed := false
    tookLong := true
if goShort and strategy.position_size == 0
    strategy.entry("S", strategy.short, qty = f_qty(riskShort))
    tStop := stopShort
    tTgt  := tpShort
    beArmed := false
    tookShort := true

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

// [doc 13] ANNOTATIONS
if showEntries and (goLong or goShort)
    label.new(bar_index, goLong ? low : high, goLong ? "▲" : "▼", style = goLong ? label.style_label_up : label.style_label_down, color = color.new(goLong ? bullColor : bearColor, 20), textcolor = color.white, size = size.small, tooltip = "take profit " + str.tostring(goLong ? tpLong : tpShort, format.mintick) + " (" + str.tostring((goLong ? rLong : rShort) * tpFrac, "#.##") + "R booked)  ·  swing " + str.tostring(goLong ? tgtLong : tgtShort, format.mintick) + " (" + str.tostring(goLong ? rLong : rShort, "#.##") + "R available)  ·  " + str.tostring(goLong ? lowFamilies : highFamilies) + " level(s) swept")

if showBlocked and (not na(blockLong) or not na(blockShort))
    label.new(bar_index, not na(blockLong) ? low : high, "REFUSED", style = not na(blockLong) ? label.style_label_up : label.style_label_down, color = color.new(color.orange, 60), textcolor = color.orange, size = size.tiny, tooltip = not na(blockLong) ? blockLong : blockShort)

// ⚠ Declared at top level, not inside the `if`. Pine refuses a function declaration inside a
// conditional block, and the failure is a compile error rather than a quiet no-op.
f_lvl(float p, color c, string txt, bool on) =>
    if on and not na(p)
        line.new(bar_index - 100, p, bar_index + 10, p, color = color.new(c, 60), style = line.style_dotted)
        label.new(bar_index + 10, p, txt, style = label.style_label_left, color = color(na), textcolor = color.new(c, 30), size = size.tiny)

bool drawLevels = showLevels and barstate.islast
f_lvl(h4H, color.gray, "H4 H", drawLevels)
f_lvl(h4L, color.gray, "H4 L", drawLevels)
f_lvl(dH, color.orange, "PDH", drawLevels)
f_lvl(dL, color.orange, "PDL", drawLevels)
f_lvl(wH, color.purple, "PWH", drawLevels)
f_lvl(wL, color.purple, "PWL", drawLevels)

if showDebug and barstate.islast
    label.new(bar_index, high, "15m dir " + str.tostring(st15.dir) + "\\n15m swing H " + str.tostring(st15.ash, format.mintick) + "\\n15m swing L " + str.tostring(st15.asl, format.mintick), style = label.style_label_down, color = color.new(color.black, 30), textcolor = color.white, size = size.small)
"""


EXPORT = """
// [doc 14] ═══════════════════════════════════════════════════════════════════════
// THE EXPORT BLOCK — this file's only difference from the strategy, and why it exists
//
// TradingView will not tell you WHY it did something; it will only show you what it did. A trade
// list says two runs disagree and nothing about where. These plots write the decision itself —
// every level, every sweep, every candidate and every refusal — into the CSV, so a disagreement
// lands on a named column at a named bar instead of on "trade 14 is missing".
//
// HOW TO TAKE THE EXPORT (the one step no machine here can do):
//   1. Paste this file into a new Pine editor tab on a XAUUSD 5-minute chart.
//   2. Leave every input at its default unless you are testing a specific setting.
//   3. Scroll the chart LEFT until it stops loading more history — the export only holds
//      what the chart has loaded.
//   4. ⋮ (top right of the Strategy Tester) -> Export chart data -> Bar data and indicator values.
//   5. Save the CSV under `engines/`. It is git-ignored there on purpose.
//
// ⚠ EVERY COLUMN IS `na` WHERE IT HAS NO MEANING, and that is deliberate. A column that reports 0
// for "no candidate" cannot be told apart from a candidate whose value really is 0 — the same
// distinction this repo lost once already when a dead terminal read as a quiet market.

color _INV = color.new(color.gray, 100)   // transparent — in the CSV, invisible on the chart

// [doc 15] ── The bar's classification, bit-packed ──────────────────────────────
// One column rather than ten, because plots are capped at 64 and each of these is one bit of
// information. Read it with a bit test, never with an equality.
//   1 a 15-minute period closed here     ·   2 5m bullish change of character
//   4 5m bearish change of character     ·   8 the low side is armed
//  16 the high side is armed             ·  32 a raw long setup existed
//  64 a raw short setup existed          · 128 entered long
// 256 entered short                      · 512 went flat here
float _xSeq = (periodClosed ? 1 : 0) + (st.bull_sos ? 2 : 0) + (st.bear_sos ? 4 : 0) +
  (lowArmed ? 8 : 0) + (highArmed ? 16 : 0) + (rawLong ? 32 : 0) + (rawShort ? 64 : 0) +
  (tookLong ? 128 : 0) + (tookShort ? 256 : 0) +
  (strategy.position_size == 0 and strategy.position_size[1] != 0 ? 512 : 0)

// [doc 16] ── Which level family was taken ON THIS BAR ────────────────────────
// ⚠ This is the FIRING edge, not the armed state. A level fires once and is then dead until it is
// replaced, so a column reporting "a level is currently under us" would be a different fact and
// would agree with Python for the wrong reason.
//  1 h4 low · 2 h4 high · 4 session low · 8 session high
// 16 prev-day low · 32 prev-day high · 64 prev-week low · 128 prev-week high
float _xSwept = (swH4L ? 1 : 0) + (swH4H ? 2 : 0) + (sessLowSwept ? 4 : 0) + (sessHighSwept ? 8 : 0) +
  (swDL ? 16 : 0) + (swDH ? 32 : 0) + (swWL ? 64 : 0) + (swWH ? 128 : 0)

float _xLowAge  = na(lowSweepBar)  ? na : bar_index - lowSweepBar
float _xHighAge = na(highSweepBar) ? na : bar_index - highSweepBar

// [doc 17] ── The candidate, on every bar one existed — TAKEN OR REFUSED ──────
// A refused setup is the more valuable half of this export. A port that agrees on every trade and
// disagrees about what it REFUSED has a filter bug that has not surfaced yet, and it will surface
// on a bar neither side has seen.
float _xCandDir   = rawLong ? 1.0 : rawShort ? -1.0 : na
float _xCandEntry = rawLong or rawShort ? entryPx : na
float _xCandStop  = rawLong ? stopLong : rawShort ? stopShort : na
float _xCandTgt   = rawLong ? tgtLong  : rawShort ? tgtShort  : na
float _xCandTp    = rawLong ? tpLong   : rawShort ? tpShort   : na
float _xCandR     = rawLong ? rLong    : rawShort ? rShort    : na
float _xBlk       = rawLong ? blkLong  : rawShort ? blkShort  : na

// [doc 18] ── The open trade ──────────────────────────────────────────────────
// ⚠ The entry price, the opening stop and the direction are latched HERE rather than read back off
// `strategy.position_avg_price`, because the bar that places the order still reports flat — see
// [doc 12a]. Reading the platform on that bar returns `na` and every R below it would be `na` too.
var float _xEntry    = na
var float _xOpenStop = na
var float _xOpenTp   = na
var float _xDir      = na
if tookLong
    _xEntry := entryPx
    _xOpenStop := stopLong
    _xOpenTp := tpLong
    _xDir := 1
if tookShort
    _xEntry := entryPx
    _xOpenStop := stopShort
    _xOpenTp := tpShort
    _xDir := -1

float _x1r = na(_xEntry) or na(_xOpenStop) ? na : math.abs(_xEntry - _xOpenStop)

var float _xMfe = na
var float _xMae = na
if tookLong or tookShort
    _xMfe := 0.0
    _xMae := 0.0
if strategy.position_size != 0 and not na(_x1r) and _x1r > 0
    _xMfe := math.max(nz(_xMfe, 0.0), (_xDir > 0 ? high - _xEntry : _xEntry - low) / _x1r)
    _xMae := math.min(nz(_xMae, 0.0), (_xDir > 0 ? low - _xEntry : _xEntry - high) / _x1r)

bool  _held  = strategy.position_size != 0 or tookLong or tookShort
float _xFill = tookLong or tookShort ? _xEntry : na
float _xRisk = tookLong or tookShort ? _x1r : na
float _xStop = tookLong or tookShort ? _xOpenStop : na
float _xTp   = tookLong or tookShort ? _xOpenTp : na
float _xLive = _held ? tStop : na
float _xMfeC = _held ? _xMfe : na
float _xMaeC = _held ? _xMae : na

// The trade's own R, on the bar it closed. Taken from the platform's own book rather than
// recomputed from the exit price: a rounded fill, a gap through the stop and a bar that touched
// both ends all land here, and this is what the account actually received.
float _xClosedR = na
if strategy.closedtrades > nz(strategy.closedtrades[1], 0) and not na(_x1r) and _x1r > 0
    int _ix = strategy.closedtrades - 1
    float _sz = strategy.closedtrades.size(_ix)
    if _sz != 0
        _xClosedR := (strategy.closedtrades.profit(_ix) / math.abs(_sz)) / _x1r

// [doc 19] ── The aggregated 15-minute bar, on the bar it completes ───────────
// ⚠ The single most valuable four columns here. The 15-minute half of this strategy is built in
// code out of 5-minute bars, so a port can disagree about the TREND for a reason that has nothing
// to do with trading logic — an off-by-one in where a period starts. Without these the symptom is
// a missing trade eleven hours later.
float _xAggO = periodClosed ? doneO : na
float _xAggH = periodClosed ? doneH : na
float _xAggL = periodClosed ? doneL : na
float _xAggC = periodClosed ? doneC : na

// [doc 20] ═══════════════════════════════════════════════════════════════════
plot(_xSeq,          "px_seq",          _INV, editable = false)
plot(_xSwept,        "px_swept",        _INV, editable = false)
plot(_xLowAge,       "px_low_age",      _INV, editable = false)   // bars since the low side was taken
plot(_xHighAge,      "px_high_age",     _INV, editable = false)
plot(lowFamilies,    "px_low_fam",      _INV, editable = false)   // families counted, low side
plot(highFamilies,   "px_high_fam",     _INV, editable = false)
plot(st15.dir,       "px_dir15",        _INV, editable = false)   // the 15m trend: 1 up, -1 down
plot(st15.ash,       "px_swing_hi",     _INV, editable = false)   // the 15m swing being aimed at
plot(st15.asl,       "px_swing_lo",     _INV, editable = false)
plot(extremeLow,     "px_extreme_lo",   _INV, editable = false)   // the stop anchor
plot(extremeHigh,    "px_extreme_hi",   _INV, editable = false)
plot(atrNow,         "px_atr",          _INV, editable = false)
plot(_xCandDir,      "px_cand_dir",     _INV, editable = false)
plot(_xCandEntry,    "px_cand_entry",   _INV, editable = false)
plot(_xCandStop,     "px_cand_stop",    _INV, editable = false)
plot(_xCandTgt,      "px_cand_tgt",     _INV, editable = false)
plot(_xCandTp,       "px_cand_tp",      _INV, editable = false)
plot(_xCandR,        "px_cand_r",       _INV, editable = false)   // R to the SWING, not to the exit
plot(_xBlk,          "px_blk",          _INV, editable = false)   // 0 taken · 1-6 refused, see [doc 12d]
plot(_xFill,         "px_fill",         _INV, editable = false)
plot(_xRisk,         "px_1r",           _INV, editable = false)   // 1R in PRICE, so R and dollars reconcile
plot(_xStop,         "px_stop",         _INV, editable = false)   // the FROZEN opening stop
plot(_xTp,           "px_tp",           _INV, editable = false)
plot(_xLive,         "px_cur_stop",     _INV, editable = false)   // the LIVE stop — watch breakeven move it
plot(beArmed ? 1 : 0, "px_be_armed",    _INV, editable = false)
plot(_xMfeC,         "px_mfe_r",        _INV, editable = false)
plot(_xMaeC,         "px_mae_r",        _INV, editable = false)
plot(_xClosedR,      "px_closed_r",     _INV, editable = false)
plot(strategy.equity, "px_equity",      _INV, editable = false)
plot(strategy.position_size, "px_pos",  _INV, editable = false)
plot(_xAggO,         "px_agg_o",        _INV, editable = false)
plot(_xAggH,         "px_agg_h",        _INV, editable = false)
plot(_xAggL,         "px_agg_l",        _INV, editable = false)
plot(_xAggC,         "px_agg_c",        _INV, editable = false)
plot(ph15,           "px_ph15",         _INV, editable = false)   // the 15m pivots, as detected
plot(pl15,           "px_pl15",         _INV, editable = false)
plot(h4H,            "px_h4h",          _INV, editable = false)
plot(h4L,            "px_h4l",          _INV, editable = false)
plot(dH,             "px_dh",           _INV, editable = false)
plot(dL,             "px_dl",           _INV, editable = false)
plot(wH,             "px_wh",           _INV, editable = false)
plot(wL,             "px_wl",           _INV, editable = false)
plot(asiaH,          "px_asia_h",       _INV, editable = false)
plot(asiaL,          "px_asia_l",       _INV, editable = false)
plot(ldnH,           "px_ldn_h",        _INV, editable = false)
plot(ldnL,           "px_ldn_l",        _INV, editable = false)
plot(nyH,            "px_ny_h",         _INV, editable = false)
plot(nyL,            "px_ny_l",         _INV, editable = false)
plot(barsBack,       "px_bars_back",    _INV, editable = false)   // the minutes->bars conversions,
plot(lookbackBars,   "px_lookback",     _INV, editable = false)   // exported so a rounding gap shows

// [doc 21] ── The settings this run was taken with ─────────────────────────────
// ⚠ The harness configures the PYTHON side from these columns rather than from its own defaults.
// A port replayed at its defaults against an export taken at somebody else's is comparing two
// different strategies and will spend a day looking for the bug in the wrong half.
plot((execLongs ? 1 : 0) + (execShorts ? 2 : 0) + (reqCounterTrend ? 4 : 0) + (useH4Level ? 8 : 0) +
  (useSessionLevel ? 16 : 0) + (useDailyLevel ? 32 : 0) + (useWeeklyLevel ? 64 : 0) +
  (skipFriday ? 128 : 0) + (useBreakeven ? 256 : 0), "cfg_flags", _INV, editable = false)
plot(sweptMinutes,   "cfg_swept_min",   _INV, editable = false)
plot(minFamilies,    "cfg_min_fam",     _INV, editable = false)
plot(extremeMinutes, "cfg_extreme_min", _INV, editable = false)
plot(stopBufferAtr,  "cfg_stop_buf",    _INV, editable = false)
plot(tpFrac,         "cfg_tp_frac",     _INV, editable = false)
plot(beArmFrac,      "cfg_be_arm",      _INV, editable = false)
plot(minR,           "cfg_min_r",       _INV, editable = false)
plot(minStopUsd,     "cfg_min_stop",    _INV, editable = false)
plot(riskPct,        "cfg_risk_pct",    _INV, editable = false)
plot(fixedQty,       "cfg_fixed_qty",   _INV, editable = false)
plot(sizeMode == "Risk % of equity" ? 0 : 1, "cfg_size_mode", _INV, editable = false)
"""

body = HEAD + native + "\n" + derived + MID
OUT.write_text(body)

# The twin is the SAME body with a different title and the export block on the end. Nothing is
# retyped, so "does the twin still match the strategy?" is not a question anybody has to ask.
twin = body.replace('strategy("MPC Extreme Leg"', 'strategy("MPC Extreme Leg Export"', 1)
assert twin != body, "the strategy title moved — the twin would ship under the parent's name"
OUT_EXPORT.write_text(twin + EXPORT)

for f in (OUT, OUT_EXPORT):
    print(f"wrote {f.name} — {len(f.read_text().splitlines())} lines")
n_plots = EXPORT.count("\nplot(")
assert n_plots <= 64, f"Pine caps a script at 64 plots and the twin has {n_plots}"
print(f"  {n_plots} plotted columns (Pine's cap is 64)")
