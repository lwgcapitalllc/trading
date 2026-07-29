# Trade archive — XAUUSD 15m, full broker history

Generated **2026-07-29**. This is a frozen snapshot, committed on purpose so it can be
pulled and read on a machine with no VPS, no MT5, and no local cache. Nothing here is
regenerated automatically — if the strategy config changes, this folder goes stale and
must be re-run (command at the bottom).

Everything is in here: winners, losers, scratches, and every setup that never traded.

## What was run

| | |
|---|---|
| Instrument | XAUUSD, 15-minute bars |
| Data source | Vantage Markets demo (MT5), via `backtest/cache/` |
| Window | **2018-09-13 → 2026-07-29** — 7.9 years, 185,783 bars |
| Warm-up | first 1,000 bars, engines only, no decisions recorded |
| Fill model | `bar` — zero-cost, matches what TradingView's Strategy Tester would show. `costs_usd` is 0 in every row. Real spread/commission is NOT modelled here. |
| Strategies | `mpc_sos_fade` (A+ SOS Fade) and `mpc_bleg` (B-LEG) |

2018-09-13 is the **measured** floor of the broker's real 15m history, not a guess.
MT5 answers a request for a timeframe it has no history at with coarser bars still
labelled as what you asked for, so the floor is probed by bar density and cached in
`backtest/cache/history_floors.json`. Do not run this earlier than that date — the
numbers would be fiction. (The first day is partial: 38 real bars, history begins
mid-day.)

## Headline

| | A+ SOS Fade | B-LEG |
|---|---|---|
| Trades | 188 | 58 |
| Total | **+109.5R** | **+3.5R** |
| Avg per trade | +0.58R | +0.06R |
| Win / Loss / Breakeven | 59 / 61 / 68 | 20 / 28 / 10 |
| Win rate | 31% | 34% |
| Avg win / avg loss | +2.78R / −0.92R | +1.56R / −1.00R |

A+ carries the edge. B-LEG is roughly flat over 7.9 years and is the one that most
needs the analysis. Its losing years are 2021 (−6.0R), 2022 (−3.9R) and 2023 (−3.6R).

A+'s only losing years are 2018 (−1.8R, a 5-trade stub) and 2022 (−4.0R, 3 wins from 22).

Win rate is low by design — this is a fade strategy that scratches often at breakeven and
pays out on a small number of large runners. Judge it on sumR, not win rate.

## Files

Per strategy folder (`mpc_sos_fade/`, `mpc_bleg/`):

- **`trades.csv`** — one row per completed trade. Every trade, not just losers.
- **`setups.csv`** — one row per A+ leg that reached the SOS stage, whether it traded
  or not. 700 rows. This is the only place a *blocked* or *skipped* setup is countable —
  no order is placed, so a broker trade list has no record of it at all.
- **`summary.txt`** — the full stdout: totals by year, by regime, by session, by
  direction, the "did the losing trade ever work" breakdown, and the never-traded reasons.

### `trades.csv` columns

| column | meaning |
|---|---|
| `entry_utc`, `entry_ny` | entry timestamp, UTC and New York |
| `year`, `month`, `weekday`, `hour_ny` | split-out entry time |
| `session` | Asia (20–04 NY) / London (04–09) / NewYork (09–18) / Late (18–20) |
| `regime` | market regime at entry — TRENDING / TRANSITIONING / RANGING / HIGH_VOLATILITY / LOW_VOLATILITY |
| `dir` | long or short |
| `r` | **the result, in R.** 1R = the money risked on that trade. This is the number that matters. |
| `grade` | `win` / `loss` / `be`. Anything inside ±0.15R is graded `be` (breakeven scratch), not a win or a loss. |
| `pnl_usd` | dollars, on a $10,000 starting account at 10% risk per trade |
| `entry_price`, `exit_price`, `stop_distance` | prices, and the initial stop distance in dollars of gold |
| `bars_held` | how many 15m bars the trade was open |
| `mfe_r`, `mae_r` | **the useful pair.** `mfe_r` = furthest the trade ever showed in profit before it closed. `mae_r` = furthest it ever went against. On a loser, a high `mfe_r` means the trade *worked and was given back* — an exit problem, not an entry problem. |
| `mfe_usd`, `mae_usd` | the same two in dollars |
| `exit_reason` | which exit rung closed it. In this run it is only ever `L-RUN` / `S-RUN` (long/short runner), because TP1 and TP2 are both set to 0% — the whole position is the runner, so every exit comes off that one leg whether it stopped out or trailed out. Use `r` and `mfe_r` to tell those apart, not this column. |
| `costs_usd` | always 0 under the `bar` fill model |

