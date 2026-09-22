"""killzone_study.py — do gold's three MPC-JARVIS kill zones carry a tradeable edge, once the
number of rules tried AND the time of day have both been paid for?

A STUDY, not a strategy: one-trade-per-day books and real costs, no Pine twin, no parity gate, so
every number it prints is a lab finding. It is built ON `loaded_level_study.py` (the bid/ask
`Book`, the swap rollovers, ATR) and `structure_patterns.py` (`FastWalk`, `net_r`) and imports
them rather than copying them. The kill zones are read off `engines/sessions/` — the canonical
implementation — and never typed in here.

THE QUESTION
  The user (2026-09-15): "the market always reverses or continues around those times." Reverse or
  continue is every outcome price has, at every minute, so it cannot be the edge on its own. The
  testable claim is narrower: at the kill-zone clock the move INTO the zone is faded (or followed)
  more reliably — in a way that pays after costs — than the same rule at any other clock time.
  Two things line the zones up with real events, which is why a burst of movement there is
  expected and is NOT evidence of direction: 10:00 New York is the US 10:00 data releases and the
  London gold price auction (15:00 London), and 13:30 is the COMEX gold settlement.

THE KILL ZONES — from SessionEngine, and checked against every bar
  Read off the engine over a winter and a summer weekday (they must agree — New York time,
  DST-aware), then the per-bar New York minute windows used here are compared with the engine's
  own flags on EVERY explore bar; one disagreement raises. The placebo clocks below are the same
  windows moved, so they are measured on the clock the engine is proven to agree with.

PART 1 — DESCRIBE (no trades, no costs). For each kill zone and every other clock start of the
  same length (5-minute grid, 03:00 NY until the window ends by 16:59, never overlapping the
  zone's own window), over explore weekdays:
    busy     the window's high-low range / ATR — how much price moves there
    follow%  how often the window's move has the SAME sign as the 60 minutes before it (50% =
             no memory; above = it continues, below = it reverses)
    turn%    how often the New York session's high or low (08:00-16:59) prints inside the window
             (windows inside the session only)
  Each kill zone's value and its percentile among the other clocks.

PART 2 — SEARCH: 3 zones x 4 entries x 3 lookbacks x 3 sizes x 2 stops x 3 exits = 648 rules,
  declared here before any result existed.
  ENTRY  fade    at the zone's first bar, trade AGAINST the move of the last L minutes
         follow  at the zone's first bar, trade WITH it
         sweep   inside the zone, price trades beyond the last-L-minutes high (low) and a bar then
                 CLOSES back inside: short (long) at the next bar's open. First trigger only; a bar
                 that triggers both sides is skipped.
         break   inside the zone, a bar CLOSES beyond the last-L-minutes high (low): long (short)
                 at the next bar's open. First trigger only.
  L      30, 60 or 120 minutes before the zone opens. At least half those minutes must have bars.
  SIZE   fade/follow: |move over L| >= 0, 0.5 or 1.0 x ATR; sweep/break: the L range >= the same.
  STOP   0.5 or 1.0 x ATR from the fill. ATR = Wilder ATR(14) on 1-hour bars (built from the M1
         with reopen spikes clipped), the last hour completed before the entry bar opens.
  EXIT   a 1R target, a 2R target, or none; every trade is out at market after 120 one-minute
         bars. A trade whose 120 bars would run past 16:59 NY that day (a data hole, an early
         close) is skipped — the same filter at every clock.
  One trade per zone per rule per day; both directions in one book.
  WALK   the studies' own (`FastWalk`, proven here against `Book.walk` on every real trade):
         entry at the bar's open, a long pays the spread (bars are bid), stop before target on
         the same bar, a gap through the stop fills at the open, a gap through the target better.
  COSTS  `puprime_ecn` through `net_r`: spread 0.12, $1/side/lot, swap if a trade ever crosses
         17:00 NY (none should).

DATA WINDOWS — the same hard rules `structure_patterns.py` enforces
  EXPLORE  2020-01-01 -> 2025-08-31. Every selection decision is made on these bars only.
  🔴 TEST  2018-09-14 -> 2019-12-31, run ONCE with `test --spend-test-set`, only on rules that
           pass all three gates. No kill-zone rule has ever been run on it. It is also the window
           the user never watched — their belief was formed on recent charts, which is why recent
           months cannot confirm it.
  SPENT    2025-09-01 onward was used by another test and is never loaded.

GATES — fixed, in this order
  1 SAMPLE  >= 25 trades in EACH half of explore (split at the bar-count midpoint) and net R
            positive in both halves.
  2 LUCK    the WHOLE 648-rule search re-run 200 times with every zone moved to a random eligible
            clock start (5-minute grid, 03:00 NY to the latest start whose trade can end by 16:55,
            never overlapping that zone's own window). The best t (net R per trade) of any rule
            through gate 1 is recorded per run; a rule must beat the 95th percentile.
  3 CLOCK   the same rule run at every eligible clock start: the kill zone's t must beat 95% of
            them. Reported beside it, as a diagnostic: the rank among New York clocks only
            (08:00+), because a rule that wins at every New York hour is a New York edge, not a
            kill-zone one.
  TEST      pass = net R per trade > 0 and t >= 1.65 on the test set.

MEASURED 2026-09-15 — PU Prime XAUUSD.p M1, 2,005,828 bars 2020-01-01 -> 2025-08-31, puprime_ecn
  0 of 648 rules pass. 42 pass gate 1 (random clocks: median 29). Best real t +1.84; luck bar
  +2.57 (random-clock best t median +1.68) — 41% of random-clock runs beat the best real rule.
  Describe: no zone's direction follows the prior hour (follow% 48.7 / 50.0 / 49.0, other clocks
  41-54). 10:00 is busy (1.74 ATR, 87th pct) and holds the NY high/low on 27.9% of days (typical
  hour 11.4%), but the 08:00-09:25 starts beat it on both. 11:45 and 13:00 are ordinary.
  Best rule, 10:00 follow L30 m0.5 s0.5 no target: 777 trades, +0.146R net, longs +96.9R vs
  shorts +16.6R, 2022-23 carry it, 2021 and 2024 lose; the same rule at 08:30 has t +2.35.
  The test set stays UNSPENT. Checks: engine windows = minute windows on every bar; FastWalk =
  Book.walk on all 252,654 real walks. Record: backtest/notes/tools.md.

Usage (from the repo root, with command-center/backend/.venv/bin/python):
  python backtest/tools/killzone_study.py explore
  python backtest/tools/killzone_study.py test --cells 'KZ1|fade|L60|m0.5|s1.0|2R' --spend-test-set
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "engines", ROOT / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import loaded_level_study as S  # noqa: E402
import structure_patterns as P  # noqa: E402
from sessions import SessionEngine  # noqa: E402

from backtest.data.resample import resample_up  # noqa: E402

CACHE = ROOT / "backtest" / "cache" / "PUPrime_Demo" / "XAUUSD_p__M1.csv"
EXPLORE = P.EXPLORE  # [start, end)
TEST_SET = P.TEST_SET  # [start, end)
PROFILE = "puprime_ecn"

RULES = ("fade", "follow", "sweep", "break")
LOOKBACKS = (30, 60, 120)
SIZES = (0.0, 0.5, 1.0)
STOPS = (0.5, 1.0)
EXITS = ("1R", "2R", "time")
EXIT_R = {"1R": 1.0, "2R": 2.0, "time": None}
CELLS = [
    (L, r, s, x, m) for L in LOOKBACKS for r in RULES for s in STOPS for x in EXITS for m in SIZES
]

HOLD = 120  # one-minute bars
ATR_N = 14  # on 1-hour bars
GRID = 5  # minutes between clock starts
EARLIEST = 3 * 60  # 03:00 NY, the London open
LAST_EXIT = 16 * 60 + 55  # a placebo's trade must be able to end by 16:55 NY
DAY_END = 16 * 60 + 59  # nothing may be held past 16:59 NY
NY_OPEN = 8 * 60
SESSION = (8 * 60, 17 * 60)  # [start, end) — the New York session for turn%
DESCRIBE_L = 60
ENTRY_SLACK = 5  # minutes: the entry bar must open within this of its intended minute

MIN_PER_HALF = 25
NULL_RUNS, MIN_NULL_RUNS, NULL_Q = 200, 100, 0.95
CLOCK_Q = 0.95
TEST_T = 1.65
SEED = 20260915
TOP = 20
NEVER = 1e12  # a target no price reaches: the "time" exit


# ─────────────────────────────── bars and clock ───────────────────────────────


def load_1m(start: str, end: str, volume: bool = False) -> pd.DataFrame:
    """Cached PU Prime M1 bars in [start, end). The test set lives in the same file, so rows outside
    the window are dropped at read, before anything computes on them. `volume` keeps the tick
    volume column (VWAP needs it); a missing cell stays NaN for the caller to treat as unknown."""
    if not CACHE.exists():
        sys.exit(f"no cached bars at {CACHE}")
    df = pd.read_csv(CACHE, parse_dates=["time"])
    df = df[(df["time"] >= start) & (df["time"] < end)].set_index("time")
    df = df[["open", "high", "low", "close"] + (["volume"] if volume else [])].astype(float)
    if df.empty:
        sys.exit(f"{CACHE} holds no bars in [{start}, {end})")
    return df


def kill_zones() -> list:
    """(name, first NY minute, length in minutes) of each kill zone, read off the canonical
    SessionEngine over a winter and a summer weekday. Nothing here types a clock time in."""
    found = []
    for day in ("2024-01-10", "2024-07-10"):  # Wednesdays, EST and EDT
        se, t0 = SessionEngine(), pd.Timestamp(day, tz=S.NY)
        flags = np.zeros((3, 1440), bool)
        for m in range(1440):
            ev = se.update(m, int((t0 + pd.Timedelta(minutes=m)).timestamp() * 1000), 0.0, 0.0)
            flags[:, m] = (ev.in_kz1, ev.in_kz2, ev.in_kz3)
        zones = []
        for z in range(3):
            on = np.flatnonzero(flags[z])
            if not len(on) or on[-1] - on[0] + 1 != len(on):
                raise RuntimeError(f"kill zone {z + 1} is not one contiguous window on {day}")
            zones.append((f"KZ{z + 1}", int(on[0]), len(on)))
        found.append(zones)
    if found[0] != found[1]:
        raise RuntimeError(f"the kill zones moved between winter and summer: {found}")
    return found[0]


def hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


@dataclass
class Tape:
    raw: pd.DataFrame
    n: int
    minute: np.ndarray  # per bar: New York minute of the day
    day: np.ndarray  # per bar: row in the day grid, -1 for a weekend date
    days: np.ndarray  # New York weekday dates
    idx: np.ndarray  # [day, minute] -> bar index, -1 = no bar
    C: np.ndarray  # [day, minute] close, NaN = no bar
    Cf: np.ndarray  # close carried forward within the day
    H: np.ndarray
    L: np.ndarray
    nxt: np.ndarray  # [day, minute] first bar at or after that minute, same day; -1 = none
    atr: np.ndarray  # per bar: ATR(14) of the last 1-hour bar completed before it opens
    books: dict
    fast: dict
    costs: dict
    split: int
    months: float
    hold: int  # one-minute bars before the time exit


def build_tape(raw: pd.DataFrame, hold: int = HOLD) -> Tape:
    t0 = time.time()
    n = len(raw)
    ny = raw.index.tz_localize("UTC").tz_convert(S.NY)
    minute = (ny.hour * 60 + ny.minute).to_numpy()
    date = ny.tz_localize(None).normalize().to_numpy()
    week = np.asarray(ny.weekday < 5)
    days, inv = np.unique(date[week], return_inverse=True)
    day = np.full(n, -1, np.int64)
    day[week] = inv
    rows = np.flatnonzero(week)
    idx = np.full((len(days), 1440), -1, np.int64)
    if len(np.unique(day[rows] * 1440 + minute[rows])) != len(rows):
        raise RuntimeError("two weekday bars share one New York minute")
    idx[day[rows], minute[rows]] = rows
    grids = {}
    for k in ("close", "high", "low"):
        g = np.full(idx.shape, np.nan)
        g[day[rows], minute[rows]] = raw[k].to_numpy()[rows]
        grids[k] = g
    big = np.iinfo(np.int64).max
    nxt = np.minimum.accumulate(np.where(idx >= 0, idx, big)[:, ::-1], axis=1)[:, ::-1]
    nxt = np.where(nxt == big, -1, nxt)
    clean, fixed = S.clean_reopens(raw)
    h1 = resample_up(clean, 60, 1)
    a1 = S.wilder_atr(*(h1[k].to_numpy() for k in ("high", "low", "close")), n=ATR_N)
    done = (h1.index + pd.Timedelta(minutes=60)).to_numpy()
    j = np.searchsorted(done, raw.index.to_numpy(), side="right") - 1
    atr = np.where(j >= 0, a1[np.clip(j, 0, None)], np.nan)
    prof = S.PROFILES[PROFILE]
    sw, spread = prof.swap, prof.spread_or_refuse()
    costs = dict(
        comm_rt=2 * prof.commission_per_side_per_lot, contract=prof.contract_size,
        swap_long=sw.swap_long_points, swap_short=sw.swap_short_points, t=raw.index.to_numpy(),
    )  # fmt: skip
    costs["roll"], costs["cum"] = S.rollovers(raw.index, sw.triple_weekday)
    books = {"short": S.Book(raw, "short", spread), "long": S.Book(S.mirror(raw), "long", spread)}
    S.MAX_HOLD = hold  # `Book.walk` reads its time exit from this global
    tp = Tape(
        raw=raw, n=n, minute=minute, day=day, days=days, idx=idx, C=grids["close"],
        Cf=pd.DataFrame(grids["close"]).ffill(axis=1).to_numpy(), H=grids["high"],
        L=grids["low"], nxt=nxt, atr=atr, books=books,
        fast={k: P.FastWalk(b, hold) for k, b in books.items()}, costs=costs, split=n // 2,
        months=(raw.index[-1] - raw.index[0]).days / 30.44, hold=hold,
    )  # fmt: skip
    print(
        f"M1: {n:,} bars {raw.index[0]:%Y-%m-%d %H:%M} -> {raw.index[-1]:%Y-%m-%d %H:%M} UTC, "
        f"{len(days):,} New York weekdays, {len(h1):,} hour bars, {len(fixed)} reopen spikes "
        f"clipped for the ATR ({time.time() - t0:.0f}s)"
    )
    return tp


def check_engine(tp: Tape, zones: list) -> None:
    """CHECK 0 — the engine's kill-zone flags against this tool's minute windows, every bar."""
    t0 = time.time()
    se = SessionEngine()
    ms = tp.raw.index.values.astype("datetime64[ms]").astype(np.int64)  # unit-safe under pandas 3
    hi, lo = tp.raw["high"].to_numpy(), tp.raw["low"].to_numpy()
    eng = np.zeros((3, tp.n), bool)
    for i in range(tp.n):
        ev = se.update(i, int(ms[i]), float(hi[i]), float(lo[i]))
        eng[0, i], eng[1, i], eng[2, i] = ev.in_kz1, ev.in_kz2, ev.in_kz3
    for z, (name, s, d) in enumerate(zones):
        mine = (tp.minute >= s) & (tp.minute < s + d)
        bad = int(np.sum(mine != eng[z]))
        if bad:
            raise RuntimeError(
                f"{name}: the minute window disagrees with SessionEngine on {bad} bars"
            )
    print(
        f"CHECK 0 — SessionEngine's kill zones match the minute windows on all {tp.n:,} bars "
        f"({', '.join(f'{nm} {hhmm(s)}-{hhmm(s + d - 1)}' for nm, s, d in zones)} NY) "
        f"({time.time() - t0:.0f}s)"
    )


# ─────────────────────────────── entries ───────────────────────────────


def _hold_ok(tp: Tape, e: np.ndarray) -> np.ndarray:
    """The entry exists, has an ATR, and its hold (`tp.hold` bars) ends the same New York day by
    16:59."""
    ok = (e >= 0) & (e + tp.hold < tp.n)
    ee = np.where(ok, e, 0)
    ok &= np.isfinite(tp.atr[ee]) & (tp.atr[ee] > 0)
    x = np.where(ok, ee + tp.hold, 0)
    return ok & (tp.day[x] == tp.day[ee]) & (tp.minute[x] <= DAY_END)


def _first(mask: np.ndarray, d: int) -> np.ndarray:
    return np.where(mask.any(axis=1), np.argmax(mask, axis=1), d)


def window(tp: Tape, s: int, d: int, L: int) -> dict:
    """One clock window, one row per day -> rule -> (entry bar, is_long, size in price)."""
    D = len(tp.days)
    rows = np.arange(D)
    p0, p1 = tp.Cf[:, s - L - 1], tp.Cf[:, s - 1]
    pre = p1 - p0
    lbH, lbL = tp.H[:, s - L : s], tp.L[:, s - L : s]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN rows are refused just below
        rh, rl = np.nanmax(lbH, axis=1), np.nanmin(lbL, axis=1)
    base = (np.sum(~np.isnan(lbH), axis=1) >= L / 2) & np.isfinite(p0) & np.isfinite(p1)
    out = {}
    e = tp.nxt[:, s]
    ok = base & (pre != 0) & (e >= 0)
    ok &= tp.minute[np.where(ok, e, 0)] < s + ENTRY_SLACK
    ok &= _hold_ok(tp, np.where(ok, e, -1))
    up = pre[ok] > 0
    out["follow"] = (e[ok], up, np.abs(pre[ok]))
    out["fade"] = (e[ok], ~up, np.abs(pre[ok]))
    Hz, Lz, Cz = tp.H[:, s : s + d], tp.L[:, s : s + d], tp.C[:, s : s + d]
    hc, lc = rh[:, None], rl[:, None]
    with np.errstate(invalid="ignore"):
        brk = (Cz > hc, Cz < lc)
        swp = (
            np.maximum.accumulate(Lz < lc, axis=1) & (Cz > lc),  # low taken, closed back above
            np.maximum.accumulate(Hz > hc, axis=1) & (Cz < hc),  # high taken, closed back below
        )
    for rule, (long_m, short_m) in (("break", brk), ("sweep", swp)):
        jl, js = _first(long_m, d), _first(short_m, d)
        j = np.minimum(jl, js)
        fire = base & (j < d) & (jl != js)
        trig = np.where(fire, tp.idx[rows, s + np.minimum(j, d - 1)], -1)
        fire &= trig >= 0
        e = np.where(fire, trig + 1, -1)
        fire &= e < tp.n
        e = np.where(fire, e, -1)
        ee, tt = np.where(fire, e, 0), np.where(fire, trig, 0)
        fire &= (tp.day[ee] == tp.day[tt]) & (tp.minute[ee] - tp.minute[tt] <= ENTRY_SLACK)
        fire &= _hold_ok(tp, np.where(fire, e, -1))
        out[rule] = (e[fire], (jl < js)[fire], (rh - rl)[fire])
    return out


# ─────────────────────────────── trades ───────────────────────────────


def walk(tp: Tape, e: np.ndarray, is_long: np.ndarray, risk: np.ndarray, mult, prove=False):
    """Net R, gross R, exit bar and outcome per trade, both sides through FastWalk + net_r.
    `prove` re-walks every trade with the study's own `Book.walk` and raises on any difference."""
    net, gross = np.empty(len(e)), np.empty(len(e))
    xbar, how = np.empty(len(e), np.int64), np.empty(len(e), np.int8)
    for side, sel in (("short", ~is_long), ("long", is_long)):
        if not sel.any():
            continue
        b, k, rk = tp.books[side], e[sel], risk[sel]
        entry = b.O[k] - b.en
        stop = entry + rk
        target = entry - (mult * rk if mult else NEVER)
        xb, rg, o = tp.fast[side].walk(k, entry, stop, target)
        if prove:
            for q in range(len(k)):
                x, r, oc = b.walk(
                    int(k[q]), float(entry[q]), float(stop[q]), float(target[q]), True
                )
                if x != xb[q] or P.OUTCOME.index(oc) != o[q] or abs(r - rg[q]) > 1e-12:
                    raise RuntimeError(
                        f"FastWalk disagrees with Book.walk on a {side} at bar {k[q]}: "
                        f"{(x, r, oc)} vs {(xb[q], rg[q], o[q])}"
                    )
        net[sel] = P.net_r(tp.costs, side, k, xb, rk, rg)[0]
        gross[sel], xbar[sel], how[sel] = rg, xb, o
    return net, gross, xbar, how


