"""
news/store.py — the local event store that accumulates calendar history forward.

The free Forex Factory feed only serves ~last/this/next week, so there is no deep past to download.
This store is how "history" is built: every time refresh.py pulls the feed, it upserts the events
here, and the covered date ranges grow. Over weeks/months the store becomes the historical calendar
a backtest reads — and its earliest covered ms is the boundary before which a backtest must run
with the news filter OFF (the "news data starts here" line).

It records TWO things, because coverage is not derivable from events alone:
  * events        — de-duped by (time, currency, title); a later fetch of the same event replaces
                    the earlier one, so a published `actual` overwrites the blank pre-release row.
  * covered_ranges — the [lo, hi] epoch-ms date spans actually fetched, merged. A quiet week with no
                    high-impact prints still counts as covered, so it is not read as a data gap.

Format is plain JSON (inspectable, no dependency). Thousands of events over years is still only a
few MB. The file lives under engines/news/data/ and is git-ignored (fetched data, like exports/).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from .engine import _merge_intervals
from .sources.base import FetchResult
from .types import NewsEvent

Interval = Tuple[int, int]

DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "events.json"


class EventStore:
    """A JSON-backed, append-forward calendar store. `path` defaults to engines/news/data/events.json."""

    def __init__(self, path: os.PathLike | str = DEFAULT_PATH):
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Tuple[List[NewsEvent], List[Interval]]:
        """Return (events sorted by time, merged covered ranges). Empty if the file does not exist."""
        if not self._path.exists():
            return [], []
        with self._path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        events = [NewsEvent.from_dict(d) for d in data.get("events", [])]
        events.sort(key=lambda e: e.timestamp_ms)
        ranges = _merge_intervals(tuple(r) for r in data.get("covered_ranges", []))
        return events, ranges

    def upsert(
        self,
        events: Iterable[NewsEvent],
        covered_ranges: Sequence[Interval] = (),
    ) -> Tuple[int, int]:
        """Merge new events + covered ranges into the store and save. New events replace existing
        ones under the same (time, currency, title) key (so `actual` fills in on a re-fetch).
        Returns (total_events, added_or_updated)."""
        existing, ranges = self.load()
        by_key = {e.key(): e for e in existing}
        before = len(by_key)
        changed = 0
        for ev in events:
            k = ev.key()
            if by_key.get(k) != ev:
                changed += 1
            by_key[k] = ev
        merged_events = sorted(by_key.values(), key=lambda e: e.timestamp_ms)
        merged_ranges = _merge_intervals(list(ranges) + list(covered_ranges))
        self._save(merged_events, merged_ranges)
        # changed counts both brand-new and value-updated rows; new = len - before.
        return len(merged_events), changed

    def upsert_result(self, result: FetchResult) -> Tuple[int, int]:
        """Convenience: upsert a source's FetchResult (events + covered ranges) in one call."""
        return self.upsert(result.events, result.covered_ranges)

    def coverage_start_ms(self) -> Optional[int]:
        """Earliest covered ms in the store — the backtest 'news starts here' boundary. None if empty."""
        _, ranges = self.load()
        return ranges[0][0] if ranges else None

    def _save(self, events: List[NewsEvent], covered_ranges: List[Interval]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "events": [e.to_dict() for e in events],
            "covered_ranges": [list(r) for r in covered_ranges],
        }
        # Atomic write: temp file in the same dir, then replace — a crash never truncates the store.
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=0)
            os.replace(tmp, self._path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
