"""A second room may read the SETUPS, and may never read the fills.

**What this is for.** Two owners run live accounts on this box and each account names its own
rooms, so neither reads the other's money (`test_notification_routing.py`). The user asked on
2026-09-23 for the rev-setup bot's SETUP messages to arrive in his own signals room as well as in
his brother's — the same setups, twice, with the fills left exactly where they are.

**The property that matters here is the one that says NO.** A copy destination is a few lines of
code, and the thing those lines must never do is copy a TRADE: a live fill in a room the wrong
person reads cannot be taken back, and it is the failure the whole per-account routing design was
built to prevent. So the fills and the machinery are pinned as NOT copied, in their own tests,
above the test that the copy works at all.

**Watched RED (2026-09-23), two mutations.** With the `_copy_signal` call removed from
`send_telegram_id`, the six tests that assert a copy arrives go red and the seven that assert one
does not stay green. With the `kind == SIGNAL` guard removed instead, exactly the two that pin
fills and health as never copied go red. Opposite halves, which is what proves they are reading
the feature rather than each other.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ALGOS / "shared"))

import credentials as creds_mod  # noqa: E402
import notify  # noqa: E402

_HIS_LIVE = 34957946
_MY_LIVE = 35710389
_DEMO = 700152905

_SHARED = dict(
    telegram_token="t",
    telegram_chat_id="-100trades",
    telegram_health_chat="-100health",
    telegram_signal_chat="-100signals",
)


def _bs():
    """The `bot_state` module `notify` will import, resolved NOW — never bound at import.

    Same reason as `test_notification_routing._bs`: other files pop `bot_state` out of
    `sys.modules`, so a reference taken at the top of this file can be a stale copy, and patching
    the stale one leaves `notify` reading the REAL committed registry.
    """
    import importlib

    return importlib.import_module("bot_state")


@pytest.fixture(autouse=True)
def _clean(monkeypatch, tmp_path):
    """No inherited caches, no real registry, and no real copies file.

    ⚠ Both files are pointed at paths that do not exist, so a test that writes neither is
    answering about an empty box rather than about whatever is committed today.
    """
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)
    monkeypatch.setattr(_bs(), "_ACCOUNTS", tmp_path / "no_accounts.json")
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)
    monkeypatch.setattr(notify, "SIGNAL_COPIES", tmp_path / "no_copies.json")
    notify._warned_kinds.clear()
    notify._warned_no_room.clear()
    notify._warned_unreadable.clear()
    notify._warned_copies.clear()
    for var in ("LWG_TELEGRAM_CHAT_ID", "LWG_TELEGRAM_HEALTH_CHAT", "LWG_TELEGRAM_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    yield
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)
    notify._warned_copies.clear()


def _creds(monkeypatch, **values):
    monkeypatch.setattr(creds_mod, "_cache", dict(values), raising=False)


def _accounts(monkeypatch, tmp_path, *rows):
    path = tmp_path / "accounts.json"
    path.write_text(json.dumps({"_README": "test", "accounts": list(rows)}), encoding="utf-8")
    monkeypatch.setattr(_bs(), "_ACCOUNTS", path)
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)


def _copies(monkeypatch, tmp_path, mapping, *, raw=None):
    path = tmp_path / "signal_copies.json"
    path.write_text(raw if raw is not None else json.dumps({"copies": mapping}), encoding="utf-8")
    monkeypatch.setattr(notify, "SIGNAL_COPIES", path)


class _FakeResponse:
    status_code = 200
    text = "{}"

    @staticmethod
    def json():
        return {"result": {"message_id": 7}}


def _spy(monkeypatch, *, fail_chats=()):
    """Record every post. `fail_chats` answers 500 for those chats and 200 for the rest."""
    posts: list = []

    class _Bad:
        status_code = 500
        text = "chat not found"

        @staticmethod
        def json():
            return {}

    class _Req:
        @staticmethod
        def post(url, json=None, timeout=None):
            posts.append(json)
            return _Bad() if json["chat_id"] in fail_chats else _FakeResponse()

    monkeypatch.setattr(notify, "_requests", _Req)
    return posts


def _live(account, **rooms):
    return {"account": account, "kind": "live", **rooms}


# ── what must NEVER be copied ────────────────────────────────────────────────────────────────


def test_a_FILL_is_never_copied_however_the_file_is_written(monkeypatch, tmp_path):
    """🔴 THE RULE. Somebody's fills reaching the other owner's room is the one mistake here that
    cannot be undone, so the kind is checked in the code and this file cannot ask for it.

    MUTATION: drop the `kind == SIGNAL` guard and this reddens.
    """
    _creds(monkeypatch, **_SHARED)
    _accounts(
        monkeypatch,
        tmp_path,
        _live(_HIS_LIVE, telegram_trade_chat="-100his_t", telegram_signal_chat="-100his_s"),
    )
    _copies(monkeypatch, tmp_path, {str(_HIS_LIVE): ["-100mine_s"]})
    posts = _spy(monkeypatch)
    notify.send_telegram("FILLED long 0.24L", notify.TRADE, account=_HIS_LIVE)
    assert [p["chat_id"] for p in posts] == ["-100his_t"]


def test_the_machinery_room_is_never_copied(monkeypatch, tmp_path):
    """Health is about the one box every account shares; it has no business in a second room."""
    _creds(monkeypatch, **_SHARED)
    _accounts(
        monkeypatch,
        tmp_path,
        _live(_HIS_LIVE, telegram_trade_chat="-100his_t", telegram_signal_chat="-100his_s"),
    )
    _copies(monkeypatch, tmp_path, {str(_HIS_LIVE): ["-100mine_s"]})
    posts = _spy(monkeypatch)
    notify.send_telegram("the bridge halted", notify.HEALTH, account=_HIS_LIVE)
    assert [p["chat_id"] for p in posts] == ["-100health"]


def test_an_account_nobody_asked_for_a_copy_of_posts_once(monkeypatch, tmp_path):
    """The copies file names one account; every other account must be untouched by it."""
    _creds(monkeypatch, **_SHARED)
    _accounts(
        monkeypatch,
        tmp_path,
        _live(_MY_LIVE, telegram_trade_chat="-100mine_t", telegram_signal_chat="-100mine_s"),
    )
    _copies(monkeypatch, tmp_path, {str(_HIS_LIVE): ["-100mine_s"]})
    posts = _spy(monkeypatch)
    notify.send_telegram("SETUP FORMING", notify.SIGNAL, account=_MY_LIVE)
    assert [p["chat_id"] for p in posts] == ["-100mine_s"]


# ── the copy itself ──────────────────────────────────────────────────────────────────────────


def test_a_setup_reaches_its_own_room_AND_the_copy_room(monkeypatch, tmp_path):
    """The ask, in one assertion: his setups in his room, and the same text in mine.

    MUTATION: remove the `_copy_signal` call from `send_telegram_id` and this reddens.
    """
    _creds(monkeypatch, **_SHARED)
    _accounts(
        monkeypatch,
        tmp_path,
        _live(_HIS_LIVE, telegram_trade_chat="-100his_t", telegram_signal_chat="-100his_s"),
    )
    _copies(monkeypatch, tmp_path, {str(_HIS_LIVE): ["-100mine_s"]})
    posts = _spy(monkeypatch)
    notify.send_telegram("SETUP FORMING 2 of 3", notify.SIGNAL, account=_HIS_LIVE)
    assert [p["chat_id"] for p in posts] == ["-100his_s", "-100mine_s"]
    assert {p["text"] for p in posts} == {"SETUP FORMING 2 of 3"}


def test_the_copy_is_flat_and_carries_no_reply_id(monkeypatch, tmp_path):
    """A message id belongs to the chat it was posted in. Replaying his thread id in my room
    would either be refused or file the follow-up under a stranger's message."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _live(_HIS_LIVE, telegram_signal_chat="-100his_s"))
    _copies(monkeypatch, tmp_path, {str(_HIS_LIVE): ["-100mine_s"]})
    posts = _spy(monkeypatch)
    notify.send_telegram(
        "BLOCKED by the final hour", notify.SIGNAL, account=_HIS_LIVE, reply_to=4242
    )
    assert posts[0]["reply_to_message_id"] == 4242
    assert "reply_to_message_id" not in posts[1]


