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

`SoloAccount` is the same object with no RISK cap and no floor — one leg, granted the full size
the budget could fund, i.e. standalone behaviour. Standalone = a portfolio of one.
🔴 **THIS SAID `no cap ... always granted in full` AND THAT STOPPED BEING TRUE ON 2026-09-02.**
It still carries the VENUE ceiling (`max_lots`, default 100 lots), which sits outside the budget
and binds anyway — so it is not a pure passthrough, and the parity anchor is
`SoloAccount(max_lots=None)`, which the harness has to pass. The class docstring owns the rule.
Pure, offline, no app imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

__all__ = [
    "Position",
    "PortfolioAccount",
    "SoloAccount",
    "DEFAULT_MAX_LOTS",
    "DEFAULT_CONTRACT_SIZE",
]

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

# The largest position any leg may hold, in LOTS, unless a caller says otherwise.
#
# 100 is the number Aaron set on 2026-09-02, and it is a POLICY that happens to coincide with a
# MEASUREMENT rather than being derived from it: PU Prime's own ceiling on `XAUUSD.p` is also
# 100 lots (read live off account 700152905, unchanged since the 2026-08-14 reading). He does not
# want to trade more than 100 lots of gold whatever a future broker permits, so the default does
# not track the venue and must not be "corrected" to it — a broker offering 200 does not raise it.
#
# ⚠ It is a DEFAULT, not a constant: `max_lots=None` switches the ceiling off, which is what a
# parity harness wants when its Pine twin has no such rule.
#
# ⚠ **The live path takes `min(this, the broker's own maximum)`** — a configured ceiling above
# what the venue accepts is not a ceiling, it is an order that gets rejected.
DEFAULT_MAX_LOTS = 100.0

