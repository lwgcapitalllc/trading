"""What each bot MADE, and the rule that an account's growth may not be divided between them.

🔴 **The defect these exist against renders a confident, plausible number.** Every bot on a
balance used to report `total_pnl_pct` — the ACCOUNT's move — so a bot deployed yesterday claimed
credit for everything the account had ever done, in green, next to its name. Nothing errored.

Each test names the MUTATION that turns it red; every one was RUN rather than reasoned, because
this file's whole subject is figures that look right while being about the wrong thing.
"""

from __future__ import annotations

import json

import pytest
from services import bot_earnings as be


def _bar(ts="2026-08-01T00:00:00+00:00"):
    return {"ts": ts, "kind": "bar", "close": 4480.0}


def _open(ts="2026-08-01T00:00:00+00:00"):
    return {"ts": ts, "kind": "trade", "event": "opened", "lots": 0.3, "price": 4661.5}


def _close(pnl, r=0.5, ts="2026-08-01T02:00:00+00:00"):
    return {"ts": ts, "kind": "trade", "event": "closed", "pnl_usd": pnl, "r": r}


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """Point the reader at a scratch archive, and clear the fingerprint cache between tests.

    ⚠ The cache is module-level and keyed on bot KEY, so two tests reusing a key would serve
    each other's answer — which is a test passing on the previous test's data, the worst shape
    a fixture has.
    """
    monkeypatch.setattr(be, "ARCHIVE", tmp_path)
    be._ledger_cache.clear()

    def write(bot_key, day, rows):
        d = tmp_path / bot_key / "ledger"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"decisions-{day}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )

    return write


# ── a record that does not exist is not a record of zero ────────────────────────────────────


def test_a_bot_with_no_record_says_so_rather_than_reporting_zero(archive):
    """MUTATION: return `traded: True` with `closed_trades: 0, realised_usd: 0.0` when the
    folder is missing. RUN — red here, and it is the whole point: a bot deployed this morning
    would otherwise render `+$0.00` in the same styling as a bot that genuinely broke even, on
    the page where the difference decides whether a strategy is working."""
    out = be.read_bot_ledger("never_ran")
    assert out["traded"] is False
    assert out["closed_trades"] is None
    assert out["realised_usd"] is None
    assert out["reason"]


def test_a_record_holding_no_closed_trade_is_NOT_the_same_as_no_record(archive):
    """MUTATION: treat an empty trade list as `traded: False`. RUN — red. A bot that has been
    running for a month and taken nothing HAS been measured, and folding it in with a bot
    nobody can read destroys the one distinction this module exists to keep."""
    archive("quiet", "2026-08-01", [_bar(), _bar()])
    out = be.read_bot_ledger("quiet")
    assert out["traded"] is True
    assert out["closed_trades"] == 0
    assert out["realised_usd"] == 0.0
    assert out["records_from"] == "2026-08-01"


# ── the sum itself ──────────────────────────────────────────────────────────────────────────


def test_only_CLOSED_trades_count_and_an_open_one_contributes_nothing(archive):
    """MUTATION: drop the `event == "closed"` test and take every trade row. RUN — red, and the
    direction matters: an OPEN position has no realised result, so counting it books a profit
    the account has not been paid."""
    archive("b", "2026-08-01", [_bar(), _open(), _close(100.0, r=1.0), _open()])
    out = be.read_bot_ledger("b")
    assert out["closed_trades"] == 1
    assert out["realised_usd"] == 100.0


def test_a_scratch_counts_as_neither_a_win_nor_a_loss(archive):
    """MUTATION: `if p >= 0: wins += 1`. RUN — red. The backtest side already refuses to call a
    breakeven exit a win; two definitions of "won" in one app is how two pages disagree about
    the same trade."""
    archive("b", "2026-08-01", [_close(50.0), _close(-20.0), _close(0.0)])
    out = be.read_bot_ledger("b")
    assert (out["wins"], out["losses"]) == (1, 1)
    assert out["closed_trades"] == 3


def test_a_torn_line_is_skipped_and_does_not_blank_the_history(archive):
    """MUTATION: let `json.loads` raise. RUN — red. This file is appended to by a live bot while
    it is being read, so one half-written last line must not turn a month of history into an
    error the page renders as "no record"."""
    d = be.ARCHIVE / "b" / "ledger"
    d.mkdir(parents=True)
    (d / "decisions-2026-08-01.jsonl").write_text(
        json.dumps(_close(100.0)) + '\n{"kind": "trade", "event": "closed", "pnl_u',
        encoding="utf-8",
    )
    out = be.read_bot_ledger("b")
    assert out["closed_trades"] == 1
    assert out["realised_usd"] == 100.0


def test_the_cache_turns_over_when_the_record_GROWS(archive):
    """MUTATION: key the cache on the bot key alone. RUN — red. A live bot appends to today's
    file, so a cache that does not watch its size serves a frozen figure for ever — and a P&L
    that stops moving looks exactly like a bot that stopped trading."""
    archive("b", "2026-08-01", [_close(100.0)])
    assert be.read_bot_ledger("b")["realised_usd"] == 100.0
    archive("b", "2026-08-01", [_close(100.0), _close(25.0)])
    assert be.read_bot_ledger("b")["realised_usd"] == 125.0


# ── the account half ────────────────────────────────────────────────────────────────────────


def _bot(key, name, account=700152905, balance=14538.88, anchor=None):
    return {
        "bot_key": key,
        "name": name,
        "account": account,
        "balance": balance,
        "starting_balance": anchor,
    }


