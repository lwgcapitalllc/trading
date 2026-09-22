"""The PRIMARY's first rung, priced in R instead of off the fib (`exec_tp1_r`).

WHY THIS EXISTS. The primary's two rungs are fib PRICES, and a price carries no statement about
distance. Measured on run `ea46142df097` (244 trades, 2020-01-01 -> 2026-09-20): the first rung
sat at a median 1.10R but ranged 0.31R to 5.57R, with 102 of 244 below 1R. So "bank a slice at
the first target" was never "bank a slice at 1R", and only the first was expressible.

WATCHED RED against HEAD before `exec_tp1_r` existed — every test here failed, the config ones
with TypeError (unexpected keyword) and the pricing ones by returning the raw fib level. The
default test is the one that cannot go red that way and is mutation-proved instead: flip the
default to a positive R and it fails, which is what guards every stored run's reproducibility.
"""

from types import SimpleNamespace

import pytest

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.execution import Decision, Execution, _Pending


def _fill_primary(*, entry, sl, tp1, tp2, direction=1, **cfg_kw):
    cfg = SosFadeConfig(exec_min_atr_pct=0.0, **cfg_kw)
    ex = Execution(cfg)
    pend = _Pending(direction, entry, 1.0, sl, tp1, tp2, 1000)
    bar = SimpleNamespace(index=1, time_ms=0, open=entry, high=entry, low=entry, close=entry,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, entry, bar, Decision(index=1), kind="primary")
    return ex


def test_it_is_OFF_by_default_so_every_stored_run_still_reproduces():
    """MUTATION: set the default to any positive R and this goes red. That default is the only
    thing standing between this build and every figure in sos_fade_optimization.md."""
    assert SosFadeConfig().exec_tp1_r == -1.0
    ex = _fill_primary(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0)
    assert ex._tp1 == 105.0 and ex._tp2 == 106.0


def test_a_1R_target_replaces_the_first_rung_and_leaves_the_second_alone():
    """1R for a long risking 2.00 from 100.00 is 102.00 — the trade's own risk, not the fib."""
    ex = _fill_primary(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0, exec_tp1_r=1.0)
    assert ex._tp1 == 102.0
    assert ex._tp2 == 106.0          # untouched — this lever moves ONE rung


def test_the_R_target_mirrors_for_a_short():
    ex = _fill_primary(entry=100.0, sl=102.0, tp1=95.0, tp2=94.0, direction=-1, exec_tp1_r=1.5)
    assert ex._tp1 == 97.0           # 100 - 1.5 * 2.00


def test_it_prices_off_the_INITIAL_stop_so_the_trail_cannot_drag_it_in():
    """1R must keep meaning the risk the trade was SIZED against. Re-derived from the live stop,
    every ratchet would pull the target closer and the setting would quietly stop meaning 1R."""
    ex = _fill_primary(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0, exec_tp1_r=2.0)
    assert ex._tp1 == 104.0
    ex._sl = 99.5                    # the trail ratchets…
    assert ex._tp1 == 104.0          # …and the target does not move


def test_it_can_sit_INSIDE_the_fib_rung_which_is_the_whole_point():
    """102 of 244 trades had their fib rung below 1R; the other 142 had it beyond. A setting that
    only ever pushed the rung one way would not be an R rung."""
    near = _fill_primary(entry=100.0, sl=98.0, tp1=101.0, tp2=110.0, exec_tp1_r=1.0)
    assert near._tp1 == 102.0        # pushed OUT past a fib rung that sat at 0.5R
    far = _fill_primary(entry=100.0, sl=98.0, tp1=109.0, tp2=110.0, exec_tp1_r=1.0)
    assert far._tp1 == 102.0         # pulled IN from a fib rung that sat at 4.5R


def test_a_zero_or_wrong_negative_REFUSES_rather_than_resting_on_the_entry():
    with pytest.raises(ValueError, match="exec_tp1_r"):
        SosFadeConfig(exec_min_atr_pct=0.0, exec_tp1_r=0.0)
    with pytest.raises(ValueError, match="exec_tp1_r"):
        SosFadeConfig(exec_min_atr_pct=0.0, exec_tp1_r=-0.5)


def test_the_short_hold_fork_still_WINS_when_both_are_set():
    """Short-hold's point is that the WHOLE position comes off at its own target. A rung moved
    underneath it would be a ladder neither setting describes."""
    ex = _fill_primary(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0,
                       exec_tp1_r=1.0, exec_short_hold=True, exec_sh_tp_r=3.0)
    assert ex._tp1 == 106.0          # 3R, short-hold's number — not 1R


def test_a_RE_ENTRY_keeps_its_own_R_rung_and_never_reads_the_primary_one():
    """Four branches, one convention — but each trade type reads its own number."""
    cfg = SosFadeConfig(exec_min_atr_pct=0.0, exec_secondary=True,
                        exec_sec_tp_r=1.25, exec_tp1_r=1.0)
    ex = Execution(cfg)
    pend = _Pending(1, 100.0, 1.0, 98.0, 105.0, 106.0, 1000)
    bar = SimpleNamespace(index=1, time_ms=0, open=100.0, high=100.0, low=100.0, close=100.0,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, 100.0, bar, Decision(index=1), kind="secondary")
    assert ex._tp1 == 102.5          # 1.25R, the re-entry's own
