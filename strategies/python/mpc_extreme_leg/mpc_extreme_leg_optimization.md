# MPC Extreme Leg — Optimization Log

**Every parameter sweep run on this bot goes in this file, newest run at the bottom.**
Each entry records the question, the answer, how it was measured, and the full grid — so a
later run can be compared against an earlier one instead of re-litigated.

**Why this file exists:** three separate searches have now landed back on the shipped
settings, and two of them re-tested ideas an earlier one had already refused. A refusal that
is not written down gets retried, and retrying a sweep is how a noise result eventually wins
by chance. **A negative result recorded here is worth as much as a positive one.**

Standing rules for anything recorded here:

- **Score in R, never dollars.** Sizing risks a fixed percentage of equity, so dollars
  compound and a dollar ranking measures recency rather than edge.
- 🔴 **A cut is applied to the SETUP POOL, before the one-position rule.** This bot holds ONE
  position, so refusing a setup genuinely buys whatever came next. Scoring a cut by deleting
  rows from a finished result measures a strategy that could see the future, and it flatters
  every cut ever tried — Run 11 is the worked example: a cut that looked free on the finished
  book cost 10R when it was actually run.
- **Print the NEIGHBOURS of any winner.** Several axes here move 10R between adjacent values.
  Without neighbours a coin landing well reads as a 4% improvement.
- **Re-check any winner on both halves of the history.** A setting that only works in one half
  is not a setting, it is a story.
- 🔴 **Every run carries a CONTROL row that must reproduce the shipped baseline exactly.** If
  the control has moved, the harness moved and no row in that run is readable. This has caught
  nothing yet, which is the point — it is how you find out it did.
- **A result here is a measurement, not a default.** Adopting one means a commit across
  `config.py`, `strategies/tradingview/tools/build_extreme_leg.py` (which generates BOTH Pine
  files — never edit either `.pine`) and `compare_extreme_leg.py`, with the parity gate re-run
  green.
- ⚠ **A one-at-a-time sweep cannot see an interaction, so its winners are candidates and never
  conclusions.** Requiring two liquidity levels is the standing example: measured alone it is
  the single best change available, and combined with the half-way exit it cuts the return by
  more than half.

## The basis

Unless a run says otherwise:

| | |
|---|---|
| tooling | `backtest/tools/pre_sos_leg.py` + `pre_sos_leg_queued.py` + `pre_sos_leg_tune.py` |
| data | Vantage XAUUSD, 187,386 M15 bars and 562,071 M5 bars, 2018-09-13 → 2026-08-23 |
| frames | 15m for trend and target, 5m for the trigger |
| costs | half the spread at entry (0.22), and nothing else |
| position slot | ONE, applied after any cut |
| shipped baseline | **208 trades, 47.6% hit, +0.400R, +83.3R, worst losing run 9.7R** |
| the same with Friday refused | **169 trades, 50.3% hit, +84.0R, worst losing run 7.9R** |

🔴 **THE STUDY HAS NO TRANSITIONING-MARKET REFUSAL AND THE SHIPPED BOT DOES.** That cut lives
only on the Python side (`engines/regime/` has no Pine source), so every figure in this file
describes the strategy WITHOUT it. Run 5 measures what it is worth on its own basis; the two
may not be added together.

⚠ **These are STUDY numbers, not lab numbers.** The study charges half a spread and nothing
else — no commission, no swap, no slippage. The real bill is in
`strategies/tradingview/docs/mpc_extreme_leg_strategy.md` → *The real bill, on the account this
will actually trade*. Rankings survive the difference; totals do not.

## Runs

