"""BarSource — the one entry point the replay loop calls for bars.

load(symbol, timeframe, start, end):
    1. Resolve the base timeframe to pull (the target itself if the broker serves
       it, else the largest served divisor).
    2. Serve base bars cache-first; on a miss fetch the whole [start, end] from
       the MT5 agent, cache it, and record the fetched range.
    3. Resample up to the target timeframe if base != target.
    4. Slice to [start, end] and return.

The agent is injected, so tests run against a fake with no network. In the lab
the default agent hits localhost:8766 through the SSH tunnel.
"""

from __future__ import annotations

import pandas as pd

from .atomic import cache_lock
from .cache import BarCache
from .coverage import RangeCoverage
from .history import HistoryFloors, assert_bar_spacing
from .mt5_agent import Mt5Agent
from .resample import resample_up
from .timeframes import resolve_base_tf, to_minutes


class BarSource:
    def __init__(self, agent: Mt5Agent | None = None, cache: BarCache | None = None):
        self.agent = agent if agent is not None else Mt5Agent()
        self.cache = cache if cache is not None else BarCache()
        self.coverage = RangeCoverage(self.cache.dir)
        # Built from OUR agent, not the module-level shared one, so an injected fake in a
        # test probes the fake — a floor check that reached the real terminal from a unit
        # test would be both slow and non-deterministic.
        self.floors = HistoryFloors(agent=self.agent, cache_dir=self.cache.dir)

    def load(
        self, symbol: str, timeframe: str | int, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Return canonical OHLC bars for the target timeframe over
        [start_date, end_date] inclusive (dates as YYYY-MM-DD).

        Raises `history.HistoryFloorError` when the window starts before the broker's
        real history for this timeframe, or when the bars that came back are not the
        timeframe requested. **Both checks live here, not in the callers** — MT5 answers
        a too-early request with COARSER bars mislabelled as what you asked for, and a
        backtest fed those produces a clean, confident, fictional result. Every consumer
        (the lab, the optimizer, the CLI tools) reads bars through this method, so this
        is the one place that can protect all of them. The floor is MEASURED per broker,
        never hardcoded — see `history.py` for the evidence and the probe.
        """
        target_min = to_minutes(timeframe)
        self.floors.assert_window(symbol, target_min, start_date, end_date)
        base_tf, base_min = resolve_base_tf(target_min)

        base_bars = self._load_base(symbol, base_tf, start_date, end_date)
        # Checked at the BASE timeframe — that is what the broker actually served, and
        # resampling up would smooth a substitution into a plausible-looking frame.
        assert_bar_spacing(base_bars, base_min, symbol)
        if base_min == target_min:
            bars = base_bars
        else:
            bars = resample_up(base_bars, target_min, base_min)
        return _slice(bars, start_date, end_date)

    def _load_base(self, symbol: str, base_tf: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Cache-first base-bar load. Fetches only the sub-ranges of [start, end] that are not
        already recorded as fetched, merges them into the cache, and returns the whole file.

        A stale FEED_VERSION forces a refetch and DROPS the recorded coverage. Both halves are
        required: `cache.load` already refuses to read a stale file, so honouring the old coverage
        would return an empty frame forever instead of re-pulling — the coverage says "we have
        this" while the cache says "not in a form you can use", and the caller gets nothing.

        🔴 **This asked `covered()` and refetched the WHOLE window on False until 2026-08-06,
        and that turned the deliberate never-mark-today rule into a 72x tax.** `covered_spans`
        will not mark today as covered, on purpose — a day still filling looks exactly like a
        complete one — so a window ending today is *never* fully covered, and every single
        request re-pulled the entire history to obtain the one missing day. **Measured on the
        live cache: 27.8s for 2020-01-01 → today against 0.39s for the same span ending
        yesterday, on every chart open, backtest and sweep reaching the live edge.**

        Asking for the GAPS keeps the rule and drops the tax. Note the two are not alternatives:
        the clamp is what keeps the recent edge honest, and this is what makes honouring it cheap.
        """
        if self.cache.is_stale(symbol, base_tf):
            self.coverage.reset(symbol, base_tf)
        for gap_start, gap_end in self.coverage.missing(symbol, base_tf, start_date, end_date):
            fetched = self.agent.bars(symbol, base_tf, gap_start, gap_end)
            # The bars and the coverage that DESCRIBES them are written as ONE operation. The
            # invariant that matters is not "each file is well-formed" but *coverage never claims
            # more than the bars on disk* — and a save and a record that are individually atomic
            # still leave a window between them where exactly that lie is true. Anything that
            # crashes or interleaves in that window strands missing bars behind a cache HIT,
            # permanently, because a covered range is never re-fetched.
            #
            # The lock is taken here rather than around the whole loop on purpose: the FETCH is
            # the slow part and holding a lock across it would serialise two backtests for
            # minutes. Two processes fetching the same range concurrently is merely wasteful —
            # `save` MERGES, so both results survive.
            with cache_lock(self.cache.dir, symbol, base_tf):
                # MERGES, never overwrites (`BarCache.save`) — which is what makes a partial fetch
                # safe. Overwriting would let a one-day tail pull delete six years of cached bars.
                self.cache.save(symbol, base_tf, fetched)
                # Record what CAME BACK, never what was asked for — see `covered_spans`.
                for span_start, span_end in covered_spans(fetched, gap_start, gap_end):
                    self.coverage.record(symbol, base_tf, span_start, span_end)
        return self.cache.load(symbol, base_tf)


# The longest stretch of consecutive days on which this market legitimately prints NO bars.
# MEASURED rather than chosen: over the whole cached XAUUSD history (2018-09-14 → 2026-08-06,
# 186,366 M15 bars and the same span at H1) the longest no-bar run is **2 days** — a weekend, or
# Good Friday plus its weekend (2026-04-02 → 2026-04-05, 2020-04-09 → 2020-04-12). 4 is that
# measurement plus headroom for a holiday landing beside a weekend on some other instrument.
#
# It is the one number separating *the market was shut* from *the fetch did not deliver*, and it
# only has to be good enough to tell 2 days from the 45-day hole that prompted it. Widening it
# past a week would start swallowing real losses; tightening it below 3 would make every Easter
# refetch for ever.
_MAX_CLOSURE_DAYS = 4


def covered_spans(fetched: pd.DataFrame, gap_start: str, gap_end: str) -> list[tuple[str, str]]:
    """The date ranges this fetch may honestly claim to have covered — DESCRIBING the bars that
    came back, never the window that was asked for.

    🔴 **The predecessor, `_covered_end`, answered with one END date and therefore always claimed
    from `gap_start`, whatever arrived — so a PARTIAL serve was recorded as a complete one.** Its
    single clamp is *never past the last bar returned*, and there was no mirror for the first, so a
    request for 45 days that came back with one day's bars was written down as 45 days fetched. A
    fetch with a HOLE in it is the same defect one step in: bars either side, nothing between, one
    span claimed straight across.

    ⚠ **`Mt5Agent.bars` produces exactly those shapes on its own** — it CHUNKS a long window (M1
    past ~60,000 bars needs several) and stitches the results, and an empty chunk beside a served
    one is deliberately not an error. So a partial serve needs no bug anywhere else; it is the
    documented behaviour of a request that half-succeeded.

    ⚠ **A WHOLLY empty fetch returns `[]` here as defence in depth, not as the observed cause** —
    today it never reaches this function, because `BarCache.save` raises on a frame with no columns
    and the whole load fails loudly first. That is the right outcome and it is also incidental;
    coverage should not depend on a different module crashing to stay honest.

    ✅ **MEASURED on the live cache 2026-08-07, which is what found this:** `XAUUSD__M1.ranges.json`
    claimed `2018-09-14 → 2026-08-06` while the CSV held **nothing at all between 2026-06-22 and
    2026-08-05** — 45 days, ~62,000 bars, gone. The broker was serving them the whole time (asked
    directly for 2026-07-15 → 2026-07-17 it returned 4,013 bars). Because a covered range is never
    re-fetched, that hole was permanent, and because the M1 drill-down reads the same cache, the
    price chart reported the hole's edge as *"No earlier M1 data — all the broker still has"*.

    So coverage is now a description of what is on disk: the days that actually carry bars, joined
    across stretches no longer than `_MAX_CLOSURE_DAYS` (a weekend or a holiday genuinely has no
    bars and must not split a span, or every Easter would refetch for ever). A stretch longer than
    that is not a closure — it is missing data, and it stays missing so the next load re-fetches it.

    The `gap_start` edge is extended back to the request only when the first bar is within that
    same tolerance, which is what keeps a window opening on a Saturday from re-fetching its weekend
    on every single load.

    ⚠ **The end keeps BOTH of the clamps it already had**, and the second is the one that is easy
    to miss: never past the last bar returned, and **never into today** — a day still filling looks
    identical to a complete one from the bars alone, so the live edge is never marked covered and
    simply refetches until it is genuinely in the past.
    """
    import datetime as _dt

    if fetched.empty:
        # Nothing came back, so nothing was covered. This is the branch that lost 45 days of M1.
        return []

    days = sorted({str(pd.Timestamp(t).date()) for t in fetched.index})
    spans: list[list[str]] = [[days[0], days[0]]]
    for day in days[1:]:
        if _days_between(spans[-1][1], day) <= _MAX_CLOSURE_DAYS:
            spans[-1][1] = day
        else:
            spans.append([day, day])

    # Only the FIRST span may reach back to the request, and only over a plausible closure.
    if _days_between(gap_start, spans[0][0]) <= _MAX_CLOSURE_DAYS and gap_start < spans[0][0]:
        spans[0][0] = gap_start

    yesterday = str(_dt.date.today() - _dt.timedelta(days=1))
    out: list[tuple[str, str]] = []
    for lo, hi in spans:
        hi = min(hi, gap_end, yesterday)
        if lo <= hi:
            out.append((lo, hi))
    return out


def _days_between(earlier: str, later: str) -> int:
    import datetime as _dt

    return (_dt.date.fromisoformat(later) - _dt.date.fromisoformat(earlier)).days


def _slice(bars: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    """Inclusive [start_date, end_date] slice (end_date's whole day included)."""
    if bars.empty:
        return bars
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    return bars.loc[(bars.index >= start) & (bars.index < end)]
