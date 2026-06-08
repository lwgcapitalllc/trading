# CLAUDE.md — Command Center Backend

Auto-loaded by Claude Code when editing any file inside `backend/`.

**Last reviewed:** 2026-06-07 (Speed Steps 4–6)

FastAPI backend served on `:8000`. Talks to the VPS via SSH and HTTP, runs smart-money pipeline via subprocess, and owns all SQLite state. The frontend never touches the filesystem or the VPS directly.

The lab module (strategies, firms, backtests, evaluations) is live as of M1.

**Lab design principle:** The user always picks which firm challenges to evaluate against. Never default `evaluate_firms` to all firms.

---

## Directory layout

```
backend/
├── main.py                app entry; registers all routers
├── config.py              loads config.json → typed module constants
├── config.json            machine-specific paths only — no business logic here
├── models.py              ALL Pydantic models — one file, never split
├── routers/               thin — validation + status codes only, no business logic
│   ├── smart_money.py
│   ├── bots.py
│   ├── backtests.py       lab — backtest runs
│   ├── strategies.py      lab — strategy registry + deploy endpoint + GET /:id/instrument_summary
│   ├── rulesets.py        lab — ruleset CRUD (/rulesets)
│   ├── firms.py           backward-compat redirect /firms → /rulesets (deprecated, keep until all callers confirmed updated)
│   ├── system.py          lab — health + log proxies
│   ├── strategy_files.py  lab — strategy file deployment (list, upload, delete, compile, sync-status)
│   ├── stress_tests.py    lab — stress test CRUD + trigger (GET /stress-tests, GET /running-lock, GET /strategy-grades, GET /:id, POST /run, DELETE /:id)
│   ├── sweeps.py          lab — instrument sweep (POST /backtests/sweep, GET /backtests/sweeps, GET/DELETE /backtests/sweeps/:id)
│   ├── optimizations.py   lab — optimizer (POST /optimizations/run, GET /optimizations/*, DELETE /optimizations/:id)
│   ├── queue.py           job queue (GET /queue, POST /queue/optimization, POST /queue/stress-test, DELETE /queue/:id)
│   └── settings.py
├── services/              business logic, DB access, external clients
│   ├── lab_db.py          only module that touches lab.db
│   ├── strategy_scanner.py  reads from strategies/ (not algos/); emits warnings for stale source_paths
│   ├── evaluator.py       per-firm pass/fail logic
│   ├── backtest_runner.py background VPS polling task (single run)
│   ├── sweep_runner.py    runs N backtests sequentially (semaphore = 1) for a sweep
│   ├── optimization_runner.py  multi-call brute-force optimizer (see note below)
│   ├── worthiness.py      Tier 1/2/3 scoring
│   ├── objectives.py      optimizer objective functions
│   ├── stress_tester.py   Monte Carlo + walk-forward + sensitivity + auto-trigger
│   ├── grading.py         compute_grade() → A/B/C/D/F with plain-English reasons
│   ├── ohlc_fetcher.py    fetch and cache daily OHLC per (instrument, date); NT8 first, yfinance fallback
│   ├── nt8_agent_client.py      typed HTTP wrapper over NT8 nt8_agent; runner dispatcher (routes mt5 → mt5_agent_client)
│   ├── mt5_agent_client.py  typed HTTP wrapper over MT5 agent (port 8766 via SSH tunnel)
│   ├── notify.py            Telegram notifier (urllib, no extra deps); mirrors algos/shared/notify.py token/chat
│   └── queue_runner.py      asyncio queue loop — dispatches optimization + stress_test jobs one at a time
├── data/lab.db            strategies, rulesets, runs, evaluations, optimizations, stress_tests
└── reports/lab/           run output files — equity curves, logs, progress.json
```

---

## Router conventions

```python
from fastapi import APIRouter, HTTPException
import config as cfg
from models import ThingA, ThingCreate
from services import some_service

router = APIRouter(prefix="/things", tags=["things"])

@router.get("", response_model=list[ThingA])
def list_things(): ...

@router.post("", response_model=ThingA, status_code=201)
def create_thing(body: ThingCreate): ...
```

