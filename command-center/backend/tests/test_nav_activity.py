"""
`GET /system/activity` — the three booleans behind the sidebar's running-dots.

⚠ **These tests exist because the dot moved from the browser to the server.** The sidebar used
to derive "is anything running" client-side from the FULL runs / optimizations / stress-test
lists, so the predicates were visible next to the thing they drew. Now they are SQL in
`lab_db.get_nav_activity` and nothing in the UI can contradict them — which is the saving and
also the risk, so every predicate is pinned here, including the ones that must NOT match.
"""
import time

import pytest

from services import lab_db


def _strategy() -> str:
    """Same shape the shared `_insert_strategy` fixture helper uses — a hand-rolled INSERT drifts
    from the real schema and then fails for a reason that has nothing to do with the test."""
    sid = "strat_nav_activity"
    lab_db.upsert_strategy({
        "id": sid,
        "name": "Nav Activity",
        "class_name": "NavActivity",
        "source_path": "test/NavActivity.py",
        "scanned_at": int(time.time()),
        "default_params": {},
        "param_schema": [],
        "runner": "python",
    })
    return sid


def _run(run_id: str, status: str, **over) -> None:
    row = {
        "run_id": run_id,
        "strategy_id": _strategy(),
        "instrument": "XAUUSD",
        "params": {},
        "bar_type": "Minute",
        "bar_value": 15,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
        "commission_per_side": 0.0,
        "slippage_ticks": 0,
        "status": status,
        "created_at": int(time.time()),
    }
    row.update(over)
    lab_db.insert_run(row)
    # insert_run does not take these, and the predicates turn on them.
    sets, vals = [], []
    for col in ("optimization_id", "sweep_id", "stack_id"):
        if col in over:
            sets.append(f"{col} = ?")
            vals.append(over[col])
    if sets:
        with lab_db._connect() as conn:
            conn.execute(f"UPDATE backtest_runs SET {', '.join(sets)} WHERE run_id = ?",
                         (*vals, run_id))


def test_all_quiet_by_default(fresh_db):
    assert lab_db.get_nav_activity() == {
        "backtests": False, "optimizations": False, "stress_tests": False,
    }


def test_a_running_backtest_lights_backtests(fresh_db):
    _run("r_running", "running")
    assert lab_db.get_nav_activity()["backtests"] is True


def test_a_completed_backtest_lights_nothing(fresh_db):
    _run("r_done", "complete")
    assert lab_db.get_nav_activity()["backtests"] is False


def test_an_optimization_COMBO_does_not_light_backtests(fresh_db):
    """⚠ The one predicate that is easy to get wrong, and the reason this file exists.

    A combo carries `optimization_id` and belongs to the Optimizations section, whose own grid
    reports it. Counting it here would light BOTH dots for one job — mirrors `Sidebar.tsx`'s
    `!r.optimization_id`.
    """
    _run("r_combo", "running", optimization_id="opt_1")
    assert lab_db.get_nav_activity()["backtests"] is False


@pytest.mark.parametrize("child", ["sweep_id", "stack_id"])
def test_sweep_and_stack_children_DO_light_backtests(fresh_db, child):
    """They surface in the Runs tab, so the Backtests dot is the honest place for them."""
    _run(f"r_{child}", "running", **{child: "parent_1"})
    assert lab_db.get_nav_activity()["backtests"] is True


def _optimization(status: str) -> None:
    with lab_db._connect() as conn:
        conn.execute(
            "INSERT INTO optimizations (optimization_id, strategy_id, instrument, start_date, "
            "end_date, commission_per_side, slippage_ticks, mode, search_method, param_grid, "
            "status, estimated_runs, completed_runs, created_at, bar_type, bar_value, min_trades) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("opt_run", _strategy(), "XAUUSD", "2024-01-01", "2024-12-31", 0.0, 0,
             "standard", "native", "{}", status, 4, 0, int(time.time()), "Minute", 15, 0),
        )


def _stress_test(status: str, run_id: str) -> None:
    with lab_db._connect() as conn:
        conn.execute(
            "INSERT INTO stress_tests (stress_test_id, run_id, status, created_at, "
            "num_simulations, num_bootstrap, walk_forward_windows) VALUES (?,?,?,?,?,?,?)",
            (f"st_{status}", run_id, status, int(time.time()), 100, 100, 5),
        )


def test_a_running_optimization_lights_optimizations(fresh_db):
    _optimization("running")
    act = lab_db.get_nav_activity()
    assert act["optimizations"] is True
    assert act["backtests"] is False   # scopes must not bleed


def test_a_finished_optimization_lights_nothing(fresh_db):
    _optimization("complete")
    assert lab_db.get_nav_activity()["optimizations"] is False


@pytest.mark.parametrize("status", ["running", "running_wf", "running_sens"])
def test_every_stress_PHASE_lights_stress_tests(fresh_db, status):
    """⚠ `LIKE 'running%'`, not `= 'running'`. A stress test spends most of its life in
    `running_wf` / `running_sens`, so an equality check leaves the dot off for most of the run —
    which looks exactly like a test that already finished."""
    _run("r_for_stress", "complete")          # the FK target — a stress test needs a real run
    _stress_test(status, "r_for_stress")
    act = lab_db.get_nav_activity()
    assert act["stress_tests"] is True
    assert act["backtests"] is False          # its source run is finished; scopes must not bleed


def test_a_graded_stress_test_lights_nothing(fresh_db):
    _run("r_for_stress", "complete")
    _stress_test("complete", "r_for_stress")
    assert lab_db.get_nav_activity()["stress_tests"] is False


def test_endpoint_returns_the_three_keys(client):
    res = client.get("/system/activity")
    assert res.status_code == 200
    assert set(res.json()) == {"backtests", "optimizations", "stress_tests"}
    assert all(isinstance(v, bool) for v in res.json().values())
