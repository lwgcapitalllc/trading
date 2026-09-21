#!/usr/bin/env python3
"""fft_first_touch_study.py — the user's FFT (first fib touch) claim, measured before costs.

The claim (the user, 2026-09-21): with the 15m AND the 5m bullish and the 1m bearish with no 1m
bullish structure break, the FIRST time price comes back into the 61.8-70.2 zone of the 5m FFT fib
it reacts back to the 50 (TP1) about 90% of the time, and often on to the 38.2 (TP2). The second
and third visits do not. A sell is the mirror.

Rule, fixed before any result was seen:

    fib       the canonical Structure ("FFT") fib on 5m bars — `engines/fibonacci/` StructureFib,
              default MPC settings, internal-swing adoption on, exactly as EngineStack wires it
    first     the leg's E1 (0.618) is still untouched by the engine's own latch at the close of the
              last 5m bar, that close sits on the far side of E1, and it is the first entry of this
              leg (one per leg: fib direction + origin bar)
    fill      a resting limit at E1, filled on the first 1m bar that reaches it; a 1m bar that makes
              a new 0.0 extreme first redraws the fib, so the order is dropped for that 5m bar
    gates     15m external trend = trade side (last 15m bar CLOSED by the fill minute)
              5m  external trend = trade side (the fib's own direction agrees)
              1m  external trend = AGAINST the side on the minute before the fill, AND no 1m break in
                  the trade's direction since the minute that made the fib's 0.0 extreme
              no weekend: no market closure (a 1m gap over 12 hours) between that extreme and the
                  fill (the user, 2026-09-21)
              5m at most MAX_BOS continuation BOS since the trend's shift (SOS) — "more than one
                  BOS is continuation, and can be exhaustion" (the user, 2026-09-21). The shift
                  sets the BOS flag too, so it resets the count rather than adding to it.
    outcome   walked on raw 1m bars from the fill minute until the stop or the target: on the fill
              minute only the stop counts (the target may have printed before the touch); a later
              minute that reaches both is a LOSS. No time limit, no costs.

Variants reported beside the primary cell (61.8 fill, stop at the 1.0, target TP1, gates on):
entry at 70.2 instead (filled only if price gets there before TP1), stop at 88.6, target TP2, the
sniper zone / a 5m FVG overlapping the 61.8-70.2 zone (or neither — "just a bounce"), no gates at
all, and the SECOND touch of the same leg after the first one reached TP1.

The benchmark. With no costs, a trade's break-even win rate is risk / (risk + reward) — and that is
ALSO what a random walk scores on the same bracket. From 61.8 with the stop at 1.0 and TP1 at 0.5
it is 76.4%. So a hit rate means nothing on its own: each cell is compared with (1) that random-walk
figure and (2) random entries in the same month and New York hour, same side, same dollar stop and
target, walked on the same raw 1m bars (REPS per real trade). avgR is before costs.

Gold before 2020-01-01 is the reserved test set and is refused here — except by --holdout, which
runs ONE frozen claim on it and prints nothing else.

THE HOLDOUT CLAIM — frozen 2026-09-21 BEFORE the run (the user said "run it"):
    rule      first touch; 15m + 5m with the trade; 1m against it with no 1m break in the trade's
              direction since the extreme; no weekend; the 5m has made NO continuation BOS since its
              shift (the first pullback after the SOS); 61.8 fill; stop at 1.0
    targets   TP1 (0.5) and TP2 (0.382), both declared
    window    PU Prime M1 2018-09-14 -> 2019-12-31 (trades count from 2018-10-15, after warm-up)
    pass      on BOTH targets: win rate above the break-even AND above the matched random entries,
              and avgR > 0 before costs. Expect ~30-40 trades, so a z under ~1.65 reads "consistent,
              not proven" and a fail on either target is a fail. Context row printed beside it: the
              same rule with any number of BOS. Nothing is re-tuned on this window afterwards.

Usage:
  python backtest/tools/fft_first_touch_study.py
  python backtest/tools/fft_first_touch_study.py --start 2025-09-01 --end 2026-09-17 --list 20
  python backtest/tools/fft_first_touch_study.py --holdout      # SPENT 2026-09-21 — do not re-run to tune
"""

from __future__ import annotations

import argparse
import math
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "engines", ROOT / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from loaded_level_study import NY, clean_reopens, wilder_atr  # noqa: E402
from market_structure import Bar, StructureEngine  # noqa: E402

from backtest.data.resample import resample_up  # noqa: E402
from backtest.replay.loop import iter_bars  # noqa: E402
from backtest.replay.stack import EngineConfig, EngineStack  # noqa: E402

CACHE_DIR = ROOT / "backtest" / "cache" / "PUPrime_Demo"
SYMBOL = "XAUUSD_p"  # --symbol swaps it; only gold carries the reserved pre-2020 test set
RESERVED_BEFORE = pd.Timestamp("2020-01-01")
WARMUP_DAYS = 31  # engines run from --start; trades count only after this
REPS = 20
SEED = 7

# (label, ratio) — the fib's own names; 1.0 is the stop the user starts from.
ENTRIES = (("61.8", "E1"), ("70.2", "E2"))
STOPS = (("1.0", "1.0"), ("88.6", "E4"))
TARGETS = (("TP1 50", "TP1"), ("TP2 38.2", "TP2"))


# ── data ─────────────────────────────────────────────────────────────────────
HOLDOUT = ("2018-09-14", "2020-01-01")


def load_1m(start: str, end: str, holdout: bool = False) -> pd.DataFrame:
    if SYMBOL == "XAUUSD_p" and not holdout and pd.Timestamp(start) < RESERVED_BEFORE:
        sys.exit("gold before 2020-01-01 is the reserved test set — refused")
    path = CACHE_DIR / f"{SYMBOL}__M1.csv"
    if not path.exists():
        sys.exit(f"no cached M1 bars at {path}")
    df = pd.read_csv(path, usecols=["time", "open", "high", "low", "close"], parse_dates=["time"])
    df = df[(df["time"] >= start) & (df["time"] < end)].set_index("time")
    return df.astype(float)


def structure_run(o, h, lo, c):
    """External trend after each bar, whether the bar broke structure bull / bear, and how many
    continuation BOS the current trend has made since its shift (a shift sets the BOS flag too, so
    it resets the count to 0)."""
    eng = StructureEngine()
    n = len(c)
    d = np.zeros(n, dtype=np.int8)
    bull = np.zeros(n, dtype=bool)
    bear = np.zeros(n, dtype=bool)
    nbos = np.full(n, -1, dtype=np.int16)
    nb = {1: 0, -1: 0}
    for i in range(n):
        ext = eng.update(Bar(index=i, open=o[i], high=h[i], low=lo[i], close=c[i])).external
        d[i] = eng.dir
        bull[i] = ext.bull_bos or ext.bull_sos
        bear[i] = ext.bear_bos or ext.bear_sos
        if ext.bull_bos:
            nb[1] = 0 if ext.bull_sos else nb[1] + 1
        if ext.bear_bos:
            nb[-1] = 0 if ext.bear_sos else nb[-1] + 1
        if d[i] != 0:
            nbos[i] = nb[int(d[i])]
    return d, bull, bear, nbos


def five_minute_run(df5: pd.DataFrame):
    """Per 5m bar, the state a trader sees at its close: the fib, the sniper zone, open FVGs."""
    cfg = EngineConfig(macro=False, internal=False, rsi=False)
    stack = EngineStack(cfg)
    rows = []
    # continuation BOS since the last shift, per side. A shift (SOS) also sets the BOS flag, so it
    # resets the count to 0 rather than adding one.
    nb = {1: 0, -1: 0}
    for bar in iter_bars(df5):
        s = stack.step(bar)
        ext = s.structure.external
        if ext.bull_bos:
            nb[1] = 0 if ext.bull_sos else nb[1] + 1
        if ext.bear_bos:
            nb[-1] = 0 if ext.bear_sos else nb[-1] + 1
        f = s.fib
        if f is None or not f.active or f.direction == 0:
            rows.append(None)
            continue
        lq = s.liquidity
        # wick-swept levels only (day / session / H4) — a weekly level is a close-through break
        sw_lo = [x.price for x in lq.mitigated if x.rule == "sweep_low"] if lq else []
        sw_hi = [x.price for x in lq.mitigated if x.rule == "sweep_high"] if lq else []
        act_lo = (
            sorted((x.price for x in lq.active if x.rule == "sweep_low"), reverse=True)[:3]
            if lq
            else []
        )
        act_hi = sorted(x.price for x in lq.active if x.rule == "sweep_high")[:3] if lq else []
        d = f.direction
        lv = f.levels
        z_hi, z_lo = max(lv["E1"], lv["E2"]), min(lv["E1"], lv["E2"])
        sn = s.sniper
        sniper = bool(
            sn is not None
            and sn.active
            and sn.direction == d
            and sn.zone_bot is not None
            and sn.zone_bot <= z_hi
            and sn.zone_top >= z_lo
        )
        fvg = bool(
            s.fvg is not None
            and any(
                g.is_bullish == (d == 1) and g.bottom <= z_hi and g.top >= z_lo
                for g in s.fvg.active
            )
        )
        rows.append(
            dict(
                d=d,
                sdir=stack.structure.dir,
                lv={k: lv[k] for k in ("E1", "E2", "E4", "1.0", "TP1", "TP2", "TP3")},
                e1_done="E1" in f.touched_so_far,
                origin=f.asl_loc if d == 1 else f.ash_loc,
                ext_loc=f.ash_loc if d == 1 else f.asl_loc,
                sniper=sniper,
                fvg=fvg,
                nbos=nb[d],
                sn_top=sn.zone_top if sn is not None and sn.active else None,
                sn_bot=sn.zone_bot if sn is not None and sn.active else None,
                sn_dir=sn.direction if sn is not None else 0,
                sn_touched=bool(sn is not None and sn.zone_active),
                sw_lo=sw_lo,
                sw_hi=sw_hi,
                act_lo=act_lo,
                act_hi=act_hi,
            )
        )
    return rows


