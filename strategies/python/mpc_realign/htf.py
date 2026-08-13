"""HtfStructure — the 15m external structure, aggregated from the chart's own 5m bars.

WHY THIS EXISTS. The setup reads structure on TWO frames: a 15m external false break and a
5m internal realignment. The obvious build is a dual-frame strategy, and
`backtest.optimizer.run_sweep` REFUSES those — it replays a single frame, so a dual-frame
bot is locked out of the optimizer, every sweep and the stress test's sensitivity pass.

So the strategy runs on the 5m stream and builds its own 15m bars here. This is exactly
what the Pine does with `request.security`, it is deterministic, and it keeps the strategy
single-frame from the runner's point of view.

🔴 **A 15m BAR IS PUBLISHED ONLY ONCE ITS LAST 5m BAR HAS CLOSED, AND THAT IS THE WHOLE
CORRECTNESS ARGUMENT.** Feeding a forming 15m bar to the structure engine is lookahead of
the flattering kind: the external break would be known one or two 5m bars before it could
possibly have been, and every entry after it would be priced on information the trade did
not have. The aggregator therefore emits a bar on the FIRST 5m bar of the NEXT bucket, not
on the last bar of the current one.

⚠ Buckets are aligned to the wall clock (:00/:15/:30/:45), not counted three-at-a-time
from whatever bar arrives first. A counted aggregation drifts after any gap — a weekend, a
holiday, a missing bar — and then silently builds 15m bars straddling two real ones.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[3]
_ENGINES = _ROOT / "engines"
for _p in (str(_ROOT), str(_ENGINES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from market_structure import Bar, StructureEngine  # noqa: E402

_MS_PER_MIN = 60_000


class HtfStructure:
    """Aggregate the chart frame up to `minutes` and run a StructureEngine on the result.

    `update(bar)` is called once per chart bar and returns the `ExternalEvents` of the HTF
    bar that CLOSED on this chart bar, or None on every other bar. The caller must treat
    None as "no HTF information this bar", never as "no break".
    """

    def __init__(self, minutes: int = 15, major_length: int = 10) -> None:
        self._ms = minutes * _MS_PER_MIN
        self._engine = StructureEngine(major_length=major_length)
        self._bucket: Optional[int] = None
        self._o = self._h = self._l = self._c = 0.0
        self._filling = False            # is a bucket open? NEVER infer this from a price
        self._n = 0                      # HTF bars published so far — the engine's bar index
        # The external high/low that stood at the last HTF break, latched for the target.
        self.broken_high: Optional[float] = None
        self.broken_low: Optional[float] = None

    def _bucket_of(self, time_ms: int) -> int:
        return time_ms - (time_ms % self._ms)

    def update(self, time_ms: int, o: float, h: float, l: float, c: float):
        """Fold one chart bar in. Returns ExternalEvents on an HTF close, else None."""
        b = self._bucket_of(time_ms)
        closed = None

        if self._bucket is None:
            self._bucket = b
        elif b != self._bucket:
            # The previous bucket is complete — publish it BEFORE folding this bar in.
            ev = self._engine.update(Bar(index=self._n, open=self._o, high=self._h,
                                         low=self._l, close=self._c)).external
            self._n += 1
            if ev.broken_high_price is not None:
                self.broken_high = ev.broken_high_price
            if ev.broken_low_price is not None:
                self.broken_low = ev.broken_low_price
            closed = ev
            self._bucket = b
            self._filling = False

        if not self._filling:
            self._o, self._h, self._l, self._c = o, h, l, c
            self._filling = True
        else:
            self._h = max(self._h, h)
            self._l = min(self._l, l)
            self._c = c
        return closed
