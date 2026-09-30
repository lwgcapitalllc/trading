"""Hand-traced tests for the directional-trend engine.

These lock the mechanics without an export: the bias rule's precedence, the non-repainting publish
timing, the partial-first-period discard, None-for-cannot-know, and that every STR row is the
canonical structure engine fed that timeframe's closed candles. Pine parity lives in
tools/compare_directional_trend.py against a real TradingView export.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

_ENGINES = Path(__file__).resolve().parents[2]
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from directional_trend import BEARISH, BULLISH, NEUTRAL, DirectionalTrend, bias_state  # noqa: E402
from directional_trend.types import (  # noqa: E402
    DESC_CLOSE_ABOVE,
    DESC_CLOSE_BELOW,
    DESC_INSIDE,
    DESC_SWEPT_HIGH,
    DESC_SWEPT_LOW,
    EV_CONTINUATION,
    EV_EXPANSION,
    EV_SHIFT,
)
from market_structure import Bar, StructureEngine  # noqa: E402
from sessions.engine import _resolve_tz  # noqa: E402

NY = _resolve_tz("America/New_York")
MIN = 60_000


def ny_ms(y, mo, d, h, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=NY).timestamp() * 1000)


# ── the bias rule ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "h,l,c,state,code,text",
    [
        (110, 95, 105, BULLISH, DESC_CLOSE_ABOVE, "Close > Prev D High"),
        (105, 85, 89, BEARISH, DESC_CLOSE_BELOW, "Close < Prev D Low"),
        (104, 95, 99, BEARISH, DESC_SWEPT_HIGH, "Swept D High"),
        (99, 85, 91, BULLISH, DESC_SWEPT_LOW, "Swept D Low"),
        (99, 91, 95, NEUTRAL, DESC_INSIDE, "Inside D Range"),
    ],
)
def test_bias_state_matches_every_branch_of_the_pine(h, l, c, state, code, text):
    row = bias_state(h, l, c, 100, 90, "D")
    assert (row.state, row.desc_code, row.desc) == (state, code, text)


def test_a_close_above_beats_a_low_sweep_on_an_outside_bar():
    """Pine checks closures before sweeps — an outside bar that closes above is a closure."""
    assert bias_state(110, 80, 105, 100, 90, "W").desc_code == DESC_CLOSE_ABOVE


def test_a_bar_that_sweeps_both_sides_and_closes_inside_is_a_high_sweep():
    """Pine's else-if order: the bearish sweep is tested before the bullish one."""
    assert bias_state(110, 80, 95, 100, 90, "D").desc_code == DESC_SWEPT_HIGH


def test_a_close_exactly_on_the_high_is_not_a_closure():
    assert bias_state(100, 95, 100, 100, 90, "D").state == NEUTRAL


# ── daily bias timing ───────────────────────────────────────────────────────────────────────────


def _feed_day(eng, start_ms, hours, high, low, close, step_min=15):
    """Feed a flat run of bars spanning `hours`, the last one closing at `close`."""
    n = hours * 60 // step_min
    snap = None
    for i in range(n):
        c = close if i == n - 1 else (high + low) / 2
        snap = eng.update(start_ms + i * step_min * MIN, c, high, low, c)
    return snap


def test_daily_bias_needs_two_full_days_and_ignores_the_partial_first_one():
    eng = DirectionalTrend(15)
    # Partial day: starts 06:00 NY (trading day opened 18:00 the evening before).
    _feed_day(eng, ny_ms(2026, 3, 3, 6), 11, high=200, low=10, close=100)
    # Full day 1: 18:00 → 17:00, range 90-100, close 95.
    snap = _feed_day(eng, ny_ms(2026, 3, 3, 18), 23, high=100, low=90, close=95)
    assert snap.daily is None, "a partial first day must never become bias context"
    # Full day 2: breaks above day 1's high and closes there.
    snap = _feed_day(eng, ny_ms(2026, 3, 4, 18), 23, high=110, low=94, close=108)
    assert snap.daily is None, "day 2 is still developing — nothing may read it yet"
    # First bar of day 3 publishes day 2 vs day 1.
    snap = eng.update(ny_ms(2026, 3, 5, 18), 108, 108, 108, 108)
    assert snap.daily.state == BULLISH and snap.daily.desc == "Close > Prev D High"


def test_a_developing_day_never_moves_the_daily_row():
    eng = DirectionalTrend(15)
    _feed_day(eng, ny_ms(2026, 3, 2, 18), 23, 100, 90, 95)  # first day seen — always discarded
    _feed_day(eng, ny_ms(2026, 3, 3, 18), 23, 100, 90, 95)
    _feed_day(eng, ny_ms(2026, 3, 4, 18), 23, 99, 91, 95)
    row = eng.update(ny_ms(2026, 3, 5, 18), 95, 95, 95, 95).daily
    assert row.state == NEUTRAL
    # Rip through the prior high inside the developing day: the row must not budge.
    snap = eng.update(ny_ms(2026, 3, 5, 18, 15), 95, 150, 95, 150)
    assert snap.daily == row


# ── weekly bias ─────────────────────────────────────────────────────────────────────────────────


