#!/usr/bin/env python3
"""killzone_profile.py — measure what price actually DOES in a time window, before
anyone writes an entry rule.

This is a study, not a strategy. It answers one question: is the New York kill zone
special, or does it just look special because we watch it? Every statistic it reports
for the target window is also reported for every NY hour, because a number like
"31% of days print their high or low in this hour" is meaningless until you know that
a random hour scores 4%.

It reads the cached broker bars off disk (`backtest/cache/`), so it runs on a laptop
with no MT5 and no VPS. **Standard library only** — no pandas, no numpy. It touches
none of the `engines/` either: this is deliberately a pure clock-and-price measurement,
so nothing here can inherit a bug from the structure stack, and any edge it finds is an
edge in the CLOCK.

Definitions, all in America/New_York (DST-aware, matching engines/sessions/engine.py):

  window       the hour under test. Default 10:00-11:00 = KZ1.
  pre-leg      the move from 03:00 NY to the window close — London into New York.
  post move    price from the window close forward 1h / 2h / 4h.
  reversal     the post move ran OPPOSITE the pre-leg.
  sweep        the window took out the day's own high/low set before it, then closed
               back inside that prior range by the window's end.

Everything in price terms is normalised by ADR20 (the 20-day mean daily range, prior
days only). Gold ran at $1,200 in 2018 and $4,000 today — a raw dollar move is not
comparable across the sample, and would make every recent year look like the edge grew.

The naive fade baseline is a crude sanity check, not a proposed strategy: at the window
close, take the trade OPPOSITE the pre-leg, stop at the window's extreme on the pre-leg
side, target a multiple of that risk, give up at 16:00 NY. Bar-level fills; when one bar
holds both the stop and the target, the stop wins.

Usage:
    python3 backtest/tools/killzone_profile.py
    python3 backtest/tools/killzone_profile.py --window 09:30-10:00
    python3 backtest/tools/killzone_profile.py --start 2022-01-01 --target-r 3
    python3 backtest/tools/killzone_profile.py --out backtest/reports/kz1
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
CACHE = _ROOT / "backtest" / "cache"

# The oldest cache feed_version whose TIMESTAMPS this study can trust. A FLOOR, never an
# equality — a newer cache is newer for reasons that have nothing to do with the clock.
MIN_FEED_VERSION = 2

# The pre-leg starts here (NY time). 03:00 is inside the London session and well before
# the NY cash open, so the leg into the kill zone is a real move, not overnight drift.
PRE_LEG_START = dt.time(3, 0)

# The day is cut off here for the "where did the extreme print" stat. After 17:00 NY the
# book is thin and the 18:00 rollover distorts the range.
DAY_END = dt.time(17, 0)

# Flat-by time for the naive fade baseline.
FADE_EXIT = dt.time(16, 0)

# A day needs at least this many bars between 03:00 and 17:00 to count. Short days
# (half-sessions, holidays, broker outages) are dropped rather than half-measured.
MIN_BARS_IN_DAY = 40


class Bar(NamedTuple):
    t: dt.time
    open: float
    high: float
    low: float
    close: float


# ---------------------------------------------------------------------------
# data


def load_days(symbol: str, tf: str, start: dt.date | None, end: dt.date | None):
    """Read the cached bars once and bucket them by NY calendar date.

    The cache stamps bars in true UTC from feed_version 2 onward. Anything older is the
    broker-local-timestamp era, where every session boundary in this study would be
    silently wrong — so refuse it rather than report a plausible-looking lie.

    ⚠ The floor is a MINIMUM, not an equality, and it was written as `!= 2` until
    2026-08-13 — which bricked this study the day `FEED_VERSION` went to 3 for a reason
    that has nothing to do with time (v3 added the VOLUME column; the timestamps did not
    move). This tool is a pure clock-and-price measurement, so v3 is strictly better
    input than the v2 it demanded. Worse than the refusal was its MESSAGE: it blamed
    broker-local timestamps, sending the reader off to re-pull 186k bars to fix a bug in
    this line. Pin a floor when you mean a floor.
    """
    path = CACHE / f"{symbol}__{tf}.csv"
    meta = CACHE / f"{symbol}__{tf}.meta.json"
    if not path.exists():
        raise SystemExit(f"no cached bars at {path} — pull them with the MT5 agent first")
    if meta.exists():
        # Missing key == pre-sidecar == the version-1 era, same default backtest/data/cache.py uses.
        version = json.loads(meta.read_text()).get("feed_version", 1)
        if version < MIN_FEED_VERSION:
            raise SystemExit(
                f"{path.name} is feed_version {version}; this study needs at least "
                f"{MIN_FEED_VERSION} (true UTC). Re-pull the bars — version 1 bars are "
                "stamped in broker-local time and every NY hour in this report would be "
                "off by the broker's offset."
            )

    days: dict[dt.date, list[Bar]] = defaultdict(list)
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            stamp = dt.datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S")
            ny = stamp.replace(tzinfo=UTC).astimezone(NY)
            date = ny.date()
            if start and date < start:
                continue
            if end and date > end:
                continue
            days[date].append(
                Bar(ny.timetz().replace(tzinfo=None), float(row["open"]),
                    float(row["high"]), float(row["low"]), float(row["close"]))
            )
    for bars in days.values():
        bars.sort(key=lambda b: b.t)
    return days


def parse_window(spec: str) -> tuple[dt.time, dt.time]:
    start, _, end = spec.partition("-")
    fmt = "%H:%M"
    return (dt.datetime.strptime(start.strip(), fmt).time(),
            dt.datetime.strptime(end.strip(), fmt).time())


def _slice(bars: list[Bar], start: dt.time, end: dt.time) -> list[Bar]:
    """Bars whose OPEN time falls in [start, end) — the same half-open rule the sessions
    engine uses, so a 10:00-11:00 window is the four 15m bars 10:00..10:45."""
    return [b for b in bars if start <= b.t < end]


def _add_hours(t: dt.time, hours: int) -> dt.time:
    total = t.hour * 60 + t.minute + hours * 60
    return dt.time(min(total // 60, 23), total % 60)


# ---------------------------------------------------------------------------
# per-day measurement


def profile_days(days: dict, win_start: dt.time, win_end: dt.time,
                 target_r: float) -> list[dict]:
    """One row per trading day: the window's shape, the leg into it, what came after."""
    rows: list[dict] = []
    adr_hist: list[float] = []

    for date in sorted(days):
        if date.weekday() >= 5:
            continue
        bars = days[date]
        core = _slice(bars, PRE_LEG_START, DAY_END)
        if len(core) < MIN_BARS_IN_DAY:
            continue

        day_range = max(b.high for b in core) - min(b.low for b in core)
        # ADR from the PRIOR days only — no lookahead.
        adr = statistics.fmean(adr_hist[-20:]) if len(adr_hist) >= 5 else None
        adr_hist.append(day_range)

        win = _slice(bars, win_start, win_end)
        pre = _slice(bars, PRE_LEG_START, win_start)
        if not win or not pre or not adr or adr <= 0:
            continue

        ref = win[-1].close
        win_high = max(b.high for b in win)
        win_low = min(b.low for b in win)
        pre_open = pre[0].open
        pre_high = max(b.high for b in pre)
        pre_low = min(b.low for b in pre)

        pre_leg = ref - pre_open
        pre_dir = 1 if pre_leg > 0 else (-1 if pre_leg < 0 else 0)

        row = {
            "date": date.isoformat(),
            "year": date.year,
            "adr20": round(adr, 2),
            "day_range": round(day_range, 2),
            "win_range_adr": (win_high - win_low) / adr,
            "pre_leg_adr": pre_leg / adr,
            "pre_dir": pre_dir,
            "ref_close": ref,
            "win_high": win_high,
            "win_low": win_low,
        }

        # --- what came after, at three horizons
        for hours in (1, 2, 4):
            fwd = _slice(bars, win_end, min(_add_hours(win_end, hours), DAY_END))
            if not fwd:
                row[f"move_{hours}h_adr"] = None
                row[f"mfe_{hours}h_adr"] = None
                row[f"mae_{hours}h_adr"] = None
                row[f"reversed_{hours}h"] = None
                continue
            move = fwd[-1].close - ref
            up = max(b.high for b in fwd) - ref
            down = ref - min(b.low for b in fwd)
            row[f"move_{hours}h_adr"] = move / adr
            # MFE/MAE are stated from the FADE's point of view: "favourable" = the
            # reversal paid, "adverse" = the leg kept going.
            row[f"mfe_{hours}h_adr"] = (down if pre_dir > 0 else up) / adr
            row[f"mae_{hours}h_adr"] = (up if pre_dir > 0 else down) / adr
            row[f"reversed_{hours}h"] = pre_dir != 0 and (move * pre_dir) < 0

        # --- did the window sweep the day's prior extreme and close back inside
        row["swept_high"] = win_high > pre_high and ref < pre_high
        row["swept_low"] = win_low < pre_low and ref > pre_low
        row["swept"] = row["swept_high"] or row["swept_low"]

        # --- did the day's extreme print inside the window
        high_bar = max(core, key=lambda b: b.high)
        low_bar = min(core, key=lambda b: b.low)
        row["day_high_hour"] = high_bar.t.hour
        row["day_low_hour"] = low_bar.t.hour
        row["extreme_in_win"] = (win_start <= high_bar.t < win_end
                                 or win_start <= low_bar.t < win_end)

        row.update(_fade_trade(bars, win_end, ref, win_high, win_low, pre_dir, target_r))
        rows.append(row)

    return rows


