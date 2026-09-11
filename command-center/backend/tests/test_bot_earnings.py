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


def _start(account=700152905, ts="2026-07-31T00:00:00+00:00"):
    """A run's startup naming its account. Every real run writes one, and a trade is placed on
    the account of the latest startup before it — so an account-level fixture without one is
    SIMPLER than production and its trades belong to no account (rule 13 from the other end)."""
    return {"ts": ts, "kind": "event", "event": "startup", "account": account}


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """Point the reader at a scratch archive, and clear the fingerprint cache between tests.

    ⚠ The cache is module-level and keyed on bot KEY, so two tests reusing a key would serve
    each other's answer — which is a test passing on the previous test's data, the worst shape
    a fixture has.
    """
    monkeypatch.setattr(be, "ARCHIVE", tmp_path)
    be._ledger_cache.clear()
    be._readings_cache.clear()

    def write(bot_key, day, rows, kind="decisions"):
        d = tmp_path / bot_key / "ledger"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{kind}-{day}.jsonl").write_text(
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


def _bot(key, name, account=700152905, balance=14538.88, anchor=None, strategy=None):
    return {
        "bot_key": key,
        "name": name,
        "account": account,
        "balance": balance,
        "starting_balance": anchor,
        # The package it runs. `None` = not known, which carries no history — see `_carry_on`.
        "strategy": strategy,
    }


def test_two_bots_on_one_balance_are_NOT_each_credited_with_the_account_growth(archive):
    """MUTATION: set every bot's `pct_of_opening` from the account's net rather than from its
    own realised dollars. RUN — red, and this is the defect the whole module replaced. Aaron,
    2026-09-05: *"that 45% increase was only from the SOS Fade. That should still be showing
    zero percent from the extreme leg."*"""
    archive("old", "2026-07-31", [_start(), _close(1197.09, r=0.91)])
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
    archive("old", "2026-07-31", [_start(), _close(1197.09)])
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


# ── the two clocks ──────────────────────────────────────────────────────────────────────────
#
# 🔴 **The balance is read live over SSH and the archive is behind by however long ago the box
# committed AND this machine pulled — MEASURED at 66 minutes on 2026-09-09, with no upper bound.**
# A trade closed inside that gap sits in the balance and in no bot's row, so the bot under-reports
# by exactly its profit and the remainder line over-reports by the same amount. It happened: the
# extreme leg's $1,305.58 target rendered as money nobody's bot made.


def _now(iso="2026-09-09T03:21:00+00:00"):
    return be.datetime.fromisoformat(iso)


def test_the_reach_is_the_newest_RECORD_not_the_day_in_the_filename(archive):
    """MUTATION: return `records_through` as `records_to` (the filename day). RUN — red.

    The whole defect is that today's file always read as *recorded through today* while the
    newest line inside it could be an hour old — what was REQUESTED of the archive reported as
    what arrived."""
    archive(
        "b",
        "2026-09-09",
        [_close(100.0, ts="2026-09-09T01:00:00+00:00"), _bar("2026-09-09T02:15:05+00:00")],
    )
    out = be.read_bot_ledger("b")
    assert out["records_to"] == "2026-09-09"
    assert out["records_through"] == "2026-09-09T02:15:05+00:00"


def test_a_TORN_last_line_does_not_blank_the_reach(archive):
    """MUTATION: read only the final line and give up when it does not parse. RUN — red.

    A live bot is appending while this is read, so the last line is routinely half-written —
    and a reach of `None` there reports the lag as unmeasurable on the most ordinary file in
    the archive."""
    d = be.ARCHIVE / "b" / "ledger"
    d.mkdir(parents=True)
    (d / "decisions-2026-09-09.jsonl").write_text(
        json.dumps(_bar("2026-09-09T02:15:05+00:00")) + '\n{"ts": "2026-09-09T02:30',
        encoding="utf-8",
    )
    assert be.read_bot_ledger("b")["records_through"] == "2026-09-09T02:15:05+00:00"


def test_a_reach_that_cannot_be_READ_is_None_and_never_a_fabricated_instant(archive):
    """MUTATION: fall back to the filename day, or to `datetime.now()`. RUN — red on both.

    *We cannot tell how fresh this is* and *this is fresh* must not be the same value — the
    caller reports the first as an unknown lag, which is the thing a reader needs to see."""
    d = be.ARCHIVE / "b" / "ledger"
    d.mkdir(parents=True)
    (d / "decisions-2026-09-09.jsonl").write_text("not json\nalso not json\n", encoding="utf-8")
    out = be.read_bot_ledger("b")
    assert out["records_through"] is None
    assert out["records_to"] == "2026-09-09"


