"""
fair_value_gaps/engine.py — the fair-value-gap state machine.

One stateful streaming engine, fed one closed bar at a time (index + OHLC). It maintains the single
live gap list and returns the gaps formed / mitigated / evicted on that bar.

Ported line-by-line from indicators/mpc_assistant.pine's FVG block ("FAIR VALUE GAPS — persist until
mitigated"). The Pine keeps five parallel `var array` structures (fvgBoxes / fvgTops / fvgBots /
fvgIsBull / fvgBorn) and runs two blocks each bar:

  - Detection ....... create a bull/bear gap on a 3-candle imbalance (LuxAlgo definition), then
                      FIFO-cap the list.
  - Extend/mitigate . delete any gap a candle has CLOSED fully past; the survivors' boxes get
                      extended (drawing).

This engine mirrors both blocks minus the drawing. Two Pine details kept exactly, because dropping
either would diverge from the chart:

  1. The per-bar ORDER — detect + cap FIRST, then mitigate — so a gap created this bar survives
     the cap and is never mitigated on its own creation bar.
  2. The mitigation guard `bar_index > born` — a fresh gap's far edge can already equal the
     creation bar's close, so without this guard a gap could self-mitigate the instant it forms.

The detection rule is the LuxAlgo 3-candle imbalance, NOT a "clean impulse": the two outer candles
must not overlap (`low > high[2]` bull / `high < low[2]` bear), the middle bar's close must have
cleared the gap (`close[1] > high[2]` bull / `close[1] < low[2]` bear), and the gap must be at least
`threshold_pct`% of price. There is no body/colour or progressive-close requirement — any three bars
that leave a big-enough gap with the middle bar closing past it qualify. Mitigation is a candle
CLOSING fully past the far edge (`close <= bottom` bull / `close >= top` bear) — a mere wick into
the gap no longer removes it.

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
    Mirrors mpc_assistant.pine's default FVG settings: max_count = 10 gaps total, threshold_pct = 0.0
    (the sub-15m value the Pine uses — no minimum gap; on 15m+ the Pine passes 0.04), and
    require_close = False (the Pine default `fvgRequireClose`: the classic 3-candle FVG where bars A
    and C simply don't overlap; the middle-bar close-cleared check is OPTIONAL). Match these to the
    Pine inputs the export carried — compare_fvg.py reads them from the CSV's cfg_* columns.
    """

    def __init__(self, max_count: int = 10, threshold_pct: float = 0.0,
                 require_close: bool = False) -> None:
        self._max_count = max_count            # Pine fvgMaxCount (default 10)
        self._threshold_pct = threshold_pct    # Pine fvgThreshPct (0.0 sub-15m / 0.04 15m+)
        self._require_close = require_close     # Pine fvgRequireClose (default False = classic FVG)

        # The single live gap list, oldest-first — the Pine fvg* parallel arrays as one list.
        self._active: List[FairValueGap] = []

        # Rolling OHLC window: need the current bar, one bar back ([1]) and two back ([2]).
        self._window: Deque[Tuple[float, float, float, float]] = deque(maxlen=3)

        # EQ-coupling state for the current bar (set each update; None = exemption off).
        self._eq_levels = None
        self._eq_tol = 0.0

        self._next_id = 0

    # ------------------------------------------------------------------
    def update(self, bar_index: int, open_: float, high: float, low: float,
               close: float, eq_levels=None, eq_tol: float = 0.0) -> FvgEvents:
        """Feed one closed bar (index + OHLC). Returns this bar's FVG events.

        `eq_levels` / `eq_tol` model the Pine `eqExemptFvg` coupling: an FVG that overlaps (or sits
        within `eq_tol` of) any active Equal-High/Low level is EXEMPT from the FIFO cap — it persists
        until mitigated, exactly like mpc. Pass the EqualHighsLowsEngine's post-update active levels
        (`active_eqh + active_eql`) and its `tolerance` for this bar (run EQ BEFORE FVG, the Pine
        order). Leave them defaulted (None / 0.0) for the standalone, exemption-off behaviour — a plain
        FIFO drop-oldest, unchanged. Only the cap eviction is affected; mitigation always applies.
        """

        self._window.append((open_, high, low, close))
        self._eq_levels = eq_levels          # active EQ level prices this bar (or None = no exemption)
        self._eq_tol = eq_tol                # Pine eqTol — the proximity band for the exemption
        events = FvgEvents()

        # ── Detection: confirmed bars only (we only ever feed closed bars) and bar_index >= 2 so
        #    the two-bars-back candle exists (Pine `barstate.isconfirmed and bar_index >= 2`) ──
        if bar_index >= 2 and len(self._window) == 3:
            o0, h0, l0, c0 = self._window[-1]   # this bar
            o1, h1, l1, c1 = self._window[-2]   # [1] the middle displacement bar
            o2, h2, l2, c2 = self._window[-3]   # [2]

            # LuxAlgo 3-candle imbalance: the two outer candles don't overlap and the gap is at least
            # threshold_pct% of price. The middle bar's close clearing the gap is OPTIONAL — gated by
            # require_close, exactly the Pine `(not fvgRequireClose or close[1] > high[2])`. No
            # clean-impulse / progressive-close rule.
            # Bullish gap: between two-bars-back high and this bar's low (Pine: top=low, bot=high[2]).
            if l0 > h2 and (not self._require_close or c1 > h2) and (l0 - h2) / h2 * 100 > self._threshold_pct:
                self._form(top=l0, bottom=h2, is_bullish=True, born=bar_index, events=events)
            # Bearish gap: between two-bars-back low and this bar's high (Pine: top=low[2], bot=high).
            if h0 < l2 and (not self._require_close or c1 < l2) and (l2 - h0) / l2 * 100 > self._threshold_pct:
                self._form(top=l2, bottom=h0, is_bullish=False, born=bar_index, events=events)

            # FIFO cap: drop the OLDEST gap not exempt by the EQ coupling, beyond the limit (Pine
            # `while size > fvgMaxCount:` scanning for the oldest non-EQ gap). With no eq_levels the
            # first gap is never exempt, so this is a plain drop-oldest — identical to before.
            while len(self._active) > self._max_count:
                drop_idx = None
                for idx, gap in enumerate(self._active):
                    if not self._near_eq(gap):
                        drop_idx = idx
                        break
                if drop_idx is None:
                    break                       # every remaining gap is behind liquidity — keep them all
                events.evicted.append(self._active.pop(drop_idx))

        # ── Extend/mitigate: a gap dies only when a candle CLOSES fully past its far edge (bull:
        #    close <= bottom; bear: close >= top) — a wick into the gap leaves it alive. Skipped on
        #    the gap's own creation bar via the `bar_index > born` guard (Pine's same guard) ──
        survivors: List[FairValueGap] = []
        for gap in self._active:
            closed_past = bar_index > gap.born_index and (
                close <= gap.bottom if gap.is_bullish else close >= gap.top
            )
            if closed_past:
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

    def _near_eq(self, gap: "FairValueGap") -> bool:
        """Pine f_fvgNearEq: does any active EQ level sit within `eq_tol` of this gap's span?

        True = the gap is behind liquidity and exempt from the cap. False whenever no EQ levels were
        passed (the standalone default), so eviction stays a plain drop-oldest.
        """
        levels = self._eq_levels
        if not levels:
            return False
        tol = self._eq_tol
        lo = gap.bottom - tol
        hi = gap.top + tol
        return any(lo <= lvl <= hi for lvl in levels)

    def _take_id(self) -> int:
        self._next_id += 1
        return self._next_id
