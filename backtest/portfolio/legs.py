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
from pathlib import Path
from typing import Any, Iterator

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.replay import EngineStack, build_strategy, iter_bars  # noqa: E402

__all__ = ["StrategyLeg", "build_leg"]


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


def build_leg(
    name: str, strategy_cls, config, df, *, account, initial_capital: float, cost_profile=None
) -> StrategyLeg:
    """Construct one leg bound to `account`.

    `name` is the leg's key in the account and must be distinct within a stack — the account
    holds one open position per key, so a duplicate would overwrite a live reservation and the
    risk cap would under-count the open risk while reporting itself enforced.
    """
    _refuse_unreplayable(name, config)
    strategy = build_strategy(
        strategy_cls,
        config,
        initial_capital=initial_capital,
        cost_profile=cost_profile,
        account=account,
        leg=name,
    )
    return StrategyLeg(name, strategy, df)


def _refuse_unreplayable(name: str, config) -> None:
    """Refuse a config this simulator structurally cannot run.

    A leg is ONE bar frame. `mpc_sos_fade`'s `exec_secondary` (the 1-minute re-entry) needs a
    second stream through `run_dual`, and the merged clock steps a leg with one bar at a time.
    Replaying it single-stream is the dangerous option, not refusing: the leg comes back
    primary-only while every figure it is compared against — its own solo control, the screen,
    the shipped baseline — has the re-entries in it. Same refusal `optimizer.run_sweep` makes,
    for the same reason.
    """
    if getattr(config, "exec_secondary", False):
        raise ValueError(
            f"leg {name!r}: exec_secondary is on and a shared-account stack cannot run it — the "
            f"1m re-entry needs a second bar stream (run_dual) and a leg is one frame. This leg "
            f"would be primary-only while everything it is compared against is not. Set "
            f"exec_secondary=False on this leg's config."
        )
