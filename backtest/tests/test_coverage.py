"""Fetched-range coverage bookkeeping."""

from backtest.data.coverage import RangeCoverage, _merge_intervals


def test_uncovered_until_recorded(tmp_path):
    cov = RangeCoverage(tmp_path)
    assert not cov.covered("XAUUSD.s", "M5", "2026-01-01", "2026-01-31")
    cov.record("XAUUSD.s", "M5", "2026-01-01", "2026-01-31")
    assert cov.covered("XAUUSD.s", "M5", "2026-01-05", "2026-01-20")


def test_weekend_inside_span_is_covered_without_bars(tmp_path):
    cov = RangeCoverage(tmp_path)
    cov.record("XAUUSD.s", "M5", "2026-01-01", "2026-12-31")
    # A weekend with no bars is still "covered" — we won't refetch it.
    assert cov.covered("XAUUSD.s", "M5", "2026-06-06", "2026-06-07")


def test_partial_overlap_is_not_covered(tmp_path):
    cov = RangeCoverage(tmp_path)
    cov.record("XAUUSD.s", "M5", "2026-01-01", "2026-06-30")
    assert not cov.covered("XAUUSD.s", "M5", "2026-06-01", "2026-07-15")


def test_key_isolation_between_symbol_and_tf(tmp_path):
    cov = RangeCoverage(tmp_path)
    cov.record("XAUUSD.s", "M5", "2026-01-01", "2026-01-31")
    assert not cov.covered("XAUUSD.s", "M15", "2026-01-05", "2026-01-06")
    assert not cov.covered("EURUSD", "M5", "2026-01-05", "2026-01-06")


def test_merge_intervals_joins_touching_and_overlapping():
    merged = _merge_intervals([
        ["2026-01-01", "2026-01-31"],
        ["2026-02-01", "2026-02-28"],   # touches Jan (adjacent by string compare)
        ["2026-02-15", "2026-03-15"],   # overlaps Feb
        ["2026-06-01", "2026-06-30"],   # disjoint
    ])
    assert merged == [
        ["2026-01-01", "2026-03-15"],
        ["2026-06-01", "2026-06-30"],
    ]


def test_recording_extends_coverage(tmp_path):
    cov = RangeCoverage(tmp_path)
    cov.record("XAUUSD.s", "M5", "2026-01-01", "2026-03-31")
    cov.record("XAUUSD.s", "M5", "2026-03-15", "2026-06-30")
    assert cov.covered("XAUUSD.s", "M5", "2026-01-10", "2026-06-20")
