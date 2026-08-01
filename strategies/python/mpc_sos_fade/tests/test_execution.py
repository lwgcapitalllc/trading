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
    # `exec_sl_level` is pinned for the same reason: the price fixtures put the stop at
    # fibo_p10 = 100.0 and the sizing / −1R assertions are hand-computed off that, so they must
    # not move when the shipped default does (it went 1.0 → 0.886 on 2026-07-27).
    base = dict(exec_req_fvg=False, exec_be_buf_tk=0.0, exec_risk_pct=10.0,
                exec_arm_div=True, exec_arm_sweep=False, exec_sl_level="1.0")
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
        # Bull leg, so fiboP7 (0.0) IS the high anchor and fiboP10 (1.0) IS the low one.
        fibo_ash=110.0, fibo_asl=100.0,
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
        retro_link_l=False, retro_link_s=False, l_arm_src="DIV",
    )


def _seq_long_stage2(sos_bar=1):
    """A long setup at Stage 2 — SOS in, price has NOT retraced (neither fib latch set)."""
    s = _seq_long_ready(sos_bar)
    s.l_stage, s.l_half, s.l_618 = 2, False, False
    return s


def _seq_long_dead():
    """The bar AFTER a long setup dies. `sos_l_div` survives the death in the real sequence
    (`_clear_long` never touches it — only the next SOS reassigns it), so the fixture keeps it
    too; without that the arm source would read as absent on exactly the bar the miss is booked."""
    s = _seq_flat()
    s.sos_l_div = True
    s.l_arm_src = "DIV"
    return s


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
    # Scale-outs pinned ON: the shipped default is 0/0 (everything rides the runner), and this
    # test is about the SCALE-OUT mechanics, so it states the sizes it needs rather than
    # inheriting them — same reason _cfg pins the arm source.
    ex = Execution(_cfg(exec_tp1_pct=30.0, exec_tp2_pct=40.0))
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


def test_zero_pct_rungs_bank_nothing_but_still_stage_the_stop():
    """The SHIPPED default (0/0, 2026-07-27). Two things must both hold, and they pull opposite
    ways: no size may leave at TP1/TP2, yet touching those PRICES must still lift the stop. The
    failure mode this guards is the Pine's — `strategy.exit(qty_percent = 0)` closes the WHOLE
    position, turning "bank nothing" into "bank everything". Python must not grow that bug."""
    cfg = _cfg()
    assert (cfg.exec_tp1_pct, cfg.exec_tp2_pct) == (0.0, 0.0)     # the default under test
    ex = Execution(cfg)
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())     # place
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())     # fill @103.82
    qty_at_entry = ex._qty

    # bar 2: rallies clean through TP1 (105) and TP2 (106.18), nowhere near the stop (100).
    dec2 = ex.step(_sig(2, 104.0, 107.0, 103.9, 106.5), _seq_flat())
    assert not [f for f in dec2.fills if f.kind == "exit"]   # nothing banked
    assert ex._pos_dir == 1 and ex._qty == qty_at_entry      # full size still on
    # ...but the stop staged exactly as if the rungs had filled: TP2 seen -> floor = TP1 price.
    assert dec2.stop is not None and abs(dec2.stop - 105.0) < 1e-9

    # bar 3: pulls back into the staged stop — the WHOLE position leaves as the runner.
    dec3 = ex.step(_sig(3, 106.0, 106.2, 104.9, 105.0), _seq_flat())
    runs = [f for f in dec3.fills if f.order_id == "L-RUN"]
    assert len(runs) == 1 and abs(runs[0].qty - qty_at_entry) < 1e-9
    assert len(ex.trades) == 1 and ex.trades[0].r > 0


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


# ------------------------------------------------------- missed setups ---------
# Port of the Pine's orange 2-of-3 callout: a setup that reached two or three of the three
# confluences and then DIED without becoming a trade. Reporting only, like the blocks.

