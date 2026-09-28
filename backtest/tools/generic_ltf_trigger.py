"""generic_ltf_trigger.py — when a zone touch turns, did a 1-5 minute structure shift call it?

Aaron, 2026-09-27: *"For SOS Fade trades where price retraced into the zone then went on to make a
new high, go on a lower timeframe: after price turned, was it because of a 1-5 min SOS followed by
a BOS, or any internal structure pattern? From 2020-01-01. I want a pattern that gives a return."*

RULES, fixed before any result (long side; shorts mirror):

POPULATION  SOS Fade Generic setups whose pullback tagged the 0.5-0.886 zone on M15, zone touch on
            or after 2020-01-01; outcome TURN (0.0 before 1.0) or FAIL, as generic_fx_patterns.py.
LTF         the canonical structure engine, fresh per setup, run on M1 or M5 from 1,500 bars before
            the zone touch (warm-up) to the M15 outcome. Default swing length.
PATTERNS    in the trade's direction, completed on an LTF bar after price reached the 0.5 and
            BEFORE any LTF bar touched the 0.0 or the 1.0 (a pattern after the 1.0 belongs to a
            setup that already stopped out — counting it was a look-ahead the first run had):
              ext SOS -> BOS   an external SOS, then an external BOS
              ext SOS          an external SOS
              int SOS -> BOS   an internal SOS, then an internal BOS
              any internal     any internal SOS or BOS
PREVALENCE  share of TURN and of FAIL setups that showed each pattern. ⚠ A turn to a new high must
            break small structure on the way, so the TURN column is near 100% by construction —
            only the gap between the columns means anything.
TRADE       the one that could be taken: at the close of the LTF bar the FIRST such pattern
            completes, if price is still between the M15 1.0 and 0.0, enter at that close; stop
            1.0, target 0.0, walked on LTF bars (a bar touching both = loss, 30 days).
            Win rate vs its break-even (entry-to-stop / stop-to-target); z on the whole window and
            the same side in both date halves. Gross R, then NET R.
COSTS       PU Prime ECN, as measured in backtest/fills.py and charged the way the lab's bar mode
            charges them: one full spread per round trip, $1/side/lot commission, and the swap at
            every 17:00-New-York rollover held through (Saturday books none, Wednesday three).
            Yen figures convert at the hourly USDJPY rate through the lab's own conversion.
CONTROL     the same trade entered at the close of the first LTF bar in the zone — knows nothing
            about structure; if it beat break-even the study would be biased.
            ⚠ A "random bar of the live window" control was tried and dropped: the window ENDS at
            the first 0.0/1.0 touch, so picking inside it uses the future (it printed -0.18R, z -3.7).

Usage: python3 backtest/tools/generic_ltf_trigger.py GBPJPY.p:M1 GBPJPY.p:M5 GBPUSD.p:M5
"""

import math
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "strategies/python"), str(ROOT / "backtest/tools")]

import numpy as np  # noqa: E402
from generic_fx_patterns import END, collect, walk  # noqa: E402

from backtest.data.cache import BarCache  # noqa: E402
from backtest.data.fx import rate_provider_for  # noqa: E402
from backtest.data.source import BarSource  # noqa: E402
from backtest.fills import PROFILES  # noqa: E402
from engines.fibonacci.geometry import fib_level  # noqa: E402
from engines.market_structure.engine import StructureEngine  # noqa: E402
from engines.market_structure.types import Bar  # noqa: E402

START, LOAD_FROM, LTF_WARM = "2020-01-01", "2019-06-01", 1500
LTF_HORIZON_MIN = 30 * 24 * 60
PATTERNS = ("ext SOS -> BOS", "ext SOS", "int SOS -> BOS", "any internal", "CONTROL zone touch")


def scan(eng_out, d):
    """First completion bar (window offset) of each pattern, from per-bar engine events."""
    first, ext_sos, int_sos = {}, False, False
    for k, ev in eng_out:
        x, n = ev.external, ev.internal
        e_sos, e_bos = (x.bull_sos, x.bull_bos) if d > 0 else (x.bear_sos, x.bear_bos)
        i_sos, i_bos = (n.bull_sos, n.bull_bos) if d > 0 else (n.bear_sos, n.bear_bos)
        if e_sos:
            first.setdefault("ext SOS", k)
        if ext_sos and e_bos and not e_sos:
            first.setdefault("ext SOS -> BOS", k)
        if int_sos and i_bos and not i_sos:
            first.setdefault("int SOS -> BOS", k)
        if i_sos or i_bos:
            first.setdefault("any internal", k)
        ext_sos |= e_sos
        int_sos |= i_sos
    return first


