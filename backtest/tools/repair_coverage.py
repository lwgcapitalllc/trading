"""Re-derive a cache's `ranges.json` from the bars actually on disk.

🔴 **Why this exists.** `RangeCoverage` is a record of what we fetched, and a range it claims is
NEVER re-fetched. So the one thing that must always be true is *coverage never claims more than the
bars on disk* — and on 2026-08-07 it did: `XAUUSD__M1.ranges.json` claimed 2018-09-14 → 2026-08-06
while the CSV held **nothing between 2026-06-22 and 2026-08-05**, 45 days and ~62,000 bars, with the
broker serving them on request the whole time. Because the range was claimed, nothing would ever ask
for them again; and because the M1 drill-down reads the same cache, the price chart drew the hole's
edge as *"No earlier M1 data — all the broker still has"*.

`source.covered_spans` closes the way that lie gets WRITTEN. It cannot un-write one already on disk,
which is what this is for: it reads the cached bars, recomputes the spans they support (the same
function, so there is one definition of what coverage means), and rewrites the sidecar. Days that
turn out to be missing become gaps again, and the next load re-fetches them normally.

⚠ **It only ever SHRINKS coverage, and a shrink is never destructive here** — the bars stay, and
the worst case is a range being fetched a second time. Growing it would be inventing a fetch.

⚠ **A weekend is not a hole.** The join tolerance is `source._MAX_CLOSURE_DAYS`, measured against
this repo's own cached history; see the note there before changing it.

    python -m backtest.tools.repair_coverage --check              # report only, touch nothing
    python -m backtest.tools.repair_coverage --symbol XAUUSD      # rewrite the sidecars
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest.data.atomic import atomic_write_json, cache_lock  # noqa: E402
from backtest.data.cache import BarCache  # noqa: E402
from backtest.data.coverage import RangeCoverage, _merge_intervals  # noqa: E402
from backtest.data.source import covered_spans  # noqa: E402


def _pairs(cache: BarCache) -> list[tuple[str, str]]:
    out = []
    for csv in sorted(cache.dir.glob("*__*.csv")):
        symbol, _, tf = csv.stem.partition("__")
        out.append((symbol, tf))
    return out


def repair(cache_dir: str | None, only_symbol: str | None, check: bool) -> int:
    cache = BarCache(cache_dir) if cache_dir else BarCache()
    coverage = RangeCoverage(cache.dir)
    shrunk = 0

    for symbol, tf in _pairs(cache):
        if only_symbol and symbol != only_symbol:
            continue
        try:
            bars = cache.load(symbol, tf)
        except Exception as exc:  # noqa: BLE001 — a stale/unreadable file is not this tool's job
            print(f"{symbol} {tf}: SKIPPED — {type(exc).__name__}: {exc}")
            continue
        if bars.empty:
            continue

        claimed = _merge_intervals(coverage._load(symbol, tf))
        first = str(bars.index[0].date())
        last = str(bars.index[-1].date())
        real = _merge_intervals([list(s) for s in covered_spans(bars, first, last)])
        if real == claimed:
            print(f"{symbol} {tf}: ok ({len(claimed)} span(s))")
            continue

        shrunk += 1
        print(f"{symbol} {tf}: CLAIMED {claimed}")
        print(f"{symbol} {tf}: HELD    {real}")
        missing = _missing_days(claimed, real)
        print(f"{symbol} {tf}: {missing} day(s) claimed but not held")
        if not check:
            with cache_lock(cache.dir, symbol, tf):
                atomic_write_json(coverage.path(symbol, tf), real)
            print(f"{symbol} {tf}: rewritten — those days will re-fetch on next load")

    print(f"\n{shrunk} sidecar(s) {'would be' if check else ''} corrected")
    return shrunk


def _missing_days(claimed: list[list[str]], real: list[list[str]]) -> int:
    from datetime import date, timedelta

    def days(spans):
        out = set()
        for lo, hi in spans:
            d, end = date.fromisoformat(lo), date.fromisoformat(hi)
            while d <= end:
                out.add(d)
                d += timedelta(days=1)
        return out

    return len(days(claimed) - days(real))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--symbol", default=None, help="limit to one symbol")
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    args = ap.parse_args()
    repair(args.cache_dir, args.symbol, args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
