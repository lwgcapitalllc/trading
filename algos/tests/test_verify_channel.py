"""`algos/tools/verify_channel.py` — proving a Telegram channel works before money depends on it.

**Why it exists.** An account's trades and signals channels are typed in by a person. A chat id
one digit wrong, or one the bot has not been added to, fails the way this whole design exists to
prevent: silently, at the moment a real fill arrives. The only honest check is to post to it.

**What these are weighted toward** is the set of ways a checking tool reports *fine* when it is
not — a tool that always fails passes every sad-path case beautifully, which this repo has already
shipped once (`check_tradingbox.py` certifying two tools that had never worked). So there is a
success CONTROL, and the three refusals are pinned apart by their own exit codes: *nothing to
test*, *nobody could read the registry*, and *Telegram said no* call for three different pieces of
work and must never render as one answer.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
for _p in (str(_ALGOS / "shared"), str(_ALGOS / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import credentials as creds_mod  # noqa: E402
import notify  # noqa: E402
import verify_channel as tool  # noqa: E402

_LIVE = 34957946


def _bs():
    """Resolved NOW, never bound at import: two other test modules pop `bot_state` out of
    `sys.modules`, and patching a stale copy leaves this reading the REAL account registry."""
    return importlib.import_module("bot_state")


@pytest.fixture
def box(monkeypatch, tmp_path):
    """A private registry, private credentials and a fake Telegram. Yields what was posted and a
    switch for making Telegram refuse."""
    reg = tmp_path / "accounts.json"
    reg.write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "account": _LIVE,
                        "kind": "live",
                        "telegram_trade_chat": "-1001111111111",
                        "telegram_signal_chat": "",
                    }
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
        {"telegram_token": "t", "telegram_chat_id": "-1002222222222"},
        raising=False,
    )
    notify._warned_no_room.clear()
    notify._warned_unreadable.clear()
    posted: list = []
    state = {"ok": True}

    class _Resp:
        text = '{"description":"chat not found"}'

        @property
        def status_code(self):
            return 200 if state["ok"] else 400

        @staticmethod
        def json():
            return {"result": {"message_id": 42}}

    class _Req:
        @staticmethod
        def post(url, json=None, timeout=None):
            posted.append(json)
            return _Resp()

    monkeypatch.setattr(notify, "_requests", _Req)
    yield type("Box", (), {"posted": posted, "state": state, "reg": reg})()
    monkeypatch.setattr(creds_mod, "_cache", None, raising=False)
    monkeypatch.setattr(_bs(), "_accounts_cache", None, raising=False)


def test_it_posts_to_the_id_it_was_HANDED(box):
    """THE CONTROL. Without it every refusal below passes for a tool that refuses everything.

    The id under test is one nothing has saved yet, which is the whole point: a person types it,
    proves it, and only then is it written anywhere."""
    assert tool.main(["--kind", "trade", "--chat-id", "-1009999999999"]) == 0
    assert [p["chat_id"] for p in box.posted] == ["-1009999999999"]


def test_the_typed_id_BEATS_the_saved_one(box):
    """A test of what is about to be entered, not of what is already there — otherwise the button
    beside an input box would confirm the OLD channel and read as approval of the new one."""
    rc = tool.main(["--kind", "trade", "--chat-id", "-1009999999999", "--account", str(_LIVE)])
    assert rc == 0
    assert box.posted[0]["chat_id"] == "-1009999999999"


def test_with_an_account_alone_it_posts_to_what_that_account_has_SAVED(box):
    """The other half: proving a live bot can actually report where its row says it will."""
    assert tool.main(["--kind", "trade", "--account", str(_LIVE)]) == 0
    assert box.posted[0]["chat_id"] == "-1001111111111"


def test_an_account_that_names_NO_channel_of_that_kind_is_its_own_answer(box, capsys):
    """Exit 4 — nothing to test. Distinct from the unreadable registry below, because one is
    solved by entering a channel and the other by fixing a file."""
    assert tool.main(["--kind", "signal", "--account", str(_LIVE)]) == 4
    assert box.posted == []
    assert "names no signal channel" in capsys.readouterr().out


def test_an_UNREADABLE_registry_is_a_DIFFERENT_answer(box, capsys):
    """Exit 3. Rule 1 in a diagnostic: *this account names no channel* and *nobody could open the
    file that would say* are two facts, and reporting them as one sends somebody to do the wrong
    work."""
    box.reg.write_text("{ not json", encoding="utf-8")
    assert tool.main(["--kind", "trade", "--account", str(_LIVE)]) == 3
    assert box.posted == []
    assert "could not be read" in capsys.readouterr().out


def test_a_refusal_FROM_TELEGRAM_is_reported_as_a_failure(box, capsys):
    """The case the tool exists for: an id that parses fine and that the bot cannot post to."""
    box.state["ok"] = False
    assert tool.main(["--kind", "trade", "--chat-id", "-1008888888888"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out
    # The reason Telegram gave survives to the reader — it IS the product of this tool.
    assert "chat not found" in out


def test_an_unknown_KIND_is_refused_before_anything_is_sent(box):
    assert tool.main(["--kind", "trades", "--chat-id", "-1009999999999"]) == 2
    assert box.posted == []


def test_neither_an_account_nor_an_id_is_refused(box):
    assert tool.main(["--kind", "trade"]) == 2


def test_the_message_says_WHAT_it_is_and_WHY_it_arrived(box):
    """The person reading the channel is often not the person who pressed the button. An
    unexplained message in a channel somebody has just been handed reads as a bot misbehaving."""
    tool.main(["--kind", "trade", "--chat-id", "-1009999999999", "--account", str(_LIVE)])
    text = box.posted[0]["text"]
    assert "TEST MESSAGE" in text and "trade channel" in text
    assert str(_LIVE) in text and "-1009999999999" in text
    assert "Nothing is trading because of this message" in text


def test_a_channel_id_STARTING_WITH_A_MINUS_is_read_as_a_value(box):
    """Every Telegram channel id is a minus followed by digits, and a command-line parser reaches
    for anything starting with `-` as a flag. It is read as a value because the id is all digits;
    an id with a letter in it would be taken as an unknown option and refused.

    This is pinned rather than left to luck: the ids in these tests are the shape real ones are,
    for the same reason a fixture must never be able to do something production cannot."""
    assert tool.main(["--kind", "trade", "--chat-id", "-1004410831757"]) == 0
    assert box.posted[0]["chat_id"] == "-1004410831757"


def test_a_channel_USERNAME_is_accepted_too(box):
    """A public channel can be addressed as `@name`, which Telegram accepts in place of an id."""
    assert tool.main(["--kind", "trade", "--chat-id", "@lwg_live_trades"]) == 0
    assert box.posted[0]["chat_id"] == "@lwg_live_trades"


def test_the_message_is_sent_as_PLAIN_TEXT(box):
    """Telegram eats an even number of underscores in silence — HTTP 200, characters gone. A chat
    id starts with a minus and a bot key is full of underscores, so a test message asking to be
    parsed can arrive altered and still report success."""
    tool.main(["--kind", "trade", "--chat-id", "-1009999999999"])
    assert "parse_mode" not in box.posted[0]


def test_an_unexpected_failure_is_a_VERDICT_not_a_traceback(box, monkeypatch, capsys):
    """Over SSH an unhandled traceback reads to the Command Center as *no answer* rather than as a
    failure, which is the one outcome a checking tool may never produce."""

    def boom(*a, **k):
        raise RuntimeError("registry on fire")

    monkeypatch.setattr(tool, "run", boom)
    assert tool.main(["--kind", "trade", "--chat-id", "-1009999999999"]) == 1
    assert "FAIL: RuntimeError: registry on fire" in capsys.readouterr().out
