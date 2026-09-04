"""Tests for the BOS order layer — the entry ladder, the stop models, the TP tiers, TP3.

Weighted toward the seams where this fork DIFFERS from the A+ bot it subclasses, because that
is where an inherited default or an un-overridden method goes wrong silently: the config pins,
the third TP rung, the live divergence kill, and the ATR-once-per-bar guard.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[4]
for _p in (str(_ROOT), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bos.bos import BosLeg, BosState  # noqa: E402
from bos.config import BosConfig  # noqa: E402
from bos.execution import BosExecution  # noqa: E402
from sos_fade.config import SosFadeConfig  # noqa: E402


def levels(ext: float, org: float) -> dict:
    return {r: ext + (org - ext) * r
            for r in (0.0, 0.118, 0.236, 0.382, 0.5, 0.618, 0.702, 0.786, 0.886, 1.0)}


def execution(**cfg):
    return BosExecution(BosConfig(**cfg), initial_capital=100_000.0)


# ── the config pins ─────────────────────────────────────────────────────────────
def test_the_pins_that_would_move_trades_if_inherited():
    """Three parent defaults this fork's Pine does not have, and one it cannot run at all.

    `exec_fib_nearest` and the two other entry-model rules landed in the A+ on 2026-08-02 and
    price a gap at a DIFFERENT level from Method 3 — with no `execFibNearest` input in
    `bos_strategy.pine`, an inherited True would rest every gap entry somewhere the Pine
    never chose, and the export has no column to catch it with.

    `exec_secondary` is the loud one: it defaulted ON in the parent on 2026-08-07 and needs a
    second bar stream, which `backtest.optimizer.run_sweep` cannot supply — so an inherited
    True would refuse every BOS sweep rather than merely mis-price one.
    """
    parent, cfg = SosFadeConfig(), BosConfig()
    assert parent.exec_fib_nearest is True and cfg.exec_fib_nearest is False
    assert parent.exec_deep_fib is False and cfg.exec_deep_fib is True
    # ⚠ 2026-08-21: the parent reverted this to False (Aaron — every optional entry path ships
    # OFF), so the inheritance hazard this line guarded is dormant rather than gone. The fork's own
    # False is asserted first because that is what protects this bot; the parent's value is pinned
    # after it so a future flip back to True surfaces HERE rather than as a refused BOS sweep.
    assert cfg.exec_secondary is False
    # 🔴 2026-08-27: the parent ships the re-entry ON again (as the reclaim), so this fork's pin is
    # LOAD-BEARING once more — `run_sweep` still cannot supply a second bar stream, and an inherited
    # True would break every sweep rather than mis-price a trade. The pin above is what stops it.
    assert parent.exec_secondary is True, (
        "the parent's default moved again — re-answer this in the same commit and say whether this "
        "fork's pin is load-bearing or redundant")
    assert parent.exec_time_stop_mode != "Off" and cfg.exec_time_stop_mode == "Off"
    assert parent.exec_runner_trail != cfg.exec_runner_trail


def test_the_subclass_still_runs_the_parents_own_validation():
    """A subclass that defines `__post_init__` REPLACES the parent's, so omitting the `super()`
    call would silently retire the two checks this fork still inherits the fields for."""
    with pytest.raises(ValueError, match="exec_time_stop_mode"):
        BosConfig(exec_time_stop_mode="sometimes")


def test_a_dropdown_value_the_pine_cannot_produce_is_refused():
    """A silent fall-through would replay a whole backtest against a stop nobody chose and
    report it as theirs — and a value outside the Pine's options cannot be exported, so
    `compare_bos.py` could never check the run either."""
    with pytest.raises(ValueError, match="bos_sl_model"):
        BosConfig(bos_sl_model="atr")
    with pytest.raises(ValueError, match="bos_entry_fib"):
        BosConfig(bos_entry_fib="0.65")


# ── the stop models ─────────────────────────────────────────────────────────────
def _sig(**kw):
    base = dict(index=10, time_ms=0, open=100.0, high=100.0, low=100.0, close=100.0,
                last_conf_high=112.0, last_conf_low=96.0,
                bull_div_active=False, bear_div_active=False,
                veto_rsi_ob=False, veto_rsi_os=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_every_stop_model_prices_off_the_thing_its_name_says():
    lv = levels(110.0, 100.0)          # a long leg 100 -> 110
    for model, expected in (("Fib 1.0 (leg origin)", 100.0),
                            ("Fib 0.886", 101.14),
                            ("Last confirmed swing", 96.0),
                            ("Broken swing level", 110.0)):
        ex = execution(bos_sl_model=model)
        got = ex._bos_stop(_sig(), 102.0, lv, broken=110.0, bull=True)
        assert got == pytest.approx(expected, abs=1e-9), model


def test_the_broken_swing_stop_lands_ABOVE_a_longs_entry_and_that_is_why_it_barely_trades():
    """Pine's own tooltip says so. It is kept only because the Pine has it — pinning the
    behaviour stops someone "fixing" it into a stop that silently flips side."""
    ex = execution(bos_sl_model="Broken swing level")
    stop = ex._bos_stop(_sig(), 102.0, levels(110.0, 100.0), broken=110.0, bull=True)
    assert stop > 102.0, "a stop above the entry — dist is negative, so the order is refused"
    assert ex._build_pending(_sig(), BosLeg(on=True, high=110.0, low=100.0, bar=1),
                             levels(110.0, 100.0), 102.0, bull=True) is None


def test_the_atr_stop_does_not_scale_with_the_leg_and_refuses_during_the_warmup():
    """The whole argument for the 2026-08-07 default change: a fib stop is a FRACTION of the
    leg, so a small leg produces a small stop mechanically. An ATR stop does not care.

    The warmup half matters as much — Pine's arithmetic against a `na` ATR yields `na`, so the
    first 13 bars refuse rather than taking an unpriced stop.
    """
    ex = execution(bos_sl_model="ATR", bos_sl_atr=1.3)
    assert ex._bos_stop(_sig(), 100.0, levels(110.0, 100.0), 110.0, bull=True) is None

    ex._atr = 2.0
    assert ex._bos_stop(_sig(), 100.0, levels(110.0, 100.0), 110.0, bull=True) == pytest.approx(97.4)
    # a leg ten times smaller — the fib stop would shrink with it, the ATR stop does not
    assert ex._bos_stop(_sig(), 100.0, levels(101.0, 100.0), 101.0, bull=True) == pytest.approx(97.4)


def test_the_stop_buffer_always_pushes_the_stop_FURTHER_from_the_entry():
    ex = execution(bos_sl_model="Fib 1.0 (leg origin)", exec_sl_buf_tk=50.0)  # 50 ticks = $0.50
    assert ex._bos_stop(_sig(), 102.0, levels(110.0, 100.0), 110.0, bull=True) == pytest.approx(99.5)
    assert ex._bos_stop(_sig(), 98.0, levels(90.0, 100.0), 90.0, bull=False) == pytest.approx(100.5)


# ── entry depth -> the TP ladder ────────────────────────────────────────────────
def test_the_tier_is_derived_from_where_the_limit_landed_never_chosen():
    lv = levels(110.0, 100.0)
    assert BosExecution._tier(lv[0.618], lv, bull=True) == 2      # at 0.618 -> DEEP
    assert BosExecution._tier(104.5, lv, bull=True) == 1          # between 0.5 and 0.618
    assert BosExecution._tier(106.0, lv, bull=True) == 0          # shallower than 0.5
    assert BosExecution._tier(None, lv, bull=True) == 1


def test_tp1_is_never_a_level_the_entry_already_rests_at():
    """The rule the whole tier system exists for: a target the entry already sits at fills on
    the trade's OWN fill bar, stages the stop to breakeven, and the trade dies a scratch."""
    lv = levels(110.0, 100.0)
    ex = execution()
    leg = BosLeg(on=True, high=110.0, low=100.0, bar=1)
    for tier, entry in ((2, lv[0.618]), (1, lv[0.5]), (0, lv[0.382])):
        tp1, tp2, tp3 = ex._targets(tier, lv, leg, bull=True)
        assert tp1 > entry, f"tier {tier}: TP1 must be beyond the entry"
        assert tp2 > tp1 and tp3 > tp2, f"tier {tier}: the ladder must be ordered"


