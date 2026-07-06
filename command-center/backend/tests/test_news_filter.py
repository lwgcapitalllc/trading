"""
Tests for services.news_filter — tagging a backtest's trades against the canonical news engine.

Uses synthetic events (a fake store), so it never touches the network or the real calendar cache.
Locks the two rules the user set: high-impact news blocks 15 min before → 30 min after, and bank
holidays are always flagged (and kept separable from news so the UI can remove them unconditionally).
"""

from datetime import datetime, timezone

from services import news_filter
from news import Impact, NewsEvent, NewsPolicy  # importable: news_filter put engines/ on sys.path

_UTC = timezone.utc


def ms(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=_UTC).timestamp() * 1000)


class _FakeStore:
    """Stand-in for EventStore — hands load_engine a fixed (events, covered_ranges)."""

    def __init__(self, events, covered):
        self._events, self._covered = events, covered

    def load(self):
        return self._events, self._covered


# High-impact USD CPI at 13:30 UTC on 2025-02-12; a USD bank holiday on 2025-02-17.
_CPI = NewsEvent(ms(2025, 2, 12, 13, 30), "USD", Impact.HIGH, "CPI")
_HOLIDAY = NewsEvent(ms(2025, 2, 17, 0, 0), "USD", Impact.NONE, "Presidents Day", is_holiday=True)
_FEB = [(ms(2025, 2, 1, 0, 0), ms(2025, 2, 28, 23, 59))]


def _store():
    return _FakeStore([_CPI, _HOLIDAY], _FEB)


def _tags(trades):
    return news_filter.build_report(trades, store=_store())["trades"]


def test_window_is_15_before_and_30_after():
    trades = [
        {"index": 1, "entry_ms": ms(2025, 2, 12, 13, 15)},   # exactly 15 min before -> in
        {"index": 2, "entry_ms": ms(2025, 2, 12, 13, 14)},   # 16 min before -> out
        {"index": 3, "entry_ms": ms(2025, 2, 12, 14, 0)},    # exactly 30 min after -> in
        {"index": 4, "entry_ms": ms(2025, 2, 12, 14, 1)},    # 31 min after -> out
    ]
    got = [t["in_news"] for t in _tags(trades)]
    assert got == [True, False, True, False]


def test_output_order_matches_input_order():
    # Fed out of time order; the returned list must stay in input order for the UI to zip by index.
    trades = [
        {"index": 9, "entry_ms": ms(2025, 2, 12, 14, 1)},    # clean (out of window)
        {"index": 8, "entry_ms": ms(2025, 2, 12, 13, 30)},   # at the event -> news
    ]
    out = _tags(trades)
    assert [t["index"] for t in out] == [9, 8]
    assert [t["in_news"] for t in out] == [False, True]


def test_holiday_is_flagged_and_separate_from_news():
    trades = [{"index": 1, "entry_ms": ms(2025, 2, 17, 15, 0)}]  # any time on the holiday date
    t = _tags(trades)[0]
    assert t["in_holiday"] is True
    assert t["in_news"] is False
    assert t["title"] == "Presidents Day"


def test_quiet_time_is_untouched():
    trades = [{"index": 1, "entry_ms": ms(2025, 2, 12, 9, 0)}]  # covered, but no event near
    t = _tags(trades)[0]
    assert t["in_coverage"] is True
    assert t["in_news"] is False and t["in_holiday"] is False


def test_outside_coverage_is_left_untagged():
    trades = [{"index": 1, "entry_ms": ms(2025, 1, 1, 13, 30)}]  # January — before Feb coverage
    t = _tags(trades)[0]
    assert t["in_coverage"] is False
    assert t["in_news"] is False and t["in_holiday"] is False


def test_missing_timestamp_is_left_untagged():
    trades = [{"index": 1, "entry_ms": None}]
    t = _tags(trades)[0]
    assert t["in_coverage"] is False and t["in_news"] is False


def test_report_counts_and_coverage_boundary():
    trades = [
        {"index": 1, "entry_ms": ms(2025, 2, 12, 13, 30)},   # news
        {"index": 2, "entry_ms": ms(2025, 2, 17, 15, 0)},    # holiday
        {"index": 3, "entry_ms": ms(2025, 2, 12, 9, 0)},     # clean
    ]
    rep = news_filter.build_report(trades, store=_store())
    assert rep["has_data"] is True
    assert rep["news_trade_count"] == 1
    assert rep["holiday_trade_count"] == 1
    assert rep["coverage_start_ms"] == _FEB[0][0]
    assert rep["pre_minutes"] == 15 and rep["post_minutes"] == 30


def test_empty_cache_reports_no_data():
    rep = news_filter.build_report(
        [{"index": 1, "entry_ms": ms(2025, 2, 12, 13, 30)}],
        store=_FakeStore([], []),
    )
    assert rep["has_data"] is False
    assert rep["trades"][0]["in_news"] is False


def test_defaults_are_15_and_30():
    p = news_filter.make_policy()
    assert (p.pre_minutes, p.post_minutes) == (15, 30)
    assert p.block_holidays is True
    assert p.min_impact == Impact.HIGH
