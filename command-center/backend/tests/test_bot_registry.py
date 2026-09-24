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
against the DERIVATION, not against `sos_fade_demo`, so they still mean something on the
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


def test_bot_keys_are_unique():
    """`_kill_bot` and every route match on the key. A duplicate makes one bot's controls act on
    another. (Display names are NOT unique since 2026-09-11 — see the two tests below.)"""
    keys = [b.key for b in bots._BOTS]
    assert len(set(keys)) == len(keys)


def test_a_name_two_bots_SHARE_is_refused_never_resolved_to_the_first(monkeypatch):
    """🔴 Two copies of one strategy share a display name on purpose (a name is the strategy; demo
    or live belongs to the account). The old first-match sent a by-name Stop to whichever bot
    registered first — the LIVE one. MUTATION: drop the `len(named) > 1` refusal -> red."""
    live = bots.BotReg(task="A", key="a_live", display="Same", account_type="live")
    demo = bots.BotReg(task="B", key="a_demo", display="Same", account_type="demo")
    monkeypatch.setattr(bots, "_BOTS", [live, demo])
    monkeypatch.setattr(bots, "_BY_KEY", {x.key: x for x in (live, demo)})
    with pytest.raises(Exception) as e:
        bots._resolve_bot("same")
    assert getattr(e.value, "status_code", None) == 409
    assert "a_live" in e.value.detail and "a_demo" in e.value.detail
    # ...and each key still reaches exactly its own bot.
    assert bots._resolve_bot("a_live") == ("A", "a_live")
    assert bots._resolve_bot("a_demo") == ("B", "a_demo")


def test_the_REAL_registry_has_copies_sharing_a_name_and_each_key_resolves():
    """The case above is not hypothetical: the demo copies carry their originals' names. Every
    shared name must refuse, and every key must still reach its own bot."""
    from collections import Counter

    counts = Counter(b.display.lower() for b in bots._BOTS)
    shared = [n for n, c in counts.items() if c > 1]
    assert shared, "no two bots share a name - this test's premise has gone"
    for name in shared:
        with pytest.raises(Exception) as e:
            bots._resolve_bot(name)
        assert getattr(e.value, "status_code", None) == 409
    for b in bots._BOTS:
        assert bots._resolve_bot(b.key) == (b.task, b.key)


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
    """The type is DERIVED from the account the bot's config names, looked up in the account list,
    with the hardcoded label only as a fallback (`_account_type_of`).

    🔴 **It compared against the hardcoded label until 2026-09-11 and went red the day two bots
    went LIVE** — their configs name the live account while their registry label still says demo.
    The page was right and the test's premise had gone stale; a test that can only pass while every
    bot is on a demo account is not testing the derivation at all. The expected value is built here
    from the config and the account list directly, never by calling the function under test.
    """
    monkeypatch.setattr(bots, "_fetch_vps_snapshot", lambda: {})
    snap = bots.get_snapshot()
    # By KEY, never by name: two copies of one strategy share a name since 2026-09-11, and a
    # name-keyed map would collapse them and compare the live copy against the demo one's answer.
    by_key = {b.key: b for b in snap.bots}
    kinds = {
        a.account: a.kind for a in bots.bot_account_registry.load_accounts(bots._registry_path())
    }
    for reg in bots._BOTS:
        account = (bots._read_instance_config(reg.key) or {}).get("account")
        expected = kinds.get(account, reg.account_type) if account else reg.account_type
        assert by_key[reg.key].account_type == expected, reg.key


def test_the_snapshot_says_whether_the_account_may_trade_and_only_while_running(monkeypatch):
    """The page's "trading off" chip can only appear if the endpoint passes the bot's reading on —
    and only for a running bot, whose reading describes a process that still exists.

    MUTATION: drop `trade_allowed` from the row → red. MUTATION: drop the RUNNING gate → red.
    """
    key = bots._BOTS[0].key
    state = {"trade_allowed": False, "trade_block": "the broker has switched trading off"}
    running = {"value": True}
    monkeypatch.setattr(bots, "_fetch_vps_snapshot", lambda: {})
    monkeypatch.setattr(bots, "_parse_bot_states", lambda _snap: {key: state})
    monkeypatch.setattr(bots, "_bot_runner_running", lambda _snap, _key: running["value"])

    row = next(b for b in bots.get_snapshot().bots if b.key == key)
    assert (row.trade_allowed, row.trade_block) == (False, state["trade_block"])

    running["value"] = False
    row = next(b for b in bots.get_snapshot().bots if b.key == key)
    assert (row.trade_allowed, row.trade_block) == (None, None)


