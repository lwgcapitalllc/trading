"""A live link says nothing about WHOSE account is behind it.

🔴 **Written after it happened, on a live bot, and nothing objected.** On 2026-08-12 the `MT5_FFT`
terminal was logged from the PU Prime Standard demo onto the ECN one while `sos_fade_demo` was
running. `connect()` had asserted the account at startup — once — and the terminal is a shared
resource for the rest of the process, so every read afterwards was answered promptly and correctly
about the wrong account. The bot **re-anchored its position sizing from $1,992.21 to $9,996.99**,
five times the money, and logged it as the ordinary event it looks like. It placed no order in that
window, so it cost nothing; the next setup would have been sized against a stranger's balance.

Three properties are pinned here, and each is a decision rather than an implementation detail:

1. **It HALTS, it does not reconnect.** The link is healthy — it is the identity behind it that
   moved. `_recover_link` calls `connect()` calls `mt5.login()`, which would drag the terminal back
   off whatever a human is doing on it. A bot must not fight its operator for a window.
2. **An UNREADABLE account is not a match.** "No" and "cannot ask" are never the same value.
3. **It latches**, so a terminal flipping between logins cannot toggle a live book unattended.

⚠ `probe_link` is tested here too, because the account number has to come off the SAME
`account_info()` call the balance does. Reading it separately is exactly what let two answers about
one terminal disagree during the 50-minute blind outage of 2026-08-04.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "live"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

import runner as runner_mod  # noqa: E402

LiveRunner = runner_mod.LiveRunner

MINE = 700152905
THEIRS = 700107749


class _Bridge:
    def __init__(self):
        self.halts = []

    def halt(self, reason):
        self.halts.append(reason)


class _Ledger:
    def __init__(self):
        self.events = []

    def event(self, name, **kw):
        self.events.append((name, kw))


def _runner(monkeypatch, observed):
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(bot_key="bot", display_name="Bot", account=MINE)
    r.bridge = _Bridge()
    r.ledger = _Ledger()
    r._account_mismatch_halted = False
    r._observed_account = observed
    r.errors, r.alerts = [], []
    r.log = SimpleNamespace(
        info=lambda m, *a, **k: None,
        warning=lambda m, *a, **k: None,
        error=lambda m, *a, **k: r.errors.append(m),
    )
    monkeypatch.setattr(r, "_notify_health", lambda text: r.alerts.append(text))
    return r


def test_the_right_account_does_nothing_at_all(monkeypatch):
    """The normal state, evaluated every ~10 seconds forever. It must not log, alert or write a
    ledger record — a health stream with a line per poll is one nobody reads."""
    r = _runner(monkeypatch, MINE)

    r._check_account_identity()

    assert r._account_mismatch_halted is False
    assert r.bridge.halts == [] and r.ledger.events == [] and r.alerts == [] and r.errors == []


def test_a_different_account_HALTS_THE_BRIDGE(monkeypatch):
    """The defect. Noticing the mismatch and not stopping the thing that places orders would be
    the same failure one layer up."""
    r = _runner(monkeypatch, THEIRS)

    r._check_account_identity()

    assert r._account_mismatch_halted is True
    assert len(r.bridge.halts) == 1
    assert "account mismatch" in r.bridge.halts[0]
    # BOTH numbers, because "the accounts disagree" is true of every cause at once and sends the
    # reader at whichever half they thought of first.
    assert str(THEIRS) in r.bridge.halts[0] and str(MINE) in r.bridge.halts[0]


def test_the_mismatch_is_recorded_and_alerted_once(monkeypatch):
    r = _runner(monkeypatch, THEIRS)

    r._check_account_identity()
    r._check_account_identity()
    r._check_account_identity()

    assert len(r.bridge.halts) == 1, "it latches — a flapping terminal must not re-halt per poll"
    assert len(r.alerts) == 1
    names = [n for n, _ in r.ledger.events]
    assert names == ["account_mismatch"]
    _, kw = r.ledger.events[0]
    assert kw == {"observed": THEIRS, "expected": MINE}


def test_an_unreadable_account_is_not_treated_as_a_match(monkeypatch):
    """`None` = could not ask. It must not halt (that is the dead-link path's job, and
    `probe_link` already reports it as one) and it must not LATCH a clean state either."""
    r = _runner(monkeypatch, None)

    r._check_account_identity()

    assert r.bridge.halts == [] and r.alerts == []
    assert r._account_mismatch_halted is False, "nothing was established, so nothing is settled"


def test_a_terminal_that_comes_back_on_the_wrong_account_still_halts(monkeypatch):
    """The realistic sequence: unreadable for a poll or two, then readable and wrong. An
    early-return on `None` that also latched would swallow this."""
    r = _runner(monkeypatch, None)
    r._check_account_identity()

    r._observed_account = THEIRS
    r._check_account_identity()

    assert len(r.bridge.halts) == 1


class _Info:
    def __init__(self, balance, login=None):
        self.balance = balance
        if login is not None:
            self.login = login


def _probe(monkeypatch, info, raises=False):
    """Drive `probe_link` against a fake MetaTrader5 module."""
    r = LiveRunner.__new__(LiveRunner)
    r._observed_account = "untouched"
    r.log = SimpleNamespace(warning=lambda *a, **k: None)

    class _Mt5:
        @staticmethod
        def account_info():
            if raises:
                raise RuntimeError("pipe closed")
            return info

    monkeypatch.setitem(sys.modules, "MetaTrader5", _Mt5)
    return r, r.probe_link()


def test_probe_link_reads_the_account_off_the_same_call_as_the_balance(monkeypatch):
    r, (up, balance) = _probe(monkeypatch, _Info(9996.99, login=MINE))

    assert up is True
    assert balance == pytest.approx(9996.99)
    assert r._observed_account == MINE


@pytest.mark.parametrize("info,raises", [(None, False), (None, True)])
def test_a_link_that_cannot_answer_leaves_no_stale_account_behind(monkeypatch, info, raises):
    """A remembered number from before the outage would let the identity check pass on evidence
    that is no longer being gathered."""
    r, (up, balance) = _probe(monkeypatch, info, raises=raises)

    assert up is False and balance is None
    assert r._observed_account is None


def test_an_account_info_without_a_login_is_unreadable_not_a_match(monkeypatch):
    r, (up, _) = _probe(monkeypatch, _Info(9996.99))  # no `login` attribute at all

    assert up is True, "the balance answered, so the link is alive"
    assert r._observed_account is None, "but the identity was not established"
