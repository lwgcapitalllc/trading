# LWG Capital — Project State Snapshot
**Last updated:** 2026-06-10
**Source:** live repo state — verified against filesystem, DB, and CLAUDE.md files

> Hand this document to any new Claude.ai chat as the first message, along with
> `LWG_Roadmap_And_Open_Questions.md`. Together they replace the need to re-explain
> the project from scratch.

---

## What this project is

LWG Capital is a personal algorithmic trading operation. The near-term goal is to pass LucidFlex (and similar) prop firm evaluation challenges. The long-term goal is to run 30–50 funded prop accounts. The working method is S.Y.S.T.E.M. — a six-step process for building any strategy: Specify, Yield (gather data), Simulate (backtest), Test (stress test), Execute (live demo), Manage (monitor funded). Today the focus is futures trading via NinjaTrader 8 backtesting and prop evals, with MT5 forex as a parallel research track. The core platform (command center) is feature-complete; the remaining work is running strategies through the full evaluation pipeline until one earns a funded account.

---

## Stack and infrastructure

**Mac development environment:**
- FastAPI backend (`command-center/backend/`, port 8000) — owns all SQLite state and is the only process that touches the filesystem or the VPS.
- React + Vite + TypeScript frontend (`command-center/frontend/`, port 5173) — talks to the backend via the `/api` Vite proxy.
- SQLite (`command-center/backend/data/lab.db`) — strategies, rulesets, runs, evaluations, optimizations, stress tests, job queue.
- VS Code + Claude Code (primary dev tools).
- Claude.ai chat (architecture and planning discussions).
- GitHub — single monorepo, `main` branch for all development.

**Windows VPS (ForexVPS):**
- NinjaTrader 8 — backtest engine, Strategy Analyzer, and native optimizer.
- `nt8_agent.py` (port 8765 via SSH tunnel) — Flask HTTP bridge; `pywinauto` drives the NT8 WPF UI.
- `mt5_agent.py` (port 8766 via SSH tunnel) — Flask HTTP bridge; drives the MT5 Strategy Tester.
- Four live MT5 forex/gold trading bots (`algos/`) — demo phase on PU Prime accounts.
- Windows Task Scheduler — `NT8Agent` (NT8 agent), `MT5AgentRDP` (MT5 agent), `SYS_STARTUP` (bots).

**SSH tunnel:** `start.sh` opens a persistent `ssh -N forexvps` background process. `LocalForward 8765` (NT8 agent) and `LocalForward 8766` (MT5 agent) use `127.0.0.1` as the remote target — not `localhost` — because the VPS resolves `localhost` to IPv6 but the Flask agents bind IPv4 only.

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
Monte Carlo (10k reshuffles + 1k bootstrap of the trade list, pure Python, ~5s). Walk-forward (N windows of in-sample/out-of-sample NT8 backtests measuring Sharpe degradation). Sensitivity (each numeric param shifted, one VPS backtest per shift — 4 shifts for NT8, 2 for MT5). A–F robustness grade with plain-English reasons. Auto-trigger runs Monte Carlo only on Tier 1 wins; manual trigger runs all three phases. A Telegram notification fires after the grade is written.

### Speed Steps 1–3 — Native optimizer, rescoring, grid sensitivity, native walk-forward ✅
Native NT8 optimizer became the only search path (brute/genetic removed). Rescoring uses `MaxDailyLoss` from fixed params as the effective per-period drawdown (NT8's cumulative drawdown is not comparable to a prop firm's daily limit) plus a win-rate CSV format fix. Grid sensitivity is computed from optimizer neighbor combos with no extra VPS runs. Native walk-forward mode (`BacktestType = Walk Forward`) added to `nt8_backtest_runner.py`.

### Pass 1 — Foundational Config injection ✅
Rulesets carry 10 foundational fields (risk %, halt fraction, max consecutive losses, entry hours ET, days allowed, daily profit target, lock-in %, commission per side, slippage ticks). They are injected into strategy params at run creation. Every parameter is categorized as `Strategy Logic` (tunable, optimizer-visible) or `Foundational` (injected, hidden in the UI). Strategies hold sentinel default values and refuse to trade if injection fails.