def fifteen_fib_run(df15: pd.DataFrame):
    """The 15m FFT fib after each 15m bar: direction, its 0.0 and its 1.0 (NaN when not drawn)."""
    cfg = EngineConfig(
        sniper=False,
        macro=False,
        internal=False,
        fvg=False,
        rsi=False,
        liquidity=False,
        sessions=False,
    )
    stack = EngineStack(cfg)
    n = len(df15)
    d, top, one = np.zeros(n, dtype=np.int8), np.full(n, np.nan), np.full(n, np.nan)
    for i, bar in enumerate(iter_bars(df15)):
        f = stack.step(bar).fib
        if f is not None and f.active and f.direction != 0:
            d[i], top[i], one[i] = f.direction, f.levels["TP3"], f.levels["1.0"]
    return d, top, one


# ── outcome walk ─────────────────────────────────────────────────────────────
def walk(H, L, m, d, stop, target, entry_bar_full):
    """First of stop / target from minute m. Returns (win, ambiguous, exit minute) or None if
    unresolved.
    entry_bar_full: the fill came at minute m's OPEN, so its whole range is after the entry."""
    n = len(H)
    if d == 1:
        if L[m] <= stop:
            return (False, entry_bar_full and H[m] >= target, m)
        if entry_bar_full and H[m] >= target:
            return (True, False, m)
    else:
        if H[m] >= stop:
            return (False, entry_bar_full and L[m] <= target, m)
        if entry_bar_full and L[m] <= target:
            return (True, False, m)
    i, step = m + 1, 512
    while i < n:
        j = min(n, i + step)
        if d == 1:
            s_hit, t_hit = L[i:j] <= stop, H[i:j] >= target
        else:
            s_hit, t_hit = H[i:j] >= stop, L[i:j] <= target
        s_any, t_any = s_hit.any(), t_hit.any()
        if s_any or t_any:
            si = int(s_hit.argmax()) if s_any else 1 << 30
            ti = int(t_hit.argmax()) if t_any else 1 << 30
            if si <= ti:
                return (False, si == ti, i + si)
            return (True, False, i + ti)
        i, step = j, step * 4
    return None


def managed(H, L, m, d, entry, stop, tp1, tp2, full, tp3=None):
    """One fill, three ways out. None if unresolved or TP1 is not beyond the entry.
    tp1  exit at TP1 (win) or the stop (loss)
    tp2  exit at TP2 (win) or the stop (loss), no management
    be   the stop before TP1 = 'loss'; at TP1 the stop moves to the entry and the trade runs to
         TP2 ('full') or back to the entry ('scratch'). A minute after TP1 that reaches both the
         entry and TP2 is a scratch."""
    if (tp1 - entry) * d <= 0 or (entry - stop) * d <= 0:
        return None
    a = walk(H, L, m, d, stop, tp1, full)
    b = walk(H, L, m, d, stop, tp2, full)
    if a is None or b is None:
        return None
    if not a[0]:
        be = "loss"
    else:
        j = a[2]
        if (H[j] >= tp2) if d == 1 else (L[j] <= tp2):
            be = "full"
        else:
            c = walk(H, L, j + 1, d, entry, tp2, True) if j + 1 < len(H) else None
            if c is None:
                return None
            be = "full" if c[0] else "scratch"
    risk = abs(entry - stop)
    out = dict(
        risk=risk,
        r1=abs(tp1 - entry) / risk,
        r2=abs(tp2 - entry) / risk,
        tp1=a[0],
        tp2=b[0],
        be=be,
        m=m,
    )
    if tp3 is not None:
        c3 = walk(H, L, m, d, stop, tp3, full)
        if c3 is None:
            return None
        out.update(r3=abs(tp3 - entry) / risk, tp3=c3[0])
    return out


# ── the scan ─────────────────────────────────────────────────────────────────
def find_touch(cH, cL, a, b, d, level, extreme):
    """First minute in [a, b) that reaches `level`; None if a new 0.0 extreme prints first (or in
    the same minute — the order of the two is unknown, so the fill is not claimed)."""
    for m in range(a, b):
        new_ext = cH[m] > extreme if d == 1 else cL[m] < extreme
        touch = cL[m] <= level if d == 1 else cH[m] >= level
        if new_ext:
            return None
        if touch:
            return m
    return None


