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
the fill). 🔴 **SUPERSEDED — the label behind these figures counted levels that were already taken, and
the touch minute past the fill** (found and fixed 2026-09-21; see *The sweep label, corrected*). As
first measured: first leg TP1 85.9% vs 77.4% (dev, 64 vs 93), 100% vs 80% (recent, 10 vs 20); TP2
+0.16R vs +0.15R dev, +0.29R vs +0.13R recent. The "swept level at/past 61.8" rows (10 / 3 trades)
were the look-ahead itself and do not exist on the corrected label.

## The bot (2026-09-21, `strategies/python/fft/`)

**Built and matched to this study trade for trade** (`strategies/python/fft/tools/compare_study.py`):
157/157 trades and 2,644/2,644 first touches 2020-25, 34/34 and 494/494 in the last year. One
position at a time costs nothing (0 of 191 trades overlap; median trade ~1 hour). Through PU Prime
ECN with bid/ask fills: **+0.149R a trade over 152 (2020-25), +0.136R over 34 (last year).** Risk 5%
a trade (the user). Not deployed yet.

**Added 2026-09-21:** the "Skip after 4+ 15m BOS" setting, **off** (the user's call). The gate now
also matches the 15m BOS count (2,644 / 2,644 and 494 / 494) and the corrected sweep label (the same),
and with the setting on the bot takes exactly its trades minus the 4+ ones: 146 = 157 − 11, and
26 = 34 − 8, the study's own counts. `strategies/python/fft/tools/forward_log.py` grades all three
leads on any window of demo trades by replay; on the last year it reproduces lead 1's 8 (5 won) and
lead 2's +0.8R.

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

## The pullback's path into the 61.8 (2026-09-21, version 1, cost-free, TP2)

- **A small bounce off the 50%** (≥ 0.05 of the leg) before the 61.8: in 55% of losers vs 62% of
  winners; better in 2020-25 (+0.230R vs +0.066R), worse last year (+0.103R vs +0.213R). No signal.
- **A deep bounce off the 50% back to the 38.2** before the 61.8: in 42% of losers vs 33% of winners,
  and WEAKER IN BOTH WINDOWS — 49 trades +0.090R vs +0.196R (2020-25), 19 trades +0.022R vs +0.294R
  (last year). A LEAD, not proven: those trades are still positive, so skipping them lowers the total
  (21.2R vs 24.2R; 4.4R vs 4.8R). Candidate for a B grade, not a filter.
- **A sniper zone wholly in front of the 61.8** on a first leg: 3 of 191 trades. Explains nothing.
- **Trade 2026-02-04 21:14 NY (buy, loss)**, which the user would have skipped: 15m had 4 continuation
  BOS (median 1), the entry sat at 0.82 of the 15m fib (94th pct) and the 5m leg's START sat at 1.13 of
  the 15m fib (97th pct). The first two were already tested and did not help; the leg-start depth has
  not been. Awaiting the user's exact definition before any test.

## The user's "overextended trend, deep dive, then shift" pattern (2026-09-21, frozen before the run)

From the user's chart of the 2026-02-04 21:14 NY loss: the 15m made 4 bullish BOS, dipped through its
protected low without a 15m close below (an "almost SOS"), the 5m shifted bullish, the FFT buy failed,
and the 15m then shifted bearish. Rule: 15m continuation BOS since its shift ≥ N AND the 5m leg's
start at/through the 15m fib's 1.0 (or past its 88.6). Version 1 trades, TP2, cost-free.

| flag | 2020-25 flagged | skip → rest | last year flagged | skip → rest |
|---|---|---|---|---|
| 15m ≥ 4 BOS alone | 11, 55%, −0.118R | 146, +0.175R, +25.5R total (vs +24.2) | 8, 62%, +0.011R | 26, +0.182R, +4.7R (vs +4.8) |
| 15m ≥ 3 BOS alone | 22, 77%, +0.250R | worse | 10, 70%, +0.132R | flat |
| dive through the 15m 1.0 alone | 83, 76%, +0.228R | worse | 14, 64%, +0.040R | better |
| ≥ 4 BOS + through the 15m 1.0 | 6, 50%, −0.191R | 151, +0.168R, +25.3R | 2, 50%, −0.191R | 32, +0.163R, +5.2R |
| ≥ 4 BOS + past the 15m 88.6 | 10, 50%, −0.191R | +26.1R | 4, 75%, +0.213R | +4.0R |

**Reading:** the part that holds is the OVEREXTENSION — 4+ 15m BOS is weak in both windows (19
trades, ~58% win). The deep dive is not a warning on its own: more than half of all first legs start
at or through the 15m low, and in 2020-25 those did better. Not proven (z ≈ −1.2 on 19 trades), but
skipping 4+ BOS costs nothing measurable in total R. Earlier `--legs15` split at ≤1 vs 2+ and missed it.

## Mining the losers (2026-09-21, frozen before the run, version 1, cost-free)

- **Anatomy:** 15 of 45 losers 2020-25 (33%) touched TP1 first and then turned to the stop; 5 of 10
  last year.
- **Exits on every trade** (avgR / total / worst DD / total per DD): TP2 +0.154 / +24.2R / 3.8 / 6.3
  and +0.142 / +4.8R / 3.8 / 1.3 — TP1 +0.059 / +9.2R / 3.9 / 2.4 and +0.116 / +4.0R / 2.4 / 1.7 —
  half at TP1 + half to TP2 +0.106 / +16.7R / 3.1 / 5.4 and +0.129 / +4.4R / 2.9 / 1.5 — half at TP1 +
  rest at break-even +0.052 / +8.1R and +0.130 / +4.4R. **TP2 stays**; half-and-half smooths the curve
  a little and gives up a third of 2020-25's profit.
- **Feature scan** — 12 entry-time features × (skip, or TP1 instead of TP2), luck bar from 2,000
  shuffles, 24 tests so ~1.2 false passes expected. **One passed: Asia entries (18:00-02:59 NY) →
  take TP1**, +2.1R on 37 trades (p 0.02) and +0.8R on 8 last year. One pass is what luck alone
  gives; a lead only (plausible: Asia's range is smaller). **15m ≥ 4 BOS → skip: +1.3R, p 0.08, and
  −0.1R last year — did NOT clear the bar.** Every other feature cost R as a skip.
- The 55 losers, with levels and flags, were listed for the user to review on the chart.

## ⚠ Five results below were re-run with the reopen clip working (2026-09-21)

Round 2, the 03-27 pattern, "with the sweep", the 23.6 target and the other-market test first ran
under pandas 3, where `clean_reopens` silently clipped nothing (backtest/notes/tools.md). Re-run with
it working: gold 2020-25 has 157 trades (156 without the clip), every figure moved by at most ~1R,
and every verdict held. The figures below are the re-run's; the side-flipped accidental run was not
re-run and is marked as such.

## Mining the losers, round 2 — sniper position, day, the 1-hour (2026-09-21, frozen, cost-free)

10 more features × (skip, or TP1 instead), 5,000 shuffles; 20 tests (~1 false pass expected), 44
loser tests this session. **No leads.** Share of 2020-25 losers vs winners carrying each:

- 5m sniper zone overlapping 61.8-70.2: 69% vs 68% — wholly deeper than 70.2: 31% vs 31% — shallower
  than 61.8: 0% vs 1% — every setup had a same-side zone. Last year deeper-than-70.2 was 5 of 10
  losers vs 17% of winners (skip +2.5R), but it costs −7.6R over 2020-25 — noise on 10 losers.
- 1h trend against the trade: 33% vs 41% (a skip costs −13.4R) — 1h trend with it on 3+ BOS: 7% vs
  6% — entry in the wrong half of the 1h leg: 51% vs 53%.
- A 1h leg's high/low between the entry and TP2: 1 trade in 190 — the 1h leg's end almost always sits
  past the 5m extreme, so this could not be judged. It checks the 1h leg's ends only, not every 1h swing.
- Monday 13% vs 12%, Friday 20% vs 26%.
- Every skip lost R over 2020-25. The losers carry nothing the winners do not.

## The user's 2026-03-27 10:03 sell — a strong 5m counter-run, then one shift (2026-09-21, frozen)

The user's read of the loss: the 15m bearish on 4 BOS; the 5m had turned UP and made 3 bullish BOS;
one bearish shift; the FFT sold its first leg and lost. The count was checked against the chart: the
engine reads 3 prior 5m BOS and 15m 4 BOS on this trade, as the user did. Version 1, TP2, cost-free.

- **By the prior 5m run's BOS count** (n / win / avgR): 2020-25 0: 61 / 77% / +0.25 — 1: 39 / 64% /
  +0.04 — 2: 26 / 69% / +0.12 — 3+: 31 / 71% / +0.15. Last year 0: 12 / 83% / +0.35 — 1: 12 / 67% /
  +0.08 — 2: 3 — 3+: 7 / 57% / −0.08. Not monotonic; a strong counter-run is not a warning on its own.
- **Skip prior 3+:** −4.6R 2020-25 (p 0.44), +0.5R last year — FAIL.
- **Prior 3+ AND 15m 4+ (the full pattern):** 2 trades 2020-25, 1 last year (this one) — 3 in 6.7
  years, 1 win. Cannot be measured. The 15m 4+ BOS skip would already have skipped this trade.
- **Leg ended on a liquidity grab** (a day / session / H4 level on the target side taken on the
  extreme's 5m candle or the two before): 54 trades 2020-25, 70% / +0.14R; skipping costs −7.5R (p
  0.40), −1.9R last year — FAIL. It did NOT flag this trade: here the H4 low (4420.87) went at 06:40,
  27 minutes before the leg's low (4404.39, 07:07).
- **The day's facts:** the 1.0 (4475.10) was exactly the Asia high; price ran to 4509 through it. The
  Asia low (4375.57) held; London's low (4404.39) and New York's (4412.69 by 10:00) were higher lows.

## "With the sweep, not against it" — the user's liquidity read (2026-09-21, frozen, user's go)

From the 03-27 sell: the London low was swept the day before, Asia held above it, and highs (sessions,
previous day, equal highs, a trend line of lower highs) sat untaken above — so the draw was up and the
sell was against it. Levels: session / previous-day / 4-hour highs and lows (wick sweeps), equal
highs/lows from the canonical 5m engine; closed 5m bars before the fill's. The trend line is NOT
measured (no engine draws one). Version 1, TP2, cost-free; skip the flagged ("against") trades.

- **R0 against the last sweep** (the last bar that took a level took one on the target side only):
  4h in — 2020-25 97 against, 70% / +0.13R vs 60 with, 73% / +0.19R, skip −13.0R (p 0.34); last year
  against did BETTER (25, 76% / +0.23R vs 9, 56%). 4h out — against 106, 75% / +0.21R vs 51, 65% /
  +0.05R, skip −21.8R; last year 18, 67% vs 16, 75%. **FAIL** both ways.
- **R1 the user's points 1+2** (the last sweep before the 5m leg's start was target-side, none taken
  on that side since): 4h in — flags 1 trade in 6.7 years (a sell leg almost always takes a 4-hour
  low on the way down), so unmeasurable. 4h out — 23, 74% / +0.20R, better than the rest; skip −4.5R;
  last year 6, 67%. **FAIL.**
- **R2 points 1+2+3** (+ more untaken levels behind the stop than ahead of the target): 4h out — 15,
  80% / +0.29R in 2020-25, among the best trades; last year 3, 1 won. **FAIL.** 4h in: 1 trade.
- It flags the 03-27 sell (4h out: R0, R1, R2; 4h in: R0 only), not the 02-04 buy.
- ⚠ The first run had the side flipped (it flagged WITH-the-sweep trades); caught because the 03-27
  check disagreed with that day's known sweeps, then fixed and re-run with the rules unchanged. That
  accidental run (before the clip fix, not re-run) is itself a finding, NOT tested for: with 4h in, trades whose leg started after a
  sweep on the STOP side (a sell leg after highs were taken — "with the sweep") went 86, 64% / +0.04R
  vs 80% / +0.29R (2020-25, p 0.02) and 68% vs 75% last year. The opposite of the principle, found by
  accident after ~50 tests — not a lead to act on.
- About 55 loser tests this session; the standing leads were Asia → TP1 and the 15m 4+ BOS skip —
  and, once its label was corrected, the sweep (below).

## A 23.6 target instead of the 38.2 (2026-09-21, frozen before the run, version 1)

The 23.6 is not on the Structure fib's ladder; built as 0.0 + 0.236 × (1.0 − 0.0), checked against the
ladder's own 38.2. From the 61.8 with the stop at 1.0 it pays 1.0R (the 38.2 pays 0.62R). Same 157 /
34 setups; after PU Prime ECN costs (spread, commission, swap per rollover) and one position at a
time, since a longer hold can block the next touch. Figures: n / avgR / total / worst DD / total per DD.

| Exit | 2020-25 | Last year | Win rate (cost-free) |
|---|---|---|---|
| 38.2 (version 1) | 157 / +0.132 / +20.7R / 4.2 / 5.0 | 34 / +0.137 / +4.7R / 3.6 / 1.3 | 71% / 71% |
| 23.6 | 157 / +0.119 / +18.7R / 6.7 / 2.8 | 34 / +0.288 / +9.8R / 3.0 / 3.3 | 57% / 65% |
| 0.0 (old TP3) | 157 / +0.058 / +9.1R / 14.4 / 0.6 | 34 / +0.155 / +5.3R / 5.2 / 1.0 | 41% / 44% |
| Half 38.2 + half 23.6 | 157 / +0.126 / +19.7R / 5.2 / 3.8 | 34 / +0.212 / +7.2R / 3.2 / 2.2 | 57% / 65% |
| Half 38.2, rest to 23.6 at break-even | 157 / +0.134 / +21.0R / 4.6 / 4.5 | 34 / +0.168 / +5.7R / 3.2 / 1.8 | 71% / 71% |

- **All four FAIL** the frozen bar (beat version 1 on total and total per drawdown in both windows,
  and a paired bootstrap p < 0.05 on 2020-25): p 0.58 / 0.81 / 0.59 / 0.45.
- **The 23.6 wins only last year** (22 of 24 TP2 winners ran on to it, in a strongly trending gold
  year). Over 2020-25 only 89 of 112 did: it lost 2.0R and the worst drawdown rose from 4.2R to 6.7R.
- Edge over random entries on the same bracket is about the same for both targets (38.2 +0.15 vs
  +0.04 random; 23.6 +0.13 vs +0.02), so the target changes the payoff shape, not the edge.
- The 23.6 holds about twice as long (median 96 vs 55 minutes in 2020-25): more swap on buys and the
  10% pool tied up longer.
- The break-even scale-out is a wash in 2020-25 (+0.3R) and +1.0R last year: nothing proven, extra
  moving parts. **The 38.2 stays.**

## The sweep label, corrected — and the sweep becomes the strongest lead (2026-09-21)

**Found by `backtest/tools/fft_blind_deck.py`**, which reads the sweep a third way (the engine's own
level log, cut at the touch) and disagreed with the study on 11 of 60 setups — all 11 the study's
"swept" and the deck's "none". Two defects, in the study's `sweep()` AND the bot's A+ label (the bot
was matched to the study, so it copied both): (1) the fill bar was checked against the nearest live
levels INCLUDING ones already taken and still drawn — one sell counted highs $6-16 below its own fill;
(2) the touch minute's whole range counted, so a level reached only after the fill was a sweep
"before" it. Fixed: levels not yet taken, and the touch minute only as far as the 61.8. After the fix
the study, the bot and the deck agree on every setup (2,644 / 2,644 first touches 2020-25, 494 / 494
last year, 60 / 60 in the deck). It moves no trade — the label never gated one.