| # | Date | What was swept | Winner | Status |
|---|---|---|---|---|
| 1 | 2026-08-25 | **The tuning pass, with the position slot ON** — every knob moved one at a time around the then-shipped values. The parent study had scored everything with no slot, which is not this strategy. | **TWO CHANGES ADOPTED: air under the stop 0.05 → 0.20 ATR, and take profit the whole swing → HALF the way to it.** 200 trades / 27.5% / +55.2R / 18.1R drawdown became **208 / 47.6% / +83.3R / 9.7R**. | ✅ **SHIPPED** |
| 2 | 2026-08-25 | **Breakeven arming** — move the stop to entry once price has travelled 30/50/70/90% of the way | **STAYS OFF, and it is a measurement rather than caution.** Arming at 30% costs −0.217R; the best point (~70%) is worth +0.024R, i.e. noise. Win rate falls 28.1% → 16.2% while losses only fall 71.9% → 50.9%. | **do not build it** |
| 3 | 2026-09-01 | 🔴 **THE EXHAUSTIVE SEARCH — 509,000 configurations across 5 grids**, plus every pairing of base and trigger chart | **NOT ONE BEAT THE SHIPPED SETTINGS.** The fine pass named a winner (sweep within 165 min, +86.8R vs +83.3R) and it was **rejected on its neighbours** — adjacent 15-minute steps run 74 / 87 / 83 / 75 / 77 / 74, so the axis moves 10R between neighbours and 165 is a coin landing well. Timeframe answered: **15m base with a 5m trigger**; 30m/5m gives +35.9R, 15m/1m +38.0R. | **shipped settings CONFIRMED** |
| 4 | 2026-09-01 | **Refusing Friday** (day read in UTC, because that is how it was measured) | ✅ **ADOPTED.** 40 Friday setups over eight years returned **+1.1R between them** while supplying 25 of the losses. 208 → 169 trades, +83.3R → **+84.0R**, worst losing run 9.7R → **7.9R**. ⚠ Friday is not reliably bad — it lost 8.5R in the first half of the history and made 9.6R in the second. The case is that it adds risk without adding return. ⚠ Weekend carry is not the mechanism: 18 Friday trades ran past Friday for +5.2R. | ✅ **SHIPPED, defaults ON** |
| 5 | 2026-09-02 | **Refusing a transitioning market**, and a news-blackout cut alongside it. 470,995 PU Prime `XAUUSD.p` M5 bars, 2020-01-01 → 2026-08-23 — a different basis from the rest of this file | ✅ **THE TRANSITIONING CUT ADOPTED:** worst losing run **8.13R → 6.00R while the money goes UP, +57.10R → +58.53R**, on 40 refusals out of 550 setups. ❌ **The news cut is worse on both counts** (+51.45R, worst run 8.87R) and stays off. 🔴 Neither can exist in the Pine, so the chart takes 19 trades the bot refuses. | ✅ **TRANSITIONING SHIPPED; news OFF** |
| 6 | 2026-09-01 | **The two-stage exit ladder** — take part of the position at one distance and let the rest run to another, with and without moving the stop up after the first fill. **160 ladders** | **REJECTED AS NOISE.** Best scores +85.8R against the single exit's +84.0R — a 2% gain for three new inputs — and its four nearest neighbours run +81.8R, +82.1R, +84.5R, +85.8R, with the shipped single exit sitting inside that band. 🔴 **The FIRST search got the answer wrong because of its axes**: it only offered ladders whose second leg ran FURTHER, every one lost, and the reason took the slot to see — a runner holds the position 625 minutes against 400 and blocks ten setups. **A search that can only move a setting one way has decided the answer before it runs.** | **do not build it** |
| 7 | 2026-09-01 | **Six ideas that did not work**, recorded so they are not tried again — session filters, capping how far the swing may be, a floor or ceiling on stop size, breakeven arming, trading one side only, demanding two liquidity levels agree | **ALL SIX LOSE MONEY.** Asia is the best session per trade (+0.534R on 68 trades) and refusing it drops the average to +0.335R. Nearby targets win most often and pay least; the 8 setups aiming 9+ stops away pay **+1.83R each**. Longs alone +47.4R, shorts alone +35.9R, **together +83.3R** — they do not compete for the slot. Two levels halves the take, +83.3R → +38.6R, and its halves fall apart (+0.133 / +0.547). | **do not build any of them** |
| 8 | 2026-09-03 | **THE FULL EXIT CURVE, 40% → 100% of the way to the swing at 5% steps** — Runs 1 and 3 swept this at 10% steps and a fine pass covered 44–54%, so **nothing recorded what 55–95% scored** and the gap between "half way" and "the whole swing" had no committed number | **50% CONFIRMED, and there is no sweet spot in the gap.** 50% makes the most money AND has the smallest drawdown: **+83.3R at 9.7R**, against +74.4R at 55%, +61.7R at 60%, +69.6R at 100% — and every point past 50% roughly doubles the drawdown (12.6R to 20.7R). Hit rate falls 47.6% → 40.9% → 29.7%. 50% is also the only setting strong in **both** halves (+0.386R then +0.414R). | **shipped default CONFIRMED** |
| 9 | 2026-09-03 | **Re-vet of the two structure settings Aaron asked about** — how recently a level must have been swept (shipped 3 hours) and how far back the extreme is looked for (shipped 2 hours), plus the stop cushion | **BOTH CONFIRMED. The sweep window is a sharp peak** — 1h +14.3R, 2h +40.8R, **3h +83.3R**, 4h +74.3R, 8h +59.7R — best money and lowest drawdown together. **The extreme lookback has one small open trade-off:** 2h makes the most money (+83.3R / 9.7R) but 3h, 4h and 6h are **identical** (+79.5R / 8.7R) — past 3 hours the extreme stops moving, so the real choice is 2h or "wide", and wide pays 3.8R for 1R off the worst run. Stop cushion 0.20 ATR re-confirmed as a smooth hill. | **shipped CONFIRMED; one open decision, see Run 9 below** |
| 10 | 2026-09-03 | 🔴 **"WHAT DO THE LOSERS HAVE IN COMMON, AND CAN WE CLOSE EARLY?"** — Aaron's question. Every trade the shipped configuration books, profiled across 8 features, plus **a TIME STOP swept from 1 hour to 3 days** — the one exit rule this strategy has never had | **THE TIME STOP IS DEAD AND THE CURVE IS PERFECTLY MONOTONIC:** 1h −3.7R, 4h +6.2R, 12h +34.3R, 24h +60.6R, 48h +79.4R, 72h +81.1R, **no limit +84.0R**. It frees the slot (169 → 181 trades) and still loses. 🔴 **The mechanism is the finding: losers die fast and winners take days.** Quickest quarter of trades 32.6% hit / −9.9R; slowest quarter 69.0% hit / +63.0R. **A time stop cuts the winners.** 🔴 **And no early exit of any kind can work here: ZERO of 84 losers ever reached half way to the target** (median loser got 12%). Nothing else the losers share is cuttable. | **do not build it** — read the verdict |
| 11 | 2026-09-03 | **The two cuts Run 10's profile pointed at** — a CEILING on stop size (the widest quarter paid +0.052R a trade) and a higher FLOOR on distance to the swing (the nearest quarter paid +0.284R). Applied to the setup pool, before the slot | **BOTH FAIL.** Every stop ceiling loses: 4.0 → +32.9R, 5.0 → +71.7R, 6.0 → +73.4R, 8.0 → +82.6R against the control's **+84.0R**. Only 7.0 beats it, by +1.2R, with neighbours +79.7R / **+85.2R** / +82.6R — a lone bump. The target floor declines monotonically: 2.5 → +71.3R, 3.0 → +69.0R, 4.0 → +51.7R. Combining them does not rescue either (best pairing +73.1R). 🔴 **THE TRANSFERABLE RESULT: on the finished book the widest-stop trades looked like +2.2R across 42 trades, obviously free to delete. Refusing them properly costs 10R,** because the slot they occupied was going to be occupied anyway. | **do not build either** |

