"""The stop / rerun / poll lifecycle of a single backtest run.

Every test here was written against a defect found in the 2026-08-06 audit of the Backtests list
and the Backtest detail page, and every one of them fails against the code as it was:

* Stop read the job id out of `lab_progress.json` — ONE file shared by every runner — so it could
  cancel another platform's job while marking THIS run cancelled and releasing its lock.
* Stop did not stop the poller, so a cancelled run's results were written over it as `complete`.
* A rerun deleted two of a run's six-plus artefacts, so the Price tab, the Blocked/Missed layers,
  the regime calendar and the `sized` flag all described the PREVIOUS attempt.
* A ten-minute wall clock killed a healthy heartbeating job and blamed the agent for it.

The shape they share is worth stating: none of these produced an error. Each one reported success
while doing something other than what it said.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch


# ── Stop cancels THIS run's job ───────────────────────────────────────────────

def _running_run(lab_db, run_id="stoprun12345", runner="python"):
    lab_db.upsert_strategy({
        "id": "stop_strategy", "name": "Stop Strategy", "runner": runner,
        "class_name": "StopStrategy", "source_path": "strategies/python/stop",
        "scanned_at": int(time.time()), "param_schema": [], "default_params": {},
    })
    lab_db.insert_run({
        "run_id": run_id, "strategy_id": "stop_strategy", "instrument": "XAUUSD",
        "params": {}, "bar_type": "Minute", "bar_value": 15,
        "start_date": "2024-01-01", "end_date": "2024-06-30",
        "commission_per_side": 0.0, "slippage_ticks": 0,
        "status": "running", "created_at": int(time.time()), "runner": runner,
    })
    return run_id


def test_stop_cancels_this_runs_job_not_the_progress_files(client, fresh_db):
    """The job id is the RUN id. It used to come from the shared progress file.

    The file is global across nt8/mt5/python, so whatever wrote progress most recently was what
    got cancelled — another platform's live job when two were busy, or a stale id (the live file
    held `"j2"` when this was found). The failure was swallowed, so the run was marked cancelled,
    its platform lock released, and the real job carried on.
    """
    from services import lab_db
    run_id = _running_run(lab_db)

    seen = {}

    def _cancel(job_id, runner=None):
        seen["job_id"] = job_id
        return {"status": "cancelling"}

    with (
        patch("routers.backtests.read_progress", return_value={"job_id": "some-other-platforms-job"}),
        patch("services.runner_dispatch.cancel_job", side_effect=_cancel),
    ):
        r = client.post(f"/backtests/runs/{run_id}/stop")

    assert r.status_code == 200
    assert seen["job_id"] == run_id


def test_stop_does_not_clear_another_platforms_progress(client, fresh_db):
    """`clear_progress()` was unconditional, so stopping one run blanked another's live banner."""
    from services import lab_db
    run_id = _running_run(lab_db)

    cleared = {"called": False}

    def _clear():
        cleared["called"] = True

    with (
        patch("routers.backtests.read_progress", return_value={"job_id": "another-job"}),
        patch("routers.backtests.clear_progress", side_effect=_clear),
        patch("services.runner_dispatch.cancel_job", return_value={"status": "cancelling"}),
    ):
        client.post(f"/backtests/runs/{run_id}/stop")

    assert cleared["called"] is False


def test_stop_clears_progress_when_the_entry_is_this_run(client, fresh_db):
    """The other half of the rule — our own stale entry must go, or the banner keeps its error.

    ⚠ This is the ONE test in this file that passed against HEAD, and it is kept deliberately and
    labelled: the old code cleared progress unconditionally, so it satisfied this by accident while
    failing the test above. It pins the half of the rule that was always right, and a rule stated
    in only one direction is the one that gets "simplified" back.
    """
    from services import lab_db
    run_id = _running_run(lab_db)

    cleared = {"called": False}

    with (
        patch("routers.backtests.read_progress", return_value={"job_id": run_id}),
        patch("routers.backtests.clear_progress", side_effect=lambda: cleared.__setitem__("called", True)),
        patch("services.runner_dispatch.cancel_job", return_value={"status": "cancelling"}),
    ):
        client.post(f"/backtests/runs/{run_id}/stop")

    assert cleared["called"] is True


def test_stop_reports_whether_the_runner_acknowledged(client, fresh_db):
    """The row is cancelled either way — but 'we told the runner' and 'we could not reach it' are
    different facts, and only the first means the machine is actually free."""
    from services import lab_db

    ok_id = _running_run(lab_db, "stopok123456")
    with patch("services.runner_dispatch.cancel_job", return_value={"status": "cancelling"}):
        r = client.post(f"/backtests/runs/{ok_id}/stop")
    assert r.json()["job_stopped"] is True

    bad_id = _running_run(lab_db, "stopbad12345")
    with patch("services.runner_dispatch.cancel_job", side_effect=RuntimeError("agent down")):
        r = client.post(f"/backtests/runs/{bad_id}/stop")
    assert r.status_code == 200
    assert r.json()["job_stopped"] is False
    assert lab_db.get_run(bad_id)["status"] == "failed_cancelled"


