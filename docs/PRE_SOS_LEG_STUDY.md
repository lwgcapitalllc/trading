# The leg BEFORE the shift of structure — is it tradeable?

**Tool:** `backtest/tools/pre_sos_leg.py`
**Run:** 2026-08-24, Vantage XAUUSD, 187,386 M15 bars + 562,071 M5 bars, 2018-09-13 → 2026-08-23
**Question:** the live A+ bot waits for the shift of structure and fades the retracement. Is the
move that CREATES the shift — extreme up to the swing that breaks — worth taking on its own?

```
python3 backtest/tools/pre_sos_leg.py                   # the headline run
python3 backtest/tools/pre_sos_leg.py --confirm M15     # confirm on the base frame
python3 backtest/tools/pre_sos_leg.py --confirm M1      # confirm on a faster one
```

---

## Why it was asked

Aaron, 2026-08-24: *"What if we traded from the extreme to the shift of structure as a trade?
The stop loss will be the structure point under the extreme, and the target will be right at the
shift of structure. Kind of want to just get in, get out. How can we measure the extreme?"*

The measurement question is the whole problem. **The extreme is only knowable afterwards.** By
the time the structure engine can name the low an impulse launched from, the impulse has already
happened. So the study is not about the leg — it is about finding a REAL-TIME proxy for the
extreme, and then scoring that proxy against a control that does not know anything.

---

## 1. The leg itself is worth chasing

Measured over 811 external changes of character on the PU Prime M15 cache, 2019-01 → 2026-08:

| | median |
|---|---|
| distance, extreme → the level that breaks | **$20.55** |
| the same in ATR(50) of an M15 bar | **7.7×** |
| bars from the extreme to the break | **36** (≈9 hours) |
| how often | **811 in 7.6 years — ~106 a year**, split evenly between the two sides |

So the prize is real and it is frequent. Everything below is about whether you can get on it.

---

## 2. Three proxies for the extreme. Two of them are dead.

**The plain sweep-and-reclaim, aimed at the swing.** Every time a liquidity level is wicked
through and the bar closes back, enter and target the live opposing swing.

```
n=9,974   hit 10.0%   medR 12.17   exp -0.035R   |   control 10.1%   edge -0.1% (-0.3s)
```

Dead flat. It also exposes why: with a wick-width stop the target sits a median **12 stops**
away, which is a lottery ticket, not a trade.

**The smaller-degree shift on the base frame.** Wait for the internal structure to change
character on the same M15 chart.

```
n=572   hit 50.9%   medR 0.87   exp -0.082R   |   control 53.2%   edge -2.3% (-1.1s)
```

🔴 **The number that kills it is `medR 0.87`, not the edge.** By the time the M15 confirms the
turn, the target is CLOSER than the stop. Price has already travelled most of the leg. There is
no trade left to take — the setup arrives having spent its own reward.

**The change of character on a FASTER frame, after a base-frame level was swept.** This is the
one that survives, and it is section 3.

---

## 3. The setup that scored

The rule, in full:

1. A liquidity level on the 15-minute chart gets swept — a session high/low, the previous day's,
   the previous week's, or a 4-hour level.
2. Within 3 hours, the **5-minute** chart puts in its own change of character in the opposite
   direction.
3. The 15-minute trend still points the other way, so the swing being aimed at is a genuine
   change of character rather than a continuation.
4. That swing is at least **2 stops** away, the stop sitting under the 5-minute extreme of the
   last 2 hours.

Entry at the 5-minute close, half the measured Vantage spread charged. Target is the swing.

```
                                     n     hit    medR      exp    stop  |  ctrl    edge
all 5m changes of character        1496   38.0%   1.77   -0.065R  $7.97  | 39.3%   -1.3% (-1.0s)
+ counter-trend, R>=2               486   22.8%   3.64   +0.040R  $6.99  | 21.1%   +1.7% (+0.9s)
+ a level was swept  <- THE SETUP   228   28.1%   3.67   +0.296R  $7.24  | 21.6%   +6.4% (+2.2s)
+ two level families agreeing       112   30.4%   3.77   +0.386R  $7.17  | 19.9%  +10.4% (+2.4s)
```

**≈25 trades a year at +0.30R each.** The two-family row is ≈12 a year at +0.39R.

### Faster is not better — the 1-minute confirmation

Aaron's follow-up: *"I'm curious if the one minute might be better for the structure
confirmation. We might get it much quicker."* It does get in quicker and cheaper — and it is the
worse trade.

