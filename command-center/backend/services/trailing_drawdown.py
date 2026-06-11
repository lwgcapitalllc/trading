"""
End-of-day trailing max-loss (MLL) calculator.

Standalone and side-effect-free so it can be unit-tested in isolation.
Models a prop-firm trailing drawdown: a loss floor that trails the highest
end-of-day (EOD) balance upward, never downward, and optionally freezes once
the account reaches a lock balance.
"""

from __future__ import annotations

from typing import Optional


def compute_trailing_mll(
    daily_pnl: list[dict],
    account_size: float,
    mll_amount: float,
    lock_balance: Optional[float],
) -> dict:
    """
    Walk daily P&L in order and evaluate a trailing end-of-day max-loss floor.

    Floor rules:
      - Start floor = account_size - mll_amount.
      - After each EOD, the floor trails the highest EOD balance seen so far:
        floor = highest_eod_balance - mll_amount. It only ever moves up.
      - If lock_balance is given, it is the locked floor value itself — the highest
        the floor can ever reach. The trailing floor is simply capped at it:
        floor = min(highest_eod_balance - mll_amount, lock_balance).
        When lock_balance is None (e.g. Tradeify), the floor trails forever.

    Breach detection:
      The floor that applies during a given day is the one set by all PRIOR EODs,
      so each day is tested against the floor before that day's EOD update.
      Breach = the balance touches or drops below the current floor.

      We only have daily P&L, not intraday ticks. If a day dict carries an
      intraday low balance under "low", that value is tested; otherwise the day's
      EOD balance is used. With EOD-only data an intraday breach that recovered by
      the close cannot be seen — a known limitation of daily-resolution data.

    Returns:
      {
        "breached": bool,
        "breach_day": int | None,        # 1-based position in daily_pnl
        "min_floor_distance": float,     # closest balance ever got to the floor
                                         # (<= 0 means breached)
        "final_floor": float,
        "highest_eod_balance": float,
      }
    """
    start_balance = float(account_size)
    floor = start_balance - float(mll_amount)
    highest_eod = start_balance

    breached = False
    breach_day: Optional[int] = None
    min_floor_distance = float("inf")

    cumulative = 0.0
    for idx, day in enumerate(daily_pnl, start=1):
        cumulative += day.get("pnl", 0.0) or 0.0
        eod_balance = start_balance + cumulative

        # Lowest balance to test this day: intraday low if the data carries one,
        # else the EOD balance (daily-resolution limitation noted above).
        low = day.get("low")
        test_balance = float(low) if low is not None else eod_balance

        # Test against the floor set by prior EODs (this day's EOD hasn't moved it yet).
        distance = test_balance - floor
        if distance < min_floor_distance:
            min_floor_distance = distance
        if test_balance <= floor and not breached:
            breached = True
            breach_day = idx

        # EOD floor update — trail the highest EOD balance, capped at the lock floor.
        highest_eod = max(highest_eod, eod_balance)
        new_floor = highest_eod - float(mll_amount)
        if lock_balance is not None:
            new_floor = min(new_floor, float(lock_balance))
        floor = max(floor, new_floor)  # monotonic — never descends

    if min_floor_distance == float("inf"):
        # No days walked — distance from the starting balance to the start floor.
        min_floor_distance = start_balance - floor

    return {
        "breached": breached,
        "breach_day": breach_day,
        "min_floor_distance": round(min_floor_distance, 2),
        "final_floor": round(floor, 2),
        "highest_eod_balance": round(highest_eod, 2),
    }
