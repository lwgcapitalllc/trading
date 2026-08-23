# CLAUDE.md — Command Center

**Purpose:** Local operations platform for LWG Capital — a React frontend + FastAPI backend that monitors the live bots and runs/evaluates NinjaTrader + MT5 backtests. It also surfaces the Smart Money pipeline, which is built and **flagged OFF** in the UI since 2026-08-04.
**Scope:** This covers the command-center app (backend + frontend). Sub-directory CLAUDE.md files cover backend and frontend internals. It does NOT cover `algos/` or `smart-money/` source — those are read-only outputs to this app.
**Status:** Live — all modules shipped (Bots, Backtests lab, Sweeps, Optimizations, Stress Tests, MT5 runner, Python runner, portfolio stacks). Smart Money is shipped and hidden behind a feature flag.

Local operations platform for LWG Capital. Two-process app: React frontend (`:5173`) → FastAPI backend (`:8000`). The backend is the only process that touches the filesystem or the VPS — the frontend never does.

Sub-directory CLAUDE.md files are auto-loaded when editing files in those directories:
- `backend/CLAUDE.md` — Python conventions, router rules, SQLite patterns, VPS interaction
- `frontend/CLAUDE.md` — hook patterns, component rules, theme tokens, routing

---


**Last reviewed:** 2026-08-12 - the dated build narrative that used to sit here moved VERBATIM to `command-center/docs/COMMAND_CENTER_BUILD_NOTES.md`. **Nothing was deleted.** It was 86,368 bytes in 1 paragraph(s), the largest 86,368 bytes on a single line, loaded in full every time anyone opened this area. Rules stay here; the evidence is one file away.

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

**SSH tunnel** — `start.sh` opens a persistent `ssh -N forexvps` background process on launch. This keeps two LocalForwards alive: `8765` (NT8 nt8_agent_tunnel) and `8766` (MT5 mt5_agent_tunnel). Without the tunnel, both runner_dispatch and mt5_agent_client calls fail even though SSH itself appears healthy. The tunnel is killed automatically on Ctrl-C. **Important:** the `-L` flags must use `127.0.0.1` (not `localhost`) as the remote target — the VPS resolves `localhost` to `::1` (IPv6) but Flask agents bind only `127.0.0.1` (IPv4). Both `start.sh` and `_restart_tunnel()` in `system.py` use `127.0.0.1` explicitly.

**Agent supervisor** (`backend/services/agent_supervisor.py`, 2026-08-02) — one daemon loop, every 60s, doing the SAME thing on every pass, so a cold start and a wake-from-sleep are literally the same code path. It replaced a ONE-SHOT thread that ran 8s after boot and never again — which is why the MT5 agent had to be started by hand after every laptop sleep. It probes the tunnel by **port binding** and the agents by **HTTP `/health`**, because `ssh -L` binds the local port itself: a bound port with both agents silent is a stale tunnel forwarding into nothing, an unbound port is a dead one, and the pair is what tells them apart. Rebuilds the tunnel, fires `NT8Agent` / `MT5AgentRDP`, and **re-probes after every fire** — `schtasks /run` reports SUCCESS for a task Windows refuses to launch, so the fire is not evidence. ⚠ **The guard is the point, not the loop:** every action is skipped when the scope it would disturb has a job running, and a **python run counts as MT5 traffic** (the local runner pulls its bars through 8766). One deliberate asymmetry — an **unbound** port is rebuilt even under a running job (nothing can connect, so that job is already failing and this is its only route back), while a merely **stale** one is not (an agent driving a heavy backtest stops answering `/health` while working fine — the NT8 agent does exactly this under pywinauto). ⚠ **It is OFF under pytest** (`CC_DISABLE_SUPERVISOR=1`, set in `tests/conftest.py`): every endpoint test builds a `TestClient`, which fires the startup hook, so without the guard a plain `pytest tests/` on a laptop with a dead tunnel would rebuild it and fire two scheduled tasks on the live VPS. ⚠ **It will not rescue an agent whose death left a job marked `running`** — "dead" and "too loaded to answer" are indistinguishable from here and the wrong guess kills a live run — so it names the deadlock in the log instead (`nt8-DOWN-with-a-job-running`); clear the lock (Stop, or restart the backend) and the next pass fixes it. Observed live on 2026-08-02, which is why the message exists.

