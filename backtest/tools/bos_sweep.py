#!/usr/bin/env python3
"""bos_sweep.py — measure mpc_bos_strategy.pine over the full bar cache.

🔴 FALSIFIED 2026-08-07, THE DAY IT WAS WRITTEN. DO NOT QUOTE ITS NUMBERS.

Same symbol, same timeframe, same window, config confirmed identical by the Pine's own [CFG] echo:

                        this tool      TradingView Strategy Tester
    trades                     20                             24
    win rate                80.0%                         66.67%
    profit factor            2.97                           1.04
    return @10% risk      +102.5%                         +5.01%

The Strategy Tester is the ground truth. ENTRIES ROUGHLY AGREE (20 vs 24); THE EXIT LADDER DOES
NOT — this model averages +0.73R per win against a -1.02R loss, while the Tester's 66.67% win rate
at PF 1.043 implies winners roughly HALF the size of losers. The fault is somewhere in the staged
stop, the structure trail, or how the position leaves at TP3.

It is kept because the METHOD is sound and reusable and fixing it is cheaper than rewriting it.
Every result HERE is still unverified, and the 2026-08-07 parity green does NOT change that.
`strategies/python/mpc_bos/tools/compare_bos.py` now exits 0 against a real export — but it
validates `strategies/python/mpc_bos/`, which is a DIFFERENT implementation from this file's
model. Nothing has re-checked this tool since the Strategy Tester falsified it. Use the ported
strategy for anything that has to be right. (This line named `backtest/tools/compare_bos.py`
until 2026-08-07; a parity harness belongs to the STRATEGY, beside `compare_strategy.py` and
`compare_bleg.py`, not to this package.)
Full record: docs/MPC_BOS_OPTIMIZATION.md -> Run 8.

⚠ The docstring below already said this was a MODEL rather than the strategy. That was true, it
was not enough, and the reason is worth carrying: a table of numbers reads as a finding no matter
what sentence sits under it. The check that falsified this was ONE Strategy Tester run.


This is the tool that chose the defaults `indicators/strategies/mpc_bos_strategy.pine` ships with today
(2026-08-07, Run 7 in `docs/MPC_BOS_OPTIMIZATION.md`). It exists so that answer is reproducible
rather than asserted.

    python backtest/tools/bos_sweep.py sensitivity   # one lever at a time from the shipped config
    python backtest/tools/bos_sweep.py grid          # the full cartesian, half-split ranked
    python backtest/tools/bos_sweep.py frontier      # ranked at a MATCHED drawdown budget
    python backtest/tools/bos_sweep.py settle        # paired jitter head-to-head of the finalists

⚠ FOUR THINGS IT DOES THAT A NAIVE SWEEP DOES NOT, EACH OF WHICH CHANGED THE ANSWER.

  1. ONE POSITION SLOT. The Pine is a `strategy()`; it holds one position. Scoring every setup
     independently counts trades the strategy could never have taken and lets a winner and the
     trade it would have blocked BOTH score. With a slot a marginal setup is a QUEUE, not an
     addition — this repo has measured that twice (Run 12, the min-stop guard) and both times the
     cheap estimate had the SIGN wrong.

  2. REAL COSTS. Spread $0.22 (Vantage, measured on 1,494,459 ticks) and swap charged per NIGHT
     HELD (long -74.84 points, short +26.98, triple Wednesday). Swap is the biggest cost here and
     gold's SHORT swap is a CREDIT — a model that abs()es it cannot see that, and this repo booked
     exactly that credit as a charge once already.

  3. A STOP THE BAR CAN RESOLVE. R = profit / stop, so shrinking the stop inflates every R in the
     book without one extra dollar being made. The old fib-1.0 default's tightest tenth of stops
     is $0.64 wide, where the spread is 34% of R and a 15-minute bar's low simply cannot say
     whether it was touched. Every ranking mode reports the tightest-tenth stop and the spread as
     a share of R there, and `frontier` refuses rows that fail it. Ignoring this put a book with a
     median 74-cent stop at the top of the first leaderboard, by a distance.

  4. A MATCHED DRAWDOWN BUDGET. Summing R treats a 25R drawdown as three times worse than an 8R
     one; at 10% risk it is the difference between giving back 30% and giving back 93%. So
     configurations are compared at the risk fraction that produces the SAME peak-to-trough
     percentage, which is the only way a 55-trade book and a 600-trade one can be ranked together.

⚠ AND THE ONE THAT DECIDES CLOSE CALLS: the multiple-at-a-drawdown-budget is NOISY — a factor of
two across jitter seeds on one configuration. `settle` therefore scores every finalist on THE SAME
jittered series and compares pairwise, which is what separated the shipped default from the ATR
stop after the unpaired medians had them tied.

⚠ Look-ahead traps that are deliberately avoided, both of which were made and caught here:
the VWAP side is read off the PREVIOUS closed bar (reading it off the fill bar's own close selects
bars that recovered and was worth a fake +9%), and the FILL BAR MAY NOT STAGE THE STOP — a resting
limit is reached by price coming to it from the wrong side, so the fill bar's favourable extreme is
the approach to the order, not a move the trade made. That is BUG_exit_fill_price_mismatch.
"""

