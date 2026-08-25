#!/usr/bin/env python3
"""pre_sos_leg.py — the leg BEFORE the shift of structure. Is it tradeable?

Aaron's question (2026-08-24): the live A+ bot waits for the shift of structure and then fades
the retracement. The move it never takes is the one that CREATES the shift — from the extreme up
to the swing whose break IS the shift. Stop under the extreme, target the swing, get in and get
out. "How do we measure the extreme?"

WHAT THIS IS AND IS NOT. A study, in the shape of `trigger_edge.py` and `sweep_edge.py`: a
trigger population, a matched control, and one question. It is NOT a backtest and must never be
quoted as one — no position slot, no queueing, no re-entry cap, no news filter, no TP ladder, no
sizing. Outcomes are a bar-by-bar walk of "which came first, stop or target", and a bar holding
both books the STOP.

THE PROBLEM THE TOOL EXISTS TO SOLVE. The extreme is only knowable afterwards, so it cannot be
traded directly. Everything here is about finding a REAL-TIME proxy for it and then scoring that
proxy honestly. Three proxies were tried and only the third survived:

  1. sweep-and-reclaim of a liquidity level on the base frame, aimed at the swing
       -> dead flat against control (measured: 9,974 signals, edge -0.1%)
  2. the smaller-degree (internal) shift on the BASE frame
       -> too late. By the time it prints, the target sits CLOSER than the stop.
  3. the change of character on a FASTER frame, after a base-frame level was swept
       -> this is what the tool scores.

🔴 THE CONTROL IS THE WHOLE TOOL. Gold went 1,200 -> 4,600 across the cached window, so a
long-side "edge" is free. Every set is scored against random entries MATCHED ON DIRECTION,
HOUR OF DAY and STOP DISTANCE, resolved to the SAME R multiple by the same walk. The hour axis is
not optional: sweeps land at specific hours, gold does not drift uniformly around the clock, and
a control drawn from all hours hands the sweep rows an edge made entirely of what time it is.

⚠ THE 'open' OUTCOME IS COUNTED AS A FULL LOSS, on both sides. A trade that reaches neither end
inside the horizon is not a scratch here. That is pessimistic and it is applied to the control
too, so the EDGE is unaffected while the absolute expectancy is the low end.

⚠ ONE BROKER PER RUN. Spread differs per broker and per account tier, and the confirmation frame
has to come from the same feed as the base frame or the two disagree about what a bar is. The
tool refuses to mix them.

⚠ IT READS ONE PRIVATE FIELD OF THE STRUCTURE ENGINE (`_ext.ash` / `_ext.asl`) — the swing that
is live RIGHT NOW, which the public event stream does not expose (events fire on change, not on
state). The alternative was to rebuild that state here from the event stream, which is a second
implementation of the thing rule 21 exists to prevent. It is read-only and it is guarded: a
rename raises on the first bar instead of quietly scoring nothing.

Usage:
    python3 backtest/tools/pre_sos_leg.py                      # defaults: Vantage XAUUSD, 5m confirm
    python3 backtest/tools/pre_sos_leg.py --confirm M1         # does a faster frame get in cheaper?
    python3 backtest/tools/pre_sos_leg.py --min-r 3
    python3 backtest/tools/pre_sos_leg.py --broker PUPrime_Demo --symbol XAUUSD_p
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "backtest" / "cache"
for _p in ("engines", "engines/market_structure", "engines/liquidity", "engines/sessions"):
    sys.path.insert(0, str(REPO / _p))

from liquidity import LiquidityEngine  # noqa: E402
from market_structure import Bar, StructureEngine  # noqa: E402

# Bars must be stamped in true UTC. Version-1 bars carry broker-local timestamps, and this study
# buckets both the control and the report by hour of day — every hour would be off by the
# broker's offset and the answer would be plausible and wrong. Same floor as sweep_edge.py.
MIN_FEED_VERSION = 2

MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60}
FAMILIES = ("h4", "session", "daily", "weekly")


# ----------------------------------------------------------------------------- bars


@dataclass
class Row:
    i: int
    ts: int  # epoch ms
    tmin: int  # epoch MINUTES — the common clock across frames
    hour: int
    year: int
    o: float
    h: float
    l: float
    c: float


def load(broker: str, symbol: str, tf: str) -> List[Row]:
    path = CACHE / broker / f"{symbol}__{tf}.csv"
    if not path.exists():
        raise SystemExit(f"no cached bars at {path} — pull them with the MT5 agent first")
    meta = path.with_suffix(".meta.json")
    if meta.exists():
        version = json.loads(meta.read_text()).get("feed_version", 1)
        if version < MIN_FEED_VERSION:
            raise SystemExit(
                f"{path.name} is feed_version {version}; this study needs at least "
                f"{MIN_FEED_VERSION}, where bars are stamped in true UTC. Every hour bucket "
                "here — the report's and the control's — would be off by the broker's offset."
            )
    rows: List[Row] = []
    with path.open(newline="") as fh:
        for rec in csv.DictReader(fh):
            t = datetime.strptime(rec["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            ms = int(t.timestamp() * 1000)
            rows.append(
                Row(
                    0,
                    ms,
                    ms // 60000,
                    t.hour,
                    t.year,
                    float(rec["open"]),
                    float(rec["high"]),
                    float(rec["low"]),
                    float(rec["close"]),
                )
            )
    return rows


def drop_coarse(rows: List[Row], tf_minutes: int) -> List[Row]:
    """Cut the coarse prefix off the front of the cache.

    The broker's deep history is stored at a coarser timeframe than the label claims — the
    XAUUSD M15 file opens with hourly bars. Walk back from the end to the last point where the
    surrounding gaps are genuinely wider than the timeframe, and start there. Same routine as
    trigger_edge.py and sweep_edge.py; kept local so this tool imports nothing from a sibling.
    """
    start = 0
    for k in range(len(rows) - 1, 0, -1):
        if (rows[k].ts - rows[k - 1].ts) // 60000 > tf_minutes:
            window = rows[max(0, k - 200) : k]
            gaps = [(window[j].ts - window[j - 1].ts) // 60000 for j in range(1, len(window))]
            if gaps and statistics.median(gaps) > tf_minutes:
                start = k
                break
    out = rows[start:]
    for n, r in enumerate(out):
        r.i = n
    return out


def atr(rows: Sequence[Row], length: int = 50) -> List[float]:
    out: List[float] = []
    prev = rows[0].c
    a = rows[0].h - rows[0].l
    for r in rows:
        tr = max(r.h - r.l, abs(r.h - prev), abs(r.l - prev))
        a = tr if not out else (a * (length - 1) + tr) / length
        out.append(a)
        prev = r.c
    return out


# ----------------------------------------------------------------------------- the base frame


@dataclass
class Base:
    """Per-bar state of the frame that decides WHERE: the trend, the swing that is the target,
    and the times each level family was last swept on each side."""

    tmin: List[int]
    direction: List[int]
    swing_high: List[Optional[float]]
    swing_low: List[Optional[float]]
    swept: Dict[Tuple[str, str], List[int]]  # (family, side) -> sorted sweep times, minutes


def replay_base(rows: Sequence[Row]) -> Base:
    se = StructureEngine()
    le = LiquidityEngine()
    if not hasattr(se, "_ext") or not hasattr(se._ext, "ash"):
        raise SystemExit(
            "the structure engine no longer exposes `_ext.ash` — this study reads the LIVE active "
            "swing, which the public event stream does not carry. Re-point it at whatever replaced "
            "that field rather than rebuilding the state here."
        )
    b = Base([], [], [], [], {(f, s): [] for f in FAMILIES for s in ("high", "low")})
    for r in rows:
        se.update(Bar(index=r.i, open=r.o, high=r.h, low=r.l, close=r.c))
        ev = le.update(r.i, r.ts, r.h, r.l, r.c)
        st = se._ext
        b.tmin.append(r.tmin)
        b.direction.append(st.dir)
        b.swing_high.append(st.ash)
        b.swing_low.append(st.asl)
        for lv in ev.mitigated:
            key = (lv.kind, lv.side)
            if key in b.swept:
                # the sweep is only KNOWN once the bar that made it has closed
                b.swept[key].append(r.tmin + (rows[1].tmin - rows[0].tmin if len(rows) > 1 else 0))
    return b


def replay_confirm(rows: Sequence[Row], same_frame: bool) -> List[Tuple[int, int]]:
    """The frame that decides WHEN. Returns (bar index, direction) per change of character.

    On a FASTER frame that is the external CHoCH. When the confirmation frame IS the base frame
    the external CHoCH is degenerate — it fires on the bar the target is broken, so there is no
    trade left to take — and the smaller-degree (internal) shift is the honest same-frame
    equivalent. Reported so the "just use the 15m" answer has a number beside it.
    """
    se = StructureEngine()
    out: List[Tuple[int, int]] = []
    for r in rows:
        ev = se.update(Bar(index=r.i, open=r.o, high=r.h, low=r.l, close=r.c))
        x, iv = ev.external, ev.internal
        if same_frame:
            if iv.bull_sos:
                out.append((r.i, 1))
            if iv.bear_sos:
                out.append((r.i, -1))
        else:
            if x.bull_sos:
                out.append((r.i, 1))
            if x.bear_sos:
                out.append((r.i, -1))
    return out


# ----------------------------------------------------------------------------- scoring


@dataclass
class Signal:
    i: int
    direction: int
    year: int
    hour: int
    entry: float
    stop: float
    target: float
    risk: float
    risk_atr: float
    r_available: float
    outcome: str  # "win" | "loss" | "open"
    mfe: float  # best fraction of the way to the target, before it resolved
    families: Tuple[str, ...]
    counter_trend: bool


def walk(
    rows: Sequence[Row],
    i: int,
    direction: int,
    entry: float,
    stop: float,
    target: float,
    horizon: int,
) -> Tuple[str, float]:
    span = abs(target - entry)
    best = 0.0
    end = min(i + 1 + horizon, len(rows))
    for j in range(i + 1, end):
        r = rows[j]
        if direction > 0:
            v = (r.h - entry) / span
            if v > best:
                best = v
            if r.l <= stop:
                return "loss", best
            if r.h >= target:
                return "win", best
        else:
            v = (entry - r.l) / span
            if v > best:
                best = v
            if r.h >= stop:
                return "loss", best
            if r.l <= target:
                return "win", best
    return "open", best


def walk_breakeven(
    rows: Sequence[Row],
    i: int,
    direction: int,
    entry: float,
    stop: float,
    target: float,
    horizon: int,
    arm_at: float,
) -> str:
    """Same walk, except the stop moves to the entry price once price has travelled `arm_at` of
    the way to the target. Returns "win" | "scratch" | "loss" | "open".

    ⚠ THE ARM IS DECIDED ON A BAR CLOSE, not intrabar. A bar that reaches the arm level and then
    retraces to the entry within that same bar does NOT scratch — nothing in a bar tells you the
    order its extremes came in, and arming intrabar would let the model exit at a price it could
    not have known to place. The original stop still governs the bar that arms.

    ⚠ A bar holding both the breakeven stop and the target books the SCRATCH, matching the
    pessimistic convention `walk()` uses for stop-and-target.
    """
    span = abs(target - entry)
    arm_price = entry + direction * arm_at * span
    armed = False
    end = min(i + 1 + horizon, len(rows))
    for j in range(i + 1, end):
        r = rows[j]
        live_stop = entry if armed else stop
        if direction > 0:
            if r.l <= live_stop:
                return "scratch" if armed else "loss"
            if r.h >= target:
                return "win"
            if not armed and r.h >= arm_price:
                armed = True
        else:
            if r.h >= live_stop:
                return "scratch" if armed else "loss"
            if r.l <= target:
                return "win"
            if not armed and r.l <= arm_price:
                armed = True
    return "open"


def _last_at_or_before(times: List[int], t: int) -> Optional[int]:
    lo, hi = 0, len(times)
    while lo < hi:
        mid = (lo + hi) // 2
        if times[mid] <= t:
            lo = mid + 1
        else:
            hi = mid
    return times[lo - 1] if lo else None


def collect(
    fast: Sequence[Row],
    base: Base,
    shifts: Sequence[Tuple[int, int]],
    a_fast: Sequence[float],
    args,
) -> List[Signal]:
    lookback = max(1, args.extreme_minutes // MINUTES[args.confirm])
    horizon = args.horizon_minutes // MINUTES[args.confirm]
    half_spread = args.spread / 2.0
    out: List[Signal] = []
    bi = 0  # walking pointer into the base frame — both streams are time-ordered
    for i, direction in shifts:
        if i < lookback + 60 or i >= len(fast) - horizon - 2:
            continue
        t = fast[i].tmin
        # the last base bar that had CLOSED before this fast bar opened — no look-ahead
        while bi + 1 < len(base.tmin) and base.tmin[bi + 1] + MINUTES[args.base] <= t:
            bi += 1
        if bi < 60 or base.tmin[bi] + MINUTES[args.base] > t:
            continue
        target = base.swing_high[bi] if direction > 0 else base.swing_low[bi]
        if target is None:
            continue
        if direction > 0:
            extreme = min(r.l for r in fast[i - lookback : i + 1])
            entry = fast[i].c + half_spread
            stop = extreme - args.stop_buffer_atr * a_fast[i]
            if target <= entry or stop >= entry:
                continue
        else:
            extreme = max(r.h for r in fast[i - lookback : i + 1])
            entry = fast[i].c - half_spread
            stop = extreme + args.stop_buffer_atr * a_fast[i]
            if target >= entry or stop <= entry:
                continue
        risk = abs(entry - stop)
        if risk <= 0:
            continue
        side = "low" if direction > 0 else "high"
        fams = tuple(
            f
            for f in FAMILIES
            if (lambda s: s is not None and t - s <= args.swept_minutes)(
                _last_at_or_before(base.swept[(f, side)], t)
            )
        )
        outcome, mfe = walk(fast, i, direction, entry, stop, target, horizon)
        out.append(
            Signal(
                i=i,
                direction=direction,
                year=fast[i].year,
                hour=fast[i].hour,
                entry=entry,
                stop=stop,
                target=target,
                risk=risk,
                risk_atr=risk / a_fast[i],
                r_available=abs(target - entry) / risk,
                outcome=outcome,
                mfe=mfe,
                families=fams,
                counter_trend=(direction > 0 and base.direction[bi] < 0)
                or (direction < 0 and base.direction[bi] > 0),
            )
        )
    return out


class Control:
    """Random entries matched on direction, hour of day and stop distance, scored to the same R
    by the same walk. Without this the tool measures gold's trend, not the trigger."""

    def __init__(self, rows: Sequence[Row], a: Sequence[float], args, horizon: int):
        self.rows, self.a, self.args, self.horizon = rows, a, args, horizon
        self.by_hour: Dict[int, List[int]] = {h: [] for h in range(24)}
        lo, hi = 200, len(rows) - horizon - 2
        for r in rows[lo:hi]:
            self.by_hour[r.hour].append(r.i)
        self.rng = random.Random(args.seed)

    def score(self, sigs: Sequence[Signal], draws: int) -> Tuple[float, float]:
        wins = 0
        total = 0
        exp = 0.0
        half = self.args.spread / 2.0
        for s in sigs:
            pool = self.by_hour[s.hour]
            if not pool:
                continue
            for _ in range(draws):
                j = self.rng.choice(pool)
                risk = s.risk_atr * self.a[j]
                entry = self.rows[j].c + s.direction * half
                stop = entry - s.direction * risk
                target = entry + s.direction * risk * s.r_available
                outcome, _ = walk(self.rows, j, s.direction, entry, stop, target, self.horizon)
                total += 1
                if outcome == "win":
                    wins += 1
                    exp += s.r_available
                else:
                    exp -= 1.0
        if not total:
            return 0.0, 0.0
        return wins / total, exp / total


