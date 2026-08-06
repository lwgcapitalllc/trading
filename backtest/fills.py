"""A2 — the fill & cost model: which level did price reach FIRST, and what did it cost?

**The question this answers.** A bar reports a high and a low but not their ORDER. When one bar
covers both a target and a stop, the bar cannot say which filled — and that single unknown is the
difference between a winning and a losing trade. Someone must decide. This module is that someone,
and it makes the choice explicit and swappable instead of burying it in the strategy.

**Two resolvers, and why BOTH must exist:**

* `BarPathResolver` — the TradingView assumption: if the bar opened nearer its high, assume price
  travelled open→high→low→close (targets first); nearer its low, stop first. It is a GUESS. It is
  also exactly what `mpc_strategy.pine` does, and that is the point — `compare_strategy.py` proves
  the Python bot thinks like the Pine, and a comparison is only meaningful when both sides get the
  SAME information. A resolver that knew more would make the bot disagree with the Pine for a
  reason that isn't a bug, and the regression gate would stop meaning anything. Bar mode is the bot
  deliberately playing dumb so the harness stays honest.
* `TickPathResolver` — walks the real bid/ask stream and reports what actually happened first. This
  is the truth, and it is what a real backtest must use. It will disagree with the Pine on
  ambiguous bars. That disagreement is the model getting BETTER, not drifting.

Keeping both is why parity and honesty don't have to trade off. Never "fix" a tick-mode/Pine
difference by making tick mode guess.

**Costs.** Charged asymmetrically, because they are asymmetric in reality:

* **Spread** — real and measured. Entries and exits transact at the correct side of the book (a
  long buys the ask and sells the bid), so the spread is paid by construction rather than bolted on
  as a fudge factor. Gold on PU Prime **Standard** measures a FIXED ~$0.32 (2026-08-06, 1,893,438
  ticks over 3 whole days: median 0.320, p99 0.370, max 0.390) — see
  `_SPREAD_XAUUSD_PUPRIME_STANDARD` for the by-hour detail and for Vantage's very different $0.22.
  Re-measure with `algos/tools/broker_facts.py` rather than quoting this line: it is a snapshot of
  a broker's pricing, not a constant. ⚠ **It is a fact about an ACCOUNT TIER, not about the
  broker** — the raw tiers carry `SPREAD_UNMEASURED` and REFUSE rather than borrowing this figure.
* **Commission** — a per-side fact about the ACCOUNT TYPE, not the symbol and not an estimate. It
  lives in `AccountProfile`, because on every broker the same symbol costs different amounts on
  different account tiers (PU Prime Standard: $0 + wide spread; Prime: $3.50/side/lot + raw spread).
  There is no default — see `AccountProfile`.
* **Slippage** — NOT a parameter in tick mode. It is measured, because the tick stream already
  contains it: a stop is a market order, so it fills at the next price that actually EXISTS, and the
  gap to that price is the slippage. Measured on XAUUSD.s (2026-07-14, 688k ticks): the median
  tick-to-tick jump is $0.02, but p99 is $0.23 and the worst single gap in one day was **$13.74**.
  A flat assumption cannot represent that, and the tail is not academic: stops are hit precisely
  WHEN price is moving fast, so the slippage conditional on a stop firing lives in the tail, not at
  the median. Filling at the real next tick puts the fat tail exactly where it belongs, for free.
  Only entries and TPs are limits, and a limit does not slip against you — it fills at your price or
  better, or not at all.
* **Latency** — the ONE thing ticks cannot show: the ~50-100ms for an order to reach the broker,
  during which price drifts. Median tick spacing is 75ms, so this is ~1-2 ticks. It is the single
  irreducible assumption in this model, and it is isolated in `AccountProfile.latency_ms` so its
  effect can be tested rather than believed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Sequence

__all__ = ["AccountProfile", "PROFILES", "CostsNotConfigured", "PathResolver", "BarPathResolver",
           "TickPathResolver", "Bar", "Fill", "Level", "SwapModel", "SENTINEL",
           "SPREAD_UNMEASURED"]

# An un-set cost. Not 0.0: zero is a legitimate value (PU Prime Standard genuinely charges no
# commission), so zero must be a thing you can deliberately SAY, distinct from never having said
# anything. A backtest that silently runs at zero cost is how a losing strategy passes review.
SENTINEL = -1.0

# A spread NOBODY HAS MEASURED on this account, as distinct from `spread = 0.0`, which means
# "not priced" and charges nothing on purpose. Same reasoning as SENTINEL one line up, and it
# exists because of a defect this file actually shipped:
#
# 🔴 Until 2026-08-06 all four PU Prime tiers in `PROFILES` carried ONE spread — 0.32, measured on
# a STANDARD demo, which is the single tier priced by a marked-up spread. So selecting
# `puprime_ecn` charged ECN's commission ON TOP OF Standard's spread: a combination no real
# account offers, which overstates every raw tier and flatters Standard. Nothing errored.
#
# ⚠ This is the repo's own "quoting one broker's figure for another is a 50% error" rule one level
# DOWN — the same trap between two ACCOUNTS of one broker rather than between two brokers, and it
# is harder to see, because the broker name on the profile is right.
#
# The fix is a REFUSAL rather than a published number typed into code. A marketing page is not a
# measurement, and the published figures for these tiers contradict each other across sources.
# Measure the tier with `algos/tools/broker_facts.py --history-days 3` against an account of that
# type, then replace the sentinel with what it read.
SPREAD_UNMEASURED = -1.0


class CostsNotConfigured(RuntimeError):
    """A cost input was never set. Raised at construction, not mid-run."""


@dataclass(frozen=True)
class Bar:
    """The minimum a resolver needs about the bar being filled against."""

    time_ms: int
    open: float
    high: float
    low: float
    close: float
    duration_ms: int = 300_000     # 5m default


@dataclass(frozen=True)
class SwapModel:
    """Overnight financing, charged per lot per night held.

    **Why this is not optional.** The MPC SOS Fade runner is DESIGNED to hold overnight, so swap is not a
    rounding error on this strategy — it is a structural cost that hits longs and shorts in opposite
    directions. Gold is ~$400k notional per lot; at ~7% annual financing that is ~$78/night, which is
    exactly what the broker quotes. A backtest without it flatters every long and understates every
    short, i.e. it gets the strategy's direction bias wrong.

    Values come from the symbol's own Specification (MT5: right-click the symbol -> Specification),
    in the broker's published units. PU Prime's formula, quoted verbatim from their fees page:

        Swap in points = Swap (long or short) * Contract Size * 10^(-Digits) * Lot * Nights

    XAUUSD.s check: -79.60 * 100 * 10^-2 * 1 * 1 = -$79.60/lot/night long. `+30.25` short (a credit).

    ⚠ **THOSE NUMBERS MOVE, so do not treat this worked example as a constant.** The same symbol
    read -78.29 / +29.49 on 2026-07-16 and -79.60 / +30.25 on 2026-08-06 — 1.7% / 2.6% adrift in
    three weeks, with nothing to announce it. A swap gets read once, hardcoded, and then quietly
    describes a rate the broker has moved on from, and on a strategy designed to hold overnight it
    is the LARGEST re-priceable cost. Re-read it with `algos/tools/broker_facts.py`.

    `triple_weekday` is the day that carries three nights (the weekend roll). MT5 exposes it as the
    swap-rates table; PU Prime gold books it on WEDNESDAY (=2, Monday-based like date.weekday()).
    Getting this wrong misprices ~1 night in 5.
    """

    swap_long_points: float = SENTINEL
    swap_short_points: float = SENTINEL
    contract_size: float = 100.0
    digits: int = 2
    triple_weekday: int = 2          # Wednesday, per PU Prime's swap-rates table

    def __post_init__(self) -> None:
        for name, v in (("swap_long_points", self.swap_long_points),
                        ("swap_short_points", self.swap_short_points)):
            if v == SENTINEL:
                raise CostsNotConfigured(
                    f"{name} not set. Read it off the symbol's Specification window — it is a "
                    f"published fact, not an estimate. A sign matters: a NEGATIVE value is a "
                    f"charge, a positive one is a credit."
                )

    def per_lot_per_night(self, direction: int) -> float:
        """Account-currency swap for one lot, one night. Negative = charged, positive = credited."""
        pts = self.swap_long_points if direction > 0 else self.swap_short_points
        return pts * self.contract_size * (10 ** -self.digits)

    def nights_charged(self, roll_date) -> int:
        """Nights booked at this rollover — 3 on the triple day, else 1."""
        return 3 if roll_date.weekday() == self.triple_weekday else 1

    def charge(self, direction: int, lots: float, roll_date) -> float:
        """Swap for holding `lots` through the rollover on `roll_date`."""
        return self.per_lot_per_night(direction) * abs(lots) * self.nights_charged(roll_date)


@dataclass(frozen=True)
class AccountProfile:
    """What a specific BROKER ACCOUNT costs to trade — the cost model's real owner.

    **Why the account, not the symbol.** The same XAUUSD.s costs different amounts depending on which
    tier the account is: PU Prime Standard is $0 commission with a marked-up (~$0.33) spread, while
    Prime is $3.50/side/lot against a raw spread near zero. Burying a commission constant in code
    means it silently lies the day the account changes. Naming the profile makes the assumption
    switchable in one line, and every KPI moves with it.

    `commission_per_side_per_lot` has NO default — see `PROFILES` for the verified ones. Stating 0.0
    is allowed and meaningful ("I checked; it is zero"); the sentinel exists so that never having
    said is a loud error rather than a silent zero.

    `latency_ms` is the ONE assumption in the whole cost model (see the module docstring): the time
    an order takes to reach the broker, during which price drifts. Everything else is measured.

    `slippage_ticks` is the deliberate exception, and it is **BAR MODE ONLY**. Tick mode MEASURES
    slippage off the tape (see the module docstring), so a stated estimate there would double-charge
    it and is ignored — every profile below leaves this at 0 for that reason. Bar mode cannot see
    the path inside a bar, so it has no basis to measure anything; stating a per-fill estimate is
    the only way to price it there, and 0 honestly means "not priced" rather than "none occurred".
    It is charged on MARKET exits only: a resting limit fills at your price or better or not at
    all, so entries and take-profit rungs do not slip against you.

    `spread` is the same shape as `slippage_ticks` — **BAR MODE ONLY**, 0.0 meaning "not priced" —
    but for the opposite reason. It is not unknowable; it is MEASURED and stable (gold on both
    brokers below reads a fixed $0.33). Tick mode has the real bid and ask on every tick, so it
    pays the spread by construction and ignores this field; bar mode gets one price per bar and
    has to be told. **It is a fact about the SYMBOL as much as the account**, and the value here is
    XAUUSD's — the same is already true of `swap`, so a profile in this module is read as "this
    account, trading gold". Quote a different instrument and both numbers need re-measuring.

    `bid_ask_fills` is the OTHER half of the spread and the only field here that can change which
    trades exist. Charging the spread as a cost leaves every fill where it was; in reality the
    broker's bars are the BID, and a BUY transacts at the ask. So a long's entry limit and a
    short's stop are both one spread harder to reach than a bid-only bar makes them look. With
    this on, everything that transacts at the ask is tested against `bid + spread` — which is what
    tick mode does, at bar resolution. Default OFF, because it moves the trade list and a run that
    moves the trade list must be asked for. It lives on the profile rather than in the strategy
    config so it travels with the `spread` it is meaningless without.

    ⚠ **`spread` and `bid_ask_fills` are ALTERNATIVES, not layers that stack** — running both bills
    one spread twice. They also do not agree, and the disagreement is informative rather than a
    bug: a flat charge is the market-order intuition, while a strategy whose entries and exits are
    all PRICED ORDERS feels the spread as fill timing instead. Full reasoning, with the long-vs-
    short asymmetry worked through: `strategies/python/mpc_sos_fade/execution.py::_charge_spread`.
    """

    name: str
    commission_per_side_per_lot: float = SENTINEL
    contract_size: float = 100.0        # units (oz) per lot — turns qty into lots
    mintick: float = 0.01
    latency_ms: int = 75                # ~1 median tick spacing; the single assumption
    swap: Optional[SwapModel] = None
    slippage_ticks: int = 0             # BAR MODE ONLY — see below
    spread: float = 0.0                 # BAR MODE ONLY — price units; 0.0 = not priced
    bid_ask_fills: bool = False         # BAR MODE ONLY — moves fills, not just P&L

    def __post_init__(self) -> None:
        if self.commission_per_side_per_lot == SENTINEL:
            raise CostsNotConfigured(
                f"profile {self.name!r}: commission_per_side_per_lot not set. This is a fact about "
                f"your ACCOUNT TYPE, not the symbol — check your broker's account-types page. "
                f"Passing 0.0 is fine IF you have checked it is zero; the point is that it must be "
                f"a decision, not a default."
            )
        if self.commission_per_side_per_lot < 0:
            raise CostsNotConfigured("commission_per_side_per_lot must be >= 0")
        if self.latency_ms < 0:
            raise CostsNotConfigured("latency_ms must be >= 0")
        if self.slippage_ticks < 0:
            raise CostsNotConfigured("slippage_ticks must be >= 0")
        if self.spread < 0 and self.spread != SPREAD_UNMEASURED:
            raise CostsNotConfigured("spread must be >= 0 (it is a width, not a signed cost)")
        if self.bid_ask_fills and self.spread == SPREAD_UNMEASURED:
            raise CostsNotConfigured(
                f"profile {self.name!r}: bid_ask_fills is on but this account's spread has never "
                f"been measured. Modelling fills against an ask nobody has read is not a "
                f"conservative estimate — it decides WHICH TRADES EXIST. Measure it with "
                f"`algos/tools/broker_facts.py --history-days 3` against an account of this type."
            )
        if self.bid_ask_fills and self.spread <= 0:
            raise CostsNotConfigured(
                "bid_ask_fills is on but spread is 0 — the ask would equal the bid, so the "
                "setting would silently do nothing while claiming the fills are modelled."
            )

    def lots(self, qty: float) -> float:
        """Position size in LOTS. Commission and swap are quoted per lot; the strategy sizes in
        units (ounces), so everything must pass through here or the costs are off by 100x."""
        return abs(qty) / self.contract_size

    def commission(self, qty: float) -> float:
        """Commission for ONE side of a `qty`-unit trade."""
        return self.commission_per_side_per_lot * self.lots(qty)

    @property
    def spread_measured(self) -> bool:
        """False when nobody has read this account's spread. See `SPREAD_UNMEASURED`."""
        return self.spread != SPREAD_UNMEASURED

    def spread_or_refuse(self) -> float:
        """The spread, or a refusal — never a stand-in.

        Call this from anything that is about to CHARGE the spread or model fills against it.
        Reading `.spread` directly is fine for reporting ("is this priced?"); it is not fine for
        arithmetic, because the sentinel is a negative number and would quietly pay the trader.
        """
        if not self.spread_measured:
            raise CostsNotConfigured(
                f"profile {self.name!r}: this account's spread has never been measured, so it "
                f"cannot be charged. It is deliberately NOT defaulted to a sibling tier's figure "
                f"— a broker's tiers differ by exactly this number, so borrowing one is the whole "
                f"error. Measure it with `algos/tools/broker_facts.py --history-days 3` against an "
                f"account of this type, or run this backtest without the spread layer."
            )
        return self.spread

    def swap_charge(self, direction: int, qty: float, roll_date) -> float:
        if self.swap is None:
            return 0.0
        return self.swap.charge(direction, self.lots(qty), roll_date)


