"""Copying a graded STACK's settings onto the bots that run its legs.

**ALL OR NOTHING.** A shared-account stack is a measurement of several strategies competing for
one balance and one risk budget. Writing three of its four legs produces a strategy set nobody
has measured — and it reads as a completed copy, because every bot it did reach is correct.

⚠ **A fail-watch against HEAD is VACUOUS for every case here** — the module did not exist — so
non-vacuity is by MUTATION, and each docstring names the mutation that turns it red.
"""

from __future__ import annotations

import pytest
from services.stack_settings_import import BotTarget, plan_stack_import

_DECLARED = {"exec_risk_pct", "exec_tp1_pct", "exec_sl_mode"}
_ACCOUNT = 700152905


def _bot(
    key: str,
    *,
    pkg: str,
    account=_ACCOUNT,
    account_type: str = "demo",
    running: bool = False,
    risk=5.0,
    cap=10.0,
    tf: str = "M15",
    symbol: str = "XAUUSD.p",
    unreadable: bool = False,
    extra: dict | None = None,
) -> BotTarget:
    config = (
        None
        if unreadable
        else {
            "strategy_package": pkg,
            "account": account,
            "account_risk_cap_pct": cap,
            "symbol": symbol,
            "timeframe": tf,
            "strategy_params": {"exec_risk_pct": risk, **(extra or {})},
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


def _leg(sid: str, *, bar_value=15, **params) -> dict:
    return {
        "strategy_id": sid,
        "params": {"exec_risk_pct": 5.0, **params},
        "instrument": "XAUUSD.p",
        "bar_type": "Minute",
        "bar_value": bar_value,
    }


def _plan(legs, bots, *, cap=10.0, grade="A", graded=True):
    return plan_stack_import(
        legs=legs, bots=bots, stack_risk_cap_pct=cap, grade=grade, graded=graded
    )


TWO_BOTS = [
    _bot("sos_fade_demo", pkg="sos_fade"),
    _bot("extreme_leg_demo", pkg="extreme_leg"),
]
TWO_LEGS = [_leg("sos_fade"), _leg("extreme_leg")]


# ── Every leg has to land somewhere ───────────────────────────────────────────


def test_a_leg_with_NO_bot_blocks_the_whole_copy():
    """🔴 The rule the feature exists for. Writing the legs that do have bots produces a strategy
    set nobody measured, and every bot it reached would be correct — so it reads as finished.

    ⚠ Watched RED by planning only the legs that matched.
    """
    plan = _plan(TWO_LEGS + [_leg("b_leg")], TWO_BOTS)
    assert plan.blocked
    assert "b_leg" in plan.blocked
    assert plan.legs == []


def test_TWO_bots_running_one_strategy_blocks_rather_than_picking_one():
    """Nothing here can say which of two bots a leg belongs to, and guessing writes a stack onto
    a bot that was not in it.

    ⚠ Watched RED by taking the first match.
    """
    bots = TWO_BOTS + [_bot("sos_fade_demo_2", pkg="sos_fade")]
    plan = _plan(TWO_LEGS, bots)
    assert plan.blocked
    assert "more than one" in plan.blocked
    assert "sos_fade_demo" in plan.blocked and "sos_fade_demo_2" in plan.blocked


def test_a_leg_is_matched_on_the_bots_own_strategy_package():
    """Never on a key-name convention. `sos_fade` → `sos_fade_demo` is a rule living in a string,
    and it breaks the first time a bot is named differently.

    ⚠ Watched RED by matching on the bot key's prefix.
    """
    bots = [
        _bot("alpha", pkg="sos_fade"),
        _bot("beta", pkg="extreme_leg"),
    ]
    plan = _plan(TWO_LEGS, bots)
    assert plan.blocked is None
    assert {leg.bot_key for leg in plan.legs} == {"alpha", "beta"}


# ── Demo, one account, stopped ────────────────────────────────────────────────


def test_a_LIVE_bot_among_the_legs_blocks_the_whole_copy():
    """Demo → live is the next stage and a separate decision. If this could reach a live bot the
    two stages would be one button with two labels.

    🔴 It asserts WHICH rule refused, not just that something did. The first version checked only
    that the message named the bot and the word "demo" — and it SURVIVED its own mutation: with
    the stack-level check narrowed to the first leg, the live bot falls through to the per-leg
    planner, which refuses it too and produces a message satisfying both halves. **A refusal for
    a different reason passes a test that only asks whether it refused** — the same trap
    `test_gradable_resolver.py` recorded on its exactly-one-target case.

    ⚠ The per-leg planner IS the backstop and stays; what this pins is that the STACK-level check
    gets there first, so the reader is told the whole set is barred rather than reading it as one
    leg's problem.
    ⚠ Watched RED by checking only the first leg's account type.
    """
    bots = [TWO_BOTS[0], _bot("extreme_leg_demo", pkg="extreme_leg", account_type="live")]
    plan = _plan(TWO_LEGS, bots)
    assert plan.blocked
    assert "does not trade a demo account" in plan.blocked
    assert not plan.blocked.startswith("extreme_leg_demo:"), (
        "refused by the per-leg backstop, not by the stack-level check"
    )


def test_a_BENCHED_leg_bot_blocks_it__the_legs_do_not_share_a_balance():
    """A bot with no account is not on the account the stack was replayed on, so the set does not
    share a balance and nothing measured it.

    ⚠ Watched RED by treating a null account as "same as everyone else's".
    """
    bots = [TWO_BOTS[0], _bot("extreme_leg_demo", pkg="extreme_leg", account=None)]
    plan = _plan(TWO_LEGS, bots)
    assert plan.blocked
    assert "not on an account" in plan.blocked


def test_bots_on_TWO_accounts_block_it():
    """🔴 The stack was replayed on ONE balance with one risk budget. Across two accounts the
    contention that produced every number in it does not exist.

    ⚠ Watched RED by taking the first leg's account and never comparing.
    """
    bots = [TWO_BOTS[0], _bot("extreme_leg_demo", pkg="extreme_leg", account=999)]
    plan = _plan(TWO_LEGS, bots)
    assert plan.blocked
    assert "different accounts" in plan.blocked


def test_a_RUNNING_leg_bot_blocks_it():
    """A bot reads its config at startup, so the write cannot reach the live process — it would
    go on trading the old settings while the page showed the new ones.

    ⚠ Watched RED by dropping the running check.
    """
    bots = [TWO_BOTS[0], _bot("extreme_leg_demo", pkg="extreme_leg", running=True)]
    plan = _plan(TWO_LEGS, bots)
    assert plan.blocked
    assert "is running" in plan.blocked


def test_an_UNREADABLE_config_blocks_it_rather_than_reading_as_empty():
    """A bot whose settings cannot be read is not a bot with no settings. Treating it as `{}`
    would report every one of the run's values as a change and write them blind.

    🔴 It also has to name the RIGHT cause. An unreadable config states no strategy package, so
    the leg's own bot fails to match and the first version of this reported *"no registered bot
    runs extreme_leg"* — sending the reader to register a bot that already exists. The check runs
    before the matching now, over every registered bot, because an unreadable one may equally be
    a stranger sharing the account.

    ⚠ Watched RED by defaulting an unreadable config to `{}`.
    """
    bots = [TWO_BOTS[0], _bot("extreme_leg_demo", pkg="extreme_leg", unreadable=True)]
    plan = _plan(TWO_LEGS, bots)
    assert plan.blocked
    assert "could not be read" in plan.blocked
    assert "no registered bot runs" not in plan.blocked


# ── The per-leg work goes through the SAME planner a single import uses ───────


def test_each_leg_is_planned_through_the_single_bot_planner():
    """Not re-implemented here. A second copy of *which settings move* is a second answer, and
    the copy is the one that goes stale.

    ⚠ Watched RED by mutating the single-bot planner's equality rule — this test moves with it,
    which is the property being asserted.
    """
    legs = [_leg("sos_fade", exec_tp1_pct=30.0), _leg("extreme_leg")]
    plan = _plan(legs, TWO_BOTS)
    assert plan.blocked is None
    by_bot = {leg.bot_key: leg for leg in plan.legs}
    names = {c.name for c in by_bot["sos_fade_demo"].plan.changes}
    assert names == {"exec_tp1_pct"}, "exec_risk_pct already matches at 5.0 and must not be listed"
    assert by_bot["extreme_leg_demo"].plan.changes == []


def test_a_leg_level_refusal_blocks_the_WHOLE_plan_and_names_the_bot():
    """A stack written minus one leg is a strategy set nobody measured, and it reads as finished.

    ⚠ Watched RED by skipping a blocked leg instead of returning.
    """
    legs = [dict(_leg("sos_fade"), params={}), _leg("extreme_leg")]
    plan = _plan(legs, TWO_BOTS)
    assert plan.blocked
    assert plan.blocked.startswith("sos_fade_demo:")


def test_nothing_to_do_is_a_NOOP_not_a_change():
    """The bots already match and the account is already at the stack's budget.

    ⚠ Watched RED by counting an unchanged setting as a change.
    """
    plan = _plan(TWO_LEGS, TWO_BOTS, cap=10.0)
    assert plan.blocked is None
    assert plan.change_count == 0
    assert plan.is_noop is True


# ── The account's risk budget ─────────────────────────────────────────────────


def test_the_budget_is_written_to_EVERY_bot_on_the_account():
    """🔴 The ceiling is stored per bot and the account's cap is whatever its bots agree on, so
    one left behind leaves the account with two ceilings — the state `bot_accounts` refuses to
    report a cap for at all.

    ⚠ Watched RED by writing the budget to the stack's legs only.
    ⚠ The legs drop to 3% each so the account still FITS under the lower ceiling. The first
    version left them at 5% against a new cap of 8% and was correctly refused as
    over-subscribed — a premise that made the test about the share check instead.
    """
    bots = TWO_BOTS + [_bot("b_leg_demo", pkg="b_leg", risk=0.0)]
    legs = [_leg("sos_fade", exec_risk_pct=3.0), _leg("extreme_leg", exec_risk_pct=3.0)]
    plan = _plan(legs, bots, cap=8.0)
    assert plan.blocked is None
    assert plan.cap.current == 10.0
    assert plan.cap.proposed == 8.0
    assert plan.cap.bots_to_write == ["b_leg_demo", "extreme_leg_demo", "sos_fade_demo"]


def test_a_stack_that_recorded_NO_budget_leaves_the_ceiling_alone_and_says_so():
    """`None` means the stack recorded no budget, not that it recorded an absence of one.
    Clearing a live account's ceiling because a stored figure was missing is the opposite of what
    an absent value means.

    ⚠ Watched RED by writing `None` as the proposed cap.
    """
    plan = _plan(TWO_LEGS, TWO_BOTS, cap=None)
    assert plan.blocked is None
    assert plan.cap.proposed is None
    assert plan.cap.bots_to_write == []
    assert any("no account risk budget" in w for w in plan.warnings)


# ── The shares must still fit, AFTER the write ───────────────────────────────


def test_an_OVER_SUBSCRIBED_result_blocks_the_copy():
    """Aaron's rule: the risk per trade cannot add up to more than the cap. Over the ceiling the
    bots do not share the budget, they take turns — so each one stops being the bot that was
    measured, silently.

    ⚠ Watched RED by dropping the share check.
    """
    legs = [_leg("sos_fade", exec_risk_pct=6.0), _leg("extreme_leg", exec_risk_pct=6.0)]
    plan = _plan(legs, TWO_BOTS, cap=10.0)
    assert plan.blocked
    assert "over-subscribed" in plan.blocked


def test_the_share_check_reads_the_PROPOSED_shares_not_todays():
    """🔴 The load-bearing half. Checking the current state passes every write that CREATES the
    problem and refuses every write that FIXES it — here the bots are over their ceiling today
    and the copy is what brings them back under it.

    ⚠ Watched RED by summing the bots' current shares instead of the planned ones.
    """
    bots = [
        _bot("sos_fade_demo", pkg="sos_fade", risk=8.0),
        _bot("extreme_leg_demo", pkg="extreme_leg", risk=8.0),
    ]
    legs = [_leg("sos_fade", exec_risk_pct=4.0), _leg("extreme_leg", exec_risk_pct=4.0)]
    plan = _plan(legs, bots, cap=10.0)
    assert plan.blocked is None, plan.blocked
    assert plan.change_count == 2


def test_a_bot_on_the_account_that_is_NOT_a_leg_still_counts_against_the_budget():
    """It shares the balance, so it spends the budget whether or not this stack mentions it.
    Leaving it out reports a set of shares that fits while the account's does not.

    ⚠ Watched RED by summing the stack's legs alone.
    """
    bots = TWO_BOTS + [_bot("b_leg_demo", pkg="b_leg", risk=4.0)]
    plan = _plan(TWO_LEGS, bots, cap=10.0)
    assert plan.blocked
    assert "over-subscribed" in plan.blocked
    assert "b_leg_demo" in plan.blocked


def test_a_bot_on_the_account_that_is_not_a_leg_is_WARNED_about():
    """The account will hold a strategy set the stack never modelled. Not a refusal — benching it
    is the reader's call — but a page that cannot say so shows a partial picture as a complete
    one.

    ⚠ Watched RED by dropping the stranger warning.
    """
    bots = TWO_BOTS + [_bot("b_leg_demo", pkg="b_leg", risk=0.0)]
    plan = _plan(TWO_LEGS, bots, cap=10.0)
    assert plan.blocked is None
    assert any("b_leg_demo" in w and "not part of this stack" in w for w in plan.warnings)


def test_an_UNREADABLE_share_on_the_account_blocks_rather_than_counting_as_zero():
    """A bot whose risk cannot be read is not a bot risking nothing, and scoring it 0.0 lets a
    genuinely over-subscribed account save cleanly.

    ⚠ It is a bot on the account but NOT a leg, so it reaches the share check rather than the
    per-leg readability refusal above.
    ⚠ Watched RED by defaulting a missing share to 0.0.
    """
    stranger = _bot("b_leg_demo", pkg="b_leg")
    stranger.config["strategy_params"] = {}
    plan = _plan(TWO_LEGS, TWO_BOTS + [stranger], cap=10.0)
    assert plan.blocked
    assert "b_leg_demo" in plan.blocked


# ── Warnings carry the bot they belong to ────────────────────────────────────


def test_each_legs_own_warnings_are_NAMED_with_its_bot():
    """Rolled into one list, a reader cannot tell which of four bots is on the wrong chart.

    ⚠ Watched RED by extending the warnings without the prefix.
    """
    bots = [TWO_BOTS[0], _bot("extreme_leg_demo", pkg="extreme_leg", tf="M5")]
    plan = _plan(TWO_LEGS, bots)
    assert plan.blocked is None
    assert any(w.startswith("extreme_leg_demo:") and "5-minute" in w for w in plan.warnings)


def test_an_UNGRADED_stress_test_warns_on_every_leg_and_refuses_nothing():
    """Not graded is not the same as passed — and blocking a low grade fights this repo's stated
    design intent, so every grade signal here is loud and none of them refuses.

    ⚠ Watched RED by blocking on an ungraded test.
    """
    plan = _plan(
        [_leg("sos_fade", exec_tp1_pct=30.0), _leg("extreme_leg")],
        TWO_BOTS,
        grade=None,
        graded=False,
    )
    assert plan.blocked is None
    assert plan.change_count == 1
    named = [w for w in plan.warnings if "not been graded" in w]
    assert len(named) == 2, "one per leg, each naming its bot"


def test_NO_LEGS_at_all_is_refused():
    """A stack row with no legs recorded has nothing to copy, and an empty plan would apply
    cleanly and write nothing while reporting success.

    ⚠ Watched RED by returning an empty plan.
    """
    plan = _plan([], TWO_BOTS)
    assert plan.blocked
    assert "no legs" in plan.blocked


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])


