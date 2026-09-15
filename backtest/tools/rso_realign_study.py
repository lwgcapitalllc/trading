#!/usr/bin/env python3
"""rso_realign_study.py — the user's RSO realign sequence, graded on how to enter, stop and exit.

The user's own rule (2026-09-14, five 1-minute XAUUSD charts). SHORT; a long is the exact mirror:

    trend     a bearish external BOS — the market is trending down
    counter   a bullish external SOS — the counter shift; retail buys the turn
    push      one or more bullish external BOS after it — the counter push; retail adds
    realign   a bearish external SOS — structure turns back with the trend. THE TRADE.
    stop      beyond the counter push's highest point: the chart price must trade one spread
              through it

Structure is the canonical `engines/market_structure/` external stream on the CHART frame (1m, 5m
or 15m, the higher two resampled from the same 1m bars). Every trade is walked on the raw
1-minute bars whatever the chart frame, so a 15m trade is resolved minute by minute.

THE GRID, declared in the spec before any result (memory: rso-realign-study-spec), per frame:

    counter BOS  1 | 2+
    entry        close  - market at the realign SOS close
                 fib50  - a limit at the 0.5 of the realign leg (counter top -> running low),
                          re-priced at each chart close, the way the JARVIS fib extends
                 pb382  - once price pulls back to the 0.382, market on the first candle of the
                          next frame up (5m on a 1m chart, 15m on 5m, 1H on 15m) closing back down
                 split  - half at the close, half at the fib50 limit; each half risks 0.5R
    stop         struct - the counter push's extreme, one spread through it
                 atr2   - 2 x ATR(14) of the chart frame, from the fill
    exit         t1 t1.5 t2 t3 - a fixed target at that many R
                 tS    - the low the counter push launched from (the engine's own leg origin)
                 t2be  - 2R target; stop to breakeven from the minute after +1R
                 half  - half off at +1R, stop to breakeven, the rest trails 1R behind the best price
                 swing - stop to breakeven after +1R, then beyond each new with-trend BOS swing

Shared rules: one position at a time across BOTH sides, and a pending entry holds the slot; a
pending entry dies after 60 chart bars or on a chart close through the counter top; a trade still
open after 500 chart bars closes at market; every step is in R, never % of price (the B-LEG trail
was inert for weeks on a % step bigger than its whole risk); a stop move takes effect on the next
minute; a minute that touches both sides is the WORSE outcome; a limit filled inside a minute can
be stopped on that minute but can reach nothing favourable on it.

THE PICK RULE (loaded_level_study.py's, fixed before results): >= 30 trades, net R positive in
BOTH halves (split 2023-05-01), more than half of the one-step neighbours net positive, and z >= 2
against random entries matched on side, calendar month, New York hour, stop distance and exit rule.
Rank by the worse half's average R. The pick then gets ONE run on 2018-09-14 -> 2019-12-31
(`--holdout "<label>"`), which is spent the moment it is read.

🔴 MEASURED 2026-09-14 — NO MECHANICAL EDGE, AND THE HOLDOUT IS SPENT.

RECALL (`--recall`): on PU Prime 1m bars the rule finds 4 of the user's 5 trades 0-10 minutes from
their entry, the realign close within $1.32 of their entry and the counter extreme within $0.95 of
their stop. Image 4 is NOT a 1m realign — 1m structure had turned bullish at 10:07 and the entry sits
in a run of bullish BOS — and the user's own image-4 trade is STOPPED on these bars by 5 cents.

THE GRID, 2,371,706 M1 bars 2020-01-01 -> 2026-09-11, `puprime_ecn`, 128 cells a frame:
    1m   the user's rule as drawn (close entry, structure stop) loses in all 16 counter x exit rows,
         -0.002 to -0.082 R a trade over ~1,500-2,500 trades. Best 1m cell anywhere: t +0.82.
         4 of 128 positive in both halves.
    5m   best t +0.81; 3 of 128 positive in both halves.
    15m  46 of 128 positive in both halves. The rule as drawn with 1 counter BOS makes +0.04 to
         +0.13 R a trade — and random entries at the same month and hour make about the same
         (z 0.2-0.7): that is gold's drift, not the pattern. With 2+ counter BOS, -0.10 to +0.06.
16 cells qualified, every one 15m with 2+ counter BOS. THE PICK, 15m c2+ fib50 atr2 t3: 122 trades,
+61.9R, +0.507 a trade, 37.7% win, PF 1.80, halves +0.293 / +0.751, control -0.094, z +3.31. Audit
clean — no overlapping positions, no wrong-side stop, no fill outside its minute, every target
exactly 3R; still +0.461 a trade when a limit must trade $0.50 THROUGH its level. ⚠ But a RIDGE:
drop any one of 2+ counter BOS, the fib50 entry or the atr2 stop and it goes flat or negative
(c1: +3.1R; structure stop: +5.1R; market entry: -6.8R).
THE HOLDOUT, ONE RUN, 2018-09-14 -> 2019-12-31: 14 trades, -5.5R, -0.393 a trade, 14.3% win,
control -0.128, z -0.65. The pick is abandoned. ⚠ Fourteen trades cannot prove a pattern dead
either — but the rule was fixed before the run, and a failed pre-declared check is not re-run.
🔴 Never test another cell of this pattern on 2018-09-14 -> 2019-12-31, and never treat 2020-2026
as fresh: both have been looked at. A revived rule needs NEW data — the user's forward journal, or
their losers and skipped setups. The tool finds their 1m trades to the minute, so what is missing
is their discretion, not the definition. Full record: `docs/RSO_REALIGN_SPEC.md`.

⚠ The control for a `split` cell uses its first leg's geometry at full size — a single market
entry — because a random bar has no realign leg to rest a limit on.

THE $$ ENTRY (`--sl`, added 2026-09-14 AFTER the results above — exploration, NOT the declared
grid). The user: structural liquidity is the band between two lower highs (for a short), and it is
an ENTRY AREA or a TARGET, never a filter. The target half is `tS`, already in the grid. The entry
half: after the realign, a limit at the counter push's high (the band's lower edge), stop beyond
the lower high before it (`lh`) or 2 x ATR. Gold 2020-2026 has been searched for this pattern, so
a result here is a lead only — confirmed on data nothing has looked at (EURUSD, or forward), and
NEVER on `--holdout`, which is spent.
🔴 MEASURED 2026-09-14, same bars and costs, 96 cells: 0 QUALIFY. On image 1 it reproduces the
user's line (older lower high 4311.75; price back at the counter high 08:16 NY); on images 2, 3 and
5 price never came back. 1m: 182-245 trades a cell, the user's version (stop past the older lower
high) loses in all 16 counter x exit rows, best -0.003 R a trade, best cell t +0.35. 5m: 33-35
trades, best t +0.81. 15m: 14 trades a cell, under the 30-trade floor. The declared grid above
reproduces exactly after this mode was added.

Usage:
  python backtest/tools/rso_realign_study.py --recall          # find the user's 5 trades first
  python backtest/tools/rso_realign_study.py                   # the grid, 2020-01 -> 2026-09
  python backtest/tools/rso_realign_study.py --sl              # the $$ entry, exploration only
  python backtest/tools/rso_realign_study.py --holdout "1m c1 close struct t2"   # ONCE
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "engines", ROOT / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from fibonacci.geometry import fib_level  # noqa: E402
from loaded_level_study import NY, POINT, clean_reopens, mirror, rollovers, wilder_atr  # noqa: E402
from market_structure import Bar, StructureEngine  # noqa: E402

from backtest.data.resample import resample_up  # noqa: E402
from backtest.fills import PROFILES  # noqa: E402

CACHE = ROOT / "backtest" / "cache" / "PUPrime_Demo" / "XAUUSD_p__M1.csv"
BUILD = ("2020-01-01", "2026-09-12")
SPLIT = np.datetime64("2023-05-01")
HOLDOUT = ("2018-09-14", "2020-01-01")
WARMUP = 1000  # chart bars before any setup counts
PENDING = 60  # chart bars a pullback entry may wait
MAX_HOLD = 500  # chart bars, then out at market
REPS = 20  # random entries per real trade
SEED = 7
UP = {1: 5, 5: 15, 15: 60}
FRAMES = (1, 5, 15)
COUNTERS = ("1", "2+")
ENTRIES = ("close", "fib50", "pb382", "split")
STOPS = ("struct", "atr2")
EXITS = ("t1", "t1.5", "t2", "t3", "tS", "t2be", "half", "swing")
FIXED_R = {"t1": 1.0, "t1.5": 1.5, "t2": 2.0, "t3": 3.0}
# How far price must trade THROUGH a resting limit before it counts as filled. 0.0 = a touch fills,
# the optimistic reading a bar walk always makes (a touch says nothing about queue position). A
# probe, never a grid axis: raising it must not turn a limit-entry result negative.
LIMIT_THROUGH = 0.0

# The user's five trades, off their 1-minute TradingView charts (New York time — the chart reads
# UTC-4). TIMES ARE READ OFF PIXELS, +-5 minutes; PRICES are the chart's own labels. Images 4 and 5
# were labelled September by the user; PU Prime's daily ranges put them in August (2026-09-14).
EXAMPLES = [
    ("img1 14 Sep short", "2026-09-14 07:51", "short", 4290.13, 4297.84, 4277.68),
    ("img2 10 Sep pm short", "2026-09-10 21:22", "short", 4327.97, 4340.54, 4301.83),
    ("img3 10 Sep am short", "2026-09-10 06:31", "short", 4389.91, 4400.33, 4375.34),
    ("img4 25 Aug long", "2026-08-25 11:30", "long", 4651.33, 4634.28, 4673.62),
    ("img5 11 Aug long", "2026-08-11 20:55", "long", 4386.05, 4360.03, 4417.05),
]


# ─────────────────────────────── bars ───────────────────────────────


def load_1m(start: str, end: str) -> pd.DataFrame:
    if not CACHE.exists():
        sys.exit(f"no cached 1-minute bars at {CACHE}")
    df = pd.read_csv(CACHE, usecols=["time", "open", "high", "low", "close"], parse_dates=["time"])
    df = df[(df["time"] >= start) & (df["time"] < end)].set_index("time")
    return df.astype(float)


class Tape:
    """Raw 1-minute bars in ONE side's price space. Shorts trade the real bars; longs trade the
    MIRRORED bars through the identical short code — never a hand-written bullish branch. Bars are
    bid: a short sells the bid and buys back the ask, so its exits test `bid + spread`; a mirrored
    long pays the spread on its ENTRY instead (loaded_level_study.Book's convention)."""

    def __init__(self, raw: pd.DataFrame, side: str, spread: float) -> None:
        self.side = side
        self.O, self.H, self.L, self.C = (
            raw[k].to_numpy() for k in ("open", "high", "low", "close")
        )
        self.en = spread if side == "long" else 0.0
        self.ex = spread if side == "short" else 0.0
        self.spread = spread
        self.n = len(self.C)


@dataclass
class Setup:
    side: str
    frame: int
    j: int  # chart bar the realign SOS closed on
    m: int  # ...its last minute
    counter: int  # chart bar of the counter SOS
    origin: float  # the low the counter push launched from (engine leg origin), side space
    trend_n: int
    push_n: int
    top: float  # the counter push's highest point, raw, side space
    top_k: int  # ...and its minute
    atr: float
    lh_old: float = math.nan  # the lower high before the one the counter shift broke, side space


@dataclass
class Frame:
    minutes: int
    side: str
    first: np.ndarray  # first minute of each chart bar
    last: np.ndarray  # last minute of each chart bar
    lo: np.ndarray  # each chart bar's raw low, side space
    up_last: np.ndarray  # next frame up: each candle's last minute
    up_bear: np.ndarray  # ...and whether it closed down, side space
    setups: list
    ev_eff: np.ndarray  # with-trend BOS: the first minute its swing is known on
    ev_lvl: np.ndarray  # ...and that swing, one spread through, as a stop level
    n: int


# ─────────────────────────────── detection ───────────────────────────────


def detect(o, h, lo, c) -> tuple[list, list]:
    """Replay the canonical engine over one side's chart bars and read the user's sequence off its
    external stream. Fed contiguously — it is a streaming state machine, so a filtered frame would
    corrupt structure rather than fail. SOS is tested before BOS: the engine may raise both on a
    shift bar, and a shift bar is a shift."""
    eng = StructureEngine()
    setups, bos = [], []
    state, trend_n, push_n, counter, origin, trend_at = "none", 0, 0, -1, math.nan, 0
    lhs: list = []  # the lower highs of the current bear run, oldest first
    lh_old = math.nan
    for i in range(len(c)):
        ext = eng.update(Bar(index=i, open=o[i], high=h[i], low=lo[i], close=c[i])).external
        if ext.bear_sos:
            if state == "push":
                setups.append((i, counter, origin, trend_at, push_n, lh_old))
            state, trend_n = "trend", 0
            lhs = [float(ext.bear_bos_high)] if ext.bear_bos_high is not None else []
        elif ext.bear_bos:
            # A bear BOS only fires while structure is already bearish (or on the very first break).
            state, trend_n = "trend", trend_n + 1
            if ext.bear_bos_high is not None:
                bos.append((i, float(ext.bear_bos_high)))
                lhs.append(float(ext.bear_bos_high))
        elif ext.bull_sos:
            if state == "trend" and trend_n >= 1 and ext.bull_bos_low is not None:
                # The counter shift breaks the LAST lower high by definition. The $$ band's upper
                # edge is the lower high BEFORE it — the most recent one above the broken level.
                brk = ext.bull_bos_price
                lh_old = next(
                    (x for x in reversed(lhs) if brk is not None and x > brk + 1e-9), math.nan
                )
                state, counter, origin, trend_at, push_n = (
                    "counter",
                    i,
                    float(ext.bull_bos_low),
                    trend_n,
                    0,
                )
            else:
                state = "void"  # a bull run with no qualifying trend before it
        elif ext.bull_bos and state in ("counter", "push"):
            state, push_n = "push", push_n + 1
    return setups, bos


def _detect_task(job):
    key, o, h, lo, c = job
    return key, detect(o, h, lo, c)


def build(raw: pd.DataFrame, clean: pd.DataFrame, frames, spread: float, workers: int):
    """One Frame per (chart minutes, side). Structure reads the reopen-cleaned bars; every PRICE a
    trade uses comes from the raw bars — the broker fills on what it printed."""
    t1m = raw.index.to_numpy()
    tapes = {"short": Tape(raw, "short", spread), "long": Tape(mirror(raw), "long", spread)}
    jobs, meta = [], {}
    for F in frames:
        ch = resample_up(clean, F, 1)
        tf = ch.index.to_numpy()
        first = np.searchsorted(t1m, tf, "left")
        last = np.searchsorted(t1m, tf + np.timedelta64(F, "m"), "left") - 1
        ut = resample_up(clean, UP[F], 1).index.to_numpy()
        u_first = np.searchsorted(t1m, ut, "left")
        u_last = np.searchsorted(t1m, ut + np.timedelta64(UP[F], "m"), "left") - 1
        for side in ("short", "long"):
            cs = ch if side == "short" else mirror(ch)
            o, h, lo, c = (cs[k].to_numpy() for k in ("open", "high", "low", "close"))
            meta[(F, side)] = (first, last, wilder_atr(h, lo, c, 14), u_first, u_last, len(c))
            jobs.append(((F, side), o, h, lo, c))
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        found = dict(pool.map(_detect_task, jobs))
    print(f"structure replayed on {len(jobs)} streams in {time.time() - t0:.0f}s")
    frs = {}
    for (F, side), (first, last, atr, u_first, u_last, n) in meta.items():
        tp = tapes[side]
        raw_setups, bos = found[(F, side)]
        setups = []
        for j, counter, origin, trend_at, push_n, lh_old in raw_setups:
            if j < WARMUP:
                continue
            m, a = int(last[j]), int(first[counter])
            k = a + int(np.argmax(tp.H[a : m + 1]))
            setups.append(
                Setup(
                    side,
                    F,
                    j,
                    m,
                    counter,
                    origin,
                    trend_at,
                    push_n,
                    float(tp.H[k]),
                    k,
                    float(atr[j]),
                    lh_old,
                )
            )
        frs[(F, side)] = Frame(
            F, side, first, last, np.minimum.reduceat(tp.L, first), u_last,
            tp.C[u_last] < tp.O[u_first], setups,
            np.array([last[b] + 1 for b, _ in bos], dtype=np.int64),
            np.array([lv + spread + tp.ex for _, lv in bos]), n,
        )  # fmt: skip
    return tapes, frs


# ─────────────────────────────── entries ───────────────────────────────


def fill_sl(fr: Frame, tp: Tape, s: Setup):
    """The user's $$ entry (added 2026-09-14, AFTER the declared grid): structural liquidity is the
    band between two lower highs, so after the realign a limit rests at its lower edge — the counter
    push's high — until price returns to it. No band (the counter push went above the older lower
    high) is no trade. Dies after PENDING chart bars or on a chart close above the older lower high."""
    jend = min(s.j + PENDING, fr.n - 1)
    if jend <= s.j or not s.lh_old > s.top:
        return None, math.nan, False, s.m
    js = np.arange(s.j + 1, jend + 1)
    dead = np.flatnonzero(tp.C[fr.last[js]] > s.lh_old)
    jstop = int(js[dead[0]]) if len(dead) else jend
    a, b = int(fr.first[s.j + 1]), int(fr.last[jstop])
    hit = np.flatnonzero(tp.H[a : b + 1] >= s.top + tp.en + LIMIT_THROUGH)
    if not len(hit):
        return None, math.nan, False, b
    return a + int(hit[0]), s.top, True, b


def fill(fr: Frame, tp: Tape, s: Setup, how: str):
    """-> (fill minute or None, price, filled INSIDE the minute, minute the slot frees if unfilled)"""
    if how == "close":
        return s.m, tp.C[s.m] - tp.en, False, s.m
    if how == "sl":
        return fill_sl(fr, tp, s)
    jend = min(s.j + PENDING, fr.n - 1)
    if jend <= s.j:
        return None, math.nan, False, s.m
    js = np.arange(s.j + 1, jend + 1)
    dead = np.flatnonzero(tp.C[fr.last[js]] > s.top)  # a close through the counter top kills it
    jstop = int(js[dead[0]]) if len(dead) else jend
    # The realign leg runs from the counter top to the running low, fixed at each chart close:
    # the level resting during bar jj is the one set at the close of jj-1.
    rl0 = float(tp.L[s.top_k : s.m + 1].min())
    runlow = np.minimum.accumulate(np.concatenate(([rl0], fr.lo[s.j + 1 : jstop])))
    lvl = fib_level(s.top, runlow, -1, 0.5 if how == "fib50" else 0.382)
    a, b = int(fr.first[s.j + 1]), int(fr.last[jstop])
    lv1 = np.repeat(lvl, fr.last[s.j + 1 : jstop + 1] - fr.first[s.j + 1 : jstop + 1] + 1)
    if how == "fib50":
        hit = np.flatnonzero(tp.H[a : b + 1] >= lv1 + tp.en + LIMIT_THROUGH)
        if not len(hit):
            return None, math.nan, False, b
        return a + int(hit[0]), float(lv1[hit[0]]), True, b
    hit = np.flatnonzero(tp.H[a : b + 1] >= lv1)  # pb382: the pullback touch (a price event)
    if not len(hit):
        return None, math.nan, False, b
    touch = a + int(hit[0])
    # A candle closing on the dying bar's own close would be entering through the top.
    limit_k = b - 1 if len(dead) else b
    ci = int(np.searchsorted(fr.up_last, touch, "left"))
    cj = int(np.searchsorted(fr.up_last, limit_k, "right"))
    bears = np.flatnonzero(fr.up_bear[ci:cj])
    if not len(bears):
        return None, math.nan, False, b
    k = int(fr.up_last[ci + bears[0]])
    return k, tp.C[k] - tp.en, False, b


# ─────────────────────────────── the walk ───────────────────────────────


def end_for(fr: Frame, k: int) -> int:
    jk = int(np.searchsorted(fr.last, k, "left"))
    return int(fr.last[min(jk + MAX_HOLD, fr.n - 1)])


def walk(
    tp: Tape, k0: int, inside: bool, e: float, S0: float, end: int, kind: str, T=math.nan, ev=None
):
    """Resolve a SHORT in this side's space from minute k0 through `end`.
    Returns (exit minute, gross R, outcome, partial minute or -1)."""
    R0 = S0 - e
    ex = tp.ex
    if end < k0:
        return k0, (e - (tp.C[min(k0, tp.n - 1)] + ex)) / R0, "time", -1
    H = tp.H[k0 : end + 1] + ex  # the ask a short buys back at
    L = tp.L[k0 : end + 1] + ex
    O = tp.O[k0 : end + 1] + ex
    last = len(H) - 1
    fav = 1 if inside else 0

    def first(mask, frm):
        if frm > last:
            return None
        idx = np.flatnonzero(mask[frm:])
        return frm + int(idx[0]) if len(idx) else None

    def stop_px(j, lvl):  # a minute that OPENS through the stop fills at its open
        return float(O[j]) if (j > 0 or not inside) and O[j] > lvl else lvl

    def tgt_px(j):  # a minute that opens through the target fills there, better
        return min(T, float(O[j])) if (j > 0 or not inside) else T

    def at_time(part=-1):
        return end, (e - (tp.C[end] + ex)) / R0, "time", part

    js = first(H >= S0, 0)
    if kind == "fixed":
        jt = first(L <= T, fav)
        if js is not None and (jt is None or js <= jt):
            return k0 + js, (e - stop_px(js, S0)) / R0, "stop", -1
        if jt is not None:
            return k0 + jt, (e - tgt_px(jt)) / R0, "target", -1
        return at_time()

    ja = first(L <= e - R0, fav)  # +1R reached
    if js is not None and (ja is None or js <= ja):
        return k0 + js, (e - stop_px(js, S0)) / R0, "stop", -1
    if ja is None:
        return at_time()

    if kind == "be":
        jt = first(L <= T, ja)
        jb = first(H >= e, ja + 1)
        if jt is not None and (jb is None or jt < jb):
            return k0 + jt, (e - tgt_px(jt)) / R0, "target", -1
        if jb is not None:
            return k0 + jb, (e - stop_px(jb, e)) / R0, "breakeven", -1
        return at_time()

    if kind == "half":
        lv = np.minimum.accumulate(L[ja:])[:-1] + R0  # the trail on minutes ja+1 .. last
        hit = np.flatnonzero(H[ja + 1 :] >= lv)
        if len(hit):
            j = ja + 1 + int(hit[0])
            return k0 + j, 0.5 + 0.5 * (e - stop_px(j, float(lv[hit[0]]))) / R0, "trail", k0 + ja
        return end, 0.5 + 0.5 * (e - (tp.C[end] + ex)) / R0, "time", k0 + ja

    # swing: breakeven, then beyond each new with-trend BOS swing — never loosened
    ev_eff, ev_lvl = ev
    lv = np.full(last - ja, e)
    for q in range(
        int(np.searchsorted(ev_eff, k0 + ja + 1, "left")),
        int(np.searchsorted(ev_eff, end, "right")),
    ):
        pos = int(ev_eff[q]) - (k0 + ja + 1)
        lv[pos] = min(lv[pos], ev_lvl[q])
    lv = np.minimum.accumulate(lv)
    hit = np.flatnonzero(H[ja + 1 :] >= lv)
    if len(hit):
        j = ja + 1 + int(hit[0])
        return k0 + j, (e - stop_px(j, float(lv[hit[0]]))) / R0, "trail", -1
    return at_time()


def exit_rule(exit_: str, e: float, R0: float, origin: float):
    """-> (walk kind, target price) or None when the target sits at or behind the entry."""
    if exit_ in FIXED_R:
        return "fixed", e - FIXED_R[exit_] * R0
    if exit_ == "tS":
        return ("fixed", origin) if origin < e else None
    if exit_ == "t2be":
        return "be", e - 2.0 * R0
    return exit_, math.nan  # "half" | "swing"


def nights(costs: dict, k1: int, k2: int) -> float:
    t, roll, cum = costs["t"], costs["roll"], costs["cum"]
    return cum[np.searchsorted(roll, t[k2], "right")] - cum[np.searchsorted(roll, t[k1], "right")]


def net_r(rg: float, R0: float, kf: int, kx: int, kp: int, side: str, costs: dict) -> float:
    sw = costs["swap_short"] if side == "short" else costs["swap_long"]
    n = (
        0.5 * nights(costs, kf, kp) + 0.5 * nights(costs, kf, kx)
        if kp >= 0
        else nights(costs, kf, kx)
    )
    return rg - costs["comm_rt"] / (R0 * costs["contract"]) + n * sw * POINT / R0


def trade(
    fr: Frame,
    tp: Tape,
    s: Setup,
    kf: int,
    e: float,
    inside: bool,
    stop: str,
    exit_: str,
    costs: dict,
):
    if stop == "struct":
        S0 = s.top + tp.spread + tp.ex
    elif stop == "lh":  # beyond the older lower high — the $$ band's upper edge
        S0 = s.lh_old + tp.spread + tp.ex
    else:
        S0 = e + 2.0 * s.atr
    R0 = S0 - e
    if not R0 > 0:
        return None
    rule = exit_rule(exit_, e, R0, s.origin)
    if rule is None:
        return None
    kind, T = rule
    xk, rg, outcome, kp = walk(
        tp,
        kf if inside else kf + 1,
        inside,
        e,
        S0,
        end_for(fr, kf),
        kind,
        T,
        (fr.ev_eff, fr.ev_lvl),
    )
    return dict(
        side=s.side, kf=kf, kx=xk, e=e, R0=R0, rg=rg, r=net_r(rg, R0, kf, xk, kp, s.side, costs),
        outcome=outcome, kind=kind, tdist=(e - T) if kind in ("fixed", "be") else math.nan, push_n=s.push_n,
    )  # fmt: skip


def evaluate(
    frs: dict,
    tapes: dict,
    F: int,
    costs: dict,
    cells=None,
    hows=("close", "fib50", "pb382"),
    stops=STOPS,
) -> dict:
    """Every setup through every (entry, stop, exit) on frame F. -> {(entry, stop, exit): rows},
    rows = [(realign minute, minute the slot frees, trade or None, counter BOS count)] by time.
    The `split` entry is built only when both of its legs are in `hows`."""
    want = cells
    rows: dict = {}
    for side in ("short", "long"):
        fr, tp = frs[(F, side)], tapes[side]
        for s in fr.setups:
            fills = {h: fill(fr, tp, s, h) for h in hows}
            for st in stops:
                for ex in EXITS:
                    if want is not None and not any(c[3] == st and c[4] == ex for c in want):
                        continue
                    legs = {}
                    for how, (kf, e, inside, pend) in fills.items():
                        tr = (
                            trade(fr, tp, s, kf, e, inside, st, ex, costs)
                            if kf is not None
                            else None
                        )
                        busy = (
                            tr["kx"]
                            if tr
                            else (s.m if how == "close" else (kf if kf is not None else pend))
                        )
                        legs[how] = (tr, busy)
                        rows.setdefault((how, st, ex), []).append((s.m, busy, tr, s.push_n))
                    if "close" not in legs or "fib50" not in legs:
                        continue
                    (t1, b1), (t2, b2) = legs["close"], legs["fib50"]
                    sp = None
                    if t1 is not None:
                        sp = dict(t1)
                        sp["r"] = 0.5 * t1["r"] + (0.5 * t2["r"] if t2 else 0.0)
                        sp["rg"] = 0.5 * t1["rg"] + (0.5 * t2["rg"] if t2 else 0.0)
                        sp["kx"] = max(t1["kx"], t2["kx"] if t2 else -1)
                    rows.setdefault(("split", st, ex), []).append(
                        (s.m, max(b1, b2) if t1 else s.m, sp, s.push_n)
                    )
    for v in rows.values():
        v.sort(key=lambda r: r[0])
    return rows


def book(rows: list, counter: str) -> list:
    """One position at a time across both sides; a pending entry holds the slot."""
    out, free = [], -1
    for m, busy, tr, push_n in rows:
        if (push_n == 1) != (counter == "1") or m <= free:
            continue
        free = busy
        if tr is not None:
            out.append(tr)
    return out


# ─────────────────────────────── scoring ───────────────────────────────


def stats(trades: list, t1m: np.ndarray, months: float) -> dict:
    if not trades:
        return dict(n=0, pm=0.0, win=0.0, avg=0.0, tot=0.0, pf=0.0, dd=0.0, h1=0.0, h2=0.0, a1=math.nan,
                    a2=math.nan, worse=-math.inf, t=0.0, risk=math.nan)  # fmt: skip
    r = np.array([t["r"] for t in trades])
    early = np.array([t1m[t["kf"]] < SPLIT for t in trades])
    eq = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(np.concatenate(([0.0], eq)))[1:] - eq))
    gp, gl = r[r > 0].sum(), -r[r < 0].sum()
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    a1 = r[early].mean() if early.any() else math.nan
    a2 = r[~early].mean() if (~early).any() else math.nan
    return dict(
        n=len(r), pm=len(r) / months, win=float((r > 0).mean() * 100), avg=float(r.mean()), tot=float(r.sum()),
        pf=float(gp / gl) if gl else math.inf, dd=dd, h1=float(r[early].sum()), h2=float(r[~early].sum()),
        a1=a1, a2=a2, worse=min(a1, a2) if early.any() and (~early).any() else -math.inf,
        t=float(r.mean() / (sd / math.sqrt(len(r)))) if sd else 0.0,
        risk=float(np.median([t["R0"] for t in trades])),
    )  # fmt: skip