# Verified account profiles. Sources, checked 2026-07-16:
#   puprime.com/account-types  — Standard $0 | Prime $3.5/side/lot | ECN $1/side/lot | Cent none
#   puprime.com/fee-charges    — the swap formula reproduced in SwapModel
# Evidence the live demo (700107749, PUPrime-Demo) is STANDARD and not a raw-spread tier: its gold
# spread measures a FIXED marked-up value (see the spread block below). That is how a
# commission-free tier is priced; Prime/ECN quote a variable raw spread near zero.
#
# ✅ SWAP RE-MEASURED 2026-08-06 off the LIVE MT5_FFT terminal (`algos/tools/broker_facts.py`,
# read-only): swap_long **-79.60**, swap_short **+30.25**, swap_mode 1 (points), contract 100,
# digits 2, rollover3days 3 → our Monday-based `triple_weekday=2`. Confirmed identical on
# 2026-08-05 and 2026-08-06, two days apart, so it is the broker's standing rate and not a blip.
#
# ⚠ A SWAP IS NOT A CONSTANT, AND THIS IS THE EVIDENCE. The previous values here (-78.29 / +29.49)
# came off the same symbol's Specification window on **2026-07-16** and were 1.7% / 2.6% adrift
# three weeks later. Nothing announced the change and nothing could have caught it — a swap is
# read once, hardcoded, and then quietly describes a rate the broker has moved on from. Swap is
# also the LARGEST re-priceable cost on this strategy (6.41R of the reference run's 12.08R), so
# it is the worst one to leave stale. **Re-run `broker_facts.py` before quoting a cost figure.**
_XAUUSD_SWAP = SwapModel(swap_long_points=-79.60, swap_short_points=30.25,
                         contract_size=100.0, digits=2, triple_weekday=2)

