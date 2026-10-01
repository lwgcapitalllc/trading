"""A Command Center deploy, start or restart is ONE message, and its failure is still said (2026-09-26).

Every promote used to put PROMOTED + STOPPED + ONLINE in the health room, per bot; a start was
STARTING + ONLINE; a restart RESTARTING + ONLINE. Now the Command Center's one message is EDITED by
the bot into the outcome once it is online (`runner._finish_action`), the bot's own STOPPED is held
while the action is in flight (`alert_policy`, tested in `test_alert_policy.py`), and the box's
watchdog says NOT BACK ONLINE if the bot has not consumed the action's record three minutes on.

⚠ Rule 12, proven by MUTATION (run 2026-09-26; each went RED):
  - `_finish_action` returning True without editing                -> the fallback test red
  - the `from_version` line dropped from the DEPLOYED text           -> the deploy test red
  - `ACTION_GRACE_SECONDS` compared with `>` the wrong way round     -> both watchdog tests red
  - the `action_alerted` memory removed                              -> the once-only test red
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
for _p in (_ALGOS / "live", _ALGOS / "shared", _ALGOS / "notifications", _ALGOS.parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import notify  # noqa: E402
from runner import LiveRunner  # noqa: E402


class _Runner(LiveRunner):
    _label = "SOS Fade · LIVE"  # a property on the real class, off the account registry


def _runner(tmp_path):
    r = _Runner.__new__(_Runner)
    r.cfg = SimpleNamespace(
        bot_key="sos_fade_demo", instance_dir=tmp_path, account=34957946, version_label="v399"
    )
    r.log = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)
    return r


def _record(r, **fields):
    rec = {"message_id": 555, "expires_at": time.time() + 900, "sent_at": time.time()}
    rec.update(fields)
    r.alert_thread_path().write_text(json.dumps(rec), encoding="utf-8")


@pytest.fixture
def edits(monkeypatch):
    seen = []

    def _edit(chat, mid, text, **kw):
        seen.append((chat, mid, text, kw))
        return True

    monkeypatch.setattr(notify, "edit_telegram", _edit)
    return seen


def test_a_DEPLOY_is_edited_into_one_DEPLOYED_message_with_both_versions(tmp_path, edits):
    r = _runner(tmp_path)
    _record(r, action="promote", chat="-100health", from_version="v397")
    assert r._finish_action("Trading live · XAUUSD.p M15 · $10,752.18", "v399 (abcd1234)") is True
    ((chat, mid, text, kw),) = edits
    assert (chat, mid) == ("-100health", 555)
    assert text.splitlines()[0] == "✅ DEPLOYED · SOS Fade · LIVE"
    assert "v397 → v399, back online" in text
    assert "$10,752.18" in text
    assert kw.get("bot") == "sos_fade_demo" and "token_key" not in kw, (
        "the Command Center sent it with the DEFAULT token, and only its sender may edit it"
    )


@pytest.mark.parametrize(
    "action, head, line",
    [
        ("start", "✅ ONLINE · SOS Fade · LIVE", "Started from the Command Center."),
        ("restart", "✅ RESTARTED · SOS Fade · LIVE", "Restarted from the Command Center"),
    ],
)
def test_a_START_and_a_RESTART_become_their_outcome(tmp_path, edits, action, head, line):
    r = _runner(tmp_path)
    _record(r, action=action, chat="-100health")
    assert r._finish_action("facts", "version") is True
    text = edits[0][2]
    assert text.splitlines()[0] == head and line in text


@pytest.mark.parametrize(
    "fields",
    [
        {},  # an older Command Center: no action, no room
        {"action": "promote"},  # no room
        {"action": "stop", "chat": "-100health"},  # not an action this edits
    ],
)
def test_anything_short_of_a_landed_edit_answers_False_so_ONLINE_is_sent(tmp_path, edits, fields):
    """Losing the ONLINE is the one outcome this may not have."""
    r = _runner(tmp_path)
    _record(r, **fields)
    assert r._finish_action("facts", "version") is False
    assert edits == []


def test_a_REFUSED_edit_answers_False(tmp_path, monkeypatch):
    monkeypatch.setattr(notify, "edit_telegram", lambda *a, **k: False)
    r = _runner(tmp_path)
    _record(r, action="promote", chat="-100health")
    assert r._finish_action("facts", "version") is False


def test_the_runner_falls_back_to_ONLINE_when_the_edit_does_not_land():
    """Read off the source, because the start path needs a live terminal: the plain ONLINE must sit
    under a `not self._finish_action(...)`, and the thread must still be consumed after it."""
    src = (_ALGOS / "live" / "runner.py").read_text(encoding="utf-8")
    i = src.index("if not self._finish_action(facts, version_line):")
    assert '"ONLINE"' in src[i : i + 200]
    assert src.index("self.clear_alert_thread()", i) > i


# ── the watchdog breaks the silence a failed action would leave ────────────────────────────


@pytest.fixture
def watch(monkeypatch, tmp_path):
    import monitor

    sent = []
    monkeypatch.setattr(monitor, "send_alert", lambda m, account=None, **kw: sent.append(m))
    monkeypatch.setattr(monitor._bot_state, "BOT_INSTANCES", {"b": tmp_path})
    return monitor, sent, tmp_path


def _action(tmp_path, *, age, action="promote", mid=77, sent_at=True):
    now = time.time()
    rec = {"message_id": mid, "expires_at": now - age + 900, "action": action}
    if sent_at:
        rec["sent_at"] = now - age
    (tmp_path / "alert_thread.json").write_text(json.dumps(rec), encoding="utf-8")


def test_an_action_the_bot_never_came_back_from_is_said_at_3_minutes(watch):
    monitor, sent, tmp = watch
    _action(tmp, age=60)
    monitor.check_action("b", {}, 1, "SOS Fade · LIVE")
    assert sent == []
    _action(tmp, age=200)
    st = monitor.check_action("b", {}, 1, "SOS Fade · LIVE")
    (msg,) = sent
    assert msg.startswith("⛔ NOT BACK ONLINE · SOS Fade · LIVE")
    assert "deployed and restarted it" in msg
    assert st["action_alerted"] == 77


def test_it_is_said_ONCE_per_action(watch):
    monitor, sent, tmp = watch
    _action(tmp, age=200)
    st = monitor.check_action("b", {}, 1, "x")
    st = monitor.check_action("b", st, 1, "x")
    assert len(sent) == 1
    _action(tmp, age=200, mid=78)  # a NEW action
    monitor.check_action("b", st, 1, "x")
    assert len(sent) == 2


def test_an_OLDER_command_centers_record_is_timed_off_its_expiry(watch):
    monitor, sent, tmp = watch
    _action(tmp, age=200, sent_at=False)
    monitor.check_action("b", {}, 1, "x")
    assert len(sent) == 1


def test_no_record_or_an_expired_one_says_nothing(watch):
    monitor, sent, tmp = watch
    monitor.check_action("b", {}, 1, "x")
    _action(tmp, age=1000)
    monitor.check_action("b", {}, 1, "x")
    assert sent == []


def test_the_watchdog_runs_the_check_for_every_assigned_bot():
    src = (_ALGOS / "notifications" / "monitor.py").read_text(encoding="utf-8")
    main = src[src.index("def main():") :]
    assert "check_action(" in main and main.index("check_bot(") < main.index("check_action(")
