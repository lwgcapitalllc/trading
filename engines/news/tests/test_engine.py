"""
Hand-traced tests for the news engine's pure core.

There is no Pine source for the economic calendar, so full parity is a live feed smoke test
(tools/fetch_smoke.py). These lock the deterministic mechanics — blackout windows, coverage
gating, the next/active/last phases, edges, policy filtering, window merging — so a regression is
caught without the network.
"""

from datetime import datetime, timezone

import pytest
from news import Impact, NewsEngine, NewsEvent, NewsPolicy

_UTC = timezone.utc


def ms(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=_UTC).timestamp() * 1000)


def ev(y, mo, d, h, mi, currency="USD", impact=Impact.HIGH, title="CPI"):
    return NewsEvent(
        timestamp_ms=ms(y, mo, d, h, mi), currency=currency, impact=impact, title=title
    )


# --- blackout window ----------------------------------------------------------------------------


def test_blackout_window_inclusive_edges():
    e = ev(2026, 7, 6, 12, 30)  # 12:30 UTC
    eng = NewsEngine([e], policy=NewsPolicy.usd(pre_minutes=30, post_minutes=30))
    assert not eng.update(0, ms(2026, 7, 6, 11, 59)).in_blackout  # 31 min before
    assert eng.update(1, ms(2026, 7, 6, 12, 0)).in_blackout  # exactly -30 (inclusive)
    assert eng.update(2, ms(2026, 7, 6, 12, 30)).in_blackout  # at the event
    assert eng.update(3, ms(2026, 7, 6, 13, 0)).in_blackout  # exactly +30 (inclusive)
    assert not eng.update(4, ms(2026, 7, 6, 13, 1)).in_blackout  # 31 min after


def test_overlapping_windows_merge_into_one_blackout():
    # Two events 20 min apart with ±30 windows -> one continuous blackout, no gap between them.
    events = [ev(2026, 7, 6, 12, 0, title="A"), ev(2026, 7, 6, 12, 20, title="B")]
    eng = NewsEngine(events, policy=NewsPolicy.usd(pre_minutes=30, post_minutes=30))
    # 12:10 is after A's +? no, between them — inside both -> blackout.
    assert eng.update(0, ms(2026, 7, 6, 12, 10)).in_blackout


# --- coverage gating ----------------------------------------------------------------------------


def test_no_coverage_forces_filter_off():
    e = ev(2026, 7, 6, 12, 30)
    eng = NewsEngine(
        [e],
        policy=NewsPolicy.usd(),
        covered_ranges=[(ms(2026, 7, 6, 0, 0), ms(2026, 7, 6, 23, 59))],
    )
    # A bar the day BEFORE any coverage: no data -> not covered -> never blacked out.
    out = eng.update(0, ms(2026, 7, 5, 12, 30))
    assert out.has_coverage is False
    assert out.in_blackout is False


def test_quiet_but_covered_week_is_not_a_gap():
    # Covered range with NO relevant event inside: has_coverage True, but in_blackout False.
    eng = NewsEngine(
        [ev(2026, 7, 6, 12, 30, impact=Impact.LOW)],  # low impact -> not relevant to usd() policy
        policy=NewsPolicy.usd(),
        covered_ranges=[(ms(2026, 7, 6, 0, 0), ms(2026, 7, 6, 23, 59))],
    )
    out = eng.update(0, ms(2026, 7, 6, 12, 30))
    assert out.has_coverage is True
    assert out.in_blackout is False


def test_no_covered_ranges_means_unbounded_coverage():
    # None => "coverage unknown, don't gate": has_coverage always True, no boundary reported.
    a, b = ev(2026, 7, 6, 12, 0, title="A"), ev(2026, 7, 8, 12, 0, title="B")
    eng = NewsEngine([a, b], policy=NewsPolicy.usd())  # no covered_ranges
    assert eng.coverage_start_ms is None
    assert eng.update(0, ms(2026, 7, 1, 0, 0)).has_coverage is True  # even years off
    assert eng.update(1, ms(2026, 7, 6, 11, 45)).in_blackout is True  # blackout still works


