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
