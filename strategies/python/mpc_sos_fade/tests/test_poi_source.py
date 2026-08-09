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
from strategies.python.mpc_sos_fade.signals import (PoiSourceUnavailable, Signals,
                                                    pois_for)
from strategies.python.mpc_sos_fade.strategy import MpcSosFadeStrategy

_GAP = (105.0, 104.0, True, 7)
_BLOCK = (103.0, 102.0, True, 9)


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
    assert pois_for(_cfg("FVG"), sig) == [_GAP]
    assert pois_for(_cfg("Order block"), sig) == [_BLOCK]
    assert sorted(pois_for(_cfg("Either"), sig)) == sorted([_GAP, _BLOCK])


def test_an_order_block_arrives_in_the_GAP_shape_so_the_same_rules_apply():
    """A block must be a `(top, bottom, is_bullish, born)` 4-tuple, because both consumers unpack
    it into exactly those four names. A different shape would raise inside the entry loop rather
    than at the seam, which is a long way from the cause."""
    (top, bottom, is_bullish, born), = pois_for(_cfg("Order block"), _sig())
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
    assert pois_for(_cfg("FVG"), blind) == [_GAP]


def test_found_none_is_distinct_from_never_asked():
    """The engine ran and this bar simply holds no block: an empty list, no refusal."""
    empty = _sig(obs=[], obs_available=True)
    assert pois_for(_cfg("Order block"), empty) == []


def test_the_stack_builds_the_order_block_engine_ONLY_when_the_config_needs_it():
    """`engine_config()` stays a static description of the Pine's constants (the parity harness and
    `mpc_bleg` both call it off the class); `stack_config()` is the per-instance layer.

    The OFF half matters as much as the ON half — turning the engine on unconditionally would add
    its work to every A+ and B-LEG replay for a feature they do not read.
    """
    default = MpcSosFadeStrategy(config=_cfg("FVG"))
    assert default.stack_config().order_blocks is False

    for source in ("Order block", "Either"):
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
