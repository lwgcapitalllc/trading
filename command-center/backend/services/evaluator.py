"""
Post-run evaluation logic — §7 of the M1 spec.
Tier-aware: funded firms only need drawdown_pass; eval firms run all three checks.
"""

from __future__ import annotations

import uuid
from typing import Optional

from services import lab_db


def _count_drawdown_breaches_equity(equity_curve: list[dict], max_loss_eod: float) -> int:
    """Count equity observations where drawdown from running peak exceeds max_loss_eod."""
    if not equity_curve:
        return 0
    peak = equity_curve[0]["equity"]
    breaches = 0
    for pt in equity_curve:
        eq = pt["equity"]
        if eq > peak:
            peak = eq
        if (peak - eq) > max_loss_eod:
            breaches += 1
    return breaches


def _count_drawdown_breaches_daily(daily_pnl: list[dict], max_loss_eod: float) -> int:
    """Fallback: use daily cumsum when equity_curve is empty."""
    if not daily_pnl:
        return 0
    cumsum = 0.0
    peak = 0.0
    breaches = 0
    for day in daily_pnl:
        cumsum += day.get("pnl", 0.0)
        if cumsum > peak:
            peak = cumsum
        if (peak - cumsum) > max_loss_eod:
            breaches += 1
    return breaches


def _simulated_eval_days(daily_pnl: list[dict]) -> int:
    return len([d for d in daily_pnl if d.get("pnl", 0.0) != 0.0])


def _notes(
    firm: dict,
    drawdown_pass: bool,
    target_pass: bool,
    consistency_pass: Optional[bool],
    largest_day_share: Optional[float],
    max_drawdown: float,
    net_pnl: float,
) -> str:
    parts = []
    dd_limit = firm["max_loss_eod"]
    if drawdown_pass:
        parts.append(f"Drawdown peaked at ${max_drawdown:,.0f} (under ${dd_limit:,} limit)")
    else:
        parts.append(f"Drawdown ${max_drawdown:,.0f} BREACHED ${dd_limit:,} limit")

    if firm["account_tier"] == "funded":
        return "; ".join(parts)

    pt = firm["profit_target"]
    if pt > 0:
        if target_pass:
            parts.append(f"Hit ${pt:,} profit target (net ${net_pnl:,.0f})")
        else:
            parts.append(f"Did not reach ${pt:,} profit target (net ${net_pnl:,.0f})")

    if consistency_pass is not None and largest_day_share is not None:
        limit = firm["consistency_pct"]
        tag = "under" if consistency_pass else "EXCEEDS"
        parts.append(
            f"Largest single day was {largest_day_share:.1f}% of total profit "
            f"({tag} {limit:.0f}% limit)"
        )
    return "; ".join(parts)


def evaluate_run(
    run_id: str,
    firm_ids: list[str],
    kpis: dict,
    equity_curve: list[dict],
    daily_pnl: list[dict],
) -> list[dict]:
    """
    Evaluate a completed backtest run against the given firms.
    Inserts rows into `evaluations` table (INSERT OR REPLACE).
    Returns list of evaluation dicts.
    """
    results = []

    net_pnl = kpis.get("net_pnl") or 0.0
    max_drawdown = kpis.get("max_drawdown") or 0.0

    for firm_id in firm_ids:
        firm = lab_db.get_firm(firm_id)
        if firm is None:
            continue

        # 1. Drawdown — both eval and funded
        drawdown_pass = max_drawdown <= firm["max_loss_eod"]

        # 2. Target — funded always True (profit_target == 0 signals "no target")
        if firm["account_tier"] == "funded" or firm["profit_target"] == 0:
            target_pass = True
        else:
            target_pass = net_pnl >= firm["profit_target"]

        # 3. Consistency — funded: skip entirely (remains None)
        consistency_pass: Optional[bool] = None
        largest_day_share: Optional[float] = None
        if (
            firm["account_tier"] != "funded"
            and firm.get("consistency_pct") is not None
            and net_pnl > 0
        ):
            pos_days = [d.get("pnl", 0.0) for d in daily_pnl if d.get("pnl", 0.0) > 0]
            biggest_day = max(pos_days, default=0.0)
            share = biggest_day / net_pnl * 100
            largest_day_share = share
            consistency_pass = share <= firm["consistency_pct"]

        # 4. Breach count — prefer equity_curve, fallback to daily_pnl cumsum
        if equity_curve:
            breach_count = _count_drawdown_breaches_equity(equity_curve, firm["max_loss_eod"])
        else:
            breach_count = _count_drawdown_breaches_daily(daily_pnl, firm["max_loss_eod"])

        # 5. Verdict — tier-aware
        if not drawdown_pass:
            verdict = "DISCARD"
        elif firm["account_tier"] == "funded":
            # Funded: surviving drawdown is sufficient — no WARN tier
            verdict = "PASS"
        elif not target_pass:
            verdict = "WARN"
        elif consistency_pass is False:
            verdict = "WARN"
        else:
            verdict = "PASS"

        sim_days = _simulated_eval_days(daily_pnl) if target_pass else None

        eval_data = {
            "eval_id": uuid.uuid4().hex[:12],
            "run_id": run_id,
            "firm_id": firm_id,
            "verdict": verdict,
            "drawdown_pass": drawdown_pass,
            "target_pass": target_pass,
            "consistency_pass": consistency_pass,
            "simulated_eval_days": sim_days,
            "breach_count": breach_count,
            "largest_day_share_pct": largest_day_share,
            "notes": _notes(
                firm, drawdown_pass, target_pass, consistency_pass,
                largest_day_share, max_drawdown, net_pnl,
            ),
        }
        lab_db.insert_evaluation(eval_data)
        results.append(eval_data)

    return results
