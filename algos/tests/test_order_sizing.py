"""Sizing an order — the regression suite for the 2026-08-07 oversizing incident.

**What happened.** The live bot rested a sell limit for **54.82 lots** on a $2,000 account. It
should have been **0.25**. Two faults multiplied: the strategy's quantity is in INSTRUMENT UNITS
(ounces) and was sent to MT5 as LOTS (100x), and the strategy was sizing off its own compounded
warm-up equity of ~$4,423 rather than the real $2,000 (2.2x). The broker deleted the order at the
fill with `[no money]`, the emulator filled anyway, and the bridge halted.

**What these tests are actually for.** Not "does the divide-by-100 work" — a single conversion is
a single point of failure and a wrong one looks exactly like a right one. They pin the property
that makes the class of bug unshippable: **every order is sized by two independent routes and a
disagreement REFUSES**. So the tests are mostly about instruments this repo has never traded —
EURUSD, USDJPY, an index CFD — because that is where a unit assumption baked in for gold shows up.

`test_the_2026_08_07_order_is_refused_end_to_end` replays the real incident's numbers.

Every test here is pure: no MT5, no network, no terminal. That is the point — the sizing rules
have to be checkable on a laptop, or they only ever get checked by a live account.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent / "shared"
sys.path.insert(0, str(_SHARED))
from order_sizing import (  # noqa: E402
    SymbolSpec, lots_for_risk, lots_from_units, plan_order, round_down_to_step, value_per_lot,
)


# ── real broker specs, measured or from the broker's own contract tables ─────
GOLD = SymbolSpec(symbol="XAUUSD.s", contract_size=100.0, tick_size=0.01, tick_value=1.0,
                  volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=2)
# EURUSD on a USD account: 1 lot = 100,000 EUR, a 0.00001 move is $1.00.
EURUSD = SymbolSpec(symbol="EURUSD", contract_size=100_000.0, tick_size=0.00001, tick_value=1.0,
                    volume_min=0.01, volume_max=200.0, volume_step=0.01, digits=5)
# USDJPY on a USD account: 1 lot = 100,000 USD, a 0.001 move is 100 JPY ≈ $0.67. The quote
# currency is NOT the account currency, which is the case a gold-shaped assumption gets wrong.
USDJPY = SymbolSpec(symbol="USDJPY", contract_size=100_000.0, tick_size=0.001, tick_value=0.67,
                    volume_min=0.01, volume_max=200.0, volume_step=0.01, digits=3)
# A cash index CFD: 1 lot = 1 unit of the index, $1 per point, and the broker allows tenths.
US30 = SymbolSpec(symbol="US30", contract_size=1.0, tick_size=0.1, tick_value=0.1,
                  volume_min=0.1, volume_max=50.0, volume_step=0.1, digits=1)


def _units_for(risk, dist, spec):
    """The quantity a %-risk strategy would compute for this risk over this stop, in the
    instrument's own units — i.e. exactly what `Execution` puts on `_Pending.qty`."""
    return (risk / dist) * (spec.contract_size / (spec.contract_size))  # units == risk/dist


# ─────────────────────────────────────────────────────────────────────────────
# THE INCIDENT
# ─────────────────────────────────────────────────────────────────────────────
def test_the_2026_08_07_order_is_refused_end_to_end():
    """🔴 The real numbers off the real order, and it must not be placeable.

    Ticket 320620565: sell limit at 4286.75448, stop 4294.82248, 54.82 units of quantity, on an
    account holding $2,000 at 10% risk. Two faults at once — so this asserts a refusal without
    caring which of the two checks catches it first.
    """
    plan = plan_order(
        qty_units=54.82, entry=4286.75448, stop=4294.82248, spec=GOLD, point_value=1.0,
        account_equity=2000.0, risk_pct=10.0,
        free_margin=2000.0, margin_for=lambda lots: lots * 100 * 4286.75 / 500)
    assert not plan.ok
    # The compounded warm-up equity is the first thing wrong, so that is what it names.
    assert plan.code == "risk_not_authorised", plan
    assert "442.29" in plan.detail and "200.00" in plan.detail


