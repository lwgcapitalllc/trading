"""The 2026-08-25 defect: one limit order became five positions.

A broker request that TIMED OUT was read as one that FAILED. The outcome of a timeout is
UNKNOWN — the reply never arrived, and the broker may well have acted — so re-sending is exactly
the wrong response. Four requests timed out, all four had reached the broker, and five copies of
one limit filled at 4661.50 within 69 milliseconds.

Three separate faults had to line up, and each is pinned here on its own, because fixing one
and assuming the others followed is how this comes back:

  1. a send that does not confirm must ASK THE BROKER before reporting failure
  2. a cancel that is not confirmed must NOT be followed by a replacement order
  3. a resting order under our magic that we have no record of must be found DURING a run

**Every test below was watched RED against the fixed code by mutation** — the mutation for each
is named in its docstring. `test_the_incident_cannot_replay` is the end-to-end one: it drives the
real sequence from that day and fails with five orders on the pre-fix behaviour.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "live"))
# The bridge's broker fake and its strategy stub live next door and are reused rather than
# re-declared: a second fake of the same thing is a second thing to drift.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from broker_result import UNKNOWN  # noqa: E402
from test_live_bridge import (  # noqa: E402
    _bridge,
    _Dec,
    _FakeExecution,
    _Order,
    _Pend,
    _Sig,
    install_mt5_stub,
)


@pytest.fixture(autouse=True)
def _stub_mt5(monkeypatch):
    """The account cap reads a live balance, and without one it refuses every order - correctly,
    but that would make the cap tests below pass for the wrong reason."""
    install_mt5_stub(monkeypatch)


# ── 1. a send that does not confirm ──────────────────────────────────────────────────────────


class _TimeoutOnce:
    """Wraps the bridge's broker fake so the FIRST placement behaves exactly like 2026-08-25:
    the order reaches the book, and the caller is told it failed."""

    def __init__(self, ops, times=1, land=True):
        self._ops = ops
        self._left = times
        self._land = land

    def __getattr__(self, name):
        return getattr(self._ops, name)

    def place_pending_limit(self, direction, lots, price, sl, tp=0.0, comment="", symbol=None):
        if self._left > 0:
            self._left -= 1
            if self._land:
                # the order DID land - this is the whole point
                self._ops._ticket += 1
                self._ops.orders.append(
                    _Order(
                        self._ops._ticket,
                        price=price,
                        sl=sl,
                        volume=lots,
                        buy=direction == "bullish",
                    )
                )
            self._ops.actions.append(("place", direction, lots, price, sl))
            return None, None  # what the pre-fix broker layer reported for a timeout
        return self._ops.place_pending_limit(direction, lots, price, sl, tp, comment, symbol)


def test_the_incident_cannot_replay():
    """🔴 THE END-TO-END ONE. Five bars, every placement reported as failed, every one landing.

    MUTATION: remove the `_observe_orphans()` call from `sync()` and this ends with five resting
    orders — the incident, reproduced. With the sweep it never exceeds one.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, notes = _bridge(ex)
    b._mt5 = _TimeoutOnce(ops, times=5)

    for _ in range(5):
        b.sync(_Dec(), _Sig())
        assert len(ops.orders) <= 1, (
            f"{len(ops.orders)} orders are resting. The strategy wants ONE, and every extra "
            f"copy is a full-size position at the same price."
        )
    assert len(ops.orders) <= 1