def _fade_trade(bars: list[Bar], entry_t: dt.time, entry: float, win_high: float,
                win_low: float, pre_dir: int, target_r: float) -> dict:
    """Crude fade of the pre-leg: stop at the window extreme, flat by 16:00 NY.

    Bar-level fills. When one bar holds both the stop and the target we book the STOP —
    the pessimistic read, because a bar cannot tell us which came first and an optimistic
    guess here is exactly how a study talks itself into an edge.
    """
    blank = {"fade_dir": 0, "fade_r": None, "fade_outcome": ""}
    if pre_dir == 0:
        return blank
    side = -pre_dir  # fade the leg
    stop = win_high if side < 0 else win_low
    risk = abs(stop - entry)
    if risk <= 0:
        return blank
    target = entry + side * risk * target_r

    fwd = _slice(bars, entry_t, FADE_EXIT)
    if not fwd:
        return blank

    for bar in fwd:
        hit_stop = bar.high >= stop if side < 0 else bar.low <= stop
        hit_target = bar.low <= target if side < 0 else bar.high >= target
        if hit_stop:
            return {"fade_dir": side, "fade_r": -1.0, "fade_outcome": "stop"}
        if hit_target:
            return {"fade_dir": side, "fade_r": target_r, "fade_outcome": "target"}

    return {"fade_dir": side, "fade_r": side * (fwd[-1].close - entry) / risk,
            "fade_outcome": "timed_out"}


