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


def effective_dd_limit_pct(ruleset: Optional[dict]) -> Optional[float]:
    """
    The same drawdown limit expressed as a PERCENT of the account, or None when the ruleset
    states none. None means NOT GRADEABLE — do not substitute a default. Total ruin (100%) was
    measured as a candidate default and rejected: a compounding simulation can never reach a zero
    balance, so a 10%-risk strategy with a 70.4% worst-1% drawdown clears a ruin bar and would be
    graded A. A threshold almost nothing can fail is not a grade.

    Percent is the comparison that survives compounding. A dollar limit is fixed while a
    compounding account is not, so once the account has grown the two are not comparable: on run
    06f7eece0db1 the dollar view reported a 100% breach of TOTAL RUIN ($10k on a $10k account)
    across simulations in which the account was never once wiped out — 0.00% real ruin. Every
    ruleset already carries the percent, either stated outright or derivable, so nothing new has
    to be defined to use it.
    """
    if not ruleset:
        return None
    size = ruleset.get("account_size")
    if ruleset.get("ruleset_type") in ("personal", "demo"):
        pct = ruleset.get("max_drawdown_from_peak_pct")
        return float(pct) if pct else None
    # Prop rows state the limit in dollars against a fixed account size, so the percent is that
    # ratio — a $5,000 trailing max loss on a $50,000 account is 10%.
    usd = effective_dd_limit_usd(ruleset)
    if usd > 0 and size:
        return usd / float(size) * 100.0
    return None


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
    kpis["platform_sharpe"] = kpis.get("sharpe")
    kpis["sharpe"] = daily_sharpe(daily_pnl)
    kpis["sharpe_low_sample"] = active_day_count(daily_pnl) < SHARPE_LOW_SAMPLE_DAYS
    return kpis


# How a stored concentration figure was weighted. Persisted alongside the number
# (backtest_runs.profit_concentration_basis) so a row is self-describing and the one-time
# backfill knows which rows it has already converted.
CONCENTRATION_RETURN = "return"
CONCENTRATION_DOLLARS = "dollars"


def _equity_base(equity_curve: Optional[list[dict]]) -> float:
    """The account balance the curve starts FROM, or 0 when it carries none.

    An equity point's `equity` is the running account value; subtracting that point's own
    `profit` gives the balance before the first trade. The python and MT5 runners open from a
    real deposit, so this is positive; the NT8 parser accumulates from 0, so it is 0.
    """
    if not equity_curve:
        return 0.0
    first = equity_curve[0]
    return float(first.get("equity", 0.0) or 0.0) - float(first.get("profit", 0.0) or 0.0)