def test_a_copy_room_that_is_already_the_primary_is_not_posted_twice(monkeypatch, tmp_path):
    """Both owners reading one room is a legitimate way to configure this, and it must not
    double every setup in it."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _live(_HIS_LIVE, telegram_signal_chat="-100his_s"))
    _copies(monkeypatch, tmp_path, {str(_HIS_LIVE): ["-100his_s", "-100mine_s", "-100mine_s"]})
    posts = _spy(monkeypatch)
    notify.send_telegram("SETUP FORMING", notify.SIGNAL, account=_HIS_LIVE)
    assert [p["chat_id"] for p in posts] == ["-100his_s", "-100mine_s"]


def test_a_broken_copy_room_does_not_cost_the_real_message_or_its_thread(monkeypatch, tmp_path):
    """The copy is a courtesy. If my room is gone, his bot must still report normally and still
    return the id its follow-ups reply to — and say what happened, once.

    MUTATION: let `_copy_signal` raise instead of printing and this reddens.
    """
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _live(_HIS_LIVE, telegram_signal_chat="-100his_s"))
    _copies(monkeypatch, tmp_path, {str(_HIS_LIVE): ["-100gone"]})
    _spy(monkeypatch, fail_chats={"-100gone"})
    for _ in range(3):
        assert notify.send_telegram_id("SETUP FORMING", notify.SIGNAL, account=_HIS_LIVE) == 7


def test_a_broken_copy_room_says_so_ONCE(monkeypatch, tmp_path, capsys):
    """A bot sends setups on a bar loop; a line per message is a log nobody can read."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _live(_HIS_LIVE, telegram_signal_chat="-100his_s"))
    _copies(monkeypatch, tmp_path, {str(_HIS_LIVE): ["-100gone"]})
    _spy(monkeypatch, fail_chats={"-100gone"})
    for _ in range(3):
        notify.send_telegram("SETUP FORMING", notify.SIGNAL, account=_HIS_LIVE)
    assert capsys.readouterr().out.count("-100gone") == 1


