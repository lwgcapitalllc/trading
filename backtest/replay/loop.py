"""ReplayBar + bar iteration — the bridge from the data layer's DataFrame to the
engine stack.

`iter_bars(df)` turns a canonical bar frame (the shape `backtest.data.BarSource`
returns: DatetimeIndex 'time' in UTC, columns open/high/low/close) into a stream
of `ReplayBar`s with a sequential 0-based index and an epoch-millisecond timestamp
(exactly Pine's `time` — the value the liquidity and sessions engines consume).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

import pandas as pd


@dataclass(frozen=True)
class ReplayBar:
    """One closed bar, in the form the engines need: a 0-based sequential index, a
    UTC epoch-millisecond timestamp, and OHLC. `time` keeps the original Timestamp
    for reporting / the flat-by-close clock rule."""

    index: int
    timestamp_ms: int
    time: pd.Timestamp
    open: float
    high: float
    low: float
    close: float


def _epoch_ms(ts: pd.Timestamp) -> int:
    """Epoch milliseconds for a bar's open time. The data layer stores times as
    UTC wall-clock (the MT5 agent serialises `datetime.utcfromtimestamp(...)`), so
    a naive Timestamp is taken as UTC; `.value` is ns since the Unix epoch."""
    return int(ts.value // 1_000_000)


def iter_bars(df: pd.DataFrame) -> Iterator[ReplayBar]:
    """Yield each row of a canonical bar frame as a ReplayBar, in time order."""
    for seq, (ts, row) in enumerate(df.iterrows()):
        yield ReplayBar(
            index=seq,
            timestamp_ms=_epoch_ms(ts),
            time=ts,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
        )
