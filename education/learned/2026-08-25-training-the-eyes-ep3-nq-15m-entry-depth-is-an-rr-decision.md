---
source: https://youtu.be/tTAu-2703uo
title: Training The Eyes Ep. 3
uploader: Inter Equity Trading
duration: 06:25
watched: 2026-08-25
detail: transcript
focus: fill the gap — Eps. 1–3 were never watched
---

# Training The Eyes Ep. 3 — NQ 15m, and how deep the entry goes is an RR decision

Third in the series, on NASDAQ. The shortest of the three and the most consequential, because it
contains the one rule that **contradicts the student handout as currently written**.

## What it covers

**[00:45–01:23] The target is chosen first, from the left.** A high that has been respected
repeatedly is marked as *"a future target, a future buy target"* — *"but in order for us to buy this
thing back up, we're going to need to see lows taken on the other side."* Target before entry, and
the entry only exists to reach it.

**[02:19–02:38] "Intact" defined.** Equal highs left untouched through Asia and London, then price
goes short off the New York open leaving them intact. Intact = never traded through = still owed.

**[03:18–04:33] 🔴 HOW DEEP THE ENTRY GOES IS DECIDED BY RISK-TO-REWARD, NOT BY A FIXED RULE.**

> *"Price can actually go long **anywhere below the blue line**, anywhere below the liquidity. **It
> does not have to come all the way to the extreme. However, in order for the RR to make sense,
> sometimes I want price to come a little bit deeper.**"*

He then shows the arithmetic on his own chart: taking the shallow fill gives *"about 1 to 2"*, and
*"per my system, I don't like to take those kind of trades. So I wanted price to come as deep as
possible."* Setting the limit deeper gets him **1 risking to gain about 4**.

⚠ **This is not in tension with Ep. 1's "don't wait for the extreme" — it is the other half of the
same rule.** Entry is valid anywhere past the level. **Where you actually place the limit inside
that zone is chosen so the reward-to-risk clears your threshold.** Ep. 1 warns against demanding the
extreme *for its own sake*; Ep. 3 says go deeper *when the numbers need it*.

🔴 **The handout `docs/teaching/MPC_Loaded_Level_Strategy.pdf` currently teaches only half of this**
— *"Entry: the instant my level from step 2 is stabbed. No waiting, no better price."* That is Ep.
1's half stated as an absolute. See the handout evaluation.

**[04:16–04:33] The gate, restated.** *"We're not just buying because liquidity is taken. No — we're
buying because liquidity is taken **and** we have highs intact, we have liquidity to target."* No
target, no trade.

**[04:51–05:12] Why the extreme low will not be run.** *"There is no reasoning to run past that low.
Why? We have swept liquidity out, printed this low and moved bullish to the upside. So we don't have
a reasoning to sweep this low yet."* The same no-liquidity object as Eps. 1 and 2.

**[05:12–05:54] Managing through a pullback.** Price reaches the first high, respects it, pulls
back. *"We haven't taken the high from the left yet. We haven't taken all that liquidity yet. So if
we get any pullbacks, it should be short-lived and overall just a continuation."* **An un-taken
target is the reason to hold through a retrace.**

## Worth acting on

1. **Fix the handout's entry rule.** It states "no waiting, no better price" as absolute. The
   complete rule has a second clause about RR deciding depth, and the handout separately demands
   3× reward — so as written the two pages can contradict each other on the same trade.
2. **The scanner has no entry-depth parameter.** `backtest/tools/loaded_level_scan.py` fills at the
   level. If depth is chosen to clear an RR floor, then the measured RR distribution is not the one
   he trades — and the 2R sensitivity finding in `docs/DAVINCI_MODEL_SPEC.md` may be measuring the
   wrong thing.