**Start any loss analysis with `mfe_r`.** Across A+, zero losing trades in any year
"never worked" (mfe < 0.1R), and roughly half of every year's losers had shown ≥0.5R in
profit first. Median mfe on a losing A+ trade runs 0.33R–0.68R depending on the year.
That points at the exit ladder, not the entry filter.

### `setups.csv` columns

| column | meaning |
|---|---|
| `sos_utc`, `year`, `hour_ny`, `session`, `dir` | when and where the setup appeared |
| `bars_alive` | how long the leg stayed valid |
| `stage_max` | furthest stage the setup progressed to |
| `reached_zone` | did price get to the entry zone at all (stage ≥ 3) |
| `edge_ever`, `veto_ever`, `armed_ever` | whether it found an edge, hit a veto, and armed |
| `traded` | did it become a trade |
| `verdict` | **why it didn't trade.** One of: `traded`, `never retraced to 0.5`, `no FVG in the zone`, `limit rested, never filled`, `divergence / extreme-R`, `arm source disabled` |
| `edge_price` | the price of the first edge touch |

The two dominant reasons a setup never traded are `never retraced to 0.5` and
`no FVG in the zone`. Both are entry-filter choices, and both are worth arguing about —
across 7.9 years, 700 setups reached SOS and only 188 became A+ trades.

## Caveats — read before drawing conclusions

1. **The parity gates are stale.** As of 2026-07-28 the repo flags both
   `compare_strategy.py` (A+) and `compare_bleg.py` (B-LEG) as needing a re-run on fresh
   TradingView exports. These numbers come from the Python bot; they have not been
   re-proven bar-for-bar identical to the Pine since the last exit-ladder change. Treat
   them as directionally right, not settled.
2. **Zero costs.** `fill=bar` models no spread and no commission. Real fills will be
   worse. A `--fill-model tick` run exists as an option and was not used here.
3. **Small sample per strategy.** 188 A+ trades over 7.9 years is by design — a selective
   entry that fires a couple of times a month. It still means wide error bars on the edge
   itself. Sample size is meant to arrive at the portfolio level, once several strategies
   stack on one account.
4. **These two strategies may overlap.** A+ fades an SOS and B-LEG catches the late
   retrace of an SOS, so both can be triggered by the same structure break. Whether they
   are ever in the market at the same time has never been measured. Do not assume their
   R adds cleanly.
5. **Config at time of run:** SL fib `0.886`, TP1/TP2 scale-out rungs both `0%` (runner
   only, no partial take-profits), runner trail `Structure + % ratchet` at 1% of price,
   breakeven buffer 30 ticks, risk 10% per trade, no entries in the final NY hour.

## How to regenerate

Needs the repo, Python deps, and either a warm `backtest/cache/` or a running MT5 agent.

```
python backtest/tools/run_report.py --strategy mpc_sos_fade --out <dir>
python backtest/tools/run_report.py --strategy mpc_bleg     --out <dir>
```

No `--start` needed — the tool defaults to the broker's measured floor for the
timeframe. If the MT5 agent is down it cannot identify the broker, so it refuses to
guess and asks for `--start` rather than quietly running a narrower window.

`backtest/reports/` is git-ignored (per-run scratch output). This folder is not — it is
a deliberate committed snapshot.
