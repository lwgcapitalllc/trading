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
    "mpc_extreme_leg": "strategies.python.mpc_extreme_leg",
}

# Same-direction entries this far apart or less are reported as a CLUSTER — the proxy for
# "both bots read the same structure break". Four hours is comfortably wider than the retrace
# a B-LEG waits for after an A+ entry would have fired.
#
# ⚠ **IT IS A DURATION, NOT A BAR COUNT, AND THAT CHANGED ON 2026-09-01.** It was 16 bars,
# which meant four hours only while both bots shared a 15-minute frame. Two bots on different
# frames make a bar count mean two different things at once, and the flag would have silently
# narrowed the window to 80 minutes the first time one of them ran on 5-minute bars. The
# 15-minute case still resolves to exactly 16 units, so nothing already measured moved.
_CLUSTER_MINUTES = 240


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
        self.end = max(end, start + 1)  # a same-bar entry/exit still occupies its bar
        self.r = r
        self.idx = idx


def _holds(trades, df, grid) -> list[Hold]:
    """Map one bot's trades onto the SHARED grid.

    🔴 **THE TWO BOTS NEED NOT BE ON THE SAME BAR FRAME, AND BAR INDICES CANNOT EXPRESS THAT.**
    Bar 400 of a 15-minute frame and bar 400 of a 5-minute frame are eleven hours apart, so a
    comparison built on indices silently compares two different afternoons. Every hold is
    therefore converted to its own bar's TIMESTAMPS and then located on the finer frame's own
    index, which is the one grid both frames' bars land on.

    ⚠ **When the two frames are the SAME, the grid IS that frame and this is the identity** —
    every number the tool produced before this existed reproduces exactly. That was the
    constraint the design had to meet: the A+/B-LEG result is quoted in `CLAUDE.md`.

    ⚠ The half-open [entry, exit) convention is unchanged and still applies to both sides. A
    trade that opens and closes on ONE of its own bars occupies that bar's whole width on the
    grid — `grid.span` — rather than a single fine unit, or a 15-minute bot would report a
    third of its real exposure against a 5-minute one.
    """
    idx = df.index
    last = len(idx) - 1
    # Once, not per trade: it is a diff over the whole index, and a 5-minute frame over eight
    # years is half a million rows. The first version called it inside the loop.
    span = grid.span(df)
    out: list[Hold] = []
    for i, t in enumerate(trades):
        start = grid.unit(idx[min(t.entry_index, last)])
        end = grid.unit(idx[min(t.exit_index, last)])
        out.append(Hold(t.dir, start, max(end, start + span), t.r, i))
    return out


