"""order_sizing.py — turn a strategy's intent into a broker order size, or REFUSE.

**Why this file exists.** On 2026-08-07 the live bot rested a sell limit for **54.82 lots** on a
$2,000 account — 5,482 ounces of gold, ~$23.5M notional. It sat there for eight hours looking
perfectly healthy, price reached it, and the broker deleted it with `[no money]`. The emulator
filled itself on the same bar, the two ledgers parted, and the bridge halted. Nothing in the
system had objected at any point before the fill.

Two faults stacked, and BOTH were invisible:

1. **Units.** `Execution` sizes in INSTRUMENT UNITS (`qty = equity·risk%/stop_distance`, so
   ounces for gold, base-currency units for FX). `bridge._sync_side` handed that number to MT5
   as LOTS. Gold's contract is 100 oz, so every order was **100x** the intended size. The only
   place `trade_contract_size` appeared in the whole live path was reading a fill back.
2. **Equity.** The strategy was built with the real balance and then replayed 5,000 warm-up
   bars, whose simulated profits compounded the emulator's balance to ~$4,423. It sized live
   orders off that. Another **2.2x**.

Together: 0.25 lots intended, 54.82 lots sent. **221x.**

**The lesson this module is built around is not "divide by contract size".** A single conversion
is a single point of failure and a wrong one looks exactly like a right one, so the defence is
LAYERED — and it is worth being exact about which layer stops what, because a guard credited with
catching more than it does is how the next one of these ships.

  * **The conversion itself.** Lots come from the money: how many lots lose `intended_risk` in the
    ACCOUNT's currency if price travels `stop_distance`? That is
    `(stop_distance / tick_size) x tick_value` per lot, every number read off the broker. This is
    the fix for fault 1, and its real protection is that `plan_order` is the ONLY place in the
    live path a lot count is produced — there is now one seam to review instead of none.

  * **A cross-check against the units route** (`qty / contract_size`). ⚠ **This does NOT catch a
    caller passing an already-wrong quantity** — both routes are proportional to `qty`, so they
    scale together. What it catches is the SPEC disagreeing with the STRATEGY: a wrong
    `point_value`, a wrong contract size, or a quote currency that is not the account's. That is
    the shape the incident would take on the next instrument (see the USDJPY test), where a
    `point_value = 1.0` inherited from gold is wrong by a factor of ~150.

  * **The authorised-risk check.** `intended_risk` must equal `account_equity x risk_pct / 100`.
    This is the guard on fault 2 — it fires the moment a strategy sizes off a stale or compounded
    equity, which is the half nothing else here can see.

  * **The margin check, which is the backstop that has no opinion about causes.** Whatever went
    wrong upstream, an order the account cannot carry is refused before it is sent. On
    2026-08-07 this alone would have stopped the order eight hours before the broker did.

**Everything here is pure.** No MT5 import, no I/O, no logging. It takes a `SymbolSpec` (facts
read off the terminal by `mt5_ops.symbol_spec`) and returns either a `SizedOrder` or a
`SizingRefusal`. That is what makes it testable across instruments the repo has never traded —
gold, EURUSD, USDJPY, an index CFD — on a laptop with no broker.

**Refusing is a real answer and is never a rounding-down.** Three policies, all deliberate:

  * **Below the broker minimum → no trade.** Never round UP: that is a bigger bet than the
    strategy asked for, on an account already too small to take the one it wanted.
  * **Above the broker maximum → no trade.** Never CLAMP: a clamped order risks less, which
    sounds safe, but it is not the trade the emulator is holding — and an emulator and a broker
    carrying different sizes is the same class of divergence that halts the bot, arriving
    quietly instead of loudly.
  * **Not affordable on margin → no trade.** Never shrink to fit. Same reason.

⚠ **"Cannot ask" is never "affordable".** A margin figure the terminal declines to compute is a
refusal, not a pass — the same three-state rule `mt5_link` follows. A `None` margin that fell
through to "fine" is how this incident would have happened again with the check installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Union

__all__ = [
    "SymbolSpec", "SizedOrder", "SizingRefusal", "OrderPlan",
    "value_per_lot", "lots_for_risk", "lots_from_units", "round_down_to_step",
    "plan_order", "DEFAULT_MARGIN_SAFETY_PCT", "UNIT_MISMATCH_TOLERANCE",
]

# How much of the account's FREE margin one order may consume. 50% leaves room for the
# position to move against us before the broker starts closing things, and for a second bot
# on the same account. It is a config field (`margin_safety_pct`), not a constant, because the
# right number depends on how many bots share the login — but it has to have a default, and a
# default that lets one order eat the whole account is not a safety rail.
DEFAULT_MARGIN_SAFETY_PCT = 50.0

# Two independently-derived lot counts may differ by this fraction before the order is refused.
# It is generous on purpose: it exists to catch factor-of-100 unit errors, not to police the
# last decimal of a tick value. Anything inside it is arithmetic noise; anything outside it is
# somebody's units being wrong.
UNIT_MISMATCH_TOLERANCE = 0.02


@dataclass(frozen=True)
class SymbolSpec:
    """The broker's facts about ONE symbol. Every field is read off the terminal — nothing here
    may be assumed, defaulted per symbol, or carried over from another instrument.

    `tick_value` is the one that makes this instrument-agnostic: it is the profit, **in the
    ACCOUNT's currency**, of a `tick_size` price move on one lot. That is what turns a JPY-quoted
    pair, a gold CFD and an index into the same arithmetic.
    """
    symbol: str
    contract_size: float   # instrument units in ONE lot (gold 100 oz, EURUSD 100,000 EUR)
    tick_size: float       # the price increment `tick_value` is quoted against
    tick_value: float      # ACCOUNT-currency profit per lot per `tick_size` of favourable move
    volume_min: float
    volume_max: float
    volume_step: float
    digits: int = 2

    def is_priceable(self) -> bool:
        """Can this spec convert a price distance into money at all?

        A zero or missing `tick_size` / `tick_value` is what an unselected symbol, a wrong
        suffix or a terminal that has not finished loading returns. Sizing through it produces
        a division by zero or an infinite position, so it is refused rather than defaulted —
        there is no safe stand-in for "the broker did not tell us what this is worth".
        """
        return (self.tick_size > 0 and self.tick_value > 0
                and self.contract_size > 0 and self.volume_step > 0)


@dataclass(frozen=True)
class SizedOrder:
    """An order that passed every check. `risk_ccy` is what it ACTUALLY risks after rounding —
    always ≤ `intended_risk_ccy`, because rounding is always down."""
    lots: float
    risk_ccy: float
    intended_risk_ccy: float
    margin_ccy: Optional[float] = None
    lots_by_risk: float = 0.0      # route A, before rounding — kept for the ledger
    lots_by_units: float = 0.0     # route B, before rounding — kept for the ledger

    @property
    def ok(self) -> bool:
        return True


@dataclass(frozen=True)
class SizingRefusal:
    """No order. `code` is stable and countable; `detail` is written for a human at 3am and
    always names the numbers, because a refusal nobody can act on is a silent failure with
    extra steps."""
    code: str
    detail: str

    @property
    def ok(self) -> bool:
        return False


OrderPlan = Union[SizedOrder, SizingRefusal]


# ── the arithmetic, each piece separately testable ────────────────────────────
def value_per_lot(stop_distance: float, spec: SymbolSpec) -> float:
    """Account-currency loss on ONE lot when price travels `stop_distance` against the position.

    This is the whole instrument-agnostic core. It never touches contract size, because
    `tick_value` already contains it — and it never touches the quote currency, because
    `tick_value` is already in the account's.
    """
    return (stop_distance / spec.tick_size) * spec.tick_value


def lots_for_risk(risk_ccy: float, stop_distance: float, spec: SymbolSpec) -> float:
    """Route A — lots from the money. Unrounded."""
    vpl = value_per_lot(stop_distance, spec)
    return risk_ccy / vpl


def lots_from_units(qty_units: float, spec: SymbolSpec) -> float:
    """Route B — lots from the instrument units the strategy sized in. Unrounded.

    This is the conversion whose ABSENCE caused the 2026-08-07 incident. It is kept as the
    cross-check rather than as the answer, because it depends on the strategy and the broker
    agreeing about what a "unit" is, and route A does not.
    """
    return qty_units / spec.contract_size


def round_down_to_step(lots: float, spec: SymbolSpec) -> float:
    """Round DOWN to the broker's volume step. Never to nearest, never up.

    Rounding up crosses the risk the strategy sized for. On a small account that is not a
    rounding error — at a `volume_min` of 0.01 lots on gold, rounding 0.004 up is 2.5x the
    intended position.
    """
    if spec.volume_step <= 0:
        return lots
    steps = int(lots / spec.volume_step + 1e-9)
    return round(steps * spec.volume_step, 8)


def plan_order(
    *,
    qty_units: float,
    entry: float,
    stop: float,
    spec: SymbolSpec,
    point_value: float = 1.0,
    account_equity: Optional[float] = None,
    risk_pct: Optional[float] = None,
    free_margin: Optional[float] = None,
    margin_for: Optional[Callable[[float], Optional[float]]] = None,
    margin_safety_pct: float = DEFAULT_MARGIN_SAFETY_PCT,
    unit_tolerance: float = UNIT_MISMATCH_TOLERANCE,
) -> OrderPlan:
    """Size one order, or refuse it with a reason.

    `qty_units` / `entry` / `stop` / `point_value` come from the strategy — they are its intent.
    `spec` / `free_margin` / `margin_for` come from the broker — they are reality. Every check
    below is one of those two disagreeing with the other, or with itself.

    `margin_for(lots)` returns the margin the broker requires for that size, or `None` if it
    could not be computed. Pass it as a callable so this module never imports MT5.
    """
    # ── the strategy's own numbers have to make sense first ──
    dist = abs(float(entry) - float(stop))
    if dist <= 0:
        return SizingRefusal(
            "zero_stop_distance",
            f"stop {stop} is at the entry {entry}; qty = risk / distance is undefined and any "
            f"size would be arbitrary.")
    if qty_units <= 0:
        return SizingRefusal("non_positive_qty", f"the strategy asked for {qty_units} units.")

    if not spec.is_priceable():
        return SizingRefusal(
            "symbol_unpriceable",
            f"{spec.symbol}: tick_size={spec.tick_size} tick_value={spec.tick_value} "
            f"contract_size={spec.contract_size} volume_step={spec.volume_step}. The terminal "
            f"has not said what a price move is worth, so no size can be derived. Check the "
            f"symbol name and that it is visible in Market Watch.")

    intended_risk = qty_units * dist * float(point_value)

    # ── check 3: does the intent match the risk the account actually authorised? ──
    # This is the guard on the compounded-warm-up-equity fault. It runs first because when it
    # fires, every number below it is derived from a balance that does not exist.
    if account_equity and risk_pct:
        authorised = float(account_equity) * float(risk_pct) / 100.0
        if authorised > 0 and _disagree(intended_risk, authorised, unit_tolerance):
            return SizingRefusal(
                "risk_not_authorised",
                f"the order would risk {intended_risk:,.2f} but {risk_pct}% of the account's "
                f"{account_equity:,.2f} is {authorised:,.2f}. The strategy is sizing off a "
                f"balance the account does not have — most likely warm-up equity that "
                f"compounded away from the broker's.")

    # ── checks 1 and 2: two independent routes to the same lot count ──
    lots_a = lots_for_risk(intended_risk, dist, spec)      # from the money (authoritative)
    lots_b = lots_from_units(qty_units, spec)              # from the units (cross-check)
    if _disagree(lots_a, lots_b, unit_tolerance):
        return SizingRefusal(
            "unit_mismatch",
            f"sizing disagrees with itself on {spec.symbol}: {lots_a:.6f} lots by risk "
            f"({intended_risk:,.2f} over a {dist} stop at {spec.tick_value}/{spec.tick_size} "
            f"per lot) vs {lots_b:.6f} lots by units ({qty_units} / contract {spec.contract_size}). "
            f"A unit, a contract size, a point value or a quote currency is wrong. Refusing "
            f"rather than picking one — the ratio here is {max(lots_a, lots_b) / max(min(lots_a, lots_b), 1e-12):,.1f}x.")

    lots = round_down_to_step(lots_a, spec)

    # ── the broker's own volume band ──
    if lots < spec.volume_min:
        return SizingRefusal(
            "below_broker_minimum",
            f"{lots_a:.6f} lots rounds to {lots}, under {spec.symbol}'s minimum "
            f"{spec.volume_min}. NOT rounding up — the minimum would risk "
            f"{value_per_lot(dist, spec) * spec.volume_min:,.2f} against an intended "
            f"{intended_risk:,.2f}. The account is too small for this setup's stop distance.")
    if lots > spec.volume_max:
        return SizingRefusal(
            "above_broker_maximum",
            f"{lots} lots exceeds {spec.symbol}'s maximum {spec.volume_max}. NOT clamping — a "
            f"clamped order is a different position from the one the strategy is holding, and "
            f"the two would diverge silently.")

    # ── can the account actually carry it? ──
    margin = None
    if margin_for is not None:
        margin = margin_for(lots)
        if margin is None:
            return SizingRefusal(
                "margin_unknown",
                f"the terminal would not compute the margin for {lots} lots of {spec.symbol}. "
                f"'Cannot ask' is not 'affordable' — refusing rather than finding out at the "
                f"fill, which is exactly how the 2026-08-07 order died.")
        if free_margin is None:
            return SizingRefusal(
                "free_margin_unknown",
                f"margin for {lots} lots is {margin:,.2f} but the account's free margin could "
                f"not be read, so there is nothing to compare it against.")
        ceiling = float(free_margin) * float(margin_safety_pct) / 100.0
        if margin > ceiling:
            return SizingRefusal(
                "insufficient_margin",
                f"{lots} lots of {spec.symbol} needs {margin:,.2f} margin; the cap is "
                f"{ceiling:,.2f} ({margin_safety_pct:g}% of {float(free_margin):,.2f} free). "
                f"NOT shrinking to fit — a smaller position is not the trade the strategy is "
                f"holding.")

    risk = value_per_lot(dist, spec) * lots
    # Rounding is always down, so this cannot exceed the intent. If it ever does, the step
    # arithmetic is wrong and the order must not go out on the strength of a comment.
    if risk > intended_risk * (1.0 + unit_tolerance):
        return SizingRefusal(
            "oversized_after_rounding",
            f"{lots} lots risks {risk:,.2f} against an intended {intended_risk:,.2f}. Rounding "
            f"is supposed to be downward only; this is a bug in the step arithmetic.")

    return SizedOrder(lots=lots, risk_ccy=risk, intended_risk_ccy=intended_risk,
                      margin_ccy=margin, lots_by_risk=lots_a, lots_by_units=lots_b)


def _disagree(a: float, b: float, tol: float) -> bool:
    """Relative comparison against the LARGER of the two.

    Against the smaller, a 100x error and a 0.01x error score differently for no reason; against
    the larger, both read as ~1.0 and either trips the same tolerance.
    """
    big = max(abs(a), abs(b))
    if big <= 0:
        return False
    return abs(a - b) / big > tol
