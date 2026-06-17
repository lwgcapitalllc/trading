# LWG Capital — Project State Snapshot
**Last updated:** 2026-06-16
**Source:** live repo state — verified against filesystem, `lab.db`, git log, and CLAUDE.md files

> Hand this document to any new Claude.ai chat as the first message, along with
> `LWG_Roadmap_And_Open_Questions.md`. Together they replace the need to re-explain
> the project from scratch.

---

## What this project is

LWG Capital is a personal algorithmic trading operation. The near-term goal is to pass prop firm evaluation challenges (LucidFlex and similar). The long-term goal is to run 30–50 funded prop accounts. Prop firms are the capital engine, not the destination — the plan is to use prop payouts to fund personal demo forex/futures accounts where the rules are looser and the real growth happens. The working method is S.Y.S.T.E.M. — a six-step process for building any strategy: Specify, Yield (gather data), Simulate (backtest), Test (stress test), Execute (live demo), Manage (monitor funded). Today the focus is running strategies through the full evaluation pipeline on two platforms: NinjaTrader 8 for futures and MT5 for forex (both backtest engines are fully wired into the command center). The core platform (command center) is feature-complete; the remaining work is grinding strategies through the pipeline until one earns a funded account.

Two standing rules shape every strategy: intraday only (flat by session end, never hold overnight), and every account has a ruleset — personal/demo accounts get relaxed rules and a real PASS/DISCARD verdict, not a free pass. The full design philosophy — layer architecture, edge buckets, build order, KPI floor — lives in `docs/LWG_Strategy_Framework.md` (the standing strategy reference).

---

## Stack and infrastructure

**Mac development environment:**
- FastAPI backend (`command-center/backend/`, port 8000) — owns all SQLite state and is the only process that touches the filesystem or the VPS.
- React + Vite + TypeScript frontend (`command-center/frontend/`, port 5173) — talks to the backend via the `/api` Vite proxy.
- SQLite (`command-center/backend/data/lab.db`) — strategies, rulesets, runs, evaluations, optimizations, stress tests, job queue, strategy versions.
- VS Code + Claude Code (primary dev tools).
- Claude.ai chat (architecture and planning discussions).
- GitHub — single monorepo, `main` branch for all development.

**Windows VPS (ForexVPS):**
- NinjaTrader 8 — backtest engine, Strategy Analyzer, and native optimizer.
- `nt8_agent.py` (port 8765 via SSH tunnel) — Flask HTTP bridge; `pywinauto` drives the NT8 WPF UI.
- `mt5_agent.py` (port 8766 via SSH tunnel) — Flask HTTP bridge; drives the MT5 Strategy Tester and supplies intraday OHLC for the price chart.
- Four live MT5 forex/gold trading bots (`algos/`) — demo phase on PU Prime accounts.
- Windows Task Scheduler — `NT8Agent` (NT8 agent), `MT5AgentRDP` (MT5 agent), `SYS_STARTUP` (bots).

**SSH tunnel:** `start.sh` opens a persistent `ssh -N forexvps` background process. `LocalForward 8765` (NT8 agent) and `LocalForward 8766` (MT5 agent) use `127.0.0.1` as the remote target — not `localhost` — because the VPS resolves `localhost` to IPv6 but the Flask agents bind IPv4 only.

**Runner dispatch:** `services/runner_dispatch.py` is the single dispatcher — it routes jobs to the NT8 agent or the MT5 agent based on the strategy's `runner` field and normalizes both response shapes so callers stay runner-agnostic.

---

## Monorepo structure

```
trading/
├── algos/           ← Four live MT5 forex/gold bots on the VPS (demo phase)
├── smart-money/     ← Crypto/forex trader scanner for copy-trading candidates
├── command-center/  ← React + FastAPI local operations platform (fully live)
├── regime/          ← Shared market regime classifier (live bots + backtest lab)
├── strategies/      ← Generic strategy source files (.cs NT8, .mq5 MT5)
├── scripts/         ← VPS bootstrap and full-recovery scripts
└── docs/            ← Cross-subsystem reference docs and audit tools
```

`algos/`, `smart-money/`, and `command-center/` are fully independent. `regime/` is shared by `algos/` (via a thin shim) and `command-center/` (imported directly). `strategies/` is consumed by `command-center/` (scanner + deploy) and deployed to the VPS strategy folders.

