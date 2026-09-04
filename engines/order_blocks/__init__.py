"""
order_blocks/ — the order-block engine subsystem.

Turns the bar stream into order-block LEVEL EVENTS — the base candle a turn left behind once price
displaced away from it, and the bar it is later consumed on. Colours and boxes are out of scope;
this is the trading-signal layer, not the drawing layer.

Ported line-by-line from indicators/engines/mpc_jarvis.pine's OB blocks.

STANDALONE since the 2026-07-31 re-port. It used to consume market_structure/ via a
StructureSnapshot, because every block was born on a BOS/SOS/iBOS/iSOS. The Pine commented out all
four of those creation sites: blocks now come from short pivots (turns) alone, so this engine needs
no upstream engine and takes no snapshot. It is now a sibling of fair_value_gaps/ and
equal_highs_lows/ in shape — OHLC-driven, no volume, no timestamp. See CLAUDE.md.

Public API:
    from order_blocks import OrderBlockEngine

    ob = OrderBlockEngine()          # max_active=10, body_only=False — the Pine defaults
    # each closed bar, in order:
    ob_events = ob.update(bar.index, bar.open, bar.high, bar.low, bar.close)
    for o in ob_events.created:      # zones created THIS bar
        ...
    for o in ob_events.mitigated:    # zones consumed THIS bar — the signal
        ...
    ob_events.expired                # zones that simply aged out — NOT a signal
    ob_events.evicted                # zones dropped past the cap — NOT a signal
    ob_events.active_bull            # current live bull OBs (oldest-first)
"""

from .engine import OrderBlockEngine
from .types import OrderBlock, OrderBlockEvents

__all__ = [
    "OrderBlockEngine",
    "OrderBlock",
    "OrderBlockEvents",
]
