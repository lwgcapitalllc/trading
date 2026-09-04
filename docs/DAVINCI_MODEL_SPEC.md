# Da Vinci Model — spec in progress

**Sources:** Marco (@marcotrades) on Chart Fanatics.
- **Video 1** — "STEAL This EASY Liquidity TRAP Trading Strategy", 2025-08-03, 109 min. The
  foundation. Defines how liquidity is identified. **Never says "Da Vinci"** — the name is new in
  video 2, and this episode is the one that carries the primitive rules.
- **Video 2** — "The ONE Liquidity Trading Pattern That Actually Works", 2026-07-12, 71 min.
  Names the model and gives the entry sequence.

Plus marked-up chart screenshots Aaron is collecting.

**Status:** NOT BUILT. This file exists to turn a video into rules precise enough to code.
Nothing here is measured yet. There is no Pine source — this is a third-party model, so any
result from it will be a lab finding until a Pine twin exists (`docs/STRATEGY_WORKFLOW.md`).

---

## The model, as stated

⚠ **Both directions are written out in full below, deliberately.** "Bullish, invert for short" is
fine for a human reading a diagram and useless for a state machine — the two directions need
separate arm tests, separate sweep tests and opposite stop sides, and the inversion is where a
port silently gets it backwards.

### The one primitive everything is built from

**A level becomes LOADED when price returns to it, respects it (does not break it), and moves
away.** That is Marco's "high taken → low respected → move away". Every object below is this
primitive fired on one side or the other; the side decides the role.

### The sequence, both directions

| # | Step | LONG | SHORT |
|---|---|---|---|
| 1 | **Arm** | price trades **below** an old low from the left → long only | price trades **above** an old high from the left → short only |
| 2 | **Entry level forms** | the bounce prints a **low that respects an earlier low** — early buyers sit above it | the sell-off prints a **high that respects an earlier high** — early sellers sit below it |
| 3 | **Inducement** | price takes out a minor **high**; more buyers pile in | price takes out a minor **low**; more sellers pile in |
| 4 | **Engineered liquidity** | a **high** respects earlier highs then moves away → **the target** | a **low** respects earlier lows then moves away → **the target** |
| 5 | **Rejection** | price sells off from the EL zone | price rallies off the EL zone |
| 6 | **ENTRY** | price **sweeps the low from step 2** → buy the instant it is stabbed | price **sweeps the high from step 2** → sell the instant it is stabbed |
| 7 | **Stop** | **below** the liquidity block (the extreme of the arming leg) | **above** the liquidity block |
| 8 | **Target** | the EL highs from step 4 | the EL lows from step 4 |

**No EL = no setup.** Step 4 is the gate; without it there is nothing to target and nothing to
make the direction real. Steps 3 and 4 usually overlap in time — the same rally both induces and
builds the EL.

No refinement inside the entry level. He enters on the stab, not on an imbalance within it.

### Liquidity block — and it has TWO jobs, not one

A level that **already swept the level before it** and was left behind. It holds nothing; price
has no reason to return.

1. **It is where the stop goes.** Past it, so a normal sweep cannot clip it.
2. **It can VETO the trade.** If a block sits between the entry and where the stop must go, the
   stop is forced wide and the RR dies. Video 2 hits this on gold, calls the stop too big, and
   **skips the trade to drop a timeframe** for a tighter version of the same idea. This is the
   role that is easiest to miss and it is not optional — without it the backtest will take trades
   he would refuse.

⚠ **Step 7 was previously written as "below a prior low to the left", which is wrong** — 1b shows
it anchored to the extreme low of the arming leg (~0.2 pts of buffer on 1m gold), not to any
nearby prior low.

---

## What video 1 adds — the two rules that change the design

### 1. Liquidity is a LIFECYCLE on a level, not a property of it