def test_a_setup_that_had_everything_and_never_filled_is_a_3_of_3_miss():
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert ex.misses == []                      # still alive — nothing is booked yet
    ex.step(_sig(1, 104.0, 104.5, 103.9, 104.2), _seq_long_dead())
    assert len(ex.misses) == 1
    m = ex.misses[0]
    assert (m.met, m.code, m.dir) == (3, 7, 1)  # 7 = the limit rested and price never came
    assert m.labels == ["Never filled"]
    assert m.near is True
    assert abs(m.edge - 103.82) < 1e-9          # where the limit would have rested
    assert m.met_lines == ["Arm — RSI divergence", "SOS — confirmed",
                           "Zone — 0.5-0.886 tagged, FVG live"]


def test_a_setup_that_never_retraced_is_a_2_of_3_and_is_NOT_a_near_miss():
    """The ordinary way most setups die. It is still recorded — the lab has no label cap and a
    count nobody kept is a count nobody can get back — but `near` is False, which is what the
    chart reads to leave it out of the default view."""
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_stage2())
    ex.step(_sig(1, 104.0, 104.5, 103.9, 104.2), _seq_long_dead())
    m = ex.misses[0]
    assert (m.met, m.code) == (2, 2)
    assert m.labels == ["No retrace"] and m.near is False
    assert m.met_lines == ["Arm — RSI divergence", "SOS — confirmed"]


def test_a_setup_armed_by_a_disabled_source_names_that_source():
    """With BOTH arm toggles off the arm confluence cannot count, so the setup tops out at 2/3
    — and the reason has to say WHICH trigger was switched off, or it means nothing. That name
    comes from the sequence's `l_arm_src`, the one place that still knows."""
    ex = Execution(_cfg(exec_arm_div=False, exec_arm_sweep=False))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.0, 104.5, 103.9, 104.2), _seq_long_dead())
    m = ex.misses[0]
    assert (m.met, m.code) == (2, 1)
    assert m.arm_met is False
    assert "RSI divergence" in m.reasons[0] and "switched OFF" in m.reasons[0]


def test_a_3_of_3_that_a_rule_refused_names_the_rule_not_the_fill():
    """At 3/3 every confluence was there, so the miss reports the ENTRY-side reason instead —
    in the Pine's precedence. The final hour beats 'never filled'."""
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2, ny_hour=16), _seq_long_ready())
    ex.step(_sig(1, 104.0, 104.5, 103.9, 104.2, ny_hour=16), _seq_long_dead())
    m = ex.misses[0]
    assert (m.met, m.code) == (3, 5)
    assert m.labels == ["Final hour"]


def test_one_record_per_setup_booked_only_when_it_dies():
    """A setup alive for many bars is ONE record, and nothing at all until it actually dies —
    otherwise the count measures bars, not setups."""
    ex = Execution(_cfg())
    for i in range(5):
        ex.step(_sig(i, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert ex.misses == []
    ex.step(_sig(5, 104.0, 104.5, 103.9, 104.2), _seq_long_dead())
    ex.step(_sig(6, 104.0, 104.5, 103.9, 104.2), _seq_long_dead())
    assert len(ex.misses) == 1


def test_a_setup_that_traded_is_never_a_miss():
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.0, 104.5, 103.0, 104.0), _seq_long_ready())   # limit at 103.82 fills
    assert ex._pos_dir == 1
    ex.step(_sig(2, 104.0, 104.5, 103.9, 104.2), _seq_long_dead())
    assert ex.misses == []


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


def test_swing_ratchet_climbs_above_the_bare_structure_anchor():
    """"Structure + % ratchet": same anchor as Structure (swing low 105.6 - 0.20 = 105.40),
    then one step per step of favourable move. Max favourable on bar 2 is 107.0, so the step
    is 107.0 * 1% = 1.07 and the run is 107.0 - 105.40 = 1.60. floor((1.60-1.07)/1.07) = 0,
    so the stop is anchor + 0 = 105.40 — engaged, and never below the anchor."""
    dec = _stage2_long(Execution(_cfg(exec_runner_trail="Structure + % ratchet",
                                      exec_struct_trail_buf_tk=20.0,
                                      exec_trail_pct=1.0)), last_conf_low=105.6)
    assert abs(dec.stop - 105.4) < 1e-9


