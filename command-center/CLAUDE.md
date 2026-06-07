# CLAUDE.md — Command Center

Local operations platform for LWG Capital. Two-process app: React frontend (`:5173`) → FastAPI backend (`:8000`). The backend is the only process that touches the filesystem or the VPS — the frontend never does.

**Last reviewed:** 2026-06-07 (Pass Speed Steps 4–6)

Sub-directory CLAUDE.md files are auto-loaded when editing files in those directories:
- `backend/CLAUDE.md` — Python conventions, router rules, SQLite patterns, VPS interaction
- `frontend/CLAUDE.md` — hook patterns, component rules, theme tokens, routing

---

## Repo structure

```
command-center/
├── backend/
│   ├── main.py            FastAPI entry point; registers all routers
│   ├── config.py          loads config.json → typed module constants
│   ├── config.json        machine-specific paths only (no credentials)
│   ├── models.py          all Pydantic models in one file
│   ├── routers/           one file per domain
│   ├── services/          business logic, DB access, VPS client
│   ├── data/lab.db        SQLite — strategies, rulesets, runs, evaluations
│   └── reports/lab/       run output files (equity curves, logs)
├── frontend/
│   └── src/
│       ├── api/client.ts  only place fetch() lives
│       ├── types/index.ts mirrors all Pydantic models
│       ├── hooks/         one file per domain
│       ├── components/    shared UI primitives
│       └── pages/         one file (or folder) per route
└── start.sh               starts both processes
```

---

## How to run

```bash
cd command-center
./start.sh
# Frontend: http://localhost:5173
# Backend API docs: http://localhost:8000/docs
```

`start.sh` creates the Python venv and runs `npm install` on first launch.

**SSH tunnel** — `start.sh` opens a persistent `ssh -N forexvps` background process on launch. This keeps two LocalForwards alive: `8765` (NT8 nt8_agent_tunnel) and `8766` (MT5 mt5_agent_tunnel). Without the tunnel, both nt8_agent_client and mt5_agent_client calls fail even though SSH itself appears healthy. The tunnel is killed automatically on Ctrl-C. **Important:** the `-L` flags must use `127.0.0.1` (not `localhost`) as the remote target — the VPS resolves `localhost` to `::1` (IPv6) but Flask agents bind only `127.0.0.1` (IPv4). Both `start.sh` and `_restart_tunnel()` in `system.py` use `127.0.0.1` explicitly.

**Auto-start agents** — `main.py` spawns a daemon thread on startup (8s delay to let the tunnel establish) that calls `/health` on each agent and fires the schtask for any that don't respond. NT8 agent: `LucidFlexAgent`. MT5 agent: `MT5AgentRDP`. If SSH is not yet up the thread silently skips — red dots remain clickable.

**Backtesting prerequisites** — before submitting a run, the SSH tunnel and NT8 agent must be up. See Sidebar health indicators below.

---

## Key design decisions

**Config translation layer** — Smart Money pipeline stores fractional values (`win_rate: 0.75`), UI shows percentages. `_pipeline_cfg_to_api()` and `_api_cfg_to_pipeline()` in `routers/smart_money.py` handle conversion. The API contract is the stable interface.

**Batched VPS snapshot** — `GET /bots/snapshot` makes two SSH calls and returns one `BotSnapshot`. Frontend polls at 60s. Never SSH per-bot.

**No auto-commit** — `PUT /smart-money/config` writes the file only. The user decides when to commit via `GET /smart-money/config/git-status`.

**Bot risk cap deploy** — `PATCH /bots/{name}/caps` writes `algos/shared/thresholds.json` + instance `config.json`, commits both, pushes to VPS, restarts the bot, sends Telegram notification. All in one endpoint.

**Lab experiment model** — user always specifies which rulesets to evaluate against. The system never auto-evaluates against all rulesets. `evaluate_rulesets` is always set explicitly.

---

## What is built and live

