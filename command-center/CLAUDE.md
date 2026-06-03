# CLAUDE.md — Command Center

Local operations platform for LWG Capital. Two-process app: React frontend (`:5173`) → FastAPI backend (`:8000`). The backend is the only process that touches the filesystem or the VPS — the frontend never does.

**Last reviewed:** 2026-06-03 (session 10 — M4 complete: regime classifier integration, overlay, table, optimizer filter)

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

**SSH tunnel** — `start.sh` opens a persistent `ssh -N forexvps` background process on launch. This keeps `LocalForward 8765` alive so `http://127.0.0.1:8765` (vps_agent_tunnel) is reachable for the entire session. Without this, vps_client calls fail even though SSH itself appears healthy. The tunnel is killed automatically on Ctrl-C.

**Backtesting prerequisites** — before submitting a run, the SSH tunnel and VPS agent must be up. See Sidebar health indicators below.

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
| Backtests lab — strategies, runs, rulesets tabs; run modal; strategy detail; verdict pills; delete | ✅ |
| Backtests lab — runs tab duration column; prominent Stop button; live log streaming (2 s poll during active runs) | ✅ |
| Backtests lab M2 — worthiness badges (Tier 1/2/3) on every completed run | ✅ |
| Backtests lab M2 — instrument sweeps (N sequential runs via SA semaphore, Sweep Detail page with live sort-by-tier) | ✅ |
| Backtests lab M2 — parameter optimizer (brute force + genetic, Optimization Detail with ranked results table, ★ best row) | ✅ |
| Backtests lab M2 — Tier 3 warning modal with smart instrument routing | ✅ |
| Backtests lab M2 — runner field on strategies; vps_client dispatcher for future MT5 support | ✅ |
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

---

## Sidebar health indicators

Four dots in the left sidebar, sourced from `GET /system/health` (30 s TTL cache).

| Indicator | What it checks | Green | Yellow | Red | Grey |
|---|---|---|---|---|---|
| **API** | Local FastAPI on `:8000` | Backend healthy | — | Backend unreachable — restart it | — |
| **SSH** | SSH tunnel to ForexVPS | Connected | — | Unreachable — check ForexVPS or `~/.ssh/config` | — |
| **VPS agent** | `vps_agent.py` HTTP on `:8765` (via SSH tunnel) | Responding | — | Not running — click the red dot (if SSH is up) to start via `POST /system/vps-agent/start`; or manually `ssh forexvps "schtasks /run /tn LucidFlexAgent"` | — |
| **NinjaTrader** | NT8 process + Strategy Analyzer window | Running + SA open | Running, SA closed | NT8 not running on VPS | Agent unreachable |

**Stuck progress lock** — if a run dies mid-flight (backend restart, network drop), `data/lab_progress.json` can be left with `status: running`, blocking new runs with a 409. Fix: hit the Stop button, or restart the backend (startup hook resets stale locks automatically).

---

## Never do

- Touch `algos/` or `smart-money/` source code — read their output files only
- Commit secrets (`.env`, credentials, tokens)
- Add a frontend route without a corresponding `NavItem` in `Sidebar.tsx`
- Change Telegram token/chat constants in `routers/bots.py` independently of `algos/shared/notify.py` — they must stay in sync
- SSH synchronously from a request handler that could take > 2s — background it
