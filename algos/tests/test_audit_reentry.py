"""The re-entry audit must be able to FAIL. That is the only property that makes it worth having.

🔴 **WHY THIS FILE EXISTS.** The tool it tests exists because the re-entry went live having never
placed a real order, and Aaron's instruction was that the checking is not his job. An audit nobody
has watched go red is a green light with no bulb behind it — and this repo has already shipped one
of those: `check_tradingbox.py` certified two tools that had NEVER worked, because every case it
had asserted what a tool REFUSES, and a tool that always fails passes those beautifully.

So every check below is driven BOTH ways: a trade that satisfies it, and a trade that breaks it.
A check that only ever passes is removed rather than kept.

⚠ **The `NOT CHECKED` verdict is tested as carefully as the failures**, because the whole design
rests on it not being mistaken for a pass — and a bug that turned one into the other would leave
this file green while making the tool worthless.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_TOOLS = _REPO / "algos" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import audit_reentry as audit  # noqa: E402

# The live bot's own re-entry settings, so a test says what it CHANGED.
PARAMS = {
    "exec_risk_pct": 10.0,
    "exec_sec_risk_pct": 50.0,  # a re-entry risks half the primary's -> 5% of the basis
    "exec_tp1_pct": 0.0,
    "exec_tp2_pct": 0.0,
    "exec_sec_tp1_pct": 0.0,  # banks NOTHING at a price
    "exec_time_stop_hrs": 36.0,
    "exec_sec_max_per_setup": 1,
}


def _opened(**over):
    """A clean re-entry fill: long at 3300, stop 3280, risking 5% of a $10,000 basis."""
    row = dict(
        kind="trade",
        event="opened",
        ticket=901,
        dir="LONG",
        symbol="XAUUSD.p",
        intent="secondary",
        lots=0.25,
        price=3300.0,
        intended_price=3300.0,
        stop=3280.0,
        risk_pct=10.0,
        risk_usd=500.0,
        risk_pct_realised=5.0,
    )
    row.update(over)
    return row


def _closed(**over):
    row = dict(
        kind="trade",
        event="closed",
        ticket=901,
        dir="LONG",
        symbol="XAUUSD.p",
        intent="secondary",
        lots=0.25,
        price=3320.0,
        pnl_usd=490.0,
        r=1.0,
        reason="stop",
        gross_usd=500.0,
        swap_usd=-5.0,
        commission_usd=-5.0,
        entry_price=3300.0,
    )
    row.update(over)
    return row


def _event(name, **fields):
    return dict(kind="event", event=name, ticket=901, **fields)


def _verdicts(rep):
    return {rule: verdict for verdict, rule, _detail in rep.rows}


_STILL_OPEN = object()  # ⚠ a sentinel, because `None` is a MEANINGFUL argument here — it is what
#                         an open trade looks like, and a `closed=None` default would make the
#                         helper unable to express the one case it most needs to.


def _run(opened=None, closed=_STILL_OPEN, events=(), params=None):
    return audit.audit_trade(
        opened or _opened(),
        _closed() if closed is _STILL_OPEN else closed,
        list(events),
        params or PARAMS,
    )


# ── the clean trade, which must come back with nothing wrong ──────────────────
def test_a_trade_that_followed_the_strategy_passes_every_check():
    """⚠ **The control, and it is the one that keeps the rest honest.** A tool that failed
    everything would satisfy every failure test in this file on its own."""
    rep = _run(events=[_event("stop_moved", was=3280.0, now=3290.0)])
    assert not rep.failures, rep.rows
    assert not rep.unanswered, rep.rows


# ── size ──────────────────────────────────────────────────────────────────────
def test_a_re_entry_sized_like_a_PRIMARY_is_caught():
    """🔴 The defect this whole audit was built around: a re-entry is supposed to risk HALF the
    primary's percentage, and nothing before 2026-09-02 would have shown it if it did not."""
    rep = _run(_opened(risk_pct_realised=10.0, risk_usd=1000.0))
    assert _verdicts(rep)["risk sized correctly"] == audit.FAIL


def test_a_size_SHORTFALL_within_lot_rounding_is_not_a_failure():
    """⚠ The lot step rounds DOWN, so slightly under is correct behaviour. A check that failed on
    it would cry wolf on every trade and be switched off within a week."""
    rep = _run(_opened(risk_pct_realised=4.9))
    assert _verdicts(rep)["risk sized correctly"] == audit.PASS


def test_a_size_shortfall_TOO_BIG_to_be_rounding_is_caught():
    rep = _run(_opened(risk_pct_realised=3.0))
    assert _verdicts(rep)["risk sized correctly"] == audit.FAIL


