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
    # These fixtures arm via DIVERGENCE (_seq_long_ready sets sos_l_div), so pin the arm
    # source on regardless of the production default (which is now sweep-arm). This isolates
    # the execution mechanics under test from the arm-source default.
    base = dict(exec_req_fvg=False, exec_be_buf_tk=0.0, exec_risk_pct=10.0,
                exec_arm_div=True, exec_arm_sweep=False)
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


# ------------------------------------------------------- blocked setups ---------
# Port of the Pine's pink TRADE BLOCKED tag: a setup price and the engine had READY,
# refused by one of the strategy's own toggles. Reporting only — no decision reads it.

def test_a_refused_setup_is_recorded_with_the_reason_and_the_would_be_entry():
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2, ny_hour=16), _seq_long_ready())
    assert len(ex.blocks) == 1
    b = ex.blocks[0]
    assert b.dir == 1 and b.codes == [3]         # 3 = the final-hour rule
    assert b.labels == ["Final hour"]
    assert "16:00-18:00" in b.reasons[0]
    assert abs(b.edge - 103.82) < 1e-9           # where the limit would have rested


def test_an_armed_setup_records_no_block():
    """The marker is for setups that were REFUSED — one that actually arms must be silent,
    or the count stops meaning anything."""
    ex = Execution(_cfg())
    dec = ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert dec.long_armed is True
    assert ex.blocks == []


def test_every_refusing_rule_is_recorded_in_pine_precedence_order():
    """The one deliberate deviation from the Pine: it reports ONE code, we report them all so
    the chart can filter by reason ("blocked by the veto" must stay true when the final hour
    was also blocking). Pine's precedence survives as the ORDER, so `code` — the primary — is
    still exactly what `f_blkCode` would have returned alone."""
    ex = Execution(_cfg(exec_longs=False))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2, ny_hour=16, veto_on=True, veto_rsi_ob=True),
            _seq_long_ready())
    b = ex.blocks[0]
    assert b.codes == [1, 3, 4]     # direction off · final hour · veto
    assert b.code == 1              # the primary — Pine's single answer


def test_one_record_per_setup_per_reason_set_not_per_bar():
    """The Pine's `sosBar*10 + code` dedupe, generalised to the reason SET: a setup blocked
    for many bars running is ONE record — but a set that CHANGES is a genuinely different
    refusal and gets its own."""
    ex = Execution(_cfg())
    for i in range(4):
        ex.step(_sig(i, 104.0, 104.5, 103.9, 104.2, ny_hour=16), _seq_long_ready())
    assert len(ex.blocks) == 1
    # the final hour passes, the veto takes over → a second, different refusal
    ex.step(_sig(4, 104.0, 104.5, 103.9, 104.2, veto_on=True, veto_rsi_ob=True),
            _seq_long_ready())
    assert [b.codes for b in ex.blocks] == [[3], [4]]
    # picking up a SECOND blocker on the same setup is also a different refusal
    ex.step(_sig(5, 104.0, 104.5, 103.9, 104.2, ny_hour=16, veto_on=True, veto_rsi_ob=True),
            _seq_long_ready())
    assert [b.codes for b in ex.blocks] == [[3], [4], [3, 4]]


def test_a_setup_price_never_made_ready_is_not_a_block():
    """"Ready" asserts only what price and the engine decide (SOS in, fib agrees, an edge to
    rest on). With no SOS there is no setup to refuse, whatever the toggles say."""
    ex = Execution(_cfg(exec_longs=False))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2, ny_hour=16), _seq_flat())
    assert ex.blocks == []


# ------------------------------------------------------- Method 3 (deep fib) ----
# Leg fibs (from _sig): 0.5=105.0  0.618=103.82  0.702=102.8  0.786=102.0  0.886=101.14.
# A gap qualifies for the entry band when bot<=0.5 and top>=0.886. "Near edge" for a
# long is the gap TOP (price reaches it first on the way down).

def test_deep_fib_reprices_a_deep_long_gap_to_the_nearest_shallower_fib():
    """Method 3 ON: a gap floating deep in the zone (near edge below 0.618) rests at the
    fib just SHALLOWER, not the gap edge. Gap top 102.5 sits between 0.786 and 0.702, so
    the limit re-prices to 0.702 = 102.8 (the level price reaches first)."""
    fvg = [(102.5, 101.5, True)]   # (top, bot, is_bull) — deep, floats between 0.786 and 0.702
    ex_on = Execution(_cfg(exec_req_fvg=True, exec_deep_fib=True))
    le, _ = ex_on._entry_edges(_sig(0, 104, 104.5, 103.9, 104.2, fvgs=fvg))
    assert abs(le - 102.8) < 1e-9          # 0.702, not the 102.5 gap edge


def test_deep_fib_off_keeps_the_gap_edge_entry():
    """Same gap, Method 3 OFF: unchanged — the limit rests at the gap's own near edge."""
    fvg = [(102.5, 101.5, True)]
    ex_off = Execution(_cfg(exec_req_fvg=True, exec_deep_fib=False))
    le, _ = ex_off._entry_edges(_sig(0, 104, 104.5, 103.9, 104.2, fvgs=fvg))
    assert abs(le - 102.5) < 1e-9          # min(top, 0.5) = the gap edge


