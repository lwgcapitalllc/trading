"""The 2026-08-05 stress-test audit — one test per defect, named after what it prevents.

The frame for the whole file: the `stress_tests` table held exactly ONE row, written 2026-07-27,
three days before the accuracy pass that was supposed to fix this feature. So nothing here had been
exercised end to end, and every defect below rendered a confident, healthy-looking answer.
"""

import pytest
from services import lab_db
from services.grading import compute_grade
from services.stress_tester import (
    _WF_MIN_TRADES_PER_WINDOW,
    _estimate_wf_duration_min,
    _split_windows,
    child_measurement_fields,
    is_cancelled,
    param_is_reachable,
    perturbable_params,
    phases_requested,
    run_monte_carlo,
    shifted_value,
    walk_forward_feasibility,
)

LIMITED = {"id": "p", "ruleset_type": "prop_funded", "max_loss_eod": 5000, "account_size": 50_000}
NO_LIMIT = {
    "id": "unconstrained",
    "name": "Unconstrained (No Limits)",
    "ruleset_type": "personal",
    "max_loss_eod": 0,
}


def _st(**over):
    base = {
        "pct1_max_dd": 1000.0,
        "pct5_max_dd": 800.0,
        "median_max_dd": 500.0,
        "median_final_pnl": 20000.0,
        "prob_breach": 0.0,
        "walk_forward_degradation": None,
        "sensitivity_max_degradation": None,
    }
    base.update(over)
    return base


# ── A child run must be measured on the BASELINE's physics ────────────────────
# The load-bearing one. `python_runner._cost_profile` reads cost_layers/broker_profile off the job
# spec, and the walk-forward and sensitivity specs carried neither — so stress-testing a run that
# charged spread and swap produced children measured on a free book, and sensitivity reported the
# cost gap as the parameter's fragility.


def test_a_childs_spec_carries_the_baselines_costs_broker_and_sizing():
    fields = child_measurement_fields(
        {
            "cost_layers": '["spread", "swap"]',
            "broker_profile": "vantage_demo",
            "sizing_mode": "manual",
            "manual_risk_pct": 2.5,
        }
    )
    assert fields == {
        "cost_layers": ["spread", "swap"],
        "broker_profile": "vantage_demo",
        "sizing_mode": "manual",
        "manual_risk_pct": 2.5,
    }


def test_cost_layers_is_decoded_not_handed_over_as_a_string():
    """`lab_db.get_run` leaves the column as raw JSON TEXT. Passed through unparsed, the runner
    iterates its CHARACTERS: every real layer name misses while 's', 'p', 'r'... all match."""
    fields = child_measurement_fields({"cost_layers": '["spread"]'})
    assert fields["cost_layers"] == ["spread"]
    assert "s" not in fields["cost_layers"]


def test_a_pre_layer_run_stays_pre_layer():
    """NULL and [] are different contracts: NULL is a row written before layered costs existed and
    must keep the old behaviour; [] is an explicit 'charge nothing'. Collapsing them re-prices
    history on its next child run."""
    assert child_measurement_fields({})["cost_layers"] is None
    assert child_measurement_fields({"cost_layers": "[]"})["cost_layers"] == []


# ── Ran-and-failed is not never-ran ───────────────────────────────────────────


def test_a_failed_walk_forward_cannot_earn_an_a():
    """A crashed phase left the summary NULL, grading read that as not-run — which is explicitly
    unpenalised — and the test could be handed an A carrying the reason 'walk-forward not run'."""
    clean = _st(sensitivity_max_degradation=0.05)
    assert compute_grade(clean, None, {"p": {}}, LIMITED)[0] == "A"  # genuinely not run
    grade, reasons = compute_grade(clean, None, {"p": {}}, LIMITED, wf_failed=True)
    assert grade == "B"
    assert any("FAILED" in r for r in reasons)


def test_a_failed_phase_never_also_claims_it_was_not_run():
    """Two contradictory explanations in one list is worse than either alone."""
    _, reasons = compute_grade(
        _st(sensitivity_max_degradation=0.05), None, {"p": {}}, LIMITED, wf_failed=True
    )
    assert not any("not run — grade may improve" in r for r in reasons)


def test_a_failed_sensitivity_is_reported_and_neutral():
    grade, reasons = compute_grade(_st(), None, None, LIMITED, sens_failed=True)
    assert any(
        "sensitivity was requested and FAILED" in r.lower() or "FAILED" in r for r in reasons
    )
    # Neutral: it must not push the grade DOWN either.
    assert grade in ("A", "B")


