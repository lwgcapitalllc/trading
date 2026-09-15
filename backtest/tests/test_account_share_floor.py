"""The half-share minimum and the market-bot shrink (2026-09-15).

Aaron: a bot short of room trades the difference, down to half its own size; below that it is
refused. Every case uses a $10,000 balance, a 10% ($1,000) cap and $10 stops, so 1 unit = $10.
"""

import pytest

from backtest.portfolio.account import SHARED_MIN_GRANT_FRAC, PortfolioAccount, SoloAccount


def _acct(frac=0.5):
    return PortfolioAccount(balance=10_000.0, risk_cap_pct=0.10, min_grant_frac=frac)


def _hold(acct, leg, risk_usd):
    """Another leg holding `risk_usd` of risk to a $10 stop."""
    assert acct.request_fill(leg, 1, 100.0, 90.0, risk_usd / 10.0, 1.0) == pytest.approx(
        risk_usd / 10.0
    )


def test_aarons_example_8_percent_open_leaves_2_which_is_under_half_of_5_so_REFUSED():
    """3% + 5% open, the third bot wants 5%: 2% left is under half its share (2.5%)."""
    a = _acct()
    _hold(a, "one", 300.0)
    _hold(a, "two", 500.0)
    assert a.affordable_qty("three", 100.0, 90.0, 1.0, 50.0) == 0.0
    assert a.request_fill("three", 1, 100.0, 90.0, 50.0, 1.0) == 0.0
    assert a.contention[-1]["blocked"] is True


def test_room_of_at_least_half_is_TAKEN_at_the_smaller_size():
    a = _acct()
    _hold(a, "one", 700.0)  # 3% left, over half of 5%
    assert a.affordable_qty("three", 100.0, 90.0, 1.0, 50.0) == pytest.approx(30.0)
    assert a.request_fill("three", 1, 100.0, 90.0, 50.0, 1.0) == pytest.approx(30.0)


def test_EXACTLY_half_is_taken_not_refused_by_the_last_bit_of_a_float():
    a = _acct()
    _hold(a, "one", 750.0)
    assert a.affordable_qty("three", 100.0, 90.0, 1.0, 50.0) == pytest.approx(25.0)


def test_both_others_at_BREAKEVEN_give_the_third_its_FULL_share():
    a = _acct()
    _hold(a, "one", 500.0)
    _hold(a, "two", 500.0)
    a.update_stop("one", 100.0)
    a.update_stop("two", 100.0)
    assert a.affordable_qty("three", 100.0, 90.0, 1.0, 50.0) == pytest.approx(50.0)


def test_the_minimum_is_OFF_by_default_so_no_stored_stack_moves():
    a = PortfolioAccount(balance=10_000.0, risk_cap_pct=0.10)
    _hold(a, "one", 800.0)
    assert a.affordable_qty("three", 100.0, 90.0, 1.0, 50.0) == pytest.approx(20.0)


def test_a_SOLO_replay_has_no_minimum_and_a_LIVE_shared_bot_has_half():
    s = SoloAccount(balance=10_000.0)
    assert s.min_grant_frac == 0.0, "a solo replay and every parity gate must be untouched"
    s.external_room = 200.0
    assert s.min_grant_frac == SHARED_MIN_GRANT_FRAC == 0.5
    assert s.affordable_qty("bot", 100.0, 90.0, 1.0, 50.0) == 0.0  # $200 < half of $500
    s.external_room = 300.0
    assert s.affordable_qty("bot", 100.0, 90.0, 1.0, 50.0) == pytest.approx(30.0)


def test_a_MARKET_bot_sharing_an_account_is_SHRUNK_at_its_fill_not_refused():
    """A market bot's fill is its placement, so a shrink there reaches the broker as the size the
    bot holds. RED before `fills_at_placement`: refused, because a stated room refused every
    shrink at the fill."""
    s = SoloAccount(balance=10_000.0)
    s.external_room = 300.0
    assert s.request_fill("bot", 1, 100.0, 90.0, 50.0, 1.0) == 0.0, "a RESTING bot still refuses"
    s2 = SoloAccount(balance=10_000.0)
    s2.external_room = 300.0
    s2.fills_at_placement = True
    assert s2.request_fill("bot", 1, 100.0, 90.0, 50.0, 1.0) == pytest.approx(30.0)


def test_a_MARKET_bot_under_half_is_still_refused_at_its_fill():
    s = SoloAccount(balance=10_000.0)
    s.external_room = 200.0
    s.fills_at_placement = True
    assert s.request_fill("bot", 1, 100.0, 90.0, 50.0, 1.0) == 0.0
