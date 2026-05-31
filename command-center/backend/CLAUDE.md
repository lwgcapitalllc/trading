# CLAUDE.md — Command Center Backend

Auto-loaded by Claude Code when editing any file inside `backend/`.

**Last reviewed:** 2026-05-30

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
│   ├── firms.py           lab — prop firm rules
│   ├── system.py          lab — health + log proxies
│   ├── stress_tests.py    stub
│   ├── sweeps.py          lab — instrument sweep (POST /backtests/sweep, GET /backtests/sweeps/:id)
│   ├── optimizations.py   lab — optimizer (POST /optimizations/run, GET /optimizations/*)
│   └── settings.py
├── services/              business logic, DB access, external clients
│   ├── lab_db.py          only module that touches lab.db
│   ├── strategy_scanner.py
│   ├── evaluator.py       per-firm pass/fail logic
│   ├── backtest_runner.py background VPS polling task (single run)
│   ├── sweep_runner.py    fans out N parallel backtests for a sweep
│   ├── optimization_runner.py  multi-call brute-force optimizer (see note below)
│   ├── worthiness.py      Tier 1/2/3 scoring
│   ├── objectives.py      optimizer objective functions
│   └── vps_client.py      typed HTTP wrapper over vps_agent; runner dispatcher
├── data/lab.db            strategies, firms, runs, evaluations, optimizations
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

## Firm account tiers — eval vs funded

Every firm row has an `account_tier` column: `"eval"` or `"funded"`.

- **eval** firms: full three-way evaluation — drawdown + profit target + consistency rule.
- **funded** firms: drawdown only. `consistency_pass` is stored as `NULL`, `target_pass` is always `True`. The profit target on a funded account is 0 (no requirement).

Never skip the tier check in `evaluator.py`. The current seeded firms are:
- `lucidflex_50k_eval`, `lucidflex_100k_eval` — eval challenges
- `lucidflex_50k_funded`, `lucidflex_100k_funded` — funded account limits

---

## What's built (status)

| Domain | Status | What it does |
|---|---|---|
| Smart Money | ✅ Live | Scans and profiles crypto/forex traders for copy-trading candidates. Scan, terminal, rankings, profile, disqualified log, config, cache tabs. |
| Bots | ✅ Live | Monitors all three live algo instances (gold_main, gold_scalper, gold_fft) via SSH. Global + per-bot risk controls, risk cap deploy with Telegram notification, Telegram users tab. |
| Lab — Strategies | ✅ Live | Registry of NinjaScript strategies scanned from the local repo. Auto-derives param schema from `[NinjaScriptProperty]` attributes. Each strategy has a `runner` field (default `"ninjatrader"`). |
| Lab — Firms | ✅ Live | Prop firm rule profiles (drawdown limits, profit targets, consistency %). CRUD endpoints. Seeded with 4 LucidFlex profiles (50k/100k × eval/funded). |
| Lab — Backtests | ✅ Live | Trigger NT8 runs on the VPS via the agent. Poll to completion. Evaluate against selected firms. Equity curve, daily P&L, per-firm verdicts, full KPI set. After evaluation, computes Worthiness Score (Tier 1/2/3). |
| Lab — Sweeps | ✅ Live | Fan out N parallel backtests across all allowed instruments for a strategy. Each run completes independently with its own worthiness score. |
| Lab — Optimizations | ✅ Live | Multi-call brute-force optimizer (see note). Generates all param combos, runs each as a child backtest, scores by objective (eval_pass_prob or funded_sharpe). Best run tracked in `optimizations.best_run_id`. |
| Lab — System | ✅ Live | Health endpoints (SSH, VPS agent, NT8, compile status). Log proxies. Progress file read. |
| Lab — Stress Tests | 🔲 Stub | Router exists, no logic yet. M3 scope. |
| Settings | ✅ Live | Config read/write. |

---

## M2 key decisions

**Optimizer implementation:** NT8 Optimizer GUI automation (pywinauto) was not attempted. Instead, the optimizer generates all parameter combinations from the grid and drives them as individual backtest calls via the existing VPS agent pipeline (`optimization_runner.py`). Max 4 concurrent VPS jobs (`_MAX_CONCURRENT = 4`). For 3+D grids with "auto" or "genetic" search method, a random subset of up to 200 combinations is sampled. This is slower than NT8's native optimizer but reliable and reuses all M1 infrastructure. If native NT8 optimization is needed in M3, the `vps_client.py` dispatcher pattern makes it easy to route differently.

**Runner dispatcher:** `vps_client.start_backtest(job_spec, runner)` routes to the appropriate backend. Currently only `"ninjatrader"` is wired; `"mt5"` raises `NotImplementedError` as a placeholder for forex work.

**Sweep vs. progress lock:** Sweep and optimization runs do NOT use `lab_progress.json`. That file is exclusively for the single-run flow. Sweep/optimization state is tracked only in the DB.

---

## DB table additions (M2)

`strategies` table: added `runner TEXT NOT NULL DEFAULT 'ninjatrader'`

`backtest_runs` table: added `worthiness_tier TEXT`, `worthiness_reason TEXT`, `worthiness_computed_against_firm TEXT`, `sweep_id TEXT`, `optimization_id TEXT`

New table: `optimizations` — stores optimizer job metadata, progress, and `best_run_id`
