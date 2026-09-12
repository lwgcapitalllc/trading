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

import math
from dataclasses import dataclass, field, replace
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
    "risk_pct_of",
    "share_overflow",
    "assign_plan",
    "RiskPlan",
    "risk_plan",
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
    def share_total_pct(self) -> Optional[float]:
        """The per-trade shares handed out on this account, added up.

        🔴 **`None` when ANY bot's share is unreadable or unstated — never a partial sum.** The
        page that shows this is the page somebody uses to split a cap between two bots, and a
        total quietly missing one bot's share is a number that says the account fits when it does
        not. Same rule as `share_overflow`, which REFUSES rather than counting an unknown as zero:
        an unreadable share is not a share of zero (rule 1).

        ⚠ **It is served rather than added up on the page**, because the page had its own reduce
        with `?? 0` in it — the exact leniency this refuses — so the browser could print a total
        that fitted while the save was refused. One rule, one place, whichever side asks.
        """
        if any(b.unreadable or b.risk_pct is None for b in self.bots):
            return None
        return sum(float(b.risk_pct) for b in self.bots)

    @property
    def share_overflow_reason(self) -> Optional[str]:
        """Why the shares here do NOT fit under the ceiling — the sentence a save is refused with.

        `None` when they fit, when there is no cap, or when the caps disagree (there is no agreed
        ceiling to check against, and inventing one is what `risk_cap_pct` already refuses to do).

        ⚠ **This is the SAME call the write path makes**, so what the page shows before you save
        and what the save says are one function. It is served so an over-subscribed account is
        VISIBLE, rather than being discovered by typing a number and being refused.
        """
        return share_overflow(self.bots, self.risk_cap_pct)

    @property
    def room_pct(self) -> Optional[float]:
        """The share still free under the ceiling — the cap minus the shares handed out.

        `None` when there is no agreed cap or the shares cannot be totalled: an uncapped account has
        no room to run out of, and an unreadable share makes the room unknown, never the cap itself.
        ⚠ **Negative when the shares already exceed the cap**, and deliberately not floored at zero
        here — *over by 3%* is a real answer, and a floor would make an over-subscribed account read
        exactly like a full one.

        ⚠ **SERVED for the same reason as `share_total_pct`**: the page's Add bot offers a share
        that fits, and subtracting two numbers there is the same rule written twice in two
        languages.
        """
        if self.kind != "account" or not self.cap_agrees or self.risk_cap_pct is None:
            return None
        total = self.share_total_pct
        if total is None:
            return None
        return round(float(self.risk_cap_pct) - total, 6)

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
            account = raw.get("account")
            kind = "account" if account is not None else "bench"
            server = raw.get("server") or ""
            bot = AccountBot(
                key=key,
                display=raw.get("display_name") or displays.get(key, key),
                symbol=raw.get("symbol") or "",
                magic=int(raw.get("magic") or 0),
                strategy_package=raw.get("strategy_package") or "",
                risk_pct=risk_pct_of(raw),
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


# The tolerance on the shares-vs-ceiling comparison. Two bots at 5.0 against a cap of 10.0 must
# FIT — that is the intended configuration, not a near miss — and binary floating point is not
# guaranteed to make the sum land exactly on the ceiling once a third share or a decimal like 3.3
# is involved. Same reasoning and same size as `_GRANT_EPS` in `backtest/portfolio/account.py`.
def risk_pct_of(raw: dict) -> Optional[float]:
    """What ONE bot risks per trade, read out of its instance config.

    The single definition, so a caller assembling a hypothetical account (a bot about to be
    MOVED onto one) reads this number exactly the way `group_by_account` reads every other bot's.
    Two ways of finding it is two answers, and the one that drifts is the hypothetical.

    `None` when the config states nothing readable — never 0.0, which would read as a bot that
    risks nothing and let an over-subscribed account save cleanly.
    """
    return _num((raw.get("strategy_params") or {}).get("exec_risk_pct"))


_SHARE_EPS = 1e-9


def share_overflow(bots: list, cap_pct: Optional[float]) -> Optional[str]:
    """Do the per-trade shares handed out on this account fit under its ceiling?

    Returns `None` when they fit — or when there is nothing to check — and the reason to REFUSE
    otherwise. Aaron, 2026-09-03: *"the risk per trade cannot add up to more than that cap"*.

    🔴 **WHY A SUM, when the cap is enforced live per order anyway.** The live cap already stops
    an account exceeding its ceiling; it does that by making whoever asks LAST take less, or
    nothing. So an over-subscribed account is not unsafe — it is a set of bots that quietly stop
    being the bots that were backtested, because each one only gets its full size when it happens
    to ask first. **This check is about the CONFIGURATION being coherent, not about safety**, and
    that distinction belongs in the message: refusing here prevents a silent demotion, not a loss.

    ⚠ **An unreadable or unstated share REFUSES rather than counting as zero** (rule 1). A bot
    whose risk cannot be read is not a bot risking nothing, and treating it as 0.0 would let an
    account that is genuinely over its ceiling save cleanly — which is the one outcome this
    function exists to prevent.

    ⚠ **No cap means nothing to check.** Uncapped is a supported, deliberate state; it is not a
    cap of zero, and it is not an error.
    """
    if cap_pct is None:
        return None

    unknown = [b.key for b in bots if b.unreadable or b.risk_pct is None]
    if unknown:
        return (
            f"cannot check the risk shares on this account: {', '.join(sorted(unknown))} "
            f"{'does' if len(unknown) == 1 else 'do'} not state a readable risk per trade. "
            f"An unreadable share is not a share of zero — fix the config first."
        )

    total = sum(float(b.risk_pct) for b in bots)
    if total <= float(cap_pct) + _SHARE_EPS:
        return None

    shares = ", ".join(
        f"{b.display} {float(b.risk_pct):g}%" for b in sorted(bots, key=lambda x: x.key)
    )
    return (
        f"the risk shares on this account add up to {total:g}%, which is more than its "
        f"{float(cap_pct):g}% ceiling ({shares}). Over the ceiling the bots do not share the "
        f"budget, they take turns: whoever asks first gets its full size and the others are cut "
        f"down or refused, so each one stops being the bot that was backtested. Lower a share, "
        f"or raise the cap."
    )


# The two one-click fixes a plan offers are rounded to this many decimals — a share DOWN and a cap
# UP, so a suggestion can never land a hair over the ceiling it was computed to fit under.
_FIT_DECIMALS = 2
# The smallest share the runtime editor accepts (`bot_params.RUNTIME_BOUNDS`). A scaled share below
# it would be refused at the save, so a suggestion that needs one is not offered at all.
_MIN_SHARE = 0.1


@dataclass
class RiskPlan:
    """An account's risk budget AFTER a proposed write, and whether that write may be made.

    🔴 **ONE planner for every write that can move the budget** (2026-09-11): a bot's share (the
    runtime editor), the cap, several shares and the cap together (the account panel), and a bot
    about to JOIN (the Add bot preview). Each write carried its own copy of the check until then,
    and every copy refused an IMPROVEMENT — lowering a share on an account already over its cap was
    refused because the RESULT was still over. That made such an account unfixable one step at a
    time, which is the exact outcome `share_overflow`'s note on this rule promised never to cause.

    **The rule: a write is refused only when the result does not fit AND the write adds risk** — a
    share rises, a bot joins, or the cap comes down (or appears where there was none). A write that
    frees room is always allowed, even when the account is still over afterwards, because it moves
    the account the right way and refusing it leaves the reader with no small step that works.
    """

    account: Optional[int]
    risk_cap_pct: Optional[float]  # the cap AFTER the write
    cap_changed: bool
    bots: list[AccountBot]  # every bot counted, each with its share AFTER the write
    before: dict[str, Optional[float]]  # each bot's share BEFORE; a joining bot's is None
    joining: list[str]  # keys counted in but not on the account yet
    share_total_pct: Optional[float]  # AFTER; None when any share is unreadable or unstated
    reason: Optional[str]  # why the result does not fit — the served sentence; None = it fits
    adds_risk: bool
    fit_cap: Optional[float]  # the smallest cap these shares fit under, rounded UP
    fit_shares: Optional[dict[str, float]]  # these shares scaled to fit the cap, rounded DOWN

    @property
    def fits(self) -> bool:
        return self.reason is None

    @property
    def refusal(self) -> Optional[str]:
        """The sentence a SAVE is refused with — set only when the write makes things worse."""
        return self.reason if self.reason and self.adds_risk else None

    @property
    def changed(self) -> bool:
        """Would a save write anything? Shares that move, or the cap. A joining bot is never
        written by a budget save — it joins through its own move."""
        return self.cap_changed or any(
            self.before.get(b.key) != b.risk_pct for b in self.bots if b.key not in self.joining
        )

    @property
    def room_pct(self) -> Optional[float]:
        """The cap minus the shares, after the write. Same meaning as `AccountGroup.room_pct`."""
        if self.risk_cap_pct is None or self.share_total_pct is None:
            return None
        return round(float(self.risk_cap_pct) - self.share_total_pct, 6)


def risk_plan(
    group: AccountGroup,
    shares: Optional[dict[str, float]] = None,
    *,
    cap_set: bool = False,
    cap: Optional[float] = None,
    joining: Optional[list[AccountBot]] = None,
) -> RiskPlan:
    """Plan a change to one account's risk budget. Raises `ValueError` with a sentence when the
    change cannot be planned at all; otherwise the plan says whether it fits and may be saved.

    `cap_set` separates *leave the cap alone* from *set it to `cap`* — `None` is a real cap value
    (uncapped), so the absent value and the null one have to be told apart by the caller, the same
    `model_fields_set` rule the move endpoint follows.

    ⚠ **An unreadable bot on the account REFUSES the whole plan**, because its share is unknown and
    an unknown share is not a share of zero (rule 1) — the same call `share_overflow` makes.
    ⚠ **Caps that DISAGREE refuse a plan that does not set one**: there is no ceiling to check a
    share against, and none of those bots will start until they agree. Setting a cap is the fix.
    """
    shares = {k: float(v) for k, v in (shares or {}).items()}
    joining = list(joining or [])
    if group.kind != "account":
        raise ValueError("only a real account has a risk budget")
    on_it = {b.key for b in group.bots}
    stray = sorted(set(shares) - on_it)
    if stray:
        raise ValueError(
            f"{', '.join(stray)} {'is' if len(stray) == 1 else 'are'} not on account "
            f"{group.account}, so this account's budget cannot set "
            f"{'its' if len(stray) == 1 else 'their'} risk."
        )
    already = sorted(b.key for b in joining if b.key in on_it)
    if already:
        raise ValueError(f"{', '.join(already)} is already on account {group.account}.")
    unreadable = sorted(b.key for b in group.bots if b.unreadable)
    if unreadable:
        raise ValueError(
            f"{', '.join(unreadable)} cannot be read, so this account's budget cannot be checked or "
            f"written — an unreadable share is not a share of zero. Fix the config first."
        )

    if cap_set:
        new_cap = None if cap is None else float(cap)
    elif group.cap_agrees:
        new_cap = group.risk_cap_pct
    else:
        raise ValueError(
            "the bots on this account state different caps, so there is no ceiling to check a "
            "share against — and none of them will start until they agree. Set one cap for the "
            "account first."
        )
    old_cap = group.risk_cap_pct if group.cap_agrees else None
    # A cap appearing where there was none — or any cap while the bots disagree — counts as coming
    # DOWN: both can refuse a trade that was allowed before.
    cap_lowered = (
        cap_set
        and new_cap is not None
        and (not group.cap_agrees or old_cap is None or new_cap < float(old_cap) - _SHARE_EPS)
    )
    cap_changed = cap_set and (not group.cap_agrees or new_cap != old_cap)

    before: dict[str, Optional[float]] = {b.key: b.risk_pct for b in group.bots}
    after_bots = [replace(b, risk_pct=shares[b.key]) if b.key in shares else b for b in group.bots]
    # An unstated share becoming a number counts as RAISED — nothing measured says it went down.
    share_raised = any(
        before[k] is None or v > float(before[k]) + _SHARE_EPS for k, v in shares.items()
    )
    for j in joining:
        before[j.key] = None
    everyone = after_bots + joining

    reason = share_overflow(everyone, new_cap)
    total = (
        None
        if any(b.unreadable or b.risk_pct is None for b in everyone)
        else sum(float(b.risk_pct) for b in everyone)
    )

    fit_cap: Optional[float] = None
    fit_shares: Optional[dict[str, float]] = None
    if reason and total is not None and new_cap is not None and total > 0:
        step = 10**_FIT_DECIMALS
        up = math.ceil(total * step - 1e-9) / step
        fit_cap = up if up <= 100 else None
        scale = float(new_cap) / total
        scaled = {
            b.key: math.floor(float(b.risk_pct) * scale * step + 1e-9) / step for b in everyone
        }
        fit_shares = scaled if all(v >= _MIN_SHARE for v in scaled.values()) else None

    return RiskPlan(
        account=group.account,
        risk_cap_pct=new_cap,
        cap_changed=bool(cap_changed),
        bots=everyone,
        before=before,
        joining=[j.key for j in joining],
        share_total_pct=total,
        reason=reason,
        adds_risk=bool(cap_lowered or share_raised or joining),
        fit_cap=fit_cap,
        fit_shares=fit_shares,
    )


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

    `info` is the harmless half, split out 2026-09-10: a setting left UNWRITTEN because the
    receiving strategy has no such setting. It cannot change how that strategy trades — a setting
    it does not declare is one it cannot read — so it is bookkeeping, never a hazard. It is kept
    apart so the demo → live screen can show only real warnings; the single-bot move still says it.
    """

    fields: dict[str, Any] = field(default_factory=dict)
    param_fields: dict[str, Any] = field(default_factory=dict)
    adopt_terminal_from: str = ""
    notes: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def _only_declared(
    param_fields: dict[str, Any], declared: Optional[set]
) -> tuple[dict[str, Any], list[str]]:
    """Drop any `strategy_params` write the receiving strategy does not declare.

    🔴 **`runner._build_strategy` REFUSES to start on any `strategy_params` key the strategy's
    config class does not have** — *"they would be ignored, so the bot would trade settings you
    did not choose"* — and that refusal is right. **MEASURED 2026-09-04**: assigning
    `extreme_leg_demo` wrote `account_profile` off the account registry, `ExtremeLegConfig` has no
    such field, and the bot connected to the broker and refused to start on every attempt.

    🔴 **THE SHAPE: a write that is correct for every existing receiver is not a correct write.**
    Both strategies that had ever been assigned declare that field, so this had a 100% pass rate
    right up to the first one that did not, and nothing in the code was going to reveal it before
    a third strategy existed.

    ⚠ **Filtering happens HERE, at the end, rather than at each write site** — so a param this
    function learns to carry tomorrow is covered without anyone remembering this rule. The
    per-site version is the one that goes stale.

    ⚠ **`declared is None` means COULD NOT ASK, and it writes anyway.** That is deliberate and it
    is the one place here that does not follow "refuse when you cannot ask": of the two wrong
    answers, writing gives a bot that refuses to start and says exactly why, while skipping gives
    a bot that starts and trades an account with another broker's costs recorded against it — the
    quiet one. **A note says the check could not be made, so it is never silent.**
    """
    if declared is None:
        if param_fields:
            return param_fields, [
                "the receiving strategy's settings could not be read, so "
                + ", ".join(sorted(param_fields))
                + " were written unchecked — if the strategy does not declare one of them the "
                "bot will refuse to start and name it."
            ]
        return param_fields, []

    kept = {k: v for k, v in param_fields.items() if k in declared}
    dropped = sorted(set(param_fields) - set(kept))
    if not dropped:
        return kept, []
    return kept, [
        f"{', '.join(dropped)} was not written: this strategy does not have that setting, and a "
        f"setting it cannot read would stop it starting. Anything that value describes about the "
        f"account is not recorded on this bot."
    ]


def _cap_words(cap: Optional[float]) -> str:
    return "none (uncapped)" if cap is None else f"{float(cap):g}%"


def assign_plan(
    bot_key: str,
    account: Optional[int],
    *,
    target: Optional[AccountGroup] = None,
    registered: Any = None,
    current_symbol: str = "",
    declared_params: Optional[set] = None,
    current_account: Optional[int] = None,
    current_adjustment: Any = None,
    first_cap_chosen: bool = False,
    first_cap: Optional[float] = None,
) -> AssignPlan:
    """The fields to write on `bot_key`'s config to put it on `account` (or on the bench).

    🔴 **A SEVENTH, and it put a live bot out of action on the first move to real money
    (2026-09-11).** `sizing_basis_adjustment` shrinks the balance a bot sizes from by an amount
    MEASURED on one account — SOS Fade carried -4518.23, the demo account's duplicate-fill
    windfall, onto a $451.97 live account, and refused to start there ("leaves nothing to trade
    on"). It is a claim about the account being LEFT, so a move to a different account clears a
    non-zero one to 0 and says so; a move back to the same account keeps it. ⚠ It is cleared only
    when it is set, so a move writes nothing for a bot that never had one. ⚠ Benching leaves it,
    like every other field — the bench is a resting state, and a move off it clears it then.

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

    ⚠ **`declared_params` is the receiving strategy's own field names**, and every
    `strategy_params` write is filtered through it — see `_only_declared`, which carries the
    2026-09-04 incident this argument exists because of. Pass `None` only when the strategy genuinely
    could not be read; it means *unchecked*, not *nothing to check*, and it is reported as such.
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
        if first_cap_chosen and first_cap != target.risk_cap_pct:
            # The page offers a cap only for an EMPTY account; one arriving here means the account
            # gained a bot since it was drawn. Adopting silently would override what was chosen,
            # and writing it would disagree with the bots already there — both are refused.
            raise ValueError(
                f"account {account} already has a bot on it, and its cap is "
                f"{_cap_words(target.risk_cap_pct)} — a bot joining adopts that. Change the cap "
                f"on the account, not while adding a bot."
            )
        fields["account_risk_cap_pct"] = target.risk_cap_pct
        peers = [b for b in target.bots if b.key != bot_key]
        adopt_from = peers[0].key if peers else ""
    elif first_cap_chosen:
        # First bot on this account, and the person adding it chose the ceiling — `None` included,
        # which is choosing to run uncapped rather than not having chosen.
        fields["account_risk_cap_pct"] = first_cap
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

    # The balance adjustment describes the account being LEFT — see the docstring. Anything set and
    # not a numeric zero is cleared, a malformed value included: it cannot describe the new account.
    if account != current_account and current_adjustment not in (None, 0, 0.0):
        fields["sizing_basis_adjustment"] = 0.0
        amount = (
            f"{float(current_adjustment):,.2f}"
            if isinstance(current_adjustment, (int, float))
            and not isinstance(current_adjustment, bool)
            else repr(current_adjustment)
        )
        notes.append(
            f"the balance it sizes from was adjusted by {amount}, an amount measured on account "
            f"{current_account}. That is cleared, because on account {account} it would shrink or "
            f"refuse every trade."
        )

    # LAST, so every param write above is covered — including any added later. See `_only_declared`.
    param_fields, unwritable = _only_declared(param_fields, declared_params)
    # ⚠ WHICH list depends on whether the strategy could be READ. Unread, the params were written
    # UNCHECKED and the bot may refuse to start — a hazard. Read, the only thing skipped is a
    # setting the strategy does not have, which cannot change how it trades — bookkeeping.
    info: list[str] = []
    if declared_params is None:
        notes.extend(unwritable)
    else:
        info.extend(unwritable)
    return AssignPlan(
        fields=fields,
        param_fields=param_fields,
        adopt_terminal_from=adopt_from,
        notes=notes,
        info=info,
    )
