"""
Rulesets router — /rulesets/*
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from models import Ruleset, RulesetCreate

from services import lab_db

router = APIRouter(prefix="/rulesets", tags=["rulesets"])


@router.get("", response_model=list[Ruleset])
def list_rulesets():
    return lab_db.list_rulesets()


@router.post("", response_model=Ruleset, status_code=201)
def create_ruleset(body: RulesetCreate):
    if lab_db.get_ruleset(body.id):
        raise HTTPException(409, f"Ruleset '{body.id}' already exists")
    lab_db.insert_ruleset(body.model_dump())
    return lab_db.get_ruleset(body.id)


@router.get("/{ruleset_id}", response_model=Ruleset)
def get_ruleset(ruleset_id: str):
    row = lab_db.get_ruleset(ruleset_id)
    if not row:
        raise HTTPException(404, f"Ruleset '{ruleset_id}' not found")
    return row


@router.put("/{ruleset_id}", response_model=Ruleset)
def update_ruleset(ruleset_id: str, body: RulesetCreate):
    if not lab_db.get_ruleset(ruleset_id):
        raise HTTPException(404, f"Ruleset '{ruleset_id}' not found")
    lab_db.update_ruleset(ruleset_id, body.model_dump())
    return lab_db.get_ruleset(ruleset_id)


@router.delete("/{ruleset_id}", status_code=204)
def delete_ruleset(ruleset_id: str):
    if not lab_db.delete_ruleset(ruleset_id):
        raise HTTPException(404, f"Ruleset '{ruleset_id}' not found")
