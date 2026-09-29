"""The 1-minute SOS-then-BOS entry (`exec_shift_entry`) — the rules the screen graded, and the
order path it borrows.

WHY THIS EXISTS. Aaron, 2026-09-28, *"can you prove it?"* — the screen
(`backtest/tools/generic_ltf_trigger.py`) found that entering a zone touch only after a 1-minute
SOS and then a BOS made +0.26R a trade net on GBPJPY and +0.19R on GBPUSD. This is that trade
built into the strategy so a real lab run can price it with one position slot and sizing.

WATCHED RED against HEAD: every test failed with `ModuleNotFoundError: shift_entry` or
`TypeError: unexpected keyword argument 'exec_shift_entry'`. The mutations each rule test was
run against are named in its docstring.
"""

from types import SimpleNamespace

import pytest

from strategies.python.sos_fade.config import SosFadeConfig
from strategies.python.sos_fade.dual_clock import FAST_CLOCK_FLAGS, uses_fast_clock
from strategies.python.sos_fade.execution import Decision, Execution, _Pending
from strategies.python.sos_fade.shift_entry import SRC, ShiftCtx, ShiftEntry

MIN = 60_000
# A long setup: 15m 1.0 at 100, 0.0 at 110, tag reported by the 15m bar opening at t=0.
LONG = ShiftCtx(dir=1, sos_ms=-900_000, from_ms=0, stop=100.0, extreme=110.0)


def _m1(sos=False, bos=False, bear_sos=False, bear_bos=False):
    return SimpleNamespace(new_bull_sos=sos, new_bull_bos=bos,
                           new_bear_sos=bear_sos, new_bear_bos=bear_bos)


def _bar(se, minute, *, sos=False, bos=False, high=104.0, low=103.0, close=103.5, flat=True,
         ctx=LONG):
    return se.update((ctx, None), now_ms=minute * MIN, m1=_m1(sos, bos), high=high, low=low,
                     close=close, flat=flat)


def _entry(**kw):
    return ShiftEntry(SosFadeConfig(exec_shift_entry=True, **kw))


def test_default_is_off():
    """The guarantee every stored run rests on. MUTATION: flip the field default -> red."""
    assert SosFadeConfig().exec_shift_entry is False
    assert not uses_fast_clock(SosFadeConfig(exec_secondary=False, exec_scale_in=False))


def test_an_sos_then_a_later_bos_arms_at_market_with_the_frozen_levels():
    se = _entry()
    assert not _bar(se, 16, sos=True).l_armed
    arm = _bar(se, 20, bos=True, close=104.0)
    assert (arm.l_armed, arm.l_edge, arm.l_sl, arm.l_tp1, arm.l_src) == \
        (True, 104.0, 100.0, 110.0, SRC)
    assert arm.l_tp2 > arm.l_tp1          # parked beyond, never staged off


def test_a_bos_on_the_sos_bar_itself_is_not_the_pattern():
    """The screen excluded it, even after an earlier SOS. MUTATION: drop `not sos[d]` from the
    fire test -> red (it went GREEN on a first draft that had no earlier SOS, so proved nothing)."""
    se = _entry()
    _bar(se, 16, sos=True)
    assert not _bar(se, 17, sos=True, bos=True).l_armed
    assert _bar(se, 18, bos=True).l_armed


def test_a_bos_with_no_sos_before_it_does_nothing():
    """MUTATION: fire on any BOS (ignore `sos_seen`) -> red."""
    se = _entry()
    assert not _bar(se, 16, bos=True).l_armed


def test_an_sos_printed_inside_the_tag_bar_counts():
    """The tag is only known at the 15m close, so the ctx arrives late; an SOS already printed
    in that 15m bar (at or after `from_ms`) still counts. MUTATION: `seen_before = False` -> red."""
    se = _entry()
    se.update((None, None), now_ms=5 * MIN, m1=_m1(sos=True), high=104, low=103, close=103.5,
              flat=True)
    assert _bar(se, 16, bos=True).l_armed


def test_an_sos_from_before_the_tag_bar_does_not_count():
    """MUTATION: drop the `ctx.from_ms <=` bound -> red."""
    se = _entry()
    se.update((None, None), now_ms=-5 * MIN, m1=_m1(sos=True), high=104, low=103, close=103.5,
              flat=True)
    assert not _bar(se, 16, bos=True).l_armed


@pytest.mark.parametrize("high,low", [(104.0, 100.0), (110.0, 103.0)])
def test_a_wick_to_the_stop_or_the_extreme_retires_the_setup(high, low):
    """Checked before the signal, and for good. MUTATION: skip the touch test -> red."""
    se = _entry()
    _bar(se, 16, sos=True)
    assert not _bar(se, 17, bos=True, high=high, low=low).l_armed
    assert not _bar(se, 18, bos=True).l_armed


def test_only_the_first_completion_is_ever_the_trade():
    """MUTATION: do not retire on the fire -> red (the second BOS arms again)."""
    se = _entry()
    _bar(se, 16, sos=True)
    assert _bar(se, 17, bos=True).l_armed
    assert not _bar(se, 18, bos=True).l_armed


