"""
fair_value_gaps/types.py — plain data containers for the FVG engine.

No behavior lives here. Two kinds of container:

  FairValueGap — one fair value gap: the price void left by a clean 3-candle displacement.
    Mirrors the parallel Pine arrays in mpc_assistant.pine's FVG block (fvgTops / fvgBots /
    fvgIsBull / fvgBorn) collapsed into one object; the drawing-only `box` handle is dropped.
    `top`/`bottom` are the gap's price edges (top > bottom always); `born_index` is the bar it
    formed on; `id` is a stable id so a consumer can match a formed gap to its later mitigation.

  FvgEvents — the FVG engine's OUTPUT: which gaps formed / were mitigated (tapped) / were evicted
    (aged out past the cap) THIS bar (edge events), plus the current live gap list (state). Colours,
    boxes and the directional-visibility filter are deliberately absent — those are TradingView
    visuals; the trading signal is the events. A consumer that cares about direction reads each
    gap's `is_bullish` itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class FairValueGap:
    """One fair value gap — the void a clean 3-candle displacement leaves behind.

    A **bullish** gap is the space between candle A's high (two bars back) and candle C's low (the
    displacement bar), when the three candles closed progressively higher and never overlapped
    (`low > high[2]`): `top` = C's low, `bottom` = A's high. A **bearish** gap mirrors it: `top` =
    A's low (two bars back), `bottom` = C's high, when `high < low[2]`. Either way `top > bottom`.
    """
    top: float
    bottom: float
    is_bullish: bool
    born_index: int    # bar index the gap formed on (Pine fvgBorn)
    id: int            # stable id so a consumer can match a formed gap to its later mitigation


@dataclass
class FvgEvents:
    """The FVG engine's per-bar output.

    `formed` / `mitigated` / `evicted` are edge events (what changed THIS bar); `active` is the
    current live gap list (state), oldest-first, exactly mirroring the Pine fvg* arrays after this
    bar.

    mitigated vs evicted are different things and kept apart on purpose:
      - mitigated: price tapped the gap's near edge (bull: `low <= top`; bear: `high >= bottom`).
        This is the real signal — the gap was filled / entered. Pine deletes the box on the tap.
      - evicted: the gap simply aged out because the total cap (max_count, default 3) was exceeded
        by a newer gap. Pine array.shifts the oldest; not a trading signal.
    """

    formed: List[FairValueGap] = field(default_factory=list)      # gaps created THIS bar (events)
    mitigated: List[FairValueGap] = field(default_factory=list)   # gaps tapped out THIS bar (events)
    evicted: List[FairValueGap] = field(default_factory=list)     # gaps aged out (FIFO > max) THIS bar
    active: List[FairValueGap] = field(default_factory=list)      # live gaps, oldest-first (state)