# ── The two endpoints ─────────────────────────────────────────────────────────


@pytest.fixture
def stack_env(client, tmp_path, monkeypatch):
    """A shared stack with a combined book, two demo bots, and every write intercepted.

    ⚠ **Nothing touches a real instance config.** `tests/conftest.py::_no_live_bot_config` exists
    because a refusal test once moved the live `b_leg_demo` bot onto an account — a plain file in
    this repo, reachable with no network at all.
    """
    import json

    from routers import bots
    from services import lab_db, portfolio_runner

    monkeypatch.setattr(portfolio_runner, "_LAB_RESULTS_DIR", tmp_path / "reports")

    for sid, name in (("sos_fade", "SOS Fade"), ("extreme_leg", "Extreme Leg")):
        lab_db.upsert_strategy(
            {
                "id": sid,
                "name": name,
                "class_name": f"{sid.title()}Strategy",
                "source_path": f"strategies/python/{sid}",
                "runner": "python",
                "scanned_at": 1,
                "source_hash": "h",
            }
        )
        lab_db.insert_run(
            {
                "run_id": f"r_{sid}",
                "strategy_id": sid,
                "instrument": "XAUUSD.p",
                # 🔴 4% a leg against the stack's own 8% budget. The first version of this
                # fixture put 5% legs under an 8% ceiling and every apply here was correctly
                # REFUSED as over-subscribed — a fixture describing an account the stack itself
                # could not have been replayed on. Second time in this file that a premise, not
                # a subject, failed: check the fixture before the code.
                "params": {"exec_risk_pct": 4.0, "exec_tp1_pct": 30.0},
                "bar_type": "Minute",
                "bar_value": 15,
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "commission_per_side": 0.0,
                "slippage_ticks": 0,
                "status": "complete",
                "created_at": 1,
                "runner": "python",
            }
        )

    lab_db.insert_stack(
        {
            "stack_id": "stk_1",
            "instrument": "XAUUSD.p",
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "created_at": 1,
            "mode": "shared",
            "account_size": 10_000.0,
            "risk_cap_pct": 8.0,
            "entry_floor_pct": 0.0,
        }
    )
    for i, sid in enumerate(("sos_fade", "extreme_leg")):
        lab_db.add_stack_member("stk_1", f"r_{sid}", 1, i)

    sdir = portfolio_runner.stack_dir("stk_1")
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "combined_equity_curve.json").write_text(
        json.dumps([{"index": 1, "equity": 10_500.0, "profit": 500.0}])
    )
    (sdir / "combined_daily_pnl.json").write_text("[]")
    (sdir / "shared_summary.json").write_text(
        json.dumps({"stack_id": "stk_1", "combined_kpis": {"trade_count": 120}})
    )

    lab_db.insert_stress_test(
        {
            "stress_test_id": "st_stack",
            "stack_id": "stk_1",
            "status": "complete",
            "created_at": 2,
            "runner": "python",
            "target_label": "SOS Fade + Extreme Leg",
        }
    )

    configs = {
        "sos_fade_demo": {
            "strategy_package": "sos_fade",
            "account": _ACCOUNT,
            "account_risk_cap_pct": 10.0,
            "symbol": "XAUUSD.p",
            "timeframe": "M15",
            "strategy_params": {"exec_risk_pct": 5.0, "exec_tp1_pct": 0.0},
        },
        "extreme_leg_demo": {
            "strategy_package": "extreme_leg",
            "account": _ACCOUNT,
            "account_risk_cap_pct": 10.0,
            "symbol": "XAUUSD.p",
            "timeframe": "M15",
            "strategy_params": {"exec_risk_pct": 5.0, "exec_tp1_pct": 0.0},
        },
    }
    written: dict = {}
    commits: list = []

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
    monkeypatch.setattr(
        bots, "_git_commit_push", lambda paths, msg, reason: commits.append((paths, msg)) or "ok"
    )
    return {"configs": configs, "written": written, "commits": commits}


