"""Adding one Telegram user must never remove the others.

Every write here replaces the WHOLE file from a dict this process assembled, so the read in
front of it is load-bearing: if the read is wrong, the write is a delete. `_read_users_vps`
used to answer `{}` for a missing file, an unreadable one, a locked one, a corrupt one and a
dead SSH alike — and `add_user` then wrote a users.json containing only the new user.

Remove and role-change survived that by accident (an empty dict 404s before it can write).
Add is the destructive one, and it is the one somebody runs while onboarding a person, which
is the moment nobody is looking at the existing list.

The tests below are organised around the three things the file can be — absent, present,
unreadable — because collapsing any two of them is the bug.
"""

import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routers import bots
from models import TelegramUserCreate, TelegramUserRoleUpdate


EXISTING = {
    "111": {"name": "Aaron", "role": "admin",  "added": "2026-01-01"},
    "222": {"name": "Brother", "role": "readonly", "added": "2026-02-02"},
}


@pytest.fixture
def vps(monkeypatch):
    """Script the far end: what the read returns, and capture what the write sends."""
    state = {"read": json.dumps({"users": EXISTING}), "written": None, "write_ok": True}

    def fake_ssh(cmd: str) -> str:
        if "sys.stdout.write" in cmd:                 # the read one-liner
            return state["read"]
        if "base64" in cmd:                           # the write one-liner
            b64 = cmd.split("b64decode(b'")[1].split("'")[0]
            import base64 as _b64
            state["written"] = json.loads(_b64.b64decode(b64).decode())["users"]
            return bots._USERS_WRITTEN if state["write_ok"] else ""
        return ""

    monkeypatch.setattr(bots, "_ssh", fake_ssh)
    return state


# ── The file is absent — the genuine first-user path ──────────────────────────

def test_absent_file_reads_as_no_users(vps):
    vps["read"] = bots._USERS_ABSENT
    assert bots._read_users_vps() == {}


def test_the_first_user_can_be_added_to_an_absent_file(vps):
    vps["read"] = bots._USERS_ABSENT
    bots.add_user(TelegramUserCreate(chat_id="999", name="New", role="readonly"))
    assert set(vps["written"]) == {"999"}


# ── The file is unreadable — the case that used to delete everyone ────────────

@pytest.mark.parametrize("answer", ["", "not json at all", "{}", '{"users": "oops"}'])
def test_an_unreadable_file_refuses_to_be_read_as_empty(vps, answer):
    vps["read"] = answer
    with pytest.raises(bots.UsersFileUnreadable):
        bots._read_users_vps()


@pytest.mark.parametrize("answer", ["", "not json at all", '{"users": null}'])
def test_adding_a_user_over_an_unreadable_file_writes_nothing(vps, answer):
    vps["read"] = answer
    with pytest.raises(HTTPException) as e:
        bots.add_user(TelegramUserCreate(chat_id="999", name="New", role="readonly"))
    assert e.value.status_code == 502
    assert vps["written"] is None, "it wrote a users.json built on a failed read"


def test_a_dead_ssh_does_not_empty_the_file(vps, monkeypatch):
    def dead(_cmd: str) -> str:
        raise bots.VpsUnreachable("ssh: connect to host forexvps port 22: timed out")

    monkeypatch.setattr(bots, "_ssh", dead)
    with pytest.raises(HTTPException) as e:
        bots.add_user(TelegramUserCreate(chat_id="999", name="New", role="readonly"))
    assert e.value.status_code == 502
    assert vps["written"] is None


def test_listing_users_reports_the_failure_instead_of_an_empty_list(vps):
    """An empty list reads as "nobody has access", which is a different fact and would send
    somebody to re-add users that are already there."""
    vps["read"] = "not json at all"
    with pytest.raises(HTTPException) as e:
        bots.list_users()
    assert e.value.status_code == 502


# ── The file is present — the ordinary path still works ──────────────────────

def test_a_legitimately_empty_users_object_is_not_an_error(vps):
    """Removing the last user writes `{"users": {}}`. That is a real state, not a failure —
    only a file we cannot parse is."""
    vps["read"] = json.dumps({"users": {}})
    assert bots._read_users_vps() == {}


def test_adding_a_user_keeps_the_existing_ones(vps):
    bots.add_user(TelegramUserCreate(chat_id="999", name="New", role="readonly"))
    assert set(vps["written"]) == {"111", "222", "999"}


def test_removing_a_user_keeps_the_others(vps):
    bots.remove_user("222")
    assert set(vps["written"]) == {"111"}


def test_a_role_change_touches_only_that_row(vps):
    bots.update_user_role("222", TelegramUserRoleUpdate(role="admin"))
    assert vps["written"]["222"]["role"] == "admin"
    assert vps["written"]["111"] == EXISTING["111"]


