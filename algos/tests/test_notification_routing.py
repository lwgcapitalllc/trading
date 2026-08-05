"""Which room a Telegram message lands in, and the guard that keeps it there.

**The failure this exists to prevent.** Every notifier in this repo sent to one chat. The chat
Aaron reads for fills was also carrying: twelve lifecycle messages from the live bot (link lost,
link restored, re-warming, startup banner, clean stop, config refused, bridge HALTED), nine from
the watchdog (offline, restarted, stalled, recovered), nine from the command center's buttons,
the Telegram bot's own startup ping, and every finished stress test. **A room that pings all day
about machinery is a room you learn to swipe away**, and the day you mute it you mute the alert
that says an order actually filled.

So a message now declares its KIND and the kind picks the room. Two properties are worth pinning
and the second is the one that will actually catch a regression:

1. The resolution itself — including that a MISSING health chat falls back and SAYS so, rather
   than dropping the message. The wrong room beats silence; that is the opposite call from
   `deadman_url`, where unset means the check cannot work at all.
2. **Every call site states a kind.** `kind` is a required argument, so a forgotten one is a
   `TypeError` — but a `TypeError` in a notifier is discovered at 3am on the VPS, inside the
   very alert that was trying to tell you something. The grep below finds it in the suite
   instead. It is the same shape as `test_ledger_streams.py`, which greps every `ledger.event()`
   call for exactly the same reason: a routing table nobody checks is a routing table that
   describes last month.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
_REPO = _ALGOS.parent
sys.path.insert(0, str(_ALGOS / "shared"))

import credentials as creds_mod      # noqa: E402
import notify                        # noqa: E402


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Both modules cache: `credentials` caches the FILE, `notify` caches which kinds it has
    already warned about. A test that inherits either reads another test's answer."""
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)
    notify._warned_kinds.clear()
    for var in ("LWG_TELEGRAM_CHAT_ID", "LWG_TELEGRAM_HEALTH_CHAT", "LWG_TELEGRAM_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    yield
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)
    notify._warned_kinds.clear()


def _creds(monkeypatch, **values):
    monkeypatch.setattr(creds_mod, "_cache", dict(values), raising=False)


# ── the two rooms ────────────────────────────────────────────────────────────────────────────

def test_a_trade_goes_to_the_trades_chat(monkeypatch):
    _creds(monkeypatch, telegram_chat_id="-100trades", telegram_health_chat="-100health")
    assert notify.chat_for(notify.TRADE) == ("-100trades", True)


def test_health_goes_to_the_health_chat(monkeypatch):
    _creds(monkeypatch, telegram_chat_id="-100trades", telegram_health_chat="-100health")
    assert notify.chat_for(notify.HEALTH) == ("-100health", True)


def test_the_two_rooms_are_not_the_same_room(monkeypatch):
    """The whole point, stated as one assertion so it cannot be refactored away by accident."""
    _creds(monkeypatch, telegram_chat_id="-100trades", telegram_health_chat="-100health")
    trade, _ = notify.chat_for(notify.TRADE)
    health, _ = notify.chat_for(notify.HEALTH)
    assert trade != health


# ── the fallback, and why it is loud ─────────────────────────────────────────────────────────

def test_an_unset_health_chat_falls_back_to_the_main_group(monkeypatch):
    """Delivery beats tidiness. An operator who has not made the second group yet still gets
    told the bridge halted."""
    _creds(monkeypatch, telegram_chat_id="-100trades")
    assert notify.chat_for(notify.HEALTH) == ("-100trades", False)


def test_the_fallback_says_so(monkeypatch, capsys):
    _creds(monkeypatch, telegram_chat_id="-100trades")
    notify.chat_for(notify.HEALTH)
    out = capsys.readouterr().out
    assert "telegram_health_chat" in out and "main group" in out


def test_the_fallback_warns_once_not_per_message(monkeypatch, capsys):
    """The watchdog sends on a 60s loop. A warning per send is a log nobody can read."""
    _creds(monkeypatch, telegram_chat_id="-100trades")
    for _ in range(5):
        notify.chat_for(notify.HEALTH)
    assert capsys.readouterr().out.count("telegram_health_chat") == 1


