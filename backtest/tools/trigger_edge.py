#!/usr/bin/env python3
"""trigger_edge.py — does a TRIGGER carry forward edge, before any strategy is built?

Not a backtest and deliberately not a strategy. It replays the canonical engines
(market_structure + vwap), finds the bar a trigger would actually be IN on, and asks one
question: from there, does price reach +NR before -1R? No sizing, no TP ladder, no costs.
R is each trigger's own structural stop, so triggers are compared on their own terms.

WHY IT EXISTS. `mpc_bos_strategy.pine` and `mpc_d_strategy.pine` are both continuation
setups and neither has a Python port, so neither can be swept by backtest/optimizer.py.
The question "which one is worth building on" does not need a port — it needs the trigger
population and an honest control.

🔴 THE CONTROL IS THE WHOLE TOOL. Gold went 1,200 -> 4,300 across the cached window, so a
long-side "edge" is free and any harness without a control will find one. Every set is
scored against random entries MATCHED ON DIRECTION AND STOP DISTANCE. The control lands on
the theoretical breakeven with expectancy ~0.000, which is what says the harness is unbiased
before any result is read off it. If you add a trigger here, add its control in the same
commit — a number without one is a description of gold, not of the trigger.

⚠ IT MEASURES SKELETONS, NOT THE SHIPPED STRATEGIES. No FVG requirement, no Sniper Zone, no
session filter, no min-stop guard, no real exit ladder. Read a result as a prior for a
trigger, never as a strategy's own number.

⚠ THE LOOK-AHEAD TRAP THIS TOOL ALREADY FELL INTO, recorded so it is not repeated: a filter
read off the CLOSE of the bar its limit fills on selects bars that recovered by their close.
That reported the VWAP filter at +15.9% / +5.0 sigma; reading the PREVIOUS closed bar gives
+6.8%. The symptom was being too good, not erroring. Anything evaluated on the bar it acts
on is look-ahead until proven otherwise — see `prev_side` below.

⚠ Stdlib only, on purpose — no pandas, so it runs on a bare interpreter.

Findings 2026-08-06, 186,384 true-M15 XAUUSD bars (2018-09-13 -> 2026-08-07), written up in
docs/MPC_BOS_SPEC.md §4b and indicators/CLAUDE.md:
    CONT (with-trend BOS -> 0.5 retrace)   n=778  +4.4% over control (+2.5 sigma)
    CONT + pro-trend VWAP side             n=404  +6.8% over control (+2.8 sigma), stop 38% tighter
    D    (counter-SOS -> VWAP reclaim)     n=833  -0.4% over control — indistinguishable from random

    usage:  python3 backtest/tools/trigger_edge.py
"""
from __future__ import annotations

import csv
import random
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engines"))

from market_structure import Bar, StructureEngine  # noqa: E402
from vwap import VwapEngine  # noqa: E402

CACHE = ROOT / "backtest" / "cache" / "XAUUSD__M15.csv"

D_CTR_BARS_MAX = 133
CONT_BARS_MAX = 133
CONT_ZONE_LO = 0.5
CONT_STOP_FIB = 0.886
RR_TARGET = 2.0
HORIZON = 400


@dataclass
class Row:
    i: int; ts: int; o: float; h: float; l: float; c: float; v: float


@dataclass
class Event:
    kind: str
    entry_i: int
    direction: int
    entry: float
    stop: float
    maturity: int
    risk_atr: float
    vwap_ok: bool = True
    ctr_bos: int = 0
    bars_wait: int = 0
    outcome: str = ""


def load() -> list[Row]:
    rows = []
    with CACHE.open() as f:
        for rec in csv.DictReader(f):
            t = datetime.strptime(rec["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append(Row(0, int(t.timestamp() * 1000), float(rec["open"]), float(rec["high"]),
                            float(rec["low"]), float(rec["close"]), float(rec["volume"] or 0)))
    return rows


