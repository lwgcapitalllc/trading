# The Pine-less setup filters — what each one measured

All seven settings have no Pine input, ship OFF, and are forced off by the parity gate. A run with
any of them on is a DIFFERENT strategy from the one the chart trades.

## Run 1 — 2026-09-21, one switch per run

Window: `backtest/cache/VantageMarkets_Demo/XAUUSD__M5.csv`, 2018-09-14 → 2026-08-23, no costs.
Config: the middle row of `exports/golden/VANTAGE_XAUUSD_M5_conf5_20633bars.csv`, then one override.
⚠ Eight years, most of it OUTSIDE the gated window. ⚠ Costs not charged — the lab refuses costs
for this strategy until `core.py` prices them.

| Run | Trades | Total R | Win % | PF | Max DD (R) | Avg R |
|---|---|---|---|---|---|---|
| Baseline, all off | 71 | +5.3 | 28.2 | 1.11 | -10.3 | +0.075 |
| Slower trend 60m must agree | 40 | -0.3 | 25.0 | 0.99 | -6.6 | -0.007 |
| Slower trend 240m must agree | 45 | +6.5 | 31.1 | 1.21 | -6.6 | +0.143 |
| Gap max age 60 bars | 65 | +14.1 | 30.8 | 1.32 | -7.8 | +0.216 |
| Gap max age 20 bars | 65 | +14.1 | 30.8 | 1.32 | -7.8 | +0.216 |
| Gap size 0.2–2.0 ATR | 48 | -0.3 | 25.0 | 0.99 | -9.6 | -0.007 |
| Gap must overlap a live order block | 10 | -2.4 | 20.0 | 0.70 | -4.2 | -0.239 |
| News blackout 30 min before / after | 54 | +7.7 | 27.8 | 1.20 | -8.9 | +0.142 |

Reading:
- Gap age is the only candidate. Ages 20 and 60 are identical, so the whole effect is six trades
  off gaps older than 60 bars, worth about -9R together. Six trades is thin; it may be luck.
- Order-block overlap cuts 71 → 10 and loses. Rejected.
- The news calendar on this machine covers 2021-01 onward only; before that the filter cannot ask
  and allows every trade. So its +2.4R came from the covered years alone.
- Next: test gap age on data it has never seen, with costs, before it goes anywhere near a chart.

## Run 2 — 2026-09-21, is the gap-age filter real? (`tools/measure_filters.py`)

Costs charged per trade after the replay: PU Prime ECN, measured, $0.14/oz round trip. No swap.
Halves split at 2022-09-01. "Unseen" = bars after 2026-08-23, after the filter was chosen.

| Feed | Run | Net R | Net PF | Max DD | 2018–22 net R | 2022–26 net R | Unseen |
|---|---|---|---|---|---|---|---|
| Vantage | baseline | +3.6 (71 tr) | 1.07 | -11.4 | +10.5 (17) | -6.9 (54) | no bars |
| Vantage | age 10 / 30 / 60 / 100 | +12.5 (65) | 1.28 | -8.1 | +6.2 (13) | +6.2 (52) | no bars |
| Vantage | age 200 | +4.1 (66) | 1.09 | -12.2 | +5.2 (14) | -1.1 (52) | no bars |
| PU Prime | baseline | +3.8 (76) | 1.07 | -16.3 | +13.1 (19) | -9.3 (57) | -3.1 (3) |
| PU Prime | age 60 | +11.3 (67) | 1.24 | -8.1 | +9.9 (14) | +1.4 (53) | -2.0 (2) |

Reading:
- NOT a tuned point: every limit from 10 to 100 bars gives the same trades. The kept gaps are all
  under 10 bars old; the dropped ones are all over 100. The filter is a clean split, not a dial.
- It holds on a second broker's feed after costs (+3.8R → +11.3R).
- ⚠ It does NOT help in both halves: it costs ~4R in 2018–22 and earns it back in 2022–26.
- 🔴 The strategy itself is still not tradeable. On the live broker's feed, 2022–26, with the filter,
  it made +1.4R over 53 trades (PF 1.04). The four unseen weeks lost on both runs (2–3 trades — noise).