---

## What's shipped (oldest first)

### App shell + Smart Money + Bots monitor (pre-M1) ✅
First working command center. React shell with sidebar routing, the Bots tab (SSH monitor for gold_main/gold_scalper/gold_fft, risk-cap deploy, Telegram users), and the full Smart Money pipeline UI (scan, terminal, rankings, candidate profiles, disqualified log, config, cache). Smart Money stages 1–2 and 5 are live; stages 3–4 are blocked on API keys.

### Pre-M4 unification — single regime classifier ✅
The regime classifier was simplified to one 5-label output set (TRENDING / TRANSITIONING / RANGING / HIGH_VOLATILITY / LOW_VOLATILITY, plus UNKNOWN) and made the single canonical implementation in `regime/`. The live bots use it via `algos/shared/shared_regime.py`; the lab imports it directly. The old two-mode design and any duplicate classifiers were removed.

### M1 — Backtests Lab (strategy registry + runs + evaluations) ✅
The Strategies tab scans `strategies/` for `.cs` and `.mq5` files. Users pick a strategy, instrument, date range, and which rulesets to evaluate against. NT8 runs the backtest; results (equity curve, daily P&L, trade list) are stored under `reports/lab/`. Per-ruleset evaluations (PASS/WARN/DISCARD) fire on completion. The user always picks the rulesets — the system never auto-evaluates against all of them.

### M2 — Worthiness badges, instrument sweeps, parameter optimizer ✅
Tier 1/2/3 worthiness scoring based on profit factor and drawdown versus the strictest evaluated firm. Instrument sweeps run N sequential backtests across instruments (semaphore of 1). The native NT8 optimizer fires one grid job using all CPU cores, exports the CSV results grid, and scores every combo by our objective function. A Tier 3 warning modal routes users to sweep untested instruments.

### M3 — Stability and retry UX ✅
Sweep cancel endpoint, retry-all and per-run retry on sweeps and optimizations, SweepDetail brought to visual parity with OptimizationDetail (ProgressCard with segmented bar and elapsed timer), and a contract-month propagation fix (`withContractMonth()` stamps e.g. "MNQ" → "MNQ 06-26").

### M3 Stress Tests — Monte Carlo, walk-forward, sensitivity, A–F grading ✅
Monte Carlo (10k reshuffles + 1k bootstrap of the trade list, pure Python, ~5s). Walk-forward (N windows of in-sample/out-of-sample NT8 backtests measuring Sharpe degradation). Sensitivity (each numeric param shifted, one VPS backtest per shift — 4 shifts for NT8, 2 for MT5). A–F robustness grade with plain-English reasons. Auto-trigger runs Monte Carlo only on Tier 1 wins; manual trigger runs all three phases. A sample-size gate blocks the whole stress test below 100 trades. A Telegram notification fires after the grade is written.

### Speed Steps 1–3 — Native optimizer, rescoring, grid sensitivity, native walk-forward ✅
Native NT8 optimizer became the only search path (brute/genetic removed). Rescoring uses `MaxDailyLoss` from fixed params as the effective per-period drawdown plus a win-rate CSV format fix. Grid sensitivity is computed from optimizer neighbor combos with no extra VPS runs. Native walk-forward mode added to `nt8_backtest_runner.py`.

### Pass 1 — Foundational Config injection ✅
Rulesets carry 10 foundational fields (risk %, halt fraction, max consecutive losses, entry hours ET, days allowed, daily profit target, lock-in %, commission per side, slippage ticks). They are injected into strategy params at run creation. Every parameter is categorized as `Strategy Logic` (tunable, optimizer-visible) or `Foundational` (injected, hidden in the UI). Strategies hold sentinel default values and refuse to trade if injection fails.

### Pass 2 — Strategy Deployment Manager ✅
Upload, delete, and compile NT8 `.cs` strategy files from the UI without RDP. The NT8 agent gained file-management plus F5-compile endpoints (pywinauto via the NinjaScript Editor; success detected by polling `NinjaTrader.Custom.dll` mtime). Lock detection returns HTTP 423 if NT8 has the file open. Upload limit 256 KB.

### Pass 2.5 — Strategies subsystem + Deploy button ✅
Created `strategies/` as a top-level subsystem and moved the strategy files out of `algos/`. The scanner reads from `strategies/`. A one-click Deploy button per strategy uploads the file to the VPS (`.cs` to the NT8 agent, `.mq5` to the MT5 agent). `source_path` is stored relative to the monorepo root.

