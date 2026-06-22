# LWG Capital — Roadmap and Open Questions
**Last updated:** 2026-06-21

> Companion to the Project State Snapshot. Hand both to any new Claude.ai chat.

---

## Immediate next work (priority order)

1. **Push LondonBreakout from grade C toward B.** (strategy task) LondonBreakout is the furthest along — it has the first Tier 1 run and a grade-C stress test, but C is below the eval-purchase gate (B). It needs a real edge: v1 showed no edge on AUDJPY (the Asian session is itself active for AUD/JPY pairs — see `strategies/mt5/LONDON_BREAKOUT.md`). Test it on majors where the "quiet Asian range → London expansion" premise actually holds (EUR/GBP crosses, GBPUSD), run a coarse sweep to find the parameter plateau, pick from the middle, then re-stress. If no instrument yields an edge, shelve it rather than over-tune.

2. **Take MeanReversion.mq5 through the framework pipeline on a tight-spread major.** (strategy task) The build order is MT5-first, mean reversion first, EURUSD/GBPUSD at M5/M15. MeanReversion has 10 runs but no assigned worthiness tier and one grade-F stress test — and it has not been run on the tight-spread major the build order calls for. Run the full loop: simple baseline → trade management on → coarse sweep for the parameter plateau → pick from the middle → stress test.

3. **Get ORB off the floor on a futures instrument.** (strategy task) ORB is now the only NT8 strategy (VWAP_MR and Momentum deleted 2026-06-21 for embedding risk management). It has 2 runs on MNQ, all Tier 3. Run a proper optimization across MES / MNQ / MGC (integer-only parameter steps; the UI blocks decimal steps on `int` params), and use the Tuning Workbench to iterate a winner against a baseline. Note ORB is also the first strategy being re-shaped for the dynamic sizing & gating engine (emit per-trade stop, halts move out) — coordinate the two.

4. **Stress-test the first viable parameter set to a B grade.** (strategy task) Once item 1, 2, or 3 yields a Tier 1 combo, run the full manual stress test (Monte Carlo + walk-forward + sensitivity). Grade B or better is the gate to purchasing an eval challenge (the deployment-gate convention: A = funded, B = eval purchase, C = demo).

5. **NT8 auto-start on VPS reboot.** (platform task) Still open — flagged in `strategies/CLAUDE.md` as the operational gap. NT8 does not relaunch after a VPS reboot or crash; it needs manual RDP. Add a Windows Task Scheduler task (trigger: At startup, run whether logged on or not) modeled on `SYS_STARTUP` in `algos/`.

6. **Seed Apex funded/PA rulesets.** (platform task) Apex EOD eval rulesets (50k/100k) are seeded; the funded/PA side is not. Verify the rules from Apex's docs (`docs_url` convention) and add the rows so an Apex eval pass has a funded ruleset to graduate into.

Resolved since the last roadmap: the price-chart panel shipped end-to-end (real specs, strategy-structure overlays, ATR, measurement tool); the documentation audit cleaned repo-wide doc drift; LondonBreakout was added and produced the first Tier 1 run.

---

## Future platform milestones (in order, not yet started)

### Dynamic sizing & gating engine  (CORE BUILT 2026-06-21 — VPS tail pending)
The mechanism behind the whole gated-layer model: the strategy signals at unit size; layered
gates decide *whether* a trade is allowed (time cutoff, daily loss/profit limit, consistency
limit, the Section-3 filters); the engine decides *how big* from the room left now — max
scaling size for bullet evals, room-to-the-floor ÷ 7 for funded/live. The stop comes from the
strategy. **Done:** the pure Python engine + waterfall + 14 unit tests (`command-center/
backend/services/sizing_engine.py`). **Pending (needs the live VPS):** strategies emit their
per-trade stream incl. stop distance and run with halts OFF; both agents export it; wire
`run_engine` into the completion path; rework the base-size step to the locked two-mode model;
remove the halts from the .cs/.mq5; build the day-by-day timeline UI. Full spec + status:
`docs/dynamic_sizing_engine.md`. Sizing rationale: `LWG_Strategy_Framework.md` ("Sizing is set
by the engine"). **Prerequisite:** none technical for the core; the tail touches deployed
strategy files + VPS agents.

### Funded account management
Once a strategy earns a stress test grade of B or better, the next step is purchasing an eval and, after passing, going funded. The platform needs a way to track live funded accounts: current equity, daily loss remaining (the trailing-MLL engine already computes the floor), profit target progress, halt status. A new "Accounts" tab pulling from MT5 or NT8 live data. Sizing and halts on these live accounts are driven by the dynamic sizing & gating engine above (funded mode = room ÷ 7). **Prerequisite:** at least one strategy with a B+ grade.

### Live-bot version tracking (running-commit → v1/v2/v3)
At go-live you must know exactly what code each bot is running, and be able to confirm a bug fix is actually *live* — not just pulled. A `git pull` on the VPS updates the files but does not change a running bot; it keeps trading the old code until it is restarted. So "the repo is on the fixed commit" ≠ "the bot is running the fix."

**Design (agreed earlier, not yet built):**
- Each bot records the commit it **started on** (`git rev-parse HEAD` on the VPS, captured once at startup — not in the trade loop) and reports it in its status.
- The command-center keeps a tiny **per-bot ledger** that auto-assigns v1, v2, v3… the first time it observes a bot running a commit it hasn't seen before, storing `(bot, version, commit, first-seen)`. Zero manual mapping — the number is a friendly label; the commit SHA is the source of truth.
- The Bots monitor shows e.g. `<instance> — v3 (4c58350), running 6h · latest v4 (1ca8c0c) — restart to apply`. The ledger doubles as a per-bot deploy-history audit trail.

**Touches:** `algos/` bot startup (one `git rev-parse`) + command-center Bots monitor + a small ledger table. **Prerequisite:** none technical; most valuable at go-live.

**Explicitly out of scope:** lab *strategy* provenance (arbitrary past-version running, per-version source storage, changelog automation) — enterprise audit machinery mismatched to a solo research lab that runs the latest. The lab's actual need was already met by content-aware sync detection + the content-addressed `strategy_versions` registry.

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

- **Register LondonBreakout's direct MT5-agent runs in `lab.db`:** some LondonBreakout backtests were run via the MT5 agent directly. Run **Scan Strategies** when the command center is next up so any unregistered files/results are tracked.

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

**Resolved — MT5 optimization throughput.** The MT5 optimizer runs as a single native `Optimization=1` job: MQL5 frame callbacks (`OnTesterPass`) collect per-combo KPIs into `opt_results.csv`, and the MT5 tester distributes combos across its local agents. Not a bottleneck; kept here only so a new chat doesn't re-raise it.

**Resolved — NT8 cumulative drawdown versus prop firm daily drawdown.** Closed by `services/trailing_drawdown.py`: the evaluator now recomputes EOD equity from daily P&L and applies a real trailing max-loss floor with per-firm lock balances. Kept here only so a new chat doesn't re-raise it.

---

## Communication rules for new chats

- Plain English. Short sentences. No bullet points to explain a simple thing.
- No preamble ("Great question!", "Sure, I can help with that").
- One clear question at a time. Present options concisely when they exist.
- Stop after each numbered implementation step and report results.
- Smallest viable change first — no refactoring, abstractions, or speculative features beyond what the task requires.
- CLAUDE.md files are updated in the same session as approved changes, not as a follow-up.
