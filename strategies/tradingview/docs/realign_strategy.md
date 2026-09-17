# realign_strategy.pine — commentary

The prose that used to live inline in the Pine. Each entry is anchored from the
source by a `// [doc N]` line. Grep this file for `## [N]` to find one.

**Covers:** `realign_strategy.pine`

---

## [1] Realign — internal-structure realignment after an external false bre

```
// =====================================================================================
// Realign — internal-structure realignment after an external false break
//
// THE SETUP (long; the short is the exact mirror and is half the strategy, not an extra):
//   1. 15m external structure is BULLISH — a bullish SOS or BOS.
//   2. 15m prints a bearish SOS, and it is the FIRST bearish break since (1). That is the
//      FALSE BREAK — a deviation / structural liquidity grab, not a new trend. The setup
//      arms, and the 15m active swing HIGH that stood is latched: it is the target.
//   3. On the CHART frame (5m) structure goes bearish inside the deviation.
//   4. The chart frame prints a bullish SOS — the realignment. ENTER AT MARKET.
//      The 15m bullish SOS that confirms all this comes LATER; the trade front-runs it.
//
// Spec + every measurement behind the defaults: docs/REALIGN_SPEC.md
// Python port (stage 5, already built and replayed): strategies/python/realign/
//
// MEASURED by real replay of the Python port, 467,352 M5 bars 2020-01-02 -> 2026-08-06,
// $10,000, warmup 1000, full exit ladder, one position slot. The 5m frame is RESAMPLED
// FROM M1 — backtest/cache/XAUUSD__M5.csv holds 26,887 bars where a complete history is
// ~467,000, and replaying a streaming structure engine across holes that size builds
// structure over candles that never traded and returns a clean-looking number:
//     free                     162 trades (77L/85S)  +45.14R  win 44.4%  maxDD 12.15R
//     spread + swap charged    162 trades            +35.81R  win 33.3%  maxDD 15.52R
//   (charged = PROFILES["puprime_standard"], spread $0.32 + swap, no commission)
//
// ⚠ AN EARLIER REVISION OF THIS HEADER CLAIMED +37.67R / maxDD 14.60R CHARGED AND IT DOES
//   NOT REPRODUCE — today's run gives +35.81R / 15.52R on the same window and profile.
//   The FREE figure reproduces to the cent, so whatever differs is on the charged path
//   alone. Aaron's 32b633f was checked and is NOT the cause: it touched only tools and
//   docs, no execution code. The remaining candidates are a different warmup or a
//   different bar set in the original run, and NEITHER IS MEASURED — the original run's
//   command was not recorded, which is exactly why it cannot be settled now. The figures
//   above are the ones a command reproduces; quote those.
//
// ⚠ BOTH SIDES TRIGGER ON THE FRAME'S OWN SWING STRUCTURE. An earlier trigger scan said
//   the short side wanted the engine's INTERNAL (iBOS/iSOS) stream; a real replay through
//   the exit ladder gave -13.26R against +20.22R on swing. The scan scored setups
//   independently at a fixed 4R target with no ladder and no position slot, and that short
//   edge existed only in the tail. This file therefore needs NO internal state machine.
//
// ✅ COMPILED AND RUN IN THE STRATEGY TESTER, 2026-08-12 — XAUUSD 5m, 2020-01-01 ->
//   2026-08-12, $10,000, risk 1%:
//     143 trades   +41.35% (~35R)   maxDD 17.79% (~19.5R)   PF 1.617   win 30.77%
//   Against the Python port's charged +37.67R over 162 trades, the TOTAL R agrees within
//   noise across two independent implementations. Two differences are open, not resolved:
//   ⚠ DRAWDOWN IS WORSE HERE (~19.5R vs 14.60R) AND PINE IS PROBABLY RIGHT. TradingView
//     fills a gapped stop at the next bar's OPEN; the Python replay is a bar model that
//     fills at the stop price, which undercounts what a weekend gap costs. Same total R,
//     deeper drawdown, is exactly the signature of that.
//   ✅ THE WIN-RATE GAP IS LARGELY CLOSED, AND THE CAUSE WAS THE COMPARISON RATHER THAN
//     EITHER IMPLEMENTATION. This note used to read "30.77% HERE vs 44% THERE" and blamed
//     scratch classification. 44% is the Python's FREE book; its CHARGED book — the one
//     the R figure above is quoted from — wins 33.3%, against the tester's 30.77%. So the
//     comparison was reading its R off one book and its win rate off the other. Costs move
//     this strategy's win rate 11 points (44.4% -> 33.3%) because it enters at MARKET and
//     pays the spread both ways, which is the whole reason that mattered here.
//     ⚠ ~2.5 points remain unexplained and scratch classification is still the candidate
//     (the Python counts 11 of 162 separately at |r| <= 0.02; the tester asks only whether
//     P&L > 0). Small, and NOT measured — the parity gate is what settles it.
//
// ⚠ STILL NOT PARITY-VALIDATED. Stage 2 of docs/STRATEGY_WORKFLOW.md is now done; the
//   export twin (stage 3), a real CSV (stage 4, human-only) and compare_realign.py
//   (stage 6) do not exist, so no bar-by-bar diff has been run and the two differences
//   above are diagnosed rather than measured.
// =====================================================================================
// ⚠ `margin_long/short = 0.2` is 500x — the same pin every other strategy file here
//   carries, and Aaron's real demo account. It is NOT decoration.
//   🔴 Pine's DEFAULT (margin unset) is 100%, i.e. full cash, and size here is
//   risk/stop-distance: a $10,000 account risking 10% against an $8 stop asks for ~125 oz,
//   about $500,000 notional. At 100% margin TradingView REFUSES every one of those orders
//   and the Strategy Tester shows NO TRADES AND NO ERROR — indistinguishable from a
//   strategy that never found a setup. That is what an empty tester means here.
//   🔴 The first fix for that was `margin = 0`, which is UNBOUNDED leverage, and it
//   produced -98.10% / PF 0.193 over 2009-2026: the stop still says 10%, but a weekend gap
//   THROUGH the stop fills at the next open and loses a multiple of it on a position that
//   large. 500x bounds the notional; `riskPct` is the real control.
```