```
                      n      hit    medR      exp    stop   |  ctrl     edge
M15 (same frame)     572   50.9%   0.87   -0.082R  $8.90   | 53.2%   -2.3% (-1.1s)
M5   THE SETUP       228   28.1%   3.67   +0.296R  $7.24   | 21.6%   +6.4% (+2.2s)
M1   THE SETUP      2771   18.4%   5.09   +0.032R  $4.35   | 16.0%   +2.4% (+3.2s)
```

The 1-minute entry is exactly what he expected it to be: the stop is **$4.35 against $7.24**, so
the same swing is **5.1 stops away instead of 3.7**. The problem is that the hit rate falls
faster than the payoff rises — 18.4% against 28.1% — and expectancy drops by a factor of nine.

🔴 **AND THE 1-MINUTE ROW HAS THE HIGHER SIGMA (+3.2σ vs +2.2σ), WHICH IS THE TRAP.** More
confidence in a smaller number is still a smaller number: σ scales with √n and the 1-minute
trigger fires **12× as often**. Ranking rows by significance would pick the 1-minute here and be
wrong. **Read the expectancy; the sigma only says whether it is real.**

⚠ **Per YEAR the two look close and that is the thing that nearly hid it** — ~25 trades at
+0.296R is ≈+7.5R a year, while ~308 trades at +0.032R is ≈+9.9R. What separates them is COST.
Passing `--spread 0.44` charges the whole round trip at entry instead of half of it, and the two
frames respond completely differently because their stops differ by 1.7×:

```
M5   THE SETUP, full round trip charged     222   28.8%   +0.307R   | edge +12.2% (+4.0s)
M1   THE SETUP, full round trip charged    2735   18.3%   +0.002R   | edge  +2.3% (+3.1s)
```

🔴 **The half-spread the first table did not charge WAS the 1-minute's entire edge.** It goes
+0.032R -> **+0.002R**, i.e. nothing, while the 5-minute is unmoved at +0.307R. A full round trip
is ~1.5% of a $7.24 stop and ~5% of a $4.46 one. ⚠ **A trigger whose edge per trade is thinner
than the round trip is not a cheaper version of the same idea, it is a different and worse one.**
The stop got tighter; the cost did not.

⚠ **Its edge over the control SURVIVES at +2.3% / +3.1σ, and that is the sharpest lesson in this
file.** The 1-minute trigger is really detecting something — it beats a matched random entry, and
it does so more certainly than the 5-minute one. It is still not worth trading, because the thing
it detects is smaller than the cost of acting on it. **"Better than random" and "worth trading"
are different questions, and only the second one has a broker in it.**

Also worth noting: on 5-minute, stacking level families improves the row monotonically. On
1-minute it does nothing (2 families +0.6%, 3 families −1.9%). **A filter that works on one frame
and not on the other is a sign the two triggers are not detecting the same event.**

---

## 4. 🔴 The sweep is the ingredient, and it is not close

Hold the trigger and the trend filter fixed; vary only whether a level had been swept.

```
no level swept at all      258   18.2%   -0.186R   | ctrl 22.0%   -3.7% (-1.6s)
h4 level swept             199   25.6%   +0.225R   | ctrl 19.9%   +5.7% (+1.8s)
session level swept        127   32.3%   +0.449R   | ctrl 17.8%  +14.4% (+3.5s)
daily level swept           64   32.8%   +0.489R   | ctrl 16.1%  +16.7% (+2.8s)
weekly level swept           8   (too few)
```

**The same trigger with no level under it LOSES money.** Session and daily are the strong
families; the 4-hour level — the cheapest, most frequently taken level on the chart — is the
weak one that still works. Previous-week is too rare to say anything about, and saying so is the
answer rather than a gap.

Stacking families helps, monotonically:

```
0 families   258   18.2%   -0.186R   | edge  -0.1%
1 family     116   25.9%   +0.210R   | edge  +5.2%
2 families    58   31.0%   +0.368R   | edge +10.9%
3 families    50   30.0%   +0.417R   | edge +15.3%
```

⚠ **This contradicts `docs/SWEEP_LEVEL_STUDY.md` §4, which found confluence made things WORSE**,
and the contradiction is not a mistake in either. That study scored a fixed +2R target off a
wick-width stop on the base frame. This one scores a structural target off a faster-frame
confirmation. **Confluence is not a property of the levels alone — it only pays once there is
something to confirm the turn.** If either result is re-quoted, quote which target it was
measured against.

---

## 5. The exit — banking early buys nothing, and the stop should stay put

Exit at a fraction of the way to the swing instead of at it, same entry, same stop:

```
frac    reached    R booked    expectancy
0.50     45.2%      1.83R       +0.349R
0.70     36.4%      2.57R       +0.324R
0.90     30.7%      3.30R       +0.323R
1.00     28.5%      3.67R       +0.310R
```