def cell_stats(net: np.ndarray, first: np.ndarray) -> tuple:
    """(n, n in the 1st half, net R 1st half, net R 2nd half, mean, t)."""
    n = len(net)
    if n < 2:
        return (n, int(first.sum()), float(net[first].sum()), float(net[~first].sum()), 0.0, 0.0)
    mean, sd = float(net.mean()), float(net.std(ddof=1))
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    return (n, int(first.sum()), float(net[first].sum()), float(net[~first].sum()), mean, t)


def gate1(st: np.ndarray) -> np.ndarray:
    n, n1, h1, h2 = st[..., 0], st[..., 1], st[..., 2], st[..., 3]
    return (n1 >= MIN_PER_HALF) & (n - n1 >= MIN_PER_HALF) & (h1 > 0) & (h2 > 0)


def evaluate(tp: Tape, s: int, d: int, keep=False, prove=False):
    """All 216 rules of one zone at clock start `s`: stats[cell] = cell_stats(...), in CELLS
    order; with `keep`, the trades of each cell too."""
    stats = np.zeros((len(CELLS), 6))
    trades = {}
    ci = 0
    for L in LOOKBACKS:
        w = window(tp, s, d, L)
        for rule in RULES:
            e, is_long, size = w[rule]
            a = tp.atr[e]
            first = e < tp.split
            for stop in STOPS:
                risk = stop * a
                for ex in EXITS:
                    net, gross, xb, how = walk(tp, e, is_long, risk, EXIT_R[ex], prove)
                    for m in SIZES:
                        if CELLS[ci] != (L, rule, stop, ex, m):
                            raise RuntimeError("cell order drifted from CELLS")
                        sel = size >= m * a
                        stats[ci] = cell_stats(net[sel], first[sel])
                        if keep:
                            trades[CELLS[ci]] = dict(
                                e=e[sel], is_long=is_long[sel], net=net[sel], gross=gross[sel],
                                how=how[sel], xbar=xb[sel], risk=risk[sel],
                            )  # fmt: skip
                        ci += 1
    return stats, trades