# Vantage demo (account 25815745, VantageMarkets-Demo) — the BACKTEST-ONLY broker, chosen so bar and
# tick data match the VANTAGE_XAUUSD TradingView feed the strategies are designed against. Live
# trading is always PU Prime; this profile exists purely to price backtests on the matching feed.
# Every value below was read straight off the live terminal on 2026-07-22 via the agent's
# /symbol_info endpoint (symbol "XAUUSD", contract 100, digits 2, swap_mode=points): swap_long
# -74.84, swap_short +26.98, triple-swap on Wednesday (MT5 rollover3days=3 → our Monday-based 2).
# Commission is 0.00 because it is a DEMO account — Aaron's standing fact: demos never charge
# commission (a live Vantage RAW ECN would be $3.00/side/lot, but we never trade Vantage live).
_XAUUSD_SWAP_VANTAGE = SwapModel(swap_long_points=-74.84, swap_short_points=26.98,
                                 contract_size=100.0, digits=2, triple_weekday=2)

# Bar-mode spreads, MEASURED off each broker's own cached bid/ask tick stream — never quoted from
# the other one, and that distinction is not academic: the two differ by 50%.
#   PU Prime XAUUSD.s (2026-08-06, **1,893,438 ticks** over 3 whole days off the LIVE MT5_FFT
#     terminal's own tick store) — median **0.320**, p90 0.320, p99 0.370, max 0.390, min 0.270.
#     A FIXED marked-up spread, which is how a zero-commission tier is priced.
#     ⚠ It is flat at $0.32 in EVERY hour of the day except one. The 21:00-22:00 UTC daily break
#     has no ticks at all, and the hour that REOPENS after it (22:00 UTC) is the only wide one —
#     median $0.35, p99 $0.39. So the reopen, not the session, is where gold's spread lives here.
#     ⚠ Supersedes 0.33 (2026-07-14, 688k ticks). Both are real; this one is 2.7x the sample, is
#     three weeks newer, and — the part that matters — covers ALL 23 traded hours rather than a
#     slice, which the previous figure could not claim.
#   Vantage  XAUUSD   (2026-08-02, 1,494,459 ticks over 60 sampled hours of the local tick cache,
#     spanning 2025-08 → 2026-07) — median **0.220**, p90 0.270, p99 0.310, max 0.310.
# Tick mode ignores both: it has the real bid and ask on every tick. These exist so BAR mode, which
# sees one price per bar, can be told what it cannot measure.
#
# ⚠ **THE SPREAD IS PER ACCOUNT TIER, NOT PER BROKER, AND THE 0.32 BELONGS TO ONE TIER.** The live
# demo is a **Standard** account — a commission-free tier is priced by MARKING UP the spread, which
# is why 0.32 reads flat in 22 of 23 hours, and it agrees with PU Prime's published "3.0 pips" for
# Standard at the $0.10/pip gold convention. Prime and ECN are raw-spread tiers and quote something
# far tighter. Giving them Standard's number is not a conservative approximation; it is the single
# number that distinguishes them. They carry `SPREAD_UNMEASURED` until somebody opens an account of
# that type and measures it. See `docs/BROKER_QUESTIONS.md`.
_SPREAD_XAUUSD_PUPRIME_STANDARD = 0.32
_SPREAD_XAUUSD_VANTAGE = 0.22

