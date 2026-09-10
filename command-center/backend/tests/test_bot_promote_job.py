"""A promote run as a background JOB reports the step it is on, from the code doing the step.

The page draws one progress indicator over a deploy (Aaron, 2026-09-10). That indicator is only
worth drawing if each step is REPORTED by the code as it enters it — a bar that advanced on a
clock would move at a speed unrelated to the deploy. So these tests pin three things: the steps
are entered in the order the work actually happens, a step that never ran never reads as done,
and a failure says what state it left the bot in, which depends on the step it hit.
"""

import ast
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException
from models import BotPromoteRequest
from routers import bots

BOT = "sos_fade_demo"
FULL = BotPromoteRequest(pull=True, allow_dirty=False, restart=True)
DEPLOYED = "bbbbbbbbbbbb0123456789"
OLD = {
    "source_hash": "aaaaaaaaaaaa",
    "started": 1000.0,
    "last_updated": "2026-09-10T10:00:00+00:00",
}
NEW = {
    "source_hash": "bbbbbbbbbbbb",
    "started": 2000.0,
    "last_updated": "2026-09-10T10:01:30+00:00",
}


def _deployed_record(hash_: str) -> dict:
    """A `deployed.json` in the shape `algos/tools/promote.py::write_pin` writes it — every field,
    under its real name. 🔴 The first fixture here returned `{"hash": ...}`, a key promote.py
    never writes, and so did the code under test: the two agreed, every test was green, and the
    confirm step could not confirm a single real deploy (2026-09-10). A fake record must be shaped
    like the real one or it certifies code against a file that does not exist."""
    return {
        "strategy_source_hash": hash_,
        "promoted_commit": "74e5ba7a",
        "promoted_at": "2026-09-10",
        "strategy_package": "sos_fade",
        "strategy_class": "SosFadeStrategy",
        "strategy_version": 218,
        "strategy_params": {},
        "files": 161,
    }


@pytest.fixture
def box(monkeypatch):
    """The VPS stubbed at the four seams a promote crosses, recording the ORDER of everything —
    the ssh calls, the stop, the start, and every step the job enters."""
    state = {
        "out": f"  pinned abc123\n{bots._PROMOTE_OK}",
        "events": [],
        "raise_at": None,
        # What the bot's own state file says, read in order: the OLD process (read just before
        # the stop), then whatever the restarted one writes on each confirm poll.
        "run_states": [OLD, NEW],
        "deployed_hash": DEPLOYED,
    }

    def read_state(k):
        state["events"].append(("read_state", k))
        seq = state["run_states"]
        return seq.pop(0) if len(seq) > 1 else seq[0]

    def ssh(cmd):
        kind = "pull" if "git pull" in cmd else "promote.py" if "promote.py" in cmd else cmd
        state["events"].append(("ssh", kind))
        if state["raise_at"] == kind:
            raise state["exc"]
        return "Already up to date." if kind == "pull" else state["out"]

    def kill(k):
        state["events"].append(("kill", k))
        if state["raise_at"] == "kill":
            raise state["exc"]
        return ""

    def launch(k):
        state["events"].append(("launch", k))
        if state["raise_at"] == "launch":
            raise state["exc"]
        return ""

    real_enter = bots._job_enter

    def enter(job, key):
        state["events"].append(("enter", key))
        real_enter(job, key)

    monkeypatch.setattr(bots, "_ssh", ssh)
    monkeypatch.setattr(bots, "_kill_bot", kill)
    monkeypatch.setattr(bots, "_launch_bot", launch)
    monkeypatch.setattr(bots, "_job_enter", enter)
    monkeypatch.setattr(bots, "_read_run_state", read_state)
    monkeypatch.setattr(bots, "_deployed_json", lambda k: _deployed_record(state["deployed_hash"]))
    monkeypatch.setattr(bots, "_notify_telegram", lambda *_a, **_k: None)
    monkeypatch.setattr(bots, "_set_alert_thread", lambda *_a, **_k: True)
    monkeypatch.setattr(bots._time, "sleep", lambda *_a: None)
    # Run the job inline, so each test reads the finished job without racing a thread.
    monkeypatch.setattr(bots, "_spawn", lambda fn: fn())
    monkeypatch.setattr(bots, "_PROMOTE_JOBS", {})
    return state