def test_tp3_is_the_leg_extreme_and_the_measured_move_replaces_it_only_when_further():
    lv = levels(110.0, 100.0)
    leg = BosLeg(on=True, high=110.0, low=100.0, bar=1)
    assert execution()._targets(2, lv, leg, bull=True)[2] == pytest.approx(110.0)

    ex = execution(bos_tp3_measured=True)
    # the break leg 100 -> 110 projected forward from 110 = 120, beyond the fib extreme
    assert ex._targets(2, lv, leg, bull=True)[2] == pytest.approx(120.0)

    # A projection landing BEHIND TP2 is ignored rather than pulling the ladder in. The leg
    # and the ladder can genuinely disagree here — under the "Expansion leg" anchor the ladder
    # is the live fib while the measured move is always built from the BREAK leg's own span.
    small = BosLeg(on=True, high=105.0, low=104.9, bar=1)
    assert ex._targets(2, lv, small, bull=True)[2] == pytest.approx(110.0)


# ── TP3, the rung the A+ ladder does not have ───────────────────────────────────
def _open_a_trade(ex, qty=10.0, entry=100.0):
    ex._pos_dir = 1
    ex._qty = qty
    ex._filled_qty = 0.0
    ex._entry = entry
    ex._tp1, ex._tp2, ex._tp3 = 104.0, 106.0, 110.0
    ex._sl = 98.0
    ex._stage = 0