def test_a_trade_the_ARCHIVE_has_not_caught_up_to_is_still_counted(archive):
    """MUTATION: ignore `live_trades` and sum the archive alone. RUN — red at $0.00 against
    $1,305.58 — which is the live case exactly: the extreme leg's 2026-09-09 target was in the
    balance and in no bot's row, and rendered as a manual fill or a deposit."""
    archive("b", "2026-09-09", [_bar("2026-09-09T02:15:05+00:00")])
    fresh = _close(1305.58, r=2.1, ts="2026-09-09T07:15:02+00:00")
    fresh["ticket"] = 367577331
    out = be.read_bot_ledger("b", [fresh])
    assert out["closed_trades"] == 1
    assert out["realised_usd"] == 1305.58
    assert out["record_source"] == "live"


def test_a_trade_in_BOTH_the_archive_and_the_box_is_counted_ONCE(archive):
    """MUTATION: append the live rows without deduping. RUN — red at double.

    The archive is a COPY of the box's file, so the overlap is the ordinary case rather than an
    edge one — every synced trade is in both, and a page reporting each of them twice is worse
    than one reporting them an hour late."""
    row = _close(1305.58, r=2.1, ts="2026-09-09T07:15:02+00:00")
    row["ticket"] = 367577331
    archive("b", "2026-09-09", [row])
    out = be.read_bot_ledger("b", [dict(row)])
    assert out["closed_trades"] == 1
    assert out["realised_usd"] == 1305.58


def test_the_box_answering_with_NOTHING_is_not_the_box_failing_to_answer(archive):
    """MUTATION: treat `live_trades=None` as `[]`. RUN — red on `record_source`.

    `None` = the box could not be asked, so this figure is as stale as the last sync. `[]` = it
    answered and this bot has closed nothing in the window, which is the ordinary state of a bot
    that has not traded this month. Only one of them makes the split provisional."""
    archive("b", "2026-09-09", [_bar("2026-09-09T02:15:05+00:00")])
    assert be.read_bot_ledger("b", [])["record_source"] == "live"
    assert be.read_bot_ledger("b", None)["record_source"] == "archive"


def test_a_bot_with_NO_archive_but_a_live_record_is_not_reported_as_untraded(archive):
    """MUTATION: return the no-record answer whenever the archive folder is missing. RUN — red.

    A bot registered since the last sync has a real record sitting in the response — reporting
    it as untraded while its own trades are right there is the reverse of this module's rule
    about zero, and just as wrong."""
    row = _close(400.0, ts="2026-09-09T07:15:02+00:00")
    row["ticket"] = 42
    out = be.read_bot_ledger("brand_new", [row])
    assert out["traded"] is True
    assert out["realised_usd"] == 400.0
    assert out["records_from"] is None


def test_the_page_SAYS_the_split_is_provisional_when_a_record_was_not_read_live(archive):
    """MUTATION: always report `records_live: True`, or drop the note. RUN — red on both.

    This is the fix itself. Without it a stale read and a real attribution gap are the same
    pixel: the remainder line names a manual fill, a deposit or an old trade — three real
    causes — and said exactly that for a trade that had simply not synced yet."""
    archive("b", "2026-09-09", [_bar("2026-09-09T02:15:05+00:00")])
    acct = be.account_earnings(
        [_bot("b", "B", anchor=9996.99)], as_of=_now("2026-09-09T03:21:00+00:00")
    )[0]
    assert acct["records_live"] is False
    assert acct["attribution_lag_seconds"] == pytest.approx(66 * 60, abs=60)
    assert "66 minutes behind" in acct["attribution_note"]


def test_a_record_read_LIVE_carries_no_caveat_at_all(archive):
    """MUTATION: emit the note unconditionally. RUN — red.

    A caveat printed on every split is one nobody reads by the second day, and it would be
    stating a lag that is not there — the two halves genuinely were read at the same moment."""
    archive("b", "2026-09-09", [_bar("2026-09-09T02:15:05+00:00")])
    acct = be.account_earnings(
        [{**_bot("b", "B", anchor=9996.99), "live_trades": []}], as_of=_now()
    )[0]
    assert acct["records_live"] is True
    assert acct["attribution_lag_seconds"] == 0.0
    assert acct["attribution_note"] is None


