#!/usr/bin/env python3
"""killzone_vwap_retest.py — price retests the session VWAP inside a window: does it trade
AWAY from it, does higher-timeframe TREND make that more likely, and which target is best?

The trade, as Aaron described it (2026-09-15):

  trigger  the FIRST bar in the window whose range reaches the VWAP from the side it opened
           on. The level is the VWAP as it stood after the PREVIOUS bar closed — known in
           advance, so a resting limit order could sit on it. No lookahead.
  entry    at the VWAP (the limit fill); long if price came down to it, short if up.
  trend    the canonical `engines/market_structure/` direction on M15 / H1 / H4 / D1, read at
           the trigger bar from HIGHER-TIMEFRAME CANDLES THAT HAD ALREADY CLOSED. A trade is
           taken only when the required timeframes agree with the bounce direction.
  stop     `--stop` x ADR20 THROUGH the VWAP. Held fixed across the target sweep, because a
           "best target" measured while the stop also moves is not a statement about targets.
  target   swept: 0.05 / 0.10 / 0.15 / 0.20 / 0.30 / 0.50 x ADR20, plus "no target, out at
           the zone's end" — the scalp as originally specified.

⚠ **Inside the TRIGGER bar only the stop can count.** The bar opened on the entry side and
reached the VWAP, so an excursion toward the target may have happened BEFORE the fill, while
one through the VWAP to the stop can only have happened after it. After the trigger bar, a bar
holding both books the stop. Every ambiguity resolves against the trade, and the same bias
applies to the controls — so read a zone against the all-day column, never against 50%.

⚠ **8 trend variants x 7 targets is 56 cells for one window.** The search is deliberately
narrowed to the 10:00 zone and the winner is then checked on the other zones and against every
same-length window of the day. Discovery 2018-2023 and unseen 2024-2026 are reported
separately for the best cell of each variant: a cell that flips between them is a regime, not
an edge. $0.14/oz round trip is charged on every trade.

Uses `engines/vwap/` and `engines/market_structure/`. Never a second copy of either.

Usage:
    python3 backtest/tools/killzone_vwap_retest.py
    python3 backtest/tools/killzone_vwap_retest.py --stop 0.15
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
_ENGINES = _ROOT / "engines"
for _p in (str(_ROOT), str(_ENGINES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from market_structure import Bar, StructureEngine  # noqa: E402
from vwap import VwapEngine  # noqa: E402

from backtest.tools.killzone_profile import CACHE, DEFAULT_SERVER, _safe_token  # noqa: E402

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
T = dt.time
SPLIT = dt.date(2023, 12, 31)
COST = 0.14
WINDOWS = ("10:00-11:00", "10:30-11:00", "11:45-12:15", "13:00-13:45")
TARGETS = (0.05, 0.10, 0.15, 0.20, 0.30, 0.50)

# Trend confluence variants: which timeframes must agree with the bounce. () = no filter.
VARIANTS = {
    "no trend filter": (),
    "M15 agrees": ("m15",),
    "H1 agrees": ("h1",),
    "H4 agrees": ("h4",),
    "D1 agrees": ("d1",),
    "H1 + H4 agree": ("h1", "h4"),
    "H4 + D1 agree": ("h4", "d1"),
    "all four agree": ("m15", "h1", "h4", "d1"),
}


class _Htf:
    """Aggregate the M5 stream into one higher timeframe, feeding a structure engine each time
    a bucket COMPLETES. `key_of` decides the bucket, so D1 can be a NY calendar day while the
    intraday frames are UTC-floored (NY is a whole-hour offset, so those align either way)."""

    def __init__(self, key_of):
        self.key_of = key_of
        self.engine = StructureEngine()
        self.key = None
        self.o = self.h = self.l = self.c = None
        self.n = 0

    def push(self, ts, ny, o, h, l, c) -> None:
        key = self.key_of(ts, ny)
        if key != self.key:
            if self.key is not None:
                self.engine.update(Bar(self.n, self.o, self.h, self.l, self.c))
                self.n += 1
            self.key, self.o, self.h, self.l, self.c = key, o, h, l, c
        else:
            self.h, self.l, self.c = max(self.h, h), min(self.l, l), c


def _floor(minutes: int):
    epoch = dt.datetime.min.replace(tzinfo=UTC)
    return lambda ts, ny: (ts - epoch).total_seconds() // (60 * minutes)


def load(symbol: str, tf: str, server: str) -> dict:
    """NY date -> [(time, o, h, l, c, vwap_before, dirs)] with dirs = {m15,h1,h4,d1}."""
    path = CACHE / _safe_token(server) / f"{symbol}__{tf}.csv"
    if not path.exists():
        raise SystemExit(f"no cached bars at {path}")
    vwe = VwapEngine()
    htf = {
        "m15": _Htf(_floor(15)),
        "h1": _Htf(_floor(60)),
        "h4": _Htf(_floor(240)),
        "d1": _Htf(lambda ts, ny: ny.date()),
    }
    days = defaultdict(list)
    before = None
    with path.open(newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            ts = dt.datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
            if row.get("volume") in (None, "", "nan", "NaN"):
                raise SystemExit(f"{path.name} row {i} has no volume — VWAP cannot be computed")
            ny = ts.astimezone(NY)
            # Push first: a completed higher-timeframe candle is information this bar may use.
            for a in htf.values():
                a.push(ts, ny, o, h, l, c)
            dirs = {k: a.engine.dir for k, a in htf.items()}
            days[ny.date()].append((ny.time(), o, h, l, c, before, dirs))
            ev = vwe.update(i, int(ts.timestamp() * 1000), h, l, c, float(row["volume"]))
            before = ev.value
    return days


def adr_by_day(days: dict) -> dict:
    out, hist = {}, []
    for d in sorted(days):
        core = [b for b in days[d] if T(3) <= b[0] < T(17)]
        if d.weekday() >= 5 or len(core) < 118:
            continue
        if len(hist) >= 5:
            out[d] = statistics.fmean(hist[-20:])
        hist.append(max(b[2] for b in core) - min(b[3] for b in core))
    return out


def touch(bars: list, ws: dt.time, we: dt.time):
    """The first VWAP retest in [ws, we): side, entry, trend dirs, and the path after it."""
    zb = [b for b in bars if ws <= b[0] < we]
    for j, (t, o, h, l, c, v, dirs) in enumerate(zb):
        if v is None or o == v:
            continue
        side = 1 if o > v else -1
        if (side > 0 and l <= v) or (side < 0 and h >= v):
            return {
                "side": side,
                "v": v,
                "dirs": dirs,
                "trigger": (h, l),
                "path": [(b[2], b[3]) for b in zb[j + 1 :]],
                "exit": zb[-1][4],
            }
    return None


def price(tc: dict, adr: float, stop_k: float | None, target_k: float | None) -> float:
    """Dollars, after costs. target_k None = no target; stop_k None = no stop. Both None is
    the pure time exit: in at the VWAP, out at the window's end, nothing in between."""
    side, v = tc["side"], tc["v"]
    timed = side * (tc["exit"] - v) - COST
    tgt = None if target_k is None else v + side * target_k * adr

    if stop_k is None:
        if tgt is None:
            return timed
        for h, l in tc["path"]:  # trigger bar cannot count a target (see docstring)
            if (h >= tgt) if side > 0 else (l <= tgt):
                return target_k * adr - COST
        return timed

    stop = v - side * stop_k * adr
    hit = lambda h, l: (l <= stop) if side > 0 else (h >= stop)  # noqa: E731
    if hit(*tc["trigger"]):  # trigger bar: only the stop can count
        return -stop_k * adr - COST
    for h, l in tc["path"]:
        if hit(h, l):
            return -stop_k * adr - COST
        if tgt is not None and ((h >= tgt) if side > 0 else (l <= tgt)):
            return target_k * adr - COST
    return timed


