# CLAUDE.md — Command Center Backend

Auto-loaded by Claude Code when editing any file inside `backend/`.

**Last reviewed:** 2026-05-31 (session 4)

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

## Firm account tiers — eval vs funded

Every firm row has an `account_tier` column: `"eval"` or `"funded"`.

- **eval** firms: full three-way evaluation — drawdown + profit target + consistency rule.
- **funded** firms: drawdown only. `consistency_pass` is stored as `NULL`, `target_pass` is always `True`. The profit target on a funded account is 0 (no requirement).

Never skip the tier check in `evaluator.py`. The current seeded firms are:
- `lucidflex_50k_eval`, `lucidflex_100k_eval` — eval challenges
- `lucidflex_50k_funded`, `lucidflex_100k_funded` — funded account limits
- `tradeify_50k_eval`, `tradeify_100k_eval` — eval challenges
- `tradeify_50k_funded`, `tradeify_100k_funded` — funded account limits
- `fundednext_flex_50k_eval`, `fundednext_flex_100k_eval` — eval challenges
- `fundednext_flex_50k_funded`, `fundednext_flex_100k_funded` — funded account limits

---

## What's built (status)

| Domain | Status | What it does |
|---|---|---|
| Smart Money | ✅ Live | Scans and profiles crypto/forex traders for copy-trading candidates. Scan, terminal, rankings, profile, disqualified log, config, cache tabs. |
| Bots | ✅ Live | Monitors all three live algo instances (gold_main, gold_scalper, gold_fft) via SSH. Global + per-bot risk controls, risk cap deploy with Telegram notification, Telegram users tab. |
| Lab — Strategies | ✅ Live | Registry of NinjaScript strategies scanned from the local repo. Auto-derives param schema from `[NinjaScriptProperty]` attributes. Each strategy has a `runner` field (default `"ninjatrader"`). |
| Lab — Firms | ✅ Live | Prop firm rule profiles (drawdown limits, profit targets, consistency %). CRUD endpoints. Firms: 4 LucidFlex (50k/100k × eval/funded) + 4 Tradeify Select (50k/100k × eval/funded) + 4 FundedNext Futures Flex (50k/100k × eval/funded). Schema has `eval_cost_usd`, `activation_fee_usd`, `profit_split_pct` columns. `max_contracts` is free-form JSON dict: carries optional `scaling` object (Tradeify `cumulative_ratchet`, LucidFlex `bidirectional_band`) and optional `mix_allowed`/`mix_ratio_micro_per_mini` flags (FundedNext — minis and micros are mixable at 1:10, unlike Tradeify). FundedNext has fixed contract limits (no scaling), EOD trailing drawdown locking $100 above start, 40% challenge-only consistency (unusual: breach raises target, does not fail), no daily loss limit. LucidFlex rows corrected 2026-05-31: `drawdown_type` -> `trailing_eod`, `force_flat_time_et` -> `16:45`, eval contracts fixed, funded bidirectional scaling added. TODO: verify LucidFlex DLL — `max_loss_intraday` left NULL. |
| Lab — Backtests | ✅ Live | Trigger NT8 runs on the VPS via the agent. Poll to completion. Evaluate against selected firms. Equity curve, daily P&L, per-firm verdicts, full KPI set. After evaluation, computes Worthiness Score (Tier 1/2/3). |
| Lab — Sweeps | ✅ Live | Runs N backtests sequentially (one instrument at a time, `_MAX_CONCURRENT = 1`) across all instruments for a strategy. Each run gets its own worthiness score. Deletable. Cancel endpoint force-fails stuck `running` rows (backend-restart recovery). Retry-all and per-run retry via `POST /backtests/runs/{id}/retry`. |
| Lab — Optimizations | ✅ Live | Multi-call brute-force optimizer. Generates all param combos, runs each sequentially via SA semaphore, scores by objective (eval_pass_prob or funded_sharpe). Best run tracked in `optimizations.best_run_id`. `source_run_id` links an optimization back to the run it was triggered from. Deletable. Per-run retry via `POST /backtests/runs/{id}/retry`. |
| Lab — System | ✅ Live | Health endpoints (SSH, VPS agent, NT8, compile status). Log proxies. Progress file read. `POST /system/vps-agent/start` restarts vps_agent via SSH (`schtasks /run /tn LucidFlexAgent`). |
| Lab — Stress Tests | 🔲 Stub | Router exists, no logic yet. M3 scope. |
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

`optimizations` table key fields: `optimization_id`, `strategy_id`, `instrument`, `start_date`, `end_date`, `commission_per_side`, `slippage_ticks`, `firm_id`, `mode`, `search_method`, `param_grid` (JSON), `status`, `estimated_runs`, `completed_runs`, `best_run_id`, `source_run_id`, `created_at`, `completed_at`.

---

## Key architectural decisions

**Optimizer implementation:** NT8 Optimizer GUI automation (pywinauto) was not attempted. Instead, the optimizer generates all parameter combinations from the grid and drives them as individual backtest calls via the existing VPS agent pipeline (`optimization_runner.py`). `_MAX_CONCURRENT = 1` — the NT8 Strategy Analyzer window is single-threaded; running more than one job at a time causes SA conflicts, display switch failures, and missing XML logs. For 3+D grids with "auto" or "genetic" search method, a random subset of up to 200 combinations is sampled.

**NT8 SA global lock:** All three job types (single backtest, sweep, optimization) share the same physical SA window. `lab_db.has_any_running_vps_job()` checks for any `backtest_runs` or `optimizations` row with `status = 'running'`. All three trigger endpoints call it and return 409 if true. This prevents cross-job conflicts (e.g. a sweep starting while an optimization is in progress).

**Sweep serialisation:** `sweep_runner.py` uses `asyncio.Semaphore(1)` — same constraint as the optimizer. Instruments run one at a time through the SA window.

**Runner dispatcher:** `vps_client.start_backtest(job_spec, runner)` routes to the appropriate backend. Currently only `"ninjatrader"` is wired; `"mt5"` raises `NotImplementedError` as a placeholder for forex work.

**Sweep vs. progress lock:** Sweep and optimization runs do NOT use `lab_progress.json`. That file is exclusively for the single-run flow. Sweep/optimization state is tracked only in the DB.

**source_run_id:** `optimizations` stores the `run_id` of the backtest that spawned it. Sweep child runs store the `run_id` of the run that triggered the sweep. The Runs tab uses this to nest linked jobs under their source run. Rows without `source_run_id` (created before this was added) appear flat — no backfill is possible.
