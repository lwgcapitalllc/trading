"""One record per bot, and every other map derived from it.

There were NINE parallel dicts here, keyed three different ways — task name, bot key, and
state-file section. Registering a bot meant editing all nine, and forgetting one produced a
confident wrong answer rather than an error:

  * no `_TASK_ACCT_TYPE` entry ⇒ `.get(task, "demo")` rendered a **LIVE bot as demo**,
    which loses the amber tinting, the "N of these are LIVE accounts" warning on every
    fleet dialog, and its place in the demo/live filter — all at once, and all silently.
  * no `_SUPPRESS_KEYS` entry ⇒ "Stop all N bots" skipped that bot **and reported success**,
    because `_stop_procs` iterated the crash-alert map while the count on the button came
    from the registry it was not using.

Neither is reachable now, and these tests are about keeping it that way. They are written
against the DERIVATION, not against `mpc_sos_fade_demo`, so they still mean something on the
day bot #2 lands — which is the whole reason the audit that found this ran.
"""

import pytest
from routers import bots

# ── The registration itself ───────────────────────────────────────────────────


def test_account_type_cannot_be_omitted():
    """No default, on purpose. A bot registered without one is a TypeError at import — loud,
    and at the only moment when it costs nothing. The old `.get(task, "demo")` defaulted in
    the dangerous direction."""
    with pytest.raises(TypeError):
        bots.BotReg(task="BOT_X", key="x_live", display="X")


def test_account_type_must_be_demo_or_live():
    """A typo is not a third account type. `"Live"` would compare unequal to `"live"`
    everywhere downstream and quietly file the bot as neither."""
    with pytest.raises(ValueError):
        bots.BotReg(task="BOT_X", key="x_live", display="X", account_type="Live")


def test_the_conventional_names_are_derived_from_the_key():
    b = bots.BotReg(task="BOT_X", key="x_demo", display="X", account_type="demo")
    assert b.instance_dir == "x_demo"
    assert b.suppress_key == "x_demo"
    # ⚠ EMPTY, not "x_demo.log". It used to default to that name, and the runner stopped
    # writing it on 2026-08-05 when it moved to one file per UTC day — so the log panel served
    # a dead file for nineteen days. Empty now means "discover the newest daily file";
    # tests/test_bot_log_view.py owns that behaviour.
    assert b.log_file == ""
    assert b.state_file.endswith(r"\x_demo\bot_state.json")


def test_a_bot_that_breaks_the_convention_can_override_every_one():
    b = bots.BotReg(
        task="BOT_X",
        key="x_demo",
        display="X",
        account_type="live",
        instance_dir="shared_dir",
        log_file="custom.log",
        suppress_key="short",
        state_section="state_shared",
    )
    assert (b.instance_dir, b.log_file, b.suppress_key) == ("shared_dir", "custom.log", "short")
    assert b.state_file.endswith(r"\shared_dir\bot_state.json")


def test_two_bots_sharing_a_state_file_share_one_section():
    """`_BOT_STATE_SECTIONS` groups by FILE — a single bot_state.json can hold several bot
    keys, which is why its value is a list and not a key."""
    a = bots.BotReg(
        task="A", key="a", display="A", account_type="demo", state_section="state_shared"
    )
    b = bots.BotReg(
        task="B", key="b", display="B", account_type="demo", state_section="state_shared"
    )
    sections = [
        (s, [x.key for x in (a, b) if x.state_section == s])
        for s in dict.fromkeys(x.state_section for x in (a, b))
    ]
    assert sections == [("state_shared", ["a", "b"])]


# ── Every derived map covers every bot ────────────────────────────────────────


