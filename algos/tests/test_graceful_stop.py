"""Stopping a bot by ASKING, not by killing it.

**Why this exists.** Every deliberate stop in this system was a `wmic ... call terminate` — a
hard kill — so the bot never reached the `finally` that writes its `shutdown` record. The next
startup then reported, correctly and uselessly, *"the previous run ended WITHOUT a shutdown
record: it was killed, it crashed, or the box went down."*

That sentence is the **silent-death detector** (`algos/CLAUDE.md` → *The daily record*): no
shutdown record ⇒ the process was killed or the box died. It only carries information if a
DELIBERATE stop leaves one. It did not, so it fired on every restart anybody performed on
purpose — and an alarm that fires when you press the button is one you learn to scroll past,
which was steadily costing the only signal that a bot had died without saying so.

**Why a file and not a signal.** Windows has no usable SIGTERM for a console process
(`taskkill` without `/f` posts WM_CLOSE, which a Python console app never receives). A file fits
what this loop already is: something that polls its own instance directory every few seconds and
already re-reads its config from there.

⚠ The tests are weighted toward the ways this could be WORSE than the kill it replaces — a stale
request stopping a healthy bot seconds after boot, or a filesystem error inventing one — because
a bot that will not stay up is a far worse failure than a noisy chip.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from runner import LiveRunner  # noqa: E402





def _stop_runner(tmp_path):
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(bot_key="bot", instance_dir=tmp_path)
    r.notes, r.warns = [], []
    r.log = SimpleNamespace(info=lambda m, *a, **k: r.notes.append(m),
                            warning=lambda m, *a, **k: r.warns.append(m),
                            error=lambda m, *a, **k: r.warns.append(m))
    return r


def test_a_stop_request_file_is_seen(tmp_path):
    r = _stop_runner(tmp_path)
    assert r._stop_file_present() is False
    r.stop_file_path().write_text("stop")
    assert r._stop_file_present() is True


def test_a_stale_stop_request_is_cleared_at_startup(tmp_path):
    """🔴 The one way this could be WORSE than the kill it replaces.

    A stop file left behind by a crash, a failed shutdown or an aborted SSH call would stop
    every subsequent start seconds after boot — and a bot that will not stay up is a far worse
    failure than a noisy chip. `run()` clears it before the loop, so the file can only ever mean
    "somebody asked while THIS process was alive".
    """
    r = _stop_runner(tmp_path)
    r.stop_file_path().write_text("stop")
    r.clear_stop_request()
    assert r._stop_file_present() is False
    assert any("stale" in n for n in r.notes)


def test_clearing_when_there_is_nothing_to_clear_is_silent(tmp_path):
    """Called on every startup. A log line per boot saying it found nothing is noise."""
    r = _stop_runner(tmp_path)
    r.clear_stop_request()
    assert r.notes == [] and r.warns == []


def test_an_unreadable_instance_dir_is_not_a_stop_request(tmp_path, monkeypatch):
    """⚠ Guessing True here would let a transient filesystem error take a live bot down. The
    safe direction is not symmetric: a missed stop is a button you press twice, an invented one
    is a bot that stops trading for no reason anybody can see."""
    r = _stop_runner(tmp_path)

    def _boom(self):
        raise OSError("disk gone")

    monkeypatch.setattr(Path, "exists", _boom)
    assert r._stop_file_present() is False


def test_a_clear_that_fails_does_not_stop_the_bot_starting(tmp_path, monkeypatch):
    """The worst case of carrying on is one clean shutdown right after boot, which is visible
    and recoverable. Refusing to start a trading bot because a marker file would not delete is
    the worse of the two."""
    r = _stop_runner(tmp_path)
    r.stop_file_path().write_text("stop")

    def _boom(self):
        raise OSError("locked")

    monkeypatch.setattr(Path, "unlink", _boom)
    r.clear_stop_request()                        # must not raise
    assert any("Could not clear" in w for w in r.warns)
