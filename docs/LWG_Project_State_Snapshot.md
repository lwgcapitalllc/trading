# LWG Capital — Project State Snapshot
**Last updated:** 2026-07-04
**Source:** live repo state — verified against filesystem, `lab.db`, git log, and CLAUDE.md files

> Hand this document to any new Claude.ai chat as the first message, along with
> `LWG_Roadmap_And_Open_Questions.md`. Together they replace the need to re-explain
> the project from scratch.

---

## What this project is

LWG Capital is a personal algorithmic trading operation. The near-term goal is to pass prop firm evaluation challenges (LucidFlex and similar). The long-term goal is to run 30–50 funded prop accounts. Prop firms are the capital engine, not the destination — the plan is to use prop payouts to fund personal demo forex/futures accounts where the rules are looser and the real growth happens. The working method is S.Y.S.T.E.M. — a six-step process for building any strategy: Specify, Yield (build), Stress test (backtest), Threshold check (robustness), Evaluate (live demo), Manage (monitor funded/live). Today the focus is two tracks: futures (NinjaTrader 8) and forex (MT5) strategy research through the command-center backtest lab, and a growing library of canonical Python market-analysis engines (market structure, fibonacci — extracted from a TradingView SMC indicator and validated at 100% Pine parity) that future bots will trade from. The `algos/` live-bot suite is not currently running anything: the first four bots were deleted 2026-06-22 to rebuild backtest-first, so forex/MT5 live trading is present as infrastructure and one candidate strategy (LondonBreakout), not as a running bot. The core platform (command center) is feature-complete; the remaining work is grinding strategies through the pipeline until one earns a funded account.

Two standing rules shape every strategy: intraday only (flat by session end, never hold overnight), and every account has a ruleset — personal/demo accounts get relaxed rules and a real PASS/DISCARD verdict, not a free pass. The full design philosophy — layer architecture, edge buckets, build order, KPI floor — lives in `docs/LWG_Strategy_Framework.md`.

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
- **No live bots.** The four first-attempt MT5 bots (SMC Trend, Scalper, FFT, Mean Reversion) were deleted 2026-06-22 — code, data, and the VPS side all removed — to rebuild the suite backtest-first per `docs/BOT_DEVELOPMENT_METHOD.md`. Reusable deployment plumbing (MT5 connection layer, per-instance configs, Task Scheduler wiring, liveness/notification layer) is preserved in `algos/docs/BOT_DEPLOYMENT_INFRA.md` so a validated strategy can go to live demo without rebuilding infrastructure.
- Windows Task Scheduler — `NT8Agent` (NT8 agent), `MT5AgentRDP` (MT5 agent), `SYS_STARTUP` (bot launcher, currently nothing to launch).

**SSH tunnel:** `start.sh` opens a persistent `ssh -N forexvps` background process. `LocalForward 8765` (NT8 agent) and `LocalForward 8766` (MT5 agent) use `127.0.0.1` as the remote target — not `localhost` — because the VPS resolves `localhost` to IPv6 but the Flask agents bind IPv4 only.

**Runner dispatch:** `services/runner_dispatch.py` is the single dispatcher — it routes jobs to the NT8 agent or the MT5 agent based on the strategy's `runner` field and normalizes both response shapes so callers stay runner-agnostic.

---

## Monorepo structure

```
trading/
├── algos/             ← MT5 bot deployment infra; no live bots today (rebuilding backtest-first)
│   ├── bots/              launcher, startup coordinator, config loader
│   ├── shared/            MT5 ops, risk engine, scanner, regime shim, structure-engine shim, notify
│   ├── notifications/     Telegram bot, monitor, P&L tracker, daily reporter
│   ├── scheduler/         Windows Task Scheduler XML definitions
│   ├── nt8/               NT8 backtest toolchain (agent, runner, compile runner, deploy)
│   └── markets/           per-market tool + instance dirs (fx/tools/mt5_agent.py; crypto reserved/empty)
├── smart-money/       ← Crypto/forex trader scanner for copy-trading candidates (Mac-only)
├── command-center/    ← React + FastAPI local operations platform (fully live)
│   ├── backend/           FastAPI app, SQLite (lab.db), VPS clients, backtest/stress/optimizer services
│   └── frontend/          React + Vite UI — lab, bots monitor, smart money, rulesets
├── engines/regime/            ← Shared market regime classifier (live bots + backtest lab)
├── engines/market_structure/  ← Canonical BOS/CHoCH/swing detection engine (Python, 100% Pine parity)
├── engines/fibonacci/         ← Canonical fib level-event engine, downstream of engines/market_structure/ (100% Pine parity)
├── strategies/        ← Generic strategy source files, organized by runner platform
│   ├── ninjatrader/       NT8 NinjaScript strategies (.cs)
│   ├── mt5/               MT5 expert advisors (.mq5)
│   └── tradingview/       Pine v6 research strategies — TradingView Strategy Tester only, not scanned
├── indicators/        ← TradingView Pine indicator rebuild + Pine sources/parity exports for the engines
├── scripts/           ← Cross-subsystem VPS bootstrap and full-recovery scripts
└── docs/              ← Cross-subsystem reference docs and audit tools
```

