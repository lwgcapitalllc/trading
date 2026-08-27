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
    # 🔴 **COLUMN ARRAYS, NEVER `df.iterrows()`, AND THIS IS THE HOT LOOP OF THE WHOLE LAB.**
    # `iterrows` builds a fresh pandas Series for EVERY BAR — a full object with its own block
    # manager, dtype resolution and `__finalize__` — purely so five numbers can be read off it and
    # thrown away. MEASURED under cProfile on a real replay: Series construction alone was **12.7%
    # of a 15m run and 19% of a 5m one**, plus `Series.__getitem__` five times a bar on top. On the
    # 6.6-year window this app actually runs that is minutes of wall clock spent allocating
    # objects, and none of it touches a single number the strategy reads.
    #
    # ⚠ **The conversion is IDENTICAL, deliberately, and that is the whole design.** `.to_numpy()`
    # is called with NO dtype coercion and each element still goes through `float(...)` — the same
    # call applied to the same stored value that `row["open"]` produced. Forcing `dtype="float64"`
    # here would be faster again and is refused: on an object column it would convert by a
    # different route, and "a bit faster and occasionally a different float" is not a trade
    # anybody asked for. Aaron's constraint, 2026-08-26: *"do not sacrifice the accuracy."*
    #
    # ⚠ **`pd.isna` on the raw volume element STAYS.** It is what keeps a missing volume `None`
    # rather than `0.0`, and the field's own docstring above says why that distinction is
    # load-bearing. A NaN test written as `raw != raw` would be equivalent for floats and wrong
    # for an object column carrying `None`.
    #
    # ⚠ Proven on real bars, not by argument: `backtest/tools/replay_fingerprint.py` replays a
    # 2.5-year window and compares the bar stream digest AND every trade field before and after.
    has_volume = "volume" in df.columns
    idx = df.index
    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    vols = df["volume"].to_numpy() if has_volume else None

    for seq in range(len(idx)):
        vol = None
        if vols is not None:
            raw = vols[seq]
            vol = None if pd.isna(raw) else float(raw)
        ts = idx[seq]
        yield ReplayBar(
            index=seq,
            timestamp_ms=_epoch_ms(ts),
            time=ts,
            open=float(opens[seq]),
            high=float(highs[seq]),
            low=float(lows[seq]),
            close=float(closes[seq]),
            volume=vol,
        )