⚠ **Runs 1–7 are BACK-FILLED from `strategies/tradingview/docs/mpc_extreme_leg_strategy.md` on
2026-09-03 and were NOT re-run that day.** They are recorded here so the file is a complete
record of what has been tried; the strategy doc remains the authority on their detail. Runs 8–11
were run on 2026-09-03 and their grids below are the primary record.

🔴 **WHAT EVERY RUN IN THIS FILE HAS IN COMMON: nothing beats the shipped settings.** Three
independent searches — a 509,000-configuration sweep, a 160-ladder exit search, and the four
runs of 2026-09-03 — have each landed back on the same configuration. ⚠ **The honest reading is
that this strategy is TUNED, and the next R comes from another leg, another instrument or
another timeframe rather than another knob.** That is the standing conclusion of the root
`CLAUDE.md` → *Trading Philosophy*, arriving here from the measurement side.

---

# Run 8 — the full exit curve, 40% to 100%

**Date:** 2026-09-03
**Question:** Aaron — *"and there is no sweet spot between 1:1 and 1:2?"*
**Tool:** a one-off over `pre_sos_leg_tune.py`'s own collection and scoring, 5% steps
**Basis:** the standard basis above. Friday NOT refused (the study has no such filter), so the
control is the 208-trade baseline.

