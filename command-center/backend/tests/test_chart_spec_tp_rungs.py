"""
Tests for the two things a chart has to get right about a trade's exit LADDER: what each rung is
called, and whether a rung is a target at all. Pure over stored equity-curve points — no DB, no
network, no run.

**The bug that bought these.** Run 687c8df2a523, the re-entry short of 2026-05-21: the chart drew
TWO chips reading `TP1`, at 4,507.04 and at 4,491.99, on one trade. Both were drawn from the same
record and neither was a drawing glitch.

  - The upper one came from a leg whose exit-order id was `S-TP1`. The trade's TRAIL closed that
    rung at 4,507.04; its first target sat 15 points further away at 4,491.99 and price never
    reached it. Naming a leg after the order that carried it claims a target fill that never
    happened.
  - The lower one was the real target, drawn faintly and correctly.

The second finding, from the same picture: a `TP2` chip at 4,505.43 for a rung that places no
order. At the shipped settings the second rung banks 0% of the position on every trade of every
run — nothing is ever sold there, and a touch only steps the stop. Across all 205 trades of that
run there is not one second-rung fill; every trade closed on the runner, the first rung, or time.

Both are the same defect twice: a LABEL is a claim about behaviour somewhere else, and neither
claim was ever checked against the trade's own record.
"""

from services.chart_spec import _build_trades

_CANDLES = [{"time": 1_000, "open": 4500.0, "high": 4600.0, "low": 4400.0, "close": 4500.0}]

# The real trade, to the cent. A short: it profits DOWNWARD, so "further" is a LOWER price.
_ENTRY = 4537.46496
_STOP = 4573.83792
_TRAIL_EXIT = 4507.04  # where the trail actually took both rungs off
_RUNG_1 = 4491.99876  # first target — 1.25x risk below the entry. Never reached.
_RUNG_2 = 4505.43504  # second rung — a leftover fib price. No order sits here.


def _short(*, legs, targets=None):
    p = {
        "direction": "Short",
        "entry_ms": 1_000,
        "exit_ms": 2_000,
        "entry_price": _ENTRY,
        "exit_price": _TRAIL_EXIT,
        "stop_price": _STOP,
        "profit": 1000.0,
        "equity": 1000.0,
        "legs": legs,
    }
    if targets is not None:
        p["tp_targets"] = targets
    return p


def _labels(point):
    return [lg["label"] for lg in _build_trades([point], _CANDLES)[0]["profitLegs"]]


# ── what a rung is CALLED ─────────────────────────────────────────────────────


def test_a_rung_the_trail_closed_short_of_its_target_is_not_named_after_that_target():
    """The reported bug, at its smallest: two `TP1` chips at two prices on one trade.

    The leg is named `S-TP1` and came off at 4,507.04. Its own target is 4,491.99 — on a short
    that is 15 points further down, so price never got there. It is an exit, not a target fill.
    """
    point = _short(
        legs=[{"reason": "S-TP1", "price": _TRAIL_EXIT}],
        targets=[{"price": _RUNG_1, "banks": True}, {"price": _RUNG_2, "banks": False}],
    )
    assert _labels(point) == ["Exit"]


def test_a_rung_that_reached_its_target_keeps_its_number():
    """The check must not swallow real target fills — that would trade one lie for another."""
    point = _short(
        legs=[{"reason": "S-TP1", "price": _RUNG_1}],
        targets=[{"price": _RUNG_1, "banks": True}, {"price": _RUNG_2, "banks": False}],
    )
    assert _labels(point) == ["TP1"]


def test_a_limit_that_GAPPED_past_its_target_still_counts_as_a_target_fill():
    """A limit the bar opens past fills at the OPEN, i.e. better than its own price. That is
    still the target filling, so "reached" is at-or-beyond, never equality."""
    point = _short(
        legs=[{"reason": "S-TP1", "price": _RUNG_1 - 3.0}],  # a short: lower is better
        targets=[{"price": _RUNG_1, "banks": True}],
    )
    assert _labels(point) == ["TP1"]


def test_a_rung_the_trade_reports_no_target_for_keeps_its_id():
    """Absent evidence is not evidence against. With no rung to check the id against, the id
    stands — inventing an `Exit` here would relabel every run stored before rungs existed."""
    point = _short(legs=[{"reason": "S-TP1", "price": _TRAIL_EXIT}])
    assert _labels(point) == ["TP1"]


def test_two_rungs_closed_by_one_event_at_one_price_draw_one_chip():
    """The trail takes every still-open bracket at the same price on the same bar, so the record
    holds one leg per bracket. They are one line on the chart and must be one chip — the second
    is de-collided 15px below the first and reads as a separate fill."""
    point = _short(
        legs=[
            {"reason": "S-TP1", "price": _TRAIL_EXIT},
            {"reason": "S-RUN", "price": _TRAIL_EXIT},
        ],
        targets=[{"price": _RUNG_1, "banks": True}, {"price": _RUNG_2, "banks": False}],
    )
    assert _labels(point) == ["Exit"]


# ── whether a rung is a TARGET at all ─────────────────────────────────────────


def test_a_rung_that_banks_nothing_is_marked_so_the_chart_can_stop_calling_it_a_target():
    point = _short(
        legs=[{"reason": "S-RUN", "price": _TRAIL_EXIT}],
        targets=[{"price": _RUNG_1, "banks": True}, {"price": _RUNG_2, "banks": False}],
    )
    assert _build_trades([point], _CANDLES)[0]["tpTargets"] == [
        {"price": _RUNG_1, "banks": True},
        {"price": _RUNG_2, "banks": False},
    ]


def test_a_run_stored_before_rungs_existed_says_UNKNOWN_and_never_says_no():
    """🔴 The rule this repo keeps re-learning: "no" and "cannot ask" must not be one value.

    Bare prices are every run on disk before 2026-08-21. Defaulting them to `banks: False` would
    redraw every historical chart's targets as stop steps off a measurement nobody made.
    """
    point = _short(legs=[{"reason": "S-RUN", "price": _TRAIL_EXIT}], targets=[_RUNG_1, _RUNG_2])
    rungs = _build_trades([point], _CANDLES)[0]["tpTargets"]
    assert rungs == [{"price": _RUNG_1}, {"price": _RUNG_2}]
    assert not any("banks" in r for r in rungs)


def test_the_ladder_keeps_the_STRATEGYS_order_and_is_not_sorted_by_distance():
    """A re-entry prices its first rung off risk and its second off a fib, so rung 2 is routinely
    NEARER the entry than rung 1 (182 of 205 trades on run 687c8df2a523). Sorting would renumber
    the strategy's own rungs, which is a different lie from the one being fixed."""
    point = _short(
        legs=[{"reason": "S-RUN", "price": _TRAIL_EXIT}],
        targets=[{"price": _RUNG_1, "banks": True}, {"price": _RUNG_2, "banks": False}],
    )
    prices = [r["price"] for r in _build_trades([point], _CANDLES)[0]["tpTargets"]]
    assert prices == [_RUNG_1, _RUNG_2]  # further one FIRST — the strategy's order
    assert prices != sorted(prices, reverse=True)  # …and not distance order for a short
