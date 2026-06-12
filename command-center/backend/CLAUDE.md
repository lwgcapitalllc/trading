# CLAUDE.md — Command Center Backend

**Purpose:** FastAPI backend (`:8000`) — owns all SQLite state, talks to the VPS via SSH + HTTP agents, runs the smart-money pipeline via subprocess, and drives NT8/MT5 backtests.
**Scope:** This covers backend conventions, routers, services, DB, and VPS interaction. It does NOT cover the frontend (see `../frontend/CLAUDE.md`) or `algos/`/`smart-money/` source.
**Status:** Live — lab (strategies, rulesets, backtests, sweeps, optimizations, stress tests, queue, MT5 runner) all shipped.
**Last reviewed:** 2026-06-12

Auto-loaded by Claude Code when editing any file inside `backend/`.

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
│   ├── strategies.py      lab — strategy registry + deploy endpoint + GET /:id/instrument_summary + GET /:id/param-types
│   ├── rulesets.py        lab — ruleset CRUD (/rulesets); PATCH = guarded personal-rules edit (prop rows locked 403; PUT also 403 on prop)
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
│   ├── evaluator.py       per-ruleset verdict; also exports compute_contract_cap_status()
│   ├── trailing_drawdown.py  compute_trailing_mll() — EOD trailing max-loss engine (the drawdown check)
│   ├── metrics.py         shared metric helpers: daily_sharpe / apply_canonical_sharpe / profit_concentration_pct
│   ├── backtest_runner.py background VPS polling task (single run)
│   ├── sweep_runner.py    runs N backtests sequentially (semaphore = 1) for a sweep
│   ├── optimization_runner.py  native NT8/MT5 optimizer (one VPS job, all CPU cores)
│   ├── worthiness.py      Tier 1/2/3 scoring
│   ├── objectives.py      optimizer objective functions
│   ├── stress_tester.py   Monte Carlo + walk-forward + sensitivity + auto-trigger
│   ├── grading.py         compute_grade() → A/B/C/D/F with plain-English reasons
│   ├── scripts/backfill_metrics.py  one-time, idempotent backfill of file-derivable metrics on old runs
│   ├── ohlc_fetcher.py    fetch and cache daily OHLC per (instrument, date); NT8 first, yfinance fallback
│   ├── runner_dispatch.py      typed HTTP wrapper over NT8 nt8_agent; runner dispatcher (routes mt5 → mt5_agent_client)
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
| HTTP (nt8_agent) | NT8 control, pywinauto, live job control | `services/runner_dispatch.py` — always use the typed wrapper |

Never make a synchronous SSH call from a request handler that could take > 2s. Background it.

---

## NT8 Strategy Analyzer UI automation (nt8_backtest_runner.py)

Hard-won rules for pywinauto + NT8 WPF — violating these causes silent wrong-strategy runs or broken SA state:

**PCT:100 hung fix**: In `nt8_agent.py`, the `for line in proc.stdout:` loop never sees EOF on Windows when the subprocess calls `os._exit(0)`. This is because `subprocess.Popen` with `stdout=PIPE` sets `close_fds=False` on Windows — the agent process inherits the write-end of the pipe, keeping it open after the child exits. Fix: mark the job `status="complete"` *inside* the stdout loop the moment `PCT:100` arrives AND the results file exists — never wait for loop exit. Same pattern applies to walk-forward jobs.

**SA auto-open**: `find_strategy_analyzer` opens SA automatically via NT8's New → Strategy Analyzer menu if not already visible. This handles the case where NT8 crashes and restarts without restoring the SA window. Retries once after opening.

**Narrow scan `txtBox` probe**: `_build_opt_grid_map` uses a narrow scan to avoid the ~22s full `sa.descendants()` call. The probe must use `found_index=0` — `sa.child_window(auto_id="txtBox", control_type="Edit", found_index=0)` — because multiple elements match and `child_window()` without `found_index` throws "N elements match." Each `node.parent()` call in the walk must be in its own `try/except` so a COM error on one level doesn't abort the entire walk.

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

