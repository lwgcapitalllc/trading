"""loaded_level_study.py — the Loaded Level (ELS) setup as the user's OWN trades define it, detected
on the canonical engines and graded over a grid of reward-to-risk floors, targets, entry types and
structure sizes.

A STUDY, not a strategy: one position slot and real costs, but no Pine twin and no parity gate, so
every number it prints is a lab finding. The trades it was built from are Examples 3-9 in
`docs/DAVINCI_MODEL_SPEC.md` (seven 5-minute XAUUSD shorts, all winners).

THE SETUP, as a short (a long is the SAME code on mirrored bars — see `mirror()`):
  1 TOP     a confirmed swing high whose push took liquidity within SWEEP_LB bars before it: an
            external bullish break, a named high from the liquidity engine (session / day /
            4-hour / week), or an internal bullish break.
  2 LEVELS  every later lower high, merged within the equal-highs band (ATR(50) x 0.25 — the
            canonical engine's own tolerance). TOUCHES = how many swings merged into a level.
  3 -> 4    INDUCEMENT: a swing low after the top gets undercut. "4" = the lowest low since the top.
  5 ENTRY   "stab":    a sell limit at the first level the rally stabs whose reward-to-risk clears
                       the floor (the user's own entry — "do not wait for the close").
            "reclaim": sell at the close of the first bar, within RECLAIM_WAIT bars of the stab,
                       that closes back BELOW the level — a stab that failed.
  STOP      the top + BUFFER x ATR(50).
  TARGET    "4" | "pool" (nearest untaken swing low below 4) | "named" (nearest untaken named low
            below 4 — session / day / 4-hour / week). A pool further than POOL_GAP of the
            top-to-4 range below 4 falls back to 4.
  SIZE      min stop and min top-to-4 range, both in ATR(50). The user's seven trades are printed
            in these units by `--recall-only`, which is where the FAITHFUL thresholds come from.
  DEAD      the top is traded through, or EXPIRY bars pass. A setup trades at most once.

⚠ LOOK-AHEAD: a candidate at bar i is priced only from state closed by bar i-1 — swings confirm
  2 bars late (the engine's own pivot), "4" and the pools are read before bar i updates them.
🔴 THE BROKER'S DAILY REOPEN BAR IS CLEANED FOR DETECTION ONLY. PU Prime's first bar after the
  17:00 NY break can print a spike no chart shows (22 Jul 2026 opened 19.20 below both neighbours)
  and it "takes" levels that were never traded. Detection clips a reopen bar's wick to its own
  close and the previous close when it pokes further than max($2, 3x a typical bar). FILLS, STOPS
  AND TARGETS USE THE RAW BARS — the broker fills on what it printed.
🔴 NEVER READ THIS IN R WITHOUT A MINIMUM STOP. Overnight financing is charged per LOT, so in R it
  scales with 1/stop: the first grid let through stops of a few cents and one long carried -408R
  of swap. R on a stop smaller than the market's own noise measures the stop, not the setup.
⚠ ONE SLOT: a bot holds one trade. A setup whose level qualifies while the slot is busy stays armed.
⚠ A GRID HANDS BACK A WINNER WHATEVER THE DATA IS. Cells are ranked on the WORSE calendar half,
  the winner's neighbours are printed, and the shortlist is scored against random entries matched
  on direction, stop distance and target distance, entered at a bar close and checked from the
  very next bar for both stop and target.

Usage:
  python backtest/tools/loaded_level_study.py --recall-only      # prove it finds the 7 trades
  python backtest/tools/loaded_level_study.py                    # the full grid, 2020 -> today
"""

from __future__ import annotations

import argparse
import bisect
import csv
import itertools
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "engines"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from equal_highs_lows import EqualHighsLowsEngine  # noqa: E402

from backtest.fills import PROFILES  # noqa: E402
from backtest.replay.loop import iter_bars  # noqa: E402
from backtest.replay.stack import EngineConfig, EngineStack  # noqa: E402

SWEEP_LB = 24  # bars: the sweep must sit within 2 hours before the top
EXPIRY = 864  # bars: a setup lives 3 days of 5-minute trading
MAX_HOLD = 1152  # bars: 4 days, then the trade is closed at market ("time")
POOL_AGE = 864  # bars: a pool below "4" must be at most 3 days old
POOL_GAP = 0.35  # a pool further than this fraction of the top-to-4 range below "4" is ignored
RECLAIM_WAIT = 3  # bars after the stab in which a close back below the level still counts
BUFFER = 0.25  # stop = top + BUFFER x ATR(50); 0 / 0.25 / 0.5 moved nothing in the first grid
MAX_ALIVE = 8
REOPEN_GAP_S = 55 * 60
POINT = 0.01  # XAUUSD: swaps are quoted in points of 0.01
NY = ZoneInfo("America/New_York")