_URL = "/bots/stack-settings-from-stress-test/st_stack"


def test_a_SINGLE_RUN_stress_test_is_sent_to_the_other_control(client, stack_env):
    """Not a 404 and not a silent single-bot copy — a run has one bot and this route writes to
    many, so naming the right control is the answer.

    ⚠ Watched RED by dropping the stack_id check.
    """
    from services import lab_db

    lab_db.insert_stress_test(
        {"stress_test_id": "st_run", "run_id": "r_sos_fade", "status": "complete", "created_at": 1}
    )
    r = client.get("/bots/stack-settings-from-stress-test/st_run")
    assert r.status_code == 400
    assert "single run" in r.json()["detail"]


def test_a_SCREEN_stack_is_refused_by_the_same_resolver_the_test_was_started_through(
    client, stack_env
):
    """🔴 On a screen every leg traded its own full account with nothing able to block anything,
    so its settings describe bots that never contended — which is not the configuration these
    bots would be put into.

    ⚠ It goes through `gradable.resolve`, the SAME call the stress test itself was started
    through, so this route cannot accept a target that one refuses.
    ⚠ Watched RED by resolving the stack from `lab_db` directly instead.
    """
    import sqlite3

    from services import lab_db

    with sqlite3.connect(lab_db.DB_PATH) as c:
        c.execute("UPDATE stacks SET mode='screen' WHERE stack_id='stk_1'")
    r = client.get(_URL)
    assert r.status_code == 400
    assert "screen" in r.json()["detail"]


