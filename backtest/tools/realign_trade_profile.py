#!/usr/bin/env python3
"""realign_trade_profile.py — do the losers have ANYTHING in common? (Aaron, 2026-09-16)

Buckets the stacked config's trades by every feature knowable AT ENTRY — side, New York hour,
weekday, reward:risk, stop size, retest depth — and by exit reason, with win/loss/scratch counts
beside each. Answered: **no.** Median reward:risk is 2.20 for winners and 2.25 for losers, and
nothing else separates them either. Full record: `strategies/python/realign/CLAUDE.md`.

🔴 **IT REMOVES THE SINGLE BIGGEST TRADE AND REPRINTS EVERY TABLE, AND THAT HALF IS THE POINT.**
This book has 3-5 trades carrying 5.5 years, so ONE trade lands in one bucket of every table and
makes that bucket look like a rule. Measured: shorts, Mondays, the 3-5 R:R bucket and sub-$5 stops
ALL looked like strong signals and were all the same +22.56R trade — with it removed, shorts fall
behind longs and Monday goes from the best day to the worst. **A bucketed claim on this strategy is
not believable until it survives that removal.**

⚠ Exploratory. Anything found here is a HYPOTHESIS, never a filter: it is read off a window several
picks already came from, and a filter must be REPLAYED — one position slot means a refused setup
frees the slot for a different trade, which is how the minimum-stop guard's cheap estimate got its
SIGN wrong (+1.84R estimated, -1.84R replayed).
"""

import dataclasses
import sys
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, "/Users/alwg/trading")
sys.path.insert(0, "/Users/alwg/trading/strategies/python")
from realign.config import RealignConfig
from realign.strategy import RealignStrategy

from backtest.data.source import BarSource
from backtest.fills import PROFILES
from backtest.replay import build_strategy

NY = ZoneInfo("America/New_York")
SCRATCH = 0.25
df = BarSource(server="VantageMarkets_Demo").load("XAUUSD", "5", "2020-01-02", "2025-08-05")
cfg = dataclasses.replace(
    RealignConfig(symbol="XAUUSD"),
    realign_entry_mode="retest",
    realign_retest_bars=5,
    exec_time_stop_mode="Always",
    exec_time_stop_hrs=12.0,
    flat_by_close=True,
)
s = build_strategy(
    RealignStrategy, cfg, initial_capital=10_000.0, cost_profile=PROFILES["puprime_standard"]
)
s.run(df)

times = [int(t.value // 1_000_000) for t in df.index]
closes = df["close"].to_numpy()
trig = []
for i, st in enumerate(s.states):
    if st is not None and st.trigger_dir != 0:
        trig.append(
            (
                times[i],
                closes[i],
                st.trigger_dir,
                st.trigger_stop,
                st.trigger_target,
                st.trigger_level,
            )
        )

rows = []
for t in s.execution.trades:
    cand = [x for x in trig if x[0] <= t.entry_ms and x[2] == t.dir]
    if not cand:
        continue
    ms, close, d, stop, target, level = cand[-1]
    ny = datetime.fromtimestamp(t.entry_ms / 1000.0, tz=timezone.utc).astimezone(NY)
    risk = abs(t.entry_price - stop) or 1e-9
    rows.append(
        dict(
            r=t.r,
            dir=d,
            hour=ny.hour,
            dow=ny.strftime("%a"),
            rr=(target - t.entry_price) * d / risk,
            stop_usd=t.stop_distance,
            stop_pct=100 * t.stop_distance / t.entry_price,
            pullback=abs(close - t.entry_price) / risk,  # how deep the retest went, in R
            exit=t.exit_reason,
        )
    )


def bucket(name, keyfn, rows):
    g = defaultdict(list)
    for x in rows:
        g[keyfn(x)].append(x["r"])
    print(f"\n{name}")
    for k in sorted(g, key=lambda k: -sum(g[k])):
        v = g[k]
        w = sum(1 for r in v if r > SCRATCH)
        l = sum(1 for r in v if r < -SCRATCH)
        print(
            f"  {str(k):<14} {len(v):3d} tr  {sum(v):+7.2f}R  avg {sum(v) / len(v):+.3f}  "
            f"W{w:3d} L{l:3d} S{len(v) - w - l:3d}"
        )


top = max(rows, key=lambda x: x["r"])
print(
    f"\nBIGGEST TRADE: {top['r']:+.2f}R  {top['dow']} {top['hour']:02d}:00 NY  "
    f"dir {'LONG' if top['dir'] > 0 else 'SHORT'}  rr {top['rr']:.2f}  stop ${top['stop_usd']:.2f}"
)
rows = [x for x in rows if x is not top]
print("=== EVERY TABLE BELOW HAS THE SINGLE BIGGEST TRADE REMOVED ===")
win = [x for x in rows if x["r"] > SCRATCH]
los = [x for x in rows if x["r"] < -SCRATCH]
scr = [x for x in rows if -SCRATCH <= x["r"] <= SCRATCH]
print(f"{len(rows)} trades matched   W{len(win)} L{len(los)} S{len(scr)}")
for f in ("rr", "stop_usd", "stop_pct", "pullback"):

    def med(g):
        v = sorted(x[f] for x in g)
        return v[len(v) // 2] if v else 0

    print(f"  median {f:<9} win {med(win):8.2f}   loss {med(los):8.2f}   scratch {med(scr):8.2f}")

bucket("by direction", lambda x: "LONG" if x["dir"] > 0 else "SHORT", rows)
bucket("by day of week", lambda x: x["dow"], rows)
bucket("by NY hour", lambda x: f"{x['hour']:02d}:00", rows)
bucket(
    "by reward:risk at entry",
    lambda x: (
        "<1"
        if x["rr"] < 1
        else "1-2"
        if x["rr"] < 2
        else "2-3"
        if x["rr"] < 3
        else "3-5"
        if x["rr"] < 5
        else "5+"
    ),
    rows,
)
bucket(
    "by stop size ($)",
    lambda x: (
        "<5"
        if x["stop_usd"] < 5
        else "5-10"
        if x["stop_usd"] < 10
        else "10-15"
        if x["stop_usd"] < 15
        else "15-25"
        if x["stop_usd"] < 25
        else "25+"
    ),
    rows,
)
bucket(
    "by retest depth (R)",
    lambda x: (
        "<0.25"
        if x["pullback"] < 0.25
        else "0.25-0.5"
        if x["pullback"] < 0.5
        else "0.5-0.75"
        if x["pullback"] < 0.75
        else "0.75+"
    ),
    rows,
)
bucket("by exit", lambda x: x["exit"], rows)
