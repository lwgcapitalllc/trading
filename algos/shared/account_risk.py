"""What the WHOLE ACCOUNT has at risk right now — the one number a per-trade risk % cannot see.

`order_sizing.py` answers "how big is THIS order". This answers "how much is already on", across
every bot on the account and every trade a human placed by hand. They are different questions and
the second one has never been asked in this repo: `exec_risk_pct` is per-trade with nothing above
it, so two bots at 10% put 20% at risk from a state neither of them can see
(`docs/LIVE_TRADING_PIPELINE.md` → G10).

**The broker is the source of truth, and that is the whole design.** Every alternative needs the
bots to trust each other — a shared state file, a lock, a message bus — and each of those has the
same fatal property: a bot that crashed, was killed, or was never told about leaves a stale
reservation, or none at all, and the cap then bounds a fiction. The broker knows what is actually
open. It also knows the STOP on every one of them, because this suite puts the stop at the broker
by design (`algos/live/bridge.py` → D4), so risk-to-the-current-stop is readable rather than
inferred — the same basis `backtest/portfolio/account.py` reserves on.

Three rules, each of which is the difference between a cap and a decoration:

  1. **A position with no stop cannot be measured, and that REFUSES.** Its risk is not zero, it is
     unbounded — a hand trade left running is exactly that. Scoring it as zero is this repo's
     "no" vs "cannot ask" defect landing on the single number the cap exists to bound.
  2. **A RESTING order counts against the budget**, even though it has not filled. Live there is no
     scheduler serialising the bots: two limits can fill on the same tick with neither bot having
     seen the other, and a cap a race can walk through is not a cap. ⚠ **This is a deliberate
     DIVERGENCE from `backtest/portfolio/`, which reserves at the FILL** — see `counts_pendings`.
  3. **Refuse, never shrink.** `order_sizing` already refuses rather than resizing, for the reason
     recorded there: a resized order is not the trade the strategy's emulator is holding, and the
     two then drift apart silently. ⚠ **The backtest allocator SHRINKS**, which is coherent there
     because the account hands the granted size back and the emulator opens at it. Nothing hands a
     size back across a process boundary, so live refuses. That difference is real and is named
     here rather than papered over.

Pure: no MT5 import, no I/O, no logging. Same discipline as `order_sizing.py`, and for the same
reason — this is arithmetic that decides whether real money goes on, so it has to be testable
without a terminal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

try:  # pragma: no cover - import shim
    from order_sizing import SymbolSpec, value_per_lot
except ImportError:  # pragma: no cover
    from .order_sizing import SymbolSpec, value_per_lot  # type: ignore

__all__ = [
    "Exposure",
    "AccountRisk",
    "RiskUnmeasurable",
    "measure_exposure",
    "check_account_cap",
]


@dataclass(frozen=True)
class Exposure:
    """One thing the account is carrying — an open position or a resting order.

    Deliberately ONE type for both. The cap does not care which it is, and two types would mean
    two code paths that can disagree about the arithmetic; `resting` is carried so the refusal
    message can say what is holding the room.
    """

    ticket: int
    symbol: str
    magic: int
    direction: int  # +1 long, -1 short — see the note in `measure_exposure`
    volume: float  # LOTS, as the broker reports it
    entry: float  # open price, or the resting limit's price
    stop: float  # the broker-side SL; 0.0 / None means there isn't one
    resting: bool = False
    label: str = ""  # which bot, when it can be named — for the refusal message only


@dataclass(frozen=True)
class AccountRisk:
    """What the account has on, in account currency."""

    total_ccy: float
    positions: int
    resting: int
    per_magic: dict = field(default_factory=dict)

    def pct_of(self, balance: Optional[float]) -> Optional[float]:
        """As a fraction of `balance`. `None` when the balance could not be read — never 0.0,
        which would read as "nothing at risk" on the one number that must not be guessed."""
        if balance is None or balance <= 0:
            return None
        return self.total_ccy / balance


class RiskUnmeasurable(Exception):
    """The account is carrying something whose risk cannot be computed.

    Raised rather than returned, because every caller has exactly one correct response — refuse
    the order — and an exception cannot be ignored by a caller that forgot to check a field.
    """


def measure_exposure(items: Sequence[Exposure], spec: SymbolSpec) -> AccountRisk:
    """Total account-currency risk across everything passed in.

    `spec` converts a price distance into money and is the reason this is instrument-agnostic:
    `value_per_lot` already carries contract size and the account's currency, so gold, a JPY pair
    and a cash index are one arithmetic. Same function `order_sizing` sizes with, so the number
    this returns and the number an order is sized against cannot drift.

    ⚠ **Everything must be the SAME symbol.** Two symbols need two specs, and silently applying
    one instrument's tick value to another is a factor-of-150 error on a JPY pair. A caller with a
    mixed account filters first and is refused here if it did not.
    """
    if not spec.is_priceable():
        raise RiskUnmeasurable(
            f"the broker has not said what a tick of {spec.symbol} is worth "
            f"(tick_size={spec.tick_size}, tick_value={spec.tick_value}), so no open risk on this "
            f"account can be converted into money."
        )

    total = 0.0
    positions = 0
    resting = 0
    per_magic: dict = {}
    for it in items:
        if it.symbol != spec.symbol:
            raise RiskUnmeasurable(
                f"ticket {it.ticket} is on {it.symbol} and the spec describes {spec.symbol}; one "
                f"instrument's tick value must never be applied to another's position."
            )
        if not it.stop:
            # 0.0 and None are the same thing here and both mean NO STOP AT THE BROKER. That is
            # not small risk, it is unbounded risk — the position runs until something else stops
            # it. A hand trade is the usual source. Refusing is the only honest answer: the cap
            # cannot bound a number nobody can compute.
            raise RiskUnmeasurable(
                f"{'order' if it.resting else 'position'} {it.ticket} on {it.symbol} "
                f"(magic {it.magic}) has NO broker-side stop, so its risk is unbounded and the "
                f"account's open risk cannot be totalled. Attach a stop to it, or close it."
            )
        # DIRECTION-AWARE, and `abs()` here is a real bug rather than a simplification — it was
        # written that way first and a test caught it. A long whose stop has ratcheted ABOVE its
        # entry is locked in profit and risks NOTHING; `abs()` scores that as risk and grows it
        # as the runner runs, so a winning trade would hold the budget shut against the other bot
        # for as long as it kept winning. That is the exact opposite of what the
        # reserve-to-the-current-stop model exists to do.
        # Identical formula to `backtest/portfolio/account.py::Position.reserved`, deliberately:
        # the two sides of the same rule must not be two expressions of it.
        risk_per_unit = max(0.0, it.direction * (float(it.entry) - float(it.stop)))
        risk = value_per_lot(risk_per_unit, spec) * float(it.volume)
        total += risk
        per_magic[it.magic] = round(per_magic.get(it.magic, 0.0) + risk, 2)
        if it.resting:
            resting += 1
        else:
            positions += 1
    return AccountRisk(
        total_ccy=round(total, 2), positions=positions, resting=resting, per_magic=per_magic
    )


@dataclass(frozen=True)
class CapVerdict:
    """Allowed, or refused with a reason a human can act on at 3am."""

    allowed: bool
    code: str = ""
    detail: str = ""
    open_risk_ccy: float = 0.0
    cap_ccy: float = 0.0
    room_ccy: float = 0.0


def check_account_cap(
    *,
    new_order_risk_ccy: float,
    open_risk: AccountRisk,
    balance: Optional[float],
    cap_pct: Optional[float],
) -> CapVerdict:
    """Does this order fit inside the account-level cap?

    `cap_pct` is a PERCENT of the live balance (10.0 = 10%), matching `exec_risk_pct`'s unit so
    the two can be read side by side without converting. `None` = no cap configured, which is a
    supported and honest state — a single bot needs none — and the caller is expected to SAY SO
    at startup rather than let its absence pass unremarked (the `deadman_url` precedent).

    `balance` of `None` REFUSES. A cap is a fraction of something, and with the terminal unable
    to say what, the choice is between refusing one setup and letting an unbounded one through.
    """
    if cap_pct is None:
        return CapVerdict(allowed=True, code="no_cap")
    if cap_pct <= 0:
        return CapVerdict(
            allowed=False,
            code="cap_not_positive",
            detail=f"the account risk cap is {cap_pct}%, which refuses every order. Remove the "
            f"setting to run uncapped, or set a real percentage.",
        )
    if balance is None or balance <= 0:
        return CapVerdict(
            allowed=False,
            code="balance_unreadable",
            detail="the account balance could not be read, so the account-level risk cap cannot "
            "be computed. Refusing rather than guessing — 'cannot ask' is never "
            "'affordable'.",
        )

    cap = balance * cap_pct / 100.0
    room = cap - open_risk.total_ccy
    if new_order_risk_ccy > room:
        held = ", ".join(f"magic {m}: ${v:,.2f}" for m, v in sorted(open_risk.per_magic.items()))
        return CapVerdict(
            allowed=False,
            code="account_risk_cap",
            detail=(
                f"this order risks ${new_order_risk_ccy:,.2f} and only ${room:,.2f} is left "
                f"under the account cap (${cap:,.2f} = {cap_pct}% of ${balance:,.2f}). "
                f"The account already has ${open_risk.total_ccy:,.2f} on across "
                f"{open_risk.positions} position(s) and {open_risk.resting} resting order(s)"
                + (f" — {held}." if held else ".")
            ),
            open_risk_ccy=open_risk.total_ccy,
            cap_ccy=cap,
            room_ccy=room,
        )
    return CapVerdict(
        allowed=True, code="", open_risk_ccy=open_risk.total_ccy, cap_ccy=cap, room_ccy=room
    )


# ⚠ WHY THERE IS NO `shrink_to_room()` HERE, and it is not an omission.
#
# `backtest/portfolio/account.py` SCALES a leg's desired size down to the room and the leg opens
# at the granted size — coherent there, because the account hands the number back and the same
# process's emulator uses it.
#
# Nothing hands a size back across a process boundary. A live bot's `Execution` has already opened
# its own position at its own size by the time the bridge talks to the broker; a shrunk order would
# leave the emulator holding one trade and the account holding a smaller one, they would grade
# different R, and `_agrees` would eventually halt the bot on a divergence created by the safety
# feature. That is the identical reasoning `order_sizing` records for the broker's volume band.
#
# The consequence has to be said out loud rather than left implicit: **the backtest and the live
# bot resolve a shortfall DIFFERENTLY** — shrink there, refuse here. On the measured history it
# changes nothing, because the cap never bound at all (`backtest/CLAUDE.md` → *The shared-account
# run*), but that is a fact about one history and not a licence. Anything that tunes the cap has to
# be replayed under the REFUSE policy, or the backtest stops predicting the account.
