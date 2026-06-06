"""
Strategies router — /strategies/*
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from models import Strategy, ScanResult, InstrumentSummary, InstrumentResult, DeployJobStatus


class StrategyPatch(BaseModel):
    description: Optional[str] = None
from services import lab_db, strategy_scanner, nt8_agent_client
import config as cfg

_deploy_jobs: dict[str, dict] = {}

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=list[Strategy])
def list_strategies():
    return lab_db.list_strategies()


@router.post("/scan", response_model=ScanResult)
def scan_strategies():
    return strategy_scanner.scan_strategies()


@router.get("/{strategy_id}", response_model=Strategy)
def get_strategy(strategy_id: str):
    row = lab_db.get_strategy(strategy_id)
    if not row:
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")
    return row


@router.patch("/{strategy_id}", response_model=Strategy)
def patch_strategy(strategy_id: str, body: StrategyPatch):
    if not lab_db.get_strategy(strategy_id):
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")
    lab_db.update_strategy_description(strategy_id, body.description or None)
    row = lab_db.get_strategy(strategy_id)
    return row


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(strategy_id: str):
    if not lab_db.delete_strategy(strategy_id):
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")


@router.post("/{strategy_id}/deploy", status_code=202)
def deploy_strategy(strategy_id: str):
    strategy = lab_db.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")

    source_path = strategy.get("source_path")
    if not source_path:
        raise HTTPException(400, "Strategy has no source_path. Set it first or use the Deployed tab to upload manually.")

    file_path = Path(cfg.MONOREPO_ROOT) / source_path
    if not file_path.exists():
        raise HTTPException(404, f"Source file not found on disk: {source_path}")

    filename = file_path.name
    content = file_path.read_bytes()

    job_id = str(uuid.uuid4())
    _deploy_jobs[job_id] = {
        "deploy_job_id": job_id,
        "strategy_id": strategy_id,
        "status": "running",
        "filename": filename,
        "uploaded_size_bytes": None,
        "error": None,
    }

    try:
        result = nt8_agent_client.upload_strategy_file(filename, content, overwrite=True)
        _deploy_jobs[job_id].update({
            "status": "complete",
            "uploaded_size_bytes": result.get("size_bytes"),
        })
    except RuntimeError as exc:
        msg = str(exc)
        _deploy_jobs[job_id].update({"status": "failed", "error": msg})
        if "HTTP 423" in msg:
            raise HTTPException(423, detail=msg)
        raise HTTPException(502, detail=msg)

    return {"deploy_job_id": job_id, "status": "started"}


@router.get("/{strategy_id}/deploy/{deploy_job_id}", response_model=DeployJobStatus)
def get_deploy_status(strategy_id: str, deploy_job_id: str):
    job = _deploy_jobs.get(deploy_job_id)
    if not job:
        raise HTTPException(404, "Deploy job not found")
    return job


@router.get("/{strategy_id}/instrument_summary", response_model=InstrumentSummary)
def instrument_summary(
    strategy_id: str,
    ruleset_id:  Optional[str] = None,
    firm_id:     Optional[str] = None,   # backward-compat alias
    start_date:  Optional[str] = None,
    end_date:    Optional[str] = None,
) -> InstrumentSummary:
    """Return best worthiness per instrument for this strategy, and untested instruments."""
    if not lab_db.get_strategy(strategy_id):
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")

    # Collect all allowed instruments from ruleset (or default list)
    rid = ruleset_id or firm_id
    ruleset = lab_db.get_ruleset(rid) if rid else None
    if ruleset and ruleset.get("allowed_instruments"):
        all_instruments = ruleset["allowed_instruments"]
    else:
        all_instruments = ["MES", "MNQ", "MGC", "MCL", "MYM", "M2K"]

    runs = lab_db.list_runs(strategy_id=strategy_id, status="complete")

    TIER_ORDER = {
        "TIER_1_STRESS_TEST": 0,
        "TIER_2_OPTIMIZE":    1,
        "TIER_3_DISCARD":     2,
        None:                 3,
    }

    best_by_instrument: dict[str, dict] = {}
    for run in runs:
        inst = run["instrument"]
        # Strip contract month (e.g. "MES 06-26" → "MES")
        base = inst.split()[0] if " " in inst else inst
        tier = run.get("worthiness_tier")
        if base not in best_by_instrument:
            best_by_instrument[base] = {
                "instrument":      inst,
                "best_worthiness": tier,
                "best_run_id":     run["run_id"],
                "tested_at":       run.get("completed_at"),
            }
        else:
            current_order = TIER_ORDER.get(best_by_instrument[base]["best_worthiness"], 3)
            new_order     = TIER_ORDER.get(tier, 3)
            if new_order < current_order:
                best_by_instrument[base] = {
                    "instrument":      inst,
                    "best_worthiness": tier,
                    "best_run_id":     run["run_id"],
                    "tested_at":       run.get("completed_at"),
                }

    instrument_results = []
    tested_bases: set[str] = set()
    for base, info in best_by_instrument.items():
        tested_bases.add(base)
        instrument_results.append(InstrumentResult(
            instrument=info["instrument"],
            best_worthiness=info["best_worthiness"],
            best_run_id=info["best_run_id"],
            tested_at=info["tested_at"],
        ))

    # Sort by tier (best first)
    instrument_results.sort(key=lambda r: TIER_ORDER.get(r.best_worthiness, 3))

    # Untested instruments (base symbols not yet seen)
    untested = [i for i in all_instruments if i not in tested_bases]

    return InstrumentSummary(
        instrument_results=instrument_results,
        untested_instruments=untested,
    )
