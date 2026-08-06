"""The time stop (`exec_time_stop_mode` / `exec_time_stop_hrs`) — the one exit lever
here driven by the clock instead of by price.

The fixtures are the ones `test_execution.py` uses: a long setup that fills at 103.82
with the stop at 100.0, TP1 105.0 and TP2 106.18, one bar every 15 minutes
(`time_ms = index * 900_000`). The entry fills on bar 1, so bar `n` is
`(n - 1) * 15` minutes into the trade.

What these lock, and why each one matters:
  * OFF closes nothing — the default has to be byte-identical to the pre-lever build,
    or every stored run stops reproducing.
  * "Before TP1 only" is gated on the STAGE, not on the clock alone. A trade that has
    touched TP1 has staged its stop to breakeven and can no longer take a full loss,
    which is the entire reason the lever exists in that shape.
  * "Always" ignores the stage, so the two modes are genuinely different code paths
    rather than one path with a cosmetic label.
  * The clock runs from the FILL, never from the bar the limit was placed on — a limit
    can rest for days, and charging that waiting time against the trade's life would
    close positions that had barely opened.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1].parent))

from mpc_sos_fade import SosFadeConfig, Execution  # noqa: E402
from mpc_sos_fade.tests.test_execution import _cfg, _sig, _seq_long_ready, _seq_flat  # noqa: E402


def _run_to(ex, bars, seq_after=None):
    """Place on bar 0, fill on bar 1, then drift quietly for `bars` more bars.

    The drift bars sit between the breakeven stop (103.82) and TP1 (105.0), so nothing
    price-driven can close the position and the ONLY thing that can is the clock.
    """
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())   # fill @ 103.82
    last = None
    for i in range(2, 2 + bars):
        last = ex.step(_sig(i, 104.2, 104.6, 103.95, 104.3), seq_after or _seq_flat())
    return last


def _exit_ids(dec):
    return {f.order_id for f in dec.fills if f.kind == "exit"}


# ------------------------------------------------------------------ OFF ---------
def test_off_never_closes_a_position_however_long_it_runs():
    """100 bars is 25 hours — past every cutoff measured, and Off still closes nothing.

    `Off` stopped being the shipped default on 2026-08-06, so this asks for it EXPLICITLY.
    It used to read the default and assert it was Off, which quietly made one test carry
    two claims: that Off is inert, and that Off is what ships. The second belongs to
    `test_the_shipped_default_is_the_measured_shape` below, where a deliberate change to
    the default fails one honest test instead of a mislabelled one."""
    ex = Execution(_cfg(exec_time_stop_mode="Off"))
    _run_to(ex, 100)
    assert ex.trades == []
    assert ex._pos_dir != 0          # still holding


def test_the_shipped_default_is_the_measured_shape():
    """The default is a DECISION, not an accident, so it is pinned where a reader can see it.

    "Before TP1 only" at 36h was measured by real replay over 155,440 M15 bars: 6 trades cut
    in 6.5 years, all losers, max drawdown 7.99R -> 5.62R. The stage gate is the lever, not
    the clock — "Always" at the same 36 hours gives back a third of the strategy — so a
    change to EITHER field here should have a replay behind it."""
    cfg = SosFadeConfig()
    assert cfg.exec_time_stop_mode == "Before TP1 only"
    assert cfg.exec_time_stop_hrs == 36.0


def test_off_ignores_the_hours_field_entirely():
    """A swept `exec_time_stop_hrs` sitting behind an Off mode is inert, not an error —
    the same standing `exec_sl_custom` has behind a non-Custom `exec_sl_level`."""
    ex = Execution(_cfg(exec_time_stop_mode="Off", exec_time_stop_hrs=0.25))
    _run_to(ex, 40)
    assert ex.trades == []


# -------------------------------------------------- Before TP1 only -------------
def test_before_tp1_closes_a_trade_that_never_reached_tp1():
    ex = Execution(_cfg(exec_time_stop_mode="Before TP1 only", exec_time_stop_hrs=1.0))
    # fill on bar 1 (t=900_000); 1.0h later is t=4_500_000, i.e. bar 5 DECIDES and bar 6 FILLS.
    dec = _run_to(ex, 5)             # bars 2..6
    assert "L-TIME" in _exit_ids(dec)
    assert len(ex.trades) == 1
    assert ex.trades[0].exit_reason == "L-TIME"


def test_the_close_fills_at_the_NEXT_bar_open_not_at_the_deciding_bar_close():
    """Pine's `strategy.close()` is a MARKET order, so it cannot execute on the bar that
    decided it — that bar has already closed. It fills at the next bar's OPEN.

    Watched red against the first implementation, which closed at the deciding bar's close.
    That version passed every other test in this file and failed a real 4-hour-cutoff export
    on its first exercised bar: Python booked bar 696's close 3651.28, Pine booked bar 697's
    open 3651.23. The whole defect is one bar, and no unit test here could see it, because
    every one of them was written against the same wrong assumption."""
    ex = Execution(_cfg(exec_time_stop_mode="Before TP1 only", exec_time_stop_hrs=1.0))
    dec5 = _run_to(ex, 4)                                   # bar 5 decides
    assert _exit_ids(dec5) == set(), "the deciding bar must not fill it"
    assert ex._pos_dir != 0
    dec6 = ex.step(_sig(6, 104.11, 104.6, 103.95, 104.3), _seq_flat())
    assert "L-TIME" in _exit_ids(dec6)
    assert ex.trades[0].exit_price == 104.11                # bar 6's OPEN, not bar 5's close


def test_before_tp1_leaves_a_trade_that_reached_tp1_alone_for_ever():
    """The load-bearing half. Touching TP1 stages the stop to breakeven, so the trade is
    no longer the thing the time stop exists to cut — and the clock must stop applying."""
    ex = Execution(_cfg(exec_time_stop_mode="Before TP1 only", exec_time_stop_hrs=1.0))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())   # fill @ 103.82
    ex.step(_sig(2, 104.2, 105.4, 104.0, 105.2), _seq_flat())         # tags TP1 -> stage 1
    assert ex._stage >= 1
    for i in range(3, 40):                                            # ~9 hours past the cutoff
        ex.step(_sig(i, 104.6, 104.9, 104.2, 104.5), _seq_flat())
    assert ex.trades == []
    assert ex._pos_dir != 0


# ------------------------------------------------------------- Always -----------
def test_always_closes_even_after_tp1_was_reached():
    ex = Execution(_cfg(exec_time_stop_mode="Always", exec_time_stop_hrs=1.0))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    ex.step(_sig(2, 104.2, 105.4, 104.0, 105.2), _seq_flat())         # stage 1
    assert ex._stage >= 1
    seen = set()
    for i in range(3, 8):
        seen |= _exit_ids(ex.step(_sig(i, 104.6, 104.9, 104.2, 104.5), _seq_flat()))
    assert "L-TIME" in seen
    assert len(ex.trades) == 1


def test_always_and_before_tp1_agree_when_tp1_is_never_reached():
    """The two modes may only differ on trades that reached TP1. If they diverge here the
    stage gate has leaked into the clock itself."""
    out = []
    for mode in ("Before TP1 only", "Always"):
        ex = Execution(_cfg(exec_time_stop_mode=mode, exec_time_stop_hrs=1.0))
        _run_to(ex, 5)   # bar 5 decides, bar 6 fills
        out.append((len(ex.trades), ex.trades[0].exit_reason, ex.trades[0].exit_ms))
    assert out[0] == out[1]


# ---------------------------------------------------------- the clock ------------
def test_the_clock_runs_from_the_FILL_not_from_the_bar_the_limit_was_PLACED():
    """A resting limit can wait for days. If the clock started at placement, a trade could
    be closed on the bar after it opened for having 'been open' for hours."""
    ex = Execution(_cfg(exec_time_stop_mode="Before TP1 only", exec_time_stop_hrs=1.0))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())   # place
    # 8 bars (2 hours) where price never reaches the limit — the order just rests.
    for i in range(1, 9):
        ex.step(_sig(i, 104.5, 104.8, 104.1, 104.4), _seq_long_ready())
    assert ex._pos_dir == 0                                           # nothing filled yet
    ex.step(_sig(9, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())   # NOW it fills
    assert ex._pos_dir != 0
    # one bar later the trade is 15 minutes old, not 2h15 — the cutoff must not fire.
    ex.step(_sig(10, 104.2, 104.6, 103.95, 104.3), _seq_flat())
    assert ex.trades == []


def test_it_fires_on_the_bar_that_REACHES_the_threshold_not_the_one_after():
    """`>=`, so a threshold landing exactly on a bar close DECIDES on that bar.

    The fill is then one bar later — see
    `test_the_close_fills_at_the_NEXT_bar_open_not_at_the_deciding_bar_close`. This test is
    about WHEN the clock decides; that one is about when the broker fills. Keeping them
    apart is the point: they were one test, and the merged version hid a one-bar error."""
    ex = Execution(_cfg(exec_time_stop_mode="Before TP1 only", exec_time_stop_hrs=1.0))
    _run_to(ex, 3)                   # bar 4 -> t=3_600_000, 45 min into the trade
    assert ex.trades == []
    ex.step(_sig(5, 104.2, 104.6, 103.95, 104.3), _seq_flat())            # exactly 1.0h: decides
    dec_fill = ex.step(_sig(6, 104.2, 104.6, 103.95, 104.3), _seq_flat())
    assert "L-TIME" in _exit_ids(dec_fill)


def test_the_clock_is_CALENDAR_hours_and_counts_a_weekend():
    """Bars are only emitted while the market is open, so a Friday-to-Monday hold advances
    the clock by the whole weekend even though only a few bars arrive. That is deliberate —
    it is the same basis the swap is charged on, and it is what a reader sees on a chart."""
    ex = Execution(_cfg(exec_time_stop_mode="Before TP1 only", exec_time_stop_hrs=24.0))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())   # fill, t=900_000
    # the next bar arrives two days later — one bar, 48 hours of clock
    two_days = _sig(2, 104.2, 104.6, 103.95, 104.3)
    two_days.time_ms = 900_000 + 48 * 3_600_000
    ex.step(two_days, _seq_flat())                                   # decides on the weekend gap
    dec = ex.step(_sig(3, 104.2, 104.6, 103.95, 104.3), _seq_flat())
    assert "L-TIME" in _exit_ids(dec)


# --------------------------------------------------------- the exit tag ----------
def test_the_time_stop_leg_is_tagged_TIME_and_a_force_close_is_still_CLOSE():
    """Two halves of one rule. The new exit needs its own name so it is countable in the
    lab, and the EXISTING force-closes must keep theirs — renaming those would make every
    stored run's exit list stop matching its own chart."""
    ex = Execution(_cfg(exec_time_stop_mode="Before TP1 only", exec_time_stop_hrs=1.0))
    dec = _run_to(ex, 5)
    assert "L-TIME" in _exit_ids(dec)

    # The opposite-SOS force close, on the same fixtures, still books as L-CLOSE — and it is
    # deferred to the next bar's open by the same rule, because it is the same `strategy.close()`
    # market order in Pine. It defaults OFF and has never appeared in a parity export, so that
    # half is corrected by inference from the time stop's measured evidence, not by its own.
    ex2 = Execution(_cfg(exec_close_opp_sos=True))
    ex2.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex2.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    ex2.step(_sig(2, 104.2, 104.6, 103.95, 104.3, bear_sos=True), _seq_flat())   # decides
    dec2 = ex2.step(_sig(3, 104.2, 104.6, 103.95, 104.3), _seq_flat())           # fills
    assert "L-CLOSE" in _exit_ids(dec2)


