#!/usr/bin/env python3
"""pre_sos_leg_grid.py — every combination at once, and which timeframe to run it on.

WHY THIS EXISTS AND WHY IT IS NOT `pre_sos_leg_tune.py`. That tool moves ONE knob at a time
around the shipped value. It says so, and it also says what that cannot see: an interaction.
It found exactly one — requiring two liquidity levels to agree was the best single change it
measured and lost more than half the return in combination with the others. **A one-at-a-time
sweep produces candidates, never conclusions.** This tool runs the cartesian product.

🔴 AND THAT IS THE DANGEROUS PART, SO IT IS BUILT AROUND IT. A quarter of a million
configurations searched against roughly two hundred trades will hand back a winner whatever
the data is. The top row of a grid this size is a coin that came up heads eight times; there
is no version of this tool that does not have that problem. What it can do is refuse to
report the top row on its own:

  * **Every configuration is scored on the two calendar halves separately, and the ranking
    that matters is by the WORSE half.** A configuration that made its money in one half is
    a story about that half.
  * **The neighbours of any winner are printed.** A real setting sits on a hill. A lone
    spike surrounded by mediocrity is the search finding noise, and it looks identical to a
    discovery until you look next to it.
  * **Trade count is a column, never a filter.** `CLAUDE.md` -> *Trading Philosophy*: with
    one position slot an extra setup does not add to the book, it queues in front of it.
  * **The shipped configuration is printed on every ranking** so the honest question — is
    the winner actually better than what we already run — is answerable without arithmetic.

WHAT IT INHERITS. Everything that decides what a setup IS comes from `pre_sos_leg.py`, and
the one-position rule from `pre_sos_leg_queued.py`. Nothing here restates a rule. So every
caveat on the parent holds: no news filter, no re-entry cap, no sizing, costs are the
parent's half-spread only, and an unresolved trade is booked as a full loss.

⚠ WHAT THE GRID CANNOT REACH. The strategy file has inputs this study has no model for —
which side to trade, the minimum stop in dollars, the individual level families. The first
two are cheap filters and are IN the grid. The families are a separate stage, because
folding 15 subsets into the product multiplies the search by 15 and buys a question that
can be asked on its own.

Usage:
    python3 backtest/tools/pre_sos_leg_grid.py --stage timeframe
    python3 backtest/tools/pre_sos_leg_grid.py --stage grid --base M15 --confirm M5
    python3 backtest/tools/pre_sos_leg_grid.py --stage families --base M15 --confirm M5
"""

from __future__ import annotations

import argparse
import csv
import itertools
import statistics
import sys
import time
from argparse import Namespace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.tools.pre_sos_leg import (  # noqa: E402
    FAMILIES,
    MINUTES,
    Row,
    Signal,
    atr,
    collect,
    drop_coarse,
    load,
    replay_base,
    replay_confirm,
    walk,
    walk_breakeven,
)

# ⚠ MUST TRACK `indicators/strategies/mpc_extreme_leg_strategy.pine`'s INPUT DEFAULTS. Same
# warning as `pre_sos_leg_tune.py`: if these drift, every table below still prints the word
# "shipped" beside a configuration nobody runs.
SHIPPED = {
    "extreme_minutes": 120,
    "swept_minutes": 180,
    "stop_buffer_atr": 0.20,
    "min_r": 2.0,
    "min_families": 1,
    "counter_trend": True,
    "min_stop": 0.0,
    "tp": 0.5,
    "arm": None,
}

# The grid. Each axis brackets the shipped value rather than starting from it, so a winner
# at an edge is visible AS an edge and can be re-run wider.
AX_EXTREME = (60, 90, 120, 180, 240)
AX_SWEPT = (60, 120, 180, 300)
AX_BUFFER = (0.0, 0.10, 0.20, 0.35, 0.50)
AX_MIN_R = (1.5, 2.0, 2.5, 3.0, 4.0)
AX_FAMILIES = (1, 2, 3)
AX_COUNTER = (True, False)
AX_MIN_STOP = (0.0, 1.0, 2.0)
AX_TP = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0)
AX_ARM = (None, 0.5, 0.7, 0.9)

# The second pass. A coarse grid can only say which SQUARE the winner is in, and a square
# two hours wide is not an answer to "how far back is the extreme looked for". These step
# through the winning square, and they exist so that a peak found on the coarse pass has to
# survive being looked at closely — a hill that flattens out under magnification was a hill
# made of the spacing.
FINE = {
    "extreme": (90, 105, 120, 135, 150, 165, 180),
    "swept": (150, 165, 180, 195, 210, 240),
    "buffer": (0.14, 0.17, 0.20, 0.23, 0.26, 0.30),
    "min_r": (1.75, 2.0, 2.25, 2.5),
    "tp": (0.42, 0.46, 0.50, 0.54, 0.58),
}


# ----------------------------------------------------------------------------- one result


class Cell:
    """One configuration, scored over the whole history and over each calendar half."""

    __slots__ = ("cfg", "n", "wins", "total", "dd", "hold", "years", "a_n", "a_r", "b_n", "b_r")

    def __init__(self, cfg: Dict, n, wins, total, dd, hold, years, a_n, a_r, b_n, b_r):
        self.cfg = cfg
        self.n, self.wins, self.total, self.dd = n, wins, total, dd
        self.hold, self.years = hold, years
        self.a_n, self.a_r, self.b_n, self.b_r = a_n, a_r, b_n, b_r

    @property
    def hit(self) -> float:
        return self.wins / self.n if self.n else 0.0

    @property
    def exp(self) -> float:
        return self.total / self.n if self.n else 0.0

    @property
    def ratio(self) -> float:
        return self.total / self.dd if self.dd > 0 else 0.0

    @property
    def per_year(self) -> float:
        return self.n / self.years if self.years else 0.0

    @property
    def worse_half(self) -> float:
        """The worse calendar half's total R, doubled so it reads on the full-history scale.

        This is the ranking that decides. Total R alone rewards a configuration that found
        one good stretch; this one cannot be won that way.
        """
        return 2.0 * min(self.a_r, self.b_r)

    def row(self) -> str:
        return (
            f"n={self.n:4d} ({self.per_year:4.1f}/yr) hit={self.hit:5.1%} exp={self.exp:+.3f}R "
            f"tot={self.total:+7.1f}R DD={self.dd:5.1f}R R/DD={self.ratio:5.2f} "
            f"halves {self.a_r:+6.1f}/{self.b_r:+6.1f}R hold={self.hold:5.0f}m"
        )


def _fmt_arm(a: Optional[float]) -> str:
    return "--" if a is None else f"{a:.0%}"


def label_of(cfg: Dict) -> str:
    return (
        f"ext{cfg['extreme_minutes']:>3d} swp{cfg['swept_minutes']:>3d} "
        f"buf{cfg['stop_buffer_atr']:.2f} R>={cfg['min_r']:.1f} fam{cfg['min_families']} "
        f"{'ct' if cfg['counter_trend'] else 'any':>3s} minstop{cfg['min_stop']:.0f} "
        f"tp{cfg['tp']:.0%} be{_fmt_arm(cfg['arm']):>3s}"
    )