# Instrument units in ONE lot. 100 oz of gold, and the same default `fills.AccountProfile` uses
# for the identical conversion — the two must agree or costs and the ceiling disagree about what
# a lot is.
DEFAULT_CONTRACT_SIZE = 100.0


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
        self,
        *,
        balance: float,
        risk_cap_pct: float,
        entry_floor_pct: float = 0.0,
        all_or_nothing: bool = False,
        leg_priority: Optional[dict] = None,
        leg_risk_pct: Optional[dict] = None,
        max_lots: Optional[float] = DEFAULT_MAX_LOTS,
        contract_size: float = DEFAULT_CONTRACT_SIZE,
    ) -> None:
        self.balance = float(balance)
        self.risk_cap_pct = float(risk_cap_pct)
        self.entry_floor_pct = float(entry_floor_pct)
        # THE VENUE CEILING — the largest position any leg may hold, in LOTS, whatever its risk
        # % says it wants. `None` switches it off entirely.
        #
        # 🔴 This is the one gate here that is NOT about risk, and reading it as one gets it
        # backwards. Every other check above asks "can the account afford this?"; this one asks
        # "will the broker accept it at all?" — a question with a hard answer that no amount of
        # equity changes. MEASURED 2026-09-02 on PU Prime `XAUUSD.p`: the ceiling is 100 lots,
        # and a 6.6-year replay of the live A+ config from $10,000 asks for more on **25 of its
        # 205 trades**, topping out at **742.60 lots — 7.4x what the venue will take**. Those
        # orders do not get filled small; they get REJECTED, so a replay that books them is
        # describing an account nobody can have.
        #
        # ⚠ **It clamps rather than refuses, and that reverses this repo's older rule.**
        # `algos/shared/order_sizing.py` refused an over-max order for a real reason: a clamped
        # broker order is not the position the emulator is holding, the two grade different R,
        # and the bridge halts on the divergence. That reasoning is sound and is exactly why the
        # clamp lives HERE instead — this is the seam where the strategy decides its own size, so
        # the emulator books the capped qty as its own and the two sides never disagree. Clamping
        # at the ORDER is still wrong; clamping at the DECISION is not. (Aaron's call, 2026-09-02.)
        #
        # ⚠ **It changes what a replay reports above ~$927,000 of balance and nothing below it.**
        # That is the first trade in the A+ book that touches the ceiling. Runs stored before this
        # existed did not model it, so a long compounding run will no longer reproduce its old
        # number — deliberately, because the old number was untradeable past that point.
        #
        # ⚠ **Past the ceiling an account stops compounding and grows LINEARLY**: size is frozen
        # while the balance keeps rising, so risk-per-trade falls away toward zero. That is the
        # real cost of the cap, and it is a property of the venue rather than of this code.
        self.max_lots: Optional[float] = None if max_lots is None else float(max_lots)
        # Instrument units in ONE lot — 100 oz for gold. The cap is quoted in lots because that
        # is the unit the broker refuses in; the legs size in units, so one of the two has to be
        # converted and this is the number that does it. It mirrors `fills.AccountProfile`, which
        # has needed the same conversion for costs since long before this.
        self.contract_size = float(contract_size)
        # Every entry this ceiling shrank: {when, leg, dir, desired_qty, granted_qty, ...}.
        #
        # ⚠ Deliberately NOT folded into `contention`. That log answers "did the legs compete for
        # the budget", and a venue ceiling is not competition — a solo run with no cap and all the
        # room in the world still hits it. Mixing them would make the contention log overstate
        # itself on exactly the runs a reader is using it to judge a stack by.
        self.lot_capped: list[dict] = []
        # THE CONTENTION RULE, stated rather than implied. False = shrink-to-fit: a contested
        # entry takes whatever room is left. True = *risk is never layered*: an entry that cannot
        # be granted in FULL is refused outright and the budget stays with whoever already holds
        # it. Both obey the cap — this decides WHICH TRADE you end up in, not how much is at risk.
        #
        # ⚠ It is deliberately not an entry floor. A floor is one number for the whole account
        # while legs risk different amounts, so any floor high enough to make a 10% leg
        # all-or-nothing also bans a 2.5% leg outright whatever the room (measured: 64 refusals,
        # 0 trades). "Was this granted in full?" needs no per-leg number and holds for any
        # number of legs.
        #
        # ⚠ Defaults OFF. Every run recorded before this existed used shrink-to-fit, and a
        # default that changed them would re-write history rather than add an option.
        self.all_or_nothing = bool(all_or_nothing)
        # LEG PRECEDENCE. `leg_priority` ranks the legs (LOWER number = higher precedence) and
        # `leg_risk_pct` says how much of the balance each one wants when it trades.
        #
        # 🔴 It cannot be "the better leg wins the clash". By the time the priority leg asks, the
        # other one is already holding the budget, and the only way to take it back is closing a
        # live trade — which this repo refuses on principle. So precedence acts BEFORE the clash:
        # a priority leg's risk stays RESERVED while it is flat, and lower legs get only what is
        # genuinely spare. See `_headroom_for`.
        #
        # ⚠ Both default empty, which makes the headroom zero and every stored run identical.
        self.leg_priority: dict = dict(leg_priority or {})
        self.leg_risk_pct: dict = dict(leg_risk_pct or {})
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

    def _headroom_for(self, leg: str) -> float:
        """Budget that is SPOKEN FOR by higher-precedence legs which are not holding yet.

        ⚠ Only legs strictly ABOVE `leg` in precedence, and only while they are FLAT — a leg that
        is already holding has its real reservation inside `reserved()`, and counting it here too
        would subtract its risk twice. That double count is the mutation the tests pin.

        ⚠ A leg with no declared risk contributes nothing, so an unknown leg cannot silently
        shrink somebody else's room.
        """
        if not self.leg_priority:
            return 0.0
        mine = self.leg_priority.get(leg)
        if mine is None:
            return 0.0
        total = 0.0
        for other, rank in self.leg_priority.items():
            if other == leg or rank >= mine:
                continue
            if self.has_position(other):
                continue  # its real reservation is already in reserved()
            total += self.leg_risk_pct.get(other, 0.0) * self.balance
        return total

    def room_for(self, leg: str) -> float:
        """The room THIS leg may use — the shared room less anything reserved for its betters."""
        return max(0.0, self.room() - self._headroom_for(leg))

    def _floor(self) -> float:
        return self.entry_floor_pct * self.balance

    @staticmethod
    def _risk_of(qty: float, entry: float, stop: float, point_value: float) -> float:
        """Actual dollars this trade puts at risk — qty × distance-to-stop × point value."""
        return abs(qty) * abs(entry - stop) * point_value

    # ── entries ───────────────────────────────────────────────────────────────
    def _cap_to_max_lots(self, leg: str, dir: int, desired_qty: float) -> float:
        """Clamp one leg's desired size to the venue ceiling. Returns the size it may actually ask
        for, and records the clamp when it bites.

        ⚠ **This runs BEFORE the risk arithmetic, not after it, and the order matters.** Every
        number downstream — the desired risk, the share of the budget this leg is asking for, the
        proportional split when two legs fill on one bar — has to describe the position that can
        really be opened. Capping afterwards would let a leg reserve budget against 742 lots it
        was never going to hold, and quietly block the other leg out of room nobody used.

        ⚠ **It never rounds to the broker's volume STEP.** That belongs to the live path, which
        knows the step and rounds DOWN; doing it here would put a broker's fill granularity into
        every lab number and make the two disagree about what a clean replay is.
        """
        if self.max_lots is None or self.contract_size <= 0 or desired_qty <= 0:
            return desired_qty
        ceiling = self.max_lots * self.contract_size
        if desired_qty <= ceiling:
            return desired_qty
        self.lot_capped.append(
            {
                "when": self.now,
                "leg": leg,
                "dir": dir,
                "desired_qty": round(desired_qty, 6),
                "granted_qty": round(ceiling, 6),
                "desired_lots": round(desired_qty / self.contract_size, 4),
                "max_lots": self.max_lots,
                # How far over the ceiling the strategy actually wanted to be. This is the number
                # that says whether the cap is a rare edge or the thing now driving the account.
                "over_x": round(desired_qty / ceiling, 3),
            }
        )
        return ceiling

    def request_fill(
        self, leg: str, dir: int, entry: float, stop: float, desired_qty: float, point_value: float
    ) -> float:
        """A leg fills and asks for `desired_qty` (its own sizing). Returns the granted qty
        (0.0 = blocked). The gate runs at FILL, so a resting order that never fills holds
        nothing. The desired qty is SCALED to the room, never recomputed."""
        desired_qty = self._cap_to_max_lots(leg, dir, desired_qty)
        desired_risk = self._risk_of(desired_qty, entry, stop, point_value)
        granted_risk = min(desired_risk, self.room_for(leg))
        # a zero grant (no room) is a block, not a zero-size fill — even when the floor is 0.
        # `_MIN_GRANT_USD` makes "essentially zero" a block too: see its note, one dust fill
        # silently retired a leg for five and a half years.
        if granted_risk < _MIN_GRANT_USD or self._below_floor(granted_risk):
            self._log_contention(leg, dir, desired_risk, 0.0, blocked=True)
            return 0.0
        if self._is_shrunk(desired_risk, granted_risk):
            if self.all_or_nothing:
                # Refused, not "granted and then dropped" — the log records 0.0 granted so a
                # reader cannot mistake this for a shrink that happened to be discarded.
                self._log_contention(leg, dir, desired_risk, 0.0, blocked=True)
                return 0.0
            self._log_contention(leg, dir, desired_risk, granted_risk, blocked=False)
        return self._open(
            leg, dir, entry, stop, desired_qty, desired_risk, granted_risk, point_value
        )

    def request_fills(self, requests: Sequence[dict]) -> dict[str, float]:
        """Several legs fill on the SAME bar. Split the room in proportion to each leg's
        desired risk (one split, no re-split), then floor-check each. Each request dict:
        {leg, dir, entry, stop, desired_qty, point_value}."""
        # 🔴 With precedence declared, a same-bar tie is settled BY RANK, not by proportion — the
        # better leg takes what it needs first and the rest split what is left. Splitting
        # proportionally would let a lower leg dilute the one it is supposed to defer to, on the
        # one bar where they arrive together. With no precedence declared this is skipped entirely
        # and the original proportional split runs, so no stored run moves.
        if self.leg_priority:
            return self._request_fills_by_rank(requests)
        # The ceiling applies before the room is split, for the reason `_cap_to_max_lots` gives:
        # a leg must not claim a share of the budget proportional to a size it cannot hold.
        # ⚠ Copied rather than mutated — `requests` belongs to the caller, and the by-rank path
        # above re-reads the same dicts through `request_fill`.
        requests = [
            {**r, "desired_qty": self._cap_to_max_lots(r["leg"], r["dir"], r["desired_qty"])}
            for r in requests
        ]
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
            if granted_risk < _MIN_GRANT_USD or self._below_floor(granted_risk):
                self._log_contention(r["leg"], r["dir"], desired_risk, 0.0, blocked=True)
                out[r["leg"]] = 0.0
                continue
            if self._is_shrunk(desired_risk, granted_risk):
                if self.all_or_nothing:
                    self._log_contention(r["leg"], r["dir"], desired_risk, 0.0, blocked=True)
                    out[r["leg"]] = 0.0
                    continue
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

    def _request_fills_by_rank(self, requests: Sequence[dict]) -> dict:
        """Same-bar fills settled in precedence order — better legs first, each taking
        `min(desired, its own room)`, with every grant reducing what the next one sees.

        ⚠ Each leg is still asked through `room_for`, so a lower leg keeps deferring to any
        higher leg that is FLAT and has not filled on this bar either.
        """
        out: dict = {}
        ordered = sorted(
            requests, key=lambda r: self.leg_priority.get(r["leg"], len(self.leg_priority))
        )
        for r in ordered:
            out[r["leg"]] = self.request_fill(
                r["leg"], r["dir"], r["entry"], r["stop"], r["desired_qty"], r["point_value"]
            )
        return out

    @staticmethod
    def _is_shrunk(desired_risk: float, granted_risk: float) -> bool:
        """Did the budget actually take size away? See `_GRANT_EPS` for why this is not `<`."""
        return granted_risk < desired_risk * (1.0 - _GRANT_EPS)

    def _below_floor(self, granted_risk: float) -> bool:
        """Is this grant under the entry floor? Carries `_GRANT_EPS`, for the reason that
        constant already documents one method up — and it was MISSING here until 2026-08-20.

        🔴 The floor is a fraction of the BALANCE and a leg's own risk % is too, so the natural way
        to express *risk is never layered* — set the floor to the leg's full risk, so anything the
        budget shrinks is refused instead — puts `granted` and `floor` on exactly the same number.
        `granted = min(desired, cap - reserved)` reaches it by a different arithmetic route (a leg
        DIVIDES by the stop distance to get a qty, the account re-MULTIPLIES), so the two differ in
        the last bit and a bare `<` refuses an entry nothing was competing for.

        MEASURED before this existed: A+ at 10% under a 10% cap with the floor at 10% was refused
        **3,650 times over 7.9 years and took 31 trades instead of 181** — a book that reads like a
        savage allocator and is a rounding error. The shrink test has carried this tolerance since
        the same defect was found there; the floor test was left on `<`, and nobody had set a floor
        equal to a leg's own risk until now. ⚠ **No stored run moves**: `entry_floor_pct` defaults
        to 0.0, and with a zero floor both forms answer identically.
        """
        floor = self._floor()
        return floor > 0.0 and granted_risk < floor * (1.0 - _GRANT_EPS)

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
    """One leg, no RISK cap, no floor — grants the full desired qty out of the budget. Reproduces
    standalone behaviour (scale == 1), so a bot run through this is unchanged by contention.

    🔴 **It still carries the VENUE ceiling, and that is the one way it is no longer a pure
    passthrough (2026-09-02).** `room()` is infinite, so the budget never binds; `max_lots` is not
    part of the budget and does bind, because a broker refusing a 742-lot order does not care that
    the account could afford it. A solo replay that never asks for more than `max_lots` is
    byte-identical to its old self — MEASURED: the A+ book does not touch the ceiling until the
    balance passes ~$927,000.

    ⚠ **The parity anchor therefore needs `max_lots=None`, and the harness has to pass it.** The
    Pine twin has no such rule, so leaving the ceiling on would grade a capped Python run against
    an uncapped chart and report a parity break that is really a policy difference. This is the
    same trap as any other feature the chart cannot express — the gate must compare like with
    like or it is measuring the wrong thing. `compare_strategy.py` must stay exit 0.
    """

    def __init__(
        self,
        *,
        balance: float,
        max_lots: Optional[float] = DEFAULT_MAX_LOTS,
        contract_size: float = DEFAULT_CONTRACT_SIZE,
    ) -> None:
        super().__init__(
            balance=balance,
            risk_cap_pct=float("inf"),
            entry_floor_pct=0.0,
            max_lots=max_lots,
            contract_size=contract_size,
        )

    def room(self) -> float:
        return float("inf")  # never the bottleneck; desired is always granted in full
