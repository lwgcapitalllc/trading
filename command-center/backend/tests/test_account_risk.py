"""An account's risk budget — ONE planner for every write that can move it (2026-09-11).

🔴 **2026-09-15: shares that ADD UP past the cap are no longer refused** — they share the room, and
the plan carries a `note` saying so. The planner now refuses only an unreadable share or ONE bot
above the whole cap, and every case below that used a sum as its refusal now uses a share above
the cap. The same file also carries the account PRIORITY route.

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
def test_LOWERING_a_share_that_is_still_above_the_cap_is_allowed():
    """🔴 The defect this planner exists for: a change that frees room is always allowed. A 15%
    bot under a 10% cap, lowered to 12%, is still above it and still the right direction.
    MUTATION: make `refusal` return `reason` whether or not the write adds risk → red."""
    plan = ba.risk_plan(_group(_bot("a", 15), _bot("b", 5)), {"a": 12.0})
    assert plan.reason is not None, "the premise: the result is still above the cap"
    assert plan.refusal is None


def test_RAISING_a_share_past_the_ROOM_is_allowed_and_SAYS_the_bots_share_it():
    """🔴 2026-09-15: 6 + 5 under 10 shares the room — never refused, always said.
    MUTATION: restore the sum refusal → red. MUTATION: drop the note → red."""
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5)), {"a": 6.0})
    assert plan.refusal is None and plan.fits
    assert plan.note and "11%" in plan.note and "share the room" in plan.note


def test_RAISING_a_share_ABOVE_the_cap_is_refused():
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5)), {"a": 11.0})
    assert plan.refusal and "full size" in plan.refusal
    assert plan.note is None, "a refused plan says the refusal, not the note"


def test_RAISING_the_cap_while_a_share_is_still_above_it_is_allowed():
    """MUTATION: count every cap change as coming down → red."""
    plan = ba.risk_plan(_group(_bot("a", 15), _bot("b", 5)), cap_set=True, cap=12.0)
    assert plan.reason is not None, "the premise: 15% is still above a 12% cap"
    assert plan.refusal is None
    assert plan.cap_changed


def test_LOWERING_the_cap_under_ONE_share_is_refused_and_under_the_SUM_is_not():
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5)), cap_set=True, cap=4.0)
    assert plan.refusal and "full size" in plan.refusal
    shared = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5)), cap_set=True, cap=8.0)
    assert shared.refusal is None and shared.note


def test_a_cap_APPEARING_on_an_uncapped_account_counts_as_coming_down():
    """Uncapped holds anything, so a first cap under a share refuses trades that were allowed.
    MUTATION: drop `old_cap is None` from `cap_lowered` → it saves → red."""
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5), cap=None), cap_set=True, cap=4.0)
    assert plan.refusal


def test_an_UNSTATED_share_becoming_a_number_counts_as_RAISED():
    """Nothing measured says an unstated share went DOWN. MUTATION: drop the `before is None`
    branch → a first share above the cap saves → red."""
    plan = ba.risk_plan(_group(_bot("a", None), _bot("b", 8)), {"a": 12.0})
    assert plan.refusal


def test_a_JOINING_bot_always_adds_risk_and_is_never_written_by_a_budget_save():
    """MUTATION: drop `joining` from `adds_risk` → a bot above the cap plans as savable → red."""
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5)), joining=[_bot("c", 12)])
    assert plan.refusal and plan.joining == ["c"]
    assert plan.changed is False, "a joining bot is written by its own move, never by a save"


def test_a_THIRD_bot_joining_a_FULL_account_fits_and_shares_the_room():
    """🔴 The case Aaron asked about, allowed since 2026-09-15."""
    plan = ba.risk_plan(_group(_bot("a", 5), _bot("b", 5)), joining=[_bot("c", 5)])
    assert plan.fits and plan.refusal is None
    assert "15%" in plan.note


def test_the_two_fixes_bring_ONLY_the_share_above_the_cap_and_never_land_a_hair_over():
    """`fit_cap` is the largest share rounded UP; `fit_shares` brings each share above the cap DOWN
    to it and leaves the rest exactly as they are. MUTATION: scale every share → a changes → red."""
    plan = ba.risk_plan(_group(_bot("a", 3.333), _bot("b", 5)), joining=[_bot("c", 12.5)])
    assert plan.fit_cap == 12.5
    assert plan.fit_shares == {"a": 3.333, "b": 5.0, "c": 10.0}
    fitted = [_bot(k, v) for k, v in plan.fit_shares.items()]
    assert ba.share_overflow(fitted, 10.0) is None


def test_a_cap_fix_past_100_percent_is_not_offered():
    """A cap is a percentage of the balance, so a suggestion over 100 would be refused at the save."""
    plan = ba.risk_plan(_group(_bot("a", 30), cap=50.0), joining=[_bot("c", 120)])
    assert plan.reason and plan.fit_cap is None


def test_a_share_fix_below_the_floor_is_not_offered():
    """A 0.05% cap would bring a 0.2% share to 0.05%, under the 0.1% the runtime editor accepts —
    so the suggestion is withheld rather than offered and refused. MUTATION: drop the floor → red."""
    plan = ba.risk_plan(_group(_bot("a", 0.2), cap=0.05))
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
    out.routed = []
    monkeypatch.setattr(
        r,
        "_notify_telegram",
        lambda *a, **k: out.notes.append(a) or out.routed.append(k.get("account")),
    )
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


def test_the_risk_alert_lands_in_THAT_accounts_room(client, budget):
    """Each account may name its own health channel (2026-09-13); a risk change on one owner's
    account is news for that owner. MUTATION: drop `account=account` from the RISK CHANGED call
    -> red."""
    r = client.patch(f"/bots/accounts/{ACCOUNT}/risk", json={"shares": {"sos_fade_demo": 4.0}})
    assert r.status_code == 200, r.text
    assert budget.routed == [ACCOUNT]


def test_a_save_that_puts_a_share_ABOVE_the_cap_is_refused_and_writes_NOTHING(client, budget):
    r = client.patch(f"/bots/accounts/{ACCOUNT}/risk", json={"shares": {"sos_fade_demo": 12.0}})
    assert r.status_code == 409 and "full size" in r.json()["detail"]
    assert budget.written == {} and budget.commits == []


def test_a_save_that_only_makes_the_shares_ADD_UP_past_the_cap_is_written(client, budget):
    """🔴 2026-09-15. MUTATION: restore the sum refusal → 409 → red."""
    r = client.patch(f"/bots/accounts/{ACCOUNT}/risk", json={"shares": {"sos_fade_demo": 8.0}})
    assert r.status_code == 200, r.text
    assert budget.written["sos_fade_demo"]["strategy_params"]["exec_risk_pct"] == 8.0
    assert "share the room" in r.json()["note"]


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
    r = client.post(f"/bots/accounts/{ACCOUNT}/risk-plan", json={"joining": {"b_leg_demo": 12.0}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fits"] is False and body["refused"]
    assert body["fit_cap"] == 12.0 and body["fit_shares"]["b_leg_demo"] == 10.0
    assert [b["key"] for b in body["bots"] if b["joining"]] == ["b_leg_demo"]
    assert budget.written == {} and budget.commits == []


def test_the_PLAN_serves_the_SHARING_note_for_a_bot_that_fills_a_full_account(client, budget):
    """MUTATION: drop `note` from the plan view → red."""
    r = client.post(f"/bots/accounts/{ACCOUNT}/risk-plan", json={"joining": {"b_leg_demo": 5.0}})
    body = r.json()
    assert body["fits"] is True and body["refused"] is None
    assert "15%" in body["note"] and "priority" in body["note"]


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


# ── the PRIORITY order (2026-09-15) ────────────────────────────────────────────
def test_the_PRIORITY_save_writes_ranks_1_to_n_in_ONE_commit(client, budget):
    """The order as listed, first = 1, through the risk save's own write → commit → pull path.
    MUTATION: number from 0 → red. MUTATION: skip the commit → red. MUTATION: drop
    `account=account` from the alert → the wrong room → red."""
    r = client.put(
        f"/bots/accounts/{ACCOUNT}/priority", json={"order": ["extreme_leg_demo", "sos_fade_demo"]}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["changed"] and body["deployed"] is True
    assert body["order"] == ["extreme_leg_demo", "sos_fade_demo"]
    assert budget.written["extreme_leg_demo"]["account_priority"] == 1
    assert budget.written["sos_fade_demo"]["account_priority"] == 2
    assert len(budget.commits) == 1 and len(budget.commits[0][0]) == 2
    assert budget.routed == [ACCOUNT]
    assert "no restart" in body["applies"]


@pytest.mark.parametrize(
    "order, words",
    [
        (["sos_fade_demo"], "missing"),
        (["sos_fade_demo", "extreme_leg_demo", "b_leg_demo"], "not on account"),
        (["sos_fade_demo", "sos_fade_demo", "extreme_leg_demo"], "twice"),
    ],
)
def test_an_order_that_is_not_EXACTLY_the_accounts_bots_is_refused_and_writes_NOTHING(
    client, budget, order, words
):
    """A partial order leaves a bot holding a rank nobody chose. MUTATION: drop each of the three
    checks in `priority_order_plan` → its case goes 200 → red."""
    r = client.put(f"/bots/accounts/{ACCOUNT}/priority", json={"order": order})
    assert r.status_code == 400 and words in r.json()["detail"], r.text
    assert budget.written == {} and budget.commits == []


def test_an_UNREADABLE_config_anywhere_refuses_the_priority_write(client, budget, monkeypatch):
    """It might be on this account, so the order could not be known to be complete (rule 1).
    MUTATION: ignore the unreadable bucket → 200 and written → red."""
    broken = ba.AccountGroup(account=None, server="", kind="unknown")
    broken.bots = [_bot("broken", None, unreadable=True)]
    monkeypatch.setattr(
        budget.r,
        "_account_groups",
        lambda: [_group(_bot("sos_fade_demo", 5.0), _bot("extreme_leg_demo", 5.0)), broken],
    )
    r = client.put(
        f"/bots/accounts/{ACCOUNT}/priority", json={"order": ["sos_fade_demo", "extreme_leg_demo"]}
    )
    assert r.status_code == 409 and "broken" in r.json()["detail"], r.text
    assert budget.written == {} and budget.commits == []


def test_an_order_the_bots_already_hold_commits_nothing(client, budget, monkeypatch):
    """MUTATION: write every bot regardless → a commit and a pull for nothing → red."""
    held = {
        "sos_fade_demo": {"account": ACCOUNT, "account_priority": 1},
        "extreme_leg_demo": {"account": ACCOUNT, "account_priority": 2},
    }
    monkeypatch.setattr(budget.r, "_read_instance_config", lambda k: copy.deepcopy(held[k]))
    r = client.put(
        f"/bots/accounts/{ACCOUNT}/priority", json={"order": ["sos_fade_demo", "extreme_leg_demo"]}
    )
    assert r.status_code == 200 and r.json()["changed"] is False
    assert budget.written == {} and budget.commits == []


def test_a_priority_order_for_an_account_with_no_bots_is_a_404(client, budget):
    r = client.put("/bots/accounts/12345/priority", json={"order": []})
    assert r.status_code == 404


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
        # A live account that names its Telegram channels, i.e. one that is READY to receive a
        # bot. ⚠ Defaulted rather than left off: an account with no channels is refused outright
        # since 2026-09-13, so omitting this would make every case here pass for the wrong reason.
        # The missing-channel case has its own test, which sets a reason.
        missing_channels=[],
        channels_reason="",
        kind=kind,
    )
    monkeypatch.setattr(r, "_bot_running_state", lambda key: running)
    monkeypatch.setattr(r, "_holds_position", lambda key: False)
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
    """b_leg_demo states 10% of its own; under a 4% cap that is above the whole cap, at 4% it fits
    exactly. MUTATION: ignore `risk_pct` in the joining hypothetical → the 4% move is refused →
    red. MUTATION: drop the write → the stored share stays 10 → red."""
    full = _group(_bot("sos_fade_demo", 3.0), cap=4.0)
    _, written = _stub_move(monkeypatch, groups=[full])
    over = client.patch("/bots/b_leg_demo/account", json={"account": ACCOUNT, "deploy": False})
    assert over.status_code == 409 and "full size" in over.json()["detail"], over.text
    fits = client.patch(
        "/bots/b_leg_demo/account", json={"account": ACCOUNT, "risk_pct": 4.0, "deploy": False}
    )
    assert fits.status_code == 200, fits.text
    assert written["b_leg_demo"]["strategy_params"]["exec_risk_pct"] == 4.0


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


# ── putting a bot on an account DEPLOYS it, and leaves it stopped (2026-09-16) ──
#
# 🔴 Aaron, 2026-09-16: *"If I put bots on an account, shouldn't they be deployed immediately? But
# just remains off until I start them?"* A bot on an account with no frozen snapshot imports from
# the trading box's WORKING TREE, so a pull there changes what it trades with nobody deploying
# anything — the state two bots were left in for a day, behind a grey badge on every screen.


def _stub_deploy(monkeypatch, *, fails=False):
    """The box half of a real (deploying) move: the push, the pull, Telegram, and the deploy job.

    Returns the list every deploy this move starts is recorded in, as `(bot, request)`.
    """
    from routers import bots as r

    started: list[tuple] = []

    def begin(bot_key, req, take_over=None):
        if fails:
            raise ValueError(f"A deploy of {bot_key} is already running — wait for it to finish.")
        started.append((bot_key, req))
        return {"job_id": f"pj_test_{bot_key}"}

    monkeypatch.setattr(r, "_git_commit_push", lambda *a, **k: None)
    monkeypatch.setattr(r, "_ssh", lambda *a, **k: "Already up to date.")
    monkeypatch.setattr(r, "_notify_telegram", lambda *a, **k: None)
    monkeypatch.setattr(r, "_begin_promote_job", begin)
    return started


def test_putting_a_bot_ON_an_account_deploys_it_and_does_NOT_restart_it(client, monkeypatch):
    """MUTATION: drop the `_begin_promote_job` call from the move → nothing is deployed, the bot
    sits on the account importing the box's working tree, and `deploy_job` is empty → red.
    MUTATION: send `restart=True` → the move would START a bot nobody started → red."""
    _stub_move(monkeypatch)
    started = _stub_deploy(monkeypatch)
    ok = client.patch("/bots/b_leg_demo/account", json={"account": ACCOUNT})
    assert ok.status_code == 200, ok.text
    assert [b for b, _ in started] == ["b_leg_demo"]
    req = started[0][1]
    # 🔴 The half that matters: deployed, and left exactly as stopped as it was found.
    assert req.restart is False
    # The pull that put this config on the box already ran; a second is a step this did not need.
    assert req.pull is False
    assert ok.json()["deploy_job"] == "pj_test_b_leg_demo"


def test_taking_a_bot_OFF_an_account_deploys_nothing(client, monkeypatch):
    """The control. A benched bot trades nothing, so there is nothing to pin a version of — and a
    deploy here would be a box action nobody asked for. MUTATION: deploy unconditionally → red."""
    _stub_move(monkeypatch)
    started = _stub_deploy(monkeypatch)
    ok = client.patch("/bots/b_leg_demo/account", json={"account": None})
    assert ok.status_code == 200, ok.text
    assert started == []
    assert ok.json()["deploy_job"] == ""


def test_a_deploy_that_cannot_START_is_reported_and_the_move_still_stands(client, monkeypatch):
    """The move is already written when the deploy is asked for, so a failure may not be raised as
    if nothing had happened — it is NAMED instead, and the bot sits on the account undeployed.

    MUTATION: let the exception escape → a 500 over a move that is on disk, pushed and pulled →
    red. MUTATION: swallow it silently → the move reads clean while the bot cannot be started
    → red on the note."""
    _stub_move(monkeypatch)
    started = _stub_deploy(monkeypatch, fails=True)
    ok = client.patch("/bots/b_leg_demo/account", json={"account": ACCOUNT})
    assert ok.status_code == 200, ok.text
    assert started == []
    assert ok.json()["deploy_job"] == ""
    assert any("no pinned version" in n for n in ok.json()["notes"])
