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

import json
import re
import sys
from pathlib import Path

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
_REPO = _ALGOS.parent
sys.path.insert(0, str(_ALGOS / "shared"))

import credentials as creds_mod  # noqa: E402
import notify  # noqa: E402


def _bs():
    """The `bot_state` module `notify` will actually import, resolved NOW.

    🔴 **Never a reference bound at import time, and this cost a green-alone / red-together
    failure.** `test_mt5_ops_pending.py` and `test_mt5_lock.py` POP `bot_state` out of
    `sys.modules` so they can re-import `mt5_ops` against a fake terminal — so once either has
    run, a module object bound at the top of this file is a stale copy. Patching the stale one
    leaves `notify` reading the REAL account registry, and these tests then pass or fail on
    whatever channel is committed. **Found by running the suite together; every file passed
    alone**, which is the worst failure shape a suite has.
    """
    import importlib

    return importlib.import_module("bot_state")


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch, tmp_path):
    """Three module-level caches, and a test that inherits any of them reads another test's
    answer: `credentials` caches the file, `notify` remembers which warnings it has already
    printed, and `bot_state` keeps the last account rows it could parse.

    ⚠ The account registry is pointed at a PRIVATE path that does not exist, so every test starts
    with no accounts — the committed file names real channels, and a test reading it would pass or
    fail on whatever was last written there. The tests that want a row write their own.
    ⚠ **`_accounts_cache` is cleared as well as the path.** Clearing only the path leaves the last
    good rows in place and the registry answers a REAL account to a test that wrote none, which is
    the cache doing exactly its job in the one place it must not."""
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)
    monkeypatch.setattr(_bs(), "_ACCOUNTS", tmp_path / "no_accounts_here.json")
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)
    notify._warned_kinds.clear()
    notify._warned_no_room.clear()
    notify._warned_unreadable.clear()
    for var in ("LWG_TELEGRAM_CHAT_ID", "LWG_TELEGRAM_HEALTH_CHAT", "LWG_TELEGRAM_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    yield
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)
    notify._warned_kinds.clear()
    notify._warned_no_room.clear()
    notify._warned_unreadable.clear()


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


# ── EVERY ACCOUNT NAMES ITS OWN ROOMS (2026-09-13) ───────────────────────────────────────────
#
# The rule that replaced one shared pair of live rooms: two people own two live accounts on this
# box, so a room belongs to the ACCOUNT. The case these tests are weighted toward is the one that
# cannot be undone — a live fill reaching a room the wrong person reads — which is why a live
# account's trade and signal rooms are the one destination in this module with NO fallback.

_LIVE = 34957946
_OTHER_LIVE = 35710389
_DEMO = 700152905

_SHARED = dict(
    telegram_chat_id="-100trades",
    telegram_health_chat="-100health",
    telegram_signal_chat="-100signals",
)


def _accounts(monkeypatch, tmp_path, *rows):
    """Write an account registry and point `bot_state` at it. ⚠ The cache is cleared too: it
    deliberately survives an unreadable read, so leaving it set would answer the PREVIOUS rows."""
    path = tmp_path / "accounts.json"
    path.write_text(json.dumps({"_README": "test", "accounts": list(rows)}), encoding="utf-8")
    monkeypatch.setattr(_bs(), "_ACCOUNTS", path)
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)


def _row(account, kind="live", **rooms):
    return {"account": account, "kind": kind, **rooms}


def test_an_accounts_own_rooms_carry_its_trades_and_signals(monkeypatch, tmp_path):
    """The whole point: two live accounts, two sets of channels, neither reading the other."""
    _creds(monkeypatch, **_SHARED)
    _accounts(
        monkeypatch,
        tmp_path,
        _row(_LIVE, telegram_trade_chat="-100mine_t", telegram_signal_chat="-100mine_s"),
        _row(_OTHER_LIVE, telegram_trade_chat="-100his_t", telegram_signal_chat="-100his_s"),
    )
    assert notify.chat_for(notify.TRADE, account=_LIVE) == ("-100mine_t", True)
    assert notify.chat_for(notify.SIGNAL, account=_LIVE) == ("-100mine_s", True)
    assert notify.chat_for(notify.TRADE, account=_OTHER_LIVE) == ("-100his_t", True)
    assert notify.chat_for(notify.SIGNAL, account=_OTHER_LIVE) == ("-100his_s", True)


