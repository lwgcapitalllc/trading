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
    monkeypatch.setattr(monitor, "_query_process_list", lambda: "")
    monkeypatch.setattr(monitor, "BOTS", {"assigned": {}, "benched": {}})
    monkeypatch.setattr(monitor, "check_bot", lambda k, s, t: checked.append(k) or {})
    monkeypatch.setattr(monitor, "check_telegram_bot", lambda s: {})
    monkeypatch.setattr(monitor, "load_state", lambda: {})
    monkeypatch.setattr(monitor, "save_state", lambda s: None)
    monkeypatch.setattr(monitor._bot_state, "is_assigned", lambda k: k == "assigned")

    monitor.main()
    assert checked == ["assigned"]


# ── every roster is DERIVED from the bot folders ──────────────────────────────
#
# 🔴 **A bot lived in FIVE hand-kept lists until 2026-09-13** — the state map and the display names
# here, the boot sequence, the process watchdog, the dead-man's switch, and the Command Center's own
# list. Tests held the five together and could catch a mismatch; they could not stop one being
# written, and every omission was silent: a bot missing from the state map died on startup with a
# bare KeyError after connecting and warming, one missing from the boot sequence was absent after a
# reboot, one missing from a watcher was a bot nothing watched. A bot IS its folder now
# (`bot_registry.discover`); what is left to pin is that every roster reads it and none has grown a
# hand-kept list again.


def _algos_rosters():
    """Every algos-side roster, as {name: set of bot keys}."""
    monitor = _load("monitor_registry", "algos/notifications/monitor.py")
    deadman = _load("deadman_registry", "algos/notifications/deadman.py")
    coord = _load("coordinator_registry", "algos/bots/startup_coordinator.py")
    return {
        "bot_state.BOT_INSTANCES": set(bs.BOT_INSTANCES),
        "bot_state.BOT_NAMES": set(bs.BOT_NAMES),
        "monitor.BOTS": set(monitor.BOTS),
        "deadman.BOTS": set(deadman.BOTS),
        "startup_coordinator.startup_sequence()": {row[0] for row in coord.startup_sequence()},
    }


def test_every_algos_roster_IS_the_bot_folders():
    """MUTATION: hand-type one roster again, or filter one — red, naming both sides.

    ⚠ Refuses an empty folder list: with nothing discovered every comparison passes for free."""
    import bot_registry

    folders = set(bot_registry.discover())
    assert folders, "no bot folders found - every assertion here would pass for free"
    for name, keys in _algos_rosters().items():
        assert keys == folders, (
            f"{name} holds {sorted(keys)} but the bot folders are {sorted(folders)}. Every roster "
            f"that starts, watches or names a bot reads the folders — see this section's header."
        )


def test_a_new_bot_folder_joins_the_rosters_with_no_other_edit(tmp_path):
    """The feature: creating the folder IS registering the bot. A folder with no config (a watcher
    once made one named after a renamed bot) is not one."""
    import bot_registry

    for key in ("alpha_1", "beta_2"):
        d = tmp_path / key
        d.mkdir()
        (d / "config.json").write_text(json.dumps({"bot_key": key, "display_name": key.title()}))
    (tmp_path / "left_behind").mkdir()
    coord = _load("coordinator_new_folder", "algos/bots/startup_coordinator.py")

    assert set(bot_registry.discover(tmp_path)) == {"alpha_1", "beta_2"}
    assert {row[0] for row in coord.startup_sequence(tmp_path)} == {"alpha_1", "beta_2"}


def test_the_command_center_keeps_no_hand_list_of_bots():
    """The Command Center's list is DERIVED from the same folders (`routers/bots.py`
    `_discover_bots`) — its own backend tests pin the derivation. This pins the other direction:
    no bot key typed into a `BotReg` by hand, which would be a sixth list the folders cannot move.

    ⚠ **Parsed rather than imported, deliberately.** That router lives in another package with
    its own venv and imports FastAPI; importing it here would wire two trees together to answer a
    question about a list of strings.
    """
    import re

    import bot_registry

    text = (_REPO / "command-center/backend/routers/bots.py").read_text(encoding="utf-8")
    assert "_discover_bots" in text, "the Command Center no longer derives its bot list?"
    # A POPULATED literal. `_BOTS: list[BotReg] = []` is the empty list the discovery fills in
    # place, and a plain substring check read that as the hand list coming back.
    hand_list = re.search(r"_BOTS\s*:\s*list\[BotReg\]\s*=\s*\[\s*[^\]\s]", text)
    assert not hand_list, "the Command Center's hand-kept bot list is back"
    typed = set(re.findall(r'key="([a-z0-9_]+)"', text)) & set(bot_registry.discover())
    assert not typed, f"the Command Center types these bot keys by hand: {sorted(typed)}"