def test_the_WORST_lag_is_reported_never_the_average_or_the_first(archive):
    """MUTATION: take the mean, or the first stale bot's lag. RUN — red on both.

    The question is whether ANY trade could be missing, so one bot an hour behind makes the
    whole split provisional however fresh its neighbour is. An average buries exactly the bot
    the reader needs to know about."""
    archive("fresh", "2026-09-09", [_bar("2026-09-09T03:20:00+00:00")])
    archive("stale", "2026-09-09", [_bar("2026-09-09T00:21:00+00:00")])
    acct = be.account_earnings(
        [_bot("fresh", "F", anchor=9996.99), _bot("stale", "S", anchor=9996.99)],
        as_of=_now("2026-09-09T03:21:00+00:00"),
    )[0]
    assert acct["attribution_lag_seconds"] == pytest.approx(3 * 60 * 60, abs=60)


def test_a_lag_that_cannot_be_MEASURED_says_so_rather_than_reading_as_fresh(archive):
    """MUTATION: fall back to `0.0` when the reach is unreadable. RUN — red.

    A zero lag is the most reassuring answer available and here it is the one that cannot be
    supported — the same rule as the reach itself, one level up."""
    d = be.ARCHIVE / "b" / "ledger"
    d.mkdir(parents=True)
    (d / "decisions-2026-09-09.jsonl").write_text("not json\n", encoding="utf-8")
    acct = be.account_earnings([_bot("b", "B", anchor=9996.99)], as_of=_now())[0]
    assert acct["records_live"] is False
    assert acct["attribution_lag_seconds"] is None
    assert "could not be read" in acct["attribution_note"]


# ── a trade belongs to the account it was MADE on (2026-09-11) ───────────────────────────────

_DEMO, _LIVE = 700152905, 34957946


def test_a_trade_is_credited_to_the_account_it_was_MADE_on_never_the_bots_current_one(archive):
    """🔴 The day the demo set went live, the live account showed the bots' DEMO trades as its own
    — +264% on a $451.97 account that had not traded. The trade happened on demo; it stays there,
    as a history row saying where the bot went.

    MUTATION: credit every trade to the bot's current account (no placing) → red.
    """
    archive(
        "sos",
        "2026-08-26",
        [
            _start(_DEMO, "2026-08-12T16:00:00+00:00"),
            _close(1197.09, r=0.91, ts="2026-08-26T02:15:00+00:00"),
            _start(_LIVE, "2026-09-11T00:13:59+00:00"),
        ],
    )
    rows = {
        e["account"]: e
        for e in be.account_earnings(
            [_bot("sos", "SOS Fade", account=_LIVE, balance=451.97, anchor=451.97)]
        )
    }
    live = rows[_LIVE]["bots"][0]
    assert (live["closed_trades"], live["realised_usd"], live["former"]) == (0, 0.0, False)
    assert rows[_LIVE]["unattributed_usd"] == 0.0
    demo = rows[_DEMO]["bots"][0]
    assert (demo["closed_trades"], demo["realised_usd"]) == (1, 1197.09)
    assert demo["former"] is True and demo["moved_to"] == _LIVE


def test_startups_are_read_from_the_HEALTH_files_too(archive):
    """They moved there on 2026-08-05; reading the decision files alone left a month of trades on
    no account at all. MUTATION: skip the health files → the trade is unplaced → red."""
    archive("b", "2026-08-26", [_start(_DEMO, "2026-08-12T16:00:00+00:00")], kind="health")
    archive("b", "2026-08-26", [_close(50.0, ts="2026-08-26T02:15:00+00:00")])
    out = be.read_bot_ledger("b", account=_DEMO)
    assert (out["closed_trades"], out["unplaced_trades"]) == (1, 0)


def test_a_run_begun_since_the_last_sync_is_placed_by_the_BOX_startups(archive):
    """The archive knows only the demo run; the live run's startup is on the box alone. Without
    the box's startups its trade would be placed on demo. MUTATION: ignore `live_starts` → red."""
    archive("b", "2026-09-10", [_start(_DEMO, "2026-09-05T00:00:00+00:00")])
    trade = {**_close(20.0, ts="2026-09-11T03:00:00+00:00"), "ticket": 7}
    starts = [("2026-09-11T00:13:59+00:00", _LIVE)]
    live = be.read_bot_ledger("b", [trade], account=_LIVE, live_starts=starts)
    demo = be.read_bot_ledger("b", [trade], account=_DEMO, live_starts=starts)
    assert (live["closed_trades"], demo["closed_trades"]) == (1, 0)


