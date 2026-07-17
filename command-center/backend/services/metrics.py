"""Shared performance-metric helpers — one canonical definition per metric."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np

# Annualization factor: trading days per year.
TRADING_DAYS_PER_YEAR = 252

# Below this many ACTIVE trading days (days that actually closed a trade) the daily Sharpe is
# statistically noisy — flag, don't suppress. This MUST count active days, not the length of the
# Sharpe input series: that series is zero-filled (see zero_filled_daily_values), so measuring it
# would read a 3-trade year as ~250 well-sampled days and the flag would never fire.
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

    Takes bare values, so it CANNOT zero-fill (no dates). The caller owns that: pass a series
    that already represents every day in the population. `daily_sharpe()` below is the dated
    entry point and is what run-completion paths want. This one stays for callers whose day
    population is genuinely sparse by definition (e.g. the optimizer's regime-filtered scoring,
    where non-matching-regime days are NOT part of the population and must not become zeros).
    """
    if not daily_values or len(daily_values) < 2:
        return 0.0
    arr = np.asarray(daily_values, dtype=np.float64)
    sd = arr.std(ddof=1)
    if sd == 0:
        return 0.0
    return float((arr.mean() / sd) * np.sqrt(TRADING_DAYS_PER_YEAR))


def zero_filled_daily_values(daily_pnl: list[dict]) -> list[float]:
    """
    Per-day P&L for EVERY weekday spanned by `daily_pnl`, flat days included as 0.0.

    `build_daily_pnl` (and the NT8/MT5 parsers) emit only days that closed a trade — flat days
    are absent by design, because the trailing-drawdown engine walks the days that exist. That
    series is wrong for Sharpe: a strategy trading 22 days out of a 225-day span would be scored
    as if every day earned the active-day mean, then annualized by sqrt(252). Measured on a real
    run that read 7.80 against a true ~2.2 (and TradingView's own monthly Sharpe, annualized,
    agreed at ~2.0). A flat day is a real observation and belongs in the series.

    Weekends are skipped to match TRADING_DAYS_PER_YEAR=252 — but any date PRESENT in the input
    is always kept, even on a weekend, so a Sunday-open forex fill is never silently dropped.
    """
    dated: dict[str, float] = {}
    for d in daily_pnl:
        key = d.get("date")
        if not key:
            continue
        dated[key] = dated.get(key, 0.0) + (d.get("pnl", 0.0) or 0.0)
    if len(dated) < 2:
        return list(dated.values())

    days = sorted(date.fromisoformat(k) for k in dated)
    out: list[float] = []
    cur, last = days[0], days[-1]
    while cur <= last:
        key = cur.isoformat()
        if key in dated or cur.weekday() < 5:
            out.append(dated.get(key, 0.0))
        cur += timedelta(days=1)
    return out


def active_day_count(daily_pnl: list[dict]) -> int:
    """Days that actually closed a trade — the real sample size behind a Sharpe.

    Counts non-zero days, so it reads the same whether it's handed a raw (sparse) daily_pnl or an
    already-zero-filled one. A day netting exactly $0.00 is treated as flat; with commissions that
    is vanishingly rare, and undercounting by one is harmless for a >=10 threshold.
    """
    return sum(1 for d in daily_pnl if (d.get("pnl", 0.0) or 0.0) != 0.0)


def daily_sharpe(daily_pnl: list[dict]) -> float:
    """Annualized daily Sharpe from a daily_pnl list of {'date', 'pnl'} dicts.

    Zero-fills flat days first — see zero_filled_daily_values for why.
    """
    return daily_sharpe_from_values(zero_filled_daily_values(daily_pnl))


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
    kpis["sharpe_low_sample"] = active_day_count(daily_pnl) < SHARPE_LOW_SAMPLE_DAYS
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
    trade_count: Optional[int] = None,
) -> list[dict]:
    """
    Per-regime performance breakdown — the canonical, runner-independent implementation.

    Day-level columns (days, net_pnl, worst_day) come from the regime-tagged daily series,
    which is the source of truth: every day carries a 'regime_tag', so summing per regime
    reproduces the run totals exactly — no inflation.

    Trade-level columns (trades, win_rate, profit_factor) are attributed from each trade's own
    realized 'profit', joined to the regime of its day. Two MT5 wrinkles handled here:
      * MT5 emits TWO deal-rows per trade — an entry (profit 0.0) and an exit (the realized
        P&L), both carrying a direction. So the raw direction-bearing point count is ~2x the
        real trade count. We rescale each regime's count to the authoritative `trade_count`
        (points-per-trade is uniform per runner — 2 for MT5, 1 for NT8 — so the scaling is
        exact). win_rate then divides real wins (entries are profit 0, never a win) by the
        rescaled count. profit_factor is unaffected (entries contribute 0 to gross win/loss).
      * Per-trade P&L is NEVER derived from equity differences (the original frontend bug).
    Dates are normalized to YYYY-MM-DD so a timestamped equity point still joins to a daily date.

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
        # A trade carries a direction (Long/Short); balance/equity-only rows (no direction) are
        # skipped. MT5 entry deals are kept here (they have a direction + profit 0.0) and the
        # raw count is rescaled to trade_count below.
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

    # Rescale raw direction-bearing point counts to the real trade count (MT5 doubles via
    # entry+exit deals). Exact when points-per-trade is uniform; 1.0 (no-op) for NT8 or when
    # trade_count is unknown.
    total_pts = sum(t["trades"] for t in trade_agg.values())
    scale = (trade_count / total_pts) if (trade_count and total_pts) else 1.0

    rows: list[dict] = []
    for regime in set(day_agg) | set(trade_agg):
        day = day_agg.get(regime)
        t = trade_agg.get(regime)
        trades = round(t["trades"] * scale) if t else 0
        # Prefer the regime-intrinsic daily sum; fall back to the trade sum for a
        # trade-only bucket (a trade whose day never made it into daily_pnl).
        net_pnl = day["net_pnl"] if day else (t["net_pnl"] if t else 0.0)
        rows.append({
            "regime": regime,
            "days": day["days"] if day else 0,
            "trades": trades,
            "net_pnl": round(net_pnl, 2),
            # win_rate = real wins (entries are profit 0, never counted) over the rescaled count.
            "win_rate": (t["wins"] / trades) if (t and trades) else None,
            "profit_factor": (t["gross_win"] / t["gross_loss"]) if (t and t["gross_loss"] > 0) else None,
            "worst_day": round(day["worst_day"], 2) if (day and day["worst_day"] is not None) else None,
        })

    rows.sort(key=lambda r: (-r["days"], -r["trades"]))
    unknown_idx = next((i for i, r in enumerate(rows) if r["regime"] == _REGIME_UNKNOWN), None)
    if unknown_idx is not None and unknown_idx != len(rows) - 1:
        rows.append(rows.pop(unknown_idx))
    return rows
