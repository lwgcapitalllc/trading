---
source: https://www.youtube.com/watch?v=MU2ILU-z-0A
title: Training The Eyes Ep. 8
uploader: Inter Equity Trading
duration: 11:43
watched: 2026-08-13
detail: transcript only (native captions; frames skipped — see Ep. 7 note)
focus: Aaron's continuation model — the trading time window, and left-side liquidity
---

# Training The Eyes Ep. 8 — Gold 15m/5m, the time window

Gold, M15 with drops to M5. Several entries walked through. He calls one stretch *"textbook
stuff, I'm not going to lie to you."*

## 🔴 A TRADING TIME WINDOW — he skips valid setups outside it

New, and it is a hard filter he applies twice in one video, [05:07] and [10:38]:

> *"Maybe a possible sell entry up here. **It is out of my time window though, so I was not
> taking this.**"*
>
> *"**This was actually in my time window. This would be an entry I would take.**"*

⚠ **The window is never defined.** He does not say what the hours are, only that setups outside
it are skipped regardless of quality. Combined with Ep. 4 (London open / NY open / 09:30) and
Ep. 10 (New York open) it is clear a session filter exists, but its actual boundaries have not
been stated in any of the nine videos. **This is a question to put to Aaron directly** — it is
the single largest unknown in the model and it decides how many setups ever qualify.

## 🔴 Left-side internal liquidity must be taken first

[04:16-05:07], and he flags it as the mistake to avoid:

> *"**A lot of the uninformed traders would be looking to take a sell right here. But that's not
> correct. Why?** Remember that internal liquidity we marked on to the left-hand side. Look at
> these highs… we end up hunting for that internal liquidity point. **So don't make the mistake
> of looking for shorts up here when we still have liquidity to the left-hand side.**"*
>
> *"Don't just force that short. **Don't be a pattern trader.** Just because we took out this
> high does not mean we need to be looking for sells right away. **You need to make sure that
> that internal liquidity is taken as well.**"*

This extends the "check what's above you" rule into a second dimension. It is not enough that the
liquidity directly above is gone — **unclaimed internal liquidity to the LEFT also has to be
run** before the entry is valid. Price goes and gets it first.

> [05:07] *"The market purposely engineered it in the past for us to now run it in the future."*

## A reaction at a level is not the move — it can just be building

[08:55], the counter-intuitive one:

> *"The market simply reacts off liquidity. **It builds even more liquidity. This is all done on
> purpose.** This is where you might get psyched out. You have to trust yourself. You have to
> understand that **the market will react off liquidity sometimes just to build it.**"*

Same shape at [07:13]: *"This is a sell-off that takes out a low to induce sellers. **We do not
sell from here. We allow the market to react though, to build liquidity for us.**"*

So an initial reaction at your level is not the signal and not an invalidation. It is fuel. ⚠ This
is what makes a naive "reacted at the level → enter" detector wrong for this model.

## Targets — buyer liquidity first, then higher timeframe

[10:38], the most explicit target statement yet in the series:

> *"**Target one would be here. Why? Buyer liquidity.** We take out highs, buyers are induced at
> the low. This would be a valid area to target. And then of course our **higher timeframe
> targets to the left-hand side.**"*

Consistent with Ep. 4 (structural high first, HTF on partials) and Ep. 5 (every target is a
liquidity pool). Three videos now agree on the ladder.

## Stop — "cover the whole high to be safe"

[10:38]: *"Wait for the liquidity to get taken, aka the high gets ran. Stop loss — **you can just
cover the whole high to be safe.** No worries."*

The stop is the LB's full extent, not a tick beyond the wick. Slightly looser than a
minimum-buffer reading of the earlier videos.

## Other confirmations

- Asia session equal highs used as a pool [08:30].
- Market-open **gap** acknowledged as making a chart *"look ugly"*, and he redraws the sequence as
  a clean diagram to teach it — worth remembering when we replay across session boundaries.
- Retail BOS as generator, again [05:32]: *"This is a BOS for retail and people are going to be
  buying at these lows. Once we trade below them, buyers are trapped and we're also inducing
  sellers by that."*
- Touch counting throughout: *"once, twice"* at four separate levels.
- Sequence stated as a unit [08:04]: *"**Low taken, high taken, liquidity block.**"*

## What is worth acting on

- 🔴 **The time window is a real filter and is undefined.** Ask Aaron. Nothing can be scoped
  without it — it plausibly removes most candidate setups.
- 🔴 **Left-side internal liquidity is a second precondition.** Encoding needs to check for
  unclaimed pools *to the left*, not just above/below the entry. `engines/liquidity/` and
  `engines/equal_highs_lows/` both already emit the levels this needs.
- ⚠ **A reaction at a level is not a trigger.** Any detector must distinguish "reacted and built"
  from "swept and left" — those are the same bar pattern at different scales, which is exactly
  the sort of distinction that gets destroyed at the bottom of a pipeline.
