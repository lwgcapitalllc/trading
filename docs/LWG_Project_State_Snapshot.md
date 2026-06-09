# LWG Capital — Project State Snapshot
**Last updated:** 2026-06-09
**Source:** live repo state — verified against filesystem, DB, and CLAUDE.md files

> Hand this document to any new Claude.ai chat as the first message, along with
> `LWG_Roadmap_And_Open_Questions.md`. They replace the need to re-explain the
> project from scratch.

---

## What this project is

LWG Capital is a personal algorithmic trading operation. The near-term goal is to pass LucidFlex prop firm evaluation challenges and build toward 30–50 funded accounts. The methodology is S.Y.S.T.E.M. — a six-step process for building any strategy: Specify, Yield (gather data), Simulate (backtest), Test (stress test), Execute (live demo), Manage (monitor funded). Today the focus is futures trading via NinjaTrader 8 backtesting, with MT5 forex as a parallel research track. The core platform (command center) is feature-complete; the remaining work is running strategies through the full evaluation pipeline until one earns a funded account.

---

## Stack and infrastructure

**Mac development environment:**
- FastAPI backend (`command-center/backend/`, port 8000)
- React + Vite + TypeScript frontend (`command-center/frontend/`, port 5173)
- SQLite (`data/lab.db`) — strategies, rulesets, runs, evaluations, optimizations, stress tests
- VS Code + Claude Code (primary dev tools)
- Claude.ai chat (architecture and planning discussions)

**Windows VPS (ForexVPS):**
- NinjaTrader 8 — backtest + Strategy Analyzer + optimization engine
- `nt8_agent.py` (port 8765 via SSH tunnel) — Flask HTTP bridge; pywinauto drives the NT8 UI
- `mt5_agent.py` (port 8766 via SSH tunnel) — Flask HTTP bridge; drives MT5 Strategy Tester
- Four live MT5 trading bots (`algos/`) — demo phase on PU Prime accounts
- Windows Task Scheduler — `LucidFlexAgent` (NT8 agent), `MT5AgentRDP` (MT5 agent), `SYS_STARTUP` (bots)

**SSH tunnel:** `start.sh` opens a persistent `ssh -N forexvps` background process. `LocalForward 8765` (NT8 agent) and `LocalForward 8766` (MT5 agent) use `127.0.0.1` as remote target — not `localhost` — because the VPS resolves `localhost` to IPv6 but Flask agents bind IPv4 only.

---

## Monorepo structure

```
trading/
├── algos/           ← Four live MT5 forex/gold bots on VPS (demo phase)
├── smart-money/     ← Crypto/forex trader scanner for copy-trading candidates
├── command-center/  ← React + FastAPI local operations platform (fully live)
├── regime/          ← Shared market regime classifier (live bots + backtest lab)
├── strategies/      ← Generic strategy source files (.cs NT8, .mq5 MT5)
├── scripts/         ← VPS bootstrap and full-recovery scripts
└── docs/            ← Cross-subsystem reference docs and audit tools
```

`algos/`, `smart-money/`, and `command-center/` are fully independent. `regime/` is shared by `algos/` (via thin shim) and `command-center/` (directly). `strategies/` is consumed by `command-center/` (scanner + deploy) and deployed to the VPS.

---

## What's shipped (chronological)

### App shell + Smart Money + Bots monitor (pre-M1)
First working command center. React shell with sidebar routing, Bots tab (SSH monitor for gold_main/gold_scalper/gold_fft, risk cap deploy, Telegram users), and the full Smart Money pipeline UI (scan, terminal, rankings, candidate profiles, disqualified log, config, cache). Smart Money stages 1–2 and 5 are live; stages 3–4 are blocked on API keys.

### M1 — Backtests Lab (strategy registry + runs + evaluations)
Strategies tab scans `strategies/` for `.cs` and `.mq5` files. Users select a strategy, instrument, date range, and rulesets to evaluate against. NT8 runs the backtest; results (equity curve, daily P&L, trade list) stored under `reports/lab/`. Per-ruleset evaluations (PASS/WARN/DISCARD) fire on completion.

### M2 — Worthiness badges, instrument sweeps, parameter optimizer
Tier 1/2/3 worthiness scoring based on profit factor and drawdown vs firm limits. Instrument sweeps run N sequential backtests across multiple instruments. Native NT8 optimizer fires one grid job using all CPU cores, exports the CSV results grid, scores every combo by our objective function. Tier 3 warning modal routes users to sweep untested instruments.

