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


# ── meta.json ↔ config agreement ─────────────────────────────────────────────

def test_meta_json_matches_the_config_dataclass():
    """The meta file is hand-written while the schema is generated from the dataclass, so they
    drift silently: a renamed field leaves a stale entry that simply stops applying, and the
    param quietly loses its label/description. Assert every meta param still exists."""
    import json
    from pathlib import Path
    import config as cfg
    from strategies.python.mpc_sos_fade import SosFadeConfig

    meta_path = (Path(cfg.MONOREPO_ROOT) / "strategies" / "python" / "mpc_sos_fade"
                 / "mpc_sos_fade.meta.json")
    meta = json.loads(meta_path.read_text())
    fields = {f.name for f in __import__("dataclasses").fields(SosFadeConfig)}

    named = [p["name"] for p in meta["params"]]
    assert not (set(named) - fields), f"meta names a param the config doesn't have: {set(named) - fields}"
    assert len(named) == len(set(named)), "a param is listed twice in meta.json"


def test_every_tunable_param_is_documented():
    """A param with no description renders as '—' on the strategy page. The foundational ones
    (instrument facts, fill model) are deliberately not user-facing and are excluded."""
    from services import strategy_scanner
    from strategies.python.mpc_sos_fade import SosFadeConfig
    import config as cfg
    from pathlib import Path

    schema = strategy_scanner._py_param_schema(SosFadeConfig)
    meta_path = (Path(cfg.MONOREPO_ROOT) / "strategies" / "python" / "mpc_sos_fade"
                 / "mpc_sos_fade.meta.json")
    schema = strategy_scanner._apply_param_meta(schema, meta_path)

    undocumented = [p["name"] for p in schema
                    if p.get("category") != "foundational" and not p.get("desc")]
    assert not undocumented, f"params with no description: {undocumented}"


def test_enum_defaults_are_legal_choices():
    """A `choices` list renders a dropdown. If the config's default isn't in it, the select has
    no matching option and silently shows/sends a DIFFERENT value than the strategy's default."""
    import json
    from pathlib import Path
    import config as cfg
    from strategies.python.mpc_sos_fade import SosFadeConfig

    meta_path = (Path(cfg.MONOREPO_ROOT) / "strategies" / "python" / "mpc_sos_fade"
                 / "mpc_sos_fade.meta.json")
    meta = json.loads(meta_path.read_text())
    defaults = SosFadeConfig()
    for p in meta["params"]:
        if "choices" in p:
            actual = getattr(defaults, p["name"])
            assert actual in p["choices"], (
                f"{p['name']}: default {actual!r} is not one of {p['choices']}")


# ── run costs (2026-08-01) ───────────────────────────────────────────────────────
#
# The lab collected `commission_per_side` / `slippage_ticks` at run creation, stored them on the
# row and displayed them — and `python_runner` never read either, so every Python run was
# frictionless while reporting a cost profile it had not applied. `_cost_profile` is the seam
# that closes it; these pin the two things about it that would fail silently.

def test_a_run_that_states_no_costs_builds_no_profile():
    """0/0 must yield None, not a zero-valued profile. None is what leaves the charge paths
    unentered, and that is what keeps every result measured before this landed reproducible."""
    from services.python_runner import _cost_profile

    assert _cost_profile({}) is None
    assert _cost_profile({"commission_per_side": 0, "slippage_ticks": 0}) is None
    assert _cost_profile({"commission_per_side": None, "slippage_ticks": None}) is None


def test_either_cost_alone_still_builds_a_profile():
    """Either number on its own is a real cost — an `and` here would silently drop a
    slippage-only run back to frictionless, which is the exact bug being fixed."""
    from services.python_runner import _cost_profile

    assert _cost_profile({"slippage_ticks": 1}) is not None
    assert _cost_profile({"commission_per_side": 3.0}) is not None

    p = _cost_profile({"commission_per_side": 3.0, "slippage_ticks": 2})
    assert (p.commission_per_side_per_lot, p.slippage_ticks) == (3.0, 2)
    # Swap is a broker fact the lab does not collect. Inventing one here would move every
    # result under the banner of a commission change; tick mode remains the way to price it.
    assert p.swap is None


