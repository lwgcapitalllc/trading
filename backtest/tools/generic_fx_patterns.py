"""generic_fx_patterns.py — where, when and on which days SOS Fade Generic setups turn, on FX.

Aaron, 2026-09-27: *"For GBPUSD and GBPJPY, find the patterns on each. Where does price typically
reject from? Where does it not? What times of day give good trades, which don't? When should we
not trade — time of day or day of week?"*

RULES, fixed before any result:

POPULATION  every setup (sweep or divergence arm, then the shift) whose pullback tagged the
            0.5-0.886 zone, M15, PU Prime bars. Collected with an impossible minimum stop so the
            bot never trades: every setup is recorded and each one is measured ALONE.
            ⚠ Since 2026-09-28 a setup is anchored on the bar the strategy FIRST reported the
            touch (the point-in-time feed, `backtest/setup_feed.py`). Every number this tool
            printed before then was anchored on the setup's DEEPEST zone visit, known only once it
            was over — see `backtest/notes/study-reconciliation.md` — and is NOT reconciled.
OUTCOME     from the zone touch: TURN = a new high/low (the 0.0) before breaking the 1.0; a bar
            touching both = FAIL; 30-day horizon. Entering at the zone's edge (0.5) with the stop at
            1.0 and the target at 0.0 is a 1:1 trade, so TURN% above 50 is the edge, before costs.
CUTS        New York hour of the zone touch (in 3-hour blocks), New York weekday, direction, what
            armed it, which liquidity pool was swept, whether a gap was in the zone, leg size
            (quartiles), and how deep the pullback had gone.
            DEPTH is read two ways: where the turners turned (the deepest fib reached before the
            new extreme), and the turn rate GIVEN price reached each depth.
HONESTY     each pair's window is split in two by date. A bucket is compared with the PAIR'S OWN
            turn rate (not 50% — a pair that turns 45% of the time would otherwise flag every
            bucket). It is called a pattern only if it sits on the SAME side of that rate in both
            halves AND is at least 2 standard errors from it on the whole window; z is printed.
            ⚠ ~35 buckets per pair are tested, so about one "pattern" per pair is expected by luck.

⚠ A SCREEN: no costs, no position slot. ⚠ Volume is not used.

Usage: python3 backtest/tools/generic_fx_patterns.py GBPUSD.p:2000-01-01 GBPJPY.p:2016-01-01
"""

import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "strategies/python")]

import numpy as np  # noqa: E402
from sos_fade_generic import SosFadeGenericConfig, SosFadeGenericStrategy  # noqa: E402

from backtest.data.cache import BarCache  # noqa: E402
from backtest.setup_feed import episodes, leg_side, replay_setups  # noqa: E402
from engines.fibonacci.geometry import fib_level  # noqa: E402

NY = ZoneInfo("America/New_York")
END, WARMUP, HORIZON = "2026-09-26", 500, 2880
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sun")


