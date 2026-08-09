"""`exec_poi_source` — which zones a setup may use as its point of interest.

The seam is `signals.pois_for()`, and it exists so there is exactly ONE of it: both consumers of a
zone (the confluence flag in `sequence.py` and the entry-edge loop in `execution.py`) call it and
then run unchanged logic, which is what makes "an order block obeys the same rules as a gap" true by
construction rather than by two implementations agreeing.

These tests are weighted toward the ways this can be silently wrong rather than loudly broken:
a source that quietly falls back to gaps, and an order-block run on a stack that never built the
engine — which would return `[]` and trade exactly like a Require-FVG run that found no gap.
"""

import dataclasses

import pytest

from strategies.python.mpc_sos_fade.config import SosFadeConfig
from strategies.python.mpc_sos_fade.signals import (POI_RANK_FVG, POI_RANK_FVG_ON_OB,
                                                    POI_RANK_OB, PoiSourceUnavailable,
                                                    Signals, pois_for)
from strategies.python.mpc_sos_fade.strategy import MpcSosFadeStrategy

# Deliberately NOT overlapping — 104.0 vs 103.0 — so the default fixture exercises the plain
# tiers and an overlap has to be built on purpose by the test that means to test one.
_GAP = (105.0, 104.0, True, 7)
_BLOCK = (103.0, 102.0, True, 9)

# `pois_for` returns 5-tuples; the flat rank every non-precedence mode uses.
_FLAT = 0


def _zones(pois):
    """Drop the rank — for the modes where every candidate ties and it carries no information."""
    return [p[:4] for p in pois]


def _sig(**kw) -> Signals:
    """A real `Signals`, never a stand-in. A hand-built namespace here could carry a field
    production does not produce, which is the fixture-more-complete-than-the-code trap that hid the
    `run_dual` AttributeError for three weeks (see this package's CLAUDE.md)."""
    base = dict(
        index=10, time_ms=0, open=1.0, high=1.0, low=1.0, close=1.0,
        session_gap_bar=False, ny_hour=10,
        bull_sos=False, bear_sos=False, bull_bos=False, bear_bos=False,
        recent_ssl="", recent_ssl_bar=None, recent_ssl_time=None,
        recent_bsl="", recent_bsl_bar=None, recent_bsl_time=None,
        last_bull_div_bar=None, last_bear_div_bar=None,
        bull_div_active=False, bear_div_active=False,
        veto_on=False, veto_rsi_ob=False, veto_rsi_os=False,
        fibo_dir=1,
        fibo_p1=106.18, fibo_p2=105.0, fibo_p3=103.82, fibo_p4=102.8,
        fibo_p5=102.0, fibo_p6=101.14, fibo_p7=110.0, fibo_p10=100.0,
        fibo_ash=110.0, fibo_asl=100.0,
        fibo_half_reached=True, fibo_618_ever_reached=True, fibo7_touched=False,
        fvgs=[_GAP], obs=[_BLOCK], obs_available=True,
        poi_long_now=False, poi_short_now=False,
    )
    base.update(kw)
    return Signals(**base)


def _cfg(source: str) -> SosFadeConfig:
    return dataclasses.replace(SosFadeConfig(), exec_poi_source=source)


def test_the_shipped_default_is_FVG_so_nothing_historical_moves():
    """The whole point of the default: an order-block run is a LAB finding with no Pine
    counterpart, so it must never be what a plain `SosFadeConfig()` does."""
    assert SosFadeConfig().exec_poi_source == "FVG"


def test_each_source_returns_exactly_the_zones_it_names():
    sig = _sig()
    assert _zones(pois_for(_cfg("FVG"), sig)) == [_GAP]
    assert _zones(pois_for(_cfg("Order block"), sig)) == [_BLOCK]
    assert sorted(_zones(pois_for(_cfg("Either"), sig))) == sorted([_GAP, _BLOCK])
    assert sorted(_zones(pois_for(_cfg("FVG first"), sig))) == sorted([_GAP, _BLOCK])


def test_every_mode_but_FVG_first_ranks_its_candidates_FLAT():
    """The precedence tiers must be inert everywhere else, or adding "FVG first" silently
    re-ordered the entry loop's choice in three modes that were already measured. A flat rank is
    what makes the loop collapse back to its original nearest-first max/min."""
    sig = _sig()
    for source in ("FVG", "Order block", "Either"):
        assert {p[4] for p in pois_for(_cfg(source), sig)} == {_FLAT}, source


def test_an_order_block_arrives_in_the_GAP_shape_so_the_same_rules_apply():
    """A block must be a `(top, bottom, is_bullish, born)` tuple + its rank, because both consumers
    unpack it into exactly those names. A different shape would raise inside the entry loop rather
    than at the seam, which is a long way from the cause."""
    (top, bottom, is_bullish, born, _rank), = pois_for(_cfg("Order block"), _sig())
    assert (top, bottom, is_bullish, born) == _BLOCK
    assert top > bottom


