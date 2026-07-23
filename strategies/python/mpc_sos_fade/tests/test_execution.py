"""Execution tests — the broker emulator, entry ladder, stop staging and R, driven
directly with crafted Signals + SeqState (no engines), so every fill is hand-checkable.

Leg used throughout (bull): high anchor 110, low anchor 100, range 10 -> fib levels
    0.382=106.18  0.5=105.0  0.618=103.82  0.886=101.14  0.0=110.0  1.0=100.0
With "Require FVG" off the long edge falls back to 0.618 = 103.82 (a DEEP entry:
TP1=0.5=105.0, TP2=0.382=106.18, stop=1.0=100.0).
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT / "strategies" / "python"))

from mpc_sos_fade import SosFadeConfig, Execution, SeqState  # noqa: E402
from mpc_sos_fade.signals import Signals  # noqa: E402


def _cfg(**kw):
    base = dict(exec_req_fvg=False, exec_be_buf_tk=0.0, exec_risk_pct=10.0)
    base.update(kw)
    return SosFadeConfig(**base)


def _sig(index, o, h, l, c, dir=1, ny_hour=8, **kw):
    base = dict(
        index=index, time_ms=index * 900_000, open=o, high=h, low=l, close=c,
        session_gap_bar=False, ny_hour=ny_hour,
        bull_sos=False, bear_sos=False, bull_bos=False, bear_bos=False,
        recent_ssl="", recent_ssl_bar=None, recent_ssl_time=None,
        recent_bsl="", recent_bsl_bar=None, recent_bsl_time=None,
        last_bull_div_bar=None, last_bear_div_bar=None,
        bull_div_active=False, bear_div_active=False, veto_on=False, veto_rsi_ob=False, veto_rsi_os=False,
        fibo_dir=dir,
        fibo_p1=106.18, fibo_p2=105.0, fibo_p3=103.82, fibo_p4=102.8,
        fibo_p5=102.0, fibo_p6=101.14, fibo_p7=110.0, fibo_p10=100.0,
        fibo_half_reached=True, fibo_618_ever_reached=True, fibo7_touched=False,
        fvgs=[], poi_long_now=False, poi_short_now=False,
    )
    base.update(kw)
    return Signals(**base)


def _seq_long_ready(sos_bar=1):
    """A long setup fully armed to READY (Stage 4), divergence source live."""
    return SeqState(
        l_stage=4, s_stage=0, l_sos_bar=sos_bar, s_sos_bar=None,
        l_half=True, l_618=True, s_half=False, s_618=False,
        l_poi=False, s_poi=False, l_fvg=False, s_fvg=False,
        sos_l_swp=False, sos_l_div=True, sos_s_swp=False, sos_s_div=False,
        new_sweep_l=False, new_div_l=False, new_sweep_s=False, new_div_s=False,
        retro_link_l=False, retro_link_s=False,
    )


def _seq_flat():
    return SeqState(
        l_stage=0, s_stage=0, l_sos_bar=None, s_sos_bar=None,
        l_half=False, l_618=False, s_half=False, s_618=False,
        l_poi=False, s_poi=False, l_fvg=False, s_fvg=False,
        sos_l_swp=False, sos_l_div=False, sos_s_swp=False, sos_s_div=False,
        new_sweep_l=False, new_div_l=False, new_sweep_s=False, new_div_s=False,
        retro_link_l=False, retro_link_s=False,
    )


# ------------------------------------------------------- arming + sizing --------
def test_long_arms_and_places_a_limit():
    ex = Execution(_cfg(), initial_capital=1_000_000.0)
    dec = ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert dec.long_armed is True
    assert abs(dec.long_edge - 103.82) < 1e-9
    # nothing filled yet — a limit placed this bar is active next bar
    assert dec.fills == []


def test_entry_fills_next_bar_not_this_bar():
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())   # place
    # bar 1 dips to the edge -> fills; but no EXIT may fill on the entry bar
    dec = ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    entries = [f for f in dec.fills if f.kind == "entry"]
    exits = [f for f in dec.fills if f.kind == "exit"]
    assert len(entries) == 1
    assert abs(entries[0].price - 103.82) < 1e-9   # filled at the limit
    assert exits == []                              # one-bar delay


def test_sizing_matches_risk_over_stop_distance():
    ex = Execution(_cfg(exec_risk_pct=10.0), initial_capital=1_000_000.0)
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    # qty = equity*10% / (edge-sl) = 100000 / 3.82
    assert abs(ex._qty - (100_000.0 / 3.82)) < 1e-6


# ------------------------------------------------------- winning ladder ---------
def test_ladder_wins_tp1_tp2_then_runner_trail():
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())     # place
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())     # fill @103.82
    # bar 2: rallies through TP1(105) and TP2(106.18), never near stop(100)
    dec2 = ex.step(_sig(2, 104.0, 107.0, 103.9, 106.5), _seq_flat())
    ids = {f.order_id for f in dec2.fills if f.kind == "exit"}
    assert "L-TP1" in ids and "L-TP2" in ids
    # runner (30%) still open; stage advanced to 2 -> stop lifted to TP1 (105)
    assert dec2.stop is not None and abs(dec2.stop - 105.0) < 1e-9
    # bar 3: pulls back to 105 -> runner stops out
    dec3 = ex.step(_sig(3, 106.0, 106.2, 104.9, 105.0), _seq_flat())
    assert any(f.order_id == "L-RUN" for f in dec3.fills)
    assert len(ex.trades) == 1
    assert ex.trades[0].r > 0        # net winner


# ------------------------------------------------------- losing stop-out --------
def test_stop_out_is_minus_one_r():
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())     # place
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())     # fill @103.82
    # bar 2 opens near the low and trades down through the stop (100)
    dec = ex.step(_sig(2, 100.5, 101.0, 99.5, 99.8), _seq_flat())
    assert ex._pos_dir == 0
    assert len(ex.trades) == 1
    assert abs(ex.trades[0].r - (-1.0)) < 1e-6     # full -1R


def test_trade_records_favorable_and_adverse_excursion():
    """Excursion = how far the trade ran each way before closing, across the whole hold.

    Long filled @103.82; the hold's highest high is bar 2's 107.0 (favorable) and its lowest low is
    the 103.5 the entry bar dipped to (adverse). Both are measured vs entry with the same point value,
    so their ratio is price-only — free of qty/point_value.
    """
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())     # place
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())     # fill @103.82, low 103.5
    ex.step(_sig(2, 104.0, 107.0, 103.9, 106.5), _seq_flat())           # high 107.0
    ex.step(_sig(3, 106.0, 106.2, 104.9, 105.0), _seq_flat())           # runner stops @105

    t = ex.trades[0]
    assert t.mfe_usd > 0 and t.mae_usd < 0
    expected_ratio = (107.0 - t.entry_price) / (103.5 - t.entry_price)   # favorable vs adverse, signed
    assert abs(t.mfe_usd / t.mae_usd - expected_ratio) < 1e-3   # 2dp rounding on the stored $ values


def test_late_day_block_stops_new_entries():
    ex = Execution(_cfg())
    dec = ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2, ny_hour=16), _seq_long_ready())
    assert dec.long_armed is False


def test_veto_blocks_when_respected():
    ex = Execution(_cfg())
    # extreme-RSI veto — never exempt, blocks whatever the SOS bar is
    dec = ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2, veto_on=True, veto_rsi_ob=True),
                  _seq_long_ready())
    assert dec.long_armed is False


def test_divergence_before_the_sos_still_vetoes():
    """Pine longVetoA: a bear divergence already live AT OR BEFORE the SOS bar blocks
    the long, exactly as the old rule did."""
    ex = Execution(_cfg())
    dec = ex.step(
        _sig(0, 104.0, 104.5, 103.9, 104.2,
             veto_on=True, bear_div_active=True, last_bear_div_bar=1),
        _seq_long_ready(sos_bar=1),
    )
    assert dec.long_veto is True
    assert dec.long_armed is False


def test_divergence_after_the_sos_is_exempt():
    """The 2026-07-21 Pine change: a bear divergence that printed AFTER the bull SOS is
    the pullback the setup is waiting on, not a reversal — it no longer vetoes."""
    ex = Execution(_cfg())
    dec = ex.step(
        _sig(0, 104.0, 104.5, 103.9, 104.2,
             veto_on=True, bear_div_active=True, last_bear_div_bar=5),
        _seq_long_ready(sos_bar=1),
    )
    assert dec.long_veto is False
    assert dec.long_armed is True
