"""Promoting a proven strategy set from its demo account onto a live one.

**The last stage, and the only write in this app that puts a strategy on real money.**

⚠ **A fail-watch against HEAD is VACUOUS for every case here** — the module did not exist — so
non-vacuity is by MUTATION, and each docstring names the mutation that turns it red.
"""

from __future__ import annotations

import json

import pytest
from services import bot_accounts
from services.bot_account_registry import RegisteredAccount
from services.go_live import confirmation_phrase, plan_go_live
from services.stack_settings_import import BotTarget

_DEMO = 700152905
_LIVE = 800345678
_DECLARED = {"exec_risk_pct", "exec_tp1_pct", "account_profile", "symbol"}


def _bot(
    key: str,
    *,
    pkg: str,
    account=_DEMO,
    account_type: str = "demo",
    running: bool = False,
    risk=5.0,
    cap=10.0,
    symbol: str = "XAUUSD.p",
    unreadable: bool = False,
) -> BotTarget:
    config = (
        None
        if unreadable
        else {
            "strategy_package": pkg,
            "account": account,
            "account_risk_cap_pct": cap,
            "symbol": symbol,
            "magic": 0,
            "strategy_params": {"exec_risk_pct": risk},
        }
    )
    return BotTarget(
        key=key,
        display=key,
        account_type=account_type,
        running=running,
        config=config,
        declared=set(_DECLARED),
    )


def _account(number=_LIVE, *, kind="live", mt5_path=r"C:\MT5_Live", suffix=".p", **kw):
    return RegisteredAccount(
        account=number,
        kind=kind,
        broker="PU Prime",
        server="PUPrime-Live",
        mt5_path=mt5_path,
        symbol_suffix=suffix,
        account_profile="pu_ecn",
        **kw,
    )


def _record(traded=True, trades=12, r=4.5):
    if not traded:
        return {
            "bot_key": "x",
            "traded": False,
            "reason": "No decision record has reached this machine for this bot yet.",
            "closed_trades": None,
            "realised_usd": None,
            "realised_r": None,
            "wins": None,
            "losses": None,
            "records_from": None,
            "records_to": None,
        }
    return {
        "bot_key": "x",
        "traded": True,
        "reason": None,
        "closed_trades": trades,
        "realised_usd": 1197.09,
        "realised_r": r,
        "wins": 8,
        "losses": 4,
        "records_from": "2026-08-01",
        "records_to": "2026-09-06",
    }


TWO_BOTS = [
    _bot("sos_fade_demo", pkg="sos_fade"),
    _bot("extreme_leg_demo", pkg="extreme_leg"),
]
# Deliberately NOT alphabetical: the planner orders its own moves, and a fixture already in
# order cannot tell a planner that sorts from one that echoes whatever it was handed.
BOTH = ["sos_fade_demo", "extreme_leg_demo"]
IN_ORDER = sorted(BOTH)

_UNSET = object()


def _plan(
    bot_keys=None,
    bots=None,
    *,
    destination=_UNSET,
    destination_group=None,
    records=None,
    assign=bot_accounts.assign_plan,
):
    bots = TWO_BOTS if bots is None else bots
    keys = BOTH if bot_keys is None else bot_keys
    return plan_go_live(
        bot_keys=keys,
        bots=bots,
        # ⚠ A SENTINEL, not `None`: `None` is a real destination here (an unregistered account)
        # and a default that swallowed it would make that case untestable.
        destination=_account() if destination is _UNSET else destination,
        destination_group=destination_group,
        records={k: _record() for k in keys} if records is None else records,
        assign=assign,
    )


def _group(account=_LIVE, bots=(), *, cap=10.0, agrees=True, unknown=False):
    return bot_accounts.AccountGroup(
        account=account,
        server="PUPrime-Live",
        kind="account",
        bots=list(bots),
        risk_cap_pct=cap,
        cap_agrees=agrees,
        cap_unknown=unknown,
    )


def _resident(key="other_live", risk=2.0, cap=10.0):
    return bot_accounts.AccountBot(
        key=key,
        display=key,
        symbol="EURUSD",
        magic=7,
        strategy_package="other",
        risk_pct=risk,
        cap_pct=cap,
    )


# ── The happy path, so every refusal below is a refusal and not a broken fixture ─────────


