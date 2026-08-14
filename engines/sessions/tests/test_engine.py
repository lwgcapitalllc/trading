"""
Hand-traced tests for the sessions engine.

These pin the clock logic against explicit epoch timestamps: session-window membership (each window
in its own city's clock, DST-aware, plus the overnight-wrap rule the parser still supports),
kill-zone windows and their DST behaviour,
the running session high/low + open/close edges, the NY opening range, and new-day/weekday flags.
Full Pine-parity validation lives in tools/compare_sessions.py against a real TradingView export;
these tests lock the mechanics so a regression is caught without an export.
"""

from datetime import datetime, timedelta, timezone

import pytest

from sessions import SessionEngine, SessionSpec
from sessions.engine import _resolve_tz, _pine_dayofweek, _in_window

_UTC = timezone.utc


def ms(tz_name, y, mo, d, h, mi):
    """Epoch milliseconds for a wall-clock time in the given timezone (DST-aware for IANA names)."""
    dt = datetime(y, mo, d, h, mi, tzinfo=_resolve_tz(tz_name))
    return int(dt.timestamp() * 1000)


def ms_utc(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=_UTC).timestamp() * 1000)


# ── timezone / clock helpers ────────────────────────────────────────────────

def test_resolve_gmt_offsets():
    assert _resolve_tz("GMT-4").utcoffset(None) == timedelta(hours=-4)
    assert _resolve_tz("GMT+5:30").utcoffset(None) == timedelta(hours=5, minutes=30)
    assert _resolve_tz("GMT-3:30").utcoffset(None) == timedelta(hours=-3, minutes=-30)
    assert _resolve_tz("UTC").utcoffset(None) == timedelta(0)


def test_resolve_iana_dst():
    ny = _resolve_tz("America/New_York")
    summer = datetime(2024, 7, 2, 12, 0, tzinfo=_UTC).astimezone(ny)
    winter = datetime(2024, 1, 2, 12, 0, tzinfo=_UTC).astimezone(ny)
    assert summer.utcoffset() == timedelta(hours=-4)   # EDT
    assert winter.utcoffset() == timedelta(hours=-5)   # EST


def test_pine_dayofweek():
    # 2024-07-07 is a Sunday -> Pine dayofweek 1; Saturday -> 7.
    assert _pine_dayofweek(datetime(2024, 7, 7)) == 1
    assert _pine_dayofweek(datetime(2024, 7, 8)) == 2   # Monday
    assert _pine_dayofweek(datetime(2024, 7, 12)) == 6  # Friday
    assert _pine_dayofweek(datetime(2024, 7, 13)) == 7  # Saturday


def test_in_window_overnight_wrap():
    # Tokyo 2000-0500 == minutes 1200..300 (wraps midnight).
    assert _in_window(1200, 1200, 300) is True     # 20:00 start, inclusive
    assert _in_window(0, 1200, 300) is True        # 00:00 inside overnight
    assert _in_window(299, 1200, 300) is True      # 04:59 inside
    assert _in_window(300, 1200, 300) is False     # 05:00 end, exclusive
    assert _in_window(1199, 1200, 300) is False    # 19:59 before start


def test_session_spec_from_pine():
    s = SessionSpec.from_pine("Asia", "2000-0500", "GMT-4")
    assert (s.start_minute, s.end_minute) == (1200, 300)
    assert s.tz_name == "GMT-4"


# ── session windows (each in its own city's clock, DST-aware since 2026-07-31) ─

def _in_ny(ts_ms):
    return SessionEngine().update(0, ts_ms, 1, 0).in_ny


def _in_london(ts_ms):
    return SessionEngine().update(0, ts_ms, 1, 0).in_london


def _in_asia(ts_ms):
    return SessionEngine().update(0, ts_ms, 1, 0).in_asia


def test_ny_session_is_dst_aware():
    """NY is 0800-1700 America/New_York, so its UTC span MOVES with DST: 12:00-21:00 under EDT,
    13:00-22:00 under EST. This is the behaviour change from the old fixed 0900-1800 GMT-4 (always
    13:00-22:00 UTC) — under EDT the session now opens an hour earlier in UTC terms."""
    # Summer (EDT, UTC-4) -> 12:00-21:00 UTC.
    assert _in_ny(ms_utc(2024, 7, 2, 11, 59)) is False
    assert _in_ny(ms_utc(2024, 7, 2, 12, 0)) is True
    assert _in_ny(ms_utc(2024, 7, 2, 20, 59)) is True
    assert _in_ny(ms_utc(2024, 7, 2, 21, 0)) is False
    # Winter (EST, UTC-5) -> 13:00-22:00 UTC. 12:00 UTC is now OUTSIDE.
    assert _in_ny(ms_utc(2024, 1, 2, 12, 0)) is False
    assert _in_ny(ms_utc(2024, 1, 2, 13, 0)) is True
    assert _in_ny(ms_utc(2024, 1, 2, 21, 59)) is True
    assert _in_ny(ms_utc(2024, 1, 2, 22, 0)) is False


