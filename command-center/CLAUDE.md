# CLAUDE.md — Command Center

**Purpose:** Local operations platform for LWG Capital — a React frontend + FastAPI backend that monitors the live bots, surfaces the Smart Money pipeline, and runs/evaluates NinjaTrader + MT5 backtests.
**Scope:** This covers the command-center app (backend + frontend). Sub-directory CLAUDE.md files cover backend and frontend internals. It does NOT cover `algos/` or `smart-money/` source — those are read-only outputs to this app.
**Status:** Live — all modules shipped (Smart Money, Bots, Backtests lab, Sweeps, Optimizations, Stress Tests, MT5 runner, Python runner, portfolio stacks).
**Last reviewed:** 2026-07-25

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
| Stress Tests | ✅ Live | Monte Carlo, walk-forward, sensitivity, A–F grade with Telegram notification |
| Portfolio stacks | ✅ Live | Stacks tab on Backtests + `StackDetail`. Layer 2+ Python strategies over one shared instrument/timeframe/costs/window and read the COMBINED portfolio: the page renders like a single backtest (same KPI grid, Equity/Price/Breakdown charts, full price chart) against a client-side union of the enabled legs' trades on one account. **Smart reuse** — a leg whose exact settings already have a completed standalone run is reused instead of re-run (STRICT match); ownership ≠ membership, so a reused run stays in Runs and survives the stack's deletion. Cost defaults are 0/0 to match the Pine strategies. Per-strategy toggles drive every number and chart; the price chart names the strategy in each trade's outcome chip and has its own Strategies dropdown to isolate a leg |
| Regime tagging (M4) | ✅ Live | Every trading day in a run's window classified once into `regime_timeline.json` (regime is a property of the market on a date, not of a run); daily PnL tagged from that same map; regime overlays and filters |
| News & Holiday filter | ✅ Live (NT8) | Post-run card on BacktestDetail: removes trades in a high-impact news window (15m before/30m after, sliders) and always excludes bank holidays; KPIs + equity recompute live. Composes `engines/news/`; toggle default from the strategy's `avoid_news`. Forex/MT5 pending (TODO #3 — non-UTC broker clock) |
| Strategy deployment | ✅ Live | Upload, delete, compile, and one-click Deploy NT8/MT5 strategy files from the UI |
| MT5 runner | ✅ Live | MT5 agent on VPS drives Strategy Tester; backtests, optimizer, walk-forward, badges |
| Python runner | ✅ Live | `services/python_runner.py` runs `strategies/python/` packages LOCALLY via the top-level `backtest/` package (no VPS, no compile). Backtests + native optimizer (A4 `backtest/optimizer.py` sweep across cores). Third independent lock scope (`python`), end-to-end: `get_running_job()` returns a `python` bucket and the frontend resolves scope/market/labels through `lib/runner.ts` (**2026-07-16** — replaced the `runner === 'mt5' ? … : NT8` branching that made python jobs wear the NT8 badge and check the NT8 lock). Price charts come from the same `backtest/` bar cache the run replayed |
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
- Change Telegram token/chat constants in `routers/bots.py` independently of `algos/shared/notify.py` — they must stay in sync
- SSH synchronously from a request handler that could take > 2s — background it