def _row_for(monkeypatch, state, *, running=True):
    key = bots._BOTS[0].key
    monkeypatch.setattr(bots, "_fetch_vps_snapshot", lambda: {})
    monkeypatch.setattr(bots, "_parse_bot_states", lambda _snap: {key: state})
    monkeypatch.setattr(bots, "_bot_runner_running", lambda _snap, _key: running)
    return next(b for b in bots.get_snapshot().bots if b.key == key)


# ── A balance is only an account's if it was READ on that account (2026-09-14) ──────────────────
#
# 🔴 Measured on the box the night two bots were taken live: both stopped copies' records still held
# the DEMO account's $15,844.46, and the starter had re-stamped them with the LIVE account's number
# when it tried to launch them — so the live account's card showed the demo's equity, and +$5,844.46
# "not from these bots". The bot writes the account each balance was READ on beside it
# (`observed_account`); a reading for another account is not this one's.

_HERE, _THERE = 900000001, 700000001

_DEMO_READING = {
    "balance": 15844.46,
    "capital_in": 10000.0,
    "total_pnl_pct": 58.44,
    "starting_balance": 15844.46,
    "starting_balance_account": _THERE,
}


def _snapshot_on(monkeypatch, state, *, config_account=_HERE, running=False):
    """The row, and the whole snapshot, for a bot whose CONFIG names `config_account` — the account
    the page lays its row under."""
    key = bots._BOTS[0].key
    real = bots._read_instance_config
    monkeypatch.setattr(
        bots,
        "_read_instance_config",
        lambda k: {**real(k), "account": config_account} if k == key else real(k),
    )
    monkeypatch.setattr(bots, "_fetch_vps_snapshot", lambda: {})
    monkeypatch.setattr(bots, "_parse_bot_states", lambda _snap: {key: state})
    monkeypatch.setattr(bots, "_bot_runner_running", lambda _snap, _key: running)
    snap = bots.get_snapshot()
    return next(b for b in snap.bots if b.key == key), snap


def _readings(row):
    return (row.balance, row.capital_in, row.total_pnl_pct, row.starting_balance)


def test_a_balance_read_on_the_account_a_bot_LEFT_is_not_the_new_accounts(monkeypatch):
    """The take-live case as measured: the record names the new account (the starter re-stamps it
    from the config on every launch) while its balance was read on the old one.

    MUTATION: drop the gate on the balance → red, the row states $15,844.46. MUTATION: drop the
    gate on the anchor alone → red. MUTATION: compare against the record's own account instead of
    the config's → still green HERE; the next test is the one that catches it.
    """
    state = {"account": _HERE, "observed_account": _THERE, **_DEMO_READING}
    row, snap = _snapshot_on(monkeypatch, state)
    assert _readings(row) == (None, None, None, None)
    # And so the account's card has no equity to show until a bot there reads one.
    card = next((e for e in snap.earnings if e.account == _HERE), None)
    assert card is not None, "the account the bot is on must still get a card"
    assert card.balance is None


def test_a_bot_moved_but_not_restarted_does_not_carry_its_old_balance_across(monkeypatch):
    """Between the move and the restart the record still names the OLD account throughout — its
    stamp and its reading agree with each other, and neither is where the page now lays the row.

    MUTATION: compare the reading against the record's own account → red.
    """
    state = {"account": _THERE, "observed_account": _THERE, **_DEMO_READING}
    row, _ = _snapshot_on(monkeypatch, state)
    assert _readings(row) == (None, None, None, None)


def test_a_stopped_bots_reading_of_its_OWN_account_still_stands(monkeypatch):
    """The control: the gate refuses a reading for ANOTHER account, never a reading as such. A stopped
    bot's last balance on the account it is on is still that account's latest measurement. The
    record states its account as a string here on purpose — an older writer did.

    MUTATION: blank the four fields unconditionally → red.
    """
    state = {
        "account": str(_HERE),
        "observed_account": _HERE,
        **_DEMO_READING,
        "starting_balance_account": _HERE,
    }
    row, _ = _snapshot_on(monkeypatch, state)
    assert _readings(row) == (15844.46, 10000.0, 58.44, 15844.46)


def test_a_balance_that_does_not_say_where_it_was_read_is_not_stated(monkeypatch):
    """Every runner since 2026-09-10 writes the account beside the balance, off the same terminal
    call, and both live bots' frozen code carries it. A reading without it cannot be placed, and
    *cannot say* is not *this account's* (rule 1).

    MUTATION: let a missing read-on account through → red.
    """
    state = {"account": _HERE, **_DEMO_READING, "starting_balance_account": _HERE}
    row, _ = _snapshot_on(monkeypatch, state)
    assert (row.balance, row.capital_in, row.total_pnl_pct) == (None, None, None)
    # The anchor states its own account, so it stands on its own evidence.
    assert row.starting_balance == 15844.46


