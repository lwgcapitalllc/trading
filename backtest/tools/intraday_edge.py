#!/usr/bin/env python3
"""intraday_edge.py — which INTRADAY trigger carries edge, before any strategy is built?

The sibling of `trigger_edge.py`, aimed at a different question. That tool screened the two
CONTINUATION triggers (`mpc_bos`, `mpc_d`) that hold for days. This one screens triggers that
fire and RESOLVE inside a session, because the thing being looked for is a strategy that
stacks with `mpc_sos_fade` rather than queueing behind it.

Same three disciplines as `trigger_edge.py`, and they are the whole tool:

  1. 🔴 EVERY SET IS SCORED AGAINST A CONTROL MATCHED ON DIRECTION AND STOP DISTANCE. Gold went
     1,200 -> 4,300 across this window, so a long-side "edge" is free and any harness without a
     control will find one. The control lands on the theoretical breakeven, which is what says
     the harness is unbiased before any result is read off it.
  2. ⚠ THE HORIZON IS A HARD INTRADAY CAP. A trigger that only pays if you hold it four days is
     not an intraday trigger, and without the cap the sweep-fades below quietly become swing
     trades and score as such. Unresolved at the cap counts as 0R — conservative, and applied
     to the control identically.
  3. ⚠ NOTHING IS EVALUATED ON THE BAR IT ACTS ON. Every trigger fires on a CLOSED bar and
     enters at that bar's close. This is the look-ahead trap `trigger_edge.py` already fell into
     once (a filter read off the fill bar's close reported +15.9% where the honest read was
     +6.8%); the symptom was being too good, not erroring.

⚠ IT MEASURES SKELETONS, NOT STRATEGIES. No TP ladder, no staged stop, no runner, no costs, no
min-stop guard, one position per trigger set and no shared slot. Read a result as a PRIOR for a
trigger — "is there anything here" — never as a strategy's own number. The h4_sweep study is the
cautionary tale in the other direction: a real edge at +0.073R gross that did not clear cost until
the geometry was rebuilt around it.

⚠ COST IS NOT MODELLED AND IT IS THE AXIS THAT KILLS INTRADAY IDEAS. The `risk=` column is the
median stop in ATR and the `$stop` column is the median stop in dollars — read them BEFORE the
edge column. Gold's round-trip is ~$0.30; a trigger with a $2 stop is spending 15% of 1R on cost
and needs a far larger edge than one with a $12 stop to survive the translation.

⚠ Stdlib only, on purpose — no pandas, so it runs on a bare interpreter with no MT5 and no VPS.

    usage:  python3 backtest/tools/intraday_edge.py
            python3 backtest/tools/intraday_edge.py --horizon 32 --target 2.0
"""
from __future__ import annotations

import argparse
import collections
import random
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engines"))
sys.path.insert(0, str(ROOT))

from market_structure import Bar, StructureEngine  # noqa: E402
from vwap import VwapEngine  # noqa: E402
from sessions import SessionEngine  # noqa: E402
from liquidity import LiquidityEngine  # noqa: E402
from equal_highs_lows import EqualHighsLowsEngine  # noqa: E402

# ONE loader, shared with trigger_edge.py — a cache result and a published screen number
# cannot drift apart if there is only one thing reading the file.
from backtest.tools.trigger_edge import Row, atr, drop_coarse  # noqa: E402

import csv as _csv  # noqa: E402


# 🔴 THE COST IS PER SYMBOL AND IT IS THE AXIS THAT DECIDES INTRADAY, so it is a measured
# table rather than one constant. Values are the broker's own live `spread_price` off
# `GET /symbol_info` (Vantage demo), charged ONCE per round trip.
#   XAUUSD  $0.22 measured over 1,494,459 ticks -> $0.30 with slippage headroom.
#           On a $4,155 price that is 0.0053% — and an intraday gold stop is $1-7,
#           so cost is 4-37% of every R.
#   NAS100  $0.80 live spread on a 29,687 price = 0.0027%, HALF gold's in relative terms,
#           while an intraday index stop is 50-150 points. Cost per R is an order of
#           magnitude smaller. This is the whole reason a second instrument is tested.
COSTS = {"XAUUSD": 0.30, "NAS100": 1.00}
COST_USD = 0.30

