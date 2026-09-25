# CLAUDE.md — Command Center Backend

**Purpose:** FastAPI backend (`:8000`) — owns all SQLite state, talks to the VPS via SSH + HTTP agents, runs the smart-money pipeline via subprocess, and drives NT8/MT5 backtests.
**Scope:** This covers backend conventions, routers, services, DB, and VPS interaction. It does NOT cover the frontend (see `../frontend/CLAUDE.md`) or `algos/`/`smart-money/` source.
**Status:** Live — lab (strategies, rulesets, backtests, sweeps, optimizations, stress tests, MT5 runner, Python runner) all shipped.




Auto-loaded by Claude Code when editing any file inside `backend/`.

FastAPI backend served on `:8000`. Talks to the VPS via SSH and HTTP, runs smart-money pipeline via subprocess, and owns all SQLite state. The frontend never touches the filesystem or the VPS directly.

The lab module (strategies, firms, backtests, evaluations) is live as of M1.

**Lab design principle:** The user always picks which firm challenges to evaluate against. Never default `evaluate_firms` to all firms.

---


**Last reviewed:** 2026-08-12 - the dated build narrative that used to sit here moved VERBATIM to `command-center/docs/BACKEND_DIARY_NOTES.md`. **Nothing was deleted.** It was 112,399 bytes in 4 paragraph(s), the largest 47,183 bytes on a single line, loaded in full every time anyone opened this area. Rules stay here; the evidence is one file away.

## Guides & references

- `command-center/docs/PROP_RULESET_KPIS.md` — per-firm prop ruleset KPIs, doc links, and the DB sync-check query.
- `command-center/docs/BACKEND_BUILD_NOTES.md` — NT8 Strategy Analyzer pywinauto automation implementation notes, and the dynamic sizing/risk engine build history.

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
- Write a destructive test and rely on a person remembering a flag to keep it out of the way.
  `tests/test_integration.py` drives the live VPS and its Case 6 kills a running agent on purpose;
  its docstring said "select it explicitly" from day one and nothing enforced it, so a bare
  `pytest tests/` ran the lot. `pytest.ini` now carries `-m "not integration"` — the suite is
  DESELECTED by default and runs only on `pytest tests/test_integration.py -m integration`. If you
  add another test that touches the live box, mark it `integration` so the same interlock covers it
- Kill by image name anywhere — in source, in a test, or in a one-off command. `taskkill /f /im
  python.exe` takes out both backtest agents, the Telegram bot and the LIVE TRADING BOT, and it is
  what left the bot dead for three days in July. `test_integration.py` carried one until 2026-08-05.
  Every kill matches on BOTH `name='python.exe'` and something identifying the ONE process — see
  `routers/bots.py::_kill_bot` for why each half is load-bearing
- Let the agent supervisor run in a test process. `CC_DISABLE_SUPERVISOR=1` is set at module scope
  in `tests/conftest.py`; a fixture is too late, because `main` is imported at collection. Without it
  a plain `pytest tests/` restarts the SSH tunnel and fires two scheduled tasks on the live VPS
- Commit credentials (Telegram tokens, API keys, `.env`)
- Add a prop firm without filling in `docs_url` — rules drift, the link is how you verify
- Treat `pytest-xdist` in `requirements.txt` as optional tooling and drop it. It is a RUNTIME
  dependency of `scripts/run_all_tests.sh`, which passes `-n auto --dist load` to both python
  suites — this venv is the one that runs them BOTH, not just the backend's. Without it pytest
  exits 4 on an unrecognised argument, which reads as a suite failure and sends the reader at the
  tests; the script checks for it up front and refuses with the install line instead. **MEASURED:
  this suite 150s → 52s.** ⚠ **A test added here must be parallel-safe** — per-test `tmp_path` DBs,
  no fixed paths written. A test that writes a shared path breaks OTHER tests non-deterministically,
  which is the worst failure shape a suite has
- Re-read a bar cache, or re-replay an engine, once per TEST when the tests share a window.
  `tests/test_structure_internal_breaks.py` read the 31 MB / 559,035-row M5 cache once per window
  per test and replayed the structure engine six times for two distinct answers — **62s of a suite
  that was 221s**, now 21s, by `lru_cache` on the read, the window slice and the replay, plus a
  `timegm` slice in place of `strptime` (2.45s a window on its own, and its equivalence is
  asserted). ⚠ **A cached frame is handed out as-is, so nothing may mutate one**, and ⚠ **the
  caches are MODULE-level, so a parallel runner has to keep a file on ONE worker**
  (`--dist loadfile`) or every worker rebuilds them

