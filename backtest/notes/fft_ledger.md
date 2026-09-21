# FFT ledger — every combination of the user's FFT setup, measured

**What this is:** the running record of the user's manual FFT (first fib touch) combinations, kept
while they tune the approach (the user, 2026-09-21: *"keep all profitable results in history while
we tweak"*). Profitable combinations are listed first; the ones that failed stay below so nobody
re-tests them. The tool and its method: `backtest/tools/fft_first_touch_study.py` and its entry in
`notes/tools.md`.

**How to read a row.** All before costs, PU Prime gold M1. **dev** = 2020-01 → 2025-08, **recent**
= 2025-09 → 2026-09-16 (both already looked at many times — a lead, never a proof). **b/e** =
the break-even win rate for that stop and target, which is also what random entries score. **avgR**
= average result per trade in units of the stop. The 2018-09 → 2019-12 test set is SPENT (one run,
2026-09-21, below).

**Every row carries the base rules:** 15m + 5m trend with the trade, 1m against it with no 1m break
in the trade's direction since the 5m leg's extreme, first touch only, no setup whose leg spans a
weekend. "0 BOS" = the first pullback after the 5m shift (SOS); "≤1 BOS" = that or the next leg.

**Fills.** A 61.8 limit fills on the touch (stops are ~$5, the touch barely matters: $0.10 through
moves it by 1-2 points). A sniper limit fills only once price trades **$0.10 through** it — its
stops are ~$1, and a touch fill inflated it by 6 points.

## Profitable in BOTH windows

| Combination | Target | dev: n, win vs b/e, avgR | recent: n, win vs b/e, avgR |
|---|---|---|---|
| 61.8 entry, stop 1.0, 0 BOS | TP2 38.2 | 157, 71.3% vs 61.8%, +0.15R | 30, 73.3% vs 61.8%, +0.19R |
| 61.8 entry, stop 1.0, 0 BOS | TP1 50 | 157, 80.9% vs 76.4%, +0.06R | 30, 86.7% vs 76.4%, +0.13R |
| 61.8 entry, stop 88.6, 0 BOS ($0.10 through) | TP2 38.2 | 145, +0.19R | 30, +0.13R |
| 61.8 entry, stop 88.6, 0 BOS ($0.10 through) | TP1 50 | 145, +0.05R | 30, +0.10R |
| Sniper overlapping 61.8-88.6, ≤1 BOS | TP2 38.2 | 238, 26.5% vs 22.9%, +0.36R | 54, 27.8% vs 25.4%, +0.17R |
| Sniper overlapping 61.8-88.6, ≤1 BOS | TP1 50 | 238, 34.5% vs 35.8%, +0.12R | 54, 44.4% vs 40.7%, +0.13R |
| Sniper overlapping 61.8-88.6, 0 BOS | TP1 50 | 115, 43.5% vs 40.4%, +0.21R | 30, 50.0% vs 41.1%, +0.09R |
| Sniper entry at 0.702-0.786 of the FFT, any BOS | TP2 38.2 | 110, 17.3% vs 14.4%, +0.15R | 18, 22.2% vs 15.6%, +0.50R |
| 61.8 touch → wait for the 1m break back → enter, stop at the extreme since the touch; first leg | TP2 38.2 | 27, 48.1% vs 36.3%, +0.51R (random +0.21R) | 4, 4 wins, +1.32R |

⚠ **The one row that met the spent test set:** 61.8 entry, stop 1.0, 0 BOS — 2018-09 → 2019-12, 31
trades: TP1 74.2% vs 76.4% (−0.03R, **failed**), TP2 67.7% vs 61.8% (+0.10R). So TP2 on the first
leg is positive in all three windows; TP1 is not.

## Profitable in dev only (recent did not confirm)

| Combination | Target | dev | recent |
|---|---|---|---|
| Sniper starting at/past 61.8, 0 BOS | TP1 50 | 68, 36.8% vs 27.5%, +0.40R | 20, 30.0% vs 29.2%, −0.07R |
| Sniper entry at 0.702-0.786, 0 BOS | TP1 50 | 21, 42.9% vs 19.6%, +1.11R | 5, 1 win, −0.17R |
| Sniper overlapping 61.8-88.6, 0 BOS | TP2 38.2 | 115, +0.47R | 30, −0.06R |
| 61.8 entry, any BOS (the original rule, before the weekend rule), sells | TP1 50 | 269, 81.4% vs 76.4%, +0.07R | 45, 68.9%, −0.10R |

## Refinements — five ideas fixed BEFORE testing (2026-09-21)

Judged on dev, kept only if recent agreed with the SAME cut-offs (thirds of dev). Tested on both
profitable models: A = 61.8 entry, stop 1.0, first leg; B = sniper overlapping 61.8-88.6, ≤1 BOS.

- **1m confirmation entry — KEEP (per trade).** After the 61.8 touch, wait for the 1m to break back
  in the trade's direction, enter at that minute's close, stop at the extreme since the touch. Stop
  roughly halves ($3.34 vs $6.02). TP2 +0.51R per trade vs +0.15R for the plain limit. ⚠ It fires on
  only 27 of 157 setups (17%) — TP1 often prints before the 1m breaks — so in TOTAL it made +13.8R
  vs +23.6R for the limit over dev. Better per trade, fewer trades. Recent: 4 of 30, all won.
- **TP3 (back to the old high) — NO.** A: +0.07R, the same as random, below TP2's +0.15R. B: dev
  +0.42R but recent +0.11R, below random.
- **Impulse strength (5m leg / 5m ATR14) — NO.** No consistent order: A's middle third is worst in
  both windows but not monotonic; B's strong third is middling in dev and worst in recent (−0.60R).
- **15m discount vs premium — NO.** Dev: A discount +0.18R / premium +0.09R; recent reverses
  (+0.15R / +0.35R). B: no difference in dev.
- **Pullback speed — NO.** A: slow pullbacks best in dev, worst-but-one in recent. B: the reverse.
- Time-of-day filters were NOT re-tested: they failed on gold three times already in this repo.

## Scale-in — half on the 61.8 limit, half added on the 1m confirmation (2026-09-21)

Frozen before the run: one trade's risk split 50/50, never layered on top; first-leg setups.
R per setup in units of one full trade risk; max DD = deepest run of losses in R.

| Plan | Target | dev: total R, max DD, total/DD | recent: total R, max DD, total/DD |
|---|---|---|---|
| All on the 61.8 limit | TP2 | +24.2R, 3.8, 6.3 | +5.6R, 3.8, 1.5 |
| Scale-in 50/50 | TP2 | +19.0R, 2.8, **6.9** | +5.4R, 1.9, **2.9** |
| All on the 61.8 limit | TP1 | +9.2R, 3.9, 2.4 | +4.0R, 2.4, 1.7 |
| Scale-in 50/50 | TP1 | +10.9R, 2.0, **5.4** | +3.6R, 1.2, **3.0** |
| All on the confirmation only | TP2 | +13.8R (27 trades), 4.7, 2.9 | +5.3R (4 trades), 0, — |

**Reading:** at the same risk budget the scale-in makes a little LESS in total on TP2 (it uses only
59% of the risk on average — the half that waits for a confirmation that comes 1 time in 6), but
it cuts the deepest losing run by a quarter to a half, so return per unit of drawdown is better in
both windows, on both targets. Worth it only if the freed room is spent on size. ⚠ The added half
rests on 27 + 4 confirmations.

## Which 15m leg — 15m continuation BOS since its shift, crossed with the 5m leg (2026-09-21)

`--legs15`. TP2 avgR, dev / recent (n in brackets).

- **Model A with the 5m first leg — the 15m leg adds NOTHING.** 15m any +0.15 (157) / +0.19 (30); 15m
  first leg +0.12 (100) / +0.08 (12); 15m 3+ BOS +0.25 (22) / +0.13 (10). The 5m first leg already
  does the work; keep 15m "any leg" (trend aligned).
- **Model A on ANY 5m leg — early 15m legs help, both windows agree.** 15m at most 1 BOS +0.12 (355) /
  +0.04 (53); 15m 2+ BOS about 0 (217) / about −0.06 (43). Only relevant if the 5m leg is not filtered.
- **Model B (sniper) — no pattern.** 15m first leg +0.58 in dev (125) but −0.12 in recent (21); 1 BOS
  −0.34 / +0.04; 2 BOS +0.65 / +1.42 (4). A zigzag — not a filter.

## The clock — sessions, kill zones, session opens, news (2026-09-21)

`--clock`, on the canonical sessions and news engines (MPC kill zones: 10:00-11:00, 11:45-12:15,
13:00-13:30 NY; news = USD high impact ±30 min). Model A, TP2 avgR, dev / recent (n). Recent has 30
first-leg setups, so most buckets hold 1-9 trades — read the ANY-leg rows for size.

- **Kill zones — do NOT help.** Any leg: in a kill zone +0.00 (66) / −0.13 (13) vs outside +0.08 (506)
  / +0.01 (83). First leg: +0.23 (21) / −0.31 (7) — disagree.
- **First hour after the London open — the one consistent "avoid" on any leg:** −0.24 (32) / −0.39 (8).
  On the first leg it is +0.62 on 5 + 2 trades, so it does not touch the recommended plan.
- **News — no blackout needed.** Any leg, within 30 min of a USD release: +0.17 (40) / +0.16 (7); quiet
  days +0.07 / +0.07.
- **Sessions — nothing robust.** NY afternoon (NY only, after the London close) is positive in both on
  both legs but on 13 / 9 first-leg trades; the London/NY overlap flips sign.
- In line with the repo's three earlier gold time studies: time of day is not where this edge lives.

## Second touch and liquidity sweep (2026-09-21, `--second-sweep`)

**Second touch, first leg** (price back at 61.8 after the first touch reached TP1). Dev: 74 at 77.0% to
TP2 (+0.25R), recent 13 at 53.8% (−0.13R). ⚠ 50 of 74 / 9 of 13 come while the first trade is still
open — taking them doubles the risk on one leg. **Only when flat:** 24 at +0.21R / 4 at +0.21R; the
plan with it: TP2 +29.3R vs +24.2R (DD 4.8 vs 3.8) dev, +6.5R vs +5.6R (DD same) recent. A small
add, on 28 trades.

**Liquidity sweep** (a day / session / H4 level on the pullback side taken between the 5m extreme and
the fill). **It lifts the TP1 hit rate in both windows:** first leg 85.9% vs 77.4% no sweep (dev, 64 vs
93), 100% vs 80% (recent, 10 vs 20); any leg 83.1% vs 76.6% / 84.6% vs 68.6%. To TP2, first leg: +0.16R
vs +0.15R dev, +0.29R vs +0.13R recent — never worse. The swept level sitting at/past 61.8 adds
nothing (10 / 3 trades). About 4 in 10 first-leg setups have a sweep.

## The bot (2026-09-21, `strategies/python/fft/`)

**Built and matched to this study trade for trade** (`strategies/python/fft/tools/compare_study.py`):
157/157 trades and 2,644/2,644 first touches 2020-25, 34/34 and 494/494 in the last year. One
position at a time costs nothing (0 of 191 trades overlap; median trade ~1 hour). Through PU Prime
ECN with bid/ask fills: **+0.149R a trade over 152 (2020-25), +0.136R over 34 (last year).** Risk 5%
a trade (the user). Not deployed yet.

## Version 1 through real costs, and on silver (2026-09-21, `--v1`)

**Gold, PU Prime ECN** ($0.12 spread on a BID chart — a buy limit fills only when the ask reaches
61.8, a sell's stop and target trigger a spread early — $1/side/lot commission, swap per 17:00 NY
rollover). TP2: dev 152 trades, 71.1%, **+0.149R → +0.140R after costs** (0.009R a trade), total
+21.3R, max DD 3.9R; recent 29 trades, 72.4%, **+0.172R → +0.165R**, total +4.8R, DD 4.0R. 5 buy
limits in dev never reached by the ask. **Costs barely touch it** — the stop is ~$6-16, so $0.14 of
spread and commission is under 0.01R. TP1 after costs: +0.030R / +0.128R.
⚠ Recent year by half: 13 trades at 92.3% then 17 at 58.8% (−0.05R) — too few to call, watch it.

**Silver (XAGUSD.p, all of 2020-01 → 2026-09, new data for this rule, COST-FREE — silver's costs are
unmeasured and gold's may not be borrowed):** 179 trades, TP2 63.7% vs 61.7% break-even, **+0.03R**
(random −0.03R); first half +0.08R, second half −0.01R; the sweep adds nothing (+0.01R). **Barely
positive before costs — silver does NOT confirm the gold edge.** On a ~$0.16 silver stop any real
spread likely turns it negative. Either the edge is gold-specific or gold's +0.15R is partly luck.

**What version 1 is worth on gold:** ~2.3 setups a month × +0.14R ≈ +4R a year after costs, against
a worst drawdown of ~4R. Real but small — about one year of profit per worst drawdown.

## Setup frequency and what a bad run looks like (plan A, first leg)

2.4 setups a month in dev, 2.7 recent. Longest losing streak 3 (both windows, TP2). Worst drawdown
3.8R (both). Losing months: 20 of 61 in dev, 3 of 10 recent — about one month in three. Plan for
twice the measured drawdown before costs and small-sample error: ~8R.

## Tested and NOT profitable — do not re-test

- **5m 3+ BOS since the shift** (sniper, overlapping 61.8-88.6): dev −0.32R, recent −0.37R. Late legs lose.
- **Sniper zone starting BEFORE 61.8** (entry 0.5-0.618): dev −0.11R, recent −0.12R.
- **Exactly 1 BOS on the 61.8 entry:** below break-even in both windows (72.7%, 65.2%).
- **Break-even stop at TP1:** never beat simply holding to TP2, on either entry.
- **70.2 entry instead of 61.8:** fills 56% of setups, no better.
- **5m FVG in the zone:** adds nothing.
- **Original rule, buys only** (61.8, any BOS, TP1): 76.0% vs 76.4%.
- **Sniper wholly inside 61.8-70.2:** never happens — off one swing low the zone is wider than the band.
- **Sniper, touch fill:** every sniper row lost 5-10 win-rate points once a fill needed $0.10 through.

## The game plan as it stands (2026-09-21) — the checklist

1. **15m** — trade only in its trend direction (its last break). Any 15m leg.
2. **5m** — the FIRST leg after the 5m shift (SOS) in that direction. Once the 5m has made another BOS, stop looking.
3. **1m** — trending against you at the touch, with no 1m break in your direction since the 5m leg's high/low.
4. **No weekends** — skip a setup whose leg crosses a weekend.
5. **Entry** — limit at 61.8 on the FIRST touch. **Stop** at 100 (the fib's 1.0).
6. **Target** — TP2 (38.2). Do not move to break-even at TP1.
7. **Optional** — half size at 61.8, add the other half when the 1m breaks back (stop under the pullback low).
8. **Any session, kill zone or news time** — none of them improved it.
9. **A+ grade** — a day / session / H4 low (buys) swept on the way into 61.8. Take both; the swept ones hit TP1 more often.
10. **Second touch** — only when the first trade is closed; never add to an open one.

## What the numbers say to adjust (2026-09-21)

1. **Trade the first leg after the 5m shift; skip after 3+ BOS.** The only direction both windows agree on.
   The 15m leg count adds nothing on top of it — keep the 15m to "trend agrees", any leg.
2. **Highest win rate:** the 61.8 entry on the first leg to TP1 — ~80-87%, but each win is only 0.31 of the stop.
3. **Best return per trade that held twice:** the sniper zone overlapping 61.8-88.6 on the first or
   second leg, held to TP2 — ~27% win rate, +0.17 to +0.36R.
4. **Hold to TP2 rather than moving the stop to break-even at TP1** — and not on to TP3.
5. **Waiting for the 1m to break back after the 61.8 touch** triples the return per trade but takes
   one setup in six. Filters on impulse size, 15m discount and pullback speed added nothing.
6. Costs are still owed: on a ~$1 sniper stop the spread alone is ~0.1R per trade.
