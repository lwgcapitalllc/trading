"""On-disk bar cache — pull once, reuse.

One CSV per (symbol, base timeframe), holding every bar ever fetched for that
pair. Broker bar sets are small (2yr of M15 ≈ 46k rows), so CSV is plenty and
stays human-inspectable; no parquet dependency. The cache is content-addressed
by (symbol, tf) only — the date range lives inside the file, and reads slice it.

Default location: backtest/cache/ (git-ignored). Override with $BACKTEST_CACHE_DIR.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd

from .resample import OHLC_COLS

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "cache"


def _default_cache_dir() -> Path:
    env = os.environ.get("BACKTEST_CACHE_DIR", "").strip()
    return Path(env) if env else _DEFAULT_DIR


def _safe(token: str) -> str:
    """Filesystem-safe token: 'XAUUSD.s' → 'XAUUSD_s'."""
    return re.sub(r"[^A-Za-z0-9]+", "_", token).strip("_")


class BarCache:
    """CSV-backed store of base-timeframe bars, keyed by (symbol, timeframe)."""

    def __init__(self, cache_dir: str | os.PathLike | None = None):
        self.dir = Path(cache_dir) if cache_dir is not None else _default_cache_dir()

    def path(self, symbol: str, tf_name: str) -> Path:
        return self.dir / f"{_safe(symbol)}__{_safe(tf_name)}.csv"

    def load(self, symbol: str, tf_name: str) -> pd.DataFrame:
        """Return all cached bars for (symbol, tf), or an empty frame if none."""
        p = self.path(symbol, tf_name)
        if not p.is_file():
            return _empty_bars()
        df = pd.read_csv(p, parse_dates=["time"])
        return _normalize(df)

    def save(self, symbol: str, tf_name: str, bars: pd.DataFrame) -> None:
        """Merge `bars` into the cache for (symbol, tf), newest values winning on
        a duplicate timestamp, and persist. Index must be the bar-open time."""
        merged = self.merge(self.load(symbol, tf_name), bars)
        self.dir.mkdir(parents=True, exist_ok=True)
        merged.reset_index().to_csv(self.path(symbol, tf_name), index=False)

    @staticmethod
    def merge(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
        """Union two bar frames by timestamp; incoming wins on collision."""
        if existing.empty:
            return _normalize(incoming)
        if incoming.empty:
            return _normalize(existing)
        combined = pd.concat([_normalize(existing), _normalize(incoming)])
        combined = combined[~combined.index.duplicated(keep="last")]
        return combined.sort_index()


def _empty_bars() -> pd.DataFrame:
    idx = pd.DatetimeIndex([], name="time")
    return pd.DataFrame({c: pd.Series(dtype="float64") for c in OHLC_COLS}, index=idx)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce a bar frame to the canonical shape: DatetimeIndex 'time' (sorted,
    unique) + float OHLC columns."""
    if df.empty and df.index.name == "time":
        return df
    out = df.copy()
    if "time" in out.columns:
        out = out.set_index("time")
    out.index = pd.to_datetime(out.index)
    out.index.name = "time"
    for c in OHLC_COLS:
        out[c] = out[c].astype("float64")
    out = out[OHLC_COLS]
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()
