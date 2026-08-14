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

import json
import time as _t

import pytest
from models import BotPromoteRequest
from routers import bots


@pytest.fixture
def vps(monkeypatch):
    state = {"out": "", "cmds": [], "killed": [], "launched": []}

    monkeypatch.setattr(bots, "_ssh", lambda c: (state["cmds"].append(c), state["out"])[1])
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


# ── which versions it moved between ───────────────────────────────────────────
#
# 🔴 The PROMOTED alert said only *"It is now running the code that was just deployed"* — a
# sentence a reader cannot check against anything, sent about the one action that changes what
# a live account trades. Aaron, 2026-08-14: *"The prompted message should say the version of the
# bot that was promoted from and to."* `promote.py` prints `##VERSIONS <from> <to>`.


@pytest.fixture
def sent(monkeypatch):
    """Capture the Telegram text instead of dropping it, so the wording is testable."""
    msgs: list[str] = []
    monkeypatch.setattr(bots, "_notify_telegram", lambda m, *a, **k: msgs.append(m))
    return msgs


def test_the_promoted_alert_names_the_version_it_moved_from_and_to(vps, sent):
    vps["out"] = f"  pinned abc123\n{bots._VERSION_MARK} 164 165\n{bots._PROMOTE_OK}"
    bots.promote_bot("MPC SOS Fade", REQ)
    assert sent, "no alert was sent"
    assert "v164 → v165" in sent[0]


def test_an_uncountable_side_reads_v_question_and_is_still_PRINTED(vps, sent):
    """A bot promoted before the version stamp existed has no "from". Dropping the line
    silently would make the message look complete while answering half the question; `v?` says
    which half is missing. And it must NEVER read `v0` — that is a version somebody could be
    on, and it is the value that misreported this field for its whole life."""
    vps["out"] = f"  pinned abc123\n{bots._VERSION_MARK} ? 165\n{bots._PROMOTE_OK}"
    bots.promote_bot("MPC SOS Fade", REQ)
    assert "v? → v165" in sent[0]
    assert "v0" not in sent[0]


def test_a_promote_with_no_version_line_still_reports_success(vps, sent):
    """An older `promote.py` on the VPS prints no marker at all. The alert must degrade to the
    sentence it always sent rather than inventing a version or failing to send."""
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    bots.promote_bot("MPC SOS Fade", REQ)
    assert sent and "deployed" in sent[0]
    assert "v?" not in sent[0] and "v0" not in sent[0]


def test_the_version_marker_is_stripped_from_what_the_user_reads(vps):
    """It is a channel for one caller, not output. Leaving it in puts `##VERSIONS 164 165` in
    the panel under the deploy button."""
    vps["out"] = f"  pinned abc123\n{bots._VERSION_MARK} 164 165\n{bots._PROMOTE_OK}"
    r = bots.promote_bot("MPC SOS Fade", REQ)
    assert bots._VERSION_MARK not in r.output
    assert r.output == "pinned abc123"


def test_a_FAILED_promote_sends_no_version_claim_at_all(vps, sent):
    """Nothing was deployed, so there is no "to" — and the alert is not sent either way. A
    version pair on a failed promote would describe a move that did not happen."""
    vps["out"] = f"  pinned abc123\n{bots._VERSION_MARK} 164 165\n{bots._PROMOTE_FAIL}"
    r = bots.promote_bot("MPC SOS Fade", REQ)
    assert r.ok is False
    assert sent == []


def test_a_malformed_version_line_is_refused_rather_than_half_read(vps):
    """Two tokens, three tokens, junk — anything that is not `<mark> <from> <to>` is *cannot
    say*. Reading the first number off a broken line is how a message comes to name a version
    nobody measured."""
    assert bots._parse_versions(f"{bots._VERSION_MARK} 164") == (None, None)
    assert bots._parse_versions(f"{bots._VERSION_MARK} 164 165 166") == (None, None)
    assert bots._parse_versions("nothing here") == (None, None)
    assert bots._parse_versions(f"{bots._VERSION_MARK} x y") == (None, None)


@pytest.mark.parametrize("n,expected", [(0, "v0"), (165, "v165"), (None, "v?")])
def test_the_backend_renders_an_unknown_version_as_v_question(n, expected):
    assert bots._vlabel(n) == expected


# ── the thread root ───────────────────────────────────────────────────────────
#
# A deploy is ONE event producing THREE messages from TWO machines: this router's PROMOTED, and
# the bot's own STOPPED and ONLINE. Aaron read them as three unrelated bubbles. The root is sent
# here and its id is written into the bot's instance directory, which is the channel those two
# processes already share.


