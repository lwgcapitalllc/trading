"""A deposit is not a return — `algos/shared/account_flows.py`.

🔴 **The bug these are written from (2026-09-12).** A $9,860.51 transfer into live account
34957946 read as **+2,181.67%** on the Bots page, the Overview and Telegram's /balance, over two
bots that had not traded. The return was `(balance - anchor) / anchor`, so every dollar arriving
after the anchor read as profit and every dollar taken out as a loss.

The first two cases are the REAL shapes of the two accounts read off the box that day (read-only):
live holds two transfers in and nothing else, demo one deposit and then only trades. So the module
is pinned against the accounts it was written for, not against a story about them.

Every test names the mutation that turns it red, and each one was RUN.
"""

import sys
from itertools import count
from pathlib import Path
from types import SimpleNamespace

import pytest

_SHARED = Path(__file__).resolve().parent.parent / "shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from account_flows import DEAL_BALANCE, DEAL_BONUS, DEAL_CREDIT, account_return  # noqa: E402

_BUY, _SELL = 0, 1
_tickets = count(1)


def _deal(t, kind, profit=0.0, commission=0.0, swap=0.0, fee=0.0):
    """Shaped like MT5's `TradeDeal`: `time_msc` orders it, `ticket` breaks a tie, `type` says what
    it is, and the four money fields are what it did to the balance."""
    return SimpleNamespace(
        time_msc=t,
        ticket=next(_tickets),
        type=kind,
        profit=profit,
        commission=commission,
        swap=swap,
        fee=fee,
    )


def _deposit(t, amount):
    """A deposit, or a withdrawal when `amount` is negative — MT5 books both as BALANCE."""
    return _deal(t, DEAL_BALANCE, profit=amount)


def _trade(t, pnl, **costs):
    return _deal(t, _SELL, profit=pnl, **costs)


# ── the two accounts it was written for ────────────────────────────────────────


def test_the_live_account_that_read_plus_2181_percent_reads_flat():
    """Two transfers in and not one trade, so trading made nothing.

    Red under: dropping BALANCE from `FLOW_TYPES` (no deposit is then on record, and it refuses).
    """
    r = account_return([_deposit(1, 451.97), _deposit(2, 9_860.51)], 10_312.48)

    assert r.capital_in == 10_312.48
    assert r.pnl_usd == 0.0
    assert r.return_pct == 0.0
    assert r.flows == 2
    assert r.reason is None


def test_the_demo_account_reads_what_it_made_on_its_one_deposit():
    """One deposit and then only trades is one period, so the chained return equals the plain one:
    5,844.46 on 10,000.

    Red under: reporting the growth FACTOR rather than the growth (dropping the `- 1.0`).
    """
    deals = [
        _deposit(1, 10_000.00),
        _trade(2, 3_000.00, commission=-6.0),
        _trade(3, -1_143.54, commission=-6.0),
        _trade(4, 4_000.00),
    ]
    r = account_return(deals, 15_844.46)

    assert r.capital_in == 10_000.00
    assert r.pnl_usd == 5_844.46
    assert r.return_pct == 58.44


# ── what makes it right ────────────────────────────────────────────────────────


def test_a_deposit_after_a_gain_neither_counts_as_return_nor_dilutes_it():
    """The case the fix exists for. 452 made +10% (to 497.20), then 10,000 arrived, then the whole
    10,497.20 made +5%. The strategy did +10% then +5%: chained, +15.5%.

    The two wrong answers it replaces: on what went in (570.06 / 10,452 = +5.45%) the deposit
    DILUTES the earlier gain, and on the opening balance (570.06 / 452 = +126%) it is very nearly
    the bug itself.

    Red under: not closing the period at a deposit (the growth is then only taken at the end).
    """
    deals = [_deposit(1, 452.00), _trade(2, 45.20), _deposit(3, 10_000.00), _trade(4, 524.86)]
    r = account_return(deals, 11_022.06)

    assert r.return_pct == 15.5
    assert r.pnl_usd == 570.06
    assert r.capital_in == 10_452.00


def test_a_withdrawal_is_not_a_loss():
    """1,000 made +10%, 500 came out, and the 600 left made +10% again: chained +21%. Net of the
    withdrawal 500 went in, and trading made 160.

    Red under: counting only money IN as capital (the withdrawal then lands in the P&L).
    """
    deals = [_deposit(1, 1_000), _trade(2, 100), _deposit(3, -500), _trade(4, 60)]
    r = account_return(deals, 660)

    assert r.return_pct == 21.0
    assert r.capital_in == 500
    assert r.pnl_usd == 160


