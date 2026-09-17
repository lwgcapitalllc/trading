"""A resting order the BROKER rejects: one alert, and a quick re-send when the cause is temporary.

2026-09-16 ~19:15 UTC, `sos_fade_demo`: a re-placed sell limit came back retcode 10031 "Request
rejected due to absence of network connection". Nothing was sent to Telegram, and the order sat
off the book until the next 15-minute bar placed it at 19:30.

**Watched RED before the fix:** no ORDER REJECTED message existed, `retry_rejected` did not exist,
and the refusal record carried no retcode. The fake refuses the way `mt5_ops` does — a dict with the
code, the broker's sentence and the retcode, or nothing at all — never more than production can say.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from test_live_bridge import (  # noqa: E402
    _bridge,
    _Dec,
    _FakeExecution,
    _Pend,
    _Sig,
    install_mt5_stub,
)

NO_CONNECTION = {
    "code": "broker_rejected",
    "detail": "Pending failed (XAUUSD.p bearish 0.14L @ 4316.98): retcode=10031 "
    "'Request rejected due to absence of network connection' last_error=(1, 'Success')",
    "retcode": 10031,
}
NO_MONEY = {
    "code": "broker_rejected",
    "detail": "Pending failed: retcode=10019 'No money'",
    "retcode": 10019,
}


@pytest.fixture(autouse=True)
def _stub(monkeypatch):
    install_mt5_stub(monkeypatch)


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _setup(refusal):
    ex = _FakeExecution(pend_short=_Pend(-1, 3310.0, 14.0, 3320.0))
    b, ops, ledger, notes = _bridge(ex)
    clock = _Clock()
    b._now = clock
    ops.refuse_placement = refusal
    b.sync(_Dec(), _Sig())
    return ex, b, ops, ledger, notes, clock


def _rejected(notes):
    return [n for n in notes if "ORDER REJECTED" in n]


def test_a_rejection_is_ALERTED_with_the_order_the_reason_and_what_happens_next():
    """MUTATION: delete the `_on_broker_rejection` call in `_place` and this reddens."""
    _, _, _, ledger, notes, _ = _setup(NO_CONNECTION)
    (msg,) = _rejected(notes)
    assert "limit 0.14L @ 3310.0" in msg
    assert "absence of network connection" in msg
    assert "re-sent in 10s" in msg
    row = [kw for k, kw in ledger.rows if k == "event:order_refused"][0]
    assert row["retcode"] == 10031


def test_a_TEMPORARY_rejection_is_re_sent_on_the_poll_loop_not_a_bar_later():
    _, b, ops, _, notes, clock = _setup(NO_CONNECTION)
    b.retry_rejected()
    assert ops.actions == []  # not due yet
    ops.refuse_placement = None  # the link came back
    clock.t += 10
    b.retry_rejected()
    assert [a[0] for a in ops.actions] == ["place"]
    assert any("ORDER PLACED AFTER REJECTION" in n for n in notes)
    b.retry_rejected()
    assert len(ops.actions) == 1  # MUTATION: skip popping `_retry` on success and it re-sends


def test_a_flapping_link_is_ONE_message_and_the_retries_are_BOUNDED():
    _, b, ops, _, notes, clock = _setup(NO_CONNECTION)
    for _ in range(20):
        clock.t += 1000
        b.retry_rejected()
    # 1 original send + 5 re-sends, then it stops until the next bar.
    assert b._retry == {}
    msgs = _rejected(notes)
    assert len(msgs) == 2  # the first, and the give-up
    assert "Gave up after 5" in msgs[1]


def test_a_PERMANENT_rejection_is_never_re_sent():
    """MUTATION: treat every retcode as temporary and this reddens."""
    _, b, ops, _, notes, clock = _setup(NO_MONEY)
    clock.t += 1000
    b.retry_rejected()
    assert b._retry == {}
    (msg,) = _rejected(notes)
    assert "Not re-sent now" in msg


def test_no_retcode_at_all_is_not_a_reason_to_re_send():
    """A send with no reply is not a KNOWN temporary rejection."""
    _, b, _, _, notes, _ = _setup(
        {"code": "broker_rejected", "detail": "no reply", "retcode": None}
    )
    assert b._retry == {} and _rejected(notes) == []


def test_the_re_send_is_DROPPED_when_the_strategy_no_longer_wants_that_order():
    """MUTATION: drop the `pend is r["pend"]` guard and a stale order is sent."""
    ex, b, ops, _, _, clock = _setup(NO_CONNECTION)
    ops.refuse_placement = None
    ex._pend_short = _Pend(-1, 3305.0, 14.0, 3320.0)  # the next bar moved it
    clock.t += 10
    b.retry_rejected()
    assert ops.actions == [] and b._retry == {}


def test_the_re_send_is_DROPPED_when_the_broker_now_holds_a_position():
    from test_live_bridge import _Pos

    _, b, ops, _, _, clock = _setup(NO_CONNECTION)
    ops.refuse_placement = None
    ops.positions = [_Pos(99, 1, 3310.0, 0.14, 3320.0)]
    clock.t += 10
    b.retry_rejected()
    assert ops.actions == [] and b._retry == {}


def test_a_MARKET_rejection_is_alerted_and_never_re_sent():
    ex = _FakeExecution(pend_long=_Pend(1, 3290.0, 42.0, 3280.0, market=True))
    b, ops, _, notes = _bridge(ex)
    ops.refuse_placement = NO_CONNECTION
    b.sync(_Dec(), _Sig())
    (msg,) = _rejected(notes)
    assert "market order" in msg and "Not re-sent" in msg
    assert b._retry == {}


def test_the_retry_is_driven_from_the_runner_poll_loop():
    """The call site exists; without it the whole mechanism is a label with no consumer."""
    src = (_HERE.parent / "live" / "runner.py").read_text(encoding="utf-8")
    assert "self.bridge.retry_rejected()" in src


def test_the_transient_list_is_the_MT5_documented_codes():
    from broker_result import TRANSIENT_RETCODES, is_transient

    assert TRANSIENT_RETCODES == {10004, 10020, 10021, 10024, 10028, 10031}
    assert not is_transient(10012)  # timeout = unknown outcome, reconciled, never re-sent
    assert not is_transient(None)