Version 1, TP2, cost-free, the corrected label:

- **2020-25:** 45 of 157 trades had a sweep (29%, not ~41%) — TP2 84.4% vs 66.1%, **+0.366R vs
  +0.069R a trade** (5,000 shuffles, p 0.01); TP1 88.9% vs 77.7%.
- **Last year:** 8 of 34 — TP2 75% vs 69%, +0.213R vs +0.120R (p 0.29). Same direction, 8 trades.
- **EURUSD and NAS100** (frozen before the run; new data): EURUSD 38 of 231, 63% vs 57%, +0.022R vs
  −0.078R (p 0.28); NAS100 41 of 241, 76% vs 64%, +0.223R vs +0.043R (p 0.08). Same direction on both,
  neither past p 0.05 — NOT confirmed by the frozen bar, but the most consistent lead measured here:
  four samples, four the same way.
- ⚠ Found by fixing a defect, not by searching outcomes — the definition is the one pre-declared
  before any run today — but it still sits among ~60 tests this session. The earlier loser scan's
  "A+ sweep" feature used the flawed label.

## The three leads on EURUSD and NAS100 (2026-09-21, frozen before the run)

FFT version 1 exactly, PU Prime 1m, 2020-01 → 2026-09, cost-free; EURUSD in pips so the reopen clip's
$2 floor means 2 pips. Check: gold 2020-25 through the same script reproduces 157 trades, lead 1
+1.3R, lead 2 +2.1R. Bar: HOLDS at gain > 0 and p < 0.05; CONFIRMED on both markets, or p < 0.0125 on
one with the same sign on the other.