| Module | Status |
|---|---|
| App shell — sidebar, topbar, routing | ✅ |
| Overview — stat row + Bots + Smart Money + Backtests cards | ✅ |
| Smart Money — full pipeline UI (scan, terminal, rankings, profiles, disqualified, config, cache) | ✅ |
| Bots — monitor, control (global + per-bot), configure (risk caps + deploy), users (Telegram) | ✅ |
| Backtests lab — Runs / Sweeps / Optimizations tabs; run modal; BacktestDetail; verdict pills; delete | ✅ |
| Backtests lab — runs tab duration column; prominent Stop button; live log streaming (2 s poll during active runs) | ✅ |
| Backtests lab M2 — worthiness badges (Tier 1/2/3) on every completed run | ✅ |
| Backtests lab M2 — instrument sweeps (N sequential runs via SA semaphore, Sweep Detail page with live sort-by-tier) | ✅ |
| Backtests lab M2 — parameter optimizer (brute force + genetic, Optimization Detail with ranked results table, ★ best row) | ✅ |
| Backtests Speed Step 1 — native NT8 optimizer path (`search_method="native"`): one VPS job, all CPU cores, export CSV results grid, create run rows on return. VPS: `nt8_backtest_runner.run_native_optimize_mode` switches SA to Optimization mode, sets param ranges as `lo;hi;step` format (fixed params use `value;value;1`), exports results. Agent: `POST /native-optimize`, `GET /jobs/{id}/native-opt-results`, `GET /optimize-mode-dump?strategy=X` diagnostic. Backend: `run_native_optimization()` in `optimization_runner.py`. Guard: native method rejected for MT5 strategies. No auto-trigger stress test (no per-combo equity curve). Parity check confirmed: ORB ORMinutes=50 TpMultiple=5 → NT8 optimizer and single-run paths agree to $0.01. | ✅ |
| Backtests Speed Step 2 — re-score native opt shortlist with real objective: (1) Wide cut: top 25% of combos by NT8's native rank (30 of 120 for a 12×10 grid). (2) Drawdown substitution: NT8 "Max. drawdown" is cumulative peak-to-trough — not comparable to prop firm's daily `max_loss_eod`. `run_native_optimization` substitutes `MaxDailyLoss` from `fixed_params` as the effective per-period drawdown when evaluating and tiering native combo rows. (3) Win-rate fix: NT8 CSV already reports as fraction (0.327); VPS parser no longer divides by 100 when value < 1. Scoring via `eval_pass_probability` / `funded_sharpe` / `raw_pf` per mode — winner picked by our objective, not NT8's built-in rank. Worthiness Tier 1/2/3 auto-assigned per combo. | ✅ |
| Backtests lab M2 — Tier 3 warning modal with smart instrument routing | ✅ |
| Backtests lab M2 — runner field on strategies; nt8_agent_client dispatcher for future MT5 support | ✅ |
| Backtests lab M2 — Sweeps tab (list view with count badge, progress, status, delete) | ✅ |
| Backtests lab M2 — Optimizations tab (delete; count badge; Runs tab nests child runs under source run via `source_run_id`) | ✅ |
| Backtests lab M2 — global NT8 SA lock: only one job type (backtest/sweep/optimization) may run at a time; 409 with clear message | ✅ |
| Backtests lab M2 — Overview Backtests card shows optimization count, Tier 1 passes, running optimization banner, best PF result | ✅ |
| Backtests lab M3 — sweep cancel endpoint + Cancel button (recovers sweeps stuck at `running` after backend restart) | ✅ |
| Backtests lab M3 — sweep retry-all + per-run retry; optimization per-run retry; `POST /backtests/runs/{id}/retry` context-aware | ✅ |
| Backtests lab M3 — SweepDetail visual parity with OptimizationDetail (ProgressCard, segmented bar, elapsed timer, status icons) | ✅ |
| Backtests lab M3 — contract month propagation fix: `withContractMonth()` in Tier3WarningModal stamps root symbols (e.g. "MNQ" → "MNQ 06-26") | ✅ |
| Backtests lab M4 — sweeps nest under source run in Runs tab (`source_run_id` on sweep child runs; `SweepNestRow` component) | ✅ |
| Backtests lab M4 — cascade delete: deleting a run also deletes linked sweeps and optimizations; warning shown before confirm | ✅ |
| Backtests lab M4 — active job indicator: pulsing dot on Runs/Sweeps/Optimizations tabs when any job is running | ✅ |
| Backtests lab M4 — header redesign: instrument chip accent-colored and first; bar/commission chips removed; chips consolidated | ✅ |
| Backtests lab M4 — log terminal success color matches SmartMoney (cyan dot + "· complete" label when run finishes) | ✅ |
| Backtests lab M4 — Platform-based job lock: NT8 and MT5 lock independently (`RunningJobStatus.nt8` / `.mt5`). Lock checked in RunBacktestModal, OptimizeButton, Tier3WarningModal, RunRow retry button (Backtests.tsx), and Retry/Rerun button (BacktestDetail.tsx). `BacktestSummary.runner` added so RunRow knows which platform to check. `Strategies.tsx` calls `useRunningVpsJob()` at page level to keep cache warm (prevents modal opening with stale undefined state). All six job-lifecycle mutations invalidate `running-job` on success for immediate lock feedback. **Bug:** `_row_to_summary` was not mapping `runner` from the DB row into the Pydantic model, so every run arrived at the frontend with `runner = undefined`, making `isMt5` always false — all retry buttons disabled during any NT8 job regardless of platform. Fixed by adding `runner: str = "ninjatrader"` to `BacktestSummary` (models.py) and `runner=row.get("runner", "ninjatrader")` to `_row_to_summary` (backtests.py). | ✅ |
| MT5 optimization (raw mode): `OptimizerModal` is MT5-aware — hides Ruleset/Mode/Regime selectors, sends `ruleset_id: null` and `mode: "raw"`. Backend: `raw_profit_factor` objective (maximises PF, no firm needed). `optimizations.ruleset_id` migrated to nullable (`_migrate_optimizations_nullable_ruleset` table-recreation). `OptimizationRequest.ruleset_id: Optional[str]`. Router skips ruleset lookup when null; uses MT5 lock when strategy runner is MT5. `optimization_runner` handles null firm throughout (run_optimization, retry_single, retry_failed). `OptimizationSummary/Detail.ruleset_id` nullable — detail page shows "Raw PF" chip when null. `insert_run_optimization` and `insert_run_sweep` do not set runner on child rows (defaults to ninjatrader; correct for NT8 jobs). | ✅ |
| Backtests lab M4 — Runs table: "Verdicts" column renamed "Challenge", shows firm name only; "Score" column shows worthiness tier (no duplication). Per-row trash icon removed (redundant — bulk checkbox delete covers it). Inline Play (Retry) button added per row; fires `POST /backtests/runs/{id}/retry`. Deployed tab count now uses `syncStatus`-filtered file count (was showing all VPS files including platform defaults). | ✅ |
| Stress Tests | ✅ Live | Monte Carlo (10k reshuffles + 1k bootstrap), walk-forward (N NT8 windows or native WF), sensitivity (±10%/±25% per param or free grid read), A–F grade, auto-trigger on Tier 1 + optimizer winners |
| Backtests Speed Step 3 — native opt powers stress testing | ✅ | **(A) Grid sensitivity:** `_compute_grid_sensitivity()` in `optimization_runner.py` runs before the wide cut on all 120 combos; measures PF degradation for winner's neighbors in each ranged param; stores `grid_sensitivity_score` + `grid_sensitivity_summary` on the optimization row. `stress_tester._apply_grid_sensitivity_if_available()` populates sensitivity fields from the opt row (no NT8 backtests) when source run has `optimization_id`. **(B) Winner single backtest:** `_run_winner_backtest_for_mc()` auto-submits a full NT8 single-run backtest for the best combo after native opt completes; winner run has `optimization_id` set (links to grid sensitivity); always auto-triggers stress test on completion. **(C) Native walk-forward:** `run_native_walkforward_mode()` in `nt8_backtest_runner.py` sets BacktestType="Walk Forward", all params as `value;value;1` (no IS re-optimization), configures WF periods/OOS%; exports and parses WF results CSV. Agent: `POST /native-walkforward` + `GET /jobs/{id}/native-wf-results`. `stress_tester.run_walk_forward_task()` dispatches to `_run_native_walk_forward()` when source run has `optimization_id`. **WF auto_ids need VPS validation** (`OutOfSampleIterations`, `OutOfSamplePercentage`). |
| Backtests Speed Step 4 — MT5 native optimizer + walk-forward | ✅ | MT5 agent (`mt5_agent.py`) extended: `_run_mt5_optimization()` writes set file with `param=value\|\|1\|\|min\|\|step\|\|max` ranges + `Optimization=1` ini, runs terminal64, parses HTML combo table. `_run_mt5_forward_test()` uses `ForwardMode` in ini (2=50%OOS, 3=33%, 4=25%), parses IS and OOS KPI sections split at "forward" keyword boundary. Agent endpoints: `POST /native-optimize`, `GET /backtests/{id}/native-opt-results`, `POST /native-walkforward`, `GET /backtests/{id}/native-wf-results`. `mt5_agent_client.py` exposes matching typed wrappers. `nt8_agent_client` dispatcher updated: `start_native_optimization`, `native_opt_results`, `start_native_walkforward`, `native_wf_results` all accept `runner` param and route to MT5 client when `runner="mt5"`. `optimization_runner.run_native_optimization` reads `runner_str` from strategy and passes it through the entire poll loop. **HTML parsing needs VPS validation.** |
| Backtests Speed Step 5 — Telegram grade notification | ✅ | `services/notify.py` (new) — urllib-only Telegram sender; same token/chat as `algos/shared/notify.py`. `stress_tester.py` imports it and calls `_fire_grade_notification()` after `update_stress_test_grade()` in both the MC-only path and the full WF+sensitivity path. Message includes strategy name, instrument, grade letter, pass probability, worst-1% drawdown, and grade reasons. |
| Backtests Speed Step 6 — job queue | ✅ | `job_queue` SQLite table (`lab_db.py`) + 9 CRUD functions. `services/queue_runner.py` — asyncio loop, dispatches `optimization` and `stress_test` job types, runs one at a time. `routers/queue.py` — `GET /queue`, `POST /queue/optimization`, `POST /queue/stress-test`, `DELETE /queue/{id}` (pending only). `main.py` registers router + starts queue loop as asyncio task on startup. Frontend: `QueueItem` type, `hooks/useQueue.ts`, `pages/Queue.tsx`, `/queue` route, Queue nav item in sidebar (Research section). |
| Regime Tags (M4) | ✅ Live | Every backtest's `daily_pnl` entries are tagged with a regime label (TRENDING/TRANSITIONING/RANGING/HIGH_VOLATILITY/LOW_VOLATILITY/UNKNOWN). **Auto-tagged as a visible Tagging pipeline step** (runs before `update_run_complete` so the run stays `running` during tagging). Manual `BackfillRegimeButton` removed. Performance by Regime table on BacktestDetail. Equity curve regime overlay. Optimizer regime filter. |
| Pass 2 — Strategy deployment | ✅ Live | Upload, delete, and compile NT8 strategy files from the UI without RDP. NT8 agent extended with file management + compile endpoints. pywinauto F5 compile via NinjaScript Editor. |
| Pass 2.5 — Strategy location + deploy button | ✅ Live | `strategies/` top-level subsystem. Files moved from `algos/`. Scanner updated. One-click Deploy button per strategy in Strategies tab. Strategies / Rulesets / Deployed nav page split from Backtests. Tab counts, platform column, trash-can delete on Deployed tab. |
| Steps 1-7 — MT5 runner | ✅ Live | `mt5_agent.py` on VPS (port 8766) — health/status, historical data, Strategy Tester driver (ini+set file, terminal64.exe, HTML report parser). `mt5_agent_client.py` on backend. `nt8_agent_client` dispatches backtests to MT5 agent when `strategy.runner == "mt5"`. `_nt8_to_mt5_spec` passes `job_id` through so MT5 agent stores job under our run_id (bug: without this, all status polls returned 404 and every run timed out). MT5 agent `POST /backtests` accepts client `job_id` if provided, else generates UUID. Timeframe mapping: M1/M5/M15/M30/H1/H4/D1. `MeanReversion.mq5` smoke-tested. **MT5 agent VPS env vars (set in MT5AgentRDP Task Scheduler task):** `MT5_DATA_DIR=C:\Users\Administrator\AppData\Roaming\MetaQuotes\Terminal\927F99AD709B93AD91622378376929BE` (MT5_Lab AppData). `TERMINAL_PATH` not required — `_get_tester_exe()` resolves the lab exe from `MT5_DATA_DIR/origin.txt` (contains `C:\MT5_Lab`). **Bug fixes (2026-06-05):** (1) `_alog` wrapped `print()` in try/except OSError — Task Scheduler has no stdout; the bare print caused OSError which propagated out of POST /backtests synchronously, returning 500 before Flask could respond 202. (2) `_get_tester_exe()` now reads `MT5_DATA_DIR/origin.txt` as resolution step 2 (before the `terminal_info()` fallback that was returning `C:\MT5_FFT\terminal64.exe`, the live FFT bot terminal). **(2026-06-06):** (3) MT5 HTML reports are written as UTF-16 LE (BOM `\xff\xfe`) — `read_text(encoding="utf-8")` produced garbage; detect BOM and decode as `utf-16`. (4) After report is parsed, `_kill_by_path(tester_exe)` called as belt-and-suspenders alongside `ShutdownTerminal=1` in the ini to ensure MT5_Lab closes. (5) `_normalize_mt5_results` (backend) injects sequential `index` into each equity curve point (Pydantic `EquityPoint.index: int` is required). |
| Step 8 — Runner badges + market filter | ✅ Live | `RunnerBadge` component shows NT8/MT5 on each strategy row. `MarketFilterBar` on Strategies and Runs tabs filters to Futures or Forex. Instrument→market mapping: MT5 runner → Forex, all others → Futures. |
| Step 9 — MT5 deployment manager | ✅ Live | Upload/delete `.mq5` files via MT5 agent. `POST /strategy-files/compile-mt5` triggers `metaeditor64.exe /compile:<experts_dir>` async; polls log for `N error(s)`. Drop zone in Deployed tab accepts `.mq5`. "Compile MT5" button (purple) appears when MT5 files are present. sync_status checks MT5 agent for `runner=mt5` strategies. |
| MT5 backtest modal | ✅ Live | `RunBacktestModal` is fully MT5-aware when `strategy.runner === 'mt5'`: free-text symbol input with preset buttons (EURUSD/GBPUSD/…), bar presets [5m/15m/30m/1h/4h] default 1h, "Evaluate Against" section hidden, "Foundational Config" section hidden, `evaluate_rulesets: []` always, no contract month, `canSubmit` requires no firm selection. NT8 modal: symbol dropdown only includes instruments from `market !== 'forex'` rulesets; "Evaluate Against" also filters to futures rulesets only; brand selection uses tabs (not radio buttons). |
| MT5 backtest detail | ✅ Live | `BacktestDetail` is MT5-aware via `runner` field on API response (`BacktestDetail` model + `_row_to_detail`): `MT5_RUN_STEPS` (Launch→Testing→Results→Tagging) vs `NT8_RUN_STEPS` (Connect→Configure→Run→Results→Tagging); runner-aware failure messages; "Load chart data from NT8", "Refresh", and "Stress Test" buttons hidden for MT5; empty-state copy updated; `_normalize_mt5_status` returns `pct=30` + "MT5 Strategy Tester running…" while running. **KPI completeness (2026-06-06):** `_normalize_mt5_results` computes `avg_win`/`avg_loss` from trades list. Direction/profit injected into equity curve points so `DirectionBreakdown` works. **Date parsing (2026-06-06):** MT5 equity dates are full ISO datetimes (`2025-12-11T18:51:00`) — `calTickLabel`, `calIndexTicks`, `fmtChartDate`, and `computeRegimeBands` all slice to 10 chars before parsing to avoid NaN axis labels, invalid tooltip dates, and missed regime lookups. Calmar also slices. Daily P&L hover cursor `rgba(255,255,255,0.04)`. |
| Strategy detail UX | ✅ Live | `StrategyDetail` header: `class_name` removed from subtitle; category shown as a coloured pill badge (cyan=mean_reversion, amber=breakout, green=momentum); platform shown as 28px icon only (`/nt8-icon.png` or `/mt5-icon.png`, no text label). Editable one-line description below the badges — click to open inline input, Enter/✓ to save, Esc/✗ to cancel. Backend: `description TEXT` column added to `strategies` table via migration; `PATCH /strategies/{id}` endpoint; `useUpdateStrategyDescription` hook. Runs table: strategy name is **plain text** (no link — was causing accidental navigation when clicking rows). Navigate to the strategy from the `<h1>` title on `BacktestDetail` instead. |
| BacktestDetail polish (2026-06-06) | ✅ Live | **Rerun button** on detail header (shown when not running): `POST /backtests/runs/{id}/retry`, navigates to new run if a new `run_id` is returned. Backend status gate changed from `startsWith("failed")` → `!= "running"` so complete runs can also be rerun. **Stale progress fix**: `useLabProgress` result is only trusted when `progress.job_id === run.run_id`; otherwise all progress values default to 0 to avoid the bar showing 100% from a prior run. **Progress bar**: single milestone-dot track; connectors between dots are the progress bar (filled by `segFill = clamp((pct - step.startPct) / (nextStep.startPct - step.startPct), 0, 1)`). **Equity curve gradient**: `endEq >= startEq` (not `>= 0`) determines green vs red for both regime-on and regime-off branches. Gradient fill preserved when regime overlay is on (base `Area` keeps `url(#eqPos/eqNeg)` fill, not `transparent`). **`StatusPill`** moved to `components/StatusPill.tsx` — shared across Backtests.tsx and BacktestDetail.tsx; pulsing cyan dot replaces 🏃 emoji. |