def test_a_trade_no_startup_precedes_is_COUNTED_never_credited_to_a_guess(archive):
    """MUTATION: place an unplaceable trade on the asked account → red."""
    archive(
        "b",
        "2026-08-01",
        [_close(10.0, ts="2026-08-01T02:00:00+00:00"), _start(_DEMO, "2026-08-02T00:00:00+00:00")],
    )
    out = be.read_bot_ledger("b", account=_DEMO)
    assert (out["closed_trades"], out["unplaced_trades"]) == (0, 1)


def test_an_account_only_DEPARTED_bots_traded_on_carries_no_balance_net_or_remainder(archive):
    """Nothing reads its balance any more, so every figure off the account's growth is withheld
    and the note says why — the trades alone are the record."""
    archive(
        "b",
        "2026-08-26",
        [
            _start(_DEMO, "2026-08-12T16:00:00+00:00"),
            _close(5.0, ts="2026-08-26T02:00:00+00:00"),
            _start(_LIVE, "2026-09-11T00:00:00+00:00"),
        ],
    )
    rows = {
        e["account"]: e
        for e in be.account_earnings([_bot("b", "B", account=_LIVE, balance=451.97, anchor=451.97)])
    }
    demo = rows[_DEMO]
    assert (demo["balance"], demo["net_usd"], demo["unattributed_usd"]) == (None, None, None)
    assert "No bot is on this account now" in demo["opening_note"]


def test_a_departed_bots_trades_REFUSE_the_remainder_where_bots_still_trade(archive):
    """With NO balance reading to take the account's own opening from, the opening falls back to
    the current bot's anchor — and whether the departed bot's trades fall inside that window cannot
    be told, so the remainder is withheld rather than guessed. MUTATION: drop the refusal → red."""
    archive(
        "gone",
        "2026-08-26",
        [
            _start(_DEMO, "2026-08-12T00:00:00+00:00"),
            _close(5.0, ts="2026-08-26T02:00:00+00:00"),
            _start(_LIVE, "2026-09-11T00:00:00+00:00"),
        ],
    )
    archive("stay", "2026-08-20", [_start(_DEMO, "2026-08-20T00:00:00+00:00")])
    rows = {
        e["account"]: e
        for e in be.account_earnings(
            [
                _bot("gone", "Gone", account=_LIVE, balance=451.97, anchor=451.97),
                _bot("stay", "Stay", account=_DEMO, balance=10100.0, anchor=10000.0),
            ]
        )
    }
    assert rows[_DEMO]["net_usd"] == 100.0
    assert rows[_DEMO]["unattributed_usd"] is None


def test_a_departed_bot_is_never_given_a_share_of_a_CURRENT_bots_anchor(archive):
    """With no reading of its own opening, the account's opening is the current bot's anchor, and
    dividing a departed bot's dollars by it mixes two starts. MUTATION: drop the `former` guard on
    `pct_of_opening` → red."""
    archive(
        "gone",
        "2026-08-26",
        [
            _start(_DEMO, "2026-08-12T00:00:00+00:00"),
            _close(5.0, ts="2026-08-26T02:00:00+00:00"),
            _start(_LIVE, "2026-09-11T00:00:00+00:00"),
        ],
    )
    archive("stay", "2026-08-20", [_start(_DEMO, "2026-08-20T00:00:00+00:00")])
    rows = {
        e["account"]: e
        for e in be.account_earnings(
            [
                _bot("gone", "Gone", account=_LIVE, balance=451.97, anchor=451.97),
                _bot("stay", "Stay", account=_DEMO, balance=10100.0, anchor=10000.0),
            ]
        )
    }
    gone = next(b for b in rows[_DEMO]["bots"] if b["bot_key"] == "gone")
    assert gone["former"] is True and gone["pct_of_opening"] is None


# ── an account bots LEFT keeps a balance: the last one they read on it ──────────────────────
#
# 🔴 2026-09-11: once the demo set went live, the demo account had no balance, no net and no
# Return %, and read as a closed account (Aaron: *"moving bots to live doesn't mean we don't trade
# on the demo still"*). Every running bot writes a `pulse` carrying its account and that account's
# balance, so the bots that left it had read one every fifteen minutes.


def _pulse(account=_DEMO, balance=9996.99, ts="2026-08-12T16:15:00+00:00"):
    return {"ts": ts, "kind": "pulse", "link": True, "balance": balance, "account": account}