def test_a_trade_never_falls_back_to_the_health_chat(monkeypatch):
    """Deliberately asymmetric. Health borrowing the trades room is a nuisance; a FILL landing
    in the room full of re-warm chatter is the failure this whole change exists to prevent."""
    _creds(monkeypatch, telegram_health_chat="-100health")
    assert notify.chat_for(notify.TRADE) == ("", False)


# ── overrides and refusals ───────────────────────────────────────────────────────────────────

def test_a_bots_own_chat_wins(monkeypatch):
    """Per-bot routing from the instance config, which is what lets two bots on two accounts
    report into two different rooms."""
    _creds(monkeypatch, telegram_chat_id="-100trades")
    assert notify.chat_for(notify.TRADE, "-100mine") == ("-100mine", True)


def test_an_unknown_kind_raises(monkeypatch):
    """Not a silent fallback. A typo'd kind that quietly picked the main group would put a
    trade alert somewhere nobody chose and never mention it."""
    _creds(monkeypatch, telegram_chat_id="-100trades")
    with pytest.raises(ValueError):
        notify.chat_for("healthy")


def test_the_env_var_beats_the_file(monkeypatch):
    """`log_review.py` read credentials.json directly until 2026-08-05, which meant the
    documented `LWG_TELEGRAM_HEALTH_CHAT` did nothing at all. One resolver, one answer."""
    _creds(monkeypatch, telegram_chat_id="-100trades", telegram_health_chat="-100file")
    monkeypatch.setenv("LWG_TELEGRAM_HEALTH_CHAT", "-100env")
    assert notify.chat_for(notify.HEALTH) == ("-100env", True)


def test_the_health_key_has_a_registered_env_name():
    assert creds_mod.env_name("telegram_health_chat") == "LWG_TELEGRAM_HEALTH_CHAT"


# ── the send path actually uses the routing ──────────────────────────────────────────────────

class _FakeResponse:
    status_code = 200
    text = "{}"

    @staticmethod
    def json():
        return {"result": {"message_id": 7}}


def test_the_sender_posts_to_the_kinds_chat(monkeypatch):
    """The resolver being right is worth nothing if the sender ignores it — which is precisely
    how `send_telegram` behaved before this change."""
    _creds(monkeypatch, telegram_token="t", telegram_chat_id="-100trades",
           telegram_health_chat="-100health")
    seen = {}

    class _Req:
        @staticmethod
        def post(url, json=None, timeout=None):
            seen["chat"] = json["chat_id"]
            return _FakeResponse()

    monkeypatch.setattr(notify, "_requests", _Req)
    notify.send_telegram("the bridge halted", notify.HEALTH)
    assert seen["chat"] == "-100health"
    notify.send_telegram("filled long", notify.TRADE)
    assert seen["chat"] == "-100trades"


# ── the guard: every call site states a kind ─────────────────────────────────────────────────

_SEND_CALL = re.compile(r"\bsend_telegram(?:_id)?\s*\(")
_KIND_TOKEN = re.compile(r"\b(TRADE|HEALTH|notify\.TRADE|notify\.HEALTH|kind)\b")

_SOURCES = [
    _ALGOS / "live",
    _ALGOS / "notifications",
    _ALGOS / "tools",
    _ALGOS / "bots",
    _REPO / "command-center" / "backend" / "routers",
    _REPO / "command-center" / "backend" / "services",
]


def _call_sites():
    """(path, lineno, text) for every send call outside the sender modules themselves."""
    for root in _SOURCES:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if path.name == "notify.py":
                continue            # the definitions and the docstring examples live here
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines, 1):
                if _SEND_CALL.search(line):
                    # A call can wrap; give the checker the statement, not the first line of it.
                    yield path, i, "\n".join(lines[i - 1:i + 6])


def test_the_sweep_actually_finds_call_sites():
    """A grep test that matches nothing passes for ever and proves nothing. This is the same
    vacuous-check trap the Stress Test browser suite hit on 2026-08-05."""
    assert len(list(_call_sites())) >= 2


def test_every_send_call_states_its_kind():
    unrouted = [f"{p.relative_to(_REPO)}:{n}"
                for p, n, text in _call_sites() if not _KIND_TOKEN.search(text)]
    assert not unrouted, ("these Telegram sends do not say which room they belong in: "
                          + ", ".join(unrouted))
