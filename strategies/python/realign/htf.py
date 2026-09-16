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

# `realign_strategy.pine` majorLength — "Swing detection lookback, on both frames". ONE number for
# both, and `strategy.engine_config()` reads this rather than restating it: the chart frame took
# the engines' default 15 for a month because only the 15m half named a value.
MAJOR_LENGTH = 10


class HtfStructure:
    """Aggregate the chart frame up to `minutes` and run a StructureEngine on the result.

    `update(bar)` is called once per chart bar and returns the `ExternalEvents` of the HTF
    bar that CLOSED on this chart bar, or None on every other bar. The caller must treat
    None as "no HTF information this bar", never as "no break".
    """

    def __init__(self, minutes: int = 15, major_length: int = MAJOR_LENGTH) -> None:
        self._ms = minutes * _MS_PER_MIN
        self._engine = StructureEngine(major_length=major_length)
        self._bucket: Optional[int] = None
        self._o = self._h = self._l = self._c = 0.0
        self._filling = False            # is a bucket open? NEVER infer this from a price
        self._n = 0                      # HTF bars published so far — the engine's bar index
        # The external swing high/low STANDING after the last closed HTF bar — the setup's
        # target, and the Pine's `hAsh` / `hAsl`. 🔴 This was a latch of the event's broken
        # level until 2026-09-16, which the engine leaves blank on some breaks, so the target
        # silently fell back to a high remembered from an EARLIER break. The first parity
        # export disagreed on 552 armed bars; the engine's own standing swing removed all.
        self.standing_high: Optional[float] = None
        self.standing_low: Optional[float] = None
        # The HTF's last CONFIRMED swings — what `realign_strategy.pine` anchors its runner
        # trail on (`hConfHi` / `hConfLo`). Latched here so the trail can read the same frame
        # the Pine does; see `RealignConfig.realign_trail_frame` for why the two disagree.
        # ⚠ Updated only on an HTF CLOSE, which is the same no-lookahead contract the rest of
        # this class enforces: a swing confirmed by a still-forming 15m bar is not yet a fact.
        self.conf_high: Optional[float] = None
        self.conf_low: Optional[float] = None

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
            ash, asl = self._engine.active_swing_high, self._engine.active_swing_low
            self.standing_high = ash.price if ash is not None else None
            self.standing_low = asl.price if asl is not None else None
            # 🔴 READ OFF THE ENGINE, NEVER OFF `ev`. This read `getattr(ev, "last_conf_high",
            #    None)` until 2026-09-16, and `ExternalEvents` has no such field — so both
            #    anchors were None on every bar the port ever replayed, `getattr` hid it, and
            #    every "external trail frame" figure (the −15.68R) was a trail with NO structure
            #    anchor at all. Found by the first real parity export: `px_htf_conf*` differed
            #    on 20,316 of 20,316 bars with this side blank. The engine's public read is the
            #    same latched value the Pine plots as `hConfHi` / `hConfLo`.
            lch = self._engine.last_confirmed_high
            lcl = self._engine.last_confirmed_low
            self.conf_high = lch.price if lch is not None else None
            self.conf_low = lcl.price if lcl is not None else None
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
