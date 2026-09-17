#!/usr/bin/env python3
"""The ceiling on the 195 genuine no-gap setups (see nogap_zone_funnel.py).

Enter blind at the 0.5, stop at the 15m 1.0, walk 1m bars forward from ARRIVAL in the zone
until the 1.0 is touched or 5 trading days pass. A bar holding both counts as STOPPED.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
from backtest.data.cache import BarCache  # noqa: E402

HORIZON = 7200
rows_in = pickle.load(open(Path("nogap_arrivals.pkl"), "rb"))
df1 = (
    BarCache(Path("/Users/alwg/trading/backtest/cache/VantageMarkets_Demo"))
    .load("XAUUSD", "M1")
    .loc["2020-01-01":"2026-08-06"]
)
ms1 = np.asarray(df1.index.view("int64") // 10**6)
hi, lo = df1["high"].to_numpy(), df1["low"].to_numpy()

rows = []
for (d, _sos), v in rows_in.items():
    stop, extreme, t0 = v["stop"], v["extreme"], v["t0"]
    half = (stop + extreme) / 2.0
    risk = abs(half - stop)
    if risk <= 0:
        continue
    i0 = np.searchsorted(ms1, t0)
    best, stopped = 0.0, False
    for i in range(i0, min(len(ms1), i0 + HORIZON)):
        if d == 1:
            if lo[i] <= stop:
                stopped = True
                break
            best = max(best, (hi[i] - half) / risk)
        else:
            if hi[i] >= stop:
                stopped = True
                break
            best = max(best, (half - lo[i]) / risk)
    rows.append((stopped, best))

n = len(rows)
print(f"\nno-gap setups measured: {n}")
print(
    f"  hit the 1.0 first:        {sum(1 for s, _ in rows if s):4d}  "
    f"({sum(1 for s, _ in rows if s) / n:5.1%})"
)
print(
    f"  never hit the 1.0:        {sum(1 for s, _ in rows if not s):4d}  "
    f"({sum(1 for s, _ in rows if not s) / n:5.1%})"
)
print("\nreversed off the zone and made, before the 1.0 was touched:")
for r in (1, 2, 3):
    k = sum(1 for s, b in rows if not s and b >= r)
    print(f"  {r}R or better: {k:4d}  ({k / n:5.1%})")
for r in (2, 3):
    k = sum(1 for s, b in rows if not s and b >= r)
    print(
        f"\nblind 0.5 entry, stop 1.0, target {r}R: "
        f"{sum(float(r) if (not s and b >= r) else -1.0 for s, b in rows):+.1f}R over {n}"
        f"   (break-even needs {1 / (1 + r):.0%}, actual {k / n:.1%})"
    )