**Optimization results export**
- Right-click CSV export from the SA results grid is the **only** way to get optimization results. Native optimize writes `.cs` files per combo — no `.xml`. Never look for an output file; always export via the context menu.
- `_export_optimization_results` uses a two-pass right-click: Pass 1 opens the context menu and scans the UIA tree to find Export coordinates (the scan causes WPF to close the popup), Pass 2 right-clicks again and immediately clicks Export at the recorded coordinates.
- Sleep **1.0 s** (not 0.3 s) after `sa.restore()` before right-clicking — the SA needs time to finish restoring before WM_RBUTTONDOWN lands on the right element.
- Right-click at `y = sa_rect.top + int(sa_h * 0.20)` — 20% skips the Display dropdown and column headers. y=5% lands in the header row (no Export option). y=50%+ lands in the performance summary tab (wrong export format). The print log shows `[opt-export] Right-click at (x, y)  sa=WxH` for debugging.
- **0-trade combos kill Export**: when all optimization combos produce 0 trades, NT8 shows no results in the grid and the Export context menu item does not appear. Root cause: NinjaScript `int` parameters (e.g. `MaPeriod`) silently truncate decimal values — a step of 2.5 generates values like 22.5 → cast to 22, but NT8 skips the combo because the effective value doesn't match. The `param-types` endpoint + frontend validation (see frontend CLAUDE.md) prevents users from entering non-integer steps on `int` params.
- When the same 3 persistent items (`Momentum`, `Select`, `Trades ($)`) appear in the UIA scan, the right-click is NOT opening a context menu — it landed on a different element. These are persistent WPF dropdown elements, not context menu items.

**Param setting in Optimize mode — confirmed behavior**
- NT8 does NOT automatically reset BacktestType after `select_strategy`. It stays in whatever mode was active. Always call `_set_backtest_type("Backtest")` explicitly after `select_strategy` + 3s sleep to get a clean state.
- String and bool params: set via PDEX `set_edit_typed`/`set_checkbox` in Backtest mode. These persist through Backtest→Optimize switch (no Optimize-grid entry for them).
- Numeric params: DO NOT persist through Backtest→Optimize switch. NT8 resets all Optimize-grid params to their NinjaScript defaults on the mode switch. Must be set via the Optimize grid (`_set_range_in_grid` with lo=hi=value, step=1) AFTER switching to Optimize mode.
- One-time re-render: the first write to ANY txtBox in the Optimize grid triggers NT8's WPF property-change event, rebuilding the entire grid (stale elements). Set RANGE params first — they absorb the re-render. Then rebuild `grid_map` (0.5s sleep) and set fixed numeric params. They will stick because the re-render has already fired.
- Confirmed flow in `run_native_optimize_mode`: select_strategy → 3s → `_set_backtest_type("Backtest")` → 1.5s → set str/bool via PDEX → `_set_backtest_type("Optimize")` → set instrument/dates → build grid_map → set range params → 0.5s → rebuild grid_map → set fixed numeric params (lo=hi=value, step=1).
- `set_edit_text` does not trigger NT8's WPF LostFocus commit handler. Always use `set_edit_typed` (click_input + type_keys with `~`) for strategy PDEX fields.

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

The `firms` table is now `rulesets`; `firm_id` is `ruleset_id` everywhere (evaluations, optimizations). `/firms/*` routes redirect to `/rulesets/*` via `routers/firms.py` (deprecated shim; keep until all callers confirmed updated). `BacktestRunRequest.evaluate_rulesets` replaces `evaluate_firms` (backward-compat alias still accepted). Full migration story in the M3 archive spec.

**`ruleset_type` values and evaluation logic:**