def test_a_clean_promotion_moves_every_bot_and_names_both_accounts():
    """PREMISE for this whole file. If this goes red the fixtures describe a set that could not
    be promoted at all, and every refusal case below passes for the wrong reason — which has now
    happened twice in this codebase, both times in a fixture rather than in a subject.
    """
    plan = _plan()
    assert plan.blocked is None
    assert [m.bot_key for m in plan.moves] == IN_ORDER
    assert plan.from_account == _DEMO and plan.to_account == _LIVE
    assert all(m.fields["account"] == _LIVE for m in plan.moves)


def test_the_move_carries_the_server_terminal_and_symbol_off_the_account_registry():
    """An account number alone is not enough to trade an account — six fields are, and each one
    has an incident behind it. This asserts they are actually in the plan rather than trusting
    that `assign_plan` was called.

    ⚠ Watched RED by dropping `registered` from the assign call.
    """
    m = _plan().moves[0]
    assert m.fields["server"] == "PUPrime-Live"
    assert m.fields["mt5_path"] == r"C:\MT5_Live"
    assert m.param_fields["account_profile"] == "pu_ecn"


# ── The destination has to BE a live account ────────────────────────────────────────────


def test_an_unregistered_destination_is_refused():
    """Nothing here would know its server, its terminal, or that it is live at all.

    ⚠ Watched RED by treating `destination=None` as an empty account.
    """
    plan = _plan(destination=None)
    assert "not registered" in plan.blocked


def test_a_DEMO_destination_is_refused_even_though_every_other_check_would_pass():
    """🔴 The account check. Moving demo→demo is an assignment; calling it a promotion writes
    the word LIVE over a change that risks nothing, and the next reader believes it.

    ⚠ **The registry is what says live, not the account number and not the bot's name.**
    ⚠ Watched RED by dropping the `kind != "live"` branch.
    """
    plan = _plan(destination=_account(kind="demo"))
    assert "only ever moves a set onto a LIVE one" in plan.blocked
    assert "demo account" in plan.blocked


def test_a_destination_with_no_terminal_logged_into_it_is_refused():
    """The bot connects by attaching to a terminal already logged into the account. Without one
    the move is written, committed, pushed and pulled, and fails at connect with a message about
    credentials — pointing the reader at the password rather than the missing terminal.

    ⚠ **It asserts WHICH rule refused.** `assign_plan` refuses an unassignable account too, so
    dropping the check here still produces a message containing "no terminal" — a loose assertion
    passes against a set-level guard that has been deleted. THIRD time this exact shape has been
    caught by mutation in this codebase.
    ⚠ Watched RED by dropping the `assignable` branch.
    """
    plan = _plan(destination=_account(mt5_path=""))
    assert "no terminal" in plan.blocked
    # ⚠ Against EVERY bot key, not one: the per-bot backstop refuses whichever bot it reaches
    # first, and naming a single key made this assertion depend on the iteration order — it was
    # still passing under the mutation for exactly that reason.
    assert not any(plan.blocked.startswith(f"{k}:") for k in BOTH)


def test_moving_a_set_onto_the_account_it_is_already_on_is_refused():
    """⚠ Watched RED by dropping the same-account branch."""
    plan = _plan(destination=_account(number=_DEMO, kind="live"))
    assert "already on account" in plan.blocked


# ── One demo set, all of it, none of it running ─────────────────────────────────────────


def test_no_bots_named_is_refused():
    """⚠ Watched RED by returning an empty plan instead of a blocked one."""
    assert "nothing to promote" in _plan(bot_keys=[]).blocked


def test_an_unregistered_bot_key_is_refused_by_name():
    """⚠ Watched RED by skipping unknown keys instead of refusing."""
    plan = _plan(bot_keys=["sos_fade_demo", "ghost"])
    assert "ghost" in plan.blocked and "not a registered bot" in plan.blocked


def test_an_unreadable_config_ANYWHERE_is_refused_before_anything_else():
    """🔴 Checked over EVERY registered bot and checked FIRST — the ordering step 7 learned the
    hard way. An unreadable config states no account, so a stranger sharing the destination is
    simply not seen, and the set lands on an account whose occupants, shares and ceiling are all
    unknown.

    ⚠ **The bot here is NOT in the promotion**, which is the whole point of the case.
    ⚠ Watched RED by narrowing the readability check to the bots being moved.
    """
    bots = TWO_BOTS + [_bot("b_leg_demo", pkg="b_leg", unreadable=True)]
    plan = _plan(bots=bots)
    assert "b_leg_demo" in plan.blocked and "could not be read" in plan.blocked


