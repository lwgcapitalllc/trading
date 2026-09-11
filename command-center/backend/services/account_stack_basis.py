"""What an account's bots actually run, as a stack the lab can backtest.

**The one job: turn "backtest this account's bots" into the stack builder's starting point** —
each bot's strategy, the chart it trades, the settings it trades with, the instrument, the
account's risk ceiling and its cost profile — so the backtest measures the ACCOUNT and not the
strategies' defaults. Every function here is pure; `routers/bots.py` does the reading.

🔴 **THE BOT'S OWN SETTINGS, NEVER THE STRATEGY'S DEFAULTS.** MEASURED 2026-09-10 on PU Prime demo
700152905: the lab's SOS Fade default risks 10% a trade while the bot risks 5%, beside the extreme
leg's 5% under a 10% ceiling. The Accounts tab's old "Backtest this account" pre-filled the
strategies and the cap and nothing else, so it asked for 10 + 5 = 15% under 10% — which the stack
builder refuses. A builder that merely ran would have measured a different account.

⚠ **Each leg is sent COMPLETE**: the strategy's stored defaults with every setting the bot states
laid over them. A stack request's per-leg settings REPLACE that leg's defaults rather than merging
with them (`routers/stacks.py` reads the override OR the defaults, never both), so sending only the
bot's pins would drop every setting it happens not to state.

⚠ **A setting the strategy no longer has is left out and COUNTED**, through the same filter an
account move uses (`bot_accounts._only_declared`), rather than handed to a run that cannot read it.

⚠ **What it cannot carry is the CODE.** The lab replays this machine's strategy; a bot runs the
snapshot it was last deployed with. The page says so rather than implying the two are one thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# 🔴 Imported, never re-implemented — each is the one statement of its rule. `_only_declared` is
# the filter behind the 2026-09-04 bot that refused to start; `_bot_tf_minutes` is how a bot's
# chart is read everywhere else; `group_by_account` decides which bots share a balance.
from services.bot_accounts import _only_declared, group_by_account, risk_pct_of
from services.bot_settings_import import _bot_tf_minutes


@dataclass(frozen=True)
class BasisStrategy:
    """The lab's row for a strategy package, as far as this plan cares."""

    id: str
    name: str
    runner: str
    default_params: dict
    requires_source: bool = False


@dataclass
class BasisLeg:
    """One bot, as the leg of a stack."""

    bot: str
    display: str
    strategy_id: str
    strategy_name: str
    bar_value: Optional[int]  # None = the bot's chart could not be read
    risk_pct: Optional[float]
    from_bot: int  # settings the bot states
    from_defaults: int  # settings it does not state, taken from the strategy's stored defaults


