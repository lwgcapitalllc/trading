"""
equal_highs_lows/types.py — plain data containers for the Equal Highs/Lows (EQH/EQL) engine.

No behavior lives here. Two kinds of container:

  EqLevel — one active equal-highs (EQH) or equal-lows (EQL) level: the horizontal price a pair of
    near-equal consecutive swing pivots print, marking a stacked liquidity pool (EQH = buy-side
    resting above; EQL = sell-side below). Mirrors the line the Pine draws from the FIRST pivot
    (`eqPrev*Bar`) rightward until price CLOSES through it, in mpc_assistant.pine's "EQUAL HIGHS /
    LOWS" block; the drawing-only `line`/`label` handles are dropped. The level PRICE is the outer of
    the two pivots — `max` of the two highs for an EQH, `min` of the two lows for an EQL.

  EqEvents — the engine's OUTPUT per bar: any levels FORMED this bar and any MITIGATED (taken) this
    bar (edge events), plus the live active-level state (`active_eqh` / `active_eql`, oldest→newest,
    matching the Pine arrays) a consumer reads, plus two diagnostics (`tolerance` — the ATR-based
    equality band this bar; `pivot_high` / `pivot_low` — a strict price pivot confirmed this bar).
    Colours, dotted lines and labels are deliberately absent — those are TradingView visuals; the
    signal is the level event + the live active list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EqLevel:
    """One equal-highs (EQH) or equal-lows (EQL) liquidity level.

    `is_high` True = EQH (buy-side liquidity resting above), False = EQL (sell-side below).
    `price` is the level itself — `max(pivot, prev_pivot)` for an EQH, `min(...)` for an EQL, exactly
    as the Pine stores in `eqhPx` / `eqlPx`. `left_bar` is the FIRST pivot's bar (the line's left
    anchor, Pine `eqPrev*Bar`); `formed_bar` is the bar the second pivot CONFIRMED on (when the level
    printed, `pivot_len` bars after the second pivot's extreme). `id` is a stable per-engine id.
    """

    is_high: bool
    price: float
    left_bar: int  # first pivot's bar — Pine eqPrevPhBar / eqPrevPlBar
    formed_bar: int  # bar the level printed on (second pivot's confirmation bar)
    id: int  # stable id so a consumer can track a specific level


@dataclass
class EqEvents:
    """The Equal Highs/Lows engine's per-bar output.

    `formed` / `mitigated` are the edge events (levels that printed / were taken THIS bar). `active_eqh`
    / `active_eql` are the live states — the active level prices, oldest→newest, mirroring the Pine
    `eqhPx` / `eqlPx` arrays (after this bar's formation, FIFO eviction and mitigation). `tolerance` is
    the ATR(50)×mult equality band used this bar (Pine `eqTol`; 0.0 during ATR warm-up). `pivot_high`
    / `pivot_low` are a strict price pivot confirmed this bar (Pine `eqPh` / `eqPl`), else None —
    diagnostics, not signals.
    """

    formed: List[EqLevel] = field(default_factory=list)  # levels that printed THIS bar
    mitigated: List[EqLevel] = field(default_factory=list)  # levels taken (closed through) THIS bar
    active_eqh: List[float] = field(default_factory=list)  # live EQH prices, oldest→newest
    active_eql: List[float] = field(default_factory=list)  # live EQL prices, oldest→newest
    tolerance: float = 0.0  # eqTol this bar (diagnostic)
    pivot_high: Optional[float] = None  # strict price pivot high confirmed this bar
    pivot_low: Optional[float] = None  # strict price pivot low confirmed this bar
