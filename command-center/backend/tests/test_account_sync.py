"""Sync: what it may change on the account list, and what it must leave for a person.

Aaron, 2026-09-10: *"not a scan, a sync"*, pressed by hand only. The rules pinned here are the
ones whose failure is SILENT — every one of them produces a plausible, well-formed list:

  * an account a bot trades is never changed, even when the box plainly disagrees,
  * a terminal is only ever CLEARED, never set, and an empty one is never filled,
  * nothing is removed because the box could not see it,
  * a broker that did not say demo or live gets no row, rather than a guessed "demo",
  * an unreadable bot config blocks every write, rather than reading as "no bot trades it",
  * the write lands on the row as it is on disk NOW, not on the copy the plan was made from,
  * a Sync press applies only the plan the person was SHOWN, and writes nothing when it moved.

⚠ **A fail-watch against HEAD is VACUOUS — the module did not exist.** Non-vacuity is by MUTATION;
each test that pins a refusal names the mutation that turns it red.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from services import account_sync
from services import bot_account_registry as reg
from services.terminal_scan import reconcile

_PROFILES = {"puprime_ecn", "puprime_standard", "puprime_prime"}
TODAY = "2026-09-10"
NAMES = {"sos_fade_demo": "SOS Fade", "extreme_leg_demo": "Extreme Leg", "b_leg_demo": "B-LEG"}
BOTS = {"sos_fade_demo": 700152905, "extreme_leg_demo": 700152905, "b_leg_demo": None}


def _acct(**kw):
    base = dict(
        account=700152905,
        label="PU Prime ECN demo",
        broker="PU Prime",
        tier="ECN",
        kind="demo",
        server="PUPrime-Demo",
        mt5_path=r"C:\MT5_FFT\terminal64.exe",
        symbol_suffix=".p",
        account_profile="puprime_ecn",
    )
    base.update(kw)
    return reg.RegisteredAccount(**base)


def _fft(seen=700152905):
    """The bots' own terminal: never attached to, so its account comes from what the bots see."""
    return {
        "key": r"c:\mt5_fft",
        "install": r"C:\MT5_FFT",
        "state": "owned_by_bot",
        "running": True,
        "owned_by_bots": ["extreme_leg_demo", "sos_fade_demo"],
        "account": None,
        "reported_by_bots": {"sos_fade_demo": seen, "extreme_leg_demo": seen},
    }


def _probed(install, account, **kw):
    base = {
        "key": install.lower(),
        "install": install,
        "state": "probed",
        "running": True,
        "owned_by_bots": [],
        "account": account,
        "server": "PUPrime-Demo",
        "kind": "demo",
        "company": "PU Prime Ltd",
        "symbol_suffix": ".p",
    }
    base.update(kw)
    return base


LAB = _probed(r"C:\MT5_Lab", 700152905)
SCALPER = _probed(r"C:\MT5_Scalper", 34957946, server="PUPrime-Live", kind="live")
STOPPED = {
    "key": r"c:\program files\metatrader 5",
    "install": r"C:\Program Files\MetaTrader 5",
    "state": "not_running",
    "running": False,
    "owned_by_bots": [],
    "account": None,
}

# The list as it stood on 2026-09-10, when the screenshot was taken.
ECN = _acct()
RETIRED = _acct(account=700107749, label="PU Prime Standard demo (retired)", symbol_suffix=".s")
LIVE = _acct(
    account=34957946,
    label="Aaron Live (Smaller)",
    kind="live",
    server="PUPrime-Live",
    mt5_path=r"C:\MT5_Scalper\terminal64.exe",
)
PROBE = _acct(account=700119432, label="tier probe", mt5_path="", symbol_suffix=".s")


def _plan(terminals, rows, bots=BOTS, today=TODAY):
    payload = {
        "asked": True,
        "scanned_at": "2026-09-10T11:44:21Z",
        "terminals": [dict(t) for t in terminals],
    }
    return account_sync.plan_sync(reconcile(payload, rows), rows, bots, NAMES, today)