---

## When you add a new module

1. Create `routers/<thing>.py`
2. Create `services/<thing>.py` (or `<thing>_db.py` for DB-heavy modules)
3. Add Pydantic models to `models.py`
4. Register the router in `main.py`
5. If it has its own DB, create it under `data/` and call `init_db()` on startup
6. Update `notes/layout.md`

---

## The notes — read the matching file BEFORE touching its code

🔴 **This file was 576 KB on 2026-09-13 and loaded in full every time anyone opened
a file in this folder.** Everything outside the rules above moved VERBATIM into
`notes/` — nothing reworded, nothing dropped.

**How to write here from now on:** a rule gets ONE line under its topic below; its story and
evidence go in that topic's notes file. A notes file satisfies the commit hook's doc check.

⚠ **An old pointer to a section of this file still resolves** — every moved heading is
listed below under the notes file that now holds it.

### `notes/layout.md` — Directory layout

**Read before touching:** adding, renaming or looking for a file.
Most-cited code: `routers/system.py`, `routers/bots.py`.

- Directory layout

### `notes/runs.md` — Backtest runs, rulesets, sizing and metrics

**Read before touching:** the run pipeline, rulesets, the sizing engine, run metrics, run pages, run comparison.
Most-cited code: `services/python_runner.py`, `services/history_limits.py`, `routers/firms.py`, `services/grading.py`, `services/sizing_engine.py`, `services/decision_log.py`.

- Ruleset abstraction (M3)
- Dynamic sizing & risk engine + decision log
- Lens metrics (the per-run scoring layer)
- 🔴 A trade's `exitPrice` is an AVERAGE, so the chart is given its FILLS (2026-08-25)
- Foundational config (Pass 1)
- What's built (status)
- The Backtests list and the Backtest detail page — the 2026-08-06 audit
- History floors — blocking a window the broker has no bars for
- Comparing two runs — the BASIS before the result
- `python_runner` finalizes the strategy after `_replay` (2026-08-20)
- A RERUN reads the broker the run was MADE on (2026-08-24)
- The BROKER spells the symbol, and the run records the resolved name (2026-08-26)
- Recorded answers a browser spec replays are held to their route's model (2026-09-10)

### `notes/box.md` — The trading box, agents and test safety

**Read before touching:** the agent supervisor, SSH to the box, readiness, the calendar, test isolation.
Most-cited code: `services/agent_supervisor.py`, `routers/bots.py`, `services/nt8_switch.py`, `services/vps_ssh.py`, `services/readiness.py`, `routers/system.py`.

- The agent supervisor — and the two indicators that were lying
- The box refuses SSH when it is crowded — `services/vps_ssh.py` (2026-09-11)
- Every SSH call rides ONE shared login — 2.2s → 0.45s a call; never a tunnel (2026-09-24)
- The calendar's polarity list was written for the wrong provider
- Readiness — the checks whose failure mode is silence
- A unit test may not reach the VPS, and now it cannot
- Three tests that were red on main, and none of them was wrong about the code (2026-08-14)

### `notes/stress-tests.md` — Stress tests on a single run

**Read before touching:** the stress tester, grading, the stress-test routes.
Most-cited code: `services/stress_tester.py`, `services/grading.py`.

- Stress tests — the 2026-08-05 audit
- How stress tests work

### `notes/accounts-risk.md` — Broker accounts, risk shares and bot P&L

**Read before touching:** accounts, risk shares or caps, assigning a bot, the terminal scan, account P&L.
Most-cited code: `services/stack_risk_budget.py`, `services/bot_account_registry.py`, `services/account_stack_basis.py`, `services/terminal_scan.py`, `services/account_sync.py`, `services/bot_earnings.py`.

- Shares may add up past the cap, and an account has a PRIORITY order (2026-09-15)
- The shares may not add up to more than the ceiling (2026-09-03) — superseded 2026-09-15
- An account's risk budget is ONE planner, and a change that frees room is always allowed (2026-09-11)
- A shared stack's legs may not add up past its cap (2026-09-10)
- The account REGISTRY — the gap that made moving a bot a manual afternoon (2026-08-12)
- "Backtest these bots" — `GET /bots/accounts/{account}/stack-basis` (2026-09-10)
- Checking the account list against the BOX — `services/terminal_scan.py` (2026-09-10)
- 🔴 An assignment may only write a param the RECEIVING strategy declares (2026-09-04)
- The account's net is measured off what went IN (2026-09-12)
- A balance is an account's only if it was READ on that account (2026-09-14)
- A LIVE account names its own Telegram channels, and no door puts a bot on one that does not (2026-09-13)
- An account's demo/live field is LOCKED on the page — and now on the save route too (2026-09-14)
- `POST /{bot_name}/clone` — a fresh copy of a bot, for a strategy with nowhere free (2026-09-14)
- What a BOT made, and why it may not be the account's growth (2026-09-05)
- An account's REAL record off MT5's deals — `GET /bots/accounts/{account}/history` (2026-09-17)