# ── The last admin ───────────────────────────────────────────────────────────
#
# `admin` is the only role carrying /stop, /restart, /emergency and /resume
# (algos/notifications/telegram_bot.py → ROLE_COMMANDS), so a users.json with no admin means
# nobody can stop a bot from Telegram. ⚠ The bot's ADMIN_CHAT fallback does NOT cover this —
# it only fires when the file is MISSING or unparseable, so a file listing everyone as
# readonly is read exactly as written and the primary admin loses the commands too.

def test_removing_the_last_admin_is_refused(vps):
    vps["read"] = json.dumps({"users": {"111": dict(EXISTING["111"])}})
    with pytest.raises(HTTPException) as e:
        bots.remove_user("111")
    assert e.value.status_code == 409
    assert vps["written"] is None


def test_demoting_the_last_admin_is_refused(vps):
    vps["read"] = json.dumps({"users": {"111": dict(EXISTING["111"])}})
    with pytest.raises(HTTPException) as e:
        bots.update_user_role("111", TelegramUserRoleUpdate(role="readonly"))
    assert e.value.status_code == 409
    assert vps["written"] is None


def test_removing_an_admin_is_fine_while_another_remains(vps):
    vps["read"] = json.dumps({"users": {
        "111": dict(EXISTING["111"]),
        "333": {"name": "Second", "role": "admin", "added": "2026-03-03"},
    }})
    bots.remove_user("111")
    assert set(vps["written"]) == {"333"}


def test_a_file_that_already_has_no_admin_is_not_frozen(vps):
    """The guard is about the CHANGE, not the state. Refusing every edit on a file that is
    already admin-less would leave no way to repair it from here."""
    vps["read"] = json.dumps({"users": {"222": dict(EXISTING["222"])}})
    bots.remove_user("222")
    assert vps["written"] == {}


def test_a_role_outside_the_known_set_is_refused():
    """Not a new role — a user with NO permissions, because ROLE_COMMANDS misses. `"Admin"`
    is the shape of that mistake and it looks completely fine on the page."""
    with pytest.raises(ValidationError):
        TelegramUserRoleUpdate(role="Admin")
    with pytest.raises(ValidationError):
        TelegramUserCreate(chat_id="9", name="X", role="owner")


# ── Two edits at once ────────────────────────────────────────────────────────

def test_concurrent_adds_do_not_lose_one(monkeypatch):
    """Every write replaces the whole file, so an overlapping pair means the second one's
    READ can predate the first one's WRITE — and the first user silently vanishes. FastAPI
    runs sync endpoints in a threadpool, so this is reachable, not theoretical.

    The read is deliberately made slow here: without the lock the interleaving happens every
    time, so this test fails loudly rather than flaking.
    """
    import threading
    import time

    store = {"users": dict(EXISTING)}

    def fake_ssh(cmd: str) -> str:
        if "sys.stdout.write" in cmd:
            # Snapshot FIRST, then sleep. A real read gets the file's contents at the moment
            # it reads them; taking the snapshot after the delay instead would quietly hand
            # every thread the latest state and this test would pass with no lock at all
            # (measured — it did, until this line moved).
            answer = json.dumps({"users": store["users"]})
            time.sleep(0.05)                      # widen the window
            return answer
        if "base64" in cmd:
            import base64 as _b64
            b64 = cmd.split("b64decode(b'")[1].split("'")[0]
            store["users"] = json.loads(_b64.b64decode(b64).decode())["users"]
            return bots._USERS_WRITTEN
        return ""

    monkeypatch.setattr(bots, "_ssh", fake_ssh)

    threads = [
        threading.Thread(target=bots.add_user,
                         args=(TelegramUserCreate(chat_id=cid, name=cid, role="readonly"),))
        for cid in ("901", "902", "903")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert set(store["users"]) == {"111", "222", "901", "902", "903"}


# ── The write itself ─────────────────────────────────────────────────────────

def test_an_unconfirmed_write_is_reported_as_a_failure(vps):
    """A remote Python traceback exits non-zero with empty stdout — which `_ssh` correctly
    does NOT read as a connection failure. Without the marker, that reports success."""
    vps["write_ok"] = False
    with pytest.raises(HTTPException) as e:
        bots.add_user(TelegramUserCreate(chat_id="999", name="New", role="readonly"))
    assert e.value.status_code == 502
    assert "not confirmed" in e.value.detail


def test_the_write_backs_the_file_up_first(vps, monkeypatch):
    sent: list[str] = []
    monkeypatch.setattr(bots, "_ssh", lambda c: (sent.append(c), bots._USERS_WRITTEN)[1])
    bots._write_users_vps(EXISTING)
    assert any("shutil.copy2" in c and ".bak" in c for c in sent), (
        "users.json is replaced wholesale — the .bak is the only copy of who had access"
    )
