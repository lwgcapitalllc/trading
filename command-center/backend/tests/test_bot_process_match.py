"""Which process IS a trading bot — the runner, with exactly that bot's key.

🔴 A STOPPED bot read RUNNING whenever any tool carrying its key was running (2026-09-11). Every
tool that acts on a bot takes the same flag — `promote.py --bot X`, the hourly
`watch_reentry.py --bot X`, the coordinator starting it — and the page matched the key anywhere in
the process list. MEASURED: the demo SOS Fade copy read RUNNING straight after its first deploy,
with no process of its own and no account.

Watched RED by mutation, one per rule:
    drop the `runner.py` requirement            -> the tool and coordinator cases red
    drop the end-of-key boundary                -> the `sos_fade_20` case red
    route the snapshot back to the loose match  -> test_the_PAGE_shows_... red
                                                   (it SURVIVED the helper-only tests)
    route the running set back to the loose one -> test_the_running_set_... red
    drop `runner.py` from the WMI filter        -> test_the_probe_and_the_kill_... red
    the snapshot helper as a raw substring      -> the helper and page tests red
"""

from __future__ import annotations

import pytest
from routers import bots

_PY = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
_RUNNER = rf"{_PY} C:\trading\algos\live\runner.py"

CASES = [
    # (process line, key, is it that bot's runner?)
    (rf"{_RUNNER} --bot sos_fade_demo --live", "sos_fade_demo", True),
    (rf'"{_PY}" C:\trading\algos\live\runner.py --bot sos_fade_2', "sos_fade_2", True),
    (rf"CommandLine={_RUNNER} --bot extreme_leg_2 --live", "extreme_leg_2", True),
    (rf"{_RUNNER} --live --bot extreme_leg_2", "extreme_leg_2", True),
    (rf"{_RUNNER} --bot=extreme_leg_2", "extreme_leg_2", True),
    (rf"{_PY} C:\trading\algos\tools\promote.py --bot sos_fade_2", "sos_fade_2", False),
    (rf"{_PY} C:\trading\algos\tools\watch_reentry.py --bot sos_fade_demo", "sos_fade_demo", False),
    (rf"{_PY} C:\trading\algos\bots\startup_coordinator.py --bot sos_fade_2", "sos_fade_2", False),
    (rf"{_RUNNER} --bot sos_fade_20 --live", "sos_fade_2", False),
    (rf"{_RUNNER} --bot sos_fade_demo --live", "sos_fade_2", False),
    (rf"{_PY} C:\trading\algos\live\my_runner.py --bot sos_fade_2", "sos_fade_2", False),
]


@pytest.mark.parametrize("line,key,expected", CASES)
def test_only_the_bots_own_runner_counts(line, key, expected):
    assert bots._is_bot_runner(line, key) is expected


def test_the_snapshot_reads_a_deploy_of_a_stopped_bot_as_STOPPED():
    procs = "\n".join(
        [
            rf"CommandLine={_RUNNER} --bot sos_fade_demo --live",
            rf"CommandLine={_PY} C:\trading\algos\tools\promote.py --bot sos_fade_2",
        ]
    )
    snap = {"procs": procs}
    assert bots._bot_runner_running(snap, "sos_fade_demo") is True
    assert bots._bot_runner_running(snap, "sos_fade_2") is False


def test_the_PAGE_shows_a_stopped_bot_being_deployed_as_STOPPED(monkeypatch):
    """Through the snapshot the Bots page reads, not the helper alone — routing the status back to
    the loose match survived the helper's own tests."""
    procs = "\n".join(
        [
            rf"CommandLine={_RUNNER} --bot sos_fade_demo --live",
            rf"CommandLine={_PY} C:\trading\algos\tools\promote.py --bot sos_fade_2",
        ]
    )
    monkeypatch.setattr(bots, "_fetch_vps_snapshot", lambda: {"procs": procs})
    status = {b.key: b.status for b in bots.get_snapshot().bots}
    assert status["sos_fade_demo"] == "RUNNING"
    assert status["sos_fade_2"] == "STOPPED"


def test_the_running_set_ignores_a_tool_carrying_the_key(monkeypatch):
    out = "\n".join(
        [
            rf"{_RUNNER} --bot sos_fade_demo --live",
            rf"{_PY} C:\trading\algos\tools\watch_reentry.py --bot extreme_leg_demo",
        ]
    )
    monkeypatch.setattr(bots, "_ssh", lambda cmd: out)
    running = bots._running_bot_keys()
    assert "sos_fade_demo" in running
    assert "extreme_leg_demo" not in running


def test_the_probe_and_the_kill_name_the_runner(monkeypatch):
    """So a forced stop never terminates the bot's own deploy or re-entry check, and the probe
    never waits on them as if they were the bot. Verified read-only on the box 2026-09-11."""
    sent = []

    def fake(cmd):
        sent.append(cmd)
        return "ProcessId\n9620\n" if "get processid" in cmd else ""

    monkeypatch.setattr(bots, "_ssh", fake)
    monkeypatch.setattr(bots._time, "sleep", lambda *_a: None)
    bots._kill_bot("sos_fade_2")
    wmi = [c for c in sent if "wmic process where" in c]
    assert wmi and all("runner.py" in c and "--bot sos_fade_2" in c for c in wmi), wmi
    assert any("call terminate" in c for c in wmi)
