"""A dead SSH must not render as "every bot is stopped".

`_ssh` used to discard the return code and the stderr and hand back stdout. A broken ssh
exits **255 with empty stdout and raises nothing**, so `get_snapshot` got empty sections and
reported every bot STOPPED with a null balance — no error, no banner, nothing on the page
able to say the question was never answered. That is the same defect as the live bot reading
a dead MT5 link as a quiet market, one layer up and in the other direction.

The line these tests defend: **`""` because nothing is running, and `""` because nobody
answered, must not be the same value.** They are deliberately written against the
`subprocess.run` contract — return code, stdout, stderr — rather than against a stubbed
`_ssh`, because the bug lived in how that contract was read.
"""

import subprocess

import pytest
from fastapi import HTTPException
from routers import bots


class _Result:
    def __init__(self, code: int, out: bytes = b"", err: bytes = b""):
        self.returncode = code
        self.stdout = out
        self.stderr = err


def _run(monkeypatch, result: _Result):
    monkeypatch.setattr(bots.subprocess, "run", lambda *_a, **_k: result)


# ── The distinction ───────────────────────────────────────────────────────────


def test_empty_output_from_a_working_ssh_is_a_real_answer(monkeypatch):
    """No bot running ⇒ wmic prints nothing ⇒ empty string, exit 0. Not an error."""
    _run(monkeypatch, _Result(0, b""))
    assert bots._ssh("wmic ...") == ""


def test_ssh_that_could_not_connect_raises_instead_of_returning_empty(monkeypatch):
    _run(
        monkeypatch,
        _Result(255, b"", b"ssh: connect to host forexvps port 22: Operation timed out"),
    )
    with pytest.raises(bots.VpsUnreachable) as e:
        bots._ssh("wmic ...")
    assert "connect to host" in str(e.value)


def test_the_stderr_is_carried_not_swallowed(monkeypatch):
    """The reason is the only actionable part — a bare "failed" sends you to the VPS to
    look for a problem that is on this laptop."""
    _run(monkeypatch, _Result(255, b"", b"Permission denied (publickey)"))
    with pytest.raises(bots.VpsUnreachable) as e:
        bots._ssh("whoami")
    assert "publickey" in str(e.value)


def test_a_silent_255_still_raises_with_something_to_read(monkeypatch):
    _run(monkeypatch, _Result(255, b"", b""))
    with pytest.raises(bots.VpsUnreachable) as e:
        bots._ssh("whoami")
    assert str(e.value).strip()


# ── The codes that are NOT a connection failure ───────────────────────────────


def test_a_remote_command_failing_is_ordinary_and_must_not_raise(monkeypatch):
    """`type` on a missing state file exits 1, and `wmic … call terminate` that matched
    nothing exits non-zero too. Half the commands in this module end in `2>nul` precisely
    because failing is the normal case — raising on those would break every one."""
    for code in (1, 2, 4, 9009):
        _run(monkeypatch, _Result(code, b""))
        assert bots._ssh("type C:\\missing.json 2>nul") == ""


def test_a_255_that_printed_something_is_believed(monkeypatch):
    """255 is OpenSSH's own reserved code, but a remote program may use it too. If output
    came back, the connection plainly worked — trust the output."""
    _run(monkeypatch, _Result(255, b"some real output"))
    assert bots._ssh("whatever") == "some real output"


# ── What the page sees ────────────────────────────────────────────────────────


def test_the_snapshot_endpoint_errors_rather_than_reporting_every_bot_stopped(monkeypatch):
    _run(monkeypatch, _Result(255, b"", b"ssh: Could not resolve hostname forexvps"))
    with pytest.raises(HTTPException) as e:
        bots.get_snapshot()
    assert e.value.status_code == 502
    assert "Cannot reach the VPS" in e.value.detail


def test_a_timeout_is_still_a_504_not_a_502(monkeypatch):
    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=30)

    monkeypatch.setattr(bots.subprocess, "run", boom)
    with pytest.raises(HTTPException) as e:
        bots.get_snapshot()
    assert e.value.status_code == 504
