#!/usr/bin/env python3
"""recovery_smoothness.py — "does loss recovery SMOOTH the equity curve?"

Different question from max drawdown, which was answered (no) and is a single worst moment.
Smoothness is about the rest of the curve: how long you spend below a prior high, how deep the
TYPICAL dip is, how often a new high arrives, and how variable the monthly result is.

Both sides costed at puprime_ecn. Recovery at 25%.

ANSWER: no. See strategies/python/loss_recovery/CLAUDE.md — average and median drawdown both rise,
time under water rises, longest underwater stretch is identical, and monthly risk-adjusted return
is unchanged. The per-trade volatility drop is dilution from quarter-size trades, not smoothing.
"""

from __future__ import annotations

import dataclasses
import sys
from datetime import timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "engines"), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from loss_recovery import LossRecoveryEngine, RecoveryConfig  # noqa: E402


def stats(rows, risk_pct=10.0):
    """rows = [(timestamp, R)] in time order -> a dict of curve-shape figures."""
    rows = sorted(rows)
    ts = [t for t, _ in rows]
    bal = 1.0
    peak = 1.0
    curve, dds, under, newhigh = [], [], 0, 0
    for _, r in rows:
        bal = max(bal * (1.0 + (risk_pct / 100.0) * r), 1e-9)
        if bal >= peak:
            peak = bal
            newhigh += 1
        else:
            under += 1
        dd = 1.0 - bal / peak
        dds.append(dd)
        curve.append(bal)
    # longest stretch below a prior high, in calendar days
    longest, run_start = timedelta(0), None
    for t, d in zip(ts, dds):
        if d > 1e-12:
            run_start = run_start or t
        elif run_start is not None:
            longest = max(longest, t - run_start)
            run_start = None
    if run_start is not None:
        longest = max(longest, ts[-1] - run_start)

    s = pd.Series([r for _, r in rows], index=pd.DatetimeIndex(ts))
    monthly = s.resample("ME").sum()
    monthly = monthly[monthly != 0]
    return {
        "trades": len(rows),
        "final": curve[-1],
        "maxdd": 100 * max(dds),
        "avgdd": 100 * float(np.mean(dds)),
        "meddd": 100 * float(np.median(dds)),
        "under_pct": 100 * under / len(rows),
        "newhigh": newhigh,
        "longest_days": longest.days,
        "r_std": float(np.std([r for _, r in rows])),
        "mo_n": len(monthly),
        "mo_std": float(monthly.std()),
        "mo_neg": int((monthly < 0).sum()),
        "mo_mean": float(monthly.mean()),
    }


def main():
    from backtest.data.source import BarSource
    from backtest.fills import PROFILES
    from strategies.python.sos_fade import LAB_STRATEGY

    prof = PROFILES["puprime_ecn"]
    sw = prof.swap
    bars = BarSource().load("XAUUSD", 15, "2018-09-14", "2026-08-14")
    S, C = LAB_STRATEGY["strategy"], LAB_STRATEGY["config"]
    cfg = dataclasses.replace(C(fill_model="bar", symbol="XAUUSD"), exec_secondary=False)
    st = S(config=cfg, initial_capital=10_000.0)
    st.run(bars, warmup=1000)
    trades = st.execution.trades
    idx = bars.index

    def cost_r(d, i0, j, risk):
        n = 0
        day = idx[i0].date()
        while day < idx[j].date():
            day += timedelta(days=1)
            if day.weekday() >= 5:
                continue
            n += 3 if day.weekday() == sw.triple_weekday else 1
        return (
            (sw.per_lot_per_night(d) * n) / (risk * sw.contract_size)
            - prof.spread / risk
            - 2.0 * prof.commission_per_side_per_lot / (risk * sw.contract_size)
        )

    base = [
        (idx[t.exit_index], t.r + cost_r(t.dir, t.entry_index, t.exit_index, t.stop_distance))
        for t in trades
    ]
    recs = LossRecoveryEngine(RecoveryConfig(enabled=True)).run(bars, trades)
    rec = [
        (idx[t.exit_index], (t.r + cost_r(t.direction, t.entry_index, t.exit_index, t.risk)) * 0.25)
        for t in recs
    ]

    a, b = stats(base), stats(base + rec)
    rows = [
        ("trades on the curve", "trades", "{:,.0f}"),
        ("ending balance", "final", "{:,.0f}x"),
        ("MAX drawdown", "maxdd", "{:.1f}%"),
        ("AVERAGE drawdown", "avgdd", "{:.1f}%"),
        ("MEDIAN drawdown", "meddd", "{:.1f}%"),
        ("% of trades under water", "under_pct", "{:.0f}%"),
        ("new equity highs", "newhigh", "{:,.0f}"),
        ("longest time under water", "longest_days", "{:,.0f}d"),
        ("std dev of per-trade R", "r_std", "{:.2f}R"),
        ("months traded", "mo_n", "{:,.0f}"),
        ("mean month", "mo_mean", "{:+.2f}R"),
        ("std dev of monthly R", "mo_std", "{:.2f}R"),
        ("losing months", "mo_neg", "{:,.0f}"),
    ]
    print(f"{'':<26} {'primary alone':>15} {'+ recovery @25%':>17}   change")
    for label, key, fmt in rows:
        va, vb = a[key], b[key]
        d = vb - va
        arrow = ""
        if key in (
            "maxdd",
            "avgdd",
            "meddd",
            "under_pct",
            "longest_days",
            "r_std",
            "mo_std",
            "mo_neg",
        ):
            arrow = "  smoother" if d < 0 else ("  rougher" if d > 0 else "  same")
        print(f"{label:<26} {fmt.format(va):>15} {fmt.format(vb):>17}   {d:+.2f}{arrow}")

    print(f"\n  losing months: {a['mo_neg']}/{a['mo_n']} -> {b['mo_neg']}/{b['mo_n']}")
    print("  per-trade R / std (higher = smoother per unit of return):")
    print(
        f"    primary {np.mean([r for _, r in base]) / a['r_std']:.3f}   "
        f"+recovery {np.mean([r for _, r in base + rec]) / b['r_std']:.3f}"
    )
    print("  monthly mean / std:")
    print(
        f"    primary {a['mo_mean'] / a['mo_std']:.3f}   +recovery {b['mo_mean'] / b['mo_std']:.3f}"
    )
    return 0


raise SystemExit(main())