def test_a_LIVE_trade_with_no_room_of_its_own_is_NOT_SENT(monkeypatch, tmp_path, capsys):
    """🔴 THE RULE THIS FILE EXISTS FOR, and it is the opposite call from every other fallback
    here. A live fill in a room the wrong person reads cannot be taken back, so it is not sent —
    an EMPTY chat id, which `send_telegram_id` refuses to post to — and it says so once, not per
    fill. The runner's startup gate is what stops this being an ordinary state."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _row(_OTHER_LIVE))
    for _ in range(3):
        assert notify.chat_for(notify.TRADE, account=_OTHER_LIVE) == ("", False)
        assert notify.chat_for(notify.SIGNAL, account=_OTHER_LIVE) == ("", False)
    out = capsys.readouterr().out
    assert out.count("names no trade channel") == 1
    assert out.count("names no signal channel") == 1


def test_one_live_account_missing_a_room_does_not_silence_the_other(monkeypatch, tmp_path):
    """The refusal is per ACCOUNT. A second live account arriving unconfigured must not stop the
    first account's fills — that would make adding somebody take the other owner's alerts down."""
    _creds(monkeypatch, **_SHARED)
    _accounts(
        monkeypatch,
        tmp_path,
        _row(_LIVE, telegram_trade_chat="-100mine_t", telegram_signal_chat="-100mine_s"),
        _row(_OTHER_LIVE),
    )
    assert notify.chat_for(notify.TRADE, account=_OTHER_LIVE) == ("", False)
    assert notify.chat_for(notify.TRADE, account=_LIVE) == ("-100mine_t", True)


def test_a_DEMO_account_with_no_rooms_keeps_the_SHARED_rooms(monkeypatch, tmp_path):
    """Unchanged behaviour, and it has to stay unchanged: the demo bots report where they always
    did. The no-fallback rule is about real money, not about tidiness."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _row(_DEMO, kind="demo"))
    assert notify.chat_for(notify.TRADE, account=_DEMO) == ("-100trades", True)
    assert notify.chat_for(notify.SIGNAL, account=_DEMO) == ("-100signals", True)
    assert notify.chat_for(notify.HEALTH, account=_DEMO) == ("-100health", True)


def test_a_DEMO_account_MAY_name_its_own_rooms(monkeypatch, tmp_path):
    """Nothing does today. It is honoured so the shape scales to a demo account somebody wants
    reported apart — the alternative is a rule that reads the same fields and ignores them, which
    is a field nobody can trust."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _row(_DEMO, kind="demo", telegram_trade_chat="-100demo_t"))
    assert notify.chat_for(notify.TRADE, account=_DEMO) == ("-100demo_t", True)


def test_LIVE_health_falls_back_to_the_shared_room_with_NO_warning(monkeypatch, tmp_path, capsys):
    """Aaron's call: health is optional, because most of it is about the one box every account
    shares. It must arrive, in the shared room, and quietly — a warning printed on every health
    message is how the useful ones stop being read."""
    _creds(monkeypatch, **_SHARED)
    _accounts(
        monkeypatch,
        tmp_path,
        _row(_LIVE, telegram_trade_chat="-100mine_t", telegram_signal_chat="-100mine_s"),
    )
    assert notify.chat_for(notify.HEALTH, account=_LIVE) == ("-100health", True)
    assert "names no" not in capsys.readouterr().out


def test_an_accounts_own_HEALTH_room_is_used_when_it_names_one(monkeypatch, tmp_path):
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _row(_LIVE, telegram_health_chat="-100mine_h"))
    assert notify.chat_for(notify.HEALTH, account=_LIVE) == ("-100mine_h", True)


def test_a_bots_own_room_still_wins_over_the_accounts(monkeypatch, tmp_path):
    """A per-bot room is an explicit choice for THAT bot and keeps its old precedence. ⚠ It stays
    WITH the bot when the bot moves, which is why nothing sets one today."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _row(_LIVE, telegram_trade_chat="-100mine_t"))
    assert notify.chat_for(notify.TRADE, "-100bot", account=_LIVE) == ("-100bot", True)


