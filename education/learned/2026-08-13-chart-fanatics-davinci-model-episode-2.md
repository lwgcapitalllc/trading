---
source: https://www.youtube.com/watch?v=T_djSNBmV00
title: The ONE Liquidity Trading Pattern That Actually Works (Precise Entries)
uploader: Chart Fanatics (guest: Marco Aset / @marcotrades, Inter Equity Trading)
duration: 1:11:22
watched: 2026-08-13
detail: transcript only (native captions; 71 min — frames not extracted)
focus: the Da Vinci model named and specified — the anchor for the whole set
---

# Chart Fanatics — the Da Vinci model (episode 2)

🔴 **This is already `docs/DAVINCI_MODEL_SPEC.md`'s "video 2".** The spec covers the sequence,
the liquidity block's two jobs, and the worked examples in more detail than this note will. **Read
the spec first.** This note records only what the transcript adds to the spec's *open questions*,
plus the operator-level rules the spec does not carry.

**The presenter is the same person as the entire "Training The Eyes" series** — Marco, Inter
Equity Trading. So all thirteen of those episodes are the same model taught without the name. That
connection is the main finding of this session and is what makes the other notes usable as
corroboration rather than as a second opinion.

## What this transcript adds to the spec's open questions

**Q7 — which timeframes, and how far down for entry?** Answered, and it is instrument-dependent:

> *"Typically CFD I'm holding trades long-term… over the course of a couple days maybe even a
> week. However, in the futures market you've got to close before market close. So typically
> we'll be looking at a model to take an entry off the **1 minute, 5 minute** — really deep into
> the lower timeframes — and then targeting those **15 minute, 1 hour** levels."*

**Q6 — what kills a setup?** Partly answered. A failed sweep is **not** a thesis failure:

> *"Let's say price comes down and sweeps out this low [and fails], then I need to wait for
> something like this to occur again. I need to see early buyers induced, I need to see those
> early buyers taken out, and then I will look for my entry again. **We still have liquidity to
> the upside. Maybe we were early. That's fine. But it does not mean the direction, the bias, the
> idea is incorrect.**"*

So: re-arm and re-enter on the same thesis while the target pool is still unclaimed. The setup
dies when the **target** is taken, not when an entry fails.

**The liquidity-block veto, confirmed with the reasoning:**

> *"We had a big liquidity block, a low that doesn't hold any liquidity. So **the stop loss is too
> big. When the stop loss is too big, the RR is shot in my opinion and I just don't take those
> trades.** So what I need to do is wait for the lower timeframe to develop an entry for me."*

## 🔴 The operator rules — none of these are in the spec

**Minimum RR is 1:3.** His own stated threshold:

> *"I understand that I perform the best, I make the most money, when my **RR is minimum 1 to 3
> minimum**. That's just what I found works. If 1 to 1.7 works for you, go ahead. But for myself I
> do want to see a higher R on the table."*

Consistent with Training The Eyes Ep. 9, where he refuses to partial at 1:1.6.

**Do not over-refine — it costs you entries:**

> *"A lot of people like to **over-refine** and look for an imbalance in this low. In my opinion,
> unnecessary… because typically when people over-refine **you're going to start missing
> entries**. Keep it as easy as possible: once this low is taken, where the liquidity is, you
> enter your buy position."*

Settles the same question the Training The Eyes series answers three times: enter on the stab, do
not hunt a deeper fill.

**And you do not need the extreme:**

> *"Do you need the absolute extreme? Even if you grab this low… **remember the stop loss is the
> most important part.** Don't get greedy. Even if you didn't take the lowest point, look at the
> RR still — you are still catching almost a 1 to 5."*

**Nested Da Vinci — HTF for direction, LTF for entry:**

> *"Sometimes I'll have a Da Vinci model on the higher timeframes providing me my direction, my
> bias, and then **a Da Vinci model playing out on the lower timeframes providing me my entry**.
> That's when the RR can get stupid."*

**Frequency — the number that scopes everything:**

> *"Sometimes they'll come along a couple times in a week, sometimes **once or twice in a
> month**."* (for the high-RR ones; the model itself presents day-to-day on lower frames)

⚠ This sits exactly on the repo's standing **Trading Philosophy** — few high-quality setups, and
sample size arriving at the portfolio level. It is corroboration from an outside source that the
low trade count is the design, not a defect.

**Risk sizing:** *"you could risk **0.5% to 0.75%** and still make $10,000, $20,000 in payouts
because of the asymmetric setup"*, plus *"I have a specific figure I'm willing to risk on a
**daily** basis."* A daily loss cap exists; the figure is not given.

**Why he claims high RR AND high win rate coexist** — the causal claim, worth recording because it
is testable and probably wrong:

> *"The smaller the stop, the lower the RR — in some ways that's correct. However the reason that
> occurs is typically **for a higher RR you need a lower timeframe entry**. People go into lower
> timeframes and they're more prone to make mistakes… when mistakes occur the strike rate goes
> down. **If you prioritise patience and discipline, your strike rate won't get affected.**"*

⚠ He attributes the usual RR/win-rate tradeoff to *execution error* rather than to the geometry of
a wider target. That is a strong claim, it is unmeasured, and it is the sort of thing this repo
exists to check.

## Claims, unverified

*"Last year I did over $100,000 in payouts."* Host introduces him as having *"over $500,000 in
payouts."* Prop-firm payouts, not a verified track record, and the episode is sponsored by three
prop firms and a journalling tool. ⚠ **No win rate, no sample size, no equity curve is shown at
any point in 71 minutes** — same as all thirteen Training The Eyes episodes.

## What is worth acting on

- ✅ **Q7 and the re-entry half of Q6 are now answered** — see above.
- 🔴 **Minimum 1:3 RR, and the liquidity-block veto, are hard filters that will remove trades.**
  Both must be in any replay or the backtest takes trades he would refuse.
- 🔴 **Frequency: a couple a week to once or twice a month** for the high-R setups. That is the
  number to size expectations against before building anything.
- ⚠ **The presenter identity links all fifteen videos.** The Training The Eyes notes in this
  folder are the same model and can be used to answer spec questions — see especially
  [Ep. 9](2026-08-13-training-the-eyes-ep9-nq-the-edge-stated.md) on the breakeven trigger, which
  resolves the spec's open question 9.