---

## Sidebar health indicators

Four dots in the left sidebar, sourced from `GET /system/health` (30 s TTL cache).

| Indicator | What it checks | Green | Yellow | Red |
|---|---|---|---|---|
| **API** | Local FastAPI on `:8000` | Backend healthy | — | Unreachable — restart backend |
| **SSH** | SSH tunnel to ForexVPS | Connected | — | Unreachable — check ForexVPS or `~/.ssh/config` |
| **NT8** | Agent HTTP + NT8 running + Strategy Analyzer open | All three up | Agent up, NT8 not running or SA closed | Agent down — click to start (`LucidFlexAgent` schtask) |
| **MT5 Agent** | `mt5_agent.py` HTTP on `:8766` | Responding | — | Down — click to start (`MT5AgentRDP` schtask) |

NT8 and NinjaTrader were merged into one dot. Red = agent down (clickable); yellow = agent up but NT8 not running or Strategy Analyzer not open (needs RDP intervention).

**Stuck progress lock** — if a run dies mid-flight (backend restart, network drop), `data/lab_progress.json` can be left with `status: running`, blocking new runs with a 409. Fix: hit the Stop button, or restart the backend (startup hook resets stale locks automatically).

---

## Never do

- Touch `algos/` or `smart-money/` source code — read their output files only
- Commit secrets (`.env`, credentials, tokens)
- Add a frontend route without a corresponding `NavItem` in `Sidebar.tsx`
- Change Telegram token/chat constants in `routers/bots.py` independently of `algos/shared/notify.py` — they must stay in sync
- SSH synchronously from a request handler that could take > 2s — background it
