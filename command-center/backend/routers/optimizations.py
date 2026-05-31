"""
Optimizations router — /optimizations/*
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException

from models import (
    OptimizationRequest, OptimizationSummary, OptimizationDetail,
)
from services import lab_db
from services.optimization_runner import expand_grid, pick_search_method, sample_combinations, run_optimization
from routers.backtests import _row_to_summary

router = APIRouter(prefix="/optimizations", tags=["optimizations"])


@router.post("/run", status_code=202)
async def trigger_optimization(req: OptimizationRequest) -> dict:
    strategy = lab_db.get_strategy(req.strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy '{req.strategy_id}' not found")

    firm = lab_db.get_firm(req.firm_id)
    if not firm:
        raise HTTPException(404, f"Firm '{req.firm_id}' not found")

    if not req.param_grid:
        raise HTTPException(400, "param_grid cannot be empty")

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
        "firm_id":            req.firm_id,
        "mode":               req.mode,
        "search_method":      method,
        "param_grid":         req.param_grid,
        "status":             "running",
        "estimated_runs":     estimated,
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

    return OptimizationDetail(
        optimization_id=opt["optimization_id"],
        strategy_id=opt["strategy_id"],
        strategy_name=strategy["name"] if strategy else opt["strategy_id"],
        instrument=opt["instrument"],
        start_date=opt["start_date"],
        end_date=opt["end_date"],
        firm_id=opt["firm_id"],
        mode=opt["mode"],
        search_method=opt["search_method"],
        param_grid=opt["param_grid"],
        status=opt["status"],
        estimated_runs=opt["estimated_runs"],
        completed_runs=opt["completed_runs"],
        best_run_id=opt.get("best_run_id"),
        created_at=opt["created_at"],
        completed_at=opt.get("completed_at"),
        runs=summaries,
    )


def _row_to_opt_summary(row: dict) -> OptimizationSummary:
    return OptimizationSummary(
        optimization_id=row["optimization_id"],
        strategy_id=row["strategy_id"],
        instrument=row["instrument"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        firm_id=row["firm_id"],
        mode=row["mode"],
        search_method=row["search_method"],
        status=row["status"],
        estimated_runs=row["estimated_runs"],
        completed_runs=row["completed_runs"],
        best_run_id=row.get("best_run_id"),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
    )