def _states(job):
    return {s.key: s.state for s in job.stages}


# ── the steps are the work, in the order it happens ──────────────────────────


def test_each_step_is_entered_immediately_before_the_work_it_names(box):
    """The indicator is only honest if `active` means *this is what the box is doing now*.
    Entering a step after its work, or all at once up front, would draw progress that did not
    happen. MUTATION: move `stage("stop")` below `_kill_bot` in `_finish_promote` → red."""
    bots.start_promote_job(BOT, FULL)
    assert box["events"] == [
        ("enter", "pull"),
        ("ssh", "pull"),
        ("enter", "build"),
        ("ssh", "promote.py"),
        ("read_state", BOT),  # the OLD process, read BEFORE it is asked to stop
        ("enter", "stop"),
        ("kill", BOT),
        ("enter", "start"),
        ("launch", BOT),
        ("enter", "confirm"),
        ("read_state", BOT),
    ]


def test_a_clean_deploy_finishes_with_every_step_done(box):
    bots.start_promote_job(BOT, FULL)
    job = bots.get_promote_job(BOT)
    assert job.status == "done"
    assert _states(job) == {
        "pull": "done",
        "build": "done",
        "stop": "done",
        "start": "done",
        "confirm": "done",
    }
    assert job.result.ok is True and job.result.restarted is True
    assert all(s.seconds is not None for s in job.stages)


# ── a step that never ran never reads as done ────────────────────────────────


def test_a_REFUSED_build_fails_that_step_and_never_touches_the_bot(box):
    """promote.py refusing (a dirty tree, a snapshot that will not import) leaves the running bot
    exactly as it was. The indicator must say the build failed and the restart did not happen —
    not paint the stop and start as done. MUTATION: mark every open step `done` in `_job_close`
    whatever the status → red."""
    box["out"] = f"Refusing to promote — a dirty tree\n{bots._PROMOTE_FAIL}"
    bots.start_promote_job(BOT, FULL)
    job = bots.get_promote_job(BOT)
    assert job.status == "failed"
    assert _states(job) == {
        "pull": "done",
        "build": "failed",
        "stop": "skipped",
        "start": "skipped",
        "confirm": "skipped",
    }
    assert ("kill", BOT) not in box["events"]
    assert job.result.ok is False and "Refusing" in job.result.output


def test_a_build_that_reported_NOTHING_is_a_failure_that_says_so(box):
    """No exit marker means nobody knows whether it deployed. It must not restart on a maybe, and
    the output must carry the doubt rather than resolve it."""
    box["out"] = "truncated"
    bots.start_promote_job(BOT, FULL)
    job = bots.get_promote_job(BOT)
    assert job.status == "failed"
    assert _states(job)["build"] == "failed"
    assert "did not report an exit status" in job.result.output
    # Structured, so the page never reads promote.py's prose to avoid calling the bot untouched.
    # MUTATION: drop the `reported is None` error → red.
    assert job.error and "may or may not have deployed" in job.error


def test_a_REFUSED_build_carries_no_error_because_the_bot_really_is_untouched(box):
    box["out"] = f"Refusing to promote — a dirty tree\n{bots._PROMOTE_FAIL}"
    bots.start_promote_job(BOT, FULL)
    assert bots.get_promote_job(BOT).error is None


