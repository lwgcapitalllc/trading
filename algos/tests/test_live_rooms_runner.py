"""The live bot reports into ITS ACCOUNT's channels, and refuses to start when it has none.

**Why (2026-09-13).** Two people own two live accounts on this box. Aaron's rule: each account
names its own trades and signals channels, neither owner reads the other's fills, and a live bot
with nowhere to report does not trade at all. Health stays optional and falls back to the one
shared room, because most of it is about the box they share.

These drive `LiveRunner` itself — `_label`, `_notify`, `_unnamed_channels` and the gate in `_run` —
through the REAL `notify.chat_for`, so a wiring gap between the runner and the router cannot pass.
The router is tested alone in `test_notification_routing.py` and the label in
`test_account_label.py`.

🔴 **The case these are weighted toward is the one that cannot be undone**: a live fill reaching a
room the wrong person reads. Every other failure here is a message in the wrong place that somebody
can see and move on from.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import credentials as creds_mod  # noqa: E402
import notify  # noqa: E402
from runner import LiveRunner  # noqa: E402

_LIVE, _OTHER_LIVE, _DEMO = 34957946, 35710389, 700152905


def _bs():
    """The `bot_state` module the code under test will actually import, resolved NOW.

    🔴 Never a reference bound at import time: `test_mt5_ops_pending.py` and `test_mt5_lock.py`
    POP `bot_state` out of `sys.modules` to re-import `mt5_ops` against a fake terminal, so a
    module object bound at the top of this file goes stale the moment either runs — and patching
    the stale one leaves the code reading the REAL account registry. Green alone, red together.
    """
    return importlib.import_module("bot_state")


@pytest.fixture
def world(monkeypatch, tmp_path):
    """A private account registry, private credentials and a fake Telegram — so nothing here reads
    the committed channels or reaches the network. Yields the list of (chat, text) posted."""
    reg = tmp_path / "accounts.json"
    reg.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "account": _LIVE,
                        "kind": "live",
                        "telegram_trade_chat": "-100mine_t",
                        "telegram_signal_chat": "-100mine_s",
                    },
                    {
                        "account": _OTHER_LIVE,
                        "kind": "live",
                        "telegram_trade_chat": "",
                        "telegram_signal_chat": "",
                    },
                    {"account": _DEMO, "kind": "demo"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(_bs(), "_ACCOUNTS", reg)
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)
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
    notify._warned_no_room.clear()
    notify._warned_unreadable.clear()
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
    # 🔴 Stubbed so `_run` can carry on PAST the gate. Without it the wiring test below goes red
    # on a missing attribute rather than on its own assertion — which is a vacuous red: it would
    # pass for a gate that had been deleted, because the next line raises either way.
    import runner as runner_mod

    monkeypatch.setattr(runner_mod, "current_commit", lambda root: "abc1234")
    yield sent
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)
    notify._warned_no_room.clear()
    notify._warned_unreadable.clear()


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
        repo_root=Path("."),
        # ⚠ A DEPLOYED bot, because that is the only kind that reaches the channel gate: an
        # undeployed one refuses before it (2026-09-16). A stub without this describes a bot
        # production cannot produce, which is rule 13 from the other end.
        is_frozen=True,
    )
    r.log = SimpleNamespace(
        warning=lambda *a, **k: None, info=lambda *a, **k: None, error=lambda *a, **k: None
    )
    return r


# ── the label ────────────────────────────────────────────────────────────────────────────────


def test_the_bot_names_itself_with_its_accounts_KIND(world):
    assert _runner(_LIVE)._label == "SOS Fade · LIVE"
    assert _runner(_DEMO)._label == "SOS Fade · demo"


def test_a_bot_with_no_readable_account_keeps_its_plain_name(world):
    """The runner tests elsewhere build a config with no account at all; the label must degrade to
    the name, never raise inside an alert built on a failure path."""
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(display_name="Bot")
    assert r._label == "Bot"


# ── where a message lands ────────────────────────────────────────────────────────────────────


def test_a_LIVE_bots_trades_and_signals_reach_ITS_OWN_channels(world):
    """MUTATION: drop `account=` from `_notify` -> red (both land in the shared rooms)."""
    r = _runner(_LIVE)
    r._notify("ENTRY", notify.TRADE)
    r._notify("SETUP", notify.SIGNAL)
    assert world == [("-100mine_t", "ENTRY"), ("-100mine_s", "SETUP")]


def test_a_LIVE_bots_health_falls_back_to_the_shared_room(world):
    """Health is optional by decision — it is about the one box every account shares."""
    _runner(_LIVE)._notify("HALTED", notify.HEALTH)
    assert world == [("-100health", "HALTED")]


def test_a_DEMO_bots_messages_keep_the_shared_rooms(world):
    """The demo copy running the same strategy stays out of the live channels entirely."""
    r = _runner(_DEMO)
    r._notify("ENTRY", notify.TRADE)
    r._notify("SETUP", notify.SIGNAL)
    r._notify("HALTED", notify.HEALTH)
    assert [chat for chat, _ in world] == ["-100trades", "-100signals", "-100health"]


def test_the_channel_FOLLOWS_the_account_when_the_bot_is_moved(world):
    """Nothing on the bot says where it reports: move it and its next fill goes to the other
    account's channel, with no edit anywhere."""
    r = _runner(_DEMO)
    r._notify("before", notify.TRADE)
    r.cfg.account = _LIVE
    r._notify("after", notify.TRADE)
    assert world == [("-100trades", "before"), ("-100mine_t", "after")]