def test_stop_marks_the_row_before_reaching_for_the_runner(client, fresh_db):
    """The poller reads this row every tick. Cancelling the agent first leaves a window in which
    the job finishes and `_handle_complete` writes `complete` over the cancellation."""
    from services import lab_db
    run_id = _running_run(lab_db)

    status_at_cancel = {}

    def _cancel(job_id, runner=None):
        status_at_cancel["status"] = lab_db.get_run(run_id)["status"]
        return {"status": "cancelling"}

    with patch("services.runner_dispatch.cancel_job", side_effect=_cancel):
        client.post(f"/backtests/runs/{run_id}/stop")

    assert status_at_cancel["status"] == "failed_cancelled"


# ── The poller stands down on a cancelled row ─────────────────────────────────

def test_run_was_cancelled_reads_the_row(fresh_db):
    from services import lab_db
    from services.backtest_runner import run_was_cancelled

    run_id = _running_run(lab_db, "pollrun12345")
    assert run_was_cancelled(run_id) is False

    lab_db.update_run_status(run_id, "failed_cancelled", "Cancelled by user")
    assert run_was_cancelled(run_id) is True


def test_an_unreadable_row_does_not_abandon_a_live_run(fresh_db):
    """A momentary read failure must not look like a cancellation — the poller carrying on is
    recoverable, abandoning a live run because sqlite was busy is not."""
    from services.backtest_runner import run_was_cancelled

    with patch("services.lab_db.get_run", side_effect=RuntimeError("database is locked")):
        assert run_was_cancelled("anything") is False


def test_a_cancelled_run_does_not_come_back_as_complete(fresh_db):
    """`_handle_complete` re-checks AFTER fetching results, because that await is where a Stop
    lands most often and everything below it writes."""
    from services import lab_db
    from services import backtest_runner

    run_id = _running_run(lab_db, "resurrect123")
    lab_db.update_run_status(run_id, "failed_cancelled", "Cancelled by user")

    results = {"kpis": {"net_pnl": 999.0}, "equity_curve": [], "daily_pnl": []}
    with patch("services.runner_dispatch.job_results", return_value=results):
        asyncio.run(backtest_runner._handle_complete(
            run_id, run_id, "stop_strategy", "XAUUSD", [], 0.0,
        ))

    assert lab_db.get_run(run_id)["status"] == "failed_cancelled"


# ── The stall kill and the runtime ceiling are different diagnoses ────────────

def test_a_heartbeating_job_is_not_killed_at_ten_minutes():
    """`(now - started_at) > _STALL_KILL_SEC` killed a perfectly healthy job and wrote
    "No heartbeat for 0s". The longest completed run in the lab is 275s, so it had not yet bitten
    — a tick-mode run or a slower box crosses it, and the message blames the agent."""
    from services import backtest_runner as br

    assert br._MAX_RUNTIME_SEC > br._STALL_KILL_SEC
    # 20 minutes is a long backtest, not a stalled one.
    assert 20 * 60 < br._MAX_RUNTIME_SEC


# ── An optional artefact's absence is what removes its chart layer ────────────

def test_write_or_clear_removes_a_stale_file(tmp_path):
    """`if blocked:` left the PREVIOUS attempt's refusals on disk, and the chart drew them over
    the new run's candles as though this run had produced them."""
    from services.backtest_runner import _write_or_clear

    path = tmp_path / "blocked_setups.json"
    _write_or_clear(path, [{"reason": "no fvg"}])
    assert json.loads(path.read_text()) == [{"reason": "no fvg"}]

    _write_or_clear(path, [])
    assert not path.exists()

    # Idempotent — a run that never had one must not raise.
    _write_or_clear(path, [])
    assert not path.exists()


# ── A rerun starts from an empty run directory ───────────────────────────────

def test_retry_clears_every_derived_artefact(client, fresh_db, tmp_path):
    """Only `equity_curve.json` and `daily_pnl.json` were deleted. `chart_spec.json` is CACHED, so
    the Price tab drew the old run's candles and trades; `blocked_setups.json` and
    `missed_setups.json` are written only when non-empty, so the old refusals survived; and
    `engine_timeline.json` kept `sized` true on a run that no longer was.
    """
    from services import lab_db
    from routers import backtests as bt

    run_id = _running_run(lab_db, "retrywipe123")
    lab_db.update_run_complete(run_id, {"net_pnl": 1.0, "trade_count": 1}, {})

    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    artefacts = [
        "equity_curve.json", "daily_pnl.json", "chart_spec.json",
        "blocked_setups.json", "missed_setups.json", "regime_timeline.json",
        "engine_timeline.json", "ruleset_sizing.json",
    ]
    for name in artefacts:
        (run_dir / name).write_text("[]")

    with (
        patch.object(bt, "LAB_RESULTS_DIR", tmp_path),
        patch("routers.backtests.run_backtest_job", new_callable=AsyncMock),
        patch("services.runner_dispatch.start_backtest", return_value={"status": "ok"}),
    ):
        r = client.post(f"/backtests/runs/{run_id}/retry")

    assert r.status_code == 202
    assert not run_dir.exists(), f"left behind: {[p.name for p in run_dir.iterdir()]}"