def test_the_snapshot_carries_the_open_trade_and_the_halt_only_while_running(monkeypatch):
    """The row's "trade open" and "halted" tags can only appear if the endpoint passes the bot's
    reading on — and only for a running bot: a stopped bot's last reading describes a process that
    no longer exists, and its trade may have closed since.

    MUTATION: drop `in_trade` from the row → red. MUTATION: drop the RUNNING gate → red.
    MUTATION: serve the halt reason beside a bridge that is not halted → red.
    """
    position = {
        "side": "long",
        "lots": 0.4,
        "entry": 3290.0,
        "stop": 3280.0,
        "profit_usd": 83.0,
        "risk_usd": 70.0,
        "r": 1.19,
        "tickets": 1,
    }
    state = {
        "bridge_state": "halted",
        "halt_reason": "MT5 holds none",
        "in_trade": True,
        "position": position,
    }
    row = _row_for(monkeypatch, state)
    assert (row.bridge_state, row.halt_reason, row.in_trade) == ("halted", "MT5 holds none", True)
    assert row.position is not None
    assert (row.position.side, row.position.lots, row.position.r) == ("long", 0.4, 1.19)
    assert (row.position.risk_usd, row.position.tickets) == (70.0, 1)

    state["bridge_state"] = "live"
    row = _row_for(monkeypatch, state)
    assert (row.bridge_state, row.halt_reason) == ("live", None)

    row = _row_for(monkeypatch, state, running=False)
    assert (row.bridge_state, row.halt_reason, row.in_trade, row.position) == (None,) * 4


def test_the_target_has_three_answers_a_price_none_and_not_reported(monkeypatch):
    """2026-09-24. The runner reports the broker's take-profit and its R. A runner from before that
    says NOTHING about a target, and that must not read as "this trade has no target" — live SOS
    Fade's ordinary trade really has none, so the two would be indistinguishable on the page.

    MUTATION: serve `target_reported` True always → red on the older runner.
    MUTATION: let a 0 through as a price → red on the zero.
    """
    base = {"side": "long", "lots": 0.4, "entry": 3290.0, "stop": 3280.0, "tickets": 1}

    def served(pos):
        return _row_for(
            monkeypatch, {"bridge_state": "live", "in_trade": True, "position": pos}
        ).position

    got = served({**base, "target": 3320.0, "target_r": 3.0})
    assert (got.target, got.target_r, got.target_reported) == (3320.0, 3.0, True)
    got = served({**base, "target": None, "target_r": None})
    assert (got.target, got.target_r, got.target_reported) == (None, None, True)
    got = served(dict(base))
    assert (got.target, got.target_r, got.target_reported) == (None, None, False)
    got = served({**base, "target": 0.0, "target_r": -9.0})
    assert (got.target, got.target_r, got.target_reported) == (None, None, True)


def test_a_bot_on_an_older_runner_still_shows_its_halt_and_a_watchdog_word_is_not_one(monkeypatch):
    """Until 2026-09-12 the runner wrote the bridge's state only into `status` — a key the watchdog
    and the launcher also write (running / stalled / stopped / offline). A halt there must still
    show; one of their words must never read as the bridge's.

    MUTATION: drop the `status` fallback → red on `halted`. MUTATION: take any `status` word → red
    on `stalled`.
    """
    for word, expected in (("halted", "halted"), ("stalled", None), ("running", None)):
        row = _row_for(monkeypatch, {"status": word})
        assert row.bridge_state == expected, word


def test_a_reading_the_page_cannot_draw_is_withheld_never_served(monkeypatch):
    """The state file is JSON another program wrote. A position the page cannot draw is dropped —
    `in_trade` still says the bot holds something — and it must never fail the snapshot, which
    would blank every bot on the page. A flag that is not a real boolean is not an answer.

    MUTATION: pass the raw reading through → red (a 500, or a side nothing can draw).
    MUTATION: coerce `in_trade` rather than require a boolean → red on "yes".
    """
    for bad in (
        "long",
        {"side": "sideways", "lots": 0.4},
        {"side": "long", "lots": 0},
        {"side": "long", "lots": "many"},
    ):
        row = _row_for(monkeypatch, {"in_trade": True, "position": bad})
        assert (row.in_trade, row.position) == (True, None), bad

    row = _row_for(monkeypatch, {"in_trade": "yes"})
    assert row.in_trade is None


# ── Which name identifies a bot ───────────────────────────────────────────────


def test_a_bot_resolves_by_its_key(monkeypatch):
    """The key is the stable identifier. Every route was keyed on the DISPLAY NAME — a
    label, chosen for a human, and therefore the one field somebody eventually changes."""
    for b in bots._BOTS:
        assert bots._resolve_bot(b.key) == (b.task, b.key)