This is the cleanest rule in either video and it is the thing to build first. Paraphrasing his
own sequence: a level that price merely traded through and left behind holds nothing and is safe
to enter from. Once price comes back, respects it, and moves away — *now* there is liquidity
there. He states the primitive as **high taken → low respected → move away**, and says that is
the market telling him liquidity rests below that low.

So each swing level has three states:

| State | How it got there | Role |
|---|---|---|
| **Fresh** | just printed, never revisited | nothing yet |
| **Liquidity-bearing** | revisited, respected, price moved away | **entry** (sweep it) or **target** |
| **Consumed** | traded through, not returned to | **stop anchor** — no reason for price to go back |

`equal_highs_lows` already does form → mitigate. This needs *respected* tracked as a middle
state, and it must **not** discard a mitigated level — a consumed level is what a stop hangs off.
That is a real extension, not a config change.

### 2. Engineered liquidity is an EVENT, not a side of the chart

Both roles above are produced by the *same* primitive — respect, then move away. Marco applies
the phrase "engineered liquidity" to whichever one he happens to be pointing at, which is fine
for a human and fatal for code. For the build there is **one detector** and the direction and
role fall out of which side it fired on:

- fired at a **high** in a long setup → that pool is the **target**
- fired at a **low** in a long setup → that pool is the **entry** to sweep
- fired at a supply area price then sells from → that is the push that delivers the entry

### 3. Hard filters he states outright

- Buy **below** lows, sell **above** highs. He says he will never take a long above the lows.
- A reaction inside a marked supply/demand area is **false by assumption** in the direction of
  the setup — it exists to build liquidity, not to be traded.
- No partials at a fixed R. Targets are levels or nothing.

### ⚠ The two videos CONTRADICT each other on trade management

| | Video 1 (2025-08) | Video 2 (2026-07) |
|---|---|---|
| After entry works | **Trails the stop below the new low**, explicitly says he is *not* a fan of breakeven | **Rolls to breakeven** once a high is taken |
| Partials | dislikes them | 20–25% at most, prefers none |

Trailing to a structure low and going flat-to-breakeven are materially different exit curves.
Ship both as `davinci_exit_mode` and measure. Do not silently pick one.

---

## Worked examples

All three screenshots so far are **one setup, 2026-01-27 on XAUUSD (OANDA)**, framed on two
timeframes: 5m for context and target, 1m for the entry. The two entries are ~70 minutes and
25 points apart, so they are two executions of one idea, not two trades.

### Example 1a — 5m context frame, LONG

Screenshot: TradingView long-position tool, "Marked up" layout. This is his **drawing tool**,
not a broker fill — "Closed P&L" equals the target distance exactly.

**Printed on the chart (exact):**

| | |
|---|---|
| Entry | 5,049.524 |
| Stop | 5,013.598 |
| Target | 5,173.001 |
| Stop distance | 35.926 (0.711% of price) |
| Target distance | 123.477 (2.445%) |
| R:R | 3.44 |
| Entry time | Tue 27 Jan 2026, ~08:50 |
| Target hit | ~16:00 same day (~7 h hold) |

**Read off the chart (approximate, pixel-derived):**

- **"Eng. LQ" is a BOX, not a line.** Roughly 5,095–5,113 — an ~18-point band, ~0.35% of price.
  Left-anchored at the first high of the cluster (~03:00 on the 26th), extended right ~18 hours.
- The EL zone is **not** the target. Target 5,173 sits well above it, and is not a visible prior
  high anywhere on this 5m window.
- Entry level = a swing low from ~21:00 on the 26th, swept ~11.5 hours later at 08:50.
- Stop 5,013.6 sits at a low from ~15:30 on the 26th. That low was **already swept** by a deeper
  low near 5,000 at ~18:00. The stop is above that deeper low, not below it.

**What this example pins down:**

