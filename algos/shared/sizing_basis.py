"""The balance a strategy may size against, which is not always the balance the broker reports.

🔴 **Built 2026-08-26.** A broker request that timed out was re-sent five times, five copies of
one order filled, and the account gained **$3,344.80 it had not earned**. Every trade after that
sized off the inflated figure: the next one went out at 0.53 lots where the strategy's own risk
percentage called for 0.40. **A windfall from a defect does not just need labelling in the
record — it compounds into the size of every trade that follows, and nothing in the system says
so.** The four trades were marked as not-strategy-performance the same night; the balance they
left behind kept working regardless.

**One seam, deliberately.** Three places in the live path read the account balance — the startup
capital, the flat-moment equity re-anchor, and the account-level risk cap — and all three must
agree, or the strategy sizes against one number while the cap measures another. That is the same
shape as 2026-08-07, where the conversion from the strategy's units to the broker's lots existed
in no single place and was wrong by 221x with every artefact reading as correct.

⚠ **It REFUSES; it never clamps.** An adjustment that would leave nothing to trade on returns
`None`, which every caller already treats as "cannot size" — the same three-state rule as
`mt5_link`. Silently trading a floor would be a size nobody chose.
"""

from typing import Optional


class SizingBasisRefused(Exception):
    """The adjustment leaves no usable balance. Raised only by `describe`, never by the hot path."""


def sizing_basis(raw_balance: Optional[float], adjustment: Optional[float]) -> Optional[float]:
    """The balance to size against: the broker's, plus a STATED adjustment.

    `raw_balance` of `None` stays `None` — "the terminal could not be asked" must not become a
    number, which is rule 1 and the reason this returns an Optional at all.

    `adjustment` is ADDED, so a windfall to exclude is written as a NEGATIVE number. Addition is
    unambiguous arithmetic; an "amount to exclude" invites a sign error, and a sign error here
    makes every position bigger rather than smaller.

    Returns `None` when the result is not a usable basis (zero or below). ⚠ **Never clamped to a
    minimum** — a bot that cannot afford its own strategy must refuse, exactly as
    `order_sizing` refuses an order below the broker minimum rather than rounding it up.
    """
    if raw_balance is None:
        return None
    if not adjustment:
        return float(raw_balance)
    adjusted = float(raw_balance) + float(adjustment)
    if adjusted <= 0:
        return None
    return adjusted


def describe(raw_balance: Optional[float], adjustment: Optional[float]) -> str:
    """One line for the log, and it is REQUIRED reading rather than decoration.

    An adjusted basis that is not announced is indistinguishable from a broker balance, and the
    next person to reconcile the bot's sizing against the account statement would find a gap with
    nothing anywhere to explain it. Returns "" when there is no adjustment, so the ordinary case
    stays quiet.
    """
    if not adjustment or raw_balance is None:
        return ""
    adjusted = sizing_basis(raw_balance, adjustment)
    if adjusted is None:
        return (
            f"REFUSING to size: the broker balance is {float(raw_balance):,.2f} and the stated "
            f"adjustment of {float(adjustment):,.2f} leaves nothing to trade on. Nothing is "
            f"clamped - fix the adjustment or fund the account."
        )
    return (
        f"Sizing basis {adjusted:,.2f} = broker balance {float(raw_balance):,.2f} "
        f"{'+' if adjustment >= 0 else '-'} {abs(float(adjustment)):,.2f} stated adjustment"
    )