def pools_of(index: pd.DatetimeIndex) -> dict:
    """Minutes grouped by (calendar month, New York hour) — the control's matching buckets."""
    ny = index.tz_localize("UTC").tz_convert(NY)
    key = ((ny.year * 12 + ny.month) * 24 + ny.hour).to_numpy()
    ok = np.arange(len(key))
    ok = ok[(ok >= 1000) & (ok < len(key) - 2)]
    order = ok[np.argsort(key[ok], kind="stable")]
    ks, starts = np.unique(key[order], return_index=True)
    return dict(key=key, pools=dict(zip(ks.tolist(), np.split(order, starts[1:]))))


def control(trades: list, frs: dict, F: int, tapes: dict, pools: dict, costs: dict, rng) -> dict:
    """Random market entries matched on side, calendar month, NY hour, stop distance and exit rule
    (same R target, or the same $ distance to a structural target). Only the timing is random."""
    rs = []
    for t in trades:
        tp, fr = tapes[t["side"]], frs[(F, t["side"])]
        pool = pools["pools"][int(pools["key"][t["kf"]])]
        for k in rng.choice(pool, size=REPS):
            k = int(k)
            e = tp.C[k] - tp.en
            S0 = e + t["R0"]
            T = e - t["tdist"] if t["kind"] in ("fixed", "be") else math.nan
            xk, rg, _, kp = walk(
                tp, k + 1, False, e, S0, end_for(fr, k), t["kind"], T, (fr.ev_eff, fr.ev_lvl)
            )
            rs.append(net_r(rg, t["R0"], k, xk, kp, t["side"], costs))
    rs = np.array(rs)
    return dict(avg=float(rs.mean()), sd=float(rs.std(ddof=1)), n=len(rs))


