"""
Strategies router — /strategies/*
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from models import Strategy, ScanResult
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
