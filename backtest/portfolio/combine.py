"""The combine screen — add up finished standalone runs to see if they diversify.

This is the CHEAP, IDEALIZED view. Each leg is a strategy that already ran ALONE on its own
account; we just add the daily P&L together. There is no shared account here, so nothing is
shrunk or blocked — every leg trades a full account and always fills. That makes the combined
result an UPPER BOUND: on a real shared account the legs fight for one risk budget and the
stack is smaller. Use this to decide *which* strategies are worth stacking; use the
shared-account simulator (later) for what the stack actually does.

Everything here is arithmetic over each run's stored `daily_pnl` (the `{date, pnl}` list
`backtest.output.build_daily_pnl` produces). Day-resolution on purpose: summing per-day P&L
needs no per-trade merge, so no `exit_ms` and no intrabar ordering. Stdlib only.

Output of `combine_runs`:
  {
    "combined_daily_pnl":   [{date, pnl}]            # legs summed by UTC day
    "combined_equity_curve":[{index, date, pnl, equity}]   # day-resolution, anchored on capital
    "correlation":          {labels, matrix}         # pairwise Pearson of daily P&L (None = flat leg)
    "diversification_dd":   {combined_max_dd, sum_leg_max_dd, ratio}
    "per_leg":              [{name, net, share, max_dd}]
  }
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

__all__ = ["Leg", "combine_runs", "leg_from_result"]


def _round(x: float, n: int = 2) -> float:
    return round(float(x), n)


@dataclass(frozen=True)
class Leg:
    """One strategy's finished standalone run, reduced to what the screen needs.

    `daily_pnl` is the run's stored `{date, pnl}` list (UTC day → net that day). `name` is
    the label shown in the correlation matrix and per-leg table (a strategy or run name).
    """

    name: str
    daily_pnl: Sequence[dict]


def leg_from_result(name: str, result: dict) -> Leg:
    """Build a `Leg` from a lab run result (or any dict carrying `daily_pnl`)."""
    return Leg(name=name, daily_pnl=list(result.get("daily_pnl") or []))


# ── drawdown ──────────────────────────────────────────────────────────────────


def _max_drawdown(daily: Sequence[dict]) -> float:
    """Largest peak-to-trough drop of the cumulative daily P&L, as a POSITIVE dollar number.

    The starting-capital offset is a constant, so it never changes the drawdown — this works
    straight off P&L, no anchor needed. Same sign convention as `output._max_drawdown`.
    """
    peak = 0.0
    equity = 0.0
    worst = 0.0
    for d in sorted(daily, key=lambda x: x["date"]):
        equity += d["pnl"]
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return _round(worst)


# ── correlation ─────────────────────────────────────────────────────────────--


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Pearson correlation, or None if either series has no variance (a flat leg —
    correlation is undefined, not zero, so we say so rather than invent a 0)."""
    n = len(xs)
    if n == 0:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0.0 or vy == 0.0:
        return None
    return _round(cov / (vx * vy) ** 0.5, 4)


def _correlation_matrix(legs: Sequence[Leg]) -> dict:
    """Pairwise correlation of the legs' daily P&L over the UNION of all trading days
    (a day a leg didn't trade counts as 0 for it — the account was flat that day). The
    diagonal is 1.0; a flat leg's row/column is None."""
    all_days = sorted({d["date"] for leg in legs for d in leg.daily_pnl})
    vectors = []
    for leg in legs:
        by_day = {d["date"]: d["pnl"] for d in leg.daily_pnl}
        vectors.append([by_day.get(day, 0.0) for day in all_days])

    labels = [leg.name for leg in legs]
    matrix: list[list[Optional[float]]] = []
    for i, vi in enumerate(vectors):
        row: list[Optional[float]] = []
        for j, vj in enumerate(vectors):
            row.append(1.0 if i == j else _pearson(vi, vj))
        matrix.append(row)
    return {"labels": labels, "matrix": matrix}


# ── the entry point ─────────────────────────────────────────────────────────--


def combine_runs(legs: Sequence[Leg], *, initial_capital: float = 0.0) -> dict:
    """Add up standalone runs into one idealized combined account. See module docstring."""
    legs = list(legs)

    # combined daily P&L: sum every leg's day into one series
    combined: dict[str, float] = {}
    for leg in legs:
        for d in leg.daily_pnl:
            combined[d["date"]] = combined.get(d["date"], 0.0) + d["pnl"]
    combined_daily = [{"date": day, "pnl": _round(pnl)} for day, pnl in sorted(combined.items())]

    # day-resolution equity curve, anchored on the account you'd compare against
    curve = []
    equity = float(initial_capital)
    for i, d in enumerate(combined_daily, start=1):
        equity += d["pnl"]
        curve.append({"index": i, "date": d["date"], "pnl": d["pnl"], "equity": _round(equity)})

    # diversification drawdown: the account's DD vs the sum of the legs' own DDs
    combined_dd = _max_drawdown(combined_daily)
    sum_leg_dd = _round(sum(_max_drawdown(leg.daily_pnl) for leg in legs))
    div_dd = {
        "combined_max_dd": combined_dd,
        "sum_leg_max_dd": sum_leg_dd,
        # < 1 means the stack drew down less than its parts summed — the diversification benefit.
        "ratio": _round(combined_dd / sum_leg_dd, 4) if sum_leg_dd > 0 else None,
    }

    # per-leg contribution
    combined_net = _round(sum(sum(d["pnl"] for d in leg.daily_pnl) for leg in legs))
    per_leg = []
    for leg in legs:
        net = _round(sum(d["pnl"] for d in leg.daily_pnl))
        per_leg.append(
            {
                "name": leg.name,
                "net": net,
                "share": _round(net / combined_net, 4) if combined_net != 0 else None,
                "max_dd": _max_drawdown(leg.daily_pnl),
            }
        )

    return {
        "combined_daily_pnl": combined_daily,
        "combined_equity_curve": curve,
        "correlation": _correlation_matrix(legs),
        "diversification_dd": div_dd,
        "per_leg": per_leg,
        "combined_net": combined_net,
    }