def test_no_pull_asked_for_reads_SKIPPED_not_done(box):
    """`skipped` and `done` are different facts. A pull nobody asked for must not read as a pull
    that ran. MUTATION: make `_job_close` turn `pending` into `done` → red."""
    bots.start_promote_job(BOT, BotPromoteRequest(pull=False, allow_dirty=False, restart=True))
    job = bots.get_promote_job(BOT)
    assert job.status == "done"
    assert _states(job) == {
        "pull": "skipped",
        "build": "done",
        "stop": "done",
        "start": "done",
        "confirm": "done",
    }
    assert ("ssh", "pull") not in box["events"]


def test_no_restart_asked_for_skips_the_stop_and_start(box):
    bots.start_promote_job(BOT, BotPromoteRequest(pull=True, allow_dirty=False, restart=False))
    job = bots.get_promote_job(BOT)
    assert job.status == "done"
    assert _states(job) == {
        "pull": "done",
        "build": "done",
        "stop": "skipped",
        "start": "skipped",
        "confirm": "skipped",
    }
    assert job.result.restarted is False


# ── a failure says what state it left the bot in ─────────────────────────────


def test_the_box_dropping_during_the_STOP_says_the_code_is_deployed(box):
    """By the stop, promote.py has already swapped the snapshot. A message saying *nothing was
    deployed* here would send the reader to redeploy code that is already live."""
    box["raise_at"], box["exc"] = "kill", bots.VpsUnreachable("tunnel dead")
    bots.start_promote_job(BOT, FULL)
    job = bots.get_promote_job(BOT)
    assert job.status == "failed"
    assert _states(job) == {
        "pull": "done",
        "build": "done",
        "stop": "failed",
        "start": "skipped",
        "confirm": "skipped",
    }
    assert "IS deployed" in job.error
    assert ("launch", BOT) not in box["events"]


def test_a_BUILD_timeout_is_reported_as_uncertain_never_as_untouched(box):
    """promote.py may have finished on the box after this end stopped listening. *Untouched*
    would be a claim nothing measured, in the reassuring direction."""
    box["raise_at"], box["exc"] = "promote.py", subprocess.TimeoutExpired("ssh", 30)
    bots.start_promote_job(BOT, FULL)
    job = bots.get_promote_job(BOT)
    assert _states(job)["build"] == "failed"
    assert "may or may not have deployed" in job.error
    assert "untouched" not in job.error


def test_a_PULL_failure_is_the_one_that_says_untouched(box):
    box["raise_at"], box["exc"] = "pull", bots.VpsUnreachable("no route")
    bots.start_promote_job(BOT, FULL)
    job = bots.get_promote_job(BOT)
    assert _states(job) == {
        "pull": "failed",
        "build": "skipped",
        "stop": "skipped",
        "start": "skipped",
        "confirm": "skipped",
    }
    assert "untouched" in job.error


# ── one deploy of a bot at a time, and the page can find it again ────────────


def test_a_second_deploy_of_the_same_bot_while_one_runs_is_REFUSED(box, monkeypatch):
    """The page can be closed and reopened mid-deploy. Two promote.py runs over one instance
    directory, and two stop/start pairs on one process, is not a state anybody meant.
    MUTATION: drop the running-job check → red."""
    monkeypatch.setattr(bots, "_spawn", lambda fn: None)  # leave the first one running
    bots.start_promote_job(BOT, FULL)
    with pytest.raises(HTTPException) as e:
        bots.start_promote_job(BOT, FULL)
    assert e.value.status_code == 409


def test_a_running_deploy_of_ANOTHER_bot_does_not_block_this_one(box, monkeypatch):
    monkeypatch.setattr(bots, "_spawn", lambda fn: None)
    bots.start_promote_job(BOT, FULL)
    other = next(b.key for b in bots._BOTS if b.key != BOT)
    bots.start_promote_job(other, FULL)  # must not raise


def test_the_page_finds_the_RUNNING_job_by_the_bot_not_by_an_id(box, monkeypatch):
    """Reopening the drawer mid-deploy must show the run already going, not a fresh Deploy
    button over it — so the latest job is addressed by the bot."""
    monkeypatch.setattr(bots, "_spawn", lambda fn: None)
    started = bots.start_promote_job(BOT, FULL)
    found = bots.get_promote_job(BOT)
    assert found.job_id == started.job_id
    assert found.status == "running"