def profit_concentration_pct(
    daily_pnl: list[dict],
    equity_curve: Optional[list[dict]] = None,
) -> tuple[Optional[float], str]:
    """
    Share of total gross profit earned in the most profitable quarter of the test span.

    Split the span (first→last date) into 4 equal slices and take the largest slice's share of
    gross profit × 100. High = the edge is clustered in one period rather than repeatable — a
    classic curve-fit signal.

    MEASURED IN RETURNS WHENEVER THE RUN COMPOUNDED (fixed 2026-07-31). Weighted by dollars, this
    reports the compounding rather than the clustering: on an account that grows 85x, the final
    quarter must hold nearly all the dollars however evenly the edge is spread. Measured on
    sos_fade run d2ab68f9e884 — dollar quarters of $9k / $49k / $71k / $1,039k read 88.9%
    ("edge clustered — overfit risk"), while the same trades as returns on the equity each was
    taken with read 40.0% ("spread across the test"). The warning was describing the account.

    The switch is whether the equity curve carries a real account base. A %-of-equity strategy
    compounds and must be normalized; a cum-P&L-from-zero curve (the NT8 shape) is a unit-size
    run whose dollars ARE already comparable across periods, and dividing those by a fictitious
    balance would introduce the opposite bias. With no curve at all, dollars is the only option.

    Returns (pct, basis). `pct` is None when there's no dated data, a zero span, or no positive
    profit to concentrate (e.g. a net-negative run with no winning days) — never fabricated.
    The frontend's computeProfitConcentration applies the identical rule.
    """
    # Each entry contributes a WEIGHT: a return when the run compounded, else a dollar amount.
    if _equity_base(equity_curve) > 0:
        basis = CONCENTRATION_RETURN
        points = []
        for e in equity_curve or []:
            if not e.get("date"):
                continue
            before = float(e.get("equity", 0.0) or 0.0) - float(e.get("profit", 0.0) or 0.0)
            if before <= 0:
                continue
            points.append((str(e["date"])[:10], float(e.get("profit", 0.0) or 0.0) / before))
    else:
        basis = CONCENTRATION_DOLLARS
        points = [
            (str(d["date"])[:10], float(d.get("pnl", 0.0) or 0.0))
            for d in daily_pnl
            if d.get("date")
        ]

    if len(points) < 2:
        return None, basis
    try:
        t0 = date.fromisoformat(points[0][0])
        t1 = date.fromisoformat(points[-1][0])
    except ValueError:
        return None, basis
    span = (t1 - t0).days
    if span <= 0:
        return None, basis

    quarters = [0.0, 0.0, 0.0, 0.0]
    gross = 0.0
    for day_str, weight in points:
        if weight <= 0:
            continue
        try:
            day = date.fromisoformat(day_str)
        except ValueError:
            continue
        gross += weight
        idx = int(((day - t0).days / span) * 4)
        idx = max(0, min(3, idx))
        quarters[idx] += weight

    if gross <= 0:
        return None, basis
    return round((max(quarters) / gross) * 100, 2), basis


# ── the three numbers that were true and misread (added 2026-08-01) ──────────────
#
# Audit of run f866873aa862 found no arithmetic wrong anywhere on the page. What was wrong was
# what three headline numbers let a reader CONCLUDE, and none of the three is fixable by relabelling
# — each needed a companion number that had never been computed.
#
#   max drawdown  stored and listed in DOLLARS only. $1.73M against $14.4M of profit reads as
#                 ~12%; against the running peak it is 55.9%. The detail page had the percentage
#                 (client-side, off the equity curve); the LIST page, where runs are compared, did
#                 not, and a list is exactly where a wrong order of magnitude does its damage.
#   win rate      67.3% — arithmetically right. 45 of the 111 "winners" made under a sixth of a
#                 typical loss, all exiting at the breakeven-stop buffer. The honest split is
#                 40% won / 27% scratched / 33% lost.
#   concentration 34.5%, which is the largest QUARTER's share — a time question. The reader hears
#                 the trade question, and its answer on that run was that 5 of 165 trades made
#                 47% of the gross.
#
# All three take the equity curve, and all three weight by RETURN when the run compounded, for the
# same reason `profit_concentration_pct` does: dollars on a compounding account measure the
# compounding. Each returns None rather than a fabricated value when there is nothing to measure.


def _trade_weights(equity_curve: Optional[list[dict]]) -> tuple[list[float], str]:
    """Each trade's contribution, in the basis that says something about the EDGE.

    Return on the equity it was taken with when the curve carries a real account base (a
    compounding run), else raw dollars (a unit-size cum-P&L-from-zero curve, where the dollars
    already are comparable). Identical rule to `profit_concentration_pct` — see its docstring for
    the measurement that forced it.
    """
    if not equity_curve:
        return [], CONCENTRATION_DOLLARS
    if _equity_base(equity_curve) <= 0:
        return ([float(e.get("profit", 0.0) or 0.0) for e in equity_curve], CONCENTRATION_DOLLARS)
    out = []
    for e in equity_curve:
        profit = float(e.get("profit", 0.0) or 0.0)
        before = float(e.get("equity", 0.0) or 0.0) - profit
        if before > 0:
            out.append(profit / before)
    return out, CONCENTRATION_RETURN


