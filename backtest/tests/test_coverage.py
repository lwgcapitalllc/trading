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


# ── missing(): the GAPS, so a near-miss costs a near-miss ────────────────────────
# `covered()` answers yes/no, and `_load_base` used to turn a No into a full refetch of the
# whole window. Since `_covered_end` deliberately never claims today, a window ending today
# is never fully covered — so every request re-pulled everything to obtain one day. Measured
# on the live cache: 27.8s vs 0.39s for the same span ending yesterday.

def test_nothing_recorded_means_the_whole_window_is_missing(tmp_path):
    cov = RangeCoverage(tmp_path)
    assert cov.missing("XAUUSD", "M15", "2026-01-01", "2026-01-31") == [
        ("2026-01-01", "2026-01-31")]


def test_a_fully_covered_window_is_missing_nothing(tmp_path):
    cov = RangeCoverage(tmp_path)
    cov.record("XAUUSD", "M15", "2026-01-01", "2026-01-31")
    assert cov.missing("XAUUSD", "M15", "2026-01-05", "2026-01-20") == []


def test_only_the_uncovered_tail_comes_back(tmp_path):
    cov = RangeCoverage(tmp_path)
    cov.record("XAUUSD", "M15", "2020-01-01", "2026-08-05")
    assert cov.missing("XAUUSD", "M15", "2020-01-01", "2026-08-06") == [
        ("2026-08-06", "2026-08-06")]


def test_the_uncovered_head_comes_back(tmp_path):
    cov = RangeCoverage(tmp_path)
    cov.record("XAUUSD", "M15", "2026-01-10", "2026-01-31")
    assert cov.missing("XAUUSD", "M15", "2026-01-01", "2026-01-31") == [
        ("2026-01-01", "2026-01-09")]


def test_a_hole_between_two_fetched_spans_comes_back_alone(tmp_path):
    cov = RangeCoverage(tmp_path)
    cov.record("XAUUSD", "M15", "2026-01-01", "2026-01-10")
    cov.record("XAUUSD", "M15", "2026-02-01", "2026-02-10")
    assert cov.missing("XAUUSD", "M15", "2026-01-01", "2026-02-10") == [
        ("2026-01-11", "2026-01-31")]


def test_several_holes_all_come_back_in_order(tmp_path):
    cov = RangeCoverage(tmp_path)
    cov.record("XAUUSD", "M15", "2026-01-05", "2026-01-10")
    cov.record("XAUUSD", "M15", "2026-01-20", "2026-01-25")
    assert cov.missing("XAUUSD", "M15", "2026-01-01", "2026-01-31") == [
        ("2026-01-01", "2026-01-04"),
        ("2026-01-11", "2026-01-19"),
        ("2026-01-26", "2026-01-31"),
    ]


def test_missing_is_the_exact_complement_of_covered(tmp_path):
    # The two must never disagree: a day `covered()` says we hold must not appear in a gap,
    # and a day it says we lack must. Walked day by day rather than asserted in prose.
    from datetime import date, timedelta
    cov = RangeCoverage(tmp_path)
    cov.record("XAUUSD", "M15", "2026-01-05", "2026-01-10")
    cov.record("XAUUSD", "M15", "2026-01-20", "2026-01-25")
    gaps = cov.missing("XAUUSD", "M15", "2026-01-01", "2026-01-31")

    def in_a_gap(day: str) -> bool:
        return any(lo <= day <= hi for lo, hi in gaps)

    d = date(2026, 1, 1)
    while d <= date(2026, 1, 31):
        day = d.isoformat()
        assert in_a_gap(day) != cov.covered("XAUUSD", "M15", day, day), day
        d += timedelta(days=1)


def test_an_inverted_window_asks_for_nothing(tmp_path):
    cov = RangeCoverage(tmp_path)
    assert cov.missing("XAUUSD", "M15", "2026-02-01", "2026-01-01") == []


def test_coverage_outside_the_window_is_ignored(tmp_path):
    cov = RangeCoverage(tmp_path)
    cov.record("XAUUSD", "M15", "2020-01-01", "2020-12-31")
    assert cov.missing("XAUUSD", "M15", "2026-01-01", "2026-01-05") == [
        ("2026-01-01", "2026-01-05")]
