"""Shared-account tests — hand-computed, offline. Lock the contention gate:
reservation to the live stop, cap tracks balance, room = cap − reserved, desired-qty
scaling, split-by-weight ties, sub-floor blocks, close frees room, and SoloAccount =
standalone sizing (scale == 1).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest.portfolio.account import PortfolioAccount, SoloAccount


def _acct(balance=10_000.0, cap=0.10, floor=0.0):
    return PortfolioAccount(balance=balance, risk_cap_pct=cap, entry_floor_pct=floor)


# ── reservation & cap ───────────────────────────────────────────────────────────


def test_fill_grants_full_size_then_breakeven_frees_reservation():
    a = _acct()  # cap = 10% of 10k = 1000
    # desired 200 units × (100−95) × 1 = 1000 risk → fits exactly
    qty = a.request_fill("A", +1, entry=100.0, stop=95.0, desired_qty=200.0, point_value=1.0)
    assert qty == 200.0  # granted in full
    assert a.reserved() == 1000.0
    assert a.room() == 0.0
    a.update_stop("A", current_stop=100.0)  # stop → breakeven
    assert a.reserved() == 0.0
    assert a.room() == 1000.0


def test_stop_in_profit_reserves_nothing():
    a = _acct()
    a.request_fill("A", +1, 100.0, 95.0, desired_qty=200.0, point_value=1.0)
    a.update_stop("A", current_stop=103.0)  # locked profit, not risk
    assert a.reserved() == 0.0


def test_cap_tracks_live_balance():
    a = _acct()
    assert a.cap() == 1000.0
    a.on_close("none", pnl=5_000.0)  # balance → 15k
    assert a.balance == 15_000.0
    assert a.cap() == 1500.0


def test_short_reservation_uses_stop_above_entry():
    a = _acct()
    a.request_fill("S", -1, entry=100.0, stop=105.0, desired_qty=200.0, point_value=1.0)
    assert a.reserved() == 1000.0  # 200 × (105−100)


# ── shrink-to-fit & floor ───────────────────────────────────────────────────────


def test_second_leg_is_scaled_to_remaining_room():
    a = _acct()
    a.request_fill("A", +1, 100.0, 96.0, desired_qty=200.0, point_value=1.0)  # 200×4 = 800 risk
    assert a.reserved() == 800.0
    # B wants 200×5 = 1000 risk, only 200 room left → scaled to 200/1000 = 0.2 → qty 40
    qty = a.request_fill("B", +1, 100.0, 95.0, desired_qty=200.0, point_value=1.0)
    assert qty == 40.0
    assert a.reserved() == 1000.0  # now at the cap


def test_sub_floor_grant_is_blocked():
    a = _acct(floor=0.03)  # floor = 3% of 10k = 300 risk dollars
    a.request_fill("A", +1, 100.0, 96.0, desired_qty=200.0, point_value=1.0)  # 800 risk, room 200
    qty = a.request_fill("B", +1, 100.0, 95.0, desired_qty=200.0, point_value=1.0)
    assert qty == 0.0  # 200 granted < floor 300 → blocked
    assert not a.has_position("B")


# ── same-bar ties ───────────────────────────────────────────────────────────────


def test_same_bar_tie_splits_room_by_desired_risk():
    a = _acct()  # room 1000
    out = a.request_fills(
        [
            {
                "leg": "A",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,
                "desired_qty": 200.0,
                "point_value": 1.0,
            },
            {
                "leg": "B",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,
                "desired_qty": 200.0,
                "point_value": 1.0,
            },
        ]
    )
    # both want 1000 risk, total 2000 > room 1000 → factor 0.5 → qty 100 each
    assert out == {"A": 100.0, "B": 100.0}
    assert a.reserved() == 1000.0


def test_same_bar_tie_unequal_weights():
    a = _acct()  # room 1000
    out = a.request_fills(
        [
            {
                "leg": "A",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,
                "desired_qty": 300.0,
                "point_value": 1.0,
            },
            {
                "leg": "B",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,
                "desired_qty": 100.0,
                "point_value": 1.0,
            },
        ]
    )
    # risks 1500 & 500, total 2000, factor 0.5 → A qty 150, B qty 50
    assert out == {"A": 150.0, "B": 50.0}


def test_same_bar_both_fit_get_full_size():
    a = _acct()  # room 1000
    out = a.request_fills(
        [
            {
                "leg": "A",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,
                "desired_qty": 100.0,
                "point_value": 1.0,
            },
            {
                "leg": "B",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,
                "desired_qty": 100.0,
                "point_value": 1.0,
            },
        ]
    )
    # risks 500 + 500 = 1000 == room → no scaling, full size
    assert out == {"A": 100.0, "B": 100.0}


# ── booking & close ──────────────────────────────────────────────────────────────


def test_book_pnl_moves_balance_without_touching_reservation():
    a = _acct()
    a.request_fill("A", +1, 100.0, 95.0, desired_qty=200.0, point_value=1.0)
    a.book_pnl("A", 300.0)  # a partial exit's P&L
    assert a.balance == 10_300.0
    assert a.reserved() == 1000.0  # position still open, still reserving


def test_close_position_frees_room_without_moving_balance():
    a = _acct()
    a.request_fill("A", +1, 100.0, 95.0, desired_qty=200.0, point_value=1.0)
    a.close_position("A")
    assert a.reserved() == 0.0
    assert a.balance == 10_000.0  # close doesn't book P&L (already booked)


def test_on_close_books_and_frees():
    a = _acct()
    a.request_fill("A", +1, 100.0, 95.0, desired_qty=200.0, point_value=1.0)
    a.on_close("A", pnl=250.0)
    assert a.reserved() == 0.0
    assert a.balance == 10_250.0
    assert not a.has_position("A")


# ── trailing halt ────────────────────────────────────────────────────────────────


def test_trailing_halt_trips_on_peak_to_trough_drop():
    a = _acct()
    a.on_close("x", pnl=2_000.0)  # peak 12k
    a.on_close("y", pnl=-1_500.0)  # down to 10.5k, drop 1500
    assert a.check_trailing_halt(trailing_max_loss=1_000.0) is True
    assert a.halted is True


# ── SoloAccount = standalone sizing ──────────────────────────────────────────────


def test_solo_account_grants_full_desired_qty():
    s = SoloAccount(balance=10_000.0)
    qty = s.request_fill("A", +1, 100.0, 95.0, desired_qty=40.0, point_value=1.0)
    assert qty == 40.0  # scale == 1, no cap
    assert s.room() == float("inf")


def test_solo_account_never_blocks_a_second_leg():
    s = SoloAccount(balance=10_000.0)
    s.request_fill("A", +1, 100.0, 95.0, desired_qty=5_000.0, point_value=1.0)  # huge
    qty = s.request_fill("B", +1, 100.0, 95.0, desired_qty=5_000.0, point_value=1.0)
    assert qty == 5_000.0  # never contended


# ── dust grants (2026-08-09) ────────────────────────────────────────────────────
#
# 🔴 The defect these pin cost a whole leg and raised nothing. With the budget almost full, a leg
# asking for $4,385.98 of risk was granted a fraction of a cent, and `_open` scaled its qty by
# `granted/desired` — about 1e-6 — opening a position of no meaningful size. A leg holds ONE
# position at a time, so that dust occupied its only slot from November 2020 to August 2026:
# 18 trades where a solo replay of the same leg made 181, and NOTHING in the contention log said
# a word, because a grant is not a refusal.
#
# It survived because the first shared-account run ever made had an EMPTY contention log — the
# budget never bound, so this branch had never once executed.


def test_a_grant_too_small_to_be_a_position_is_a_BLOCK():
    """A leg asking against an almost-full budget must be refused, not handed dust.

    ⚠ Watched RED against `granted_risk <= 0.0`: the old test returns a qty of ~2e-9 and the
    account opens a position with it.
    """
    a = _acct()  # cap = 1000
    # fill 999.999 of the 1000, leaving a tenth of a cent of room
    a.request_fill("A", +1, entry=100.0, stop=95.0, desired_qty=199.9998, point_value=1.0)
    assert 0.0 < a.room() < 0.01

    qty = a.request_fill("B", +1, entry=100.0, stop=95.0, desired_qty=200.0, point_value=1.0)
    assert qty == 0.0, "a sub-cent grant must not become a position"
    assert a.contention[-1]["leg"] == "B"
    assert a.contention[-1]["blocked"] is True


def test_a_dust_grant_never_logs_as_an_UNBLOCKED_zero():
    """The log's own tell, and the reason the defect read as impossible rather than as itself.

    `_log_contention` rounds to 2dp, so a $0.003 grant printed `granted_risk: 0.0` with
    `blocked: False` — a combination the shrink branch cannot produce. Any event showing a zero
    grant must now be a block.
    """
    a = _acct()
    a.request_fill("A", +1, entry=100.0, stop=95.0, desired_qty=199.9998, point_value=1.0)
    a.request_fill("B", +1, entry=100.0, stop=95.0, desired_qty=200.0, point_value=1.0)
    for c in a.contention:
        assert not (c["granted_risk"] == 0.0 and c["blocked"] is False), c


def test_the_same_bar_TIE_path_refuses_dust_too():
    """`request_fills` splits the room by weight and has its own copy of the gate. A guard on one
    of two entry paths is a guard on neither — the split path is what runs whenever two legs fill
    on the same bar, which is exactly when the budget is tightest.

    ⚠ Watched RED against `granted_risk <= 0.0` in `request_fills`.
    """
    a = _acct()
    a.request_fill("A", +1, entry=100.0, stop=95.0, desired_qty=199.9998, point_value=1.0)
    out = a.request_fills(
        [
            {
                "leg": "B",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,
                "desired_qty": 200.0,
                "point_value": 1.0,
            },
            {
                "leg": "C",
                "dir": -1,
                "entry": 100.0,
                "stop": 105.0,
                "desired_qty": 200.0,
                "point_value": 1.0,
            },
        ]
    )
    assert out == {"B": 0.0, "C": 0.0}
    assert all(c["blocked"] for c in a.contention if c["leg"] in ("B", "C"))


def test_a_REAL_shrink_is_still_granted():
    """The guard must not turn ordinary contention into refusal — shrink-to-fit is the design, and
    a leg getting 40% of its size is a normal outcome the log calls a shrink, not a block."""
    a = _acct()
    a.request_fill("A", +1, entry=100.0, stop=95.0, desired_qty=120.0, point_value=1.0)  # 600
    qty = a.request_fill("B", +1, entry=100.0, stop=95.0, desired_qty=200.0, point_value=1.0)
    assert abs(qty - 80.0) < 1e-9, qty  # 400 of the 1000 left
    assert a.contention[-1]["blocked"] is False
    assert a.contention[-1]["granted_risk"] == 400.0


def test_a_floor_equal_to_the_legs_own_risk_does_not_refuse_an_uncontested_entry():
    """RED by mutation: drop the `_GRANT_EPS` tolerance in `_below_floor` — i.e. put it back to
    `granted_risk < floor`.

    The natural way to express *risk is never layered* is to set the entry floor to the leg's own
    full risk, so any entry the budget has to shrink is refused outright instead. That puts the
    granted risk and the floor on EXACTLY the same number — and they are reached by different
    arithmetic (the leg divides by the stop distance to get a qty, the account re-multiplies), so
    they differ in the last bit. A bare `<` then refuses an entry that nothing was competing for.

    MEASURED before the tolerance existed: A+ at 10% under a 10% cap with a 10% floor was refused
    3,650 times over 7.9 years and took 31 trades instead of 181. Nothing was open; the whole
    budget was free.
    """
    acct = PortfolioAccount(balance=10_000.0, risk_cap_pct=0.10, entry_floor_pct=0.10)
    # Deliberately a stop distance that does NOT divide the balance exactly, so the round trip
    # through qty cannot be exact in binary — the shape the real legs hit.
    dist, pv = 7.3, 100.0
    qty = (10_000.0 * 0.10) / (dist * pv)
    granted = acct.request_fill("solo", 1, 2000.0, 2000.0 - dist, qty, pv)
    assert granted > 0.0, "an uncontested entry at exactly the cap was refused"
    assert acct.contention == []


def test_a_floor_still_refuses_an_entry_the_budget_genuinely_shrank():
    """RED by mutation: make `_below_floor` return False always.

    The tolerance must not turn the floor off. This is the other side of the boundary — a real
    contest, where the room left is a fraction of what the leg asked for — and it has to be
    refused outright rather than trickled in, which is the whole point of setting a floor.
    """
    # Cap 15%, floor 10%, both legs asking 10%. The first is granted in full and leaves 5% —
    # a real, non-zero room that is still under the floor, which is the case the floor exists
    # for. (A first leg asking LESS than the floor would itself be refused, which is what the
    # first draft of this test did — it then measured nothing.)
    acct = PortfolioAccount(balance=10_000.0, risk_cap_pct=0.15, entry_floor_pct=0.10)
    dist, pv = 7.3, 100.0
    qty = (10_000.0 * 0.10) / (dist * pv)
    assert acct.request_fill("first", 1, 2000.0, 2000.0 - dist, qty, pv) > 0.0
    assert acct.room() > 0.0, "no room left at all, so the FLOOR is not what refuses the second"
    granted = acct.request_fill("second", 1, 2000.0, 2000.0 - dist, qty, pv)
    assert granted == 0.0, "an entry with only half its risk available was not refused"
    assert any(c["blocked"] for c in acct.contention)


# ── all-or-nothing: refuse a contested entry rather than shrink it ───────────────
#
# 🔴 THE RULE THIS EXPRESSES: *risk is never layered*. Shrink-to-fit takes a smaller version of
# the trade; this refuses it outright and leaves the budget to whoever already holds it. Both stay
# under the cap — this is a preference about WHICH trade you end up in, not a tighter limit.
#
# ⚠ It is deliberately NOT expressed as an entry floor. A floor is one number for the whole
# account while legs risk different amounts, so any floor high enough to make a 10% leg
# all-or-nothing also bans a 2.5% leg outright whatever the room — MEASURED at 64 refusals and 0
# trades. Asking "was this granted in full?" needs no per-leg number and works for any number of
# legs, which is why the policy lives on the grant rather than on a size.
#
# ⚠ It rides on `_is_shrunk`, so it inherits that method's tolerance ON PURPOSE. A leg whose own
# risk equals the cap lands exactly on the boundary and misses by a float's last bit; without the
# tolerance this policy would refuse every uncontested entry — the same defect the floor test
# below already pins, and the reason that one exists.


def test_all_or_nothing_refuses_the_entry_the_budget_would_have_shrunk():
    """RED by mutation: drop the `all_or_nothing` branch in `request_fill`, and the contested leg
    is granted 80.0 (shrunk) instead of refused."""
    a = PortfolioAccount(balance=10_000.0, risk_cap_pct=0.10, all_or_nothing=True)
    a.request_fill("A", +1, entry=100.0, stop=95.0, desired_qty=120.0, point_value=1.0)  # 600
    qty = a.request_fill("B", +1, entry=100.0, stop=95.0, desired_qty=200.0, point_value=1.0)
    assert qty == 0.0  # would have been shrunk to 80 → refused
    assert not a.has_position("B")
    assert a.contention[-1]["blocked"] is True
    assert a.contention[-1]["granted_risk"] == 0.0  # refused, not "granted 400 and dropped"
    assert a.reserved() == 600.0  # A keeps the whole budget it was using


def test_all_or_nothing_still_grants_an_entry_that_fits_in_full():
    """The policy must only fire on CONTENTION. An entry with room for its full size is untouched,
    or the rule is a size ban wearing an allocator's clothes."""
    a = PortfolioAccount(balance=10_000.0, risk_cap_pct=0.10, all_or_nothing=True)
    a.request_fill("A", +1, entry=100.0, stop=95.0, desired_qty=100.0, point_value=1.0)  # 500
    qty = a.request_fill("B", +1, entry=100.0, stop=95.0, desired_qty=100.0, point_value=1.0)
    assert qty == 100.0  # 500 + 500 = the 1000 cap exactly
    assert a.reserved() == 1000.0


