"""Per-runner job lock scopes (NT8 / MT5 / Python).

The property under test is PARTITION: every running job belongs to exactly one lock scope.
A row counted by two scopes makes one job block a platform it never touches; a row counted by
none runs unreported and lets a second job start on top of it. Python is the scope that broke
this — it was silently counted as NT8 — so each job type is checked from both sides: the owning
scope sees it, and the other two do not.
"""

import time

import pytest
from services import lab_db


def _strategy(strategy_id: str, runner: str) -> None:
    lab_db.upsert_strategy(
        {
            "id": strategy_id,
            "name": strategy_id,
            "class_name": strategy_id,
            "source_path": f"strategies/{strategy_id}",
            "scanned_at": int(time.time()),
            "runner": runner,
        }
    )


def _run(run_id: str, runner: str, status: str = "running", **extra) -> None:
    """A backtest run. `runner=None` stands in for a legacy row written before the column
    existed — those must fall to NT8, matching COALESCE(runner, 'ninjatrader')."""
    strategy_id = f"strat_{runner or 'legacy'}"
    _strategy(strategy_id, runner or "ninjatrader")
    data = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "instrument": "XAUUSD.s",
        "params": {},
        "bar_type": "Minute",
        "bar_value": 15,
        "start_date": "2025-01-01",
        "end_date": "2025-06-01",
        "commission_per_side": 0.0,
        "slippage_ticks": 0,
        "status": status,
        "created_at": int(time.time()),
    }
    if runner is not None:
        data["runner"] = runner
    data.update(extra)
    lab_db.insert_run(data)


def _optimization(opt_id: str, runner: str, status: str = "running") -> None:
    strategy_id = f"strat_{runner}"
    _strategy(strategy_id, runner)
    lab_db.insert_optimization(
        {
            "optimization_id": opt_id,
            "strategy_id": strategy_id,
            "instrument": "XAUUSD.s",
            "start_date": "2025-01-01",
            "end_date": "2025-06-01",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "ruleset_id": None,
            "mode": "raw",
            "search_method": "native",
            "param_grid": {},
            "status": status,
            "estimated_runs": 4,
        }
    )


ALL_SCOPES = ("nt8", "mt5", "python")
RUNNER_OF_SCOPE = {"nt8": "ninjatrader", "mt5": "mt5", "python": "python"}


def _assert_only_scope_busy(busy_scope: str) -> None:
    """The named scope is locked and reports the job; the other two are idle."""
    for scope in ALL_SCOPES:
        expected = scope == busy_scope
        assert lab_db.has_running_job(RUNNER_OF_SCOPE[scope]) is expected, (
            f"has_running_job({RUNNER_OF_SCOPE[scope]!r}) should be {expected} "
            f"while a {busy_scope} job runs"
        )
        assert lab_db.get_running_job()[scope]["running"] is expected, (
            f"get_running_job()[{scope!r}] should be {expected} while a {busy_scope} job runs"
        )


# ── Backtests ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("scope", ALL_SCOPES)
def test_running_backtest_locks_only_its_own_scope(fresh_db, scope):
    _run("r1", RUNNER_OF_SCOPE[scope])
    _assert_only_scope_busy(scope)


def test_legacy_run_without_a_runner_falls_to_nt8(fresh_db):
    _run("r1", None)
    _assert_only_scope_busy("nt8")


# ── Optimizations ─────────────────────────────────────────────────────────────
# `optimizations` has no runner column — the scope comes from the joined strategy. Without the
# join every optimization would land in NT8's bucket and block NinjaTrader.


@pytest.mark.parametrize("scope", ALL_SCOPES)
def test_running_optimization_locks_only_its_own_scope(fresh_db, scope):
    _optimization("o1", RUNNER_OF_SCOPE[scope])
    _assert_only_scope_busy(scope)


