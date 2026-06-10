# LWG Capital — Roadmap and Open Questions
**Last updated:** 2026-06-10

> Companion to the Project State Snapshot. Hand both to any new Claude.ai chat.

---

## Immediate next work (priority order)

1. **Get a strategy to Tier 1 on a futures instrument.** (strategy task) Momentum on MCL is currently TIER_3_DISCARD. Run a proper optimization on ORB or VWAP_MR across MES / MNQ / MGC with integer-only parameter steps to find a winning parameter set before spending stress test time on Momentum.

2. **Fix the 500 error on optimization delete from the UI.** (platform task) `DELETE /optimizations/{id}` returns 500 for some optimizations; direct SQLite deletion has been used as a workaround twice. Root cause unknown — likely a cascade constraint, a missing guard on child runs, or a status check that blocks deletion.

3. **NT8 auto-start on VPS reboot.** (platform task) NT8 does not relaunch automatically after a VPS reboot or NT8 crash — it needs manual RDP intervention. Add a Windows Task Scheduler task (trigger: At startup, run whether logged on or not) that launches NT8 and loads the active strategy set. Model it on the `SYS_STARTUP` task in `algos/`.

4. **Stress-test the first viable futures parameter set.** (strategy task) Once item 1 yields a Tier 1 combo, run the full manual stress test (Monte Carlo + walk-forward + sensitivity) on the winner to get an A–F grade. A grade of B or better is the gate to purchasing an eval challenge.

---

## Future platform milestones (in order, not yet started)

### Funded account management
Once a strategy earns Tier 1 status and a stress test grade of B or better, the next step is purchasing an eval challenge and, after passing, going funded. The platform needs a way to track live funded accounts: current equity, daily loss remaining, profit target progress, halt status. This would be a new "Accounts" tab pulling from MT5 or NT8 live data. **Prerequisite:** at least one strategy with a B+ grade.

### Copy trading integration
Smart Money stages 3–4 (API keys required) are incomplete. When they are unblocked the pipeline would produce a ranked list of traders to copy. The command center would need a Copy Trading tab tying the Smart Money candidate pool to configurable copy-trade rules (max allocation, max drawdown per copied trader, kill switch). **Prerequisite:** API keys for stages 3–4.

### Per-instrument regime thresholds
The regime classifier uses fixed ADX/ATR/RSI thresholds calibrated for XAUUSD on H1/H4. `REGIME_CLASSIFIER.md` flags this as a known gap — NAS100, MNQ, MCL, and EURUSD have different volatility profiles. A per-instrument threshold config in `regime/thresholds.py` would improve label quality for futures instruments. **Prerequisite:** none technical, but most valuable once a futures strategy is live enough to care about regime-conditioned sizing.

---

## Smaller items raised but deferred

- **Regime persistence filter:** require two consecutive identical classifications before committing a label change, to reduce noise at transitions (suggested in `REGIME_CLASSIFIER.md`). Not implemented; thresholds are intentionally not auto-optimized.

- **Multi-timeframe regime consistency:** a regime where the short and long timeframes agree is more reliable. A "confidence" field could surface this. Deferred.

- **Optimization re-run on completed (not just failed) optimizations:** the re-run button currently shows only on failed/cancelled optimizations. Extending it to completed ones would let users tweak the grid and re-run in place. Noted as a natural extension, not formally requested.

- **Smart Money stages 3–4:** blocked externally on API keys. No code work needed until keys are available.

---

## Parallel tracks Aaron runs separately

- **Live bots demo phase (`algos/`):** Four MT5 bots (SMC Trend, Mean Reversion, Scalper, FFT) are accumulating trade history toward Calmar targets (2.0–2.5 to proceed to prop eval; FFT stays at 1% risk until 30+ trades). This runs independently of command center work — no shared sessions. The bots are monitored via the Bots tab.

- **Smart Money candidate research:** Stages 1–2 and 5 of the Smart Money pipeline are live and can be run locally to build a copy-trading candidate pool. This is a separate track from command center development.

- **Prop firm research:** evaluating and onboarding prop firms (their rules, drawdown models, payout terms) feeds the ruleset library but is researched outside the codebase. Each new firm becomes an eval/funded ruleset pair with `docs_url` filled in.

---

## Open architectural questions

> These are documented so a new chat can pick them up if relevant. Do not proactively re-litigate them — they are settled-for-now decisions with known trade-offs.

**NT8 cumulative drawdown versus prop firm daily drawdown.** NT8's "Max. drawdown" is cumulative peak-to-trough over the whole test, not a per-day figure. Prop firms evaluate daily EOD equity. The current workaround uses `MaxDailyLoss` from `fixed_params` as a proxy — a heuristic, not a precise calculation. A more accurate approach would parse the trade list to recompute daily EOD equity and measure per-day drawdown directly. Not built because the proxy is good enough for Tier 1/2/3 classification; it would matter for precise PASS/WARN/DISCARD evaluation. Raise only if evaluation accuracy becomes a bottleneck.

**NT8 SA window state after optimization export.** The two-pass right-click export for native optimization results is brittle: if the results panel is collapsed or all combos produce 0 trades, the Export context menu item does not appear and the job fails. Current mitigation is integer-param validation in the UI plus coordinate tuning (right-click at y=20%). Any NT8 UI change that shifts the panel layout could break it again. The CSV export is the only programmatic output path from NT8's optimization grid — no robust alternative identified.

**MT5 optimization uses sequential single backtests.** MT5's `Optimization=1` CLI mode populates only the GUI results tab — no parseable file. The workaround runs each combo as a separate single backtest and collects individual HTML reports. Correct and validated, but MT5 optimization speed scales linearly with combo count (no parallelism). If combo counts grow large, this becomes a queue bottleneck. No solution planned — flagged for awareness.

---

## Communication rules for new chats

- Plain English. Short sentences. No bullet points to explain a simple thing.
- No preamble ("Great question!", "Sure, I can help with that").
- One clear question at a time. Present options concisely when they exist.
- Stop after each numbered implementation step and report results.
- Smallest viable change first — no refactoring, abstractions, or speculative features beyond what the task requires.
- CLAUDE.md files are updated in the same session as approved changes, not as a follow-up.