def test_a_benched_bot_in_the_set_is_refused():
    """A bot on no account has no demo record to promote and was never run with the others.

    ⚠ Watched RED by dropping the benched branch.
    """
    bots = [_bot("sos_fade_demo", pkg="sos_fade", account=None), TWO_BOTS[1]]
    plan = _plan(bots=bots)
    assert "not on an account" in plan.blocked


def test_bots_on_two_different_accounts_are_refused():
    """A set is promoted because it was proven on ONE balance under one budget.

    ⚠ Watched RED by taking the first account instead of refusing on more than one.
    """
    bots = [TWO_BOTS[0], _bot("extreme_leg_demo", pkg="extreme_leg", account=700000001)]
    plan = _plan(bots=bots)
    assert "different accounts" in plan.blocked


def test_a_bot_LEFT_BEHIND_on_the_demo_account_is_refused_not_warned():
    """🔴 What goes live is then not what was proven: the set on demo competed for one balance
    with that bot in it, so promoting a subset promotes a strategy set nothing has measured.

    ⚠ **This is a REFUSAL rather than a warning on purpose**, and it is the only check here that
    fires on a bot nobody asked to move.
    ⚠ Watched RED by demoting it to a warning.
    """
    bots = TWO_BOTS + [_bot("b_leg_demo", pkg="b_leg")]
    plan = _plan(bots=bots)
    assert plan.blocked is not None
    assert "b_leg_demo" in plan.blocked and "not what was proven" in plan.blocked


def test_a_bot_already_on_a_LIVE_account_is_refused_by_the_set_level_check():
    """Half a set that is already live was never run together on demo.

    ⚠ **It asserts WHICH rule refused.** Narrow the set-level check and this bot still gets
    refused further down, by a different rule, with a message a loose assertion would accept —
    that exact mutation survived in this file's sibling.
    ⚠ Watched RED by dropping the `account_type != "demo"` branch.
    """
    bots = [TWO_BOTS[0], _bot("extreme_leg_demo", pkg="extreme_leg", account_type="live")]
    plan = _plan(bots=bots)
    assert "not a demo-to-live promotion" in plan.blocked
    assert not plan.blocked.startswith("extreme_leg_demo:")


def test_a_RUNNING_bot_is_refused():
    """It read its config at startup, so the page would show a live account while the process
    went on trading the demo one.

    ⚠ Watched RED by dropping the running branch.
    """
    bots = [_bot("sos_fade_demo", pkg="sos_fade", running=True), TWO_BOTS[1]]
    plan = _plan(bots=bots)
    assert "is running" in plan.blocked


# ── The risk budget, which is the trap this module exists for ───────────────────────────


def test_the_set_arrives_CAPPED_at_the_budget_it_was_measured_under():
    """🔴 THE REASON THIS MODULE EXISTS. `assign_plan` writes `None` for the FIRST bot on an
    account, and every member of a set moved together looks like the first — so left alone a
    proven set lands on a live account with no ceiling at all.

    ⚠ **Every bot is written, not one**: the ceiling is stored per instance, and one left behind
    leaves the account with two of them.
    ⚠ Watched RED by removing the override and letting `assign_plan`'s `None` through.
    """
    plan = _plan()
    assert plan.cap_pct == 10.0
    assert [m.fields["account_risk_cap_pct"] for m in plan.moves] == [10.0, 10.0]


def test_the_uncapped_note_is_dropped_when_the_budget_IS_carried():
    """`assign_plan` adds "starts UNCAPPED" for the first bot on an account, and that sentence is
    false the moment the override writes a ceiling. A note contradicting the fields beside it is
    worse than no note.

    ⚠ Watched RED by keeping every note verbatim.
    """
    plan = _plan()
    assert not any("UNCAPPED" in n for m in plan.moves for n in m.notes)


def test_a_demo_account_whose_bots_DISAGREE_on_the_budget_carries_none_and_says_so():
    """Two ceilings is not a ceiling, and picking one would invent a budget nobody set.

    ⚠ Watched RED by carrying the first bot's cap when they disagree.
    """
    bots = [TWO_BOTS[0], _bot("extreme_leg_demo", pkg="extreme_leg", cap=25.0)]
    plan = _plan(bots=bots)
    assert plan.blocked is None
    assert plan.cap_pct is None
    assert any("UNCAPPED" in w for w in plan.warnings)


def test_a_populated_destination_makes_the_set_ADOPT_its_budget():
    """A live account already carrying bots has a ceiling those bots agreed on. The alternative
    is the arrivals rewriting a budget on an account they have never traded — and every bot
    already there refuses to start when the caps disagree.

    ⚠ Watched RED by always preferring the source account's cap.
    """
    plan = _plan(destination_group=_group(bots=[_resident(risk=2.0)], cap=12.0))
    assert plan.cap_pct == 12.0
    assert all(m.fields["account_risk_cap_pct"] == 12.0 for m in plan.moves)


