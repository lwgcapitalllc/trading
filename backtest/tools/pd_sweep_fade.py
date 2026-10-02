#!/usr/bin/env python3
"""pd_sweep_fade.py — fade a sweep of the previous day's high/low on 5m. Which session, which entry?

A STUDY, not a strategy. Pinned with Aaron 2026-10-02 after a live SOS Fade stop was taken by a sweep
of the previous day's low inside Asia. Record and verdicts: `docs/SWEEP_LEVEL_STUDY.md`.

THE TRADE (long side; a short is the mirror):

    level    the previous trading day's low, day rolling 18:00 New York (`engines/liquidity/` owns
             the level and its creation — not reimplemented here)
    sweep    a 5m bar trades below it and CLOSES back above. Only the first touch of a level counts;
             a 5m close below it kills the level for the day (the `sweep_edge.py` rule)
    entry    three models, scored on the SAME signals so their rows compare:
               now    market at the sweep bar's close
               push   the next 5m bar must trade below its own open, then the first 1m close back
                      above that open is a market entry ("leaves a wick, starts forming a body").
                      No push, or no close back above, inside that one bar = no trade
               flip   the first 1m change of character up (internal or external, the canonical
                      structure engine) within 60 minutes of the sweep bar's close, cancelled if a
                      5m bar closes back below the level first
    stop     under the lowest low from the sweep to the entry, minus 0.1 ATR(5m, 14); never closer
             than 0.5 ATR (the stop is widened to it — cost would otherwise eat the R)
    target   two exits, scored separately (never as a ladder):
               near   the last small 5m swing high before the sweep (one bar either side, within
                      2 hours) — on 2026-10-02 the 4161.77 bounce
               far    the top of the whole drop: the highest high of the sweep bar and the 2 hours
                      before it — on 2026-10-02 the 4183.76 where the decline began
             A setup whose target is under 1R is skipped — it is not a trade anyone takes
    time     anything still open at the next 18:00 New York closes at that minute's open

COSTS: PU Prime ECN, the measured profile. Bars are BID: a buy and a short's exits transact at the ask
(bid + spread); commission both sides; swap per rollover held. R is the planned risk, entry to stop.

THE CONTROL: for every trade, CONTROL_K random 5m closes in the same half, same hour of day, same
direction, same stop and target distances in price, walked identically. Gold rose ~2.5x across the
window, so a long-side number with no control is partly just the trend.

⚠ No look-ahead: every decision reads bars up to and including the minute it is taken on, and the
walk starts on the minute AFTER entry. Same-minute stop and target is scored as the stop.

Usage:
    python3 backtest/tools/pd_sweep_fade.py
    python3 backtest/tools/pd_sweep_fade.py --csv backtest/reports/pd_sweep_fade/trades.csv
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engines"))

from liquidity import LiquidityEngine  # noqa: E402
from market_structure import Bar, StructureEngine  # noqa: E402
from sessions import SessionEngine  # noqa: E402

from backtest.data.resample import resample_up  # noqa: E402
from backtest.data.source import BarSource  # noqa: E402
from backtest.fills import PROFILES  # noqa: E402
from backtest.reprice import rollovers_between  # noqa: E402

NY = ZoneInfo("America/New_York")
SYMBOL = "XAUUSD.p"
PROFILE = "puprime_ecn"
SPLIT = pd.Timestamp("2023-05-01")  # discovery before, confirmation from
LOOKBACK_5M = 24  # bars before the sweep searched for the top of the drop
STOP_BUF_ATR = 0.1
MIN_STOP_ATR = 0.5
MIN_REWARD_R = 1.0
FLIP_WINDOW_MIN = 60
FLIP_WARMUP_MIN = 600
CONTROL_K = 10
ENTRY_MODELS = ("now", "push", "flip")
EXITS = ("near", "far")
MODELS = tuple(f"{e}/{x}" for e in ENTRY_MODELS for x in EXITS)
SESSIONS = ("Asia", "London", "NY", "between")


@dataclass
class Signal:
    k: int  # 5m bar index of the sweep
    t: pd.Timestamp  # sweep bar open, naive UTC
    d: int  # +1 long (low swept), -1 short (high swept)
    level: float
    ext: float  # the sweep bar's extreme
    near: Optional[float]  # last small swing before the sweep — target "near"
    far: float  # top of the whole drop — target "far"
    atr: float
    session: str
    trades: Dict[str, dict] = field(default_factory=dict)


# ----------------------------------------------------------------------------- data


def load(start: str, end: str):
    m1 = BarSource().load(SYMBOL, 1, start, end)
    m5 = resample_up(m1[["open", "high", "low", "close"]], 5, 1)
    return m1, m5


def wilder_atr(h, l, c, n=14):
    out = np.empty(len(c))
    a = h[0] - l[0]
    for i in range(len(c)):
        tr = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        a = tr if i == 0 else (a * (n - 1) + tr) / n
        out[i] = a
    return out


def next_rollover(t: pd.Timestamp) -> pd.Timestamp:
    """The first 18:00 New York strictly after `t` (naive UTC in, naive UTC out)."""
    loc = t.to_pydatetime().replace(tzinfo=timezone.utc).astimezone(NY)
    r = datetime(loc.year, loc.month, loc.day, 18, tzinfo=NY)
    if r <= loc:
        nxt = loc.date() + timedelta(days=1)
        r = datetime(nxt.year, nxt.month, nxt.day, 18, tzinfo=NY)
    return pd.Timestamp(r.astimezone(timezone.utc).replace(tzinfo=None))


# ----------------------------------------------------------------------------- signals


def find_signals(m5: pd.DataFrame) -> List[Signal]:
    o, h, l, c = (m5[x].to_numpy() for x in ("open", "high", "low", "close"))
    ts = m5.index
    atr = wilder_atr(h, l, c)
    liq = LiquidityEngine()
    sess = SessionEngine()
    pdh = pdl = None
    out: List[Signal] = []
    for k in range(len(c)):
        ms = int(ts[k].tz_localize("UTC").value // 10**6)
        ev = liq.update(k, ms, h[k], l[k], c[k])
        sv = sess.update(k, ms, h[k], l[k])
        for lvl in ev.created:
            if lvl.kind == "daily" and lvl.side == "high":
                pdh = lvl.price
            elif lvl.kind == "daily" and lvl.side == "low":
                pdl = lvl.price
        tag = (
            "NY" if sv.in_ny else "London" if sv.in_london else "Asia" if sv.in_asia else "between"
        )
        lo = max(0, k - LOOKBACK_5M)
        if pdl is not None and l[k] < pdl:
            if c[k] > pdl:
                out.append(
                    Signal(
                        k,
                        ts[k],
                        1,
                        pdl,
                        l[k],
                        last_pivot(h, k, +1),
                        h[lo : k + 1].max(),
                        atr[k],
                        tag,
                    )
                )
            pdl = None  # swept once, or broken — either way done for the day
        if pdh is not None and h[k] > pdh:
            if c[k] < pdh:
                out.append(
                    Signal(
                        k,
                        ts[k],
                        -1,
                        pdh,
                        h[k],
                        last_pivot(l, k, -1),
                        l[lo : k + 1].min(),
                        atr[k],
                        tag,
                    )
                )
            pdh = None
    return out


def last_pivot(x, k: int, sign: int) -> Optional[float]:
    """The most recent small 5m swing high (sign +1) or low (-1) — one bar either side — already
    CONFIRMED when bar k closes, within LOOKBACK_5M bars. On 2026-10-02 it is 4161.77."""
    for i in range(k - 1, max(1, k - LOOKBACK_5M) - 1, -1):
        v = x[i] * sign
        if v > x[i - 1] * sign and v >= x[i + 1] * sign:
            return x[i]
    return None


# ----------------------------------------------------------------------------- entries


class Minutes:
    def __init__(self, m1: pd.DataFrame):
        self.t = m1.index.to_numpy()
        self.o, self.h, self.l, self.c = (
            m1[x].to_numpy() for x in ("open", "high", "low", "close")
        )

    def span(self, t0: pd.Timestamp, minutes: int):
        a = int(np.searchsorted(self.t, np.datetime64(t0)))
        b = int(np.searchsorted(self.t, np.datetime64(t0 + pd.Timedelta(minutes=minutes))))
        return a, b


def entry_now(s: Signal, mn: Minutes, m5: pd.DataFrame):
    a, b = mn.span(s.t, 5)
    if b <= a:
        return None
    return b - 1, mn.c[b - 1], s.ext


def entry_push(s: Signal, mn: Minutes, m5: pd.DataFrame):
    if s.k + 1 >= len(m5) or m5.index[s.k + 1] - s.t != pd.Timedelta(minutes=5):
        return None  # the next bar is across a gap — not "the next candle"
    op = m5["open"].iat[s.k + 1]
    a, b = mn.span(m5.index[s.k + 1], 5)
    pushed = False
    ext = s.ext
    for j in range(a, b):
        ext = min(ext, mn.l[j]) if s.d == 1 else max(ext, mn.h[j])
        if not pushed:
            pushed = mn.l[j] < op if s.d == 1 else mn.h[j] > op
        if pushed and ((s.d == 1 and mn.c[j] > op) or (s.d == -1 and mn.c[j] < op)):
            return j, mn.c[j], ext
    return None


def entry_flip(s: Signal, mn: Minutes, m5: pd.DataFrame):
    a0, _ = mn.span(s.t - pd.Timedelta(minutes=FLIP_WARMUP_MIN), 0)
    a, b = mn.span(s.t, 5)
    _, end = mn.span(s.t + pd.Timedelta(minutes=5), FLIP_WINDOW_MIN)
    eng = StructureEngine()
    ext = s.ext
    for j in range(a0, end):
        ev = eng.update(Bar(j - a0, mn.o[j], mn.h[j], mn.l[j], mn.c[j]))
        if j < b:
            continue  # warm-up and the sweep bar itself
        ext = min(ext, mn.l[j]) if s.d == 1 else max(ext, mn.h[j])
        t = pd.Timestamp(mn.t[j])
        if t.minute % 5 == 4:  # a 5m close: back through the level kills the setup
            if (s.d == 1 and mn.c[j] < s.level) or (s.d == -1 and mn.c[j] > s.level):
                return None
        up = ev.external.bull_sos or ev.internal.bull_sos
        dn = ev.external.bear_sos or ev.internal.bear_sos
        if (s.d == 1 and up) or (s.d == -1 and dn):
            return j, mn.c[j], ext
    return None


ENTRIES = {"now": entry_now, "push": entry_push, "flip": entry_flip}


# ----------------------------------------------------------------------------- scoring


def walk(mn: Minutes, j: int, d: int, entry: float, stop: float, target: float, sp: float):
    """Walk from the minute after entry. Returns (exit_index, exit_price, how) or None if data ends.
    Bars are bid; a long exits on the bid, a short exits on the ask (bid + sp)."""
    t_end = next_rollover(pd.Timestamp(mn.t[j]))
    e = int(np.searchsorted(mn.t, np.datetime64(t_end)))
    if e >= len(mn.t):
        return None
    sl = slice(j + 1, e)
    if d == 1:
        s_hit = mn.l[sl] <= stop
        t_hit = mn.h[sl] >= target
    else:
        s_hit = mn.h[sl] + sp >= stop
        t_hit = mn.l[sl] + sp <= target
    si = int(np.argmax(s_hit)) if s_hit.any() else None
    ti = int(np.argmax(t_hit)) if t_hit.any() else None
    if si is not None and (ti is None or si <= ti):
        m = j + 1 + si
        op = mn.o[m] if d == 1 else mn.o[m] + sp
        px = min(op, stop) if d == 1 else max(op, stop)  # a gap through the stop fills at the open
        return m, px, "stop"
    if ti is not None:
        return j + 1 + ti, target, "target"
    return e, (mn.o[e] if d == 1 else mn.o[e] + sp), "time"


def price_trade(mn, j, raw, ext, d, top, atr, prof, sp):
    """One costed trade: entry, stop, target `top` and the walk. None when the data ends first."""
    entry = raw + sp if d == 1 else raw  # a buy pays the ask; a sell gets the bid
    stop = ext - STOP_BUF_ATR * atr if d == 1 else ext + sp + STOP_BUF_ATR * atr
    if (entry - stop) * d < MIN_STOP_ATR * atr:
        stop = entry - d * MIN_STOP_ATR * atr
    risk = (entry - stop) * d
    reward = (top - entry) * d
    if reward < MIN_REWARD_R * risk:
        return {"skip": "target under 1R"}
    w = walk(mn, j, d, entry, stop, top, sp)
    if w is None:
        return None
    m, px, how = w
    gross = (px - entry) * d / risk
    comm = 2 * prof.commission_per_side_per_lot / prof.contract_size
    ms = lambda i: int(pd.Timestamp(mn.t[i]).tz_localize("UTC").value // 10**6)  # noqa: E731
    swap = sum(
        prof.swap.charge(d, 1.0, day) / prof.contract_size
        for day in rollovers_between(ms(j), ms(m), 17)
    )
    return dict(
        j=j,
        entry=entry,
        stop=stop,
        target=top,
        risk=risk,
        exit=px,
        how=how,
        gross=gross,
        net=gross + (swap - comm) / risk,
        held_min=int((mn.t[m] - mn.t[j]) / np.timedelta64(1, "m")),
    )


def control(mn, m5, s, tr, prof, sp, pool_by_hour, rng):
    """Same hour, same half, same direction, same stop and target distances — random 5m closes."""
    key = (s.t < SPLIT, s.t.hour)
    pool = pool_by_hour.get(key, [])
    out = []
    for k in rng.sample(pool, min(CONTROL_K, len(pool))):
        a, b = mn.span(m5.index[k], 5)
        if b <= a:
            continue
        j = b - 1
        entry = mn.c[j] + sp if s.d == 1 else mn.c[j]
        stop = entry - s.d * tr["risk"]
        tgt = entry + (tr["target"] - tr["entry"])
        w = walk(mn, j, s.d, entry, stop, tgt, sp)
        if w is None:
            continue
        m, px, _ = w
        out.append(
            (px - entry) * s.d / tr["risk"]
            - 2 * prof.commission_per_side_per_lot / prof.contract_size / tr["risk"]
        )
    return float(np.mean(out)) if out else None


# ----------------------------------------------------------------------------- report


def stats(x):
    x = np.asarray(x, float)
    n = len(x)
    if n < 2:
        return n, float("nan"), float("nan")
    return n, x.mean(), x.std(ddof=1) / math.sqrt(n)


def p_better(m1, se1, m2, se2):
    se = math.sqrt(se1**2 + se2**2)
    return 0.5 * (1 + math.erf((m1 - m2) / se / math.sqrt(2))) if se > 0 else float("nan")


def row(label, trades, ctrl_of=None, base=None):
    n, m, se = stats([t["net"] for t in trades])
    if n < 2:
        return f"  {label:<26} n={n}"
    win = np.mean([t["how"] == "target" for t in trades]) * 100
    s = f"  {label:<26} n={n:>4}  win {win:4.1f}%  {m:+.3f}R ±{se:.3f}  ({m / se:+.1f}σ)"
    if ctrl_of:
        cv = [ctrl_of[id(t)] for t in trades if ctrl_of.get(id(t)) is not None]
        if cv:
            s += f"  ctrl {np.mean(cv):+.3f}  edge {m - np.mean(cv):+.3f}"
    if base is not None:
        bn, bm, bse = stats([t["net"] for t in base])
        s += f"  vs rest {m - bm:+.3f}  P(better) {p_better(m, se, bm, bse) * 100:.0f}%"
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-09-30")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    prof = PROFILES[PROFILE]
    sp = prof.spread_or_refuse()
    m1, m5 = load(args.start, args.end)
    mn = Minutes(m1)
    sigs = find_signals(m5)
    print(f"{len(m5):,} 5m bars, {len(sigs)} sweep-and-reclaim signals of the previous day's level")

    rng = random.Random(args.seed)
    pool: Dict[tuple, List[int]] = {}
    for k, t in enumerate(m5.index):
        pool.setdefault((t < SPLIT, t.hour), []).append(k)

    ctrl_of: Dict[int, Optional[float]] = {}
    skipped = {m: 0 for m in MODELS}
    for s in sigs:
        for ename in ENTRY_MODELS:
            e = ENTRIES[ename](s, mn, m5)
            if e is None:
                continue
            j, raw, ext = e
            for xname in EXITS:
                mname = f"{ename}/{xname}"
                target = s.near if xname == "near" else s.far
                if target is None:
                    skipped[mname] += 1
                    continue
                tr = price_trade(mn, j, raw, ext, s.d, target, s.atr, prof, sp)
                if tr is None:
                    continue
                if "skip" in tr:
                    skipped[mname] += 1
                    continue
                tr.update(sig=s, model=mname)
                s.trades[mname] = tr
                ctrl_of[id(tr)] = control(mn, m5, s, tr, prof, sp, pool, rng)

    print(f"skipped for a target under 1R: {skipped}\n")
    for half, keep in (
        ("ALL", lambda s: True),
        ("DISCOVERY 2020-01 → 2023-04", lambda s: s.t < SPLIT),
        ("CONFIRMATION 2023-05 → 2026-09", lambda s: s.t >= SPLIT),
    ):
        print(f"=== {half}")
        for mname in MODELS:
            book = [s.trades[mname] for s in sigs if keep(s) and mname in s.trades]
            print(row(f"{mname}: every session", book, ctrl_of))
            for sess in SESSIONS:
                sub = [t for t in book if t["sig"].session == sess]
                rest = [t for t in book if t["sig"].session != sess]
                print(row(f"{mname}: {sess}", sub, ctrl_of, rest))
            for d, nm in ((1, "longs"), (-1, "shorts")):
                print(row(f"{mname}: {nm}", [t for t in book if t["sig"].d == d], ctrl_of))
        # push vs now on the SAME signals — does waiting for the push add anything?
        for xname in EXITS:
            for alt in ("push", "flip"):
                a_, b_ = f"{alt}/{xname}", f"now/{xname}"
                both = [s for s in sigs if keep(s) and a_ in s.trades and b_ in s.trades]
                n, m, se = stats([s.trades[a_]["net"] - s.trades[b_]["net"] for s in both])
                if n > 1:
                    print(
                        f"  {alt} minus now ({xname}), same signals  n={n}  {m:+.3f}R ±{se:.3f}  "
                        f"P({alt} better) {0.5 * (1 + math.erf(m / se / math.sqrt(2))) * 100:.0f}%"
                    )
        print()

    if args.csv:
        rows = []
        for s in sigs:
            for mname, t in s.trades.items():
                rows.append(
                    dict(
                        model=mname,
                        sweep=s.t,
                        dir=s.d,
                        session=s.session,
                        level=s.level,
                        entry_time=pd.Timestamp(mn.t[t["j"]]),
                        entry=t["entry"],
                        stop=t["stop"],
                        target=t["target"],
                        exit=t["exit"],
                        how=t["how"],
                        held_min=t["held_min"],
                        gross_r=t["gross"],
                        net_r=t["net"],
                        ctrl_r=ctrl_of.get(id(t)),
                    )
                )
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(args.csv, index=False)
        print(f"wrote {len(rows)} trades to {args.csv}")


if __name__ == "__main__":
    main()
