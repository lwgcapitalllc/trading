# RSO Realign — the user's 1-minute retail shake-out, measured

**Status:** 🔴 **MEASURED 2026-09-14 — NO MECHANICAL EDGE. The one clean check is SPENT.**
**2026-09-16:** the higher-frame gate the user's own name for the pattern implies — measured raw
and charged, on every frame: **it does not help, and on 5m and 15m it hurts** (section below).
**2026-09-16, second pass:** the user's displacement rule, the shift-level retest and reward-to-risk
at entry — **the far close is a bad entry as he said; nothing else in it clears the bar** (below).
**2026-09-16, third pass:** the gold family on silver, EURUSD and NAS100 — bars nothing had looked
at — **failed 0 of 3** (below). The pattern is measured out on this repo's data.
**2026-09-16, fourth pass:** the user's breaker entry (a limit back at the counter push's BOS level)
— **both of the user's trades found to the cent, and the rule loses on all four instruments** (below). The target was
misread and corrected the same day; it still loses.
**2026-09-16, fifth pass:** the user's full rule from four trades (a stop-size ladder) and their
second-realign alternative — **every trade reproduces, both rules fail** (below).
Tool: `backtest/tools/rso_realign_study.py` (its docstring carries the same record).
Tool note: `backtest/notes/tools.md`. Nothing here is a strategy, a bot or a Pine file.

⚠ **Not the RSO in `docs/FB_SPEC.md`.** That one is a video's model (early break → wick shake
out → aggressive real break). This one is the user's own sequence, drawn on their charts.

---

## The rule, as the user trades it

Short (a long is the exact mirror):

1. **Trend** — a bearish BOS.
2. **Counter shift** — a bullish SOS. Retail buys the turn.
3. **Counter push** — one or more bullish BOS. Retail adds.
4. **Realign** — a bearish SOS. Structure turns back with the trend. **The trade.**
5. **Stop** — beyond the counter push's highest point.

Taken from five of the user's 1-minute XAUUSD charts: shorts on 14 Sep ~07:51, 10 Sep ~21:22 and
10 Sep ~06:31; longs on 25 Aug ~11:30 and 11 Aug ~20:55 (New York time, 2026). The user labelled
all five September; PU Prime's daily ranges put the two longs in August.

## What was tested — declared before any result

Agreed in chat 2026-09-14 ("lets go ahead"). The user asked for the best WIN RATE; the study ranks
on **net R per trade after costs** instead, because a smaller target buys win rate while the account
shrinks. Win rate is reported beside every row.