# How long a swept level stays "pending" waiting for its close-back-inside confirmation.
# 8 M15 bars = 2 hours. Beyond that the grab is not a grab, it is a trend.
CONFIRM_BARS = 8


@dataclass
class Event:
    kind: str
    entry_i: int
    direction: int          # +1 long, -1 short
    entry: float
    stop: float
    risk_atr: float
    risk_usd: float
    outcome: str = ""
    year: int = 0
    tag: str = ""           # free-form split label (side, session, ...)
    # Confluence flags, frozen from CLOSED-bar state at the moment the trigger fired.
    # Every one is a fact known before the entry bar's close — see the look-ahead note.
    f_vwap: bool = False    # entering on the trend's own side of the session VWAP
    f_trend: bool = False   # entering with the structure trend (last SOS)
    f_dbias: bool = False   # entering with yesterday's direction (prev day close vs open)
    f_kz: bool = False      # inside a NY kill zone
    f_narrow: bool = False  # the opening range was NARROW vs ATR (a coiled spring)


def load(symbol="XAUUSD"):
    """Same shape as trigger_edge.load(), but for any cached symbol. The COARSE-HEAD drop is
    still trigger_edge's — MT5 serves hourly bars where it has no M15 history, and measuring
    the raw file scores eight years of a trigger against a different bar size."""
    path = ROOT / "backtest" / "cache" / f"{symbol}__M15.csv"
    rows = []
    with path.open() as f:
        for rec in _csv.DictReader(f):
            t = datetime.strptime(rec["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append(Row(0, int(t.timestamp() * 1000), float(rec["open"]), float(rec["high"]),
                            float(rec["low"]), float(rec["close"]), float(rec["volume"] or 0)))
    return rows


# ----------------------------------------------------------------------------- scoring
def resolve(rows, entry_i, direction, entry, stop, target_r, horizon):
    """+target_r R before -1R, within `horizon` bars. A bar holding BOTH resolves as the
    LOSS — a 15-minute bar cannot say which came first, and the pessimistic read is the
    only one that cannot flatter the result."""
    risk = abs(entry - stop)
    if risk <= 0:
        return "bad"
    target = entry + direction * target_r * risk
    for k in range(entry_i + 1, min(entry_i + 1 + horizon, len(rows))):
        r = rows[k]
        if (r.l <= stop) if direction == 1 else (r.h >= stop):
            return "loss"
        if (r.h >= target) if direction == 1 else (r.l <= target):
            return "win"
    return "open"


_CTRL = {}


def control(rows, direction, risk_atr, target_r, horizon, n=8000, seed=7):
    """Random entries in ONE direction at a fixed stop distance in ATR. This is the number an
    event set has to beat. Without splitting by direction, gold's drift hides inside it."""
    key = (direction, round(risk_atr, 2), target_r, horizon, n, seed)
    if key in _CTRL:
        return _CTRL[key]
    rnd, a, out = random.Random(seed), atr(rows), []
    for _ in range(n):
        i = rnd.randrange(200, len(rows) - horizon - 2)
        entry = rows[i].c
        stop = entry - direction * risk_atr * a[i]
        out.append(Event("CTRL", i, direction, entry, stop, risk_atr, abs(entry - stop),
                         outcome=resolve(rows, i, direction, entry, stop, target_r, horizon)))
    _CTRL[key] = out
    return out