def test_a_bot_still_resolves_by_a_display_name_ONLY_it_carries(monkeypatch):
    """Kept working on purpose for a name one bot owns — the frontend passes keys, but scripts and
    older callers may not. A name two bots share is the refusal pinned above."""
    from collections import Counter

    counts = Counter(b.display.lower() for b in bots._BOTS)
    own = [b for b in bots._BOTS if counts[b.display.lower()] == 1]
    assert own, "every name is shared - nothing left to resolve by name"
    for b in own:
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


# ── The list is DISCOVERED from the bot folders (2026-09-13) ──────────────────
#
# 🔴 A hand-kept list of `BotReg`s until this date, and one of five: a bot missing here could not
# be put on an account from this page, and a bot only here was one the page could arm and no
# watchdog watched. A bot IS its folder now, on both sides (`algos/shared/bot_registry.py`).


@pytest.fixture
def bot_folders(tmp_path):
    """A private instances folder. The maps are rebuilt IN PLACE, so the real list is rebuilt on
    the way out — a test leaving scratch bots in `_BOTS` would hand them to every test after it."""
    import json

    real = bots._INSTANCES_ROOT
    bots._INSTANCES_ROOT = tmp_path
    bots._REGISTRY_SIG = None

    def make(key, **body):
        d = tmp_path / key
        d.mkdir(parents=True, exist_ok=True)
        (d / "config.json").write_text(json.dumps({"bot_key": key, **body}))
        return d

    yield make
    bots._INSTANCES_ROOT = real
    bots._REGISTRY_SIG = None
    bots._refresh_bots()


def test_the_list_is_the_bot_folders_and_nothing_else(bot_folders, tmp_path):
    """A folder holding a config IS a bot; a folder without one is not.
    MUTATION: drop the config-file test in `_discover_bots` -> red."""
    bot_folders("b_bot", display_name="B", account=None)
    bot_folders("a_bot", display_name="A", account=None)
    (tmp_path / "left_behind").mkdir()
    (tmp_path / "Bad-Name").mkdir()
    (tmp_path / "Bad-Name" / "config.json").write_text("{}")

    bots._refresh_bots()
    assert [b.key for b in bots._BOTS] == ["a_bot", "b_bot"]
    assert bots._KEY_DISPLAY == {"a_bot": "A", "b_bot": "B"}
    assert bots._BOT_INSTANCE_MAP["a_bot"]["path"] == tmp_path / "a_bot" / "config.json"
    assert [s for s, _ in bots._BOT_STATE_SECTIONS] == ["state_a_bot", "state_b_bot"]


def test_a_new_folder_shows_up_on_the_NEXT_request_with_no_restart(bot_folders, client):
    """The feature a copy of a bot needs: made from this page, listed on the next request.
    MUTATION: drop the router's `_current_bots` dependency -> red."""
    bot_folders("a_bot", account=None)
    assert [b["key"] for b in client.get("/bots/accounts").json()[0]["bots"]] == ["a_bot"]

    bot_folders("b_bot", account=None)
    keys = {b["key"] for g in client.get("/bots/accounts").json() for b in g["bots"]}
    assert keys == {"a_bot", "b_bot"}


def test_an_unchanged_tree_is_not_rebuilt(bot_folders):
    """A directory listing per request, and nothing more unless something moved — the maps keep
    their identity. MUTATION: rebuild unconditionally -> red."""
    bot_folders("a_bot", account=None)
    bots._refresh_bots()
    first = bots._BOTS[0]
    bots._refresh_bots()
    assert bots._BOTS[0] is first


def test_a_folder_that_cannot_be_listed_is_a_503_never_an_empty_page(bot_folders, tmp_path):
    """A Bots page with no bots on it reads as "you have no bots" — the confident wrong answer.
    MUTATION: swallow the OSError and return an empty list -> red."""
    bots._INSTANCES_ROOT = tmp_path / "missing"
    bots._REGISTRY_SIG = None
    with pytest.raises(bots.HTTPException) as e:
        bots._refresh_bots()
    assert e.value.status_code == 503
    assert "missing" in e.value.detail


def test_an_unclassifiable_account_is_labelled_LIVE_and_a_benched_bot_demo(
    bot_folders, monkeypatch
):
    """The fallback `_account_type_of` uses when the account list cannot be read: under-reporting
    real money is the failure that label exists to prevent. MUTATION: default to demo -> red."""
    monkeypatch.setattr(bots, "_account_kinds_now", lambda: {1: "demo"})
    bot_folders("benched", account=None)
    bot_folders("known_demo", account=1)
    bot_folders("unknown", account=999)
    bots._refresh_bots()
    kinds = {b.key: b.account_type for b in bots._BOTS}
    assert kinds == {"benched": "demo", "known_demo": "demo", "unknown": "live"}