def test_a_destination_whose_bots_disagree_on_the_budget_is_REFUSED():
    """There is no ceiling to adopt, and writing one would take every bot already trading that
    live account off the box at its next restart.

    ⚠ Watched RED by falling back to the source account's cap when the destination disagrees.
    """
    plan = _plan(destination_group=_group(bots=[_resident()], agrees=False))
    assert plan.blocked is not None and "different risk budgets" in plan.blocked


def test_a_destination_carrying_an_UNREADABLE_bot_is_refused():
    """Its budget is unknown, so there is nothing safe to adopt.

    ⚠ Watched RED by ignoring `cap_unknown`.
    """
    plan = _plan(destination_group=_group(bots=[_resident()], unknown=True))
    assert plan.blocked is not None and "could not be read" in plan.blocked


# ── The shares still have to fit, on the account as it WOULD be ─────────────────────────


def test_the_shares_are_checked_on_the_account_AFTER_the_arrival():
    """🔴 Checking the live account as it stands passes every move that over-subscribes it and
    refuses every move that would fix one — the arrivals are precisely what is not there yet.

    Two 5% legs plus a 4% resident is 14% under a 12% ceiling.
    ⚠ Watched RED by checking the destination's current bots only.
    """
    plan = _plan(destination_group=_group(bots=[_resident(risk=4.0)], cap=12.0))
    assert plan.blocked is not None and "over-subscribed" in plan.blocked


def test_an_arriving_bot_keeps_its_OWN_share_rather_than_being_resized_to_fit():
    """A promotion moves an account, not a setting. Quietly re-sizing the strategies would
    promote something other than what was proven — the refusal is the answer.

    ⚠ Watched RED by clamping each arrival's share to the room left under the cap.
    """
    bots = [
        _bot("sos_fade_demo", pkg="sos_fade", risk=9.0),
        _bot("extreme_leg_demo", pkg="extreme_leg", risk=9.0),
    ]
    plan = _plan(bots=bots)
    assert plan.blocked is not None and "over-subscribed" in plan.blocked


def test_a_resident_whose_share_cannot_be_read_REFUSES_rather_than_counting_as_zero():
    """A bot whose risk cannot be read is not a bot risking nothing — the repo's oldest rule.

    ⚠ Watched RED by treating an unstated share as 0.
    """
    plan = _plan(destination_group=_group(bots=[_resident(risk=None)]))
    assert plan.blocked is not None


# ── The demo record: reported, never enforced ───────────────────────────────────────────


def test_a_bot_that_has_NEVER_TRADED_on_demo_is_promoted_and_said_so_loudly():
    """🔴 There is no minimum record here — Aaron's call — so the record may not refuse. What it
    must do is make the absence impossible to miss, or a set goes live on a sibling's evidence.

    ⚠ **It asserts BOTH halves**: that it is not blocked, AND that a warning names the bot. A
    case asserting only the first would pass against a planner that says nothing at all.
    ⚠ Watched RED both ways — by refusing on it, and by dropping the warning.
    """
    records = {"sos_fade_demo": _record(), "extreme_leg_demo": _record(traded=False)}
    plan = _plan(records=records)
    assert plan.blocked is None
    assert any("extreme_leg_demo" in w and "NO demo evidence" in w for w in plan.warnings)


def test_a_record_that_could_not_be_read_is_NOT_reported_as_no_trades():
    """Rule 1 at the top of this repo. *Never traded* and *no record to read* are different
    answers and only one of them is a measurement.

    ⚠ Watched RED by rendering a missing record as "no trades".
    """
    records = {"sos_fade_demo": _record(), "extreme_leg_demo": {}}
    plan = _plan(records=records)
    warn = next(w for w in plan.warnings if w.startswith("extreme_leg_demo:"))
    assert "could not be read" in warn
    assert "not the same as it having done nothing" in warn


def test_a_traded_bots_record_reaches_the_reader_with_its_numbers():
    """⚠ Watched RED by summarising the record as a bare "has traded"."""
    plan = _plan()
    warn = next(w for w in plan.warnings if w.startswith("sos_fade_demo:"))
    assert "12 closed trades" in warn and "+4.50R" in warn and "2026-08-01" in warn