def _demo_then_live(bot="sos", last=14538.88, last_at="2026-09-10T22:00:00+00:00"):
    """A bot that opened the demo account, traded on it, and went live — the real sequence."""
    archive_rows = [
        _start(_DEMO, "2026-08-12T16:00:00+00:00"),
        _close(1197.09, r=0.91, ts="2026-08-26T02:15:00+00:00"),
        _start(_LIVE, "2026-09-11T00:13:59+00:00"),
    ]
    health_rows = [
        _pulse(_DEMO, 9996.99, "2026-08-12T16:15:00+00:00"),
        _pulse(_DEMO, last, last_at),
    ]
    return archive_rows, health_rows


def test_an_account_bots_LEFT_reports_the_last_balance_they_read_on_it_WITH_its_time(archive):
    """The demo card had no balance at all. MEASURED on the real record: the first pulse on the
    demo account read $9,996.99 — the opening this module had recorded — and the last one $15,844.46.

    MUTATION: drop the last-reading balance → red on the balance. MUTATION: drop `balance_read_at`
    → red on the time.
    """
    rows, health = _demo_then_live()
    archive("sos", "2026-08-26", rows)
    archive("sos", "2026-09-10", health, kind="health")
    demo = {
        e["account"]: e
        for e in be.account_earnings(
            [_bot("sos", "SOS Fade", account=_LIVE, balance=451.97, anchor=451.97)]
        )
    }[_DEMO]
    assert demo["balance"] == 14538.88
    assert demo["balance_read_at"] == "2026-09-10T22:00:00+00:00"
    assert (demo["opening_balance"], demo["opening_from"]) == (9996.99, "sos")
    assert demo["net_usd"] == round(14538.88 - 9996.99, 2)
    # The remainder the demo account always carried — the duplicate positions closed by hand.
    assert demo["unattributed_usd"] == round(14538.88 - 9996.99 - 1197.09, 2)
    sos = demo["bots"][0]
    assert sos["former"] is True
    assert sos["pct_of_opening"] == round(1197.09 / 9996.99 * 100, 2)


def test_a_LIVE_balance_carries_no_read_time(archive):
    """`balance_read_at` means *this is a past reading*; on a live balance it must be absent, or
    every account on the page reads as stale. MUTATION: stamp it whenever a reading exists → red.

    ⚠ The live account needs READINGS of its own here. The first version had none, so a stamp
    taken off the readings was absent either way and the mutation SURVIVED — inputs that cannot
    tell the two behaviours apart do not test which one runs."""
    rows, health = _demo_then_live()
    archive("sos", "2026-08-26", rows)
    archive(
        "sos",
        "2026-09-10",
        [*health, _pulse(_LIVE, 451.97, "2026-09-11T00:30:00+00:00")],
        kind="health",
    )
    live = {
        e["account"]: e
        for e in be.account_earnings(
            [_bot("sos", "SOS Fade", account=_LIVE, balance=451.97, anchor=451.97)]
        )
    }[_LIVE]
    assert (live["balance"], live["balance_read_at"]) == (451.97, None)


def test_a_reading_taken_AFTER_a_trade_closed_is_never_the_opening(archive):
    """A later reading already holds a bot's result, so dividing by it under-states every return.
    MUTATION: drop the before-the-first-trade check → red."""
    archive(
        "sos",
        "2026-08-26",
        [
            _start(_DEMO, "2026-08-12T16:00:00+00:00"),
            _close(1197.09, ts="2026-08-26T02:15:00+00:00"),
            _start(_LIVE, "2026-09-11T00:00:00+00:00"),
        ],
    )
    archive(
        "sos", "2026-08-27", [_pulse(_DEMO, 11194.08, "2026-08-27T00:00:00+00:00")], kind="health"
    )
    demo = {
        e["account"]: e
        for e in be.account_earnings(
            [_bot("sos", "SOS Fade", account=_LIVE, balance=451.97, anchor=451.97)]
        )
    }[_DEMO]
    assert demo["balance"] == 11194.08
    assert (demo["opening_balance"], demo["net_usd"]) == (None, None)
    assert "after a trade had already closed" in demo["opening_note"]


