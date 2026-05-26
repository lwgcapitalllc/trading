"""
Backtests router — /backtests/* (scaffold stubs)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.get("/runs")
def list_backtest_runs():
    return []


@router.get("/runs/{run_id}")
def get_backtest_run(run_id: str):
    return {"status": "not_implemented", "message": "Backtest results viewer not yet built."}


@router.post("/run", status_code=501)
def trigger_backtest(combo: Optional[str] = None):
    return {
        "status": "not_implemented",
        "message": "Backtest trigger not yet implemented.",
    }
