"""Drawdown basis — dollars vs percent, and what a no-limits ruleset is measured against.

A dollar drawdown is only comparable to a fixed dollar limit while the account stays near the size
that limit was written for. A compounding account does not: on run 06f7eece0db1 the dollar view
reported a 100% breach of TOTAL RUIN ($10k on a $10k account) across 20,000 simulations in which
the account was never once wiped out — 0.00% real ruin, 60.5% worst-1% drawdown.

So the run itself decides: percent once it compounds, dollars otherwise, recorded as `dd_basis`.
"""

import numpy as np
import pytest

from services.grading import compute_grade
from services.metrics import effective_dd_limit_pct, effective_dd_limit_usd
from services.stress_tester import run_monte_carlo

PROP = {"id": "prop", "name": "Prop $50k", "ruleset_type": "prop_funded",
        "max_loss_eod": 5000, "account_size": 50000}
DEMO = {"id": "demo", "name": "Demo", "ruleset_type": "personal",
        "max_drawdown_from_peak_pct": 15.0, "account_size": 10000, "max_loss_eod": 0}
NO_LIMIT = {"id": "unconstrained", "name": "Unconstrained (No Limits)", "ruleset_type": "personal",
            "max_loss_eod": 0, "max_drawdown_from_peak_pct": None, "account_size": 10000}


def _compounding_run(n=120, start=10_000.0, risk=0.10, seed=2):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.03, risk, n)
    bal, pnls, balances = start, [], []
    for r in rets:
        balances.append(bal)
        pnls.append(bal * r)
        bal += bal * r
    return pnls, balances


def _fixed_size_run(n=120, start=50_000.0):
    rng = np.random.default_rng(1)
    pnls = rng.normal(200.0, 800.0, n)
    bal, balances = start, []
    for p in pnls:
        balances.append(bal)
        bal += p
    return list(pnls), balances


# ── the percent limit ─────────────────────────────────────────────────────────

def test_a_prop_dollar_limit_converts_to_its_percent():
    """$5,000 on a $50,000 account is 10%. Nothing new to define — it was always the same rule."""
    assert effective_dd_limit_pct(PROP) == pytest.approx(10.0)
    assert effective_dd_limit_usd(PROP) == 5000.0


def test_a_personal_percent_limit_is_used_as_stated():
    assert effective_dd_limit_pct(DEMO) == pytest.approx(15.0)


def test_a_ruleset_with_no_limit_states_none():
    """None, not 0.0 and not a guess — the caller substitutes ruin."""
    assert effective_dd_limit_pct(NO_LIMIT) is None
    assert effective_dd_limit_pct(None) is None


# ── which basis a run gets ────────────────────────────────────────────────────

def test_a_compounding_run_is_measured_in_percent():
    pnls, balances = _compounding_run()
    mc = run_monte_carlo(pnls, NO_LIMIT, 2000, 500, 100, balances)
    assert mc["dd_basis"] == "percent"
    assert mc["pct1_max_dd_pct"] is not None
    # Ordered by construction, and a percentage of an account cannot exceed 100.
    assert 0 < mc["median_max_dd_pct"] <= mc["pct5_max_dd_pct"] <= mc["pct1_max_dd_pct"] <= 100


def test_a_fixed_size_run_stays_in_dollars():
    """It has no balance series of its own, so a percent would need an account size the simulation
    is not given. Dollars, exactly as before."""
    pnls, balances = _fixed_size_run()
    mc = run_monte_carlo(pnls, PROP, 2000, 500, 100, balances)
    assert mc["dd_basis"] == "dollars"
    assert mc["median_max_dd_pct"] is None
    assert mc["pct1_max_dd"] > 0


def test_breach_probability_is_measured_on_the_graded_basis():
    """If the headline number and the letter come off different bases they can contradict."""
    pnls, balances = _compounding_run()
    mc = run_monte_carlo(pnls, DEMO, 2000, 500, 100, balances)
    assert mc["dd_basis"] == "percent"
    # A 10%-risk compounding run against a 15% rule breaches essentially always — and it is the
    # PERCENT drawdown being tested, not a dollar figure inflated by the account's own growth.
    assert mc["prob_breach"] == pytest.approx(1.0, abs=0.01)


def test_no_stated_limit_reports_no_breach_probability():
    """Nothing to breach, so None — not 0.0 (never breaches) and not 1.0 (always does)."""
    pnls, balances = _compounding_run()
    mc = run_monte_carlo(pnls, NO_LIMIT, 2000, 500, 100, balances)
    assert mc["prob_breach"] is None
    assert mc["prob_pass_eval"] is None


# ── how grading reads it ──────────────────────────────────────────────────────

def _st(**over):
    base = {"median_final_pnl": 20000.0, "prob_breach": 0.0, "dd_basis": "percent",
            "median_max_dd_pct": 30.0, "pct5_max_dd_pct": 50.0, "pct1_max_dd_pct": 60.0,
            "median_max_dd": 84000.0, "pct5_max_dd": 237000.0, "pct1_max_dd": 359000.0,
            "walk_forward_degradation": 0.05, "sensitivity_max_degradation": 0.05}
    base.update(over)
    return base


def test_no_stated_limit_stays_ungraded_even_on_the_percent_basis():
    """Ruin (100%) was tried as the default bar and REJECTED: a compounding simulation can never
    reach a zero balance, so a 10%-risk run with a 70.4% worst-1% drawdown clears it and would have
    been handed an A. A bar almost nothing can fail is not a grade — so this stays ungraded, and
    the reason tells the user to state a drawdown percent they actually accept."""
    grade, reasons = compute_grade(_st(), None, {"p": {}}, NO_LIMIT)
    assert grade is None
    assert any("drawdown percent you are willing to accept" in r for r in reasons)


def test_the_percent_limit_is_enforced_when_the_ruleset_states_one():
    """60% worst-1% against a 15% rule fails, even though ruin would have passed."""
    grade, _ = compute_grade(_st(), None, None, DEMO)
    assert grade == "D"


def test_reasons_are_written_in_the_unit_being_judged():
    grade, reasons = compute_grade(_st(median_max_dd_pct=10.0, pct5_max_dd_pct=20.0,
                                       pct1_max_dd_pct=25.0), None, None, DEMO)
    assert grade == "C"
    assert any("%" in r and "$" not in r for r in reasons)


def test_rows_written_before_the_percent_columns_still_grade_in_dollars():
    """No dd_basis and no percent values — an old record must keep reproducing its stored grade."""
    old = {"median_final_pnl": 20000.0, "prob_breach": 0.0,
           "median_max_dd": 500.0, "pct5_max_dd": 800.0, "pct1_max_dd": 1000.0,
           "walk_forward_degradation": None, "sensitivity_max_degradation": None}
    assert compute_grade(old, None, None, PROP)[0] == "A"


def test_a_fixed_size_run_against_no_limit_is_still_ungraded():
    """Honest edge case: dollars basis, no dollar limit, and no percent to fall back on."""
    old = {"median_final_pnl": 20000.0, "prob_breach": 0.0, "dd_basis": "dollars",
           "median_max_dd": 500.0, "pct5_max_dd": 800.0, "pct1_max_dd": 1000.0,
           "walk_forward_degradation": None, "sensitivity_max_degradation": None}
    grade, reasons = compute_grade(old, None, None, NO_LIMIT)
    assert grade is None
    assert any("no drawdown limit" in r for r in reasons)