**Why it was run:** the exit was swept at 10% steps in Run 1 and again in Run 3, and a fine pass
covered 44–54%. **Nothing anywhere recorded what 55%, 65%, 75%, 85% or 95% scored.** The gap
between the shipped half-way exit and the whole swing had no committed number, so the question
could be asked again for ever.

**Control:** the 50% row reproduced the shipped baseline exactly — 208 trades, 47.6%, +83.3R,
worst run 9.7R.

| exit at | trades | hit | per trade | total | worst run | return / drawdown |
|---|---|---|---|---|---|---|
| 40% | 213 | 51.2% | +0.306R | +65.2R | 10.5R | 6.19 |
| 45% | 212 | 49.1% | +0.342R | +72.5R | 10.1R | 7.17 |
| **50%** | **208** | **47.6%** | **+0.400R** | **+83.3R** | **9.7R** | **8.60** |
| 55% | 203 | 44.8% | +0.366R | +74.4R | 12.6R | 5.91 |
| 60% | 203 | 40.9% | +0.304R | +61.7R | 14.3R | 4.30 |
| 65% | 201 | 38.3% | +0.283R | +56.9R | 14.3R | 3.98 |
| 70% | 198 | 37.4% | +0.332R | +65.7R | 15.8R | 4.16 |
| 75% | 197 | 34.5% | +0.304R | +59.9R | 20.7R | 2.90 |
| 80% | 197 | 33.0% | +0.311R | +61.3R | 19.9R | 3.09 |
| 85% | 195 | 32.3% | +0.337R | +65.7R | 19.0R | 3.46 |
| 90% | 195 | 31.3% | +0.349R | +68.1R | 18.2R | 3.74 |
| 95% | 195 | 29.7% | +0.304R | +59.2R | 18.4R | 3.22 |
| 100% | 195 | 29.7% | +0.357R | +69.6R | 17.6R | 3.96 |

**Verdict: 50% wins on money and on drawdown at the same time, which is unusual and is why it
ships.**

- **Reaching past half way roughly doubles the drawdown.** 9.7R becomes 12.6R at 55% and 15–20R
  beyond. You pay a much rougher ride for less money.
- **The hit rate collapses:** 47.6% at half way, 40.9% at 60%, 29.7% at the full swing. The leg
  genuinely does not get there most of the time.
- ⚠ **The wobble between 60% and 100% (+57R up to +70R) is a handful of trades flipping.** Do
  not read the 100% row as a second peak — it is 14R below the shipped setting with nearly
  twice the drawdown.
- **The trade count falls as the exit widens** (208 → 195) because a trade reaching further
  holds the slot longer. That is the slot effect Run 1 found, visible again on a different axis.

**Both halves of the history:**

| exit at | first half | second half |
|---|---|---|
| **50%** | **+0.386R (101)** | **+0.414R (107)** |
| 55% | +0.257R (98) | +0.469R (105) |
| 100% | +0.296R (93) | +0.412R (102) |

⚠ **50% is the only setting that is strong in both halves.** 55% looks respectable overall and
is carried by its second half; the same is true of 100%. This is the check that separates the
shipped value from its neighbours.

---

# Run 9 — the sweep window and the extreme lookback, re-vetted

**Date:** 2026-09-03
**Question:** Aaron — *"did we vet the 3 hrs param and did we vet the stop sits beyond the
extreme of the last 2 hours, any more optimizations to these improve anything?"*
**Tool:** `python3 backtest/tools/pre_sos_leg_tune.py --stage structure`
**Basis:** the standard basis above. Control reproduced at 208 / 47.6% / +83.3R / 9.7R.

## How recently a level must have been swept — shipped 3 hours

| window | trades | hit | per trade | total | worst run | return / drawdown |
|---|---|---|---|---|---|---|
| 1h | 60 | 41.7% | +0.239R | +14.3R | 12.0R | 1.19 |
| 2h | 141 | 44.7% | +0.289R | +40.8R | 12.0R | 3.40 |
| **3h** | **208** | **47.6%** | **+0.400R** | **+83.3R** | **9.7R** | **8.60** |
| 4h | 261 | 43.7% | +0.285R | +74.3R | 10.7R | 6.96 |
| 6h | 313 | 42.8% | +0.232R | +72.5R | 10.8R | 6.70 |
| 8h | 342 | 41.2% | +0.175R | +59.7R | 14.6R | 4.08 |

