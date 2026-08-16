---
source: https://www.youtube.com/watch?v=76Oh3eBJ9Tg
title: Training The Eyes Ep. 6
uploader: Inter Equity Trading
duration: 11:05
watched: 2026-08-13
detail: cue frames (28 forced timestamps, native captions)
focus: Aaron's continuation model — the entry order type, and volume as a signal
---

# Training The Eyes Ep. 6 — AUDUSD H1, the limit entry

Naked AUDUSD H1, replay mode, one short. Deliberately stays on **one timeframe** the whole video
— *"I don't really want to switch between timeframes too much"* [00:40] — which makes it the
cleanest single-frame statement of the model. He calls the setup *"textbook"* and *"a bread and
butter kind of setup"* [10:15].

## 🔴 THE ENTRY IS A RESTING LIMIT AT THE LEVEL

This corrects a reading taken from Ep. 4 and it changes implementation, so it goes first.

[09:11], stated with the actual price:

> *"There's going to be liquidity above this high. **We're going to put our limit right at this
> high at 0.66102.** And look what the next candle does. Taps us in."*

And the principle at [07:50]: *"We like to take entries **as soon as liquidity is taken**. As
soon as this high is taken, liquidity has now been stabbed, liquidated, trapped — now we're
entering at that position."*

So the order is a **limit resting AT the level that is about to be swept**. Price runs the level,
the limit fills, the trade is on. That is the same instruction as Ep. 4's *"I don't need the
bottom"* seen from the other side:

| | |
|---|---|
| ✅ **Limit at the swept level** | This is the entry. Fills the moment the sweep happens. |
| ✅ Anywhere just past the level | Also fine — Ep. 4's *"anywhere below this black line"*. |
| ❌ **A deeper fill at the extreme** of the imbalance | What Ep. 4 warns against — *"you're going to be missing a lot of trades."* |

⚠ **Earlier note said a resting limit was the wrong shape for this model. That was wrong** — the
limit is exactly right, it just sits at the *level*, not at the extreme beyond it. The entry zone
runs from the level outward, and the level itself is its near edge.

## 🔴 Retail's break of structure IS the liquidity generator

The clearest statement in any of the six videos of *why* the liquidity exists, [01:41-02:24]:

> *"Price printed this new low. From a common retail perspective they now view this as a BOS…
> **automatically I now know that there is going to be liquidity above this high eventually**,
> because sellers are interested in selling below it based off this common retail pattern."*

And inverted at [06:49]: *"This high has been taken. So that's a BOS for retail. **Automatically
there's going to be a ton of liquidity at the lows down here.** So we want to be selling into
it."*

The model is explicitly **a bet against pattern traders**, and the direction is derived from
where their stops must be. This is the mechanism behind everything the other five videos assert.

## Volume and speed as the induction signal — new

[05:26-06:07], not mentioned in the earlier videos:

> *"Since we have sold off aggressively **with speed**, it's induced sellers into the market.
> **Look at the volume. One, two candles. Two candles sweep out what, 12, 13 hours of price
> action.** So this high volume move taking out lows induces sellers again."*

Two measurable things in one sentence:
- **Speed**: how few bars it took to erase the build-up.
- **Volume**: the sweep candles are high volume.

A sweep that takes two candles to undo thirteen hours is treated as a *stronger* induction than a
slow grind through. ⚠ Note this cuts against `engines/vwap/` and `session_volume_profile/` being
the only volume consumers — this model wants the bar's volume too.

## Time-building, quoted twice more

[03:04] *"about 11, 12 hours of price action building liquidity at this high"* and [04:45]
*"12, 13 hours, we couldn't break this high. Building, building, building."*

Third and fourth instances of duration-as-magnitude (Ep. 5 gave 5½ hours). Consistently quoted in
**hours on an H1/M5 chart**, always double digits. Still no threshold, but the order of magnitude
is now visible across two instruments.

## The "low probable move" — a named category of trade to skip

[03:45], new terminology:

> *"Any sort of buys coming out of this red area from the left-hand side — if it goes long,
> that's fine. **This is now known as a low probable move.** Yes, there was a long that occurred
> and it was actually just over 50 pips. However, it's a low probable move. **We do not want to
> be buying in a bearish market.**"*

He names a move that *worked* — 50 pips — and classifies it as one not to take. Same discipline
as Ep. 5's refusals. The counter-direction reaction off a left-hand level is real but is not the
model's trade, and *"any reactions out of here will literally just build liquidity at the lows
for us"* — i.e. it is fuel for the trade he does want.

## The trigger leg, stated as a requirement

[06:27]:

> *"This move from **low to high** is now providing us an opportunity to sell back down. **You
> need to wait for this kind of move to occur, low to high.**"*

That is the engineering leg from the continuation video, restated as a required trigger. For a
short: after the sweep of the lows, price must rally *back up* to give the entry. It is not
optional and it is not the entry itself — it is what creates the level the limit rests at.

## The stop, and why it's safe

[08:10-08:51], the LB logic in his own compressed form:

> *"Our stop is simply covering this high because it's a **liquidity block**. We built, built,
> built, then this candle — this whole area was created because we ran liquidity. We ran all of
> this liquidity built at these highs and then sold off with lots of volume. So **I'm viewing
> this high to have no liquidity above it.** That's why I'm letting my stop cover it."*
>
> *"Liquidity built, liquidity taken, and ran away."* — his one-line LB definition.

## The trade, in order

1. Downtrend, new low printed → **retail BOS** → liquidity will build above [01:41].
2. Price goes bullish, takes the high → **buyers induced**; every reaction there adds more [02:24].
3. Low respected twice; **11-12 hours building at a high**; spike, sharp sell-off [03:04].
4. Price taps a left-hand area, rallies 50 pips → **low probable move, skipped** [03:45].
5. **12-13 hours** unable to break a high → build → long → sellers trapped [04:45].
6. Two high-volume candles erase it, taking out a low with speed → **sellers induced** [05:26].
7. That area is now a **trap**; price must come back above the high [06:07].
8. **Low-to-high leg** occurs — the required trigger [06:27].
9. **Sell limit at 0.66102**, right at the high; **stop covering the LB high**; target the lows
   [07:29-09:11].
10. Fills next candle. High taken → buyers induced → rejection → lows taken → target [09:32-10:15].

## What is worth acting on

**Corrects one thing and confirms the rest:**
- ✅ **Entry = limit at the level.** Not a market order, not a deep pullback fill.
- ✅ Stop covers the LB. Target is the opposing liquidity. Unchanged across all six videos.

**New and measurable:**
- ⚠ **Volume and speed of the sweep** as an induction-strength signal. First appearance. Two
  candles undoing thirteen hours is the shape he wants.
- ⚠ **The retail-BOS mechanism** gives us a *derivable direction rule*: a structure break in one
  direction implies a liquidity pool on the opposite side, and that pool is the target. This is
  the most encodable statement of bias in the six videos, and `engines/market_structure/` already
  emits exactly the BOS/CHoCH events it needs.
- ⚠ **"Low probable move"** — a named skip category, useful as a label when we start classifying
  what the model rejects.
- ⚠ **The low-to-high (or high-to-low) trigger leg is mandatory.** Same object the continuation
  video called engineered liquidity.

⚠ **Still no numbers.** Six videos, one worked example each, no win rate, no sample, no backtest.
