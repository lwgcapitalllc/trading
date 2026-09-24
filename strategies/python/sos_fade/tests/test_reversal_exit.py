"""The reversal exit: a shift of structure against an open trade, read on the FASTER chart.

WHY THIS EXISTS. Aaron, 2026-09-22, on a demo trade that showed over $2,000 and closed red:
*"I want to know how can we confidently tell we are losing momentum, or hit a point of major
reversal ... as soon as possible so we can get out and bank our max profit."* His own definition
of a reversal is the one implemented here: *"if we're getting a shift of structure and then break
of structure coming back towards us on lower time frames, that tells me price is reversing."*

🔴 IT IS A SIGNAL, NOT A PERCENTAGE, and that is the whole difference from the give-back guard.
The guard fires off the trade's own profit curve; this fires off what the market did. MEASURED
2026-09-22: the give-back guard moves profit capture 41.0% -> 41.1%, which is why a second,
differently-shaped rule was built rather than a tighter setting of the first one.

WATCHED RED against HEAD: every behaviour test here failed before the rule existed — the config
tests at construction (`unexpected keyword argument 'exec_rev_exit'`) and the rest with
`AttributeError: 'Execution' object has no attribute 'step_reversal'`.

🔴 THE OFF-BY-DEFAULT TEST IS THE ONE THAT PROTECTS EVERY STORED RUN, and it cannot fail at
construction, so it is mutation-proved instead: change the default off "Off" and it goes red.
"""

import pytest

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.execution import Execution


class _M1:
    """The fast frame's structure state, cut down to the two fields this rule reads.

    ⚠ A DOUBLE NO MORE CAPABLE THAN THE REAL THING (rule 13): `M1State` publishes these as
    THIS BAR's events, never latches, and so does this.
    """

    def __init__(self, bull=False, bear=False):
        self.new_bull_sos = bull
        self.new_bear_sos = bear


class _Bar:
    def __init__(self, index=10, open_=100.0, ts=1_600_000_000_000):
        self.index = index
        self.timestamp_ms = ts
        self.time_ms = ts
        self.open = open_
        self.high = open_
        self.low = open_
        self.close = open_


def _armed(dir_=1, entry=100.0, risk=10.0, best=None, **cfg_kw):
    """An execution holding one PRIMARY position with its high-water mark set by the caller.

    R is priced off the FROZEN entry risk — entry minus the INITIAL stop — so the fixture sets
    `_init_stop` rather than carrying a distance of its own.
    """
    ex = Execution(SosFadeConfig(exec_min_atr_pct=0.0, **cfg_kw))
    ex._pos_dir = dir_
    ex._entry_kind = "primary"
    ex._entry = entry
    ex._init_stop = entry - risk * dir_
    # The FAST frame's own high-water mark. `_ext_high`/`_ext_low` are reporting only and are
    # widened on the 15m stream, so a fixture that set them would be describing a field this
    # rule deliberately does not read.
    ex._rev_best = entry if best is None else best
    ex._ext_high = entry
    ex._ext_low = entry
    return ex


# ── off by default ───────────────────────────────────────────────────────────

def test_off_by_default_so_no_stored_run_moves():
    # MUTATION PROOF: set the default to anything but "Off" and this goes red.
    assert SosFadeConfig().exec_rev_exit == "Off"
    ex = _armed(best=130.0)
    assert ex._reversal_due(_M1(bear=True)) is False


def test_off_means_the_fast_bar_hook_does_nothing_at_all():
    ex = _armed(best=130.0)
    ex.step_reversal(_Bar(), _M1(bear=True))
    assert ex._pending_rev is None


# ── the trigger ──────────────────────────────────────────────────────────────

def test_a_shift_against_an_armed_long_is_due():
    ex = _armed(exec_rev_exit="Close", exec_rev_arm_r=1.0, best=120.0)
    assert ex._reversal_due(_M1(bear=True)) is True


def test_a_shift_the_trade_s_OWN_way_is_not_a_reversal():
    # The defect this catches is reading the event without its side, which would exit every
    # winner on the first continuation break.
    ex = _armed(exec_rev_exit="Close", exec_rev_arm_r=1.0, best=120.0)
    assert ex._reversal_due(_M1(bull=True)) is False


def test_a_short_reads_the_mirror_event():
    ex = _armed(dir_=-1, exec_rev_exit="Close", exec_rev_arm_r=1.0, best=80.0)
    assert ex._reversal_due(_M1(bull=True)) is True
    assert ex._reversal_due(_M1(bear=True)) is False


def test_a_trade_that_was_never_far_enough_in_front_is_never_due():
    # Without the arm level this rule is a second stop loss, and the stop is faster.
    ex = _armed(exec_rev_exit="Close", exec_rev_arm_r=1.5, best=112.0)  # best 1.2R
    assert ex._reversal_due(_M1(bear=True)) is False