def test_known_empty_coverage_makes_filter_inert():
    # [] => known-empty (an empty store): never covered, so a backtest trades normally throughout.
    eng = NewsEngine([ev(2026, 7, 6, 12, 30)], policy=NewsPolicy.usd(), covered_ranges=[])
    out = eng.update(0, ms(2026, 7, 6, 12, 30))
    assert out.has_coverage is False
    assert out.in_blackout is False
    assert eng.coverage_start_ms is None


def test_empty_engine_has_no_events():
    eng = NewsEngine([], policy=NewsPolicy.usd(), covered_ranges=[])
    out = eng.update(0, ms(2026, 7, 6, 12, 30))
    assert out.has_coverage is False and out.in_blackout is False
    assert out.next_event is None and out.last_event is None


# --- phases: next / active / last ---------------------------------------------------------------


def test_phases_next_active_last():
    past = ev(2026, 7, 6, 8, 30, title="NFP")
    soon = ev(2026, 7, 6, 12, 30, title="CPI")
    eng = NewsEngine([past, soon], policy=NewsPolicy.usd())

    out = eng.update(0, ms(2026, 7, 6, 10, 0))  # between the two, outside both windows
    assert out.next_event.title == "CPI"
    assert out.minutes_to_next == pytest.approx(150.0)  # 10:00 -> 12:30
    assert out.last_event.title == "NFP"
    assert out.minutes_since_last == pytest.approx(90.0)  # 08:30 -> 10:00
    assert out.active_event is None  # not inside either ±30 window

    out2 = eng.update(1, ms(2026, 7, 6, 12, 20))  # inside CPI's window
    assert out2.active_event.title == "CPI"
    assert out2.in_blackout is True


def test_active_prefers_higher_impact_on_overlap():
    # A medium and a high event both cover 12:00; active should pick the HIGH one.
    med = NewsEvent(ms(2026, 7, 6, 12, 5), "USD", Impact.MEDIUM, "med")
    high = NewsEvent(ms(2026, 7, 6, 11, 55), "USD", Impact.HIGH, "high")
    eng = NewsEngine(
        [med, high], policy=NewsPolicy(currencies=frozenset({"USD"}), min_impact=Impact.MEDIUM)
    )
    out = eng.update(0, ms(2026, 7, 6, 12, 0))
    assert out.active_event.title == "high"


# --- edges: entered / exited / released ---------------------------------------------------------


def test_blackout_enter_and_exit_edges():
    e = ev(2026, 7, 6, 12, 30)
    eng = NewsEngine([e], policy=NewsPolicy.usd(pre_minutes=30, post_minutes=30))
    a = eng.update(0, ms(2026, 7, 6, 11, 55))  # outside
    assert not a.entered_blackout and not a.exited_blackout
    b = eng.update(1, ms(2026, 7, 6, 12, 5))  # crossed in
    assert b.entered_blackout and not b.exited_blackout
    c = eng.update(2, ms(2026, 7, 6, 12, 25))  # still in
    assert not c.entered_blackout and not c.exited_blackout
    d = eng.update(3, ms(2026, 7, 6, 13, 5))  # crossed out
    assert d.exited_blackout and not d.entered_blackout


def test_released_edge_fires_once_when_event_time_is_crossed():
    e = ev(2026, 7, 6, 12, 30)
    eng = NewsEngine([e], policy=NewsPolicy.usd())
    eng.update(0, ms(2026, 7, 6, 12, 25))  # before the event time
    crossed = eng.update(1, ms(2026, 7, 6, 12, 35))  # bar straddles the event time
    assert [x.title for x in crossed.released] == ["CPI"]
    after = eng.update(2, ms(2026, 7, 6, 12, 40))  # already released -> not again
    assert after.released == []


