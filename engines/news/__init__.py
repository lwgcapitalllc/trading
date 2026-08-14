"""
news/ — the economic-calendar (news) engine subsystem.

Turns the clock into news EVENTS the bot can gate on: for each closed bar's UTC timestamp it reports
whether trading is in a blackout around a scheduled economic release, plus the three phases —
next (coming up), active (happening now), last (finished) — and blackout enter/exit + "just
released" edges. A bot consults `in_blackout` to skip trading; the engine decides nothing itself.

Off the roadmap and NOT a Pine port — the calendar comes from an external API (the free Forex
Factory / faireconomy feed), so it is validated by unit tests + a live feed smoke test, not by Pine
parity. It is a *macro* calendar (NFP/CPI/FOMC/PCE/ISM/EIA…), keyed by currency, so it serves FX,
gold and index/rates futures alike (pick the currency per instrument); it does NOT carry single-stock
earnings or unscheduled headlines.

Three layers:
    NewsEngine  (engine.py)  — pure, deterministic, streaming: events + policy -> per-bar NewsEvents.
    sources/                 — CalendarSource interface + ForexFactorySource (free feed).
    EventStore  (store.py)   — accumulates fetches forward into local history; refresh.py drives it.

Public API:
    from news import NewsEngine, NewsPolicy, NewsEvent, NewsEvents, Impact
    from news import ForexFactorySource, EventStore

    # Live/backtest — load the accumulated store, build the engine with a bot-owned policy:
    events, covered = EventStore().load()
    eng = NewsEngine(events, policy=NewsPolicy.usd(), covered_ranges=covered)
    for bar in feed:                                  # closed bars, timestamp = epoch ms UTC
        out = eng.update(bar.index, bar.timestamp_ms)
        if out.has_coverage and out.in_blackout:      # bot's gate — stand aside
            continue
        # ...trade. Where has_coverage is False (before the store's history begins) the filter is
        #    inert, so a backtest trades normally; eng.coverage_start_ms is that boundary.
"""

from .engine import NewsEngine
from .sources import CalendarSource, FetchResult, ForexFactoryHistorySource, ForexFactorySource
from .store import EventStore
from .types import Impact, NewsEvent, NewsEvents, NewsPolicy

__all__ = [
    "NewsEngine",
    "NewsPolicy",
    "NewsEvent",
    "NewsEvents",
    "Impact",
    "CalendarSource",
    "FetchResult",
    "ForexFactorySource",
    "ForexFactoryHistorySource",
    "EventStore",
]
