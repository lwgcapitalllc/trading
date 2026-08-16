---
source: https://www.youtube.com/watch?v=po3MlSGt5CY
title: Training The Eyes Ep. 5
uploader: Inter Equity Trading
duration: 11:48
watched: 2026-08-13
detail: cue frames (31 forced timestamps, native captions)
focus: Aaron's continuation model — the cycle stated as a rule, and target selection
---

# Training The Eyes Ep. 5 — GBPJPY, the cycle stated plainly

Naked GBPJPY chart, marked up from scratch, 30m → 15m → 5m. **This is the most valuable of the
four videos so far** because it stops describing one setup and states the *cycle* as a repeating
rule — and because it is the first to explain **how targets are chosen** rather than just naming
one.

Presenter calls it *"debatably my favourite episode yet."* Two entries shown; the second he says
he took.

## 🔴 The cycle — the whole model in three steps

Stated verbatim at [08:07], and this is the sentence to keep:

> *"We need to see a **build-up**. We need to see a **run of that build-up**. We need to see a
> **liquidity block form** for us, basically, and then the whole cycle starts again, over and
> over and over."*

Restated at [08:49]: *"we need to see a pool of liquidity built, and then we stab it and move
away, leaving an LB for us."*

And the pattern named at [04:25]:

> *"I hope you're starting to see the consistent cycle of price **building liquidity, taking it
> out, and then moving in the correct direction**. Price built, induced, trapped, and then moved
> in the intended direction. Same thing over and over and over."*

**Build → sweep → LB → entry → the LB's move creates the next build-up.** It is a loop, not a
one-shot setup. That reframing is new: the other three videos each taught one instance of it.

## 🔴 Targets — the first real explanation

The closing lesson [10:32-11:12], and it is the answer to a question the other videos left open:

> *"Every single target has a reason. There's liquidity lying at these highs. **They're not just
> random highs.**"*

A target is a level where liquidity is **resting** — a high price has bumped into and respected,
or a build-up left behind. He lays three targets on the final trade and takes the last at
**72 pips, 1:7.8**, noting you can partial at each. He also predicts the pause: [10:52] after the
first target is taken price pulls back — *"Coincidence? There was liquidity above this high.
That's why the market gives you a reaction back down."*

⚠ **This joins up with the target rule from Ep. 4** (structural high first, HTF level on
partials). Same idea from the other end: targets are liquidity, and each one is a place a
reaction is expected — which is why you pay yourself there.

## The two measurable strength signals

Both are new, both are quantifiable, and neither is defined numerically:

**1. 🔴 TIME spent above a level = how much liquidity is under it.** [09:30], the sharpest new
idea in any of the four videos:

> *"This is for hours, guys. Hours and hours and hours. … we traded above this low for **5 and a
> half hours**. So just imagine how much liquidity was being built below this low."*

Duration is treated as magnitude. A level price has hovered above for five hours has more resting
under it than one it touched once.

**2. Touch count = strength.** [06:27] *"We respect this high once, twice, three times, and then
fuels the sell-off"* — and again at [05:46] and [09:09]. Same signal as the 23552 high in Ep. 4.

## "Price leaves hints"

[06:47], his framing for building a directional bias before any entry exists:

> *"Price is essentially leaving us a bunch of hints that we're going to be moving bullish
> eventually. We're not just going to buy to buy — that needs to make sense. But look how it's
> leaving hints."*

The hints are untaken liquidity stacking on one side: internal highs respected repeatedly, plus
the higher-timeframe level above. Direction is inferred from **where the unclaimed liquidity
is**, not from trend.

## What he refuses to trade — two explicit no-trade rules

**1. A pullback continuation with no sweep.** [02:02] *"Price takes the high, gets a pullback,
and goes long — I don't typically trade from these kind of areas."* No sweep, no trade, even
though the direction was right.

**2. Buying above an old high.** [05:05]

> *"After price takes out this high, you no longer want to be looking for buys right away cuz
> you're going to be **trading above old highs**."*

He then shows a lower-timeframe buy that *did* work and says he still would not have taken it.
This is the "check what's above you first" rule from the continuation video, restated as a
directional constraint: **the liquidity above has to be gone before you buy toward it.**

## Other things worth keeping

**Every timeframe is used, on purpose.** [02:44] answering his most-asked question:

> *"What timeframe do you use to identify liquidity? **I use every single time frame.**"*

His method is mechanical: when price action is squeezed on the current frame, drop one. He does
30m → 15m → 5m mid-analysis and back up again. Confirms the fractal reading from Ep. 4, and it
is now stated rather than merely demonstrated.

**Levels get recycled.** [07:07] *"Don't forget the entry that we took before, now becomes an
LB."* The low your entry was taken from becomes a liquidity block for a future trade. Levels
persist and change role.

**A breakeven stop-out is an acceptable outcome.** [07:27] *"If you never took any partials, you
might have gotten taken out BE, which is completely fine."* Said without hedging.

## The two trades

**Entry 1** [03:24-04:04], 5m: range builds → price goes long → liquidity left below the lows →
price returns and sweeps them → LB → buy at 199.603. *"We're able to take the buy as soon as the
liquidity's taken."*

**Entry 2** [09:09-11:12], the one he says he took: high taken out (trap) → price respects it
twice, moves up → liquidity left at the low → **price trades above that low for 5½ hours,
building** → stab → buy on the sweep, imbalance and LB supporting → **stop below the low** →
three targets, last at 72 pips / **1:7.8**.

## What is worth acting on

**The cycle is now stateable as a loop**, which is what an engine needs:

```
build-up of liquidity  →  sweep of it  →  LB left behind  →  entry off the LB
        ↑                                                            │
        └──────────  the move creates the next build-up  ←───────────┘
```

**Newly measurable, and all of it undefined numerically — this is our work, not his:**

- ⚠ **Time above/below a level as liquidity magnitude.** 5½ hours is quoted as impressive; no
  threshold given. This is the most encodable idea in the four videos and the easiest to measure.
  Bars-spent-above-a-level is trivial to compute off `engines/market_structure/`.
- ⚠ **Touch count as strength** — third video in a row to use it, still no number.
- ⚠ **"Build-up" has no definition.** He points at ranges. Needs a real one: a range of what
  width, over how many bars, with how many touches.
- ⚠ **Target selection is now specified in kind but not in rank** — targets are resting-liquidity
  levels, there are several, and partials go at each. Which one is TP1 versus the runner is
  chosen by eye ("that's not big enough for myself").

**Two clean no-trade rules to encode**, both of which reject setups that would otherwise pass a
naive continuation filter: no sweep → no trade, and never buy toward liquidity that is still
sitting above you.

⚠ **Still no numbers.** Four videos, zero win rates, zero sample sizes. Two worked examples here,
one of them claimed as taken live. Same standing position: the model is well specified, the edge
is entirely unmeasured, and every figure will be ours.