**Readiness report** (`backend/services/readiness.py`) — the dependencies whose failure mode is SILENCE, checked once at boot and served at `GET /system/readiness`. An un-backfilled news calendar makes the News & Holiday filter **inert** (it tags nothing, which looks identical to a broken filter), and missing `algos/credentials.json` makes every Telegram send a no-op. It REPORTS and never acts — neither is fixable from here, and neither is worth refusing to boot over.

🔴 **THE DEV SERVER DOES NOT RELOAD WHEN THE STRATEGY OR AN ENGINE CHANGES, AND A RUN GIVES YOU
NO WAY TO NOTICE (2026-08-23).** `start.sh` launches `uvicorn --reload` with no `--reload-dir`, so
the reloader watches its working directory — the backend folder — and nothing else. A python
backtest imports its strategy from `strategies/python/` and its engines from `engines/`, both
**outside** that folder. Edit either, or pull somebody else's fix, and the running server keeps
serving the version it imported when it started.

**MEASURED, and it had already produced a real result:** a server started 2026-08-21 12:55 ran a
backtest at 2026-08-23 16:39, eleven minutes after a structure-engine fix landed in the working
tree. Re-driven with the code actually on disk, the same settings give **249 trades / +177.89R**
against the run's stored **250 / +175.43R** — six trades different. The stored run is not wrong
arithmetic; every figure in it reconciles to the cent. It is the right arithmetic on **two-day-old
code**, and the page renders identically either way.

⚠ **Restart the app after a pull, or after any edit under `engines/`, `strategies/` or
`backtest/`.** Nothing enforces this today.

⚠ **Widening `--reload` to those paths is NOT an obvious win and was deliberately not done
here.** The reloader restarts the process, and a restart mid-run kills a backtest that can take
twenty minutes — so a doc edit in a strategy package would destroy a running job. **The safer
shape is to STAMP each run with the commit that produced it**, so a stale result announces itself
instead of a guard deciding when to interrupt work. Neither is built; this paragraph is the whole
of the protection.

⚠ **This is the same failure shape the doc-size guard's own notes name: silence read as
checked.** A run made on stale code has a green status, a full chart and a KPI row. Nothing in a
result can show you which code produced it.

**Backtesting prerequisites** — before submitting a run, the SSH tunnel and NT8 agent must be up. See Sidebar health indicators below.

---

## Key design decisions

**Config translation layer** — Smart Money pipeline stores fractional values (`win_rate: 0.75`), UI shows percentages. `_pipeline_cfg_to_api()` and `_api_cfg_to_pipeline()` in `routers/smart_money.py` handle conversion. The API contract is the stable interface.

**Batched VPS snapshot** — `GET /bots/snapshot` makes two SSH calls and returns one `BotSnapshot`. Frontend polls at 60s. Never SSH per-bot.

**No auto-commit** — `PUT /smart-money/config` writes the file only. The user decides when to commit via `GET /smart-money/config/git-status`.

**There is no bot risk-cap deploy, and there is no risk cap.** `PATCH /bots/{name}/caps` wrote `algos/shared/thresholds.json`, committed, pushed, pulled and restarted the bot — it was deleted 2026-08-04 for having no consumer, and on **2026-08-05 its whole subject went with it**: `thresholds.json`, `bot_state.BOT_THRESHOLDS` and the P&L tracker that read them are all gone (see `algos/CLAUDE.md`). Those numbers were daily-goal / daily-cap / weekly-cap **alert** levels for a job that had carried an empty bot registry since June — so the Bots page was rendering a cap that nothing enforced. **An alert is not a limit.** The live bot's risk lever is `strategy_params.exec_risk_pct` in its instance config, edited through `PATCH /bots/{name}/runtime` (which does not restart it); a real account-level cap has to live in `algos/live/runner.py`, where it can refuse a trade.

**Lab experiment model** — user always specifies which rulesets to evaluate against. The system never auto-evaluates against all rulesets. `evaluate_rulesets` is always set explicitly.

---

## What is built and live

