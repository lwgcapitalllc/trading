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

And three KINDS of group, for the same reason one level up (`AccountGroup.kind`):

  * `account`  — a real login. `account` is its number.
  * `bench`    — bots whose config reads `account: null`: registered, configured, and
                 deliberately on no account. This is what removing a bot from an account
                 produces, and it is a normal resting state rather than a fault.
  * `unknown`  — bots whose config could not be READ, so which account they are on is unknown.

⚠ **`bench` and `unknown` were one group until 2026-08-09 and merging them is the defect, not
the tidy-up.** Both have no account number, so keying on `account` alone puts them together — and
then a bot nobody has assigned is displayed beside a bot whose config is broken, under one
heading, with the same controls. One of those is a state you chose and the other is a fault you
have to fix, and the page cannot say which if this module cannot. It is the repo's own *no* vs
*cannot ask* rule applied to a GROUP rather than to a value.

Pure: no HTTP, no SSH, no filesystem. It takes configs that have already been read and returns
plain dataclasses, so the grouping rules can be tested without a VPS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# One pure function, and it belongs to the ACCOUNT rather than to the grouping: a suffix is a
# fact the registry records. Imported rather than restated so the two cannot drift.
from services.bot_account_registry import rebase_symbol

__all__ = [
    "AccountBot",
    "AccountGroup",
    "AssignPlan",
    "group_by_account",
    "cap_change_plan",
    "assign_plan",
]


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
    cap_pct: Optional[float] = None  # what THIS bot states; None = uncapped
    unreadable: bool = False  # its config could not be parsed — cap UNKNOWN


@dataclass
class AccountGroup:
    account: Optional[int]
    server: str
    # "account" | "bench" | "unknown" — see the module docstring. `account` is set only on the
    # first; the other two are collections of bots that have no account for opposite reasons.
    kind: str = "account"
    bots: list[AccountBot] = field(default_factory=list)
    # The agreed cap, and it is only meaningful when `cap_agrees`. When the bots disagree there
    # is no account cap to report — deliberately NOT the max or the min, because picking one
    # would invent a ceiling nobody configured and hide the fault behind a plausible number.
    risk_cap_pct: Optional[float] = None
    cap_agrees: bool = True
    cap_unknown: bool = False  # at least one config is unreadable

    @property
    def stacked(self) -> bool:
        """More than one bot on one BALANCE. This is the whole definition — there is no separate
        'stack' object to be in or out of.

        ⚠ **The `kind` guard is load-bearing.** Two bots on the bench share no balance and cannot
        contend for anything, and two unreadable configs are not evidence of anything at all — so
        without it, benching a bot would light a **Stacked** chip on the Monitor row of a bot that
        is not trading. That chip's job is to warn that risk is doubled up, and a false one is the
        exact direction it must never fail in.
        """
        return self.kind == "account" and len(self.bots) > 1

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

    @property
    def magic_clash(self) -> list[str]:
        """Bots on this account sharing an order tag (`magic`). Empty is the healthy answer.

        **This exists so the page can stop showing the number.** A raw magic in a column told the
        reader nothing — Aaron, 2026-08-09: *"I don't know what the column magic even means"* —
        while the thing it encodes matters a great deal on a page about putting two bots on one
        balance: every read in `mt5_ops.py` filters by it, so two bots sharing one each read the
        OTHER's orders as their own, cancelling them, ratcheting their stops and booking their
        fills. So the fact is REPORTED when it is true and absent when it is not, instead of a
        number sitting on screen forever waiting to be interpreted.

        ⚠ It is `live_config._assert_magic_is_unique` said from the outside, and it can only ever
        agree with it — that guard is what actually refuses, at the bot's own startup, where it
        cannot be bypassed. This one gets ahead of it: the refusal happens on the box at 3am and
        this is visible the moment the clash is created.

        ⚠ Unreadable bots are excluded. Their magic is unknown, and `0` (the placeholder) would
        collide with every other unreadable bot and manufacture a clash out of a read failure.
        """
        if self.kind != "account":
            return []
        seen: dict[int, list[str]] = {}
        for b in self.bots:
            if b.unreadable or not b.magic:
                continue
            seen.setdefault(b.magic, []).append(b.key)
        return sorted(k for keys in seen.values() if len(keys) > 1 for k in keys)