def test_an_unreadable_balance_is_NOT_CHECKED_rather_than_passed():
    """Rule 1, and the reason the tool has three verdicts instead of two. The bot records `None`
    when it could not read the balance; scoring that as a pass would certify the one trade whose
    size nobody can confirm."""
    rep = _run(_opened(risk_pct_realised=None))
    assert _verdicts(rep)["risk sized correctly"] == audit.UNKNOWN
    assert rep.unanswered, "an unanswered check must be counted apart from the passes"


# ── the stop ──────────────────────────────────────────────────────────────────
def test_a_position_opened_with_NO_stop_is_caught():
    rep = _run(_opened(stop=0.0))
    assert _verdicts(rep)["stop attached at entry"] == audit.FAIL


def test_a_stop_on_the_WRONG_SIDE_of_entry_is_caught():
    """A long whose stop sits above its entry is not protected, it is a guaranteed exit — and
    every field is present, so nothing else in the record looks wrong."""
    rep = _run(_opened(stop=3320.0))
    assert _verdicts(rep)["stop attached at entry"] == audit.FAIL


def test_a_stop_that_moved_AGAINST_the_trade_is_caught():
    """The stop ratchets one way only. A move that widens it is a bigger loss than the one the
    trade was sized for, which makes every R figure after it wrong."""
    rep = _run(events=[_event("stop_moved", was=3290.0, now=3270.0)])
    assert _verdicts(rep)["the stop never widened"] == audit.FAIL


def test_a_stop_the_strategy_could_not_REPORT_is_caught():
    """The bot writes this when it is holding a re-entry and cannot read its stop. The broker's
    stop then stands still while the strategy believes it is ratcheting — and a stop that does
    not move is indistinguishable from a trade with nothing to move."""
    rep = _run(events=[_event("secondary_stop_unreadable")])
    assert _verdicts(rep)["the stop was managed throughout"] == audit.FAIL


# ── banking ───────────────────────────────────────────────────────────────────
def test_banking_on_a_leg_set_to_bank_NOTHING_is_caught():
    """This bot's re-entry takes nothing off at a price — that setting is worth +7.49R over 6.6
    years. A partial bank means it traded a different book from the one that was measured."""
    rep = _run(events=[_event("partial_banked", lots=0.12)])
    assert _verdicts(rep)["banking matches the settings"] == audit.FAIL


def test_NOT_banking_on_a_leg_that_is_SUPPOSED_to_is_caught():
    """⚠ The other direction, and it is the one that would go unnoticed: the trade simply rides,
    and it looks like an ordinary winner or loser. The bot would be riding where the backtest
    scaled out — a whole class of divergence with no symptom."""
    rep = _run(params={**PARAMS, "exec_sec_tp1_pct": 50.0})
    assert _verdicts(rep)["banking matches the settings"] == audit.FAIL


# ── the exit ──────────────────────────────────────────────────────────────────
def test_a_trade_still_OPEN_is_NOT_CHECKED_rather_than_passed():
    rep = _run(closed=None)
    assert _verdicts(rep)["the exit"] == audit.UNKNOWN
    assert "R matches the prices" not in _verdicts(rep), (
        "an open trade has no exit to check — inventing a verdict for one would be worse than "
        "leaving it out"
    )


def test_an_exit_with_NO_REASON_recorded_is_caught():
    rep = _run(closed=_closed(reason=""))
    assert _verdicts(rep)["the exit reason is recorded"] == audit.FAIL


def test_an_R_that_does_not_match_the_PRICES_is_caught():
    """🔴 Recomputed from the recorded prices rather than read back. A stored figure that
    reproduces its own arithmetic has been checked against nothing — this repo has a rule about
    that, learned from a page whose every number recomputed to the cent and still misled."""
    rep = _run(closed=_closed(r=5.0))  # prices imply +1.0R
    assert _verdicts(rep)["R matches the prices"] == audit.FAIL


def test_COSTS_the_broker_could_not_be_asked_for_are_NOT_CHECKED():
    """`None` means the broker could not be ASKED, never that the cost was zero. The P&L may then
    not be net, and a net-looking figure that is gross is exactly the kind of wrong that survives
    for months."""
    rep = _run(closed=_closed(swap_usd=None))
    assert _verdicts(rep)["costs recorded separately"] == audit.UNKNOWN


# ── the expected-risk rule the audit restates ────────────────────────────────
def test_the_expected_risk_for_a_re_entry_is_a_FRACTION_of_the_primarys():
    """MUTATION: return the primary's figure for both legs and this goes red — which is the bug
    that was live in the ledger and the Telegram message until 2026-09-02."""
    assert audit.expected_risk_pct(PARAMS, "primary") == 10.0
    assert audit.expected_risk_pct(PARAMS, "secondary") == 5.0


def test_a_missing_risk_setting_gives_None_and_not_a_guess():
    assert audit.expected_risk_pct({}, "primary") is None
    assert audit.expected_risk_pct({"exec_risk_pct": 10.0}, "secondary") is None
