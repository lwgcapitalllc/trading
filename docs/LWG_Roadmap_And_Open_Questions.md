# LWG Capital — Roadmap and Open Questions
**Last updated:** 2026-06-12

> Companion to the Project State Snapshot. Hand both to any new Claude.ai chat.

---

## Immediate next work (priority order)

1. **Take MeanReversion.mq5 through the framework pipeline on a tight-spread major.** (strategy task) The Strategy Framework build order is MT5-first, mean reversion first, EURUSD/GBPUSD at M5/M15. MeanReversion has 10 runs (all now on USDCAD.s) and one grade-F stress test, but no clean optimized result — and USDCAD is not the tight-spread major the build order calls for. Run the full loop on EURUSD/GBPUSD: simple baseline → trade management on → coarse sweep to find the parameter plateau → pick from the middle of the good region → stress test. MT5 is also the faster backtest platform.

2. **Get an NT8 strategy to Tier 1 on a futures instrument.** (strategy task) Momentum keeps grading F (its current MYM 06-26 run and earlier deleted MCL runs all came back F) — stop spending time on it. ORB has 3 runs on MNQ, all Tier 3; VWAP_MR has no runs yet. Run a proper optimization on ORB or VWAP_MR across MES / MNQ / MGC (integer-only parameter steps; the UI now blocks decimal steps on `int` params). The Tuning Workbench exists specifically to iterate a winner's params against a baseline.

3. **Stress-test the first viable parameter set to a B grade.** (strategy task) Once item 1 or 2 yields a Tier 1 combo, run the full manual stress test (Monte Carlo + walk-forward + sensitivity). Grade B or better is the gate to purchasing an eval challenge (the deployment-gate convention: A = funded, B = eval purchase, C = demo).

4. **NT8 auto-start on VPS reboot.** (platform task) Still open — flagged in `strategies/CLAUDE.md` as the operational gap. NT8 does not relaunch after a VPS reboot or crash; it needs manual RDP. Add a Windows Task Scheduler task (trigger: At startup, run whether logged on or not) modeled on `SYS_STARTUP` in `algos/`.

5. **Seed Apex funded/PA rulesets.** (platform task) Apex EOD eval rulesets (50k/100k) are seeded; the funded/PA side is not. Verify the rules from Apex's docs (`docs_url` convention) and add the rows so an Apex eval pass has a funded ruleset to graduate into.

Resolved since the last roadmap: the optimization-delete 500 bug no longer reproduces in the endpoint code — `DELETE /optimizations/{id}` now guards running status and cascades child runs and report directories (TODO: verify with a live delete). The "re-run a completed optimization with tweaked grid" wish was superseded by the Tuning Workbench.

---

## Future platform milestones (in order, not yet started)

### Funded account management
Once a strategy earns a stress test grade of B or better, the next step is purchasing an eval and, after passing, going funded. The platform needs a way to track live funded accounts: current equity, daily loss remaining (the trailing-MLL engine already computes the floor), profit target progress, halt status. A new "Accounts" tab pulling from MT5 or NT8 live data. **Prerequisite:** at least one strategy with a B+ grade.

### Strategy stacking layer
The Strategy Framework's end-state is a stack of uncorrelated edge buckets (mean reversion + trend + volatility breakout) so something works in every regime and the combined curve is smooth enough to pass evals. Once 2–3 graded candidates per bucket exist, the platform needs a way to evaluate combined equity curves against a ruleset. **Prerequisite:** multiple graded strategies across at least two buckets.

### Instrument profile layer (Layer B)
The framework defines a per-symbol config layer — spread guards, session windows, per-instrument regime thresholds — distinct from strategy params and rulesets. Broker-known facts (tick size/value, min stop) are read at runtime; only what the broker can't tell you gets configured. The per-instrument regime thresholds item below folds into this. **Prerequisite:** none technical; most valuable once strategies run on more than one or two symbols.

### Copy trading integration
Smart Money stages 3–4 (API keys required) are incomplete. When unblocked, the pipeline produces a ranked list of traders to copy; the command center would need a Copy Trading tab tying the candidate pool to configurable copy-trade rules (max allocation, max drawdown per copied trader, kill switch). **Prerequisite:** API keys for stages 3–4.

