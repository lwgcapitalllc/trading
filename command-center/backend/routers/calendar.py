"""
Calendar router — /calendar for the live News Calendar tab.

Thin: parse the date window, delegate to `services.calendar_service`, map its errors to HTTP codes.
The endpoint returns the WHOLE week; currency/impact/category/day filtering happens client-side (see
calendar_service). All logic (fetch, cache, beat/miss) lives in the service (house style).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from models import CalendarCurrencies, CalendarResponse
from services import calendar_service
from services.calendar_service import iso_to_ms

router = APIRouter(tags=["calendar"])


@router.get("/calendar/currencies", response_model=CalendarCurrencies)
def get_calendar_currencies() -> CalendarCurrencies:
    """The currency roster the tab's chips are drawn from. Static, no upstream call — it is derived
    from the country list this service queries, so the chips cannot drift from the query."""
    return CalendarCurrencies(currencies=calendar_service.currencies_for())


@router.get("/calendar", response_model=CalendarResponse)
def get_calendar(
    from_: str = Query(..., alias="from", description="window start, ISO-8601 UTC"),
    to: str = Query(..., description="window end, ISO-8601 UTC"),
) -> CalendarResponse:
    try:
        from_ms = iso_to_ms(from_)
        to_ms = iso_to_ms(to)
    except ValueError:
        raise HTTPException(status_code=400, detail="from/to must be ISO-8601 datetimes")

    try:
        return calendar_service.get_calendar(from_ms=from_ms, to_ms=to_ms)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
