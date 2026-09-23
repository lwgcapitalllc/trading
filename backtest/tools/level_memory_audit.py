"""level_memory_audit.py — the level the bot already traded, tapped AGAIN after the setup died.

Aaron's question (2026-09-22): the Monday-night short filled at 4369.93 (the gap edge the setup
published), closed at a profit stop, and ~20 hours later price came all the way back to that same
price and sold off with nothing placed. *"We did not have any logic to take that trade. Why? How
many trades like this have we been missing?"*

THE POPULATION, and it is NOT one this repo has measured before:
  - Run 41 (`exec_sec_poi_fallback`) only reaches a return while the SETUP IS STILL ALIVE.
  - Runs 27-36 measured setups the primary NEVER traded (no gap on arrival).
  - Run 39 measured the return into the zone from the leg EXTREME, a different geometry.
  This tool measures returns to a level the primary DID trade, AFTER that setup is finished.

THE TRADE GRADED HERE (a short; a long is the mirror):
  LEVEL   the primary's own entry price — the gap edge the bot published and rested a limit at.
  ARMED   from the bar the primary CLOSES, for `--horizon` days.
  ENTRY   a sell limit at LEVEL, filled on the first lower-frame bar whose high reaches it.
  STOP    the SAME distance the original trade was sized against (`Trade.stop_distance`), so
          1R here is 1R there. No new stop rule is invented and nothing is re-derived.
  TARGET  fixed R multiples, walked on the lower frame.
  GATE    the bot must be FLAT at the touch (one position slot), and the touch is tagged with
          whether an armed setup already existed on that side — those are trades the bot could
          already take and must not be counted as missing.

⚠ THIS IS A SCREEN, NOT A BACKTEST. No slot contention with the trades it would queue in front
  of, no portfolio risk budget, no session rules. Rule 12 of the repo applies to the conclusion:
  a positive number here has to survive a real replay before it is an edge.
⚠ A lower-frame bar holding BOTH the stop and the target counts as STOPPED (the pessimistic
  reading, the same convention as `zone_return_audit.py`).
🔴 `--away` (default 1.0R) IS NOT A TUNING KNOB, IT IS THE POPULATION DEFINITION, and the
  first version of this tool shipped without it and was WRONG. A breakeven or profit stop exits AT
  the entry price, so "price returned to the level" is trivially true within minutes of the close:
  a vacuity check at `--horizon 0.01` (14 minutes) still reported 82 returns and a spurious -38R.
  Price must now travel `--away` x the original 1R AWAY from the level, in the original trade's own
  direction, before a return counts. The same check re-run: 2 returns, 0 in the graded group.
  ⚠ Rule 12 in practice — the number was believable, and only a run that should have returned
  NOTHING exposed it.
⚠ 2018-09 -> 2019-12 is left unread; the window starts 2020-01-01 so those months stay a holdout.

Usage:
  python backtest/tools/level_memory_audit.py
  python backtest/tools/level_memory_audit.py --horizon 5 --targets 1 2 3 --ltf M5
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import List

warnings.filterwarnings("ignore")

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

MS_DAY = 86_400_000


@dataclass
class Touch:
    """One return to a level the primary already traded."""

    side: int  # +1 long, -1 short (the ORIGINAL trade's direction)
    level: float
    stop_dist: float
    orig_r: float  # what the original trade made
    orig_entry_ms: int
    orig_exit_ms: int
    touch_ms: int
    hours_after: float
    setup_armed: bool  # an armed setup on this side at the touch -> bot could already act
    flat: bool  # the bot was flat at the touch
    r_by_target: dict  # target multiple -> R booked
    mfe_r: float  # best excursion before the stop, in R


def _load(cache_dir: str, symbol: str, tf: str):
    from backtest.data.cache import BarCache

    return BarCache(_ROOT / cache_dir).load(symbol, tf)


def _ms(idx) -> int:
    return int(idx.value // 1_000_000)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Returns to a level the primary already traded.")
    ap.add_argument("--cache", default="backtest/cache/PUPrime_Demo")
    ap.add_argument("--symbol", default="XAUUSD_p")
    ap.add_argument("--htf", default="M15")
    ap.add_argument("--ltf", default="M5")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--warmup", type=int, default=1000)
    ap.add_argument("--horizon", type=float, default=5.0, help="days the level stays remembered")
    ap.add_argument("--max-hold", type=float, default=3.0, help="days before a time exit")
    ap.add_argument("--targets", type=float, nargs="+", default=[1.0, 1.5, 2.0, 3.0])
    ap.add_argument(
        "--cost",
        type=float,
        default=0.20,
        help="round-trip cost per ounce (PU Prime ECN measures 0.12 spread + 0.02 comm)",
    )
    ap.add_argument("--split", default="2023-05-01")
    ap.add_argument(
        "--stop-frac",
        type=float,
        default=1.0,
        help="stop as a fraction of the ORIGINAL trade's 1R (0.33 = a third as wide)",
    )
    ap.add_argument(
        "--away",
        type=float,
        default=1.0,
        help="price must first travel this many R (of the original stop) AWAY from "
        "the level before a return counts — without it a breakeven exit re-touches "
        "its own level within minutes and floods the sample",
    )
    ap.add_argument(
        "--randoms",
        type=int,
        default=0,
        help="matched random entries per real one (same year, direction, stop, target)",
    )
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--entry",
        default="limit",
        choices=("limit", "reject"),
        help="limit = fill at the level on the touch; reject = wait for the first "
        "lower-frame bar that CLOSES back out of it, enter at that close",
    )
    ap.add_argument("--capital", type=float, default=10_000.0)
    args = ap.parse_args(argv)

    import datetime as dt
    import importlib

    import numpy as np
    import pandas as pd

    df = _load(args.cache, args.symbol, args.htf)
    if df.empty:
        print(f"no cached {args.htf} bars for {args.symbol} under {args.cache}")
        return 1
    ltf = _load(args.cache, args.symbol, args.ltf)
    if ltf.empty:
        print(f"no cached {args.ltf} bars for {args.symbol}")
        return 1

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else df.index[-1]
    df = df[(df.index >= start) & (df.index <= end)]
    ltf = ltf[(ltf.index >= start) & (ltf.index <= end)]
    print(f"{args.symbol}  {args.htf} {len(df):,} bars  {df.index[0]} -> {df.index[-1]}")
    print(f"{args.symbol}  {args.ltf} {len(ltf):,} bars")

    mod = importlib.import_module("strategies.python.sos_fade")
    spec = mod.LAB_STRATEGY
    StrategyCls, ConfigCls = spec["strategy"], spec["config"]
    cfg = ConfigCls(fill_model="bar", symbol="XAUUSD")
    cfg = dataclasses.replace(cfg, exec_secondary=False)

    print(f"replaying sos_fade (warmup {args.warmup}, re-entry off) ...", flush=True)
    strat = StrategyCls(config=cfg, initial_capital=args.capital)
    strat.run(df, warmup=args.warmup)
    trades = [t for t in strat.execution.trades if t.entry_index >= args.warmup]
    print(f"  {len(trades)} primary trades")

    # ── per-bar armed state, indexed by bar time ──────────────────────────────────────────
    bar_ms = np.array([_ms(t) for t in df.index], dtype="int64")
    armed_l = np.zeros(len(df), dtype=bool)
    armed_s = np.zeros(len(df), dtype=bool)
    for d in strat.decisions:
        if 0 <= d.index < len(df):
            armed_l[d.index] = d.l_stage >= 2
            armed_s[d.index] = d.s_stage >= 2

    # ── occupancy: when the single position slot was taken ────────────────────────────────
    busy = sorted((t.entry_ms, t.exit_ms) for t in trades)

    def _flat(ms: int) -> bool:
        for a, b in busy:
            if a <= ms <= b:
                return False
            if a > ms:
                break
        return True

    l_ms = np.array([_ms(t) for t in ltf.index], dtype="int64")
    l_hi = ltf["high"].to_numpy()
    l_lo = ltf["low"].to_numpy()
    l_cl = ltf["close"].to_numpy()

    touches: List[Touch] = []
    for t in trades:
        sd = float(getattr(t, "stop_distance", 0.0) or 0.0)
        if sd <= 0:
            continue
        level = float(t.entry_price)
        side = int(t.dir)
        # the level is remembered from the bar the trade CLOSES
        j0 = int(np.searchsorted(l_ms, t.exit_ms, side="right"))
        j_end = int(np.searchsorted(l_ms, t.exit_ms + int(args.horizon * MS_DAY), side="right"))
        hit = -1
        armed_away = args.away <= 0.0
        for j in range(j0, min(j_end, len(l_ms))):
            if not armed_away:
                # price must first travel AWAY from the level, in the trade's own direction
                gone = (level - l_lo[j]) if side < 0 else (l_hi[j] - level)
                if gone >= args.away * sd:
                    armed_away = True
                continue
            if side < 0 and l_hi[j] >= level:
                hit = j
                break
            if side > 0 and l_lo[j] <= level:
                hit = j
                break
        if hit < 0:
            continue
        tms = int(l_ms[hit])
        k = int(np.searchsorted(bar_ms, tms, side="right")) - 1
        setup_armed = bool((armed_s if side < 0 else armed_l)[k]) if 0 <= k < len(df) else False

        entry = level
        if args.entry == "reject":
            rj = -1
            for j in range(hit, min(hit + 48, len(l_ms))):
                c = float(l_cl[j])
                if (side < 0 and c < level) or (side > 0 and c > level):
                    rj = j
                    break
            if rj < 0:
                continue
            entry = float(l_cl[rj])
            hit = rj + 1  # the next bar is the first one that can fill or stop
            if hit >= len(l_ms):
                continue
            tms = int(l_ms[hit])
            k = int(np.searchsorted(bar_ms, tms, side="right")) - 1
            setup_armed = bool((armed_s if side < 0 else armed_l)[k]) if 0 <= k < len(df) else False
        sd_eff = sd * args.stop_frac
        stop = (
            (level if args.entry == "limit" else max(level, entry)) + sd_eff
            if side < 0
            else (level if args.entry == "limit" else min(level, entry)) - sd_eff
        )
        walk_end = int(np.searchsorted(l_ms, tms + int(args.max_hold * MS_DAY), side="right"))
        r_by = {}
        mfe = 0.0
        for mult in args.targets:
            tgt = entry - mult * sd_eff if side < 0 else entry + mult * sd_eff
            out = None
            for j in range(hit, min(walk_end, len(l_ms))):
                stopped = (l_hi[j] >= stop) if side < 0 else (l_lo[j] <= stop)
                won = (l_lo[j] <= tgt) if side < 0 else (l_hi[j] >= tgt)
                if stopped:  # stop first when a bar holds both
                    out = -1.0
                    break
                if won:
                    out = mult
                    break
            if out is None:  # time exit at the last bar walked
                j = min(walk_end, len(l_ms)) - 1
                px = float(l_cl[j])
                out = ((entry - px) if side < 0 else (px - entry)) / sd_eff
            r_by[mult] = out - args.cost / sd_eff
        for j in range(hit, min(walk_end, len(l_ms))):
            stopped = (l_hi[j] >= stop) if side < 0 else (l_lo[j] <= stop)
            best = (entry - l_lo[j]) if side < 0 else (l_hi[j] - entry)
            mfe = max(mfe, best / sd_eff)
            if stopped:
                break

        touches.append(
            Touch(
                side=side,
                level=entry,
                stop_dist=sd_eff,
                orig_r=float(t.r),
                orig_entry_ms=int(t.entry_ms),
                orig_exit_ms=int(t.exit_ms),
                touch_ms=tms,
                hours_after=(tms - t.exit_ms) / 3_600_000.0,
                setup_armed=setup_armed,
                flat=_flat(tms),
                r_by_target=r_by,
                mfe_r=mfe,
            )
        )

    # ── report ────────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 96)
    print(
        f"RETURNS TO A LEVEL THE PRIMARY ALREADY TRADED   horizon {args.horizon}d  "
        f"hold {args.max_hold}d  cost ${args.cost}/oz  entry={args.entry}  "
        f"stop={args.stop_frac:g}x the original 1R  away={args.away:g}R"
    )
    print("=" * 96)
    print(f"  primaries closed                         {len(trades):>5}")
    print(
        f"  price returned to the entry within {args.horizon:.0f}d   {len(touches):>5}"
        f"   ({100.0 * len(touches) / max(1, len(trades)):.0f}%)"
    )
    usable = [x for x in touches if x.flat and not x.setup_armed]
    print(f"    of those, bot FLAT and NO armed setup   {len(usable):>5}   <- the missing ones")
    print(
        f"    bot already had an armed setup          "
        f"{len([x for x in touches if x.setup_armed]):>5}"
    )
    print(
        f"    bot was IN a position                   {len([x for x in touches if not x.flat]):>5}"
    )

    if not usable:
        print("\nnothing to grade.")
        return 0

    split_ms = _ms(pd.Timestamp(args.split))

    def _grade(name, grp):
        if not grp:
            return
        print(
            f"\nGRADED — {name}  (n={len(grp)}, entry at the level, "
            f"stop = the original trade's own 1R)"
        )
        print(
            f"  {'target':>8}{'total R':>10}{'per trade':>11}{'win%':>7}"
            f"{'  first half':>13}{'second half':>13}{'  drop best':>12}"
        )
        for mult in args.targets:
            rs = [x.r_by_target[mult] for x in grp]
            a = [x.r_by_target[mult] for x in grp if x.touch_ms < split_ms]
            b = [x.r_by_target[mult] for x in grp if x.touch_ms >= split_ms]
            wins = len([r for r in rs if r > 0])
            dropped = sum(sorted(rs)[:-1])
            print(
                f"  {mult:>8.2f}{sum(rs):>10.2f}{sum(rs) / len(rs):>11.3f}"
                f"{100.0 * wins / len(rs):>6.0f}%"
                f"{sum(a):>9.1f} (n{len(a)}){sum(b):>9.1f} (n{len(b)}){dropped:>12.2f}"
            )

    _grade("NO armed setup — the bot had nothing at all", usable)
    _grade(
        "an armed setup was live — the bot had a setup and still placed nothing",
        [x for x in touches if x.flat and x.setup_armed],
    )
    _grade("every flat return, both groups together", [x for x in touches if x.flat])

    print(
        f"\n  median best excursion before the stop: {float(np.median([x.mfe_r for x in usable])):.2f}R"
    )
    print(
        f"  median hours after the primary closed: {float(np.median([x.hours_after for x in usable])):.1f}"
    )

    print("\nPER YEAR")
    years = sorted({dt.datetime.utcfromtimestamp(x.touch_ms / 1000).year for x in usable})
    head = "  year   n" + "".join(f"{('R@' + format(m, 'g')):>10}" for m in args.targets)
    print(head)
    for y in years:
        grp = [x for x in usable if dt.datetime.utcfromtimestamp(x.touch_ms / 1000).year == y]
        row = f"  {y}  {len(grp):>3}"
        for m in args.targets:
            row += f"{sum(x.r_by_target[m] for x in grp):>10.2f}"
        print(row)

    print("\nBY WHAT THE ORIGINAL TRADE DID")
    for label, sel in (
        ("original won (>0.25R)", lambda x: x.orig_r > 0.25),
        ("original scratched", lambda x: -0.25 <= x.orig_r <= 0.25),
        ("original stopped (<-0.25R)", lambda x: x.orig_r < -0.25),
    ):
        grp = [x for x in usable if sel(x)]
        if not grp:
            continue
        row = f"  {label:<28}n{len(grp):>4}"
        for m in args.targets:
            row += f"{sum(x.r_by_target[m] for x in grp):>10.2f}"
        print(row)

    if args.randoms:
        import random

        rng = random.Random(args.seed)
        yr_bars = {}
        for i, ms in enumerate(l_ms):
            yr_bars.setdefault(dt.datetime.utcfromtimestamp(ms / 1000).year, []).append(i)
        print(
            f"\nMATCHED RANDOM CONTROL  ({args.randoms} per real trade, same year, "
            f"same direction, same stop, same target)"
        )
        print(f"  {'target':>8}{'real R':>10}{'random mean':>14}{'random sd':>11}{'z':>7}")
        for mult in args.targets:
            real = sum(x.r_by_target[mult] for x in usable)
            draws = []
            for _ in range(args.randoms):
                tot = 0.0
                for x in usable:
                    y = dt.datetime.utcfromtimestamp(x.touch_ms / 1000).year
                    pool = yr_bars.get(y) or yr_bars[min(yr_bars)]
                    j0 = rng.choice(pool)
                    e = float(l_cl[j0])
                    sd_e, sgn = x.stop_dist, x.side
                    stop = e + sd_e if sgn < 0 else e - sd_e
                    tgt = e - mult * sd_e if sgn < 0 else e + mult * sd_e
                    lim = min(j0 + int(args.max_hold * 288), len(l_ms))
                    out = None
                    for j in range(j0 + 1, lim):
                        if (l_hi[j] >= stop) if sgn < 0 else (l_lo[j] <= stop):
                            out = -1.0
                            break
                        if (l_lo[j] <= tgt) if sgn < 0 else (l_hi[j] >= tgt):
                            out = mult
                            break
                    if out is None:
                        px = float(l_cl[lim - 1])
                        out = ((e - px) if sgn < 0 else (px - e)) / sd_e
                    tot += out - args.cost / sd_e
                draws.append(tot)
            mu = float(np.mean(draws))
            sg = float(np.std(draws)) or 1e-9
            print(f"  {mult:>8.2f}{real:>10.2f}{mu:>14.2f}{sg:>11.2f}{(real - mu) / sg:>7.2f}")

    print("\n⚠ SCREEN ONLY — one position slot is NOT simulated against the trades these would")
    print("  queue in front of. Rule: an added setup displaces rather than adds (Run 12).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