- **Base edge:** gold +0.154R (random +0.014R); **EURUSD −0.062R (58% win, random +0.005R) — FFT
  does not work there**; NAS100 +0.074R (66%, random +0.001R), first half +0.12R, second +0.03R. The
  leads are relative tests, so they still read where the base is flat.
- **Lead 1, skip after 4+ 15m BOS:** EURUSD 15 flagged, −0.03R vs −0.06R, +0.4R (p 0.54); NAS100 13
  flagged, −0.25R vs +0.09R, +3.3R (p 0.064). Same direction on both; **not confirmed.**
- **Lead 2, Asia entries → TP1:** EURUSD 42, +1.7R (p 0.38); NAS100 23, +0.5R (p 0.25). Same
  direction; **not confirmed.**
- **Lead 3, the sweep:** above. **Not confirmed**, same direction on both.
- Six of six lead-market results point the leads' way; none clears p 0.05. Evidence, not proof.
  Route 2 (the forward log) is what can settle them.

## The blind take/skip deck (2026-09-21, `backtest/tools/fft_blind_deck.py`)

60 of the 157 version-1 trades of 2020-02 → 2025-08, seed 20260921, 7+ days apart, shuffled; each
chart is PU Prime 5m cut at the first touch of the 61.8, with the 5m leg's 1.0 and 0.0, the engines'
structure and levels, the sweep or "none", and the 15m BOS count. **Take-everything baseline: 38 of
60 reached TP2 (63%), +1.48R** — below the pool's 71% by the luck of the draw. 14 of 60 show a sweep.
Outcomes: `backtest/reports/fft_blind/outcomes.csv` (git-ignored; never opened before the marks are
in). Page: https://claude.ai/artifact/VJbyecKjWZRfRmkHG6TYwy (marks save to its store). Grade with
`blind_replay_grade.py` on `FFT_r`, and read the takes within sweep / no-sweep as well: the sweep is
on the page, so a pick that just follows it would beat random without the eye adding anything.

