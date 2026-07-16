"""backtest.data — the data layer (A0).

Pulls broker bars directly at the base timeframe the broker serves (PU Prime demo:
M1 ~30d, M5 ~240d, M15 ~2yr), caches them to disk, and resamples UP to any higher
timeframe. Real ticks (2yr deep) back the honest fill model in a later phase.

Public surface:
    BarSource     — cache-first bar loader (fetch on miss, resample up).
    Mt5Agent      — thin HTTP client over the VPS MT5 agent's /historical_data.
    to_minutes    — parse a timeframe input ("15m", "M15", 15) to minutes.
    resample_up   — aggregate OHLC bars to a higher timeframe (pure).
"""

from .timeframes import SERVED_TF, resolve_base_tf, to_minutes
from .resample import resample_up
from .cache import BarCache
from .mt5_agent import Mt5Agent, Mt5AgentError
from .source import BarSource

__all__ = [
    "SERVED_TF",
    "resolve_base_tf",
    "to_minutes",
    "resample_up",
    "BarCache",
    "Mt5Agent",
    "Mt5AgentError",
    "BarSource",
]