def test_the_PREVIEW_and_the_APPLY_build_the_SAME_plan(client, stack_env):
    """🔴 The whole value of the feature. Two code paths that each assemble a list are two lists
    that can drift, invisibly, and the reader has then approved something else.

    ⚠ **It asserts what was WRITTEN, not only what the two reported.** Both endpoints build
    their response from their own plan, so comparing the two responses alone passes against an
    apply that plans correctly and then writes something else — which is the drift that matters.
    ⚠ Watched RED by having the apply write a subset of its own plan.
    """
    preview = client.get(_URL).json()
    applied = client.post(_URL).json()

    def _shape(p):
        return [
            (leg["bot"], sorted((c["name"], c["proposed"]) for c in leg["changes"]))
            for leg in p["legs"]
        ], (p["cap"] or {}).get("bots_to_write")

    assert _shape(preview) == _shape(applied)
    assert preview["applied"] is False and applied["applied"] is True

    written = stack_env["written"]
    for leg in preview["legs"]:
        for change in leg["changes"]:
            assert written[leg["bot"]]["strategy_params"][change["name"]] == change["proposed"], (
                f"{leg['bot']} was written something other than the previewed {change['name']}"
            )


def test_the_APPLY_writes_every_leg_AND_the_budget_in_ONE_commit(client, stack_env):
    """⚠ One commit, because a stack is a set of bots measured together — two commits is two
    states of the fleet and the one in between was never measured.

    ⚠ It asserts the commit carries EVERY written file. Counting commits alone passes against
    one commit that stages a single bot, which is the same fleet-in-between state.
    ⚠ Watched RED by committing one bot's path, and again by skipping the account budget.
    """
    r = client.post(_URL)
    assert r.status_code == 200, r.text
    written = stack_env["written"]
    assert set(written) == {"sos_fade_demo", "extreme_leg_demo"}
    for cfg in written.values():
        assert cfg["strategy_params"]["exec_tp1_pct"] == 30.0
        assert cfg["strategy_params"]["exec_risk_pct"] == 4.0
        assert cfg["account_risk_cap_pct"] == 8.0, "the stack's own budget, on every bot"
    assert len(stack_env["commits"]) == 1
    paths, _msg = stack_env["commits"][0]
    assert {p.name for p in paths} == {"sos_fade_demo.json", "extreme_leg_demo.json"}
    assert r.json()["restart_required"] is True


