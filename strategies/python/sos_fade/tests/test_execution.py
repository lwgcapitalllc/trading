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

from sos_fade import SosFadeConfig, Execution, SeqState  # noqa: E402
from sos_fade.signals import Signals  # noqa: E402


def _cfg(**kw):
    # These fixtures arm via DIVERGENCE (_seq_long_ready sets sos_l_div), so pin the arm
    # source on regardless of the production default (which is now sweep-arm). This isolates
    # the execution mechanics under test from the arm-source default.
    # `exec_sl_level` is pinned for the same reason: the price fixtures put the stop at
    # fibo_p10 = 100.0 and the sizing / −1R assertions are hand-computed off that, so they must
    # not move when the shipped default does (it went 1.0 → 0.886 on 2026-07-27).
    # The dead-market floor is pinned OFF for the same reason: these fixtures feed 2-4 bars, so
    # ATR(14) is never seeded, and the floor REFUSES on an unseeded ATR by design ("cannot ask"
    # is not "measured quiet" - rule 1). Every one of these tests was written against a basis
    # where this gate did not exist; leaving it on would have them all assert that nothing
    # trades, which is not what any of them is about. `test_dead_market.py` turns it on and owns
    # the behaviour, including the unseeded-ATR case.
    base = dict(exec_req_fvg=False, exec_be_buf_tk=0.0, exec_risk_pct=10.0,
                exec_arm_div=True, exec_arm_sweep=False, exec_sl_level="1.0",
                exec_min_atr_pct=0.0)
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


def _seq_short_ready(sos_bar=1):
    """The short mirror of `_seq_long_ready` — used where a rule reads the DIRECTION and getting it
    backwards would be silent (the adverse extreme is the highest high on a short, not the lowest
    low), so a long-only fixture cannot see the bug."""
    return SeqState(
        l_stage=0, s_stage=4, l_sos_bar=None, s_sos_bar=sos_bar,
        l_half=False, l_618=False, s_half=True, s_618=True,
        l_poi=False, s_poi=False, l_fvg=False, s_fvg=False,
        sos_l_swp=False, sos_l_div=False, sos_s_swp=False, sos_s_div=True,
        new_sweep_l=False, new_div_l=False, new_sweep_s=False, new_div_s=False,
        retro_link_l=False, retro_link_s=False, s_arm_src="DIV",
    )


def _seq_short_dead():
    s = _seq_flat()
    s.sos_s_div = True
    s.s_arm_src = "DIV"
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
    """The sizing FORMULA: qty = equity x risk% / stop distance.

    🔴 **The capital is $100,000 and it used to be $1,000,000, which is not a tidy-up.** Since
    2026-09-02 the default account carries the VENUE CEILING — 100 lots of gold, measured on the
    live account — and at $1m this setup asks for 261.78 lots, so the number this test asserted
    was one the broker would reject. It was measuring the formula through a clamp that had
    nothing to do with the formula. Below the ceiling the two are the same thing, so the test now
    sits where its own subject is the only thing acting.
    ⚠ The ceiling itself is pinned by the test below rather than dodged.
    """
    ex = Execution(_cfg(exec_risk_pct=10.0), initial_capital=100_000.0)
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    # qty = equity*10% / (edge-sl) = 10000 / 3.82 = 2617.8 units = 26.18 lots, under the ceiling
    assert abs(ex._qty - (10_000.0 / 3.82)) < 1e-6


def test_the_venue_ceiling_clamps_a_size_the_broker_would_REJECT():
    """The same setup at $1,000,000, where the formula asks for more than the venue will take.

    🔴 **This is the case that made the old test red, kept as COVERAGE instead of deleted.** The
    formula wants 100,000 / 3.82 = 26,178 oz = 261.78 lots; PU Prime's measured ceiling on
    `XAUUSD.p` is 100 lots, and an order above it is not filled small, it is REJECTED — so a
    replay that books 261.78 lots is describing an account nobody can have.

    ⚠ It clamps rather than refusing, and only because this is the DECISION seam: the emulator
    books the capped size as its own, so the two sides never grade different R. Clamping at the
    ORDER is still wrong — see `algos/shared/order_sizing.py`, which refuses.

    MUTATION: BOTH WATCHED. `max_lots=None` on the default `SoloAccount` reds it (the formula's
    full 26,178 oz comes back), and so does a ceiling of 200 lots. ⚠ Neither touches the test
    above, which sits under any of those ceilings — that is the point of the pair: one measures
    the formula, the other measures the clamp, and no single change can move both.
    """
    ex = Execution(_cfg(exec_risk_pct=10.0), initial_capital=1_000_000.0)
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    assert ex._qty < (100_000.0 / 3.82)  # the formula's answer was refused
    # 🔴 The measured numbers are written out rather than imported from `account.py`. Importing
    # them would make this test agree with whatever the ceiling becomes, so a ceiling raised by
    # accident would stay green — and the ceiling is a MEASURED fact about the venue (100 lots,
    # read off account 700152905), not a preference. Moving it should have to come here and say so.
    assert ex._qty == 100.0 * 100.0  # 100 lots x 100 oz per lot


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


def test_the_entry_bar_cannot_stage_the_stop():
    """Regression — `indicators/docs/BUG_exit_fill_price_mismatch.md`.

    A resting limit is reached by price coming to it from the WRONG side: this buy limit at
    103.82 is filled on the way down, so the entry bar's HIGH is where the market was before
    the trade existed. Staging off it lifted the stop to breakeven (entry + buf = ABOVE the
    entry) on a trade that had gone nowhere — a stop already through the market, which fills
    every leg at the next bar's open at a price that is neither the stop nor any target.

    Entry bar opens at 105.40, ABOVE TP1 (105.0), dips to 103.5 filling the limit, closes at
    104.0. Nothing about that is favourable to the trade, so nothing may stage.
    """
    ex = Execution(_cfg(exec_be_buf_tk=30.0, mintick=0.01), initial_capital=10_000.0)
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())          # place the limit
    dec1 = ex.step(_sig(1, 105.40, 105.50, 103.50, 104.00), _seq_long_ready())

    assert abs([f for f in dec1.fills if f.kind == "entry"][0].price - 103.82) < 1e-9
    assert ex._stage == 0                       # the entry bar's high reached TP1 — irrelevant
    assert abs(dec1.stop - 100.0) < 1e-9        # still the real SL, not entry + 0.30

    # ...and an ordinary next bar must NOT close the trade.
    dec2 = ex.step(_sig(2, 103.50, 104.10, 103.40, 103.60), _seq_flat())
    assert [f for f in dec2.fills if f.kind == "exit"] == []
    assert ex._pos_dir == 1

    # The bar AFTER the fill stages normally — the rule is "not on the fill bar", not "never".
    dec3 = ex.step(_sig(3, 104.0, 105.20, 103.9, 105.10), _seq_flat())
    assert ex._stage == 1
    assert abs(dec3.stop - (103.82 + 0.30)) < 1e-9


def test_max_fav_starts_at_the_entry_price_not_the_entry_bars_extreme():
    """Pine `lMaxFav := lEntry`. The high-water mark drives the runner trail and the
    "One trail step behind" floor, so seeding it from the entry bar's high hands the trail a
    peak the trade never made — the same contamination as the staging bug above."""
    ex = Execution(_cfg(exec_be_buf_tk=30.0, mintick=0.01))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 105.40, 105.50, 103.50, 104.00), _seq_long_ready())      # fill @103.82
    assert ex._max_fav == 103.82                # not the bar's 105.50

    ex.step(_sig(2, 104.0, 104.60, 103.9, 104.5), _seq_flat())              # now it tracks
    assert ex._max_fav == 104.60


