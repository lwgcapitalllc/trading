"""
Stress Tests router — /stress-tests/* (scaffold stubs)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

router = APIRouter(prefix="/stress-tests", tags=["stress-tests"])


@router.get("/results")
def list_stress_results():
    return []


@router.post("/run", status_code=501)
def trigger_stress_test(strategy: Optional[str] = None, instrument: Optional[str] = None):
    return {
        "status": "not_implemented",
        "message": "Stress test trigger not yet implemented.",
    }
