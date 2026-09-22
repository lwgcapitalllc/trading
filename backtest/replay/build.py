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

`timeframe_minutes` is the bar spacing the run will replay, handed to any strategy that declares
`set_timeframe_minutes`. That hook is where a strategy REFUSES a frame it cannot read (FFT needs
1-minute bars and raises on anything else). Until 2026-09-22 no lab path called it: FFT on 5m
bars ran "complete" with 0 trades, because its 1m-against-5m rule compares one series with
itself and can never pass. Pass the spacing of the frame actually LOADED (`frame_minutes`), not
the one requested — rule 3. Leaving it out constructs the strategy exactly as before.
"""

from __future__ import annotations

import inspect
from typing import Any

__all__ = ["build_strategy", "frame_minutes", "UNSTATED"]

#: "the caller expressed no opinion", which is NOT the same value as "no ceiling". `max_lots=None`
#: is a real instruction meaning *do not clamp this run at all*; leaving the parameter out means
#: *use whatever the account defaults to* (100 lots). Collapsing the two would make a run that
#: never mentioned a ceiling indistinguishable from one that deliberately removed it — rule 1.
UNSTATED: Any = object()


def frame_minutes(df) -> int | None:
    """The bar spacing of a loaded frame, in minutes: the smallest gap between two bars.

    `None` when it cannot be read (not a time-indexed frame, fewer than two bars, or no positive
    gap) — never a guess. The smallest gap, not the first: the first may span a weekend.
    """
    index = getattr(df, "index", None)
    if not hasattr(index, "to_series") or len(index) < 2:
        return None
    gap = index.to_series().diff().min()
    if not hasattr(gap, "total_seconds") or gap != gap:  # a plain-number index, or NaT
        return None
    minutes = int(gap.total_seconds() // 60)
    return minutes if minutes > 0 else None


def build_strategy(
    strategy_cls,
    config,
    *,
    initial_capital: float,
    cost_profile=None,
    account=None,
    leg: str | None = None,
    max_lots: Any = UNSTATED,
    timeframe_minutes: int | None = None,
) -> Any:
    strategy = _construct(
        strategy_cls,
        config,
        initial_capital=initial_capital,
        cost_profile=cost_profile,
        account=account,
        leg=leg,
        max_lots=max_lots,
    )
    if timeframe_minutes is not None and hasattr(strategy, "set_timeframe_minutes"):
        # Raises for a frame the strategy cannot read — and a refusal is the point: the run
        # fails with the strategy's own reason instead of completing on 0 trades.
        strategy.set_timeframe_minutes(int(timeframe_minutes))
    return strategy


def _construct(strategy_cls, config, *, initial_capital, cost_profile, account, leg, max_lots):
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
                f"SosFadeStrategy._fill_model), or run with commission and slippage at 0 — "
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
                f"pass both through to Execution (see SosFadeStrategy.__init__) — running it "
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
