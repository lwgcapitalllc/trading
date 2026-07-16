"""Fetched-range coverage — what date windows we've already pulled.

Tracked separately from the bars themselves so the cache-hit test never has to
reason about the trading calendar. A request for a weekend inside an
already-fetched span is "covered" even though no bars exist on those days, so we
don't refetch it; and a bar set that legitimately ends at 23:45 on the last day
still counts as covering that whole day. One JSON sidecar per (symbol, tf) holds
the union of fetched [start, end] date intervals (inclusive, YYYY-MM-DD).
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path


def _safe(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", token).strip("_")


class RangeCoverage:
    """Union-of-intervals record of fetched date ranges, persisted as JSON."""

    def __init__(self, cache_dir: str | Path):
        self.dir = Path(cache_dir)

    def path(self, symbol: str, tf_name: str) -> Path:
        return self.dir / f"{_safe(symbol)}__{_safe(tf_name)}.ranges.json"

    def _load(self, symbol: str, tf_name: str) -> list[list[str]]:
        p = self.path(symbol, tf_name)
        if not p.is_file():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return [[str(a), str(b)] for a, b in data]
        except Exception:
            return []

    def covered(self, symbol: str, tf_name: str, start_date: str, end_date: str) -> bool:
        """True if [start_date, end_date] falls entirely within one fetched interval."""
        for lo, hi in self._load(symbol, tf_name):
            if lo <= start_date and end_date <= hi:
                return True
        return False

    def reset(self, symbol: str, tf_name: str) -> None:
        """Forget every fetched interval for (symbol, tf).

        Called when the cache's FEED_VERSION no longer matches — the bars those intervals refer
        to are unreadable, so claiming to have fetched them would strand the caller with an empty
        frame instead of a re-pull. Absent file = already reset.
        """
        self.path(symbol, tf_name).unlink(missing_ok=True)

    def record(self, symbol: str, tf_name: str, start_date: str, end_date: str) -> None:
        """Add [start_date, end_date] to the coverage and merge overlapping/adjacent
        intervals, then persist."""
        intervals = self._load(symbol, tf_name)
        intervals.append([start_date, end_date])
        merged = _merge_intervals(intervals)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path(symbol, tf_name).write_text(json.dumps(merged), encoding="utf-8")


def _merge_intervals(intervals: list[list[str]]) -> list[list[str]]:
    """Merge overlapping OR calendar-adjacent date intervals. Dates are ISO
    strings (lexicographic order == chronological order). Adjacency matters:
    fetching [.., Jan-31] then [Feb-01, ..] leaves no gap, so the two become one
    interval and a later query straddling the boundary reads as covered."""
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda iv: iv[0])
    merged = [list(ordered[0])]
    for lo, hi in ordered[1:]:
        last = merged[-1]
        # touches if lo is on/before (last_hi + 1 day)
        next_day = (date.fromisoformat(last[1]) + timedelta(days=1)).isoformat()
        if lo <= next_day:
            if hi > last[1]:
                last[1] = hi
        else:
            merged.append([lo, hi])
    return merged
