"""The MT5 connect lock is ONE PER TERMINAL — `algos/shared/mt5_lock.py`.

🔴 **It was one file for the whole box until 2026-09-13**, so a connect on one account made every
other account's bots queue behind it, and a terminal that hung mid-connect held the lock until it
went stale while the other accounts' bots gave up and exited. Two separately owned accounts on one
box must not be able to take each other's bots down, and a shared lock was a way to.

The connect case is driven through the REAL `BotMT5.connect` against a stand-in terminal, because
the property worth pinning is *which lock a connect waits on* — a test of `lock_path` alone would
pass against a connect that never called it.
"""

from __future__ import annotations

import os
import sys
import time
import types
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent / "shared"
sys.path.insert(0, str(_SHARED))
import mt5_lock  # noqa: E402


# ── naming ───────────────────────────────────────────────────────────────────────
def test_one_terminal_spelled_two_ways_is_ONE_lock():
    """Two bots on one terminal must still wait for each other — that is the lock's whole job. A
    path typed with other slashes, case or quotes must not buy a second lock.
    MUTATION: drop the case/slash folding -> red."""
    assert mt5_lock.lock_path("C:\\MT5_FFT\\terminal64.exe") == mt5_lock.lock_path(
        '"c:/mt5_fft/Terminal64.exe"'
    )


def test_two_terminals_are_two_locks():
    """MUTATION: return the old single path -> red."""
    a = mt5_lock.lock_path("C:\\MT5_FFT\\terminal64.exe")
    b = mt5_lock.lock_path("C:\\Program Files\\PU Prime MT5 Terminal\\terminal64.exe")
    assert a != b
    assert a.name.startswith("mt5_connect_") and b.name.startswith("mt5_connect_")


def test_an_empty_path_still_names_a_lock():
    assert mt5_lock.lock_path("").name == "mt5_connect_default.lock"


# ── what a cleaner may remove ────────────────────────────────────────────────────
def test_only_an_ABANDONED_lock_is_stale(tmp_path):
    """A fresh lock is a bot mid-connect. MUTATION: drop the age test -> red."""
    fresh = mt5_lock.lock_path("C:\\A\\terminal64.exe", root=tmp_path)
    old = mt5_lock.lock_path("C:\\B\\terminal64.exe", root=tmp_path)
    fresh.write_text("bot_a_1")
    old.write_text("bot_b_2")
    past = time.time() - 3600
    os.utime(old, (past, past))
    assert mt5_lock.stale_locks(tmp_path) == [old]


def test_the_old_single_lock_is_swept_too(tmp_path):
    """A bot still running the code from before the split holds `mt5_connect.lock`; every cleaner
    that sweeps the prefix must still clear it."""
    single = tmp_path / "mt5_connect.lock"
    single.write_text("old_code_bot")
    past = time.time() - 3600
    os.utime(single, (past, past))
    assert single in mt5_lock.all_locks(tmp_path)
    assert mt5_lock.stale_locks(tmp_path) == [single]


# ── a connect waits on ITS terminal's lock, and only that one ────────────────────
class _Info:
    def __init__(self, login):
        self.login, self.balance, self.server = login, 1000.0, "Demo"


def _fake_terminal(login):
    m = types.ModuleType("MetaTrader5")
    m.initialize = lambda path=None: True
    m.login = lambda *a, **k: True
    m.account_info = lambda: _Info(login)
    m.shutdown = lambda: None
    m.last_error = lambda: (0, "ok")
    return m


class _Log:
    def __init__(self):
        self.lines = []

    def _rec(self, msg):
        self.lines.append(str(msg))

    info = warning = error = _rec

    def saw(self, fragment):
        return any(fragment.lower() in ln.lower() for ln in self.lines)


@pytest.fixture
def ops(monkeypatch, tmp_path):
    """`mt5_ops` against a stand-in terminal, its locks in a scratch folder — a test writing the
    real `algos/` folder would be writing the file a live bot on this machine reads."""
    monkeypatch.setitem(sys.modules, "MetaTrader5", _fake_terminal(1))
    monkeypatch.syspath_prepend(str(_SHARED))
    for mod in ("mt5_ops", "bot_state", "broker_clock"):
        sys.modules.pop(mod, None)
    import mt5_ops

    monkeypatch.setattr(mt5_ops, "_lock_path", lambda p: mt5_lock.lock_path(p, root=tmp_path))
    monkeypatch.setattr(mt5_ops.time, "sleep", lambda s: None)
    return mt5_ops


def _bot(mt5_ops, terminal, log):
    return mt5_ops.BotMT5(
        "XAUUSD",
        770115,
        "BOT_TEST",
        {"mt5_path": terminal},
        {"login": 1, "password": "x", "server": "Demo"},
        log,
    )


def test_ANOTHER_terminals_connect_does_not_hold_this_one_up(ops, tmp_path):
    """🔴 THE property. A connect in progress on account A's terminal must not make account B's
    bot wait. MUTATION: take the lock off a fixed path again -> red (it waits out the timeout)."""
    held = mt5_lock.lock_path("C:\\MT5_A\\terminal64.exe", root=tmp_path)
    held.write_text("bot_on_a_1")  # fresh: a bot on terminal A is mid-connect
    log = _Log()

    assert _bot(ops, "C:\\MT5_B\\terminal64.exe", log).connect() is True
    assert not log.saw("Waiting for MT5 lock"), log.lines
    assert held.exists(), "a connect on terminal B removed terminal A's lock"
    assert not mt5_lock.lock_path("C:\\MT5_B\\terminal64.exe", root=tmp_path).exists()


def test_the_SAME_terminal_still_waits(ops, tmp_path):
    """The other half — two bots on one terminal must still take turns, however the path is
    spelled. MUTATION: key the lock on the bot rather than the terminal -> red."""
    held = mt5_lock.lock_path("C:\\MT5_A\\terminal64.exe", root=tmp_path)
    held.write_text("sibling_on_a_1")
    log = _Log()

    assert _bot(ops, "c:/mt5_a/terminal64.exe", log).connect() is False
    assert log.saw("Waiting for MT5 lock")
    assert log.saw("Could not acquire MT5 lock")
