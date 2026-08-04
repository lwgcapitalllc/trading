#!/usr/bin/env python3
"""killzone_sweep.py — does a REAL liquidity sweep inside the kill zone reverse price?

`killzone_profile.py` found that the 10:00 NY hour has no reversal edge on the clock
alone (48.9% at +2h — a coin flip, and the lowest rate of any hour), but that its own
crude sweep proxy — the window taking out the day's 03:00-10:00 range and closing back
inside — lifted a losing fade from -0.118R to -0.011R. That proxy is not a liquidity
level. It is just "the last seven hours".

This tool replaces the proxy with the canonical `engines/liquidity/` levels: previous
day high/low, previous week high/low, previous week close, the H4 sweep targets, and
each finished session's high/low, every one of them non-repainting and mitigation-
tracked. It asks two questions the proxy could not:

  1. WHICH level, when swept in the kill zone, actually precedes a reversal?
  2. Does taking the trade in the direction the SWEEP implies beat taking it in the
     direction the pre-leg implies?

Question 2 matters because the profile tool only ever faded the leg into the window.
The classic setup is different: price grabs the liquidity resting above a level, so you
sell — regardless of which way the London leg ran. Those two rules disagree on plenty of
days, and only one of them is the setup being described.

Both baselines stay deliberately crude — entry at the window close, stop at the window's
extreme, fixed R target, flat at 16:00 NY, and the stop wins any bar that contains both
stop and target. No structure, no FVG, no confluence. This measures whether the sweep
carries information, not whether a finished strategy makes money.

Usage:
    python3 backtest/tools/killzone_sweep.py
    python3 backtest/tools/killzone_sweep.py --window 09:00-10:00
    python3 backtest/tools/killzone_sweep.py --target-r 3 --out backtest/reports/kz1_sweep
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENGINES = _ROOT / "engines"
for _p in (str(_ROOT), str(_ENGINES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from liquidity import LiquidityEngine  # noqa: E402

from backtest.tools.killzone_profile import (  # noqa: E402
    CACHE,
    FADE_EXIT,
    NY,
    UTC,
    _fade_trade,
    _mean,
    _pct,
    _slice,
    load_days,
    parse_window,
    profile_days,
)


def sweeps_in_window(symbol: str, tf: str, win_start: dt.time, win_end: dt.time
                     ) -> dict[dt.date, list[tuple[str, str]]]:
    """Replay the whole bar stream through the canonical liquidity engine and collect,
    per NY date, the (level name, side) pairs that price MITIGATED inside the window.

    The engine is fed every bar in sequence including weekends — its day/week/H4 periods
    are built from completed prior periods, so skipping bars would silently corrupt the
    levels rather than fail loudly.
    """
    path = CACHE / f"{symbol}__{tf}.csv"
    liq = LiquidityEngine()
    hits: dict[dt.date, list[tuple[str, str]]] = defaultdict(list)

    with path.open(newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            stamp = dt.datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            ev = liq.update(
                i,
                int(stamp.timestamp() * 1000),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
            )
            if not ev.mitigated:
                continue
            ny = stamp.astimezone(NY)
            if win_start <= ny.time() < win_end:
                for lvl in ev.mitigated:
                    hits[ny.date()].append((lvl.name, lvl.side))
    return hits


def directed_trade(bars, entry_t, entry, win_high, win_low, side, target_r) -> dict:
    """The sweep-directed trade: a swept HIGH means sell, a swept LOW means buy.

    Reuses the profile tool's fill logic verbatim (it takes a leg direction and fades it,
    so passing -side gives the trade we want) — one fill model, not two that can drift.
    """
    out = _fade_trade(bars, entry_t, entry, win_high, win_low, -side, target_r)
    return {"dir_dir": out["fade_dir"], "dir_r": out["fade_r"],
            "dir_outcome": out["fade_outcome"]}


def _stats(rows: list[dict], key: str) -> tuple[int, float, float, float]:
    live = [r for r in rows if r.get(key) is not None]
    if not live:
        return 0, float("nan"), float("nan"), 0.0
    wins = [r for r in live if r[key] > 0]
    return (len(live), 100 * len(wins) / len(live),
            statistics.fmean(r[key] for r in live), sum(r[key] for r in live))


def _line(label: str, rows: list[dict], key: str, floor: int = 25) -> None:
    n, win, exp, tot = _stats(rows, key)
    if n < floor:
        return
    print(f"  {label:<28}{n:>8}{win:>8.1f}%{exp:>9.3f}{tot:>9.1f}")


def build_rows(symbol: str, tf: str, win_start: dt.time, win_end: dt.time,
               target_r: float, start=None, end=None) -> tuple[list[dict], dict]:
    """Per-day rows with the real swept levels joined on and both baselines priced.

    Returns (rows, days) so a caller can re-slice without replaying anything.
    """
    days = load_days(symbol, tf, start, end)
    rows = profile_days(days, win_start, win_end, target_r)
    if not rows:
        return [], days
    hits = sweeps_in_window(symbol, tf, win_start, win_end)

    for r in rows:
        date = dt.date.fromisoformat(r["date"])
        taken = hits.get(date, [])
        r["levels"] = "|".join(sorted({n for n, _ in taken}))
        r["swept_any"] = bool(taken)
        sides = {s for _, s in taken}
        r["swept_high_lvl"] = "high" in sides
        r["swept_low_lvl"] = "low" in sides
        r["swept_both"] = r["swept_high_lvl"] and r["swept_low_lvl"]

        # Only an unambiguous sweep gives a direction. Both sides taken in one hour is a
        # whipsaw, not a setup, and is measured separately rather than guessed at.
        if r["swept_high_lvl"] and not r["swept_low_lvl"]:
            side = -1
        elif r["swept_low_lvl"] and not r["swept_high_lvl"]:
            side = 1
        else:
            side = 0
        r["sweep_side"] = side
        # The sweep pointing the SAME way as the leg into the window is a pullback inside
        # that leg — a continuation entry, not a reversal. Tagged here because it is the
        # only cut in this study that ever came out positive.
        r["continuation"] = side != 0 and side == r["pre_dir"]
        if side:
            r.update(directed_trade(days[date], win_end, r["ref_close"],
                                    r["win_high"], r["win_low"], side, target_r))
        else:
            r.update({"dir_dir": 0, "dir_r": None, "dir_outcome": ""})
    return rows, days


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="M15")
    ap.add_argument("--window", default="10:00-11:00")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--target-r", type=float, default=2.0)
    ap.add_argument("--out")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start) if args.start else None
    end = dt.date.fromisoformat(args.end) if args.end else None
    win_start, win_end = parse_window(args.window)

    rows, days = build_rows(args.symbol, args.tf, win_start, win_end,
                            args.target_r, start, end)
    if not rows:
        raise SystemExit("no days survived the filters")

    print(f"\n{'=' * 84}")
    print(f"  {args.symbol} {args.tf} — REAL LIQUIDITY SWEEPS in {args.window} NY — "
          f"{len(rows)} days, {rows[0]['date']} → {rows[-1]['date']}")
    print(f"{'=' * 84}\n")

    swept = [r for r in rows if r["swept_any"]]
    print("HOW OFTEN IS A REAL LEVEL TAKEN IN THIS WINDOW")
    print(f"  any level swept       {100 * len(swept) / len(rows):.1f}% of days "
          f"({len(swept)} of {len(rows)})")
    print(f"  high side only        {_pct(rows, 'swept_high_lvl'):.1f}%      "
          f"low side only  {_pct(rows, 'swept_low_lvl'):.1f}%      "
          f"both sides {_pct(rows, 'swept_both'):.1f}%")

    counts = defaultdict(int)
    for r in rows:
        for name in filter(None, r["levels"].split("|")):
            counts[name] += 1
    print("\n  levels taken, by name")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {name:<12}{n:>6} days  ({100 * n / len(rows):>4.1f}%)")

    print(f"\nBASELINE A — FADE THE LEG INTO THE WINDOW "
          f"(stop at window extreme, {args.target_r:g}R, flat {FADE_EXIT:%H:%M})")
    print(f"  {'cut':<28}{'trades':>8}{'win%':>8}{'expR':>9}{'totR':>9}")
    _line("all days", rows, "fade_r")
    _line("a real level was swept", swept, "fade_r")
    _line("no level swept", [r for r in rows if not r["swept_any"]], "fade_r")

    print(f"\nBASELINE B — TRADE THE SWEEP'S OWN DIRECTION "
          f"(swept high = sell, swept low = buy)")
    print(f"  {'cut':<28}{'trades':>8}{'win%':>8}{'expR':>9}{'totR':>9}")
    directed = [r for r in rows if r["sweep_side"] != 0]
    _line("every clean sweep", directed, "dir_r")
    _line("swept high → short", [r for r in directed if r["sweep_side"] < 0], "dir_r")
    _line("swept low → long", [r for r in directed if r["sweep_side"] > 0], "dir_r")
    _line("sweep AGREES with fade", [r for r in directed
                                     if r["sweep_side"] == -r["pre_dir"]], "dir_r")
    _line("sweep OPPOSES the fade", [r for r in directed
                                     if r["sweep_side"] == r["pre_dir"]], "dir_r")
    _line("both sides swept (whipsaw)", [r for r in rows if r["swept_both"]], "fade_r")

    print("\nBASELINE B BY LEVEL — which level's sweep carries information")
    print(f"  {'level':<28}{'trades':>8}{'win%':>8}{'expR':>9}{'totR':>9}")
    for name in sorted(counts, key=lambda n: -counts[n]):
        _line(name, [r for r in directed if name in r["levels"].split("|")], "dir_r")

    print("\nBASELINE B BY YEAR")
    print(f"  {'year':<28}{'trades':>8}{'win%':>8}{'expR':>9}{'totR':>9}")
    years = defaultdict(list)
    for r in directed:
        years[r["year"]].append(r)
    for year in sorted(years):
        _line(str(year), years[year], "dir_r", floor=1)
    print()

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        with (out / "killzone_sweeps.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"per-day rows → {out / 'killzone_sweeps.csv'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
