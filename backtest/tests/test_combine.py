"""Combine-screen tests — hand-computed, offline. Lock the diversification arithmetic
and the "idealized upper bound" behaviour of `backtest.portfolio.combine`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest.portfolio.combine import Leg, combine_runs, leg_from_result


def _leg(name: str, days: dict) -> Leg:
    """Leg from a {date: pnl} map (dates are 2026-01-DD)."""
    return Leg(
        name=name,
        daily_pnl=[{"date": f"2026-01-{d:02d}", "pnl": p} for d, p in sorted(days.items())],
    )


# ── combined P&L / equity ──────────────────────────────────────────────────────


def test_combined_net_is_sum_of_leg_nets():
    a = _leg("A", {1: 100.0, 2: -40.0})
    b = _leg("B", {2: 50.0, 3: 20.0})
    out = combine_runs([a, b])
    assert out["combined_net"] == 130.0
    assert sum(p["net"] for p in out["per_leg"]) == 130.0


def test_combined_daily_sums_overlapping_days():
    a = _leg("A", {1: 100.0, 2: -40.0})
    b = _leg("B", {2: 50.0, 3: 20.0})
    out = combine_runs([a, b])
    by_day = {d["date"]: d["pnl"] for d in out["combined_daily_pnl"]}
    assert by_day["2026-01-01"] == 100.0
    assert by_day["2026-01-02"] == 10.0  # -40 + 50
    assert by_day["2026-01-03"] == 20.0


def test_equity_curve_anchors_on_capital():
    a = _leg("A", {1: 100.0, 2: -40.0})
    out = combine_runs([a], initial_capital=10_000.0)
    assert [p["equity"] for p in out["combined_equity_curve"]] == [10_100.0, 10_060.0]


# ── diversification drawdown ────────────────────────────────────────────────────


def test_offsetting_legs_reduce_drawdown_below_sum():
    # A bleeds on day 2, B pays on day 2 → combined never draws down as deep as A alone.
    a = _leg("A", {1: 100.0, 2: -80.0})  # own DD = 80
    b = _leg("B", {1: -80.0, 2: 100.0})  # own DD = 80
    out = combine_runs([a, b])
    # each day nets +20 → combined cumulative only rises → combined DD = 0
    assert out["diversification_dd"]["combined_max_dd"] == 0.0
    assert out["diversification_dd"]["sum_leg_max_dd"] == 160.0
    assert out["diversification_dd"]["ratio"] == 0.0


def test_identical_legs_double_drawdown_and_correlate_one():
    a = _leg("A", {1: 50.0, 2: -30.0})
    b = _leg("B", {1: 50.0, 2: -30.0})
    out = combine_runs([a, b])
    # same series added → combined DD is exactly twice one leg's DD, no diversification
    assert out["diversification_dd"]["combined_max_dd"] == 60.0  # 2 × 30
    assert out["diversification_dd"]["sum_leg_max_dd"] == 60.0
    assert out["diversification_dd"]["ratio"] == 1.0
    # perfectly correlated
    m = out["correlation"]["matrix"]
    assert m[0][1] == 1.0 and m[1][0] == 1.0


def test_max_dd_uses_offset_invariant_peak_to_trough():
    # up 100, down 60, down 20, up 10 → peak 100, trough 20 → DD = 80
    a = _leg("A", {1: 100.0, 2: -60.0, 3: -20.0, 4: 10.0})
    out = combine_runs([a])
    assert out["diversification_dd"]["combined_max_dd"] == 80.0


# ── correlation edges ───────────────────────────────────────────────────────────


def test_flat_leg_correlation_is_none_not_zero():
    a = _leg("A", {1: 10.0, 2: 10.0})  # zero variance — flat every day
    b = _leg("B", {1: 5.0, 2: -5.0})
    out = combine_runs([a, b])
    m = out["correlation"]["matrix"]
    assert m[0][0] == 1.0  # diagonal always 1
    assert m[0][1] is None  # undefined against a flat leg
    assert m[1][0] is None


def test_correlation_union_of_days_fills_missing_with_zero():
    # B trades a day A doesn't; the union vector pads A with 0 that day.
    a = _leg("A", {1: 10.0, 2: -10.0})
    b = _leg("B", {1: 10.0, 2: -10.0, 3: 5.0})
    out = combine_runs([a, b])
    assert out["correlation"]["labels"] == ["A", "B"]
    # not perfectly 1.0 anymore because of the padded day, but positive and defined
    c = out["correlation"]["matrix"][0][1]
    assert c is not None and 0.0 < c < 1.0


# ── per-leg contribution ────────────────────────────────────────────────────────


def test_per_leg_share_sums_to_one():
    a = _leg("A", {1: 90.0})
    b = _leg("B", {1: 10.0})
    out = combine_runs([a, b])
    shares = {p["name"]: p["share"] for p in out["per_leg"]}
    assert shares["A"] == 0.9
    assert shares["B"] == 0.1


def test_zero_net_share_is_none():
    a = _leg("A", {1: 50.0})
    b = _leg("B", {1: -50.0})
    out = combine_runs([a, b])
    assert out["combined_net"] == 0.0
    assert all(p["share"] is None for p in out["per_leg"])


# ── the run-result adapter ──────────────────────────────────────────────────────


def test_leg_from_result_reads_daily_pnl():
    result = {"daily_pnl": [{"date": "2026-01-01", "pnl": 25.0}], "kpis": {}}
    leg = leg_from_result("MPC SOS Fade", result)
    assert leg.name == "MPC SOS Fade"
    out = combine_runs([leg])
    assert out["combined_net"] == 25.0


def test_leg_from_result_tolerates_missing_daily_pnl():
    leg = leg_from_result("empty", {})
    out = combine_runs([leg])
    assert out["combined_net"] == 0.0
    assert out["combined_daily_pnl"] == []
