"""The health policy — which HEALTH messages are sent, held, or held to see if they clear (stage 2).

Driven through the REAL `notify.send_with_outcome`, with only Telegram's HTTP call faked, so the
policy, the outbox, the send log and the flusher are exercised together the way the box runs them.
The scenarios are the real ones from the 4–25 Sep 2026 hand count of the health room.

⚠ Rule 12. The policy shipped with these tests, so there was no red build to watch; each rule was
proven by MUTATION instead (run 2026-09-26 by `scratchpad/mutate.py`; the mutation is named on
the test that caught it). Every one went RED.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ALGOS / "shared"))

import alert_policy  # noqa: E402
import credentials as creds_mod  # noqa: E402
import notify  # noqa: E402
import notify_log  # noqa: E402
from alert_format import CRITICAL, INFO, OK, WARNING, alert  # noqa: E402

LIVE, DEMO = 34957946, 700152905


class _Resp:
    status_code = 200
    text = "ok"

    def __init__(self, mid):
        self._mid = mid

    def json(self):
        return {"ok": True, "result": {"message_id": self._mid}}


class _Telegram:
    """Records every message that REACHED a room."""

    def __init__(self):
        self.posts = []

    def post(self, url, json=None, timeout=None, **_kw):
        self.posts.append(json)
        return _Resp(len(self.posts))

    @property
    def texts(self):
        return [p["text"] for p in self.posts]


class _Clock:
    def __init__(self):
        self.t = 1_790_000_000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


@pytest.fixture
def box(monkeypatch, tmp_path):
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)
    monkeypatch.setenv("LWG_TELEGRAM_TOKEN", "T")
    monkeypatch.setenv("LWG_TELEGRAM_CHAT_ID", "-100trades")
    monkeypatch.setenv("LWG_TELEGRAM_HEALTH_CHAT", "-100health")
    monkeypatch.setenv("LWG_NOTIFY_DIR", str(tmp_path / "notify"))
    monkeypatch.setattr(notify, "_account_row", lambda account: {})
    monkeypatch.setattr(alert_policy, "action_in_progress", lambda bot: None)
    tg = _Telegram()
    monkeypatch.setattr(notify, "_requests", tg)
    clock = _Clock()
    monkeypatch.setattr(time, "time", clock)

    class Box:
        telegram = tg

        @staticmethod
        def send(text, bot="sos_fade_demo", account=LIVE):
            return notify.send_with_outcome(text, notify.HEALTH, account=account, bot=bot)[1]

        @staticmethod
        def monitor_pass(advance=0):
            clock.advance(advance)
            return notify.flush_outbox()

        @staticmethod
        def log():
            rows = []
            for p in sorted(notify_log.notify_dir().glob("*.jsonl")):
                rows += [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
            return rows

        tick = staticmethod(clock.advance)

    yield Box
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)


def _msg(icon, label, subject="SOS Fade · LIVE", *lines):
    return alert(icon, label, subject, *(lines or ("fact",)))


WILL_NOT_START = _msg(CRITICAL, "WILL NOT START", "SOS Fade · LIVE", "Startup failed: no such file")
OFFLINE = _msg(CRITICAL, "OFFLINE", "SOS Fade · LIVE", "The process is gone. Restarting it now.")
RESTARTED = _msg(OK, "RESTARTED", "SOS Fade · LIVE", "It was offline and has been restarted.")
ONLINE = _msg(OK, "ONLINE", "SOS Fade · LIVE", "Trading live · XAUUSD.p M15")
OFF = _msg(
    CRITICAL, "TRADING OFF", "Account 34957946 · LIVE", "The broker has switched trading off."
)
BACK_ON = _msg(OK, "TRADING BACK ON", "Account 34957946 · LIVE", "The account can trade again.")


# ── one alert per fault ─────────────────────────────────────────────────────────────────────


def test_the_same_fault_is_sent_ONCE_and_its_repeats_are_held_and_counted(box):
    """MUTATION: make the dedup comparison always False (`prev.get("body") == h` -> `False`) -> red."""
    assert [box.send(WILL_NOT_START) for _ in range(3)] == ["sent", "held", "held"]
    assert len(box.telegram.texts) == 1
    held = [r for r in box.log() if r["outcome"] == "held"]
    assert len(held) == 2 and all(r.get("covered") for r in held), (
        "a repeat of a SENT alert is marked covered, so the reviewer knows the reader saw it"
    )


def test_a_CHANGED_fault_text_is_a_new_fault_and_is_sent(box):
    box.send(WILL_NOT_START)
    other = _msg(CRITICAL, "WILL NOT START", "SOS Fade · LIVE", "Startup failed: a different one")
    assert box.send(other) == "sent"


def test_a_successful_START_clears_the_fault_so_the_next_failure_speaks(box):
    """MUTATION: drop the `DEFAULT_RECOVERED_BY` clearing AND the loop in step 1 -> red."""
    box.send(WILL_NOT_START)
    box.send(ONLINE)
    assert box.send(WILL_NOT_START) == "sent"


def test_a_fault_is_cleared_by_ITS_OWN_recovery_too_not_only_by_a_start(box):
    """WILL NOT START lists BACK ONLINE (the watchdog seeing it come up) as well as a start.

    MUTATION: drop the fault-clearing loop in step 1 of `_decide` -> red. (The start test above
    survives that mutation — a start also clears through the default path — which is why this
    one exists.)"""
    box.send(WILL_NOT_START)
    box.send(_msg(OK, "BACK ONLINE"))
    assert box.send(WILL_NOT_START) == "sent"


def test_the_same_fault_is_said_again_after_24_hours(box):
    box.send(WILL_NOT_START)
    box.tick(alert_policy.DEDUP_SECONDS + 1)
    assert box.send(WILL_NOT_START) == "sent"


def test_the_same_fault_about_ANOTHER_bot_is_its_own_fault(box):
    box.send(WILL_NOT_START, bot="sos_fade_demo")
    assert box.send(WILL_NOT_START, bot="extreme_leg_demo") == "sent"


def test_a_DROPPED_alert_is_not_remembered_so_its_repeat_is_not_held_as_seen(box, monkeypatch):
    class _Refuse(_Telegram):
        def post(self, url, json=None, timeout=None, **_kw):
            r = _Resp(0)
            r.status_code, r.text = 403, "bot was kicked"
            return r

    monkeypatch.setattr(notify, "_requests", _Refuse())
    assert box.send(WILL_NOT_START) == "dropped"
    monkeypatch.setattr(notify, "_requests", box.telegram)
    assert box.send(WILL_NOT_START) == "sent"


# ── the 17 Sep startup loop ─────────────────────────────────────────────────────────────────


def test_the_17_SEP_STARTUP_LOOP_reaches_the_room_as_ONE_message(box):
    """One missing file on 17 Sep: 17 WILL NOT START + 5 OFFLINE + 3 RESTARTED in 7 minutes. The
    first WILL NOT START says everything; the rest is the same fault or a quick recovery."""
    box.monitor_pass()  # the watchdog is alive
    for i in range(17):
        box.send(WILL_NOT_START)
        if i % 3 == 0:
            box.send(OFFLINE)
            box.tick(8)
            box.send(RESTARTED)
        box.monitor_pass(advance=20)
    assert box.telegram.texts == [WILL_NOT_START]
    assert sum(r["outcome"] == "held" for r in box.log()) >= 16 + 5 + 5


# ── hold to see whether it clears ───────────────────────────────────────────────────────────


def test_an_OFFLINE_that_the_watchdog_restarts_inside_5_minutes_is_held_with_its_recovery(box):
    """MUTATION: remove the `notify_log.cancel(...)` in the recovery step -> red."""
    box.monitor_pass()
    assert box.send(OFFLINE) == "queued"
    box.tick(8)
    assert box.send(RESTARTED) == "held"
    box.tick(30)
    assert box.send(ONLINE) == "held", "the bot's own ONLINE after one crash is the same event"
    box.monitor_pass(advance=600)
    assert box.telegram.texts == []
    reasons = [r.get("reason", "") for r in box.log() if r["outcome"] == "held"]
    assert any("cleared after" in r for r in reasons)


def test_an_OFFLINE_that_does_NOT_recover_is_sent_at_5_minutes_and_says_so(box):
    """MUTATION: delete the flush's deferred send (`not_before` never reached) -> red."""
    box.monitor_pass()
    box.send(OFFLINE)
    box.monitor_pass(advance=60)
    assert box.telegram.texts == []
    box.monitor_pass(advance=5 * 60)
    (sent,) = box.telegram.texts
    assert sent.startswith(OFFLINE) and "Still happening 5 minutes later" in sent
    assert box.send(RESTARTED) == "sent", "its fault was sent, so its recovery is needed"
    assert box.send(ONLINE) == "sent"