**Flat from halfway to the full level.** There is no free improvement in taking less; the fewer
R you book is paid for exactly by the extra hits. Run it to the swing.

Aaron's instinct about the stop is confirmed by the failure shape:

```
reached 30%: n=119   finishes 54.6%   falls back to the stop 35.3%
reached 50%: n=103   finishes 63.1%   falls back to the stop 26.2%
reached 80%: n= 74   finishes 87.8%   falls back to the stop  6.8%
reached 90%: n= 70   finishes 92.9%   falls back to the stop  5.7%
```

Most losers die early and never get near a breakeven trigger, and once price is 80% of the way
the trade finishes ~88% of the time.

### What an early move to breakeven costs — measured

Aaron's rule was *"we don't really move this stop unless we are within a percentage of the
target."* The tool now re-walks every qualifying trade with the stop moving to the entry price
once price has travelled a given fraction of the way. A scratch is booked at
**−(half spread)/risk**, not at zero: the entry already carries half the spread and exiting at the
entry price hands the other half back.

```
arm at     win    scratch   loss    expectancy   vs never
never     28.1%     0.0%   71.9%     +0.296R
30%       16.2%    32.9%   50.9%     +0.080R      -0.217R
40%       19.7%    25.4%   54.8%     +0.183R      -0.113R
50%       23.2%    18.4%   58.3%     +0.273R      -0.023R
70%       27.2%     6.6%   66.2%     +0.320R      +0.024R
80%       27.6%     2.2%   70.2%     +0.300R      +0.004R
90%       27.6%     1.8%   70.6%     +0.296R      -0.001R
```

🔴 **Arming at 30% of the way costs −0.217R a trade — it converts a fifth of the book's winners
into scratches.** The win rate falls 28.1% → 16.2% while losses only fall 71.9% → 50.9%. The
trades a breakeven stop "saves" are overwhelmingly ones that were going to win anyway, because
this setup's retracements happen INSIDE the leg, not before it.

✅ **The best arm point is ~70%, and it is worth +0.024R — a rounding error.** By 90% there is
nothing left to protect. **So the honest answer to the rule is: the instinct not to touch the
stop early is worth a lot, and the breakeven move itself is worth almost nothing.** Leaving the
stop alone entirely is within noise of the best setting, and it is one less thing to get wrong
live.

⚠ **The arm is decided on a BAR CLOSE, never intrabar.** A bar that reaches the arm level and
retraces to the entry inside the same bar does not scratch here — nothing in a bar says which
extreme came first, and arming intrabar lets the model exit at a price it could not have known to
place. That choice flatters the breakeven rows slightly, and they still lose.

---

## 6. Read this before quoting any of it

⚠ **228 trades in 9 years, and three losing years inside them** — 2021 −5.5R, 2023 −1.5R,
2024 −7.3R, against 2019 +17.3R, 2025 +27.3R and 2026 +23.7R in 14 trades. The result is lumpy
and concentrated in the recent window.

⚠ **This is a STUDY, not a backtest.** No position slot, no queueing, no re-entry cap, no news
filter, no TP ladder, no sizing. A bar holding both stop and target books the stop; a trade that
resolves neither way inside 100 hours books a full loss. Both are applied to the control too, so
the EDGE survives them while the absolute expectancy is the pessimistic end.

⚠ **Costs are half a spread on entry, at the measured Vantage figure ($0.22).** No commission,
no swap. On PU Prime ECN the spread is $0.12 but commission is $1.00/side/lot, which this does
not charge — so **the live account's costs are NOT modelled here** and the expectancy is an
upper bound for it.

⚠ **The setup was found by testing roughly twenty combinations and reporting the one that
scored.** It survived a 2018-2022 / 2023-2026 split, a sweep of its own thresholds, and a change
of broker feed (found on PU Prime, reproduced on Vantage) — which is more than noise usually
survives. It is still not out-of-sample, and nothing here has been forward-tested.

⚠ **The tool reads one private field of the structure engine** — the swing that is live right
now, which the public event stream does not expose because events fire on change, not on state.
It is guarded: a rename raises on the first bar rather than quietly scoring nothing.

---

## 7. What this would be, if it were built

It is a different LEG of the same move the A+ bot already trades, which is exactly the carve-up
`CLAUDE.md` → *Trading Philosophy* describes: A+ takes the reversal, this would take the run into
it. **Their per-year records point in opposite directions in 2023 and 2024** — the live strategy
made +8.4R and +2.2R in the two years this study lost — which is a hint of low correlation and
nothing more at these sample sizes. ⚠ It is one instrument off one structure stream, so it is
NOT independent, and it would need `backtest/tools/overlap_audit.py` run against it before any
stacking claim, exactly as B-LEG did.