- Prefix = single noun, plural (`/strategies`, `/bots`, `/firms`)
- Routers validate input and set status codes — nothing else
- Business logic, DB queries, subprocess calls → `services/`
- Trigger endpoints → 202 with `{run_id, status: "started"}`
- Errors → `HTTPException(status_code=..., detail=...)`, never bare `raise`
- Always set `response_model` on read endpoints

---

## Pydantic models

All in `models.py`. One file. Never split it.

- `snake_case` fields
- `Optional[X] = None` for nullable fields
- `field_validator` for constraints
- New models go at the bottom of their section

---

## SQLite conventions

- Raw `sqlite3` only — no SQLAlchemy, no ORM
- Each domain owns one DB file. Lab cannot read smart-money tables — expose cross-domain data through the other domain's API
- Schemas in `init_db()` — run on startup, idempotent (`CREATE TABLE IF NOT EXISTS`)
- All queries parameterized — never `f"WHERE id = '{id}'"`
- `conn.row_factory = sqlite3.Row` for dict-like access

**Heavy data goes on disk, not in SQLite.** Equity curves, trade lists, daily P&L arrays → JSON files under `reports/lab/<run_id>/`. DB row stores the path.

---

## VPS interaction

| Channel | Use for | How |
|---|---|---|
| SSH (subprocess) | File transfer, Task Scheduler, taskkill | `subprocess.run(["ssh", cfg.SSH_ALIAS, ...])` |
| HTTP (nt8_agent) | NT8 control, pywinauto, live job control | `services/nt8_agent_client.py` — always use the typed wrapper |

Never make a synchronous SSH call from a request handler that could take > 2s. Background it.

---

## NT8 Strategy Analyzer UI automation (nt8_backtest_runner.py)

Hard-won rules for pywinauto + NT8 WPF — violating these causes silent wrong-strategy runs or broken SA state:

**SA auto-open**: `find_strategy_analyzer` opens SA automatically via NT8's New → Strategy Analyzer menu if not already visible. This handles the case where NT8 crashes and restarts without restoring the SA window. Retries once after opening.

**Strategy compile delays**: After NT8 restart, strategies are compiled lazily. `select_strategy` retries with increasing waits (1.5s → 5s → 10s) to allow NT8 time to compile before giving up.

**ComboBox identification**
- All NT8 WPF ComboBoxes return empty `window_text()` — you cannot identify them by their current value.
- Named ComboBoxes (`auto_id != ''`) are all strategy/config controls (BacktestType, TradingHours, EntryHandling, etc.). **Never click them during trade export** — it corrupts SA configuration for the next run.
- The Display combo (Summary/Analysis/Chart/Trades/…) always has an empty `auto_id`. Only scan unnamed ComboBoxes.
- To identify the Display combo: click it, then look for a "Trades" item in the SA subtree or Desktop. Try `control_type="MenuItem"` first, then `"ListItem"`, then a broad `descendants()` scan by `window_text()`.
- To close a dropdown without selecting: click the same combo again (toggle). **Do not use `send_keys("{ESCAPE}")`** — it sends ESCAPE to the active window and can dismiss unrelated dialogs.

**Strategy selection**
- `select_strategy()` returns `True/False`. If it returns `False`, the SA still has the previous strategy loaded.
- `configure_from_spec()` raises `RuntimeError` on strategy-selection failure; `run_job_mode()` catches it and calls `sys.exit(1)`. **Never let a run proceed if strategy selection failed** — NT8 will silently run whatever was last loaded.
- Strategy dropdown items are `control_type="MenuItem"`, not `ListItem`.
- **WPF popup location changes after first run**: On a fresh SA the dropdown popup is a child of the SA window in the UIA tree. After a backtest completes, subsequent clicks on the selector render the popup as a top-level Desktop element. `select_strategy` uses `_find_strategy_item` which tries both: `sa.child_window(...)` first, then `Desktop(backend="uia").window(...)`. Never search only within SA.

**Timing**
- After `select_strategy`, sleep 2–3 s — NT8 fully rebuilds the property grid and the UIA tree is temporarily invalid.
- After clicking a WPF ComboBox to open it, sleep ≥ 0.7 s before searching for items — the popup renders asynchronously.

---

## Background job pattern

Smart-money `/run` is the canonical pattern:

