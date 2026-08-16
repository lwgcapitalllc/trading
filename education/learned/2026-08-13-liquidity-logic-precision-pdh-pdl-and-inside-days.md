---
source: https://www.youtube.com/watch?v=HEBP5I3z__c
title: The Liquidity Logic You NEED To Know (PRECISION)
uploader: Inter Equity Trading
duration: 14:12
watched: 2026-08-13
detail: transcript only (native captions)
focus: previous-day levels, the inside-day no-trade filter, the candle-close entry pattern
---

# "The Liquidity Logic You NEED To Know" — PDH/PDL and the inside-day filter

NQ, daily → 30m → 15m. **The most encodable of the whole set** — it turns the model's timing from
"sessions matter" into two specific, mechanical rules.

## 🔴 INSIDE DAY = NO-TRADE DAY

[02:34], a regime filter that appears nowhere else in the set:

> *"Now we have Tuesday's high intact and Tuesday's low intact. **Typically this following day,
> aka Wednesday, is going to be no trading for me**, because I anticipate price to have more of an
> **inside day** — meaning we're going to trade below previous daily high and above previous daily
> low. And typically in those conditions, not my favourite to trade, cuz it's just going to be
> small in-and-out scalpy kind of trades. … **I'm usually on the brakes.** … Understand it is
> going to be an inside day, **maybe I cut the risk a bit.**"*

He then plays it forward and Wednesday *does* print an inside day: *"Kind of squeezy,
inconsistent, not a lot to trade. **Anticipating this kind of price action before it actually
happens will help you tremendously.**"*

Fully mechanical: **after a day that sweeps both PDH and PDL, expect an inside day and stand
down** (or cut size). Testable directly — no interpretation needed.

## 🔴 The candle-close sweep — the same pattern on two frames at once

[09:42], and this generalises Ep. 9's hourly-close observation into a rule:

> *"We allowed **Wednesday to close** up. **Thursday now opened, spiked PDL.** … **Same thing's
> now happening on the 30-minute chart. 30-minute closed up. We've left the previous 30-minute
> unran. The next candle comes in and boom, we spike out the previous 30-minute low. Boom, that is
> your entry right there.**"*

**The pattern: a candle closes leaving the previous candle's extreme unswept → the next candle
sweeps it → that is the entry.** It fired on the daily and the 30-minute simultaneously, which is
the fractal claim reduced to something a scanner can compute off nothing but OHLC and a
timeframe.

**R on that trade: 1:9**, *"capturing the whole daily range, from PDL to PDH."*

## 🔴 Previous-day levels and day-of-week levels are first-class

Throughout: **PDH**, **PDL**, *"Monday's high"*, *"Friday's low"*, *"Tuesday's high and low"*,
*"Wednesday's high, Wednesday's low"*. Used both as pools to sweep and as targets:

> [07:11] *"Since Wednesday has closed up, we have a **PDL that we have yet to run**. I don't
> believe Tuesday's low needs to get ran — why? We just ran that level of liquidity. **This low
> can act as a liquidity block.** So what I'm anticipating just off the daily chart alone is
> **Thursday to open up, we spike down below Wednesday's low, we hold Tuesday's, we use it as an
> LB, and eventually we can trade higher.**"*

That is a complete, falsifiable next-day forecast built from three daily levels. ⚠ **We already
have `engines/liquidity/` emitting previous day/week levels** — this is the consumer for it.

## The "red flag" — a move that induces without clearing

[06:10], a useful negative signal:

> *"We have a move to the upside, **but what don't we do? We leave the high to the left-hand side
> intact.** This high still remains below this high over here. **So we did not grab any
> liquidity.** All we've done from low to high — the volume injected into the market like this —
> **this will induce buyers.**"*

A rally that fails to take the level to its left has generated liquidity without consuming any.
That is the setup for the reversal, and he flags it live with an eye emoji: *"This is red flaggy
to me."*

## Timing confluences named

- **Asia open, 8:00 p.m.** — plotted explicitly as *"a time confluence"*, and the entry landed
  there: *"there's your entry in Asia session… great timing confluence right at Asia open. So
  everything lines up perfectly."*
- **10:00 a.m. New York** — used again in the next video as *"a very key time we always use,
  especially on the indexes."*
- Market open, stock open.

## Duration again

[06:41] *"we come down here and **hold the low for about 3 hours** — so a lot of buyers are trying
to step in above this low."* Seventh instance of duration-as-magnitude.

## What is worth acting on

- 🔴 **Inside-day no-trade filter.** Mechanical, testable, and it is a *regime* rule — the only one
  in the whole set. Sits naturally beside `engines/regime/`.
- 🔴 **The candle-close sweep entry**: previous candle's extreme left unswept → next candle sweeps
  it → entry. Computable on any timeframe from OHLC alone, and it fires on several frames at once.
- 🔴 **PDH / PDL / day-of-week levels as pools and targets.** `engines/liquidity/` already emits
  these and nothing currently consumes them for a strategy.
- ⚠ **"Induced without clearing" is a detectable negative** — a leg that makes a new local high but
  fails to exceed the prior swing high to its left.