def label(zone: str, c: tuple) -> str:
    L, rule, stop, ex, m = c
    return f"{zone}|{rule}|L{L}|m{m:g}|s{stop:g}|{ex}"


def parse(text: str) -> tuple:
    zone, rule, L, m, stop, ex = text.split("|")
    c = (int(L[1:]), rule, float(stop[1:]), ex, float(m[1:]))
    if c not in CELLS:
        sys.exit(f"not a declared rule: {text}")
    return zone, c


# ─────────────────────────────── clocks ───────────────────────────────


def placebo_clocks(s0: int, d: int, latest: int) -> list:
    """5-minute-grid starts from 03:00 NY up to `latest` inclusive that never overlap the zone's
    own window [s0, s0 + d)."""
    return [s for s in range(EARLIEST, latest + 1, GRID) if abs(s - s0) >= d]


def surface(tp: Tape, zones: list) -> dict:
    """Every rule of every zone at every eligible placebo clock: the latest start is the one whose
    last possible entry (the zone's end) plus the 120-bar hold still ends by 16:55 NY."""
    out = {}
    t0 = time.time()
    for name, s0, d in zones:
        clocks = placebo_clocks(s0, d, LAST_EXIT - HOLD - d)
        st = np.stack([evaluate(tp, s, d)[0] for s in clocks])
        out[name] = dict(clocks=np.array(clocks), stats=st, g1=gate1(st), t=st[..., 5])
        print(
            f"  {name}: {len(clocks)} placebo clocks {hhmm(clocks[0])}-{hhmm(clocks[-1])} "
            f"({time.time() - t0:.0f}s)"
        )
    return out