def test_a_short_books_its_time_stop_as_S_TIME():
    cfg = _cfg(exec_time_stop_mode="Before TP1 only", exec_time_stop_hrs=1.0)
    ex = Execution(cfg)
    seq = _seq_long_ready()
    seq.l_stage, seq.s_stage = 0, 4
    seq.l_sos_bar, seq.s_sos_bar = None, 1
    seq.sos_l_div, seq.sos_s_div = False, True
    seq.s_half, seq.s_618 = True, True
    seq.s_arm_src = "DIV"
    # bear leg: the fib ladder flips, so the anchors and levels mirror
    kw = dict(dir=-1, fibo_p1=103.82, fibo_p2=105.0, fibo_p3=106.18, fibo_p4=107.2,
              fibo_p5=108.0, fibo_p6=108.86, fibo_p7=100.0, fibo_p10=110.0,
              fibo_ash=110.0, fibo_asl=100.0)
    ex.step(_sig(0, 105.5, 106.1, 105.4, 105.8, **kw), seq)
    ex.step(_sig(1, 105.8, 106.5, 105.7, 106.0, **kw), seq)           # fill the sell limit
    assert ex._pos_dir < 0
    seen = set()
    for i in range(2, 7):
        seen |= _exit_ids(ex.step(_sig(i, 106.0, 106.1, 105.6, 105.9, **kw), _seq_flat()))
    assert "S-TIME" in seen


