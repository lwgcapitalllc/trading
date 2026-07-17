"""The `runner="python"` in-process runner.

Offline: nothing here loads bars, hits the broker, or needs the tunnel. What's locked is the seam
where this runner meets the rest of the lab — the job contract, strategy resolution, and the config
build — because that seam is where a Python-specific assumption would silently diverge from what
the routers actually send.
"""

import pytest

from services import python_runner, strategy_scanner


# ── strategy resolution (the job contract) ────────────────────────────────────
#
# Every trigger site builds its job_spec with "strategy_class": strategy["class_name"] — routers/
# backtests.py, routers/sweeps.py, services/sweep_runner.py, services/stress_tester.py, and
# services/optimization_runner.py. There is no "strategy" key anywhere. These tests exist because
# this runner originally read one, which passed a hand-written smoke test and would have failed
# every real Run.

def test_resolves_a_strategy_by_its_class_name():
    found = python_runner._resolve("MpcSosFadeStrategy")
    assert found is not None, "the class name the routers send must resolve"
    pkg_name, entry = found
    assert pkg_name == "mpc_sos_fade"
    assert entry["strategy"].__name__ == "MpcSosFadeStrategy"


def test_the_scanner_and_the_runner_agree_on_the_name():
    """The loop-closer: whatever the scanner stores as class_name is what the routers put in the
    job_spec, so the runner MUST resolve exactly that string. Assert against the scanner's real
    output rather than a hardcoded name, so a rename can't split the two halves apart."""
    from pathlib import Path
    import config as cfg

    pkg_dir = Path(cfg.MONOREPO_ROOT) / "strategies" / "python" / "mpc_sos_fade"
    row = strategy_scanner._parse_python_package(pkg_dir, Path(cfg.MONOREPO_ROOT))
    assert row is not None
    assert python_runner._resolve(row["class_name"]) is not None


def test_the_package_id_is_not_the_contract():
    """"mpc_sos_fade" is the lab id, not the class name — resolving it would mean accepting a key the
    dispatcher never sends and re-opening the original bug from the other side."""
    assert python_runner._resolve("mpc_sos_fade") is None


@pytest.mark.parametrize("name", ["", None, "NoSuchStrategy"])
def test_unknown_names_resolve_to_nothing(name):
    assert python_runner._resolve(name) is None


# ── config build ──────────────────────────────────────────────────────────────

def test_unknown_params_are_dropped_not_passed_through():
    """The lab's stored params can carry leftovers from an older schema or another runner. A
    dataclass raises TypeError on an unexpected keyword, which would fail the run over a param the
    strategy doesn't even read."""
    from strategies.python.mpc_sos_fade.config import SosFadeConfig

    config = python_runner._build_config(
        SosFadeConfig, {"exec_risk_pct": 3.0, "AccountSize": 50000, "NotAParam": "x"}, "XAUUSD.s")
    assert config.exec_risk_pct == 3.0


def test_json_types_are_coerced_to_the_field_types():
    """Params round-trip through JSON, where every number is a float and a bool may be 0/1."""
    from strategies.python.mpc_sos_fade.config import SosFadeConfig

    config = python_runner._build_config(
        SosFadeConfig, {"exec_risk_pct": "2.5", "flat_by_close": 1}, "XAUUSD.s")
    assert config.exec_risk_pct == 2.5
    assert config.flat_by_close is True


def test_the_symbol_comes_from_the_run_not_the_param_form():
    """The lab already knows the instrument; tick mode shouldn't need it typed in twice."""
    from strategies.python.mpc_sos_fade.config import SosFadeConfig

    assert python_runner._build_config(SosFadeConfig, {}, "XAUUSD.s").symbol == "XAUUSD.s"


# ── job bookkeeping ───────────────────────────────────────────────────────────

def test_an_unknown_job_reports_failed_rather_than_raising():
    """backtest_runner polls status in a loop; an exception there would strand the run row."""
    assert python_runner.job_status("nope")["status"] == "failed_error"


def test_results_for_an_unfinished_job_raise():
    assert pytest.raises(RuntimeError, python_runner.job_results, "nope")


def test_opt_results_for_an_unfinished_job_raise():
    assert pytest.raises(RuntimeError, python_runner.native_opt_results, "nope")


def test_status_omits_combo_counts_for_a_single_backtest():
    """The optimizer poller writes completed_runs whenever completed_count is present. A single
    backtest has no combos, so it must not report a count of 0 — that would overwrite a real one."""
    python_runner._JOBS["j1"] = {
        "job_id": "j1", "status": "running", "pct": 5, "message": "x",
        "created_at": 0, "updated_at": 0, "results": None, "error": None,
        "cancelled": False, "log": [],
    }
    try:
        assert "completed_count" not in python_runner.job_status("j1")
    finally:
        del python_runner._JOBS["j1"]


def test_status_reports_combo_counts_for_a_sweep():
    python_runner._JOBS["j2"] = {
        "job_id": "j2", "status": "running", "pct": 50, "message": "x",
        "created_at": 0, "updated_at": 0, "results": None, "error": None,
        "cancelled": False, "log": [], "combos": None,
        "completed_count": 4, "total_count": 8,
    }
    try:
        status = python_runner.job_status("j2")
        assert status["completed_count"] == 4
        assert status["total_count"] == 8
    finally:
        del python_runner._JOBS["j2"]


def test_health_is_always_up():
    """It is this process — there is no agent to be down."""
    assert python_runner.health()["status"] == "ok"
