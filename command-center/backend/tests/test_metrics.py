"""Canonical-Sharpe metrics — the zero-filled-flat-days definition and its low-sample guard."""

from datetime import date, timedelta

import numpy as np
import pytest

from services.metrics import (
    SHARPE_LOW_SAMPLE_DAYS,
    active_day_count,
    apply_canonical_sharpe,
    daily_sharpe,
    daily_sharpe_from_values,
    profit_concentration_pct,
    zero_filled_daily_values,
)


def _weekdays(start: str, n: int) -> list[date]:
    out, cur = [], date.fromisoformat(start)
    while len(out) < n:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


# ── zero_filled_daily_values ──────────────────────────────────────────────────

def test_zero_fill_inserts_flat_weekdays_between_active_days():
    # Mon 2026-01-05 and Fri 2026-01-09 traded; Tue/Wed/Thu were flat but real.
    pnl = [{"date": "2026-01-05", "pnl": 100.0}, {"date": "2026-01-09", "pnl": 50.0}]
    assert zero_filled_daily_values(pnl) == [100.0, 0.0, 0.0, 0.0, 50.0]


def test_zero_fill_skips_weekends():
    # Fri 2026-01-09 → Mon 2026-01-12: the Sat/Sun between are not trading days.
    pnl = [{"date": "2026-01-09", "pnl": 10.0}, {"date": "2026-01-12", "pnl": 20.0}]
    assert zero_filled_daily_values(pnl) == [10.0, 20.0]


def test_zero_fill_keeps_a_weekend_day_that_actually_traded():
    # A Sunday-open forex fill is a real observation — never silently dropped.
    pnl = [{"date": "2026-01-09", "pnl": 10.0},   # Fri
           {"date": "2026-01-11", "pnl": 5.0},    # Sun
           {"date": "2026-01-12", "pnl": 20.0}]   # Mon
    assert zero_filled_daily_values(pnl) == [10.0, 5.0, 20.0]


def test_zero_fill_degenerate_inputs():
    assert zero_filled_daily_values([]) == []
    assert zero_filled_daily_values([{"date": "2026-01-05", "pnl": 7.0}]) == [7.0]


def test_zero_fill_is_idempotent():
    pnl = [{"date": "2026-01-05", "pnl": 100.0}, {"date": "2026-01-09", "pnl": 50.0}]
    once = zero_filled_daily_values(pnl)
    twice = zero_filled_daily_values(
        [{"date": d.isoformat(), "pnl": v} for d, v in zip(_weekdays("2026-01-05", 5), once)]
    )
    assert once == twice


def test_zero_fill_sums_duplicate_dates():
    pnl = [{"date": "2026-01-05", "pnl": 10.0}, {"date": "2026-01-05", "pnl": 5.0},
           {"date": "2026-01-06", "pnl": 1.0}]
    assert zero_filled_daily_values(pnl) == [15.0, 1.0]


# ── the actual bug ────────────────────────────────────────────────────────────

def test_sharpe_counts_flat_days_and_is_far_below_the_active_only_value():
    """A strategy flat ~90% of the time must not be scored on its active days alone.

    Reproduces the shipped run: 22 winning days scattered across a ~225-weekday span read 7.80
    when only active days were counted; the honest value is ~2.
    """
    span = _weekdays("2025-09-01", 225)
    active = span[::10]           # 23 active days, evenly spread
    pnl = [{"date": d.isoformat(), "pnl": 500.0} for d in active]

    active_only = daily_sharpe_from_values([p["pnl"] for p in pnl])
    honest = daily_sharpe(pnl)

    # Active-only sees a constant series (sd == 0) or a wildly inflated one; either way the
    # zero-filled value is the one that reflects the 202 days of doing nothing.
    assert honest < active_only or active_only == 0.0
    assert 0.0 < honest < 6.0


def test_sharpe_matches_hand_computed_zero_filled_value():
    pnl = [{"date": "2026-01-05", "pnl": 100.0}, {"date": "2026-01-09", "pnl": 50.0}]
    vals = np.array([100.0, 0.0, 0.0, 0.0, 50.0])
    expected = (vals.mean() / vals.std(ddof=1)) * np.sqrt(252)
    assert daily_sharpe(pnl) == pytest.approx(expected)


