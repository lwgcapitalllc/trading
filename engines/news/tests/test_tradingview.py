"""
Offline parser tests for TradingViewSource.

These never touch the network — they feed a saved slice of the real TradingView `result` schema
(confirmed live 2026-07-17) through the pure `parse_result` classmethod and pin the normalisation:
`currency` (not `country`) → currency, importance 1/0/-1 → Impact, `date` (trailing Z) → UTC epoch-ms,
value+unit → display string, null → None, unparseable date skipped, is_holiday always False. The live
endpoint itself is exercised by the smoke test in the build notes.
"""

from datetime import datetime, timezone

from news import Impact
from news.sources.tradingview import TradingViewSource, _fmt

# A saved slice: a released % print, a currency-unit row (display-scaled), a suffix-unit row, an
# unreleased high-impact speech (all values null), a low-impact row, and a row with no date.
SAMPLE = [
    {"title": "Inflation Rate YoY", "country": "US", "currency": "USD",
     "date": "2026-07-14T12:30:00.000Z", "importance": 1, "unit": "%", "category": "prce",
     "actual": 3.5, "forecast": 3.8, "previous": 4.2,
     "actualRaw": 3.5, "forecastRaw": 3.8, "previousRaw": 4.2, "period": "Jun"},
    {"title": "Balance of Trade", "country": "CN", "currency": "CNY",
     "date": "2026-07-14T03:00:00.000Z", "importance": 1, "unit": "$",
     "actual": 125.62, "forecast": 121, "previous": 105.43, "period": "Jun"},
    {"title": "Non Farm Payrolls", "country": "US", "currency": "USD",
     "date": "2026-07-03T12:30:00.000Z", "importance": 1, "unit": "K",
     "actual": 206, "forecast": 168, "previous": 199, "period": "Jun"},
    {"title": "Fed Chair Speech", "country": "US", "currency": "USD",
     "date": "2026-07-14T18:00:00.000Z", "importance": 1, "unit": None,
     "actual": None, "forecast": None, "previous": None, "period": ""},
    {"title": "10-Year Bund Auction", "country": "EU", "currency": "EUR",
     "date": "2026-07-14T10:10:00.000Z", "importance": -1, "unit": "%",
     "actual": 2.808, "forecast": None, "previous": 2.935},
    {"title": "No Date Row", "country": "US", "currency": "USD",
     "date": None, "importance": 0},
]


def _utc_ms(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


def test_parses_core_fields_and_utc_z_time():
    events = TradingViewSource.parse_result(SAMPLE)
    cpi = next(e for e in events if e.title == "Inflation Rate YoY")
    assert cpi.currency == "USD"          # the ISO `currency`, NOT the `country` "US"
    assert cpi.impact == Impact.HIGH
    assert cpi.actual == "3.5%" and cpi.forecast == "3.8%" and cpi.previous == "4.2%"
    assert cpi.is_holiday is False
    assert cpi.category == "Prices"          # "prce" code -> human label for the dropdown
    assert cpi.timestamp_ms == _utc_ms(2026, 7, 14, 12, 30)


def test_importance_mapping():
    by_title = {e.title: e for e in TradingViewSource.parse_result(SAMPLE)}
    assert by_title["Inflation Rate YoY"].impact == Impact.HIGH      # 1
    assert by_title["10-Year Bund Auction"].impact == Impact.LOW     # -1
    # importance 0 would be MEDIUM, but the only importance-0 row here has no date and is skipped.


def test_unit_formatting():
    by_title = {e.title: e for e in TradingViewSource.parse_result(SAMPLE)}
    assert by_title["Balance of Trade"].actual == "$125.62"   # currency unit prefixes
    assert by_title["Non Farm Payrolls"].actual == "206K"     # scale unit suffixes
    assert by_title["Fed Chair Speech"].actual is None        # null stays None


def test_null_values_become_none():
    speech = next(e for e in TradingViewSource.parse_result(SAMPLE) if e.title == "Fed Chair Speech")
    assert speech.forecast is None and speech.previous is None and speech.actual is None


def test_undated_row_is_skipped():
    events = TradingViewSource.parse_result(SAMPLE)
    assert all(e.title != "No Date Row" for e in events)
    assert len(events) == len(SAMPLE) - 1


def test_fmt_helper_edges():
    assert _fmt(None, "%") is None
    assert _fmt(34, None) == "34"            # trailing zeros trimmed via %g
    assert _fmt(2.80, "%") == "2.8%"
    assert _fmt(-3.018, "$") == "$-3.018"    # currency prefix keeps the sign readable
    assert _fmt(168, "K") == "168K"