# ⚠ **SWAP IS ASSUMED TIER-INVARIANT, and that assumption is NAMED rather than measured.** These
# values were read off the Standard demo. Overnight financing is normally a fact about the SYMBOL
# and the same across a broker's tiers — but nobody has confirmed it here, and swap is the largest
# re-priceable cost on this strategy (6.60R vs a ~10R total gap between tiers), so if it does vary
# it outranks everything the tier comparison measured. It is question 3 in
# `docs/BROKER_QUESTIONS.md`. It is deliberately NOT sentinelled: the spread is different by
# CONSTRUCTION (it is how a tier is priced) where this is merely unconfirmed, and refusing every
# raw-tier run over an assumption that is probably true would cost more than it buys.
PROFILES = {
    "puprime_standard": AccountProfile("puprime_standard", 0.00, swap=_XAUUSD_SWAP,
                                       spread=_SPREAD_XAUUSD_PUPRIME_STANDARD),
    "puprime_prime":    AccountProfile("puprime_prime",    3.50, swap=_XAUUSD_SWAP,
                                       spread=SPREAD_UNMEASURED),
    "puprime_ecn":      AccountProfile("puprime_ecn",      1.00, swap=_XAUUSD_SWAP,
                                       spread=SPREAD_UNMEASURED),
    "puprime_cent":     AccountProfile("puprime_cent",     0.00, swap=_XAUUSD_SWAP,
                                       spread=SPREAD_UNMEASURED),
    "vantage_demo":     AccountProfile("vantage_demo",     0.00, swap=_XAUUSD_SWAP_VANTAGE,
                                       spread=_SPREAD_XAUUSD_VANTAGE),
}