def stats(evs, rows, target_r, horizon):
    n = len(evs)
    if not n:
        return None
    w = sum(1 for e in evs if e.outcome == "win")
    l = sum(1 for e in evs if e.outcome == "loss")
    dec = w + l
    wr = w / dec if dec else 0.0
    exp = (w * target_r - l) / n
    se = (wr * (1 - wr) / dec) ** 0.5 if dec > 1 else 0.0
    med = statistics.median(e.risk_atr for e in evs)
    medusd = statistics.median(e.risk_usd for e in evs)
    longs = sum(1 for e in evs if e.direction == 1) / n
    cl = control(rows, 1, med, target_r, horizon)
    cs = control(rows, -1, med, target_r, horizon)

    def _wr(c):
        d = sum(1 for e in c if e.outcome in ("win", "loss"))
        return sum(1 for e in c if e.outcome == "win") / max(1, d)

    cwr = longs * _wr(cl) + (1 - longs) * _wr(cs)
    z = (wr - cwr) / se if se else 0.0
    # 🔴 THE DECIDING COLUMN. A gross edge is not a strategy — the h4 sweep study found a real
    # +0.073R fade that never cleared cost, and every trigger here has a stop of a few dollars
    # of gold against a ~$0.30 round trip. Cost in R = cost_usd / stop_usd, charged per trade.
    exp_net = exp - (COST_USD / medusd if medusd > 0 else 0.0)
    return dict(n=n, wr=wr, exp=exp, exp_net=exp_net, med=med, medusd=medusd, cwr=cwr,
                edge=wr - cwr, z=z, dec=dec, openpct=1 - dec / n,
                costr=(COST_USD / medusd if medusd > 0 else 0.0))


def line(label, evs, rows, target_r, horizon):
    s = stats(evs, rows, target_r, horizon)
    if s is None:
        print(f"{label:<38} n=0")
        return
    print(f"{label:<38} n={s['n']:>4}  WR={s['wr']:>5.1%}  expR={s['exp']:>+6.3f}  "
          f"NET={s['exp_net']:>+6.3f}  ${s['medusd']:>6.2f}(cost {s['costr']:>4.1%}R)  "
          f"ctrl={s['cwr']:>5.1%}  edge={s['edge']:>+6.1%} ({s['z']:>+4.1f}s)")


# ----------------------------------------------------------------------------- triggers
@dataclass
class Pending:
    """A level that has been swept and is waiting for its close-back-inside confirmation."""
    kind: str
    side: str               # "high" (swept above -> fade short) | "low"
    price: float
    start_i: int
    extreme: float
    tag: str = ""


