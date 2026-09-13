"""
Worthiness scoring — Tier 1/2/3 badge for a completed backtest run.

Tier 1 (STRESS_TEST): PF > 1.3, DD <= limit, trade_count >= 50
Tier 2 (OPTIMIZE):   PF in [0.8, 1.3], or DD in danger zone [0.7x, 1.0x], trade_count >= 30
Tier 3 (DISCARD):    PF < 0.8, DD > limit, or trade_count < 30

When several rulesets were evaluated the score is computed against the strictest one. Prop
rulesets win the pick; personal/demo rulesets are the fallback, because a forex run has no prop
firm and would otherwise never get a tier.

🔴 THE DRAWDOWN AND ITS LIMIT ARE COMPARED IN ONE UNIT, AND THE RUN DECIDES WHICH (2026-09-13).
Percent of the running peak when the run COMPOUNDED, dollars otherwise — the decision the stress
test's Monte Carlo makes for its own `dd_basis` (`stress_tester.drawdown_basis`), so a run's badge
and its stress-test grade are never judged in two different units. It compared dollars always
until then, and a compounding run's late dollar drops dwarf a limit written for its opening size:
run 952f14f8172e lost 46.84% from its peak against a 55% ruleset and scored DISCARD, because
$1,051,553 is past $5,500.
"""

from __future__ import annotations

from typing import Optional

TIER_1 = "TIER_1_STRESS_TEST"
TIER_2 = "TIER_2_OPTIMIZE"
TIER_3 = "TIER_3_DISCARD"

DD_PERCENT = "percent"
DD_DOLLARS = "dollars"


def compute_worthiness(
    profit_factor: Optional[float],
    max_drawdown: Optional[float],
    trade_count: Optional[int],
    dd_limit: float,
) -> tuple[str, Optional[str]]:
    """Returns (tier, reason). reason is None for Tier 1 and Tier 2 unless there's a notable cause.

    ⚠ `max_drawdown` and `dd_limit` must be in the SAME unit — both dollars or both percent.
    `score_run_after_evals` is what picks the unit.
    """
    pf = profit_factor or 0.0
    dd = abs(max_drawdown or 0.0)
    tc = trade_count or 0

    if tc == 0:
        return TIER_3, "no_trades"
    if tc < 30:
        return TIER_3, "insufficient_signal"
    if dd > dd_limit:
        return TIER_3, "drawdown_breach"
    if pf < 0.8:
        return TIER_3, "low_profit_factor"

    # DD in danger zone (0.7x–1.0x of limit) → Tier 2 even if PF is strong
    in_danger_zone = dd >= 0.7 * dd_limit

    if pf > 1.3 and not in_danger_zone and tc >= 50:
        return TIER_1, None

    return TIER_2, None


def _limit_in(ruleset: dict, basis: str) -> Optional[float]:
    """The ruleset's drawdown limit in `basis`'s unit, or None when it states none there.

    `metrics` owns both translations: a personal row states its percent and derives dollars from
    its account size; a prop row states dollars and derives the percent the same way.
    """
    from services.metrics import effective_dd_limit_pct, effective_dd_limit_usd

    if basis == DD_PERCENT:
        return effective_dd_limit_pct(ruleset)
    usd = effective_dd_limit_usd(ruleset)
    return usd if usd > 0 else None


def score_run_after_evals(
    run_id: str,
    ruleset_ids: list[str],
    profit_factor: Optional[float],
    max_drawdown: Optional[float],
    trade_count: Optional[int],
    *,
    equity_curve: Optional[list[dict]],
) -> Optional[tuple[str, Optional[str], str]]:
    """Find the strictest evaluated ruleset, compute the tier, return (tier, reason, ruleset_id).
    Returns None when no ruleset states a usable drawdown limit in the run's unit.

    `max_drawdown` is the run's deepest DOLLAR drop, used when the run is judged in dollars. On a
    compounding run the percent is taken off `equity_curve` instead (peak-relative, the figure the
    runs list shows). ⚠ `equity_curve` is keyword-only with NO default: `None` is a real answer —
    a native optimizer combo carries KPIs only and is judged in dollars — so every caller has to
    say which it is rather than inherit the unit by forgetting the argument.

    "Strictest" is the smallest limit IN THAT UNIT, which can be a different ruleset: $2,000 on
    $50,000 (4%) is the smaller dollar limit and the looser percent one beside $3,000 on $100,000.
    """
    from services import lab_db, stress_tester
    from services.metrics import max_drawdown_pct

    basis = stress_tester.drawdown_basis(equity_curve)
    if basis == DD_PERCENT:
        dd = max_drawdown_pct(equity_curve)
        if dd is None:  # unreachable while the basis is percent; never score a guess
            return None
    else:
        dd = abs(max_drawdown or 0.0)

    prop: list[tuple[float, str]] = []
    personal: list[tuple[float, str]] = []
    for rid in ruleset_ids:
        ruleset = lab_db.get_ruleset(rid)
        if ruleset is None:
            continue
        limit = _limit_in(ruleset, basis)
        if not limit or limit <= 0:
            continue
        pool = personal if ruleset.get("ruleset_type") in ("personal", "demo") else prop
        pool.append((limit, ruleset["id"]))

    # Prop limits are the binding constraint when present; fall back to personal otherwise.
    candidates = prop or personal
    if not candidates:
        return None
    limit, ruleset_id = min(candidates, key=lambda c: c[0])

    tier, reason = compute_worthiness(profit_factor, dd, trade_count, limit)
    return tier, reason, ruleset_id