def test_with_NO_deliverer_running_nothing_is_deferred(box):
    """A hold that waits on a process which is not running is a DROP (new bot code on a box whose
    monitor is dead, or still on code that has never heard of the outbox).

    MUTATION: remove the `flusher_alive` condition -> red."""
    assert box.send(OFFLINE) == "sent"
    assert box.send(RESTARTED) == "sent"


def test_a_STALL_and_a_LINK_DROP_that_heal_are_held_too(box):
    box.monitor_pass()
    assert box.send(_msg(WARNING, "STALLED")) == "queued"
    assert box.send(_msg(OK, "RECOVERED")) == "held"
    assert box.send(_msg(CRITICAL, "NO MT5 LINK")) == "queued"
    assert box.send(_msg(OK, "RECONNECTED")) == "held"
    assert box.telegram.texts == []


def test_a_link_back_on_a_HALTED_bot_is_always_said(box):
    box.monitor_pass()
    box.send(_msg(CRITICAL, "NO MT5 LINK"))
    assert box.send(_msg(CRITICAL, "RECONNECTED — STILL HALTED")) == "sent"


# ── trading off, per ACCOUNT ────────────────────────────────────────────────────────────────


def test_the_19_SEP_BLIPS_send_NOTHING(box):
    """19 Sep: four episodes, ~40 s each, five bots on two accounts. The room got 20 TRADING BACK
    ON and no OFF. Every one of these cleared inside the 15-minute hold."""
    box.monitor_pass()
    bots = [
        ("sos_fade_demo", LIVE),
        ("extreme_leg_demo", LIVE),
        ("sos_fade_1", DEMO),
        ("extreme_leg_1", DEMO),
        ("realign_1", DEMO),
    ]
    for _episode in range(4):
        for bot, acct in bots:
            box.send(OFF, bot=bot, account=acct)
        box.tick(45)
        for bot, acct in bots:
            box.send(BACK_ON, bot=bot, account=acct)
        box.monitor_pass(advance=600)
    box.monitor_pass(advance=3600)
    assert box.telegram.texts == []


