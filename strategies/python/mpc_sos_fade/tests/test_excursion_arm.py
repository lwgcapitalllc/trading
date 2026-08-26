"""Protecting the stop on HOW FAR THE TRADE HAS GONE, rather than on a rung being touched.

🔴 **The stop had exactly one trigger and it was a rung touch.** A trade could run a full R in
profit and, as far as the stop was concerned, nothing had happened. MEASURED on the re-entry short
of 2020-11-04 (run `ed21fca08a91`): entry 1902.97, frozen stop 1912.55354, risk 9.58354, nearest
rung 1.25R away. Its best price was 1893.23 — **1.016R in profit** — so it never reached the rung,
the stop never left 1912.55354, and it finished at a full loss. In the shipped configuration the
same trade LIVED, but only because its ladder came out flipped and put a rung at 0.757R: it was
protected by an accident of geometry, not by a rule.

What these tests pin is the SHAPE, not one run's arithmetic:

* the feature ships OFF, so no stored result and no deployed bot can move without a config change;
* it arms on EXCURSION with no rung touched — the case above, reproduced at test scale;
* it LATCHES, because `_max_fav` is restored state and a stop that can un-ratchet is a trade that
  can lose after it was protected;
* the trigger is measured off the FROZEN entry stop, so it cannot creep in as the stop ratchets;
* it can only ever TIGHTEN — a touched rung outranks it, and the armed stop always lands strictly
  between the entry and the original stop;
* `exec_be_keep_r` cuts the loss rather than erasing it, and takes NO buffer.

Every test here was watched RED — the mutation table is in `docs/SOS_FADE_BUILD_NOTES.md`.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from strategies.python.mpc_sos_fade.config import SosFadeConfig
from strategies.python.mpc_sos_fade.execution import Execution, _Pending

from .test_execution_ticks import Dec, Sig as _Sig


class Sig(_Sig):
    """The shared double plus the two structure-trail fields `_advance_stage` reads.

    ⚠ Added HERE rather than to the shared double. Every other suite drives `_advance_stage` the
    long way round and gets these from a real Signals; widening the shared stub would hand those
    suites a fixture more capable than the object they are pretending to be, which is how a test
    ends up describing a system nobody has.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.last_conf_high = None
        self.last_conf_low = None

# A long at 99.5 risking 0.50. The first rung sits 1.00 away = 2.0R, deliberately BEYOND every
# excursion below, so nothing here can be explained by a rung touch.
ENTRY, STOP, TP1, TP2 = 99.5, 99.0, 100.5, 101.0
RISK = ENTRY - STOP


def _long_in(ex, entry=ENTRY, sl=STOP, tp1=TP1, tp2=TP2, qty=100.0):
    ex._pend_long = _Pending(dir=1, edge=entry, qty=qty, sl=sl, tp1=tp1, tp2=tp2, sos_bar=1)
    assert ex._try_entry_fill(Sig(o=100.0, h=101.0, l=99.2), Dec()) is True


def _short_in(ex, entry=100.5, sl=101.0, tp1=99.5, tp2=99.0, qty=100.0):
    ex._pend_short = _Pending(dir=-1, edge=entry, qty=qty, sl=sl, tp1=tp1, tp2=tp2, sos_bar=1)
    assert ex._try_entry_fill(Sig(o=100.0, h=100.8, l=99.0), Dec()) is True


def _run_to(ex, high):
    """One bar whose high reaches `high` and which touches no rung."""
    ex._advance_stage(Sig(o=ENTRY, h=high, l=ENTRY, c=ENTRY))


# ── it ships off ────────────────────────────────────────────────────────────────

def test_it_ships_off_so_no_deployed_bot_moves():
    """A default that armed would change what the live bot trades the moment this landed, with no
    promote and no restart."""
    cfg = SosFadeConfig()
    assert cfg.exec_be_arm_r == -1.0
    assert cfg.exec_be_keep_r == 0.0
    ex = Execution(cfg, initial_capital=10_000.0)
    _long_in(ex)
    _run_to(ex, ENTRY + 0.95 * RISK)      # 0.95R in profit, no rung touched
    assert ex._exc_be_armed is False
    assert ex._current_stop() == pytest.approx(STOP)


# ── the 2020-11-04 case, at test scale ──────────────────────────────────────────

def test_a_trade_up_more_than_1R_with_no_rung_touched_is_still_unprotected_when_off():
    """The defect itself. Nothing here is a claim about the fix — it is what shipping today does."""
    ex = Execution(SosFadeConfig(), initial_capital=10_000.0)
    _long_in(ex)
    _run_to(ex, ENTRY + 1.016 * RISK)     # exactly the 2020-11-04 excursion
    assert ex._stage == 0                 # the nearest rung is 2.0R away and was never reached
    assert ex._current_stop() == pytest.approx(STOP)


def test_the_same_trade_is_protected_once_the_excursion_arm_is_on():
    ex = Execution(SosFadeConfig(exec_be_arm_r=0.75), initial_capital=10_000.0)
    _long_in(ex)
    _run_to(ex, ENTRY + 1.016 * RISK)
    assert ex._stage == 0                 # still no rung touched — excursion is the only trigger
    assert ex._exc_be_armed is True
    assert ex._current_stop() > ENTRY     # above the entry: this trade can no longer lose


# ── the trigger itself ──────────────────────────────────────────────────────────

def test_short_of_the_trigger_nothing_arms():
    ex = Execution(SosFadeConfig(exec_be_arm_r=0.75), initial_capital=10_000.0)
    _long_in(ex)
    _run_to(ex, ENTRY + 0.74 * RISK)
    assert ex._exc_be_armed is False
    assert ex._current_stop() == pytest.approx(STOP)


