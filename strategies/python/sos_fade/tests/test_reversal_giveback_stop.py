"""The reversal exit's "Give-back stop" action, its "Target 2 price" arm and its "break first" gate.

WHY THIS EXISTS. Aaron, 2026-09-25, off a live XAUUSD short that passed its second target, broke
structure its own way on 5m, then shifted against on 5m and handed most of the profit back: *"that
shift of structure in five minutes signals time to get out as soon as price retraces at least 50
percent"*. Pinned: arm when the best reaches the trade's own TP2 price; on a 5m shift against, rest
a stop where half the open profit (entry -> best) is gone, moving with the best; if price is
already past it, leave at the next fast bar's open. It only tightens.

Every behaviour test below was watched RED under a named mutation, recorded in its docstring.
"""

import pytest

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.execution import Execution


class _M1:
    """This bar's fast-frame events only — never latches, like `M1State` (rule 13)."""

    def __init__(self, bull=False, bear=False, bull_bos=False, bear_bos=False):
        self.new_bull_sos = bull
        self.new_bear_sos = bear
        self.new_bull_bos = bull_bos
        self.new_bear_bos = bear_bos


class _Bar:
    def __init__(self, o, h, l, c, index=10, ts=1_600_000_000_000):
        self.index = index
        self.timestamp_ms = ts
        self.time_ms = ts
        self.open, self.high, self.low, self.close = o, h, l, c


def _short(best, tp2=4300.0, **cfg_kw):
    """An open PRIMARY short at 4370, initial stop 4390 (1R = 20), TP2 at `tp2`."""
    kw = dict(exec_rev_exit="Give-back stop", exec_rev_arm_at="Target 2 price")
    kw.update(cfg_kw)
    ex = Execution(SosFadeConfig(exec_min_atr_pct=0.0, **kw))
    ex._pos_dir = -1
    ex._entry_kind = "primary"
    ex._entry = 4370.0
    ex._init_stop = 4390.0
    ex._sl = 4390.0
    ex._tp1 = 4340.0
    ex._tp2 = tp2
    ex._qty = 1.0
    ex._filled_qty = 0.0
    ex._risk_usd = 20.0
    ex._rev_best = best
    ex._ext_high = ex._ext_low = 4370.0
    return ex


def test_defaults_are_inert():
    """MUTATION: default `exec_rev_arm_at` to "Target 2 price", or `exec_rev_need_bos` to True
    -> red. Either would move every stored run that has the reversal exit on."""
    c = SosFadeConfig()
    assert c.exec_rev_arm_at == "R"
    assert c.exec_rev_need_bos is False
    assert c.exec_rev_exit == "Off"


def test_the_level_hands_back_the_asked_share_of_entry_to_best():
    """The chart trade: short 4370, best 4291, 50% -> 4330.5.
    MUTATION: measure the share off the TP2 price instead of the entry -> red."""
    ex = _short(best=4291.0)
    assert ex._rev_lock_level() == pytest.approx(4330.5)
    ex2 = _short(best=4291.0, exec_rev_giveback_pct=38.2)
    assert ex2._rev_lock_level() == pytest.approx(4291.0 + 0.382 * 79.0)


def test_armed_by_the_target_2_PRICE_not_by_R():
    """Best 4301 is 3.45R but short of TP2 at 4300, so a shift must NOT fire it.
    MUTATION: drop the `Target 2 price` branch in `_rev_armed` (fall to R at arm 1R) -> red."""
    ex = _short(best=4301.0)
    assert ex._reversal_due(_M1(bull=True)) is False
    ex._rev_best = 4299.0
    assert ex._reversal_due(_M1(bull=True)) is True


def test_a_shift_sets_the_stop_and_does_not_close_while_price_is_still_in_front():
    """MUTATION: have `_set_rev_lock` always rest "Close" -> red."""
    ex = _short(best=4291.0)
    ex.step_reversal(_Bar(4300, 4305, 4295, 4302), _M1(bull=True))
    assert ex._rev_lock is True
    assert ex._pending_rev is None
    assert ex._pos_dir == -1


def test_price_already_past_the_level_leaves_at_the_next_fast_open():
    """Close 4335 is above 4330.5 on the shift bar -> market out at the next bar's OPEN.
    MUTATION: compare the close the wrong way round (`>= 0`) -> red."""
    ex = _short(best=4291.0)
    ex.step_reversal(_Bar(4320, 4336, 4318, 4335), _M1(bull=True))
    assert ex._pending_rev == "Close"
    assert ex._pos_dir == -1                        # nothing fills on the deciding bar
    ex.step_reversal(_Bar(4333, 4334, 4325, 4330, index=11), _M1())
    assert ex._pos_dir == 0
    assert ex.trades[-1].exit_price == pytest.approx(4333.0)


