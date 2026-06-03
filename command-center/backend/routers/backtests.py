"""
Backtests router — /backtests/*
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from models import (
    BacktestRunRequest, BacktestSummary, BacktestDetail, EvaluationDetail,
    WorthinessScore, RunningJobStatus,
)
from services import lab_db, vps_client
from services.backtest_runner import (
    run_backtest_job, read_progress, clear_progress, LAB_RESULTS_DIR, parse_trades_csv,
    get_backfill_status, run_backfill,
)
from services.evaluator import evaluate_run
from services.sweep_runner import retry_single_sweep_run
from services.optimization_runner import retry_single_optimization_run

router = APIRouter(prefix="/backtests", tags=["backtests"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_json(path: Optional[str]) -> list:
    if not path:
        return []
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return []


def _worthiness_from_row(row: dict) -> Optional[WorthinessScore]:
    if not row.get("worthiness_tier"):
        return None
    return WorthinessScore(
        tier=row["worthiness_tier"],
        reason=row.get("worthiness_reason"),
        computed_against_firm=row.get("worthiness_computed_against_firm"),
    )


def _row_to_summary(row: dict) -> BacktestSummary:
    return BacktestSummary(
        run_id=row["run_id"],
        strategy_id=row["strategy_id"],
        strategy_name=row.get("strategy_name", ""),
        instrument=row["instrument"],
        status=row["status"],
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
        net_pnl=row.get("net_pnl"),
        max_drawdown=row.get("max_drawdown"),
        profit_factor=row.get("profit_factor"),
        win_rate=row.get("win_rate"),
        trade_count=row.get("trade_count"),
        verdicts=lab_db.get_run_verdict_summary(row["run_id"]),
        worthiness=_worthiness_from_row(row),
        sweep_id=row.get("sweep_id"),
        optimization_id=row.get("optimization_id"),
        sharpe=row.get("sharpe"),
        params=row.get("params") or {},
        error_message=row.get("error_message"),
        start_date=row.get("start_date"),
        end_date=row.get("end_date"),
    )


def _row_to_detail(row: dict) -> BacktestDetail:
    evals = [
        EvaluationDetail(
            eval_id=e["eval_id"],
            ruleset_id=e["ruleset_id"],
            ruleset_name=e["ruleset_name"],
            verdict=e["verdict"],
            drawdown_pass=bool(e["drawdown_pass"]),
            target_pass=bool(e["target_pass"]),
            consistency_pass=(
                bool(e["consistency_pass"])
                if e.get("consistency_pass") is not None
                else None
            ),
            simulated_eval_days=e.get("simulated_eval_days"),
            breach_count=e["breach_count"],
            largest_day_share_pct=e.get("largest_day_share_pct"),
            firm_max_loss_eod=e["firm_max_loss_eod"],
            firm_profit_target=e["firm_profit_target"],
            firm_consistency_pct=e.get("firm_consistency_pct"),
            notes=e.get("notes"),
        )
        for e in lab_db.get_evaluations(row["run_id"])
    ]

    return BacktestDetail(
        run_id=row["run_id"],
        strategy_id=row["strategy_id"],
        strategy_name=row.get("strategy_name", ""),
        instrument=row["instrument"],
        params=row.get("params", {}),
        bar_type=row["bar_type"],
        bar_value=row["bar_value"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        commission_per_side=row["commission_per_side"],
        slippage_ticks=row["slippage_ticks"],
        status=row["status"],
        error_message=row.get("error_message"),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
        net_pnl=row.get("net_pnl"),
        max_drawdown=row.get("max_drawdown"),
        profit_factor=row.get("profit_factor"),
        win_rate=row.get("win_rate"),
        win_count=row.get("win_count"),
        trade_count=row.get("trade_count"),
        sharpe=row.get("sharpe"),
        sortino=row.get("sortino"),
        cagr=row.get("cagr"),
        avg_win=row.get("avg_win"),
        avg_loss=row.get("avg_loss"),
        avg_trade_duration_min=row.get("avg_trade_duration_min"),
        worst_day_pnl=row.get("worst_day_pnl"),
        worst_losing_streak=row.get("worst_losing_streak"),
        equity_curve=_load_json(row.get("equity_curve_path")),
        daily_pnl=_load_json(row.get("daily_pnl_path")),
        evaluations=evals,
        worthiness=_worthiness_from_row(row),
        sweep_id=row.get("sweep_id"),
        optimization_id=row.get("optimization_id"),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/running-job", response_model=RunningJobStatus)
def get_running_job() -> RunningJobStatus:
    job = lab_db.get_running_job()
    if job:
        return RunningJobStatus(running=True, **job)
    return RunningJobStatus(running=False)


@router.get("/runs")
def list_backtest_runs(
    strategy_id: Optional[str] = None,
    ruleset_id:  Optional[str] = None,
    firm_id:     Optional[str] = None,  # backward-compat alias
    status:      Optional[str] = None,
) -> list[BacktestSummary]:
    effective_ruleset_id = ruleset_id or firm_id
    rows = lab_db.list_runs(strategy_id=strategy_id, ruleset_id=effective_ruleset_id, status=status)
    return [_row_to_summary(r) for r in rows]


@router.get("/runs/{run_id}")
def get_backtest_run(run_id: str) -> BacktestDetail:
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    return _row_to_detail(row)


@router.get("/runs/{run_id}/log", response_class=PlainTextResponse)
def get_run_log(run_id: str, lines: int = 200) -> str:
    if not lab_db.get_run(run_id):
        raise HTTPException(404, "Run not found")
    return vps_client.job_log(run_id, lines=lines)


@router.post("/run", status_code=202)
async def trigger_backtest(req: BacktestRunRequest) -> dict:
    strategy = lab_db.get_strategy(req.strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy '{req.strategy_id}' not found")

    ruleset_ids = req.ruleset_ids
    for rid in ruleset_ids:
        if not lab_db.get_ruleset(rid):
            raise HTTPException(404, f"Ruleset '{rid}' not found")

    if read_progress().get("status") == "running":
        raise HTTPException(409, "A backtest is already running")

    if lab_db.has_any_running_vps_job():
        raise HTTPException(409, "An optimization or sweep is already running — wait for it to finish before starting a new backtest")

    run_id = uuid.uuid4().hex[:12]
    job_id = run_id

    lab_db.insert_run({
        "run_id":             run_id,
        "strategy_id":        req.strategy_id,
        "instrument":         req.instrument,
        "params":             req.params,
        "bar_type":           req.bar_type,
        "bar_value":          req.bar_value,
        "start_date":         req.start_date,
        "end_date":           req.end_date,
        "commission_per_side": req.commission_per_side,
        "slippage_ticks":     req.slippage_ticks,
        "status":             "running",
        "created_at":         int(time.time()),
        "evaluate_rulesets":  ruleset_ids,
    })

    job_spec = {
        "job_id":            job_id,
        "strategy_class":    strategy["class_name"],
        "instrument":        req.instrument,
        "params":            req.params,
        "bar_type":          req.bar_type,
        "bar_value":         req.bar_value,
        "start_date":        req.start_date,
        "end_date":          req.end_date,
        "commission_per_side": req.commission_per_side,
        "slippage_ticks":    req.slippage_ticks,
    }

    try:
        await asyncio.to_thread(vps_client.start_backtest, job_spec, strategy.get("runner", "ninjatrader"))
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", str(exc))
        raise HTTPException(502, f"VPS agent unreachable: {exc}")

    asyncio.create_task(
        run_backtest_job(run_id, job_id, req.strategy_id, req.instrument, ruleset_ids)
    )

    return {"run_id": run_id, "status": "started"}


@router.post("/runs/{run_id}/stop", status_code=200)
async def stop_backtest_run(run_id: str) -> dict:
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    if row["status"] != "running":
        raise HTTPException(400, f"Run is not running (status: {row['status']})")

    progress = read_progress()
    job_id   = progress.get("job_id") or run_id

    try:
        await asyncio.to_thread(vps_client.cancel_job, job_id)
    except Exception:
        pass  # best-effort — still mark cancelled locally

    lab_db.update_run_status(run_id, "failed_cancelled", "Cancelled by user")
    clear_progress()
    return {"run_id": run_id, "status": "failed_cancelled"}


@router.post("/runs/{run_id}/retry", status_code=202)
async def retry_backtest_run(run_id: str) -> dict:
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    if not row["status"].startswith("failed"):
        raise HTTPException(400, f"Run is not failed (status: {row['status']})")

    # Sweep run — reset in place and re-fire via sweep runner
    if row.get("sweep_id"):
        if lab_db.has_any_running_vps_job():
            raise HTTPException(409, "Another VPS job is running — wait for it to finish before retrying")
        lab_db.reset_run_for_retry(run_id)
        asyncio.create_task(retry_single_sweep_run(run_id))
        return {"run_id": run_id, "status": "running"}

    # Optimization run — reset in place and re-fire via optimization runner
    if row.get("optimization_id"):
        if lab_db.has_any_running_vps_job():
            raise HTTPException(409, "Another VPS job is running — wait for it to finish before retrying")
        lab_db.reset_run_for_retry(run_id)
        asyncio.create_task(retry_single_optimization_run(run_id))
        return {"run_id": run_id, "status": "running"}

    # Standalone run — create a fresh run row with a new ID
    strategy = lab_db.get_strategy(row["strategy_id"])
    if not strategy:
        raise HTTPException(404, f"Strategy '{row['strategy_id']}' not found")

    if read_progress().get("status") == "running":
        raise HTTPException(409, "A backtest is already running")

    evaluate_rulesets = row.get("evaluate_firms") or []

    new_run_id = uuid.uuid4().hex[:12]
    lab_db.insert_run({
        "run_id":             new_run_id,
        "strategy_id":        row["strategy_id"],
        "instrument":         row["instrument"],
        "params":             row["params"],
        "bar_type":           row["bar_type"],
        "bar_value":          row["bar_value"],
        "start_date":         row["start_date"],
        "end_date":           row["end_date"],
        "commission_per_side": row["commission_per_side"],
        "slippage_ticks":     row["slippage_ticks"],
        "status":             "running",
        "created_at":         int(time.time()),
        "evaluate_rulesets":  evaluate_rulesets,
    })

    job_spec = {
        "job_id":            new_run_id,
        "strategy_class":    strategy["class_name"],
        "instrument":        row["instrument"],
        "params":            row["params"],
        "bar_type":          row["bar_type"],
        "bar_value":         row["bar_value"],
        "start_date":        row["start_date"],
        "end_date":          row["end_date"],
        "commission_per_side": row["commission_per_side"],
        "slippage_ticks":    row["slippage_ticks"],
    }

    try:
        await asyncio.to_thread(vps_client.start_backtest, job_spec, strategy.get("runner", "ninjatrader"))
    except Exception as exc:
        lab_db.update_run_status(new_run_id, "failed_unknown", str(exc))
        raise HTTPException(502, f"VPS agent unreachable: {exc}")

    asyncio.create_task(
        run_backtest_job(new_run_id, new_run_id, row["strategy_id"], row["instrument"], evaluate_rulesets)
    )

    return {"run_id": new_run_id, "status": "started"}


@router.delete("/runs/{run_id}", status_code=204)
def delete_backtest_run(run_id: str) -> Response:
    if not lab_db.delete_run(run_id):
        raise HTTPException(404, "Run not found")
    run_dir = LAB_RESULTS_DIR / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    return Response(status_code=204)


class _ReevalRequest(BaseModel):
    ruleset_ids: list[str] = []
    firm_ids: list[str] = []  # backward-compat alias


@router.post("/runs/{run_id}/reevaluate")
def reevaluate_run(run_id: str, req: _ReevalRequest) -> BacktestDetail:
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    if row["status"] != "complete":
        raise HTTPException(400, f"Run status is '{row['status']}', not 'complete'")

    ids = req.ruleset_ids or req.firm_ids
    kpis = {k: row.get(k) for k in (
        "net_pnl", "max_drawdown", "profit_factor", "win_rate",
        "win_count", "trade_count", "sharpe", "sortino",
    )}
    equity_curve = _load_json(row.get("equity_curve_path"))
    daily_pnl    = _load_json(row.get("daily_pnl_path"))

    evaluate_run(run_id, ids, kpis, equity_curve, daily_pnl)

    return _row_to_detail(lab_db.get_run(run_id))


@router.post("/runs/{run_id}/reload-charts")
async def reload_charts(run_id: str) -> dict:
    """Re-export trades from NT8 SA and repopulate equity_curve + daily_pnl for a run."""
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    if row["status"] != "complete":
        raise HTTPException(409, f"Run status is '{row['status']}' — can only reload charts for completed runs")

    try:
        export = await asyncio.to_thread(vps_client.export_trades)
    except Exception as exc:
        raise HTTPException(502, f"VPS agent error: {exc}")

    csv_text = export.get("csv", "")
    if not csv_text:
        raise HTTPException(502, "VPS agent returned no CSV data")

    equity_curve, daily_pnl = parse_trades_csv(csv_text)

    run_dir = LAB_RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    eq_path  = run_dir / "equity_curve.json"
    dpnl_path = run_dir / "daily_pnl.json"
    eq_path.write_text(json.dumps(equity_curve))
    dpnl_path.write_text(json.dumps(daily_pnl))

    lab_db.update_run_chart_paths(run_id, {
        "equity_curve": str(eq_path),
        "daily_pnl":    str(dpnl_path),
    })

    return {"equity_points": len(equity_curve), "daily_bars": len(daily_pnl)}


@router.post("/runs/{run_id}/backfill_regime", status_code=202)
async def backfill_regime(run_id: str) -> dict:
    """Classify regime for each daily_pnl entry on a pre-M4 (or OHLC-failed) backtest."""
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    if row["status"] != "complete":
        raise HTTPException(400, f"Run is not complete (status: {row['status']})")

    daily_pnl_path = Path(row.get("daily_pnl_path") or "")
    if not daily_pnl_path.exists():
        raise HTTPException(400, "No daily_pnl file found for this run")

    asyncio.create_task(
        run_backfill(
            run_id,
            row["instrument"],
            row.get("start_date", ""),
            row.get("end_date", ""),
            daily_pnl_path,
        )
    )
    return {"run_id": run_id, "status": "started"}


@router.get("/runs/{run_id}/backfill_status")
def backfill_regime_status(run_id: str) -> dict:
    """Poll status of an in-progress or completed regime backfill."""
    if not lab_db.get_run(run_id):
        raise HTTPException(404, "Run not found")
    return get_backfill_status(run_id)