def test_london_session_is_dst_aware():
    """London is 0800-1700 Europe/London: 07:00-16:00 UTC under BST, 08:00-17:00 UTC under GMT."""
    # Summer (BST, UTC+1) -> 07:00-16:00 UTC.
    assert _in_london(ms_utc(2024, 7, 2, 6, 59)) is False
    assert _in_london(ms_utc(2024, 7, 2, 7, 0)) is True
    assert _in_london(ms_utc(2024, 7, 2, 15, 59)) is True
    assert _in_london(ms_utc(2024, 7, 2, 16, 0)) is False
    # Winter (GMT, UTC+0) -> 08:00-17:00 UTC. 07:00 UTC is now OUTSIDE.
    assert _in_london(ms_utc(2024, 1, 2, 7, 0)) is False
    assert _in_london(ms_utc(2024, 1, 2, 8, 0)) is True
    assert _in_london(ms_utc(2024, 1, 2, 16, 59)) is True
    assert _in_london(ms_utc(2024, 1, 2, 17, 0)) is False


def test_asia_session_is_utc_stable_year_round():
    """Asia is 0900-1800 Asia/Tokyo, and Japan has no DST — so it is 00:00-09:00 UTC in BOTH
    seasons. That is bit-identical to the old 2000-0500 GMT-4 form, which is why the 2026-07-31
    re-sync did NOT move the Asia window and why engines/session_volume_profile/ (Asia POC only)
    was unaffected by it. Guard this: if Asia ever moves, SVP's parity moves with it."""
    for y, mo in [(2024, 7), (2024, 1)]:            # summer and winter
        assert _in_asia(ms_utc(y, mo, 3, 23, 59)) is False   # previous day, before the open
        assert _in_asia(ms_utc(y, mo, 3, 0, 0)) is True
        assert _in_asia(ms_utc(y, mo, 3, 8, 59)) is True
        assert _in_asia(ms_utc(y, mo, 3, 9, 0)) is False     # end exclusive
    # Same boundaries expressed in the OLD fixed-offset clock, to make the equivalence explicit.
    assert _in_asia(ms("GMT-4", 2024, 7, 2, 20, 0)) is True
    assert _in_asia(ms("GMT-4", 2024, 7, 3, 4, 59)) is True
    assert _in_asia(ms("GMT-4", 2024, 7, 3, 5, 0)) is False


# ── session high/low + open/close edges ──────────────────────────────────────

def test_session_hl_open_expand_close():
    se = SessionEngine()
    # Three NY-session bars then a bar past the NY close (NY is 0800-1700, end exclusive).
    e0 = se.update(0, ms("America/New_York", 2024, 7, 2, 10, 0), high=10.0, low=9.0)
    assert "NY" in e0.opened and e0.in_ny is True
    e1 = se.update(1, ms("America/New_York", 2024, 7, 2, 11, 0), high=12.0, low=9.5)   # new high
    e2 = se.update(2, ms("America/New_York", 2024, 7, 2, 12, 0), high=11.0, low=8.0)   # new low
    assert e1.opened == [] and e2.opened == []
    live = se.current_range("NY")
    assert (live.high, live.low) == (12.0, 8.0)

    e3 = se.update(3, ms("America/New_York", 2024, 7, 2, 17, 0), high=20.0, low=1.0)   # NY closed
    assert e3.in_ny is False
    closed = [r for r in e3.closed if r.name == "NY"]
    assert len(closed) == 1
    r = closed[0]
    assert (r.high, r.low) == (12.0, 8.0)          # finalized, unaffected by the post-close bar
    assert (r.start_index, r.end_index) == (0, 2)


def test_session_hl_persists_between_sessions():
    se = SessionEngine()
    se.update(0, ms("America/New_York", 2024, 7, 2, 10, 0), high=10.0, low=9.0)
    se.update(1, ms("America/New_York", 2024, 7, 2, 17, 0), high=99.0, low=1.0)  # NY closed
    # Between sessions the last NY extremes persist (Pine `var`), not the post-close bar.
    assert se.current_range("NY").high == 10.0


