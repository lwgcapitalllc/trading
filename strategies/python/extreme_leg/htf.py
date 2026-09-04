"""The 15-minute half of the strategy, built out of the chart's own 5-minute bars.

⚠ **AGGREGATED, NEVER REQUESTED, AND THAT IS THE PINE'S DECISION RATHER THAN THIS FILE'S.** The
Pine's own header says it: a higher-timeframe request returns a VALUE, and this needs a state
machine to be FED — three closed 5-minute bars at a time, in order, with no lookahead anywhere.
Reproducing that here means the two sides can disagree about the TREND for a reason that has
nothing to do with trading logic, which is why the export twin carries the aggregated bar's own
open/high/low/close on the bar it completes. An off-by-one in where a period starts shows up
there, on the bar it happens, instead of as a missing trade eleven hours later.

⚠ **THE STRUCTURE ENGINE IS THE CANONICAL ONE, INSTANTIATED TWICE.** The Pine embeds the state
machine twice because Pine has no other way to have two of them; this side imports one class and
builds two objects. Nothing here re-implements structure — see the repo's rule 21.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Tuple

_REPO = Path(__file__).resolve().parents[3]
for _p in ("engines", "engines/market_structure"):
    _q = str(_REPO / _p)
    if _q not in sys.path:
        sys.path.insert(0, _q)

from market_structure import Bar, StructureEngine  # noqa: E402

NA = float("nan")


class HtfStructure:
    """Buckets the chart's bars into higher-timeframe candles and runs structure on them.

    The public reads are `dir`, `swing_high`, `swing_low` — the trend and the swing the setup is
    aimed at — plus `period_closed` and `done` for the harness.

    🔴 **IT READS ONE PRIVATE FIELD OF THE STRUCTURE ENGINE, DELIBERATELY AND WITH A GUARD.** The
    public event stream fires on CHANGE, so it carries "a swing was confirmed here" and not "the
    swing that is live right now" — and the live one is exactly what a target is. Rebuilding that
    state from the event stream would be a second implementation of the thing rule 21 exists to
    prevent. `backtest/tools/pre_sos_leg.py` made the same call for the same reason, and every
    measurement behind this strategy came through it. The guard below turns a rename into a loud
    failure on the first bar rather than a run that quietly scores nothing.
    """

    def __init__(self, htf_minutes: int = 15, major_length: int = 15) -> None:
        self._ms = int(htf_minutes) * 60_000
        self._eng = StructureEngine(major_length=major_length)
        if not hasattr(self._eng, "_ext") or not hasattr(self._eng._ext, "ash"):
            raise RuntimeError(
                "the structure engine no longer exposes `_ext.ash` — this strategy reads the LIVE "
                "active swing, which the public event stream does not carry (it fires on change, "
                "not on state). Re-point this at whatever replaced that field rather than "
                "rebuilding the swing state here."
            )
        self._key: Optional[int] = None
        self._o = self._h = self._l = self._c = None
        self._n = 0
        self.dir: int = 0
        self.swing_high: float = NA
        self.swing_low: float = NA
        self.period_closed: bool = False
        self.done: Optional[Tuple[float, float, float, float]] = None
        # The pivots the engine confirmed on the bar it confirmed them — exported so a tie-break
        # disagreement between this pivot rule and the Pine's hand-rolled one lands on its own
        # column instead of on a trade eleven hours downstream.
        self.pivot_high: float = NA
        self.pivot_low: float = NA

    def update(self, ts_ms: int, open_: float, high: float, low: float, close: float) -> None:
        """Feed one closed chart bar.

        ⚠ **A period is published on the FIRST bar of the NEXT one**, which is what the Pine does
        and is the only non-repainting way to do it: the bar that closes a 15-minute candle cannot
        know it closed one until the next candle opens.
        """
        key = ts_ms // self._ms
        self.period_closed = False
        self.done = None
        self.pivot_high = NA
        self.pivot_low = NA
        if key != self._key:
            if self._o is not None:
                self.done = (self._o, self._h, self._l, self._c)
                self.period_closed = True
            self._key = key
            self._o, self._h, self._l, self._c = open_, high, low, close
        else:
            self._h = max(self._h, high)
            self._l = min(self._l, low)
            self._c = close
        if not self.period_closed:
            return
        o, h, l, c = self.done
        ev = self._eng.update(Bar(index=self._n, open=o, high=h, low=l, close=c))
        self._n += 1
        ext = self._eng._ext
        self.dir = int(ext.dir or 0)
        self.swing_high = NA if ext.ash is None else float(ext.ash)
        self.swing_low = NA if ext.asl is None else float(ext.asl)
        x = ev.external
        if getattr(x, "new_swing_high", False) and ext.ash is not None:
            self.pivot_high = float(ext.ash)
        if getattr(x, "new_swing_low", False) and ext.asl is not None:
            self.pivot_low = float(ext.asl)