def drop_coarse(rows):
    start = 0
    for k in range(len(rows) - 1, 0, -1):
        if (rows[k].ts - rows[k - 1].ts) // 60000 > 15:
            w = rows[max(0, k - 200):k]
            g = [(w[j].ts - w[j - 1].ts) // 60000 for j in range(1, len(w))]
            if g and statistics.median(g) > 15:
                start = k
                break
    out = rows[start:]
    for n, r in enumerate(out):
        r.i = n
    return out


def atr(rows, length=14):
    out, prev, a = [], rows[0].c, rows[0].h - rows[0].l
    for r in rows:
        tr = max(r.h - r.l, abs(r.h - prev), abs(r.l - prev))
        a = tr if not out else (a * (length - 1) + tr) / length
        out.append(a); prev = r.c
    return out


def resolve(rows, entry_i, direction, entry, stop):
    risk = abs(entry - stop)
    if risk <= 0:
        return "bad"
    target = entry + direction * RR_TARGET * risk
    for k in range(entry_i + 1, min(entry_i + 1 + HORIZON, len(rows))):
        r = rows[k]
        if (r.l <= stop) if direction == 1 else (r.h >= stop):
            return "loss"
        if (r.h >= target) if direction == 1 else (r.l <= target):
            return "win"
    return "open"


def collect(rows):
    st, vw, a = StructureEngine(), VwapEngine(), atr(rows)
    evs = []
    prev_side = 0        # sign of the PREVIOUS closed bar's close vs its VWAP
    trend = bos_count = 0
    cont_p = None
    d_p = None          # (dir, sos_bar, extreme, maturity, ctr_bos, lost_vwap, side_taken)

    for r in rows:
        e = st.update(Bar(r.i, r.o, r.h, r.l, r.c)).external
        vwap = vw.update(r.i, r.ts, r.h, r.l, r.c, r.v).value

        if d_p is not None:
            d, sos_b, ext, mat, cbos, lost, side_done = d_p
            ext = min(ext, r.l) if d == 1 else max(ext, r.h)
            # a BOS printed by the counter-move: the shakeout became a trend
            if (e.bear_bos and d == 1) or (e.bull_bos and d == -1):
                cbos += 1
            if r.i - sos_b > D_CTR_BARS_MAX:
                d_p = None
            else:
                if vwap is not None:
                    wrong = (r.c < vwap) if d == 1 else (r.c > vwap)
                    if wrong:
                        lost = True
                    else:
                        risk = abs(r.c - ext)
                        # variant A: no reclaim required — first pro-trend-side bar
                        if not side_done and risk > 1e-9:
                            evs.append(Event("D_side", r.i, d, r.c, ext, mat,
                                             risk / a[r.i], True, cbos, r.i - sos_b))
                            side_done = True
                        # variant B: the shipped reclaim — must have LOST the line first
                        if lost and risk > 1e-9:
                            evs.append(Event("D", r.i, d, r.c, ext, mat,
                                             risk / a[r.i], True, cbos, r.i - sos_b))
                            d_p = None
                if d_p is not None:
                    d_p = (d, sos_b, ext, mat, cbos, lost, side_done)

        if cont_p is not None:
            c, lo, hi, armed, mat = cont_p
            span = hi - lo
            if r.i - armed > CONT_BARS_MAX or span <= 0:
                cont_p = None
            else:
                zone = hi - CONT_ZONE_LO * span if c == 1 else lo + CONT_ZONE_LO * span
                stop = hi - CONT_STOP_FIB * span if c == 1 else lo + CONT_STOP_FIB * span
                if (r.c < stop) if c == 1 else (r.c > stop):
                    cont_p = None
                elif ((r.l <= zone) if c == 1 else (r.h >= zone)) and abs(zone - stop) > 1e-9:
                    ok = prev_side == c      # known BEFORE this bar opened — no look-ahead
                    evs.append(Event("CONT", r.i, c, zone, stop, mat, abs(zone - stop) / a[r.i],
                                     ok, 0, r.i - armed))
                    cont_p = None

        if e.bull_sos or e.bear_sos:
            new = 1 if e.bull_sos else -1
            if trend == -new and trend != 0:
                d_p = (trend, r.i, r.l if trend == 1 else r.h, bos_count, 0, False, False)
            trend, bos_count, cont_p = new, 0, None
        elif e.bull_bos and trend == 1:
            bos_count += 1
            if e.bull_bos_low is not None and e.bull_bos_high is not None:
                cont_p = (1, e.bull_bos_low, e.bull_bos_high, r.i, bos_count)
        elif e.bear_bos and trend == -1:
            bos_count += 1
            if e.bear_bos_low is not None and e.bear_bos_high is not None:
                cont_p = (-1, e.bear_bos_low, e.bear_bos_high, r.i, bos_count)

        prev_side = 0 if vwap is None else (1 if r.c > vwap else -1 if r.c < vwap else 0)

    for x in evs:
        x.outcome = resolve(rows, x.entry_i, x.direction, x.entry, x.stop)
    return evs


_CTRL_CACHE = {}


def control(rows, direction, risk_atr, n=12000, seed=7):
    """Random entries in ONE direction at a fixed stop distance. This is the number an
    event set has to beat; without splitting by direction, gold's drift hides inside it."""
    key = (direction, round(risk_atr, 2), n, seed)
    if key in _CTRL_CACHE:
        return _CTRL_CACHE[key]
    rnd, a, out = random.Random(seed), atr(rows), []
    for _ in range(n):
        i = rnd.randrange(200, len(rows) - HORIZON - 1)
        entry = rows[i].c
        stop = entry - direction * risk_atr * a[i]
        out.append(Event("CTRL", i, direction, entry, stop, 0, risk_atr,
                         outcome=resolve(rows, i, direction, entry, stop)))
    _CTRL_CACHE[key] = out
    return out


def line(label, evs, rows=None):
    n = len(evs)
    if not n:
        print(f"{label:<40} n=0"); return
    w = sum(1 for e in evs if e.outcome == "win")
    l = sum(1 for e in evs if e.outcome == "loss")
    dec = w + l
    wr = w / dec if dec else 0.0
    exp = (w * RR_TARGET - l) / n
    se = (wr * (1 - wr) / dec) ** 0.5 if dec > 1 else 0.0
    med = statistics.median(e.risk_atr for e in evs)
    edge = ""
    if rows is not None and dec:
        # matched control: same direction mix, same median stop distance
        longs = sum(1 for e in evs if e.direction == 1) / n
        cl = control(rows, 1, med); cs = control(rows, -1, med)
        cwr = (longs * (sum(1 for e in cl if e.outcome == "win") /
                        max(1, sum(1 for e in cl if e.outcome in ("win", "loss"))))
               + (1 - longs) * (sum(1 for e in cs if e.outcome == "win") /
                                max(1, sum(1 for e in cs if e.outcome in ("win", "loss")))))
        z = (wr - cwr) / se if se else 0.0
        edge = f"  ctrl={cwr:>5.1%}  edge={wr-cwr:>+6.1%} ({z:>+4.1f}σ)"
    print(f"{label:<40} n={n:>5}  WR={wr:>6.1%}  expR={exp:>+6.3f}  risk={med:>4.2f}ATR{edge}")


if __name__ == "__main__":
    rows = drop_coarse(load())
    print(f"{len(rows)} true-M15 bars, "
          f"{datetime.fromtimestamp(rows[0].ts/1000, timezone.utc):%Y-%m-%d} -> "
          f"{datetime.fromtimestamp(rows[-1].ts/1000, timezone.utc):%Y-%m-%d}")
    print(f"scored at +{RR_TARGET}R before -1R; breakeven WR = {1/(1+RR_TARGET):.1%}\n")

    evs = collect(rows)
    cont = [e for e in evs if e.kind == "CONT"]
    d = [e for e in evs if e.kind == "D"]
    dside = [e for e in evs if e.kind == "D_side"]

    print("── the raw drift control, by direction (1.3 ATR stop) ──")
    for dr, nm in ((1, "long"), (-1, "short")):
        line(f"  random {nm}", control(rows, dr, 1.3))
    print("── ditto at D's much wider stop (2.9 ATR) ──")
    for dr, nm in ((1, "long"), (-1, "short")):
        line(f"  random {nm}", control(rows, dr, 2.9))

    print("\n── the two triggers, vs a matched control ──")
    line("CONT  with-trend BOS -> 0.5 retrace", cont, rows)
    line("D     counter-SOS -> VWAP reclaim", d, rows)
    line("D     counter-SOS -> VWAP side only", dside, rows)

    print("\n── does VWAP help CONT? (the combination asked about) ──")
    line("CONT  pro-trend side of VWAP", [e for e in cont if e.vwap_ok], rows)
    line("CONT  wrong side of VWAP", [e for e in cont if not e.vwap_ok], rows)

    print("\n── does the dCtrBosMax gate help D? ──")
    line("D     shakeout printed no BOS", [e for e in d if e.ctr_bos == 0], rows)
    line("D     shakeout printed >=1 BOS", [e for e in d if e.ctr_bos >= 1], rows)

    print("\n── by direction ──")
    for dr, nm in ((1, "long"), (-1, "short")):
        line(f"CONT  {nm}", [e for e in cont if e.direction == dr], rows)
        line(f"D     {nm}", [e for e in d if e.direction == dr], rows)

    print("\n── CONT by trend maturity ──")
    for lo, hi in ((1, 1), (2, 2), (3, 3), (4, 99)):
        line(f"CONT  {lo}-{hi} BOS deep", [e for e in cont if lo <= e.maturity <= hi], rows)

    print("\n── CONT: VWAP filter AND maturity together ──")
    for lo, hi in ((1, 2), (3, 99)):
        line(f"CONT  {lo}-{hi} BOS + VWAP ok",
             [e for e in cont if lo <= e.maturity <= hi and e.vwap_ok], rows)

    # ---------------- robustness: is the edge spread across time, or one lucky year?
    print("\n── CONT+VWAP by period (an edge living in one year is a curve fit) ──")
    import collections
    yrs = collections.defaultdict(list)
    for e in [x for x in cont if x.vwap_ok]:
        yrs[datetime.fromtimestamp(rows[e.entry_i].ts / 1000, timezone.utc).year].append(e)
    for y in sorted(yrs):
        line(f"CONT+VWAP  {y}", yrs[y], rows)

    print("\n── CONT+VWAP vs R target (an edge only at 2R is an artefact of 2R) ──")
    g = globals()
    for rr in (1.0, 1.5, 2.0, 3.0, 4.0):
        g["RR_TARGET"] = rr
        _CTRL_CACHE.clear()
        sub = [Event(e.kind, e.entry_i, e.direction, e.entry, e.stop, e.maturity,
                     e.risk_atr, e.vwap_ok, e.ctr_bos, e.bars_wait,
                     resolve(rows, e.entry_i, e.direction, e.entry, e.stop))
               for e in cont if e.vwap_ok]
        dd = [Event(e.kind, e.entry_i, e.direction, e.entry, e.stop, e.maturity,
                    e.risk_atr, e.vwap_ok, e.ctr_bos, e.bars_wait,
                    resolve(rows, e.entry_i, e.direction, e.entry, e.stop)) for e in d]
        print(f"  target +{rr}R  (breakeven WR {1/(1+rr):.1%})")
        line("    CONT+VWAP", sub, rows)
        line("    D", dd, rows)
    g["RR_TARGET"] = 2.0