@dataclass
class AccountStackBasis:
    account: int
    # A REASON, not a bool: a caller that only knows "no" cannot tell the reader which rule said no.
    blocked: Optional[str] = None
    strategy_ids: list[str] = field(default_factory=list)
    instrument: Optional[str] = None
    broker_profile: Optional[str] = None
    risk_cap_pct: Optional[float] = None
    params_by_strategy: dict[str, dict] = field(default_factory=dict)
    bar_values_by_strategy: dict[str, int] = field(default_factory=dict)
    legs: list[BasisLeg] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _names(bots: list) -> str:
    names = [b.display for b in bots]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def plan_account_stack(
    *,
    account: int,
    configs: dict[str, Optional[dict]],
    displays: dict[str, str],
    strategies: dict[str, Optional[BasisStrategy]],
    declared: dict[str, Optional[set]],
    account_profile: Optional[str],
    registry_readable: bool = True,
) -> AccountStackBasis:
    """The whole decision, as data.

    `configs` is EVERY registered bot's instance config, `None` where it could not be read — every
    bot rather than this account's, because an unreadable one might be on it. `strategies` and
    `declared` are keyed by strategy package; `None` in `declared` means the strategy's settings
    could not be read, which `_only_declared` handles as *unchecked*, never as *declares nothing*.
    `registry_readable=False` keeps *the account list could not be read* apart from *nothing is
    recorded for this account* — the same two answers, told apart.
    """
    basis = AccountStackBasis(account=account)
    groups = group_by_account(configs, displays)

    # 🔴 An unreadable config has no account we can see, so it might be on THIS one. A backtest
    # without it is an account quietly one bot short, which reads exactly like a complete one.
    unreadable = [b for g in groups if g.kind == "unknown" for b in g.bots]
    if unreadable:
        return _refuse(
            account,
            (
                f"{_names(unreadable)}'s settings could not be read, so whether "
                f"{'it trades' if len(unreadable) == 1 else 'they trade'} this account is unknown. Fix "
                f"that first — a backtest without {'it' if len(unreadable) == 1 else 'them'} could be "
                f"missing a bot."
            ),
        )

    group = next((g for g in groups if g.kind == "account" and g.account == account), None)
    if group is None or not group.bots:
        return _refuse(
            account, f"No bot trades account {account}, so there is nothing to backtest."
        )
    if len(group.bots) < 2:
        return _refuse(
            account,
            (
                f"Only {group.bots[0].display} trades account {account}. A stack needs two or more "
                f"bots — backtest this one on its own from its strategy page."
            ),
        )
    if not group.cap_agrees:
        return _refuse(
            account,
            (
                f"The bots on account {account} state different risk ceilings, so the account has no "
                f"single budget to backtest under. Set one ceiling for the account first."
            ),
        )

    seen: dict[str, Any] = {}
    instruments: dict[str, list] = {}
    for bot in group.bots:
        raw = configs[bot.key] or {}
        package = str(raw.get("strategy_package") or "")
        strategy = strategies.get(package) if package else None
        if strategy is None:
            return _refuse(
                account,
                (
                    f"{bot.display} runs a strategy the lab does not have. Scan strategies on the "
                    f"Strategies page, then try again."
                ),
            )
        if strategy.runner != "python":
            return _refuse(
                account,
                (
                    f"{bot.display}'s strategy does not run in the lab's Python runner, and a stack is "
                    f"Python only."
                ),
            )
        if strategy.requires_source:
            return _refuse(
                account,
                (
                    f"{bot.display} runs a rule that only works on another strategy's losses. A stack "
                    f"adds that as a tick under its parent, not as a bot of its own."
                ),
            )
        if package in seen:
            return _refuse(
                account,
                (
                    f"{seen[package].display} and {bot.display} run the same strategy. A stack has one "
                    f"leg per strategy, so it cannot hold both."
                ),
            )
        seen[package] = bot
        instruments.setdefault(str(raw.get("symbol") or ""), []).append(bot)

        # Prose keys (`_`-prefixed) are an explanation a human left in the file, not settings.
        pins = {
            k: v
            for k, v in (raw.get("strategy_params") or {}).items()
            if not str(k).startswith("_")
        }
        merged = {**(strategy.default_params or {}), **pins}
        kept, _ = _only_declared(merged, declared.get(package))
        dropped = [k for k in pins if k not in kept]
        if dropped:
            basis.notes.append(
                f"{bot.display} states {len(dropped)} setting"
                f"{'' if len(dropped) == 1 else 's'} its strategy no longer has, so the backtest "
                f"leaves {'it' if len(dropped) == 1 else 'them'} out."
            )
        from_bot = sum(1 for k in kept if k in pins)
        from_defaults = len(kept) - from_bot
        if from_defaults:
            basis.notes.append(
                f"{from_defaults} of {bot.display}'s settings are not stated by the bot, so they "
                f"come from its strategy's current defaults."
            )

        bar = _bot_tf_minutes(str(raw.get("timeframe") or ""))
        if bar is None:
            basis.notes.append(
                f"{bot.display}'s chart timeframe could not be read, so its leg uses the one its "
                f"strategy was measured on."
            )
        else:
            basis.bar_values_by_strategy[strategy.id] = bar

        basis.strategy_ids.append(strategy.id)
        basis.params_by_strategy[strategy.id] = kept
        basis.legs.append(
            BasisLeg(
                bot=bot.key,
                display=bot.display,
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                bar_value=bar,
                risk_pct=risk_pct_of(raw),
                from_bot=from_bot,
                from_defaults=from_defaults,
            )
        )

    # A stack replays ONE instrument, so bots on two cannot be one backtest.
    if "" in instruments:
        return _refuse(account, f"{_names(instruments[''])} names no instrument to trade.")
    if len(instruments) > 1:
        return _refuse(
            account,
            f"The bots on account {account} trade different instruments "
            f"({', '.join(sorted(instruments))}), and a stack replays one.",
        )
    basis.instrument = next(iter(instruments))

    basis.risk_cap_pct = group.risk_cap_pct
    if basis.risk_cap_pct is None:
        basis.notes.append(
            f"Account {account} has no risk ceiling, and a shared backtest needs one — the form "
            f"starts at the lab's own and you can change it."
        )

    basis.broker_profile = account_profile or None
    if not registry_readable:
        basis.notes.append(
            "The account list could not be read, so the form starts on the broker the lab's "
            "terminal is connected to."
        )
    elif basis.broker_profile is None:
        basis.notes.append(
            f"No cost profile is recorded for account {account}, so the form starts on the broker "
            f"the lab's terminal is connected to."
        )
    return basis


def _refuse(account: int, reason: Optional[str]) -> AccountStackBasis:
    """A refused plan carries NO half-built stack. Legs already assembled when a later bot is
    refused are thrown away: a caller reading `strategy_ids` off a blocked plan would pre-fill a
    form the refusal said could not be built."""
    return AccountStackBasis(account=account, blocked=reason)
