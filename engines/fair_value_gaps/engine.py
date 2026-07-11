"""
fair_value_gaps/engine.py — the fair-value-gap state machine.

One stateful streaming engine, fed one closed bar at a time (index + OHLC). It maintains the single
live gap list and returns the gaps formed / mitigated / evicted on that bar.

Ported line-by-line from indicators/mpc_assistant.pine's FVG block ("FAIR VALUE GAPS — persist until
mitigated"). The Pine keeps five parallel `var array` structures (fvgBoxes / fvgTops / fvgBots /
fvgIsBull / fvgBorn) and runs two blocks each bar:

  - Detection ....... create a bull/bear gap on a clean 3-candle displacement, then FIFO-cap the list.
  - Extend/mitigate . delete any gap price has tapped; the survivors' boxes get extended (drawing).

This engine mirrors both blocks minus the drawing. Two Pine details kept exactly, because dropping
either would diverge from the chart:

  1. The per-bar ORDER — detect + cap FIRST, then tap/mitigate — so a gap created this bar survives
     the cap and is never tapped on its own creation bar.
  2. The tap guard `bar_index > born` — a bullish gap's top IS the creation bar's low, so without
     this guard every gap would self-mitigate the instant it forms.

The `st.dir` directional-visibility filter in the Pine is drawing-only (it recolours boxes, it does
not add or remove gaps), so it is out of scope here: the engine emits every gap with its
`is_bullish` flag and a consumer decides alignment. That is why this engine is standalone — it needs
only OHLC, no structure input.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, List, Tuple

from .types import FairValueGap, FvgEvents


class FairValueGapEngine:
    """Streaming fair-value-gap detector.

    Build one per symbol/timeframe, feed it one closed candle at a time as they close, in order.
    Mirrors mpc_assistant.pine's default FVG settings: max_count = 3 gaps total, min_ticks = 0 (no
    size filter). `mintick` is the instrument's minimum price increment — only consulted when
    min_ticks > 0 (min gap size = min_ticks * mintick), so the default behaviour is mintick-agnostic.
    """

    def __init__(self, max_count: int = 3, min_ticks: int = 0, mintick: float = 0.01) -> None:
        self._max_count = max_count          # Pine fvgMaxCount (default 3)
        self._min_ticks = min_ticks          # Pine fvgMinTicks (default 0)
        self._mintick = mintick              # Pine syminfo.mintick

        # The single live gap list, oldest-first — the Pine fvg* parallel arrays as one list.
        self._active: List[FairValueGap] = []

        # Rolling OHLC window: need the current bar, one bar back ([1]) and two back ([2]).
        self._window: Deque[Tuple[float, float, float, float]] = deque(maxlen=3)

        self._next_id = 0

    # ------------------------------------------------------------------
    def update(self, bar_index: int, open_: float, high: float, low: float,
               close: float) -> FvgEvents:
        """Feed one closed bar (index + OHLC). Returns this bar's FVG events."""

        self._window.append((open_, high, low, close))
        events = FvgEvents()
        min_size = self._min_ticks * self._mintick   # Pine fvgMinSize

        # ── Detection: confirmed bars only (we only ever feed closed bars) and bar_index >= 2 so
        #    the two-bars-back candle exists (Pine `barstate.isconfirmed and bar_index >= 2`) ──
        if bar_index >= 2 and len(self._window) == 3:
            o0, h0, l0, c0 = self._window[-1]   # this bar
            o1, h1, l1, c1 = self._window[-2]   # [1]
            o2, h2, l2, c2 = self._window[-3]   # [2]

            # Clean displacement: all three candles close in the move's direction AND make
            # progressively higher (bull) / lower (bear) closes.
            bull_impulse = (c0 > o0 and c1 > o1 and c2 > o2 and c0 > c1 and c1 > c2)
            bear_impulse = (c0 < o0 and c1 < o1 and c2 < o2 and c0 < c1 and c1 < c2)

            # Bullish gap: between two-bars-back high and this bar's low (Pine: top=low, bot=high[2]).
            if bull_impulse and l0 > h2 and (l0 - h2) >= min_size:
                self._form(top=l0, bottom=h2, is_bullish=True, born=bar_index, events=events)
            # Bearish gap: between two-bars-back low and this bar's high (Pine: top=low[2], bot=high).
            if bear_impulse and h0 < l2 and (l2 - h0) >= min_size:
                self._form(top=l2, bottom=h0, is_bullish=False, born=bar_index, events=events)

            # FIFO cap: drop the oldest gaps beyond the limit (Pine `while size > fvgMaxCount: shift`).
            while len(self._active) > self._max_count:
                events.evicted.append(self._active.pop(0))

        # ── Extend/mitigate: a gap dies the moment price taps its near edge. Skipped on the gap's
        #    own creation bar via the `bar_index > born` guard (Pine's same guard) ──
        o0, h0, l0, c0 = self._window[-1]
        survivors: List[FairValueGap] = []
        for gap in self._active:
            tapped = bar_index > gap.born_index and (
                low <= gap.top if gap.is_bullish else high >= gap.bottom
            )
            if tapped:
                events.mitigated.append(gap)
            else:
                survivors.append(gap)
        self._active = survivors

        events.active = list(self._active)
        return events

    # ------------------------------------------------------------------
    def _form(self, top: float, bottom: float, is_bullish: bool, born: int,
              events: FvgEvents) -> None:
        """Push a freshly detected gap onto the live list (Pine array.push into all five arrays)."""
        gap = FairValueGap(
            top=top,
            bottom=bottom,
            is_bullish=is_bullish,
            born_index=born,
            id=self._take_id(),
        )
        self._active.append(gap)
        events.formed.append(gap)

    def _take_id(self) -> int:
        self._next_id += 1
        return self._next_id
