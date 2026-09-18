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

---

## First measured baseline — 2026-09-17

Command that produced it:

```
python3 backtest/tools/regime_grade.py --symbol XAUUSD.p --tf 240 \
  --start 2018-07-25 --end 2026-09-15 --horizon 30 \
  --trades <trades.csv from a fresh sos_fade 15m+5m replay> \
  --out backtest/reports/regime_grade_20260917
```

Scope: 12,593 four-hour gold bars, 2018-07-25 -> 2026-09-15, forward horizon 30 bars.
274 SOS Fade trades over the same window, replayed with the regime filter OFF so the
labels grade the trades without having changed them.

**Caveat on the data.** The study ran on the LIVE broker's gold feed (PU Prime, the `.p`
symbol), not the backtest broker named in `backtest/CLAUDE.md`. The attached terminal only
serves the live symbol, so a re-run on the backtest broker is still owed before any number
here is treated as final.

### What the labels are worth against the market

| label | bars | share | avg forward efficiency |
|---|---|---|---|
| TRENDING | 9,814 | 78% | 0.208 (0.198 - 0.217) |
| TRANSITIONING | 2,356 | 19% | 0.203 (0.187 - 0.218) |
| RANGING | 194 | 1.5% | 0.213 (0.177 - 0.247) |
| UNKNOWN | 199 | 1.6% | 0.169 |

The three labels are indistinguishable on the thing they are named after, and the
"ranging" label is followed by marginally MORE directional travel than the "trending"
one. The label is also degenerate: nearly four bars in five are called trending.

### What the labels are worth against money

| label | trades | avg R | range |
|---|---|---|---|
| TRENDING | 225 | +0.82 | +0.33 to +1.46 |
| TRANSITIONING | 41 | +1.32 | -0.18 to +3.43 |
| RANGING | 8 | -0.28 | too few to range |

Shuffle test: a spread this wide arises from randomly reshuffled labels **27.6%** of the
time. The label ordering is therefore not evidence of anything. Note also that the best
label here is TRANSITIONING - the opposite of the cut adopted for the extreme leg bot in
its Run 5. Different bot, so not a contradiction, but it means the Run 5 result has no
support from this study and should be re-checked on the extreme leg's own trade list.

### The readings, ranked

Against the market, over 12.3k-12.5k rows (Spearman, moving-block bootstrap, 95%):

- Volatility percentile is the strongest single reading: -0.223 on forward volatility
  change, -0.215 on forward excursion, -0.158 on forward move, -0.072 on forward
  efficiency. All four clear of zero, all four consistent in sign.
- Where price sits in its recent range is second: +0.210, +0.117, +0.089, +0.053. All
  four clear of zero.
- The variance ratio is weaker but consistent: three of four clear of zero, all negative.
- The engine's own three inputs are the worst of the seven. Its trend-strength and
  momentum-swing readings straddle zero on forward efficiency, forward move and (for
  momentum swing) everything. Its volatility ratio tracks future volatility (+0.160) and
  nothing else.

Against money, all seven have a rank correlation whose range straddles zero, so no
reading is a continuous predictor of trade outcome on 274 trades. Two show a band
ordering worth a second look:

- Where price sits in its recent range: bottom third +0.45R, middle +0.75R, top +1.39R -
  monotone, though the outer bands' ranges overlap.
- The engine's volatility ratio: the middle band (0.87-1.01) averages +0.50R against
  +1.87R below it. That is a band effect, not a threshold effect, and the shipped
  thresholds sit nowhere near it.

### Verdict

The shipped engine's labels cannot currently be used to decide whether a bot should
trade. They do not separate market behaviour, they do not separate money, and one of the
three labels covers 78% of all bars. Nothing here says market conditions are irrelevant -
two of the four candidate readings do carry a real, if modest, signal against the market.
It says the current three-input score and its round-number thresholds are not the way to
extract it.


---

## The candidate reading — 2026-09-17

`backtest/regime_study/candidate.py`. **It is not an engine and no strategy imports it.** It
sits under `backtest/` so that it cannot reach a live bot before the graders have scored it;
it moves into `engines/regime/` only if it wins, and the engine keeps exactly one
implementation either way.

Three changes from the shipped engine, each with a measurement behind it:

1. **Two scales, never collapsed into one.** How fast the market is moving relative to its own
   history, and whether moves persist or unwind. The shipped engine folds three inputs into
   one score and then one of five names, and 78% of bars came out with the same name.
2. **Bands are thirds of the instrument's own trailing history**, not hand-picked constants
   shared by every instrument. Equal populations by construction, so the degenerate bucket is
   impossible. Nothing is fitted, so nothing can go stale, and the reading needs no
   per-instrument file.
3. **The two readings are the two that survived eight years.** Trend efficiency looked strong
   on 2024-2026 and is weak across the full window - it was in the plan and was dropped when
   the full-history numbers came in.

⚠ **The bands are RELATIVE.** In a permanently calm year "fast" still fires a third of the
time. That is the right shape for "should this bot trade now, compared with how this market
usually is" and the wrong shape for a question about absolute danger.

⚠ **The variance ratio is RANKED, not read against its textbook value of 1.0.** Measured over
eight years of gold the quantity never centres on 1.0 - its middle third ran 0.985 to 1.133 -
so a band drawn at the textbook value would not split this market into the parts the theory
names.