FLOORS = (0.0, 1.0, 1.5, 2.0, 2.5, 3.0)
TARGETS = ("4", "pool", "named")
ENTRIES = ("stab", "reclaim")
MIN_RISK = (0.0, 1.0, 2.0)  # stop distance, in ATR(50)
MIN_RANGE = (0.0, 5.0, 10.0)  # top-to-4 range, in ATR(50)
TOUCHES = (1, 2)
NEED_SOS = (False, True)
DIRS = ("both", "short", "long")
FAITHFUL = dict(min_risk=1.0, min_range=5.0, touches=1, need_sos=False)  # sized like the 7 trades

# The user's trades (docs/DAVINCI_MODEL_SPEC.md, Examples 3-9): broker top, fill bar (UTC), entry.
EXAMPLES = [
    ("Ex3 26 Aug", 4673.72, "2026-08-27 01:50", 4633.87),
    ("Ex4 25 Aug", 4696.75, "2026-08-25 15:35", 4653.83),
    ("Ex5 28 Aug", 4643.06, "2026-08-28 13:55", 4616.75),
    ("Ex6 31 Aug", 4472.08, "2026-08-31 10:50", 4453.98),
    ("Ex7 04 Sep", 4510.83, "2026-09-04 07:40", 4486.20),
    ("Ex8 07 Sep", 4449.00, "2026-09-08 01:45", 4438.20),
    ("Ex9 22 Jul", 4166.08, "2026-07-23 01:00", 4138.07),
]


# ─────────────────────────────── bars ───────────────────────────────


