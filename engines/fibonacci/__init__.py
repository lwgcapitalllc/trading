"""
fibonacci/ — the fib engine subsystem.

Reusable fib geometry (geometry.py) plus per-fib state machines (engine.py) that turn the
market-structure engine's output into fib LEVEL EVENTS — first-touch of each level (E1-E4,
TP1-TP5, 1.0), edge-triggered. Colours and lines are out of scope; this is the trading-signal
layer, not the drawing layer.

Ported line-by-line from indicators/mpc_assistant.pine's fib blocks. Feeds off
market_structure/ via StructureSnapshot (public reads/events only — never that engine's internals).

Public API:
    from fibonacci import StructureFib, StructureSnapshot, fib_level, fib_levels

    fib = StructureFib()
    # each closed bar, after structure_engine.update(bar) -> events:
    snap = StructureSnapshot.from_engine(structure_engine, events)
    fib_events = fib.update(bar.high, bar.low, snap)
    for t in fib_events.touched:      # levels first-reached THIS bar
        ...
"""

from .geometry import fib_from_origin, fib_level, fib_levels, origin_index
from .types import (
    FibTouch,
    InternalFibEvents,
    MacroFibEvents,
    SniperFibEvents,
    StructureFibEvents,
    StructureSnapshot,
)
from .engine import InternalFib, MacroFib, SniperFib, StructureFib

__all__ = [
    "fib_level",
    "fib_levels",
    "fib_from_origin",
    "origin_index",
    "FibTouch",
    "StructureFibEvents",
    "SniperFibEvents",
    "MacroFibEvents",
    "InternalFibEvents",
    "StructureSnapshot",
    "StructureFib",
    "SniperFib",
    "MacroFib",
    "InternalFib",
]