def test_two_bots_on_one_balance_are_NOT_each_credited_with_the_account_growth(archive):
    """MUTATION: set every bot's `pct_of_opening` from the account's net rather than from its
    own realised dollars. RUN — red, and this is the defect the whole module replaced. Aaron,
    2026-09-05: *"that 45% increase was only from the SOS Fade. That should still be showing
    zero percent from the extreme leg."*"""
    archive("old", "2026-07-31", [_close(1197.09, r=0.91)])
    rows = be.account_earnings(
        [_bot("old", "SOS Fade", anchor=9996.99), _bot("new", "Extreme Leg", anchor=14538.88)]
    )
    assert len(rows) == 1
    acct = rows[0]
    by_key = {b["bot_key"]: b for b in acct["bots"]}
    assert by_key["old"]["realised_usd"] == 1197.09
    # The account is up 45.4%; this bot made 12.0% of the opening. They are different numbers
    # and only one of them is about the bot.
    assert acct["net_pct"] == pytest.approx(45.43, abs=0.01)
    assert by_key["old"]["pct_of_opening"] == pytest.approx(11.97, abs=0.01)
    assert by_key["new"]["traded"] is False
    assert by_key["new"]["pct_of_opening"] is None


def test_the_growth_no_bot_recorded_is_REPORTED_not_divided_up(archive):
    """MUTATION: `unattributed_usd = 0.0`, or split the remainder between the bots pro rata.
    RUN — red. MEASURED on the live account 2026-09-05: $3,344.80 of $4,541.89 was not from a
    recorded bot trade, so a page dividing it up would credit a strategy with 74% more than it
    made."""
    archive("old", "2026-07-31", [_close(1197.09)])
    acct = be.account_earnings([_bot("old", "SOS Fade", anchor=9996.99)])[0]
    assert acct["net_usd"] == pytest.approx(4541.89, abs=0.01)
    assert acct["attributed_usd"] == pytest.approx(1197.09, abs=0.01)
    assert acct["unattributed_usd"] == pytest.approx(3344.80, abs=0.01)


def test_the_account_opening_comes_from_the_bot_with_the_EARLIEST_record(archive):
    """MUTATION: take the first bot in the list, or the largest anchor. RUN — red on both.

    Each bot anchors what the account held when IT arrived, so a bot that joined a grown
    account states a much higher number and BOTH are correct. Taking the newcomer's anchor
    reports an account up $0.00 that is really up 45% — which is exactly what this page showed
    after the 2026-09-03 rename orphaned the live bot's anchor."""
    archive("newcomer", "2026-09-04", [_close(10.0)])
    archive("oldtimer", "2026-07-31", [_close(1197.09)])
    acct = be.account_earnings(
        [
            _bot("newcomer", "Extreme Leg", anchor=14538.88),
            _bot("oldtimer", "SOS Fade", anchor=9996.99),
        ]
    )[0]
    assert acct["opening_balance"] == 9996.99
    assert acct["opening_from"] == "oldtimer"


def test_an_account_nobody_has_anchored_REFUSES_rather_than_dividing_by_nothing(archive):
    """MUTATION: fall back to `opening = balance`, or to 0. RUN — red. `balance` reports a flat
    account that may have doubled; 0 is a division by nothing. Both are answers nobody
    measured, and the note is what sends the reader at the real cause."""
    acct = be.account_earnings([_bot("b", "B", anchor=None)])[0]
    assert acct["opening_balance"] is None
    assert acct["net_usd"] is None and acct["net_pct"] is None
    assert acct["opening_note"]


def test_a_bot_with_no_account_is_not_grouped_under_one(archive):
    """MUTATION: `by_account.setdefault(b.get("account"), ...)` with no truthiness test. RUN —
    red. A benched bot has no account, and inventing a group for it puts a balance and a net on
    a row that trades nothing."""
    assert be.account_earnings([_bot("b", "B-LEG", account=None, balance=None)]) == []


def test_a_bot_whose_record_has_not_arrived_is_NAMED_so_the_split_reads_as_a_floor(archive):
    """MUTATION: drop `bots_without_record`. RUN — red. While it is non-empty the attributed
    figure is a FLOOR, and a page that cannot say so presents an incomplete split as a
    complete one — the same collapse as rendering an unread balance as zero."""
    archive("old", "2026-07-31", [_close(100.0)])
    acct = be.account_earnings(
        [_bot("old", "SOS Fade", anchor=9996.99), _bot("new", "Extreme Leg", anchor=14538.88)]
    )[0]
    assert acct["bots_without_record"] == ["new"]


def test_one_pot_of_money_is_read_once_even_when_a_neighbour_reports_nothing(archive):
    """MUTATION: sum the balances. RUN — red at exactly 2x.

    🔴 **The first version of this test could not catch that mutation and passed against it.**
    It gave one bot `balance=None`, so summing the non-null balances returned the same figure
    as taking the first — *"this is summed"* and *"this is read once"* were the same assertion.
    Both cases are asserted now: two bots BOTH reporting is what makes the sum visible, and the
    silent neighbour is a separate check. Same shape as the period window's scale-of-1 cases."""
    both = be.account_earnings(
        [
            _bot("a", "A", balance=14538.88, anchor=9996.99),
            _bot("b", "B", balance=14538.88, anchor=9996.99),
        ]
    )[0]
    assert both["balance"] == 14538.88  # not 29,077.76

    quiet = be.account_earnings(
        [
            _bot("a", "A", balance=None, anchor=9996.99),
            _bot("b", "B", balance=14538.88, anchor=9996.99),
        ]
    )[0]
    assert quiet["balance"] == 14538.88
