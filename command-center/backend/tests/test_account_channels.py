"""A live account names ITS OWN Telegram channels, and nothing puts a bot on one that does not.

**Aaron's rule, 2026-09-13, the day a second person's live account joined the box.** Two owners,
two lots of real money, and neither may read the other's fills — so a room is a property of the
ACCOUNT, and a live account with no trades or signals channel takes no bot. The bot enforces the
same rule at startup (`algos/live/runner.py`, `algos/tests/test_live_rooms_runner.py`); this file
covers the four doors in THIS app that could put a bot there anyway, plus where this app's own
alerts land.

⚠ **A fail-watch against HEAD is vacuous for every case here** — none of these fields existed — so
non-vacuity is by MUTATION (`python3 -m scripts.testing.mutate`), named in each docstring.

🔴 **The case these are weighted toward is the one that cannot be undone**: a bot trading real
money with nowhere to report it, discovered when a fill does not arrive. Every other failure here
is a message in the wrong place that somebody can see and correct.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from routers import bots as r  # noqa: E402
from services import bot_account_registry as reg  # noqa: E402

_LIVE = 35710389
_DEMO = 700152905
_TRADE_ID = "-1004410831757"
_SIGNAL_ID = "-1003332727688"


def _acct(**kw):
    base = dict(
        account=_LIVE,
        kind="live",
        broker="PU Prime",
        server="PUPrime-Live",
        mt5_path=r"C:\MT5_Live\terminal64.exe",
        symbol_suffix=".p",
        account_profile="puprime_ecn",
        telegram_trade_chat=_TRADE_ID,
        telegram_signal_chat=_SIGNAL_ID,
    )
    base.update(kw)
    return reg.RegisteredAccount(**base)


# ── what an account OWES ──────────────────────────────────────────────────────


def test_a_configured_live_account_owes_NOTHING():
    """The CONTROL, and without it every case below passes for a rule that refuses everything."""
    assert _acct().missing_channels == []
    assert _acct().channels_reason == ""


def test_a_live_account_with_neither_channel_owes_BOTH_in_a_fixed_order():
    """A set comes back in whatever order it feels like, and this list is rendered straight into a
    refusal a person acts on — two readings of one problem look like two problems.
    MUTATION: build the list from a set → red."""
    a = _acct(telegram_trade_chat="", telegram_signal_chat="")
    assert a.missing_channels == ["trades", "signals"]
    assert "trades and signals" in a.channels_reason


def test_each_channel_is_owed_SEPARATELY():
    assert _acct(telegram_trade_chat="").missing_channels == ["trades"]
    assert _acct(telegram_signal_chat="").missing_channels == ["signals"]


def test_HEALTH_is_never_owed():
    """🔴 A DECISION, not an omission. Most of health is about the one box every account shares,
    so it falls back to the shared room — requiring it would stop a bot starting over a channel
    that is meant to be shared. MUTATION: add health to the owed list → red."""
    assert _acct(telegram_health_chat="").missing_channels == []


def test_a_DEMO_account_owes_NOTHING_whatever_it_names():
    """Gating demo would take the demo fleet down over a field never required of it.
    MUTATION: drop the kind check → red."""
    a = _acct(kind="demo", telegram_trade_chat="", telegram_signal_chat="")
    assert a.missing_channels == []
    assert a.channels_reason == ""


def test_WHITESPACE_is_not_a_channel():
    """A space survives a form, a copy-paste and a JSON round trip, and looks configured in every
    listing. MUTATION: test the raw value instead of the stripped one → red."""
    assert _acct(telegram_trade_chat="   ").missing_channels == ["trades"]


def test_the_refusal_names_the_ACCOUNT_and_the_WORK():
    """It is read by somebody who has to act on it — so it says which account and what to do."""
    reason = _acct(telegram_trade_chat="", telegram_signal_chat="").channels_reason
    assert str(_LIVE) in reason
    assert "refuse to start" in reason
    assert "Enter the channel" in reason


def test_the_two_refusals_stay_SEPARATE_sentences():
    """A missing terminal and a missing channel need different work — logging a terminal in, or
    entering a channel. One merged message sends the reader to do one of them."""
    a = _acct(mt5_path="", telegram_trade_chat="", telegram_signal_chat="")
    assert a.channels_reason and a.unassignable_reason
    assert a.channels_reason != a.unassignable_reason


# ── a chat id that Telegram could never resolve ───────────────────────────────


@pytest.mark.parametrize(
    "field", ["telegram_trade_chat", "telegram_signal_chat", "telegram_health_chat"]
)
def test_a_value_that_is_not_a_chat_id_is_REFUSED_on_every_channel(tmp_path, field):
    """🔴 A wrong id fails at the moment a real fill is sent, which is the one moment nobody is
    reading the log — so it is refused when it is typed, not when it matters.
    MUTATION: check only the trade field → the other two go red."""
    with pytest.raises(reg.RegistryError, match="not a Telegram channel"):
        reg.check_entry(tmp_path / "accounts.json", _acct(**{field: "my channel"}), None)


def test_the_REAL_shapes_of_a_chat_id_are_accepted(tmp_path):
    """The control. A rule that refused a real id would be discovered by a person who could not
    save the channel they had just been given."""
    for value in (_TRADE_ID, "@lwg_live_trades", "-1003332727688"):
        reg.check_entry(tmp_path / "accounts.json", _acct(telegram_trade_chat=value), None)


def test_an_EMPTY_channel_is_not_a_bad_one(tmp_path):
    """Empty is how a row is saved before its owner has entered them — refused later, by the rules
    above, and only once a bot is actually on it."""
    reg.check_entry(
        tmp_path / "accounts.json",
        _acct(telegram_trade_chat="", telegram_signal_chat="", telegram_health_chat=""),
        None,
    )


def test_the_channels_SURVIVE_a_write_and_a_read(tmp_path):
    """A field that validates and then does not persist is the same defect as no field at all.
    MUTATION: drop one of the three from the serialiser → red."""
    path = tmp_path / "accounts.json"
    path.write_text('{"accounts": []}', encoding="utf-8")
    reg.upsert_account(path, _acct(telegram_health_chat="@lwg_health"), None)
    back = reg.account_by_number(path, _LIVE)
    assert back.telegram_trade_chat == _TRADE_ID
    assert back.telegram_signal_chat == _SIGNAL_ID
    assert back.telegram_health_chat == "@lwg_health"


# ── door 1: moving ONE bot onto the account ───────────────────────────────────


def _stub_move(monkeypatch, entry):
    monkeypatch.setattr(r, "_bot_running_state", lambda key: False)
    monkeypatch.setattr(r, "_holds_position", lambda key: False)
    monkeypatch.setattr(r, "_accounts_with_a_password", lambda: {entry.account})
    monkeypatch.setattr(r, "_account_groups", lambda: [])
    monkeypatch.setattr(r.bot_account_registry, "account_by_number", lambda path, n: entry)
    written = {}
    monkeypatch.setattr(r, "_write_instance_config", lambda k, d: written.__setitem__(k, d))
    return written


def test_a_bot_may_NOT_be_moved_onto_a_live_account_with_no_channels(client, monkeypatch):
    """🔴 Without this the move commits, pushes, pulls — and produces a bot that refuses to start.
    MUTATION: delete the `channels_reason` check from `set_bot_account` → red."""
    written = _stub_move(monkeypatch, _acct(telegram_trade_chat="", telegram_signal_chat=""))
    got = client.patch(
        "/bots/b_leg_demo/account",
        json={"account": _LIVE, "confirm_live": True, "deploy": False},
    )
    assert got.status_code == 409, got.text
    assert "no trades and signals channel" in got.json()["detail"]
    assert written == {}, "nothing may be written by a refused move"


def test_a_bot_MAY_be_moved_onto_a_live_account_that_names_them(client, monkeypatch):
    """The control: the same path, on a configured account, goes through."""
    written = _stub_move(monkeypatch, _acct())
    got = client.patch(
        "/bots/b_leg_demo/account",
        json={"account": _LIVE, "confirm_live": True, "deploy": False},
    )
    assert got.status_code == 200, got.text
    assert list(written) == ["b_leg_demo"]


def test_a_DEMO_account_with_no_channels_still_takes_a_bot(client, monkeypatch):
    """The demo fleet has never named a channel and must keep working."""
    written = _stub_move(
        monkeypatch,
        _acct(account=_DEMO, kind="demo", telegram_trade_chat="", telegram_signal_chat=""),
    )
    got = client.patch("/bots/b_leg_demo/account", json={"account": _DEMO, "deploy": False})
    assert got.status_code == 200, got.text
    assert list(written) == ["b_leg_demo"]


# ── door 2: clearing the channels while bots are already there ────────────────


def _stub_registry_write(monkeypatch, *, bot_keys=()):
    saved = {}
    group = SimpleNamespace(
        kind="account",
        account=_LIVE,
        bots=[SimpleNamespace(key=k) for k in bot_keys],
    )
    monkeypatch.setattr(r, "_account_groups", lambda: [group])
    monkeypatch.setattr(r, "_known_profiles", lambda: {"puprime_ecn"})
    monkeypatch.setattr(r, "_accounts_with_a_password", lambda: set())
    monkeypatch.setattr(r.bot_account_registry, "check_entry", lambda *a, **k: None)

    def _upsert(path, entry, profiles):
        saved["entry"] = entry
        return entry, True

    monkeypatch.setattr(r.bot_account_registry, "upsert_account", _upsert)
    return saved


def _write_body(**kw):
    body = dict(
        account=_LIVE,
        kind="live",
        server="PUPrime-Live",
        mt5_path=r"C:\MT5_Live\terminal64.exe",
        symbol_suffix=".p",
        account_profile="puprime_ecn",
        telegram_trade_chat=_TRADE_ID,
        telegram_signal_chat=_SIGNAL_ID,
        deploy=False,
    )
    body.update(kw)
    return body


def test_the_channels_may_NOT_be_cleared_while_bots_trade_the_account(client, monkeypatch):
    """🔴 The second door to the same room, and the quieter one: the bots keep running and simply
    stop reporting, then refuse to start the next time anything restarts them.
    MUTATION: delete the `bots_here and entry.missing_channels` check → red."""
    saved = _stub_registry_write(monkeypatch, bot_keys=("sos_fade_demo", "extreme_leg_demo"))
    got = client.put(
        f"/bots/accounts/registry/{_LIVE}",
        json=_write_body(telegram_trade_chat="", telegram_signal_chat=""),
    )
    assert got.status_code == 409, got.text
    detail = got.json()["detail"]
    assert "extreme_leg_demo, sos_fade_demo" in detail
    assert "trades and signals" in detail
    assert saved == {}, "a refused save may not reach the registry"


def test_an_account_with_NO_bots_on_it_may_be_saved_with_no_channels(client, monkeypatch):
    """🔴 It refuses the STATE, not the change. This is how a row gets created before its owner
    has been asked for a channel — refusing it would make a new live account unregisterable.
    MUTATION: drop `bots_here` from the condition → red."""
    _stub_registry_write(monkeypatch, bot_keys=())
    got = client.put(
        f"/bots/accounts/registry/{_LIVE}",
        json=_write_body(telegram_trade_chat="", telegram_signal_chat=""),
    )
    assert got.status_code == 200, got.text


def test_the_channels_ARE_carried_into_the_stored_row(client, monkeypatch):
    """A field the endpoint accepts and drops is worse than one it rejects.
    MUTATION: stop passing the three fields into `RegisteredAccount` → red."""
    seen = {}
    monkeypatch.setattr(r, "_account_groups", lambda: [])
    monkeypatch.setattr(r, "_known_profiles", lambda: {"puprime_ecn"})
    monkeypatch.setattr(r, "_accounts_with_a_password", lambda: set())
    monkeypatch.setattr(r.bot_account_registry, "check_entry", lambda *a, **k: None)

    def _upsert(path, entry, profiles):
        seen["entry"] = entry
        return entry, True

    monkeypatch.setattr(r.bot_account_registry, "upsert_account", _upsert)
    got = client.put(
        f"/bots/accounts/registry/{_LIVE}", json=_write_body(telegram_health_chat="@lwg_health")
    )
    assert got.status_code == 200, got.text
    assert seen["entry"].telegram_trade_chat == _TRADE_ID
    assert seen["entry"].telegram_signal_chat == _SIGNAL_ID
    assert seen["entry"].telegram_health_chat == "@lwg_health"
    body = got.json()
    assert body["telegram_trade_chat"] == _TRADE_ID
    assert body["missing_channels"] == []
    assert body["channels_reason"] == ""


def test_the_page_is_TOLD_what_an_account_still_owes(client, monkeypatch):
    """The refusals above are the backstop; this is what lets the page say so before anyone tries.
    MUTATION: stop serving `missing_channels` / `channels_reason` → red."""
    monkeypatch.setattr(r, "_account_groups", lambda: [])
    monkeypatch.setattr(r, "_known_profiles", lambda: {"puprime_ecn"})
    monkeypatch.setattr(r, "_accounts_with_a_password", lambda: set())
    monkeypatch.setattr(r.bot_account_registry, "check_entry", lambda *a, **k: None)
    monkeypatch.setattr(
        r.bot_account_registry, "upsert_account", lambda path, entry, profiles: (entry, True)
    )
    got = client.put(
        f"/bots/accounts/registry/{_LIVE}",
        json=_write_body(telegram_trade_chat="", telegram_signal_chat=""),
    )
    assert got.status_code == 200, got.text
    assert got.json()["missing_channels"] == ["trades", "signals"]
    assert "refuse to start" in got.json()["channels_reason"]


# ── door 3: taking a whole proven set live ────────────────────────────────────
#
# Tested in `test_go_live.py`, beside the rest of that planner and its fixtures — see
# `test_a_set_may_NOT_go_live_onto_an_account_with_no_channels` there. Duplicating its world
# here would be a second, thinner copy of the same setup, and the thin one goes stale first.


# ── where THIS app's own alerts land ──────────────────────────────────────────


def test_an_alert_about_a_bot_goes_to_ITS_ACCOUNTS_health_channel(monkeypatch):
    """🔴 The deploy THREAD is why this matters rather than being a nicety: a promote's root is
    sent from here and the bot's two replies come from the box, and a reply only threads inside
    one chat. A root in the shared room while the bot answers in its own channel is a thread that
    silently stops working. MUTATION: drop `chat_id=` from `_notify_telegram` → red."""
    monkeypatch.setattr(r, "_read_instance_config", lambda key: {"account": _LIVE})
    monkeypatch.setattr(
        r.bot_account_registry,
        "account_by_number",
        lambda path, n: _acct(telegram_health_chat="@lwg_health") if n == _LIVE else None,
    )
    sent = []
    monkeypatch.setattr(r, "send_telegram_id", lambda text, kind, chat_id="": sent.append(chat_id))
    r._notify_telegram("PROMOTED", bot_key="sos_fade_demo")
    assert sent == ["@lwg_health"]


def test_an_alert_about_an_ACCOUNT_needs_no_bot_to_route_it(monkeypatch):
    """The risk-cap and go-live alerts know the account and not one bot."""
    monkeypatch.setattr(
        r.bot_account_registry,
        "account_by_number",
        lambda path, n: _acct(telegram_health_chat="@lwg_health"),
    )
    sent = []
    monkeypatch.setattr(r, "send_telegram_id", lambda text, kind, chat_id="": sent.append(chat_id))
    r._notify_telegram("GONE LIVE", account=_LIVE)
    assert sent == ["@lwg_health"]


def test_an_alert_about_the_BOX_keeps_the_shared_room(monkeypatch):
    """🔴 A DECISION. The fleet stop is about the machine every account shares, so it names no
    account and falls back — which is where every one of these went before this existed.
    MUTATION: default the account to anything → red."""
    sent = []
    monkeypatch.setattr(r, "send_telegram_id", lambda text, kind, chat_id="": sent.append(chat_id))
    r._notify_telegram("All bots STOPPED")
    assert sent == [""]


def test_an_account_naming_no_health_channel_falls_back_to_the_shared_room(monkeypatch):
    """Health is optional by decision, so an account that names none is not an error."""
    monkeypatch.setattr(r, "_read_instance_config", lambda key: {"account": _LIVE})
    monkeypatch.setattr(
        r.bot_account_registry, "account_by_number", lambda path, n: _acct(telegram_health_chat="")
    )
    sent = []
    monkeypatch.setattr(r, "send_telegram_id", lambda text, kind, chat_id="": sent.append(chat_id))
    r._notify_telegram("STARTING", bot_key="sos_fade_demo")
    assert sent == [""]


def test_the_ROUTING_can_never_break_an_alert(monkeypatch):
    """⚠ This sits on the path of an alert, and several of those alerts are about something having
    gone wrong. A message that fails over its own routing is worse than one in the wrong room.
    MUTATION: let `_account_health_chat` raise → red."""

    def boom(*_a, **_k):
        raise RuntimeError("registry on fire")

    monkeypatch.setattr(r, "_read_instance_config", boom)
    monkeypatch.setattr(r.bot_account_registry, "account_by_number", boom)
    sent = []
    monkeypatch.setattr(r, "send_telegram_id", lambda text, kind, chat_id="": sent.append(chat_id))
    r._notify_telegram("HALTED", bot_key="sos_fade_demo")
    assert sent == [""], "it must still send, into the shared room"


def test_every_send_from_this_backend_is_still_HEALTH(monkeypatch):
    """⚠ The standing rule this app has had since 2026-08-05: only the bot on the box knows a fill
    happened, so this backend can never legitimately send a TRADE. The new routing must not have
    opened a way to."""
    monkeypatch.setattr(r, "_read_instance_config", lambda key: None)
    kinds = []
    monkeypatch.setattr(r, "send_telegram_id", lambda text, kind, chat_id="": kinds.append(kind))
    r._notify_telegram("anything", bot_key="sos_fade_demo")
    assert kinds == [r.notify.HEALTH]


# ── the check that proves a channel actually works ────────────────────────────


class _Ran:
    """A fake `ssh` run. Records the command so the argv can be asserted, not just the verdict."""

    def __init__(self, code, out=b"", err=b""):
        self.code, self.out, self.err = code, out, err
        self.cmds = []

    def __call__(self, argv, **_kw):
        self.cmds.append(argv[-1])
        return SimpleNamespace(returncode=self.code, stdout=self.out, stderr=self.err)


def _fake_ssh(monkeypatch, ran):
    monkeypatch.setattr(r.vps_ssh, "run", ran)
    return ran


def test_a_channel_that_ACCEPTS_the_message_reads_as_working(client, monkeypatch):
    """The control, and the case a person presses the button for."""
    _fake_ssh(monkeypatch, _Ran(0, b"OK: posted to -1004410831757 as message 44."))
    got = client.post(
        f"/bots/accounts/registry/{_LIVE}/test-channel",
        json={"kind": "trade", "chat_id": _TRADE_ID},
    )
    assert got.status_code == 200, got.text
    assert got.json()["ok"] is True
    assert "message 44" in got.json()["detail"]


def test_a_channel_Telegram_REFUSES_reads_as_broken(client, monkeypatch):
    """🔴 The whole reason this button exists: a chat id one digit wrong, or one the bot has not
    been added to, otherwise fails at the moment a real fill is sent.
    MUTATION: return `ok=True` regardless of the code → red."""
    _fake_ssh(monkeypatch, _Ran(1, b"FAIL: could not post to -100999. chat not found"))
    got = client.post(
        f"/bots/accounts/registry/{_LIVE}/test-channel",
        json={"kind": "trade", "chat_id": "-1009999999999"},
    )
    assert got.status_code == 200, got.text
    assert got.json()["ok"] is False
    assert "chat not found" in got.json()["detail"], "Telegram's own reason must survive"


def test_the_verdict_is_the_EXIT_CODE_and_never_the_text(client, monkeypatch):
    """🔴 The output is written for a person and its wording is free to change; the exit code is
    what the program decided. A backend that read the word OK out of prose would be making a claim
    about a string. MUTATION: decide `ok` by `detail.startswith("OK")` → red."""
    _fake_ssh(monkeypatch, _Ran(4, b"OK is a word that appears in this line"))
    got = client.post(f"/bots/accounts/registry/{_LIVE}/test-channel", json={"kind": "signal"})
    assert got.json()["ok"] is False


def test_a_SILENT_failure_still_says_something(client, monkeypatch):
    """A blank panel beside a red tick is the shape this repo keeps paying for."""
    _fake_ssh(monkeypatch, _Ran(3, b""))
    got = client.post(f"/bots/accounts/registry/{_LIVE}/test-channel", json={"kind": "trade"})
    assert got.json()["ok"] is False
    assert got.json()["detail"].strip()


def test_a_DEAD_SSH_is_not_reported_as_a_dead_channel(client, monkeypatch):
    """🔴 The distinction this repo is built on: *the channel does not work* and *we never got an
    answer* are different facts, and blaming the channel for a dead tunnel sends somebody to
    re-enter an id that was always right. MUTATION: report 255-with-no-output as `ok=False` → red.
    """
    _fake_ssh(monkeypatch, _Ran(255, b"", b"ssh: connect to host forexvps port 22: timed out"))
    got = client.post(f"/bots/accounts/registry/{_LIVE}/test-channel", json={"kind": "trade"})
    assert got.status_code == 502, got.text
    assert "connect to host" in got.json()["detail"]


def test_a_TYPED_id_is_tested_instead_of_the_saved_one(client, monkeypatch):
    """The button beside the field has to check what is in the field, before it is saved — that is
    the whole point of testing before you commit a bot to the account."""
    ran = _fake_ssh(monkeypatch, _Ran(0, b"OK: posted"))
    client.post(
        f"/bots/accounts/registry/{_LIVE}/test-channel",
        json={"kind": "signal", "chat_id": _SIGNAL_ID},
    )
    assert f'--chat-id="{_SIGNAL_ID}"' in ran.cmds[0]
    assert "--kind signal" in ran.cmds[0]


def test_an_id_beginning_with_a_MINUS_is_not_read_as_a_flag(client, monkeypatch):
    """⚠ Every real channel id starts with `-`. `--chat-id -100…` is read by argparse as a flag
    unless the value is all digits, so an `@name` or any future shape would fail to parse and the
    channel would report as dead. MUTATION: pass the id after a space → red on the shape below."""
    ran = _fake_ssh(monkeypatch, _Ran(0, b"OK: posted"))
    client.post(
        f"/bots/accounts/registry/{_LIVE}/test-channel",
        json={"kind": "trade", "chat_id": "@lwg_live_trades"},
    )
    assert '--chat-id="@lwg_live_trades"' in ran.cmds[0]
    assert "--chat-id @" not in ran.cmds[0]


def test_NO_typed_id_tests_what_the_BOX_already_has(client, monkeypatch):
    """The other half, and the one that answers "can a live bot report from here" — it reads the
    registry as the box has it, which is only what this page shows once the write is deployed."""
    ran = _fake_ssh(monkeypatch, _Ran(0, b"OK: posted"))
    client.post(f"/bots/accounts/registry/{_LIVE}/test-channel", json={"kind": "trade"})
    assert f"--account {_LIVE}" in ran.cmds[0]
    assert "--chat-id" not in ran.cmds[0]


def test_the_check_RUNS_ON_THE_BOX_and_drives_the_real_tool(client, monkeypatch):
    """🔴 Rule 7: the tick on the page is a claim about code somewhere else. The token lives only
    in the box's credentials file, so a message sent from this laptop would be testing a DIFFERENT
    sender from the one that carries the fills. MUTATION: send from here instead → red."""
    ran = _fake_ssh(monkeypatch, _Ran(0, b"OK: posted"))
    client.post(f"/bots/accounts/registry/{_LIVE}/test-channel", json={"kind": "health"})
    cmd = ran.cmds[0]
    assert "algos/tools/verify_channel.py" in cmd
    assert cmd.startswith(f"cd {r._VPS_REPO}")


def test_the_tool_it_drives_EXISTS(monkeypatch):
    """⚠ The path is a string in a command line, so nothing else here would notice it moving.
    A renamed tool would report every channel as dead, from the box, with no local symptom."""
    tool = Path(r.cfg.MONOREPO_ROOT) / r._VERIFY_CHANNEL
    assert tool.is_file(), f"{tool} — the channel check points at a tool that is not there"


def test_an_UNKNOWN_kind_is_refused_before_it_reaches_the_box(client, monkeypatch):
    """A kind nothing routes would be a message sent into the shared room by a check whose whole
    job is to prove a message did NOT go there."""
    ran = _fake_ssh(monkeypatch, _Ran(0, b"OK: posted"))
    got = client.post(f"/bots/accounts/registry/{_LIVE}/test-channel", json={"kind": "everything"})
    assert got.status_code == 422, got.text
    assert ran.cmds == [], "nothing may reach the box on a refused request"


# ── every alert says what it is ABOUT ─────────────────────────────────────────


def test_every_alert_names_its_bot_or_account_except_the_FLEET_ones():
    """⚠ Built to SCALE, which is the part a per-route test cannot do: the next route somebody
    adds with a `_notify_telegram(...)` and no routing lands in the shared room, and nothing
    behavioural would notice until a message reached the wrong owner. This reads the router and
    refuses any call that names neither, other than the three that are about the whole box.

    The behavioural halves live beside each route's own tests (`test_bot_label.py`,
    `test_bot_promote.py`, `test_account_risk.py`, `test_go_live.py`).
    MUTATION: drop `bot_key=bot_key` from any one per-bot call → red, naming its line.
    """
    import ast

    src = (Path(r.__file__)).read_text(encoding="utf-8")
    tree = ast.parse(src)
    unrouted, fleet = [], 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_notify_telegram"):
            continue
        if {k.arg for k in node.keywords} & {"bot_key", "account"}:
            continue
        if "All bots" in ast.get_source_segment(src, node):
            fleet += 1
            continue
        unrouted.append(node.lineno)
    assert unrouted == [], f"alerts naming no bot or account at routers/bots.py lines {unrouted}"
    # The control: the fleet exemption is not quietly swallowing everything.
    assert fleet == 3, f"expected the three All-bots alerts (start, stop, restart); saw {fleet}"