def zscore(trades: list, ctl: dict) -> float:
    r = np.array([t["r"] for t in trades])
    se = math.sqrt(r.var(ddof=1) / len(r) + ctl["sd"] ** 2 / ctl["n"])
    return (r.mean() - ctl["avg"]) / se if se else 0.0


def label(c: tuple) -> str:
    return f"{c[0]}m c{c[1]} {c[2]} {c[3]} {c[4]}"


def parse(lbl: str) -> tuple:
    f, c, en, st, ex = lbl.split()
    cell = (int(f.rstrip("m")), c.lstrip("c"), en, st, ex)
    if (
        cell[0] not in FRAMES
        or cell[1] not in COUNTERS
        or en not in ENTRIES
        or st not in STOPS
        or ex not in EXITS
    ):
        sys.exit(f"not a cell of the declared grid: {lbl!r}")
    return cell


HEAD = f"{'':<30} {'n':>5} {'/mo':>5} {'win':>6} {'avg R':>7} {'tot R':>8} {'PF':>5} {'maxDD':>6} {'1st½':>7} {'2nd½':>7} {'t':>5} {'risk$':>6}"


def row(lbl: str, st: dict, extra: str = "") -> str:
    return (
        f"{lbl:<30} {st['n']:>5} {st['pm']:>5.1f} {st['win']:>5.1f}% {st['avg']:>+7.3f} {st['tot']:>+8.1f} "
        f"{st['pf']:>5.2f} {st['dd']:>6.1f} {st['a1']:>+7.3f} {st['a2']:>+7.3f} {st['t']:>+5.2f} {st['risk']:>6.2f}{extra}"
    )


