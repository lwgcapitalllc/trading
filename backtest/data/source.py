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
from .cache import BarCache, UnknownBrokerError, _default_cache_dir, broker_cache_dir
from .coverage import RangeCoverage
from .history import HistoryFloors, assert_bar_spacing
from .mt5_agent import Mt5Agent, Mt5AgentError
from .resample import resample_up
from .timeframes import resolve_base_tf, to_minutes


class BarSource:
    """Bars for one broker's terminal, cached under that broker's own folder.

    🔴 **The cache is partitioned by the attached terminal's SERVER**, resolved from the
    agent on first use. Before 2026-08-24 it was one flat folder keyed on (symbol, timeframe), so
    switching the lab to a second broker would have served the first one's bars without a word —
    and the run would have charged the second one's spread and commission over them. Nothing in
    the output could show you that: the frame is clean, the curve is complete, and the two feeds
    here differ by a systematic 4-5 cents a bar.

    ⚠ **An explicitly injected `cache` is HONOURED and not partitioned.** That is what every test
    passes, and it is a deliberate statement about where these bars live. Production constructs
    `BarSource()` bare — checked across all 20 call sites — so production always partitions.

    ⚠ **Partitioning is LAZY, on the first `load()`.** Construction stayed free of network calls
    on purpose: `HistoryFloors` already resolved its server that way, and a tool that dies while
    building an object reports the failure in the wrong place.
    """

    def __init__(self, agent: Mt5Agent | None = None, cache: BarCache | None = None):
        self.agent = agent if agent is not None else Mt5Agent()
        self._pinned_cache = cache
        self._cache: BarCache | None = None
        self._coverage: RangeCoverage | None = None
        self._floors: HistoryFloors | None = None

    def _partition(self) -> None:
        """Bind the cache, coverage and floors to this terminal's broker. Idempotent."""
        if self._cache is not None:
            return
        if self._pinned_cache is not None:
            cache = self._pinned_cache
        else:
            # ⚠ Read through `HistoryFloors.server()`-style handling: an agent that cannot be
            # reached returns no server, and `broker_cache_dir` REFUSES on an empty one rather
            # than letting "cannot ask" and "the default broker" be the same folder. That is
            # rule 1 applied to a filesystem path.
            try:
                server = str(self.agent.status().get("server") or "")
            except Mt5AgentError as exc:
                raise UnknownBrokerError(
                    "cannot file bars without knowing which broker served them — the MT5 agent "
                    f"is unreachable ({exc}). A backtest must never replay one broker's bars "
                    "while charging another's costs."
                ) from exc
            cache = BarCache(broker_cache_dir(_default_cache_dir(), server))
        self._cache = cache
        self._coverage = RangeCoverage(cache.dir)
        # Built from OUR agent, not the module-level shared one, so an injected fake in a
        # test probes the fake — a floor check that reached the real terminal from a unit
        # test would be both slow and non-deterministic.
        self._floors = HistoryFloors(agent=self.agent, cache_dir=cache.dir)

    @property
    def cache(self) -> BarCache:
        self._partition()
        assert self._cache is not None
        return self._cache

    @property
    def coverage(self) -> RangeCoverage:
        self._partition()
        assert self._coverage is not None
        return self._coverage

    @property
    def floors(self) -> HistoryFloors:
        self._partition()
        assert self._floors is not None
        return self._floors

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
            try:
                fetched = self.agent.bars(symbol, base_tf, gap_start, gap_end)
            except Mt5AgentError:
                # THE WHOLE GAP SERVED NOTHING. That has two causes and they need opposite
                # responses: the market was SHUT over it (a weekend, a holiday, or a window
                # ending today before the session opens), or the data is MISSING (the 45-day
                # M1 hole `covered_spans` records). Raising on both made every run whose end
                # date fell on a Saturday fail — which is how this was found — and swallowing
                # both would hide the hole. `_market_was_shut` is the one thing that can tell
                # them apart, and it refuses to guess.
                if self._market_was_shut(symbol, base_tf, gap_start, gap_end):
                    # Deliberately record NO coverage. The span carries no bars, so there is
                    # nothing to describe, and `covered_spans` already joins across closures
                    # up to `_MAX_CLOSURE_DAYS` — so the next fetch that DOES serve bars
                    # absorbs this weekend into its span and the probe stops happening.
                    continue
                raise
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

    def _market_was_shut(self, symbol: str, base_tf: str, gap_start: str, gap_end: str) -> bool:
        """Did this gap serve nothing because the MARKET was shut, rather than because the data
        is missing? Only `True` when that can be shown; `False` whenever it cannot.

        🔴 **The whole point is that an empty answer means two opposite things and the caller
        must not guess.** A backtest ending on a Saturday, a Sunday, a holiday, or on today
        before the session opens asks for a window that legitimately holds no bars — and until
        2026-08-15 every one of those failed the entire run with "MT5 agent returned no bars".
        A gap in the MIDDLE of history that serves nothing is the opposite case: 45 days of M1
        went missing that way, and swallowing it would make the hole permanent.

        Two conditions, and BOTH are required:

        1. **The gap is no longer than `_MAX_CLOSURE_DAYS`.** That constant is already this
           module's measured answer to "how long can this market legitimately print no bars"
           — 2 days observed over 186,366 bars, 4 with headroom. A longer stretch is missing
           data BY THE DEFINITION ALREADY IN USE HERE, so it can never be called a closure and
           the 45-day hole stays loud.
        2. **A WIDER window around the gap does serve bars.** This is the half that makes the
           answer worth anything: it proves the agent is up, the terminal is connected, the
           symbol resolves, and history exists right there — so the only thing absent is the
           market itself. ⚠ **The probe must be longer than any closure it is being used to
           excuse, or it answers the same "no bars" for both cases and is not a probe at all**
           — this repo's own rule about a negative a healthy system can also produce. It is
           `_MAX_CLOSURE_DAYS` either side, so the shortest probe is 9 days against a longest
           measured closure of 2.

        ⚠ **The probe is clamped at today.** Asking past it is asking for bars nothing can have
        yet, which is the very failure this function exists to stop — from inside itself.

        ⚠ **A probe that RAISES answers `False`.** An unreachable agent cannot license skipping
        anything, and the caller re-raises the original error, which is the accurate one.

        ⚠ **The probe's bars are deliberately DISCARDED.** Every bar it returns lies outside the
        gap (the gap served nothing), so they are either already cached or outside the window
        that was asked for; saving them would record coverage for a span nobody requested.
        """
        import datetime as _dt

        if _days_between(gap_start, gap_end) > _MAX_CLOSURE_DAYS:
            return False
        today = _dt.date.today()
        # 🔴 The BACKWARD reach carries the whole probe, and it is not symmetric with the
        # forward one for a measured reason: the forward side is clamped at today, and the
        # gap that matters most IS today (a run ending on a Saturday). Reaching
        # `_MAX_CLOSURE_DAYS` each way collapsed to a 4-day window there — exactly the
        # length of the closure it was being asked to excuse, so it answered "no bars" for
        # both causes and was not a probe at all. Caught by the test that asserts the span,
        # against the fix, not against HEAD.
        lo = _dt.date.fromisoformat(gap_start) - _dt.timedelta(days=_PROBE_DAYS)
        hi = min(
            _dt.date.fromisoformat(gap_end) + _dt.timedelta(days=_MAX_CLOSURE_DAYS),
            today,
        )
        if hi <= lo:
            return False
        try:
            probe = self.agent.bars(symbol, base_tf, str(lo), str(hi))
        except Mt5AgentError:
            return False
        return not probe.empty


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

# How far BACK `_market_was_shut` reaches to prove the feed is alive. Derived from the
# constant above rather than chosen: it must stay longer than the longest span that may be
# called a closure even after the forward half is clamped at today, or the probe returns
# the same empty answer for "market shut" and "data missing" and decides nothing.
_PROBE_DAYS = _MAX_CLOSURE_DAYS * 2 + 1


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
