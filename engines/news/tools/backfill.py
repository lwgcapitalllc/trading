#!/usr/bin/env python3
"""
backfill.py — fetch historical calendar months from the FF website into the local cache.

Cache-aware: historical months are static, so a month already in the store is skipped — only the
missing months (and always the current month, whose `actual` values are still filling in) are
fetched. So the first backfill over a long range does the work once; every later run is fast.

    python engines/news/tools/backfill.py --from 2024-01              # 2024-01 .. today
    python engines/news/tools/backfill.py --from 2025-02 --to 2025-06
    python engines/news/tools/backfill.py --from 2024-01 --force      # re-fetch even cached months
    python engines/news/tools/backfill.py --top-up                    # from where the cache ends .. today
    python engines/news/tools/backfill.py --top-up --if-stale         # ...and do nothing if it is current

`--top-up` is the one you schedule. It reads its own start date off the cache's coverage end, so
nothing has to remember when the cache was last filled, and it REFUSES on an empty cache rather
than picking a year to begin at — a default start date is a hardcode with better manners, and it
fails quietly in the direction nobody checks. It always re-fetches the CURRENT month too, because
that month is still filling in its `actual` values — `--if-stale` is the way to say "only when
coverage has actually fallen behind", and it decides that without touching the network, so a
launcher can call it on every run for nothing.

Needs curl_cffi (Cloudflare bypass): `pip install curl_cffi`. Writes to engines/news/data/events.json.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from news.sources.forex_factory_history import (  # noqa: E402
    ForexFactoryHistorySource,
    _month_bounds_ms,
    _months_between,
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


def _coverage_is_current(store: EventStore, now_ms: int) -> bool:
    """True when the cache's coverage already runs up to now — so there is nothing to fetch.

    Answered from the cache alone, never from the network, so a launcher can ask on every run.
    An empty cache is NOT current: there is everything to fetch, and the caller refuses there
    rather than inventing a start date.
    """
    end = store.coverage_end_ms()
    return end is not None and end >= now_ms


def _fmt_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _top_up_start_ms(store: EventStore, now_ms: int) -> int | None:
    """Where a top-up resumes: the start of the month the cache's coverage ends in.

    Never later than the CURRENT month, so the month still publishing its `actual` values is
    re-fetched on every run even when the cache already reaches past today. Returns None on an
    empty cache — the caller refuses there; it does not invent a start date.
    """
    end = store.coverage_end_ms()
    if end is None:
        return None
    edge = min(end, now_ms)
    dt = datetime.fromtimestamp(edge / 1000, tz=timezone.utc)
    return int(datetime(dt.year, dt.month, 1, tzinfo=timezone.utc).timestamp() * 1000)


def _range_covered(ranges, lo, hi) -> bool:
    """True if some single merged coverage interval fully contains [lo, hi]."""
    return any(rlo <= lo and rhi >= hi for rlo, rhi in ranges)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Backfill historical FF calendar months into the cache."
    )
    ap.add_argument("--from", dest="start", type=_parse_month, help="YYYY-MM[-DD]")
    ap.add_argument(
        "--to", dest="end", type=_parse_month, default=None, help="YYYY-MM[-DD] (default: today)"
    )
    ap.add_argument(
        "--top-up",
        dest="top_up",
        action="store_true",
        help="start from where the cache's coverage ends (refuses if the cache is empty)",
    )
    ap.add_argument(
        "--if-stale",
        dest="if_stale",
        action="store_true",
        help="with --top-up: do nothing (no network) while coverage already reaches now",
    )
    ap.add_argument("--force", action="store_true", help="re-fetch months even if already cached")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between month requests")
    args = ap.parse_args(argv)

    if bool(args.top_up) == (args.start is not None):
        ap.error("give exactly one of --from or --top-up")
    if args.if_stale and not args.top_up:
        ap.error("--if-stale only means anything with --top-up")

    now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    end_ms = args.end if args.end is not None else now_ms

    store = EventStore()
    _, covered = store.load()

    if args.top_up:
        start_ms = _top_up_start_ms(store, now_ms)
        if start_ms is None:
            print(
                "[backfill] the calendar cache is EMPTY — a top-up has nowhere to resume from, "
                "and this tool will not guess a start date. Fill it first, e.g. "
                "`backfill.py --from 2021-01`.",
                file=sys.stderr,
            )
            return 1
        args.start = start_ms
        if args.if_stale and _coverage_is_current(store, now_ms):
            end = store.coverage_end_ms()
            print(f"[backfill] coverage already reaches {_fmt_day(end)} — nothing to fetch")
            return 0
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
    startstr = (
        datetime.fromtimestamp(start / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        if start
        else "n/a"
    )
    print(
        f"[backfill] done: {fetched} month(s) fetched, {skipped} cached/skipped, "
        f"{added_total} events new/updated. Cache now starts {startstr} -> {store.path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
