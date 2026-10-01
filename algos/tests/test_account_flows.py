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


# ── a deal the BROKER lost (2026-10-01) ────────────────────────────────────────
#
# 🔴 Live 34957946 paid a $0.35 entry commission at 07:25:29 UTC and MT5 holds no entry deal for
# that position, so every rebuild sat $0.35 above the broker and the return was refused all day.
# The deals below are the account's real ones, read off the live terminal (read-only) that day.

_LOST_POS = 368940178
_LOST = {"position": _LOST_POS, "money": -0.35, "time_msc": 1_790_850_329_266, "why": "probe"}


def _live_2026_10_01():
    flows = [
        _deposit(1_789_020_756_147, 451.97),
        _deposit(1_789_197_824_182, 9_860.51),
        _deposit(1_789_199_393_146, -10_312.48),  # everything out...
        _deposit(1_789_228_078_813, 10_311.48),  # ...and back in, less $1
    ]
    before = [_trade(1_790_000_000_000, -24.42)]  # what trading had made by 07:14 that day
    today = [
        SimpleNamespace(
            **vars(_trade(1_790_853_123_237, 12.25, commission=-0.35)),
            position_id=_LOST_POS,
            entry=1,
        ),
        SimpleNamespace(
            **vars(_deal(1_790_853_424_870, _BUY, commission=-0.17)), position_id=368996332, entry=0
        ),
        SimpleNamespace(
            **vars(_trade(1_790_871_302_449, 218.11, commission=-0.17)),
            position_id=368996332,
            entry=1,
        ),
    ]
    return flows + before + today


def test_the_lost_entry_deal_refuses_without_its_correction():
    """What the bot logged all day: the rebuild is $0.35 above the broker."""
    r = account_return(_live_2026_10_01(), 10_516.38)
    assert r.return_pct is None
    assert "10,516.73" in r.reason and "10,516.38" in r.reason


def test_with_the_recorded_correction_the_true_return_is_stated():
    """+$204.90 on $10,311.48 put in — never +2,226.8% on the first $451.97.
    MUTATION: drop `deals.extend(missing)` -> refused, red (watched 2026-10-01)."""
    r = account_return(_live_2026_10_01(), 10_516.38, corrections=[_LOST])
    assert r.reason is None, r.reason
    assert r.capital_in == 10_311.48
    assert r.pnl_usd == 204.90
    assert r.return_pct == 1.99


def test_the_correction_steps_aside_once_the_broker_restores_the_deal():
    """Counting both would be the money twice. MUTATION: skip the entered-position check -> red."""
    restored = SimpleNamespace(
        **vars(_deal(1_790_850_329_266, _BUY, commission=-0.35)), position_id=_LOST_POS, entry=0
    )
    r = account_return([*_live_2026_10_01(), restored], 10_516.38, corrections=[_LOST])
    assert r.reason is None, r.reason
    assert r.pnl_usd == 204.90


def test_a_correction_is_never_a_deposit():
    """It stands in for a TRADE deal. MUTATION: give `_Missing` type BALANCE -> capital_in moves."""
    r = account_return(_live_2026_10_01(), 10_516.38, corrections=[_LOST])
    assert r.flows == 4


def test_an_unreadable_corrections_file_refuses_rather_than_assuming_none():
    """Rule 1: *could not read the list* is not *the list is empty*."""
    r = account_return(_live_2026_10_01(), 10_516.38, corrections=None)
    assert r.return_pct is None and "could not be read" in r.reason


def test_a_malformed_correction_refuses():
    r = account_return(_live_2026_10_01(), 10_516.38, corrections=[{"position": "x"}])
    assert r.return_pct is None and "malformed" in r.reason


# ── the file the runner reads them from ────────────────────────────────────────


def _loader(monkeypatch, tmp_path, text):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "live"))
    import repo_paths
    import runner as runner_mod

    monkeypatch.setattr(repo_paths, "ALGOS_ROOT", tmp_path)
    if text is not None:
        (tmp_path / "markets" / "fx").mkdir(parents=True)
        (tmp_path / "markets" / "fx" / "history_corrections.json").write_text(text)
    return runner_mod._history_corrections


def test_no_corrections_file_is_an_account_with_nothing_recorded(monkeypatch, tmp_path):
    assert _loader(monkeypatch, tmp_path, None)(34957946) == []


def test_a_corrections_file_that_will_not_parse_is_cannot_ask(monkeypatch, tmp_path):
    """MUTATION: answer [] on a ValueError -> red."""
    assert _loader(monkeypatch, tmp_path, "{not json")(34957946) is None


def test_the_committed_file_carries_the_live_hole_and_reconciles_it():
    """The real file, against the real deals: what the live bots will state after a pull."""
    import json

    raw = json.loads(
        (Path(__file__).resolve().parents[1] / "markets/fx/history_corrections.json").read_text()
    )
    rows = raw["accounts"]["34957946"]
    r = account_return(_live_2026_10_01(), 10_516.38, corrections=rows)
    assert (r.reason, r.pnl_usd, r.return_pct) == (None, 204.90, 1.99)
