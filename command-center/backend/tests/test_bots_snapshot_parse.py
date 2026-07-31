"""Parsing the batched VPS snapshot.

Everything on the Bots page comes from ONE `ssh` call whose output is a set of
`===SECTION===` markers. Two Windows-cmd behaviours have silently merged those sections,
and both failed the same way — no exception, no empty result, just a bot reporting nothing
about itself while showing as RUNNING:

  * `if exist X (type X) & next` binds `next` to the if-block, so a MISSING file swallows
    every section after it;
  * `type` emits no trailing newline, so the next marker lands glued to the file's last
    character (`}===TELEGRAM_START===`) and stops being recognised as a marker at all.

The second only appears once a state file has CONTENT, i.e. after a bot has run once — so
it cannot be caught before the thing it breaks starts mattering. Hence these tests.
"""

import json

from routers import bots


def _state_blob() -> str:
    return json.dumps({
        "mpc_sos_fade_demo": {
            "name": "MPC SOS Fade", "status": "live", "started": 1785471363.6,
            "account": 700107749, "balance": 2000.0, "trades_today": 0,
            "last_updated": "2026-07-31T04:18:43+00:00",
        },
        "last_updated": "2026-07-31T04:18:43.940729",
    }, indent=2)


def test_a_section_marker_glued_to_the_previous_line_is_still_found():
    """`type` leaves no trailing newline. Without the `echo.` guard in the fetch command
    this is exactly what comes back, and BOTH sections are lost."""
    raw = (f"===STATE_MPC_SOS_FADE===\n{_state_blob()}"
           '===TELEGRAM_START===\n{"started": 1785468642.7}')
    sections = bots._parse_sections(raw, "head")
    assert "telegram_start" in sections, "the glued marker was not recognised"
    json.loads(sections["state_mpc_sos_fade"])      # must be parseable on its own


def test_bot_state_is_read_out_of_its_section():
    raw = f"===STATE_MPC_SOS_FADE===\n{_state_blob()}\n===TELEGRAM_START===\n"
    states = bots._parse_bot_states(bots._parse_sections(raw, "head"))
    assert states["mpc_sos_fade_demo"]["balance"] == 2000.0


def test_a_bot_that_has_never_run_leaves_the_later_sections_intact():
    """The empty-state-file case — the first cmd quirk. A bot with no state file yet must
    not take the Telegram row down with it."""
    raw = ('===STATE_MPC_SOS_FADE===\n'
           '===TELEGRAM_START===\n{"started": 1785468642.7}')
    sections = bots._parse_sections(raw, "head")
    assert sections["state_mpc_sos_fade"] == ""
    assert json.loads(sections["telegram_start"])["started"] == 1785468642.7


def test_every_declared_state_section_has_a_path_to_fetch_it():
    """The fetch command is BUILT from _BOT_STATE_SECTIONS. A section with no path entry
    would raise KeyError mid-snapshot; a path with no section would never be fetched."""
    assert {s for s, _ in bots._BOT_STATE_SECTIONS} == set(bots._BOT_STATE_PATHS)


def test_schtasks_paths_resolve_to_task_names():
    """schtasks reports `\\SYS_MONITOR`, not `SYS_MONITOR`. Matching the raw value meant
    _parse_tasks returned {} and EVERY job read UNKNOWN from the day it was written."""
    raw = ('===TASKS===\n'
           '"\\SYS_MONITOR","N/A","Disabled"\n'
           '"\\SYS_TELEGRAM","N/A","Running"\n'
           '"\\Folder\\SYS_REPORTER","N/A","Ready"\n')
    tasks = bots._parse_tasks(bots._parse_sections(raw, "head"))
    assert tasks["SYS_MONITOR"] == "Disabled"
    assert tasks["SYS_TELEGRAM"] == "Running"
    assert tasks["SYS_REPORTER"] == "Ready"        # nested folders resolve too


def test_the_bot_key_is_what_identifies_the_process():
    """`runner.py --bot <key>` — the key is on the commandline. Matching on the script name
    would make every live bot indistinguishable the moment there are two."""
    snap = {"procs": r"python  C:\trading\algos\live\runner.py --bot mpc_sos_fade_demo"}
    assert bots._is_python_running(snap, "mpc_sos_fade_demo")
    assert not bots._is_python_running(snap, "some_other_bot")
