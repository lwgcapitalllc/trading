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
    "id": "unconstrained",
    "name": "Unconstrained (No Limits)",
    "ruleset_type": "personal",
    "max_loss_eod": 0,
    "max_drawdown_from_peak_pct": None,
    "account_size": 10000,
}


def _st(**over) -> dict:
    # Drawdown percentiles are ordered by construction — the worst-1% is always at least the
    # worst-5%, which is always at least the median. A fixture that breaks that ordering tests a
    # state Monte Carlo cannot produce.
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


# ── falsy-vs-None ─────────────────────────────────────────────────────────────


def test_zero_prob_breach_is_reported_as_zero_not_one():
    """`prob_breach or 1.0` turned a perfect 0.0 into 1.0 and told the user '100% probability of
    breaching' about a strategy that breached in none of 11,000 simulations."""
    # Force the D branch (median profitable, drawdown over the limit) so prob_breach is printed.
    grade, reasons = compute_grade(
        _st(pct1_max_dd=9000.0, pct5_max_dd=8000.0, median_max_dd=7000.0, prob_breach=0.0),
        None,
        None,
        LIMITED,
    )
    assert grade == "D"
    assert any("0% probability" in r for r in reasons)
    assert not any("100% probability" in r for r in reasons)


def test_zero_drawdown_passes_every_limit_check():
    """`pct1_max_dd or inf` turned a real 0.0 drawdown into infinity, failing every check."""
    grade, _ = compute_grade(
        _st(pct1_max_dd=0.0, pct5_max_dd=0.0, median_max_dd=0.0), None, None, LIMITED
    )
    assert grade == "A"


def test_missing_metric_still_falls_back():
    """The None fallback must survive: an absent drawdown is unknown, so it cannot pass a limit."""
    grade, _ = compute_grade(
        _st(pct1_max_dd=None, pct5_max_dd=None, median_max_dd=None), None, None, LIMITED
    )
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
    grade, reasons = compute_grade(
        st, [{"window": 1, "is_trades": 60, "oos_trades": 40}], {}, LIMITED
    )
    assert grade == "A"
    assert any("no measurable result" in r for r in reasons)


def test_limited_ruleset_grades_are_untouched():
    solid = {"walk_forward_degradation": 0.10, "sensitivity_max_degradation": 0.10}
    wf, sens = [{"window": 1}], {"p": {}}
    assert compute_grade(_st(**solid), wf, sens, LIMITED)[0] == "A"
    assert compute_grade(_st(pct1_max_dd=6000.0, **solid), wf, sens, LIMITED)[0] == "B"
    assert (
        compute_grade(_st(pct1_max_dd=6000.0, pct5_max_dd=6000.0, **solid), wf, sens, LIMITED)[0]
        == "C"
    )
    assert (
        compute_grade(
            _st(pct1_max_dd=9000.0, pct5_max_dd=8000.0, median_max_dd=7000.0, **solid),
            wf,
            sens,
            LIMITED,
        )[0]
        == "D"
    )
    assert (
        compute_grade(
            _st(
                pct1_max_dd=9000.0,
                pct5_max_dd=8000.0,
                median_max_dd=7000.0,
                median_final_pnl=-500.0,
                **solid,
            ),
            wf,
            sens,
            LIMITED,
        )[0]
        == "F"
    )


# ── a B names what kept it from an A ──────────────────────────────────────────
#
# Non-vacuity is by MUTATION, each run and each turning its named test red: dropping the worst-1%
# line; dropping the "an A needs" suffix from the walk-forward line; the same for sensitivity;
# restoring the old `a_blocked_no_evidence and pct1_passes` guard; rendering the miss at the base
# decimals only (the 55.0%-vs-55.0% case). Against HEAD every one of them fails because none of the
# sentences existed.

# Aaron's own 55% ruleset, on the percent basis a compounding run is graded on.
RISK_55 = {
    "id": "personal_forex_risk",
    "name": "Personal Forex — 55% Drawdown",
    "ruleset_type": "personal",
    "max_loss_eod": 0,
    "max_drawdown_from_peak_pct": 55.0,
    "account_size": 10000,
}


def _pct_st(**over) -> dict:
    base = _st(
        dd_basis="percent",
        pct1_max_dd_pct=55.55,
        pct5_max_dd_pct=45.0,
        median_max_dd_pct=34.1,
    )
    base.update(over)
    return base


