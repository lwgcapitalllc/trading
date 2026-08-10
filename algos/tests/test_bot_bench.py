"""The BENCH — a registered bot with no account — and the account being DERIVED, not restated.

**Why this file exists.** Adding and removing bots from an account is now something Aaron does in
the browser (`command-center` → Bots → Accounts), which makes two facts about a bot MOVE that used
to be constants: which account it trades, and whether anything should expect it to be running.
Every place that had a private copy of either is a place that can now go stale, silently, in the
reassuring direction.

Two rules, and everything here is one or the other:

  * **`account` is read from the bot's own instance config, never restated.** `BOT_ACCOUNTS` was
    a hardcoded login per bot stamped into `bot_state.json`, which is what the Bots page renders
    in its Account column — so a moved bot would have gone on displaying the old number.
  * **The bench is ONE definition**, shared by the boot coordinator, the process watchdog and the
    dead-man's switch. Three copies is three chances for one of them to alarm about a bot
    somebody deliberately took off an account, which is how an alert channel gets muted.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "algos" / "shared"))
import bot_state as bs  # noqa: E402


@pytest.fixture
def instances(tmp_path, monkeypatch):
    """A private instances tree, so nothing here reads the real live bot's config."""
    def _write(key, body):
        d = tmp_path / key
        d.mkdir(parents=True, exist_ok=True)
        (d / "config.json").write_text(json.dumps(body))
        bs.BOT_INSTANCES[key] = d
        return d
    monkeypatch.setattr(bs, "BOT_INSTANCES", dict(bs.BOT_INSTANCES))
    return _write


# ── the account is DERIVED ────────────────────────────────────────────────────
def test_the_account_comes_from_the_bots_own_config(instances):
    instances("b1", {"bot_key": "b1", "account": 700107749})
    assert bs.read_account("b1") == 700107749


def test_moving_a_bot_moves_the_account_it_reports(instances):
    """MUTATION: restore a hardcoded account map -> red.

    This is the whole reason `BOT_ACCOUNTS` was deleted. The Bots page writes the new account
    into the config; anything holding its own copy would keep reporting the old one, on the very
    page you would look at to check the move worked."""
    d = instances("b1", {"bot_key": "b1", "account": 111})
    assert bs.read_account("b1") == 111
    (d / "config.json").write_text(json.dumps({"bot_key": "b1", "account": 222}))
    assert bs.read_account("b1") == 222


def test_a_benched_bot_reports_no_account(instances):
    instances("b1", {"bot_key": "b1", "account": None})
    assert bs.read_account("b1") is None


# ── the bench, and the three-way read behind it ───────────────────────────────
def test_a_bot_with_an_account_is_assigned(instances):
    instances("b1", {"bot_key": "b1", "account": 700107749})
    assert bs.is_assigned("b1") is True


def test_a_bot_with_a_null_account_is_not_assigned(instances):
    instances("b1", {"bot_key": "b1", "account": None})
    assert bs.is_assigned("b1") is False


def test_an_UNREADABLE_config_is_treated_as_assigned(instances):
    """MUTATION: return False on the read failure -> red.

    "No account" and "could not ask" must not be one value. Of the two wrong answers, watching a
    bot that is not running is noisy, and quietly not watching a live one is silent."""
    d = instances("b1", {"bot_key": "b1", "account": None})
    (d / "config.json").write_text("{not json")
    assert bs.is_assigned("b1") is True


def test_a_key_that_is_in_NO_instance_registry_is_treated_as_assigned():
    """A bot in a watchdog's roster that `BOT_INSTANCES` does not know is a registry MISMATCH.
    That is a fault to be loud about, not a bot to quietly stop watching."""
    assert bs.is_assigned("never_registered_anywhere") is True


# ── the watchdog stands down for a benched bot ────────────────────────────────
def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, _REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_process_watchdog_skips_a_benched_bot(monkeypatch):
    """MUTATION: drop the `is_assigned` skip from `monitor.main` -> red.

    Worse than noisy: this watchdog's RESPONSE to an offline bot is to start it, so without the
    skip it would launch a bot with no account to trade, every pass, for ever."""
    monitor = _load("monitor_bench", "algos/notifications/monitor.py")
    checked: list[str] = []
    monkeypatch.setattr(monitor, "BOTS", {"assigned": {}, "benched": {}})
    monkeypatch.setattr(monitor, "check_bot", lambda k, s, t: checked.append(k) or {})
    monkeypatch.setattr(monitor, "check_telegram_bot", lambda s: {})
    monkeypatch.setattr(monitor, "load_state", lambda: {})
    monkeypatch.setattr(monitor, "save_state", lambda s: None)
    monkeypatch.setattr(monitor._bot_state, "is_assigned", lambda k: k == "assigned")

    monitor.main()
    assert checked == ["assigned"]
