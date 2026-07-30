"""Grading — the A-F robustness verdict.

Two classes of bug are pinned here because both produced a CONFIDENT WRONG ANSWER rather than an
error, which is the only kind a user cannot catch:
  1. falsy-vs-None metric reads (`x or fallback`) — a real 0.0 was silently replaced by the fallback;
  2. grading against a ruleset that has no drawdown limit — D was the ceiling for every strategy.
"""

from services.grading import compute_grade


# A prop-style ruleset with a real $5,000 drawdown limit.
LIMITED = {"id": "prop", "name": "Prop $50k", "ruleset_type": "prop_funded", "max_loss_eod": 5000}
# The "Unconstrained (No Limits)" row: personal type, no trailing EOD rule, no drawdown-from-peak.
UNLIMITED = {
    "id": "unconstrained", "name": "Unconstrained (No Limits)", "ruleset_type": "personal",
    "max_loss_eod": 0, "max_drawdown_from_peak_pct": None, "account_size": 10000,
}


def _st(**over) -> dict:
    # Drawdown percentiles are ordered by construction — the worst-1% is always at least the
    # worst-5%, which is always at least the median. A fixture that breaks that ordering tests a
    # state Monte Carlo cannot produce.
    base = {
        "pct1_max_dd": 1000.0, "pct5_max_dd": 800.0, "median_max_dd": 500.0,
        "median_final_pnl": 20000.0, "prob_breach": 0.0,
        "walk_forward_degradation": None, "sensitivity_max_degradation": None,
    }
    base.update(over)
    return base


# ── falsy-vs-None ─────────────────────────────────────────────────────────────

def test_zero_prob_breach_is_reported_as_zero_not_one():
    """`prob_breach or 1.0` turned a perfect 0.0 into 1.0 and told the user '100% probability of
    breaching' about a strategy that breached in none of 11,000 simulations."""
    # Force the D branch (median profitable, drawdown over the limit) so prob_breach is printed.
    grade, reasons = compute_grade(_st(pct1_max_dd=9000.0, pct5_max_dd=8000.0, median_max_dd=7000.0, prob_breach=0.0), None, None, LIMITED)
    assert grade == "D"
    assert any("0% probability" in r for r in reasons)
    assert not any("100% probability" in r for r in reasons)


def test_zero_drawdown_passes_every_limit_check():
    """`pct1_max_dd or inf` turned a real 0.0 drawdown into infinity, failing every check."""
    grade, _ = compute_grade(_st(pct1_max_dd=0.0, pct5_max_dd=0.0, median_max_dd=0.0), None, None, LIMITED)
    assert grade == "A"


def test_missing_metric_still_falls_back():
    """The None fallback must survive: an absent drawdown is unknown, so it cannot pass a limit."""
    grade, _ = compute_grade(_st(pct1_max_dd=None, pct5_max_dd=None, median_max_dd=None), None, None, LIMITED)
    assert grade == "D"  # median profitable, no assessable drawdown


# ── no drawdown limit ─────────────────────────────────────────────────────────

def test_no_drawdown_limit_is_not_graded():
    """A ruleset with no limit has nothing for the drawdown grade to measure against. It used to
    fall through to D and blame a limit that does not exist."""
    grade, reasons = compute_grade(_st(), None, None, UNLIMITED)
    assert grade is None
    assert any("no drawdown limit" in r for r in reasons)
    assert not any("breaches the limit" in r for r in reasons)


def test_no_drawdown_limit_still_reports_what_did_run():
    """Ungraded must not mean uninformative — the MC/WF/sensitivity numbers still reach the user."""
    st = _st(walk_forward_degradation=0.386, sensitivity_max_degradation=0.858)
    grade, reasons = compute_grade(st, [{"window": 1, "is_sharpe": 1.0}], {"p": {}}, UNLIMITED)
    assert grade is None
    blob = " ".join(reasons)
    assert "39%" in blob and "86%" in blob


def test_a_perfect_strategy_could_never_beat_d_before_this():
    """The regression itself: worst-1% clean, walk-forward solid, sensitivity solid — and the old
    code still returned D purely because the ruleset carried no limit."""
    st = _st(walk_forward_degradation=0.05, sensitivity_max_degradation=0.05)
    assert compute_grade(st, [{"window": 1}], {"p": {}}, LIMITED)[0] == "A"
    assert compute_grade(st, [{"window": 1}], {"p": {}}, UNLIMITED)[0] is None


# ── the limited path is unchanged ─────────────────────────────────────────────

def test_unassessable_sensitivity_is_treated_as_not_run():
    """Sensitivity that RAN but measured nothing (no tunable params, or an unusable baseline profit
    factor) used to silently block A and B — a penalty for a measurement that never happened."""
    st = _st(walk_forward_degradation=0.10, sensitivity_max_degradation=None)
    grade, reasons = compute_grade(st, [{"window": 1, "is_trades": 60, "oos_trades": 40}], {}, LIMITED)
    assert grade == "A"
    assert any("no measurable result" in r for r in reasons)


def test_limited_ruleset_grades_are_untouched():
    solid = {"walk_forward_degradation": 0.10, "sensitivity_max_degradation": 0.10}
    wf, sens = [{"window": 1}], {"p": {}}
    assert compute_grade(_st(**solid), wf, sens, LIMITED)[0] == "A"
    assert compute_grade(_st(pct1_max_dd=6000.0, **solid), wf, sens, LIMITED)[0] == "B"
    assert compute_grade(_st(pct1_max_dd=6000.0, pct5_max_dd=6000.0, **solid), wf, sens, LIMITED)[0] == "C"
    assert compute_grade(_st(pct1_max_dd=9000.0, pct5_max_dd=8000.0, median_max_dd=7000.0, **solid), wf, sens, LIMITED)[0] == "D"
    assert compute_grade(_st(pct1_max_dd=9000.0, pct5_max_dd=8000.0, median_max_dd=7000.0, median_final_pnl=-500.0, **solid), wf, sens, LIMITED)[0] == "F"
