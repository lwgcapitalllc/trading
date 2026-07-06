"""
news/sources/base.py — the calendar-source interface.

A source turns "some external economic calendar" into the engine's input: a list of NewsEvent plus
the date ranges that list actually covers (so a quiet-but-fetched week is not mistaken for a data
gap). Everything downstream — the store, the engine — depends only on this interface, so swapping
the free Forex Factory feed for a paid provider (Trading Economics, …) later is a new file here and
nothing else.

FetchResult carries BOTH the events and their covered ranges precisely because coverage is not
derivable from the events alone: a week with no high-impact prints still counts as covered.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Tuple

from ..types import NewsEvent

Interval = Tuple[int, int]


@dataclass
class FetchResult:
    """One fetch's payload: the events pulled, and the [lo, hi] epoch-ms date ranges they cover."""

    events: List[NewsEvent] = field(default_factory=list)
    covered_ranges: List[Interval] = field(default_factory=list)


class CalendarSource(ABC):
    """A provider of economic-calendar events. Implementations must be side-effect-free apart from
    the network fetch itself, and must normalise every provider quirk into plain NewsEvent objects
    (UTC epoch-ms times, currency codes, Impact enum) so the engine never sees a provider detail."""

    @abstractmethod
    def fetch(self) -> FetchResult:
        """Pull the calendar and return normalised events + the date ranges they cover. Raises on a
        network/parse failure — callers (refresh.py) decide whether to swallow or surface it."""
        raise NotImplementedError
