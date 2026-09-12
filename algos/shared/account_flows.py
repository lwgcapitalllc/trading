"""What an account made, net of the money put in or taken out — off the broker's own records.

🔴 **A DEPOSIT IS NOT A RETURN, AND THE RETURN THIS REPO REPORTED COUNTED ONE (2026-09-12).** The
runner wrote `(balance - starting_balance) / starting_balance`, the anchor being the balance a bot
first saw on the account — so every dollar arriving after the anchor read as profit. A $9,860.51
transfer into live account 34957946 showed as **+2,181.67%** on the Bots page, on the Overview and
in Telegram's /balance, over two bots that had not traded. A withdrawal reads as a loss the same
way. Aaron: *"if I deposit money that should not show as the account return, same thing if I
withdraw."*

**The broker already says which is which.** MT5 books a deposit or a withdrawal as a deal of type
BALANCE, apart from every trade. So this reads the account's WHOLE deal history, and states:

- `capital_in` — every BALANCE and BONUS deal added up: the money put in, less the money taken out;
- `pnl_usd` — the broker's balance minus that: what trading made over the account's life;
- `return_pct` — TIME-WEIGHTED: the return between one deposit or withdrawal and the next,
  chained. A deposit neither adds to it nor dilutes it, so it measures the strategy rather than
  when money arrived — how a fund reports its return.

⚠ **Not "return on the balance before any trades".** That keeps a deposit out of the numerator and
out of the DENOMINATOR too: after this deposit, one 5% trade on $10,312 would read as +114% of the
$451.97 the account opened with.

MEASURED 2026-09-12 on the box, read-only (a throwaway probe, deleted after): live 34957946 holds
2 deals, both BALANCE — +451.97 and +9,860.51, each "Transfer In from …" — and the deals rebuild a
balance of 10,312.48 against the broker's 10,312.48. Demo 700152905 holds 23: one BALANCE of
+10,000.00 ("demo"), 11 buys and 11 sells, rebuilt 15,844.46 against 15,844.46 — trading P&L
+5,844.46, time-weighted +58.4446%.

⚠ **The deals must add up to the broker's balance to the cent, or NOTHING is reported.** Summing
every deal checks the history AND this module's split of it: a history that did not arrive whole,
or a deal counted on the wrong side, shows up as a difference — and a return off a history missing
a deposit is a confident wrong number (rule 1: *cannot tell* must not look like an answer).

⚠ **CREDIT is not balance** (MT5 keeps it in its own field), so it is skipped. **A BONUS is money
put in**, not something the strategy earned. Every other type that moves the balance — trades,
commission, charges, interest, corrections — is trading P&L. If that split is ever wrong on a real
account, the rebuild check above refuses rather than reporting it.

⚠ **Pure: no MetaTrader5, no I/O, no clock.** The runner hands it the deals and the balance read
off the same terminal in the same poll; anything holding those two can be checked against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

# MetaTrader5's own values, read off the box's module on 2026-09-12 — not copied from its docs.
# Named here so this module needs no MetaTrader5 import and runs in the Mac test suite.
DEAL_BALANCE = 2
DEAL_CREDIT = 3
DEAL_BONUS = 6

#: Deals that move money INTO or OUT OF the account, rather than earning or losing it.
FLOW_TYPES = frozenset({DEAL_BALANCE, DEAL_BONUS})

#: How far the rebuilt balance may sit from the broker's. A cent: every figure is to two
#: decimals, so anything wider is a deal this module did not see, not rounding.
RECONCILE_TOLERANCE = 0.01


@dataclass(frozen=True)
class AccountReturn:
    """What the account made net of money in and out. The three figures are `None` TOGETHER,
    with `reason` saying why — never a figure off a history that does not add up."""

    capital_in: Optional[float]
    pnl_usd: Optional[float]
    return_pct: Optional[float]
    flows: int
    reason: Optional[str] = None


def _refused(reason: str, flows: int = 0) -> AccountReturn:
    return AccountReturn(None, None, None, flows, reason)


def _money(deal) -> float:
    """What one deal did to the balance. `fee` is absent on older MT5 builds."""
    return sum(
        float(getattr(deal, field, 0.0) or 0.0) for field in ("profit", "commission", "swap", "fee")
    )


def account_return(deals: Optional[Iterable], broker_balance: Optional[float]) -> AccountReturn:
    """Net deposits, trading P&L and the time-weighted return, from the account's whole history.

    `deals` is every deal on the account (MT5's `TradeDeal`, or anything with the same fields),
    `None` when the history could not be read. `broker_balance` is the balance the terminal
    reports, read in the same poll — `None` when it could not be.
    """
    if deals is None:
        return _refused("the account's deal history could not be read")
    if broker_balance is None:
        return _refused("the account's balance could not be read")

    # Deposits and trades are interleaved in time, and the return between two deposits needs them
    # in order. The ticket breaks a tie inside one millisecond; MT5 numbers deals in sequence.
    ordered = sorted(
        deals,
        key=lambda d: (int(getattr(d, "time_msc", 0) or 0), int(getattr(d, "ticket", 0) or 0)),
    )
    balance = capital = 0.0
    growth = 1.0
    start: Optional[float] = None  # the balance a period opened on; None before the first deposit
    flows = 0

    def close(balance_now: float) -> Optional[str]:
        """Fold the period that just ended into `growth`, or say why it cannot be."""
        nonlocal growth
        if start is None:
            return None
        if start <= 0:
            # The account held nothing, so there is no balance a return could be measured on —
            # fine while nothing traded, and a refusal if something did.
            if abs(balance_now - start) <= RECONCILE_TOLERANCE:
                return None
            return "money was made or lost while the account held nothing"
        growth *= balance_now / start
        return None

    for d in ordered:
        kind = getattr(d, "type", None)
        if kind == DEAL_CREDIT:
            continue
        money = _money(d)
        if kind in FLOW_TYPES:
            problem = close(balance)
            if problem:
                return _refused(problem, flows)
            balance += money
            capital += money
            flows += 1
            start = balance
        else:
            balance += money

    if flows == 0:
        return _refused("no deposit is on record, so there is nothing to measure a return on")
    if abs(balance - broker_balance) > RECONCILE_TOLERANCE:
        return _refused(
            f"the deals add up to {balance:,.2f} while the broker reports {broker_balance:,.2f} — "
            "a deal is missing from the history, or one landed between the two reads",
            flows,
        )
    problem = close(broker_balance)
    if problem:
        return _refused(problem, flows)
    return AccountReturn(
        capital_in=round(capital, 2),
        pnl_usd=round(broker_balance - capital, 2),
        return_pct=round((growth - 1.0) * 100.0, 2),
        flows=flows,
    )