def test_a_re_entry_is_left_to_its_own_ladder():
    # The fast stream already manages a secondary position; two exit paths on one position and
    # one bar is two rules answering one question.
    ex = _armed(exec_rev_exit="Close", exec_rev_arm_r=1.0, best=120.0)
    ex._entry_kind = "secondary"
    assert ex._reversal_due(_M1(bear=True)) is False


def test_a_flat_book_is_never_due():
    ex = _armed(exec_rev_exit="Close", exec_rev_arm_r=1.0, best=120.0)
    ex._pos_dir = 0
    assert ex._reversal_due(_M1(bear=True)) is False


# ── the one-bar delay ────────────────────────────────────────────────────────

def test_the_decision_is_taken_at_the_close_and_rests_for_the_next_bar():
    # Nothing fills on the bar that fired the rule — the one-bar order delay this whole engine
    # is built on. Filling here would price a DECISION instead of a TRADE.
    ex = _armed(exec_rev_exit="Close", exec_rev_arm_r=1.0, best=120.0)
    ex.step_reversal(_Bar(), _M1(bear=True))
    assert ex._pending_rev == "Close"
    assert ex._pos_dir == 1          # still open


def test_a_resting_order_is_not_re_decided_on_the_next_bar():
    ex = _armed(exec_rev_exit="Bank half", exec_rev_arm_r=1.0, best=120.0)
    ex._pending_rev = "Bank half"
    assert ex._reversal_due(_M1(bear=True)) is False


# ── it is spent after one use, except when it closes ─────────────────────────

def test_the_keep_it_open_actions_fire_once_per_trade():
    # Re-banking half on every later shift walks a runner out of the market a rung at a time.
    ex = _armed(exec_rev_exit="Bank half", exec_rev_arm_r=1.0, best=120.0)
    ex._rev_done = True
    assert ex._reversal_due(_M1(bear=True)) is False


def test_closing_has_no_second_time_so_it_is_never_marked_spent():
    ex = _armed(exec_rev_exit="Close", exec_rev_arm_r=1.0, best=120.0)
    ex._rev_done = True
    assert ex._reversal_due(_M1(bear=True)) is True


# ── the restart seam ─────────────────────────────────────────────────────────

def test_the_arming_peak_is_carried_on_the_FAST_frame_not_the_15m_reporting_one():
    """The rule arms off a high-water mark this frame has actually seen.

    🔴 THE DEFECT THIS PINS, found before any number was published: the first version read
    `_ext_high`/`_ext_low`, which `_manage_open` widens on the 15m stream for a primary. On a
    fast bar they are stale by up to a whole 15m bar — the exact delay reading a faster chart
    exists to remove — and the file documents them as reporting only, never read by a decision.

    MUTATION PROOF: point `_reversal_due` back at `_ext_high` and this goes red, because the
    reporting field here still says the trade never left its entry.
    """
    ex = _armed(exec_rev_exit="Close", exec_rev_arm_r=1.0)
    ex._ext_high = 100.0          # the 15m stream has not widened yet
    ex._rev_best = None
    bar = _Bar()
    bar.high = 120.0              # but THIS fast bar printed 2R
    ex.step_reversal(bar, _M1(bear=True))
    assert ex._rev_best == 120.0
    assert ex._pending_rev == "Close"


def test_a_trade_the_fast_frame_has_not_seen_move_is_not_armed():
    # `None` means the fast frame has no reading yet, which is not the same as "no profit".
    ex = _armed(exec_rev_exit="Close", exec_rev_arm_r=1.0)
    ex._rev_best = None
    assert ex._reversal_due(_M1(bear=True)) is False


def test_both_new_fields_are_in_the_position_record():
    # A field left out of the record is SILENT: the restored trade manages against a constructor
    # default, so a spent guard would come back unspent and re-bank a runner it already halved.
    assert "_pending_rev" in Execution._POSITION_FIELDS
    assert "_rev_done" in Execution._POSITION_FIELDS
    assert "_rev_best" in Execution._POSITION_FIELDS


# ── the config refuses what it cannot mean ───────────────────────────────────

def test_a_mode_that_is_not_a_mode_is_refused():
    with pytest.raises(ValueError, match="exec_rev_exit"):
        SosFadeConfig(exec_rev_exit="Tighten")   # near-miss of a real choice


@pytest.mark.parametrize("arm", [0.0, -1.0])
def test_an_arm_level_that_would_arm_on_the_fill_is_refused(arm):
    with pytest.raises(ValueError, match="exec_rev_arm_r"):
        SosFadeConfig(exec_rev_exit="Close", exec_rev_arm_r=arm)


def test_the_arm_level_is_not_policed_while_the_rule_is_off():
    # Off means off: a stored run carrying any value must still load.
    assert SosFadeConfig(exec_rev_exit="Off", exec_rev_arm_r=0.0).exec_rev_exit == "Off"
