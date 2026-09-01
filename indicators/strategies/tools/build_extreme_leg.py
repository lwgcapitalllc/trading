#!/usr/bin/env python3
"""build_extreme_leg.py — assemble mpc_extreme_leg_strategy.pine.

The file embeds the external structure state machine TWICE — once on the chart's own 5-minute bars
(the change of character that arms the trade) and once on 15-minute bars aggregated in code (the
trend, and the swing that is the target). The second copy is DERIVED by
`derive_htf_structure.py`, never retyped, so the two cannot drift silently.

Run `derive_htf_structure.py` first, then this. Both are idempotent.
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
STRAT = HERE.parent
SRC = STRAT / "mpc_h4_sweep_strategy.pine"
DERIVED = HERE / "_derived_structure_15.pine"
OUT = STRAT / "mpc_extreme_leg_strategy.pine"

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
G5 = "5 · Entry"
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

// ── 5 · Entry ───────────────────────────────────────────────────
bool entryOnClose = input.bool(true, "Enter on the change-of-character close", group = G5, tooltip = "On = enter as soon as the 5-minute bar that shifts structure closes. Off waits for the next 15-minute close instead, which is later and worth less.")

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
f_sess(string spec) =>
    bool inSess = not na(time(timeframe.period, spec))
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

[asiaH, asiaL] = f_sess("0000-0900")
[ldnH,  ldnL]  = f_sess("0800-1700")
[nyH,   nyL]   = f_sess("1300-2200")

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

string blockLong  = na
string blockShort = na
if rawLong
    blockLong := skipFriday and isFriday ? "Friday - refused by the calendar" : na(tgtLong) ? "no 15m swing to aim at" : tgtLong <= entryPx ? "the swing is already below us" : riskLong <= 0 ? "the extreme is above the entry" : minStopUsd > 0 and riskLong < minStopUsd ? "stop tighter than the floor" : rLong < minR ? "the swing is nearer than " + str.tostring(minR, "#.#") + "R" : na
if rawShort
    blockShort := skipFriday and isFriday ? "Friday - refused by the calendar" : na(tgtShort) ? "no 15m swing to aim at" : tgtShort >= entryPx ? "the swing is already above us" : riskShort <= 0 ? "the extreme is below the entry" : minStopUsd > 0 and riskShort < minStopUsd ? "stop tighter than the floor" : rShort < minR ? "the swing is nearer than " + str.tostring(minR, "#.#") + "R" : na

bool goLong  = rawLong  and na(blockLong)
bool goShort = rawShort and na(blockShort)

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

OUT.write_text(HEAD + native + "\n" + derived + MID)
print(f"wrote {OUT.name} — {len(OUT.read_text().splitlines())} lines")
