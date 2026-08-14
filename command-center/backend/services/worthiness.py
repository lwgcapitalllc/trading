"""
Worthiness scoring — Tier 1/2/3 badge for a completed backtest run.

Tier 1 (STRESS_TEST): PF > 1.3, DD <= limit, trade_count >= 50
Tier 2 (OPTIMIZE):   PF in [0.8, 1.3], or DD in danger zone [0.7x, 1.0x], trade_count >= 30
Tier 3 (DISCARD):    PF < 0.8, DD > limit, or trade_count < 30

When multiple firm evals exist, score is computed against the strictest firm
(smallest max_loss_eod). When the run was evaluated against personal/demo rulesets
only (e.g. a forex run — no prop firm covers forex), score against the personal
drawdown limit instead (account_size × max_drawdown_from_peak_pct).
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
    Returns None if no ruleset yields a usable dollar drawdown limit.

    Prop rulesets win the strictest pick (smallest trailing max-loss) and take precedence.
    Personal/demo rows carry max_loss_eod = 0 (sentinel: no trailing EOD rule), so they're
    scored against their drawdown-from-peak limit instead (account_size × pct, via
    metrics.effective_dd_limit_usd). This is the only limit a forex run has — no prop firm
    covers forex — so without it forex runs would never get a worthiness tier.
    """
    from services import lab_db
    from services.metrics import effective_dd_limit_usd

    prop_strictest = None  # smallest max_loss_eod among prop rulesets
    personal_strictest = None  # (limit_usd, ruleset) among personal/demo rulesets
    for rid in ruleset_ids:
        ruleset = lab_db.get_ruleset(rid)
        if ruleset is None:
            continue
        if ruleset.get("ruleset_type") in ("personal", "demo"):
            limit = effective_dd_limit_usd(ruleset)
            if limit > 0 and (personal_strictest is None or limit < personal_strictest[0]):
                personal_strictest = (limit, ruleset)
        elif prop_strictest is None or ruleset["max_loss_eod"] < prop_strictest["max_loss_eod"]:
            prop_strictest = ruleset

    # Prop limits are the binding constraint when present; fall back to personal otherwise.
    if prop_strictest is not None:
        limit_usd, ruleset_id = prop_strictest["max_loss_eod"], prop_strictest["id"]
    elif personal_strictest is not None:
        limit_usd, ruleset_id = personal_strictest[0], personal_strictest[1]["id"]
    else:
        return None

    tier, reason = compute_worthiness(profit_factor, max_drawdown, trade_count, limit_usd)
    return tier, reason, ruleset_id
