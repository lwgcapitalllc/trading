# CLAUDE.md — Command Center

Local operations platform for LWG Capital. Two-process app: React frontend (`:5173`) → FastAPI backend (`:8000`). The backend is the only process that touches the filesystem or the VPS — the frontend never does.

```
command-center/
├── backend/          FastAPI + Pydantic v2, Python 3.9
│   ├── main.py
│   ├── config.py     loads config.json → typed constants
│   ├── config.json   absolute paths to smart-money and algos on this machine
│   ├── models.py     all Pydantic models (shared data contracts)
│   └── routers/
│       ├── smart_money.py
│       ├── bots.py
│       ├── backtests.py     stub
│       ├── stress_tests.py  stub
│       └── settings.py
├── frontend/         Vite + React 18 + TypeScript + Tailwind + TanStack Query
│   └── src/
│       ├── api/client.ts       all fetch goes through here (prefix /api → :8000)
│       ├── types/index.ts      mirrors all Pydantic models exactly
│       ├── hooks/              one file per backend module
│       ├── components/         Sidebar, TopBar, StatCard, ScaffoldBanner, EmptyState
│       └── pages/
│           ├── SmartMoney/     PoolOverview, Rankings, CandidateProfile, DisqualifiedLog, Config
│           ├── Bots/           monitoring table, scheduled jobs, log viewer
│           ├── Overview.tsx    scaffold
│           ├── Backtests.tsx   scaffold
│           ├── StressTests.tsx scaffold
│           └── Settings.tsx    scaffold
├── design/
│   ├── prototype.html          interactive visual spec — open in browser, no build step
│   ├── README.md               theme reference (Refined dark, teal accent, gold secondary)
│   └── LWG_Capital_Command_Center_Build_Spec.md   full architectural spec
└── start.sh          starts both processes; ./start.sh from this dir
```

---

## How to run

```bash
cd command-center
./start.sh
# Frontend: http://localhost:5173
# Backend:  http://localhost:8000/docs
```

`start.sh` creates the Python venv and runs `npm install` on first launch.

---

## Key design decisions

**Config translation layer** — the Smart Money pipeline stores fractional values (`win_rate: 0.75`) but the UI shows percentages (`75.0`). `_pipeline_cfg_to_api()` and `_api_cfg_to_pipeline()` in `routers/smart_money.py` handle bidirectional conversion. The API contract (percentages, flat keys) is the stable interface; if the pipeline changes its format, only the translation functions change.

**Batched VPS snapshot** — `GET /bots/snapshot` makes two SSH calls (replicating algo.py's `fetch_vps_snapshot()` exactly) and returns a single `BotSnapshot`. The frontend polls this at 60s. Never SSH per-bot.

**Bot control actions are 501 stubs** — `POST /bots/start|stop|restart|emergency` all return 501 with an explanatory message. This is deliberate: monitoring must be verified against the live VPS before controls are enabled. Do not implement these until `/bots/snapshot` has been validated in production.

**No auto-commit** — `PUT /smart-money/config` writes the file only. `GET /smart-money/config/git-status` shows dirty state. The user decides when to commit.

---

## What is built and live

| Module | Status | Notes |
|---|---|---|
| App shell (sidebar, topbar, routing) | ✅ Live | All 6 routes |
| Smart Money — Config | ✅ Live | Reads/writes `smart-money/config/config.json` |
| Smart Money — Pool Overview | ✅ Live (UI) | Needs pipeline run output to show real data |
| Smart Money — Rankings | ✅ Live (UI) | Needs pipeline run output |
| Smart Money — Candidate Profile | ✅ Live (UI) | Needs pipeline run output |
| Smart Money — Disqualified Log | ✅ Live (UI) | Needs pipeline run output |
| Bots — monitoring table | ✅ Live (UI) | Needs VPS SSH verification |
| Bots — scheduled jobs | ✅ Live (UI) | Needs VPS SSH verification |
| Bots — log viewer | ✅ Live (UI) | Needs VPS SSH verification |

---

## What still needs to be done

### Step 4 — Verify Smart Money file-reading against real pipeline output
`GET /smart-money/runs*` reads `smart-money/reports/{run_id}/full_report.json` and `disqualified.json`. The file-reading logic is written. It needs a real pipeline run to test against. Run the pipeline, then open the Rankings and Pool Overview views and confirm the data displays correctly. If the pipeline output format differs from the `SmartMoneyRun` model, update the translation layer — not the pipeline.

Expected directory shape:
```
smart-money/reports/
└── {YYYY-MM-DD_HHmmss}/
    ├── full_report.json      → SmartMoneyRun model
    └── disqualified.json     → list of DisqualifiedCandidate
```

### Step 5 — Verify Bots monitoring against live VPS
`GET /bots/snapshot` makes two SSH calls to `forexvps`. Verify:
- The wmic + schtasks parsing matches what the VPS actually returns
- `bot_state.json` exists at `C:\trading\algos\markets\fx\instances\{bot_name}\bot_state.json`
- The `BotSnapshot` response populates correctly in the UI

### Step 6 — Overview page
Currently a scaffold. Should show a combined summary: bots running, SM pool size, recent pipeline run, last backtest. Pulls from existing endpoints — no new backend work needed.

### Step 7 — Enable bot control actions
Only after Step 5 is verified. Implement `POST /bots/start|stop|restart` in `routers/bots.py` using SSH calls mirroring CLAUDE.md's VPS deploy workflow. Keep Emergency Stop as last to implement. Remove `ScaffoldBanner` from Bots page and enable the control buttons when controls are live.

### Step 8 — Backtests module
Backend: `GET /backtests/runs` reads from `algos/` backtest output directory (TBD). Frontend `src/pages/Backtests.tsx` is scaffolded. See `design/LWG_Capital_Command_Center_Build_Spec.md` section 7 for the full spec.

### Step 9 — Stress Tests module
Backend: `GET /stress-tests/results` reads stress test output (TBD). Frontend `src/pages/StressTests.tsx` is scaffolded.

---

## Never do

- Touch `algos/` or `smart-money/` source code from within this subsystem — read their output files only
- Implement bot control actions before monitoring is verified (Steps 4–5 first)
- Commit secrets: `config.json` contains local paths only (no credentials), but `.env` or any credential files must never be committed
- Add frontend routes without adding the corresponding `ROUTE_LABELS` entry in `TopBar.tsx`
