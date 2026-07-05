"""
sessions/types.py — plain data containers for the sessions engine.

No behavior lives here (bar the two tiny parsers on SessionSpec, which are pure string/clock
arithmetic). Three kinds of container:

  SessionSpec — one configured trading-session window: a name, a [start, end) minute window in a
    named timezone. Mirrors the per-session inputs in indicators/mpc_assistant.pine (Tokyo/London/
    New York — the display name + `input.session` string + `input.session` timezone). Colours and
    the "show" toggles are drawing concerns and dropped. The three Pine defaults are exposed as
    SessionEngine.DEFAULT_SESSIONS.

  SessionRange — one session's finalized (or in-progress) high/low with the bar span it covered.
    This is the OUTPUT the downstream Liquidity engine will consume as a session-H/L level (it adds
    the sweep/mitigation tracking; the raw high/low is computed here). Mirrors Pine's
    asiaHigh/asiaLow (+ london*/ny*) captured on the SESSION H/L TRACKING block.

  SessionEvents — the engine's per-bar OUTPUT: the clock flags for this bar (which sessions /
    kill zones are open, whether we are in the NY opening-range window, new-day / weekday), the
    live NY opening-range high/low, plus edge events — which sessions opened this bar and which
    closed (carrying their finalized SessionRange). Boxes, lines and colours are deliberately
    absent — those are TradingView visuals; the trading signal is the flags + edges.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


def _pine_session_to_minutes(session: str) -> "tuple[int, int]":
    """Parse a Pine `input.session` string ("HHMM-HHMM") into (start_minute, end_minute), each
    measured as minutes-from-midnight in the session's own timezone. The window is [start, end):
    start inclusive, end exclusive, and when end <= start it spans midnight (e.g. Tokyo 2000-0500).
    Day-of-week suffixes ("...:1234567") are not used by the mpc sessions and are not parsed."""
    start_s, end_s = session.split("-")
    start = int(start_s[:2]) * 60 + int(start_s[2:])
    end = int(end_s[:2]) * 60 + int(end_s[2:])
    return start, end


@dataclass(frozen=True)
class SessionSpec:
    """One configured session window. `start_minute`/`end_minute` are minutes-from-midnight in
    `tz_name`; the window is [start, end) and wraps past midnight when end <= start. `tz_name` is
    either a fixed GMT offset ("GMT-4", "GMT+5:30") or an IANA name ("America/New_York")."""

    name: str
    start_minute: int
    end_minute: int
    tz_name: str

    @classmethod
    def from_pine(cls, name: str, session: str, tz_name: str) -> "SessionSpec":
        """Build from the raw Pine inputs, e.g. from_pine("Asia", "2000-0500", "GMT-4")."""
        start, end = _pine_session_to_minutes(session)
        return cls(name=name, start_minute=start, end_minute=end, tz_name=tz_name)


@dataclass
class SessionRange:
    """One session's high/low over the bars it spanned.

    Emitted (finalized) on the bar a session closes; also returned live mid-session via
    SessionEngine.current_range(). `start_index` is the first in-session bar; `end_index` is the
    last in-session bar (None while the session is still open). Mirrors Pine's persisted
    asiaHigh/asiaLow etc. — the raw session extremes the Liquidity engine turns into swept levels.
    """

    name: str
    high: float
    low: float
    start_index: int
    end_index: Optional[int] = None


@dataclass
class SessionEvents:
    """The sessions engine's per-bar output — clock flags (state) + open/close edges (events).

    State (this bar):
      in_asia / in_london / in_ny         — inside each configured session window
      in_kz1 / in_kz2 / in_kz3            — inside each NY kill zone (see in_killzone)
      in_ny_range_window                  — inside the 0930-0935 NY opening-range window
      in_ny_range_extend                  — inside the 0935-1600 NY range-extend window
      is_new_day                          — NY calendar day changed vs the previous bar
      is_weekday                          — NY day is Mon-Fri
      ny_range_high / ny_range_low        — the live NY opening range (None until first formed)

    Edges (this bar):
      opened   — names of sessions that opened on this bar
      closed   — SessionRange for each session that closed on this bar (finalized high/low)
    """

    in_asia: bool = False
    in_london: bool = False
    in_ny: bool = False

    in_kz1: bool = False
    in_kz2: bool = False
    in_kz3: bool = False

    in_ny_range_window: bool = False
    in_ny_range_extend: bool = False

    is_new_day: bool = False
    is_weekday: bool = False

    ny_range_high: Optional[float] = None
    ny_range_low: Optional[float] = None

    opened: List[str] = field(default_factory=list)
    closed: List[SessionRange] = field(default_factory=list)

    @property
    def in_killzone(self) -> bool:
        """True if this bar is inside any of the three NY kill zones."""
        return self.in_kz1 or self.in_kz2 or self.in_kz3