@dataclass(frozen=True)
class Level:
    """A price the caller is waiting on, and which way price must move to reach it.

    `falling` is stated, never inferred. Two earlier attempts tried to derive it — first from the
    position's direction (which silently made a long's take-profit unfillable, because every level
    got tested as though it were a stop) and then from a reference price (which broke the moment a
    level was ALREADY through at the reference, i.e. the gap-in-your-favour case). The caller always
    knows: a long's stop falls to it, its target rises to it; a short is the mirror. Asking is one
    parameter; guessing is a class of silent bug.
    """

    price: float
    falling: bool     # True ⇒ price must FALL to reach it (a long's stop, a short's target)


@dataclass(frozen=True)
class Fill:
    """A resolved fill: WHICH level triggered, and the price it ACTUALLY filled at.

    `price` is the whole point of the tick model. A stop at 4000.00 that fills at 3999.78 because
    that was the next price in existence has slipped $0.22 — and reporting `level` as the fill would
    silently erase exactly the cost we built this to measure. In bar mode there is no path to read,
    so `price` is the level itself and `slippage` is 0.0 by construction — an honest statement that
    bar mode cannot see slippage, not a claim that none occurred.
    """

    key: str
    price: float
    slippage: float = 0.0     # adverse distance from the level, >= 0