def test_a_LIVE_bot_whose_account_names_no_channel_SENDS_NOTHING(world):
    """🔴 The rule that cannot be undone. Not the shared room, not the other account's room —
    nothing. Health from the same bot still arrives, because that one is deliberately shared."""
    r = _runner(_OTHER_LIVE)
    assert r._notify("ENTRY", notify.TRADE) is None
    assert r._notify("SETUP", notify.SIGNAL) is None
    assert world == []
    r._notify("HALTED", notify.HEALTH)
    assert world == [("-100health", "HALTED")]


# ── the startup gate ─────────────────────────────────────────────────────────────────────────


def test_a_LIVE_bot_with_both_channels_may_start(world):
    """The CONTROL, and without it every case below passes for a gate that refuses everything."""
    assert _runner(_LIVE)._unnamed_channels() == ""


def test_a_LIVE_bot_with_neither_channel_is_refused_and_the_message_names_both(world):
    assert _runner(_OTHER_LIVE)._unnamed_channels() == "trades and signals"


def test_the_missing_channels_are_named_in_a_FIXED_order(world, monkeypatch, tmp_path):
    """A set comes back in whatever order it feels like. The log line and the Telegram message
    have to read the same way every time, or two reports of one problem look like two problems."""
    reg = tmp_path / "one.json"
    reg.write_text(
        json.dumps(
            {
                "accounts": [
                    {"account": _LIVE, "kind": "live", "telegram_signal_chat": "-100s"},
                    {"account": _OTHER_LIVE, "kind": "live", "telegram_trade_chat": "-100t"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(_bs(), "_ACCOUNTS", reg)
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)
    assert _runner(_LIVE)._unnamed_channels() == "trades"
    assert _runner(_OTHER_LIVE)._unnamed_channels() == "signals"


def test_a_DEMO_bot_is_NEVER_gated(world):
    """A demo account keeps the shared rooms and always has. Gating it would take the demo fleet
    down over a field that has never been required of it."""
    assert _runner(_DEMO)._unnamed_channels() == ""


def test_an_UNREADABLE_registry_lets_the_bot_START(world, monkeypatch, tmp_path):
    """🔴 A DECISION, not a fallthrough. Of the two wrong answers, a bot that does not trade
    because a JSON file will not parse costs setups nobody can get back, while a message in the
    shared room is a privacy failure somebody can see and correct. Money outranks privacy, and
    the notifier says so loudly on every send."""
    bad = tmp_path / "accounts.json"
    bad.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(_bs(), "_ACCOUNTS", bad)
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)
    assert _runner(_LIVE)._unnamed_channels() == ""


def test_the_gate_NEVER_raises(world, monkeypatch):
    """A gate that can crash the startup it guards is worse than the gap it closes."""

    def boom(_account):
        raise RuntimeError("registry on fire")

    monkeypatch.setattr(notify, "missing_rooms", boom)
    assert _runner(_LIVE)._unnamed_channels() == ""


def test_the_gate_is_WIRED_into_the_start_and_the_bot_does_not_reach_its_code(world, monkeypatch):
    """🔴 THE CALL SITE, not the helper. A guard is only as real as the line that invokes it —
    this repo has already shipped a startup check nothing called, described in four docstrings as
    the gate. Drives `_run` and asserts the bot never reached the version pin.

    MUTATION: delete the block from `_run` -> red.
    """
    r = _runner(_OTHER_LIVE)
    bound = []
    r.already_running = lambda: False
    # Records that it was reached and then refuses, so the mutated run ends on the version-pin
    # path rather than on a missing attribute further down `_run`. A red for the wrong reason
    # would kill this mutation whether or not the gate existed.
    r._bind_code = lambda: bound.append("bound") or (_ for _ in ()).throw(RuntimeError("pin"))
    r.ledger = SimpleNamespace(event=lambda name, **kw: bound.append((name, kw)))
    code, reason = r._run()
    assert code == 5
    assert "trades and signals" in reason
    assert "bound" not in bound
    assert ("startup_failed", {"error": reason}) in bound
    # It says so where a person will see it, in the room that still works for this account.
    assert world and "WILL NOT START" in world[0][1]
    assert world[0][0] == "-100health"


def test_a_LIVE_bot_WITH_its_channels_is_not_stopped_by_the_gate(world, monkeypatch):
    """The control for the wiring test: the same path, on an account that is configured, gets past
    the gate and on to the version pin. Without it, a gate that refused every bot would pass."""
    r = _runner(_LIVE)
    r.already_running = lambda: False
    reached = []
    r._bind_code = lambda: reached.append("bound") or (_ for _ in ()).throw(RuntimeError("stop"))
    r.ledger = SimpleNamespace(event=lambda name, **kw: None)
    r.source_hash = ""
    code, _reason = r._run()
    assert reached == ["bound"]
    assert code == 2  # the version-pin refusal, i.e. it got past this gate


# ── what the start-up log SAYS about where signals go ───────────────────────────────────────


def test_the_start_up_line_names_the_ACCOUNTS_signals_channel_on_a_live_account(world):
    """🔴 Rule 7 on the bot's own log. It said "the shared telegram_signal_chat" for every bot with
    no per-bot room until 2026-09-14, while the live bot's signals were going to its account's
    channel — so the one line a person reads at start-up described a room nothing was using.
    MUTATION: return the shared room without asking the account -> red."""
    assert _runner(_LIVE)._signal_room() == f"account {_LIVE}'s own signals channel -100mine_s"


def test_the_start_up_line_says_SHARED_only_when_it_is(world):
    """The control: a demo account names no room, and its signals really do go to the shared one."""
    assert _runner(_DEMO)._signal_room() == "the shared signals channel"


def test_a_per_bot_signals_room_is_named_first(world):
    """The order `notify.chat_for` routes in — a per-bot room wins outright."""
    r = _runner(_LIVE)
    r.cfg.telegram_signal_chat = "-100perbot"
    assert r._signal_room() == "this bot's own signals channel -100perbot"


def test_the_start_up_line_NEVER_raises(world, monkeypatch):
    """It only describes; a start-up log line must never stop a start."""

    def boom(_account):
        raise RuntimeError("registry on fire")

    monkeypatch.setattr(notify, "account_rooms", boom)
    assert _runner(_LIVE)._signal_room() == "the shared signals channel"
