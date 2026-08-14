"""The Optimizations page's defects, one test each (2026-08-04 audit).

The `optimizations` table was EMPTY when this audit ran, which is the frame for all of it: the
page had never been driven end to end, so every defect below was latent rather than corrupting
live data. That also means none of these were caught by use — they are caught here.

Grouped the way the audit was: what BREAKS, what MISLEADS, what is merely wasteful.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from services import lab_db
from services.optimization_runner import (
    _expand_axis,
    _pick_best_run,
    expand_grid,
    validate_param_grid,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _strategy(
    strategy_id: str = "pybot", runner: str = "python", defaults: Optional[dict] = None
) -> dict:
    lab_db.upsert_strategy(
        {
            "id": strategy_id,
            "name": strategy_id.upper(),
            "class_name": strategy_id,
            "source_path": f"strategies/{strategy_id}",
            "scanned_at": int(time.time()),
            "runner": runner,
            "default_params": defaults or {"exec_risk_pct": 10.0},
            "param_schema": [],
        }
    )
    return lab_db.get_strategy(strategy_id)


def _opt(opt_id: str = "opt_test01", **over) -> dict:
    lab_db.insert_optimization(
        {
            "optimization_id": opt_id,
            "strategy_id": over.pop("strategy_id", "pybot"),
            "instrument": "XAUUSD.s",
            "start_date": "2025-01-01",
            "end_date": "2025-06-01",
            "commission_per_side": 0.0,
            "slippage_ticks": 0,
            "ruleset_id": over.pop("ruleset_id", None),
            "mode": over.pop("mode", "raw"),
            "search_method": "native",
            "param_grid": {"exec_risk_pct": {"min": 1, "max": 3, "step": 1}},
            "status": "running",
            "estimated_runs": 3,
            **over,
        }
    )
    return lab_db.get_optimization(opt_id)


def _combo(run_id: str, opt_id: str, *, pf: float, trades: int, strategy_id: str = "pybot") -> None:
    lab_db.insert_complete_optimization_runs(
        [
            {
                "run_id": run_id,
                "strategy_id": strategy_id,
                "instrument": "XAUUSD.s",
                "params": {"exec_risk_pct": 1.0},
                "bar_type": "Minute",
                "bar_value": 15,
                "start_date": "2025-01-01",
                "end_date": "2025-06-01",
                "commission_per_side": 0.0,
                "slippage_ticks": 0,
                "created_at": int(time.time()),
                "optimization_id": opt_id,
                "runner": "python",
                "kpis": {"profit_factor": pf, "trade_count": trades, "net_pnl": pf * 100},
            }
        ]
    )


def _post(client, strategy_id: str, grid: dict, **extra):
    with (
        patch("routers.optimizations.run_optimization", new_callable=AsyncMock),
        patch("routers.optimizations.history_limits.validate_window", return_value=None),
    ):
        return client.post(
            "/optimizations/run",
            json={
                "strategy_id": strategy_id,
                "instrument": "XAUUSD.s",
                "bar_type": "Minute",
                "bar_value": 15,
                "start_date": "2025-01-01",
                "end_date": "2025-06-01",
                "search_method": "native",
                "param_grid": grid,
                **extra,
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# 1. A grid that cannot be expanded must be REFUSED, not started
# ─────────────────────────────────────────────────────────────────────────────


def test_a_zero_step_raises_instead_of_looping_forever():
    """The whole-backend hang. `while v <= hi: v += 0` never terminates, and it ran on the
    event loop inside the request handler — so a typo in a step box took down every endpoint,
    not just this optimization. There is no assertion that can catch a hang; the point is that
    this returns at all."""
    with pytest.raises(ValueError, match="step must be greater than 0"):
        _expand_axis({"min": 1, "max": 10, "step": 0}, "exec_risk_pct")


def test_a_negative_step_raises_too():
    with pytest.raises(ValueError, match="step must be greater than 0"):
        _expand_axis({"min": 1, "max": 10, "step": -1}, "exec_risk_pct")


def test_an_inverted_range_is_refused_rather_than_silently_empty():
    """min 20 / max 5 used to expand to [] — an axis with no values, which makes the whole
    cartesian product empty, so the job started and did nothing."""
    with pytest.raises(ValueError, match="below min"):
        _expand_axis({"min": 20, "max": 5, "step": 1}, "exec_risk_pct")


def test_an_absurd_axis_is_refused_before_it_is_built():
    """Counted arithmetically, so the ceiling is checked WITHOUT materialising the list — the
    guard must not itself be the memory event it exists to prevent."""
    with pytest.raises(ValueError, match="over the"):
        _expand_axis({"min": 0, "max": 1e9, "step": 0.001}, "exec_risk_pct")


def test_the_error_message_names_the_parameter():
    """One bad box among thirty. An error that does not say which is barely better than none."""
    with pytest.raises(ValueError, match="exec_tp1_pct"):
        validate_param_grid({"exec_tp1_pct": {"min": 1, "max": 10, "step": 0}})


def test_a_valid_range_still_expands_exactly_as_before():
    """The guards are a refusal path, not a change of behaviour. Arithmetic counting replaced
    an accumulating `v += step` loop, so the values themselves are re-pinned here."""
    assert _expand_axis({"min": 1, "max": 10, "step": 2}) == [1.0, 3.0, 5.0, 7.0, 9.0]
    assert _expand_axis({"min": 0, "max": 1, "step": 0.25}) == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert len(expand_grid({"a": {"min": 1, "max": 5, "step": 1}, "b": [True, False]})) == 10


def test_the_endpoint_turns_a_bad_grid_into_a_400(client):
    _strategy()
    resp = _post(client, "pybot", {"exec_risk_pct": {"min": 1, "max": 10, "step": 0}})
    assert resp.status_code == 400
    assert "step" in resp.json()["detail"]
    # And nothing was written — a refused request must not leave a row behind.
    assert lab_db.list_optimizations() == []


# ─────────────────────────────────────────────────────────────────────────────
# 2. Cancel has to cancel
# ─────────────────────────────────────────────────────────────────────────────


def test_cancel_stops_the_runner_job_and_not_only_the_database_row(client):
    """The row status is what the page reads and what releases the per-platform job lock. Until
    2026-08-04 it was the ONLY thing cancel did: the sweep kept every core busy, the lock said
    the platform was free, and the job ended by overwriting its own cancelled status."""
    _strategy()
    _opt("opt_cancel01")

    with patch(
        "services.runner_dispatch.cancel_job", return_value={"status": "cancelling"}
    ) as stop:
        resp = client.post("/optimizations/opt_cancel01/cancel")

    assert resp.status_code == 200
    assert resp.json()["job_stopped"] is True
    stop.assert_called_once()
    # The job id the runner knows it by — not the optimization id.
    assert stop.call_args[0][0] == "nopt_opt_cancel01"
    assert stop.call_args[0][1] == "python"
    assert lab_db.get_optimization("opt_cancel01")["status"] == "failed_cancelled"


def test_cancel_reports_when_the_runner_could_not_be_reached(client):
    """The row is still marked cancelled — the poller abandons it either way — but 'stopped' and
    'we could not tell it to stop' are different facts and the machine may still be busy."""
    _strategy()
    _opt("opt_cancel02")

    with patch("services.runner_dispatch.cancel_job", side_effect=RuntimeError("agent down")):
        resp = client.post("/optimizations/opt_cancel02/cancel")

    assert resp.status_code == 200
    assert resp.json()["job_stopped"] is False
    assert lab_db.get_optimization("opt_cancel02")["status"] == "failed_cancelled"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Delete and re-run must survive a foreign key
# ─────────────────────────────────────────────────────────────────────────────


def _stress_test_on(run_id: str, st_id: str = "st_1") -> None:
    lab_db.insert_stress_test(
        {
            "stress_test_id": st_id,
            "run_id": run_id,
            "ruleset_id": None,
            "status": "complete",
            "created_at": int(time.time()),
        }
    )


def test_deleting_an_optimization_whose_combo_was_stress_tested_does_not_500(client):
    """`stress_tests.run_id` is a FK into backtest_runs under PRAGMA foreign_keys=ON, so a
    stress-tested child run cannot be deleted until its test is gone. Reachable on python:
    retry a combo as a full backtest, stress-test it, then delete the optimization."""
    _strategy()
    _opt("opt_del01")
    _combo("comborun001", "opt_del01", pf=2.0, trades=100)
    _stress_test_on("comborun001")
    lab_db.complete_optimization("opt_del01", "comborun001")  # a running one refuses outright

    resp = client.delete("/optimizations/opt_del01")

    assert resp.status_code == 204
    assert lab_db.get_optimization("opt_del01") is None
    assert lab_db.get_run("comborun001") is None
    assert lab_db.get_stress_test("st_1") is None


def test_rerunning_an_optimization_that_wrote_evaluations_does_not_500(client, monkeypatch):
    """The NT8 case: one evaluation row per combo, all of them FK'd to the child run being
    deleted. Re-run crashed on every optimization that had a ruleset."""
    _strategy("ntbot", "ninjatrader")
    _opt("opt_rerun01", strategy_id="ntbot", ruleset_id=None)
    _combo("comborun002", "opt_rerun01", pf=2.0, trades=100, strategy_id="ntbot")
    _stress_test_on("comborun002", "st_2")

    with (
        patch("routers.optimizations.run_optimization", new_callable=AsyncMock),
        patch("routers.optimizations.ensure_platform_idle", return_value=None),
    ):
        # Not running any more, or rerun refuses outright.
        lab_db.complete_optimization("opt_rerun01", "comborun002")
        resp = client.post("/optimizations/opt_rerun01/rerun")

    assert resp.status_code == 202
    assert lab_db.get_run("comborun002") is None
    assert lab_db.get_stress_test("st_2") is None
    row = lab_db.get_optimization("opt_rerun01")
    assert row["status"] == "running"
    # A re-run re-measures — carrying the old winner or its robustness score forward would
    # describe a grid that no longer exists.
    assert row["best_run_id"] is None
    assert row["grid_sensitivity_score"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. A failure is a finish
# ─────────────────────────────────────────────────────────────────────────────


def test_failing_an_optimization_stamps_a_completion_time(fresh_db):
    """Without it the page had no end to measure against, fell back to now(), and a job that
    died on Tuesday read 'Ran for 74h' and kept counting."""
    _strategy()
    _opt("opt_fail01")
    assert lab_db.get_optimization("opt_fail01")["completed_at"] is None

    lab_db.fail_optimization("opt_fail01", "VPS submit failed")

    row = lab_db.get_optimization("opt_fail01")
    assert row["status"].startswith("failed")
    assert row["completed_at"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# 5. Picking the winner
# ─────────────────────────────────────────────────────────────────────────────


def _pick(opt: dict, firm=None):
    return asyncio.run(
        _pick_best_run(
            [
                r
                for r in lab_db.list_optimization_runs(opt["optimization_id"])
                if r["status"] == "complete"
            ],
            opt,
            firm,
        )
    )


def test_a_two_trade_fluke_cannot_win_when_a_trade_floor_is_set(fresh_db):
    """Profit factor has no opinion about sample size. PF 8.0 on two trades outranks PF 2.0 on
    two hundred, and the optimizer used to hand you the two."""
    _strategy()
    opt = _opt("opt_floor01", min_trades=30)
    _combo("flukerun0001", "opt_floor01", pf=8.0, trades=2)
    _combo("realrun00001", "opt_floor01", pf=2.0, trades=200)

    winner, note = _pick(opt)

    assert winner == "realrun00001"
    assert note is None


def test_a_combo_under_the_floor_is_still_stored_and_listed(fresh_db):
    """The floor decides who can WIN, never who gets run. Dropping the rows would make the grid
    quietly narrower than the page says it is."""
    _strategy()
    _opt("opt_floor02", min_trades=30)
    _combo("flukerun0002", "opt_floor02", pf=8.0, trades=2)

    rows = lab_db.list_optimization_runs("opt_floor02")
    assert [r["run_id"] for r in rows] == ["flukerun0002"]
    assert rows[0]["status"] == "complete"


def test_when_the_floor_excludes_everything_it_falls_back_and_SAYS_SO(fresh_db):
    """An optimization that names no winner is useless, so falling back is right. A SILENT
    fallback is the repo's signature defect — a page claiming something the code did not do."""
    _strategy()
    opt = _opt("opt_floor03", min_trades=500)
    _combo("smallrun0001", "opt_floor03", pf=3.0, trades=10)
    _combo("smallrun0002", "opt_floor03", pf=1.5, trades=20)

    winner, note = _pick(opt)

    assert winner == "smallrun0001"
    assert note and "500-trade minimum" in note


