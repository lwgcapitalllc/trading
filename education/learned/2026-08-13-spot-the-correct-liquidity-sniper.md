---
source: https://www.youtube.com/watch?v=lWTb3oiugDo
title: How To Spot The CORRECT Liquidity (SNIPER)
uploader: Inter Equity Trading
duration: 16:19
watched: 2026-08-13
detail: transcript only (native captions)
focus: the counterfactual that defines a valid level, and why he sits out
---

# "How To Spot The CORRECT Liquidity" — the counterfactual, and sitting out

NQ, H4 → M1, replay of a Thursday he livestreamed. The title is the content: **which highs and
lows actually count.**

## 🔴 The counterfactual that defines a level — the sharpest statement in the set

[04:34]. Everywhere else he says *"a high respecting a high to the left"*. Here he states the
**negative case**, which is what makes it a rule rather than a description:

> *"This high has respected this high and moved away to the downside. Simple, all we've got to do
> is plot a line on it. **Now, if this high never touched into this high, and we just had a
> sell-off to the downside — price went like this, sold off, and we didn't have this actual price
> action in front of us — then you wouldn't be plotting a line on this high.** However, in this
> example we did get price back up to the upside, respects the high to the left, and we sell off.
> So we have liquidity, and **price has literally just communicated that towards us.**"*

**A swing extreme with no return-and-respect is not liquidity.** An untouched high is just a high.
This is the single filter that separates his method from "there's liquidity above every high",
which he names as the novice error:

> [17:44 CF ep.] *"There's a lot of people out there like to say there's liquidity above every
> high and low. Right then and there the novice trader is going to think **there's highs and lows
> all over my chart, what do I do?**"*

⚠ **This is the rule that makes the model computable.** Without it the level set is every pivot;
with it, it is a small subset. It should be the first thing built and the first thing measured —
if "respected" describes most swing levels, it is not a filter and everything downstream is noise.
(That is already step 4 of the spec's build order.)

## 🔴 Top-down is mandatory, and it is a gate

[01:00]:

> *"I really want you guys to get used to starting off on the higher. **If you don't see anything
> on the higher, anything relevant, then you shouldn't be going to the lower timeframe.**"*

Not a preference — a precondition. No HTF context, no LTF search.

## 🔴 Liquidity that never gets used is still liquidity

[09:09], and it matters for how we score a detector:

> *"A lot of people in live time get confused by this. They're like, 'maybe I did something wrong,
> maybe this actually isn't liquidity.' **But no. You did something correct, and yes, this is for
> sure liquidity. It just did not get used in this current day.**"*

⚠ **A level that is never swept is not a false positive.** Any evaluation of a level detector that
scores unswept levels as errors is measuring the wrong thing.

## 🔴 Why he sat out — a documented skip with a reason

[09:40], and the spec's open question 6 asks for exactly this kind of example:

> *"I didn't really love the extreme entries here… **I was happy to look for confirmations, which
> we didn't really get.** … The 4-hour told me the story. We had a big 4-hour close. The next
> candle came in — **all we did was wick and go long again. And we left these lows intact.** As
> you guys know, **I like to trade below lows**. And the 4-hour was a bit of a red flag to me. I
> just didn't really love the nature of this price action: how this 4-hour candle closed very
> bullish, the next one opened up, spiked down, and **we respected the low here instead of running
> it. I personally just like to sit out in these situations.**"*

**The skip condition: the HTF candle respected the low instead of running it.** That is the
inverse of the candle-close sweep entry from the PRECISION video — same observation, opposite
outcome, and it is a reason to stand down rather than to reverse.

## Other things

- **"Trend line liquidity"** named as a type — a diagonal run of respected extremes, marked with a
  trend line rather than a horizontal. He says draw it however you like; the object is the same.
- **LB drawn to cover the bottom of the low**, dragged forward as a box — the mechanical
  construction of the stop zone.
- **10:00 a.m. NY** called *"a very key time we always use, especially on the indexes."* The
  sell-off landed at exactly 10:00.
- **Fractal, again**, on the M1: *"this is simply just that high taken, low respected… it's all
  fractal all the way down to the 5-second if you want. Unnecessary, but you know what I'm getting
  at."*
- **Buildup**: *"high taken, low respecting low, high taken, low respecting low — all of this is a
  buildup."*

## What is worth acting on

- 🔴 **The counterfactual is the core filter and should be built and measured first.** A level
  counts only if price returned to it, respected it, and moved away. Everything else is a pivot.
- 🔴 **An unswept level is not a detector error.** Score accordingly.
- 🔴 **A documented skip with a stated reason** — HTF candle respected rather than ran the low.
  Partially answers spec open question 6, which the spec calls the most valuable and hardest
  screenshot to get.
- ⚠ **Top-down is a gate, not a habit.**
