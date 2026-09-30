"""Output types for the directional-trend engine — the JARVIS panel's BIAS and STR rows.

Every row is Optional on the snapshot, and `None` means CANNOT KNOW YET (not enough closed
periods, or a timeframe finer than the bars the engine is fed) — never "neutral". A measured
neutral is a row whose state says so. (Root CLAUDE.md rule 1.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

BULLISH = "Bullish"
BEARISH = "Bearish"
NEUTRAL = "Neutral"

# Pine `f_biasState` desc codes — the export plots these, the harness compares them.
DESC_INSIDE = 0  # "Inside <TF> Range"
DESC_CLOSE_ABOVE = 1  # "Close > Prev <TF> High"
DESC_CLOSE_BELOW = 2  # "Close < Prev <TF> Low"
DESC_SWEPT_HIGH = 3  # "Swept <TF> High"   (bearish)
DESC_SWEPT_LOW = 4  # "Swept <TF> Low"    (bullish)

# MTF structure event codes — Pine `f_mtfStruct`'s `sEv`.
EV_NONE = 0
EV_SHIFT = 1  # a break that reversed direction (SOS / CHoCH)
EV_EXPANSION = 2  # the first same-direction break after a shift
EV_CONTINUATION = 3  # any further same-direction break

_EV_LABEL = {
    EV_NONE: "—",
    EV_SHIFT: "Shift",
    EV_EXPANSION: "Expansion",
    EV_CONTINUATION: "Continuation",
}


@dataclass(frozen=True)
class BiasRow:
    """Weekly or daily bias: the last CLOSED period judged against the one before it."""

    state: str  # BULLISH / BEARISH / NEUTRAL
    desc_code: int  # DESC_*
    desc: str  # the exact text the JARVIS panel shows, e.g. "Close > Prev D High"

    @property
    def direction(self) -> int:
        return 1 if self.state == BULLISH else -1 if self.state == BEARISH else 0


@dataclass(frozen=True)
class StructureRow:
    """One timeframe's external structure: last break direction + where it sits in the sequence."""

    direction: int  # 1 bullish, -1 bearish, 0 no break yet
    event: int  # EV_*

    @property
    def state(self) -> str:
        return BULLISH if self.direction == 1 else BEARISH if self.direction == -1 else "—"

    @property
    def event_label(self) -> str:
        return _EV_LABEL[self.event]


@dataclass(frozen=True)
class TrendSnapshot:
    """The panel's five direction rows, as of the close of the last bar fed."""

    weekly: Optional[BiasRow] = None
    daily: Optional[BiasRow] = None
    h4: Optional[StructureRow] = None
    m15: Optional[StructureRow] = None
    m1: Optional[StructureRow] = None
