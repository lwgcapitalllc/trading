"""generic_zone_turn.py — Of the setups that come back into the 0.5-0.886 zone, how many turn and make a new high/low
(reach the 0.0 fib) before breaking the 1.0?  SOS Fade Generic defaults, M15, PU Prime bars.

Population = every setup (arm + shift) whose pullback tagged the zone:
  traded      -> a trade's own result answers it (stop 1.0, target 0.0, whole position)
  missed      -> "No FVG in zone" (code 3) or "Never filled" (code 7): walked forward from the
                 bar that tagged the zone, on the fib as it stood on that bar.
Walk: bar by bar; the 1.0 touched first (or both on one bar) = FAIL, the 0.0 touched first = TURN.

A SCREEN: each setup alone, no costs. Result: docs/SOS_FADE_GENERIC_SPEC.md -> *What it measured*.

Usage: python3 backtest/tools/generic_zone_turn.py GBPUSD.p GBPJPY.p XAUUSD.p
"""

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "strategies/python")]

from sos_fade_generic import SosFadeGenericConfig, SosFadeGenericStrategy  # noqa: E402

from backtest.data.cache import BarCache  # noqa: E402

HORIZON = 2880  # 30 days of M15
WARMUP = 500


from engines.fibonacci.geometry import fib_level as lvl  # noqa: E402


def run(symbol):
    df = (
        BarCache(ROOT / "backtest/cache/PUPrime_Demo")
        .load(symbol, "M15")
        .loc["2020-01-01":"2026-09-26"]
    )
    strat = SosFadeGenericStrategy(SosFadeGenericConfig(symbol=symbol))
    ex = strat.execution
    geo = {}
    orig = ex._record_misses

    def hooked(sig, seq, dec, le, se):
        if sig.fibo_ash is not None and sig.fibo_asl is not None:
            geo[sig.time_ms] = (sig.index, sig.fibo_ash, sig.fibo_asl, sig.fibo_dir)
        return orig(sig, seq, dec, le, se)

    ex._record_misses = hooked
    strat.run(df, warmup=WARMUP)
    H, L = df["high"].to_numpy(), df["low"].to_numpy()

    out = Counter()
    for t in ex.trades:
        if t.entry_index < WARMUP:
            continue
        out[("gap-traded", "TURN" if t.r > 0 else "FAIL")] += 1
    for m in ex.misses:
        if m.index < WARMUP or m.code not in (3, 7, 8) or m.zone_time_ms is None:
            continue
        g = geo.get(m.zone_time_ms)
        key = "no-gap" if m.code == 3 else "gap-unfilled"
        if g is None or g[3] != m.dir:
            out[(key, "no-geometry")] += 1
            continue
        z, ash, asl, fdir = g
        p0, p1 = lvl(ash, asl, fdir, 0.0), lvl(ash, asl, fdir, 1.0)
        d = m.dir
        res = "OPEN"
        for i in range(z, min(z + HORIZON, len(H))):
            broke = L[i] <= p1 if d > 0 else H[i] >= p1
            if broke:
                res = "FAIL"
                break
            if i > z and (H[i] >= p0 if d > 0 else L[i] <= p0):
                res = "TURN"
                break
        out[(key, res)] += 1
    return out


for sym in sys.argv[1:]:
    c = run(sym)
    print(f"\n== {sym}")
    tot = Counter()
    for grp in ("gap-traded", "gap-unfilled", "no-gap"):
        n = {k: c[(grp, k)] for k in ("TURN", "FAIL", "OPEN", "no-geometry")}
        s = n["TURN"] + n["FAIL"]
        for k, v in n.items():
            tot[k] += v
        print(
            f"  {grp:13s} turn {n['TURN']:4d}  fail {n['FAIL']:4d}  open {n['OPEN']:3d}  nogeo {n['no-geometry']:3d}"
            f"  turn% {100 * n['TURN'] / s:5.1f}"
            if s
            else f"  {grp:13s} none"
        )
    s = tot["TURN"] + tot["FAIL"]
    print(
        f"  {'ALL':13s} turn {tot['TURN']:4d}  fail {tot['FAIL']:4d}  open {tot['OPEN']:3d}  nogeo {tot['no-geometry']:3d}  turn% {100 * tot['TURN'] / s:5.1f}"
    )
