# RSO Realign — the user's 1-minute retail shake-out, measured

**Status:** 🔴 **MEASURED 2026-09-14 — NO MECHANICAL EDGE. The one clean check is SPENT.**
**2026-09-16:** the higher-frame gate the user's own name for the pattern implies — measured raw
and charged, on every frame: **it does not help, and on 5m and 15m it hurts** (section below).
**2026-09-16, second pass:** the user's displacement rule, the shift-level retest and reward-to-risk
at entry — **the far close is a bad entry as he said; nothing else in it clears the bar** (below).
**2026-09-16, third pass:** the gold family on silver, EURUSD and NAS100 — bars nothing had looked
at — **failed 0 of 3** (below). The pattern is measured out on this repo's data.
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