def test_an_OFF_that_LASTS_is_sent_ONCE_per_account_and_ONE_back_on_follows(box):
    """MUTATION: set TRADING OFF's scope to "bot" -> red (one OFF per bot)."""
    box.monitor_pass()
    for bot in ("sos_fade_demo", "extreme_leg_demo"):
        assert box.send(OFF, bot=bot) in ("queued", "held")
    box.monitor_pass(advance=16 * 60)
    (off,) = box.telegram.texts
    assert "Still happening 15 minutes later" in off
    assert box.send(BACK_ON, bot="sos_fade_demo") == "sent"
    assert box.send(BACK_ON, bot="extreme_leg_demo") == "held"
    assert len(box.telegram.texts) == 2


def test_a_BACK_ON_whose_OFF_was_never_sent_is_never_sent(box):
    """The 19 Sep defect itself: the OFF did not reach the room and the BACK ON did.

    MUTATION: delete the `needs_sent_fault` branch in `_decide` -> red."""
    assert box.send(BACK_ON) == "held"
    assert box.telegram.texts == []


def test_a_STILL_HALTED_is_always_said_and_ends_a_held_OFF(box):
    box.monitor_pass()
    box.send(OFF)
    still = _msg(CRITICAL, "STILL HALTED", "SOS Fade · LIVE", "halted while it was not")
    assert box.send(still) == "sent"
    box.monitor_pass(advance=20 * 60)
    assert box.telegram.texts == [still], "the held OFF was cancelled, not sent late"


