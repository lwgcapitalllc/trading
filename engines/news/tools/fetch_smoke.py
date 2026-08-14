#!/usr/bin/env python3
"""
fetch_smoke.py — manual sanity check against the LIVE Forex Factory feed.

Not a unit test (it hits the network, so it is not in CI). Run it by hand to confirm the feed is
reachable and the parser produces sane events, and to eyeball the upcoming high-impact USD prints
the engine would black out around:

    python engines/news/tools/fetch_smoke.py            # next high-impact USD events + coverage
    python engines/news/tools/fetch_smoke.py --all      # all currencies/impacts

Exit 0 = feed reached and parsed. This is the news engine's stand-in for the other engines' Pine
parity check: there is no Pine source, so "does it agree with the real calendar?" is verified live.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from news.engine import NewsEngine  # noqa: E402
from news.sources.forex_factory import ForexFactorySource  # noqa: E402
from news.types import Impact, NewsPolicy  # noqa: E402


def _fmt(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %a %H:%M UTC")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Live Forex Factory feed smoke test.")
    ap.add_argument("--all", action="store_true", help="show every event, not just high-impact USD")
    args = ap.parse_args(argv)

    src = ForexFactorySource()
    try:
        res = src.fetch()
    except Exception as exc:
        print(f"FEED UNREACHABLE: {exc}", file=sys.stderr)
        return 1

    if not res.events:
        print("Feed returned zero events.", file=sys.stderr)
        return 1

    lo = min(e.timestamp_ms for e in res.events)
    hi = max(e.timestamp_ms for e in res.events)
    print(f"Fetched {len(res.events)} events. Coverage {_fmt(lo)}  ->  {_fmt(hi)}\n")

    if args.all:
        shown = sorted(res.events, key=lambda e: e.timestamp_ms)
    else:
        pol = NewsPolicy.usd()
        shown = sorted((e for e in res.events if pol.matches(e)), key=lambda e: e.timestamp_ms)
        print("High-impact USD events (what NewsPolicy.usd() blacks out around):\n")

    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    for e in shown:
        when = "past" if e.timestamp_ms < now_ms else "up next"
        star = "*" if e.impact == Impact.HIGH else " "
        print(
            f"  {star} {_fmt(e.timestamp_ms)}  {e.currency:<4} {e.impact.name:<6} "
            f"{e.title}  (f:{e.forecast} p:{e.previous} a:{e.actual}) [{when}]"
        )

    # Prove the engine consumes it end to end at 'now'.
    eng = NewsEngine(res.events, policy=NewsPolicy.usd(), covered_ranges=res.covered_ranges)
    out = eng.update(0, now_ms)
    print(f"\nEngine @ now: in_blackout={out.in_blackout} has_coverage={out.has_coverage}")
    if out.next_event:
        print(f"  next: {out.next_event.title} in {out.minutes_to_next:.0f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
