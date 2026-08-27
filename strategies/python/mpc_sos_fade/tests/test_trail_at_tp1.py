"""`exec_sec_trail_at_tp1` — a re-entry hands to the runner trail at its FIRST target.

Watched RED against HEAD: the field did not exist, so every test failed at construction. The
behavioural guarantees were then re-proved BY MUTATION against the real implementation, because
"the field is new" cannot tell a rule that works from one that is merely present.

⚠ The guarantee that matters most is the FLOOR. Collapsing both rungs onto the first target
without moving the floor would put the stop on the price standing right now and close the runner
for the same figure the banked half just made — a change that would look like it worked (stage 2
reached, stop moved) while deleting the runner entirely.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from strategies.python.mpc_sos_fade.config import SosFadeConfig
from strategies.python.mpc_sos_fade.execution import Decision, Execution, _Pending

# A long re-entry at 100.00 risking 2.00. Its first target is 1.25R = 102.50 (the shipped rung),
# and the fib second rung is put at 106.00 — comfortably beyond, so nothing here is explained by
# a flip unless a test says so.
ENTRY, STOP, TP1_FIB, TP2_FIB = 100.0, 98.0, 105.0, 106.0
FIRST = 102.5          # 1.25R, what the re-entry actually aims at


def _fill(direction=1, entry=ENTRY, sl=STOP, tp1=TP1_FIB, tp2=TP2_FIB,
          kind="secondary", **cfg_kw):
    cfg = SosFadeConfig(exec_secondary=True, **cfg_kw)
    ex = Execution(cfg)
    pend = _Pending(direction, entry, 1.0, sl, tp1, tp2, 1000)
    bar = SimpleNamespace(index=1, time_ms=0, open=entry, high=entry, low=entry, close=entry,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, entry, bar, Decision(index=1), kind=kind)
    return ex


def _bar(high, low=None, o=ENTRY, c=ENTRY):
    return SimpleNamespace(index=2, time_ms=60_000, open=o, high=high,
                           low=ENTRY if low is None else low, close=c,
                           last_conf_high=None, last_conf_low=None)


def test_it_ships_off_so_no_deployed_bot_moves():
    """A default that armed would change what the live bot trades the moment this landed."""
    assert SosFadeConfig().exec_sec_trail_at_tp1 is False
    ex = _fill()
    assert ex._stage_rungs() == (FIRST, TP2_FIB)


def test_both_rungs_collapse_onto_the_FIRST_target():
    ex = _fill(exec_sec_trail_at_tp1=True)
    assert ex._stage_rungs() == (FIRST, FIRST)


def test_touching_the_first_target_arms_stage_TWO_where_the_shipped_ladder_reaches_only_one():
    """The whole point: the runner starts trailing at a price the strategy chose, rather than
    waiting on a level fixed to the first trade's chart."""
    off = _fill()
    off._advance_stage(_bar(high=FIRST))
    assert off._stage == 1

    on = _fill(exec_sec_trail_at_tp1=True)
    on._advance_stage(_bar(high=FIRST))
    assert on._stage == 2


def test_the_stage_two_floor_is_BREAKEVEN_and_NOT_the_price_just_reached():
    """🔴 THE TEST THIS FILE EXISTS FOR. The floor normally sits at the rung that armed stage 2.
    Here that rung IS the current price, so leaving it would stop the runner out instantly."""
    ex = _fill(exec_sec_trail_at_tp1=True)
    ex._advance_stage(_bar(high=FIRST))
    stop = ex._current_stop()
    assert stop < FIRST, "the stop was left on the price price just reached"
    assert stop == pytest.approx(ENTRY + ex._be_buffer(hold_ok=False))


def test_the_stop_is_never_LOOSER_than_the_breakeven_the_shipped_ladder_would_have_held():
    """Stage 1 already holds breakeven, so this mode may tighten and must never give ground."""
    off = _fill()
    off._advance_stage(_bar(high=FIRST))
    on = _fill(exec_sec_trail_at_tp1=True)
    on._advance_stage(_bar(high=FIRST))
    assert on._current_stop() >= off._current_stop()


def test_it_mirrors_for_a_short():
    first = 100.0 - 1.25 * 2.0        # 97.50
    ex = _fill(direction=-1, entry=100.0, sl=102.0, tp1=95.0, tp2=94.0,
               exec_sec_trail_at_tp1=True)
    assert ex._stage_rungs() == (first, first)
    ex._advance_stage(_bar(high=100.0, low=first, o=100.0, c=100.0))
    assert ex._stage == 2
    assert ex._current_stop() > first


def test_a_FLIPPED_ladder_cannot_survive_this_mode():
    """With no second rung consulted there is no second ruler left to disagree with the first,
    so the ordering problem this mode inherits simply cannot occur."""
    ex = _fill(tp2=100.6, exec_sec_trail_at_tp1=True)   # fib rung INSIDE the first target
    near, far = ex._stage_rungs()
    assert near == far == FIRST


def test_it_never_touches_a_PRIMARY():
    """Secondaries only — a primary's ladder is the ported path the parity gate checks."""
    ex = _fill(kind="primary", exec_sec_trail_at_tp1=True)
    assert ex._stage_rungs() == (TP1_FIB, TP2_FIB)
    ex._advance_stage(_bar(high=TP1_FIB))
    assert ex._stage == 1


def test_the_other_floor_modes_are_left_alone():
    """Neither names the rung, and both already floor at breakeven, so neither can collapse onto
    the current price — overriding them would be a change with no defect behind it."""
    ex = _fill(exec_sec_trail_at_tp1=True, exec_tp2_stop_mode="Breakeven")
    ex._advance_stage(_bar(high=FIRST))
    assert ex._current_stop() == pytest.approx(ENTRY + ex._be_buffer(hold_ok=False))


def test_the_step_trail_anchors_on_the_first_target_in_this_mode():
    """The run is measured from the rung that armed stage 2. Anchoring the stop on a second rung
    this mode never consults would place the trail at a price neither rung names."""
    ex = _fill(exec_sec_trail_at_tp1=True, exec_runner_trail="Fixed step",
               exec_trail_step=0.5)
    ex._advance_stage(_bar(high=FIRST + 1.6))
    t = ex._trail()
    assert t is not None
    assert t == pytest.approx(FIRST + 1.0)      # anchored on 102.50, two 0.50 steps


def test_the_UI_contract_carries_it_ungreyed():
    """A field with no contract row is invisible in the Command Center, which is how a lever gets
    built, measured, and then never reached by the person who needs it."""
    import json
    p = Path(__file__).resolve().parents[1] / "mpc_sos_fade.meta.json"
    row = [x for x in json.loads(p.read_text())["params"]
           if x["name"] == "exec_sec_trail_at_tp1"]
    assert len(row) == 1
    assert row[0]["show_if"] == {"exec_secondary": True}
    assert "disable_if" not in row[0]