# ── Sweeps ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("scope", ALL_SCOPES)
def test_running_sweep_child_locks_only_its_own_scope(fresh_db, scope):
    runner = RUNNER_OF_SCOPE[scope]
    _strategy(f"strat_{runner}", runner)
    lab_db.insert_run_sweep(
        {
            "run_id": "r1",
            "strategy_id": f"strat_{runner}",
            "instrument": "XAUUSD.s",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 15,
            "start_date": "2025-01-01",
            "end_date": "2025-06-01",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "status": "running",
            "created_at": int(time.time()),
            "sweep_id": "s1",
            "source_run_id": None,
            "runner": runner,
        }
    )
    _assert_only_scope_busy(scope)


# ── Idle / finished ───────────────────────────────────────────────────────────


def test_no_jobs_means_every_scope_is_idle(fresh_db):
    for scope in ALL_SCOPES:
        assert lab_db.has_running_job(RUNNER_OF_SCOPE[scope]) is False
        assert lab_db.get_running_job()[scope]["running"] is False


def test_completed_job_releases_its_lock(fresh_db):
    _run("r1", "python", status="complete")
    assert lab_db.has_running_job("python") is False
    assert lab_db.get_running_job()["python"]["running"] is False


def test_scopes_lock_independently_and_concurrently(fresh_db):
    """The point of separate scopes: all three can run at once without blocking each other."""
    _run("r_nt8", "ninjatrader")
    _run("r_mt5", "mt5")
    _run("r_py", "python")
    job = lab_db.get_running_job()
    for scope in ALL_SCOPES:
        assert lab_db.has_running_job(RUNNER_OF_SCOPE[scope]) is True
        assert job[scope]["running"] is True
    # Each scope reports ITS job, not another scope's.
    assert job["nt8"]["job_id"] == "r_nt8"
    assert job["mt5"]["job_id"] == "r_mt5"
    assert job["python"]["job_id"] == "r_py"


def test_unknown_runner_is_treated_as_nt8(fresh_db):
    """has_running_job()'s contract: anything not mt5/python is NT8. A typo'd runner must
    still take a lock — an unlocked job is worse than one locked to the wrong platform."""
    _run("r1", "ninjatrader")
    assert lab_db.has_running_job("some_future_runner") is True


# ── NinjaTrader switched off ON PURPOSE refuses NT8 jobs up front ─────────────


@pytest.mark.parametrize("runner", ["ninjatrader", None, "some_future_runner"])
def test_an_NT8_job_is_refused_with_the_reason_while_NT8_is_switched_off(
    fresh_db, monkeypatch, runner
):
    """Before this, an NT8 backtest was accepted, a run row inserted, and the job died at dispatch
    on 'Remote end closed connection' — the app not knowing why. Refused at the one gate every
    trigger passes, naming the reason. Same NT8 fallback as `has_running_job`.
    MUTATION: drop the switched-off check — no HTTPException (reddens)."""
    from fastapi import HTTPException
    from routers._locks import ensure_platform_idle
    from services import nt8_switch

    monkeypatch.setattr(nt8_switch, "_state", nt8_switch.DISABLED)
    with pytest.raises(HTTPException) as exc:
        ensure_platform_idle(runner)
    assert exc.value.status_code == 503
    assert "switched off" in exc.value.detail


@pytest.mark.parametrize("runner", ["mt5", "python"])
def test_MT5_and_python_jobs_are_untouched_by_NT8_being_off(fresh_db, monkeypatch, runner):
    """MUTATION: refuse every runner while NT8 is off — reddens both."""
    from routers._locks import ensure_platform_idle
    from services import nt8_switch

    monkeypatch.setattr(nt8_switch, "_state", nt8_switch.DISABLED)
    ensure_platform_idle(runner)  # must not raise


def test_an_UNASKED_box_does_not_refuse_an_NT8_job(fresh_db, monkeypatch):
    """`None` = the box has not answered yet — the job tries, exactly as before the switch.
    MUTATION: refuse on `is not False` — reddens this."""
    from routers._locks import ensure_platform_idle
    from services import nt8_switch

    monkeypatch.setattr(nt8_switch, "_state", None)
    ensure_platform_idle("ninjatrader")  # must not raise
