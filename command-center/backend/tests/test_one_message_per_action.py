"""A deploy, start, restart or stop from this app is ONE message in the health room (2026-09-26).

The hand count of the health room (4–25 Sep 2026) found the lifecycle of Command Center actions was
~520 of ~800 messages. The message this app sends is now the ROOT of the action: it is sent BEFORE
the bot is touched, and its id, room, action and starting version are written for the bot, which
edits it into the outcome once it is online (`algos/live/runner.py::_finish_action`). A stop is said
once — by the bot when it shut down cleanly, by this app only when it had to terminate it.

⚠ Rule 12, proven by MUTATION (run 2026-09-26; each went RED):
  - the start's root moved back AFTER `_launch_bot`                   -> the start ordering test red
  - `action="start"` changed to "promote"                              -> the start test red
  - the stop's `"shut down cleanly"` branch removed                    -> the clean-stop test red
"""

import json

import pytest
from routers import bots
from services import notify


@pytest.fixture
def box(monkeypatch, tmp_path):
    state = {"order": [], "threads": [], "sent": [], "kill_out": ""}

    def _notify(text, **k):
        state["order"].append("message")
        state["sent"].append(text)
        return 4242

    def _thread(bot_key, mid, **k):
        state["order"].append("thread")
        state["threads"].append({"bot": bot_key, "mid": mid, **k})
        return True

    monkeypatch.setattr(bots, "_notify_telegram", _notify)
    monkeypatch.setattr(bots, "_set_alert_thread", _thread)
    monkeypatch.setattr(bots, "_health_room", lambda k: "-100health")
    monkeypatch.setattr(bots, "_launch_bot", lambda k: state["order"].append("launch") or "")
    monkeypatch.setattr(
        bots, "_kill_bot", lambda k: state["order"].append("kill") or state["kill_out"]
    )
    monkeypatch.setattr(bots, "_suppress_stop_alert", lambda k: None)
    monkeypatch.setattr(bots._time, "sleep", lambda *_a: None)
    monkeypatch.setenv("LWG_NOTIFY_DIR", str(tmp_path / "log"))
    return state


def test_a_START_says_one_message_FIRST_and_hands_it_to_the_bot(box):
    bots._start_bot("sos_fade_demo")
    assert box["order"] == ["message", "thread", "launch"]
    (t,) = box["threads"]
    assert (t["mid"], t["action"], t["chat"]) == (4242, "start", "-100health")
    assert "This message will say when it is online." in box["sent"][0]


def test_a_RESTART_says_one_message_BEFORE_the_bot_is_stopped(box):
    """The bot's own STOPPED is held while this record is live — so the record has to exist
    before the stop file does."""
    bots._restart_bot("sos_fade_demo")
    assert box["order"][:3] == ["message", "thread", "kill"]
    assert box["threads"][0]["action"] == "restart"


def test_a_CLEAN_stop_is_said_by_the_bot_alone_and_this_one_is_logged_HELD(box, tmp_path):
    box["kill_out"] = "sos_fade_demo shut down cleanly after 4s"
    bots._stop_bot("sos_fade_demo")
    assert box["sent"] == []
    (path,) = sorted((tmp_path / "log").glob("*.jsonl"))
    (row,) = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert (row["outcome"], row["label"]) == ("held", "STOPPED")


def test_a_stop_that_had_to_TERMINATE_the_bot_is_still_said_here(box):
    """The bot said nothing — it was killed — so this is the only STOPPED there will be."""
    box["kill_out"] = "sos_fade_demo did not stop within 60s — terminating"
    bots._stop_bot("sos_fade_demo")
    assert len(box["sent"]) == 1 and "STOPPED" in box["sent"][0]


def test_the_record_carries_what_the_bot_needs_to_edit_the_message(monkeypatch):
    """Action, room, version it came from and when it was sent — the bot edits with the first
    three and the box's watchdog times NOT BACK ONLINE off the fourth."""
    seen = {}

    class _Out:
        returncode = 0
        stderr = b""

    def _run(args, input=None, **k):
        seen["payload"] = json.loads(input.decode())
        return _Out()

    monkeypatch.setattr(bots.vps_ssh, "run", _run)
    assert bots._set_alert_thread(
        "sos_fade_demo", 4242, action="promote", chat="-100h", from_version="v397"
    )
    p = seen["payload"]
    assert (p["message_id"], p["action"], p["chat"], p["from_version"]) == (
        4242,
        "promote",
        "-100h",
        "v397",
    )
    assert p["expires_at"] - p["sent_at"] == pytest.approx(bots._ALERT_THREAD_TTL_SECONDS)


def test_the_health_room_falls_back_to_the_shared_one(monkeypatch):
    monkeypatch.setattr(bots, "_account_health_chat", lambda **k: "")
    monkeypatch.setattr(notify, "chat_for", lambda kind: "-100shared")
    assert bots._health_room("sos_fade_demo") == "-100shared"
