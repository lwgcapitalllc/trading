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

# ⚠ Every call below names the bot by its KEY. It said "SOS Fade" until 2026-09-11, when the demo
# copy took the same display name and a name two bots share became a refusal (`_resolve_bot`).


# ── The exit code decides ─────────────────────────────────────────────────────


def test_a_zero_exit_is_a_success(vps):
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    r = bots.promote_bot("sos_fade_demo", REQ)
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
    r = bots.promote_bot("sos_fade_demo", REQ)
    assert r.ok is False
    assert r.restarted is False
    assert vps["killed"] == [], "it restarted a bot after a refused promote"


def test_a_successful_promote_that_never_mentions_pinned_is_still_a_success(vps):
    """The other direction — reword one print and the old check goes dark."""
    vps["out"] = f"  deployed 93 files\n{bots._PROMOTE_OK}"
    assert bots.promote_bot("sos_fade_demo", REQ).ok is True


def test_a_preview_is_judged_the_same_way(vps):
    vps["out"] = f"  dry run — nothing was deployed\n{bots._PROMOTE_OK}"
    assert bots.preview_bot_promote("sos_fade_demo", REQ).ok is True
    vps["out"] = f"  ! the staged snapshot does not import\n{bots._PROMOTE_FAIL}"
    assert bots.preview_bot_promote("sos_fade_demo", REQ).ok is False


# ── The third state ───────────────────────────────────────────────────────────


def test_no_reported_result_is_not_silently_a_failure(vps):
    """It takes the false branch — so nothing restarts and no alert fires — but the output
    says we do not know, because the promote may have deployed."""
    vps["out"] = "some output with no marker at all"
    r = bots.promote_bot("sos_fade_demo", REQ)
    assert r.ok is False
    assert r.restarted is False
    assert "did not report an exit status" in r.output


def test_no_reported_result_on_a_preview_says_so_too(vps):
    vps["out"] = "truncated"
    assert "did not report an exit status" in bots.preview_bot_promote("sos_fade_demo", REQ).output


# ── How the code is read off the far end ──────────────────────────────────────


def test_the_exit_code_is_tested_at_run_time_not_expanded_at_parse_time(vps):
    """`echo %errorlevel%` on one cmd line prints the code from BEFORE the command ran —
    cmd expands `%VAR%` at parse time. That trap looks like a working exit-code check and
    always answers 0, which is the failure this test exists to prevent."""
    vps["out"] = bots._PROMOTE_OK
    bots.promote_bot("sos_fade_demo", REQ)
    cmd = vps["cmds"][0]
    assert "if errorlevel 1" in cmd
    assert "%errorlevel%" not in cmd


def test_the_marker_is_stripped_from_what_the_user_reads(vps):
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    r = bots.promote_bot("sos_fade_demo", REQ)
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
    bots.promote_bot("sos_fade_demo", REQ)
    assert sent, "no alert was sent"
    assert "v164 → v165" in sent[0]


def test_the_PROMOTED_root_lands_in_the_bots_OWN_accounts_room(vps, monkeypatch):
    """🔴 The thread depends on it. The bot's STOPPED and ONLINE are REPLIES to this message, sent
    from the box into its account's health channel — and a reply only threads inside one chat. A
    root in the shared room is a thread that silently stops working.
    MUTATION: drop `bot_key=bot_key` from the PROMOTED call -> red."""
    routed = []
    # Answers None (no message id), so the promote does not go on to write the thread file on
    # the box — that write is covered by its own tests and is not what this one is about.
    monkeypatch.setattr(bots, "_notify_telegram", lambda m, **k: routed.append(k.get("bot_key")))
    vps["out"] = f"  pinned abc123\n{bots._VERSION_MARK} 164 165\n{bots._PROMOTE_OK}"
    bots.promote_bot("sos_fade_demo", REQ)
    assert routed and routed[0] == "sos_fade_demo"


def test_an_uncountable_side_reads_v_question_and_is_still_PRINTED(vps, sent):
    """A bot promoted before the version stamp existed has no "from". Dropping the line
    silently would make the message look complete while answering half the question; `v?` says
    which half is missing. And it must NEVER read `v0` — that is a version somebody could be
    on, and it is the value that misreported this field for its whole life."""
    vps["out"] = f"  pinned abc123\n{bots._VERSION_MARK} ? 165\n{bots._PROMOTE_OK}"
    bots.promote_bot("sos_fade_demo", REQ)
    assert "v? → v165" in sent[0]
    assert "v0" not in sent[0]