1. Check progress file — return 409 if already running
2. `subprocess.Popen` the worker, redirect stdout/stderr to log file
3. Write PID to `reports/<domain>/.pid`
4. Return 202 immediately
5. Worker writes `progress.json` atomically (write `.tmp` → `os.replace`)
6. `/progress` endpoint reads the file; frontend polls
7. `/stop` reads PID, sends SIGTERM, resets progress

Lab backtests use the same pattern but the "worker" is the NT8 agent over HTTP.

---

## Config

`config.json` holds machine-specific paths and the SSH alias. Nothing else. No thresholds, no business rules, no feature flags. If you're adding a non-path field to `config.json`, it belongs somewhere else.

---

## What NOT to do

- Hardcode paths — everything machine-specific comes from `config.json`
- Cross-domain DB access — lab cannot SELECT from smart-money tables
- Business logic in routers — validate and delegate only
- Synchronous SSH in request handlers — background it
- Introduce an ORM, task queue, or new framework without raising it first
- Write `progress.json` non-atomically — always write `.tmp` then `os.replace`
- Commit credentials (Telegram tokens, API keys, `.env`)
- Add a prop firm without filling in `docs_url` — rules drift, the link is how you verify

---

## When you add a new module

1. Create `routers/<thing>.py`
2. Create `services/<thing>.py` (or `<thing>_db.py` for DB-heavy modules)
3. Add Pydantic models to `models.py`
4. Register the router in `main.py`
5. If it has its own DB, create it under `data/` and call `init_db()` on startup
6. Update directory layout above

---

## Ruleset abstraction (M3)

The `firms` table was renamed to `rulesets` in M3. All references updated. `/firms/*` routes redirect to `/rulesets/*` via `routers/firms.py` (deprecated backward-compat shim; keep until all callers are confirmed updated).

**`ruleset_type` values and evaluation logic:**

| ruleset_type | Who uses it | Evaluator behavior |
|---|---|---|
| `prop_eval` | Prop firm eval challenges | drawdown + profit target + consistency |
| `prop_funded` | Prop firm funded accounts | drawdown only; PASS if under limit |
| `personal` | Personal trading accounts | daily_loss_cap + weekly_loss_cap; WARN if weekly breached |
| `demo` | Paper/demo accounts | always PASS/WARN based on net P&L; never DISCARD |

`account_tier` is still present on rows (eval/funded/live) — useful for prop rulesets. `ruleset_type` is the broader category.

New columns on `rulesets` (M3): `ruleset_type`, `daily_loss_cap`, `weekly_loss_cap`, `daily_profit_goal`, `description`.

Seeded rulesets (13 rows): 4 LucidFlex × (eval/funded) + 4 Tradeify × (eval/funded) + 4 FundedNext × (eval/funded) + 1 personal example (`personal_futures_10k_example`).

**Evaluations table:** `firm_id` column renamed to `ruleset_id`. `optimizations` table: `firm_id` → `ruleset_id` too.

`BacktestRunRequest.evaluate_rulesets` — replaces `evaluate_firms` (backward-compat alias still accepted).

---

## Pass 1 — Foundational Config

Rulesets carry 10 foundational fields (risk %, halt fraction, consecutive loss limit, entry hours ET, days allowed, daily profit target, profit lock-in %, commission/side, slippage ticks). Injected into strategy params at run creation by `nt8_agent_client.inject_foundational()`.

**Category tagging:** every `[NinjaScriptProperty]` in a strategy file carries `[Category("Strategy Logic")]` (tunable, optimizer-visible) or `[Category("Foundational")]` (injected from ruleset, hidden in UI). Legacy files with `[Display(GroupName = "Prop Firm")]` fall back to `"foundational"` via GroupName heuristic.

**Dispatcher injection:** happens at three creation points — `trigger_backtest()`, `trigger_sweep()`, and `run_optimization()` — using the primary ruleset (first in `evaluate_rulesets`). Merged params stored in DB at creation so all retry paths pick them up without re-injection.

**Primary ruleset rule:** only the first ruleset in the list injects foundational config. Others evaluate only. To test two rulesets' configs simultaneously, run two separate backtests.

**Sentinel guard:** strategies refuse to trade (print warning + return) if foundational params are still at placeholder values (-1 or empty string). This catches dispatcher failures early.

---

## What's built (status)

