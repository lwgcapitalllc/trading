"""Level memory — rest a limit again at a level a PRIMARY already traded, after its setup died.

WHY THIS EXISTS. Aaron, 2026-09-22, off a live trade: the Monday short filled at the gap edge,
closed at a profit stop for nothing, and ~20 hours later price came all the way back to that
price and sold off with the bot holding nothing. Two causes from its own decision record — the
setup died when structure re-broke (and the published entry price dies with it), and no shift of
structure printed that evening, so nothing armed. Run 42 measured the population.

WATCHED RED against HEAD, and what each one failed with:
  - every behaviour test: `ImportError: cannot import name 'LevelMemory'` — the module did not
    exist, and neither did the config fields the fixture builds.
  - the refusal tests: `TypeError: unexpected keyword argument 'exec_lvl_memory'`.
  - `test_default_is_off`: mutation-proved instead, because it cannot fail at construction —
    flip `exec_lvl_memory` to True in config.py and it goes red. It is the test that protects
    every stored figure in this package.
  - `test_away_gate_is_not_vacuous`: mutation-proved as well — drop the away latch (arm on the
    first bar) and it goes red. 🔴 This is the defect the AUDIT shipped with: a breakeven or
    profit stop exits AT the entry price, so "price came back to the level" is trivially true
    minutes later, and a fourteen-minute window still reported 82 returns and a spurious -38R.
"""

import pytest

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.dual_clock import _merge_arm
from strategies.python.sos_fade.level_memory import SRC, LevelMemory
from strategies.python.sos_fade.secondary import SecArm

# One remembered SHORT: entered at 4369.93 with a 20.00 stop distance, closed at t=0.
# The numbers are Aaron's own trade, so a reader can line the test up against the chart.
SHORT = (4369.93, 20.00, 0)
HOUR = 3_600_000


def _mem(**kw):
    cfg = SosFadeConfig(exec_lvl_memory=True, **kw)
    m = LevelMemory(cfg)
    m.observe(None, SHORT)
    return m


def _step(m, *, hours, high, low, flat=True, resting=False):
    return m.update(now_ms=int(hours * HOUR), high=high, low=low, flat=flat,
                    primary_resting_l=False, primary_resting_s=resting)


def test_default_is_off():
    """Nothing arms while the switch is off — the guarantee every stored run rests on."""
    m = LevelMemory(SosFadeConfig())
    m.observe(None, SHORT)
    arm = _step(m, hours=20, high=4369.93, low=4300.0)
    assert not arm.s_armed and not arm.l_armed


def test_away_gate_is_not_vacuous():
    """A return BEFORE price has travelled away is not a return, and must not arm.

    The trade closed at its own entry price, so the level is touched immediately. Without the
    away latch this arms on the first bar, which is the audit's original defect.
    """
    m = _mem()
    arm = _step(m, hours=0.25, high=4369.93, low=4365.0)   # 0.25R away at most
    assert not arm.s_armed


def test_the_limit_rests_as_soon_as_price_has_travelled_away():
    """⚠ ARMED means *an order is resting at the level*, NOT *price is back at it*.

    The bar that carries price 3R away is the bar the limit goes on the book, and it then waits
    however long it waits — the fill is the execution's job, on the bar price returns. A test
    that expected arming only on the touch would be describing a market order.
    """
    m = _mem()
    assert not _step(m, hours=0.25, high=4369.93, low=4365.0).s_armed
    arm = _step(m, hours=1, high=4360.0, low=4310.0)               # 3R away
    assert arm.s_armed and arm.s_src == SRC
    assert arm.s_edge == pytest.approx(4369.93)


def test_stop_is_a_fraction_of_the_original_trades_own_risk():
    """The measured variable: 0.5 halves the 20.00 the primary was sized against."""
    m = _mem(exec_lvl_stop_frac=0.5)
    _step(m, hours=1, high=4360.0, low=4310.0)
    arm = _step(m, hours=20, high=4369.93, low=4350.0)
    assert arm.s_sl == pytest.approx(4369.93 + 10.0)