class PathResolver(Protocol):
    """Decides which of several price levels the bar reached first, and at what price."""

    def first_touch(self, bar: Bar, levels: Dict[str, "Level"], *, buying: bool) -> Optional[Fill]:
        """Return the Fill for the level reached FIRST within `bar`, or None if none was.

        `levels` maps a caller's own label to a `Level` (price + which way price must move to it).

        `buying` says which side of the book this order transacts on, and it is NOT the same thing
        as the position's direction — that conflation is a real bug this signature exists to
        prevent. A long ENTERING buys the ask; the same long EXITING sells the bid. A short entering
        sells the bid; exiting, it buys the ask. Only the caller knows which of the four it is.
        """
        ...


class BarPathResolver:
    """The TradingView guess — kept so `compare_strategy.py` stays a meaningful gate.

    See the module docstring: this is deliberately no smarter than the Pine.
    """

    @staticmethod
    def targets_first(open_: float, high: float, low: float) -> bool:
        """True ⇒ assume price travelled open→high→low→close (upside reached first).

        Byte-for-byte the rule in `mpc_sos_fade.execution._intrabar_targets_first`, and it must STAY
        that way — this is the function `compare_strategy.py`'s exit 0 rests on. Note the tie:
        equal distance resolves to targets-FIRST (`<=`, not `<`). Writing the strict form here
        silently flips every doji-ish bar's outcome and breaks parity, which is exactly what a
        first draft of this file did.
        """
        return abs(open_ - high) <= abs(open_ - low)

    def first_touch(self, bar: Bar, levels: Dict[str, Level], *, buying: bool = False) -> Optional[Fill]:
        # `buying` is accepted for interface parity and deliberately unused: a bar carries no
        # bid/ask, so bar mode cannot know which side of the book transacted. Another thing it
        # cannot see — and must not pretend to.
        up_first = self.targets_first(bar.open, bar.high, bar.low)
        reached = [(k, lv.price) for k, lv in levels.items() if bar.low <= lv.price <= bar.high]
        if not reached:
            return None
        # Among reached levels, the one the assumed path meets first: travelling up first means the
        # highest level is met before lower ones, and vice versa.
        key, price = max(reached, key=lambda kp: kp[1]) if up_first \
            else min(reached, key=lambda kp: kp[1])
        # slippage stays 0.0: a bar cannot show the price BETWEEN its extremes, so bar mode has no
        # basis to claim any. That is a limitation being stated, not an absence being asserted.
        return Fill(key, price, 0.0)