def test_an_account_the_registry_does_not_carry_keeps_the_shared_rooms(monkeypatch, tmp_path):
    """Read, and this login is simply not in it — which is what every message did before any of
    this existed. It is not the same as the file being unreadable; the test below is that one."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _row(_DEMO, kind="demo"))
    assert notify.chat_for(notify.TRADE, account=999999) == ("-100trades", True)


def test_an_UNREADABLE_registry_still_sends_and_SAYS_so_once(monkeypatch, tmp_path, capsys):
    """🔴 THE ONE PATH HERE THAT CAN PUT A LIVE FILL IN THE SHARED ROOM, so it is loud. Of the two
    wrong answers, dropping every message on a box whose account file will not parse is worse than
    a message somebody can see in the wrong room. It cannot be established that the account is
    live, so it cannot be refused on those grounds either."""
    _creds(monkeypatch, **_SHARED)
    bad = tmp_path / "accounts.json"
    bad.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(_bs(), "_ACCOUNTS", bad)
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)
    for _ in range(3):
        assert notify.chat_for(notify.TRADE, account=_LIVE) == ("-100trades", True)
    assert capsys.readouterr().out.count("could not be read") == 1


def test_an_unreadable_registry_answers_the_LAST_GOOD_rows(monkeypatch, tmp_path):
    """🔴 LOAD-BEARING, not an optimisation. The box's hourly sync runs `git pull`, which rewrites
    the registry — and a fill composed inside that window would otherwise be told its account does
    not exist, which for a live account means a message nobody is sent."""
    _creds(monkeypatch, **_SHARED)
    path = tmp_path / "accounts.json"
    _accounts(monkeypatch, tmp_path, _row(_LIVE, telegram_trade_chat="-100mine_t"))
    assert notify.chat_for(notify.TRADE, account=_LIVE) == ("-100mine_t", True)
    path.write_text("", encoding="utf-8")  # mid-rewrite
    assert notify.chat_for(notify.TRADE, account=_LIVE) == ("-100mine_t", True)


def test_a_room_of_whitespace_is_NO_room(monkeypatch, tmp_path):
    """A field somebody cleared by pressing space is not a channel, and posting to `" "` fails at
    Telegram with a message nobody reads. It has to reach the same refusal as an empty one."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _row(_LIVE, telegram_trade_chat="   "))
    assert notify.chat_for(notify.TRADE, account=_LIVE) == ("", False)


def test_missing_rooms_names_what_a_live_account_still_owes(monkeypatch, tmp_path):
    """What the runner's startup gate reads. THREE answers: nothing owed, the kinds owed, and
    `None` for a registry that could not be asked."""
    _creds(monkeypatch, **_SHARED)
    _accounts(
        monkeypatch,
        tmp_path,
        _row(_LIVE, telegram_trade_chat="-100t", telegram_signal_chat="-100s"),
        _row(_OTHER_LIVE, telegram_trade_chat="-100t"),
    )
    assert notify.missing_rooms(_LIVE) == ()
    assert notify.missing_rooms(_OTHER_LIVE) == (notify.SIGNAL,)
    monkeypatch.setattr(_bs(), "_ACCOUNTS", tmp_path / "gone.json")
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)
    assert notify.missing_rooms(_LIVE) is None


def test_HEALTH_is_not_something_a_live_account_owes():
    """Pinned as its own claim rather than left as a gap in the list above: making health required
    would stop a bot starting over a room that is deliberately shared."""
    assert notify.REQUIRED_LIVE_KINDS == (notify.TRADE, notify.SIGNAL)
    assert notify.HEALTH not in notify.REQUIRED_LIVE_KINDS


def test_the_COMMITTED_registry_gives_every_live_account_a_trade_and_signal_room():
    """The real file. A live account with no rooms is a bot that will not start, so this goes red
    the day one is added without them — which is the moment to enter them, not the morning
    somebody wonders why a bot is down.

    ⚠ It pinned 35710389 as the one account still waiting for its rooms until its owner entered
    both on 2026-09-14 — so it went red the day the rooms landed, and the pin is gone. Proved by
    mutation (2026-09-15): blanking either room of either live account on a copy of the file turns
    it red; the real file passes."""
    raw = json.loads((_ALGOS / "markets" / "fx" / "accounts.json").read_text(encoding="utf-8"))
    live = [r for r in raw["accounts"] if r.get("kind") == "live"]
    assert live, "the registry names no live account - this test would pass for free"
    # 🔴 A room that is present and MALFORMED is the case nothing else would catch until a fill was
    # refused by Telegram.
    for row in live:
        for field in ("telegram_trade_chat", "telegram_signal_chat", "telegram_health_chat"):
            value = row.get(field, "")
            assert isinstance(value, str), f"{row['account']} {field}: {value!r}"
            if value:
                assert re.fullmatch(r"-?\d{5,20}|@[A-Za-z0-9_]{5,32}", value), (
                    f"{row['account']} {field}: {value!r}"
                )
    unnamed = [
        (r["account"], field)
        for r in live
        for field in ("telegram_trade_chat", "telegram_signal_chat")
        if not r.get(field)
    ]
    assert unnamed == [], f"a live account names no room its bot needs to start: {unnamed}"


