"""What it costs to HOLD one recovery trade, in R. One implementation, two drivers.

The recovery engine models price only — it does not run an order layer — so unlike a trade booked
inside `Execution` (which charges friction as it goes) these have to be priced by whoever turns a
`RecoveryTrade` into a booked position. There are two such callers now, the batch adapter and the
shared-account leg, and a second copy of this arithmetic is how they would come to disagree about
what the same trade cost.

⚠ **It takes TIMESTAMPS, not bar indices.** The batch caller has a `DatetimeIndex` and the stepped
caller has only the bar's own clock, and indexing a frame is the one thing they do not share.

⚠ **An unpriced run returns an honest 0.0** — meaning *nothing was priced*, never a claim that
trading was free. Same rule as everywhere else here: never let "no cost" and "cannot ask" be the
same value to a reader; the caller states which it had.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

__all__ = ["hold_cost_r"]


def hold_cost_r(profile, entry_ms: int, exit_ms: int, direction: int, risk_price: float) -> float:
    """Swap + spread + commission for one trade, expressed in that trade's own R.

    Lot size cancels out of the ratio, which is why this needs no quantity: every component is
    per-lot and R is per-lot too.

    `direction` is +1 long / -1 short — gold pays a swap CREDIT to hold short on some tiers, so
    the sign is load-bearing rather than cosmetic. Returns a value to ADD to the trade's R, i.e.
    normally negative.
    """
    swap = getattr(profile, "swap", None)
    if profile is None or swap is None or risk_price <= 0:
        return 0.0

    nights = 0
    day = datetime.fromtimestamp(entry_ms / 1000.0, tz=timezone.utc).date()
    last = datetime.fromtimestamp(exit_ms / 1000.0, tz=timezone.utc).date()
    while day < last:
        day += timedelta(days=1)
        if day.weekday() >= 5:  # the broker books no rollover at the weekend
            continue
        nights += 3 if day.weekday() == swap.triple_weekday else 1

    return (
        (swap.per_lot_per_night(direction) * nights) / (risk_price * swap.contract_size)
        - getattr(profile, "spread", 0.0) / risk_price
        - 2.0
        * getattr(profile, "commission_per_side_per_lot", 0.0)
        / (risk_price * swap.contract_size)
    )
