"""Plan moving a PROVEN strategy set off its demo account and onto a live one.

**The last stage of the pipeline, and the only one where a mistake costs money.** Steps before
this move numbers: a backtest, a grade, a settings copy onto demo bots. This moves the bots
themselves — the same set, together, onto a live broker account.

🔴 **ALL OR NOTHING, for the reason the stack settings copy is.** A strategy set is a
measurement of several strategies competing for ONE balance and ONE risk budget. Two of three
legs on the live account is a set nobody has ever run, and it reads as a finished promotion
because every bot it did move is correct.

🔴 **THERE IS NO MINIMUM RECORD, AND THAT IS A DECISION** (Aaron, 2026-09-06: *"There's no
minimum to go from demo to live. That's discretionary."*). So this REPORTS what each bot did on
demo and refuses on none of it. ⚠ **A bot with no ledger reads *no record reached this machine*,
never *zero trades*** — `bot_earnings` already refuses to collapse those two and this may not
undo it one layer up. The reader decides; this makes sure they cannot decide without seeing it.

**What it refuses on is the ACCOUNT, not the evidence:**

  - the destination has to be a REGISTERED account whose registry entry says `live` — going
    "live" onto a demo account is a no-op wearing the word, and the registry is the one place
    that states what an account is;
  - every bot has to be on ONE demo account today, which is the set that was proven together;
  - nothing may be RUNNING — a bot reads its config at startup, so a moved config on a running
    bot means the page shows a live account while the process trades the demo one;
  - the shares still have to fit under the budget the set arrives with.

🔴 **THE RISK BUDGET IS CARRIED, NOT RE-DERIVED, and this is the trap that made the module.**
`bot_accounts.assign_plan` writes `account_risk_cap_pct = None` for the FIRST bot on an account,
which is right for one bot joining an empty account and catastrophic for a set: moved one at a
time, every one of them looks like the first, so a proven set lands on a live account UNCAPPED.
The budget the set was measured under is written explicitly here, on every bot.

⚠ **PURE.** No HTTP, no SSH, no file write, no clock. `routers/bots.py` reads the edges and
writes exactly what a plan holds.

⚠ **A plan is BLOCKED or it is complete.** `blocked` is a sentence, and a caller holding one
writes nothing at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from services.bot_account_registry import RegisteredAccount
from services.bot_accounts import AccountBot, AccountGroup, AssignPlan, risk_pct_of, share_overflow
from services.stack_settings_import import BotTarget

__all__ = [
    "BotTarget",
    "BotMove",
    "GoLivePlan",
    "confirmation_phrase",
    "plan_go_live",
]


def confirmation_phrase(account: Optional[int]) -> str:
    """The exact words a caller has to send back before anything is written.

    🔴 **It NAMES THE ACCOUNT, and that is the whole design.** A fixed word like "CONFIRM" is a
    reflex — it is typed the same way whichever preview is on screen, so it proves the button was
    pressed and nothing else. The account number can only be typed by somebody reading THIS
    preview, so pasting yesterday's confirmation at a different destination fails.

    ⚠ Compared exactly, case included. A confirmation that accepts near-misses is a confirmation
    that can be produced without reading it.
    """
    return f"GO LIVE {account}"


@dataclass
class BotMove:
    """One bot's move, as the fields to write and what could not be carried.

    `fields` are top-level config keys; `param_fields` go INSIDE `strategy_params`. The split is
    `bot_accounts.AssignPlan`'s and is kept rather than flattened — the symbol and the cost
    profile live in both places and a flat dict cannot say so.

    `record` is what this bot did on the demo account. It is REPORTED and never enforced.
    """

    bot_key: str
    display: str
    fields: dict[str, Any] = field(default_factory=dict)
    param_fields: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    record: dict[str, Any] = field(default_factory=dict)


@dataclass
class GoLivePlan:
    blocked: Optional[str] = None
    from_account: Optional[int] = None
    to_account: Optional[int] = None
    moves: list[BotMove] = field(default_factory=list)
    # The budget every moved bot arrives stating. `None` means the demo account had no agreed
    # ceiling and none is written — see `_carried_cap`.
    cap_pct: Optional[float] = None
    confirm: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def is_noop(self) -> bool:
        return not self.moves


def _blocked(reason: str) -> GoLivePlan:
    return GoLivePlan(blocked=reason)


def plan_go_live(
    *,
    bot_keys: list[str],
    bots: list[BotTarget],
    destination: Optional[RegisteredAccount],
    destination_group: Optional[AccountGroup],
    records: dict[str, dict],
    assign: Any,
) -> GoLivePlan:
    """The whole decision, as data.

    `bot_keys` is the set being promoted. `bots` is EVERY registered bot — not just those, for
    `stack_settings_import`'s reason: a bot the promotion never mentions still shares an account,
    so its share and its ceiling decide whether the result fits.

    `assign` is `bot_accounts.assign_plan`, injected so the per-bot field work is the SAME
    function a single move from the Accounts page runs through. **Never re-implemented here** —
    six fields move a bot and each one has an incident behind it.

    Refusals are ordered the way a reader fixes them: can this be read at all, is there a
    destination, is it live, are the bots one demo set, is anything running.
    """
    if not bot_keys:
        return _blocked("no bots were named, so there is nothing to promote.")

    by_key = {b.key: b for b in bots}
    unknown = sorted(k for k in bot_keys if k not in by_key)
    if unknown:
        return _blocked(
            f"{_join(unknown)} is not a registered bot, so this cannot read what "
            f"{'it trades' if len(unknown) == 1 else 'they trade'} or where. Register it first."
        )

    # 🔴 Over EVERY registered bot, before anything else — the ordering `stack_settings_import`
    # learned the hard way. An unreadable config states no account, so a stranger sharing the
    # destination would simply not be seen, and the set would be promoted onto an account whose
    # occupants, shares and ceiling are all unknown.
    unreadable = sorted(b.key for b in bots if b.config is None)
    if unreadable:
        return _blocked(
            f"{_join(unreadable)} could not be read, so this cannot tell what "
            f"{'it states' if len(unreadable) == 1 else 'they state'} today — nor whether "
            f"{'it shares' if len(unreadable) == 1 else 'they share'} either account. Fix the "
            f"config first: an unreadable bot is not a bot with no settings."
        )

    # ── the destination has to BE a live account, and the registry is what says so ────────
    if destination is None:
        return _blocked(
            "that account is not registered, so nothing here knows its server, its terminal, "
            "its symbol suffix or whether it is a live account at all. Add it under Accounts "
            "first."
        )
    if destination.kind != "live":
        return _blocked(
            f"account {destination.account} is registered as a {destination.kind or 'unknown'} "
            f"account, and this control only ever moves a set onto a LIVE one. Moving between "
            f"demo accounts is an assignment, not a promotion — use the Accounts page."
        )
    if not destination.assignable:
        return _blocked(destination.unassignable_reason)

    # ── one demo account, and every bot on it ────────────────────────────────────────────
    moving = [by_key[k] for k in sorted(bot_keys)]

    benched = [b.key for b in moving if b.account is None]
    if benched:
        return _blocked(
            f"{_join(sorted(benched))} is not on an account, so this set has no demo record to "
            f"promote and was never run together. Assign it first."
        )

    accounts = {b.account for b in moving}
    if len(accounts) > 1:
        listed = ", ".join(f"{b.key} on {b.account}" for b in moving)
        return _blocked(
            f"these bots are on different accounts ({listed}). A set is promoted because it was "
            f"proven on ONE balance under one risk budget, and bots on two accounts have never "
            f"been that set."
        )
    from_account = accounts.pop()

    if from_account == destination.account:
        return _blocked(
            f"these bots are already on account {destination.account}, so there is nothing to move."
        )

    not_demo = sorted(
        f"{b.key} ({b.account_type or 'unknown'})" for b in moving if b.account_type != "demo"
    )
    if not_demo:
        return _blocked(
            f"{_join(not_demo)} does not trade a demo account, so this is not a demo-to-live "
            f"promotion. Nothing is moved: a set half of which is already live was never run "
            f"together on demo."
        )

    running = sorted(b.key for b in moving if b.running)
    if running:
        return _blocked(
            f"{_join(running)} is running, so its account cannot be changed — it read its config "
            f"at startup and would go on trading the demo account while this page showed the live "
            f"one. Stop every bot in the set, promote, then start them."
        )

    # 🔴 A bot LEFT BEHIND on the demo account is not a warning, it is a different set. The whole
    # claim being promoted is that these strategies were measured competing for one balance, and
    # a leg that stays behind means the thing that ran on demo is not the thing going live.
    on_source = sorted(b.key for b in bots if b.config is not None and b.account == from_account)
    left = [k for k in on_source if k not in set(bot_keys)]
    if left:
        return _blocked(
            f"{_join(left)} also trades demo account {from_account} and is not in this "
            f"promotion, so what goes live is not what was proven — the set on demo competed for "
            f"one balance with {'it' if len(left) == 1 else 'them'} in it. Promote the whole "
            f"account or bench what is not part of the set."
        )

    plan = GoLivePlan(
        from_account=from_account,
        to_account=destination.account,
        confirm=confirmation_phrase(destination.account),
    )

    # ── the budget the set arrives under ─────────────────────────────────────────────────
    cap, cap_note = _carried_cap(
        source_bots=[b for b in bots if b.config is not None and b.account == from_account],
        destination_group=destination_group,
    )
    if cap_note and cap is None and destination_group is not None:
        # A destination whose own bots disagree has no ceiling to adopt and the arrivals cannot
        # invent one — `live_config._assert_account_cap_agrees` would then refuse every bot on
        # that account at its next start, including the ones already trading it.
        return _blocked(cap_note)
    plan.cap_pct = cap

    # ── the per-bot field work, through the SAME planner a single move runs ──────────────
    for bot in moving:
        config = bot.config or {}
        try:
            moved: AssignPlan = assign(
                bot.key,
                destination.account,
                target=destination_group,
                registered=destination,
                current_symbol=str(config.get("symbol") or ""),
                declared_params=bot.declared,
            )
        except ValueError as exc:
            return _blocked(f"{bot.key}: {exc}")

        fields = dict(moved.fields)
        notes = list(moved.notes)

        # 🔴 THE OVERRIDE THE MODULE EXISTS FOR. `assign_plan` states `None` for the first bot on
        # an account, and every member of a set moved together looks like the first — so left
        # alone, a proven set lands on a live account with no ceiling at all. The budget written
        # is the one the set was measured under, on every bot, because the ceiling is stored per
        # instance and one left behind leaves the account with two.
        if cap is not None:
            fields["account_risk_cap_pct"] = cap
            notes = [n for n in notes if "starts UNCAPPED" not in n]

        plan.moves.append(
            BotMove(
                bot_key=bot.key,
                display=bot.display,
                fields=fields,
                param_fields=dict(moved.param_fields),
                notes=notes,
                record=dict(records.get(bot.key) or {}),
            )
        )

    # ── the shares must still fit, AFTER everything this would write ─────────────────────
    overflow = share_overflow(_hypothetical(plan, moving, destination_group), cap)
    if overflow:
        return _blocked(
            f"account {destination.account} would be over-subscribed once this set arrives — "
            f"{overflow} Nothing is moved: the set's own numbers were produced with these shares "
            f"fitting."
        )

    plan.warnings.extend(_warnings(plan, moving, destination_group, cap_note))
    return plan


def _carried_cap(
    *, source_bots: list[BotTarget], destination_group: Optional[AccountGroup]
) -> tuple[Optional[float], str]:
    """The ceiling the set arrives stating, and anything worth saying about it.

    ⚠ **The DESTINATION's ceiling wins when it has one.** A live account already carrying bots
    has a budget those bots agreed on, and arrivals adopt it — the alternative is the set
    rewriting a ceiling on an account it has never traded.

    ⚠ **Otherwise the SOURCE's, which is the budget the set was measured under.** An empty live
    account has no opinion, so carrying the demo account's is the only write that leaves the set
    configured as it was proven.

    ⚠ **`None` means neither side states one**, and then nothing is written. An absent ceiling is
    not a ceiling of nothing.
    """
    if destination_group is not None and destination_group.bots:
        if destination_group.cap_unknown:
            return None, (
                f"account {destination_group.account} already carries a bot whose config could "
                f"not be read, so its risk budget is unknown and this set cannot adopt it."
            )
        if not destination_group.cap_agrees:
            return None, (
                f"the bots already on account {destination_group.account} state different risk "
                f"budgets, so there is no ceiling for this set to adopt — and every bot there "
                f"will refuse to start until they agree. Set the account's budget first."
            )
        if destination_group.risk_cap_pct is not None:
            return float(destination_group.risk_cap_pct), (
                f"account {destination_group.account} already has a risk budget of "
                f"{float(destination_group.risk_cap_pct):g}% and the set adopts it rather than "
                f"bringing its own."
            )

    caps = {_cap_of(b) for b in source_bots}
    current = next(iter(caps)) if len(caps) == 1 else None
    if current is None:
        return None, (
            "the demo account states no single risk budget, so none is written and the live "
            "account starts UNCAPPED. Set it before these bots are started."
        )
    return current, ""


def _cap_of(bot: BotTarget) -> Optional[float]:
    raw = (bot.config or {}).get("account_risk_cap_pct")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def _hypothetical(
    plan: GoLivePlan, moving: list[BotTarget], destination_group: Optional[AccountGroup]
) -> list[AccountBot]:
    """The live account as it would be AFTER the move — never as it is today.

    🔴 Checking the account as it stands passes every move that over-subscribes it and refuses
    every move that would fix one, because the arrivals are precisely what is not there yet.

    ⚠ **An arriving bot's share is its OWN `exec_risk_pct`, unchanged.** This control moves an
    account, not a setting: a promotion that quietly re-sized the strategies would be promoting
    something other than what was proven. If the shares do not fit, that is a refusal to read,
    not a number to adjust.

    ⚠ **A bot already on the destination keeps the share it states, and an unreadable or unstated
    one stays `None` — `share_overflow` REFUSES on it.** A bot whose risk cannot be read is not a
    bot risking nothing.
    """
    out: list[AccountBot] = list(destination_group.bots) if destination_group is not None else []
    for bot in moving:
        raw = bot.config or {}
        out.append(
            AccountBot(
                key=bot.key,
                display=bot.display,
                symbol=str(raw.get("symbol") or ""),
                magic=int(raw.get("magic") or 0),
                strategy_package=bot.strategy_package,
                risk_pct=risk_pct_of(raw),
                cap_pct=plan.cap_pct,
            )
        )
    return sorted(out, key=lambda b: b.key)


def _warnings(
    plan: GoLivePlan,
    moving: list[BotTarget],
    destination_group: Optional[AccountGroup],
    cap_note: str,
) -> list[str]:
    """Everything LOUD that does not refuse — the demo record above all.

    🔴 **The record is a WARNING and never a refusal, on purpose.** There is no minimum here, so
    the only thing this can do is put the evidence where it cannot be missed. Saying nothing when
    a bot has never traded would let a set go live on the strength of a sibling's record.
    """
    out: list[str] = []

    for bot in moving:
        rec = next((m.record for m in plan.moves if m.bot_key == bot.key), {})
        if not rec:
            out.append(
                f"{bot.key}: its demo record could not be read, so this says nothing about what "
                f"it did — that is not the same as it having done nothing."
            )
        elif not rec.get("traded"):
            out.append(
                f"{bot.key}: {rec.get('reason') or 'no decision record has reached this machine'} "
                f"— so there is NO demo evidence for this bot at all."
            )
        else:
            r = rec.get("realised_r")
            out.append(
                f"{bot.key}: {rec.get('closed_trades')} closed trades on demo, "
                f"{'unknown' if r is None else f'{float(r):+.2f}R'}, "
                f"{rec.get('wins')} won / {rec.get('losses')} lost, recorded "
                f"{rec.get('records_from')} → {rec.get('records_to')}."
            )

    if destination_group is not None and destination_group.bots:
        existing = sorted(b.key for b in destination_group.bots)
        out.append(
            f"account {plan.to_account} is already traded by {_join(existing)}, so the live "
            f"account will hold a strategy set nothing has measured together. Their shares are "
            f"counted against the budget; their settings are not touched."
        )

    if cap_note:
        out.append(cap_note)

    for move in plan.moves:
        for note in move.notes:
            out.append(f"{move.bot_key}: {note}")

    out.append(
        "nothing is started. Every bot in this set is stopped and stays stopped — a promotion "
        "writes configs, and a bot only trades the live account once somebody starts it."
    )
    return out


def _join(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " and " + items[-1]
