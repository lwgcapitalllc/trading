"""
order_blocks/engine.py — the order-block state machine.

One stateful streaming engine, fed one closed bar at a time plus a StructureSnapshot (the
structure engine's public output for that bar). It maintains the two live OB lists (bull / bear)
and returns the OBs created / mitigated / evicted on that bar.

Ported line-by-line from indicators/mpc_assistant.pine. The OB logic lives in four Pine spots,
all sharing the SAME two arrays (activeBullOBs / activeBearOBs):

  - type OrderBlock + manageOBs + extendOBs .......... Pine 38-66
  - external-break OB creation ....................... Pine 863-895
  - internal-break OB creation ....................... Pine 1290-1317

Because both creation paths push into the same arrays (with FIFO eviction at max_active and
close-through mitigation), porting only one path would guarantee a parity mismatch with the chart
— both are ported here. As with market_structure/ and fibonacci/, do NOT "clean up" or reorder
the ported logic: the per-bar order (mitigate first, then external-bull, external-bear,
internal-bull, internal-bear creation) matches Pine's execution order and drives which OBs survive
the max_active cap.

Drawing (box.new / box.set_right / colours) is out of scope — this emits events, not visuals.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional, Tuple

from .types import OrderBlock, OrderBlockEvents, StructureSnapshot

# Pine caps the OB lookback at `lookbackIdx < 500`, then scans up to +20 bars further back, so the
# furthest bar the engine ever reads is 519 bars ago. The rolling OHLC window must hold at least
# that many bars; a little slack is harmless (bars past 519 are never indexed).
_MAX_LOOKBACK = 500          # Pine: `lookbackIdx < 500`
_SCAN_AHEAD = 20             # Pine: `math.min(lookbackIdx + 20, bar_index)`
_WINDOW = _MAX_LOOKBACK + _SCAN_AHEAD + 40   # 560 — comfortably covers the reachable range


class OrderBlockEngine:
    """Streaming order-block detector.

    Build one per symbol/timeframe, feed it one closed candle at a time as they close, in order.
    Mirrors mpc_assistant.pine's default OB settings: max_active = 6 OBs per direction,
    body_only = False (use the full candle high/low, not just the body).
    """

    def __init__(self, max_active: int = 6, body_only: bool = False,
                 window: int = _WINDOW) -> None:
        self._max_active = max_active          # Pine maxActiveOB (default 6)
        self._body_only = body_only            # Pine obBodyOnly (default false)

        # The two live OB lists, oldest-first — Pine activeBullOBs / activeBearOBs.
        self._bull: List[OrderBlock] = []
        self._bear: List[OrderBlock] = []

        # Rolling OHLC window for the bars-ago lookback. window[-1] is the current bar (0 bars
        # ago); window[-1 - i] is `i` bars ago — mirrors Pine's `open[i]` / `high[i]` / etc.
        self._window: Deque[Tuple[float, float, float, float]] = deque(maxlen=window)

        self._next_id = 0

    # ------------------------------------------------------------------
    def update(self, bar_index: int, open_: float, high: float, low: float, close: float,
               snap: StructureSnapshot) -> OrderBlockEvents:
        """Feed one closed bar (index + OHLC) plus this bar's structure snapshot."""

        # Push this bar so the bars-ago lookback (and this bar's own candle) is available.
        self._window.append((open_, high, low, close))

        events = OrderBlockEvents()

        # ── Extend + mitigate every bar, BOTH arrays, BEFORE any creation (Pine 863-866) ──
        self._extend_and_mitigate(self._bull, close, events, is_bull=True)
        self._extend_and_mitigate(self._bear, close, events, is_bull=False)

        # ── External-break OB creation (Pine 868-895) — bull first, then bear ──
        if (snap.bull_bos or snap.bull_sos) and snap.bull_bos_l_loc is not None:
            self._create(bar_index, snap.bull_bos_l_loc, is_bull=True, events=events)
        if (snap.bear_bos or snap.bear_sos) and snap.bear_bos_h_loc is not None:
            self._create(bar_index, snap.bear_bos_h_loc, is_bull=False, events=events)

        # ── Internal-break OB creation (Pine 1290-1317) — runs AFTER the external path, same
        # shared arrays, so its pushes can evict external OBs and vice versa ──
        if snap.int_bull_break and snap.int_break_origin_loc is not None:
            self._create(bar_index, snap.int_break_origin_loc, is_bull=True, events=events)
        if snap.int_bear_break and snap.int_break_origin_loc is not None:
            self._create(bar_index, snap.int_break_origin_loc, is_bull=False, events=events)

        events.active_bull = list(self._bull)
        events.active_bear = list(self._bear)
        return events

    # ------------------------------------------------------------------
    def _extend_and_mitigate(self, arr: List[OrderBlock], close: float,
                             events: OrderBlockEvents, is_bull: bool) -> None:
        """Port of Pine `extendOBs` (53-66) minus the drawing. A bull OB dies when price closes
        below its bottom; a bear OB dies when price closes above its top. Removal preserves the
        order of the survivors (Pine removes by index without reordering the rest)."""
        survivors: List[OrderBlock] = []
        for ob in arr:
            if is_bull:
                mitigated = close < ob.bottom          # Pine: close < ob.bottom
            else:
                mitigated = close > ob.top             # Pine: close > ob.top
            if mitigated:
                events.mitigated.append(ob)
            else:
                survivors.append(ob)
        arr[:] = survivors

    # ------------------------------------------------------------------
    def _create(self, bar_index: int, origin_loc: int, is_bull: bool,
                events: OrderBlockEvents) -> None:
        """Port of the OB-creation body shared by the external (868-895) and internal (1290-1317)
        Pine blocks: scan forward (older) from the break-leg origin for the first opposite-colour
        candle, and if found, drop an OB across it."""
        lookback_idx = bar_index - origin_loc
        if not (0 <= lookback_idx < _MAX_LOOKBACK):     # Pine: lookbackIdx >= 0 and lookbackIdx < 500
            return

        upper = min(lookback_idx + _SCAN_AHEAD, bar_index)  # Pine math.min(lookbackIdx + 20, bar_index)
        ob_idx: Optional[int] = None
        for i in range(lookback_idx, upper + 1):        # Pine `for i = lookbackIdx to upper` (inclusive)
            bar = self._bar_ago(i)
            if bar is None:
                continue                                # bar out of window / before history — Pine `na`
            o, _h, _l, c = bar
            if is_bull:
                if c < o:                               # Pine: close[i] < open[i]  (first DOWN candle)
                    ob_idx = i
                    break
            else:
                if c > o:                               # Pine: close[i] > open[i]  (first UP candle)
                    ob_idx = i
                    break

        if ob_idx is None:                              # Pine: not na(obIdx)
            return

        o, h, l, c = self._bar_ago(ob_idx)              # type: ignore[misc]
        if self._body_only:
            ob_top = max(o, c)                          # Pine math.max(open[obIdx], close[obIdx])
            ob_bot = min(o, c)
        else:
            ob_top = h                                  # Pine high[obIdx]
            ob_bot = l                                  # Pine low[obIdx]

        ob = OrderBlock(
            top=ob_top,
            bottom=ob_bot,
            is_bullish=is_bull,
            origin_index=bar_index - ob_idx,            # Pine box left edge = bar_index - obIdx
            created_index=bar_index,
            id=self._take_id(),
        )
        self._manage(self._bull if is_bull else self._bear, ob, events)

    # ------------------------------------------------------------------
    def _manage(self, arr: List[OrderBlock], new_ob: OrderBlock,
                events: OrderBlockEvents) -> None:
        """Port of Pine `manageOBs` (47-51): push the new OB; if the list now exceeds max_active,
        drop (evict) the oldest."""
        arr.append(new_ob)
        events.created.append(new_ob)
        if len(arr) > self._max_active:                 # Pine: array.size(arr) > maxActiveOB
            oldest = arr.pop(0)                          # Pine array.shift
            events.evicted.append(oldest)

    # ------------------------------------------------------------------
    def _bar_ago(self, i: int) -> Optional[Tuple[float, float, float, float]]:
        """The (open, high, low, close) tuple `i` bars ago, or None if outside the window /
        before the first bar — mirrors Pine's `[i]` history reference returning `na`."""
        if i < 0 or i >= len(self._window):
            return None
        return self._window[-1 - i]

    def _take_id(self) -> int:
        self._next_id += 1
        return self._next_id
