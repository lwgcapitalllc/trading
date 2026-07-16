"""backtest.replay — A1, the replay loop.

Feeds a canonical bar frame one bar at a time through the canonical `engines/` in
Pine order (structure -> fib -> FVG -> RSI-divergence -> liquidity -> sessions),
producing a per-bar `BarState` the strategy layer reads. This module wires the
engines and drives them; it never reimplements detection.

    from backtest.replay import run, EngineStack, EngineConfig, iter_bars

    for state in run(df, warmup=200):        # df from backtest.data.BarSource.load
        state.bar.close, state.structure, state.fib, state.fvg, state.liquidity, ...
"""

from .loop import ReplayBar, iter_bars
from .stack import BarState, EngineConfig, EngineStack, run

__all__ = [
    "ReplayBar",
    "iter_bars",
    "BarState",
    "EngineConfig",
    "EngineStack",
    "run",
]
