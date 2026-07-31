"""The crash watchdog, and the heartbeat it depends on.

**Why this file exists.** SYS_MONITOR was written with two checks: the process is gone, and
the process is alive but its loop has stopped turning. The second one had never worked.
Nothing wrote the `heartbeat` field it reads, and the check reads a missing field as 0 and
then asks `0 > 300` — so it was permanently false. Found on 2026-07-31, while enabling the
task, by reading it rather than by running it.

That failure mode is the reason for this file. A watchdog that breaks LOUDLY costs an hour;
a watchdog that breaks SILENTLY costs whatever the unwatched thing does next, because an
empty alert channel is indistinguishable from a healthy system. So the tests below pin the
contract from both ends — the runner writes the stamp, the monitor reads it, and neither
side can quietly stop honouring it without going red.

No MT5 and no Telegram: `send_alert` is stubbed, so a test can never post to a real chat.
"""

from __future__ import annotations

import ast
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared"),
           str(_REPO / "algos" / "notifications")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import monitor                                                       # noqa: E402
from runner import LiveRunner                                        # noqa: E402


# ── the runner's half of the contract ───────────────────────────────────────────
class _StateModule:
    """Stands in for the `bot_state` module the runner writes through."""

    def __init__(self):
        self.written = {}

    def write_bot(self, bot_key, updates):
        self.written.setdefault(bot_key, {}).update(updates)


def _runner(monkeypatch, *, balance_raises=False):
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(bot_key="bot", account=1, symbol="XAUUSD.s",
                            strategy_version="1.0.0")
    r.bridge = SimpleNamespace(state=SimpleNamespace(value="idle"))
    r.source_hash = "0123456789abcdef"
    r.dry_run = True
    r.feed = SimpleNamespace(last_bar_time=None)
    r.warnings = []
    r.log = SimpleNamespace(info=lambda *a, **k: None,
                            warning=lambda m: r.warnings.append(m),
                            error=lambda *a, **k: None)

    # The runner imports MetaTrader5 INSIDE _heartbeat, so a fake module in sys.modules is
    # enough — no MT5 install, and it works identically on the Mac and the VPS.
    def _account_info():
        if balance_raises:
            raise RuntimeError("terminal not connected")
        return SimpleNamespace(balance=2000.0)

    monkeypatch.setitem(sys.modules, "MetaTrader5",
                        SimpleNamespace(account_info=_account_info))
    return r


def test_the_loop_stamps_a_heartbeat(monkeypatch):
    """The whole feature in one assertion: SYS_MONITOR has nothing to read without this."""
    r = _runner(monkeypatch)
    st = _StateModule()
    r._heartbeat(st)

    written = st.written["bot"]
    assert "heartbeat" in written, "no stamp — the stalled-loop check goes permanently blind"
    assert abs(written["heartbeat"] - time.time()) < 5
    assert written["balance"] == 2000.0


def test_a_broken_balance_read_does_not_swallow_the_heartbeat(monkeypatch):
    """The balance lookup is best-effort and the stamp is not.

    These were one try block, so any MT5 hiccup dropped the heartbeat too — which would
    have reported a perfectly healthy loop as stalled the moment the watchdog worked at all.
    """
    r = _runner(monkeypatch, balance_raises=True)
    st = _StateModule()
    r._heartbeat(st)

    written = st.written["bot"]
    assert abs(written["heartbeat"] - time.time()) < 5
    assert written["balance"] is None
    assert any("Balance read failed" in w for w in r.warnings)


# ── the monitor's half ──────────────────────────────────────────────────────────
@pytest.fixture
def watch(monkeypatch):
    """Drive `check_bot` with a scripted bot state, capturing alerts instead of sending."""
    sent = []
    monkeypatch.setattr(monitor, "send_alert", lambda msg: sent.append(msg))
    monkeypatch.setattr(monitor, "is_running", lambda script: True)
    monkeypatch.setattr(monitor._bot_state, "set_status", lambda *a, **k: None)

    def run(live_state, carried=None):
        monkeypatch.setattr(monitor._bot_state, "read_bot", lambda k: live_state)
        state = {"running": True, **(carried or {})}
        return monitor.check_bot("mpc_sos_fade_demo", {"mpc_sos_fade_demo": state},
                                 "2026-07-31")

    return SimpleNamespace(run=run, sent=sent)