def test_entry_bar_excursion_keeps_the_adverse_side_and_drops_the_favourable_one():
    """The asymmetry is real, not a rounding-off: a buy limit fills on the way DOWN, so the
    entry bar's LOW is reached AFTER the fill and is a genuine adverse excursion, while its
    HIGH is the approach. Reporting-only (no decision reads these), but reading the approach
    as "the trade went into profit" is exactly what sent the original bug report down the
    wrong path."""
    ex = Execution(_cfg(exec_be_buf_tk=30.0, mintick=0.01))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 105.40, 105.50, 103.50, 104.00), _seq_long_ready())      # fill @103.82
    assert ex._ext_high == 103.82               # the 105.50 approach is NOT favourable
    assert ex._ext_low == 103.50                # the dip past the fill IS adverse


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


# --- the RETRACE a miss was waiting on (`zone_time_ms` / `zone_turn_ms`, 2026-08-08) ---
# `time_ms` is the bar the setup DIED. On the reference run that is a median 17 and up to 717 bars
# after the retrace, leaving price a median $22 from the setup's own edge — so a consumer asking
# "which candle turned this" has to be told, not left to derive it. The band here is fiboP2 105.0
# (0.5) to fiboP6 101.14 (0.886).

def test_a_miss_records_the_retrace_it_was_waiting_on_not_just_its_death():
    ex = Execution(_cfg())
    # ⚠ Every bar stays ABOVE the 103.82 entry edge — dip under it and the limit FILLS, the setup
    # becomes a trade and there is no miss to inspect at all.
    ex.step(_sig(0, 104.6, 104.9, 104.5, 104.7), _seq_long_ready())   # in the band
    ex.step(_sig(1, 104.3, 104.4, 103.9, 104.0), _seq_long_ready())   # deeper — the turn
    ex.step(_sig(2, 104.3, 104.8, 104.2, 104.6), _seq_long_ready())
    ex.step(_sig(3, 104.5, 104.9, 104.4, 104.7), _seq_long_dead())
    m = ex.misses[0]
    assert m.time_ms == 3 * 900_000, "the record still marks where the setup died"
    assert (m.zone_time_ms, m.zone_turn_ms) == (0, 1 * 900_000)


def test_the_visit_is_measured_off_the_BAND_not_off_the_latch():
    """🔴 The one that matters. `zone_hit` is `l_half or l_618` — a LATCH: once price tags 0.5 it
    stays true for every bar until the leg resets. Tracking the visit off it made the retrace read
    as 717 bars on a real run and painted a quarter of a week of chart.

    Here price tags the band, LEAVES it upwards for two bars, and comes back deeper. Off the latch
    that is one 5-bar visit whose extreme is the final low; off the band it is two visits and the
    deeper one wins — same answer for the turn, but the SPAN starts at bar 3, not bar 0.

    ⚠ Watch it go red by testing `zone_hit` instead of the bar's own range."""
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.7, 104.9, 104.6, 104.8), _seq_long_ready())     # in the band
    ex.step(_sig(1, 106.0, 106.5, 105.9, 106.2), _seq_long_ready())     # ABOVE 0.5 — out
    ex.step(_sig(2, 106.0, 106.5, 105.2, 106.2), _seq_long_ready())     # still out
    ex.step(_sig(3, 104.6, 104.8, 104.2, 104.4), _seq_long_ready())     # back in, deeper
    ex.step(_sig(4, 104.2, 104.3, 103.9, 104.0), _seq_long_ready())     # the turn
    ex.step(_sig(5, 104.5, 104.9, 104.4, 104.7), _seq_long_dead())
    m = ex.misses[0]
    assert (m.zone_time_ms, m.zone_turn_ms) == (3 * 900_000, 4 * 900_000)


def test_the_DEEPEST_visit_is_the_one_reported():
    """A setup can tag the zone, leave, and come back — those are different retraces, and the one
    worth reporting is the one that came closest to filling. The first visit here is shallow."""
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.8, 104.95, 104.7, 104.9), _seq_long_ready())    # shallow visit
    ex.step(_sig(1, 106.0, 106.5, 105.9, 106.2), _seq_long_ready())     # out
    ex.step(_sig(2, 104.4, 104.6, 103.9, 104.1), _seq_long_ready())     # deep visit
    ex.step(_sig(3, 104.5, 104.9, 104.4, 104.7), _seq_long_dead())
    assert ex.misses[0].zone_turn_ms == 2 * 900_000


def test_a_SHORT_setups_turn_is_its_HIGHEST_high():
    """A short retraces UP into the band, so the deepest point against it is the high. Getting this
    backwards would report the shallowest bar of every short as its turn."""
    ex = Execution(_cfg(exec_shorts=True))
    ex.step(_sig(0, 102.0, 102.5, 101.9, 102.2, dir=-1), _seq_short_ready())
    ex.step(_sig(1, 102.0, 104.9, 101.9, 104.5, dir=-1), _seq_short_ready())   # highest
    ex.step(_sig(2, 102.0, 102.5, 101.9, 102.2, dir=-1), _seq_short_ready())
    ex.step(_sig(3, 102.0, 102.5, 101.9, 102.2, dir=-1), _seq_short_dead())
    assert ex.misses[0].zone_turn_ms == 1 * 900_000


def test_a_setup_that_never_reached_the_zone_records_NO_retrace():
    """`None` means price never got there. A fallback to `time_ms` would put the answer back exactly
    where it was wrong, and a 0 would anchor it on the epoch."""
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_stage2())
    ex.step(_sig(1, 104.0, 104.5, 103.9, 104.2), _seq_long_dead())
    m = ex.misses[0]
    assert m.met == 2 and (m.zone_time_ms, m.zone_turn_ms) == (None, None)


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
#
# Method 3 sits at the BOTTOM of the 2026-08-02 cascade, so every test here has to switch
# rules 2 and 3 off to reach it. `_m3` says that once instead of four times.

def _m3(**kw):
    return _cfg(exec_req_fvg=True, exec_fib_overlap=False, exec_fib_deep_edge=False,
                exec_fib_nearest=False, **kw)


def test_deep_fib_reprices_a_deep_long_gap_to_the_nearest_shallower_fib():
    """Method 3 ON: a gap floating deep in the zone (near edge below 0.618) rests at the
    fib just SHALLOWER, not the gap edge. Gap top 102.5 sits between 0.786 and 0.702, so
    the limit re-prices to 0.702 = 102.8 (the level price reaches first)."""
    fvg = [(102.5, 101.5, True, 0)]   # (top, bot, is_bull, born) — deep, between 0.786 and 0.702
    ex_on = Execution(_m3(exec_deep_fib=True))
    le, _ = ex_on._entry_edges(_sig(0, 104, 104.5, 103.9, 104.2, fvgs=fvg), _seq_flat())
    assert abs(le - 102.8) < 1e-9          # 0.702, not the 102.5 gap edge


def test_deep_fib_off_keeps_the_gap_edge_entry():
    """Same gap, EVERY snap rule OFF: unchanged — the limit rests at the gap's own near edge."""
    fvg = [(102.5, 101.5, True, 0)]
    ex_off = Execution(_m3(exec_deep_fib=False))
    le, _ = ex_off._entry_edges(_sig(0, 104, 104.5, 103.9, 104.2, fvgs=fvg), _seq_flat())
    assert abs(le - 102.5) < 1e-9          # min(top, 0.5) = the gap edge