# ─────────────────────────────── recall ───────────────────────────────


def recall(raw: pd.DataFrame, tapes: dict, frs: dict, frames) -> None:
    """Does the rule, on PU Prime's bars, find the user's five trades — on which chart frame? And
    what did the user's OWN entry, stop and target do on these bars?"""
    idx = raw.index
    print("\nRECALL — every same-side realign within 30 minutes of each of the user's entries")
    for name, when, side, u_e, u_s, u_t in EXAMPLES:
        t = pd.Timestamp(when, tz=NY).tz_convert("UTC").tz_localize(None)
        tp, sg = tapes[side], (1 if side == "short" else -1)
        print(f"\n  {name}: entry {u_e}  stop {u_s}  target {u_t}")
        for F in frames:
            near = [s for s in frs[(F, side)].setups if abs((idx[s.m] - t).total_seconds()) <= 1800]
            if not near:
                print(f"    {F:>2}m: NO realign within 30 minutes")
            for s in near:
                gap = (idx[s.m] - t).total_seconds() / 60
                ny = idx[s.m].tz_localize("UTC").tz_convert(NY)
                print(
                    f"    {F:>2}m: realign closed {ny:%H:%M} NY ({gap:+.0f} min)  close {sg * tp.C[s.m]:.2f} "
                    f"(user entry {sg * tp.C[s.m] - u_e:+.2f})  counter extreme {sg * s.top:.2f} "
                    f"(user stop {sg * s.top - u_s:+.2f})  counter BOS {s.push_n}  trend BOS {s.trend_n}"
                )
                if F == 1:
                    kf, e, _, _ = fill_sl(frs[(F, side)], tp, s)
                    band = f"$$ band {sg * s.top:.2f} -> {sg * s.lh_old:.2f}"
                    if kf is None:
                        print(f"          {band}: price never came back to it (or no band)")
                    else:
                        fny = idx[kf].tz_localize("UTC").tz_convert(NY)
                        print(
                            f"          {band}: price came back to {sg * e:.2f} at {fny:%H:%M} NY"
                        )
        k = int(np.searchsorted(idx, t))
        e, S0, T = sg * u_e, sg * u_s, sg * u_t
        xk, rg, outcome, _ = walk(tp, k + 1, False, e, S0, min(k + 3000, tp.n - 1), "fixed", T)
        worst = float(np.max(tp.H[k + 1 : xk + 1] + tp.ex)) if xk > k else math.nan
        ny = idx[xk].tz_localize("UTC").tz_convert(NY)
        print(
            f"    the user's own trade on PU Prime: {outcome} at {ny:%m-%d %H:%M} NY, {rg:+.2f}R; "
            f"closest to the stop {S0 - worst:+.2f} away"
        )