def run(start: str, end: str, holdout: bool = False):
    t0 = time.time()
    raw = load_1m(start, end, holdout)
    clean, fixed = clean_reopens(raw)
    df5, df15 = resample_up(clean, 5, 1), resample_up(clean, 15, 1)
    print(
        f"bars: 1m {len(clean):,}  5m {len(df5):,}  15m {len(df15):,}  "
        f"({clean.index[0]} -> {clean.index[-1]}), reopen spikes clipped {len(fixed)}"
    )

    arr = lambda df: tuple(df[k].to_numpy() for k in ("open", "high", "low", "close"))  # noqa: E731
    with ProcessPoolExecutor(max_workers=4) as pool:
        f1 = pool.submit(structure_run, *arr(clean))
        f15 = pool.submit(structure_run, *arr(df15))
        f5 = pool.submit(five_minute_run, df5)
        ff = pool.submit(fifteen_fib_run, df15)
        dir1, bull1, bear1, _ = f1.result()
        dir15, _, _, nbos15 = f15.result()
        rows = f5.result()
        f15d, f15top, f15one = ff.result()
    print(f"engines done in {time.time() - t0:.0f}s")

    t1 = clean.index.to_numpy()
    t5 = df5.index.to_numpy()
    t15_close = df15.index.to_numpy() + np.timedelta64(15, "m")
    close5 = df5["close"].to_numpy()
    cO, cH, cL = clean["open"].to_numpy(), clean["high"].to_numpy(), clean["low"].to_numpy()
    rH, rL = raw["high"].to_numpy(), raw["low"].to_numpy()
    first_min = np.searchsorted(t1, t5, "left")
    last_min = np.append(first_min[1:], len(t1))
    cb = {1: np.concatenate([[0], np.cumsum(bull1)]), -1: np.concatenate([[0], np.cumsum(bear1)])}
    # cg[i] = closures (a 1m gap over 12 hours — a weekend or a holiday) landing on minutes < i
    closed = np.concatenate([[False], np.diff(t1) > np.timedelta64(12, "h")])
    cg = np.concatenate([[0], np.cumsum(closed)])
    cC = clean["close"].to_numpy()
    atr5 = wilder_atr(*(df5[k].to_numpy() for k in ("high", "low", "close")), n=14)

    def features(k, m, em, d, lv, price):
        """The four pre-declared refinement measures (2026-09-21), all known at the fill."""
        a = atr5[k - 1]
        i15 = int(np.searchsorted(t15_close, t1[m], "right")) - 1
        dep = None
        if i15 >= 0 and int(f15d[i15]) == d and not np.isnan(f15top[i15]):
            dep = float((f15top[i15] - price) / (f15top[i15] - f15one[i15]))
        return dict(
            # the 15m trend's continuation BOS since its shift, on the last closed 15m bar
            n15=int(nbos15[i15]) if i15 >= 0 else -1,
            impulse=float(abs(lv["TP3"] - lv["1.0"]) / a) if a and not np.isnan(a) else None,
            depth15=dep,
            pb_min=float((t1[m] - t1[em]) / np.timedelta64(1, "m")),
        )

    def sweep(k, m, d, ext_loc, e1):
        """Pre-declared 2026-09-21: did the pullback take a named level on its own side (a buy: a
        day / session / H4 LOW) between the 5m extreme and the fill? Closed 5m bars after the extreme,
        plus the fill's own 5m bar up to the fill minute against the levels live at its open. Returns
        (any sweep, a swept level at or past 61.8)."""
        got = []
        for j in range(ext_loc + 1, k):
            r = rows[j]
            if r is not None:
                got += r["sw_lo"] if d == 1 else r["sw_hi"]
        r = rows[k - 1]
        a = first_min[k]
        if d == 1:
            lo = cL[a : m + 1].min()
            got += [p for p in r["act_lo"] if lo < p]
            deep = any(p <= e1 for p in got)
        else:
            hi = cH[a : m + 1].max()
            got += [p for p in r["act_hi"] if hi > p]
            deep = any(p >= e1 for p in got)
        return bool(got), bool(deep)

    def confirm(m, d, lv):
        """Idea 5: after the 61.8 touch, the first 1m break back in the trade's direction; enter at
        that minute's close, stop at the extreme since the touch. None if the 1.0 or TP1 prints first
        (or on the same minute — the order is unknown, not claimed)."""
        brk = bull1 if d == 1 else bear1
        fail, tp = lv["1.0"], lv["TP1"]
        i, n, step = m, len(t1), 256
        while i < n:
            j = min(n, i + step)
            b = brk[i:j]
            f = (rL[i:j] <= fail) if d == 1 else (rH[i:j] >= fail)
            t = (rH[i:j] >= tp) if d == 1 else (rL[i:j] <= tp)
            if i == m:
                t = t.copy()
                t[0] = False  # the touch minute's TP1 print came before the touch
            ba, fa, ta = b.any(), f.any(), t.any()
            if ba or fa or ta:
                bi = int(b.argmax()) if ba else 1 << 30
                fi = int(f.argmax()) if fa else 1 << 30
                ti = int(t.argmax()) if ta else 1 << 30
                if not (bi < fi and bi < ti):
                    return None
                e = i + bi
                if e + 1 >= n:
                    return None
                stop = rL[m : e + 1].min() if d == 1 else rH[m : e + 1].max()
                return managed(rH, rL, e + 1, d, cC[e], stop, lv["TP1"], lv["TP2"], True, lv["TP3"])
            i, step = j, step * 4
        return None

    count_from = np.datetime64(pd.Timestamp(start) + pd.Timedelta(days=WARMUP_DAYS))

    def ext_minute(k5, d):
        a, b = first_min[k5], last_min[k5]
        return a + int(np.argmax(cH[a:b]) if d == 1 else np.argmin(cL[a:b]))

    def gates(m, d, ext_loc):
        i15 = int(np.searchsorted(t15_close, t1[m], "right")) - 1
        g15 = i15 >= 0 and int(dir15[i15]) == d
        g1dir = m >= 1 and int(dir1[m - 1]) == -d
        em = ext_minute(ext_loc, d)
        # no 1m break in the trade's direction in minutes (em, m-1]
        g1clean = (cb[d][m] - cb[d][em + 1]) == 0 if m > em + 1 else True
        # the stricter reading of "consistent": the 1m has itself PRINTED a break against the trade
        # since the extreme, rather than only carrying a trend it had before the leg topped
        g1printed = m > em + 1 and (cb[-d][m] - cb[-d][em + 1]) > 0
        return g15, g1dir, g1clean, g1printed, em

    def outcomes(m, d, lv, fill_price, open_fill):
        """Every entry/stop/target combination for a touch at minute m."""
        out = {}
        # the 70.2 fill: from the 61.8 touch, the first minute reaching 70.2 before TP1 prints
        e2 = lv["E2"]
        m2, open2 = None, False
        if (cL[m] <= e2) if d == 1 else (cH[m] >= e2):
            m2, open2 = m, (cO[m] <= e2) if d == 1 else (cO[m] >= e2)
        else:
            for j in range(m + 1, min(len(t1), m + 200_000)):
                tp = cH[j] >= lv["TP1"] if d == 1 else cL[j] <= lv["TP1"]
                hit = cL[j] <= e2 if d == 1 else cH[j] >= e2
                if hit and not tp:
                    m2, open2 = j, (cO[j] <= e2) if d == 1 else (cO[j] >= e2)
                    break
                if tp:
                    break
        for en, ek in ENTRIES:
            if ek == "E1":
                mm, px, full = m, fill_price, open_fill
            else:
                if m2 is None:
                    continue
                mm, full = m2, open2
                px = (min(e2, cO[m2]) if d == 1 else max(e2, cO[m2])) if open2 else e2
            for sn, sk in STOPS:
                stop = lv[sk]
                if (px - stop) * d <= 0:
                    continue
                for tn, tk in TARGETS:
                    tgt = lv[tk]
                    if (tgt - px) * d <= 0:
                        continue
                    r = walk(rH, rL, mm, d, stop, tgt, full)
                    if r is None:
                        continue
                    out[(en, sn, tn)] = dict(
                        win=r[0],
                        amb=r[1],
                        exit=r[2],
                        risk=abs(px - stop),
                        reward=abs(tgt - px),
                        m=mm,
                    )
        return out

    touches = []
    done_first, done_second, won_first = set(), set(), {}
    for k in range(1, len(t5)):
        s = rows[k - 1]
        if s is None or s["sdir"] != s["d"]:
            continue
        d, lv = s["d"], s["lv"]
        key = (d, s["origin"])
        e1 = lv["E1"]
        if (close5[k - 1] - e1) * d <= 0:
            continue
        extreme = lv["TP3"]
        if key not in done_first:
            if s["e1_done"]:
                continue
            kind = "first"
        elif key in won_first and key not in done_second and first_min[k] > won_first[key]:
            kind = "second"
        else:
            continue
        m = find_touch(cH, cL, first_min[k], last_min[k], d, e1, extreme)
        if m is None:
            continue
        (done_first if kind == "first" else done_second).add(key)
        open_fill = (cO[m] <= e1) if d == 1 else (cO[m] >= e1)
        fill = (min(e1, cO[m]) if d == 1 else max(e1, cO[m])) if open_fill else e1
        res = outcomes(m, d, lv, fill, open_fill)
        if kind == "first":
            p = res.get(("61.8", "1.0", "TP1 50"))
            if p is not None and p["win"]:
                # the first touch's TP1 minute: a re-touch only counts after it
                won_first[key] = _tp_minute(rH, rL, m, d, lv["TP1"])
        if t1[m] < count_from:
            continue
        g15, g1dir, g1clean, g1printed, em = gates(m, d, s["ext_loc"])
        feat = features(k, m, em, d, lv, fill)
        conf = confirm(m, d, lv) if (g15 and g1dir and g1clean and kind == "first") else None
        swept, swept_deep = sweep(k, m, d, s["ext_loc"], lv["E1"])
        weekend = bool(cg[m + 1] - cg[em + 1] > 0)
        held = {c: bool(cg[r["exit"] + 1] - cg[r["m"] + 1] > 0) for c, r in res.items()}
        touches.append(
            dict(
                kind=kind,
                t=pd.Timestamp(t1[m]),
                d=d,
                g15=g15,
                g1dir=g1dir,
                g1clean=g1clean,
                g1printed=g1printed,
                em=em,
                m=m,
                sniper=s["sniper"],
                fvg=s["fvg"],
                res=res,
                nbos=s["nbos"],
                weekend=weekend,
                held=held,
                open_fill=open_fill,
                fill=fill,
                lv=lv,
                conf=conf,
                key=key,
                swept=swept,
                swept_deep=swept_deep,
                **feat,
            )
        )
    # ── the sniper entry (the user, 2026-09-21): a limit at the sniper zone's near edge on its FIRST
    #    touch (the engine's own latch), stop at its far edge, FFT TP1 / TP2 as the targets ──
    snipes, done_zone = [], set()
    for k in range(1, len(t5)):
        s = rows[k - 1]
        if s is None or s["sdir"] != s["d"] or s["sn_top"] is None:
            continue
        d, lv = s["d"], s["lv"]
        if s["sn_dir"] != d or s["sn_touched"]:
            continue
        top, bot = s["sn_top"], s["sn_bot"]
        near, far = (top, bot) if d == 1 else (bot, top)
        zkey = (d, top, bot)
        if zkey in done_zone or (close5[k - 1] - near) * d <= 0:
            continue
        m = find_touch(cH, cL, first_min[k], last_min[k], d, near, lv["TP3"])
        if m is None:
            continue
        done_zone.add(zkey)
        open_fill = (cO[m] <= near) if d == 1 else (cO[m] >= near)
        fill = (min(near, cO[m]) if d == 1 else max(near, cO[m])) if open_fill else near
        if t1[m] < count_from:
            continue
        res = managed(rH, rL, m, d, fill, far, lv["TP1"], lv["TP2"], open_fill)
        if res is None:
            continue
        g15, g1dir, g1clean, g1printed, em = gates(m, d, s["ext_loc"])
        feat = features(k, m, em, d, lv, fill)
        e1, e2 = lv["E1"], lv["E2"]
        snipes.append(
            dict(
                kind="sniper",
                t=pd.Timestamp(t1[m]),
                d=d,
                g15=g15,
                g1dir=g1dir,
                g1clean=g1clean,
                weekend=bool(cg[m + 1] - cg[em + 1] > 0),
                nbos=s["nbos"],
                res=res,
                m=m,
                near=near,
                far=far,
                fill=fill,
                open_fill=open_fill,
                lv=lv,
                # the zone's two edges as FFT retracement depth (0 = the 0.0 extreme, 1 = the 1.0)
                pos_near=(lv["TP3"] - near) / (lv["TP3"] - lv["1.0"]),
                pos_far=(lv["TP3"] - far) / (lv["TP3"] - lv["1.0"]),
                **feat,
                # where the sniper zone sits against the FFT 61.8-70.2 zone
                overlap=bool(min(top, bot) <= max(e1, e2) and max(top, bot) >= min(e1, e2)),
                behind=bool((e1 - near) * d >= 0),  # starts at or past 61.8
                inside=bool((e1 - near) * d >= 0 and (far - e2) * d >= 0),  # wholly in 61.8-70.2
            )
        )
    print(
        f"scan done in {time.time() - t0:.0f}s — {len(touches):,} touches, {len(snipes):,} sniper fills"
    )
    return touches, snipes, raw, t0


def _tp_minute(H, L, m, d, tp):
    i, n, step = m + 1, len(H), 512
    while i < n:
        j = min(n, i + step)
        hit = H[i:j] >= tp if d == 1 else L[i:j] <= tp
        if hit.any():
            return i + int(hit.argmax())
        i, step = j, step * 4
    return n


# ── the random control ───────────────────────────────────────────────────────
class Control:
    """Random entries in the same month and New York hour, same side, same dollar stop and target."""

    def __init__(self, raw: pd.DataFrame):
        self.O, self.H, self.L = (raw[k].to_numpy() for k in ("open", "high", "low"))
        ny = raw.index.tz_localize("UTC").tz_convert(NY)
        keys = (ny.year * 100 + ny.month) * 100 + ny.hour
        self.keys = np.asarray(keys)
        order = np.argsort(self.keys, kind="stable")
        self.sorted_keys = self.keys[order]
        self.order = order
        self.cache = {}

    def pool(self, key):
        if key not in self.cache:
            a = np.searchsorted(self.sorted_keys, key, "left")
            b = np.searchsorted(self.sorted_keys, key, "right")
            self.cache[key] = self.order[a:b]
        return self.cache[key]

    def draw(self, m, d, risk, reward, combo):
        # seeded by the trade and the bracket, so one trade gets the same draws in every table
        rng = np.random.default_rng([SEED, int(m), zlib.crc32("|".join(combo).encode())])
        pool = self.pool(self.keys[m])
        wins = 0
        got = 0
        rs = []
        for _ in range(REPS):
            j = int(pool[rng.integers(len(pool))])
            e = self.O[j]
            r = walk(self.H, self.L, j, d, e - d * risk, e + d * reward, True)
            if r is None:
                continue
            got += 1
            wins += r[0]
            rs.append(reward / risk if r[0] else -1.0)
        return wins, got, rs


# ── report ───────────────────────────────────────────────────────────────────
def cell(rows, combo, ctrl):
    trades = [r["res"][combo] for r in rows if combo in r["res"]]
    n = len(trades)
    if n == 0:
        return None
    w = sum(t["win"] for t in trades)
    amb = sum(t["amb"] for t in trades)
    rw = float(np.mean([t["risk"] / (t["risk"] + t["reward"]) for t in trades]))
    avg_r = float(np.mean([t["reward"] / t["risk"] if t["win"] else -1.0 for t in trades]))
    cw = cg = 0
    crs = []
    for r in rows:
        t = r["res"].get(combo)
        if t is None:
            continue
        a, b, rs = ctrl.draw(t["m"], r["d"], t["risk"], t["reward"], combo)
        cw += a
        cg += b
        crs += rs
    p, pc = w / n, cw / max(cg, 1)
    z = (p - pc) / math.sqrt(max(pc * (1 - pc), 1e-9) * (1 / n + 1 / max(cg, 1)))
    return dict(
        n=n,
        win=p,
        rw=rw,
        ctrl=pc,
        z=z,
        avg_r=avg_r,
        ctrl_r=float(np.mean(crs)) if crs else float("nan"),
        amb=amb,
    )


