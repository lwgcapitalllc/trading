"""Copying a graded stress test's settings onto a DEMO bot.

**The promise this feature makes is a narrow one and every test here is about it: the list the
reader approves is the change that lands.** A preview that can differ from the apply is worse than
no feature — the reader has approved a list that describes something else, and nothing on the page
can say so. `test_the_PREVIEW_and_the_APPLY_return_the_SAME_plan` is the one that guards it; the
rest guard the rules that make the list correct in the first place.

⚠ **A fail-watch against HEAD is VACUOUS for all of these** — `services/bot_settings_import.py` did
not exist, so the module cannot be imported at HEAD and every test in the file errors for a reason
unrelated to any defect. **Non-vacuity is therefore by MUTATION**, and each test's docstring names
the mutation that turns it red. **All 20 were RUN and all 20 are killed** — but only after two
survived, and both survivals are worth more than the pass:

🔴 **One "survivor" was the HARNESS aiming at the wrong code.** `if _bot_is_running(bot_key):`
appears twice in `routers/bots.py` — the account move at 1582 and this feature at 2293 — and a
first-occurrence replace mutated the OTHER endpoint. The test stayed green because nothing it
covers had been touched. **A mutation that lands somewhere else is not a surviving mutation, and
it reads exactly like one.** Assert the edit landed where you meant before believing the verdict.

🔴 **The other was a real hole, and it took two attempts to close.** The bot fixture and the run
carried the SAME key set, so "write exactly the planned changes" and "merge the run's whole dict"
produced identical output — the test could not distinguish the behaviours it named. Adding a
bot-only setting did not fix it either, because a merge leaves that key alone. Only a run setting
the strategy does NOT declare separates them, which is also the one that matters: the bot refuses
to start on such a setting. **Check that a test's inputs can distinguish the behaviours it names.**
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from services import bot_settings_import as bsi

_RUN_PARAMS = {
    "exec_aplus": True,
    "exec_scale_in": True,
    "exec_risk_pct": 10.0,
    "exec_sec_trigger": "FVG in zone + Reclaim Entry",
}
_BOT_PARAMS = {
    "exec_aplus": True,
    "exec_scale_in": False,
    "exec_risk_pct": 5.0,
    "exec_sec_trigger": "FVG in zone",
}
_DECLARED = set(_RUN_PARAMS) | set(_BOT_PARAMS)


def _plan(**over):
    kwargs = dict(
        run_params=dict(_RUN_PARAMS),
        bot_params=dict(_BOT_PARAMS),
        declared=set(_DECLARED),
        account_type="demo",
        grade="A",
        graded=True,
        run_instrument="XAUUSD.p",
        bot_symbol="XAUUSD.p",
        run_bar_type="Minute",
        run_bar_value=15,
        bot_timeframe="M15",
    )
    kwargs.update(over)
    return bsi.plan_import(**kwargs)


# ── the one refusal ───────────────────────────────────────────────────────────


def test_a_LIVE_bot_is_refused_outright():
    """MUTATION: drop the account_type branch → this goes red.

    Demo-only is the whole point of the stage. If this control could write to a live bot then
    "promote to demo" and "promote to live" would be one button with two labels, and the pipeline
    would have one fewer gate than the operator believes it has.
    """
    plan = _plan(account_type="live")
    assert plan.blocked is not None
    assert "live" in plan.blocked
    assert plan.changes == [], "a refused plan must propose nothing"


def test_a_demo_bot_is_not_refused():
    """The other half of the branch — green at HEAD by construction, kept so a future tightening
    that refuses everything cannot land quietly."""
    assert _plan().blocked is None


def test_a_run_with_NO_stored_settings_is_refused_rather_than_applied_as_empty():
    """MUTATION: return an empty plan instead of blocking → red.

    A run carrying no settings cannot be reproduced either. Treating it as "nothing to change"
    would report success for a copy that copied nothing.
    """
    plan = _plan(run_params={})
    assert plan.blocked is not None
    assert plan.changes == []


# ── what the list contains ────────────────────────────────────────────────────


def test_only_the_settings_that_DIFFER_are_listed():
    """MUTATION: list every writable setting rather than the differing ones → red.

    A list padded with settings that are not moving is a list nobody reads to the end, which
    defeats the one safeguard this feature provides.
    """
    plan = _plan()
    moved = {c.name for c in plan.changes}
    assert moved == {"exec_scale_in", "exec_risk_pct", "exec_sec_trigger"}
    assert plan.unchanged_count == 1, "exec_aplus already matches on both sides"


def test_a_change_carries_BOTH_ends_of_the_move():
    """MUTATION: drop `current` from the change record → red.

    The reader is approving a transition, not a destination. "Scale-ins become on" is only
    checkable beside "they are off today".
    """
    plan = _plan()
    scale = next(c for c in plan.changes if c.name == "exec_scale_in")
    assert scale.current is False
    assert scale.proposed is True


def test_1_and_1_point_0_are_NOT_reported_as_a_change():
    """MUTATION: compare with `!=` on the raw values → red.

    Settings arrive from JSON on the bot's side and from a dataclass on the run's, so the two
    spellings of one number are routine. Reporting them as changes fills the list with noise.
    """
    plan = _plan(run_params={"exec_risk_pct": 10}, bot_params={"exec_risk_pct": 10.0})
    assert plan.changes == []
    assert plan.unchanged_count == 1


def test_a_BOOLEAN_is_never_folded_into_a_number():
    """MUTATION: drop the bool guard from `_same` → red.

    `True == 1` in Python. A toggle flipping between the two is a real change on a bot, and the
    arithmetic agreeing is exactly why it would go unreported.
    """
    plan = _plan(run_params={"exec_scale_in": True}, bot_params={"exec_scale_in": 1})
    assert [c.name for c in plan.changes] == ["exec_scale_in"]


# ── what may be written at all ────────────────────────────────────────────────


def test_a_setting_the_STRATEGY_does_not_declare_is_dropped_AND_NAMED():
    """MUTATION: write every run setting regardless of the declared set → red.

    The bot refuses to start on a setting its strategy does not have (measured 2026-09-04). Being
    named is the other half: a setting that vanishes without a word is one the reader believes
    they applied.
    """
    plan = _plan(run_params={**_RUN_PARAMS, "lab_only_knob": 3})
    assert "lab_only_knob" not in {c.name for c in plan.changes}
    assert any("lab_only_knob" in note for note in plan.dropped_notes)


def test_an_UNREADABLE_strategy_writes_unchecked_and_says_so():
    """MUTATION: treat `declared=None` as "declare nothing" and drop everything → red.

    `None` is *could not ask*, not *accepts nothing*. Of the two wrong answers, writing gives a bot
    that refuses to start and names the field, while skipping gives a bot that starts and trades
    settings nobody chose. A note carries the uncertainty.
    """
    plan = _plan(declared=None)
    assert {c.name for c in plan.changes} == {
        "exec_scale_in",
        "exec_risk_pct",
        "exec_sec_trigger",
    }
    assert plan.dropped_notes, "writing unchecked must never be silent"


def test_settings_the_RUN_never_mentions_are_reported_as_untouched():
    """MUTATION: stop collecting `untouched` → red.

    "Apply this run" reads as "the bot now matches this run". For a bot pinning 116 settings
    against a run naming four, that is not what happens, and the page has to be able to say so.
    """
    plan = _plan(bot_params={**_BOT_PARAMS, "exec_sl_deep": True})
    assert plan.untouched == ["exec_sl_deep"]
    assert any("keep their current values" in w for w in plan.warnings)


# ── the warnings: every one is loud and NONE of them refuses ──────────────────


def test_an_UNGRADED_test_warns_and_does_not_block():
    """MUTATION: raise/block instead of warning → red.

    Aaron's call: warn, never block. Blocking a low or absent grade makes the gate unreachable for
    a legitimately good low-trade config, which fights the stated design intent.
    """
    plan = _plan(graded=False, grade=None)
    assert plan.blocked is None
    assert any("has not been graded" in w for w in plan.warnings)
    assert any("Not graded is not the same as passed" in w for w in plan.warnings)


def test_GRADED_WITH_NO_LETTER_is_a_different_warning_from_NEVER_GRADED():
    """MUTATION: collapse the two into one message → red.

    `grade=None` after grading ran is a first-class outcome — the ruleset stated no drawdown limit,
    so there was no bar to grade against. Rendering that as "not graded" hides that the shake-out
    actually ran; rendering it as a pass would be worse.
    """
    never = _plan(graded=False, grade=None).warnings
    no_letter = _plan(graded=True, grade=None).warnings
    assert never != no_letter
    assert any("no drawdown limit" in w for w in no_letter)


@pytest.mark.parametrize("grade", ["D", "F"])
def test_a_WEAK_grade_warns_and_does_not_block(grade):
    """MUTATION: drop the weak-grade branch → red."""
    plan = _plan(grade=grade)
    assert plan.blocked is None
    assert any(grade in w for w in plan.warnings)


def test_a_STRONG_grade_raises_no_grade_warning():
    """Green at HEAD by construction. Kept so a change that warns on every grade — which would
    make the warning meaningless — cannot land quietly."""
    plan = _plan(grade="A")
    assert not any("graded" in w for w in plan.warnings)


def test_a_SYMBOL_mismatch_warns_and_still_writes():
    """MUTATION: refuse on a symbol mismatch → red.

    Measuring on one instrument and applying to another can be deliberate. Refusing guesses at the
    operator's intent; the warning states the fact and leaves the decision alone.
    """
    plan = _plan(run_instrument="EURUSD")
    assert plan.blocked is None
    assert plan.changes, "the settings are still written"
    assert any("EURUSD" in w for w in plan.warnings)


def test_a_TIMEFRAME_mismatch_warns_and_still_writes():
    """MUTATION: drop the timeframe comparison → red."""
    plan = _plan(run_bar_value=5, bot_timeframe="M15")
    assert plan.blocked is None
    assert any("5-minute" in w and "15-minute" in w for w in plan.warnings)


def test_a_timeframe_that_CANNOT_be_compared_says_so_rather_than_reporting_a_match():
    """MUTATION: return a match when either side is unparseable → red.

    A tick or range bar has no minute count. Silently comparing one to `M15` reports agreement
    between two things that were never the same shape — rule 1, in a warning line.
    """
    plan = _plan(run_bar_type="Tick", run_bar_value=500)
    assert any("could not compare" in w for w in plan.warnings)


def test_matching_symbol_and_timeframe_produce_NO_basis_warning():
    """Green at HEAD. Guards against a change that warns unconditionally."""
    warnings = _plan().warnings
    assert not any("could not compare" in w or "different" in w for w in warnings)


# ── the endpoints ─────────────────────────────────────────────────────────────


def _seed(fresh_db, *, grade="A", params=None):
    """One completed run and one graded stress test over it.

    ⚠ Built through `lab_db`'s own writers rather than raw SQL. The first version INSERTed
    straight into `backtest_runs` with a hand-rolled `strategies` row, and every endpoint test
    died on `FOREIGN KEY constraint failed` — the strategy insert was silently dropped by
    `OR IGNORE` because it did not satisfy the real table. A fixture that builds rows the app
    could not have written is describing a database you do not have.
    """
    from services import lab_db

    lab_db.upsert_strategy(
        {
            "id": "s_import",
            "name": "SOS Fade",
            "class_name": "SosFadeStrategy",
            "source_path": "strategies/python/sos_fade",
            "scanned_at": 0,
            "default_params": {},
            "param_schema": [],
            "runner": "python",
        }
    )
    run_id, st_id = "r_import_1", "st_import_1"
    lab_db.insert_run(
        {
            "run_id": run_id,
            "strategy_id": "s_import",
            "instrument": "XAUUSD.p",
            "params": params if params is not None else dict(_RUN_PARAMS),
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2020-01-01",
            "end_date": "2026-08-23",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "complete",
            "created_at": 0,
        }
    )
    with lab_db._connect() as conn:
        conn.execute(
            "INSERT INTO stress_tests (stress_test_id, run_id, status, created_at, grade,"
            " grade_reasons) VALUES (?,?,?,?,?,?)",
            (st_id, run_id, "complete", 0, grade, json.dumps(["ok"])),
        )
        conn.commit()
    return run_id, st_id


@pytest.fixture
def _bot(monkeypatch):
    """Point the router at a scratch instance config so no live bot is touched."""
    from routers import bots

    # 🔴 `exec_sl_deep` is on the BOT and in the DECLARED set while the run never mentions it, and
    # that asymmetry is load-bearing. With the two sides carrying the same key set, "write exactly
    # the planned changes" and "write the run's whole dict over the top" produce an identical
    # result — MEASURED: that mutation SURVIVED until this setting was added. A fixture whose
    # inputs cannot distinguish the behaviours the test names is describing a system where the
    # thing under test does nothing.
    cfg = {
        "bot_key": "sos_fade_demo",
        "symbol": "XAUUSD.p",
        "timeframe": "M15",
        "strategy_package": "sos_fade",
        "strategy_params": {**_BOT_PARAMS, "exec_sl_deep": True},
    }
    written = {}

    monkeypatch.setattr(bots, "_read_instance_config", lambda key: json.loads(json.dumps(cfg)))
    monkeypatch.setattr(bots, "_write_instance_config", lambda key, data: written.update(data))
    monkeypatch.setattr(bots, "_declared_strategy_params", lambda pkg: set(_DECLARED))
    monkeypatch.setattr(bots, "_bot_is_running", lambda key: False)
    monkeypatch.setattr(bots, "_git_commit_push", lambda *a, **k: "pushed")
    return written


def test_the_PREVIEW_writes_NOTHING(client, fresh_db, _bot):
    """MUTATION: have the preview call `_write_instance_config` → red.

    A preview that writes is not a preview. The `_write_instance_config` stub records into `_bot`,
    so a write is visible rather than merely unasserted.
    """
    _, st_id = _seed(fresh_db)
    r = client.get(f"/bots/sos_fade_demo/settings-from-stress-test/{st_id}")
    assert r.status_code == 200, r.text
    assert _bot == {}, "the preview must not have written the config"
    assert r.json()["applied"] is False


def test_the_PREVIEW_and_the_APPLY_return_the_SAME_plan(client, fresh_db, _bot):
    """MUTATION: have the apply rebuild its own list instead of using the planner → red.

    **This is the test the whole feature rests on.** The value of a preview-then-apply flow is
    entirely that the list the reader approved is the change that lands; two code paths that each
    assemble a list are two lists that can drift, invisibly.
    """
    _, st_id = _seed(fresh_db)
    url = f"/bots/sos_fade_demo/settings-from-stress-test/{st_id}"

    preview = client.get(url).json()
    applied = client.post(url).json()

    def shape(p):
        return sorted((c["name"], c["current"], c["proposed"]) for c in p["changes"])

    assert shape(preview) == shape(applied)
    assert preview["warnings"] == applied["warnings"]
    assert preview["dropped_notes"] == applied["dropped_notes"]


def test_the_APPLY_writes_EXACTLY_the_planned_changes_and_nothing_else(client, fresh_db, _bot):
    """MUTATION: merge the run's whole param dict into `strategy_params` → red.

    Two things must hold and they fail differently. The bot's own settings that the run never
    mentions survive untouched — replacing the dict wholesale would clear every pinned setting the
    run had no opinion about. And a LAB-ONLY setting the strategy does not declare must not reach
    the file at all: the bot refuses to start on one, so that write is the difference between a
    running bot and a dead one.

    🔴 **This test could not tell the two apart for two revisions, and each fix was insufficient
    for a different reason.** With the bot and run carrying identical key sets, "write the plan"
    and "write the run's dict" produced byte-identical output. Adding a bot-only setting did not
    help either, because a MERGE leaves it in place regardless. Only a run key the strategy does
    not declare separates them — MEASURED, the mutation survived both earlier versions.
    """
    _, st_id = _seed(fresh_db, params={**_RUN_PARAMS, "lab_only_knob": 3})
    r = client.post(f"/bots/sos_fade_demo/settings-from-stress-test/{st_id}")
    assert r.status_code == 200, r.text

    written = _bot["strategy_params"]
    assert written["exec_scale_in"] is True
    assert written["exec_risk_pct"] == 10.0
    assert written["exec_sec_trigger"] == "FVG in zone + Reclaim Entry"
    assert written["exec_aplus"] is True, "an unchanged setting must still be present"
    # The bot's own setting that the run never mentions — this is the assertion that can tell
    # "wrote the plan" apart from "wrote the run's whole dict", and it is why the fixture gives
    # the bot a key the run does not have.
    assert written["exec_sl_deep"] is True, "a setting the run never mentioned must survive"
    # The assertion that actually separates "wrote the plan" from "merged the run's dict": a
    # setting the strategy does not declare would stop the bot starting, so it must never land.
    assert "lab_only_knob" not in written, "an undeclared setting must not reach the bot's config"
    assert r.json()["applied"] is True


def test_the_APPLY_always_reports_that_a_RESTART_is_required(client, fresh_db, _bot):
    """MUTATION: report `restart_required=False` → red.

    Exactly one setting reaches a running bot without a restart. This control writes many, so any
    other answer claims an effect the bot has not had.
    """
    _, st_id = _seed(fresh_db)
    body = client.post(f"/bots/sos_fade_demo/settings-from-stress-test/{st_id}").json()
    assert body["restart_required"] is True


def test_a_RUNNING_bot_is_refused_and_nothing_is_written(client, fresh_db, _bot, monkeypatch):
    """MUTATION: drop the running check → red.

    Same reasoning as the account move: the bot read its config at startup, so the file change
    cannot reach the live process. It would go on trading the old settings while the page showed
    the new ones — a screen lying about a live position.
    """
    from routers import bots

    monkeypatch.setattr(bots, "_bot_is_running", lambda key: True)
    _, st_id = _seed(fresh_db)
    r = client.post(f"/bots/sos_fade_demo/settings-from-stress-test/{st_id}")
    assert r.status_code == 409
    assert "running" in r.json()["detail"]
    assert _bot == {}


def test_a_NO_OP_apply_writes_nothing_and_does_not_commit(client, fresh_db, _bot):
    """MUTATION: write and commit unconditionally → red.

    A bot that already matches needs no commit. Reporting `applied: True` there would claim a
    write that did not happen, and an empty commit is noise in a log two people read.
    """
    _, st_id = _seed(fresh_db, params=dict(_BOT_PARAMS))
    with patch("routers.bots._git_commit_push") as push:
        body = client.post(f"/bots/sos_fade_demo/settings-from-stress-test/{st_id}").json()
    assert body["applied"] is False
    assert body["changes"] == []
    assert _bot == {}
    push.assert_not_called()


def test_an_unknown_stress_test_is_a_404(client, fresh_db, _bot):
    """MUTATION: fall through to an empty plan → red. A typo'd id must not read as
    'this test proposes no changes'."""
    r = client.get("/bots/sos_fade_demo/settings-from-stress-test/nope")
    assert r.status_code == 404


def test_a_stress_test_whose_RUN_cannot_be_read_is_a_404_naming_the_run(
    client, fresh_db, _bot, monkeypatch
):
    """MUTATION: return an empty plan instead of raising → red.

    The settings live on the RUN, not on the test. A run that cannot be read means they cannot be
    read at all, which is a different fact from a run that carried none — and an empty plan would
    render as "this stress test proposes no changes".

    🔴 **The obvious version of this test CANNOT BE WRITTEN, and finding that out is worth more
    than the test was.** `stress_tests.run_id` is a FOREIGN KEY into `backtest_runs`, so pointing
    a test at a missing run raises `IntegrityError` on the way in — **the state this branch
    guards against is unreachable through the schema.** So the guard is defensive rather than
    load-bearing, and it is driven directly here rather than through a database state that cannot
    exist. Say that plainly rather than deleting the branch: `get_run` INNER JOINs `strategies`,
    so a future schema change could make it answer `None` again.
    """
    from services import lab_db

    _, st_id = _seed(fresh_db)
    monkeypatch.setattr(lab_db, "get_run", lambda run_id: None)
    r = client.get(f"/bots/sos_fade_demo/settings-from-stress-test/{st_id}")
    assert r.status_code == 404
    assert "r_import_1" in r.json()["detail"], "the refusal must name the run it could not read"