def test_deep_fib_leaves_a_shallow_gap_unchanged():
    """A gap whose near edge is SHALLOWER than 0.618 (top 104.0, between 0.5 and 0.618) is
    not a Method 3 case — it enters at the gap edge whether the toggle is on or off."""
    fvg = [(104.0, 101.5, True)]
    on = Execution(_cfg(exec_req_fvg=True, exec_deep_fib=True))._entry_edges(
        _sig(0, 104, 104.5, 103.9, 104.2, fvgs=fvg))[0]
    off = Execution(_cfg(exec_req_fvg=True, exec_deep_fib=False))._entry_edges(
        _sig(0, 104, 104.5, 103.9, 104.2, fvgs=fvg))[0]
    assert abs(on - 104.0) < 1e-9 and abs(off - 104.0) < 1e-9


def test_deep_fib_reprices_a_deep_short_gap():
    """Short mirror: near edge is the gap BOTTOM. With short-side fibs 0.5=105 0.618=106.18
    0.702=107.2 0.786=108.0 0.886=108.86, a gap bottom 107.5 (between 0.702 and 0.786)
    re-prices to 0.702 = 107.2."""
    fvg = [(108.0, 107.5, False)]
    sig = _sig(0, 106, 106.1, 105.5, 105.8, dir=-1, fvgs=fvg,
               fibo_p2=105.0, fibo_p3=106.18, fibo_p4=107.2, fibo_p5=108.0,
               fibo_p6=108.86, fibo_p1=103.82, fibo_p7=100.0, fibo_p10=110.0)
    _, se = Execution(_cfg(exec_req_fvg=True, exec_deep_fib=True))._entry_edges(sig)
    assert abs(se - 107.2) < 1e-9


# ---------------------------------------------- runner trail + TP2 stop floor ----
# The exit levers added to `mpc_strategy.pine` 2026-07-25. All four tests drive the same
# long to stage 2 (TP1 105 and TP2 106.18 both taken on bar 2) and then read the stop the
# bar-2 close staged, so only the lever under test differs.

def _stage2_long(ex, last_conf_low=None):
    """Fill a long at 103.82 and rally it through TP1+TP2 on bar 2. Returns bar 2's decision,
    whose `.stop` is the runner's stop for bar 3."""
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    return ex.step(_sig(2, 104.0, 107.0, 103.9, 106.5, last_conf_low=last_conf_low), _seq_flat())


def test_structure_trail_rides_the_confirmed_swing_low():
    """Structure mode: the runner stop is the last confirmed swing low minus the buffer.
    Swing 105.6, buffer 20 ticks of 0.01 = 0.20 -> 105.4, which beats the TP1 floor (105)."""
    dec = _stage2_long(Execution(_cfg(exec_runner_trail="Structure (swing)",
                                      exec_struct_trail_buf_tk=20.0)), last_conf_low=105.6)
    assert abs(dec.stop - 105.4) < 1e-9


def test_structure_trail_never_loosens_below_the_stage2_floor():
    """A swing BELOW the floor is ignored — the floor wins. Swing 104.0 - 0.20 = 103.80,
    which is worse than the TP1 floor (105), so the stop stays at 105."""
    dec = _stage2_long(Execution(_cfg(exec_runner_trail="Structure (swing)",
                                      exec_struct_trail_buf_tk=20.0)), last_conf_low=104.0)
    assert abs(dec.stop - 105.0) < 1e-9


def test_structure_trail_with_no_confirmed_swing_falls_back_to_the_floor():
    """Warmup case: no confirmed swing yet -> no trail, floor only."""
    dec = _stage2_long(Execution(_cfg(exec_runner_trail="Structure (swing)")), last_conf_low=None)
    assert abs(dec.stop - 105.0) < 1e-9


def test_fixed_step_trail_ignores_the_confirmed_swing():
    """Fixed-step mode must not read the swing at all. Max favourable 107.0 is only 0.82
    past TP2 (106.18) — under one 5.0 step — so the ratchet hasn't engaged and the floor holds,
    even though a structure trail would have put the stop at 105.4."""
    dec = _stage2_long(Execution(_cfg(exec_runner_trail="Fixed step")), last_conf_low=105.6)
    assert abs(dec.stop - 105.0) < 1e-9


def test_tp2_stop_mode_breakeven_holds_the_stop_at_entry():
    """'Breakeven' keeps the runner at entry + the BE buffer instead of jumping to TP1.
    Entry 103.82, buffer 0 in these fixtures -> 103.82."""
    dec = _stage2_long(Execution(_cfg(exec_runner_trail="Fixed step",
                                      exec_tp2_stop_mode="Breakeven")))
    assert abs(dec.stop - 103.82) < 1e-9


def test_tp2_stop_mode_one_trail_step_behind():
    """'One trail step behind' floors the stop one 5.0 step under the high-water mark
    (107.0 - 5.0 = 102.0), but never below breakeven (103.82), so breakeven wins here."""
    dec = _stage2_long(Execution(_cfg(exec_runner_trail="Fixed step",
                                      exec_tp2_stop_mode="One trail step behind")))
    assert abs(dec.stop - 103.82) < 1e-9


def test_tp2_stop_mode_one_trail_step_behind_beats_breakeven_on_a_big_run():
    """Same mode, bigger run: high-water 112.0 - 5.0 = 107.0 clears breakeven, so it holds."""
    ex = Execution(_cfg(exec_runner_trail="Fixed step",
                        exec_tp2_stop_mode="One trail step behind"))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    dec = ex.step(_sig(2, 104.0, 112.0, 103.9, 111.5), _seq_flat())
    assert abs(dec.stop - 107.0) < 1e-9


def test_aplus_off_disarms_every_a_plus_entry():
    """`exec_aplus` False = the A+ sequence never arms, so nothing is ever placed."""
    ex = Execution(_cfg(exec_aplus=False))
    dec = ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert dec.long_armed is False
    assert ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready()).fills == []