`algos/`, `smart-money/`, and `command-center/` are fully independent. `engines/regime/` and `engines/market_structure/` are shared libraries imported by `algos/` (each via a thin shim in `algos/shared/`); `engines/regime/` is also imported by `command-center/` directly. `engines/fibonacci/` is downstream of `engines/market_structure/` — it consumes that engine's public output (a `StructureSnapshot`) only, never its internals, and will get an `algos/shared/` shim when a bot first uses it. `strategies/` is consumed by `command-center/` (scanner + deploy) and deployed to the VPS strategy folders.

---

## What's shipped (chronological, oldest first)

**App shell + Smart Money + Bots monitor (pre-M1) — shipped.** First working command center. React shell with sidebar routing, the Bots tab (SSH monitor + control scaffold, risk-cap deploy, Telegram users), and the full Smart Money pipeline UI (scan, terminal, rankings, candidate profiles, disqualified log, config, cache). Smart Money stages 1–2 and 5 are live; stages 3–4 are blocked on API keys.

**Pre-M4 unification — single regime classifier — shipped.** The regime classifier was simplified to one 5-label output set (TRENDING / TRANSITIONING / RANGING / HIGH_VOLATILITY / LOW_VOLATILITY, plus UNKNOWN) and made the single canonical implementation in `engines/regime/`. Live bots use it via `algos/shared/shared_regime.py`; the lab imports it directly.

**M1 — Backtests Lab (strategy registry + runs + evaluations) — shipped.** The Strategies tab scans `strategies/` for `.cs` and `.mq5` files. Users pick a strategy, instrument, date range, and which rulesets to evaluate against. NT8 runs the backtest; results are stored under `reports/lab/`. Per-ruleset evaluations (PASS/WARN/DISCARD) fire on completion — the user always picks the rulesets.

**M2 — Worthiness badges, instrument sweeps, parameter optimizer — shipped.** Tier 1/2/3 worthiness scoring against the strictest evaluated firm. Instrument sweeps run N sequential backtests (semaphore of 1). The native NT8 optimizer fires one grid job using all CPU cores, exports the CSV results grid, and scores every combo. A Tier 3 warning modal routes users to sweep untested instruments.

**M3 — Stability and retry UX — shipped.** Sweep cancel, retry-all and per-run retry on sweeps/optimizations, SweepDetail parity with OptimizationDetail, contract-month propagation fix.

**M3 Stress Tests — Monte Carlo, walk-forward, sensitivity, A–F grading — shipped.** Monte Carlo (10k reshuffles + 1k bootstrap, pure Python, ~5s). Walk-forward (N windows of in-sample/out-of-sample NT8 backtests). Sensitivity (each numeric param shifted — 4 shifts NT8, 2 shifts MT5). A–F robustness grade. Auto-trigger runs Monte Carlo only on Tier 1 wins; manual trigger runs all three phases. Sample-size gate blocks the whole test below 100 trades.

**Speed Steps 1–3 — Native optimizer, rescoring, grid sensitivity, native walk-forward — shipped.** Native NT8 optimizer became the only search path (brute-force/genetic removed from the UI). Grid sensitivity computed from optimizer neighbor combos with no extra VPS runs. Native walk-forward mode added.

**Pass 1 — Foundational Config injection — shipped.** Rulesets carry 10 foundational fields (risk %, halt fraction, max consecutive losses, entry hours ET, days allowed, daily profit target, lock-in %, commission/side, slippage ticks), injected into strategy params at run creation. Every parameter is categorized `Strategy Logic` (tunable) or `Foundational` (injected, hidden). Strategies hold sentinel defaults and refuse to trade if injection fails.

**Pass 2 — Strategy Deployment Manager — shipped.** Upload, delete, and compile NT8 `.cs` files from the UI without RDP. NT8 agent gained file-management + F5-compile endpoints (success detected by polling `NinjaTrader.Custom.dll` mtime). Lock detection returns HTTP 423 if NT8 has the file open.

**Pass 2.5 — Strategies subsystem + Deploy button — shipped.** Created `strategies/` as a top-level subsystem, moved strategy files out of `algos/`. One-click Deploy button per strategy uploads to the VPS.

