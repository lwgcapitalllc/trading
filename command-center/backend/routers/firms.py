"""
Firms router — /firms/* (backward-compat redirect to /rulesets/*)
Deprecated in M3. Will be removed in M4.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/firms", tags=["firms-deprecated"])


@router.api_route("", methods=["GET", "POST"])
async def firms_root(request: object = None):
    return RedirectResponse(url="/rulesets", status_code=308)


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def firms_item(path: str):
    return RedirectResponse(url=f"/rulesets/{path}", status_code=308)
