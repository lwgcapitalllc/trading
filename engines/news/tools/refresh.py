#!/usr/bin/env python3
"""
refresh.py — pull the calendar feed and accumulate it into the local store.

This is the live data pipeline: run it on a schedule (a VPS task / cron) so the store always holds
the current week (for live blackout gating) AND grows a historical record forward over time (for
backtests). Each run fetches the source and upserts — de-duping events and filling in `actual` once
releases publish.

    python engines/news/tools/refresh.py

The engine itself never calls this; it consumes the store's output. Keeping fetch (impure, network)
out of the engine (pure) is what makes the engine deterministic and backtestable.

NOTE: lives in tools/ (not the package root) on purpose — a script run from inside the package dir
would put engines/news/ on sys.path[0] and shadow the stdlib `types` module with news/types.py.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

# Make `news` importable: add engines/ (three levels up from this file) to the path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from news.sources.forex_factory import ForexFactorySource  # noqa: E402
from news.store import EventStore  # noqa: E402


def _fmt(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def main(argv=None) -> int:
    source = ForexFactorySource()
    try:
        result = source.fetch()
    except Exception as exc:  # network/parse — report, don't crash a scheduler loudly
        print(f"[news.refresh] fetch failed: {exc}", file=sys.stderr)
        return 1

    store = EventStore()
    total, changed = store.upsert_result(result)
    start = store.coverage_start_ms()

    print(
        f"[news.refresh] fetched {len(result.events)} events; "
        f"store now {total} ({changed} new/updated)"
    )
    if start is not None:
        print(f"[news.refresh] coverage starts {_fmt(start)}  ->  {store.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
