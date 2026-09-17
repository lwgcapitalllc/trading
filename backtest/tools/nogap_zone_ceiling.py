#!/usr/bin/env python3
"""How much is ON THE TABLE in the no-gap zone, before any entry rule.

For every no-gap setup (0.5 tagged, no fair-value gap, not traded), measure the
ceiling a perfect entry could have reached: enter blind at the 0.5 level, stop at
the 15m 1.0, and ask how far price travelled in the trade direction before the 1.0
was touched. Bar-by-bar on 1m; if one bar holds both the stop and the target, it
counts as STOPPED (the conservative read).

This is not a strategy. It is the upper bound any confirmation rule is competing for.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

from backtest.data.cache import BarCache  # noqa: E402
from backtest.replay import build_strategy  # noqa: E402
from strategies.python.sos_fade import LAB_STRATEGY  # noqa: E402
from strategies.python.sos_fade.execution import Execution  # noqa: E402

HORIZON_BARS = 7200  # 5 trading days of 1m bars
CACHE = Path("/Users/alwg/trading/backtest/cache/VantageMarkets_Demo")
START, END = "2020-01-01", "2026-08-06"

seen: dict = {}  # (dir, sos_ms) -> [first_ms, last_ms, stop, extreme]
_orig = Execution._ngs_context


def _patched(self, sig, seq, long_edge, short_edge):
    out = _orig(self, sig, seq, long_edge, short_edge)
    ms = self._bar_ms.get(self._bar_ms_last)
    for ctx in out:
        if ctx is None:
            continue
        key = (ctx.dir, ctx.sos_ms)
        t = ms if ms is not None else ctx.sos_ms
        if key in seen:
            seen[key][1] = t
        else:
            seen[key] = [t, t, ctx.stop, ctx.extreme]
    return out


Execution._ngs_context = _patched

df15 = BarCache(CACHE).load("XAUUSD", "M15").loc[START:END]
df1 = BarCache(CACHE).load("XAUUSD", "M1").loc[START:END]
S, C = LAB_STRATEGY["strategy"], LAB_STRATEGY["config"]
cfg = dataclasses.replace(
    C(fill_model="bar", symbol="XAUUSD"),
    exec_secondary=False,
    exec_ngs=True,
    exec_sec_fill_tf_min=1,
)
strat = build_strategy(S, cfg, initial_capital=10_000.0, cost_profile=None)
strat.run_dual(df15, df1, warmup=1000)
print(f"no-gap setups recorded: {len(seen)}", flush=True)

ms1 = np.asarray(df1.index.view("int64") // 10**6)
hi, lo = df1["high"].to_numpy(), df1["low"].to_numpy()

rows = []
for (d, sos_ms), (t0, t1, stop, extreme) in seen.items():
    half = (stop + extreme) / 2.0
    risk = abs(half - stop)
    if risk <= 0:
        continue
    i0 = np.searchsorted(ms1, t0)
    i1 = min(len(ms1), i0 + HORIZON_BARS)  # price is the only stopping condition now
    best = 0.0
    stopped = False
    for i in range(i0, i1):
        h, lw = hi[i], lo[i]
        if d == 1:
            if lw <= stop:
                stopped = True
                break
            best = max(best, (h - half) / risk)
        else:
            if h >= stop:
                stopped = True
                break
            best = max(best, (half - lw) / risk)
    rows.append((stopped, best))

n = len(rows)
survived = [b for s, b in rows if not s]
print(f"\nsetups measured: {n}")
print(
    f"  hit the 1.0 (stop) while the setup was live: {n - len(survived)}  "
    f"({(n - len(survived)) / n:.0%})"
)
print(f"  never hit the 1.0:                           {len(survived)}  ({len(survived) / n:.0%})")
print("\nof ALL setups, how far price ran from the 0.5 before the 1.0 was touched:")
for r in (1, 2, 3):
    k = sum(1 for s, b in rows if not s and b >= r)
    print(f"  reached {r}R or better: {k:4d}  ({k / n:5.1%} of all setups)")
print(
    f"\nblind entry at the 0.5, stop at the 1.0, target 3R: "
    f"{sum(3.0 if (not s and b >= 3) else -1.0 for s, b in rows):+.1f}R over {n} setups"
)
