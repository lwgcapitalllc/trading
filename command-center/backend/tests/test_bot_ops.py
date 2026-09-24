"""One action at a time per bot, and an account holds still while one of its bots is mid-action.

Aaron, 2026-09-24: *"if I'm updating a bot I shouldn't be able to stop and restart it."* Every
action checked only itself — a deploy refused a second deploy and nothing else, so a Stop pressed
mid-deploy raced the deploy's own stop/start on a live process. Rules: `services/bot_ops.py`.

⚠ A fail-watch against HEAD is VACUOUS for most of these — the lock did not exist, so the call
simply went through. Non-vacuity is by MUTATION, named per test.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from models import BotPromoteRequest
from routers import bots
from services import bot_ops, promote_jobs

REQ = BotPromoteRequest(pull=False, restart=True, allow_dirty=False)


@pytest.fixture
def box(monkeypatch):
    """Every call that would reach the trading box, recorded instead."""
    calls: list[str] = []
    monkeypatch.setattr(bots, "_kill_bot", lambda k: calls.append(f"kill {k}") or "")
    monkeypatch.setattr(bots, "_launch_bot", lambda k: calls.append(f"launch {k}") or "")
    monkeypatch.setattr(bots, "_suppress_stop_alert", lambda k: None)
    monkeypatch.setattr(bots, "_refuse_if_benched", lambda k: None)
    monkeypatch.setattr(bots, "_notify_telegram", lambda *a, **k: None)
    monkeypatch.setattr(
        bots,
        "_time",
        type(
            "T", (), {"sleep": staticmethod(lambda s: None), "time": staticmethod(bots._time.time)}
        ),
    )
    return calls


def _held_deploy(monkeypatch, bot_key="sos_fade_demo") -> None:
    """A deploy of `bot_key` in flight: started, its thread not yet finished."""
    monkeypatch.setattr(bots, "_spawn", lambda fn: None)
    bots._begin_promote_job(bot_key, REQ)


# ── the lock itself ────────────────────────────────────────────────────────────


def test_a_second_claim_is_refused_with_the_first_ones_name():
    bot_ops.claim("x", "deploying")
    with pytest.raises(bot_ops.Busy, match="SOS Fade is deploying"):
        bot_ops.claim("x", "restarting", "SOS Fade")


def test_hold_releases_however_the_block_ends():
    with pytest.raises(RuntimeError):
        with bot_ops.hold("x", "restarting"):
            raise RuntimeError
    assert bot_ops.doing("x") is None


def test_a_handed_over_claim_is_not_cleared_by_the_one_that_handed_it():
    """A move that starts a deploy must not free the bot when the move's own request ends.
    MUTATION: `hold` releases unconditionally — this reddens (killed 2026-09-24)."""
    with bot_ops.hold("x", "being moved"):
        assert bot_ops.hand_over("x", "being moved", "deploying")
    assert bot_ops.doing("x") == "deploying"


# ── a deploy holds its bot ─────────────────────────────────────────────────────


@pytest.mark.parametrize("action", ["stop_bot", "start_bot", "restart_bot"])
def test_stop_start_and_restart_are_refused_mid_deploy_and_never_reach_the_box(
    monkeypatch, box, action
):
    """THE REPORTED DEFECT. MUTATION: drop `_acting` from the three routes — every case reddens
    (killed 2026-09-24)."""
    _held_deploy(monkeypatch)
    with pytest.raises(HTTPException) as e:
        getattr(bots, action)("sos_fade_demo")
    assert e.value.status_code == 409 and "deploying" in e.value.detail
    assert box == [], "the box was touched while a deploy held the bot"


def test_a_deploy_is_refused_while_a_restart_is_in_flight(monkeypatch):
    """The other direction. MUTATION: `_begin_promote_job` without its claim — this reddens
    (killed 2026-09-24)."""
    monkeypatch.setattr(bots, "_spawn", lambda fn: None)
    bot_ops.claim("sos_fade_demo", bots._RESTARTING)
    with pytest.raises(ValueError, match="restarting"):
        bots._begin_promote_job("sos_fade_demo", REQ)


def test_another_bot_is_not_held_by_this_ones_deploy(monkeypatch, box):
    _held_deploy(monkeypatch, "sos_fade_demo")
    bots.stop_bot("extreme_leg_demo")
    assert box == ["kill extreme_leg_demo"]


@pytest.mark.parametrize("ends", ["finishes", "raises"])
def test_the_deploy_frees_its_bot_when_its_thread_ends(monkeypatch, ends):
    """MUTATION: drop the `finally` release in `_run_promote_job` — both cases redden, and the bot
    is locked until the backend restarts (killed 2026-09-24)."""
    ran = []
    monkeypatch.setattr(bots, "_spawn", lambda fn: ran.append(fn))

    def steps(job, bot_key, req):
        if ends == "raises":
            raise RuntimeError("box went away")

    monkeypatch.setattr(bots, "_run_promote_steps", steps)
    bots._begin_promote_job("sos_fade_demo", REQ)
    assert bot_ops.doing("sos_fade_demo") == "deploying"
    try:
        ran[0]()
    except RuntimeError:
        pass
    assert bot_ops.doing("sos_fade_demo") is None


def test_a_move_hands_its_claim_to_the_deploy_it_starts(monkeypatch):
    """No gap between the move and its deploy for a Start to slip into."""
    monkeypatch.setattr(bots, "_spawn", lambda fn: None)
    with bot_ops.hold("sos_fade_demo", bots._MOVING):
        bots._begin_promote_job("sos_fade_demo", REQ, take_over=bots._MOVING)
    assert bot_ops.doing("sos_fade_demo") == "deploying"


# ── the account holds still ────────────────────────────────────────────────────


def _an_account_with_a_bot() -> tuple[int, str]:
    for g in bots._account_groups():
        if g.kind == "account" and g.account is not None and g.bots:
            return g.account, g.bots[0].key
    pytest.skip("no bot is on an account in this checkout")


@pytest.mark.parametrize(
    "route",
    [
        "set_account_risk_cap",
        "set_account_risk",
        "set_account_priority",
        "register_account",
        "unregister_account",
    ],
)
def test_an_account_write_is_refused_while_one_of_its_bots_is_deploying(monkeypatch, route):
    """MUTATION: drop `_refuse_if_account_busy` from the five routes — every case reddens
    (killed 2026-09-24). The body is never reached, so the arguments are never read."""
    account, key = _an_account_with_a_bot()
    _held_deploy(monkeypatch, key)
    args = {"unregister_account": (account,)}.get(route, (account, None))
    with pytest.raises(HTTPException) as e:
        getattr(bots, route)(*args)
    assert e.value.status_code == 409 and "deploying" in e.value.detail


def test_a_bot_may_not_join_an_account_whose_bot_is_deploying(monkeypatch):
    """MUTATION: drop the destination check from `set_bot_account` — this reddens (killed
    2026-09-24)."""
    account, key = _an_account_with_a_bot()
    _held_deploy(monkeypatch, key)
    other = next(b.key for b in bots._BOTS if b.key != key)
    with pytest.raises(HTTPException) as e:
        bots.set_bot_account(other, bots.BotAccountAssign(account=account))
    assert e.value.status_code == 409 and "deploying" in e.value.detail
    assert bot_ops.doing(other) is None, "the refused move left its bot held"


def test_the_fleet_stop_is_refused_mid_deploy_and_holds_nothing_after(monkeypatch, box):
    """MUTATION: `_acting_all` keeps the claims it made before the refusal — the second assert
    reddens (killed 2026-09-24)."""
    monkeypatch.setattr(bots, "_stop_procs", lambda: box.append("stop all") or "")
    _held_deploy(monkeypatch, bots._BOTS[-1].key)
    with pytest.raises(HTTPException) as e:
        bots.stop_bots()
    assert e.value.status_code == 409 and box == []
    assert set(bot_ops.snapshot()) == {bots._BOTS[-1].key}


# ── a deploy survives a restart as a record ───────────────────────────────────


def test_a_job_left_running_is_read_back_as_failed_at_its_step(tmp_path):
    """THE 2026-09-24 LOSS: the backend restarted mid-deploy and the job vanished.
    MUTATION: `load` returns the jobs untouched — this reddens (killed 2026-09-24)."""
    f = tmp_path / "jobs.json"
    stages = {
        k: {"state": "pending", "started": None, "ended": None} for k in bots._PROMOTE_STAGE_KEYS
    }
    stages["pull"] = {"state": "done", "started": 100.0, "ended": 110.0}
    stages["build"] = {"state": "active", "started": 110.0, "ended": None}
    job = {
        "job_id": "pj_1",
        "bot": "sos_fade_demo",
        "status": "running",
        "stages": stages,
        "result": None,
        "error": None,
        "started": 100.0,
        "ended": None,
    }
    promote_jobs.save({"pj_1": job}, f)

    back = promote_jobs.load(
        lambda stage: bots._describe_job_failure(
            stage, what="was cut off when the Command Center restarted"
        ),
        f,
    )["pj_1"]
    assert back["status"] == "failed"
    assert back["stages"]["build"]["state"] == "failed"
    assert back["stages"]["stop"]["state"] == "skipped"
    assert "build was cut off" in back["error"] and "may or may not have deployed" in back["error"]
    assert back["ended"] == 110.0, "ended at the last moment it was known alive"
    assert bots._job_view(back).status == "failed"


def test_a_saved_job_with_a_result_reads_back(tmp_path):
    f = tmp_path / "jobs.json"
    job = {
        "job_id": "pj_2",
        "bot": "b",
        "status": "done",
        "stages": {},
        "started": 1.0,
        "ended": 2.0,
        "error": None,
        "result": bots.BotPromoteResult(ok=True, output="x", restarted=True),
    }
    promote_jobs.save({"pj_2": job}, f)
    assert json.loads(f.read_text())["pj_2"]["result"]["restarted"] is True


def test_an_empty_path_turns_saving_off(tmp_path, monkeypatch):
    monkeypatch.setenv("CC_PROMOTE_JOBS_FILE", "")
    assert promote_jobs.path() is None
    promote_jobs.save({"a": {}})
    assert promote_jobs.load(lambda s: "") == {}