| Domain | Status | What it does |
|---|---|---|
| Smart Money | ✅ Live | Scan, terminal, rankings, profile, disqualified log, config, cache tabs. |
| Bots | ✅ Live | SSH monitor for gold_main/gold_scalper/gold_fft. Global + per-bot risk controls, cap deploy, Telegram users tab. |
| Lab — Strategies | ✅ Live | Registry scanned from `strategies/`. Param schema from `[NinjaScriptProperty]`. `runner` field per strategy. |
| Lab — Rulesets | ✅ Live | CRUD at `/rulesets`. 4 types: `prop_eval`, `prop_funded`, `personal`, `demo`. 13 seeded rows. |
| Lab — Backtests | ✅ Live | NT8/MT5 runs via agent. Equity curve, daily P&L, per-ruleset verdicts, Worthiness tier (1/2/3). |
| Lab — Sweeps | ✅ Live | N sequential backtests across instruments (`_MAX_CONCURRENT = 1`). Cancel, retry-all, per-run retry. |
| Lab — Optimizations | ✅ Live | Brute-force + genetic optimizer. Scores by objective. `best_run_id` tracked. Source run nesting. Per-run retry. |
| Lab — System | ✅ Live | Health (SSH, NT8, MT5 agents). Log proxies. `POST /system/{nt8,mt5}-agent/start` fires schtasks. |
| Lab — Stress Tests | ✅ Live | MC (10k reshuffles + 1k bootstrap), walk-forward (IS/OOS NT8 windows), sensitivity (±10%/±25%). A–F grade. |
| Lab — Regime Tags (M4) | ✅ Live | `daily_pnl` entries tagged with regime label. Auto-tagged at pipeline time. Optimizer `regime_filter`. |
| Lab — Strategy Files (Pass 2) | ✅ Live | Upload/delete/compile `.cs` (NT8 F5) and `.mq5` (MetaEditor) files. Sync-status badges. |
| Lab — Strategy Deploy (Pass 2.5) | ✅ Live | `POST /strategies/{id}/deploy` reads `source_path`, uploads to VPS. `.mq5` → MT5 agent, `.cs` → NT8 agent. |
| Lab — MT5 runner (M5) | ✅ Live | `mt5_agent.py` port 8766: Strategy Tester driver (ini+set, terminal64, HTML report). `mt5_agent_client.py` typed wrapper. Runner dispatch via `nt8_agent_client`. |
| Lab — MT5 deployment (Step 9) | ✅ Live | MT5 agent upload/delete `.mq5`. `POST /compile` → MetaEditor. Backend: `POST/GET /strategy-files/compile-mt5`. |
| Lab — MT5 native optimizer (Speed Step 4) | ✅ Live | `mt5_agent.py` extended with `POST /native-optimize` (Optimization=1 ini, set-file ranges, HTML combo parser) and `POST /native-walkforward` (ForwardMode ini, IS/OOS HTML split). `mt5_agent_client.py` typed wrappers. `nt8_agent_client` dispatcher: `start_native_optimization`, `native_opt_results`, `start_native_walkforward`, `native_wf_results` all accept `runner` param. `optimization_runner.run_native_optimization` reads `runner_str` from strategy and passes through poll loop. **HTML parsing needs VPS validation.** |
| Lab — Telegram notifications (Speed Step 5) | ✅ Live | `services/notify.py` — urllib Telegram sender (same token as `algos/shared/notify.py`, no extra deps). `stress_tester` fires after grade is written in both MC-only and full WF+sens paths. |
| Lab — Job queue (Speed Step 6) | ✅ Live | `job_queue` table + CRUD in `lab_db.py`. `queue_runner.py` asyncio loop runs one job at a time (optimization or stress_test). `routers/queue.py`: GET/POST/DELETE. Loop started as asyncio task in `main.py` startup. |
| Settings | ✅ Live | Config read/write. `nt8_agent_tunnel` and `mt5_agent_tunnel` both present. |
| Startup — auto-start agents | ✅ Live | Daemon thread on startup (8s delay): `/health` each agent, fires schtask for any that don't respond. |

---

## Worthiness scoring

`services/worthiness.py`. Scored against the strictest evaluated firm (smallest `max_loss_eod`).

