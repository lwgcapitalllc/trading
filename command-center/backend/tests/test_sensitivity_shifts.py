"""Sensitivity — which perturbations are worth a backtest, and what a wobble is measured in.

`run_sensitivity_task` is a long async orchestration around VPS/local backtests, so what is pinned
here is the SHIFT SELECTION it performs: a perturbed value that equals the baseline (or one already
measured for the same param) re-runs the identical backtest and books a 0% delta, which reads as
"this setting is rock solid" when the truth is "this setting was never tested".

Measured on stress test 630cefbebd8347db: 43 of 60 sensitivity backtests were exact baseline
re-runs — ~56 minutes of a 78-minute phase, and 11 params reported a false all-clear.
"""

import numpy as np
import pytest

from services.stress_tester import run_sensitivity_task  # noqa: F401  (import guard)


def _shifts_for(baseline_val, ptype: str, shifts) -> tuple[list, list]:
    """Mirror of the selection loop in run_sensitivity_task. Returns (measured, skipped)."""
    measured, skipped, seen = [], [], set()
    for label, factor in shifts:
        new_val = baseline_val * factor
        if ptype == "int":
            new_val = int(round(new_val))
        if new_val == baseline_val or new_val in seen:
            skipped.append((label, new_val))
            continue
        seen.add(new_val)
        measured.append((label, new_val))
    return measured, skipped


NT8_SHIFTS = [("+10%", 1.10), ("-10%", 0.90), ("+25%", 1.25), ("-25%", 0.75)]


def test_a_zero_param_has_no_measurable_shift():
    """0 x anything is 0, so all four shifts re-run the baseline. Real case: exec_tp1_pct and
    exec_sl_buf_tk both ship at 0, and each burned four backtests reporting a false 0% delta."""
    measured, skipped = _shifts_for(0.0, "double", NT8_SHIFTS)
    assert measured == []
    assert len(skipped) == 4


def test_int_shifts_that_round_together_are_measured_once():
    """Pivot width 5: +10% -> 6 and +25% -> 6; -10% -> 4 and -25% -> 4. Four shifts, two values."""
    measured, skipped = _shifts_for(5, "int", NT8_SHIFTS)
    assert sorted(v for _, v in measured) == [4, 6]
    assert len(skipped) == 2


def test_an_int_too_small_to_move_is_fully_skipped():
    """Baseline 1: every shift rounds back to 1, so nothing is testable at all."""
    measured, _ = _shifts_for(1, "int", NT8_SHIFTS)
    assert measured == []


def test_a_normal_param_keeps_all_four_shifts():
    measured, skipped = _shifts_for(10.0, "double", NT8_SHIFTS)
    assert [v for _, v in measured] == pytest.approx([11.0, 9.0, 12.5, 7.5])
    assert skipped == []


def test_the_real_run_would_have_dropped_two_thirds_of_its_backtests():
    """The 15 params of stress test 630cefbebd8347db, at their real base values."""
    params = [
        ("aplus_window", 4320, "int"), ("exec_risk_pct", 10, "double"),
        ("exec_sl_buf_tk", 0, "double"), ("exec_tp1_pct", 0, "double"),
        ("exec_tp2_pct", -4, "double"), ("exec_be_buf_tk", 30, "double"),
        ("exec_struct_trail_buf_tk", 20, "double"), ("exec_trail_step", 5, "double"),
        ("div_rsi_len", 14, "int"), ("div_pivot_len", 5, "int"),
        ("div_valid_bars", 100, "int"), ("div_extreme_ob", 80, "int"),
        ("div_extreme_os", 20, "int"), ("flat_by_close_min", 15, "int"),
        ("exec_scratch_r", 0.15, "double"),
    ]
    total_measured = sum(len(_shifts_for(v, t, NT8_SHIFTS)[0]) for _, v, t in params)
    total_skipped = sum(len(_shifts_for(v, t, NT8_SHIFTS)[1]) for _, v, t in params)
    assert total_measured + total_skipped == 60
    # 4 (exec_sl_buf_tk) + 4 (exec_tp1_pct) + 2 (div_pivot_len rounding) = 10 backtests saved,
    # each ~78s on that run. The remaining waste is params the config genuinely ignores, which
    # no arithmetic check can predict — see the stress-test accuracy notes.
    assert total_skipped == 10


# ── the scored metric ─────────────────────────────────────────────────────────
# Sensitivity scores a PROFIT-FACTOR change, not a net-P&L change. Net P&L is a dollar figure, so
# any parameter that scales position size dominates by arithmetic rather than by fragility — and
# the optimizer-grid path already reported a profit-factor drop into the SAME field, judged by the
# SAME grading thresholds. The two had to agree.

def _degradation(baseline_pf, child_pf):
    """Mirror of the scoring line in run_sensitivity_task."""
    if baseline_pf is None or not np.isfinite(baseline_pf) or baseline_pf <= 0:
        return None
    if child_pf is None or not np.isfinite(child_pf):
        return None
    return abs(child_pf - baseline_pf) / baseline_pf


def test_scaling_every_trade_equally_is_not_fragility():
    """Doubling position size doubles both gross profit and gross loss, so profit factor holds.
    Measured on the real run: exec_risk_pct scored 85.8% on P&L and 11.8% on profit factor."""
    assert _degradation(5.242, 5.242) == 0.0


def test_a_real_edge_change_still_registers():
    assert _degradation(5.242, 4.0) == pytest.approx(0.2369, abs=1e-4)


def test_magnitude_is_absolute_so_an_improvement_counts_too():
    """A shift that IMPROVES the result is equally good evidence that the result moves."""
    assert _degradation(4.0, 5.0) == _degradation(4.0, 3.0)


def test_an_unusable_profit_factor_is_none_never_zero():
    """0.0 would read as 'tested, nothing moved' — the most reassuring answer — on a run where
    nothing was measured at all."""
    assert _degradation(None, 4.0) is None
    assert _degradation(0.0, 4.0) is None
    assert _degradation(float("inf"), 4.0) is None
    assert _degradation(5.242, None) is None      # child run failed
    assert _degradation(5.242, float("inf")) is None  # child had no losing trade