def fmt(label, c):
    if c is None:
        return f"  {label:<34} {'—':>5}"
    return (
        f"  {label:<34} {c['n']:>5}  {100 * c['win']:5.1f}%  {100 * c['rw']:5.1f}%  "
        f"{100 * c['ctrl']:5.1f}%  {c['z']:+5.2f}   {c['avg_r']:+.3f}R  {c['ctrl_r']:+.3f}R"
        + (f"   ({c['amb']} same-minute)" if c["amb"] else "")
    )


HDR = (
    f"  {'':<34} {'n':>5}  {'win':>6}  {'b/even':>6}  {'random':>6}  {'z':>5}   "
    f"{'avgR':>7}  {'rand R':>7}"
)


def gated(t, weekend_ok=False, max_bos=None):
    """The user's gates: 15m + 5m with the trade, 1m against it with no 1m break in the trade's
    direction since the extreme; no setup whose leg spans a weekend; at most `max_bos` 5m
    continuation BOS since the shift."""
    return (
        t["g15"]
        and t["g1dir"]
        and t["g1clean"]
        and (weekend_ok or not t["weekend"])
        and (max_bos is None or t["nbos"] <= max_bos)
    )


MAX_BOS = 1  # the user, 2026-09-21: "the 5m should not have more than one BOS"


def report(touches, raw):
    ctrl = Control(raw)
    first = [t for t in touches if t["kind"] == "first"]
    rule = [t for t in first if gated(t, max_bos=MAX_BOS)]
    primary = ("61.8", "1.0", "TP1 50")
    tp2 = ("61.8", "1.0", "TP2 38.2")

    print(
        "\nwin = hit the target before the stop | b/even = break-even win rate (also what a random"
    )
    print(
        "walk scores on the same bracket) | random = matched random entries | avgR before costs\n"
    )

    print(
        "THE RULE NOW — first touch, gates, no weekend, 5m at most 1 BOS; 61.8 fill, stop 1.0, TP1"
    )
    print(HDR)
    print(fmt("buys and sells", cell(rule, primary, ctrl)))
    print(fmt("buys", cell([t for t in rule if t["d"] == 1], primary, ctrl)))
    print(fmt("sells", cell([t for t in rule if t["d"] == -1], primary, ctrl)))
    cut = pd.Timestamp("2023-01-01")
    print(fmt("first half (before 2023)", cell([t for t in rule if t["t"] < cut], primary, ctrl)))
    print(fmt("second half (2023 on)", cell([t for t in rule if t["t"] >= cut], primary, ctrl)))

    print("\nWHAT EACH CHANGE DOES — 61.8 fill, stop 1.0")
    print(HDR)
    nowk = [t for t in first if gated(t)]
    steps = [
        ("every first touch, no gates", first),
        ("all gates (last run's rule)", [t for t in first if gated(t, weekend_ok=True)]),
        (
            "  weekend setups only (now dropped)",
            [t for t in first if gated(t, weekend_ok=True) and t["weekend"]],
        ),
        ("gates, no weekend", nowk),
        ("  + 5m shift leg only (0 BOS)", [t for t in nowk if t["nbos"] == 0]),
        ("  + 5m at most 1 BOS  <- the rule", rule),
        ("  5m 2+ BOS (now dropped)", [t for t in nowk if t["nbos"] >= 2]),
    ]
    for label, rows in steps:
        print(fmt(label + " [TP1]", cell(rows, primary, ctrl)))
    for label, rows in steps[3:]:
        print(fmt(label + " [TP2]", cell(rows, tp2, ctrl)))
    print("\n  by 5m BOS count since the shift (gates, no weekend), TP1:")
    for k in range(4):
        print(fmt(f"    {k} BOS", cell([t for t in nowk if t["nbos"] == k], primary, ctrl)))
    print(fmt("    4+ BOS", cell([t for t in nowk if t["nbos"] >= 4], primary, ctrl)))

    print("\nENTRY x STOP x TARGET — the rule")
    print(HDR)
    for en, _ in ENTRIES:
        for sn, _ in STOPS:
            for tn, _ in TARGETS:
                print(fmt(f"fill {en}  stop {sn}  {tn}", cell(rule, (en, sn, tn), ctrl)))

    print("\nCONFLUENCE IN THE 61.8-70.2 ZONE — the rule, stop 1.0")
    print(HDR)
    conf = [
        ("  + sniper zone in the zone", [t for t in rule if t["sniper"]]),
        ("  + 5m FVG in the zone", [t for t in rule if t["fvg"]]),
        ("  + either", [t for t in rule if t["sniper"] or t["fvg"]]),
        ("  neither — just a bounce", [t for t in rule if not t["sniper"] and not t["fvg"]]),
    ]
    for tag, combo in (("TP1", primary), ("TP2", tp2)):
        for label, rows in conf:
            print(fmt(f"{label} [{tag}]", cell(rows, combo, ctrl)))

    second = [t for t in touches if t["kind"] == "second"]
    print(
        "\nFIRST TOUCH vs SECOND TOUCH (same leg, after the first reached TP1) — 61.8, stop 1.0, TP1"
    )
    print(HDR)
    print(fmt("first touch, the rule", cell(rule, primary, ctrl)))
    print(
        fmt(
            "second touch, the rule",
            cell([t for t in second if gated(t, max_bos=MAX_BOS)], primary, ctrl),
        )
    )

    prim = [t["res"][primary] for t in rule if primary in t["res"]]
    if prim:
        print(
            f"\n  the rule, median distance from fill: stop ${np.median([x['risk'] for x in prim]):.2f}, "
            f"TP1 ${np.median([x['reward'] for x in prim]):.2f}"
        )
    held = sum(t["held"].get(primary, False) for t in rule)
    print(f"  the rule, trades still open across a weekend (TP1): {held} of {len(prim)}")
    gap = sum(t["open_fill"] for t in rule)
    print(f"  the rule, filled at a gap-through open (not at 61.8): {gap} of {len(rule)}")


def through_fill(H, L, m, d, level, x, tp1, open_fill):
    """The minute a resting limit at `level` really fills if price must trade `x` dollars THROUGH
    it, from the first touch at minute m; None if TP1 prints first (the setup left without us).
    x == 0 is the touch fill. A gap-through open fills at the open, as before."""
    if x <= 0 or open_fill:
        return m
    lvl = level - d * x
    if (L[m] <= lvl) if d == 1 else (H[m] >= lvl):
        return m
    i, n, step = m + 1, len(H), 512
    while i < n:
        j = min(n, i + step)
        f = (L[i:j] <= lvl) if d == 1 else (H[i:j] >= lvl)
        t = (H[i:j] >= tp1) if d == 1 else (L[i:j] <= tp1)
        fa, ta = f.any(), t.any()
        if fa or ta:
            fi = int(f.argmax()) if fa else 1 << 30
            ti = int(t.argmax()) if ta else 1 << 30
            return i + fi if fi < ti else None  # same minute: order unknown, not claimed
        i, step = j, step * 4
    return None


def _mgd_r(r, how):
    if how == "tp1":
        return r["r1"] if r["tp1"] else -1.0
    if how == "tp2":
        return r["r2"] if r["tp2"] else -1.0
    if how == "tp3":
        return r["r3"] if r["tp3"] else -1.0
    if how == "be":
        return {"loss": -1.0, "scratch": 0.0, "full": r["r2"]}[r["be"]]
    return {"loss": -1.0, "scratch": 0.5 * r["r1"], "full": 0.5 * (r["r1"] + r["r2"])}[r["be"]]


def mcell(items, ctrl, tag):
    """items: (direction, managed-result). The TP1 exit, TP2 straight, and TP1 -> break-even -> TP2
    (all of it, or half off at TP1), each beside random entries on the same three distances."""
    if not items:
        return None
    rs = [r for _, r in items]
    ctl = []
    for d, r in items:
        rng = np.random.default_rng([SEED, int(r["m"]), zlib.crc32(tag.encode())])
        pool = ctrl.pool(ctrl.keys[r["m"]])
        for _ in range(REPS):
            j = int(pool[rng.integers(len(pool))])
            e = ctrl.O[j]
            c = managed(
                ctrl.H,
                ctrl.L,
                j,
                d,
                e,
                e - d * r["risk"],
                e + d * r["r1"] * r["risk"],
                e + d * r["r2"] * r["risk"],
                True,
                e + d * r["r3"] * r["risk"] if "r3" in r else None,
            )
            if c is not None:
                ctl.append(c)
    n = len(rs)
    p = sum(r["tp1"] for r in rs) / n
    pc = sum(c["tp1"] for c in ctl) / max(len(ctl), 1)
    z = (p - pc) / math.sqrt(max(pc * (1 - pc), 1e-9) * (1 / n + 1 / max(len(ctl), 1)))
    avg = lambda xs, how: float(np.mean([_mgd_r(x, how) for x in xs])) if xs else float("nan")  # noqa: E731
    return dict(
        n=n,
        win=p,
        rw=float(np.mean([1 / (1 + r["r1"]) for r in rs])),
        ctrl=pc,
        z=z,
        tp2=sum(r["tp2"] for r in rs) / n,
        rw2=float(np.mean([1 / (1 + r["r2"]) for r in rs])),
        full=sum(r["be"] == "full" for r in rs) / n,
        scratch=sum(r["be"] == "scratch" for r in rs) / n,
        stop_usd=float(np.median([r["risk"] for r in rs])),
        r1=float(np.median([r["r1"] for r in rs])),
        **{f"R_{h}": avg(rs, h) for h in ("tp1", "tp2", "be", "half")},
        **{f"C_{h}": avg(ctl, h) for h in ("tp1", "tp2", "be", "half")},
        **(
            {}
            if not all("r3" in r for r in rs)
            else dict(
                tp3=sum(r["tp3"] for r in rs) / n,
                rw3=float(np.mean([1 / (1 + r["r3"]) for r in rs])),
                R_tp3=avg(rs, "tp3"),
                C_tp3=avg([c for c in ctl if "r3" in c], "tp3"),
            )
        ),
    )


MHDR1 = (
    f"  {'':<40} {'n':>4}  {'stop$':>6} {'TP1 R':>5}  {'TP1 win':>7} {'b/even':>6} {'random':>6} "
    f"{'z':>5}  {'TP2 win':>7} {'b/even':>6}"
)
MHDR2 = (
    f"  {'':<40} {'n':>4}  {'stopped':>7} {'scratch':>7} {'to TP2':>6}   {'avgR: TP1':>9} {'TP2':>6} "
    f"{'BE':>6} {'half':>6}   {'random: TP1':>11} {'TP2':>6} {'BE':>6} {'half':>6}"
)