**Speed Steps 4–6 — MT5 native optimizer, Telegram, job queue — shipped.** MT5 native optimizer via `Optimization=1` ini + set-file ranges with per-combo progress. Telegram grade notifications. `job_queue` SQLite table + asyncio queue runner dispatching one job at a time, surfaced on a Queue page.

**M4 — Regime tagging + equity overlay + optimizer regime filter + platform lock — shipped.** Every run's daily P&L tagged with a regime label. Performance-by-Regime table, equity-curve regime overlay, optimizer regime filter. Platform-based job lock: NT8 and MT5 lock independently. Cascade delete on runs.

**M5 / Steps 1–9 — MT5 runner + deployment — shipped.** `mt5_agent.py` on VPS port 8766: health, Strategy Tester driver (ini + set file, `terminal64.exe`, HTML report parser). Dispatcher routes to MT5 agent when `strategy.runner == "mt5"`. MT5-aware backtest modal/detail, runner badges, market filter, MT5 deployment (upload/delete/compile).

**Tuning Workbench + decoupled Optimizations + per-platform lock refinement — shipped.** `/backtests/runs/:id/tune` — param editor seeded from a baseline run, tweak iterations as real linked backtests, leaderboard with deltas, regime-aware overlay. Optimizations got their own top-level page (`/optimizations`).

**Grouped KPI grid + canonical metrics layer + trailing drawdown engine — shipped.** BacktestDetail's KPI section became a data-driven grid. One canonical Sharpe everywhere (daily √252, `services/metrics.py`). `services/trailing_drawdown.py` implements the real prop-firm EOD trailing max-loss as the drawdown check, replacing whole-test max drawdown.

**Rulesets — own page, personal demo rulesets, firm branding — shipped.** Rulesets moved to `/rulesets`: prop rows grouped by firm (Lucid / Tradeify / FundedNext / Apex), Contracts column with SCALES/MIX pills. Two personal demo rulesets get real PASS/DISCARD verdicts. Prop rows locked server-side (403 on PATCH/PUT).

**Stress-test trustworthiness + observability polish — shipped.** Correctness pass over the stress pipeline (personal ruleset pass-probability branch, runner-aware sensitivity shift count, honest `None` for unassessable walk-forward degradation). Stress detail page regrouped into three labelled analysis sections. Sidebar activity dots.

**Content-aware deploy sync + strategy versioning — shipped.** Strategy file sync-status is content-aware (hashes local source live, compares to recorded deployed/compiled hashes). Content-addressed `strategy_versions` registry assigns monotonic v1/v2/v3 per strategy.

**Price-chart panel — klinecharts candlestick view on BacktestDetail — shipped.** Strategy-agnostic candlestick panel (`ChartPanel/`, klinecharts v9, lazy-loaded) renders a per-run `ChartSpec`: real candles, timeframe switch, DST-correct sessions, trade overlays, generic structure overlays, EMA/ATR indicators, measurement tool.

**LondonBreakout strategy + documentation audit cleanup (2026-06-16) — shipped.** `strategies/mt5/LondonBreakout.mq5` added — instrument-agnostic Asian-range → London breakout. A documentation audit cleaned drift across CLAUDE.md/README files repo-wide.

**LondonBreakout JPY-cross sweep (2026-06-18) — shipped.** Eight MT5 backtests: seven JPY crosses plus USDCAD. Six scored Tier 2 (OPTIMIZE) — USDJPY, GBPJPY, CADJPY, EURJPY, CHFJPY, NZDJPY; AUDJPY and USDCAD scored Tier 3. These are the current LondonBreakout results of record in `lab.db`.

**Bot suite reset (2026-06-21 to 2026-06-22) — shipped.** All four first-attempt MT5 bots (SMC Trend, Scalper, FFT, Mean Reversion) deleted — code, data, VPS side. Two NT8 strategies (VWAP_MR, Momentum) also deleted for embedding account-governance logic in the strategy, against the gated-layer rules. Reusable deployment infra preserved in `algos/docs/BOT_DEPLOYMENT_INFRA.md`.

**Dynamic sizing & risk engine + decision log (core built 2026-06-21, wired through 2026-06-30) — shipped.** The mechanism behind the LWG gated-layer model: a strategy signals at unit size; gates decide whether a trade is allowed; `services/sizing_engine.py` (pure, no DB/network) decides how big from the room left, in one of two per-run modes (bullet = max the rules allow; consistent = room ÷ 7). `services/decision_log.py` is the one reusable audit log (one JSONL record per signal). `ORB.cs` and `LondonBreakout.mq5` were both reshaped to trade unit size and emit `engine_trades.csv` (the runner→engine contract); `services/sizing_pipeline.py` wires the engine into the run-completion path. Every prop/personal ruleset gets its own sized P&L, timeline, and equity curve per run (`ruleset_sizing.json`), and BacktestDetail switches all ruleset-dependent charts/KPIs per firm.

