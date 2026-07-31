# CLAUDE.md — Command Center

**Purpose:** Local operations platform for LWG Capital — a React frontend + FastAPI backend that monitors the live bots, surfaces the Smart Money pipeline, and runs/evaluates NinjaTrader + MT5 backtests.
**Scope:** This covers the command-center app (backend + frontend). Sub-directory CLAUDE.md files cover backend and frontend internals. It does NOT cover `algos/` or `smart-money/` source — those are read-only outputs to this app.
**Status:** Live — all modules shipped (Smart Money, Bots, Backtests lab, Sweeps, Optimizations, Stress Tests, MT5 runner, Python runner, portfolio stacks).
**Last reviewed:** 2026-07-30 — **the drawdown defect turned up a THIRD time, now in the KPI grid.** `BacktestDetail`'s Max Drawdown and Calmar both divided by the ruleset's static `account_size`, so on a compounding run they reported a percentage of an account that had ceased to exist: the shipped `mpc_sos_fade` run printed **Max DD 1096.7%** and a red **Calmar 0.11** where the honest figures are **54.9%** and **2.25** — two of the six core cards arguing a good strategy was bad. Both now divide by the running PEAK (`frontend/CLAUDE.md` → *Drawdown is peak-relative*), and the card learned that the deepest DOLLAR drawdown is a different episode from the worst PERCENTAGE one. Standing lesson: a percent of a growing account needs a growing denominator — check every place one is computed. Same day: the price chart's **scroll-left paging now shows itself** (the blank strip you scroll into is shaded from the oldest loaded bar back and labelled `Loading earlier bars…`), and **the stress-test engine's accuracy pass.** A D grade traced to the engine, not the strategy: Monte Carlo was shuffling dollar P&L on a compounding run (trade size drifts 17.7x, so it simulated a strategy that never existed), drawdown was compared in dollars against a fixed limit while the account grew, sensitivity scored on net P&L so a position-SIZE knob dominated the score, walk-forward averaged Sharpes off 6-trade windows, and a ruleset stating no drawdown limit could not grade above **D**. All five fixed generically; a `None` grade is now a first-class outcome and `personal_forex_risk` (55%) was seeded as the forex bar. Detail + the ruin walk-back in `backend/CLAUDE.md` → *How stress tests work* / *Robustness grading*. Earlier: 2026-07-29 — the price chart's fib levels became configurable (add/remove/retune/recolour/hide a level, per drawing or as the tool's persisted default, extensions included); the News & Holiday filter works end to end (calendar backfilled 2021→2026, `entry_ms` reaching the frontend, one Equity chart that follows the filter); 2026-07-28 — the price chart got a Go-to-date jump (type a date, it pages the history in and lands there); 2026-07-27 — missed setups (how close the ones that died came) shipped end to end alongside blocked setups; the price chart now opens on the timeframe the run traded

Local operations platform for LWG Capital. Two-process app: React frontend (`:5173`) → FastAPI backend (`:8000`). The backend is the only process that touches the filesystem or the VPS — the frontend never does.

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

**SSH tunnel** — `start.sh` opens a persistent `ssh -N forexvps` background process on launch. This keeps two LocalForwards alive: `8765` (NT8 nt8_agent_tunnel) and `8766` (MT5 mt5_agent_tunnel). Without the tunnel, both runner_dispatch and mt5_agent_client calls fail even though SSH itself appears healthy. The tunnel is killed automatically on Ctrl-C. **Important:** the `-L` flags must use `127.0.0.1` (not `localhost`) as the remote target — the VPS resolves `localhost` to `::1` (IPv6) but Flask agents bind only `127.0.0.1` (IPv4). Both `start.sh` and `_restart_tunnel()` in `system.py` use `127.0.0.1` explicitly.

**Auto-start agents** — `main.py` spawns a daemon thread on startup (8s delay to let the tunnel establish) that calls `/health` on each agent and fires the schtask for any that don't respond. NT8 agent: `NT8Agent`. MT5 agent: `MT5AgentRDP`. If SSH is not yet up the thread silently skips — red dots remain clickable.

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