class TickPathResolver:
    """The truth — walks the real bid/ask stream and reports what happened first, AT WHAT PRICE.

    Two things this gets right that a bar cannot:

    1. **The side of the book.** A long exits by SELLING (hits the bid); a short exits by BUYING
       (lifts the ask). Each level is tested against the side that would actually transact. Testing
       the mid quietly refunds a fraction of the spread on every fill, and this strategy's ladder
       fills 4 times per trade.
    2. **The real fill price, so slippage is MEASURED.** A stop is a market order: it fills at the
       next price that exists, not at the level it crossed. The gap between them IS the slippage,
       and it is already in the stream — including the fat tail (measured on XAUUSD.s: median jump
       $0.02, p99 $0.23, worst-in-a-day $13.74). This matters because stops are hit precisely WHEN
       price is moving fast, so the tail is where a stop actually lives. No parameter can express
       that; the ticks just do.

    `latency_ms` shifts the window start: an order is not live until it reaches the broker. It is the
    one assumption here — everything else is read off the tape.

    If the tick window is unavailable this RAISES rather than silently falling back to the guess: a
    backtest that quietly downgrades its own fill model is the dishonesty this module exists to
    prevent. `fallback=True` opts in explicitly and records every bar that used it in
    `fallback_bars`, so a run can report how often it was flying blind.
    """

    def __init__(self, tick_source, symbol: str, *, fallback: bool = False, latency_ms: int = 0):
        self.ticks = tick_source
        self.symbol = symbol
        self.fallback = fallback
        self.latency_ms = latency_ms
        self.fallback_bars: List[int] = []
        self._bar_guess = BarPathResolver()

    def first_touch(self, bar: Bar, levels: Dict[str, Level], *, buying: bool) -> Optional[Fill]:
        stream = self._window(bar)
        if stream is None:
            return self._bar_guess.first_touch(bar, levels, buying=buying)
        for t in stream:
            px = t.ask if buying else t.bid          # the side that actually transacts
            for key, lv in levels.items():
                if not ((px <= lv.price) if lv.falling else (px >= lv.price)):
                    continue
                # Adverse-only: a fill BETTER than the level is a gift, not negative slippage. This
                # is also what makes the gap case right — a level already through on the first tick
                # fills there, at the better price, with zero slippage.
                slip = max(0.0, (px - lv.price) if buying else (lv.price - px))
                return Fill(key, px, slip)
        return None

    def _window(self, bar: Bar) -> Optional[Sequence]:
        from .data.ticks import TickWindowUnavailable

        start = bar.time_ms + self.latency_ms
        try:
            stream = self.ticks.window(self.symbol, start, bar.time_ms + bar.duration_ms)
        except TickWindowUnavailable:
            if not self.fallback:
                raise
            self.fallback_bars.append(bar.time_ms)
            return None
        if not stream:
            # A genuinely tickless window (weekend / the 17:00-NY gold break). There is no path to
            # read, so there is nothing to resolve — the caller's bar shouldn't exist here at all.
            if not self.fallback:
                raise TickWindowUnavailable(
                    f"no ticks for {self.symbol} at {bar.time_ms} — cannot resolve the intrabar "
                    f"path. Pass fallback=True to guess instead (and know that you did).")
            self.fallback_bars.append(bar.time_ms)
            return None
        return stream
