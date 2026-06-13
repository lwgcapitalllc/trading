Audit this backtest. Be the bear case, not a cheerleader.

Run to audit: [RUN ID or path under reports/lab/]

Open the raw outputs — the trade list, equity curve, and daily P&L — not just the KPI summary. Then answer honestly:

1. Is there a real edge here, or is this noise / overfit? Say which.
2. Where does the profit come from? Check if a few trades, days, or one regime carry the whole result. Tell me what happens if I remove the best week.
3. Does the win rate match the R:R, or is something off?
4. Is the equity curve broadly steady or one lucky streak?
5. Does it survive the spread and slippage already in the numbers?

Grade it against my KPI floor from the Strategy Framework: Sharpe ≥ 1.0, Calmar ≥ 1.0, profit concentration < 60% in one quarter, z-score within ±2, expectancy > 0 after costs. State pass/fail on each.

Then tell me: would you walk away from this, or is it worth tuning? If worth tuning, name the 1–2 params most likely to matter and why — but do not hand me an optimized parameter set, and do not invent an edge that isn't in the data.

One trade per fact. If the fills look untrustworthy (both-sided bars, synthetic ticks), flag it and caveat the whole read.