def _num(v: Any) -> Optional[float]:
    """A number, or None. `None` and a missing key are the same thing here — both mean the file
    states no opinion — but a string or a bool is a malformed value and must not be coerced into
    a plausible float."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def group_by_account(
    configs: dict[str, Optional[dict]], displays: Optional[dict[str, str]] = None
) -> list[AccountGroup]:
    """Group registered bots by the account their config names.

    `configs` maps bot key → the parsed instance config, or **`None` when it could not be read**.
    That `None` is load-bearing: an unreadable bot still belongs to an account (we do not know
    which, so it is grouped under `None`) and still makes that account's cap UNKNOWN. Dropping it
    would report a smaller, tidier, wrong account.
    """
    displays = displays or {}
    # Keyed by KIND as well as number, because "no account" happens for two unrelated reasons and
    # `None == None` would file them together. See the module docstring.
    groups: dict[tuple[str, Optional[int]], AccountGroup] = {}

    for key in sorted(configs):
        raw = configs[key]
        if raw is None:
            bot = AccountBot(
                key=key,
                display=displays.get(key, key),
                symbol="",
                magic=0,
                strategy_package="",
                unreadable=True,
            )
            account: Optional[int] = None
            kind = "unknown"
            server = ""
        else:
            params = raw.get("strategy_params") or {}
            account = raw.get("account")
            kind = "account" if account is not None else "bench"
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

        g = groups.get((kind, account))
        if g is None:
            g = groups[(kind, account)] = AccountGroup(account=account, server=server, kind=kind)
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

    # Accounts first in number order, then the bench, then the unreadable bucket — each of the
    # last two is a different kind of thing from an account, and putting either in the middle of
    # the list reads as though it were one.
    order = {"account": 0, "bench": 1, "unknown": 2}
    return sorted(groups.values(), key=lambda g: (order[g.kind], g.account or 0))


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
            f"the unreadable config first."
        )
    return [b.key for b in group.bots if b.cap_pct != new_cap]


@dataclass
class AssignPlan:
    """What moving one bot writes.

    `fields` are literal top-level config keys and values, so a caller can `data.update(...)` and
    be done. `param_fields` go INSIDE `strategy_params` — the symbol and the cost profile live
    there as well as at the top level, and a flat dict cannot express that.

    `adopt_terminal_from` is deliberately NOT in `fields` — it is a bot KEY to read `mt5_path`
    off, not a value to write, and a sentinel mixed into a dict of real config fields is one
    careless `update()` away from being written to disk as a setting. It is now only used when
    the target account is NOT in the registry.

    `notes` is what could not be carried. It is a list rather than a bool because the caller has
    to be able to SAY so: a move that silently leaves a symbol or a cost profile describing the
    account the bot has left is exactly the 2026-08-12 defect, and it produces a bot that starts
    cleanly, connects cleanly and sees no bars.
    """

    fields: dict[str, Any] = field(default_factory=dict)
    param_fields: dict[str, Any] = field(default_factory=dict)
    adopt_terminal_from: str = ""
    notes: list[str] = field(default_factory=list)


def assign_plan(
    bot_key: str,
    account: Optional[int],
    *,
    target: Optional[AccountGroup] = None,
    registered: Any = None,
    current_symbol: str = "",
) -> AssignPlan:
    """The fields to write on `bot_key`'s config to put it on `account` (or on the bench).

    **Moving a bot is SIX fields, not one, and getting that wrong produces a bot that cannot
    start — or, worse, one that starts and trades nothing.** An account number on its own is not
    enough to trade an account:

      * `account` — the login itself. `None` benches the bot.
      * `server`  — an account number IS a login on a server; the pair is the identity, and the
        two halves disagreeing is a connection failure at startup with a confusing message.
      * `mt5_path` — the terminal has to be LOGGED INTO the account the bot claims to trade.
      * `symbol` — 🔴 **the one that was missing until 2026-08-12 and cost a manual afternoon.**
        PU Prime quotes gold as `XAUUSD.s` on its Standard book and `XAUUSD.p` on Prime and ECN,
        so an account move that writes the login and leaves the symbol produces a bot pointed at
        a symbol its terminal does not quote. Nothing errors: it connects, warms up, and receives
        no bars — which reads exactly like a quiet market.
      * `strategy_params.account_profile` — which measured cost model prices this account. Inert
        live (it only bills fills in tick mode, which the bridge refuses) and it must still be
        right, or the file claims one broker's costs while trading another's.
      * `account_risk_cap_pct` — the cap is an account-level fact stored per instance, and
        `live_config._assert_account_cap_agrees` **refuses to start every bot on the account**
        when they disagree. So a bot that arrived keeping its own cap would not merely be
        misconfigured, it would take the bots that were already there off the box at their next
        restart. Adopting the account's value is the only write that leaves the account coherent.

    ⚠ **Everything except the cap comes from the REGISTRY, and the cap comes from the BOTS.**
    That split is the whole design and it is not arbitrary: the registry states what the account
    IS, and it deliberately holds no cap, because the bots are what actually read one — a stored
    cap here would be a second answer that can disagree with them. Conversely the server, the
    terminal, the suffix and the profile are facts about the broker that no bot is authoritative
    about, and reading them off a PEER only works when a peer exists. Before the registry it had
    to, which is why the first bot on a new account could not be moved from the page at all.

    ⚠ **The symbol is REBASED, never copied from a peer.** The instrument is the bot's and the
    suffix is the account's — two bots on one account can legitimately trade gold and a currency
    pair, and copying whichever symbol happened to be there would rewrite one onto the other's
    market.

    ⚠ **A fact the registry does not carry is NOT guessed — it is reported in `notes`.** An
    account with no recorded suffix leaves the symbol alone and says so.

    ⚠ **Benching writes ONLY `account: None`.** The server, the terminal, the symbol and the cap
    are left exactly as they were, because the bench is a resting state and those are the settings
    that make re-assignment cheap — and because a cap of `None` on a benched bot is not a claim
    about any account (the guard exempts the bench for precisely that reason).

    ⚠ **An unreadable bot in the target group is refused**, for `cap_change_plan`'s reason
    sharpened: we would be adopting a cap agreed by only the bots we could read, which is the
    disagreement the guard exists to catch, created deliberately by the tool meant to prevent it.
    """
    if account is None:
        return AssignPlan(fields={"account": None})

    if target is not None and (target.kind != "account" or target.account != account):
        raise ValueError("the target group is not this account; pass None to bench a bot")

    if registered is None and target is None:
        raise ValueError(
            f"account {account} is neither registered nor traded by any bot, so nothing here "
            f"knows its server, its terminal or its symbol suffix. Register it first."
        )

    if registered is not None and not registered.assignable:
        raise ValueError(registered.unassignable_reason)

    notes: list[str] = []
    fields: dict[str, Any] = {"account": account}
    param_fields: dict[str, Any] = {}
    adopt_from = ""

    if target is not None:
        unreadable = [b.key for b in target.bots if b.unreadable]
        if unreadable:
            raise ValueError(
                f"cannot add {bot_key} to account {account} while {', '.join(unreadable)} "
                f"cannot be read: the new bot has to adopt the account's risk cap, and the cap "
                f"those bots state is unknown. Fix the unreadable config first."
            )
        if not target.cap_agrees:
            raise ValueError(
                f"cannot add {bot_key} to account {account} while the bots already on it state "
                f"different risk caps: there is no account cap for it to adopt, and every bot "
                f"here will refuse to start until they agree. Set the cap on this account first."
            )
        fields["account_risk_cap_pct"] = target.risk_cap_pct
        peers = [b for b in target.bots if b.key != bot_key]
        adopt_from = peers[0].key if peers else ""
    else:
        # First bot on this account. UNCAPPED is the honest state — nobody has chosen a ceiling
        # here — and the bot's existing value describes the account it is leaving, so carrying it
        # would state a ceiling for this account that nobody set.
        fields["account_risk_cap_pct"] = None
        notes.append(
            f"account {account} has no other bot on it, so it starts UNCAPPED — set the "
            f"account risk cap before a second bot joins."
        )

    if registered is not None:
        fields["server"] = registered.server
        fields["mt5_path"] = registered.mt5_path
        if registered.account_profile:
            param_fields["account_profile"] = registered.account_profile
        else:
            notes.append(
                f"account {account} records no cost profile, so the bot keeps the one "
                f"it had — it describes the account it came from."
            )

        moved = rebase_symbol(current_symbol, registered.symbol_suffix)
        if moved:
            if moved != current_symbol:
                fields["symbol"] = moved
                param_fields["symbol"] = moved
        elif current_symbol:
            notes.append(
                f"account {account} records no symbol suffix, so {bot_key} keeps "
                f"{current_symbol!r}. If this account quotes that instrument under another name, "
                f"the bot will connect and receive no bars."
            )
    else:
        if target is not None and target.server:
            fields["server"] = target.server
        adopt_from = adopt_from or (target.bots[0].key if target and target.bots else "")
        notes.append(
            f"account {account} is not in the account registry, so its symbol suffix and cost "
            f"profile could not be carried — the bot keeps the ones it had. Register the account "
            f"to make a move complete."
        )

    return AssignPlan(
        fields=fields, param_fields=param_fields, adopt_terminal_from=adopt_from, notes=notes
    )