def test_a_balance_read_BEFORE_the_last_trade_closed_takes_no_remainder_off_it(archive):
    """That balance does not contain the trade, so the remainder would be off by exactly its result.
    The net still stands — it is a true difference between two readings.
    MUTATION: drop the covered-window check → red."""
    rows, _ = _demo_then_live()
    archive("sos", "2026-08-26", rows)
    archive(
        "sos",
        "2026-08-20",
        [
            _pulse(_DEMO, 9996.99, "2026-08-12T16:15:00+00:00"),
            _pulse(_DEMO, 10100.0, "2026-08-20T00:00:00+00:00"),
        ],
        kind="health",
    )
    demo = {
        e["account"]: e
        for e in be.account_earnings(
            [_bot("sos", "SOS Fade", account=_LIVE, balance=451.97, anchor=451.97)]
        )
    }[_DEMO]
    assert demo["net_usd"] == round(10100.0 - 9996.99, 2)
    assert demo["unattributed_usd"] is None


def test_putting_a_NEW_bot_on_an_account_keeps_its_opening_and_its_record(archive):
    """🔴 Aaron: *"what if I wanted to test out more bots on a demo account while the live bot is
    also trading... it shouldn't matter."* A new bot's anchor is what the account held when IT
    arrived; taking that as the opening would re-base the account on whoever joined last and wipe
    the departed bots' history off its card.

    MUTATION: take the current bot's anchor even where a reading covers the account → red.
    """
    rows, health = _demo_then_live("gone")
    archive("gone", "2026-08-26", rows)
    archive("gone", "2026-09-10", health, kind="health")
    archive("new", "2026-09-12", [_start(_DEMO, "2026-09-12T00:00:00+00:00")])
    demo = {
        e["account"]: e
        for e in be.account_earnings(
            [
                _bot("gone", "Gone", account=_LIVE, balance=451.97, anchor=451.97),
                _bot("new", "New", account=_DEMO, balance=14600.0, anchor=14538.88),
            ]
        )
    }[_DEMO]
    assert (demo["opening_balance"], demo["opening_from"]) == (9996.99, "gone")
    # A bot on the account now: the balance is its live one, not a reading.
    assert (demo["balance"], demo["balance_read_at"]) == (14600.0, None)
    assert demo["net_usd"] == round(14600.0 - 9996.99, 2)
    assert demo["unattributed_usd"] == round(14600.0 - 9996.99 - 1197.09, 2)
    gone = next(b for b in demo["bots"] if b["bot_key"] == "gone")
    assert gone["former"] is True
    assert gone["pct_of_opening"] == round(1197.09 / 9996.99 * 100, 2)


def test_a_pulse_with_no_balance_is_not_a_reading_of_zero(archive):
    """A bot whose terminal link is down writes a pulse with no balance — *could not ask*, never
    $0. MUTATION: read a missing balance as 0 → red (the last reading becomes zero)."""
    rows, health = _demo_then_live()
    archive("sos", "2026-08-26", rows)
    blind = {**_pulse(_DEMO, 0, "2026-09-10T23:00:00+00:00"), "balance": None, "link": False}
    archive("sos", "2026-09-10", [*health, blind], kind="health")
    demo = {
        e["account"]: e
        for e in be.account_earnings(
            [_bot("sos", "SOS Fade", account=_LIVE, balance=451.97, anchor=451.97)]
        )
    }[_DEMO]
    assert (demo["balance"], demo["balance_read_at"]) == (14538.88, "2026-09-10T22:00:00+00:00")


def test_the_read_time_survives_the_response_model():
    """Pydantic drops a field the model does not declare, and then a day-old reading renders as the
    account's balance NOW. MUTATION: remove the field from `AccountEarnings` → red."""
    from models import AccountEarnings

    out = AccountEarnings(
        account=_DEMO, balance=14538.88, balance_read_at="2026-09-10T22:00:00+00:00"
    )
    assert out.model_dump()["balance_read_at"] == "2026-09-10T22:00:00+00:00"


# ── a bot on the account that has not REPORTED yet (2026-09-11) ─────────────────────────────
#
# 🔴 Adding the first bot to the demo account blanked a balance that had been on screen a minute
# earlier: the last reading was served only for an account NO bot is on, so a bot that had just
# started — on it, and not yet reporting — made the balance unread until its first report.


def _gone_from_demo(archive):
    rows, health = _demo_then_live("gone")
    archive("gone", "2026-08-26", rows)
    archive("gone", "2026-09-10", health, kind="health")