def luck_bar(surf: dict, runs: int, seed: int) -> dict:
    """Gate 2: each run moves every zone to one random eligible clock and records the best t of
    any of the 648 rules through gate 1."""
    rng = np.random.default_rng(seed)
    best, npass = np.full(runs, -np.inf), np.zeros(runs, np.int64)
    for r in range(runs):
        t, g = [], []
        for sf in surf.values():
            c = int(rng.integers(len(sf["clocks"])))
            t.append(sf["t"][c])
            g.append(sf["g1"][c])
        t, g = np.concatenate(t), np.concatenate(g)
        npass[r] = int(g.sum())
        if g.any():
            best[r] = float(t[g].max())
    return dict(best=best, npass=npass)


# ─────────────────────────────── describe ───────────────────────────────


def describe(tp: Tape, zones: list) -> list:
    """Part 1 — busy / follow% / turn% for each zone against every other clock of its length."""
    Hs, Ls = tp.H[:, SESSION[0] : SESSION[1]], tp.L[:, SESSION[0] : SESSION[1]]
    full = np.sum(~np.isnan(Hs), axis=1) >= 0.8 * (SESSION[1] - SESSION[0])
    hi_m = SESSION[0] + np.argmax(np.where(np.isnan(Hs), -np.inf, Hs), axis=1)
    lo_m = SESSION[0] + np.argmin(np.where(np.isnan(Ls), np.inf, Ls), axis=1)
    rows = []
    for name, s0, d in zones:
        starts = sorted(set(placebo_clocks(s0, d, DAY_END + 1 - d)) | {s0})  # ends by 16:59
        for s in starts:
            pre = tp.Cf[:, s - 1] - tp.Cf[:, s - 1 - DESCRIBE_L]
            mv = tp.Cf[:, s + d - 1] - tp.Cf[:, s - 1]
            e = tp.nxt[:, s]
            a = np.where(e >= 0, tp.atr[np.where(e >= 0, e, 0)], np.nan)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                rng = np.nanmax(tp.H[:, s : s + d], axis=1) - np.nanmin(tp.L[:, s : s + d], axis=1)
            busy = rng / a
            busy = busy[np.isfinite(busy)]
            both = np.isfinite(pre) & np.isfinite(mv) & (pre != 0) & (mv != 0)
            fol = float(np.mean(np.sign(pre[both]) == np.sign(mv[both])))
            inside = SESSION[0] <= s and s + d <= SESSION[1]
            hit = ((hi_m >= s) & (hi_m < s + d)) | ((lo_m >= s) & (lo_m < s + d))
            turn = float(np.mean(hit[full])) if inside else math.nan
            rows.append(
                dict(zone=name, clock=hhmm(s), start=s, real=s == s0, busy=float(busy.mean()),
                     follow=fol, n_follow=int(both.sum()), turn=turn)
            )  # fmt: skip
    return rows


