#!/usr/bin/env python3
"""WHEN does the with-trend break of structure print, relative to the money?

Aaron's point: a no-gap setup that goes on to make 1R has by definition broken structure.
If so, the break is a CONSEQUENCE of the move, and the only question that matters is how
much of the move is already gone by the time it prints. This measures that directly.

For each of the 195 no-gap setups, from arrival in the zone: find the FIRST with-trend
external break on the 15m, the 5m and the 1m, and record how far price had ALREADY travelled
(in R, entry 0.5, stop the 15m 1.0) at that moment. Then the outcome of entering THERE.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "engines"))

from market_structure import Bar, StructureEngine  # noqa: E402

from backtest.data.cache import BarCache  # noqa: E402

CACHE = Path("/Users/alwg/trading/backtest/cache/VantageMarkets_Demo")
START, END = "2020-01-01", "2026-08-06"
rows_in = pickle.load(open("nogap_arrivals.pkl", "rb"))


def breaks(tf):
    """(timestamps, prices, dir) of every external BOS/SOS the engine prints on this frame."""
    df = BarCache(CACHE).load("XAUUSD", tf).loc[START:END]
    ms = np.asarray(df.index.view("int64") // 10**6)
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    eng = StructureEngine(major_length=15)
    t, p, d = [], [], []
    for i in range(len(df)):
        st = eng.update(Bar(index=i, open=o[i], high=h[i], low=l[i], close=c[i]))
        e = st.external
        if e.bull_bos or e.bull_sos:
            t.append(ms[i])
            p.append(c[i])
            d.append(1)
        if e.bear_bos or e.bear_sos:
            t.append(ms[i])
            p.append(c[i])
            d.append(-1)
    return np.array(t), np.array(p), np.array(d)


df1 = BarCache(CACHE).load("XAUUSD", "M1").loc[START:END]
ms1 = np.asarray(df1.index.view("int64") // 10**6)
hi, lo = df1["high"].to_numpy(), df1["low"].to_numpy()
HORIZON = 7200

for tf in ("M15", "M5", "M1"):
    bt, bp, bd = breaks(tf)
    already, after, n_none = [], [], 0
    for (d, _sos), v in rows_in.items():
        stop, extreme, t0 = v["stop"], v["extreme"], v["t0"]
        half = (stop + extreme) / 2.0
        risk = abs(half - stop)
        if risk <= 0:
            continue
        # the first with-trend break after arrival, before the 1.0 is touched
        i0 = np.searchsorted(ms1, t0)
        stop_ms = None
        for i in range(i0, min(len(ms1), i0 + HORIZON)):
            if (d == 1 and lo[i] <= stop) or (d == -1 and hi[i] >= stop):
                stop_ms = ms1[i]
                break
        sel = np.where((bt >= t0) & (bd == d) & ((bt <= stop_ms) if stop_ms else True))[0]
        if not len(sel):
            n_none += 1
            continue
        j = sel[0]
        e_px = bp[j]
        already.append(((e_px - half) / risk) if d == 1 else ((half - e_px) / risk))
        # entering AT that break, same stop, 3R target on the ORIGINAL risk
        k0 = np.searchsorted(ms1, bt[j])
        got = False
        for i in range(k0, min(len(ms1), k0 + HORIZON)):
            if (d == 1 and lo[i] <= stop) or (d == -1 and hi[i] >= stop):
                break
            r = ((hi[i] - e_px) / risk) if d == 1 else ((e_px - lo[i]) / risk)
            if r >= 3.0:
                got = True
                break
        after.append(3.0 if got else -(abs(e_px - stop) / risk))
    a = np.array(already)
    print(f"\n{tf} — first with-trend break after arrival in the zone")
    print(f"  no break before the 1.0 was hit: {n_none} of {len(rows_in)}")
    print(f"  breaks found: {len(a)}")
    print(
        f"  R already travelled when it printed:  median {np.median(a):+.2f}R  "
        f"mean {a.mean():+.2f}R"
    )
    for thr in (0.0, 0.5, 1.0):
        print(
            f"    printed at or beyond {thr:+.1f}R: {int((a >= thr).sum()):4d}  "
            f"({(a >= thr).mean():5.1%})"
        )
    print(
        f"  entering AT the break, stop unchanged, 3R target: {sum(after):+.1f}R over {len(after)}"
    )
