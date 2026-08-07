"""ReplayBar + bar iteration — the bridge from the data layer's DataFrame to the
engine stack.

`iter_bars(df)` turns a canonical bar frame (the shape `backtest.data.BarSource`
returns: DatetimeIndex 'time' in UTC, columns open/high/low/close) into a stream
of `ReplayBar`s with a sequential 0-based index and an epoch-millisecond timestamp
(exactly Pine's `time` — the value the liquidity and sessions engines consume).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

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
    # OPTIONAL fifth field, and `None` means THE FEED DID NOT CARRY ONE — never 0.0.
    # A zero-volume bar is a real thing MT5 reports on a dead session, so filling the
    # unknown with a zero puts a measurement where there is none, and a volume-weighted
    # consumer (`engines/vwap/`) averages straight through it without complaining. The
    # data layer already treats the column as optional for exactly this reason — see
    # `backtest/CLAUDE.md` → the 2026-08-06 volume-passthrough entry.
    volume: Optional[float] = None


def _epoch_ms(ts: pd.Timestamp) -> int:
    """Epoch milliseconds for a bar's open time. The data layer stores times as
    UTC wall-clock (the MT5 agent serialises `datetime.utcfromtimestamp(...)`), so
    a naive Timestamp is taken as UTC; `.value` is ns since the Unix epoch."""
    return int(ts.value // 1_000_000)


def iter_bars(df: pd.DataFrame) -> Iterator[ReplayBar]:
    """Yield each row of a canonical bar frame as a ReplayBar, in time order.

    `volume` rides along when the frame carries the column and stays `None` when it does
    not — the column is optional all the way up from `BarCache`, and a frame from a feed
    with no volume must arrive with no volume rather than with zeros. A NaN cell (one
    unknown bar inside an otherwise-populated column) is `None` for the same reason.
    """
    has_volume = "volume" in df.columns
    for seq, (ts, row) in enumerate(df.iterrows()):
        vol = None
        if has_volume:
            raw = row["volume"]
            vol = None if pd.isna(raw) else float(raw)
        yield ReplayBar(
            index=seq,
            timestamp_ms=_epoch_ms(ts),
            time=ts,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=vol,
        )
