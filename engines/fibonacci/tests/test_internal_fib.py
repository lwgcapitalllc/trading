"""
Hand-traced tests for the Internal fib state machine (the 4th fib, GRP_IFIB).

These pin the ported Pine behaviour (mpc_assistant.pine's Internal Fib block): the fib seeds off an
internal-structure leg (an iBOS/iSOS, delivered as the snapshot's ifib_seed_*), extends its moving
anchor live, registers first touches on the same 0.618 gate as the other fibs (skipping the checks
on any bar the moving anchor itself changed — Pine iFibExtChanged), and is wiped by ANY external
BOS/SOS. Full Pine↔Python parity is validated separately against a <=5m TradingView export
(compare_fib.py, px_ifib_* touch pulses).

Run:  python3 -m pytest fibonacci/tests/ -q      (from the repo root)
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fibonacci import InternalFib, StructureSnapshot


def _seed(d, asl, ash, asl_loc=0, ash_loc=10):
    """A snapshot carrying an internal-fib seed (an iBOS/iSOS fired this bar)."""
    return StructureSnapshot(
        ifib_seed_dir=d, ifib_seed_asl=asl, ifib_seed_asl_loc=asl_loc,
        ifib_seed_ash=ash, ifib_seed_ash_loc=ash_loc,
    )


def _ext(bull_bos=False, bear_bos=False, bull_sos=False, bear_sos=False):
    return StructureSnapshot(bull_bos=bull_bos, bear_bos=bear_bos, bull_sos=bull_sos, bear_sos=bear_sos)


def _plain():
    return StructureSnapshot()


# ── seeding / clearing ──

def test_seed_activates_bull_leg():
    fib = InternalFib()
    ev = fib.update(0, high=109.0, low=108.0, snap=_seed(1, 100.0, 110.0))
    assert ev.active and ev.seeded and ev.direction == 1
    assert ev.top == 110.0 and ev.bot == 100.0


def test_external_break_clears_fib():
    fib = InternalFib()
    fib.update(0, high=109.0, low=108.0, snap=_seed(1, 100.0, 110.0))
    ev = fib.update(1, high=109.0, low=108.0, snap=_ext(bull_sos=True))
    assert not ev.active and ev.cleared and ev.direction == 0


def test_external_break_wins_over_same_bar_seed():
    """Pine runs the internal-fib clear AFTER the seed, so a same-bar external break wipes a fresh
    seed."""
    fib = InternalFib()
    snap = StructureSnapshot(
        ifib_seed_dir=1, ifib_seed_asl=100.0, ifib_seed_asl_loc=0,
        ifib_seed_ash=110.0, ifib_seed_ash_loc=10, bear_sos=True,
    )
    ev = fib.update(0, high=109.0, low=108.0, snap=snap)
    assert not ev.active and ev.cleared


# ── live extension ──

def test_bull_anchor_extends_up_with_new_highs():
    fib = InternalFib()
    fib.update(0, high=109.0, low=108.0, snap=_seed(1, 100.0, 110.0))
    ev = fib.update(1, high=115.0, low=108.0, snap=_plain())
    assert ev.top == 115.0                       # 0.0 anchor rode up to the new high


def test_bear_anchor_extends_down_with_new_lows():
    fib = InternalFib()
    fib.update(0, high=112.0, low=111.0, snap=_seed(-1, 100.0, 110.0))
    ev = fib.update(1, high=112.0, low=95.0, snap=_plain())
    assert ev.bot == 95.0                        # 0.0 anchor (bear) rode down to the new low


# ── touch machine ──

def test_gate_then_target_sequence():
    fib = InternalFib()
    # Bull leg 100->110: E1=103.82, TP1=105, TP3=110.
    fib.update(0, high=109.0, low=108.0, snap=_seed(1, 100.0, 110.0))
    ev = fib.update(1, high=104.0, low=103.0, snap=_plain())    # tap 0.618
    assert "E1" in {t.level for t in ev.touched}
    assert "TP1" not in {t.level for t in ev.touched}          # target can't fire the gate bar
    ev = fib.update(2, high=105.5, low=104.0, snap=_plain())    # push up to TP1
    assert "TP1" in {t.level for t in ev.touched}
    assert ev.touched[0].role == "target"


def test_retrace_levels_arm_once_e1_ever_touched():
    """Unlike the Structure fib, the Internal fib's deeper retrace levels arm the moment E1 is
    EVER touched (persistent), not only while price is currently at/through 0.618."""
    fib = InternalFib()
    fib.update(0, high=109.0, low=108.0, snap=_seed(1, 100.0, 110.0))   # E2=102.98, E3=102.14
    fib.update(1, high=104.0, low=103.0, snap=_plain())                 # E1 touched (low 103)
    ev = fib.update(2, high=104.0, low=102.0, snap=_plain())            # later stab down to 0.786
    assert {"E2", "E3"}.issubset({t.level for t in ev.touched})


def test_tp3_hit_no_longer_latches_reset_active():
    """The 2026-07-09 re-paste dropped the TP3-hit setter — TP3 (0.0) still fires a touch, but
    reset_active stays False (the leg is spent only on the external-break wipe, not on the tap)."""
    fib = InternalFib()
    fib.update(0, high=109.0, low=108.0, snap=_seed(1, 100.0, 110.0))
    fib.update(1, high=104.0, low=103.0, snap=_plain())        # gate (E1)
    ev = fib.update(2, high=110.0, low=104.0, snap=_plain())   # rally to 0.0 (TP3)
    assert "TP3" in {t.level for t in ev.touched}              # the touch still fires
    assert not ev.reset_active                                 # ...but no longer latches
    ev = fib.update(3, high=109.0, low=108.0, snap=_plain())
    assert not ev.reset_active


def test_reseed_starts_a_fresh_leg():
    fib = InternalFib()
    fib.update(0, high=109.0, low=108.0, snap=_seed(1, 100.0, 110.0))
    fib.update(1, high=104.0, low=103.0, snap=_plain())            # E1 touched on the first leg
    ev = fib.update(2, high=124.0, low=123.0, snap=_seed(1, 120.0, 130.0))  # fresh internal leg
    assert ev.seeded and ev.top == 130.0 and ev.bot == 120.0      # fresh anchors
    assert ev.touched_so_far == set()                             # old touches wiped


def test_extend_bar_skips_touch_checks():
    """A bar on which the moving anchor changed (a live wick extends the top) skips the touched-
    checks — Pine iFibExtChanged — so a fresh extreme can't retroactively satisfy the level it just
    created. The checks resume on the next stable bar."""
    fib = InternalFib()
    fib.update(0, high=109.0, low=108.0, snap=_seed(1, 100.0, 110.0))   # ash=110, asl=100
    fib.update(1, high=104.0, low=103.0, snap=_plain())                 # gate E1 (no extend: 104<110)
    ev = fib.update(2, high=116.0, low=104.0, snap=_plain())            # new high extends 110 -> 116
    assert ev.top == 116.0                          # anchor rode up
    assert ev.touched == []                          # ...but touched-checks skipped this bar
    ev = fib.update(3, high=116.0, low=104.0, snap=_plain())            # anchor stable -> checks resume
    assert "TP1" in {t.level for t in ev.touched}    # TP1 (100->116 leg) = 108, high 116 -> fires