# ─────────────────────────────── main ───────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="puprime_ecn")
    ap.add_argument("--frames", default="1,5,15")
    ap.add_argument("--recall", action="store_true")
    ap.add_argument(
        "--holdout",
        default=None,
        help='ONE cell label, e.g. "1m c1 close struct t2" — spends the holdout',
    )
    ap.add_argument(
        "--sl", action="store_true", help="the $$ structural-liquidity entry — exploration only"
    )
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default="backtest/reports/rso_realign_study")
    args = ap.parse_args()

    prof = PROFILES[args.profile]
    sw = prof.swap
    costs = dict(
        comm_rt=2 * prof.commission_per_side_per_lot, contract=prof.contract_size,
        swap_long=sw.swap_long_points, swap_short=sw.swap_short_points,
    )  # fmt: skip
    cell = parse(args.holdout) if args.holdout else None
    if args.recall:
        window, frames = ("2026-07-01", "2026-09-15"), FRAMES
    elif cell:
        window, frames = HOLDOUT, (cell[0],)
    else:
        window, frames = BUILD, tuple(int(x) for x in args.frames.split(","))
    raw = load_1m(*window)
    clean, fixed = clean_reopens(raw)
    print(
        f"{len(raw):,} PU Prime M1 bars {raw.index[0]:%Y-%m-%d} -> {raw.index[-1]:%Y-%m-%d}; profile {args.profile}: "
        f"spread {prof.spread}, commission {prof.commission_per_side_per_lot}/side/lot, swap "
        f"{sw.swap_long_points}/{sw.swap_short_points} pts; {len(fixed)} reopen spikes clipped for structure"
    )
    costs["t"] = raw.index.to_numpy()
    costs["roll"], costs["cum"] = rollovers(raw.index, sw.triple_weekday)
    tapes, frs = build(raw, clean, frames, prof.spread, args.workers)
    for F in frames:
        for side in ("short", "long"):
            ss = frs[(F, side)].setups
            p1 = sum(s.push_n == 1 for s in ss)
            print(
                f"  {F:>2}m {side:>5}: {len(ss):,} realign setups ({p1:,} with 1 counter BOS, {len(ss) - p1:,} with 2+)"
            )
    if args.recall:
        recall(raw, tapes, frs, frames)
        return

    t1m = raw.index.to_numpy()
    months = (raw.index[-1] - raw.index[0]).days / 30.44
    pools = pools_of(raw.index)
    rng = np.random.default_rng(SEED)

    if cell:
        F, c, en, st, ex = cell
        tr = book(evaluate(frs, tapes, F, costs, [cell])[(en, st, ex)], c)
        s = stats(tr, t1m, months)
        ctl = control(tr, frs, F, tapes, pools, costs, rng) if tr else None
        print(
            "\n🔴 HOLDOUT RUN — 2018-09-14 -> 2019-12-31. THIS PERIOD IS NOW SPENT FOR THIS PATTERN."
        )
        print(HEAD)
        print(
            row(
                label(cell),
                s,
                f"   control {ctl['avg']:+.3f}  z {zscore(tr, ctl):+.2f}" if ctl else "",
            )
        )
        return

    t0 = time.time()
    grid: dict = {}
    trades: dict = {}
    if args.sl:
        hows, stops, ents, drawn = ("sl",), ("lh", "atr2"), ("sl",), ("sl", "lh")
    else:
        hows, stops, ents, drawn = ("close", "fib50", "pb382"), STOPS, ENTRIES, ("close", "struct")
    for F in frames:
        rows = evaluate(frs, tapes, F, costs, hows=hows, stops=stops)
        for (en, st, ex), rr in rows.items():
            for c in COUNTERS:
                k = (F, c, en, st, ex)
                trades[k] = book(rr, c)
                grid[k] = stats(trades[k], t1m, months)
    print(f"{len(grid)} cells in {time.time() - t0:.0f}s")

    def neighbours(k):
        F, c, en, st, ex = k
        out = [(F, x, en, st, ex) for x in COUNTERS if x != c]
        out += [(F, c, x, st, ex) for x in ents if x != en]
        out += [(F, c, en, x, ex) for x in stops if x != st]
        out += [(F, c, en, st, x) for x in EXITS if x != ex]
        return [n for n in out if n in grid]

    cands = []
    for k, s in grid.items():
        if s["n"] < 30 or not (s["h1"] > 0 and s["h2"] > 0):
            continue
        nb = neighbours(k)
        pos = sum(grid[n]["tot"] > 0 for n in nb)
        if pos * 2 <= len(nb):
            continue
        cands.append(k)
    ctls = {k: control(trades[k], frs, k[0], tapes, pools, costs, rng) for k in cands}
    qual = sorted(
        (k for k in cands if zscore(trades[k], ctls[k]) >= 2.0), key=lambda k: -grid[k]["worse"]
    )

    out = ROOT / (args.out + ("_sl" if args.sl else ""))
    out.mkdir(parents=True, exist_ok=True)
    with (out / f"grid_{args.profile}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "counter", "entry", "stop", "exit"] + list(next(iter(grid.values()))))
        for k, s in grid.items():
            w.writerow(list(k) + list(s.values()))

    how_drawn = (
        "the $$ entry, stop past the older lower high"
        if args.sl
        else "market at the realign close, structure stop"
    )
    for F in frames:
        print(f"\n{F}m — THE USER'S RULE AS DRAWN ({how_drawn}), every exit")
        print(HEAD)
        for c in COUNTERS:
            for ex in EXITS:
                k = (F, c, *drawn, ex)
                print(row(label(k), grid[k]))
        best = sorted(
            (k for k in grid if k[0] == F and grid[k]["n"] >= 30), key=lambda k: -grid[k]["worse"]
        )[:12]
        print(f"\n{F}m — best 12 by the worse half's average R (>= 30 trades)")
        print(HEAD)
        for k in best:
            print(row(label(k), grid[k]))
    print(
        f"\n{len(cands)} cells positive in both halves with mostly-positive neighbours; control run on each"
    )
    print(HEAD + "  control      z")
    for k in sorted(cands, key=lambda k: -grid[k]["worse"]):
        z = zscore(trades[k], ctls[k])
        print(
            row(
                label(k),
                grid[k],
                f"  {ctls[k]['avg']:>+7.3f} {z:>+6.2f}{'  QUALIFIES' if z >= 2 else ''}",
            )
        )
    if qual and args.sl:
        print(
            f"\nLEAD (searched data): {label(qual[0])} — confirm on EURUSD or forward; "
            "--holdout is SPENT for this pattern"
        )
    elif qual:
        print(f'\nTHE PICK: {label(qual[0])} — run it ONCE with --holdout "{label(qual[0])}"')
    elif args.sl:
        print("\nNO CELL QUALIFIES — the $$ entry shows no edge even on the searched data.")
    else:
        print(
            "\nNO CELL QUALIFIES — no mechanical edge at these settings; the holdout stays unspent."
        )
    print(f"wrote {(out / f'grid_{args.profile}.csv').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
