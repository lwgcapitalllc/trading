"""
Robustness grading — A through F.
compute_grade() is called after Monte Carlo (and optionally walk-forward + sensitivity) complete.
"""

from __future__ import annotations
from typing import Optional

from services.metrics import effective_dd_limit_usd


def compute_grade(
    st: dict,
    walk_forward: Optional[list],
    sensitivity: Optional[dict],
    ruleset: dict,
) -> tuple[str, list[str]]:
    """
    Returns (grade, reasons) where grade is 'A'|'B'|'C'|'D'|'F'.

    When walk_forward/sensitivity are None (MC-only trigger), grade is computed
    on Monte Carlo alone — partial grade, marked with '_mc' suffix internally
    but still shown as A-F. Walk-forward and sensitivity tighten the grade when available.
    """
    reasons: list[str] = []
    # Personal/demo: max_loss_eod = 0 is a sentinel (no trailing EOD rule); the helper
    # translates their drawdown-from-peak rule into the dollar limit MC drawdown uses.
    max_loss = effective_dd_limit_usd(ruleset)

    pct1_max_dd = st.get("pct1_max_dd") or float("inf")
    pct5_max_dd = st.get("pct5_max_dd") or float("inf")
    median_max_dd = st.get("median_max_dd") or float("inf")
    median_final_pnl = st.get("median_final_pnl") or 0.0
    prob_breach = st.get("prob_breach") or 1.0

    pct1_passes = max_loss > 0 and pct1_max_dd <= max_loss
    pct5_passes = max_loss > 0 and pct5_max_dd <= max_loss
    median_passes = max_loss > 0 and median_max_dd <= max_loss

    wf_degradation = st.get("walk_forward_degradation")
    wf_solid = wf_degradation is not None and wf_degradation < 0.20
    wf_ok    = wf_degradation is not None and wf_degradation < 0.30
    # WF ran but degradation is None = not assessable (1 - OOS/IS is a meaningless signed ratio
    # when the in-sample metric is ≤ 0). Treat it like not-run: don't read the absent number as
    # "solid" and don't penalise on it either. The metric depends on the WF path: the serial path
    # degrades on Sharpe, the native (optimization-derived) path on profit factor.
    wf_not_assessable = walk_forward is not None and wf_degradation is None
    # If walk-forward wasn't run (or couldn't be assessed), don't penalise on it
    wf_not_run = walk_forward is None or wf_not_assessable

    sens_degradation = st.get("sensitivity_max_degradation")
    sens_solid = sens_degradation is not None and sens_degradation < 0.25
    sens_ok    = sens_degradation is not None and sens_degradation < 0.40
    sens_not_run = sensitivity is None

    if wf_not_assessable:
        # Name the metric the path actually used: native WF rows carry per-window profit factor
        # (is_pf), the serial path carries Sharpe. Detect by the summary shape so the reason
        # doesn't claim "Sharpe" on a PF-based native run.
        pf_based = bool(walk_forward) and any("is_pf" in w for w in walk_forward)
        metric = "IS profit factor ≤ 0" if pf_based else "IS Sharpe ≤ 0"
        reasons.append(f"Walk-forward ran but IS→OOS degradation is not assessable ({metric})")

    # ── A: worst-1% passes, WF solid (or not run), sensitivity solid (or not run)
    if pct1_passes and (wf_solid or wf_not_run) and (sens_solid or sens_not_run):
        reasons.append("Worst 1% of Monte Carlo simulations stays under ruleset limit")
        if not wf_not_run:
            reasons.append(f"Walk-forward IS→OOS degradation only {wf_degradation*100:.0f}%")
        if not sens_not_run:
            reasons.append(f"Parameter sensitivity worst case {sens_degradation*100:.0f}% drop")
        if walk_forward is None or sens_not_run:
            reasons.append("Walk-forward / sensitivity not run — grade may improve with full analysis")
        return ("A", reasons)

    # ── B: worst-5% passes, WF ok (or not run), sensitivity ok (or not run)
    if pct5_passes and (wf_ok or wf_not_run) and (sens_ok or sens_not_run):
        reasons.append("Worst 5% of Monte Carlo simulations stays under ruleset limit")
        if not wf_not_run:
            reasons.append(f"Walk-forward degradation {wf_degradation*100:.0f}%")
        if not sens_not_run:
            reasons.append(f"Parameter sensitivity worst case {sens_degradation*100:.0f}% drop")
        if walk_forward is None or sens_not_run:
            reasons.append("Walk-forward / sensitivity not run — grade may improve with full analysis")
        return ("B", reasons)

    # ── C: median passes but worst-5% doesn't
    if median_passes:
        if not pct5_passes and max_loss > 0:
            reasons.append(f"Worst 5% breaches limit by ${(pct5_max_dd - max_loss):.0f}")
        if wf_degradation is not None and wf_degradation >= 0.30:
            reasons.append(f"Walk-forward shows {wf_degradation*100:.0f}% IS→OOS degradation")
        if sens_degradation is not None and sens_degradation >= 0.40:
            reasons.append(f"Parameter sensitivity worst case is {sens_degradation*100:.0f}%")
        if not reasons:
            reasons.append("Median simulation passes but tail risk is elevated")
        return ("C", reasons)

    # ── D: median profitable but drawdown fails
    if median_final_pnl > 0:
        reasons.append("Median simulation is profitable but median drawdown breaches the limit")
        reasons.append(f"{prob_breach*100:.0f}% probability of breaching ruleset limit at some point")
        return ("D", reasons)

    # ── F: median simulation loses money
    reasons.append(f"Median simulation ends with loss of ${abs(median_final_pnl):.0f}")
    reasons.append(f"{prob_breach*100:.0f}% probability of breaching ruleset limit")
    return ("F", reasons)
