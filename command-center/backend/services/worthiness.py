"""
Worthiness scoring — Tier 1/2/3 badge for a completed backtest run.

Tier 1 (STRESS_TEST): PF > 1.3, DD <= limit, trade_count >= 50
Tier 2 (OPTIMIZE):   PF in [0.8, 1.3], or DD in danger zone [0.7x, 1.0x], trade_count >= 30
Tier 3 (DISCARD):    PF < 0.8, DD > limit, or trade_count < 30

When multiple firm evals exist, score is computed against the strictest firm
(smallest max_loss_eod).
"""

from __future__ import annotations

from typing import Optional

TIER_1 = "TIER_1_STRESS_TEST"
TIER_2 = "TIER_2_OPTIMIZE"
TIER_3 = "TIER_3_DISCARD"


def compute_worthiness(
    profit_factor: Optional[float],
    max_drawdown: Optional[float],
    trade_count: Optional[int],
    firm_max_loss_eod: float,
) -> tuple[str, Optional[str]]:
    """Returns (tier, reason). reason is None for Tier 1 and Tier 2 unless there's a notable cause."""
    pf = profit_factor or 0.0
    dd = abs(max_drawdown or 0.0)
    tc = trade_count or 0

    if tc == 0:
        return TIER_3, "no_trades"
    if tc < 30:
        return TIER_3, "insufficient_signal"
    if dd > firm_max_loss_eod:
        return TIER_3, "drawdown_breach"
    if pf < 0.8:
        return TIER_3, "low_profit_factor"

    # DD in danger zone (0.7x–1.0x of limit) → Tier 2 even if PF is strong
    in_danger_zone = dd >= 0.7 * firm_max_loss_eod

    if pf > 1.3 and not in_danger_zone and tc >= 50:
        return TIER_1, None

    return TIER_2, None


def score_run_after_evals(
    run_id: str,
    ruleset_ids: list[str],
    profit_factor: Optional[float],
    max_drawdown: Optional[float],
    trade_count: Optional[int],
) -> Optional[tuple[str, Optional[str], str]]:
    """
    Find the strictest evaluated ruleset, compute tier, return (tier, reason, ruleset_id).
    Returns None if no rulesets available.
    """
    from services import lab_db

    if not ruleset_ids:
        return None

    strictest = None
    for rid in ruleset_ids:
        ruleset = lab_db.get_ruleset(rid)
        if ruleset is None:
            continue
        # Personal/demo rows carry max_loss_eod = 0 (sentinel: no trailing EOD rule) and
        # must never win the strictest pick — worthiness is scored against prop limits
        # only. A personal-only run gets no tier (strictest stays None below).
        if ruleset.get("ruleset_type") in ("personal", "demo"):
            continue
        if strictest is None or ruleset["max_loss_eod"] < strictest["max_loss_eod"]:
            strictest = ruleset

    if strictest is None:
        return None

    tier, reason = compute_worthiness(profit_factor, max_drawdown, trade_count, strictest["max_loss_eod"])
    return tier, reason, strictest["id"]