def test_every_bots_record_travels_on_its_own_move():
    """⚠ Watched RED by attaching one record to every move."""
    records = {"sos_fade_demo": _record(trades=3), "extreme_leg_demo": _record(trades=40)}
    plan = _plan(records=records)
    assert [m.record["closed_trades"] for m in plan.moves] == [40, 3]


# ── The typed confirmation ──────────────────────────────────────────────────────────────


def test_the_confirmation_phrase_NAMES_THE_ACCOUNT():
    """🔴 A fixed word is a reflex — typed the same way whichever preview is on screen, so it
    proves the button was pressed and nothing else. An account number can only be typed by
    somebody reading THIS preview.

    ⚠ Watched RED by returning a constant phrase.
    """
    assert confirmation_phrase(_LIVE) == f"GO LIVE {_LIVE}"
    assert confirmation_phrase(1) != confirmation_phrase(2)
    assert _plan().confirm == f"GO LIVE {_LIVE}"


# ── Warnings that do not refuse ─────────────────────────────────────────────────────────


def test_a_stranger_already_on_the_live_account_is_warned_about_not_refused():
    """Its share counts against the budget and its settings are untouched. Benching it is the
    reader's call, not this planner's.

    ⚠ Watched RED by refusing on any resident.
    """
    plan = _plan(destination_group=_group(bots=[_resident(risk=1.0)], cap=12.0))
    assert plan.blocked is None
    assert any("other_live" in w and "nothing has measured together" in w for w in plan.warnings)


def test_the_plan_says_plainly_that_nothing_is_started():
    """Every bot in the set is stopped and stays stopped. A promotion writes configs; a page that
    left that ambiguous would have somebody believe money is at risk when it is not, or the
    reverse.

    ⚠ Watched RED by dropping the closing warning.
    """
    assert any("nothing is started" in w for w in _plan().warnings)


def test_assign_plans_own_notes_survive_and_name_their_bot():
    """What could NOT be carried is the silent half: a bot pointed at a symbol its terminal does
    not quote connects, warms up, and receives no bars — which reads exactly like a quiet market.

    ⚠ Watched RED by dropping per-move notes from the warnings.
    """
    plan = _plan(destination=_account(suffix=None))
    assert any(w.startswith("sos_fade_demo:") and "no symbol suffix" in w for w in plan.warnings)


def test_a_leg_level_refusal_from_assign_plan_blocks_the_WHOLE_promotion():
    """Two of three bots on the live account is a set nobody ran, and it reads as a finished
    promotion because every bot it did move is correct.

    ⚠ Watched RED by skipping the failing bot and moving the rest.
    """

    def _boom(key, account, **kw):
        if key == "extreme_leg_demo":
            raise ValueError("nope")
        return bot_accounts.assign_plan(key, account, **kw)

    plan = _plan(assign=_boom)
    assert plan.blocked == "extreme_leg_demo: nope"
    assert not plan.moves


# ── The endpoints ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def live_env(monkeypatch, tmp_path):
    from routers import bots

    configs = {
        "sos_fade_demo": {
            "strategy_package": "sos_fade",
            "account": _DEMO,
            "account_risk_cap_pct": 10.0,
            "symbol": "XAUUSD.p",
            "magic": 1,
            "strategy_params": {"exec_risk_pct": 5.0},
        },
        "extreme_leg_demo": {
            "strategy_package": "extreme_leg",
            "account": _DEMO,
            "account_risk_cap_pct": 10.0,
            "symbol": "XAUUSD.p",
            "magic": 2,
            "strategy_params": {"exec_risk_pct": 5.0},
        },
    }
    written: dict = {}
    commits: list = []
    alerts: list = []

    class _Reg:
        def __init__(self, key):
            self.key, self.display, self.account_type = key, key, "demo"

    monkeypatch.setattr(bots, "_BY_KEY", {k: _Reg(k) for k in configs})
    monkeypatch.setattr(
        bots, "_BOT_INSTANCE_MAP", {k: {"path": tmp_path / f"{k}.json"} for k in configs}
    )
    monkeypatch.setattr(
        bots, "_read_instance_config", lambda key: json.loads(json.dumps(configs[key]))
    )
    monkeypatch.setattr(
        bots, "_write_instance_config", lambda key, data: written.__setitem__(key, data)
    )
    monkeypatch.setattr(bots, "_declared_strategy_params", lambda pkg: set(_DECLARED))
    monkeypatch.setattr(bots, "_running_bot_keys", lambda: set())
    monkeypatch.setattr(bots, "_account_groups", lambda: [])
    monkeypatch.setattr(bots, "_accounts_with_a_password", lambda: {_LIVE})
    monkeypatch.setattr(bots.bot_account_registry, "account_by_number", lambda p, n: _account(n))
    monkeypatch.setattr(bots.bot_earnings, "read_bot_ledger", lambda key: _record())
    monkeypatch.setattr(
        bots, "_git_commit_push", lambda paths, msg, reason: commits.append((paths, msg)) or "ok"
    )
    monkeypatch.setattr(bots, "_ssh", lambda cmd, **kw: "pulled")
    monkeypatch.setattr(bots, "_notify_telegram", lambda msg: alerts.append(msg))
    return {"configs": configs, "written": written, "commits": commits, "alerts": alerts}


