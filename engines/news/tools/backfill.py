#!/usr/bin/env python3
"""
backfill.py — fetch historical calendar months from the FF website into the local cache.

Cache-aware: historical months are static, so a month already in the store is skipped — only the
missing months (and always the current month, whose `actual` values are still filling in) are
fetched. So the first backfill over a long range does the work once; every later run is fast.

    python engines/news/tools/backfill.py --from 2024-01              # 2024-01 .. today
    python engines/news/tools/backfill.py --from 2025-02 --to 2025-06
    python engines/news/tools/backfill.py --from 2024-01 --force      # re-fetch even cached months

Needs curl_cffi (Cloudflare bypass): `pip install curl_cffi`. Writes to engines/news/data/events.json.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from news.sources.forex_factory_history import (  # noqa: E402
    ForexFactoryHistorySource, _month_bounds_ms, _months_between,
)
from news.store import EventStore  # noqa: E402


def _parse_month(s: str) -> int:
    """'YYYY-MM' or 'YYYY-MM-DD' -> epoch ms at that day/month start (UTC)."""
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            dt = datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f"bad date {s!r}; use YYYY-MM or YYYY-MM-DD")


def _range_covered(ranges, lo, hi) -> bool:
    """True if some single merged coverage interval fully contains [lo, hi]."""
    return any(rlo <= lo and rhi >= hi for rlo, rhi in ranges)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Backfill historical FF calendar months into the cache.")
    ap.add_argument("--from", dest="start", required=True, type=_parse_month, help="YYYY-MM[-DD]")
    ap.add_argument("--to", dest="end", type=_parse_month, default=None, help="YYYY-MM[-DD] (default: today)")
    ap.add_argument("--force", action="store_true", help="re-fetch months even if already cached")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between month requests")
    args = ap.parse_args(argv)

    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    end_ms = args.end if args.end is not None else now_ms

    store = EventStore()
    _, covered = store.load()
    src = ForexFactoryHistorySource(sleep_s=args.sleep)

    fetched = skipped = added_total = 0
    for year, month in _months_between(args.start, end_ms):
        mstart, mend = _month_bounds_ms(year, month)
        immutable = mend < now_ms  # a fully-past month never changes
        if not args.force and immutable and _range_covered(covered, mstart, mend):
            skipped += 1
            continue
        try:
            res = src.fetch_month(year, month)
        except Exception as exc:
            print(f"[backfill] {year}-{month:02d} FAILED: {exc}", file=sys.stderr)
            return 1
        total, changed = store.upsert_result(res)
        _, covered = store.load()  # refresh coverage for subsequent iterations
        fetched += 1
        added_total += changed
        print(f"[backfill] {year}-{month:02d}: {len(res.events)} events ({changed} new/updated)")

    start = store.coverage_start_ms()
    startstr = datetime.fromtimestamp(start / 1000, tz=timezone.utc).strftime("%Y-%m-%d") if start else "n/a"
    print(f"[backfill] done: {fetched} month(s) fetched, {skipped} cached/skipped, "
          f"{added_total} events new/updated. Cache now starts {startstr} -> {store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
