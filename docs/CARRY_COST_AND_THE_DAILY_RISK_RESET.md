# Carry cost, and the daily risk reset

**Status: AN IDEA TO EXPLORE. Nothing here is built, and nothing here is decided.**
Raised by Aaron 2026-08-21 off a measurement made while chasing something else.
The measurements are real and are named with the command that produced them. The
*proposal* is a sketch, and Aaron's own words on it were "maybe this is a good idea,
maybe not — maybe we just let it run as high as possible. I don't know."

---

## The thing that started it

A capped run reported peak open risk of **10.9140%** against a **10%** ceiling, which
looked like the limit leaking. It is not. Chased to the exact booking:

```
python3 backtest/tools/recovery_stack.py --start 2018-09-14 --end 2026-08-14 \
        --profile puprime_ecn --on-contention share
```

The worst moment, traced booking by booking to the line that made each one:

| | |
|---|---|
| balance when the trade was granted | $154,696.17 |
| risk granted | $15,469.62 — **exactly 10%** |
| entry commission | −$52.71 |
| entry half-spread | −$316.24 |
| **overnight financing, one rollover** | **−$12,586.52** |
| balance at the breach | $141,740.69 |
| the same untouched risk, restated | **10.9140%** |

The position was **5,270.74 oz (52.7 lots)** with a stop **$2.94** away, and its size
and stop never moved. Nothing was risked above the cap. **The account financing the
trade got smaller underneath it.**

⚠ **Verified as not-a-stacking-problem, because that was the obvious wrong answer.**
A+ run ALONE, with no second leg in the run at all, reproduces the identical
**2,984** over-cap ticks and the identical **10.9140%** peak. The live bot has always
done this on its own.

---

## The asymmetry worth keeping even if nothing is ever built

**The risk cap limits RISK. Financing is charged on SIZE.** Those are different
quantities and they move independently:

* risk = size × distance to stop
* financing = size × price × a rate × nights held

So for the same 10% of the account, **a tighter stop buys a bigger position, and a
bigger position costs more to carry.** The trade that looks cheapest by the risk
number is the most expensive to hold. Nothing in the risk figure shows you this, and
nothing in the run's reporting surfaces it today.

Second-order, and it is the bit that makes it compound: every night of carry lowers
the balance, so the *same* open dollars become a larger share of the account. If the
trade then stops out, it takes **10.9%** of what is left rather than the 10% it was
worth when it was taken.

⚠ **Held time is therefore a cost input, and this repo has never priced it as one.**
The loss-recovery rule holds a median **4.3 days** and up to **29.3** — that is a lot
of nights, and its measured contribution is small enough that carry could plausibly be
a material share of it. NOT MEASURED. Do not quote that as a finding; it is the
question, not the answer.

---

## Aaron's proposal, in his framing

Assess it **daily, at the rollover**, rather than once at entry:

> "If I'm winning, I need to close some of the trade off to account for the rollovers.
> If I'm losing, don't do anything until I start to win. The only scenario where I know
> I will lose is if it goes against me for a couple of days and then hits stop loss.
> I'm okay with that loss. But if I can help it, every day that we roll over, we should
> pull some off the table to account for the risk of carrying the trade."

The shape of it: each rollover, take enough off a **winning** position to cover what
carrying it has cost, so the risk-to-account ratio is reset to the intended 10% rather
than drifting up. A **losing** position is left alone — trimming it would realise a
loss to pay a cost, which is the wrong direction.

---

## What has to be answered before anybody builds it

**1. Is trimming a live position allowed here at all?** The repo's standing rule is
that a resized order is not the trade the strategy is holding — refusing is the answer,
never shrinking to fit. That rule is about ENTRY sizing, and this proposal is about
MANAGING an open trade, which is a different act. But the two are close enough that the
distinction has to be made deliberately and written down, not assumed.

**2. It changes trade outcomes, so it needs its own measurement.** Trimming a winner
caps its upside. This strategy's return is carried by a small number of very large
winners — one trade alone was worth +22.7R. Shaving a runner every night to pay its
financing could easily cost more than the financing does. **That is the whole question
and it is unmeasured.** The honest test is a full replay with the rule on and off,
compared in R.

**3. "If I'm winning" needs a definition.** Winning by price? Past breakeven? Past 1R?
A trade can be up at one rollover and down at the next, so a naive test would trim on
the way up and hold through the way down — buying the worst of both.

**4. Does it interact with the stop ladder already there?** The trade already moves to
breakeven and takes partials at rungs. A nightly trim is a second thing reducing size,
and two independent size-reducers on one position is exactly where quiet
double-counting lives.

**5. What is the actual financing rate, per side?** Everything above traces ONE booking
on ONE trade. The rate is in the cost tier and a short position can be *credited*
rather than charged. **The total carry bill across a run has never been measured.**
Until it is, nobody knows whether this is worth any code at all — it may be a rounding
error outside the handful of very large positions.

**6. Would it even reach the live bot?** Live sizing already refuses orders above the
broker's maximum and refuses on margin. A nightly resize is a new order path with its
own failure modes on an armed account, and it is a change to `algos/live/`.

---

## The honest counter-argument

Let it run. The strategy's edge is in letting winners extend, financing is a cost of
doing that, and a rule that nibbles at every winner to save a cost may be optimising the
smaller number at the expense of the larger one. **The 10.9% is not a breach and does not
need fixing** — nothing is ever put at risk above the cap, and the drift is arithmetic
on a shrinking denominator, not a leak.

⚠ **Aaron's own separate point, recorded so it is not lost:** he would not run 10% risk
on a seven-figure account anyway, and does not want that written as a rule. So the
scenario where carry costs bite hardest — enormous positions on a large balance — is one
he would not be trading into in the first place.

---

## First step, whenever this is picked up

Measure before designing. Total financing paid across a full run, split by leg and by
direction, against total R. If carry is a small share, this document is the answer and
nothing gets built. If it is a large share, the trim rule earns a real replay.

⚠ Compare R, never net dollars — both sides of any such comparison share one balance.