| Module | Status | What it does |
|---|---|---|
| App shell | ✅ Live | Sidebar, topbar, routing across all pages |
| Overview | ✅ Live | Stat row plus Bots and Research summary cards, and the calendar preview. The two Smart Money stat cards and its module card are behind `FEATURES.smartMoney` and hidden; **both grids drop a column with them**, because two cards left in a four-column row reads as data that failed to load. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#overview) |
| Smart Money | 🟡 Built, flagged OFF | Full pipeline UI: scan, terminal, rankings, profiles, config, cache — all of it still works. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#smart-money) |
| Bots | ✅ Live | Monitor / **Accounts** / Configure / Users. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#bots) |
| News Calendar | ✅ Live | tab (`/calendar`) — live Forex-Factory-style economic calendar off the free TradingView feed (`engines/news/` `TradingViewSource`, read-only, not the shared cache). Separate path from the backtest news/holiday filter. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#news-calendar) |
| Rulesets | ✅ Live | Own top-level page: firm-grouped tables, contract scaling column, editable personal rules (server-side lock on prop rows) |
| Backtests lab | ✅ Live | Runs and Sweeps tabs; BacktestDetail with collapsible params side panel |
| Optimizations | ✅ Live | Own top-level page (`/optimizations`); native NT8/MT5/Python optimizer; ranked results; "Tune winner" |
| Tuning workbench | ✅ Live | `/backtests/runs/:id/tune` — edit a winner's params, run iterations, leaderboard + deltas + regime-aware equity overlay |
| Per-platform job lock | ✅ Live | One job per platform (NT8/MT5/Python), platforms independent; DB is the single lock source (`has_running_job`) |
| Worthiness badges | ✅ Live | Tier 1/2/3 worthiness badge auto-assigned on every completed run |
| Stress Tests | ✅ Live | Monte Carlo, walk-forward, sensitivity, A–F grade with Telegram notification. MC picks its own shuffle series (dollars, or per-trade returns compounded when a run's trade size drifts) and reports drawdown in the matching unit; the grade is `None`, not D, when the ruleset states no drawdown limit. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#stress-tests) |
| Portfolio stacks | ✅ Live | Stacks tab on Backtests + `StackDetail`. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#portfolio-stacks) |
| Regime tagging (M4) | ✅ Live | Every trading day in a run's window classified once into `regime_timeline.json` (regime is a property of the market on a date, not of a run); daily PnL tagged from that same map; regime overlays and filters |
| Blocked setups | ✅ Live (Python) | **The trades that never happened.** [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#blocked-setups) |
| Missed setups | ✅ Live (Python) | **How close the setups that DIED came.** The companion of Blocked, one step earlier in a setup's life: a block is a trade the strategy had fully READY and a rule refused; a miss met some of the strategy's confluences and then died without ever becoming a trade. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#missed-setups) |
| Fibs on the chart | ✅ Live (Python) | **The fib LEG each trade was actually priced off.** Aaron's brother asked to see, on every plotted trade, the fib run on the points that trade used — which retracement levels it went into. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#fibs-on-the-chart) |
| Fair value gaps on the chart | ✅ Live (Python) | **The gaps that were live when something happened.** [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#fair-value-gaps-on-the-chart) |
| Order blocks on the chart | ✅ Live (Python) | **The supply/demand zones that were live when something happened.** Aaron's brother asked to see order blocks on the backtest chart. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#order-blocks-on-the-chart) |
| Candlestick reversals on the chart | ✅ Live (Python) | **One candle repainted navy per setup: the pattern candle that turned price.** Aaron's ask (2026-08-08) — he wants to read whether candlestick patterns line up with his reversals before deciding whether to add them as a confluence. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#candlestick-reversals-on-the-chart) |
| News & Holiday filter | ✅ Live (NT8 + Python) | Post-run view layer on BacktestDetail — a pill on the **Performance** header that drops trades in a high-impact news window and/or on a bank holiday. It **reshapes the page's REAL KPIs and Equity chart** rather than showing a second copy; both rules default OFF. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#news--holiday-filter) |
| Strategy deployment | ✅ Live | Upload, delete, compile, and one-click Deploy NT8/MT5 strategy files from the UI. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#strategy-deployment) |
| MT5 runner | ✅ Live | MT5 agent on VPS drives Strategy Tester; backtests, optimizer, walk-forward, badges |
| Python runner | ✅ Live | `services/python_runner.py` runs `strategies/python/` packages LOCALLY via the top-level `backtest/` package (no VPS, no compile). [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#python-runner) |
| Costs on a finished run | ✅ Live (Python) | **A Costs pill on BacktestDetail's Performance header that charges spread / commission / swap onto a run that already happened**, reshaping the real KPIs and the Equity chart with no re-run. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#costs-on-a-finished-run) |
| Period filter | ✅ Live | **The period chip on BacktestDetail is a control: cut a window out of a finished run and re-read the whole page on it — KPIs, equity curve, breakdown, per-regime table and price chart — with no re-run.** Dollars are rebased onto the run's own opening balance by a single scale factor, which makes it exact arithmetic and leaves every RATIO untouched; the picker says so. Refused under a firm's sizing. Rules: `frontend/CLAUDE.md` → *The period filter*. |
| Trading costs | ✅ Live (Python) | **The costs the lab KNOWS, charged in layers you tick.** Aaron's framing — *"you know what the spread is based upon your broker… the only thing we don't know is slippage"* — and bar mode was charging neither the spread nor the overnight swap. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#trading-costs) |
| History floors | ✅ Live | Backtest windows are refused (400) before the broker's real history for that timeframe. MT5 silently substitutes COARSER bars when it has none, which would produce a plausible but fictional run. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#history-floors) |
| Settings | ✅ Live | Strategy detail UX, descriptions, best-grade column, runner badges, market filter |
| Sidebar health | ✅ Live | Four live dots: API, SSH tunnel (3-state), NT8 agent (3-state), MT5 agent (3-state — agent **and** terminal) |
| Agent supervisor | ✅ Live | 60s loop keeping the tunnel and both agents up, guarded on the per-platform job lock. Replaces the one-shot startup thread; same code path on a cold start and after a laptop sleep. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#agent-supervisor) |
| Deep debug toggle | ✅ Live | One row at the top of the price chart's **Analysis** menu, on or off. [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#deep-debug-toggle) |
| Affirmation ribbon | ✅ Live | **Six affirmations rotating in the top bar, one every 20 seconds** (Aaron's wording, `components/TopBar.tsx` → `AFFIRMATIONS`). [Detail](docs/COMMAND_CENTER_BUILD_NOTES.md#affirmation-ribbon) |

---

## Sidebar health indicators

Four dots in the left sidebar, sourced from `GET /system/health` (30 s TTL cache).

| Indicator | What it checks | Green | Yellow | Red |
|---|---|---|---|---|
| **API** | Local FastAPI on `:8000` | Backend healthy | — | Unreachable — restart backend |
| **SSH** | The two LocalForwards (8765/8766) are **bound** | Tunnel up | Tunnel down, VPS reachable — the supervisor is rebuilding it | VPS unreachable — check ForexVPS or `~/.ssh/config` |
| **NT8** | Agent HTTP + NT8 running + Strategy Analyzer open | All three up | Agent up, NT8 not running or SA closed | Agent down — click to start (`NT8Agent` schtask) |
| **MT5 Agent** | `mt5_agent.py` HTTP on `:8766` **+ the terminal's own `/status`** | Agent up and MT5_Lab connected | Agent up, terminal NOT connected to the broker (open it via RDP) | Down — click to start (`MT5AgentRDP` schtask) |

NT8 and NinjaTrader were merged into one dot. Red = agent down (clickable); yellow = agent up but NT8 not running or Strategy Analyzer not open (needs RDP intervention).

⚠ **`nt8_running` and `nt8_sa_visible` are `Optional[bool]` and every check is `=== false`, never falsy (2026-08-06).** Both come off the NT8 agent's own `/nt-health`, so with the agent down the honest answer is `None` — initialising them to `False` claimed NinjaTrader was not running, which is a measurement nothing took, and it was exactly wrong on 2026-08-06: the agent was wedged and NT8 was open on the VPS. Same three-state contract as `mt5_connected`. ⚠ **The Start button on the red NT8 dot fires the `NT8Agent` schtask, which Windows REFUSES while a wedged process still holds the task** — clicking it against a wedged agent does nothing and always did; recovery is the supervisor's kill-then-refire, within a minute.

🔴 **The SSH dot did not check the tunnel until 2026-08-02, and the MT5 dot did not check the terminal.** `_check_ssh` ran `ssh forexvps "echo ok"` — a BRAND NEW connection with nothing to do with the port forwards — so after a laptop sleep the dot sat **green** beside two red agent dots, sending you to the VPS when the problem was on this laptop. `ssh_tunnel` now measures the forwards and a new `vps_reachable` carries the old question, which is what separates a dead tunnel from a dead network. Separately, `/health` on the MT5 agent answers `ok` whether or not MT5 is running or logged in, so an MT5_Lab that had dropped its broker connection showed green and every python run needing uncached bars failed at fetch time; the dot now reads `mt5_connected` off the agent's `/status`, with the account and server on the tooltip. **`mt5_connected` is `Optional[bool]` and `None` means the agent could not be asked — never render an unanswered question as a disconnected terminal.** The standing lesson is the repo's own: a label on a screen is a CLAIM about code somewhere else, and both of these were claims nothing was checking.

**Stuck progress lock** — if a run dies mid-flight (backend restart, network drop), `data/lab_progress.json` can be left with `status: running`, blocking new runs with a 409. Fix: hit the Stop button, or restart the backend (startup hook resets stale locks automatically). **Stuck stress tests** are handled separately: `reset_stale_stress_tests()` in `main.py` startup marks any `running%` stress tests and their child runs as failed on every boot. ⚠ **A stale lock now also freezes the supervisor's repair of that platform** — it refuses to restart an agent whose scope holds a running job, so an agent that died mid-submission stays down until the lock clears. The log names it (`nt8-DOWN-with-a-job-running`) rather than retrying silently.

---

## Never do

- **Reach for `test_integration.py` only when a LIVE check was actually asked for** — it submits real VPS backtests and deliberately kills a running agent. ✅ **It can no longer be run by accident (2026-08-05): `pytest.ini` carries `-m "not integration"`, so a bare `pytest tests/` DESELECTS it** (measured: 432 collected, 5 deselected), and the live suite runs only when someone asks — `pytest tests/test_integration.py -m integration`, whose command-line `-m` replaces the default. ⚠ **The old rule here was "always remember `--ignore=tests/test_integration.py`", and that is exactly the shape of rule this repo should not be writing** — the module's own docstring had said to select it explicitly since the day it was written, nothing enforced it, and the safety of a live trading box rested on a person remembering a flag. **An interlock you have to remember is not an interlock.** 🔴 **Its Case 6 ran `taskkill /f /im python.exe` on the VPS until the same day**, which kills every python process there — both backtest agents, the Telegram bot, and the LIVE TRADING BOT. There was no live bot when the test was written and there has been one since 2026-07-31; that blanket kill is what left the bot dead for three days in July. It is now a `wmic` match scoped on **both** `name='python.exe'` and the agent's own script name, the same two-clause rule `routers/bots.py::_kill_bot` documents. Recovery if an old checkout still does it: `ssh forexvps "schtasks /run /tn MT5AgentRDP"` (and `NT8Agent`), then REBUILD the SSH tunnel — the old `ssh -N -L` survives holding the ports while forwarding to a dead agent.
- **Let a unit test reach the live VPS.** ✅ **It can no longer, on either channel (2026-08-05):** `tests/conftest.py::_no_live_vps` is autouse and refuses both the agent HTTP calls and any `subprocess` that shells out to the box — an `ssh`/`scp`/`sftp` program, or any argv carrying the SSH alias, which is what catches `restart_tunnel`'s `pkill -f "ssh -N.*forexvps"` **killing the developer's own tunnel from inside a test**. A test that needs one stubs the named function (`bots._ssh`, `sup.vps_reachable`) and its patch wins. ⚠ **It raises a `BaseException`, deliberately** — every probe on this path catches `Exception` and reports the failure as "the box is down", so an `AssertionError` guard is swallowed by the exact code it polices; **measured: with one stub removed, the catchable version left 11 of 12 tests passing while every one opened a real ssh connection.** ⚠ Do not "tidy" `LiveVpsCall` into an `Exception` — a test pins that it is not one, because that edit disarms the whole suite silently
- Touch `algos/` or `smart-money/` source code — read their output files only
- Commit secrets (`.env`, credentials, tokens)
- Add a frontend route without a corresponding `NavItem` in `Sidebar.tsx` — and the reverse: never hide a nav row while leaving its route mounted. A page with no way to reach it is still reachable by URL, which is not "removed". A feature flag (`frontend/src/lib/features.ts`) must switch BOTH, in one commit
- Put a Telegram token (or any credential) in a source file. Since 2026-07-30 both sides resolve them at runtime — env var, else the git-ignored `algos/credentials.json` — through `services/notify.py` here and `algos/shared/credentials.py` there. `routers/bots.py` delegates to `services/notify.py` and must never grow its own sender again: a private copy of the token in that router is exactly how the old one ended up committed in six places. The former "keep the two constants in sync" rule is retired — there are no constants left
- Send a Telegram message from this app without a `kind`, or with `notify.TRADE`. Since 2026-08-05 a message declares what it IS and the kind picks the chat: trades in one room, everything about the machinery in another. **This backend can never legitimately send a TRADE** — only the bot on the VPS knows a fill happened — so every send here is `notify.HEALTH`, and `tests/test_notification_routing.py` refuses both mistakes by test rather than by memory
- SSH synchronously from a request handler that could take > 2s — background it
