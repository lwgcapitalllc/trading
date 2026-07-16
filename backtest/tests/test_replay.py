"""A1 replay-loop tests — offline, no network.

They prove the loop (a) converts the data layer's frame to correct engine inputs
(sequential index, epoch-ms UTC timestamp), (b) genuinely drives every canonical
engine so each produces output, (c) is deterministic, and (d) passes construction
config through to the underlying engines.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _synth import synth_bars  # noqa: E402

from backtest.replay import EngineConfig, EngineStack, ReplayBar, iter_bars, run  # noqa: E402


# ---------------------------------------------------------------- iter_bars ----
def test_iter_bars_index_is_sequential_and_ohlc_float():
    df = synth_bars(2)
    bars = list(iter_bars(df))
    assert len(bars) == len(df)
    assert [b.index for b in bars] == list(range(len(df)))
    b = bars[0]
    assert isinstance(b, ReplayBar)
    assert isinstance(b.open, float) and isinstance(b.close, float)
    assert (b.open, b.high, b.low, b.close) == tuple(
        float(df.iloc[0][c]) for c in ("open", "high", "low", "close")
    )


def test_iter_bars_timestamp_is_utc_epoch_ms():
    df = synth_bars(1)  # starts 2025-01-06 00:00 UTC
    b0 = next(iter_bars(df))
    # 2025-01-06 00:00:00 UTC == 1736121600 s
    assert b0.timestamp_ms == 1736121600000
    assert b0.time == pd.Timestamp("2025-01-06 00:00:00")


def test_iter_bars_timestamps_are_monotonic():
    bars = list(iter_bars(synth_bars(3)))
    ts = [b.timestamp_ms for b in bars]
    assert ts == sorted(ts)
    assert len(set(ts)) == len(ts)


# --------------------------------------------------------------------- run -----
def test_run_warmup_skips_leading_bars_but_still_warms_engines():
    df = synth_bars(5)
    warmup = 100
    states = list(run(df, warmup=warmup))
    assert len(states) == len(df) - warmup
    assert states[0].bar.index == warmup
    # engines were fed the skipped bars, so RSI is already warm on the first yield
    assert states[0].rsi.rsi is not None


def test_run_drives_every_engine():
    df = synth_bars(10)
    n_swing = n_fib = n_fvg = n_sess = n_liq = n_rsi = 0
    count = 0
    for s in run(df):
        count += 1
        if s.structure.external.new_swing_high or s.structure.external.new_swing_low:
            n_swing += 1
        n_fib += len(s.fib.touched)
        n_fvg += len(s.fvg.formed)
        n_sess += len(s.sessions.opened)
        n_liq += len(s.liquidity.created)
        if s.rsi.rsi is not None:
            n_rsi += 1
    assert count == len(df)
    # each engine produced output over the series — the stack really reaches them
    assert n_swing > 0
    assert n_fib > 0
    assert n_fvg > 0
    assert n_sess > 0
    assert n_liq > 0
    assert n_rsi > 0


def test_run_is_deterministic():
    df = synth_bars(4)
    a = [repr(s) for s in run(df)]
    b = [repr(s) for s in run(df)]
    assert a == b


# ------------------------------------------------------------- EngineStack -----
def test_stack_step_matches_run():
    df = synth_bars(3)
    stack = EngineStack()
    manual = [repr(stack.step(bar)) for bar in iter_bars(df)]
    auto = [repr(s) for s in run(df)]
    assert manual == auto


def test_config_reaches_underlying_engine():
    df = synth_bars(6)
    # a threshold so large no gap qualifies -> the config must be reaching the FVG engine
    cfg = EngineConfig(fvg_threshold_pct=100.0)
    stack = EngineStack(cfg)
    assert stack.config is cfg
    formed = sum(len(stack.step(bar).fvg.formed) for bar in iter_bars(df))
    assert formed == 0
    # sanity: the default config does form gaps on the same series
    default_formed = sum(len(s.fvg.formed) for s in run(df))
    assert default_formed > 0
