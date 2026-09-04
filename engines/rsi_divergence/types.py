"""
rsi_divergence/types.py — plain data containers for the RSI-divergence engine.

No behavior lives here. Two kinds of container:

  RsiDivergence — one confirmed regular divergence at the extremes: two consecutive RSI pivots
    (of the same side) where price and RSI disagree. Mirrors the anchor pair the Pine draws a
    dotted line between (`divPrev*` → the newly confirmed pivot) in mpc_jarvis.pine's RSI
    DIVERGENCE block; the drawing-only `line`/`label` handles are dropped. A **bullish** divergence
    is a lower price low with a higher RSI low, the lower of the two RSI lows coming from oversold;
    a **bearish** one mirrors it from overbought.

  RsiDivEvents — the engine's OUTPUT per bar: any divergences confirmed THIS bar (edge events),
    plus the live confluence flags (`bull_active` / `bear_active`, true for `valid_bars` bars after
    a divergence's pivot) and the current RSI value (diagnostic). Colours, lines and labels are
    deliberately absent — those are TradingView visuals; the signal is the event + the live flag a
    consumer (e.g. the A+ setup row) reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RsiDivergence:
    """One confirmed regular RSI divergence — the pair of pivots it connects.

    A **bullish** divergence: price prints a LOWER low (`pivot_price < prev_price`) while RSI prints
    a HIGHER low (`pivot_rsi > prev_rsi`), with the lower of the two RSI lows ≤ the oversold level.
    A **bearish** divergence mirrors it: a HIGHER price high with a LOWER RSI high, the higher of the
    two RSI highs ≥ the overbought level.

    `pivot_*` is the newly confirmed pivot (the "now" end of the line, `divPivotLen` bars behind the
    confirmation bar); `prev_*` is the immediately preceding pivot of the same side (the other end).
    `*_bar` are absolute bar indices; `*_price` is the bar's price extreme; `*_rsi` is the RSI value.
    """

    is_bullish: bool
    pivot_bar: int  # the confirmed pivot bar (Pine _pBar / lastBull|BearDivBar)
    pivot_price: float  # low[divPivotLen] (bull) / high[divPivotLen] (bear) at that bar
    pivot_rsi: float  # divPlRsi (bull) / divPhRsi (bear)
    prev_bar: int  # the previous same-side pivot bar (line's other end)
    prev_price: float  # divPrevPriceLow / divPrevPriceHigh
    prev_rsi: float  # divPrevRsiLow / divPrevRsiHigh
    id: int  # stable id so a consumer can track a specific divergence


@dataclass
class RsiDivEvents:
    """The RSI-divergence engine's per-bar output.

    `detected` is the edge event (divergences confirmed THIS bar — at most one bullish and one
    bearish); `bull_active` / `bear_active` are the live confluence flags (state) — true while the
    most recent divergence's pivot is within `valid_bars` bars of the current bar, exactly mirroring
    the Pine `bullDivActive` / `bearDivActive`. `rsi` is the current bar's RSI value (or None during
    warm-up) — diagnostic, not a signal.
    """

    detected: List[RsiDivergence] = field(default_factory=list)  # divergences confirmed THIS bar
    bull_active: bool = False  # live bull confluence (state)
    bear_active: bool = False  # live bear confluence (state)
    rsi: Optional[float] = None  # current RSI value (diagnostic)
    pivot_low_rsi: Optional[float] = (
        None  # RSI pivot LOW confirmed THIS bar (Pine divPlRsi), else None
    )
    pivot_high_rsi: Optional[float] = (
        None  # RSI pivot HIGH confirmed THIS bar (Pine divPhRsi), else None
    )