**Verdict: a sharp peak, and there is nothing here to take.** 3 hours is best on total R, on
expectancy, on hit rate and on drawdown simultaneously. Tighter throws away the trades that
pay; looser adds trades that do not — 8 hours takes 134 more trades than 3 hours and makes 24R
less.

⚠ **This is the axis Run 3's fine pass found 165 minutes on.** The neighbours there ran
74 / 87 / 83 / 75 / 77 / 74 across single 15-minute steps, so this axis moves ~10R between
adjacent values and a 4% "improvement" on it is not a setting. **Do not re-run a fine pass here
expecting a different answer.**

## How far back the extreme is looked for — shipped 2 hours

| lookback | trades | hit | per trade | total | worst run | return / drawdown |
|---|---|---|---|---|---|---|
| 1h | 235 | 42.6% | +0.271R | +63.8R | 9.3R | 6.89 |
| 1.5h | 212 | 45.8% | +0.371R | +78.5R | 9.7R | 8.11 |
| **2h** | **208** | **47.6%** | **+0.400R** | **+83.3R** | **9.7R** | **8.60** |
| 3h | 200 | 47.5% | +0.398R | +79.5R | **8.7R** | **9.16** |
| 4h | 200 | 47.5% | +0.397R | +79.4R | 8.7R | 9.14 |
| 6h | 200 | 47.5% | +0.397R | +79.4R | 8.7R | 9.14 |

**Verdict: 2 hours confirmed on money, with ONE open trade-off worth stating rather than
burying.**

- **3h, 4h and 6h are identical.** Past 3 hours the extreme stops moving, so this axis is not
  really continuous — it is a choice between 2h and "wide".
- **Wide costs 3.8R and buys 1.0R off the worst losing run** (+83.3R / 9.7R against
  +79.5R / 8.7R), and it wins on return-over-drawdown, 9.16 against 8.60.
- ⚠ **That is a decision about risk appetite, not a measurement with a right answer.** At 5%
  a trade a full R off the worst run is worth something real. It is small either way and it is
  **NOT ADOPTED** — recorded here so the next person does not have to re-run the axis to find
  it.
- ⚠ **This CORRECTS a line in the strategy doc** which said *"90 min scores marginally better
  alone"*. On the current basis 1.5h scores **+78.5R against 2h's +83.3R** — worse, not better.
  The doc's own caveat (*"adds nothing once the stop is wider"*) explains it: that reading
  predates the 0.20 ATR cushion adopted in Run 1.

## Air under the stop — shipped 0.20 ATR, re-confirmed

| cushion | trades | hit | total | worst run |
|---|---|---|---|---|
| 0.0 | 213 | 44.1% | +68.2R | 8.5R |
| 0.05 | 213 | 45.1% | +73.1R | 8.6R |
| 0.10 | 210 | 45.7% | +74.1R | 9.6R |
| **0.20** | **208** | **47.6%** | **+83.3R** | **9.7R** |
| 0.30 | 206 | 47.1% | +77.1R | 9.7R |
| 0.50 | 198 | 47.0% | +70.7R | 9.9R |

A smooth hill with the shipped value on top, exactly as Run 1 found. No lone spike.

---

# Run 10 — what the losers have in common, and the time stop

**Date:** 2026-09-03
**Question:** Aaron — *"what about losing trades can we use to kill or prevent taking more of
them? Like time trade opened close early or anything losing trades have in common?"*
**Tool:** a one-off profiler over the study's own collection, walk and slot
**Basis:** the standard basis. Every profile is printed twice — as the study books it, and with
Friday refused — because **the live file already refuses Friday and the first thing an
un-adjusted profile "discovers" is a cut that is already in.** The Friday-refused numbers are
the ones quoted below.

**The time stop needed no second walk.** The study's walk reports the bar a trade resolved on
over the full horizon; if that bar is past the limit then nothing resolved inside the limit, and
the trade is booked at the close of the limit bar. Reusing it is what keeps the comparison
honest.

**Control:** 208 / 47.6% / +83.3R / 9.7R reproduced exactly.

## The time stop — give up on a trade that has not resolved

Applied **before** the one-position rule, so giving up early genuinely buys the next setup.