def test_a_bot_that_has_not_REPORTED_yet_shows_the_last_reading_WITH_its_time(archive):
    """MUTATION: fall back only when no bot is on the account (the old `not merged`) → red."""
    _gone_from_demo(archive)
    demo = {
        e["account"]: e
        for e in be.account_earnings(
            [
                _bot("gone", "Gone", account=_LIVE, balance=451.97, anchor=451.97),
                _bot("new", "New", account=_DEMO, balance=None),
            ]
        )
    }[_DEMO]
    assert (demo["balance"], demo["balance_read_at"]) == (14538.88, "2026-09-10T22:00:00+00:00")
    assert demo["net_usd"] == round(14538.88 - 9996.99, 2)


def _stay_on_demo(archive, read_at):
    """One bot that has always been here, traded $50 on 2026-08-25, and last read the balance at
    `read_at` — then restarted and has not reported since."""
    archive(
        "stay",
        "2026-08-25",
        [_start(_DEMO, "2026-08-20T00:00:00+00:00"), _close(50.0, ts="2026-08-25T00:00:00+00:00")],
    )
    archive("stay", read_at[:10], [_pulse(_DEMO, 10020.0, read_at)], kind="health")
    return {
        e["account"]: e
        for e in be.account_earnings(
            [_bot("stay", "Stay", account=_DEMO, balance=None, anchor=10000.0)]
        )
    }[_DEMO]


def test_a_past_reading_takes_no_remainder_off_a_CURRENT_bots_anchor_past_a_later_trade(archive):
    """A past reading can now reach the anchor branch, where it never could before — and a trade
    that closed after it is not in it, so the remainder would be off by exactly that trade.
    MUTATION: ask the covered-window check on the account's own opening only → red."""
    demo = _stay_on_demo(archive, "2026-08-24T00:00:00+00:00")
    assert (demo["balance"], demo["net_usd"]) == (10020.0, 20.0)
    assert demo["unattributed_usd"] is None


def test_a_past_reading_AFTER_the_last_trade_does_take_the_remainder(archive):
    """The control for the case above: a reading that contains every trade is a fair one to take a
    remainder off. MUTATION: refuse any past reading in the anchor branch → red."""
    demo = _stay_on_demo(archive, "2026-08-26T00:00:00+00:00")
    assert demo["unattributed_usd"] == round(20.0 - 50.0, 2)


# ── a new bot on an account CARRIES ON the record of the one that left (2026-09-11) ─────────
#
# 🔴 The demo copies put on the demo account after the set went live drew at $0, beside two rows
# holding the account's whole demo record under "moved to live". Aaron: *"if I add back bots on the
# demo they should just pick up where they left off."*


def _carry(archive, new_strategy="sos_fade", gone_strategy="sos_fade"):
    _gone_from_demo(archive)
    archive("new", "2026-09-12", [_start(_DEMO, "2026-09-12T00:00:00+00:00")])
    return {
        e["account"]: e
        for e in be.account_earnings(
            [
                _bot("gone", "SOS Fade", _LIVE, 451.97, anchor=451.97, strategy=gone_strategy),
                _bot(
                    "new", "SOS Fade (demo)", _DEMO, 14600.0, anchor=14538.88, strategy=new_strategy
                ),
            ]
        )
    }[_DEMO]


def test_a_new_bot_CARRIES_ON_the_record_of_the_bot_that_left_the_same_strategy_here(archive):
    """MUTATION: return the current rows unfolded → red (the new bot reads $0 beside a history
    row). MUTATION: drop `carried_from` → red on whose trades the row shows."""
    demo = _carry(archive)
    assert [b["bot_key"] for b in demo["bots"]] == ["new"]
    new = demo["bots"][0]
    assert (new["closed_trades"], new["realised_usd"], new["wins"], new["former"]) == (
        1,
        1197.09,
        1,
        False,
    )
    assert new["carried_from"] == [
        {"bot_key": "gone", "name": "SOS Fade", "moved_to": _LIVE, "closed_trades": 1}
    ]
    # The strategy's tenure here starts with the bot that left, not the one that arrived.
    assert new["records_from"] == "2026-08-12"
    # On the account's OWN opening, so the carried dollars are inside the window it measures.
    assert new["pct_of_opening"] == round(1197.09 / 9996.99 * 100, 2)


def test_carrying_the_record_moves_NO_account_figure(archive):
    """The fold is WHICH ROW shows the trades, never what the account made. MUTATION: count the
    folded rows AND the departed rows toward the attributed total → red on the remainder."""
    demo = _carry(archive)
    assert (demo["opening_balance"], demo["opening_from"]) == (9996.99, "gone")
    assert demo["net_usd"] == round(14600.0 - 9996.99, 2)
    assert demo["attributed_usd"] == 1197.09
    assert demo["unattributed_usd"] == round(14600.0 - 9996.99 - 1197.09, 2)


