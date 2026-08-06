"""On-disk bar cache — pull once, reuse.

One CSV per (symbol, base timeframe), holding every bar ever fetched for that
pair. Broker bar sets are small (2yr of M15 ≈ 46k rows), so CSV is plenty and
stays human-inspectable; no parquet dependency. The cache is content-addressed
by (symbol, tf) only — the date range lives inside the file, and reads slice it.

Default location: backtest/cache/ (git-ignored). Override with $BACKTEST_CACHE_DIR.

**Feed versioning — read before changing FEED_VERSION.** A cached bar is only as good as the
agent that produced it, and a cache MISS is loud while a stale cache HIT is silent. On 2026-07-16
the agent was fixed to return true UTC instead of broker-local time (see
`algos/markets/fx/tools/broker_clock.py`); the on-disk cache still held bars stamped 2-3h wrong,
so `compare_feeds.py` kept reporting the bug as unfixed against a correct agent — the cache was
answering, not the broker. `FEED_VERSION` closes that hole: it is stamped into each cache file's
sidecar, and a file written under a different version is ignored (treated as a miss) and re-pulled.

**Bump FEED_VERSION whenever the MEANING of a cached value changes** — a timestamp convention, a
price adjustment, a new column, a different tick source. Do NOT bump it for changes that cannot
alter what a stored bar means (a new endpoint, a refactor, a bug fix in code the cache never
touched). The cost of a needless bump is one slow re-pull; the cost of a missed one is silently
backtesting on wrong data, which is the exact failure this module exists to prevent.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

import pandas as pd

from .resample import OHLC_COLS, VOLUME_COL

_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "cache"

# 1: original (bars stamped in BROKER-LOCAL time — the pre-2026-07-16 agent bug).
# 2: bars stamped in TRUE UTC (agent's broker_clock conversion).
# 3: bars carry TICK VOLUME (2026-08-06). The agent dropped MT5's `tick_volume` at
#    `_rates_to_bars`, so every file written under 1 or 2 is price-only. A v2 file is not
#    WRONG, it is INCOMPLETE — but the distinction cannot survive a merge: fold a v2 span
#    and a v3 span into one file and the volume column is real for part of the history and
#    NaN for the rest, which is exactly the shape a VWAP averages straight through. Re-pull.
FEED_VERSION = 3


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

    def meta_path(self, symbol: str, tf_name: str) -> Path:
        """Sidecar carrying the FEED_VERSION the CSV was written under, and whether the bars that
        came back actually carried VOLUME."""
        return self.dir / f"{_safe(symbol)}__{_safe(tf_name)}.meta.json"

    def has_volume(self, symbol: str, tf_name: str) -> Optional[bool]:
        """Did the fetch that wrote this file return tick volume? None = the file predates the
        question (feed version 1 or 2, or no sidecar at all).

        🔴 **This exists to make ONE otherwise-silent state visible, and it is a deploy-ordering
        trap rather than a hypothetical.** `FEED_VERSION` went to 3 the moment the cache learned to
        CARRY volume, but the VPS agent has to be deployed separately before it SENDS any. Fetch in
        that window and the file is stamped current while holding no volume — so it never re-pulls,
        and the chart's VWAP layer is permanently and silently absent for that symbol.

        The sidecar records what CAME BACK rather than what the version implies, which is this
        package's own rule (`_covered_end`: never record what you requested as though it were what
        you received). `False` here is the marker to re-pull: delete the pair's `.csv` and
        `.meta.json`, or bump `FEED_VERSION` again.

        ⚠ It is deliberately NOT wired into `is_stale`. Doing so would re-pull the entire history
        on every single run until the agent ships — loud, but it would make the lab unusable for
        anyone who pulls this change before deploying, and the honest fix is one deletion.
        """
        p = self.meta_path(symbol, tf_name)
        if not p.is_file():
            return None
        try:
            v = json.loads(p.read_text()).get("has_volume")
        except (ValueError, OSError, TypeError):
            return None
        return bool(v) if isinstance(v, bool) else None

    def version_of(self, symbol: str, tf_name: str) -> int:
        """FEED_VERSION the cache file was written under. A cache from before the sidecar
        existed has no marker and is version 1 — the broker-local-timestamp era."""
        p = self.meta_path(symbol, tf_name)
        if not p.is_file():
            return 1
        try:
            return int(json.loads(p.read_text()).get("feed_version", 1))
        except (ValueError, OSError, TypeError):
            return 1

    def is_stale(self, symbol: str, tf_name: str) -> bool:
        """True if a cache file exists but was written under a different FEED_VERSION —
        its values no longer mean what we now expect them to mean."""
        return self.path(symbol, tf_name).is_file() and \
            self.version_of(symbol, tf_name) != FEED_VERSION

    def load(self, symbol: str, tf_name: str) -> pd.DataFrame:
        """Return all cached bars for (symbol, tf), or an empty frame if none.

        A file written under an older FEED_VERSION reads as EMPTY, not as data: its bars mean
        something different from what the caller expects (e.g. broker-local vs true UTC), and
        silently serving them is worse than the re-pull a miss costs.
        """
        p = self.path(symbol, tf_name)
        if not p.is_file() or self.is_stale(symbol, tf_name):
            return _empty_bars()
        df = pd.read_csv(p, parse_dates=["time"])
        return _normalize(df)

    def save(self, symbol: str, tf_name: str, bars: pd.DataFrame) -> None:
        """Merge `bars` into the cache for (symbol, tf), newest values winning on
        a duplicate timestamp, and persist. Index must be the bar-open time.

        A stale-version file is OVERWRITTEN rather than merged — `load` already refuses to read
        it, so merging would fold rows we've deemed unreadable back into a file we then stamp as
        current, laundering the bad data into the new version.
        """
        existing = _empty_bars() if self.is_stale(symbol, tf_name) else self.load(symbol, tf_name)
        merged = self.merge(existing, bars)
        self.dir.mkdir(parents=True, exist_ok=True)
        merged.reset_index().to_csv(self.path(symbol, tf_name), index=False)
        # `has_volume` describes the FILE as written, not the version's intent — see `has_volume`.
        self.meta_path(symbol, tf_name).write_text(json.dumps({
            "feed_version": FEED_VERSION,
            "has_volume": VOLUME_COL in merged.columns,
        }))

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
    unique) + float OHLC columns, plus `volume` when the feed supplied one.

    Volume is carried only if it is THERE. A feed with no volume yields a frame with no volume
    column, never a column of zeros: a zero-volume bar is a real thing MT5 reports on a dead
    session, so filling the unknown with one would put a measurement where there is none and
    every consumer downstream would read it as fact.
    """
    if df.empty and df.index.name == "time":
        return df
    out = df.copy()
    if "time" in out.columns:
        out = out.set_index("time")
    out.index = pd.to_datetime(out.index)
    out.index.name = "time"
    cols = list(OHLC_COLS)
    if VOLUME_COL in out.columns:
        cols.append(VOLUME_COL)
    for c in cols:
        out[c] = out[c].astype("float64")
    out = out[cols]
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()
