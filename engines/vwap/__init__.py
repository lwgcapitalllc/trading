"""
vwap/ — the session VWAP engine subsystem.

Turns the bar stream into a running, volume-weighted average price line — the VWAP — anchored to
each new trading day, plus a derived close-vs-line cross. Ported from the one-liner
`vwapValue = ta.vwap(hlc3)` in indicators/engines/mpc_assistant.pine (line 852): a session-anchored,
volume-weighted mean of hlc3 that resets on the trading-day boundary (18:00 NY for XAUUSD — the same
boundary the liquidity engine's daily level uses).

First engine to need a VOLUME column in the feed (all prior engines used only OHLC + timestamp). For
XAUUSD that is tick volume, which is exactly what the Pine `ta.vwap` reads, so parity is unaffected.

Public API:
    from vwap import VwapEngine, VwapEvents

    vw = VwapEngine()                    # Pine defaults: hlc3, volume-weighted, 18:00-NY day anchor
    # each closed bar (timestamp is epoch MILLISECONDS, UTC — exactly Pine's `time`):
    ev = vw.update(bar.index, bar.timestamp_ms, bar.high, bar.low, bar.close, bar.volume)
    ev.value             # the session VWAP price this bar (None until first volume) — Pine-validated
    ev.anchored          # did the session reset (new trading day) on this bar? (edge)
    ev.side              # +1 close above VWAP, -1 below, 0 on it
    ev.crossed_up        # DERIVED: close crossed up through VWAP this bar (edge)
    ev.crossed_down      # DERIVED: close crossed down through VWAP this bar (edge)
"""

from .engine import VwapEngine
from .types import VwapEvents

__all__ = [
    "VwapEngine",
    "VwapEvents",
]
