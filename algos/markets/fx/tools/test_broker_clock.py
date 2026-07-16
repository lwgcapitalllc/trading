"""Offline tests for the broker-clock → true-UTC conversion.

Pure arithmetic — no MT5, no network, no VPS. These lock the DST RULE (EU: last Sunday of
March/October at 01:00 UTC). They cannot prove the broker actually follows that rule; only
`backtest/tools/compare_feeds.py` against a real pull can (see broker_clock's docstring).

Run: command-center/backend/.venv/bin/python -m pytest algos/markets/fx/tools/test_broker_clock.py -q
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from broker_clock import STD_OFFSET, DST_OFFSET, to_utc, utc_offset_hours  # noqa: E402


def _dt(y, mo, d, h=0, mi=0) -> datetime.datetime:
    return datetime.datetime(y, mo, d, h, mi)


# ── the offset rule, on UTC instants ──────────────────────────────────────────

def test_winter_is_standard_offset():
    assert utc_offset_hours(_dt(2026, 1, 15, 12)) == STD_OFFSET == 2


def test_summer_is_dst_offset():
    assert utc_offset_hours(_dt(2026, 7, 15, 12)) == DST_OFFSET == 3


def test_2026_transitions_are_the_us_dates():
    # 2026: 2nd Sunday of March = the 8th (07:00 UTC); 1st Sunday of November = the 1st (06:00 UTC).
    assert utc_offset_hours(_dt(2026, 3, 8, 6, 59)) == STD_OFFSET
    assert utc_offset_hours(_dt(2026, 3, 8, 7, 0)) == DST_OFFSET
    assert utc_offset_hours(_dt(2026, 11, 1, 5, 59)) == DST_OFFSET
    assert utc_offset_hours(_dt(2026, 11, 1, 6, 0)) == STD_OFFSET


def test_2025_transitions():
    # 2025: 2nd Sunday of March = the 9th; 1st Sunday of November = the 2nd.
    assert utc_offset_hours(_dt(2025, 3, 9, 6, 59)) == STD_OFFSET
    assert utc_offset_hours(_dt(2025, 3, 9, 7, 0)) == DST_OFFSET
    assert utc_offset_hours(_dt(2025, 11, 2, 6, 0)) == STD_OFFSET


def test_the_rule_is_us_not_eu():
    """The measured evidence, pinned (compare_feeds.py, 2026-07-16): the broker was on +2h at
    2026-02-17 and +3h at 2026-03-13. EU summer time starts 2026-03-29 — it cannot produce +3h on
    2026-03-13, which is what rules EU out. Reverting this file to EU rules fails HERE."""
    assert utc_offset_hours(_dt(2026, 2, 17, 12)) == STD_OFFSET     # +2h, measured
    assert utc_offset_hours(_dt(2026, 3, 13, 12)) == DST_OFFSET     # +3h, measured
    # ...and the EU transition date must still be inside summer, not the start of it.
    assert utc_offset_hours(_dt(2026, 3, 29, 12)) == DST_OFFSET


def test_march_1st_sunday_is_not_the_transition():
    """Guards the _nth_sunday count: 2026-03-01 is itself a Sunday, so the SECOND Sunday is the
    8th, not the 1st. An off-by-one week here is a silent 7-day window of wrong timestamps."""
    assert utc_offset_hours(_dt(2026, 3, 1, 12)) == STD_OFFSET
    assert utc_offset_hours(_dt(2026, 3, 7, 12)) == STD_OFFSET
    assert utc_offset_hours(_dt(2026, 3, 9, 12)) == DST_OFFSET


# ── the conversion ────────────────────────────────────────────────────────────

def test_winter_bar_shifts_back_two_hours():
    assert to_utc(_dt(2026, 1, 15, 14, 0)) == _dt(2026, 1, 15, 12, 0)


def test_summer_bar_shifts_back_three_hours():
    assert to_utc(_dt(2026, 7, 15, 15, 0)) == _dt(2026, 7, 15, 12, 0)


def test_the_bug_this_fixes():
    """A 17:00-NY gold close in summer is 21:00 UTC. Broker stamps it 00:00 next day.
    The old code called that midnight UTC — three hours late, on the exact boundary the
    liquidity engine anchors the trading day to."""
    broker_stamp = _dt(2026, 7, 16, 0, 0)
    assert to_utc(broker_stamp) == _dt(2026, 7, 15, 21, 0)


def test_round_trip_is_self_consistent_across_a_year():
    """Every candidate we return must really carry the offset we assumed."""
    d = _dt(2026, 1, 1, 0, 30)
    while d.year == 2026:
        utc = to_utc(d)
        gap_hours = (d - utc).total_seconds() / 3600.0
        assert gap_hours == utc_offset_hours(utc)
        d += datetime.timedelta(hours=7)


def test_november_fold_returns_the_earlier_instant():
    """08:30 broker time happens twice on the November transition day (09:00 EEST-equivalent rolls
    back to 08:00). We return the first (DST) reading — the same convention as fold=0."""
    got = to_utc(_dt(2026, 11, 1, 8, 30))
    assert got == _dt(2026, 11, 1, 5, 30)      # DST reading, not 06:30
    assert utc_offset_hours(got) == DST_OFFSET


def test_march_gap_does_not_raise():
    """09:00-10:00 broker time never happens in March (the clock jumps 09:00 -> 10:00). A bar
    can't legitimately be stamped there, but a corrupt feed must not take the agent down."""
    got = to_utc(_dt(2026, 3, 8, 9, 30))
    assert isinstance(got, datetime.datetime)


def test_conversion_is_monotonic_across_the_march_transition():
    """Bars must never travel backwards in UTC — a non-monotonic stream would corrupt every
    engine's bar ordering."""
    prev = None
    d = _dt(2026, 3, 8, 4, 0)
    while d < _dt(2026, 3, 9, 4, 0):
        utc = to_utc(d)
        if prev is not None:
            assert utc >= prev, f"went backwards at broker {d}"
        prev = utc
        d += datetime.timedelta(minutes=5)


def test_conversion_is_monotonic_across_the_november_transition():
    prev = None
    d = _dt(2026, 11, 1, 4, 0)
    while d < _dt(2026, 11, 2, 4, 0):
        utc = to_utc(d)
        if prev is not None:
            assert utc >= prev, f"went backwards at broker {d}"
        prev = utc
        d += datetime.timedelta(minutes=5)


def test_epoch_reader_recovers_broker_wall_clock_fields():
    from broker_clock import broker_naive_from_epoch

    # 1_700_000_000 == 2023-11-14 22:13:20 UTC as wall-clock fields.
    assert broker_naive_from_epoch(1_700_000_000) == _dt(2023, 11, 14, 22, 13) + \
        datetime.timedelta(seconds=20)