def test_sharpe_of_a_single_flat_span_is_zero_not_a_divide_error():
    pnl = [{"date": d.isoformat(), "pnl": 0.0} for d in _weekdays("2026-01-05", 10)]
    assert daily_sharpe(pnl) == 0.0


# ── active_day_count / the low-sample guard ───────────────────────────────────

def test_active_day_count_ignores_flat_days():
    pnl = [{"date": "2026-01-05", "pnl": 100.0},
           {"date": "2026-01-06", "pnl": 0.0},
           {"date": "2026-01-07", "pnl": -20.0}]
    assert active_day_count(pnl) == 2


def test_low_sample_flag_reads_active_days_not_the_zero_filled_span():
    """The guardrail: zero-filling must not make a thin run look well-sampled.

    3 active days scattered over a year is exactly the case the flag exists to catch — measuring
    the zero-filled series (~250 entries) would silently clear it.
    """
    span = _weekdays("2025-09-01", 225)
    pnl = [{"date": d.isoformat(), "pnl": 500.0} for d in (span[0], span[100], span[224])]

    kpis = apply_canonical_sharpe({"sharpe": 9.9}, pnl)

    assert active_day_count(pnl) == 3
    assert len(zero_filled_daily_values(pnl)) > SHARPE_LOW_SAMPLE_DAYS   # the trap
    assert kpis["sharpe_low_sample"] is True


def test_low_sample_flag_clear_when_enough_active_days():
    span = _weekdays("2025-09-01", 225)
    pnl = [{"date": d.isoformat(), "pnl": 100.0} for d in span[:SHARPE_LOW_SAMPLE_DAYS]]
    kpis = apply_canonical_sharpe({"sharpe": 1.0}, pnl)
    assert kpis["sharpe_low_sample"] is False


# ── apply_canonical_sharpe contract ───────────────────────────────────────────

def test_apply_canonical_sharpe_moves_platform_value_and_replaces_sharpe():
    pnl = [{"date": "2026-01-05", "pnl": 100.0}, {"date": "2026-01-09", "pnl": 50.0}]
    kpis = apply_canonical_sharpe({"sharpe": 1.23}, pnl)
    assert kpis["platform_sharpe"] == 1.23
    assert kpis["sharpe"] == pytest.approx(daily_sharpe(pnl))
    assert kpis["sharpe"] != 1.23


# ── backfill: platform_sharpe honesty ─────────────────────────────────────────

def test_backfill_never_invents_a_platform_sharpe_for_python_runs(fresh_db, tmp_path):
    """A python run has no platform, so platform_sharpe must stay NULL.

    `backtest/output.py` deliberately computes no Sharpe (the lab owns the canonical one), so a
    python run's `sharpe` is ALREADY ours. The backfill's sharpe→platform_sharpe move assumes the
    column still holds the platform's own number; for python that assumption is false and the move
    would stamp our value as the platform's, inventing a reference point that never existed.
    """
    import json
    import scripts.backfill_metrics as bf
    from services import lab_db
    from tests.conftest import _insert_strategy

    strategy_id = _insert_strategy(lab_db)

    daily = tmp_path / "daily.json"
    daily.write_text(json.dumps([{"date": "2026-01-05", "pnl": 100.0},
                                 {"date": "2026-01-09", "pnl": 50.0}]))

    conn = lab_db._connect()
    for run_id, runner in (("py_run", "python"), ("mt5_run", "mt5")):
        conn.execute(
            "INSERT INTO backtest_runs (run_id, strategy_id, instrument, params, bar_type, "
            "bar_value, start_date, end_date, commission_per_side, slippage_ticks, status, "
            "created_at, runner, sharpe, platform_sharpe, daily_pnl_path) "
            "VALUES (?, ?, 'XAUUSD.s', '{}', 'Minute', 15, '2026-01-01', '2026-01-31', "
            "0, 0, 'complete', 0, ?, 7.8, NULL, ?)",
            (run_id, strategy_id, runner, str(daily)),
        )
    conn.commit()

    bf.backfill(dry_run=False)

    rows = {r["run_id"]: dict(r) for r in
            conn.execute("SELECT run_id, sharpe, platform_sharpe FROM backtest_runs").fetchall()}

    # python: our 7.8 is discarded, never relabelled as a platform value
    assert rows["py_run"]["platform_sharpe"] is None
    # mt5: the platform genuinely reported 7.8 — that move still happens
    assert rows["mt5_run"]["platform_sharpe"] == 7.8
    # both get the canonical zero-filled value
    for run_id in ("py_run", "mt5_run"):
        assert rows[run_id]["sharpe"] == pytest.approx(
            daily_sharpe([{"date": "2026-01-05", "pnl": 100.0},
                          {"date": "2026-01-09", "pnl": 50.0}])
        )


