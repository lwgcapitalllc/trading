"""
Stress Tests router — /stress-tests/*
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException

from models import StressTest, StressTestCreate, StressTestDetail
from services import lab_db
from services.stress_tester import (
    run_stress_test_task,
    _estimate_wf_duration_min,
    _estimate_sens_duration_min,
)

router = APIRouter(prefix="/stress-tests", tags=["stress-tests"])


@router.get("", response_model=list[StressTest])
def list_stress_tests(run_id: Optional[str] = None, grade: Optional[str] = None):
    return lab_db.list_stress_tests(run_id=run_id, grade=grade)


@router.get("/{stress_test_id}", response_model=StressTestDetail)
def get_stress_test(stress_test_id: str):
    st = lab_db.get_stress_test(stress_test_id)
    if not st:
        raise HTTPException(404, "Stress test not found")

    # Load heavy files from disk
    equity_paths = None
    distribution = None

    if st.get("equity_paths_path"):
        p = Path(st["equity_paths_path"])
        if p.exists():
            try:
                equity_paths = json.loads(p.read_text())
            except Exception:
                pass

    if st.get("distribution_path"):
        p = Path(st["distribution_path"])
        if p.exists():
            try:
                distribution = json.loads(p.read_text())
            except Exception:
                pass

    return {**st, "equity_paths": equity_paths, "distribution": distribution}


@router.post("/run", status_code=202)
async def trigger_stress_test(body: StressTestCreate):
    run = lab_db.get_run(body.run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.get("status") != "complete":
        raise HTTPException(400, "Run must be complete before stress testing")

    if not run.get("equity_curve_path"):
        raise HTTPException(400, "Run has no equity curve data")

    if body.ruleset_id:
        rs = lab_db.get_ruleset(body.ruleset_id)
        if not rs:
            raise HTTPException(404, "Ruleset not found")

    if (body.include_walk_forward or body.include_sensitivity) and lab_db.has_any_running_vps_job():
        raise HTTPException(409, "NT8 Strategy Analyzer is busy — walk-forward and sensitivity require it to be idle")

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
    })

    asyncio.create_task(
        run_stress_test_task(st_id, body.include_walk_forward, body.include_sensitivity)
    )

    # Build time estimate message for the UI
    est_min = 0
    notes = []
    if body.include_walk_forward:
        wf_min = _estimate_wf_duration_min(body.walk_forward_windows)
        est_min += wf_min
        notes.append(f"Walk-forward: ~{wf_min} min ({body.walk_forward_windows * 2} NT8 backtests)")
    if body.include_sensitivity:
        strategy = lab_db.get_strategy(run.get("strategy_id", ""))
        n_params = len([p for p in (strategy or {}).get("param_schema") or []
                        if p.get("type") in ("int", "float", "double")])
        sens_min = _estimate_sens_duration_min(n_params)
        est_min += sens_min
        notes.append(f"Sensitivity: ~{sens_min} min ({n_params * 4} NT8 backtests)")

    return {
        "stress_test_id": st_id,
        "status": "running",
        "estimated_duration_min": est_min if est_min else None,
        "notes": notes,
    }


@router.delete("/{stress_test_id}", status_code=204)
def delete_stress_test(stress_test_id: str):
    if not lab_db.delete_stress_test(stress_test_id):
        raise HTTPException(404, "Stress test not found")
