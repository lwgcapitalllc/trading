#!/usr/bin/env python3
"""session_relay_scan.py — how often does the session-sweep relay playbook actually appear?

Aaron's playbook, read off a 2026-08-06/07 XAUUSD M15 chart (2026-08-08):

    A bullish BOS sets the trend up. Price then flips DOWN with a bearish SOS — a
    deviation, not a new trend. While that deviation runs, the sessions take each
    other's lows in a relay: London sweeps Asia's low, then NY sweeps London's low.
    Sell-side liquidity, at least two grabs, all in the direction OPPOSITE to where
    price ends up going. Then the next Asia session turns it and structure flips back
    up with a bullish SOS — the original up-trend resumes.

    The sweeps are the fuel, not the trend.

The short version is the mirror: bearish BOS, a bullish SOS deviation, session HIGHS
swept in the same relay, then a bearish SOS resumes the down-trend.

This tool COUNTS those occurrences. It does not trade them, size them or score them —
there is no entry, no stop and no R here, deliberately. "How many are there" is the
question being asked, and answering it with a P&L number would smuggle in a dozen
decisions nobody has made yet.

WHAT IT REPLAYS — nothing new, three canonical engines over one bar frame:

  engines/market_structure/  → the BOS / SOS stream (`bull_bos`, `bull_sos`, and mirrors)
  engines/liquidity/         → "Asia L", "London L", "NY H" … levels and the bar each is swept on
  engines/sessions/          → which session was ACTIVE on the sweep bar

The relay needs all three: liquidity says WHICH level was taken, sessions say WHO took
it. A sweep of Asia's low means nothing on its own — the playbook is that LONDON is the
one that takes it.

⚠ Session levels here are NON-REPAINTING by the engine's standing rule: "Asia L" is the
low of the last COMPLETED Asia session, never the developing one. That is what makes the
relay checkable in real time, and it is also why the windows are tight — Asia closes
0900 UTC and London runs to 1600 UTC, so today's Asia low has a 7-hour window in which
London can take it; London closes 1600 UTC and NY runs to 2100 UTC, a 5-hour window.

⚠ The sessions OVERLAP (London 0700-1600 UTC, NY 1200-2100 UTC), so a sweep between 1200
and 1600 is inside both. Each sweep is therefore recorded with BOTH flags rather than
being assigned one owner, and the strict filter asks only that the required session was
running — see `overlap_ambiguous` in the CSV for how often that matters.

ONE REPLAY, MANY FILTERS. The pass collects a rich candidate table — every structure
flip-flop inside the time budget, with every session sweep that happened inside it — and
the variants are filters over that table, not separate scans. So the strict relay and the
looser readings are all priced by the same run and are directly comparable.

  strict   London takes Asia's low, THEN NY takes London's low (the chart)
  relay    any session takes the previous session's low, then a later session takes that
           one's low — Asia->London->NY is one instance of it, London->NY->Asia another
  any2     any two sell-side session sweeps inside the deviation, no relay required

Usage:
    python3 backtest/tools/session_relay_scan.py
    python3 backtest/tools/session_relay_scan.py --budget-bars 480 --start 2020-01-01
    python3 backtest/tools/session_relay_scan.py --out backtest/reports/session_relay
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENGINES = _ROOT / "engines"
for _p in (str(_ROOT), str(_ENGINES)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from liquidity import LiquidityEngine  # noqa: E402
from market_structure import Bar, StructureEngine  # noqa: E402
from sessions import SessionEngine  # noqa: E402

CACHE = _ROOT / "backtest" / "cache"
UTC = dt.timezone.utc

# The three sessions, in the order the relay walks them on a normal day. "Asia" closes
# first (0900 UTC), then London (1600 UTC), then NY (2100 UTC).
SESSION_ORDER = ("Asia", "London", "NY")


# --------------------------------------------------------------------------------------
# Pass 1 — replay
# --------------------------------------------------------------------------------------


class Bars:
    """The bar frame plus the three engines' per-bar output, held once and re-filtered.

    Everything downstream is a query over these lists. Nothing here decides whether a
    pattern occurred — that is the matcher's job, and keeping the two apart is what lets
    the variants share one replay.
    """

    def __init__(self) -> None:
        self.time: list[dt.datetime] = []
        self.high: list[float] = []
        self.low: list[float] = []
        self.close: list[float] = []
        # Structure break events, as (bar_index, kind) with kind in
        # {"bull_bos", "bull_sos", "bear_bos", "bear_sos"}. NOTE an SOS bar raises its
        # plain BOS flag too (engine.py sets `bull_bos` then `bull_sos` on a CHoCH), so a
        # bullish SOS appears under BOTH kinds. That is deliberate: a bullish SOS
        # establishes an up-trend just as a plain bullish BOS does, so it is a valid
        # step 1, and `sos_is_step1` on the row records which kind actually opened it.
        self.breaks: list[tuple[int, str]] = []
        # One dict per session-level sweep — see `_sweep_row`.
        self.sweeps: list[dict] = []


def _fresh(sweep: dict, max_age_bars: int) -> bool:
    """Was the swept level made by THIS day's run of that session, not yesterday's?

    A session level lives until the same session closes again, so "London L" is still the
    most recent completed London low twenty hours later — correct by the engine's rules,
    and NOT the playbook. The chart takes today's Asia low with today's London and today's
    London low with today's NY; a twenty-hour-old level is a different setup wearing the
    same shape.

    MEASURED over the full history (2026-08-08): across every relayed leg the ages are
    355 at <=7h, TWO between 8h and 17h, and 87 at >=18h. The cutoff therefore sits in an
    empty band rather than on a slope — which is the only reason a single number is
    defensible here. The gap is structural: Asia closes 0900 UTC with London running to
    1600, and London closes 1600 with NY running to 2100, so a same-cycle sweep cannot be
    older than ~7h and yesterday's cannot be younger than ~18h.

    `max_age_bars <= 0` disables the gate (`--max-level-age-hrs 0`).
    """
    if max_age_bars <= 0:
        return True
    return sweep["index"] - sweep["created_index"] <= max_age_bars


def _sweep_row(index: int, stamp: dt.datetime, level, sess) -> dict:
    """One swept session level, tagged with who was trading when it went.

    `level.session_name` is the session the level BELONGS to; `in_*` is the session that
    was RUNNING when price took it. The playbook is a statement about the pair.
    """
    return {
        "index": index,
        "time": stamp,
        "level": level.name,  # "Asia L", "London H", …
        "owner": level.session_name,  # "Asia" | "London" | "NY"
        "side": level.side,  # "high" | "low"
        "created_index": level.created_index,
        "in_asia": sess.in_asia,
        "in_london": sess.in_london,
        "in_ny": sess.in_ny,
    }


def replay(symbol: str, tf: str, start: dt.date | None, end: dt.date | None) -> Bars:
    """Feed every cached bar through all three engines, in order, keeping the edges.

    Bars are fed CONTIGUOUSLY including weekends — every one of these engines is a
    streaming state machine whose periods are built from completed prior periods, so
    filtering the frame before the replay would silently corrupt the levels rather than
    fail loudly. The date window is applied to the RESULT, not to the input.
    """
    path = CACHE / f"{symbol}__{tf}.csv"
    if not path.exists():
        raise SystemExit(f"no cached bars at {path}")

    out = Bars()
    structure = StructureEngine()
    liq = LiquidityEngine()
    sess_eng = SessionEngine()

    with path.open(newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            stamp = dt.datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            o, h, l, c = (
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
            )
            ts_ms = int(stamp.timestamp() * 1000)

            ext = structure.update(Bar(index=i, open=o, high=h, low=l, close=c)).external
            sess = sess_eng.update(i, ts_ms, h, l)
            liq_ev = liq.update(i, ts_ms, h, l, c)

            out.time.append(stamp)
            out.high.append(h)
            out.low.append(l)
            out.close.append(c)

            for flag in ("bull_bos", "bull_sos", "bear_bos", "bear_sos"):
                if getattr(ext, flag):
                    out.breaks.append((i, flag))

            for lvl in liq_ev.mitigated:
                if lvl.kind == "session":
                    out.sweeps.append(_sweep_row(i, stamp, lvl, sess))

    if start or end:
        _trim(out, start, end)
    return out


def _trim(bars: Bars, start: dt.date | None, end: dt.date | None) -> None:
    """Drop EVENTS outside the reporting window. The bar arrays are left whole so an
    instance near the edge can still measure its own extremes."""

    def keep(stamp: dt.datetime) -> bool:
        d = stamp.date()
        return (start is None or d >= start) and (end is None or d <= end)

    bars.breaks = [(i, k) for i, k in bars.breaks if keep(bars.time[i])]
    bars.sweeps = [s for s in bars.sweeps if keep(s["time"])]


# --------------------------------------------------------------------------------------
# Pass 2 — candidates
# --------------------------------------------------------------------------------------


def candidates(bars: Bars, bullish: bool, budget_bars: int, max_age_bars: int = 0) -> list[dict]:
    """Every structure flip-flop that fits the time budget, with its sweeps attached.

    Bullish reading (the chart): a bullish break sets the trend, a BEARISH SOS deviates
    against it, and the first BULLISH SOS after that resumes it. Bearish is the mirror.

    A deviation is claimed by the FIRST resuming SOS after it, so two candidates can
    never share a resumption and nothing is counted twice.

    `max_age_bars` is the FRESHNESS gate and it is load-bearing — see `_fresh`. It is
    applied here, once, so every variant filter downstream reads the same sweep list and
    the three counts stay comparable.
    """
    step1 = "bull_bos" if bullish else "bear_bos"
    deviation = "bear_sos" if bullish else "bull_sos"
    resume = "bull_sos" if bullish else "bear_sos"

    opens = sorted(i for i, k in bars.breaks if k == step1)
    devs = sorted(i for i, k in bars.breaks if k == deviation)
    ends = sorted(i for i, k in bars.breaks if k == resume)
    sos_bars = {i for i, k in bars.breaks if k in ("bull_sos", "bear_sos")}

    # The sweep side the playbook wants: a bullish setup grabs sell-side liquidity
    # (session LOWS) on the way down; a bearish setup grabs buy-side (session HIGHS).
    want_side = "low" if bullish else "high"
    sweeps = [s for s in bars.sweeps if s["side"] == want_side and _fresh(s, max_age_bars)]

    rows: list[dict] = []
    for j in devs:
        k = next((x for x in ends if x > j), None)
        if k is None:
            continue
        i = max((x for x in opens if x < j), default=None)
        if i is None:
            continue
        if k - i > budget_bars:
            continue

        window = [s for s in sweeps if i < s["index"] <= k]
        rows.append(
            {
                "direction": "long" if bullish else "short",
                "open_index": i,
                "dev_index": j,
                "end_index": k,
                "open_time": bars.time[i],
                "dev_time": bars.time[j],
                "end_time": bars.time[k],
                "span_bars": k - i,
                "span_days": round((bars.time[k] - bars.time[i]).total_seconds() / 86400, 2),
                # Was step 1 itself a trend flip, or a plain continuation break? Kept because
                # the chart's step 1 is a plain BOS and we may want to require that later.
                "sos_is_step1": i in sos_bars,
                "sweeps": window,
            }
        )
    return rows


# --------------------------------------------------------------------------------------
# Pass 3 — the variant filters
# --------------------------------------------------------------------------------------


def _took(sweep: dict, session: str) -> bool:
    """Was `session` running when this level was swept?"""
    return bool(sweep[{"Asia": "in_asia", "London": "in_london", "NY": "in_ny"}[session]])


def strict_relay(row: dict) -> list[dict] | None:
    """London takes Asia's level, then NY takes London's. The chart, literally.

    Returns the two sweeps in order, or None. The ordering test is on the SWEEP bars, not
    on the levels' own sessions — a relay is a sequence of events in time.
    """
    for a in row["sweeps"]:
        if a["owner"] != "Asia" or not _took(a, "London"):
            continue
        for b in row["sweeps"]:
            if b["index"] <= a["index"]:
                continue
            if b["owner"] == "London" and _took(b, "NY"):
                return [a, b]
    return None


def any_relay(row: dict) -> list[dict] | None:
    """Any session takes another session's level, then a LATER session takes that one's.

    The relay shape without pinning the cast: Asia->London->NY qualifies, and so does
    London->NY->Asia across a day boundary. The link that makes it a relay is that the
    second sweep's OWNER is the first sweep's TAKER.
    """
    for a in row["sweeps"]:
        takers_a = [s for s in SESSION_ORDER if _took(a, s) and s != a["owner"]]
        if not takers_a:
            continue
        for b in row["sweeps"]:
            if b["index"] <= a["index"] or b["owner"] not in takers_a:
                continue
            if any(_took(b, s) and s != b["owner"] for s in SESSION_ORDER):
                return [a, b]
    return None


def any_two(row: dict) -> list[dict] | None:
    """Any two session-level sweeps on the right side inside the deviation. No relay."""
    if len(row["sweeps"]) >= 2:
        return row["sweeps"][:2]
    return None


VARIANTS = (
    ("strict", "London takes Asia, then NY takes London", strict_relay),
    ("relay", "any session-to-session relay, twice", any_relay),
    ("any2", "any two session sweeps, no relay", any_two),
)


# --------------------------------------------------------------------------------------
# Reversal origin + reporting
# --------------------------------------------------------------------------------------


def reversal_origin(bars: Bars, row: dict) -> tuple[str, dt.datetime]:
    """Which session was running at the deviation's extreme — the bar the reversal turned on.

    Recorded, never required (Aaron's call). If the Asia origin is what separates the good
    instances from the bad, this column is what will show it.
    """
    lo, hi = row["dev_index"], row["end_index"]
    series = bars.low if row["direction"] == "long" else bars.high
    pick = min if row["direction"] == "long" else max
    turn = pick(range(lo, hi + 1), key=lambda x: series[x])

    stamp = bars.time[turn]
    sess = SessionEngine()
    # The sessions engine is a pure clock for these three flags, so a one-bar probe is
    # exact — no warm-up, no carried state. (The NY opening range is stateful; unused here.)
    ev = sess.update(turn, int(stamp.timestamp() * 1000), bars.high[turn], bars.low[turn])
    live = [n for n, on in (("Asia", ev.in_asia), ("London", ev.in_london), ("NY", ev.in_ny)) if on]
    return ("+".join(live) if live else "none"), stamp


def report(bars: Bars, rows_by_dir: dict[str, list[dict]], out: Path | None, args) -> None:
    print()
    print("=" * 78)
    print("SESSION-SWEEP RELAY — how often the playbook appears")
    print("=" * 78)
    print(
        f"  {args.symbol} {args.tf}   bars replayed {len(bars.time):,}  "
        f"({bars.time[0]:%Y-%m-%d} -> {bars.time[-1]:%Y-%m-%d}, UTC)"
    )
    print(f"  structure breaks{len(bars.breaks):>8,}     session sweeps {len(bars.sweeps):>7,}")
    print(
        f"  budget {args.budget_bars} bars   swept level at most "
        f"{args.max_level_age_hrs:g}h old"
        f"{'  (freshness gate OFF)' if args.max_level_age_hrs <= 0 else ''}"
    )
    print(
        f"  candidates (structure flip-flops inside the budget):  "
        f"long {len(rows_by_dir['long'])}   short {len(rows_by_dir['short'])}"
    )

    for name, blurb, fn in VARIANTS:
        print()
        print(f"  {name.upper():<8} {blurb}")
        print(f"  {'':<10}{'instances':>10}{'per year':>10}   reversal turned in")
        for direction in ("long", "short"):
            hits = [r for r in rows_by_dir[direction] if fn(r)]
            years = (bars.time[-1] - bars.time[0]).days / 365.25
            origins = Counter(r["origin"] for r in hits)
            top = ", ".join(f"{k} {v}" for k, v in origins.most_common(3)) or "-"
            print(f"  {direction:<10}{len(hits):>10}{len(hits) / years:>10.1f}   {top}")

    if out:
        _write_csv(rows_by_dir, out)


def _write_csv(rows_by_dir: dict[str, list[dict]], out: Path) -> None:
    """One row per candidate, with a column per variant, so the instances can be pulled
    up on a chart and eyeballed. The candidate table is written WHOLE — including the
    rows every variant rejected — because the near-misses are what say whether a filter
    is doing real work or just narrowing."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = [
        "direction",
        "open_time",
        "dev_time",
        "end_time",
        "span_bars",
        "span_days",
        "sos_is_step1",
        "origin",
        "origin_time",
        "n_sweeps",
        "sweep_levels",
        "leg1_time",
        "leg1_age_hrs",
        "leg2_time",
        "leg2_age_hrs",
        "overlap_ambiguous",
    ] + [n for n, _, _ in VARIANTS]

    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for direction in ("long", "short"):
            for r in rows_by_dir[direction]:
                marks = {n: bool(fn(r)) for n, _, fn in VARIANTS}
                hit = strict_relay(r) or []
                # A sweep inside the London/NY overlap satisfies the strict rule while
                # being equally attributable to the other session. Flagged, not dropped —
                # the reader can see the two legs' own times and decide.
                ambiguous = bool(hit) and any(s["in_london"] and s["in_ny"] for s in hit)
                legs = {}
                for n, s in enumerate(hit, start=1):
                    legs[f"leg{n}_time"] = f"{s['time']:%Y-%m-%d %H:%M}"
                    legs[f"leg{n}_age_hrs"] = round(
                        (s["index"] - s["created_index"]) * 15 / 60.0, 1
                    )
                w.writerow(
                    {
                        "direction": r["direction"],
                        "open_time": f"{r['open_time']:%Y-%m-%d %H:%M}",
                        "dev_time": f"{r['dev_time']:%Y-%m-%d %H:%M}",
                        "end_time": f"{r['end_time']:%Y-%m-%d %H:%M}",
                        "span_bars": r["span_bars"],
                        "span_days": r["span_days"],
                        "sos_is_step1": r["sos_is_step1"],
                        "origin": r["origin"],
                        "origin_time": f"{r['origin_time']:%Y-%m-%d %H:%M}",
                        "n_sweeps": len(r["sweeps"]),
                        "sweep_levels": " > ".join(s["level"] for s in r["sweeps"]),
                        "overlap_ambiguous": ambiguous,
                        **legs,
                        **marks,
                    }
                )
    print(f"\n  wrote {out}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--symbol", default="XAUUSD")
    ap.add_argument("--tf", default="M15")
    ap.add_argument(
        "--budget-bars",
        type=int,
        default=288,
        help="max bars from the opening break to the resuming SOS "
        "(default 288 = 3 trading days of M15)",
    )
    ap.add_argument(
        "--max-level-age-hrs",
        type=float,
        default=8.0,
        help="a swept level must have been made this many hours ago at most, "
        "i.e. by TODAY's run of that session (default 8; 0 disables). "
        "See _fresh() — the 8-18h band is measured empty.",
    )
    ap.add_argument("--start", type=dt.date.fromisoformat, default=None)
    ap.add_argument("--end", type=dt.date.fromisoformat, default=None)
    ap.add_argument("--out", type=Path, default=None, help="write the candidate CSV here")
    args = ap.parse_args()

    bars = replay(args.symbol, args.tf, args.start, args.end)
    tf_minutes = {"M5": 5, "M15": 15, "M30": 30, "H1": 60}.get(args.tf)
    if tf_minutes is None:
        raise SystemExit(f"--tf {args.tf}: unknown bar size, cannot convert the age gate")
    max_age_bars = int(args.max_level_age_hrs * 60 / tf_minutes)

    rows_by_dir: dict[str, list[dict]] = {}
    for direction, bullish in (("long", True), ("short", False)):
        rows = candidates(bars, bullish, args.budget_bars, max_age_bars)
        for r in rows:
            r["origin"], r["origin_time"] = reversal_origin(bars, r)
        rows_by_dir[direction] = rows

    report(bars, rows_by_dir, args.out, args)


if __name__ == "__main__":
    main()
