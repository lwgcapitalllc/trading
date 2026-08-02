"""How a strategy gets CONSTRUCTED for a replay — one definition, two callers.

`backtest.optimizer` and the lab's `python_runner` both instantiate a `LAB_STRATEGY` class, and
both may now have costs to charge. Neither can just pass `cost_profile=` unconditionally: the
kwarg is a 2026-08-01 addition and `LAB_STRATEGY` is an open contract — any package that declares
one is a valid strategy, including one written before the parameter existed.

The rule below is the whole point of the module. A strategy that cannot take a cost profile and
is not being given one is constructed exactly as before. A strategy that cannot take one while
the run STATED costs **raises**, and does not run. Silently dropping the profile there is the
defect this parameter was added to fix (the lab collected commission and slippage for months and
charged neither), and it would be reintroduced in the one place nobody would look for it.
"""

from __future__ import annotations

import inspect
from typing import Any

__all__ = ["build_strategy"]


def build_strategy(strategy_cls, config, *, initial_capital: float, cost_profile=None) -> Any:
    if cost_profile is None:
        return strategy_cls(config, initial_capital=initial_capital)
    try:
        params = inspect.signature(strategy_cls).parameters
    except (TypeError, ValueError):                # a C-level or otherwise unintrospectable class
        params = {}
    if "cost_profile" not in params:
        raise TypeError(
            f"{strategy_cls.__name__} does not accept `cost_profile`, but this run states costs "
            f"to charge. Add the parameter and pass it through to Execution (see "
            f"MpcSosFadeStrategy._fill_model), or run with commission and slippage at 0 — "
            f"running it as-is would silently discard the costs, which is the bug this refuses."
        )
    return strategy_cls(config, initial_capital=initial_capital, cost_profile=cost_profile)
