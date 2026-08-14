"""Tests for the fleet halt switch.

Weighted toward the ways this can wrongly say "fine", because that is the failure mode nobody sees:
a switch that reports CLEAR when it could not read anything looks identical to a healthy fleet, and
it fails on exactly the day it is needed. The happy paths get one test each.

Every test uses a REAL temp directory rather than a mock, because the whole point of the module is
what the filesystem does at the edges — `Path.exists()` swallowing `OSError` is the defect being
guarded against, and a mocked filesystem is the one thing that cannot reproduce it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from algos.shared.fleet_halt import (  # noqa: E402
    DEFAULT_FLAG_NAME,
    FleetHaltReading,
    flag_path,
    read_fleet_halt,
)


def test_no_flag_is_not_a_halt(tmp_path):
    r = read_fleet_halt(tmp_path)
    assert r.halted is False
    assert r.readable is True
    assert r.kind == "clear"


def test_a_flag_halts_and_carries_its_reason(tmp_path):
    (tmp_path / DEFAULT_FLAG_NAME).write_text("spread blew out on the open", encoding="utf-8")
    r = read_fleet_halt(tmp_path)
    assert r.halted is True
    assert r.readable is True
    assert r.reason == "spread blew out on the open"
    assert r.kind == "requested"


def test_an_EMPTY_flag_still_halts(tmp_path):
    """The flag's PRESENCE is the instruction. Somebody in a hurry types `type nul > FLEET_HALT`
    and the switch has to work — treating an empty file as "no reason, therefore no halt" would
    make the fastest way to pull it the one way that does nothing."""
    (tmp_path / DEFAULT_FLAG_NAME).write_text("", encoding="utf-8")
    r = read_fleet_halt(tmp_path)
    assert r.halted is True
    assert r.reason  # a stand-in reason, never blank — the alert has to say something
    assert DEFAULT_FLAG_NAME in r.reason


def test_a_MISSING_DIRECTORY_halts_rather_than_reading_as_clear(tmp_path):
    """The trap this module exists for.

    `os.stat(dir/FLEET_HALT)` on a missing parent raises FileNotFoundError — byte-identical to the
    flag simply not being there. Without the separate directory probe, deleting the folder is a
    silent way to disable the switch, and nothing anywhere would report it.
    """
    gone = tmp_path / "not_there"
    r = read_fleet_halt(gone)
    assert r.halted is True
    assert r.readable is False
    assert r.kind == "unreadable"
    assert "cannot read the halt directory" in r.reason


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read a 000 directory")
def test_an_UNREADABLE_DIRECTORY_halts(tmp_path):
    """A permissions failure is 'cannot ask', and cannot-ask halts (Aaron, 2026-08-09).

    This is the case `Path.exists()` gets wrong: it catches the OSError and answers False, i.e.
    'no halt requested', which is the reassuring answer produced by a broken system.
    """
    d = tmp_path / "locked"
    d.mkdir()
    (d / DEFAULT_FLAG_NAME).write_text("halt", encoding="utf-8")
    d.chmod(0o000)
    try:
        r = read_fleet_halt(d)
        assert r.halted is True
        assert r.readable is False
        assert "cannot read the halt flag" in r.reason
    finally:
        d.chmod(0o700)  # or tmp_path cleanup fails and takes the whole session's teardown with it


def test_pathlib_exists_cannot_tell_a_missing_FLAG_from_a_missing_BOX(tmp_path):
    """Pins the DEFECT this module is shaped around, so the fix cannot be 'simplified' back into it.

    Both calls below answer False, and they mean opposite things: the first is a healthy fleet with
    nobody pulling the switch, the second is a bot that has no way to be told anything. `stat`
    raises FileNotFoundError for BOTH — the errno is identical — which is why `read_fleet_halt`
    probes the DIRECTORY separately rather than trusting one answer about the file.

    ⚠ Deliberately NOT asserting anything about `exists()` and a PERMISSION error: that is version-
    dependent (3.9 propagates it, later versions swallow it), the Mac here runs 3.9 and the VPS runs
    3.11, and a test that pins a CPython version detail would go red on an upgrade for no reason
    this module cares about. The ENOENT collision below is true on every version and is the whole
    justification for the directory probe.
    """
    (tmp_path / DEFAULT_FLAG_NAME).unlink(missing_ok=True)
    assert (tmp_path / DEFAULT_FLAG_NAME).exists() is False  # healthy: no halt requested
    assert (tmp_path / "gone" / DEFAULT_FLAG_NAME).exists() is False  # broken: cannot be told
    # ...and the module tells them apart, which is the point.
    assert read_fleet_halt(tmp_path).halted is False
    assert read_fleet_halt(tmp_path / "gone").halted is True


def test_the_flag_sits_at_the_algos_ROOT_not_in_an_instance_dir():
    """A fleet switch nested under one bot's instance directory would be a per-bot switch wearing
    the wrong name, and the next person would put a second one under the other bot."""
    p = flag_path()
    assert p.name == DEFAULT_FLAG_NAME
    assert p.parent.name == "algos"
    assert "instances" not in p.parts


def test_a_reading_is_immutable():
    """The runner latches on this value and passes it to an alert; a caller that could flip
    `halted` after the fact would make the ledger record and the message disagree."""
    r = FleetHaltReading(True, "why", readable=True)
    with pytest.raises(Exception):
        r.halted = False  # type: ignore[misc]