def _body(**kw):
    return {"bots": BOTH, "account": _LIVE, **kw}


def test_the_preview_writes_nothing(client, live_env):
    """⚠ Watched RED by pointing the preview at the apply."""
    r = client.post("/bots/go-live/preview", json=_body())
    assert r.status_code == 200
    assert r.json()["blocked"] is None
    assert live_env["written"] == {} and live_env["commits"] == []


def test_a_missing_confirmation_refuses_and_the_error_names_the_phrase(client, live_env):
    """⚠ The refusal has to CARRY the phrase, or the caller is told no with no way to say yes.
    ⚠ Watched RED by dropping the confirm comparison.
    """
    r = client.post("/bots/go-live", json=_body())
    assert r.status_code == 400
    assert f"GO LIVE {_LIVE}" in r.json()["detail"]
    assert live_env["written"] == {}


def test_a_confirmation_for_a_DIFFERENT_account_is_refused(client, live_env):
    """The phrase names the destination, so one pasted from another preview cannot pass.

    ⚠ Watched RED by comparing only a fixed prefix.
    """
    r = client.post("/bots/go-live", json=_body(confirm=f"GO LIVE {_DEMO}"))
    assert r.status_code == 400
    assert live_env["written"] == {}


def test_the_apply_writes_every_bot_and_makes_ONE_commit(client, live_env):
    """⚠ A set is bots measured together; two commits is two states of the fleet, and the one in
    between was never measured.
    ⚠ Watched RED by committing per bot.
    """
    r = client.post("/bots/go-live", json=_body(confirm=f"GO LIVE {_LIVE}"))
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] is True and body["restart_required"] is True
    assert sorted(live_env["written"]) == IN_ORDER
    assert all(c["account"] == _LIVE for c in live_env["written"].values())
    assert len(live_env["commits"]) == 1
    assert len(live_env["commits"][0][0]) == 2


def test_the_apply_MERGES_strategy_params_rather_than_replacing_them(client, live_env):
    """The symbol and the cost profile move with the account; every other key in there is the
    bot's own tuning and has nothing to do with which account it is on.

    ⚠ Watched RED by assigning `param_fields` over `strategy_params`.
    """
    client.post("/bots/go-live", json=_body(confirm=f"GO LIVE {_LIVE}"))
    params = live_env["written"]["sos_fade_demo"]["strategy_params"]
    assert params["exec_risk_pct"] == 5.0
    assert params["account_profile"] == "pu_ecn"


def test_the_preview_and_the_apply_build_the_SAME_plan(client, live_env):
    """🔴 The list a human reads before authorising a live-money write has to BE the write.

    ⚠ **It asserts what was WRITTEN, not only what the two reported** — comparing responses alone
    passes against an apply that plans correctly and then writes something else.
    ⚠ Watched RED by having the apply write a subset of its own plan.
    """
    preview = client.post("/bots/go-live/preview", json=_body()).json()
    applied = client.post("/bots/go-live", json=_body(confirm=f"GO LIVE {_LIVE}")).json()

    def _shape(p):
        return sorted((m["bot"], sorted(m["fields"].items(), key=str)) for m in p["moves"])

    assert _shape(preview) == _shape(applied)
    for move in preview["moves"]:
        for name, value in move["fields"].items():
            assert live_env["written"][move["bot"]][name] == value


def test_a_definite_missing_password_refuses_before_any_write(client, live_env, monkeypatch):
    """A bot on an account with no stored password cannot log in, and finding that out after a
    commit, a push and a VPS pull is the discovery loop this page exists to remove.

    ⚠ Watched RED by dropping the password check.
    """
    from routers import bots

    monkeypatch.setattr(bots, "_accounts_with_a_password", lambda: set())
    r = client.post("/bots/go-live", json=_body(confirm=f"GO LIVE {_LIVE}"))
    assert r.status_code == 409 and "password" in r.json()["detail"]
    assert live_env["written"] == {}


