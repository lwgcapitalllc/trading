"""
Shared fixtures for the lab test suite.

DB isolation: every test gets a fresh SQLite DB via monkeypatching lab_db.DB_PATH
to a temp path before any lab_db function runs.

VPS isolation: client fixture stubs out all nt8_agent_client calls and the async
background job (run_backtest_job), so unit tests never open network connections.
"""

import time
import pytest
from unittest.mock import patch, AsyncMock


# ── DB isolation ──────────────────────────────────────────────────────────────

@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """
    Patches lab_db.DB_PATH to a temp file and calls init_db().
    All fixtures that depend on this share the same temp DB within one test.
    """
    from services import lab_db
    db = tmp_path / "lab.db"
    monkeypatch.setattr(lab_db, "DB_PATH", db)
    lab_db.init_db()
    return db


# ── API client ────────────────────────────────────────────────────────────────

@pytest.fixture
def client(fresh_db):
    """
    FastAPI TestClient with:
    - isolated DB (via fresh_db)
    - all outbound VPS calls stubbed
    - background backtest job mocked (no-op AsyncMock)

    Use this for all endpoint tests. Tests that only need the service layer
    directly can use fresh_db + seeded_run without this fixture.
    """
    from main import app
    from fastapi.testclient import TestClient

    with (
        patch("services.nt8_agent_client.start_backtest", return_value={"status": "ok"}),
        patch("services.nt8_agent_client.job_log", return_value=""),
        patch("services.nt8_agent_client.health", return_value={"status": "ok"}),
        patch("routers.backtests.run_backtest_job", new_callable=AsyncMock),
        patch("routers.backtests.read_progress", return_value={"status": "idle", "pct": 0}),
    ):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


# ── Seeded data helpers ───────────────────────────────────────────────────────

def _insert_strategy(lab_db):
    lab_db.upsert_strategy({
        "id": "test_strategy",
        "name": "Test Strategy",
        "class_name": "TestStrategy",
        "source_path": "test/TestStrategy.cs",
        "scanned_at": int(time.time()),
        "default_params": {},
        "param_schema": [],
    })
    return "test_strategy"


@pytest.fixture
def seeded_run(fresh_db):
    """
    Seeds a minimal strategy + a completed run with known KPIs.
    net_pnl=4000, max_drawdown=1500, no equity/daily_pnl files.

    Used by evaluator unit tests and reevaluate endpoint tests.
    """
    from services import lab_db

    strategy_id = _insert_strategy(lab_db)
    run_id = "testrun12abc"

    lab_db.insert_run({
        "run_id": run_id,
        "strategy_id": strategy_id,
        "instrument": "MNQ 06-26",
        "params": {},
        "bar_type": "Minute",
        "bar_value": 5,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "commission_per_side": 0.50,
        "slippage_ticks": 1,
        "status": "running",
        "created_at": int(time.time()),
    })
    lab_db.update_run_complete(run_id, {
        "net_pnl": 4000.0,
        "max_drawdown": 1500.0,
        "profit_factor": 1.8,
        "win_rate": 0.55,
        "win_count": 80,
        "trade_count": 145,
        "sharpe": 1.2,
        "sortino": 1.5,
        "cagr": 0.22,
        "avg_win": 120.0,
        "avg_loss": -85.0,
        "avg_trade_duration_min": 43.0,
        "worst_day_pnl": -400.0,
        "worst_losing_streak": 5,
    }, {})
    return run_id
