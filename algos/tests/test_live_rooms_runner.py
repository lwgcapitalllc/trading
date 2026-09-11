"""The live bot names itself with its account's kind, and its trades reach the LIVE rooms.

**Why (2026-09-11).** Two bots went onto real money while their demo copies kept trading the same
strategy, and Aaron made two channels for the live account alone — trades and signals. Health
stays one shared room. The room is chosen by the ACCOUNT a message is about (the account
registry's `kind`), never by a setting on the bot, so a bot moved onto a live account reports
there with no edit.

These drive `LiveRunner` itself — `_label` and `_notify` — through the REAL `notify.chat_for`, so a
wiring gap between the runner and the router cannot pass. The pieces are tested alone in
`test_notification_routing.py` and `test_account_label.py`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bot_state  # noqa: E402
import credentials as creds_mod  # noqa: E402
import notify  # noqa: E402
from runner import LiveRunner  # noqa: E402

_LIVE, _DEMO = 34957946, 700152905


@pytest.fixture
def world(monkeypatch, tmp_path):
    """A private account registry, private rooms, private credentials and a fake Telegram — so
    nothing here reads the real files or reaches the network."""
    reg = tmp_path / "accounts.json"
    reg.write_text(
        json.dumps(
            {"accounts": [{"account": _LIVE, "kind": "live"}, {"account": _DEMO, "kind": "demo"}]}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_state, "_ACCOUNTS", reg)
    rooms = tmp_path / "telegram_rooms.json"
    rooms.write_text(
        json.dumps({"live": {"trade": "-100live_trades", "signal": "-100live_signals"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(notify, "_ROOMS_PATH", rooms)
    monkeypatch.setattr(
        creds_mod,
        "_cache",
        {
            "telegram_token": "t",
            "telegram_chat_id": "-100trades",
            "telegram_health_chat": "-100health",
            "telegram_signal_chat": "-100signals",
        },
        raising=False,
    )
    notify._warned_live.clear()
    sent: list[tuple[str, str]] = []

    class _Resp:
        status_code = 200
        text = "{}"

        @staticmethod
        def json():
            return {"result": {"message_id": len(sent)}}

    class _Req:
        @staticmethod
        def post(url, json=None, timeout=None):
            sent.append((json["chat_id"], json["text"]))
            return _Resp()

    monkeypatch.setattr(notify, "_requests", _Req)
    yield sent
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)


def _runner(account, name="SOS Fade"):
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(
        bot_key="sos_fade_demo",
        display_name=name,
        account=account,
        telegram_chat_id="",
        telegram_signal_chat="",
        telegram_health_chat="",
        telegram_token_key="",
    )
    r.log = SimpleNamespace(warning=lambda *a, **k: None, info=lambda *a, **k: None)
    return r


def test_the_bot_names_itself_with_its_accounts_KIND(world):
    assert _runner(_LIVE)._label == "SOS Fade · LIVE"
    assert _runner(_DEMO)._label == "SOS Fade · demo"


def test_a_bot_with_no_readable_account_keeps_its_plain_name(world):
    """The runner tests elsewhere build a config with no account at all; the label must degrade
    to the name, never raise inside an alert built on a failure path."""
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(display_name="Bot")
    assert r._label == "Bot"


def test_a_LIVE_bots_trades_and_signals_reach_the_LIVE_rooms(world):
    """MUTATION: drop `account_kind=` from `_notify` -> red (both land in the shared rooms)."""
    r = _runner(_LIVE)
    r._notify("ENTRY", notify.TRADE)
    r._notify("SETUP", notify.SIGNAL)
    assert world == [("-100live_trades", "ENTRY"), ("-100live_signals", "SETUP")]


def test_a_LIVE_bots_health_stays_in_the_ONE_shared_health_room(world):
    _runner(_LIVE)._notify("HALTED", notify.HEALTH)
    assert world == [("-100health", "HALTED")]


def test_a_DEMO_bots_messages_keep_the_shared_rooms(world):
    """The demo copy running the same strategy stays out of the live channels entirely."""
    r = _runner(_DEMO)
    r._notify("ENTRY", notify.TRADE)
    r._notify("SETUP", notify.SIGNAL)
    r._notify("HALTED", notify.HEALTH)
    assert [chat for chat, _ in world] == ["-100trades", "-100signals", "-100health"]


def test_the_room_FOLLOWS_the_account_when_the_bot_is_moved(world):
    """Nothing on the bot says where it reports: move it and its next fill goes to the other room."""
    r = _runner(_DEMO)
    r._notify("before", notify.TRADE)
    r.cfg.account = _LIVE
    r._notify("after", notify.TRADE)
    assert world == [("-100trades", "before"), ("-100live_trades", "after")]