# ── Profit concentration — the return basis ──────────────────────────────────────────────────
#
# The metric answers "was the edge clustered in one window, or repeatable?". Weighted by dollars
# it answers a different question on a compounding account: the last quarter must hold nearly all
# the dollars however evenly the edge is spread, which is what made mpc_sos_fade d2ab68f9e884
# read 88.9% ("edge clustered — overfit risk") on a run whose returns are spread.


def _curve(rows, *, base):
    """Equity points from (date, pnl) pairs, compounding from `base`. base=0 gives the NT8
    cum-P&L-from-zero shape — a unit-size run with no account to compound against."""
    out, equity = [], float(base)
    for i, (day, pnl) in enumerate(rows, start=1):
        equity += pnl
        out.append({"index": i, "date": day, "equity": round(equity, 2), "profit": pnl})
    return out


def _even_return_run(base=10_000.0, years=4, per_year=8, rate=0.20):
    """A strategy with a CONSTANT 20% return per trade, evenly spaced over four years — the edge
    is identical in every quarter by construction, so honest concentration is ~25%."""
    rows, equity = [], base
    for y in range(years):
        for i in range(per_year):
            pnl = equity * rate
            equity += pnl
            rows.append((f"{2021 + y}-{1 + i:02d}-15", round(pnl, 2)))
    return rows


def test_compounding_run_is_measured_in_returns_not_dollars():
    rows = _even_return_run()
    daily = [{"date": d, "pnl": p} for d, p in rows]
    curve = _curve(rows, base=10_000.0)

    pct, basis = profit_concentration_pct(daily, curve)
    assert basis == "return"
    # Every trade earned the same RETURN, so no quarter is special — ~25%, and nowhere near the
    # 60% threshold that prints "edge clustered — overfit risk".
    assert pct == pytest.approx(25.0, abs=1.0)

    # The same trades weighted by dollars: the compounding alone reads as clustering.
    dollars, _ = profit_concentration_pct(daily, None)
    assert dollars > 60


def test_unit_size_run_keeps_the_dollar_basis():
    # An NT8-shaped curve accumulates from 0, so there is no balance to compound against — its
    # dollars are already comparable across periods and must not be divided by a fiction.
    rows = [("2021-01-15", 100.0), ("2021-07-15", 100.0),
            ("2022-01-15", 100.0), ("2022-07-15", 100.0)]
    daily = [{"date": d, "pnl": p} for d, p in rows]
    pct, basis = profit_concentration_pct(daily, _curve(rows, base=0.0))
    assert basis == "dollars"
    assert pct == pytest.approx(25.0, abs=1.0)


def test_clustered_edge_still_reports_clustered():
    # The fix must not blunt the detector: profit earned only in the final quarter reads ~100%
    # on the return basis too.
    rows = [("2021-02-15", 0.0), ("2021-08-15", 0.0), ("2022-02-15", 0.0),
            ("2022-11-15", 4000.0)]
    daily = [{"date": d, "pnl": p} for d, p in rows]
    pct, basis = profit_concentration_pct(daily, _curve(rows, base=10_000.0))
    assert basis == "return"
    assert pct == pytest.approx(100.0)


def test_no_positive_profit_is_none_never_zero():
    rows = [("2021-01-15", -100.0), ("2022-01-15", -100.0)]
    daily = [{"date": d, "pnl": p} for d, p in rows]
    pct, _ = profit_concentration_pct(daily, _curve(rows, base=10_000.0))
    assert pct is None


# ── the three shape metrics (2026-08-01) ─────────────────────────────────────────
#
# Each exists because a TRUE number was letting a reader conclude something false. The tests
# below pin the conclusion each one restores, not just the arithmetic.

from services.metrics import (                                    # noqa: E402
    max_drawdown_pct,
    scratch_count,
    trade_concentration_pct,
)