def test_no_job_yet_is_NULL_and_another_bots_job_is_not_mine(box):
    assert bots.get_promote_job(BOT) is None
    other = next(b.key for b in bots._BOTS if b.key != BOT)
    bots.start_promote_job(other, FULL)
    assert bots.get_promote_job(BOT) is None


def test_eviction_never_drops_a_RUNNING_job(box, monkeypatch):
    """A job evicted while it runs is a deploy the page can no longer see — and the 409 guard
    reads the same dict, so it would also let a second one start. MUTATION: evict the oldest job
    whatever its status → red."""
    monkeypatch.setattr(bots, "_PROMOTE_JOBS_CAP", 2)
    monkeypatch.setattr(bots, "_spawn", lambda fn: None)
    running = bots.start_promote_job(BOT, FULL)
    monkeypatch.setattr(bots, "_spawn", lambda fn: fn())
    others = [b.key for b in bots._BOTS if b.key != BOT]
    for _ in range(3):
        for k in others:
            bots.start_promote_job(k, FULL)
    assert running.job_id in bots._PROMOTE_JOBS


# ── the routes exist where the page calls them ───────────────────────────────


def test_the_job_routes_are_reachable_over_http(box, client):
    """A route that collides with another `/{bot_name}/…` pattern answers somebody else's
    handler, and nothing about that fails until a page calls it."""
    r = client.post(f"/bots/{BOT}/promote/job", json={"pull": True, "restart": True})
    assert r.status_code == 202, r.text
    assert r.json()["bot"] == BOT
    r = client.get(f"/bots/{BOT}/promote/job")
    assert r.status_code == 200 and r.json()["status"] == "done"


# ── the last step is a MEASUREMENT: the restarted bot reports the deployed code ──


def test_a_redeploy_of_UNCHANGED_code_is_not_confirmed_by_the_hash_alone():
    """On a re-deploy the OLD process already reports the deployed hash, so a hash match alone
    would read as confirmed while the bot is still stopped. A new start stamp and a heartbeat
    written since the stop are what separate the new process from the old one.
    MUTATION: return True on a hash match without comparing against `before` → red."""
    same = {**OLD, "source_hash": DEPLOYED[:12]}
    assert bots._is_new_process_on(same, same, DEPLOYED) is False
    restarted = {**same, "started": 3000.0, "last_updated": "2026-09-10T10:02:00+00:00"}
    assert bots._is_new_process_on(restarted, same, DEPLOYED) is True


def test_the_WRONG_hash_is_never_confirmed_whatever_the_stamps_say():
    assert bots._is_new_process_on(NEW, OLD, "cccccccccccc999") is False
    assert bots._is_new_process_on({**NEW, "source_hash": ""}, OLD, DEPLOYED) is False
    assert bots._is_new_process_on(NEW, OLD, "") is False, "an unread deployed hash confirmed"


def test_a_bot_that_never_reports_the_new_code_ends_UNCONFIRMED_not_done(box, monkeypatch):
    """The deploy worked; the bot has not shown it. `done` there would claim a measurement nobody
    took, and `failed` would send the reader to redeploy code that is already on the box.
    MUTATION: drop the `unconfirmed` branch so the step closes `done` → red."""
    monkeypatch.setattr(bots, "_CONFIRM_ATTEMPTS", 3)
    box["run_states"] = [OLD]  # the old process's stamps, for ever
    bots.start_promote_job(BOT, FULL)
    job = bots.get_promote_job(BOT)
    assert job.status == "done"
    assert _states(job)["confirm"] == "unconfirmed"
    polls = [e for e in box["events"] if e == ("read_state", BOT)]
    assert len(polls) == 1 + 3, "it did not stop asking at the limit"