def test_the_incident_order_is_still_refused_with_the_equity_check_disarmed():
    """The same order with NO balance to check against — the margin backstop must hold alone.

    ⚠ This is the test that keeps the module honest about its own guards. The unit cross-check
    canNOT catch this: both sizing routes are proportional to `qty`, so a caller passing an
    already-wrong quantity scales both and they still agree. Only the MARGIN check has an
    opinion about a position the account cannot carry, whatever produced it — which is why it is
    not optional and why "cannot ask" is a refusal.

    54.82 lots of gold at 4286 is ~$47,000 of margin at 1:500 against $2,000 free.
    """
    plan = plan_order(
        qty_units=54.82 * 100, entry=4286.75448, stop=4294.82248, spec=GOLD, point_value=1.0,
        account_equity=None, risk_pct=None,
        free_margin=2000.0, margin_for=lambda lots: lots * 100 * 4286.75 / 500)
    assert not plan.ok
    assert plan.code == "insufficient_margin", plan
    assert "46,999.93" in plan.detail    # the margin it would have needed, named
    assert "54.82 lots" in plan.detail


def test_the_correctly_sized_gold_order_is_0_25_lots():
    """What the bot SHOULD have placed: $200 of risk over an $8.068 stop on gold."""
    dist = 4294.82248 - 4286.75448
    units = 200.0 / dist                     # what Execution computes: 24.79 ounces
    plan = plan_order(qty_units=units, entry=4286.75448, stop=4294.82248, spec=GOLD,
                      point_value=1.0, account_equity=2000.0, risk_pct=10.0)
    assert plan.ok, getattr(plan, "detail", "")
    assert plan.lots == 0.24                 # 0.2479 rounded DOWN to the 0.01 step
    assert plan.risk_ccy == pytest.approx(193.63, abs=0.01)
    assert plan.risk_ccy < plan.intended_risk_ccy


# ─────────────────────────────────────────────────────────────────────────────
# INSTRUMENT-AGNOSTIC — the whole point of route A
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("spec,entry,stop", [
    (GOLD, 4286.75, 4294.82),
    (EURUSD, 1.09500, 1.09000),
    (USDJPY, 149.500, 150.200),
    (US30, 38500.0, 38300.0),
])
def test_a_correctly_configured_symbol_agrees_with_itself_on_every_instrument(spec, entry, stop):
    """Route A (from the money) and route B (from the units) are algebraically identical when
    the point value matches the broker's tick value. If a future edit breaks that identity for
    ANY instrument shape, this fails before a live account finds out.

    `point_value` is derived here the way a correct config would state it: account currency per
    1.0 of price move per 1 unit of the instrument.
    """
    dist = abs(entry - stop)
    point_value = spec.tick_value / (spec.tick_size * spec.contract_size)
    units = (500.0 / dist) / point_value            # a $500 risk, in the instrument's units
    plan = plan_order(qty_units=units, entry=entry, stop=stop, spec=spec,
                      point_value=point_value)
    assert plan.ok, getattr(plan, "detail", "")
    assert plan.risk_ccy == pytest.approx(500.0, rel=0.05)


def test_a_jpy_quoted_pair_is_refused_when_the_config_assumes_dollars():
    """🔴 The gold assumption, carried onto a yen pair.

    `point_value = 1.0` is right for gold on a USD account and wrong for USDJPY by a factor of
    ~150, because a 1.0 move there is 1 JPY, not $1. Nothing in the strategy could notice. The
    cross-check does — and refuses rather than trading 150x.
    """
    dist = 0.700
    units = 500.0 / dist
    plan = plan_order(qty_units=units, entry=149.500, stop=150.200, spec=USDJPY, point_value=1.0)
    assert not plan.ok
    assert plan.code == "unit_mismatch"
    assert "USDJPY" in plan.detail


