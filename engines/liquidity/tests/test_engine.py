"""
Hand-traced tests for the liquidity engine.

These pin the mechanics against explicit bars: previous-period level creation (non-repainting — the
level equals the COMPLETED period, never the developing one), the sweep-vs-break mitigation rules,
PWC, the H4 SSH/BSL sweep, session-H/L levels consumed from the composed sessions engine, the
new-day tidy, and eviction on a period roll. Full Pine-parity validation lives in
tools/compare_liquidity.py against a real TradingView export; these lock the logic so a regression is
caught without an export.
"""

from datetime import datetime

import pytest

from liquidity import LiquidityEngine
from liquidity.engine import _PeriodTracker, _key_day, _key_week, _key_h4
from sessions.engine import _resolve_tz


def ms(tz_name, y, mo, d, h, mi=0):
    """Epoch milliseconds for a wall-clock time in the given timezone (DST-aware for IANA names)."""
    return int(datetime(y, mo, d, h, mi, tzinfo=_resolve_tz(tz_name)).timestamp() * 1000)


NY = "America/New_York"


def _only(**flags):
    """A LiquidityEngine with every feature disabled except the ones named True, hide-on-new-day off
    by default (tests that want it pass hide=True). Isolates one feature at a time."""
    base = dict(enable_daily=False, enable_weekly=False,
                enable_pwc=False, enable_h4=False, enable_sessions=False,
                hide_mitigated_on_new_day=False, htf_timezone=NY, htf_rollover_hours=0)
    base.update(flags)
    return LiquidityEngine(**base)


# ── _PeriodTracker ───────────────────────────────────────────────────────────

def test_period_tracker_rolls_previous_only():
    tr = _PeriodTracker(_key_day)
    # first bar of day 1: sets the key, never a roll, no previous yet
    assert tr.update(datetime(2024, 7, 1, 10, tzinfo=_resolve_tz(NY)), 100, 90, 95) is False
    assert tr.prev_high is None
    # second bar of day 1: expands, still no roll
    assert tr.update(datetime(2024, 7, 1, 12, tzinfo=_resolve_tz(NY)), 110, 85, 105) is False
    assert (tr.cur_high, tr.cur_low, tr.cur_close) == (110, 85, 105)
    # first bar of day 2: rolls, previous = the finished day 1 (high 110, low 85, close 105)
    assert tr.update(datetime(2024, 7, 2, 10, tzinfo=_resolve_tz(NY)), 999, 998, 999) is True
    assert (tr.prev_high, tr.prev_low, tr.prev_close) == (110, 85, 105)


def test_key_functions():
    assert _key_day(datetime(2024, 7, 2, 23)) == (2024, 7, 2)
    assert _key_week(datetime(2024, 7, 3)) == (2024, 27)     # Wed of ISO week 27
    assert _key_week(datetime(2024, 7, 8)) == (2024, 28)     # following Monday → week 28
    assert _key_h4(datetime(2024, 7, 2, 9)) == (2024, 7, 2, 2)   # 08:00-12:00 bucket
    assert _key_h4(datetime(2024, 7, 2, 13)) == (2024, 7, 2, 3)  # 12:00-16:00 bucket


# ── daily levels: non-repainting creation + sweep ────────────────────────────

def test_daily_level_is_previous_completed_day():
    liq = _only(enable_daily=True)
    liq.update(0, ms(NY, 2024, 7, 1, 10), 100, 90, 95)
    liq.update(1, ms(NY, 2024, 7, 1, 12), 110, 90, 105)      # day 1: high 110, low 90
    ev = liq.update(2, ms(NY, 2024, 7, 2, 10), 105, 100, 102)  # first bar of day 2 → roll
    created = {(l.name, l.price) for l in ev.created}
    assert created == {("PDH", 110), ("PDL", 90)}           # the COMPLETED day, not day-2's 105
    assert all(not l.mitigated for l in ev.created)


def test_daily_high_swept_on_wick_through():
    liq = _only(enable_daily=True)
    liq.update(0, ms(NY, 2024, 7, 1, 10), 100, 90, 95)
    liq.update(1, ms(NY, 2024, 7, 1, 12), 110, 90, 105)
    liq.update(2, ms(NY, 2024, 7, 2, 10), 105, 100, 102)    # PDH=110 created
    # wick does not reach the level → not swept
    ev = liq.update(3, ms(NY, 2024, 7, 2, 12), 109, 104, 108)
    assert ev.mitigated == []
    # wick through the level → swept, even though the bar also CLOSES above it (the close-back
    # guard was dropped 2026-07-06 to match mpc_jarvis.pine — a wick alone now sweeps)
    ev = liq.update(4, ms(NY, 2024, 7, 2, 13), 112, 108, 111)
    assert [l.name for l in ev.mitigated] == ["PDH"]
    assert ev.mitigated[0].mitigated_index == 4