def test_the_stop_fills_at_its_own_price_when_touched():
    """MUTATION: skip `_rev_lock_hit` in phase A -> red (trade stays open)."""
    ex = _short(best=4291.0)
    ex.step_reversal(_Bar(4300, 4305, 4295, 4302), _M1(bull=True))
    ex.step_reversal(_Bar(4310, 4332, 4308, 4325, index=11), _M1())
    assert ex._pos_dir == 0
    assert ex.trades[-1].exit_price == pytest.approx(4330.5)


def test_the_level_follows_a_new_best_and_only_tightens():
    """Best extends to 4271 after the stop is set -> the stop is 4320.5, and a bar to 4325 hits it.
    MUTATION: freeze the level at the moment of the shift -> red (4330.5 is not reached)."""
    ex = _short(best=4291.0)
    ex.step_reversal(_Bar(4300, 4305, 4295, 4302), _M1(bull=True))
    ex.step_reversal(_Bar(4290, 4292, 4271, 4280, index=11), _M1())
    assert ex._rev_lock_level() == pytest.approx(4320.5)
    ex.step_reversal(_Bar(4300, 4325, 4298, 4322, index=12), _M1())
    assert ex._pos_dir == 0
    assert ex.trades[-1].exit_price == pytest.approx(4320.5)


def test_it_never_loosens_a_tighter_ladder_stop():
    """The ladder stop at 4310 is already tighter than 4330.5, so this rule stays out of it.
    MUTATION: drop the tighter-stop check in `_rev_lock_hit` -> red (it would close at 4330.5)."""
    ex = _short(best=4291.0)
    ex._stage = 2
    ex._current_stop = lambda: 4310.0
    ex.step_reversal(_Bar(4300, 4305, 4295, 4302), _M1(bull=True))
    ex.step_reversal(_Bar(4305, 4332, 4300, 4325, index=11), _M1())
    assert ex._pos_dir == -1


def test_need_bos_blocks_a_shift_without_a_prior_break_our_way():
    """MUTATION: ignore `exec_rev_need_bos` in `_reversal_due` -> red."""
    ex = _short(best=4291.0, exec_rev_need_bos=True)
    assert ex._reversal_due(_M1(bull=True)) is False


def test_need_bos_accepts_a_break_after_arming_then_a_shift():
    """A bear break on an armed short, then a bull shift on the next bar -> the stop rests.
    MUTATION: read `new_bull_bos` for a short (the wrong side) -> red."""
    ex = _short(best=4291.0, exec_rev_need_bos=True)
    ex.step_reversal(_Bar(4295, 4296, 4288, 4290), _M1(bear_bos=True))
    assert ex._rev_bos_seen is True
    ex.step_reversal(_Bar(4290, 4300, 4289, 4298, index=11), _M1(bull=True))
    assert ex._rev_lock is True


def test_a_break_before_the_trade_reached_target_2_does_not_count():
    """MUTATION: drop the `_rev_armed()` condition on the break gate -> red."""
    ex = _short(best=4320.0, exec_rev_need_bos=True)
    ex.step_reversal(_Bar(4320, 4322, 4315, 4318), _M1(bear_bos=True))
    assert ex._rev_bos_seen is False


def test_the_new_state_is_in_the_position_record():
    """A restored trade must not come back with its stop forgotten."""
    assert "_rev_lock" in Execution._POSITION_FIELDS
    assert "_rev_bos_seen" in Execution._POSITION_FIELDS


@pytest.mark.parametrize("kw,field", [
    (dict(exec_rev_exit="Give-back stop", exec_rev_giveback_pct=0.0), "exec_rev_giveback_pct"),
    (dict(exec_rev_exit="Give-back stop", exec_rev_giveback_pct=100.0), "exec_rev_giveback_pct"),
    (dict(exec_rev_arm_at="TP2"), "exec_rev_arm_at"),
    (dict(exec_rev_need_bos="yes"), "exec_rev_need_bos"),
])
def test_bad_values_are_refused(kw, field):
    with pytest.raises(ValueError, match=field):
        SosFadeConfig(**kw)


def test_a_fast_bar_through_the_ladder_stop_hands_the_close_to_the_15m_step():
    """The 2022-08-03 defect: the ladder's stop was hit on a fast bar, a shift printed, and this
    path closed the trade on a LATER fast bar at a worse price than the stop it had already hit.
    Here the ladder stop is 4310 and the bar trades to 4336 with a shift and a close past the
    give-back level — the rule must stand down, never rest a market close behind the stop.
    MUTATION: delete Phase 0 in `step_reversal` -> red (`_pending_rev` is "Close", then the
    next fast bar closes the trade at its open, 4333, above the 4310 stop)."""
    ex = _short(best=4291.0)
    ex._stage = 2
    ex._current_stop = lambda: 4310.0
    ex.step_reversal(_Bar(4320, 4336, 4318, 4335), _M1(bull=True))
    assert ex._pending_rev is None
    ex.step_reversal(_Bar(4333, 4334, 4325, 4330, index=11), _M1())
    assert ex._pos_dir == -1                        # the 15m step fills the stop, not this path
    assert "_rev_yield" in Execution._POSITION_FIELDS