def test_an_unknown_source_RAISES_rather_than_falling_back_to_gaps():
    """A typo that silently ran the default would make a whole replay a lie about what it tested —
    the run would report itself as an order-block run and be an FVG one."""
    with pytest.raises(ValueError) as exc:
        pois_for(_cfg("order blocks"), _sig())     # lower-case, plural: a plausible typo
    assert "exec_poi_source" in str(exc.value)


def test_asking_for_blocks_on_a_stack_that_never_BUILT_them_refuses():
    """`obs_available=False` means the engine never ran, which is NOT the same as it running and
    finding nothing. Returning `[]` here would trade exactly like a Require-FVG run with no gap —
    a silently different strategy reporting itself as the one you configured.

    This is the repo's standing rule that "no" and "cannot ask" must never be the same value.
    """
    blind = _sig(obs=[], obs_available=False)
    with pytest.raises(PoiSourceUnavailable):
        pois_for(_cfg("Order block"), blind)
    with pytest.raises(PoiSourceUnavailable):
        pois_for(_cfg("Either"), blind)


def test_an_FVG_run_does_NOT_refuse_on_a_stack_without_order_blocks():
    """The default must keep working on every stack that has ever existed — otherwise adding this
    feature breaks every caller that builds its own `EngineConfig`."""
    blind = _sig(obs=[], obs_available=False)
    assert _zones(pois_for(_cfg("FVG"), blind)) == [_GAP]


def test_found_none_is_distinct_from_never_asked():
    """The engine ran and this bar simply holds no block: an empty list, no refusal."""
    empty = _sig(obs=[], obs_available=True)
    assert pois_for(_cfg("Order block"), empty) == []


# ── "FVG first" — the PRECEDENCE mode (2026-08-09) ────────────────────────────────
# Aaron: "if there is fair value gaps, take those preferentially over order blocks. Only if
# there's no fair value gaps, then take the order blocks. If a fair value gap and an order block
# overlap, that's the most preferred fair value gap to take."


def test_FVG_first_refuses_on_a_blind_stack_because_it_NEEDS_the_blocks():
    """It reads blocks twice — as the fallback tier AND as the thing that promotes a gap — so a
    stack without the engine cannot run it. Returning gaps-only would be an "FVG" run wearing the
    name of a mode that also trades blocks: the exact silent-degrade this seam exists to refuse."""
    with pytest.raises(PoiSourceUnavailable):
        pois_for(_cfg("FVG first"), _sig(obs=[], obs_available=False))


def test_a_gap_outranks_a_block_and_a_block_still_gets_a_tier():
    """The fallback is half the mode. Ranking the block OUT would make this "FVG" with extra
    work — the trade count would be identical and the whole point is that a leg whose only zone
    is a block still trades."""
    ranks = {p[:4]: p[4] for p in pois_for(_cfg("FVG first"), _sig())}
    assert ranks[_GAP] == POI_RANK_FVG
    assert ranks[_BLOCK] == POI_RANK_OB
    assert POI_RANK_FVG > POI_RANK_OB


def test_a_gap_an_order_block_SITS_ON_takes_the_top_tier():
    """The rule Aaron asked for by name. The block here shares price with the gap (103.5-104.5
    against 104.0-105.0), so it confirms it; the other gap floats free and stays on the plain tier.
    That pair is what makes the promotion visible — with one gap there is nothing to outrank."""
    confirmed = (105.0, 104.0, True, 7)
    plain = (99.0, 98.0, True, 7)
    block = (104.5, 103.5, True, 9)
    ranks = {p[:4]: p[4] for p in pois_for(
        _cfg("FVG first"), _sig(fvgs=[confirmed, plain], obs=[block]))}
    assert ranks[confirmed] == POI_RANK_FVG_ON_OB
    assert ranks[plain] == POI_RANK_FVG
    assert POI_RANK_FVG_ON_OB > POI_RANK_FVG


def test_the_confirming_block_must_point_the_SAME_WAY_as_the_gap():
    """A bearish (supply) block on a bullish gap is the opposite of confirmation, so promoting
    that gap to the top tier would rank the WORST candidate on the leg highest. This is the one
    reading of Aaron's rule that his words did not settle, so it is pinned rather than assumed —
    and it must be flipped here and in `mpc_strategy.pine` together or the parity gate goes red."""
    gap = (105.0, 104.0, True, 7)
    opposing = (104.5, 103.5, False, 9)     # same price, opposite direction
    ranks = {p[:4]: p[4] for p in pois_for(_cfg("FVG first"), _sig(fvgs=[gap], obs=[opposing]))}
    assert ranks[gap] == POI_RANK_FVG