# ── The two probabilities must come off ONE basis ─────────────────────────────


def _compounding_run():
    """A run whose trade size drifts hard enough to trip the returns model — i.e. one graded on
    PERCENT. `balances` is the account balance before each trade, as the orchestrator builds it."""
    pnls = [10.0 * (1.06**i) if i % 3 else -6.0 * (1.06**i) for i in range(120)]
    balances, bal = [], 10_000.0
    for p in pnls:
        balances.append(bal)
        bal += p
    return pnls, balances


def test_prob_pass_is_measured_on_the_same_basis_as_prob_breach():
    """🔴 `prob_breach` was branched on `dd_basis`; `prob_pass_eval` was hardcoded to the DOLLAR
    comparison. MEASURED on this exact fixture against the old code — a $6,000 limit on a $10,000
    account, i.e. 60%, on a run whose worst-1% drawdown is 26% and $24,647:

        prob_breach     0.0%   (percent basis, 60% limit — nothing ever breaches)
        prob_pass_eval  31.2%  (dollar basis, $6,000 limit — the grown account blows through it)

    Two headline numbers side by side on one card: a strategy that never breaches, passing a third
    of the time. On the one basis both are read from, the honest answer is 100%."""
    pnls, balances = _compounding_run()
    ruleset = {
        "id": "eval",
        "ruleset_type": "prop_eval",
        "account_size": 10_000,
        "max_loss_eod": 6000,
        "profit_target": 100,
    }
    mc = run_monte_carlo(
        pnls, ruleset, num_reshuffles=500, num_bootstrap=500, num_path_samples=5, balances=balances
    )
    assert mc["dd_basis"] == "percent"
    assert mc["prob_breach"] == 0.0
    assert mc["prob_pass_eval"] == 1.0
    # The general invariant, which is what actually has to hold: you cannot pass more often than
    # you avoid breaching.
    assert mc["prob_pass_eval"] <= 1.0 - mc["prob_breach"] + 1e-9


def test_a_fixed_size_run_still_reports_dollars():
    """The percent path must not capture runs that never compound — their numbers must not move."""
    pnls = [100.0, -50.0] * 60
    mc = run_monte_carlo(pnls, None, num_reshuffles=200, num_bootstrap=200, num_path_samples=5)
    assert mc["dd_basis"] == "dollars"
    assert mc["median_max_dd_pct"] is None
    assert "max_dd_pct" not in mc["distribution"]


def test_the_percent_histogram_exists_exactly_when_the_percent_basis_does():
    """The one picture of the drawdown distribution was dollars-only, so on a compounding run it
    was drawn — with a dollar limit line over it — in the unit the letter beside it had ignored."""
    pnls, balances = _compounding_run()
    mc = run_monte_carlo(
        pnls, None, num_reshuffles=200, num_bootstrap=200, num_path_samples=5, balances=balances
    )
    assert mc["dd_basis"] == "percent"
    assert "max_dd_pct" in mc["distribution"]
    assert len(mc["distribution"]["max_dd_pct"]["counts"]) == 50


# ── Walk-forward feasibility is arithmetic, knowable before the work ──────────


def test_five_windows_on_this_labs_own_trade_counts_can_never_be_assessed():
    """126 trades over 5 windows leaves ~7.6 unseen trades each, under the 20 floor — measured on
    the real run: 6, 6, 6, 12 and 8. So the shipped default guaranteed 'not assessable', every
    time, with nothing on screen saying so before ten backtests had run."""
    ok, why = walk_forward_feasibility(126, 5)
    assert not ok
    assert "cap the grade at B" in why
    assert "or fewer" in why  # it names the fix


def test_enough_trades_passes():
    ok, why = walk_forward_feasibility(400, 5)
    assert ok and why == ""


def test_the_boundary_is_the_documented_floor():
    """One window needs MIN/0.3 trades for its unseen 30% to clear the floor."""
    import math

    need = math.ceil(_WF_MIN_TRADES_PER_WINDOW / 0.3)
    assert walk_forward_feasibility(need, 1)[0]
    assert not walk_forward_feasibility(need - 10, 1)[0]


def test_the_in_and_out_of_sample_halves_do_not_share_a_day():
    """`is_end == oos_start` backtested the split date on BOTH sides — a bar the 'unseen' half had
    already seen. Immaterial to the numbers and still on the wrong side of the only line this
    phase draws."""
    for w in _split_windows("2020-01-01", "2026-01-01", 5):
        assert w["is_end"] < w["oos_start"]


# ── Sensitivity may not test what it cannot move, or what it may not reach ────


