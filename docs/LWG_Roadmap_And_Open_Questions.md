# LWG Capital — Roadmap and Open Questions
**Last updated:** 2026-06-09

> Companion to the Project State Snapshot. Hand both to any new Claude.ai chat.

---

## Immediate next work (priority order)

1. **Get a strategy to Tier 1 on a futures instrument.** Momentum on MCL is currently TIER_3_DISCARD. Run a proper optimization sweep on ORB or VWAP_MR across MES/MNQ/MGC with integer-only parameter steps to find a winning parameter set before investing stress test time on Momentum.

2. **Investigate and fix the 500 error on optimization delete from the UI.** Direct SQLite deletion has been used as a workaround twice (opt_5d440e4922, opt_1d15d468bd). The `DELETE /optimizations/{id}` endpoint is returning 500 — root cause unknown. Could be a cascade constraint, missing guard on child runs, or a status check that blocks deletion.

3. **Verify and document TestOptPass.mq5.** This file exists in `strategies/mt5/` but is not in `strategies/CLAUDE.md`. Either document it with its purpose or delete it.

4. **Reconcile ruleset count discrepancy.** `backend/CLAUDE.md` says 13 seeded rulesets but `lab.db` has 15. Identify which 2 extra rows were added and update the CLAUDE.md documentation.

5. **NT8 auto-start on VPS reboot.** NT8 does not start automatically after a VPS reboot or NT8 crash — requires manual RDP intervention. Add a Windows Task Scheduler task (trigger: At startup, run whether logged on or not) to launch NT8 and load the active strategy set. Model it on the `SYS_STARTUP` task in `algos/`.

---

## Future platform milestones (in order, not yet started)

### Funded account management
Once a strategy earns Tier 1 status and a stress test grade of B or better, the next step is purchasing an eval challenge. The platform needs a way to track live funded accounts: current equity, daily loss remaining, profit target progress, halt status. This would be a new "Accounts" tab pulling from MT5 or NT8 live data. Prerequisite: at least one strategy with a B+ grade.

### Copy trading integration
Smart Money stages 3–4 (API keys required) are incomplete. When they're unblocked, the pipeline would produce a ranked list of traders to copy. The command center would need a Copy Trading tab that ties the Smart Money candidate pool to a set of configurable copy-trade rules (max allocation, max drawdown per copied trader, kill switch). Prerequisite: API keys for stages 3–4.

### Per-instrument regime thresholds
The regime classifier uses fixed ADX/ATR/RSI thresholds calibrated for XAUUSD on H1/H4. The `REGIME_CLASSIFIER.md` flags this as a known gap — NAS100 and EURUSD have different volatility profiles. A per-instrument threshold config in `regime/thresholds.py` would improve label quality for futures instruments like MNQ and MCL.

---

## Smaller items raised but deferred

- **Optimization delete 500 error:** The UI delete endpoint returns 500 for some optimizations (worked around twice with direct SQLite deletion). Root cause not investigated — could be cascade logic or a status guard.

- **Smart Money stages 3–4:** API keys required for the copy trading candidate ranking stages. Blocked externally; no code work needed until keys are available.

- **Regime persistence filter:** `REGIME_CLASSIFIER.md` suggests requiring two consecutive identical classifications before committing a label change, to reduce noise at transitions. Not implemented; thresholds are intentionally not auto-optimized.

- **Multi-timeframe regime consistency:** `REGIME_CLASSIFIER.md` notes that a regime where H1 and H4 agree is more reliable. A "confidence" field could surface this. Deferred.

- **Optimization re-run button on completed optimizations:** Currently the re-run button only shows on failed/cancelled optimizations. Extending it to completed ones would let users tweak the grid and re-run without creating a new optimization record. Not raised formally, noted as a natural extension.

---

## Parallel tracks Aaron is running separately

- **Live bots demo phase (`algos/`):** Four MT5 bots (SMC Trend, Mean Reversion, Scalper, FFT) are accumulating trade history toward Calmar targets (2.0–2.5 to proceed to prop eval). This runs independently of the command center work — no shared sessions. The bots are monitored via the Bots tab.

- **Smart Money candidate research:** Stages 1–2 and 5 of the Smart Money pipeline are live and can be run locally. Active use for building a copy-trading candidate pool is a separate track from command center development.

---

## Open architectural questions

**How to handle the backtesting gap between NT8 cumulative drawdown and prop firm daily drawdown.** NT8 "Max. drawdown" is cumulative peak-to-trough over the entire test period, not a per-day figure. Prop firms evaluate daily EOD equity. The current workaround uses `MaxDailyLoss` from `fixed_params` as a proxy — this is a heuristic, not a precise calculation. A more accurate approach would parse the trade list to recompute daily EOD equity and measure per-day drawdown directly. This hasn't been built because the proxy is good enough for Tier 1/2/3 classification, but it would matter for precise PASS/WARN/DISCARD evaluation. Not actively planned — raise if evaluation accuracy becomes a bottleneck.

**NT8 SA window state after optimization export.** The two-pass right-click export for native optimization results is brittle: if the results panel is collapsed or all combos produce 0 trades, the Export context menu item doesn't appear and the job fails. The current mitigation is integer param validation in the UI and coordinate tuning (y=20%). If NT8 adds any UI change that shifts the panel layout, the export will break again. No robust alternative has been identified — the CSV export is the only programmatic output path from NT8's optimization grid.

**MT5 optimization uses sequential single backtests.** MT5's `Optimization=1` command-line mode populates only the GUI results tab — no parseable file output. The workaround is running each combo as a separate single backtest and collecting individual HTML reports. This is correct and validated, but it means MT5 optimization speed scales linearly with combo count (no parallelism). If combo counts grow large, this becomes a queue bottleneck. No solution is planned — flagged for awareness.

---

## Communication rules for new chats

- Plain English. Short sentences. No bullet points for simple explanations.
- No preamble ("Great question!", "Sure, I can help with that").
- One clear question at a time. Present options concisely when they exist.
- Stop after each numbered implementation step and report results.
- Smallest viable change first — no refactoring, abstractions, or speculative features beyond what the task requires.
- CLAUDE.md files are updated in the same session as approved changes, not as a follow-up.