from __future__ import annotations

import csv
import itertools
import multiprocessing as mp
import random
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path("/Users/millionairekelly/trading")
sys.path.insert(0, str(ROOT / "engines"))
from market_structure import Bar, StructureEngine  # noqa: E402
from vwap import VwapEngine  # noqa: E402

CACHE = ROOT / "backtest" / "cache" / "XAUUSD__M15.csv"
HORIZON = 1200  # bars a trade may stay open before it is marked to market
MINTICK = 0.01
BE_BUF = 30 * MINTICK
STRUCT_BUF = 20 * MINTICK

SPREAD = 0.22  # Vantage XAUUSD, repo-measured on 1,494,459 ticks
SWAP_LONG_PTS = -74.84  # Vantage demo, read off the live terminal 2026-07-22
SWAP_SHORT_PTS = 26.98
TRIPLE_WEEKDAY = 2  # Wednesday, Monday-based

SPLIT_TS = int(datetime(2022, 8, 1, tzinfo=timezone.utc).timestamp() * 1000)

FIBS = {
    "0.382": 0.382,
    "0.5": 0.5,
    "0.618": 0.618,
    "0.702": 0.702,
    "0.786": 0.786,
    "0.886": 0.886,
    "1.0": 1.0,
}


@dataclass
class Row:
    i: int
    ts: int
    o: float
    h: float
    l: float
    c: float
    v: float