- **The EL band is far wider than `equal_highs_lows` tolerance.** That engine defaults to
  ATR(50)×0.1. On 5m gold at $5,100 that is well under a point. His band is ~18 points — one to
  two orders of magnitude wider. **EQH as configured will not reproduce his marks.** Either
  `atr_mult` becomes a swept parameter at a much higher setting, or EL needs its own clustering
  rule (N pivots inside a band, not 2).
- **The entry low can be hours old.** ~11.5 h / ~138 bars on 5m. The scan needs a real lookback
  window, not "the last swing low".
- **The stop reading here is doubtful.** It looked like the stop sat *above* the deepest low
  (~5,000 at 18:00), which would be the liquidity-block rule. Example 1b contradicts that
  cleanly. Re-check whether the 5,000 low belonged to an earlier leg. Working rule is 1b's.

### Example 1b — 1m entry frame, same setup, LONG

Two screenshots: one wide (04:00–17:00) and one zoomed to the entry (09:00–10:45).
Chart title reads `Gold Spot / U.S. Dollar · 1 · OANDA` — 1m, not 15m.

**Printed on the chart (exact):**

| | |
|---|---|
| Entry | 5,056.964 |
| Stop | 5,046.188 |
| Stop distance | 10.776 |
| Entry time | Tue 27 Jan 2026, 09:59 |

**Read off the chart (approximate):**

| Time | Event |
|---|---|
| 09:15–09:18 | Extreme low, wicks to ~5,046.4. Hand-drawn "U" under it. |
| ~09:20 | Bounce prints a low at ~5,057 — the entry level, lined right. |
| 09:20→09:45 | Rally taking highs. Inducement. |
| 09:38–09:45 | **ENG LQ** box forms, ~5,077–5,081.5. Hand-circled. |
| 09:45→09:59 | Sell-off from the EL zone. |
| 09:59 | Sweep of the 5,057 low → **entry**. Stop 0.2 under the 09:15 extreme. |

**What 1b pins down:**

- **The stop anchors below the extreme low of the arming leg**, not below the entry low, and not
  above a liquidity block. Buffer is ~0.2 points, ~0.4 bp. Answers open question 4.
- **The entry low is the FIRST low after the extreme** — the low early buyers sit above as price
  bounces. Not the extreme itself, not the nearest low to the inducement. Answers question 3.
- **The EL zone scales with timeframe, and the ATR multiple may be constant.** 1m zone ~4.5 pts
  over 7 minutes; 5m zone ~18 pts over ~9 hours. Guessing ATR(50) at ~1–1.5 (1m) and ~3–5 (5m)
  gives a multiple of roughly **3–5 on both**. If that holds it is the tolerance rule, and it is
  30–50× the `equal_highs_lows` default of 0.1. ⚠ The ATR figures are estimated, not measured —
  **first thing to check against the cached M1/M15 bars at this exact timestamp.**
- **The RR multiplier is the stop, not the target.** Against 1a's 5,173.001 target the 1m entry
  gives `116.037 / 10.776 = 1:10.8`, against 1a's own 1:3.44. Same target, stop 3.3× tighter.
  That is his "1 to 12" claim reduced to arithmetic, and it says the whole edge claim rests on
  the entry timeframe rather than on level selection.
- The wide 1m shot carries a measure tool reading 19.306 (0.38%) over 303 bars, 10:00→15:03,
  spanning 5,042.450 → 5,061.756. Purpose unclear — possibly a partial. Not relied on.

### Example 2 — Aaron's own mark-up, MPC-JARVIS, XAUUSD 2026-08-05 → 07, LONG

⚠ **Aaron's boxes, not Marco's.** Useful for checking whether the model is recognisable through
the existing indicator. **Cannot be used to calibrate the EL tolerance** — only Marco's own boxes
can do that. Two screenshots, same chart, second with internal-structure labels on.

**The setup maps.** Every ingredient is present and in the right order:

