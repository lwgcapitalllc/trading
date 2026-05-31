"""
Strategies router — /strategies/*
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from models import Strategy, ScanResult, InstrumentSummary, InstrumentResult
from services import lab_db, strategy_scanner

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


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(strategy_id: str):
    if not lab_db.delete_strategy(strategy_id):
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")


@router.get("/{strategy_id}/instrument_summary", response_model=InstrumentSummary)
def instrument_summary(
    strategy_id: str,
    firm_id:     Optional[str] = None,
    start_date:  Optional[str] = None,
    end_date:    Optional[str] = None,
) -> InstrumentSummary:
    """Return best worthiness per instrument for this strategy, and untested instruments."""
    if not lab_db.get_strategy(strategy_id):
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")

    # Collect all allowed instruments from firm (or default list)
    firm = lab_db.get_firm(firm_id) if firm_id else None
    if firm and firm.get("allowed_instruments"):
        all_instruments = firm["allowed_instruments"]
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