# ── layered costs (2026-08-02) ───────────────────────────────────────────────────
#
# Aaron's shape: the baseline run stays FREE so it is comparable to the TradingView Strategy
# Tester, and each cost is switched on deliberately. The two costs we can measure (spread, swap)
# come off a broker profile so nobody types them; slippage keeps its own switch because it is the
# one that genuinely cannot be measured from history.

def test_an_explicit_empty_layer_list_charges_nothing():
    """The default, and it must produce NO profile — not a zero-valued one — so the charge paths
    stay unentered and the run is byte-identical to a pre-cost result."""
    from services.python_runner import _cost_profile

    assert _cost_profile({"cost_layers": []}) is None
    # ...even when the numbers are sitting right there un-ticked.
    assert _cost_profile({"cost_layers": [], "commission_per_side": 3.0,
                          "slippage_ticks": 2}) is None


def test_a_missing_layer_list_is_not_an_empty_one():
    """NULL means the row predates layers and must keep the OLD contract (charge what it stated);
    `[]` means charge nothing. Collapsing the two would silently re-price every stored run the
    first time it was retried."""
    from services.python_runner import _cost_profile

    legacy = _cost_profile({"commission_per_side": 2.25, "slippage_ticks": 1})
    assert legacy is not None and legacy.commission_per_side_per_lot == 2.25
    assert _cost_profile({"cost_layers": [], "commission_per_side": 2.25,
                          "slippage_ticks": 1}) is None


def test_spread_and_swap_come_from_the_broker_not_the_request():
    """Both are MEASUREMENTS. A field the operator can type is a field that can disagree with the
    broker, so neither is accepted from the request at all."""
    from services.python_runner import _cost_profile

    p = _cost_profile({"cost_layers": ["spread", "swap"]})
    assert p.spread == 0.22                      # Vantage gold, measured off 1.49M cached ticks
    assert p.swap is not None and p.swap.swap_long_points == -74.84
    assert p.commission_per_side_per_lot == 0.0  # not ticked
    assert p.slippage_ticks == 0


def test_the_broker_profile_changes_the_spread():
    """0.22 vs 0.33 is a 50% difference, and it is the whole reason the profile is a choice."""
    from services.python_runner import _cost_profile

    assert _cost_profile({"cost_layers": ["spread"],
                          "broker_profile": "puprime_standard"}).spread == 0.33


def test_bid_ask_fills_implies_a_spread_to_model():
    """Modelling the ask with no spread is a no-op wearing a label — the class of silent nothing
    this whole area exists to stop."""
    from services.python_runner import _cost_profile

    p = _cost_profile({"cost_layers": ["bid_ask_fills"]})
    assert p.bid_ask_fills is True and p.spread == 0.22


def test_each_layer_only_switches_on_its_own_cost():
    from services.python_runner import _cost_profile

    p = _cost_profile({"cost_layers": ["slippage"], "slippage_ticks": 2,
                       "commission_per_side": 3.0})
    assert p.slippage_ticks == 2
    assert p.commission_per_side_per_lot == 0.0, "commission was not ticked"
    assert p.spread == 0.0 and p.swap is None


def test_an_unknown_layer_or_broker_is_refused_loudly():
    """A layer nobody reads would be charged as nothing while the page said otherwise — which is
    precisely the defect this module's docstring is about."""
    import pytest as _pytest

    from services.python_runner import _cost_profile

    with _pytest.raises(ValueError):
        _cost_profile({"cost_layers": ["spred"]})
    with _pytest.raises(ValueError):
        _cost_profile({"cost_layers": ["spread"], "broker_profile": "not_a_broker"})
