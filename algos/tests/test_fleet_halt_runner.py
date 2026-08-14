"""The fleet switch as the RUNNER sees it — does pulling it actually stop this bot placing orders?

`test_fleet_halt.py` tests the reader in isolation. This tests the wiring, which is where a safety
feature usually fails: the file is read correctly, and then nothing acts on it.

Every test drives `LiveRunner._check_fleet_halt` directly rather than turning the whole loop. The
loop path is already covered by `test_mt5_link.py`; what is worth pinning here is the DECISION —
halt the bridge, latch, alert once, and say which of the two situations it is.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "live"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

import runner as runner_mod  # noqa: E402

from algos.shared.fleet_halt import DEFAULT_FLAG_NAME, FleetHaltReading  # noqa: E402

LiveRunner = runner_mod.LiveRunner


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


def _runner(monkeypatch, reading):
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(bot_key="bot", display_name="Bot")
    r.bridge = _Bridge()
    r.ledger = _Ledger()
    r._fleet_halted = False
    r.errors, r.alerts = [], []
    r.log = SimpleNamespace(
        info=lambda m, *a, **k: None,
        warning=lambda m, *a, **k: None,
        error=lambda m, *a, **k: r.errors.append(m),
    )
    monkeypatch.setattr(r, "_notify_health", lambda text: r.alerts.append(text))
    monkeypatch.setattr(runner_mod, "read_fleet_halt", lambda *a, **k: reading)
    return r


def test_a_clear_switch_does_nothing_at_all(monkeypatch):
    """The normal state, run every ~10 seconds forever. It must not log, alert or write a ledger
    record — a health stream that gets a line per poll is one nobody can read."""
    r = _runner(monkeypatch, FleetHaltReading(False, "", readable=True))
    r._check_fleet_halt()
    assert r._fleet_halted is False
    assert r.bridge.halts == [] and r.ledger.events == [] and r.alerts == [] and r.errors == []


def test_pulling_the_switch_HALTS_THE_BRIDGE(monkeypatch):
    """The whole point. Reading the flag and not stopping the thing that places orders is the
    failure this file exists to catch."""
    r = _runner(monkeypatch, FleetHaltReading(True, "spread blew out", readable=True))
    r._check_fleet_halt()
    assert r._fleet_halted is True
    assert len(r.bridge.halts) == 1
    assert "spread blew out" in r.bridge.halts[0]
    assert "fleet halt" in r.bridge.halts[0]  # the bridge's own reason names WHO stopped it


def test_the_halt_is_recorded_and_alerted_ONCE(monkeypatch):
    """A switch left on over a weekend must not send one message per poll — that is how the room
    carrying every other health alert gets muted."""
    r = _runner(monkeypatch, FleetHaltReading(True, "why", readable=True))
    for _ in range(5):
        r._check_fleet_halt()
    assert len(r.alerts) == 1
    assert len(r.ledger.events) == 1
    assert r.ledger.events[0][0] == "fleet_halt"
    assert len(r.bridge.halts) == 1


def test_it_LATCHES_so_clearing_the_flag_does_not_put_the_bot_back_in_the_market(monkeypatch):
    """⚠ The design decision most likely to be "simplified" later.

    A flapping or intermittently-unreadable filesystem would otherwise toggle a live book on and
    off with nobody watching. Resume is: clear the flag, restart the bots.
    """
    r = _runner(monkeypatch, FleetHaltReading(True, "why", readable=True))
    r._check_fleet_halt()
    monkeypatch.setattr(
        runner_mod, "read_fleet_halt", lambda *a, **k: FleetHaltReading(False, "", readable=True)
    )
    r._check_fleet_halt()
    assert r._fleet_halted is True  # still halted
    assert len(r.bridge.halts) == 1  # and it did not un-halt or re-halt


def test_an_UNREADABLE_switch_halts_and_the_record_says_which_kind_it_was(monkeypatch):
    """Cannot-read halts (Aaron, 2026-08-09), and the ledger keeps `readable` so a reader can tell
    "somebody pulled it" from "this box cannot read its own filesystem". Those need different
    fixes, and collapsing them into one boolean would be the exact absence-as-value trap the
    reader module is shaped around."""
    r = _runner(monkeypatch, FleetHaltReading(True, "cannot read the halt flag", readable=False))
    r._check_fleet_halt()
    assert r._fleet_halted is True
    assert r.bridge.halts
    assert r.ledger.events[0][1]["readable"] is False


def test_the_alert_tells_the_reader_that_clearing_alone_will_not_resume(monkeypatch):
    """The one instruction somebody acting at 3am needs and would otherwise get wrong. A message
    that says only "halted" leaves them deleting a file and waiting for trades that never come."""
    r = _runner(monkeypatch, FleetHaltReading(True, "why", readable=True))
    r._check_fleet_halt()
    text = r.alerts[0]
    assert "restart" in text.lower()
    assert "stop" in text.lower() or "position" in text.lower()


def test_a_halt_with_NO_BRIDGE_yet_still_latches_and_reports(monkeypatch):
    """The bridge is built after the terminal connects, so a switch pulled during a start-up
    retry is read before there is anything to halt. Skipping the record because the bridge is
    None would lose the one trace that the bot saw it."""
    r = _runner(monkeypatch, FleetHaltReading(True, "why", readable=True))
    r.bridge = None
    r._check_fleet_halt()  # must not raise
    assert r._fleet_halted is True
    assert r.ledger.events and r.alerts


def test_the_flag_name_is_the_one_the_tool_and_the_docs_write():
    """A reader and a writer that disagree about the filename is a switch that silently does
    nothing, and both sides look correct in isolation."""
    assert DEFAULT_FLAG_NAME == "FLEET_HALT"