def test_a_departed_bot_of_ANOTHER_strategy_keeps_its_own_row(archive):
    """MUTATION: fold regardless of strategy → red."""
    demo = _carry(archive, new_strategy="extreme_leg")
    by_key = {b["bot_key"]: b for b in demo["bots"]}
    assert by_key["gone"]["former"] is True
    assert (by_key["new"]["carried_from"], by_key["new"]["closed_trades"]) == ([], 0)


def test_an_UNKNOWN_strategy_never_matches_another_unknown_one(archive):
    """Two bots whose strategy could not be read are not the same strategy. MUTATION: group a
    missing strategy under "" → red (the unread history folds into an unread bot)."""
    demo = _carry(archive, new_strategy=None, gone_strategy=None)
    assert {b["bot_key"]: b["former"] for b in demo["bots"]} == {"new": False, "gone": True}


def test_TWO_bots_of_one_strategy_get_no_carried_history(archive):
    """No single heir: handing the history to either credits it to a guess.
    MUTATION: take the first bot as the heir → red."""
    _gone_from_demo(archive)
    for k in ("a", "b"):
        archive(k, "2026-09-12", [_start(_DEMO, "2026-09-12T00:00:00+00:00")])
    demo = {
        e["account"]: e
        for e in be.account_earnings(
            [
                _bot("gone", "Gone", _LIVE, 451.97, anchor=451.97, strategy="sos_fade"),
                _bot("a", "A", _DEMO, 14600.0, anchor=14538.88, strategy="sos_fade"),
                _bot("b", "B", _DEMO, 14600.0, anchor=14538.88, strategy="sos_fade"),
            ]
        )
    }[_DEMO]
    assert next(b for b in demo["bots"] if b["bot_key"] == "gone")["former"] is True
    assert all(b["carried_from"] == [] for b in demo["bots"])


def test_an_heir_whose_own_record_is_UNREAD_shows_the_history_and_stays_NAMED(archive):
    """A bot that has just started may have no record on this machine yet. Its row shows what it
    carries on, and the account still names it, so the split still reads as a floor.
    MUTATION: take the no-record list after the fold → red on the name."""
    _gone_from_demo(archive)
    demo = {
        e["account"]: e
        for e in be.account_earnings(
            [
                _bot("gone", "Gone", _LIVE, 451.97, anchor=451.97, strategy="sos_fade"),
                _bot("new", "New", _DEMO, None, strategy="sos_fade"),
            ]
        )
    }[_DEMO]
    new = demo["bots"][0]
    assert (new["traded"], new["closed_trades"], new["realised_usd"]) == (True, 1, 1197.09)
    assert demo["bots_without_record"] == ["new"]


def test_CARRIED_dollars_get_no_share_of_a_current_bots_anchor(archive):
    """With no reading of the account's own opening, the opening is the heir's anchor — what the
    account held when IT arrived — and the carried trades closed before that. Dividing them by it
    mixes two starts, the rule a departed bot's own row already follows.
    MUTATION: guard `pct_of_opening` on `former` alone → red."""
    rows, _ = _demo_then_live("gone")
    archive("gone", "2026-08-26", rows)
    archive("new", "2026-09-12", [_start(_DEMO, "2026-09-12T00:00:00+00:00")])
    demo = {
        e["account"]: e
        for e in be.account_earnings(
            [
                _bot("gone", "Gone", _LIVE, 451.97, anchor=451.97, strategy="sos_fade"),
                _bot("new", "New", _DEMO, 14600.0, anchor=14538.88, strategy="sos_fade"),
            ]
        )
    }[_DEMO]
    new = demo["bots"][0]
    assert (new["realised_usd"], new["pct_of_opening"]) == (1197.09, None)


def test_carried_from_survives_the_response_model():
    """Pydantic drops a field the model does not declare, and the page then cannot say whose trades
    a new bot's row is showing. MUTATION: remove the field from `BotEarnings` → red."""
    from models import BotEarnings

    out = BotEarnings(
        bot_key="new",
        name="New",
        traded=True,
        carried_from=[{"bot_key": "gone", "name": "Gone", "moved_to": _LIVE, "closed_trades": 1}],
    )
    assert out.model_dump()["carried_from"][0]["moved_to"] == _LIVE
