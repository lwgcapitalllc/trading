"""One merged timeline over the legs.

The legs can be different instruments and timeframes, but the shared account's balance and
open-risk total must be right at every instant a leg asks to trade. So all legs run on ONE
clock: their bar streams are merged into a single stream ordered by UTC timestamp, and a 5m
leg simply steps three times inside a 15m leg's bar.

`merge_streams` yields one `Tick` per distinct timestamp, carrying every leg that has a bar
at that instant. The simulator then processes a tick in two passes — position-updates on all
legs first, entries second — so room a closing trade frees is released BEFORE another leg is
sized against it. That release-before-entry rule lives in the simulator; the clock just gives
it every co-timed bar together. Pure, offline; a bar is any object with a `timestamp_ms`.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator

__all__ = ["Tick", "merge_streams"]


@dataclass(frozen=True)
class Tick:
    """All the legs that have a bar at one timestamp."""
    time: int                       # epoch ms
    bars: list[tuple[str, Any]]     # (leg_name, bar), one per leg present at this time


def merge_streams(
    streams: dict[str, Iterable[Any]],
    *,
    time_key: Callable[[Any], int] = lambda b: b.timestamp_ms,
) -> Iterator[Tick]:
    """K-way merge N per-leg bar streams into time-ordered `Tick`s.

    Each input stream must already be sorted by time (bar streams are). Legs that share a
    timestamp are grouped into one Tick, in the leg order the streams dict was given (a
    stable merge), so the simulator sees co-timed bars deterministically.
    """
    # a bound helper, not a bare genexp — a genexp would close over the loop's `leg` late
    # and tag every bar with the last leg.
    def _tag(leg: str, stream: Iterable[Any]):
        for b in stream:
            yield (time_key(b), leg, b)

    tagged = [_tag(leg, stream) for leg, stream in streams.items()]
    # merge on time only — never compare the bar objects (they may be un-orderable)
    merged = heapq.merge(*tagged, key=lambda x: x[0])
    for time, group in itertools.groupby(merged, key=lambda x: x[0]):
        yield Tick(time=time, bars=[(leg, b) for (_, leg, b) in group])