# ── kill zones + DST ─────────────────────────────────────────────────────────

def test_killzones_ny_time():
    se = SessionEngine()
    assert se.update(0, ms("America/New_York", 2024, 7, 2, 10, 0), 1, 0).in_kz1 is True
    assert SessionEngine().update(0, ms("America/New_York", 2024, 7, 2, 11, 0), 1, 0).in_kz1 is False
    assert SessionEngine().update(0, ms("America/New_York", 2024, 7, 2, 11, 45), 1, 0).in_kz2 is True
    assert SessionEngine().update(0, ms("America/New_York", 2024, 7, 2, 12, 14), 1, 0).in_kz2 is True
    assert SessionEngine().update(0, ms("America/New_York", 2024, 7, 2, 12, 15), 1, 0).in_kz2 is False
    assert SessionEngine().update(0, ms("America/New_York", 2024, 7, 2, 13, 30), 1, 0).in_kz3 is True
    assert SessionEngine().update(0, ms("America/New_York", 2024, 7, 2, 13, 31), 1, 0).in_kz3 is False


def test_killzone_is_dst_aware():
    # 14:00 UTC == NY 10:00 in summer (EDT) -> kz1; == NY 09:00 in winter (EST) -> not kz1.
    assert SessionEngine().update(0, ms_utc(2024, 7, 2, 14, 0), 1, 0).in_kz1 is True
    assert SessionEngine().update(0, ms_utc(2024, 1, 2, 14, 0), 1, 0).in_kz1 is False
    assert SessionEngine().update(0, ms_utc(2024, 1, 2, 15, 0), 1, 0).in_kz1 is True  # NY 10:00 EST


def test_in_killzone_property():
    ev = SessionEngine().update(0, ms("America/New_York", 2024, 7, 2, 10, 30), 1, 0)
    assert ev.in_kz1 is True and ev.in_killzone is True


# ── NY opening range ──────────────────────────────────────────────────────────

def test_ny_range_captures_0930_window():
    se = SessionEngine()
    # 2024-07-02 is a Tuesday. NY 09:30 5m bar forms the range; 09:35 freezes it.
    e0 = se.update(0, ms("America/New_York", 2024, 7, 2, 9, 30), high=10.0, low=9.0)
    assert e0.in_ny_range_window is True
    assert (e0.ny_range_high, e0.ny_range_low) == (10.0, 9.0)

    e1 = se.update(1, ms("America/New_York", 2024, 7, 2, 9, 35), high=20.0, low=1.0)
    assert e1.in_ny_range_window is False and e1.in_ny_range_extend is True
    assert (e1.ny_range_high, e1.ny_range_low) == (10.0, 9.0)   # frozen after the window


def test_ny_range_expands_within_window():
    se = SessionEngine()
    se.update(0, ms("America/New_York", 2024, 7, 2, 9, 30), high=10.0, low=9.0)
    ev = se.update(1, ms("America/New_York", 2024, 7, 2, 9, 31), high=11.0, low=8.0)  # sub-5m bar
    assert (ev.ny_range_high, ev.ny_range_low) == (11.0, 8.0)


def test_ny_range_ignored_on_weekend():
    # 2024-07-06 is a Saturday: no NY range reset even inside the 0930 window.
    ev = SessionEngine().update(0, ms("America/New_York", 2024, 7, 6, 9, 30), high=10.0, low=9.0)
    assert ev.is_weekday is False
    assert ev.ny_range_high is None and ev.ny_range_low is None


# ── new day / weekday ──────────────────────────────────────────────────────────

def test_new_day_and_weekday():
    se = SessionEngine()
    e0 = se.update(0, ms("America/New_York", 2024, 7, 2, 23, 0), 1, 0)  # Tuesday
    assert e0.is_new_day is False       # no previous bar to compare
    assert e0.is_weekday is True
    e1 = se.update(1, ms("America/New_York", 2024, 7, 2, 23, 30), 1, 0)  # same NY day
    assert e1.is_new_day is False
    e2 = se.update(2, ms("America/New_York", 2024, 7, 3, 0, 30), 1, 0)   # next NY day
    assert e2.is_new_day is True


def test_weekend_flag():
    ev = SessionEngine().update(0, ms("America/New_York", 2024, 7, 7, 12, 0), 1, 0)  # Sunday
    assert ev.is_weekday is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