def test_the_shipped_ladder_puts_the_whole_position_on_tp3_and_leaves_no_runner():
    """0/0/100 measured best on every axis on 2026-08-07 (+137.7R vs +90.8R for 30/30/20)."""
    ex = execution()
    _open_a_trade(ex)
    brackets = ex._remaining_brackets()
    assert [b[0] for b in brackets] == ["L-TP3"]
    assert brackets[0][1] == pytest.approx(110.0)
    assert brackets[0][2] == pytest.approx(10.0)


def test_a_rung_sized_zero_is_skipped_never_placed():
    """In the Pine `strategy.exit(qty_percent = 0)` falls back to closing the WHOLE position at
    that limit — the exact opposite of "bank nothing here"."""
    ex = execution(exec_tp1_pct=0.0, exec_tp2_pct=30.0, exec_tp3_pct=70.0)
    _open_a_trade(ex)
    assert [b[0] for b in ex._remaining_brackets()] == ["L-TP2", "L-TP3"]


def test_whatever_is_left_under_100_becomes_the_runner_again():
    ex = execution(exec_tp1_pct=30.0, exec_tp2_pct=30.0, exec_tp3_pct=20.0)
    _open_a_trade(ex)
    ids = [b[0] for b in ex._remaining_brackets()]
    assert ids == ["L-TP1", "L-TP2", "L-TP3", "L-RUN"]
    assert ex._remaining_brackets()[-1][2] == pytest.approx(2.0)   # the last 20%


def test_a_partially_filled_ladder_offers_only_what_is_left():
    ex = execution(exec_tp1_pct=30.0, exec_tp2_pct=30.0, exec_tp3_pct=40.0)
    _open_a_trade(ex)
    ex._filled_qty = 3.0                       # TP1 banked
    ids = [b[0] for b in ex._remaining_brackets()]
    assert ids == ["L-TP2", "L-TP3"]
    assert sum(b[2] for b in ex._remaining_brackets()) == pytest.approx(7.0)


def test_a_tp3_that_was_never_priced_does_not_swallow_the_position():
    """`_tp3` is None on any trade opened before this fork set it. A `None` target would make
    the bracket unfillable and, worse, silently hold the qty out of the runner."""
    ex = execution()
    _open_a_trade(ex)
    ex._tp3 = None
    brackets = ex._remaining_brackets()
    assert [b[0] for b in brackets] == ["L-RUN"]
    assert brackets[0][2] == pytest.approx(10.0), "the whole position must still be covered"


# ── the divergence KILL ─────────────────────────────────────────────────────────
def test_the_veto_is_LIVE_and_has_no_post_sos_exemption():
    """Item 2 of the fork's three differences. The A+ veto is judged at the SOS and carries an
    exemption, so a divergence that armed the fade cannot then refuse it; a continuation setup
    has the opposite relationship to divergence — an opposing one is the fakeout signature."""
    ex = execution()
    assert ex._veto(_sig(bear_div_active=True)) == (True, False)
    assert ex._veto(_sig(veto_rsi_ob=True)) == (True, False)
    assert ex._veto(_sig(bull_div_active=True)) == (False, True)