def test_no_floor_means_no_floor(fresh_db):
    """0 is the API default — a caller that states nothing gets nothing applied."""
    _strategy()
    opt = _opt("opt_floor04", min_trades=0)
    _combo("flukerun0003", "opt_floor04", pf=8.0, trades=2)
    _combo("realrun00002", "opt_floor04", pf=2.0, trades=200)

    winner, note = _pick(opt)

    assert winner == "flukerun0003"
    assert note is None


def test_a_regime_filter_that_matches_nothing_falls_back_and_SAYS_SO(fresh_db, monkeypatch):
    """The NT8-only bug, and it produced NO winner at all. `_regime_filtered_score` returns -inf
    when a run has no trades in the target regime — and on a filter that matches nothing that is
    every run, so the whole optimization finished with a blank ★ and no explanation."""
    from services import optimization_runner as orun

    _strategy("ntbot", "ninjatrader")
    opt = _opt("opt_regime01", strategy_id="ntbot", regime_filter="TRENDING")
    _combo("regimerun001", "opt_regime01", pf=3.0, trades=100, strategy_id="ntbot")
    _combo("regimerun002", "opt_regime01", pf=1.2, trades=100, strategy_id="ntbot")

    # A real regime map, so the filter is genuinely ACTIVE — the point is that no combo has
    # trades in it, not that the map failed to build (which already fell back).
    monkeypatch.setattr(orun, "build_date_regime_map", lambda *a: {"2025-02-03": "TRENDING"})

    winner, note = _pick(opt)

    assert winner == "regimerun001"
    assert note and "trending" in note.lower()


