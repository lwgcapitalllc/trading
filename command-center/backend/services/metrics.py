"""Shared performance-metric helpers — one canonical definition per metric."""

from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np

# Annualization factor: trading days per year.
TRADING_DAYS_PER_YEAR = 252

# Below this many trading days the daily Sharpe is statistically noisy — flag, don't suppress.
SHARPE_LOW_SAMPLE_DAYS = 10


def effective_dd_limit_usd(ruleset: Optional[dict]) -> float:
    """
    Dollar drawdown limit a Monte Carlo / objective check should compare against.
    Returns 0.0 when the ruleset has no usable limit — callers must skip the check.

    Personal/demo rulesets have NO trailing EOD rule (max_loss_eod = 0 is a sentinel,
    never a $0 limit). Their drawdown rule is max_drawdown_from_peak_pct of
    account_size — which is exactly what MC max-drawdown measures, so it translates
    directly to dollars. The guard keys on ruleset_type, not the sentinel value, so
    it holds even if the sentinel ever changes.
    """
    if not ruleset:
        return 0.0
    if ruleset.get("ruleset_type") in ("personal", "demo"):
        pct = ruleset.get("max_drawdown_from_peak_pct")
        size = ruleset.get("account_size")
        if pct and size:
            return float(size) * float(pct) / 100.0
        return 0.0
    return float(ruleset.get("max_loss_eod") or ruleset.get("daily_loss_cap") or 0)


def daily_sharpe_from_values(daily_values: list[float]) -> float:
    """
    Annualized Sharpe from a list of per-day P&L values.

    Return series = daily P&L. Dividing each day by a constant starting capital would
    cancel in the mean/std ratio, so Sharpe is capital-independent — daily P&L is used
    directly. Sample std (ddof=1), annualized by sqrt(252). Returns 0.0 when there are
    fewer than two days or zero variance.
    """
    if not daily_values or len(daily_values) < 2:
        return 0.0
    arr = np.asarray(daily_values, dtype=np.float64)
    sd = arr.std(ddof=1)
    if sd == 0:
        return 0.0
    return float((arr.mean() / sd) * np.sqrt(TRADING_DAYS_PER_YEAR))


def daily_sharpe(daily_pnl: list[dict]) -> float:
    """Annualized daily Sharpe from a daily_pnl list of {'date', 'pnl'} dicts."""
    return daily_sharpe_from_values([d.get("pnl", 0.0) or 0.0 for d in daily_pnl])


def apply_canonical_sharpe(kpis: dict, daily_pnl: list[dict]) -> dict:
    """
    Replace a run's Sharpe with the canonical daily-√252 value, preserving the platform's own
    value as platform_sharpe and flagging the low-sample case. Mutates and returns kpis.

    One definition for every run path. ONLY call where daily_pnl is genuinely available —
    never on paths that lack it (e.g. native optimizer combos), where daily_sharpe([]) would
    overwrite the platform Sharpe with 0.0.
    """
    kpis["platform_sharpe"]   = kpis.get("sharpe")
    kpis["sharpe"]            = daily_sharpe(daily_pnl)
    kpis["sharpe_low_sample"] = len(daily_pnl) < SHARPE_LOW_SAMPLE_DAYS
    return kpis


def profit_concentration_pct(daily_pnl: list[dict]) -> Optional[float]:
    """
    Share of total gross profit earned in the most profitable calendar quarter.

    Mirrors the frontend computeProfitConcentration exactly: split the date span (first→last)
    into 4 equal slices, gross profit = sum of positive daily P&L, concentration = the largest
    quarter's positive P&L / gross × 100. High = the edge is clustered in one period.

    Returns None when there's no dated data, a zero span, or no positive profit to concentrate
    (e.g. a net-negative run with no winning days) — never fabricated.
    """
    dated = [d for d in daily_pnl if d.get("date")]
    if len(dated) < 2:
        return None
    try:
        t0 = date.fromisoformat(str(dated[0]["date"])[:10])
        t1 = date.fromisoformat(str(dated[-1]["date"])[:10])
    except ValueError:
        return None
    span = (t1 - t0).days
    if span <= 0:
        return None

    quarters = [0.0, 0.0, 0.0, 0.0]
    gross = 0.0
    for d in dated:
        pnl = d.get("pnl", 0.0) or 0.0
        if pnl <= 0:
            continue
        try:
            day = date.fromisoformat(str(d["date"])[:10])
        except ValueError:
            continue
        gross += pnl
        idx = int(((day - t0).days / span) * 4)
        idx = max(0, min(3, idx))
        quarters[idx] += pnl

    if gross <= 0:
        return None
    return round((max(quarters) / gross) * 100, 2)


