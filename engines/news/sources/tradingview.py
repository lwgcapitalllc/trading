"""
news/sources/tradingview.py — the free TradingView economic-calendar source.

Pulls TradingView's public economic-calendar endpoint. Unlike the Forex Factory free feed (one week,
no `actual` until much later), this serves an ARBITRARY date window (history back to ~2018, forward
~2 months) and fills in `actual` shortly after each release — which is exactly what the command-center
live calendar tab needs. Free, no API key; it only requires an `Origin` header (it 403s without it).

It is a *macro* calendar keyed by currency (USD/EUR/GBP/…), same shape as Forex Factory: NFP, CPI,
FOMC, PMIs, rate decisions, central-bank speeches, auctions. It carries **no bank-holiday rows** — so
`is_holiday` is always False from this source. Holidays still come only from the Forex Factory path
(the backtest holiday filter); this source is not a replacement for that.

Endpoint (confirmed live 2026-07-17):
    GET https://economic-calendar.tradingview.com/events
        ?from=<ISO8601 UTC, e.g. 2026-07-13T00:00:00.000Z>
        &to=<ISO8601 UTC>
        &countries=US,EU,GB,JP,CA,AU,NZ,CH,CN
    headers: Origin: https://www.tradingview.com   (required)
             User-Agent: Mozilla/5.0
Response: {"status": "ok", "result": [ {event}, ... ]}

Per-event fields we read:
    date        UTC ISO 8601 with a trailing Z            -> timestamp_ms
    currency    ISO currency code (USD/EUR/…)             -> currency
    importance  1 = high, 0 = medium, -1 = low            -> impact
    title       event name                                -> title
    forecast/previous/actual  display-scaled numbers      -> forecast/previous/actual (as strings)
    unit        "%", "K", "A$", …                         -> folded into the display string
    period      "Jun", "Q1", …                            -> title-agnostic; carried on the raw row only
`actual` is null before release and fills in after. The paired `*Raw` fields carry the same values
unscaled; we keep the human `actual`/`forecast`/`previous` (already same-unit within an event, so a
consumer can compare them numerically for a beat/miss without expanding K/M).

This is a `CalendarSource` sibling of `forex_factory.py` — the sanctioned way to add a provider. The
store and engine are unaffected. Do NOT build a second news engine (CLAUDE.md rule).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Sequence
from urllib.error import HTTPError, URLError

from ..types import Impact, NewsEvent
from .base import CalendarSource, FetchResult

_ENDPOINT = "https://economic-calendar.tradingview.com/events"
# The nine major FX blocs — USD dominates for gold; the rest give context (Aaron's call 2026-07-17).
DEFAULT_COUNTRIES = ("US", "EU", "GB", "JP", "CA", "AU", "NZ", "CH", "CN")
# It 403s without an Origin; a browser-ish UA is served reliably.
_HEADERS = {
    "Origin": "https://www.tradingview.com",
    "User-Agent": "Mozilla/5.0",
}
# importance -> Impact. There is no "holiday" importance; holidays never appear on this source.
_IMPORTANCE = {1: Impact.HIGH, 0: Impact.MEDIUM, -1: Impact.LOW}

# TradingView's short `category` codes -> the human labels its own dropdown uses. An unknown non-empty
# code falls back to a title-cased version of itself; empty/missing -> None.
_CATEGORY_LABELS = {
    "bnd": "Bonds",
    "bsnss": "Business",
    "cnsm": "Consumer",
    "enrg": "Energy",
    "gdp": "GDP",
    "gov": "Government",
    "hlth": "Health",
    "hse": "Housing",
    "lbr": "Labor",
    "mny": "Money",
    "mrkt": "Markets",
    "prce": "Prices",
    "trd": "Trade",
    "tax": "Taxes",
}


def _category_label(code) -> Optional[str]:
    if not code:
        return None
    code = str(code).strip()
    return _CATEGORY_LABELS.get(code, code.title() or None)


class TradingViewSource(CalendarSource):
    """Fetches the TradingView economic-calendar endpoint and normalises rows to NewsEvent objects.

    `countries` is the default 2-letter bloc list (US/EU/GB/…) — note these are country/bloc codes for
    the query, distinct from the ISO `currency` on each row. `timeout` is the per-request network
    timeout in seconds. Pass a custom `endpoint` only to point at a local mirror in tests.
    """

    def __init__(
        self,
        countries: Iterable[str] = DEFAULT_COUNTRIES,
        timeout: float = 20.0,
        endpoint: str = _ENDPOINT,
    ):
        self._countries = list(countries)
        self._timeout = timeout
        self._endpoint = endpoint

    def fetch(self) -> FetchResult:
        """Satisfy the CalendarSource contract: pull the current UTC week (Mon 00:00 → +7 days)."""
        start = _week_start_ms(_now_ms())
        return self.fetch_window(start, start + 7 * 86_400_000)

    def fetch_window(
        self,
        from_ms: int,
        to_ms: int,
        countries: Optional[Sequence[str]] = None,
    ) -> FetchResult:
        """Pull [from_ms, to_ms] (epoch ms, UTC). Coverage is the REQUESTED window, not derived from
        the events — a quiet week we asked for is still covered (same rule as the FF source). Raises on
        a network/parse failure; the caller decides whether to swallow it."""
        cc = list(countries) if countries is not None else self._countries
        raw = self._get(from_ms, to_ms, cc)
        events = self.parse_result(raw)
        return FetchResult(events=events, covered_ranges=[(int(from_ms), int(to_ms))])

    # --- network (the only impure part) ----------------------------------------------------------

    def _get(self, from_ms: int, to_ms: int, countries: Sequence[str]) -> list:
        query = urllib.parse.urlencode(
            {
                "from": _iso_z(from_ms),
                "to": _iso_z(to_ms),
                "countries": ",".join(countries),
            }
        )
        req = urllib.request.Request(f"{self._endpoint}?{query}", headers=_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError) as exc:
            raise RuntimeError(f"TradingView calendar fetch failed: {exc}") from exc
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise RuntimeError(f"TradingView calendar returned non-ok status: {payload!r:.200}")
        result = payload.get("result")
        return result if isinstance(result, list) else []

    # --- parsing (pure — unit-tested offline on a saved sample) ----------------------------------

    @classmethod
    def parse_result(cls, raw: list) -> List[NewsEvent]:
        """Normalise a list of raw TradingView rows into NewsEvent objects, skipping any without a
        parseable date. Pure and network-free so it is tested against a saved JSON sample."""
        out: List[NewsEvent] = []
        for row in raw:
            ts = _parse_date(row.get("date"))
            if ts is None:
                continue
            unit = row.get("unit")
            out.append(
                NewsEvent(
                    timestamp_ms=ts,
                    currency=(row.get("currency") or "").strip(),
                    impact=_IMPORTANCE.get(row.get("importance"), Impact.NONE),
                    title=(row.get("title") or "").strip(),
                    forecast=_fmt(row.get("forecast"), unit),
                    previous=_fmt(row.get("previous"), unit),
                    actual=_fmt(row.get("actual"), unit),
                    is_holiday=False,  # this source carries no holiday rows
                    category=_category_label(row.get("category")),
                )
            )
        return out


# --- module helpers (pure) -----------------------------------------------------------------------


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _week_start_ms(ms: int) -> int:
    """Monday 00:00:00 UTC of the week containing `ms`."""
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    monday = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(monday.timestamp() * 1000)


def _iso_z(ms: int) -> str:
    """Epoch ms → '2026-07-13T00:00:00.000Z' (the format the endpoint expects)."""
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _parse_date(s: Optional[str]) -> Optional[int]:
    """UTC ISO 8601 (trailing 'Z' or a numeric offset) → epoch ms. None if missing/unparseable."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _fmt(value, unit: Optional[str]) -> Optional[str]:
    """A raw TradingView value (+unit) → the display string NewsEvent stores, or None.

    TradingView gives the display magnitude as a number (e.g. 2.8 with unit '%', or -3.018 with unit
    'A$') plus the `unit`. We fold them into one human string: '2.8%', '168K', 'A$-3.018'. Both the
    forecast and the actual of one event share a unit, so a consumer can still parse the leading number
    and compare them for a beat/miss without needing the unit expanded.
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
    elif isinstance(value, (int, float)):
        s = f"{value:g}"  # trims trailing zeros: 34 -> '34', 2.80 -> '2.8', -3.018 -> '-3.018'
    else:
        return None
    if not s:
        return None
    u = (unit or "").strip()
    if not u:
        return s
    if u == "%":
        return f"{s}%"
    if u.endswith("$") or u in {"€", "£", "¥"}:  # currency-symbol units read better as a prefix
        return f"{u}{s}"
    return f"{s}{u}"  # scale/suffix units: '168' + 'K' -> '168K'