### `notes/bots-deploys.md` — Bots page, versions and deploys

**Read before touching:** the Bots routes, promote or deploy, bot versions, stop/kill, the snapshot, app git commits.
Most-cited code: `routers/bots.py`, `services/bot_versions.py`.

- 🔴 The app's commit swept up whatever ELSE was staged (2026-09-10)
- 🔴 The app's PUSH carried every commit waiting on `main` (2026-09-13)
- 🔴 A REJECTED push was reported as a deployment (2026-09-04)
- Every Deploy button in this app was dead for eight days (2026-08-12)
- A bot's VERSION — the number the page showed was never written (2026-08-07)
- A promote as a JOB — the steps the deploy panel draws (2026-09-10)
- 🔴 A deploy with NOTHING to deploy still stopped and restarted the bot, and the badge that asked for it was drawing a pre-deploy reading (2026-09-23)
- 🔴 Nothing new ON DISK is not nothing new IN THE PROCESS — a nothing-new deploy still restarts a bot running older code (2026-09-24)
- Stopping a bot ASKS it to stop (2026-08-07)
- `_BOTS` is DISCOVERED from the bot folders (2026-09-13)
- The "needs review" flag — the one thing this page could not see
- 🔴 The log panel read a file the bot abandoned nineteen days ago (2026-08-24)
- Nav activity — three booleans so the sidebar stops pulling three lists
- The snapshot says whether a bot's account may TRADE (2026-09-12)
- The snapshot carries the bot's open trade and its halt (2026-09-12)
- The status read runs its two calls side by side, and version reads are capped at three (2026-09-24)
- The files (tamper) check is its own read, asked only by the bot panel; an unanswered check is unknown, never a pass (2026-09-24)
- 🔴 One action at a time per bot, and an account holds still while one of its bots is mid-action — every route that changes a bot or an account goes through `services/bot_ops.py`; deploy jobs are saved to disk (2026-09-24)
- 🔴 A deploy runs in its OWN process (`services/promote_worker.py`) and outlives a backend restart; its job file is its claim on the bot. No test may start a real one (2026-09-24)

### `notes/optimizer.md` — Optimizer and worthiness

**Read before touching:** the optimizer, objectives, worthiness scoring.
Most-cited code: `services/worthiness.py`, `services/objectives.py`.

- Worthiness scoring
- Objective functions
- The optimizer's winner — three fallbacks, each of which must SAY SO
- Optimizations — the 2026-08-04 audit

### `notes/architecture.md` — Schema and architectural decisions

**Read before touching:** the lab DB schema, the per-platform lock, engine imports, any cross-cutting design change.
Most-cited code: `routers/optimizations.py`, `services/stress_tester.py`, `services/grading.py`.

- DB schema — notable columns
- Key architectural decisions

### `notes/strategies.md` — Strategies: scanning, versions, files and metadata

**Read before touching:** the strategy scanner or registry, strategy files, meta.json keys, the Strategies page.
Most-cited code: `services/strategy_import.py`, `routers/strategy_files.py`.

- Strategy file deployment (Pass 2)
- The scanner read the MODULE and hashed the FILES — so a stale row could not be fixed by scanning
- A scan rewrites a Python row whose SCHEMA it would build differently (2026-09-13)
- The Strategies page — the 2026-08-06 audit
- A strategy may declare which row it is LISTED UNDER — `display_under` (2026-08-21)
- The TL;DR is a meta-file key, resolved on the PAGE (2026-09-13)
- Strategy versioning (content-addressed)
- Strategy location + deploy (Pass 2.5)
- A strategy names its own setup on the chart — `chart_tag` (2026-09-02)
- Retired strategy ids are migrated by a script — `scripts/migrate_debrand_ids.py` (2026-09-13)

### `notes/stacks.md` — Portfolio stacks

**Read before touching:** portfolio stacks, shared-account replays, stack costs, dependent (recovery) legs.
Most-cited code: `routers/_costs.py`, `routers/stacks.py`, `services/chart_spec.py`, `services/portfolio_runner.py`, `routers/backtests.py`, `routers/_source_guard.py`.

