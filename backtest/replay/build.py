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

`rate_provider` is the run's QUOTE-TO-ACCOUNT conversion, a `time_ms -> rate` callable from
`backtest.data.fx.rate_provider_for`. It is installed through the strategy's execution layer
(`execution.set_rate_provider`), and it follows the cost-profile rule above: a strategy that cannot
take one while the run needs one **raises**. Running it anyway would price a yen trade as though it
were dollars — the swap about 156x too large, and every trade sized by the wrong factor. `None`
(every dollar-quoted run) installs nothing and constructs the strategy exactly as before.

🔴 **Leaving it out on a symbol that needs one ALSO raises**, whichever path built the run. The
config names its symbol, so this is checkable here, and a caller that forgot is exactly the caller
that would otherwise run silently wrong. A caller that really wants the configured snapshot says so
with `backtest.data.fx.constant_rate(config.point_value)` — stated, never omitted.
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
    rate_provider=None,
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
    if rate_provider is not None:
        _install_rate(strategy, rate_provider)
    else:
        _refuse_unconverted(config)
    return strategy


def _refuse_unconverted(config) -> None:
    from backtest.data.fx import UnknownQuoteCurrency, conversion_symbol

    symbol = getattr(config, "symbol", None)
    if not symbol:
        return
    try:
        pair = conversion_symbol(str(symbol))
    except UnknownQuoteCurrency:
        # A name that is not a currency pair (an index, a future) predates this rule and keeps
        # its configured constant. The lab path refuses those in `rate_provider_for` instead.
        return
    if pair is not None:
        raise ValueError(
            f"{symbol} is not quoted in dollars and this run was given no conversion. Pass "
            f"rate_provider=backtest.data.fx.rate_provider_for(source, {symbol!r}, start, end) — "
            f"per-bar {pair[0]} — or, to use the configured snapshot knowingly, "
            f"rate_provider=constant_rate(config.point_value)."
        )


def _install_rate(strategy, rate_provider) -> None:
    execution = getattr(strategy, "execution", None)
    install = getattr(execution, "set_rate_provider", None)
    if install is None:
        raise TypeError(
            f"{type(strategy).__name__} cannot convert its P&L out of this symbol's quote "
            f"currency (its execution layer has no set_rate_provider), and this run is on a "
            f"symbol that is not quoted in dollars. Running it would price every trade as though "
            f"it were — give its execution a backtest.data.fx.QuoteConversion (see "
            f"strategies/python/extreme_leg/execution.py), or run it on a dollar-quoted symbol."
        )
    install(rate_provider)


def _contract_size(config, cost_profile) -> float:
    """Units in one lot of the run's instrument — what the venue lot ceiling counts in.

    The run's cost profile when it has one (measured off the broker's Specification), else the
    currency-pair standard when the config names a pair, else the account's default (gold's 100).
    """
    from backtest.data.fx import fx_contract_size
    from backtest.portfolio.account import DEFAULT_CONTRACT_SIZE

    size = getattr(cost_profile, "contract_size", None) if cost_profile is not None else None
    if size:
        return float(size)
    return fx_contract_size(str(getattr(config, "symbol", "") or "")) or DEFAULT_CONTRACT_SIZE


def _construct(strategy_cls, config, *, initial_capital, cost_profile, account, leg, max_lots):
    from backtest.portfolio.account import DEFAULT_CONTRACT_SIZE, DEFAULT_MAX_LOTS

    own_account = False
    # 🔴 THE CEILING COUNTS LOTS, AND A LOT IS NOT THE SAME SIZE ON EVERY INSTRUMENT. Every
    # account here defaulted to gold's 100 units, so a GBPJPY run's "100 lots" was 10,000 units —
    # 0.1 of a real lot — and every trade above that was silently resized (2026-09-27).
    contract = _contract_size(config, cost_profile)
    if max_lots is UNSTATED and account is None and contract != DEFAULT_CONTRACT_SIZE:
        # No ceiling stated, so the strategy would build its own account with gold's lot size.
        # Build it here instead, with the default ceiling counted in THIS instrument's lots.
        from backtest.portfolio.account import SoloAccount

        account = SoloAccount(
            balance=initial_capital, max_lots=DEFAULT_MAX_LOTS, contract_size=contract
        )
        own_account = True
    elif max_lots is not UNSTATED:
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

        account = SoloAccount(balance=initial_capital, max_lots=max_lots, contract_size=contract)
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