def test_an_all_ineligible_grid_still_names_a_winner_with_a_note(fresh_db):
    """`funded` mode returns -inf for a drawdown breach. Every combo breaching left best_run_id
    None — a finished optimization with no ★ and nothing on the page explaining why."""
    _strategy()
    opt = _opt("opt_none01", mode="funded")
    _combo("breached0001", "opt_none01", pf=3.0, trades=100)
    _combo("breached0002", "opt_none01", pf=1.2, trades=100)
    firm = {"id": "f", "max_loss_eod": 1.0, "account_size": 100.0, "profit_target": 1000.0}

    # Every row's max_drawdown is None here, so nothing breaches — force the breach by giving
    # the firm a limit of 1 and the runs a drawdown above it.
    with lab_db._connect() as conn:
        conn.execute(
            "UPDATE backtest_runs SET max_drawdown = 99999 WHERE optimization_id = ?",
            ("opt_none01",),
        )

    winner, note = _pick(opt, firm)

    assert winner == "breached0001"  # highest profit factor of a rejected field
    assert note and "rejected" in note


def test_robustness_is_measured_on_the_run_that_actually_won(fresh_db):
    """ "Winner robustness" has to be about the ★. `_compute_grid_sensitivity` anchored itself on
    the highest profit factor, which is the same row only under `raw` mode with no trade floor —
    so with a floor set, or under eval/funded mode, the card described a DIFFERENT combination
    than the one starred above it."""
    from services.optimization_runner import _compute_grid_sensitivity

    # A lone spike at risk=2 (PF 9, 2 trades) and a plateau at risk=4 (PF 2.0 with PF 1.98
    # neighbours). The floor makes the plateau the winner.
    combos = [
        {"params": {"exec_risk_pct": 1.0}, "kpis": {"profit_factor": 0.5, "trade_count": 90}},
        {"params": {"exec_risk_pct": 2.0}, "kpis": {"profit_factor": 9.0, "trade_count": 2}},
        {"params": {"exec_risk_pct": 3.0}, "kpis": {"profit_factor": 1.98, "trade_count": 95}},
        {"params": {"exec_risk_pct": 4.0}, "kpis": {"profit_factor": 2.00, "trade_count": 99}},
        {"params": {"exec_risk_pct": 5.0}, "kpis": {"profit_factor": 1.98, "trade_count": 97}},
    ]
    ranges = {"exec_risk_pct": {"min": 1, "max": 5, "step": 1}}

    spike, _ = _compute_grid_sensitivity(combos, ranges)  # old
    plateau, summary = _compute_grid_sensitivity(combos, ranges, {"exec_risk_pct": 4.0})  # new

    # Anchored on the fluke, the grid looks fragile; anchored on the actual winner it is flat.
    assert spike > 0.7
    assert plateau < 0.05
    assert summary["exec_risk_pct"]["up"]["value"] == 5.0
    assert summary["exec_risk_pct"]["down"]["value"] == 3.0


