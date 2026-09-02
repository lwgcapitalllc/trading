"""Hand-traced tests for the BOS tracker — regime, arm, anchor fib, death, VWAP.

Every test here pins a rule against `strategies/tradingview/mpc_bos_strategy_export.pine` by LINE, so a
future edit that "simplifies" one has something to fail against. The weighting is deliberate:
most of these cover the ways the tracker can be quietly WRONG (arm a leg it should not, keep a
dead leg alive, answer a gate it cannot compute) rather than the ways it can be loudly broken.
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

from mpc_bos.bos import BosTracker, VolumeUnavailable, fib_price  # noqa: E402
from mpc_bos.config import BosConfig  # noqa: E402


def sig(index=0, *, close=100.0, high=None, low=None, bull_sos=False, bear_sos=False,
        bull_bos=False, bear_bos=False, gap=False, bull_hi=None, bull_lo=None,
        bear_hi=None, bear_lo=None, atr=1.0, time_ms=0,
        fibo_dir=0, fibo_ash=None, fibo_asl=None, **kw):
    """A minimal `Signals` stand-in. Only the fields the tracker reads."""
    return SimpleNamespace(
        index=index, time_ms=time_ms or 1_600_000_000_000 + index * 900_000,
        open=close, close=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        bull_sos=bull_sos, bear_sos=bear_sos, bull_bos=bull_bos, bear_bos=bear_bos,
        session_gap_bar=gap,
        bull_bos_high=bull_hi, bull_bos_low=bull_lo,
        bear_bos_high=bear_hi, bear_bos_low=bear_lo,
        fibo_dir=fibo_dir, fibo_ash=fibo_ash, fibo_asl=fibo_asl,
        bos_atr14=atr, **kw)


def bar(volume=1000.0):
    return SimpleNamespace(volume=volume)


def tracker(**overrides):
    return BosTracker(BosConfig(bos_vwap_req="Off", **overrides))


# ── Stage 0: the regime ──────────────────────────────────────────────────────────
def test_a_bos_before_any_sos_cannot_arm():
    """Pine 3492: the arm requires `bosRegL`, which only an SOS sets.

    At the start of history the structure engine seeds a direction with no SOS behind it, so
    those seeded breaks must never trade — there is no shift for them to be a continuation of.
    """
    t = tracker()
    st = t.update(sig(0, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    assert not st.long.on
    assert st.count_l == 0, "the ordinal counter must not advance outside a regime either"


def test_an_sos_on_a_session_gap_bar_does_not_open_a_regime():
    """Pine 3480: OPEN is gap-guarded — a structure event on a time-jump bar is an artifact."""
    t = tracker()
    st = t.update(sig(0, bull_sos=True, gap=True), bar())
    assert not st.regime_l


def test_an_opposite_sos_on_a_gap_bar_STILL_kills_the_armed_leg():
    """Pine 3466-3473, and this asymmetry was a real bug until 2026-07-29.

    CLOSE fires even on a gap bar. Leaving the long armed there let its buy limit rest straight
    through into the new bearish regime, where it could still fill on the way down — a trade
    with no BOS of its own behind it. Killing on a possible artifact costs one setup; keeping it
    costs a wrong-way trade.
    """
    t = tracker()
    t.update(sig(0, bull_sos=True), bar())
    st = t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    assert st.long.on

    st = t.update(sig(2, bear_sos=True, gap=True), bar())
    assert not st.long.on, "an SOS on a gap bar must still close the opposite regime"
    assert not st.regime_l
    assert "opposite SOS" in st.long.why


def test_a_shift_bar_is_not_its_own_first_continuation():
    """Pine 3492 reads `bull_bos and not bull_sos`.

    The structure engine sets `bull_bos = True` on every `bull_sos` bar too — they are not
    mutually exclusive — so an unguarded read would treat the shift itself as break #1.
    """
    t = tracker()
    st = t.update(sig(0, bull_sos=True, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    assert not st.long.on
    assert st.count_l == 0


# ── Stage 1: which break arms ───────────────────────────────────────────────────
def test_the_ordinal_counts_refused_breaks_too():
    """Pine 3496: the counter increments before the filters run, so the ordinal a trade reports
    is its TRUE position in the run rather than its position among the ones that armed."""
    t = BosTracker(BosConfig(bos_vwap_req="Off", bos_which="1st only"))
    t.update(sig(0, bull_sos=True), bar())
    t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    st = t.update(sig(2, bull_bos=True, bull_hi=120, bull_lo=110), bar())
    assert st.count_l == 2, "the second break counts even though '1st only' refused it"
    assert not st.long.on


def test_a_refused_newer_break_still_cancels_the_older_arm():
    """Pine 3497-3500: the arm is dropped BEFORE the new break is tested, mirroring the drawn
    fib re-anchoring. The newest break always owns the leg — even when it is refused."""
    t = BosTracker(BosConfig(bos_vwap_req="Off", bos_which="1st only"))
    t.update(sig(0, bull_sos=True), bar())
    assert t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar()).long.on
    st = t.update(sig(2, bull_bos=True, bull_hi=120, bull_lo=110), bar())
    assert not st.long.on
    assert "re-anchored" in st.long.why


def test_an_unknown_atr_refuses_a_switched_on_displacement_filter():
    """Pine `>= bosMinDispAtr * atr14` against `na` is falsy.

    The dangerous direction is the other one: passing on an unknown ATR would let the whole
    warmup through a filter the operator switched on.
    """
    t = BosTracker(BosConfig(bos_vwap_req="Off", bos_min_disp_atr=0.5))
    t.update(sig(0, bull_sos=True), bar())
    st = t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100, close=115, atr=None), bar())
    assert not st.long.on


def test_the_displacement_filter_measures_the_close_past_the_broken_swing():
    """Pine 3503: `(close - bull_bos_high) >= bosMinDispAtr * atr14`. A one-tick poke through a
    high is a liquidity grab, not a break."""
    cfg = dict(bos_vwap_req="Off", bos_min_disp_atr=1.0)
    t = BosTracker(BosConfig(**cfg))
    t.update(sig(0, bull_sos=True), bar())
    assert not t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100,
                            close=110.5, atr=1.0), bar()).long.on

    t = BosTracker(BosConfig(**cfg))
    t.update(sig(0, bull_sos=True), bar())
    assert t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100,
                        close=111.5, atr=1.0), bar()).long.on


# ── the anchor ladder ───────────────────────────────────────────────────────────
def test_the_break_leg_anchor_is_frozen_and_the_expansion_anchor_is_live():
    """Pine 3547-3550. Under "Break leg" the ladder is the arm bar's own high/low and does not
    move; under "Expansion leg" it tracks the live structure fib, which keeps extending until
    the pullback confirms. These are genuinely different trades, not a cosmetic choice."""
    frozen = BosTracker(BosConfig(bos_vwap_req="Off", bos_fib_anchor="Break leg"))
    frozen.update(sig(0, bull_sos=True), bar())
    frozen.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    st = frozen.update(sig(2, close=130, fibo_dir=1, fibo_ash=130, fibo_asl=100), bar())
    assert st.l_levels[0.0] == 110, "the frozen anchor must ignore the live fib"

    live = BosTracker(BosConfig(bos_vwap_req="Off", bos_fib_anchor="Expansion leg"))
    live.update(sig(0, bull_sos=True), bar())
    live.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    st = live.update(sig(2, close=130, fibo_dir=1, fibo_ash=130, fibo_asl=100), bar())
    assert st.l_levels[0.0] == 130


def test_the_band_shallow_end_moves_with_the_setting_and_the_deep_end_does_not():
    """Pine 3572-3573. Six separate rules read `lTop`; the 0.886 floor is fixed."""
    t = tracker()
    t.update(sig(0, bull_sos=True), bar())
    st = t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    assert st.l_top == pytest.approx(105.0)          # fib 0.5 of 100 -> 110

    t = BosTracker(BosConfig(bos_vwap_req="Off", bos_entry_top="0.382"))
    t.update(sig(0, bull_sos=True), bar())
    st = t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    assert st.l_top == pytest.approx(106.18)
    assert st.l_levels[0.886] == pytest.approx(101.14), "the deep end must not move"


def test_fib_price_is_the_engines_own_arithmetic_in_both_directions():
    assert fib_price(110, 100, 0.5) == pytest.approx(105.0)     # long: ext high, org low
    assert fib_price(100, 110, 0.5) == pytest.approx(105.0)     # short: ext low, org high
    assert fib_price(None, 100, 0.5) is None


# ── death ───────────────────────────────────────────────────────────────────────
def test_the_cycle_latch_is_per_anchor_not_global():
    """Pine 3588-3606, and this is the deviation the spec's §10a records.

    The engine's `fibo7Touched` is keyed to the fib ORIGIN, which does not change across a run
    of breaks — so break #1's round trip would kill breaks #2 and #3 on their own arm bar and
    every continuation after the first would be untradeable. A fresh break must arrive with an
    unset latch.

    ⚠ The new break's bar sits at 118, ABOVE its own 0.5 (115), deliberately. Pine 3590 runs
    the `low <= lTop` latch test on the arm bar as well, so a break bar that already dips into
    its own band latches immediately and legitimately — writing the test the other way would
    have asserted a behaviour the Pine does not have. (It did, on the first attempt.)
    """
    t = tracker()
    t.update(sig(0, bull_sos=True), bar())
    t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    st = t.update(sig(2, close=104, low=104), bar())          # taps the 0.5 band
    assert st.long.half

    st = t.update(sig(3, bull_bos=True, bull_hi=120, bull_lo=110, close=118, low=118), bar())
    assert st.long.on
    assert not st.long.half, "a NEW break must arrive with its own latch unset"


def test_a_retrace_then_a_return_to_the_leg_extreme_kills_the_leg():
    """Pine 3595-3596 — the cycle completed without the limit ever filling."""
    t = tracker()
    t.update(sig(0, bull_sos=True), bar())
    t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    t.update(sig(2, close=104, low=104), bar())
    st = t.update(sig(3, close=110, high=111), bar())
    assert not st.long.on
    assert "cycle complete" in st.long.why


def test_a_close_past_the_leg_origin_invalidates_the_leg():
    """Pine 3597-3598."""
    t = tracker()
    t.update(sig(0, bull_sos=True), bar())
    t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    st = t.update(sig(2, close=99, low=99), bar())
    assert not st.long.on
    assert "fib 1.0" in st.long.why


def test_the_staleness_cap_is_counted_in_bars_not_clock_time():
    """Pine 3586 — `bosMaxDays` becomes a BAR count at this timeframe, so weekends and the
    daily close do not use the allowance up."""
    t = BosTracker(BosConfig(bos_vwap_req="Off", bos_max_days=1.0), tf_seconds=900)
    assert t.max_bars == 96                                   # 86400 / 900
    t.update(sig(0, bull_sos=True), bar())
    t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    assert t.update(sig(1 + 96, close=105.5), bar()).long.on
    assert not t.update(sig(1 + 97, close=105.5), bar()).long.on


def test_a_dead_leg_keeps_its_numbers_and_only_the_flag_goes_off():
    """Pine sets `bosL_on := false` and touches NOTHING else — `bosL_high` / `bosL_low` /
    `bosL_bar` / `bosL_n` / `bosL_half` are `var` and are reassigned only when a NEW break
    arms. So `px_l_ext`, `px_l_org`, `px_ord_l` and `lFibsReady` all keep the last leg's
    values after a death.

    🔴 This is the defect the first real parity run found (2026-08-07). The port built a blank
    `BosLeg` on death, so every bar after the first dead leg diverged —
    `l_ext: py=None pine=4584.26` on the FIRST compared bar at warmup 2000.

    ⚠ The stale numbers are safe only because every consumer ANDs with `.on` first, in both
    implementations. This test pins the persistence; `test_a_dead_leg_prices_nothing` pins the
    other half, and neither is sufficient alone.
    """
    t = BosTracker(BosConfig(bos_vwap_req="Off", bos_max_days=1.0), tf_seconds=900)
    t.update(sig(0, bull_sos=True), bar())
    t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    st = t.update(sig(1 + 97, close=105.5), bar())            # stale — past the day cap
    assert not st.long.on
    assert (st.long.high, st.long.low) == (110, 100), "the leg's prices must survive its death"
    assert st.long.bar == 1 and st.long.ordinal == 1


def test_a_break_the_filters_refuse_leaves_the_previous_leg_standing():
    """Pine assigns the leg's fields INSIDE `if _okWhich and _okDisp and _okLeg`, so a refused
    break flips `bosL_on` off and leaves every number from the break before it.

    The ORDINAL is the readable half: `bosCntL` counts refused breaks (that is deliberate — a
    trade reports its true position in the run) while `bosL_n` does not move, so after a
    refusal the two legitimately disagree.
    """
    t = BosTracker(BosConfig(bos_vwap_req="Off", bos_which="1st only"))
    t.update(sig(0, bull_sos=True), bar())
    t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    st = t.update(sig(2, bull_bos=True, bull_hi=120, bull_lo=112), bar())   # #2 — refused
    assert not st.long.on
    assert (st.long.high, st.long.low) == (110, 100), "the refused break must not overwrite"
    assert st.long.ordinal == 1, "bosL_n stays on the last ARMED leg"
    assert st.count_l == 2, "bosCntL counts the refused break"


def test_the_ladder_is_still_priced_and_ready_on_the_bar_AFTER_the_death():
    """The other half of the persistence rule, and the reason the stale numbers are safe: the
    ladder is still computed and still `ready` long after the leg died, and the execution layer
    must still refuse, because it reads `.on` first.

    ⚠ It has to step PAST the death bar. `update()` computes the ladder BEFORE `_death` runs, so
    on the death bar itself the pre-fix code reported the live leg's levels too — a version of
    this test that stopped there passed against the defect and proved nothing. The divergence
    starts on the NEXT bar.
    """
    t = BosTracker(BosConfig(bos_vwap_req="Off", bos_max_days=1.0), tf_seconds=900)
    t.update(sig(0, bull_sos=True), bar())
    t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    t.update(sig(1 + 97, close=105.5), bar())                 # the leg dies here
    st = t.update(sig(1 + 98, close=105.5), bar())            # and the levels must survive it
    assert not st.long.on
    assert st.l_ready, "lFibsReady reads the stale ladder in the Pine, so it must here too"
    assert st.l_levels[0.0] == 110 and st.l_levels[1.0] == 100


def test_f4_is_off_by_default_and_kills_the_leg_when_switched_on():
    """Pine 3599-3600 + spec §10b: F4 fights the entry, because the 0.5-0.886 band sits BELOW
    the broken swing on almost every leg — so price cannot reach the limit without first
    closing back through the level. It is off by MEASUREMENT (13 trades in a year), not by
    omission, and both halves of that are worth pinning."""
    t = tracker()
    t.update(sig(0, bull_sos=True), bar())
    t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    assert t.update(sig(2, close=105), bar()).long.on, "default OFF must not kill it"

    t = BosTracker(BosConfig(bos_vwap_req="Off", bos_req_hold=True))
    t.update(sig(0, bull_sos=True), bar())
    t.update(sig(1, bull_bos=True, bull_hi=110, bull_lo=100), bar())
    st = t.update(sig(2, close=105), bar())
    assert not st.long.on
    assert "F4" in st.long.why


# ── F10, the session VWAP ───────────────────────────────────────────────────────
def test_the_vwap_gate_blocks_both_sides_before_any_volume_has_accumulated():
    """Pine 3812-3816: a `na` VWAP returns FALSE, never true.

    "Cannot ask" and "no" must not be the same value, and of the two answers available to a
    gate about to place money the safe one is the refusal.
    """
    t = BosTracker(BosConfig())          # filter ON, the shipped default
    st = t.update(sig(0, close=100), bar(volume=0.0))
    assert st.vwap is None
    assert st.vwap_block_l and st.vwap_block_s


def test_the_vwap_gate_reads_the_side_the_bar_CLOSED_on():
    """Pine 3814. It is a STATE, not a cross — it never asks whether price crossed the line."""
    t = BosTracker(BosConfig())
    t.update(sig(0, close=100, high=100, low=100), bar(volume=1000))
    st = t.update(sig(1, close=110, high=110, low=110), bar(volume=1000))
    assert st.vwap is not None and st.vwap < 110
    assert not st.vwap_block_l
    assert st.vwap_block_s


def test_a_missing_volume_column_REFUSES_rather_than_answering():
    """The filter cannot be computed, and both wrong answers are silent: blocking everything
    yields an empty book that reads like a strategy with no signals, and passing everything
    yields a filter reported as on and doing nothing."""
    t = BosTracker(BosConfig())
    with pytest.raises(VolumeUnavailable):
        t.update(sig(0, close=100), bar(volume=None))


def test_the_vwap_engine_is_stepped_even_while_the_filter_is_off():
    """Otherwise switching the filter on mid-run would anchor it on a PARTIAL session — a VWAP
    computed from whichever bar the operator happened to flip the switch on."""
    t = BosTracker(BosConfig(bos_vwap_req="Off"))
    t.update(sig(0, close=100), bar(volume=1000))
    st = t.update(sig(1, close=110), bar(volume=1000))
    assert st.vwap is None, "reported as None while Off — the gate is not answering"
    assert t._vwap._sum_v > 0, "but the accumulator has been running the whole time"