def test_broker_CREDIT_is_neither_capital_nor_profit():
    """MT5 keeps credit in its own field, outside the balance, so the broker's 1,100 here excludes
    the 500 of credit and a credit deal must move neither figure.

    Red under: not skipping CREDIT (the rebuild reaches 1,600 against 1,100 and refuses).
    """
    deals = [_deposit(1, 1_000), _deal(2, DEAL_CREDIT, profit=500), _trade(3, 100)]
    r = account_return(deals, 1_100)

    assert r.return_pct == 10.0
    assert r.capital_in == 1_000


def test_a_BONUS_is_money_put_in_not_money_earned():
    """Red under: dropping BONUS from `FLOW_TYPES` (it would read as trading, +32%)."""
    deals = [_deposit(1, 1_000), _deal(2, DEAL_BONUS, profit=200), _trade(3, 120)]
    r = account_return(deals, 1_320)

    assert r.capital_in == 1_200
    assert r.pnl_usd == 120
    assert r.return_pct == 10.0


def test_commission_swap_and_fee_are_what_trading_made():
    """Every cost a trade carries is part of its result, not money moved in or out.

    Red under: dropping `fee` from `_money` (the rebuild then misses the broker's balance by 0.50
    and refuses).
    """
    deals = [
        _deposit(1, 1_000),
        _deal(2, _BUY, commission=-1.0),
        _deal(3, _SELL, profit=50.0, swap=-2.0, fee=-0.5),
    ]
    r = account_return(deals, 1_046.5)

    assert r.pnl_usd == 46.5
    assert r.return_pct == 4.65


def test_the_deals_are_put_in_time_order_whatever_order_they_arrive_in():
    """Deposits and trades are interleaved, so an out-of-order history credits a trade to the wrong
    period. MT5 answers in time order today and nothing promises it.

    Red under: dropping the sort (this reversed history then reads +0.43%).
    """
    deals = [_deposit(1, 452.00), _trade(2, 45.20), _deposit(3, 10_000.00), _trade(4, 524.86)]

    assert account_return(list(reversed(deals)), 11_022.06).return_pct == 15.5


def test_two_deals_in_one_millisecond_are_ordered_by_ticket():
    """MT5 numbers deals in sequence, so inside one millisecond the ticket is the order.

    Red under: sorting on time alone (a stable sort then keeps the trade before its deposit and
    the account reads flat).
    """
    first, second = _deposit(7, 1_000), _trade(7, 100)

    assert account_return([second, first], 1_100).return_pct == 10.0


def test_an_account_emptied_and_refilled_is_fine_when_nothing_traded_while_empty():
    """1,000... no: 100 made +10%, all 110 came out, 500 went in and made +10%. The empty stretch
    between is not a period, and must not stop the two either side of it chaining.

    Red under: refusing every period that opened at zero, traded or not.
    """
    deals = [_deposit(1, 100), _trade(2, 10), _deposit(3, -110), _deposit(4, 500), _trade(5, 50)]
    r = account_return(deals, 550)

    assert r.return_pct == 21.0
    assert r.capital_in == 490
    assert r.pnl_usd == 60


# ── when it must say nothing ───────────────────────────────────────────────────


def test_money_made_while_the_account_held_nothing_is_refused():
    """Everything withdrawn, then a trade booked +5: there is no balance that return is ON.

    Red under: letting a period that opened at zero close without a word (it then reads 0.0%).
    """
    r = account_return([_deposit(1, 100), _deposit(2, -100), _trade(3, 5)], 5.0)

    assert r.return_pct is None
    assert "held nothing" in r.reason


@pytest.mark.parametrize(
    "deals,balance,why",
    [
        (None, 1_000.0, "history could not be read"),
        ([_deposit(1, 1_000)], None, "balance could not be read"),
        ([_trade(1, 50)], 50.0, "no deposit"),
        ([_deposit(1, 1_000), _trade(2, 50)], 1_100.0, "while the broker reports"),
    ],
)
def test_it_REFUSES_rather_than_state_a_number_it_cannot_stand_behind(deals, balance, why):
    """Rule 1: all three figures `None` together, with the reason. The last case is a deposit the
    history did not return, and a return off that history is a confident wrong number.

    Red under: widening `RECONCILE_TOLERANCE` to 100 (the missing-history case then reports), and
    under removing the no-deposit refusal (a trade-only history then reads 0.0%).
    """
    r = account_return(deals, balance)

    assert (r.capital_in, r.pnl_usd, r.return_pct) == (None, None, None)
    assert why in r.reason
