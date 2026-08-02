"""What the optimizer holds the NON-swept params at, and what may be swept.

Two properties, both of which failed silently before 2026-08-02:

1. The optimize modal shows the SOURCE RUN's values and labels them "inherited". The grid was
   built from the strategy's scanned `default_params` instead, so optimizing from a tuned run
   quietly tested a different configuration from the one on screen — with nothing on the page
   able to say so. `base_params_for` is the seam.
2. A param with a closed set of values (a dropdown, an on/off) can now be swept as a LIST. Only
   the Python runner expands a grid locally; NT8 and MT5 hand a Start/Step/End range to their own
   tester, so a list sent there would produce a job that optimizes nothing.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest

from services import lab_db
from services.optimization_runner import _expand_axis, base_params_for, expand_grid


# ── helpers ───────────────────────────────────────────────────────────────────

def _strategy(strategy_id: str, runner: str, defaults: dict) -> dict:
    lab_db.upsert_strategy({
        "id": strategy_id,
        "name": strategy_id,
        "class_name": strategy_id,
        "source_path": f"strategies/{strategy_id}",
        "scanned_at": int(time.time()),
        "runner": runner,
        "default_params": defaults,
        "param_schema": [],
    })
    return lab_db.get_strategy(strategy_id)


def _run(run_id: str, strategy_id: str, params: dict) -> str:
    lab_db.insert_run({
        "run_id": run_id, "strategy_id": strategy_id, "instrument": "XAUUSD.s",
        "params": params, "bar_type": "Minute", "bar_value": 15,
        "start_date": "2025-01-01", "end_date": "2025-06-01",
        "commission_per_side": 0.0, "slippage_ticks": 0,
        "status": "complete", "created_at": int(time.time()),
    })
    return run_id


# ── 1. "inherited" has to mean inherited ──────────────────────────────────────

def test_a_non_swept_param_takes_the_source_runs_value_not_the_strategy_default(fresh_db):
    """The exact shape of the live bug: run 096432c2ad20 was tuned to 30/40 while the strategy
    defaults are 0/0, and the whole grid ran at 0/0 under a label saying otherwise."""
    strategy = _strategy("bleg", "python", {"exec_tp1_pct": 0.0, "exec_tp2_pct": 0.0})
    run_id = _run("tunedrun001", "bleg", {"exec_tp1_pct": 30.0, "exec_tp2_pct": 40.0})

    base = base_params_for({"source_run_id": run_id}, strategy)

    assert base["exec_tp1_pct"] == 30.0
    assert base["exec_tp2_pct"] == 40.0


def test_a_key_the_strategy_does_not_declare_is_never_introduced(fresh_db):
    """A run can carry leftovers from an older schema. For MT5 a fixed_params dict holding an
    input the EA does not declare makes the tester treat the set file as mismatched and silently
    run a single backtest, so this may change a VALUE and never add a KEY."""
    strategy = _strategy("aplus", "mt5", {"exec_risk_pct": 10.0})
    run_id = _run("staleparams1", "aplus", {"exec_risk_pct": 12.5, "exec_sl_by_entry": True})

    base = base_params_for({"source_run_id": run_id}, strategy)

    assert base["exec_risk_pct"] == 12.5
    assert "exec_sl_by_entry" not in base


def test_no_source_run_falls_back_to_the_strategy_defaults(fresh_db):
    strategy = _strategy("aplus", "python", {"exec_risk_pct": 10.0})

    assert base_params_for({}, strategy) == {"exec_risk_pct": 10.0}
    assert base_params_for({"source_run_id": "doesnotexist"}, strategy) == {"exec_risk_pct": 10.0}


# ── 2. a list axis is a real axis ─────────────────────────────────────────────

def test_a_list_axis_expands_to_exactly_its_values():
    assert _expand_axis(["0.618", "0.886", "1.0"]) == ["0.618", "0.886", "1.0"]
    assert _expand_axis([True, False]) == [True, False]


def test_a_list_axis_multiplies_into_the_grid_like_a_range():
    combos = expand_grid({
        "exec_sl_level": ["0.886", "1.0"],
        "exec_risk_pct": {"min": 10, "max": 12, "step": 1},
    })
    assert len(combos) == 6
    assert {c["exec_sl_level"] for c in combos} == {"0.886", "1.0"}


# ── 3. only the runner that can walk a list may be sent one ───────────────────

def _post_grid(client, strategy_id: str, grid: dict):
    with (
        patch("routers.optimizations.run_optimization", new_callable=AsyncMock),
        patch("routers.optimizations.history_limits.validate_window", return_value=None),
    ):
        return client.post("/optimizations/run", json={
            "strategy_id": strategy_id, "instrument": "XAUUSD.s",
            "bar_type": "Minute", "bar_value": 15,
            "start_date": "2025-01-01", "end_date": "2025-06-01",
            "search_method": "native", "param_grid": grid,
        })


@pytest.mark.parametrize("runner", ["ninjatrader", "mt5"])
def test_a_list_axis_is_refused_for_a_runner_that_cannot_walk_one(client, runner):
    _strategy("legacyrunner", runner, {"exec_sl_level": "0.886"})

    resp = _post_grid(client, "legacyrunner", {"exec_sl_level": ["0.886", "1.0"]})

    assert resp.status_code == 400
    assert "exec_sl_level" in resp.json()["detail"]


def test_a_list_axis_is_accepted_for_the_python_runner(client):
    _strategy("pyrunner", "python", {"exec_sl_level": "0.886"})

    resp = _post_grid(client, "pyrunner", {"exec_sl_level": ["0.618", "0.886", "1.0"]})

    assert resp.status_code == 202
    assert resp.json()["estimated_runs"] == 3


def test_a_numeric_range_is_still_accepted_for_every_runner(client):
    _strategy("ntrunner", "ninjatrader", {"exec_risk_pct": 10.0})

    resp = _post_grid(client, "ntrunner", {"exec_risk_pct": {"min": 10, "max": 12, "step": 1}})

    assert resp.status_code == 202
    assert resp.json()["estimated_runs"] == 3