### M3 — Stability and retry UX
Sweep cancel endpoint. Retry-all and per-run retry on sweeps and optimizations. SweepDetail visual parity with OptimizationDetail (ProgressCard with segmented bar, elapsed timer). Contract month propagation fix (`withContractMonth()` stamps e.g. "MNQ" → "MNQ 06-26").

### M3 Stress Tests — Monte Carlo, walk-forward, sensitivity, A–F grading
Monte Carlo: 10k reshuffles + 1k bootstrap of the trade list (~5s, pure Python). Walk-forward: N windows of IS/OOS NT8 backtests measuring Sharpe degradation. Sensitivity: each numeric param shifted ±10%/±25%, one VPS backtest per shift (2 shifts for MT5, 4 for NT8). A–F grade. Auto-triggers MC on Tier 1 wins; manual trigger runs all three phases. Telegram notification after grade is written.

### Speed Steps 1–3 — Native NT8 optimizer, rescoring, grid sensitivity, native walk-forward
Step 1: native NT8 optimizer becomes the only search path. Step 2: rescoring — NT8 cumulative drawdown replaced with `MaxDailyLoss` from fixed params for daily drawdown evaluation; win-rate CSV format fix. Step 3: grid sensitivity computed from optimizer neighbor combos (no extra VPS runs); native walk-forward mode (`BacktestType=Walk Forward`) added to `nt8_backtest_runner.py`.

### Pass 1 — Foundational Config injection
Rulesets carry 10 foundational fields (risk %, halt fraction, max consecutive losses, entry hours, days allowed, daily target, lock-in %, commission, slippage). Injected into strategy params at run creation. Parameters categorized as `Strategy Logic` (optimizer-visible) or `Foundational` (injected, hidden). Strategies include sentinel guard values that refuse to trade if injection fails.

### Pass 2 — Strategy Deployment Manager
Upload, delete, and compile NT8 `.cs` strategy files from the UI without RDP. NT8 agent extended with file management + F5-compile endpoints (pywinauto via NinjaScript Editor; success detected by polling `NinjaTrader.Custom.dll` mtime). Lock detection: HTTP 423 if NT8 has the file open.

### Pass 2.5 — Strategies subsystem + Deploy button
Created `strategies/` as a top-level subsystem. Strategy files moved from `algos/`. Scanner reads from `strategies/`. One-click Deploy button per strategy uploads the file to the VPS. `source_path` stored relative to monorepo root.

### Speed Steps 4–6 — MT5 native optimizer, Telegram, job queue
Step 4: MT5 native optimizer uses sequential single backtests (MT5 GUI `Optimization=1` does not write a parseable file — sequential HTML-report runs are the only reliable path). MT5 native walk-forward uses `ForwardMode` ini. Step 5: `services/notify.py` sends Telegram grade notifications. Step 6: `job_queue` SQLite table + asyncio queue runner dispatches one optimization or stress test at a time. Queue page in frontend.

### M4 — Regime tagging + equity overlay + optimizer regime filter + platform lock
Every backtest's daily P&L entries tagged with regime labels using `regime/classifier.py`. Visible Tagging pipeline step. Performance by Regime table on BacktestDetail. Equity curve regime overlay. Optimizer regime filter re-scores combos using only matching-regime trades. Platform-based job lock: NT8 and MT5 lock independently. Cascade delete on runs. Sweeps nested under source run in Runs tab. Tab-specific active dots.

### M5 / Steps 1–9 — MT5 runner + deployment
`mt5_agent.py` on VPS port 8766: health, Strategy Tester driver (ini+set file, `terminal64.exe`, HTML report parser). `mt5_agent_client.py` typed wrapper on backend. Dispatcher routes to MT5 agent when `strategy.runner == "mt5"`. MT5 backtest modal (free-text symbol, bar presets, no ruleset). MT5 backtest detail (MT5-specific pipeline steps, UTF-16 HTML parsing, KPI injection from trades list). Runner badges (NT8/MT5). Market filter bar. MT5 deployment: upload/delete `.mq5`, compile via MetaEditor64.

