# Intraday edge study — what stacks with the SOS Fade SOS fade

**Status:** ✅ **CLOSED 2026-08-07 — measured, with a recommendation in the last section.** Two results, and they point opposite ways: **no intraday edge on GOLD** (structural, not a tuning problem) while **the same trigger clears cost on NAS100**. Kept as the record of why. Read the Recommendation before proposing any intraday leg.

**Date:** 2026-08-07
**Tool:** `backtest/tools/intraday_edge.py` (stdlib only, runs off `backtest/cache/`)
**Question:** Aaron has one profitable 15m swing strategy (`sos_fade`) and wants a SECOND,
intraday, easy-to-run strategy that adds trade frequency rather than queueing behind the first.

Run it:

```
command-center/backend/.venv/bin/python backtest/tools/intraday_edge.py --symbol XAUUSD --target 1.0
command-center/backend/.venv/bin/python backtest/tools/intraday_edge.py --symbol NAS100 --target 1.0
```

---

## Method, and the three things that make it trustworthy

Eight intraday triggers were built off the canonical engines and scored on one question: from the
bar the trigger puts you IN on, does price reach `+NR` before `-1R`, within an intraday horizon?

1. 🔴 **Every set is scored against a random control MATCHED ON DIRECTION AND STOP DISTANCE.**
   Both instruments rose hard across the window, so a long-side "edge" is free. The harness
   self-check prints the control at every stop distance and it lands on the theoretical breakeven
   at `+0.0% (+0.0σ)` — that is what certifies the harness before any result is read off it.
2. ⚠ **A HARD INTRADAY HORIZON (32 M15 bars = 8h).** Without it the sweep-fades quietly become
   swing trades and score as such. Unresolved at the cap counts as 0R, applied to the control identically.
3. ⚠ **Nothing is evaluated on the bar it acts on.** Every trigger fires on a CLOSED bar and enters
   at that bar's close. This is the look-ahead trap `trigger_edge.py` already fell into once.

🔴 **The deciding column is NET, not edge.** Cost in R is `cost_usd / stop_usd`, charged per trade.
A gross edge is not a strategy — the H4 sweep study found a real +0.073R fade that never cleared cost.

---

## Result 1 — there is no intraday edge to harvest on GOLD, and the reason is structural

Every trigger, 186,384 true-M15 XAUUSD bars, 2018-09-13 → 2026-08-07, scored at 1R:

| trigger | n | edge vs control | median stop | cost as %R | **NET** |
|---|---|---|---|---|---|
| ORB_BREAK | 2623 | +2.6% (+2.4σ) | $6.65 | 4.5% | **−0.008** |
| EQ_FADE | 2572 | +1.2% (+1.2σ) | $3.17 | 9.5% | −0.076 |
| PD_FADE | 1438 | +0.6% (+0.4σ) | $3.73 | 8.1% | −0.075 |
| LDN_FADE | 1085 | −0.1% | $3.47 | 8.6% | −0.096 |
| ASIA_FADE | 1935 | −1.0% | $3.37 | 8.9% | −0.114 |
| VWAP_STRETCH_FADE | 24461 | **−1.8% (−5.6σ)** | $1.57 | 19.1% | −0.279 |
| VWAP_TREND_BOUNCE | 12295 | **−3.1% (−6.8σ)** | $1.24 | 24.2% | −0.360 |
| ORB_FADE | 2582 | **−5.7% (−6.5σ)** | $0.80 | 37.5% | −0.817 |

**Not one trigger is net-positive.** The best (`ORB_BREAK`) is +2.6% over random and lands at
**−0.008R after cost** — a real, statistically detectable effect that is almost exactly the size of
the spread. Stacking confluence on it gets to `+0.003R` at best (pro-trend VWAP side), which is
+6R over eight years and 2,019 trades. Nothing.

**The mechanism, and it generalises past these eight triggers.** An intraday stop on gold is
$1–7. The round trip is ~$0.30. So cost is **4–37% of every R** before the signal says anything.
The directional information available (2–3% win rate over random) is worth ~0.03–0.05R gross, and
cost eats all of it. **This is why the SOS fade works and an intraday sibling does not — same
instrument, but a median $8.88 stop puts cost at ~3% of R.**

Two results are strongly NEGATIVE and worth keeping as knowledge: fading a VWAP stretch and fading
the opening-range break both lose to random with high significance, in 9 years out of 9. Gold does
not mean-revert intraday. Do not build either.

---

## Result 2 — the SAME trigger clears cost comfortably on NAS100

The cost hypothesis makes a prediction: move to an instrument whose spread is smaller relative to
its intraday range and the same signal should survive. NAS100's spread is $0.80 on a 29,687 price
= **0.0027%, half gold's 0.0053%**, while an index intraday stop is 50–150 points.

185,463 true-M15 NAS100 bars, same window, scored at 1R, cost charged at **$1.00** (live spread
$0.80 plus headroom):

| trigger | n | edge vs control | median stop | cost as %R | **NET** |
|---|---|---|---|---|---|
| **ORB_BREAK** | **2658** | **+4.0% (+3.6σ)** | **85.68** | **1.2%** | **+0.049** |
| EQ_FADE | 2347 | +1.6% (+1.5σ) | 26.75 | 3.7% | −0.018 |
| ASIA_FADE | 2326 | +1.4% (+1.3σ) | 28.50 | 3.5% | −0.020 |
| PD_FADE | 1425 | +0.7% | 30.95 | 3.2% | −0.033 |
| LDN_FADE | 1457 | −1.4% | 34.10 | 2.9% | −0.071 |
| VWAP_TREND_BOUNCE | 12656 | −2.4% (−5.5σ) | 9.75 | 10.3% | −0.229 |
| VWAP_STRETCH_FADE | 22215 | −3.0% (−9.1σ) | 13.75 | 7.3% | −0.185 |
| ORB_FADE | 2579 | **−15.2% (−18.9σ)** | 7.25 | 13.8% | −0.718 |