def test_deep_fib_leaves_a_shallow_gap_unchanged():
    """A gap whose near edge is SHALLOWER than 0.618 (top 104.0, between 0.5 and 0.618) is
    not a Method 3 case — it enters at the gap edge whether the toggle is on or off."""
    fvg = [(104.0, 101.5, True, 0)]
    on = Execution(_m3(exec_deep_fib=True))._entry_edges(
        _sig(0, 104, 104.5, 103.9, 104.2, fvgs=fvg), _seq_flat())[0]
    off = Execution(_m3(exec_deep_fib=False))._entry_edges(
        _sig(0, 104, 104.5, 103.9, 104.2, fvgs=fvg), _seq_flat())[0]
    assert abs(on - 104.0) < 1e-9 and abs(off - 104.0) < 1e-9


def _bear_sig(fvg):
    """Short-side leg: 0.5=105 0.618=106.18 0.702=107.2 0.786=108.0 0.886=108.86."""
    return _sig(0, 106, 106.1, 105.5, 105.8, dir=-1, fvgs=fvg,
                fibo_p2=105.0, fibo_p3=106.18, fibo_p4=107.2, fibo_p5=108.0,
                fibo_p6=108.86, fibo_p1=103.82, fibo_p7=100.0, fibo_p10=110.0)


def test_deep_fib_reprices_a_deep_short_gap():
    """Short mirror: near edge is the gap BOTTOM. A gap bottom 107.5 (between 0.702 and
    0.786) re-prices to 0.702 = 107.2."""
    sig = _bear_sig([(108.0, 107.5, False, 0)])
    _, se = Execution(_m3(exec_deep_fib=True))._entry_edges(sig, _seq_flat())
    assert abs(se - 107.2) < 1e-9


# ------------------------------------------- the 2026-08-02 entry model (rules 1-3) ----
# Long leg fibs again: 0.5=105.0  0.618=103.82  0.702=102.8  0.786=102.0  0.886=101.14.
# A gap running 102.7 -> 102.05 FLOATS between 0.702 and 0.786 — its body holds no level —
# and is deliberately NOT equidistant: 0.05 down to 0.786, 0.10 up to 0.702. That asymmetry
# is what separates rule 3 from Method 3, which only ever looks upward.

_FLOAT_GAP = [(102.7, 102.05, True, 0)]


def _entry(cfg, fvg=None, sig=None):
    return Execution(cfg)._entry_edges(sig or _sig(0, 104, 104.5, 103.9, 104.2,
                                                   fvgs=fvg or _FLOAT_GAP), _seq_flat())[0]


def test_nearest_fib_takes_the_DEEPER_level_when_it_is_closer():
    """Rule 3, the shipped default, and the whole reason it exists: the level BELOW the gap
    is 0.05 away while the one above is 0.10, so the limit rests at 0.786. Method 3 would
    take 0.702 however far away it was — that is the bug Aaron caught on 30 Jul 2026."""
    assert abs(_entry(_cfg(exec_req_fvg=True)) - 102.0) < 1e-9
    assert abs(_entry(_m3(exec_deep_fib=True)) - 102.8) < 1e-9   # the old answer, same gap


def test_nearest_fib_takes_the_SHALLOWER_level_when_that_one_is_closer():
    """The other half of rule 3 — and a tie goes to the shallower level, because that is the
    one price reaches first, so an equal price is bought without giving up the fill."""
    near_top = [(102.75, 102.3, True, 0)]     # 0.05 up to 0.702, 0.30 down to 0.786
    assert abs(_entry(_cfg(exec_req_fvg=True), near_top) - 102.8) < 1e-9
    tie = [(102.7, 102.1, True, 0)]           # 0.10 each way
    assert abs(_entry(_cfg(exec_req_fvg=True), tie) - 102.8) < 1e-9


def test_deep_edge_rests_inside_the_gap_and_overrides_rule_3():
    """Rule 2 rests at the gap's OWN far edge — inside the imbalance, so price entering the
    gap at all fills you — and it wins over rule 3 even with rule 3 also on."""
    cfg = _cfg(exec_req_fvg=True, exec_fib_deep_edge=True, exec_fib_nearest=True)
    assert abs(_entry(cfg) - 102.05) < 1e-9


def test_deep_edge_falls_back_when_the_gap_reaches_the_band_FLOOR():
    """A gap whose far edge clamps onto 0.886 would rest ON the stop — a zero stop distance
    and a cancelled order. Rule 2 sends it to the level above instead (0.786)."""
    on_the_floor = [(101.8, 101.0, True, 0)]      # far clamps to 0.886 = 101.14
    cfg = _cfg(exec_req_fvg=True, exec_fib_deep_edge=True)
    assert abs(_entry(cfg, on_the_floor) - 102.0) < 1e-9


def test_overlap_rests_on_the_SHALLOWEST_level_inside_the_gap_body():
    """Rule 1 fires only on a gap whose BODY holds a level, and takes the shallowest of them
    — the one price reaches first. It is independent of rules 2/3, so it wins with both on."""
    holds_two = [(103.0, 102.0, True, 0)]         # body holds 0.702 and 0.786
    cfg = _cfg(exec_req_fvg=True, exec_fib_overlap=True)
    assert abs(_entry(cfg, holds_two) - 102.8) < 1e-9
    # …and this is the case rule 1 exists for. Rule 3 does not ask whether the body holds a
    # level, so on its own it snaps this gap to 0.618 — ABOVE the whole imbalance, filling
    # before price has traded into the thing the setup was justified by.
    assert abs(_entry(_cfg(exec_req_fvg=True), holds_two) - 103.82) < 1e-9


def test_no_rule_ever_snaps_an_entry_onto_0_886():
    """0.886 is the STOP. An entry resting there has a stop distance of zero, `dist > 0`
    fails, the order is cancelled and the setup vanishes with no trade and no block tag — so
    every scan stops at 0.786. This gap floats between 0.786 and 0.886, where the nearest
    level below it IS 0.886, and no toggle combination may reach it."""
    between = [(101.8, 101.3, True, 0)]
    for cfg in (_cfg(exec_req_fvg=True),                                    # rule 3
                _cfg(exec_req_fvg=True, exec_fib_overlap=True),             # rule 1 + 3
                _m3(exec_deep_fib=True)):                                   # Method 3
        assert _entry(cfg, between) > 101.14


def test_the_entry_model_mirrors_on_a_bear_leg():
    """Short mirror of rule 3: gap 107.3 -> 107.95 floats between 0.702 (107.2) and 0.786
    (108.0); 0.05 deeper vs 0.10 shallower, so the deeper level 0.786 wins."""
    sig = _bear_sig([(107.95, 107.3, False, 0)])
    _, se = Execution(_cfg(exec_req_fvg=True))._entry_edges(sig, _seq_flat())
    assert abs(se - 108.0) < 1e-9


# ------------------------------------------------ the pre-zone gate (execFvgPreZone) ----

def test_pre_zone_gate_refuses_a_gap_the_retrace_itself_printed():
    """A gap born ON or AFTER the bar price first tagged 0.5 is the retrace manufacturing its
    own confluence. STRICTLY earlier survives: born on the zone-entry bar was still forming
    as price arrived, so it was not present."""
    ex = Execution(_cfg(exec_req_fvg=True, exec_fvg_pre_zone=True))
    for born, kept in ((9, True), (10, False), (11, False)):
        sig = _sig(0, 104, 104.5, 103.9, 104.2, fibo_half_bar=10,
                   fvgs=[(102.7, 102.05, True, born)])
        assert (ex._entry_edges(sig, _seq_flat())[0] is not None) is kept, born


