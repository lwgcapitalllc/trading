"""The shared account — one balance, one live risk budget the legs compete for.

This is the broker for a stacked portfolio. Legs don't own money; they ASK the account to
enter and it decides how much of their desired size fits (or refuses). The whole contention
model lives here:

  * one realized `balance`, every leg's P&L books onto it;
  * open trades RESERVE risk measured to their CURRENT stop, so a trade at breakeven reserves
    nothing and its room is freed for others;
  * the cap is a % of the live balance;
  * a leg asks with a DESIRED qty (it sized itself off its own logic); the account grants the
    fraction that fits — full size when there's room, shrunk when there isn't, blocked below a
    floor. It SCALES the leg's qty, it never re-derives it — so a leg run alone is untouched.
  * same-bar ties split the room by each leg's desired risk.

`SoloAccount` is the same object with no cap and no floor — one leg, always granted in full,
i.e. standalone behaviour. Standalone = a portfolio of one. This is the parity anchor.
Pure, offline, no app imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

__all__ = ["Position", "PortfolioAccount", "SoloAccount"]

# A grant within this much of the desired risk IS the desired risk.
#
# `granted = min(desired, room)` and `room = cap - reserved`, so a lone leg whose own risk %
# equals the account cap lands EXACTLY on the boundary — `mpc_sos_fade` at `exec_risk_pct = 10`
# under a 10% cap does it on every single entry. In exact arithmetic those two are equal and
# nothing is refused; in floats the room comes out a few parts in 1e16 short, `granted < desired`
# is true, and the entry is logged as a shrink.
#
# Measured before this existed: a 6.5-year two-leg run reported **11 contention events totalling
# $0.00 of refused risk** — every one of them float noise, on a run where the cap never actually
# bound. That is the whole log made unreadable, and downstream it would put "this trade was
# shrunk" markers on a chart for trades granted in full.
#
# It is deliberately RELATIVE and deliberately tiny: 1e-9 of the desired risk is $0.000001 on a
# $1,000 risk, far below a broker's smallest volume step, while a real shrink is a fraction of the
# position. It is not a rounding of the granted QTY — the leg still gets `min(desired, room)`
# scaled exactly; it only decides whether the difference is worth calling contention.
_GRANT_EPS = 1e-9

# The smallest grant that may become a POSITION, in account currency. Below this the entry is
# refused outright, exactly as if there were no room at all.
#
# 🔴 Measured 2026-08-09, and it is the first time a shared run ever had a tight budget: a leg
# asked for $4,385.98 of risk against a room of a fraction of a cent, and `_open` scaled its qty
# by `granted/desired` — about 1e-6 — opening a position of essentially no size. Nothing errored.
# But a leg holds ONE position at a time, so that dust occupied its only slot from November 2020
# to August 2026: **18 trades instead of 181**, no refusal in the log, and from outside it reads
# exactly like a strategy that stopped finding setups.
#
# ⚠ `entry_floor_pct` is the POLICY knob for this ("skip it rather than trickle it in") and it
# defaults to 0.0, which switches the policy off. That default is defensible — a caller who
# states no floor should not have one invented — but it cannot be the only guard, because a
# position too small to matter is a CORRECTNESS problem rather than a preference: it consumes the
# slot whatever the caller thinks about small positions.
#
# One cent is chosen so it lines up with `_log_contention`'s own 2dp rounding. Before this, a
# grant of $0.003 was logged as `granted_risk: 0.0, blocked: False` — a state that branch cannot
# produce, so the log itself read as impossible while being perfectly accurate.
_MIN_GRANT_USD = 0.01


@dataclass
class Position:
    """One open trade the account is carrying. Reservation is recomputed from `current_stop`
    every time it's asked, so moving the stop to breakeven drops it to zero automatically."""

    leg: str
    dir: int  # +1 long, -1 short
    entry: float
    current_stop: float
    qty: float
    point_value: float  # account dollars per 1.0 price unit per 1.0 qty

    def reserved(self) -> float:
        # dir·(entry − stop): positive while the stop is on the losing side of entry (real risk),
        # zero at breakeven, zero once the stop locks profit. max(0,·) enforces that.
        risk_per_unit = max(0.0, self.dir * (self.entry - self.current_stop))
        return self.qty * self.point_value * risk_per_unit


