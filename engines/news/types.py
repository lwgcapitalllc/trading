"""
news/types.py — plain data containers for the economic-calendar (news) engine.

No behavior of consequence lives here; the engine's state machine is in engine.py. Five containers:

  Impact — the folder colour of an event (High/Medium/Low), plus NONE for holidays / non-economic /
    unknown so a `min_impact >= LOW` policy never trips on them. Ordered (IntEnum) so a policy can
    say "block anything at or above MEDIUM" with a `>=`.

  NewsEvent — one scheduled calendar event: its UTC time (epoch ms, == Pine `time` convention), the
    currency it moves (Forex Factory's `country` field is a currency code — USD/EUR/GBP…), its
    impact, title, and the forecast/previous/actual strings as the source gives them (units kept,
    no numeric parsing — that is a consumer's job). This is the engine's raw input and the store's
    record. Frozen + hashable so it de-dupes cleanly by `key()`.

  NewsPolicy — the bot-owned rule that turns raw events into a trade blackout: which currencies
    matter, the minimum impact to react to, and how many minutes before/after an event to stay out.
    The engine reports facts; the bot owns the policy — same split as each bot owning its own
    REGIME_RISK_TABLE. `NewsPolicy.gold()` is the sensible XAUUSD default (USD, High, ±30 min).

  NewsEvents — the engine's per-bar OUTPUT: the blackout flag the bot gates on, whether this bar is
    even covered by fetched data (drives the "news starts here" boundary), the three phases the user
    asked for — next (coming up), active (happening now), last (finished) — with minutes-to/-since,
    and the blackout enter/exit + "just released" edges. No visuals — the vertical coverage line a
    backtest UI draws reads `has_coverage` / the engine's `coverage_start_ms`; it is not drawn here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Tuple


class Impact(IntEnum):
    """Event importance, ordered so policies can compare with `>=`. NONE (0) covers holidays,
    non-economic entries, and anything unrecognised — below LOW, so a `min_impact >= LOW` policy
    ignores them by default."""

    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @classmethod
    def parse(cls, s: Optional[str]) -> "Impact":
        """Normalise a source impact string ("High"/"Medium"/"Low"/"Holiday"/"") to an Impact."""
        key = (s or "").strip().lower()
        return {
            "high": cls.HIGH,
            "medium": cls.MEDIUM,
            "low": cls.LOW,
        }.get(key, cls.NONE)


@dataclass(frozen=True)
class NewsEvent:
    """One scheduled economic-calendar event.

    `timestamp_ms` is the event's UTC time in epoch milliseconds (the same convention the sessions
    engine takes — Pine `time`). `currency` is the ISO currency the event moves (Forex Factory's
    `country` field is really a currency code). `forecast`/`previous`/`actual` are the raw source
    strings (e.g. "168K", "3.2%"), or None when the source omits them; `actual` fills in only after
    the release. Frozen + hashable so repeated fetches de-dupe by `key()`.
    """

    timestamp_ms: int
    currency: str
    impact: Impact
    title: str
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    is_holiday: bool = (
        False  # a bank holiday (all-day, market thin/closed) — gated whole-day, not ±window
    )
    category: Optional[str] = None  # display-only grouping label (e.g. "Labor", "Prices"); a source
    #                                 sets it if it has one, else None. The engine never reads it.

    def key(self) -> Tuple[int, str, str]:
        """Stable identity for de-duping across fetches: (time, currency, title). A later fetch of
        the same event (e.g. once `actual` is published) replaces the earlier one under this key."""
        return (self.timestamp_ms, self.currency, self.title)

    def to_dict(self) -> dict:
        return {
            "timestamp_ms": self.timestamp_ms,
            "currency": self.currency,
            "impact": int(self.impact),
            "title": self.title,
            "forecast": self.forecast,
            "previous": self.previous,
            "actual": self.actual,
            "is_holiday": self.is_holiday,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NewsEvent":
        return cls(
            timestamp_ms=int(d["timestamp_ms"]),
            currency=d["currency"],
            impact=Impact(int(d["impact"])),
            title=d["title"],
            forecast=d.get("forecast"),
            previous=d.get("previous"),
            actual=d.get("actual"),
            is_holiday=bool(d.get("is_holiday", False)),
            category=d.get("category"),
        )


@dataclass(frozen=True)
class NewsPolicy:
    """The bot-owned rule that turns raw events into a trade blackout.

    A *timed* event is relevant when its impact is `>= min_impact` and (if `currencies` is non-empty)
    its currency is in `currencies`; it blacks out [event - pre_minutes, event + post_minutes]. A
    *bank holiday* (`ev.is_holiday`) for a matching currency is ALWAYS reported (`is_holiday` /
    `active_holiday`) so the strategy can decide for itself; it is folded into `in_blackout` only if
    the bot opts in with `block_holidays=True` (default OFF — the engine reports, the bot decides).
    An empty `currencies` set means "all currencies". The engine owns none of this — a bot constructs
    the policy it wants and hands it in, exactly like REGIME_RISK_TABLE.
    """

    currencies: frozenset = frozenset()
    min_impact: Impact = Impact.HIGH
    pre_minutes: int = 30
    post_minutes: int = 30
    block_holidays: bool = (
        False  # opt-in: also fold a matching bank holiday's whole day into in_blackout
    )

    def _currency_ok(self, ev: NewsEvent) -> bool:
        return (not self.currencies) or ev.currency in self.currencies

    def matches(self, ev: NewsEvent) -> bool:
        """True if `ev` is a relevant *timed* release (impact + currency filter). Holidays are NOT
        timed events — they are reported via `is_relevant_holiday` and only optionally blacked out."""
        if ev.is_holiday:
            return False
        if ev.impact < self.min_impact:
            return False
        return self._currency_ok(ev)

    def is_relevant_holiday(self, ev: NewsEvent) -> bool:
        """True if `ev` is a bank holiday for a currency this policy cares about. This drives the
        `is_holiday` REPORT and is independent of `block_holidays` — reporting is always on; whether
        it blocks trading is the bot's separate choice."""
        return ev.is_holiday and self._currency_ok(ev)

    @classmethod
    def usd(
        cls, pre_minutes: int = 30, post_minutes: int = 30, block_holidays: bool = False
    ) -> "NewsPolicy":
        """High-impact USD events, ±`pre`/`post` minutes. The right default for anything the US macro
        calendar whips around the NY session — gold (XAUUSD/GC), US index futures (ES/NQ), crude
        (CL), treasuries — since Forex Factory is a macro calendar, not an FX-only one. Bank holidays
        for USD are always REPORTED (`is_holiday`); pass `block_holidays=True` if you also want them
        folded into `in_blackout`. It does NOT carry single-stock earnings or unscheduled headlines.
        Widen `currencies` per instrument (EUR for the DAX, GBP for the FTSE, JPY for the Nikkei)."""
        return cls(
            currencies=frozenset({"USD"}),
            min_impact=Impact.HIGH,
            pre_minutes=pre_minutes,
            post_minutes=post_minutes,
            block_holidays=block_holidays,
        )

    # Back-compat / readability alias: gold is just the USD preset (gold tracks the dollar).
    gold = usd