def collect(symbol, m15, on_signal=None, every_episode=False):
    """Every setup whose pullback touched the zone, AT THE BAR THE STRATEGY FIRST REPORTED IT.

    Read off the strategy's own setup snapshots through `backtest/setup_feed.py`, never off its
    miss records. 🔴 **The miss records were the old anchor and they looked ahead**: a miss's zone
    time brackets the setup's DEEPEST visit to the zone, known only once the setup is over, so every
    study built on it skipped the early entries — the ones that lose. Found 2026-09-28 by matching
    the 1m SOS-then-BOS study against its lab run (`backtest/notes/study-reconciliation.md`).

    A setup qualifies on a bar while it is armed by an enabled source, SOS'd, has touched the zone
    (0.5 or 0.618 tagged — no gap needed) and the 15m fib points its way: the same check the
    strategy's own 1-minute entry makes. The fib (`ash`, `asl`) is the one standing on that bar.

    One row per setup — its FIRST qualifying run — unless `every_episode`, which returns every
    unbroken run (a setup that stops qualifying and comes back is watched afresh, as the lab does).
    `on_signal(sig)`, if given, sees every bar's signals.
    """
    cfg = SosFadeGenericConfig(symbol=symbol, exec_min_stop_mode="Fixed $", exec_min_stop_val=1e12)
    strat = SosFadeGenericStrategy(cfg)
    if on_signal is not None:
        upd = strat.signals.update

        def watched(state):
            sig = upd(state)
            on_signal(sig)
            return sig

        strat.signals.update = watched
    rows = replay_setups(strat, m15, warmup=WARMUP)
    assert not strat.execution.trades, "the impossible stop floor let a trade through"
    eps = episodes(rows, lambda s: s.tradeable and s.touched is True and leg_side(s.leg) == s.side)
    step = rows[0].known_ms - rows[0].bar_ms if rows else 0
    out, seen = [], set()
    for e in eps:
        if not every_episode and e.key in seen:
            continue
        seen.add(e.key)
        r, snap = e.first, e.first.snap
        ext, org = snap.leg
        conf = {c.name: c for c in snap.confluences}
        anchor = snap.key.rsplit(":", 1)[-1]
        out.append(
            dict(
                key=snap.key,
                sos_ms=int(anchor[1:]) if anchor.startswith("t") else None,
                dir=snap.side,
                gap=conf["Retrace zone"].met,
                arm=conf["Arm"].detail,
                t=r.bar_ms,
                known_ms=r.known_ms,
                until_ms=e.rows[-1].known_ms + step,
                z=r.index,
                ash=ext if snap.side > 0 else org,
                asl=org if snap.side > 0 else ext,
                fdir=snap.side,
            )
        )
    return out


def walk(H, L, s):
    """TURN/FAIL from the zone touch, and the deepest fib ratio reached before the outcome."""
    d, z = s["dir"], s["z"]
    rng = s["ash"] - s["asl"]
    p0 = fib_level(s["ash"], s["asl"], s["fdir"], 0.0)
    p1 = fib_level(s["ash"], s["asl"], s["fdir"], 1.0)
    deep = 0.5
    for i in range(z, min(z + HORIZON, len(H))):
        far = L[i] if d > 0 else H[i]
        deep = max(deep, min(1.0, (p0 - far) / rng if d > 0 else (far - p0) / rng))
        if (L[i] <= p1) if d > 0 else (H[i] >= p1):
            return "FAIL", deep
        if i > z and ((H[i] >= p0) if d > 0 else (L[i] <= p0)):
            return "TURN", deep
    return "OPEN", deep