## Tested and NOT profitable — do not re-test
- **After a stop-out, does price come back?** (2026-09-21, version 1, cost-free.) Within 24h of the
  stop, 58% of 2020-25 losses (26/45) went back to TP1 and 51% on to TP2; last year 5/10 and 4/10.
  Within 4h only 33% / 24%, and 1/10 last year. Before TP1, price first ran a median **0.62R past the
  stop** (75th pct 1.30R) — a deep run, not a wick through the 1.0.
- **Wider stop** (same entry and TP2): 1.13 → +0.098R vs +0.154R (2020-25), +0.031R vs +0.142R (last
  year); 1.272 → +0.075R / −0.039R. The win rate rises, the profit per trade falls in both windows.
- **Stop-sweep RE-ENTRY** (frozen before the run): after the stop, enter on the first 1m break back
  in the trade's direction within 24h, stop at the sweep's extreme, target the original TP1 / TP2;
  variant B also needs the close back beyond the 1.0. **Loses in all 8 cells**: 2020-25 A −0.26R /
  −0.28R (n 36/42), B −0.24R / −0.24R (n 27/33), every one under break-even and under random entries
  (z −0.5 to −1.1); last year the same (n 5-8). The "come back" above is how far gold moves in a day,
  not a tradeable sweep.

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
