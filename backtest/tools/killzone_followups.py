#!/usr/bin/env python3
"""killzone_followups.py — the three pre-registered follow-up tests on the 10:00 zone.

Each hypothesis below was written down BEFORE its numbers were read (2026-09-15), and each
carries the same pass line as `killzone_edge_search.py`: discovery 2018-2023, confirmation on
2024-2026, $0.14/oz round trip charged on every trade (ECN spread $0.12 + $1/side/lot).

  dayturn  Is 10:00 the day's turning point? Which hour prints the day's high/low, and do
           36 clock-and-price rules (follow/fade the morning, the NY opening range, the
           morning range, the 10am hour, a failed sweep of the morning extreme) pay to
           11:00 / 12:00 / 13:00 / 16:00? Reads raw bars.
  news     H1: do 10:00 ET USD releases carry the zone's size? H2: does following — or
           fading — the zone's first 15 / 30 minutes pay, overall and split by release day?
  trend    Every positive cell anywhere in this study was a FOLLOW rule that worked in
           2024-2026 only, which is a regime signature. So: take the 10:00 continuation
           ONLY in the direction of the daily trend (20-day average, 20-day momentum),
           learned on 2018-2023 — which holds both the 2019-20 trend and the 2021-22 chop.

Modes `news` and `trend` read the table `killzone_features.py` writes. Run that first.

Usage:
    python3 backtest/tools/killzone_followups.py              # all three
    python3 backtest/tools/killzone_followups.py trend
    python3 backtest/tools/killzone_followups.py dayturn --cost 0   # gross
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.tools.killzone_profile import DEFAULT_SERVER, _slice, load_days  # noqa: E402

T = dt.time
SPLIT = dt.date(2023, 12, 31)
FEATURES = _ROOT / "backtest" / "reports" / "kz_features" / "features_1000.csv"


def _t(v):
    if len(v) < 30:
        return float("nan")
    sd = statistics.stdev(v)
    return statistics.fmean(v) / (sd / math.sqrt(len(v))) if sd else float("nan")


def _sg(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _load_features() -> list[dict]:
    if not FEATURES.exists():
        raise SystemExit(
            f"no feature table at {FEATURES} — run backtest/tools/killzone_features.py"
        )
    rows = []
    for r in csv.DictReader(FEATURES.open()):
        q = {"d": dt.date.fromisoformat(r["date"])}
        for k, v in r.items():
            if v in ("True", "False"):
                q[k] = v == "True"
            elif v in ("", "None"):
                q[k] = None
            else:
                try:
                    q[k] = float(v)
                except ValueError:
                    q[k] = v
        rows.append(q)
    rows.sort(key=lambda q: q["d"])
    return rows


# ---------------------------------------------------------------------------
# dayturn


def dayturn(cost: float, server: str) -> None:
    days = load_days("XAUUSD", "M5", None, None, server=server)
    hist, table = [], []
    for date in sorted(days):
        if date.weekday() >= 5:
            continue
        bars = days[date]
        core = _slice(bars, T(3), T(17))
        if len(core) < 118:  # 70% of the 168 M5 bars in 03:00-17:00
            continue
        adr = statistics.fmean(hist[-20:]) if len(hist) >= 5 else None
        hist.append(max(b.high for b in core) - min(b.low for b in core))
        if not adr:
            continue
        morn, orb, h10 = (
            _slice(bars, T(3), T(10)),
            _slice(bars, T(9, 30), T(10)),
            _slice(bars, T(10), T(11)),
        )
        if len(morn) < 60 or len(orb) < 5 or len(h10) < 10:
            continue

        def close_before(t, bars=bars):
            s = [b for b in bars if b.t < t]
            return s[-1].close if s else None

        hb, lb = max(core, key=lambda b: b.high), min(core, key=lambda b: b.low)
        table.append(
            dict(
                date=date,
                adr=adr,
                bars=bars,
                m_open=morn[0].open,
                o10=h10[0].open,
                c11=h10[-1].close,
                m_hi=max(b.high for b in morn),
                m_lo=min(b.low for b in morn),
                or_hi=max(b.high for b in orb),
                or_lo=min(b.low for b in orb),
                h10_hi=max(b.high for b in h10),
                h10_lo=min(b.low for b in h10),
                c12=close_before(T(12)),
                c13=close_before(T(13)),
                c16=close_before(T(16)),
                hi_hour=hb.t.hour,
                lo_hour=lb.t.hour,
            )
        )

    print(f"\nDAYTURN — {len(table)} days, ${cost:.2f}/oz round trip")
    print("\n  which hour prints the day's high or low (03:00-17:00)")
    cnt = defaultdict(int)
    for r in table:
        cnt[r["hi_hour"]] += 1
        cnt[r["lo_hour"]] += 1
    for h in range(3, 17):
        print(f"    {h:02d}:00  {100 * cnt[h] / (2 * len(table)):5.1f}%")

    def breakout(r, hi, lo):
        bs = _slice(r["bars"], T(10), T(11))
        for i, b in enumerate(bs[:-1]):
            up, dn = b.high > hi, b.low < lo
            if up and dn:
                return 0, None
            if up:
                return 1, bs[i + 1].open  # filled one bar behind the break
            if dn:
                return -1, bs[i + 1].open
        return 0, None

    def rules(r):
        o10, c11 = r["o10"], r["c11"]
        mdir, hdir = (1 if o10 > r["m_open"] else -1), (1 if c11 > o10 else -1)
        out = {}
        for hz in ("c11", "c12", "c13", "c16"):
            x = r[hz]
            if x is None:
                continue
            out[f"follow morning, 10->{hz}"] = (mdir, o10, x)
            out[f"fade morning, 10->{hz}"] = (-mdir, o10, x)
            d, e = breakout(r, r["or_hi"], r["or_lo"])
            if d:
                out[f"NY-open-range break, ->{hz}"] = (d, e, x)
                out[f"NY-open-range FADE, ->{hz}"] = (-d, e, x)
            d, e = breakout(r, r["m_hi"], r["m_lo"])
            if d:
                out[f"morning-range break, ->{hz}"] = (d, e, x)
                out[f"morning-range FADE, ->{hz}"] = (-d, e, x)
        for hz in ("c12", "c13", "c16"):
            x = r[hz]
            if x is None:
                continue
            out[f"follow the 10am hour, 11->{hz}"] = (hdir, c11, x)
            out[f"fade the 10am hour, 11->{hz}"] = (-hdir, c11, x)
            if r["h10_hi"] > r["m_hi"] and c11 < r["m_hi"] and c11 < o10:
                out[f"10am swept morning HIGH & failed, short 11->{hz}"] = (-1, c11, x)
            if r["h10_lo"] < r["m_lo"] and c11 > r["m_lo"] and c11 > o10:
                out[f"10am swept morning LOW & failed, long 11->{hz}"] = (1, c11, x)
        return out

    stats = defaultdict(lambda: {"dis": [], "oos": [], "oos_usd": []})
    for r in table:
        k = "dis" if r["date"] <= SPLIT else "oos"
        for name, (d, e, x) in rules(r).items():
            usd = d * (x - e) - cost
            stats[name][k].append(usd / r["adr"])
            if k == "oos":
                stats[name]["oos_usd"].append(usd)
    _table(stats, min_dis=50)


# ---------------------------------------------------------------------------
# news


def news(cost: float) -> None:
    rows = _load_features()
    cov = [r for r in rows if r["news_covered"]]
    rel = [r for r in cov if (r["usd_release_at"] or 0) >= 2]
    quiet = [r for r in cov if (r["usd_release_at"] or 0) < 2]
    print(
        f"\nNEWS — calendar covers {len(cov)} of {len(rows)} days ({cov[0]['d']} -> {cov[-1]['d']});"
        f" 10:00 USD release days {len(rel)}, quiet {len(quiet)}"
    )
    rng = lambda r: r["z_hi"] - r["z_lo"]  # noqa: E731
    print(
        f"  H1 zone range, median: release ${statistics.median(map(rng, rel)):.2f} "
        f"vs quiet ${statistics.median(map(rng, quiet)):.2f}  "
        f"(ADR {statistics.median(rng(r) / r['adr'] for r in rel):.1%} vs "
        f"{statistics.median(rng(r) / r['adr'] for r in quiet):.1%})"
    )
    print("  H2 early momentum — in after the first 15/30 min, out at a fixed time")
    for label, subset in (("all days", rows), ("release days", rel), ("quiet days", quiet)):
        stats = defaultdict(lambda: {"dis": [], "oos": [], "oos_usd": []})
        for r in subset:
            for entry, exits in (
                ("c_1015", ("c_1100", "c_1215")),
                ("c_1030", ("c_1100", "c_1215")),
            ):
                for ex in exits:
                    e, x = r[entry], r[ex]
                    if e is None or x is None or not _sg(e - r["o_at"]):
                        continue
                    for mult, word in ((1, "follow"), (-1, "fade")):
                        usd = mult * _sg(e - r["o_at"]) * (x - e) - cost
                        k = "dis" if r["d"] <= SPLIT else "oos"
                        name = f"[{label}] {word} first {entry[-2:]}min, {entry[2:]}->{ex[2:]}"
                        stats[name][k].append(usd / r["adr"])
                        if k == "oos":
                            stats[name]["oos_usd"].append(usd)
        _table(stats, min_dis=30, sort=False)


# ---------------------------------------------------------------------------
# trend


def trend(cost: float) -> None:
    rows = _load_features()
    closes = [q["pd_close"] for q in rows]  # row i's pd_close is day i-1's 16:00 close
    for i, q in enumerate(rows):
        hist = [c for c in closes[max(0, i - 20) : i + 1] if c is not None]
        q["T20"] = q["M20"] = 0
        if len(hist) >= 21 and closes[i] is not None:
            q["T20"] = 1 if closes[i] > statistics.fmean(hist[-20:]) else -1  # vs mean(D-20..D-1)
            q["M20"] = 1 if closes[i] > hist[-21] else -1  # vs close[D-21]

    def rule(q, name, tr):
        d = q[tr]
        if not d:
            return 0, None
        if name == "trade the daily trend at 10:00":
            return d, q["o_at"]
        if name == "morning move WITH the daily trend":
            return (d, q["o_at"]) if _sg(q["o_at"] - q["m_open"]) == d else (0, None)
        if q["c_1030"] is None:
            return 0, None
        return (d, q["c_1030"]) if _sg(q["c_1030"] - q["o_at"]) == d else (0, None)

    stats = defaultdict(lambda: {"dis": [], "oos": [], "oos_usd": []})
    for name in (
        "trade the daily trend at 10:00",
        "morning move WITH the daily trend",
        "first 30min WITH the daily trend",
    ):
        for tr in ("T20", "M20"):
            for ex in ("c_1100", "c_1215", "c_1300"):
                key = f"{name} [{tr}] ->{ex[2:]}"
                for q in rows:
                    d, e = rule(q, name, tr)
                    if not d or e is None or q[ex] is None:
                        continue
                    usd = d * (q[ex] - e) - cost
                    k = "dis" if q["d"] <= SPLIT else "oos"
                    stats[key][k].append(usd / q["adr"])
                    if k == "oos":
                        stats[key]["oos_usd"].append(usd)
    print(f"\nTREND — the 10:00 continuation, only with the daily trend (${cost:.2f}/oz)")
    _table(stats, min_dis=30, sort=False)


# ---------------------------------------------------------------------------


def _table(stats, min_dis: int, sort: bool = True) -> None:
    keys = [k for k in stats if len(stats[k]["dis"]) >= min_dis]
    if sort:
        keys.sort(key=lambda k: -_t(stats[k]["dis"]))
    print(f"  {'rule':<58}{'nDis':>5}{'tDis':>7}{'nOOS':>6}{'tOOS':>7}{'oos$':>8}  verdict")
    passed = 0
    for k in keys:
        s = stats[k]
        td, to = _t(s["dis"]), _t(s["oos"])
        ok = td >= 2.5 and to >= 2.0
        passed += ok
        usd = statistics.fmean(s["oos_usd"]) if s["oos_usd"] else float("nan")
        print(
            f"  {k:<58}{len(s['dis']):>5}{td:>+7.1f}{len(s['oos']):>6}{to:>+7.1f}{usd:>+8.2f}"
            f"  {'PASS' if ok else 'fail'}"
        )
    print(f"  {passed} of {len(keys)} pass (discovery t >= 2.5 AND unseen t >= 2.0)")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("mode", nargs="?", choices=("dayturn", "news", "trend", "all"), default="all")
    ap.add_argument("--cost", type=float, default=0.14, help="round trip, $/oz (default ECN 0.14)")
    ap.add_argument("--server", default=DEFAULT_SERVER)
    args = ap.parse_args()
    if args.mode in ("dayturn", "all"):
        dayturn(args.cost, args.server)
    if args.mode in ("news", "all"):
        news(args.cost)
    if args.mode in ("trend", "all"):
        trend(args.cost)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