# ----------------------------------------------------------------------------- the machinery


def prepare(broker: str, symbol: str, base_tf: str, confirm_tf: str):
    """Load and replay one timeframe pair. This is the whole cost — everything else is cheap."""
    base_rows = drop_coarse(load(broker, symbol, base_tf), MINUTES[base_tf])
    same = base_tf == confirm_tf
    fast_rows = (
        base_rows if same else drop_coarse(load(broker, symbol, confirm_tf), MINUTES[confirm_tf])
    )
    base = replay_base(base_rows)
    shifts = replay_confirm(fast_rows, same)
    a_fast = atr(fast_rows)
    return base_rows, fast_rows, base, shifts, a_fast


def pool_for(
    fast, base, shifts, a_fast, args, extreme, swept, buffer, on_base_close: bool = False
) -> List[Signal]:
    ns = Namespace(
        confirm=args.confirm,
        base=args.base,
        spread=args.spread,
        horizon_minutes=args.horizon_minutes,
        entry_on_base_close=on_base_close,
        extreme_minutes=extreme,
        swept_minutes=swept,
        stop_buffer_atr=buffer,
    )
    return collect(fast, base, shifts, a_fast, ns)


def rewalk(
    sigs: Sequence[Signal], fast: Sequence[Row], horizon: int, tp: float, arm: Optional[float]
) -> List[Tuple[str, int]]:
    """Re-resolve every setup in the pool under one exit rule.

    Done ONCE per (pool, exit rule) and shared by every filter combination underneath it,
    because a filter cannot change when a trade ended — only which trades are looked at.
    That sharing is the only reason a grid this size finishes.
    """
    out: List[Tuple[str, int]] = []
    for s in sigs:
        span = abs(s.target - s.entry)
        tgt = s.entry + s.direction * span * tp
        if s.direction * (tgt - s.entry) <= 0.0:
            # The swing is so close that a fraction of the way to it ROUNDS ONTO THE ENTRY.
            # Not a trade: there is no distance to book. It is reported as such rather than
            # walked, because a zero-width target divides by zero in the walk — which is how
            # this was found, on a same-frame pair where the swing sits a rounding error from
            # the close. A skipped setup does NOT take the slot; nothing was entered.
            out.append(("skip", s.i))
            continue
        if arm is None:
            outcome, _, ex = walk(fast, s.i, s.direction, s.entry, s.stop, tgt, horizon)
        else:
            outcome, ex = walk_breakeven(fast, s.i, s.direction, s.entry, s.stop, tgt, horizon, arm)
        out.append((outcome, ex))
    return out


def drawdown(rs: Sequence[float]) -> float:
    peak = run = worst = 0.0
    for r in rs:
        run += r
        peak = max(peak, run)
        worst = max(worst, peak - run)
    return worst


def slot_run(
    sigs: Sequence[Signal],
    walked: Sequence[Tuple[str, int]],
    keep: Sequence[bool],
    tp: float,
    spread: float,
    lo: int,
    hi: int,
) -> Tuple[List[float], int, List[int]]:
    """Take what one position can reach, inside a bar range.

    The filter is applied BEFORE the slot: a setup the strategy refuses never occupies the
    slot, so a stricter filter genuinely buys later setups. Doing it the other way round
    measures a strategy that decides its own rules after seeing what it missed.
    """
    rs: List[float] = []
    holds: List[int] = []
    wins = 0
    free_at = -1
    for k, s in enumerate(sigs):
        if not keep[k] or s.i < lo or s.i >= hi or s.i < free_at:
            continue
        outcome, ex = walked[k]
        if outcome == "skip":
            continue
        free_at = ex
        holds.append(ex - s.i)
        if outcome == "win":
            wins += 1
            rs.append(s.r_available * tp)
        elif outcome == "scratch":
            rs.append(-(spread / 2.0) / s.risk)
        else:
            rs.append(-1.0)
    return rs, wins, holds


def evaluate(
    sigs, walked, keep, cfg, tp, spread, mid, span_years, confirm_minutes, n_fast
) -> Optional[Cell]:
    rs, wins, holds = slot_run(sigs, walked, keep, tp, spread, 0, n_fast)
    if not rs:
        return None
    a_rs, _, _ = slot_run(sigs, walked, keep, tp, spread, 0, mid)
    b_rs, _, _ = slot_run(sigs, walked, keep, tp, spread, mid, n_fast)
    hold = statistics.median(holds) * confirm_minutes if holds else 0.0
    return Cell(
        cfg,
        len(rs),
        wins,
        sum(rs),
        drawdown(rs),
        hold,
        span_years,
        len(a_rs),
        sum(a_rs),
        len(b_rs),
        sum(b_rs),
    )


# ----------------------------------------------------------------------------- reporting


def show(title: str, cells: Sequence[Cell], key, n_floor: int, limit: int = 12) -> None:
    print(f"\n=== {title} ===")
    pool = [c for c in cells if c.n >= n_floor]
    if not pool:
        print("  nothing clears the trade-count floor")
        return
    for c in sorted(pool, key=key, reverse=True)[:limit]:
        print(f"  {label_of(c.cfg)}  {c.row()}")


def neighbours(cells: Sequence[Cell], win: Dict, axes: Dict[str, Sequence]) -> None:
    """Walk each axis away from the winner with everything else held. A real setting is a hill."""
    print("\n=== the winner's neighbours, one axis at a time ===")
    print("    a lone spike here is the search finding noise, not a setting")
    index = {tuple(sorted(c.cfg.items(), key=lambda kv: kv[0])): c for c in cells}
    for name, values in axes.items():
        parts = []
        for v in values:
            probe = dict(win)
            probe[name] = v
            c = index.get(tuple(sorted(probe.items(), key=lambda kv: kv[0])))
            if c is None:
                continue
            mark = "*" if v == win[name] else " "
            shown = (
                _fmt_arm(v) if name == "arm" else (str(v) if not isinstance(v, float) else f"{v:g}")
            )
            parts.append(f"{mark}{shown}={c.total:+.1f}R/{c.worse_half:+.1f}w")
        print(f"  {name:16s} " + "  ".join(parts))


def compounded(rs: Sequence[float], risk_pct: float) -> Tuple[float, float]:
    """What a compounding account actually does. Returns (multiple, worst drawdown percent)."""
    eq = 1.0
    peak = 1.0
    worst = 0.0
    for r in rs:
        eq *= 1.0 + r * risk_pct / 100.0
        if eq <= 0:
            return 0.0, 100.0
        peak = max(peak, eq)
        worst = max(worst, 1.0 - eq / peak)
    return eq, worst * 100.0


# ----------------------------------------------------------------------------- stages