def ny(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(NY)


def tag(s, leg_q):
    t = ny(s["t"])
    trade_day = (t + timedelta(hours=7)).strftime("%a")  # 17:00 New York starts the next day
    arm = s["arm"]
    pool = arm.split("· ")[1] if "· " in arm else "none (divergence only)"
    src = (
        "sweep + div"
        if "Sweep + RSI div" in arm
        else "sweep"
        if arm.startswith("Sweep")
        else "divergence"
    )
    size = (s["ash"] - s["asl"]) / ((s["ash"] + s["asl"]) / 2) * 100
    q = sum(size > x for x in leg_q)
    return {
        "NY hour (zone touch)": f"{t.hour // 3 * 3:02d}-{t.hour // 3 * 3 + 3:02d}",
        "weekday (NY trading day)": trade_day,
        "direction": "long" if s["dir"] > 0 else "short",
        "what armed it": src,
        "liquidity swept": pool.replace("Ldn", "London"),
        "gap in the zone": "yes" if s["gap"] else "no",
        "leg size (quartile)": ("Q1 smallest", "Q2", "Q3", "Q4 largest")[q],
    }


def line(label, all_, a, b, base=None):
    def pct(x):
        n = x[0] + x[1]
        return (100 * x[0] / n if n else float("nan")), n

    p, n = pct(all_)
    pa, na = pct(a)
    pb, nb = pct(b)
    ref = p if base is None else base
    se = 100 * math.sqrt(ref / 100 * (1 - ref / 100) / n) if n else float("inf")
    z = (p - ref) / se if n and se else 0.0
    same = n and na and nb and (pa - ref) * (pb - ref) > 0
    verdict = "PATTERN +" if same and z >= 2 else "PATTERN -" if same and z <= -2 else "noise"
    return (
        f"    {label:24s} {p:5.1f}% ({n:4d})   1st half {pa:5.1f}% ({na:3d})  "
        f"2nd half {pb:5.1f}% ({nb:3d})   z {z:+5.1f}  {verdict}"
    )


def main(arg):
    symbol, start = arg.split(":")
    cache = BarCache(ROOT / "backtest/cache/PUPrime_Demo")
    m15 = cache.load(symbol, "M15").loc[start:END]
    H, L = m15["high"].to_numpy(), m15["low"].to_numpy()
    S = collect(symbol, m15)
    sizes = [(s["ash"] - s["asl"]) / ((s["ash"] + s["asl"]) / 2) * 100 for s in S]
    leg_q = list(np.percentile(sizes, [25, 50, 75]))
    mid = S[len(S) // 2]["t"]
    tab = defaultdict(lambda: [[0, 0], [0, 0], [0, 0]])  # all, 1st half, 2nd half
    depth_turn = defaultdict(int)
    reached = defaultdict(lambda: [0, 0])
    tot = [[0, 0], [0, 0], [0, 0]]
    for s in S:
        res, deep = walk(H, L, s)
        if res == "OPEN":
            continue
        k = 0 if res == "TURN" else 1
        h = 1 if s["t"] < mid else 2
        for c in (0, h):
            tot[c][k] += 1
        for cut, bucket in tag(s, leg_q).items():
            for c in (0, h):
                tab[(cut, bucket)][c][k] += 1
        if res == "TURN":
            band = next(
                b
                for b in ("0.5-0.618", "0.618-0.702", "0.702-0.786", "0.786-0.886", "0.886-1.0")
                if deep < float(b.split("-")[1]) or b == "0.886-1.0"
            )
            depth_turn[band] += 1
        for lv in (0.618, 0.702, 0.786, 0.886):
            if deep >= lv:
                reached[lv][k] += 1

    print(
        f"\n== {symbol}  {start} -> {END}   {sum(tot[0])} setups reached the zone   "
        f"halves split at {ny(mid):%Y-%m-%d}"
    )
    base = 100 * tot[0][0] / sum(tot[0])
    print(line("ALL", *tot).replace("noise", "(the baseline)"))
    cuts = []
    for cut, bucket in tab:
        if cut not in cuts:
            cuts.append(cut)
    order = {"weekday (NY trading day)": DAYS}
    for cut in cuts:
        print(f"  {cut}")
        buckets = sorted(b for c, b in tab if c == cut)
        if cut in order:
            buckets = [b for b in order[cut] if b in buckets]
        for b in buckets:
            print(line(b, *tab[(cut, b)], base=base))
    nt = sum(depth_turn.values())
    print("  where the TURNERS turned (deepest fib reached before the new high/low)")
    for b in ("0.5-0.618", "0.618-0.702", "0.702-0.786", "0.786-0.886", "0.886-1.0"):
        print(f"    {b:12s} {100 * depth_turn[b] / nt:5.1f}%  ({depth_turn[b]})")
    print(
        "  turn rate GIVEN the pullback reached at least this deep (it then needs to go all the "
        "way to the 0.0)"
    )
    for lv in (0.618, 0.702, 0.786, 0.886):
        t, f = reached[lv]
        print(
            f"    reached {lv:<5}  {100 * t / (t + f):5.1f}% turned ({t + f})   "
            f"break-even at an entry there: {100 * (1 - lv):.1f}%"
        )


if __name__ == "__main__":
    for a in sys.argv[1:]:
        main(a)