def cells(days, adrs, ws, we, keys, stop_k):
    """(date, touch, adr) for days whose retest passes this trend variant."""
    out = []
    for d in sorted(adrs):
        tc = touch(days[d], ws, we)
        if not tc:
            continue
        if all(tc["dirs"][k] == tc["side"] for k in keys):
            out.append((d, tc, adrs[d]))
    return out


def stats(rows, stop_k, target_k):
    pnl = [(d, price(tc, adr, stop_k, target_k)) for d, tc, adr in rows]
    if not pnl:
        return None
    wins = [x for _, x in pnl if x > 0]
    dis = [(d, x) for d, x in pnl if d <= SPLIT]
    oos = [(d, x) for d, x in pnl if d > SPLIT]
    adrs = [adr for _, _, adr in rows]
    per_adr = [x / a for (_, x), a in zip(pnl, adrs)]
    return {
        "n": len(pnl),
        "win": 100 * len(wins) / len(pnl),
        "usd": statistics.fmean(x for _, x in pnl),
        # 🔴 The comparable unit ACROSS stop sizes. R cannot be: one R *is* the stop, so a
        # wider stop silently inflates every R it reports. A share of the day's range is the
        # same unit in every cell and in every year of a sample where gold tripled.
        "adr": statistics.fmean(per_adr),
        # R stays for reading one stop size against its own targets; undefined without a stop.
        # `is not None`, never falsy (rule 1): a 0.0 stop is a degenerate MEASUREMENT and must
        # raise, where None is the question never asked. Collapsing them hides one behind the other.
        "r": (
            statistics.fmean(x / (stop_k * a) for (_, x), a in zip(pnl, adrs))
            if stop_k is not None
            else None
        ),
        "win_dis": 100 * sum(1 for _, x in dis if x > 0) / len(dis) if dis else float("nan"),
        "win_oos": 100 * sum(1 for _, x in oos if x > 0) / len(oos) if oos else float("nan"),
        "adr_dis": statistics.fmean(x / a for (d, x), a in zip(pnl, adrs) if d <= SPLIT)
        if dis
        else float("nan"),
        "adr_oos": statistics.fmean(x / a for (d, x), a in zip(pnl, adrs) if d > SPLIT)
        if oos
        else float("nan"),
    }