def test_every_registered_bot_appears_in_every_derived_map():
    """The failure this replaces was never a crash — it was one map missing one bot."""
    for b in bots._BOTS:
        assert bots._TASK_BOT_KEYS[b.task] == b.key
        assert bots._DISPLAY_NAMES[b.task] == b.display
        assert bots._KEY_DISPLAY[b.key] == b.display
        assert bots._SUPPRESS_KEYS[b.key] == b.suppress_key
        assert bots._BOT_INSTANCE_MAP[b.key]["section"] == b.config_section
        assert bots._BOT_STATE_PATHS[b.state_section] == b.state_file
        assert bots._bot_state_path(b.key) == b.state_file
        assert b.task in bots._BOT_DISPLAY_ORDER


def test_the_sys_job_names_do_not_collide_with_a_bot():
    """`_DISPLAY_NAMES` merges bots over the SYS_* jobs. A bot registered under a SYS_ task
    would shadow one and `_resolve_bot` would answer for the wrong thing."""
    assert not ({b.task for b in bots._BOTS} & set(bots._SYS_DISPLAY_NAMES))


def test_bot_keys_and_display_names_are_unique():
    """`_resolve_bot` matches on display name, and `_kill_bot` matches on key. A duplicate
    of either makes one bot's controls act on another."""
    keys = [b.key for b in bots._BOTS]
    names = [b.display.lower() for b in bots._BOTS]
    assert len(set(keys)) == len(keys)
    assert len(set(names)) == len(names)


# ── The two behaviours the missing entries broke ──────────────────────────────


def test_stop_all_kills_every_registered_bot(monkeypatch):
    """It used to iterate `_SUPPRESS_KEYS`, which is a different question that happened to
    have the same answer."""
    killed: list[str] = []
    monkeypatch.setattr(bots, "_kill_bot", lambda k: killed.append(k) or "")
    monkeypatch.setattr(bots, "_ssh", lambda _c: "")
    bots._stop_procs()
    assert killed == [b.key for b in bots._BOTS]


def test_the_snapshot_reports_each_bots_own_account_type(monkeypatch):
    monkeypatch.setattr(bots, "_fetch_vps_snapshot", lambda: {})
    snap = bots.get_snapshot()
    by_name = {b.name: b for b in snap.bots}
    for reg in bots._BOTS:
        assert by_name[reg.display].account_type == reg.account_type


# ── Which name identifies a bot ───────────────────────────────────────────────


def test_a_bot_resolves_by_its_key(monkeypatch):
    """The key is the stable identifier. Every route was keyed on the DISPLAY NAME — a
    label, chosen for a human, and therefore the one field somebody eventually changes."""
    for b in bots._BOTS:
        assert bots._resolve_bot(b.key) == (b.task, b.key)


def test_a_bot_still_resolves_by_its_display_name(monkeypatch):
    """Kept working on purpose — the frontend renders off `BotStatus.name` and there is no
    version of this worth a flag day."""
    for b in bots._BOTS:
        assert bots._resolve_bot(b.display) == (b.task, b.key)
        assert bots._resolve_bot(b.display.lower()) == (b.task, b.key)


def test_the_key_is_tried_before_the_display_name(monkeypatch):
    """If a future bot's display name equals another bot's key, name-first would route one
    bot's Stop to the other. The registry cannot rule that out — the two namespaces are
    free — so the ORDER is the guarantee."""
    a = bots.BotReg(task="A", key="shared", display="A one", account_type="demo")
    b = bots.BotReg(task="B", key="b_key", display="Shared", account_type="live")
    monkeypatch.setattr(bots, "_BOTS", [a, b])
    monkeypatch.setattr(bots, "_BY_KEY", {x.key: x for x in (a, b)})
    assert bots._resolve_bot("shared") == ("A", "shared")


def test_an_unknown_reference_is_a_404():
    with pytest.raises(Exception) as e:
        bots._resolve_bot("no_such_bot")
    assert getattr(e.value, "status_code", None) == 404


def test_the_snapshot_carries_the_key_the_routes_accept(monkeypatch):
    """A page can only use the stable identifier if the snapshot hands it one."""
    monkeypatch.setattr(bots, "_fetch_vps_snapshot", lambda: {})
    for row in bots.get_snapshot().bots:
        assert bots._resolve_bot(row.key)[1] == row.key