def test_daily_low_swept():
    liq = _only(enable_daily=True)
    liq.update(0, ms(NY, 2024, 7, 1, 10), 100, 90, 95)
    liq.update(1, ms(NY, 2024, 7, 1, 12), 110, 90, 105)
    liq.update(2, ms(NY, 2024, 7, 2, 10), 105, 100, 102)    # PDL=90 created
    ev = liq.update(3, ms(NY, 2024, 7, 2, 12), 101, 88, 95)  # low 88<90 → swept (wick through)
    assert [l.name for l in ev.mitigated] == ["PDL"]


# ── weekly: the break rule (close-through, no wick condition) ─────────────────

def test_weekly_high_broken_by_close_not_wick():
    liq = _only(enable_weekly=True)
    liq.update(0, ms(NY, 2024, 7, 3, 10), 200, 180, 190)     # week 27
    liq.update(1, ms(NY, 2024, 7, 4, 10), 210, 185, 205)     # week 27: high 210, low 180
    ev = liq.update(2, ms(NY, 2024, 7, 8, 10), 195, 190, 193)  # Mon week 28 → roll
    assert {(l.name, l.price) for l in ev.created} == {("PWH", 210), ("PWL", 180)}
    # wick above but close below → NOT broken (break rule needs a CLOSE above)
    ev = liq.update(3, ms(NY, 2024, 7, 8, 12), 215, 191, 209)
    assert ev.mitigated == []
    # close above → broken
    ev = liq.update(4, ms(NY, 2024, 7, 8, 13), 212, 200, 211)
    assert [l.name for l in ev.mitigated] == ["PWH"]


# ── PWC: previous week's final close, never mitigated ────────────────────────

def test_pwc_is_previous_week_close_and_never_mitigates():
    liq = _only(enable_pwc=True)          # weekly levels off, only PWC
    liq.update(0, ms(NY, 2024, 7, 3, 10), 200, 180, 190)
    liq.update(1, ms(NY, 2024, 7, 4, 10), 210, 185, 205)    # week 27 final close = 205
    ev = liq.update(2, ms(NY, 2024, 7, 8, 10), 195, 190, 193)
    pwc = [l for l in ev.created if l.name == "PWC"]
    assert len(pwc) == 1 and pwc[0].price == 205 and pwc[0].side == "close"
    # price crossing PWC never marks it mitigated
    ev = liq.update(3, ms(NY, 2024, 7, 8, 12), 250, 100, 150)
    assert ev.mitigated == []
    assert not any(l.name == "PWC" and l.mitigated for l in liq.active_levels())


# ── H4 sweep: prev-H4 high/low + SSH/BSL labels ──────────────────────────────

def test_h4_sweep_high_emits_bsl():
    liq = _only(enable_h4=True)
    liq.update(0, ms(NY, 2024, 7, 1, 9), 50, 40, 45)        # 08:00-12:00 bucket
    liq.update(1, ms(NY, 2024, 7, 1, 10), 55, 42, 52)       # bucket high 55, low 40
    ev = liq.update(2, ms(NY, 2024, 7, 1, 13), 53, 48, 50)  # 12:00-16:00 bucket → roll
    assert {(l.name, l.price) for l in ev.created} == {("H4 H", 55), ("H4 L", 40)}
    ev = liq.update(3, ms(NY, 2024, 7, 1, 14), 57, 49, 54)  # high 57>55 → swept (wick through)
    swept = [l for l in ev.mitigated if l.name == "H4 H"]
    assert len(swept) == 1 and swept[0].sweep_label == "BSL"


def test_h4_sweep_low_emits_ssl():
    liq = _only(enable_h4=True)
    liq.update(0, ms(NY, 2024, 7, 1, 9), 50, 40, 45)
    liq.update(1, ms(NY, 2024, 7, 1, 10), 55, 42, 52)
    liq.update(2, ms(NY, 2024, 7, 1, 13), 53, 48, 50)       # H4 L=40 created
    ev = liq.update(3, ms(NY, 2024, 7, 1, 14), 52, 38, 45)  # low 38<40 → swept (wick through)
    swept = [l for l in ev.mitigated if l.name == "H4 L"]
    assert len(swept) == 1 and swept[0].sweep_label == "SSL"