**Structure engine — canonical Python port (validated through 2026-07-02) — shipped.** `engines/market_structure/` — a stateful streaming state machine ported line-by-line from `indicators/structure_engine.pine` (itself extracted from a full SMC indicator). External + internal structure: BOS/CHoCH, swing highs/lows, HH/HL/LH/LL, plus the BOS break-leg endpoints. Validated at **100% Pine parity** on real XAUUSD 15m exports (21,729 bars OANDA; re-confirmed on a fresh 9,721-bar Vantage export) via `engines/market_structure/tools/compare_tradingview.py`. Wired into `algos/` via the `algos/shared/structure_engine.py` shim. This is the single structure implementation — no consumer builds its own.

**Fibonacci engine — all three fibs, Pine-parity-validated (2026-07-02 to 2026-07-04) — shipped.** `engines/fibonacci/` — one shared geometry core plus three per-fib state machines ported line-by-line from `mpc_assistant.pine`: Structure ("FFT", swing-anchored E1–E4/TP1–TP5 with the 0.618 gate), Sniper (BOS-impulse 0.382–0.5 zone), and Macro (HH→LL cycle, ≤5m only). Emits level EVENTS (first-touch pulses), not visuals. Consumes the structure engine's public `StructureSnapshot` only. All three validated at **100% Pine parity** on real XAUUSD exports (Structure/Sniper on 15m, Macro on 5m) via `engines/fibonacci/tools/compare_fib.py` against the instrumented `indicators/fib_export.pine`. Gets an `algos/shared/` shim when a bot first consumes it.

**First sized-path VPS run — NT8 verified (2026-07-01) — shipped.** ORB ran on MES and MNQ from the lab (both completed; both Tier 3 on performance). The MES run produced the full sized-engine output on disk — `engine_trades.csv` came back from the VPS, and `decisions.jsonl`, `engine_timeline.json`, `engine_daily_pnl.json`, and the per-firm `ruleset_sizing.json` were all written. The NT8 runner→engine→files path is proven end-to-end on a real VPS backtest. The MT5 side (LondonBreakout) has not yet produced engine output — see the roadmap.

---

## Current state of strategies

Three strategy source files exist today, across two runners plus one research-only Pine track. Run facts verified by direct `lab.db` query on 2026-07-04 (10 real runs total; the stress-tests table is currently empty — earlier stress-test records were deleted along with their runs).

| Strategy | File | Runner | State |
|---|---|---|---|
| ORB (Opening Range Breakout) | `strategies/ninjatrader/ORB.cs` | ninjatrader | The only NT8 strategy. Reshaped 2026-06-21 to trade unit size (1 contract) with self-policing halts removed (moved to the sizing engine); emits `engine_trades.csv`. 2 runs on record (MES + MNQ, 2026-07-01), both Tier 3 discard on performance — but the MES run proved the sized-engine path end-to-end (full engine output on disk). Next step is a proper optimization across MES/MNQ/MGC. |
| LondonBreakout | `strategies/mt5/LondonBreakout.mq5` | mt5 | Instrument-agnostic Asian-range (00:00–06:00 GMT) → London breakout. Reshaped 2026-06-22 (v3) to trade unit size; carries the `OnTester*` optimizer callbacks. 8 runs on record (2026-06-18 sweep): Tier 2 OPTIMIZE on USDJPY, GBPJPY, CADJPY, EURJPY, CHFJPY, NZDJPY; Tier 3 on AUDJPY and USDCAD (the Asian session is itself active for AUD — notes in `strategies/mt5/LONDON_BREAKOUT.md`). No stress test on record. The v3 unit-size reshape has not yet produced `engine_trades.csv` from a VPS run. |
| ny_orb (NY Opening Range Breakout) | `strategies/tradingview/ny_orb.pine` | tradingview (research only) | In TradingView research/tuning as of 2026-06-20, not yet promoted to NT8/MT5. Instrument-agnostic, built on `london_breakout.pine`'s skeleton. Not picked up by the command-center scanner (only `.cs`/`.mq5` are scanned). |

TODO: verify run/tier counts against `lab.db` at read time if this snapshot is more than a few days old.

