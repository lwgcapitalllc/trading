"""Which bots share a trading ACCOUNT, and what ceiling that account is under.

A "stack" on the live side is not something you configure — it is something you READ. Two bots
that name the same `account` in their instance configs are trading one balance whether anybody
intended it or not, so this module derives the grouping from the configs rather than storing a
second list of who-is-with-whom. **A stored grouping is a second answer that can disagree with
what the bots actually do**, and this repo has paid for that shape more than once (a label on a
screen claiming something no code checked). The broker is the source of truth about exposure;
the instance config is the source of truth about which broker account a bot points at.

The one thing that genuinely IS configuration is the ceiling — `account_risk_cap_pct` — and it
has an awkward home: it is an ACCOUNT-level fact stored per INSTANCE, because an instance config
is the only file a bot reads. So the same number lives in N places and can disagree in N ways.
`live_config._assert_account_cap_agrees` refuses to start a bot into that state; this module is
the half that lets the page SHOW it and fix it in one action, rather than leaving a human to
edit N files and get it right.

Three states for the cap, and they must not collapse into two:

  * a number   — this account is capped at that % of the live balance
  * `None`     — UNCAPPED, deliberately, which is the honest state for a one-bot account and is
                 what every measured result in this repo was taken on
  * unreadable — the config could not be parsed, so the cap is UNKNOWN

The third is why `unreadable` is its own field rather than a bot that quietly vanishes from its
account: a bot missing from a group reads as an account with fewer bots on it, which is the most
reassuring wrong answer available on a page about how much risk is on.

Pure: no HTTP, no SSH, no filesystem. It takes configs that have already been read and returns
plain dataclasses, so the grouping rules can be tested without a VPS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["AccountBot", "AccountGroup", "group_by_account", "cap_change_plan"]


@dataclass
class AccountBot:
    """One bot's place in an account, as far as the account cares."""
    key: str
    display: str
    symbol: str
    magic: int
    strategy_package: str
    # Per-TRADE risk, the layer BELOW the cap. Carried so the page can put the two numbers side
    # by side: a cap at or under a bot's own risk % does not let the bots share, it makes them
    # take turns, and that is invisible from the cap alone.
    risk_pct: Optional[float] = None
    cap_pct: Optional[float] = None          # what THIS bot states; None = uncapped
    unreadable: bool = False                 # its config could not be parsed — cap UNKNOWN


@dataclass
class AccountGroup:
    account: Optional[int]
    server: str
    bots: list[AccountBot] = field(default_factory=list)
    # The agreed cap, and it is only meaningful when `cap_agrees`. When the bots disagree there
    # is no account cap to report — deliberately NOT the max or the min, because picking one
    # would invent a ceiling nobody configured and hide the fault behind a plausible number.
    risk_cap_pct: Optional[float] = None
    cap_agrees: bool = True
    cap_unknown: bool = False                # at least one config is unreadable

    @property
    def stacked(self) -> bool:
        """More than one bot on one balance. This is the whole definition — there is no separate
        'stack' object to be in or out of."""
        return len(self.bots) > 1

    @property
    def cap_takes_turns(self) -> bool:
        """True when the cap is at or below the largest per-trade risk on the account.

        Not a fault and not a warning — a fact the two numbers imply and neither states. At a 10%
        cap against two bots each risking 10%, the account never holds both at once: whichever
        fills first holds the entire budget until its stop moves. A cap that lets both hold has
        to exceed the sum. Reported so the page can show it rather than leaving it to be
        discovered by a bot that mysteriously never trades.
        """
        if self.risk_cap_pct is None or not self.cap_agrees or not self.stacked:
            return False
        risks = [b.risk_pct for b in self.bots if b.risk_pct is not None]
        return bool(risks) and self.risk_cap_pct <= max(risks)


def _num(v: Any) -> Optional[float]:
    """A number, or None. `None` and a missing key are the same thing here — both mean the file
    states no opinion — but a string or a bool is a malformed value and must not be coerced into
    a plausible float."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def group_by_account(configs: dict[str, Optional[dict]],
                     displays: Optional[dict[str, str]] = None) -> list[AccountGroup]:
    """Group registered bots by the account their config names.

    `configs` maps bot key → the parsed instance config, or **`None` when it could not be read**.
    That `None` is load-bearing: an unreadable bot still belongs to an account (we do not know
    which, so it is grouped under `None`) and still makes that account's cap UNKNOWN. Dropping it
    would report a smaller, tidier, wrong account.
    """
    displays = displays or {}
    groups: dict[Optional[int], AccountGroup] = {}

    for key in sorted(configs):
        raw = configs[key]
        if raw is None:
            bot = AccountBot(key=key, display=displays.get(key, key), symbol="", magic=0,
                             strategy_package="", unreadable=True)
            account: Optional[int] = None
            server = ""
        else:
            params = raw.get("strategy_params") or {}
            account = raw.get("account")
            server = raw.get("server") or ""
            bot = AccountBot(
                key=key,
                display=raw.get("display_name") or displays.get(key, key),
                symbol=raw.get("symbol") or "",
                magic=int(raw.get("magic") or 0),
                strategy_package=raw.get("strategy_package") or "",
                risk_pct=_num(params.get("exec_risk_pct")),
                cap_pct=_num(raw.get("account_risk_cap_pct")),
            )

        g = groups.get(account)
        if g is None:
            g = groups[account] = AccountGroup(account=account, server=server)
        # The first readable config names the server. They cannot legitimately differ — an
        # account number IS a login on one server — so a later one is not merged over it.
        if not g.server and server:
            g.server = server
        g.bots.append(bot)

    for g in groups.values():
        readable = [b for b in g.bots if not b.unreadable]
        g.cap_unknown = len(readable) != len(g.bots)
        caps = {b.cap_pct for b in readable}
        g.cap_agrees = len(caps) <= 1
        g.risk_cap_pct = next(iter(caps)) if g.cap_agrees and caps else None

    # Accounts first, in number order; the unreadable bucket last, because it is a fault report
    # rather than an account and putting it in the middle of the list reads like one.
    return sorted(groups.values(),
                  key=lambda g: (g.account is None, g.account or 0))


def cap_change_plan(group: AccountGroup, new_cap: Optional[float]) -> list[str]:
    """Which bots in this account need writing to reach `new_cap`.

    Every bot on the account is a target, not just the ones that differ — but the ones already at
    the value are excluded so a no-op change does not produce a commit, a push and a VPS pull for
    nothing. An UNREADABLE bot is refused rather than skipped: writing the cap to three of four
    configs leaves exactly the disagreement this whole mechanism exists to prevent, and it would
    report success.
    """
    unreadable = [b.key for b in group.bots if b.unreadable]
    if unreadable:
        raise ValueError(
            f"cannot set an account cap while {', '.join(unreadable)} cannot be read: the cap has "
            f"to land on EVERY bot on the account or the account is left with two ceilings. Fix "
            f"the unreadable config first.")
    return [b.key for b in group.bots if b.cap_pct != new_cap]