| Tier | Criteria |
|---|---|
| **Tier 1 — STRESS_TEST** | PF > 1.3 AND DD ≤ firm limit AND DD not in danger zone AND trade_count ≥ 50 |
| **Tier 2 — OPTIMIZE** | PF in [0.8, 1.3] OR DD in danger zone (0.7×–1.0× of limit), trade_count ≥ 30 |
| **Tier 3 — DISCARD** | PF < 0.8 OR DD > firm limit OR trade_count < 30 |

Columns on `backtest_runs`: `worthiness_tier`, `worthiness_reason`, `worthiness_computed_against_firm` (firm_id of the strictest firm used). Added via migration — not in the original CREATE TABLE.

---

## Objective functions

`services/objectives.py`. Two registered objectives; chosen by `mode`:

- **`eval_pass_probability`** (default) — score 0.0–1.5. 1.0 = DD ok + target hit; speed bonus up to +0.5 for hitting target in fewer than 30 simulated days. Partial credit (0–0.5) if DD passes but target not reached. 0.0 if DD breached.
- **`funded_sharpe_under_drawdown`** — Sharpe ratio if DD within limit, −∞ if breached. Used when `mode = "funded"`.

---

## DB schema — notable columns added via migration

`backtest_runs` additions (not in original CREATE TABLE):
- `worthiness_tier`, `worthiness_reason`, `worthiness_computed_against_firm` — see Worthiness scoring above
- `sweep_id` — set on all child runs of an instrument sweep
- `optimization_id` — set on all child runs of an optimizer job
- `source_run_id` — set when a sweep or optimization is triggered from a BacktestDetail page; links children back to the originating run
- `stress_test_id` — set on walk-forward and sensitivity child runs; links them back to the parent stress test
- `walk_forward_window_id` — identifies the window and period (e.g. `wf_2_oos`, `sens_EntryOffset_+10%`)

`optimizations` table key fields: `optimization_id`, `strategy_id`, `instrument`, `start_date`, `end_date`, `commission_per_side`, `slippage_ticks`, `ruleset_id`, `mode`, `search_method`, `param_grid` (JSON), `status`, `estimated_runs`, `completed_runs`, `best_run_id`, `source_run_id`, `regime_filter` (M4 — one of the 5 regime labels or NULL), `created_at`, `completed_at`.

`instrument_daily_ohlc` table (M4): caches OHLC by (instrument, date). Source can be `"yfinance"` or `"nt8"`. Cache freshness: dates > 5 days old are fetched once and never refetched. Recent dates always refetched.

`stress_tests` additions (added via migration, not in original CREATE TABLE):
- `mc_completed_at` — unix timestamp when Monte Carlo phase finished; used by frontend pipeline stepper to show per-phase elapsed time
- `wf_completed_at` — unix timestamp when walk-forward phase finished; same purpose

---

## How stress tests work

**Monte Carlo** — pure Python (numpy), no NT8 involved. Takes the trade P&L list from a completed backtest and runs two simulations:
- 10,000 reshuffles: same trades, random order. Probes whether the sequence of wins/losses was lucky. Sum is invariant, so final PnL doesn't vary across reshuffles — only drawdown does.
- 1,000 bootstrap resamples: samples trades with replacement. Both total PnL and drawdown vary.
Merges both pools (~11,000 paths) and computes: median/P95/P99 drawdown, prob of breaching the firm's loss limit, prob of passing the eval. Runs in ~5s even for 700+ trades.

**Walk-forward** — sends real backtests to NT8. Splits the original date range into N equal windows. Each window is split 70% in-sample / 30% out-of-sample — two separate NT8 backtests per window. Measures how much Sharpe drops from in-sample to out-of-sample. Large drop = strategy may be overfit to the training period.

**Sensitivity** — re-runs the strategy with each numeric parameter shifted, one VPS backtest per shift. Booleans are skipped. Measures PnL delta vs the baseline run. Large swings = strategy is fragile to exact parameter values. **MT5 uses 2 shifts (±10%)** to limit queue depth; NT8 uses 4 shifts (±10% and ±25%). `SHIFTS` in `stress_tester.run_sensitivity_task()` is runner-aware. Duration estimate: `_estimate_sens_duration_min(n_params, runner)`.

**Auto-trigger** — fires MC only (no NT8) automatically when a Tier 1 backtest completes or an optimizer picks a winner. Manual trigger always runs all three phases (MC + walk-forward + sensitivity); no user checkbox.