def stage_timeframe(args) -> None:
    """Which pair of frames? The frame that finds the level and swing, and the one that triggers."""
    pairs = [p.split("/") for p in args.pairs.split(",")]
    print("=== the shipped rules, on every pair of frames ===")
    print("    base = where the level and the target swing come from; confirm = what triggers")
    print("    same numbers, same rules, only the chart changes\n")
    header = (
        f"  {'base/confirm':13s} {'n':>5s} {'/yr':>5s} {'hit':>6s} {'exp':>8s} "
        f"{'total':>9s} {'DD':>7s} {'R/DD':>6s} {'halves':>15s} {'hold':>8s}"
    )
    print(header)
    for base_tf, confirm_tf in pairs:
        if MINUTES[confirm_tf] > MINUTES[base_tf]:
            print(f"  {base_tf}/{confirm_tf:9s} refused — the trigger frame must not be slower")
            continue
        t0 = time.time()
        args.base, args.confirm = base_tf, confirm_tf
        try:
            base_rows, fast, base, shifts, a_fast = prepare(
                args.broker, args.symbol, base_tf, confirm_tf
            )
        except SystemExit as exc:
            print(f"  {base_tf}/{confirm_tf:9s} no data — {exc}")
            continue
        horizon = args.horizon_minutes // MINUTES[confirm_tf]
        sigs = pool_for(
            fast,
            base,
            shifts,
            a_fast,
            args,
            SHIPPED["extreme_minutes"],
            SHIPPED["swept_minutes"],
            SHIPPED["stop_buffer_atr"],
        )
        span_years = (fast[-1].ts - fast[0].ts) / (1000 * 60 * 60 * 24 * 365.25)
        keep = [
            s.r_available >= SHIPPED["min_r"]
            and s.counter_trend
            and len(s.families) >= SHIPPED["min_families"]
            for s in sigs
        ]
        walked = rewalk(sigs, fast, horizon, SHIPPED["tp"], SHIPPED["arm"])
        cell = evaluate(
            sigs,
            walked,
            keep,
            dict(SHIPPED),
            SHIPPED["tp"],
            args.spread,
            len(fast) // 2,
            span_years,
            MINUTES[confirm_tf],
            len(fast),
        )
        if cell is None:
            print(f"  {base_tf}/{confirm_tf:9s} no setups at all")
            continue
        print(
            f"  {base_tf + '/' + confirm_tf:13s} {cell.n:5d} {cell.per_year:5.1f} {cell.hit:6.1%} "
            f"{cell.exp:+8.3f} {cell.total:+8.1f}R {cell.dd:6.1f}R {cell.ratio:6.2f} "
            f"{cell.a_r:+7.1f}/{cell.b_r:+6.1f} {cell.hold:7.0f}m   ({time.time() - t0:.0f}s, "
            f"{len(shifts)} triggers)"
        )


def stage_grid(args) -> None:
    global \
        AX_EXTREME, \
        AX_SWEPT, \
        AX_BUFFER, \
        AX_MIN_R, \
        AX_TP, \
        AX_FAMILIES, \
        AX_COUNTER, \
        AX_MIN_STOP, \
        AX_ARM
    if args.quick:
        # A CHALLENGER FRAME still has to be re-tuned before it is dismissed, or the sweep
        # only proves that settings tuned on one chart do not transfer to another — which
        # nobody doubted. The full product is unaffordable on a 1-minute trigger (millions
        # of bar steps per walk), so this asks the smaller question honestly: with the
        # structure rules held, is there ANY exit and any filter that makes the frame pay?
        AX_EXTREME = (120,)
        AX_SWEPT = (120, 180, 300)
        AX_BUFFER = (0.20,)
        AX_MIN_R = (1.5, 2.0, 3.0)
        AX_TP = (0.3, 0.5, 0.7, 1.0)
        AX_FAMILIES = (1, 2)
        AX_COUNTER = (True,)
        AX_MIN_STOP = (0.0,)
        AX_ARM = (None, 0.7)
    elif args.fine:
        # everything the coarse pass settled is PINNED here rather than re-searched. Leaving
        # a settled axis open would let the fine pass move it on a difference the coarse pass
        # already showed is noise, and then the two winners disagree for no reason.
        AX_EXTREME = FINE["extreme"]
        AX_SWEPT = FINE["swept"]
        AX_BUFFER = FINE["buffer"]
        AX_MIN_R = FINE["min_r"]
        AX_TP = FINE["tp"]
        AX_FAMILIES = (1,)
        AX_COUNTER = (True,)
        AX_MIN_STOP = (0.0,)
        AX_ARM = (None,)
    base_rows, fast, base, shifts, a_fast = prepare(
        args.broker, args.symbol, args.base, args.confirm
    )
    horizon = args.horizon_minutes // MINUTES[args.confirm]
    span_years = (fast[-1].ts - fast[0].ts) / (1000 * 60 * 60 * 24 * 365.25)
    mid = len(fast) // 2
    print(
        f"{args.base} base / {args.confirm} confirm — "
        f"{datetime.utcfromtimestamp(fast[0].ts / 1000):%Y-%m-%d} to "
        f"{datetime.utcfromtimestamp(fast[-1].ts / 1000):%Y-%m-%d} "
        f"({span_years:.1f} years, {len(shifts)} triggers)"
    )
    total_cfgs = (
        len(AX_EXTREME)
        * len(AX_SWEPT)
        * len(AX_BUFFER)
        * len(AX_TP)
        * len(AX_ARM)
        * len(AX_MIN_R)
        * len(AX_FAMILIES)
        * len(AX_COUNTER)
        * len(AX_MIN_STOP)
    )
    print(f"grid: {total_cfgs} configurations\n")

    cells: List[Cell] = []
    t0 = time.time()
    done = 0
    for extreme, swept, buffer in itertools.product(AX_EXTREME, AX_SWEPT, AX_BUFFER):
        sigs = pool_for(fast, base, shifts, a_fast, args, extreme, swept, buffer)
        # per-signal facts that no exit rule and no filter can move
        fam_n = [len(s.families) for s in sigs]
        for tp, arm in itertools.product(AX_TP, AX_ARM):
            walked = rewalk(sigs, fast, horizon, tp, arm)
            for min_r, fams, ct, min_stop in itertools.product(
                AX_MIN_R, AX_FAMILIES, AX_COUNTER, AX_MIN_STOP
            ):
                keep = [
                    s.r_available >= min_r
                    and fam_n[k] >= fams
                    and (s.counter_trend or not ct)
                    and s.risk >= min_stop
                    for k, s in enumerate(sigs)
                ]
                cfg = {
                    "extreme_minutes": extreme,
                    "swept_minutes": swept,
                    "stop_buffer_atr": buffer,
                    "min_r": min_r,
                    "min_families": fams,
                    "counter_trend": ct,
                    "min_stop": min_stop,
                    "tp": tp,
                    "arm": arm,
                }
                cell = evaluate(
                    sigs,
                    walked,
                    keep,
                    cfg,
                    tp,
                    args.spread,
                    mid,
                    span_years,
                    MINUTES[args.confirm],
                    len(fast),
                )
                if cell is not None:
                    cells.append(cell)
                done += 1
        print(
            f"  {done}/{total_cfgs} configurations  {time.time() - t0:5.0f}s", end="\r", flush=True
        )
    print(f"\n{len(cells)} scored in {time.time() - t0:.0f}s")

    floor = args.n_floor
    show(
        "ranked by the WORSE calendar half — the one that decides",
        cells,
        lambda c: c.worse_half,
        floor,
    )
    show(
        "ranked by total R — what a grid search will always sell you",
        cells,
        lambda c: c.total,
        floor,
    )
    show("ranked by return over worst drawdown", cells, lambda c: c.ratio, floor)
    show(
        "ranked by trades per year, among configurations that make money",
        [c for c in cells if c.worse_half > 0],
        lambda c: c.per_year,
        floor,
    )

    ship = [c for c in cells if all(c.cfg[k] == v for k, v in SHIPPED.items())]
    if ship:
        print("\n=== what we ship today, for comparison ===")
        print(f"  {label_of(ship[0].cfg)}  {ship[0].row()}")

    best = max((c for c in cells if c.n >= floor), key=lambda c: c.worse_half, default=None)
    if best is not None:
        neighbours(
            cells,
            best.cfg,
            {
                "extreme_minutes": AX_EXTREME,
                "swept_minutes": AX_SWEPT,
                "stop_buffer_atr": AX_BUFFER,
                "min_r": AX_MIN_R,
                "min_families": AX_FAMILIES,
                "min_stop": AX_MIN_STOP,
                "tp": AX_TP,
                "arm": AX_ARM,
            },
        )

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(
                list(SHIPPED)
                + [
                    "n",
                    "per_year",
                    "hit",
                    "exp",
                    "total",
                    "dd",
                    "ratio",
                    "worse_half",
                    "first_half_r",
                    "second_half_r",
                    "median_hold_minutes",
                ]
            )
            for c in cells:
                w.writerow(
                    [c.cfg[k] for k in SHIPPED]
                    + [
                        c.n,
                        round(c.per_year, 2),
                        round(c.hit, 4),
                        round(c.exp, 4),
                        round(c.total, 2),
                        round(c.dd, 2),
                        round(c.ratio, 3),
                        round(c.worse_half, 2),
                        round(c.a_r, 2),
                        round(c.b_r, 2),
                        round(c.hold, 1),
                    ]
                )
        print(f"\nwrote {len(cells)} rows to {p}")