def test_every_account_row_carries_all_three_channel_fields():
    """Present on EVERY row, demo included, because an absent field and an empty one read alike to
    a person editing the file — and the Command Center writes all three."""
    raw = json.loads((_ALGOS / "markets" / "fx" / "accounts.json").read_text(encoding="utf-8"))
    for row in raw["accounts"]:
        for field in ("telegram_trade_chat", "telegram_signal_chat", "telegram_health_chat"):
            assert field in row, f"account {row.get('account')} has no {field}"


def test_the_sender_posts_to_the_accounts_own_room(monkeypatch, tmp_path):
    """The resolver being right is worth nothing if the sender does not hand it the account."""
    _creds(monkeypatch, telegram_token="t", **_SHARED)
    _accounts(
        monkeypatch,
        tmp_path,
        _row(_LIVE, telegram_trade_chat="-100mine_t"),
        _row(_DEMO, kind="demo"),
    )
    seen = {}

    class _Req:
        @staticmethod
        def post(url, json=None, timeout=None):
            seen["chat"] = json["chat_id"]
            return _FakeResponse()

    monkeypatch.setattr(notify, "_requests", _Req)
    notify.send_telegram("filled long", notify.TRADE, account=_LIVE)
    assert seen["chat"] == "-100mine_t"
    notify.send_telegram_id("filled long", notify.TRADE, account=_DEMO)
    assert seen["chat"] == "-100trades"


def test_the_sender_REFUSES_a_live_trade_with_no_room(monkeypatch, tmp_path):
    """The refusal has to reach the wire, not just the resolver: an empty destination must stop
    the post rather than being handed to Telegram as a chat id."""
    _creds(monkeypatch, telegram_token="t", **_SHARED)
    _accounts(monkeypatch, tmp_path, _row(_OTHER_LIVE))
    posted = []

    class _Req:
        @staticmethod
        def post(url, json=None, timeout=None):
            posted.append(json["chat_id"])
            return _FakeResponse()

    monkeypatch.setattr(notify, "_requests", _Req)
    assert notify.send_telegram("filled long", notify.TRADE, account=_OTHER_LIVE) is False
    assert posted == []


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
    _creds(
        monkeypatch,
        telegram_token="t",
        telegram_chat_id="-100trades",
        telegram_health_chat="-100health",
    )
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
# ⚠ **Every room this suite has must appear here, and `SIGNAL` was missing for a day.** It shipped
# on 2026-08-13 and this list was not touched, so a correctly-routed signals send read as an
# UNROUTED one — the first to arrive (`tools/signal_samples.py`) failed this test while doing
# exactly the right thing. It went unnoticed that long because `setup_alerts.py` posts through an
# injected `self._send` rather than calling `send_telegram` by name, so the only consumer of the
# new room was invisible to the matcher above. **A guard with a hardcoded list of the valid
# answers goes stale the moment a valid answer is added, and it fails in the direction that
# accuses correct code — which is the one people fix by editing the code rather than the guard.**
_KIND_TOKEN = re.compile(r"\b(TRADE|HEALTH|SIGNAL|notify\.(TRADE|HEALTH|SIGNAL)|kind)\b")

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
                continue  # the definitions and the docstring examples live here
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            for i, line in enumerate(lines, 1):
                if _SEND_CALL.search(line):
                    # A call can wrap; give the checker the statement, not the first line of it.
                    yield path, i, "\n".join(lines[i - 1 : i + 6])


def test_the_sweep_actually_finds_call_sites():
    """A grep test that matches nothing passes for ever and proves nothing. This is the same
    vacuous-check trap the Stress Test browser suite hit on 2026-08-05."""
    assert len(list(_call_sites())) >= 2


def test_every_send_call_states_its_kind():
    unrouted = [
        f"{p.relative_to(_REPO)}:{n}"
        for p, n, text in _call_sites()
        if not _KIND_TOKEN.search(text)
    ]
    assert not unrouted, "these Telegram sends do not say which room they belong in: " + ", ".join(
        unrouted
    )
