"""generic_ltf_trigger.py — when a zone touch turns, did a 1-5 minute structure shift call it?

Aaron, 2026-09-27: *"For SOS Fade trades where price retraced into the zone then went on to make a
new high, go on a lower timeframe: after price turned, was it because of a 1-5 min SOS followed by
a BOS, or any internal structure pattern? From 2020-01-01. I want a pattern that gives a return."*

RULES, fixed before any result (long side; shorts mirror):

🔴 REBUILT 2026-09-28 ON THE POINT-IN-TIME FEED. The first version anchored each setup on its miss
record's zone time — the setup's DEEPEST zone visit, known only once it was over — and printed
+0.26R a trade net on GBPJPY for "ext SOS -> BOS" where the lab made -0.06R. Those numbers are NOT
reconciled. This version watches each setup exactly as the strategy's own 1-minute entry does
(`strategies/python/sos_fade/shift_entry.py`); reconciliation: `backtest/notes/study-reconciliation.md`.

POPULATION  SOS Fade Generic setups whose pullback touched the zone on M15 (0.5 or 0.618 tagged, no
            gap needed), armed by an enabled source, SOS'd, the 15m fib pointing their way — read
            from the strategy's setup snapshots (`backtest/setup_feed.py`), one watch per unbroken
            run of 15m bars that reports it, first report on or after 2020-01-01. Outcome TURN
            (0.0 before 1.0) or FAIL, as generic_fx_patterns.py, from the first report.
LEVELS      the 15m 1.0 and 0.0 standing on the bar that FIRST reported the touch, frozen.
LTF         ONE continuous structure feed over the whole window — the strategy's own 1-minute
            feed (`Structure1m`, swing length 15), started on the window's first bar, as the lab's is.
WINDOW      the lab's: an SOS on any LTF bar of the 15m bar that reported the touch counts; nothing
            else is seen before that bar CLOSES. From then until the 15m side stops reporting the
            setup, the first LTF wick to the 1.0 or the 0.0 ends the watch for good, checked BEFORE
            the signal. A setup that stops being reported and comes back is watched afresh.
PATTERNS    in the trade's direction; the FIRST completion is the trade, taken or not:
              ext SOS -> BOS   an external SOS, then an external BOS
              ext SOS          an external SOS
              int SOS -> BOS   an internal SOS, then an internal BOS
              any internal     any internal SOS or BOS
PREVALENCE  share of TURN and of FAIL setups that showed each pattern. ⚠ A turn to a new high must
            break small structure on the way, so the TURN column is near 100% by construction —
            only the gap between the columns means anything.
TRADE       the lab's: if the completing bar closes beyond the 1.0, enter at the NEXT bar's open;
            stop 1.0, target 0.0, walked on LTF bars to the end of the data (a bar touching
            both = loss); a short's stop and target trigger on the ask, as the lab's fills do.
            Win rate vs its break-even (entry-to-stop / stop-to-target); z on the whole window and
            the same side in both date halves. Gross R, then NET R.
COSTS       PU Prime ECN, as measured in backtest/fills.py and charged the way the lab's bar mode
            charges them: one full spread per round trip (a long as a cost, a short through its
            exits triggering on the ask), $1/side/lot commission, and the swap at
            every 17:00-New-York rollover held through (Saturday books none, Wednesday three).
            Yen figures convert at the hourly USDJPY rate through the lab's own conversion.
CONTROL     the same trade entered on the first LTF bar after the touch is known — knows nothing
            about structure; if it beat break-even the study would be biased.
DELIBERATE  vs the lab: every setup is taken (the lab holds one position at a time) and there is
            no minimum stop (the lab refuses a stop under its floor; `--min-stop-pct` NOTES them).
            ⚠ A "random bar of the live window" control was tried and dropped: the window ENDS at
            the first 0.0/1.0 touch, so picking inside it uses the future (it printed -0.18R, z -3.7).

Usage: python3 backtest/tools/generic_ltf_trigger.py GBPJPY.p:M1 GBPJPY.p:M5 GBPUSD.p:M5
       ... GBPJPY.p:M1 --dump study.json --min-stop-pct 0.08   (the "ext SOS -> BOS" trades, for
       backtest/tools/study_vs_lab.py; the first pair given)
"""

import argparse
import json
import math
import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "strategies/python"), str(ROOT / "backtest/tools")]

import numpy as np  # noqa: E402
from generic_fx_patterns import END, collect, walk  # noqa: E402
from sos_fade.secondary import Structure1m  # noqa: E402

from backtest.data.cache import BarCache  # noqa: E402
from backtest.data.fx import rate_provider_for  # noqa: E402
from backtest.data.source import BarSource  # noqa: E402
from backtest.fills import PROFILES  # noqa: E402
from engines.fibonacci.geometry import fib_level  # noqa: E402

START, LOAD_FROM = "2020-01-01", "2019-06-01"
PATTERNS = ("ext SOS -> BOS", "ext SOS", "int SOS -> BOS", "any internal", "CONTROL zone touch")


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