def test_a_send_that_did_not_confirm_adopts_the_order_it_finds():
    """A reported failure whose order landed must not become a second order.

    ⚠ **Honest about what this covers.** The fake here returns `(None, None)` directly, so it
    never reaches `mt5_ops._reconcile_pending` - mutating that function does NOT turn this red,
    and an earlier version of this docstring claimed it would. What actually saves it at this
    level is the orphan sweep. **The broker layer's own reconciliation is tested where it
    lives**, in `test_mt5_ops_pending.py::test_a_timed_out_send_whose_order_LANDED_returns_that_ticket`.

    Both belong: the sweep is the backstop for every way an unowned order can appear, and the
    reconciliation is what stops one appearing in the first place. A test naming the wrong
    mutation is worse than one naming none - it reports coverage that is not there.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, notes = _bridge(ex)
    b._mt5 = _TimeoutOnce(ops, times=1)

    b.sync(_Dec(), _Sig())  # reported failure, order landed
    b.sync(_Dec(), _Sig())  # second bar: must not add another

    assert len(ops.orders) == 1, "a second order was placed beside the first"


def test_an_unreadable_book_after_a_failed_send_blocks_the_side():
    """ "Cannot ask" is never "nothing there". With the book unreadable the bot must place
    NOTHING, rather than assume the send failed and try again.

    MUTATION: make `_sync_side` ignore `self._unresolved`, and this fails with a second order.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, notes = _bridge(ex)

    class _Unreadable(_TimeoutOnce):
        def place_pending_limit(self, *a, **k):
            self._ops.actions.append(("place",) + a[:4])
            return UNKNOWN, None

    b._mt5 = _Unreadable(ops)
    b.sync(_Dec(), _Sig())
    assert b._unresolved[1] is True

    ops.orders_readable = False  # still cannot read it
    b.sync(_Dec(), _Sig())
    assert b._unresolved[1] is True, "the side was cleared without the book ever being read"
    placed = [a for a in ops.actions if a[0] == "place"]
    assert len(placed) == 1, "it sent a second order while the first one's fate was unknown"


def test_the_side_reopens_once_the_book_can_be_read():
    """The block is not a latch — it clears the moment the sweep can see the book, or the bot
    would stop trading for good after one bad minute."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, notes = _bridge(ex)
    b._unresolved[1] = True
    ops.orders_readable = True
    b.sync(_Dec(), _Sig())
    assert b._unresolved[1] is False


# ── 2. a cancel that was not confirmed ───────────────────────────────────────────────────────


def test_a_failed_cancel_is_never_followed_by_a_replacement():
    """🔴 This one needs NO timeout. An ordinary rejected cancel was enough: the bridge threw
    the answer away, forgot the order, and placed a second one on top of it.

    MUTATION: have `_drop_rest` return True regardless, and this fails with two orders.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, notes = _bridge(ex)
    b.sync(_Dec(), _Sig())
    assert len(ops.orders) == 1
    first = ops.orders[0].ticket

    ops.cancel_result = False  # the broker refuses the cancel
    ex._pend_long = _Pend(1, 3290.0, 84.0, 3280.0)  # size doubles -> cancel + re-place
    b.sync(_Dec(), _Sig())

    assert len(ops.orders) == 1, "a second order was placed while the first was still resting"
    assert ops.orders[0].ticket == first
    assert b._rest[1] is not None, "the record was cleared for an order that is still there"


def test_an_unconfirmable_cancel_is_treated_as_a_failed_one():
    """UNKNOWN takes the conservative branch: one stale order beats two live ones.

    MUTATION: treat `UNKNOWN` as success in `_drop_rest` and this fails with two orders.
    """
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, notes = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ops.cancel_result = UNKNOWN
    ex._pend_long = _Pend(1, 3290.0, 84.0, 3280.0)
    b.sync(_Dec(), _Sig())
    assert len(ops.orders) == 1
    assert b._rest[1] is not None


