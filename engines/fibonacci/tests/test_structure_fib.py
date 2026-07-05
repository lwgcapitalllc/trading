"""
Hand-traced tests for the fib geometry core and the Structure fib state machine.

These pin the ported Pine behaviour: the shared geometry, and the gated first-touch sequence
(0.618 gates everything; targets only arm from the bar AFTER 0.618; a new leg resets all touches).
Full Pine↔Python parity is validated separately against a TradingView export, same as
market_structure/.

Run:  python3 -m pytest fibonacci/tests/ -q      (from the repo root)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fibonacci import StructureFib, StructureSnapshot, fib_level, fib_levels


# ── geometry core ──

def test_fib_level_bull_and_bear():
    # Bull: retracements measured DOWN from the high.
    assert fib_level(110.0, 100.0, 1, 0.0) == 110.0     # 0.0 = the high (origin at low, top at high)
    assert fib_level(110.0, 100.0, 1, 0.618) == 110.0 - 10.0 * 0.618
    assert fib_level(110.0, 100.0, 1, 1.0) == 100.0     # full retrace back to the low
    # Bear: mirror — measured UP from the low.
    assert fib_level(110.0, 100.0, -1, 0.618) == 100.0 + 10.0 * 0.618
    assert fib_level(110.0, 100.0, -1, 1.0) == 110.0


def test_fib_levels_names():
    lv = fib_levels(110.0, 100.0, 1, [("E1", 0.618), ("TP1", 0.5)])
    assert set(lv) == {"E1", "TP1"}
    assert lv["TP1"] == 105.0


# ── Structure fib state machine ──

def _bull_snap(ash=110.0, asl=100.0, ash_loc=10, asl_loc=0):
    """A stable bull-leg snapshot (origin at asl_loc). No pullback in progress."""
    return StructureSnapshot(ash=ash, asl=asl, ash_loc=ash_loc, asl_loc=asl_loc, direction=1)


def test_first_bar_is_origin_change_and_no_touches():
    fib = StructureFib()
    ev = fib.update(high=109.0, low=108.0, snap=_bull_snap())
    assert ev.active
    assert ev.origin_changed          # first valid leg counts as an origin change
    assert ev.touched == []           # checks skipped on the origin bar


def test_gate_then_targets_sequence():
    fib = StructureFib()
    snap = _bull_snap()               # E1=103.82, TP1=105.0

    fib.update(109.0, 108.0, snap)    # bar 0: origin bar, skipped
    fib.update(109.0, 108.0, snap)    # bar 1: nothing reached

    # bar 2: price taps 0.618 AND spikes up through TP1 (105) in the same bar.
    ev = fib.update(high=105.5, low=103.5, snap=snap)
    names = {t.level for t in ev.touched}
    assert "E1" in names              # gate fires the bar it is first hit
    assert "TP1" not in names         # targets must NOT fire on the same bar the gate is first hit

    # bar 3: price rallies to TP1 -> now it fires (gate was reached on a previous bar).
    ev = fib.update(high=105.2, low=104.0, snap=snap)
    assert {t.level for t in ev.touched} == {"TP1"}
    assert ev.touched[0].role == "target"


def test_deeper_retrace_levels_fire_together():
    fib = StructureFib()
    snap = _bull_snap()               # E1=103.82, E2=102.98, E3=102.14
    fib.update(109.0, 108.0, snap)    # origin bar
    # One bar that stabs from 0.618 down through 0.786: E1, E2, E3 all first-touched at once.
    ev = fib.update(high=104.0, low=102.0, snap=snap)
    assert {t.level for t in ev.touched} == {"E1", "E2", "E3"}
    assert all(t.role == "entry" for t in ev.touched)


def test_touch_is_edge_triggered_once():
    fib = StructureFib()
    snap = _bull_snap()
    fib.update(109.0, 108.0, snap)
    fib.update(104.0, 103.5, snap)    # E1 touched here
    ev = fib.update(104.0, 103.0, snap)  # still below E1, but already touched
    assert "E1" not in {t.level for t in ev.touched}   # fires once, not every bar
    assert "E1" in ev.touched_so_far                   # ...but stays in cumulative state


def test_new_leg_resets_touches():
    fib = StructureFib()
    snap = _bull_snap()
    fib.update(109.0, 108.0, snap)
    fib.update(104.0, 103.5, snap)               # E1 touched
    # New leg: origin bar moves (different asl_loc) -> everything resets, checks skipped this bar.
    new = _bull_snap(ash=120.0, asl=105.0, ash_loc=60, asl_loc=50)
    ev = fib.update(104.0, 103.5, snap=new)
    assert ev.origin_changed
    assert ev.touched == []
    assert ev.touched_so_far == set()


def test_pullback_extreme_extends_anchor():
    """While a pullback is in progress the fib should follow the live extreme (pb_extreme),
    not the last locked swing — so the leg extends with the move exactly like the chart."""
    fib = StructureFib()
    # Bull leg with an in-progress pullback high that is HIGHER than the locked ash.
    snap = StructureSnapshot(
        ash=110.0, asl=100.0, ash_loc=10, asl_loc=0, direction=1,
        pb_mode=1, pb_extreme=112.0, pb_extreme_loc=15,
    )
    fib.update(111.0, 109.0, snap)                 # origin bar establishes anchors
    ev = fib.update(111.0, 109.0, snap)
    # E1 for a 100->112 leg is 112 - 12*0.618 = 104.584, not the 103.82 of the un-extended leg.
    assert abs(ev.levels["E1"] - (112.0 - 12.0 * 0.618)) < 1e-9
