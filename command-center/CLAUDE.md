# CLAUDE.md — Command Center

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
│   ├── data/lab.db        SQLite — strategies, firms, runs, evaluations
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

---

## Key design decisions

**Config translation layer** — Smart Money pipeline stores fractional values (`win_rate: 0.75`), UI shows percentages. `_pipeline_cfg_to_api()` and `_api_cfg_to_pipeline()` in `routers/smart_money.py` handle conversion. The API contract is the stable interface.

**Batched VPS snapshot** — `GET /bots/snapshot` makes two SSH calls and returns one `BotSnapshot`. Frontend polls at 60s. Never SSH per-bot.

**No auto-commit** — `PUT /smart-money/config` writes the file only. The user decides when to commit via `GET /smart-money/config/git-status`.

**Bot risk cap deploy** — `PATCH /bots/{name}/caps` writes `algos/shared/thresholds.json` + instance `config.json`, commits both, pushes to VPS, restarts the bot, sends Telegram notification. All in one endpoint.

**Lab experiment model** — user always specifies which firm challenges to evaluate against. The system never auto-evaluates against all firms. `evaluate_firms` is always set explicitly.

---

## What is built and live

| Module | Status |
|---|---|
| App shell — sidebar, topbar, routing | ✅ |
| Overview — stat row + Bots + Smart Money + Backtests cards | ✅ |
| Smart Money — full pipeline UI (scan, terminal, rankings, profiles, disqualified, config, cache) | ✅ |
| Bots — monitor, control (global + per-bot), configure (risk caps + deploy), users (Telegram) | ✅ |
| Backtests lab — strategies, runs, firms tabs; run modal; strategy detail; verdict pills; delete | ✅ |
| Stress Tests | 🔲 Stub |

---

## Sidebar health indicators

Five dots in the left sidebar, sourced from `GET /system/health` (30 s TTL cache).

| Indicator | What it checks | Green | Yellow | Red | Grey |
|---|---|---|---|---|---|
| **API** | Local FastAPI on `:8000` | Backend healthy | — | Backend unreachable — restart it | — |
| **SSH** | SSH tunnel to ForexVPS | Connected | — | Unreachable — check ForexVPS or `~/.ssh/config` | — |
| **VPS agent** | `vps_agent.py` HTTP on `:8765` (via SSH tunnel) | Responding | — | Not running — start it in the RDP session | — |
| **NinjaTrader** | NT8 process + Strategy Analyzer window | Running + SA open | Running, SA closed | NT8 not running on VPS | Agent unreachable |
| **NT8 compile** | C# strategy compilation result from NT8 logs | Clean | — | Compile errors in NinjaTrader — fix the strategy code | Agent unreachable |

NT8 compile = grey (unknown) when VPS Agent is red, because we can't reach NT8 to check. Only shows red when the agent is up **and** reports a compile error.

**Stuck progress lock** — if a run dies mid-flight (backend restart, network drop), `data/lab_progress.json` can be left with `status: running`, blocking new runs with a 409. Fix: hit the Stop button, or restart the backend (startup hook resets stale locks automatically).

---

## Never do

- Touch `algos/` or `smart-money/` source code — read their output files only
- Commit secrets (`.env`, credentials, tokens)
- Add a frontend route without a corresponding `NavItem` in `Sidebar.tsx`
- Change Telegram token/chat constants in `routers/bots.py` independently of `algos/shared/notify.py` — they must stay in sync
- SSH synchronously from a request handler that could take > 2s — background it
