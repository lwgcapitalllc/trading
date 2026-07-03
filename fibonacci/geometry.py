"""
fibonacci/geometry.py — the one reusable fib geometry core.

Every fib in the source indicator (Structure, Sniper, Macro) draws the SAME geometry: given a
high anchor, a low anchor, and a direction, each ratio maps to a price. They differ only in
which two points anchor them and which ratios they draw — never in the math below. This module
is that shared math, ported from mpc_assistant.pine:

    fiboRange      = fibo_ash - fibo_asl
    fiboStartIndex = fibo_dir == 1 ? fibo_asl_loc : fibo_ash_loc
    level          = fibo_dir == 1 ? fibo_ash - fiboRange * r
                                   : fibo_asl + fiboRange * r

Pure functions only — no state, no I/O. Keep it that way.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple


def fib_level(anchor_high: float, anchor_low: float, direction: int, ratio: float) -> float:
    """Price of a single ratio between the two anchors, in the trend direction.

    direction == 1 (bull): retracements come DOWN from the high  -> high - range*ratio
    direction == -1 (bear): retracements come UP from the low     -> low  + range*ratio
    """
    rng = anchor_high - anchor_low
    if direction == 1:
        return anchor_high - rng * ratio
    return anchor_low + rng * ratio


def fib_levels(
    anchor_high: float,
    anchor_low: float,
    direction: int,
    ratios: Iterable[Tuple[str, float]],
) -> Dict[str, float]:
    """Map each (name, ratio) to its price. `ratios` is an ordered iterable of (name, ratio)."""
    return {name: fib_level(anchor_high, anchor_low, direction, r) for name, r in ratios}


def origin_index(direction: int, anchor_high_loc: Optional[int], anchor_low_loc: Optional[int]) -> Optional[int]:
    """The bar the fib is anchored FROM (its 0.0 origin, where the leg started).

    Pine: fiboStartIndex = fibo_dir == 1 ? fibo_asl_loc : fibo_ash_loc — a bull leg starts at
    the swing low, a bear leg starts at the swing high. This bar index is what identifies the
    leg: when it changes, a new leg has started (see StructureFib origin-change reset).
    """
    return anchor_low_loc if direction == 1 else anchor_high_loc