def test_pre_zone_gate_is_inert_when_off_and_before_the_zone_is_reached():
    """Off = the original condition exactly. And with the toggle ON but price not yet in the
    zone (`fibo_half_bar` None) every gap trivially pre-dates a moment that has not happened,
    so nothing is refused — that is what keeps the gate from suppressing the arm itself."""
    late = [(102.7, 102.05, True, 99)]
    assert _entry(_cfg(exec_req_fvg=True, exec_fvg_pre_zone=False),
                  fvg=late, sig=_sig(0, 104, 104.5, 103.9, 104.2,
                                     fibo_half_bar=10, fvgs=late)) is not None
    assert _entry(_cfg(exec_req_fvg=True, exec_fvg_pre_zone=True),
                  fvg=late, sig=_sig(0, 104, 104.5, 103.9, 104.2,
                                     fibo_half_bar=None, fvgs=late)) is not None


# ----------------------------------------------- the deep-entry stop (execSlDeep) ----

def test_sl_deep_moves_the_stop_to_the_leg_origin_only_for_a_deep_fill():
    """AT OR PAST 0.786 -> fib 1.0 (the leg origin, the only level beyond the whole entry
    band). 0.702 and shallower keeps the chosen level. The test is inclusive at 0.786 on
    purpose: rule 3 assigns that fib to the edge directly, so the comparison is exact."""
    sig = _sig(0, 104, 104.5, 103.9, 104.2)
    on = Execution(_cfg(exec_sl_level="0.886", exec_sl_deep=True))
    assert on._sl_anchor(sig, 102.0, True) == sig.fibo_p10     # exactly 0.786 -> 1.0
    assert on._sl_anchor(sig, 101.5, True) == sig.fibo_p10     # deeper still -> 1.0
    assert on._sl_anchor(sig, 102.8, True) == sig.fibo_p6      # 0.702 -> the chosen level
    off = Execution(_cfg(exec_sl_level="0.886", exec_sl_deep=False))
    assert off._sl_anchor(sig, 102.0, True) == sig.fibo_p6     # toggle off: never moves


def test_sl_deep_mirrors_on_a_bear_leg_and_treats_a_missing_edge_as_shallow():
    bear = _bear_sig([])
    on = Execution(_cfg(exec_sl_level="0.886", exec_sl_deep=True))
    assert on._sl_anchor(bear, 108.0, False) == bear.fibo_p10  # exactly 0.786 -> 1.0
    assert on._sl_anchor(bear, 107.2, False) == bear.fibo_p6   # 0.702 -> the chosen level
    # An unknown edge must never silently WIDEN the stop.
    assert on._sl_anchor(bear, None, False) == bear.fibo_p6