def _tname(k):
    return "zone end" if k is None else f"{k:g}xADR"


def _sname(k):
    return "no stop" if k is None else f"{k:g}xADR"


def sweep_stops(days, adrs, ws, we, labels, stops, targets) -> tuple | None:
    """The stop x target grid, scored as a share of ADR20.

    ⚠ **Scored in ADR, not in R, and that is the whole reason this function exists.** One R is
    the stop, so reading R down a column of different stops compares different units and makes
    the widest stop look best for free. A share of the day's range is one unit everywhere.
    """
    grids = {}
    for label in labels:
        rows = cells(days, adrs, ws, we, VARIANTS[label], None)
        grids[label] = {(s, t): stats(rows, s, t) for s in stops for t in targets}
        n = next((v["n"] for v in grids[label].values() if v), 0)
        print(f"\n  {label.upper()} — {n} retests, expectancy as % of a day's range")
        print(f"    {'stop':<10}" + "".join(f"{_tname(t):>11}" for t in targets))
        for s in stops:
            line = "".join(
                f"{100 * grids[label][(s, t)]['adr']:>+10.2f}%"
                if grids[label][(s, t)]
                else f"{'-':>11}"
                for t in targets
            )
            print(f"    {_sname(s):<10}{line}")
        print(f"    {'':<10}" + "".join(f"{'':>11}" for _ in targets))
        print(f"    {'stop':<10}" + "".join(f"{_tname(t):>11}" for t in targets) + "   win %")
        for s in stops:
            line = "".join(
                f"{grids[label][(s, t)]['win']:>10.1f}%" if grids[label][(s, t)] else f"{'-':>11}"
                for t in targets
            )
            print(f"    {_sname(s):<10}{line}")

    flat = [
        (label, s, t, v)
        for label, g in grids.items()
        for (s, t), v in g.items()
        if v and v["n"] >= 100
    ]
    flat.sort(key=lambda x: -x[3]["adr"])
    print("\n  TOP 8 CELLS, and whether each held in both halves of the sample")
    print(
        f"    {'filter':<18}{'stop':>10}{'target':>11}{'days':>6}{'win%':>8}"
        f"{'%ADR':>8}{'$/trade':>9}{'2018-23':>10}{'2024-26':>10}"
    )
    for label, s, t, v in flat[:8]:
        print(
            f"    {label:<18}{_sname(s):>10}{_tname(t):>11}{v['n']:>6}{v['win']:>7.1f}%"
            f"{100 * v['adr']:>+7.2f}%{v['usd']:>+9.2f}"
            f"{100 * v['adr_dis']:>+9.2f}%{100 * v['adr_oos']:>+9.2f}%"
        )
    return flat[0] if flat else None


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="M5")
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--search-window", default="10:00-11:00")
    ap.add_argument("--stop", type=float, default=0.10, help="stop = k x ADR20 through the VWAP")
    ap.add_argument(
        "--sweep-stops",
        action="store_true",
        help="also sweep the STOP against the target, scored as a share of ADR20",
    )
    args = ap.parse_args()

    days = load(args.symbol, args.tf, args.server)
    adrs = adr_by_day(days)
    sw = tuple(
        dt.datetime.strptime(x.strip(), "%H:%M").time() for x in args.search_window.split("-")
    )
    exits = [None, *TARGETS]

    print(
        f"\nVWAP RETEST + TREND CONFLUENCE — {args.symbol} {args.tf}, {len(adrs)} days, "
        f"stop {args.stop:g}xADR20 through the VWAP, ${COST:.2f}/oz charged"
    )
    # ⚠ A stop stated only as a multiple of ADR is not a stop anyone can place. It is quoted in
    # DOLLARS here as well, per year, because gold went from ~$1,200 to ~$4,400 across this
    # sample: the same rule is a ~$1 stop at the start and a ~$6 one at the end.
    by_year = defaultdict(list)
    for d, a in adrs.items():
        by_year[d.year].append(a)
    span = " ".join(
        f"{y}:${args.stop * statistics.median(v):.2f}" for y, v in sorted(by_year.items())
    )
    print(
        f"  the stop in dollars — median ${args.stop * statistics.median(adrs.values()):.2f} "
        f"over the sample, by year: {span}"
    )
    print(f"\nSEARCH WINDOW {args.search_window} NY — win% by trend filter and target")
    head = "".join(f"{_tname(k):>11}" for k in exits)
    print(f"  {'trend filter':<18}{'days':>6}{head}")
    grid = {}
    for label, keys in VARIANTS.items():
        rows = cells(days, adrs, sw[0], sw[1], keys, args.stop)
        grid[label] = {k: stats(rows, args.stop, k) for k in exits}
        n = grid[label][None]["n"] if grid[label][None] else 0
        line = "".join(
            f"{grid[label][k]['win']:>10.1f}%" if grid[label][k] else f"{'-':>11}" for k in exits
        )
        print(f"  {label:<18}{n:>6}{line}")

    print(f"\n  same grid, expectancy in R (one R = the {args.stop:g}xADR stop)")
    print(f"  {'trend filter':<18}{'days':>6}{head}")
    for label in VARIANTS:
        n = grid[label][None]["n"] if grid[label][None] else 0
        line = "".join(
            f"{grid[label][k]['r']:>+11.3f}" if grid[label][k] else f"{'-':>11}" for k in exits
        )
        print(f"  {label:<18}{n:>6}{line}")

    print("\n  BEST TARGET PER FILTER, and whether it held in both halves of the sample")
    print(
        f"  {'trend filter':<18}{'best target':>12}{'days':>6}{'win%':>8}{'expR':>8}{'$/trade':>9}{'2018-23 win%':>14}{'2024-26 win%':>14}"
    )
    best_overall = None
    for label in VARIANTS:
        ok = [(k, s) for k, s in grid[label].items() if s and s["n"] >= 100]
        if not ok:
            continue
        k, s = max(ok, key=lambda kv: kv[1]["r"])
        print(
            f"  {label:<18}{_tname(k):>12}{s['n']:>6}{s['win']:>7.1f}%{s['r']:>+8.3f}"
            f"{s['usd']:>+9.2f}{s['win_dis']:>13.1f}%{s['win_oos']:>13.1f}%"
        )
        if best_overall is None or s["r"] > best_overall[2]["r"]:
            best_overall = (label, k, s)

    if best_overall:
        label, k, s = best_overall
        keys = VARIANTS[label]
        print(
            f"\nBEST CELL — {label}, target {_tname(k)}: {s['win']:.1f}% win, {s['r']:+.3f}R, {s['usd']:+.2f}$/trade"
        )
        length = (sw[1].hour * 60 + sw[1].minute) - (sw[0].hour * 60 + sw[0].minute)
        print("\n  the SAME rule on every other same-length window of the day — the control")
        ctrl = []
        m = 4 * 60
        while m + length <= 16 * 60:
            ca = T(m // 60, m % 60)
            cb = T((m + length) // 60, (m + length) % 60)
            m += 30
            if (ca, cb) == sw:
                continue
            cs = stats(cells(days, adrs, ca, cb, keys, args.stop), args.stop, k)
            if cs and cs["n"] >= 100:
                ctrl.append((f"{ca:%H:%M}-{cb:%H:%M}", cs))
        for name, cs in ctrl:
            print(f"    {name:<14}{cs['n']:>6}{cs['win']:>7.1f}%{cs['r']:>+8.3f}")
        if ctrl:
            print(
                f"    all-day median: win {statistics.median(c['win'] for _, c in ctrl):.1f}%, "
                f"{statistics.median(c['r'] for _, c in ctrl):+.3f}R"
            )

        print("\n  the same rule in the OTHER kill zones")
        for w in WINDOWS:
            if w == args.search_window:
                continue
            a, b = (dt.datetime.strptime(x.strip(), "%H:%M").time() for x in w.split("-"))
            cs = stats(cells(days, adrs, a, b, keys, args.stop), args.stop, k)
            if cs:
                print(
                    f"    {w:<14}{cs['n']:>6}{cs['win']:>7.1f}%{cs['r']:>+8.3f}{cs['usd']:>+9.2f}"
                )
    searched = len(VARIANTS) * len(exits)
    if args.sweep_stops:
        stops = (None, *TARGETS)  # the same ladder as the targets, plus no stop at all
        labels = ["no trend filter", "H1 + H4 agree"]
        print(f"\n\nSTOP x TARGET SWEEP — {args.search_window} NY")
        searched += len(labels) * len(stops) * len(exits)
        best = sweep_stops(days, adrs, sw[0], sw[1], labels, stops, exits)
        if best:
            label, s, t, v = best
            length = (sw[1].hour * 60 + sw[1].minute) - (sw[0].hour * 60 + sw[0].minute)
            print(
                f"\n  BEST SWEEP CELL — {label}, stop {_sname(s)}, target {_tname(t)}: "
                f"{v['win']:.1f}% win, {100 * v['adr']:+.2f}% of a day's range, {v['usd']:+.2f}$/trade"
            )
            ctrl = []
            m = 4 * 60
            while m + length <= 16 * 60:
                ca = T(m // 60, m % 60)
                cb = T((m + length) // 60, (m + length) % 60)
                m += 30
                if (ca, cb) == sw:
                    continue
                cs = stats(cells(days, adrs, ca, cb, VARIANTS[label], None), s, t)
                if cs and cs["n"] >= 100:
                    ctrl.append(cs)
            if ctrl:
                print(
                    f"  the SAME cell on every other same-length window: median win "
                    f"{statistics.median(c['win'] for c in ctrl):.1f}%, "
                    f"{100 * statistics.median(c['adr'] for c in ctrl):+.2f}% of a day's range "
                    f"({len(ctrl)} windows); best of them "
                    f"{100 * max(c['adr'] for c in ctrl):+.2f}%"
                )
            print("  the same cell in the OTHER kill zones")
            for w in WINDOWS:
                if w == args.search_window:
                    continue
                a, b = (dt.datetime.strptime(x.strip(), "%H:%M").time() for x in w.split("-"))
                cs = stats(cells(days, adrs, a, b, VARIANTS[label], None), s, t)
                if cs:
                    print(
                        f"    {w:<14}{cs['n']:>6}{cs['win']:>7.1f}%"
                        f"{100 * cs['adr']:>+8.2f}%{cs['usd']:>+9.2f}"
                    )

    print(
        f"\n  {searched} cells searched in {args.search_window}."
        " Believe a cell only if it beats the all-day control AND holds in both halves."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
