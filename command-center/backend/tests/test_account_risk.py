"""An account's risk budget — ONE planner for every write that can move it (2026-09-11).

Aaron: *"I should be able to add bots to demo and live accounts … take bots off … increase or lower
the percentage risk on the bot … increase or lower the max percentage traded on the account … all
this stuff seamlessly."* Three writes each carried their own copy of the share-vs-cap check, and
every copy refused an IMPROVEMENT: lowering a share on an account still over its cap was refused
because the RESULT was still over, which made such an account unfixable one step at a time.

**The rule now: a write is refused only when the result does not fit AND the write adds risk.**

⚠ A fail-watch against HEAD is vacuous for the planner — it did not exist — so non-vacuity is by
MUTATION (`python3 -m scripts.testing.mutate`), named in each docstring. The two endpoint defects
this replaces (runtime and cap refusing an improvement) WERE watched red against HEAD.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from services import bot_accounts as ba

ACCOUNT = 700152905


def _bot(key, risk, *, unreadable=False):
    return ba.AccountBot(
        key=key,
        display=key.upper(),
        symbol="XAUUSD.p",
        magic=1,
        strategy_package="sos_fade",
        risk_pct=risk,
        unreadable=unreadable,
    )


def _group(*bots, cap=10.0, agrees=True):
    g = ba.AccountGroup(account=ACCOUNT, server="PUPrime-Demo", kind="account")
    g.bots = list(bots)
    g.risk_cap_pct = cap if agrees else None
    g.cap_agrees = agrees
    return g


# ── the planner ────────────────────────────────────────────────────────────────
def test_LOWERING_a_share_on_an_account_still_over_is_allowed():
    """🔴 The defect this planner exists for. 5 + 5 + 5 under a 10% cap is over; lowering one to 4
    leaves it over (14%) and is still the right direction. MUTATION: make `refusal` return `reason`
    whether or not the write adds risk → red."""
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5), _bot("c", 5)), {"a": 4.0})
    assert plan.reason is not None, "the premise: the result is still over the cap"
    assert plan.refusal is None


def test_RAISING_a_share_past_the_room_is_refused():
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5)), {"a": 6.0})
    assert plan.refusal and "add up to" in plan.refusal


def test_RAISING_the_cap_on_an_account_still_over_is_allowed():
    """MUTATION: count every cap change as coming down → red."""
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5), _bot("c", 5)), cap_set=True, cap=12.0)
    assert plan.reason is not None, "the premise: 15% is still over a 12% cap"
    assert plan.refusal is None
    assert plan.cap_changed


def test_LOWERING_the_cap_under_the_shares_is_refused():
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5)), cap_set=True, cap=8.0)
    assert plan.refusal and "add up to" in plan.refusal


def test_a_cap_APPEARING_on_an_uncapped_account_counts_as_coming_down():
    """Uncapped holds anything, so a first cap under the shares refuses trades that were allowed.
    MUTATION: drop `old_cap is None` from `cap_lowered` → it saves → red."""
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5), cap=None), cap_set=True, cap=8.0)
    assert plan.refusal


def test_an_UNSTATED_share_becoming_a_number_counts_as_RAISED():
    """Nothing measured says an unstated share went DOWN. MUTATION: drop the `before is None`
    branch → an overflowing first share saves → red."""
    plan = ba.risk_plan(_group(_bot("a", None), _bot("b", 8)), {"a": 5.0})
    assert plan.refusal


def test_a_JOINING_bot_always_adds_risk_and_is_never_written_by_a_budget_save():
    """MUTATION: drop `joining` from `adds_risk` → a bot joining a full account plans as savable →
    red."""
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5)), joining=[_bot("c", 5)])
    assert plan.refusal and plan.joining == ["c"]
    assert plan.changed is False, "a joining bot is written by its own move, never by a save"


def test_the_two_fixes_fit_and_never_land_a_hair_over():
    """`fit_cap` rounds UP, `fit_shares` round DOWN: 5+5+5 → cap 15, shares 3.33 each (9.99 fits a
    10% cap). MUTATION: round the shares UP → 3.34 × 3 = 10.02, over the cap → red."""
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5)), joining=[_bot("c", 5)])
    assert plan.fit_cap == 15.0
    assert plan.fit_shares == {"a": 3.33, "b": 3.33, "c": 3.33}
    fitted = [_bot(k, v) for k, v in plan.fit_shares.items()]
    assert ba.share_overflow(fitted, 10.0) is None


def test_a_cap_fix_past_100_percent_is_not_offered():
    """A cap is a percentage of the balance, so a suggestion over 100 would be refused at the save."""
    plan = ba.risk_plan(
        _group(_bot("a", 30), _bot("b", 30), cap=50.0), joining=[_bot("c", 30), _bot("d", 30)]
    )
    assert plan.reason and plan.fit_cap is None


def test_a_share_fix_below_the_floor_is_not_offered():
    """0.2% under a 0.15% cap scales to 0.075% a share, under the 0.1% the runtime editor accepts —
    so the suggestion is withheld rather than offered and refused. MUTATION: drop the floor → red."""
    plan = ba.risk_plan(_group(_bot("a", 0.1), _bot("b", 0.1), cap=0.15))
    assert plan.reason and plan.fit_shares is None


def test_an_UNREADABLE_bot_refuses_the_plan():
    """Rule 1: an unreadable share is not a share of zero."""
    with pytest.raises(ValueError, match="cannot be read"):
        ba.risk_plan(_group(_bot("a", 5), _bot("b", None, unreadable=True)), {"a": 4.0})


def test_DISAGREEING_caps_refuse_a_share_change_and_setting_ONE_cap_is_the_fix():
    g = _group(_bot("a", 5), _bot("b", 5), agrees=False)
    with pytest.raises(ValueError, match="different caps"):
        ba.risk_plan(g, {"a": 4.0})
    fixed = ba.risk_plan(g, cap_set=True, cap=10.0)
    assert fixed.refusal is None and fixed.cap_changed


def test_a_share_for_a_bot_NOT_on_the_account_is_refused():
    with pytest.raises(ValueError, match="not on account"):
        ba.risk_plan(_group(_bot("a", 5)), {"zzz": 1.0})


def test_nothing_moving_is_not_a_change():
    """MUTATION: make `changed` always True → a no-op save commits and pulls for nothing → red."""
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5)), {"a": 5.0}, cap_set=True, cap=10.0)
    assert plan.changed is False


def test_room_is_served_and_goes_NEGATIVE_when_over():
    """MUTATION: floor the room at zero → an over-subscribed account reads as a full one → red."""
    assert _group(_bot("a", 5), _bot("b", 3)).room_pct == 2.0
    assert _group(_bot("a", 5), _bot("b", 8)).room_pct == -3.0
    assert _group(_bot("a", 5), cap=None).room_pct is None


# ── the budget endpoints ───────────────────────────────────────────────────────
@pytest.fixture
def budget(monkeypatch):
    """The account's two bots at 5% under a 10% cap — the live pairing's shape — and every write
    captured, so no test reaches an instance config or the box."""
    from routers import bots as r

    configs = {
        "sos_fade_demo": {
            "account": ACCOUNT,
            "account_risk_cap_pct": 10.0,
            "strategy_params": {"exec_risk_pct": 5.0},
        },
        "extreme_leg_demo": {
            "account": ACCOUNT,
            "account_risk_cap_pct": 10.0,
            "strategy_params": {"exec_risk_pct": 5.0},
        },
        "b_leg_demo": {
            "account": None,
            "account_risk_cap_pct": None,
            "strategy_params": {"exec_risk_pct": 5.0},
        },
    }
    out = SimpleNamespace(r=r, written={}, commits=[], notes=[])
    monkeypatch.setattr(
        r,
        "_account_groups",
        lambda: [_group(_bot("sos_fade_demo", 5.0), _bot("extreme_leg_demo", 5.0))],
    )
    monkeypatch.setattr(r, "_read_instance_config", lambda k: copy.deepcopy(configs[k]))
    monkeypatch.setattr(r, "_write_instance_config", lambda k, d: out.written.__setitem__(k, d))
    monkeypatch.setattr(
        r, "_git_commit_push", lambda paths, msg, reason: out.commits.append((list(paths), msg))
    )
    monkeypatch.setattr(r, "_ssh", lambda cmd: "Already up to date.")
    monkeypatch.setattr(r, "_notify_telegram", lambda *a, **k: out.notes.append(a))
    return out


def test_ONE_save_writes_every_share_AND_the_cap_in_ONE_commit(client, budget):
    """MUTATION: skip the cap write when a share also moved → red on the cap assertion."""
    r = client.patch(
        f"/bots/accounts/{ACCOUNT}/risk",
        json={"risk_cap_pct": 15.0, "shares": {"sos_fade_demo": 7.5, "extreme_leg_demo": 7.5}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["changed"] and body["deployed"] is True
    assert sorted(body["written"]) == ["extreme_leg_demo", "sos_fade_demo"]
    assert budget.written["sos_fade_demo"]["strategy_params"]["exec_risk_pct"] == 7.5
    assert budget.written["extreme_leg_demo"]["account_risk_cap_pct"] == 15.0
    assert len(budget.commits) == 1 and len(budget.commits[0][0]) == 2
    assert "no restart" in body["applies"]


def test_a_save_that_ADDS_risk_past_the_cap_is_refused_and_writes_NOTHING(client, budget):
    r = client.patch(f"/bots/accounts/{ACCOUNT}/risk", json={"shares": {"sos_fade_demo": 8.0}})
    assert r.status_code == 409 and "add up to" in r.json()["detail"]
    assert budget.written == {} and budget.commits == []


def test_a_save_that_changes_nothing_commits_nothing(client, budget):
    r = client.patch(
        f"/bots/accounts/{ACCOUNT}/risk",
        json={"shares": {"sos_fade_demo": 5.0}, "risk_cap_pct": 10.0},
    )
    assert r.status_code == 200 and r.json()["changed"] is False
    assert budget.commits == [] and budget.written == {}


def test_the_PLAN_writes_nothing_and_serves_both_fixes_for_a_JOINING_bot(client, budget):
    """The Add bot preview. MUTATION: ignore `joining` in the plan endpoint → it answers "fits" for
    a bot that does not → red."""
    r = client.post(f"/bots/accounts/{ACCOUNT}/risk-plan", json={"joining": {"b_leg_demo": 5.0}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fits"] is False and body["refused"]
    assert body["fit_cap"] == 15.0 and body["fit_shares"]["b_leg_demo"] == 3.33
    assert [b["key"] for b in body["bots"] if b["joining"]] == ["b_leg_demo"]
    assert budget.written == {} and budget.commits == []


def test_the_SAVE_refuses_a_joining_bot(client, budget):
    r = client.patch(f"/bots/accounts/{ACCOUNT}/risk", json={"joining": {"b_leg_demo": 1.0}})
    assert r.status_code == 400
    assert budget.written == {}


def test_a_share_outside_the_runtime_bounds_is_refused_by_the_SAME_rule(client, budget):
    r = client.patch(f"/bots/accounts/{ACCOUNT}/risk", json={"shares": {"sos_fade_demo": 50.0}})
    assert r.status_code == 400 and "between" in r.json()["detail"]


def test_the_RUNTIME_editor_lets_a_share_come_DOWN_on_an_account_still_over(client, monkeypatch):
    """🔴 Watched RED against HEAD — the old check refused 4% on a 5+5+5 account under 10%.
    MUTATION: restore `share_overflow` on the proposed list in `save_bot_runtime` → red."""
    from routers import bots as r

    monkeypatch.setattr(
        r,
        "_account_groups",
        lambda: [_group(_bot("sos_fade_demo", 5), _bot("b", 5), _bot("c", 5))],
    )
    written = []
    monkeypatch.setattr(r, "_write_instance_config", lambda k, d: written.append(k))
    resp = client.patch(
        "/bots/sos_fade_demo/runtime", json={"values": {"exec_risk_pct": 4.0}, "deploy": False}
    )
    assert resp.status_code == 200, resp.text
    assert written == ["sos_fade_demo"]


def test_the_CAP_editor_lets_a_cap_go_UP_on_an_account_still_over(client, monkeypatch):
    """🔴 Watched RED against HEAD — 12% on a 15% account was refused although it frees room.
    It also says the cap needs NO restart, which the test beneath pins to the bot side."""
    from routers import bots as r

    monkeypatch.setattr(
        r,
        "_account_groups",
        lambda: [
            _group(_bot("sos_fade_demo", 5), _bot("extreme_leg_demo", 5), _bot("b_leg_demo", 5))
        ],
    )
    monkeypatch.setattr(
        r, "_read_instance_config", lambda k: {"account": ACCOUNT, "account_risk_cap_pct": 10.0}
    )
    written = []
    monkeypatch.setattr(r, "_write_instance_config", lambda k, d: written.append(k))
    resp = client.patch(
        f"/bots/accounts/{ACCOUNT}/risk-cap", json={"risk_cap_pct": 12.0, "deploy": False}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["restart_required"] is False
    assert "no restart" in resp.json()["applies"]
    assert len(written) == 3


def test_the_no_restart_claim_is_PINNED_to_the_bot_side():
    """The cap endpoint and the budget save both tell the reader a cap change needs no restart — a
    claim about `algos/live`. READ, never imported (the subsystems may not import each other).
    MUTATION (in a throwaway worktree, since this reads a file): take the cap out of
    `RUNTIME_RELOADABLE_ACCOUNT` → red."""
    src = (Path(__file__).resolve().parents[3] / "algos" / "live" / "live_config.py").read_text(
        encoding="utf-8"
    )
    m = re.search(r"^RUNTIME_RELOADABLE_ACCOUNT\s*=\s*frozenset\(\{([^}]*)\}\)", src, re.M)
    assert m, "the constant moved or was renamed — the Bots page's no-restart claim lost its anchor"
    assert '"account_risk_cap_pct"' in m.group(1)


# ── the move, and start ────────────────────────────────────────────────────────
def _stub_move(monkeypatch, *, kind="demo", running=False, groups=None):
    """Everything the move asks before it plans, answered without the box. The registered account
    is a stub so a new required field on the real one cannot change what these cases test."""
    from routers import bots as r

    reg = SimpleNamespace(
        server="PUPrime-Live" if kind == "live" else "PUPrime-Demo",
        mt5_path=r"C:\MT5_Scalper\terminal64.exe",
        account_profile="puprime_ecn",
        symbol_suffix=".p",
        assignable=True,
        unassignable_reason="",
        kind=kind,
    )
    monkeypatch.setattr(r, "_bot_running_state", lambda key: running)
    monkeypatch.setattr(r, "_accounts_with_a_password", lambda: {ACCOUNT})
    monkeypatch.setattr(r, "_account_groups", lambda: groups or [])
    monkeypatch.setattr(r.bot_account_registry, "account_by_number", lambda path, n: reg)
    written = {}
    monkeypatch.setattr(r, "_write_instance_config", lambda k, d: written.__setitem__(k, d))
    return r, written


def test_a_move_onto_a_LIVE_account_needs_its_confirmation(client, monkeypatch):
    """🔴 The one-bot move had no guard while the whole-set move to live needs a typed phrase.
    MUTATION: drop the `confirm_live` check → the move is written without it → red."""
    _, written = _stub_move(monkeypatch, kind="live")
    refused = client.patch("/bots/b_leg_demo/account", json={"account": ACCOUNT, "deploy": False})
    assert refused.status_code == 409 and "LIVE" in refused.json()["detail"]
    assert written == {}
    ok = client.patch(
        "/bots/b_leg_demo/account",
        json={"account": ACCOUNT, "confirm_live": True, "deploy": False},
    )
    assert ok.status_code == 200, ok.text
    assert list(written) == ["b_leg_demo"]


def test_a_move_onto_a_DEMO_account_needs_no_confirmation(client, monkeypatch):
    """The control: a confirmation on every move is one people learn to click through."""
    _, written = _stub_move(monkeypatch, kind="demo")
    ok = client.patch("/bots/b_leg_demo/account", json={"account": ACCOUNT, "deploy": False})
    assert ok.status_code == 200, ok.text
    assert list(written) == ["b_leg_demo"]


def test_a_move_WRITES_the_share_it_carries_and_COUNTS_it_in_the_join_check(client, monkeypatch):
    """b_leg_demo states 10% of its own; joining a 5% bot under a 10% cap at that share is over, at
    5% it fits exactly. MUTATION: ignore `risk_pct` in the joining hypothetical → the 5% move is
    refused → red. MUTATION: drop the write → the stored share stays 10 → red."""
    full = _group(_bot("sos_fade_demo", 5.0))
    _, written = _stub_move(monkeypatch, groups=[full])
    over = client.patch("/bots/b_leg_demo/account", json={"account": ACCOUNT, "deploy": False})
    assert over.status_code == 409 and "add up to" in over.json()["detail"], over.text
    fits = client.patch(
        "/bots/b_leg_demo/account", json={"account": ACCOUNT, "risk_pct": 5.0, "deploy": False}
    )
    assert fits.status_code == 200, fits.text
    assert written["b_leg_demo"]["strategy_params"]["exec_risk_pct"] == 5.0


def test_an_UNANSWERED_running_check_is_a_503_never_running(client, monkeypatch):
    """🔴 *Could not ask* read as RUNNING told the reader to stop a bot that was already stopped.
    MUTATION: read `None` as running again → it answers 409 "is running" → red."""
    _stub_move(monkeypatch, running=None)
    resp = client.patch("/bots/b_leg_demo/account", json={"account": ACCOUNT})
    assert resp.status_code == 503 and "did not answer" in resp.json()["detail"]


def test_the_STOP_path_still_reads_an_unanswered_check_as_running(monkeypatch):
    """The other half, which must NOT move: the stop path escalates on *cannot ask*, because
    reporting a live bot as stopped is the one wrong answer that costs money."""
    from routers import bots as r

    monkeypatch.setattr(r, "_bot_running_state", lambda key: None)
    assert r._bot_is_running("sos_fade_demo") is True


@pytest.mark.parametrize("action", ["start", "restart"])
def test_START_and_RESTART_refuse_a_bot_on_NO_account(client, monkeypatch, action):
    """🔴 It answered 200 and sent STARTING to Telegram over a bot the box then refused. MUTATION:
    drop `_refuse_if_benched` from the endpoint → the launch fires → red."""
    from routers import bots as r

    launched = []
    monkeypatch.setattr(r, "_launch_bot", lambda k: launched.append(k) or "ok")
    monkeypatch.setattr(r, "_kill_bot", lambda k: "stopped")
    monkeypatch.setattr(r, "_suppress_stop_alert", lambda k: None)
    monkeypatch.setattr(r._time, "sleep", lambda s: None)
    monkeypatch.setattr(r, "_notify_telegram", lambda *a, **k: None)
    monkeypatch.setattr(r, "_read_instance_config", lambda k: {"account": None})
    resp = client.post(f"/bots/b_leg_demo/{action}")
    assert resp.status_code == 409 and "not on an account" in resp.json()["detail"]
    assert launched == []
    monkeypatch.setattr(r, "_read_instance_config", lambda k: {"account": ACCOUNT})
    ok = client.post(f"/bots/b_leg_demo/{action}")
    assert ok.status_code == 200, ok.text
    assert launched == ["b_leg_demo"]