| axis | values |
|---|---|
| chart frame | 1m (the user's), 5m and 15m resampled from the same 1m bars, each judged alone |
| counter BOS | exactly 1, or 2+ |
| entry | market at the realign close · limit at the 0.5 of the realign leg · pullback to 0.382 then a next-frame-up candle closing back · half and half |
| stop | one spread through the counter push's extreme · 2 × ATR(14) of the chart frame |
| exit | 1R · 1.5R · 2R · 3R · the counter push's origin · 2R with breakeven at +1R · half off at +1R then trail 1R · breakeven at +1R then trail each new swing |

The breakeven and trailing exits were the user's addition, declared **up front** alongside the fixed
targets rather than tried after they failed. 128 cells a frame, 384 in all.

**Shared rules:** one position at a time across both sides; a pending entry holds the slot and dies
after 60 chart bars or on a chart close through the counter top; out at market after 500 chart
bars; every step in R; a stop move takes effect on the next minute; a minute touching both sides is
the worse outcome; every trade walked on raw 1-minute bars whatever the chart frame; PU Prime ECN
costs (spread $0.12, $1/side/lot, swap).

**Pick rule** (the Loaded Level study's): ≥ 30 trades, net R positive in both halves (split
2023-05-01), more than half the one-step neighbours positive, z ≥ 2 against random entries matched
on side, calendar month, New York hour, stop distance and exit rule; ranked by the worse half's
average R. **Then ONE run on 2018-09-14 → 2019-12-31**, data no test of this pattern had touched.

## Recall — does the tool see the user's trades?

`python backtest/tools/rso_realign_study.py --recall`

| chart | found on 1m | realign close vs user entry | counter extreme vs user stop | user's own trade on PU Prime |
|---|---|---|---|---|
| 14 Sep short | +0 min | −0.22 | −0.95 | target, +1.61R — the stop missed by **$0.10** |
| 10 Sep pm short | −1 min | −0.81 | −0.09 | target, +2.08R |
| 10 Sep am short | +1 min | −1.32 | −0.11 | target, +1.40R |
| 25 Aug long | **not a 1m realign** | — | — | **stopped, −1.00R** (by $0.05) |
| 11 Aug long | +10 min | +0.41 | +0.30 | target, +1.19R |

On 25 Aug the 1m structure had already turned bullish at 10:07, and the 11:30 entry sits inside a
run of bullish BOS. The 5m frame shows a realign at 11:39, but its counter extreme is 4605.29 — the
user's stop sat $29 tighter than their own rule.

## The grid — 2,371,706 PU Prime M1 bars, 2020-01-01 → 2026-09-11

`python backtest/tools/rso_realign_study.py` → `backtest/reports/rso_realign_study/grid_puprime_ecn.csv`

| frame | realign setups (short / long) | cells positive in both halves | best t |
|---|---|---|---|
| 1m | 2,510 / 2,552 | 4 of 128 | +0.82 |
| 5m | 469 / 467 | 3 of 128 | +0.81 |
| 15m | 179 / 176 | 46 of 128 | +2.88 |

- **1m, the rule as drawn** (market at the realign close, structure stop) loses in all 16
  counter × exit rows: −0.002 to −0.082 R a trade over roughly 1,500–2,500 trades.
- **15m, the rule as drawn** makes +0.04 to +0.13 R a trade with 1 counter BOS — and random
  entries at the same month and hour make about the same (z 0.2–0.7). That is gold's drift, not the
  pattern. With 2+ counter BOS it runs −0.10 to +0.06.
- **16 cells qualified, every one 15m with 2+ counter BOS.**

**The pick: 15m, 2+ counter BOS, limit at the 0.5, 2 × ATR stop, 3R target** — 122 trades,
+61.9R, +0.507 a trade, 37.7% win, PF 1.80, max drawdown 9.9R, halves +0.293 / +0.751, control
−0.094, **z +3.31**. Shorts +32.4R (77), longs +29.4R (45). Every year positive but 2020 (−7.9R).

**Audit before the holdout** (build data only): no overlapping positions, no stop on the wrong
side, no fill outside its minute's range, every target exactly 3R, no exit before its fill. It holds
at +0.461 a trade when a limit must trade $0.50 **through** its level to fill, so it is not a
touch-fill artifact. ⚠ **But it is a ridge**: drop any one of its three settings and it goes flat
or negative — 1 counter BOS +3.1R, structure stop +5.1R, market entry −6.8R.

## The holdout — one run, 2018-09-14 → 2019-12-31

`python backtest/tools/rso_realign_study.py --holdout "15m c2+ fib50 atr2 t3"`

**14 trades, −5.5R, −0.393 a trade, 14.3% win, PF 0.53, control −0.128, z −0.65.**
The pick is abandoned.

⚠ Fourteen trades cannot prove the pattern dead either. But the rule was fixed before the run, and
a pre-declared check that fails is not re-run — that is the same shape as the Loaded Level scalp
pick the same morning (+48.1R in-sample, −1.5R on its holdout).

## The $$ entry — added after the results, exploration only

The user, asked what his "$$" line does: it is **structural liquidity** — for a short, the band
between the lower high and the lower high before it — and he uses it as **an area to enter, or a
target**. Never a filter. The target half was already in the grid (the counter push's starting
low). The entry half was not, so it was added as `--sl`:

- **Entry** — after the realign, a limit back at the counter push's high (the band's lower edge).
- **Stop** — past the lower high before it (the band's upper edge), or 2 × ATR.
- **Exits** — the same eight. 96 cells over 1m / 5m / 15m.

**Recall:** on image 1 the engine puts the older lower high at 4311.75 and price came back to the
counter push's high (4296.89) at 08:16 NY — the spike the user marked. On images 2, 3 and 5 price
never came back, so this is a second-chance entry, not a replacement for the realign.

`python backtest/tools/rso_realign_study.py --sl` →
`backtest/reports/rso_realign_study_sl/grid_puprime_ecn.csv`

| frame | trades a cell | best t | positive in both halves |
|---|---|---|---|
| 1m | 182–245 | +0.35 | 1 of 32 |
| 5m | 33–35 | +0.81 | 4 of 32 |
| 15m | 14 | +0.77 | too few to judge (floor is 30) |

- **On 1m the user's version (stop past the older lower high) loses in all 16 counter × exit rows**;
  the best is −0.003 R a trade.
- **0 cells qualify.** This was searched data, so even a positive result would only have been a lead.
- ✅ The declared grid above still reproduces exactly after these additions (diffed line for line).

## The higher-frame gate — 2026-09-16, and it does not help

The user's own name for the pattern is a realignment WITH the higher frame — *"the 15m might be
bullish and the 1m bearish, and when the 1m goes bullish"* — and the grid above never asked the
higher frame anything. Two gates, declared in the tool's docstring before any result, read off the
canonical engine on the gate frame (1m and 5m charts gate on the 15m, the 15m chart on the 1H; a
gate bar counts only once it has closed):

- **htf** — the gate frame's structure points the trade's way at the realign close.
- **intact** — ...and did on every gate bar from before the counter shift through the realign: the
  counter push was a pullback inside the higher frame's leg, never a break of it. (The
  break-then-realign case is the Realign bot's, measured in `strategies/python/realign/`.)

The user also asked to see the pattern **before costs** — `--free` zeroes spread, commission and
swap. Same bars, the same 384 cells per gate, the rule as drawn (market at the realign close,
structure stop) with its matched random control on every row whether or not it is a candidate:

| frame | gate | trades / month | as-drawn rows at z ≥ 2 (of 16) | mean z, raw | mean z, ECN | cells positive in both halves, ECN |
|---|---|---|---|---|---|---|
| 1m | none | 24 | 0 | −0.65 | −0.55 | 5 of 128 |
| 1m | 15m agrees | 14 | 0 | −0.63 | −0.41 | 7 of 128 |
| 1m | 15m intact | 14 | 0 | −0.61 | −0.52 | 7 of 128 |
| 5m | none | 4.7 | 0 | −0.15 | −0.19 | 3 of 128 |
| 5m | 15m agrees | 1.9 | 0 | −0.97 | −1.16 | 5 of 128 |
| 5m | 15m intact | 1.6 | 0 | −1.26 | −1.28 | 5 of 128 |
| 15m | none | 1.7 | 1 | +0.90 | +0.74 | 47 of 128 |
| 15m | 1H agrees | 0.8 | 0 | −0.36 | −0.64 | 37 of 128 |
| 15m | 1H intact | 0.8 | 0 | −0.37 | −0.53 | 33 of 128 |

- **On 1m the raw pattern IS its control.** At a 1R target it wins 50.2% and makes +0.009R a
  trade; random timing at the same month and hour makes +0.009R (z −0.03). The best of the eight
  exits, the structure trail, makes +0.058R against +0.021R random (z +0.91). There is nothing for
  costs to take — the pattern as drawn carries no direction on the 1m before a cent is charged.
- **The gate adds direction nowhere, and on 5m and 15m it subtracts it.** On the 15m the as-drawn
  rows average +0.089R a trade raw and +0.002R once the 1H must agree.
- **On 1m the two gates are the same gate:** 1,247 of the 1,249 short setups the 15m agrees with
  are also intact. A 1m counter push almost never breaks 15m structure, so "pullback inside the
  15m leg" is not a filter there.
- **Charged, every 1m as-drawn row is negative with or without the gate** (−0.001 to −0.059R).
- **No gated cell clears z 2 charged.** The 19 cells that do are the ungated 15m 2+ counter BOS,
  fib-0.5 limit, 2 × ATR family — the ridge that already lost its holdout above. Four 1m cells
  clear z 2 **uncosted** (a fib-0.5 limit with a **$1.39** 2 × ATR stop, +0.13–0.15R a trade):
  4 of 1,152 at z 2.0–2.2 is what a null search returns, and charged they read +0.02–0.07R.
- ✅ **The gate's sign is proven, not assumed.** On 313 setups (May–Sep 2026) the flag equals the
  engine's direction on the real, unmirrored 15m bars on every one, and the flipped sign mismatches
  every one. The user's 25 Aug long had the 15m BEARISH at entry — the gate refuses it; the 11 Aug
  long had it bullish.

Report: `backtest/reports/rso_realign_gate/grid_free.csv` and `grid_puprime_ecn.csv`. ⚠ Both runs
are on the searched 2020–2026 bars, so even a positive here would have been a lead, never a pick.

## The displacement rule, the shift-level retest and reward-to-risk at entry — 2026-09-16

The user's second image (two longs, 15 Sep 08:55 and 11:07 NY) and his refinement: *"if the candle
that closes for the realignment is not very far away it makes it a profitable trade and it has to
go all the way to the last high; if the candle closes extremely far from where the shift printed you
have to wait on some type of retracement back to the shift of structure."* Three things added to the
tool, declared before the run:

- **`retest`** — a limit AT the swing the realign SOS broke (the engine's own break price), structure
  stop, dying after 60 chart bars or on a close through the counter extreme, like the fib entries.
- **`disp`** — his rule as one entry: the close when it sits within 1 chart ATR of that level, else
  the retest (`--disp-atr`).
- **Two splits of the rule as drawn**, each bucket against its own matched random control: by how
  far the realign bar closed past the level (chart ATR), and — for the last-high target — by
  reward-to-risk AT ENTRY (distance to the last high ÷ stop distance).

**1m, his frame, one counter BOS, market at the close, raw:**

| realign close past the level | trades | at 1R | at 2R | last high | structure trail |
|---|---|---|---|---|---|
| under 0.5 ATR | 1,036 (63%) | +0.004 (z −0.07) | +0.026 (z +0.72) | +0.009 | +0.028 (z +0.59) |
| 0.5–1 ATR | 372 | +0.060 (z +1.26) | +0.103 (z +1.39) | +0.043 | **+0.174 (z +1.49)** |
| 1–2 ATR | 197 | −0.046 | −0.091 | −0.084 | +0.031 |
| 2 ATR and more | 31 | −0.107 | −0.087 | **−0.447 (z −2.32, 11)** | −0.171 |

| the last high at entry sits… | trades | win | raw avg R | charged avg R |
|---|---|---|---|---|
| under half a stop away | 564 (35%) | 78% | −0.023 (z −1.42) | −0.060 |
| half to one stop | 447 (27%) | 58% | +0.012 | −0.002 |
| one to two stops | 398 (24%) | 46% | **+0.078 (z +1.52)** | +0.034 (z +1.40) |
| two stops and more | 225 (14%) | 28% | −0.078 | −0.172 (z −1.26) |

- **The far close is a bad market entry, exactly as he said.** Over 1 ATR every exit is negative;
  over 2 ATR, aiming at the last high is the worst cell in the study.
- **But the near close is a coin flip**, not a profitable trade: 1,036 of them, +0.004R at 1R, the
  same as random timing. The best band is the MIDDLE one — a candle that shows some displacement
  — and it does not clear the bar (z +1.49 raw, +1.69 charged on the trail).
- **The retest does not rescue the far setups.** Every 1m retest row sits within ±0.03R of zero
  raw and every one is negative charged; the combined rule reads the same as the plain close
  (z ≤ +1.0 raw, all negative charged).
- **"The previous high is closer than the stop" is true of 62% of the mechanical fires**, and
  those are the ones he does not take. The ones he does — the high one to two stops away — make
  +0.08R raw and +0.03R charged a trade, 5 a month, and are not past the bar; two or more stops
  away, price reaches the high 28% of the time and the trade loses. **"It has to go all the way
  to the last high" is the claim the data refuses**: the further the high, the less often it is
  reached, and a fixed target there loses.
- **5m:** the near close makes +0.13R at 2R (189 trades, z +0.7–0.8); every other bucket and the
  retest are negative. **15m:** the near close +0.26R at 2R (61 trades, z +1.6); three 2+-counter
  retest cells clear z 2 raw (2.11–2.15) and none charged. The one bucket anywhere past the family
  bar is the last high UNDER half a stop away on the 15m — 35 trades, 91% win, +0.195R, z +3.79
  charged — 0.4 trades a month for about 1R a year, and the opposite of the trade asked about.
- The realign bar's displacement and the reward-to-risk at entry are the same lever seen from two
  sides: a far close is a bigger stop and a nearer target, which is why both splits agree.

✅ Every pre-existing cell reproduces exactly after each patch (max diff 0.0 on the 15m grid,
twice). Report: `backtest/reports/rso_realign_disp/grid_free.csv`, `grid_puprime_ecn.csv`. ⚠ Same
searched bars as everything above — a lead at most, never a pick.

## The cross-instrument test — 2026-09-16, failed 0 of 3

The user asked for the most effective way to trade the pattern and for more trades. Buying trade
count by loosening a rule has been measured to lose here (root CLAUDE.md, Run 12), so the honest
route to frequency is the SAME rule on more instruments. The one family that cleared z 2 on gold —
15m, 2+ counter BOS, fib-0.5 limit, 2 × ATR stop, 1.5R / 2R / 3R targets — had already failed its
gold holdout, so bars nothing had looked at were its only remaining test.

**Declared before a single bar was fetched** (tool docstring): PU Prime M1 for XAGUSD.p, EURUSD.p
and NAS100, 2020-01-01 onward, fetched through the lab's bar source with the floor measured per
symbol; run `--free` (costs are unmeasured off gold); PASS = that family positive in both halves and
z ≥ 2 against its matched control on 2 of its 3 cells, on 2 of the 3 instruments.

| instrument | M1 bars | t1.5 | t2 | t3 | both halves | z | verdict |
|---|---|---|---|---|---|---|---|
| gold (the build) | 2,371,706 | +0.315 | +0.406 | +0.533 | yes | +3.2 / +3.2 / +3.4 | in-sample; lost its holdout |
| silver | 2,371,703 | +0.072 | −0.006 | +0.072 | no cell | — | **fail** |
| EURUSD | 2,497,753 | +0.158 | +0.168 | +0.280 | all three | +1.47 / +1.69 / +1.87 | **fail** (under the bar) |
| NAS100 | 2,363,731 | −0.094 | −0.092 | −0.114 | no cell | — | **fail** |

- **0 of 3.** Silver's second half is negative on every cell; EURUSD shows the shape and never
  clears the bar; NAS100 is the opposite sign.
- Across each instrument's whole 576-cell grid: silver and EURUSD have **no** cell at z ≥ 2,
  NAS100 has three (z 2.13–2.18, three unrelated cells) — what a null search returns.
- **The user's 1m rule as drawn** is negative in all eight exits on silver (mean z −1.49) and
  EURUSD (−1.40); on NAS100 seven of eight are positive and none is past z 1.3.

Reports: `backtest/reports/rso_realign_xsym/<symbol>/grid_free.csv`. ⚠ The three new caches are
now looked-at data for this pattern.

## The breaker entry — 2026-09-16, fourth pass, failed

Two more of the user's 1m trades, both longs on 15 Sep 2026, and a different entry from everything
above. Long (a short mirrors):

1. A bullish BOS — the trend.
2. A bearish SOS, then **one bearish BOS** — the shakeout. That broken level is the future entry.
3. A bullish SOS — the realign. Price leaves.
4. **A limit back AT the level the bearish BOS broke.** Stop at the shakeout low. Target the high
   price made after the realign.

| | realign | breaker vs the user's entry | stop vs the user's | filled (NY) | result on PU Prime |
|---|---|---|---|---|---|
| trade 1 | 08:34 | −$0.45 | −$0.04 | 10:39, 2 hours later | +5.27R to the high |
| trade 2 | 11:06 | $0.00 | +$0.05 | **20:56, 10 hours later** | +20.47R to the high |

The detector finds both. Trade 2 only fills if the level stays valid for a day, so a 24-hour window
was declared, with the pass rule, before any 24-hour result was read: **1m, one counter BOS, the
breaker limit, structure stop, target the post-realign high. PASS = gold charged positive in both
halves at z ≥ 2, AND raw positive in both halves on 2 of silver, EURUSD and NAS100.**

| instrument | trades | a month | win | avg R | 1st half | 2nd half | random | z |
|---|---|---|---|---|---|---|---|---|
| gold, ECN | 1,109 | 13.8 | 23.9% | **−0.162** | −127.2R | −52.6R | −0.123 | −0.56 |
| gold, raw | 1,122 | 14.0 | 23.4% | −0.066 | −75.6R | +1.6R | +0.037 | −1.23 |
| silver, raw | 1,141 | 14.2 | 21.5% | −0.081 | −17.9R | −74.6R | +0.035 | −1.40 |
| EURUSD, raw | 1,286 | 16.0 | 23.4% | +0.125 | +200.8R | **−40.1R** | +0.011 | +0.79 |
| NAS100, raw | 1,134 | 14.1 | 23.9% | −0.054 | −55.5R | −6.1R | +0.040 | −1.34 |

**It fails every part of the rule.** Why, from gold's 1m trades before costs:

| the high sits, at the fill | trades | reached | avg R |
|---|---|---|---|
| under 1R | 80 | 45% | −0.098 |
| 1–2R | 176 | 39% | −0.016 |
| 2–3R | 161 | 30% | +0.083 |
| 3–5R | 194 | 23% | +0.201 |
| 5–10R | 245 | 11% | −0.080 |
| 10R and more | 266 | 4% | −0.360 |

- **His two examples, 5.3R and 20.5R, come from the two buckets where the high is reached 11%
  and 4% of the time.** Half of all fills sit 4.4R or more from the high.
- **The stop is the other half of it.** The median is $1.40. Stops under $2 reach the high 12–18%
  of the time and lose; stops of $2 and more reach it about 30% and break even before costs.
- **The 15m agreeing does not rescue it**: −0.066 → +0.005R raw, −0.162 → −0.237R charged.
- A four-hour window (read first, not declared): no breaker cell past z 2 on gold, silver or
  NAS100. EURUSD's 5m shows a handful at z 2.2–2.5 among hundreds of searched cells.

⚠ Both of the user's trades are real and both win on PU Prime's bars. The rule that finds them also
finds 13 losers a month for every one like them, so **the filter is the user's, and it is not in the
chart structure this tool reads.** Four weeks of the detector's setups, outcomes left out, for
the user to mark TAKE or SKIP: `backtest/reports/rso_realign_breaker/candidates_2026-08-17_to_09-16.csv`
(32 setups, 26 filled within a day).

### The target was misread — corrected the same day, and the rule still fails

The user, on the 27 Jul loser: the target is the **higher high of the trend leg** — after the first
bullish BOS and before the bearish shift — not the high made after the shift back, and "at least"
that. The engine agrees to the cent: its leg origin on 27 Jul is **4106.02**, where the table above
aimed at 4100.41. Both 15 Sep trades aimed higher than their trend-leg highs (4300.54 over 4286.77;
4310.71 over 4300.54), at the post-shift high, so the user's target is **the further of the two**.
Re-declared under the same cell and pass rule before any result with it existed:

| instrument | trades | win | avg R | 1st half | 2nd half | random | z |
|---|---|---|---|---|---|---|---|
| gold, ECN | 1,089 | 20.4% | **−0.102** | −71.8R | −39.6R | −0.099 | −0.03 |
| gold, raw | 1,102 | 19.8% | +0.039 | −13.4R | +56.5R | +0.025 | +0.14 |
| silver, raw | 1,126 | 16.8% | −0.119 | −33.4R | −100.9R | −0.050 | −0.78 |
| EURUSD, raw | 1,266 | 18.2% | +0.051 | +106.9R | **−42.6R** | +0.002 | +0.33 |
| NAS100, raw | 1,111 | 18.9% | −0.044 | −70.0R | +21.5R | +0.039 | −1.01 |

**Still a fail on every part of the rule.** The trend-leg high on its own reads −0.126R charged and
+0.028R raw on gold. ⚠ The random control is a fresh draw each run, so z moves a few tenths between
runs on identical trades.

Reports: `backtest/reports/rso_realign_breaker/<symbol>/` (four hours) and `<symbol>_24h/`.

## The user's full rule, built from four trades — 2026-09-16, fifth pass

After the target correction the user explained two more of their trades, and each explanation added
a branch. Every trade below reproduces on PU Prime's bars under the rule that followed it.

| trade | how the user took it | on these bars |
|---|---|---|
| 15 Sep long 1 | breaker limit, full stop ($4.55) | +5.41R to the post-shift high |
| 15 Sep long 2 | breaker limit 10 hours later, full stop ($1.59) | +22.01R |
| 27 Jul long | zone too big ($8.80): skip the first return, buy when price climbs back to the level, stop behind the little swing low (4092.41), 1:2 | +2.00R at 07:09 |
| 28 Jul short | sell at the shift itself, stop $4.79 above, target the trend-leg low 4040.36 | +1.26R at 01:00 |

**What decides the entry is the stop size in DOLLARS, not volatility.** Measured as a share of
price, every stop the user accepted is 0.118% or less and every one they refused is 0.215% or more.
In chart ATR the same stops do not separate (the 28 Jul close stop is 4.24 ATR and accepted; the
15 Sep trade 2 close stop is 3.54 and refused), and how far the shift candle closed past its level
does not separate them either (0.20 ATR taken at the close, 0.27 ATR waited).

**Two rules, each declared in the tool before its run** (1m, one counter BOS, 24-hour window, same
pass rule as above):

- **Conservative only** — a zone over 4 ATR gets the conservative entry, otherwise the breaker limit.
- **The ladder** — take the most aggressive entry whose stop is at most **0.16% of price** (about
  $7 at today's gold): the shift's close, else the breaker limit, else the conservative entry.

| rule | gold, ECN | gold, raw | random, raw | silver | EURUSD | NAS100 |
|---|---|---|---|---|---|---|
| conservative only | −0.136R (z +0.04) | +0.003R | +0.002R | −0.062R | +0.047R | −0.029R |
| the ladder | **−0.042R** (z +0.61) | +0.070R | +0.024R | −0.055R | −0.091R | −0.022R |

⚠ **Corrected the same day.** The first runs let the conservative entry use ANY intact swing low,
and 41 of 168 conservative stops ran wider than the rule allows (one $44 on 5 Apr 2026). The
user's conservative stop exists to be tight, so a swing now counts only inside the zone it replaces
(conservative only) or inside the 0.16% maximum (the ladder). The table is the corrected run; the
first read −0.133R / −0.050R after costs. Only the conservative rows moved.

The raw figures for silver, EURUSD and NAS100 are before costs.

- **Both fail.** After costs both lose in both halves, and neither beats random timing.
- **The ladder is the best version so far** — 33% win, 14.3 trades a month on gold — and before
  costs it is positive in both halves. But random entries with the same stops and targets make
  +0.024R against its +0.070R, so the setup adds little to where the stop and target sit.
- ⚠ Found after the ladder's run: both 28 Jul entries sit on the shift LEVEL on the user's feed
  (4046.36 against a 4046.60 level and a 4046.38 close; 4046.15 against 4046.16 and 4045.54), so the
  ladder's "sell at the close" is an approximation of a limit at the level. Not re-run — its one test
  on these bars is spent.

### The second realign — the user's alternative strategy, same day, fails

On the 28 Jul short the user proposed another strategy on the same setup: **wait for price to break
back through it** (above the shakeout high 4051.17, first at 02:40), **then sell the next bearish
shift** (04:10, level 4046.16), stop above the high made since the break (4055.26), target 3R.
Declared before the run: a limit at the new shift's level (where both 28 Jul entries were drawn),
dying after an hour or on price through the stop, 3R. It reproduces the example: filled 04:11 at
4046.16, 3R (4018.86) at 06:23.

| 1m, one counter BOS | gold, ECN | gold, raw | random, raw | silver | EURUSD | NAS100 |
|---|---|---|---|---|---|---|
| **3R (declared)** | **−0.010R** (808, 36% win, z +0.26) | +0.039R | +0.033R | −0.065R | −0.050R | −0.086R |
| 2R | −0.009R | +0.033R | +0.022R | −0.038R | −0.063R | −0.079R |
| 1R | −0.020R | +0.003R | +0.029R | −0.025R | −0.032R | −0.044R |
| the lower low or further | +0.013R (z +0.95) | +0.052R | +0.004R | −0.096R | −0.046R | −0.061R |
| sell at the shift's close, 3R | −0.030R | +0.008R | +0.011R | −0.046R | −0.066R | −0.086R |

The raw figures for silver, EURUSD and NAS100 are before costs.

- **It fails:** gold's first half loses (−45.6R after costs, −13.4R before), no instrument beyond
  gold is positive, and every row sits on its random control.
- **It is the nearest to breakeven of anything tried**, about 10 trades a month. The lower-low target
  is the one row positive after costs on gold (+0.013R) — reported, not picked; its first half loses.
- On 5m and 15m it fires about once a month or less, too few to read.

**The pattern across every pass: each version lands on its own random control.** Wherever the stop
and target are placed, random moments with the same stop and target make about the same. The
structure decides WHERE the stop and target sit; on these bars it does not decide WHEN price moves.

### Time of day, the time limit and weekends — before costs, same day

The user asked whether the time limit is cutting winners, and which sessions lose. Gold 1m, before
costs, by the time the order FILLED (New York), with the time limit the tests used (500 minutes).

| the time limit | full rule | second realign 1:3 | second realign, lower low |
|---|---|---|---|
| trades it closes | 3% (97% of them green) | 34% (71% green) | 22% (70% green) |
| win rate, 500 min / 24 h / 3 days | 33.7% / 32.2% / 32.2% | 37.1% / 28.3% / 27.0% | 46.3% / 41.2% / 40.5% |
| avg R, 500 min / 24 h / 3 days | +0.070 / +0.090 / +0.103 | +0.039 / +0.003 / +0.027 | +0.052 / +0.000 / +0.026 |

- **The limit barely touches the full rule**, and letting its few open trades run adds a little.
- **For the second realign the limit PROPS UP the win rate**: most trades it closes green would have
  gone on to the stop. Its 37% at 3R is 27% without the limit.
- **Weekends:** the full rule held 9 trades over a weekend for −35.4R, almost all from ONE trade —
  25 Feb 2022, a short with an 82-cent stop that reopened $33 through it (−40.4R). Without weekend
  holds it averages +0.101R. The second realign's weekend holds made money (worst −1.0R).

| full rule by session, no weekend holds | trades | win | avg R |
|---|---|---|---|
| Asia | 392 | 35.7% | −0.017 |
| London, before New York | 274 | 35.4% | +0.095 |
| London and New York together | 284 | 26.4% | +0.227 |
| New York, after London | 150 | 32.7% | −0.035 |
| between the New York close and Asia | 56 | 50.0% | +0.688 |

- The full rule's worst hours: 01:00 (−22.8R over 59 trades), 03:00 (−16.3R), 23:00 (−13.7R);
  its worst days Tuesday (−26.0R) and Friday (−16.2R).
- The second realign at 1:3 loses in **London before New York** (206 trades, 27.2% win, −0.100R),
  worst at 04:00 and 05:00.
- ⚠ **None of these differences is past noise.** A session holds 150–400 trades and an hour 20–100,
  so a bucket's average moves ±0.2 to ±0.4R by chance. They are places to look on a chart, not
  filters — adopting one would be a new search on bars already used eight times.

Every trade, with its session and result (nothing on or after 17 Aug 2026, so the marking list stays
blind): `backtest/reports/rso_realign_breaker/trades_by_session_2020-01_to_2026-08-16.csv`.

### Flat over weekends, and a stop cap on the second realign — the user's two decisions, same day, both fail

The user decided: nothing is held over a weekend, and the second realign skips a stop that is too
big. A trade now closes at the last bar before any market closure longer than 12 hours (the daily
break is not one), and an unfilled order dies there. The second realign's cap was declared at
0.30% of price before any run (their own 28 Jul trade had 0.225%); 0.16% and 0.50% are reported,
never picked. Both switches are off by default and change nothing when off.

| before costs, 1m, 24h, flat over weekends | trades | a month | win | win needed | avg R | 1st half | 2nd half |
|---|---|---|---|---|---|---|---|
| full rule, gold | 1,161 | 14.5 | 33.9% | 31.0% | +0.096 | +0.080 | +0.110 |
| full rule, silver | 963 | 12.0 | 18.0% | 19.4% | −0.075 | −0.230 | +0.068 |
| full rule, EURUSD | 1,675 | 20.9 | 48.4% | 53.8% | −0.098 | −0.177 | −0.029 |
| full rule, NAS100 | 1,047 | 13.0 | 29.1% | 30.5% | −0.046 | −0.164 | +0.056 |
| second realign 1:3, gold | 497 | 6.2 | 29.6% | 32.2% | −0.080 | −0.101 | −0.060 |
| second realign 1:3, silver | 219 | 2.7 | 23.3% | 27.9% | −0.171 | −0.071 | −0.264 |
| second realign 1:3, EURUSD | 854 | 10.6 | 33.0% | 35.0% | −0.054 | +0.062 | −0.165 |
| second realign 1:3, NAS100 | 399 | 5.0 | 25.3% | 30.0% | −0.154 | −0.288 | −0.052 |

- **Flat weekends lift the full rule on gold** from +0.070R to +0.096R a trade, but random entries
  at the same month and hour, with the same stop and target, make +0.035R (z +0.82). Charged (ECN)
  it is −0.012R, both halves negative. It fails on the other three instruments.
- **Both decisions make the second realign worse.** Its weekend holds were making money (+19R),
  and the stops the cap removes were its better trades. On gold at 3R: no cap −0.010R, cap 0.50
  −0.010R, cap 0.30 −0.080R, cap 0.16 −0.041R. Charged at cap 0.30: −0.137R, z −1.21.
- **FAIL on the pass rule for both**: gold charged is not positive in both halves at z ≥ 2, and
  no other instrument is positive in both halves before costs.

## What this leaves

- 🔴 **Both periods are spent for this pattern.** Never test another cell on 2018-09-14 →
  2019-12-31, and never treat 2020–2026 as fresh.
- ⚠ **That window is also the test set `backtest/tools/structure_patterns.py` reserves** (built the
  same day, test mode never run). None of its strategies was tested here, but the window has now been
  looked at for a structure-sequence idea — any result it produces there should say so. That study
  also found none of 1,424 structure sequences on 5m gold beat its luck bar, which points the same
  way as this one.
- **The tool finds the user's 1m trades to the minute, so the definition is not what is missing —
  their discretion is.** The next input is their losing and skipped setups, compared against the
  tool's candidates, or a forward journal of every realign they take or pass on and why.
- A revived rule needs new data: that journal, or forward results on the demo account.
- **The higher-frame gate is not the missing filter** (2026-09-16, above). The 15m agreeing —
  or holding intact through the pullback — removes half the setups and none of the noise.
- **Neither is the displacement of the realign candle, nor a retest of the shift level** (2026-09-16,
  above). A far close is a bad entry, a near close is a coin flip, and the retest adds nothing.
- **The gold family does not carry to silver, EURUSD or NAS100** (2026-09-16, above). The only
  realignment that pays on this repo's data is the Realign bot's — the higher frame FALSE-BROKEN
  and the lower frame realigning — `strategies/python/realign/`, and its next step is the parity
  gate, not another pass on this pattern.
- **The breaker entry is not it either** (2026-09-16, above). The detector finds the user's trades to
  the cent; the user's marks on the four weeks of candidates are the only input left that can find the filter.
- **Nor the stop-size ladder or the second realign** (2026-09-16, fifth pass). Every version
  lands on its random control. Eight passes on 2020–2026 gold: the bars are exhausted for this pattern.
