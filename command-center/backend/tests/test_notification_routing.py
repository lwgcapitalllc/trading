"""Which Telegram room this app's messages land in.

**Context.** Everything this backend announces is about the MACHINERY — a bot started, stopped,
restarted, promoted, its runtime params applied, a stress test finished. Not one of them is a
fill; the live bot sends those itself from the VPS. They were all going to the chat Aaron reads
for fills, alongside the bot's own twelve lifecycle messages and the watchdog's nine, which is
how a trade alert stops being read.

So `send_telegram` takes a KIND and the kind picks the chat. This file pins the resolution and,
more usefully, pins that no sender in this app can quietly aim at the trades room.

⚠ This is the SECOND implementation of one routing rule — `algos/shared/notify.py` has the other
— and the duplication is the price of the subsystem boundary (a shared FILE is the allowed seam,
a shared import is not). The two are held together by reading the same credential KEYS, which is
what `test_the_keys_match_the_algos_side` checks by reading that file rather than restating it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import config as cfg
from services import notify

_BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(notify, "_cache", {}, raising=False)
    notify._warned_kinds.clear()
    for var in ("LWG_TELEGRAM_CHAT_ID", "LWG_TELEGRAM_HEALTH_CHAT", "LWG_TELEGRAM_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    yield
    notify._warned_kinds.clear()


def _creds(monkeypatch, **values):
    monkeypatch.setattr(notify, "_cache", dict(values), raising=False)


def test_health_goes_to_the_health_chat(monkeypatch):
    _creds(monkeypatch, telegram_chat_id="-100trades", telegram_health_chat="-100health")
    assert notify.chat_for(notify.HEALTH) == "-100health"


def test_a_trade_goes_to_the_trades_chat(monkeypatch):
    _creds(monkeypatch, telegram_chat_id="-100trades", telegram_health_chat="-100health")
    assert notify.chat_for(notify.TRADE) == "-100trades"


def test_an_unset_health_chat_falls_back_and_says_so(monkeypatch, capsys):
    """Delivery beats tidiness — an operator who has not made the second group yet still hears
    that a bot went down. The fallback is a nuisance you can see, never a silent drop."""
    _creds(monkeypatch, telegram_chat_id="-100trades")
    assert notify.chat_for(notify.HEALTH) == "-100trades"
    assert "telegram_health_chat" in capsys.readouterr().out


def test_the_fallback_warns_once(monkeypatch, capsys):
    _creds(monkeypatch, telegram_chat_id="-100trades")
    for _ in range(4):
        notify.chat_for(notify.HEALTH)
    assert capsys.readouterr().out.count("telegram_health_chat") == 1


def test_an_unknown_kind_raises(monkeypatch):
    _creds(monkeypatch, telegram_chat_id="-100trades")
    with pytest.raises(ValueError):
        notify.chat_for("ops")


def test_the_env_var_wins(monkeypatch):
    _creds(monkeypatch, telegram_chat_id="-100trades", telegram_health_chat="-100file")
    monkeypatch.setenv("LWG_TELEGRAM_HEALTH_CHAT", "-100env")
    assert notify.chat_for(notify.HEALTH) == "-100env"


def test_the_sender_posts_to_the_kinds_chat(monkeypatch):
    """The resolver being right is worth nothing if the sender ignores it."""
    _creds(monkeypatch, telegram_token="T", telegram_chat_id="-100trades",
           telegram_health_chat="-100health")
    seen = {}

    class _Resp:
        def close(self):
            pass

    def _urlopen(req, timeout=None):
        import json as _json
        seen["chat"] = _json.loads(req.data.decode())["chat_id"]
        return _Resp()

    monkeypatch.setattr(notify.urllib.request, "urlopen", _urlopen)
    assert notify.send_telegram("bot restarted", notify.HEALTH) is True
    assert seen["chat"] == "-100health"


def test_the_keys_match_the_algos_side():
    """One rule, two implementations, and drift here means a message routed by the credential
    key nobody set. Read the other file rather than restating its table."""
    src = (cfg.MONOREPO_ROOT / "algos" / "shared" / "notify.py").read_text(encoding="utf-8")
    for kind, (key, _env) in notify.CHAT_KEYS.items():
        assert f'"{key}"' in src, f"{kind!r} routes on {key!r}, which the algos side does not use"


# ── no sender in this app may aim at the trades room ─────────────────────────────────────────

_SEND_CALL = re.compile(r"\bsend_telegram\s*\(")


def _call_sites():
    for root in (_BACKEND / "routers", _BACKEND / "services"):
        for path in sorted(root.rglob("*.py")):
            if path.name == "notify.py":
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines, 1):
                if _SEND_CALL.search(line):
                    yield path, i, "\n".join(lines[i - 1:i + 4])


def test_the_sweep_actually_finds_call_sites():
    """A grep test matching nothing passes for ever and proves nothing."""
    assert len(list(_call_sites())) >= 2


def test_no_backend_sender_uses_the_trades_room():
    """This app has no way to know a trade happened — the bot on the VPS is the only thing that
    does. A `TRADE` here would be an operational message wearing a fill's clothes."""
    offenders = [f"{p.name}:{n}" for p, n, text in _call_sites() if "TRADE" in text]
    assert not offenders, f"these send to the trades chat and should not: {offenders}"


def test_every_backend_send_states_a_kind():
    unrouted = [f"{p.name}:{n}" for p, n, text in _call_sites()
                if not re.search(r"\b(notify\.HEALTH|notify\.TRADE|HEALTH|TRADE|kind)\b", text)]
    assert not unrouted, f"these Telegram sends do not say which room they belong in: {unrouted}"
