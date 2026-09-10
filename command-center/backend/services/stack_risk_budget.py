"""Do a shared stack's legs fit under its risk cap?

Aaron, 2026-09-10: *"if I put ten percent cap, then the strategies that I choose cannot trade more
than the cap … they cannot add up to more than the risk cap."*

One function answers it for two callers — the stack FORM, which shows the total while the reader
types, and the LAUNCH, which refuses a stack that does not fit. They must be the same answer: the
Bots page once added the shares up in the browser with `?? 0`, printed a total that fitted, and
had the save refused (`command-center/backend/CLAUDE.md` → *The shares may not add up to more than
the ceiling*). So the page reads this, never its own sum.

🔴 **The DECISION is `bot_accounts.share_overflow`, the check the Bots page, the copy-to-demo button
and the stress tester's nudge skip already use.** A second comparison here would be a second rule
free to drift from the one that refuses a live account. Only the SENTENCE is this module's own,
because "each bot stops being the bot that was backtested" is the wrong thing to tell somebody
building the backtest.

🔴 **Why the sum is the right question for a BACKTEST too, when the simulator would just shrink the
later entry.** Over the cap the legs take turns rather than share, so the stack stops describing an
account the Bots page would let you run — the live side refuses those shares at the moment of
assignment. Refusing here keeps a shared stack a measurement of something deployable.

⚠ **A leg's share is what ONE entry risks** (`risk_pct_of`, the same reader the Bots page uses).
Each leg holds one position at a time; a re-entry risks less than the primary and only follows it
once it is closed, and an add is sized so its worst case is profit the stop already locked. So the
per-trade setting is the most a leg can put at risk at entry, which is what the cap budgets.

⚠ **An unreadable share REFUSES, never counts as zero** (rule 1) — a leg whose risk cannot be read
is not a leg risking nothing, and a partial total is a number that gets believed.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional

from services.bot_accounts import risk_pct_of, share_overflow


@dataclass(frozen=True)
class LegShare:
    strategy_id: str
    name: str
    # What one entry of this leg risks, % of the balance. `None` = the leg states no readable
    # risk per trade — never 0.0, which would let an over-subscribed stack pass.
    risk_pct: Optional[float]
    # Set on the loss-recovery leg only: the strategy whose losses it recovers.
    recovery_of: Optional[str] = None


@dataclass(frozen=True)
class RiskBudget:
    cap_pct: float
    legs: list
    # `None` when ANY leg's share is unreadable — never a partial sum.
    total_pct: Optional[float]
    fits: bool
    reason: Optional[str]


def leg_share(strategy_id: str, name: str, params: Optional[dict]) -> LegShare:
    """A leg's share, read off the settings the leg will RUN with."""
    return LegShare(strategy_id, name, risk_pct_of({"strategy_params": params or {}}))


def _fraction(v) -> Optional[float]:
    # A string or a bool is a malformed value, not a fraction — same rule `risk_pct_of` applies.
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v) if v > 0 else None


def recovery_share(
    parent: Optional[LegShare],
    recovery_params: Optional[dict],
    rule_defaults: Optional[dict],
    name: str,
) -> LegShare:
    """The loss-recovery leg's share: its parent's per-trade risk times the rule's size fraction.

    That is how the leg sizes itself (`loss_recovery.lab.leg_config` reads the parent's risk and the
    leg takes `rec_risk_frac` of it), so the two move together — raise the parent and a quarter-size
    recovery is still a quarter.

    ⚠ **The fraction comes from the request, else the rule's stored defaults** — the strategy row the
    lab reads every other leg's defaults from. The launch passes `recovery_params` as sent and the
    rule's own class fills the rest, so a class default edited without a rescan would disagree with
    the row; that is the Strategies page's *Needs scan* state, not a silent one.
    """
    frac = _fraction((recovery_params or {}).get("rec_risk_frac"))
    if frac is None and "rec_risk_frac" not in (recovery_params or {}):
        frac = _fraction((rule_defaults or {}).get("rec_risk_frac"))
    parent_risk = parent.risk_pct if parent is not None else None
    risk = parent_risk * frac if parent_risk is not None and frac is not None else None
    return LegShare(
        "loss_recovery",
        name,
        risk,
        recovery_of=parent.strategy_id if parent is not None else None,
    )


def budget(legs: list[LegShare], cap_pct: float) -> RiskBudget:
    """Does this stack fit, and if not, the sentence to show and to refuse with."""
    rows = [
        SimpleNamespace(key=leg.name, display=leg.name, risk_pct=leg.risk_pct, unreadable=False)
        for leg in legs
    ]
    unknown = [leg.name for leg in legs if leg.risk_pct is None]
    total = None if unknown else sum(float(leg.risk_pct) for leg in legs)
    cap = float(cap_pct)

    if share_overflow(rows, cap) is None:
        return RiskBudget(cap, legs, total, True, None)

    if unknown:
        verb = "does" if len(unknown) == 1 else "do"
        reason = (
            f"Cannot add up the risk: {', '.join(unknown)} {verb} not state a risk per trade. "
            f"An unreadable risk is not a risk of zero."
        )
    else:
        shares = " + ".join(f"{leg.name} {float(leg.risk_pct):g}%" for leg in legs)
        reason = (
            f"These legs risk {total:g}% per trade together ({shares}), more than the "
            f"{cap:g}% cap. Over the cap they take turns instead of sharing — whoever enters "
            f"first gets its full size and the rest are cut down — so this is not an account "
            f"the Bots page would let you run. Lower a leg's risk or raise the cap."
        )
    return RiskBudget(cap, legs, total, False, reason)