def _names_a_miss(reasons: list[str]) -> bool:
    return any(" an A " in f" {r} " or r.startswith("An A ") for r in reasons)


def test_a_B_that_missed_on_the_worst_1pct_says_by_how_much():
    """The run that asked the question: grade B on the 55% ruleset, and nothing said why not A.
    The worst 1% was stored as 55.55% against 55%, and that is the sentence the reader needed.

    ⚠ 55.55 is 55.5499… in binary, so it prints 55.5% here — and the page's own tile prints it
    the same way, so the reason and the tile agree."""
    wf = [{"window": 1, "is_trades": 60, "oos_trades": 40}]
    grade, reasons = compute_grade(_pct_st(walk_forward_degradation=0.11), wf, None, RISK_55)
    assert grade == "B"
    assert any("55.5%" in r and "55.0% limit" in r and "an A needs" in r for r in reasons), reasons


def test_a_miss_is_printed_with_enough_decimals_to_READ_as_a_miss():
    """At one decimal 55.04% and 55% both print 55.0%, so the reason would say a drawdown equal
    to the limit failed it — a sentence that contradicts itself."""
    grade, reasons = compute_grade(_pct_st(pct1_max_dd_pct=55.04), None, None, RISK_55)
    assert grade == "B"
    line = next(r for r in reasons if "Worst 1%" in r)
    assert "55.04%" in line and "55.00%" in line, line


def test_a_B_held_back_by_walk_forward_names_the_bar():
    grade, reasons = compute_grade(
        _st(pct1_max_dd=900.0, walk_forward_degradation=0.24),
        [{"window": 1, "is_trades": 60, "oos_trades": 40}],
        None,
        LIMITED,
    )
    assert grade == "B"
    assert "Walk-forward degradation 24% — an A needs under 20%" in reasons


def test_a_B_held_back_by_sensitivity_names_the_bar():
    grade, reasons = compute_grade(
        _st(pct1_max_dd=900.0, sensitivity_max_degradation=0.30), None, {"p": {}}, LIMITED
    )
    assert grade == "B"
    assert "Parameter sensitivity worst case 30% drop — an A needs under 25%" in reasons


def test_a_B_that_missed_TWO_bars_names_both():
    """Naming only the first miss implies fixing it earns the A. With the worst 1% over the limit
    AND no walk-forward evidence, the reader must be told both."""
    wf = [{"window": 1, "is_trades": 5, "oos_trades": 3}]  # ran, too thin to assess
    grade, reasons = compute_grade(_st(pct1_max_dd=6000.0), wf, None, LIMITED)
    assert grade == "B"
    assert any(r.startswith("Worst 1% of simulations reaches") for r in reasons), reasons
    assert "An A also needs walk-forward evidence, and this run produced none" in reasons


def test_EVERY_B_names_at_least_one_reason_it_is_not_an_A():
    """The property, over every way a run can land on B: worst 1% pass/fail x walk-forward
    none/solid/ok-not-solid/unassessable x sensitivity none/solid/ok-not-solid."""
    wf_cases = [
        (None, None),
        ([{"window": 1, "is_trades": 60, "oos_trades": 40}], 0.10),
        ([{"window": 1, "is_trades": 60, "oos_trades": 40}], 0.25),
        ([{"window": 1, "is_trades": 5, "oos_trades": 3}], None),
    ]
    sens_cases = [(None, None), ({"p": {}}, 0.10), ({"p": {}}, 0.30)]
    seen_b = 0
    for pct1 in (900.0, 6000.0):
        for wf, wf_deg in wf_cases:
            for sens, sens_deg in sens_cases:
                st = _st(
                    pct1_max_dd=pct1,
                    walk_forward_degradation=wf_deg,
                    sensitivity_max_degradation=sens_deg,
                )
                grade, reasons = compute_grade(st, wf, sens, LIMITED)
                if grade == "B":
                    seen_b += 1
                    assert _names_a_miss(reasons), (pct1, wf_deg, sens_deg, reasons)
    assert seen_b >= 10, "the grid must actually reach B, or it proves nothing"


def test_an_A_carries_no_miss_line():
    """The sentences belong to B. An A that said "an A needs" would contradict its own letter."""
    grade, reasons = compute_grade(
        _st(walk_forward_degradation=0.10, sensitivity_max_degradation=0.10),
        [{"window": 1, "is_trades": 60, "oos_trades": 40}],
        {"p": {}},
        LIMITED,
    )
    assert grade == "A"
    assert not _names_a_miss(reasons), reasons