# ---------------------------------------------------------------------------
# aggregation helpers


def _mean(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return statistics.fmean(vals) if vals else float("nan")


def _pct(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return 100 * statistics.fmean([1.0 if v else 0.0 for v in vals]) if vals else float("nan")


def _median(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    return statistics.median(vals) if vals else float("nan")


# ---------------------------------------------------------------------------
# the all-hours baseline


def hour_baseline(days: dict, target_r: float, step_minutes: int) -> list[dict]:
    """Run the same measurement on every window of the day, so the target window has
    something to be compared against. Without this the report is astrology."""
    out = []
    minute = (PRE_LEG_START.hour * 60 + PRE_LEG_START.minute) + step_minutes
    while minute + 60 <= 23 * 60:
        start = dt.time(minute // 60, minute % 60)
        end = _add_hours(start, 1)
        rows = profile_days(days, start, end, target_r)
        minute += step_minutes
        if not rows:
            continue
        fades = [r for r in rows if r["fade_r"] is not None]
        out.append({
            "window": f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}",
            "days": len(rows),
            "extreme_pct": _pct(rows, "extreme_in_win"),
            "rev_2h_pct": _pct(rows, "reversed_2h"),
            "sweep_pct": _pct(rows, "swept"),
            "range_adr": _mean(rows, "win_range_adr"),
            "fade_exp_r": _mean(fades, "fade_r"),
            "fade_total_r": sum(r["fade_r"] for r in fades),
        })
    return out


def _quartile_cuts(rows: list[dict], key: str, label: str, absolute: bool = False):
    """Split rows into quartiles of `key` and yield (label, subset) for the top and
    bottom quarter. A flat average over all days can hide an edge that only lives in the
    extremes, and this is the cheapest way to see it."""
    vals = sorted(abs(r[key]) if absolute else r[key]
                  for r in rows if r.get(key) is not None)
    if len(vals) < 40:
        return
    lo, hi = vals[len(vals) // 4], vals[3 * len(vals) // 4]
    pick = (lambda r: abs(r[key])) if absolute else (lambda r: r[key])
    yield f"{label} bottom 25%", [r for r in rows if r.get(key) is not None and pick(r) <= lo]
    yield f"{label} top 25%", [r for r in rows if r.get(key) is not None and pick(r) >= hi]


def _cuts(fades: list[dict]):
    """The conditional slices. Each is a hypothesis about WHEN the fade works, phrased
    so a null result is as readable as a positive one."""
    yield "swept prior range", [r for r in fades if r["swept"]]
    yield "did NOT sweep", [r for r in fades if not r["swept"]]
    yield "fade = short", [r for r in fades if r["fade_dir"] < 0]
    yield "fade = long", [r for r in fades if r["fade_dir"] > 0]
    yield from _quartile_cuts(fades, "pre_leg_adr", "leg into window", absolute=True)
    yield from _quartile_cuts(fades, "win_range_adr", "window range")
    swept = [r for r in fades if r["swept"]]
    yield "swept + big leg", [
        r for r in swept
        if abs(r["pre_leg_adr"]) >= statistics.median(abs(x["pre_leg_adr"]) for x in fades)
    ]


# ---------------------------------------------------------------------------
# reporting


def report(rows: list[dict], base: list[dict], win: str, target_r: float,
           symbol: str, tf: str) -> None:
    print(f"\n{'=' * 82}")
    print(f"  {symbol} {tf} — WINDOW {win} New York — {len(rows)} trading days, "
          f"{rows[0]['date']} → {rows[-1]['date']}")
    print(f"{'=' * 82}\n")

    print("SHAPE OF THE WINDOW")
    print(f"  window range        {_mean(rows, 'win_range_adr'):.1%} of ADR20 "
          f"(median {_median(rows, 'win_range_adr'):.1%})")
    print(f"  day's high or low   {_pct(rows, 'extreme_in_win'):.1f}% of days print it "
          f"inside this window")
    print(f"  swept + closed back {_pct(rows, 'swept'):.1f}% of days "
          f"(high {_pct(rows, 'swept_high'):.1f}%, low {_pct(rows, 'swept_low'):.1f}%)")

    print("\nDOES IT REVERSE THE LEG INTO IT")
    for h in (1, 2, 4):
        print(f"  +{h}h  reversed {_pct(rows, f'reversed_{h}h'):5.1f}%   "
              f"fade MFE {_mean(rows, f'mfe_{h}h_adr'):6.1%} ADR   "
              f"fade MAE {_mean(rows, f'mae_{h}h_adr'):6.1%} ADR   "
              f"net move {_mean(rows, f'move_{h}h_adr'):+.1%} ADR")

    fades = [r for r in rows if r["fade_r"] is not None]
    if fades:
        wins = [r for r in fades if r["fade_r"] > 0]
        outcomes = defaultdict(int)
        for r in fades:
            outcomes[r["fade_outcome"]] += 1
        print(f"\nNAIVE FADE BASELINE  (enter at window close, stop at window extreme, "
              f"target {target_r:g}R, flat {FADE_EXIT:%H:%M})")
        print(f"  trades {len(fades)}   win rate {100 * len(wins) / len(fades):.1f}%   "
              f"expectancy {_mean(fades, 'fade_r'):+.3f}R   "
              f"total {sum(r['fade_r'] for r in fades):+.1f}R")
        print("  outcomes  " + "   ".join(f"{k} {v}" for k, v in sorted(outcomes.items())))

    if fades:
        print("\nCONDITIONAL CUTS  (same days, same fade, split by what the window looked "
              "like)")
        print(f"  {'cut':<26}{'trades':>8}{'win%':>8}{'expR':>9}{'totR':>9}")
        for label, subset in _cuts(fades):
            if len(subset) < 30:
                continue
            w = [r for r in subset if r["fade_r"] > 0]
            print(f"  {label:<26}{len(subset):>8}{100 * len(w) / len(subset):>7.1f}%"
                  f"{_mean(subset, 'fade_r'):>9.3f}{sum(r['fade_r'] for r in subset):>9.1f}")

    print("\nBY YEAR")
    print(f"  {'year':<6}{'days':>6}{'extreme%':>10}{'rev2h%':>9}{'sweep%':>9}"
          f"{'fadeR':>9}{'expR':>8}")
    years = defaultdict(list)
    for r in rows:
        years[r["year"]].append(r)
    for year in sorted(years):
        grp = years[year]
        f = [r for r in grp if r["fade_r"] is not None]
        print(f"  {year:<6}{len(grp):>6}{_pct(grp, 'extreme_in_win'):>9.1f}%"
              f"{_pct(grp, 'reversed_2h'):>8.1f}%{_pct(grp, 'swept'):>8.1f}%"
              f"{sum(r['fade_r'] for r in f):>9.1f}{_mean(f, 'fade_r'):>8.3f}")

    if base:
        print("\nEVERY WINDOW OF THE DAY — the baseline this one has to beat")
        print(f"  {'window':<14}{'days':>6}{'extreme%':>10}{'rev2h%':>9}{'sweep%':>9}"
              f"{'rangeADR':>10}{'fadeExpR':>10}{'fadeTotR':>10}")
        for r in base:
            mark = "  <<<" if r["window"] == win else ""
            print(f"  {r['window']:<14}{r['days']:>6}{r['extreme_pct']:>9.1f}%"
                  f"{r['rev_2h_pct']:>8.1f}%{r['sweep_pct']:>8.1f}%"
                  f"{r['range_adr']:>9.1%}{r['fade_exp_r']:>10.3f}"
                  f"{r['fade_total_r']:>10.1f}{mark}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="M15")
    ap.add_argument("--window", default="10:00-11:00", help="NY window under test")
    ap.add_argument("--start", help="YYYY-MM-DD, default = all cached history")
    ap.add_argument("--end", help="YYYY-MM-DD")
    ap.add_argument("--target-r", type=float, default=2.0)
    ap.add_argument("--baseline-step", type=int, default=60,
                    help="minutes between the comparison windows (default 60)")
    ap.add_argument("--out", help="directory for the per-day CSV")
    ap.add_argument("--no-baseline", action="store_true")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start) if args.start else None
    end = dt.date.fromisoformat(args.end) if args.end else None
    days = load_days(args.symbol, args.tf, start, end)

    win_start, win_end = parse_window(args.window)
    rows = profile_days(days, win_start, win_end, args.target_r)
    if not rows:
        raise SystemExit("no days survived the filters — check the window and date range")

    base = [] if args.no_baseline else hour_baseline(days, args.target_r,
                                                     args.baseline_step)
    report(rows, base, args.window, args.target_r, args.symbol, args.tf)

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        with (out / "killzone_days.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        if base:
            with (out / "window_baseline.csv").open("w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(base[0]))
                w.writeheader()
                w.writerows(base)
        print(f"per-day rows → {out / 'killzone_days.csv'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
