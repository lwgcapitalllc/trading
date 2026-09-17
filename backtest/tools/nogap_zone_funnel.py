#!/usr/bin/env python3
"""The raw funnel behind the no-gap count — each setup classified ONCE.

🔴 The first version of this latched every flag across all bars of a setup's life, so a setup
with no gap on arrival that formed one later was counted in BOTH the gap and the no-gap pile
(194 + 277 against 374 arrivals). Rule 3: it recorded what was ever true, not what was true at
the moment the question is asked. Here each setup is keyed by (direction, SOS timestamp) and
its gap state is read ONCE, on the FIRST bar price is in the zone, which is when a trader would
look for one.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from backtest.data.cache import BarCache  # noqa: E402
from backtest.replay import build_strategy  # noqa: E402
from strategies.python.sos_fade import LAB_STRATEGY  # noqa: E402
from strategies.python.sos_fade.execution import Execution  # noqa: E402

CACHE = Path("/Users/alwg/trading/backtest/cache/VantageMarkets_Demo")
START, END = "2020-01-01", "2026-08-06"

sos_seen: set = set()
arrival: dict = {}  # key -> {"gap_on_arrival": bool, "stop":, "extreme":, "t0":}
traded: set = set()  # keys the primary took
_orig = Execution._ngs_context


def _patched(self, sig, seq, long_edge, short_edge):
    cfg = self._cfg
    ms_now = self._bar_ms.get(self._bar_ms_last)
    for d, stage, sos_bar, swp, div, tagged, edge, t_bar, t_ms in (
        (
            1,
            seq.l_stage,
            seq.l_sos_bar,
            seq.sos_l_swp,
            seq.sos_l_div,
            seq.l_half or seq.l_618,
            long_edge,
            self._traded_sos_l,
            self._traded_sos_l_ms,
        ),
        (
            -1,
            seq.s_stage,
            seq.s_sos_bar,
            seq.sos_s_swp,
            seq.sos_s_div,
            seq.s_half or seq.s_618,
            short_edge,
            self._traded_sos_s,
            self._traded_sos_s_ms,
        ),
    ):
        sos_ms = self._bar_ms.get(sos_bar) if sos_bar is not None else None
        if not (
            stage >= 2
            and sos_ms is not None
            and sig.fibo_dir == d
            and sig.fibo_p10 is not None
            and sig.fibo_p7 is not None
            and ((cfg.exec_arm_sweep and swp) or (cfg.exec_arm_div and div))
        ):
            continue
        k = (d, sos_ms)
        sos_seen.add(k)
        if not tagged:
            continue
        if k not in arrival:  # FIRST bar in the zone — read the gap once
            arrival[k] = {
                "gap": edge is not None,
                "stop": float(sig.fibo_p10),
                "extreme": float(sig.fibo_p7),
                "t0": ms_now or sos_ms,
            }
    # What the execution itself believes it has traded, read straight off its own latches
    # rather than re-deriving it: each time a side's traded-SOS timestamp advances, the
    # primary took that leg.
    for d, tms in ((1, self._traded_sos_l_ms), (-1, self._traded_sos_s_ms)):
        if tms is not None:
            traded.add((d, int(tms)))
    return _orig(self, sig, seq, long_edge, short_edge)


Execution._ngs_context = _patched

df15 = BarCache(CACHE).load("XAUUSD", "M15").loc[START:END]
df1 = BarCache(CACHE).load("XAUUSD", "M1").loc[START:END]
Strat, C = LAB_STRATEGY["strategy"], LAB_STRATEGY["config"]
cfg = dataclasses.replace(
    C(fill_model="bar", symbol="XAUUSD"),
    exec_secondary=False,
    exec_ngs=True,
    exec_sec_fill_tf_min=1,
)
st = build_strategy(Strat, cfg, initial_capital=10_000.0, cost_profile=None)
st.run_dual(df15, df1, warmup=1000)

arrived = set(arrival)
gap = {k for k in arrived if arrival[k]["gap"]}
nogap = arrived - gap
nogap_untraded = nogap - traded
print(f"\nXAUUSD 15m  {START} -> {END}\n")
print(f"  armed SOS setups with fibs                   {len(sos_seen):5d}")
print(f"  ... price came back into the zone            {len(arrived):5d}")
print(f"        a fair-value gap WAS there on arrival  {len(gap):5d}")
print(f"        NO fair-value gap on arrival           {len(nogap):5d}")
print(f"  ... and the primary never traded that leg    {len(nogap_untraded):5d}   <- the count")
print(
    f"\n  legs the primary reports trading      {len(traded):5d}"
    f"   (of which arrived in the zone: {len(traded & arrived)})"
)
print(f"  gap + no gap = {len(gap) + len(nogap)}  (must equal {len(arrived)})")
print(f"  primaries actually taken                     {len(st.execution.trades):5d}")

import pickle  # noqa: E402

pickle.dump({k: arrival[k] for k in nogap_untraded}, open("nogap_arrivals.pkl", "wb"))
print(f"\n  wrote nogap_arrivals.pkl ({len(nogap_untraded)} setups)")