def load():
    rows = []
    with CACHE.open() as f:
        for r in csv.DictReader(f):
            t = datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            rows.append(
                Row(
                    0,
                    int(t.timestamp() * 1000),
                    float(r["open"]),
                    float(r["high"]),
                    float(r["low"]),
                    float(r["close"]),
                    float(r["volume"] or 0),
                )
            )
    # drop the coarser-than-M15 prefix the broker serves where it has no real M15 history
    start = 0
    for k in range(len(rows) - 1, 0, -1):
        if (rows[k].ts - rows[k - 1].ts) // 60000 > 15:
            w = rows[max(0, k - 200) : k]
            g = [(w[j].ts - w[j - 1].ts) // 60000 for j in range(1, len(w))]
            if g and statistics.median(g) > 15:
                start = k
                break
    out = rows[start:]
    for n, r in enumerate(out):
        r.i = n
    return out


def prescan(rows):
    """Everything a configuration might need, computed ONCE. 186k bars through two engines is the
    expensive part; after this a whole configuration costs milliseconds."""
    st, vw = StructureEngine(), VwapEngine()
    n = len(rows)
    legs = [None] * n
    vside = [0] * n
    swlo = [None] * n
    swhi = [None] * n
    atr = [0.0] * n
    nyhour = [0] * n

    prev_c = rows[0].c
    a = rows[0].h - rows[0].l
    trend = ordinal = 0
    since_shift = 0
    prevside = 0

    for r in rows:
        tr = max(r.h - r.l, abs(r.h - prev_c), abs(r.l - prev_c))
        a = tr if r.i == 0 else (a * 13 + tr) / 14
        atr[r.i] = a
        prev_c = r.c

        e = st.update(Bar(r.i, r.o, r.h, r.l, r.c)).external
        vwap = vw.update(r.i, r.ts, r.h, r.l, r.c, r.v).value
        vside[r.i] = prevside  # PREVIOUS closed bar — no look-ahead
        lo, hi = st.last_confirmed_low, st.last_confirmed_high
        swlo[r.i] = lo.price if lo else None
        swhi[r.i] = hi.price if hi else None

        dt = datetime.fromtimestamp(r.ts / 1000, timezone.utc)
        nyhour[r.i] = (dt.hour - 4) % 24  # NY = UTC-4 (EDT); good enough for a late-day gate

        if e.bull_sos or e.bear_sos:
            trend, ordinal, since_shift = (1 if e.bull_sos else -1), 0, 0
        elif e.bull_bos and trend == 1 and e.bull_bos_low is not None:
            ordinal += 1
            legs[r.i] = (1, e.bull_bos_low, e.bull_bos_high, ordinal, r.c, e.bull_bos_high, a)
        elif e.bear_bos and trend == -1 and e.bear_bos_low is not None:
            ordinal += 1
            legs[r.i] = (-1, e.bear_bos_low, e.bear_bos_high, ordinal, r.c, e.bear_bos_low, a)

        prevside = 0 if vwap is None else (1 if r.c > vwap else -1 if r.c < vwap else 0)

    return dict(legs=legs, vside=vside, swlo=swlo, swhi=swhi, atr=atr, nyhour=nyhour)


def nights(ts_in: int, ts_out: int) -> float:
    """Swap-charging nights between two bars, triple on Wednesday. A rollover is a DATE boundary,
    so this counts dates crossed rather than dividing a duration."""
    d0 = datetime.fromtimestamp(ts_in / 1000, timezone.utc).date()
    d1 = datetime.fromtimestamp(ts_out / 1000, timezone.utc).date()
    tot = 0.0
    d = d0
    while d < d1:
        d += timedelta(days=1)
        tot += 3.0 if d.weekday() == TRIPLE_WEEKDAY else 1.0
    return tot


def run(rows, pre, cfg):
    """One configuration, one pass. Returns a list of (entry_bar, R_net, stop_dist, dir)."""
    legs, vside, swlo, swhi, atr, nyhour = (
        pre["legs"],
        pre["vside"],
        pre["swlo"],
        pre["swhi"],
        pre["atr"],
        pre["nyhour"],
    )
    ef = FIBS[cfg["entry"]]
    sf = cfg["stop"]  # "1.0" | "0.886" | "swing" | ("atr", mult)
    t1f, t2f = cfg["tp1f"], cfg["tp2f"]
    sizes = cfg["sizes"]
    max_bars = int(cfg["max_days"] * 96)
    which = cfg["which"]  # max ordinal accepted
    use_vwap = cfg["vwap"]
    min_disp = cfg["min_disp"]  # x ATR the break close must clear the level by
    min_leg = cfg["min_leg"]  # x ATR the leg must span
    late = cfg["late"]  # block new entries 16:00-18:00 NY
    per_regime = cfg["per_regime"]
    trail = cfg["trail"]
    tp2mode = cfg["tp2mode"]  # "tp1" | "be"
    dirs = cfg["dirs"]  # 1 longs only, -1 shorts only, 0 both
    min_stop_pct = cfg["min_stop_pct"]  # refuse a setup whose stop is under this % of price

    out = []
    pend = None
    open_tr = None
    fills_since_shift = 0

    for r in rows:
        i = r.i

        # ---- manage an open position first; the slot is what makes this a strategy ----
        if open_tr is not None:
            d, entry, risk, cur, t1, t2, t3, booked, left, stage, ib = open_tr
            done = None
            hit = (r.l <= cur) if d == 1 else (r.h >= cur)
            if hit:
                done = booked + left * (d * (cur - entry)) / risk
            else:
                for lvl, sz, need in ((t1, sizes[0], 1), (t2, sizes[1], 2), (t3, sizes[2], 3)):
                    reached = (r.h >= lvl) if d == 1 else (r.l <= lvl)
                    if reached:
                        if stage < need and sz > 0:
                            take = min(sz, left)
                            booked += take * (d * (lvl - entry)) / risk
                            left -= take
                        if stage < need:
                            stage = need
                if left <= 1e-9:
                    done = booked
                elif i - ib >= HORIZON:
                    done = booked + left * (d * (r.c - entry)) / risk
                else:
                    if stage >= 2:
                        floor_ = t1 if tp2mode == "tp1" else entry + d * BE_BUF
                        if trail:
                            sw = swlo[i] if d == 1 else swhi[i]
                            if sw is not None:
                                tr_ = sw - STRUCT_BUF if d == 1 else sw + STRUCT_BUF
                                floor_ = max(floor_, tr_) if d == 1 else min(floor_, tr_)
                        cur = max(cur, floor_) if d == 1 else min(cur, floor_)
                    elif stage >= 1:
                        be = entry + d * BE_BUF
                        cur = max(cur, be) if d == 1 else min(cur, be)
                    open_tr = (d, entry, risk, cur, t1, t2, t3, booked, left, stage, ib)
            if done is not None:
                gross = done
                sp = SPREAD / risk
                pts = SWAP_LONG_PTS if d == 1 else SWAP_SHORT_PTS
                # swap in R: (pts * $1/pt/lot * lots) / (risk * lots * 100)
                sw_r = (pts * nights(rows[ib].ts, r.ts)) / (risk * 100.0)
                # target DISTANCES travel with the trade so a control can reproduce its geometry
                out.append(
                    (
                        ib,
                        gross - sp + sw_r,
                        risk,
                        d,
                        gross,
                        (abs(t1 - entry), abs(t2 - entry), abs(t3 - entry)),
                    )
                )
                open_tr = None

        # ---- a resting limit, only while the slot is free ----
        if pend is not None:
            d, lo, hi, armed, ordn = pend
            span = hi - lo
            if i - armed > max_bars or span <= 0:
                pend = None
            else:
                ext, org = (hi, lo) if d == 1 else (lo, hi)
                lvl = lambda v: ext + (org - ext) * v  # noqa: E731
                zone = lvl(ef)
                dead = (r.c < org) if d == 1 else (r.c > org)
                touched = (r.l <= zone) if d == 1 else (r.h >= zone)
                if dead:
                    pend = None
                elif touched:
                    ok = open_tr is None
                    if ok and use_vwap and vside[i] != d:
                        ok = False
                    if ok and dirs != 0 and dirs != d:
                        ok = False
                    if ok and late and 16 <= nyhour[i] < 18:
                        ok = False
                    if ok and per_regime and fills_since_shift >= per_regime:
                        ok = False
                    if ok:
                        if sf == "1.0":
                            stop = lvl(1.0)
                        elif sf == "0.886":
                            stop = lvl(0.886)
                        elif sf == "swing":
                            sw = swlo[i] if d == 1 else swhi[i]
                            stop = sw if sw is not None else lvl(1.0)
                        else:
                            stop = zone - d * sf[1] * atr[i]
                        risk = abs(zone - stop)
                        if risk <= 0 or (d == 1 and stop >= zone) or (d == -1 and stop <= zone):
                            ok = False
                        elif min_stop_pct and risk < zone * min_stop_pct / 100.0:
                            ok = False
                    if ok:
                        t1, t2, t3 = lvl(t1f), lvl(t2f), lvl(0.0)
                        open_tr = (d, zone, risk, stop, t1, t2, t3, 0.0, 1.0, 0, i)
                        fills_since_shift += 1
                    pend = None

        # ---- a new break replaces whatever was waiting ----
        lg = legs[i]
        if lg is not None:
            d, lo, hi, ordn, bclose, blevel, batr = lg
            if ordn == 1:
                fills_since_shift = 0
            keep = ordn <= which
            if keep and min_disp and abs(bclose - blevel) < min_disp * batr:
                keep = False
            if keep and min_leg and (hi - lo) < min_leg * batr:
                keep = False
            if keep:
                pend = (d, lo, hi, i, ordn)
    return out


def score(evs, rows, lo_ts=None, hi_ts=None):
    sel = [
        e
        for e in evs
        if (lo_ts is None or rows[e[0]].ts >= lo_ts) and (hi_ts is None or rows[e[0]].ts < hi_ts)
    ]
    if len(sel) < 2:
        return None
    rs = [e[1] for e in sel]
    n = len(rs)
    gp = sum(r for r in rs if r > 0)
    gl = abs(sum(r for r in rs if r < 0))
    peak = cum = dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    mean = sum(rs) / n
    sd = (sum((x - mean) ** 2 for x in rs) / (n - 1)) ** 0.5 if n > 1 else 0.0
    t = mean / (sd / n**0.5) if sd > 0 else 0.0
    stops = sorted(e[2] for e in sel)
    return dict(
        n=n,
        sum=sum(rs),
        exp=mean,
        pf=(gp / gl if gl else 99.0),
        dd=dd,
        t=t,
        med_stop=statistics.median(stops),
        p10_stop=stops[max(0, int(0.10 * len(stops)) - 1)],
        # what the spread costs on the TIGHTEST tenth, which is where a stop model breaks
        worst_sprd=100.0 * 0.22 / stops[max(0, int(0.10 * len(stops)) - 1)],
    )


# ---------------------------------------------------------------------------------------------
# Ranking modes. Everything above is measurement; everything below is how a measurement is READ.
# ---------------------------------------------------------------------------------------------

SHIPPED = dict(
    entry="0.786",
    stop=("atr", 1.3),
    tp1f=0.5,
    tp2f=0.382,
    sizes=(0.0, 0.0, 1.0),
    max_days=3.0,
    which=99,
    vwap=True,
    min_disp=0.0,
    min_leg=0.0,
    late=True,
    per_regime=0,
    trail=True,
    tp2mode="tp1",
    dirs=0,
    min_stop_pct=0.10,
)

# what `mpc_bos_strategy.pine` shipped before Run 7, kept so the improvement stays checkable
PRE_RUN7 = dict(SHIPPED, stop="1.0", min_stop_pct=0.0)

RISK = 0.10
_R = _P = None


def _init():
    global _R, _P
    _R, _P = None, None
    _R = load()
    _P = prescan(_R)


def compound(evs, risk=RISK):
    """Terminal multiple and peak-to-trough % at fixed-fractional risk. Path-dependent, so it is
    walked in order — a sum of R cannot produce it."""
    bal = peak = 1.0
    dd = 0.0
    for e in sorted(evs, key=lambda x: x[0]):
        bal *= 1.0 + risk * e[1]
        if bal <= 0:
            return 0.0, 1.0
        peak = max(peak, bal)
        dd = max(dd, 1.0 - bal / peak)
    return bal, dd


def risk_for_dd(evs, target=0.25):
    """The risk fraction that spends exactly `target` of drawdown. Drawdown is monotone in risk
    for a fixed trade list, so the bisection is well defined."""
    lo, hi = 0.0005, 0.60
    if compound(evs, hi)[1] < target:
        return hi, compound(evs, hi)[0]
    for _ in range(40):
        mid = (lo + hi) / 2
        if compound(evs, mid)[1] > target:
            hi = mid
        else:
            lo = mid
    return lo, compound(evs, lo)[0]


def halves(rows, evs):
    return (
        [e for e in evs if rows[e[0]].ts < SPLIT_TS],
        [e for e in evs if rows[e[0]].ts >= SPLIT_TS],
    )


def jitter_rows(seed):
    """A full replay on a jittered series. ONE offset per BAR applied to all four prices —
    independent per-price noise would build candles no feed can produce, and a CONSTANT offset
    would flip nothing because the whole fib ladder translates with it."""
    rng = random.Random(seed)
    rows = load()
    for r in rows:
        off = rng.uniform(-0.05, 0.05)
        r.o += off
        r.h += off
        r.l += off
        r.c += off
    return rows


def _line(tag, rows, evs, budget=0.25):
    a = score(evs, rows)
    if a is None:
        print(f"{tag:<46} none")
        return
    A, B = halves(rows, evs)
    _, m = risk_for_dd(evs, budget)
    mA = risk_for_dd(A, budget)[1] if len(A) > 3 else 0.0
    mB = risk_for_dd(B, budget)[1] if len(B) > 3 else 0.0
    print(
        f"{tag:<46}n={a['n']:>4} {a['sum']:>+7.1f}R exp{a['exp']:>+6.3f} PF{a['pf']:>5.2f} "
        f"t{a['t']:>5.2f} | {m:>7.1f}x  A{mA:>6.1f}x B{mB:>6.1f}x | "
        f"stop ${a['med_stop']:>6.2f} p10 ${a['p10_stop']:>5.2f} sprd{a['worst_sprd']:>5.1f}%"
    )


def cmd_sensitivity():
    _init()
    print(
        f"{len(_R)} true-M15 bars  "
        f"{datetime.fromtimestamp(_R[0].ts / 1000, timezone.utc):%Y-%m-%d} -> "
        f"{datetime.fromtimestamp(_R[-1].ts / 1000, timezone.utc):%Y-%m-%d}"
    )
    print("multiples are at whatever risk % produces a 25% peak-to-trough drawdown\n")
    _line("BEFORE Run 7 (fib 1.0, no stop floor)", _R, run(_R, _P, PRE_RUN7))
    _line("SHIPPED TODAY (ATR 1.3 + 0.10% floor)", _R, run(_R, _P, SHIPPED))
    print("\n-- one lever at a time from the shipped configuration --")
    SW = {
        "entry": ["0.382", "0.5", "0.618", "0.702", "0.786", "0.886"],
        "stop": ["1.0", "0.886", "swing", ("atr", 1.0), ("atr", 1.3), ("atr", 1.75), ("atr", 2.5)],
        "which": [1, 2, 3, 99],
        "vwap": [True, False],
        "min_stop_pct": [0.0, 0.05, 0.08, 0.10, 0.15],
        "sizes": [
            (0.0, 0.0, 1.0),
            (0.3, 0.3, 0.2),
            (0.5, 0.5, 0.0),
            (1.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.5, 0.5),
        ],
        "min_disp": [0.0, 0.25, 0.5],
        "max_days": [0.5, 1.0, 3.0, 10.0],
        "late": [True, False],
        "tp2mode": ["tp1", "be"],
        "dirs": [0, 1, -1],
    }
    for k, vals in SW.items():
        print(f"\n  {k}:")
        for v in vals:
            c = dict(SHIPPED)
            c[k] = v
            _line(f"   {v}{' *' if v == SHIPPED[k] else '  '}", _R, run(_R, _P, c))


def _grid_one(combo):
    cfg = dict(SHIPPED)
    cfg.update(combo)
    evs = run(_R, _P, cfg)
    a = score(evs, _R)
    if a is None or a["n"] < 40 or a["worst_sprd"] > 15.0:
        return None
    A, B = halves(_R, evs)
    if len(A) < 12 or len(B) < 12 or sum(e[1] for e in A) <= 0 or sum(e[1] for e in B) <= 0:
        return None
    return dict(
        cfg=combo, a=a, mult=risk_for_dd(evs)[1], mA=risk_for_dd(A)[1], mB=risk_for_dd(B)[1]
    )


GRID = dict(
    entry=["0.618", "0.702", "0.786", "0.886"],
    stop=["1.0", "0.886", ("atr", 1.0), ("atr", 1.3), ("atr", 1.5), ("atr", 2.0)],
    sizes=[(0.0, 0.0, 1.0), (0.0, 0.5, 0.5), (0.0, 0.0, 0.0)],
    vwap=[True, False],
    tp1f=[0.5, 0.382],
    min_stop_pct=[0.0, 0.05, 0.08, 0.10, 0.12, 0.15],
    which=[2, 3, 99],
)


def _tag(c):
    s = c.get("stop", SHIPPED["stop"])
    s = s if not isinstance(s, tuple) else "atr%.2f" % s[1]
    z = c.get("sizes", SHIPPED["sizes"])
    return (
        f"e{c.get('entry', ''):<6}s{s:<8}{'/'.join(str(int(x * 100)) for x in z):<9}"
        f"{'vwap' if c.get('vwap', True) else '----'} "
        f"min{c.get('min_stop_pct', 0):<5}w{c.get('which', 99)}"
    )


def cmd_frontier():
    keys = list(GRID)
    combos = [dict(zip(keys, v)) for v in itertools.product(*(GRID[k] for k in keys))]
    print(
        f"{len(combos)} configurations; keeping resolvable stops, both halves positive\n",
        flush=True,
    )
    with mp.Pool(processes=max(1, mp.cpu_count() - 2), initializer=_init) as pool:
        res = [r for r in pool.map(_grid_one, combos, chunksize=8) if r]
    print(f"{len(res)} survive\n")
    print("RANKED BY TERMINAL MULTIPLE AT A 25% DRAWDOWN BUDGET over the full history")
    print(
        f"{'configuration':<52}{'n':>5}{'MULT':>9}{'halfA':>8}{'halfB':>8}"
        f"{'expR':>8}{'PF':>6}{'t':>6}"
    )
    print("-" * 102)
    for r in sorted(res, key=lambda x: -min(x["mA"], x["mB"]))[:25]:
        print(
            f"{_tag(r['cfg']):<52}{r['a']['n']:>5}{r['mult']:>8.1f}x{r['mA']:>7.1f}x"
            f"{r['mB']:>7.1f}x{r['a']['exp']:>+8.3f}{r['a']['pf']:>6.2f}{r['a']['t']:>6.2f}"
        )
    print("\nranked by the WEAKER HALF, which is the number one lucky year cannot buy")


def _settle_seed(seed):
    rows = jitter_rows(seed)
    pre = prescan(rows)
    out = {}
    for name, cfg in (("before Run 7", PRE_RUN7), ("shipped today", SHIPPED)):
        evs = run(rows, pre, cfg)
        a = score(evs, rows)
        if a is None:
            return None
        A, B = halves(rows, evs)
        out[name] = dict(
            n=a["n"],
            sum=a["sum"],
            pf=a["pf"],
            m=risk_for_dd(evs)[1],
            mA=risk_for_dd(A)[1] if len(A) > 3 else 0.0,
            mB=risk_for_dd(B)[1] if len(B) > 3 else 0.0,
        )
    return out


def cmd_settle(nseed=40):
    """Both configurations on THE SAME jittered series, compared pairwise. Unpaired medians had
    these tied; pairing removes the price series as a source of difference and separated them."""
    with mp.Pool(processes=max(1, mp.cpu_count() - 2)) as pool:
        res = [r for r in pool.map(_settle_seed, range(9000, 9000 + nseed), chunksize=1) if r]
    print(f"{len(res)} jittered replays, each scored by both configurations\n")
    names = ["before Run 7", "shipped today"]
    print(
        f"{'configuration':<24}{'trades':>8}{'sumR':>9}{'PF':>7}{'MULT@25%dd':>12}"
        f"{'10th':>8}{'90th':>8}{'halfA':>8}{'halfB':>8}"
    )
    print("-" * 92)
    for n in names:
        v = [r[n] for r in res]
        ms = sorted(x["m"] for x in v)
        q = lambda a, p: a[max(0, min(len(a) - 1, int(p * len(a))))]  # noqa: E731
        print(
            f"{n:<24}{statistics.median(x['n'] for x in v):>8.0f}"
            f"{statistics.median(x['sum'] for x in v):>+9.1f}"
            f"{statistics.median(x['pf'] for x in v):>7.2f}"
            f"{statistics.median(ms):>11.1f}x{q(ms, 0.1):>7.1f}x{q(ms, 0.9):>7.1f}x"
            f"{statistics.median(x['mA'] for x in v):>7.1f}x"
            f"{statistics.median(x['mB'] for x in v):>7.1f}x"
        )
    w = sum(1 for r in res if r["shipped today"]["m"] > r["before Run 7"]["m"])
    okn = sum(1 for r in res if r["shipped today"]["mA"] > 4 and r["shipped today"]["mB"] > 4)
    oko = sum(1 for r in res if r["before Run 7"]["mA"] > 4 and r["before Run 7"]["mB"] > 4)
    print(f"\nPAIRED on the same series: shipped beats the old default on {w} of {len(res)}")
    print(f"clears 4x on BOTH halves: shipped {okn}/{len(res)}, old default {oko}/{len(res)}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "sensitivity"
    if mode == "sensitivity":
        cmd_sensitivity()
    elif mode in ("grid", "frontier"):
        cmd_frontier()
    elif mode == "settle":
        cmd_settle(int(sys.argv[2]) if len(sys.argv) > 2 else 40)
    else:
        print(__doc__)
        sys.exit(2)
