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


# ── leg PRECEDENCE: reserved headroom for a leg that is not holding yet ──────────
#
# 🔴 WHY IT CANNOT BE "THE BETTER LEG WINS THE CLASH". By the time the priority leg asks, the
# other one is already holding the budget, and the only way to take it back is closing a live
# trade — which this repo refuses on principle (a resized order is not the trade the strategy is
# holding). So precedence has to act BEFORE the clash: a priority leg's risk stays reserved even
# while it is FLAT, and lower legs may only use what is genuinely spare.
#
# 🔴 MEASURED, and it is why this exists: under `all_or_nothing` with no precedence, A+ was
# refused 176 times and lost a third of its edge (127.11R → 85.05R) because a leg worth $14,025
# standalone over eight years got to the budget first. Whoever asked first won, and the legs were
# treated as equals. They are not.
#
# ⚠ The consequence is deliberate and must not be "fixed" later by someone who finds it harsh:
# with A+ at 10% under a 10% cap there is NO spare room, so a lower leg never trades at all. That
# is the correct answer to "is it worth taking room off A+" — the honest way to run a second leg
# is to give it headroom of its own (raise the cap), not to let it bite into the first.
#
# ⚠ No double counting: a priority leg that is ALREADY holding has its real reservation in
# `reserved()`, so it must not also get headroom. RED by mutation: drop the `has_position` test in
# `_headroom_for` and the third test below fails with the room halved twice.


def _prio_acct(balance=10_000.0, cap=0.10):
    return PortfolioAccount(
        balance=balance,
        risk_cap_pct=cap,
        leg_priority={"aplus": 0, "recovery": 1},
        leg_risk_pct={"aplus": 0.10, "recovery": 0.025},
    )


def test_a_lower_leg_is_held_out_of_the_headroom_reserved_for_a_FLAT_priority_leg():
    """A+ is flat and risks the whole 10% cap, so nothing is spare. The recovery leg asks for
    2.5% and is refused — not because the budget is in use, but because it is SPOKEN FOR."""
    a = _prio_acct()
    qty = a.request_fill(
        "recovery", +1, entry=100.0, stop=95.0, desired_qty=5.0, point_value=1.0
    )  # wants 25 risk
    assert qty == 0.0
    assert not a.has_position("recovery")
    assert a.contention[-1]["blocked"] is True


def test_the_priority_leg_is_never_held_out_by_its_OWN_headroom():
    """The reservation exists FOR A+. If A+ were made to respect it, the rule would lock out the
    leg it is protecting — which is the failure it exists to prevent, wearing the opposite mask."""
    a = _prio_acct()
    qty = a.request_fill(
        "aplus", +1, entry=100.0, stop=95.0, desired_qty=200.0, point_value=1.0
    )  # the full 1000 = 10%
    assert qty == 200.0
    assert a.reserved() == 1000.0


def test_a_priority_leg_that_is_ALREADY_holding_does_not_also_get_headroom():
    """No double counting. A+ holds 600 of the 1000 cap, so 400 is genuinely spare and the
    recovery leg may have its 25. RED by mutation: drop the `has_position` test in `_headroom_for`
    and this is refused, because A+'s risk is subtracted twice."""
    a = _prio_acct()
    a.request_fill("aplus", +1, entry=100.0, stop=97.0, desired_qty=200.0, point_value=1.0)  # 600
    qty = a.request_fill("recovery", +1, entry=100.0, stop=95.0, desired_qty=5.0, point_value=1.0)
    assert qty == 5.0, qty
    assert a.reserved() == 625.0


def test_headroom_is_released_once_the_priority_leg_closes_for_good():
    """Precedence is about the budget, not about punishing the other leg forever — when A+ is
    flat again the reservation is back, and when the cap has room beyond it the lower leg trades."""
    a = PortfolioAccount(
        balance=10_000.0,
        risk_cap_pct=0.125,  # 1250: 1000 for A+, 250 spare
        leg_priority={"aplus": 0, "recovery": 1},
        leg_risk_pct={"aplus": 0.10, "recovery": 0.025},
    )
    qty = a.request_fill(
        "recovery", +1, entry=100.0, stop=95.0, desired_qty=50.0, point_value=1.0
    )  # wants 250, exactly the spare
    assert qty == 50.0, qty  # granted in full


