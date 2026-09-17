"""Tests for the shared N-day momentum read — weighted toward the SILENT failures.

Two things can go wrong here without raising: reading the still-forming day's close (look-ahead,
which flatters any filter built on it), and putting the day boundary in the wrong place (a filter
that runs, and reads a different month than the Pine does).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from daily_momentum import DailyMomentum, trading_day_key  # noqa: E402

HOUR = 3_600_000


def _utc(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp() * 1000)


@pytest.mark.parametrize("utc,day", [
    # Summer (New York is UTC-4): the roll is 21:00 UTC.
    ("2025-07-15 20:55", 20250715), ("2025-07-15 21:00", 20250716),
    # Winter (UTC-5): the roll is 22:00 UTC. A fixed UTC hour would get one of these wrong.
    ("2025-01-15 21:55", 20250115), ("2025-01-15 22:00", 20250116),
    # Sunday's reopen belongs to Monday.
    ("2025-07-13 22:00", 20250714),
])
def test_the_day_rolls_at_1700_new_york_in_both_seasons(utc, day):
    """Watched RED by reading the shifted date in UTC instead of New York: both seasons break."""
    assert trading_day_key(_utc(utc)) == day


def _feed_days(m, closes, start="2025-03-03 14:00"):
    """One bar per trading day at 14:00 UTC, then a bar on the next day to complete the last."""
    t = _utc(start)
    for c in closes:
        m.update(t, c)
        t += 24 * HOUR


def test_nothing_is_known_until_n_plus_one_days_have_completed():
    m = DailyMomentum(3)
    _feed_days(m, [100, 101, 102])
    assert m.direction is None, "the third day is still forming"
    _feed_days(m, [103], start="2025-03-06 14:00")
    assert m.direction is None, "three completed days cannot measure a 3-day move"
    _feed_days(m, [104], start="2025-03-07 14:00")
    assert m.direction == 1


def test_the_day_still_forming_is_never_read():
    """🔴 The look-ahead guard. The forming day crashes far below everything; if its close were
    read, the answer would flip to -1. Watched RED by overwriting the last completed close with
    every new bar's close."""
    m = DailyMomentum(2)
    _feed_days(m, [100, 101, 102])           # 100 and 101 completed, 102 forming
    m.update(_utc("2025-03-06 14:00"), 110)  # completes 102; 110 forming
    assert m.direction == 1
    m.update(_utc("2025-03-06 15:00"), 1.0)  # same day — still forming
    assert m.direction == 1


def test_the_last_bar_of_a_day_is_its_close():
    m = DailyMomentum(1)
    m.update(_utc("2025-03-03 14:00"), 100)
    m.update(_utc("2025-03-04 14:00"), 50)
    m.update(_utc("2025-03-04 20:55"), 120)  # last bar before the 21:00 UTC roll (EST: 22:00)
    m.update(_utc("2025-03-05 14:00"), 1)
    assert m.direction == 1, "the day closed at 120, not at its first bar's 50"


def test_a_down_move_and_a_flat_move_are_told_apart():
    down, flat = DailyMomentum(1), DailyMomentum(1)
    _feed_days(down, [100, 90, 1])
    _feed_days(flat, [100, 100, 1])
    assert down.direction == -1
    assert flat.direction == 0, "no move is 0, which is not the same as unknown"


def test_a_lookback_below_one_is_refused():
    with pytest.raises(ValueError):
        DailyMomentum(0)