### Speed Steps 4–6 — MT5 native optimizer, Telegram, job queue ✅
MT5 native optimizer (`POST /native-optimize` on the MT5 agent) drives the Strategy Tester via `Optimization=1` ini + set-file ranges, with per-combo progress reported back. MT5 native walk-forward uses `ForwardMode` in the ini. `services/notify.py` sends Telegram grade notifications. A `job_queue` SQLite table plus an asyncio queue runner dispatches one optimization or stress test at a time, surfaced in a Queue page.

### M4 — Regime tagging + equity overlay + optimizer regime filter + platform lock ✅
Every backtest's daily P&L entries are tagged with a regime label using `regime/classifier.py`, run as a visible Tagging pipeline step. A Performance by Regime table appears on BacktestDetail, plus an equity-curve regime overlay and an optimizer regime filter that re-scores combos using only matching-regime trades. Platform-based job lock: NT8 and MT5 lock independently. Cascade delete on runs. Sweeps and optimizations nest under their source run in the Runs tab.

### M5 / Steps 1–9 — MT5 runner + deployment ✅
`mt5_agent.py` on VPS port 8766: health, Strategy Tester driver (ini + set file, `terminal64.exe`, HTML report parser). `mt5_agent_client.py` typed wrapper on the backend. The dispatcher routes to the MT5 agent when `strategy.runner == "mt5"`. MT5-aware backtest modal and detail page, runner badges (NT8/MT5), a market filter bar (Futures/Forex), and MT5 deployment (upload/delete `.mq5`, compile via MetaEditor64).

### Tuning Workbench + decoupled Optimizations + per-platform lock refinement ✅
`/backtests/runs/:id/tune` — a param editor seeded from a baseline run; tweak iterations run as real backtests linked by `source_run_id`; leaderboard with deltas; regime-aware cumulative-P&L overlay and net-P&L-by-regime table. Reached from any run or from an optimization's "Tune winner" button. Optimizations got their own top-level RESEARCH page (`/optimizations`). The per-platform job lock was refined: the DB is the single lock source (`has_running_job(runner)`), NT8 and MT5 fully independent, stale rows cleaned on boot.

### Grouped KPI grid + canonical metrics layer + trailing drawdown engine ✅
BacktestDetail's KPI section became a data-driven grid (core + "more" cards). One canonical Sharpe everywhere — daily √252, computed in `services/metrics.py`, with the platform's value preserved as `platform_sharpe`. Profit concentration persisted per run; `scripts/backfill_metrics.py` backfilled old runs idempotently. `services/trailing_drawdown.py` (`compute_trailing_mll()`) implements the real prop-firm EOD trailing max-loss: the floor trails the highest EOD balance, locks at `mll_lock_balance`, and a breach is the only thing that fails `drawdown_pass`. This replaced whole-test max-drawdown as the lens drawdown check.

