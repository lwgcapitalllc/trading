"""
Sweeps router — POST /backtests/sweep, GET /backtests/sweeps/:sweep_id
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from models import SweepRequest, SweepResponse, SweepDetail, SweepSummary, BacktestSummary, WorthinessScore
from services import lab_db, runner_dispatch, worthiness, history_limits
from services.evaluator import evaluate_run
from services.sweep_runner import run_sweep, retry_failed_sweep_runs
from routers.backtests import _row_to_summary
from routers._locks import ensure_platform_idle


def _load_json(path: Optional[str]) -> list:
    if not path:
        return []
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return []

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

    ruleset_ids = req.effective_ruleset_ids
    for rid in ruleset_ids:
        if not lab_db.get_ruleset(rid):
            raise HTTPException(404, f"Ruleset '{rid}' not found")

    if not req.instruments:
        raise HTTPException(400, "instruments list cannot be empty")

    runner = strategy.get("runner", "ninjatrader")

    # Broker-history floor — every instrument in the sweep shares one window, so one check
    # per instrument before anything is inserted or locked.
    for _inst in req.instruments:
        try:
            history_limits.validate_window(
                _inst, req.start_date, req.end_date, req.bar_type, req.bar_value, runner)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    ensure_platform_idle(runner)

    sweep_id = "sw_" + uuid.uuid4().hex[:10]
    now      = int(time.time())
    run_specs: list[dict] = []
    job_specs: list[dict] = []
    run_ids:   list[str]  = []

    # Inject foundational config from primary ruleset once for all sweep instruments.
    primary_ruleset = lab_db.get_ruleset(ruleset_ids[0]) if ruleset_ids else None
    merged_params = runner_dispatch.inject_foundational(req.params, primary_ruleset)

    for instrument in req.instruments:
        run_id = uuid.uuid4().hex[:12]
        run_ids.append(run_id)

        lab_db.insert_run_sweep({
            "run_id":             run_id,
            "strategy_id":        req.strategy_id,
            "instrument":         instrument,
            "params":             merged_params,
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
            "runner":             runner,
        })

        run_specs.append({
            "run_id":       run_id,
            "job_id":       run_id,
            "strategy_id":  req.strategy_id,
            "instrument":   instrument,
            "ruleset_ids":  ruleset_ids,
            "runner":       strategy.get("runner", "ninjatrader"),
        })

        job_specs.append({
            "job_id":            run_id,
            "strategy_class":    strategy["class_name"],
            "instrument":        instrument,
            "params":            merged_params,
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
    runner = (lab_db.get_strategy(rows[0]["strategy_id"]) or {}).get("runner", "ninjatrader")
    ensure_platform_idle(runner)
    failed = lab_db.list_sweep_failed_runs(sweep_id)
    if not failed:
        raise HTTPException(400, "No failed runs to retry")
    asyncio.create_task(retry_failed_sweep_runs(sweep_id))
    return {"sweep_id": sweep_id, "retrying": len(failed), "status": "running"}


class _SweepReevalRequest(BaseModel):
    ruleset_ids: list[str] = []
    firm_ids: list[str] = []  # backward-compat alias


@router.post("/sweeps/{sweep_id}/reevaluate", status_code=200)
def reevaluate_sweep(sweep_id: str, req: _SweepReevalRequest) -> dict:
    ids = req.ruleset_ids or req.firm_ids
    for rid in ids:
        if not lab_db.get_ruleset(rid):
            raise HTTPException(404, f"Ruleset '{rid}' not found")

    rows = lab_db.list_sweep_runs(sweep_id)
    if not rows:
        raise HTTPException(404, f"Sweep '{sweep_id}' not found")

    complete_rows = [r for r in rows if r["status"] == "complete"]
    if not complete_rows:
        raise HTTPException(400, "No complete runs to re-evaluate")

    for row in complete_rows:
        run_id = row["run_id"]
        kpis = {k: row.get(k) for k in (
            "net_pnl", "max_drawdown", "profit_factor",
            "win_rate", "win_count", "trade_count", "sharpe", "sortino",
        )}
        equity_curve = _load_json(row.get("equity_curve_path"))
        daily_pnl    = _load_json(row.get("daily_pnl_path"))

        evaluate_run(run_id, ids, kpis, equity_curve, daily_pnl)

        w = worthiness.score_run_after_evals(
            run_id, ids,
            row.get("profit_factor"), row.get("max_drawdown"), row.get("trade_count"),
        )
        if w:
            lab_db.update_run_worthiness(run_id, w[0], w[1], w[2])

    return {"sweep_id": sweep_id, "reevaluated": len(complete_rows)}


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

    seen_ruleset_ids = list({
        e["ruleset_id"]
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
        ruleset_ids=seen_ruleset_ids,
        total_instruments=len(rows),
        completed_instruments=completed,
        status=status,
        created_at=created_at,
        completed_at=completed_at,
        runs=summaries,
    )
