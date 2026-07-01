# LWG Capital — Roadmap and Open Questions
**Last updated:** 2026-07-01

> Companion to the Project State Snapshot. Hand both to any new Claude.ai chat.

---

## Immediate next work (priority order)

1. **Verify the dynamic sizing engine on the VPS.** (platform task) The sizing engine, decision log, and per-firm sized results are all code-complete on Mac (`services/sizing_engine.py`, `services/sizing_pipeline.py`, tests green), and both `ORB.cs` and `LondonBreakout.mq5` have been reshaped to emit `engine_trades.csv` at unit size. Neither can be tested locally — both need a real VPS compile + backtest to confirm the sized path (equity curve, timeline, KPIs) actually renders end to end. This unblocks everything downstream that depends on real sized numbers.

2. **Push LondonBreakout toward a B-grade stress test.** (strategy task) LondonBreakout is the furthest along — first Tier 1 run, grade-C stress test. C is below the eval-purchase gate (B). v1 showed no edge on AUDJPY (the Asian session is itself active for AUD/JPY pairs). Test it on majors where the "quiet Asian range → London expansion" premise actually holds (EUR/GBP crosses, GBPUSD), run a coarse sweep for the parameter plateau, pick from the middle, re-stress. If no instrument yields an edge, shelve it rather than over-tune.

3. **Get ORB off the floor on a futures instrument.** (strategy task) ORB is the only NT8 strategy (VWAP_MR and Momentum were deleted 2026-06-21 for embedding risk management). It has 2 runs on MNQ, both Tier 3. Run a proper optimization across MES / MNQ / MGC (integer-only parameter steps — the UI already blocks decimal steps on `int` params), then use the Tuning Workbench to iterate a winner against a baseline.

4. **Rebuild the algos/ bot suite backtest-first.** (platform + strategy task) `algos/` has zero live bots. New bots follow the S.Y.S.T.E.M. six-step process in `docs/BOT_DEVELOPMENT_METHOD.md` — a strategy only reaches live demo after it has cleared the command-center backtest lab and a stress-test grade. This is really the same track as items 2–3: whichever strategy first earns a B+ grade is the candidate for live demo wiring, using the preserved deployment plumbing in `algos/docs/BOT_DEPLOYMENT_INFRA.md`.

5. **NT8 auto-start on VPS reboot.** (platform task) Still open. NT8 does not relaunch after a VPS reboot or crash; it needs manual RDP. Add a Windows Task Scheduler task (trigger: At startup, run whether logged on or not) modeled on `SYS_STARTUP` in `algos/`.

6. **Seed Apex funded/PA rulesets.** (platform task) Apex EOD eval rulesets (50k/100k) are seeded; the funded/PA side is not. Verify the rules from Apex's docs (`docs_url` convention) and add the rows so an Apex eval pass has a funded ruleset to graduate into.

Note: an earlier version of this list included "take MeanReversion.mq5 through the framework pipeline" as a strategy task. `MeanReversion.mq5` was deleted 2026-06-22 alongside the Mean Reversion bot — that item no longer applies and has been dropped.

TODO: verify items 2–4 against the latest `lab.db` state at the start of a new session — strategy grades and run counts move as backtests complete.

---

## Future platform milestones (in order, not yet started)

### Funded account management
Once a strategy earns a stress-test grade of B or better, the next step is purchasing an eval and, after passing, going funded. The platform needs a way to track live funded accounts: current equity, daily loss remaining (the trailing-MLL engine already computes the floor), profit target progress, halt status. A new "Accounts" tab pulling from MT5 or NT8 live data. Sizing and halts on these accounts are driven by the dynamic sizing & gating engine (funded mode = room ÷ 7). **Prerequisite:** at least one strategy with a B+ grade, and the sizing engine verified live on the VPS (see immediate item 1).

### Live-bot version tracking (running-commit → v1/v2/v3)
At go-live you must know exactly what code each bot is running, and be able to confirm a bug fix is actually *live* — not just pulled. A `git pull` on the VPS updates files but does not restart a running bot, so "the repo is on the fixed commit" does not mean "the bot is running the fix."

Design (agreed, not yet built): each bot records the commit it started on (`git rev-parse HEAD`, captured once at startup) and reports it in its status. The command center keeps a small per-bot ledger that auto-assigns v1, v2, v3… the first time it observes a new commit for that bot, storing `(bot, version, commit, first-seen)`. The Bots monitor would show e.g. "v3 (4c58350), running 6h · latest v4 — restart to apply." **Prerequisite:** none technical; most valuable once a bot is actually running live (currently none are).

### Strategy stacking layer
The Strategy Framework's end state is a stack of uncorrelated edge buckets (mean reversion + trend + volatility breakout) so something works in every regime and the combined curve is smooth enough to pass evals. The platform needs a way to evaluate combined equity curves against a ruleset. **Prerequisite:** 2–3 graded candidates across at least two edge buckets — currently only one strategy per runner exists (ORB, LondonBreakout), both breakout-type.

### Instrument profile layer (Layer B)
The framework defines a per-symbol config layer — spread guards, session windows, per-instrument regime thresholds — distinct from strategy params and rulesets. Broker-known facts (tick size/value, min stop) are read at runtime; only what the broker can't tell you gets configured. **Prerequisite:** none technical; most valuable once strategies run on more than one or two symbols.

