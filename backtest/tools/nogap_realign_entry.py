#!/usr/bin/env python3
"""The REALIGN trigger used as the no-gap entry — with Realign's own STOP.

Runs 27-33 all entered on a single structure event and kept SOS Fade's wide stop at the 15m 1.0.
Run 34 showed no single event or ordered pair separates the winners. What is left, and what
Aaron asked for, is the OTHER half of Realign: its stop.

The setup: one of Run 32's 195 no-gap setups, price in the 0.5-0.886 zone, no gap to rest on.
The trigger (Realign's, on the 5m SWING stream - `realign_long_source="swing"`, which is the 5m's
own external structure, NOT the engine's internal events):

    1. a counter-direction external break (against the trade),
    2. then a with-trend external shift. That second event is the trigger.

Entry: market at the trigger bar's close.
Stop:  the counter-move extreme + `realign_sl_buf_tk` (20 ticks = $0.20 on XAUUSD), NOT the 15m 1.0.
Exits measured three ways: the 15m 0.0 extreme (the structural target), a fixed 3R, and a fixed 2R.
The setup is abandoned if the 15m 1.0 is touched first.

⚠ R here is Realign's own, off the tight stop, so these R are NOT comparable with Runs 27-34.
The account figure at the bottom is, because it is priced off the same risk budget.
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
HORIZON = 7200
BUF = 0.20  # realign_sl_buf_tk = 20 ticks
COST = 0.20  # flat, per trade, in price
SPLIT_MS = 1704067200000

rows_in = pickle.load(open("nogap_arrivals.pkl", "rb"))

df1 = BarCache(CACHE).load("XAUUSD", "M1").loc[START:END]
ms1 = np.asarray(df1.index.view("int64") // 10**6)
hi1, lo1 = df1["high"].to_numpy(), df1["low"].to_numpy()

df5 = BarCache(CACHE).load("XAUUSD", "M5").loc[START:END]
ms5 = np.asarray(df5.index.view("int64") // 10**6)
o5, h5, l5, c5 = (df5[k].to_numpy() for k in ("open", "high", "low", "close"))
eng = StructureEngine(major_length=15)
ev5 = []  # (bar, dir, is_shift)
for i in range(len(df5)):
    st = eng.update(Bar(index=i, open=o5[i], high=h5[i], low=l5[i], close=c5[i]))
    e = st.external
    if e.bull_bos:
        ev5.append((i, 1, False))
    if e.bull_sos:
        ev5.append((i, 1, True))
    if e.bear_bos:
        ev5.append((i, -1, False))
    if e.bear_sos:
        ev5.append((i, -1, True))
ev_bar = np.array([e[0] for e in ev5])
print(f"5m swing events: {len(ev5)}", flush=True)

trades = []
for (d, _sos), v in rows_in.items():
    stop15, extreme, t0 = v["stop"], v["extreme"], v["t0"]
    half = (stop15 + extreme) / 2.0
    # when does the setup die?
    i0 = np.searchsorted(ms1, t0)
    t_dead = None
    for i in range(i0, min(len(ms1), i0 + HORIZON)):
        if (d == 1 and lo1[i] <= stop15) or (d == -1 and hi1[i] >= stop15):
            t_dead = ms1[i]
            break
    if t_dead is None:
        t_dead = ms1[min(len(ms1) - 1, i0 + HORIZON - 1)]
    b0, b1 = np.searchsorted(ms5, t0), np.searchsorted(ms5, t_dead, side="right")
    sel = np.where((ev_bar >= b0) & (ev_bar < b1))[0]
    # the pattern: a counter break, THEN a with-trend shift
    counter_bar = None
    trig = None
    for j in sel:
        bar, ed, is_shift = ev5[j]
        if ed == -d:
            counter_bar = bar  # newest counter break replaces the old one
        elif ed == d and is_shift and counter_bar is not None:
            trig = (counter_bar, bar)
            break
    if trig is None:
        continue
    cb, tb = trig
    entry = c5[tb]
    # the counter-move extreme, between the counter break and the trigger
    seg = slice(cb, tb + 1)
    sl = (l5[seg].min() - BUF) if d == 1 else (h5[seg].max() + BUF)
    risk = abs(entry - sl)
    if risk <= 0:
        continue
    k0 = np.searchsorted(ms1, ms5[tb]) + 1  # enter on the next 1m bar
    out = {}
    for label, tgt in (
        ("extreme", extreme),
        ("3R", entry + d * 3 * risk),
        ("2R", entry + d * 2 * risk),
    ):
        r = None
        for i in range(k0, min(len(ms1), k0 + HORIZON)):
            if (d == 1 and lo1[i] <= sl) or (d == -1 and hi1[i] >= sl):
                r = -(risk + COST) / risk  # the cost hits the loser too
                break
            if (d == 1 and hi1[i] >= tgt) or (d == -1 and lo1[i] <= tgt):
                r = (abs(tgt - entry) - COST) / risk
                break
        out[label] = r if r is not None else 0.0
    trades.append({"t0": t0, "risk": risk, "wide": abs(half - stop15), **out})

n = len(trades)
print(f"\nno-gap setups: {len(rows_in)}   Realign trigger fired on: {n}  ({n / len(rows_in):.0%})")
if not n:
    raise SystemExit(0)
tight = np.array([t["risk"] for t in trades])
wide = np.array([t["wide"] for t in trades])
print(
    f"Realign's stop vs SOS Fade's: median {np.median(tight / wide):.0%} of the risk "
    f"(${np.median(tight):.2f} against ${np.median(wide):.2f})"
)

for label in ("extreme", "3R", "2R"):
    rs = np.array([t[label] for t in trades])
    tr = np.array([t[label] for t in trades if t["t0"] < SPLIT_MS])
    te = np.array([t[label] for t in trades if t["t0"] >= SPLIT_MS])
    print(f"\ntarget = {label}")
    print(
        f"  all      n{n:<4} total {rs.sum():+7.2f}R  mean {rs.mean():+.3f}  "
        f"win {np.mean(rs > 0):5.1%}  without best 3 {np.sort(rs)[:-3].sum():+7.2f}R"
    )
    print(f"  2020-23  n{len(tr):<4} total {tr.sum():+7.2f}R  win {np.mean(tr > 0):5.1%}")
    print(f"  2024-26  n{len(te):<4} total {te.sum():+7.2f}R  win {np.mean(te > 0):5.1%}")