### The setup, stated plainly

> **The opening range is the first 15-minute bar of the New York cash open (09:30–09:45 NY).
> The first later M15 bar that CLOSES outside that range is the entry, in the break's direction.
> The stop is the far side of the range. The target is 1R.**

No gap requirement, no fib, no sweep, no structure. Three inputs: a clock, a high and a low.

### Why it is not one lucky cell

- **Both SIDES are positive, and the SHORT side is stronger** — long +2.2% (+1.4σ), short
  +5.9% (+3.7σ). NAS100 also rose across this window, so drift would favour longs. It does the
  opposite. This is the single most important check here and it passes emphatically.
- **Both HALVES are positive** — 1st +2.5%, 2nd +5.4%. Same sign, growing.
- **Per year: positive in 6 of 9, flat in one.** 2021→2026 reads
  **+0.08 / +0.09 / +0.08 / +0.07 / +0.10 / +0.06** — six consecutive years inside a narrow band.
  The only negative is the partial 2018 stub (107 trades).
- **The MIRROR is catastrophic** — `ORB_FADE` at −15.2% / −18.9σ. A trigger with no information
  scores ~0 both ways; one whose inverse is that bad is carrying real directional signal.
- **The same shape appears on GOLD** (+2.6%, positive 2019 and 2021–2026, identical decay with R
  target). Two instruments agreeing on the effect's existence AND its character is independent
  confirmation. Gold simply cannot pay for it.
- **It does not need more time.** 24h and 4d horizons give +3.4% / +3.5% against 8h's +4.0%. The
  edge is captured intraday, which is what makes it an intraday trigger rather than a swing one.

### The caveats that matter

1. 🔴 **It is a ~1R burst that EXHAUSTS, and that is the opposite of everything else in this repo.**
   Edge by target: **1R +4.0% · 1.5R +3.0% · 2R +0.6% · 3R −3.4%.** Every other strategy here is
   runner-based and SOS Fade Run 9 proved a hard TP caps what pays. **That reasoning does not transfer to
   this trigger** — here the ceiling IS the edge. Do not "improve" it with a runner without
   measuring; the table says a runner destroys it.
2. ⚠ **Confluence does NOT help.** VWAP side, structure trend, yesterday's direction and the kill
   zone all leave the edge flat while cutting n by 10–55%. The narrow-range filter is n=2. **The
   trigger is already the whole signal** — which is good news for "easy", and it means resisting the
   urge to bolt engines onto it.
3. ⚠ **This is a SKELETON, not a strategy.** No ladder, no staged stop, no min-stop guard, no
   position slot, no swap. Read `+0.049R × ~336 trades/yr ≈ +16R/yr` as a prior on the trigger,
   never as a projected return. The `bos_sweep.py` falsification of 2026-08-07 is the standing
   warning: a table of numbers reads as a finding whatever caveat sits under it, and one Strategy
   Tester run overturned it.
4. ⚠ **NAS100 is a new instrument for this repo.** No swap measured, no tick data cached, no
   history-floor seed, no Pine parity, no strategy package. Its swap is `−5.99 long / +1.10 short`
   per the live terminal — an index CFD held overnight is a real cost this study does not charge,
   though an intraday strategy that is flat by the close mostly avoids it.
5. ⚠ **Overlap with SOS Fade is UNMEASURED** and it is a different instrument, which is the strongest
   possible argument that they are uncorrelated — but that is an argument, not a measurement.

---

## Recommendation

**Build the NAS100 opening-range break as the second bot. It is the only intraday thing measured
here that clears its own cost, and it is by a distance the simplest.**

It fits the standing philosophy from a new direction: the portfolio gets its trade count from a
SECOND INSTRUMENT rather than from loosening a filter, which is the one route to frequency Run 12
did not close off. ~336 trades/year against SOS Fade's ~20, on a different market, with no shared engine
state — that is genuine diversification rather than a queue.

Order of work, cheapest falsification first:

1. **Re-measure with a real exit ladder and one position slot.** The 1R ceiling is the whole result
   and a skeleton cannot price it. This is the step that killed `bos_sweep.py`'s numbers.
2. **Charge NAS100's real spread and swap** — measure them with `algos/tools/broker_facts.py`
   rather than taking the $0.80 snapshot here.
3. **A third instrument.** US500 or GER40 costs one cache pull and one command. If the opening-range
   break holds on a third index it is a market-structure fact; if it does not, it is NAS100's.
4. **Then** the strategy package, the Pine port and the parity gate.

**Do not** build any gold intraday strategy from this study. **Do not** build a VWAP mean-reversion
or opening-range fade on either instrument — both are measurably worse than random.

### The standing lesson

The eight triggers were screened on gold first and every one failed, which reads as "there is no
intraday edge". That conclusion would have been wrong, and the thing that was actually being
measured was **the instrument's cost-to-range ratio, not the triggers**. The same signal that nets
−0.008R on gold nets +0.049R on an index, unchanged. **Before concluding a class of strategy does
not work, check whether what you measured was the strategy or the instrument you measured it on.**