def test_a_promote_with_no_version_line_still_reports_success(vps, sent):
    """An older `promote.py` on the VPS prints no marker at all. The alert must degrade to the
    sentence it always sent rather than inventing a version or failing to send."""
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    bots.promote_bot("sos_fade_demo", REQ)
    assert sent and "deployed" in sent[0]
    assert "v?" not in sent[0] and "v0" not in sent[0]


def test_the_version_marker_is_stripped_from_what_the_user_reads(vps):
    """It is a channel for one caller, not output. Leaving it in puts `##VERSIONS 164 165` in
    the panel under the deploy button."""
    vps["out"] = f"  pinned abc123\n{bots._VERSION_MARK} 164 165\n{bots._PROMOTE_OK}"
    r = bots.promote_bot("sos_fade_demo", REQ)
    assert bots._VERSION_MARK not in r.output
    assert r.output == "pinned abc123"


def test_a_FAILED_promote_sends_no_version_claim_at_all(vps, sent):
    """Nothing was deployed, so there is no "to" — and the alert is not sent either way. A
    version pair on a failed promote would describe a move that did not happen."""
    vps["out"] = f"  pinned abc123\n{bots._VERSION_MARK} 164 165\n{bots._PROMOTE_FAIL}"
    r = bots.promote_bot("sos_fade_demo", REQ)
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
    bots.promote_bot("sos_fade_demo", REQ)
    assert order == ["alert", "thread", "kill"]


def test_the_root_states_the_INTENT_because_the_replies_report_the_outcome(vps, sent):
    """It is sent before the restart, so it cannot claim the bot is running — the ONLINE that
    threads under it is what says that, from the process that would know."""
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    bots.promote_bot("sos_fade_demo", REQ)
    assert "Restarting it now." in sent[0]
    assert "It is running it now" not in sent[0]


