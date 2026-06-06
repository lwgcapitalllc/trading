# CLAUDE.md — Command Center

Local operations platform for LWG Capital. Two-process app: React frontend (`:5173`) → FastAPI backend (`:8000`). The backend is the only process that touches the filesystem or the VPS — the frontend never does.

**Last reviewed:** 2026-06-05

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

**SSH tunnel** — `start.sh` opens a persistent `ssh -N forexvps` background process on launch. This keeps two LocalForwards alive: `8765` (NT8 nt8_agent_tunnel) and `8766` (MT5 mt5_agent_tunnel). Without the tunnel, both nt8_agent_client and mt5_agent_client calls fail even though SSH itself appears healthy. The tunnel is killed automatically on Ctrl-C. **Important:** the `-L` flags must use `127.0.0.1` (not `localhost`) as the remote target — the VPS resolves `localhost` to `::1` (IPv6) but Flask agents bind only `127.0.0.1` (IPv4). Both `start.sh` and `_restart_tunnel()` in `system.py` use `127.0.0.1` explicitly.

**Auto-start agents** — `main.py` spawns a daemon thread on startup (8s delay to let the tunnel establish) that calls `/health` on each agent and fires the schtask for any that don't respond. NT8 agent: `LucidFlexAgent`. MT5 agent: `MT5AgentRDP`. If SSH is not yet up the thread silently skips — red dots remain clickable.

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

| Module | Status |
|---|---|
| App shell — sidebar, topbar, routing | ✅ |
| Overview — stat row + Bots + Smart Money + Backtests cards | ✅ |
| Smart Money — full pipeline UI (scan, terminal, rankings, profiles, disqualified, config, cache) | ✅ |
| Bots — monitor, control (global + per-bot), configure (risk caps + deploy), users (Telegram) | ✅ |
| Backtests lab — Runs / Sweeps / Optimizations tabs; run modal; BacktestDetail; verdict pills; delete | ✅ |
| Backtests lab — runs tab duration column; prominent Stop button; live log streaming (2 s poll during active runs) | ✅ |
| Backtests lab M2 — worthiness badges (Tier 1/2/3) on every completed run | ✅ |
| Backtests lab M2 — instrument sweeps (N sequential runs via SA semaphore, Sweep Detail page with live sort-by-tier) | ✅ |
| Backtests lab M2 — parameter optimizer (brute force + genetic, Optimization Detail with ranked results table, ★ best row) | ✅ |
| Backtests lab M2 — Tier 3 warning modal with smart instrument routing | ✅ |
| Backtests lab M2 — runner field on strategies; nt8_agent_client dispatcher for future MT5 support | ✅ |
| Backtests lab M2 — Sweeps tab (list view with count badge, progress, status, delete) | ✅ |
| Backtests lab M2 — Optimizations tab (delete; count badge; Runs tab nests child runs under source run via `source_run_id`) | ✅ |
| Backtests lab M2 — global NT8 SA lock: only one job type (backtest/sweep/optimization) may run at a time; 409 with clear message | ✅ |
| Backtests lab M2 — Overview Backtests card shows optimization count, Tier 1 passes, running optimization banner, best PF result | ✅ |
| Backtests lab M3 — sweep cancel endpoint + Cancel button (recovers sweeps stuck at `running` after backend restart) | ✅ |
| Backtests lab M3 — sweep retry-all + per-run retry; optimization per-run retry; `POST /backtests/runs/{id}/retry` context-aware | ✅ |
| Backtests lab M3 — SweepDetail visual parity with OptimizationDetail (ProgressCard, segmented bar, elapsed timer, status icons) | ✅ |
| Backtests lab M3 — contract month propagation fix: `withContractMonth()` in Tier3WarningModal stamps root symbols (e.g. "MNQ" → "MNQ 06-26") | ✅ |
| Backtests lab M4 — sweeps nest under source run in Runs tab (`source_run_id` on sweep child runs; `SweepNestRow` component) | ✅ |
| Backtests lab M4 — cascade delete: deleting a run also deletes linked sweeps and optimizations; warning shown before confirm | ✅ |
| Backtests lab M4 — active job indicator: pulsing dot on Runs/Sweeps/Optimizations tabs when any job is running | ✅ |
| Backtests lab M4 — header redesign: instrument chip accent-colored and first; bar/commission chips removed; chips consolidated | ✅ |
| Backtests lab M4 — log terminal success color matches SmartMoney (cyan dot + "· complete" label when run finishes) | ✅ |
| Backtests lab M4 — NT8 single-instance lock enforced in UI: all job triggers disabled with inline warning when NT8 is busy | ✅ |
| Backtests lab M4 — Runs table: "Verdicts" column renamed "Challenge", shows firm name only; "Score" column shows worthiness tier (no duplication) | ✅ |
| Stress Tests | ✅ Live | Monte Carlo (10k reshuffles + 1k bootstrap), walk-forward (N NT8 windows), sensitivity (±10%/±25% per param), A–F grade, auto-trigger on Tier 1 + optimizer winners |
| Regime Tags (M4) | ✅ Live | Every backtest's `daily_pnl` entries are tagged with a regime label (TRENDING/TRANSITIONING/RANGING/HIGH_VOLATILITY/LOW_VOLATILITY/UNKNOWN). Auto-tagged via pipeline; manual backfill via UI button. Performance by Regime table on BacktestDetail. Equity curve regime overlay (background bands + diagonal stripes for UNKNOWN). Optimizer regime filter. |
| Pass 2 — Strategy deployment | ✅ Live | Upload, delete, and compile NT8 strategy files from the UI without RDP. NT8 agent extended with file management + compile endpoints. pywinauto F5 compile via NinjaScript Editor. |
| Pass 2.5 — Strategy location + deploy button | ✅ Live | `strategies/` top-level subsystem. Files moved from `algos/`. Scanner updated. One-click Deploy button per strategy in Strategies tab. Strategies / Rulesets / Deployed nav page split from Backtests. Tab counts, platform column, trash-can delete on Deployed tab. |
| Steps 1-7 — MT5 runner | ✅ Live | `mt5_agent.py` on VPS (port 8766) — health/status, historical data, Strategy Tester driver (ini+set file, terminal64.exe, HTML report parser). `mt5_agent_client.py` on backend. `nt8_agent_client` dispatches backtests to MT5 agent when `strategy.runner == "mt5"`. `_nt8_to_mt5_spec` passes `job_id` through so MT5 agent stores job under our run_id (bug: without this, all status polls returned 404 and every run timed out). MT5 agent `POST /backtests` accepts client `job_id` if provided, else generates UUID. Timeframe mapping: M1/M5/M15/M30/H1/H4/D1. `MeanReversion.mq5` smoke-tested. |
| Step 8 — Runner badges + market filter | ✅ Live | `RunnerBadge` component shows NT8/MT5 on each strategy row. `MarketFilterBar` on Strategies and Runs tabs filters to Futures or Forex. Instrument→market mapping: MT5 runner → Forex, all others → Futures. |
| Step 9 — MT5 deployment manager | ✅ Live | Upload/delete `.mq5` files via MT5 agent. `POST /strategy-files/compile-mt5` triggers `metaeditor64.exe /compile:<experts_dir>` async; polls log for `N error(s)`. Drop zone in Deployed tab accepts `.mq5`. "Compile MT5" button (purple) appears when MT5 files are present. sync_status checks MT5 agent for `runner=mt5` strategies. |
| MT5 backtest modal | ✅ Live | `RunBacktestModal` is fully MT5-aware when `strategy.runner === 'mt5'`: free-text symbol input with preset buttons (EURUSD/GBPUSD/…), bar presets [5m/15m/30m/1h/4h] default 1h, "Evaluate Against" section hidden, "Foundational Config" section hidden, `evaluate_rulesets: []` always, no contract month, `canSubmit` requires no firm selection. NT8 modal: symbol dropdown only includes instruments from `market !== 'forex'` rulesets; "Evaluate Against" also filters to futures rulesets only; brand selection uses tabs (not radio buttons). |
| MT5 backtest detail | ✅ Live | `BacktestDetail` is MT5-aware via `runner` field on API response (`BacktestDetail` model + `_row_to_detail`): `MT5_RUN_STEPS` (Launch→Testing→Parse) vs `NT8_RUN_STEPS`; runner-aware failure messages; "Load chart data from NT8", "Refresh", and "Stress Test" buttons hidden for MT5; empty-state copy updated; `_normalize_mt5_status` returns `pct=30` + "MT5 Strategy Tester running…" while running. |
| Strategy detail UX | ✅ Live | `StrategyDetail` header: `class_name` removed from subtitle; category shown as a coloured pill badge (cyan=mean_reversion, amber=breakout, green=momentum); platform shown as 28px icon only (`/nt8-icon.png` or `/mt5-icon.png`, no text label). Editable one-line description below the badges — click to open inline input, Enter/✓ to save, Esc/✗ to cancel. Backend: `description TEXT` column added to `strategies` table via migration; `PATCH /strategies/{id}` endpoint; `useUpdateStrategyDescription` hook. Runs table: strategy name is now a clickable link → `/strategies/:id` (stops row propagation). |

