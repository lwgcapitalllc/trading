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
    WorthinessScore, RunningJobStatus, RunningJobInfo,
)
from services import lab_db, runner_dispatch, chart_spec
from services.backtest_runner import (
    run_backtest_job, read_progress, clear_progress, LAB_RESULTS_DIR, parse_trades_csv,
)
from services.evaluator import evaluate_run
from services.metrics import compute_regime_breakdown
from services.sweep_runner import retry_single_sweep_run
from services.optimization_runner import retry_single_optimization_run
from routers._locks import ensure_platform_idle

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
        source_run_id=row.get("source_run_id"),
        sharpe=row.get("sharpe"),
        params=row.get("params") or {},
        error_message=row.get("error_message"),
        start_date=row.get("start_date"),
        end_date=row.get("end_date"),
        runner=row.get("runner", "ninjatrader"),
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
            adjusted_profit_target=e.get("adjusted_profit_target"),
            contract_cap_status=e.get("contract_cap_status"),
            mll_final_floor=e.get("mll_final_floor"),
            mll_highest_eod_balance=e.get("mll_highest_eod_balance"),
            mll_breach_day=e.get("mll_breach_day"),
            mll_min_floor_distance=e.get("mll_min_floor_distance"),
            firm_max_loss_eod=e["firm_max_loss_eod"],
            firm_profit_target=e["firm_profit_target"],
            firm_consistency_pct=e.get("firm_consistency_pct"),
            ruleset_type=e.get("ruleset_type") or "prop_eval",
            personal_daily_loss_cap=e.get("personal_daily_loss_cap"),
            personal_max_drawdown_from_peak_pct=e.get("personal_max_drawdown_from_peak_pct"),
            personal_max_consecutive_loss_days=e.get("personal_max_consecutive_loss_days"),
            notes=e.get("notes"),
        )
        for e in lab_db.get_evaluations(row["run_id"])
    ]

    equity_curve = _load_json(row.get("equity_curve_path"))
    daily_pnl = _load_json(row.get("daily_pnl_path"))

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
        platform_sharpe=row.get("platform_sharpe"),
        sharpe_low_sample=bool(row.get("sharpe_low_sample")),
        profit_concentration_pct=row.get("profit_concentration_pct"),
        sortino=row.get("sortino"),
        cagr=row.get("cagr"),
        avg_win=row.get("avg_win"),
        avg_loss=row.get("avg_loss"),
        avg_trade_duration_min=row.get("avg_trade_duration_min"),
        worst_day_pnl=row.get("worst_day_pnl"),
        worst_losing_streak=row.get("worst_losing_streak"),
        equity_curve=equity_curve,
        daily_pnl=daily_pnl,
        regime_breakdown=compute_regime_breakdown(equity_curve, daily_pnl),
        evaluations=evals,
        worthiness=_worthiness_from_row(row),
        sweep_id=row.get("sweep_id"),
        optimization_id=row.get("optimization_id"),
        source_run_id=row.get("source_run_id"),
        runner=row.get("runner", "ninjatrader"),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/running-job", response_model=RunningJobStatus)
def get_running_job() -> RunningJobStatus:
    jobs = lab_db.get_running_job()
    return RunningJobStatus(
        nt8=RunningJobInfo(**jobs["nt8"]),
        mt5=RunningJobInfo(**jobs["mt5"]),
    )


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
    return runner_dispatch.job_log(run_id, lines=lines)


