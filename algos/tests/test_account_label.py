"""Demo or live is worked out from the ACCOUNT, at the moment a message is written.

**Why (2026-09-11).** Two bots now run the same strategy on two accounts, and for the day they
existed the demo copies were NAMED "SOS Fade (demo)" so Telegram could tell them apart. Aaron:
*"it's a generic strategy, not a demo specific strategy."* He was right in a way that costs
money: a bot can be moved, and the name would have gone on saying demo while it traded real
money — the originals' own keys already say `demo` and trade the live account. So names are the
strategy alone, and `bot_state.labelled` adds `LIVE` or `demo` off the account registry, which is
the same row the command center's label and its go-live refusal read.

What is pinned here: the registry is what answers (never a guess), an account it cannot classify
keeps the plain name, and nothing on this path can raise inside a notification.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ALGOS / "shared"))

import bot_state  # noqa: E402

_LIVE, _DEMO = 34957946, 700152905


@pytest.fixture
def registry(monkeypatch, tmp_path):
    """A private account registry, so a test never reads whatever the real one says today."""

    def _write(rows):
        path = tmp_path / "accounts.json"
        path.write_text(json.dumps({"accounts": rows}), encoding="utf-8")
        monkeypatch.setattr(bot_state, "_ACCOUNTS", path)
        return path

    _write(
        [
            {"account": _DEMO, "kind": "demo"},
            {"account": _LIVE, "kind": "live"},
        ]
    )
    return _write


def test_the_registry_says_which_kind_an_account_is(registry):
    assert bot_state.account_kind(_LIVE) == "live"
    assert bot_state.account_kind(_DEMO) == "demo"


def test_an_account_number_written_as_TEXT_still_matches(registry):
    """`bot_state.json` has stored the account as a string; a message about it must not lose its
    tag over the quote marks."""
    assert bot_state.account_kind(str(_LIVE)) == "live"


@pytest.mark.parametrize("account", [None, 111, "not-a-number"])
def test_no_account_or_an_UNREGISTERED_one_is_None_never_a_guess(registry, account):
    """A benched bot, a login nobody registered, a malformed value: the registry does not say, so
    nothing is claimed — never `demo` (which would bury a live fill) and never `live`."""
    assert bot_state.account_kind(account) is None


def test_a_kind_that_is_neither_live_nor_demo_is_None(registry):
    """A `contest` account, or a typo, is not real money and is not demo either; saying nothing is
    the honest answer."""
    registry([{"account": _DEMO, "kind": "contest"}])
    assert bot_state.account_kind(_DEMO) is None


def test_an_unreadable_registry_is_None_never_a_crash(monkeypatch, tmp_path):
    bad = tmp_path / "accounts.json"
    bad.write_text("{ not json", encoding="utf-8")
    monkeypatch.setattr(bot_state, "_ACCOUNTS", bad)
    assert bot_state.account_kind(_LIVE) is None
    monkeypatch.setattr(bot_state, "_ACCOUNTS", tmp_path / "missing.json")
    assert bot_state.account_kind(_LIVE) is None


def test_a_malformed_row_is_skipped_not_fatal(registry):
    """One bad row must not blind the lookup for every other account."""
    registry(["junk", {"account": None}, {"kind": "live"}, {"account": _LIVE, "kind": "live"}])
    assert bot_state.account_kind(_LIVE) == "live"


def test_the_label_says_LIVE_or_demo(registry):
    assert bot_state.labelled("SOS Fade", _LIVE) == "SOS Fade · LIVE"
    assert bot_state.labelled("SOS Fade", _DEMO) == "SOS Fade · demo"


def test_two_copies_of_one_strategy_are_told_apart_by_their_ACCOUNTS(registry):
    """The case the old "(demo)" name existed for, answered without it."""
    live = bot_state.labelled("SOS Fade", _LIVE)
    demo = bot_state.labelled("SOS Fade", _DEMO)
    assert live != demo


def test_an_unclassifiable_account_keeps_the_PLAIN_name(registry):
    """No tag rather than a guessed one — the plain name is what every message said before."""
    assert bot_state.labelled("SOS Fade", 111) == "SOS Fade"
    assert bot_state.labelled("SOS Fade", None) == "SOS Fade"


def test_the_label_FOLLOWS_the_account_when_the_registry_changes(registry):
    """Worked out at the moment of writing, never stored — so a corrected row, or a bot moved to
    another account, cannot leave a stale tag behind."""
    assert bot_state.labelled("SOS Fade", _DEMO) == "SOS Fade · demo"
    registry([{"account": _DEMO, "kind": "live"}])
    assert bot_state.labelled("SOS Fade", _DEMO) == "SOS Fade · LIVE"


def test_bot_label_reads_the_bots_OWN_config_for_its_account(registry, monkeypatch):
    monkeypatch.setattr(bot_state, "read_account", lambda key: {"a": _LIVE, "b": _DEMO}.get(key))
    monkeypatch.setattr(bot_state, "BOT_NAMES", {"a": "SOS Fade", "b": "SOS Fade"})
    assert bot_state.bot_label("a") == "SOS Fade · LIVE"
    assert bot_state.bot_label("b") == "SOS Fade · demo"


def test_no_registered_name_says_demo_or_live():
    """The rule itself: a name is the strategy, and the account's kind is added by `labelled`. A
    name carrying either word would contradict the tag the day its bot moved."""
    for key, name in bot_state.BOT_NAMES.items():
        lowered = name.lower()
        assert "demo" not in lowered and "live" not in lowered, f"{key}: {name!r}"


def test_a_start_RE_STAMPS_the_stored_name(monkeypatch, tmp_path):
    """The stored name was written once, at the entry's creation, so a renamed bot kept its old
    name in its state file for ever. MUTATION: drop `name` from `set_started` -> red."""
    seen = {}
    monkeypatch.setattr(bot_state, "write_bot", lambda key, fields: seen.update(fields))
    monkeypatch.setattr(bot_state, "read_account", lambda key: _DEMO)
    monkeypatch.setattr(bot_state, "BOT_NAMES", {"copy": "SOS Fade"})
    bot_state.set_started("copy")
    assert seen["name"] == "SOS Fade"


def test_the_REAL_registry_classifies_both_accounts_the_bots_trade():
    """The committed registry, read the way the bots read it: the live account and the demo
    account both come back with a kind, so every message from today's bots carries one."""
    assert bot_state.account_kind(_LIVE) == "live"
    assert bot_state.account_kind(_DEMO) == "demo"
