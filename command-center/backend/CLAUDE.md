# CLAUDE.md — Command Center Backend

Auto-loaded by Claude Code when editing any file inside `backend/`.

**Last reviewed:** 2026-06-01 (session 5 — M3 Steps 2-6: stress testing, grading, frontend)

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
│   ├── strategies.py      lab — strategy registry + GET /:id/instrument_summary
│   ├── rulesets.py        lab — ruleset CRUD (/rulesets)
│   ├── firms.py           backward-compat redirect /firms → /rulesets (deprecated, remove in M4)
│   ├── system.py          lab — health + log proxies
│   ├── stress_tests.py    lab — stress test CRUD + trigger (GET /stress-tests, GET /:id, POST /run, DELETE /:id)
│   ├── sweeps.py          lab — instrument sweep (POST /backtests/sweep, GET /backtests/sweeps, GET/DELETE /backtests/sweeps/:id)
│   ├── optimizations.py   lab — optimizer (POST /optimizations/run, GET /optimizations/*, DELETE /optimizations/:id)
│   └── settings.py
├── services/              business logic, DB access, external clients
│   ├── lab_db.py          only module that touches lab.db
│   ├── strategy_scanner.py
│   ├── evaluator.py       per-firm pass/fail logic
│   ├── backtest_runner.py background VPS polling task (single run)
│   ├── sweep_runner.py    runs N backtests sequentially (semaphore = 1) for a sweep
│   ├── optimization_runner.py  multi-call brute-force optimizer (see note below)
│   ├── worthiness.py      Tier 1/2/3 scoring
│   ├── objectives.py      optimizer objective functions
│   ├── stress_tester.py   Monte Carlo + walk-forward + sensitivity + auto-trigger
│   ├── grading.py         compute_grade() → A/B/C/D/F with plain-English reasons
│   ├── correlation_table.py  hardcoded correlated instrument pairs (M4 will replace with live data)
│   └── vps_client.py      typed HTTP wrapper over vps_agent; runner dispatcher
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
| HTTP (vps_agent) | NT8 control, pywinauto, live job control | `services/vps_client.py` — always use the typed wrapper |

Never make a synchronous SSH call from a request handler that could take > 2s. Background it.

---

## NT8 Strategy Analyzer UI automation (vps_backtest_runner.py)

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

Lab backtests use the same pattern but the "worker" is the VPS agent over HTTP.

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

The `firms` table was renamed to `rulesets` in M3. All references updated. `/firms/*` routes redirect to `/rulesets/*` (deprecated, remove in M4).

**`ruleset_type` values and evaluation logic:**

| ruleset_type | Who uses it | Evaluator behavior |
|---|---|---|
| `prop_eval` | Prop firm eval challenges | drawdown + profit target + consistency |
| `prop_funded` | Prop firm funded accounts | drawdown only; PASS if under limit |
| `personal` | Personal trading accounts | daily_loss_cap + weekly_loss_cap; WARN if weekly breached |
| `demo` | Paper/demo accounts | always PASS/WARN based on net P&L; never DISCARD |

`account_tier` is still present on rows (eval/funded/live) — useful for prop rulesets. `ruleset_type` is the broader category.

New columns on `rulesets`: `ruleset_type`, `daily_loss_cap`, `weekly_loss_cap`, `daily_profit_goal`, `description`.

Seeded rulesets (13 rows): 4 LucidFlex × (eval/funded) + 4 Tradeify × (eval/funded) + 4 FundedNext × (eval/funded) + 1 personal example (`personal_futures_10k_example`).

**Evaluations table:** `firm_id` column renamed to `ruleset_id`. `optimizations` table: `firm_id` → `ruleset_id` too.

`BacktestRunRequest.evaluate_rulesets` — replaces `evaluate_firms` (backward-compat alias still accepted).

---

## What's built (status)

| Domain | Status | What it does |
|---|---|---|
| Smart Money | ✅ Live | Scans and profiles crypto/forex traders for copy-trading candidates. Scan, terminal, rankings, profile, disqualified log, config, cache tabs. |
| Bots | ✅ Live | Monitors all three live algo instances (gold_main, gold_scalper, gold_fft) via SSH. Global + per-bot risk controls, risk cap deploy with Telegram notification, Telegram users tab. |
| Lab — Strategies | ✅ Live | Registry of NinjaScript strategies scanned from the local repo. Auto-derives param schema from `[NinjaScriptProperty]` attributes. Each strategy has a `runner` field (default `"ninjatrader"`). |
| Lab — Rulesets | ✅ Live | Ruleset profiles (formerly "Firms"). CRUD at `/rulesets`. Supports 4 types: `prop_eval`, `prop_funded`, `personal`, `demo`. Seeded: 12 prop firm rows + 1 personal example. Evaluator branches on `ruleset_type`. |
| Lab — Backtests | ✅ Live | Trigger NT8 runs on the VPS via the agent. Poll to completion. Evaluate against selected firms. Equity curve, daily P&L, per-firm verdicts, full KPI set. After evaluation, computes Worthiness Score (Tier 1/2/3). |
| Lab — Sweeps | ✅ Live | Runs N backtests sequentially (one instrument at a time, `_MAX_CONCURRENT = 1`) across all instruments for a strategy. Each run gets its own worthiness score. Deletable. Cancel endpoint force-fails stuck `running` rows (backend-restart recovery). Retry-all and per-run retry via `POST /backtests/runs/{id}/retry`. |
| Lab — Optimizations | ✅ Live | Multi-call brute-force optimizer. Generates all param combos, runs each sequentially via SA semaphore, scores by objective (eval_pass_prob or funded_sharpe). Best run tracked in `optimizations.best_run_id`. `source_run_id` links an optimization back to the run it was triggered from. Deletable. Per-run retry via `POST /backtests/runs/{id}/retry`. |
| Lab — System | ✅ Live | Health endpoints (SSH, VPS agent, NT8, compile status). Log proxies. Progress file read. `POST /system/vps-agent/start` restarts vps_agent via SSH (`schtasks /run /tn LucidFlexAgent`). |
| Lab — Stress Tests | ✅ Live | Monte Carlo (10k reshuffles + 1k bootstrap, vectorised numpy). Walk-forward (N sequential NT8 windows, IS/OOS Sharpe). Sensitivity (±10%/±25% param perturbations via NT8). Auto-triggered (MC only) on Tier 1 backtests and optimizer winners. Graded A-F. |
| Settings | ✅ Live | Config read/write. |

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

`optimizations` table key fields: `optimization_id`, `strategy_id`, `instrument`, `start_date`, `end_date`, `commission_per_side`, `slippage_ticks`, `ruleset_id`, `mode`, `search_method`, `param_grid` (JSON), `status`, `estimated_runs`, `completed_runs`, `best_run_id`, `source_run_id`, `created_at`, `completed_at`.

---

## Key architectural decisions

**Optimizer implementation:** NT8 Optimizer GUI automation (pywinauto) was not attempted. Instead, the optimizer generates all parameter combinations from the grid and drives them as individual backtest calls via the existing VPS agent pipeline (`optimization_runner.py`). `_MAX_CONCURRENT = 1` — the NT8 Strategy Analyzer window is single-threaded; running more than one job at a time causes SA conflicts, display switch failures, and missing XML logs. For 3+D grids with "auto" or "genetic" search method, a random subset of up to 200 combinations is sampled.

**NT8 SA global lock:** All three job types (single backtest, sweep, optimization) share the same physical SA window. `lab_db.has_any_running_vps_job()` checks for any `backtest_runs` or `optimizations` row with `status = 'running'`. All three trigger endpoints call it and return 409 if true. This prevents cross-job conflicts (e.g. a sweep starting while an optimization is in progress). Walk-forward and sensitivity stress tests also check this lock before triggering.

**Stress test architecture:** `services/stress_tester.py` runs three phases: (1) Monte Carlo — pure numpy, vectorised, ~5s even for 700+ trades. (2) Walk-forward — N windows × 2 NT8 backtests (IS + OOS), sequential through SA. (3) Sensitivity — N params × 4 perturbations × NT8 backtests, sequential. Auto-trigger (Tier 1 backtests + optimizer winners) runs MC only — no NT8 needed. Manual trigger can optionally include walk-forward and sensitivity.

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

**Correlation table:** `services/correlation_table.py`. Hardcoded pairs: MES/MNQ, ES/NQ, GC/MGC, CL/MCL, MYM/M2K, plus micro/full equivalents. Shown as an informational note on StrategyDetail when the strategy has been run on both instruments of a pair. M4 will replace with a real correlation matrix.

**Sweep serialisation:** `sweep_runner.py` uses `asyncio.Semaphore(1)` — same constraint as the optimizer. Instruments run one at a time through the SA window.

**Runner dispatcher:** `vps_client.start_backtest(job_spec, runner)` routes to the appropriate backend. Currently only `"ninjatrader"` is wired; `"mt5"` raises `NotImplementedError` as a placeholder for forex work.

**Sweep vs. progress lock:** Sweep and optimization runs do NOT use `lab_progress.json`. That file is exclusively for the single-run flow. Sweep/optimization state is tracked only in the DB.

**source_run_id:** `optimizations` stores the `run_id` of the backtest that spawned it. Sweep child runs store the `run_id` of the run that triggered the sweep. The Runs tab uses this to nest linked jobs under their source run. Rows without `source_run_id` (created before this was added) appear flat — no backfill is possible.