def test_a_completion_while_holding_a_position_is_lost_not_queued():
    """One slot: the screen's trade is THAT bar's, so a later BOS may not stand in for it.
    MUTATION: retire only when flat -> red."""
    se = _entry()
    _bar(se, 16, sos=True)
    assert not _bar(se, 17, bos=True, flat=False).l_armed
    assert not _bar(se, 18, bos=True).l_armed


def test_the_short_side_mirrors():
    se = _entry()
    ctx = ShiftCtx(dir=-1, sos_ms=1, from_ms=0, stop=110.0, extreme=100.0)
    se.update((None, ctx), now_ms=16 * MIN, m1=_m1(bear_sos=True), high=107, low=106, close=106.5,
              flat=True)
    arm = se.update((None, ctx), now_ms=17 * MIN, m1=_m1(bear_bos=True), high=107, low=106,
                    close=106.0, flat=True)
    assert (arm.s_armed, arm.s_edge, arm.s_sl, arm.s_tp1) == (True, 106.0, 110.0, 100.0)


def test_an_r_target_prices_off_the_risk():
    se = _entry(exec_tp1_r=2.0)
    _bar(se, 16, sos=True)
    assert _bar(se, 17, bos=True, close=104.0).l_tp1 == 112.0      # 104 + 2 * 4


def test_it_refuses_a_fill_clock_other_than_one_minute():
    with pytest.raises(ValueError, match="1 minute"):
        SosFadeConfig(exec_shift_entry=True, exec_sec_fill_tf_min=5, exec_scale_in=False)


# ── the order path it borrows ────────────────────────────────────────────────────


def test_it_enters_at_market_at_the_FULL_first_trade_risk():
    """A re-entry risks a fraction (`exec_sec_risk_pct`, 50 shipped). This is a first trade.
    MUTATION: delete the SHIFT_SRC risk override -> red (half the size)."""
    cfg = SosFadeConfig(exec_shift_entry=True, exec_min_stop_mode="% of price",
                        exec_min_atr_pct=0.0)
    assert cfg.exec_sec_risk_pct != 100.0
    se = ShiftEntry(cfg)
    _bar(se, 16, sos=True)
    arm = _bar(se, 17, bos=True, close=104.0)
    pend = Execution(cfg)._secondary_pending(arm)
    ref = Execution(cfg)._qty_for_risk(cfg.exec_risk_pct, 4.0)
    assert pend.market is True and pend.src == SRC
    assert pend.qty == pytest.approx(ref)


def _open(cfg, entry, sl=100.0, tp1=110.0):
    ex = Execution(cfg)
    pend = _Pending(1, entry, 1.0, sl, tp1, 130.0, 1, src=SRC, market=True, kind="secondary")
    bar = SimpleNamespace(index=1, time_ms=0, open=entry, high=entry, low=entry, close=entry,
                          last_conf_high=None, last_conf_low=None)
    ex._open_position(pend, entry, bar, Decision(index=1), kind="secondary")
    return ex


def test_the_swing_target_stays_at_the_frozen_level_and_banks_the_first_trades_share():
    ex = _open(SosFadeConfig(exec_shift_entry=True, exec_tp1_pct=100.0), entry=104.2)
    assert ex._tp1 == 110.0
    assert ex._tp1_pct() == 100.0


def test_an_r_target_is_re_priced_off_the_real_fill():
    """MUTATION: read `exec_sec_tp_r` for this source -> red."""
    ex = _open(SosFadeConfig(exec_shift_entry=True, exec_tp1_r=2.0), entry=104.5)
    assert ex._tp1 == pytest.approx(113.5)                          # 104.5 + 2 * 4.5


def test_the_stop_follows_the_FIRST_trades_rule_not_a_re_entrys():
    cfg = SosFadeConfig(exec_shift_entry=True, exec_be_arm_r=1.5, exec_be_keep_r=0.25)
    assert _open(cfg, entry=104.0)._protect_rule() == (1.5, 0.25)


def test_its_stop_out_never_kills_a_re_entry_leg():
    """It is not on a re-entry leg. MUTATION: drop SHIFT_SRC from `_OWN_TRADE_SRCS` -> red."""
    from strategies.python.sos_fade import execution as ex_mod
    assert SRC in ex_mod._OWN_TRADE_SRCS


# ── the second feed ──────────────────────────────────────────────────────────────


def test_switching_it_on_asks_for_the_one_minute_feed():
    """Without the feed the entry can never fire, and a run reads 'no trades' as 'no edge'.
    MUTATION: drop it from `FAST_CLOCK_FLAGS` -> red."""
    from strategies.python.sos_fade.strategy import SosFadeStrategy
    assert "exec_shift_entry" in FAST_CLOCK_FLAGS
    assert SosFadeStrategy(SosFadeConfig(exec_shift_entry=True, exec_secondary=False, exec_scale_in=False)
                           ).fast_feed_minutes() == 1
    assert SosFadeStrategy(SosFadeConfig(exec_secondary=False, exec_scale_in=False)
                           ).fast_feed_minutes() is None
