"""
Firms router — /firms/*
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from models import Firm, FirmCreate

from services import lab_db

router = APIRouter(prefix="/firms", tags=["firms"])


@router.get("", response_model=list[Firm])
def list_firms():
    return lab_db.list_firms()


@router.post("", response_model=Firm, status_code=201)
def create_firm(body: FirmCreate):
    if lab_db.get_firm(body.id):
        raise HTTPException(409, f"Firm '{body.id}' already exists")
    lab_db.insert_firm(body.model_dump())
    return lab_db.get_firm(body.id)


@router.get("/{firm_id}", response_model=Firm)
def get_firm(firm_id: str):
    row = lab_db.get_firm(firm_id)
    if not row:
        raise HTTPException(404, f"Firm '{firm_id}' not found")
    return row


@router.put("/{firm_id}", response_model=Firm)
def update_firm(firm_id: str, body: FirmCreate):
    if not lab_db.get_firm(firm_id):
        raise HTTPException(404, f"Firm '{firm_id}' not found")
    lab_db.update_firm(firm_id, body.model_dump())
    return lab_db.get_firm(firm_id)


@router.delete("/{firm_id}", status_code=204)
def delete_firm(firm_id: str):
    if not lab_db.delete_firm(firm_id):
        raise HTTPException(404, f"Firm '{firm_id}' not found")
