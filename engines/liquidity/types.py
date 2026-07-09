"""
liquidity/types.py — plain data containers for the liquidity engine.

No behavior lives here (bar a couple of tiny helpers on LiquidityLevel). Two containers:

  LiquidityLevel — one price line the market runs toward and grabs: a previous day/week high or low
    (PDH/PDL/PWH/PWL), the previous week's close (PWC), a previous-H4 high/low
    (H4 sweep target), or a finished session's high/low (Asia/London/NY H/L). Carries its price, the
    bar it was created on, its mitigation rule, and — once price takes it — the bar it was mitigated
    (swept) on. Mirrors the persisted d_hPrice / w_hPrice / h4TrackHigh / asiaHigh ... state in
    indicators/mpc_assistant.pine's liquidity blocks. Colours, lines and labels are drawing concerns
    and dropped.

  LiquidityEvents — the engine's per-bar OUTPUT: the levels created this bar (edge), the levels
    mitigated/swept this bar (edge), the levels evicted this bar (a period rolled or the new-day
    tidy removed a spent level — NOT a trading signal), and the full set of currently-active levels
    (state). The signal is the event ("PDH created at 4108", "H4 high swept — BSL"), not the box.

NON-REPAINTING BY DESIGN (Aaron's explicit decision, 2026-07-05): every HTF level is built from a
PREVIOUS, fully-completed period — the engine never forecasts the current day/week's high or low.
A live bot must never trade a level that peeked at the future. See engine.py and CLAUDE.md.

(The MONTHLY level PMH/PML was removed from the source and this engine on 2026-07-09.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Mitigation rules — how a level is "taken". Ported exactly from mpc_assistant.pine:
#   SWEEP_HIGH  a wick through the level           (high > price)                     — day/session/H4 highs
#   SWEEP_LOW   a wick through the level           (low  < price)                     — day/session/H4 lows
#   BREAK_HIGH  a body close above                 (close > price)                    — week highs
#   BREAK_LOW   a body close below                 (close < price)                    — week lows
#   NONE        never mitigated                    (PWC — a reference close, not a swept level)
#
# The close-back guard was DROPPED 2026-07-06 to match a re-pasted mpc_assistant.pine: the sweep
# rules used to require price close back the other side (high>price AND close<price); they now fire
# on the wick alone. Weekly keeps the plain close-through break rule (unchanged).
SWEEP_HIGH = "sweep_high"
SWEEP_LOW = "sweep_low"
BREAK_HIGH = "break_high"
BREAK_LOW = "break_low"
NONE = "none"


@dataclass
class LiquidityLevel:
    """One liquidity price line.

    kind    — "daily" | "weekly" | "pwc" | "h4" | "session"
    side    — "high" | "low" | "close"   (close only for PWC)
    name    — the source label: PDH/PDL, PWH/PWL, PWC, "H4 H"/"H4 L", "Asia H"/"Asia L", …
    price   — the level's price (frozen at creation; never repainted)
    rule    — the mitigation rule (one of the constants above)
    created_index    — bar index the level was created on
    session_name     — for kind=="session": "Asia" | "London" | "NY"; else None
    mitigated        — has price taken this level?
    mitigated_index  — bar index it was mitigated (swept) on, or None
    sweep_label      — for kind=="h4" only: "BSL" when the high is swept, "SSL" when the low is
                       (mirrors the labels mpc_assistant.pine prints on an H4 sweep)
    id      — stable id so a consumer can match a created level to its later mitigation
    """

    kind: str
    side: str
    name: str
    price: float
    rule: str
    created_index: int
    session_name: Optional[str] = None
    mitigated: bool = False
    mitigated_index: Optional[int] = None
    sweep_label: Optional[str] = None
    id: int = -1

    def is_taken_by(self, high: float, low: float, close: float) -> bool:
        """Would this bar's high/low/close mitigate (sweep/break) this level? Pure test — does not
        mutate. Encodes the four ported rules exactly (see the constants above)."""
        if self.rule == SWEEP_HIGH:
            return high > self.price
        if self.rule == SWEEP_LOW:
            return low < self.price
        if self.rule == BREAK_HIGH:
            return close > self.price
        if self.rule == BREAK_LOW:
            return close < self.price
        return False


@dataclass
class LiquidityEvents:
    """The liquidity engine's per-bar output — edges (created / mitigated / evicted) + state (active).

    Edges (this bar):
      created    — levels created on this bar (a period completed, or a session closed)
      mitigated  — levels price took on this bar (swept highs/lows, broken week levels)
      evicted    — levels removed on this bar because a period rolled or the new-day tidy dropped an
                   already-spent level. NOT a trading signal — a consumer must never confuse this
                   with `mitigated`.

    State (this bar):
      active     — every currently-live level (includes mitigated-but-still-shown ones, flagged
                   mitigated=True, until a period roll or the new-day tidy removes them)
    """

    created: List[LiquidityLevel] = field(default_factory=list)
    mitigated: List[LiquidityLevel] = field(default_factory=list)
    evicted: List[LiquidityLevel] = field(default_factory=list)
    active: List[LiquidityLevel] = field(default_factory=list)
