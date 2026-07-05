"""
market_structure — canonical market-structure (BOS/CHoCH/swing) engine for LWG Capital.

Ported from indicators/structure_engine.pine (itself extracted from indicators/mpc_assistant.pine,
validated by Aaron on a live chart at ~99.99% parity against the original "Structure OS"
TradingView indicator). See MARKET_STRUCTURE_ENGINE.md for the algorithm and CLAUDE.md for
consumers and API rules.
"""

from .engine import StructureEngine
from .types import (
    Bar,
    ExternalEvents,
    InternalEvents,
    StructureEvents,
    SwingLevel,
)

__all__ = [
    "StructureEngine",
    "Bar",
    "SwingLevel",
    "ExternalEvents",
    "InternalEvents",
    "StructureEvents",
]