def rollovers(t0_ms, t1_ms):
    """Dates of the 17:00-New-York rollovers in (t0, t1], Saturday skipped — the lab's rule."""
    ny = ZoneInfo("America/New_York")
    day = datetime.fromtimestamp(t0_ms / 1000, tz=timezone.utc).astimezone(ny).date()
    out = []
    while True:
        roll = datetime.combine(day, time(17), tzinfo=ny)
        ms = roll.timestamp() * 1000
        if ms > t1_ms:
            return out
        if ms > t0_ms and day.weekday() != 5:
            out.append(day)
        day += timedelta(days=1)


def cost_in_price(profile, rate, d, t0_ms, t1_ms):
    """Round-trip cost of one unit, in PRICE units (the quote currency). Positive = a cost."""
    qta = rate(t0_ms) if rate else 1.0  # account currency per unit of quote currency
    commission = 2 * profile.commission(1.0) / qta
    swap = sum(profile.swap.charge(d, profile.lots(1.0), day) for day in rollovers(t0_ms, t1_ms))
    return profile.spread_or_refuse() + commission - swap


def main(arg):
    symbol, tf = arg.split(":")
    cache = BarCache(ROOT / "backtest/cache/PUPrime_Demo")
    m15 = cache.load(symbol, "M15").loc[LOAD_FROM:END]
    ltf = cache.load(symbol, tf).loc[LOAD_FROM:END]
    H15, L15 = m15["high"].to_numpy(), m15["low"].to_numpy()
    t15 = m15.index.values.astype("datetime64[ms]").astype("int64")
    tl = ltf.index.values.astype("datetime64[ms]").astype("int64")
    O, Hl, Ll, C = (ltf[c].to_numpy() for c in ("open", "high", "low", "close"))
    step = int(tf[1:]) * 60_000
    horizon = LTF_HORIZON_MIN * 60_000 // step
    ltf_end = tl[-1]
    profile = PROFILES["puprime_ecn_" + symbol[:6].lower()]
    rate = rate_provider_for(BarSource(server="PUPrime-Demo"), symbol, LOAD_FROM, END)

    rows = []
    for s in collect(symbol, m15):
        if (
            s["t"] < np.datetime64(START).astype("datetime64[ms]").astype("int64")
            or s["t"] > ltf_end
        ):
            continue
        res, _ = walk(H15, L15, s)
        if res == "OPEN":
            continue
        # the M15 bar the outcome printed on: re-walk to find it
        d, p0 = s["dir"], fib_level(s["ash"], s["asl"], s["fdir"], 0.0)
        p1 = fib_level(s["ash"], s["asl"], s["fdir"], 1.0)
        j = s["z"]
        while not (
            (L15[j] <= p1 or (j > s["z"] and H15[j] >= p0))
            if d > 0
            else (H15[j] >= p1 or (j > s["z"] and L15[j] <= p0))
        ):
            j += 1
        a = int(np.searchsorted(tl, s["t"]))  # first LTF bar of the zone-touch M15 bar
        b = int(np.searchsorted(tl, t15[j] + 15 * 60_000))
        # The live window: from the first LTF bar that reaches the zone (the 0.5) to the bar BEFORE
        # the first one that touches the 0.0 or the 1.0. A pattern after either touch is not this
        # setup any more — after the 1.0 it is a setup that already stopped out.
        p5 = fib_level(s["ash"], s["asl"], s["fdir"], 0.5)
        k0 = next((k for k in range(a, b) if (Ll[k] <= p5 if d > 0 else Hl[k] >= p5)), b)
        kx = next(
            (
                k
                for k in range(k0, b)
                if ((Hl[k] >= p0 or Ll[k] <= p1) if d > 0 else (Ll[k] <= p0 or Hl[k] >= p1))
            ),
            b,
        )
        w0 = max(0, a - LTF_WARM)
        eng, out = StructureEngine(), []
        for k in range(w0, kx):
            ev = eng.update(Bar(k - w0, O[k], Hl[k], Ll[k], C[k]))
            if k >= k0:
                out.append((k, ev))
        first = scan(out, d)
        # CONTROLS — entries that know nothing about structure, on the same window, stop and target.
        # If these beat break-even too, the study is biased, not the pattern good.
        if kx > k0:
            first["CONTROL zone touch"] = k0
        trades = {}
        for p, k in first.items():
            e = C[k]
            if not ((p1 < e < p0) if d > 0 else (p0 < e < p1)):
                continue
            win = None
            for m in range(k + 1, min(k + 1 + horizon, len(C))):
                if (Ll[m] <= p1) if d > 0 else (Hl[m] >= p1):
                    win = False
                    break
                if (Hl[m] >= p0) if d > 0 else (Ll[m] <= p0):
                    win = True
                    break
            if win is not None:
                risk = abs(e - p1)
                cost = cost_in_price(profile, rate, d, int(tl[k]) + step, int(tl[m]) + step)
                trades[p] = (win, abs(p0 - e) / risk, risk / abs(p0 - p1), cost / risk)
        rows.append(dict(t=s["t"], turn=res == "TURN", seen=set(first), trades=trades))

    mid = rows[len(rows) // 2]["t"]
    nt = sum(r["turn"] for r in rows)
    print(
        f"\n== {symbol} {tf}  {START} -> {END}   {len(rows)} setups ({nt} turned, "
        f"{len(rows) - nt} failed)"
    )
    print("  pattern            seen in TURNERS   seen in FAILERS  |  trade at the pattern's close")
    for p in PATTERNS:
        st = 100 * sum(p in r["seen"] for r in rows if r["turn"]) / max(nt, 1)
        sf = 100 * sum(p in r["seen"] for r in rows if not r["turn"]) / max(len(rows) - nt, 1)
        tr = [(r["t"], *r["trades"][p]) for r in rows if p in r["trades"]]
        net = [(x[2] if x[1] else -1.0) - x[4] for x in tr]
        if not tr:
            print(f"  {p:16s}   {st:5.1f}%            {sf:5.1f}%          |  no trades")
            continue
        n = len(tr)
        w = sum(x[1] for x in tr) / n
        be = sum(x[3] for x in tr) / n  # mean break-even win rate
        r = sum(x[2] if x[1] else -1.0 for x in tr) / n
        wa = [x[1] for x in tr if x[0] < mid]
        wb = [x[1] for x in tr if x[0] >= mid]
        ba = sum(x[3] for x in tr if x[0] < mid) / max(len(wa), 1)
        bb = sum(x[3] for x in tr if x[0] >= mid) / max(len(wb), 1)
        ra = [x[2] if x[1] else -1.0 for x in tr if x[0] < mid]
        rb = [x[2] if x[1] else -1.0 for x in tr if x[0] >= mid]
        sd = float(np.std([x[2] if x[1] else -1.0 for x in tr])) or 1.0
        z = r / (sd / math.sqrt(n))
        same = (np.mean(ra) if ra else 0) * (np.mean(rb) if rb else 0) > 0 and np.sign(
            np.mean(ra)
        ) == np.sign(r)
        tag = "EDGE +" if same and z >= 2 else "HARM -" if same and z <= -2 else "noise"
        print(
            f"  {p:16s}   {st:5.1f}%            {sf:5.1f}%          |  {n:4d} trades  win "
            f"{100 * w:5.1f}% vs {100 * be:4.1f}% needed (halves {100 * np.mean(wa):4.1f}/"
            f"{100 * ba:4.1f}, {100 * np.mean(wb):4.1f}/{100 * bb:4.1f})  R/trade {r:+.3f}  "
            f"z {z:+5.1f}  {tag}"
        )
        na = [v for x, v in zip(tr, net) if x[0] < mid]
        nb = [v for x, v in zip(tr, net) if x[0] >= mid]
        rn = float(np.mean(net))
        zn = rn / ((float(np.std(net)) or 1.0) / math.sqrt(n))
        same_n = np.sign(np.mean(na)) == np.sign(np.mean(nb)) == np.sign(rn) if na and nb else False
        tag_n = "EDGE +" if same_n and zn >= 2 else "HARM -" if same_n and zn <= -2 else "noise"
        costs = sorted(x[4] for x in tr)
        print(
            f"  {'':16s}   {'':34s}|  NET: cost {np.mean(costs):.3f}R mean, "
            f"{costs[len(costs) // 2]:.3f}R median  R/trade {rn:+.3f} (halves "
            f"{np.mean(na):+.3f} / {np.mean(nb):+.3f})  z {zn:+5.1f}  {tag_n}"
        )


if __name__ == "__main__":
    for a in sys.argv[1:]:
        main(a)