---

## Sidebar health indicators

Four dots in the left sidebar, sourced from `GET /system/health` (30 s TTL cache).

| Indicator | What it checks | Green | Yellow | Red |
|---|---|---|---|---|
| **API** | Local FastAPI on `:8000` | Backend healthy | — | Unreachable — restart backend |
| **SSH** | SSH tunnel to ForexVPS | Connected | — | Unreachable — check ForexVPS or `~/.ssh/config` |
| **NT8** | Agent HTTP + NT8 running + Strategy Analyzer open | All three up | Agent up, NT8 not running or SA closed | Agent down — click to start (`LucidFlexAgent` schtask) |
| **MT5 Agent** | `mt5_agent.py` HTTP on `:8766` | Responding | — | Down — click to start (`MT5AgentRDP` schtask) |

NT8 and NinjaTrader were merged into one dot. Red = agent down (clickable); yellow = agent up but NT8 not running or Strategy Analyzer not open (needs RDP intervention).

**Stuck progress lock** — if a run dies mid-flight (backend restart, network drop), `data/lab_progress.json` can be left with `status: running`, blocking new runs with a 409. Fix: hit the Stop button, or restart the backend (startup hook resets stale locks automatically).

---

## Never do

- Touch `algos/` or `smart-money/` source code — read their output files only
- Commit secrets (`.env`, credentials, tokens)
- Add a frontend route without a corresponding `NavItem` in `Sidebar.tsx`
- Change Telegram token/chat constants in `routers/bots.py` independently of `algos/shared/notify.py` — they must stay in sync
- SSH synchronously from a request handler that could take > 2s — background it
