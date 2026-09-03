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

`max_lots` is the VENUE LOT CEILING and follows the same shape for the same reason. It is applied
by constructing the run's account here rather than by threading a parameter through five strategy
packages: the account is the single seam every strategy's sizing already reaches, so one place
honours it and no two strategies can disagree about what it means. Clamping there is also what
keeps the emulator and the broker holding the SAME quantity — clamping the ORDER instead is the
bug root `CLAUDE.md` rule 17 was written about.
"""

from __future__ import annotations

import inspect
from typing import Any

__all__ = ["build_strategy", "UNSTATED"]

#: "the caller expressed no opinion", which is NOT the same value as "no ceiling". `max_lots=None`
#: is a real instruction meaning *do not clamp this run at all*; leaving the parameter out means
#: *use whatever the account defaults to* (100 lots). Collapsing the two would make a run that
#: never mentioned a ceiling indistinguishable from one that deliberately removed it — rule 1.
UNSTATED: Any = object()


def build_strategy(
    strategy_cls,
    config,
    *,
    initial_capital: float,
    cost_profile=None,
    account=None,
    leg: str | None = None,
    max_lots: Any = UNSTATED,
) -> Any:
    own_account = False
    if max_lots is not UNSTATED:
        # A stated venue lot ceiling. It lives on the ACCOUNT, which is the one seam every
        # strategy's sizing already passes through, so honouring it here costs no per-strategy
        # wiring and cannot drift between them. See `backtest/portfolio/account.py`.
        if account is not None:
            raise ValueError(
                "state a lot ceiling or a shared account, never both. A shared account carries "
                "ONE ceiling for every leg on it; a second one named here would apply to this "
                "leg alone and the run would report a ceiling it did not enforce evenly."
            )
        from backtest.portfolio.account import SoloAccount

        account = SoloAccount(balance=initial_capital, max_lots=max_lots)
        own_account = True

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
                + (
                    "  This run states a lot ceiling, which is carried on the account, so the "
                    "same parameter is what a ceiling needs."
                    if own_account
                    else ""
                )
            )
        kwargs["account"] = account
        # ⚠ Only override the strategy's OWN default leg key when a caller named one. The
        # strategies do not agree on a default — 'strat' for most, 'recovery' for the loss
        # recovery leg — so substituting the class name for a solo account built right here
        # would silently re-file every trade under a different key for no reason. The class-name
        # fallback stays for a SHARED account, where a missing key really is a caller bug.
        if leg is not None:
            kwargs["leg"] = leg
        elif not own_account:
            kwargs["leg"] = strategy_cls.__name__
    return strategy_cls(config, **kwargs)
