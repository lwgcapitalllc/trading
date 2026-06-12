"""
Rulesets router — /rulesets/*
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from models import PersonalRulesetPatch, Ruleset, RulesetCreate

from services import lab_db

router = APIRouter(prefix="/rulesets", tags=["rulesets"])

_PROP_TYPES = ("prop_eval", "prop_funded")
_LOCKED_DETAIL = "Firm rules — not editable. Prop rulesets are verified firm data; only personal/demo rulesets accept edits."


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
    row = lab_db.get_ruleset(ruleset_id)
    if not row:
        raise HTTPException(404, f"Ruleset '{ruleset_id}' not found")
    # Prop rows are locked server-side — PUT would otherwise bypass the PATCH lock.
    if row.get("ruleset_type") in _PROP_TYPES:
        raise HTTPException(403, _LOCKED_DETAIL)
    lab_db.update_ruleset(ruleset_id, body.model_dump())
    return lab_db.get_ruleset(ruleset_id)


@router.patch("/{ruleset_id}", response_model=Ruleset)
def patch_personal_ruleset(ruleset_id: str, body: PersonalRulesetPatch):
    """
    Edit the personal rule fields on a personal/demo ruleset. The lock lives HERE,
    not in the UI: prop rows are rejected 403, non-allowlisted fields are rejected
    422 by the body model (extra=forbid), and the SQL layer re-checks the allowlist.
    """
    row = lab_db.get_ruleset(ruleset_id)
    if not row:
        raise HTTPException(404, f"Ruleset '{ruleset_id}' not found")
    if row.get("ruleset_type") not in ("personal", "demo"):
        raise HTTPException(403, _LOCKED_DETAIL)
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    if not fields:
        raise HTTPException(400, "No editable fields provided")
    lab_db.update_ruleset_fields(ruleset_id, fields)
    return lab_db.get_ruleset(ruleset_id)


@router.delete("/{ruleset_id}", status_code=204)
def delete_ruleset(ruleset_id: str):
    if not lab_db.delete_ruleset(ruleset_id):
        raise HTTPException(404, f"Ruleset '{ruleset_id}' not found")
