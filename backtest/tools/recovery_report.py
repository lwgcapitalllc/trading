#!/usr/bin/env python3
"""recovery_report.py — replay a strategy, then replay the loss-recovery rule over its losses.

    python backtest/tools/recovery_report.py --start 2018-09-14 --end 2026-08-14

Prints the primary alone and the primary plus recovery, both COSTED, and prices the addition
against the only honest alternative — turning `exec_risk_pct` up on the strategy you already own.

⚠ Both sides carry costs. Charging the recovery leg and not the primary is rule 11 broken: the
run you re-create for comparison has to carry everything that decides what it is measured on, and
the primary's median hold is 0.3 days against the recovery's ~4, so the bias is not small.

⚠ Every number this prints is a LAB finding. There is no Pine twin and no parity gate.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from datetime import timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT), str(_ROOT / "engines"), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


from loss_recovery import LossRecoveryEngine, RecoveryConfig  # noqa: E402

from backtest.data.source import BarSource  # noqa: E402
from backtest.fills import PROFILES  # noqa: E402


def curve(seq, risk_pct):
    """Compounded balance multiple and peak-to-trough drawdown for a sequence of R."""
    bal = peak = 1.0
    dd = 0.0
    for r in seq:
        bal = max(bal * (1.0 + (risk_pct / 100.0) * r), 1e-9)
        peak = max(peak, bal)
        dd = max(dd, 1.0 - bal / peak)
    return sum(seq), bal, 100.0 * dd


def risk_for_dd(seq, target_dd):
    """The risk % whose max drawdown equals `target_dd`. Bisection, because compounding at a
    fixed fraction is non-linear and there is no closed form."""
    lo, hi = 0.01, 60.0
    for _ in range(90):
        mid = 0.5 * (lo + hi)
        if curve(seq, mid)[2] < target_dd:
            lo = mid
        else:
            hi = mid
    return lo, curve(seq, lo)[1]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", type=int, default=15)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--risk-pct", type=float, default=10.0, help="the primary's risk per trade")
    ap.add_argument("--profile", default="puprime_ecn", help="cost profile, or 'none'")
    ap.add_argument(
        "--size",
        type=float,
        default=None,
        help="recovery size as a fraction of normal risk (default: config's 0.25)",
    )
    ap.add_argument(
        "--longs-only",
        action="store_true",
        help="⚠ FITTED: this cut was chosen after seeing which direction won",
    )
    ap.add_argument("--sweep", action="store_true", help="sweep recovery size in 5%% steps")
    args = ap.parse_args()

    from strategies.python.mpc_sos_fade import LAB_STRATEGY

    bars = BarSource().load(args.symbol, args.tf, args.start, args.end)
    S, C = LAB_STRATEGY["strategy"], LAB_STRATEGY["config"]
    cfg = dataclasses.replace(C(fill_model="bar", symbol=args.symbol), exec_secondary=False)
    strat = S(config=cfg, initial_capital=10_000.0)
    strat.run(bars, warmup=args.warmup)
    trades = strat.execution.trades
    idx = bars.index

    prof = None if args.profile == "none" else PROFILES[args.profile]

    def cost_r(direction, i0, j, risk_price):
        """swap + spread + commission for one trade, in R. Lot size cancels out of the ratio."""
        if prof is None or prof.swap is None:
            return 0.0
        sw = prof.swap
        n = 0
        day = idx[i0].date()
        while day < idx[j].date():
            day += timedelta(days=1)
            if day.weekday() >= 5:  # the broker books no rollover at the weekend
                continue
            n += 3 if day.weekday() == sw.triple_weekday else 1
        return (
            (sw.per_lot_per_night(direction) * n) / (risk_price * sw.contract_size)
            - prof.spread / risk_price
            - 2.0 * prof.commission_per_side_per_lot / (risk_price * sw.contract_size)
        )

    base = sorted(
        (idx[t.exit_index], t.r + cost_r(t.dir, t.entry_index, t.exit_index, t.stop_distance))
        for t in trades
    )
    bseq = [r for _, r in base]
    e0, b0, dd0 = curve(bseq, args.risk_pct)
    gross0 = sum(t.r for t in trades)
    losses = [t for t in trades if t.r < -cfg.exec_scratch_r]
    print(f"{args.symbol} {args.tf}m  {args.start} → {args.end}   {len(bars):,} bars")
    print(f"cost profile: {args.profile}\n")
    print(f"PRIMARY  {len(trades)} trades, {len(losses)} losses")
    print(
        f"  gross {gross0:+.1f}R → net {e0:+.1f}R    {b0:,.0f}x @ {args.risk_pct:g}%   maxDD {dd0:.1f}%\n"
    )

    rcfg = RecoveryConfig(
        enabled=True,
        both_directions=not args.longs_only,
        risk_fraction=args.size if args.size is not None else RecoveryConfig().risk_fraction,
        scratch_r=cfg.exec_scratch_r,
    )
    recs = LossRecoveryEngine(rcfg).run(bars, trades)
    pend = LossRecoveryEngine(rcfg).pending(bars, trades)
    # Costed at FULL size, then scaled — so a size sweep does not re-walk the bars.
    costed = [
        (idx[t.exit_index], t.r + cost_r(t.direction, t.entry_index, t.exit_index, t.risk))
        for t in recs
    ]
    wins = sum(1 for _, r in costed if r > 0)
    holds = sorted((t.exit_index - t.entry_index) for t in recs)
    print(f"RECOVERY  {len(recs)} trades  ({len(pend)} losses never got their CHoCH)")
    print(
        f"  net at FULL size {sum(r for _, r in costed):+.1f}R   win {100 * wins / max(len(recs), 1):.0f}%   "
        f"median hold {holds[len(holds) // 2] if holds else 0} bars"
    )
    locked = sum(1 for t in recs if t.locked)
    print(f"  {locked} of {len(recs)} reached +{rcfg.lock_at_r:g}R and locked the recovery in\n")

    sizes = [x / 100 for x in range(5, 105, 5)] if args.sweep else [rcfg.risk_fraction]
    print(
        f"  {'size':>6} {'net R':>9} {'balance':>11} {'maxDD':>7} {'primary at that DD':>20} {'':>8}"
    )
    for f in sizes:
        seq = [r for _, r in sorted(base + [(ts, r * f) for ts, r in costed])]
        e, b, dd = curve(seq, args.risk_pct)
        br, bb = risk_for_dd(bseq, dd)
        ratio = b / bb
        tag = "recovery" if ratio > 1 else "primary "
        flag = " ≤ today's DD" if dd <= dd0 + 1e-9 else ""
        print(
            f"  {f:>5.0%} {e:>+8.1f}R {b:>10,.0f}x {dd:>6.1f}% "
            f"{br:>6.2f}% → {bb:>9,.0f}x  {tag} {max(ratio, 1 / ratio):.2f}x{flag}"
        )

    if not args.sweep:
        print("\n  (--sweep for the full size curve)")
    print("\n⚠ LAB ONLY — no Pine twin, no parity gate, not wired to any bot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
