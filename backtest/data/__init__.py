"""backtest.data — the data layer (A0).

Pulls broker bars directly at the base timeframe the broker serves (PU Prime demo:
M1 ~30d, M5 ~240d, M15 ~2yr), caches them to disk, and resamples UP to any higher
timeframe. Real ticks (2yr deep) back the honest fill model (A2).

Public surface:
    BarSource     — cache-first bar loader (fetch on miss, resample up).
    TickSource    — lazy, cache-backed real bid/ask tick windows (the fill model's feed).
    Mt5Agent      — thin HTTP client over the VPS MT5 agent (/historical_data, /ticks).
    to_minutes    — parse a timeframe input ("15m", "M15", 15) to minutes.
    resample_up   — aggregate OHLC bars to a higher timeframe (pure).
"""

from .cache import FEED_VERSION, BarCache
from .mt5_agent import Mt5Agent, Mt5AgentError
from .resample import resample_up
from .source import BarSource
from .ticks import Tick, TickCache, TickSource, TickWindowUnavailable
from .timeframes import SERVED_TF, resolve_base_tf, to_minutes

__all__ = [
    "SERVED_TF",
    "resolve_base_tf",
    "to_minutes",
    "resample_up",
    "FEED_VERSION",
    "BarCache",
    "Mt5Agent",
    "Mt5AgentError",
    "BarSource",
    "Tick",
    "TickCache",
    "TickSource",
    "TickWindowUnavailable",
]
