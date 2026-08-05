"""Whether a promote worked is read from its EXIT CODE, not from its prose.

Promote is the one action in this router that changes what a bot trades. Its verdict used
to be a substring search on stdout — `"pinned" in out` for a promote, `"dry run" in out`
for a preview — while `promote.py` had returned a real exit code all along (0 on success,
1 on a dirty tree, a snapshot that does not import, or a missing source tree).

Two ways that fails, and both are silent: reword one `print` in promote.py and the verdict
flips, and a FAILURE whose message happens to contain the word reads as a success. The
second is the dangerous one — a failed promote reported as ok also restarts the bot.

The third state matters too. If the marker never arrives, we do not know what happened, and
that is not the same as "it failed" — the promote may well have deployed.
"""

import pytest

from routers import bots
from models import BotPromoteRequest


@pytest.fixture
def vps(monkeypatch):
    state = {"out": "", "cmds": [], "killed": [], "launched": []}

    monkeypatch.setattr(bots, "_ssh",
                        lambda c: (state["cmds"].append(c), state["out"])[1])
    monkeypatch.setattr(bots, "_kill_bot", lambda k: state["killed"].append(k) or "")
    monkeypatch.setattr(bots, "_launch_bot", lambda k: state["launched"].append(k) or "")
    monkeypatch.setattr(bots, "_notify_telegram", lambda *_a, **_k: None)
    monkeypatch.setattr(bots._time, "sleep", lambda *_a: None)
    return state


REQ = BotPromoteRequest(pull=False, allow_dirty=False, restart=True)


# ── The exit code decides ─────────────────────────────────────────────────────

def test_a_zero_exit_is_a_success(vps):
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    r = bots.promote_bot("MPC SOS Fade", REQ)
    assert r.ok is True
    assert r.restarted is True


def test_a_nonzero_exit_is_a_failure_even_when_the_output_says_pinned(vps):
    """The exact shape the substring check got wrong: promote.py prints the currently pinned
    hash while REFUSING to promote over a dirty tree. `"pinned" in out` called that a
    success — and then restarted the bot onto code that was never deployed."""
    vps["out"] = (
        "Refusing to promote — 3 uncommitted change(s) in the trees to deploy:\n"
        "  pinned e42a95c96bb2\n"
        f"{bots._PROMOTE_FAIL}"
    )
    r = bots.promote_bot("MPC SOS Fade", REQ)
    assert r.ok is False
    assert r.restarted is False
    assert vps["killed"] == [], "it restarted a bot after a refused promote"


def test_a_successful_promote_that_never_mentions_pinned_is_still_a_success(vps):
    """The other direction — reword one print and the old check goes dark."""
    vps["out"] = f"  deployed 93 files\n{bots._PROMOTE_OK}"
    assert bots.promote_bot("MPC SOS Fade", REQ).ok is True


def test_a_preview_is_judged_the_same_way(vps):
    vps["out"] = f"  dry run — nothing was deployed\n{bots._PROMOTE_OK}"
    assert bots.preview_bot_promote("MPC SOS Fade", REQ).ok is True
    vps["out"] = f"  ! the staged snapshot does not import\n{bots._PROMOTE_FAIL}"
    assert bots.preview_bot_promote("MPC SOS Fade", REQ).ok is False


# ── The third state ───────────────────────────────────────────────────────────

def test_no_reported_result_is_not_silently_a_failure(vps):
    """It takes the false branch — so nothing restarts and no alert fires — but the output
    says we do not know, because the promote may have deployed."""
    vps["out"] = "some output with no marker at all"
    r = bots.promote_bot("MPC SOS Fade", REQ)
    assert r.ok is False
    assert r.restarted is False
    assert "did not report an exit status" in r.output


def test_no_reported_result_on_a_preview_says_so_too(vps):
    vps["out"] = "truncated"
    assert "did not report an exit status" in bots.preview_bot_promote("MPC SOS Fade", REQ).output


# ── How the code is read off the far end ──────────────────────────────────────

def test_the_exit_code_is_tested_at_run_time_not_expanded_at_parse_time(vps):
    """`echo %errorlevel%` on one cmd line prints the code from BEFORE the command ran —
    cmd expands `%VAR%` at parse time. That trap looks like a working exit-code check and
    always answers 0, which is the failure this test exists to prevent."""
    vps["out"] = bots._PROMOTE_OK
    bots.promote_bot("MPC SOS Fade", REQ)
    cmd = vps["cmds"][0]
    assert "if errorlevel 1" in cmd
    assert "%errorlevel%" not in cmd


def test_the_marker_is_stripped_from_what_the_user_reads(vps):
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    r = bots.promote_bot("MPC SOS Fade", REQ)
    assert r.output == "pinned abc123"
