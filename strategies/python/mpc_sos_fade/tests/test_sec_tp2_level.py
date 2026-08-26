"""`exec_sec_tp2_x` — REPLACE a re-entry's second target with a multiple of the first one.

Watched RED against HEAD: the field did not exist, so every test here failed at construction.
The mutation map is in `docs/SOS_FADE_BUILD_NOTES.md` and was RUN, not reasoned.

⚠ The distinction these tests exist to pin is the one against `exec_sec_tp2_min_x`, which is a
FLOOR: it lets the fib win whenever it already sits further out. This one overrides in BOTH
directions, so the test that matters most is the one where the fib is PULLED IN.
"""
from types import SimpleNamespace

import pytest

from strategies.python.mpc_sos_fade.config import SosFadeConfig
from strategies.python.mpc_sos_fade.execution import Execution


def _fill(entry, sl, tp1, tp2, direction=1, kind="secondary", **cfg_kw):
    """Fill through the real entry path and hand back the ladder it opened with."""
    from strategies.python.mpc_sos_fade.execution import Decision, _Pending
    cfg = SosFadeConfig(exec_secondary=True, **cfg_kw)
    ex = Execution(cfg)
    pend = _Pending(direction, entry, 1.0, sl, tp1, tp2, 1000)
    bar = SimpleNamespace(index=1, time_ms=0, open=entry, high=entry, low=entry, close=entry,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, entry, bar, Decision(index=1), kind=kind)
    return ex


def test_it_ships_OFF_and_the_swing_level_stands():
    """Default must not move a single stored figure — every earlier run has to reproduce."""
    assert SosFadeConfig().exec_sec_tp2_x == -1.0
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0)
    assert ex._tp2 == 106.0


def test_it_places_the_second_target_at_the_multiple_of_the_FIRST_rung():
    """Long risking 2.00 from 100: the first rung is 1.25R = 102.50, so 2x is 105.00."""
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0, exec_sec_tp2_x=2.0)
    assert ex._tp1 == 102.5
    assert ex._tp2 == 105.0


def test_it_mirrors_for_a_short():
    ex = _fill(entry=100.0, sl=102.0, tp1=95.0, tp2=94.0, direction=-1, exec_sec_tp2_x=2.0)
    assert ex._tp1 == 97.5           # 100 - 1.25 * 2.00
    assert ex._tp2 == 95.0           # 100 - 2.0 * 2.50


def test_it_PULLS_IN_a_swing_level_that_ran_away__the_whole_difference_from_the_floor():
    """🔴 THE TEST THIS FILE EXISTS FOR. The floor lets a distant fib stand; this replaces it.

    The fib at 130.00 is 12x the first rung's distance. A floor would leave it there. Measured on
    a real run, the fib rung reached 6.732R, which is not a target any re-entry was sized for.
    """
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=130.0, exec_sec_tp2_x=2.0)
    assert ex._tp2 == 105.0          # pulled IN from 130.00


def test_it_PUSHES_OUT_a_swing_level_that_landed_inside_the_first_rung():
    """The flip itself: the fib at 101.00 sits nearer than the 102.50 first rung."""
    ex = _fill(entry=100.0, sl=98.0, tp1=101.0, tp2=101.0, exec_sec_tp2_x=2.0)
    assert ex._tp2 == 105.0


def test_the_two_rungs_end_up_in_order_on_every_arm_worth_sweeping():
    """The stated point of the setting: order by construction, not by luck."""
    for x in (1.5, 2.0, 2.5, 3.0, 4.0):
        for tp2 in (101.0, 106.0, 130.0):
            ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=tp2, exec_sec_tp2_x=x)
            assert ex._tp2 > ex._tp1, (x, tp2)


def test_it_measures_off_the_first_rung_AFTER_the_R_override_not_off_the_raw_fib():
    """Order matters: the first rung is itself replaced by a multiple of risk just above. If this
    read `pend.tp1` the multiple would be of the fib's distance and mean something else."""
    ex = _fill(entry=100.0, sl=98.0, tp1=140.0, tp2=106.0, exec_sec_tp2_x=2.0)
    assert ex._tp1 == 102.5          # the R rung, not the 140.00 fib
    assert ex._tp2 == 105.0          # 2 x 2.50, not 2 x 40.00


def test_it_prices_off_the_INITIAL_stop_so_the_trail_cannot_drag_it_in():
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0, exec_sec_tp2_x=2.0)
    assert ex._tp2 == 105.0
    ex._sl = 99.5                    # the trail ratchets…
    assert ex._tp2 == 105.0          # …and the target does not move


def test_the_floor_still_floors_the_REPLACED_level_when_both_are_on():
    """Applied BEFORE the floor, so the two compose instead of one silently winning."""
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0,
               exec_sec_tp2_x=2.0, exec_sec_tp2_min_x=3.0)
    assert ex._tp1 == 102.5
    assert ex._tp2 == 107.5          # replaced to 105.00, then floored out to 3 x 2.50


def test_it_never_touches_a_PRIMARY():
    """Secondaries only — a primary's ladder is the ported path `compare_strategy.py` gates."""
    ex = _fill(entry=100.0, sl=98.0, tp1=105.0, tp2=106.0, kind="primary", exec_sec_tp2_x=2.0)
    assert ex._tp2 == 106.0


@pytest.mark.parametrize("bad", [0.0, 1.0, 0.5, -2.0])
def test_it_REFUSES_a_multiple_that_cannot_order_the_rungs(bad):
    """Refuse rather than clamp: at or below 1.0 the second target lands on or inside the first,
    which is the flip the setting exists to remove."""
    with pytest.raises(ValueError, match="exec_sec_tp2_x"):
        SosFadeConfig(exec_secondary=True, exec_sec_tp2_x=bad)


def test_the_UI_contract_carries_it_ungreyed():
    """A field with no row in the contract is invisible in the Command Center, which is how a
    lever gets built, measured and then never reached by the person who needs it."""
    import json
    import pathlib
    p = pathlib.Path(__file__).resolve().parents[1] / "mpc_sos_fade.meta.json"
    row = [x for x in json.loads(p.read_text())["params"] if x["name"] == "exec_sec_tp2_x"]
    assert len(row) == 1
    assert row[0]["show_if"] == {"exec_secondary": True}
    assert "disable_if" not in row[0]