class Grid:
    """The shared time axis — the FINER of the two frames' own bar index.

    A regular clock grid was the obvious alternative and is wrong here: it would count the
    weekend as bars, so `in the market X% of all bars` would fall by a third and every figure
    already recorded against this tool would move. The finer frame's own index carries only
    the bars the market actually printed, and the coarser frame's bar opens are a subset of it.
    """

    def __init__(self, df):
        self.index = df.index
        self._pos = {t.value: i for i, t in enumerate(df.index)}
        self.minutes = int(df.index.to_series().diff().min().total_seconds() // 60)
        # How many bar opens the coarse frame held that the fine one does not. Counted rather
        # than raised, and PRINTED rather than counted in silence — see `unit`.
        self.misses = 0

    def __len__(self):
        return len(self.index)

    def unit(self, ts) -> int:
        """Where this bar's open sits on the grid.

        ⚠ A timestamp the grid does not hold falls to the NEXT grid bar rather than raising —
        the fine feed can be missing a bar the coarse one has, and dying on one absent
        five-minute candle would throw away an eight-year replay. But it is COUNTED and the
        count is printed once at the end of the run, because the silent version of this is the
        trap this repo keeps re-learning: a hole in the feed and a clean feed would produce
        the same confident output, and the reader has no way to tell which one they got.
        """
        hit = self._pos.get(ts.value)
        if hit is not None:
            return hit
        self.misses += 1
        return int(self.index.searchsorted(ts))

    def span(self, df) -> int:
        """How many grid units one bar of `df` covers."""
        m = int(df.index.to_series().diff().min().total_seconds() // 60)
        return max(1, m // self.minutes)


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


def _replay(key: str, df, warmup: int, capital: float, overrides: dict, symbol: str):
    mod = importlib.import_module(_STRATEGIES[key])
    spec = mod.LAB_STRATEGY
    StrategyCls, ConfigCls = spec["strategy"], spec["config"]
    # ⚠ Only the fields this strategy DECLARES. `LAB_STRATEGY` is an open contract — a config
    # is not required to have a fill model or to name a symbol, and passing one that does not
    # exist is a TypeError at construction rather than anything a reader could act on.
    wanted = {"fill_model": "bar", "symbol": symbol}
    have = getattr(ConfigCls, "__dataclass_fields__", {})
    cfg = ConfigCls(**{k: v for k, v in wanted.items() if k in have})
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
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--a", default="mpc_sos_fade", choices=sorted(_STRATEGIES))
    ap.add_argument("--b", default="mpc_bleg", choices=sorted(_STRATEGIES))
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="15", help="the frame BOTH bots run on, unless overridden")
    # ⚠ A bot's frame is not a preference — `mpc_extreme_leg` measures its trigger on 5-minute
    # bars and builds its 15-minute half in code, so handing it a 15-minute frame makes the
    # trigger and the target the same series and there is no trade left to take.
    ap.add_argument("--tf-a", default=None, help="override the frame for --a")
    ap.add_argument("--tf-b", default=None, help="override the frame for --b")
    ap.add_argument(
        "--start",
        default=None,
        help="YYYY-MM-DD (default: the broker's measured earliest bar at this tf)",
    )
    ap.add_argument("--end", default=None)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument(
        "--cluster-minutes",
        type=int,
        default=_CLUSTER_MINUTES,
        help="same-direction entries this close in TIME are reported as one cluster",
    )
    ap.add_argument(
        "--server",
        default=None,
        help="the broker whose cached bars to read, e.g. VantageMarkets-Demo. Without it the "
        "bar source asks whichever MT5 terminal is attached, which needs the SSH tunnel up — "
        "so a re-run with the app down fails at the fetch rather than reading the cache it "
        "already holds. Name the server this audit was measured on.",
    )
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if args.a == args.b:
        raise SystemExit("--a and --b must be different strategies")

    from backtest.data.history import floor_for
    from backtest.data.source import BarSource

    tf_a = args.tf_a or args.tf
    tf_b = args.tf_b or args.tf

    # ⚠ The window is bounded by the SHALLOWEST frame either bot needs. A start date the
    # 15-minute feed can serve and the 5-minute one cannot is a run that dies at the fetch,
    # after both replays have been queued.
    start = args.start
    if start is None:
        floors = []
        for tf in {tf_a, tf_b}:
            # ⚠ `floor_for` measures the ATTACHED terminal, so with the app down it cannot
            # answer and the refusal below says to pass `--start`. That is right — a history
            # floor is a fact about a broker and there is no honest default to substitute.
            fl = floor_for(args.symbol, tf)
            if fl is None:
                raise SystemExit(
                    f"cannot measure the broker's earliest {tf}m history for {args.symbol}. "
                    f"Pass --start explicitly rather than guessing one."
                )
            floors.append(fl)
        start = max(floors).isoformat()
    end = args.end or dt.date.today().isoformat()

    frames: dict[str, object] = {}
    for tf in sorted({tf_a, tf_b}, key=int):
        print(f"loading {args.symbol} {tf}m  {start} -> {end} ...", flush=True)
        d = BarSource(server=args.server).load(args.symbol, tf, start, end)
        if d.empty:
            print(f"no {tf}m bars returned")
            return 1
        print(f"  {len(d):,} bars  {d.index[0]} -> {d.index[-1]}", flush=True)
        frames[tf] = d

    df_a, df_b = frames[tf_a], frames[tf_b]
    # The finer frame is the grid — see `Grid`. `min` on the timeframe as an INT, because
    # "5" < "15" is false as strings and the grid would silently be the coarser one.
    grid = Grid(frames[min(frames, key=int)])
    n = len(grid)

    sa = _replay(args.a, df_a, args.warmup, args.capital, {}, args.symbol)
    sb = _replay(args.b, df_b, args.warmup, args.capital, {}, args.symbol)

    ta, tb = sa.execution.trades, sb.execution.trades
    ha, hb = _holds(ta, df_a, grid), _holds(tb, df_b, grid)
    oa, ob = _occupancy(ha, n), _occupancy(hb, n)
    cluster_units = max(1, args.cluster_minutes // grid.minutes)

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
        if best is not None and abs(best[1]) <= cluster_units:
            clusters.append((x, best[0], best[1]))

    ma, mb = _monthly_r(ta, df_a), _monthly_r(tb, df_b)
    months = sorted(set(ma) | set(mb))
    xs = [ma.get(m, 0.0) for m in months]
    ys = [mb.get(m, 0.0) for m in months]
    corr = _pearson(xs, ys)
    both_traded = [m for m in months if m in ma and m in mb]

    # ── report ──
    w = 100
    print("\n" + "=" * w)
    print(
        f"OVERLAP AUDIT   {args.a} ({tf_a}m)  vs  {args.b} ({tf_b}m)"
        f"   {grid.index[0].date()} -> {grid.index[-1].date()}"
        f"   {n:,} bars of {grid.minutes}m"
    )
    print("=" * w)

    # Said BEFORE the numbers, not in a footnote. A gappy fine feed shifts a coarse bot's
    # holds onto the next bar that exists, which is the safe direction but is not free — and
    # a reader who meets the caveat after the conclusion has already formed the conclusion.
    if grid.misses:
        print(
            f"\n⚠ {grid.misses:,} bar opens on a coarser frame have no {grid.minutes}m bar of "
            f"their own and were placed on the NEXT one that exists. The fine feed has holes; "
            f"treat the bar counts below as approximate to that extent."
        )

    print(
        f"\n{args.a:<18} {len(ta):4d} trades   {sum(t.r for t in ta):8.2f}R"
        f"   in the market {in_a:6,d} bars ({_pct(in_a, n)} of all bars)"
    )
    print(
        f"{args.b:<18} {len(tb):4d} trades   {sum(t.r for t in tb):8.2f}R"
        f"   in the market {in_b:6,d} bars ({_pct(in_b, n)} of all bars)"
    )

    print("\n--- BARS BOTH BOTS HELD A POSITION ---")
    print(
        f"  both in the market   {both:6,d} bars"
        f"   = {_pct(both, in_a)} of {args.a}'s hold time"
        f", {_pct(both, in_b)} of {args.b}'s"
    )
    print(
        f"    SAME direction     {same:6,d} bars  ({_pct(same, both)} of the overlap)"
        f"   <- doubled risk on one idea"
    )
    print(
        f"    OPPOSITE direction {opp:6,d} bars  ({_pct(opp, both)} of the overlap)"
        f"   <- partially hedged"
    )

    print("\n--- TRADES THAT OVERLAP AT ALL ---")
    print(
        f"  {args.a:<18} {len(a_paired):4d} of {len(ta):4d} trades ({_pct(len(a_paired), len(ta))})"
        f" share a bar with a {args.b} trade"
    )
    print(
        f"  {args.b:<18} {len(b_paired):4d} of {len(tb):4d} trades ({_pct(len(b_paired), len(tb))})"
        f" share a bar with a {args.a} trade"
    )
    print(
        f"  overlapping PAIRS    {len(pairs):4d}   of which {len(same_dir_pairs)} are same-direction"
    )

    print(
        f"\n--- SAME STRUCTURE BREAK? (same-direction entries <= {args.cluster_minutes} minutes apart) ---"
    )
    if clusters:
        gaps = [abs(c[2]) for c in clusters]
        print(
            f"  {len(clusters)} of {len(ta)} {args.a} trades have a same-direction {args.b} entry"
            f" within {args.cluster_minutes} minutes"
        )
        print(
            f"  gap in bars: min {min(gaps)}  median {statistics.median(gaps):.0f}  max {max(gaps)}"
        )
        for x, y, d in clusters[:15]:
            side = "long " if x.dir > 0 else "short"
            when = grid.index[x.start]
            print(
                f"    {when}  {side}  {args.b} entered {d:+d} bars"
                f"   A {x.r:+6.2f}R   B {y.r:+6.2f}R"
            )
        if len(clusters) > 15:
            print(f"    ... and {len(clusters) - 15} more (see clusters.csv)")
    else:
        print(
            f"  NONE. No {args.a} trade has a same-direction {args.b} entry within"
            f" {args.cluster_minutes} minutes."
        )

    print("\n--- WHAT ONE ACCOUNT WOULD HAVE CARRIED ---")
    print(f"  bars at 1 position   {in_a + in_b - 2 * both:6,d}")
    print(f"  bars at 2 positions  {both:6,d}   (peak concurrent positions: {2 if both else 1})")
    print("  ⚠ each bot sizes off its OWN equity, so 2 positions is 2x the per-trade risk %.")
    print(
        f"    At exec_risk_pct = 10 that is 20% of the account at risk on {both:,} bars,"
        f" {same:,} of them on the SAME side."
    )

    print("\n--- MONTHLY R CORRELATION ---")
    print(f"  months with any trade: {len(months)}  (both traded in {len(both_traded)})")
    if corr is None:
        print("  correlation: not computable (a series is flat or too short)")
    else:
        print(f"  Pearson r = {corr:+.3f} over {len(months)} months")
        print(
            "  ⚠ months where only one bot traded contribute a 0 for the other, which pulls r "
            "toward 0.\n    Read it as a floor on how together they move, not a precise figure."
        )

    # ── files ──
    out = (
        Path(args.out)
        if args.out
        else _ROOT
        / "backtest"
        / "reports"
        / ("overlap_" + dt.datetime.now().strftime("%Y%m%dT%H%M%S"))
    )
    out.mkdir(parents=True, exist_ok=True)

    with open(out / "pairs.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(
            [
                "a_entry_utc",
                "a_dir",
                "a_r",
                "b_entry_utc",
                "b_dir",
                "b_r",
                "shared_bars",
                "same_direction",
                "entry_gap_grid_bars",
            ]
        )
        for x, y, shared in sorted(pairs, key=lambda p: p[0].start):
            wr.writerow(
                [
                    grid.index[x.start].isoformat(),
                    x.dir,
                    round(x.r, 3),
                    grid.index[y.start].isoformat(),
                    y.dir,
                    round(y.r, 3),
                    shared,
                    x.dir == y.dir,
                    y.start - x.start,
                ]
            )

    with open(out / "clusters.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["a_entry_utc", "dir", "gap_grid_bars", "a_r", "b_r"])
        for x, y, d in clusters:
            wr.writerow([grid.index[x.start].isoformat(), x.dir, d, round(x.r, 3), round(y.r, 3)])

    with open(out / "monthly.csv", "w", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["month", f"{args.a}_r", f"{args.b}_r"])
        for m in months:
            wr.writerow([m, round(ma.get(m, 0.0), 3), round(mb.get(m, 0.0), 3)])

    print(f"\nwrote {out}/pairs.csv, clusters.csv, monthly.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