def test_an_UNANSWERABLE_password_question_does_not_refuse(client, live_env, monkeypatch):
    """`None` means the box could not be asked. Refusing on it would send the reader to re-enter
    a password that is already there — the repo's rule that a definite no and an unanswered
    question are different values.

    ⚠ Watched RED by refusing on `None`.
    """
    from routers import bots

    monkeypatch.setattr(bots, "_accounts_with_a_password", lambda: None)
    r = client.post("/bots/go-live", json=_body(confirm=f"GO LIVE {_LIVE}"))
    assert r.status_code == 200


def test_a_blocked_plan_is_a_409_and_writes_nothing(client, live_env, monkeypatch):
    """⚠ Watched RED by applying a blocked plan."""
    from routers import bots

    monkeypatch.setattr(
        bots.bot_account_registry, "account_by_number", lambda p, n: _account(n, kind="demo")
    )
    r = client.post("/bots/go-live", json=_body(confirm=f"GO LIVE {_LIVE}"))
    assert r.status_code == 409
    assert live_env["written"] == {}


def test_going_live_is_ANNOUNCED_on_telegram(client, live_env):
    """The one event on this box where a config write changes whose money is at risk, and the
    person who did not press the button is the one who most needs to know.

    ⚠ Watched RED by dropping the alert.
    """
    client.post("/bots/go-live", json=_body(confirm=f"GO LIVE {_LIVE}"))
    assert len(live_env["alerts"]) == 1
    assert str(_LIVE) in live_env["alerts"][0]


# ── The demo/live label follows the ACCOUNT, not a hardcode ─────────────────────────────


def test_a_bot_on_a_LIVE_account_reports_live_even_though_the_registry_says_demo(monkeypatch):
    """🔴 `BotReg.account_type` is a hardcoded Python fact, and the moment a bot can be MOVED to
    a live account that hardcode is a second answer that drifts — in the one direction the
    registry's own comment names as dangerous.

    ⚠ Watched RED by reading `reg.account_type` directly.
    """
    from routers import bots

    monkeypatch.setattr(bots, "_registered_kinds", lambda: {_LIVE: "live", _DEMO: "demo"})
    monkeypatch.setattr(bots, "_read_instance_config", lambda key: {"account": _LIVE})
    assert bots._account_type_of("sos_fade_demo") == "live"


def test_LIVE_WINS_when_the_config_and_the_running_process_disagree(monkeypatch):
    """Between the promotion write and the restart, both are true of something. The tint says
    this bot touches real money, so it goes amber the moment ANY evidence says live.

    ⚠ Watched RED by preferring the reported account.
    """
    from routers import bots

    monkeypatch.setattr(bots, "_registered_kinds", lambda: {_LIVE: "live", _DEMO: "demo"})
    monkeypatch.setattr(bots, "_read_instance_config", lambda key: {"account": _LIVE})
    assert bots._account_type_of("sos_fade_demo", reported_account=_DEMO) == "live"


def test_an_UNREADABLE_registry_falls_back_to_the_hardcoded_label(monkeypatch):
    """Cannot ask is not an answer. An unreadable account registry may not blank the fleet's
    tinting or silently redesignate every bot.

    🔴 **The bot here is registered LIVE on purpose.** Every real bot today is registered demo,
    so against one of those *"fall back to the hardcode"* and *"just answer demo"* are the SAME
    assertion — the test would be green against a planner that had no fallback at all. A mutation
    proved it: this case passed with the fallback replaced by the literal "demo".
    ⚠ Watched RED by returning "demo" when the registry is empty.
    """
    from routers import bots

    monkeypatch.setattr(bots, "_BY_KEY", dict(bots._BY_KEY, x_live=_LiveReg("x_live")))
    monkeypatch.setattr(bots, "_registered_kinds", lambda: {})
    monkeypatch.setattr(bots, "_read_instance_config", lambda key: {"account": _LIVE})
    assert bots._account_type_of("x_live") == "live"


def test_a_BENCHED_bot_falls_back_to_the_hardcoded_label(monkeypatch):
    """A bot on no account has no account to derive a kind from.

    ⚠ Registered LIVE for the reason above: against a demo-registered bot this case cannot tell
    a fallback from a hardcoded "demo".
    ⚠ Watched RED by returning "demo" for every unresolvable bot regardless of its registration.
    """
    from routers import bots

    monkeypatch.setattr(bots, "_BY_KEY", dict(bots._BY_KEY, x_live=_LiveReg("x_live")))
    monkeypatch.setattr(bots, "_registered_kinds", lambda: {_LIVE: "live"})
    monkeypatch.setattr(bots, "_read_instance_config", lambda key: {"account": None})
    assert bots._account_type_of("x_live") == "live"