def test_first_bar_never_reports_released():
    e = ev(2026, 7, 6, 12, 30)
    eng = NewsEngine([e], policy=NewsPolicy.usd())
    out = eng.update(0, ms(2026, 7, 6, 13, 0))  # first bar is already past the event
    assert out.released == []  # no prior bar -> nothing "newly" released


# --- policy filtering ---------------------------------------------------------------------------


def test_policy_filters_currency_and_impact():
    eur = ev(2026, 7, 6, 12, 30, currency="EUR", title="EUR CPI")
    usd_low = ev(2026, 7, 6, 12, 30, currency="USD", impact=Impact.LOW, title="USD minor")
    usd_high = ev(2026, 7, 6, 12, 30, currency="USD", impact=Impact.HIGH, title="USD NFP")
    eng = NewsEngine([eur, usd_low, usd_high], policy=NewsPolicy.usd())  # USD + HIGH only
    out = eng.update(0, ms(2026, 7, 6, 12, 30))
    assert out.active_event.title == "USD NFP"
    assert out.next_event.title == "USD NFP"


def test_empty_currency_set_means_all_currencies():
    eur = ev(2026, 7, 6, 12, 30, currency="EUR", title="EUR CPI")
    eng = NewsEngine([eur], policy=NewsPolicy(currencies=frozenset(), min_impact=Impact.HIGH))
    assert eng.update(0, ms(2026, 7, 6, 12, 20)).in_blackout is True


# --- bank holidays (whole-day blackout) ---------------------------------------------------------


def _holiday(y, mo, d, currency="USD", title="Bank Holiday"):
    # FF holidays carry impact NONE + is_holiday True; the time-of-day is irrelevant (whole day).
    return NewsEvent(ms(y, mo, d, 0, 0), currency, Impact.NONE, title, is_holiday=True)


def test_holiday_is_reported_but_not_blocked_by_default():
    # Default: the engine TELLS you it's a holiday, but does NOT force a blackout — the bot decides.
    eng = NewsEngine(
        [_holiday(2026, 7, 3)], policy=NewsPolicy.usd()
    )  # block_holidays defaults False
    out = eng.update(0, ms(2026, 7, 3, 12, 0))
    assert out.is_holiday is True
    assert out.active_holiday.title == "Bank Holiday"
    assert out.in_blackout is False  # reported, not blocked


def test_holiday_blocks_whole_day_only_when_opted_in():
    eng = NewsEngine([_holiday(2026, 7, 3)], policy=NewsPolicy.usd(block_holidays=True))
    for h in (0, 9, 15, 23):  # any hour on the holiday date
        out = eng.update(h, ms(2026, 7, 3, h, 0))
        assert out.in_blackout is True and out.is_holiday is True
    clear = eng.update(99, ms(2026, 7, 4, 12, 0))  # next day clear
    assert clear.in_blackout is False and clear.is_holiday is False


def test_holiday_reporting_respects_currency_filter():
    # A UK holiday is not "my" holiday for a USD-only (gold) bot — not even reported.
    eng = NewsEngine(
        [_holiday(2026, 7, 3, currency="GBP")], policy=NewsPolicy.usd(block_holidays=True)
    )
    out = eng.update(0, ms(2026, 7, 3, 12, 0))
    assert out.in_blackout is False and out.is_holiday is False


def test_holiday_not_reported_where_no_coverage():
    eng = NewsEngine(
        [_holiday(2026, 7, 3)],
        policy=NewsPolicy.usd(block_holidays=True),
        covered_ranges=[(ms(2026, 7, 4, 0, 0), ms(2026, 7, 5, 0, 0))],
    )
    out = eng.update(0, ms(2026, 7, 3, 12, 0))  # holiday date is outside coverage
    assert out.has_coverage is False and out.in_blackout is False and out.is_holiday is False