@pytest.mark.parametrize(
    "combos, winner",
    [
        # Winner not in the grid at all (a retried combo, or a rewritten param set).
        (
            [{"params": {"exec_risk_pct": 1.0}, "kpis": {"profit_factor": 2.0}}],
            {"exec_risk_pct": 99.0},
        ),
        # Winner PF is 0 — there is no denominator to express a degradation as a fraction of.
        (
            [
                {"params": {"exec_risk_pct": 1.0}, "kpis": {"profit_factor": 0.0}},
                {"params": {"exec_risk_pct": 2.0}, "kpis": {"profit_factor": 0.0}},
            ],
            {"exec_risk_pct": 1.0},
        ),
        # One value on every axis — nothing to compare the winner against.
        (
            [{"params": {"exec_risk_pct": 1.0}, "kpis": {"profit_factor": 3.0}}],
            {"exec_risk_pct": 1.0},
        ),
        # Empty grid.
        ([], None),
    ],
)
def test_unmeasurable_robustness_is_NULL_and_never_zero(combos, winner):
    """0.0 is the PERFECT-PLATEAU score — the strongest "trust this winner" the metric can say.
    Using it for "could not measure" puts the most reassuring number on screen exactly when
    nothing was checked, which is worse than showing nothing. None means the column stays NULL
    and the card does not render."""
    from services.optimization_runner import _compute_grid_sensitivity

    score, summary = _compute_grid_sensitivity(
        combos, {"exec_risk_pct": {"min": 1, "max": 5, "step": 1}}, winner
    )

    assert score is None
    assert summary == {}


