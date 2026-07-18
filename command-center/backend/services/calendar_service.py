"""
calendar_service.py — the live News Calendar tab's data layer.

Fetches a date window from the canonical news engine's TradingView source, applies the tab's
currency/impact filters, and computes each released event's beat/miss "surprise" so the frontend can
colour the actual without owning any market-polarity logic.

This is a LIVE VIEW, deliberately separate from the backtest news path:
  * It reads TradingView (arbitrary window + `actual` results) — NOT the Forex Factory feed that
    `news_filter.py` uses for the backtest holiday filter. The two paths do not overlap.
  * It does NOT write the shared `engines/news/data/events.json` the backtest filter reads. A live
    poll must never mutate the backtest's cache.
  * It caches each upstream fetch in memory for ~60s so re-polling is cheap and TradingView is not
    hammered.

It owns NO news logic of its own — it composes the single canonical engine's `TradingViewSource`
(never a second implementation, CLAUDE.md rule). The only judgement it adds is the display-side
"lower is better" polarity list for colouring, which is a UI concern, not calendar data.
"""

from __future__ import annotations

import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from models import CalendarEvent, CalendarResponse

# engines/ on sys.path so the canonical engine imports by bare name (same pattern as news_filter.py).
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from news.sources import TradingViewSource  # noqa: E402
from news.sources.tradingview import DEFAULT_COUNTRIES  # noqa: E402
from news.types import NewsEvent  # noqa: E402

# Titles where a LOWER actual than forecast is the "good" print (green). Everything else is
# higher-is-better by default. Matched as a lowercase substring of the event title. Start small;
# grow as we spot mis-coloured rows. (Balance of Trade is intentionally absent — a higher/less-
# negative balance is better, which the default higher-is-better already handles.)
_LOWER_IS_BETTER: Tuple[str, ...] = (
    "unemployment rate",
    "jobless claims",          # initial + continuing
    "initial claims",
    "continuing claims",
    "crude oil inventories",
    "gasoline inventories",
    "natural gas storage",
    "inflation rate",          # regime call: lower inflation prints read risk-on / gold-positive
    "cpi",
    "ppi",
    "producer prices",
)

# ── In-memory fetch cache (per window+countries, ~60s) ──────────────────────────

_CACHE_TTL = 60.0  # seconds
_cache: dict[Tuple[int, int, Tuple[str, ...]], Tuple[float, List[NewsEvent]]] = {}

# Guardrail: refuse absurd windows (the endpoint caps ~2000 events/query anyway).
_MAX_SPAN_MS = 60 * 86_400_000  # 60 days


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def iso_to_ms(s: str) -> int:
    """Parse an ISO-8601 string (trailing 'Z' or a numeric offset, or a bare date) to UTC epoch ms.
    Raises ValueError on anything unparseable — the router turns that into a 400."""
    dt = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _fetch_window_cached(from_ms: int, to_ms: int, countries: Sequence[str]) -> List[NewsEvent]:
    key = (from_ms, to_ms, tuple(countries))
    now = time.time()
    hit = _cache.get(key)
    if hit is not None and (now - hit[0]) < _CACHE_TTL:
        return hit[1]
    result = TradingViewSource(countries=countries).fetch_window(from_ms, to_ms)
    events = result.events
    _cache[key] = (now, events)
    return events


def _num(s: Optional[str]) -> Optional[float]:
    """Pull the leading signed number out of a display string ("2.6%"→2.6, "$-3.018"→-3.018,
    "168K"→168). Only the magnitude matters for a beat/miss: an event's actual and forecast share a
    unit, so the unit cancels and we never expand K/M."""
    if not s:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s.replace(",", ""))
    return float(m.group()) if m else None


def _surprise(title: str, actual: Optional[str], forecast: Optional[str]) -> Optional[str]:
    """beat / miss / inline once both actual and forecast are numeric; None otherwise."""
    a = _num(actual)
    f = _num(forecast)
    if a is None or f is None:
        return None
    if a == f:
        return "inline"
    lower_is_better = any(k in title.lower() for k in _LOWER_IS_BETTER)
    better = (a < f) if lower_is_better else (a > f)
    return "beat" if better else "miss"


def get_calendar(
    from_ms: int,
    to_ms: int,
    countries: Sequence[str] = DEFAULT_COUNTRIES,
) -> CalendarResponse:
    """Build the calendar response for [from_ms, to_ms] — the WHOLE window, unfiltered. The frontend
    does the currency/impact/category/day filtering client-side (a week is only a few hundred rows).
    Raises ValueError for a bad window (router → 400) and RuntimeError if the upstream fetch fails
    (router → 502)."""
    if to_ms <= from_ms:
        raise ValueError("'to' must be after 'from'")
    if to_ms - from_ms > _MAX_SPAN_MS:
        raise ValueError("window too large (max 60 days)")

    raw = _fetch_window_cached(from_ms, to_ms, countries)
    out = [
        CalendarEvent(
            timestamp_ms=e.timestamp_ms,
            currency=e.currency,
            impact=e.impact.name,
            title=e.title,
            category=e.category,
            forecast=e.forecast,
            previous=e.previous,
            actual=e.actual,
            surprise=_surprise(e.title, e.actual, e.forecast),
        )
        for e in sorted(raw, key=lambda ev: ev.timestamp_ms)
    ]
    return CalendarResponse(events=out, server_now_ms=_now_ms(), from_ms=from_ms, to_ms=to_ms)
