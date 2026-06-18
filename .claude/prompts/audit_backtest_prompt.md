Audit this backtest. Be the bear case, not a cheerleader.

Run to audit: [RUN ID or path under command-center/backend/reports/lab/<id>/]

## What data you actually have

Each run directory holds exactly two files:
- `equity_curve.json` — one row per trade: `date`, `equity`, `direction`, `profit`, `size`. This IS the trade list. There are NO entry/exit prices, no stops, no R:R, no spread, no slippage, no tick or bar data.
- `daily_pnl.json` — one row per trading day: `date`, `pnl`, `regime_tag`.

Richer KPIs are already computed and stored — read them, do not re-derive by eye. They live on the run's `backtest_runs` row in `command-center/backend/data/lab.db` (or the BacktestDetail API): `sharpe` (daily √252), `platform_sharpe`, `sharpe_low_sample`, `profit_factor`, `win_rate`, `avg_win`, `avg_loss`, `worst_day_pnl`, `worst_losing_streak`, `trade_count`, `profit_concentration_pct`, `sortino`, plus the per-regime table (`regime_breakdown`: net_pnl / win_rate / profit_factor / worst_day per regime). The `runner` field tells you NT8 vs MT5.

**Do not invent data that isn't there.** No R:R, no fill quality, no per-trade prices exist. If a question needs them, say so and use the proxy named below — never fabricate the number.

## Step 0 — sample-size honesty (do this first)

Count the trades and the trading days. The house stress gate needs ≥100 trades; Sharpe is flagged low-sample below 10 trading days. State the count, and let it cap every claim that follows. Under ~30 trades, "edge / overfit / lucky streak" are all low-confidence by definition — say that out loud rather than pretending the curve tells you.

## Then answer honestly

1. Real edge, noise, or overfit? Say which, and tie your confidence to the trade count from Step 0.
2. Where does the profit come from? Use `profit_concentration_pct` and the `regime_breakdown` table. Check if a few trades, one month, or one regime carry the whole result. Tell me what happens if I remove the single best month — use months, not weeks; trades are too sparse for weekly buckets.
3. Does the payoff ratio match the win rate? There is no R:R in the data, so use `avg_win / avg_loss` (payoff) against `win_rate`. Does the breakeven math hold, or is something off?
4. Steady curve or one lucky streak? Compute the runs-test z-score yourself from the win/loss sequence in the equity curve — the system does NOT store it. Within ±2 = consistent with random ordering of a real edge; beyond = non-random streaking. Call out the longest losing streak (`worst_losing_streak`).
5. Are costs already in the numbers? NT8 runs inject commission-per-side and slippage from the ruleset's foundational config; MT5 runs do NOT inject costs. State the runner and what that means. You cannot verify fill quality from these files — say so, don't guess.

## Grade against my KPI floor (Strategy Framework)

State pass/fail on each, with the number:
- Sharpe (daily √252) ≥ 1.0 — use stored `sharpe`; flag if `sharpe_low_sample` is true.
- Calmar ≥ 1.0 — not stored (capital-dependent). Compute it: CAGR ÷ max drawdown %, off the equity curve (it starts at $10,000). Note the account assumption.
- Profit concentration < ~60% in the largest quarter — use `profit_concentration_pct`.
- Runs-test z within ±2 — from Q4.
- Expectancy > 0 after costs — net P&L ÷ trade count.

## Verdict

Walk away, or worth tuning? If worth tuning, name the 1–2 params most likely to matter and why — but do not hand me an optimized parameter set, and do not invent an edge that isn't in the data.

One trade per fact. If the sample is too small to trust (Step 0), or the runner injected no costs, caveat the whole read.
