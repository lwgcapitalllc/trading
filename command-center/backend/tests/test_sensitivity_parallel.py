"""Sensitivity runs its shifts in PARALLEL — the plan, the matcher, and the estimate.

Why this exists: the phase ran 60 full-history replays one at a time on a 12-core box.
MEASURED before the change — 69s per child (65-71s across children, i.e. compute-bound rather
than I/O), so ~69 minutes on one core while `backtest/optimizer.run_sweep` had been fanning
optimizer grids across every core the whole time.

⚠ The obvious fix does not work and would look like it did: `python_runner.start_backtest` runs
each backtest on a THREAD, and an engine replay is pure Python stepping one bar at a time, so it
is GIL-bound. `asyncio.gather` over the old per-child path buys almost nothing. It needs
processes, which is what `run_sweep` already provides.
"""

import asyncio
import json

import pytest

from services import lab_db, stress_tester
from services.stress_tester import (
    sensitivity_plan,
    _estimate_sens_duration_min,
    _run_shifts_pooled,
)

# Two params, so a cartesian product would be visibly different from one-at-a-time.
PARAMS = [
    {"name": "aplus_window", "type": "int", "min": 1, "max": 20000},
    {"name": "exec_tp1_pct", "type": "float", "min": 0.0, "max": 100.0},
]
BASE = {"aplus_window": 4320, "exec_tp1_pct": 40.0}
SHIFTS = [("+10%", 1.10), ("-10%", 0.90)]


# ── The plan ──────────────────────────────────────────────────────────────────

def test_the_plan_moves_ONE_param_at_a_time_not_a_grid():
    """Sensitivity asks "what does THIS setting do", so each entry perturbs exactly one param.
    The cartesian product of the same shifts is a different, much larger experiment — which is
    what `expand_grid` would have produced had the shifts been fed through it."""
    plan, _ = sensitivity_plan(PARAMS, BASE, SHIFTS)
    assert len(plan) == 4                      # 2 params x 2 shifts, NOT 2x2 combinations
    assert {e["param"] for e in plan} == {"aplus_window", "exec_tp1_pct"}
    for e in plan:
        assert set(e) == {"param", "label", "value"}


def test_a_shift_landing_back_on_the_baseline_is_skipped_and_named():
    """0 x 1.10 == 0 re-runs the identical backtest and books a 0% delta, which reads as
    "rock solid" when the truth is "never measured"."""
    plan, skipped = sensitivity_plan(
        [{"name": "exec_tp2_pct", "type": "float"}], {"exec_tp2_pct": 0.0}, SHIFTS)
    assert plan == []
    assert len(skipped) == 2 and all("exec_tp2_pct" in s for s in skipped)


def test_an_int_that_rounds_onto_a_value_already_planned_runs_once():
    plan, skipped = sensitivity_plan(
        [{"name": "pivot", "type": "int"}], {"pivot": 5},
        [("+10%", 1.10), ("+25%", 1.25)])           # 5.5 -> 6 and 6.25 -> 6
    assert [e["value"] for e in plan] == [6]
    assert any("(=6)" in s for s in skipped)


def test_param_and_value_identify_a_shift_uniquely():
    """The pooled matcher keys on (param, value). If that pair could repeat, one shift's numbers
    would be attributed to another — so the plan must guarantee it, and it does via the per-param
    `seen_vals` dedupe."""
    plan, _ = sensitivity_plan(PARAMS, BASE, [("+10%", 1.10), ("-10%", 0.90),
                                              ("+25%", 1.25), ("-25%", 0.75)])
    keys = [(e["param"], e["value"]) for e in plan]
    assert len(keys) == len(set(keys))


# ── The matcher ───────────────────────────────────────────────────────────────

def _ctx(fresh_db_seeded):
    return {
        "stress_test_id": "st1",
        "source_run": lab_db.get_run("src"),
        "strategy": {"class_name": "SosFade"},
        "runner": "python",
        "base_params": BASE,
        "measured_on": {"cost_layers": ["spread"], "broker_profile": "vantage_demo",
                        "sizing_mode": "consistent", "manual_risk_pct": None},
    }


def _seed(fresh_db):
    with lab_db._connect() as conn:
        conn.execute("INSERT OR IGNORE INTO strategies "
                     "(id, name, class_name, source_path, scanned_at, runner) "
                     "VALUES ('s1','S','SosFade','x.py',1,'python')")
        conn.execute(
            "INSERT INTO backtest_runs (run_id, strategy_id, instrument, params, bar_type, "
            "bar_value, start_date, end_date, commission_per_side, slippage_ticks, status, "
            "created_at) VALUES ('src','s1','XAUUSD','{}','Minute',15,'2020-01-01','2026-01-01',"
            "0,0,'complete',1)")
        conn.execute("INSERT INTO stress_tests (stress_test_id, run_id, status, created_at) "
                     "VALUES ('st1','src','running_sens',1)")


