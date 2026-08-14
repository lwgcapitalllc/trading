"""
Tests for the accumulating EventStore — the mechanism behind "history grows forward".

Uses a temp file (no network, no touching the real data/ store). Pins: round-trip, de-dupe by
(time, currency, title) with `actual` overwriting a blank pre-release row, covered-range merging,
and the coverage-start boundary a backtest reads.
"""

from news import EventStore, Impact, NewsEvent


def _ev(ts, title, actual=None):
    return NewsEvent(
        timestamp_ms=ts, currency="USD", impact=Impact.HIGH, title=title, actual=actual
    )


def test_upsert_roundtrip_and_dedupe(tmp_path):
    store = EventStore(tmp_path / "events.json")
    store.upsert([_ev(1000, "A"), _ev(2000, "B")], covered_ranges=[(1000, 2000)])
    # Re-fetch of A now carries `actual` -> replaces, does not duplicate.
    store.upsert([_ev(1000, "A", actual="5.0%")], covered_ranges=[(1000, 2000)])
    events, ranges = store.load()
    assert [e.title for e in events] == ["A", "B"]  # no dupe
    assert next(e for e in events if e.title == "A").actual == "5.0%"  # updated
    assert ranges == [(1000, 2000)]


def test_covered_ranges_merge_across_fetches(tmp_path):
    store = EventStore(tmp_path / "events.json")
    store.upsert([_ev(1000, "A")], covered_ranges=[(1000, 5000)])
    store.upsert([_ev(6000, "B")], covered_ranges=[(4000, 9000)])  # overlaps prior -> merges
    _, ranges = store.load()
    assert ranges == [(1000, 9000)]
    assert store.coverage_start_ms() == 1000


def test_empty_store_loads_clean(tmp_path):
    store = EventStore(tmp_path / "nope.json")
    events, ranges = store.load()
    assert events == [] and ranges == []
    assert store.coverage_start_ms() is None