# ── session H/L: consumed from the composed sessions engine ───────────────────

def test_session_levels_created_on_session_close():
    liq = _only(enable_sessions=True)
    # Asia = 0900-1800 Asia/Tokyo == 0000-0900 UTC year-round. Feed two in-Asia bars then one out
    # (09:00 UTC in July is past the Asia close and inside London's BST window).
    liq.update(0, ms("UTC", 2024, 7, 1, 0), 10, 5, 8)       # Asia opens
    liq.update(1, ms("UTC", 2024, 7, 1, 4), 12, 6, 11)      # Asia high 12, low 5
    ev = liq.update(2, ms("UTC", 2024, 7, 1, 9), 11, 9, 10)  # out of Asia → Asia closes
    created = {(l.name, l.price) for l in ev.created}
    assert created == {("Asia H", 12), ("Asia L", 5)}
    assert all(l.kind == "session" and l.session_name == "Asia" for l in ev.created)


def test_session_high_sweep():
    liq = _only(enable_sessions=True)
    liq.update(0, ms("UTC", 2024, 7, 1, 0), 10, 5, 8)
    liq.update(1, ms("UTC", 2024, 7, 1, 4), 12, 6, 11)
    liq.update(2, ms("UTC", 2024, 7, 1, 9), 11, 9, 10)      # Asia H=12 created
    ev = liq.update(3, ms("UTC", 2024, 7, 1, 10), 13, 10, 11)  # high 13>12 → swept (wick through)
    assert [l.name for l in ev.mitigated] == ["Asia H"]


# ── eviction on a period roll ────────────────────────────────────────────────

def test_period_roll_evicts_old_level():
    liq = _only(enable_daily=True)
    liq.update(0, ms(NY, 2024, 7, 1, 10), 100, 90, 95)
    liq.update(1, ms(NY, 2024, 7, 1, 12), 110, 90, 105)
    liq.update(2, ms(NY, 2024, 7, 2, 10), 105, 100, 102)    # PDH=110 (from day 1)
    ev = liq.update(3, ms(NY, 2024, 7, 3, 10), 104, 101, 103)  # roll: PDH now from day 2
    evicted = {(l.name, l.price) for l in ev.evicted}
    created = {(l.name, l.price) for l in ev.created}
    assert ("PDH", 110) in evicted and ("PDL", 90) in evicted   # day-1 levels gone
    assert ("PDH", 105) in created and ("PDL", 100) in created  # day-2 levels in
    active_prices = {(l.name, l.price) for l in liq.active_levels()}
    assert active_prices == {("PDH", 105), ("PDL", 100)}


# ── new-day tidy: drop mitigated day/week/session levels ──────────────────────

def test_hide_mitigated_on_new_day():
    # weekly-only so the NY new-day fires WITHOUT a weekly roll, isolating the tidy from a roll.
    liq = _only(enable_weekly=True, hide_mitigated_on_new_day=True)
    liq.update(0, ms(NY, 2024, 7, 3, 10), 200, 180, 190)
    liq.update(1, ms(NY, 2024, 7, 4, 10), 210, 185, 205)
    liq.update(2, ms(NY, 2024, 7, 8, 10), 195, 190, 193)    # PWH=210 created (Mon)
    liq.update(3, ms(NY, 2024, 7, 8, 13), 212, 200, 211)    # PWH broken (mitigated)
    assert any(l.name == "PWH" and l.mitigated for l in liq.active_levels())
    ev = liq.update(4, ms(NY, 2024, 7, 9, 10), 205, 200, 203)  # new NY day, still week 28
    assert any(l.name == "PWH" for l in ev.evicted)
    assert not any(l.name == "PWH" for l in liq.active_levels())


def test_no_level_before_first_period_completes():
    liq = _only(enable_daily=True)
    ev0 = liq.update(0, ms(NY, 2024, 7, 1, 10), 100, 90, 95)
    ev1 = liq.update(1, ms(NY, 2024, 7, 1, 12), 110, 90, 105)
    assert ev0.created == [] and ev1.created == []          # no completed day yet
    assert liq.active_levels() == []