def pct(value: float, others: np.ndarray) -> float:
    others = others[np.isfinite(others)]
    return float(np.mean(others < value) * 100) if len(others) else math.nan


# ─────────────────────────────── report ───────────────────────────────


def write_csv(path: Path, rows: list) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def by_year(tp: Tape, tr: dict) -> str:
    yrs = tp.raw.index[tr["e"]].year.to_numpy()
    return "  ".join(f"{y}:{tr['net'][yrs == y].sum():+.1f}" for y in np.unique(yrs))


def explore(a) -> None:
    if a.null_runs < MIN_NULL_RUNS:
        sys.exit(f"refused: the luck bar needs at least {MIN_NULL_RUNS} null runs")
    t_all = time.time()
    zones = kill_zones()
    tp = build_tape(load_1m(*EXPLORE))
    check_engine(tp, zones)
    out = Path(a.out)

    # ── part 1 ──
    drows = describe(tp, zones)
    write_csv(out / "describe.csv", drows)
    print("\nPART 1 — DESCRIBE: each kill zone against every other clock start of the same length")
    print(
        f"  {'':<16} {'busy':>6} {'pct':>5}   {'follow%':>7} {'z vs 50':>7} {'pct':>5}   "
        f"{'turn%':>6} {'pct':>5}   (pct = share of other clocks it beats)"
    )
    for name, s0, d in zones:
        zr = [r for r in drows if r["zone"] == name]
        me = next(r for r in zr if r["real"])
        oth = [r for r in zr if not r["real"]]
        ob, of, ot = (np.array([r[k] for r in oth]) for k in ("busy", "follow", "turn"))
        z = (me["follow"] - 0.5) / math.sqrt(0.25 / me["n_follow"])
        print(
            f"  {name} {hhmm(s0)}-{hhmm(s0 + d - 1)}  {me['busy']:>6.2f} {pct(me['busy'], ob):>4.0f}%   "
            f"{me['follow'] * 100:>6.1f}% {z:>+7.2f} {pct(me['follow'], of):>4.0f}%   "
            f"{me['turn'] * 100:>5.1f}% {pct(me['turn'], ot):>4.0f}%"
        )
        print(
            f"  {'':<16} other clocks: busy {np.median(ob):.2f}, follow% {np.median(of) * 100:.1f} "
            f"({np.min(of) * 100:.1f}-{np.max(of) * 100:.1f}), turn% {np.nanmedian(ot) * 100:.1f}"
        )

    # ── part 2 ──
    print(f"\nPART 2 — SEARCH: {len(CELLS) * len(zones)} rules, {PROFILE} costs")
    real, trades = {}, {}
    t0 = time.time()
    for name, s0, d in zones:
        real[name], trades[name] = evaluate(tp, s0, d, keep=True, prove=True)
    ntr = sum(len(tr["e"]) for zt in trades.values() for c, tr in zt.items() if c[4] == 0.0)
    print(
        f"CHECK 1 — FastWalk matched Book.walk on every real trade ({ntr:,} walks; exit bar, "
        f"outcome and R identical) ({time.time() - t0:.0f}s)"
    )
    print("placebo clocks:")
    surf = surface(tp, zones)
    luck = luck_bar(surf, a.null_runs, a.seed)
    q95 = float(np.quantile(luck["best"], NULL_Q))

    rows = []
    for name, s0, d in zones:
        sf, st = surf[name], real[name]
        g1 = gate1(st)
        ny = sf["clocks"] >= NY_OPEN
        for ci, c in enumerate(CELLS):
            tr = trades[name][c]
            others = sf["t"][:, ci]
            rank = float(np.mean(others < st[ci, 5]))
            rank_ny = float(np.mean(others[ny] < st[ci, 5]))
            n = int(st[ci, 0])
            rows.append(
                dict(
                    rule=label(name, c), n=n, per_month=n / tp.months,
                    win=float(np.mean(tr["net"] > 0) * 100) if n else 0.0,  # net winners, any exit
                    avg_gross=float(tr["gross"].mean()) if n else 0.0, avg_net=st[ci, 4],
                    total_net=float(tr["net"].sum()), h1=st[ci, 2], h2=st[ci, 3], t=st[ci, 5],
                    long_n=int(tr["is_long"].sum()),
                    long_net=float(tr["net"][tr["is_long"]].sum()),
                    short_net=float(tr["net"][~tr["is_long"]].sum()),
                    gate1=bool(g1[ci]), beats_luck=bool(g1[ci] and st[ci, 5] > q95),
                    clock_rank=rank * 100, clock_rank_ny=rank_ny * 100,
                    gate3=bool(rank >= CLOCK_Q), by_year=by_year(tp, tr) if n else "",
                )
            )  # fmt: skip
    write_csv(out / "rules.csv", rows)
    write_csv(out / "luck.csv", [dict(run=i, best_t=b, n_gate1=int(k)) for i, (b, k) in
                                 enumerate(zip(luck["best"], luck["npass"]))])  # fmt: skip
    srows = []
    for name, sf in surf.items():
        for k, s in enumerate(sf["clocks"]):
            for ci, c in enumerate(CELLS):
                st = sf["stats"][k, ci]
                srows.append(dict(rule=label(name, c), clock=hhmm(int(s)), n=int(st[0]),
                                  avg_net=st[4], t=st[5], gate1=bool(sf["g1"][k, ci])))  # fmt: skip
    write_csv(out / "clocks.csv", srows)

    g1n = sum(r["gate1"] for r in rows)
    g3n = sum(r["gate3"] for r in rows)
    win = [r for r in rows if r["gate1"] and r["beats_luck"] and r["gate3"]]
    print(
        f"\n  gate 1 — both halves net positive, >= {MIN_PER_HALF} trades each: {g1n} of {len(rows)}"
    )
    print(
        f"  gate 2 — luck bar, {a.null_runs} runs with every zone at a random clock (seed "
        f"{a.seed}): best t per run median {np.median(luck['best']):+.2f}, 95th percentile "
        f"{q95:+.2f}; rules through gate 1 per run: median {int(np.median(luck['npass']))}"
    )
    best_real = max((r["t"] for r in rows if r["gate1"]), default=-math.inf)
    print(
        f"           best real t {best_real:+.2f} — beaten by {np.mean(luck['best'] >= best_real) * 100:.1f}% "
        f"of the random-clock runs; rules past the bar: {sum(r['beats_luck'] for r in rows)}"
    )
    # how many rules rank in the top 5% of clocks — at the real clock vs at each placebo clock
    counts = {}
    for name, s0, d in zones:
        T = surf[name]["t"]
        k_real = np.array(
            [r["clock_rank"] >= CLOCK_Q * 100 for r in rows if r["rule"].startswith(name + "|")]
        )
        per_clock = np.array([np.sum(np.mean(np.delete(T, k, 0) < T[k], axis=0) >= CLOCK_Q)
                              for k in range(len(T))])  # fmt: skip
        counts[name] = (int(k_real.sum()), per_clock)
    print(
        f"  gate 3 — the rule at the kill zone beats {CLOCK_Q * 100:.0f}% of clocks: {g3n} of {len(rows)} "
        f"(an ordinary clock would score about {(1 - CLOCK_Q) * 100:.0f}% = {len(rows) * (1 - CLOCK_Q):.0f})"
    )
    for name, (k, per_clock) in counts.items():
        print(
            f"           {name}: {k} of {len(CELLS)} rules; placebo clocks score median "
            f"{int(np.median(per_clock))}, 95th percentile {int(np.quantile(per_clock, 0.95))} — "
            f"the kill zone beats {np.mean(per_clock < k) * 100:.0f}% of them"
        )
    print(f"  ALL THREE GATES: {len(win)}")

    head = (
        f"\n  {'rule':<30} {'n':>5} {'/mo':>5} {'win%':>5} {'gross':>7} {'net':>7} {'tot R':>7} "
        f"{'1st½':>7} {'2nd½':>7} {'t':>6} {'clk%':>5} {'NY%':>5}  g1 luck g3"
    )
    yn = lambda b: " Y" if b else " ."  # noqa: E731
    for title, sel in (
        (f"TOP {TOP} BY t (gate 1 passers)", sorted((r for r in rows if r["gate1"]), key=lambda r: -r["t"])[:TOP]),
        ("BEST RULE PER ZONE AND ENTRY (gate 1 passers)", [
            max(g, key=lambda r: r["t"]) for name, _, _ in zones for rule in RULES
            if (g := [r for r in rows if r["gate1"] and r["rule"].startswith(f"{name}|{rule}|")])
        ]),
    ):  # fmt: skip
        print(f"\n{title}{head}")
        for r in sel:
            print(
                f"  {r['rule']:<30} {r['n']:>5} {r['per_month']:>5.1f} {r['win']:>5.1f} "
                f"{r['avg_gross']:>+7.3f} {r['avg_net']:>+7.3f} {r['total_net']:>+7.1f} {r['h1']:>+7.1f} "
                f"{r['h2']:>+7.1f} {r['t']:>+6.2f} {r['clock_rank']:>5.0f} {r['clock_rank_ny']:>5.0f} "
                f"{yn(r['gate1'])}  {yn(r['beats_luck'])}  {yn(r['gate3'])}"
            )
    if win:
        print("\nSURVIVORS — by year (net R), long/short split:")
        for r in win:
            print(
                f"  {r['rule']}: {r['by_year']}  | long {r['long_net']:+.1f} short {r['short_net']:+.1f}"
            )
        print("  -> ONE run on the test set: test --cells '<rule>' --spend-test-set")
    else:
        print("\nNo rule passed all three gates — the test set stays UNSPENT.")
    print(f"\ncsv: {out}/  ({time.time() - t_all:.0f}s)")