def test_a_shift_past_the_params_own_bound_is_refused_not_clamped():
    """`exec_sl_custom` is a fib ratio bounded (0, 1.0] at 0.886, so +25% is 1.1075 — which the
    strategy raises on, failing the child and losing the shift silently. Clamping instead would
    run a backtest at +12.8% under a label reading `+25%`, a magnitude that is not the one stated."""
    p = {"name": "exec_sl_custom", "type": "float", "min": 0.0, "max": 1.0}
    value, refusal = shifted_value(p, 0.886, 1.25)
    assert value is None
    assert "maximum" in refusal
    # In range, it still measures.
    value, refusal = shifted_value(p, 0.886, 0.9)
    assert refusal is None and value == pytest.approx(0.7974)


def test_an_int_param_still_rounds():
    assert shifted_value({"name": "n", "type": "int"}, 5, 1.10)[0] == 6


def test_a_param_behind_a_switch_this_run_has_off_is_not_perturbed():
    """A setting the strategy never reads cannot move the result, so every shift of it books a
    guaranteed 0% change — 'tested, rock solid' for something that was never consulted. The
    value-equality dedupe cannot catch it: the value really does change, only the outcome cannot."""
    schema = [
        {"name": "div_extreme_ob", "type": "int", "show_if": {"div_veto": True}},
        {"name": "aplus_window", "type": "int"},
    ]
    off = {"div_veto": False, "div_extreme_ob": 80, "aplus_window": 4320}
    on = {"div_veto": True, "div_extreme_ob": 80, "aplus_window": 4320}
    assert [p["name"] for p in perturbable_params({"param_schema": schema}, off)] == [
        "aplus_window"
    ]
    assert len(perturbable_params({"param_schema": schema}, on)) == 2


def test_show_if_matches_the_editors_own_rules():
    """Mirrors ParamEditor.visible — stringified comparison, and an ARRAY means 'any of these'."""
    p = {"name": "x", "show_if": {"mode": ["1", "2"]}}
    assert param_is_reachable(p, {"mode": 1})  # stringified: 1 matches "1"
    assert param_is_reachable(p, {"mode": "2"})
    assert not param_is_reachable(p, {"mode": 3})


# ── Estimates must know which runner they are estimating ──────────────────────


def test_the_walk_forward_estimate_is_runner_aware():
    """It was hardcoded to the NT8 per-backtest cost regardless of runner, so a python run — which
    replays locally off a warm cache — was quoted ~30x its real wait."""
    assert _estimate_wf_duration_min(5, "python") < _estimate_wf_duration_min(5, "mt5")
    assert _estimate_wf_duration_min(5, "mt5") < _estimate_wf_duration_min(5, "ninjatrader")


# ── One definition of which market lock a runner takes ────────────────────────


def test_a_python_run_takes_the_forex_lock_like_the_frontend_says_it_does():
    """Backend inline: `"forex" if runner == "mt5" else "futures"` — python filed under FUTURES.
    Frontend `runnerMarket`: MT5 and python are both FOREX, since only NinjaTrader trades futures
    contracts. So a running python stress test set `futures`, the run page read `forex`, the button
    stayed enabled and the POST answered 409."""
    assert lab_db.stress_market_for_runner("python") == "forex"
    assert lab_db.stress_market_for_runner("mt5") == "forex"
    assert lab_db.stress_market_for_runner("ninjatrader") == "futures"
    assert lab_db.stress_market_for_runner(None) == "futures"


# ── Bounds on anything that allocates ─────────────────────────────────────────


def test_the_simulation_counts_are_bounded():
    """`run_monte_carlo` allocates (num_simulations x n_trades) float64 arrays, several of them, so
    an extra typed zero is gigabytes in a worker thread — the same shape as the optimizer's
    `step: 0`, which hung the whole backend."""
    from models import StressTestCreate
    from pydantic import ValidationError

    for bad in (
        {"num_simulations": 10_000_000},
        {"num_bootstrap": 0},
        {"walk_forward_windows": 500},
        {"walk_forward_windows": 1},
    ):
        with pytest.raises(ValidationError):
            StressTestCreate(run_id="r", **bad)
    StressTestCreate(run_id="r")  # the defaults are inside the bounds


# ── Cancellation ──────────────────────────────────────────────────────────────


def test_cancel_marks_the_row_and_returns_its_running_children(fresh_db):
    st_id = _seed_running_test()
    children = lab_db.cancel_stress_test(st_id)
    assert children == ["child_running"]  # the finished child is not "stopped"
    assert lab_db.get_stress_test(st_id)["status"] == "failed_cancelled"
    assert is_cancelled(st_id)