def stage_families(args) -> None:
    """Which kinds of level are worth arming on — every subset, not one at a time."""
    base_rows, fast, base, shifts, a_fast = prepare(
        args.broker, args.symbol, args.base, args.confirm
    )
    horizon = args.horizon_minutes // MINUTES[args.confirm]
    span_years = (fast[-1].ts - fast[0].ts) / (1000 * 60 * 60 * 24 * 365.25)
    mid = len(fast) // 2
    sigs = pool_for(
        fast,
        base,
        shifts,
        a_fast,
        args,
        args.extreme_minutes,
        args.swept_minutes,
        args.stop_buffer_atr,
    )
    walked = rewalk(sigs, fast, horizon, args.tp, None if args.arm < 0 else args.arm)
    print(f"\n=== which level families to arm on ({args.base}/{args.confirm}) ===")
    print("    every subset, with the rest of the configuration held")
    out = []
    for k in range(1, len(FAMILIES) + 1):
        for subset in itertools.combinations(FAMILIES, k):
            for fams in (1, 2):
                if fams > k:
                    continue
                keep = [
                    s.r_available >= args.min_r
                    and s.counter_trend
                    and len([f for f in s.families if f in subset]) >= fams
                    for s in sigs
                ]
                cell = evaluate(
                    sigs,
                    walked,
                    keep,
                    {"subset": subset, "fams": fams},
                    args.tp,
                    args.spread,
                    mid,
                    span_years,
                    MINUTES[args.confirm],
                    len(fast),
                )
                if cell is not None and cell.n >= args.n_floor:
                    out.append((subset, fams, cell))
    for subset, fams, c in sorted(out, key=lambda t: t[2].worse_half, reverse=True):
        print(f"  {'+'.join(subset):32s} >={fams}  {c.row()}")


def stage_risk(args) -> None:
    """What risk percent survives the configuration you land on."""
    base_rows, fast, base, shifts, a_fast = prepare(
        args.broker, args.symbol, args.base, args.confirm
    )
    horizon = args.horizon_minutes // MINUTES[args.confirm]
    sigs = pool_for(
        fast,
        base,
        shifts,
        a_fast,
        args,
        args.extreme_minutes,
        args.swept_minutes,
        args.stop_buffer_atr,
    )
    walked = rewalk(sigs, fast, horizon, args.tp, None if args.arm < 0 else args.arm)
    keep = [
        s.r_available >= args.min_r
        and s.counter_trend
        and len(s.families) >= args.min_families
        and s.risk >= args.min_stop
        for s in sigs
    ]
    rs, wins, holds = slot_run(sigs, walked, keep, args.tp, args.spread, 0, len(fast))
    print(f"\n=== risk percent, on {len(rs)} trades ===")
    print("    compounding, one position at a time, and the 'twice as deep' column is the")
    print("    honest planning number — the worst run measured is not the worst run there is")
    print(f"  {'risk':>6s} {'multiple':>12s} {'worst DD':>10s} {'if twice as deep':>18s}")
    for pct in (1.0, 2.0, 2.5, 5.0, 7.5, 10.0):
        mult, dd = compounded(rs, pct)
        deep = compounded([r * 2 if r < 0 else r for r in rs], pct)[1]
        print(f"  {pct:5.1f}% {mult:11.1f}x {dd:9.1f}% {deep:17.1f}%")


