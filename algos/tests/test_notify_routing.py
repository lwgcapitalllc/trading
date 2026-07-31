"""Telegram credential resolution and per-bot routing.

Two properties are being pinned here, and both were paid for.

**No literal secret.** The token was pasted into six files and committed. `credentials.py` is
the only thing that knows where a secret lives, so these tests assert on RESOLUTION ORDER —
env beats file beats empty — not on any value.

**Routing is per bot.** Bots are not interchangeable: a demo gold bot and a funded FX bot are
different conversations. A bot names its own destination (`chat_id`) and, optionally, its own
Telegram identity by NAMING a credential key (`token_key`) rather than carrying the token.

Every test here is offline. `send_telegram` is exercised through a stubbed HTTP layer, because
the one behaviour that matters most is that the notifier NEVER raises into a trading loop.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parent.parent / "shared"
sys.path.insert(0, str(_SHARED))
import credentials  # noqa: E402
import notify  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """No env, no file — every test declares exactly what exists."""
    for var in list(_ENV_VARS):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(credentials, "_cache", {})
    notify._warned = False
    notify._warned_keys = set()
    yield


_ENV_VARS = ("LWG_TELEGRAM_TOKEN", "LWG_TELEGRAM_CHAT_ID", "LWG_TELEGRAM_ADMIN_CHAT_ID",
             "LWG_TELEGRAM_TOKEN_BLEG")


class _Sent:
    """Captures what would have gone to Telegram."""

    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "chat_id": json["chat_id"], "text": json["text"]})
        return type("R", (), {"status_code": 200, "text": "ok"})()

    @property
    def last_token(self):
        return self.calls[-1]["url"].split("/bot")[1].split("/")[0]


@pytest.fixture
def sent(monkeypatch):
    s = _Sent()
    monkeypatch.setattr(notify, "_requests", s)
    return s


# ── resolution order ────────────────────────────────────────────────────────────
def test_env_beats_the_file(monkeypatch):
    monkeypatch.setattr(credentials, "_cache", {"telegram_token": "from-file"})
    monkeypatch.setenv("LWG_TELEGRAM_TOKEN", "from-env")
    assert credentials.get("telegram_token") == "from-env"


def test_a_missing_credential_is_empty_never_an_exception():
    """A bot must not crash at 2am because a notification channel is unset."""
    assert credentials.get("telegram_token") == ""


def test_any_key_resolves_not_just_the_canonical_three(monkeypatch):
    """This is what makes a second Telegram identity possible with no code change — a new key
    in the credentials file is enough."""
    monkeypatch.setattr(credentials, "_cache", {"telegram_token_bleg": "second-bot"})
    assert credentials.get("telegram_token_bleg") == "second-bot"


def test_a_custom_key_gets_a_predictable_env_name(monkeypatch):
    assert credentials.env_name("telegram_token_bleg") == "LWG_TELEGRAM_TOKEN_BLEG"
    monkeypatch.setenv("LWG_TELEGRAM_TOKEN_BLEG", "from-env")
    assert credentials.get("telegram_token_bleg") == "from-env"


def test_the_canonical_keys_keep_their_historical_env_names():
    """Renaming these would silently mute a VPS whose scheduled task sets the old name."""
    assert credentials.env_name("telegram_token") == "LWG_TELEGRAM_TOKEN"
    assert credentials.env_name("telegram_chat_id") == "LWG_TELEGRAM_CHAT_ID"


# ── per-bot routing ─────────────────────────────────────────────────────────────
def test_default_routing_goes_to_the_shared_group(monkeypatch, sent):
    monkeypatch.setattr(credentials, "_cache",
                        {"telegram_token": "T", "telegram_chat_id": "-100shared"})
    assert notify.send_telegram("hi") is True
    assert sent.calls[-1]["chat_id"] == "-100shared"


def test_a_bot_can_send_to_its_own_chat(monkeypatch, sent):
    monkeypatch.setattr(credentials, "_cache",
                        {"telegram_token": "T", "telegram_chat_id": "-100shared"})
    notify.send_telegram("hi", chat_id="-100mine")
    assert sent.calls[-1]["chat_id"] == "-100mine"


def test_a_bot_can_send_as_its_own_telegram_identity(monkeypatch, sent):
    """Two bots, two tokens, two groups — the whole point of the per-bot fields."""
    monkeypatch.setattr(credentials, "_cache", {
        "telegram_token": "DEFAULT", "telegram_chat_id": "-100shared",
        "telegram_token_bleg": "SECOND"})
    notify.send_telegram("hi", chat_id="-100bleg", token_key="telegram_token_bleg")
    assert sent.last_token == "SECOND"
    assert sent.calls[-1]["chat_id"] == "-100bleg"


def test_a_named_token_that_is_missing_falls_back_and_says_so(monkeypatch, sent, capsys):
    """The wrong sender identity is recoverable. A silently dropped trade alert is not — so it
    falls back rather than going mute, and prints the key that needs adding."""
    monkeypatch.setattr(credentials, "_cache",
                        {"telegram_token": "DEFAULT", "telegram_chat_id": "-100shared"})
    assert notify.send_telegram("hi", token_key="telegram_token_bleg") is True
    assert sent.last_token == "DEFAULT"
    assert "telegram_token_bleg" in capsys.readouterr().out


def test_the_fallback_warning_is_printed_once_per_key(monkeypatch, sent, capsys):
    """A message per bar would bury the log it is trying to draw attention to."""
    monkeypatch.setattr(credentials, "_cache",
                        {"telegram_token": "T", "telegram_chat_id": "-100shared"})
    for _ in range(3):
        notify.send_telegram("hi", token_key="telegram_token_bleg")
    assert capsys.readouterr().out.count("telegram_token_bleg") == 1


# ── unparseable Markdown must not eat the message ───────────────────────────────
# Telegram rejects the WHOLE message when Markdown does not parse, and a single underscore is
# enough. Bot keys, symbols and file paths are made of underscores — `mpc_sos_fade_demo`,
# `MT5_FFT`, `live_config.py` — so the alert most likely to be refused is the one carrying an
# exception, whose text is full of paths. Found on the first real send, 2026-07-31.

class _RejectsMarkdown:
    """Telegram's actual behaviour: 400 with a parse error while parse_mode is set."""

    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append(json)
        if "parse_mode" in json:
            return type("R", (), {
                "status_code": 400,
                "text": '{"ok":false,"error_code":400,"description":'
                        '"Bad Request: can\'t parse entities: Can\'t find end of the entity"'})()
        return type("R", (), {"status_code": 200, "text": "ok"})()