| Step | On the chart |
|---|---|
| Arm | ASL / Ldn Low swept ~Aug 6 12:00 at ~4,223 (JARVIS: `SSL Swept — Ldn Low`) |
| Pool built | repeated respect of the 4,223–4,233 band |
| Inducement | push up ~Aug 6 20:30 taking highs — annotated *"induce early buyers"* |
| Entry | sweep back into ~4,230 — annotated *"Buy on fake bearish iSOS"* |
| Stop | would go below 4,223.14 (ASL / PDL) — the extreme of the arming leg |
| Target | EQH 4,304.61, with H4 H 4,266.03 and NY H ~4,280 as intermediates. `$$` marked on all. |

**The label is on the wrong object, and it matters.** The cyan `ENG LQ` box is drawn at
4,223.14–4,233.45 — at the **lows**. In a long setup that band is the sell-side pool the entry
sweeps. The engineered liquidity that makes it a long is the **high** above that respected prior
highs and became the target. Per the "EL is an event" rule above, both are the same primitive —
but they play opposite roles, and coding the low-side band as the gate builds a model with no
direction.

**Worth noting:** every JARVIS structure row reads Bearish while the annotation is a BUY. That is
**on model**, not a contradiction — the bearish 1m/15m shift *is* the "fake bearish iSOS". It is
also exactly why this model cannot be gated on a trend filter.

**Measured:** the band is 10.31 points at ~4,228, i.e. **0.244% of price**. Recorded for interest
only, per the caveat above.

---

## Open questions — what the next screenshots need to answer

Each of these changes the trade. None is answered by the video.

1. **How is the EL band sized?** Fixed % of price, ATR multiple, or the hull of the pivot cluster?
   Capture: several EL boxes with the price axis readable, on the same instrument and timeframe.
2. **How is the target chosen when it is above the EL zone?** Example 1's target is not a visible
   level on its own chart. Higher-timeframe level, or a fixed R? Capture: the same setup on the
   timeframe where the target level is visible.
3. ~~Which low is the entry?~~ **Answered by 1b** — the first low after the extreme. Confirm on
   a second setup.
4. ~~What anchors the stop?~~ **Answered by 1b** — below the extreme low of the arming leg, ~0.2
   pts buffer on 1m gold. Confirm, and find how the buffer scales.
5. **Is inducement required, or descriptive?** Capture: a setup he took with no high taken out on
   the pullback — if one exists.
6. **What kills a setup?** He says re-enter after a failed sweep. Capture: a losing or invalidated
   example. **This is the most valuable single screenshot and the hardest to get.**
7. **Which context timeframe picks the target, and how far down does he drop for entry?** 1a/1b is
   5m → 1m. The video also mentions 1H/4H entries on CFDs. Capture: a non-gold example, and one
   where the pair is not 5m/1m.
8. **Does the EL zone have to be broken before entry, or only formed?** In 1b price sells off from
   the zone without exceeding it. Capture: a setup where price trades through the EL zone first.
9. **Which exit rule is current — trail-to-structure or breakeven?** The two videos disagree.
   Video 2 is the later one, but he may simply have simplified for the audience. Capture: any
   screenshot showing a stop that has been moved.
10. **How long does a level stay "consumed"?** Video 1 says a level price never returned to holds
   nothing. It gives no expiry. Without one, every old swept low is a live stop anchor for ever.

---

## MEASURED 2026-08-13 — first real scan, and it is not a green light

```
python3 backtest/tools/loaded_level_scan.py --tf M15 --side both --control 40
```

**XAUUSD M15, 186,759 bars, 2018-09-13 → 2026-08-13.** Every setup scored against random entries
**matched on direction, stop distance and target distance** — gold ran ~1,200 → ~4,300 over this
window, so an unmatched long-side result is worthless.

| side | trades | hit | random hit | edge | z | R/trade | median stop | net of spread |
|---|---|---|---|---|---|---|---|---|
| long | 49 | 34.7% | 22.9% | **+11.8 pts** | **+1.96** | +0.751R | $2.81 | +0.633R |
| short | 80 | 21.2% | 20.9% | +0.4 pts | +0.09 | +0.016R | $2.15 | **−0.137R** |