def expectancy(sigs: Sequence[Signal]) -> float:
    if not sigs:
        return 0.0
    return sum(s.r_available if s.outcome == "win" else -1.0 for s in sigs) / len(sigs)


def line(label: str, sigs: Sequence[Signal], ctl: Optional[Control], draws: int) -> None:
    if len(sigs) < 20:
        print(f"  {label:34s} n={len(sigs):4d}  (too few to read)")
        return
    hit = sum(1 for s in sigs if s.outcome == "win") / len(sigs)
    med_r = statistics.median(s.r_available for s in sigs)
    med_stop = statistics.median(s.risk for s in sigs)
    txt = (
        f"  {label:34s} n={len(sigs):4d} hit={hit:6.1%} medR={med_r:5.2f} "
        f"exp={expectancy(sigs):+.3f}R stop=${med_stop:5.2f}"
    )
    if ctl is not None:
        c_hit, c_exp = ctl.score(sigs, draws)
        se = math.sqrt(max(hit * (1 - hit), 1e-9) / len(sigs))
        txt += (
            f" | ctrl {c_hit:6.1%} {c_exp:+.3f}R  edge={hit - c_hit:+.1%} "
            f"({(hit - c_hit) / se:+.1f}s)"
        )
    print(txt)


# ----------------------------------------------------------------------------- report