| Module | Status | What it does |
|---|---|---|
| App shell | ✅ Live | Sidebar, topbar, routing across all pages |
| Overview | ✅ Live | Stat row plus Bots, Smart Money, and Backtests summary cards |
| Smart Money | ✅ Live | Full pipeline UI: scan, terminal, rankings, profiles, config, cache |
| Bots | ✅ Live | Monitor/control scaffold; no bots registered yet (all four first-attempt bots deleted 2026-06-22). Configure risk caps and deploy, manage Telegram users |
| News Calendar | ✅ Live | tab (`/calendar`) — live Forex-Factory-style economic calendar off the free TradingView feed (`engines/news/` `TradingViewSource`, read-only, not the shared cache). Day strip, server-clock "now" line + countdown, actual/forecast/previous w/ beat-miss colour, currency/impact/category filters. Separate path from the backtest news/holiday filter |
| Rulesets | ✅ Live | Own top-level page: firm-grouped tables, contract scaling column, editable personal rules (server-side lock on prop rows) |
| Backtests lab | ✅ Live | Runs and Sweeps tabs; BacktestDetail with collapsible params side panel |
| Optimizations | ✅ Live | Own top-level page (`/optimizations`); native NT8/MT5/Python optimizer; ranked results; "Tune winner" |
| Tuning workbench | ✅ Live | `/backtests/runs/:id/tune` — edit a winner's params, run iterations, leaderboard + deltas + regime-aware equity overlay |
| Per-platform job lock | ✅ Live | One job per platform (NT8/MT5/Python), platforms independent; DB is the single lock source (`has_running_job`) |
| Worthiness badges | ✅ Live | Tier 1/2/3 worthiness badge auto-assigned on every completed run |
| Stress Tests | ✅ Live | Monte Carlo, walk-forward, sensitivity, A–F grade with Telegram notification. MC picks its own shuffle series (dollars, or per-trade returns compounded when a run's trade size drifts) and reports drawdown in the matching unit; the grade is `None`, not D, when the ruleset states no drawdown limit |
| Portfolio stacks | ✅ Live | Stacks tab on Backtests + `StackDetail`. Layer 2+ Python strategies over one shared instrument/timeframe/costs/window and read the COMBINED portfolio: the page renders like a single backtest (same KPI grid, Equity/Price/Breakdown charts, full price chart) against a client-side union of the enabled legs' trades on one account. **Smart reuse** — a leg whose exact settings already have a completed standalone run is reused instead of re-run (STRICT match); ownership ≠ membership, so a reused run stays in Runs and survives the stack's deletion. Cost defaults are 0/0 to match the Pine strategies. Per-strategy toggles drive every number and chart; the price chart names the strategy in each trade's outcome chip and has its own Strategies dropdown to isolate a leg. A stack can be started from EITHER the Stacks tab or the Strategies page (tick 2+ python rows → Stack N strategies), both opening the same config modal. **The stack opens on the legs' SHARED balance, not the sum** (2026-07-25 fix — two $10k legs were starting the portfolio at $20k and halving every balance-relative KPI). **This is a SCREEN, not a simulation:** each leg was sized as if it owned the whole account, so no leg ever blocks another and the stack OVERSTATES the result. The shared-risk simulator that fixes that (`backtest/portfolio/`, built, unwired) is specced in `docs/SHARED_RISK_STACK.md` |
| Regime tagging (M4) | ✅ Live | Every trading day in a run's window classified once into `regime_timeline.json` (regime is a property of the market on a date, not of a run); daily PnL tagged from that same map; regime overlays and filters |
| Blocked setups | ✅ Live (Python) | **The trades that never happened.** A signal the strategy had READY that one of its OWN rules refused places no order, so it is in no trade list, no equity curve and no broker report — this is the only place it is countable, and without it there is no way to judge whether a blocking rule protects the account or costs it. Port of `mpc_strategy.pine`'s pink TRADE BLOCKED tag: the strategy records each refusal (reporting-only, parity-safe) → `backtest/output.py` → `blocked_setups.json` in the run dir → the price chart's **Analysis → Blocked** layer (default OFF), where each draws a dashed line at the exact would-be entry price with every refusing rule on hover, filterable by reason. Python runner only — NT8/MT5 cannot report them, and the layer correctly does not appear for them. Full path: `backend/CLAUDE.md` → *Blocked setups* |
| Missed setups | ✅ Live (Python) | **How close the setups that DIED came.** The companion of Blocked, one step earlier in a setup's life: a block is a trade the strategy had fully READY and a rule refused; a miss met some of the strategy's confluences and then died without ever becoming a trade. Port of `mpc_strategy.pine`'s orange 2-of-3 callout: same path as the blocks (strategy → `backtest/output.py` → `missed_setups.json` → the price chart's **Analysis → Missed** layer, default OFF), with the SCORE on the tag (`2/3` / `3/3`) and hover showing what it had vs the one thing it didn't. The routine reasons start unticked, driven by a `missNoise` list the backend DERIVES from the strategy's own near-miss flag — so the layer opens on the misses worth studying without the chart learning what any of them mean. Full path: `backend/CLAUDE.md` → *Missed setups* |
| News & Holiday filter | ✅ Live (NT8 + Python) | Post-run view layer on BacktestDetail — a pill on the **Performance** header that removes trades in a high-impact news window and/or on a bank holiday, and **reshapes the page's REAL 12 KPIs plus the Equity chart** rather than showing a second copy of them (the duplicate tiles and the filter's own section were both removed 2026-07-30). Two rules, both switchable, holidays ticked by default; each card's caption becomes its delta vs unfiltered. Composes `engines/news/`; news default from the strategy's `avoid_news`. What deliberately does NOT follow it — per-firm sized runs, the firm verdict, `platform_sharpe` — is in `frontend/CLAUDE.md` → *The News & Holiday filter*. **Inert until the calendar months are backfilled** — the cache is git-ignored, so backfill per machine. Forex/MT5 pending (TODO #3 — non-UTC broker clock) |
| Strategy deployment | ✅ Live | Upload, delete, compile, and one-click Deploy NT8/MT5 strategy files from the UI |
| MT5 runner | ✅ Live | MT5 agent on VPS drives Strategy Tester; backtests, optimizer, walk-forward, badges |
| Python runner | ✅ Live | `services/python_runner.py` runs `strategies/python/` packages LOCALLY via the top-level `backtest/` package (no VPS, no compile). Backtests + native optimizer (A4 `backtest/optimizer.py` sweep across cores). Third independent lock scope (`python`), end-to-end: `get_running_job()` returns a `python` bucket and the frontend resolves scope/market/labels through `lib/runner.ts` (**2026-07-16** — replaced the `runner === 'mt5' ? … : NT8` branching that made python jobs wear the NT8 badge and check the NT8 lock). Price charts come from the same `backtest/` bar cache the run replayed |
| History floors | ✅ Live | Backtest windows are refused (400) before the broker's real history for that timeframe. MT5 silently substitutes COARSER bars when it has none, which would produce a plausible but fictional run. The floor is MEASURED off the live terminal (bar-density probe, cached per broker) via the canonical `backtest/data/history.py` — swap brokers and it re-measures rather than inheriting. Enforced at run/retry/sweep/optimization/stack and in `BarSource.load`; the date picker's minimum reads `GET /backtests/history-limit`. Python runner only (NT8/MT5 use their own terminals' history) |
| Settings | ✅ Live | Strategy detail UX, descriptions, best-grade column, runner badges, market filter |
| Sidebar health | ✅ Live | Four live dots: API, SSH tunnel, NT8 agent, MT5 agent |

---

## Sidebar health indicators

Four dots in the left sidebar, sourced from `GET /system/health` (30 s TTL cache).

| Indicator | What it checks | Green | Yellow | Red |
|---|---|---|---|---|
| **API** | Local FastAPI on `:8000` | Backend healthy | — | Unreachable — restart backend |
| **SSH** | SSH tunnel to ForexVPS | Connected | — | Unreachable — check ForexVPS or `~/.ssh/config` |
| **NT8** | Agent HTTP + NT8 running + Strategy Analyzer open | All three up | Agent up, NT8 not running or SA closed | Agent down — click to start (`NT8Agent` schtask) |
| **MT5 Agent** | `mt5_agent.py` HTTP on `:8766` | Responding | — | Down — click to start (`MT5AgentRDP` schtask) |

NT8 and NinjaTrader were merged into one dot. Red = agent down (clickable); yellow = agent up but NT8 not running or Strategy Analyzer not open (needs RDP intervention).

**Stuck progress lock** — if a run dies mid-flight (backend restart, network drop), `data/lab_progress.json` can be left with `status: running`, blocking new runs with a 409. Fix: hit the Stop button, or restart the backend (startup hook resets stale locks automatically). **Stuck stress tests** are handled separately: `reset_stale_stress_tests()` in `main.py` startup marks any `running%` stress tests and their child runs as failed on every boot.

---

## Never do

- **Never run a bare `pytest tests/` in `backend/`** — it includes `tests/test_integration.py`, a LIVE suite that submits a real VPS backtest and runs `taskkill /f /im python.exe` on the VPS, which kills BOTH backtest agents (NT8 + MT5) and any in-flight tick-mode backtest. Always `pytest tests/ --ignore=tests/test_integration.py` (or name specific files). The tell you're about to make the mistake: the full suite takes ~15min vs ~5s without integration. Recovery if it happens: `ssh forexvps "schtasks /run /tn MT5AgentRDP"` (and `NT8Agent`), then REBUILD the SSH tunnel (the old `ssh -N -L` survives holding the ports while forwarding to a dead agent). Only run `test_integration.py` when explicitly asked for a live check.
- Touch `algos/` or `smart-money/` source code — read their output files only
- Commit secrets (`.env`, credentials, tokens)
- Add a frontend route without a corresponding `NavItem` in `Sidebar.tsx`
- Put a Telegram token (or any credential) in a source file. Since 2026-07-30 both sides resolve them at runtime — env var, else the git-ignored `algos/credentials.json` — through `services/notify.py` here and `algos/shared/credentials.py` there. `routers/bots.py` delegates to `services/notify.py` and must never grow its own sender again: a private copy of the token in that router is exactly how the old one ended up committed in six places. The former "keep the two constants in sync" rule is retired — there are no constants left
- SSH synchronously from a request handler that could take > 2s — background it