def load_bars(server_dir: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    path = ROOT / "backtest" / "cache" / server_dir / f"{symbol}__M5.csv"
    if not path.exists():
        sys.exit(f"no cached bars at {path}")
    df = pd.read_csv(path, parse_dates=["time"])
    df = df[(df["time"] >= start) & (df["time"] < end)].set_index("time")
    return df[["open", "high", "low", "close"]].astype(float)


def clean_reopens(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """Clip a reopen bar's spike to its own close and the previous close. Causal: uses only the
    bar itself and bars before it. Returns the cleaned frame and what was clipped."""
    o, h, lo, c = (df[k].to_numpy().copy() for k in ("open", "high", "low", "close"))
    # in SECONDS whatever unit pandas parsed to: `asi8 // 10**9` assumed nanoseconds, and pandas 3
    # parses to microseconds, so no gap was ever a reopen (2026-09-21, test_clean_reopens_units)
    secs = df.index.values.astype("datetime64[s]").astype(np.int64)
    rng = h - lo
    fixed = []
    for i in range(1, len(df)):
        if secs[i] - secs[i - 1] < REOPEN_GAP_S:
            continue
        thr = max(2.0, 3.0 * float(np.median(rng[max(0, i - 24) : i])))
        lo_ok, hi_ok = min(c[i], c[i - 1]), max(c[i], c[i - 1])
        if lo_ok - lo[i] > thr:
            fixed.append((df.index[i], "low", lo[i], lo_ok))
            lo[i] = lo_ok
            o[i] = max(o[i], lo_ok)
        if h[i] - hi_ok > thr:
            fixed.append((df.index[i], "high", h[i], hi_ok))
            h[i] = hi_ok
            o[i] = min(o[i], hi_ok)
    out = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=df.index)
    return out, fixed


def mirror(df: pd.DataFrame) -> pd.DataFrame:
    """Negate prices so the SHORT code finds LONGS. High and low swap because negation flips which
    is larger. Never a hand-written bullish branch — that is where a sign goes missing. The
    engines' symmetry this relies on was CHECKED: on 73,294 bars every bullish/bearish structure
    count and every high/low liquidity count matches its mirror exactly."""
    return pd.DataFrame(
        {"open": -df["open"], "high": -df["low"], "low": -df["high"], "close": -df["close"]},
        index=df.index,
    )


def wilder_atr(h: np.ndarray, lo: np.ndarray, c: np.ndarray, n: int = 50) -> np.ndarray:
    prev = np.concatenate(([c[0]], c[:-1]))
    tr = np.maximum(h - lo, np.maximum(np.abs(h - prev), np.abs(lo - prev)))
    out = np.full(len(h), np.nan)
    if len(h) >= n:
        out[n - 1] = tr[:n].mean()
        for i in range(n, len(h)):
            out[i] = out[i - 1] + (tr[i] - out[i - 1]) / n
    return out


# ─────────────────────────────── detection ───────────────────────────────


@dataclass
class Setup:
    id: int
    top: float
    top_bar: int
    made: int
    kind: str  # the strongest sweep under the top: "ext" > "named" > "int"
    low4: float
    lv_px: list = field(default_factory=list)  # lower-high levels, ascending
    lv_info: list = field(default_factory=list)  # [touches, made_bar] per level
    max_plow: float = -math.inf
    induced: bool = False
    bear_sos: bool = False
    dead: int = -1


class _Pools:
    """Untaken lows as a price-sorted list. Taken = a later low trades BELOW it (a double bottom
    that holds is still a pool). Older than POOL_AGE is dropped."""

    def __init__(self) -> None:
        self.px: list = []
        self.bar: list = []

    def add(self, price: float, bar: int) -> None:
        k = bisect.bisect_left(self.px, price)
        self.px.insert(k, price)
        self.bar.insert(k, bar)

    def take(self, low: float) -> None:
        k = bisect.bisect_right(self.px, low)
        del self.px[k:]
        del self.bar[k:]

    def age(self, i: int) -> None:
        keep = [j for j, b in enumerate(self.bar) if b >= i - POOL_AGE]
        self.px = [self.px[j] for j in keep]
        self.bar = [self.bar[j] for j in keep]

    def below(self, x: float) -> float:
        k = bisect.bisect_left(self.px, x)
        return self.px[k - 1] if k else math.nan


def _add_level(s: Setup, px: float, made: int, tol: float) -> None:
    tol = tol if tol == tol else 0.0
    k = bisect.bisect_left(s.lv_px, px - tol)
    if k < len(s.lv_px) and s.lv_px[k] <= px + tol:
        s.lv_info[k][0] += 1
        if px > s.lv_px[k]:
            s.lv_px[k] = px
            order = sorted(range(len(s.lv_px)), key=s.lv_px.__getitem__)
            s.lv_px[:] = [s.lv_px[j] for j in order]
            s.lv_info[:] = [s.lv_info[j] for j in order]
        return
    s.lv_px.insert(k, px)
    s.lv_info.insert(k, [1, made])


def detect(df: pd.DataFrame) -> tuple[list, dict]:
    """Find every setup and every level-stab ("candidate") on bars in SHORT space."""
    H, L, C = (df[k].to_numpy() for k in ("high", "low", "close"))
    atr = wilder_atr(H, L, C)
    cfg = EngineConfig(
        fib=False, sniper=False, macro=False, internal=False, fvg=False,
        rsi=False, sessions=False, liquidity=True,
    )  # fmt: skip
    stack, eq = EngineStack(cfg), EqualHighsLowsEngine()
    last = {"ext": -(10**9), "named": -(10**9), "int": -(10**9)}
    setups: list = []
    alive: list = []
    pools, named = _Pools(), _Pools()
    cols = {
        k: []
        for k in (
            "bar",
            "setup",
            "entry",
            "low4",
            "pool",
            "named",
            "touches",
            "induced",
            "sos",
            "atr",
        )
    }
    for bar in iter_bars(df):
        i, hi, lo = bar.index, bar.high, bar.low
        st = stack.step(bar)
        ev = eq.update(i, hi, lo, bar.close)
        a_prev = atr[i - 1] if i > 0 else math.nan

        # (a) stabs — priced from state closed by bar i-1
        for s in alive:
            while s.lv_px and s.lv_px[0] <= hi:
                px = s.lv_px.pop(0)
                touches, _made = s.lv_info.pop(0)
                for k, v in (
                    ("bar", i), ("setup", s.id), ("entry", px), ("low4", s.low4),
                    ("pool", pools.below(s.low4)), ("named", named.below(s.low4)),
                    ("touches", touches), ("induced", s.induced), ("sos", s.bear_sos), ("atr", a_prev),
                ):  # fmt: skip
                    cols[k].append(v)

        # (b) deaths — after the stabs, so a bar that fills and runs through the top is a real loss
        keep = []
        for s in alive:
            if hi > s.top or i - s.made > EXPIRY:
                s.dead = i
            else:
                keep.append(s)
        alive = keep

        # (c) this bar's own facts update the armed setups
        x, n = st.structure.external, st.structure.internal
        for s in alive:
            if lo < s.low4:
                s.low4 = lo
            if lo < s.max_plow:
                s.induced = True
            if x.bear_sos:
                s.bear_sos = True
        pools.take(lo)
        named.take(lo)
        if i % 288 == 0:
            pools.age(i)
            named.age(i)

        # (d) new sweeps, pools and swings
        if x.bull_bos:
            last["ext"] = i
        if n.bull_bos or n.bull_sos:
            last["int"] = i
        if st.liquidity is not None:
            for lv in st.liquidity.mitigated:
                if lv.side == "high":
                    last["named"] = i
            for lv in st.liquidity.created:
                if lv.side == "low":
                    named.add(lv.price, i)
        if ev.pivot_low is not None:
            q, pl = i - 2, ev.pivot_low
            pools.add(pl, i)
            for s in alive:
                if q > s.top_bar:
                    s.max_plow = max(s.max_plow, pl)
        if ev.pivot_high is not None:
            p, ph = i - 2, ev.pivot_high
            for s in alive:
                if p > s.top_bar and ph < s.top:
                    _add_level(s, ph, i, 0.25 * a_prev)
            inwin = [k for k in ("ext", "named", "int") if p - SWEEP_LB <= last[k] <= p]
            if inwin:
                j0 = min(last[k] for k in inwin)
                if ph >= H[j0 : p + 1].max() and not any(abs(s.top - ph) < 1e-9 for s in alive):
                    s = Setup(len(setups), ph, p, i, inwin[0], float(L[p + 1 : i + 1].min()))
                    setups.append(s)
                    alive.append(s)
                    if len(alive) > MAX_ALIVE:
                        alive.pop(0).dead = i
    cands = {k: np.array(v) for k, v in cols.items()}
    return setups, cands


# ─────────────────────────────── costs + walk ───────────────────────────────


class Book:
    """One side's raw bars plus everything a trade needs to be priced on them."""

    def __init__(self, raw: pd.DataFrame, side: str, spread: float) -> None:
        self.H, self.L, self.O, self.C = (
            raw[k].to_numpy() for k in ("high", "low", "open", "close")
        )
        self.side = side
        # A short buys back at the ASK: exits need the bid a spread further. A long (mirrored)
        # buys at the ASK: its entry needs the mirrored bid a spread further. Bars are bid.
        self.ex = spread if side == "short" else 0.0
        self.en = spread if side == "long" else 0.0
        self.n = len(self.H)

    def reclaim(self, bar: int, level: float, top: float):
        """The first close back below the level within RECLAIM_WAIT bars of the stab, before the
        top is traded through. Returns (bar, entry price) or None."""
        for j in range(bar, min(bar + RECLAIM_WAIT + 1, self.n - 1)):
            if self.H[j] > top:
                return None
            if self.C[j] < level:
                return j, self.C[j] - self.en
        return None

    def walk(self, i: int, entry: float, stop: float, target: float, force: bool = False):
        """Resolve a short in this side's space. `force=False`: a resting limit filling INSIDE
        bar i, so bar i can stop it but cannot also reach the target (the order within a bar is
        unknown). `force=True`: already filled at the close of bar i-1, so bar i is a full bar."""
        if not force and self.H[i] < entry + self.en:
            return None
        end = min(i + MAX_HOLD, self.n - 1)
        tstart = i if force else i + 1
        hs = np.flatnonzero(self.H[i : end + 1] >= stop - self.ex)
        ts = np.flatnonzero(self.L[tstart : end + 1] <= target - self.ex)
        js = i + int(hs[0]) if len(hs) else None
        jt = tstart + int(ts[0]) if len(ts) else None
        risk = stop - entry
        if js is not None and (jt is None or js <= jt):
            px = stop
            if (force or js > i) and self.O[js] + self.ex > stop:  # gapped through the stop
                px = self.O[js] + self.ex
            return js, (entry - px) / risk, "stop"
        if jt is not None:
            px = min(target, self.O[jt] + self.ex)  # a gap through the target fills better
            return jt, (entry - px) / risk, "target"
        return end, (entry - (self.C[end] + self.ex)) / risk, "time"


def rollovers(index: pd.DatetimeIndex, triple_weekday: int):
    """Swap nights as a cumulative weight at each 17:00 New York rollover (UTC), Mon-Fri, x3 on
    the broker's triple day."""
    days = pd.date_range(
        index[0].normalize() - pd.Timedelta(days=1), index[-1].normalize() + pd.Timedelta(days=2)
    )
    ts, w = [], []
    for d in days:
        if d.weekday() > 4:
            continue
        roll = pd.Timestamp(d.year, d.month, d.day, 17, tz=NY).tz_convert("UTC").tz_localize(None)
        ts.append(roll.to_datetime64())
        w.append(3 if d.weekday() == triple_weekday else 1)
    return np.array(ts), np.concatenate(([0], np.cumsum(w)))


# ─────────────────────────────── grid ───────────────────────────────


@dataclass
class Side:
    name: str
    setups: list
    c: dict  # candidate columns
    book: Book
    top: np.ndarray = None
    range_atr: np.ndarray = None


def build_side(name: str, clean: pd.DataFrame, raw: pd.DataFrame, spread: float) -> Side:
    t0 = time.time()
    setups, c = detect(clean)
    s = Side(name, setups, c, Book(raw, name, spread))
    s.top = np.array([setups[j].top for j in c["setup"]]) if len(c["setup"]) else np.array([])
    with np.errstate(divide="ignore", invalid="ignore"):
        s.range_atr = (s.top - c["low4"]) / c["atr"]
    print(
        f"  {name:>5}: {len(setups):,} tops, {len(c['bar']):,} level stabs  ({time.time() - t0:.0f}s)"
    )
    return s


def targets(side: Side, mode: str) -> np.ndarray:
    low4 = side.c["low4"]
    if mode == "4":
        return low4
    pool = side.c["pool" if mode == "pool" else "named"]
    ok = ~np.isnan(pool) & ((low4 - pool) <= POOL_GAP * (side.top - low4))
    return np.where(ok, pool, low4)


def simulate(sides: list, cell: dict, costs: dict, cache: dict) -> list:
    """Chronological one-slot replay of every candidate that passes this cell's rules."""
    rows = []
    for si, s in enumerate(sides):
        c = s.c
        if not len(c["bar"]):
            continue
        tgt = targets(s, cell["target"])
        stop = s.top + BUFFER * c["atr"]
        risk, reward = stop - c["entry"], c["entry"] - tgt
        with np.errstate(divide="ignore", invalid="ignore"):
            rr = np.where(risk > 0, reward / risk, -1.0)
        m = c["induced"] & (c["touches"] >= cell["touches"]) & (reward > 0) & (risk > 0)
        m &= ~np.isnan(c["atr"]) & (rr >= cell["floor"]) & (s.range_atr >= cell["min_range"])
        if cell["need_sos"]:
            m &= c["sos"]
        for k in np.flatnonzero(m):
            rows.append(
                (
                    int(c["bar"][k]),
                    float(c["entry"][k]),
                    -int(c["setup"][k]),
                    si,
                    int(k),
                    float(stop[k]),
                    float(tgt[k]),
                )
            )
    rows.sort()
    trades, traded, free = [], set(), -1
    for bar, level, negsid, si, k, stop, tgt in rows:
        key = (si, -negsid)
        if key in traded or bar <= free:
            continue
        side = sides[si]
        a = float(side.c["atr"][k])
        # 🔴 KEYED ON THE SIDE'S NAME, NEVER ITS POSITION IN `sides`. A "long" run puts the long book
        # at index 0, where "both" and "short" keep the short one, so a positional key handed each
        # direction the other's cached trades — found 2026-09-14 when a cell re-scored alone gave
        # 1,108 trades against the grid's 1,089 for identical rules. The numbers still looked like
        # numbers. The owner stored in the value is checked on every read.
        ck = (side.name, k, cell["target"], cell["entry"])
        if ck not in cache:
            if cell["entry"] == "stab":
                cache[ck] = (side.name, bar, level, side.book.walk(bar, level, stop, tgt))
            else:
                rc = side.book.reclaim(bar, level, float(side.top[k]))
                walk = side.book.walk(rc[0] + 1, rc[1], stop, tgt, force=True) if rc else None
                cache[ck] = (side.name, rc[0] if rc else -1, rc[1] if rc else math.nan, walk)
        owner, ebar, entry, res = cache[ck]
        if owner != side.name:
            raise RuntimeError(f"a cached trade crossed sides: {owner} read as {side.name}")
        if res is None:
            continue
        xbar, r_gross, outcome = res
        if ebar <= free:
            continue
        risk = stop - entry
        rr = (entry - tgt) / risk
        if rr < cell["floor"] or risk < cell["min_risk"] * a:
            continue
        traded.add(key)
        free = xbar
        nights = (
            costs["cum"][np.searchsorted(costs["roll"], costs["t"][xbar], "right")]
            - costs["cum"][np.searchsorted(costs["roll"], costs["t"][ebar], "right")]
        )
        swap_pts = costs["swap_short"] if side.name == "short" else costs["swap_long"]
        swap_r = nights * swap_pts * POINT / risk
        comm_r = costs["comm_rt"] / (risk * costs["contract"])
        trades.append(dict(
            side=side.name, bar=ebar, xbar=xbar, entry=entry, stop=stop, target=tgt, rr=rr,
            r_gross=r_gross, r=r_gross - comm_r + swap_r, swap_r=swap_r, outcome=outcome,
            risk_atr=risk / a, range_atr=float(side.range_atr[k]), setup=-negsid,
        ))  # fmt: skip
    return trades


def stats(trades: list, split: int, months: float) -> dict:
    if not trades:
        return dict(
            n=0,
            win=0.0,
            avg_g=0.0,
            avg=0.0,
            tot=0.0,
            pf=0.0,
            dd=0.0,
            h1=0.0,
            h2=0.0,
            n1=0,
            n2=0,
            pm=0.0,
            rr=0.0,
            t_stat=0.0,
        )
    r = np.array([t["r"] for t in trades])
    wins = sum(t["outcome"] == "target" for t in trades)
    eq = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(np.concatenate(([0.0], eq)))[1:] - eq))
    first = np.array([t["bar"] < split for t in trades])
    gp, gl = r[r > 0].sum(), -r[r < 0].sum()
    sd = r.std(ddof=1) if len(r) > 1 else 0.0
    return dict(
        n=len(r), win=wins / len(r) * 100, avg_g=float(np.mean([t["r_gross"] for t in trades])),
        avg=r.mean(), tot=r.sum(), pf=gp / gl if gl else math.inf, dd=dd,
        h1=r[first].sum(), h2=r[~first].sum(), n1=int(first.sum()), n2=int((~first).sum()),
        pm=len(r) / months, rr=float(np.mean([t["rr"] for t in trades])),
        t_stat=r.mean() / (sd / math.sqrt(len(r))) if sd else 0.0,
    )  # fmt: skip