**Child run isolation** — walk-forward and sensitivity runs are inserted into `backtest_runs` with `stress_test_id` set. `lab_db.list_runs()` always adds `r.stress_test_id IS NULL` to its WHERE clause so they never appear in the Runs tab. They're accessible only from `StressTestDetail`.

**Market lock** — `lab_db.running_stress_test_markets()` queries `stress_tests WHERE status LIKE 'running%'` (covers `running`, `running_wf`, `running_sens`), joins to derive `runner`, returns `{futures, forex, run_ids}`. `POST /stress-tests/run` checks this before inserting; 409 if same market is already running. `GET /stress-tests/running-lock` exposes it for the frontend poll.

**Crash recovery** — `lab_db.reset_stale_stress_tests()` marks any `running%` stress tests as `failed_crashed` and their child runs as `failed_timeout`. Called in `main.py` `startup()` — backend restarts automatically clear stuck tests and release the market lock.

---

## Key architectural decisions

**Optimizer implementation:** Two paths, selected by `search_method` on the optimization row:

- **`"brute"` / `"genetic"` / `"auto"`** (legacy) — generates all param combos on the backend and fires them as individual backtest calls via `nt8_agent_client.start_backtest`. `_MAX_CONCURRENT = 1` — the SA window is single-threaded. "genetic" samples up to 200 combos for 3+D grids.

- **`"native"`** (Step 1 fast path, NT8 only) — sends ONE `POST /native-optimize` to the VPS agent. `nt8_backtest_runner.run_native_optimize_mode` switches the SA to Optimization mode, sets Start/End/Increment ranges for each Strategy Logic param, fires a single Run that uses all CPU cores, then exports the results grid to CSV. The backend creates run rows for every combo after the grid is returned. No per-combo equity curve — auto-trigger stress test is skipped; winner must be stress-tested via a manual single rerun. `estimated_runs` is always the full grid size (no sampling in native mode).

**Parity check:** before trusting the native path, run one combo through it and compare to the existing single-run path. Optimize mode under pywinauto differs from Run mode — the parity check catches setup bugs.

**NT8 SA global lock:** All three job types (single backtest, sweep, optimization) share the same physical SA window. `lab_db.has_any_running_vps_job()` checks for any `backtest_runs` or `optimizations` row with `status = 'running'`. All three trigger endpoints call it and return 409 if true. This prevents cross-job conflicts (e.g. a sweep starting while an optimization is in progress). Walk-forward and sensitivity stress tests also check this lock before triggering.

**Stress test architecture:** `services/stress_tester.py` runs three phases: (1) Monte Carlo — pure numpy, vectorised, ~5s even for 700+ trades. (2) Walk-forward — N windows × 2 VPS backtests (IS + OOS), sequential. (3) Sensitivity — N params × SHIFTS VPS backtests, sequential; SHIFTS = 2 for MT5, 4 for NT8. Auto-trigger (Tier 1 backtests + optimizer winners) runs MC only — no VPS needed. Manual trigger always runs all three phases.

**Strategy best grades:** `lab_db.best_grades_by_strategy()` queries all graded stress tests, returns `{strategy_id: {grade, stress_test_id}}` keeping the best grade per strategy (A–F ordered). `GET /stress-tests/strategy-grades` exposes this. Route must be defined before `GET /{stress_test_id}` to avoid FastAPI matching "strategy-grades" as a stress test ID.

**Robustness grading:** `services/grading.py`. Grade A-F based on Monte Carlo tail risk + optional walk-forward IS→OOS degradation + parameter sensitivity.

| Grade | MC condition | Walk-forward (if run) | Sensitivity (if run) |
|---|---|---|---|
| A | worst-1% DD ≤ limit | degradation < 20% | max drop < 25% |
| B | worst-5% DD ≤ limit | degradation < 30% | max drop < 40% |
| C | median DD ≤ limit | — | — |
| D | median profitable but DD fails | — | — |
| F | median loses money | — | — |

When walk-forward/sensitivity weren't run, those conditions are skipped (grade is based on MC alone — still valid but grade_reasons notes the gap).

**Deployment gates (UI only, soft):** A = funded; B = eval purchase; C = demo. Shown as warnings, never blocking.

