"""Sequence + signal-adapter tests — offline, no network.

They prove the A+ front half (SignalAdapter -> SosFadeSequence) (a) wires onto the real
engine stack without error, (b) is a proper streaming state machine that produces the
staged output the Pine does, and (c) reproduces two hand-checkable Pine rules in
isolation: the Stage-1 -> Stage-2 -> death progression and the arm-source snapshot.

The engine stack is fed a deterministic synthetic multi-day 15m series (the same one
the replay tests use), so structure/fib/FVG/liquidity all fire.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))                       # repo root -> `import backtest`
sys.path.insert(0, str(_ROOT / "strategies" / "python"))  # -> `import mpc_sos_fade`
sys.path.insert(0, str(_ROOT / "backtest" / "tests"))     # -> `import _synth`

from _synth import synth_bars  # noqa: E402
from backtest.replay import EngineStack, iter_bars  # noqa: E402
from mpc_sos_fade import SosFadeConfig, SosFadeSequence, SignalAdapter  # noqa: E402
from mpc_sos_fade.signals import Signals  # noqa: E402


def _run(df, config=None):
    """Drive the stack + adapter + sequence over a frame, returning the list of
    (Signals, SeqState) pairs."""
    cfg = config or SosFadeConfig()
    stack = EngineStack()
    adapter = SignalAdapter(cfg)
    seq = SosFadeSequence(cfg)
    out = []
    for bar in iter_bars(df):
        state = stack.step(bar)
        sig = adapter.update(state)
        st = seq.update(sig)
        out.append((sig, st))
    return out


# ------------------------------------------------------------------ plumbing ----
def test_pipeline_runs_and_produces_signals():
    out = _run(synth_bars(6))
    assert len(out) == 6 * 96
    sig0, _ = out[0]
    assert isinstance(sig0, Signals)
    # OHLC carried through
    assert sig0.high >= sig0.low
    # NY hour is a valid clock hour
    assert 0 <= sig0.ny_hour <= 23


def test_sequence_reaches_a_setup_stage():
    # On a multi-day impulse series the A+ sequence must arm and advance at least to
    # Stage 1 (a sweep or divergence) somewhere — proof the whole chain lights up.
    out = _run(synth_bars(10))
    max_stage = max(max(st.l_stage, st.s_stage) for _, st in out)
    assert max_stage >= 1


def test_signals_are_deterministic():
    a = _run(synth_bars(5))
    b = _run(synth_bars(5))
    assert [st.l_stage for _, st in a] == [st.l_stage for _, st in b]
    assert [st.s_stage for _, st in a] == [st.s_stage for _, st in b]


# ------------------------------------------------- hand-checked Pine rules ------
def _sig(**kw):
    """A blank Signals with sane defaults; override the fields a test cares about."""
    base = dict(
        index=0, time_ms=0, open=100.0, high=101.0, low=99.0, close=100.0,
        session_gap_bar=False, ny_hour=8,
        bull_sos=False, bear_sos=False, bull_bos=False, bear_bos=False,
        recent_ssl="", recent_ssl_bar=None, recent_ssl_time=None,
        recent_bsl="", recent_bsl_bar=None, recent_bsl_time=None,
        last_bull_div_bar=None, last_bear_div_bar=None,
        bull_div_active=False, bear_div_active=False, veto_on=False, veto_rsi_ob=False, veto_rsi_os=False,
        fibo_dir=0, fibo_p1=None, fibo_p2=None, fibo_p3=None, fibo_p4=None,
        fibo_p5=None, fibo_p6=None, fibo_p7=None, fibo_p10=None,
        # Anchors track the levels: this fixture's fib is inactive, so both are None.
        fibo_ash=None, fibo_asl=None,
        fibo_half_reached=False, fibo_618_ever_reached=False, fibo7_touched=False,
        fvgs=[], poi_long_now=False, poi_short_now=False,
    )
    base.update(kw)
    return Signals(**base)


def test_sweep_then_sos_advances_to_stage_2():
    seq = SosFadeSequence(SosFadeConfig())
    # bar 0: a new SSL sweep arms Stage 1 (long)
    st = seq.update(_sig(index=0, time_ms=0, recent_ssl="Asia Low", recent_ssl_bar=0))
    assert st.l_stage == 1 and st.l_sos_bar is None
    # bar 1: a bull SOS inside the window advances to Stage 2
    st = seq.update(_sig(index=1, time_ms=60_000, bull_sos=True,
                         recent_ssl="Asia Low", recent_ssl_bar=0))
    assert st.l_stage == 2 and st.l_sos_bar == 1
    assert st.sos_l_swp is True and st.sos_l_div is False


def test_opposite_sos_kills_the_long():
    seq = SosFadeSequence(SosFadeConfig())
    seq.update(_sig(index=0, time_ms=0, recent_ssl="Asia Low", recent_ssl_bar=0))
    seq.update(_sig(index=1, time_ms=60_000, bull_sos=True,
                    recent_ssl="Asia Low", recent_ssl_bar=0))
    # a bear SOS reverses the trend the long was fading -> long sequence dies
    st = seq.update(_sig(index=2, time_ms=120_000, bear_sos=True))
    assert st.l_stage == 0 and st.l_sos_bar is None


def test_stale_arm_clears_after_window():
    cfg = SosFadeConfig()  # window 4320 min
    seq = SosFadeSequence(cfg)
    st = seq.update(_sig(index=0, time_ms=0, recent_ssl="Asia Low", recent_ssl_bar=0))
    assert st.l_stage == 1
    # far beyond the window, no SOS -> arm cleared
    late = (cfg.aplus_window + 1) * 60_000
    st = seq.update(_sig(index=1, time_ms=late))
    assert st.l_stage == 0


# ------------------------------------------------- the leg's anchor TIMES -------
# `fibo_ash_ms` / `fibo_asl_ms` are reporting-only (nothing in the A+ path reads them), and they
# exist so a consumer downstream of this run can say WHERE the fib leg is. The engine reports its
# anchors as bar INDICES; a bar index is relative to the window that produced it, so shipping one
# to a chart that trimmed its candles would point at the wrong candle — hence times.

def test_the_fib_leg_anchor_times_are_real_bar_timestamps_from_this_run():
    out = _run(synth_bars(10))
    times = {sig.time_ms for sig, _ in out}
    live = [sig for sig, _ in out if sig.fibo_ash is not None]
    assert live, "the fib never went active on this fixture — nothing is being tested"
    for sig in live:
        assert sig.fibo_ash_ms in times
        assert sig.fibo_asl_ms in times
        # An anchor is a PAST swing, so it can never postdate the bar reporting it.
        assert sig.fibo_ash_ms <= sig.time_ms
        assert sig.fibo_asl_ms <= sig.time_ms


def test_no_anchor_time_ever_outlives_its_anchor():
    """They are two halves of one fact. A time surviving a leg that has gone would let a consumer
    draw a span for a leg that no longer exists. The converse is deliberately NOT asserted: an
    anchor whose bar predates this run's first bar has no time here, and `_bar_time` answers None
    rather than inventing one — over a full replay that case cannot arise (every bar from index 0
    is recorded), which is why both directions hold in practice."""
    out = _run(synth_bars(10))
    assert any(sig.fibo_ash is not None for sig, _ in out), "fixture never activates the fib"
    assert any(sig.fibo_ash is None for sig, _ in out), "fixture never has the fib inactive"
    for sig, _ in out:
        if sig.fibo_ash is None:
            assert sig.fibo_ash_ms is None
        if sig.fibo_asl is None:
            assert sig.fibo_asl_ms is None