### Rulesets — own page, personal demo rulesets, firm branding ✅
Rulesets moved to their own top-level page (`/rulesets`): prop rows grouped by firm (Lucid / Tradeify / FundedNext / Apex) with a page-level filter, a Contracts column (SCALES and MIX pills — FundedNext's shared mini/micro cap), and firm branding. Two personal demo rulesets get real PASS/DISCARD verdicts from `_evaluate_personal` (drawdown-from-peak and consecutive-capped-loss-days fails; daily caps are halts, not fails). Personal rules are editable via `PersonalRulesEditModal` (`PATCH /rulesets/{id}`, 5-field allowlist); prop rows are locked server-side — PATCH and PUT both return 403.

### Stress-test trustworthiness + observability polish ✅
A correctness pass over the stress pipeline: Monte Carlo pass-probability for `personal` rulesets stays in the `1 − prob_breach` branch with `demo`; sensitivity perturbs only Strategy-Logic params with a runner-aware shift count; native NT8 walk-forward stores unassessable IS→OOS degradation as `None` (not `0.0`). The stress detail page regrouped into three labelled analysis sections, and a unified per-tab layout shipped (each tab's KPI cards sit directly above its own chart). Lab observability: sidebar activity dots, Overview research quick links.

### Content-aware deploy sync + strategy versioning ✅
Strategy file sync-status is content-aware: it hashes local source live and compares to recorded deployed/compiled hashes (`needs_deploy` / `needs_compile`), so an edited-but-not-redeployed strategy no longer falsely reads "in sync." A content-addressed `strategy_versions` registry assigns a monotonic v1/v2/v3 per strategy (same hash → same version, reverts reuse), surfaced as a version chip + accurate status on the Strategies and Deployed tabs.

### Price-chart panel — klinecharts candlestick view on BacktestDetail ✅
A strategy-agnostic candlestick panel (`command-center/frontend/src/components/ChartPanel/`, klinecharts v9, lazy-loaded) renders a per-run `ChartSpec` built by `services/chart_spec.py` (`GET /backtests/runs/{id}/chart-spec`). It draws real candles with a timeframe switch, DST-correct session boxes, trade entry/exit overlays, generic structure overlays (box/hline/vline), shipped indicators (EMA main-pane / ATR sub-pane), daily breaks, and a TradingView-style measurement tool. The backend reconstructs London-breakout structure (Asian range box + ATR-buffered buy/sell levels + ATR(14)) from the M15 candles. The MT5 agent's `/historical_data` supplies intraday OHLC (case-preserving symbol fallback; daily yfinance fallback when a symbol is absent); a candle cap steps the timeframe up on long spans.

### LondonBreakout strategy + documentation audit cleanup (2026-06-16) ✅
`strategies/mt5/LondonBreakout.mq5` added — a fully instrument-agnostic Asian-range → London bar-close breakout (ATR-scaled, broker-derived GMT offset recomputed per bar, 1:1 stop/target, flat by 11:00 GMT). Design notes + v1 backtest record live in `strategies/mt5/LONDON_BREAKOUT.md`. The MT5 backtest modal symbol list gained AUDJPY.s and CADJPY.s. A documentation audit pass cleaned drift across the repo's CLAUDE.md/README files (dead `docs/archive/` and "archive spec" references removed, file locations corrected, CLAUDE.md bloat moved to guides).

---

## Current state of strategies

Five strategies are registered — three NinjaTrader `.cs` files and two MT5 `.mq5` files. The first Tier 1 run has now appeared (LondonBreakout); the best stress grade so far is **C** (also LondonBreakout). Every graded stress test on the other strategies is F. The DB holds 9 stress tests total; 5 are orphaned grade-F tests (their source runs were deleted).

| Strategy | File | Runner | Category | State (verified from `lab.db`) |
|---|---|---|---|---|
| ORB | `strategies/ninjatrader/ORB.cs` | ninjatrader | breakout | 2 runs, all TIER_3_DISCARD. No stress tests. Opening Range Breakout — entry on ORB high/low break. |
| VWAP_MR | `strategies/ninjatrader/VWAP_MR.cs` | ninjatrader | mean_reversion | No runs in the DB yet. Fades extended moves back to VWAP. |
| Momentum | `strategies/ninjatrader/Momentum.cs` | ninjatrader | momentum | 6 runs (2 TIER_2_OPTIMIZE, 4 TIER_3_DISCARD). 1 linked stress test grade F, plus 5 orphaned F tests from earlier deleted runs. EMA-based intraday momentum pullback. |
| MeanReversion | `strategies/mt5/MeanReversion.mq5` | mt5 | mean_reversion | 10 runs, no worthiness tier assigned. 2 stress tests (one grade F, one ungraded). Ported from `algos/bots/bot_mean_reversion.py` — BB + RSI + intraday VWAP confluence. |
| LondonBreakout | `strategies/mt5/LondonBreakout.mq5` | mt5 | breakout | 7 runs (1 TIER_1_STRESS_TEST, 4 TIER_2_OPTIMIZE, 2 TIER_3_DISCARD). 1 stress test grade C. Instrument-agnostic Asian-range → London breakout; v1 showed no edge on AUDJPY (notes in `LONDON_BREAKOUT.md`). |

`strategies/tradovate/` is an empty placeholder (no source files yet).

The Strategy Framework build order says: MT5 first (faster optimization), mean reversion → trend → volatility breakout, intraday bar-close logic at M5/M15 on a tight-spread major (EURUSD/GBPUSD), 2–3 candidates per bucket. Data fidelity note: both testers are trustworthy for bar-close logic at M5 and above, not for sub-minute scalping (tick-mode levers exist but are not enabled).

---

## Current state of rulesets

16 rulesets in `lab.db` (verified by direct query):
- `prop_eval`: 8 rows — Apex EOD 50k/100k, FundedNext Futures Flex 50k/100k, LucidFlex 50k/100k, Tradeify Select 50k/100k
- `prop_funded`: 6 rows — FundedNext, LucidFlex, Tradeify at 50k/100k each (Apex has no funded rows yet)
- `personal`: 2 rows — `personal_forex_demo`, `personal_futures_demo` ($10k balance, $500 daily loss cap, $1,000 daily target, fail at 15% drawdown-from-peak or 3 consecutive capped-loss days)

There are zero rows typed `demo` — both demo accounts are `ruleset_type = personal` (with `account_tier = demo`). Evaluator behavior by type: `prop_eval` checks EOD trailing max-loss (DISCARD on breach), profit target (WARN), and consistency (WARN); `prop_funded` checks trailing max-loss only; `personal` gets a real PASS/DISCARD verdict against the relaxed rules. For personal rows `max_loss_eod = 0` is a sentinel meaning "no trailing EOD rule" — it must never render or feed a verdict.

Firm naming: the firm name lives in the UI group header (Lucid / Tradeify / FundedNext / Apex); the row `name` carries the program ("LucidFlex $50k Evaluation", "Select $50k Evaluation", "Futures Flex $50k Challenge", "EOD $50k Evaluation"). LucidFlex is Lucid's program name, not the firm. Adding a prop firm means adding its eval and funded rulesets with `docs_url` filled in so the rules can be re-verified.

---

## Architectural principles locked in

1. **One backtest, N verdicts.** A single run is evaluated against multiple rulesets at once. Never run the same strategy N times for N firms. Only the first (primary) ruleset injects foundational config; the rest evaluate only.

2. **Generic strategies, ruleset-injected config.** No firm-specific defaults in strategy files. Account size, daily loss cap, commission, slippage, and entry config are all injected at run creation. Sentinel values prevent trading if injection fails.

3. **Categorized parameters.** `Strategy Logic` = tunable and optimizer-visible. `Foundational` = injected from the ruleset and hidden in the UI.

4. **Every account has a ruleset.** Personal/demo accounts get relaxed rules and a real verdict — there is no "no-verdict" account type. Prop rulesets are locked (server-side 403 on edit); personal rules are editable.

5. **One shared regime classifier.** `regime/classifier.py` is canonical. Never duplicate it; all consumers import from there.

6. **NT8 is the futures backtest + execution engine; MT5 is the forex track.** The same command center dispatcher (`runner_dispatch.py`) routes to both via runner-aware clients.

7. **Drawdown means EOD trailing max-loss.** `compute_trailing_mll()` is the lens drawdown check for prop rulesets — not whole-test peak-to-trough. One canonical Sharpe (daily √252) everywhere via `services/metrics.py`.

8. **Observability is mandatory.** Every run writes progress, logs, and output files. Optimization runs persist their VPS logs. Progress bars are wired to real agent output, not faked.

9. **CLAUDE.md updates in the same session as approved changes.** Not as a follow-up. Every session that ships a feature ends with the relevant CLAUDE.md files updated.

10. **Strict build order with stop-and-report checkpoints.** Each step is confirmed working before the next begins.

11. **Per-platform job lock, DB as the single lock source.** One job per platform at a time; NT8 and MT5 lock independently; stale `running` rows are reset on boot. Stress tests additionally lock by market (one futures + one forex at most).

12. **No ORM, no task queues, no extra frameworks.** Raw `sqlite3`, asyncio for the queue loop, `subprocess` for SSH. New dependencies require explicit discussion first. Heavy data (equity curves, trade lists) lives in JSON files on disk, not in SQLite.

---

## Communication rules with Claude Code

- Plain English. Short sentences. No bullet points to explain a simple thing.
- No preamble ("Great question!", "Sure, I can help with that").
- One clear question at a time. Present options concisely when they exist.
- Stop after each numbered implementation step and report results.
- Smallest viable change first — no refactoring, abstractions, or speculative features beyond what the task requires.
- CLAUDE.md files are updated in the same session as approved changes.

---

## What's NOT done

See `docs/LWG_Roadmap_And_Open_Questions.md` for the forward plan, deferred items, open questions, and the parallel tracks Aaron runs separately.
