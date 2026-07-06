"""
news/sources/forex_factory.py — the free Forex Factory calendar source.

Pulls the faireconomy.media weekly JSON feeds (this / next / last week) that mirror the Forex
Factory calendar — the retail-standard macro calendar for FX, gold, index and rates futures. Free,
no API key. It is a *macro* calendar (NFP, CPI, FOMC, PCE, ISM, EIA inventories, …), keyed by
currency; it does NOT carry single-stock earnings or unscheduled headlines.

Feed entry schema (confirmed live):
    {"title": "Non-Farm Employment Change", "country": "USD",
     "date": "2026-07-05T21:00:00-04:00", "impact": "High",
     "forecast": "168K", "previous": "199K"}          # "actual" appears once released
`country` is really a currency code (USD/EUR/GBP/…); `date` is ISO-8601 with a numeric offset;
empty strings mean "not published". We normalise date → UTC epoch-ms and impact → Impact.

Limits (why the store exists): the free feed only serves ~last/this/next week. There is no deep
history to download for free, so history is accumulated forward by refresh.py upserting each fetch
into store.py. A paid provider would be a sibling file implementing CalendarSource; nothing else
changes.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from typing import Iterable, List, Optional
from urllib.error import HTTPError, URLError

from ..types import Impact, NewsEvent
from .base import CalendarSource, FetchResult, Interval

_BASE = "https://nfs.faireconomy.media"
_FEEDS = {
    "thisweek": f"{_BASE}/ff_calendar_thisweek.json",
    # nextweek/lastweek are defined for callers that want to try them, but the free host currently
    # serves only thisweek (the others 404). fetch() skips any feed that is missing, so history is
    # built by scheduling refresh.py to pull thisweek repeatedly and accumulating in the store.
    "nextweek": f"{_BASE}/ff_calendar_nextweek.json",
    "lastweek": f"{_BASE}/ff_calendar_lastweek.json",
}
_DEFAULT_FEEDS = ("thisweek",)
# faireconomy occasionally 403s a bare urllib UA; a browser-ish UA is reliably served.
_USER_AGENT = "Mozilla/5.0 (compatible; LWG-news-engine/1.0)"


class ForexFactorySource(CalendarSource):
    """Fetches one or more faireconomy weekly feeds and normalises them to NewsEvent objects.

    `feeds` selects which of last/this/next week to pull (default: all three — the widest free
    window). `timeout` is the per-request network timeout in seconds. Pass a custom `url_base` only
    to point at a local mirror in tests.
    """

    def __init__(
        self,
        feeds: Iterable[str] = _DEFAULT_FEEDS,
        timeout: float = 20.0,
        url_base: str = _BASE,
    ):
        self._feeds = list(feeds)
        self._timeout = timeout
        self._url_base = url_base.rstrip("/")

    def fetch(self) -> FetchResult:
        events: List[NewsEvent] = []
        ranges: List[Interval] = []
        errors: List[str] = []
        for feed in self._feeds:
            try:
                raw = self._get(self._feed_url(feed))
            except (HTTPError, URLError) as exc:
                # A missing feed (e.g. nextweek 404s on the free host) is skipped, not fatal —
                # only a total failure (every requested feed down) is raised.
                errors.append(f"{feed}: {exc}")
                continue
            parsed = self.parse_entries(raw)
            events.extend(parsed)
            if parsed:
                times = [e.timestamp_ms for e in parsed]
                ranges.append((min(times), max(times)))
        if errors and len(errors) == len(self._feeds):
            raise RuntimeError("all calendar feeds failed: " + "; ".join(errors))
        return FetchResult(events=events, covered_ranges=ranges)

    # --- URL / network (the only impure parts) ---------------------------------------------------

    def _feed_url(self, feed: str) -> str:
        if feed in _FEEDS and self._url_base == _BASE:
            return _FEEDS[feed]
        return f"{self._url_base}/ff_calendar_{feed}.json"

    def _get(self, url: str) -> list:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # --- Parsing (pure — unit-tested offline on a saved sample) ----------------------------------

    @classmethod
    def parse_entries(cls, raw: list) -> List[NewsEvent]:
        """Normalise a list of raw feed dicts into NewsEvent objects, skipping any without a parseable
        date. Pure and network-free so it is tested against a saved JSON sample."""
        out: List[NewsEvent] = []
        for row in raw:
            ts = cls._parse_date(row.get("date"))
            if ts is None:
                continue
            impact_str = row.get("impact")
            out.append(
                NewsEvent(
                    timestamp_ms=ts,
                    currency=(row.get("country") or "").strip(),
                    impact=Impact.parse(impact_str),
                    title=(row.get("title") or "").strip(),
                    forecast=_clean(row.get("forecast")),
                    previous=_clean(row.get("previous")),
                    actual=_clean(row.get("actual")),
                    is_holiday=(impact_str or "").strip().lower() == "holiday",
                )
            )
        return out

    @staticmethod
    def _parse_date(s: Optional[str]) -> Optional[int]:
        """ISO-8601 with a numeric offset ("2026-07-05T21:00:00-04:00") → UTC epoch milliseconds.
        Returns None for a missing/unparseable date (some 'Tentative'/all-day rows carry no time)."""
        if not s:
            return None
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        return int(dt.timestamp() * 1000)


def _clean(v: Optional[str]) -> Optional[str]:
    """Empty strings in the feed mean 'not published' — fold them to None."""
    if v is None:
        return None
    v = str(v).strip()
    return v or None
