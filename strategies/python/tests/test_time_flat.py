"""The shared flat-before-the-close clock — `strategies/python/time_flat.py`.

**Every test here was watched go RED for the right reason** (root rule 12), and two of them are
mutation-proofs of defects that actually happened during the build rather than hypotheticals:

  * `test_friday_only_does_not_fire_on_an_ordinary_weekday` — the rule asked the calendar
    "is there a close hour for this date" when it meant "is this a HOLIDAY close", and an
    ordinary day answers the first question with 17. "Friday only" therefore fired every day.
    It was invisible in unit terms and showed up as two sweep rows agreeing to four decimals.
  * `test_the_thursday_before_a_shut_friday_is_flagged` — the first calendar was built on
    "the eve closes early", which cannot see that gold shut ALL of Friday 2021-12-24 and that
    the week's last session was therefore the Thursday. A 73-hour break went unguarded.

⚠ **The historical dates below are MEASURED, not looked up.** They are the last bar before each
of the 18 extended session breaks present in the XAUUSD M1 tape 2020-01-01 → 2026-09-16, read off
`backtest/cache/PUPrime_Demo/XAUUSD_p__M1.csv` by classifying every hole longer than five minutes.
That is why this file can assert a calendar rather than agree with one.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from time_flat import (  # noqa: E402
    MODES,
    HolidayCalendar,
    TimeFlatConfig,
    TimeFlatRule,
    easter_sunday,
)

#: The last NEW YORK trading date before each extended break in the measured tape. Every one of
#: these must be flagged by the calendar — either as an early close, or as the last session
#: before a weekend-length hole.
MEASURED_BREAKS = [
    "2020-04-09", "2020-12-24", "2020-12-31", "2021-04-01", "2021-12-23", "2022-04-14",
    "2022-12-23", "2022-12-30", "2023-04-06", "2023-12-22", "2023-12-29", "2024-03-28",
    "2024-12-24", "2024-12-31", "2025-04-17", "2025-12-24", "2025-12-31", "2026-04-02",
]


def _ms(year, month, day, hour, minute, tz="UTC") -> int:
    return int(dt.datetime(year, month, day, hour, minute,
                           tzinfo=dt.timezone.utc).timestamp() * 1000)


# ── the calendar ─────────────────────────────────────────────────────────────────

def test_good_friday_is_computed_and_matches_the_tape():
    """Easter drives the one market holiday with no fixed date. These seven are the Good Fridays
    the M1 tape actually shows a 73-hour hole behind."""
    assert [easter_sunday(y) - dt.timedelta(days=2) for y in range(2020, 2027)] == [
        dt.date(2020, 4, 10), dt.date(2021, 4, 2), dt.date(2022, 4, 15), dt.date(2023, 4, 7),
        dt.date(2024, 3, 29), dt.date(2025, 4, 18), dt.date(2026, 4, 3),
    ]


@pytest.mark.parametrize("day", MEASURED_BREAKS)
def test_every_measured_break_is_flagged(day):
    """The whole point of the calendar: 18 of 18, or it has a hole somebody has to find live."""
    cal = HolidayCalendar(17)
    date = dt.date.fromisoformat(day)
    assert not cal.is_closed(date), f"{day} traded — the tape has bars on it"
    assert cal.is_early_close(date) or cal.is_last_before_long_break(date)


def test_the_thursday_before_a_shut_friday_is_flagged():
    """Christmas 2021 fell on a Saturday, so gold took Friday 2021-12-24 off and the week's last
    session was **Thursday the 23rd** — with a 73-hour hole behind it.

    A calendar that only knows "the eve closes early" flags the 24th, which has no bars, and
    misses the 23rd, which has the position on it. Mutation-proof for the first version.
    """
    cal = HolidayCalendar(17)
    assert cal.is_closed(dt.date(2021, 12, 24))
    assert cal.is_last_before_long_break(dt.date(2021, 12, 23))


def test_an_ordinary_tuesday_is_neither():
    cal = HolidayCalendar(17)
    ordinary = dt.date(2025, 12, 23)
    assert not cal.is_closed(ordinary)
    assert not cal.is_early_close(ordinary)
    assert not cal.is_last_before_long_break(ordinary)
    assert cal.close_hour_ny(ordinary) == 17


def test_a_shut_date_has_no_close_hour_and_an_early_one_has_1300():
    """`None` means THERE IS NO SESSION, and it is the only thing it means — an ordinary day
    returns the default rather than sharing that value (root rule 1)."""
    cal = HolidayCalendar(17)
    assert cal.close_hour_ny(dt.date(2026, 4, 3)) is None        # Good Friday, shut
    assert cal.close_hour_ny(dt.date(2025, 12, 24)) == 13        # Christmas Eve, early
    assert cal.close_hour_ny(dt.date(2025, 12, 23)) == 17        # ordinary


def test_the_calendar_keeps_generating_past_the_measured_window():
    """A hand-typed list stops protecting on a date nobody notices. 2031 is past every figure
    this repo holds, and the calendar still has an opinion about it."""
    cal = HolidayCalendar(17)
    assert cal.is_closed(dt.date(2031, 4, 11))                   # Good Friday 2031
    assert cal.is_early_close(dt.date(2031, 12, 24))


# ── the switch ───────────────────────────────────────────────────────────────────

def _fires(rule, year, month, day) -> list:
    out = []
    base = dt.datetime(year, month, day, 0, 0, tzinfo=dt.timezone.utc)
    for i in range(288):
        bar = base + dt.timedelta(minutes=5 * i)
        if rule.due(int(bar.timestamp() * 1000)):
            out.append(bar.strftime("%H:%M"))
    return out


def _rule(mode, **kw):
    return TimeFlatRule(TimeFlatConfig(mode=mode, minutes_before=15, close_hour_ny=17, **kw),
                        bar_minutes=5)


def test_off_never_fires():
    rule = _rule("Off")
    assert _fires(rule, 2026, 6, 5) == []                        # a Friday


def test_every_day_fires_in_the_last_quarter_hour_of_each_weekday():
    rule = _rule("Every day")
    assert _fires(rule, 2026, 6, 1) == ["20:45", "20:50", "20:55"]   # Monday, 16:45-16:55 NY
    assert _fires(rule, 2026, 6, 5) == ["20:45", "20:50", "20:55"]   # Friday


def test_friday_only_does_not_fire_on_an_ordinary_weekday():
    """🔴 **THE BUG THIS FILE EXISTS FOR.** The rule asked the calendar for the date's close
    HOUR and treated any answer as "holiday". An ordinary weekday answers 17, so the holiday
    branch swallowed the Friday test and "Friday only" became "Every day" — which a sweep showed
    as two rows agreeing to four decimals across 127 trades.
    """
    rule = _rule("Friday only")
    assert _fires(rule, 2026, 6, 1) == []                        # Monday
    assert _fires(rule, 2026, 6, 3) == []                        # Wednesday
    assert _fires(rule, 2026, 6, 5) == ["20:45", "20:50", "20:55"]


def test_friday_only_covers_the_thursday_before_good_friday():
    """The name says Friday; the rule means "before a weekend-length hole", and the Thursday
    before Good Friday is one — the 2026 instance gapped $29.87."""
    assert _fires(_rule("Friday only"), 2026, 4, 2) == ["20:45", "20:50", "20:55"]


def test_a_holiday_early_close_moves_the_window_rather_than_adding_a_rule():
    """Christmas Eve 2025 was a Wednesday closing 13:00 New York — 18:00 UTC. The window sits
    four hours earlier than an ordinary day's, and it is the SAME window. December is EST, so
    13:00 New York is 18:00 UTC."""
    assert _fires(_rule("Friday only"), 2025, 12, 24) == ["17:45", "17:50", "17:55"]
    assert _fires(_rule("Every day"), 2025, 12, 24) == ["17:45", "17:50", "17:55"]


def test_holidays_off_leaves_the_early_closes_uncovered():
    """The switch is real: turn it off and Christmas Eve is treated as an ordinary Wednesday —
    a 17:00 New York close, which December is EST for, so 21:45 UTC. Asserted so `holidays=True`
    is a measured default rather than a decoration."""
    assert _fires(_rule("Every day", holidays=False), 2025, 12, 24) == ["21:45", "21:50", "21:55"]
    assert _fires(_rule("Friday only", holidays=False), 2025, 12, 24) == []


def test_nothing_fires_on_a_date_the_market_is_shut():
    """A live bot handed a stray tick on Good Friday must not act on it, and a replay has no
    bars there to disagree with."""
    assert _fires(_rule("Every day"), 2026, 4, 3) == []           # Good Friday
    assert _fires(_rule("Every day"), 2026, 6, 6) == []           # Saturday


def test_dst_moves_the_window_in_utc_and_not_in_new_york():
    """January and June fire at different UTC times and the same New York time. The old
    daily rule read minutes off the UTC clock and got away with it; a rule that also has to know
    the DATE cannot, which is why the conversion is done in full."""
    rule = _rule("Every day")
    assert _fires(rule, 2026, 1, 7) == ["21:45", "21:50", "21:55"]   # EST, 16:45 NY
    assert _fires(rule, 2026, 6, 3) == ["20:45", "20:50", "20:55"]   # EDT, 16:45 NY


# ── the refusals ─────────────────────────────────────────────────────────────────

def test_a_window_with_no_room_for_a_deferred_exit_is_refused():
    """A 15-minute window on a 15-minute bar can only fire on the session's LAST bar. For a
    caller whose exit is a market order filling at the NEXT bar's open, that fill lands after
    the break — the rule would run, log nothing, and carry the position through the gap it was
    switched on to prevent. Refused at construction, where a person still sees it."""
    with pytest.raises(ValueError, match="leaves no room"):
        TimeFlatRule(TimeFlatConfig(mode="Every day", minutes_before=15), bar_minutes=15)
    with pytest.raises(ValueError, match="leaves no room"):
        TimeFlatRule(TimeFlatConfig(mode="Every day", minutes_before=5), bar_minutes=5)
    # Off is exempt: nothing can fire, so nothing can fire late.
    TimeFlatRule(TimeFlatConfig(mode="Off", minutes_before=5), bar_minutes=15)


def test_an_exit_that_fills_on_this_bars_close_needs_no_lead_bar():
    """🔴 **THE FIRST VERSION OF THE GUARD REFUSED A SHIPPED CONFIGURATION.** SOS Fade is a 15m
    bot with a 15-minute window, and its daily flat books the exit at THIS bar's own close — the
    16:45 bar fires and the position is out at 17:00. A guard that assumed the deferred timing
    killed the run outright. The lead required is the CALLER's, not the module's.
    """
    rule = TimeFlatRule(TimeFlatConfig(mode="Every day", minutes_before=15),
                        bar_minutes=15, exit_delay_bars=0)
    assert rule.due(_ms(2026, 6, 3, 20, 45))
    with pytest.raises(ValueError):
        TimeFlatRule(TimeFlatConfig(mode="Every day", minutes_before=0),
                     bar_minutes=15, exit_delay_bars=0)


def test_an_unrecognised_mode_is_refused_rather_than_read_as_off():
    with pytest.raises(ValueError):
        TimeFlatRule(TimeFlatConfig(mode="Weekend only"), bar_minutes=5)


def test_the_modes_are_spelled_as_the_pine_input_spells_them():
    """`strategies/tradingview/realign_strategy.pine` is the one Pine with this input, and the
    parity gate compares the strings. A nicer name here is a red gate there."""
    assert MODES == ("Off", "Friday only", "Every day")
    pine = (_PYPKGS.parents[0] / "tradingview" / "realign_strategy.pine").read_text()
    for mode in MODES:
        assert f'"{mode}"' in pine