## [2] THE TWO STRUCTURE READS

```
// =====================================================================================
// THE TWO STRUCTURE READS
// =====================================================================================
// One state machine per frame. Both are the SWING (external) read — this strategy needs
// no internal state machine, see the header note.
```

## [3] The same read, one HTF bar in the PAST. This is the non-repainting idiom

```
// The same read, one HTF bar in the PAST. This is the non-repainting idiom, and it is
// what makes the external break honest: `[1]` + lookahead_on returns the values of the
// last CLOSED external bar, so a break can never be seen while its own bar is still
// forming. It mirrors the Python port exactly (`htf.py` publishes a 15m bar only once
// its final chart bar has closed) — get this wrong and the strategy front-runs its own
// signal by up to two chart bars, which flatters every result and raises nothing.
```

## [4] ── the EXTERNAL frame, via security ────────────────────────────────────

```
// ── the EXTERNAL frame, via security ─────────────────────────────────────────────
// ⚠ `[1]` INSIDE the function + lookahead_on is the standard NON-REPAINTING pair, and it
//   is deliberate. lookahead_on alone would be genuine future data; the `[1]` is what
//   makes it safe, because the value returned is the last CLOSED external bar's. Removing
//   either half breaks it in a way that only makes the backtest look better.
```

## [5] A security call REPEATS its value across every chart bar inside one HTF 

```
// A security call REPEATS its value across every chart bar inside one HTF bar, so acting
// on the raw flags would re-fire the same break two or three times. Gate on the HTF bar
// actually turning over.
```

## [6] THE SETUP TRACKER

```
// =====================================================================================
// THE SETUP TRACKER
// =====================================================================================
```

## [7] ── the chart-frame realignment ─────────────────────────────────────────

```
// ── the chart-frame realignment ──────────────────────────────────────────────────
// Pattern: a counter-direction break, then a with-trend SOS — the LOOSE rule.
// ⚠ THIS COMMENT USED TO SAY THE TIGHTER THREE-STEP SEQUENCE WAS "MEASURED AS WORSE ON
//   BOTH SIDES". That was the TRIGGER SCAN talking, and a real replay overturns it.
//   Over 467,352 M5 bars, FREE, the strict sequence is the BEST of the three on average R
//   (+0.294 vs +0.279), profit factor (1.977 vs 1.658) and drawdown (4.15R vs 12.15R) at
//   once. It only loses once COSTS ARE CHARGED, where it gives up 40% of its average R
//   against the loose rule's 21% and the ranking flips.
//   The loose rule ships because charged it earns 5x the total R (+35.81R vs +7.33R) and
//   more R per unit of drawdown (2.31 vs 1.66) — not because the tight one is a bad rule.
//   ⚠ This file has no input for it: the strict sequence would need its own state, and
//   adding a lever the Python has and the Pine does not is how the two stop being
//   comparable. Measure it in Python first. Tables: strategies/python/realign/CLAUDE.md
```

## [8] ENTRY — at MARKET, on the bar the realignment confirms