def collect(rows, horizon):
    """One pass, every engine, every candidate trigger."""
    a = atr(rows)
    # ⚠ TWO SessionEngine INSTANCES ON PURPOSE, AND THE FIRST ATTEMPT SHARED ONE AND WAS WRONG.
    # LiquidityEngine COMPOSES a sessions engine and calls its update() internally. Passing it
    # mine and then calling update() again fed every bar to the same state machine TWICE, which
    # is idempotent for the pure clock flags (in_asia/in_london/in_ny) and silently destroys
    # every field that compares against the PREVIOUS bar: `is_new_day` (prev_ny_dow already
    # advanced -> always False) and the NY opening range (prev_in_nyr_window already True -> the
    # range never opens). The symptom was ORB firing 2 times in 8 years instead of ~2,000.
    # The engine is a pure function of the bar stream, so two instances each fed once are
    # identical to one instance fed once — and cannot desync.
    liq = LiquidityEngine()
    sess_engine = SessionEngine()
    vw = VwapEngine()
    eq = EqualHighsLowsEngine()
    st = StructureEngine()

    evs: list[Event] = []
    pend: list[Pending] = []
    eq_pend: list[Pending] = []

    trend = 0
    prev_vwap = None
    prev_close = None
    # VWAP extension state: how far the current excursion has run, and its extreme.
    ext_dir, ext_peak = 0, None
    # NY opening range: one shot per day per side.
    orb_day, orb_done = None, set()
    day_open, prev_day_dir = None, 0

    for r in rows:
        ext = st.update(Bar(r.i, r.o, r.h, r.l, r.c)).external
        # LiquidityEngine drives the shared SessionEngine internally; read sessions off it so
        # the clock cannot disagree between the two consumers.
        lev = liq.update(r.i, r.ts, r.h, r.l, r.c)
        se = sess_engine.update(r.i, r.ts, r.h, r.l)
        vwap = vw.update(r.i, r.ts, r.h, r.l, r.c, r.v).value
        eqe = eq.update(r.i, r.h, r.l, r.c)

        if ext.bull_sos:
            trend = 1
        elif ext.bear_sos:
            trend = -1

        year = datetime.fromtimestamp(r.ts / 1000, timezone.utc).year

        # ---------------------------------------------------------------- 1. SWEEP FADES
        # A live liquidity level is taken (wick through), then a later bar CLOSES back
        # inside. That close is the entry; the stop is the sweep's own extreme. This is
        # the shape h4_sweep_profile.py found carries the edge on gold (the FADE, not the
        # continuation), asked here at intraday levels and an intraday horizon.
        for lv in lev.mitigated:
            tag = None
            if lv.kind == "session" and lv.session_name == "Asia" and (se.in_london or se.in_ny):
                tag = "ASIA"          # the judas swing — Asia's range grabbed in London/NY
            elif lv.kind == "session" and lv.session_name == "London" and se.in_ny:
                tag = "LDN"
            elif lv.kind == "daily":
                tag = "PD"            # PDH / PDL
            if tag is None:
                continue
            pend.append(Pending(tag, lv.side, lv.price, r.i,
                                r.h if lv.side == "high" else r.l))

        for lv in eqe.mitigated:
            eq_pend.append(Pending("EQ", "high" if lv.is_high else "low", lv.price, r.i,
                                   r.h if lv.is_high else r.l))

        for bag in (pend, eq_pend):
            for p in list(bag):
                if p.side == "high":
                    p.extreme = max(p.extreme, r.h)
                    confirmed = r.c < p.price
                    direction = -1
                else:
                    p.extreme = min(p.extreme, r.l)
                    confirmed = r.c > p.price
                    direction = 1
                if r.i - p.start_i > CONFIRM_BARS:
                    bag.remove(p)
                    continue
                if r.i == p.start_i:
                    continue          # the sweep bar itself cannot confirm its own sweep
                if confirmed:
                    stop = p.extreme
                    risk = abs(r.c - stop)
                    if risk > 1e-9:
                        evs.append(Event(f"{p.kind}_FADE", r.i, direction, r.c, stop,
                                         risk / a[r.i], risk, year=year,
                                         tag="long" if direction == 1 else "short"))
                    bag.remove(p)

        # ---------------------------------------------------------------- 2. VWAP
        if vwap is not None and prev_vwap is not None and prev_close is not None:
            dist = (r.c - vwap) / a[r.i]

            # 2a. STRETCH FADE — price ran >=2 ATR from the session VWAP, then printed a bar
            # closing BACK toward it. Pure mean reversion, the classic intraday idea.
            if abs(dist) >= 2.0:
                d = 1 if dist > 0 else -1
                if ext_dir != d:
                    ext_dir, ext_peak = d, (r.h if d == 1 else r.l)
                else:
                    ext_peak = max(ext_peak, r.h) if d == 1 else min(ext_peak, r.l)
                # turning back: this close is nearer VWAP than the last one was
                if abs(r.c - vwap) < abs(prev_close - prev_vwap):
                    stop = ext_peak
                    risk = abs(r.c - stop)
                    if risk > 1e-9:
                        evs.append(Event("VWAP_STRETCH_FADE", r.i, -d, r.c, stop,
                                         risk / a[r.i], risk, year=year,
                                         tag="long" if -d == 1 else "short"))
                        ext_dir, ext_peak = 0, None
            elif abs(dist) < 1.0:
                ext_dir, ext_peak = 0, None

            # 2b. TREND BOUNCE — with the structure trend, price pulls back and TAGS the
            # session VWAP, then closes back on the trend's side. The "easy confluence"
            # everyone trades. Stop below the tagging bar.
            if trend != 0:
                tagged = (r.l <= vwap <= r.h)
                on_side = (r.c > vwap) if trend == 1 else (r.c < vwap)
                was_side = (prev_close > prev_vwap) if trend == 1 else (prev_close < prev_vwap)
                if tagged and on_side and was_side:
                    stop = r.l if trend == 1 else r.h
                    risk = abs(r.c - stop)
                    if risk > 1e-9:
                        evs.append(Event("VWAP_TREND_BOUNCE", r.i, trend, r.c, stop,
                                         risk / a[r.i], risk, year=year,
                                         tag="long" if trend == 1 else "short"))

        # ---------------------------------------------------------------- 3. NY OPEN RANGE
        # One shot per side per day: the first M15 bar to CLOSE outside the 09:30-09:35 NY
        # opening range. Breakout and its fade are both emitted — they are the same event
        # read two ways, so whichever wins, the other is its mirror.
        if se.is_new_day:
            # Freeze YESTERDAY's direction before the new day overwrites it. Read as a closed
            # fact about a finished day, so it cannot see into the bar it filters.
            if day_open is not None and prev_close is not None:
                prev_day_dir = 1 if prev_close > day_open else -1
            day_open = r.o
            orb_day, orb_done = year, set()
        if (se.ny_range_high is not None and se.ny_range_low is not None
                and se.in_ny_range_extend and se.ny_range_high > se.ny_range_low):
            rh, rl = se.ny_range_high, se.ny_range_low
            narrow = (rh - rl) < 0.8 * a[r.i]

            def _orb(d, stop_px, fade_stop):
                risk = abs(r.c - stop_px)
                if risk <= 1e-9:
                    return
                on_vwap = vwap is not None and ((r.c > vwap) if d == 1 else (r.c < vwap))
                evs.append(Event("ORB_BREAK", r.i, d, r.c, stop_px, risk / a[r.i], risk,
                                 year=year, tag="long" if d == 1 else "short",
                                 f_vwap=on_vwap, f_trend=(trend == d),
                                 f_dbias=(prev_day_dir == d), f_kz=se.in_killzone,
                                 f_narrow=narrow))
                if abs(r.c - fade_stop) > 1e-9:
                    evs.append(Event("ORB_FADE", r.i, -d, r.c, fade_stop,
                                     abs(r.c - fade_stop) / a[r.i], abs(r.c - fade_stop),
                                     year=year, tag="short" if d == 1 else "long"))

            if r.c > rh and "up" not in orb_done:
                orb_done.add("up")
                _orb(1, rl, r.h)
            if r.c < rl and "dn" not in orb_done:
                orb_done.add("dn")
                _orb(-1, rh, r.l)

        prev_vwap, prev_close = vwap, r.c

    for e in evs:
        e.outcome = ""
    return evs