# ── never held ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "label",
    [
        "HALTED",
        "FLEET HALT",
        "ACCOUNT MISMATCH",
        "CLOSE FAILED",
        "ORDER REFUSED",
        "ORDER REJECTED",
        "NOT BACK ONLINE",
        "SETTINGS LOADED — STILL HALTED",
        "REMINDER — DOWN",
    ],
)
def test_the_NEVER_HELD_labels_go_out_every_time(box, label):
    """MUTATION: drop "HALT" from `_never_hold` -> red on HALTED."""
    box.monitor_pass()
    msg = _msg(CRITICAL, label)
    assert [box.send(msg) for _ in range(3)] == ["sent", "sent", "sent"]


# ── routine, and once per version ───────────────────────────────────────────────────────────


def test_the_chat_bots_own_nightly_restart_is_held_and_a_TRADING_bots_restart_is_not(box):
    box.monitor_pass()
    assert box.send(_msg(OK, "RESTARTED", "Telegram bot"), bot=None, account=None) == "held"
    assert box.send(_msg(OK, "COMMANDS ONLINE", "Telegram bot"), bot=None, account=None) == "held"
    will_not = _msg(CRITICAL, "WILL NOT START", "Telegram bot", "3 restart attempts have failed")
    assert box.send(will_not, bot=None, account=None) == "sent"


def test_NO_SETUP_MESSAGES_is_said_once_per_bot_per_VERSION(box):
    v1 = _msg(WARNING, "NO SETUP MESSAGES", "Realign · demo", "Its strategy (RealignStrategy, v12)")
    v2 = _msg(WARNING, "NO SETUP MESSAGES", "Realign · demo", "Its strategy (RealignStrategy, v13)")
    assert box.send(v1, bot="realign_1") == "sent"
    box.send(_msg(OK, "ONLINE", "Realign · demo"), bot="realign_1")
    box.tick(3 * 86400)
    assert box.send(v1, bot="realign_1") == "held", "a restart on the same code says nothing new"
    assert box.send(v2, bot="realign_1") == "sent"


def test_a_bots_STOPPED_during_a_command_center_action_is_held(box, monkeypatch):
    stopped = _msg(INFO, "STOPPED", "SOS Fade · LIVE", "Shut down cleanly.")
    monkeypatch.setattr(alert_policy, "action_in_progress", lambda bot: "promote")
    assert box.send(stopped) == "held"
    monkeypatch.setattr(alert_policy, "action_in_progress", lambda bot: None)
    assert box.send(stopped) == "sent"


def test_the_action_record_is_read_off_the_bots_folder(tmp_path, monkeypatch):
    import repo_paths

    monkeypatch.setattr(repo_paths, "INSTANCES", tmp_path)
    (tmp_path / "b").mkdir()
    f = tmp_path / "b" / "alert_thread.json"
    assert alert_policy.action_in_progress("b") is None
    f.write_text(json.dumps({"message_id": 1, "expires_at": time.time() + 60, "action": "start"}))
    assert alert_policy.action_in_progress("b") == "start"
    f.write_text(json.dumps({"message_id": 1, "expires_at": time.time() + 60}))
    assert alert_policy.action_in_progress("b") == "promote", "an older record is a restart"
    f.write_text(json.dumps({"message_id": 1, "expires_at": time.time() - 1, "action": "start"}))
    assert alert_policy.action_in_progress("b") is None


# ── every failure answers SEND ──────────────────────────────────────────────────────────────


def test_a_CORRUPT_memory_sends_rather_than_swallowing(box):
    box.send(WILL_NOT_START)
    (notify_log.notify_dir() / "policy_state.json").write_text("{ not json")
    assert box.send(WILL_NOT_START) == "sent"


