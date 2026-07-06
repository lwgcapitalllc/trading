"""
Hand-traced tests for the VWAP engine.

These pin the mechanics against explicit bars: the volume-weighted running mean of hlc3, the
trading-day re-anchor (accumulator reset), the na/zero-volume guard, and the derived close-vs-line
cross. Full Pine-parity validation of the `value` lives in tools/compare_vwap.py against a real
TradingView export; these lock the logic so a regression is caught without an export.
"""

from datetime import datetime

import pytest

from vwap import VwapEngine
from vwap.engine import _key_day
from sessions.engine import _resolve_tz


def ms(tz_name, y, mo, d, h, mi=0):
    """Epoch milliseconds for a wall-clock time in the given timezone (DST-aware for IANA names)."""
    return int(datetime(y, mo, d, h, mi, tzinfo=_resolve_tz(tz_name)).timestamp() * 1000)


NY = "America/New_York"


def _eng(rollover=0):
    """A VwapEngine on NY time with the day boundary at midnight by default (rollover=0) so the
    hand-traced bars stay on clean calendar days; pass rollover=18 to exercise the evening open."""
    return VwapEngine(htf_timezone=NY, htf_rollover_hours=rollover)


# ── the volume-weighted running mean ─────────────────────────────────────────

def test_single_bar_vwap_is_hlc3():
    vw = _eng()
    ev = vw.update(0, ms(NY, 2024, 7, 1, 10), high=110, low=90, close=100, volume=5)
    assert ev.value == pytest.approx(100.0)     # hlc3 = (110+90+100)/3 = 100
    assert ev.anchored is False                 # first fed bar never pulses anchored
    assert ev.side == 0                          # close 100 sits exactly on the line


def test_two_bars_volume_weighted():
    vw = _eng()
    vw.update(0, ms(NY, 2024, 7, 1, 10), 110, 90, 100, volume=1)     # hlc3 100, vol 1
    ev = vw.update(1, ms(NY, 2024, 7, 1, 11), 210, 190, 200, volume=3)  # hlc3 200, vol 3
    # (100*1 + 200*3) / (1+3) = 700/4 = 175 — pulled toward the heavier-volume 200
    assert ev.value == pytest.approx(175.0)


def test_volume_actually_weights():
    """Same two prices, swap the volumes → the average moves the other way."""
    vw = _eng()
    vw.update(0, ms(NY, 2024, 7, 1, 10), 110, 90, 100, volume=3)     # hlc3 100, vol 3
    ev = vw.update(1, ms(NY, 2024, 7, 1, 11), 210, 190, 200, volume=1)  # hlc3 200, vol 1
    assert ev.value == pytest.approx(125.0)     # (300+200)/4


# ── trading-day re-anchor ────────────────────────────────────────────────────

def test_new_day_resets_accumulator():
    vw = _eng()
    vw.update(0, ms(NY, 2024, 7, 1, 10), 110, 90, 100, volume=10)    # day 1
    ev = vw.update(1, ms(NY, 2024, 7, 2, 10), 210, 190, 200, volume=1)  # day 2 → reset
    assert ev.anchored is True
    assert ev.value == pytest.approx(200.0)     # day-2 bar only; day-1 volume is gone


def test_same_day_does_not_reanchor():
    vw = _eng()
    vw.update(0, ms(NY, 2024, 7, 1, 10), 110, 90, 100, volume=1)
    ev = vw.update(1, ms(NY, 2024, 7, 1, 23, 59), 210, 190, 200, volume=1)
    assert ev.anchored is False                 # still 1 Jul → same session


def test_evening_open_rolls_at_18():
    """rollover=18: the 18:00-NY bar opens the NEXT trading day, so it re-anchors; 17:00 does not."""
    vw = _eng(rollover=18)
    vw.update(0, ms(NY, 2024, 7, 1, 17, 0), 110, 90, 100, volume=1)     # still 1-Jul session
    ev_open = vw.update(1, ms(NY, 2024, 7, 1, 18, 0), 210, 190, 200, volume=1)  # opens 2-Jul session
    assert ev_open.anchored is True
    assert ev_open.value == pytest.approx(200.0)


# ── zero / missing volume guard ──────────────────────────────────────────────

def test_zero_volume_bar_gives_na_then_recovers():
    vw = _eng()
    ev0 = vw.update(0, ms(NY, 2024, 7, 1, 10), 110, 90, 100, volume=0)
    assert ev0.value is None                     # 0/0 → na, like Pine ta.vwap
    ev1 = vw.update(1, ms(NY, 2024, 7, 1, 11), 210, 190, 200, volume=2)
    assert ev1.value == pytest.approx(200.0)     # first real volume anchors the value


def test_none_volume_treated_as_zero():
    vw = _eng()
    ev = vw.update(0, ms(NY, 2024, 7, 1, 10), 110, 90, 100, volume=None)
    assert ev.value is None


# ── derived close-vs-line cross ──────────────────────────────────────────────

def test_side_above_and_below():
    vw = _eng()
    ev = vw.update(0, ms(NY, 2024, 7, 1, 10), high=101, low=99, close=98, volume=1)
    assert ev.value == pytest.approx((101 + 99 + 98) / 3)   # 99.333
    assert ev.side == -1                          # close 98 below the line


def test_cross_up_then_down():
    vw = _eng()
    # bar0: close below the line → side -1, no cross yet
    ev0 = vw.update(0, ms(NY, 2024, 7, 1, 10), 101, 99, 98, volume=1)
    assert ev0.side == -1 and ev0.crossed_up is False
    # bar1: a high-close bar drags close above the running VWAP → cross up
    ev1 = vw.update(1, ms(NY, 2024, 7, 1, 11), 110, 108, 109, volume=1)
    assert ev1.side == 1 and ev1.crossed_up is True and ev1.crossed_down is False
    # bar2: close drops back below → cross down
    ev2 = vw.update(2, ms(NY, 2024, 7, 1, 12), 100, 98, 99, volume=1)
    assert ev2.side == -1 and ev2.crossed_down is True and ev2.crossed_up is False


def test_no_double_cross_when_staying_above():
    vw = _eng()
    vw.update(0, ms(NY, 2024, 7, 1, 10), 101, 99, 98, volume=1)      # below
    vw.update(1, ms(NY, 2024, 7, 1, 11), 110, 108, 109, volume=1)    # cross up
    ev = vw.update(2, ms(NY, 2024, 7, 1, 12), 120, 118, 119, volume=1)  # stays above
    assert ev.side == 1 and ev.crossed_up is False and ev.crossed_down is False


# ── misc ─────────────────────────────────────────────────────────────────────

def test_value_read_matches_event():
    vw = _eng()
    ev = vw.update(0, ms(NY, 2024, 7, 1, 10), 110, 90, 100, volume=4)
    assert vw.value() == pytest.approx(ev.value)


def test_key_day():
    assert _key_day(datetime(2024, 7, 2, 23)) == (2024, 7, 2)
