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
from services import lab_db, runner_dispatch, history_limits
from services.optimization_runner import (
    expand_grid, pick_search_method, sample_combinations, run_optimization,
    retry_failed_runs, validate_param_grid,
)
from routers.backtests import _row_to_summary
from routers._locks import ensure_platform_idle

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

    # A LIST axis is a closed set of values (a dropdown's options, a bool's two states) that the
    # optimizer walks itself. Only the Python runner expands the grid locally; NT8 and MT5 hand a
    # Start/Step/Increment RANGE to their own tester, so a list of strings has nowhere to land
    # there. Refuse it rather than submit a job that quietly optimizes the wrong thing.
    listed = sorted(k for k, v in req.param_grid.items() if isinstance(v, list))
    if listed and runner != "python":
        raise HTTPException(
            400,
            f"{runner} sweeps numeric ranges only — {', '.join(listed)} "
            "cannot be swept as a list of values.")

    # Check the grid BEFORE anything expands it. A step of 0 used to reach the expander's
    # `while v <= hi: v += step` loop and never come back — on the event loop, so it took the
    # whole backend with it, not just this request.
    try:
        validate_param_grid(req.param_grid)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    try:
        history_limits.validate_window(
            req.instrument, req.start_date, req.end_date,
            req.bar_type, req.bar_value, runner)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    ensure_platform_idle(runner)

    method = pick_search_method(req.param_grid, req.search_method)
    # Off the event loop — a big grid is a real amount of work and this handler is async, so
    # expanding it inline stalls every other request for the duration.
    all_combos = await asyncio.to_thread(expand_grid, req.param_grid)
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
        "cost_layers":        req.cost_layers,
        "broker_profile":     req.broker_profile,
        "min_trades":         req.min_trades,
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
    # One lookup per distinct strategy, not one per row — the list page shows the strategy's
    # NAME and its runner, and both live on the strategy row.
    strategies = {sid: lab_db.get_strategy(sid) for sid in {r["strategy_id"] for r in rows}}
    return [_row_to_opt_summary(r, strategies.get(r["strategy_id"])) for r in rows]


@router.get("/{optimization_id}", response_model=OptimizationDetail)
async def get_optimization(optimization_id: str) -> OptimizationDetail:
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        raise HTTPException(404, "Optimization not found")

    strategy = lab_db.get_strategy(opt["strategy_id"])
    run_rows  = lab_db.list_optimization_runs(optimization_id)

    # Ship only the params the page can draw. A combo row's `params` is fixed_params merged
    # with the swept ones — 50+ keys on a Python strategy — and the page renders exactly the
    # grid's keys. On a 1,000-combo grid polled every 3s that is most of the response, repeated
    # every three seconds, for columns nothing displays.
    grid_keys = set(opt["param_grid"].keys())
    summaries = []
    for r in run_rows:
        s = _row_to_summary(r)
        if s.params:
            s.params = {k: v for k, v in s.params.items() if k in grid_keys}
        summaries.append(s)

    live_pct     = None
    live_message = None
    if opt["status"] == "running":
        try:
            runner_str  = (strategy or {}).get("runner", "ninjatrader")
            # Off the event loop — for NT8/MT5 this is an HTTP call over the SSH tunnel, and
            # the page polls it every 3 seconds while the job runs.
            status_data = await asyncio.to_thread(
                runner_dispatch.job_status, f"nopt_{optimization_id}", runner_str)
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
        source_run_id=opt.get("source_run_id"),
        cost_layers=opt.get("cost_layers"),
        broker_profile=opt.get("broker_profile"),
        min_trades=opt.get("min_trades") or 0,
        winner_note=opt.get("winner_note"),
        grid_sensitivity_score=opt.get("grid_sensitivity_score"),
        grid_sensitivity_summary=opt.get("grid_sensitivity_summary") or None,
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


@router.post("/{optimization_id}/rerun", status_code=202)
async def rerun_optimization(optimization_id: str) -> dict:
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        raise HTTPException(404, "Optimization not found")
    if opt["status"] == "running":
        raise HTTPException(409, "Optimization is already running")

    strategy = lab_db.get_strategy(opt["strategy_id"])
    runner = (strategy or {}).get("runner", "ninjatrader")
    ensure_platform_idle(runner)

    # Reset the existing optimization in-place: clear child runs and set status=running
    deleted_run_ids = lab_db.reset_optimization_for_rerun(optimization_id)
    for run_id in deleted_run_ids:
        run_dir = _LAB_RESULTS_DIR / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)

    asyncio.create_task(run_optimization(optimization_id))
    return {"optimization_id": optimization_id, "status": "started", "estimated_runs": opt["estimated_runs"]}


@router.post("/{optimization_id}/cancel", status_code=200)
async def cancel_optimization(optimization_id: str) -> dict:
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        raise HTTPException(404, "Optimization not found")
    if opt["status"] not in ("running",):
        raise HTTPException(400, f"Optimization is not running (status: {opt['status']})")

    # The DB write is what the page reads and what releases the per-platform job lock, so it
    # MUST be paired with a real stop. Until 2026-08-04 it was the only thing that happened:
    # the sweep kept burning every core, the lock said the platform was free, and the job
    # finished by overwriting its own cancelled status with 'complete'.
    #
    # Runner-agnostic on purpose — python's cancel is a cooperative flag its replay loop
    # checks, NT8's and MT5's is a request to the agent. Same call, three implementations.
    runner = (lab_db.get_strategy(opt["strategy_id"]) or {}).get("runner", "ninjatrader")
    stopped = True
    try:
        await asyncio.to_thread(
            runner_dispatch.cancel_job, f"nopt_{optimization_id}", runner)
    except Exception as exc:
        # The row is still marked cancelled — a job we could not reach is one the poller will
        # abandon on its next tick anyway. Report it rather than claiming a clean stop.
        stopped = False
        _log_cancel_failure(optimization_id, exc)

    lab_db.cancel_optimization(optimization_id)
    return {
        "optimization_id": optimization_id,
        "status": "failed_cancelled",
        "job_stopped": stopped,
    }


def _log_cancel_failure(optimization_id: str, exc: Exception) -> None:
    import logging
    logging.getLogger("optimizations").warning(
        "Could not stop the runner job for %s: %s — the row is marked cancelled and the "
        "poller will abandon it", optimization_id, exc)


@router.post("/{optimization_id}/retry-failed", status_code=202)
async def retry_optimization_failed(optimization_id: str) -> dict:
    opt = lab_db.get_optimization(optimization_id)
    if not opt:
        raise HTTPException(404, "Optimization not found")
    runner = (lab_db.get_strategy(opt["strategy_id"]) or {}).get("runner", "ninjatrader")
    ensure_platform_idle(runner)
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

    live = runner_dispatch.job_log(job_id, lines=lines, runner=runner)
    if live:
        return live

    # Agent has no record (restarted) — serve the saved log file if it exists
    saved = _LAB_RESULTS_DIR / optimization_id / "opt_log.txt"
    if saved.is_file():
        text = saved.read_text(encoding="utf-8", errors="replace")
        return "\n".join(text.splitlines()[-lines:])
    return ""


def _row_to_opt_summary(row: dict, strategy: Optional[dict] = None) -> OptimizationSummary:
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
        runner=(strategy or {}).get("runner", "ninjatrader"),
        strategy_name=(strategy or {}).get("name"),
        winner_note=row.get("winner_note"),
        grid_sensitivity_score=row.get("grid_sensitivity_score"),
    )
