"""ny_open_scalp_study.py — is there a scalping edge on gold in the New York morning, traded off the
MPC-JARVIS indicator's own levels: the 09:30-09:35 opening range, the 08:00-09:30 pre-open range
and the session VWAP — as a break, a break-and-retest, or a failed break?

A STUDY, not a strategy: one-trade-per-day books and real costs, no Pine twin, no parity gate, so
every number it prints is a lab finding. Built on `killzone_study.py` — its day grid, ATR, walk and
costs, which come from `loaded_level_study.py` / `structure_patterns.py` — and imports them. The
opening range is read off `engines/sessions/` and the VWAP off `engines/vwap/`, the canonical
engines; neither is recomputed here.

THE ASK (the user, 2026-09-15): "inspect what strategy I can create around these times for
scalping the market, the mpc jarvis have 5min range also that can be used and vwap for a break and
retest strategy."

THE LEVELS
  OR5   the New York opening range: SessionEngine's high/low over its 09:30-09:34 NY window (the
        window is read off the engine, not typed in). A day whose window holds fewer than 3 bars is
        skipped, because the engine then carries yesterday's range. CHECK: the engine's range equals
        the grid's own high/low of those minutes on every day used; one difference raises.
  PRE   the pre-open range: the high/low of 08:00-09:29 NY, the 08:30 data hour inside it.
  VWAP  VwapEngine's session VWAP (hlc3, volume-weighted, reset 18:00 NY) on the M1 feed. A missing
        volume is fed as None — "cannot compute", never zero.

THE RULES — 14 entries x 2 stops x 3 exits = 84, declared before any result existed
  break    OR5/PRE: the first bar that CLOSES beyond the range — trade that way.
           VWAP:    the first bar whose close sits on the other side of VWAP from the last close.
  retest   OR5/PRE: after the break, the first bar that trades back to the broken edge — if it
                    CLOSES on the break side, trade the break; if not, no retest that day.
           VWAP:    after the latest cross, the first bar that trades back to the line and closes
                    on the cross side — trade the cross side.
  fail     OR5/PRE: after the break, the first bar that closes back inside the range — trade
                    AGAINST the break.
  +vwap    OR5/PRE: a second copy of each entry, taken only when the signal bar's close is on the
           trade's side of VWAP (the user's "VWAP confluence").
  WINDOW   signal bars: OR5 09:35-10:59, PRE 09:30-10:59, VWAP 08:00-10:59 NY (the 08:00-09:30
           window and the 10:00 kill zone inside all of them). One trade per rule per day: its
           first signal.
  ENTRY    the next bar's open. Bars are bid; a long pays the spread.
  STOP     0.5 or 1.0 x ATR(14, 1-hour), the last hour completed before the entry bar.
  EXIT     a 1R target, a 2R target, or none; out at market after 60 one-minute bars. A trade whose
           60 bars would run past 16:59 NY is skipped (none should).
  WALK/COSTS  killzone_study's: FastWalk proven against Book.walk on every real trade here;
           puprime_ecn (spread 0.12, $1/side/lot).

DATA WINDOWS — the rules killzone_study.py / structure_patterns.py enforce
  EXPLORE  2020-01-01 -> 2025-08-31. Every selection decision is made on these bars only.
  🔴 TEST  2018-09-14 -> 2019-12-31, ONCE, with `test --spend-test-set`, only on rules that pass all
           three gates. No opening-range or VWAP rule has ever been run on it.
  SPENT    2025-09-01 onward is never loaded.

GATES — fixed, in this order
  1 SAMPLE  >= 25 trades in each half of explore (bar-count midpoint), net R positive in both.
  2 LUCK    the WHOLE 84-rule search re-run 200 times with every real trade moved to a random bar
            INSIDE ITS RULE'S WINDOW on a random explore weekday — same direction, same stop in ATR,
            same target in R, same walk and costs. The best t (net R per trade) of any rule through
            gate 1 is recorded per run; a rule must beat the 95th percentile.
  3 ENTRY   its GROSS R beats a matched random-entry control — same direction, same stop and target
            distance in price, entered at a random bar inside the same window, 20 draws a trade —
            at z >= 2.
  TEST      pass = net R per trade > 0 and t >= 1.65 on the test set.

TEST PLAN — declared 2026-09-15 AFTER explore and BEFORE any test-set bar was loaded
  No rule passed all three gates, so by the rules above the test set stays unspent. It is spent
  anyway, ONCE, through `plan --spend-test-set`, on the two claims below and on nothing else, for
  two reasons measured on explore: the FAMILY is not luck (26 rules through gate 1 against a
  maximum of 14 in 200 random-entry runs), and one mechanism repeats across entry types — trades on
  VWAP's side beat trades against it in 11 of 12 entry/exit pairs. More explore data cannot say
  more; only months nobody has looked at can.
  C1 VWAP SIDE  net R of trades on VWAP's side minus trades against it, pooled over the six OR5/PRE
                entries at 0.5 ATR / no target, standard error clustered by New York day. Explore
                reference: +0.179R, se 0.070, z +2.57. PASS = difference > 0 at z >= 1.0.
  C2 THE RULE   OR5|fail|vwap|s0.5|time. Explore: 529 trades, +0.203R each, t +2.25.
                PASS = net R per trade > 0.
  ⚠ POWER, stated before the run: 15 months hold about a fifth of explore's days, so if the explore
    effects were fully real C1 would show z ~ 1.2 and C2 t ~ 1.1. These are SCREENS — a negative
    result is strong evidence against the idea, a positive one is modest support. A double pass
    sends the rule to a DEMO forward test at small risk, never straight to money. ⚠ C2's ten best
    explore trades made 84% of its profit, so its test result leans on whether a big day lands in
    those 15 months.
  Nothing else runs on the test set, and nothing is re-tuned after it.

MEASURED 2026-09-15 — PU Prime XAUUSD.p M1, puprime_ecn
  EXPLORE 2,005,828 bars: 0 of 84 rules pass all three gates; 26 pass gate 1 (random runs: median
    7, max 14); best t +2.25 against a luck bar of +2.45; 10 pass gate 3; C1 +0.179R, z +2.57.
  TEST SET 457,977 bars, spent once by `plan --spend-test-set`: C1 -0.121R, z -0.95 -> FAIL
    (a real explore-sized effect lands this far the wrong way about 1 time in 100); C2 125 trades,
    -0.180R each, -22.5R, t -1.30 -> FAIL. Nothing to build. The test set is SPENT for
    opening-range, pre-open-range and VWAP-side ideas. Record: backtest/notes/tools.md.

Usage (from the repo root, with command-center/backend/.venv/bin/python):
  python backtest/tools/ny_open_scalp_study.py explore
  python backtest/tools/ny_open_scalp_study.py plan                    # explore reference
  python backtest/tools/ny_open_scalp_study.py plan --spend-test-set   # ONCE
  python backtest/tools/ny_open_scalp_study.py test --rules 'OR5|retest|vwap|s0.5|2R' --spend-test-set
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "engines", ROOT / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import killzone_study as K  # noqa: E402
from sessions import SessionEngine  # noqa: E402
from vwap import VwapEngine  # noqa: E402

HOLD = 60  # one-minute bars
PRE = (8 * 60, 9 * 60 + 30)  # [start, end) NY — the user's "8-9:30"
WINDOW_END = 10 * 60 + 59  # last signal minute, NY
VWAP_FROM = 8 * 60
MIN_OR_BARS = 3
ENTRIES = [
    (lvl, ent, al) for lvl in ("OR5", "PRE") for ent in ("break", "retest", "fail") for al in (0, 1)
] + [("VWAP", "break", 0), ("VWAP", "retest", 0)]
STOPS = (0.5, 1.0)
EXITS = ("1R", "2R", "time")
RULES = [e + (s, x) for e in ENTRIES for s in STOPS for x in EXITS]
CONTROL_REPS, Z_TO_BEAT = 20, 2.0
SEED = 20260916


def rule_label(r: tuple) -> str:
    lvl, ent, al, stop, ex = r
    return f"{lvl}|{ent}|{'vwap' if al else 'any'}|s{stop:g}|{ex}"


def parse_rule(text: str) -> tuple:
    lvl, ent, al, stop, ex = text.split("|")
    r = (lvl, ent, 1 if al == "vwap" else 0, float(stop[1:]), ex)
    if r not in RULES:
        sys.exit(f"not a declared rule: {text}")
    return r


def or_window() -> tuple:
    """[start, end) NY minutes of the opening-range window, read off SessionEngine."""
    se, t0 = SessionEngine(), pd.Timestamp("2024-01-10", tz=K.S.NY)
    on = []
    for m in range(1440):
        ev = se.update(m, int((t0 + pd.Timedelta(minutes=m)).timestamp() * 1000), 1.0, 1.0)
        if ev.in_ny_range_window:
            on.append(m)
    if not on or on[-1] - on[0] + 1 != len(on):
        raise RuntimeError("the NY opening-range window is not one contiguous window")
    return on[0], on[-1] + 1


# ─────────────────────────────── levels ───────────────────────────────


@dataclass
class Levels:
    orh: np.ndarray  # per day: opening-range high, NaN = day skipped
    orl: np.ndarray
    prh: np.ndarray  # per day: pre-open high / low
    prl: np.ndarray
    V: np.ndarray  # [day, minute] session VWAP after that bar, NaN = no bar
    Vf: np.ndarray  # carried forward within the day
    windows: dict  # level -> (first, last) signal minute
    bar_vwap: np.ndarray  # per M1 bar, weekend dates included: VWAP after that bar, NaN = unknown


def levels(tp: K.Tape) -> Levels:
    t0 = time.time()
    ow = or_window()
    se, vw = SessionEngine(), VwapEngine()
    ms = tp.raw.index.asi8 // 10**6
    h, lo, c, v = (tp.raw[k].to_numpy() for k in ("high", "low", "close", "volume"))
    orh, orl, vwap = (np.full(tp.n, np.nan) for _ in range(3))
    missing_vol = 0
    for i in range(tp.n):
        ev = se.update(i, int(ms[i]), float(h[i]), float(lo[i]))
        if ev.ny_range_high is not None:
            orh[i], orl[i] = ev.ny_range_high, ev.ny_range_low
        vol = None if np.isnan(v[i]) else float(v[i])
        missing_vol += vol is None
        val = vw.update(i, int(ms[i]), float(h[i]), float(lo[i]), float(c[i]), vol).value
        if val is not None:
            vwap[i] = val
    D = len(tp.days)
    rows = np.arange(D)
    first = tp.nxt[:, ow[1]]  # first bar at/after the window closes
    enough = np.sum(~np.isnan(tp.H[:, ow[0] : ow[1]]), axis=1) >= MIN_OR_BARS
    ok = enough & (first >= 0)
    ok &= tp.minute[np.where(ok, first, 0)] < ow[1] + K.ENTRY_SLACK
    d_orh = np.where(ok, orh[np.where(ok, first, 0)], np.nan)
    d_orl = np.where(ok, orl[np.where(ok, first, 0)], np.nan)
    with np.errstate(invalid="ignore"), K.warnings.catch_warnings():
        K.warnings.simplefilter("ignore", RuntimeWarning)
        g_hi = np.nanmax(tp.H[:, ow[0] : ow[1]], axis=1)
        g_lo = np.nanmin(tp.L[:, ow[0] : ow[1]], axis=1)
        prh = np.nanmax(tp.H[:, PRE[0] : PRE[1]], axis=1)
        prl = np.nanmin(tp.L[:, PRE[0] : PRE[1]], axis=1)
    bad = int(np.sum(ok & ((d_orh != g_hi) | (d_orl != g_lo))))
    if bad:
        raise RuntimeError(f"SessionEngine's opening range differs from the grid on {bad} days")
    pre_ok = np.sum(~np.isnan(tp.H[:, PRE[0] : PRE[1]]), axis=1) >= (PRE[1] - PRE[0]) / 2
    prh, prl = np.where(pre_ok, prh, np.nan), np.where(pre_ok, prl, np.nan)
    V = np.full(tp.idx.shape, np.nan)
    wk = tp.day >= 0
    V[tp.day[wk], tp.minute[wk]] = vwap[wk]
    lv = Levels(
        orh=d_orh, orl=d_orl, prh=prh, prl=prl, V=V,
        Vf=pd.DataFrame(V).ffill(axis=1).to_numpy(),
        windows={"OR5": (ow[1], WINDOW_END), "PRE": (PRE[1], WINDOW_END),
                 "VWAP": (VWAP_FROM, WINDOW_END)}, bar_vwap=vwap,
    )  # fmt: skip
    print(
        f"CHECK 2 — opening range {K.hhmm(ow[0])}-{K.hhmm(ow[1] - 1)} NY from SessionEngine: "
        f"{int(ok.sum()):,} of {D:,} days usable, engine = grid on every one; pre-open range on "
        f"{int(pre_ok.sum()):,} days; VWAP from VwapEngine, {missing_vol} bars without volume "
        f"({time.time() - t0:.0f}s)"
    )
    return lv


# ─────────────────────────────── signals ───────────────────────────────


def range_signals(tp: K.Tape, hi: np.ndarray, lo: np.ndarray, w0: int, w1: int):
    """Per day over signal minutes w0..w1: the break minute and side, then the retest and the
    fail minutes after it. -1 = none."""
    D = len(tp.days)
    brk, bdir = np.full(D, -1), np.zeros(D, np.int64)
    ret, dead, fail = np.full(D, -1), np.zeros(D, bool), np.full(D, -1)
    lvl_ok = np.isfinite(hi) & np.isfinite(lo)
    for m in range(w0, w1 + 1):
        c, h, lw = tp.C[:, m], tp.H[:, m], tp.L[:, m]
        live = lvl_ok & np.isfinite(c)
        with np.errstate(invalid="ignore"):
            up, dn = live & (brk >= 0) & (bdir == 1), live & (brk >= 0) & (bdir == -1)
            touch = (up & (lw <= hi)) | (dn & (h >= lo))
            held = (up & (c > hi)) | (dn & (c < lo))
            back = (up & (c < hi)) | (dn & (c > lo))
            first_touch = touch & (ret == -1) & ~dead
            ret = np.where(first_touch & held, m, ret)
            dead |= first_touch & ~held
            fail = np.where(back & (fail == -1), m, fail)
            new = live & (brk == -1)
            bu, bd = new & (c > hi), new & (c < lo)
        brk = np.where(bu | bd, m, brk)
        bdir = np.where(bu, 1, np.where(bd, -1, bdir))
    return brk, bdir, ret, fail


def vwap_signals(tp: K.Tape, lv: Levels, w0: int, w1: int):
    """Per day: the first VWAP cross (minute, side) and the first retest after the latest cross."""
    D = len(tp.days)
    with np.errstate(invalid="ignore"):
        prev = np.nan_to_num(np.sign(tp.Cf[:, w0 - 1] - lv.Vf[:, w0 - 1]))
    cross, cdir = np.full(D, -1), np.zeros(D, np.int64)
    ret, rdir = np.full(D, -1), np.zeros(D, np.int64)
    arm, armed_at = np.zeros(D, np.int64), np.full(D, -1)
    for m in range(w0, w1 + 1):
        c, h, lw, v = tp.C[:, m], tp.H[:, m], tp.L[:, m], lv.V[:, m]
        live = np.isfinite(c) & np.isfinite(v)
        with np.errstate(invalid="ignore"):
            side = np.where(live, np.sign(c - v), 0).astype(np.int64)
            ready = live & (armed_at >= 0) & (armed_at < m) & (ret == -1)
            held = (ready & (arm == 1) & (lw <= v) & (c > v)) | (
                ready & (arm == -1) & (h >= v) & (c < v)
            )
        ret = np.where(held, m, ret)
        rdir = np.where(held, arm, rdir)
        x = live & (side != 0) & (prev != 0) & (side != prev)
        first = x & (cross == -1)
        cross = np.where(first, m, cross)
        cdir = np.where(first, side, cdir)
        arm = np.where(x, side, arm)
        armed_at = np.where(x, m, armed_at)
        prev = np.where(live & (side != 0), side, prev)
    return cross, cdir, ret, rdir


def make(tp: K.Tape, lv: Levels, m: np.ndarray, d: np.ndarray, align: bool) -> dict:
    """Signal minute + side per day -> entry at the next bar, with the usual existence checks."""
    rows = np.flatnonzero(m >= 0)
    mm, dd = m[rows], d[rows]
    trig = tp.idx[rows, mm]
    ok = (trig >= 0) & (dd != 0)
    e = np.where(ok, trig + 1, -1)
    ok &= e < tp.n
    ee, tt = np.where(ok, e, 0), np.where(ok, trig, 0)
    ok &= (tp.day[ee] == tp.day[tt]) & (tp.minute[ee] - tp.minute[tt] <= K.ENTRY_SLACK)
    ok &= K._hold_ok(tp, np.where(ok, e, -1))
    if align:
        c, v = tp.C[rows, mm], lv.V[rows, mm]
        with np.errstate(invalid="ignore"):
            ok &= np.where(dd == 1, c > v, c < v)
    return dict(e=e[ok], is_long=(dd == 1)[ok])


def entry_sets(tp: K.Tape, lv: Levels) -> dict:
    out = {}
    for name, hi, lo in (("OR5", lv.orh, lv.orl), ("PRE", lv.prh, lv.prl)):
        brk, bdir, ret, fail = range_signals(tp, hi, lo, *lv.windows[name])
        for ent, m, d in (("break", brk, bdir), ("retest", ret, bdir), ("fail", fail, -bdir)):
            for al in (0, 1):
                out[(name, ent, al)] = make(tp, lv, m, d, bool(al))
    cross, cdir, ret, rdir = vwap_signals(tp, lv, *lv.windows["VWAP"])
    out[("VWAP", "break", 0)] = make(tp, lv, cross, cdir, False)
    out[("VWAP", "retest", 0)] = make(tp, lv, ret, rdir, False)
    if list(out) != ENTRIES:
        raise RuntimeError("entry order drifted from ENTRIES")
    return out


# ─────────────────────────────── trades and gates ───────────────────────────────


def evaluate(tp: K.Tape, sets: dict, prove=False) -> dict:
    res = {}
    for key, s in sets.items():
        e, il = s["e"], s["is_long"]
        a, first = tp.atr[e], e < tp.split
        for stop in STOPS:
            risk = stop * a
            for ex in EXITS:
                net, gross, xb, how = K.walk(tp, e, il, risk, K.EXIT_R[ex], prove)
                res[key + (stop, ex)] = dict(
                    st=K.cell_stats(net, first), e=e, is_long=il, risk=risk, net=net,
                    gross=gross, how=how,
                )  # fmt: skip
    return res


def pools(tp: K.Tape, lv: Levels) -> dict:
    """Every bar a real trade of each level could enter on: the bar after a window minute."""
    out = {}
    wk = tp.day >= 0
    for name, (w0, w1) in lv.windows.items():
        cand = np.flatnonzero(wk & (tp.minute >= w0 + 1) & (tp.minute <= w1 + 1))
        out[name] = cand[K._hold_ok(tp, cand)]
    return out


def luck_bar(tp: K.Tape, res: dict, pool: dict, runs: int, seed: int) -> dict:
    """Gate 2 — the whole search on random entries inside each rule's own window."""
    keys = [k for k in RULES if res[k]["st"][0] >= 2 * K.MIN_PER_HALF]
    best, npass = np.full(runs, -np.inf), np.zeros(runs, np.int64)
    if not keys:
        return dict(best=best, npass=npass)
    sid = np.concatenate([np.full(len(res[k]["e"]), g) for g, k in enumerate(keys)])
    il = np.concatenate([res[k]["is_long"] for k in keys])
    mult = np.concatenate([np.full(len(res[k]["e"]), k[3]) for k in keys])
    exit_ = np.concatenate([np.full(len(res[k]["e"]), EXITS.index(k[4])) for k in keys])
    lvl = np.concatenate([np.full(len(res[k]["e"]), k[0]) for k in keys])
    ns, total = len(keys), len(sid)
    rng = np.random.default_rng(seed)
    t0 = time.time()
    for run in range(runs):
        e = np.empty(total, np.int64)
        for name, p in pool.items():
            sel = lvl == name
            e[sel] = p[rng.integers(0, len(p), size=int(sel.sum()))]
        net = np.empty(total)
        for xi, ex in enumerate(EXITS):
            sel = exit_ == xi
            net[sel] = K.walk(tp, e[sel], il[sel], mult[sel] * tp.atr[e[sel]], K.EXIT_R[ex])[0]
        first = e < tp.split
        cnt = np.bincount(sid, minlength=ns)
        n1 = np.bincount(sid[first], minlength=ns)
        h1 = np.bincount(sid[first], weights=net[first], minlength=ns)
        h2 = np.bincount(sid[~first], weights=net[~first], minlength=ns)
        mean = np.bincount(sid, weights=net, minlength=ns) / cnt
        sd = np.sqrt(np.bincount(sid, weights=(net - mean[sid]) ** 2, minlength=ns) / (cnt - 1))
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(sd > 0, mean / (sd / np.sqrt(cnt)), 0.0)
        ok = (n1 >= K.MIN_PER_HALF) & (cnt - n1 >= K.MIN_PER_HALF) & (h1 > 0) & (h2 > 0)
        npass[run] = int(ok.sum())
        if ok.any():
            best[run] = float(t[ok].max())
        if (run + 1) % 50 == 0:
            print(f"  null run {run + 1}/{runs}  ({time.time() - t0:.0f}s)")
    return dict(best=best, npass=npass)


