"""
news/sources/forex_factory_history.py — historical calendar backfill by scraping the FF website.

The free JSON feed (forex_factory.py) only serves the current week. The forexfactory.com CALENDAR
PAGE, however, shows any date — but it sits behind Cloudflare, so a plain urllib request gets a
403 "Just a moment" challenge instead of the data. This source gets past that by impersonating a
real browser's TLS/HTTP fingerprint with `curl_cffi`, then parsing the calendar data the page
embeds as `calendarComponentStates[...] = { days: [...] }`.

Each embedded event carries a `dateline` (UTC unix seconds — exact, timezone-free), `currency`,
`impactName` (low/medium/high/holiday), `name`, and `actual`/`forecast`/`previous`. One request
returns a whole month (`?month=feb.2025` -> ~400 events), so backfilling a range is a handful of
requests, cached forever in the EventStore (historical events are static).

Dependency + etiquette (deliberately isolated here, lazy-imported):
  * needs `curl_cffi` (pip install curl_cffi) — a compiled browser-impersonation client. The engine
    core and the live JSON feed stay pure-stdlib; only historical backfill needs this.
  * scraping is against FF's ToS and the fingerprint trick can break when Cloudflare updates — this
    is for personal backtest data. Be gentle: the source sleeps between month requests by default.
"""

from __future__ import annotations

import json
import re
import time
from calendar import monthrange
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from ..types import Impact, NewsEvent
from .base import CalendarSource, FetchResult, Interval

_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_CAL_URL = "https://www.forexfactory.com/calendar?month={mon}.{year}"
_STATE_RE = re.compile(r"calendarComponentStates\[\d+\]\s*=\s*\{")

# curl_cffi browser fingerprints, tried in order until one is not refused. Cloudflare blocks these
# per-family and changes its mind over time — as of 2026-07-28 every chrome* profile 403s here while
# safari and firefox return the page, which is the exact reverse of when this source was written.
# So this is an ordered fallback chain, never a single hardcoded profile: measure, don't assume.
# Chrome is kept last rather than deleted — it is the most common fingerprint and may be unblocked
# again. If the whole chain ever fails, upgrade curl_cffi and add its newer profiles at the front.
_PROFILES = ("safari18_0", "firefox133", "safari17_0", "chrome131")


def _month_bounds_ms(year: int, month: int) -> Interval:
    """[first-instant, last-instant] of a calendar month in UTC epoch ms."""
    start = datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)
    last_day = monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _extract_days_array(html: str) -> Optional[str]:
    """Return the raw JSON text of the `days: [ ... ]` array embedded in the calendar page, or None.
    The page assigns a JS object with UNQUOTED top-level keys (not valid JSON), but the `days` value
    is itself a proper JSON array, so we bracket-match just that array out and json.loads it."""
    m = _STATE_RE.search(html)
    if not m:
        return None
    key = html.find("days:", m.end())
    if key == -1:
        return None
    start = html.find("[", key)
    if start == -1:
        return None
    depth, i, instr, esc = 0, start, False, False
    while i < len(html):
        c = html[i]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
        else:
            if c == '"':
                instr = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return html[start : i + 1]
        i += 1
    return None


