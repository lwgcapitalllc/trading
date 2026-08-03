import os
import threading
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import smart_money, bots, backtests, stress_tests, settings, strategies, rulesets, system, sweeps, stacks, optimizations, strategy_files, calendar
from services import lab_db, agent_supervisor, readiness
from services.backtest_runner import read_progress, clear_progress

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
app.include_router(stacks.router)
app.include_router(optimizations.router)
app.include_router(stress_tests.router)
app.include_router(settings.router)
app.include_router(strategies.router)
app.include_router(rulesets.router)
app.include_router(system.router)
app.include_router(strategy_files.router)
app.include_router(calendar.router)


def _supervise():
    """Keep the tunnel and both agents up, for the whole life of the process.

    This replaced a ONE-SHOT thread (`_auto_start_agents`) that ran 8 seconds
    after boot and never again. It worked on a cold start and did nothing for
    every case after it — close the laptop, the tunnel dies, come back, and the
    agents had to be started by hand. There is no separate startup path now: the
    first pass is the same pass as every later one, so "it works on launch" and
    "it recovers from sleep" cannot diverge.

    The 8s delay survives for the same reason it existed — start.sh opens the
    tunnel in parallel with this process, and probing before it is up would fire
    two scheduled tasks for agents that are perfectly fine.
    """
    time.sleep(8)
    agent_supervisor.run_forever()


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
    # Dependencies that fail SILENTLY — an un-backfilled news calendar, missing
    # Telegram credentials. Reported, never repaired: neither can be fixed from
    # here, and neither is worth refusing to boot over.
    readiness.report()
    # ⚠ OFF under pytest, and the guard is not optional. Every endpoint test
    # builds a TestClient, which fires this startup hook — so without it a
    # `pytest tests/` on a laptop whose tunnel happened to be down would rebuild
    # the tunnel and fire two scheduled tasks on the live VPS. Same class of
    # hazard as tests/test_integration.py, which is why it is refused by
    # default rather than mocked per-test.
    if os.getenv("CC_DISABLE_SUPERVISOR") != "1":
        threading.Thread(target=_supervise, daemon=True, name="agent-supervisor-boot").start()


@app.get("/health")
def health():
    return {"status": "ok", "service": "lwg-command-center"}