def matched_control(tp: K.Tape, r: dict, pool: np.ndarray, rng) -> float:
    """Gate 3 — z of the rule's gross R against random entries inside its window with the same
    direction and the same stop and target distance in price."""
    n = len(r["e"])
    if n < 2:
        return math.nan
    e = pool[rng.integers(0, len(pool), size=n * CONTROL_REPS)]
    il = np.repeat(r["is_long"], CONTROL_REPS)
    risk = np.repeat(r["risk"], CONTROL_REPS)
    mult = K.EXIT_R[r["exit"]]
    g = K.walk(tp, e, il, risk, mult)[1]
    real = r["gross"]
    return float(
        (real.mean() - g.mean()) / math.sqrt(real.var(ddof=1) / n + g.var(ddof=1) / len(g))
    )


# ─────────────────────────────── report ───────────────────────────────


def explore(a) -> None:
    if a.null_runs < K.MIN_NULL_RUNS:
        sys.exit(f"refused: the luck bar needs at least {K.MIN_NULL_RUNS} null runs")
    t_all = time.time()
    tp = K.build_tape(K.load_1m(*K.EXPLORE, volume=True), hold=HOLD)
    lv = levels(tp)
    sets = entry_sets(tp, lv)
    t0 = time.time()
    res = evaluate(tp, sets, prove=True)
    nw = sum(len(s["e"]) for s in sets.values()) * len(STOPS) * len(EXITS)
    print(
        f"CHECK 1 — FastWalk matched Book.walk on every real trade ({nw:,} walks) "
        f"({time.time() - t0:.0f}s)"
    )
    pool = pools(tp, lv)
    luck = luck_bar(tp, res, pool, a.null_runs, a.seed)
    q95 = float(np.quantile(luck["best"], K.NULL_Q))
    rng = np.random.default_rng(7)
    rows = []
    for k in RULES:
        r = res[k] | dict(exit=k[4])
        n, n1, h1, h2, mean, t = r["st"]
        g1 = bool((n1 >= K.MIN_PER_HALF) and (n - n1 >= K.MIN_PER_HALF) and h1 > 0 and h2 > 0)
        z = matched_control(tp, r, pool[k[0]], rng)
        yrs = tp.raw.index[r["e"]].year.to_numpy() if n else np.array([])
        rows.append(
            dict(
                rule=rule_label(k), n=int(n), per_month=n / tp.months,
                win=float(np.mean(r["net"] > 0) * 100) if n else 0.0,
                avg_gross=float(r["gross"].mean()) if n else 0.0, avg_net=mean,
                total_net=float(r["net"].sum()), h1=h1, h2=h2, t=t, z_entry=z,
                long_net=float(r["net"][r["is_long"]].sum()),
                short_net=float(r["net"][~r["is_long"]].sum()),
                gate1=g1, beats_luck=bool(g1 and t > q95), gate3=bool(g1 and z >= Z_TO_BEAT),
                by_year="  ".join(f"{y}:{r['net'][yrs == y].sum():+.1f}" for y in np.unique(yrs)),
            )
        )  # fmt: skip
    out = Path(a.out)
    K.write_csv(out / "rules.csv", rows)
    K.write_csv(
        out / "luck.csv",
        [dict(run=i, best_t=b, n_gate1=int(k)) for i, (b, k) in enumerate(zip(luck["best"], luck["npass"]))],
    )  # fmt: skip
    win = [r for r in rows if r["gate1"] and r["beats_luck"] and r["gate3"]]
    best_real = max((r["t"] for r in rows if r["gate1"]), default=-math.inf)
    print(f"\nSEARCH — {len(RULES)} rules, {K.PROFILE} costs, {HOLD}-bar time exit")
    print(
        f"  gate 1 — both halves net positive, >= {K.MIN_PER_HALF} each: {sum(r['gate1'] for r in rows)}"
    )
    print(
        f"  gate 2 — luck bar ({a.null_runs} runs, seed {a.seed}): best t per run median "
        f"{np.median(luck['best']):+.2f}, 95th percentile {q95:+.2f}; best real t {best_real:+.2f} "
        f"(beaten by {np.mean(luck['best'] >= best_real) * 100:.1f}% of runs); random runs pass "
        f"gate 1 median {int(np.median(luck['npass']))}"
    )
    print(
        f"  gate 3 — entries beat matched random entries at z >= {Z_TO_BEAT}: {sum(r['gate3'] for r in rows)}"
    )
    print(f"  ALL THREE GATES: {len(win)}")
    head = (
        f"\n  {'rule':<26} {'n':>5} {'/mo':>5} {'win%':>5} {'gross':>7} {'net':>7} {'tot R':>7} "
        f"{'1st½':>7} {'2nd½':>7} {'t':>6} {'z':>6}  g1 luck g3"
    )
    yn = lambda b: " Y" if b else " ."  # noqa: E731
    print(f"\nALL RULES BY t{head}")
    for r in sorted(rows, key=lambda r: -r["t"]):
        print(
            f"  {r['rule']:<26} {r['n']:>5} {r['per_month']:>5.1f} {r['win']:>5.1f} "
            f"{r['avg_gross']:>+7.3f} {r['avg_net']:>+7.3f} {r['total_net']:>+7.1f} {r['h1']:>+7.1f} "
            f"{r['h2']:>+7.1f} {r['t']:>+6.2f} {r['z_entry']:>+6.2f} {yn(r['gate1'])}  "
            f"{yn(r['beats_luck'])}  {yn(r['gate3'])}"
        )
    for r in sorted(rows, key=lambda r: -r["t"])[:5]:
        print(
            f"  {r['rule']}: {r['by_year']}  | long {r['long_net']:+.1f} short {r['short_net']:+.1f}"
        )
    if win:
        print("\n  -> ONE run on the test set: test --rules '<rule>' --spend-test-set")
    else:
        print("\nNo rule passed all three gates — the test set stays UNSPENT.")
    print(f"\ncsv: {out}/  ({time.time() - t_all:.0f}s)")


