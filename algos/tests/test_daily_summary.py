"""The daily summary — once a day, what the health rooms did NOT show (stage 4, 2026-09-26).

The whole hold policy rests on one promise: nothing held becomes invisible. This message keeps it,
built ONLY from the send log. The tests pin the three answers rule 1 demands — "nothing held" only
off a log that was READ, "could not be read" when it was not, "no log" when none was written — and
drive the real notifier and policy end to end for the counts.

⚠ Rule 12, proven by MUTATION (run 2026-09-26; each went RED):
  - the `problem` branch removed (an unreadable log falls through)     -> the unreadable test red
  - the `found` branch removed                                          -> the no-log test red
  - held rows counted from `sent` instead                               -> the end-to-end test red
  - `due` ignoring `sent_for`                                           -> the once-a-day test red
  - a Command Center restart (`edit_of`) counted as an auto-restart     -> the named-counts test red
    (watched RED 2026-09-27 before the fix: it counted 3, not 2)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
for _p in (_ALGOS / "shared", _ALGOS / "notifications"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import alert_policy  # noqa: E402
import credentials as creds_mod  # noqa: E402
import daily_summary as ds  # noqa: E402
import notify  # noqa: E402
import notify_log  # noqa: E402
from alert_format import CRITICAL, OK, alert  # noqa: E402

START, END = ds.window_for(datetime(2026, 9, 26).date())


def _r(label, outcome="held", subject="SOS Fade · LIVE", **kw):
    return {
        "ts": "2026-09-26T05:00:00+00:00",
        "kind": "health",
        "label": label,
        "outcome": outcome,
        "subject": subject,
        **kw,
    }


def test_the_window_is_the_24_hours_to_8_AM_Chicago():
    assert START == datetime(2026, 9, 25, 13, 0, tzinfo=timezone.utc)
    assert END == datetime(2026, 9, 26, 13, 0, tzinfo=timezone.utc)


def test_held_messages_are_counted_by_label_and_by_bot_biggest_first():
    rows = (
        [_r("WILL NOT START")] * 16
        + [_r("OFFLINE")] * 3
        + [_r("OFFLINE", subject="Extreme Leg · LIVE")] * 2
    )
    text = ds.summarise(rows, None, 1, START, END)
    assert text.splitlines()[0] == "ℹ️ DAILY SUMMARY · Health room"
    assert (
        "Held 21: WILL NOT START 16 (SOS Fade · LIVE 16); "
        "OFFLINE 5 (SOS Fade · LIVE 3, Extreme Leg · LIVE 2)." in text
    )


def test_NOTHING_HELD_is_said_when_it_is_the_truth():
    text = ds.summarise([_r("ONLINE", outcome="sent")], None, 1, START, END)
    assert "Nothing held." in text
    assert "Delivered late: 0 · Given up after 24 h: 0." in text


def test_an_UNREADABLE_log_says_so_and_never_reports_zero():
    """MUTATION: remove the `problem` branch -> red."""
    text = ds.summarise([], "could not read 2026-09-26.jsonl: denied", 1, START, END)
    assert "could not be read" in text and "denied" in text
    assert "Nothing held" not in text and "Held" not in text and "Delivered late" not in text


def test_NO_log_at_all_is_not_reported_as_a_quiet_day():
    """MUTATION: remove the `found` branch -> red."""
    text = ds.summarise([], None, 0, START, END)
    assert "no send log" in text and "Nothing held" not in text


def test_the_longest_trading_off_the_restarts_and_the_late_and_lost_are_named():
    rows = [
        _r("TRADING OFF", duration_s=420, account=34957946),
        _r(
            "TRADING BACK ON",
            outcome="sent",
            duration_s=1500,
            recovers="TRADING OFF",
            account=700152905,
        ),
        _r("RESTARTED"),
        _r("RESTARTED", outcome="sent"),
        _r("RESTARTED", subject="Telegram bot"),
        # A restart somebody PRESSED: the bot edits the Command Center's own message. Not an
        # auto-restart - on its first morning the summary counted Aaron's deploys as two.
        _r("RESTARTED", outcome="sent", edit_of=15),
        _r("HALTED", outcome="sent", delayed=True),
        {**_r("ENTRY", outcome="dropped", gave_up=True), "kind": "trade"},
    ]
    text = ds.summarise(rows, None, 1, START, END)
    assert "Longest trading-off: 25 min (account 700152905)." in text
    assert "Auto-restarts: 2 (SOS Fade · LIVE 2)." in text
    assert "The Telegram bot was restarted 1 time(s)." in text
    assert (
        "Delivered late: 1 · Given up after 24 h: 1 (of them 1 trade or setup message(s))." in text
    )


def test_it_is_due_ONCE_a_day_at_or_after_8_AM_Chicago():
    """MUTATION: make `due` ignore `sent_for` -> red."""
    before = datetime(2026, 9, 26, 12, 59, tzinfo=timezone.utc)  # 7:59 AM CDT
    at = datetime(2026, 9, 26, 13, 0, tzinfo=timezone.utc)
    assert not ds.due({}, before)
    assert ds.due({}, at)
    assert not ds.due({"sent_for": "2026-09-26"}, at)


# ── end to end, through the real notifier and policy ────────────────────────────────────────


@pytest.fixture
def box(monkeypatch, tmp_path):
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)
    monkeypatch.setenv("LWG_TELEGRAM_TOKEN", "T")
    monkeypatch.setenv("LWG_TELEGRAM_CHAT_ID", "-100trades")
    monkeypatch.setenv("LWG_TELEGRAM_HEALTH_CHAT", "-100shared")
    monkeypatch.setenv("LWG_NOTIFY_DIR", str(tmp_path / "notify"))
    rooms = {34957946: {"telegram_health_chat": "-100live"}}
    monkeypatch.setattr(notify, "_account_row", lambda a: rooms.get(a, {}))
    monkeypatch.setattr(alert_policy, "action_in_progress", lambda bot: None)
    import bot_state

    monkeypatch.setattr(
        bot_state, "BOT_INSTANCES", {"sos_fade_demo": tmp_path, "sos_fade_1": tmp_path}
    )
    monkeypatch.setattr(
        bot_state, "read_account", lambda k: 34957946 if k == "sos_fade_demo" else 700152905
    )
    posts = []

    class _Resp:
        status_code, text = 200, "ok"

        def json(self):
            return {"result": {"message_id": len(posts)}}

    class _Tg:
        def post(self, url, json=None, timeout=None, **_k):
            posts.append(json)
            return _Resp()

    monkeypatch.setattr(notify, "_requests", _Tg())
    yield posts
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)


def test_ONE_summary_per_health_room_counting_what_the_policy_held(box):
    """MUTATION: count `sent` rows as held -> red."""
    will_not = alert(CRITICAL, "WILL NOT START", "SOS Fade · LIVE", "Startup failed: x")
    for _ in range(3):
        notify.send_telegram_id(will_not, notify.HEALTH, account=34957946, bot="sos_fade_demo")
    chat = alert(OK, "COMMANDS ONLINE", "Telegram bot", "listening")
    notify.send_telegram_id(chat, notify.HEALTH)
    box.clear()

    # The log is written with the real clock; build the summary for the window that contains now.
    now = datetime.now(timezone.utc)
    local = now.astimezone(ds.TZ)
    day = local.date() if local.time() < ds.SEND_AT else (local + ds.timedelta(days=1)).date()
    state = ds.maybe_send({}, now=datetime.combine(day, ds.SEND_AT, tzinfo=ds.TZ))
    assert state["sent_for"] == day.isoformat()

    by_room = {p["chat_id"]: p["text"] for p in box}
    assert set(by_room) == {"-100live", "-100shared"}, "one per health room, the live room included"
    assert "Held 2: WILL NOT START 2 (SOS Fade · LIVE 2)." in by_room["-100live"]
    assert "Held 1: COMMANDS ONLINE 1 (Telegram bot 1)." in by_room["-100shared"]

    # It is itself in the log, and never counted by tomorrow's.
    rows, _p, _f = notify_log.read_window(
        ds.window_for(day)[0], datetime.now(timezone.utc).replace(year=2100)
    )
    assert any(r.get("label") == ds.LABEL for r in rows)
    assert ds.LABEL not in ds.summarise(rows, None, 1, START, END).split("\n", 1)[1]


def test_the_watchdog_sends_it():
    src = (_ALGOS / "notifications" / "monitor.py").read_text(encoding="utf-8")
    assert "maybe_send_daily_summary(" in src[src.index("def main():") :]


def test_a_summary_that_fails_never_stops_the_watchdog(monkeypatch):
    monkeypatch.setattr(ds, "build", lambda now: 1 / 0)
    assert ds.maybe_send({}, now=datetime(2026, 9, 26, 14, 0, tzinfo=timezone.utc)) == {}


def test_the_log_line_format_is_the_one_the_summary_reads(tmp_path, monkeypatch):
    """The summary reads `outcome`, `label`, `subject`, `duration_s`, `delayed`, `gave_up`,
    `recovers` and `kind` off the log. Written by the real writer, read back by the real reader."""
    monkeypatch.setenv("LWG_NOTIFY_DIR", str(tmp_path))
    notify_log.record("health", "held", text="⚠️ OFFLINE · Bot\nx", duration_s=5, recovers="X")
    (row,) = [json.loads(x) for x in next(tmp_path.glob("*.jsonl")).read_text().splitlines()]
    for field in ("outcome", "label", "subject", "kind", "duration_s", "recovers"):
        assert field in row
