# CLAUDE.md — Command Center Backend
## Standing Instructions for Claude Code

This file is auto-loaded by Claude Code at the start of every session.
Read it before touching any code in `backend/`.

---

## What this is

FastAPI backend for the LWG Capital command center. Serves the React frontend
on `:5173` via the Vite proxy at `/api`. Talks to:
- Local Python pipelines (smart-money) via subprocess
- The VPS via SSH (for bots) and HTTP (for vps_agent on the tunnel)
- SQLite databases under `data/` for state

Each domain (smart-money, bots, lab) is independent. They share patterns, not
tables. Touching one should not require touching another.

---

## Directory layout — where things go

```
backend/
├── main.py                ← FastAPI app entry; registers all routers
├── config.py              ← Loads config.json once at import; module constants
├── config.json            ← Machine-specific paths only — NO business config
├── models.py              ← ALL Pydantic models, one file
├── routers/               ← One file per domain — thin, no business logic
│   ├── smart_money.py
│   ├── bots.py
│   ├── backtests.py       ← Lab module — backtest runs
│   ├── strategies.py      ← Lab module — strategy registry
│   ├── firms.py           ← Lab module — prop firm rules
│   ├── system.py          ← Lab module — health + log proxies
│   ├── stress_tests.py    ← Stub until M2
│   └── settings.py
├── services/              ← Business logic, DB access, external clients
│   ├── lab_db.py          ← Only module that talks to lab.db
│   ├── strategy_scanner.py
│   ├── vps_client.py      ← Typed HTTP wrapper over vps_agent
│   ├── evaluator.py       ← Per-firm pass/fail logic
│   └── backtest_runner.py ← Background polling task
├── data/                  ← SQLite files — one per domain
│   ├── lab.db             ← Lab module (strategies, firms, runs, evals)
│   └── (smart_money.db lives in smart-money/data, not here)
└── reports/               ← Generated outputs, log files, progress.json
    └── lab/               ← Lab module outputs
```

**File-naming rule:** snake_case everywhere. Match the router prefix
(`/strategies` → `routers/strategies.py`).

---

## Router conventions

Every router file follows the same shape:

```python
from fastapi import APIRouter, HTTPException
import config as cfg
from models import ThingA, ThingB
from services import some_service

router = APIRouter(prefix="/things", tags=["things"])

@router.get("", response_model=list[ThingA])
def list_things(): ...

@router.post("", response_model=ThingA, status_code=201)
def create_thing(body: ThingCreate): ...
```

**Rules:**
- Prefix = single noun, plural where applicable (`/strategies`, `/bots`)
- Routers contain validation + status code logic ONLY
- Business logic, DB queries, subprocess calls → `services/`
- Trigger endpoints return 202 with `{run_id, status: "started"}`
- Errors → `HTTPException(status_code=..., detail=...)`, never bare `raise`
- Always set `response_model` on read endpoints — it's the API contract
- Reference the smart-money or bots router patterns; do not invent new ones

---

## Pydantic models

All models live in `models.py`. One file. Don't split it.

- snake_case fields (FastAPI auto-serializes; the frontend handles it)
- Use `Optional[X] = None` for nullable
- Use `field_validator` for constraints (see `SmartMoneyConfig` for examples)
- New models go at the bottom of the relevant section, not scattered

---

## SQLite conventions

- Raw `sqlite3` module. No SQLAlchemy, no ORM. We are not building Django.
- Each domain owns one DB file:
  - `data/lab.db` — strategies, firms, runs, evaluations
  - `smart-money/data/smart_money.db` — wallets, trades (lives in
    smart-money repo, not this backend)
- A router must NEVER access another domain's DB. Lab cannot read smart-money
  tables, even one-way. If you need cross-domain data, expose it via the other
  domain's API.
- Schemas live in their service module's `init_db()` function, run on
  startup. Idempotent — `CREATE TABLE IF NOT EXISTS`.
- All queries parameterized. Never `f"... WHERE id = '{id}'"`.
- Use `conn.row_factory = sqlite3.Row` for dict-like access.

---

## Heavy data goes on disk, not in SQLite

SQLite holds the index + summary KPIs. Big payloads (equity curves with
thousands of points, full trade lists, daily P&L arrays, log files) go in
JSON files under `reports/lab/<run_id>/`. The DB row stores the file path.

This keeps backups fast and queries snappy.

---

## VPS interaction

Two channels, used for different things:

| Channel | What it's for | How to call |
|---|---|---|
| SSH (subprocess) | File transfer, Task Scheduler control, taskkill | `subprocess.run(["ssh", cfg.SSH_ALIAS, ...])` — see `routers/bots.py` |
| HTTP (vps_agent tunnel) | Anything pywinauto / NT8 / live job control | `services/vps_client.py` — typed wrapper, always |

**Never SSH from inside a request handler if the call could take more than
~2 seconds.** Use subprocess + background task pattern (see how
`routers/smart_money.py` spawns the pipeline).

---

## Subprocess & background jobs

Smart-money's `/run` endpoint is the canonical pattern. Reuse it:

1. Validate input, check progress file for already-running state, return 409 if running.
2. `subprocess.Popen` the worker, redirect stdout/stderr to a log file.
3. Write the PID to `reports/<domain>/.pid`.
4. Return 202 immediately.
5. Worker writes `progress.json` atomically (write to `.tmp`, then `os.replace`).
6. `/progress` endpoint reads the file. Frontend polls.
7. `/stop` endpoint reads the PID file, sends SIGTERM, resets progress.

For lab backtests, the worker is the VPS agent (over HTTP). Pattern is the same:
trigger, write a progress file, frontend polls. The poller is what watches the
VPS agent.

---

## Configuration

`config.json` holds machine-specific paths and the SSH alias.
**Nothing else.** No thresholds, no business rules, no feature flags. Those
belong in the relevant domain's own config (smart-money has its own; lab will
have firm configs in the DB).

Editing config.json should never require code changes. If you find yourself
adding a non-path config field there, it belongs somewhere else.

---

## What NOT to do

- Don't hardcode paths. Everything machine-specific reads from `config.json`.
- Don't cross domains in the DB. Lab cannot SELECT from smart-money tables.
- Don't put business logic in routers. Routers are validate-and-delegate only.
- Don't make synchronous SSH calls from request handlers. Background it.
- Don't introduce an ORM, a task queue (Celery/RQ), or a new framework
  without raising it first. The current stack is intentionally minimal.
- Don't write to `progress.json` non-atomically. Always write `.tmp` and
  `os.replace`. Concurrent reads happen.
- Don't reuse the LucidFlex `backtest_config.json` — deprecated as of M1.
  All backtest configs are now per-job, sent over HTTP.
- Don't commit credentials. Telegram tokens, API keys, the works.
- Don't add a new prop firm without filling in `docs_url`. Rules drift; the
  link is how you verify the row reflects current rules. Also stamp `notes`
  with the verification date.

---

## When you add a new module

Checklist:

1. Create `routers/<thing>.py` following the established shape.
2. Create `services/<thing>_db.py` (or similar) for DB access.
3. Add Pydantic models to `models.py`.
4. Register the router in `main.py`.
5. If it has its own DB, create it under `data/` and add the schema's
   `init_db()` call to startup.
6. Update this file's directory layout section if the module adds a new
   service.

---

## When you finish a milestone

Update this file's "what this is" section to mention the new domain.
Don't leave outdated guidance.
