---
source: https://www.youtube.com/watch?v=4pINx9wV18U
title: SIMPLE Liquidity HACK You Need To Learn
uploader: Inter Equity Trading
duration: 15:43
watched: 2026-08-25
detail: transcript + 14 transcript-cue frames at 1024px
focus: general — what this adds to docs/DAVINCI_MODEL_SPEC.md
---

# SIMPLE Liquidity HACK You Need To Learn

One trade on gold, narrated end to end from the daily frame down to the 1-minute entry, using the
replay tool on a Thursday→Friday. **The most complete single walkthrough in this folder**, and the
only one that contains a documented scratch, a re-entry, and a hard number for the stop buffer.
It answers four of the spec's open questions and introduces two rules that are in nothing else we
have.

The trade: short from ~4,084.4, stop above ~4,090.9, ran to ~4,026. About **nine times risk**. He
reports ~$6,500 across a funded and a personal account. ⚠ **The captions garble the R he says out
loud** ("A 128.88 88") — it is almost certainly "1 to 8.88", and the arithmetic off his own chart
(58.4 of reward against 6.5 of risk = 8.98) corroborates it. Treat 8.9R as read off the chart, not
as a quoted figure.

## What it covers

**[00:16–02:44] Top-down framing, stated as a procedure for the first time.** Daily first: mark the
previous day's high and low, every day, before anything else. Then the 4-hour — and here he rejects
it out loud because it is *"quite squeezed up"*, and drops to the hourly. **The timeframe rule is
"drop until the price action is legible", not a fixed pair.** He names this as the answer to the
question he says he gets most often.

**[02:28] Previous-day levels are never traded on their own.** *"We're not shorting above PDH just
because it's a daily high. No. We need to open up the chart. We need to find liquidity."* A daily
level is a frame for possibilities, not a signal.

**[03:47–04:16] How the far target gets chosen, before the setup exists.** Thursday swept
Wednesday's high; Wednesday's **low was left intact**. He marks that untouched daily level and it is
still the final target fifteen minutes later. So the last target is a higher-timeframe level nobody
has taken, identified during the framing pass rather than during the trade.

**[05:16–05:58] Marking the entry level — the counterfactual, again.** Look left, ask where the
bottom came from. A level respected on the way up means buyers committed there, so liquidity rests
below it. He drops to the 1-minute purely to find the exact low, then goes back up. The level is a
low, not a zone.

**[06:41–07:24] 🔴 A LEVEL CAN BE SKIPPED PERMANENTLY, AND A LIQUIDITY BLOCK IS WHY.** This is new
and it is not in the spec. Price spiked the previous daily high, moved away bearish, and left a
liquidity block behind it. The market then reacted off that block and **never went back for the
daily high**:

> *"The market reacted off the liquidity block and did not take out previous daily high because we
> didn't need to take out previous daily high. Why? It was a liquidity block and that's why it was
> respected."*

**An unswept level with a block in front of it is not a pending target.** Every model here that
treats "un-swept" as "still owed" gets this wrong.

**[07:11] The money-sign habit.** When he was building the system he plotted `$$$` above the highs
holding liquidity, to force himself to see it. Visible on the charts throughout.

**[07:41–08:20] 🔴 A DOCUMENTED SCRATCH AND A RE-ENTRY.** The spec calls a losing or invalidated
example *"the most valuable single screenshot and the hardest to get"* — this is it. He took an
earlier short, moved it to breakeven **because of the time of day** (3pm Thursday, which he calls a
bad time to be holding), got tagged out for zero, and price then ran without him. The rule stated
plainly:

> *"Just because I'm break even does not mean my analysis is incorrect."*

He waited for another entry on the same idea. Not a loss — a scratch — but it is a full invalidation
and re-entry with the reasoning attached.

