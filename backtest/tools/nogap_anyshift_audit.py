#!/usr/bin/env python3
"""nogap_anyshift_audit.py — Run 28: the no-gap setups entered on the FIRST 1m shift, stop at 1.0.

Aaron, 2026-09-16. Of the 178 code-3 setups: once price has tagged the 0.5, take the first 1m
change of character in the trade's direction — internal OR main structure — at that bar's close.
Stop at the 1.0 fib. No trade if price touches the 1.0 or takes out the leg's 0.0 first, or if
nothing prints within 48h. Exits: a price target at the 0.0 (the new high/low), a fixed-R grid, or
a 48h mark; stop live from the bar after entry; costs and swap charged.

⚠ A SCREEN, not the bot: each setup walked alone, no Pine counterpart for the 1m feed, and the
entry is reconstructed rather than replayed through the order layer. Result: sos_fade_optimization.md Run 28.

Usage: PYTHONPATH=. python3 backtest/tools/nogap_anyshift_audit.py
"""

from pathlib import Path

import numpy as np

import backtest.tools.nogap_ishift_audit as A
from engines.market_structure.engine import StructureEngine
from engines.market_structure.types import Bar

c = Path(A._ROOT / "backtest/cache/VantageMarkets_Demo")
df15 = A._load(c, "XAUUSD", "M15", "2020-01-01", "2026-08-21")
df1 = A._load(c, "XAUUSD", "M1", "2020-01-01", "2026-08-21")
setups, shipped, _, _ = A.collect(df15, 1000, {}, verbose=False)
setups = [s for s in setups if s.time_ms < 1786060800000]
tape = A.Tape1m(df1)
eng = StructureEngine(major_length=15)
sh = np.zeros(tape.n, np.int8)
for i in range(tape.n):
    st = eng.update(Bar(index=i, open=tape.o[i], high=tape.h[i], low=tape.l[i], close=tape.c[i]))
    n, e = st.internal, st.external
    sh[i] = 1 if (n.bull_sos or e.bull_sos) else -1 if (n.bear_sos or e.bear_sos) else 0
H = 2880


def exitwalk(d, i0, e, st, tgt):
    risk = abs(e - st)
    end = min(i0 + H, tape.n - 1)
    px = None
    xi = end
    for i in range(i0 + 1, end + 1):
        hs = (tape.l[i] <= st) if d > 0 else (tape.h[i] >= st)
        ht = tgt is not None and ((tape.h[i] >= tgt) if d > 0 else (tape.l[i] <= tgt))
        if hs and ht:
            up = A._intrabar_targets_first(tape.o[i], tape.h[i], tape.l[i])
            px = tgt if (up if d > 0 else not up) else st
        elif ht:
            px = tgt
        elif hs:
            px = st
        if px is not None:
            xi = i
            break
    if px is None:
        px = tape.c[end]
    g = (px - e) * d / risk
    nights = A._rollovers_between(int(tape.t[i0]), int(tape.t[xi]))
    return g - A._COST_PRICE / risk + nights * A._swap_price_per_night(d) / risk


trades = []
stats = dict(stopped=0, late=0, none=0, floor=0)
for s in setups:
    d = s.dir
    st = s.level(1.0)
    ext = s.level(0.0)
    i0 = np.searchsorted(tape.t, s.time_ms)
    res = None
    half = s.level(0.5)
    tagged = False
    for i in range(i0, min(i0 + H, tape.n)):
        if not tagged:
            tagged = (tape.l[i] <= half) if d > 0 else (tape.h[i] >= half)
            if not tagged:
                continue
        if (tape.l[i] <= st) if d > 0 else (tape.h[i] >= st):
            res = "stopped"
            break
        if (tape.h[i] > ext) if d > 0 else (tape.l[i] < ext):
            res = "late"
            break
        if sh[i] == d:
            res = i
            break
    if not isinstance(res, (int, np.integer)):
        stats[res or "none"] += 1
        continue
    e = float(tape.c[res])
    if abs(e - st) < e * 0.0008:
        stats["floor"] += 1
        continue
    trades.append((s, d, res, e, st, ext))
print(stats, "trades", len(trades))
risks = [abs(e - st) for _, _, _, e, st, _ in trades]
print(
    "entry depth median",
    np.median([(x - e) / (x - st) for _, _, _, e, st, x in trades]),
    "reward to the high/low in R median",
    np.median([abs(x - e) / abs(e - st) for _, _, _, e, st, x in trades]),
)
rows = {}
for name, tg in [
    ("new high/low", None),
    ("1R", 1),
    ("2R", 2),
    ("3R", 3),
    ("5R", 5),
    ("48h mark", "h"),
]:
    rs = []
    for s, d, i, e, st, x in trades:
        if name == "new high/low":
            t = x
        elif tg == "h":
            t = None
        else:
            t = e + d * tg * abs(e - st)
        rs.append(exitwalk(d, i, e, st, t))
    rs = np.array(rs)
    rows[name] = rs
    print(
        f"{name:13} total {rs.sum():+7.1f}R  mean {rs.mean():+.2f}  win {np.mean(rs > 0):.0%}  without best {np.sort(rs)[:-1].sum():+.1f}  without best 3 {np.sort(rs)[:-3].sum():+.1f}"
    )
yrs: dict = {}
for (s, d, i, e, st, x), r in zip(trades, rows["3R"]):
    y = df1.index[i].year
    yrs.setdefault(y, []).append(r)
print(
    "by year (3R target):",
    "  ".join(f"{y} n{len(v)} {sum(v):+.1f}" for y, v in sorted(yrs.items())),
)
busy = sum(any(t.entry_ms <= tape.t[i] < t.exit_ms for t in shipped) for _, _, i, *_ in trades)
print("overlap with shipped trades", busy)
