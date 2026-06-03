from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import smart_money, bots, backtests, stress_tests, settings, strategies, firms, rulesets, system, sweeps, optimizations, strategy_files
from services import lab_db
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
app.include_router(optimizations.router)
app.include_router(stress_tests.router)
app.include_router(settings.router)
app.include_router(strategies.router)
app.include_router(rulesets.router)
app.include_router(firms.router)          # backward-compat redirect — deprecated in M3
app.include_router(system.router)
app.include_router(strategy_files.router)


@app.on_event("startup")
def startup():
    lab_db.init_db()
    # Any "running" state left on disk is from a previous process that died.
    # The asyncio task tracking that job no longer exists, so clear the lock.
    if read_progress().get("status") == "running":
        clear_progress()


@app.get("/health")
def health():
    return {"status": "ok", "service": "lwg-command-center"}