def test_every_bot_folder_names_itself():
    """`live_config.load` REFUSES a config whose `bot_key` is not its folder's name — a copied
    folder with the key left unchanged would write into the other bot's state, ledger and position
    record. Pinned on the real folders so a hand-made copy fails here rather than at its start."""
    import bot_registry

    for key, folder in bot_registry.discover().items():
        raw = bot_registry.read_config(folder)
        assert raw is not None, f"{key}: config.json cannot be read"
        assert raw.get("bot_key") == key, f"{key}/config.json says it is {raw.get('bot_key')!r}"


def test_each_bots_name_comes_from_its_own_config():
    """One bot, one name, read off its own file — so a Telegram alert and a page column cannot
    call one bot two things. MUTATION: fall back to the key when a display name exists -> red."""
    import bot_registry

    for key, folder in bot_registry.discover().items():
        raw = bot_registry.read_config(folder) or {}
        assert bs.BOT_NAMES[key] == (raw.get("display_name") or key), key


def test_every_bot_pins_every_setting_its_strategy_declares():
    """An instance config states what the bot trades. A field it does NOT state resolves to
    whatever the strategy dataclass happens to default to that day.

    🔴 **This is a real failure, not a hypothetical: `b_leg_demo` was missing 57 fields on
    2026-09-07.** Its config was dumped from the dataclass on 2026-08-09 and was complete THAT
    DAY — but a dump is a snapshot and the dataclass kept growing, so every field added since
    silently inherited a moving default. The one that bit: the add-size setting arrived
    2026-08-16 and flipped off → on on 2026-09-06, so arming that bot would have started it
    scaling in — a behaviour never measured on it, and one its Pine parity gate has no column to
    check. Its own note claimed 'every field ... DUMPED' throughout, so the file asserted a
    completeness it had quietly lost and nothing could fail.

    ⚠ **A pin equal to the default changes nothing, which is exactly why this is cheap.** The
    cost of pinning everything is one line per setting; the cost of pinning nothing is that a
    default somebody else moves becomes a live behaviour change nobody decided.

    ⚠ **It reads the BOT's own declared strategy rather than a hardcoded list**, so a bot added
    tomorrow is covered without touching this file — and a benched bot is checked too, because
    the bench is exactly when the drift accumulates unseen.

    ⚠ **The reverse direction is checked in the same pass and it is the harsher failure:** the
    runner REFUSES to start on a key the dataclass does not declare, so an undeclared key is a
    bot that will not boot, discovered at startup rather than here.

    MUTATION: delete any one key from any instance config's settings and this goes red naming
    the bot and the field. Watched red by removing the add-size setting from `b_leg_demo`.
    """
    import dataclasses
    import importlib

    sys.path.insert(0, str(_REPO / "strategies" / "python"))
    checked = 0
    for key, path in bs.BOT_INSTANCES.items():
        doc = json.loads((path / "config.json").read_text(encoding="utf-8"))
        pkg, cls_name = doc.get("strategy_package"), doc.get("strategy_class")
        assert pkg and cls_name, f"{key} names no strategy package/class"
        cfg_cls = getattr(
            importlib.import_module(f"{pkg}.config"), cls_name.replace("Strategy", "Config")
        )
        declared = {f.name for f in dataclasses.fields(cfg_cls)}
        assert declared, f"{cfg_cls.__name__} declared no fields — this would pass for free"
        pinned = set(doc.get("strategy_params") or {})

        unpinned = sorted(declared - pinned)
        assert not unpinned, (
            f"{key} does not state {len(unpinned)} of {cfg_cls.__name__}'s settings, so each one "
            f"trades at whatever that dataclass defaults to today: {unpinned}. Re-dump the "
            f"config from the dataclass and diff it before this bot is armed."
        )
        undeclared = sorted(pinned - declared)
        assert not undeclared, (
            f"{key} states {undeclared}, which {cfg_cls.__name__} does not declare. The runner "
            f"REFUSES to build a strategy on an unknown key, so this bot cannot start."
        )
        checked += 1
    assert checked >= 3, f"only {checked} bots checked — the roster parsed as near-empty"