### Per-instrument regime thresholds
The regime classifier uses fixed ADX/ATR/RSI thresholds calibrated for XAUUSD on H1/H4. `REGIME_CLASSIFIER.md` flags this as a known gap — NAS100, MNQ, MCL, and EURUSD have different volatility profiles. A per-instrument threshold config in `regime/thresholds.py` would improve label quality. **Prerequisite:** none technical; most valuable once a futures strategy is live enough to care about regime-conditioned sizing.

### Tick-level backtest fidelity
Both testers currently run on minute bars (MT5 `Model=1`, NT8 standard fills) — trustworthy for bar-close logic at M5+, not for sub-minute scalping. Real bid/ask ticks exist on the broker ≥ 2 years deep. Enabling MT5 `Model=4` / NT8 Tick Replay is a known one-line lever, not yet turned on. **Prerequisite:** a scalping-speed strategy worth validating.

---

## Smaller items raised but deferred

- **Regime persistence filter:** require two consecutive identical classifications before committing a label change, to reduce noise at transitions (suggested in `REGIME_CLASSIFIER.md`). Not implemented; thresholds are intentionally not auto-optimized.

- **Multi-timeframe regime consistency:** a regime where the short and long timeframes agree is more reliable. A "confidence" field could surface this. Deferred.

- **Foundational-values edit UI on personal rulesets:** the `PUT` endpoint can still edit foundational fields on personal rows, but there is no UI affordance since `FoundationalEditModal` was removed with the prop lock. Add one only if foundational tweaking on personal rows becomes a real workflow.

- **Strategy file sync-status hash comparison:** sync-status currently checks file presence on the VPS only, no content hash. Fine until a stale-deploy bug actually bites.

- **Smart Money stages 3–4:** blocked externally on API keys. No code work needed until keys are available.

---

## Parallel tracks Aaron runs separately

- **Live bots demo phase (`algos/`):** Four MT5 bots (SMC Trend, Mean Reversion, Scalper, FFT) are accumulating trade history toward Calmar targets (2.0–2.5 to proceed to prop eval; FFT stays at 1% risk until 30+ trades). This runs independently of command center work — no shared sessions. The bots are monitored via the Bots tab.

- **Smart Money candidate research:** Stages 1–2 and 5 of the Smart Money pipeline are live and can be run locally to build a copy-trading candidate pool. Separate track from command center development.

- **Prop firm research:** evaluating and onboarding prop firms (rules, drawdown models, lock balances, payout terms) feeds the ruleset library but is researched outside the codebase. The Apex addition came from this track. Each new firm becomes eval + funded rulesets with `docs_url` filled in; the trailing-MLL lock behavior varies by firm (start + $100 for most, start + target for Apex/Rithmic, never for Tradeify eval) and must be captured per ruleset.

---

## Open architectural questions

> Documented so a new chat can pick them up if relevant. Do not proactively re-litigate them — they are settled-for-now decisions with known trade-offs.

**NT8 SA window state after optimization export.** The two-pass right-click export for native optimization results is brittle: if the results panel is collapsed or all combos produce 0 trades, the Export context menu item does not appear and the job fails. Current mitigation is integer-param validation in the UI plus coordinate tuning (right-click at y=20%). Any NT8 UI change that shifts the panel layout could break it again. The CSV export is the only programmatic output path from NT8's optimization grid — no robust alternative identified.

**Resolved — MT5 optimization throughput.** The MT5 optimizer runs as a single native `Optimization=1` job: MQL5 frame callbacks (`OnTesterPass`) collect per-combo KPIs into `opt_results.csv`, and the MT5 tester distributes combos across its local agents (verified in `mt5_agent.py` and `MeanReversion.mq5`). Not a bottleneck; kept here only so a new chat doesn't re-raise it.

**Resolved — NT8 cumulative drawdown versus prop firm daily drawdown.** The old open question (NT8's whole-test max drawdown isn't comparable to a firm's trailing daily limit) was closed by `services/trailing_drawdown.py`: the evaluator now recomputes EOD equity from daily P&L and applies a real trailing max-loss floor with per-firm lock balances. Kept here only so a new chat doesn't re-raise it.

---

## Communication rules for new chats

- Plain English. Short sentences. No bullet points to explain a simple thing.
- No preamble ("Great question!", "Sure, I can help with that").
- One clear question at a time. Present options concisely when they exist.
- Stop after each numbered implementation step and report results.
- Smallest viable change first — no refactoring, abstractions, or speculative features beyond what the task requires.
- CLAUDE.md files are updated in the same session as approved changes, not as a follow-up.
