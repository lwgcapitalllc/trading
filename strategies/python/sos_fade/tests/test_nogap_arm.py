"""`exec_nogap_arm` — which no-FVG setups may rest a fallback limit at the 0.618.

`exec_req_fvg = False` lets a setup with no qualifying zone trade anyway, at the 0.618. Measured
over 155,531 M15 bars that adds 173 trades worth +36.18R gross, and splitting them by what armed
the SOS separates them cleanly: the 78 that carried BOTH a liquidity sweep and an RSI divergence
made +35.47R, and the 95 that carried only a sweep made +0.71R — an average of +0.007R. This
lever is that split turned into a rule.

The tests are weighted toward the ways it can be silently wrong rather than loudly broken:

  * a default that is not byte-identical to the old fallback — the whole safety argument
  * the gate reading the TOGGLE-FILTERED arm flags instead of the raw ones, which would make it
    refuse everything whenever `exec_arm_div` is off (the shipped default), i.e. look enabled and
    do the opposite of its job
  * the gate leaking into a run that HAS a gap, where it must never be consulted
  * the short side being wrong while the long side is right
"""

from __future__ import annotations

import dataclasses
import inspect
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT / "strategies" / "python"))

from sos_fade import Execution, SeqState, SosFadeConfig  # noqa: E402
from sos_fade.signals import Signals  # noqa: E402

# The bull leg every fixture below uses: high anchor 110, low 100.
#   0.382=106.18  0.5=105.0  0.618=103.82  0.786=102.0  0.886=101.14  1.0=100.0
_P3 = 103.82                      # the 0.618 — where a no-gap fallback rests
# A gap sitting inside the 0.5-0.886 band, deep enough to pass `exec_fvg_deep_only`.
_GAP = (104.5, 104.0, True, 1)


def _cfg(**kw) -> SosFadeConfig:
    base = dict(exec_req_fvg=False, exec_arm_div=False, exec_arm_sweep=True)
    base.update(kw)
    return SosFadeConfig(**base)


def _sig(dir=1, **kw) -> Signals:
    """A real `Signals`. Never a `SimpleNamespace` — a hand-built stand-in can carry a field
    production does not produce, which is the fixture-more-complete-than-the-code trap that hid
    the `run_dual` AttributeError for three weeks (see this package's CLAUDE.md)."""
    base = dict(
        index=10, time_ms=9_000_000, open=104.0, high=104.0, low=104.0, close=104.0,
        session_gap_bar=False, ny_hour=8,
        bull_sos=False, bear_sos=False, bull_bos=False, bear_bos=False,
        recent_ssl="", recent_ssl_bar=None, recent_ssl_time=None,
        recent_bsl="", recent_bsl_bar=None, recent_bsl_time=None,
        last_bull_div_bar=None, last_bear_div_bar=None,
        bull_div_active=False, bear_div_active=False,
        veto_on=False, veto_rsi_ob=False, veto_rsi_os=False,
        fibo_dir=dir,
        fibo_p1=106.18, fibo_p2=105.0, fibo_p3=_P3, fibo_p4=102.8,
        fibo_p5=102.0, fibo_p6=101.14, fibo_p7=110.0, fibo_p10=100.0,
        fibo_ash=110.0, fibo_asl=100.0,
        fibo_half_reached=True, fibo_618_ever_reached=True, fibo7_touched=False,
        fvgs=[], poi_long_now=False, poi_short_now=False,
    )
    base.update(kw)
    return Signals(**base)


def _seq(*, swp_l=False, div_l=False, swp_s=False, div_s=False) -> SeqState:
    return SeqState(
        l_stage=4, s_stage=4, l_sos_bar=1, s_sos_bar=1,
        l_half=True, l_618=True, s_half=True, s_618=True,
        l_poi=False, s_poi=False, l_fvg=False, s_fvg=False,
        sos_l_swp=swp_l, sos_l_div=div_l, sos_s_swp=swp_s, sos_s_div=div_s,
        new_sweep_l=False, new_div_l=False, new_sweep_s=False, new_div_s=False,
        retro_link_l=False, retro_link_s=False,
    )


def _edges(cfg, sig, seq):
    return Execution(cfg)._entry_edges(sig, seq)


# ── the default is the old behaviour ────────────────────────────────────────────
def test_the_shipped_default_is_Any():
    """The safety argument for the whole lever: it is PYTHON-ONLY with no Pine input, so a plain
    `SosFadeConfig()` must never be running it."""
    assert SosFadeConfig().exec_nogap_arm == "Any"


def test_Any_rests_at_the_0618_whatever_armed_the_setup():
    """"Any" must be byte-identical to what `exec_req_fvg = False` did before this field existed.
    Every historical no-FVG figure in this package was measured on that branch."""
    for seq in (_seq(swp_l=True), _seq(div_l=True), _seq(swp_l=True, div_l=True)):
        long_edge, _short = _edges(_cfg(exec_nogap_arm="Any"), _sig(), seq)
        assert long_edge == pytest.approx(_P3)


