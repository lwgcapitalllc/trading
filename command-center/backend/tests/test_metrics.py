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