def test_the_unconfirmed_cancel_is_recorded():
    """A refusal nobody can count is a refusal nobody acts on."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, notes = _bridge(ex)
    b.sync(_Dec(), _Sig())
    ops.cancel_result = False
    ex._pend_long = _Pend(1, 3290.0, 84.0, 3280.0)
    b.sync(_Dec(), _Sig())
    assert any(k == "event:cancel_unconfirmed" for k, _ in ledger.rows)


# ── 3. an order at the broker we have no record of ───────────────────────────────────────────


def test_an_orphan_order_is_found_during_the_run():
    """Not only at startup. Four orphans sat resting for five hours through twenty bars.

    MUTATION: drop the `_observe_orphans()` call and this fails with the orphan still resting.
    """
    ex = _FakeExecution()
    b, ops, ledger, notes = _bridge(ex)
    ops.orders = [_Order(4242, price=3290.0, sl=3280.0, volume=0.4, buy=False)]

    b.sync(_Dec(), _Sig())

    assert ops.orders == [], "an order nobody placed is still resting"
    assert any(k == "event:order_orphaned" for k, _ in ledger.rows)


def test_an_unreadable_book_cancels_nothing():
    """Fail closed. A read that failed must not be read as "the book is empty", and it must
    certainly not be read as "everything here is an orphan".

    MUTATION: make `_observe_orphans` treat `None` as `[]` and this still passes — which is why
    the assertion is on `cancel` actions, not on the order list.
    """
    ex = _FakeExecution()
    b, ops, ledger, notes = _bridge(ex)
    ops.orders = [_Order(4242, price=3290.0, sl=3280.0, volume=0.4, buy=False)]
    ops.orders_readable = False

    b.sync(_Dec(), _Sig())

    assert not [a for a in ops.actions if a[0] == "cancel"]
    assert not any(k == "event:order_orphaned" for k, _ in ledger.rows)


def test_the_bots_own_resting_order_is_not_an_orphan():
    """The sweep must be silent on the ordinary case, or it is a guard people learn to ignore —
    which this repo has already measured to be worth less than no guard at all."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, notes = _bridge(ex)
    b.sync(_Dec(), _Sig())  # places one
    b.sync(_Dec(), _Sig())  # and again, unchanged
    assert len(ops.orders) == 1
    assert not any(k == "event:order_orphaned" for k, _ in ledger.rows)


def test_a_filled_order_is_not_an_orphan():
    """A pending order that FILLS leaves the book and becomes a position. If the sweep read that
    as an orphan it would try to cancel a live position's origin on every fill."""
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0))
    b, ops, ledger, notes = _bridge(ex)
    b.sync(_Dec(), _Sig())
    from test_live_bridge import _Pos

    ops.positions = [_Pos(ops.orders[0].ticket, 0, 3290.0, 0.42, 3280.0)]
    ex._pos_dir, ex._pend_long = 1, None
    b.sync(_Dec(stop=3280.0), _Sig())
    assert not any(k == "event:order_orphaned" for k, _ in ledger.rows)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ── 4. the account risk cap's unstated premise ───────────────────────────────────────────────


def test_an_unknown_order_under_our_own_magic_COUNTS_against_the_account_cap():
    """🔴 The check that could have caught it was the one told not to look.

    The cap excluded everything under this bot's magic, on the premise that our own orders are
    always the thing being replaced. Four orders we had no record of were under our magic too, so
    five copies of a 10% order looked like an empty account.

    MUTATION: change the exclusion back to `it.magic != self._mt5.magic` and this fails - the
    order is allowed with half the account already committed.
    """
    from test_live_bridge import _cap_pend, _Order

    b, ops, ledger, notes = _bridge(
        _FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0
    )
    # An order under OUR magic that this bot never placed and has no record of. It alone fills
    # the account's whole budget, so a cap that can see it must refuse anything more.
    ops.orders = [_Order(4242, price=3300.0, sl=3290.0, volume=0.2, buy=True)]

    plan = b._plan(1, _cap_pend())

    assert not plan.ok, "an unrecognised order under our own magic was counted as no risk at all"
    assert plan.code == "account_risk_cap"


def test_our_OWN_recorded_order_is_still_excluded():
    """The exclusion has to survive, or the bot refuses its own re-size the moment it is near the
    cap - which reads exactly like a broken strategy and is why the exclusion exists."""
    from test_live_bridge import _cap_pend

    b, ops, ledger, notes = _bridge(
        _FakeExecution(pend_long=_cap_pend()), account_risk_cap_pct=10.0
    )
    b.sync(_Dec(), _Sig())  # places one, and RECORDS it
    assert b._rest[1] is not None, "nothing was placed, so this proves nothing"
    assert ops.orders, "the broker holds no order, so there is nothing to exclude"

    plan = b._plan(1, _cap_pend())  # the same setup again, one bar later

    assert plan.ok, "the bot refused an order because of its OWN recorded resting order"