def mfmt(label, c):
    if c is None:
        return f"  {label:<40} {'—':>4}", f"  {label:<40} {'—':>4}"
    a = (
        f"  {label:<40} {c['n']:>4}  {c['stop_usd']:>6.2f} {c['r1']:>5.2f}  {100 * c['win']:>6.1f}% "
        f"{100 * c['rw']:>5.1f}% {100 * c['ctrl']:>5.1f}% {c['z']:>+5.2f}  {100 * c['tp2']:>6.1f}% "
        f"{100 * c['rw2']:>5.1f}%"
    )
    b = (
        f"  {label:<40} {c['n']:>4}  {100 * (1 - c['win']):>6.1f}% {100 * c['scratch']:>6.1f}% "
        f"{100 * c['full']:>5.1f}%   {c['R_tp1']:>+9.3f} {c['R_tp2']:>+6.3f} {c['R_be']:>+6.3f} "
        f"{c['R_half']:>+6.3f}   {c['C_tp1']:>+11.3f} {c['C_tp2']:>+6.3f} {c['C_be']:>+6.3f} {c['C_half']:>+6.3f}"
    )
    return a, b


def entries_report(touches, snipes, raw, x=0.0):
    """The user's sniper-zone entry against the 61.8 entry, each with break-even at TP1. `x`: how far
    price must trade through a limit before it counts as filled (0 = the touch)."""
    ctrl = Control(raw)
    rH, rL = raw["high"].to_numpy(), raw["low"].to_numpy()
    first = [t for t in touches if t["kind"] == "first"]
    groups = (("any BOS", None), ("at most 1 BOS", 1), ("0 BOS (first leg)", 0))

    lines = []  # (label, cell)
    for sk, sname in (("1.0", "stop 1.0"), ("E4", "stop 88.6")):
        for gname, mb in groups:
            items = []
            for t in first:
                if not gated(t, max_bos=mb):
                    continue
                lv = t["lv"]
                j = through_fill(rH, rL, t["m"], t["d"], lv["E1"], x, lv["TP1"], t["open_fill"])
                if j is None:
                    continue
                r = managed(
                    rH,
                    rL,
                    j,
                    t["d"],
                    t["fill"],
                    lv[sk],
                    lv["TP1"],
                    lv["TP2"],
                    t["open_fill"] and j == t["m"],
                )
                if r is not None:
                    items.append((t["d"], r))
            lines.append((f"61.8 fill, {sname}, {gname}", mcell(items, ctrl, f"fft|{sk}|{gname}")))
    # "wholly inside 61.8-70.2" is left out: off the same swing low the sniper zone (0.118 of its
    # leg) cannot fit inside the 0.084-wide 61.8-70.2 band, and 2020-25 had none.
    wheres = (
        ("any sniper zone", lambda t: True),
        ("overlaps 61.8-70.2", lambda t: t["overlap"]),
        ("starts at/past 61.8 <- user", lambda t: t["behind"]),
    )
    for wname, wf in wheres:
        for gname, mb in groups:
            items = []
            for t in snipes:
                if not (gated(t, max_bos=mb) and wf(t)):
                    continue
                j = through_fill(
                    rH, rL, t["m"], t["d"], t["near"], x, t["lv"]["TP1"], t["open_fill"]
                )
                if j is None:
                    continue
                r = managed(
                    rH,
                    rL,
                    j,
                    t["d"],
                    t["fill"],
                    t["far"],
                    t["lv"]["TP1"],
                    t["lv"]["TP2"],
                    t["open_fill"] and j == t["m"],
                )
                if r is not None:
                    items.append((t["d"], r))
            lines.append((f"sniper, {wname}, {gname}", mcell(items, ctrl, f"sn|{wname}|{gname}")))

    print(
        f"\nENTRY MODELS — first touch, gates, no weekend, before costs; a limit fills only when "
        f"price trades ${x:.2f} through it"
    )
    print("stop$ = median stop distance in dollars | TP1 R = median reward to TP1 in stops")
    print(
        "b/even = the win rate that breaks even (also what a random walk scores on that bracket)\n"
    )
    print("WIN RATES")
    print(MHDR1)
    cells = [(label, mfmt(label, c)) for label, c in lines]
    for i, (label, (a, _)) in enumerate(cells):
        if i and i % 3 == 0:
            print()
        print(a)
    print("\nBREAK-EVEN AT TP1 — how trades end, and average R per trade for each way out")
    print(
        "  TP1 = all off at TP1 | TP2 = all to TP2, no management | BE = stop to entry at TP1, all to"
    )
    print("  TP2 | half = half off at TP1, stop to entry, half to TP2")
    print(MHDR2)
    for i, (label, (_, b)) in enumerate(cells):
        if i and i % 3 == 0:
            print()
        print(b)


def _sniper_items(snipes, rH, rL, x, keep):
    items = []
    for t in snipes:
        if not keep(t):
            continue
        j = through_fill(rH, rL, t["m"], t["d"], t["near"], x, t["lv"]["TP1"], t["open_fill"])
        if j is None:
            continue
        r = managed(
            rH,
            rL,
            j,
            t["d"],
            t["fill"],
            t["far"],
            t["lv"]["TP1"],
            t["lv"]["TP2"],
            t["open_fill"] and j == t["m"],
        )
        if r is not None:
            items.append((t["d"], r))
    return items


SHDR = (
    f"  {'':<44} {'n':>4} {'wins':>4}  {'TP1 win':>7} {'b/even':>6} {'random':>6} {'z':>5} "
    f"{'avgR':>6}   {'TP2 win':>7} {'b/even':>6} {'avgR':>6}  {'stop$':>5}"
)


def sfmt(label, c):
    if c is None:
        return f"  {label:<44} {'—':>4}"
    return (
        f"  {label:<44} {c['n']:>4} {round(c['win'] * c['n']):>4}  {100 * c['win']:>6.1f}% "
        f"{100 * c['rw']:>5.1f}% {100 * c['ctrl']:>5.1f}% {c['z']:>+5.2f} {c['R_tp1']:>+6.2f}   "
        f"{100 * c['tp2']:>6.1f}% {100 * c['rw2']:>5.1f}% {c['R_tp2']:>+6.2f}  {c['stop_usd']:>5.2f}"
    )


NEAR_BUCKETS = (
    (None, 0.500),
    (0.500, 0.618),
    (0.618, 0.702),
    (0.702, 0.786),
    (0.786, 0.886),
    (0.886, None),
)


def sweet_report(snipes, raw, x):
    """Where the sniper zone sits on the FFT fib, and which placement wins most."""
    ctrl = Control(raw)
    rH, rL = raw["high"].to_numpy(), raw["low"].to_numpy()
    base = lambda t, mb=None: gated(t, max_bos=mb)  # noqa: E731
    ov = lambda t: t["pos_near"] <= 0.886 and t["pos_far"] >= 0.618  # noqa: E731

    def show(label, keep, tag):
        print(sfmt(label, mcell(_sniper_items(snipes, rH, rL, x, keep), ctrl, tag)))

    print("\nSNIPER ENTRY — near edge, stop past the far edge, FFT TP1 / TP2; gates, no weekend;")
    print(
        f"a limit fills once price trades ${x:.2f} through it; before costs. wins = TP1 before the stop\n"
    )
    print("OVERLAPS 61.8-88.6 (any overlap, need not fit inside)")
    print(SHDR)
    for gname, mb in (("any BOS", None), ("at most 1 BOS", 1), ("0 BOS (first leg)", 0)):
        show(f"overlaps 61.8-88.6, {gname}", lambda t, mb=mb: base(t, mb) and ov(t), f"ov|{gname}")
    for k in (1, 2):
        show(
            f"overlaps 61.8-88.6, exactly {k} BOS",
            lambda t, k=k: base(t) and ov(t) and t["nbos"] == k,
            f"ov|{k}",
        )
    show("overlaps 61.8-88.6, 3+ BOS", lambda t: base(t) and ov(t) and t["nbos"] >= 3, "ov|3+")
    show("does NOT overlap 61.8-88.6 (reference)", lambda t: base(t) and not ov(t), "nov")

    for gname, mb in (("any BOS", None), ("0 BOS (first leg)", 0)):
        print(f"\nSWEET SPOT — where the zone's NEAR edge (the entry) sits on the FFT fib, {gname}")
        print(SHDR)
        for lo, hi in NEAR_BUCKETS:
            name = (
                f"entry shallower than {hi}"
                if lo is None
                else f"entry deeper than {lo}"
                if hi is None
                else f"entry at {lo}-{hi}"
            )
            keep = lambda t, lo=lo, hi=hi, mb=mb: (
                base(t, mb)
                and (lo is None or t["pos_near"] >= lo)
                and (hi is None or t["pos_near"] < hi)
            )
            show(name, keep, f"nb|{lo}|{hi}|{gname}")
        print(f"  by where the STOP (far edge) sits, {gname}:")
        for lo, hi in NEAR_BUCKETS:
            name = (
                f"stop shallower than {hi}"
                if lo is None
                else f"stop deeper than {lo}"
                if hi is None
                else f"stop at {lo}-{hi}"
            )
            keep = lambda t, lo=lo, hi=hi, mb=mb: (
                base(t, mb)
                and (lo is None or t["pos_far"] >= lo)
                and (hi is None or t["pos_far"] < hi)
            )
            show(name, keep, f"fb|{lo}|{hi}|{gname}")


IHDR = (
    f"  {'':<34} {'n':>4}  {'TP1 win':>7} {'avgR':>6}   {'TP2 win':>7} {'b/e':>6} {'avgR':>6} "
    f"{'rand':>6}   {'TP3 win':>7} {'b/e':>6} {'avgR':>6} {'rand':>6}"
)


def ifmt(label, c):
    if c is None:
        return f"  {label:<34} {'—':>4}"
    t3 = (
        f"{100 * c['tp3']:>6.1f}% {100 * c['rw3']:>5.1f}% {c['R_tp3']:>+6.2f} {c['C_tp3']:>+6.2f}"
        if "tp3" in c
        else ""
    )
    return (
        f"  {label:<34} {c['n']:>4}  {100 * c['win']:>6.1f}% {c['R_tp1']:>+6.2f}   "
        f"{100 * c['tp2']:>6.1f}% {100 * c['rw2']:>5.1f}% {c['R_tp2']:>+6.2f} {c['C_tp2']:>+6.2f}   "
        + t3
    )