def test_the_root_is_sent_BEFORE_the_bot_is_stopped(vps, sent, monkeypatch):
    """🔴 The ORDERING is the feature. The bot writes STOPPED the moment it notices its stop
    file, seconds from here — a root sent afterwards is not the root of anything.

    Nothing is lost by moving it: `restarted` was never a measurement (it was set to
    `ok and req.restart` unconditionally after the kill), so the old placement bought no
    knowledge the new one lacks.
    """
    order: list[str] = []
    monkeypatch.setattr(bots, "_notify_telegram", lambda m, *a, **k: order.append("alert") or 1)
    monkeypatch.setattr(bots, "_kill_bot", lambda k: order.append("kill") or "")
    monkeypatch.setattr(bots, "_set_alert_thread", lambda *a: order.append("thread"))
    vps["out"] = f"  pinned abc123\n{bots._VERSION_MARK} 164 165\n{bots._PROMOTE_OK}"
    bots.promote_bot("MPC SOS Fade", REQ)
    assert order == ["alert", "thread", "kill"]


def test_the_root_states_the_INTENT_because_the_replies_report_the_outcome(vps, sent):
    """It is sent before the restart, so it cannot claim the bot is running — the ONLINE that
    threads under it is what says that, from the process that would know."""
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    bots.promote_bot("MPC SOS Fade", REQ)
    assert "Restarting it now." in sent[0]
    assert "It is running it now" not in sent[0]


def test_no_thread_is_written_when_no_restart_was_asked_for(vps, sent, monkeypatch):
    """Without a restart the bot sends neither STOPPED nor ONLINE, so there is nothing to
    thread — and a file left in the instance directory would parent whatever it sends next."""
    wrote: list = []
    monkeypatch.setattr(bots, "_set_alert_thread", lambda *a: wrote.append(a))
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    bots.promote_bot(
        "MPC SOS Fade", BotPromoteRequest(pull=False, allow_dirty=False, restart=False)
    )
    assert wrote == []
    assert "Restart it to pick the new version up." in sent[0]


def test_an_UNSENDABLE_root_writes_no_thread_and_the_promote_still_succeeds(vps, monkeypatch):
    """`_notify_telegram` answers None when Telegram is unconfigured or refuses. Writing that
    would ask the bot to reply to nothing; failing the promote over it would be far worse."""
    monkeypatch.setattr(bots, "_notify_telegram", lambda *a, **k: None)
    ssh_calls: list = []
    monkeypatch.setattr(bots.subprocess, "run", lambda *a, **k: ssh_calls.append(a) or _Done())
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    r = bots.promote_bot("MPC SOS Fade", REQ)
    assert r.ok is True
    assert ssh_calls == [], "a null message id was written as a thread root"


class _Done:
    returncode = 0
    stdout = b""
    stderr = b""


def test_writing_the_thread_NEVER_raises(monkeypatch):
    """A deploy that failed because a Telegram convenience could not be written would be a
    spectacularly bad trade. The worst case is two unthreaded messages, which is what every
    deploy before this looked like."""

    def boom(*_a, **_k):
        raise OSError("ssh is down")

    monkeypatch.setattr(bots.subprocess, "run", boom)
    bots._set_alert_thread("mpc_sos_fade_demo", 4242)  # must not raise


def test_the_thread_payload_carries_an_EXPIRY(monkeypatch):
    """The guard that cannot be forgotten. A restart that never completes leaves nobody to
    delete the file, so the id has to go stale on its own — otherwise the next ONLINE, days
    later, replies under a deploy that failed."""
    captured: dict = {}

    def fake(cmd, **kw):
        captured["cmd"] = cmd
        captured["input"] = kw.get("input", b"")
        return _Done()

    monkeypatch.setattr(bots.subprocess, "run", fake)
    bots._set_alert_thread("mpc_sos_fade_demo", 4242)
    body = json.loads(captured["input"].decode())
    assert body["message_id"] == 4242
    assert body["expires_at"] > _t.time()
    # ⚠ over STDIN, never argv — the payload is JSON, and quoting braces through cmd is the kind
    # of escaping that works until a value changes shape.
    assert "4242" not in " ".join(captured["cmd"][2:])


@pytest.mark.parametrize("mid", [None, 0])
def test_a_missing_message_id_writes_nothing(monkeypatch, mid):
    calls: list = []
    monkeypatch.setattr(bots.subprocess, "run", lambda *a, **k: calls.append(a) or _Done())
    bots._set_alert_thread("mpc_sos_fade_demo", mid)
    assert calls == []