def test_a_lock_that_cannot_be_had_SENDS(box, monkeypatch):
    """A lock held by a live process (fresh mtime) that never lets go: after its short wait the
    policy gives up and SENDS — a trading loop may not wait on a notifier."""
    box.send(WILL_NOT_START)
    lock = notify_log.notify_dir() / "policy.lock"
    lock.write_text("")
    real_sleep = time.sleep
    monkeypatch.setattr(time, "sleep", lambda s: box.tick(s) or real_sleep(0))
    assert box.send(WILL_NOT_START) == "sent"


def test_a_policy_that_RAISES_sends(box, monkeypatch):
    monkeypatch.setattr(alert_policy, "_decide", lambda *a, **k: 1 / 0)
    box.send(WILL_NOT_START)
    assert box.send(WILL_NOT_START) == "sent"


def test_trades_and_setups_are_never_held(box):
    fill = "📈 ENTRY · LONG XAUUSD.p\nEntry 3,300.00"
    for _ in range(2):
        mid, outcome = notify.send_with_outcome(fill, notify.TRADE, account=LIVE, bot="b")
        assert outcome == "sent"


# ── the fixes made at the source ────────────────────────────────────────────────────────────


def test_SETTINGS_NOT_APPLIED_says_how_many_and_names_the_first_few():
    sys.path.insert(0, str(_ALGOS / "live"))
    from runner import refused_summary

    names = [f"exec_param_{i}" for i in range(25)]
    assert refused_summary(names) == (
        "25 changes need a restart: Param 0, Param 1, Param 2 and 22 more."
    )
    assert refused_summary(["account"]) == "1 change needs a restart: Account."
    assert refused_summary([]) == ""
    # The Command Center's label, never the code name (2026-09-30).
    labelled = refused_summary(["exec_risk_pct"], package="sos_fade")
    assert labelled == "1 change needs a restart: Risk % per trade."


def test_the_runner_says_SETTINGS_NOT_APPLIED_through_the_summary():
    """MUTATION: put `f"Refused: {detail}"` back in the alert -> red."""
    src = (_ALGOS / "live" / "runner.py").read_text(encoding="utf-8")
    block = src[
        src.index('"SETTINGS NOT APPLIED"') - 200 : src.index('"SETTINGS NOT APPLIED"') + 500
    ]
    assert "refused_summary(" in block and "Refused: {detail}" not in block


def test_a_terminal_that_lost_the_broker_says_THAT_not_that_the_broker_switched_trading_off():
    sys.path.insert(0, str(_ALGOS / "live"))
    from types import SimpleNamespace

    from runner import trading_block

    ok_acct = SimpleNamespace(trade_allowed=True, trade_expert=True)
    sym = SimpleNamespace(trade_mode=4)
    dropped = SimpleNamespace(trade_allowed=True, connected=False)
    allowed, why = trading_block(ok_acct, dropped, sym, "XAUUSD.p")
    assert allowed is False and "lost its connection" in why
    # A terminal double without the field is NOT disconnected — every existing test uses one.
    assert trading_block(ok_acct, SimpleNamespace(trade_allowed=True), sym, "XAUUSD.p") == (
        True,
        None,
    )


def test_an_EDIT_into_ONLINE_is_logged_and_clears_the_fault_like_a_new_message(box):
    """The bot edits the Command Center's message into its outcome (`runner._finish_action`); that
    start must clear a WILL NOT START exactly as a new ONLINE would.

    MUTATION: drop the `alert_policy.decide(...)` call in `notify.edit_telegram` -> red."""
    box.send(WILL_NOT_START)
    assert notify.edit_telegram("-100health", 9, ONLINE, account=LIVE, bot="sos_fade_demo")
    assert box.telegram.posts[-1] == {"chat_id": "-100health", "message_id": 9, "text": ONLINE}
    row = box.log()[-1]
    assert (row["outcome"], row["edit_of"], row["label"]) == ("sent", 9, "ONLINE")
    assert box.send(WILL_NOT_START) == "sent"
