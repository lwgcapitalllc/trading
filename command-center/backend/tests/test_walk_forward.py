"""Walk-forward — which windows are allowed to contribute a degradation number.

`1 - OOS/IS` is only interpretable when BOTH sides are real estimates. Two ways they are not, and
both must exclude the window rather than average it in:
  - the in-sample side had no edge to degrade from (existing `_WF_IS_SHARPE_FLOOR`);
  - either side closed too few trades to support a Sharpe at all (`_WF_MIN_TRADES_PER_WINDOW`).

The degradation maths lives inside the async orchestration, so what is pinned here is the window
FILTER, mirrored exactly, plus grading's handling of the unassessable result.
"""

import numpy as np
from services.grading import compute_grade
from services.stress_tester import (
    _WF_IS_SHARPE_FLOOR,
    _WF_MIN_TRADES_PER_WINDOW,
    _clamp_wf_degradation,
)

LIMITED = {"id": "p", "ruleset_type": "prop_funded", "max_loss_eod": 5000}


def _avg_degradation(summary: list[dict]):
    """Mirror of the filter + average at the end of run_walk_forward_task."""
    thin = [
        w["window"]
        for w in summary
        if (w.get("is_trades") or 0) < _WF_MIN_TRADES_PER_WINDOW
        or (w.get("oos_trades") or 0) < _WF_MIN_TRADES_PER_WINDOW
    ]
    degs = [
        _clamp_wf_degradation(1.0 - (w.get("oos_sharpe") or 0) / w["is_sharpe"])
        for w in summary
        if w.get("is_sharpe") and w["is_sharpe"] >= _WF_IS_SHARPE_FLOOR and w["window"] not in thin
    ]
    return float(np.mean(degs)) if degs else None


# The real windows of stress test 630cefbebd8347db: 126 trades over 5 years, split 5 ways.
REAL_RUN = [
    {"window": 1, "is_sharpe": -0.1268, "oos_sharpe": -3.6622, "is_trades": 15, "oos_trades": 6},
    {"window": 2, "is_sharpe": 1.8156, "oos_sharpe": 0.5065, "is_trades": 24, "oos_trades": 6},
    {"window": 3, "is_sharpe": -1.8737, "oos_sharpe": 1.5675, "is_trades": 10, "oos_trades": 6},
    {"window": 4, "is_sharpe": 1.5620, "oos_sharpe": 0.6940, "is_trades": 16, "oos_trades": 12},
    {"window": 5, "is_sharpe": 2.3792, "oos_sharpe": 2.6627, "is_trades": 22, "oos_trades": 8},
]


def test_the_real_run_is_not_assessable():
    """Every out-of-sample half closed 6-12 trades. Window 1 produced -3.66 and window 5 +2.66 off
    six trades each; averaging them was reported as a 38.6% degradation verdict."""
    assert _avg_degradation(REAL_RUN) is None


def test_windows_with_enough_trades_still_count():
    fat = [dict(w, is_trades=60, oos_trades=30) for w in REAL_RUN]
    deg = _avg_degradation(fat)
    assert deg is not None
    # Windows 1 and 3 remain excluded by the in-sample Sharpe floor, so 2, 4 and 5 average.
    expected = np.mean([1 - 0.5065 / 1.8156, 1 - 0.6940 / 1.5620, 1 - 2.6627 / 2.3792])
    assert deg == expected


def test_a_thin_side_excludes_the_window_even_with_a_strong_sharpe():
    one = [{"window": 1, "is_sharpe": 2.0, "oos_sharpe": 1.0, "is_trades": 50, "oos_trades": 5}]
    assert _avg_degradation(one) is None
    one[0]["oos_trades"] = _WF_MIN_TRADES_PER_WINDOW
    assert _avg_degradation(one) == 0.5


def test_missing_trade_counts_exclude_the_window():
    """A summary written before trade counts were recorded cannot prove it had enough evidence, so
    it must not be silently credited."""
    legacy = [{"window": 1, "is_sharpe": 2.0, "oos_sharpe": 1.0}]
    assert _avg_degradation(legacy) is None


# ── how grading reports it ────────────────────────────────────────────────────


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


def test_thin_windows_get_their_own_reason_and_the_actionable_fix():
    _, reasons = compute_grade(_st(), REAL_RUN, None, LIMITED)
    blob = " ".join(reasons)
    assert "too few trades" in blob
    assert "fewer walk-forward windows" in blob
    assert "IS Sharpe" not in blob


def test_a_flat_in_sample_period_still_reports_the_sharpe_reason():
    flat = [dict(w, is_trades=60, oos_trades=30, is_sharpe=0.0) for w in REAL_RUN]
    _, reasons = compute_grade(_st(), flat, None, LIMITED)
    assert any("IS Sharpe ≤ 0" in r for r in reasons)


def test_the_native_profit_factor_path_is_unchanged():
    native = [{"window": 1, "is_pf": 0.0, "oos_pf": 0.0}]
    _, reasons = compute_grade(_st(), native, None, LIMITED)
    assert any("IS profit factor ≤ 0" in r for r in reasons)


def test_unassessable_walk_forward_caps_the_grade_at_b():
    """It stays NEUTRAL — no penalty for a measurement that never happened — but it may not earn an
    A. An A off "the Monte Carlo passed and we have no out-of-sample evidence" reads as proof the
    strategy held up, which is a claim nothing in the run supports. Monte Carlo here is clean
    enough for an A on its own; the missing evidence is the only thing holding it to B."""
    clean_mc = _st(sensitivity_max_degradation=0.05)
    assert compute_grade(clean_mc, None, {"p": {}}, LIMITED)[0] == "A"  # WF simply not run
    grade, reasons = compute_grade(clean_mc, REAL_RUN, {"p": {}}, LIMITED)
    assert grade == "B"
    assert any("Capped at B" in r for r in reasons)


def test_the_cap_is_not_a_penalty_below_b():
    """A run that was only ever going to be a C must still be a C — the cap is a ceiling, not a
    deduction, so it must not push anything DOWN."""
    weak = _st(pct1_max_dd=9000.0, pct5_max_dd=8000.0, median_max_dd=4000.0)
    assert compute_grade(weak, REAL_RUN, None, LIMITED)[0] == "C"


def test_a_walk_forward_that_was_never_run_is_not_capped():
    """Deliberately uncapped: the not-run path carries its own 'grade may improve' caveat and is
    how every auto-triggered Monte-Carlo-only test runs, so capping it would relabel the library."""
    grade, reasons = compute_grade(_st(), None, None, LIMITED)
    assert grade == "A"
    assert any("not run" in r for r in reasons)
