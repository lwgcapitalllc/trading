# CLAUDE.md — Command Center Backend

**Purpose:** FastAPI backend (`:8000`) — owns all SQLite state, talks to the VPS via SSH + HTTP agents, runs the smart-money pipeline via subprocess, and drives NT8/MT5 backtests.
**Scope:** This covers backend conventions, routers, services, DB, and VPS interaction. It does NOT cover the frontend (see `../frontend/CLAUDE.md`) or `algos/`/`smart-money/` source.
**Status:** Live — lab (strategies, rulesets, backtests, sweeps, optimizations, stress tests, queue, MT5 runner, Python runner) all shipped.
**Last reviewed:** 2026-07-16

Auto-loaded by Claude Code when editing any file inside `backend/`.

FastAPI backend served on `:8000`. Talks to the VPS via SSH and HTTP, runs smart-money pipeline via subprocess, and owns all SQLite state. The frontend never touches the filesystem or the VPS directly.

The lab module (strategies, firms, backtests, evaluations) is live as of M1.

**Lab design principle:** The user always picks which firm challenges to evaluate against. Never default `evaluate_firms` to all firms.

---

## Guides & references

- `command-center/docs/PROP_RULESET_KPIS.md` — per-firm prop ruleset KPIs, doc links, and the DB sync-check query.
- `command-center/docs/BACKEND_BUILD_NOTES.md` — NT8 Strategy Analyzer pywinauto automation implementation notes, and the dynamic sizing/risk engine build history.

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
│   ├── backtests.py       lab — backtest runs; GET /runs/{id}/chart-spec serves the price-chart ChartSpec (chart_spec.py); GET /runs/{id}/news serves the post-run news/holiday trade tags (news_filter.py)
│   ├── strategies.py      lab — strategy registry + deploy endpoint + POST /scan (read-only) + POST /reconcile (destructive orphan cleanup) + GET /:id/instrument_summary + GET /:id/param-types
│   ├── rulesets.py        lab — ruleset CRUD (/rulesets); PATCH = guarded personal-rules edit (prop rows locked 403; PUT also 403 on prop)
│   ├── system.py          lab — health + log proxies
│   ├── strategy_files.py  lab — strategy file deployment (list, upload, delete, compile, sync-status)
│   ├── stress_tests.py    lab — stress test CRUD + trigger (GET /stress-tests, GET /running-lock, GET /strategy-grades, GET /:id, POST /run, DELETE /:id)
│   ├── sweeps.py          lab — instrument sweep (POST /backtests/sweep, GET /backtests/sweeps, GET/DELETE /backtests/sweeps/:id)
│   ├── optimizations.py   lab — optimizer (POST /optimizations/run, GET /optimizations/*, DELETE /optimizations/:id)
│   ├── queue.py           job queue (GET /queue, POST /queue/optimization, POST /queue/stress-test, DELETE /queue/:id)
│   └── settings.py
├── services/              business logic, DB access, external clients
│   ├── lab_db.py          only module that touches lab.db
│   ├── strategy_scanner.py  reads from strategies/ (not algos/); scan is READ-ONLY (add/update + report orphans, never deletes). reconcile_strategies() is the explicit destructive counterpart (DB row + VPS file); remove_strategy() is the shared one-strategy delete
│   ├── evaluator.py       per-ruleset verdict; also exports compute_contract_cap_status()
│   ├── trailing_drawdown.py  compute_trailing_mll() — EOD trailing max-loss engine (the drawdown check)
│   ├── sizing_engine.py     dynamic sizing & risk engine — PURE (no DB/network). run_engine(mode="bullet"|"consistent") sizes each trade off the room left (bullet=max the rules allow; consistent=room÷7), reserves open-trade risk, applies halts, rounds-up-to-min-or-skip, detects breaches; emits size-correct daily_pnl (feeds evaluator) + the decision log. CORE BUILT, not yet wired to a runner — see "Dynamic sizing & risk engine" below
│   ├── decision_log.py      the ONE reusable audit log — TradeDecision/DecisionLog. One JSONL record per signal (taken or not): idea + setup score, every gate's verdict in order, the sizing decision, and the full life of a taken trade. Extensible (new gate = decision.gate(...)); identical in backtest and live
│   ├── metrics.py         shared metric helpers: daily_sharpe / apply_canonical_sharpe / profit_concentration_pct / compute_regime_breakdown (per-regime P&L table → BacktestDetail.regime_breakdown; rescales direction-point counts to trade_count — after the _normalize_mt5_results fix, MT5 equity curves have one point per trade so scale=1.0, but the rescale is kept for safety)
│   ├── backtest_runner.py background VPS polling task (single run)
│   ├── sweep_runner.py    runs N backtests sequentially (semaphore = 1) for a sweep
│   ├── optimization_runner.py  native NT8/MT5 optimizer (one VPS job, all CPU cores)
│   ├── worthiness.py      Tier 1/2/3 scoring
│   ├── objectives.py      optimizer objective functions
│   ├── stress_tester.py   Monte Carlo + walk-forward + sensitivity + auto-trigger
│   ├── grading.py         compute_grade() → A/B/C/D/F with plain-English reasons
│   ├── scripts/backfill_metrics.py  one-time, idempotent backfill of file-derivable metrics on old runs
│   ├── scripts/prop_kpi_audit.py    read-only dump of every prop ruleset's core KPIs from lab.db (the saved "is our engine in sync" query); feeds docs/PROP_RULESET_KPIS.md
│   ├── ohlc_fetcher.py    fetch and cache daily OHLC per (instrument, date); NT8 first, yfinance fallback
│   ├── chart_spec.py      build the ChartSpec for the price-chart panel (candles + sessions + trades + recomputed strategy structure/ATR)
│   ├── news_filter.py     post-run news/holiday tagging — composes the canonical engines/news/ engine (never a 2nd impl) to mark which of a run's trades opened in a high-impact news window / on a bank holiday, for the BacktestDetail News filter card. Pure over a trade list; loads the EventStore cache (see "News filter (post-run)")
│   ├── runner_dispatch.py      typed HTTP wrapper over NT8 nt8_agent; runner dispatcher (routes mt5 → mt5_agent_client)
│   ├── mt5_agent_client.py  typed HTTP wrapper over MT5 agent (port 8766 via SSH tunnel)
│   ├── python_runner.py     local Python runner — runs strategies/python/ packages in-process via the top-level backtest/ package (backtests + A4 optimizer sweep). No VPS, no agent. Resolves strategies by `strategy_class` (the class `__name__` the scanner stored) — NEVER by package id
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

Backtest and optimization runs drive NT8's Strategy Analyzer window via pywinauto (WPF UI automation over SSH), not an API — there's no native NT8 automation interface. This is inherently fragile: WPF control identification, popup timing, and mode-switch state all have non-obvious failure modes.

Full implementation notes (exact sleep durations, coordinate math, ComboBox identification quirks, optimization export mechanics, param-setting order): `command-center/docs/BACKEND_BUILD_NOTES.md`.

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

The `firms` table is now `rulesets`; `firm_id` is `ruleset_id` everywhere (evaluations, optimizations). The `/firms/*` backward-compat redirect shim (`routers/firms.py`) was removed 2026-07-01 — no callers were found (frontend's `useFirms` is an alias to `useRulesets`, never hit `/firms` directly). `BacktestRunRequest.evaluate_rulesets` replaces `evaluate_firms` (backward-compat alias still accepted). Full migration story is in git history (M3).

**`ruleset_type` values and evaluation logic:**

| ruleset_type | Who uses it | Evaluator behavior |
|---|---|---|
| `prop_eval` | Prop firm eval challenges | EOD trailing max-loss (DISCARD on breach) → profit target (WARN if missed; target is raised when a `raise_target` firm's consistency is breached) → consistency (WARN). PASS if all clear. |
| `prop_funded` | Prop firm funded accounts | EOD trailing max-loss only — PASS if not breached, else DISCARD. No WARN. |
| `personal` | Personal trading accounts | Real PASS/DISCARD verdict against the relaxed personal rules (`_evaluate_personal`): DISCARD on `max_consecutive_loss_days` consecutive days whose loss hit `daily_loss_cap`, or on EOD equity dropping `max_drawdown_from_peak_pct` from its running peak; otherwise PASS. `daily_profit_target` is an informational halt note, never a fail. No trailing MLL (max_loss_eod = 0 sentinel), no profit-target requirement, no consistency rule, no reference line. |
| `demo` | Paper/demo accounts | Same as `personal`. |

For prop types the verdict reads `max_loss_eod` (the trailing-MLL amount) and `mll_lock_balance` for drawdown; it never reads `daily_loss_cap` (a soft/informational field for firms like Apex). For personal/demo types `daily_loss_cap` IS a rule input (the capped-day trigger) and `max_loss_eod` is never read (0 sentinel = no trailing EOD rule). `metrics.effective_dd_limit_usd()` is the one place that turns a ruleset into a dollar MC/objective drawdown limit — personal/demo rows translate to `account_size × max_drawdown_from_peak_pct`. The stress-test primary pick excludes personal/demo rows from its strictest-ruleset comparison; worthiness prefers prop rows but falls back to the strictest personal/demo limit when a run was evaluated against personal/demo only (forex).

`account_tier` is still present on rows (eval/funded/live) — useful for prop rulesets. `ruleset_type` is the broader category.

Columns on `rulesets`: `ruleset_type`, `daily_loss_cap`, `weekly_loss_cap`, `daily_profit_goal`, `description`.

Seeded rulesets (16 rows): 4 prop firms = 14 prop rows — LucidFlex, FundedNext, Tradeify each at 50k/100k × eval/funded (12 rows), plus Apex EOD eval-only at 50k/100k (2 rows; funded/PA not yet seeded) — plus 2 personal demo rows (`personal_forex_demo`, `personal_futures_demo`; ruleset_type `personal`, account_tier `demo`). Personal demo rules on a $10k balance: $500 daily loss cap, $1,000 daily profit target, fail at 15% drawdown from peak (`max_drawdown_from_peak_pct`) or 3 consecutive capped-loss days (`max_consecutive_loss_days`) — stored now, enforced in a later evaluator pass. `max_loss_eod = 0` is the sentinel for "no trailing EOD rule" on personal rows (the column is NOT NULL); the evaluator must treat it as rule-absent. All seeded via the per-id idempotent pattern (`_PROP_SEED_ROWS` + `_seed_apex_eod_eval`). The core KPIs of all 14 prop rows (account size, target, drawdown type/amount/lock, consistency, min trading days, contract scaling, funded split, doc links) are documented for hand-off in `command-center/docs/PROP_RULESET_KPIS.md`, which also carries the firm doc links, the saved sync query (`scripts/prop_kpi_audit.py`), and a verification prompt; re-run that prompt to re-check the firms and keep the doc in sync with the DB. Display names: the firm name lives in the UI group header only; `name` carries the program/challenge ("LucidFlex $50k Evaluation", "Select $50k Evaluation", "Futures Flex $50k Challenge", "EOD $50k Evaluation") — canonical map in `_RULESET_DISPLAY_NAMES`, re-applied on every `init_db`. The firm behind the `lucidflex_*` ids is Lucid (Lucid Trading); LucidFlex is its program name.

---

## Dynamic sizing & risk engine + decision log

The mechanism behind the LWG gated-layer model (`docs/LWG_Strategy_Framework.md`,
`docs/dynamic_sizing_engine.md`): the strategy proposes setups at unit size; gates decide
*whether* a trade is allowed; the engine decides *how big* from the room left now. No strategy
manages risk.

- **`services/sizing_engine.py`** — PURE (no DB/network/clock). `run_engine(trades, ruleset,
  *, is_micro, mode)` where mode is the per-run **bullet/consistent** switch: bullet = the most
  the rules allow (with a one-loss-can't-breach guard); consistent = **room ÷ 7** per trade.
  Room is measured to the **trailing floor** (highest-EOD-based, capped at the firm lock — NOT
  balance−start, so growth doesn't fake a buffer). It reserves **open-trade risk** (a running
  trade holds its risk; the next signal shrinks or is blocked), rounds a sub-minimum size **up
  to 1 only if 1 still fits the room** else skips, applies the daily-loss / profit-target halts,
  and detects breaches. Output: `daily_pnl` (size-correct — feeds `evaluator.evaluate_run`
  unchanged, so no second grader), a day-by-day `timeline`, `sized_trades`, and `decisions`.
  Sizing is goal-driven, NOT % of balance and NOT `daily-loss ÷ trade-count` (both dead).
- **`services/decision_log.py`** — `TradeDecision` / `DecisionLog`, the one reusable audit log.
  One JSONL record per signal (taken or not): idea + setup score, every gate's verdict in order
  (which one shut it down, or that all passed), the sizing decision (size + what bound it, or why
  skipped), and the full life of a taken trade (entry, exit, exit reason, P&L). Gates are an
  ordered list — a new gate just calls `decision.gate(name, passed, reason)`, no schema change.
  Pure stdlib, identical in backtest and live.
- **`services/sizing_pipeline.py`** — the FS/IO wiring: `run_sizing_engine(run_id, trade_records,
  ruleset, *, mode, instrument, strategy, results_dir)` builds `RawTrade`s from a runner's export,
  runs the engine, and persists `decisions.jsonl` + `engine_timeline.json` + `engine_daily_pnl.json`
  to the run dir. `size_run_for_rulesets(...)` sizes once per ruleset and additionally writes every
  firm's `{kpis, daily_pnl, timeline}` to `ruleset_sizing.json`, keyed by ruleset id, so every
  evaluation carries its own P&L, timeline, and equity curve (not just the primary/headline
  ruleset) — this is what lets BacktestDetail switch all ruleset-dependent charts/KPIs per firm.
  Locks the runner→engine column contract.
- **Tests:** `tests/test_sizing_engine.py` (20), `tests/test_decision_log.py` (7),
  `tests/test_sizing_pipeline.py` (7) — all green.

**Current state:** ORB.cs (NT8) and LondonBreakout.mq5 (MT5) are both reshaped to trade unit
size and emit `engine_trades.csv` (the runner→engine contract). `nt8_backtest_runner` and the
MT5 agent both read that file back after a run and attach it as `result["engine_trades"]`;
`backtest_runner._handle_complete` sizes any run that carries `engine_trades` per ruleset,
runner-agnostically (same gate for NT8 and MT5). The per-run **bullet/consistent** sizing mode
is plumbed end-to-end: `BacktestRunRequest.sizing_mode` → `backtest_runs.sizing_mode` column →
`BacktestDetail.sizing_mode`/`sized`/`sized_timeline`. Native (unit-size, non-reshaped) runs
carry no `engine_trades` and are unaffected. The whole sized path only activates once a reshaped
strategy actually emits `engine_trades.csv` from a VPS run.

Build history (the ORB/LondonBreakout reshape, the NT8/MT5 wiring order, the per-firm
`ruleset_sizing.json` rollout, and the MT5 tester-agent sandbox file-path gotcha) is in
`command-center/docs/BACKEND_BUILD_NOTES.md`.

## Lens metrics (the per-run scoring layer)

**Drawdown = EOD trailing max-loss** (`services/trailing_drawdown.compute_trailing_mll`), not whole-test max DD. Floor trails the highest EOD balance, capped at `mll_lock_balance` when set; a breach (balance falls through the floor) is the only thing that fails `drawdown_pass`. Detail columns on `evaluations`: `mll_final_floor`, `mll_highest_eod_balance`, `mll_breach_day`, `mll_min_floor_distance`.

**Canonical Sharpe — one definition everywhere.** `metrics.apply_canonical_sharpe(kpis, daily_pnl)` writes the daily-√252 Sharpe into `sharpe`, moves the platform's value to `platform_sharpe`, and sets `sharpe_low_sample` (<10 trading days). It's called at every run-completion path that has `daily_pnl` — single run, sweep child, stress child, optimizer winner — but NOT the native-combo path (no daily_pnl). **Idempotency guard:** only runs when `platform_sharpe` is null, so a second pass can't overwrite the platform value. Walk-forward window Sharpe (`stress_tester._compute_sharpe`) and the optimizer both go through `daily_sharpe_from_values`.

**Contract cap** (`evaluator.compute_contract_cap_status`, informational — never moves the verdict): scaling ladder → `not_applicable`; MT5 (lots) → `not_applicable`; NT8 without per-trade size → `not_evaluable`; NT8 fixed cap + size → real largest-single-trade vs cap. Per-trade `size` is captured from NT8's Quantity column / MT5 volume.

**Profit concentration** persisted as `profit_concentration_pct` (largest calendar quarter's share of gross profit) for later grading use. **Backfill:** `scripts/backfill_metrics.py` recomputes the file-derivable columns (Sharpe trio, profit concentration, contract status) on old runs — idempotent, only touches what's derivable from stored result files.

**Capital-based scores stay client-side** (BacktestDetail). Calmar / Max-DD-% need an account balance (the ruleset's `account_size` or the what-if slider); they're computed in the browser by rebasing the equity, never persisted, and never feed the verdict.

---

## Foundational config (Pass 1)

Rulesets carry 10 foundational fields (risk %, halt fraction, consecutive loss limit, entry hours ET, days allowed, daily profit target, profit lock-in %, commission/side, slippage ticks), injected into strategy params at run creation by `runner_dispatch.inject_foundational()`. Detail is in git history (Pass 1).

**Standing rules:**
- **Category tagging:** every `[NinjaScriptProperty]` carries `[Category("Strategy Logic")]` (tunable, optimizer-visible) or `[Category("Foundational")]` (injected, hidden in UI). Legacy `[Display(GroupName = "Prop Firm")]` falls back to `"foundational"` via GroupName heuristic.
- **Dispatcher injection** happens at three creation points — `trigger_backtest()`, `trigger_sweep()`, `run_optimization()` — using the primary ruleset (first in `evaluate_rulesets`). Merged params stored in DB at creation so all retry paths pick them up without re-injection. **NinjaScript-only:** never inject for the `mt5` runner — foundational params map to `[Category("Foundational")]` properties MQL5 strategies don't have. Forex runs now carry a (personal) ruleset for *evaluation*, but `trigger_backtest()` forces `primary_ruleset=None` when `runner == "mt5"`, so no config is injected. **`run_native_optimization()` enforces the same gate** (`if firm and runner_str != "mt5"`): it previously injected NT8 foundational params (`AccountSize`, `EarliestEntryTimeET`, `DaysOfWeekAllowed`, …) into the MT5 optimizer's `.set` file regardless of runner, and MT5 treats a set file carrying inputs the EA doesn't declare as mismatched — silently running a single backtest instead of the optimization, so `opt_results.csv` is never written. See the set-file purity rule under "Runner dispatcher" below.
- **Primary ruleset rule:** only the first ruleset injects foundational config; others evaluate only. To test two rulesets' configs, run two separate backtests.
- **Sentinel guard:** strategies refuse to trade (warn + return) if foundational params are still at placeholders (-1 or empty string), catching dispatcher failures early.

---

## What's built (status)

| Domain | Status | What it does |
|---|---|---|
| Smart Money | ✅ Live | Scan, terminal, rankings, profile, disqualified log, config, cache tabs. |
| Bots | ✅ Live | SSH monitor + control scaffold; no bots currently registered (all four first-attempt bots deleted 2026-06-22). Global + per-bot risk controls, cap deploy, Telegram users tab. |
| Strategies | ✅ Live | Registry scanned from `strategies/`. Param schema from `[NinjaScriptProperty]`. `runner` field per strategy. `run_count` (shown in the Strategies-tab Runs column) joins `backtest_runs` with `r.stress_test_id IS NULL` — same "real run" filter as `list_runs`, so hidden stress-test child runs don't inflate the count. **Strategy-level narrative** (`edge` TEXT, `steps` JSON) is overlaid from the companion `<Strategy>.meta.json` **top-level** `edge`/`steps` keys by `strategy_scanner._read_strategy_overview` and stored on `strategies`; drives the StrategyDetail Overview. UI-only (no source-hash impact). NULL-safe: a backfill migration sets `steps='[]'` and `Strategy.steps` has a `mode="before"` validator coercing `None→[]` (a NULL would otherwise fail the `list[dict]` response validation on `GET /strategies`). `.mq5` re-scans on meta mtime change; `.cs` only on source change. |
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
| MT5 runner | ✅ Live | `mt5_agent.py` port 8766: Strategy Tester driver (ini+set, terminal64, HTML report). `mt5_agent_client.py` typed wrapper. Runner dispatch via `runner_dispatch`. `/historical_data` maps M5/M15/M30 (was M1/H1/H4/D1 only), `symbol_select()`s before reading bars, **preserves symbol case** and tries the symbol **as given then its root** (terminals vary — GBPJPY is only `GBPJPY.s`, USDJPY both ways). `ohlc_fetcher._resolve_mt5_symbol` passes the run's broker symbol through; `chart_spec._fit_timeframe` caps candle volume (long spans step the base TF up — 5yr → H1). |
| MT5 deployment | ✅ Live | MT5 agent upload/delete `.mq5`. `POST /compile` → MetaEditor. Backend: `POST/GET /strategy-files/compile-mt5`. |
| MT5 native optimizer | ✅ Live | `mt5_agent.py` `POST /native-optimize` + `POST /native-walkforward`; `mt5_agent_client.py` typed wrappers. `runner_dispatch` dispatcher + `optimization_runner.run_native_optimization` route by `runner`. Native single-job `Optimization=1` run — MQL5 frame callbacks (`OnTesterInit/OnTester/OnTesterPass/OnTesterDeinit`) collect per-combo KPIs into `opt_results.csv`; the tester distributes combos across its local agents. **The EA MUST implement those callbacks** — without them the optimizer runs every pass but harvests nothing (single backtests work, optimization yields an empty CSV → "OnTesterPass may not have fired"). CSV columns must match `_parse_opt_csv` / `_OPT_KPI_COLS` (net_pnl/profit_factor/max_drawdown/trade_count/win_trades/sharpe[/gross_profit/gross_loss]) and the param column names must equal the grid keys. Combos rank on MT5's platform Sharpe (the native path has no `daily_pnl`, so canonical Sharpe isn't computed) — re-validate a winner with a single full backtest. |
| Python runner + optimizer | ✅ Live | `services/python_runner.py` — runs `strategies/python/` packages LOCALLY, in-process, via the top-level `backtest/` package (data cache → engine replay → `output.build_results`). No VPS, no agent, no compile. Scanner registers packages declaring `LAB_STRATEGY` (`strategy_scanner._parse_python_package`); the runner resolves by `strategy_class` = the strategy class's `__name__` — the same job-spec key NT8/MT5 use, locked by `test_python_runner.py`'s scanner↔runner agreement test. Optimizer: `runner_dispatch.start_native_optimization(spec, "python")` → `backtest/optimizer.run_sweep` fans combos across cores (lab still owns grid expansion + ranking — `expand_grid`, `objectives.py`). Sweeps run in bar mode; validate the winner in tick mode. Third lock scope: `has_running_python_job()`, surfaced through `get_running_job()`'s `python` bucket and consumed by the frontend's `lib/runner.ts` (wired 2026-07-16). Price charts AND regime tagging both read `ohlc_fetcher.get_ohlc(runner="python")` → `backtest.data.BarSource`, the SAME disk cache the run replayed, and deliberately never fall back to another feed: yfinance maps XAUUSD.s → GC=F, so a fallback would chart/label a spot-gold run off Yahoo's gold FUTURES daily bars. **Feature parity with the native runners is otherwise inherited, not re-implemented** — `run_backtest_job`/`_handle_complete` are runner-agnostic, so sizing (via `engine_trades`, which `backtest/output.py` emits), evaluations, worthiness, canonical Sharpe, regime tagging, the news/holiday filter (needs `entry_ms`, which the Python output carries) and stress tests all work unchanged. |
| Telegram notifications | ✅ Live | `services/notify.py` — urllib Telegram sender (same token as `algos/shared/notify.py`, no extra deps). `stress_tester` fires after grade is written. |
| Job queue | ✅ Live | `job_queue` table + CRUD in `lab_db.py`. `queue_runner.py` asyncio loop runs one job at a time (optimization or stress_test). `routers/queue.py`: GET/POST/DELETE. Started in `main.py` startup. |
| Settings | ✅ Live | Config read/write. `nt8_agent_tunnel` and `mt5_agent_tunnel` both present. |
| Startup — auto-start agents | ✅ Live | Daemon thread on startup (8s delay): `/health` each agent, fires schtask for any that don't respond. |

---

## Worthiness scoring

`services/worthiness.py`. Scored against the strictest evaluated prop firm (smallest `max_loss_eod`). When a run is evaluated against personal/demo rulesets only (e.g. a forex run — no prop firm covers forex), it falls back to the strictest personal drawdown limit (`account_size × max_drawdown_from_peak_pct`, via `metrics.effective_dd_limit_usd`) so forex runs still get a tier. Prop rows always win the pick when present.

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
- `started_at` — actual start of the LATEST attempt. Set = `created_at` at insert; `reset_run_for_retry` moves it to `now` (while `created_at` stays put to anchor list order). Duration on the Runs page is `completed_at − started_at`, so a retried run measures only the attempt that produced the result, not back to the first kickoff. The live progress-bar timer already reads `progress.json`'s per-attempt `started_at`, so it was never affected.
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
- **Pass-probability by ruleset_type** (`run_monte_carlo`): `prop_eval` with a profit target = `mean(final_pnl ≥ target AND max_dd ≤ limit)` (hit target AND never breach). `prop_funded`, `demo`, **and `personal`** = `1 − prob_breach` ("pass" = never breached the drawdown rule — none of them has a profit-target requirement). `personal` MUST stay in the `1 − prob_breach` branch with `demo`: it was previously only in the target branch, so with `profit_target = 0` it fell through both and defaulted to `0.0`, silently reporting 0% pass for any good personal strategy.

**Walk-forward** — sends real backtests to NT8. Splits the original date range into N equal windows. Each window is split 70% in-sample / 30% out-of-sample — two separate NT8 backtests per window. Measures how much Sharpe drops from in-sample to out-of-sample. Large drop = strategy may be overfit to the training period. **Degradation is only computed over windows with a MEANINGFUL positive IS Sharpe** (the serial/MT5 path) — `1 − OOS/IS` is a meaningless signed ratio when IS Sharpe ≤ 0, and *explodes* when IS Sharpe is a tiny positive (a flat in-sample window with Sharpe ~0.002 once produced a 539,229% per-window value → 134,540% average). So windows below `_WF_IS_SHARPE_FLOOR` (0.1) are excluded as not-assessable, and each surviving window is clamped to `_WF_DEG_CLAMP` (`[-100%, +200%]`) before averaging. If no window qualifies, degradation is stored as `None` → UI shows "n/a (IS Sharpe ≤ 0)" and grading treats it as not-run (neither credit nor penalty). The native NT8 WF path (optimization-derived runs) degrades on **profit factor**, not Sharpe (no per-trade data), so the signed-ratio sign-flip can't occur — but it applies the **same honesty rule**: when no window has IS PF > 0, degradation is stored as `None` (not `0.0` — `0.0` would read as "0% = solid robustness" for a strategy unprofitable in every in-sample window), and grading's not-assessable reason is PF-worded ("IS profit factor ≤ 0"). Both WF paths now treat unassessable degradation identically (`None`); `0.0`-as-solid is gone from both.

**Sensitivity** — re-runs the strategy with each numeric parameter shifted, one VPS backtest per shift. **Only STRATEGY-LOGIC params are perturbed** — foundational params (`category == "foundational"` or the MQL5 `f_` prefix) are excluded via `_is_foundational`, the same split the optimizer tunes; perturbing injected config (often at the `-1` sentinel) is wasteful and meaningless. Booleans are skipped. Measures PnL delta vs the baseline run. Large swings = strategy is fragile to exact parameter values. **MT5 uses 2 shifts (±10%)** to limit queue depth; NT8 uses 4 shifts (±10% and ±25%). `SHIFTS` in `stress_tester.run_sensitivity_task()` is runner-aware. The UI time estimate, the note's backtest count, and the run loop all read from shared helpers (`sensitivity_param_count` = perturbed (non-foundational) count, `sensitivity_shift_count` = 2/4 by runner) so they can't drift — `_estimate_sens_duration_min(n_params, runner)`.

**Auto-trigger** — fires MC only (no NT8) automatically when a Tier 1 backtest completes or an optimizer picks a winner. Manual trigger always runs all three phases (MC + walk-forward + sensitivity); no user checkbox.

**Sample-size gate** (`stress_tester.MIN_TRADES_FOR_STRESS = 100`) — one flat floor: below 100 trades the WHOLE stress test is blocked, not just walk-forward. Rationale: the page's output is the A–F grade, and the grade leans on Monte Carlo TAIL percentiles (A = worst-1% drawdown, B = worst-5%) that small samples can't estimate — so a sub-100 grade is false confidence, the same disease as the 134,540% walk-forward number. `POST /stress-tests/run` returns **422** below 100 and `trigger_auto_stress_test` skips (so Tier 1 runs with 50–99 trades get no auto Monte Carlo either). `BacktestDetail.tsx` mirrors the constant and disables the Stress Test button below 100 with an explicit tooltip — backend is authoritative. Clear the bar with more DATA (longer period, more instruments, smaller timeframe), never by loosening params to inflate the trade count (that just curve-fits).

**Child run isolation** — walk-forward and sensitivity runs are inserted into `backtest_runs` with `stress_test_id` set. `lab_db.list_runs()` always adds `r.stress_test_id IS NULL` to its WHERE clause so they never appear in the Runs tab. They're accessible only from `StressTestDetail`.

**Market lock** — `lab_db.running_stress_test_markets()` queries `stress_tests WHERE status LIKE 'running%'` (covers `running`, `running_wf`, `running_sens`), joins to derive `runner`, returns `{futures, forex, run_ids}`. `POST /stress-tests/run` checks this before inserting; 409 if same market is already running. `GET /stress-tests/running-lock` exposes it for the frontend poll.

**Crash recovery** — `lab_db.reset_stale_stress_tests()` marks any `running%` stress tests as `failed_crashed` and their child runs as `failed_timeout`. Called in `main.py` `startup()` — backend restarts automatically clear stuck tests and release the market lock.

---

## Key architectural decisions

**Optimizer implementation:** All optimizations use `search_method = "native"`. The brute-force batch path still exists in `optimization_runner.py` for retrying the two legacy runs in the DB but is not reachable from the UI for new jobs.

- **`"native"`** — sends ONE `POST /native-optimize` to the VPS agent. `nt8_backtest_runner.run_native_optimize_mode` switches the SA to Optimization mode, sets Start/End/Increment ranges for each Strategy Logic param, fires a single Run that uses all CPU cores, then exports the results grid to CSV. MT5 path uses `mt5_agent.py` with `Optimization=1` ini + set-file ranges + HTML combo parser. The backend creates run rows for every combo after the grid is returned. No per-combo equity curve — auto-trigger stress test is skipped; winner must be stress-tested via a manual single rerun. `estimated_runs` is always the full grid size.

**Per-platform job lock — the single source of truth:** There is one physical terminal per platform — one NT8 Strategy Analyzer, one MT5 Strategy Tester — so each platform runs at most ONE job at a time (single backtest, sweep, or optimization), but **the platforms are fully independent: an MT5 job never blocks an NT8 job and vice versa.** `python` is a THIRD independent scope — no terminal at all (runs in the backend process), serialized anyway to protect the local CPU/data cache; its rows are excluded from the NT8 count so the scopes partition. The lock is the DB, scoped by runner. `lab_db.has_running_job(runner)` is the canonical check — it dispatches to `has_running_nt8_job()` / `has_running_mt5_job()` / `has_running_python_job()`, which each count `status='running'` rows in `backtest_runs` (covers single runs, sweep child runs, and stress-test child runs — all carry `runner`) plus `optimizations`. Every trigger/retry/rerun endpoint across backtests, sweeps, optimizations, and stress tests calls `routers._locks.ensure_platform_idle(runner)` before creating a job; it raises 409 if that platform is busy. **Gates must never read `lab_progress.json`** — that file is for the single-run progress bar only and is shared across both platforms, so using it to gate would cross-block (an MT5 run blocking NT8) and could deadlock on a stale value. There is no cross-platform "any VPS job" lock.

**Must join strategies for optimizations:** `optimizations` has no `runner` column — `has_running_nt8_job()`, `has_running_mt5_job()`, and `get_running_job()` all `LEFT JOIN strategies s ON s.id = o.strategy_id` and filter on `COALESCE(s.runner, 'ninjatrader')`. Without the join a running MT5 optimization would appear as an NT8 job and block NT8. `get_running_job()` returns `{nt8, mt5, python}` — one bucket per lock scope, each resolved by the SAME `_SCOPE_RUNNER_SQL` predicate table the `has_running_*_job()` checks use, over the three job types (backtest → sweep → optimization, first hit wins). **The predicates must PARTITION:** a row matching two scopes makes one job block a platform it never touches; a row matching none runs unreported and a second job starts on top of it. NULL/unknown runners fall to NT8. `tests/test_job_locks.py` pins the partition from both sides — the owning scope sees each job type, the other two do not. Sweep child runs persist `runner` (set in `insert_run_sweep`), so MT5 sweeps lock MT5 and NT8 sweeps lock NT8.

**Sizing: who decides the size (2026-07-16).** Two questions, kept separate. (1) **Does the lab size this strategy at all?** `strategies.self_sizing` — 0 (default) = it proposes unit-size trades and `sizing_engine` sizes them per ruleset (ORB, LondonBreakout: the gated layer, which forbids a strategy from baking risk management in — so there is deliberately no meta.json escape hatch, only a python package's `LAB_STRATEGY` may declare it). 1 = the strategy already applied its own risk % (`mpc_sos_fade`'s `exec_risk_pct`), so `_handle_complete` SKIPS the engine entirely. It must: re-sizing discards the strategy's real size, and since `equity_curve` deliberately stays the runner's own curve while `kpis`/`daily_pnl` get replaced, the page would show two different P&Ls for one run. (2) **If the lab sizes it, on whose terms?** `backtest_runs.sizing_mode` ∈ `sizing_engine.MODES` — `consistent` (room÷7) and `bullet` (max the ladder allows) are AUTOMATIC (the ruleset decides); `manual` takes `backtest_runs.manual_risk_pct` and risks exactly that % of the CURRENT balance every trade (so it compounds). Manual sets only the waterfall's BASE — the hard clamps (drawdown room, contract ladder) still apply, so on a ruleset with limits manual is a request, not a guarantee. The **`unconstrained` ruleset** ("Unconstrained (No Limits)") is the pairing that makes X% mean exactly X%: `max_loss_eod=0` + `max_drawdown_from_peak_pct=NULL` ⇒ `current_floor()` is None ⇒ room is None ⇒ no clamp; no daily cap/target ⇒ no halts; no ladder/consistency. **Never add a limit to that row** — its whole purpose is having none.

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

When walk-forward/sensitivity weren't run, those conditions are skipped (grade is based on MC alone — still valid but grade_reasons notes the gap). A WF that ran but couldn't be assessed (degradation `None` — all IS Sharpe ≤ 0 on the serial path, or all IS profit factor ≤ 0 on the native path) is treated the same as not-run — neither credit nor penalty — with a distinct grade_reason that names the path's metric ("Walk-forward ran but IS→OOS degradation is not assessable (IS Sharpe ≤ 0)" serial / "(IS profit factor ≤ 0)" native; chosen by summary shape — native rows carry `is_pf`); the "not run" caveat is scoped to genuinely-not-run so the two messages don't contradict.

**Deployment gates (UI only, soft):** A = funded; B = eval purchase; C = demo. Shown as warnings, never blocking.

**Regime classifier (M4):** Import from `trading/engines/regime/` — the canonical implementation lives there, never duplicate it here. The canonical algorithm doc is at `trading/engines/regime/REGIME_CLASSIFIER.md`. Import pattern:
```python
import sys
from pathlib import Path
# engines/ on sys.path so the canonical engines import by bare name
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))
from regime import classify_regime  # returns one of 5 labels + UNKNOWN
```
Lab uses daily OHLC, so pass the same DataFrame for both `df_short` and `df_long` (`classify_regime(df_daily, df_daily)`). Warmup: fetch 50 extra days before `start_date` so day 1 gets a real label. Window: 34 bars. The OHLC cache is in `instrument_daily_ohlc` — use `services/ohlc_fetcher.get_ohlc()`, never fetch directly in service code.

**Regime filter in optimizer (M4):** When `regime_filter` is set on an optimization, `_pick_best_run` builds a `date → regime` map once from OHLC, then scores each child run using only trades from matching-regime days. NT8 still runs the full backtest period — filtering happens at scoring time only. All three scoring paths (initial run, retry-one, retry-all) go through `_pick_best_run`.

**Sweep serialisation:** `sweep_runner.py` uses `asyncio.Semaphore(1)` — same constraint as the optimizer. Instruments run one at a time through the SA window.

**Runner dispatcher:** `runner_dispatch.start_backtest(job_spec, runner)` routes to the appropriate backend. `"ninjatrader"` (NT8 Strategy Analyzer), `"mt5"` (MT5 Strategy Tester via `mt5_agent_client`), and `"python"` (local in-process via `python_runner` — backtests AND `start_native_optimization`/`native_opt_results`) are wired. `runner_dispatch._nt8_to_mt5_spec()` translates the NT8-style job_spec to the MT5 agent's format — critically, it passes `job_id` through so the MT5 agent stores the job under our `run_id`; without this every status poll returns 404 and the run times out. Timeframe mapping in `_nt8_to_mt5_spec`: M1/M5/M15/M30/H1/H4/D1 (Minute bar_value thresholds: ≥240→H4, ≥60→H1, ≥30→M30, ≥15→M15, ≥5→M5, else M1). `_normalize_mt5_status/results()` translates the MT5 agent's response shape back to the NT8 shape so all callers remain runner-agnostic. `_normalize_mt5_status` passes through actual `pct`, `completed_count`, and `total_count` from the MT5 agent job dict (single backtests have no granular progress so they stay at a low floor; optimizations emit per-combo updates). `runner` field added to `BacktestDetail` model and `_row_to_detail`. File upload/delete also dispatch by extension: `.mq5` files go to `mt5_agent_client`, `.cs` files go to the NT8 nt8_agent.

**Set-file purity (MT5) — the `.set` file must contain ONLY inputs the target EA declares.** `_nt8_to_mt5_spec` provides standalone foundational (`f_*`) defaults for raw MT5 runs (no ruleset → `inject_foundational` never fires), but that default set is a *union* across MT5 EAs (e.g. it carries MeanReversion's `f_BrokerToEtOffsetHours`). It now **filters those defaults to keys present in the strategy's scanned `params`** (`{k: v for k, v in foundational_defaults.items() if k in params}`) so an EA never receives an `f_` input it doesn't declare. Strategies always pass their declared `f_` params (at the `-1` sentinel pre-injection), so a missing key genuinely means "not an EA input". MT5 tolerates a *lone* unknown input, but a set file polluted with several is treated as mismatched and the optimizer silently degrades to a single backtest (no `opt_results.csv`). This is the runtime twin of the `run_native_optimization` gate above — both exist to keep the MT5 set file clean.

**MT5 deal direction vs position direction:** MT5 Strategy Tester emits 2 deal-rows per trade — an entry deal (profit=0, deal direction = position direction: "buy" for Long, "sell" for Short) and an exit deal (profit=realized P&L, deal direction = opposite of position direction: "buy" to close a Short, "sell" to close a Long). `_normalize_mt5_results` **builds the equity curve directly from the paired trades** — it walks deals in time order (entry = profit==0.0, exit = profit≠0), pairs them via a **FIFO queue** of pending entries (so two positions open at once close first-opened-first-closed instead of the later entry clobbering the earlier), and emits **one directional point per closed trade**, accumulating realized P&L onto an opening-balance anchor. This guarantees `long + short == trade_count` for every consumer (Long-vs-Short breakdown, regime breakdown, stress-test trade-P&L list, price-chart markers). **Do NOT** revert to overlaying direction onto the agent's raw balance curve keyed by exit timestamp: MT5 timestamps are minute-resolution, so two trades closing in the same minute collapsed onto one point and the breakdown silently undercounted (long+short < trade_count). And do NOT map all deals naively — that doubles the trade count and inverts the labels on exit deals. The entry/exit split is heuristic (profit==0.0 = entry), so a genuine $0.00 breakeven exit would be misread as an entry — acceptably rare with commissions, but the real fix would need the report's Direction (in/out) column, which `mt5_agent.py` drops before the backend sees it.

**`delete_run` cascade — stress tests included:** `stress_tests.run_id` is a FOREIGN KEY into `backtest_runs`, so a run that has a stress test cannot be deleted until that test (and its walk-forward/sensitivity child runs) is gone — otherwise SQLite raises `IntegrityError` and the DELETE endpoint 500s. `delete_run` calls `_purge_stress_tests_for_runs()` for the target run AND for the optimization/sweep child runs it cascades (a winner or sweep child can also carry a stress test). A stress test's own child runs never carry a nested stress test (auto-trigger is parent-only), so one level of cascade suffices. `delete_run` **returns the run_ids of every backtest_run it deleted** (target + all cascaded children; empty list = run not found), and the DELETE router `shutil.rmtree`s each one's `reports/lab/<run_id>` dir so no orphan report folders are left behind.

**Sweep vs. progress lock:** Sweep and optimization runs do NOT use `lab_progress.json`. That file is exclusively for the single-run flow. Sweep/optimization state is tracked only in the DB.

**source_run_id:** `optimizations` stores the `run_id` of the backtest that spawned it. Sweep child runs store the `run_id` of the run that triggered the sweep. The Runs tab uses this to nest linked jobs under their source run. Rows without `source_run_id` (created before this was added) appear only in their own tab — no backfill is possible.

**Optimizer-combo full backtest scoring (inherit, else prompt):** combo runs (`insert_run_optimization`) don't store an eval selection, so `POST /runs/{id}/retry` resolves one before re-firing: explicit `RetryRunRequest.evaluate_rulesets` (the UI's choice) > the optimization's own `ruleset_id` > the spawning run's `evaluate_firms` (forex/`raw` optimizations have no `ruleset_id` but are usually launched from an evaluated parent) — see `optimization_runner.resolve_opt_eval_rulesets`. When nothing is inheritable and no explicit choice was sent, the endpoint returns `{status: "needs_ruleset"}` WITHOUT starting a run; the frontend prompts (`FullBacktestEvalModal`) and re-fires with the choice. `retry_single_optimization_run(run_id, evaluate_rulesets=...)` then scores via `_handle_opt_complete` → `evaluator.evaluate_run`. Without this a combo full backtest completed unscored (empty `ruleset_ids` → zero evaluation rows → no PASS/DISCARD).

---

## Strategy file deployment (Pass 2)

Live behavior. NT8 agent endpoints: `GET/POST/DELETE /files/strategies/<filename>`, `POST/GET /compile`. NT8 strategy folder: `C:\Users\Administrator\Documents\NinjaTrader 8\bin\Custom\Strategies\`. Detail is in git history (Pass 2).

**Gotchas:**
- **Compile (NT8):** `nt8_compile_runner.py` uses pywinauto F5 via NinjaScript Editor (`NCompile.exe` does not exist on this install). **Success** = `NinjaTrader.Custom.dll` mtime advances (NT8 rewrites it on every successful compile). **Failure** is read straight from the editor's UIA error grid — NT8 keeps F5 compile errors ONLY in that in-memory grid, never in any trace/log file (verified: the trace/log dirs carry zero compile output), so polling logs can't surface them. The runner scrapes the grid rows (`ORB.cs  Identifier expected  CS1001  1  16`) and emits each as an `ERROR:` line, which the `CompileModal` renders one per line. It fails **fast** (~6–10s, after a 6s grace for the grid to repopulate) instead of always waiting the full 90s. Guardrails: real error rows are trusted unconditionally; the "errors must be resolved" status marker only counts if it's *fresh* (captured before vs after F5, so a stale marker from a prior failed build can't false-trip); if the grid read finds nothing it still fails fast with an honest "open the editor" message; a true hang falls back to the 90s timeout. The NT8 agent spawns the runner as a fresh subprocess per compile, so a runner change is live on `git pull` alone — no agent restart. **Note:** sync-status compares only the hashes command-center itself deployed/compiled — it never re-hashes the live VPS file, so a file hand-edited directly on the VPS (bypassing deploy) still shows green "In sync"; a failed compile never advances `compiled_source_hash` (`mark_runner_compiled` runs only on `status == "success"`), so the badge is honest for the normal deploy→compile flow.
- **Compile (MT5):** `mt5_agent._run_compile` compiles each `.mq5` explicitly (`metaeditor64.exe /compile:<file> /log`) and confirms success the same way NT8 does — by mtime. It records each `.ex5` mtime before compiling and requires it to advance afterward; MetaEditor's exit code is unreliable and the directory form (`/compile:<dir>`) could silently no-op, reporting a stale `.ex5` as success. A file whose `.ex5` mtime does not move is a hard failure (`status: failed`) with the compiler `.log` lines surfaced in `errors` — never reported as success. **Warnings** are scraped from the same `.log` and returned in `warnings`, but the match requires the `": warning"` token (MQL5 format `file(line,col) : warning 123: msg`), NOT a bare `"warning"` substring — MetaEditor's trailing summary line `Result: 0 errors, 0 warnings, …` contains the word "warning" and a loose check false-positived a clean build as "1 warning". **The MT5 agent is a long-running process** (not respawned per compile like the NT8 runner), so an agent-side change like this is live only after `git pull` on the VPS **and** restarting the `MT5AgentRDP` schtask — never a blanket `taskkill python.exe` (that also kills the NT8 backtest agent).
- **Upload limit:** 256 KB, enforced on both agent and backend router.
- **Lock detection:** agent tries `r+b` open before upload/delete; `IOError` → HTTP 423.
- **Sync-status:** `GET /strategy-files/sync-status` — **content-aware** (no longer presence-only). It reads the local source **live from disk**, hashes it (md5, same as the scanner via `strategy_scanner.source_hash`), and compares to the recorded deployed/compiled hashes: `needs_deploy = local_hash != deployed_source_hash`, `needs_compile = deployed_source_hash != compiled_source_hash`. `in_sync = file_exists_on_vps AND not needs_deploy`. Also returns `current_version` / `deployed_version` / `compiled_version`. It lazily registers the live hash (`ensure_strategy_version`) so the current version always resolves even before a re-scan. A 502 from the NT8 agent still hard-fails the whole call (MT5 agent degrades gracefully).

## News filter (post-run)

The economic-calendar (news) filter is a **post-run view layer**, NOT a run-time gate: the lab runs every backtest RAW (news is never wired into the C#/MQL5 strategy), so removing news-window trades is pure arithmetic on the finished trade list — instant, no VPS re-run. Design decision (Aaron 2026-07-05): **run raw + toggle after.** Window default **15 min before / 30 min after** a high-impact USD release (asymmetric — liquidity dies only in the last minutes before; the spike/reversal/move run 15–30 min after). **Bank holidays are ALWAYS excluded** (Aaron's rule — not on the toggle); the toggle governs only news-window trades.

- **`services/news_filter.py`** — composes the canonical `engines/news/` engine (imported by bare name after adding `engines/` to `sys.path`, same pattern as regime; **never a second calendar impl**). `build_report(trades, pre, post, ...)` loads the `EventStore` cache, builds a lab `NewsPolicy` (high-impact USD, holidays always), and walks each trade's `entry_ms` through the engine → per-trade `{in_coverage, in_news, in_holiday, title}` + coverage boundary + counts. Reads `in_news` (a high-impact window) and `in_holiday` **separately** so the UI keeps them separable. 9 unit tests (synthetic events, no network). Coverage honesty: outside the fetched calendar range trades come back untagged (never guess) — backfill months via `engines/news/tools/backfill.py`.
- **`GET /backtests/runs/{id}/news?pre=&post=`** → `RunNewsReport` (models.py `RunNewsReport`/`NewsTradeTag`). Pure off the stored `equity_curve` — no VPS. `pre`/`post` are the window minutes (sliders re-call to re-tag). Old runs with no `entry_ms` come back untagged.
- **Trade entry time capture:** `parse_trades_csv` now stores each trade's `entry_ms` (UTC epoch ms) on its equity-curve point, from the NT8 "Entry time" column via `_parse_nt8_dt`. The VPS **NinjaTrader Time zone is UTC** (confirmed) → naive value treated as UTC, no offset. Old runs predate this → re-pull with **Reload charts** (or rerun).
- **Strategy sets the toggle's start:** `strategies.avoid_news` (INTEGER col, migration; default 0) overlaid from `<Strategy>.meta.json` top-level `"avoid_news"` by `strategy_scanner._read_strategy_overview`, exposed on `Strategy.avoid_news`. `true` → the News toggle starts "Removed". `ORB.meta.json` ships `avoid_news:true` (gold avoids news). **Scanner fix:** the `.cs` skip now also re-scans on meta.json **mtime** (mirrors the `.mq5` path) — before this, a meta-only edit on an unchanged `.cs` source (avoid_news, edge/steps, param labels) never took effect. A **Scan** picks up the new value.
- **TODO (#3, not built):** wire the MT5/forex path — `runner_dispatch._normalize_mt5_results` needs its own `entry_ms`, and the **MT5 broker server clock is NOT UTC** (offset + DST), so it needs its own timezone handling (a confirming step like the NT8 one). Gold-on-NT8 works today; forex-on-MT5 does not until this lands.

## Strategy versioning (content-addressed)

`strategy_versions` table — the single source of truth for "what version of strategy X exists / is running." Each distinct source content hash maps to a monotonic `version` per strategy (PK `(strategy_id, version)`, UNIQUE `(strategy_id, source_hash)`); reverting to earlier content **reuses** its original version. `lab_db.ensure_strategy_version()` assigns/returns it (content-addressed, idempotent, retries on the rare concurrent-PK race); `version_for_hash()` resolves a stored hash; `list_strategy_versions()` is the history (newest-first), exposed at `GET /strategies/{id}/versions`.

Versions are registered in three places: the **scanner** (every scan, both `.cs`/`.mq5`, before the skip check so unchanged strategies still register), the **deploy** endpoint, and the **upload** endpoint. Lab-VPS deploy/compile state lives as columns on `strategies` (`deployed_source_hash`/`deployed_at`, `compiled_source_hash`/`compiled_at`): `set_strategy_deployed()` stamps the deployed hash + flags needs-compile (`is_compiled=0`); `mark_runner_compiled()` stamps `compiled_source_hash = deployed_source_hash` on compile success (content-accurate, not just the coarse `is_compiled` boolean). **Hash parity is essential** — anything that records a deployed hash must hash the same way the scanner does (decode bytes utf-8 errors=replace → md5), or `deployed_version` won't resolve.

**First-run note:** strategies deployed before this feature have `deployed_source_hash = NULL`, so they correctly show `needs_deploy` until deployed once through the tracked path (we never fake a hash we can't verify — the VPS agent's file listing exposes size/mtime, not content). **Scalability:** the version registry is target-agnostic — a future "deploy version N to bot X" records `(strategy_id, target, version)` in its own table without touching the registry; the lab VPS is just today's only target.

---

## Strategy location + deploy (Pass 2.5)

Live behavior. Scanner reads from `strategies/` via `rglob("*.cs")`/`rglob("*.mq5")`; `source_path` stored relative to monorepo root (e.g. `strategies/ninjatrader/ORB.cs`); missing `source_path` warns, never auto-deletes. `POST /strategies/{id}/deploy` reads `source_path` and uploads via `runner_dispatch` (`.mq5` → MT5 agent, `.cs` → NT8 agent), returns 202 + `deploy_job_id`. Edge cases: `source_path` null → 400, file missing → 404, VPS locked → 423. Detail is in git history (Pass 2.5).

**Bidirectional delete (reconcile) — deletion propagates only on an explicit action.** Deleting a source file from the repo should mean "remove everywhere" (DB row + the deployed `.cs`/`.mq5` on the VPS NT8/MT5 folder), but that destructive step is **never** wired into a scan. `scan_strategies()` is READ-ONLY: it adds/updates from disk and calls `_detect_orphans()` (DB strategies whose recorded `source_path` no longer exists on disk) to REPORT them in `ScanResult.orphans` — it deletes nothing. A scan is a frequent read; a mis-synced disk (wrong `MONOREPO_ROOT`, repo not checked out) would otherwise silently wipe every deployed file. The destructive cleanup is a separate endpoint, `POST /strategies/reconcile` → `reconcile_strategies()`, which calls `remove_strategy(sid)` for each orphan (best-effort VPS delete — 404/"not found" counts as success; a real failure is surfaced as a warning but never blocks the DB removal) and returns `ReconcileResult{removed, warnings}`. The per-strategy `DELETE /strategies/{id}` uses the same `remove_strategy` helper. Frontend (`Strategies.tsx`): Scan toast flags orphan count; a red **Reconcile (N)** button appears only when the last scan found orphans, fronted by a `ConfirmDeleteModal` listing exactly which strategies go.

**`delete_strategy` cascades the FK chain.** Foreign keys are ON, and `backtest_runs`/`optimizations` reference `strategies` (and `evaluations`/`stress_tests` reference those runs), all `NO ACTION`. So `lab_db.delete_strategy()` purges the whole chain children-first in one transaction — evaluations + stress_tests (via the strategy's run_ids) → backtest_runs + optimizations → strategy_versions → the strategy — or deleting any strategy that has runs raises `FOREIGN KEY constraint failed` (this was an unhandled 500 on reconcile of a strategy with runs).

**MT5 delete removes BOTH the `.mq5` and the `.ex5`.** MT5 loads the compiled `.ex5`, which outlives its source — deleting only the `.mq5` leaves the strategy in the Navigator and Strategy Tester. `mt5_agent_client.delete_strategy_file()` deletes both siblings (`_delete_one` per file; an already-absent sibling 404 is fine; fails only on a real error or if neither existed). NT8 has no analog — it compiles all `.cs` into one `NinjaTrader.Custom.dll`, so deleting the `.cs` + recompiling clears it.