def test_a_live_setup_with_no_room_of_its_own_is_not_copied_either(monkeypatch, tmp_path):
    """The refusal comes first. A live account that names no signals room sends nothing, and a
    copy destination must not become a way round that."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _live(_HIS_LIVE))
    _copies(monkeypatch, tmp_path, {str(_HIS_LIVE): ["-100mine_s"]})
    posts = _spy(monkeypatch)
    assert notify.send_telegram("SETUP FORMING", notify.SIGNAL, account=_HIS_LIVE) is False
    assert posts == []


# ── the file itself ──────────────────────────────────────────────────────────────────────────


def test_no_copies_file_at_all_is_the_ordinary_state(monkeypatch, tmp_path, capsys):
    """A box where nobody wants a copy must be silent about it — no warning, no copy."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _live(_HIS_LIVE, telegram_signal_chat="-100his_s"))
    posts = _spy(monkeypatch)
    notify.send_telegram("SETUP FORMING", notify.SIGNAL, account=_HIS_LIVE)
    assert [p["chat_id"] for p in posts] == ["-100his_s"]
    assert "copies" not in capsys.readouterr().out


def test_an_unreadable_copies_file_still_delivers_and_SAYS_so_once(monkeypatch, tmp_path, capsys):
    """Half-written or hand-broken JSON. The distinction between *nobody asked* and *could not
    ask* is reported rather than returned — the message has already gone either way."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _live(_HIS_LIVE, telegram_signal_chat="-100his_s"))
    _copies(monkeypatch, tmp_path, {}, raw='{"copies": {"349579')
    posts = _spy(monkeypatch)
    for _ in range(3):
        notify.send_telegram("SETUP FORMING", notify.SIGNAL, account=_HIS_LIVE)
    assert [p["chat_id"] for p in posts] == ["-100his_s"] * 3
    assert capsys.readouterr().out.count("could not be read") == 1


def test_one_room_may_be_written_as_a_bare_string(monkeypatch, tmp_path):
    """A person edits this file by hand, and `"-100mine_s"` is what they will write."""
    _creds(monkeypatch, **_SHARED)
    _accounts(monkeypatch, tmp_path, _live(_HIS_LIVE, telegram_signal_chat="-100his_s"))
    _copies(monkeypatch, tmp_path, {str(_HIS_LIVE): "-100mine_s"})
    posts = _spy(monkeypatch)
    notify.send_telegram("SETUP FORMING", notify.SIGNAL, account=_HIS_LIVE)
    assert [p["chat_id"] for p in posts] == ["-100his_s", "-100mine_s"]


def test_the_COMMITTED_file_names_real_accounts_and_no_trades_room():
    """A guard on the real file, because this one is edited by hand.

    Two ways a typo here would be quiet: a copy under an account number nothing runs on would
    simply never fire, and an id that is some account's TRADES room would put setups in a room
    reserved for fills — which is the one direction the routing rules exist to protect.
    """
    fx = _ALGOS / "markets" / "fx"
    copies = json.loads((fx / "signal_copies.json").read_text(encoding="utf-8"))["copies"]
    rows = json.loads((fx / "accounts.json").read_text(encoding="utf-8"))["accounts"]
    known = {str(r["account"]) for r in rows if isinstance(r, dict)}
    trade_rooms = {
        str(r.get("telegram_trade_chat") or "").strip()
        for r in rows
        if isinstance(r, dict) and str(r.get("telegram_trade_chat") or "").strip()
    }
    for account, rooms in copies.items():
        assert account in known, f"{account} is not an account in accounts.json"
        for room in [rooms] if isinstance(rooms, str) else rooms:
            assert room not in trade_rooms, f"{room} is an account's TRADES room"
