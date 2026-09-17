"""The extreme-leg bot's setup messages (`setups.py`) — one thread per armed episode.

Driven with hand-built `LegState`s, the exact object the strategy hands the watch. **Watched RED
before `setups.py` existed** (import error); each rule below also names its mutation.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PY = Path(__file__).resolve().parents[2]
for _p in (_PY, _PY.parents[1]):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from extreme_leg.config import ExtremeLegConfig  # noqa: E402
from extreme_leg.execution import BLK_TARGET_TOO_NEAR  # noqa: E402
from extreme_leg.setups import LegSetupWatch  # noqa: E402
from extreme_leg.strategy import LegState  # noqa: E402

from backtest.setups import DEAD, FILLED, WATCHING  # noqa: E402

T0 = 1_700_000_000_000
BAR = 300_000


def _st(i, *, armed=True, age=None, swept=0, raw=False, go=False, blk=0, entered=0, dir15=-1):
    return LegState(
        index=i, ts_ms=T0 + i * BAR, close=100.0, high=101.0, low=99.0, atr=1.0,
        dir15=dir15, low_armed=armed, low_age=age, swept_now=swept,
        raw_long=raw, go_long=go, blk_long=blk, entered=entered,
        stop_long=98.0, tp_long=103.0, tgt_long=106.0,
    )


def _watch():
    return LegSetupWatch(ExtremeLegConfig(symbol="XAUUSD.p"))


def test_a_sweep_with_no_shift_sends_NOTHING():
    """Measured: announcing on the sweep sent 91 roots a month and 2% traded.

    MUTATION: set `ep.announced = True` when the episode opens and this reddens.
    """
    w = _watch()
    w.observe(_st(0, age=0, swept=1), False)
    assert w.drain_setups() == []
    w.observe(_st(1, age=1), False)
    w.observe(_st(2, armed=False, age=2), False)
    assert w.drain_setups() == []


def test_a_shift_that_is_taken_is_one_thread_that_ends_FILLED():
    w = _watch()
    w.observe(_st(0, age=0, swept=1 | 4), False)
    w.observe(_st(3, age=3, raw=True, go=True, entered=1), False)
    snaps = w.drain_setups()
    assert [s.state for s in snaps] == [FILLED]
    s = snaps[0]
    assert s.key == f"ExtremeLegStrategy:L:t{T0}"
    assert s.met == s.of == 3
    assert "H4" in s.confluences[0].detail and "session" in s.confluences[0].detail
    assert s.stop == 98.0 and s.targets == (103.0,)


def test_the_same_sweep_never_opens_a_SECOND_thread_after_a_fill():
    """After a fill the side is usually still armed. MUTATION: let an episode open on any armed
    bar (drop the `age != 0` return) and a second one opens under the key just forgotten."""
    w = _watch()
    w.observe(_st(0, age=0, swept=1), False)
    w.observe(_st(1, age=1, raw=True, go=True, entered=1), False)
    w.drain_setups()
    w.observe(_st(2, age=2, raw=True, go=True), True)  # still armed, a trade is open
    assert w.drain_setups() == []


def test_a_refused_shift_is_BLOCKED_then_closed_with_the_last_refusal():
    w = _watch()
    w.observe(_st(0, age=0, swept=1), False)
    w.observe(_st(1, age=1, raw=True, blk=BLK_TARGET_TOO_NEAR), False)
    snaps = w.drain_setups()
    assert [s.state for s in snaps] == [WATCHING]
    assert snaps[0].blocked_by == ("the swing is nearer than the minimum",)
    w.observe(_st(2, age=2), False)
    assert w.drain_setups()[0].blocked_by == ()  # a refusal belongs to its own bar
    w.observe(_st(3, armed=False, age=3), False)
    snaps = w.drain_setups()
    assert [s.state for s in snaps] == [DEAD]
    assert "the swing is nearer than the minimum" in snaps[0].reason
    assert w.drain_setups() == []  # MUTATION: drop `_done.clear()` and it repeats


def test_a_ready_shift_the_slot_refused_names_WHY():
    w = _watch()
    w.observe(_st(0, age=0, swept=1), False)
    w.observe(_st(1, age=1, raw=True, go=True), True)
    assert w.drain_setups()[0].blocked_by == ("a trade is already open",)
    w.observe(_st(2, age=2, raw=True, go=True), False)
    assert w.drain_setups()[0].blocked_by == ("the account's risk budget had no room",)


def test_a_fresh_sweep_while_armed_keeps_the_SAME_thread():
    w = _watch()
    w.observe(_st(0, age=0, swept=1), False)
    w.observe(_st(5, age=0, swept=16), False)  # daily low taken too
    w.observe(_st(6, age=1, raw=True, go=True, entered=1), False)
    (s,) = w.drain_setups()
    assert s.key == f"ExtremeLegStrategy:L:t{T0}"
    assert "daily" in s.confluences[0].detail


def test_a_side_switched_off_is_never_tradeable():
    w = LegSetupWatch(ExtremeLegConfig(symbol="XAUUSD.p", exec_longs=False))
    w.observe(_st(0, age=0, swept=1), False)
    w.observe(_st(1, age=1, raw=True, blk=BLK_TARGET_TOO_NEAR), False)
    assert w.drain_setups()[0].tradeable is False


def test_armed_on_the_first_bar_seen_is_not_keyed_on_a_guess():
    """A replay that starts mid-window has no sweep time. MUTATION: key it on the bar's own time
    and a restart renames the setup."""
    w = _watch()
    w.observe(_st(0, age=4, raw=True, go=True, entered=1), False)
    assert w.drain_setups() == []