def _fake_dispatch(monkeypatch, combos):
    """Stand in for runner_dispatch: the sweep 'runs' and returns `combos` verbatim."""
    from services import runner_dispatch
    monkeypatch.setattr(runner_dispatch, "start_native_optimization",
                        lambda spec, runner: {"job_id": spec["job_id"], "status": "running"},
                        raising=False)
    monkeypatch.setattr(runner_dispatch, "job_status",
                        lambda job_id, runner=None: {"status": "complete"}, raising=False)
    monkeypatch.setattr(runner_dispatch, "native_opt_results",
                        lambda job_id, runner=None: {"combos": combos}, raising=False)
    monkeypatch.setattr(stress_tester, "_POLL_INTERVAL", 0)


def test_results_are_matched_by_param_and_value_never_by_index(fresh_db, monkeypatch):
    """🔴 `run_sweep` COMPACTS its result list on cancellation — `[r for r in results if r]` — so a
    cancelled sweep returns fewer rows than combos. Matching by index would then hand one shift's
    profit factor to a different parameter, silently and with no error."""
    _seed(fresh_db)
    plan, _ = sensitivity_plan(PARAMS, BASE, SHIFTS)
    # The sweep comes back SHORT and OUT OF ORDER — the shape a cancel produces.
    combos = [
        {"params": {"exec_tp1_pct": plan[3]["value"]}, "kpis": {"profit_factor": 9.9, "net_pnl": 99.0}},
        {"params": {"aplus_window": plan[0]["value"]}, "kpis": {"profit_factor": 1.1, "net_pnl": 11.0}},
    ]
    _fake_dispatch(monkeypatch, combos)

    out = asyncio.run(_run_shifts_pooled(plan, _ctx(fresh_db)))
    by = {(r["entry"]["param"], r["entry"]["label"]): r for r in out}
    assert by[("aplus_window", "+10%")]["pf"] == 1.1
    assert by[("exec_tp1_pct", "-10%")]["pf"] == 9.9
    # The two the sweep never returned are FAILED, not silently zero.
    assert by[("aplus_window", "-10%")]["ok"] is False
    assert by[("exec_tp1_pct", "+10%")]["ok"] is False


def test_a_shift_the_sweep_did_not_return_is_failed_not_a_zero_row(fresh_db, monkeypatch):
    """A `complete` child with 0 KPIs scores as "this parameter does nothing" — the most
    reassuring answer available for a measurement that never happened."""
    _seed(fresh_db)
    plan, _ = sensitivity_plan([PARAMS[0]], BASE, [("+10%", 1.10)])
    _fake_dispatch(monkeypatch, [])

    out = asyncio.run(_run_shifts_pooled(plan, _ctx(fresh_db)))
    assert out[0]["ok"] is False and out[0]["pf"] is None
    assert lab_db.get_run(out[0]["run_id"])["status"].startswith("failed")


def test_every_pooled_child_carries_the_baselines_physics(fresh_db, monkeypatch):
    """The audit's load-bearing fix must survive the executor swap: a child measured on a
    different cost model reports the cost gap as the parameter's fragility."""
    _seed(fresh_db)
    plan, _ = sensitivity_plan([PARAMS[0]], BASE, [("+10%", 1.10)])
    _fake_dispatch(monkeypatch, [{"params": {"aplus_window": plan[0]["value"]},
                                  "kpis": {"profit_factor": 2.0, "net_pnl": 5.0}}])

    out = asyncio.run(_run_shifts_pooled(plan, _ctx(fresh_db)))
    child = lab_db.get_run(out[0]["run_id"])
    # `cost_layers` is stored as raw JSON TEXT; the router parses it on the way out. Compare the
    # PARSED value — `set(row["cost_layers"])` on the string iterates its characters, which is the
    # trap `/runs/{id}/repriced` hit on 2026-08-03.
    stored = child["cost_layers"]
    parsed = json.loads(stored) if isinstance(stored, str) else stored
    assert parsed == ["spread"]
    assert child["broker_profile"] == "vantage_demo"
    assert child["sizing_mode"] == "consistent"


# ── The estimate ──────────────────────────────────────────────────────────────

def test_the_estimate_uses_the_runs_own_duration_not_a_constant():
    """`_mins_per_job` says 0.2 min for python. A 6.6-year M15 replay measured 69s a child, so the
    modal quoted ~12 min for a ~69 min job. The source run is the same replay over the same bars."""
    run = {"started_at": 0, "completed_at": 69}          # 69 seconds
    slow = _estimate_sens_duration_min(15, "python", run)
    fast = _estimate_sens_duration_min(15, "python", None)
    assert slow > fast


def test_the_python_estimate_accounts_for_the_workers():
    """Sixty jobs over eleven workers is not sixty jobs of wall clock."""
    run = {"started_at": 0, "completed_at": 60}
    est = _estimate_sens_duration_min(15, "python", run)
    serial = 15 * 4 * 1.0                                # 60 jobs x 1 min
    assert est < serial


def test_a_non_python_runner_is_not_divided_by_workers():
    """MT5 and NT8 drive ONE terminal each — there is nothing to run in parallel on, so quoting a
    divided estimate would promise a wait the machine cannot meet."""
    run = {"started_at": 0, "completed_at": 60}
    est = _estimate_sens_duration_min(10, "mt5", run)
    assert est >= 10 * 2 * 1.0
