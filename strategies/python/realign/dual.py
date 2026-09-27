"""RealignDualClock — the 5m chart and the 1m early trigger on one merged clock.

Built only for `realign_early_1m`. It answers the same interface the lab's two-stream seams drive
— `push_primary` / `step_fast` / `drain_primary`, which is what `backtest.portfolio.legs.DualFeedLeg`
calls through `make_dual_clock`, and what `RealignStrategy.run_dual` drives for a single run.

**The merge rule is SOS Fade's (`sos_fade/dual_clock.py`), stated once more here in two lines.**
Bars are stamped at their OPEN, so a 5m bar opening at `t` is only known at `t + 5m`; a 1m bar
opening at `X` is stepped once every 5m bar whose close is `<= X` has been stepped, and not
before. So every 1m bar inside a 5m bar is stepped BEFORE that 5m bar, against the tracker state
of the 5m bar that has already closed — never the forming one.

⚠ Not a subclass of that clock, deliberately: it owns SOS Fade's re-entry state machines, the
level memory and the reversal exit, none of which this bot has, and every one of which it would
construct and run against this bot's config. Only the two-line flush is shared in substance, and
`tests/test_realign.py` pins it by behaviour. ⚠ Nothing live drives this — the live `step`
refuses the early trigger, so there is no second, live, driver to keep in step with this one.
"""

from __future__ import annotations

from collections import deque, namedtuple
from typing import Any, Deque

#: The 1m bar as the entry path sees it: the 5m bar it sits inside supplies `index`, so a trade
#: record numbers bars on one frame; the time and prices are the 1m bar's own.
FastSig = namedtuple("FastSig", "index time_ms open high low close")


class RealignDualClock:
    def __init__(self, strategy, stack, *, tf_primary_ms: int) -> None:
        self._st = strategy
        self._stack = stack
        self._tf = int(tf_primary_ms)
        self._queue: Deque[Any] = deque()     # 5m bars pushed, not yet due
        self._last_index = -1                 # index of the last 5m bar STEPPED

    # ── the interface the lab's two-stream seams drive ──────────────────────
    def push_primary(self, bar) -> None:
        """Queue one 5m bar. It is stepped when a 1m bar reaches its close, or by `drain_primary`."""
        self._queue.append(bar)

    def step_fast(self, bar) -> None:
        """Flush every 5m bar CLOSED by this 1m bar's open, then offer the 1m bar to the trigger."""
        ts = int(bar.timestamp_ms)
        q = self._queue
        while q and int(q[0].timestamp_ms) + self._tf <= ts:
            self._step_primary(q.popleft())
        bucket = ts - ts % self._tf
        self._st._on_fast_bar(
            FastSig(self._last_index + 1, ts, bar.open, bar.high, bar.low, bar.close), bucket)

    def drain_primary(self) -> list:
        """Step every queued 5m bar — the window's tail, which no 1m bar reaches."""
        out = []
        while self._queue:
            out.append(self._step_primary(self._queue.popleft()))
        return out

    # ── internals ──────────────────────────────────────────────────────────
    def _step_primary(self, bar):
        dec = self._st._step_primary_bar(self._stack.step(bar), bar.timestamp_ms)
        self._last_index = bar.index
        return bar, dec
