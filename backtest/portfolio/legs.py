"""One `strategies/python/` bot, wrapped as a LEG the shared-account simulator can drive.

`simulator.simulate` takes anything exposing `name` / `bars()` / `step(bar)` / `in_position()`
/ `trades`, deliberately, so it can be tested with scripted fakes. This is the adapter that
turns a real bot into one — an `EngineStack` plus the strategy, stepped exactly the way
`optimizer._replay_one` and the lab's `python_runner._replay` step it, so a leg in a stack and
the same bot run alone go down one code path.

**Each leg owns its own EngineStack**, and that is not an optimisation to remove later: the two
bots pin different engine inputs (`mpc_bleg` forces `eq_exempt_fvg` off where the A+ forces it
on), so one shared stack would replay at least one of them against a market it never saw. A leg
may also be a different symbol or timeframe, where a shared stack is not even meaningful.

Pure and offline — pandas + the replay loop, no app imports.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.replay import EngineStack, build_strategy, iter_bars  # noqa: E402

__all__ = ["DualFeedLeg", "FeedBar", "StrategyLeg", "build_leg"]


class StrategyLeg:
    """A built strategy + its engine stack + its bar frame, as one leg of a stack."""

    def __init__(self, name: str, strategy: Any, df) -> None:
        self.name = name
        self.strategy = strategy
        self._df = df
        # `stack_config()`, NOT `engine_config()` — the second is the STATIC description of the
        # Pine's engine constants, and a caller that drives `step()` with its own stack must
        # apply the per-instance layer on top (a config whose POI source is order blocks needs
        # the OB engine switched on, and a stack without it hands the strategy
        # `order_blocks=None`). Older strategies may not have the method; fall back rather than
        # require it, since `engine_config()` is the whole of the contract for them.
        cfg = (
            strategy.stack_config()
            if hasattr(strategy, "stack_config")
            else strategy.engine_config()
        )
        self._stack = EngineStack(cfg)
        # The strategy's swap clock and time stop are measured in bar durations, so the leg has
        # to state its own — a 15m leg and a 1m leg in one stack cannot share one figure.
        if len(df.index) > 1:
            strategy.execution.bar_ms = int(
                df.index.to_series().diff().min().total_seconds() * 1000
            )

    def bars(self) -> Iterator[Any]:
        return iter_bars(self._df)

    def step(self, bar) -> None:
        self.strategy.step(self._stack.step(bar))

    def in_position(self) -> bool:
        return not self.strategy.execution.is_flat

    @property
    def trades(self) -> list:
        return self.strategy.execution.trades


def _frame_ms(df) -> int:
    """One bar's duration on this frame, in ms."""
    if len(df.index) < 2:
        raise ValueError("a leg needs at least two bars to know its own timeframe")
    return int(df.index.to_series().diff().min().total_seconds() * 1000)


@dataclass(frozen=True)
class FeedBar:
    """One bar plus WHICH of a two-feed leg's streams it came from.

    A leg hands the simulator ONE stream, and the simulator merges legs on `timestamp_ms`
    alone — so a two-feed leg merges its own two frames first and has to carry the answer to
    *which frame is this* with the bar. Reading it back off the timestamp is not an option: a
    15m bar and a 5m bar share an open time four times an hour, which is exactly the pair that
    must be routed differently.
    """

    bar: Any
    fast: bool

    @property
    def timestamp_ms(self) -> int:
        return self.bar.timestamp_ms


