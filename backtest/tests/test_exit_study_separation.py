"""exit_study.py --separation: the grading of one fire, on a hand-built six-bar hold.

Pins the three things the table's meaning rests on: the exit is priced at the NEXT bar's open
(never the fire bar's close), a fire only counts once the trade's best reached the arm level, and
the REAL/FALSE label follows the definition printed in the table's header.

Watched RED by mutation (2026-09-25): pricing the exit at the fire bar's close turns 2.0 into
2.2; dropping the arm gate lets the bar-0 shift count at arm 1R; dropping the "continued" test
labels the second trade REAL.
"""

from __future__ import annotations

import types

import numpy as np

from backtest.tools.exit_study import SepFrame, separation_walk


def _bar(**flags):
    t = {
        "bull_sos": False,
        "bear_sos": False,
        "bull_bos": False,
        "bear_bos": False,
        "bull_isos": False,
        "bear_isos": False,
        "levels": (),
        "poc": None,
        "div": (),
        "bull_engulf": False,
        "bear_engulf": False,
        "fvg_formed": (),
        "high": 0.0,
        "low": 0.0,
        "close": 0.0,
    }
    t.update(flags)
    return t


def _frame(highs, opens, shift_bars):
    n = len(highs)
    track = [_bar(bear_sos=(i in shift_bars)) for i in range(n)]
    h = np.array(highs, float)
    return SepFrame(
        tf=15,
        track=track,
        stamps=np.arange(n, dtype=np.int64) * 900_000,
        o=np.array(opens, float),
        h=h,
        lo=h - 3.0,
        c=h - 1.0,
        atr=np.full(n, np.nan),
    )


def _long(r, exit_bar):
    return types.SimpleNamespace(
        dir=1,
        entry_price=100.0,
        stop_distance=10.0,
        costs_usd=0.0,
        risk_usd=100.0,
        entry_ms=0,
        exit_ms=exit_bar * 900_000,
        r=r,
    )


def test_real_reversal_priced_at_next_open_and_gated_by_arm():
    # Best R by bar: 0.5, 1.5, 2.2, 2.1, 1.8, 1.2. Shifts on bar 0 (not armed) and bar 2.
    fr = _frame([105, 115, 122, 121, 118, 112], [100, 104, 114, 120, 119, 113], {0, 2})
    fires = {(f.signal, f.arm): f for f in separation_walk(fr, _long(1.0, 5), 0, ("choch",))}
    assert set(fires) == {("choch", 1.0), ("choch", 2.0)}
    f = fires[("choch", 1.0)]
    assert f.fired_ms == 2 * 900_000  # not bar 0, which fired before the trade was 1R up
    assert abs(f.exit_r - 2.0) < 1e-9  # bar 3's OPEN, not bar 2's close
    assert f.real and abs(f.saved - 1.0) < 1e-9


def test_move_that_continues_is_a_false_alarm_even_if_the_trade_later_gives_it_back():
    # Shift at bar 2 (best 2.2R), then the trade prints 3.0R: it continued by more than 0.5R.
    fr = _frame([105, 115, 122, 130, 118, 112], [100, 104, 114, 120, 119, 113], {2})
    (f,) = [x for x in separation_walk(fr, _long(1.0, 5), 0, ("choch",)) if x.arm == 1.0]
    assert f.continued and not f.real


def test_fire_on_last_bar_of_hold_is_not_counted():
    fr = _frame([105, 115, 122, 121, 118, 112], [100, 104, 114, 120, 119, 113], {5})
    assert separation_walk(fr, _long(1.0, 5), 0, ("choch",)) == []
