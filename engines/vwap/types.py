"""
vwap/types.py — plain data container for the VWAP engine.

One container, no behaviour:

  VwapEvents — the engine's per-bar OUTPUT: the session VWAP value on this bar (a running,
    volume-weighted average of hlc3 since the trading-day anchor), whether the session reset
    (re-anchored) on this bar, which side of the line the close sits, and — a DERIVED convenience —
    whether the close crossed the line this bar (up or down).

WHAT IS PINE-VALIDATED vs DERIVED
---------------------------------
`value` is the port of `ta.vwap(hlc3)` from indicators/mpc_assistant.pine (line 852) and is checked
at 100% Pine parity. `anchored` mirrors the trading-day roll the parity export also plots. The
cross fields (`side`, `crossed_up`, `crossed_down`) are a DERIVED convenience the engine adds on top
— the Pine source only DRAWS the VWAP line, it emits no cross event — so they are unit-tested here
but are NOT part of the Pine parity set. (Same split the liquidity engine used: it consumed the
sessions engine's H/L and added the sweep tracking on top.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class VwapEvents:
    """The VWAP engine's per-bar output.

    value        — the session VWAP price on this bar: sum(hlc3 * volume) / sum(volume) since the
                   trading-day anchor. None until the first bar with volume (Pine `na`).
    anchored     — did the session RESET (re-anchor) on this bar? True on the first bar of a new
                   trading day (the accumulator was cleared and restarted here). False on the very
                   first fed bar (there is no prior session to roll off — mirrors Pine's `na` roll).
    side         — where the close sits vs the line: +1 above, -1 below, 0 exactly on it (or when
                   `value` is None). State, computed each bar.
    crossed_up   — DERIVED: the close crossed from below the line to above it on this bar (edge).
    crossed_down — DERIVED: the close crossed from above the line to below it on this bar (edge).
    """

    value: Optional[float] = None
    anchored: bool = False
    side: int = 0
    crossed_up: bool = False
    crossed_down: bool = False
