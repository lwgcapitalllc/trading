"""The shared-account simulator — drive the legs through ONE account on ONE clock.

This is where the account and the clock meet. Each leg is stepped bar-by-bar over the merged
timeline; every entry goes through the shared budget, so the legs genuinely contend. It collects
the combined trade stream, each leg's own trades, and the account's contention log.

A `Leg` is anything with:
  * `name`          — its label,
  * `bars()`        — its raw bar stream (each bar has `timestamp_ms`), for the clock,
  * `step(bar)`     — advance one bar (its execution routes through the shared account),
  * `in_position()` — whether it currently holds a trade,
  * `trades`        — the list it appends closed trades to.
The real leg wraps an `EngineStack` + strategy (built as `python_runner._replay` does); Phase 2
supplies that adapter. This module stays pure so it can be tested with scripted fake legs.

**Release before entry.** At each tick the legs are ordered so those already HOLDING a position
step before flat legs. A leg is, on any one bar, either managing its open trade or trying to fill a
new one (never both). Stepping the holders first means any room a closing trade frees is released
before a flat leg is sized against it — the ordering rule the account's budget depends on, achieved
without splitting the strategy's monolithic step.

**Known v1 limit.** Two FLAT legs that fill on the exact same tick are granted first-come (the
earlier one in leg order takes room first), NOT split by weight — honouring split-by-weight for
simultaneous fills needs the strategy step split into decide/commit phases (a parity-gated refactor).
Different instruments/timeframes make exact same-tick double-fills rare; the account's `request_fills`
batch already implements the weighted split for when that refactor lands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .clock import merge_streams

__all__ = ["PortfolioResult", "simulate"]


@dataclass
class PortfolioResult:
    trades: list = field(default_factory=list)  # combined, every leg's closed trades
    per_leg: dict = field(default_factory=dict)  # leg name -> its own trades
    contention: list = field(default_factory=list)  # the account's shrink/block log
    cancelled: bool = False  # stopped early — the book is PARTIAL


_CHECK_EVERY = 512


def simulate(
    legs: Sequence[Any], account: Any, *, progress: Any = None, should_cancel: Any = None
) -> PortfolioResult:
    """Run all legs through `account` on one merged clock. `account` is a `PortfolioAccount`
    (or `SoloAccount` for a single leg). Returns the combined trades, per-leg trades, and the
    contention log.

    `progress(tick_index)` and `should_cancel() -> bool` are optional and exist for a caller
    driving this from a UI: a full-history two-leg stack is four replays over ~150,000 bars, so
    a Stop button that cannot reach the loop is a Stop button that does nothing. Both are polled
    every `_CHECK_EVERY` ticks rather than every tick — the check is cheap and the loop body is
    cheaper, so per-tick polling is measurable overhead on a run that does not cancel.

    ⚠ **A cancelled result is PARTIAL and says so** (`cancelled=True`). It holds every trade
    closed up to the tick it stopped on, which reads exactly like a complete short backtest —
    so a caller must branch on the flag rather than on the trade list, and must never persist a
    partial book as a finished one.
    """
    by_name = {leg.name: leg for leg in legs}
    streams = {leg.name: leg.bars() for leg in legs}
    cancelled = False

    # THIS loop owns the clock. Claimed once, outside the loop, so a leg stepping inside it
    # cannot stamp its own bar open over the shared tick time — see `PortfolioAccount`.
    account.clock_external = True
    for i, tick in enumerate(merge_streams(streams)):
        if i % _CHECK_EVERY == 0:
            if should_cancel is not None and should_cancel():
                cancelled = True
                break
            if progress is not None:
                progress(i)
        account.now = tick.time
        # holders before flat legs — freed room is released before any entry is sized.
        ordered = sorted(tick.bars, key=lambda lb: 0 if by_name[lb[0]].in_position() else 1)
        for name, bar in ordered:
            by_name[name].step(bar)
        # Sample what the account is CARRYING, after the tick's entries and exits. The
        # contention log only records what was refused, and a reservation is released the
        # moment a stop reaches breakeven — so a book that held two full positions every day
        # can log nothing at all. The peaks are the other half of the answer, and they only
        # exist if somebody looks: open risk is recomputed from live stops and leaves no trace.
        sample = getattr(account, "sample_exposure", None)
        if sample is not None:
            sample()

    # A two-feed leg queues its slow bars and steps them when a fast bar reaches their close, so
    # the tail of the window — the primary bars closing after the last fast bar — is still
    # pending here. `finish` steps them. Optional on the contract, because a scripted fake and
    # every single-frame leg have nothing to drain.
    if not cancelled:
        for leg in legs:
            done = getattr(leg, "finish", None)
            if done is not None:
                done()

    per_leg = {leg.name: list(leg.trades) for leg in legs}
    combined = [t for leg in legs for t in leg.trades]
    return PortfolioResult(
        trades=combined,
        per_leg=per_leg,
        contention=list(getattr(account, "contention", [])),
        cancelled=cancelled,
    )