def test_overlap_is_INCLUSIVE_at_the_edges():
    """A block whose top is exactly the gap's bottom shares one price and counts, matching every
    other band test in this package (`bot <= p2 and top >= p6`). Pinned because a `>` here and a
    `>=` in the Pine is a divergence no unit test on either side would show."""
    gap = (105.0, 104.0, True, 7)
    touching = (104.0, 103.0, True, 9)
    ranks = {p[:4]: p[4] for p in pois_for(_cfg("FVG first"), _sig(fvgs=[gap], obs=[touching]))}
    assert ranks[gap] == POI_RANK_FVG_ON_OB


# ── The tier has to actually STEER the entry, not just ride along on the tuple ────
# The seam tests above prove the ranks are computed. These prove `_entry_edges` obeys them,
# which is the only place the mode can change a trade.


def _edges(source, **sigkw):
    """The (long, short) resting-limit price `Execution` would rest, for one bar."""
    from strategies.python.mpc_sos_fade.execution import Execution
    # deep-only OFF so the fixture's zones are judged on the band alone — this test is about
    # RANK, and leaving the gate on would make it about which zone clears 0.5.
    cfg = dataclasses.replace(_cfg(source), exec_fvg_deep_only=False)
    return Execution(cfg)._entry_edges(_sig(**sigkw))


def test_a_higher_tier_wins_even_when_a_lower_one_rests_NEARER():
    """The whole of the precedence. The block rests at 104.9 (shallower, so price reaches it
    FIRST on a long) and the gap at 102.5; under "Either" the pooled nearest-first choice takes
    the block, and under "FVG first" the gap must win anyway.

    ⚠ Watched against the un-ranked loop: with the ranks removed both rows return 104.9.
    """
    gap = (102.5, 102.0, True, 7)
    block = (104.9, 104.5, True, 9)
    pooled, _ = _edges("Either", fvgs=[gap], obs=[block])
    ranked, _ = _edges("FVG first", fvgs=[gap], obs=[block])
    assert pooled == 104.9      # nearest wins when nothing is ranked
    # The gap wins on rank and is then priced by the ordinary entry model — it floats deeper than
    # 0.618, so `exec_fib_nearest` rests it on fib 0.702 (102.8) rather than its own edge. Asserted
    # as the price the entry ACTUALLY rests at, not the raw zone edge: a rank that chose the right
    # zone and a snap that mispriced it are different failures and must not be able to hide here.
    assert ranked == _sig().fibo_p4 == 102.8


def test_with_no_qualifying_gap_the_BLOCK_still_prices_the_entry():
    """The fallback tier, and the reason this is not "FVG" with extra steps: a leg whose only
    zone is a block trades, and it trades off that block."""
    block = (104.9, 104.5, True, 9)
    assert _edges("FVG first", fvgs=[], obs=[block])[0] == 104.9
    # ...and the control: under plain "FVG" the same bar prices nothing.
    assert _edges("FVG", fvgs=[], obs=[block])[0] is None


def test_the_confirmed_gap_beats_a_plain_gap_that_rests_nearer():
    """The top tier has to outrank a plain gap the same way a plain gap outranks a block —
    otherwise the overlap rule is computed and then thrown away by the nearest-first tie-break,
    which is precisely the case Aaron said it exists for ("multiple fair value gaps")."""
    confirmed = (102.5, 102.0, True, 7)
    plain = (104.9, 104.5, True, 7)
    block = (102.4, 101.9, True, 9)          # overlaps `confirmed`, not `plain`
    # 102.8 = fib 0.702, where the entry model rests the confirmed gap (see the note above).
    # The plain gap would have rested at its own 104.9 edge, so the two are far apart and the
    # assertion cannot pass by accident.
    assert _edges("FVG first", fvgs=[confirmed, plain], obs=[block])[0] == 102.8
    assert _edges("FVG", fvgs=[confirmed, plain], obs=[])[0] == 104.9   # control: nearest wins


def test_the_stack_builds_the_order_block_engine_ONLY_when_the_config_needs_it():
    """`engine_config()` stays a static description of the Pine's constants (the parity harness and
    `mpc_bleg` both call it off the class); `stack_config()` is the per-instance layer.

    The OFF half matters as much as the ON half — turning the engine on unconditionally would add
    its work to every A+ and B-LEG replay for a feature they do not read.
    """
    default = MpcSosFadeStrategy(config=_cfg("FVG"))
    assert default.stack_config().order_blocks is False

    for source in ("Order block", "Either", "FVG first"):
        strat = MpcSosFadeStrategy(config=_cfg(source))
        assert strat.stack_config().order_blocks is True, source


def test_stack_config_preserves_every_other_engine_pin():
    """It may only ever turn `order_blocks` on — the four pins in `engine_config()` are what keep
    the bot reading the same fibs the Pine does, and a `replace` that dropped one would move trades
    with no test failing (the 2026-07-31 `fvg_threshold_pct` incident)."""
    base = MpcSosFadeStrategy.engine_config()
    got = MpcSosFadeStrategy(config=_cfg("Order block")).stack_config()
    for f in dataclasses.fields(base):
        if f.name == "order_blocks":
            continue
        assert getattr(got, f.name) == getattr(base, f.name), f.name