def _model_a(touches, rH, rL):
    """61.8 entry, stop 1.0, first leg (0 BOS), gates, no weekend — touch fill."""
    out = []
    for t in touches:
        if t["kind"] != "first" or not gated(t, max_bos=0):
            continue
        lv = t["lv"]
        r = managed(
            rH,
            rL,
            t["m"],
            t["d"],
            t["fill"],
            lv["1.0"],
            lv["TP1"],
            lv["TP2"],
            t["open_fill"],
            lv["TP3"],
        )
        if r is not None:
            out.append((t, r))
    return out


def _model_b(snipes, rH, rL, x=0.10):
    """Sniper zone overlapping 61.8-88.6, at most 1 BOS, gates, no weekend — $0.10 through."""
    out = []
    for t in snipes:
        if not (gated(t, max_bos=1) and t["pos_near"] <= 0.886 and t["pos_far"] >= 0.618):
            continue
        j = through_fill(rH, rL, t["m"], t["d"], t["near"], x, t["lv"]["TP1"], t["open_fill"])
        if j is None:
            continue
        r = managed(
            rH,
            rL,
            j,
            t["d"],
            t["fill"],
            t["far"],
            t["lv"]["TP1"],
            t["lv"]["TP2"],
            t["open_fill"] and j == t["m"],
            t["lv"]["TP3"],
        )
        if r is not None:
            out.append((t, r))
    return out


def improve_report(recent):
    """The five pre-declared refinements, judged on 2020-25 and checked on the recent year with the
    SAME cut-offs (terciles of 2020-25). An idea survives only if both windows agree."""
    windows = [("2020-01 -> 2025-08", "2020-01-01", "2025-09-01"), ("recent year", *recent)]
    data = []
    for name, a, b in windows:
        touches, snipes, raw, _ = run(a, b)
        rH, rL = raw["high"].to_numpy(), raw["low"].to_numpy()
        data.append(
            (
                name,
                raw,
                _model_a(touches, rH, rL),
                _model_b(snipes, rH, rL),
                [
                    (t, t["conf"])
                    for t in touches
                    if t["kind"] == "first" and gated(t, max_bos=0) and t["conf"] is not None
                ],
            )
        )

    def cuts(items, key):
        v = [t[key] for t, _ in items if t[key] is not None]
        return np.quantile(v, [1 / 3, 2 / 3]) if v else (np.nan, np.nan)

    for mname, mi in (
        ("MODEL A — 61.8 entry, stop 1.0, first leg", 2),
        ("MODEL B — sniper overlapping 61.8-88.6, first/second leg, $0.10 through", 3),
    ):
        dev_items = data[0][mi]
        ci, cp = cuts(dev_items, "impulse"), cuts(dev_items, "pb_min")
        print(f"\n{mname}")
        print(
            f"  cut-offs from 2020-25: impulse (leg / 5m ATR14) {ci[0]:.1f} | {ci[1]:.1f};  "
            f"pullback {cp[0]:.0f} | {cp[1]:.0f} minutes"
        )
        for name, raw, *models in data:
            items = models[mi - 2]
            ctrl = Control(raw)
            print(f"\n  {name}")
            print(IHDR)
            rows = [
                ("base", lambda t: True),
                (
                    "impulse weak (bottom third)",
                    lambda t: t["impulse"] is not None and t["impulse"] < ci[0],
                ),
                (
                    "impulse middle",
                    lambda t: t["impulse"] is not None and ci[0] <= t["impulse"] < ci[1],
                ),
                (
                    "impulse strong (top third)",
                    lambda t: t["impulse"] is not None and t["impulse"] >= ci[1],
                ),
                (
                    "15m discount (deeper than 50)",
                    lambda t: t["depth15"] is not None and t["depth15"] > 0.5,
                ),
                (
                    "15m premium (50 or shallower)",
                    lambda t: t["depth15"] is not None and t["depth15"] <= 0.5,
                ),
                ("pullback fast (bottom third)", lambda t: t["pb_min"] < cp[0]),
                ("pullback middle", lambda t: cp[0] <= t["pb_min"] < cp[1]),
                ("pullback slow (top third)", lambda t: t["pb_min"] >= cp[1]),
            ]
            for label, keep in rows:
                sub = [(t["d"], r) for t, r in items if keep(t)]
                print(ifmt(label, mcell(sub, ctrl, f"imp|{mname}|{label}")))
            if mi == 2:
                conf = models[2]
                print(
                    ifmt(
                        "1m CONFIRMATION entry (idea 5)",
                        mcell([(t["d"], r) for t, r in conf], ctrl, "imp|conf"),
                    )
                )
                if conf:
                    print(
                        f"    confirmation: {len(conf)} of {len(items)} touches confirmed; median stop "
                        f"${np.median([r['risk'] for _, r in conf]):.2f} vs "
                        f"${np.median([r['risk'] for _, r in items]):.2f} for the 61.8 limit"
                    )


def _curve(rs):
    """Total, max drawdown (peak to trough of the running sum) and the setups that made money."""
    c = np.cumsum(rs) if len(rs) else np.array([0.0])
    dd = (
        float(np.max(np.maximum.accumulate(np.concatenate([[0.0], c]))[1:] - c)) if len(rs) else 0.0
    )
    return float(c[-1]), dd


def legs15_report(recent):
    """Which 15m leg to trade (2026-09-21), the way the 5m leg was chosen: the 15m trend's continuation
    BOS since its shift at the fill, crossed with the 5m leg. Model A (61.8, stop 1.0) and model B
    (sniper overlapping 61.8-88.6, $0.10 through). A 15m filter is kept only if both windows agree."""
    windows = [("2020-01 -> 2025-08", "2020-01-01", "2025-09-01"), ("recent year", *recent)]
    b15 = (
        ("15m first leg (0 BOS)", lambda n: n == 0),
        ("15m 1 BOS", lambda n: n == 1),
        ("15m 2 BOS", lambda n: n == 2),
        ("15m 3+ BOS", lambda n: n >= 3),
        ("15m at most 1 BOS", lambda n: 0 <= n <= 1),
    )
    for name, a, b in windows:
        touches, snipes, raw, _ = run(a, b)
        rH, rL = raw["high"].to_numpy(), raw["low"].to_numpy()
        ctrl = Control(raw)
        allA = []
        for t in touches:
            if t["kind"] != "first" or not gated(t):
                continue
            lv = t["lv"]
            r = managed(
                rH,
                rL,
                t["m"],
                t["d"],
                t["fill"],
                lv["1.0"],
                lv["TP1"],
                lv["TP2"],
                t["open_fill"],
                lv["TP3"],
            )
            if r is not None:
                allA.append((t, r))
        print(f"\n=== {name} — MODEL A: 61.8 entry, stop 1.0 (gates, no weekend, before costs)")
        print(IHDR)
        for l5, f5 in (
            ("5m any leg", lambda n: True),
            ("5m first leg", lambda n: n == 0),
            ("5m at most 1 BOS", lambda n: n <= 1),
        ):
            sub = [(t["d"], r) for t, r in allA if f5(t["nbos"])]
            print(ifmt(f"{l5}, 15m any", mcell(sub, ctrl, f"l15|A|{l5}|any")))
            for l15, f15 in b15:
                sub = [(t["d"], r) for t, r in allA if f5(t["nbos"]) and f15(t["n15"])]
                print(ifmt(f"  {l15}", mcell(sub, ctrl, f"l15|A|{l5}|{l15}")))
        print(f"\n=== {name} — MODEL B: sniper overlapping 61.8-88.6, $0.10 through")
        print(IHDR)
        allB = _model_b(snipes, rH, rL)  # 5m at most 1 BOS
        print(
            ifmt(
                "5m at most 1 BOS, 15m any",
                mcell([(t["d"], r) for t, r in allB], ctrl, "l15|B|any"),
            )
        )
        for l15, f15 in b15:
            sub = [(t["d"], r) for t, r in allB if f15(t["n15"])]
            print(ifmt(f"  {l15}", mcell(sub, ctrl, f"l15|B|{l15}")))