def test_it_arms_exactly_at_the_trigger_not_a_tick_past_it():
    ex = Execution(SosFadeConfig(exec_be_arm_r=0.75), initial_capital=10_000.0)
    _long_in(ex)
    _run_to(ex, ENTRY + 0.75 * RISK)
    assert ex._exc_be_armed is True


def test_it_latches_and_a_later_bar_cannot_un_arm_it():
    """`_max_fav` is RESTORED state, and a stop that can un-ratchet is a trade that can lose after
    it was protected."""
    ex = Execution(SosFadeConfig(exec_be_arm_r=0.75), initial_capital=10_000.0)
    _long_in(ex)
    _run_to(ex, ENTRY + 1.20 * RISK)
    assert ex._exc_be_armed is True
    protected = ex._current_stop()
    ex._max_fav = ENTRY                                   # as a blank restore would leave it
    ex._advance_stage(Sig(o=ENTRY, h=ENTRY, l=ENTRY, c=ENTRY))
    assert ex._exc_be_armed is True
    assert ex._current_stop() == pytest.approx(protected)


def test_the_trigger_is_measured_off_the_FROZEN_entry_stop():
    """Reading the MANAGED stop would shrink the trigger as the stop ratchets.

    ⚠ The reclaim's ancestor of this cannot be tested for it — that one only ever runs with its
    latch clear and the stop therefore still frozen, so both readings agree and its own comment
    says so. This one shares its trade with the rung ladder, so once a rung has staged the stop the
    two readings come apart, and the numbers below are chosen so they DISAGREE rather than merely
    differ: the trade runs 1.00 of price on a frozen risk of 0.50, so 2.0R — but measured against
    the staged stop 0.30 above the entry it reads as 3.33R. A trigger at 3.0R must therefore stay
    unarmed, and does not if the managed stop is read.
    """
    ex = Execution(SosFadeConfig(exec_be_arm_r=3.0), initial_capital=10_000.0)
    _long_in(ex)
    ex._advance_stage(Sig(o=ENTRY, h=TP1, l=ENTRY, c=ENTRY))   # rung at 2.0R touched
    assert ex._stage >= 1 and ex._current_stop() == pytest.approx(ENTRY + 0.30)
    assert ex._exc_be_armed is False, "2R of the FROZEN risk must not arm a 3R trigger"


# ── it can only tighten ─────────────────────────────────────────────────────────

def test_the_armed_stop_lands_strictly_between_the_entry_and_the_original_stop():
    for keep in (0.0, 0.25, 0.5, 0.9):
        ex = Execution(SosFadeConfig(exec_be_arm_r=0.75, exec_be_keep_r=keep),
                       initial_capital=10_000.0)
        _long_in(ex)
        _run_to(ex, ENTRY + 1.20 * RISK)
        stop = ex._current_stop()
        assert stop > STOP, f"keep={keep} loosened the stop"
        assert stop <= ENTRY + 1e-9 or keep == 0.0, f"keep={keep} went past the entry"


def test_a_touched_rung_outranks_it():
    """Every branch above this one is a stop a rung has already staged, and each is at least as
    tight. If this one could win, a trade that reached its target would be protected LESS."""
    ex = Execution(SosFadeConfig(exec_be_arm_r=0.75, exec_be_keep_r=0.9),
                   initial_capital=10_000.0)
    _long_in(ex)
    ex._advance_stage(Sig(o=ENTRY, h=TP1, l=ENTRY, c=ENTRY))   # the rung IS touched
    assert ex._stage >= 1
    assert ex._current_stop() > ENTRY, "a staged breakeven must not be replaced by a 0.9R stop"


# ── how far it moves ────────────────────────────────────────────────────────────

def test_keep_zero_is_breakeven_plus_the_usual_cushion():
    cfg = SosFadeConfig(exec_be_arm_r=0.75)
    ex = Execution(cfg, initial_capital=10_000.0)
    _long_in(ex)
    _run_to(ex, ENTRY + 1.20 * RISK)
    assert ex._current_stop() == pytest.approx(ENTRY + cfg.exec_be_buf_tk * cfg.mintick)


def test_keep_half_leaves_half_the_entry_risk_in_the_market():
    ex = Execution(SosFadeConfig(exec_be_arm_r=0.75, exec_be_keep_r=0.5),
                   initial_capital=10_000.0)
    _long_in(ex)
    _run_to(ex, ENTRY + 1.20 * RISK)
    assert ex._current_stop() == pytest.approx(ENTRY - 0.5 * RISK)


def test_a_partial_move_takes_NO_buffer():
    """The cushion exists to clear the ENTRY price. Adding it to a partial move would make the
    risk left in the market a different number from the one configured."""
    cfg = SosFadeConfig(exec_be_arm_r=0.75, exec_be_keep_r=0.25, exec_be_buf_tk=500.0)
    ex = Execution(cfg, initial_capital=10_000.0)
    _long_in(ex)
    _run_to(ex, ENTRY + 1.20 * RISK)
    assert ex._current_stop() == pytest.approx(ENTRY - 0.25 * RISK)


# ── the mirror ──────────────────────────────────────────────────────────────────

def test_a_short_arms_on_a_move_DOWN_and_its_kept_stop_sits_above_the_entry():
    ex = Execution(SosFadeConfig(exec_be_arm_r=0.75, exec_be_keep_r=0.5),
                   initial_capital=10_000.0)
    _short_in(ex)
    entry, sl = 100.5, 101.0
    risk = sl - entry
    ex._advance_stage(Sig(o=entry, h=entry, l=entry - 1.20 * risk, c=entry))
    assert ex._exc_be_armed is True
    assert ex._current_stop() == pytest.approx(entry + 0.5 * risk)
    assert ex._current_stop() < sl
