"""Broker-server-clock → true UTC, DST-aware.

**The bug this exists to fix** (found by `backtest/tools/compare_feeds.py`, 2026-07-15): MT5
returns bar/tick timestamps in the BROKER SERVER's local time, but the agent stamped them with
`datetime.utcfromtimestamp()`, which labels that local time as UTC. Every bar we pulled was
2–3h off. Nothing downstream could see it — the number looked like a valid UTC timestamp — but
every time-driven engine (sessions, liquidity, VWAP, SVP, news) would fire hours out of place,
and those are exactly the engines the MPC A+ strategy trades on.

**Why not a constant offset:** the server runs MetaTrader's standard EET/EEST clock — UTC+2 in
winter, UTC+3 in summer — so any single number is wrong for half the year, and wrong in a way
that silently smears session boundaries across a DST transition instead of failing loudly.

**Why the rules are hand-rolled and not `zoneinfo`:** the agent runs on Windows, where `zoneinfo`
needs the `tzdata` package present or it raises at import. This module is pure stdlib and cannot
fail that way on a box we deploy to over SSH.

**The rule is US, not EU — this was measured, not assumed.** The offsets (+2/+3) look like Europe's
EET/EEST, and assuming so is the obvious trap. A `compare_feeds.py` run on 2026-07-16 dated the
transition between 2026-02-17 (+2h) and 2026-03-13 (+3h): EU summer time starts on the last Sunday
in March (2026-03-29), which is outside that window and therefore ruled out, while US summer time
starts on the second Sunday in March (2026-03-08), which fits. The server is effectively
**New York + 7h** — UTC+2 against EST, UTC+3 against EDT — which is common for MetaTrader brokers
because the forex week is anchored to the New York close, not to Europe.

So: summer time runs from the **second Sunday in March at 07:00 UTC** (02:00 EST) to the **first
Sunday in November at 06:00 UTC** (02:00 EDT). Transitions are defined on the UTC instant, which is
why `utc_offset_hours` takes a UTC instant and `to_utc` inverts by search rather than arithmetic.

**Verification is the only real proof.** Unit tests here lock the rule's arithmetic; they cannot
tell you the broker obeys that rule — the EU version of this file passed its tests and was wrong.
Only `compare_feeds.py` against a real pull can, and it must read a flat **0h** across a window
spanning a transition (e.g. Dec→Jul). Re-run it if the broker or terminal ever changes.
`BROKER_TZ_OFFSETS` is the knob if the offsets (not the rule) ever differ.
"""

from __future__ import annotations

import datetime
import os

__all__ = ["utc_offset_hours", "to_utc", "broker_naive_from_epoch", "STD_OFFSET", "DST_OFFSET"]

# MetaTrader server clock = EET (UTC+2) / EEST (UTC+3). Overridable without a code change if a
# broker ever differs — set e.g. BROKER_TZ_OFFSETS="2,3" (std,dst) in the agent's environment.
_ENV = os.environ.get("BROKER_TZ_OFFSETS", "2,3")
try:
    STD_OFFSET, DST_OFFSET = (int(x.strip()) for x in _ENV.split(","))
except (ValueError, TypeError):
    STD_OFFSET, DST_OFFSET = 2, 3


def _nth_sunday(year: int, month: int, n: int) -> datetime.date:
    """The `n`-th Sunday (1-based) of the given month."""
    first = datetime.date(year, month, 1)
    # weekday(): Monday=0 … Sunday=6
    first_sunday = first + datetime.timedelta(days=(6 - first.weekday()) % 7)
    return first_sunday + datetime.timedelta(weeks=n - 1)


def _dst_start_utc(year: int) -> datetime.datetime:
    """US summer time begins: second Sunday in March, 02:00 EST = 07:00 UTC."""
    return datetime.datetime.combine(_nth_sunday(year, 3, 2), datetime.time(7, 0))


def _dst_end_utc(year: int) -> datetime.datetime:
    """US summer time ends: first Sunday in November, 02:00 EDT = 06:00 UTC."""
    return datetime.datetime.combine(_nth_sunday(year, 11, 1), datetime.time(6, 0))


def utc_offset_hours(when_utc: datetime.datetime) -> int:
    """Broker offset (hours ahead of UTC) in effect at the given UTC instant.

    Boundaries are half-open: summer time is [2nd-Sun-March 07:00 UTC, 1st-Sun-November 06:00 UTC).
    """
    y = when_utc.year
    when = when_utc.replace(tzinfo=None)
    return DST_OFFSET if _dst_start_utc(y) <= when < _dst_end_utc(y) else STD_OFFSET


def to_utc(broker_naive: datetime.datetime) -> datetime.datetime:
    """Convert a naive BROKER-LOCAL datetime to naive true UTC.

    Inverted by search, not subtraction: the offset is defined on the UTC instant, so we test each
    candidate and keep the one that is self-consistent (its own UTC instant really does carry the
    offset we assumed). DST is tried first so that in the October FOLD — where 03:00–04:00 broker
    time happens twice and both candidates validate — we return the first (earlier) instant, the
    same convention `fold=0` uses.

    In the March GAP (09:00–10:00 broker time never happens — the clock jumps straight over it)
    neither candidate is self-consistent, and NO choice of offset is monotonic: subtracting the
    standard offset lands AFTER the instant that 04:00 maps to, and subtracting the DST offset
    lands BEFORE the instant that 02:59 maps to. Either way the stream would travel backwards in
    UTC, which would corrupt bar ordering in every engine. So a gap time is clamped to the
    transition instant itself, making the conversion non-decreasing everywhere. A real bar can
    never be stamped in the gap; this exists so a corrupt feed degrades instead of reordering.
    """
    for off in (DST_OFFSET, STD_OFFSET):
        candidate = broker_naive - datetime.timedelta(hours=off)
        if utc_offset_hours(candidate) == off:
            return candidate
    return _dst_start_utc(broker_naive.year)


def broker_naive_from_epoch(epoch: int) -> datetime.datetime:
    """The naive broker-local datetime MT5's integer `time` field really represents.

    MT5 hands back an epoch-looking int that is actually broker-local wall clock seconds. Reading
    it with `utcfromtimestamp` is the correct way to recover those wall-clock FIELDS — the bug was
    never this call, it was treating its result as UTC instead of passing it through `to_utc`.
    """
    return datetime.datetime.utcfromtimestamp(int(epoch))
