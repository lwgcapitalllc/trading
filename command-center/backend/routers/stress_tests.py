"""
Stress Tests router — /stress-tests/*
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from models import StressTest, StressTestCreate, StressTestDetail
from services import lab_db
from services.backtest_runner import LAB_RESULTS_DIR
from services.stress_tester import (
    run_stress_test_task,
    _estimate_wf_duration_min,
    _estimate_sens_duration_min,
    phases_requested,
    sensitivity_param_count,
    sensitivity_shift_count,
    walk_forward_feasibility,
    MIN_TRADES_FOR_STRESS,
)

router = APIRouter(prefix="/stress-tests", tags=["stress-tests"])


@router.get("", response_model=list[StressTest])
def list_stress_tests(run_id: Optional[str] = None, grade: Optional[str] = None):
    return lab_db.list_stress_tests(run_id=run_id, grade=grade)


@router.get("/running-lock")
def running_stress_lock():
    return lab_db.running_stress_test_markets()


@router.get("/strategy-grades")
def strategy_best_grades():
    return lab_db.best_grades_by_strategy()


@router.get("/{stress_test_id}", response_model=StressTestDetail)
def get_stress_test(stress_test_id: str):
    st = lab_db.get_stress_test(stress_test_id)
    if not st:
        raise HTTPException(404, "Stress test not found")

    # Load heavy files from disk. A file that is PRESENT and unreadable is a different fact from a
    # file that was never written, and both used to arrive as `None` — so a corrupt result rendered
    # as a test that simply had no chart. `results_error` names it.
    equity_paths = None
    distribution = None
    errors: list[str] = []

    def _load(path_key: str, label: str):
        raw = st.get(path_key)
        if not raw:
            return None
        p = Path(raw)
        if not p.exists():
            errors.append(f"{label} file is missing from disk")
            return None
        try:
            return json.loads(p.read_text())
        except Exception as exc:
            errors.append(f"{label} file could not be read ({type(exc).__name__})")
            return None

    equity_paths = _load("equity_paths_path", "Simulated equity paths")
    distribution = _load("distribution_path", "Drawdown distribution")

    return {
        **st,
        "equity_paths": equity_paths,
        "distribution": distribution,
        "results_error": "; ".join(errors) or None,
    }


@router.post("/run", status_code=202)
async def trigger_stress_test(body: StressTestCreate):
    run = lab_db.get_run(body.run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.get("status") != "complete":
        raise HTTPException(400, "Run must be complete before stress testing")

    if not run.get("equity_curve_path"):
        raise HTTPException(400, "Run has no equity curve data")

    # Sample-size gate — one flat floor. Below MIN_TRADES_FOR_STRESS the whole test is blocked:
    # the A-F grade leans on Monte Carlo tail percentiles (worst-1%/worst-5% drawdown) that small
    # samples can't estimate, and walk-forward's IS/OOS windows would be a coin flip. Get more
    # DATA to clear it (longer period, more instruments, smaller timeframe) — not looser params,
    # which just curve-fits the trade count up.
    trade_count = run.get("trade_count") or 0
    if trade_count < MIN_TRADES_FOR_STRESS:
        raise HTTPException(
            422,
            f"Stress test needs at least {MIN_TRADES_FOR_STRESS} trades to be meaningful — "
            f"this run has {trade_count}. Get more trades from more data (longer period, more "
            f"instruments, or a smaller timeframe) before stress testing.",
        )

    if body.ruleset_id:
        rs = lab_db.get_ruleset(body.ruleset_id)
        if not rs:
            raise HTTPException(404, "Ruleset not found")

    strategy = lab_db.get_strategy(run.get("strategy_id", ""))
    runner   = (strategy or {}).get("runner", "ninjatrader")
    # ONE definition of which market a runner belongs to (lab_db.stress_market_for_runner), mirrored
    # by the frontend's `runnerMarket`. Inline, a python run was filed under futures here and read
    # as forex on the page, so its own button never knew it was blocked.
    market   = lab_db.stress_market_for_runner(runner)
    locks    = lab_db.running_stress_test_markets()
    if locks[market]:
        raise HTTPException(409, f"A {market} stress test is already running")

    if (body.include_walk_forward or body.include_sensitivity) and lab_db.has_running_job(runner):
        raise HTTPException(409, f"An {'MT5' if runner == 'mt5' else 'NT8'} job is already running — walk-forward and sensitivity require the platform to be idle")

    st_id = uuid.uuid4().hex[:16]
    lab_db.insert_stress_test({
        "stress_test_id": st_id,
        "run_id": body.run_id,
        "ruleset_id": body.ruleset_id,
        "status": "running",
        "created_at": int(time.time()),
        "num_simulations": body.num_simulations,
        "num_bootstrap": body.num_bootstrap,
        "walk_forward_windows": body.walk_forward_windows,
        "phases_requested": phases_requested(body.include_walk_forward,
                                             body.include_sensitivity),
    })

    task = asyncio.create_task(
        run_stress_test_task(st_id, body.include_walk_forward, body.include_sensitivity)
    )
    # Hold a strong reference. `asyncio.create_task` alone does NOT keep one — the loop only holds
    # the task while a callback of its is scheduled, so a long-awaiting background task is
    # collectable and can vanish mid-flight, leaving the row `running` for ever.
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)

    # Build time estimate + warnings for the UI
    est_min = 0
    notes = []
    warnings: list[str] = []
    if body.include_walk_forward:
        wf_min = _estimate_wf_duration_min(body.walk_forward_windows, runner)
        est_min += wf_min
        notes.append(f"Walk-forward: ~{wf_min} min ({body.walk_forward_windows * 2} backtests)")
        # A walk-forward whose windows cannot each hold enough trades is arithmetic, not luck —
        # it is knowable BEFORE 10 backtests run, and it caps the grade at B when it lands. Saying
        # so up front is the difference between an unassessable result and a wasted hour.
        feasible, why = walk_forward_feasibility(trade_count, body.walk_forward_windows)
        if not feasible:
            warnings.append(why)
    if body.include_sensitivity:
        # Count only the params sensitivity actually perturbs (numeric, non-foundational, and
        # REACHABLE — not behind a switch this run has off) and use the runner's real shift count
        # (MT5 = 2, NT8/python = 4) — both via the shared helpers, so the estimate can't drift
        # from the run loop.
        n_params = sensitivity_param_count(strategy, run.get("params") or {})
        n_backtests = n_params * sensitivity_shift_count(runner)
        # The RUN is passed so the estimate can use its own measured duration instead of a
        # per-job constant — a 6.6-year replay costs ~69s a child, not the 12s the constant
        # assumes, and the modal was quoting ~12 min for a ~69 min job.
        sens_min = _estimate_sens_duration_min(n_params, runner, run)
        est_min += sens_min
        notes.append(f"Sensitivity: at most ~{sens_min} min ({n_backtests} backtests before "
                     f"no-op shifts are skipped)")

    return {
        "stress_test_id": st_id,
        "status": "running",
        "estimated_duration_min": est_min if est_min else None,
        "notes": notes,
        "warnings": warnings,
    }


# Strong references to fire-and-forget background tasks. See the note at the create_task above.
_BACKGROUND_TASKS: set = set()


@router.post("/{stress_test_id}/cancel")
async def cancel_stress_test(stress_test_id: str) -> dict:
    """Stop a running stress test and its in-flight child backtest.

    ⚠ It reports **`job_stopped`** separately from the cancellation, the same distinction the
    optimizer's cancel makes: the row is cancelled either way, but "the runner acknowledged the
    stop" and "we could not reach the runner to tell it" are different facts, and only the first
    means the platform is actually free again."""
    st = lab_db.get_stress_test(stress_test_id)
    if not st:
        raise HTTPException(404, "Stress test not found")

    children = lab_db.cancel_stress_test(stress_test_id)
    if children is None:
        raise HTTPException(409, f"Stress test is '{st['status']}' — only a running test can be cancelled")

    run = lab_db.get_run(st["run_id"]) or {}
    strategy = lab_db.get_strategy(run.get("strategy_id", "")) or {}
    runner = strategy.get("runner", "ninjatrader")

    from services import runner_dispatch
    job_stopped = True
    for child_id in children:
        try:
            await asyncio.to_thread(runner_dispatch.cancel_job, child_id, runner)
        except Exception:
            job_stopped = False
    return {"stress_test_id": stress_test_id, "status": "failed_cancelled",
            "children_cancelled": len(children), "job_stopped": job_stopped}


@router.delete("/{stress_test_id}", status_code=204)
def delete_stress_test(stress_test_id: str):
    child_ids = lab_db.delete_stress_test(stress_test_id)
    if child_ids is None:
        raise HTTPException(404, "Stress test not found")
    # The test's own results dir (equity_paths.json + distribution.json) AND every child run's dir.
    # Deleting the rows and leaving the files is how `reports/lab` grew to 191 directories against
    # 84 live runs.
    for d in [LAB_RESULTS_DIR / stress_test_id] + [LAB_RESULTS_DIR / rid for rid in child_ids]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