def max_drawdown_pct(equity_curve: Optional[list[dict]]) -> Optional[float]:
    """The worst drawdown as a percent of the equity it fell FROM (the running peak).

    **Not the same episode as the deepest DOLLAR drawdown, and the two must never be conflated.**
    On the shipped sos_fade run the biggest dollar drop is $109,665 from a $330,303 peak
    (33.2%), while the worst percentage drop is 54.9% — $16,748 → $7,551, only $9,198. Dividing
    the dollar figure by a static account size is what once printed "Max DD 1096.7%" on this
    strategy; dividing it by the FINAL equity is what makes 55.9% look like 12% on the runs list.
    A percent of a growing account needs a growing denominator.

    Mirrors the frontend's `maxDrawdownPctOf` exactly — that page computes it live off the curve;
    this one exists so the LIST can show it without shipping every run's curve to the browser.
    """
    if not equity_curve:
        return None
    peak = float("-inf")
    worst: Optional[float] = None
    base = _equity_base(equity_curve)
    series = ([base] if base > 0 else []) + [
        float(e.get("equity", 0.0) or 0.0) for e in equity_curve
    ]
    for value in series:
        peak = max(peak, value)
        if peak <= 0:  # a non-positive peak has no meaningful percent
            continue
        pct = (peak - value) / peak
        if worst is None or pct > worst:
            worst = pct
    return None if worst is None else round(worst * 100, 2)


# A trade this far below the run's own typical loss neither won nor lost meaningfully.
#
# 0.15 was picked off the measured shape of run f866873aa862 and then found to be the number
# `sos_fade_strategy.pine` already uses for the same idea — `exec_scratch_r = 0.15`, "Scratch band (R)",
# which grades a closed trade WIN / LOSS / SCRATCH on its stats table. The agreement is not a
# coincidence: for a fixed-risk strategy the median full loss IS 1R, so "0.15 of the median loss"
# and "0.15R" are the same bar. That Pine input is a stats-table setting and never reaches the
# lab, and this metric must work for strategies that have no such concept, so the threshold stays
# derived here rather than read off a config — but if it is ever made configurable, that field is
# the one it should follow.
_SCRATCH_FRACTION = 0.15


def scratch_count(equity_curve: Optional[list[dict]]) -> Optional[int]:
    """How many trades were effectively FLAT — the number the win rate hides.

    A win rate counts a trade that made a sixth of a losing trade as a full win. On run
    f866873aa862 that is 45 of the 111 "winners", every one of them exiting at exactly the
    breakeven-stop buffer: the stop doing its job, correctly, and not an edge. 67.3% won becomes
    40% won / 27% scratched / 33% lost, which is the same data saying something different.

    **The yardstick is the run's own median full loss, not a typed-in dollar figure.** For a
    fixed-risk strategy that median IS 1R (on this run 52 of 54 losers land within a cent of it),
    and for any other strategy it is still "what an ordinary adverse outcome costs here" — so the
    threshold self-scales across strategies, instruments and account sizes with nothing to tune.
    The median rather than the mean, because one outsized loss must not move the bar.

    Returns None when the run has no losing trade to measure against: with no scale there is no
    honest answer, and 0 would read as "no scratches" — the opposite of "cannot tell".
    """
    weights, _ = _trade_weights(equity_curve)
    scale = _scratch_scale(weights)
    if scale is None:
        return None
    return sum(1 for w in weights if abs(w) < scale)


def _scratch_scale(weights: list[float]) -> Optional[float]:
    """The band, in the weights' own basis: `_SCRATCH_FRACTION` of the median FULL loss.

    None when the run has no losing trade to measure against — with no scale there is no honest
    answer, and 0 would read as "nothing is a scratch", which is the opposite of "cannot tell".
    Split out of `scratch_count` so `trade_outcomes` grades against the identical bar: the run's
    scratch COUNT and the chart's per-trade verdict disagreeing would be worse than either.
    """
    losses = [abs(w) for w in weights if w < 0]
    if not losses:
        return None
    scale = float(np.median(losses))
    return scale * _SCRATCH_FRACTION if scale > 0 else None


# The three verdicts `trade_outcomes` grades into. Strings rather than an enum because they cross
# into a JSON chart spec and are read by the frontend.
OUTCOME_WON = "won"
OUTCOME_LOST = "lost"
OUTCOME_SCRATCH = "scratch"