# Bucket for a day or trade that can't be attributed to a classified regime.
_REGIME_UNKNOWN = "UNKNOWN"


def compute_regime_breakdown(
    equity_curve: list[dict],
    daily_pnl: list[dict],
) -> list[dict]:
    """
    Per-regime performance breakdown — the canonical, runner-independent implementation.

    Day-level columns (days, net_pnl, worst_day) come from the regime-tagged daily series,
    which is the source of truth: every day carries a 'regime_tag', so summing per regime
    reproduces the run totals exactly — no inflation. Trade-level columns (trades, win_rate,
    profit_factor) are attributed from each trade's own realized 'profit', joined to the
    regime of its day — the same method the optimizer uses (optimization_runner
    ._regime_filtered_score).

    Per-trade P&L is NEVER derived from equity differences: that double-counts the starting
    balance into the first "trade" and dumps everything into UNKNOWN on a date-format
    mismatch (the original frontend bug). Dates are normalized to YYYY-MM-DD so a timestamped
    equity point still joins to a daily date.

    Each row: {regime, days, trades, net_pnl, win_rate, profit_factor, worst_day}. Sorted by
    days desc (then trades), UNKNOWN pushed last. Empty when there's no daily data.
    """
    if not daily_pnl:
        return []

    date_to_regime: dict[str, str] = {}
    day_agg: dict[str, dict] = {}
    for d in daily_pnl:
        regime = d.get("regime_tag") or _REGIME_UNKNOWN
        day = str(d.get("date") or "")[:10]
        if day:
            date_to_regime[day] = regime
        pnl = float(d.get("pnl", 0.0) or 0.0)
        a = day_agg.setdefault(regime, {"days": 0, "net_pnl": 0.0, "worst_day": None})
        a["days"] += 1
        a["net_pnl"] += pnl
        a["worst_day"] = pnl if a["worst_day"] is None else min(a["worst_day"], pnl)

    trade_agg: dict[str, dict] = {}
    for pt in equity_curve:
        # A real trade carries a direction (Long/Short). The MT5 equity_curve also includes
        # non-trade equity snapshots (no direction) — skip those so the per-regime trade counts
        # sum to trade_count, not the snapshot count. Mirrors the frontend DirectionBreakdown.
        if not pt.get("direction"):
            continue
        profit = pt.get("profit")
        if profit is None:
            continue
        profit = float(profit)
        day = str(pt.get("date") or "")[:10]
        regime = date_to_regime.get(day, _REGIME_UNKNOWN) if day else _REGIME_UNKNOWN
        t = trade_agg.setdefault(
            regime, {"trades": 0, "net_pnl": 0.0, "wins": 0, "gross_win": 0.0, "gross_loss": 0.0}
        )
        t["trades"] += 1
        t["net_pnl"] += profit
        if profit > 0:
            t["wins"] += 1
            t["gross_win"] += profit
        elif profit < 0:
            t["gross_loss"] += abs(profit)

    rows: list[dict] = []
    for regime in set(day_agg) | set(trade_agg):
        day = day_agg.get(regime)
        t = trade_agg.get(regime)
        trades = t["trades"] if t else 0
        # Prefer the regime-intrinsic daily sum; fall back to the trade sum for a
        # trade-only bucket (a trade whose day never made it into daily_pnl).
        net_pnl = day["net_pnl"] if day else (t["net_pnl"] if t else 0.0)
        rows.append({
            "regime": regime,
            "days": day["days"] if day else 0,
            "trades": trades,
            "net_pnl": round(net_pnl, 2),
            "win_rate": (t["wins"] / trades) if (t and trades) else None,
            "profit_factor": (t["gross_win"] / t["gross_loss"]) if (t and t["gross_loss"] > 0) else None,
            "worst_day": round(day["worst_day"], 2) if (day and day["worst_day"] is not None) else None,
        })

    rows.sort(key=lambda r: (-r["days"], -r["trades"]))
    unknown_idx = next((i for i, r in enumerate(rows) if r["regime"] == _REGIME_UNKNOWN), None)
    if unknown_idx is not None and unknown_idx != len(rows) - 1:
        rows.append(rows.pop(unknown_idx))
    return rows
