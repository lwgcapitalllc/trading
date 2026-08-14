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


def build_strategy(
    strategy_cls,
    config,
    *,
    initial_capital: float,
    cost_profile=None,
    account=None,
    leg: str | None = None,
) -> Any:
    if cost_profile is None and account is None:
        return strategy_cls(config, initial_capital=initial_capital)
    try:
        params = inspect.signature(strategy_cls).parameters
    except (TypeError, ValueError):  # a C-level or otherwise unintrospectable class
        params = {}

    kwargs: dict = {"initial_capital": initial_capital}
    if cost_profile is not None:
        if "cost_profile" not in params:
            raise TypeError(
                f"{strategy_cls.__name__} does not accept `cost_profile`, but this run states "
                f"costs to charge. Add the parameter and pass it through to Execution (see "
                f"MpcSosFadeStrategy._fill_model), or run with commission and slippage at 0 — "
                f"running it as-is would silently discard the costs, which is the bug this "
                f"refuses."
            )
        kwargs["cost_profile"] = cost_profile
    if account is not None:
        # Same refusal, and for the sharper reason: a strategy that cannot take the shared
        # account falls back to its own `SoloAccount`, which has an INFINITE budget and always
        # grants full size. So the run would report a capped, shared portfolio while this leg
        # sized off the whole balance and contended with nobody — a risk cap claimed on screen
        # and enforced nowhere. Dropping the account is worse than dropping the costs.
        if "account" not in params:
            raise TypeError(
                f"{strategy_cls.__name__} does not accept `account`, but this run shares one "
                f"account between its legs. Add `account=None, leg='strat'` to its __init__ and "
                f"pass both through to Execution (see MpcSosFadeStrategy.__init__) — running it "
                f"as-is would give this leg its own uncapped balance and silently ignore the "
                f"shared risk budget."
            )
        kwargs["account"] = account
        kwargs["leg"] = leg or strategy_cls.__name__
    return strategy_cls(config, **kwargs)