def test_a_fresh_heartbeat_is_not_stale(watch):
    out = watch.run({"heartbeat": time.time()})
    assert watch.sent == []
    assert not out["stale_alerted"]


def test_an_old_heartbeat_raises_the_stall_alert(watch):
    out = watch.run({"heartbeat": time.time() - 20 * 60})
    assert len(watch.sent) == 1
    assert "Loop Stalled" in watch.sent[0]
    assert out["stale_alerted"]


def test_the_stall_alert_is_sent_once_not_every_minute(watch):
    """The task runs every 60s. Re-alerting on each pass would train Aaron to mute it, and a
    muted channel is the same as no watchdog."""
    watch.run({"heartbeat": time.time() - 20 * 60}, carried={"stale_alerted": True})
    assert watch.sent == []


def test_a_recovered_loop_says_so(watch):
    out = watch.run({"heartbeat": time.time()}, carried={"stale_alerted": True})
    assert len(watch.sent) == 1
    assert "Recovered" in watch.sent[0]
    assert not out["stale_alerted"]


def test_a_running_bot_that_never_stamped_is_stale_not_silent(watch):
    """THE regression. A missing `heartbeat` used to read as 0 and disable the check.

    It now falls back to `started`, so a bot that booted 20 minutes ago and has never
    stamped is reported as the stalled bot it is.
    """
    out = watch.run({"started": time.time() - 20 * 60})
    assert len(watch.sent) == 1
    assert "Loop Stalled" in watch.sent[0]
    assert out["stale_alerted"]


def test_a_bot_that_just_booted_is_given_time_to_warm_up(watch):
    """Connecting to MT5 and replaying 5,000 warmup bars happens before the first stamp.
    A false alarm on every single start is how a watchdog gets turned off."""
    assert watch.run({"started": time.time() - 30}) is not None
    assert watch.sent == []


# ── the two sides agree about which bots exist ──────────────────────────────────
def _coordinator_sequence():
    """Read STARTUP_SEQUENCE out of the launcher WITHOUT importing it.

    `startup_coordinator.py` hardcodes `Path("C:/trading/algos")` and imports from it at
    module scope, so it cannot be imported anywhere but the VPS. Parsing keeps this check
    running on the machine where the mistake actually gets made.
    """
    src = (_REPO / "algos" / "bots" / "startup_coordinator.py").read_text()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "STARTUP_SEQUENCE":
            out = []
            for elt in node.value.elts:
                bot_key = elt.elts[0].value
                argv = [a.value for a in elt.elts[3].elts]
                out.append((bot_key, argv))
            return out
    raise AssertionError("STARTUP_SEQUENCE not found in startup_coordinator.py")


def test_every_bot_the_vps_starts_is_watched():
    """A bot added to the launcher and forgotten here is a bot that can die unnoticed —
    and it fails in the quietest possible way, because everything still looks fine."""
    for bot_key, _ in _coordinator_sequence():
        assert bot_key in monitor.BOTS, f"{bot_key} boots on the VPS but nothing watches it"


def test_the_monitor_matches_the_commandline_the_launcher_actually_produces():
    """`is_running` greps the process commandline for `BOTS[key]["script"]`.

    Every live bot is `runner.py`, so the match has to be the bot_key in argv. If the two
    drift apart the watchdog reports a healthy bot as permanently offline (alert fatigue),
    or worse, matches a DIFFERENT bot's process and reports a dead one as alive.
    """
    for bot_key, argv in _coordinator_sequence():
        needle = monitor.BOTS[bot_key]["script"]
        assert needle in " ".join(argv), (
            f"{bot_key}: monitor greps for {needle!r}, which never appears in {argv}")


def test_no_bot_is_watched_that_nothing_can_start():
    """The mirror of the above — a stale entry alerts forever about a bot that does not
    exist, which is the other way to get the channel muted."""
    started = {k for k, _ in _coordinator_sequence()}
    assert set(monitor.BOTS) <= started, (
        f"watched but never launched: {set(monitor.BOTS) - started}")


def test_the_stall_threshold_is_well_clear_of_the_poll_interval():
    """`LOG_STALE_SECS` has to be a large multiple of how often the loop actually turns, or
    one slow broker call becomes a 3am alert."""
    import live_config

    poll = live_config.LiveConfig.__dataclass_fields__["poll_seconds"].default
    assert monitor.LOG_STALE_SECS >= poll * 10