def test_precedence_applies_on_the_same_bar_tie_path_too():
    """Both legs fill on the SAME bar. The tie splits the room, and the room the LOWER leg sees
    must already have A+'s headroom taken out of it."""
    a = _prio_acct()
    out = a.request_fills(
        [
            {
                "leg": "recovery",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,
                "desired_qty": 5.0,
                "point_value": 1.0,
            },
        ]
    )
    assert out == {"recovery": 0.0}


def test_no_priority_declared_means_behaviour_is_exactly_as_before():
    """Opt-in. Every run recorded before precedence existed had none, and a default would
    re-write them."""
    a = _acct()
    assert a.leg_priority == {}
    a.request_fill("A", +1, entry=100.0, stop=95.0, desired_qty=120.0, point_value=1.0)
    qty = a.request_fill("B", +1, entry=100.0, stop=95.0, desired_qty=200.0, point_value=1.0)
    assert abs(qty - 80.0) < 1e-9  # shrunk, exactly as before


def test_a_same_bar_tie_is_settled_BY_RANK_not_split_proportionally():
    """🔴 The two paths must be made to DISAGREE or this test proves nothing — and the first
    version of it proved nothing, because its numbers fitted inside the cap where proportional
    splitting and rank ordering give the identical answer. It passed with the branch deleted.

    Here the legs want 1500 against a 1250 cap, so the split has to bite. Proportional gives A+
    833 of its 1000 (diluted by the leg that defers to it). By rank A+ takes its full 1000 and the
    recovery leg gets the genuine 250 remainder.

    WATCHED RED by mutation: replace `if self.leg_priority:` in `request_fills` with `if False:`
    and A+ comes back 166.67 instead of 200.0."""
    a = PortfolioAccount(
        balance=10_000.0,
        risk_cap_pct=0.125,  # cap 1250
        leg_priority={"aplus": 0, "recovery": 1},
        leg_risk_pct={"aplus": 0.10, "recovery": 0.025},
    )
    out = a.request_fills(
        [
            {
                "leg": "recovery",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,  # listed FIRST
                "desired_qty": 100.0,
                "point_value": 1.0,
            },  # wants 500
            {
                "leg": "aplus",
                "dir": +1,
                "entry": 100.0,
                "stop": 95.0,
                "desired_qty": 200.0,
                "point_value": 1.0,
            },  # wants 1000
        ]
    )
    assert out["aplus"] == 200.0, out  # full size, though listed second
    assert out["recovery"] == 50.0, out  # the real remainder, 250 of the 500 it wanted
    assert a.reserved() == 1250.0


# ── the venue ceiling (max_lots) ────────────────────────────────────────────────
#
# Every test below was watched RED by mutation on 2026-09-02 before being kept. The mutations
# are named per test, because "it went red" is worth nothing without "for the right reason" —
# a test that goes red when the ceiling is deleted entirely proves only that the code runs.


def _lot_acct(balance=10_000_000.0, max_lots=100.0, contract_size=100.0):
    """A budget big enough that only the CEILING can ever bind. `risk_cap_pct` is a fraction, so
    1.0 is the whole balance — the point is to isolate the venue limit from the risk limit."""
    return PortfolioAccount(
        balance=balance,
        risk_cap_pct=1.0,
        entry_floor_pct=0.0,
        max_lots=max_lots,
        contract_size=contract_size,
    )


def test_an_ask_over_the_ceiling_is_RESIZED_not_refused():
    """The whole policy in one assertion. 742.60 lots is the largest ask in the real A+ book.

    RED when `_cap_to_max_lots` returns `desired_qty` unchanged (granted 74,260.0), and RED the
    other way when the over-max branch returns 0.0 the way the live path used to refuse.
    """
    a = _lot_acct()
    qty = a.request_fill("A", +1, entry=100.0, stop=99.0, desired_qty=74_260.0, point_value=1.0)
    assert qty == 10_000.0  # 100 lots × 100 oz — the ceiling, not zero and not what was asked
    assert qty > 0.0, "a resize is not a refusal"


def test_an_ask_UNDER_the_ceiling_is_untouched_and_logs_nothing():
    """The half that proves the cap is not just clamping everything to 100 lots.

    RED when the comparison is `<` instead of `<=`... only at exactly the ceiling, which is why
    the exact-boundary case below exists separately. RED here when `_cap_to_max_lots` returns
    `ceiling` unconditionally.
    """
    a = _lot_acct()
    qty = a.request_fill("A", +1, entry=100.0, stop=99.0, desired_qty=5_000.0, point_value=1.0)
    assert qty == 5_000.0  # 50 lots
    assert a.lot_capped == []


