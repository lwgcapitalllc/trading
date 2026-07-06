"""
Offline parser tests for ForexFactorySource.

These never touch the network — they feed a saved sample of the real faireconomy JSON schema
through the pure `parse_entries` classmethod and pin the normalisation (currency, impact, UTC
epoch-ms date, empty->None, holiday->NONE, unparseable date skipped). The live feed itself is
exercised by tools/fetch_smoke.py.
"""

from datetime import datetime, timezone

from news import Impact
from news.sources.forex_factory import ForexFactorySource

# A saved slice of the real feed schema (confirmed live 2026-07-05), plus edge rows: a released
# event carrying `actual`, a Holiday, an empty-impact row, and a row with no date.
SAMPLE = [
    {"title": "Non-Farm Employment Change", "country": "USD",
     "date": "2026-07-03T08:30:00-04:00", "impact": "High",
     "forecast": "168K", "previous": "199K", "actual": "206K"},
    {"title": "German Factory Orders m/m", "country": "EUR",
     "date": "2026-07-06T02:00:00-04:00", "impact": "Low",
     "forecast": "1.1%", "previous": "-3.8%"},
    {"title": "FOMC Meeting Minutes", "country": "USD",
     "date": "2026-07-08T14:00:00-04:00", "impact": "High",
     "forecast": "", "previous": ""},
    {"title": "Bank Holiday", "country": "CAD",
     "date": "2026-07-01T00:00:00-04:00", "impact": "Holiday",
     "forecast": "", "previous": ""},
    {"title": "Something Unrated", "country": "GBP",
     "date": "2026-07-07T05:00:00-04:00", "impact": "",
     "forecast": "", "previous": ""},
    {"title": "Tentative Event No Time", "country": "USD",
     "date": None, "impact": "Medium"},
]


def _utc_ms(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


def test_parses_core_fields_and_utc_time():
    events = ForexFactorySource.parse_entries(SAMPLE)
    nfp = next(e for e in events if e.title == "Non-Farm Employment Change")
    assert nfp.currency == "USD"
    assert nfp.impact == Impact.HIGH
    assert nfp.forecast == "168K" and nfp.previous == "199K" and nfp.actual == "206K"
    # 08:30 at -04:00 == 12:30 UTC
    assert nfp.timestamp_ms == _utc_ms(2026, 7, 3, 12, 30)


def test_empty_strings_become_none():
    events = ForexFactorySource.parse_entries(SAMPLE)
    fomc = next(e for e in events if e.title == "FOMC Meeting Minutes")
    assert fomc.forecast is None and fomc.previous is None and fomc.actual is None


def test_impact_normalisation():
    events = ForexFactorySource.parse_entries(SAMPLE)
    by_title = {e.title: e for e in events}
    assert by_title["German Factory Orders m/m"].impact == Impact.LOW
    assert by_title["Bank Holiday"].impact == Impact.NONE       # Holiday -> NONE magnitude...
    assert by_title["Bank Holiday"].is_holiday is True          # ...but flagged as a bank holiday
    assert by_title["Something Unrated"].impact == Impact.NONE  # "" -> NONE
    assert by_title["Something Unrated"].is_holiday is False


def test_undated_row_is_skipped():
    events = ForexFactorySource.parse_entries(SAMPLE)
    assert all(e.title != "Tentative Event No Time" for e in events)
    assert len(events) == len(SAMPLE) - 1