def test_swing_ratchet_is_never_looser_than_the_plain_structure_trail():
    """The property the whole lever rests on: for the SAME swing it can only ever be equal
    to or TIGHTER than Structure (swing). A tiny step makes the ratchet bind hard; the plain
    trail sits at the anchor. Long, so tighter = higher."""
    swing = 105.6
    plain = _stage2_long(Execution(_cfg(exec_runner_trail="Structure (swing)",
                                        exec_struct_trail_buf_tk=20.0)), last_conf_low=swing)
    ratchet = _stage2_long(Execution(_cfg(exec_runner_trail="Structure + % ratchet",
                                          exec_struct_trail_buf_tk=20.0,
                                          exec_trail_pct=0.2)), last_conf_low=swing)
    assert ratchet.stop >= plain.stop - 1e-12
    # ...and with a 0.2% step (0.214) it genuinely binds: run 1.60 -> 6 whole steps past
    # the first, so anchor + 6*0.214 = 106.684, well above the plain trail's 105.40.
    assert ratchet.stop > plain.stop


def test_swing_ratchet_with_no_confirmed_swing_falls_back_to_the_floor():
    """Same warmup guard as the plain structure trail — no anchor, no trail, floor only."""
    dec = _stage2_long(Execution(_cfg(exec_runner_trail="Structure + % ratchet")),
                       last_conf_low=None)
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


def test_shipped_sl_level_default_is_the_deep_band_edge():
    """The SHIPPED default is 0.886 (2026-07-27) — the deep edge of the 0.5-0.886 entry band,
    matching `mpc_strategy.pine` / `mpc_strategy_export.pine`. Toggle-default parity with the
    Pine is a hard requirement (see config.py's docstring), and this value is load-bearing:
    it moves the stop, so a silent drift changes every trade's size and R. The B-LEG fork
    pins "1.0" instead, because ITS Pine still ships 1.0."""
    from mpc_bleg.config import BLegConfig

    assert SosFadeConfig().exec_sl_level == "0.886"
    assert BLegConfig().exec_sl_level == "1.0"


# ------------------------------------------- minimum stop distance (Pine execMinStop*) --------
# The fixtures put the long entry edge at fibo_p3 = 103.82 and the stop anchor at fibo_p10 =
# 100.0, so every test below works against a stop distance of exactly 3.82 (3.68% of the entry
# price). Bars are parked at 107.5-109.5 so nothing ever fills and the placement decision is the
# only thing under test; their true range is a flat 2.00, which is what makes the ATR exact.

def _quiet_bars(ex, seq, n, start=0):
    """`n` bars that never touch the 103.82 entry edge. TR is 2.00 on every one of them
    (high-low = 2.00 dominates both close-gap terms), so ATR(14) settles at exactly 2.00."""
    dec = None
    for i in range(n):
        dec = ex.step(_sig(start + i, 108.5, 109.5, 107.5, 108.5), seq)
    return dec


def test_min_stop_defaults_off_and_refuses_nothing():
    """"Off" must stay inert: it is the historical default, so turning this feature on may not
    move a single past result until someone selects a mode."""
    assert SosFadeConfig().exec_min_stop_mode == "Off"
    ex = Execution(_cfg())
    dec = ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert dec.long_armed is True
    assert ex._pend_long is not None


def test_pct_floor_refuses_a_stop_narrower_than_the_floor():
    """The stop is 3.68% of price here, so a 1% floor passes and a 5% floor refuses. The setup
    is still ARMED — the floor is an order-placement filter, not an arm gate, exactly like the
    Pine, where `longArmed` is unchanged and only `strategy.entry` vs `strategy.cancel` moves."""
    passes = Execution(_cfg(exec_min_stop_mode="% of price", exec_min_stop_val=1.0))
    dec = passes.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert dec.long_armed is True and passes._pend_long is not None

    refuses = Execution(_cfg(exec_min_stop_mode="% of price", exec_min_stop_val=5.0))
    dec = refuses.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert dec.long_armed is True
    assert refuses._pend_long is None


def test_fixed_dollar_floor_refuses_a_stop_narrower_than_the_floor():
    passes = Execution(_cfg(exec_min_stop_mode="Fixed $", exec_min_stop_val=2.0))
    passes.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert passes._pend_long is not None

    refuses = Execution(_cfg(exec_min_stop_mode="Fixed $", exec_min_stop_val=5.0))
    refuses.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert refuses._pend_long is None


