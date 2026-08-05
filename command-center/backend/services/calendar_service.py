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
import threading
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
# higher-is-better by default. (Balance of Trade is intentionally absent — a higher/less-negative
# balance is better, which the default already handles.)
#
# ⚠ THIS LIST IS A CLAIM ABOUT ONE PROVIDER'S VOCABULARY, and until 2026-08-05 nothing checked it.
# It had been written against Forex Factory's naming while the tab reads TRADINGVIEW, so six of its
# eleven keys ("initial claims", "continuing claims", "crude oil inventories", "gasoline
# inventories", "natural gas storage", "producer prices") matched ZERO titles in 811 real ones —
# TradingView calls them "Initial Jobless Claims", "EIA Crude Oil Stocks Change" and "PPI". A dead
# key costs nothing visible; the DAMAGE is what it leaves uncovered, and the worst case was
# `Core PCE Price Index MoM` — HIGH impact, USD, the Fed's own preferred gauge — falling through to
# higher-is-better, so a hot PCE printed GREEN two rows under a hot CPI printing RED.
#
# `tests/test_calendar.py` now fails the build on a key that matches nothing in
# `tests/fixtures/tradingview_titles.txt`, so the list cannot silently rot against the feed again.
#
# Keys are matched at a WORD BOUNDARY on the left and openly on the right (see `_lower_is_better`):
# the left boundary is what stops "ppi" matching "Shipping"/"Shopping", and leaving the right end
# open is what lets one key cover a family ("inflation" → Inflation Rate / Core Inflation Rate /
# Inflation Expectations / Food Inflation / TD-MI Inflation Gauge).
_LOWER_IS_BETTER: Tuple[str, ...] = (
    # ── Inflation. The regime call (unchanged): a cooler print reads risk-on / gold-positive. ──
    "inflation",               # Inflation Rate, Core Inflation Rate, *Inflation Expectations, …
    "cpi",
    "ppi",
    "pce",                     # PCE Price Index MoM/YoY, Core PCE Prices QoQ — the HIGH-impact gap
    "import prices",           # Import Prices, Producer & Import Prices (an inflation INPUT)
    "raw materials prices",
    "prices paid",             # Philly Fed / regional Fed price gauges
    "ism manufacturing prices",
    "ism services prices",
    "price expectations",      # Selling Price Expectations, DMP Output Price Expectations
    # ── Wage inflation. Read as a rates print, which is the lens the whole column uses. ──
    "employment cost",
    "labour cost",             # Labour Cost Index, Labour Costs Index, Unit Labour Costs
    "wage price index",
    # ── Labour market slack. ──
    "unemployment rate",
    "jobless claims",          # Initial / Continuing / 4-week Average
    # ── Inventories & energy stocks: a BUILD is the weak print, a DRAW the strong one. ──
    "stocks change",           # every EIA row (crude, Cushing, gasoline, distillate, natural gas)
    "inventories",             # Business / Wholesale / Retail Inventories
    # ── Balance-sheet stress. ──
    "debt to gdp",
    "household debt",
)

# Compiled once. Left boundary only — see the note above.
_LOWER_RE = re.compile("|".join(r"\b" + re.escape(k) for k in _LOWER_IS_BETTER))


def _lower_is_better(title: str) -> bool:
    """True when a LOWER actual than forecast is the 'good' (green) print for this event."""
    return _LOWER_RE.search(title.lower()) is not None

# ── In-memory fetch cache (per window+countries, ~60s) ──────────────────────────

_CACHE_TTL = 60.0  # seconds
# ⚠ BOUNDED, and it must stay bounded: the key is the exact (from, to, countries) triple, so every
# week a reader pages to mints a new entry that nothing ever removed. A dashboard left open and
# scrolled through a year of weeks grew this without limit. 64 entries ≈ a year of paging either
# way, and eviction is oldest-fetched-first.
_CACHE_MAX = 64
_cache: dict[Tuple[int, int, Tuple[str, ...]], Tuple[float, List[NewsEvent]]] = {}
# One lock for the whole cache, not one per key. Two readers landing on the same uncached week
# would otherwise each hit TradingView for the same payload; the endpoint runs in FastAPI's
# threadpool, so this is real concurrency, not a theoretical one.
_cache_lock = threading.Lock()

# Guardrail: refuse absurd windows (the endpoint caps ~2000 events/query anyway).
# MEASURED 2026-08-05 against the live feed: a 60-day window returns ~1,495 events, so the guard
# sits comfortably inside the provider's cap and no request the router accepts can be silently
# truncated. (105 days DOES return exactly 2,000, i.e. truncated — which is why the guard exists.)
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
    """Fetch a window, memoised for `_CACHE_TTL`. Raises RuntimeError on ANY upstream failure —
    see `_fetch` for why that blanket conversion is the point rather than sloppiness."""
    key = (from_ms, to_ms, tuple(countries))
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and (now - hit[0]) < _CACHE_TTL:
            return hit[1]

    events = _fetch(from_ms, to_ms, countries)

    with _cache_lock:
        _cache[key] = (time.time(), events)
        while len(_cache) > _CACHE_MAX:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]))
    return events


def _fetch(from_ms: int, to_ms: int, countries: Sequence[str]) -> List[NewsEvent]:
    """The one impure call, with every failure normalised to RuntimeError → the router's 502.

    ⚠ The blanket `except Exception` is deliberate and is a FIX, not laziness. The source only
    converts `HTTPError`/`URLError` itself, so two real failure modes escaped it and were reported
    as the wrong kind of problem entirely:

      * a non-JSON body (TradingView serving an HTML error page or a Cloudflare interstitial)
        raises `json.JSONDecodeError`, which **is a subclass of ValueError** — and the router maps
        ValueError to **400**, so an upstream outage came back as "your request was malformed",
        with `Expecting value: line 1 column 1` as the detail;
      * a read timeout raises `TimeoutError`, which is an OSError but NOT a URLError, so it escaped
        both handlers and became a bare **500**.

    Neither is visible to the reader (the page renders "the feed did not answer" for any failure),
    which is exactly why they survived — the only person either one misleads is whoever is trying
    to work out why the calendar is empty. `ValueError` from this module must mean "the CALLER
    asked for something impossible", and nothing the upstream does can be that.
    """
    try:
        return TradingViewSource(countries=countries).fetch_window(from_ms, to_ms).events
    except Exception as exc:  # noqa: BLE001 — see the docstring; this is the seam that classifies
        raise RuntimeError(f"economic calendar feed unavailable: {exc}") from exc


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
    better = (a < f) if _lower_is_better(title) else (a > f)
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
