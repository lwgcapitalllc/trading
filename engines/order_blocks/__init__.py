"""
order_blocks/ — the order-block engine subsystem.

Turns the market-structure engine's output into order-block LEVEL EVENTS — a supply/demand zone
created off each structure break (external and internal), and the bar it is later mitigated
(tapped out) on. Colours and boxes are out of scope; this is the trading-signal layer, not the
drawing layer.

Ported line-by-line from indicators/mpc_assistant.pine's OB blocks. Feeds off market_structure/
via StructureSnapshot (public reads/events only — never that engine's internals). It is a sibling
of fibonacci/, not downstream of it: both consume market_structure directly.

Public API:
    from order_blocks import OrderBlockEngine, StructureSnapshot

    ob = OrderBlockEngine()          # max_active=2, body_only=False — the Pine defaults
    # each closed bar, after structure_engine.update(bar) -> events:
    snap = StructureSnapshot.from_engine(structure_engine, events)
    ob_events = ob.update(bar.index, bar.open, bar.high, bar.low, bar.close, snap)
    for o in ob_events.created:      # zones created THIS bar
        ...
    for o in ob_events.mitigated:    # zones tapped out THIS bar
        ...
    ob_events.active_bull            # current live bull OBs (oldest-first)
"""

from .engine import OrderBlockEngine
from .types import OrderBlock, OrderBlockEvents, StructureSnapshot

__all__ = [
    "OrderBlockEngine",
    "OrderBlock",
    "OrderBlockEvents",
    "StructureSnapshot",
]