class ForexFactoryHistorySource(CalendarSource):
    """Scrapes the FF calendar website for historical (or current) months and normalises to
    NewsEvent. `fetch()` pulls the current month; use `fetch_month` / `fetch_range` for history.

    `sleep_s` throttles month requests (politeness); `impersonate` pins ONE curl_cffi browser
    profile — leave it None to walk `_PROFILES` until one gets through (the normal path).
    """

    def __init__(
        self, sleep_s: float = 1.0, timeout: float = 30.0, impersonate: Optional[str] = None
    ):
        self._sleep_s = sleep_s
        self._timeout = timeout
        self._impersonate = impersonate
        self._working: Optional[str] = impersonate  # first profile that got a 200, reused after

    def fetch(self) -> FetchResult:
        now = datetime.now(tz=timezone.utc)
        return self.fetch_month(now.year, now.month)

    def fetch_month(self, year: int, month: int) -> FetchResult:
        """One month in one request. covered_ranges is the strict calendar-month span (so a sparse
        month still counts as covered — a data gap is never confused with a quiet month)."""
        html = self._get(_CAL_URL.format(mon=_MONTHS[month - 1], year=year))
        events = self.parse_page(html)
        return FetchResult(events=events, covered_ranges=[_month_bounds_ms(year, month)])

    def fetch_range(self, start_ms: int, end_ms: int) -> FetchResult:
        """Every month spanning [start_ms, end_ms], aggregated. Sleeps between requests."""
        events: List[NewsEvent] = []
        ranges: List[Interval] = []
        for year, month in _months_between(start_ms, end_ms):
            res = self.fetch_month(year, month)
            events.extend(res.events)
            ranges.extend(res.covered_ranges)
            if self._sleep_s:
                time.sleep(self._sleep_s)
        return FetchResult(events=events, covered_ranges=ranges)

    # --- network (impure, lazy dependency) -------------------------------------------------------

    def _get(self, url: str) -> str:
        try:
            from curl_cffi import requests as cffi_requests
        except ImportError as exc:  # keep the dep optional + the fix obvious
            raise RuntimeError(
                "historical FF backfill needs curl_cffi to get past Cloudflare — "
                "`pip install curl_cffi`. (The live JSON feed and the engine core need no deps.)"
            ) from exc
        # Cloudflare blocks fingerprints one family at a time, not all at once — on 2026-07-28 every
        # chrome* profile started returning 403 while safari/firefox still got 200. So we try a
        # CHAIN rather than trusting a single hardcoded profile, and remember the one that worked so
        # a 66-month backfill pays for the search once instead of on every request.
        candidates = list(_PROFILES)
        if self._working:  # known-good (or user-pinned) goes first, but the
            candidates = [self._working] + [
                p for p in _PROFILES if p != self._working
            ]  # rest still
        last = ""  # rescue us
        for profile in candidates:
            resp = cffi_requests.get(url, impersonate=profile, timeout=self._timeout)
            if resp.status_code == 200:
                self._working = profile
                return resp.text
            last = f"{resp.status_code} on {profile}"
        raise RuntimeError(
            f"FF calendar fetch failed ({last}) for {url} — every browser profile was refused. "
            f"Cloudflare has likely tightened; try a newer curl_cffi and add its profiles to "
            f"_PROFILES."
        )

    # --- parsing (pure — unit-tested offline on a saved sample) ----------------------------------

    @classmethod
    def parse_page(cls, html: str) -> List[NewsEvent]:
        """Normalise one calendar page's embedded events into NewsEvent objects. Pure + network-free
        so it is tested against a saved HTML sample. Uses each event's `dateline` (UTC unix seconds)
        for an exact, timezone-independent timestamp."""
        raw = _extract_days_array(html)
        if raw is None:
            return []
        days = json.loads(raw)
        out: List[NewsEvent] = []
        for day in days:
            for e in day.get("events") or []:
                dateline = e.get("dateline")
                if dateline is None:
                    continue
                impact_name = e.get("impactName")
                out.append(
                    NewsEvent(
                        timestamp_ms=int(dateline) * 1000,
                        currency=(e.get("currency") or "").strip(),
                        impact=Impact.parse(impact_name),
                        title=(e.get("name") or "").strip(),
                        forecast=_clean(e.get("forecast")),
                        previous=_clean(e.get("previous")),
                        actual=_clean(e.get("actual")),
                        is_holiday=(impact_name or "").strip().lower() == "holiday",
                    )
                )
        return out


def _months_between(start_ms: int, end_ms: int) -> List[Tuple[int, int]]:
    """List of (year, month) from the month of start_ms through the month of end_ms, inclusive."""
    start = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
    end = datetime.fromtimestamp(end_ms / 1000, tz=timezone.utc)
    y, m = start.year, start.month
    months: List[Tuple[int, int]] = []
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _clean(v) -> Optional[str]:
    """Empty strings mean 'not published' — fold to None."""
    if v is None:
        return None
    v = str(v).strip()
    return v or None
