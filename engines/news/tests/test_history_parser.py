"""
Offline parser test for ForexFactoryHistorySource (the website-scrape source).

Feeds a saved slice of the real calendar-page format — a JS assignment whose top-level keys are
UNQUOTED (`days: [...]`) but whose `days` value is a proper JSON array — through the pure
`parse_page`. Pins: bracket-matching the days array out of the surrounding JS, the `dateline`
(UTC unix seconds) -> ms conversion, currency/impact/title, and empty->None. No network.
"""

from news import Impact
from news.sources.forex_factory_history import ForexFactoryHistorySource, _months_between

# Mirrors the live shape: window assignment, unquoted outer keys, HTML-escaped date, a trailing
# `someOtherKey: [1,2,3]` array to prove bracket-matching stops at the DAYS array's close, not that.
SAMPLE_HTML = r"""
<script>
window.calendarComponentStates = [];
calendarComponentStates[1] = {
days: [{"date":"Mon <span>Feb 3<\/span>","dateline":1738562400,"events":[
  {"id":1,"name":"ISM Manufacturing PMI","currency":"USD","dateline":1738594800,"impactName":"high","actual":"50.9","forecast":"49.3","previous":"49.3"},
  {"id":2,"name":"Bank Holiday","currency":"CAD","dateline":1738562400,"impactName":"holiday","actual":"","forecast":"","previous":""}
]}],
someOtherKey: [1,2,3],
flag: true
};
</script>
"""


def test_parse_page_extracts_events_with_utc_ms():
    events = ForexFactoryHistorySource.parse_page(SAMPLE_HTML)
    assert len(events) == 2
    ism = next(e for e in events if e.title == "ISM Manufacturing PMI")
    assert ism.currency == "USD"
    assert ism.impact == Impact.HIGH
    assert ism.timestamp_ms == 1738594800 * 1000       # dateline seconds -> ms
    assert ism.actual == "50.9" and ism.forecast == "49.3"


def test_parse_page_impact_and_empty_fields():
    events = ForexFactoryHistorySource.parse_page(SAMPLE_HTML)
    hol = next(e for e in events if e.title == "Bank Holiday")
    assert hol.impact == Impact.NONE                    # holiday -> NONE magnitude
    assert hol.is_holiday is True                        # ...but flagged as a bank holiday
    assert hol.actual is None and hol.forecast is None and hol.previous is None


def test_parse_page_returns_empty_on_junk():
    assert ForexFactoryHistorySource.parse_page("<html>no calendar here</html>") == []


def test_months_between_spans_inclusive():
    import datetime as _dt
    def ms(y, m): return int(_dt.datetime(y, m, 15, tzinfo=_dt.timezone.utc).timestamp() * 1000)
    assert _months_between(ms(2024, 11), ms(2025, 2)) == [(2024, 11), (2024, 12), (2025, 1), (2025, 2)]
    assert _months_between(ms(2025, 3), ms(2025, 3)) == [(2025, 3)]