def cost_in_price(profile, rate, d, t0_ms, t1_ms, spread=True):
    """Round-trip cost of one unit, in PRICE units (the quote currency). Positive = a cost.

    `spread=False` for a trade that already paid it in its fills — a short whose stop and target
    trigger on the ask (see `trade`). Charging it again made every matched GBPJPY short 0.029R
    worse than the lab while longs agreed to 0.001R (2026-09-28).
    """
    qta = rate(t0_ms) if rate else 1.0  # account currency per unit of quote currency
    commission = 2 * profile.commission(1.0) / qta
    swap = sum(profile.swap.charge(d, profile.lots(1.0), day) for day in rollovers(t0_ms, t1_ms))
    return (profile.spread_or_refuse() if spread else 0.0) + commission - swap


def ltf_events(O, H, L, C):
    """Per LTF bar, the strategy's own 1-minute structure feed: external and internal SOS / BOS,
    by direction. One engine over the whole window, as the lab runs it."""
    n = len(C)
    ev = {
        k: np.zeros(n, dtype=bool)
        for k in ("xs1", "xs-1", "xb1", "xb-1", "is1", "is-1", "ib1", "ib-1")
    }
    st = Structure1m(major_length=15)
    for k in range(n):
        m = st.update(k, O[k], H[k], L[k], C[k])
        ev["xs1"][k], ev["xs-1"][k] = m.new_bull_sos, m.new_bear_sos
        ev["xb1"][k], ev["xb-1"][k] = m.new_bull_bos, m.new_bear_bos
        for d, kind in m.internal_breaks:
            ev[("is" if kind == "sos" else "ib") + str(d)][k] = True
    return ev


def completes(p, ev, d, k, seen):
    """Does pattern `p` complete on LTF bar `k`? `seen` = its SOS already printed in the window."""
    if p == "ext SOS -> BOS":
        return seen and ev[f"xb{d}"][k] and not ev[f"xs{d}"][k]
    if p == "ext SOS":
        return ev[f"xs{d}"][k]
    if p == "int SOS -> BOS":
        return seen and ev[f"ib{d}"][k] and not ev[f"is{d}"][k]
    if p == "any internal":
        return ev[f"is{d}"][k] or ev[f"ib{d}"][k]
    return True  # CONTROL: the first bar that can act


def sos_key(p, d):
    return {"ext SOS -> BOS": f"xs{d}", "int SOS -> BOS": f"is{d}"}.get(p)


def first_completion(p, eps, ev, tl, Hl, Ll, C):
    """{setup key: (episode, LTF bar)} — each setup's FIRST completion of `p`, watched the lab's way."""
    dead, out = set(), {}
    for s in eps:
        if s["key"] in dead:
            continue
        d, p0 = s["dir"], fib_level(s["ash"], s["asl"], s["fdir"], 0.0)
        p1 = fib_level(s["ash"], s["asl"], s["fdir"], 1.0)
        a0, a, b = np.searchsorted(tl, [s["t"], s["known_ms"], s["until_ms"]])
        sk = sos_key(p, d)
        seen = bool(sk and ev[sk][a0:a].any())
        for k in range(a, b):
            if (Ll[k] <= p1 or Hl[k] >= p0) if d > 0 else (Hl[k] >= p1 or Ll[k] <= p0):
                dead.add(s["key"])
                break
            if completes(p, ev, d, k, seen):
                dead.add(s["key"])
                out[s["key"]] = (s, k)
                break
            if sk:
                seen = seen or bool(ev[sk][k])
    return out


def trade(s, k, O, Hl, Ll, C, tl, step, spread, profile, rate):
    """The lab's trade off a completion on bar `k`, or None if it cannot be taken or never ends.

    ⚠ **A short's stop and target trigger on the ASK** (bid bar + spread), as the lab's bid/ask
    fills do; a long's on the bid bar. Found by the reconciliation: two GBPJPY shorts the bid
    walk called wins — one touched its target exactly on the bid, one missed its stop by 0.011 —
    were lab losses. ⚠ No time limit, as the lab has none: a trade walks to the end of the data.
    """
    d = s["dir"]
    p0 = fib_level(s["ash"], s["asl"], s["fdir"], 0.0)
    p1 = fib_level(s["ash"], s["asl"], s["fdir"], 1.0)
    if (C[k] - p1) * d <= 0 or k + 1 >= len(O):
        return None
    e = O[k + 1]
    if not ((p1 < e < p0) if d > 0 else (p0 < e < p1)):
        return None
    for m in range(k + 1, len(C)):
        if (Ll[m] <= p1) if d > 0 else (Hl[m] + spread >= p1):
            win = False
            break
        if (Hl[m] >= p0) if d > 0 else (Ll[m] + spread <= p0):
            win = True
            break
    else:
        return None
    risk = abs(e - p1)
    cost = cost_in_price(profile, rate, d, int(tl[k + 1]), int(tl[m]) + step, spread=d > 0)
    return dict(
        t=s["t"],
        entry_ms=int(tl[k + 1]),
        win=win,
        rr=abs(p0 - e) / risk,
        be=risk / abs(p0 - p1),
        cost=cost / risk,
        stop_pct=100 * risk / e,
    )


