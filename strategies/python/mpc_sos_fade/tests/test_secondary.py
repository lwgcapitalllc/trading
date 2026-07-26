"""Tests for the secondary (1m sniper) re-entry — starting with the 1m structure feed.

`Structure1m` is a thin latch over the canonical `market_structure` engine (Pine `f_struct1m`):
it must report a 1m SOS the bar it fires, capture that break's leg endpoints, hold them until the
next same-side SOS, and never invent a leg on a bar with no SOS. We reuse the structure engine's
OWN hand-traced scenario (major_length=2) — bar 8 there is a confirmed external bear SOS (CHoCH),
so it is the ground truth for the bear side; the scenario has no bull SOS, which pins the bull side
to "never latched".
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]        # repo root (…/trading)
sys.path.insert(0, str(_ROOT))
# reuse the structure engine's hand-traced bar scenario as ground truth
sys.path.insert(0, str(_ROOT / "engines" / "market_structure" / "tests"))

from strategies.python.mpc_sos_fade.secondary import Structure1m
from test_engine import _SCENARIO_BARS  # noqa: E402


def _run():
    """Feed the scenario through Structure1m, returning the per-bar M1State list."""
    s1 = Structure1m(major_length=2)
    return [s1.update(b.index, b.open, b.high, b.low, b.close) for b in _SCENARIO_BARS]


def test_bear_sos_latches_on_bar_8_with_its_leg():
    states = _run()
    st8 = states[8]
    assert st8.new_bear_sos is True                      # the SOS fires on bar 8
    assert st8.bear_sos_bar == 8
    assert st8.bear_leg_hi is not None and st8.bear_leg_lo is not None
    assert st8.bear_leg_hi > st8.bear_leg_lo             # a valid leg (0.0 above 1.0)


def test_new_bear_sos_edge_fires_exactly_once():
    states = _run()
    fired = [i for i, s in enumerate(states) if s.new_bear_sos]
    assert fired == [8]                                  # the edge is a one-bar pulse


def test_no_bull_sos_in_this_scenario():
    states = _run()
    assert all(not s.new_bull_sos for s in states)       # scenario has no bull SOS
    assert states[-1].bull_sos_bar is None               # so the bull side never latched
    assert states[-1].bull_leg_hi is None


def test_leg_persists_after_the_sos_bar():
    """The leg endpoints hold on every bar after the SOS until a new same-side SOS
    overwrites them (a consumer reads the current leg on any bar, not just the SOS bar)."""
    states = _run()
    hi8, lo8 = states[8].bear_leg_hi, states[8].bear_leg_lo
    for s in states[9:]:            # no further bear SOS after bar 8 in this scenario
        assert s.bear_leg_hi == hi8 and s.bear_leg_lo == lo8
        assert s.new_bear_sos is False


# ── The parity guard: run_dual's PRIMARY path == run(), with exec_secondary OFF ──────────
# The secondary must be purely additive. With it off, `run_dual(df15, df1m)` steps the 15m bars
# in the same order with the same OHLC and never calls step_secondary, so its decision stream and
# trade list must be byte-identical to `run(df15)`. This is the offline stand-in for the truth that
# compare_strategy.py stays exit 0 — it directly exercises the driver + the execution guards on
# real-shaped (deterministic synthetic) data, no cache/network needed.
import math

import pandas as pd

from strategies.python.mpc_sos_fade.config import SosFadeConfig
from strategies.python.mpc_sos_fade.strategy import MpcSosFadeStrategy


def _synth_df15(n: int) -> pd.DataFrame:
    """A deterministic 15m OHLC frame — a drifting sine so structure/fib/etc. actually move."""
    idx = pd.date_range("2025-01-01", periods=n, freq="15min")
    rows = []
    px = 2000.0
    for i in range(n):
        px += 3.0 * math.sin(i / 7.0) + 0.4 * math.sin(i / 2.3)
        o = px
        c = px + 1.5 * math.sin(i / 3.0)
        hi = max(o, c) + 1.2
        lo = min(o, c) - 1.2
        rows.append((o, hi, lo, c))
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])


def _synth_df1m(df15: pd.DataFrame) -> pd.DataFrame:
    """A 1m frame spanning the same window. Content is irrelevant with the secondary OFF (its
    stream is never consumed) — it exists only to exercise the merge interleaving."""
    start, end = df15.index[0], df15.index[-1] + pd.Timedelta("15min")
    idx = pd.date_range(start, end, freq="1min", inclusive="left")
    rows = []
    for i in range(len(idx)):
        px = 2000.0 + math.sin(i / 30.0)
        rows.append((px, px + 0.3, px - 0.3, px))
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"])


def test_run_dual_primary_is_identical_to_run_when_secondary_off():
    df15 = _synth_df15(400)
    df1m = _synth_df1m(df15)
    cfg = SosFadeConfig()                       # exec_secondary defaults False
    a = MpcSosFadeStrategy(cfg).run(df15)
    b = MpcSosFadeStrategy(cfg).run_dual(df15, df1m)
    assert a.decisions == b.decisions           # Decision/Fill are dataclasses → structural ==
    assert a.execution.trades == b.execution.trades


# ── Hand-traced arm + execution (proves the machinery FIRES when conditions align) ──────
# The real 4-day 1m window never lined up all the preconditions on one bar, so these craft the
# aligned state directly: a live 15m LONG leg the primary already traded, price in the 0.618-0.886
# zone, a fresh 1m bull SOS with a valid leg — and check the arm rests the right limit, and that
# execution fills + closes it as a `secondary` trade.
from types import SimpleNamespace

from strategies.python.mpc_sos_fade.execution import Execution
from strategies.python.mpc_sos_fade.secondary import M1State, SecArm, SecondaryArm

# A 15m LONG fib: up-leg low(1.0)=100 → high(0.0)=110. Retrace zone 0.618-0.886 = [101.14, 103.82].
_SIG_LONG = SimpleNamespace(
    fibo_dir=1, fibo_p1=106.18, fibo_p2=105.0, fibo_p3=103.82, fibo_p6=101.14,
    fibo_p7=110.0, fibo_p10=100.0, bull_div_active=True, bear_div_active=False,
    veto_on=False, veto_rsi_ob=False, veto_rsi_os=False)
_SEQ_LONG = SimpleNamespace(l_sos_bar=500, s_sos_bar=None)


def _m1_bull_sos(hi, lo):
    return M1State(bull_sos_bar=1000, bear_sos_bar=None, bull_leg_hi=hi, bull_leg_lo=lo,
                   bear_leg_hi=None, bear_leg_lo=None, direction=1,
                   new_bull_sos=True, new_bear_sos=False)


def test_arm_fires_and_rests_the_right_limit():
    cfg = SosFadeConfig(exec_secondary=True)
    arm_sm = SecondaryArm(cfg)
    # a 1m leg 102.0→103.0 inside the zone; primary on this 15m leg reached BE (be_sos_l == l_sos_bar)
    out = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                        ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert out.l_armed is True
    assert abs(out.l_edge - (103.0 - 1.0 * 0.382)) < 1e-9   # 38.2% retrace of the 1m leg
    assert out.l_sl == 102.0                                # stop = 1m leg origin (1.0)
    assert out.l_tp1 == 105.0 and out.l_tp2 == 106.18       # 15m 0.5 / 0.382
    assert out.l_leg == 1000

    # once that leg has re-entered, it must not re-arm (each 1m leg fires once)
    arm_sm.mark_traded(1)
    again = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                          ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert again.l_armed is False


def test_arm_blocked_until_primary_reached_breakeven():
    cfg = SosFadeConfig(exec_secondary=True)
    arm_sm = SecondaryArm(cfg)
    # the primary on this 15m leg has NOT reached breakeven (be_sos_l is None): a primary that
    # opened and got stopped at its initial stop leaves no re-entry.
    out = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                        ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None)
    assert out.l_armed is False                             # a re-entry is never the first trade


def test_dead_leg_blocks_further_reentries():
    """Once a re-entry on a 15m leg hits its initial stop, `mark_dead` kills the leg — no more
    re-entries on it (even on a fresh 1m shift) until a new break of structure resets it."""
    cfg = SosFadeConfig(exec_secondary=True)
    arm_sm = SecondaryArm(cfg)
    # arms normally on the first fresh 1m leg
    a = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                      ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert a.l_armed is True

    # that re-entry stops out → driver kills the leg
    arm_sm.mark_dead(1, _SEQ_LONG)
    # a brand-new 1m leg (bar 1001) forms in the same setup — must NOT arm (leg is dead)
    dead = arm_sm.update(M1State(bull_sos_bar=1001, bear_sos_bar=None, bull_leg_hi=104.0,
                                 bull_leg_lo=103.0, bear_leg_hi=None, bear_leg_lo=None,
                                 direction=1, new_bull_sos=True, new_bear_sos=False),
                         _SIG_LONG, _SEQ_LONG, zone_close=102.5,
                         ny_hour=10, flat=True, be_sos_l=500, be_sos_s=None)
    assert dead.l_armed is False

    # a new break of structure (l_sos_bar goes None) resets the dead flag
    seq_dead = SimpleNamespace(l_sos_bar=None, s_sos_bar=None)
    arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, seq_dead, zone_close=102.5,
                  ny_hour=10, flat=True, be_sos_l=None, be_sos_s=None)
    # the next setup on a new leg (600) can arm again
    seq_new = SimpleNamespace(l_sos_bar=600, s_sos_bar=None)
    revived = arm_sm.update(_m1_bull_sos(103.0, 102.0), _SIG_LONG, seq_new, zone_close=102.5,
                            ny_hour=10, flat=True, be_sos_l=600, be_sos_s=None)
    assert revived.l_armed is True


def _bar1m(i, o, h, l, c):
    # last_conf_* feed the STRUCTURE runner trail; None here = no confirmed swing on this
    # synthetic 1m stream, so the trail stays off and the stage-2 floor alone holds the stop.
    return SimpleNamespace(index=i, time_ms=1_700_000_000_000 + i * 60_000,
                           open=o, high=h, low=l, close=c,
                           last_conf_high=None, last_conf_low=None)


def test_execution_fills_and_closes_a_secondary_trade():
    execu = Execution(SosFadeConfig(exec_secondary=True), initial_capital=100_000.0)
    arm = SecArm(l_armed=True, l_edge=102.618, l_sl=102.0, l_tp1=105.0, l_tp2=106.18, l_leg=1000)

    # bar A: place the resting limit (one-bar delay — no fill this bar)
    assert execu.step_secondary(_bar1m(0, 102.7, 102.8, 102.65, 102.7), arm) is None
    assert execu.is_flat
    # bar B: price dips to the limit → fills LONG as a secondary; no exit on the fill bar
    assert execu.step_secondary(_bar1m(1, 102.7, 102.8, 102.5, 102.6), arm) == 1
    assert not execu.is_flat and execu.entry_kind == "secondary"
    # bar C: price collapses through the 1m-leg stop → full stop-out, trade closes
    execu.step_secondary(_bar1m(2, 102.4, 102.5, 101.5, 101.6), arm)
    assert execu.is_flat
    assert len(execu.trades) == 1
    t = execu.trades[0]
    assert t.kind == "secondary" and t.dir == 1
    assert abs(t.entry_price - 102.618) < 1e-9
    assert t.pnl_usd < 0                                    # stopped for a loss
