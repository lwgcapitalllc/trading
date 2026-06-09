"""
Optimizations router — /optimizations/*
"""

from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import PlainTextResponse

from models import (
    OptimizationRequest, OptimizationSummary, OptimizationDetail,
)
from services import lab_db, nt8_agent_client
from services.optimization_runner import expand_grid, pick_search_method, sample_combinations, run_optimization, retry_failed_runs
from routers.backtests import _row_to_summary

router = APIRouter(prefix="/optimizations", tags=["optimizations"])

_LAB_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"


@router.post("/run", status_code=202)
async def trigger_optimization(req: OptimizationRequest) -> dict:
    strategy = lab_db.get_strategy(req.strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy '{req.strategy_id}' not found")

    if req.ruleset_id:
        if not lab_db.get_ruleset(req.ruleset_id):
            raise HTTPException(404, f"Ruleset '{req.ruleset_id}' not found")

    if not req.param_grid:
        raise HTTPException(400, "param_grid cannot be empty")

    runner = strategy.get("runner", "ninjatrader")

    if runner == "mt5":
        if lab_db.has_running_mt5_job():
            raise HTTPException(409, "An MT5 job is already running — wait for it to finish")
    else:
        if lab_db.has_running_nt8_job():
            raise HTTPException(409, "An NT8 job is already running — wait for it to finish before starting a new optimization")

    method = pick_search_method(req.param_grid, req.search_method)
    all_combos = expand_grid(req.param_grid)
    sampled    = sample_combinations(all_combos, method)
    estimated  = len(sampled)

    opt_id = "opt_" + uuid.uuid4().hex[:10]

    lab_db.insert_optimization({
        "optimization_id":    opt_id,
        "strategy_id":        req.strategy_id,
        "instrument":         req.instrument,
        "start_date":         req.start_date,
        "end_date":           req.end_date,
        "commission_per_side": req.commission_per_side,
        "slippage_ticks":     req.slippage_ticks,
        "ruleset_id":         req.ruleset_id,
        "mode":               req.mode,
        "search_method":      method,
        "param_grid":         req.param_grid,
        "status":             "running",
        "estimated_runs":     estimated,
        "source_run_id":      req.source_run_id,
        "regime_filter":      req.regime_filter,
        "bar_type":           req.bar_type,
        "bar_value":          req.bar_value,
    })

    asyncio.create_task(run_optimization(opt_id))

    return {
        "optimization_id": opt_id,
        "status":          "started",
        "estimated_runs":  estimated,
    }


@router.get("", response_model=list[OptimizationSummary])
def list_optimizations(strategy_id: Optional[str] = None) -> list[OptimizationSummary]:
    rows = lab_db.list_optimizations(strategy_id=strategy_id)
    return [_row_to_opt_summary(r) for r in rows]


@router.get("/{optimization_id}", response_model=OptimizationDetail)
def get_optimization(optimization_id: str) -> OptimizationDetail:
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        raise HTTPException(404, "Optimization not found")

    strategy = lab_db.get_strategy(opt["strategy_id"])
    run_rows  = lab_db.list_optimization_runs(optimization_id)
    summaries = [_row_to_summary(r) for r in run_rows]

    live_pct     = None
    live_message = None
    if opt["status"] == "running":
        try:
            runner_str  = (strategy or {}).get("runner", "ninjatrader")
            status_data = nt8_agent_client.job_status(f"nopt_{optimization_id}", runner_str)
            live_pct     = int(status_data.get("pct") or 0) or None
            live_message = status_data.get("message") or None
        except Exception:
            pass

    return OptimizationDetail(
        optimization_id=opt["optimization_id"],
        strategy_id=opt["strategy_id"],
        strategy_name=strategy["name"] if strategy else opt["strategy_id"],
        instrument=opt["instrument"],
        start_date=opt["start_date"],
        end_date=opt["end_date"],
        ruleset_id=opt["ruleset_id"],
        mode=opt["mode"],
        search_method=opt["search_method"],
        param_grid=opt["param_grid"],
        status=opt["status"],
        estimated_runs=opt["estimated_runs"],
        completed_runs=opt["completed_runs"],
        best_run_id=opt.get("best_run_id"),
        regime_filter=opt.get("regime_filter"),
        runner=(strategy or {}).get("runner", "ninjatrader"),
        created_at=opt["created_at"],
        completed_at=opt.get("completed_at"),
        runs=summaries,
        live_pct=live_pct,
        live_message=live_message,
    )


@router.delete("/{optimization_id}", status_code=204)
def delete_optimization(optimization_id: str) -> Response:
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        raise HTTPException(404, "Optimization not found")
    if opt["status"] == "running":
        raise HTTPException(409, "Cannot delete a running optimization — cancel it first")
    deleted, child_ids = lab_db.delete_optimization(optimization_id)
    if not deleted:
        raise HTTPException(404, "Optimization not found")
    for run_id in child_ids:
        run_dir = _LAB_RESULTS_DIR / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
    return Response(status_code=204)


@router.post("/{optimization_id}/cancel", status_code=200)
def cancel_optimization(optimization_id: str) -> dict:
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        raise HTTPException(404, "Optimization not found")
    if opt["status"] not in ("running",):
        raise HTTPException(400, f"Optimization is not running (status: {opt['status']})")
    lab_db.cancel_optimization(optimization_id)
    return {"optimization_id": optimization_id, "status": "failed_cancelled"}


@router.post("/{optimization_id}/retry-failed", status_code=202)
async def retry_optimization_failed(optimization_id: str) -> dict:
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        raise HTTPException(404, "Optimization not found")
    failed = lab_db.list_optimization_failed_runs(optimization_id)
    if not failed:
        raise HTTPException(400, "No failed runs to retry")
    asyncio.create_task(retry_failed_runs(optimization_id))
    return {"optimization_id": optimization_id, "retrying": len(failed), "status": "running"}


@router.get("/{optimization_id}/log", response_class=PlainTextResponse)
def get_optimization_log(optimization_id: str, lines: int = 300) -> str:
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        raise HTTPException(404, "Optimization not found")
    strategy = lab_db.get_strategy(opt["strategy_id"])
    runner = (strategy or {}).get("runner", "ninjatrader")
    job_id = f"nopt_{optimization_id}"

    live = nt8_agent_client.job_log(job_id, lines=lines, runner=runner)
    if live:
        return live

    # Agent has no record (restarted) — serve the saved log file if it exists
    saved = _LAB_RESULTS_DIR / optimization_id / "opt_log.txt"
    if saved.is_file():
        text = saved.read_text(encoding="utf-8", errors="replace")
        return "\n".join(text.splitlines()[-lines:])
    return ""


def _row_to_opt_summary(row: dict) -> OptimizationSummary:
    return OptimizationSummary(
        optimization_id=row["optimization_id"],
        strategy_id=row["strategy_id"],
        instrument=row["instrument"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        ruleset_id=row["ruleset_id"],
        mode=row["mode"],
        search_method=row["search_method"],
        status=row["status"],
        estimated_runs=row["estimated_runs"],
        completed_runs=row["completed_runs"],
        best_run_id=row.get("best_run_id"),
        source_run_id=row.get("source_run_id"),
        regime_filter=row.get("regime_filter"),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
    )