def test(a) -> None:
    if not a.spend_test_set:
        sys.exit(
            f"refused: {K.TEST_SET[0]} -> {K.TEST_SET[1]} is the untouched test set. It gets ONE run, "
            "only on rules that passed all three explore gates. Add --spend-test-set to spend it."
        )
    picks = [parse_rule(x.strip()) for x in a.rules.split(",")]
    tp = K.build_tape(K.load_1m(*K.TEST_SET, volume=True), hold=HOLD)
    res = evaluate(tp, entry_sets(tp, levels(tp)))
    print(
        f"\nTEST SET {K.TEST_SET[0]} -> {K.TEST_SET[1]} — pass = net R/trade > 0 and t >= {K.TEST_T}"
    )
    for k in picks:
        n, _, _, _, mean, t = res[k]["st"]
        ok = n > 1 and mean > 0 and t >= K.TEST_T
        print(
            f"  {rule_label(k)}: {int(n)} trades, net {mean:+.3f} R/trade, total "
            f"{res[k]['net'].sum():+.1f}R, t {t:+.2f} -> {'PASS' if ok else 'FAIL'}"
        )


# ─────────────────────────────── the test plan (see TEST PLAN) ───────────────────────────────

C1_STOP, C1_EXIT, C1_Z = 0.5, "time", 1.0  # z bar set to the test set's power — see TEST PLAN
C2_RULE = ("OR5", "fail", 1, 0.5, "time")