**[08:34–09:18] The setup, in his order.** On the 1-minute: an old low taken, a new low printed, a
sudden reaction up taking highs, then a move away — *"you guys should all know what this is called,
a liquidity block."* Only **after** the block forms does he look for the level: *"you wait for the
liquidity block to form. Now, I want to see a level of liquidity built."* Then the higher timeframe
has to agree on direction. Three conditions, in that order.

**[09:32–10:03] 🔴 THE ENTRY IS A RESTING LIMIT, SET BEFORE BED.** Not a watched trigger. He sets
the limit at ~11pm Thursday and goes to sleep; the fill happens in London while he is unconscious.
No discretion at the entry at all.

**[09:48] 🔴 STOP PLACEMENT, WITH A NUMBER.**

> *"Stop loss goes above the high here, above the liquidity block. That always stays the same. I'm
> never going to get greedy and just plot it in a random level. No, it needs to be above the LB."*

Plus spread for gold — he calls it **50 pips**, which on his chart is about **$6.5** of price. ⚠
**This is far from the spec's other data point** (~0.2 on a 1-minute gold chart, from example 1b).
Both cannot be the rule. Reconcile before anything codes a stop.

**[10:03–11:08] A three-layer target ladder.** First an internal liquidity level as a partial /
manage point, then the daily level from the framing pass as the final target. With a warning
attached: taking out an internal liquidity level **typically produces a reaction in the opposing
direction**, and how far it retraces depends on the higher timeframe. So the bounce after a partial
is expected behaviour, not a failing trade.

**[11:08–11:48] The "low probable" refusal, stated twice.** Do not look for entries when there is a
clear level of liquidity sitting directly above them. He is scathing about pattern-matching without
this check: *"You need logic in this analysis or you're just going to be plotting on highs and lows
everywhere… you'll accumulate a lot of losses."*

**[12:20–12:52] The trap rule.** A low taken out induces sellers because they read it as their break
of structure. Therefore **any reaction at the high above is false — sell above that high, never
below it.** The entry fires right before the Frankfurt open, which he flags as no coincidence.

**[13:16–13:36] Engineered liquidity, named on the chart.** The whole low-to-high move is labelled
`Eng LQ`. Same object as the spec's step 4.

**[13:52–14:03] 🔴 WHEN THE STOP MOVES — third independent confirmation.**

> *"If I was watching this live, yes, I'd be going break even here 100%. Why would I not? Either go
> break even or pay yourself. One or the other."*

The moment is **a liquidity level being taken**, not a distance travelled. Same answer as
[[2026-08-13-10000-hours-of-liquidity-htf-only]]. He does not act on it here only because he is
asleep.

## Worth acting on

1. **Reconcile the stop buffer before anything codes it.** ~$6.5 here against ~0.2 in the spec's
   example 1b. That is a 30x spread on the same instrument. Spec open question 4 asks how the buffer
   scales and this makes the question sharper, not softer.
2. **Add the "block in front of a level" rule to the spec.** An unswept level with a liquidity block
   between price and it is not a target. Nothing in `docs/DAVINCI_MODEL_SPEC.md` or the student
   handout says this, and it changes which levels a scanner would count.
3. **Close spec open questions 2, 6, 7 and 9** — target selection from an untouched higher-timeframe
   level, an invalidation-with-re-entry example, the drop-until-legible timeframe rule, and the
   breakeven trigger. All four have answers in this video.
4. **The ordering constraint is testable**: block forms → *then* level of liquidity builds → *then*
   higher timeframe agrees. `backtest/tools/loaded_level_scan.py` does not enforce an order between
   the block and the level.
5. **Time of day is a risk input, not just a filter.** He reduced a valid trade to breakeven purely
   because of when it was. Related: [[2026-08-13-training-the-eyes-ep8-gold-time-window-and-left-side-liquidity]].

## Not worth your time

**[01:37–02:16]** is a 40-second sponsor read, mid-sentence. Skip it.

The framing in the first two minutes is slow if you have watched any other video in this folder —
the substance starts at about 02:28.