```
// =====================================================================================
// ENTRY — at MARKET, on the bar the realignment confirms
// =====================================================================================
// ⚠ This is the repo's first market entry. SOS Fade and B-LEG rest limits, which largely avoid
//   the spread; this pays it BOTH WAYS. Do not carry SOS Fade's near-zero spread cost across.
```

## [9] THE EXIT LADDER

```
// =====================================================================================
// THE EXIT LADDER
// =====================================================================================
// Three phases, always on: (0) the structural stop -> (1) after TP1, breakeven -> (2)
// after TP2, a floor, then the trail. The floor and the trail COMPOSE: past TP2 the stop
// is the floor, or the trail wherever the trail is tighter.
```

🔴 **"The trail may only ever tighten it, never loosen it" was this section's wording until
2026-09-16, and it described neither this file's code nor the port's.** Past TP2 the stop is now
rebuilt each bar — see [21].

## [10] Structure anchor: a frame's last CONFIRMED swing, buffered.

⚠ **The heading said "the chart frame's" and the code has always used the EXTERNAL frame**, which is
Aaron's call recorded below. The Python port was written against the wrong heading and trailed the
chart frame. The frame is an input now (`trailFrame`), and the first parity export (2026-09-16)
found the port's external anchor had never been populated at all — see
`strategies/python/realign/CLAUDE.md` → *The first parity export*.

```
            // Structure anchor: the chart frame's last CONFIRMED swing, buffered.
            // ⚠ The EXTERNAL frame's swing (hConfLo/hConfHi), not the chart frame's.
            //   Aaron's call: you enter off the 5m and RIDE the 15m — the 5m swing sits
            //   close enough that the first pullback scratches the runner, and the runner
            //   is where this family of strategies makes its money.
```

## [11] ── the time stop ───────────────────────────────────────────────────────

```
    // ── the time stop ────────────────────────────────────────────────────────────
    // "Before TP1 only" fires at stage 0 alone: touching TP1 staged the stop to
    // breakeven, so the trade is no longer genuinely at risk and the clock is not asked.
    // ⚠ Split across three names rather than wrapped. Pine ends a statement at a line
    //   that is already a complete expression, so a continuation beginning with `and`
    //   is CE10013 — it cannot know the line was meant to carry on.
```

## [12] DIAGNOSTICS

```
// =====================================================================================
// DIAGNOSTICS
// =====================================================================================
// A running count of every stage. The first counter reading ZERO is where the chain
// breaks, which turns "no trades appear" — a symptom with a dozen possible causes — into
// one named stage. Data Window only, so it costs nothing on the chart.
```

## [13] MARKS

```
// =====================================================================================
// MARKS
// =====================================================================================
```

⚠ **Sections [14]–[17] were anchored from the Pine on 2026-09-16 and not written until the same
evening** — four pointers to nothing, which is the one thing an anchor must never be. Written below.

## [14] The callout opens GREY — the result is not known yet

The entry callout is drawn at the fill in neutral grey and recoloured only when the trade closes.
Colouring it at entry would paint a guess. It carries "▲ LONG" / "▼ SHORT" until then.

## [15] Closed this bar: grade it in R, recolour the callout, paint the bands

The trade's R is its net P&L over the dollar risk frozen at the fill (entry to stop, times size).
A result inside ±`beBandR` is **BREAKEVEN** (orange line), otherwise a red or green result box.
The best and worst prices are banded underneath first, so the result sits on top of them. The
colours are copied from `sos_fade_strategy.pine`, never re-picked.

⚠ **This fork banks nothing at its rungs** (both default 0%), so every trade ends on the trail, the
time stop or the flat, and the result is one band rather than a stack of partials.

## [16] Entry triangles

`plotshape` only runs at global scope, so the "position just opened" test is written out inline.
⚠ **Not redundant with the box**: a scratch paints a band a few pixels tall and reads as no trade.
⚠ **The export twin does not carry them** — `tools/build_export_twins.py` strips every plot-family
call from the twin to stay under Pine's 64-plot cap. The file you trade still draws them.

## [17] REFUSED SETUPS — the only record of a trade the strategy chose not to take

A trigger that fired and was not entered leaves no trace in the trade list or the equity curve, so
it is tagged on the chart with its reason. **The side and the reason are recorded where the refusal
happens, never re-derived** — `d_strategy.pine` paid for that: its tag read direction off the same
bar's SOS and drew every candidate as a SHORT once a second entry mode existed.

Codes: 1 stop on the wrong side · 2 minimum stop · 3 target behind entry · 4 no retest level ·
5 retest expired · 6 invalidated before the fill. ⚠ Written inline, not through a helper — a Pine
function cannot assign to a global.