def test_no_thread_is_written_when_no_restart_was_asked_for(vps, sent, monkeypatch):
    """Without a restart the bot sends neither STOPPED nor ONLINE, so there is nothing to
    thread — and a file left in the instance directory would parent whatever it sends next."""
    wrote: list = []
    monkeypatch.setattr(bots, "_set_alert_thread", lambda *a: wrote.append(a))
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    bots.promote_bot(
        "sos_fade_demo", BotPromoteRequest(pull=False, allow_dirty=False, restart=False)
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
    r = bots.promote_bot("sos_fade_demo", REQ)
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
    bots._set_alert_thread("sos_fade_demo", 4242)  # must not raise


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
    bots._set_alert_thread("sos_fade_demo", 4242)
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
    bots._set_alert_thread("sos_fade_demo", mid)
    assert calls == []


# ── it has to be able to SAY it failed (2026-08-14) ──────────────────────────────
#
# 🔴 The first real deploy carrying the threading sent its three messages UNTHREADED, and the
# investigation that followed is the reason these exist: every hop was verified working in
# isolation — the backend's own writer put the file on the VPS, the bot's own reader returned
# the id from it — and **not one line anywhere on either machine said which hop had dropped it.**
# `subprocess.run` without `check=True` does not raise on a non-zero exit, so the blanket
# try/except caught the failures that raise and waved through every failure ssh reports by EXIT
# CODE; and a falsy root id returned in silence. A helper that is allowed to fail must still be
# able to say that it did, or the next occurrence is as unreadable as the first.


class _Failed:
    returncode = 255
    stdout = b""
    stderr = b"ssh: connect to host forexvps port 22: Connection refused"


def test_a_write_that_LANDED_reports_success(monkeypatch):
    monkeypatch.setattr(bots.subprocess, "run", lambda *a, **k: _Done())
    assert bots._set_alert_thread("sos_fade_demo", 4242) is True


def test_a_NONZERO_ssh_exit_is_a_failure_and_is_not_swallowed(monkeypatch, capsys):
    """🔴 The defect this pass fixed. `check=True` is absent by design — raising here would let
    a Telegram convenience fail a promote — so the exit code is the ONLY signal, and it was the
    one thing the old code never looked at."""
    monkeypatch.setattr(bots.subprocess, "run", lambda *a, **k: _Failed())
    assert bots._set_alert_thread("sos_fade_demo", 4242) is False
    assert "255" in capsys.readouterr().out


def test_a_write_that_RAISED_reports_failure_too(monkeypatch):
    """Both shapes of failure answer the same thing. Reporting only the raising half would make
    the return value a claim the caller cannot rely on, which is worse than no return value."""

    def boom(*_a, **_k):
        raise OSError("ssh is down")

    monkeypatch.setattr(bots.subprocess, "run", boom)
    assert bots._set_alert_thread("sos_fade_demo", 4242) is False


@pytest.mark.parametrize("mid", [None, 0])
def test_a_MISSING_root_id_says_so_rather_than_returning_in_silence(monkeypatch, mid, capsys):
    """`send_telegram_id` answers None for *the send failed* and 0 for *it went through but the
    id was unreadable*, and BOTH arrive here. This branch is where a five-second Telegram hiccup
    becomes a whole deploy's worth of unthreaded messages, so it may not be the quiet one."""
    monkeypatch.setattr(bots.subprocess, "run", lambda *a, **k: _Done())
    assert bots._set_alert_thread("sos_fade_demo", mid) is False
    assert "not be threaded" in capsys.readouterr().out


# ── Nothing new to deploy: say so, and leave the bot running (2026-09-23) ─────
#
# 🔴 **The failure these pin.** FFT was deployed twice inside three minutes on 2026-09-23. The
# second run staged byte-identical code, printed `v373 -> v373`, and stopped and restarted the bot
# anyway — cancelling the limit order it had placed ninety seconds earlier and putting an identical
# one back a minute later. `promote.py` had ALREADY computed and printed that the code was
# unchanged; nothing acted on it. Aaron: *"how else was I allowed to redeploy"*.
#
# **Watched RED at HEAD:** with the marker ignored, every one of these failed on `restarted is
# True` and `killed == ["fft_1"]` — the bot stopped and started for a snapshot it was already
# running, which is the defect stated as a test.


def test_a_deploy_with_NOTHING_NEW_does_not_touch_the_running_bot(vps):
    """The whole point. The snapshot on the box is the one the process is already running, so a
    stop and a start cost the bot whatever it has resting and buy nothing."""
    vps["out"] = f"{bots._NOOP_MARK}\n  nothing new for the bot to load\n{bots._PROMOTE_OK}"
    r = bots.promote_bot("fft_1", REQ)
    assert r.ok is True
    assert r.nothing_new is True
    assert r.restarted is False
    assert vps["killed"] == [] and vps["launched"] == []


def test_NOTHING_NEW_is_a_SUCCESS_not_a_refusal(vps):
    """It exits 0 and has brought the record up to date. Reporting it as a failure would send a
    reader looking for a broken deploy and, worse, teach them to press it again."""
    vps["out"] = f"{bots._NOOP_MARK}\n{bots._PROMOTE_OK}"
    assert bots.promote_bot("fft_1", REQ).ok is True


def test_an_ordinary_deploy_still_restarts(vps):
    """The guard must be narrow. Without this the two tests above pass on a bridge that never
    restarts anything, which is a far worse bug than the one being fixed."""
    vps["out"] = f"  pinned abc123\n{bots._PROMOTE_OK}"
    r = bots.promote_bot("fft_1", REQ)
    assert r.nothing_new is False
    assert r.restarted is True and vps["killed"] == ["fft_1"]


def test_the_NOTHING_NEW_marker_is_stripped_from_what_the_user_reads(vps):
    """Same rule the other two markers follow: a machine-readable line is for the caller, and a
    reader seeing `##NOTHING-NEW` learns nothing from it."""
    vps["out"] = f"{bots._NOOP_MARK}\n  nothing new for the bot to load\n{bots._PROMOTE_OK}"
    out = bots.promote_bot("fft_1", REQ).output
    assert bots._NOOP_MARK not in out
    assert "nothing new for the bot to load" in out


def test_a_deploy_that_changed_NOTHING_does_not_claim_it_PROMOTED_anything(vps, sent):
    """🔴 The message that started this. `v373 → v373 · deployed / Restarting it now.` was true of
    nothing that happened, and a reader acting on it goes looking for a restart that never came."""
    vps["out"] = f"{bots._NOOP_MARK}\n{bots._VERSION_MARK} 373 373\n{bots._PROMOTE_OK}"
    bots.promote_bot("fft_1", REQ)
    body = "\n".join(sent)
    assert "PROMOTED" not in body
    assert "Restarting it now" not in body
    assert "NOTHING TO DEPLOY" in body
    assert "it was left alone" in body


def test_a_FAILED_promote_is_never_read_as_nothing_new(vps):
    """A refusal can print anything, including the words this branch looks for. The marker is only
    honoured on a run that reported success — the same rule the version line already follows."""
    vps["out"] = f"{bots._NOOP_MARK}\n{bots._PROMOTE_FAIL}"
    r = bots.promote_bot("fft_1", REQ)
    assert r.ok is False and r.restarted is False


def test_a_PREVIEW_says_up_front_that_a_deploy_would_do_nothing(vps):
    """The preview is the one place a person looks BEFORE deciding, so it is the one place that
    must not leave this out."""
    vps["out"] = f"{bots._NOOP_MARK}\n  dry run\n{bots._PROMOTE_OK}"
    assert bots.preview_bot_promote("fft_1", REQ).nothing_new is True


# ── Nothing new ON DISK is not nothing new IN THE PROCESS (2026-09-24) ─────────
#
# 🔴 **The failure these pin.** `fft_1`'s deploy on 2026-09-24 pinned the new code and then timed
# out before its restart. The retry found nothing new to build and, by the rule above, left the
# bot alone — on the OLD code, with no deploy able to move it. The live process's own report
# (`bot_state.json`) now decides whether "nothing new" really means nothing to load.
#
# ⚠ The box is faked at the SSH boundary only, routing each command to the file it reads, so the
# real readers (`_read_run_state`, `_deployed_json`, `_deployed_hash`) parse what they are handed.


def _box(vps, monkeypatch, *, running, pinned: str):
    promote_out = f"{bots._NOOP_MARK}\n{bots._PROMOTE_OK}"
    state_path = bots._bot_state_path("fft_1")
    assert state_path, "fft_1 must resolve a state file or these tests prove nothing"

    def ssh(cmd):
        vps["cmds"].append(cmd)
        if "deployed.json" in cmd:
            return json.dumps({"strategy_source_hash": pinned})
        if state_path in cmd:
            return "" if running is None else json.dumps({"fft_1": {"source_hash": running}})
        return promote_out

    monkeypatch.setattr(bots, "_ssh", ssh)
    monkeypatch.setattr(bots, "_set_alert_thread", lambda *_a, **_k: True)


def test_NOTHING_NEW_still_restarts_a_process_running_OLDER_code(vps, sent, monkeypatch):
    """Mutation: drop the `stale` check (always leave a nothing-new bot alone) → never killed, RED."""
    _box(vps, monkeypatch, running="b9097e7f28bf", pinned="b9f340810c22b2b37751e0be7b0f43c3")
    r = bots.promote_bot("fft_1", REQ)
    assert r.ok is True and r.restarted is True and r.nothing_new is False
    assert vps["killed"] == ["fft_1"] and vps["launched"] == ["fft_1"]
    body = "\n".join(sent)
    assert "RESTARTING ONTO DEPLOYED CODE" in body and "NOTHING TO DEPLOY" not in body


def test_NOTHING_NEW_leaves_a_CURRENT_process_alone(vps, sent, monkeypatch):
    """Mutation: invert the prefix test in `_running_older_code` → the current bot is killed, RED."""
    _box(vps, monkeypatch, running="b9f340810c22", pinned="b9f340810c22b2b37751e0be7b0f43c3")
    r = bots.promote_bot("fft_1", REQ)
    assert r.restarted is False and r.nothing_new is True and vps["killed"] == []
    assert "already running this code" in "\n".join(sent)


def test_an_UNREADABLE_process_is_left_alone_and_the_message_says_it_could_not_tell(
    vps, sent, monkeypatch
):
    """`None` is not *current* (rule 1): the bot is not restarted on a guess, and the message stops
    claiming it is already running this code. Mutation: read `None` as current → wording RED."""
    _box(vps, monkeypatch, running=None, pinned="b9f340810c22b2b37751e0be7b0f43c3")
    r = bots.promote_bot("fft_1", REQ)
    assert r.restarted is False and vps["killed"] == []
    body = "\n".join(sent)
    assert "could not be read" in body and "already running this code" not in body
