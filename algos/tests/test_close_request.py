"""Closing ONE trade because a person asked — `close.request`.

Same channel as `stop.request` and for the same reason: this loop already polls its own
instance directory, and that directory is the one thing the command centre and a running bot
both reach. It is a SECOND file rather than a flag on the first because it does a different
thing — it ends one trade and leaves the bot running, looking for its next setup.

⚠ The tests are weighted toward what must NOT happen, because the failure that matters here is
a trade being closed that nobody asked about — a stale file flattening the first trade of a
later run, or a filesystem error inventing an instruction. Losing a request is cheap by
comparison: the position is still open and you ask again.

The strategy is told, never the broker. Closing at the broker from here would leave the strategy
holding a position that is gone, which is the halt this whole feature exists to avoid.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from runner import LiveRunner  # noqa: E402


class _Ex:
    def __init__(self, in_trade=True):
        self.in_trade = in_trade
        self.asked = []

    def request_close(self, reason="commanded"):
        """Mirrors the real one: False when flat, and it never closes anything itself."""
        self.asked.append(reason)
        return self.in_trade


class _Ledger:
    def __init__(self):
        self.events = []

    def event(self, kind, **kw):
        self.events.append((kind, kw))

    def kinds(self):
        return [k for k, _ in self.events]


def _runner(tmp_path, in_trade=True):
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(bot_key="bot", display_name="Bot", instance_dir=tmp_path)
    r.notes, r.warns, r.alerts = [], [], []
    r.log = SimpleNamespace(
        info=lambda m, *a, **k: r.notes.append(m),
        warning=lambda m, *a, **k: r.warns.append(m),
        error=lambda m, *a, **k: r.warns.append(m),
    )
    r.ledger = _Ledger()
    r._notify_health = lambda m, **_kw: r.alerts.append(m)
    r.strategy = SimpleNamespace(execution=_Ex(in_trade))
    return r


# ── the request ───────────────────────────────────────────────────────────────
def test_a_request_reaches_the_STRATEGY_and_the_file_is_consumed(tmp_path):
    r = _runner(tmp_path)
    (tmp_path / "close.request").write_text("aaron asked")

    r._check_close_request()

    assert r.strategy.execution.asked == ["aaron asked"]
    assert not (tmp_path / "close.request").exists()
    assert "close_requested" in r.ledger.kinds()


def test_an_empty_file_is_still_a_request(tmp_path):
    """The file being THERE is the instruction. A note inside it is a courtesy."""
    r = _runner(tmp_path)
    (tmp_path / "close.request").write_text("")

    r._check_close_request()

    assert r.strategy.execution.asked == ["asked by hand"]


def test_asking_with_NOTHING_open_says_so_and_still_consumes_the_file(tmp_path):
    """🔴 The file must go whatever the answer. A request that survived being answered would
    fire again on the next bar, and then on the trade after that — which is the stale
    instruction hazard, arriving by a different door."""
    r = _runner(tmp_path, in_trade=False)
    (tmp_path / "close.request").write_text("oops")

    r._check_close_request()

    assert not (tmp_path / "close.request").exists()
    assert r.ledger.events[0][1]["accepted"] is False
    assert any("NOTHING TO CLOSE" in str(a) for a in r.alerts)


def test_no_file_means_nothing_happens(tmp_path):
    r = _runner(tmp_path)

    r._check_close_request()

    assert r.strategy.execution.asked == []
    assert r.ledger.kinds() == []


# ── what must NOT happen ──────────────────────────────────────────────────────
def test_a_STALE_request_is_cleared_at_startup(tmp_path):
    """Left behind by a crash, a failed shutdown or an aborted SSH call, it would otherwise
    flatten the FIRST trade of every later run, seconds after that trade opened, with nobody
    expecting it. The file may only ever mean *somebody asked while this process was alive*."""
    r = _runner(tmp_path)
    (tmp_path / "close.request").write_text("from a run that is long gone")

    r.clear_close_request()

    assert not (tmp_path / "close.request").exists()
    assert r.strategy.execution.asked == []


def test_an_unreadable_instance_dir_is_NOT_a_request(tmp_path, monkeypatch):
    """A transient filesystem error must not be able to flatten a live trade. Same default as
    the stop file, and safe against the failure THIS path causes."""
    r = _runner(tmp_path)

    def _boom(self):
        raise OSError("disk went away")

    monkeypatch.setattr(Path, "exists", _boom)
    r._check_close_request()

    assert r.strategy.execution.asked == []


def test_clearing_when_there_is_nothing_to_clear_is_silent(tmp_path):
    r = _runner(tmp_path)
    r.clear_close_request()
    assert r.notes == []
