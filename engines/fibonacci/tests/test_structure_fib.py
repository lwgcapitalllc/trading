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


# ── 2026-07-08 re-sync additions ──

def test_internal_swing_adopted_as_pull_anchor():
    """A more-extreme confirmed internal low is adopted as the bull fib's bottom anchor (Pine
    2277-2282). 1.0 (the low anchor) should sit at the internal low, not the structure asl."""
    fib = StructureFib()
    snap = StructureSnapshot(
        ash=110.0, asl=100.0, ash_loc=10, asl_loc=0, direction=1,
        i_confirmed_low_price=95.0, i_confirmed_low_loc=5,     # deeper than asl=100
    )
    ev = fib.update(high=109.0, low=108.0, snap=snap)
    assert ev.levels["1.0"] == 95.0                            # adopted the internal low
    assert abs(ev.levels["E1"] - (110.0 - 15.0 * 0.618)) < 1e-9


def test_internal_swing_not_adopted_when_less_extreme():
    """An internal low that is HIGHER than the structure asl is ignored — only a MORE extreme
    swing is adopted."""
    fib = StructureFib()
    snap = StructureSnapshot(
        ash=110.0, asl=100.0, ash_loc=10, asl_loc=0, direction=1,
        i_confirmed_low_price=103.0, i_confirmed_low_loc=5,    # shallower than asl=100
    )
    ev = fib.update(high=109.0, low=108.0, snap=snap)
    assert ev.levels["1.0"] == 100.0                           # kept the structure asl


def test_tp3_hit_no_longer_latches_reset_active():
    """The 2026-07-09 re-paste dropped the TP3-hit setter: TP3 (0.0) still fires a touch, but
    reset_active stays False for the whole leg — the leg is spent only when a new leg forms."""
    fib = StructureFib()
    snap = _bull_snap()                              # E1=103.82, TP1=105, TP3=110 (the high)
    fib.update(109.0, 108.0, snap)                   # origin bar
    ev = fib.update(109.0, 103.0, snap)             # tap the 0.618 gate
    assert not ev.reset_active
    ev = fib.update(110.0, 108.0, snap)             # rally back to 0.0 (TP3)
    assert "TP3" in {t.level for t in ev.touched}    # the touch still fires
    assert not ev.reset_active                       # ...but no longer latches on the tap
    ev = fib.update(110.0, 109.0, snap)             # same leg -> still not latched
    assert not ev.reset_active


def test_extend_changed_bar_skips_touch_checks():
    """A bar on which the extending anchor itself moved skips ALL touched-checks (Pine
    fiboExtChanged) — a live wick that just moved the anchor can't retroactively satisfy the very
    level it created. The checks resume once the anchor is stable again."""
    fib = StructureFib()
    snap = _bull_snap()                              # ash=110, asl=100; E1=103.82
    fib.update(109.0, 108.0, snap)                   # origin bar
    fib.update(109.0, 103.0, snap)                   # gate reached (low 103 <= 103.82)
    # This bar MOVES the top anchor (110 -> 112, same origin) AND prints a high reaching old TP1.
    moved = _bull_snap(ash=112.0)                    # ash_loc/asl_loc default -> origin unchanged
    ev = fib.update(high=106.0, low=104.0, snap=moved)
    assert abs(ev.levels["E1"] - (112.0 - 12.0 * 0.618)) < 1e-9   # levels recomputed off the moved anchor
    assert not ev.origin_changed                     # origin bar unchanged — only the anchor moved
    assert ev.touched == []                          # ...but touched-checks skipped this bar
    # Next bar, anchor stable -> checks resume; TP1 for the 100->112 leg = 106, high 106 -> fires.
    ev = fib.update(high=106.0, low=104.0, snap=moved)
    assert "TP1" in {t.level for t in ev.touched}


# ── 2026-07-10 re-sync addition: fiboHalfReached (A+ EARLY tier) ──

def test_half_reached_inbound_05_is_ungated():
    """fiboHalfReached latches on the INBOUND 0.5 (TP1 price) tap during the retrace, WITHOUT the
    0.618 gate — the A+ EARLY entry tier. Distinct from the TP1 target, which needs the gate and
    tests the same price on the way OUT (Pine 2443)."""
    fib = StructureFib()
    snap = _bull_snap()                              # asl=100, ash=110 -> 0.5=105.0, E1(0.618)=103.82
    fib.update(109.0, 108.0, snap)                   # origin bar (checks skipped)
    # Retrace down to tap 0.5 (low 104.5 <= 105) but NOT reach 0.618 (104.5 > 103.82).
    ev = fib.update(high=106.0, low=104.5, snap=snap)
    assert ev.half_reached                            # inbound 0.5 tapped
    assert "E1" not in ev.touched_so_far              # gate NOT reached -> proves it is ungated
    assert "TP1" not in {t.level for t in ev.touched}  # the TP1 target did not fire (needs the gate)


def test_half_reached_resets_on_new_leg():
    fib = StructureFib()
    snap = _bull_snap()
    fib.update(109.0, 108.0, snap)
    ev = fib.update(106.0, 104.5, snap)              # half reached on this leg
    assert ev.half_reached
    # New leg (origin bar moves): checks skipped this bar, and the latch is reset with the leg.
    new = _bull_snap(ash=120.0, asl=108.0, ash_loc=60, asl_loc=50)
    ev = fib.update(high=115.0, low=114.0, snap=new)
    assert ev.origin_changed
    assert not ev.half_reached