| give up after | trades | hit | total | worst run | vs no limit |
|---|---|---|---|---|---|
| **no limit** | **169** | **50.3%** | **+84.0R** | **7.9R** | — |
| 1h | 181 | 41.4% | −3.7R | 9.8R | −87.7R |
| 2h | 181 | 43.6% | −6.6R | 15.6R | −90.6R |
| 4h | 181 | 48.1% | +6.2R | 9.4R | −77.8R |
| 6h | 181 | 49.2% | +20.6R | 10.0R | −63.4R |
| 8h | 179 | 48.0% | +8.3R | 16.1R | −75.7R |
| 12h | 179 | 52.0% | +34.3R | 10.5R | −49.7R |
| 24h | 175 | 51.4% | +60.6R | 10.8R | −23.4R |
| 48h | 173 | 49.7% | +79.4R | 8.9R | −4.6R |
| 72h | 170 | 50.6% | +81.1R | 8.1R | −2.9R |

🔴 **DEAD, and the curve is about as clean a refusal as a sweep produces: perfectly monotonic.**
The longer a trade is allowed to breathe, the more it makes, right up to no limit at all.

⚠ **It frees the slot — 169 trades become 181 — and still loses.** The extra setups do not pay
for what the limit cuts. **This is the strongest form of the answer**, because the slot is the
mechanism that rescued the earlier exit change in Run 1, and here it cannot.

## Why — losers die fast, winners take days

| bars held | trades | hit | total | per trade |
|---|---|---|---|---|
| quickest quarter (≤30 bars, 2.5h) | 43 | 32.6% | −9.9R | −0.231R |
| second (30–80) | 42 | 35.7% | −4.0R | −0.094R |
| third (80–193) | 42 | 64.3% | +34.9R | +0.832R |
| slowest quarter (>193 bars, 16h) | 42 | 69.0% | +63.0R | +1.500R |

**This is the strongest split in the entire profile, and it is the mechanism behind the time
stop's failure: a time limit cuts the winners, not the losers.**

🔴 **IT IS NOT A FILTER AND MUST NEVER BE READ AS ONE. Holding time is an OUTCOME, known only
after the trade is over.** There is nothing at entry that tells you which quarter a setup will
land in. The row above explains a refusal; it does not license a rule.

## How far the losers got before dying

| | |
|---|---|
| median loser | **12%** of the way to the half-way target |
| 75th percentile | 20% |
| 90th percentile | 36% |
| losers reaching 25% | 17 of 84 (20%) |
| losers reaching **50%** | **0 of 84** |
| losers reaching 75% | 0 of 84 |

🔴 **THIS KILLS THE WHOLE EARLY-EXIT FAMILY IN ONE NUMBER: not one loser in eight years ever got
half way.** There is nothing to rescue. No trailing stop, no partial bank, no breakeven move can
save a trade that never travels in your favour — it can only tax the winners on their way past.

✅ **It independently confirms Run 2's breakeven refusal from a completely different direction.**
Run 2 measured that arming a breakeven stop costs money; this says why it must — the losers were
never in profit to be protected.

## Everything else the losers share — nothing cuttable

**Day of week** (Friday already refused):

| day | trades | hit | per trade |
|---|---|---|---|
| Wed | 43 | 58.1% | +0.714R |
| Mon | 45 | 55.6% | +0.534R |
| Thu | 45 | 42.2% | +0.421R |
| Tue | 36 | 44.4% | +0.288R |

The worst remaining day still pays +0.288R. **There is no second Friday.**

**Hour of day, 4-hour blocks, UTC:** best 04:00–07:59 at +0.912R, worst 08:00–11:59 at
+0.253R — **every block positive**. Consistent with Run 7: session filters lose money.

**Direction:** longs +0.915R on 56 trades, shorts +0.290R on 113. Shorts are twice as many and
still make +32.8R. Cutting them loses money, as Run 7 already found.

**Which level was swept** (a setup can carry more than one): H4 +0.460R on 147, session +0.431R
on 102, daily +0.408R on 56, weekly +1.055R on **7**. All positive; the weekly figure is seven
trades and is not actionable.

**How many levels agreed:** 1 → +0.554R, 2 → +0.602R, 3 → +0.288R, 4 → +0.553R. **Not
monotonic, therefore not a pattern.** Run 7 already refused the two-level version on a full
re-run.

**Year:** every year positive once Friday is out; worst is 2024 at +0.040R over 18 trades.

