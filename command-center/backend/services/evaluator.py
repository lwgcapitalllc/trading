"""
Post-run evaluation logic.
Branches on ruleset_type: prop_eval, prop_funded, personal, demo.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from services import lab_db


def _count_drawdown_breaches_equity(equity_curve: list[dict], max_loss: float) -> int:
    if not equity_curve:
        return 0
    peak = equity_curve[0]["equity"]
    breaches = 0
    for pt in equity_curve:
        eq = pt["equity"]
        if eq > peak:
            peak = eq
        if (peak - eq) > max_loss:
            breaches += 1
    return breaches


def _count_drawdown_breaches_daily(daily_pnl: list[dict], max_loss: float) -> int:
    if not daily_pnl:
        return 0
    cumsum = 0.0
    peak = 0.0
    breaches = 0
    for day in daily_pnl:
        cumsum += day.get("pnl", 0.0)
        if cumsum > peak:
            peak = cumsum
        if (peak - cumsum) > max_loss:
            breaches += 1
    return breaches


def _simulated_eval_days(daily_pnl: list[dict]) -> int:
    return len([d for d in daily_pnl if d.get("pnl", 0.0) != 0.0])


def _check_weekly_cap(daily_pnl: list[dict], weekly_loss_cap: float) -> bool:
    """True if no calendar week's net P&L is a loss exceeding weekly_loss_cap."""
    weekly: dict[str, float] = {}
    for day in daily_pnl:
        date_str = day.get("date", "")
        pnl = day.get("pnl", 0.0)
        if not date_str:
            continue
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
            week_key = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
        except ValueError:
            continue
        weekly[week_key] = weekly.get(week_key, 0.0) + pnl
    return all(v >= -weekly_loss_cap for v in weekly.values())


def _notes_prop(
    ruleset: dict,
    drawdown_pass: bool,
    target_pass: bool,
    consistency_pass: Optional[bool],
    largest_day_share: Optional[float],
    max_drawdown: float,
    net_pnl: float,
) -> str:
    parts = []
    dd_limit = ruleset["max_loss_eod"]
    if drawdown_pass:
        parts.append(f"Drawdown peaked at ${max_drawdown:,.0f} (under ${dd_limit:,} limit)")
    else:
        parts.append(f"Drawdown ${max_drawdown:,.0f} BREACHED ${dd_limit:,} limit")

    if ruleset["ruleset_type"] == "prop_funded":
        return "; ".join(parts)

    pt = ruleset["profit_target"]
    if pt > 0:
        if target_pass:
            parts.append(f"Hit ${pt:,} profit target (net ${net_pnl:,.0f})")
        else:
            parts.append(f"Did not reach ${pt:,} profit target (net ${net_pnl:,.0f})")

    if consistency_pass is not None and largest_day_share is not None:
        limit = ruleset["consistency_pct"]
        tag = "under" if consistency_pass else "EXCEEDS"
        parts.append(
            f"Largest single day was {largest_day_share:.1f}% of total profit "
            f"({tag} {limit:.0f}% limit)"
        )
    return "; ".join(parts)


