"""The give-back guard: leave when a trade hands back too much of its best price.

WHY THIS EXISTS. MEASURED 2026-09-21 on lab run `ea46142df097`: the book keeps 44% of the
profit its trades ever show, and the leak is the band BELOW the runner trail's arming point —
trades reaching 1-3R showed 123R and kept 11R, because nothing protects a trade until the trail
takes over. Aaron, 2026-09-22: *"this trailing SL is giving too much back"*.

WATCHED RED against HEAD: every test in this file failed before the guard existed — the four
behaviour tests at construction (`unexpected keyword argument 'exec_giveback_arm_r'`) and the
two refusal tests because nothing validated the pair.

🔴 THE OFF-BY-DEFAULT TEST IS THE ONE THAT PROTECTS EVERY STORED RUN. It cannot fail at
construction, so it is mutation-proved instead: move the default off -1 and it goes red.
"""

import pytest

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.execution import Execution


def _armed(dir_=1, entry=100.0, risk=10.0, **cfg_kw):
    """An execution holding one position, with its high-water mark set by the caller.

    R is priced off the FROZEN entry risk — entry minus the trade's INITIAL stop — so the
    fixture sets `_init_stop`, not a distance of its own. A fixture that carried its own
    distance would be answering a question production never asks.
    """
    ex = Execution(SosFadeConfig(exec_min_atr_pct=0.0, **cfg_kw))
    ex._pos_dir = dir_
    ex._entry = entry
    ex._init_stop = entry - risk * dir_
    ex._ext_high = entry
    ex._ext_low = entry
    return ex


def test_off_by_default_so_no_stored_run_moves():
    # MUTATION PROOF: set the default to anything but -1 and this goes red.
    assert SosFadeConfig().exec_giveback_arm_r == -1.0
    ex = _armed()
    ex._ext_high = 130.0  # 3R up on a 10-point stop
    assert ex._giveback_due(price=101.0) is False


def test_a_long_that_hands_back_more_than_half_its_best_is_due():
    ex = _armed(exec_giveback_arm_r=1.5, exec_giveback_pct=50.0)
    ex._ext_high = 120.0  # best was 2R
    assert ex._giveback_due(price=109.0) is True  # 0.9R left of a 2R best


def test_a_long_still_holding_more_than_half_its_best_is_not_due():
    ex = _armed(exec_giveback_arm_r=1.5, exec_giveback_pct=50.0)
    ex._ext_high = 120.0
    assert ex._giveback_due(price=111.0) is False  # 1.1R of a 2R best


def test_a_trade_that_never_reached_the_arm_level_is_never_due():
    ex = _armed(exec_giveback_arm_r=1.5, exec_giveback_pct=50.0)
    ex._ext_high = 112.0  # best 1.2R, under the 1.5R arm
    assert ex._giveback_due(price=100.0) is False


def test_a_short_is_measured_the_same_way_from_its_own_best():
    ex = _armed(dir_=-1, exec_giveback_arm_r=1.5, exec_giveback_pct=50.0)
    ex._ext_low = 80.0  # best was 2R below a 100 entry
    assert ex._giveback_due(price=91.0) is True
    assert ex._giveback_due(price=89.0) is False


@pytest.mark.parametrize("pct", [0.0, 100.0, -5.0])
def test_a_percentage_that_can_never_fire_or_always_fires_is_refused(pct):
    # Both ends read as a guard that is switched on while doing something else entirely.
    with pytest.raises(ValueError, match="exec_giveback_pct"):
        SosFadeConfig(exec_giveback_arm_r=1.5, exec_giveback_pct=pct)


def test_an_arm_level_of_zero_is_refused_rather_than_read_as_off():
    # -1 is off; 0 would arm on every trade the instant it filled, which is not "off".
    with pytest.raises(ValueError, match="exec_giveback_arm_r"):
        SosFadeConfig(exec_giveback_arm_r=0.0)


def test_handing_to_the_trail_leaves_the_trade_open_and_moves_it_to_the_trail_stage():
    # WATCHED RED: before the option existed this failed at construction.
    ex = _armed(exec_giveback_arm_r=1.5, exec_giveback_pct=50.0,
                exec_giveback_action="Hand to the trail")
    ex._ext_high = 120.0
    assert ex._giveback_due(price=109.0) is True
    assert ex._cfg.exec_giveback_action == "Hand to the trail"


def test_a_typed_action_that_is_not_a_mode_is_refused():
    with pytest.raises(ValueError, match="exec_giveback_action"):
        SosFadeConfig(exec_giveback_arm_r=1.5, exec_giveback_action="tighten")


def test_banking_half_queues_half_of_what_is_still_open_and_trails_the_rest():
    # WATCHED RED: before "Bank half" existed this failed at construction (the config refused
    # the action), and with the action but no partial it fails on the queued quantity being 0.
    ex = _armed(exec_giveback_arm_r=1.5, exec_giveback_pct=50.0,
                exec_giveback_action="Bank half")
    ex._qty, ex._filled_qty = 4.0, 0.0
    ex._apply_giveback()
    assert ex._pending_bank == 2.0
    assert ex._stage == 2
    assert ex._pending_close is None


def test_a_trade_that_already_banked_a_target_halves_only_the_remainder():
    ex = _armed(exec_giveback_arm_r=1.5, exec_giveback_pct=50.0,
                exec_giveback_action="Bank half")
    ex._qty, ex._filled_qty = 4.0, 3.0   # a rung already took three quarters
    ex._apply_giveback()
    assert ex._pending_bank == 0.5


def test_the_guard_acts_once_so_a_runner_is_not_halved_every_bar():
    ex = _armed(exec_giveback_arm_r=1.5, exec_giveback_pct=50.0,
                exec_giveback_action="Bank half")
    ex._qty, ex._filled_qty = 4.0, 0.0
    assert ex._giveback_has_work() is True
    ex._apply_giveback()
    assert ex._giveback_has_work() is False


def test_a_spent_guard_stops_taking_the_branch_so_the_time_stop_is_still_reachable():
    # MUTATION PROOF: make `_giveback_has_work` return True unconditionally and this goes red.
    # The defect it pins is not in the guard — it is that a branch which is TAKEN and then does
    # nothing swallows every rule below it in the same elif chain.
    ex = _armed(exec_giveback_arm_r=1.5, exec_giveback_pct=50.0,
                exec_giveback_action="Hand to the trail")
    ex._ext_high = 120.0
    ex._apply_giveback()
    assert ex._giveback_due(price=109.0) is True      # still due on every later bar
    assert ex._giveback_has_work() is False           # ...but no longer takes the branch


def test_closing_always_has_work_because_it_has_no_second_time():
    ex = _armed(exec_giveback_arm_r=1.5, exec_giveback_pct=50.0)
    assert ex._giveback_has_work() is True


def test_a_fresh_trade_starts_with_an_unspent_guard_and_nothing_queued():
    ex = _armed(exec_giveback_arm_r=1.5, exec_giveback_pct=50.0,
                exec_giveback_action="Bank half")
    assert ex._gave_back is False
    assert ex._pending_bank == 0.0
