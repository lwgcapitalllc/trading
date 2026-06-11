"""Shared performance-metric helpers — one canonical definition per metric."""

from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np

# Annualization factor: trading days per year.
TRADING_DAYS_PER_YEAR = 252

# Below this many trading days the daily Sharpe is statistically noisy — flag, don't suppress.
SHARPE_LOW_SAMPLE_DAYS = 10


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