**Regime classifier (M4):** Import from `trading/regime/` — the canonical implementation lives there, never duplicate it here. The canonical algorithm doc is at `trading/regime/REGIME_CLASSIFIER.md`. Import pattern:
```python
import sys
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from regime import classify_regime  # returns one of 5 labels + UNKNOWN
```
Lab uses daily OHLC, so pass the same DataFrame for both `df_short` and `df_long` (`classify_regime(df_daily, df_daily)`). Warmup: fetch 50 extra days before `start_date` so day 1 gets a real label. Window: 34 bars. The OHLC cache is in `instrument_daily_ohlc` — use `services/ohlc_fetcher.get_ohlc()`, never fetch directly in service code.

**Regime filter in optimizer (M4):** When `regime_filter` is set on an optimization, `_pick_best_run` builds a `date → regime` map once from OHLC, then scores each child run using only trades from matching-regime days. NT8 still runs the full backtest period — filtering happens at scoring time only. All three scoring paths (initial run, retry-one, retry-all) go through `_pick_best_run`.

**Sweep serialisation:** `sweep_runner.py` uses `asyncio.Semaphore(1)` — same constraint as the optimizer. Instruments run one at a time through the SA window.

**Runner dispatcher:** `nt8_agent_client.start_backtest(job_spec, runner)` routes to the appropriate backend. Both `"ninjatrader"` (NT8 Strategy Analyzer) and `"mt5"` (MT5 Strategy Tester via `mt5_agent_client`) are wired. `nt8_agent_client._nt8_to_mt5_spec()` translates the NT8-style job_spec to the MT5 agent's format — critically, it passes `job_id` through so the MT5 agent stores the job under our `run_id`; without this every status poll returns 404 and the run times out. Timeframe mapping in `_nt8_to_mt5_spec`: M1/M5/M15/M30/H1/H4/D1 (Minute bar_value thresholds: ≥240→H4, ≥60→H1, ≥30→M30, ≥15→M15, ≥5→M5, else M1). `_normalize_mt5_status/results()` translates the MT5 agent's response shape back to the NT8 shape so all callers remain runner-agnostic. `_normalize_mt5_status` returns `pct=30` + "MT5 Strategy Tester running…" while running (no granular progress from the blocking Strategy Tester process). `runner` field added to `BacktestDetail` model and `_row_to_detail`. File upload/delete also dispatch by extension: `.mq5` files go to `mt5_agent_client`, `.cs` files go to the NT8 nt8_agent.

**Sweep vs. progress lock:** Sweep and optimization runs do NOT use `lab_progress.json`. That file is exclusively for the single-run flow. Sweep/optimization state is tracked only in the DB.

**source_run_id:** `optimizations` stores the `run_id` of the backtest that spawned it. Sweep child runs store the `run_id` of the run that triggered the sweep. The Runs tab uses this to nest linked jobs under their source run. Rows without `source_run_id` (created before this was added) appear flat — no backfill is possible.

---

## Pass 2 — Strategy Deployment Manager

NT8 agent endpoints: `GET/POST/DELETE /files/strategies/<filename>`, `POST/GET /compile`. NT8 strategy folder: `C:\Users\Administrator\Documents\NinjaTrader 8\bin\Custom\Strategies\`.

**Compile:** `nt8_compile_runner.py` uses pywinauto F5 via NinjaScript Editor (`NCompile.exe` does not exist on this install). Success detected by polling `NinjaTrader.Custom.dll` mtime — NT8 rewrites it on every successful compile (90s timeout).

**Upload limit:** 256 KB enforced on both agent and backend router.

**Lock detection:** NT8 agent tries `r+b` open before upload/delete. `IOError` → HTTP 423.

**Sync-status:** `GET /strategy-files/sync-status` — in sync when expected `.cs` file exists on VPS. File presence = in sync (no hash comparison yet).

---

## Pass 2.5 — Strategy Location Cleanup

Scanner reads from `strategies/` via `rglob("*.cs")` and `rglob("*.mq5")`. `source_path` stored relative to monorepo root (e.g. `strategies/ninjatrader/ORB.cs`). Missing `source_path` emits a warning, never auto-deletes.

`POST /strategies/{id}/deploy` reads `source_path`, uploads via `nt8_agent_client` (dispatches `.mq5` → MT5 agent, `.cs` → NT8 agent). Returns 202 + `deploy_job_id`. Edge cases: `source_path` null → 400, file missing → 404, VPS locked → 423.
