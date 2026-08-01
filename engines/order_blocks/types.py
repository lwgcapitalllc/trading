"""
order_blocks/types.py — plain data containers for the order-block engine.

No behavior lives here. Two kinds of container:

  OrderBlock — one supply/demand zone. Mirrors mpc_assistant.pine's `OrderBlock` type (the
    drawing-only `box bg` field is dropped; top / bottom / is_bullish / from_break / entered kept,
    plus provenance fields — origin_index, created_index, id — so a consumer can match a created OB
    to the bar it is later mitigated on).

  OrderBlockEvents — the OB engine's OUTPUT: which OBs were created / mitigated / expired / evicted
    this bar (edge events), plus the current live bull/bear OB lists (state). Colours and boxes are
    deliberately absent — those are TradingView visuals; the trading signal is the events.

STRUCTURESNAPSHOT IS GONE (2026-07-31). It existed because every order block used to be born on a
structure break, so the engine needed the break flags + leg locations. The mpc rework commented out
all four structure-creation sites, so this engine no longer consumes engines/market_structure/ at
all — it is now STANDALONE and OHLC-driven, a sibling of fair_value_gaps/ and equal_highs_lows/ in
shape. See CLAUDE.md. If the structure source is ever restored in the Pine, restore the snapshot
with it rather than reaching into the structure engine's internals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class OrderBlock:
    """One order block — the base candle a turn left behind before price displaced away from it.

    A bullish OB sits below price (a demand zone to buy from); a bearish OB sits above (supply to
    sell from). `top`/`bottom` are the anchor candle's high/low, or its body extremes when
    `body_only`. Mirrors the Pine `OrderBlock` type; the `box bg` field is drawing-only and dropped.
    """
    top: float
    bottom: float
    is_bullish: bool
    origin_index: int      # bar index of the anchor candle itself (Pine's box left edge)
    created_index: int     # bar index the block was actually added on (Pine reads ~10 bars late)
    id: int                # stable id so a consumer can match a created OB to its later mitigation

    # Pine `fromBreak`: true = born on a BOS/SOS/iBOS/iSOS, false = born at a turn. Every live
    # source now passes false — the structure sources are commented out in the Pine — so this is
    # always False today. Kept because the Pine kept it, and because restoring the structure source
    # would immediately need it again.
    from_break: bool = False

    # Pine `entered`: has a candle CLOSED inside this zone yet — the first half of the enter-then-
    # leave mitigation rule. Latched once by the engine, never cleared. Tracked as state rather than
    # tested per bar because entering and leaving happen on DIFFERENT bars.
    entered: bool = False


@dataclass
class OrderBlockEvents:
    """The OB engine's per-bar output.

    `created` / `mitigated` / `expired` / `evicted` are edge events (what changed THIS bar);
    `active_bull` / `active_bear` are the current live lists (state), oldest-first, exactly
    mirroring Pine's activeBullOBs / activeBearOBs arrays after this bar.

    The four are kept apart on purpose — only ONE of them is a trading signal:
      - mitigated: price reached the zone and finished with it. Under the 2026-07-31 rule that is
        EITHER a close clean past the far edge, OR a bar that touched the zone and closed outside it
        (a wick-and-reject), OR a bar that closes outside after an earlier bar closed inside. This
        is the real signal — the zone was consumed.
      - expired: the block simply got old (Pine `obStale`, bar_index - origin > max_age). A block
        price never returns to can never be mitigated — BOTH halves of that rule need price at the
        zone — so age is the only thing that retires those. NOT a signal.
      - evicted: the per-direction list already held `max_active`, so the oldest was dropped FIFO
        when a newer one was pushed. Pine deletes the box silently. NOT a signal.
      - created: a new zone exists.

    Pine lumps mitigated and expired into one `if obStale or obMitigated` delete; splitting them
    here is an output-shape choice, not a logic change — the delete happens on exactly the same bar
    either way.
    """

    created: List[OrderBlock] = field(default_factory=list)      # OBs created THIS bar (events)
    mitigated: List[OrderBlock] = field(default_factory=list)    # OBs consumed THIS bar (events)
    expired: List[OrderBlock] = field(default_factory=list)      # OBs aged out THIS bar — NOT a signal
    evicted: List[OrderBlock] = field(default_factory=list)      # OBs dropped past the cap — NOT a signal
    active_bull: List[OrderBlock] = field(default_factory=list)  # live bull OBs, oldest-first (state)
    active_bear: List[OrderBlock] = field(default_factory=list)  # live bear OBs, oldest-first (state)