| ruleset_type | Who uses it | Evaluator behavior |
|---|---|---|
| `prop_eval` | Prop firm eval challenges | EOD trailing max-loss (DISCARD on breach) → profit target (WARN if missed; target is raised when a `raise_target` firm's consistency is breached) → consistency (WARN). PASS if all clear. |
| `prop_funded` | Prop firm funded accounts | EOD trailing max-loss only — PASS if not breached, else DISCARD. No WARN. |
| `personal` | Personal trading accounts | Real PASS/DISCARD verdict against the relaxed personal rules (`_evaluate_personal`): DISCARD on `max_consecutive_loss_days` consecutive days whose loss hit `daily_loss_cap`, or on EOD equity dropping `max_drawdown_from_peak_pct` from its running peak; otherwise PASS. `daily_profit_target` is an informational halt note, never a fail. No trailing MLL (max_loss_eod = 0 sentinel), no profit-target requirement, no consistency rule, no reference line. |
| `demo` | Paper/demo accounts | Same as `personal`. |

For prop types the verdict reads `max_loss_eod` (the trailing-MLL amount) and `mll_lock_balance` for drawdown; it never reads `daily_loss_cap` (a soft/informational field for firms like Apex). For personal/demo types `daily_loss_cap` IS a rule input (the capped-day trigger) and `max_loss_eod` is never read (0 sentinel = no trailing EOD rule). `metrics.effective_dd_limit_usd()` is the one place that turns a ruleset into a dollar MC/objective drawdown limit — personal/demo rows translate to `account_size × max_drawdown_from_peak_pct`; worthiness and the stress-test primary pick exclude personal/demo rows from their strictest-ruleset comparisons.

`account_tier` is still present on rows (eval/funded/live) — useful for prop rulesets. `ruleset_type` is the broader category.

Columns on `rulesets`: `ruleset_type`, `daily_loss_cap`, `weekly_loss_cap`, `daily_profit_goal`, `description`.

Seeded rulesets (16 rows): 4 prop firms = 14 prop rows — LucidFlex, FundedNext, Tradeify each at 50k/100k × eval/funded (12 rows), plus Apex EOD eval-only at 50k/100k (2 rows; funded/PA not yet seeded) — plus 2 personal demo rows (`personal_forex_demo`, `personal_futures_demo`; ruleset_type `personal`, account_tier `demo`). Personal demo rules on a $10k balance: $500 daily loss cap, $1,000 daily profit target, fail at 15% drawdown from peak (`max_drawdown_from_peak_pct`) or 3 consecutive capped-loss days (`max_consecutive_loss_days`) — stored now, enforced in a later evaluator pass. `max_loss_eod = 0` is the sentinel for "no trailing EOD rule" on personal rows (the column is NOT NULL); the evaluator must treat it as rule-absent. All seeded via the per-id idempotent pattern (`_PROP_SEED_ROWS` + `_seed_apex_eod_eval`).

---

## Lens metrics (the per-run scoring layer)

**Drawdown = EOD trailing max-loss** (`services/trailing_drawdown.compute_trailing_mll`), not whole-test max DD. Floor trails the highest EOD balance, capped at `mll_lock_balance` when set; a breach (balance falls through the floor) is the only thing that fails `drawdown_pass`. Detail columns on `evaluations`: `mll_final_floor`, `mll_highest_eod_balance`, `mll_breach_day`, `mll_min_floor_distance`.

**Canonical Sharpe — one definition everywhere.** `metrics.apply_canonical_sharpe(kpis, daily_pnl)` writes the daily-√252 Sharpe into `sharpe`, moves the platform's value to `platform_sharpe`, and sets `sharpe_low_sample` (<10 trading days). It's called at every run-completion path that has `daily_pnl` — single run, sweep child, stress child, optimizer winner — but NOT the native-combo path (no daily_pnl). **Idempotency guard:** only runs when `platform_sharpe` is null, so a second pass can't overwrite the platform value. Walk-forward window Sharpe (`stress_tester._compute_sharpe`) and the optimizer both go through `daily_sharpe_from_values`.

**Contract cap** (`evaluator.compute_contract_cap_status`, informational — never moves the verdict): scaling ladder → `not_applicable`; MT5 (lots) → `not_applicable`; NT8 without per-trade size → `not_evaluable`; NT8 fixed cap + size → real largest-single-trade vs cap. Per-trade `size` is captured from NT8's Quantity column / MT5 volume.

**Profit concentration** persisted as `profit_concentration_pct` (largest calendar quarter's share of gross profit) for later grading use. **Backfill:** `scripts/backfill_metrics.py` recomputes the file-derivable columns (Sharpe trio, profit concentration, contract status) on old runs — idempotent, only touches what's derivable from stored result files.

**Capital-based scores stay client-side** (BacktestDetail). Calmar / Max-DD-% need an account balance (the ruleset's `account_size` or the what-if slider); they're computed in the browser by rebasing the equity, never persisted, and never feed the verdict.

---

## Foundational config (Pass 1)

Rulesets carry 10 foundational fields (risk %, halt fraction, consecutive loss limit, entry hours ET, days allowed, daily profit target, profit lock-in %, commission/side, slippage ticks), injected into strategy params at run creation by `runner_dispatch.inject_foundational()`. Detail in the Pass1 archive spec.

**Standing rules:**
- **Category tagging:** every `[NinjaScriptProperty]` carries `[Category("Strategy Logic")]` (tunable, optimizer-visible) or `[Category("Foundational")]` (injected, hidden in UI). Legacy `[Display(GroupName = "Prop Firm")]` falls back to `"foundational"` via GroupName heuristic.
- **Dispatcher injection** happens at three creation points — `trigger_backtest()`, `trigger_sweep()`, `run_optimization()` — using the primary ruleset (first in `evaluate_rulesets`). Merged params stored in DB at creation so all retry paths pick them up without re-injection.
- **Primary ruleset rule:** only the first ruleset injects foundational config; others evaluate only. To test two rulesets' configs, run two separate backtests.
- **Sentinel guard:** strategies refuse to trade (warn + return) if foundational params are still at placeholders (-1 or empty string), catching dispatcher failures early.

---

## What's built (status)

| Domain | Status | What it does |
|---|---|---|
| Smart Money | ✅ Live | Scan, terminal, rankings, profile, disqualified log, config, cache tabs. |
| Bots | ✅ Live | SSH monitor for gold_main/gold_scalper/gold_fft. Global + per-bot risk controls, cap deploy, Telegram users tab. |
| Strategies | ✅ Live | Registry scanned from `strategies/`. Param schema from `[NinjaScriptProperty]`. `runner` field per strategy. |
| Rulesets | ✅ Live | CRUD at `/rulesets`. 4 types: `prop_eval`, `prop_funded`, `personal`, `demo`. 16 seeded rows (4 prop firms + 2 personal demo). Prop rows locked server-side (PATCH/PUT 403); `PATCH` edits the 5 personal rule fields only (`PersonalRulesetPatch` extra=forbid + SQL allowlist). |
| Backtests | ✅ Live | NT8/MT5 runs via agent. Equity curve, daily P&L, per-ruleset verdicts, Worthiness tier (1/2/3). |
| Sweeps | ✅ Live | N sequential backtests across instruments (`_MAX_CONCURRENT = 1`). Cancel, retry-all, per-run retry. |
| Optimizations | ✅ Live | Native NT8/MT5 optimizer (one VPS job, full grid, all CPU cores). Scores by objective. `best_run_id` tracked. Source run nesting. Per-run retry. |
| System | ✅ Live | Health (SSH, NT8, MT5 agents). Log proxies. `POST /system/{nt8,mt5}-agent/start` fires schtasks. |
| Stress Tests | ✅ Live | MC (10k reshuffles + 1k bootstrap), walk-forward (IS/OOS NT8 windows), sensitivity (±10%/±25%). A–F grade. |
| Regime Tags | ✅ Live | `daily_pnl` entries tagged with regime label. Auto-tagged at pipeline time. Optimizer `regime_filter`. |
| Strategy Files | ✅ Live | Upload/delete/compile `.cs` (NT8 F5) and `.mq5` (MetaEditor) files. Sync-status badges. |
| Strategy Deploy | ✅ Live | `POST /strategies/{id}/deploy` reads `source_path`, uploads to VPS. `.mq5` → MT5 agent, `.cs` → NT8 agent. |
| Param types | ✅ Live | `GET /strategies/{id}/param-types` parses `.cs`/`.mq5` source → `{paramName: "int"\|"double"}`. Used by optimizer modal to block decimal steps on integer params. |
| MT5 runner | ✅ Live | `mt5_agent.py` port 8766: Strategy Tester driver (ini+set, terminal64, HTML report). `mt5_agent_client.py` typed wrapper. Runner dispatch via `runner_dispatch`. |
| MT5 deployment | ✅ Live | MT5 agent upload/delete `.mq5`. `POST /compile` → MetaEditor. Backend: `POST/GET /strategy-files/compile-mt5`. |
| MT5 native optimizer | ✅ Live | `mt5_agent.py` `POST /native-optimize` + `POST /native-walkforward`; `mt5_agent_client.py` typed wrappers. `runner_dispatch` dispatcher + `optimization_runner.run_native_optimization` route by `runner`. Combos run sequentially with per-combo progress. |
| Telegram notifications | ✅ Live | `services/notify.py` — urllib Telegram sender (same token as `algos/shared/notify.py`, no extra deps). `stress_tester` fires after grade is written. |
| Job queue | ✅ Live | `job_queue` table + CRUD in `lab_db.py`. `queue_runner.py` asyncio loop runs one job at a time (optimization or stress_test). `routers/queue.py`: GET/POST/DELETE. Started in `main.py` startup. |
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

## DB schema — notable columns

`backtest_runs`:
- `worthiness_tier`, `worthiness_reason`, `worthiness_computed_against_firm` — see Worthiness scoring above
- `sweep_id` — child runs of an instrument sweep
- `optimization_id` — child runs of an optimizer job
- `source_run_id` — set when a sweep/optimization is triggered from a BacktestDetail page, OR when a tuning-workbench iteration is run from a baseline run; links derived runs back to the originating run. `BacktestRunRequest` and `BacktestSummary` both carry `source_run_id`; the tuning workbench filters runs by it to group iterations.
- `stress_test_id` — walk-forward and sensitivity child runs; links them back to the parent stress test
- `walk_forward_window_id` — identifies the window and period (e.g. `wf_2_oos`, `sens_EntryOffset_+10%`)

`optimizations` key fields: `optimization_id`, `strategy_id`, `instrument`, `start_date`, `end_date`, `commission_per_side`, `slippage_ticks`, `ruleset_id`, `mode`, `search_method`, `param_grid` (JSON), `status`, `estimated_runs`, `completed_runs`, `best_run_id`, `source_run_id`, `regime_filter` (one of the 5 regime labels or NULL), `created_at`, `completed_at`.

`instrument_daily_ohlc`: caches OHLC by (instrument, date). Source `"yfinance"` or `"nt8"`. Cache freshness: dates > 5 days old fetched once and never refetched; recent dates always refetched.

`stress_tests`:
- `mc_completed_at` — unix timestamp when Monte Carlo phase finished; frontend pipeline stepper shows per-phase elapsed time
- `wf_completed_at` — unix timestamp when walk-forward phase finished; same purpose

---

## How stress tests work

**Monte Carlo** — pure Python (numpy), no NT8 involved. Takes the trade P&L list from a completed backtest and runs two simulations:
- 10,000 reshuffles: same trades, random order. Probes whether the sequence of wins/losses was lucky. Sum is invariant, so final PnL doesn't vary across reshuffles — only drawdown does.
- 1,000 bootstrap resamples: samples trades with replacement. Both total PnL and drawdown vary.
- **Drawdown** stats (median/P95/P99, prob-breach) use BOTH pools (order genuinely varies drawdown). **Final-PnL** stats — the median/p5/p1 percentiles, the PnL histogram, AND the "probability of passing the eval" — use the **BOOTSTRAP pool only**: reshuffle final PnLs are all the net total (order-invariant), so including them collapses those onto one degenerate value. Don't reintroduce `all_pnls` into a final-PnL stat.

**Walk-forward** — sends real backtests to NT8. Splits the original date range into N equal windows. Each window is split 70% in-sample / 30% out-of-sample — two separate NT8 backtests per window. Measures how much Sharpe drops from in-sample to out-of-sample. Large drop = strategy may be overfit to the training period.

**Sensitivity** — re-runs the strategy with each numeric parameter shifted, one VPS backtest per shift. Booleans are skipped. Measures PnL delta vs the baseline run. Large swings = strategy is fragile to exact parameter values. **MT5 uses 2 shifts (±10%)** to limit queue depth; NT8 uses 4 shifts (±10% and ±25%). `SHIFTS` in `stress_tester.run_sensitivity_task()` is runner-aware. Duration estimate: `_estimate_sens_duration_min(n_params, runner)`.

**Auto-trigger** — fires MC only (no NT8) automatically when a Tier 1 backtest completes or an optimizer picks a winner. Manual trigger always runs all three phases (MC + walk-forward + sensitivity); no user checkbox.

**Child run isolation** — walk-forward and sensitivity runs are inserted into `backtest_runs` with `stress_test_id` set. `lab_db.list_runs()` always adds `r.stress_test_id IS NULL` to its WHERE clause so they never appear in the Runs tab. They're accessible only from `StressTestDetail`.

**Market lock** — `lab_db.running_stress_test_markets()` queries `stress_tests WHERE status LIKE 'running%'` (covers `running`, `running_wf`, `running_sens`), joins to derive `runner`, returns `{futures, forex, run_ids}`. `POST /stress-tests/run` checks this before inserting; 409 if same market is already running. `GET /stress-tests/running-lock` exposes it for the frontend poll.

**Crash recovery** — `lab_db.reset_stale_stress_tests()` marks any `running%` stress tests as `failed_crashed` and their child runs as `failed_timeout`. Called in `main.py` `startup()` — backend restarts automatically clear stuck tests and release the market lock.

---

## Key architectural decisions

**Optimizer implementation:** All optimizations use `search_method = "native"`. The brute-force batch path still exists in `optimization_runner.py` for retrying the two legacy runs in the DB but is not reachable from the UI for new jobs.

- **`"native"`** — sends ONE `POST /native-optimize` to the VPS agent. `nt8_backtest_runner.run_native_optimize_mode` switches the SA to Optimization mode, sets Start/End/Increment ranges for each Strategy Logic param, fires a single Run that uses all CPU cores, then exports the results grid to CSV. MT5 path uses `mt5_agent.py` with `Optimization=1` ini + set-file ranges + HTML combo parser. The backend creates run rows for every combo after the grid is returned. No per-combo equity curve — auto-trigger stress test is skipped; winner must be stress-tested via a manual single rerun. `estimated_runs` is always the full grid size.

**Per-platform job lock — the single source of truth:** There is one physical terminal per platform — one NT8 Strategy Analyzer, one MT5 Strategy Tester — so each platform runs at most ONE job at a time (single backtest, sweep, or optimization), but **the two platforms are fully independent: an MT5 job never blocks an NT8 job and vice versa.** The lock is the DB, scoped by runner. `lab_db.has_running_job(runner)` is the canonical check — it dispatches to `has_running_nt8_job()` / `has_running_mt5_job()`, which each count `status='running'` rows in `backtest_runs` (covers single runs, sweep child runs, and stress-test child runs — all carry `runner`) plus `optimizations`. Every trigger/retry/rerun endpoint across backtests, sweeps, optimizations, and stress tests calls `routers._locks.ensure_platform_idle(runner)` before creating a job; it raises 409 if that platform is busy. **Gates must never read `lab_progress.json`** — that file is for the single-run progress bar only and is shared across both platforms, so using it to gate would cross-block (an MT5 run blocking NT8) and could deadlock on a stale value. There is no cross-platform "any VPS job" lock.

**Must join strategies for optimizations:** `optimizations` has no `runner` column — `has_running_nt8_job()`, `has_running_mt5_job()`, and `get_running_job()` all `LEFT JOIN strategies s ON s.id = o.strategy_id` and filter on `COALESCE(s.runner, 'ninjatrader')`. Without the join a running MT5 optimization would appear as an NT8 job and block NT8. `get_running_job()` returns `{nt8, mt5}` separately, with dedicated per-platform blocks for backtest, sweep, and optimization. Sweep child runs persist `runner` (set in `insert_run_sweep`), so MT5 sweeps lock MT5 and NT8 sweeps lock NT8.

**Crash recovery — DB is authoritative, so it must be cleaned on boot:** A backend restart kills the asyncio task polling a VPS job, leaving the row `status='running'` forever — and since the lock now reads these rows, a stale row would deadlock the platform. `main.py` startup calls `reset_stale_stress_tests()` (stress tests + their child runs) then `reset_stale_runs()` (all remaining `running` `backtest_runs` + `optimizations` → `failed_crashed`). `lab_progress.json` is also reset on startup but only drives the progress bar, not the lock.

**Stress test architecture:** `services/stress_tester.py` runs three phases: (1) Monte Carlo — pure numpy, vectorised, ~5s even for 700+ trades. (2) Walk-forward — N windows × 2 VPS backtests (IS + OOS), sequential. (3) Sensitivity — N params × SHIFTS VPS backtests, sequential; SHIFTS = 2 for MT5, 4 for NT8. Auto-trigger runs MC only — no VPS needed. Manual trigger always runs all three phases.

**Auto-trigger gate — Tier 1 only:** Both paths that auto-trigger MC must check `worthiness_tier == "TIER_1_STRESS_TEST"` before firing. Single-run path (`backtest_runner.py`) already does this. Optimization winner path (`optimization_runner.py`, `_run_winner_backtest`) must also check — without the gate it fires on every winner regardless of how bad the result is, producing unexpected F grades the user never asked for.

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

**Runner dispatcher:** `runner_dispatch.start_backtest(job_spec, runner)` routes to the appropriate backend. Both `"ninjatrader"` (NT8 Strategy Analyzer) and `"mt5"` (MT5 Strategy Tester via `mt5_agent_client`) are wired. `runner_dispatch._nt8_to_mt5_spec()` translates the NT8-style job_spec to the MT5 agent's format — critically, it passes `job_id` through so the MT5 agent stores the job under our `run_id`; without this every status poll returns 404 and the run times out. Timeframe mapping in `_nt8_to_mt5_spec`: M1/M5/M15/M30/H1/H4/D1 (Minute bar_value thresholds: ≥240→H4, ≥60→H1, ≥30→M30, ≥15→M15, ≥5→M5, else M1). `_normalize_mt5_status/results()` translates the MT5 agent's response shape back to the NT8 shape so all callers remain runner-agnostic. `_normalize_mt5_status` passes through actual `pct`, `completed_count`, and `total_count` from the MT5 agent job dict (single backtests have no granular progress so they stay at a low floor; optimizations emit per-combo updates). `runner` field added to `BacktestDetail` model and `_row_to_detail`. File upload/delete also dispatch by extension: `.mq5` files go to `mt5_agent_client`, `.cs` files go to the NT8 nt8_agent.

**Sweep vs. progress lock:** Sweep and optimization runs do NOT use `lab_progress.json`. That file is exclusively for the single-run flow. Sweep/optimization state is tracked only in the DB.

**source_run_id:** `optimizations` stores the `run_id` of the backtest that spawned it. Sweep child runs store the `run_id` of the run that triggered the sweep. The Runs tab uses this to nest linked jobs under their source run. Rows without `source_run_id` (created before this was added) appear flat — no backfill is possible.

---

## Strategy file deployment (Pass 2)

Live behavior. NT8 agent endpoints: `GET/POST/DELETE /files/strategies/<filename>`, `POST/GET /compile`. NT8 strategy folder: `C:\Users\Administrator\Documents\NinjaTrader 8\bin\Custom\Strategies\`. Detail in the Pass2 archive spec.

**Gotchas:**
- **Compile:** `nt8_compile_runner.py` uses pywinauto F5 via NinjaScript Editor (`NCompile.exe` does not exist on this install). Success detected by polling `NinjaTrader.Custom.dll` mtime — NT8 rewrites it on every successful compile (90s timeout).
- **Upload limit:** 256 KB, enforced on both agent and backend router.
- **Lock detection:** agent tries `r+b` open before upload/delete; `IOError` → HTTP 423.
- **Sync-status:** `GET /strategy-files/sync-status` — in sync when expected `.cs` file exists on VPS (presence only, no hash comparison yet).

---

## Strategy location + deploy (Pass 2.5)

Live behavior. Scanner reads from `strategies/` via `rglob("*.cs")`/`rglob("*.mq5")`; `source_path` stored relative to monorepo root (e.g. `strategies/ninjatrader/ORB.cs`); missing `source_path` warns, never auto-deletes. `POST /strategies/{id}/deploy` reads `source_path` and uploads via `runner_dispatch` (`.mq5` → MT5 agent, `.cs` → NT8 agent), returns 202 + `deploy_job_id`. Edge cases: `source_path` null → 400, file missing → 404, VPS locked → 423. Detail in the Pass2.5 archive spec.
