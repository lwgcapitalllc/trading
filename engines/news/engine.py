"""
news/engine.py — the economic-calendar (news) engine: a pure, deterministic, streaming state
machine. One closed bar's UTC timestamp in → the per-bar NewsEvents out (blackout gate, coverage,
next/active/last phases, edges).

This is the same *shape* as engines/sessions/ — time-driven (input = the bar's epoch-ms UTC
timestamp, not price), one closed bar per update(), state carried bar-to-bar. It is NOT a Pine port
(the calendar comes from an external API, not mpc_assistant.pine), so it is validated by unit tests
+ a live feed smoke test, not by Pine parity. That is the one deliberate break from the roadmap's
engine pattern.

Separation of concerns (why this class takes events, not a URL):
  * This core is pure — no network, no clock, no files — so it is deterministic and testable, and a
    backtest can feed it a historical event list exactly as live trading feeds it a fetched one.
  * sources/ fetches + normalises the calendar; store.py accumulates it across fetches; refresh.py
    wires them. The engine only consumes the resulting NewsEvent list (+ the date ranges that list
    covers) and a bot-owned NewsPolicy.

The policy (currencies, min impact, pre/post minutes) is applied once at construction: relevant
events are filtered out and their [event - pre, event + post] windows merged into a blackout
interval list; coverage is a second interval list (the date ranges actually fetched). Per bar we
just answer "is this timestamp in a covered range?" and "…in a blackout window?" by bisection.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional, Sequence, Tuple

from .types import NewsEvent, NewsEvents, NewsPolicy

_MS_PER_MIN = 60_000
Interval = Tuple[int, int]


def _utc_day_bounds(ts_ms: int) -> Interval:
    """[00:00:00.000, 23:59:59.999] UTC of the calendar day containing `ts_ms`, in epoch ms. Used to
    black out a whole day for a bank holiday. UTC-day granular (documented) — good enough for a
    'don't trade this holiday' rule; a bot wanting session-day precision can widen its window."""
    d = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    start = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1) - timedelta(milliseconds=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _merge_intervals(intervals: Iterable[Interval]) -> List[Interval]:
    """Sort and merge overlapping/touching inclusive [lo, hi] intervals into a minimal disjoint set.
    Two neighbouring blackout windows that overlap become one continuous blackout."""
    ordered = sorted(intervals)
    merged: List[Interval] = []
    for lo, hi in ordered:
        if merged and lo <= merged[-1][1]:
            prev_lo, prev_hi = merged[-1]
            merged[-1] = (prev_lo, max(prev_hi, hi))
        else:
            merged.append((lo, hi))
    return merged


class _IntervalIndex:
    """Membership test over a merged, disjoint, sorted interval set, by bisection on the starts."""

    def __init__(self, intervals: Iterable[Interval]):
        self._merged = _merge_intervals(intervals)
        self._starts = [lo for lo, _ in self._merged]

    def contains(self, ts: int) -> bool:
        if not self._merged:
            return False
        i = bisect_right(self._starts, ts) - 1  # last interval whose start <= ts
        if i < 0:
            return False
        return ts <= self._merged[i][1]

    @property
    def start(self) -> Optional[int]:
        return self._merged[0][0] if self._merged else None

    @property
    def end(self) -> Optional[int]:
        return self._merged[-1][1] if self._merged else None


class NewsEngine:
    """Streaming economic-calendar engine. Construct with the events to consider, a bot-owned policy,
    and (optionally) the date ranges the event list actually covers; then feed one closed bar's
    timestamp per update().

        eng = NewsEngine(events, policy=NewsPolicy.gold(), covered_ranges=[(lo_ms, hi_ms)])
        out = eng.update(bar.index, bar.timestamp_ms)
        if out.in_blackout:   # bot's gate — skip trading
            ...

    `covered_ranges` is what makes the "trade normally where we have no news data" behaviour exact:
    it is the set of date spans the fetch actually returned. Outside every covered range,
    has_coverage is False and in_blackout is forced False. Three cases:
      * omit it (None)  -> coverage is UNBOUNDED: has_coverage is always True and coverage_start_ms
                           is None. "Not told where data begins, so don't gate on it" — the right
                           default when you just want blackout logic (tests, ad-hoc use).
      * pass a list     -> gate strictly on those ranges; coverage_start_ms is the boundary a
                           backtest UI draws its "news starts here" line at. This is the real flow —
                           EventStore.load() hands you the fetched ranges.
      * pass []         -> KNOWN-empty: has_coverage is always False, so the filter is inert
                           everywhere (an empty store => a backtest trades normally throughout).
    Passing the real ranges (not deriving from events) is what stops a quiet-but-covered week from
    being mistaken for a data gap.
    """

    def __init__(
        self,
        events: Iterable[NewsEvent],
        policy: Optional[NewsPolicy] = None,
        covered_ranges: Optional[Sequence[Interval]] = None,
    ):
        self._policy = policy or NewsPolicy.gold()
        self._all: List[NewsEvent] = sorted(events, key=lambda e: e.timestamp_ms)
        self._prev_ts: Optional[int] = None
        self._prev_in_blackout: bool = False
        self._rebuild(covered_ranges)

    def _rebuild(self, covered_ranges: Optional[Sequence[Interval]]) -> None:
        """(Re)compute the policy-derived indices. Called on construction and on set_events()."""
        self._relevant: List[NewsEvent] = [e for e in self._all if self._policy.matches(e)]
        self._rel_ts: List[int] = [e.timestamp_ms for e in self._relevant]

        pre = self._policy.pre_minutes * _MS_PER_MIN
        post = self._policy.post_minutes * _MS_PER_MIN
        self._pre_ms = pre
        self._post_ms = post

        # Bank holidays -> whole-day windows. ALWAYS computed (currency-filtered) so `is_holiday` is
        # reported regardless of blocking; blocking is a separate, opt-in choice below.
        self._holiday_days: List[Tuple[int, int, NewsEvent]] = sorted(
            (*_utc_day_bounds(e.timestamp_ms), e)
            for e in self._all
            if self._policy.is_relevant_holiday(e)
        )
        self._holiday_starts: List[int] = [s for s, _, _ in self._holiday_days]

        # Blackout = timed [pre, post] windows, PLUS holiday whole-day windows only if the bot opted
        # in via block_holidays. Otherwise holidays are reported but never force a blackout.
        windows = [(e.timestamp_ms - pre, e.timestamp_ms + post) for e in self._relevant]
        if self._policy.block_holidays:
            windows += [(s, e) for s, e, _ in self._holiday_days]
        self._blackout = _IntervalIndex(windows)

        # None => unbounded coverage (never gate); a list (incl. []) => gate strictly on it.
        self._coverage_unbounded = covered_ranges is None
        self._coverage = None if self._coverage_unbounded else _IntervalIndex(covered_ranges)

    def set_events(
        self,
        events: Iterable[NewsEvent],
        covered_ranges: Optional[Sequence[Interval]] = None,
    ) -> None:
        """Live refresh: swap in a newer event list (e.g. after refresh.py pulls the feed) without
        losing the streaming edge state (prev timestamp / prev blackout)."""
        self._all = sorted(events, key=lambda e: e.timestamp_ms)
        self._rebuild(covered_ranges)

    @property
    def coverage_start_ms(self) -> Optional[int]:
        """Earliest ms we have calendar data for — where a backtest UI draws the 'news starts here'
        vertical line. None if coverage is unbounded (no ranges given) or empty."""
        return None if self._coverage_unbounded else self._coverage.start

    @property
    def coverage_end_ms(self) -> Optional[int]:
        """Latest ms we have calendar data for (typically ~2 weeks ahead of the last refresh).
        None if coverage is unbounded or empty."""
        return None if self._coverage_unbounded else self._coverage.end

    def update(self, bar_index: int, timestamp_ms: int) -> NewsEvents:
        """Advance one closed bar. `timestamp_ms` is the bar's open time in epoch ms, UTC (Pine
        `time`). Returns this bar's NewsEvents; carries the blackout edge state to the next call."""
        ts = timestamp_ms
        has_coverage = self._coverage_unbounded or self._coverage.contains(ts)
        in_blackout = has_coverage and self._blackout.contains(ts)

        out = NewsEvents(
            has_coverage=has_coverage,
            in_blackout=in_blackout,
            entered_blackout=in_blackout and not self._prev_in_blackout,
            exited_blackout=(not in_blackout) and self._prev_in_blackout,
        )

        # Bank holiday (whole-day) — only meaningful where we have data.
        if has_coverage:
            out.active_holiday = self._active_holiday(ts)
            out.is_holiday = out.active_holiday is not None

        # Phases — nearest relevant event on each side of `ts`.
        nxt_i = bisect_left(self._rel_ts, ts)  # first event with time >= ts
        if nxt_i < len(self._relevant):
            out.next_event = self._relevant[nxt_i]
            out.minutes_to_next = (self._rel_ts[nxt_i] - ts) / _MS_PER_MIN
        last_i = bisect_right(self._rel_ts, ts) - 1  # last event with time <= ts
        if last_i >= 0:
            out.last_event = self._relevant[last_i]
            out.minutes_since_last = (ts - self._rel_ts[last_i]) / _MS_PER_MIN

        out.active_event = self._active_event(ts)

        # Released — relevant events whose time fell in (prev_ts, ts]. On the first bar there is no
        # prior bar, so nothing is "newly" released.
        if self._prev_ts is not None and ts > self._prev_ts:
            lo = bisect_right(self._rel_ts, self._prev_ts)
            hi = bisect_right(self._rel_ts, ts)
            out.released = self._relevant[lo:hi]

        self._prev_ts = ts
        self._prev_in_blackout = in_blackout
        return out

    def _active_holiday(self, ts: int) -> Optional[NewsEvent]:
        """The bank holiday whose whole-day window contains `ts`, or None. Day windows are disjoint
        per date, so the nearest-preceding start that still contains `ts` is the one."""
        i = bisect_right(self._holiday_starts, ts) - 1
        if i >= 0:
            start, end, ev = self._holiday_days[i]
            if start <= ts <= end:
                return ev
        return None

    def _active_event(self, ts: int) -> Optional[NewsEvent]:
        """The relevant event whose [t-pre, t+post] window contains `ts`; on overlap prefer the
        highest impact, then the nearest in time. `ts` is inside iff the event time is within
        [ts - post, ts + pre]."""
        lo = bisect_left(self._rel_ts, ts - self._post_ms)
        hi = bisect_right(self._rel_ts, ts + self._pre_ms)
        best: Optional[NewsEvent] = None
        best_key: Tuple[int, int] = (-1, 0)
        for ev in self._relevant[lo:hi]:
            if ev.timestamp_ms - self._pre_ms <= ts <= ev.timestamp_ms + self._post_ms:
                key = (int(ev.impact), -abs(ev.timestamp_ms - ts))
                if key > best_key:
                    best_key = key
                    best = ev
        return best
