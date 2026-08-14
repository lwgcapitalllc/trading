#!/usr/bin/env python3
"""tf_overlap.py — is the 30-minute A+ a SECOND strategy, or the same bet twice?

Aaron, 2026-08-09. `tf_sweep.py` measured `mpc_sos_fade` on four timeframes over the same 6.5
years and the 30m row posts essentially the SAME edge per trade as the shipped 15m bot
(+0.893R vs +0.894R over 106 trades against 159). That is the first positive result to come out
of the order-block thread, and it is worth exactly nothing until this question is answered.

`CLAUDE.md` → *Trading Philosophy*: "Stacking only reduces drawdown if the strategies are actually
independent... Two 'different' strategies off one structure stream can fire together, lose
together, and behave as one position at 2x the size." A 15m and a 30m A+ read THE SAME market
structure on THE SAME instrument with THE SAME rules. The prior here is not neutral — it is that
they are the same bot looking through a coarser lens — so this tool exists to try to REFUTE the
30m result, not to confirm it.

**WHY IT IS NOT `overlap_audit.py`.** That tool replays two strategies over ONE bar frame and
works in bar INDICES. Here the two legs live on frames of different bar sizes, so an index means a
different amount of time on each side and nothing can be compared through it. Everything below is
measured on the TRADES' OWN CLOCK (`entry_ms` / `exit_ms`), which is the only axis both frames
share. Same questions, different axis.

⚠ **It does not net them into one equity curve.** Each leg sizes off its own equity, so running
both on one account changes both legs' sizes from the first shared trade and the result is a third
thing neither leg is. `backtest/portfolio/run_stack` is the object that answers that, and it can
be pointed at this pair once this tool says the pair is worth stacking.

⚠ **"They rarely overlap" is NOT a clean bill of health, and this is the trap the B-LEG audit
already recorded.** Two legs can be flat at different moments and still lose in the same months
for the same reason. That is what the monthly correlation is for, and on two timeframes of ONE
strategy it is the more informative of the two numbers, not the weaker one.

Usage:
    python backtest/tools/tf_overlap.py --start 2020-01-01 --end 2026-08-03
    python backtest/tools/tf_overlap.py --tf-a 15 --tf-b 60
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_MIN = 60_000  # ms in a minute
# Two entries closer together than this are reading the same structure break rather than two
# different legs of the move. 16 bars is the window `overlap_audit.py` uses on M15; stated here
# in MINUTES because the two legs do not share a bar size.
_CLUSTER_MIN = 16 * 15


def _holds(trades):
    """(dir, entry_ms, exit_ms, r) per trade, dropping any whose clock is unset.

    ⚠ A trade with `entry_ms == 0` is not a trade at midnight 1970 — it is a record whose
    reporting clock was never written, and averaging it in would silently anchor every overlap
    calculation to the epoch. Counted and reported rather than dropped in silence.
    """
    good, bad = [], 0
    for t in trades:
        if not t.entry_ms or not t.exit_ms or t.exit_ms < t.entry_ms:
            bad += 1
            continue
        good.append((t.dir, int(t.entry_ms), int(t.exit_ms), float(t.r)))
    return good, bad


def _minutes(holds):
    return sum(e - s for _d, s, e, _r in holds) / _MIN


def _overlap_ms(a, b):
    """Shared milliseconds of two half-open intervals."""
    return max(0, min(a[2], b[2]) - max(a[1], b[1]))


def _monthly_r(holds):
    out = defaultdict(float)
    for _d, s, _e, r in holds:
        d = dt.datetime.utcfromtimestamp(s / 1000)
        out[f"{d.year}-{d.month:02d}"] += r
    return out


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def _replay(symbol, tf, start, end, capital):
    from backtest.data.source import BarSource
    from strategies.python.mpc_sos_fade import LAB_STRATEGY

    print(f"  loading {symbol} {tf}m ...", flush=True)
    df = BarSource().load(symbol, str(tf), start, end)
    if df.empty:
        raise SystemExit(f"no {tf}m bars for {symbol} in this window.")
    StrategyCls, ConfigCls = LAB_STRATEGY["strategy"], LAB_STRATEGY["config"]
    cfg = ConfigCls(fill_model="bar", symbol=symbol, exec_secondary=False)
    print(f"    {len(df):,} bars, replaying ...", flush=True)
    strat = StrategyCls(config=cfg, initial_capital=capital).run(df)
    return strat.execution.trades


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf-a", default="15")
    ap.add_argument("--tf-b", default="30")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument(
        "--cluster-min",
        type=int,
        default=_CLUSTER_MIN,
        help="two same-direction entries this many MINUTES apart or less are counted "
        "as one structure break read twice",
    )
    ap.add_argument(
        "--expect-a-trades",
        type=int,
        default=None,
        help="assert leg A reproduces this trade count — the control that says this "
        "is the shipped bot and not a third thing",
    )
    args = ap.parse_args(argv)

    end = args.end or dt.date.today().isoformat()
    print(f"leg A = {args.tf_a}m")
    ta = _replay(args.symbol, args.tf_a, args.start, end, args.capital)
    print(f"leg B = {args.tf_b}m")
    tb = _replay(args.symbol, args.tf_b, args.start, end, args.capital)

    if args.expect_a_trades is not None and len(ta) != args.expect_a_trades:
        raise SystemExit(f"leg A made {len(ta)} trades, not the documented {args.expect_a_trades}.")

    ha, bad_a = _holds(ta)
    hb, bad_b = _holds(tb)
    if not ha or not hb:
        raise SystemExit("one leg produced no usable trades — nothing to compare.")
    if bad_a or bad_b:
        print(f"  ⚠ dropped {bad_a} A / {bad_b} B trades with no usable entry/exit clock")

    ma, mb = _minutes(ha), _minutes(hb)

    same = opp = 0.0
    paired_a, paired_b = set(), set()
    gaps = []
    for i, a in enumerate(ha):
        for j, b in enumerate(hb):
            ov = _overlap_ms(a, b)
            if ov <= 0:
                continue
            paired_a.add(i)
            paired_b.add(j)
            if a[0] == b[0]:
                same += ov / _MIN
            else:
                opp += ov / _MIN
    # Entry proximity is asked of EVERY same-direction pair of trades, not only the ones that
    # overlapped in time: two legs can read one structure break and enter minutes apart while the
    # faster one is already out before the slower one fills. Restricting to overlaps would score
    # exactly that case as independence.
    for a in ha:
        for b in hb:
            if a[0] == b[0]:
                gaps.append(abs(a[1] - b[1]) / _MIN)
    close = [g for g in gaps if g <= args.cluster_min]

    print()
    print(f"{'':<26}{'A ' + args.tf_a + 'm':>14}{'B ' + args.tf_b + 'm':>14}")
    print("-" * 54)
    print(f"{'trades':<26}{len(ha):>14}{len(hb):>14}")
    print(f"{'total R':<26}{sum(h[3] for h in ha):>+14.2f}{sum(h[3] for h in hb):>+14.2f}")
    print(f"{'in-market hours':<26}{ma / 60:>14,.0f}{mb / 60:>14,.0f}")
    print(f"{'trades sharing a moment':<26}{len(paired_a):>14}{len(paired_b):>14}")
    print(
        f"{'  as % of its trades':<26}{len(paired_a) / len(ha) * 100:>13.1f}%"
        f"{len(paired_b) / len(hb) * 100:>13.1f}%"
    )

    tot = same + opp
    print()
    print(
        f"shared in-market time      {tot / 60:,.0f} hours "
        f"({tot / ma * 100:.1f}% of A's, {tot / mb * 100:.1f}% of B's)"
    )
    print(f"  SAME direction           {same / 60:,.0f} hours  — one idea carried at 2x risk")
    print(f"  opposite direction       {opp / 60:,.0f} hours  — partially hedged")

    print()
    print(f"same-direction entry proximity ({len(gaps):,} pairs)")
    print(
        f"  within {args.cluster_min} minutes    {len(close):,}   <- the same-structure-break test"
    )
    if close:
        print(f"  closest pair             {min(close):,.0f} minutes apart")

    ra, rb = _monthly_r(ha), _monthly_r(hb)
    keys = sorted(set(ra) | set(rb))
    both = sorted(set(ra) & set(rb))
    xs_all = [ra.get(k, 0.0) for k in keys]
    ys_all = [rb.get(k, 0.0) for k in keys]
    r_all = _pearson(xs_all, ys_all)
    r_both = _pearson([ra[k] for k in both], [rb[k] for k in both])
    down = sum(1 for k in both if ra[k] < 0 and rb[k] < 0)
    print()
    print(f"monthly R correlation      {r_all:+.3f} over {len(keys)} months either traded")
    if r_both is not None:
        print(f"                           {r_both:+.3f} over the {len(both)} months BOTH traded")
    print(f"  months both negative     {down} of {len(both)}")

    print()
    print("  Read the SAME-direction shared hours and the entry proximity together: two legs of")
    print("  one move do not enter the same way minutes apart. A high monthly correlation is the")
    print("  quieter failure — it means they lose in the same months even when never both in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