# ─────────────────────────────────────────────────────────────────────────────
# 6. The costs a grid is ranked under
# ─────────────────────────────────────────────────────────────────────────────


def test_an_optimization_stores_the_cost_layers_it_was_asked_for(client):
    """Until 2026-08-04 the grid was ALWAYS ranked on a free book while the run it was launched
    from had spread and swap charged — two numbers produced under different physics, presented
    as a comparison."""
    _strategy()
    resp = _post(
        client,
        "pybot",
        {"exec_risk_pct": {"min": 1, "max": 3, "step": 1}},
        cost_layers=["spread", "swap"],
        broker_profile="vantage_demo",
    )

    assert resp.status_code == 202
    row = lab_db.get_optimization(resp.json()["optimization_id"])
    assert row["cost_layers"] == ["spread", "swap"]
    assert row["broker_profile"] == "vantage_demo"


def test_stating_no_layers_stores_NULL_not_an_empty_list(client):
    """NULL means 'this row predates layers, keep the old behaviour'; [] means 'charge nothing'.
    Collapsing them would silently re-price every historical row on its next re-run."""
    _strategy()
    resp = _post(client, "pybot", {"exec_risk_pct": {"min": 1, "max": 3, "step": 1}})

    row = lab_db.get_optimization(resp.json()["optimization_id"])
    assert row["cost_layers"] is None


def test_the_layers_reach_the_runner_spec(fresh_db):
    """Stored is not charged. `python_runner._cost_profile` reads them off the SPEC, so the
    value has to survive the hop out of the optimization row."""
    _strategy()
    _opt("opt_cost01", cost_layers=["spread"], broker_profile="vantage_demo")

    captured = {}

    def _capture(spec, runner):
        captured.update(spec)
        raise RuntimeError("stop here — the spec is all this test needs")

    from services import optimization_runner as orun

    with patch.object(orun.runner_dispatch, "start_native_optimization", side_effect=_capture):
        asyncio.run(orun.run_native_optimization("opt_cost01"))

    assert captured["cost_layers"] == ["spread"]
    assert captured["broker_profile"] == "vantage_demo"


# ─────────────────────────────────────────────────────────────────────────────
# 7. min_trades round-trip
# ─────────────────────────────────────────────────────────────────────────────