def report(sigs: List[Signal], ctl: Control, args, fast_rows: Sequence[Row], horizon: int) -> None:
    qualifying = [s for s in sigs if s.r_available >= args.min_r and s.counter_trend and s.families]
    d = args.control_draws

    print(f"\n=== confirmation on {args.confirm}, target on {args.base} ===")
    print(f"raw changes of character on {args.confirm}: {len(sigs)}")
    line("all of them", sigs, ctl, d)
    line(
        f"R>={args.min_r} + counter-trend",
        [s for s in sigs if s.r_available >= args.min_r and s.counter_trend],
        ctl,
        d,
    )
    line("THE SETUP (+ a level was swept)", qualifying, ctl, d)
    line("+ two level families agreeing", [s for s in qualifying if len(s.families) >= 2], ctl, d)

    print("\n-- which level got swept (counter-trend, R filter applied) --")
    pool = [s for s in sigs if s.r_available >= args.min_r and s.counter_trend]
    line("no level swept at all", [s for s in pool if not s.families], ctl, d)
    for f in FAMILIES:
        line(f"{f} level swept", [s for s in pool if f in s.families], ctl, d)
    print("\n-- how many families agree --")
    for k in (0, 1, 2, 3):
        line(f"{k} families", [s for s in pool if len(s.families) == k], ctl, d)

    if len(qualifying) >= 20:
        print("\n-- the setup, per year (R, unfinished trades booked as full losses) --")
        years = sorted({s.year for s in qualifying})
        for y in years:
            g = [s for s in qualifying if s.year == y]
            tot = sum(s.r_available if s.outcome == "win" else -1.0 for s in g)
            print(f"     {y}  n={len(g):3d}  {tot:+7.1f}R")

        print("\n-- exit at a fraction of the way to the swing (same entry, same stop) --")
        print("     frac   reached   R booked   expectancy")
        for f in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
            reached = [s for s in qualifying if s.mfe >= f]
            p = len(reached) / len(qualifying)
            booked = statistics.median(f * s.r_available for s in qualifying)
            exp = sum(f * s.r_available if s.mfe >= f else -1.0 for s in qualifying) / len(
                qualifying
            )
            print(f"     {f:4.2f}   {p:6.1%}    {booked:6.2f}R    {exp:+.3f}R")

        print("\n-- once it is X% of the way, does it finish? --")
        for f in (0.3, 0.5, 0.7, 0.8, 0.9):
            sub = [s for s in qualifying if s.mfe >= f]
            if len(sub) < 10:
                continue
            done = sum(1 for s in sub if s.mfe >= 1.0) / len(sub)
            back = sum(1 for s in sub if s.outcome == "loss") / len(sub)
            print(
                f"     reached {f:3.0%}: n={len(sub):3d}  finishes {done:5.1%}  "
                f"falls back to the stop {back:5.1%}"
            )

    if len(qualifying) >= 20:
        print("\n-- what an EARLY move to breakeven actually costs --")
        print("     arm at    win    scratch   loss    expectancy   vs never")
        base_exp = None
        for arm in (None, 0.3, 0.4, 0.5, 0.7, 0.8, 0.9):
            wins = scratches = losses = 0
            total = 0.0
            for s_ in qualifying:
                # a scratch is not free: entry already carries half the spread, and exiting at the
                # entry price gives the other half back to the broker
                scratch_r = -(args.spread / 2.0) / s_.risk
                if arm is None:
                    outcome = s_.outcome
                else:
                    outcome = walk_breakeven(
                        fast_rows, s_.i, s_.direction, s_.entry, s_.stop, s_.target, horizon, arm
                    )
                if outcome == "win":
                    wins += 1
                    total += s_.r_available
                elif outcome == "scratch":
                    scratches += 1
                    total += scratch_r
                else:
                    losses += 1
                    total -= 1.0
            exp = total / len(qualifying)
            if base_exp is None:
                base_exp = exp
            label = "never" if arm is None else f"{arm:.0%}"
            delta = "" if arm is None else f"   {exp - base_exp:+.3f}R"
            print(
                f"     {label:6s}  {wins / len(qualifying):5.1%}   {scratches / len(qualifying):6.1%} "
                f" {losses / len(qualifying):5.1%}    {exp:+.3f}R{delta}"
            )

    if args.out:
        p = Path(args.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(
                [
                    "bar",
                    "dir",
                    "year",
                    "hour",
                    "stop",
                    "stop_atr",
                    "r_available",
                    "outcome",
                    "mfe",
                    "families",
                    "counter_trend",
                ]
            )
            for s in sigs:
                w.writerow(
                    [
                        s.i,
                        s.direction,
                        s.year,
                        s.hour,
                        round(s.risk, 2),
                        round(s.risk_atr, 3),
                        round(s.r_available, 3),
                        s.outcome,
                        round(s.mfe, 3),
                        "|".join(s.families),
                        int(s.counter_trend),
                    ]
                )
        print(f"\nwrote {len(sigs)} signals to {p}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--broker", default="VantageMarkets_Demo")
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument(
        "--base",
        default="M15",
        choices=sorted(MINUTES),
        help="the frame that decides WHERE — the levels and the target swing",
    )
    ap.add_argument(
        "--confirm",
        default="M5",
        choices=sorted(MINUTES),
        help="the frame that decides WHEN — the change of character",
    )
    ap.add_argument(
        "--spread",
        type=float,
        default=0.22,
        help="measured spread for the account being modelled (Vantage XAUUSD 0.22, "
        "PU Prime ECN 0.12). Half is charged at entry.",
    )
    ap.add_argument(
        "--min-r",
        type=float,
        default=2.0,
        help="refuse a setup whose target is nearer than this many stops",
    )
    ap.add_argument(
        "--extreme-minutes",
        type=int,
        default=120,
        help="how far back the extreme the stop sits under is looked for",
    )
    ap.add_argument(
        "--swept-minutes",
        type=int,
        default=180,
        help="how recently a level must have been swept to count",
    )
    ap.add_argument(
        "--horizon-minutes",
        type=int,
        default=6000,
        help="how long a trade may stay open before it is booked as a loss",
    )
    ap.add_argument("--stop-buffer-atr", type=float, default=0.05)
    ap.add_argument("--control-draws", type=int, default=3)
    ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if MINUTES[args.confirm] > MINUTES[args.base]:
        raise SystemExit("--confirm must be the same frame as --base or a faster one")

    base_rows = drop_coarse(load(args.broker, args.symbol, args.base), MINUTES[args.base])
    same = args.confirm == args.base
    fast_rows = (
        base_rows
        if same
        else drop_coarse(load(args.broker, args.symbol, args.confirm), MINUTES[args.confirm])
    )
    print(
        f"{args.base}: {len(base_rows)} bars  "
        f"{datetime.utcfromtimestamp(base_rows[0].ts / 1000):%Y-%m-%d} -> "
        f"{datetime.utcfromtimestamp(base_rows[-1].ts / 1000):%Y-%m-%d}"
    )
    print(f"{args.confirm}: {len(fast_rows)} bars")

    base = replay_base(base_rows)
    shifts = replay_confirm(fast_rows, same)
    a_fast = atr(fast_rows)
    sigs = collect(fast_rows, base, shifts, a_fast, args)
    ctl = Control(fast_rows, a_fast, args, args.horizon_minutes // MINUTES[args.confirm])
    report(sigs, ctl, args, fast_rows, args.horizon_minutes // MINUTES[args.confirm])


if __name__ == "__main__":
    main()