def test_an_ask_EXACTLY_at_the_ceiling_is_not_recorded_as_capped():
    """Pins the boundary comparison itself. RED when `<=` becomes `<` — the qty is unchanged
    either way, so ONLY the log can catch this one, which is the point of asserting on it."""
    a = _lot_acct()
    qty = a.request_fill("A", +1, entry=100.0, stop=99.0, desired_qty=10_000.0, point_value=1.0)
    assert qty == 10_000.0
    assert a.lot_capped == [], "exactly at the ceiling is not over it"


def test_max_lots_None_switches_the_ceiling_off_for_the_parity_anchor():
    """The escape hatch `compare_strategy.py` needs — the Pine twin has no ceiling, so grading a
    capped run against it would report a policy difference as a parity break.

    RED when the `self.max_lots is None` guard is dropped from `_cap_to_max_lots`.
    """
    a = _lot_acct(max_lots=None)
    qty = a.request_fill("A", +1, entry=100.0, stop=99.0, desired_qty=74_260.0, point_value=1.0)
    assert qty == 74_260.0
    assert a.lot_capped == []


def test_the_ceiling_applies_BEFORE_the_risk_arithmetic():
    """The ordering property, and the subtle one.

    A leg asking 742 lots must have its risk measured on the 100 lots it can actually hold, not
    on the 742 it wanted. Cap afterwards and `desired_risk` describes a position that cannot
    exist, so `_open` scales the real qty by `granted/desired` — a ratio computed against a
    fiction — and shrinks a leg that fitted perfectly well.

    🔴 **The budget has to BIND for this test to see anything, and the first version of it did
    not — it was written with an unlimited budget, passed, and stayed green under the very
    mutation it names.** With room to spare both orderings grant the same 10,000, because the
    inflated desired_risk cancels itself in the scale factor. Caught by mutation on 2026-09-02;
    kept as written proof that "reserved the right amount" and "computed it in the right order"
    are different questions.

    Room here is 20,000 — above the capped risk (10,000) and below the uncapped one (74,260),
    which is the only window where the two orderings disagree.

    RED when the `_cap_to_max_lots` call is moved BELOW the `_risk_of` line in `request_fill`:
    the leg is handed 2,693 units instead of 10,000 and logged as contention that never happened.
    """
    a = _lot_acct(balance=10_000_000.0)
    a.risk_cap_pct = 0.002  # room = 20,000
    assert a.room() == 20_000.0, "the budget must bind between the two orderings"
    qty = a.request_fill("A", +1, entry=100.0, stop=99.0, desired_qty=74_260.0, point_value=1.0)
    assert qty == 10_000.0, "the ceiling fits inside the budget; nothing should have shrunk it"
    assert a.reserved() == 10_000.0
    assert a.contention == [], "a leg that fitted was logged as contended"


def test_a_lot_cap_is_NOT_logged_as_contention():
    """Contention means the legs competed for the budget. A venue ceiling is not competition —
    this account has the whole balance available and still caps.

    RED when `_cap_to_max_lots` appends to `self.contention` instead of `self.lot_capped`, which
    is exactly the shortcut that makes a solo run look like it had a clash.
    """
    a = _lot_acct()
    a.request_fill("A", +1, entry=100.0, stop=99.0, desired_qty=74_260.0, point_value=1.0)
    assert a.contention == [], "the budget never bound; nothing competed"
    assert len(a.lot_capped) == 1


def test_the_cap_record_names_how_far_over_the_ask_was():
    """A count of capped trades cannot tell you whether the ceiling is a rare edge or the thing
    now driving the account. The overage can.

    RED when `over_x` is computed against `contract_size` rather than the ceiling (74.26x), and
    RED when `desired_lots` divides by `max_lots` instead (7.426).
    """
    a = _lot_acct()
    a.request_fill("A", -1, entry=100.0, stop=101.0, desired_qty=74_260.0, point_value=1.0)
    rec = a.lot_capped[0]
    assert rec["desired_lots"] == 742.6
    assert rec["over_x"] == 7.426
    assert rec["granted_qty"] == 10_000.0
    assert rec["dir"] == -1


