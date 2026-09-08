"""The shared order vocabulary — every invariant here exists to stop a specific silent failure.

⚠ Each test names the MUTATION that reddens it. A guard nobody has watched fail is a guard that
may be asserting nothing, and this repo has shipped at least eight tests that passed against
their own bug.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from execution.intents import FillReport, IntentKind, OrderIntent  # noqa: E402


def _open(**kw):
    base = dict(kind=IntentKind.OPEN, direction=1, qty=100.0, price=99.5, stop=99.0, reason="Long")
    base.update(kw)
    return OrderIntent(**base)


# ── An intent has to be answerable ────────────────────────────────────────────


def test_a_direction_that_is_not_long_or_short_is_refused():
    """0 is the value a flat position carries, and it names no trade to act on.
    MUTATION: drop the direction check and this goes green with `direction=0`."""
    with pytest.raises(ValueError, match="direction"):
        _open(direction=0)


def test_a_stop_move_names_no_quantity():
    """A stop belongs to the WHOLE position. A quantity here would read as "move the stop on part
    of it", which no venue can do and no strategy here means.
    MUTATION: allow qty on MOVE_STOP and this goes green."""
    with pytest.raises(ValueError, match="names no quantity"):
        OrderIntent(kind=IntentKind.MOVE_STOP, direction=1, stop=99.0, qty=50.0)


def test_a_stop_move_must_say_where_to():
    """MUTATION: default the stop to None-is-fine and this goes green — and live, the bot would
    send a stop-modify with no price."""
    with pytest.raises(ValueError, match="must carry the stop"):
        OrderIntent(kind=IntentKind.MOVE_STOP, direction=1)


@pytest.mark.parametrize("kind", [IntentKind.OPEN, IntentKind.ADD, IntentKind.CLOSE_PORTION])
def test_every_other_kind_needs_a_positive_quantity(kind):
    """A zero-quantity order is an instruction that cannot be carried out, and the honest place
    to find that out is where it is written, not at the venue.
    MUTATION: relax to `qty is None` only and the 0.0 case goes green."""
    with pytest.raises(ValueError, match="positive quantity"):
        OrderIntent(kind=kind, direction=1, qty=0.0, price=1.0)


def test_an_intent_cannot_be_edited_after_it_is_made():
    """A request that can be changed after it is submitted is one nothing can reconcile against.
    MUTATION: drop `frozen=True` and this goes green."""
    with pytest.raises(Exception):
        _open().qty = 5.0


def test_a_market_order_is_a_price_of_None_and_zero_is_a_real_price():
    """Three-state, and it is the difference between "at market" and "rest at 0.00".
    MUTATION: read the price falsily anywhere downstream and a 0.0 limit becomes a market order."""
    assert _open(price=None).price is None
    assert _open(price=0.0).price == 0.0


# ── A fill has to be distinguishable from a refusal ───────────────────────────


def test_nothing_filled_and_no_reason_is_REFUSED_at_construction():
    """🔴 Rule 1 where it matters most: never let "no" and "could not ask" be the same value.
    A silent zero here would reach the strategy as a refusal nobody recorded.
    MUTATION: drop this check and the silent zero constructs happily."""
    with pytest.raises(ValueError, match="silent zero"):
        FillReport(intent=_open(), filled_qty=0.0)


def test_a_refusal_carries_its_reason_and_reads_as_rejected():
    r = FillReport(intent=_open(), filled_qty=0.0, rejected_reason="below broker minimum")
    assert r.rejected and not r.partial
    assert "minimum" in r.rejected_reason


def test_a_fill_must_say_what_price_it_transacted_at():
    """MUTATION: drop the price check and a filled report with no price is constructible — and
    every P&L computed from it would be silently wrong."""
    with pytest.raises(ValueError, match="price it transacted at"):
        FillReport(intent=_open(), filled_qty=100.0)


def test_a_partial_fill_is_not_an_error_and_is_reported_as_partial():
    """The venue met part of the request. A strategy must be able to hold less than it asked for
    rather than assume it got everything — which is exactly what the old design assumed."""
    r = FillReport(intent=_open(qty=100.0), filled_qty=40.0, fill_price=99.5)
    assert r.partial and not r.rejected


def test_a_full_fill_is_neither_partial_nor_rejected():
    r = FillReport(intent=_open(qty=100.0), filled_qty=100.0, fill_price=99.5)
    assert not r.partial and not r.rejected


def test_a_stop_move_can_never_be_partial():
    """It names no quantity, so "less than asked" is not a thing that can be true of it.
    MUTATION: compute `partial` without the None guard and this raises instead."""
    stop = OrderIntent(kind=IntentKind.MOVE_STOP, direction=-1, stop=101.0)
    assert not FillReport(intent=stop, filled_qty=1.0, fill_price=101.0).partial


def test_a_negative_fill_is_refused():
    """MUTATION: drop the check and a negative quantity flows into position arithmetic."""
    with pytest.raises(ValueError, match="cannot be negative"):
        FillReport(intent=_open(), filled_qty=-1.0, fill_price=99.5)