@dataclass
class NewsEvents:
    """The news engine's per-bar output — the blackout gate + coverage + the three phases + edges.

    Gate / coverage:
      in_blackout    — THE flag a bot gates on: inside a relevant timed event's [pre, post] window,
                       OR on a blocked bank holiday (whole day), AND we have data for this bar. False
                       whenever `has_coverage` is False, so a backtest over dates with no fetched
                       calendar trades normally (filter off by default).
      has_coverage   — this bar's timestamp falls inside a fetched date range. When False, the news
                       filter is inert; the earliest covered ms (engine.coverage_start_ms) is where a
                       backtest UI draws its "news data starts here" vertical line.
      is_holiday     — this bar's day is a bank holiday the policy blocks (whole-day blackout).
      active_holiday — the holiday event making it so (None when is_holiday is False).

    Phases (relevant events only):
      next_event / minutes_to_next      — the nearest upcoming event (coming up)
      active_event                      — the event whose blackout window contains this bar (now), or
                                          None; when several overlap, the highest-impact / nearest one
      last_event / minutes_since_last   — the most recent event at or before this bar (finished)

    Edges (this bar):
      entered_blackout / exited_blackout — blackout state flipped on this bar
      released                           — relevant events whose time fell in (prev bar, this bar] —
                                           i.e. just went live / `actual` is now due
    """

    has_coverage: bool = False
    in_blackout: bool = False

    is_holiday: bool = False
    active_holiday: Optional[NewsEvent] = None

    next_event: Optional[NewsEvent] = None
    minutes_to_next: Optional[float] = None

    active_event: Optional[NewsEvent] = None

    last_event: Optional[NewsEvent] = None
    minutes_since_last: Optional[float] = None

    entered_blackout: bool = False
    exited_blackout: bool = False
    released: List[NewsEvent] = field(default_factory=list)