def main(arg, dump=None, min_stop_pct=None):
    symbol, tf = arg.split(":")
    cache = BarCache(ROOT / "backtest/cache/PUPrime_Demo")
    m15 = cache.load(symbol, "M15").loc[LOAD_FROM:END]
    ltf = cache.load(symbol, tf).loc[START:END]
    H15, L15 = m15["high"].to_numpy(), m15["low"].to_numpy()
    tl = ltf.index.values.astype("datetime64[ms]").astype("int64")
    O, Hl, Ll, C = (ltf[c].to_numpy() for c in ("open", "high", "low", "close"))
    step = int(tf[1:]) * 60_000
    profile = PROFILES["puprime_ecn_" + symbol[:6].lower()]
    spread = profile.spread_or_refuse()
    rate = rate_provider_for(BarSource(server="PUPrime-Demo"), symbol, LOAD_FROM, END)

    start_ms = int(np.datetime64(START).astype("datetime64[ms]").astype("int64"))
    eps = [
        s
        for s in collect(symbol, m15, every_episode=True)
        if s["t"] >= start_ms and s["until_ms"] <= tl[-1]
    ]
    ev = ltf_events(O, Hl, Ll, C)

    # One row per SETUP: its 15m outcome from the first report (None if still open after 30 days
    # — it then counts in no prevalence column, but its trades still count, as the lab takes them),
    # and which patterns it showed.
    firsts = {}
    for s in eps:
        firsts.setdefault(s["key"], s)
    rows = {}
    for key, s in firsts.items():
        res, _ = walk(H15, L15, s)
        rows[key] = dict(
            t=s["t"], turn=None if res == "OPEN" else res == "TURN", seen=set(), trades={}
        )
    for p in PATTERNS:
        for key, (s, k) in first_completion(p, eps, ev, tl, Hl, Ll, C).items():
            rows[key]["seen"].add(p)
            tr = trade(s, k, O, Hl, Ll, C, tl, step, spread, profile, rate)
            if tr is not None:
                tr["key"], tr["sos_ms"], tr["dir"] = key, s["sos_ms"], s["dir"]
                tr["start_ms"] = s["known_ms"]
                rows[key]["trades"][p] = tr
    rows = sorted(rows.values(), key=lambda r: r["t"])

    if dump:
        doc = dict(
            label=f"generic_ltf_trigger {symbol} {tf} ext SOS -> BOS (every setup, no position slot)",
            trades=[
                dict(
                    entry_ms=x["entry_ms"],
                    dir=x["dir"],
                    r=(x["rr"] if x["win"] else -1.0) - x["cost"],
                    setup=x["key"],
                    start_ms=x["start_ms"],
                    note=(
                        f"stop {x['stop_pct']:.3f}% of price, under the {min_stop_pct}% minimum"
                        if min_stop_pct is not None and x["stop_pct"] < min_stop_pct
                        else ""
                    ),
                )
                for r in rows
                if (x := r["trades"].get("ext SOS -> BOS"))
            ],
            setups=[
                dict(setup=s["key"], dir=s["dir"], sos_ms=s["sos_ms"], start_ms=s["known_ms"])
                for s in eps
                if s["sos_ms"] is not None
            ],
        )
        json.dump(doc, open(dump, "w"))
        print(f"  wrote {len(doc['trades'])} trades, {len(doc['setups'])} watches -> {dump}")

    mid = rows[len(rows) // 2]["t"]
    nt = sum(r["turn"] is True for r in rows)
    nf = sum(r["turn"] is False for r in rows)
    print(
        f"\n== {symbol} {tf}  {START} -> {END}   {len(rows)} setups ({nt} turned, {nf} failed, "
        f"{len(rows) - nt - nf} still open after 30 days)"
    )
    print("  pattern            seen in TURNERS   seen in FAILERS  |  trade at the pattern's close")
    for p in PATTERNS:
        st = 100 * sum(p in r["seen"] for r in rows if r["turn"] is True) / max(nt, 1)
        sf = 100 * sum(p in r["seen"] for r in rows if r["turn"] is False) / max(nf, 1)
        tr = [
            (r["t"], x["win"], x["rr"], x["be"], x["cost"])
            for r in rows
            if (x := r["trades"].get(p))
        ]
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
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs", nargs="+", help="SYMBOL:TF, e.g. GBPJPY.p:M1")
    ap.add_argument(
        "--dump", help="write the first pair's ext SOS -> BOS trades for study_vs_lab.py"
    )
    ap.add_argument("--min-stop-pct", type=float, help="note trades whose stop is under this")
    a = ap.parse_args()
    for i, pair in enumerate(a.pairs):
        main(pair, dump=a.dump if i == 0 else None, min_stop_pct=a.min_stop_pct)