### Copy trading integration
Smart Money stages 3–4 (API keys required) are incomplete. When unblocked, the pipeline produces a ranked list of traders to copy; the command center would need a Copy Trading tab tying the candidate pool to configurable copy-trade rules (max allocation, max drawdown per copied trader, kill switch). **Prerequisite:** API keys for stages 3–4.

### Per-instrument regime thresholds
The regime classifier uses fixed ADX/ATR/RSI thresholds calibrated for XAUUSD on H1/H4. `REGIME_CLASSIFIER.md` flags this as a known gap — other instruments have different volatility profiles. A per-instrument threshold config in `regime/thresholds.py` would improve label quality. **Prerequisite:** none technical; most valuable once a strategy trades multiple instruments live enough to care about regime-conditioned sizing.

### Tick-level backtest fidelity
Both testers currently run on minute bars (MT5 `Model=1`, NT8 standard fills) — trustworthy for bar-close logic at M5+, not sub-minute scalping. Real bid/ask ticks exist on the broker ≥ 2 years deep. Enabling MT5 `Model=4` / NT8 Tick Replay is a known one-line lever, not yet turned on. **Prerequisite:** a scalping-speed strategy worth validating.

### Structure OS / SMC indicator (indicators/)
A from-scratch rewrite of a TradingView SMC/market-structure indicator (`indicators/smc_engine_v2.pine`), tracked in `indicators/STRUCTURE_OS_BUILD.md`. As of the last build note it is mid-rebuild: swing detection is validated to ~95% parity with the reference indicator on daily gold, but Stage 2 (BOS/CHoCH break logic) needs testing and Stage 3 (internal structure) hasn't started. Currently blocked on Aaron's chart validation of the swing map before Stage 2 proceeds. Not yet wired to any strategy or the command-center lab — it's a standalone research indicator today. **Prerequisite:** none technical; this is its own track, see below.

---

## Smaller items raised but deferred

- **Regime persistence filter:** require two consecutive identical classifications before committing a label change, to reduce noise at transitions. Not implemented; thresholds are intentionally not auto-optimized.
- **Multi-timeframe regime consistency:** a "confidence" field for when short and long timeframe regimes agree. Deferred.
- **Foundational-values edit UI on personal rulesets:** the `PUT` endpoint can still edit foundational fields on personal rows, but there's no UI affordance since `FoundationalEditModal` was removed with the prop lock. Add one only if it becomes a real workflow.
- **Register any LondonBreakout runs made via direct MT5-agent calls in `lab.db`:** run Scan Strategies periodically to catch anything unregistered.
- **Smart Money stages 3–4:** blocked externally on API keys. No code work needed until keys are available.

---

## Parallel tracks Aaron is running separately

- **Smart Money candidate research:** Stages 1–2 and 5 of the Smart Money pipeline are live and can be run locally to build a copy-trading candidate pool. Separate track from command-center development, no shared sessions.
- **Prop firm research:** evaluating and onboarding prop firms (rules, drawdown models, lock balances, payout terms) feeds the ruleset library but is researched outside the codebase. The Apex addition came from this track. Each new firm becomes eval + funded rulesets with `docs_url` filled in; trailing-MLL lock behavior varies by firm and must be captured per ruleset.
- **Structure OS / SMC indicator rebuild:** the `indicators/` Pine rewrite is validated interactively against TradingView chart screenshots and the public indicator page — a manual, chart-by-chart comparison process distinct from the command-center backtest pipeline.

Note: there is currently no "bots accumulating live trade history" track — `algos/` has zero live bots as of 2026-06-22. Any future note about live demo bots running independently should only be added here once a bot actually exists and is deployed.

---

## Open architectural questions

> Documented so a new chat can pick them up if relevant. Do not proactively re-litigate them — they are settled-for-now decisions with known trade-offs.

**NT8 SA window state after optimization export.** The two-pass right-click export for native optimization results is brittle: if the results panel is collapsed or all combos produce 0 trades, the Export context menu item does not appear and the job fails. Current mitigation is integer-param validation in the UI plus coordinate tuning (right-click at y=20%). Any NT8 UI change that shifts the panel layout could break it again. The CSV export is the only programmatic output path from NT8's optimization grid — no robust alternative identified.

**Resolved — MT5 optimization throughput.** The MT5 optimizer runs as a single native `Optimization=1` job: MQL5 frame callbacks (`OnTesterPass`) collect per-combo KPIs into `opt_results.csv`, and the MT5 tester distributes combos across its local agents. Not a bottleneck; kept here only so a new chat doesn't re-raise it.

**Resolved — NT8 cumulative drawdown versus prop firm daily drawdown.** Closed by `services/trailing_drawdown.py`: the evaluator recomputes EOD equity from daily P&L and applies a real trailing max-loss floor with per-firm lock balances. Kept here only so a new chat doesn't re-raise it.

**Open — sizing engine live verification.** The dynamic sizing & risk engine is fully built and unit-tested on Mac but has never run against a real VPS backtest end to end. Until item 1 in "Immediate next work" is done, treat every sized-run UI feature (Sized equity curve, Sizing Timeline table, per-firm KPI switching) as code-complete-but-unverified rather than proven.

---

## Communication rules for new chats

- Plain English. Short sentences. No bullet points to explain a simple thing.
- No preamble ("Great question!", "Sure, I can help with that").
- One clear question at a time. Present options concisely when they exist.
- Stop after each numbered implementation step and report results.
- Smallest viable change first — no refactoring, abstractions, or speculative features beyond what the task requires.
- CLAUDE.md files are updated in the same session as approved changes, not as a follow-up.