class PortfolioAccount:
    """One shared account. Cap = `risk_cap_pct` of live balance; an entry granted less than
    `entry_floor_pct` of balance in risk is skipped rather than trickled in."""

    def __init__(
        self, *, balance: float, risk_cap_pct: float, entry_floor_pct: float = 0.0
    ) -> None:
        self.balance = float(balance)
        self.risk_cap_pct = float(risk_cap_pct)
        self.entry_floor_pct = float(entry_floor_pct)
        self._positions: dict[str, Position] = {}
        self._peak = self.balance
        self.halted = False
        # the simulator stamps `now` with the current tick time before stepping the legs, so a
        # shrunk/blocked entry is logged with WHEN it happened. `contention` is the record of
        # every collision — the whole point of sharing an account. (SoloAccount never contends.)
        self.now: Optional[int] = None
        self.contention: list[dict] = []
        # What the account actually CARRIED, sampled by the simulator once per tick. The
        # contention log answers "was anything refused"; this answers the question underneath
        # it — how close the legs ever came to the cap — and the two can disagree completely.
        # A reservation falls to zero the moment a stop reaches breakeven, so a book can hold
        # two full positions all day and still log nothing, which reads as "the legs never
        # competed" when what happened is that the budget was released before they could.
        self.peak_reserved = 0.0  # dollars
        self.peak_reserved_pct = 0.0  # of the balance AT THAT MOMENT, not of the opening
        self.peak_concurrent = 0  # most legs holding a position at once

    # ── budget ────────────────────────────────────────────────────────────────
    def reserved(self) -> float:
        return sum(p.reserved() for p in self._positions.values())

    def cap(self) -> float:
        return self.risk_cap_pct * self.balance

    def room(self) -> float:
        return max(0.0, self.cap() - self.reserved())

    def _floor(self) -> float:
        return self.entry_floor_pct * self.balance

    @staticmethod
    def _risk_of(qty: float, entry: float, stop: float, point_value: float) -> float:
        """Actual dollars this trade puts at risk — qty × distance-to-stop × point value."""
        return abs(qty) * abs(entry - stop) * point_value

    # ── entries ───────────────────────────────────────────────────────────────
    def request_fill(
        self, leg: str, dir: int, entry: float, stop: float, desired_qty: float, point_value: float
    ) -> float:
        """A leg fills and asks for `desired_qty` (its own sizing). Returns the granted qty
        (0.0 = blocked). The gate runs at FILL, so a resting order that never fills holds
        nothing. The desired qty is SCALED to the room, never recomputed."""
        desired_risk = self._risk_of(desired_qty, entry, stop, point_value)
        granted_risk = min(desired_risk, self.room())
        # a zero grant (no room) is a block, not a zero-size fill — even when the floor is 0.
        # `_MIN_GRANT_USD` makes "essentially zero" a block too: see its note, one dust fill
        # silently retired a leg for five and a half years.
        if granted_risk < _MIN_GRANT_USD or granted_risk < self._floor():
            self._log_contention(leg, dir, desired_risk, 0.0, blocked=True)
            return 0.0
        if self._is_shrunk(desired_risk, granted_risk):
            self._log_contention(leg, dir, desired_risk, granted_risk, blocked=False)
        return self._open(
            leg, dir, entry, stop, desired_qty, desired_risk, granted_risk, point_value
        )

    def request_fills(self, requests: Sequence[dict]) -> dict[str, float]:
        """Several legs fill on the SAME bar. Split the room in proportion to each leg's
        desired risk (one split, no re-split), then floor-check each. Each request dict:
        {leg, dir, entry, stop, desired_qty, point_value}."""
        room = self.room()
        risks = [
            self._risk_of(r["desired_qty"], r["entry"], r["stop"], r["point_value"])
            for r in requests
        ]
        total = sum(risks)
        factor = 1.0 if total <= room else (room / total if total > 0 else 0.0)

        out: dict[str, float] = {}
        for r, desired_risk in zip(requests, risks):
            granted_risk = desired_risk * factor
            if granted_risk < _MIN_GRANT_USD or granted_risk < self._floor():
                self._log_contention(r["leg"], r["dir"], desired_risk, 0.0, blocked=True)
                out[r["leg"]] = 0.0
                continue
            if self._is_shrunk(desired_risk, granted_risk):
                self._log_contention(r["leg"], r["dir"], desired_risk, granted_risk, blocked=False)
            out[r["leg"]] = self._open(
                r["leg"],
                r["dir"],
                r["entry"],
                r["stop"],
                r["desired_qty"],
                desired_risk,
                granted_risk,
                r["point_value"],
            )
        return out

    @staticmethod
    def _is_shrunk(desired_risk: float, granted_risk: float) -> bool:
        """Did the budget actually take size away? See `_GRANT_EPS` for why this is not `<`."""
        return granted_risk < desired_risk * (1.0 - _GRANT_EPS)

    def _log_contention(
        self, leg: str, dir: int, desired_risk: float, granted_risk: float, *, blocked: bool
    ) -> None:
        self.contention.append(
            {
                "time": self.now,
                "leg": leg,
                "dir": dir,
                "desired_risk": round(desired_risk, 2),
                "granted_risk": round(granted_risk, 2),
                "blocked": blocked,
            }
        )

    def _open(
        self,
        leg: str,
        dir: int,
        entry: float,
        stop: float,
        desired_qty: float,
        desired_risk: float,
        granted_risk: float,
        point_value: float,
    ) -> float:
        if desired_risk <= 0.0 or desired_qty <= 0.0:
            return 0.0
        qty = desired_qty * (granted_risk / desired_risk)  # scale the leg's own size to fit
        self._positions[leg] = Position(leg, dir, entry, stop, qty, point_value)
        return qty

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def update_stop(self, leg: str, current_stop: float, qty: Optional[float] = None) -> None:
        """Each bar: report a position's live stop (and its size, if a partial close shrank it)."""
        p = self._positions.get(leg)
        if p is None:
            return
        p.current_stop = current_stop
        if qty is not None:
            p.qty = qty

    def book_pnl(self, leg: str, amount: float) -> None:
        """Realize P&L (or a cost) onto the shared balance as it happens — partial exits and
        commission book here, so the balance is right the instant another leg sizes off it."""
        self.balance += amount
        self._peak = max(self._peak, self.balance)

    def close_position(self, leg: str) -> None:
        """Free a leg's reservation when its trade fully closes (P&L already booked)."""
        self._positions.pop(leg, None)

    def on_close(self, leg: str, pnl: float) -> None:
        """Convenience: book the whole trade's P&L and free its reservation in one call
        (for callers that don't book partials incrementally)."""
        self.book_pnl(leg, pnl)
        self.close_position(leg)

    def has_position(self, leg: str) -> bool:
        return leg in self._positions

    def sample_exposure(self) -> None:
        """Record what the account is carrying right now. Called once per tick by the simulator.

        Sampled rather than derived at the end, because both peaks are instants: the open risk
        is recomputed from every position's CURRENT stop, so it is a moving number that leaves
        no trace once the stops advance.
        """
        held = len(self._positions)
        self.peak_concurrent = max(self.peak_concurrent, held)
        res = self.reserved()
        if res > self.peak_reserved:
            self.peak_reserved = res
        if self.balance > 0.0:
            self.peak_reserved_pct = max(self.peak_reserved_pct, res / self.balance)

    # ── account-level halt ──────────────────────────────────────────────────--
    def check_trailing_halt(self, trailing_max_loss: Optional[float]) -> bool:
        """Hard halt on the combined balance: peak-to-here drop ≥ limit stops all legs.
        Daily-loss halts are day-boundary aware and are applied at the clock/simulator level."""
        if trailing_max_loss is not None and (self._peak - self.balance) >= trailing_max_loss:
            self.halted = True
        return self.halted


class SoloAccount(PortfolioAccount):
    """One leg, no cap, no floor — always grants the full desired qty. Reproduces standalone
    behaviour exactly (scale == 1), so a bot run through this is unchanged. This is the parity
    anchor: `compare_strategy.py` must stay exit 0 with a SoloAccount."""

    def __init__(self, *, balance: float) -> None:
        super().__init__(balance=balance, risk_cap_pct=float("inf"), entry_floor_pct=0.0)

    def room(self) -> float:
        return float("inf")  # never the bottleneck; desired is always granted in full