def stage_extras(args) -> None:
    """The two questions a cartesian grid should NOT be asked, measured on their own.

    WHICH SIDE TO TRADE is the classic search trap on this instrument: gold went 1,200 to
    4,600 across this window, so "longs only" wins on any dataset that contains it and the
    win says nothing about the setup. It is reported here, alone, so it can be read as the
    fact about GOLD that it is rather than picked up as a setting.

    WHEN TO FILL is an ARCHITECTURE question, not a preference — filling at the next base
    close is what a strategy charted on the base frame can do without a second frame. The
    entry moves, the stop and the target do not, and the fill can only ever be later.
    """
    base_rows, fast, base, shifts, a_fast = prepare(
        args.broker, args.symbol, args.base, args.confirm
    )
    horizon = args.horizon_minutes // MINUTES[args.confirm]
    span_years = (fast[-1].ts - fast[0].ts) / (1000 * 60 * 60 * 24 * 365.25)
    mid = len(fast) // 2
    arm = None if args.arm < 0 else args.arm

    def base_keep(sigs):
        return [
            s.r_available >= args.min_r
            and s.counter_trend
            and len(s.families) >= args.min_families
            and s.risk >= args.min_stop
            for s in sigs
        ]

    for on_close, name in (
        (False, "fill at the trigger bar's close"),
        (True, "fill at the next base-frame close"),
    ):
        sigs = pool_for(
            fast,
            base,
            shifts,
            a_fast,
            args,
            args.extreme_minutes,
            args.swept_minutes,
            args.stop_buffer_atr,
            on_close,
        )
        walked = rewalk(sigs, fast, horizon, args.tp, arm)
        keep = base_keep(sigs)
        if not on_close:
            print(f"\n=== which side to trade ({args.base}/{args.confirm}) ===")
            print("    gold trended one way across this whole window — read this as a fact about")
            print("    the instrument, not as a setting to turn on")
            for want, side in ((0, "both sides"), (1, "longs only"), (-1, "shorts only")):
                k = [keep[i] and (want == 0 or s.direction == want) for i, s in enumerate(sigs)]
                c = evaluate(
                    sigs,
                    walked,
                    k,
                    {"side": side},
                    args.tp,
                    args.spread,
                    mid,
                    span_years,
                    MINUTES[args.confirm],
                    len(fast),
                )
                if c is not None:
                    print(f"  {side:14s} {c.row()}")
            print(f"\n=== when the order is filled ({args.base}/{args.confirm}) ===")
        c = evaluate(
            sigs,
            walked,
            keep,
            {"entry": name},
            args.tp,
            args.spread,
            mid,
            span_years,
            MINUTES[args.confirm],
            len(fast),
        )
        if c is not None:
            print(f"  {name:34s} {c.row()}")


# ----------------------------------------------------------------------------- the losers

# Windows in UTC. Named rather than numbered because an hour cut chosen by a search is the
# purest form of the thing this file warns about, while "do not trade the Asian session" is a
# claim about the market that a person can agree or disagree with before seeing its number.
WINDOWS = {
    "any hour": tuple(range(24)),
    "not Asia": tuple(range(7, 24)),
    "London and New York": tuple(range(7, 21)),
    "London only": tuple(range(7, 13)),
    "New York only": tuple(range(12, 21)),
    "not the last hours": tuple(range(0, 21)),
}
AX_RISK_ATR_MIN = (0.0, 0.5, 0.8, 1.0)
AX_RISK_ATR_MAX = (99.0, 2.0, 2.5, 3.0)
AX_R_MAX = (99.0, 5.0, 8.0, 12.0)
AX_WEEKDAY = ("all", "not Friday", "not Monday")


def _weekday(fast, i: int) -> int:
    return datetime.utcfromtimestamp(fast[i].ts / 1000).weekday()


def taken_trades(sigs, walked, keep, tp, spread, n_fast):
    """The trades a single slot actually took, with what each one booked."""
    out = []
    free_at = -1
    for k, s in enumerate(sigs):
        if not keep[k] or s.i < free_at:
            continue
        outcome, ex = walked[k]
        if outcome == "skip":
            continue
        free_at = ex
        if outcome == "win":
            r = s.r_available * tp
        elif outcome == "scratch":
            r = -(spread / 2.0) / s.risk
        else:
            r = -1.0
        out.append((s, outcome, r, ex))
    return out


def bucket(name: str, rows, mid: int) -> None:
    if not rows:
        print(f"  {name:26s} none")
        return
    wins = sum(1 for _, o, _, _ in rows if o == "win")
    tot = sum(r for _, _, r, _ in rows)
    a = sum(r for s, _, r, _ in rows if s.i < mid)
    b = tot - a
    print(
        f"  {name:26s} n={len(rows):4d}  hit={wins / len(rows):5.1%}  "
        f"tot={tot:+7.1f}R  per trade={tot / len(rows):+.3f}R  halves {a:+6.1f}/{b:+6.1f}R"
    )


