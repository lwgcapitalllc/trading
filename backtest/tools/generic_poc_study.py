"""generic_poc_study.py — Does the leg's volume POC mark where the pullback turns?  Rules fixed BEFORE any result.

POPULATION  every SOS Fade Generic setup (sweep or divergence arm, then the shift) whose pullback
            tagged the 0.5-0.886 zone, 2020-01-01 -> 2026-09-04, M15. Collected by running the bot
            with an impossible minimum stop so it never trades: every setup is then recorded, each
            one measured ALONE (no position slot).
PROFILE     the leg the fib is drawn on, origin (1.0) to extreme (0.0) as it stood on the bar the
            zone was tagged. 5-minute bars inside that time span, 50 rows over the leg's price
            range, the canonical engine's arithmetic (`session_volume_profile.range_poc`).
            Volume = MetaTrader tick volume.
ENTRIES     a limit at each level, walked on M15 from the zone-tag bar:
              fib 0.5 / 0.618 / 0.786 / 0.886   and   POC (only when the POC sits in 0.5-1.0)
            Filled when price reaches it before the 0.0; no fill = no trade.
            Then stop at 1.0, target at 0.0, whole position. A bar touching both = loss.
            The fill bar touching 1.0 = loss. Gross R, no costs. 30-day horizon.
CONTROL     the same setups (POC in the zone) entered at the standard fib NEAREST their POC, so
            depth is held equal and only "is it the volume level" differs.

A SCREEN: each setup alone, no costs. Result: docs/SOS_FADE_GENERIC_SPEC.md -> *What it measured*.

Usage: python3 backtest/tools/generic_poc_study.py GBPUSD.p GBPJPY.p XAUUSD.p
"""

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "strategies/python"), str(ROOT / "engines")]

import numpy as np  # noqa: E402
from session_volume_profile.engine import range_poc  # noqa: E402
from sos_fade_generic import SosFadeGenericConfig, SosFadeGenericStrategy  # noqa: E402

from backtest.data.cache import BarCache  # noqa: E402
from engines.fibonacci.geometry import fib_level  # noqa: E402

START, END, WARMUP, HORIZON = "2020-01-01", "2026-09-04", 500, 2880
FIBS = (0.5, 0.618, 0.786, 0.886)


def setups(symbol, m15):
    cfg = SosFadeGenericConfig(symbol=symbol, exec_min_stop_mode="Fixed $", exec_min_stop_val=1e12)
    strat = SosFadeGenericStrategy(cfg)
    ex = strat.execution
    geo, orig = {}, ex._record_misses

    def hooked(sig, seq, dec, le, se):
        if sig.fibo_ash is not None and sig.fibo_asl is not None:
            geo[sig.time_ms] = (
                sig.index,
                sig.fibo_ash,
                sig.fibo_asl,
                sig.fibo_dir,
                sig.fibo_ash_ms,
                sig.fibo_asl_ms,
            )
        return orig(sig, seq, dec, le, se)

    ex._record_misses = hooked
    strat.run(m15, warmup=WARMUP)
    assert not ex.trades, "the impossible stop floor let a trade through"
    out = []
    for m in ex.misses:
        if m.index < WARMUP or m.zone_time_ms is None or m.code not in (3, 8):
            continue
        g = geo.get(m.zone_time_ms)
        if g is None or g[3] != m.dir or g[4] is None or g[5] is None:
            continue
        out.append((m.dir, m.code == 8) + g)
    return out


def walk(H, L, z, d, entry, p0, p1):
    """-> None (no fill) or (+1 win / -1 loss / 0 open)."""
    n = min(z + HORIZON, len(H))
    i, filled = z, False
    while i < n:
        if not filled:
            if i > z and (H[i] >= p0 if d > 0 else L[i] <= p0):
                return None
            if (L[i] <= entry) if d > 0 else (H[i] >= entry):
                filled = True
                if (L[i] <= p1) if d > 0 else (H[i] >= p1):
                    return -1
        else:
            if (L[i] <= p1) if d > 0 else (H[i] >= p1):
                return -1
            if (H[i] >= p0) if d > 0 else (L[i] <= p0):
                return 1
        i += 1
    return 0 if filled else None


def score(rows):
    fills = [r for r in rows if r is not None and r[0] != 0]
    if not fills:
        return "none"
    w = sum(1 for o, _ in fills if o > 0)
    tot = sum(rr if o > 0 else -1.0 for o, rr in fills)
    return f"fills {len(fills):4d}  win {100 * w / len(fills):5.1f}%  R/fill {tot / len(fills):+.3f}  total {tot:+7.1f}R"


def main(symbol):
    cache = BarCache(ROOT / "backtest/cache/PUPrime_Demo")
    m15 = cache.load(symbol, "M15").loc[START:END]
    m5 = cache.load(symbol, "M5").loc[START:END]
    t5 = m5.index.values.astype("datetime64[ms]").astype("int64")
    b5 = m5[["open", "high", "low", "close", "volume"]].to_numpy()
    H, L = m15["high"].to_numpy(), m15["low"].to_numpy()

    S = setups(symbol, m15)
    pos = Counter()
    res = {f: [] for f in FIBS}
    res["poc"], res["ctrl"] = [], []
    for d, gap, z, ash, asl, fdir, ash_ms, asl_ms in S:
        for f in FIBS:
            e = fib_level(ash, asl, fdir, f)
            o = walk(H, L, z, d, e, fib_level(ash, asl, fdir, 0.0), fib_level(ash, asl, fdir, 1.0))
            res[f].append(None if o is None else (o, f / (1 - f)))
        t0, t1 = sorted((ash_ms, asl_ms))
        a, b = np.searchsorted(t5, t0), np.searchsorted(t5, t1 + 15 * 60_000)
        poc = range_poc([tuple(x) for x in b5[a:b]], asl, ash) if b > a else None
        if poc is None:
            pos["no profile"] += 1
            continue
        r = (ash - poc) / (ash - asl) if fdir == 1 else (poc - asl) / (ash - asl)
        pos[
            "0-0.382"
            if r < 0.382
            else "0.382-0.5"
            if r < 0.5
            else "0.5-0.886 zone"
            if r <= 0.886
            else "0.886-1.0"
        ] += 1
        if not (0.5 <= r < 1.0):
            continue
        p0, p1 = fib_level(ash, asl, fdir, 0.0), fib_level(ash, asl, fdir, 1.0)
        o = walk(H, L, z, d, poc, p0, p1)
        res["poc"].append(None if o is None else (o, r / (1 - r)))
        near = min(FIBS, key=lambda f: abs(f - r))
        o = walk(H, L, z, d, fib_level(ash, asl, fdir, near), p0, p1)
        res["ctrl"].append(None if o is None else (o, near / (1 - near)))

    print(
        f"\n== {symbol}  {len(S)} setups reached the zone ({sum(1 for s in S if s[1])} with a gap)"
    )
    print("   where the leg's POC sits (fib ratio):", dict(pos))
    for f in FIBS:
        print(f"   entry fib {f:<5}  {score(res[f])}")
    print(f"   entry at POC     {score(res['poc'])}")
    print(f"   nearest fib ctrl {score(res['ctrl'])}   (same setups as the POC row)")


for s in sys.argv[1:]:
    main(s)
