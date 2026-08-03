# CLAUDE.md — Command Center Backend

**Purpose:** FastAPI backend (`:8000`) — owns all SQLite state, talks to the VPS via SSH + HTTP agents, runs the smart-money pipeline via subprocess, and drives NT8/MT5 backtests.
**Scope:** This covers backend conventions, routers, services, DB, and VPS interaction. It does NOT cover the frontend (see `../frontend/CLAUDE.md`) or `algos/`/`smart-money/` source.
**Status:** Live — lab (strategies, rulesets, backtests, sweeps, optimizations, stress tests, MT5 runner, Python runner) all shipped.
**Last reviewed:** 2026-08-02 — 🔴 **`python_runner` was charging neither the SPREAD nor the OVERNIGHT SWAP, the two costs the lab already knew.** The 2026-08-01 fix wired commission and slippage through; these two were never collected at all, so bar mode stayed frictionless in a way that fix did not reach. A request now carries **`cost_layers`** (which costs to charge) + **`broker_profile`** (whose measured facts to charge them from) — `COST_LAYERS` is the roster, `backtest.fills.PROFILES` the source — and **every layer is OFF by default**, Aaron's explicit call, so a bare run stays comparable to the TradingView Strategy Tester. Swap needed no new code: the charge path has always run in bar mode and was dead only because `_cost_profile` passed `swap=None`. ⚠ **`cost_layers` absent (`None`) is NOT `[]`** — `None` = a row predating the layers, which must keep the OLD contract; `[]` = charge nothing. Collapsing them would re-price all 80 stored runs the first time one was retried, so `routers/backtests._json_list` preserves the distinction and the API models it as `Optional[list[str]]`. ⚠ **`spread` and `swap` are never accepted from the request** — they are MEASUREMENTS, and a field the operator can type is a field that can disagree with the broker; `GET /backtests/broker-profiles` exists so the Run modal never retypes one. The `$0.33` this repo had recorded is **PU Prime's**, and using it for a Vantage backtest overstated the cost by 50% (Vantage measures **$0.22** over 1,494,459 cached ticks). ⚠ **`bid_ask_fills` REPLACES the spread cost rather than adding to it**, and it is the only layer that can change which trades exist. ⚠ **Sweeps and stacks do not write the columns yet**, so they land in the legacy branch and stay frictionless — correct today, wire them before anyone expects a priced stack. Both `_cost_profile` call sites inherit it, so the optimizer cannot rank combos on one cost model and hand the winner to a run on another. 356 tests green (7 new in `tests/test_python_runner.py`). Full rules: *Layered costs* below. Earlier the same day: 🔴 **everything the price chart draws except the TRADES was clipped to the SHIPPED candle window, so scrolling back far enough emptied the chart.** `chart_spec._capped_start` ships the newest ~17 months of a 6.5-year run and the panel pages the rest in on scroll-left — but `overlays` (structure + FVG), `blocks` and `misses` were only ever built over those shipped candles, so past that boundary every layer the reader had switched on drew nothing while its toggle still read ON. Indistinguishable from the panel forgetting the setting, and reported as exactly that. `GET /runs/{id}/candles?analysis=true` → **`chart_spec._page_analysis`** now serves each paged window's own analysis, built with the SAME functions `build_chart_spec` uses. ⚠ **The engines are streaming state machines, so a page is replayed with `_PAGE_WARMUP_BARS` (2,000) of older bars in front of it** and only overlays reaching into the window are returned — a cold replay would open every page with no swings and no live gaps, i.e. a seam that reads as "the layer stopped working" one page further back. ⚠ **A page's internal structure is demoted to Historic** (`_demote_page_internal`): `build_market_structure_overlays` calls the newest leg in whatever it replayed "current", and only the shipped window holds the leg the run actually ended in — several pages each claiming a current leg would make that toggle describe something that does not exist. Analysis is best-effort and wrapped: a failure still delivers the page's bars. Measured on run `211384ddbea4`: one page = 11,259 candles + 1,309 overlays + 21 blocks + 45 misses, ~+2s and ~+230 KB over the bare page. 337 tests green (7 new in `tests/test_chart_page_analysis.py`). **The standing lesson, and it is not the label-on-a-screen one: a per-window computation behind a view the reader can EXTEND is a silent hole. Whatever the view can reach, the data has to reach too.** Earlier: 🔴 **the "SSH" health check never touched the tunnel, and `/health` on the MT5 agent never touched MT5.** `_check_ssh` ran `ssh forexvps "echo ok"` — a brand-new connection unrelated to the port forwards — so the dot went green over a dead tunnel; and the MT5 agent answers `ok` whether or not its terminal is running or logged in, so a disconnected MT5_Lab showed green while every python run needing uncached bars failed at fetch time. Both are measured properly now (`ssh_tunnel` = the forwards are bound, `vps_reachable` = the old question, `mt5_connected`/`mt5_server`/`mt5_account` off the agent's `/status`), and `mt5_connected` is `Optional[bool]` because **`None` = could not ask, which is not the same as disconnected**. With them, `main._auto_start_agents` — a one-shot thread 8s after boot — became **`services/agent_supervisor.py`**, a 60s loop whose first pass is identical to every later one; see *The agent supervisor* below for the two-probe table, the job-lock guard, and the deliberate unbound-vs-stale asymmetry. `restart_tunnel`/`schtasks_run` moved out of `routers/system.py` into that service (subprocess calls belong in `services/`, and `main.py` had been reaching across into the router to call one). Also new: `services/readiness.py`, the boot report for dependencies that fail silently. 330 tests green (31 new). Earlier: 2026-07-31 — **profit concentration had been measuring the account, not the edge.** The largest-quarter share was weighted in DOLLARS, which on a compounding run reports the compounding: the last quarter of an 85x account holds nearly all the dollars however evenly the edge is spread. Run `d2ab68f9e884` read **88.94%** — past the 60% "overfit risk" threshold — where the same trades weighted by RETURN read **39.97%**. `profit_concentration_pct` now takes the equity curve (that is what says whether a run compounded), stores a `profit_concentration_basis` beside the number, and `init_db` re-stamps history; all 78 completed runs were converted. See `## Metrics` → *Profit concentration*. Same day: **`unconstrained` had been returning PASS on every run, including one that lost 95% of the account.** `_evaluate_personal` ended `DISCARD if failures else PASS`, and both its checks are guarded on limits that row deliberately does not set, so `failures` was empty by construction — a vacuous pass, and the exact opposite of what `lab_db.py`'s seed note on that row says ("a run against it cannot be graded"). It now returns `INFO` ("Not graded" in the UI). Verdicts are **stored**, so `init_db` also carries an idempotent migration rewriting the affected `PASS` rows — every evaluation row in the live DB was this case. See `## Ruleset types` → *Nothing checked is not a pass*. Earlier: 2026-07-30 — **the stress-test engine was measuring the wrong things, and the D grade on `630cefbebd8347db` was the engine's fault, not the strategy's.** Four defects fixed, all generic (Aaron's scoping rule: fix what is inaccurate for ANY strategy, never tune the engine to this one). (1) Monte Carlo shuffled a DOLLAR P&L series on a compounding run — trade size drifts 17.7x across that run, so the shuffle simulated a strategy that never existed; it now switches to the per-trade RETURN series and compounds when the dollars actually drift, and the worst-1% drawdown went $41,970 → $359,886. (2) Drawdown is now compared PERCENT-to-percent on such runs — the dollar view had reported a 100% breach of total ruin across 20,000 simulations that never once wiped out the account. (3) Sensitivity scores on PROFIT FACTOR, not net P&L, so a sizing knob is no longer graded as fragility (`exec_risk_pct`: 85.8% on profit vs 11.8% on PF, and it alone set the run's score); no-op shifts are skipped, which is where ~50 of the run's 80 minutes went (43 of 60 backtests reproduced the baseline exactly). (4) Walk-forward now drops windows under 20 trades, and an unassessable WF caps the grade at B instead of being silently free. Also: a `None` grade is now a first-class outcome — **D used to be the CEILING for a ruleset stating no drawdown limit** — and `personal_forex_risk` (55%) was seeded so forex runs have a bar to be graded against. ⚠ Grading no-limit rulesets against total RUIN was built, measured, and removed — see the walk-back in `## Robustness grading`. Earlier: 2026-07-29 — `entry_ms` added to `models.EquityPoint`, which is what had the News filter reporting every run as "made before trade times were recorded"; the filter now works on Python runs too. 2026-07-27 — missed setups (how close the ones that died came) plumbed alongside blocked setups, strategy → output → run dir → chart spec; `chart_spec` now ships the run's own timeframe and caps the WINDOW instead of coarsening the bars

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
│   ├── backtests.py       lab — backtest runs; GET /history-limit serves the measured broker history floor (drives the UI date picker); GET /runs/{id}/chart-spec serves the price-chart ChartSpec (chart_spec.py); GET /runs/{id}/news serves the post-run news/holiday trade tags (news_filter.py)
│   ├── strategies.py      lab — strategy registry + deploy endpoint + POST /scan (read-only) + POST /reconcile (destructive orphan cleanup) + GET /:id/instrument_summary + GET /:id/param-types
│   ├── rulesets.py        lab — ruleset CRUD (/rulesets); PATCH = guarded personal-rules edit (prop rows locked 403; PUT also 403 on prop)
│   ├── system.py          lab — health + log proxies
│   ├── strategy_files.py  lab — strategy file deployment (list, upload, delete, compile, sync-status)
│   ├── stress_tests.py    lab — stress test CRUD + trigger (GET /stress-tests, GET /running-lock, GET /strategy-grades, GET /:id, POST /run, DELETE /:id)
│   ├── sweeps.py          lab — instrument sweep (POST /backtests/sweep, GET /backtests/sweeps, GET/DELETE /backtests/sweeps/:id)
│   ├── optimizations.py   lab — optimizer (POST /optimizations/run, GET /optimizations/*, DELETE /optimizations/:id)
│   ├── calendar.py        live News Calendar tab — thin GET /calendar?from&to (ISO); returns the whole week unfiltered, 400 on bad ISO/window, 502 on feed error
│   └── settings.py
├── services/              business logic, DB access, external clients
│   ├── lab_db.py          only module that touches lab.db
│   ├── strategy_scanner.py  reads from strategies/ (not algos/); scan is READ-ONLY (add/update + report orphans, never deletes). reconcile_strategies() is the explicit destructive counterpart (DB row + VPS file); remove_strategy() is the shared one-strategy delete.
│   │                      ⚠ Its tests state the expected roster ONCE, as `EXPECTED_CLASS_NAMES` in
│   │                      tests/test_strategies.py — added/skipped counts are `len()` of it, never a
│   │                      repeated literal. Adding a strategy used to fail three tests that each had
│   │                      to be traced back to the same cause; now it is a one-line edit
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
│   ├── scripts/backfill_regime_timeline.py  opt-in backfill of `regime_timeline.json` on old runs (`--force`, `--run-id`); kept OUT of backfill_metrics.py because it fetches OHLC
│   ├── scripts/prop_kpi_audit.py    read-only dump of every prop ruleset's core KPIs from lab.db (the saved "is our engine in sync" query); feeds docs/PROP_RULESET_KPIS.md
│   ├── ohlc_fetcher.py    fetch and cache daily OHLC per (instrument, date); NT8 first, yfinance fallback
│   ├── chart_spec.py      build the ChartSpec for the price-chart panel (candles + sessions + trades + blocked setups + recomputed strategy structure/ATR + market-structure overlays). Always ships the timeframe the run TRADED and caps the WINDOW instead (`_capped_start` → the newest slice under `_CANDLE_CAP`), with `historyStartMs` telling the panel how far back it may page; see "ChartSpec candles" below. `_build_blocks` reads the run dir's `blocked_setups.json` — see "Blocked setups" below; `_build_misses` reads `missed_setups.json` and ALSO returns the derived `missNoise` list — see "Missed setups" below
│   ├── fvg_overlays.py    replay the CANONICAL engines/fair_value_gaps/ engine (+ engines/equal_highs_lows/
│   │                      for mpc's eqExemptFvg cap coupling) over a run's candles → the "Fair Value Gaps"
│   │                      overlay group. Emits a box ONLY for a gap that was LIVE on a trade-entry / blocked /
│   │                      missed bar (all of them when several overlap); everything else is dropped. Settings
│   │                      are mpc_assistant.pine's LOCKED constants incl. the timeframe-SPLIT gap floor —
│   │                      NOT the strategy's, which differ. See "Fair value gaps" below
│   ├── structure_overlays.py  replay the CANONICAL engines/market_structure/ engine over a run's candles → BOS/SOS/swing overlays for the chart, in the 4 groups that ARE structure_engine.pine's 4 toggles (External / Internal / Historic Internal Structure / Swing Point Labels), nesting like the Pine's via each overlay's `requires` list (swing tags need their owning structure; historic internal needs Internal). Never a 2nd engine (bare-name import like regime/news); called by chart_spec on the displayed TF. Break tags anchor at the line MIDPOINT (`_mid`, = Pine's `mid_x`) so they clear the break-bar candles; reversal breaks are labelled SOS/iSOS (not "CHoCH")
│   ├── news_filter.py     post-run news/holiday tagging — composes the canonical engines/news/ engine (never a 2nd impl) to mark which of a run's trades opened in a high-impact news window / on a bank holiday, for the BacktestDetail News filter card. Pure over a trade list; loads the EventStore cache (see "News filter (post-run)")
│   ├── history_limits.py  broker history floors — thin shim over the canonical `backtest/data/history.py`
│   │                      (declares NO dates itself). `limits_for()` → the MEASURED earliest backtestable
│   │                      date for an (instrument, timeframe, runner); `validate_window()` raises ValueError
│   │                      which routers turn into a 400. PYTHON RUNNER ONLY — NT8/MT5 read history from their
│   │                      own terminals, so a Vantage floor must never be imposed on them (see "History floors")
│   ├── calendar_service.py  live News Calendar tab — calls engines/news/ TradingViewSource.fetch_window() (never a 2nd impl), 60s in-memory cache keyed on (from,to,countries), computes beat/miss "surprise" server-side via _LOWER_IS_BETTER. Read-only: does NOT touch the shared EventStore cache. Returns the whole week; the frontend filters client-side (see "Live calendar tab")
│   ├── agent_supervisor.py  keeps the SSH tunnel + both VPS agents up — one 60s loop, identical on
│   │                      every pass, so a cold start and a wake-from-sleep are the same code path.
│   │                      Owns `restart_tunnel()` / `schtasks_run()` (moved out of routers/system.py,
│   │                      where main.py was reaching across to call one). Probes the TUNNEL by port
│   │                      binding and the AGENTS by HTTP, because `ssh -L` binds the local port
│   │                      itself — see "The agent supervisor" below
│   ├── readiness.py       boot-time report of the dependencies that fail SILENTLY (news calendar
│   │                      cache, Telegram credentials). Reports, never acts; `GET /system/readiness`
│   ├── runner_dispatch.py      typed HTTP wrapper over NT8 nt8_agent; runner dispatcher (routes mt5 → mt5_agent_client)
│   ├── mt5_agent_client.py  typed HTTP wrapper over MT5 agent (port 8766 via SSH tunnel). `health()`
│   │                      is the AGENT; `status()` is the TERMINAL (mt5_connected/account/server) —
│   │                      two different questions, and only the second says a run can fetch bars
│   ├── python_runner.py     local Python runner — runs strategies/python/ packages in-process via the top-level backtest/ package (backtests + A4 optimizer sweep). No VPS, no agent. Resolves strategies by `strategy_class` (the class `__name__` the scanner stored) — NEVER by package id
│   └── notify.py            Telegram notifier (urllib, no extra deps). Holds NO token: it reads env vars, else the git-ignored `algos/credentials.json`, by PATH (`cfg.MONOREPO_ROOT / "algos" / "credentials.json"`) — the same file `algos/shared/credentials.py` reads, without importing across the app boundary, which the subsystem-independence rule forbids. `routers/bots.py` delegates here; it must never grow its own sender again. `telegram_configured()` answers whether a send would go anywhere
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
- Introduce an ORM or new framework without raising it first
- Write `progress.json` non-atomically — always write `.tmp` then `os.replace`
- Treat a `/health` response as a statement about the thing BEHIND the agent. The MT5 agent answers
  `ok` while its terminal is disconnected, and `schtasks /run` answers SUCCESS for a task Windows
  refuses to launch. Probe the thing you are actually claiming, and re-probe after any action
- Let the agent supervisor run in a test process. `CC_DISABLE_SUPERVISOR=1` is set at module scope
  in `tests/conftest.py`; a fixture is too late, because `main` is imported at collection. Without it
  a plain `pytest tests/` restarts the SSH tunnel and fires two scheduled tasks on the live VPS
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
| `personal` | Personal trading accounts | Real PASS/DISCARD verdict against the relaxed personal rules (`_evaluate_personal`): DISCARD on `max_consecutive_loss_days` consecutive days whose loss hit `daily_loss_cap`, or on EOD equity dropping `max_drawdown_from_peak_pct` from its running peak; otherwise PASS. **`INFO` when the ruleset configures NEITHER condition** — see *Nothing checked is not a pass* below. `daily_profit_target` is an informational halt note, never a fail. No trailing MLL (max_loss_eod = 0 sentinel), no profit-target requirement, no consistency rule, no reference line. |
| `demo` | Paper/demo accounts | Same as `personal`. |

**Nothing checked is not a pass (fixed 2026-07-31).** `_evaluate_personal` ended
`verdict = "DISCARD" if failures else "PASS"`, and both of its checks are guarded — check 1 needs
`daily_loss_cap` AND `max_consecutive_loss_days`, check 2 needs `account_size` AND
`max_drawdown_from_peak_pct`. On `unconstrained`, which states neither by design, both were skipped
and `failures` was empty *by construction*: **a run that lost 95% of the account returned PASS.**
Zero failures out of zero checks is the absence of a verdict, not a passing one, and it contradicted
the rule `lab_db.py`'s own seed note states on that row ("a run against it cannot be graded… there is
no honest default to substitute"). It now returns `INFO`, which the frontend already renders
neutrally as **Not graded** with no rule chips. Two things to keep in mind if you touch it: the
"was anything checked" test must **mirror the two guards exactly** (testing the caps alone called a
run graded when a missing `streak_limit` had silently skipped check 1), and because verdicts are
**stored**, the source fix alone leaves history wrong — `init_db` carries an idempotent migration
rewriting stored `PASS` rows on limit-less personal/demo rulesets to `INFO` (every evaluation row in
the live DB was exactly this case). Guard on `!= 0` as well as `IS NOT NULL`: `daily_loss_cap` is
`0`, not null, on both no-limit rows.

For prop types the verdict reads `max_loss_eod` (the trailing-MLL amount) and `mll_lock_balance` for drawdown; it never reads `daily_loss_cap` (a soft/informational field for firms like Apex). For personal/demo types `daily_loss_cap` IS a rule input (the capped-day trigger) and `max_loss_eod` is never read (0 sentinel = no trailing EOD rule). `metrics.effective_dd_limit_usd()` is the one place that turns a ruleset into a dollar MC/objective drawdown limit — personal/demo rows translate to `account_size × max_drawdown_from_peak_pct`. The stress-test primary pick excludes personal/demo rows from its strictest-ruleset comparison; worthiness prefers prop rows but falls back to the strictest personal/demo limit when a run was evaluated against personal/demo only (forex).

`account_tier` is still present on rows (eval/funded/live) — useful for prop rulesets. `ruleset_type` is the broader category.

Columns on `rulesets`: `ruleset_type`, `daily_loss_cap`, `weekly_loss_cap`, `daily_profit_goal`, `description`.

Seeded rulesets (18 rows): 4 prop firms = 14 prop rows — LucidFlex, FundedNext, Tradeify each at 50k/100k × eval/funded (12 rows), plus Apex EOD eval-only at 50k/100k (2 rows; funded/PA not yet seeded) — plus 2 personal demo rows (`personal_forex_demo`, `personal_futures_demo`; ruleset_type `personal`, account_tier `demo`), `unconstrained`, and `personal_forex_risk`. Personal demo rules on a $10k balance: $500 daily loss cap, $1,000 daily profit target, fail at 15% drawdown from peak (`max_drawdown_from_peak_pct`) or 3 consecutive capped-loss days (`max_consecutive_loss_days`) — stored now, enforced in a later evaluator pass. `max_loss_eod = 0` is the sentinel for "no trailing EOD rule" on personal rows (the column is NOT NULL); the evaluator must treat it as rule-absent. All seeded via the per-id idempotent pattern (`_PROP_SEED_ROWS` + `_seed_apex_eod_eval`). The core KPIs of all 14 prop rows (account size, target, drawdown type/amount/lock, consistency, min trading days, contract scaling, funded split, doc links) are documented for hand-off in `command-center/docs/PROP_RULESET_KPIS.md`, which also carries the firm doc links, the saved sync query (`scripts/prop_kpi_audit.py`), and a verification prompt; re-run that prompt to re-check the firms and keep the doc in sync with the DB. Display names: the firm name lives in the UI group header only; `name` carries the program/challenge ("LucidFlex $50k Evaluation", "Select $50k Evaluation", "Futures Flex $50k Challenge", "EOD $50k Evaluation") — canonical map in `_RULESET_DISPLAY_NAMES`, re-applied on every `init_db`. The firm behind the `lucidflex_*` ids is Lucid (Lucid Trading); LucidFlex is its program name.

**The two forex rows are a PAIR, and the difference is the whole point (2026-07-30).** `unconstrained` states no limit, which makes it the honest raw-behaviour view AND ungradeable — every grade in `services/grading.py` is a statement about drawdown vs a limit, and there is no defensible default to substitute (see the ruin walk-back in `grading.compute_grade`). `personal_forex_risk` ("Personal Forex — 55% Drawdown") is the same row with the one bar stated, so the same run returns a letter. 55% is **Aaron's stated tolerance**, picked against his own measured numbers on the A+ SOS Fade run: worst-5% of simulations draws down 53.2%, worst-1% draws down 62.1% — so 55% accepts the 5% tail and explicitly does not accept the 1% tail. Every other limit on it is deliberately absent (no daily cap, no loss-streak rule, no profit target), because at 10–12.5% risk per trade a daily cap fires constantly and the verdict stops being about drawdown.

⚠ **The 15% on `personal_forex_demo` is a PROP-FIRM figure and must never be applied to forex** (Aaron, 2026-07-29). Grading a forex run against it produces a D that says nothing about the strategy. Pinned by `tests/test_rulesets.py::test_the_forex_risk_row_does_not_inherit_the_prop_15_percent`.

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

**Canonical Sharpe — one definition everywhere.** `metrics.apply_canonical_sharpe(kpis, daily_pnl)` writes the daily-√252 Sharpe into `sharpe`, moves the platform's value to `platform_sharpe`, and sets `sharpe_low_sample`. It's called at every run-completion path that has `daily_pnl` — single run, sweep child, stress child, optimizer winner — but NOT the native-combo path (no daily_pnl). **Idempotency guard:** only runs when `platform_sharpe` is null, so a second pass can't overwrite the platform value. Walk-forward window Sharpe (`stress_tester._compute_sharpe`) goes through the dated `daily_sharpe`.

**Flat days are zero-filled before the Sharpe (2026-07-16).** `daily_pnl` carries only days that closed a trade (the trailing-drawdown engine walks the days that exist), so Sharpe used to average the ACTIVE days and annualize by √252 — scoring a strategy that's flat 90% of the time as if every day earned the active-day mean. A real 22-trade/225-day run read **7.80 against a true ~2.2**; TradingView's own Sharpe on the same trades, annualized, independently agreed at ~2.0 (see `metrics.zero_filled_daily_values`). `daily_sharpe(daily_pnl)` now zero-fills every weekday in the span first — dates PRESENT are always kept, even on a weekend, so a Sunday-open forex fill isn't dropped. **Do NOT change `daily_pnl` itself** — the trailing-drawdown engine depends on flat days being absent; the zero-filled series exists only for Sharpe.

Two traps this creates, both guarded:
- **`sharpe_low_sample` must count ACTIVE days** (`metrics.active_day_count`), never `len()` of the zero-filled series — otherwise a 3-trade year reads as ~250 well-sampled days and the flag never fires, exactly where it's needed most.
- **`daily_sharpe_from_values` (undated) does NOT zero-fill and must stay that way** for callers whose day population is sparse *by definition* — the optimizer's regime-filtered scoring, where the days in between are other regimes, not flat days of this one.

**Backfill (`scripts/backfill_metrics.py`) recomputes `sharpe`/`sharpe_low_sample` on EVERY pass** (pure functions of the stored `daily_pnl` → idempotent), which is how a change to the canonical definition reaches history; only the one-way `sharpe`→`platform_sharpe` move stays null-guarded. **The move skips `runner = 'python'`**: `backtest/output.py` deliberately computes no Sharpe, so a python run's `sharpe` is already ours, and moving it would stamp our own value as "the platform's" and invent a reference that never existed — NULL is the honest answer.

**Contract cap** (`evaluator.compute_contract_cap_status`, informational — never moves the verdict): scaling ladder → `not_applicable`; MT5 (lots) → `not_applicable`; NT8 without per-trade size → `not_evaluable`; NT8 fixed cap + size → real largest-single-trade vs cap. Per-trade `size` is captured from NT8's Quantity column / MT5 volume.

**Profit concentration** persisted as `profit_concentration_pct` (largest quarter's share of gross profit) for later grading use, alongside `profit_concentration_basis` — `'return'` or `'dollars'` — which says how it was weighted, so a row is self-describing.

**It is weighted in RETURNS whenever the run COMPOUNDED (fixed 2026-07-31), and this was a real false alarm, not a refinement.** In dollars the metric reports the compounding rather than the clustering it exists to detect: on an account that grows 85x, the final quarter must hold nearly all the dollars however evenly the edge is spread. Measured on run `d2ab68f9e884` — dollar quarters of $9k / $49k / $71k / $1,039k read **88.94%**, which is past the 60% "edge clustered — overfit risk" threshold and was the only warning colour on that page; the same trades weighted by each one's return on the equity it was taken with read **39.97%** ("spread across the test"). The switch is whether the equity curve carries a real account base (`_equity_base > 0`): a %-of-equity strategy compounds and must be normalized, while an NT8-shaped cum-P&L-from-zero curve is a unit-size run whose dollars ARE already comparable across periods — dividing those by a fictitious balance would introduce the opposite bias. **`profit_concentration_pct` therefore needs the EQUITY CURVE, not just `daily_pnl`**; every caller passes it (`backtest_runner._handle_complete`, `scripts/backfill_metrics.py`).

Because the figure is stored, `init_db` carries a one-time `_restamp_profit_concentration` that re-reads each completed run's `equity_curve.json` and rewrites it; `profit_concentration_basis IS NULL` is the marker that makes it run exactly once. A run whose file is missing is stamped `'dollars'` — that IS what its stored number is, and leaving it NULL would re-read a missing file on every startup forever. It restamped all 78 completed runs in the live DB. The frontend recomputes client-side rather than reading the column (`frontend/CLAUDE.md` → *Profit concentration measures the edge*), so a page never depends on this migration having run.

### The Python runner's costs were collected and never charged (fixed 2026-08-01)

`commission_per_side` and `slippage_ticks` are collected in the Run modal, stored on
`backtest_runs`, shown on the run page — and `services/python_runner.py` read neither. Every
Python run was **frictionless** while reporting a cost profile it had not applied. The tell in the
data was 52 of one run's 54 losing trades each losing **exactly 10.00%** of prior equity, which no
cost model can produce; the values themselves (2.25/1) came from a FUTURES prop-firm ruleset and
were never meaningful for spot gold.

`python_runner._cost_profile(spec)` is the seam: it turns the run's stated costs into a
`backtest.fills.AccountProfile`, passed to both the single-run path and `run_sweep` (so the
optimizer cannot rank combos on a frictionless book and then hand the winner to a run that is
not). Four rules, each of which fails silently if broken:

- **0/0 returns `None`, not a zero-valued profile.** No profile means no charge path is entered at
  all, which is what keeps every result measured before this date reproducible.
- **Either number alone builds one.** An `and` there would drop slippage-only runs back to
  frictionless — the same bug, one level down.
- **Commission is per LOT per side** (a lot = `contract_size` units, 100 oz for gold). Reading the
  field as per-unit overcharges gold 100x and nothing downstream looks wrong.
- ~~**`swap=None` deliberately.**~~ **Superseded 2026-08-02 — see below.**

#### Layered costs — and the two numbers that were never typed in (2026-08-02)

Aaron's framing, and it is the right one: the spread and the swap are things we KNOW, so leaving
them unpriced is a choice nobody made. Both are now chargeable in bar mode, and the request carries
**`cost_layers`** (which costs to charge) + **`broker_profile`** (whose measured facts to charge
them from) — `python_runner.COST_LAYERS` is the roster, `backtest.fills.PROFILES` the source.

**Every layer is OFF by default, and that is Aaron's explicit call.** A bare run charges nothing,
so it stays directly comparable to the TradingView Strategy Tester, and each cost is switched on
deliberately. **Slippage keeps its own switch and its own typed number** for the opposite reason
to the rest: it is the one cost no amount of history can measure, so it must never ride along with
the measured ones.

Four rules, each of which fails silently if broken:

- **`cost_layers` absent (`None`) is NOT `[]`.** `None` = a row written before layers existed and
  must keep the old contract (charge whatever commission/slippage it stated); `[]` = charge
  nothing. Collapsing them would re-price all 80 stored runs the first time one was retried.
  `routers/backtests._json_list` preserves the distinction on the way out, and the API models it
  as `Optional[list[str]]` so the page can caption which it is.
- **`spread` and `swap` are never accepted from the request.** They are measurements, and a field
  the operator can type is a field that can disagree with the broker. Picking `puprime_standard`
  over the default `vantage_demo` moves the spread 0.22 → 0.33 because those are two different
  measurements — **the $0.33 this repo had recorded is PU Prime's, and using it for a Vantage
  backtest overstated the cost by 50%.**
- **`bid_ask_fills` REPLACES the spread cost, never adds to it** (see the strategy's
  `_charge_spread`), and it is the only layer that can change which trades exist.
- **`GET /backtests/broker-profiles` exists so the Run modal never retypes a spread.** It serves
  `PROFILES` itself — the object the runner bills from. A number copied into a form is a second
  claim about what is charged, which is this lab's most-repeated defect.

Both `_cost_profile` call sites (single run and the optimizer sweep) inherit it, so the optimizer
cannot rank combos on one cost model and hand the winner to a run on another. ⚠ **Sweeps and stacks
do NOT write the columns yet**, so they land in the legacy branch and stay frictionless — correct
today (that is also the default), but wire them before anyone expects a priced stack.

Strategies are constructed through **`backtest.replay.build_strategy`**, never by calling the
class: `LAB_STRATEGY` is an open contract, so a strategy may predate the `cost_profile` kwarg, and
that helper **raises** rather than dropping a stated cost on the floor. Defaults on every request
model are now **0/0** (`models.py`), and `RunBacktestModal` resolves its primary ruleset across
BOTH the futures and forex lists — searching futures only is why a forex run's 0/0 ruleset default
never reached the form.

### Three numbers that were true and got misread

Auditing run `f866873aa862` found **no arithmetic wrong anywhere** — every stored KPI reproduced
from the raw trades, Sharpe included. What was wrong was what three headline numbers let a reader
conclude, and none was fixable by relabelling; each needed a companion that had never been
computed. All three live in `services/metrics.py`, are stored on `backtest_runs`, and are
backfilled onto history by `lab_db._backfill_run_shape_metrics`.

| stored | what it fixes |
|---|---|
| `max_drawdown_pct` | the drawdown was stored and LISTED in dollars only. $1.73M beside $14.4M of profit reads as ~12%; against the running peak it is **55.9%**. `BacktestDetail` always computed the percentage client-side — the RUNS LIST, which is where runs get compared, did not, and a list is exactly where a wrong order of magnitude does its damage. |
| `scratch_count` | the win rate counts a trade that made a cent as a win. 45 of that run's 111 "winners" made under a sixth of a typical loss, every one exiting at the breakeven-stop buffer — the stop doing its job, which is risk control and not an edge. Honest split: 40% won / 27% scratched / 33% lost. |
| `trade_concentration_pct` | `profit_concentration_pct` is the largest QUARTER's share — a question about time. Readers hear the question about TRADES, and the two can disagree completely: that run is 34.5% by quarter (spread evenly over 6.6 years) while **5 of 165 trades made 47%** of everything won. |

Three rules they share, and each is load-bearing:

- **All three weight by RETURN when the run compounded** (`_trade_weights`, the same
  `_equity_base` switch `profit_concentration_pct` uses). Dollars on a compounding account measure
  the compounding.
- **The scratch yardstick is the run's own MEDIAN full loss**, not a typed-in figure. For a
  fixed-risk strategy that median IS 1R, so the bar self-scales across strategies, instruments and
  account sizes with nothing to tune; the median rather than the mean so one outsized loss cannot
  move it. (It landed on the same 0.15 that `mpc_strategy.pine`'s own `exec_scratch_r` uses — not
  a coincidence, since 0.15 of the median loss and 0.15R are the same bar at fixed risk.)
- **`None` is never rounded to 0.** No losing trade means no scale to measure a scratch against,
  and `0` would read as "no scratches" — the opposite of "cannot tell". The backfill stamps
  `max_drawdown_pct = -1.0` for a run whose curve is missing, for the same reason
  `_restamp_profit_concentration` stamps `'dollars'`: a row left NULL is re-read on every startup
  forever.

**A high `trade_concentration_pct` is not a verdict.** A runner-based strategy is supposed to be
fat-tailed and this repo's stated design intent is few high-quality setups, so read it as "the
edge lives in the tail, size the risk for that" rather than as a defect. The frontend recomputes
both trade-shape metrics client-side (same rule as profit concentration — the stored value is
whatever basis was current when a run finished, and the news filter needs them over a subset).

**Backfill:** `scripts/backfill_metrics.py` recomputes the file-derivable columns (Sharpe trio, profit concentration + basis, contract status) on old runs — idempotent, only touches what's derivable from stored result files.

**Capital-based scores stay client-side** (BacktestDetail). Calmar / Max-DD-% need an account balance (the ruleset's `account_size` or the what-if slider); they're computed in the browser by rebasing the equity, never persisted, and never feed the verdict. **Both are measured against the RUNNING PEAK, not the starting balance (2026-07-30)** — the same defect `dd_basis` fixed for Monte Carlo, found in a second file: dividing a late dollar drawdown by a static `account_size` reported **1096.7%** and a red **Calmar 0.11** on a run whose honest figures are 54.9% and 2.25. If you add another percent-of-capital metric anywhere, the denominator has to grow with the account. Detail: `frontend/CLAUDE.md` → *Drawdown is peak-relative*.

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
| Strategies | ✅ Live | Registry scanned from `strategies/`. Param schema from `[NinjaScriptProperty]`. `runner` field per strategy. `run_count` (shown in the Strategies-tab Runs column) joins `backtest_runs` with `r.stress_test_id IS NULL` — same "real run" filter as `list_runs`, so hidden stress-test child runs don't inflate the count. **Strategy-level narrative** (`edge` TEXT, `steps` JSON) is overlaid from the companion `<Strategy>.meta.json` **top-level** `edge`/`steps` keys by `strategy_scanner._read_strategy_overview` and stored on `strategies`; drives the StrategyDetail Overview. UI-only (no source-hash impact). NULL-safe: a backfill migration sets `steps='[]'` and `Strategy.steps` has a `mode="before"` validator coercing `None→[]` (a NULL would otherwise fail the `list[dict]` response validation on `GET /strategies`). `.mq5` re-scans on meta mtime change; `.cs` only on source change. **`needs_scan`** (2026-07-23) — the scan-time twin of `needs_deploy`/`needs_compile`: `strategy_scanner.needs_rescan(row)` recomputes the on-disk source hash (Python = whole-package `_python_source_hash`; `.cs`/`.mq5` = file md5) + meta mtime and returns True when either diverged from what the DB last scanned, i.e. the param schema the Run modal shows is stale. Computed LIVE and enriched onto every row in `routers/strategies.list_strategies`/`get_strategy` (NOT stored — a circular import if `lab_db` computed it, and it must reflect disk right now). This is what surfaces the "Needs scan" pill so a Python strategy (which has no deploy/compile step) still tells the user to re-scan after a `config.py`/meta edit — the gap that let a run fire on the old divergence-armed defaults. |
| Rulesets | ✅ Live | CRUD at `/rulesets`. 4 types: `prop_eval`, `prop_funded`, `personal`, `demo`. 18 seeded rows (14 prop + 2 personal demo + `unconstrained` + `personal_forex_risk`). Prop rows locked server-side (PATCH/PUT 403); `PATCH` edits the 5 personal rule fields only (`PersonalRulesetPatch` extra=forbid + SQL allowlist). |
| Backtests | ✅ Live | NT8/MT5 runs via agent. Equity curve, daily P&L, per-ruleset verdicts, Worthiness tier (1/2/3). |
| Sweeps | ✅ Live | N sequential backtests across instruments (`_MAX_CONCURRENT = 1`). Cancel, retry-all, per-run retry. |
| Optimizations | ✅ Live | Native NT8/MT5 optimizer (one VPS job, full grid, all CPU cores). Scores by objective. `best_run_id` tracked. Source run nesting. Per-run retry. |
| System | ✅ Live | Health (SSH, NT8, MT5 agents). Log proxies. `POST /system/{nt8,mt5}-agent/start` fires schtasks. |
| Stress Tests | ✅ Live | MC (10k reshuffles + 1k bootstrap), walk-forward (IS/OOS NT8 windows), sensitivity (±10%/±25%). A–F grade. |
| Regime Tags | ✅ Live | `backtest_runner.build_regime_timeline_and_tag()` classifies **every trading day in the run's window** once (via the existing `build_date_regime_map`), writes it to `reports/lab/<run_id>/regime_timeline.json` → `BacktestDetail.regime_timeline` `[{date, regime}]`, and tags `daily_pnl` from that same map (a P&L day with no bar carries the last classified day). Regime is a property of the MARKET on a date, not of a run — tagging only traded days left the equity charts banding off a sparse calendar, so two runs over the same window disagreed about the regime. Cheaper too: one classification per day, reused. Old runs: `scripts/backfill_regime_timeline.py` (opt-in — it fetches OHLC, so it's not in `backfill_metrics.py`). Optimizer `regime_filter` unchanged. |
| Strategy Files | ✅ Live | Upload/delete/compile `.cs` (NT8 F5) and `.mq5` (MetaEditor) files. Sync-status badges. |
| Strategy Deploy | ✅ Live | `POST /strategies/{id}/deploy` reads `source_path`, uploads to VPS. `.mq5` → MT5 agent, `.cs` → NT8 agent. |
| Param types | ✅ Live | `GET /strategies/{id}/param-types` parses `.cs`/`.mq5` source → `{paramName: "int"\|"double"}`. Used by optimizer modal to block decimal steps on integer params. |
| MT5 runner | ✅ Live | `mt5_agent.py` port 8766: Strategy Tester driver (ini+set, terminal64, HTML report). `mt5_agent_client.py` typed wrapper. Runner dispatch via `runner_dispatch`. `/historical_data` maps M5/M15/M30 (was M1/H1/H4/D1 only), `symbol_select()`s before reading bars, **preserves symbol case** and tries the symbol **as given then its root** (terminals vary — GBPJPY is only `GBPJPY.s`, USDJPY both ways). `ohlc_fetcher._resolve_mt5_symbol` passes the run's broker symbol through; `chart_spec._capped_start` caps candle volume by trimming the WINDOW, never the timeframe. |
| MT5 deployment | ✅ Live | MT5 agent upload/delete `.mq5`. `POST /compile` → MetaEditor. Backend: `POST/GET /strategy-files/compile-mt5`. |
| MT5 native optimizer | ✅ Live | `mt5_agent.py` `POST /native-optimize` + `POST /native-walkforward`; `mt5_agent_client.py` typed wrappers. `runner_dispatch` dispatcher + `optimization_runner.run_native_optimization` route by `runner`. Native single-job `Optimization=1` run — MQL5 frame callbacks (`OnTesterInit/OnTester/OnTesterPass/OnTesterDeinit`) collect per-combo KPIs into `opt_results.csv`; the tester distributes combos across its local agents. **The EA MUST implement those callbacks** — without them the optimizer runs every pass but harvests nothing (single backtests work, optimization yields an empty CSV → "OnTesterPass may not have fired"). CSV columns must match `_parse_opt_csv` / `_OPT_KPI_COLS` (net_pnl/profit_factor/max_drawdown/trade_count/win_trades/sharpe[/gross_profit/gross_loss]) and the param column names must equal the grid keys. Combos rank on MT5's platform Sharpe (the native path has no `daily_pnl`, so canonical Sharpe isn't computed) — re-validate a winner with a single full backtest. |
| Python runner + optimizer | ✅ Live | `services/python_runner.py` — runs `strategies/python/` packages LOCALLY, in-process, via the top-level `backtest/` package (data cache → engine replay → `output.build_results`). No VPS, no agent, no compile. Scanner registers packages declaring `LAB_STRATEGY` (`strategy_scanner._parse_python_package`); the runner resolves by `strategy_class` = the strategy class's `__name__` — the same job-spec key NT8/MT5 use, locked by `test_python_runner.py`'s scanner↔runner agreement test. Optimizer: `runner_dispatch.start_native_optimization(spec, "python")` → `backtest/optimizer.run_sweep` fans combos across cores (lab still owns grid expansion + ranking — `expand_grid`, `objectives.py`). Sweeps run in bar mode; validate the winner in tick mode. Third lock scope: `has_running_python_job()`, surfaced through `get_running_job()`'s `python` bucket and consumed by the frontend's `lib/runner.ts` (wired 2026-07-16). Price charts AND regime tagging both read `ohlc_fetcher.get_ohlc(runner="python")` → `backtest.data.BarSource`, the SAME disk cache the run replayed, and deliberately never fall back to another feed: yfinance maps XAUUSD.s → GC=F, so a fallback would chart/label a spot-gold run off Yahoo's gold FUTURES daily bars. **Feature parity with the native runners is otherwise inherited, not re-implemented** — `run_backtest_job`/`_handle_complete` are runner-agnostic, so sizing (via `engine_trades`, which `backtest/output.py` emits), evaluations, worthiness, canonical Sharpe, regime tagging, the news/holiday filter (needs `entry_ms`, which the Python output carries) and stress tests all work unchanged. |
| Portfolio stacks | ✅ Live | `routers/stacks.py` + `services/lab_db.py` — layer 2+ **Python** strategies over ONE shared instrument/timeframe/window/cost profile to see combined P&L (summed client-side from each leg's `daily_pnl`; toggling a leg off never re-runs). **Smart reuse** (2026-07-25): on create, each leg that already has a COMPLETED standalone run at the EXACT same settings is reused as-is; only legs with no match are backtested fresh. `POST /backtests/stacks/preview` reports reuse-vs-run per leg without running anything (drives the modal's badges). See "Portfolio stacks (smart reuse)" below. |
| Telegram notifications | ✅ Live | `services/notify.py` — urllib Telegram sender, no extra deps. **No token in the source (2026-07-30):** env var, else the git-ignored `algos/credentials.json` read by path. `stress_tester` fires after grade is written. |
| Live calendar tab | ✅ Live | `routers/calendar.py` (`GET /calendar?from&to`) → `services/calendar_service.py` → `engines/news/` `TradingViewSource.fetch_window()` (never a 2nd impl). Returns the whole week's events unfiltered + `server_now_ms` (drives the frontend "now" line off the server clock); 60s in-memory cache; beat/miss `surprise` computed server-side (`_LOWER_IS_BETTER`). Read-only — does NOT write the shared EventStore cache (separate path from the post-run news filter). Feed only, no DB. |
| History floors | ✅ Live | `services/history_limits.py` + `GET /backtests/history-limit`. Refuses (400) any backtest window starting before the broker's REAL history for that timeframe — MT5 silently substitutes coarser bars, which would produce a plausible but fictional run. Floor is MEASURED off the live terminal (probed by bar density, cached per broker) via the canonical `backtest/data/history.py`, so a broker swap re-measures instead of inheriting. Enforced at run / retry / sweep / optimization / stack, and again in `BarSource.load`. Python runner only. |
| Settings | ✅ Live | Config read/write. `nt8_agent_tunnel` and `mt5_agent_tunnel` both present. |
| Startup — agent supervisor | ✅ Live | `services/agent_supervisor.py` — 60s loop, guarded on the per-platform job lock. Replaces the one-shot startup thread. See *The agent supervisor* below. |
| Startup — readiness report | ✅ Live | `services/readiness.py` — one boot-time line per silently-degrading dependency; `GET /system/readiness`. |

---

## The agent supervisor — and the two indicators that were lying

**Added 2026-08-02. `services/agent_supervisor.py`.** Replaces `main._auto_start_agents`, a one-shot
thread that ran 8 seconds after boot and never again: it worked on a cold start and did nothing for
every case after it, which is why the MT5 agent had to be started by hand after every laptop sleep.
There is no separate startup path now — the first pass is the same pass as every later one, so
"it works on launch" and "it recovers from sleep" cannot diverge.

**Two probes, because `ssh -L` binds the local port ITSELF.** A TCP connect to 127.0.0.1:8766
succeeds for as long as the ssh process holds the forward, whether or not anything is alive at the
far end. That gives two independent signals, and the pair is what tells the failures apart:

| ports bound | agents answering | diagnosis | action |
|---|---|---|---|
| neither | — | the tunnel is dead (laptop slept) | rebuild it |
| both | **neither** | stale tunnel forwarding into nothing, **or** both agents really down | rebuild, then fire both tasks |
| both | one | the tunnel is fine | fire that agent's task only |

🔴 **The old health check answered neither question.** `_check_ssh` ran `ssh forexvps "echo ok"` — a
BRAND NEW connection that has nothing to do with the forwards — and that is what the sidebar's "SSH"
dot reported. So after a sleep the dot sat green beside two red agent dots, which sends you to the
VPS when the problem is on the laptop. `SystemHealth.ssh_tunnel` now measures the forwards;
`vps_reachable` is a new field carrying the old question, and it is what separates a dead tunnel
from a dead network. (The agent-start endpoints already rebuilt the tunnel before firing a schtask —
the workaround was in the code, the indicator just could not say so.)

🔴 **`/health` on the MT5 agent is not a statement about MT5.** It returns `ok` if Flask is alive,
which it is whether or not the terminal is running or logged in — so an MT5_Lab that had dropped its
broker connection showed a green dot and every python run needing uncached bars failed at fetch time
instead. `mt5_agent_client.status()` wraps the agent's `/status` and health now carries
`mt5_connected` / `mt5_server` / `mt5_account`. **`mt5_connected` is `Optional[bool]` and `None`
means the agent could not be asked** — an unanswered question is not a disconnected terminal, and
rendering it as one invents a measurement. The terminal is not probed at all when the agent is down.

**The guard is the point, not the loop.** Every action is skipped when the scope it would disturb
has a job running (`lab_db.get_running_job`), and a **python run counts as MT5 traffic** — the local
runner pulls its bars through port 8766 (`backtest/data/mt5_agent.py`), so restarting the tunnel
mid-fetch kills a run that never touched the VPS directly. `busy_scopes()` returns **all three
scopes** when the DB cannot be read: doing nothing is always safe, and the wrong guess in the other
direction kills a live run.

**One deliberate asymmetry, and it is not an oversight.** An **unbound** port is rebuilt even under a
running job — nothing can connect, so every call that job makes is already failing and rebuilding is
its only route back. A merely **stale** tunnel (ports bound, agents silent) is not, because that
reading has a real false positive: an agent driving a heavy backtest stops answering `/health` while
working perfectly. The NT8 agent does exactly this under pywinauto.

**`schtasks /run` is not evidence.** It reports SUCCESS for a task Windows refuses to launch (see
`algos/CLAUDE.md` → the stored-password trap), so every fire is followed by a re-probe and the
outcome is logged either way — `nt8-started` or `nt8-fired-but-still-down`. Silence after a fire
used to read as success.

⚠ **It will not rescue an agent whose death left a job marked `running`.** "Dead" and "busy driving
my job and too loaded to answer" are indistinguishable from here, and the wrong guess kills a live
run — so the skip NAMES the deadlock (`nt8-DOWN-with-a-job-running (lock held by nt8 — Stop it or
restart the backend)`) rather than retrying silently forever. Observed live on 2026-08-02: the NT8
agent died on a backtest submission, the run row stayed `running`, and the loop correctly refused to
touch it. Clear the lock and the next pass restarts the agent by itself.

⚠ **The supervisor is DISABLED under pytest** — `CC_DISABLE_SUPERVISOR=1`, set at module scope in
`tests/conftest.py` (a fixture runs too late; `main` is imported at collection). Every endpoint test
builds a `TestClient`, which fires the startup hook, so without the guard a plain `pytest tests/` on
a laptop whose tunnel happened to be down would rebuild the tunnel and fire two scheduled tasks on
the live VPS. Same class of hazard as `tests/test_integration.py`, and refused by default for the
same reason.

**Tests:** `tests/test_agent_supervisor.py` (19) + `tests/test_system_health.py` (12). Most of them
are about what the supervisor REFUSES to do — the dangerous failure of a supervisor is not a missed
repair, it is a repair at the wrong moment.

## Readiness — the checks whose failure mode is silence

`services/readiness.py`, reported once at boot and served at `GET /system/readiness`. The supervisor
above watches things that announce themselves; this covers the opposite class — dependencies whose
absence produces no error anywhere, just a feature that quietly does nothing:

- **An un-backfilled news calendar makes the News & Holiday filter INERT.** The engine reports
  `has_coverage=False` outside the fetched range and tags nothing, so a correctly-wired filter over
  an unbackfilled period is indistinguishable from a broken one. The cache is git-ignored, so a
  fresh clone starts empty and every machine backfills its own. A cache that STOPS partway is the
  nastier case and is reported with the date it ends — recent trades come back *untagged, not
  unaffected*.
- **Missing `algos/credentials.json` makes every Telegram send a no-op.** Deliberate (a notifier
  must never be able to stop a trading loop) and it means a stress-test grade can finish with
  nobody told.

It **reports and does not act** — neither is repairable from here, and neither is worth refusing to
boot over. `_news_calendar()` catches everything: it runs inside the startup hook, and an exception
there would stop the backend booting over a git-ignored cache file.

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
- **`prob_breach`/`prob_pass_eval` are `Optional[float]`, and `None` when the ruleset states no limit.** Not `0.0` (never breaches) and not `1.0` (always does) — there is nothing to breach, which is a third answer. Grading reads them through `_num()`, which falls back ONLY on `None`; the old `value or fallback` was a live bug in both directions, since every metric here can legitimately be `0.0` (a stored `prob_breach = 0.0` was reported to the user as "100% probability of breaching ruleset limit", and a `0.0` drawdown became `inf` and failed every limit check).

**Which SERIES gets shuffled — dollars or returns (2026-07-30).** Reshuffling a dollar P&L list assumes the trades are exchangeable, which is only true at constant position size. A %-risk compounding strategy violates it outright: on run `06f7eece0db1` the median |P&L| per trade drifts **$222 → $3,913 across the run (17.7x)**, so a shuffle was moving late $4k trades to the front of a $10k account and back-loading the small ones — measuring a strategy that never existed. `choose_shuffle_series(trade_pnls, balances)` picks per run: it measures the drift of both the dollar series and the per-trade RETURN series (`pnl / balance_before`, median |value| of the last third over the first third) and switches to returns only when the dollars actually drift (≥ `_DRIFT_TRIGGER` 2.0, ≥ `_DRIFT_MIN_TRADES` 30 trades) AND returns are the more stationary of the two. Same run: dollar drift 17.66x vs return drift 1.42x → returns. Paths then COMPOUND (`start_bal × cumprod(1+r) − start_bal`) instead of `cumsum`. **Fixed-size runs are untouched** — no balance series, or no drift, means dollars exactly as before. This is not a cosmetic change: the same run's worst-1% drawdown went **$41,970 → $359,886**, i.e. the old number understated the tail ~8x.

**Drawdown basis — `dd_basis` (`"percent"` | `"dollars"`).** A compounded run reports drawdown as a percent of the running peak (`median_max_dd_pct` / `pct5_max_dd_pct` / `pct1_max_dd_pct`, alongside the dollar columns, both persisted), because a fixed dollar limit stops being comparable to an account that has grown away from the size the limit was written for. The dollar view of that same run reported a **100% breach of TOTAL RUIN across 20,000 simulations in which the account was never once wiped out** — real ruin 0.00%, real worst-1% drawdown 61%. `prob_breach` is measured on whichever basis the grade will read, so the headline number and the letter can never come off different bases and contradict. Rows written before 2026-07-30 carry no `dd_basis` and keep the dollar path, so their stored grades stay reproducible.

**Walk-forward** — sends real backtests to NT8. Splits the original date range into N equal windows. Each window is split 70% in-sample / 30% out-of-sample — two separate NT8 backtests per window. Measures how much Sharpe drops from in-sample to out-of-sample. Large drop = strategy may be overfit to the training period. **Degradation is only computed over windows with a MEANINGFUL positive IS Sharpe** (the serial/MT5 path) — `1 − OOS/IS` is a meaningless signed ratio when IS Sharpe ≤ 0, and *explodes* when IS Sharpe is a tiny positive (a flat in-sample window with Sharpe ~0.002 once produced a 539,229% per-window value → 134,540% average). So windows below `_WF_IS_SHARPE_FLOOR` (0.1) are excluded as not-assessable, and each surviving window is clamped to `_WF_DEG_CLAMP` (`[-100%, +200%]`) before averaging. If no window qualifies, degradation is stored as `None` → UI shows "n/a (IS Sharpe ≤ 0)" and grading treats it as not-run (neither credit nor penalty). The native NT8 WF path (optimization-derived runs) degrades on **profit factor**, not Sharpe (no per-trade data), so the signed-ratio sign-flip can't occur — but it applies the **same honesty rule**: when no window has IS PF > 0, degradation is stored as `None` (not `0.0` — `0.0` would read as "0% = solid robustness" for a strategy unprofitable in every in-sample window), and grading's not-assessable reason is PF-worded ("IS profit factor ≤ 0"). Both WF paths now treat unassessable degradation identically (`None`); `0.0`-as-solid is gone from both. **Thin windows are excluded too (`_WF_MIN_TRADES_PER_WINDOW = 20`, 2026-07-30):** a Sharpe off 6 out-of-sample trades is noise wearing a decimal point, and averaging it in produced a confident-looking degradation figure with nothing behind it (measured windows on run `06f7eece0db1`: IS/OOS = 15/6, 24/6, 10/6, 16/12, 22/8 — every one thin). `window_data` now carries `is_trades`/`oos_trades` so the filter can see them, and when every window is thin the degradation is `None` with a reason that names the fix ("the windows closed too few trades each to support a Sharpe. Re-run with fewer walk-forward windows") rather than the generic IS-Sharpe wording, which would be a false diagnosis.

**Sensitivity** — re-runs the strategy with each numeric parameter shifted, one VPS backtest per shift. **Only STRATEGY-LOGIC params are perturbed** — foundational params (`category == "foundational"` or the MQL5 `f_` prefix) are excluded via `_is_foundational`, the same split the optimizer tunes; perturbing injected config (often at the `-1` sentinel) is wasteful and meaningless. Booleans are skipped. **Scored on PROFIT FACTOR, not net P&L (2026-07-30, Aaron's call):** `degradation = |child_pf − baseline_pf| / baseline_pf`. Net P&L is not scale-free, so any parameter that moves position SIZE dominates the score by construction — on run `06f7eece0db1` `exec_risk_pct` read **85.8% on profit and 11.8% on profit factor**, and since the field is a max across params it single-handedly set the run's score to 85.8% (true worst on PF: `aplus_window` at 12.6%). That is a sizing knob doing exactly what it is supposed to do, graded as fragility. Excluding the param instead would have been overfitting the engine to one strategy; changing the metric is generic. `pnl_delta` is still recorded per shift (the frontend keeps it as a legacy field), and `degradation` is `None` — never `0.0` — when the baseline PF is missing or non-finite. **A shift that changes nothing is skipped, not run:** integer rounding made 43 of this run's 60 sensitivity backtests reproduce the baseline exactly (a ±10% shift on a param whose value is 1 rounds back to 1), which is ~50 minutes of VPS time measuring the same number. `seen_vals` also dedupes shifts that collide with each other. Both are reported in `skipped` — a silent skip would read as coverage that never happened. Large swings = strategy is fragile to exact parameter values. **MT5 uses 2 shifts (±10%)** to limit queue depth; NT8 uses 4 shifts (±10% and ±25%). `SHIFTS` in `stress_tester.run_sensitivity_task()` is runner-aware. The UI time estimate, the note's backtest count, and the run loop all read from shared helpers (`sensitivity_param_count` = perturbed (non-foundational) count, `sensitivity_shift_count` = 2/4 by runner) so they can't drift — `_estimate_sens_duration_min(n_params, runner)`.

**Auto-trigger** — fires MC only (no NT8) automatically when a Tier 1 backtest completes or an optimizer picks a winner. Manual trigger always runs all three phases (MC + walk-forward + sensitivity); no user checkbox.

**Sample-size gate** (`stress_tester.MIN_TRADES_FOR_STRESS = 100`) — one flat floor: below 100 trades the WHOLE stress test is blocked, not just walk-forward. Rationale: the page's output is the A–F grade, and the grade leans on Monte Carlo TAIL percentiles (A = worst-1% drawdown, B = worst-5%) that small samples can't estimate — so a sub-100 grade is false confidence, the same disease as the 134,540% walk-forward number. `POST /stress-tests/run` returns **422** below 100 and `trigger_auto_stress_test` skips (so Tier 1 runs with 50–99 trades get no auto Monte Carlo either). `BacktestDetail.tsx` mirrors the constant and disables the Stress Test button below 100 with an explicit tooltip — backend is authoritative. Clear the bar with more DATA (longer period, more instruments, smaller timeframe), never by loosening params to inflate the trade count (that just curve-fits).

**Child run isolation** — walk-forward and sensitivity runs are inserted into `backtest_runs` with `stress_test_id` set. `lab_db.list_runs()` always adds `r.stress_test_id IS NULL` to its WHERE clause so they never appear in the Runs tab. They're accessible only from `StressTestDetail`.

**Market lock** — `lab_db.running_stress_test_markets()` queries `stress_tests WHERE status LIKE 'running%'` (covers `running`, `running_wf`, `running_sens`), joins to derive `runner`, returns `{futures, forex, run_ids}`. `POST /stress-tests/run` checks this before inserting; 409 if same market is already running. `GET /stress-tests/running-lock` exposes it for the frontend poll.

**Crash recovery** — `lab_db.reset_stale_stress_tests()` marks any `running%` stress tests as `failed_crashed` and their child runs as `failed_timeout`. Called in `main.py` `startup()` — backend restarts automatically clear stuck tests and release the market lock.

---

## Key architectural decisions

**Optimizer implementation:** All optimizations use `search_method = "native"`. The brute-force batch path still exists in `optimization_runner.py` for retrying the two legacy runs in the DB but is not reachable from the UI for new jobs.

- **`"native"`** — sends ONE `POST /native-optimize` to the VPS agent. `nt8_backtest_runner.run_native_optimize_mode` switches the SA to Optimization mode, sets Start/End/Increment ranges for each Strategy Logic param, fires a single Run that uses all CPU cores, then exports the results grid to CSV. MT5 path uses `mt5_agent.py` with `Optimization=1` ini + set-file ranges + HTML combo parser. The backend creates run rows for every combo after the grid is returned. No per-combo equity curve — auto-trigger stress test is skipped; winner must be stress-tested via a manual single rerun. `estimated_runs` is always the full grid size.

**What the non-swept params are held at — "inherited" has to mean inherited (fixed 2026-08-02).** The optimize modal shows each unswept param at the SOURCE RUN's value and labels it `inherited · not swept`. The grid was built from `strategy.default_params` and never read the run at all, so optimizing from a TUNED run quietly tested a different configuration from the one on screen, with nothing on the page able to say so. Live example: run `096432c2ad20` (MPC B-LEG) carries `exec_tp1_pct = 30` / `exec_tp2_pct = 40` against `config.py` defaults of 0/0 — every combo in a grid launched from it ran 0/0. `optimization_runner.base_params_for(opt, strategy)` is the one seam, used by BOTH the native and brute paths. **It may change a VALUE and never introduce a KEY:** a run can carry leftovers from an older schema, and for MT5 a `fixed_params` dict holding an input the EA does not declare makes the tester treat the set file as mismatched and silently run a single backtest (the set-file purity rule below). Foundational injection still lands last, so ruleset values keep overriding.

**Only the Python runner may be sent a LIST axis (2026-08-02).** `_expand_axis` has always accepted `[val, ...]` beside `{min, max, step}`, which is what lets a dropdown or an on/off be swept across its own closed set — but only `python_runner` expands the grid locally. NT8 and MT5 hand a Start/Step/Increment RANGE to their own tester, so a list of strings has nowhere to land there and the job would optimize nothing while reporting success. `POST /optimizations/run` refuses it with a 400 naming the params (`routers/optimizations.py`); the frontend mirrors the rule by only offering the sweep button on python runs. Both sides are pinned by `tests/test_optimizer_grid.py`.

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
| **`None`** | **ruleset states NO drawdown limit** | — | — |

**"DD ≤ limit" is compared in the unit `dd_basis` names** — percent-vs-percent on a compounded run, dollars-vs-dollars otherwise — and the grade_reasons are written in that same unit (`_fmt`), so a reason never quotes a dollar figure the letter didn't read. `metrics.effective_dd_limit_pct()` is the one place a ruleset becomes a percent limit: personal/demo rows state it outright, prop rows derive it (a $5,000 trailing max loss on a $50,000 account is 10% — nothing new had to be defined).

**A `None` grade is a first-class outcome, not an error** (2026-07-30). The test still completes and the Monte Carlo numbers are still reported; there is simply no letter, because every row of that table is a statement about drawdown vs a limit and `unconstrained` states none. Before this, all three `limit > 0` guards evaluated False and the run fell through to **D — so D was the CEILING for any no-limit ruleset**, which reads as a verdict on the strategy and is not one. The reasons carry the fix ("Set the drawdown percent you are willing to accept on a ruleset and re-run"), and `personal_forex_risk` exists to be that ruleset for forex.

⚠ **Total ruin (100%) was implemented as the default limit for no-limit rulesets, measured, and REMOVED.** It is the one bar needing no opinion, so it looks like the obvious answer. It does not discriminate: a compounding simulation cannot reach a zero balance (every `1+r` is guarded > 0), so the bar is only brushed by a strategy already in total collapse — a 10%-risk run with a **70.4% worst-1% drawdown clears it and would have been graded A**. A threshold almost nothing can fail is not a grade. Do not re-add it; the walk-back is recorded in `grading.compute_grade` and pinned by `tests/test_drawdown_basis.py::test_no_stated_limit_stays_ungraded_even_on_the_percent_basis`.

**An unassessable walk-forward CAPS the grade at B** (Aaron's call, 2026-07-30). An A is the only grade that claims out-of-sample evidence, so awarding one off Monte Carlo alone overstates what was measured. The cap is a CEILING, not a deduction — a run that would have graded C stays C — and it applies only when WF *ran and could not be assessed*, never when it was genuinely not run (an MC-only auto-trigger is not evidence of overfitting). When the cap binds and the worst-1% would otherwise have passed, a reason says so explicitly rather than leaving the user to infer why an A became a B.

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

**Rerun over a new period:** `RetryRunRequest` optionally carries `start_date`/`end_date` (ISO days). Both or neither — a half-set, a malformed date, or `start >= end` is a 400. The dates are written onto the run row (`lab_db.update_run_period`) BEFORE the job fires, because the retry re-fills the SAME row: a run that kept its old window in the DB while being re-run over a new one would label the new result with the wrong period. **Standalone runs only** — a sweep child or optimizer combo shares one period with every sibling in its set, so an override there is rejected (400) rather than silently desyncing the comparison. The frontend mirrors the split: `BacktestDetail`'s Rerun button opens `RerunModal` (period pre-filled from the run) only when `!sweep_id && !optimization_id`, and re-fires directly otherwise.

**Rerun clears its own stale progress entry:** a retry reuses the `run_id`, so the FAILED attempt's entry in `lab_progress.json` — error text and all — is still filed under that same id, and the live banner rendered the old error while the rerun was already running. `retry_backtest_run` clears it up front, but only when `read_progress()["job_id"]` is this run: the progress file is shared across runners, and blanking it for a live job on another platform would be a worse bug. The frontend half is `useRetryBacktest` marking a trigger + invalidating `['lab','progress']` — without it the progress query sits on its idle 30s cadence (the last payload was a failure, so it isn't `running`) and the stale text survives the backend fix.

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

## Portfolio stacks (smart reuse)

A **stack** layers 2+ Python strategies over ONE shared instrument + timeframe + window + cost profile. The combined portfolio line and per-strategy toggles are composed CLIENT-SIDE from each leg's `daily_pnl`, so there is no stack-level result row and toggling a leg off never re-runs anything.

**Ownership ≠ membership (the reuse enabler, 2026-07-25).** Two tables:
- **`stacks`** — the stack's own settings (`instrument`, `bar_type`, `bar_value`, `start_date`, `end_date`, `commission_per_side`, `slippage_ticks`, `created_at`). Persisted so a stack whose legs are ALL reused (zero owned child runs) still knows what it is — `list_stacks`/`get_stack` read settings from here, not from a child row.
- **`stack_members(stack_id, run_id, owned, position)`** — membership. `owned=1` = a fresh run the stack created (carries `backtest_runs.stack_id`, hidden from the Runs tab, **deleted with the stack**). `owned=0` = a pre-existing standalone run REUSED as-is (`stack_id` stays NULL, **stays in the Runs tab, survives stack deletion**). `list_stack_runs` INNER JOINs members→runs so a reused run the user later deletes simply drops from the stack instead of 500-ing.

**Smart reuse on create (`trigger_stack`).** For each leg, `find_matching_stack_run()` looks for the most-recent COMPLETED **standalone** Python run (`stack_id IS NULL AND stress_test_id IS NULL AND sweep_id IS NULL AND optimization_id IS NULL`) matching the leg's EXACT identity — strategy + instrument + `bar_type` + `bar_value` + window + `commission_per_side` + `slippage_ticks`. Match → add an `owned=0` member, no re-run. No match → create an `owned=1` child and queue it through `run_sweep` (unchanged). The python job lock is only taken when ≥1 leg needs a fresh run; an all-reused stack is assembled instantly and returns `status="complete"`. A per-strategy `params_by_strategy` override **disables reuse for that leg** ("run it my way", not "reuse whatever exists").

**Matching is STRICT by Aaron's call (2026-07-25)** — any difference (even a one-day window shift or a different cost field) misses and the leg re-runs. Do NOT loosen it without asking. **Cost defaults are 0/0** (`commission_per_side=0`, `slippage_ticks=0`, `bar_value=15`) — matching the Pine strategies, which are all pinned `commission=0, slippage=0` for TV↔Python parity (costs are modeled inside the strategy via the 30-tick breakeven buffer). **These fields are cosmetic for Python runs** — `python_runner` never reads them; the real cost comes from the strategy's account profile (`backtest/fills.py` `PROFILES["vantage_demo"]` = commission 0.00) + measured (tick) / 0 (bar) slippage. So they're the displayed + leg-matching values, not the applied ones. The stack's original bug was the **5m timeframe** (vs the designed 15m), not costs — a stacked leg read ~⅓ of the same strategy's standalone run because it ran on entirely different signals. The forex rulesets (`personal_forex_demo`, `unconstrained`) also seed `default_slippage_ticks=0` (converged on existing DBs in `init_db`) so the Run modal shows 0/0 too; futures rulesets keep `2.25/1` (NT8/MT5 platforms genuinely apply them).

**`POST /backtests/stacks/preview`** (`StackPreviewRequest` → `StackPreviewResponse`) reports per-leg `action` (`reuse`|`run`) + the matched run's `net_pnl`/`trade_count`/`profit_factor`, running nothing — it drives the modal's live Reuse/Run badges. **`GET /stacks/{id}`** (`StackDetail`, async) now also carries `commission_per_side`/`slippage_ticks` (from the settings row, for the Rerun modal) and a full-calendar `regime_timeline` for the shared window (drives the equity chart's regime overlay). Regime source: read from a leg's `regime_timeline.json` if present; sweep-child legs aren't regime-tagged, so when none exists it computes the timeline once via `build_regime_timeline_and_tag(..., runner="python")` (off-thread) and caches it to the base leg's dir so later polls read the file. **`build_stack_chart_spec`** carries the base leg's structure `overlays`/`indicators` (a property of the market on the shared candles, identical for every leg) and a `base_run_id` — so the stack's price chart has full BacktestDetail parity (structure layers, ATR pane, fib/measurement, and M1/M5 drill-down routed through the base leg's `/candles`). **`delete_stack`** removes only `owned=1` legs from `backtest_runs` (+ their report dirs, via the router) and clears the `stacks`/`stack_members` rows; reused legs are untouched. `_backfill_stack_membership` (in `init_db`, idempotent) materialises `stacks` + owned `stack_members` for any legacy pre-membership stack so old stacks survive. Python-only: summing daily P&L models independent sleeves, and NT8/MT5 have their own single-window terminals a lab stack has no reason to touch.

## History floors — blocking a window the broker has no bars for

**MT5 does not error when a symbol lacks history at the requested timeframe — it returns the nearest
COARSER bars, still labelled as what you asked for.** A backtest fed daily bars as 15m does not crash:
it produces a full trade list, a clean equity curve, and a completely fictional answer. So the lab
refuses the window instead of running it.

The floor is **measured, never hardcoded**: `backtest/data/history.py` binary-searches the live
terminal by bar density and caches per `(server, symbol, timeframe)` — swap MT5_Lab to a broker with
deeper history and the limit widens by itself. `services/history_limits.py` is a thin shim over it and
declares no dates of its own; duplicating them here would guarantee the UI and the data layer
eventually disagree, and the disagreement would surface as a run that passes validation then dies
mid-flight.

- **`GET /backtests/history-limit?instrument=&bar_type=&bar_value=&runner=[&refresh=]`** → `HistoryLimit`
  (`earliest_date`, `broker`, `verified`, `source: probed|seed`, `note`) or **`null`** when unbounded.
  The frontend date picker reads this instead of hardcoding a date. `refresh=true` re-probes (~15s).
- **400 at every trigger that accepts dates**, checked BEFORE the platform lock is taken or a run row
  is inserted: `POST /backtests/run`, `POST /runs/{id}/retry` (period override), `POST /backtests/sweep`
  (per instrument), `POST /optimizations/run`, `POST /backtests/stacks`. `BarSource.load` raises too, so
  a path that forgets the check still cannot replay substituted bars — but it raises at FETCH time, by
  which point a row exists, a lock is held, and the user is watching a progress bar. That is the whole
  reason the router-level check exists as well.
- **Python runner ONLY.** NT8 (NinjaTrader) and MT5 pull history from their own terminals, so their
  depth is a different question with a different answer. `limits_for()`/`validate_window()` return
  None / no-op for them. Claiming a Vantage gold floor on an NT8 futures run would be a lie in the
  more dangerous direction.
- **`null` means UNKNOWN, never "unlimited"** — agent down, or a broker we cannot identify. Nothing is
  refused on a guess; the data layer's bar-spacing backstop still catches substituted bars.

Full mechanism, the evidence table, and the probe's two-phase design: `backtest/CLAUDE.md` →
*History floors*.

## ChartSpec candles — cap the WINDOW, never the timeframe

6.5 years of M15 is ~160k candles and a ~15 MB `chart_spec.json` on every chart open. Something has
to give. There were two axes to give on, and the first choice was wrong:

- **Coarsen the bars** (the old `_fit_timeframe`: that run shipped **H4**). Covers the whole span —
  and is useless, because H4 is a timeframe the run's trades and blocked setups line up with nowhere.
  It also forced a fetch-on-open to get back to M15, which meant a loading placeholder and a visible
  swap on every chart open.
- **Trim the window** (`_capped_start`, 2026-07-27, Aaron's call). Ship the run's OWN timeframe over
  the newest slice that fits `_CANDLE_CAP`. Measured on that same run: **33,041 candles / 3.1 MB /
  17 months**, painted on the first frame with no fetch at all.

Reach is restored by PAGING, not by coarsening: `historyStartMs` (the run's start) tells the panel how
far back it may go, and scroll-left pulls one page at a time through `GET /runs/{id}/candles`
(measured: 175d / 11,255 candles / ~1.0 MB / ~1.5s at M15). So trimming costs reach, not access.

**And a page carries the window's ANALYSIS, not just its bars (`analysis=true` → `_page_analysis`,
2026-08-02).** For a year that was only half true: the bars paged in and everything drawn ON them —
structure overlays, fair value gaps, blocked and missed setups — did not, because all of them are
built over `candles` and `candles` stops at `ship_from`. Scroll past that boundary and each layer
the reader had switched on drew nothing, with its toggle still on. Two rules hold it together, both
pinned by `tests/test_chart_page_analysis.py`:

- **Warm-up is context, not content.** The structure and FVG engines are streaming state machines,
  so a page is replayed over its window PLUS `_PAGE_WARMUP_BARS` (2,000 ≈ 30 trading days at M15)
  of older bars, and only overlays whose span reaches into `[from_ms, to_ms]` are returned. Without
  the prefix every page opens with no swings and no live gaps; without the filter the previous
  page's overlays are served twice.
- **A page's internal structure is HISTORIC** (`_demote_page_internal`). `build_market_structure_overlays`
  labels the newest leg in whatever it replayed "current", so each page would claim its own current
  leg — a group whose whole meaning is "the leg the run is in NOW", which exists only in the shipped
  window. The demotion carries the historic branch's own `requires` shape so the four toggles keep
  nesting.

It is best-effort and wrapped in its own `try`: the page is about its BARS, and a failed replay must
never cost the reader the history. Drill-down passes `analysis=False` — structure is computed on the
base timeframe, and a 1m view is a question about fills.

`baseTimeframe` and `runTimeframe` are now the SAME value. `runTimeframe` stays on the contract
because a `chart_spec.json` cached under the old scheme still carries a coarsened `baseTimeframe`,
and the panel opens on `runTimeframe` — which keeps those caches usable until they rebuild. Every
cached spec was cleared when this landed; they rebuild on next chart open (~5s for a 17-month M15).

## Blocked setups — the trades that never happened

A signal the strategy had READY and one of its OWN rules refused places no order, so it appears in
no trade list, no equity curve, no `engine_trades`, and no broker report. Nothing downstream can
infer it. That makes it impossible to judge whether a blocking rule protects the account or costs
it — which is the whole reason this channel exists.

The path is one straight line, and every hop is OPTIONAL so a runner that can't report them is
simply silent (never a lie, never an empty UI):

1. **The strategy records them.** `mpc_sos_fade/execution.py` — `BlockedSetup` + `_record_blocks`,
   a port of `mpc_strategy.pine`'s pink `TRADE BLOCKED` tag (4025-4086): the same six reason codes,
   the same PRECEDENCE, and the Pine's `sosBar*10 + code` dedupe generalised to the reason SET (one
   record per setup per distinct combination, not per bar). **One deliberate deviation:** the Pine
   reports the FIRST blocker only (a chart tag has room for one line); we record EVERY rule refusing
   the setup, because the lab filters by reason and "blocked by the veto" must stay true when the
   final hour was also blocking. Precedence survives as the ORDER, so `codes[0]` is exactly what
   `f_blkCode` would have returned — a per-reason count off the primary still reconciles with
   TradingView. **Reporting only** — nothing reads a record back, so it cannot move a decision and
   `compare_strategy.py`'s `px_*` stream is untouched. `mpc_bleg` records none by construction (its
   `BLegExecution` overrides `_place_entries`, where the recording hangs) — deliberate: those codes
   describe why an **A+** setup was refused, and A+ never trades in that fork.
2. **`backtest/output.py`** — `build_blocked_setups()` turns them into the lab's row shape;
   `build_results` returns them as `blocked_setups` (always present, `[]` when there are none).
   Strategy-agnostic duck-type: `dir`/`time_ms`/`edge` plus parallel `labels`/`reasons` sequences,
   emitted as a `reasons: [{label, reason}]` LIST (primary first).
3. **`backtest_runner._handle_complete`** writes `reports/lab/<run_id>/blocked_setups.json` when the
   runner reported any. Runner-agnostic — NT8/MT5 return no such key, so no file.
4. **`chart_spec._build_blocks`** reads that file into the spec's `blocks[]`, clipped to the candle
   window (same reason trades are). No file ⇒ `[]` ⇒ the chart's Blocked toggle never appears. The
   chart builds its per-reason filter roster straight off those label strings, so nothing between the
   strategy and the UI needs to know what any rule means.

**Only runs completed AFTER this landed have the file** — it is written at completion, and there is
no backfill (recomputing it would mean replaying the strategy). An older run's chart correctly shows
no Blocked layer. A run that HAS the file but a stale cached `chart_spec.json` needs **Reload charts**.

The `label`/`reason` strings are the STRATEGY's own words end to end; neither the lab nor the chart
interprets them, so a strategy with a different rule set needs no change anywhere in this path.

## Missed setups — how close the ones that died came

A **block** and a **miss** answer the same question one step apart in a setup's life. A block is a
trade the strategy had FULLY READY and one of its own rules refused. A miss never got that far: it
met some of the strategy's confluences and then DIED. Both place no order, so both are invisible
everywhere else; separately they answer "is this rule costing me?" and "what am I actually waiting
on that never arrives?".

The path is the block path, hop for hop, and every hop is equally optional:
`mpc_sos_fade/execution.py` (`MissedSetup` + `_record_misses`, a port of the Pine's orange 2-of-3
callout — see that package's CLAUDE.md → *The missed-setup watch*) → `backtest/output.py`
`build_missed_setups` → `missed_setups.json` in the run dir → `chart_spec._build_misses` →
`spec.misses[]` → the price chart's **Analysis → Missed** layer, default OFF.

**The one thing that is NOT a copy of the block path: `spec.missNoise`.** `_build_misses` returns a
second value — the reason labels the chart should start with UNTICKED — and it is **derived, never
named**. A label goes on the list when it never once appears on a miss the strategy flagged `near`.
Why this exists: the Pine's callout defaults to "Near misses only" because a chart showing every
setup that simply never retraced is unreadable, and on the measured window that is 50 of 93 markers.
Reproducing that default by teaching the chart what "No retrace" means would have put a strategy
concept inside a panel whose one rule is that it has none. Instead the strategy marks `near`, the
emitter turns it into a list of strings, and the panel hides those on first render. The panel still
lists them with their counts, so nothing is hidden silently, and one click brings any of them back —
which the Pine's radio buttons cannot do.

Same on-disk-shape discipline as the blocks: a record missing `near` reads as `near: True`, so a
file written before the flag existed does not have every one of its reasons filed as noise and
hidden on open (which would make an old run look like it had no misses at all). Locked by
`backend/tests/test_chart_spec_misses.py`. **Python runner only, no backfill** — same as the blocks,
for the same reason.

## Fair value gaps — only where something happened

`services/fvg_overlays.py`. Replays the canonical `engines/fair_value_gaps/` engine over the candles
the chart is about to show and emits one `box` overlay per gap, in the group `Fair Value Gaps`, which
the panel lists in its **Analysis** dropdown (default OFF). Never a second FVG engine — bare-name
import, public events only, same shim as regime / news / structure.

**A gap is drawn only if it was in the engine's LIVE list on the bar of a trade ENTRY, a blocked
setup, or a missed setup.** That filter is the whole design: a 33k-bar run leaves thousands of gaps
and drawing them all is both unreadable and an answer to a question nobody asked. When several gaps
were open at one of those bars, ALL of them are drawn — a cluster is exactly the thing worth seeing.
The anchors arrive as bare timestamps (`trades[].entryTime` + `blocks[].time` + `misses[].time`), so
the module knows nothing about what a trade or a block IS; hand it different anchors and it draws
gaps at those. No anchors ⇒ `[]` ⇒ the toggle never appears, which is the honest answer for NT8/MT5.

**⚠ These are `mpc_assistant.pine`'s gaps, and that is NOT the set the bot traded on.** The indicator
runs `fvgMaxCount 8`, `fvgRequireClose false`, and the timeframe-**split** floor
(`timeframe.in_seconds() < 900 ? 0.0 : 0.04`), with `eqExemptFvg` on — all locked constants, mirrored
here as named `MPC_*` values. `strategies/python/mpc_sos_fade` pins `fvg_max_count=7`,
`fvg_require_close=True`, `fvg_threshold_pct=0.1`, because `mpc_strategy.pine` hardcodes the
middle-bar close check and carries its own count. So the bot's entry rule counted strictly FEWER gaps
than this layer draws (`require_close` only ever removes gaps, and its floor is higher). The chart was
asked to match what TradingView draws, so it does — do not resolve the fork by repointing the emitter
at the strategy's config, and do not read a drawn gap as one a "no FVG" block ignored. Background:
`engines/fair_value_gaps/CLAUDE.md` → the `require_close` callout.

**Two details that would silently draw the wrong thing if they broke**, both pinned by tests:
- **The floor is timeframe-split**, so the same run charted at M5 and M15 legitimately has different
  gaps. An unrecognised timeframe takes the STRICTER (15m+) branch on purpose: over-filtering drops a
  marginal gap, under-filtering invents one the indicator never drew, and only the second puts
  something on the chart that is not there.
- **Box span mirrors the Pine box.** Pine creates it at `bar_index - 1`, pushes `box.set_right` every
  surviving bar, and DELETES it on the bar the gap is mitigated or evicted — so `t1` is the bar
  BEFORE its death, never the death bar. On the death bar mpc showed nothing there.

`build_stack_chart_spec` **strips this group**, for the same reason it strips blocks and misses: it
is anchored to the BASE leg's trades, so on a merged chart it would draw gaps at one strategy's
entries and nothing at the others' — which reads as "these setups had gaps and those didn't". A leg's
own page still carries it. Existing runs need **Reload charts** (`chart_spec.json` is cached).

**Tested two ways** (`tests/test_fvg_overlays.py`, 16 tests). Hand-built candles pin the layer's own
rules (which gaps, the cluster case, the box span, the timeframe split, the mpc constants). Then a
real TradingView export is replayed and every box is diffed against **the Pine's own live gap arrays**
(`px_fvg_top_k` / `px_fvg_bot_k` / `px_fvg_count`): on each sampled anchor bar the boxes covering it
must be exactly the gaps mpc had open, price for price. The unit tests could all pass on an emitter
drawing the wrong gaps; that one could not. The export is git-ignored, so those two SKIP without it —
and it predates the 2026-07-18 mpc default drift, so it is replayed with the settings ITS build ran
(which is what the config keyword arguments on `build_fvg_overlays` exist for). That the ENGINE still
matches today's mpc build is proven separately by `engines/fair_value_gaps/tools/compare_fvg.py`.

## Trade fibs — the leg each trade was actually priced off

`chart_spec._trade_fib`. Aaron's brother asked to see, on every trade the chart plots, the fib run
on the points that trade used — which retracement levels it went into. The strategy records that
ladder when it places the order (`mpc_sos_fade/execution.py` → `TradeFib`), `backtest/output.py`
puts it on the equity-curve point, and this turns it into the chart's `trades[].fib`.

**The levels are PASSED THROUGH; only the two RATIOS are computed here.** That split is the whole
design. The prices are the ones the strategy had in hand at placement, so a chart and a bot can
never disagree about where a level sat — a fib rebuilt downstream from anchors and a direction is
a second claim about one leg, which is the failure this repo has now met four times (Run modal
costs, Optimize modal params, the SSH dot, the lab-vs-Pine parameter names). What a price ladder
CANNOT state is where the fill landed on it, and that is the question:

- **`entryRatio`** — the fill as a ratio (0.702 = it entered at the 70.2% retrace). On the A+ bot
  this reproduces the entry model without being told about it: an entry snapped to a fib by
  `_fib_snap` reads exactly 0.618 / 0.702 / 0.786, and a gap-edge entry reads between two rungs.
- **`deepestRatio`** — the same for the deepest ADVERSE price of the hold, i.e. how far the
  retracement really ran after entry. **Not clamped at 1.0**: a trade that traded through the leg
  origin genuinely retraced past it, and clamping would report every stop-out as having stopped
  exactly at the origin.

⚠ **Both are computed and served, and since 2026-08-03 the chart draws NEITHER** — the panel's Fibs
layer prints the ladder only, and the trade's own `Entry` / `Deepest` annotations carry those two
price rows (with prices). They stay here because they are the two readings the ladder cannot state
and the derivation is pinned by tests; if nothing consumes them by the next chart pass, delete them
rather than leaving a field the UI implies it is showing.

Both are pure geometry off two levels the ladder already carries — a fib price is linear in its
ratio, so any two `(ratio, price)` pairs define the line and inverting it maps a price back. **No
anchor, no direction, no range**, hence no branch for a bear leg and nothing here that can drift
from the strategy. A degenerate (zero-height) leg returns `None` rather than dividing by zero.

`startTime` is the bar the LEG began on, not the entry — a ladder starting at the fill would hide
the retracement that produced it, which is the thing the layer exists to show.

**Optional end to end**, like blocks and misses: NT8/MT5 record none, a Python run finished before
this landed has none (**no backfill — it would mean replaying the strategy**), and `mpc_bleg` has
none by construction. The chart's Trade fibs toggle is listed off whether any trade carries one, so
absence removes the switch instead of offering an empty layer. Existing runs need **Reload charts**
(`chart_spec.json` is cached). Tests: `tests/test_chart_spec_trade_fib.py` (12).

## News filter (post-run)

The economic-calendar (news) filter is a **post-run view layer**, NOT a run-time gate: the lab runs every backtest RAW (news is never wired into the C#/MQL5 strategy), so removing news-window trades is pure arithmetic on the finished trade list — instant, no VPS re-run. Design decision (Aaron 2026-07-05): **run raw + toggle after.** Window default **15 min before / 30 min after** a high-impact USD release (asymmetric — liquidity dies only in the last minutes before; the spike/reversal/move run 15–30 min after). **Two rules, both switchable, and BOTH DEFAULT OFF** (2026-08-01, Aaron's call): the page opens on the run exactly as traded, so every number on it is the backtest's own and turning a rule on is a deliberate what-if. That replaced two different defaults for one reason — a filtered default means the headline figure on screen is not the run's result, and no checkbox further down the page makes that obvious. Holidays had defaulted ON (hardcoded always-excluded with no control at all until 2026-07-30, when they became a visible checkbox but stayed ticked), and news followed the strategy's own `avoid_news`, so the default silently DIFFERED BETWEEN STRATEGIES — two runs over the same window could open on different trade counts with nothing on screen explaining why. The backend reports `in_news` and `in_holiday` separately and always has; every default here has been a frontend-only decision.

- **`services/news_filter.py`** — composes the canonical `engines/news/` engine (imported by bare name after adding `engines/` to `sys.path`, same pattern as regime; **never a second calendar impl**). `build_report(trades, pre, post, ...)` loads the `EventStore` cache, builds a lab `NewsPolicy` (high-impact USD, holidays always), and walks each trade's `entry_ms` through the engine → per-trade `{in_coverage, in_news, in_holiday, title}` + coverage boundary + counts. Reads `in_news` (a high-impact window) and `in_holiday` **separately** so the UI keeps them separable. 9 unit tests (synthetic events, no network). Coverage honesty: outside the fetched calendar range trades come back untagged (never guess) — backfill months via `engines/news/tools/backfill.py`.
- **`GET /backtests/runs/{id}/news?pre=&post=`** → `RunNewsReport` (models.py `RunNewsReport`/`NewsTradeTag`). Pure off the stored `equity_curve` — no VPS. `pre`/`post` are the window minutes (sliders re-call to re-tag). Old runs with no `entry_ms` come back untagged.
- **Trade entry time capture:** `parse_trades_csv` now stores each trade's `entry_ms` (UTC epoch ms) on its equity-curve point, from the NT8 "Entry time" column via `_parse_nt8_dt`. The VPS **NinjaTrader Time zone is UTC** (confirmed) → naive value treated as UTC, no offset. Old NT8 runs predate this → re-pull with **Reload charts** (or rerun). Python runs carry it from `backtest/output.py` and never needed either.
- **`entry_ms` AND `exit_ms` MUST be declared on `models.EquityPoint`** (entry fixed 2026-07-28, exit 2026-07-30 — the SAME omission, caught twice, which is why this is written as a rule and not an anecdote). `exit_ms` had likewise always been in `equity_curve.json` and was likewise stripped on the way out; with both present a consumer can compute trade duration over any SUBSET of trades, which is what lets the News filter report **Avg Trade** instead of a dash once it removes something. Pydantic drops any field a model doesn't declare — so the value reached disk and the `/news` endpoint (which reads `equity_curve.json` directly, and therefore tagged correctly all along) but was stripped on the way to the browser. The card's `hasEntryTimes` check then failed for EVERY run and it showed "made before trade times were recorded" universally, which reads as an old-run problem and is not one. Same trap the `favorable`/`adverse` comment two lines below it warns about. **Nothing that reaches the frontend can rely on a field being in the JSON on disk — only on it being in the model.**
- **`avoid_news` is metadata, not a default:** `strategies.avoid_news` (INTEGER col, migration; default 0) overlaid from `<Strategy>.meta.json` top-level `"avoid_news"` by `strategy_scanner._read_strategy_overview`, exposed on `Strategy.avoid_news`. ⚠ **It no longer sets the News toggle's default** (2026-08-01 — both rules default OFF; see above). It remains real strategy metadata read off meta.json and is still exposed on the API; nothing in the UI consumes it today. Re-wiring it to a default would restore the per-strategy divergence that change removed — raise it before doing so. `ORB.meta.json` ships `avoid_news:true` (gold avoids news). **Scanner fix:** the `.cs` skip now also re-scans on meta.json **mtime** (mirrors the `.mq5` path) — before this, a meta-only edit on an unchanged `.cs` source (avoid_news, edge/steps, param labels) never took effect. A **Scan** picks up the new value.
- **Runner support:** NT8 and **PYTHON** both work (python verified end-to-end 2026-07-28 on a 142-trade XAUUSD run — 142/142 in coverage, 11 news-window trades at a 15-min pre-window). **TODO (#3, still not built): the MT5/forex path** — `runner_dispatch._normalize_mt5_results` needs its own `entry_ms`, and the **MT5 broker server clock is NOT UTC** (offset + DST), so it needs its own timezone handling (a confirming step like the NT8 one).
- **Calendar coverage is the real gate, not the code.** The engine reports `has_coverage=False` outside the fetched range and the filter goes inert there — so a correctly-wired filter over an unbackfilled period looks identical to a broken one. Backfill first (`engines/news/tools/backfill.py --from YYYY-MM`), then judge. The cache is git-ignored, so it is per-machine and a fresh clone starts empty.

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
