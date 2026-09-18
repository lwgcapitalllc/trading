# Grading the market-condition engine — `backtest/regime_study/`

**Read before touching:** the market-condition grading harness, or quoting any number it prints.

---

## Why it exists

`engines/regime/` had shipped for months with no measurement of any kind behind it. It had no test
file, no golden case and no study. The only evidence it had ever produced was one bot's worst
losing run improving from 8.13R to 6.00R over **40 refusals** (extreme leg, Run 5, 2026-09-02) —
well inside what luck produces on 40 decisions, and never described as anything stronger.

So there was no way to tell whether a change to it helped. That is the gap this package fills, and
it was built **before** any change to the engine deliberately: a change with no scoreboard is a
guess, and this repo's history is a list of guesses that looked fine.

## The reframe — why "is the classifier accurate" has no answer

A market condition is **latent**. There is no true label anywhere to compare a prediction against,
so accuracy is not a defined quantity and any argument about whether a given day was "really"
trending is unfalsifiable. Two questions replace it, and both are answerable:

| Grader | Question | Sample |
|---|---|---|
| A — `grade_market.py` | Does a reading of the market predict what the market does **next**? | tens of thousands of bars |
| B — `grade_bot.py` | Conditioned on that reading, did a **given bot** make or lose money? | a few hundred trades |

Both are needed and neither substitutes for the other. **A reading that fails grader A cannot be
rescued by grader B** — if it does not describe the market, a bot doing well under it is a
coincidence with a name on it. And grader A passing proves nothing about a bot, because a real
property of the market may be one this strategy is indifferent to.

## The three things that would have made the report lie

**1. Look-ahead at the bar boundary.** A bar is stamped with its OPEN time and covers the period
after it, so the bar containing a trade's entry has not finished yet. Reading it hands the study
hours of price the bot could not see. The effect is subtle, **always flattering**, and invisible in
the output. `grade_bot._condition_index` steps back to the last fully closed bar; the test pins it
in both directions and was watched go red with the step-back removed.

**2. The reading half and the answer half sharing a bar.** Readings use bars up to and including
`i`; outcomes use bars strictly after `i`. Nothing may straddle. Three tests hold this, including
the mirror test — an outcome that ignored the future entirely would pass a look-ahead test
perfectly, so there is a test that the outcomes *do* move when the future moves.

**3. 🔴 The bootstrap treating correlated bars as independent.** This is the big one and it is why
`stats.py` uses a **moving block bootstrap** for anything bar-level. Consecutive bars are heavily
autocorrelated — a volatility reading barely moves bar to bar — so 400,000 bars carry nowhere near
400,000 independent observations. Resampling one bar at a time invents independence that does not
exist and produces a confidence range perhaps **five to ten times too narrow**; every reading in
the report, including pure noise, would come back confidently significant. Block resampling keeps
the local correlation inside each block. `test_the_block_bootstrap_is_wider_than_the_naive_one_on_sticky_data`
is the guard, and it goes red the moment the block length collapses to 1.

⚠ **Trades use the ORDINARY bootstrap, deliberately.** Two trades days apart share no bars, and
blocks would only throw away resolution on the sample that is already the smallest.

## How to read the output

- **Read the range, never the middle number.** A range that crosses the no-effect point means the
  reading told us nothing — not "a weak signal", not "promising". The tool prints that verdict in
  words for exactly that reason: a bare correlation of 0.04 reads as a small effect when it is
  usually no effect at all.
- **Rank correlation, not ordinary correlation.** Gold has fat tails; an ordinary correlation on
  this data is carried by a handful of crisis bars.
- **The shuffle test is what settles a table of per-label averages.** It reports how often
  shuffling the labels produces a spread as wide as the real one. Above 5% the table is what
  randomness produces anyway.
- **The label flip rate is the number that decides whether a gate is usable at all.** A condition
  that changes every few bars is not a condition, and a bot gated on it is switched on and off
  inside a single move — a cost no table of average outcomes would ever reveal.
- **A band table, not a correlation, is what a threshold is read off.** A correlation says a
  relationship exists; the bands say *where* on the reading the behaviour changes.

## The candidate readings, and why each is there

| Reading | What it answers | Why not the shipped one |
|---|---|---|
| how straight the move is | net move ÷ total travel, 0–1 | the shipped trend-strength reading's scale means something different per instrument and timeframe; this one means the same everywhere |
| how fast vs its own past year | a **rank**, 0–1 | the shipped volatility reading is a ratio to its own 20-bar average — in a long calm stretch it flags a nothing-move as an expansion, and in a crisis it reads ~1.0 while the market tears itself apart |
| do moves persist or unwind | variance ratio, 1 = no memory | nothing in the shipped engine asks this, and it is close to independent of how fast the market is moving — which the shipped engine's three inputs are not |
| where price sits in its range | 0–1 | a market pinned at an extreme behaves differently from one mid-range even when everything else agrees |

The shipped engine's own three readings are in the registry too, **imported from its code rather
than re-implemented**, so old and new are graded on identical footing and the thing being graded is
the thing that ships. A test asserts they still match the engine's own arithmetic.

## Known limits — say these out loud with any result

- The band tables in grader B are computed on the same trades any threshold would be chosen from,
  so a preview of a gate cut that way is **optimistic by construction**. The honest number comes
  from a real re-run on a window the threshold never saw. The kept/refused counts matter more than
  the R — a gate that refuses four trades cannot be measured at all.
- A bot here may have ~164 trades. Cut five ways that is roughly thirty per group. If every range
  overlaps every other, the answer is that this bot cannot be gated on market conditions, and that
  is a **result** to be reported, not a starting point for tuning.

## Scope

Reads bars and a finished trade list; writes a report. It never re-runs a strategy, never touches
`engines/`, `algos/` or any stored baseline, and cannot change the run it is grading.