def test_the_ceiling_is_read_in_LOTS_so_contract_size_moves_it():
    """Proves the units really are converted rather than the number being compared to raw qty.

    RED when `_cap_to_max_lots` compares `desired_qty` against `self.max_lots` directly — then
    both contract sizes give the same answer and this test's two branches collapse.
    """
    big = _lot_acct(contract_size=100.0)  # 100 lots = 10,000 units
    small = _lot_acct(contract_size=1.0)  # 100 lots =    100 units
    q_big = big.request_fill("A", +1, 100.0, 99.0, desired_qty=9_000.0, point_value=1.0)
    q_small = small.request_fill("A", +1, 100.0, 99.0, desired_qty=9_000.0, point_value=1.0)
    assert q_big == 9_000.0, "90 lots — under the ceiling"
    assert q_small == 100.0, "9,000 lots — capped hard"


def test_the_same_bar_TIE_path_caps_too():
    """A leg must not dodge the ceiling by happening to fill on the same bar as another one.

    RED when the capping list-comprehension is removed from `request_fills` — the proportional
    split then hands the oversized leg its full 74,260.
    """
    a = _lot_acct()
    out = a.request_fills(
        [
            {
                "leg": "A",
                "dir": +1,
                "entry": 100.0,
                "stop": 99.0,
                "desired_qty": 74_260.0,
                "point_value": 1.0,
            },
            {
                "leg": "B",
                "dir": +1,
                "entry": 100.0,
                "stop": 99.0,
                "desired_qty": 500.0,
                "point_value": 1.0,
            },
        ]
    )
    assert out["A"] == 10_000.0, out
    assert out["B"] == 500.0, out
    assert len(a.lot_capped) == 1


def test_the_tie_path_does_not_mutate_the_callers_request_dicts():
    """The by-rank path re-reads the same dicts through `request_fill`, so capping in place would
    make the ceiling depend on which path ran first.

    RED when the list-comprehension in `request_fills` assigns into `r` instead of copying.
    """
    reqs = [
        {
            "leg": "A",
            "dir": +1,
            "entry": 100.0,
            "stop": 99.0,
            "desired_qty": 74_260.0,
            "point_value": 1.0,
        }
    ]
    _lot_acct().request_fills(reqs)
    assert reqs[0]["desired_qty"] == 74_260.0, "the caller's dict was rewritten"


def test_SoloAccount_has_infinite_room_and_STILL_carries_the_ceiling():
    """The two limits are independent, and this is the test that says so. A broker refusing a
    742-lot order does not care that the account could afford it.

    RED when `SoloAccount.__init__` stops forwarding `max_lots` to `super()`.
    """
    s = SoloAccount(balance=10_000_000.0)
    assert s.room() == float("inf")
    qty = s.request_fill("A", +1, 100.0, 99.0, desired_qty=74_260.0, point_value=1.0)
    assert qty == 10_000.0
    assert s.max_lots == 100.0


def test_SoloAccount_defaults_to_ONE_HUNDRED_lots_for_every_strategy():
    """The default itself, pinned. Aaron set it on 2026-09-02 and it applies to every bot, so a
    strategy that never mentions a ceiling still gets this one.

    RED when the default is changed to any other number, or to None.
    """
    assert SoloAccount(balance=1_000.0).max_lots == 100.0
    assert PortfolioAccount(balance=1_000.0, risk_cap_pct=0.1).max_lots == 100.0


def test_a_run_below_the_ceiling_is_byte_identical_to_its_uncapped_self():
    """The claim the docs make about stored runs: nothing below the ceiling moves. Asserted by
    running the SAME book through a capped and an uncapped account and comparing every grant.

    RED when `_cap_to_max_lots` clamps unconditionally rather than only over the ceiling.
    """
    asks = [120.0, 4_000.0, 9_999.0, 10_000.0, 33.0]
    capped = [
        SoloAccount(balance=10_000_000.0).request_fill("A", +1, 100.0, 99.0, q, 1.0) for q in asks
    ]
    free = [
        SoloAccount(balance=10_000_000.0, max_lots=None).request_fill("A", +1, 100.0, 99.0, q, 1.0)
        for q in asks
    ]
    assert capped == free == asks


# ── the external room — a live bot sharing an account across PROCESSES (2026-09-03) ────
#
# Aaron: each bot gets 5% of the account, and when one is occupying more than its share the
# others shrink to what is left rather than being refused outright. `PortfolioAccount` cannot be
# shared between OS processes, so the live side reads the BROKER and pushes the remaining dollars
# onto `SoloAccount.external_room`; the shrink then happens in the strategy's own sizing, which
# is what keeps the emulator and the broker holding the same quantity.
def test_an_UNSET_external_room_is_infinite_and_grants_in_full():
    """The control, and it covers every backtest and every solo replay — none of which knows
    anything about an account budget. RED if `None` is read as zero room."""
    s = SoloAccount(balance=10_000.0)
    assert s.external_room is None
    assert s.room() == float("inf")
    assert s.request_fill("A", +1, 100.0, 99.0, 1_000.0, 1.0) == 1_000.0


