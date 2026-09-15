#!/usr/bin/env python3
"""killzone_features.py — snapshot every canonical engine at one clock time, every day, and
record what price did afterwards.

One row per NY trading day. The FEATURES are each engine's state as it stood the instant the
snapshot bar opened (default 10:00 NY) — built only from bars that had already closed. The
OUTCOMES are the prices that followed. Nothing downstream of this file may use an outcome
column as a feature; the split between the two is the whole point of the table.

Generic at the seam: `--at` takes any NY time, so the same table answers "what predicts the
11:45 zone" or "what predicts the London open" without a second builder.

🔴 **No lookahead, and the ORDER OF OPERATIONS is what guarantees it.** On each incoming bar:
  1. if it starts a new M15 / H1 bucket, the PREVIOUS bucket is complete → feed it to that
     timeframe's structure engine;
  2. if it is the snapshot bar, snapshot NOW — every M5 engine has seen up to the bar before;
  3. only then feed this bar to the M5 engines.
Step 2 before step 3 is the entire no-lookahead guarantee. Swap them and every feature
silently includes the first five minutes of the move it is meant to predict.

⚠ **"No news data" is not "no news".** The calendar only covers the dates it was fetched for;
outside that range the news features are written EMPTY, never False (rule 1).

Engines used (public API only — `engines/*/CLAUDE.md`): market_structure (M5, M15, H1),
order_blocks, liquidity, vwap, session_volume_profile, fair_value_gaps, rsi_divergence,
equal_highs_lows, candlesticks, news. `regime` is left out on purpose: it is a DataFrame
classifier with its own window contract, and a guessed window is a guessed feature.

Usage:
    python3 backtest/tools/killzone_features.py
    python3 backtest/tools/killzone_features.py --at 11:45 --out backtest/reports/kz_features/f1145.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
_ENGINES = _ROOT / "engines"
for _p in (str(_ROOT), str(_ENGINES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from candlesticks import BEARISH, BULLISH, CandlestickEngine  # noqa: E402
from equal_highs_lows import EqualHighsLowsEngine  # noqa: E402
from fair_value_gaps import FairValueGapEngine  # noqa: E402
from liquidity import LiquidityEngine  # noqa: E402
from market_structure import Bar, StructureEngine  # noqa: E402
from news import EventStore, Impact, NewsEngine  # noqa: E402
from order_blocks import OrderBlockEngine  # noqa: E402
from rsi_divergence import RsiDivergenceEngine  # noqa: E402
from session_volume_profile import SvpEngine  # noqa: E402
from vwap import VwapEngine  # noqa: E402

from backtest.tools.killzone_profile import CACHE, DEFAULT_SERVER, _safe_token  # noqa: E402

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
T = dt.time

# Exit checkpoints, NY time. Each outcome column is the close of the last bar BEFORE it.
CHECKPOINTS = (T(10, 15), T(10, 30), T(11, 0), T(12, 15), T(13, 0), T(13, 45), T(16, 0))
_MIN_DAY_COVERAGE = 0.70


class _Htf:
    """Aggregates the M5 stream into one higher timeframe and feeds a structure engine each
    time a bucket COMPLETES. Buckets are UTC-floored; NY sits on whole-hour offsets from UTC,
    so an H1 bucket is exactly one NY hour."""

    def __init__(self, minutes: int):
        self.minutes = minutes
        self.engine = StructureEngine()
        self.key = None
        self.o = self.h = self.l = self.c = None
        self.n = 0

    def push(self, ts: dt.datetime, o, h, l, c) -> None:
        key = (ts - dt.datetime.min.replace(tzinfo=UTC)).total_seconds() // (60 * self.minutes)
        if key != self.key:
            if self.key is not None:
                self.engine.update(Bar(self.n, self.o, self.h, self.l, self.c))
                self.n += 1
            self.key, self.o, self.h, self.l, self.c = key, o, h, l, c
        else:
            self.h, self.l, self.c = max(self.h, h), min(self.l, l), c


def _sign(x):
    return None if x is None else (1 if x > 0 else (-1 if x < 0 else 0))


def build(symbol: str, tf: str, server: str, at: dt.time) -> list[dict]:
    path = CACHE / _safe_token(server) / f"{symbol}__{tf}.csv"
    if not path.exists():
        raise SystemExit(f"no cached bars at {path}")

    ms5 = StructureEngine()
    m15, h1 = _Htf(15), _Htf(60)
    obe = OrderBlockEngine()
    liq = LiquidityEngine()
    vwe = VwapEngine()
    svp = SvpEngine()
    fvg = FairValueGapEngine()
    rsi = RsiDivergenceEngine()
    eqe = EqualHighsLowsEngine()
    cse = CandlestickEngine()
    events, covered = EventStore().load()
    news = NewsEngine(events, covered_ranges=covered)

    # Scheduled USD releases in the snapshot's first 15 minutes, by NY date. A calendar fact,
    # known in advance — not lookahead.
    at_end = (dt.datetime.combine(dt.date.today(), at) + dt.timedelta(minutes=15)).time()
    usd_at = defaultdict(int)
    for e in events:
        if e.currency != "USD" or e.impact < Impact.MEDIUM:
            continue
        ny = dt.datetime.fromtimestamp(e.timestamp_ms / 1000, UTC).astimezone(NY)
        if at <= ny.time() < at_end:
            usd_at[ny.date()] = max(usd_at[ny.date()], int(e.impact))

    last = {}
    sweeps = defaultdict(list)  # NY date -> [(time, side, name)]
    by_day = defaultdict(list)  # NY date -> [(time, o, h, l, c)]
    snaps: dict[dt.date, dict] = {}
    prev_close = None

    with path.open(newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            ts = dt.datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            ms = int(ts.timestamp() * 1000)
            o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
            if row.get("volume") in (None, "", "nan", "NaN"):
                # The VWAP engine takes a float, and 0.0 would be a measurement where there is
                # none — a VWAP averages straight through it. Refuse; re-pull the bars.
                raise SystemExit(f"{path.name} row {i} ({row['time']}) has no volume")
            v = float(row["volume"])
            ny = ts.astimezone(NY)
            d, t = ny.date(), ny.time()

            m15.push(ts, o, h, l, c)
            h1.push(ts, o, h, l, c)

            if t == at and d.weekday() < 5 and d not in snaps and prev_close is not None and last:
                snaps[d] = _snapshot(
                    d, ms, i, prev_close, ms5, m15, h1, last, sweeps, news, usd_at, covered
                )

            last["ms5"] = ms5.update(Bar(i, o, h, l, c))
            last["ob"] = obe.update(i, o, h, l, c)
            last["liq"] = liq.update(i, ms, h, l, c)
            last["vwap"] = vwe.update(i, ms, h, l, c, v)
            last["svp"] = svp.update(i, ms, o, h, l, c, v)
            last["fvg"] = fvg.update(i, o, h, l, c)
            last["rsi"] = rsi.update(i, h, l, c)
            last["eq"] = eqe.update(i, h, l, c)
            last["cs"] = cse.update(i, o, h, l, c)
            for lvl in last["liq"].mitigated:
                sweeps[d].append((t, lvl.side, lvl.name))

            by_day[d].append((t, o, h, l, c))
            prev_close = c

    return _with_outcomes(snaps, by_day, at)


def _nearest(prices, p, above: bool):
    xs = [x for x in prices if (x > p if above else x < p)]
    if not xs:
        return None
    return min(xs) if above else max(xs)


def _snapshot(d, ms, i, p, ms5, m15, h1, last, sweeps, news, usd_at, covered) -> dict:
    fv = last["fvg"].active
    obb, obs = last["ob"].active_bull, last["ob"].active_bear
    lv = [x for x in last["liq"].active if not x.mitigated]
    ne = news.update(i, ms)
    am = [(s, n) for (t, s, n) in sweeps[d] if T(3) <= t < T(10)]
    cs = last["cs"].detected
    hi_lv = [x for x in lv if x.side == "high"]
    lo_lv = [x for x in lv if x.side == "low"]
    near_hi = min((x for x in hi_lv if x.price > p), key=lambda x: x.price, default=None)
    near_lo = max((x for x in lo_lv if x.price < p), key=lambda x: x.price, default=None)
    return {
        "date": d.isoformat(),
        "dow": d.weekday(),
        "p_prev": p,
        "ms_m5": ms5.dir,
        "ms_m15": m15.engine.dir,
        "ms_h1": h1.engine.dir,
        "vwap": last["vwap"].value,
        "poc": last["svp"].poc,
        "fvg_n_bull": sum(1 for g in fv if g.is_bullish),
        "fvg_n_bear": sum(1 for g in fv if not g.is_bullish),
        "in_bull_fvg": any(g.is_bullish and g.bottom <= p <= g.top for g in fv),
        "in_bear_fvg": any((not g.is_bullish) and g.bottom <= p <= g.top for g in fv),
        "fvg_bull_below": _nearest([g.top for g in fv if g.is_bullish], p, above=False),
        "fvg_bear_above": _nearest([g.bottom for g in fv if not g.is_bullish], p, above=True),
        "ob_n_bull": len(obb),
        "ob_n_bear": len(obs),
        "in_bull_ob": any(b.bottom <= p <= b.top for b in obb),
        "in_bear_ob": any(b.bottom <= p <= b.top for b in obs),
        "ob_bull_below": _nearest([b.top for b in obb], p, above=False),
        "ob_bear_above": _nearest([b.bottom for b in obs], p, above=True),
        "eqh_above": _nearest(list(last["eq"].active_eqh), p, above=True),
        "eql_below": _nearest(list(last["eq"].active_eql), p, above=False),
        "liq_above": near_hi.price if near_hi else None,
        "liq_above_name": near_hi.name if near_hi else "",
        "liq_below": near_lo.price if near_lo else None,
        "liq_below_name": near_lo.name if near_lo else "",
        "am_swept_high": any(s == "high" for s, _ in am),
        "am_swept_low": any(s == "low" for s, _ in am),
        "am_swept_names": "|".join(sorted({n for _, n in am})),
        "rsi": last["rsi"].rsi,
        "rsi_bull_div": last["rsi"].bull_active,
        "rsi_bear_div": last["rsi"].bear_active,
        "cs_bull": any(x.spec.direction == BULLISH for x in cs),
        "cs_bear": any(x.spec.direction == BEARISH for x in cs),
        # Empty, never False, outside the calendar's fetched range.
        "news_covered": ne.has_coverage,
        "news_blackout": ne.in_blackout if ne.has_coverage else None,
        "usd_release_at": usd_at.get(d, 0) if ne.has_coverage else None,
    }


def _close_before(bars, t):
    xs = [b for b in bars if b[0] < t]
    return xs[-1][4] if xs else None


def _with_outcomes(snaps: dict, by_day: dict, at: dt.time) -> list[dict]:
    need = int(_MIN_DAY_COVERAGE * 14 * 12)
    hist, rows = [], []
    prev = None
    for d in sorted(by_day):
        bars = by_day[d]
        core = [b for b in bars if T(3) <= b[0] < T(17)]
        if d.weekday() >= 5 or len(core) < need:
            continue
        adr = statistics.fmean(hist[-20:]) if len(hist) >= 5 else None
        hist.append(max(b[2] for b in core) - min(b[3] for b in core))
        today = {
            "m_open": core[0][1],
            "day_close": _close_before(bars, T(16)),
            "day_hi": max(b[2] for b in core),
            "day_lo": min(b[3] for b in core),
        }
        snap = snaps.get(d)
        if adr and snap:
            z = [b for b in bars if at <= b[0] < T(11)]
            at_bar = next((b for b in bars if b[0] >= at), None)
            o08 = next((b[1] for b in bars if b[0] >= T(8)), None)
            if z and at_bar and o08 is not None:
                r = dict(snap)
                r.update(
                    adr=adr,
                    o_at=at_bar[1],
                    m_open=today["m_open"],
                    o08=o08,
                    z_hi=max(b[2] for b in z),
                    z_lo=min(b[3] for b in z),
                    pd_open=prev["m_open"] if prev else None,
                    pd_close=prev["day_close"] if prev else None,
                    pdh=prev["day_hi"] if prev else None,
                    pdl=prev["day_lo"] if prev else None,
                )
                for cp in CHECKPOINTS:
                    r[f"c_{cp:%H%M}"] = _close_before(bars, cp)
                rows.append(r)
        prev = today
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="M5")
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--at", default="10:00", help="NY snapshot time (default 10:00)")
    ap.add_argument("--out", default="backtest/reports/kz_features/features_1000.csv")
    args = ap.parse_args()

    at = dt.datetime.strptime(args.at, "%H:%M").time()
    rows = build(args.symbol, args.tf, args.server, at)
    out = _ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} days → {out}  ({rows[0]['date']} → {rows[-1]['date']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