class DualFeedLeg:
    """A leg whose strategy trades on TWO frames — a slow primary and a faster fill clock.

    🔴 **The merge is NOT reimplemented here.** `DualClock` on the strategy owns it and is the
    same object the live runner drives bar-at-a-time, so a stacked leg and the live bot order
    their two streams by one rule. A second copy of *which bar steps when* is precisely the
    duplication this repo keeps paying for.

    ⚠ **`bar_ms` is the PRIMARY's duration, never the fast frame's.** The strategy's swap clock
    and time stop are counted in primary bars; taking the merged stream's minimum gap would put
    both on the fast frame and silently shorten every hold.
    """

    def __init__(self, name: str, strategy: Any, df_primary, df_fast) -> None:
        self.name = name
        self.strategy = strategy
        self._df_primary = df_primary
        self._df_fast = df_fast
        cfg = (
            strategy.stack_config()
            if hasattr(strategy, "stack_config")
            else strategy.engine_config()
        )
        self._stack = EngineStack(cfg)
        tf_primary_ms = _frame_ms(df_primary)
        strategy.execution.bar_ms = tf_primary_ms
        self._clock = strategy.make_dual_clock(
            self._stack, tf_primary_ms=tf_primary_ms, engine_config=cfg
        )

    def bars(self) -> Iterator[FeedBar]:
        """The two frames merged, PRIMARY FIRST when both open on the same instant.

        ⚠ The order at an equal timestamp is the contract, not a detail. A fast bar is stepped
        against the last CLOSED primary context, and `DualClock.step_fast` flushes the primaries
        that have closed by its open — so a primary must be queued before the fast bar sharing
        its open time is stepped, or the flush has nothing to find.
        """
        import heapq

        slow = ((b.timestamp_ms, 0, FeedBar(b, False)) for b in iter_bars(self._df_primary))
        fast = ((b.timestamp_ms, 1, FeedBar(b, True)) for b in iter_bars(self._df_fast))
        for _, _, fb in heapq.merge(slow, fast, key=lambda x: (x[0], x[1])):
            yield fb

    def step(self, fb: FeedBar) -> None:
        if fb.fast:
            self._clock.step_fast(fb.bar)
        else:
            self._clock.push_primary(fb.bar)

    def finish(self) -> None:
        """Step whatever primary bars the fast clock never reached.

        The window's tail: the last primary bars close after the final fast bar, so nothing
        flushes them. Without this the leg silently drops its last bars — and a book that stops
        a few bars early looks exactly like a book that found no more setups.
        """
        self._clock.drain_primary()

    def in_position(self) -> bool:
        return not self.strategy.execution.is_flat

    @property
    def trades(self) -> list:
        return self.strategy.execution.trades


def build_leg(
    name: str,
    strategy_cls,
    config,
    df,
    *,
    account,
    initial_capital: float,
    cost_profile=None,
    df_fast=None,
):
    """Construct one leg bound to `account`.

    `name` is the leg's key in the account and must be distinct within a stack — the account
    holds one open position per key, so a duplicate would overwrite a live reservation and the
    risk cap would under-count the open risk while reporting itself enforced.

    `df_fast` is the SECOND bar frame for a strategy that wants one. Supply it and the leg is a
    `DualFeedLeg`; leave it out and a config needing one is refused rather than run half.
    """
    _refuse_unreplayable(name, config, df_fast=df_fast)
    strategy = build_strategy(
        strategy_cls,
        config,
        initial_capital=initial_capital,
        cost_profile=cost_profile,
        account=account,
        leg=name,
    )
    if df_fast is not None and getattr(strategy, "make_dual_clock", None) is not None:
        return DualFeedLeg(name, strategy, df, df_fast)
    return StrategyLeg(name, strategy, df)


def _refuse_unreplayable(name: str, config, *, df_fast=None) -> None:
    """Refuse a config this simulator structurally cannot run.

    A leg is ONE bar frame. `mpc_sos_fade`'s `exec_secondary` (the 1-minute re-entry) needs a
    second stream through `run_dual`, and the merged clock steps a leg with one bar at a time.
    Replaying it single-stream is the dangerous option, not refusing: the leg comes back
    primary-only while every figure it is compared against — its own solo control, the screen,
    the shipped baseline — has the re-entries in it. Same refusal `optimizer.run_sweep` makes,
    for the same reason.
    """
    if getattr(config, "exec_secondary", False) and df_fast is None:
        raise ValueError(
            f"leg {name!r}: exec_secondary is on but no second bar frame was supplied, and this "
            f"leg would run primary-only while everything it is compared against — its own solo "
            f"control, the screen, the shipped baseline — has the re-entries in it. Give the leg "
            f"its fast frame (LegSpec.df_fast) or set exec_secondary=False on its config."
        )
    # 🔴 The strategy-page recovery switch is INERT in a stack and says nothing about it. That
    # switch runs through `finalize(df)`, a hook nothing here calls — the simulator steps bars and
    # never drives `run()` — so the leg comes back with the recovery trades simply MISSING. No
    # error, no empty list to notice, just a smaller book than the same settings produce anywhere
    # else. It is refused rather than ignored because the two live paths disagree about what the
    # same tick box means, and the quiet one is the one that reaches a comparison table.
    #
    # ⚠ The recovery belongs in a stack as its own LEG (`LegSpec.source`), which is the version
    # that competes for the budget. The switch cannot compete by construction: it reads a book
    # that has already finished.
    if getattr(config, "exec_recovery", False):
        raise ValueError(
            f"leg {name!r}: exec_recovery is on, and in a shared-account stack that switch does "
            f"NOTHING — it runs from a finalize hook the simulator never calls, so this leg would "
            f"come back with its recovery trades silently missing. Add the recovery as its own "
            f"leg instead (LegSpec(source=...)), which is the version that competes for the "
            f"budget, and set exec_recovery=False on this leg's config."
        )