def test_a_BLOCKED_apply_is_a_409_and_writes_NOTHING(client, stack_env, monkeypatch):
    """All or nothing. A refusal that had already written one bot would leave the fleet in a
    state nobody chose and report the refusal as the whole story.

    ⚠ Through `monkeypatch`, never a bare assignment — this module's attributes are patched by
    the fixture too, and a raw write leaves whichever of the two ran last in place for the rest
    of the session.
    ⚠ Watched RED by writing before checking `blocked`.
    """
    from routers import bots

    monkeypatch.setattr(bots, "_running_bot_keys", lambda: {"extreme_leg_demo"})
    r = client.post(_URL)
    assert r.status_code == 409
    assert "is running" in r.json()["detail"]
    assert stack_env["written"] == {}
    assert stack_env["commits"] == []


def test_an_apply_with_NOTHING_to_do_reports_applied_False_and_makes_no_commit(client, stack_env):
    """The bots already match. Reporting success there claims a write that did not happen, and an
    empty commit is noise in a log two people read.

    ⚠ Watched RED by reporting `applied=True` unconditionally.
    """
    for cfg in stack_env["configs"].values():
        cfg["strategy_params"]["exec_tp1_pct"] = 30.0
        cfg["strategy_params"]["exec_risk_pct"] = 4.0
        cfg["account_risk_cap_pct"] = 8.0
    r = client.post(_URL)
    assert r.status_code == 200, r.text
    assert r.json()["applied"] is False
    assert stack_env["written"] == {}
    assert stack_env["commits"] == []