def control(sides: list, trades: list, reps: int = 20, seed: int = 7) -> dict:
    """Random entries matched on DIRECTION, STOP DISTANCE and TARGET DISTANCE; only the entry bar
    is random. Gold ran ~1,500 -> ~4,700 over this window, so an unmatched result is worthless."""
    rng = np.random.default_rng(seed)
    by = {s.name: s for s in sides}
    rs, hits = [], 0
    for t in trades:
        b = by[t["side"]].book
        risk, reward = t["stop"] - t["entry"], t["entry"] - t["target"]
        for _ in range(reps):
            j = int(rng.integers(60, b.n - MAX_HOLD - 2))
            e = b.C[j] - b.en
            res = b.walk(j + 1, e, e + risk, e - reward, force=True)
            rs.append(res[1])
            hits += res[2] == "target"
    return dict(avg=float(np.mean(rs)), win=hits / len(rs) * 100, n=len(rs))


# ─────────────────────────────── report ───────────────────────────────


def fmt_row(label: str, st: dict) -> str:
    return (
        f"{label:<46} {st['n']:>5} {st['pm']:>5.1f} {st['win']:>5.1f}% {st['rr']:>5.2f} {st['avg_g']:>+7.3f} {st['avg']:>+7.3f} "
        f"{st['tot']:>+8.1f} {st['pf']:>5.2f} {st['dd']:>6.1f} {st['h1']:>+7.1f} {st['h2']:>+7.1f} {st['t_stat']:>+5.2f}"
    )