# --------------------------------------------------------- validation ------------
def test_an_unrecognised_mode_raises_rather_than_falling_through_to_no_time_stop():
    with pytest.raises(ValueError, match="exec_time_stop_mode"):
        SosFadeConfig(exec_time_stop_mode="before tp1")          # lowercase: not a member


def test_zero_hours_with_the_mode_on_raises_instead_of_closing_everything():
    """0 is not 'off'. Read literally it closes every position on the bar after its fill,
    which is a different backtest wearing the operator's label."""
    with pytest.raises(ValueError, match="exec_time_stop_hrs"):
        SosFadeConfig(exec_time_stop_mode="Always", exec_time_stop_hrs=0.0)


def test_zero_hours_behind_an_OFF_mode_is_inert_not_an_error():
    """An optimizer may sweep the hours axis with the mode fixed Off. Every combo is then
    identical, which is a wasted grid — raising on it would kill an otherwise valid run."""
    SosFadeConfig(exec_time_stop_mode="Off", exec_time_stop_hrs=0.0)


# ------------------------------------------------------------- B-LEG -------------
def test_the_bleg_fork_inherits_the_time_stop():
    """Both bots share ONE exit ladder, and this lever lives in the parent's `step()`,
    which `BLegExecution` delegates to. If this ever fails, the fork has grown its own
    step loop and the ladder has silently forked with it."""
    from mpc_bleg.config import BLegConfig
    from mpc_bleg.execution import BLegExecution

    cfg = BLegConfig(exec_time_stop_mode="Before TP1 only", exec_time_stop_hrs=1.0)
    assert cfg.exec_time_stop_mode == "Before TP1 only"
    assert BLegExecution(cfg)._time_stop_due.__func__ is Execution._time_stop_due
