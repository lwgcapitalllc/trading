"""Stage 3 of the health-room noise work (2026-09-26): the hourly reviewer stops repeating what the
room already had, and a LIVE bot that is halted or down is reminded about every hour.

* Every HALTED used to arrive THREE times — the bridge's own, then the reviewer's two findings an
  hour later. The two findings are now one, and the reviewer skips a finding whose real-time alert
  is in the send log. ⚠ **A real-time alert that is NOT in the log is exactly what the reviewer is
  for**, so a lost one (or one from a bot on code older than the log) is still sent.
* The counterweight to every hold: a halted or down LIVE bot gets a REMINDER an hour until it
  clears. Demo accounts get none.

⚠ Rule 12, proven by MUTATION (run 2026-09-26; each went RED):
  - `announced_in_real_time` returning False always                      -> the main-path test red
  - `_COVERING` widened to include "dropped"                             -> the lost-alert test red
  - the `account_kind(...) != "live"` gate removed                       -> the demo test red
  - `REMINDER_EVERY_SECONDS` check removed (a reminder every pass)       -> the hourly test red
  - the old `halted_now` finding put back beside the merged one        -> test_log_review's
    `test_a_FRESH_halted_heartbeat_on_a_running_bot_is_still_urgent` red
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
for _p in (_ALGOS / "shared", _ALGOS / "notifications"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import log_review as lr  # noqa: E402
import notify_log  # noqa: E402

HALT_AT = "2026-09-20T03:00:00+00:00"


def _row(label, outcome="sent", at=HALT_AT, bot="b", **kw):
    return {"ts": at, "label": label, "outcome": outcome, "bot": bot, **kw}


def _halt_finding():
    return lr.Finding(f"halted:{HALT_AT}", lr.ALERT, "Bridge is HALTED right now", "x")


# ── is this finding's real-time twin in the log? ────────────────────────────────────────────


def test_a_HALTED_already_sent_covers_the_halt_finding():
    assert lr.announced_in_real_time("b", _halt_finding(), [_row("HALTED")])


@pytest.mark.parametrize(
    "rows, why",
    [
        ([_row("HALTED", outcome="dropped")], "a DROPPED alert never reached anybody"),
        ([], "no line at all - lost, or a bot on code older than the log"),
        ([_row("HALTED", bot="other")], "another bot's halt"),
        ([_row("HALTED", at="2026-09-20T05:00:00+00:00")], "two hours later is another halt"),
        ([_row("WILL NOT START")], "a different alert"),
    ],
)
def test_a_finding_whose_alert_was_LOST_is_still_sent(rows, why):
    """MUTATION: add "dropped" to `_COVERING` -> red on the first case."""
    assert not lr.announced_in_real_time("b", _halt_finding(), rows), why


def test_an_UNREADABLE_log_covers_nothing():
    """Rule 1: could-not-read is not "nothing was sent" and not "it was all sent"."""
    assert not lr.announced_in_real_time("b", _halt_finding(), None)


def test_a_HELD_alert_covers_its_finding_because_the_summary_counts_it():
    """The policy held a quick-recovered OFFLINE on purpose; re-announcing it as a REVIEW an hour
    later would undo the hold. The daily summary is where it is counted."""
    unclean = lr.Finding(f"unclean:{HALT_AT}", lr.WARN, "Previous run ended", "x")
    at = (datetime.fromisoformat(HALT_AT) - timedelta(minutes=2)).isoformat()
    assert lr.announced_in_real_time("b", unclean, [_row("OFFLINE", outcome="held", at=at)])


def test_a_finding_with_no_real_time_twin_is_always_sent():
    loop = lr.Finding(f"restart_loop:{HALT_AT}", lr.ALERT, "Restarted 4 times", "x")
    assert not lr.announced_in_real_time("b", loop, [_row("OFFLINE"), _row("RESTARTED")])


def test_main_does_not_re_announce_a_halt_the_room_already_had(tmp_path, monkeypatch, capsys):
    """The whole path: a live halt, its HALTED in the send log -> the chip is written, the finding
    is remembered as said, and nothing is sent."""
    ts = "2026-09-20T03:00:00+00:00"
    now = datetime(2026, 9, 20, 3, 30, tzinfo=timezone.utc)
    inst = tmp_path / "inst"
    (inst / "ledger").mkdir(parents=True)
    rows = [
        {
            "ts": (now - timedelta(minutes=m)).isoformat(),
            "bot": "b",
            "kind": "pulse",
            "link": True,
            "bridge_state": "halted",
        }
        for m in (60, 45, 30, 15, 5)
    ] + [{"ts": ts, "bot": "b", "kind": "event", "event": "halted", "reason": "they disagree"}]
    (inst / "ledger" / "health-2026-09-20.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )
    notify_log.record(
        "health",
        "sent",
        text="⛔ HALTED · Bot\nthey disagree",
        bot="b",
        now=datetime.fromisoformat(ts).timestamp() + 1,
    )

    sent = []
    monkeypatch.setattr(
        lr, "send", lambda text, dry_run=False, account=None, bot=None: sent.append(text) or True
    )
    review = lr.review_bot
    monkeypatch.setattr(
        lr,
        "review_bot",
        lambda k, i, bs, now=None, process_running=None: review(
            k,
            i,
            bs,
            now=datetime(2026, 9, 20, 3, 30, tzinfo=timezone.utc),
            process_running=process_running,
        ),
    )
    monkeypatch.setattr(lr, "running_keys", lambda keys: {"b"})
    monkeypatch.setattr(lr._bot_state, "BOT_INSTANCES", {"b": inst})
    monkeypatch.setattr(lr._bot_state, "bot_label", lambda k: "Bot")
    monkeypatch.setattr(lr._bot_state, "read_bot", lambda k: {"status": "halted"})
    monkeypatch.setattr(lr._bot_state, "read_account", lambda k: None)
    monkeypatch.setattr(lr, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(
        lr, "datetime", type("D", (datetime,), {"now": staticmethod(lambda tz=None: now)})
    )

    assert lr.main([]) == 0
    assert sent == [], "the room already had this halt from the bridge itself"
    chip = json.loads((inst / "review.json").read_text(encoding="utf-8"))
    assert [f["key"] for f in chip["findings"]] == [f"halted:{ts}"], "ONE finding, on the chip"
    assert f"halted:{ts}" in json.loads((tmp_path / "state.json").read_text())["b"]


# ── the hourly reminder for a LIVE bot ──────────────────────────────────────────────────────


@pytest.fixture
def watch(monkeypatch):
    import monitor

    sent = []
    monkeypatch.setattr(monitor, "send_alert", lambda m, account=None, **kw: sent.append(m))
    kinds = {34957946: "live", 700152905: "demo"}
    monkeypatch.setattr(monitor._bot_state, "account_kind", lambda a: kinds.get(a))
    live = {"bridge_state": "halted", "halt_reason": "the bot's record doesn't match the broker."}
    monkeypatch.setattr(monitor._bot_state, "read_bot", lambda k: live)
    return monitor, sent


def _hours(monitor, state, n, account=34957946, start=1_000_000.0):
    for i in range(n * 60 + 1):  # one watchdog pass a minute
        state = monitor.check_reminder("b", state, account, "SOS Fade · LIVE", now=start + i * 60)
    return state


def test_a_LIVE_halted_bot_is_reminded_every_hour(watch):
    """MUTATION: remove the `REMINDER_EVERY_SECONDS` check -> red (a reminder every minute)."""
    monitor, sent = watch
    _hours(monitor, {"running": True}, 3)
    assert len(sent) == 3
    assert sent[0].startswith("⛔ REMINDER — HALTED · SOS Fade · LIVE")
    assert "Halted for 1 hour: the bot's record doesn't match the broker. It is" in sent[0]
    assert "Halted for 3 hours" in sent[-1]


def test_a_LIVE_bot_that_is_DOWN_and_nobody_stopped_is_reminded(watch):
    monitor, sent = watch
    _hours(monitor, {"running": False}, 1)
    assert len(sent) == 1 and sent[0].startswith("⛔ REMINDER — DOWN")


def test_a_bot_STOPPED_ON_PURPOSE_is_not_down(watch):
    monitor, sent = watch
    _hours(monitor, {"running": False, "stop_suppressed": True}, 2)
    assert sent == []


def test_a_DEMO_bot_gets_no_reminders(watch):
    """MUTATION: remove the live-account gate -> red."""
    monitor, sent = watch
    _hours(monitor, {"running": True}, 3, account=700152905)
    assert sent == []


def test_the_reminder_stops_when_the_bot_recovers_and_starts_over_next_time(watch, monkeypatch):
    monitor, sent = watch
    state = _hours(monitor, {"running": True}, 1)
    assert len(sent) == 1
    monkeypatch.setattr(monitor._bot_state, "read_bot", lambda k: {"bridge_state": "live"})
    state = monitor.check_reminder("b", state, 34957946, "x", now=2_000_000.0)
    assert "reminder" not in state


def test_the_watchdog_runs_the_reminder_for_every_assigned_bot():
    src = (_ALGOS / "notifications" / "monitor.py").read_text(encoding="utf-8")
    main = src[src.index("def main():") :]
    assert "check_reminder(" in main