def test_a_STATED_room_REFUSES_a_fill_it_cannot_cover_rather_than_shrinking_it():
    """🔴 THIS ASSERTED A SHRINK UNTIL AN AUDIT ON 2026-09-03, AND THE SHRINK WAS INCOHERENT.

    A stacked lab account may shrink because it is the only book — the leg opens at the granted
    size and nothing else has an opinion. The LIVE caller's order is already RESTING AT THE
    BROKER by the time this runs: `sos_fade.execution` sizes a pending order from
    `equity * exec_risk_pct / dist` at PLACEMENT and never consults the account, and this gate
    runs at the FILL. So a shrink books a smaller position in the emulator than the one the
    broker just filled — and `bridge._agrees` compares DIRECTION and PRESENCE, not size, so it
    does not even halt. Two books, silently different, and every stop move and R after it
    computed against the wrong one.

    ⚠ Refusing matches `bridge._account_cap_check`, which already refuses at PLACEMENT with a
    Telegram message naming the reason. A real shrink needs the size decided where the ORDER is
    decided, which is a `strategies/` change under rule 22.
    """
    s = SoloAccount(balance=10_000.0)
    s.external_room = 400.0
    assert s.room() == 400.0
    assert s.request_fill("A", +1, 100.0, 99.0, 1_000.0, 1.0) == 0.0
    assert s.contention, "a refusal must be recorded, or nothing can report why"


def test_a_STATED_room_that_COVERS_the_fill_grants_it_in_full():
    """The other side of the same rule — a room big enough changes nothing at all."""
    s = SoloAccount(balance=10_000.0)
    s.external_room = 5_000.0
    assert s.request_fill("A", +1, 100.0, 99.0, 1_000.0, 1.0) == 1_000.0


def test_a_room_that_is_never_stated_keeps_the_flag_OFF():
    """The lab's contract. Deriving the refusal from a STATED room is what keeps every solo
    replay byte-identical — an earlier version set the flag unconditionally and a pre-existing
    test caught it."""
    s = SoloAccount(balance=10_000.0)
    assert s.all_or_nothing is False
    s.external_room = 100.0
    assert s.all_or_nothing is True


def test_a_room_of_ZERO_BLOCKS_the_fill_rather_than_opening_a_dust_position():
    """🔴 "No risk available" must mean NO TRADE, not a trade of essentially no size. A leg holds
    one position at a time, so a dust fill would occupy its only slot — the defect that silently
    retired a leg for five and a half years. RED if a zero room grants anything at all."""
    s = SoloAccount(balance=10_000.0)
    s.external_room = 0.0
    assert s.room() == 0.0
    assert s.request_fill("A", +1, 100.0, 99.0, 1_000.0, 1.0) == 0.0
    assert s.contention, "a blocked fill must be recorded, or nothing can report why"


def test_NOBODY_ASKED_and_NO_ROOM_are_different_answers():
    """Rule 1 at this seam. `None` is every backtest ever run; `0.0` is a live account with its
    budget spent. Collapsing them either refuses every backtest or grants every live trade."""
    unset, none_left = SoloAccount(balance=10_000.0), SoloAccount(balance=10_000.0)
    none_left.external_room = 0.0
    assert unset.room() != none_left.room()
    assert unset.request_fill("A", +1, 100.0, 99.0, 500.0, 1.0) == 500.0
    assert none_left.request_fill("A", +1, 100.0, 99.0, 500.0, 1.0) == 0.0


def test_this_bots_OWN_open_risk_is_subtracted_from_the_stated_room():
    """`external_room` is what the ACCOUNT has left after the OTHER bots — this bot's own
    position spends the same budget, and the live read excludes its own tickets precisely because
    they are counted here instead. RED if `reserved()` is not subtracted, which would let one bot
    hold two positions worth its whole share each."""
    s = SoloAccount(balance=10_000.0)
    s.external_room = 500.0
    assert s.request_fill("A", +1, 100.0, 99.0, 300.0, 1.0) == 300.0
    assert s.room() == 200.0, "the open position must consume the stated room"


