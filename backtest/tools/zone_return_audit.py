"""zone_return_audit.py — the RETURN into the tradable zone (Run 39).

Trades the opposite direction to Runs 27-36: not the way OUT of the zone, the way BACK IN.
From the leg extreme down to the level price shifted out from, or deeper.

    15m  the Structure fib's leg gives the zone. B = the level the shift broke, S = the sweep
         it came off. REQUIRE (extreme - B) >= ratio * (B - S)  <- "is the move worth it"
         and price within `near` of the leg span of the extreme.
    LTF  entry = the first counter-direction shift of structure, but only once price has
         STALLED: over the last `stall` bars the leg-direction extreme must sit in the FIRST
         HALF of that window. That is a proxy for "no new extreme recently", NOT a literal
         bars-since-new-high counter -- do not quote it as one.
    stop   behind the furthest point price reached (the leg extreme) + buffer
    target the `depth` retracement into the leg

No lookahead: a 15m bar opening at t is read only from t+15m, and a lower-frame bar holding
both the stop and the target counts as STOPPED.

⚠ Runs GROSS of costs by default so instruments compare. Per-instrument costs are UNMEASURED
and gold's may not be borrowed onto them.

    python backtest/tools/zone_return_audit.py --symbols XAUUSD_p --ltf M1 --stall 240
    python backtest/tools/zone_return_audit.py --ratios 0 0.75 1 1.5 2 --stalls 0 120 240 480
"""

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
ROOT = Path("/Users/alwg/trading")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "engines"))
from market_structure import Bar, StructureEngine

from backtest.data.cache import BarCache
from backtest.replay.loop import iter_bars
from backtest.replay.stack import EngineConfig, EngineStack

CACHE = BarCache(ROOT / "backtest/cache/PUPrime_Demo")
SPLIT = np.datetime64("2022-09-15").astype("datetime64[ms]").astype("int64")
BUF_FRAC = 0.005  # stop buffer as a fraction of the leg span -- instrument neutral
NEAR = 0.25
MAX_HOLD = 3000


def prep(sym, htf, ltf, tf_min):
    h = CACHE.load(sym, htf)
    l = CACHE.load(sym, ltf)
    if h.empty or l.empty or len(h) < 5000 or len(l) < 20000:
        return None
    stack = EngineStack(
        EngineConfig(
            major_length=15,
            fib=True,
            sniper=False,
            macro=False,
            internal=True,
            fvg=False,
            rsi=False,
            liquidity=False,
            sessions=False,
        )
    )
    n = len(h)
    fd = np.zeros(n, np.int8)
    ash = np.full(n, np.nan)
    asl = np.full(n, np.nan)
    Bb = np.full(n, np.nan)
    Sb = np.full(n, np.nan)
    Bs = np.full(n, np.nan)
    Ss = np.full(n, np.nan)
    _bB = _bS = _sB = _sS = np.nan
    for i, bar in enumerate(iter_bars(h)):
        st = stack.step(bar)
        e = st.structure.external
        if e.bull_sos and e.bull_bos_price is not None and e.bull_bos_low is not None:
            _bB, _bS = e.bull_bos_price, e.bull_bos_low
        if e.bear_sos and e.bear_bos_price is not None and e.bear_bos_high is not None:
            _sB, _sS = e.bear_bos_price, e.bear_bos_high
        Bb[i], Sb[i], Bs[i], Ss[i] = _bB, _bS, _sB, _sS
        f = st.fib
        if f is not None and f.active and f.ash is not None and f.asl is not None:
            fd[i] = f.direction
            ash[i] = f.ash
            asl[i] = f.asl
    o, hi, lo, cl = (l[k].to_numpy() for k in ("open", "high", "low", "close"))
    eng = StructureEngine(major_length=15)
    bear, bull = [], []
    for i in range(len(l)):
        ev = eng.update(
            Bar(index=i, open=float(o[i]), high=float(hi[i]), low=float(lo[i]), close=float(cl[i]))
        ).external
        if ev.bear_sos:
            bear.append(i)
        if ev.bull_sos:
            bull.append(i)
    return dict(
        h=h,
        l=l,
        fd=fd,
        ash=ash,
        asl=asl,
        Bb=Bb,
        Sb=Sb,
        Bs=Bs,
        Ss=Ss,
        hi=hi,
        lo=lo,
        cl=cl,
        c15=h["close"].to_numpy(),
        t15=h.index.values.astype("int64") // 1_000_000 + tf_min * 60_000,
        tl=l.index.values.astype("int64") // 1_000_000,
        bear=np.array(bear),
        bull=np.array(bull),
        tf_min=tf_min,
    )