def stage_losers(args) -> None:
    """Where do the losses come from, and can any of them be refused without losing the winners?

    🔴 THIS IS THE MOST OVERFITTABLE QUESTION IN THE FILE, and it is worth saying why rather
    than only warning. Every previous stage searched settings that were already part of the
    strategy. This one searches for a NEW rule, using the losses it is trying to remove as the
    thing that suggests it — so a rule found here has been fitted to the exact trades it is
    then scored on. Dropping the worst 20 trades of 208 always looks brilliant.

    Three things are done about it, and none of them is a fix:
      * a cut is applied BEFORE the slot, so refusing a setup genuinely buys whatever came
        next. Scoring a cut by deleting rows from the result measures a strategy that could
        see the future, and it flatters every cut ever tried.
      * every cut is reported on both calendar halves. A cut that only works in one is the
        search remembering, not learning.
      * the axes are things a trader can state a REASON for — a session, a stop that is tiny
        or huge relative to the day's range, a target so far away the trade cannot finish.
        An hour-by-hour cut is not offered, because it would win and it would mean nothing.
    """
    base_rows, fast, base, shifts, a_fast = prepare(
        args.broker, args.symbol, args.base, args.confirm
    )
    horizon = args.horizon_minutes // MINUTES[args.confirm]
    span_years = (fast[-1].ts - fast[0].ts) / (1000 * 60 * 60 * 24 * 365.25)
    mid = len(fast) // 2
    sigs = pool_for(
        fast,
        base,
        shifts,
        a_fast,
        args,
        args.extreme_minutes,
        args.swept_minutes,
        args.stop_buffer_atr,
    )
    walked = rewalk(sigs, fast, horizon, args.tp, None)
    base_keep = [
        s.r_available >= args.min_r and s.counter_trend and len(s.families) >= args.min_families
        for s in sigs
    ]
    rows = taken_trades(sigs, walked, base_keep, args.tp, args.spread, len(fast))
    print(f"\n=== the {len(rows)} trades the strategy actually takes, cut up ===")
    print("    read the halves column first: a bucket that only works in one half is noise")

    print("\n-- how each trade ended --")
    for o in ("win", "loss", "open"):
        bucket(
            {"win": "hit the target", "loss": "hit the stop", "open": "ran out of time"}[o],
            [r for r in rows if r[1] == o],
            mid,
        )

    print("\n-- by session (UTC hour the trade was entered) --")
    for name, hours in WINDOWS.items():
        if name == "any hour":
            continue
        bucket(name, [r for r in rows if r[0].hour in hours], mid)
    bucket("Asia only (00-07)", [r for r in rows if r[0].hour < 7], mid)
    bucket("the last hours (21-24)", [r for r in rows if r[0].hour >= 21], mid)

    print("\n-- by day of week --")
    for d, nm in enumerate(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Sat", "Sun")):
        g = [r for r in rows if _weekday(fast, r[0].i) == d]
        if g:
            bucket(nm, g, mid)

    print("\n-- by how big the stop is against the day's average range --")
    for lo, hi in ((0.0, 0.5), (0.5, 0.8), (0.8, 1.2), (1.2, 2.0), (2.0, 3.0), (3.0, 99.0)):
        bucket(
            f"stop {lo:.1f}-{hi:.1f} x range", [r for r in rows if lo <= r[0].risk_atr < hi], mid
        )

    print("\n-- by how far away the swing is, in stops --")
    for lo, hi in ((2.0, 3.0), (3.0, 4.0), (4.0, 6.0), (6.0, 9.0), (9.0, 99.0)):
        bucket(
            f"swing {lo:.0f}-{hi:.0f} stops away",
            [r for r in rows if lo <= r[0].r_available < hi],
            mid,
        )

    print("\n-- by direction --")
    bucket("long", [r for r in rows if r[0].direction > 0], mid)
    bucket("short", [r for r in rows if r[0].direction < 0], mid)

    print("\n-- by which kinds of level were swept --")
    for f in FAMILIES:
        bucket(f"{f} among them", [r for r in rows if f in r[0].families], mid)

    print("\n=== every combination of the cuts that have a reason behind them ===")
    print("    ranked by the worse half; the shipped rules are the row with no cuts at all")
    wd = [_weekday(fast, s.i) for s in sigs]
    cells: List[Cell] = []
    for win_name, hours in WINDOWS.items():
        hourset = set(hours)
        for rmin, rmax, r_max, day in itertools.product(
            AX_RISK_ATR_MIN, AX_RISK_ATR_MAX, AX_R_MAX, AX_WEEKDAY
        ):
            if rmin >= rmax:
                continue
            keep = [
                base_keep[k]
                and s.hour in hourset
                and rmin <= s.risk_atr < rmax
                and s.r_available <= r_max
                and not (day == "not Friday" and wd[k] == 4)
                and not (day == "not Monday" and wd[k] == 0)
                for k, s in enumerate(sigs)
            ]
            cfg = {
                "window": win_name,
                "stop_atr_min": rmin,
                "stop_atr_max": rmax,
                "swing_max": r_max,
                "weekday": day,
            }
            c = evaluate(
                sigs,
                walked,
                keep,
                cfg,
                args.tp,
                args.spread,
                mid,
                span_years,
                MINUTES[args.confirm],
                len(fast),
            )
            if c is not None:
                cells.append(c)

    def lab(c) -> str:
        g = c.cfg
        hi = "any" if g["stop_atr_max"] > 90 else f"{g['stop_atr_max']:.1f}"
        sw = "any" if g["swing_max"] > 90 else f"{g['swing_max']:.0f}"
        return (
            f"{g['window']:19s} stop {g['stop_atr_min']:.1f}-{hi:>3s} x range  "
            f"swing<={sw:>3s}  {g['weekday']:10s}"
        )

    print(f"\n  {len(cells)} combinations")
    for c in sorted(
        [x for x in cells if x.n >= args.n_floor], key=lambda x: x.worse_half, reverse=True
    )[:15]:
        print(f"  {lab(c)}  {c.row()}")
    shipped_cell = [
        c
        for c in cells
        if c.cfg
        == {
            "window": "any hour",
            "stop_atr_min": 0.0,
            "stop_atr_max": 99.0,
            "swing_max": 99.0,
            "weekday": "all",
        }
    ]
    if shipped_cell:
        print("\n  no cuts at all (what you run today):")
        print(f"  {lab(shipped_cell[0])}  {shipped_cell[0].row()}")


# ----------------------------------------------------------------------------- the ladder

# Fractions of the way to the swing for the FIRST exit, the SECOND exit, and how much of the
# position leaves at the first. The shipped rule is the degenerate member of this family:
# everything off at half way, which is w1 = 1.0.
AX_TP1 = (0.2, 0.3, 0.4, 0.5, 0.6)
# 0.5 and 0.6 are here because a ladder can be FASTER than the shipped single exit as
# well as slower, and a search that only offers slower ones has decided the answer.
AX_TP2 = (0.5, 0.6, 0.7, 0.8, 1.0)
AX_SPLIT = (0.25, 0.33, 0.5, 0.67, 0.75)


def walk_ladder(
    rows: Sequence[Row],
    i: int,
    direction: int,
    entry: float,
    stop: float,
    target: float,
    horizon: int,
    r_available: float,
    risk: float,
    spread: float,
    tp1: float,
    tp2: float,
    split: float,
    be_after_first: bool,
) -> Tuple[bool, float, int]:
    """Take `split` of the position at `tp1` of the way, the rest at `tp2`. Returns (any part
    won, R booked, the bar the last part was let go on).

    ⚠ THE PESSIMISTIC CONVENTIONS ARE THE PARENT'S AND MUST STAY THAT WAY, or a ladder is
    compared against a single exit that was scored more harshly than it was. A bar holding
    both the stop and a target books the STOP. A move to breakeven arms only AFTER the bar
    that reached the trigger has finished, so the original stop governs that bar — nothing in
    a bar tells you the order its extremes came in. A trade that reaches neither end inside
    the horizon books the unfinished part as a FULL loss.

    ⚠ Exiting at the entry price is not free: the entry already carries half the spread and
    getting out gives the other half back, so a breakeven exit is charged, not zero.
    """
    span = abs(target - entry)
    p1 = entry + direction * span * tp1
    p2 = entry + direction * span * tp2
    live_stop = stop
    first_done = False
    booked = 0.0
    rest = 1.0
    end = min(i + 1 + horizon, len(rows))
    for j in range(i + 1, end):
        r = rows[j]
        hit_stop = r.l <= live_stop if direction > 0 else r.h >= live_stop
        if hit_stop:
            loss = -(spread / 2.0) / risk if (first_done and be_after_first) else -1.0
            return first_done, booked + rest * loss, j
        hit_2 = r.h >= p2 if direction > 0 else r.l <= p2
        if hit_2:
            return True, booked + rest * r_available * tp2, j
        if not first_done:
            hit_1 = r.h >= p1 if direction > 0 else r.l <= p1
            if hit_1:
                first_done = True
                booked += split * r_available * tp1
                rest = 1.0 - split
                if be_after_first:
                    live_stop = entry
    return first_done, booked + rest * -1.0, max(i, end - 1)


def stage_ladder(args) -> None:
    """Is one exit price the best this can do, or is there money in letting part of it run?

    WHY IT IS WORTH ASKING. The parent study measured that a trade which gets 70% of the way
    to the swing finishes 79% of the time. A single exit at half way collects none of that.
    A ladder is the only way to hold both facts at once — most trades do not get far, and the
    ones that do usually arrive.

    ⚠ AND WHY IT MIGHT STILL LOSE: the strategy holds ONE position, so a ladder keeps the slot
    occupied longer than a single exit does. Whatever the remainder earns has to beat whatever
    the next setup would have earned in the time it was held. That is invisible to any test
    that scores trades one at a time, and it is why the slot is applied here too.
    """
    base_rows, fast, base, shifts, a_fast = prepare(
        args.broker, args.symbol, args.base, args.confirm
    )
    horizon = args.horizon_minutes // MINUTES[args.confirm]
    span_years = (fast[-1].ts - fast[0].ts) / (1000 * 60 * 60 * 24 * 365.25)
    mid = len(fast) // 2
    sigs = pool_for(
        fast,
        base,
        shifts,
        a_fast,
        args,
        args.extreme_minutes,
        args.swept_minutes,
        args.stop_buffer_atr,
    )
    keep = [
        s.r_available >= args.min_r
        and s.counter_trend
        and len(s.families) >= args.min_families
        and not (args.skip_friday and datetime.utcfromtimestamp(fast[s.i].ts / 1000).weekday() == 4)
        for s in sigs
    ]
    print(
        f"\n=== two-stage exits, {sum(keep)} qualifying setups"
        f"{', Friday refused' if args.skip_friday else ''} ==="
    )
    print("    the slot is applied, so a longer hold has to pay for the setups it blocks")

    def run(tp1, tp2, split, be):
        """One ladder, through a single position slot."""
        rs: List[float] = []
        wins = 0
        holds: List[int] = []
        first: List[float] = []
        free_at = -1
        for k, s in enumerate(sigs):
            if not keep[k] or s.i < free_at:
                continue
            won, r, ex = walk_ladder(
                fast,
                s.i,
                s.direction,
                s.entry,
                s.stop,
                s.target,
                horizon,
                s.r_available,
                s.risk,
                args.spread,
                tp1,
                tp2,
                split,
                be,
            )
            free_at = ex
            rs.append(r)
            holds.append(ex - s.i)
            wins += 1 if won else 0
            if s.i < mid:
                first.append(r)
        return rs, wins, holds, first

    rows_out = []
    for tp1, tp2, split, be in itertools.product(AX_TP1, AX_TP2, AX_SPLIT, (False, True)):
        if tp2 <= tp1:
            continue
        rs, wins, holds, first = run(tp1, tp2, split, be)
        if not rs:
            continue
        tot, dd = sum(rs), drawdown(rs)
        fh = sum(first)
        rows_out.append(
            (
                2.0 * min(fh, tot - fh),
                f"{split:.0%} off at {tp1:.0%}, rest at {tp2:.0%}"
                f"{', then breakeven' if be else ''}",
                len(rs),
                wins,
                tot,
                dd,
                fh,
                tot - fh,
                statistics.median(holds) * MINUTES[args.confirm],
            )
        )

    # the shipped single exit, scored by the SAME code path (split = everything, so the second
    # leg never exists). A control that runs through different code is not a control.
    rs, wins, holds, first = run(args.tp, args.tp + 1e-9, 1.0, False)
    ship = (
        2.0 * min(sum(first), sum(rs) - sum(first)),
        f"ALL of it at {args.tp:.0%} (what ships)",
        len(rs),
        wins,
        sum(rs),
        drawdown(rs),
        sum(first),
        sum(rs) - sum(first),
        statistics.median(holds) * MINUTES[args.confirm],
    )

    hdr = (
        f"  {'exit rule':44s} {'n':>4s} {'hit':>6s} {'total':>8s} {'DD':>6s} "
        f"{'R/DD':>6s} {'halves':>15s} {'hold':>6s}"
    )
    print("\n-- best twelve by the worse calendar half --")
    print(hdr)
    for w, name, n, wins_, tot, dd, a, b, hold in sorted(rows_out, reverse=True)[:12]:
        print(
            f"  {name:44s} {n:4d} {wins_ / n:6.1%} {tot:+7.1f}R {dd:5.1f}R "
            f"{tot / dd if dd else 0:6.2f} {a:+7.1f}/{b:+6.1f} {hold:5.0f}m"
        )
    print("\n-- what ships today, through the same code --")
    w, name, n, wins_, tot, dd, a, b, hold = ship
    print(hdr)
    print(
        f"  {name:44s} {n:4d} {wins_ / n:6.1%} {tot:+7.1f}R {dd:5.1f}R "
        f"{tot / dd if dd else 0:6.2f} {a:+7.1f}/{b:+6.1f} {hold:5.0f}m"
    )
    best = max(rows_out)
    print(
        f"\n  best ladder beats the single exit by {best[4] - ship[4]:+.1f}R "
        f"and its worse half by {best[0] - ship[0]:+.1f}R"
    )


# ----------------------------------------------------------------------------- the real bill

# Read off `backtest/fills.py`, which is where these are MEASURED and which refuses rather than
# borrowing a sibling tier's number. They are copied here rather than imported because that module
# needs the whole replay stack and this tool is stdlib-only by design; the values are quoted with
# their source so a drift is findable. ⚠ RE-READ THEM before quoting this table again: the swap on
# this symbol moved 1.7% in three weeks with nothing to announce it.
TIERS = {
    # name: (spread, commission per side per lot, swap long $/lot/night, swap short, label)
    "Vantage demo (what every number so far used)": (0.22, 0.00, -74.84, 26.98),
    "PU Prime ECN (the live account)": (0.12, 1.00, -79.60, 30.25),
}
CONTRACT = 100.0  # ounces per lot, both tiers
ROLLOVER_UTC = 21  # the hour financing is booked; an approximation of the broker's 17:00 New York
TRIPLE_WEEKDAY = 2  # Wednesday carries the weekend, Monday-based


def nights_held(fast: Sequence[Row], i: int, exit_i: int) -> int:
    """How many financing rollovers the trade was open across, weekend triple included."""
    a = datetime.utcfromtimestamp(fast[i].ts / 1000)
    b = datetime.utcfromtimestamp(fast[min(exit_i, len(fast) - 1)].ts / 1000)
    n = 0
    cur = a.replace(hour=ROLLOVER_UTC, minute=0, second=0, microsecond=0)
    if cur <= a:
        cur += timedelta(days=1)
    while cur <= b:
        n += 3 if cur.weekday() == TRIPLE_WEEKDAY else 1
        cur += timedelta(days=1)
    return n


def stage_costs(args) -> None:
    """What this strategy costs on the account it will actually trade.

    🔴 EVERY NUMBER IN THIS STRATEGY'S DOCS CHARGES HALF THE SPREAD AT ENTRY AND NOTHING ELSE.
    No commission, no financing, and nothing on the way out. That is the parent study's model
    and it was honest for a study; quoted at a strategy about to trade money it is optimistic,
    and by how much has never been measured. This measures it.

    ⚠ THE SPREAD IS CHARGED TWICE FOR A LOSER AND ONCE FOR A WINNER, on purpose. The entry is a
    market fill and pays the offer. The target is a resting limit and fills at its own price. The
    stop is a market order and pays the spread again on the way out. Charging it symmetrically
    would overstate every winner.

    ⚠ COSTS ARE IN R AND THAT MAKES THEM SIZE-INDEPENDENT. One lot risks the stop distance times
    the contract size, so a commission of C per side is 2C / (stop x 100) of one R however big
    the account is. It also means a TIGHT stop is expensive: the same commission is a far larger
    fraction of a small risk. `CLAUDE.md` rule 6 - compare R, never dollars.
    """
    base_rows, fast, base, shifts, a_fast = prepare(
        args.broker, args.symbol, args.base, args.confirm
    )
    horizon = args.horizon_minutes // MINUTES[args.confirm]
    print(f"\n=== what the strategy costs, per account tier ({args.base}/{args.confirm}) ===")
    for name, (spread, comm, sw_long, sw_short) in TIERS.items():
        a2 = Namespace(**{**vars(args), "spread": spread})
        # the tier's spread goes into the COLLECTION, not on top of the result: it moves the
        # entry price, which moves how far the target is in stops, which moves what qualifies.
        sigs = pool_for(
            fast,
            base,
            shifts,
            a_fast,
            a2,
            args.extreme_minutes,
            args.swept_minutes,
            args.stop_buffer_atr,
        )
        walked = rewalk(sigs, fast, horizon, args.tp, None)
        keep = [
            s.r_available >= args.min_r
            and s.counter_trend
            and len(s.families) >= args.min_families
            and not (
                args.skip_friday and datetime.utcfromtimestamp(fast[s.i].ts / 1000).weekday() == 4
            )
            for s in sigs
        ]
        gross = exit_sp = commission = swap = 0.0
        n = wins = 0
        free_at = -1
        net_rs: List[float] = []
        for k, s in enumerate(sigs):
            if not keep[k] or s.i < free_at:
                continue
            outcome, ex = walked[k]
            if outcome == "skip":
                continue
            free_at = ex
            n += 1
            lot_risk = s.risk * CONTRACT  # dollars of risk in one lot, i.e. what 1R buys
            if outcome == "win":
                wins += 1
                gross += s.r_available * args.tp
            else:
                gross -= 1.0
                # a stop is a market order and pays the spread again on the way out
                exit_sp += (spread / 2.0) / s.risk
            c_trade = 2.0 * comm / lot_risk
            rate = sw_long if s.direction > 0 else sw_short
            s_trade = -nights_held(fast, s.i, ex) * rate / lot_risk
            commission += c_trade
            swap += s_trade
            # the same trade's R after every charge, kept IN ORDER — a drawdown is a property of
            # the sequence, so it cannot be recovered from the totals above
            exit_trade = 0.0 if outcome == "win" else (spread / 2.0) / s.risk
            won_r = s.r_available * args.tp if outcome == "win" else -1.0
            net_rs.append(won_r - exit_trade - c_trade - s_trade)
        net = gross - exit_sp - commission - swap
        print(f"\n  {name}")
        print(
            f"    spread ${spread:.2f}, commission ${comm:.2f}/side/lot, "
            f"swap {sw_long:+.2f}/{sw_short:+.2f} per lot per night"
        )
        print(f"    {n} trades, {wins} winners ({wins / n:.1%})")
        print(f"    gross, entry spread already inside it   {gross:+8.2f}R")
        print(f"    less the spread paid getting stopped    {-exit_sp:+8.2f}R")
        print(f"    less commission                         {-commission:+8.2f}R")
        print(f"    less overnight financing                {-swap:+8.2f}R")
        print(
            f"    NET                                     {net:+8.2f}R   ({net / n:+.3f}R a trade)"
        )
        print(f"    worst peak-to-trough after costs        {drawdown(net_rs):8.2f}R")
        print("    compounding, after every charge above:")
        for pct in (2.5, 5.0, 10.0):
            mult, dd = compounded(net_rs, pct)
            deep = compounded([r * 2 if r < 0 else r for r in net_rs], pct)[1]
            print(
                f"      {pct:4.1f}% a trade -> {mult:8.1f}x, worst drop {dd:5.1f}%, "
                f"{deep:5.1f}% if the worst run is twice as deep"
            )


# ----------------------------------------------------------------------------- entry


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--broker", default="VantageMarkets_Demo")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--base", default="M15", choices=sorted(MINUTES))
    ap.add_argument("--confirm", default="M5", choices=sorted(MINUTES))
    ap.add_argument("--spread", type=float, default=0.22)
    ap.add_argument("--horizon-minutes", type=int, default=6000)
    ap.add_argument(
        "--stage",
        default="grid",
        choices=("timeframe", "grid", "families", "risk", "extras", "losers", "ladder", "costs"),
    )
    ap.add_argument(
        "--pairs",
        default="M5/M1,M5/M5,M15/M1,M15/M5,M15/M15,M30/M5,M30/M15,M30/M30,H1/M5,H1/M15,H1/M30,H4/M15,H4/H1",
        help="base/confirm pairs for the timeframe stage",
    )
    ap.add_argument(
        "--n-floor",
        type=int,
        default=60,
        help="refuse to rank a configuration with fewer trades than this over the whole history",
    )
    ap.add_argument("--out", default="")
    ap.add_argument(
        "--fine",
        action="store_true",
        help="second pass: step through the coarse winner's square, with the axes the coarse "
        "pass settled pinned rather than re-searched",
    )
    ap.add_argument(
        "--quick",
        action="store_true",
        help="a small grid for a frame the full product cannot afford — see stage_grid",
    )
    # held constant by the families / risk stages
    ap.add_argument("--extreme-minutes", type=int, default=SHIPPED["extreme_minutes"])
    ap.add_argument("--swept-minutes", type=int, default=SHIPPED["swept_minutes"])
    ap.add_argument("--stop-buffer-atr", type=float, default=SHIPPED["stop_buffer_atr"])
    ap.add_argument("--min-r", type=float, default=SHIPPED["min_r"])
    ap.add_argument("--min-families", type=int, default=SHIPPED["min_families"])
    ap.add_argument("--min-stop", type=float, default=SHIPPED["min_stop"])
    ap.add_argument("--tp", type=float, default=SHIPPED["tp"])
    ap.add_argument("--arm", type=float, default=-1.0, help="negative = never move to breakeven")
    ap.add_argument(
        "--skip-friday",
        action="store_true",
        help="refuse a Friday entry, which the strategy has done by default since 2026-09-01",
    )
    args = ap.parse_args()

    if args.stage == "timeframe":
        stage_timeframe(args)
    elif args.stage == "grid":
        stage_grid(args)
    elif args.stage == "families":
        stage_families(args)
    elif args.stage == "extras":
        stage_extras(args)
    elif args.stage == "losers":
        stage_losers(args)
    elif args.stage == "ladder":
        stage_ladder(args)
    elif args.stage == "costs":
        stage_costs(args)
    else:
        stage_risk(args)


if __name__ == "__main__":
    main()
