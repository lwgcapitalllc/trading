"""Resample OHLC bars UP to a higher timeframe.

Pure over a bar DataFrame — no I/O, no network. The one direction we ever go is
up (5m → 15m, 15m → 45m): aggregating whole base bars is exact. Going down would
mean inventing the price path inside a bar, which we never do.
"""

from __future__ import annotations

import pandas as pd

# The canonical bar frame: DatetimeIndex named "time" (UTC, bar OPEN time),
# columns open/high/low/close. Bar timestamp = its open, matching MT5.
OHLC_COLS = ["open", "high", "low", "close"]

# OPTIONAL fifth column: the bar's TICK volume, as MT5 reports it. Optional rather than
# canonical on purpose — a frame from a feed that does not supply it must carry NO volume
# column at all, never a fabricated one. A missing column is a question the consumer can
# refuse to answer; a column of zeros is an answer, and a wrong one. `engines/vwap/` is the
# only consumer today and it needs every bar in its window to have a real figure.
VOLUME_COL = "volume"

_AGG = {"open": "first", "high": "max", "low": "min", "close": "last"}


def _volume_sum(s: pd.Series) -> float:
    """Total tick volume over a resample window — NaN if ANY base bar in it is unknown.

    Volume AGGREGATES BY SUM, unlike every price column. Reading it first/last/max would be
    silently plausible (the number stays the right order of magnitude) and would under-weight
    every resampled bar in a VWAP by roughly the resample ratio.

    `skipna=False` is the accuracy half: pandas' default sum treats an unknown bar as a zero-
    volume one, which is a real and different thing, and it yields a short total that looks
    perfectly ordinary. One unknown base bar poisons its window, and the window says so.
    """
    return s.sum(skipna=False)


def resample_up(df: pd.DataFrame, target_minutes: int, base_minutes: int) -> pd.DataFrame:
    """Aggregate base-timeframe OHLC bars into target-timeframe bars.

    `df` must be indexed by a sorted DatetimeIndex of bar OPEN times and carry
    open/high/low/close. Returns a new frame at the target timeframe; windows
    with no base bars (e.g. the daily gold break) are dropped, not carried
    forward. target_minutes must be a positive multiple of base_minutes.

    A `volume` column, if present, is carried through as a SUM over each window. Absent, it
    stays absent — this never invents one.
    """
    if target_minutes < base_minutes or target_minutes % base_minutes != 0:
        raise ValueError(
            f"target {target_minutes}m must be a positive multiple of base {base_minutes}m"
        )
    if target_minutes == base_minutes:
        return df.copy()
    if df.empty:
        return df.copy()

    missing = [c for c in OHLC_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"missing OHLC columns: {missing}")

    # origin="epoch" anchors windows to the Unix epoch, so 15m bars fall on
    # :00/:15/:30/:45 etc. — the same alignment the broker uses for its own bars.
    # label/closed="left": a bar is timestamped at its OPEN, like MT5.
    agg = dict(_AGG)
    if VOLUME_COL in df.columns:
        agg[VOLUME_COL] = _volume_sum
    out = df.resample(
        f"{target_minutes}min",
        label="left",
        closed="left",
        origin="epoch",
    ).agg(agg)
    # Empty windows produce all-NaN rows; "open" is NaN iff the window had no bars.
    return out.dropna(subset=["open"])