The Strategy Framework build order: MT5 first (faster optimization), mean reversion → trend → volatility breakout buckets, intraday bar-close logic at M5/M15 on a tight-spread major, 2–3 candidates per bucket. Both backtest engines are trustworthy for bar-close logic at M5+, not for sub-minute scalping (tick-mode levers exist but aren't enabled).

---

## Current state of rulesets

16 rulesets in `lab.db` (verified by direct query on 2026-07-04):
- `prop_eval`: 8 rows
- `prop_funded`: 6 rows
- `personal`: 2 rows (`account_tier = demo` on both — `personal_forex_demo`, `personal_futures_demo`)
- `demo` (as a distinct `ruleset_type`): 0 rows — both demo accounts are typed `personal` with `account_tier = demo`. The evaluator code path for `ruleset_type = demo` exists but is currently unused.

Firm coverage: 4 prop firms — LucidFlex, FundedNext, Tradeify (each 50k/100k × eval/funded, 12 rows) — plus Apex EOD eval-only at 50k/100k (2 rows; Apex funded/PA not yet seeded). Personal demo rules on a $10k balance: $500 daily loss cap, $1,000 daily profit target, fail at 15% drawdown from peak or 3 consecutive capped-loss days.

Evaluator behavior by type: `prop_eval` checks EOD trailing max-loss (DISCARD on breach), profit target (WARN), consistency (WARN). `prop_funded` checks trailing max-loss only. `personal`/`demo` get a real PASS/DISCARD verdict against relaxed rules — no trailing MLL, no profit-target requirement, no consistency rule. For personal rows, `max_loss_eod = 0` is a sentinel meaning "no trailing EOD rule" and must never render or feed a verdict.

---

## Architectural principles locked in

1. **One backtest, N verdicts.** A single run is evaluated against multiple rulesets at once. Never run the same strategy N times for N firms. Only the first (primary) ruleset injects foundational config; the rest evaluate only.

2. **Generic strategies, ruleset-injected config.** No firm-specific defaults in strategy files. Account size, daily loss cap, commission, slippage, and entry config are all injected at run creation. Sentinel values prevent trading if injection fails.

3. **Categorized parameters.** `Strategy Logic` = tunable and optimizer-visible. `Foundational` = injected from the ruleset and hidden in the UI.

4. **Every account has a ruleset.** Personal/demo accounts get relaxed rules and a real verdict — there is no "no-verdict" account type. Prop rulesets are locked (server-side 403 on edit); personal rules are editable.

5. **One canonical implementation per engine.** `engines/regime/classifier.py`, `engines/market_structure/engine.py`, and `engines/fibonacci/` are the single implementations of their domains. Consumers import them (bots via thin `algos/shared/` shims); nobody builds a second one anywhere.

6. **Engines are ported line-by-line and Pine-parity-validated.** Every engine extracted from the TradingView SMC indicator follows the same pattern: port the Pine block into a stateful streaming state machine (one closed bar at a time), emit events (never visuals), instrument the Pine with export plots, and diff Python-vs-Pine bar-by-bar to 100% before shipping. Downstream engines read another engine's public output only — never its internals. The queue of remaining blocks is `docs/ENGINE_EXTRACTION_ROADMAP.md`.

7. **NT8 is the futures backtest + execution engine; MT5 is the forex track.** The same command-center dispatcher (`runner_dispatch.py`) routes to both via runner-aware clients.

8. **Drawdown means EOD trailing max-loss.** `compute_trailing_mll()` is the lens drawdown check for prop rulesets — not whole-test peak-to-trough. One canonical Sharpe (daily √252) everywhere via `services/metrics.py`.

9. **Strategies signal; the engine sizes.** Strategies emit trades at unit size only and never manage account-level risk. `sizing_engine.py` decides position size from the room left against the ruleset's trailing floor. Enforced on both reshaped strategies (ORB, LondonBreakout).

10. **Observability is mandatory.** Every run writes progress, logs, and output files. Optimization runs persist their VPS logs. Progress bars are wired to real agent output, not faked.

11. **CLAUDE.md updates in the same session as approved changes.** Not as a follow-up. Every session that ships a feature ends with the relevant CLAUDE.md files updated.

12. **Strict build order with stop-and-report checkpoints.** Each step is confirmed working before the next begins.

13. **Per-platform job lock, DB as the single lock source.** One job per platform at a time; NT8 and MT5 lock independently; stale `running` rows are reset on boot. Stress tests additionally lock by market (one futures + one forex at most).

14. **No ORM, no task queues, no extra frameworks.** Raw `sqlite3`, asyncio for the queue loop, `subprocess` for SSH. New dependencies require explicit discussion first. Heavy data (equity curves, trade lists) lives in JSON files on disk, not in SQLite.

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