def test(a) -> None:
    if not a.spend_test_set:
        sys.exit(
            f"refused: {TEST_SET[0]} -> {TEST_SET[1]} is the untouched test set. It gets ONE run, "
            "only on rules that passed all three explore gates. Add --spend-test-set to spend it."
        )
    zones = {z[0]: z for z in kill_zones()}
    picks = [parse(x.strip()) for x in a.cells.split(",")]
    tp = build_tape(load_1m(*TEST_SET))
    print(
        f"\nTEST SET {TEST_SET[0]} -> {TEST_SET[1]} — pass = net R per trade > 0 and t >= {TEST_T}"
    )
    for zone, c in picks:
        name, s0, d = zones[zone]
        st, tr = evaluate(tp, s0, d, keep=True)
        k = CELLS.index(c)
        n, mean, t = int(st[k, 0]), st[k, 4], st[k, 5]
        ok = n > 1 and mean > 0 and t >= TEST_T
        print(
            f"  {label(zone, c)}: {n} trades, net {mean:+.3f} R/trade, total {tr[c]['net'].sum():+.1f}R, "
            f"t {t:+.2f} -> {'PASS' if ok else 'FAIL'}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("explore")
    ex.add_argument("--null-runs", type=int, default=NULL_RUNS)
    ex.add_argument("--seed", type=int, default=SEED)
    ex.add_argument("--out", default="backtest/reports/killzone_study")
    te = sub.add_parser("test")
    te.add_argument("--cells", required=True)
    te.add_argument("--spend-test-set", action="store_true")
    a = ap.parse_args()
    explore(a) if a.cmd == "explore" else test(a)


if __name__ == "__main__":
    main()
