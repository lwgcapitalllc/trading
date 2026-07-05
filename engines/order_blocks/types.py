"""
order_blocks/types.py — plain data containers for the order-block engine.

No behavior lives here. Three kinds of container:

  OrderBlock — one supply/demand zone. Mirrors mpc_assistant.pine's `OrderBlock` type (the
    drawing-only `box bg` field is dropped; top / bottom / is_bullish kept, plus provenance
    fields — origin_index, created_index, id — so a consumer can match a created OB to the bar it
    is later mitigated on).

  StructureSnapshot — the OB engine's INPUT: the exact subset of the market-structure engine's
    PUBLIC output the OB blocks read each bar (external break flags + the leg location they scan
    back from, and the internal break flags + shared origin). Built with
    StructureSnapshot.from_engine(engine, events). This is order_blocks/'s OWN snapshot, not the
    one in fibonacci/ — the two subsystems are siblings downstream of market_structure, not a
    chain, so each keeps its own decoupled view and reads only documented public output.

  OrderBlockEvents — the OB engine's OUTPUT: which OBs were created / mitigated / evicted this
    bar (edge events), plus the current live bull/bear OB lists (state). Colours and boxes are
    deliberately absent — those are TradingView visuals; the trading signal is the events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class OrderBlock:
    """One order block — the last opposite-colour candle before an impulse that broke structure.

    A bullish OB is the last DOWN candle before an up-break (a demand zone to buy from); a bearish
    OB is the last UP candle before a down-break (a supply zone to sell from). `top`/`bottom` are
    the candle's high/low (or body extremes when body_only). Mirrors the Pine `OrderBlock` type;
    the `box bg` field is drawing-only and dropped.
    """
    top: float
    bottom: float
    is_bullish: bool
    origin_index: int      # bar index of the OB candle itself (Pine box left edge = bar_index - obIdx)
    created_index: int     # bar index of the break that created this OB (Pine box right edge at creation)
    id: int                # stable id so a consumer can match a created OB to its later mitigation


@dataclass
class StructureSnapshot:
    """Everything the OB blocks read out of the structure engine on one bar.

    Mirrors the `st.*` / internal-break fields mpc_assistant.pine's OB blocks reference. All
    optional fields are None when absent. Built from a StructureEngine + its StructureEvents for
    that bar.
    """

    # External break THIS bar + the impulse-leg location the OB scans back from. bull scans back
    # from the low leg (bull_bos_l_loc); bear scans back from the high leg (bear_bos_h_loc). These
    # are set by market_structure on any bull/bear break (BOS and SOS alike).
    bull_bos: bool = False
    bull_sos: bool = False
    bear_bos: bool = False
    bear_sos: bool = False
    bull_bos_l_loc: Optional[int] = None
    bear_bos_h_loc: Optional[int] = None

    # Internal break THIS bar + the single shared origin both internal paths scan back from
    # (mpc_assistant.pine int_bull_break / int_bear_break / int_break_origin_loc).
    int_bull_break: bool = False
    int_bear_break: bool = False
    int_break_origin_loc: Optional[int] = None

    @classmethod
    def from_engine(cls, engine, events) -> "StructureSnapshot":
        """Build the snapshot from a market_structure StructureEngine and the StructureEvents it
        just returned for this bar. `engine` is unused today (kept for signature symmetry with
        fibonacci/ and for future reads); everything the OB blocks need is on `events`."""
        e = events.external
        i = events.internal
        return cls(
            bull_bos=e.bull_bos,
            bull_sos=e.bull_sos,
            bear_bos=e.bear_bos,
            bear_sos=e.bear_sos,
            bull_bos_l_loc=e.bull_bos_l_loc,
            bear_bos_h_loc=e.bear_bos_h_loc,
            int_bull_break=i.int_bull_break,
            int_bear_break=i.int_bear_break,
            int_break_origin_loc=i.int_break_origin_loc,
        )


@dataclass
class OrderBlockEvents:
    """The OB engine's per-bar output.

    `created` / `mitigated` / `evicted` are edge events (what changed THIS bar); `active_bull` /
    `active_bear` are the current live lists (state), oldest-first, exactly mirroring Pine's
    activeBullOBs / activeBearOBs arrays after this bar.

    mitigated vs evicted are different things and kept apart on purpose:
      - mitigated: price closed through the zone's far edge (bull: close < bottom; bear:
        close > top). This is the real signal — the zone was consumed.
      - evicted: the OB simply aged out because the per-direction cap (max_active, default 6) was
        exceeded. Pine deletes the box silently; not a trading signal.
    """

    created: List[OrderBlock] = field(default_factory=list)     # OBs created THIS bar (events)
    mitigated: List[OrderBlock] = field(default_factory=list)   # OBs tapped out THIS bar (events)
    evicted: List[OrderBlock] = field(default_factory=list)     # OBs aged out (FIFO > max) THIS bar
    active_bull: List[OrderBlock] = field(default_factory=list)  # live bull OBs, oldest-first (state)
    active_bear: List[OrderBlock] = field(default_factory=list)  # live bear OBs, oldest-first (state)
