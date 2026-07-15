"""
fair_value_gaps/ — the fair-value-gap engine subsystem.

Turns the bar stream into fair-value-gap LEVEL EVENTS — a price void left by a 3-candle imbalance
(LuxAlgo definition), and the bar a candle later CLOSES fully past it (mitigation). Colours, boxes
and the directional visibility filter are out of scope; this is the trading-signal layer, not the
drawing layer.

Ported line-by-line from indicators/mpc_assistant.pine's FVG block. Standalone and OHLC-only — it
depends on no other engine (a sibling of order_blocks in shape, but it reads price patterns
directly, not structure). The optional directional filter in the Pine is drawing-only, so it is not
reproduced here; each emitted gap carries its `is_bullish` flag and the consumer decides alignment.

Public API:
    from fair_value_gaps import FairValueGapEngine

    fvg = FairValueGapEngine()          # max_count=6, threshold_pct=0.1 — the Pine defaults
    # each closed bar, in order:
    ev = fvg.update(bar.index, bar.open, bar.high, bar.low, bar.close)
    for g in ev.formed:                 # gaps created THIS bar
        g.top, g.bottom, g.is_bullish
    for g in ev.mitigated:              # gaps closed fully past (mitigated) THIS bar
        ...
    ev.active                           # current live gaps (oldest-first)
"""

from .engine import FairValueGapEngine
from .types import FairValueGap, FvgEvents

__all__ = [
    "FairValueGapEngine",
    "FairValueGap",
    "FvgEvents",
]
