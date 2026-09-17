#!/usr/bin/env python3
"""What do the WINNERS have in common, on the lower frames, BEFORE they move?

Run 32 split the 195 no-gap setups into 43 that reversed for 1R+ and 152 that hit the 1.0.
This asks whether the 43 share a lower-frame structure pattern the 152 lack.

🔴 THE WINDOW IS THE WHOLE POINT. A pattern is only usable if it is visible BEFORE the
reversal, so events are collected from arrival in the zone until price LEAVES the zone
(crosses back past the 0.5 toward the extreme) or hits the 1.0 — never after. Anything
found in the move itself is hindsight, which is the defect Run 28 was retracted for.

🔴 43 WINNERS AGAINST ~270 CANDIDATE PATTERNS WILL PRODUCE WINNERS BY CHANCE. Everything is
reported on a 2020-2023 half and checked on 2024-2026, and nothing that fails the check is
worth reading.

Event vocabulary per bar: frame (1m/5m) x stream (swing/internal) x kind (bos/sos) x
direction (with/against the trade). 16 event types; sequences of length 1 and 2.
"""

from __future__ import annotations

import pickle
import sys
from itertools import product
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
SPLIT_MS = 1704067200000  # 2024-01-01

rows_in = pickle.load(open(_ROOT / "nogap_arrivals.pkl", "rb"))

df1 = BarCache(CACHE).load("XAUUSD", "M1").loc[START:END]
ms1 = np.asarray(df1.index.view("int64") // 10**6)
hi1, lo1 = df1["high"].to_numpy(), df1["low"].to_numpy()


def events(tf):
    """(ms, code) for every structure event on this frame. code = (frame, stream, kind, dir)."""
    df = BarCache(CACHE).load("XAUUSD", tf).loc[START:END]
    ms = np.asarray(df.index.view("int64") // 10**6)
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    eng = StructureEngine(major_length=15)
    out_ms, out_code = [], []
    for i in range(len(df)):
        st = eng.update(Bar(index=i, open=o[i], high=h[i], low=l[i], close=c[i]))
        for stream, ev in (("swing", st.external), ("internal", st.internal)):
            for kind, bull, bear in (
                ("bos", ev.bull_bos, ev.bear_bos),
                ("sos", ev.bull_sos, ev.bear_sos),
            ):
                for d, fired in ((1, bull), (-1, bear)):
                    if fired:
                        out_ms.append(ms[i])
                        out_code.append((tf, stream, kind, d))
    return np.array(out_ms), out_code


EV = {tf: events(tf) for tf in ("M1", "M5")}
print("events collected", {k: len(v[0]) for k, v in EV.items()}, flush=True)

setups = []
for (d, _sos), v in rows_in.items():
    stop, extreme, t0 = v["stop"], v["extreme"], v["t0"]
    half = (stop + extreme) / 2.0
    risk = abs(half - stop)
    if risk <= 0:
        continue
    i0 = np.searchsorted(ms1, t0)
    # THE OBSERVATION WINDOW: arrival -> the moment price is +0.5R toward the extreme, which is
    # half way to the first target. Everything after that is the move itself and is hindsight.
    # The window also ends at the 1.0. `best` is measured over the whole life to the 1.0.
    t_end, best = None, 0.0
    for i in range(i0, min(len(ms1), i0 + HORIZON)):
        if (d == 1 and lo1[i] <= stop) or (d == -1 and hi1[i] >= stop):
            if t_end is None:
                t_end = ms1[i]
            break
        r = ((hi1[i] - half) / risk) if d == 1 else ((half - lo1[i]) / risk)
        best = max(best, r)
        if t_end is None and r >= 0.5:
            t_end = ms1[i]
    if t_end is None:
        t_end = ms1[min(len(ms1) - 1, i0 + HORIZON - 1)]
    seq = []
    for tf in ("M1", "M5"):
        ems, ecode = EV[tf]
        sel = np.where((ems >= t0) & (ems <= t_end))[0]
        for j in sel:
            f, s_, k, ed = ecode[j]
            seq.append((f, s_, k, "with" if ed == d else "against"))
    setups.append({"t0": t0, "won": best >= 3.0, "seq": seq})

n_w = sum(1 for s in setups if s["won"])
print(
    f"\nsetups usable: {len(setups)}   winners (3R before the 1.0): {n_w}   losers: {len(setups) - n_w}"
)
print(f"median in-zone events per setup: {np.median([len(s['seq']) for s in setups]):.0f}")

VOCAB = list(product(("M1", "M5"), ("swing", "internal"), ("bos", "sos"), ("with", "against")))
cands = [(a,) for a in VOCAB] + [(a, b) for a in VOCAB for b in VOCAB]


def has(seq, pat):
    it = iter(seq)
    return all(any(e == p for e in it) for p in pat)


def rate(rows, pat):
    m = [r for r in rows if has(r["seq"], pat)]
    return len(m), (sum(1 for r in m if r["won"]) / len(m) if m else 0.0)


tr = [s for s in setups if s["t0"] < SPLIT_MS]
te = [s for s in setups if s["t0"] >= SPLIT_MS]
base_tr = sum(1 for s in tr if s["won"]) / len(tr)
base_te = sum(1 for s in te if s["won"]) / len(te)
print(
    f"\nbaseline win rate   2020-23 {base_tr:.1%} (n{len(tr)})   2024-26 {base_te:.1%} (n{len(te)})"
)

res = []
for pat in cands:
    n_tr, w_tr = rate(tr, pat)
    if n_tr < 15:
        continue
    n_te, w_te = rate(te, pat)
    if n_te < 8:
        continue
    res.append((w_tr - base_tr, pat, n_tr, w_tr, n_te, w_te))
res.sort(reverse=True)

print(f"\n{len(res)} patterns with enough trades in both halves. Top 12 by 2020-23 lift:\n")
print(f"  {'pattern':<62} {'2020-23':>18}  {'2024-26':>18}")
for lift, pat, n_tr, w_tr, n_te, w_te in res[:12]:
    name = " > ".join(f"{f[1:]}m {s} {k} {d}" for f, s, k, d in pat)
    print(
        f"  {name:<62} n{n_tr:<3} {w_tr:5.1%} {lift:+5.1%}   n{n_te:<3} {w_te:5.1%} "
        f"{w_te - base_te:+5.1%}"
    )

held = [r for r in res if r[0] > 0.05 and r[5] - base_te > 0.05]
print(f"\npatterns beating the baseline by 5pp in BOTH halves: {len(held)}")
for lift, pat, n_tr, w_tr, n_te, w_te in held:
    name = " > ".join(f"{f[1:]}m {s} {k} {d}" for f, s, k, d in pat)
    print(f"  {name:<62} n{n_tr:<3} {w_tr:5.1%}   n{n_te:<3} {w_te:5.1%}")