def test_Any_is_still_the_default_when_the_field_is_not_named():
    """A caller that never mentions `exec_nogap_arm` gets the old fallback — the same assertion as
    above, made through the DEFAULT rather than through an explicit value, because a default that
    drifts from its own documented meaning is the failure this pins."""
    long_edge, _short = _edges(_cfg(), _sig(), _seq(swp_l=True))
    assert long_edge == pytest.approx(_P3)


# ── the gate ────────────────────────────────────────────────────────────────────
def test_gated_takes_the_setup_when_BOTH_sources_were_live():
    long_edge, _short = _edges(_cfg(exec_nogap_arm="Sweep + RSI div"), _sig(),
                               _seq(swp_l=True, div_l=True))
    assert long_edge == pytest.approx(_P3)


@pytest.mark.parametrize("seq,why", [
    (_seq(swp_l=True), "a sweep with no divergence — the 95 trades that made +0.007R each"),
    (_seq(div_l=True), "a divergence with no sweep"),
    (_seq(), "neither source"),
])
def test_gated_refuses_a_setup_missing_either_source(seq, why):
    long_edge, _short = _edges(_cfg(exec_nogap_arm="Sweep + RSI div"), _sig(), seq)
    assert long_edge is None, why


def test_the_short_side_reads_its_OWN_arm_flags():
    """The long flags must not decide a short. A gate that reads `sos_l_*` on both sides passes
    every long-only test and silently trades the wrong population on shorts."""
    cfg = _cfg(exec_nogap_arm="Sweep + RSI div")
    sig = _sig(dir=-1)
    # long side fully armed, short side not — the short must still be refused
    _long, short_edge = _edges(cfg, sig, _seq(swp_l=True, div_l=True))
    assert short_edge is None
    _long, short_edge = _edges(cfg, sig, _seq(swp_s=True, div_s=True))
    assert short_edge == pytest.approx(_P3)


# ── the two ways it could be silently inert or silently total ───────────────────
def test_the_gate_reads_the_RAW_arm_flags_not_the_enable_toggles():
    """`exec_arm_div` is OFF at the shipped defaults. If the gate read the toggle-filtered arm
    state it would refuse EVERY setup while the page said the lever was on — enabled and doing
    the opposite of its job. The question it asks is what the market did at the SOS, not which
    triggers the operator chose to act on."""
    cfg = _cfg(exec_nogap_arm="Sweep + RSI div", exec_arm_div=False, exec_arm_sweep=False)
    long_edge, _short = _edges(cfg, _sig(), _seq(swp_l=True, div_l=True))
    assert long_edge == pytest.approx(_P3)


def test_the_gate_is_never_consulted_when_a_gap_qualifies():
    """It gates the FALLBACK only. A setup with a real zone is priced by the entry model and must
    be untouched — otherwise this lever would quietly re-price the shipped book."""
    cfg = _cfg(exec_req_fvg=True, exec_nogap_arm="Sweep + RSI div")
    sig = _sig(fvgs=[_GAP])
    gated, _short = _edges(cfg, sig, _seq())            # no arm sources at all
    ungated, _short2 = _edges(dataclasses.replace(cfg, exec_nogap_arm="Any"), sig, _seq())
    assert gated is not None
    assert gated == pytest.approx(ungated)


def test_require_fvg_on_ignores_the_lever_entirely():
    """At the shipped defaults the lever is INERT, which is what makes it safe to add: no figure
    measured before it existed can move."""
    sig = _sig()
    for arm in ("Any", "Sweep + RSI div"):
        edges = _edges(_cfg(exec_req_fvg=True, exec_nogap_arm=arm), sig, _seq(swp_l=True))
        assert edges == (None, None)


# ── the contract that keeps "cannot ask" from becoming "no" ─────────────────────
def test_entry_edges_requires_the_sequence():
    """`seq` must have NO default. With one, a caller that forgot it would silently read as
    "the confluence was not there" at the one place that decides whether a trade happens."""
    sig_param = inspect.signature(Execution._entry_edges).parameters["seq"]
    assert sig_param.default is inspect.Parameter.empty


def test_config_refuses_an_unrecognised_value():
    """An unknown string has no inert reading — the gate would match nothing and refuse every
    no-FVG setup, which on the page is indistinguishable from the feature being switched off."""
    with pytest.raises(ValueError, match="exec_nogap_arm"):
        SosFadeConfig(exec_nogap_arm="sweep+div")


def test_the_refusal_fires_even_when_the_lever_is_inert():
    """Validated ALWAYS, not only when `exec_req_fvg` is False. A typo parked behind the shipped
    default would sit unnoticed until the day somebody switched the fallback on."""
    with pytest.raises(ValueError, match="exec_nogap_arm"):
        SosFadeConfig(exec_req_fvg=True, exec_nogap_arm="Both")