def run(D, depth, stall, ratio):
    trades = []
    used = set()
    seen = set()
    passed = set()
    fd, ash_, asl_, cl, hi, lo = D["fd"], D["ash"], D["asl"], D["cl"], D["hi"], D["lo"]
    for i in range(1, len(D["c15"])):
        d = fd[i]
        if d == 0 or np.isnan(ash_[i]):
            continue
        A, L = ash_[i], asl_[i]
        span = A - L
        if span <= 0:
            continue
        key = (round(A, 5), round(L, 5), int(d))
        seen.add(key)
        if d == 1:
            B, S = D["Bb"][i], D["Sb"][i]
            if np.isnan(B) or np.isnan(S) or B <= S or (A - B) < ratio * (B - S):
                continue
        else:
            B, S = D["Bs"][i], D["Ss"][i]
            if np.isnan(B) or np.isnan(S) or S <= B or (B - L) < ratio * (S - B):
                continue
        passed.add(key)
        if key in used:
            continue
        px = D["c15"][i]
        if d == 1 and not (A - px <= NEAR * span):
            continue
        if d == -1 and not (px - L <= NEAR * span):
            continue
        tgt = A - depth * span if d == 1 else L + depth * span
        start = int(np.searchsorted(D["tl"], D["t15"][i], side="left"))
        if start >= len(D["tl"]):
            break
        pool = D["bear"] if d == 1 else D["bull"]
        p = int(np.searchsorted(pool, start, side="left"))
        if p >= len(pool):
            continue
        ei = int(pool[p])
        if D["tl"][ei] > D["t15"][i] + D["tf_min"] * 60_000:
            continue
        a = max(0, ei - stall)
        if stall:
            if ei - a < stall:
                continue
            seg = hi[a : ei + 1] if d == 1 else lo[a : ei + 1]
            if (seg.argmax() if d == 1 else seg.argmin()) >= (ei - a) * 0.5:
                continue
        entry = float(cl[ei])
        buf = BUF_FRAC * span
        stop = A + buf if d == 1 else L - buf
        if d == 1:
            if not (stop > entry > tgt):
                continue
            risk, rew = stop - entry, entry - tgt
        else:
            if not (stop < entry < tgt):
                continue
            risk, rew = entry - stop, tgt - entry
        if risk <= 0 or rew <= 0:
            continue
        used.add(key)
        for j in range(ei + 1, min(ei + 1 + MAX_HOLD, len(cl))):
            if d == 1:
                if hi[j] >= stop:
                    trades.append((D["tl"][ei], -1.0))
                    break
                if lo[j] <= tgt:
                    trades.append((D["tl"][ei], rew / risk))
                    break
            else:
                if lo[j] <= stop:
                    trades.append((D["tl"][ei], -1.0))
                    break
                if hi[j] >= tgt:
                    trades.append((D["tl"][ei], rew / risk))
                    break
    return trades, len(seen), len(passed)


def line(name, res):
    tr, seen, passed = res
    pct = 100 * passed / seen if seen else 0
    if len(tr) < 5:
        print(f"{name:<22} {passed:>5}/{seen:<6}{pct:>5.0f}%  {len(tr):>4}   too few")
        return None
    r = np.array([t[1] for t in tr])
    a = np.array([t[1] for t in tr if t[0] < SPLIT])
    b = np.array([t[1] for t in tr if t[0] >= SPLIT])
    se = r.std(ddof=1) / len(r) ** 0.5
    print(
        f"{name:<22} {passed:>5}/{seen:<6}{pct:>5.0f}%  {len(r):>4} {100 * (r > 0).mean():>6.1f}% "
        f"{r.sum():>+8.1f}R {r.mean():>+7.3f} {r.mean() / se:>6.2f} | "
        f"{a.sum():>+7.1f}R {b.sum():>+7.1f}R"
    )
    return r.mean()


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbols", nargs="+", default=["XAUUSD_p"])
    ap.add_argument("--htf", default="M15")
    ap.add_argument("--ltf", default="M1")
    ap.add_argument("--htf-min", type=int, default=15)
    ap.add_argument("--ratios", nargs="+", type=float, default=[2.0])
    ap.add_argument("--stalls", nargs="+", type=int, default=[240])
    ap.add_argument("--depths", nargs="+", type=float, default=[0.618, 0.786])
    ap.add_argument("--cache", default="backtest/cache/PUPrime_Demo")
    a = ap.parse_args()

    global CACHE
    CACHE = BarCache(ROOT / a.cache)
    print(f"entry frame {a.ltf}, GROSS of costs, split 2022-09-15")
    print(
        f"{'symbol / ratio / stall / target':<40} {'legs passing':>12}  {'n':>4} {'win':>7} "
        f"{'total':>9} {'perTr':>7} {'t':>6} | {'pre-2022':>7} {'post':>7}"
    )
    for sym in a.symbols:
        try:
            D = prep(sym, a.htf, a.ltf, a.htf_min)
        except Exception as ex:
            print(f"{sym:<40} load failed: {ex}")
            continue
        if D is None:
            print(f"{sym:<40} not enough cached data")
            continue
        for ratio in a.ratios:
            for stall in a.stalls:
                for depth in a.depths:
                    line(f"{sym} / {ratio:g}x / {stall} / {depth}", run(D, depth, stall, ratio))
        del D


if __name__ == "__main__":
    main()
