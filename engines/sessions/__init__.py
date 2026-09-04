"""
sessions/ — the trading-sessions / kill-zones / NY-range engine subsystem.

Turns a bar's wall-clock timestamp into session CLOCK EVENTS — which sessions (Tokyo/London/
New York) and kill zones are open, session open/close edges carrying each session's finalized
high/low, and the NY opening-range high/low. The signal is the event/flag, not the drawing; boxes,
lines and colours are out of scope.

Ported from indicators/engines/mpc_jarvis.pine (session windows, SESSION H/L TRACKING, KILL ZONES,
NY RANGE BOX). Standalone — depends on nothing but the bar's timestamp + high/low. It is a
prerequisite for the session-scoped parts of the future Liquidity engine (session H/L levels) and
the future VWAP engine (session anchor).

Public API:
    from sessions import SessionEngine, SessionSpec, SessionEvents, SessionRange

    se = SessionEngine()             # Pine defaults: Tokyo/London/NY each in its own city's zone
    # each closed bar (timestamp is epoch MILLISECONDS, UTC — exactly Pine's `time`):
    ev = se.update(bar.index, bar.timestamp_ms, bar.high, bar.low)
    ev.in_ny, ev.in_killzone         # clock flags for this bar (state)
    ev.ny_range_high, ev.ny_range_low
    for name in ev.opened:           # sessions that opened this bar (edge)
        ...
    for r in ev.closed:              # sessions that closed this bar, with finalized high/low (edge)
        r.name, r.high, r.low
    se.current_range("NY")           # live running high/low for a session (read)
"""

from .engine import SessionEngine
from .types import SessionEvents, SessionRange, SessionSpec

__all__ = [
    "SessionEngine",
    "SessionSpec",
    "SessionEvents",
    "SessionRange",
]