def test_the_stated_room_never_goes_NEGATIVE():
    """A bot already over its share must read as no room, not as a negative one — a negative
    would sail through `min(desired, room)` as the smaller number and grant a negative size."""
    s = SoloAccount(balance=10_000.0)
    s.external_room = 100.0
    s.request_fill("A", +1, 100.0, 99.0, 100.0, 1.0)
    s.external_room = 50.0  # the balance fell; this bot is now over its share
    assert s.room() == 0.0


# ── sizing at PLACEMENT, not at the fill (2026-09-03) ─────────────────────────────────
#
# `request_fill` decides at the FILL, which is right for a shared backtest — one process, and
# the granted size goes straight back to the emulator that opens at it. It is wrong for a live
# bot: by then a full-size order is resting at the broker, and neither shrinking nor refusing the
# emulator's copy can change that. `affordable_qty` is the same question asked one step earlier.
def test_an_UNBUDGETED_account_returns_the_desired_size_UNTOUCHED():
    """🔴 The parity-safety test. Every solo run and every `compare_*.py` gate runs on an account
    with no budget, so this MUST be the identity function there or a stored result moves and a
    gate goes red for a reason that has nothing to do with the strategy."""
    s = SoloAccount(balance=10_000.0)
    assert s.room() == float("inf")
    assert s.affordable_qty("A", 100.0, 99.0, 1.0, 1_234.5) == 1_234.5


def test_a_size_that_FITS_the_budget_is_returned_untouched():
    s = SoloAccount(balance=10_000.0)
    s.external_room = 500.0
    assert s.affordable_qty("A", 100.0, 99.0, 1.0, 300.0) == 300.0


def test_a_size_that_does_NOT_fit_is_SHRUNK_to_exactly_the_room():
    """Aaron's rule, 2026-09-03: a bot occupying more than its share makes the others shrink.
    RED if this refuses instead of shrinking, which is what it did before this date."""
    s = SoloAccount(balance=10_000.0)
    s.external_room = 250.0
    # 1 point of stop distance at point value 1 → risk == qty. 1000 wanted, 250 affordable.
    assert s.affordable_qty("A", 100.0, 99.0, 1.0, 1_000.0) == 250.0


def test_the_shrunk_size_is_then_GRANTED_IN_FULL_at_the_fill():
    """🔴 THE ANTI-DRIFT TEST, and the reason the arithmetic lives on the account rather than in
    the strategy. A placement sized by one rule and a fill judged by another is two answers to
    one question. RED if either side's thresholds move independently of the other's."""
    s = SoloAccount(balance=10_000.0)
    s.external_room = 250.0
    fitted = s.affordable_qty("A", 100.0, 99.0, 1.0, 1_000.0)
    assert s.request_fill("A", +1, 100.0, 99.0, fitted, 1.0) == fitted, (
        "the fill must not shrink a size the placement already fitted"
    )


def test_NO_ROOM_means_place_NOTHING_rather_than_a_dust_order():
    """ "If no risk is available then we will refuse trades" — Aaron, 2026-09-03. A dust order
    would occupy the leg's only position slot, which is the defect that once retired a leg for
    five and a half years."""
    s = SoloAccount(balance=10_000.0)
    s.external_room = 0.0
    assert s.affordable_qty("A", 100.0, 99.0, 1.0, 1_000.0) == 0.0


def test_a_room_below_the_MINIMUM_GRANT_also_places_nothing():
    """The same threshold `request_fill` blocks on, so a size this places could never be refused
    at the fill for being dust. RED if the two constants drift apart."""
    s = SoloAccount(balance=10_000.0)
    s.external_room = 0.001
    assert s.affordable_qty("A", 100.0, 99.0, 1.0, 1_000.0) == 0.0


def test_an_UNPRICEABLE_trade_is_not_treated_as_an_unaffordable_one():
    """A zero stop distance cannot be converted into money. Refusing here would turn a missing
    tick value into a silent no-trade, which reads as a broken engine rather than a full budget."""
    s = SoloAccount(balance=10_000.0)
    s.external_room = 250.0
    assert s.affordable_qty("A", 100.0, 100.0, 1.0, 1_000.0) == 1_000.0


# ── who stamps the clock ──────────────────────────────────────────────────────────────
def test_an_account_does_NOT_claim_the_clock_by_default():
    """A standalone run has no simulator, so the strategy must be free to stamp its own bar time
    — the state that left every venue-ceiling record with a null time."""
    assert SoloAccount(balance=10_000.0).clock_external is False
    assert PortfolioAccount(balance=10_000.0, risk_cap_pct=0.10).clock_external is False