🔴 **THE SHORT SIDE HAS NO EDGE, AND THE DETECTION IS NOT THE REASON.** The two funnels are nearly
identical (727 long vs 717 short setups reach "target built") because shorts are found by running
the *same code on inverted bars* — see `invert()`. So the asymmetry is in what happens after entry,
not in what gets found. **This is the third time in this repo a scan's short side has failed to
survive contact** (`internal_realign_scan.py` had it wrong in SIGN); do not build the short leg on
a scan result.

🔴 **THE EDGE ONLY EXISTS ABOVE A 2R FLOOR, AND THAT IS THE FINDING.** Sensitivity on `--min-rr`,
long side:

| min RR | trades | edge over control | z |
|---|---|---|---|
| 1.0 | 117 | +1.3 pts | +0.29 |
| 1.5 | 80 | +4.0 pts | +0.77 |
| **2.0** | **49** | **+11.8 pts** | **+1.96** |
| 2.5 | 31 | +11.9 pts | +1.64 |
| 3.0 | 26 | +7.8 pts | +1.02 |

**At the largest sample there is no edge at all.** Two readings, and they are not distinguishable
yet: either Marco is right that only the high-RR instances are the "higher probable ones" (he says
so, and refuses trades under ~1:3), or z peaking exactly at the tool's pre-existing default is
selection. ⚠ **The default was already 2.0 before this run** — treat the peak as suspect until a
walk-forward separates them.

⚠ **Caveats that matter more than the numbers.** n=49 is ~6 trades/year, z +1.96 is borderline;
one instrument, one timeframe, one parameter set; the outcome walk takes "which came first" and is
optimistic on bars touching both; no session filter, no position slot, no queueing, no swap. H1
(n=13) and H4 (n=3) are too thin to score at all — which is awkward, because the videos emphasise
higher timeframes.

✅ **What it does settle: "loaded" IS a filter.** 2,198 arms in 186,759 bars, and only 1,444 ever
build a target. That answers build-order step 4 — the level lifecycle is not describing most swing
levels.

⚠ **Two defects found in the scanner itself and fixed in the same pass**: it was **long-only**
(`Setup.dir` documented `"long" | "short"`, `dir="short"` constructed nowhere — root rule 10), and
it had **no control**, which the sibling `trigger_edge.py` calls the tool itself. The long-side
funnel and outcomes reproduce **exactly** across the change (1,073/1,052/925/727/49, 17 target /
32 stop), so no prior figure moves.

---

## Build order (revised after video 1)

1. **Measure the tolerance.** ATR(50) on cached M1/M15 at 2026-01-27 09:40 and 2026-01-26 09:00,
   against the 4.5 pt and 18 pt zones from 1a/1b. One command. Confirms or kills the ATR-multiple
   hypothesis before anything is written.
2. **Build the level-lifecycle detector** — fresh / liquidity-bearing / consumed, extending the
   `equal_highs_lows` shape. This is the whole model; the entry sequence is a thin layer on it.
3. **Draw it.** New chart layer beside `candle_overlays.py`, one string in `ANALYSIS_GROUPS`.
   Paint the three states in three colours on a real run and check against Marco's screenshots.
4. **Measure frequency before trading it.** If "liquidity-bearing" describes most swing levels,
   it is not a filter and everything downstream is noise.
5. Only then a strategy package, on the `b_leg` pattern.

---

## Capture checklist

For each screenshot, the useful ones have: the price axis visible, the timeframe visible, the
position tool with entry/stop/target numbers showing, and enough bars left of entry that the EL
zone and the arming sweep are both on screen. A zoomed-in entry shot is worth less than a wide one.

Losers and invalidations are worth more than winners. A model only shown on its winners has no
measurable win rate, and that is the exact claim being tested.
