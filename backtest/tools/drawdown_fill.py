#!/usr/bin/env python3
"""drawdown_fill.py — does a second leg put equity on the board while the FIRST one is bleeding?

Aaron's question (2026-08-24): *"I need more trades to help increase the equity in the drawdown
periods — can this do that?"*

**It is a different question from "is this leg profitable", and a leg can fail one and pass the
other.** A marginal leg that earns during the main leg's flat spells is worth more than a better
leg that earns at the same time, because what it buys is a shorter and shallower drawdown rather
than a bigger number at the end. Total R cannot answer it — only the TIMING can.

So this tool does three things and only three:

  1. Cuts the FIRST leg's history into drawdown EPISODES (peak -> trough -> back to peak) and
     reports what the second leg made inside each one.
  2. Correlates the two legs month by month, because a leg that helps in four episodes and is
     correlated overall was lucky in four episodes.
  3. Compounds both on ONE account at their own risk levels and compares the drawdown against
     the first leg alone — which is the only form of the answer that is actually decision-useful.

⚠ **THE COMPOUNDED ROW IS AN APPROXIMATION AND `backtest/portfolio/run_stack` IS NOT.** Trades are
sequenced by EXIT and compounded one after another, so two positions open at once are billed as if
they were consecutive. That understates the true concurrent exposure. `run_stack` replays both legs
against one balance with one risk budget and is what a real answer needs; this is the cheap version
that says whether the real one is worth running. **Do not quote the compounded row as the stack's
result.** ⚠ Also: the LIVE allocator does not exist (docs/LIVE_TRADING_PIPELINE.md -> G10), so a
shared-risk figure describes the lab, not what two bots would do on the live box.

⚠ **Compare R, never dollars** (rule 6) — that is why the episode table is in R and the dollar
column is absent rather than merely small.

Usage:
    python3 backtest/tools/drawdown_fill.py
    python3 backtest/tools/drawdown_fill.py --risk-a 10 --risk-b 2.5
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

#: The second leg, at the best configuration `ob_leg_replay.py` found. Named here rather than
#: passed in, so the run is reproducible and the config travels with the finding.
_LEG_B = {
    "exec_poi_source": "Order block (no FVG)",
    "exec_fib_nearest": False,
    "exec_deep_fib": True,
    "exec_fvg_deep_only": False,
}


def _month(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m")


def _episodes(trades, min_depth: float = 2.0):
    """Drawdown episodes of one leg: (start_ms, trough_ms, end_ms, depth_R, trades_in_it).

    An episode opens the trade after a new equity peak and closes when the running total gets
    back to that peak. An episode still open at the end of the window is reported with
    `end_ms=None` — it has not recovered, which is a fact about the leg and not a missing value.
    """
    ts = sorted(trades, key=lambda t: t.exit_ms)
    run = peak = 0.0
    peak_ms = ts[0].entry_ms if ts else 0
    out, open_ep = [], None
    for t in ts:
        run += t.r
        if run >= peak:
            if open_ep is not None:
                start, trough_ms, depth, n = open_ep
                if -depth >= min_depth:
                    out.append((start, trough_ms, t.exit_ms, -depth, n))
                open_ep = None
            peak, peak_ms = run, t.exit_ms
            continue
        gap = run - peak
        if open_ep is None:
            open_ep = (peak_ms, t.exit_ms, gap, 1)
        else:
            start, trough_ms, depth, n = open_ep
            open_ep = (start, t.exit_ms if gap < depth else trough_ms, min(depth, gap), n + 1)
    if open_ep is not None:
        start, trough_ms, depth, n = open_ep
        if -depth >= min_depth:
            out.append((start, trough_ms, None, -depth, n))
    return out


def _curve(pairs, risk):
    """Compound one sequence of (ms, r) at a fixed fraction. Returns (end, worst drawdown)."""
    eq = hi = 1.0
    dd = 0.0
    for _ms, r in pairs:
        eq *= 1 + risk / 100.0 * r
        if eq <= 0:
            return 0.0, -1.0
        hi = max(hi, eq)
        dd = min(dd, eq / hi - 1)
    return eq, dd


def _underwater(pairs, risk) -> float:
    """Total DAYS the compounded account spent below a previous equity high.

    The headline drawdown is a depth and this is a duration, and they answer different halves of
    "help me through the flat spells". A leg can deepen the worst dip and still get the account
    back to a new high months sooner — or add return while leaving the account under water
    exactly as long, which is the case worth catching.
    """
    eq = hi = 1.0
    under = 0.0
    prev_ms = pairs[0][0] if pairs else 0
    for ms, r in pairs:
        if eq < hi:
            under += (ms - prev_ms) / 86_400_000
        prev_ms = ms
        eq *= 1 + risk / 100.0 * r
        if eq <= 0:
            return under
        hi = max(hi, eq)
    return under


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-08-06")
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--risk-a", type=float, default=10.0, help="A+'s risk per trade, %%")
    ap.add_argument("--risk-b", type=float, default=2.5, help="the second leg's risk per trade, %%")
    ap.add_argument(
        "--min-depth",
        type=float,
        default=2.0,
        help="smallest drawdown, in R, worth calling an episode",
    )
    args = ap.parse_args(argv)

    sys.path.insert(0, str(_ROOT / "backtest" / "tools"))
    from ob_leg_replay import _profile, _replay

    from backtest.data.source import BarSource

    print(f"loading {args.symbol} {args.tf}m  {args.start} -> {args.end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, args.start, args.end)
    if df.empty:
        print("no bars — is the MT5 agent tunnel up on localhost:8766?")
        return 1
    prof = _profile()
    print("replaying A+ ...", flush=True)
    a = _replay(df, args.warmup, args.capital, prof)
    print("replaying the second leg ...", flush=True)
    b = _replay(df, args.warmup, args.capital, prof, **_LEG_B)

    W = 96
    print("\n" + "=" * W)
    print(
        f"DOES THE SECOND LEG PAY DURING A+'s DRAWDOWNS?   {df.index[0].date()} -> "
        f"{df.index[-1].date()}"
    )
    print(
        f"  A+ {len(a)} trades {sum(t.r for t in a):+.1f}R    "
        f"second leg {len(b)} trades {sum(t.r for t in b):+.1f}R"
    )
    print("=" * W)

    eps = _episodes(a, args.min_depth)
    print(
        f"\n1. A+'s DRAWDOWN EPISODES ({args.min_depth:.0f}R or deeper), and what the second "
        f"leg did inside each"
    )
    print(
        f"   {'from':<11}{'to':<11}{'days':>6}{'A+ R':>8}{'A+ trades':>11}"
        f"{'leg-2 R':>9}{'leg-2 trades':>14}"
    )
    helped = hurt = 0
    tot_b_in = 0.0
    for start, _trough, end, depth, n in eps:
        stop = end if end is not None else int(df.index[-1].timestamp() * 1000)
        inside = [t for t in b if start <= t.exit_ms <= stop]
        rb = sum(t.r for t in inside)
        tot_b_in += rb
        if rb > 0:
            helped += 1
        elif rb < 0:
            hurt += 1
        d0 = datetime.fromtimestamp(start / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        d1 = (
            datetime.fromtimestamp(end / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            if end
            else "not yet"
        )
        days = (stop - start) / 86_400_000
        print(f"   {d0:<11}{d1:<11}{days:>6.0f}{-depth:>8.1f}{n:>11}{rb:>9.1f}{len(inside):>14}")
    print(
        f"\n   the second leg was POSITIVE in {helped} of {len(eps)} episodes, negative in "
        f"{hurt}, total {tot_b_in:+.1f}R inside them"
    )
    print(
        f"   (it made {sum(t.r for t in b):+.1f}R over the whole window, so "
        f"{tot_b_in:+.1f}R of that landed while A+ was under water)"
    )

    print("\n2. MONTH BY MONTH — a leg that helps in a few episodes and correlates overall")
    print("   was lucky in a few episodes.")
    ma, mb = defaultdict(float), defaultdict(float)
    for t in a:
        ma[_month(t.exit_ms)] += t.r
    for t in b:
        mb[_month(t.exit_ms)] += t.r
    months = sorted(set(ma) | set(mb))
    xa = [ma.get(m, 0.0) for m in months]
    xb = [mb.get(m, 0.0) for m in months]
    n = len(months)
    mean_a, mean_b = sum(xa) / n, sum(xb) / n
    cov = sum((p - mean_a) * (q - mean_b) for p, q in zip(xa, xb))
    va = sum((p - mean_a) ** 2 for p in xa)
    vb = sum((q - mean_b) ** 2 for q in xb)
    corr = cov / (va * vb) ** 0.5 if va and vb else float("nan")
    down = [m for m in months if ma.get(m, 0.0) < 0]
    b_in_down = sum(mb.get(m, 0.0) for m in down)
    b_pos_in_down = sum(1 for m in down if mb.get(m, 0.0) > 0)
    print(f"   {n} months   correlation of monthly R: {corr:+.2f}")
    print(
        f"   A+ was DOWN in {len(down)} months; the second leg made {b_in_down:+.1f}R across "
        f"them and was positive in {b_pos_in_down} of them"
    )
    flat = [m for m in months if ma.get(m, 0.0) == 0]
    print(
        f"   A+ traded NOTHING in {len(flat)} months; the second leg made "
        f"{sum(mb.get(m, 0.0) for m in flat):+.1f}R in those"
    )

    print(f"\n3. BOTH ON ONE ACCOUNT — A+ at {args.risk_a}%, the second leg at {args.risk_b}%")
    print("   ⚠ sequenced by exit and compounded consecutively; see the module note. This says")
    print("     whether run_stack is worth running, it does not replace it.")
    pa = sorted(((t.exit_ms, t.r) for t in a))
    pb = sorted(((t.exit_ms, t.r) for t in b))
    print(f"   {'':<30}{'end':>10}{'worst drawdown':>16}{'days under water':>18}")
    solo_e, solo_d = _curve(pa, args.risk_a)
    print(f"   {'A+ alone':<30}{solo_e:>9.2f}x{solo_d:>15.0%}{_underwater(pa, args.risk_a):>17.0f}")
    # Swept rather than shown at one weight: the question is not "does 2.5% help" but "is there
    # ANY weight at which a second leg shortens the flat spells instead of just adding leverage".
    for rb in (0.5, 1.0, 2.5, 5.0, args.risk_b):
        both = sorted([(ms, r) for ms, r in pa] + [(ms, r * rb / args.risk_a) for ms, r in pb])
        e, d = _curve(both, args.risk_a)
        print(
            f"   {f'+ the second leg at {rb}%':<30}{e:>9.2f}x{d:>15.0%}"
            f"{_underwater(both, args.risk_a):>17.0f}"
        )
    print("\n   'days under water' is the total time the account sat below a previous high —")
    print("   the thing 'more trades during the drawdown' is actually asking to shrink.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