def test_full_width_stop_is_reachable_and_is_the_other_measured_arm():
    m = _mem(exec_lvl_stop_frac=1.0)
    _step(m, hours=1, high=4360.0, low=4310.0)
    arm = _step(m, hours=20, high=4369.93, low=4350.0)
    assert arm.s_sl == pytest.approx(4369.93 + 20.0)


def test_target_is_priced_off_the_narrowed_risk():
    """2R of the NARROWED stop, not of the primary's — the ladder Run 42 graded."""
    m = _mem(exec_lvl_stop_frac=0.5, exec_lvl_tp_r=2.0)
    _step(m, hours=1, high=4360.0, low=4310.0)
    arm = _step(m, hours=20, high=4369.93, low=4350.0)
    assert arm.s_tp1 == pytest.approx(4369.93 - 20.0)


def test_memory_expires():
    m = _mem(exec_lvl_days=5.0)
    _step(m, hours=1, high=4360.0, low=4310.0)
    assert not _step(m, hours=24 * 5 + 1, high=4369.93, low=4350.0).s_armed


def test_quiet_gate_refuses_while_a_primary_limit_rests():
    """The 44 returns with a setup already armed are worth -0.02R, and there is ONE slot."""
    m = _mem(exec_lvl_require_quiet=True)
    _step(m, hours=1, high=4360.0, low=4310.0)
    assert not _step(m, hours=20, high=4369.93, low=4350.0, resting=True).s_armed
    assert _step(m, hours=20, high=4369.93, low=4350.0, resting=False).s_armed


def test_quiet_gate_can_be_switched_off():
    m = _mem(exec_lvl_require_quiet=False)
    _step(m, hours=1, high=4360.0, low=4310.0)
    assert _step(m, hours=20, high=4369.93, low=4350.0, resting=True).s_armed


def test_nothing_arms_while_a_position_is_open():
    m = _mem()
    _step(m, hours=1, high=4360.0, low=4310.0)
    assert not _step(m, hours=20, high=4369.93, low=4350.0, flat=False).s_armed


def test_one_order_per_remembered_level():
    m = _mem()
    _step(m, hours=1, high=4360.0, low=4310.0)
    assert _step(m, hours=20, high=4369.93, low=4350.0).s_armed
    m.mark_traded(-1)
    assert not _step(m, hours=21, high=4369.93, low=4350.0).s_armed


def test_a_newer_primary_replaces_the_memory():
    """One level per side. With one position slot only one of them can ever trade, so a queue
    would describe a book the account cannot hold — see the class docstring."""
    m = _mem()
    _step(m, hours=1, high=4360.0, low=4310.0)          # the first level is away-latched
    m.observe(None, (4400.0, 10.0, 2 * HOUR))
    arm = _step(m, hours=20, high=4369.93, low=4350.0)
    assert m.watching() == (None, 4400.0)
    assert arm.s_edge == pytest.approx(4400.0)


def test_the_replacement_starts_its_own_away_latch():
    """The new level inherits nothing — its own 1R, measured from its own price."""
    m = _mem()
    _step(m, hours=1, high=4360.0, low=4310.0)          # the OLD level is away-latched
    m.observe(None, (4400.0, 10.0, 2 * HOUR))
    assert not _step(m, hours=3, high=4398.0, low=4396.0).s_armed    # only 0.4R away
    assert _step(m, hours=4, high=4398.0, low=4389.0).s_armed        # 1.1R away


def test_a_record_with_no_stop_distance_is_refused_not_stored():
    """Rule 1: *no usable record* must not become *a level at no risk*."""
    m = LevelMemory(SosFadeConfig(exec_lvl_memory=True))
    m.observe(None, (4369.93, 0.0, 0))
    assert m.watching() == (None, None)