def test_cancelling_a_finished_test_is_refused(fresh_db):
    st_id = _seed_running_test()
    lab_db.cancel_stress_test(st_id)
    assert lab_db.cancel_stress_test(st_id) is None  # already cancelled → nothing to do


def test_delete_reports_the_child_run_ids_so_their_files_can_go(fresh_db):
    """It returned a bare bool and the router did nothing else, so every child left its
    `reports/lab/<run_id>/` behind along with the test's own equity_paths.json."""
    st_id = _seed_running_test()
    deleted = lab_db.delete_stress_test(st_id)
    assert sorted(deleted) == ["child_done", "child_running"]
    assert lab_db.delete_stress_test(st_id) is None  # gone → None, not []


# ── Monte Carlo status must not claim to be finished mid-test ────────────────


def test_monte_carlo_does_not_mark_the_row_complete_when_phases_follow(fresh_db):
    """It hardcoded status='complete' and stamped completed_at even with walk-forward still to
    come: the market lock (`status LIKE 'running%'`) RELEASED in that gap, and a crash inside it
    left a permanently 'complete' test that `reset_stale_stress_tests` cannot see."""
    st_id = _seed_running_test()
    lab_db.update_stress_test_mc(st_id, {"median_final_pnl": 1.0}, {}, next_status="running_wf")
    row = lab_db.get_stress_test(st_id)
    assert row["status"] == "running_wf"
    assert row["completed_at"] is None
    assert row["mc_completed_at"] is not None

    lab_db.update_stress_test_mc(st_id, {"median_final_pnl": 1.0}, {}, next_status="complete")
    assert lab_db.get_stress_test(st_id)["completed_at"] is not None


# ── What was asked for is recorded at CREATION ────────────────────────────────


def test_the_requested_phases_are_stored_when_the_row_is_inserted(fresh_db):
    """It was written only after both phases had run, so for a test's whole life the record of
    what was ASKED for did not exist — the page had to infer it from the status, and a task
    killed mid-flight (a backend reload is enough) left no record at all."""
    _seed_running_test()  # gives us the `src` run the FK points at
    lab_db.insert_stress_test(
        {
            "stress_test_id": "st_new",
            "run_id": "src",
            "ruleset_id": None,
            "status": "running",
            "created_at": 0,
            "phases_requested": phases_requested(True, False),
        }
    )
    assert lab_db.get_stress_test("st_new")["phases_requested"] == ["monte_carlo", "walk_forward"]


def test_a_row_created_without_the_field_reads_as_unknown_not_as_monte_carlo_only(fresh_db):
    """NULL means "written before this was recorded", which the page falls back to inferring.
    `["monte_carlo"]` would be a positive claim that no other phase was requested."""
    _seed_running_test()
    lab_db.insert_stress_test(
        {
            "stress_test_id": "st_old",
            "run_id": "src",
            "ruleset_id": None,
            "status": "running",
            "created_at": 0,
        }
    )
    assert lab_db.get_stress_test("st_old")["phases_requested"] is None


def test_monte_carlo_is_always_a_requested_phase():
    assert phases_requested(False, False) == ["monte_carlo"]
    assert phases_requested(True, True) == ["monte_carlo", "walk_forward", "sensitivity"]


# ── helpers ───────────────────────────────────────────────────────────────────


def _seed_running_test() -> str:
    with lab_db._connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO strategies "
            "(id, name, class_name, source_path, scanned_at, runner) "
            "VALUES ('s1','S','S','x.py',1,'python')"
        )
        conn.execute(
            "INSERT INTO backtest_runs (run_id, strategy_id, instrument, params, bar_type, "
            "bar_value, start_date, end_date, commission_per_side, slippage_ticks, status, "
            "created_at) VALUES ('src','s1','X','{}','Minute',15,'2020-01-01','2021-01-01',0,0,"
            "'complete',1)"
        )
        conn.execute(
            "INSERT INTO stress_tests (stress_test_id, run_id, status, created_at) "
            "VALUES ('st1','src','running_wf',1)"
        )
        for rid, status in (("child_running", "running"), ("child_done", "complete")):
            conn.execute(
                "INSERT INTO backtest_runs (run_id, strategy_id, instrument, params, bar_type, "
                "bar_value, start_date, end_date, commission_per_side, slippage_ticks, status, "
                "created_at, stress_test_id) VALUES (?,'s1','X','{}','Minute',15,'2020-01-01',"
                "'2021-01-01',0,0,?,1,'st1')",
                (rid, status),
            )
    return "st1"