def _trades(profits: list[float], base: float = 10_000.0) -> list[dict]:
    """An equity curve in the compounding shape — `equity` running, `profit` per trade."""
    out, eq = [], base
    for p in profits:
        eq += p
        out.append({"equity": eq, "profit": p})
    return out


def test_max_drawdown_is_relative_to_the_peak_it_fell_from():
    """$10k → $20k → $10k is a 50% drawdown, not 100% of the starting balance and not the 42%
    it would read as against the final equity. The denominator has to grow with the account."""
    assert max_drawdown_pct(_trades([10_000.0, -10_000.0])) == pytest.approx(50.0)


def test_max_drawdown_counts_a_fall_from_the_opening_balance():
    """A run that loses on trade 1 has drawn down before its first equity point exists. Measuring
    only the points would miss it entirely and report 0%."""
    assert max_drawdown_pct(_trades([-2_500.0])) == pytest.approx(25.0)


def test_max_drawdown_pct_and_dollars_can_name_different_episodes():
    """The whole reason both are reported. Here the deepest DOLLAR fall ($4k) comes off a $24k
    peak = 17%, while the worst PERCENTAGE fall is the early $2.5k off $10k = 25%."""
    curve = _trades([-2_500.0, 16_500.0, -4_000.0])
    assert max_drawdown_pct(curve) == pytest.approx(25.0)


def test_max_drawdown_of_an_undefeated_curve_is_zero_not_none():
    assert max_drawdown_pct(_trades([100.0, 100.0])) == 0.0


def test_a_breakeven_scratch_is_not_counted_as_a_win():
    """The defect this row exists for: four full losses set the scale, and a +$1 exit is a
    scratch rather than a win however green it looks in the trade list."""
    curve = _trades([-1_000.0] * 4 + [1.0, 5_000.0])
    assert scratch_count(curve) == 1


def test_the_scratch_scale_is_the_median_loss_so_one_outlier_cannot_move_it():
    """A mean would be dragged to $2,600 by the single -$10k, making the -$300 trade a
    'scratch' (it is 12% of the mean, under the 15% bar). The median holds at $1,000."""
    curve = _trades([-1_000.0, -1_000.0, -1_000.0, -10_000.0, -300.0])
    assert scratch_count(curve) == 0


def test_scratch_count_is_none_with_no_losers_never_zero():
    """No losing trade means no scale. 0 would read as 'no scratches' — the opposite of
    'cannot tell'."""
    assert scratch_count(_trades([100.0, 200.0])) is None
    assert scratch_count([]) is None


def test_trade_concentration_finds_a_tail_that_the_quarter_metric_cannot():
    """20 even winners plus one that is 4x the rest: the top-5 share is well past half even
    though nothing about the CALENDAR is clustered."""
    curve = _trades([100.0] * 20 + [2_000.0])
    pct = trade_concentration_pct(curve)
    assert pct is not None and pct > 50


def test_trade_concentration_is_low_when_the_edge_is_spread():
    # Unit-size shape (a curve accumulating from 0), so the dollars ARE the weights: 100 equal
    # wins put exactly 5 of them in the top 5.
    assert trade_concentration_pct(_trades([100.0] * 100, base=0.0)) == pytest.approx(5.0)
    # The same 100 wins on a COMPOUNDING account are mildly front-loaded and that is correct,
    # not a bug: $100 is a bigger share of a $10k account than of the $20k it later becomes.
    # It must still read as spread, nowhere near the tail-carried threshold.
    spread = trade_concentration_pct(_trades([100.0] * 100))
    assert spread is not None and 5.0 < spread < 10.0


def test_trade_concentration_ignores_losers_and_is_none_with_no_profit():
    assert trade_concentration_pct(_trades([-100.0, -200.0])) is None


def test_all_three_weight_by_return_on_a_compounding_run():
    """Two trades of identical SIZE relative to the account they were taken with — the first
    $1,000 on $10k, the second $10,000 on $100k. In dollars the second looks 10x the edge; as
    returns they are equal, so neither dominates the concentration. Same basis rule as
    profit_concentration_pct, and the same reason: dollars measure the compounding."""
    curve = [{"equity": 11_000.0, "profit": 1_000.0},
             {"equity": 100_000.0, "profit": 0.0},        # a deposit-shaped jump, no P&L
             {"equity": 110_000.0, "profit": 10_000.0}]
    assert trade_concentration_pct(curve, top_n=1) == pytest.approx(50.0)