HEAD = f"{'':<46} {'n':>5} {'/mo':>5} {'win':>6} {'RR':>5} {'gross':>7} {'net R':>7} {'total R':>8} {'PF':>5} {'maxDD':>6} {'1st½':>7} {'2nd½':>7} {'t':>5}"


def label(cell: dict) -> str:
    return (
        f"{cell['dir']} {cell['entry']} {cell['target']} f{cell['floor']} risk>={cell['min_risk']:g} "
        f"range>={cell['min_range']:g} t{cell['touches']} sos{int(cell['need_sos'])}"
    )


def recall(side: Side, index: pd.DatetimeIndex) -> None:
    print("\nRECALL — does the detector find the user's seven trades? (short side, real prices)")
    c = side.c
    named = targets(side, "named")
    for name, top_px, fill_utc, entry in EXAMPLES:
        fb = int(index.searchsorted(pd.Timestamp(fill_utc)))
        hits = [
            s
            for s in side.setups
            if abs(s.top - top_px) <= 0.6 and s.made <= fb and (s.dead == -1 or s.dead >= fb)
        ]
        if not hits:
            near = [s for s in side.setups if abs(s.top - top_px) <= 0.6]
            why = f"top seen but dead at {index[near[0].dead]}" if near else "top never armed"
            print(f"  {name}: ✗ {why}")
            continue
        s = hits[-1]
        print(
            f"  {name}: top {s.top:.2f} armed ({s.kind} sweep), made {index[s.made]:%d %b %H:%M} UTC"
        )
        ks = np.flatnonzero(c["setup"] == s.id)
        at = [k for k in ks if abs(c["bar"][k] - fb) <= 3 and abs(c["entry"][k] - entry) <= 3.0]
        if not at:
            print(f"      ✗ no level stab within 3 bars / 3.00 of the user's entry {entry}")
        for k in at:
            a = c["atr"][k]
            stop = s.top + BUFFER * a
            print(
                f"      ✓ stab {index[c['bar'][k]]:%H:%M} at {c['entry'][k]:.2f} (user {entry}), touches {c['touches'][k]}, "
                f"SOS after top {bool(c['sos'][k])} | stop {((stop - c['entry'][k]) / a):.1f} ATR, top-to-4 {side.range_atr[k]:.1f} ATR "
                f"| RR to 4 {(c['entry'][k] - c['low4'][k]) / (stop - c['entry'][k]):.2f}, to named {(c['entry'][k] - named[k]) / (stop - c['entry'][k]):.2f}"
            )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-dir", default="PUPrime_Demo")
    ap.add_argument("--symbol", default="XAUUSD_p")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2026-09-12")
    ap.add_argument("--profile", default="puprime_ecn")
    ap.add_argument("--recall-only", action="store_true")
    ap.add_argument("--out", default="backtest/reports/loaded_level_study")
    args = ap.parse_args()

    prof = PROFILES[args.profile]
    sw = prof.swap
    costs = dict(
        comm_rt=2 * prof.commission_per_side_per_lot, contract=prof.contract_size,
        swap_long=sw.swap_long_points, swap_short=sw.swap_short_points,
    )  # fmt: skip
    if args.recall_only:
        args.start = "2026-06-15"
    raw = load_bars(args.server_dir, args.symbol, args.start, args.end)
    clean, fixed = clean_reopens(raw)
    print(
        f"{len(raw):,} M5 bars {raw.index[0]:%Y-%m-%d} -> {raw.index[-1]:%Y-%m-%d} ({args.server_dir}/{args.symbol}); "
        f"profile {args.profile}: spread {prof.spread}, commission {prof.commission_per_side_per_lot}/side/lot, "
        f"swap {sw.swap_long_points}/{sw.swap_short_points} pts; {len(fixed)} reopen-bar spikes clipped for detection"
    )
    costs["t"] = raw.index.to_numpy()
    costs["roll"], costs["cum"] = rollovers(raw.index, sw.triple_weekday)

    short = build_side("short", clean, raw, prof.spread)
    recall(short, raw.index)
    if args.recall_only:
        return
    long_ = build_side("long", mirror(clean), mirror(raw), prof.spread)
    sides = {"short": [short], "long": [long_], "both": [short, long_]}

    split = int(len(raw) // 2)
    months = (raw.index[-1] - raw.index[0]).days / 30.44
    print(f"halves split at {raw.index[split]:%Y-%m-%d}")
    cache: dict = {}
    results = []
    t0 = time.time()
    for tg, fl, en, mr, mg, tc, sos, d in itertools.product(
        TARGETS, FLOORS, ENTRIES, MIN_RISK, MIN_RANGE, TOUCHES, NEED_SOS, DIRS
    ):
        cell = dict(
            target=tg,
            floor=fl,
            entry=en,
            min_risk=mr,
            min_range=mg,
            touches=tc,
            need_sos=sos,
            dir=d,
        )
        tr = simulate(sides[d], cell, costs, cache)
        results.append((cell, stats(tr, split, months), tr))
    print(f"{len(results):,} cells in {time.time() - t0:.0f}s")

    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    with (out / f"grid_{args.profile}.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(list(results[0][0]) + list(results[0][1]))
        for cell, st, _ in results:
            w.writerow(list(cell.values()) + list(st.values()))

    def find(**kw):
        for cell, st, tr in results:
            if all(cell[k] == v for k, v in kw.items()):
                return cell, st, tr
        raise KeyError(kw)

    print(
        f"\nTHE QUESTION ASKED — reward floor x target x entry, sized like the user's trades {FAITHFUL}, costs charged"
    )
    print(HEAD)
    for d in DIRS:
        for en in ENTRIES:
            for tg in TARGETS:
                for fl in FLOORS:
                    _, st, _ = find(target=tg, floor=fl, entry=en, dir=d, **FAITHFUL)
                    print(fmt_row(f"{d:<5} {en:<7} target {tg:<5} floor {fl:.1f}", st))
            print()

    ranked = sorted(
        (r for r in results if r[1]["n1"] >= 20 and r[1]["n2"] >= 20),
        key=lambda r: -min(r[1]["h1"], r[1]["h2"]),
    )
    print("TOP 15 BY THE WORSE HALF (each half >= 20 trades)")
    print(HEAD)
    for cell, st, _ in ranked[:15]:
        print(fmt_row(label(cell), st))

    if ranked:
        best = ranked[0][0]
        print("\nNEIGHBOURS OF #1 — one setting moved at a time")
        print(HEAD)
        for axis, vals in (
            ("floor", FLOORS),
            ("target", TARGETS),
            ("entry", ENTRIES),
            ("min_risk", MIN_RISK),
            ("min_range", MIN_RANGE),
            ("touches", TOUCHES),
            ("need_sos", NEED_SOS),
            ("dir", DIRS),
        ):
            for v in vals:
                kw = dict(best)
                kw[axis] = v
                _, st, _ = find(**kw)
                print(fmt_row(f"{axis}={v}" + ("   <- #1" if v == best[axis] else ""), st))
            print()

    print("CONTROL — random entries matched on direction, stop and target distance (20 per trade)")
    shortlist = list(ranked[:3]) + [
        find(target=tg, floor=fl, entry=en, dir="both", **FAITHFUL)
        for en in ENTRIES
        for tg in ("4", "named")
        for fl in (1.0, 2.0)
    ]
    for cell, st, tr in shortlist:
        if not tr:
            continue
        ctl = control(sides[cell["dir"]], tr)
        print(
            f"  {label(cell):<66} real win {st['win']:5.1f}% avg {st['avg_g']:+.3f}R gross | random win {ctl['win']:5.1f}% avg {ctl['avg']:+.3f}R"
        )

    for tag, (cell, st, tr) in (
        ("#1", ranked[0] if ranked else None),
        (
            "best-faithful",
            max(
                (
                    find(target=tg, floor=fl, entry=en, dir=d, **FAITHFUL)
                    for d in DIRS
                    for en in ENTRIES
                    for tg in TARGETS
                    for fl in FLOORS
                ),
                key=lambda r: min(r[1]["h1"], r[1]["h2"]),
            ),
        ),
    ):
        if not tr:
            continue
        years = pd.Series([t["r"] for t in tr], index=[raw.index[t["bar"]].year for t in tr])
        print(
            f"\n{tag} {label(cell)} BY YEAR (R net): "
            + "  ".join(
                f"{y} {v:+.1f} ({(years.index == y).sum()})"
                for y, v in years.groupby(level=0).sum().items()
            )
        )
        with (out / f"trades_{tag.strip('#')}_{args.profile}.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "side",
                    "entry_time",
                    "exit_time",
                    "entry",
                    "stop",
                    "target",
                    "rr",
                    "outcome",
                    "r_gross",
                    "swap_r",
                    "r_net",
                    "risk_atr",
                    "range_atr",
                ]
            )
            for t in tr:
                w.writerow(
                    [
                        t["side"],
                        raw.index[t["bar"]],
                        raw.index[t["xbar"]],
                        f"{t['entry']:.2f}",
                        f"{t['stop']:.2f}",
                        f"{t['target']:.2f}",
                        f"{t['rr']:.2f}",
                        t["outcome"],
                        f"{t['r_gross']:.3f}",
                        f"{t['swap_r']:.3f}",
                        f"{t['r']:.3f}",
                        f"{t['risk_atr']:.2f}",
                        f"{t['range_atr']:.1f}",
                    ]
                )
    print(f"\nwrote {out.relative_to(ROOT)}/grid_{args.profile}.csv")


if __name__ == "__main__":
    main()
