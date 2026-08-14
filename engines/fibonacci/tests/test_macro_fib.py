"""
Hand-traced tests for the Macro cycle fib state machine.

These pin the ported Pine behaviour (mpc_assistant.pine GRP_MACRO): the bottom locks on a bullish
SOS after a bearish SOS, the top extends on new confirmed HHs, the cycle resets when price closes
below the locked bottom and hides when it closes above the top, and level touches are gated on
0.618 like the Structure fib. The last test pins the subtle edge rule — a level reset and
re-touched on the SAME bar emits no event, matching Pine's `X and not X[1]` plot. Full parity is
validated separately against a <=5m TradingView export (compare_fib.py).

Run:  python3 -m pytest fibonacci/tests/ -q      (from the repo root)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fibonacci import MacroFib, StructureSnapshot


def _snap(
    bull_sos=False, bear_sos=False, lch=None, lch_loc=None, lcl=None, lcl_loc=None, direction=0
):
    return StructureSnapshot(
        bull_sos=bull_sos,
        bear_sos=bear_sos,
        last_conf_high=lch,
        last_conf_high_loc=lch_loc,
        last_conf_low=lcl,
        last_conf_low_loc=lcl_loc,
        direction=direction,
    )


def _lock_cycle(fib):
    """Drive a fib through a bear-SOS -> lower-low -> bull-SOS lock. Cycle: bot=90, top=200.

    Returns after the lock bar (bar 20, price parked up near the top so nothing is touched yet).
    """
    fib.update(10, high=105, low=100, close=101, snap=_snap(bear_sos=True))  # bear SOS, low 100
    fib.update(12, high=95, low=90, close=92, snap=_snap())  # deeper low 90
    return fib.update(
        20,
        high=200,
        low=195,
        close=198,
        snap=_snap(bull_sos=True, lch=200, lch_loc=18, lcl=90, lcl_loc=12),
    )


def test_no_cycle_until_bull_sos():
    fib = MacroFib()
    ev = fib.update(5, high=105, low=100, close=102, snap=_snap(bear_sos=True))
    assert not ev.active and not ev.locked
    ev = fib.update(6, high=104, low=99, close=100, snap=_snap())
    assert not ev.active


def test_bull_sos_locks_cycle_with_correct_anchors_and_levels():
    fib = MacroFib()
    ev = _lock_cycle(fib)
    assert ev.active and ev.new_cycle and ev.direction == 1
    assert ev.top == 200.0 and ev.bot == 90.0
    # HH at 0.0 = top, LL at 1.0 = bottom, others measured down from the top over the 110 range.
    assert ev.levels["HH"] == 200.0
    assert ev.levels["LL"] == 90.0
    assert ev.levels["TP1"] == 200.0 - 110.0 * 0.5
    assert abs(ev.levels["E1"] - (200.0 - 110.0 * 0.618)) < 1e-9


def test_gate_then_target_sequence():
    fib = MacroFib()
    _lock_cycle(fib)  # E1 = 132.02, TP1 = 145
    ev = fib.update(21, high=200, low=130, close=140, snap=_snap())  # pull back to the gate
    assert "E1" in {t.level for t in ev.touched}
    assert "TP1" not in {t.level for t in ev.touched}  # target can't fire the bar the gate is hit
    ev = fib.update(22, high=150, low=148, close=149, snap=_snap())  # push back up to TP1
    assert {t.level for t in ev.touched} == {"TP1"}
    assert ev.touched[0].role == "target"


def test_deeper_retrace_levels_fire_together():
    fib = MacroFib()
    _lock_cycle(fib)  # E1=132.02 E2=122.78 E3=113.54
    ev = fib.update(21, high=200, low=113.0, close=120, snap=_snap())  # stab through 0.786
    assert {t.level for t in ev.touched} == {"E1", "E2", "E3"}
    assert all(t.role == "entry" for t in ev.touched)


def test_close_below_bottom_resets_cycle():
    fib = MacroFib()
    _lock_cycle(fib)
    ev = fib.update(21, high=95, low=88, close=89.0, snap=_snap())  # close under the locked LL
    assert not ev.active and not ev.locked and ev.direction == 0


def test_close_above_top_hides_but_stays_locked():
    fib = MacroFib()
    _lock_cycle(fib)
    ev = fib.update(21, high=206, low=201, close=205.0, snap=_snap())  # close above the top
    assert not ev.active and not ev.visible
    assert ev.locked  # cycle is hidden, not reset


def test_new_hh_extends_top_and_resets_touches():
    fib = MacroFib()
    _lock_cycle(fib)
    fib.update(21, high=200, low=130, close=140, snap=_snap())  # E1 touched on the old range
    ev = fib.update(
        22, high=205, low=195, close=203, snap=_snap(lch=210, lch_loc=30)
    )  # new confirmed HH 210
    assert ev.extended and ev.top == 210.0
    assert ev.touched_so_far == set()  # new range wipes touches


def test_bottom_anchor_is_always_running_low_not_structure_lcl():
    """2026-07-08 re-sync: the bottom anchor is ALWAYS the running lowest-low since the bear SOS,
    never the structure engine's last_conf_low (which can be a historical scan reaching before the
    SOS). Here the running low bottomed at 90 while last_conf_low reports a deeper 85 from further
    back — the lock must use 90."""
    fib = MacroFib()
    fib.update(10, high=105, low=100, close=101, snap=_snap(bear_sos=True))  # bear SOS, low 100
    fib.update(12, high=95, low=90, close=92, snap=_snap())  # running low bottoms at 90
    ev = fib.update(
        20,
        high=200,
        low=195,
        close=198,
        snap=_snap(bull_sos=True, lch=200, lch_loc=18, lcl=85, lcl_loc=15),
    )
    assert ev.new_cycle and ev.bot == 90.0  # 90 (running low), NOT 85 (structure lcl)


def test_same_bar_reset_and_retouch_emits_no_event():
    """The Macro does NOT skip checks on an extend bar, so a level can be reset then re-touched on
    the same bar. Pine's plot compares to the previous bar (`X and not X[1]`), so it emits nothing
    if that level was already touched last bar. The engine must match: no E1 event on the extend
    bar, even though E1 is (re)touched within it."""
    fib = MacroFib()
    _lock_cycle(fib)
    fib.update(21, high=200, low=130, close=140, snap=_snap())  # E1 touched (prev-bar True)
    ev = fib.update(
        22,
        high=200,
        low=130,
        close=140,  # extend to 210 AND low still at 130
        snap=_snap(lch=210, lch_loc=30),
    )
    assert ev.extended
    assert "E1" not in {t.level for t in ev.touched}  # suppressed: was True last bar
    assert "E1" in ev.touched_so_far  # ...but it IS (re)touched
