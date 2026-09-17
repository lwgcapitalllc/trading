#!/usr/bin/env python3
"""The ceiling on the 195 genuine no-gap setups (see nogap_zone_funnel.py).

🔴 A first version asked "never touched the 1.0 within 5 days AND made xR", which counted a
setup that ran 3R and retraced to the 1.0 a week later as a LOSER. As a trade that is a win
and the position is long gone. The question is what price did BEFORE the 1.0 was touched,
and the two answers differ hugely: 43 winners against 99.

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
    best = 0.0
    for i in range(i0, min(len(ms1), i0 + HORIZON)):
        if (d == 1 and lo[i] <= stop) or (d == -1 and hi[i] >= stop):
            break  # the 1.0 - everything after it is a different trade
        best = max(best, (hi[i] - half) / risk if d == 1 else (half - lo[i]) / risk)
    rows.append(best)

b = np.array(rows)
n = len(b)
print(f"\n{n} no-gap setups. How far price ran BEFORE the 1.0 was touched:")
for r in (1, 2, 3, 4):
    print(f"  reached {r}R: {int((b >= r).sum()):4d}  ({(b >= r).mean():5.1%})")
for r in (2, 3):
    print(
        f"\n  blind 0.5 entry, stop 1.0, target {r}R: "
        f"{float((b >= r).sum() * r - (b < r).sum()):+.1f}R over {n}"
        f"   (break-even {1 / (1 + r):.0%}, actual {(b >= r).mean():.1%})"
    )