def vwap_side(tp: K.Tape, res: dict, sets: dict) -> dict:
    """C1 — net R of trades on VWAP's side minus trades against it, pooled over the six OR5/PRE
    entries at 0.5 ATR / no target. One OLS of net R on a with-VWAP indicator; its slope is exactly
    that difference. The standard error is CLUSTERED BY NEW YORK DAY, because two entries on one
    day are often the same move and would otherwise count as two independent answers."""
    y, x, g = [], [], []
    for lvl in ("OR5", "PRE"):
        for ent in ("break", "retest", "fail"):
            r = res[(lvl, ent, 0, C1_STOP, C1_EXIT)]
            y.append(r["net"])
            x.append(np.isin(r["e"], sets[(lvl, ent, 1)]["e"]).astype(float))
            g.append(tp.day[r["e"]])
    y, x, g = (np.concatenate(v) for v in (y, x, g))
    X = np.column_stack([np.ones_like(x), x])
    inv = np.linalg.inv(X.T @ X)
    beta = inv @ X.T @ y
    u = y - X @ beta
    days, gi = np.unique(g, return_inverse=True)
    S = np.zeros((len(days), 2))
    np.add.at(S, gi, X * u[:, None])
    c = len(days) / (len(days) - 1) * (len(y) - 1) / (len(y) - 2)
    se = float(math.sqrt((c * inv @ (S.T @ S) @ inv)[1, 1]))
    return dict(
        diff=float(beta[1]), se=se, z=float(beta[1] / se), with_mean=float(beta[0] + beta[1]),
        against_mean=float(beta[0]), n_with=int(x.sum()), n_against=int(len(x) - x.sum()),
        days=len(days),
    )  # fmt: skip


