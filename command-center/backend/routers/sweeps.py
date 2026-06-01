"""
Sweeps router — POST /backtests/sweep, GET /backtests/sweeps/:sweep_id
"""

from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response

from typing import Optional
from models import SweepRequest, SweepResponse, SweepDetail, SweepSummary, BacktestSummary, WorthinessScore
from services import lab_db
from services.sweep_runner import run_sweep, retry_failed_sweep_runs
from routers.backtests import _row_to_summary

_LAB_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"

router = APIRouter(prefix="/backtests", tags=["sweeps"])


@router.get("/sweeps", response_model=list[SweepSummary])
def list_sweeps(strategy_id: Optional[str] = None) -> list[SweepSummary]:
    rows = lab_db.list_sweeps(strategy_id=strategy_id)
    return [SweepSummary(**r) for r in rows]


@router.post("/sweep", status_code=202, response_model=SweepResponse)
async def trigger_sweep(req: SweepRequest) -> SweepResponse:
    strategy = lab_db.get_strategy(req.strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy '{req.strategy_id}' not found")

    for fid in req.firm_ids:
        if not lab_db.get_firm(fid):
            raise HTTPException(404, f"Firm '{fid}' not found")

    if not req.instruments:
        raise HTTPException(400, "instruments list cannot be empty")

    if lab_db.has_any_running_vps_job():
        raise HTTPException(409, "A backtest, sweep, or optimization is already running — wait for it to finish before starting a new sweep")

    sweep_id = "sw_" + uuid.uuid4().hex[:10]
    now      = int(time.time())
    run_specs: list[dict] = []
    job_specs: list[dict] = []
    run_ids:   list[str]  = []

    for instrument in req.instruments:
        run_id = uuid.uuid4().hex[:12]
        run_ids.append(run_id)

        lab_db.insert_run_sweep({
            "run_id":             run_id,
            "strategy_id":        req.strategy_id,
            "instrument":         instrument,
            "params":             req.params,
            "bar_type":           req.bar_type,
            "bar_value":          req.bar_value,
            "start_date":         req.start_date,
            "end_date":           req.end_date,
            "commission_per_side": req.commission_per_side,
            "slippage_ticks":     req.slippage_ticks,
            "status":             "running",
            "created_at":         now,
            "sweep_id":           sweep_id,
            "source_run_id":      req.source_run_id,
        })

        run_specs.append({
            "run_id":      run_id,
            "job_id":      run_id,
            "strategy_id": req.strategy_id,
            "instrument":  instrument,
            "firm_ids":    req.firm_ids,
            "runner":      strategy.get("runner", "ninjatrader"),
        })

        job_specs.append({
            "job_id":            run_id,
            "strategy_class":    strategy["class_name"],
            "instrument":        instrument,
            "params":            req.params,
            "bar_type":          req.bar_type,
            "bar_value":         req.bar_value,
            "start_date":        req.start_date,
            "end_date":          req.end_date,
            "commission_per_side": req.commission_per_side,
            "slippage_ticks":    req.slippage_ticks,
        })

    asyncio.create_task(run_sweep(sweep_id, run_specs, job_specs))

    return SweepResponse(sweep_id=sweep_id, run_ids=run_ids, status="started")


@router.post("/sweeps/{sweep_id}/cancel", status_code=200)
def cancel_sweep(sweep_id: str) -> dict:
    rows = lab_db.list_sweep_runs(sweep_id)
    if not rows:
        raise HTTPException(404, f"Sweep '{sweep_id}' not found")
    if not any(r["status"] == "running" for r in rows):
        raise HTTPException(400, "No running runs to cancel")
    lab_db.cancel_sweep_runs(sweep_id)
    return {"sweep_id": sweep_id, "status": "failed_cancelled"}


@router.post("/sweeps/{sweep_id}/retry-failed", status_code=202)
async def retry_sweep_failed(sweep_id: str) -> dict:
    rows = lab_db.list_sweep_runs(sweep_id)
    if not rows:
        raise HTTPException(404, f"Sweep '{sweep_id}' not found")
    if any(r["status"] == "running" for r in rows):
        raise HTTPException(409, "Sweep is still running — wait for it to finish before retrying")
    if lab_db.has_any_running_vps_job():
        raise HTTPException(409, "Another VPS job is running — wait for it to finish before retrying")
    failed = lab_db.list_sweep_failed_runs(sweep_id)
    if not failed:
        raise HTTPException(400, "No failed runs to retry")
    asyncio.create_task(retry_failed_sweep_runs(sweep_id))
    return {"sweep_id": sweep_id, "retrying": len(failed), "status": "running"}


@router.delete("/sweeps/{sweep_id}", status_code=204)
def delete_sweep(sweep_id: str) -> Response:
    rows = lab_db.list_sweep_runs(sweep_id)
    if not rows:
        raise HTTPException(404, f"Sweep '{sweep_id}' not found")
    if any(r["status"] == "running" for r in rows):
        raise HTTPException(409, "Cannot delete a running sweep — wait for it to finish first")
    deleted, child_ids = lab_db.delete_sweep(sweep_id)
    if not deleted:
        raise HTTPException(404, f"Sweep '{sweep_id}' not found")
    for run_id in child_ids:
        run_dir = _LAB_RESULTS_DIR / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
    return Response(status_code=204)


@router.get("/sweeps/{sweep_id}", response_model=SweepDetail)
def get_sweep(sweep_id: str) -> SweepDetail:
    rows = lab_db.list_sweep_runs(sweep_id)
    if not rows:
        raise HTTPException(404, f"Sweep '{sweep_id}' not found")

    first     = rows[0]
    summaries = [_row_to_summary(r) for r in rows]
    completed = sum(1 for r in rows if r["status"] == "complete")

    firm_ids = list({
        e["firm_id"]
        for r in rows
        for e in lab_db.get_run_verdict_summary(r["run_id"])
    })

    if any(r["status"] == "running" for r in rows):
        status = "running"
    elif all(r["status"] == "complete" for r in rows):
        status = "complete"
    elif all(r["status"].startswith("failed") for r in rows):
        status = "failed_cancelled" if any(r["status"] == "failed_cancelled" for r in rows) else "failed"
    else:
        status = "partial"

    created_at = datetime.fromtimestamp(min(r["created_at"] for r in rows), tz=timezone.utc)
    done_ats   = [r["completed_at"] for r in rows if r.get("completed_at")]
    completed_at = datetime.fromtimestamp(max(done_ats), tz=timezone.utc) if done_ats and status not in ("running", "partial") else None

    return SweepDetail(
        sweep_id=sweep_id,
        strategy_id=first["strategy_id"],
        strategy_name=first.get("strategy_name", ""),
        start_date=first["start_date"],
        end_date=first["end_date"],
        firm_ids=firm_ids,
        total_instruments=len(rows),
        completed_instruments=completed,
        status=status,
        created_at=created_at,
        completed_at=completed_at,
        runs=summaries,
    )
