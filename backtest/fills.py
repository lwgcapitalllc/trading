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
  as a fudge factor. Gold measures ~$0.33 and is stable (2026-07-14: median 0.330, p99 0.380).
* **Commission** — a per-side fact about the account, not an estimate. There is no default: see
  `CostModel`.
* **Slippage** — charged on STOP exits ONLY. A resting limit (this strategy's entries and TPs) does
  not slip against you: it fills at your price or better, or it doesn't fill. A stop is a market
  order into a moving book, and gold stops slip hardest exactly when they trigger. Charging
  slippage on limits is as wrong as charging none on stops.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol, Sequence

__all__ = ["CostModel", "CostsNotConfigured", "PathResolver", "BarPathResolver",
           "TickPathResolver", "Bar", "SENTINEL"]

# An un-set cost. Not 0.0: zero is a legitimate value (some gold CFD accounts genuinely are
# spread-only), so zero must be a thing you can deliberately SAY, distinct from never having said
# anything. A backtest that silently runs at zero cost is how a losing strategy passes review.
SENTINEL = -1.0


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
class CostModel:
    """Per-trade transaction costs.

    `commission_per_side` and `slippage_ticks` have NO defaults — they are facts about a specific
    broker account and inventing them produces results that look precise and are fiction. Both must
    be stated, and stating 0.0 is allowed and meaningful ("I checked; it is zero"). The sentinel
    exists so that "I never said" is a loud error instead of a silent zero.

    `slippage_ticks` is charged on stop exits only (see the module docstring).
    """

    commission_per_side: float = SENTINEL
    slippage_ticks: float = SENTINEL
    mintick: float = 0.01
    point_value: float = 1.0

    def __post_init__(self) -> None:
        missing = [n for n, v in (("commission_per_side", self.commission_per_side),
                                  ("slippage_ticks", self.slippage_ticks)) if v == SENTINEL]
        if missing:
            raise CostsNotConfigured(
                f"cost input(s) not set: {', '.join(missing)}. These are facts about your broker "
                f"account, not estimates — look them up (MT5: right-click the symbol -> "
                f"Specification) and pass them explicitly. Passing 0.0 is fine IF you have "
                f"checked it is zero; the point is that it must be a decision, not a default."
            )
        for name, v in (("commission_per_side", self.commission_per_side),
                        ("slippage_ticks", self.slippage_ticks)):
            if v < 0:
                raise CostsNotConfigured(f"{name} must be >= 0, got {v}")

    @property
    def slippage_price(self) -> float:
        """Slippage as a price distance."""
        return self.slippage_ticks * self.mintick

    def commission_for(self, qty: float) -> float:
        """Commission in account currency for `qty` units, ONE side."""
        return self.commission_per_side * abs(qty)

    def slip_stop(self, level: float, direction: int) -> float:
        """A stop's realised price: always WORSE than the trigger. A long's stop sells into a
        falling book (fills lower); a short's stop buys into a rising one (fills higher)."""
        return level - self.slippage_price * direction


class PathResolver(Protocol):
    """Decides which of several price levels the bar reached first."""

    def first_touch(self, bar: Bar, levels: Dict[str, float], direction: int) -> Optional[str]:
        """Return the key of the level reached FIRST within `bar`, or None if none was.

        `levels` maps a caller's own label to a price. `direction` is the position's side (+1 long,
        -1 short) and tells the resolver which way each level is approached. Ties resolve to the
        caller's insertion order, which is the strategy's own precedence.
        """
        ...


def _touched(bar: Bar, price: float, direction: int, is_target: bool) -> bool:
    """Did the bar's range reach `price` at all (order aside)?"""
    if (direction > 0) == is_target:      # long target / short stop -> reached from below
        return bar.high >= price
    return bar.low <= price


class BarPathResolver:
    """The TradingView guess — kept so `compare_strategy.py` stays a meaningful gate.

    See the module docstring: this is deliberately no smarter than the Pine.
    """

    @staticmethod
    def targets_first(open_: float, high: float, low: float) -> bool:
        """True ⇒ assume price travelled open→high→low→close (upside reached first).

        Byte-for-byte the rule in `mpc_aplus.execution._intrabar_targets_first`, and it must STAY
        that way — this is the function `compare_strategy.py`'s exit 0 rests on. Note the tie:
        equal distance resolves to targets-FIRST (`<=`, not `<`). Writing the strict form here
        silently flips every doji-ish bar's outcome and breaks parity, which is exactly what a
        first draft of this file did.
        """
        return abs(open_ - high) <= abs(open_ - low)

    def first_touch(self, bar: Bar, levels: Dict[str, float], direction: int) -> Optional[str]:
        up_first = self.targets_first(bar.open, bar.high, bar.low)
        reached = [(k, p) for k, p in levels.items()
                   if bar.low <= p <= bar.high or _spans(bar, p)]
        if not reached:
            return None
        # Among reached levels, the one the assumed path meets first: travelling up first means the
        # highest level is met before lower ones, and vice versa.
        return max(reached, key=lambda kp: kp[1])[0] if up_first \
            else min(reached, key=lambda kp: kp[1])[0]


def _spans(bar: Bar, price: float) -> bool:
    """A gapped level: the bar opened already past it."""
    return bar.open >= price >= bar.low or bar.high >= price >= bar.open


class TickPathResolver:
    """The truth — walks the real bid/ask stream for the bar and reports what happened first.

    A long exits by SELLING (hits the bid) and a short exits by BUYING (lifts the ask), so each
    level is tested against the side of the book that would actually transact. Testing against the
    mid or the wrong side quietly gives back a fraction of the spread on every fill, which on this
    strategy's 3-exit ladder is not a rounding error.

    If the tick window is unavailable this raises rather than silently falling back to the guess:
    a backtest that quietly downgrades its own fill model is exactly the kind of dishonesty this
    module exists to prevent. `fallback` opts into the guess EXPLICITLY, and records it in
    `fallback_bars` so a run can report how often it had to.
    """

    def __init__(self, tick_source, symbol: str, *, fallback: bool = False):
        self.ticks = tick_source
        self.symbol = symbol
        self.fallback = fallback
        self.fallback_bars: List[int] = []
        self._bar_guess = BarPathResolver()

    def first_touch(self, bar: Bar, levels: Dict[str, float], direction: int) -> Optional[str]:
        stream = self._window(bar)
        if stream is None:
            return self._bar_guess.first_touch(bar, levels, direction)
        for t in stream:
            for key, price in levels.items():
                if self._hit(t, price, direction):
                    return key
        return None

    def _hit(self, tick, price: float, direction: int) -> bool:
        """Would an exit at `price` transact on this tick? A long sells the bid; a short buys the
        ask. The comparison is one-sided per direction because a level is only ever approached
        from one side by the position holding it."""
        return tick.bid <= price if direction > 0 else tick.ask >= price

    def _window(self, bar: Bar) -> Optional[Sequence]:
        from .data.ticks import TickWindowUnavailable

        try:
            stream = self.ticks.window(self.symbol, bar.time_ms, bar.time_ms + bar.duration_ms)
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
