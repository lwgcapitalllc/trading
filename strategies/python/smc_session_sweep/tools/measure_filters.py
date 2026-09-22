"""Replay the session sweep over a cached feed, one settings override per case, and report it
gross, after costs, by half, and on the bars after 2026-08-23 (unseen when the filters were chosen).

Usage:
    python strategies/python/smc_session_sweep/tools/measure_filters.py <feed.csv> \
        '[["base", {}], ["age60", {"poi_max_age_bars": 60}]]'

⚠ Costs are charged AFTER the replay, per trade, as a price distance over that trade's own 1R —
the strategy itself prices no costs yet. Swap is NOT charged. The figures are PU Prime ECN's,
measured (`backtest/fills.py`): spread $0.12/oz, commission $1/side/lot of 100 oz.
⚠ Settings come from the middle row of the no-feed golden export, then the override, so the
baseline is the gated configuration.
"""

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
import pandas as pd
from backtest.replay import iter_bars
from backtest.replay.stack import EngineStack
from strategies.python.smc_session_sweep.config import SessionSweepConfig
from strategies.python.smc_session_sweep.strategy import SessionSweepStrategy

# PU Prime ECN, measured: spread $0.12/oz, commission $1/side/lot of 100 oz = $0.02/oz round trip.
COST = 0.12 + 0.02
GOLD = Path(__file__).resolve().parents[1] / "exports" / "golden" / "VANTAGE_XAUUSD_M5_conf5_20633bars.csv"
rows = [r for r in csv.DictReader(open(GOLD)) if r["px_state"]]
feed = sys.argv[1]
df = pd.read_csv(feed)
df.index = pd.to_datetime(df["time"], utc=True)
df = df[["open", "high", "low", "close"]]

def stats(rs):
    n = len(rs); w = [r for r in rs if r > 0]; l = [r for r in rs if r <= 0]
    eq = pk = dd = 0.0
    for r in rs:
        eq += r; pk = max(pk, eq); dd = min(dd, eq - pk)
    pf = round(sum(w) / -sum(l), 2) if l and sum(l) else None
    return f"n={n:3d} R={sum(rs):+6.1f} pf={pf} dd={dd:5.1f}"

for name, ov in json.loads(sys.argv[2]):
    t0 = time.time()
    cfg = SessionSweepConfig.from_export(rows[len(rows) // 2])
    for k, v in ov.items():
        setattr(cfg, k, v)
    s = SessionSweepStrategy(cfg, initial_capital=cfg.initial_capital)
    st = EngineStack(s.engine_config())
    for b in iter_bars(df):
        s.step(st.step(b))
    tr = s.execution.trades
    for t in tr:  # the index must point at the fill bar, or every date below is wrong
        bar = df.iloc[t.entry_index]
        assert bar.low - 0.5 <= t.entry_price <= bar.high + 0.5, (t.entry_index, t.entry_price, bar)
    when = [df.index[t.entry_index] for t in tr]
    net = [t.r - COST / t.stop_distance for t in tr]
    a = [r for r, w in zip(net, when) if w.year < 2022 or (w.year == 2022 and w.month < 9)]
    b2 = [r for r, w in zip(net, when) if not (w.year < 2022 or (w.year == 2022 and w.month < 9))]
    new = [r for r, w in zip(net, when) if w >= pd.Timestamp("2026-08-24", tz="UTC")]
    print(f"{name:14s} gross {stats([t.r for t in tr])} | net {stats(net)} | "
          f"2018-22 {stats(a)} | 2022-26 {stats(b2)} | unseen {stats(new)}  [{time.time()-t0:.0f}s]", flush=True)