def test_the_settings_import_REFUSES_a_bot_that_has_been_promoted_to_live(monkeypatch):
    """🔴 The hole step 8 opens if the label stays hardcoded. Both settings imports refuse on
    anything but demo, so a stale label turns the one guard protecting real money into a comment.

    ⚠ Watched RED by leaving `_bot_targets` reading `reg.account_type`.
    """
    from routers import bots

    monkeypatch.setattr(bots, "_registered_kinds", lambda: {_LIVE: "live"})
    monkeypatch.setattr(
        bots, "_read_instance_config", lambda key: {"account": _LIVE, "strategy_package": "x"}
    )
    monkeypatch.setattr(bots, "_declared_strategy_params", lambda pkg: set())
    targets = bots._bot_targets(set())
    assert targets and all(t.account_type == "live" for t in targets)


class _LiveReg:
    """A bot REGISTERED live. Nothing in the real registry is, and that is exactly why the
    fallback cases need one: against a demo-registered bot, *fell back* and *answered demo* are
    indistinguishable."""

    def __init__(self, key):
        self.key = self.display = key
        self.account_type = "live"
        self.task = f"BOT_{key.upper()}"


def test_the_FLEET_SNAPSHOT_tints_a_promoted_bot_live(monkeypatch):
    """🔴 The tinting, the "N of these are LIVE accounts" warning on every fleet dialog and the
    demo/live filter all read this one field. A promoted bot rendered as demo is the exact
    direction the bot registry's own comment names as dangerous.

    ⚠ **`test_bot_registry.py` already asserted this field and CANNOT catch the regression** —
    it compares each row to `reg.account_type`, and every registered bot is demo-on-demo, so
    derived and hardcoded give the same answer there. This case makes the two differ.
    ⚠ Watched RED by reading `_BY_TASK[task].account_type` again.
    """
    from routers import bots

    monkeypatch.setattr(bots, "_fetch_vps_snapshot", lambda: {})
    monkeypatch.setattr(bots, "_registered_kinds", lambda: {_LIVE: "live"})
    monkeypatch.setattr(bots, "_read_instance_config", lambda key: {"account": _LIVE})
    snap = bots.get_snapshot()
    assert snap.bots and all(b.account_type == "live" for b in snap.bots)


def test_the_SINGLE_BOT_settings_import_refuses_a_promoted_bot(client, monkeypatch, tmp_path):
    """🔴 The other half of the hole step 8 opens. That planner refuses anything but a demo bot,
    so a hardcoded label would go on saying demo about a bot now trading real money — turning the
    one guard there that protects money into a comment.

    ⚠ Watched RED by reading `reg.account_type` again.
    """
    import json as _json

    from routers import bots
    from services import lab_db

    lab_db.upsert_strategy(
        {
            "id": "sos_fade",
            "name": "SOS Fade",
            "class_name": "SosFadeStrategy",
            "source_path": "strategies/python/sos_fade",
            "runner": "python",
            "scanned_at": 1,
            "source_hash": "h",
        }
    )
    lab_db.insert_run(
        {
            "run_id": "r_live",
            "strategy_id": "sos_fade",
            "status": "complete",
            "created_at": 1,
            "runner": "python",
            "instrument": "XAUUSD.p",
            "bar_type": "Minute",
            "bar_value": 15,
            "params": {"exec_risk_pct": 4.0},
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
        }
    )
    lab_db.insert_stress_test(
        {"stress_test_id": "st_live", "run_id": "r_live", "status": "complete", "created_at": 2}
    )
    config = {
        "strategy_package": "sos_fade",
        "account": _LIVE,
        "symbol": "XAUUSD.p",
        "timeframe": "M15",
        "strategy_params": {"exec_risk_pct": 5.0},
    }
    monkeypatch.setattr(bots, "_registered_kinds", lambda: {_LIVE: "live"})
    monkeypatch.setattr(bots, "_read_instance_config", lambda key: _json.loads(_json.dumps(config)))
    monkeypatch.setattr(bots, "_declared_strategy_params", lambda pkg: set(_DECLARED))

    r = client.get("/bots/sos_fade_demo/settings-from-stress-test/st_live")
    assert r.status_code == 200
    assert "live" in (r.json()["blocked"] or "")