def plan(a) -> None:
    """The ONE pre-declared test-set run. Without --spend-test-set it prints the same two numbers
    on explore, as a reference — those bars have already been seen."""
    spend = a.spend_test_set
    window = K.TEST_SET if spend else K.EXPLORE
    tp = K.build_tape(K.load_1m(*window, volume=True), hold=HOLD)
    sets = entry_sets(tp, levels(tp))
    res = evaluate(tp, sets, prove=True)
    c1 = vwap_side(tp, res, sets)
    n, n1, h1, h2, mean, t = res[C2_RULE]["st"]
    net = res[C2_RULE]["net"]
    tag = "TEST SET — spent" if spend else "EXPLORE — reference only, already seen"
    print(f"\nTEST PLAN on {window[0]} -> {window[1]}  ({tag})")
    print(
        f"  C1 VWAP side: with {c1['n_with']} trades {c1['with_mean']:+.3f}R, against "
        f"{c1['n_against']} {c1['against_mean']:+.3f}R, difference {c1['diff']:+.3f}R, "
        f"se {c1['se']:.3f} over {c1['days']} days, z {c1['z']:+.2f}"
        + (f" -> {'PASS' if c1['diff'] > 0 and c1['z'] >= C1_Z else 'FAIL'}" if spend else "")
    )
    print(
        f"  C2 {rule_label(C2_RULE)}: {int(n)} trades, net {mean:+.3f} R/trade, total "
        f"{net.sum():+.1f}R, t {t:+.2f}, win {np.mean(net > 0) * 100:.0f}%"
        + (f" -> {'PASS' if n > 1 and mean > 0 else 'FAIL'}" if spend else "")
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("explore")
    ex.add_argument("--null-runs", type=int, default=K.NULL_RUNS)
    ex.add_argument("--seed", type=int, default=SEED)
    ex.add_argument("--out", default="backtest/reports/ny_open_scalp_study")
    te = sub.add_parser("test")
    te.add_argument("--rules", required=True)
    te.add_argument("--spend-test-set", action="store_true")
    pl = sub.add_parser("plan")
    pl.add_argument("--spend-test-set", action="store_true")
    a = ap.parse_args()
    {"explore": explore, "test": test, "plan": plan}[a.cmd](a)


if __name__ == "__main__":
    main()
