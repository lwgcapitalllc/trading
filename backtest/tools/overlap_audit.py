#!/usr/bin/env python3
"""overlap_audit.py — do two strategies actually trade DIFFERENT legs of the move?

`CLAUDE.md` → *Trading Philosophy* says the suite is carved up by LEG, not by signal:
A+ fades the reversal, B-LEG catches the late retrace of an SOS, and "by construction
they should not be in the market on the same swing at the same time." **That is design
intent, and it has never been measured.** It is also the load-bearing assumption under
the whole portfolio argument — if two bots fire on the same structure break in the same
direction, they are not two strategies diversifying an account, they are one position at
2x the size, and every drawdown estimate built on stacking them is wrong.

This tool measures it. It replays two strategies over ONE bar frame and answers:

  1. **How much of each bot's in-market time is shared with the other**, split by
     SAME direction (doubled risk on one idea) vs OPPOSITE (a partial hedge).
  2. **How many trades pair up** — a bot's trade "overlaps" if it shares one bar with
     any trade of the other.
  3. **Entry proximity** — for each same-direction pair, how many bars apart the two
     entries were. This is the direct test of the same-structure-break hypothesis: two
     bots reading one break fire close together, two bots reading different legs do not.
  4. **What one account would have carried** — bars at 1x vs 2x risk, and the peak.
  5. **Monthly R correlation** — whether the two return streams move together at all.

⚠ **Two things this deliberately does NOT do.**

It does not net the two bots into a combined equity curve. Each strategy sizes itself
off its OWN equity (`self_sizing`), so running both on one account changes both bots'
position sizes from the first shared trade onward, and the result would be a third thing
neither bot is. The account-level allocator (G10) is the object that answers that
question, and it is unbuilt. What is measured here is the INPUT to that decision: how
often the allocator would have had anything to arbitrate.

It does not treat "no overlap" as a clean bill of health. Two strategies can be flat at
different moments and still lose in the same months for the same reason — everything
here reads one structure stream on one instrument. That is what the monthly correlation
is for, and it is the weaker of the two signals.

Usage:
    python backtest/tools/overlap_audit.py
    python backtest/tools/overlap_audit.py --a mpc_sos_fade --b mpc_bleg --start 2020-01-01
    python backtest/tools/overlap_audit.py --out /tmp/overlap
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import importlib
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Same registry shape as run_report.py — a package that declares LAB_STRATEGY is runnable
# here for free. Keep the two in step when a third Python strategy lands.
_STRATEGIES = {
    "mpc_sos_fade": "strategies.python.mpc_sos_fade",
    "mpc_bleg": "strategies.python.mpc_bleg",
}

# Same-direction entries this many bars apart or fewer are reported as a CLUSTER — the
# proxy for "both bots read the same structure break". 16 bars = 4 hours on M15, which is
# comfortably wider than the retrace a B-LEG waits for after an A+ entry would have fired.
_CLUSTER_BARS = 16


class Hold:
    """One bot holding one position, as a half-open bar range plus its direction.

    Half-open [entry, exit) deliberately, and applied identically to both sides: a bot is
    exposed on the bars it is IN the trade, and the exit bar is the one it leaves on. The
    convention only has to be consistent for the comparison to be honest — using inclusive
    ranges shifts every count by the same one bar per trade on both sides.
    """

    __slots__ = ("dir", "start", "end", "r", "idx")

    def __init__(self, direction: int, start: int, end: int, r: float, idx: int):
        self.dir = direction
        self.start = start
        self.end = max(end, start + 1)   # a same-bar entry/exit still occupies its bar
        self.r = r
        self.idx = idx


def _holds(trades) -> list[Hold]:
    return [Hold(t.dir, t.entry_index, t.exit_index, t.r, i) for i, t in enumerate(trades)]


def _occupancy(holds: list[Hold], n_bars: int) -> list[int]:
    """Per-bar direction: +1 long, -1 short, 0 flat.

    Each bot here runs ONE position slot, so a bar can only carry one direction. If a
    strategy ever gains concurrency this collapses two positions into one cell and would
    understate its own exposure — assert rather than silently mis-measure.
    """
    occ = [0] * n_bars
    for h in holds:
        for i in range(h.start, min(h.end, n_bars)):
            if occ[i] != 0:
                raise SystemExit(
                    f"bar {i} is held by two positions of the same strategy — this tool "
                    f"assumes one position slot per bot. Re-write _occupancy before trusting it."
                )
            occ[i] = h.dir
    return occ


def _replay(key: str, df, warmup: int, capital: float, overrides: dict):
    mod = importlib.import_module(_STRATEGIES[key])
    spec = mod.LAB_STRATEGY
    StrategyCls, ConfigCls = spec["strategy"], spec["config"]
    cfg = ConfigCls(fill_model="bar", symbol="XAUUSD")
    if overrides:
        import dataclasses
        cfg = dataclasses.replace(cfg, **overrides)
    strat = StrategyCls(config=cfg, initial_capital=capital)
    print(f"  replaying {spec['name']} (warmup {warmup}) ...", flush=True)
    strat.run(df, warmup=warmup)
    return strat


def _pct(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:.1f}%" if whole else "—"


def _monthly_r(trades, df) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for t in trades:
        ts = df.index[min(t.entry_index, len(df.index) - 1)]
        out[f"{ts.year}-{ts.month:02d}"] += t.r
    return dict(out)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Plain Pearson r. Returns None rather than 0.0 when it is undefined — a flat series
    is not an uncorrelated one, and reporting 0.0 for "cannot be computed" is exactly the
    absence-as-value trap this repo has been bitten by."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = sum((a - mx) ** 2 for a in xs) ** 0.5
    dy = sum((b - my) ** 2 for b in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a", default="mpc_sos_fade", choices=sorted(_STRATEGIES))
    ap.add_argument("--b", default="mpc_bleg", choices=sorted(_STRATEGIES))
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15")
    ap.add_argument("--start", default=None,
                    help="YYYY-MM-DD (default: the broker's measured earliest bar at this tf)")
    ap.add_argument("--end", default=None)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--cluster-bars", type=int, default=_CLUSTER_BARS,
                    help="same-direction entries this close are reported as one cluster")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if args.a == args.b:
        raise SystemExit("--a and --b must be different strategies")

    from backtest.data.history import floor_for
    from backtest.data.source import BarSource

    start = args.start
    if start is None:
        fl = floor_for(args.symbol, args.tf)
        if fl is None:
            raise SystemExit(
                f"cannot measure the broker's earliest {args.tf}m history for {args.symbol}. "
                f"Pass --start explicitly rather than guessing one.")
        start = fl.isoformat()
    end = args.end or dt.date.today().isoformat()

    print(f"loading {args.symbol} {args.tf}m  {start} -> {end} ...", flush=True)
    df = BarSource().load(args.symbol, args.tf, start, end)
    if df.empty:
        print("no bars returned")
        return 1
    n = len(df)
    print(f"  {n:,} bars  {df.index[0]} -> {df.index[-1]}", flush=True)

    sa = _replay(args.a, df, args.warmup, args.capital, {})
    sb = _replay(args.b, df, args.warmup, args.capital, {})

    ta, tb = sa.execution.trades, sb.execution.trades
    ha, hb = _holds(ta), _holds(tb)
    oa, ob = _occupancy(ha, n), _occupancy(hb, n)

    in_a = sum(1 for v in oa if v)
    in_b = sum(1 for v in ob if v)
    both = same = opp = 0
    for x, y in zip(oa, ob):
        if x and y:
            both += 1
            if x == y:
                same += 1
            else:
                opp += 1

    # Which trades pair up.
    pairs: list[tuple[Hold, Hold, int]] = []
    for x in ha:
        for y in hb:
            if x.start < y.end and y.start < x.end:
                pairs.append((x, y, min(x.end, y.end) - max(x.start, y.start)))
    a_paired = {p[0].idx for p in pairs}
    b_paired = {p[1].idx for p in pairs}
    same_dir_pairs = [p for p in pairs if p[0].dir == p[1].dir]

    # Entry proximity — the same-structure-break test. For every A trade, the nearest B
    # entry in the SAME direction, in bars (signed: negative = B entered first).
    clusters = []
    for x in ha:
        best = None
        for y in hb:
            if y.dir != x.dir:
                continue
            d = y.start - x.start
            if best is None or abs(d) < abs(best[1]):
                best = (y, d)
        if best is not None and abs(best[1]) <= args.cluster_bars:
            clusters.append((x, best[0], best[1]))

    ma, mb = _monthly_r(ta, df), _monthly_r(tb, df)
    months = sorted(set(ma) | set(mb))
    xs = [ma.get(m, 0.0) for m in months]
    ys = [mb.get(m, 0.0) for m in months]
    corr = _pearson(xs, ys)
    both_traded = [m for m in months if m in ma and m in mb]

    # ── report ──
    w = 100
    print("\n" + "=" * w)
    print(f"OVERLAP AUDIT   {args.a}  vs  {args.b}"
          f"   {df.index[0].date()} -> {df.index[-1].date()}   {n:,} bars")
    print("=" * w)

    print(f"\n{args.a:<18} {len(ta):4d} trades   {sum(t.r for t in ta):8.2f}R"
          f"   in the market {in_a:6,d} bars ({_pct(in_a, n)} of all bars)")
    print(f"{args.b:<18} {len(tb):4d} trades   {sum(t.r for t in tb):8.2f}R"
          f"   in the market {in_b:6,d} bars ({_pct(in_b, n)} of all bars)")

    print("\n--- BARS BOTH BOTS HELD A POSITION ---")
    print(f"  both in the market   {both:6,d} bars"
          f"   = {_pct(both, in_a)} of {args.a}'s hold time"
          f", {_pct(both, in_b)} of {args.b}'s")
    print(f"    SAME direction     {same:6,d} bars  ({_pct(same, both)} of the overlap)"
          f"   <- doubled risk on one idea")
    print(f"    OPPOSITE direction {opp:6,d} bars  ({_pct(opp, both)} of the overlap)"
          f"   <- partially hedged")

    print("\n--- TRADES THAT OVERLAP AT ALL ---")
    print(f"  {args.a:<18} {len(a_paired):4d} of {len(ta):4d} trades ({_pct(len(a_paired), len(ta))})"
          f" share a bar with a {args.b} trade")
    print(f"  {args.b:<18} {len(b_paired):4d} of {len(tb):4d} trades ({_pct(len(b_paired), len(tb))})"
          f" share a bar with a {args.a} trade")
    print(f"  overlapping PAIRS    {len(pairs):4d}   of which {len(same_dir_pairs)} are same-direction")

    print(f"\n--- SAME STRUCTURE BREAK? (same-direction entries <= {args.cluster_bars} bars apart) ---")
    if clusters:
        gaps = [abs(c[2]) for c in clusters]
        print(f"  {len(clusters)} of {len(ta)} {args.a} trades have a same-direction {args.b} entry"
              f" within {args.cluster_bars} bars")
        print(f"  gap in bars: min {min(gaps)}  median {statistics.median(gaps):.0f}  max {max(gaps)}")
        for x, y, d in clusters[:15]:
            side = "long " if x.dir > 0 else "short"
            when = df.index[x.start]
            print(f"    {when}  {side}  {args.b} entered {d:+d} bars"
                  f"   A {x.r:+6.2f}R   B {y.r:+6.2f}R")
        if len(clusters) > 15:
            print(f"    ... and {len(clusters) - 15} more (see clusters.csv)")
    else:
        print(f"  NONE. No {args.a} trade has a same-direction {args.b} entry within"
              f" {args.cluster_bars} bars.")

    print("\n--- WHAT ONE ACCOUNT WOULD HAVE CARRIED ---")
    print(f"  bars at 1 position   {in_a + in_b - 2 * both:6,d}")
    print(f"  bars at 2 positions  {both:6,d}   (peak concurrent positions: {2 if both else 1})")
    print(f"  ⚠ each bot sizes off its OWN equity, so 2 positions is 2x the per-trade risk %.")
    print(f"    At exec_risk_pct = 10 that is 20% of the account at risk on {both:,} bars,"
          f" {same:,} of them on the SAME side.")

    print("\n--- MONTHLY R CORRELATION ---")
    print(f"  months with any trade: {len(months)}  (both traded in {len(both_traded)})")
    if corr is None:
        print("  correlation: not computable (a series is flat or too short)")
    else:
        print(f"  Pearson r = {corr:+.3f} over {len(months)} months")
        print("  ⚠ months where only one bot traded contribute a 0 for the other, which pulls r "
              "toward 0.\n    Read it as a floor on how together they move, not a precise figure.")

    # ── files ──
    out = Path(args.out) if args.out else _ROOT / "backtest" / "reports" / (
        "overlap_" + dt.datetime.now().strftime("%Y%m%dT%H%M%S"))
    out.mkdir(parents=True, exist_ok=True)

    with open(out / "pairs.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["a_entry_utc", "a_dir", "a_r", "b_entry_utc", "b_dir", "b_r",
                     "shared_bars", "same_direction", "entry_gap_bars"])
        for x, y, shared in sorted(pairs, key=lambda p: p[0].start):
            wr.writerow([df.index[x.start].isoformat(), x.dir, round(x.r, 3),
                         df.index[y.start].isoformat(), y.dir, round(y.r, 3),
                         shared, x.dir == y.dir, y.start - x.start])

    with open(out / "clusters.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["a_entry_utc", "dir", "gap_bars", "a_r", "b_r"])
        for x, y, d in clusters:
            wr.writerow([df.index[x.start].isoformat(), x.dir, d, round(x.r, 3), round(y.r, 3)])

    with open(out / "monthly.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["month", f"{args.a}_r", f"{args.b}_r"])
        for m in months:
            wr.writerow([m, round(ma.get(m, 0.0), 3), round(mb.get(m, 0.0), 3)])

    print(f"\nwrote {out}/pairs.csv, clusters.csv, monthly.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