# ----------------------------------------------------------------------------- report
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="XAUUSD", help="XAUUSD | NAS100 (must be cached)")
    ap.add_argument("--horizon", type=int, default=32,
                    help="max bars held. 32 M15 bars = 8 hours (default, intraday)")
    ap.add_argument("--target", type=float, default=2.0, help="R target scored against -1R")
    args = ap.parse_args()

    global COST_USD
    COST_USD = COSTS.get(args.symbol, 0.30)
    rows = drop_coarse(load(args.symbol))
    print(f"{args.symbol}: {len(rows)} true-M15 bars, "
          f"{datetime.fromtimestamp(rows[0].ts/1000, timezone.utc):%Y-%m-%d} -> "
          f"{datetime.fromtimestamp(rows[-1].ts/1000, timezone.utc):%Y-%m-%d}")
    print(f"scored at +{args.target}R before -1R, horizon {args.horizon} bars "
          f"({args.horizon/4:.0f}h) | breakeven WR = {1/(1+args.target):.1%}\n")

    evs = collect(rows, args.horizon)
    for e in evs:
        e.outcome = resolve(rows, e.entry_i, e.direction, e.entry, e.stop, args.target, args.horizon)
    evs = [e for e in evs if e.outcome != "bad"]

    print("── HARNESS SELF-CHECK: the control must land on breakeven ──")
    for dr, nm in ((1, "long"), (-1, "short")):
        for ra in (0.5, 1.0, 2.0):
            line(f"  random {nm} @{ra}ATR", control(rows, dr, ra, args.target, args.horizon),
                 rows, args.target, args.horizon)

    kinds = sorted({e.kind for e in evs})
    print("\n── EVERY INTRADAY TRIGGER, vs a matched control ──")
    for k in kinds:
        line(k, [e for e in evs if e.kind == k], rows, args.target, args.horizon)

    print("\n── by SIDE (gold tripled: a long-only 'edge' is the drift talking) ──")
    for k in kinds:
        for side in ("long", "short"):
            line(f"  {k} {side}", [e for e in evs if e.kind == k and e.tag == side],
                 rows, args.target, args.horizon)

    print("\n── HALF SPLIT (a sign flip is regime, not edge) ──")
    mid = rows[len(rows) // 2].i
    for k in kinds:
        for nm, sel in (("1st", lambda e: e.entry_i < mid), ("2nd", lambda e: e.entry_i >= mid)):
            line(f"  {k} {nm}", [e for e in evs if e.kind == k and sel(e)],
                 rows, args.target, args.horizon)

    print("\n── ROBUSTNESS: vs R target, and vs horizon ──")
    print("   (an edge that exists only at one R target is an artefact of that target;")
    print("    an edge that only appears at a SWING horizon is not an intraday trigger)")
    for k in kinds:
        if len([e for e in evs if e.kind == k]) < 100:
            continue
        cells = []
        for tr in (1.0, 1.5, 2.0, 3.0):
            sub = [Event(e.kind, e.entry_i, e.direction, e.entry, e.stop, e.risk_atr,
                         e.risk_usd, resolve(rows, e.entry_i, e.direction, e.entry, e.stop,
                                             tr, args.horizon), e.year, e.tag)
                   for e in evs if e.kind == k]
            s = stats(sub, rows, tr, args.horizon)
            cells.append(f"{tr}R:{s['edge']:>+5.1%}({s['z']:>+4.1f}s)")
        for hz, nm in ((96, "24h"), (384, "4d")):
            sub = [Event(e.kind, e.entry_i, e.direction, e.entry, e.stop, e.risk_atr,
                         e.risk_usd, resolve(rows, e.entry_i, e.direction, e.entry, e.stop,
                                             args.target, hz), e.year, e.tag)
                   for e in evs if e.kind == k]
            s = stats(sub, rows, args.target, hz)
            cells.append(f"{nm}:{s['edge']:>+5.1%}({s['z']:>+4.1f}s)")
        print(f"  {k:<24} " + "  ".join(cells))

    print("\n── CONFLUENCE: does stacking an engine on ORB_BREAK lift it over cost? ──")
    print("   (NET is the only column that decides anything. A filter that raises the edge")
    print("    while shrinking n has to raise it enough to still be there at n/4.)")
    orb = [e for e in evs if e.kind == "ORB_BREAK"]
    filts = [("all", lambda e: True),
             ("+ pro-trend VWAP side", lambda e: e.f_vwap),
             ("+ with structure trend", lambda e: e.f_trend),
             ("+ with yesterday's direction", lambda e: e.f_dbias),
             ("+ inside a NY kill zone", lambda e: e.f_kz),
             ("+ narrow opening range", lambda e: e.f_narrow),
             ("+ VWAP and trend", lambda e: e.f_vwap and e.f_trend),
             ("+ VWAP and narrow", lambda e: e.f_vwap and e.f_narrow),
             ("+ VWAP and trend and narrow", lambda e: e.f_vwap and e.f_trend and e.f_narrow)]
    for nm, fn in filts:
        line(f"  ORB {nm}", [e for e in orb if fn(e)], rows, args.target, args.horizon)

    print("\n── PER YEAR, for anything worth a second look ──")
    for k in kinds:
        yrs = collections.defaultdict(list)
        for e in evs:
            if e.kind == k:
                yrs[e.year].append(e)
        row = []
        for y in sorted(yrs):
            s = stats(yrs[y], rows, args.target, args.horizon)
            row.append(f"{y}:{s['exp']:>+5.2f}({s['n']})")
        print(f"  {k:<24} " + "  ".join(row))


if __name__ == "__main__":
    main()