@router.post("/run", status_code=202)
async def trigger_backtest(req: BacktestRunRequest) -> dict:
    strategy = lab_db.get_strategy(req.strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy '{req.strategy_id}' not found")

    ruleset_ids = req.ruleset_ids
    for rid in ruleset_ids:
        if not lab_db.get_ruleset(rid):
            raise HTTPException(404, f"Ruleset '{rid}' not found")

    runner = strategy.get("runner", "ninjatrader")
    ensure_platform_idle(runner)

    run_id = uuid.uuid4().hex[:12]
    job_id = run_id

    # Inject foundational config from primary ruleset (first in evaluate list).
    # Merged params are stored in the DB so retries pick them up without re-injection.
    # NinjaScript-only: foundational params map to [Category("Foundational")] properties
    # that MT5/MQL5 strategies don't have, so never inject for the mt5 runner — a forex run
    # now carries a (personal) ruleset for evaluation, but its config must not be injected.
    primary_ruleset = (
        lab_db.get_ruleset(ruleset_ids[0])
        if ruleset_ids and runner != "mt5"
        else None
    )
    merged_params = runner_dispatch.inject_foundational(req.params, primary_ruleset)

    lab_db.insert_run({
        "run_id":             run_id,
        "strategy_id":        req.strategy_id,
        "instrument":         req.instrument,
        "params":             merged_params,
        "bar_type":           req.bar_type,
        "bar_value":          req.bar_value,
        "start_date":         req.start_date,
        "end_date":           req.end_date,
        "commission_per_side": req.commission_per_side,
        "slippage_ticks":     req.slippage_ticks,
        "status":             "running",
        "created_at":         int(time.time()),
        "evaluate_rulesets":  ruleset_ids,
        "runner":             runner,
        "source_run_id":      req.source_run_id,
    })

    job_spec = {
        "job_id":            job_id,
        "strategy_class":    strategy["class_name"],
        "instrument":        req.instrument,
        "params":            merged_params,
        "bar_type":          req.bar_type,
        "bar_value":         req.bar_value,
        "start_date":        req.start_date,
        "end_date":          req.end_date,
        "commission_per_side": req.commission_per_side,
        "slippage_ticks":    req.slippage_ticks,
    }

    try:
        await asyncio.to_thread(runner_dispatch.start_backtest, job_spec, runner)
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", str(exc))
        raise HTTPException(502, f"VPS agent unreachable: {exc}")

    asyncio.create_task(
        run_backtest_job(run_id, job_id, req.strategy_id, req.instrument, ruleset_ids, runner)
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
        await asyncio.to_thread(runner_dispatch.cancel_job, job_id)
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
    if row["status"] == "running":
        raise HTTPException(409, "Run is still in progress")

    # runner is not set on some legacy child rows — derive from the strategy
    strategy = lab_db.get_strategy(row["strategy_id"])
    runner = row.get("runner") or (strategy or {}).get("runner", "ninjatrader")

    # Sweep run — reset in place and re-fire via sweep runner
    if row.get("sweep_id"):
        ensure_platform_idle(runner)
        lab_db.reset_run_for_retry(run_id)
        asyncio.create_task(retry_single_sweep_run(run_id))
        return {"run_id": run_id, "status": "running"}

    # Optimization run — reset in place and re-fire via optimization runner
    if row.get("optimization_id"):
        ensure_platform_idle(runner)
        lab_db.reset_run_for_retry(run_id)
        asyncio.create_task(retry_single_optimization_run(run_id))
        return {"run_id": run_id, "status": "running"}

    # Standalone run — reset the existing record in place and re-fire
    if not strategy:
        raise HTTPException(404, f"Strategy '{row['strategy_id']}' not found")

    ensure_platform_idle(runner)

    evaluate_rulesets = row.get("evaluate_firms") or []

    # Reset the existing row (clears status, error, completed_at, worthiness)
    lab_db.reset_run_for_retry(run_id)
    lab_db.delete_run_evaluations(run_id)

    # Clear stale report files so the UI starts fresh
    run_dir = Path(LAB_RESULTS_DIR) / run_id
    for fname in ("equity_curve.json", "daily_pnl.json"):
        p = run_dir / fname
        if p.exists():
            p.unlink()

    job_spec = {
        "job_id":            run_id,
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
        await asyncio.to_thread(runner_dispatch.start_backtest, job_spec, runner)
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", str(exc))
        raise HTTPException(502, f"VPS agent unreachable: {exc}")

    asyncio.create_task(
        run_backtest_job(run_id, run_id, row["strategy_id"], row["instrument"], evaluate_rulesets, runner)
    )

    return {"run_id": run_id, "status": "running"}


@router.delete("/runs/{run_id}", status_code=204)
def delete_backtest_run(run_id: str) -> Response:
    if not lab_db.delete_run(run_id):
        raise HTTPException(404, "Run not found")
    run_dir = LAB_RESULTS_DIR / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    return Response(status_code=204)


@router.post("/runs/{run_id}/reload-charts")
async def reload_charts(run_id: str) -> dict:
    """Re-export trades from NT8 SA and repopulate equity_curve + daily_pnl for a run."""
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    if row["status"] != "complete":
        raise HTTPException(409, f"Run status is '{row['status']}' — can only reload charts for completed runs")

    try:
        export = await asyncio.to_thread(runner_dispatch.export_trades)
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


@router.get("/runs/{run_id}/chart-spec")
async def get_chart_spec(run_id: str, refresh: bool = False) -> dict:
    """ChartSpec for the price-chart panel — candles + sessions + trades (Phase 7a).

    Returns the camelCase contract the frontend ChartPanel reads (the one place the backend
    emits camelCase, since the shape is defined by the chart, not a DB model). Built lazily and
    cached to the run dir; `refresh=true` rebuilds. Candle fetch is backgrounded (network I/O)."""
    spec = await asyncio.to_thread(chart_spec.build_chart_spec, run_id, refresh)
    if spec is None:
        raise HTTPException(404, "Run not found")
    return spec