def _clock_flags(times):
    """Session / kill-zone / session-open / news flags for each fill time (UTC-naive), from the
    canonical sessions and news engines — no second clock. Session opens use the engines' own opens:
    London 08:00 London time, New York 08:00 NY time, and the 09:30 NY equity open."""
    from zoneinfo import ZoneInfo

    from news import NewsEngine, NewsPolicy
    from news.store import EventStore
    from sessions import SessionEngine

    events, cov = EventStore().load()
    policy = NewsPolicy.gold()
    usd_days = {
        pd.Timestamp(e.timestamp_ms, unit="ms", tz="UTC").tz_convert(NY).date()
        for e in events
        if policy.matches(e)
    }
    ld = ZoneInfo("Europe/London")
    order = sorted(set(times))
    se, ne = SessionEngine(), NewsEngine(events, policy=policy, covered_ranges=cov)
    out = {}
    for i, ts in enumerate(order):
        utc = pd.Timestamp(ts).tz_localize("UTC")
        ms = int(utc.value // 10**6)
        sv, nv = se.update(i, ms, 0.0, 0.0), ne.update(i, ms)
        ny, lo = utc.tz_convert(NY), utc.tz_convert(ld)
        nym, lom = ny.hour * 60 + ny.minute, lo.hour * 60 + lo.minute
        out[ts] = dict(
            asia=sv.in_asia,
            london=sv.in_london,
            nyses=sv.in_ny,
            kz=sv.in_kz1 or sv.in_kz2 or sv.in_kz3,
            kz1=sv.in_kz1,
            kz2=sv.in_kz2,
            kz3=sv.in_kz3,
            lon_open=480 <= lom < 540,
            ny_open=480 <= nym < 540,
            eq_open=570 <= nym < 630,
            news=bool(nv.in_blackout),
            news_cov=bool(nv.has_coverage),
            news_day=ny.date() in usd_days,
        )
    return out


def clock_report(recent):
    """Kill zones, sessions, session opens and news (the user, 2026-09-21), on model A — first leg,
    and any leg for a bigger sample. Buckets fixed before the run; kept only if both windows agree."""
    windows = [("2020-01 -> 2025-08", "2020-01-01", "2025-09-01"), ("recent year", *recent)]
    for name, a, b in windows:
        touches, _, raw, _ = run(a, b)
        rH, rL = raw["high"].to_numpy(), raw["low"].to_numpy()
        ctrl = Control(raw)
        allA = []
        for t in touches:
            if t["kind"] != "first" or not gated(t):
                continue
            lv = t["lv"]
            r = managed(
                rH,
                rL,
                t["m"],
                t["d"],
                t["fill"],
                lv["1.0"],
                lv["TP1"],
                lv["TP2"],
                t["open_fill"],
                lv["TP3"],
            )
            if r is not None:
                allA.append((t, r))
        fl = _clock_flags([t["t"] for t, _ in allA])
        cov = sum(fl[t["t"]]["news_cov"] for t, _ in allA)
        buckets = [
            ("SESSION: Asia only", lambda f: f["asia"] and not f["london"] and not f["nyses"]),
            ("SESSION: London only", lambda f: f["london"] and not f["nyses"]),
            ("SESSION: London + NY overlap", lambda f: f["london"] and f["nyses"]),
            ("SESSION: NY only", lambda f: f["nyses"] and not f["london"]),
            ("SESSION: off-session", lambda f: not (f["asia"] or f["london"] or f["nyses"])),
            ("KILL ZONE: any of the three", lambda f: f["kz"]),
            ("KILL ZONE: none", lambda f: not f["kz"]),
            ("  KZ1 10:00-11:00 NY", lambda f: f["kz1"]),
            ("  KZ2 11:45-12:15 NY", lambda f: f["kz2"]),
            ("  KZ3 13:00-13:30 NY", lambda f: f["kz3"]),
            ("OPEN: first hour of London", lambda f: f["lon_open"]),
            ("OPEN: first hour of New York", lambda f: f["ny_open"]),
            ("OPEN: 09:30-10:30 NY equity open", lambda f: f["eq_open"]),
            (
                "OPEN: none of the three",
                lambda f: not (f["lon_open"] or f["ny_open"] or f["eq_open"]),
            ),
            ("NEWS: within 30 min of USD high", lambda f: f["news"]),
            ("NEWS: USD high-impact day", lambda f: f["news_day"] and not f["news"]),
            ("NEWS: quiet day", lambda f: not f["news_day"]),
        ]
        for mname, keep5 in (
            ("first leg (0 BOS)", lambda t: t["nbos"] == 0),
            ("any 5m leg", lambda t: True),
        ):
            print(
                f"\n=== {name} — MODEL A, 61.8 entry, stop 1.0, 5m {mname} (news covered for {cov} of "
                f"{len(allA)} setups)"
            )
            print(IHDR)
            base = [(t, r) for t, r in allA if keep5(t)]
            print(ifmt("all", mcell([(t["d"], r) for t, r in base], ctrl, f"clk|{mname}|all")))
            for label, f in buckets:
                sub = [(t["d"], r) for t, r in base if f(fl[t["t"]])]
                print(ifmt(label, mcell(sub, ctrl, f"clk|{mname}|{label}")))


def second_sweep_report(recent):
    """The second touch on first-leg setups, and a liquidity sweep before the touch (2026-09-21)."""
    windows = [("2020-01 -> 2025-08", "2020-01-01", "2025-09-01"), ("recent year", *recent)]
    tp2 = ("61.8", "1.0", "TP2 38.2")
    for name, a, b in windows:
        touches, _, raw, _ = run(a, b)
        rH, rL = raw["high"].to_numpy(), raw["low"].to_numpy()
        ctrl = Control(raw)

        def item(t):
            lv = t["lv"]
            return managed(
                rH,
                rL,
                t["m"],
                t["d"],
                t["fill"],
                lv["1.0"],
                lv["TP1"],
                lv["TP2"],
                t["open_fill"],
                lv["TP3"],
            )

        first = [(t, item(t)) for t in touches if t["kind"] == "first" and gated(t, max_bos=0)]
        first = [(t, r) for t, r in first if r is not None]
        exit_of = {t["key"]: t["res"][tp2]["exit"] for t, _ in first if tp2 in t["res"]}
        second = [(t, item(t)) for t in touches if t["kind"] == "second" and gated(t, max_bos=0)]
        second = [(t, r) for t, r in second if r is not None]
        flat = [(t, r) for t, r in second if t["key"] in exit_of and exit_of[t["key"]] < t["m"]]

        print(
            f"\n=== {name} — SECOND TOUCH, first leg, 61.8 entry, stop 1.0 (after the first touch reached TP1)"
        )
        print(IHDR)
        print(ifmt("first touch", mcell([(t["d"], r) for t, r in first], ctrl, "ss|first")))
        print(ifmt("second touch, all", mcell([(t["d"], r) for t, r in second], ctrl, "ss|second")))
        print(
            ifmt(
                "second touch, first trade closed",
                mcell([(t["d"], r) for t, r in flat], ctrl, "ss|flat"),
            )
        )
        print(
            f"  second touches while the first trade (TP2 plan) was still open: {len(second) - len(flat)} "
            f"of {len(second)} — taking those would double the risk on one leg"
        )
        for tgt, key, rk in (("TP2", "tp2", "r2"), ("TP1", "tp1", "r1")):
            res = lambda r: r[rk] if r[key] else -1.0  # noqa: E731
            only = sorted(first, key=lambda x: x[0]["t"])
            both = sorted(first + flat, key=lambda x: x[0]["t"])
            for label, xs in (
                ("plan: first touch only", only),
                ("plan: + second touch when flat", both),
            ):
                tot, dd = _curve([res(r) for _, r in xs])
                print(
                    f"  {label:<32} {tgt}: {len(xs):>4} trades  total {tot:+7.2f}R  max DD {dd:5.2f}R"
                )

        print(
            f"\n=== {name} — LIQUIDITY SWEEP before the touch (day / session / H4 level on the pullback side)"
        )
        print(IHDR)
        for lname, keep5 in (
            ("first leg", lambda t: t["nbos"] == 0),
            ("any 5m leg", lambda t: True),
        ):
            base = []
            for t in touches:
                if t["kind"] == "first" and gated(t) and keep5(t):
                    r = item(t)
                    if r is not None:
                        base.append((t, r))
            for label, f in (
                ("all", lambda t: True),
                ("swept a level on the way in", lambda t: t["swept"]),
                ("  the swept level sat at/past 61.8", lambda t: t["swept_deep"]),
                ("no sweep", lambda t: not t["swept"]),
            ):
                sub = [(t["d"], r) for t, r in base if f(t)]
                print(ifmt(f"{lname}: {label}", mcell(sub, ctrl, f"sw|{lname}|{label}")))


def v1_costed(t, rH, rL, profile, tgt_key):
    """Version 1 (2026-09-21) through PU Prime ECN: charts are BID, so a buy limit at 61.8 fills only
    once the bid trades one spread below it (the ask reaches it), and a sell's stop and target
    trigger one spread early (the ask reaches them). Commission both sides; swap per rollover held
    (17:00 NY, the triple night on the profile's day). R is the planned risk: 61.8 to the 1.0."""
    from backtest.reprice import rollovers_between

    lv, d = t["lv"], t["d"]
    sp = profile.spread
    entry, stop, tgt = lv["E1"], lv["1.0"], lv[tgt_key]
    if t["open_fill"]:
        return None  # a gap-through fill at the open — a handful; kept out of the costed book
    if d == 1:
        j = through_fill(rH, rL, t["m"], d, entry, sp, lv["TP1"], False)
        if j is None:
            return "nofill"
        r = walk(rH, rL, j, d, stop, tgt, False)
    else:
        j = t["m"]
        r = walk(rH, rL, j, d, stop - sp, tgt - sp, False)
    if r is None:
        return None
    risk = abs(entry - stop)
    gross = abs(tgt - entry) / risk if r[0] else -1.0
    comm = 2 * profile.commission_per_side_per_lot / profile.contract_size

    def ms(i):
        return int(pd.Timestamp(_T1[i]).tz_localize("UTC").value // 10**6)

    swap = sum(
        profile.swap.charge(d, 1.0, day) / profile.contract_size
        for day in rollovers_between(ms(j), ms(r[2]), 17)
    )
    return dict(
        gross=gross,
        net=gross + (swap - comm) / risk,
        cost=(comm - swap) / risk,
        win=r[0],
        risk=risk,
    )


_T1 = None  # the 1m clock of the last run, for v1_costed's swap dates


def v1_report(windows, costs):
    """Version 1 frozen (2026-09-21): first touch, gates, no weekend, 5m first leg, 61.8 limit, stop
    1.0, TP2 (TP1 beside it). Cost-free with the random control; then, for gold, through PU Prime
    ECN. Nothing here is tuned — it is the checklist in notes/fft_ledger.md, run as written."""
    global _T1
    from backtest.fills import PROFILES

    for name, a, b in windows:
        touches, _, raw, _ = run(a, b)
        _T1 = raw.index.to_numpy()
        rH, rL = raw["high"].to_numpy(), raw["low"].to_numpy()
        ctrl = Control(raw)
        rows = [t for t in touches if t["kind"] == "first" and gated(t, max_bos=0)]
        items = []
        for t in rows:
            lv = t["lv"]
            r = managed(
                rH,
                rL,
                t["m"],
                t["d"],
                t["fill"],
                lv["1.0"],
                lv["TP1"],
                lv["TP2"],
                t["open_fill"],
                lv["TP3"],
            )
            if r is not None:
                items.append((t, r))
        cut = pd.Timestamp(a) + (pd.Timestamp(b) - pd.Timestamp(a)) / 2
        print(f"\n=== {SYMBOL} {name} — VERSION 1, before costs")
        print(IHDR)
        for label, keep, tag in (
            ("buys and sells", lambda t: True, "v1|all"),
            ("buys", lambda t: t["d"] == 1, "v1|b"),
            ("sells", lambda t: t["d"] == -1, "v1|s"),
            ("first half", lambda t: t["t"] < cut, "v1|h1"),
            ("second half", lambda t: t["t"] >= cut, "v1|h2"),
            ("  A+ (a liquidity sweep on the way in)", lambda t: t["swept"], "v1|sw"),
        ):
            print(ifmt(label, mcell([(t["d"], r) for t, r in items if keep(t)], ctrl, tag)))
        if items:
            months = max((pd.Timestamp(b) - pd.Timestamp(a)).days / 30.44, 1)
            print(
                f"  median stop {np.median([r['risk'] for _, r in items]):.3f} in price; "
                f"{len(items) / months:.1f} setups a month"
            )
        if not costs:
            continue
        prof = PROFILES["puprime_ecn"]
        print(
            f"\n  THROUGH PU PRIME ECN — spread ${prof.spread:.2f} (bid chart), commission "
            f"${prof.commission_per_side_per_lot:.2f}/side/lot, swap per rollover"
        )
        for tk in ("TP2", "TP1"):
            res = [v1_costed(t, rH, rL, prof, tk) for t in rows]
            got = [x for x in res if isinstance(x, dict)]
            nofill = sum(1 for x in res if x == "nofill")
            if not got:
                continue
            g = float(np.mean([x["gross"] for x in got]))
            nt = float(np.mean([x["net"] for x in got]))
            w = sum(x["win"] for x in got) / len(got)
            tot = float(np.sum([x["net"] for x in got]))
            _, dd = _curve([x["net"] for x in got])
            cst = float(np.mean([x["cost"] for x in got]))
            print(
                f"  {tk}: {len(got)} trades ({nofill} buy limits never reached by the ask), win {100 * w:.1f}%, "
                f"avgR {g:+.3f} before costs -> {nt:+.3f} after ({cst:.3f}R a trade); "
                f"total {tot:+.2f}R, max DD {dd:.2f}R"
            )


def scalein_report(recent):
    """The user's scale-in (2026-09-21), FROZEN before the run: one trade's risk split 50/50 — half on
    the 61.8 limit (stop 1.0), half added only when the 1m breaks back after the touch (stop at the
    extreme since the touch). Model A setups: first leg, gates, no weekend. Compared with the whole
    risk on the limit, and the whole risk on the confirmation only. R is in units of ONE trade's full
    risk budget, so the three rows risk the same money per setup at most."""
    windows = [("2020-01 -> 2025-08", "2020-01-01", "2025-09-01"), ("recent year", *recent)]
    print(
        "\nSCALE-IN — first leg setups; R per setup in units of one full trade risk; before costs"
    )
    for name, a, b in windows:
        touches, _, raw, _ = run(a, b)
        rH, rL = raw["high"].to_numpy(), raw["low"].to_numpy()
        setups = sorted(_model_a(touches, rH, rL), key=lambda x: x[0]["t"])
        print(
            f"\n  {name}: {len(setups)} setups, {sum(t['conf'] is not None for t, _ in setups)} confirmed"
        )
        print(
            f"  {'':<34} {'target':<6} {'trades':>6} {'total R':>8} {'R/setup':>8} {'won':>6} "
            f"{'lost':>6} {'max DD':>7} {'total/DD':>8} {'risk used':>9}"
        )
        for tgt, key, rk in (("TP2", "tp2", "r2"), ("TP1", "tp1", "r1")):
            res = lambda r: r[rk] if r[key] else -1.0  # noqa: E731
            plans = {
                "all on the 61.8 limit": [(res(r), 1.0) for t, r in setups],
                "all on the 1m confirmation": [
                    ((res(t["conf"]), 1.0) if t["conf"] is not None else (0.0, 0.0))
                    for t, r in setups
                ],
                "scale-in 50/50  <- the test": [
                    (
                        (0.5 * res(r) + (0.5 * res(t["conf"]) if t["conf"] is not None else 0.0)),
                        0.5 + (0.5 if t["conf"] is not None else 0.0),
                    )
                    for t, r in setups
                ],
            }
            for label, xs in plans.items():
                rs = [x for x, _ in xs]
                tot, dd = _curve(rs)
                taken = sum(1 for _, u in xs if u > 0)
                won = sum(1 for x, u in xs if u > 0 and x > 0) / max(taken, 1)
                lost = sum(1 for x, u in xs if u > 0 and x < 0) / max(taken, 1)
                used = float(np.mean([u for _, u in xs]))
                print(
                    f"  {label:<34} {tgt:<6} {taken:>6} {tot:>+8.2f} {tot / len(xs):>+8.3f} "
                    f"{100 * won:>5.1f}% {100 * lost:>5.1f}% {dd:>7.2f} "
                    f"{(tot / dd if dd > 0 else float('inf')):>8.2f} {100 * used:>8.0f}%"
                )


def listing(touches, n):
    """The last n first touches under the rule, New York time, for checking against a chart."""
    rows = [t for t in touches if t["kind"] == "first" and gated(t, max_bos=MAX_BOS)]
    print(f"\nLAST {n} FIRST TOUCHES UNDER THE RULE (New York time; 61.8 fill, stop 1.0)")
    print(
        f"  {'time (NY)':<17} {'side':<5} {'fill':>9} {'stop 1.0':>9} {'TP1 50':>9} {'TP2 38.2':>9}"
        f"  {'TP1':<5} {'TP2':<5} sniper fvg  5m BOS"
    )
    for t in rows[-n:]:
        r1, r2 = t["res"].get(("61.8", "1.0", "TP1 50")), t["res"].get(("61.8", "1.0", "TP2 38.2"))
        lv = t["lv"]
        ny = t["t"].tz_localize("UTC").tz_convert(NY).strftime("%Y-%m-%d %H:%M")
        w = lambda r: "-" if r is None else ("WIN" if r["win"] else "loss")  # noqa: E731
        print(
            f"  {ny:<17} {'buy' if t['d'] == 1 else 'sell':<5} {t['fill']:>9.2f} {lv['1.0']:>9.2f} "
            f"{lv['TP1']:>9.2f} {lv['TP2']:>9.2f}  {w(r1):<5} {w(r2):<5} "
            f"{'yes' if t['sniper'] else '-':<6} {'yes' if t['fvg'] else '-':<4} {t['nbos']}"
        )


def holdout_report(touches, raw):
    """The frozen claim only — no other cell is printed, so nothing can be shopped on this window."""
    ctrl = Control(raw)
    first = [t for t in touches if t["kind"] == "first"]
    claim = [t for t in first if gated(t, max_bos=0)]
    context = [t for t in first if gated(t)]
    print("\nHOLDOUT — the frozen claim (see the docstring), 61.8 fill, stop 1.0, before costs")
    print(HDR)
    ok = []
    for tag, combo in (
        ("TP1 50", ("61.8", "1.0", "TP1 50")),
        ("TP2 38.2", ("61.8", "1.0", "TP2 38.2")),
    ):
        c = cell(claim, combo, ctrl)
        print(fmt(f"CLAIM: 0 BOS  [{tag}]", c))
        print(fmt(f"context: any BOS  [{tag}]", cell(context, combo, ctrl)))
        ok.append(c is not None and c["win"] > c["rw"] and c["win"] > c["ctrl"] and c["avg_r"] > 0)
    print(
        f"\n  verdict: {'PASS' if all(ok) else 'FAIL'} (TP1 {'ok' if ok[0] else 'fails'}, "
        f"TP2 {'ok' if ok[1] else 'fails'})"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2025-09-01")
    ap.add_argument("--list", type=int, default=0, help="print the last N gated first touches")
    ap.add_argument(
        "--entries",
        action="store_true",
        help="the sniper-zone entry vs the 61.8 entry, with break-even at TP1",
    )
    ap.add_argument(
        "--v1",
        action="store_true",
        help="version 1 as frozen in notes/fft_ledger.md; gold adds PU Prime ECN costs",
    )
    ap.add_argument(
        "--symbol",
        default="XAUUSD_p",
        help="cache symbol for --v1 (XAGUSD_p = silver: no measured costs, cost-free)",
    )
    ap.add_argument(
        "--second-sweep",
        dest="second_sweep",
        action="store_true",
        help="the second touch on first-leg setups, and a liquidity sweep (2026-09-21)",
    )
    ap.add_argument(
        "--clock",
        action="store_true",
        help="kill zones, sessions, session opens and news (2026-09-21)",
    )
    ap.add_argument(
        "--legs15",
        action="store_true",
        help="which 15m leg to trade, crossed with the 5m leg (2026-09-21)",
    )
    ap.add_argument(
        "--scalein",
        action="store_true",
        help="half on the 61.8 limit, half added on the 1m confirmation (2026-09-21)",
    )
    ap.add_argument(
        "--improve",
        action="store_true",
        help="the five pre-declared refinements, both windows (2026-09-21)",
    )
    ap.add_argument(
        "--sweet",
        action="store_true",
        help="where the sniper zone sits on the FFT fib, and which placement wins most",
    )
    ap.add_argument(
        "--through",
        type=float,
        default=0.0,
        help="dollars price must trade through a limit to fill it (0 = the touch)",
    )
    ap.add_argument(
        "--holdout", action="store_true", help="the ONE run of the frozen claim on 2018-19"
    )
    a = ap.parse_args()
    if a.improve:
        improve_report(("2025-09-01", "2026-09-17"))
        return
    if a.scalein:
        scalein_report(("2025-09-01", "2026-09-17"))
        return
    if a.legs15:
        legs15_report(("2025-09-01", "2026-09-17"))
        return
    if a.clock:
        clock_report(("2025-09-01", "2026-09-17"))
        return
    if a.second_sweep:
        second_sweep_report(("2025-09-01", "2026-09-17"))
        return
    if a.v1:
        global SYMBOL
        SYMBOL = a.symbol
        if SYMBOL == "XAUUSD_p":
            windows = [
                ("2020-01 -> 2025-08", "2020-01-01", "2025-09-01"),
                ("recent year", "2025-09-01", "2026-09-17"),
            ]
        else:  # another market: its whole cached history is new data for this rule
            windows = [("2020-01 -> 2026-09, all of it", "2020-01-01", "2026-09-17")]
        v1_report(windows, costs=(SYMBOL == "XAUUSD_p"))
        return
    if a.holdout:
        touches, _, raw, t0 = run(*HOLDOUT, holdout=True)
        holdout_report(touches, raw)
        print(f"\ntotal {time.time() - t0:.0f}s")
        return
    touches, snipes, raw, t0 = run(a.start, a.end)
    if a.sweet:
        sweet_report(snipes, raw, a.through)
        print(f"\ntotal {time.time() - t0:.0f}s")
        return
    if a.entries:
        entries_report(touches, snipes, raw, a.through)
        print(f"\ntotal {time.time() - t0:.0f}s")
        return
    report(touches, raw)
    if a.list:
        listing(touches, a.list)
    print(f"\ntotal {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
