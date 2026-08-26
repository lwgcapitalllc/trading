---
source: https://youtu.be/jGAS_1bOevA
title: Training The Eyes Ep. 2
uploader: Inter Equity Trading
duration: 07:30
watched: 2026-08-25
detail: transcript
focus: fill the gap — Eps. 1–3 were never watched
---

# Training The Eyes Ep. 2 — gold 15m, and the stop is dictated by the market

Second in the series. One gold chart, 15-minute only — *"we're only going to stay on this time
frame right now cuz this shows everything clearly."* A long setup marked from the left, entered on
a limit, and it runs on a Powell speech.

## What it covers

**[01:09–02:00] Volume as the induction tell.** *"Look at the volume in this sell-off… keep an eye
on that."* He returns to it: *"a lot of volume to the downside to induce sellers."* A violent leg is
what traps, and it is visible in volume. Same signal as Ep. 9.

**[03:34–04:13] The entry level, and why it is empty.** *"We swept that previous low out and we went
long. Which tells me **we don't have any liquidity below this low**."* So it is safe to buy from —
buyers who entered in the buildup above it have their stops below it, and that is the liquidity the
entry sweeps.

**[04:13–04:47] 🔴 THE STOP IS NOT A BUFFER RULE — THE MARKET SETS THE DISTANCE.**

> *"Stop loss is going to go right below that low. And that's always gonna stay like that. So this
> low here determines how big our stop is going to be. Sometimes the stop's going to be all the way
> down here, it's going to be a little bit bigger. Sometimes smaller. **The market dictates how big
> my stop is going to be. It's very systematic.**"*

This answers the spec's open question 4 from the opposite direction to the one it was asked: there
is no scaling formula, because there is no buffer to scale. The stop sits past the level; the level
is wherever the market put it. See [[2026-08-25-steal-this-easy-liquidity-trap-foundation]] for the
instrument-dependent spread allowance that sits on top of it.

**[04:47–05:46] Targets are stacked, and the far one is slow.** Nearest: the buildup of internal
highs on the way down. Far: a high that respected earlier highs. *"Yes, it's quite a big target. So
this could take the day to play out. It could take two days."*

**[06:11–06:51] The result.** Buyers above the low get liquidated, price is tagged in, and a news
event (he thinks Powell) drives it. **Over a 300 pip move on gold from a single 15-minute candle.**

## Worth acting on

- **The stop rule is now stated identically in four videos** and should be written into
  `docs/DAVINCI_MODEL_SPEC.md` as settled: past the level, market-determined distance, plus an
  instrument-dependent spread allowance. Stop treating it as an open question.
- The trade ran on a scheduled news event. Combined with the news rule in the foundation video
  (never enter before a release, enter 2–4 minutes after), **news is a timing input in this model,
  not just a blackout** — which is the opposite of how `engines/news/` is used today.