def test_atr_floor_refuses_nothing_until_the_atr_exists_then_measures_it():
    """Pine's `ta.rma` is NA until it has 14 values, and `slDist >= na` reads as false — so the
    warmup REFUSES rather than passes. Reproducing the direction matters: passing during warmup
    would place exactly the oversized order this guard exists to stop."""
    ex = Execution(_cfg(exec_min_stop_mode="x ATR(14)", exec_min_stop_val=1.0))
    _quiet_bars(ex, _seq_long_ready(), 13)
    assert ex._atr is None
    assert ex._pend_long is None          # warmup: floor unknown ⇒ refused

    _quiet_bars(ex, _seq_long_ready(), 1, start=13)
    assert abs(ex._atr - 2.0) < 1e-9      # 14 bars of a flat 2.00 true range
    assert ex._pend_long is not None      # 1 × ATR = 2.00 < the 3.82 stop ⇒ allowed


def test_atr_floor_refuses_when_the_multiple_exceeds_the_stop():
    ex = Execution(_cfg(exec_min_stop_mode="x ATR(14)", exec_min_stop_val=2.0))
    _quiet_bars(ex, _seq_long_ready(), 14)
    assert abs(ex._atr - 2.0) < 1e-9
    assert ex._pend_long is None          # 2 × ATR = 4.00 > the 3.82 stop ⇒ refused


def test_atr_follows_wilder_after_the_sma_seed():
    """Seed = the SMA of the first 14 true ranges, then `atr += (tr - atr) / 14`. Fed 14 flat
    2.00 bars and then one 12.00-range bar, Wilder gives 2 + (12 - 2)/14."""
    ex = Execution(_cfg(exec_min_stop_mode="x ATR(14)", exec_min_stop_val=1.0))
    _quiet_bars(ex, _seq_long_ready(), 14)
    ex.step(_sig(14, 108.5, 114.5, 102.5, 108.5), _seq_long_ready())
    assert abs(ex._atr - (2.0 + (12.0 - 2.0) / 14.0)) < 1e-9


def test_a_stop_refused_on_distance_is_recorded_as_blocked_code_7():
    """Pine reports the floor refusal as block code 7, last in the precedence order, so a
    setup refused on PRICE is countable in the lab's Blocked layer like every toggle refusal."""
    ex = Execution(_cfg(exec_min_stop_mode="% of price", exec_min_stop_val=5.0))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert [b.code for b in ex.blocks] == [7]
    assert ex.blocks[0].labels == ["Stop too tight"]
    assert ex.blocks[0].dir == 1


def test_code_7_sits_last_in_precedence_behind_a_toggle_refusal():
    """A setup refused by BOTH a toggle and the floor reports the toggle as primary — the Pine's
    `f_blkCode` returns the first blocker, and `codes[0]` must keep reconciling with it."""
    ex = Execution(_cfg(exec_longs=False,
                        exec_min_stop_mode="% of price", exec_min_stop_val=5.0))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert ex.blocks[0].codes == [1, 7]
    assert ex.blocks[0].code == 1


def test_warmup_refusal_places_no_order_and_tags_nothing():
    """The one place the Pine is asymmetric, reproduced deliberately: during the ATR warmup the
    entry is cancelled (`slDist >= na` is falsy) but `lBlkTight` (`slDist < na`) is falsy too, so
    no tag is written. Refusing to place while refusing to explain is the Pine's behaviour; the
    alternative — inventing a code 7 the Pine never emits — would break block-count parity."""
    ex = Execution(_cfg(exec_min_stop_mode="x ATR(14)", exec_min_stop_val=1.0))
    _quiet_bars(ex, _seq_long_ready(), 5)
    assert ex._pend_long is None
    assert ex.blocks == []


def test_the_bleg_fork_pins_the_floor_off_because_it_cannot_enforce_it():
    """`BLegExecution` overrides `_place_entries`, so the parent's floor check never runs there
    and its Pine has no such input. The pin stops a future parent default from silently claiming
    a guard this fork does not have."""
    from mpc_bleg.config import BLegConfig

    assert BLegConfig().exec_min_stop_mode == "Off"
