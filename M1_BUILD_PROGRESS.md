# M1 Foundation Build — Session Progress

**Branch:** `main`  
**Session date:** 2026-05-29  
**Spec:** `M1_Foundation_Build_Spec.md`

---

## What was built

The full M1 "lab" module for the LWG Capital Command Center — a NinjaTrader 8 backtest engine abstracted from prop firms, where firm-agnostic runs are evaluated against configurable firm profiles.

---

## §13 Build order — status

| Step | Description | Status |
|------|-------------|--------|
| 1 | Backend foundation — `lab.db` schema + seed, `models.py` refactor, strategies + firms routers | ✅ Done |
| 2 | VPS agent generalisation — job-keyed model, `/backtest`, `/nt-health`, `/nt-compile-status`, per-job results | ✅ Done |
| 3 | Backend backtest flow — `backtests.py` router, background async poller, evaluation logic | ✅ Done |
| 4 | Backend system router — `/system/health`, `/lab/progress`, `/lab/stop`, log proxies | ✅ Done |
| 5 | Frontend types + hooks — `types/index.ts` lab types, `hooks/useLab.ts` with 14 hooks | ✅ Done |
| 6 | Frontend Backtests page — sub-tabs (Runs / Strategies / Firms), verdict dots, status pills | ✅ Done |
| 7 | Frontend BacktestDetail page — eval cards, KPI grid, daily P&L chart, equity curve, logs | ✅ Done |
| 8 | Frontend RunBacktest modal — instrument, dates, auto-generated param form, firm checkboxes | ✅ Done |
| 9 | Sidebar SystemHealthStrip — 5 dots (API / SSH / Agent / NT8 / Compile) replacing 2-dot footer | ✅ Done |
| 10 | End-to-end test (§11 acceptance cases) | ⏳ Pending |

---

## Integration tests completed (gates before frontend)

**Gate C — successful run `c7afd40f5c16`:**
- Strategy: `orb_lucidflex`, Instrument: `MNQ 06-26`, 2024 full year
- Result: 469 trades, net P&L -$36,089, max DD $69,557
- All 4 evaluations correctly `DISCARD` (DD blows every firm limit)
- Funded-tier logic verified: `consistency_pass=null, target_pass=true` ✓

**Gate D — failure path `73b9b27a4fe9`:**
- Agent killed mid-run (at PCT:30)
- After 605s: `status=failed_timeout`
- `error_message: "Lost contact with VPS agent after 605s: Remote end closed connection without response"` ✓

---

## Bug fixes discovered during integration testing

| Commit | Fix |
|--------|-----|
| `d4acdbf` | pywinauto COM threading in Flask → replaced with raw ctypes `EnumWindows` |
| `a44291d` | NT8 date format: ISO `2024-01-01` → US locale `1/1/2024` |
| `d6d8718` | NT8 instrument: `MNQ 06-26` → `MNQ JUN26` |
| `ca6a752` | Stale XML false-completion → click-timestamp gate on XML file mtime |
| `ca6a752` | Run-button race: wait-for-disabled phase before wait-for-enabled |
| `e6470f7` | `max_drawdown` sign: NT8 reports negative → `abs()` in runner + evaluator |

---

## Architecture

```
Mac (localhost:8000)                     Windows VPS (RDP Session 1)
┌──────────────────────────┐             ┌────────────────────────────┐
│  FastAPI backend          │──SSH :8765──│  vps_agent.py (Flask)      │
│  ├── routers/backtests   │             │  ├── POST /backtest         │
│  ├── routers/system      │             │  ├── GET /jobs/:id/status   │
│  ├── services/evaluator  │             │  ├── GET /nt-health         │
│  ├── services/lab_db     │             │  └── GET /nt-compile-status │
│  └── data/lab.db (SQLite)│             │                             │
└──────────────────────────┘             │  vps_backtest_runner.py    │
         │                               │  └── pywinauto → NT8 SA    │
┌──────────────────────────┐             │                             │
│  React frontend (:5173)  │             │  NinjaTrader 8              │
│  ├── pages/Backtests     │             │  └── Strategy Analyzer      │
│  ├── pages/BacktestDetail│             └────────────────────────────┘
│  ├── components/         │
│  │   ├── RunBacktestModal│
│  │   └── SystemHealthStrip
│  └── hooks/useLab.ts     │
└──────────────────────────┘
```

---

## Key files changed this session

### Backend (Steps 1–4, committed in prior session)
- `command-center/backend/routers/backtests.py` — full backtest CRUD + trigger
- `command-center/backend/routers/system.py` — health + progress + log proxies
- `command-center/backend/routers/strategies.py` + `firms.py` — strategy/firm CRUD
- `command-center/backend/services/evaluator.py` — tier-aware PASS/WARN/DISCARD logic
- `command-center/backend/services/backtest_runner.py` — async poller, stall detection
- `command-center/backend/services/lab_db.py` — SQLite ops (no ORM)
- `algos/markets/futures/lucid_flex/tools/vps_agent.py` — Flask bridge, ctypes window enum
- `algos/markets/futures/lucid_flex/tools/vps_backtest_runner.py` — NT8 SA automation

### Frontend (Steps 5–9, this session)
- `command-center/frontend/src/types/index.ts` — Strategy, Firm, BacktestSummary, BacktestDetail, EvaluationDetail, LabProgress, SystemHealth types
- `command-center/frontend/src/hooks/useLab.ts` — 14 hooks covering strategies, firms, runs, progress, system health, log proxies
- `command-center/frontend/src/pages/Backtests.tsx` — rewritten: Runs/Strategies/Firms sub-tabs
- `command-center/frontend/src/pages/BacktestDetail.tsx` — eval cards, KPI grid, daily P&L + equity charts, logs
- `command-center/frontend/src/components/RunBacktestModal.tsx` — form modal with auto-generated param inputs
- `command-center/frontend/src/components/SystemHealthStrip.tsx` — 5-dot health strip
- `command-center/frontend/src/components/Sidebar.tsx` — replaced 2-dot footer with SystemHealthStrip
- `command-center/frontend/src/App.tsx` — added `/backtests/runs/:runId` route

### Deleted
- `command-center/frontend/src/hooks/useBacktests.ts` — stale scaffold stub

### Gitignore additions
- `command-center/backend/data/lab.db` (and shm/wal) — created by `init_db()` on startup
- `command-center/backend/data/lab_progress.json` — runtime state
- `command-center/backend/reports/lab/` — per-run equity curve + daily P&L JSON

---

## Data model (lab.db)

```sql
strategies       — registered NT8 strategy classes (scanned from .cs files)
firms            — prop firm profiles (seeded from bot.json)
backtest_runs    — one row per triggered run; status: running→complete|failed_*
evaluations      — one row per (run, firm); verdict: PASS|WARN|DISCARD
```

Evaluation logic:
- **Funded tier**: drawdown_pass only → PASS or DISCARD (no WARN tier)
- **Eval tier**: drawdown → target → consistency → PASS / WARN / DISCARD

---

## Remaining (Step 10)

Walk through §11 acceptance cases manually:
1. Cold start — scan → 3 strategies, 4 firms seeded
2. Trigger a run — see `running` status in Backtests Runs tab
3. Poll to completion — equity curve + daily P&L populate in BacktestDetail
4. Evaluation cards show correct verdicts per firm
5. Failure path — kill agent → `failed_timeout` with red banner + logs
6. System health strip — 5 dots reflect live VPS/NT8 state
7. Re-run from modal — prefilled instrument + params, firm selection

Requires VPS + NT8 running in RDP session with agent started from within RDP.