def _text(plan) -> str:
    """Everything the page would print for this plan — sentences AND the field-by-field rows."""
    return json.dumps(
        [c.said for c in plan.changes]
        + [account_sync.shown_diffs(c) for c in plan.changes]
        + [a.said for a in plan.attention],
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------------------
# The screenshot
# ---------------------------------------------------------------------------------------


def test_the_screenshot_the_retired_rows_stale_terminal_is_cleared_and_nothing_else_moves():
    """🔴 The case Aaron sent: the retired account claims the bots' terminal, which the bots report
    is on the ECN account. Sync clears that claim — and touches nothing else on a list that is
    otherwise right."""
    plan = _plan([_fft(), LAB, SCALPER, STOPPED], [ECN, RETIRED, LIVE, PROBE])

    assert plan.blocked is None
    assert plan.attention == []
    (change,) = plan.changes
    assert change.account == 700107749
    assert change.action == "update"
    assert change.fields == {"mt5_path": ""}
    (row,) = account_sync.shown_diffs(change)
    assert (row["what"], row["before"], row["after"]) == ("Terminal", "MT5_FFT", "none")
    assert "MT5_FFT is logged into #700152905" in row["why"]
    assert "terminal64.exe" not in _text(plan)


# ---------------------------------------------------------------------------------------
# An account a bot trades is never changed
# ---------------------------------------------------------------------------------------


def test_an_account_a_bot_trades_is_never_changed_even_when_the_box_disagrees():
    """Watched RED by treating a bot-traded account like any other: the server is rewritten on the
    account the live bots are trading."""
    plan = _plan([_fft(), dict(LAB, server="PUPrime-Demo2")], [ECN])

    assert plan.changes == []
    (att,) = plan.attention
    assert att.account == 700152905
    assert "SOS Fade" in att.said[0] and "left it alone" in att.said[0]
    assert any("PUPrime-Demo2" in s for s in att.said)


def test_a_bots_terminal_on_the_wrong_account_is_ONE_alarm_and_writes_nothing():
    """🔴 The 2026-08-12 shape: the bots' terminal is logged into an account they are not set to
    trade. Sync must SAY so and must not agree with it — and must say it once, not also as a
    wrong terminal on the bots' own row.

    Watched RED by dropping the alarm (the page says nothing about a halted bot), and by removing
    the de-duplication (two entries describing one event)."""
    plan = _plan([_fft(seen=700107749)], [ECN, RETIRED])

    assert plan.changes == []
    (att,) = plan.attention
    assert att.account == 700152905
    (said,) = att.said
    assert "MT5_FFT is logged into #700107749" in said
    assert "set to trade #700152905" in said and "stops itself" in said


# ---------------------------------------------------------------------------------------
# Adding what the box found
# ---------------------------------------------------------------------------------------


def test_a_new_account_is_added_with_what_the_box_measured_and_NO_terminal():
    """A terminal is intent — *bots may trade this account through it* — and the box cannot know
    intent. Watched RED by filling the terminal from where the account was found."""
    plan = _plan([SCALPER], [ECN])

    (change,) = plan.changes
    assert change.action == "add"
    f = change.fields
    assert f["account"] == 34957946
    assert f["mt5_path"] == ""
    assert (f["kind"], f["server"], f["symbol_suffix"]) == ("live", "PUPrime-Live", ".p")
    # the judgement fields stay a person's
    assert f["label"] == "" and f["account_profile"] == "" and f["tier"] == ""
    assert "MT5_Scalper" in f["note"]
    assert change.live is True


@pytest.mark.parametrize("kind", [None, "contest"])
def test_a_new_account_the_broker_did_not_call_demo_or_live_is_left_for_a_person(kind):
    """Guessing demo for an account that is real is how a bot gets pointed at somebody's money.
    Watched RED by defaulting the missing type to demo."""
    plan = _plan([dict(SCALPER, kind=kind)], [ECN])

    assert plan.changes == []
    (att,) = plan.attention
    assert att.account == 34957946
    assert "demo or live" in _text(plan)


def test_an_account_a_bot_trades_but_nobody_listed_is_not_added():
    """Same rule as above, from the other side: a bot trades it, so a person adds it."""
    plan = _plan([SCALPER], [ECN], bots={"sos_fade_demo": 34957946})

    assert plan.changes == []
    (att,) = plan.attention
    assert "add it by hand" in att.said[0]


# ---------------------------------------------------------------------------------------
# What sync must never do
# ---------------------------------------------------------------------------------------


def test_an_empty_terminal_is_never_filled_even_where_the_account_is_logged_in():
    """🔴 The tier probes were logged into the LAB's terminal and deliberately left with none —
    a bot pointed there trades through the terminal the backtests run on. Watched RED by filling
    an empty terminal from where the account was seen."""
    plan = _plan([_probed(r"C:\MT5_Lab", 700119432, symbol_suffix=".s")], [PROBE])

    assert plan.changes == [] and plan.attention == []


def test_nothing_is_removed_for_an_account_the_box_could_not_see():
    """A stopped terminal is 'could not ask', never 'gone'."""
    plan = _plan([STOPPED], [ECN, RETIRED, LIVE, PROBE], bots={})

    assert plan.changes == [] and plan.attention == []


def test_a_terminal_claim_is_not_cleared_on_an_unaskable_terminal():
    """Only a terminal that was ASKED and answered another account contradicts a claim."""
    plan = _plan([dict(_fft(), reported_by_bots={})], [RETIRED], bots={})

    assert plan.changes == []


# ---------------------------------------------------------------------------------------
# Broker facts on an account no bot trades
# ---------------------------------------------------------------------------------------


def test_broker_facts_are_corrected_on_an_account_no_bot_trades():
    """Server, demo-or-live and the symbol ending are the BROKER's, and the box measured them. An
    unrecorded ending is filled; a recorded one is corrected."""
    stale = _acct(
        account=34957946,
        label="Aaron Live",
        kind="demo",
        server="PUPrime-Old",
        mt5_path=r"C:\MT5_Scalper\terminal64.exe",
        symbol_suffix=None,
    )
    plan = _plan([SCALPER], [stale], bots={})

    (change,) = plan.changes
    assert change.fields == {"server": "PUPrime-Live", "kind": "live", "symbol_suffix": ".p"}
    assert change.live is True
    assert "LIVE" in _text(plan)


def test_a_live_flag_is_raised_only_by_the_change_that_made_it_live():
    """'Real money' on every later sync of a live account is how the word stops being read."""
    stale = _acct(
        account=34957946,
        kind="live",
        server="PUPrime-Old",
        mt5_path=r"C:\MT5_Scalper\terminal64.exe",
    )
    (change,) = _plan([SCALPER], [stale], bots={}).changes
    assert change.fields == {"server": "PUPrime-Live"}
    assert change.live is False


def test_two_terminals_that_disagree_about_one_account_are_not_guessed_between():
    """One login has one server; a disagreement means one reading is stale."""
    row = _acct(account=34957946, mt5_path="", server="PUPrime-Live", kind="live")
    plan = _plan(
        [SCALPER, _probed(r"C:\MT5_Lab", 34957946, server="PUPrime-Live2", kind="live")],
        [row],
        bots={},
    )

    assert plan.changes == []
    (att,) = plan.attention
    assert "different servers" in att.said[0]


# ---------------------------------------------------------------------------------------
# An unreadable bot config
# ---------------------------------------------------------------------------------------


def test_an_unreadable_bot_config_blocks_every_write_and_says_what_it_found():
    """Without every config there is no way to show an account is one no bot trades. Watched RED
    by reading an unreadable map as 'no bots': the retired row is rewritten anyway."""
    plan = _plan([_fft(), SCALPER], [RETIRED], bots=None)

    assert plan.blocked and "couldn't be read" in plan.blocked
    assert plan.changes == []
    found = _text(plan)
    assert "MT5_FFT" in found  # the stale terminal, reported rather than fixed
    assert "#34957946" in found  # the new account, reported rather than added


def test_a_refused_scan_plans_nothing_and_keeps_its_reason():
    payload = {"asked": False, "reason": "no instance directory - refusing"}
    plan = account_sync.plan_sync(reconcile(payload, [RETIRED]), [RETIRED], BOTS, NAMES, TODAY)

    assert plan.changes == [] and "refusing" in plan.blocked


# ---------------------------------------------------------------------------------------
# Applying the plan
# ---------------------------------------------------------------------------------------


@pytest.fixture
def path(tmp_path):
    p = tmp_path / "accounts.json"
    p.write_text(json.dumps({"accounts": []}), encoding="utf-8")
    return p


def test_the_write_lands_on_the_row_as_it_is_NOW_not_the_planned_copy(path):
    """The scan takes minutes. A label a person saved in that window, and the prose a human left on
    the row, must both survive. Watched RED by writing the whole planned row back."""
    reg.upsert_account(path, RETIRED, _PROFILES)
    plan = _plan([_fft()], [RETIRED])

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["accounts"][0]["_why"] = "kept for its balance history"
    path.write_text(json.dumps(raw), encoding="utf-8")
    reg.upsert_account(path, _acct(account=700107749, label="renamed meanwhile"), _PROFILES)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["accounts"][0]["_why"]  # the prose survived that write, as upsert promises

    applied, failed = account_sync.apply_sync(path, plan, _PROFILES)

    assert failed == [] and len(applied) == 1
    (row,) = json.loads(path.read_text(encoding="utf-8"))["accounts"]
    assert row["mt5_path"] == ""
    assert row["label"] == "renamed meanwhile"
    assert row["_why"] == "kept for its balance history"


def test_an_add_is_skipped_when_somebody_added_the_account_meanwhile(path):
    plan = _plan([SCALPER], [])
    reg.upsert_account(path, LIVE, _PROFILES)

    applied, failed = account_sync.apply_sync(path, plan, _PROFILES)

    assert applied == []
    (change, why) = failed[0]
    assert change.account == 34957946 and "by hand" in why
    (row,) = reg.load_accounts(path)
    assert row.label == "Aaron Live (Smaller)"


def test_a_blocked_plan_writes_nothing(path):
    reg.upsert_account(path, RETIRED, _PROFILES)
    before = path.read_text(encoding="utf-8")
    plan = _plan([_fft()], [RETIRED], bots=None)

    assert account_sync.apply_sync(path, plan, _PROFILES) == ([], [])
    assert path.read_text(encoding="utf-8") == before


def test_a_write_the_registry_refuses_is_reported_not_raised(path):
    """A symbol ending the registry will not store fails that one change, not the whole sync."""
    plan = _plan([dict(SCALPER, symbol_suffix="bad ending")], [])

    applied, failed = account_sync.apply_sync(path, plan, _PROFILES)

    assert applied == []
    assert failed and "symbol_suffix" in failed[0][1]
    assert reg.load_accounts(path) == []


def test_the_commit_message_names_every_account_it_touched():
    changes = [
        account_sync.SyncChange(700107749, "update", "", {"mt5_path": ""}, []),
        account_sync.SyncChange(34957946, "add", "", {}, []),
    ]
    msg = account_sync.commit_message(changes)
    assert "700107749 updated mt5_path" in msg and "34957946 added" in msg


# ---------------------------------------------------------------------------------------
# What the preview shows, and the fingerprint a Sync press sends back
# ---------------------------------------------------------------------------------------


def test_the_fingerprint_is_the_same_for_the_same_plan_and_moves_with_any_value():
    """The press is refused when the plan moved, so the fingerprint must move with every written
    value — and ONLY with those. Watched RED by fingerprinting the account numbers alone: a server
    that changed between preview and press would be written unseen."""
    rows = [RETIRED, _acct(account=34957946, kind="live", server="PUPrime-Old", mt5_path="")]
    a = account_sync.plan_id(_plan([_fft(), SCALPER], rows, bots={}))
    b = account_sync.plan_id(_plan([_fft(), SCALPER], rows, bots={}))
    moved = account_sync.plan_id(
        _plan([_fft(), dict(SCALPER, server="PUPrime-Live9")], rows, bots={})
    )

    assert a and a == b
    assert moved != a


def test_the_fingerprint_ignores_the_date_on_a_new_accounts_note():
    """An added account's note carries today's date. A preview read at 23:59 and a press at 00:01
    would otherwise be refused as 'the VPS changed' when nothing about the VPS did. Watched RED by
    fingerprinting the written fields (note included) instead of the listed rows."""
    before = account_sync.plan_id(_plan([SCALPER], [ECN], today="2026-09-10"))
    after = account_sync.plan_id(_plan([SCALPER], [ECN], today="2026-09-11"))

    assert before == after


def test_the_fingerprint_ignores_findings_nothing_would_write():
    """Attention is never written, so a new finding does not change what a press does."""
    quiet = account_sync.plan_id(_plan([_fft(), LAB], [RETIRED, ECN]))
    noisy = account_sync.plan_id(
        _plan([_fft(), LAB, dict(SCALPER, kind="contest")], [RETIRED, ECN])
    )

    assert quiet == noisy


def test_an_added_account_shows_as_NEW_rows_never_as_blank_values():
    """*Not in your list yet* and *in your list, blank* are different facts. Watched RED by showing
    an add's `before` as the empty string it would otherwise format to."""
    (change,) = _plan([SCALPER], [ECN]).changes
    rows = {r["what"]: r for r in account_sync.shown_diffs(change)}

    assert all(r["before"] is None for r in rows.values())
    assert rows["Server"]["after"] == "PUPrime-Live"
    assert rows["Demo or live"]["after"] == "live"
    assert rows["Instrument ending"]["after"] == ".p"
    assert "MT5_Scalper" in change.said[0] and "no terminal or password" in change.said[0]


def test_an_unrecorded_ending_reads_as_not_recorded_never_as_none():
    """Three states: unmeasured, bare symbols, a real ending. Showing an unmeasured one as "none"
    tells the reader this broker quotes bare symbols, which nobody measured."""
    stale = _acct(
        account=34957946, kind="live", server="PUPrime-Live", mt5_path="", symbol_suffix=None
    )
    (change,) = _plan([SCALPER], [stale], bots={}).changes
    (row,) = account_sync.shown_diffs(change)

    assert (row["what"], row["before"], row["after"]) == ("Instrument ending", "not recorded", ".p")


def test_nothing_the_page_prints_is_a_field_name_or_a_path():
    """Every row and sentence is read by a person. Watched RED by dropping the words map."""
    stale = _acct(
        account=34957946,
        kind="demo",
        server="PUPrime-Old",
        mt5_path=r"C:\MT5_Scalper\terminal64.exe",
        symbol_suffix=None,
    )
    text = _text(_plan([_fft(), SCALPER], [RETIRED, stale], bots={}))

    for code in ("mt5_path", "symbol_suffix", '"kind"', "terminal64", "C:\\\\"):
        assert code not in text, code


# ---------------------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------------------


@pytest.fixture
def registry(tmp_path, monkeypatch):
    from routers import bots as bots_router

    p = tmp_path / "accounts.json"
    p.write_text(json.dumps({"accounts": []}), encoding="utf-8")
    monkeypatch.setattr(bots_router, "_registry_path", lambda: p)
    return p


@pytest.fixture
def box(monkeypatch):
    """Stub the scan, the bots' configs and the deploy — the three things that reach outside."""
    from routers import bots as bots_router

    state = SimpleNamespace(
        payload={"asked": True, "scanned_at": "2026-09-10T11:44:21Z", "terminals": [_fft()]},
        groups=[
            SimpleNamespace(
                kind="account",
                account=700152905,
                bots=[
                    SimpleNamespace(key="sos_fade_demo"),
                    SimpleNamespace(key="extreme_leg_demo"),
                ],
            )
        ],
        deploys=[],
        deploy_fails=None,
    )

    def _deploy(message):
        state.deploys.append(message)
        if state.deploy_fails:
            raise HTTPException(status_code=500, detail=state.deploy_fails)

    monkeypatch.setattr(bots_router, "_scan_terminals", lambda: state.payload)
    monkeypatch.setattr(bots_router, "_account_groups", lambda: state.groups)
    monkeypatch.setattr(bots_router, "_deploy_registry", _deploy)
    monkeypatch.setattr(bots_router, "_known_profiles", lambda: _PROFILES)
    return state


_SYNC = "/bots/accounts/registry/sync"


def _preview(client) -> dict:
    r = client.get("/bots/accounts/scan")
    assert r.status_code == 200, r.text
    return r.json()


def _sync(client, **extra):
    """What the drawer does: read the preview, then press Sync on exactly that plan."""
    return client.post(_SYNC, json={"expect_plan": _preview(client)["plan_id"], **extra})


def test_the_preview_lists_exactly_what_sync_would_write_and_writes_nothing(client, registry, box):
    """🔴 Aaron, 2026-09-10: *"it doesn't show me what it is going to do before I do it."* The
    scan is the preview: the rows a press would write, field by field, with nothing written.
    Watched RED by applying the plan inside the GET."""
    reg.upsert_account(registry, RETIRED, _PROFILES)
    before = registry.read_text(encoding="utf-8")

    body = _preview(client)

    assert registry.read_text(encoding="utf-8") == before and box.deploys == []
    assert body["blocked"] is None and body["plan_id"]
    (change,) = body["changes"]
    assert change["account"] == 700107749 and change["action"] == "update"
    (diff,) = change["diffs"]
    assert (diff["what"], diff["before"], diff["after"]) == ("Terminal", "MT5_FFT", "none")
    # still the scan underneath: the terminals and the list's verdicts ride along
    assert body["terminals"] and body["registry"][0]["verdict"] == "contradicted"


def test_sync_applies_the_previewed_plan_commits_it_once_and_shows_the_list_as_it_now_is(
    client, registry, box
):
    reg.upsert_account(registry, RETIRED, _PROFILES)

    r = _sync(client)
    assert r.status_code == 200
    body = r.json()

    (row,) = reg.load_accounts(registry)
    assert row.mt5_path == ""
    assert body["plan_changed"] is False
    assert [c["account"] for c in body["changes"]] == [700107749]
    assert box.deploys and "700107749" in box.deploys[0] and len(box.deploys) == 1
    assert body["deployed"] is True
    # re-judged after the write, from the same reading: nothing left to do, no longer contradicted
    assert body["now"]["changes"] == []
    (check,) = body["now"]["registry"]
    assert check["verdict"] == "unverified"


def test_a_press_whose_plan_MOVED_since_the_preview_writes_NOTHING_and_returns_the_new_plan(
    client, registry, box
):
    """🔴 A terminal can log into another account between the preview and the press. Writing then
    applies a list nobody read — including an ADD the reader never saw. Nothing is written, and
    the new plan comes back for them to read instead. Watched RED by dropping the fingerprint
    comparison: the unseen account is added and committed."""
    reg.upsert_account(registry, RETIRED, _PROFILES)
    seen = _preview(client)

    box.payload = dict(box.payload, terminals=[_fft(), SCALPER])  # the box moved meanwhile
    before = registry.read_text(encoding="utf-8")
    body = client.post(_SYNC, json={"expect_plan": seen["plan_id"]}).json()

    assert body["plan_changed"] is True
    assert body["changes"] == [] and body["deployed"] is False and box.deploys == []
    assert registry.read_text(encoding="utf-8") == before
    assert body["now"]["plan_id"] != seen["plan_id"]
    assert sorted(c["account"] for c in body["now"]["changes"]) == [34957946, 700107749]


def test_a_press_must_name_the_plan_it_approves(client, registry, box):
    """There is no 'sync whatever you find' form of the request — a caller that skipped the
    preview has nothing to send. Watched RED by giving `expect_plan` a default."""
    reg.upsert_account(registry, RETIRED, _PROFILES)
    before = registry.read_text(encoding="utf-8")

    assert client.post(_SYNC, json={}).status_code == 422
    assert registry.read_text(encoding="utf-8") == before and box.deploys == []


def test_a_sync_with_nothing_to_change_commits_nothing(client, registry, box):
    reg.upsert_account(registry, ECN, _PROFILES)

    body = _sync(client).json()

    assert body["changes"] == [] and box.deploys == [] and body["deployed"] is False


def test_an_unreachable_box_is_a_502_and_writes_nothing(client, registry, box, monkeypatch):
    from routers import bots as bots_router
    from services import terminal_scan

    def _boom():
        raise terminal_scan.ScanUnavailable("ssh to forexvps failed and said nothing")

    monkeypatch.setattr(bots_router, "_scan_terminals", _boom)
    reg.upsert_account(registry, RETIRED, _PROFILES)
    before = registry.read_text(encoding="utf-8")

    assert client.get("/bots/accounts/scan").status_code == 502
    r = client.post(_SYNC, json={"expect_plan": "anything"})
    assert r.status_code == 502 and "said nothing" in r.json()["detail"]
    assert registry.read_text(encoding="utf-8") == before and box.deploys == []


def test_a_refused_scan_writes_nothing_and_says_why(client, registry, box):
    box.payload = {"asked": False, "reason": "no instance directory - refusing to scan"}
    reg.upsert_account(registry, RETIRED, _PROFILES)

    seen = _preview(client)
    assert seen["asked"] is False and "refusing" in seen["blocked"] and seen["changes"] == []
    body = client.post(_SYNC, json={"expect_plan": seen["plan_id"]}).json()

    assert "refusing" in body["now"]["blocked"] and body["changes"] == []
    assert reg.load_accounts(registry)[0].mt5_path == RETIRED.mt5_path


def test_an_unreadable_bot_config_blocks_the_whole_sync(client, registry, box):
    """Watched RED by skipping the unknown group: the retired row is rewritten while a bot's
    account could not be read."""
    box.groups = box.groups + [SimpleNamespace(kind="unknown", account=None, bots=[])]
    reg.upsert_account(registry, RETIRED, _PROFILES)

    body = _sync(client).json()

    assert body["now"]["blocked"] and body["changes"] == [] and box.deploys == []
    assert reg.load_accounts(registry)[0].mt5_path == RETIRED.mt5_path


def test_a_config_that_became_unreadable_after_the_preview_writes_nothing(client, registry, box):
    """The bot-trades-it rule is only true if it is checked at the moment of the write. A preview
    taken while every config read cleanly must not be applied once one stops reading — which is
    why the write re-plans rather than replaying the plan it was shown."""
    reg.upsert_account(registry, RETIRED, _PROFILES)
    seen = _preview(client)
    assert seen["changes"]

    box.groups = box.groups + [SimpleNamespace(kind="unknown", account=None, bots=[])]
    body = client.post(_SYNC, json={"expect_plan": seen["plan_id"]}).json()

    assert body["plan_changed"] is True and body["now"]["blocked"]
    assert box.deploys == [] and reg.load_accounts(registry)[0].mt5_path == RETIRED.mt5_path


def test_a_push_that_fails_keeps_the_write_and_says_it_did_not_reach_the_vps(client, registry, box):
    """A 500 here would hide what was written on this machine."""
    box.deploy_fails = "git push failed: rejected"
    reg.upsert_account(registry, RETIRED, _PROFILES)

    r = _sync(client)
    assert r.status_code == 200
    body = r.json()
    assert body["changes"] and body["deployed"] is False
    assert "rejected" in body["deploy_error"]
    assert reg.load_accounts(registry)[0].mt5_path == ""


def test_a_second_sync_while_one_is_running_is_refused(client, registry, box):
    """Two syncs would each plan against the list before the other wrote, and race one push."""
    from routers import bots as bots_router

    assert bots_router._SYNC_LOCK.acquire(blocking=False)
    try:
        r = client.post(_SYNC, json={"expect_plan": "anything"})
        assert r.status_code == 409
    finally:
        bots_router._SYNC_LOCK.release()
    assert box.deploys == []


def test_the_lock_is_released_after_a_failure(client, registry, box, monkeypatch):
    """A sync that died must not refuse every sync after it until the backend restarts."""
    from routers import bots as bots_router
    from services import terminal_scan

    def _boom():
        raise terminal_scan.ScanUnavailable("unreachable")

    monkeypatch.setattr(bots_router, "_scan_terminals", _boom)
    assert client.post(_SYNC, json={"expect_plan": "anything"}).status_code == 502
    assert bots_router._SYNC_LOCK.acquire(blocking=False)
    bots_router._SYNC_LOCK.release()
