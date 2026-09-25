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

RUN 45's filter tests were MUTATION-PROVED, 2026-09-23, each mutation applied alone to
level_memory.py and every one went red:
  - gap filter never refuses a dead gap          -> the gap-live test.
  - a level with no gap trades unfiltered        -> wrong-direction, no-gap and tolerance tests.
  - sweep filter reads the opposite side         -> the sweep-side test.
  - shift entry drops the risk cap               -> the wide-risk test.
  - shift window never closes                    -> the window test.
  - shift entry ignores whether a shift printed  -> the tap-then-shift test.
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


# ── Run 45: the three pre-registered confluence filters ─────────────────────────────────────────
#
# The fixtures below carry ONLY the fields the real 15m signal record and the fast structure state
# carry (`fvgs`, `recent_bsl`, `recent_ssl`; `new_bear_sos`, `new_bull_sos`) — rule 13, a double
# that answers something the real thing cannot is describing a system we do not have.

from types import SimpleNamespace  # noqa: E402

from strategies.python.sos_fade.config import SosFadeConfig as _Cfg  # noqa: E402

# A bearish gap above the short's level, the shape the primary took its entry from.
GAP = (4375.0, 4369.0, False, 100)       # (top, bottom, is_bullish, born)


def _sig(fvgs=(), bsl="", ssl=""):
    return SimpleNamespace(fvgs=list(fvgs), recent_bsl=bsl, recent_ssl=ssl)


def _m1(bear=False, bull=False):
    return SimpleNamespace(new_bear_sos=bear, new_bull_sos=bull)


def _cmem(mode, sig=None, **kw):
    m = LevelMemory(_Cfg(exec_lvl_memory=True, exec_lvl_confluence=mode, **kw))
    m.observe(None, SHORT, sig=sig)
    return m


def _cstep(m, *, hours, high, low, sig=None, m1=None, close=None, flat=True):
    return m.update(now_ms=int(hours * HOUR), high=high, low=low, flat=flat,
                    primary_resting_l=False, primary_resting_s=False,
                    sig=sig, m1=m1, close=close)


def test_gap_filter_rests_only_while_the_original_gap_is_live():
    live = _sig([GAP])
    m = _cmem("Gap still open", sig=live)
    assert _cstep(m, hours=1, high=4360.0, low=4310.0, sig=live).s_armed
    gone = _sig([])                                     # closed through, or pushed off the list
    assert not _cstep(m, hours=2, high=4360.0, low=4310.0, sig=gone).s_armed


def test_gap_filter_ignores_a_gap_of_the_wrong_direction():
    """A short's level came from a BEARISH gap; a bullish one at the same price is another thing."""
    wrong = _sig([(4375.0, 4369.0, True, 100)])
    m = _cmem("Gap still open", sig=wrong)
    assert not _cstep(m, hours=1, high=4360.0, low=4310.0, sig=wrong).s_armed


def test_gap_filter_spends_a_level_that_had_no_gap_when_it_was_taken():
    """No gap to watch is not permission to trade unfiltered."""
    m = _cmem("Gap still open", sig=_sig([]))
    later = _sig([GAP])                                 # a gap appearing later is not this level's
    assert not _cstep(m, hours=1, high=4360.0, low=4310.0, sig=later).s_armed


def test_gap_filter_tolerance_is_a_fraction_of_the_original_risk():
    near = _sig([(4375.0, 4371.0, False, 100)])         # 1.07 below the band; 0.1 x 20 = 2.0
    m = _cmem("Gap still open", sig=near)
    assert _cstep(m, hours=1, high=4360.0, low=4310.0, sig=near).s_armed
    far = _sig([(4380.0, 4373.0, False, 100)])          # 3.07 below the band
    m = _cmem("Gap still open", sig=far)
    assert not _cstep(m, hours=1, high=4360.0, low=4310.0, sig=far).s_armed


def test_sweep_filter_reads_the_trades_own_side():
    m = _cmem("Sweep first")
    assert not _cstep(m, hours=1, high=4360.0, low=4310.0, sig=_sig(ssl="Day Low")).s_armed
    assert _cstep(m, hours=2, high=4360.0, low=4310.0, sig=_sig(bsl="Day High")).s_armed


def test_shift_entry_waits_for_the_tap_then_the_shift():
    m = _cmem("Shift confirms")
    _cstep(m, hours=1, high=4360.0, low=4310.0, m1=_m1(), close=4320.0)            # away
    assert not _cstep(m, hours=2, high=4365.0, low=4350.0, m1=_m1(bear=True),
                      close=4355.0).s_armed                                       # no tap yet
    assert not _cstep(m, hours=3, high=4372.0, low=4360.0, m1=_m1(), close=4365.0).s_armed
    arm = _cstep(m, hours=3.1, high=4368.0, low=4358.0, m1=_m1(bear=True), close=4360.0)
    assert arm.s_armed and arm.s_src == SRC
    assert arm.s_edge == pytest.approx(4360.0)          # the confirming bar's close
    assert arm.s_sl == pytest.approx(4372.0)            # the extreme since the tap
    assert arm.s_tp1 == pytest.approx(4360.0 - 2 * 12.0)


def test_shift_entry_window_closes_and_spends_the_level():
    m = _cmem("Shift confirms", exec_lvl_shift_bars=2)
    _cstep(m, hours=1, high=4360.0, low=4310.0, m1=_m1(), close=4320.0)
    for h in (2.0, 2.1, 2.2):                           # tap bar, then two more — window used up
        _cstep(m, hours=h, high=4372.0, low=4360.0, m1=_m1(), close=4365.0)
    assert not _cstep(m, hours=2.3, high=4368.0, low=4358.0, m1=_m1(bear=True),
                      close=4360.0).s_armed


def test_shift_entry_refuses_a_risk_wider_than_the_original_trade():
    m = _cmem("Shift confirms")
    _cstep(m, hours=1, high=4360.0, low=4310.0, m1=_m1(), close=4320.0)
    _cstep(m, hours=2, high=4395.0, low=4365.0, m1=_m1(), close=4390.0)          # tap, runs 25
    assert not _cstep(m, hours=2.1, high=4380.0, low=4360.0, m1=_m1(bear=True),
                      close=4362.0).s_armed                                       # risk 33 > 20


def test_shift_entry_is_a_market_order_and_the_others_are_not():
    from strategies.python.sos_fade.execution import Execution

    assert Execution(_Cfg(exec_lvl_memory=True, exec_lvl_confluence="Shift confirms")
                     )._market_entry(SRC) is True
    assert Execution(_Cfg(exec_lvl_memory=True, exec_lvl_confluence="Gap still open")
                     )._market_entry(SRC) is False


def test_refuses_a_confluence_that_is_not_one():
    with pytest.raises(ValueError):
        _Cfg(exec_lvl_memory=True, exec_lvl_confluence="gap")