def test_min_trades_round_trips_through_the_api(client):
    _strategy()
    resp = _post(client, "pybot", {"exec_risk_pct": {"min": 1, "max": 3, "step": 1}}, min_trades=30)
    opt_id = resp.json()["optimization_id"]

    assert lab_db.get_optimization(opt_id)["min_trades"] == 30
    assert client.get(f"/optimizations/{opt_id}").json()["min_trades"] == 30


def test_min_trades_defaults_to_zero_for_a_caller_that_says_nothing(client):
    """Nothing is assumed of an API caller — the same rule the 0/0 commission default follows.
    The modal is what states 30, visibly and editably."""
    _strategy()
    resp = _post(client, "pybot", {"exec_risk_pct": {"min": 1, "max": 3, "step": 1}})

    assert lab_db.get_optimization(resp.json()["optimization_id"])["min_trades"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 8. Payload — the detail endpoint ships what the page can draw
# ─────────────────────────────────────────────────────────────────────────────


def test_a_combo_row_ships_only_the_grids_own_params(client):
    """A combo's stored params are fixed_params merged with the swept ones — 50+ keys on a
    Python strategy — and the page renders exactly the grid's keys. Polled every 3 seconds on
    a 1,000-combo grid, the rest was most of the response and nothing displayed it."""
    _strategy()
    _opt("opt_slim01")
    lab_db.insert_complete_optimization_runs(
        [
            {
                "run_id": "fatparams001",
                "strategy_id": "pybot",
                "instrument": "XAUUSD.s",
                "params": {"exec_risk_pct": 1.0, "exec_tp1_pct": 30.0, "exec_sl_level": "0.886"},
                "bar_type": "Minute",
                "bar_value": 15,
                "start_date": "2025-01-01",
                "end_date": "2025-06-01",
                "commission_per_side": 0.0,
                "slippage_ticks": 0,
                "created_at": int(time.time()),
                "optimization_id": "opt_slim01",
                "runner": "python",
                "kpis": {"profit_factor": 2.0, "trade_count": 50},
            }
        ]
    )

    body = client.get("/optimizations/opt_slim01").json()

    assert body["runs"][0]["params"] == {"exec_risk_pct": 1.0}
    # And the full row is untouched on disk — this is a projection, not a deletion.
    assert "exec_tp1_pct" in lab_db.get_run("fatparams001")["params"]


# ─────────────────────────────────────────────────────────────────────────────
# 9. Batched writes produce the same rows the per-combo ones did
# ─────────────────────────────────────────────────────────────────────────────


def test_the_bulk_combo_insert_writes_a_complete_run_with_its_kpis(fresh_db):
    """One statement replaced insert + update per combo (~2 sqlite connections each). The row
    it produces has to be indistinguishable from the two-step one."""
    _strategy()
    _opt("opt_bulk01")
    _combo("bulkrun00001", "opt_bulk01", pf=2.5, trades=77)

    row = lab_db.get_run("bulkrun00001")
    assert row["status"] == "complete"
    assert row["profit_factor"] == 2.5
    assert row["trade_count"] == 77
    assert row["completed_at"] is not None
    # Native combos carry no curve, trades or daily P&L — the platform reports one grid, not N
    # result sets. Every consumer has to treat a combo row as KPIs-only.
    assert row["equity_curve_path"] is None
    assert row["daily_pnl_path"] is None


def test_evaluations_come_back_batched_and_keyed_by_run(fresh_db):
    _strategy()
    _opt("opt_bulk02")
    _combo("evalrun00001", "opt_bulk02", pf=2.0, trades=50)
    _combo("evalrun00002", "opt_bulk02", pf=1.0, trades=50)

    out = lab_db.get_evaluations_for_runs(["evalrun00001", "evalrun00002", "nosuchrun001"])

    # Every requested id is a key, including ones with no evaluations — a missing key and an
    # empty list are different answers, and the scorer reads this with .get().
    assert set(out) == {"evalrun00001", "evalrun00002", "nosuchrun001"}
    assert out["evalrun00001"] == []


def test_batched_evaluations_survive_more_runs_than_sqlite_takes_parameters(fresh_db):
    """SQLite's default host-parameter ceiling is 999, and the whole point of this function is
    the thousand-combo case."""
    ids = [f"r{i:011d}" for i in range(1200)]
    out = lab_db.get_evaluations_for_runs(ids)
    assert len(out) == 1200