### BacktestDetail polish and platform improvements (2026-06-06 – 2026-06-09)
Rerun button on detail header. Stale progress guard (`job_id` match). Progress bar with milestone-dot track. Equity curve gradient based on start vs end equity. Shared `StatusPill` component. OptimizationDetail 3-view toggle (Table / Bar Chart / Heatmap). Full backtest on opt combo: progress bar wired, visible in Runs tab while active, tab pulse fix. NT8 opt config speedup (grid map built once instead of per-param). Optimization log persistence (`opt_log.txt`). Copy buttons on all log terminals. Optimization re-run button (resets in-place, no new record created). Timer freeze fix on failed optimizations. Integer param validation in OptimizerModal (warns and blocks non-integer min/max/step on `int` NinjaScript params, sourced via `GET /strategies/{id}/param-types` endpoint that parses `.cs`/`.mq5` source files).

---

## Current state of strategies

| Strategy | File | Runner | Category | DB Status |
|---|---|---|---|---|
| ORB | `strategies/ninjatrader/ORB.cs` | ninjatrader | breakout | No graded runs in DB |
| VWAP_MR | `strategies/ninjatrader/VWAP_MR.cs` | ninjatrader | mean_reversion | No graded runs in DB |
| Momentum | `strategies/ninjatrader/Momentum.cs` | ninjatrader | momentum | Recent runs on MCL 06-26: TIER_3_DISCARD. Best stress test grade: F |
| MeanReversion | `strategies/mt5/MeanReversion.mq5` | mt5 | mean_reversion | Recent runs on GBPJPY.s (no worthiness tier — MT5 runs without ruleset evaluation). Smoke-tested. |

`strategies/mt5/TestOptPass.mq5` exists on disk but is not documented in `strategies/CLAUDE.md`. Its purpose is unverified — TODO: confirm and document or delete.

Momentum's `MaPeriod` parameter is `int` in NinjaScript. Optimization runs that used decimal steps (e.g. 2.5) produced 0 trades and failed to export. The UI now enforces integer-only values on `int` params.

---

## Current state of rulesets

15 rulesets in `lab.db` as of 2026-06-09:
- `prop_eval`: 6 rows
- `prop_funded`: 6 rows
- `personal`: 2 rows
- `demo`: 1 row

`backend/CLAUDE.md` documents 13 seeded rows (4 LucidFlex + 4 Tradeify + 4 FundedNext + 1 personal). DB shows 15 — 2 extra rows added after that doc was written. TODO: verify which firm/type was added.

---

## Architectural principles locked in

1. **One backtest, N verdicts.** One run evaluated against multiple rulesets simultaneously. Never run the same strategy N times for N firms.

2. **Generic strategies, ruleset-injected config.** No firm-specific defaults in strategy files. Account size, daily loss cap, commission, slippage, and entry config all injected at run creation. Sentinel values prevent trading if injection fails.

3. **Categorized parameters.** `Strategy Logic` = tunable, optimizer-visible. `Foundational` = injected from ruleset, hidden in UI.

4. **One shared regime classifier.** `regime/classifier.py` is canonical. Never duplicate it. All consumers import from there.

5. **NT8 is the primary backtest engine; MT5 is the parallel forex track.** The same command center dispatcher routes to both via runner-aware clients.

6. **Observability is mandatory.** Every run writes progress, logs, and output files. Optimization runs persist VPS logs. Progress bars are wired to real agent output.

7. **CLAUDE.md updates in the same session as approved changes.** Not as a follow-up. Every session that ships a feature ends with updated CLAUDE.md files.

8. **Strict build order with stop-and-report checkpoints.** Each step is confirmed working before the next begins.

9. **NT8 SA global lock.** Only one job type (backtest/sweep/optimization) runs per platform at a time. NT8 and MT5 lock independently.

10. **No ORM, no task queues, no extra frameworks.** Raw `sqlite3`, asyncio for the queue loop, `subprocess` for SSH. New dependencies require explicit discussion first.

---

## Communication rules with Claude Code

- Plain English. Short sentences. No bullet points for simple explanations.
- No preamble ("Great question!", "Sure, I can help with that").
- One clear question at a time. Present options concisely when they exist.
- Stop after each numbered implementation step and report results.
- Smallest viable change first — no refactoring, abstractions, or speculative features beyond what the task requires.
- CLAUDE.md files are updated in the same session as approved changes.

---

## What's NOT done

See `docs/LWG_Roadmap_And_Open_Questions.md` for the forward plan, deferred items, open questions, and parallel tracks.
