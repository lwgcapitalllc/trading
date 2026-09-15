# RSO Realign — the user's 1-minute retail shake-out, measured

**Status:** 🔴 **MEASURED 2026-09-14 — NO MECHANICAL EDGE. The one clean check is SPENT.**
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