def test_a_message_telegram_cannot_parse_is_resent_unformatted(monkeypatch, capsys):
    monkeypatch.setattr(credentials, "_cache",
                        {"telegram_token": "T", "telegram_chat_id": "-100shared"})
    fake = _RejectsMarkdown()
    monkeypatch.setattr(notify, "_requests", fake)

    assert notify.send_telegram("MPC SOS Fade on MT5_FFT") is True
    assert len(fake.calls) == 2
    assert "parse_mode" in fake.calls[0]          # tried formatted first
    assert "parse_mode" not in fake.calls[1]      # then plain
    assert fake.calls[1]["text"] == "MPC SOS Fade on MT5_FFT"   # text itself is never mangled
    assert "plain text" in capsys.readouterr().out


def test_a_400_that_is_not_a_parse_error_is_not_retried(monkeypatch):
    """A bot that is not in the chat also 400s. Retrying that unformatted just fails twice and
    hides the real reason, which is the one worth reading."""
    monkeypatch.setattr(credentials, "_cache",
                        {"telegram_token": "T", "telegram_chat_id": "-100shared"})
    calls = []

    class _NotAMember:
        def post(self, url, json=None, timeout=None):
            calls.append(json)
            return type("R", (), {"status_code": 400,
                                  "text": '{"description":"Bad Request: chat not found"}'})()

    monkeypatch.setattr(notify, "_requests", _NotAMember())
    assert notify.send_telegram("hi") is False
    assert len(calls) == 1


# ── never raises ────────────────────────────────────────────────────────────────
def test_an_unconfigured_notifier_is_a_no_op_not_a_crash(sent):
    assert notify.send_telegram("hi") is False
    assert sent.calls == []


def test_a_dead_network_is_a_no_op_not_a_crash(monkeypatch):
    monkeypatch.setattr(credentials, "_cache",
                        {"telegram_token": "T", "telegram_chat_id": "-100shared"})

    class _Boom:
        def post(self, *a, **k):
            raise OSError("network is down")

    monkeypatch.setattr(notify, "_requests", _Boom())
    assert notify.send_telegram("hi") is False


def test_a_rejection_from_telegram_is_reported_not_raised(monkeypatch, capsys):
    monkeypatch.setattr(credentials, "_cache",
                        {"telegram_token": "T", "telegram_chat_id": "-100shared"})

    class _Refuses:
        def post(self, *a, **k):
            return type("R", (), {"status_code": 403, "text": "bot is not a member of the chat"})()

    monkeypatch.setattr(notify, "_requests", _Refuses())
    assert notify.send_telegram("hi", chat_id="-100notamember") is False
    assert "403" in capsys.readouterr().out