## [18] The 15m close is read on the FIRST chart bar of the next 15m bar

🔴 **Until 2026-09-16 this read the close on the LAST chart bar of the next 15m bar — ten minutes
late — and the first parity export measured it.** The old line compared a `request.security` of
`time` with `lookahead_off` against its previous value. Off lookahead, that value only changes on
the final chart bar of each HTF bar, so the stamp moved on minute 10 of every quarter hour (all
7,104 closes in the export). But the structure read in [4] shows the closed bar from minute 0.

So every false break was acted on two 5m bars after it was known. That disagreed with the Python
port on 156 trend bars, 439 armed bars and one whole trade. Making the port imitate the delay
removed every one of them, which is the proof. `timeframe.change(htfTf)` is true on the first
chart bar of a new HTF bar — the same bar the port publishes on, and the earliest bar that is
still free of lookahead.

## [19] A setup fires ONCE

🔴 **The Pine disarmed a setup only when it placed an order.** A trigger that was refused (target
already behind the entry, stop too tight) or that fired while a trade was open left the setup
armed, with its old stop anchor, waiting for a LATER realignment to enter on. The port consumes a
setup on its trigger whatever happens next, and the port's rule is the documented one ("a setup
fires once"). The first export showed it on 2026-08-07 08:30: both sides refused the trigger, and
the Pine then stayed armed for another five hours. Now the trigger disarms, taken or not.

## [20] The stop goes in WITH the market order

🔴 **The Pine placed its stop only once a position existed.** A market order fills at the next bar's
open, and the script runs at that bar's CLOSE — so the fill bar had no stop at all, and a trade
that hit its stop there closed a bar late. A live bot sends the stop with the order, and the port's
stop is live from the fill bar. The exit is now placed on the entry bar, tied to the entry's id,
and TradingView holds it until the entry fills.

⚠ **Not changed for the retest entry**, which is shipped off and has never been exercised by an
export. Its fill-bar handling is a separate question.

⚠ **The fill PRICE still differs and is left alone**: this file's order fills at the next open, the
port fills at the trigger bar's close. On a continuous 5m gold feed those are nearly always the same
price; the gate excuses the one-bar position offset this causes and nothing else.

## [21] Past TP2 the stop is REBUILT each bar — the floor, or the trail when tighter

🔴 **This block had its own versions of three rules, and each differed from the port and from
`sos_fade_strategy.pine`**, whose parity gate is green and whose ladder the port inherits:

| rule | this file, before | now — the reference |
|---|---|---|
| ratchet step | this bar's close × pct, measured from this bar's high | the **best price since the fill** × pct, measured from that best price |
| fixed-step trail | this bar's high minus one step | one step per step of best price past TP2, from TP2 |
| "one trail step behind" floor | TP1 minus one step | the best price minus one step, never below breakeven |
| combining | ratcheted — `max(stop, candidate)` for ever | rebuilt — `max(floor, candidate)` each bar |

The first export showed the ratchet as 304 bars of stops a few cents apart.

⚠ **"Rebuilt" means the stop can step back** — by less than one ratchet step, when the structure
anchor rises and the step count drops with it. It is what the port and the live SOS Fade bot both
do today. A never-loosen rule is arguably safer, but it lives in the ladder those bots SHARE, so it
is its own change with its own measurement — never slipped in here to make one gate agree.


## [22] The N-day momentum filter — completed New York trading days only

**Added 2026-09-16, input "Skip trades with the N-day move", 0 = off (the default).** Refuses a
trade that points the same way as price's move over the last N trading days. Measured, reasoning
and the decision to build it: `strategies/python/realign/realign_optimization.md` → Run 12.

- **The day** is the New York date of `time + 7h`, so it rolls at 17:00 New York in both seasons
  and Sunday's reopen belongs to Monday. The Python twin is `strategies/python/daily_momentum.py`.
- **Only completed days are read.** The day still forming keeps its close in `dayClose` and is
  pushed only when the key changes, so today's close never reaches the answer.
- **The move** is the last completed close against the one N days before it. Up +1, down −1,
  unchanged 0 (kept).
- **Fewer than N + 1 completed days refuses** — `momDir` is `na`, not 0, and refusal code 7 is
  written. A chart's first N trading days therefore take no trades with the filter on.
- **`dayKey` starts at 0, never `na`** — Pine's `int` has no `na`, and a comparison against one is
  the trap the export block warns about.
- ⚠ **The input is the LAST `int` declared.** Adding it anywhere earlier would reset every later
  int input on a chart already running this script.