def test_the_veto_reads_show_div_alone_not_the_a_plus_combination():
    """Pine 3785 gates on `showDiv`. `Signals.veto_on` is `showDiv and divVeto` — the A+'s
    combination — and using it here would silently disable the kill for anyone who had turned
    the A+ veto off."""
    assert execution(show_div=False)._veto(_sig(bear_div_active=True)) == (False, False)
    assert execution(div_veto=False)._veto(_sig(bear_div_active=True)) == (True, False)


# ── the ATR, computed once ──────────────────────────────────────────────────────
def test_priming_the_atr_twice_on_one_bar_advances_it_once():
    """Two Wilder steps on one bar would advance the average at double rate and silently
    produce a different ATR from the Pine's on every bar after the first — with no error and
    no obviously wrong number, just a stop model quietly off."""
    ex = execution()
    bars = [_sig(index=i, high=101.0 + i, low=99.0 + i, close=100.0 + i) for i in range(30)]
    for b in bars:
        ex.prime_atr(b)
        ex._update_atr(b)          # what the parent's step() does on the same bar
    once = ex._atr

    ex2 = execution()
    for b in bars:
        ex2.prime_atr(b)
    assert once == pytest.approx(ex2._atr)


# ── the moving stop ─────────────────────────────────────────────────────────────
def test_the_moving_stop_is_dead_on_the_fill_bar():
    """`_max_fav` is seeded from the ENTRY PRICE and the fill bar's favourable extreme is where
    price was on its way INTO the resting limit — before the trade existed. Trailing off it
    would stage a stop the trade never earned."""
    ex = execution(bos_move_stop="$ of price", bos_move_stop_val=2.0)
    _open_a_trade(ex)
    ex._entry_index, ex._max_fav = 10, 105.0
    ex._bar_index = 10
    assert ex._move_stop() is None
    ex._bar_index = 11
    assert ex._move_stop() == pytest.approx(103.0)


def test_the_moving_stop_can_only_ever_tighten():
    """It composes with the staged ladder rather than replacing it: breakeven and the TP2 floor
    are never loosened by it."""
    ex = execution(bos_move_stop="$ of price", bos_move_stop_val=20.0)
    _open_a_trade(ex)
    ex._entry_index, ex._bar_index, ex._max_fav = 10, 11, 105.0
    ex._stage = 1                                   # staged to breakeven
    assert ex._move_stop() == pytest.approx(85.0)   # far looser than breakeven
    assert ex._current_stop() > 100.0, "the loose moving stop must not pull breakeven down"


# ── the per-bar exit stage ───────────────────────────────────────────────────────
def test_the_exit_stage_is_a_snapshot_and_the_three_bar_lists_stay_aligned():
    """🔴 `compare_bos.py` used to read `strat.execution._stage` INSIDE its compare loop, which
    runs after the whole replay — so every bar was diffed against the run's FINAL stage. The
    run ends flat, so that constant was 0, and the column compared nothing at all until a Pine
    bar happened to report 1 or 2. The stage is now sampled per bar into `exit_stages`.

    ⚠ This test pins the two properties a future edit can break silently — that the value is a
    SNAPSHOT (a later close cannot rewrite it) and that the three parallel lists stay the same
    length, which is what fails if someone appends in one place and forgets another. It is NOT
    the evidence that the fix works: that is the parity run, which went from RED at bar 1704 to
    GREEN over 6,200 bars.
    """
    from bos import BosStrategy

    s = BosStrategy(BosConfig(bos_vwap_req="Off"))
    s.execution._pos_dir, s.execution._stage = -1, 1
    s.exit_stages.append(s._exit_stage())
    s.execution._stage = 2
    s.exit_stages.append(s._exit_stage())
    s.execution._pos_dir, s.execution._stage = 0, 0           # the trade closes later
    s.exit_stages.append(s._exit_stage())

    assert s.exit_stages == [1, 2, 0], "a later bar must not rewrite an earlier bar's stage"


def test_a_flat_bar_reports_stage_zero_rather_than_the_last_trades_stage():
    """Pine plots `px_stage` as `na` off-position and the harness reads a flat bar as 0, so the
    Python must zero it on `_pos_dir == 0` — carrying the last trade's stage forward would
    diverge on every flat bar after a runner."""
    from bos import BosStrategy

    s = BosStrategy(BosConfig(bos_vwap_req="Off"))
    s.execution._pos_dir, s.execution._stage = 1, 2
    assert s._exit_stage() == 2
    s.execution._pos_dir = 0
    assert s._exit_stage() == 0