# ---------------------------------------------- runner trail + TP2 stop floor ----
# The exit levers added to `sos_fade_strategy.pine` 2026-07-25. All four tests drive the same
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
    matching `sos_fade_strategy.pine` / `sos_fade_strategy_export.pine`. Toggle-default parity with the
    Pine is a hard requirement (see config.py's docstring), and this value is load-bearing:
    it moves the stop, so a silent drift changes every trade's size and R. The B-LEG fork
    pins "1.0" instead, because ITS Pine still ships 1.0."""
    from b_leg.config import BLegConfig

    assert SosFadeConfig().exec_sl_level == "0.886"
    assert BLegConfig().exec_sl_level == "1.0"


# ------------------------------------------- the Custom SL level (2026-08-02) -----------------
# The fixtures are a BULL leg anchored ash = 110.0 / asl = 100.0, so a ratio v prices at
# 110 - 10v: 0.886 -> 101.14 (= fibo_p6), 0.9 -> 101.0, 1.0 -> 100.0 (= fibo_p10). The entry edge
# is fibo_p3 = 103.82 (exec_req_fvg off), which is what every stop distance below is measured to.

def test_a_custom_ratio_prices_a_level_the_dropdown_never_offered():
    """The whole point: 0.9 sits BETWEEN the 0.886 default and the 1.0 leg origin, and no
    combination of the five choices can express it."""
    ex = Execution(_cfg(exec_sl_level="Custom", exec_sl_custom=0.9))
    sig = _sig(0, 104.0, 104.5, 103.9, 104.2)

    assert abs(ex._sl_anchor(sig) - 101.0) < 1e-12
    assert sig.fibo_p10 < ex._sl_anchor(sig) < sig.fibo_p6   # deeper than 0.886, shallower than 1.0


def test_custom_at_a_dropdown_value_is_the_SAME_price_to_the_last_bit():
    """Switching the mode to Custom without moving the number must be a no-op — that is what makes
    the change safe to make on a live config. Exact float equality is the assertion on purpose:
    `fib_level` is the engine's own helper, so the Custom branch walks the identical IEEE-754 path
    the fib engine walked to produce fiboP6, and `_TOUCH_EPS`-scale drift would be a real defect.
    Checked on a BEAR leg too, where the anchor arithmetic is the mirror (asl + range*v)."""
    sig = _sig(0, 104.0, 104.5, 103.9, 104.2)
    assert Execution(_cfg(exec_sl_level="Custom", exec_sl_custom=0.886))._sl_anchor(sig) \
        == Execution(_cfg(exec_sl_level="0.886"))._sl_anchor(sig)
    assert Execution(_cfg(exec_sl_level="Custom", exec_sl_custom=1.0))._sl_anchor(sig) \
        == Execution(_cfg(exec_sl_level="1.0"))._sl_anchor(sig)

    # The shared fixture hardcodes BULL-leg fib prices, so a bear leg needs its own coherent set:
    # same anchors, mirrored arithmetic (asl + range*v instead of ash - range*v).
    bear = _sig(0, 104.0, 104.5, 103.9, 104.2, dir=-1,
                fibo_p1=103.82, fibo_p2=105.0, fibo_p3=106.18, fibo_p4=107.02,
                fibo_p5=107.86, fibo_p6=108.86, fibo_p7=100.0, fibo_p10=110.0)
    assert Execution(_cfg(exec_sl_level="Custom", exec_sl_custom=0.786))._sl_anchor(bear) \
        == Execution(_cfg(exec_sl_level="0.786"))._sl_anchor(bear)
    assert Execution(_cfg(exec_sl_level="Custom", exec_sl_custom=0.9))._sl_anchor(bear) > bear.fibo_p6


def test_a_custom_stop_sizes_the_position_off_its_own_distance():
    """The anchor being right is not enough — it has to reach SIZING. `qty = risk$ / dist`, so a
    stop the operator moved and a position size that did not follow it is the failure that costs
    money quietly. Entry 103.82, custom stop 101.0 ⇒ dist 2.82 ⇒ $1,000 of risk buys 354.6 oz."""
    ex = Execution(_cfg(exec_sl_level="Custom", exec_sl_custom=0.9))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())

    pend = ex._pend_long
    assert pend is not None
    assert abs(pend.sl - 101.0) < 1e-12
    assert abs(pend.qty - (ex.equity * 10.0 / 100.0) / (103.82 - 101.0)) < 1e-9


def test_a_custom_ratio_outside_zero_to_one_is_refused_at_construction():
    """LOUDLY, and not by falling through to fib 1.0 the way an unrecognised dropdown value does.
    A number a human typed that silently becomes a different stop would run a whole backtest
    against a level nobody chose and report it as theirs."""
    import pytest

    for bad in (0.0, -0.5, 1.2, 2.0):
        with pytest.raises(ValueError, match="exec_sl_custom"):
            SosFadeConfig(exec_sl_level="Custom", exec_sl_custom=bad)


def test_a_custom_ratio_is_only_validated_when_the_mode_reads_it():
    """An optimizer may sweep `exec_sl_custom` while `exec_sl_level` is a fixed level — every combo
    is then identical and the sweep is wasted, but it is not an error, and raising would kill an
    otherwise valid grid on a param the run never reads."""
    cfg = SosFadeConfig(exec_sl_level="0.886", exec_sl_custom=99.0)

    assert cfg.exec_sl_custom == 99.0
    ex = Execution(_cfg(exec_sl_level="0.886", exec_sl_custom=99.0))
    assert ex._sl_anchor(_sig(0, 104.0, 104.5, 103.9, 104.2)) == 101.14   # still fiboP6


def test_the_custom_default_is_the_shipped_level_so_selecting_it_moves_nothing():
    assert SosFadeConfig().exec_sl_custom == 0.886
    assert SosFadeConfig().exec_sl_level == "0.886"


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


def test_off_is_still_inert_for_anyone_reproducing_an_old_run():
    """"Off" must stay inert — it is what every result measured before 2026-08-05 was taken at, so
    selecting it has to reproduce those runs exactly.

    This used to also assert that "Off" was the DEFAULT. It is not any more (see the test below),
    and the two claims are worth keeping apart: *this* one is about the mode being a faithful
    no-op, which is what makes an old run reproducible, and it stays true forever.
    """
    ex = Execution(_cfg(exec_min_stop_mode="Off"))
    dec = ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert dec.long_armed is True
    assert ex._pend_long is not None


def test_the_shipped_default_is_the_measured_guard_not_off():
    """🔴 DEFAULT CHANGED 2026-08-05: "Off" → "% of price" 0.08 (Aaron's call).

    Swept over 186,220 M15 bars, one real replay per config: baseline 183 trades / +134.75R,
    0.08 → 181 / +136.75R, 0.10 → 176 / +132.92R, 0.15 → −25R. A small floor GAINS R because the
    three tightest stops in 7.9 years were all full −1.00R losers.

    ⚠ **The consequence this test exists to make loud: a run replayed at DEFAULTS from today is
    not comparable to one replayed at defaults before it.** Every A+ figure in this folder measured
    at "Off" describes a different configuration. Pin the mode explicitly when reproducing one.

    ⚠ It must stay in lockstep with `strategies/tradingview/sos_fade_strategy.pine`'s `execMinStopMode` /
    `execMinStopVal` defaults and its export mirror — toggle parity is a hard requirement, and a
    default that differs between the two silently makes `compare_strategy.py` compare two
    strategies whenever an export predates the column.
    """
    cfg = SosFadeConfig()
    assert cfg.exec_min_stop_mode == "% of price"
    assert cfg.exec_min_stop_val == 0.08


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
    from b_leg.config import BLegConfig

    assert BLegConfig().exec_min_stop_mode == "Off"


# ------------------------------------------------- the trade's own fib leg ------
# Reporting-only, exactly like the excursion fields: nothing reads a recorded ladder back, so
# these tests pin the RECORD, never a decision.

def test_a_filled_trade_records_the_fib_leg_it_was_priced_off():
    """The whole ladder, at the prices the strategy read, on the bar the order was placed."""
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())      # place
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())      # fill @103.82
    ex.step(_sig(2, 103.8, 103.9, 99.0, 99.5), _seq_flat())              # stop out -> closed
    t = ex.trades[0]
    assert t.fib is not None
    assert t.fib.levels == [
        (0.0, 110.0), (0.382, 106.18), (0.5, 105.0), (0.618, 103.82),
        (0.702, 102.8), (0.786, 102.0), (0.886, 101.14), (1.0, 100.0),
    ]


def test_the_recorded_fib_is_the_one_the_ORDER_rested_on_not_the_one_at_the_fill():
    """A fib is live — it keeps extending while the limit sits there. Reading it again at the fill
    would report a leg the order was never priced against, and the stop/targets on that same trade
    would then belong to a different ladder from the one drawn beside them."""
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())      # place off the 110/100 leg
    # The leg extends before the limit fills: same setup, every level moved.
    moved = dict(fibo_p1=126.18, fibo_p2=125.0, fibo_p3=123.82, fibo_p4=122.8,
                 fibo_p5=122.0, fibo_p6=121.14, fibo_p7=130.0, fibo_p10=120.0,
                 fibo_ash=130.0, fibo_asl=120.0)
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0, **moved), _seq_long_ready())   # fill @103.82
    ex.step(_sig(2, 103.8, 103.9, 99.0, 99.5, **moved), _seq_flat())           # stop out
    assert ex.trades[0].fib.levels[0] == (0.0, 110.0)      # the leg at PLACEMENT, not 130.0
    assert ex.trades[0].fib.levels[-1] == (1.0, 100.0)


def test_the_fib_start_is_the_bar_the_LEG_began_not_the_entry():
    """The x-span the chart draws from. A ladder starting at the fill would hide the retracement
    that produced it, which is the thing the layer exists to show."""
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2, fibo_ash_ms=7_000, fibo_asl_ms=3_000),
            _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0, fibo_ash_ms=7_000, fibo_asl_ms=3_000),
            _seq_long_ready())
    ex.step(_sig(2, 103.8, 103.9, 99.0, 99.5), _seq_flat())
    assert ex.trades[0].fib.start_ms == 3_000     # the EARLIER anchor — where the leg started


def test_an_incompletely_priced_fib_is_recorded_as_NOTHING_rather_than_partially():
    """All-or-nothing: a ladder missing a rung would draw seven levels and silently omit the
    eighth, which reads as 'this trade had no 0.786' instead of 'this record is incomplete'."""
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2, fibo_p5=None), _seq_long_ready())
    assert ex._pend_long is not None and ex._pend_long.fib is None


def test_the_secondary_reentry_records_no_A_plus_ladder():
    """The 1m sniper rests at a retrace of its OWN tight shift leg, which is a different fib. Absent
    is the honest answer; borrowing the 15m ladder would label the re-entry with a leg it was
    never priced on."""
    from types import SimpleNamespace

    ex = Execution(_cfg())
    arm = SimpleNamespace(l_armed=True, l_edge=103.0, l_sl=102.0, l_tp1=105.0, l_tp2=106.0,
                          l_leg=1, s_armed=False, s_edge=None, s_sl=None,
                          s_tp1=None, s_tp2=None, s_leg=None)
    assert ex._secondary_pending(arm).fib is None


# ------------------------------------------------------- scale-in reporting -----
def test_a_filled_add_is_recorded_on_the_closed_trade():
    """The closed trade must SAY it added, because nothing else in its record can.

    `qty` is the BASE size and `legs` is the exit ladder, so a trade that bought more after the
    entry looks — in every stored field — exactly like one that did not. That is not cosmetic:
    on run 295a6ff29d21 eight trades booked exactly $0.00 with the exit BELOW the entry on a
    short, and the lot that took the profit back appeared nowhere in the run, the equity curve or
    the chart. It reads as a bug in the exit code and is not one.
    """
    cfg = _cfg(exec_scale_in=True, exec_scale_mode="Trail", exec_scale_max_adds=1)
    ex = Execution(cfg)
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())     # place
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())     # fill @103.82
    base_qty = ex._qty

    # bar 2 clears TP1 (105) and TP2 (106.18): stage 2, floor = TP1 price = 105, and the add is
    # PLACED against that stop, sized off the bar's close (106.5).
    ex.step(_sig(2, 104.0, 107.0, 103.9, 106.5), _seq_flat())
    assert ex._add_pending is not None and not ex._add_lots      # placed, nothing bought yet

    # bar 3 opens where bar 2 closed, so the market add fills at exactly the price it was sized
    # against — then price falls back into the floor and the whole position leaves at 105.
    ex.step(_sig(3, 106.5, 106.6, 104.9, 105.0), _seq_flat())
    assert ex._pos_dir == 0 and len(ex.trades) == 1
    t = ex.trades[0]

    assert len(t.adds) == 1, "the add filled and the trade does not record it"
    lot = t.adds[0]
    assert abs(lot["price"] - 106.5) < 1e-9 and lot["qty"] > 0
    assert lot["ms"] == 3 * 900_000


def test_the_pnl_of_a_scaled_trade_reconciles_only_when_every_add_lot_is_read():
    """The identity in `Trade`'s docstring, and the exact case it was wrong about.

    Sized so the add's worst case equals the profit the stop had already locked (that IS the
    scale-in rule), the trade closes at EXACTLY flat — a real winner that banks nothing. The
    base-only arithmetic a reader would try first says it made money, and it is the `adds` ledger
    that closes the gap. Both halves are asserted: drop `adds` from the record and the second one
    is unprovable.
    """
    # `exec_scale_cap_x = 2` is the run's own setting and it matters: at the default 0.5 the cap
    # binds first, the add is smaller than the offsetting size, and the trade still nets a profit.
    # The exact-flat outcome is what the UNCAPPED affordability rule produces.
    cfg = _cfg(exec_scale_in=True, exec_scale_mode="Trail", exec_scale_max_adds=1,
               exec_scale_cap_x=2.0)
    ex = Execution(cfg)
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    ex.step(_sig(2, 104.0, 107.0, 103.9, 106.5), _seq_flat())
    ex.step(_sig(3, 106.5, 106.6, 104.9, 105.0), _seq_flat())
    t = ex.trades[0]
    pv = cfg.point_value

    base_only = (t.exit_price - t.entry_price) * t.dir * t.qty * pv
    assert base_only > 0, "the base leg exited in profit — that is what makes the $0 confusing"
    assert abs(t.pnl_usd) < 1e-6, "the add hands back exactly what the stop locked"

    whole = base_only + sum(
        (t.exit_price - a["price"]) * t.dir * a["qty"] * pv for a in t.adds
    )
    assert abs(whole + t.costs_usd - t.pnl_usd) < 1e-6


def test_a_trade_that_never_added_carries_an_empty_add_ledger():
    """No add, no lots — an invented entry would be worse than none, and `exec_scale_in` is OFF by
    default, so this is what every trade of every other run must look like."""
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    ex.step(_sig(2, 100.5, 101.0, 99.5, 99.8), _seq_flat())
    assert ex.trades[0].adds == []


# ── scale-in TAKE PROFIT (`exec_scale_tp_mode`, 2026-08-19) ──────────────────────────────
# Fixture shape shared by all of these, and it is the one the add tests above establish:
#   bar 0 places, bar 1 fills the base @103.82, bar 2 clears TP1 (105) and TP2 (106.18) so the
#   trade reaches stage 2 and PLACES an add sized off that bar's close, bar 3 opens at 106.5
#   and the market add FILLS there. So from bar 4 on, `_add_last_px` is 106.5 and the only base
#   bracket left is the runner, stopped at the TP1-price floor of 105.
#
# 🔴 THE TARGET IS RESTED AT A BAR'S CLOSE AND TRADES ON THE NEXT BAR, so every test here
# needs TWO bars: one where the level is visible (the order goes on), one where price reaches
# it (the order fills). Reading it from the live bar instead is the bug these were rewritten
# for — see `test_a_target_swept_by_the_filling_bar_still_fills`.

def _scaled_to_bar3(**cfgkw):
    """Drive a long to 'one add filled at 106.5, runner still open'. Returns (ex, base_qty)."""
    cfg = _cfg(exec_scale_in=True, exec_scale_mode="Trail", exec_scale_max_adds=1, **cfgkw)
    ex = Execution(cfg)
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    base_qty = ex._qty
    ex.step(_sig(2, 104.0, 107.0, 103.9, 106.5), _seq_flat())
    ex.step(_sig(3, 106.5, 106.8, 106.0, 106.5), _seq_flat())
    assert len(ex._adds) == 1 and abs(ex._add_last_px - 106.5) < 1e-9, "fixture did not add"
    return ex, base_qty


def _atp(ex):
    return [g for g in ex._legs if g["reason"].endswith("-ATP")]


def test_ride_never_banks_the_adds_however_far_price_runs():
    """The control. On "Ride" the adds have no target, so bars straight through a weekly high
    must leave them open — the behaviour every measurement before 2026-08-19 was taken on, and
    the one `exec_scale_in`'s stored runs have to keep reproducing."""
    ex, _ = _scaled_to_bar3(exec_scale_tp_mode="Ride")
    ex.step(_sig(4, 106.5, 106.9, 106.2, 106.8, liq_w_high=107.0), _seq_flat())
    ex.step(_sig(5, 106.8, 107.5, 106.6, 107.2, liq_w_high=107.0), _seq_flat())
    assert ex._pos_dir != 0, "the base should still be open — nothing here closes it"
    assert ex._adds[0][1] > 0, "the add banked with the target switched off"
    assert not _atp(ex)


def test_a_standing_weekly_level_beyond_the_newest_add_banks_the_lots():
    """The feature. The level is visible at bar 4's close (so the order rests), and bar 5
    reaches it — so the added lot banks there, and ONLY the added lot."""
    ex, base_qty = _scaled_to_bar3(exec_scale_tp_mode="Prev week H/L")
    filled_before, qty_before = ex._filled_qty, ex._qty
    ex.step(_sig(4, 106.5, 106.9, 106.2, 106.8, liq_w_high=107.0), _seq_flat())
    assert not _atp(ex), "banked on the bar the level appeared — the order was never rested"
    ex.step(_sig(5, 106.8, 107.5, 106.6, 107.2, liq_w_high=107.0), _seq_flat())
    atp = _atp(ex)
    assert len(atp) == 1, "the add did not bank at the weekly high"
    assert abs(atp[0]["price"] - 107.0) < 1e-9, "banked somewhere other than the level"
    assert ex._adds[0][1] == 0.0, "the lot is still open after banking"
    # 🔴 the BASE position is untouched — it is not one lot closer to finished
    assert ex._pos_dir != 0 and ex._qty == qty_before and ex._filled_qty == filled_before


def test_a_target_swept_by_the_filling_bar_still_fills():
    """🔴 THE REGRESSION THIS WHOLE REWRITE EXISTS FOR.

    A daily or H4 level is swept by a WICK, and the engine steps before the strategy sees the
    bar — so on the exact bar price reaches the level, `signals.py` has already dropped it as
    mitigated and reports None. Resolving the target from the LIVE bar therefore made the
    target vanish precisely when it would have filled: `Prev day H/L` resolved 1,804 targets
    across 8 years and filled ZERO, reproducing `Ride` byte-for-byte. Weekly hid it, because a
    weekly level needs a CLOSE through and survives the spike that takes it.

    Here bar 5 reports the level as GONE (swept) while trading through it. The order was rested
    at bar 4's close, so it must still fill."""
    ex, _ = _scaled_to_bar3(exec_scale_tp_mode="Prev day H/L")
    ex.step(_sig(4, 106.5, 106.9, 106.2, 106.8, liq_d_high=107.0), _seq_flat())
    ex.step(_sig(5, 106.8, 107.5, 106.6, 107.2, liq_d_high=None), _seq_flat())
    assert len(_atp(ex)) == 1, "the resting target vanished with the level that placed it"
    assert ex._adds[0][1] == 0.0


def test_a_level_that_does_not_clear_the_newest_add_is_not_a_target():
    """Banking has to be profitable on every lot it closes. A weekly high BELOW the price the
    add was bought at would close that lot at a loss, so it is never rested as a target even
    though price trades through it repeatedly."""
    ex, _ = _scaled_to_bar3(exec_scale_tp_mode="Prev week H/L")
    # 106.0 is under the add's 106.5 entry; both bars trade right through it.
    ex.step(_sig(4, 106.5, 106.9, 105.8, 106.4, liq_w_high=106.0), _seq_flat())
    ex.step(_sig(5, 106.4, 106.9, 105.8, 106.4, liq_w_high=106.0), _seq_flat())
    assert ex._adds[0][1] > 0, "banked at a level below the add's own entry"
    assert not _atp(ex)


def test_no_standing_level_leaves_the_adds_riding():
    """`signals.py` reports only UNMITIGATED levels, so a swept weekly high arrives here as
    None — and with none ever rested, None must ride: not crash, and not bank at some other
    price. This is also the state of every run before its first week has completed."""
    ex, _ = _scaled_to_bar3(exec_scale_tp_mode="Prev week H/L")
    ex.step(_sig(4, 106.5, 106.9, 106.2, 106.8, liq_w_high=None), _seq_flat())
    ex.step(_sig(5, 106.8, 107.5, 106.6, 107.2, liq_w_high=None), _seq_flat())
    assert ex._adds[0][1] > 0
    assert not _atp(ex)


def test_banking_an_add_does_not_hand_the_slot_back():
    """🔴 The other regression worth pinning. The ladder is capped on how many adds were
    BOUGHT (Pine's `lAddN` only counts up), so a banked add must not free its slot. If it did,
    a trade would add again after banking — 'scale in and out repeatedly', which is a different
    strategy from the one Run 22 measured and one nothing here has tested."""
    ex, _ = _scaled_to_bar3(exec_scale_tp_mode="Prev week H/L")
    ex.step(_sig(4, 106.5, 106.9, 106.2, 106.8, liq_w_high=107.0), _seq_flat())
    ex.step(_sig(5, 106.8, 107.5, 106.6, 107.2, liq_w_high=107.0), _seq_flat())
    assert ex._adds[0][1] == 0.0, "fixture failed — the add did not bank"
    # Bars that ratchet the trail further would otherwise be fresh add opportunities.
    ex.step(_sig(6, 107.2, 108.5, 107.0, 108.4), _seq_flat())
    ex.step(_sig(7, 108.4, 109.5, 108.2, 109.4), _seq_flat())
    assert len(ex._adds) == 1, "banking freed the slot and the trade added again"
    assert ex._add_pending is None, "a second add was even PLACED after banking"


# ── the adds must not be SLICED by a TP rung (2026-08-19) ────────────────────────────────
# Pine's `L-TP1`/`L-TP2` are `from_entry = "Long"`, so a rung can only ever close the BASE
# entry; each add carries its own `L-AX1..4` exit at the same stop and dies with it. Python
# closed the adds PRO-RATA with the base instead, then `_finalise_trade` wiped `_adds` and the
# unclosed remainder vanished with its P&L never booked.
#
# 🔴 WATCHED RED 2026-08-19 against the pro-rata code: 121.4 != 100.4 (the dropped half of the
# add lot), and the second assert failed on r too. It CANNOT go red at the shipped
# `exec_tp1_pct = 0` — the runner closes 100% of the base, so the fraction was always 1.0 and
# the divergence lived only on the settings nobody had run. That is the whole reason it
# survived a green parity gate (rule 14).

def test_a_tp_rung_does_not_slice_the_adds():
    """Banking the base at 105 and stopping the rest at 105 is the same thing as stopping all
    of it at 105 — so `exec_tp1_pct` 0 and 50 must produce an IDENTICAL trade.

    No hand-computed constant: the two runs ARE each other's expected value. The only thing
    that can separate them is the base being sliced, which is exactly the defect.
    """
    def run(tp1_pct):
        ex, _ = _scaled_to_bar3(exec_tp1_pct=tp1_pct)
        add_px, add_qty = ex._adds[0]
        # Bar 4 takes out the stage-2 stop floor, which is the TP1 PRICE — 105, the level
        # TP1 already banked at. Base and add both leave here.
        ex.step(_sig(4, 106.0, 106.2, 104.0, 104.5), _seq_flat())
        assert ex._pos_dir == 0, "fixture failed — the trade did not close"
        return ex.trades[0], add_px, add_qty

    ride, add_px, add_qty = run(0)
    sliced, add_px2, add_qty2 = run(50)

    assert (add_px, add_qty) == (add_px2, add_qty2), "the two runs did not buy the same add"
    assert abs(sliced.pnl_usd - ride.pnl_usd) < 1e-6, (
        f"a TP rung changed the trade's P&L: {sliced.pnl_usd} vs {ride.pnl_usd} — "
        f"the add lot ({add_qty} @ {add_px}) was closed pro-rata and the rest discarded")
    assert abs(sliced.r - ride.r) < 1e-9, f"...and its R: {sliced.r} vs {ride.r}"


def test_an_add_records_its_own_excursion_and_not_the_trades():
    """🔴 A LOT'S `mfe_price`/`mae_price` ARE MEASURED FROM THE LOT, NOT INHERITED FROM THE BASE.

    This is the whole reason the per-lot record exists. An add is bought later and higher than the
    entry that started the trade, so it sits through a different piece of the move: the base's
    drawdown here reaches 103.5 on the entry bar, which happened before the lot existed and is not
    the lot's drawdown by any reading. Copying the parent's numbers onto the lot would report the
    base's worst price as the add's, and the chart would draw a `Deepest` line at a price the lot
    never saw.

    Fixture: base fills around 104, the add fills at bar 3's open (106.5), bar 3 ranges 106.0-106.8
    and bar 4 falls to 104.0. So the LOT's window is [104.0, 106.8] and the TRADE's reaches down to
    the entry bar's 103.5.

    Watched RED by mutation: seeding the lot's window from `self._ext_low` / `self._ext_high`
    instead of the fill turns both `!=` assertions red, and it is those two that carry the claim —
    the bracket assertions below pass under that mutation, because the parent's window CONTAINS the
    lot's.
    """
    ex, _ = _scaled_to_bar3()
    ex.step(_sig(4, 106.0, 106.2, 104.0, 104.5), _seq_flat())
    assert ex._pos_dir == 0, "fixture failed — the trade did not close"
    t = ex.trades[0]
    lot = t.adds[0]
    # the lot's own window, and it is NOT the trade's
    assert abs(lot["mae_price"] - 104.0) < 1e-9, f"lot drawdown is {lot['mae_price']}, want 104.0"
    assert abs(lot["mfe_price"] - 106.8) < 1e-9, f"lot run is {lot['mfe_price']}, want 106.8"
    assert lot["mae_price"] != t.mae_price, "the lot inherited the trade's drawdown"
    assert lot["mfe_price"] != t.mfe_price, "the lot inherited the trade's run"
    # …and it brackets the lot's own entry, which a window measured from anywhere else need not
    assert lot["mae_price"] <= lot["price"] <= lot["mfe_price"]


def test_an_add_records_where_it_came_off_and_what_it_made():
    """A lot is a POSITION and the record has to close the arithmetic on it: where it exited, on
    which leg, and what that was worth. Until 2026-08-19 the record was `{price, ms, qty}`, so the
    chart could say a lot was BOUGHT and nothing else — an add carrying most of the size showed as
    one dotted line.

    The P&L is asserted against the lot's OWN entry rather than a hand-typed constant: a lot priced
    off the base entry is exactly the bug `_exit_portion` was fixed for, and a literal here would
    have to be recomputed by hand to notice it come back.

    Watched RED by mutation: dropping the `_close_add_record` call from `_exit_portion` leaves the
    lot with no `exit_price` at all and every assertion below fails on the KeyError.
    """
    ex, _ = _scaled_to_bar3()
    ex.step(_sig(4, 106.0, 106.2, 104.0, 104.5), _seq_flat())
    t = ex.trades[0]
    lot = t.adds[0]
    assert lot["exit_reason"].startswith("L-"), lot["exit_reason"]
    assert lot["exit_ms"] > lot["ms"], "the lot exited before it was bought"
    # it came off with the trade, so on the trade's own last leg and at that leg's price
    last = t.legs[-1]
    assert abs(lot["exit_price"] - last["price"]) < 1e-9
    assert lot["exit_reason"] == last["reason"]
    # …and its P&L is priced off ITS entry, never the base's
    want = (lot["exit_price"] - lot["price"]) * t.dir * lot["qty"] * ex._cfg.point_value
    assert abs(lot["pnl_usd"] - want) < 0.01, f"{lot['pnl_usd']} != {want}"
    off_base = (lot["exit_price"] - t.entry_price) * t.dir * lot["qty"] * ex._cfg.point_value
    assert abs(lot["pnl_usd"] - off_base) > 1.0, "the lot was priced off the BASE entry"


def test_the_lot_record_carries_no_internal_bookkeeping():
    """The running high/low and the fill-bar marks are how the excursion is ACCUMULATED; they are
    not part of what a lot is. `ext_hi` is an un-directioned number, so a consumer reading it as
    "favourable" would be right on longs and wrong on every short — the resolution into
    `mfe_price`/`mae_price` is the only correct reading and it has already happened.

    Watched RED by mutation: returning `dict(lot)` from `_add_record` (what it was before) leaks
    all four keys and this goes red naming them.
    """
    ex, _ = _scaled_to_bar3()
    ex.step(_sig(4, 106.0, 106.2, 104.0, 104.5), _seq_flat())
    lot = ex.trades[0].adds[0]
    leaked = {"ext_hi", "ext_lo", "_fill_ms", "_limit_fill"} & set(lot)
    assert not leaked, f"internal bookkeeping reached the trade record: {sorted(leaked)}"


# ------------------------------------------------ the exit RUNGS a trade reports ---
# A rung PRICE alone does not say whether the trade places an order there. At the shipped 0/0
# default nothing is ever sold at either rung — they only stage the stop — so a chart reading two
# prices off a closed trade drew two profit targets that had no orders behind them, on every trade
# of every run, until 2026-08-21. The closed record now carries the percentage each rung takes off
# beside its price. Reporting-only: no decision reads it, so parity is untouched.


def test_a_closed_trade_reports_how_much_each_rung_actually_takes_off():
    ex = Execution(_cfg(exec_tp1_pct=30.0, exec_tp2_pct=40.0))
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    ex.step(_sig(2, 104.0, 107.0, 103.9, 106.5), _seq_flat())
    ex.step(_sig(3, 106.0, 106.2, 104.9, 105.0), _seq_flat())
    t = ex.trades[0]
    assert [pct for _, pct in t.tp_rungs] == [30.0, 40.0]
    assert [price for price, _ in t.tp_rungs] == [t.tp1, t.tp2]


def test_at_the_shipped_default_BOTH_rungs_report_that_they_bank_nothing():
    """🔴 The picture the bug produced. At 0/0 the position rides the runner and neither rung ever
    sells anything — so a chart must be able to tell that these two prices are not targets."""
    cfg = _cfg()
    assert (cfg.exec_tp1_pct, cfg.exec_tp2_pct) == (0.0, 0.0)  # the shipped default under test
    ex = Execution(cfg)
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    ex.step(_sig(2, 104.0, 107.0, 103.9, 106.5), _seq_flat())
    ex.step(_sig(3, 106.0, 106.2, 104.9, 105.0), _seq_flat())
    assert [pct for _, pct in ex.trades[0].tp_rungs] == [0.0, 0.0]


# ── sizing against the ACCOUNT's budget, at placement (2026-09-03) ────────────────────
#
# Aaron, 2026-09-03: "If at any time a bot is occupying more than 5% then the other bot(s) will
# need to shrink accordingly. If no risk is available then we will refuse trades."
#
# 🔴 The moment is the whole point. The account has had a budget gate since 2026-08-09, but it
# ran at the FILL — by which time a live bot's order is already resting at the broker, so
# shrinking the emulator's copy leaves the two holding different books that grade different R.
# These drive the size that actually reaches `_Pending`, which is what the bridge sends.
def test_a_STATED_budget_SHRINKS_the_placed_size_rather_than_refusing_it():
    """Half the budget this setup wants → half the size, taken rather than skipped.

    RED if the fit is dropped, and RED the other way if it refuses: the size comes back either
    as the formula's full answer or as no trade at all.
    """
    ex = Execution(_cfg(exec_risk_pct=10.0), initial_capital=100_000.0)
    # The formula wants to risk 10% of 100,000 = $10,000 over a 3.82 stop. Grant it half.
    ex._account.external_room = 5_000.0
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    assert ex._pos_dir == 1, "a shrunk setup is still TAKEN — that is the whole request"
    assert abs(ex._qty - (5_000.0 / 3.82)) < 1e-6


def test_NO_budget_left_places_NOTHING_at_all():
    """"If no risk is available then we will refuse trades." A dust order would occupy the leg's
    only position slot, so an empty budget has to mean no order, not a tiny one."""
    ex = Execution(_cfg(exec_risk_pct=10.0), initial_capital=100_000.0)
    ex._account.external_room = 0.0
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    assert ex._pos_dir == 0, "an empty budget must leave the bot flat"


def test_an_UNBUDGETED_run_is_completely_unaffected():
    """🔴 The parity guarantee, asserted rather than assumed. Every solo run and every
    `compare_strategy.py` gate has no budget stated, so the fit must be the identity function
    there — otherwise this change moves stored results and reddens a gate for no reason.
    The number is the same one `test_position_size_uses_risk_pct_of_equity` pins."""
    ex = Execution(_cfg(exec_risk_pct=10.0), initial_capital=100_000.0)
    assert ex._account.room() == float("inf")
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    ex.step(_sig(1, 104.3, 104.4, 103.5, 104.0), _seq_long_ready())
    assert abs(ex._qty - (10_000.0 / 3.82)) < 1e-6


# ── the account learns what time it is (2026-09-03) ──────────────────────────────────
def test_the_account_is_told_the_bar_time_so_a_CLAMP_CAN_BE_DATED():
    """🔴 Every venue-ceiling clamp on a standalone run carried a null time until this landed,
    and that record is the ONLY trace a resized entry leaves — the trade list and the equity
    curve are identical either way, because R is profit over risk and both scale with quantity.
    Found by running the feature end to end, not by reading it."""
    ex = Execution(_cfg())
    ex.step(_sig(3, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert ex._account.now == 3 * 900_000


def test_a_bar_time_of_ZERO_is_still_a_time():
    """⚠ The first bar of a series stamps 0, which is falsy. A truthiness check here would drop
    it and leave the run's opening bars undateable — the same class of bug as reading a measured
    zero as "not measured"."""
    ex = Execution(_cfg())
    ex.step(_sig(0, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert ex._account.now == 0


def test_the_strategy_does_NOT_overwrite_a_clock_a_SHARED_STACK_owns():
    """🔴 A shared stack's simulator stamps ONE tick time across every leg, because a 15m leg and
    a 5m leg reporting their own bar opens would make the shared contention log disagree with
    itself about when a clash happened. RED if the strategy stamps unconditionally."""
    ex = Execution(_cfg())
    ex._account.clock_external = True
    ex._account.now = 12345
    ex.step(_sig(7, 104.0, 104.5, 103.9, 104.2), _seq_long_ready())
    assert ex._account.now == 12345, "the simulator's clock must survive a leg stepping"
