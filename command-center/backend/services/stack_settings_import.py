"""Plan a settings copy from a graded STACK's stress test onto the bots that run its legs.

**One stack, N bots, ALL OR NOTHING.** A shared-account stack is a measurement of several
strategies competing for ONE balance and ONE risk budget. Writing three of its four legs
produces a set of bots that has never been measured together — and it reads as a completed
copy, because every bot it did reach is correct.

🔴 **THIS IS NOT THE SINGLE-BOT IMPORT RUN N TIMES, and the difference is the account.** The
per-leg work IS `bot_settings_import.plan_import`, called once per leg and never
re-implemented; what this module adds is the half a per-bot planner cannot see:

  - every leg must land on a DEMO bot, and they must all be on the **same broker account** —
    two bots on two accounts is not the stack that was replayed;
  - the account's **risk budget** is part of the result and gets written too, because the
    stack's own numbers were produced under it;
  - after everything is written the per-trade shares must still FIT under that budget, or the
    bots quietly stop being the bots that were measured (`bot_accounts.share_overflow`).

⚠ **PURE.** No HTTP, no SSH, no file write — every input is read by the caller and every output
is data. `routers/bots.py` does the edges, and the apply writes exactly what a plan holds.

⚠ **A plan is BLOCKED or it is complete.** There is no partial plan: `blocked` is a sentence, and
a caller holding one must write nothing at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from services import bot_settings_import
from services.bot_accounts import AccountBot, risk_pct_of, share_overflow

__all__ = [
    "BotTarget",
    "LegImport",
    "CapChange",
    "StackImportPlan",
    "plan_stack_import",
]


@dataclass(frozen=True)
class BotTarget:
    """One registered bot, as far as this plan cares. Assembled by the caller."""

    key: str
    display: str
    account_type: str  # "demo" | "live"
    running: bool
    # `None` when the config could not be read. That is NOT an empty config: a bot whose
    # settings cannot be read is a bot this plan must refuse to reason about, never one that
    # happens to state nothing.
    config: Optional[dict] = None
    # The settings its strategy DECLARES. `None` means could-not-ask and is handled as
    # *unchecked* by `_only_declared`, never as *nothing declared*.
    declared: Optional[set] = None

    @property
    def account(self) -> Optional[int]:
        raw = (self.config or {}).get("account")
        return raw if isinstance(raw, int) else None

    @property
    def strategy_package(self) -> str:
        return str((self.config or {}).get("strategy_package") or "")


@dataclass
class LegImport:
    """One leg of the stack, and the bot it would be written to."""

    strategy_id: str
    bot_key: str
    plan: bot_settings_import.ImportPlan


@dataclass
class CapChange:
    """The account's risk budget, and which bots have to be written to move it.

    ⚠ **EVERY bot on the account is written, not just the stack's legs.** The budget is stored
    per instance and the account's cap is whatever its bots agree on — so leaving one behind
    produces exactly the two-ceilings state `bot_accounts` refuses to report a cap for.
    """

    current: Optional[float]
    proposed: Optional[float]
    bots_to_write: list[str] = field(default_factory=list)

    @property
    def moves(self) -> bool:
        return bool(self.bots_to_write)


@dataclass
class StackImportPlan:
    blocked: Optional[str] = None
    account: Optional[int] = None
    legs: list[LegImport] = field(default_factory=list)
    cap: Optional[CapChange] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def change_count(self) -> int:
        return sum(len(leg.plan.changes) for leg in self.legs)

    @property
    def is_noop(self) -> bool:
        return self.change_count == 0 and not (self.cap and self.cap.moves)


def _blocked(reason: str) -> StackImportPlan:
    return StackImportPlan(blocked=reason)


def _match_bots(strategy_id: str, bots: list[BotTarget]) -> list[BotTarget]:
    """Every registered bot running this leg's strategy.

    🔴 **Matched on the bot's own `strategy_package`, which IS the lab's strategy id for a python
    package.** A key-name convention (`sos_fade` → `sos_fade_demo`) would be a rule living in a
    string, and it breaks the first time somebody registers a second bot on one strategy or names
    one differently.
    """
    return [b for b in bots if b.strategy_package and b.strategy_package == strategy_id]


def plan_stack_import(
    *,
    legs: list[dict],
    bots: list[BotTarget],
    stack_risk_cap_pct: Optional[float],
    grade: Optional[str],
    graded: bool,
) -> StackImportPlan:
    """The whole decision, as data.

    `legs` is one dict per stack leg: `strategy_id`, `params`, and the run's own `instrument` /
    `bar_type` / `bar_value` so each leg can warn about a mismatch the way a single import does.

    Every refusal below is ALL-OR-NOTHING and names the thing to fix. They are checked in the
    order a reader would fix them: is there a bot at all, is it a demo bot, is it on an account,
    is that one account, is anything running.
    """
    if not legs:
        return _blocked(
            "this stress test's stack has no legs recorded, so there is nothing to copy."
        )

    # 🔴 CHECKED FIRST, OVER EVERY REGISTERED BOT, and that ordering is the fix rather than the
    # check. An unreadable config states no `strategy_package`, so a leg's own bot simply fails
    # to MATCH and the refusal came back as *"no registered bot runs extreme_leg"* — sending the
    # reader to register a bot that already exists. It also cannot be narrowed to the legs: an
    # unreadable bot might be a stranger sharing the account, and then its risk share and its
    # ceiling are both unknown, which is exactly what `cap_change_plan` refuses to write over.
    unreadable = sorted(b.key for b in bots if b.config is None)
    if unreadable:
        return _blocked(
            f"{_join(unreadable)} could not be read, so this cannot tell what "
            f"{'it states' if len(unreadable) == 1 else 'they state'} today — nor whether "
            f"{'it shares' if len(unreadable) == 1 else 'they share'} the account this stack "
            f"would be written to. Fix the config first: an unreadable bot is not a bot with no "
            f"settings."
        )

    # ── one bot per leg ──────────────────────────────────────────────────────────────────
    pairs: list[tuple[dict, BotTarget]] = []
    missing: list[str] = []
    ambiguous: list[str] = []
    for leg in legs:
        sid = str(leg.get("strategy_id") or "")
        found = _match_bots(sid, bots)
        if not found:
            missing.append(sid)
        elif len(found) > 1:
            ambiguous.append(f"{sid} ({', '.join(sorted(b.key for b in found))})")
        else:
            pairs.append((leg, found[0]))

    if missing:
        return _blocked(
            f"no registered bot runs {_join(missing)}, so {'that leg' if len(missing) == 1 else 'those legs'} "
            f"has nowhere to be written. Every leg of the stack has to land somewhere or the bots "
            f"left over are a different strategy set from the one that was measured."
        )
    if ambiguous:
        return _blocked(
            f"more than one registered bot runs {_join(ambiguous)}, so this cannot say which one "
            f"the leg belongs to. Nothing is written rather than guessing."
        )

    # ── demo only ────────────────────────────────────────────────────────────────────────
    not_demo = [
        f"{b.key} ({b.account_type or 'unknown'})" for _, b in pairs if b.account_type != "demo"
    ]
    if not_demo:
        return _blocked(
            f"{_join(sorted(not_demo))} does not trade a demo account, and this control only ever "
            f"writes to demo bots. Going from demo to live is the next stage and a separate "
            f"decision."
        )

    # ── one account, and every leg on it ─────────────────────────────────────────────────
    benched = [b.key for _, b in pairs if b.account is None]
    if benched:
        return _blocked(
            f"{_join(sorted(benched))} is not on an account, so the legs of this stack do not "
            f"share a balance. This stack was replayed on ONE account with one risk budget — "
            f"assign every leg's bot to the same account first."
        )

    accounts = {b.account for _, b in pairs}
    if len(accounts) > 1:
        listed = ", ".join(
            f"{b.key} on {b.account}" for _, b in sorted(pairs, key=lambda p: p[1].key)
        )
        return _blocked(
            f"these bots are on different accounts ({listed}). The stack was replayed on ONE "
            f"balance with one risk budget, so writing it across two accounts would produce a "
            f"configuration nothing has measured."
        )
    account = accounts.pop()

    running = [b.key for _, b in pairs if b.running]
    if running:
        return _blocked(
            f"{_join(sorted(running))} is running, so its settings cannot be changed — it read "
            f"its config at startup and would go on trading the old settings while this page "
            f"showed the new ones. Stop every leg's bot, apply, then start them."
        )

    plan = StackImportPlan(account=account)

    # ── the per-leg work, through the SAME planner a single import uses ──────────────────
    for leg, bot in sorted(pairs, key=lambda p: p[1].key):
        config = bot.config or {}
        leg_plan = bot_settings_import.plan_import(
            run_params=leg.get("params") or {},
            bot_params=config.get("strategy_params") or {},
            declared=bot.declared,
            account_type=bot.account_type,
            grade=grade,
            graded=graded,
            run_instrument=str(leg.get("instrument") or ""),
            bot_symbol=str(config.get("symbol") or ""),
            run_bar_type=str(leg.get("bar_type") or ""),
            run_bar_value=leg.get("bar_value"),
            bot_timeframe=str(config.get("timeframe") or ""),
        )
        # 🔴 A leg-level refusal blocks the WHOLE plan. A stack written minus one leg is a
        # strategy set nobody measured, and it reads as finished.
        if leg_plan.blocked:
            return _blocked(f"{bot.key}: {leg_plan.blocked}")
        plan.legs.append(
            LegImport(strategy_id=str(leg.get("strategy_id") or ""), bot_key=bot.key, plan=leg_plan)
        )

    # ── the account's risk budget ────────────────────────────────────────────────────────
    on_account = [b for b in bots if b.config is not None and b.account == account]
    plan.cap = _cap_change(on_account, stack_risk_cap_pct)

    # ── the shares must still fit, AFTER everything this would write ─────────────────────
    proposed_cap = plan.cap.proposed if plan.cap else None
    overflow = share_overflow(_hypothetical(on_account, plan), proposed_cap)
    if overflow:
        return _blocked(
            f"after this copy the account would be over-subscribed — {overflow} Nothing is "
            f"written: the stack's own numbers were produced with these shares fitting."
        )

    plan.warnings.extend(_warnings(plan, on_account, stack_risk_cap_pct))
    return plan


def _cap_change(on_account: list[BotTarget], proposed: Optional[float]) -> CapChange:
    """The account's budget move, and every bot that has to be written to make it.

    ⚠ **`None` proposed means the stack recorded no budget, and then NOTHING is written.** A
    screen has no account cap and neither does a stack stored before the column existed;
    clearing a live account's ceiling because a stored figure was absent is the opposite of
    what an absent value means.
    """
    caps = {_cap_of(b) for b in on_account}
    current = next(iter(caps)) if len(caps) == 1 else None
    if proposed is None:
        return CapChange(current=current, proposed=None, bots_to_write=[])
    return CapChange(
        current=current,
        proposed=proposed,
        bots_to_write=sorted(b.key for b in on_account if _cap_of(b) != proposed),
    )


def _cap_of(bot: BotTarget) -> Optional[float]:
    raw = (bot.config or {}).get("account_risk_cap_pct")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def _hypothetical(on_account: list[BotTarget], plan: StackImportPlan) -> list[AccountBot]:
    """The account as it would be AFTER this copy — never as it is today.

    🔴 Checking the current state would pass every write that creates the problem, which is the
    rule `bot_accounts` already records for a bot being moved onto an account. A leg's share is
    the one this plan would WRITE; a bot on the account that is not a leg keeps the one it has.

    ⚠ **An unreadable or unstated share stays `None` and `share_overflow` REFUSES on it.** A bot
    whose risk cannot be read is not a bot risking nothing.
    """
    proposed_share: dict[str, Any] = {}
    for leg in plan.legs:
        for change in leg.plan.changes:
            if change.name == "exec_risk_pct":
                proposed_share[leg.bot_key] = change.proposed

    out: list[AccountBot] = []
    for bot in sorted(on_account, key=lambda b: b.key):
        raw = bot.config or {}
        share = risk_pct_of(raw)
        if bot.key in proposed_share:
            val = proposed_share[bot.key]
            share = (
                float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None
            )
        out.append(
            AccountBot(
                key=bot.key,
                display=bot.display,
                symbol=str(raw.get("symbol") or ""),
                magic=0,
                strategy_package=bot.strategy_package,
                risk_pct=share,
                cap_pct=_cap_of(bot),
            )
        )
    return out


def _warnings(
    plan: StackImportPlan, on_account: list[BotTarget], stack_cap: Optional[float]
) -> list[str]:
    """Everything LOUD that does not refuse.

    ⚠ Each leg's own warnings are kept and NAMED with the bot they belong to. Rolling them into
    one list would leave the reader unable to tell which of four bots is on the wrong timeframe.
    """
    out: list[str] = []

    leg_keys = {leg.bot_key for leg in plan.legs}
    strangers = sorted(b.key for b in on_account if b.key not in leg_keys)
    if strangers:
        out.append(
            f"{_join(strangers)} also trades this account and is not part of this stack, so the "
            f"account will hold a strategy set the stack never modelled. Its risk share is "
            f"counted against the budget; its settings are not touched."
        )

    if stack_cap is None:
        out.append(
            "this stack recorded no account risk budget, so the account's ceiling is left "
            "exactly as it is. The stack's own numbers were produced under some budget — check "
            "which before reading these settings as reproduced."
        )
    elif plan.cap and not plan.cap.moves:
        pass  # already at the stack's budget; nothing worth saying
    elif plan.cap:
        out.append(
            f"the account's risk budget moves from "
            f"{'unset' if plan.cap.current is None else f'{plan.cap.current:g}%'} to "
            f"{stack_cap:g}% and is written to {_join(plan.cap.bots_to_write)} — every bot on "
            f"the account, because the ceiling is stored per bot and one left behind leaves the "
            f"account with two."
        )

    for leg in plan.legs:
        for w in leg.plan.warnings:
            out.append(f"{leg.bot_key}: {w}")
    return out


def _join(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return items[0] if items else ""
    return ", ".join(items[:-1]) + " and " + items[-1]