def test_weekly_bias_rolls_on_sunday_evening_new_york():
    eng = DirectionalTrend(15)

    # Three weeks, one bar each weekday session, 4-hourly bars would do — use 15m sparse points.
    def week(sun_d, high, low, close):
        # Sunday 18:00 open through Friday 16:45; feed a handful of bars.
        eng.update(ny_ms(2026, 3, sun_d, 18), low, high, low, (high + low) / 2)
        return eng.update(ny_ms(2026, 3, sun_d + 5, 16, 45), close, close, close, close)

    week(1, 200, 10, 100)  # first week seen — discarded as partial
    week(8, 100, 90, 95)
    snap = week(15, 99, 80, 95)  # swept the low, closed back inside
    assert snap.weekly is None
    snap = eng.update(ny_ms(2026, 3, 22, 18), 95, 95, 95, 95)
    assert snap.weekly.state == BULLISH and snap.weekly.desc == "Swept W Low"


# ── structure rows ──────────────────────────────────────────────────────────────────────────────


def _zigzag(n, base=2000.0, seed=7):
    """Deterministic trending/reversing 1-minute path with enough swings to break structure."""
    import random

    rnd = random.Random(seed)
    px, out, drift = base, [], 0.0
    for i in range(n):
        if i % 600 == 0:
            drift = rnd.choice((-0.35, 0.35))
        o = px
        px = px + drift + rnd.uniform(-1.2, 1.2)
        h = max(o, px) + rnd.uniform(0, 0.6)
        l = min(o, px) - rnd.uniform(0, 0.6)
        out.append((o, h, l, px))
    return out


def _aggregate(bars_1m, start_ms, minutes):
    """Reference 15m candles, skipping the first (it may be partial) exactly as the engine does."""
    buckets, order = {}, []
    for i, (o, h, l, c) in enumerate(bars_1m):
        k = (start_ms + i * MIN) // (minutes * MIN)
        if k not in buckets:
            buckets[k] = [o, h, l, c]
            order.append(k)
        else:
            b = buckets[k]
            b[1], b[2], b[3] = max(b[1], h), min(b[2], l), c
    return [buckets[k] for k in order[1:]]


def test_the_15m_row_is_the_canonical_engine_on_closed_15m_candles():
    start = ny_ms(2026, 3, 3, 9, 7)  # deliberately mid-bucket: first 15m candle is partial
    bars = _zigzag(6000)
    eng = DirectionalTrend(1)
    for i, b in enumerate(bars):
        snap = eng.update(start + i * MIN, *b)
    ref = StructureEngine()
    closed = _aggregate(bars, start, 15)[:-1]  # the last bucket is still developing
    for i, (o, h, l, c) in enumerate(closed):
        ref.update(Bar(index=i, open=o, high=h, low=l, close=c))
    assert ref.dir != 0, "fixture never broke structure — the comparison would be vacuous"
    assert snap.m15.direction == ref.dir


def test_the_row_for_the_fed_timeframe_updates_on_the_bar_itself():
    start = ny_ms(2026, 3, 3, 9, 0)
    bars = _zigzag(3000)
    eng, ref = DirectionalTrend(1), StructureEngine()
    for i, b in enumerate(bars):
        snap = eng.update(start + i * MIN, *b)
        ref.update(Bar(index=i, open=b[0], high=b[1], low=b[2], close=b[3]))
        assert snap.m1.direction == ref.dir


def test_event_sequence_is_shift_then_expansion_then_continuation():
    start = ny_ms(2026, 3, 3, 9, 0)
    eng, seen = DirectionalTrend(1), []
    for i, b in enumerate(_zigzag(20000)):
        ev = eng.update(start + i * MIN, *b).m1.event
        if not seen or seen[-1] != ev:
            seen.append(ev)
    # After any shift, the next distinct event is expansion (or another shift), never continuation.
    for a, b in zip(seen, seen[1:]):
        if a == EV_SHIFT:
            assert b in (EV_EXPANSION,), f"shift jumped straight to {b}"
        if b == EV_CONTINUATION:
            assert a in (EV_EXPANSION,), f"continuation arrived after {a}"
    assert EV_SHIFT in seen and EV_CONTINUATION in seen, "fixture too tame to exercise the counter"


def test_a_timeframe_finer_than_the_feed_is_cannot_know_not_neutral():
    eng = DirectionalTrend(5)
    snap = eng.update(ny_ms(2026, 3, 3, 9, 0), 1, 1, 1, 1)
    assert snap.m1 is None


def test_nothing_is_known_before_any_candle_closes():
    snap = DirectionalTrend(1).update(ny_ms(2026, 3, 3, 9, 0), 1, 1, 1, 1)
    assert (snap.weekly, snap.daily, snap.h4, snap.m15) == (None, None, None, None)
    assert snap.m1 is not None and snap.m1.direction == 0


def test_out_of_order_and_misaligned_bars_are_refused():
    eng = DirectionalTrend(5)
    t = ny_ms(2026, 3, 3, 9, 0)
    eng.update(t, 1, 1, 1, 1)
    with pytest.raises(ValueError):
        eng.update(t, 1, 1, 1, 1)
    with pytest.raises(ValueError):
        eng.update(t + 7 * MIN, 1, 1, 1, 1)


def test_unsupported_feed_is_refused():
    with pytest.raises(ValueError):
        DirectionalTrend(60)