def test_the_reentry_wins_a_contested_side():
    """One slot, so two armed sources are two claims on it. The shipped feature wins."""
    sec = SecArm(s_armed=True, s_edge=1.0, s_sl=2.0, s_src="gap")
    lvl = SecArm(s_armed=True, s_edge=9.0, s_sl=9.9, s_src=SRC)
    assert _merge_arm(sec, lvl).s_src == "gap"


def test_the_level_memory_takes_an_uncontested_side():
    lvl = SecArm(l_armed=True, l_edge=9.0, l_sl=8.0, l_src=SRC)
    merged = _merge_arm(SecArm(), lvl)
    assert merged.l_armed and merged.l_src == SRC


@pytest.mark.parametrize("kw", [
    {"exec_lvl_days": 0.0},
    {"exec_lvl_away_r": 0.0},
    {"exec_lvl_stop_frac": 1.5},
    {"exec_lvl_stop_frac": 0.0},
    {"exec_lvl_tp_r": 0.0},
    {"exec_lvl_tp1_pct": 0.0},
    {"exec_lvl_risk_pct": 0.0},
    {"exec_lvl_max_hold_hrs": 0.0},
    {"exec_lvl_be_r": 0.0},
    {"exec_lvl_be_keep_r": 1.0},
])
def test_refuses_a_setting_that_reads_as_on_and_is_not(kw):
    with pytest.raises(ValueError):
        SosFadeConfig(exec_lvl_memory=True, **kw)


def test_the_same_settings_are_accepted_while_the_switch_is_off():
    """A stored config that never turns the feature on may not be refused by a field it does
    not use — otherwise adding this breaks every saved run form."""
    SosFadeConfig(exec_lvl_days=0.0, exec_lvl_away_r=0.0, exec_lvl_stop_frac=0.0)


def test_a_spent_level_does_not_come_back():
    """🔴 THE DEFECT THE FIRST REPLAY FOUND, and it is the reason this file has a second half.

    The execution keeps its last-closed-primary record standing for days and this class POLLS it.
    Before the seen-marker, a level retired by a fill dropped to None and was rebuilt from the
    same record on the next bar — for ever. MEASURED: 141 extra trades where Run 42 found 39
    returns at all, and the replayed book fell 22R.
    """
    m = _mem()
    _step(m, hours=1, high=4360.0, low=4310.0)
    assert _step(m, hours=20, high=4369.93, low=4350.0).s_armed
    m.mark_traded(-1)
    # ⚠ The bars below carry price a full 1R away AGAIN on purpose. A resurrected record starts
    # with its away latch cleared, so a test whose bars could not re-latch it would pass against
    # the bug — which is exactly what the first version of this test did.
    for h in (21, 22, 23):
        m.observe(None, SHORT)                      # the execution still holds the same record
        assert not _step(m, hours=h, high=4369.93, low=4340.0).s_armed


def test_an_expired_level_does_not_come_back():
    """Expiry drops the record too — and re-taking it is harmless only by accident.

    ⚠ **This one does NOT catch the missing seen-marker and is not claimed to.** A resurrected
    expired record carries its old close time, so it expires again on the same bar. It is here to
    pin that behaviour, because a later change to how expiry is measured could make the
    resurrection bite here as well.
    """
    m = _mem(exec_lvl_days=5.0)
    _step(m, hours=1, high=4360.0, low=4310.0)
    assert not _step(m, hours=24 * 5 + 1, high=4369.93, low=4340.0).s_armed
    m.observe(None, SHORT)
    assert not _step(m, hours=24 * 5 + 2, high=4369.93, low=4340.0).s_armed


def test_a_refused_record_is_not_re_examined_every_bar():
    """A zero-risk record is marked seen, so the refusal costs one comparison and not a poll."""
    m = LevelMemory(SosFadeConfig(exec_lvl_memory=True))
    m.observe(None, (4369.93, 0.0, 0))
    m.observe(None, (4369.93, 0.0, 0))
    assert m.watching() == (None, None)