def test_all_or_nothing_does_not_refuse_a_leg_sized_exactly_at_the_cap():
    """🔴 The boundary that has already broken the floor test once. A lone leg risking exactly the
    cap reaches `granted` and `desired` by different arithmetic and they differ in the last bit.
    RED by mutation: change `_is_shrunk` back to a bare `granted_risk < desired_risk`."""
    a = PortfolioAccount(balance=10_000.0, risk_cap_pct=0.10, all_or_nothing=True)
    qty = a.request_fill("A", +1, entry=100.0, stop=95.0, desired_qty=200.0, point_value=1.0)
    assert qty == 200.0, qty  # 1000 risk against a 1000 cap
    assert a.contention == []  # nothing contended; nothing logged


def test_all_or_nothing_applies_on_the_same_bar_tie_path_too():
    """Two legs filling on the SAME bar split the room, so both get shrunk — and under this policy
    both must be refused. RED by mutation: drop the branch in `request_fills` only, and this fails
    while the single-fill test above still passes."""
    a = PortfolioAccount(balance=10_000.0, risk_cap_pct=0.10, all_or_nothing=True)
    out = a.request_fills(
        [
            {
                "leg": "A",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,
                "desired_qty": 150.0,
                "point_value": 1.0,
            },  # 750
            {
                "leg": "B",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,
                "desired_qty": 150.0,
                "point_value": 1.0,
            },  # 750, total 1500 vs 1000 room
        ]
    )
    assert out == {"A": 0.0, "B": 0.0}
    assert a.reserved() == 0.0
    assert all(c["blocked"] is True for c in a.contention)


def test_all_or_nothing_defaults_OFF_so_no_stored_run_moves():
    """The policy is opt-in. Every run recorded before it existed used shrink-to-fit, and a default
    that quietly changed them would re-write history rather than add an option."""
    a = _acct()
    assert a.all_or_nothing is False
    a.request_fill("A", +1, entry=100.0, stop=95.0, desired_qty=120.0, point_value=1.0)
    qty = a.request_fill("B", +1, entry=100.0, stop=95.0, desired_qty=200.0, point_value=1.0)
    assert abs(qty - 80.0) < 1e-9  # shrunk, exactly as before
    assert SoloAccount(balance=10_000.0).all_or_nothing is False