### Pass 2 — Strategy Deployment Manager ✅
Upload, delete, and compile NT8 `.cs` strategy files from the UI without RDP. The NT8 agent gained file-management plus F5-compile endpoints (pywinauto via the NinjaScript Editor; success detected by polling `NinjaTrader.Custom.dll` mtime). Lock detection returns HTTP 423 if NT8 has the file open. Upload limit 256 KB.

### Pass 2 (repo-wide) — strategies subsystem groundwork ✅
The groundwork pass that established generic, firm-agnostic strategies and the Strategy Logic / Foundational categorization convention across all strategy files, so the same source runs against any ruleset.

### Pass 2.5 — Strategies subsystem + Deploy button ✅
Created `strategies/` as a top-level subsystem and moved the strategy files out of `algos/`. The scanner reads from `strategies/`. A one-click Deploy button per strategy uploads the file to the VPS (`.cs` to the NT8 agent, `.mq5` to the MT5 agent). `source_path` is stored relative to the monorepo root. The Strategies / Rulesets / Deployed pages were split out from Backtests.

### Speed Steps 4–6 — MT5 native optimizer, Telegram, job queue ✅
MT5 native optimizer runs combos as sequential single backtests (MT5's `Optimization=1` CLI mode writes no parseable file — it only populates the GUI tab). MT5 native walk-forward uses `ForwardMode` in the ini. `services/notify.py` sends Telegram grade notifications (same token/chat as `algos/shared/notify.py`). A `job_queue` SQLite table plus an asyncio queue runner dispatches one optimization or stress test at a time, surfaced in a Queue page.

### M4 — Regime tagging + equity overlay + optimizer regime filter + platform lock ✅
Every backtest's daily P&L entries are tagged with a regime label using `regime/classifier.py`, run as a visible Tagging pipeline step. A Performance by Regime table appears on BacktestDetail, plus an equity-curve regime overlay and an optimizer regime filter that re-scores combos using only matching-regime trades. Platform-based job lock: NT8 and MT5 lock independently. Cascade delete on runs. Sweeps and optimizations nest under their source run in the Runs tab. Tab-specific active dots.

### M5 / Steps 1–9 — MT5 runner + deployment ✅
`mt5_agent.py` on VPS port 8766: health, Strategy Tester driver (ini + set file, `terminal64.exe`, HTML report parser). `mt5_agent_client.py` typed wrapper on the backend. The dispatcher routes to the MT5 agent when `strategy.runner == "mt5"`. MT5-aware backtest modal (free-text symbol, bar presets, no ruleset/foundational sections) and MT5-aware detail page (MT5 pipeline steps, UTF-16 HTML parsing, KPI injection from the trades list). Runner badges (NT8/MT5), a market filter bar (Futures/Forex), and MT5 deployment (upload/delete `.mq5`, compile via MetaEditor64).

### BacktestDetail polish and platform improvements (2026-06-06 – 2026-06-09) ✅
Rerun button on the detail header. Stale-progress guard (trusts progress only when `job_id` matches). Milestone-dot progress bar. Equity-curve gradient based on start versus end equity. Shared `StatusPill` component. OptimizationDetail 3-view toggle (Table / Bar Chart / Heatmap). Full backtest on an optimizer combo (progress bar wired, visible in the Runs tab while active, tab-pulse and regime-tag fixes). NT8 opt-config speedup (grid map built once instead of per-param). Optimization log persistence to `opt_log.txt`. Copy buttons on all log terminals. Optimization re-run button that resets the existing record in place. Timer freeze fix on failed optimizations. Integer-param validation in the optimizer modal (blocks decimal min/max/step on `int` NinjaScript params, sourced via `GET /strategies/{id}/param-types`).

---

## Current state of strategies

Four strategies are registered. Three are NinjaTrader `.cs` files, one is an MT5 `.mq5` file.

| Strategy | File | Runner | Category | Grade / perf facts |
|---|---|---|---|---|
| ORB | `strategies/ninjatrader/ORB.cs` | ninjatrader | breakout | No graded runs yet. Opening Range Breakout — entry on ORB high/low break. Optimizer parity confirmed with single-run path on ORMinutes=50 / TpMultiple=5. |
| VWAP_MR | `strategies/ninjatrader/VWAP_MR.cs` | ninjatrader | mean_reversion | No graded runs yet. Fades extended moves back to VWAP. |
| Momentum | `strategies/ninjatrader/Momentum.cs` | ninjatrader | momentum | Recent runs on MCL 06-26 graded TIER_3_DISCARD; best stress test grade so far is F. EMA crossover trend-follower. `MaPeriod` is `int` — decimal optimizer steps produced 0 trades, now blocked in the UI. |
| MeanReversion | `strategies/mt5/MeanReversion.mq5` | mt5 | mean_reversion | Smoke-tested on EURUSD H1 and GBPJPY. MT5 runs without ruleset evaluation, so no worthiness tier. Ported from `algos/bots/bot_mean_reversion.py` — BB + RSI + intraday VWAP confluence. |

`strategies/tradovate/` is an empty placeholder (no source files yet).

The M4 regime breakdown is computed per run, not per strategy — there is no documented strategy-level regime profile yet because no NT8 strategy has reached a clean Tier 1 run.

---

## Current state of rulesets

15 rulesets in `lab.db` as of 2026-06-10:
- `prop_eval`: 6 rows
- `prop_funded`: 6 rows
- `personal`: 2 rows
- `demo`: 1 row

Evaluator behavior by type: `prop_eval` checks drawdown + profit target + consistency; `prop_funded` checks drawdown only (PASS if under limit); `personal` checks daily and weekly loss caps (WARN if weekly breached); `demo` always PASS/WARN on net P&L, never DISCARD.

Prop-firm seeding track: the eval/funded rows come in firm pairs (LucidFlex, Tradeify, FundedNext were the original seed set, each with an eval and a funded ruleset). Adding a prop firm means adding both its eval and funded rulesets with the firm's `docs_url` filled in so the rules can be verified later.

---

## Architectural principles locked in

1. **One backtest, N verdicts.** A single run is evaluated against multiple rulesets at once. Never run the same strategy N times for N firms. Only the first (primary) ruleset injects foundational config; the rest evaluate only.

2. **Generic strategies, ruleset-injected config.** No firm-specific defaults in strategy files. Account size, daily loss cap, commission, slippage, and entry config are all injected at run creation. Sentinel values prevent trading if injection fails.

3. **Categorized parameters.** `Strategy Logic` = tunable and optimizer-visible. `Foundational` = injected from the ruleset and hidden in the UI.

4. **One shared regime classifier.** `regime/classifier.py` is canonical. Never duplicate it; all consumers import from there.

5. **NT8 is both the backtest and the execution engine for futures; MT5 is the parallel forex track.** The same command center dispatcher routes to both via runner-aware clients.

6. **Observability is mandatory.** Every run writes progress, logs, and output files. Optimization runs persist their VPS logs. Progress bars are wired to real agent output, not faked.

7. **CLAUDE.md updates in the same session as approved changes.** Not as a follow-up. Every session that ships a feature ends with the relevant CLAUDE.md files updated.

8. **Strict build order with stop-and-report checkpoints.** Each step is confirmed working before the next begins.

9. **Per-platform job lock.** Only one job (backtest/sweep/optimization/stress test) runs per platform at a time; NT8 and MT5 lock independently. Stress tests additionally lock by market (one futures and one forex stress test at most).

10. **No ORM, no task queues, no extra frameworks.** Raw `sqlite3`, asyncio for the queue loop, `subprocess` for SSH. New dependencies require explicit discussion first. Heavy data (equity curves, trade lists) lives in JSON files on disk, not in SQLite.

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