Ten tests in `backtest/tests/test_regime_candidate.py`, four of them watched go red by
mutating the line they guard: the rule-1 `None` guard, the band edges, the degenerate-price
refusal and the causality truncation.


## The other bot's trades, and what its shipped gate is actually worth — 2026-09-17

The extreme leg is the only bot whose money passes through a market label, so it is the one
that matters. Its trades were exported twice over the same eight years, once with the market
cut ON (shipped) and once OFF, using `backtest/tools/trade_export.py`. The two books differ by
exactly 24 trades and nothing else - no trade appears in the gated book that is absent from
the ungated one, so there was no queue displacement and the comparison is a clean subtraction.

| | trades | sumR | avgR | worst losing run |
|---|---|---|---|---|
| market cut OFF | 170 | +88.9 | +0.52 | 8.13R |
| market cut ON (shipped) | 146 | +87.3 | +0.60 | 6.00R |

**The 8.13R -> 6.00R in the strategy's own Run 5 reproduces exactly**, on a different broker
feed and a fuller window. That is a real check on this harness as well as on that result.

🔴 **It is not, however, significant.** Dropping 24 trades AT RANDOM from the ungated book gets
to 6.00R or better **10.9%** of the time (20,000 draws, median 8.00R). One in nine. The 24
refused trades were worth +1.5R between them, +0.064R each - indistinguishable from zero.

**So the shipped gate is free, not proven.** It costs no return, which is why leaving it on is
defensible; believing it CAUSES the smaller drawdown is not, on 24 trades against a one-in-nine
null. Run 5 never ran this test - the number was adopted on a single comparison.

And the labels separate nothing on this bot either: trending +0.53R over 141 trades,
transitioning +0.56R over 26, a shuffle reproducing the spread 32% of the time.

---

## Head to head: shipped engine vs candidate — 2026-09-17

One run per bot, both labels scored on the SAME 12,372 bars, the same forward outcomes and the
same shuffle test. `backtest/reports/regime_headtohead_sosfade/` and `..._xleg/` (gitignored;
the command is the one above with `--trades` pointed at each bot's export).

### Against the market — the candidate wins, and not narrowly

| | biggest bucket | forward efficiency, lowest to highest bucket | forward move, lowest to highest |
|---|---|---|---|
| shipped | 78% of bars | 0.206 - 0.213, every range overlapping | 3.25 - 3.53 |
| candidate | 16% of bars | 0.168 - 0.236, ranges separated | 2.41 - 4.51 |

The shipped engine's shuffle test also reads 0.0% on three outcomes, and that is the trap: with
12,000 rows a 0.007 difference in forward efficiency is detectable and useless. **Significance
and magnitude are different questions and only the second one can gate a bot.** The candidate's
spread is a factor of 1.4 on forward efficiency and a factor of 1.9 on forward move.

🔴 **The ordering is the opposite of what the shipped labels imply.** The QUIET, mean-reverting
market is followed by the LARGEST subsequent moves (+4.5 ATR) and the highest forward
efficiency; the FAST, persisting market is followed by the smallest (+2.4 ATR). Consistent
across all four outcomes. A gate built on "trade when it is trending" is pointed backwards.

### Against money — nothing works, on either bot, old or new

| | reversal bot (274 trades) | extreme leg (170 trades) |
|---|---|---|
| shipped labels | shuffle matches 27.6% | shuffle matches 32.0% |
| candidate labels | shuffle matches 59.2% | shuffle matches 93.0% |

The candidate is WORSE here, and the reason is arithmetic rather than quality: nine cells over
170-274 trades is ~20-30 trades a cell, so every range swallows every other. Scoring one scale
at a time instead of the nine-cell join does not rescue it either - on both bots every band of
every reading, shipped or candidate, overlaps every other band.

### The one apparent exception, and why it is noise

The extreme leg showed a real-looking link between its outcome and the shipped engine's
momentum-swing input: -0.168 (-0.311 to -0.019), clear of zero, with the lowest third of
readings averaging +0.92R against +0.25R for the highest. That is the only money link anywhere
in this study, and it is in a reading the market half of the study calls useless.

**It does not survive being split in half.** First 85 trades: -0.259 (-0.467 to -0.054), lowest
third +1.30R against +0.09R. Second 85 trades, from 2023-01-26: -0.061 (-0.264 to +0.152),
lowest third +0.53R against +0.40R. Nothing. Six readings were tested against two bots, so one
result clearing 5% by chance is roughly what twelve comparisons produce, and the split
confirms it.

### Verdict

**The candidate ships as a market DESCRIPTION and must not ship as a money GATE.** It is a
genuinely better description of what gold does next, on every test, by a margin that is
practical and not merely detectable. It does not predict either bot's trade outcome, and
neither does the engine it replaces.

The spec's named failure condition is met for the gating question, and the honest answer is the
one it committed to: **market condition does not gate these two strategies.** That is not the
same as saying market condition is irrelevant - the market half of the study says loudly that
it is not - it says these two entry rules have already priced in whatever the condition
carries, which is what a selective entry is supposed to do.

What this leaves the extreme leg's shipped market cut: free, unproven, and now known to be
pointed at the wrong end of the reading. Leaving it on costs nothing measurable. Nothing here
justifies adding a second gate like it to any other bot.