- Portfolio stacks (smart reuse)
- Shared-account stacks — one balance, one budget, N bots competing for it
- A stack is CHARGED like a single run — `routers/_costs.py` (2026-09-02)
- A stack leg may READ ANOTHER LEG'S LOSSES — `recovery_parent` (2026-08-21)
- 🔴 A rule that NEEDS A PARENT is refused at every endpoint that starts a job (2026-08-21)
- 🔴 A stack's minimum is two LEGS, not two strategies (2026-08-21)
- A stack leg runs on ITS OWN frame, and the stack asks the broker for the symbol it quotes (2026-09-03)

### `notes/stack-grading.md` — Grading and stress-testing stacks, and promoting their settings

**Read before touching:** stack stress tests or grading, the sensitivity pool, applying graded settings to bots, demo-to-live.
Most-cited code: `routers/bots.py`, `services/gradable.py`, `services/bot_settings_import.py`, `services/stress_tester.py`, `services/stack_settings_import.py`, `services/go_live.py`.

- A stress test's settings can be copied onto a DEMO bot (2026-09-06)
- A STACK can be graded — the combined book, and the target that had nowhere to point (2026-09-06)
- A STACK can now be stress tested — `services/gradable.py` (2026-09-06)
- Walk-forward over a STACK — the whole stack per window, on a fresh account (2026-09-06)
- Sensitivity over a STACK — one setting nudged, the WHOLE stack replayed (2026-09-07)
- Grading judges the COMBINED ACCOUNT, and a stack's test is a first-class row (2026-09-07)
- A graded STACK's settings, onto the bots that run its legs (2026-09-07)
- DEMO → LIVE: the whole proven set, or none of it (2026-09-07)
- A dependent leg's parent is STORED, so the stack can be replayed (2026-09-07)
- A stack shift keeps its own BOOK, so it can be opened without inventing a row (2026-09-07)
- A shared stack can run the RE-ENTRY, and it states its LOT CEILING (2026-09-08)
- Stack sensitivity runs its shifts in a POOL, and the estimate stopped double-counting (2026-09-09)
- 🔴 Two halves of one subtraction, read off two different CLOCKS (2026-09-09)
- The stack sensitivity pool runs EIGHT at once, and the six was a tail-biased reading (2026-09-10)
- A stack's setting nudges run ONLY when its bots can compete for risk (2026-09-10)

### `notes/chart.md` — The backtest price chart's data

**Read before touching:** chart_spec or any *_overlays service, blocked/missed setups, chart overlays.
Most-cited code: `services/fvg_overlays.py`, `services/ob_overlays.py`, `services/liquidity_overlays.py`, `services/candle_overlays.py`.

- ChartSpec candles — cap the WINDOW, never the timeframe
- Blocked setups — the trades that never happened
- Missed setups — how close the ones that died came
- Fair value gaps — only where something happened
- Order blocks — the same rule, a different box
- The chart's session windows are the INDICATOR's, and two of the three were not
- Liquidity levels — and WHICH POOLS PRICE HAD ALREADY TAKEN
- Candlestick reversals — which candle turned price, where a setup existed
- A trade that added — `trades[].adds`, and why a box could not account for its own P&L
- Trade fibs — the leg each trade was actually priced off
- The exit ladder — a rung is only a TARGET if the trade places an order at it (2026-08-21)
- `chart_spec` carries what the trade BEFORE a re-entry did (2026-08-21)
- The commit-gate probe writes PER-WORKER files (2026-08-21)
- The re-entry's fill feed is 5m, and `EXTRA_FEEDS` holds a COPY on purpose (2026-08-21)
- The chart is built when the run finishes, and its layers build side by side (2026-09-16)

### `notes/costs-brokers.md` — Costs, brokers, symbols and the news filter

**Read before touching:** costs, spread, broker or symbol resolution, broker-symbols, the regime cache, the news filter.
Most-cited code: `services/news_filter.py`, `routers/backtests.py`, `services/broker_symbols.py`.

- News filter (post-run)
- Costs are ONE SWITCH, and it defaults to ON (2026-08-24)
- The SPREAD has two models, and a strategy says which one it can be charged under (2026-09-02)
- The regime map is CACHED on its inputs, not recomputed per run (2026-08-26)
- The cost account FOLLOWS the attached terminal (2026-08-24)
- The broker's own instrument universe — `GET /backtests/broker-symbols` (2026-09-07)
- 🔴 A stored symbol beat the instrument the run LOADS (2026-09-09)
- What may be changed on a RUNNING bot, and why a switch is not a number - `services/bot_params.py`