⚠ **Standing caveat on this whole run: 169 trades and eight features examined.** Anything that
looked promising here was sent to Run 11 to be re-run properly rather than believed off the
profile — which is exactly what the profile is for.

---

# Run 11 — the two cuts the profile pointed at

**Date:** 2026-09-03
**Question:** the two features in Run 10 that looked cuttable — the widest quarter of stops
(+0.052R a trade over 42 trades) and the nearest quarter of targets (+0.284R against the
farthest quarter's +1.098R)
**Tool:** a one-off applying each cut to the setup pool, then re-running the slot
**Basis:** the standard basis with Friday refused. **Control: 169 / 50.3% / +84.0R / 7.9R.**

## A ceiling on stop size, in multiples of the 5-minute average range

| refuse a stop wider than | trades | hit | total | worst run |
|---|---|---|---|---|
| **no cut** | **169** | **50.3%** | **+84.0R** | **7.9R** |
| 4.0 | 46 | 52.2% | +32.9R | 3.0R |
| 5.0 | 90 | 54.4% | +71.7R | 7.0R |
| 5.5 | 106 | 50.9% | +66.9R | 7.0R |
| 6.0 | 122 | 50.8% | +73.4R | 7.0R |
| 6.5 | 135 | 51.1% | +79.7R | 6.8R |
| 7.0 | 148 | 52.0% | +85.2R | 7.8R |
| 8.0 | 161 | 50.3% | +82.6R | 6.9R |
| 10.0 | 165 | 50.3% | +83.6R | 6.9R |

**FAILS.** Only 7.0 beats the control, by **+1.2R — 1.4%** — and its neighbours run
+79.7R / **+85.2R** / +82.6R. **A lone bump between two lower values is a coin landing well.**
The shape of the whole axis is simply *the more you refuse, the less you make*.

## Raising the floor on how far the swing must be

| refuse a target nearer than | trades | hit | total | worst run |
|---|---|---|---|---|
| **2.0 (shipped)** | **169** | **50.3%** | **+84.0R** | **7.9R** |
| 2.5 | 131 | 46.6% | +71.3R | 9.0R |
| 3.0 | 98 | 46.9% | +69.0R | 7.0R |
| 3.5 | 86 | 46.5% | +65.5R | 6.0R |
| 4.0 | 62 | 43.5% | +51.7R | 7.0R |
| 4.5 | 50 | 46.0% | +51.3R | 5.0R |
| 5.0 | 37 | 43.2% | +40.7R | 4.4R |

**FAILS, monotonically.** The near-target trades pay less each but they pay, and there are many
of them. This is the mirror of Run 7's finding that capping the far end also loses money — **the
distance axis is not a filter in either direction.**

## The two together

| | trades | total | worst run |
|---|---|---|---|
| stop ≤ 5.0, target ≥ 3.0 | 63 | +63.2R | 5.0R |
| stop ≤ 6.0, target ≥ 2.5 | 101 | +67.0R | 7.0R |
| stop ≤ 6.5, target ≥ 2.5 | 110 | **+73.1R** | 7.0R |
| **no cut** | **169** | **+84.0R** | **7.9R** |

No interaction rescues either cut. The best pairing is 11R below the control.

## Both halves

| | first half | second half |
|---|---|---|
| stop ≤ 6.0 | +0.744R (61) | +0.459R (61) |
| target ≥ 3.0 | +0.791R (46) | +0.626R (52) |
| **control** | **+0.580R (80)** | **+0.422R (89)** |

⚠ **Both cuts raise per-trade expectancy in both halves and still lose on total R.** That is the
whole trap in one line: **they are not making the trades better, they are making them fewer**,
and this bot's constraint is opportunity rather than quality.

## 🔴 The transferable result — why the method matters more than the answer

**On the finished book, the widest-stop trades contributed +2.2R across 42 trades. Deleting them
looks obviously right: 42 trades of dead weight, gone.**

**Refusing them properly costs 10R.**

The gap is the slot. A trade you refuse does not remove its risk from the book — it hands the
slot to whatever came next, and what came next was, on average, no better. **Scoring a cut by
deleting rows from a finished result measures a strategy that could see the future**, and it
will endorse almost any cut you propose.

⚠ **This is the standing reason every cut in this file is applied to the setup pool before the
one-position rule, and it is the single most important line in the document.** Any future
"let's just stop taking those" idea must be run this way or its number is fiction.
