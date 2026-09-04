# Loss Recovery — Optimization Log

**Every parameter sweep run on this leg goes in this file, newest run at the bottom.**
Each entry records the question, the answer, how it was measured, and the full grid — so a
later run can be compared against an earlier one instead of re-litigated.

**Why this file exists:** a refusal that is not written down gets retried, and retrying a sweep
is how a noise result eventually wins by chance. **A negative result recorded here is worth as
much as a positive one.**

Standing rules for anything recorded here:

- **Score in R, never dollars.** Sizing risks a fixed percentage of equity, so dollars compound
  and a dollar ranking measures recency rather than edge.
- 🔴 **COST BOTH SIDES OR THE VERDICT FLIPS.** This leg is scored against the primary bot it
  rides on, and charging costs to one and not the other is rule 11 broken. Measured: uncosted
  primary against costed recovery says the plain risk dial wins; costing both says the recovery
  wins by 1.3–1.7x. The primary holds a median 0.3 days and 100 of its 181 trades are shorts,
  which gold pays a swap *credit* to hold, so it loses only 7% of gross to costs while this leg
  loses far more. **Any tool used here must charge both.**
- ⚠ **This leg's population is the primary bot's real stop-outs**, so every figure here moves
  when the primary's entry logic moves. Re-run after any change to `sos_fade`.
- **Re-check any winner with its best few trades deleted.** At n=62 a single cluster carries a
  result — Run 2 is the worked example, where the best-looking challenger was five trades.
- **A result here is a measurement, not a default.** This leg still ships `enabled=False`.

## The basis

| | |
|---|---|
| tooling | `backtest/tools/recovery_report.py` |
| data | XAUUSD M15, 186,910 bars, 2018-09-14 → 2026-08-14 |
| primary | `sos_fade` at shipped defaults with the 1m re-entry OFF, warmup 1000, bar fills |
| costs | **both sides** at `puprime_ecn`, the live account's tier |
| population | the primary's 62 stop-outs |

## Runs

| # | Date | What was swept | Winner | Status |
|---|---|---|---|---|
| 1 | 2026-08-19 | **The size of the recovery trade**, as a fraction of the primary's risk | **25% ADOPTED as the default size.** It is two answers at once — the largest size that does not raise drawdown above what the primary already runs, and the peak of the efficiency curve. **1,913x → 2,772x at the same drawdown (48.8% → 48.3%), i.e. 1.53x what the same drawdown buys on the risk dial.** ⚠ The curve is flat from 20% to 55% (1.53 → 1.48), so it is not a knife edge. | **measured — leg still ships OFF** |
| 2 | 2026-08-19 | **Nine stop placements and six exit ladders.** Recorded in full as Run 24 of `strategies/python/sos_fade/sos_fade_optimization.md` — it was filed there because the population is that bot's stop-outs | **NOTHING BEAT THE SHIPPED RULE.** A stop on the change-of-character bar's own extreme scores **+24.4R** against +16.2R on a 7x tighter stop with lower drawdown — and 🔴 **−7.4R once its best five trades are deleted**, where the shipped stop survives at +2.3R. **The one free change is a soft stop at −0.3R:** same net R, average loss −1.01R → −0.30R, win rate 58% → 37%. Everything else lost. | measured, **nothing adopted** |

🔴 **THE STANDING RESULT, and it is the first thing to say to anyone who reaches for this leg to
make a losing streak hurt less: IT DOES NOT REDUCE DRAWDOWN. IT BUYS RETURN.** Max drawdown at
25% size is **48.3%** against the primary's **48.8%** — unchanged — and at 100% size it goes
**UP**, to 57.2%. **There is no size at which this protects the account.**

⚠ **The intuition it defeats is a good one, so the reason is recorded rather than just the
verdict.** The hope is that a recovery fires mid-streak and shortens the hole. It does fire
mid-streak and it is not too slow: over 13 losing streaks **76% of recoveries resolved before the
next primary loss landed**, and every streak got a signal. **The arithmetic is what kills it —
inside those streaks the recoveries put back +0.75R against −16.4R of losses they sat between.
5%.** It cannot be fixed by sizing up, because a quarter-size trade winning 58% of the time
scales its losses with its wins.

---

# Run 1 — the size of the recovery trade

**Date:** 2026-08-19
**Command:** `python backtest/tools/recovery_report.py --start 2018-09-14 --end 2026-08-14 --sweep`

| | trades | result |
|---|---|---|
| primary alone | 181 | gross +138.9R → net **+129.0R**, **1,913x** at 10% risk, max drawdown **48.8%** |
| recovery at full size | 62 | **+16.2R**, **58%** win, 35 of 62 locked, median hold ~4 days |
| **recovery at 25% size** | 62 | **2,772x** at **48.3%** drawdown — **1.53x** what the same drawdown buys on the risk dial |

**25% is adopted because it is two answers at once:** the largest size that does not raise
drawdown above what the bot already runs, and the peak of the efficiency curve. ⚠ **Flat from
20% to 55%** (1.53 → 1.48), so it is a plateau rather than a spike — which is why it is trusted.

---

# Run 2 — nine stop placements and six exit ladders

**Date:** 2026-08-19
**Full record:** `strategies/python/sos_fade/sos_fade_optimization.md` → Run 24. It was
filed there because the population is that bot's stop-outs; it is indexed here because it is a
sweep of THIS leg's parameters and this is where somebody will look for it.

**Verdict: nothing beat the shipped rule, and its best-looking challenger was five trades.**

- A stop on the change-of-character bar's own extreme: **+24.4R**.
- A 7x tighter stop: +16.2R with lower drawdown — and 🔴 **−7.4R once its best five trades are
  deleted**, where the shipped stop survives at +2.3R.
- **The one free change: a soft stop at −0.3R** — same net R, average loss −1.01R → −0.30R, win
  rate 58% → 37%. Not adopted.
- Everything else lost.

⚠ **The transferable lesson is the deletion test.** At n=62 the challenger looked like a
drawdown improvement and was a cluster of five trades. **Delete the best few before believing
any winner on this leg.**
