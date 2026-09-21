"""The two structure streams, derived from the CHART's own bars.

**Why this exists.** The strategy reads structure on two other timeframes through
`request.security`. Until 2026-09-20 the port could not produce either one, so the parity gate
FED both from the export and was silent about them — and the lab could not run the strategy at
all, because it would have needed three bar streams and `backtest/` replays two.

🔴 **A higher timeframe is recoverable from a lower one; a lower one is not recoverable from a
higher one.** Fifteen-minute bars are exactly three five-minute bars, so the direction stream can
be rebuilt from a 5-minute chart and MEASURED against the Pine's own column. A one-minute stream
cannot be rebuilt from anything coarser, which is the whole reason the confirmation timeframe is
the thing that has to move.

**MEASURED 2026-09-20** against `exports/golden/VANTAGE_XAUUSD_M5_20597bars.csv`: the canonical
`engines/market_structure/` engine, run on 15-minute bars resampled from that 5-minute export,
reproduces the Pine's `px_dir` on **every one of the 20,096 bars after bar 500**. All 159
disagreements sit in the first 161 bars and are the engine's own warm-up.

⚠ **The shift counter's ORIGIN differs and that is not a defect.** `request.security` runs its
function over the symbol's FULL history, so the Pine's counter had already reached 3 before the
export's first bar. The strategy never reads the absolute value — only whether it went UP since
the previous bar — so what is derived here, and what the gate compares, is the INCREMENT. Diffing
the raw counter would report a constant offset of 3 as 20,096 failures.

⚠ **This is not a second structure engine.** It resamples and aligns; `engines/market_structure/`
does the work, and its own parity gate is what proves the structure itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from engines.market_structure.engine import StructureEngine
from engines.market_structure.types import Bar

__all__ = ["StructureStream", "derive_stream", "ResampledStructure"]


@dataclass
class StructureStream:
    """One structure read, aligned to the chart's bars.

    `direction[i]` is what `request.security(sym, tf, …)` returns on chart bar `i`, and
    `shifted[i]` is whether the shift counter went up on that bar — Pine's
    `shifts > shifts[1]`, which is the only thing any rule in the strategy reads.
    """

    direction: List[int]
    shifted: List[bool]
    #: The raw counter, origin-zero. Kept for diagnostics; never diff it against the Pine's.
    count: List[int]


def derive_stream(
    times_ms: Sequence[int],
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    tf_minutes: int,
    chart_minutes: int,
    pivot_length: int = 15,
) -> StructureStream:
    """Run the canonical engine on `tf_minutes` bars built from the chart's, and align the result.

    **The alignment rule, and it is the half that decides trades.** A higher-timeframe value
    becomes visible on the chart bar that CLOSES that higher-timeframe bar; every earlier chart
    bar in the group still carries the PREVIOUS one's value. Aligning it one bar the other way
    scored 20,396 of 20,597 against the export where this scores 20,436 — close enough to look
    right and wrong on every group boundary, which is where the trades are.

    ⚠ `tf_minutes` must be a whole multiple of `chart_minutes`. Anything else is a request to
    invent bars that were never traded, and it REFUSES rather than interpolating.
    """
    if tf_minutes % chart_minutes != 0:
        raise ValueError(
            f"cannot build {tf_minutes}-minute bars from a {chart_minutes}-minute chart: "
            "a lower timeframe is not recoverable from a higher one. Move the input, or "
            "replay the finer frame."
        )

    n = len(times_ms)
    bucket_ms = tf_minutes * 60_000

    # ── resample, remembering which chart bar closes each group ──────────────────────
    group_last: List[int] = []
    o: List[float] = []
    h: List[float] = []
    lo_: List[float] = []
    c: List[float] = []
    key: Optional[int] = None
    for i in range(n):
        k = times_ms[i] // bucket_ms
        if k != key:
            key = k
            group_last.append(i)
            o.append(opens[i])
            h.append(highs[i])
            lo_.append(lows[i])
            c.append(closes[i])
        else:
            h[-1] = max(h[-1], highs[i])
            lo_[-1] = min(lo_[-1], lows[i])
            c[-1] = closes[i]
            group_last[-1] = i

    # ── the canonical engine, one call per resampled bar ─────────────────────────────
    eng = StructureEngine(pivot_length)
    g_dir: List[int] = []
    g_count: List[int] = []
    count = 0
    for j in range(len(group_last)):
        ev = eng.update(Bar(index=j, open=o[j], high=h[j], low=lo_[j], close=c[j]))
        if ev.external.bull_sos or ev.external.bear_sos:
            count += 1
        g_dir.append(eng.dir)
        g_count.append(count)

    # ── align back onto the chart's bars ─────────────────────────────────────────────
    direction = [0] * n
    counts = [0] * n
    start = 0
    for j, last in enumerate(group_last):
        prev_dir = g_dir[j - 1] if j > 0 else 0
        prev_cnt = g_count[j - 1] if j > 0 else 0
        for i in range(start, last + 1):
            if i == last:
                direction[i] = g_dir[j]
                counts[i] = g_count[j]
            else:
                direction[i] = prev_dir
                counts[i] = prev_cnt
        start = last + 1

    shifted = [False] * n
    for i in range(1, n):
        shifted[i] = counts[i] > counts[i - 1]

    return StructureStream(direction=direction, shifted=shifted, count=counts)


class ResampledStructure:
    """The same derivation, STREAMING — one bar in, `(direction, shifted)` out.

    The lab replays bar by bar and cannot hand a strategy the whole series first, so this is the
    form the live path and the lab path both use; `derive_stream` above is this class in a loop,
    and the two must never drift apart. The alignment rule is identical: a group's value becomes
    visible on the chart bar that CLOSES it, and every earlier bar in the group still carries the
    previous group's.

    ⚠ It publishes the PREVIOUS group's value until a group closes, which means the first
    `tf_minutes / chart_minutes` bars of a run publish direction 0 — "not asked yet", which is
    what a warm-up honestly is. It is never a claim that structure is flat.
    """

    def __init__(self, tf_minutes: int, chart_minutes: int, pivot_length: int = 15):
        if tf_minutes % chart_minutes != 0:
            raise ValueError(
                f"cannot build {tf_minutes}-minute bars from a {chart_minutes}-minute chart: "
                "a lower timeframe is not recoverable from a higher one."
            )
        self._bucket_ms = tf_minutes * 60_000
        self._chart_ms = chart_minutes * 60_000
        self._group = tf_minutes // chart_minutes
        self._eng = StructureEngine(pivot_length)
        self._key: Optional[int] = None
        self._j = -1
        self._o = self._h = self._l = self._c = 0.0
        #: What a chart bar inside an unfinished group sees: the last CLOSED group's read.
        self.direction = 0
        self.count = 0
        self._published_dir = 0
        self._published_count = 0

    def update(self, time_ms: int, o: float, h: float, low: float, c: float) -> tuple:
        """Feed one CHART bar. Returns `(direction, shifted)` as of that bar."""
        k = time_ms // self._bucket_ms
        if k != self._key:
            if self._key is not None:
                self._published_dir = self.direction
                self._published_count = self.count
            self._key = k
            self._o, self._h, self._l, self._c = o, h, low, c
        else:
            self._h = max(self._h, h)
            self._l = min(self._l, low)
            self._c = c

        if self._group == 1 or self._closes_group(time_ms):
            self._j += 1
            ev = self._eng.update(
                Bar(index=self._j, open=self._o, high=self._h, low=self._l, close=self._c)
            )
            rose = ev.external.bull_sos or ev.external.bear_sos
            if rose:
                self.count += 1
            self.direction = self._eng.dir
            return self.direction, bool(rose)
        return self._published_dir, False

    def _closes_group(self, time_ms: int) -> bool:
        """True when this chart bar is the LAST one of its group.

        ⚠ Measured off the clock, not off a bar count: a missing bar (a holiday, a feed gap, a
        broker's late Sunday open) leaves a short group, and counting bars would then hold the
        whole stream one group behind for the rest of the run.
        """
        nxt = time_ms + self._chart_ms
        return nxt // self._bucket_ms != time_ms // self._bucket_ms
