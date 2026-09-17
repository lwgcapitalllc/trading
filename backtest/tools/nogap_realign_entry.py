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

VARIANTS = {
    "any counter event": lambda is_shift: True,
    "counter BREAK only": lambda is_shift: not is_shift,
    "counter SHIFT only": lambda is_shift: is_shift,
}
# Targets. `f` is a fraction of the 15m fib leg measured from the extreme: 0.0 IS the extreme,
# 0.382 stops short of it, and a negative f runs past it. `R` targets are fixed multiples of
# the trade's own risk. Both are swept because Run 35 showed the two answer differently.
TARGETS = [
    ("fib 0.5", ("f", 0.5)),
    ("fib 0.382", ("f", 0.382)),
    ("fib 0.236", ("f", 0.236)),
    ("the extreme", ("f", 0.0)),
    ("0.27 past it", ("f", -0.27)),
    ("0.618 past it", ("f", -0.618)),
    ("1R", ("R", 1.0)),
    ("2R", ("R", 2.0)),
    ("3R", ("R", 3.0)),
    ("4R", ("R", 4.0)),
]

all_trades = {k: [] for k in VARIANTS}
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
    for vname, accepts in VARIANTS.items():
        # the pattern: a counter event, THEN a with-trend shift
        counter_bar, trig = None, None
        for j in sel:
            bar, ed, is_shift = ev5[j]
            if ed == -d:
                if accepts(is_shift):
                    counter_bar = bar  # the newest QUALIFYING counter event wins
            elif ed == d and is_shift and counter_bar is not None:
                trig = (counter_bar, bar)
                break
        if trig is None:
            continue
        cb, tb = trig
        entry = c5[tb]
        # the counter-move extreme, between the counter event and the trigger
        seg = slice(cb, tb + 1)
        sl = (l5[seg].min() - BUF) if d == 1 else (h5[seg].max() + BUF)
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        k0 = np.searchsorted(ms1, ms5[tb]) + 1  # enter on the next 1m bar
        out = {}
        for label, (kind, val) in TARGETS:
            tgt = (extreme + val * (stop15 - extreme)) if kind == "f" else (entry + d * val * risk)
            if (d == 1 and tgt <= entry) or (d == -1 and tgt >= entry):
                out[label] = None  # already behind price - not a trade, not a loss
                continue
            r = None
            for i in range(k0, min(len(ms1), k0 + HORIZON)):
                if (d == 1 and lo1[i] <= sl) or (d == -1 and hi1[i] >= sl):
                    r = -(risk + COST) / risk  # the cost hits the loser too
                    break
                if (d == 1 and hi1[i] >= tgt) or (d == -1 and lo1[i] <= tgt):
                    r = (abs(tgt - entry) - COST) / risk
                    break
            out[label] = r if r is not None else 0.0
        all_trades[vname].append({"t0": t0, "risk": risk, "wide": abs(half - stop15), **out})

for vname, trades in all_trades.items():
    n = len(trades)
    print(f"\n{'=' * 78}\n{vname}   fired on {n} of {len(rows_in)} setups ({n / len(rows_in):.0%})")
    if not n:
        continue
    tight = np.array([t["risk"] for t in trades])
    wide = np.array([t["wide"] for t in trades])
    print(f"  stop size vs SOS Fade's: median {np.median(tight / wide):.0%}")
    print(
        f"\n  {'target':<16}{'n':>5}{'total':>10}{'win':>8}"
        f"{'2020-23':>12}{'2024-26':>12}{'no best 3':>11}"
    )
    for label, _ in TARGETS:
        rs = np.array([t[label] for t in trades if t[label] is not None])
        if len(rs) < 10:
            print(f"  {label:<16}{len(rs):>5}   (too few to read)")
            continue
        tr = np.array([t[label] for t in trades if t[label] is not None and t["t0"] < SPLIT_MS])
        te = np.array([t[label] for t in trades if t[label] is not None and t["t0"] >= SPLIT_MS])
        both = "  <-" if (len(tr) and len(te) and tr.sum() > 0 and te.sum() > 0) else ""
        print(
            f"  {label:<16}{len(rs):>5}{rs.sum():>+10.1f}{np.mean(rs > 0):>8.1%}"
            f"{tr.sum():>+12.1f}{te.sum():>+12.1f}"
            f"{np.sort(rs)[:-3].sum():>+11.1f}{both}"
        )
print("\n  <- marks a target positive in BOTH halves of the record.")
