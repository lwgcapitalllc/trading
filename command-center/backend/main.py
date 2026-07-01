import asyncio
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import smart_money, bots, backtests, stress_tests, settings, strategies, rulesets, system, sweeps, optimizations, strategy_files, queue
from services import lab_db, runner_dispatch, mt5_agent_client
from services.backtest_runner import read_progress, clear_progress
from services import queue_runner

app = FastAPI(title="LWG Capital Command Center API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(smart_money.router)
app.include_router(bots.router)
app.include_router(backtests.router)
app.include_router(sweeps.router)
app.include_router(optimizations.router)
app.include_router(stress_tests.router)
app.include_router(settings.router)
app.include_router(strategies.router)
app.include_router(rulesets.router)
app.include_router(system.router)
app.include_router(strategy_files.router)
app.include_router(queue.router)


def _auto_start_agents():
    """Wait for the SSH tunnel then start any agents that aren't responding."""
    time.sleep(8)  # give start.sh tunnel time to establish
    for client, task in [
        (runner_dispatch, "NT8Agent"),
        (mt5_agent_client, "MT5AgentRDP"),
    ]:
        try:
            client.health()
            continue  # already up
        except Exception:
            pass
        try:
            system._schtasks_run(task)
        except Exception:
            pass  # SSH not up yet — user will see red dot and can click


@app.on_event("startup")
async def startup():
    lab_db.init_db()
    # Any "running" state left on disk is from a previous process that died.
    # The asyncio task tracking that job no longer exists, so clear the lock.
    if read_progress().get("status") == "running":
        clear_progress()
    n = lab_db.reset_stale_stress_tests()
    if n:
        import logging
        logging.getLogger(__name__).warning("Reset %d stale stress test(s) from previous run", n)
    # Orphaned 'running' backtest/optimization rows from a crashed run would otherwise
    # hold the per-platform job lock forever — the DB is now the sole lock source.
    m = lab_db.reset_stale_runs()
    if m:
        import logging
        logging.getLogger(__name__).warning("Reset %d stale backtest/optimization run(s) from previous run", m)
    threading.Thread(target=_auto_start_agents, daemon=True).start()
    asyncio.create_task(queue_runner.run_queue_loop())


@app.get("/health")
def health():
    return {"status": "ok", "service": "lwg-command-center"}