def evaluate_run(
    run_id: str,
    ruleset_ids: list[str],
    kpis: dict,
    equity_curve: list[dict],
    daily_pnl: list[dict],
) -> list[dict]:
    """
    Evaluate a completed backtest run against the given rulesets.
    Inserts rows into `evaluations` table (INSERT OR REPLACE).
    Returns list of evaluation dicts.
    """
    results = []

    net_pnl = kpis.get("net_pnl") or 0.0
    max_drawdown = abs(kpis.get("max_drawdown") or 0.0)

    for rid in ruleset_ids:
        ruleset = lab_db.get_ruleset(rid)
        if ruleset is None:
            continue

        rtype = ruleset.get("ruleset_type", "prop_eval")
        dd_limit = ruleset.get("daily_loss_cap") or ruleset["max_loss_eod"]

        # ── Drawdown check (all types) ─────────────────────────────────────
        drawdown_pass = max_drawdown <= dd_limit

        if equity_curve:
            breach_count = _count_drawdown_breaches_equity(equity_curve, dd_limit)
        else:
            breach_count = _count_drawdown_breaches_daily(daily_pnl, dd_limit)

        # ── Branch on ruleset_type ─────────────────────────────────────────
        if rtype == "prop_funded":
            target_pass = True
            consistency_pass = None
            largest_day_share = None
            verdict = "PASS" if drawdown_pass else "DISCARD"
            notes = _notes_prop(ruleset, drawdown_pass, True, None, None, max_drawdown, net_pnl)

        elif rtype == "prop_eval":
            if ruleset["profit_target"] == 0:
                target_pass = True
            else:
                target_pass = net_pnl >= ruleset["profit_target"]

            consistency_pass = None
            largest_day_share = None
            if (
                ruleset.get("consistency_pct") is not None
                and net_pnl > 0
            ):
                pos_days = [d.get("pnl", 0.0) for d in daily_pnl if d.get("pnl", 0.0) > 0]
                biggest_day = max(pos_days, default=0.0)
                largest_day_share = biggest_day / net_pnl * 100
                consistency_pass = largest_day_share <= ruleset["consistency_pct"]

            if not drawdown_pass:
                verdict = "DISCARD"
            elif not target_pass:
                verdict = "WARN"
            elif consistency_pass is False:
                verdict = "WARN"
            else:
                verdict = "PASS"

            notes = _notes_prop(ruleset, drawdown_pass, target_pass, consistency_pass,
                                largest_day_share, max_drawdown, net_pnl)

        elif rtype == "personal":
            target_pass = True
            consistency_pass = None
            largest_day_share = None
            weekly_ok = True
            if ruleset.get("weekly_loss_cap") is not None:
                weekly_ok = _check_weekly_cap(daily_pnl, ruleset["weekly_loss_cap"])

            if not drawdown_pass:
                verdict = "DISCARD"
            elif not weekly_ok:
                verdict = "WARN"
            else:
                verdict = "PASS"

            wcap = ruleset.get("weekly_loss_cap")
            notes_parts = []
            if drawdown_pass:
                notes_parts.append(f"Daily cap ${dd_limit:,} maintained")
            else:
                notes_parts.append(f"Daily cap ${dd_limit:,} BREACHED (${max_drawdown:,.0f})")
            if wcap is not None:
                tag = "maintained" if weekly_ok else "BREACHED"
                notes_parts.append(f"Weekly cap ${wcap:,} {tag}")
            notes = "; ".join(notes_parts)

        elif rtype == "demo":
            target_pass = True
            consistency_pass = None
            largest_day_share = None
            verdict = "PASS" if net_pnl > 0 else "WARN"
            notes = f"Demo — net P&L ${net_pnl:,.0f} ({'positive' if net_pnl > 0 else 'negative'})"

        else:
            # Unknown type — fall back to prop_eval logic
            target_pass = net_pnl >= ruleset.get("profit_target", 0)
            consistency_pass = None
            largest_day_share = None
            verdict = "DISCARD" if not drawdown_pass else ("PASS" if target_pass else "WARN")
            notes = f"Unknown ruleset_type '{rtype}'"

        sim_days = _simulated_eval_days(daily_pnl) if target_pass else None

        eval_data = {
            "eval_id": uuid.uuid4().hex[:12],
            "run_id": run_id,
            "ruleset_id": rid,
            "verdict": verdict,
            "drawdown_pass": drawdown_pass,
            "target_pass": target_pass,
            "consistency_pass": consistency_pass,
            "simulated_eval_days": sim_days,
            "breach_count": breach_count,
            "largest_day_share_pct": largest_day_share,
            "notes": notes,
        }
        lab_db.insert_evaluation(eval_data)
        results.append(eval_data)

    return results