def test_an_index_with_a_contract_size_of_one_still_sizes():
    """The degenerate case in the other direction: contract_size 1.0, so units == lots. A
    conversion written as "always divide by 100" would be silently wrong here and this is the
    only instrument shape that would catch it."""
    plan = plan_order(qty_units=2.5, entry=38500.0, stop=38300.0, spec=US30, point_value=1.0)
    assert plan.ok, getattr(plan, "detail", "")
    assert plan.lots == 2.5
    assert plan.risk_ccy == pytest.approx(500.0, abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# AARON'S QUESTION: 0.18 lots and an account that cannot take it
# ─────────────────────────────────────────────────────────────────────────────
def test_a_size_below_the_broker_minimum_is_refused_and_never_rounded_up():
    """🔴 The account is too small for this setup's stop distance.

    The tempting answer is "trade the minimum". It is wrong: at a 0.01 minimum on gold, an order
    the strategy sized at 0.004 lots becomes 2.5x the risk it asked for — on an account already
    too small to take the trade it wanted. No trade is the honest answer, and the refusal says
    what the minimum WOULD have risked so the reader can see the gap.
    """
    dist = 50.0                     # a wide stop; $20 of risk buys 0.4 ounces
    plan = plan_order(qty_units=20.0 / dist, entry=4300.0, stop=4350.0, spec=GOLD,
                      point_value=1.0)
    assert not plan.ok
    assert plan.code == "below_broker_minimum"
    assert "NOT rounding up" in plan.detail


def test_a_size_above_the_broker_maximum_is_refused_and_never_clamped():
    """Clamping down risks LESS, which sounds safe and is not.

    The emulator would be holding the size it computed while the broker carried the clamp, and
    the two would drift apart silently — the same divergence that halts the bot, arriving
    quietly. `normalize_volume` clamps (it is a wire-level helper); the PLAN must not.
    """
    # 20,000 oz = 200 lots, against XAUUSD.s's 100-lot ceiling.
    plan = plan_order(qty_units=20_000.0, entry=4300.0, stop=4301.0, spec=GOLD, point_value=1.0)
    assert not plan.ok
    assert plan.code == "above_broker_maximum", plan
    assert "NOT clamping" in plan.detail


def test_an_unaffordable_order_is_refused_and_never_shrunk_to_fit():
    """🔴 The specific failure of 2026-08-07, at the one moment it could have been caught.

    A smaller position is not the trade the strategy is holding. Shrinking would keep the
    broker happy and put the emulator and the account on different books — which is how a
    'safe' fallback becomes the next incident.
    """
    dist = 8.0
    units = 400.0 / dist                          # $400 risk, ~0.5 lots of gold
    plan = plan_order(
        qty_units=units, entry=4300.0, stop=4308.0, spec=GOLD, point_value=1.0,
        free_margin=100.0,                        # nowhere near enough
        margin_for=lambda lots: lots * 100 * 4300 / 500)
    assert not plan.ok
    assert plan.code == "insufficient_margin"
    assert "NOT shrinking to fit" in plan.detail


def test_margin_the_terminal_will_not_compute_is_a_refusal_not_a_pass():
    """⚠ 'Cannot ask' must never equal 'affordable'.

    The repo's own `mt5_link` rule, applied to money. A `None` margin falling through to a
    placed order is exactly how this incident happens again with the check installed.
    """
    plan = plan_order(qty_units=25.0, entry=4300.0, stop=4308.0, spec=GOLD, point_value=1.0,
                      free_margin=50_000.0, margin_for=lambda lots: None)
    assert not plan.ok
    assert plan.code == "margin_unknown"


def test_an_affordable_order_inside_the_margin_cap_is_placed():
    """The happy path, so the guards above are provably not refusing everything."""
    plan = plan_order(
        qty_units=200.0 / 8.0, entry=4300.0, stop=4308.0, spec=GOLD, point_value=1.0,
        account_equity=2000.0, risk_pct=10.0,
        free_margin=50_000.0, margin_for=lambda lots: lots * 100 * 4300 / 500)
    assert plan.ok, getattr(plan, "detail", "")
    assert plan.lots == 0.25
    assert plan.margin_ccy == pytest.approx(0.25 * 100 * 4300 / 500)


def test_the_margin_cap_is_a_fraction_of_free_margin_not_all_of_it():
    """At 100% one setup may commit the entire account and the position has no room to breathe
    before the broker starts closing things. The default is 50%."""
    margin_fn = lambda lots: lots * 100 * 4300 / 500          # noqa: E731
    kw = dict(qty_units=200.0 / 8.0, entry=4300.0, stop=4308.0, spec=GOLD, point_value=1.0,
              margin_for=margin_fn)
    need = margin_fn(0.25)
    assert plan_order(free_margin=need * 1.9, **kw).ok is False       # 50% of 1.9x < need
    assert plan_order(free_margin=need * 2.1, **kw).ok is True
    assert plan_order(free_margin=need * 1.1, margin_safety_pct=100.0, **kw).ok is True


# ─────────────────────────────────────────────────────────────────────────────
# THE EQUITY GUARD (fault 2)
# ─────────────────────────────────────────────────────────────────────────────
def test_sizing_off_an_equity_the_account_does_not_have_is_refused():
    """🔴 The compounded warm-up balance, isolated.

    The emulator replays 5,000 bars and books their imaginary P&L onto its own balance. On the
    day of the incident that put it at ~$4,423 against a real $2,000, and it sized every order
    off the difference. Nothing anywhere compared the two.
    """
    dist = 8.068
    units = (4423.0 * 0.10) / dist          # what the emulator wanted
    plan = plan_order(qty_units=units, entry=4286.75, stop=4294.82, spec=GOLD, point_value=1.0,
                      account_equity=2000.0, risk_pct=10.0)
    assert not plan.ok
    assert plan.code == "risk_not_authorised"
    assert "compounded" in plan.detail


def test_the_equity_check_is_skipped_when_the_balance_cannot_be_read():
    """A balance we could not read must not refuse every order forever — the check simply does
    not run. That is the deliberate asymmetry: an unknown MARGIN refuses (the broker will
    enforce it either way), an unknown BALANCE only removes a cross-check."""
    dist = 8.0
    plan = plan_order(qty_units=200.0 / dist, entry=4300.0, stop=4308.0, spec=GOLD,
                      point_value=1.0, account_equity=None, risk_pct=10.0)
    assert plan.ok, getattr(plan, "detail", "")


# ─────────────────────────────────────────────────────────────────────────────
# DEGENERATE INPUTS — each one used to be a route to an unbounded position
# ─────────────────────────────────────────────────────────────────────────────
def test_a_stop_at_the_entry_is_refused_rather_than_dividing_by_zero():
    plan = plan_order(qty_units=10.0, entry=4300.0, stop=4300.0, spec=GOLD)
    assert not plan.ok and plan.code == "zero_stop_distance"


@pytest.mark.parametrize("bad", [
    SymbolSpec("X", contract_size=100.0, tick_size=0.0, tick_value=1.0,
               volume_min=0.01, volume_max=100.0, volume_step=0.01),
    SymbolSpec("X", contract_size=100.0, tick_size=0.01, tick_value=0.0,
               volume_min=0.01, volume_max=100.0, volume_step=0.01),
    SymbolSpec("X", contract_size=0.0, tick_size=0.01, tick_value=1.0,
               volume_min=0.01, volume_max=100.0, volume_step=0.01),
])
def test_a_symbol_the_terminal_could_not_describe_is_refused(bad):
    """A wrong broker suffix, a symbol not in Market Watch, or a terminal still loading all
    return zeros here. There is no safe stand-in for 'the broker did not say what this is
    worth' — a gold-shaped default would size a real position off a guess."""
    plan = plan_order(qty_units=10.0, entry=4300.0, stop=4308.0, spec=bad)
    assert not plan.ok and plan.code == "symbol_unpriceable"


def test_a_non_positive_quantity_is_refused():
    plan = plan_order(qty_units=0.0, entry=4300.0, stop=4308.0, spec=GOLD)
    assert not plan.ok and plan.code == "non_positive_qty"


# ─────────────────────────────────────────────────────────────────────────────
# THE PIECES
# ─────────────────────────────────────────────────────────────────────────────
def test_value_per_lot_is_the_broker_s_own_arithmetic():
    assert value_per_lot(8.068, GOLD) == pytest.approx(806.8)
    assert value_per_lot(0.0050, EURUSD) == pytest.approx(500.0)
    assert value_per_lot(0.700, USDJPY) == pytest.approx(469.0)


def test_rounding_is_always_down():
    assert round_down_to_step(0.2479, GOLD) == 0.24
    assert round_down_to_step(0.2999, GOLD) == 0.29
    assert round_down_to_step(0.009, GOLD) == 0.0
    assert round_down_to_step(2.57, US30) == 2.5


def test_the_two_routes_are_the_same_number_on_a_correct_spec():
    dist = 8.068
    units = 200.0 / dist
    assert lots_for_risk(units * dist, dist, GOLD) == pytest.approx(lots_from_units(units, GOLD))