def test_a_failed_read_mid_wait_is_a_blip_not_a_verdict(box):
    box["run_states"] = [OLD, None, NEW]
    bots.start_promote_job(BOT, FULL)
    assert _states(bots.get_promote_job(BOT))["confirm"] == "done"


def test_an_unreadable_deployed_hash_is_asked_again_rather_than_giving_up(box, monkeypatch):
    """Without the deployed hash nothing can confirm, so one failed read must not doom the
    whole wait to `unconfirmed`. MUTATION: read it once before the loop → red."""
    answers = [RuntimeError("blip"), _deployed_record(DEPLOYED)]

    def deployed(_k):
        a = answers.pop(0) if len(answers) > 1 else answers[0]
        if isinstance(a, Exception):
            raise a
        return a

    monkeypatch.setattr(bots, "_deployed_json", deployed)
    box["run_states"] = [OLD, NEW]
    bots.start_promote_job(BOT, FULL)
    assert _states(bots.get_promote_job(BOT))["confirm"] == "done"


def _hash_key_promote_writes() -> str:
    """The `deployed.json` key `promote.py::write_pin` stores its HASH argument under, read out of
    that file's own source. Parsed, not imported — `algos/` is another subsystem with its own
    runtime, and the question is only which string it writes."""
    src = Path(__file__).resolve().parents[3] / "algos" / "tools" / "promote.py"
    fn = next(
        n
        for n in ast.walk(ast.parse(src.read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == "write_pin"
    )
    hash_arg = fn.args.args[1].arg  # write_pin(cfg, hash_, ...)
    record = next(n for n in ast.walk(fn) if isinstance(n, ast.Dict))
    keys = [
        k.value
        for k, v in zip(record.keys, record.values)
        if isinstance(k, ast.Constant) and isinstance(v, ast.Name) and v.id == hash_arg
    ]
    assert len(keys) == 1, f"premise: write_pin stores `{hash_arg}` under exactly one key: {keys}"
    return keys[0]


def test_the_confirm_reads_the_hash_under_the_key_PROMOTE_ACTUALLY_WRITES():
    """🔴 The confirm step read `deployed.json["hash"]` and promote.py writes the hash under a
    different key, so on the box it got `""` and no real deploy was ever confirmed — while every
    test here passed, because the fake record used the same invented key as the code. This test
    asks the WRITER which key it uses, so the reader cannot drift from it again.
    MUTATION: read `rec.get("hash")` in `_deployed_hash` → red."""
    key = _hash_key_promote_writes()
    assert bots._deployed_hash({key: DEPLOYED}) == DEPLOYED
    assert bots._deployed_hash({}) == "", "a missing record must read as no hash, never a value"


def test_a_real_shaped_record_lets_the_WHOLE_job_confirm(box, monkeypatch):
    """End to end on a record in the writer's own shape — the path that broke on the box.
    MUTATION: `_await_new_version` reads the record's `hash` key again → red."""
    key = _hash_key_promote_writes()
    monkeypatch.setattr(bots, "_deployed_json", lambda _k: {key: DEPLOYED})
    bots.start_promote_job(BOT, FULL)
    assert _states(bots.get_promote_job(BOT))["confirm"] == "done"


def test_the_run_state_reader_answers_NONE_for_anything_it_cannot_read(monkeypatch):
    """`None` is *could not read*, never an old process — the confirm step treats the two
    differently. MUTATION: return `{}` on a parse failure → red."""
    assert bots._bot_state_path(BOT), "fixture premise: this bot has a state file"
    for raw, want in [
        (f'{{"{BOT}": {{"source_hash": "abc"}}}}', {"source_hash": "abc"}),
        ("", None),
        ("not json", None),
        ('{"another_bot": {}}', None),
    ]:
        monkeypatch.setattr(bots, "_ssh", lambda _c, r=raw: r)
        assert bots._read_run_state(BOT) == want, raw
