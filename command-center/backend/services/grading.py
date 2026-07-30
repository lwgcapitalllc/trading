"""
Robustness grading — A through F.
compute_grade() is called after Monte Carlo (and optionally walk-forward + sensitivity) complete.
"""

from __future__ import annotations
from typing import Optional

from services.metrics import effective_dd_limit_pct, effective_dd_limit_usd


def _num(value, fallback: float) -> float:
    """Read a stored metric, falling back ONLY when it is genuinely absent.

    `value or fallback` is wrong here and was a live bug: every metric in this module can
    legitimately be 0.0, which is falsy, so a stored `prob_breach = 0.0` (a strategy that never
    breached in 11,000 simulations) was read as the 1.0 fallback and reported to the user as
    "100% probability of breaching ruleset limit". The drawdown reads had the same defect in the
    opposite direction — a 0.0 drawdown became `inf` and failed every limit check.
    """
    return fallback if value is None else float(value)


def compute_grade(
    st: dict,
    walk_forward: Optional[list],
    sensitivity: Optional[dict],
    ruleset: dict,
) -> tuple[Optional[str], list[str]]:
    """
    Returns (grade, reasons) where grade is 'A'|'B'|'C'|'D'|'F', or None when the run cannot
    be graded at all (see the no-drawdown-limit branch below). A None grade is a first-class
    outcome, not an error — the UI omits the letter and shows the reasons instead.

    When walk_forward/sensitivity are None (MC-only trigger), grade is computed
    on Monte Carlo alone — partial grade, marked with '_mc' suffix internally
    but still shown as A-F. Walk-forward and sensitivity tighten the grade when available.
    """
    reasons: list[str] = []
    median_final_pnl = _num(st.get("median_final_pnl"), 0.0)
    prob_breach = _num(st.get("prob_breach"), 1.0)

    # ── Which basis the drawdown is judged on ────────────────────────────────────
    # PERCENT once the run compounds, DOLLARS otherwise, decided by the Monte Carlo and recorded on
    # the row. A dollar drawdown stops being comparable to a fixed dollar limit as soon as the
    # account grows away from the size that limit was written for: on run 06f7eece0db1 the dollar
    # comparison reported a 100% breach of TOTAL RUIN across 20,000 simulations in which the account
    # was never once wiped out.
    #
    # `dd_basis` is absent on rows written before 2026-07-30, so those keep the dollar path and
    # their stored grades stay reproducible.
    #
    # RUIN IS NOT USED AS THE DEFAULT LIMIT, and the reason is worth recording because it looks
    # like it should be. Losing 100% is the one drawdown bar that needs no ruleset and no opinion,
    # so grading a no-limits run against it was the obvious way to make that case gradeable.
    # Measured before shipping: it does not discriminate. A compounding simulation cannot reach a
    # balance of zero (every 1+r is guarded > 0), so the bar is only ever brushed by a strategy
    # already at the point of total collapse — a 10%-risk run with a 70.4% worst-1% drawdown clears
    # it comfortably, and would have been handed an A. A bar almost nothing can fail is not a grade.
    #
    # So a percent limit is used only when the ruleset STATES one. Where it does not, the run stays
    # ungraded (below) — "how much drawdown is acceptable" is a preference, and inventing a number
    # for the user would be exactly the flattering answer this whole pass exists to remove.
    unit = "%" if st.get("dd_basis") == "percent" and st.get("pct1_max_dd_pct") is not None else "$"
    if unit == "%":
        limit = effective_dd_limit_pct(ruleset) or 0.0
        pct1_max_dd = _num(st.get("pct1_max_dd_pct"), float("inf"))
        pct5_max_dd = _num(st.get("pct5_max_dd_pct"), float("inf"))
        median_max_dd = _num(st.get("median_max_dd_pct"), float("inf"))
    else:
        # Personal/demo: max_loss_eod = 0 is a sentinel (no trailing EOD rule); the helper
        # translates their drawdown-from-peak rule into the dollar limit MC drawdown uses.
        limit = effective_dd_limit_usd(ruleset)
        pct1_max_dd = _num(st.get("pct1_max_dd"), float("inf"))
        pct5_max_dd = _num(st.get("pct5_max_dd"), float("inf"))
        median_max_dd = _num(st.get("median_max_dd"), float("inf"))

    def _fmt(v: float) -> str:
        return f"{v:.1f}%" if unit == "%" else f"${v:,.0f}"

    pct1_passes = limit > 0 and pct1_max_dd <= limit
    pct5_passes = limit > 0 and pct5_max_dd <= limit
    median_passes = limit > 0 and median_max_dd <= limit

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

    # Sensitivity is a PROFIT-FACTOR change fraction on both paths — the perturbation runner and
    # the optimizer-grid injection (they used to disagree; see stress_tester.run_sensitivity_task).
    sens_degradation = st.get("sensitivity_max_degradation")
    sens_solid = sens_degradation is not None and sens_degradation < 0.25
    sens_ok    = sens_degradation is not None and sens_degradation < 0.40
    # Ran but produced no measurable number (no tunable params, or an unusable baseline profit
    # factor). Same rule as the walk-forward above: treat it as not-run — neither credit nor
    # penalty. Without this an unassessable sensitivity silently BLOCKED A and B, punishing a
    # strategy for a measurement that never happened.
    sens_not_assessable = sensitivity is not None and sens_degradation is None
    sens_not_run = sensitivity is None or sens_not_assessable

    if sens_not_assessable:
        reasons.append("Parameter sensitivity ran but produced no measurable result")

    if wf_not_assessable:
        # Name the metric the path actually used: native WF rows carry per-window profit factor
        # (is_pf), the serial path carries Sharpe. Detect by the summary shape so the reason
        # doesn't claim "Sharpe" on a PF-based native run.
        pf_based = bool(walk_forward) and any("is_pf" in w for w in walk_forward)
        # A window can also be dropped for closing too few trades to support a Sharpe at all
        # (stress_tester._WF_MIN_TRADES_PER_WINDOW). That is the more common cause on a low-trade
        # strategy and has a different fix — fewer, longer windows — so it gets its own wording
        # rather than being reported as a flat in-sample period.
        thin = bool(walk_forward) and any(
            (w.get("oos_trades") is not None and w["oos_trades"] < 20)
            or (w.get("is_trades") is not None and w["is_trades"] < 20)
            for w in walk_forward
        )
        if thin and not pf_based:
            reasons.append(
                "Walk-forward ran but is not assessable — the windows closed too few trades each "
                "to support a Sharpe. Re-run with fewer walk-forward windows."
            )
        else:
            metric = "IS profit factor ≤ 0" if pf_based else "IS Sharpe ≤ 0"
            reasons.append(f"Walk-forward ran but IS→OOS degradation is not assessable ({metric})")

    # ── Nothing to judge the drawdown against → NOT GRADEABLE ───────────────────
    # Every grade from A to D is a statement about the Monte Carlo drawdown vs a limit. On the
    # percent basis there is ALWAYS one (ruin, at worst), so this only fires on the dollar basis
    # with no dollar limit — a fixed-size run against a no-limits ruleset, or a row written before
    # the percent columns existed.
    #
    # Before 2026-07-30 this case produced a silent, guaranteed-wrong answer instead of no answer:
    # the three `limit > 0` guards above all evaluated False, so A/B/C were unreachable and every
    # profitable strategy fell through to D — reported as "median drawdown breaches the limit" when
    # nothing was breached, because no limit exists. D was the CEILING for such a run, however good.
    #
    # Returning None is the honest result and NOT a failure state: the letter is omitted and the
    # reasons explain it, exactly as the walk-forward path treats an unassessable number.
    if limit <= 0:
        reasons.append(
            f"Not graded — '{ruleset.get('name') or ruleset.get('id')}' has no drawdown limit, "
            "and every grade is a statement about drawdown vs a limit"
        )
        reasons.append(
            f"Monte Carlo still ran: median simulation "
            f"{'makes' if median_final_pnl >= 0 else 'loses'} ${abs(median_final_pnl):,.0f}, "
            f"median drawdown {_fmt(median_max_dd)}, worst-1% drawdown {_fmt(pct1_max_dd)}"
        )
        if not wf_not_run:
            reasons.append(f"Walk-forward IS→OOS degradation {wf_degradation*100:.0f}%")
        if not sens_not_run:
            reasons.append(f"Parameter sensitivity worst case {sens_degradation*100:.0f}% drop")
        reasons.append(
            "Set the drawdown percent you are willing to accept on a ruleset and re-run — "
            "total ruin was tested as a default bar and cleared by strategies at 70% drawdown, "
            "so it is not used"
        )
        return (None, reasons)

    # ── A needs EVIDENCE, not just an absence of bad news ────────────────────────
    # A walk-forward that RAN and could not be assessed is not the same as a clean one. It stays
    # neutral for B and below (penalising a measurement that never happened would be as wrong as
    # crediting it), but it may not earn the top grade: an A off "the Monte Carlo passed and we
    # have no out-of-sample evidence" reads as proof the strategy held up, which is a claim nothing
    # here supports. Not-run is deliberately NOT capped — that path carries its own explicit
    # "grade may improve with full analysis" caveat and is how every auto-triggered MC-only test
    # runs, so capping it would relabel most of the existing library.
    a_blocked_no_evidence = wf_not_assessable

    # ── A: worst-1% passes, WF solid (or not run), sensitivity solid (or not run)
    if pct1_passes and not a_blocked_no_evidence and (wf_solid or wf_not_run) and (sens_solid or sens_not_run):
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
        if a_blocked_no_evidence and pct1_passes:
            reasons.append("Capped at B — the worst 1% passes too, but an A needs walk-forward "
                           "evidence and this run produced none")
        if not wf_not_run:
            reasons.append(f"Walk-forward degradation {wf_degradation*100:.0f}%")
        if not sens_not_run:
            reasons.append(f"Parameter sensitivity worst case {sens_degradation*100:.0f}% drop")
        if walk_forward is None or sens_not_run:
            reasons.append("Walk-forward / sensitivity not run — grade may improve with full analysis")
        return ("B", reasons)

    # ── C: median passes but worst-5% doesn't
    if median_passes:
        if not pct5_passes and limit > 0:
            reasons.append(f"Worst 5% breaches limit by {_fmt(pct5_max_dd - limit)}")
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