def trade_outcomes(equity_curve: Optional[list[dict]]) -> Optional[list[str]]:
    """One verdict per curve point — won / scratch / lost — or None when it cannot be graded.

    Same bar as `scratch_count`, and that is the whole reason it exists: a run whose KPI row says
    68 scratches while its chart calls every one of them a LOSS is one system telling two stories.
    A trade that netted exactly $0.00 labelled "Lost" is what sent a reader hunting a bug in the
    exit code on run 295a6ff29d21 — the exit was right and the label was not.

    ⚠ **Aligned 1:1 with `equity_curve`, which is what `_trade_weights` is NOT** — that one drops
    any point it cannot weight, so its indices stop matching the trades the moment one is dropped.
    A point that cannot be weighted here is graded by SIGN and never as a scratch, because an
    ungradeable trade is not a measured flat one.

    Returns None (rather than an all-`won`/`lost` list) when the run carries no losing trade to
    scale against, so a caller can tell "no scratch band" from "no scratches".
    """
    if not equity_curve:
        return None
    weights, _ = _trade_weights(equity_curve)
    scale = _scratch_scale(weights)
    if scale is None:
        return None
    compounding = _equity_base(equity_curve) > 0
    out: list[str] = []
    for e in equity_curve:
        profit = float(e.get("profit", 0.0) or 0.0)
        weight = profit
        if compounding:
            before = float(e.get("equity", 0.0) or 0.0) - profit
            weight = profit / before if before > 0 else None
        if weight is not None and abs(weight) < scale:
            out.append(OUTCOME_SCRATCH)
        else:
            out.append(OUTCOME_WON if profit > 0 else OUTCOME_LOST)
    return out


# How many trades "a handful" is. Small enough that hitting the threshold is a real finding.
TRADE_CONCENTRATION_TOP_N = 5


def trade_concentration_pct(
    equity_curve: Optional[list[dict]],
    top_n: int = TRADE_CONCENTRATION_TOP_N,
) -> Optional[float]:
    """Share of GROSS PROFIT made by the `top_n` biggest winners.

    The companion to `profit_concentration_pct`, and it answers the question that metric's NAME
    suggests but its definition does not: that one splits the span into quarters and asks whether
    the edge showed up in one PERIOD, which is a curve-fit-over-time test. This asks whether it
    came from a handful of TRADES. The two can disagree completely and both be right — run
    f866873aa862 reads 34.5% by quarter (spread evenly across 6.6 years) while 5 of its 165 trades
    made 47% of everything won.

    Neither number is a verdict on its own. A runner-based strategy is SUPPOSED to be fat-tailed,
    and this repo's stated design intent is few high-quality setups — so read a high value as
    "the edge rests on the tail, size the risk accordingly", not as a defect.

    None when there is no positive profit to concentrate.
    """
    weights, _ = _trade_weights(equity_curve)
    wins = sorted((w for w in weights if w > 0), reverse=True)
    gross = sum(wins)
    if gross <= 0:
        return None
    return round((sum(wins[:top_n]) / gross) * 100, 2)


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
        rows.append(
            {
                "regime": regime,
                "days": day["days"] if day else 0,
                "trades": trades,
                "net_pnl": round(net_pnl, 2),
                # win_rate = real wins (entries are profit 0, never counted) over the rescaled count.
                "win_rate": (t["wins"] / trades) if (t and trades) else None,
                "profit_factor": (t["gross_win"] / t["gross_loss"])
                if (t and t["gross_loss"] > 0)
                else None,
                "worst_day": round(day["worst_day"], 2)
                if (day and day["worst_day"] is not None)
                else None,
            }
        )

    rows.sort(key=lambda r: (-r["days"], -r["trades"]))
    unknown_idx = next((i for i, r in enumerate(rows) if r["regime"] == _REGIME_UNKNOWN), None)
    if unknown_idx is not None and unknown_idx != len(rows) - 1:
        rows.append(rows.pop(unknown_idx))
    return rows
