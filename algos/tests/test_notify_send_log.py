"""The Telegram SEND LOG and the OUTBOX — stage 1 of the health-room noise work (2026-09-26).

What these pin, and why each matters:

* **Every outcome is written down** — sent, queued, dropped — with the label and subject parsed
  off the message. The health policy holds messages from stage 2 on, and a hold is only safe if
  it is on a record somebody can read; this log is that record.
* **A TRANSIENT failure is not a lost message.** On 19 Sep 2026 every TRADING OFF from five bots
  on two accounts was lost while the TRADING BACK ON a minute later arrived (ledger: 20
  `trading_disabled`, 20 `trading_restored`, zero OFF in the room). A network error, a timeout,
  HTTP 429 or a 5xx now goes to the outbox and is re-sent with a *(delayed, first tried …)* line.
* **A PERMANENT refusal is logged and never retried**, and the outbox gives up after 24 hours and
  COUNTS it rather than retrying for ever.
* **Nothing here may raise into a trading loop** — an unwritable log costs a log line, never the
  message.

⚠ Rule 12. These shipped with the feature, so there was no red build to watch; each one was proven
by MUTATION instead, run by hand on 2026-09-26 and recorded on the test that caught it:
  - `record(...)` in the SENT branch of `send_with_outcome` deleted            -> sent-is-logged red
  - `is_transient` returning False for everything                              -> the 429 and 502 cases red
  - the `delayed_marker` line removed from `notify_log.flush`                  -> the redelivery test red
  - `GIVE_UP_SECONDS` check removed from `notify_log.flush`                    -> the give-up test red
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ALGOS / "shared"))
sys.path.insert(0, str(_ALGOS / "notifications"))

import credentials as creds_mod  # noqa: E402
import notify  # noqa: E402
import notify_log  # noqa: E402
from alert_format import CRITICAL, alert  # noqa: E402


class _Resp:
    def __init__(self, status=200, mid=77, text=""):
        self.status_code = status
        self._mid = mid
        self.text = text or ("ok" if status == 200 else f"error {status}")

    def json(self):
        return {"ok": True, "result": {"message_id": self._mid}}


class _FakeRequests:
    """Answers each post with the next scripted response; an Exception in the script is RAISED,
    which is what `requests` does on a dead network or a timeout."""

    def __init__(self, *script):
        self.script = list(script)
        self.posts = []

    def post(self, url, json=None, timeout=None, **_kw):
        self.posts.append(json)
        nxt = self.script.pop(0) if self.script else _Resp()
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


@pytest.fixture(autouse=True)
def _configured(monkeypatch, tmp_path):
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)
    monkeypatch.setenv("LWG_TELEGRAM_TOKEN", "T")
    monkeypatch.setenv("LWG_TELEGRAM_CHAT_ID", "-100trades")
    monkeypatch.setenv("LWG_TELEGRAM_HEALTH_CHAT", "-100health")
    monkeypatch.setenv("LWG_NOTIFY_DIR", str(tmp_path / "notify"))
    # No account registry: every account resolves to the shared rooms.
    monkeypatch.setattr(notify, "_account_row", lambda account: {})
    yield
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)


def _rows():
    rows = []
    for path in sorted(notify_log.notify_dir().glob("*.jsonl")):
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return rows


HALT = alert(CRITICAL, "TRADING OFF", "SOS Fade · LIVE", "Margin call.", "Every order is refused.")


def test_a_sent_message_is_logged_with_its_label_subject_room_and_id(monkeypatch):
    """MUTATION: delete the `record(...)` in the SENT branch of `send_with_outcome` -> red."""
    monkeypatch.setattr(notify, "_requests", _FakeRequests(_Resp(200, mid=4242)))
    assert (
        notify.send_telegram_id(HALT, notify.HEALTH, account=34957946, bot="sos_fade_demo") == 4242
    )
    (row,) = _rows()
    assert row["outcome"] == "sent"
    assert row["label"] == "TRADING OFF"
    assert row["subject"] == "SOS Fade · LIVE", "the subject keeps its own ' · ' separator"
    assert row["room"] == "-100health"
    assert row["message_id"] == 4242
    assert row["account"] == 34957946 and row["bot"] == "sos_fade_demo"


@pytest.mark.parametrize(
    "failure",
    [ConnectionError("network is unreachable"), TimeoutError("timed out"), _Resp(429), _Resp(502)],
    ids=["network", "timeout", "429", "502"],
)
def test_a_TRANSIENT_failure_is_queued_not_lost(monkeypatch, failure):
    """MUTATION: make `notify_log.is_transient` answer False -> red (the message is dropped)."""
    monkeypatch.setattr(notify, "_requests", _FakeRequests(failure))
    mid, outcome = notify.send_with_outcome(HALT, notify.HEALTH, bot="sos_fade_demo")
    assert mid is None, "undelivered must not look delivered — nothing may thread under it"
    assert outcome == "queued"
    (entry,) = notify_log.entries()
    assert entry["purpose"] == "retry" and entry["chat"] == "-100health"
    assert "T" not in json.dumps({k: v for k, v in entry.items() if k != "text"}).split('"'), (
        "the outbox must hold the NAME of the credential, never the token itself"
    )
    assert [r["outcome"] for r in _rows()] == ["queued"]


def test_a_PERMANENT_refusal_is_logged_dropped_and_never_retried(monkeypatch):
    monkeypatch.setattr(notify, "_requests", _FakeRequests(_Resp(403, text="bot was kicked")))
    mid, outcome = notify.send_with_outcome(HALT, notify.HEALTH)
    assert (mid, outcome) == (None, "dropped")
    assert notify_log.entries() == []
    assert _rows()[-1]["outcome"] == "dropped"


def test_the_monitor_redelivers_a_queued_message_marked_DELAYED(monkeypatch):
    """The re-send says it is late, and when it was first tried — the reader's Telegram stamp says
    when it ARRIVED, and the whole point of the line is that the two differ.

    MUTATION: drop the `delayed_marker` line in `notify_log.flush` -> red."""
    fake = _FakeRequests(ConnectionError("down"), _Resp(200, mid=9))
    monkeypatch.setattr(notify, "_requests", fake)
    notify.send_with_outcome(HALT, notify.HEALTH, bot="sos_fade_demo")
    counts = notify.flush_outbox()
    assert counts["sent"] == 1
    assert notify_log.entries() == [], "a delivered entry leaves the outbox"
    sent_text = fake.posts[-1]["text"]
    assert sent_text.startswith(HALT)
    assert "(delayed, first tried" in sent_text.splitlines()[-1]
    last = _rows()[-1]
    assert last["outcome"] == "sent" and last["delayed"] is True and last["message_id"] == 9


def test_a_redelivery_that_fails_again_stays_queued_and_counts_its_attempts(monkeypatch):
    monkeypatch.setattr(
        notify, "_requests", _FakeRequests(ConnectionError("down"), ConnectionError("still down"))
    )
    notify.send_with_outcome(HALT, notify.HEALTH)
    assert notify.flush_outbox()["retry"] == 1
    (entry,) = notify_log.entries()
    assert entry["attempts"] == 1


def test_the_outbox_GIVES_UP_after_24_hours_and_says_so(monkeypatch):
    """MUTATION: remove the `GIVE_UP_SECONDS` check in `notify_log.flush` -> red (retries forever)."""
    monkeypatch.setattr(notify, "_requests", _FakeRequests(ConnectionError("down")))
    t0 = time.time()
    notify.send_with_outcome(HALT, notify.HEALTH)
    fake = _FakeRequests()
    monkeypatch.setattr(notify, "_requests", fake)
    counts = notify.flush_outbox(now=t0 + notify_log.GIVE_UP_SECONDS + 60)
    assert counts["dropped"] == 1 and fake.posts == [], "given up means NOT sent again"
    assert notify_log.entries() == []
    last = _rows()[-1]
    assert last["outcome"] == "dropped" and last.get("gave_up") is True


def test_an_UNWRITABLE_log_costs_the_log_never_the_message(monkeypatch, tmp_path):
    """A file where the folder should be makes every write fail."""
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")
    monkeypatch.setenv("LWG_NOTIFY_DIR", str(blocker))
    monkeypatch.setattr(notify, "_requests", _FakeRequests(_Resp(200, mid=5)))
    assert notify.send_telegram_id(HALT, notify.HEALTH) == 5


def test_no_room_is_logged_as_DROPPED_with_the_reason(monkeypatch):
    monkeypatch.delenv("LWG_TELEGRAM_CHAT_ID")
    monkeypatch.delenv("LWG_TELEGRAM_HEALTH_CHAT")
    monkeypatch.setattr(creds_mod, "_cache", {}, raising=False)
    monkeypatch.setattr(notify, "_requests", _FakeRequests())
    assert notify.send_with_outcome(HALT, notify.HEALTH) == (None, "dropped")
    assert _rows()[-1]["reason"] == "no room to send it to"


def test_the_flush_stamps_the_heartbeat_that_says_a_deliverer_is_alive(monkeypatch):
    """The policy (stage 2) only DEFERS a message while something will deliver it later — a hold
    waiting on a dead process is a drop. `flush_outbox` is what the monitor runs every minute."""
    assert notify_log.flusher_alive() is False
    notify.flush_outbox()
    assert notify_log.flusher_alive() is True
    assert notify_log.flusher_alive(now=time.time() + notify_log.FLUSHER_FRESH_SECONDS + 5) is False


def test_the_header_parser_reads_the_house_shape_and_survives_anything_else():
    assert notify_log.parse_header(HALT) == ("TRADING OFF", "SOS Fade · LIVE")
    assert notify_log.parse_header("ℹ️ ONLINE · Telegram bot\nx") == ("ONLINE", "Telegram bot")
    assert notify_log.parse_header("Realign (demo): no setup messages.")[0].startswith("Realign")
    assert notify_log.parse_header("") == ("", "")


# ── every health sender goes through the one notifier ───────────────────────────────────────


def test_the_WATCHDOG_sends_through_the_notifier_so_its_alerts_are_logged(monkeypatch):
    """It posted straight to Telegram until 2026-09-26, so OFFLINE, RESTARTED and STALLED — the
    alerts the policy most needs to see — never reached the log."""
    import monitor

    monkeypatch.setattr(notify, "_requests", _FakeRequests(_Resp(200, mid=3)))
    monitor.send_alert(
        alert(CRITICAL, "OFFLINE", "SOS Fade · LIVE", "Gone."), 34957946, bot="sos_fade_demo"
    )
    row = _rows()[-1]
    assert (row["label"], row["bot"], row["outcome"]) == ("OFFLINE", "sos_fade_demo", "sent")


def test_the_REVIEWER_counts_a_QUEUED_finding_as_said(monkeypatch):
    """A queued finding WILL arrive. Counting it unsaid would re-announce it next hour AND have the
    outbox deliver it — the same finding twice."""
    import log_review

    monkeypatch.setattr(notify, "_requests", _FakeRequests(ConnectionError("down")))
    assert log_review.send(alert(CRITICAL, "REVIEW", "SOS Fade · LIVE", "x"), bot="b") is True
    monkeypatch.setattr(notify, "_requests", _FakeRequests(_Resp(403)))
    assert log_review.send(alert(CRITICAL, "REVIEW", "SOS Fade · LIVE", "y"), bot="b") is False


def test_no_health_sender_posts_to_telegram_on_its_own():
    """The sweep behind the three rewires above: outside `shared/notify.py` (and the chat bot's
    command REPLY path, which answers the chat a person typed in and is not a broadcast) nothing
    in `algos/` builds its own `sendMessage` request. A private sender is a message the log, the
    outbox and the policy can never see."""
    offenders = []
    for path in sorted(_ALGOS.rglob("*.py")):
        rel = path.relative_to(_ALGOS).as_posix()
        if rel.startswith(("tests/", "markets/")) or rel in (
            "shared/notify.py",
            "notifications/telegram_bot.py",
        ):
            continue
        if "/sendMessage" in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(rel)
    assert offenders == [], f"these post to Telegram directly: {offenders}"
    chat_bot = (_ALGOS / "notifications" / "telegram_bot.py").read_text(encoding="utf-8")
    assert chat_bot.count("/sendMessage") == 1, "only the command-reply path may post directly"
