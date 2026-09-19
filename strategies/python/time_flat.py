"""time_flat.py — ONE answer to "is the market about to close, and should we be flat?"

**Why this module exists.** Three different answers to that question already shipped in this
repo, in three places, and they did not agree:

  * `sos_fade.execution._in_flat_window` — a DAILY window, closing at THIS bar's close.
  * `realign.execution._arm_weekend_flat` — a FRIDAY window, closing at the NEXT bar's open.
  * `extreme_leg` — nothing at all, because it is an independent implementation and inherits
    none of the above.

So "flat before the close" meant a different rule, on a different clock, with a different fill,
depending on which bot you asked — and one of the three could not be asked. That is the shape of
defect this repo's rule 7 is about: a setting whose NAME is shared and whose MEANING is not.

**What this module owns and what it refuses to own.** It owns the CLOCK — when a bar sits inside
the flatten window ahead of a daily close, a weekend, or a holiday break. It does not own the
EXIT: each strategy still books its own close through its own path, because that is where costs,
tags and R are decided and a second closing path would grade differently from the first.

⚠ **The holiday calendar is GENERATED from rules and VALIDATED against measured history.** A
hand-typed list of dates is a guessed number in a costume (root rule 4), and a list ending in
2026 would stop protecting in 2027 with nothing to report. See `HolidayCalendar`.

⚠ **`due()` looks only at the CURRENT bar.** It never inspects the next bar, the next day, or
the frame. A rule that knew a holiday was coming because the data stopped would be a backtest
that cannot be traded — the live bot has no such oracle, and the calendar is how it learns the
same fact honestly.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

__all__ = [
    "MODES",
    "NY",
    "TimeFlatConfig",
    "TimeFlatRule",
    "HolidayCalendar",
    "easter_sunday",
]

NY = ZoneInfo("America/New_York")

#: What the switch can be set to. "Off" is the shipped value for every strategy — this module
#: changes no bot's behaviour until somebody sets it, which is what makes it safe to land.
#:
#: 🔴 **The three spellings are COPIED FROM `strategies/tradingview/realign_strategy.pine`**, the
#: one Pine file that already has this input, rather than improved on here. "Friday only" is not
#: the name this module would have picked — the rule it names also covers the Thursday before
#: Good Friday — but a Python enum that reads better than the Pine enum it is compared against is
#: a parity gate that goes red on a spelling. The docstring carries the nuance; the value does not.
MODES = ("Off", "Friday only", "Every day")


# ── the holiday calendar ─────────────────────────────────────────────────────────

def easter_sunday(year: int) -> dt.date:
    """Gregorian Easter (the anonymous computus). Good Friday is this minus two days.

    Gold's only mid-week full closure is Good Friday, and it is the one market holiday that
    cannot be written as a fixed date. Computing it is the difference between a calendar that
    keeps working next year and a list that quietly stops.
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month, day = divmod(h + ll - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


class HolidayCalendar:
    """Which New York DATES gold does not trade, and which ones end early.

    **Derived, not listed.** Every entry is a rule that regenerates for any year, so the
    calendar is as correct in 2031 as in 2020. Validated against the 18 extended session breaks
    actually present in the XAUUSD M1 tape 2020-01-01 → 2026-09-16 — see
    `tests/test_time_flat.py`, which pins every one of them.

    **It models two things and derives the rest.** A date is either CLOSED (no session at all)
    or EARLY (13:00 New York instead of 17:00); everything the callers ask — the close hour, and
    whether a weekend-length hole starts tonight — is computed from those two sets. Modelling
    the holes and deriving the answers is what stopped this class being wrong about 2021:
    Christmas fell on a Saturday, gold shut on the Friday, and the last session of that week was
    a **Thursday**. A calendar built on "the eve closes early" has no way to know that and would
    have left a 73-hour break unguarded.

    The three shapes gold actually shows, measured off that tape:

      * **Good Friday** — shut. A 73-hour break, and the 2026 one gapped $29.87.
      * **Christmas and New Year** — shut on the day (moved to the nearest weekday when it lands
        on a weekend), and a 13:00 early close on the eve before it. The 2025 pair gapped $23.46
        and $14.14 through a mid-week hole.
      * **Thanksgiving** — shut on the Thursday, early close on the Friday after. Measured gaps
        are nightly-sized, so it is here for completeness rather than because the tape demands it.

    ⚠ **A holiday MOVES the close hour; it does not add a second rule.** That is why callers ask
    `close_hour_ny(date)` rather than `is_holiday(date)` — the flatten window is the same window,
    anchored earlier. Asking the yes/no question would make the caller re-derive the hour, which
    is how two opinions about one close get created.
    """

    def __init__(self, default_close_hour_ny: int = 17) -> None:
        self._default = int(default_close_hour_ny)
        self._cache: dict[int, tuple[set, dict]] = {}

    @staticmethod
    def _observed(day: dt.date) -> dt.date:
        """A holiday landing on a weekend is taken on the nearest weekday, the US convention
        gold's venue follows. Saturday goes BACK to Friday and Sunday goes FORWARD to Monday."""
        if day.weekday() == 5:
            return day - dt.timedelta(days=1)
        if day.weekday() == 6:
            return day + dt.timedelta(days=1)
        return day

    def _year(self, year: int) -> tuple[set, dict]:
        cached = self._cache.get(year)
        if cached is not None:
            return cached
        closed: set = set()
        early: dict = {}

        # Good Friday — shut, and it is the one market holiday that is not a fixed date.
        closed.add(easter_sunday(year) - dt.timedelta(days=2))

        # Thanksgiving: fourth Thursday of November, shut; the Friday after closes early.
        nov1 = dt.date(year, 11, 1)
        first_thu = nov1 + dt.timedelta(days=(3 - nov1.weekday()) % 7)
        thanksgiving = first_thu + dt.timedelta(days=21)
        closed.add(thanksgiving)
        early[thanksgiving + dt.timedelta(days=1)] = 13

        # Christmas and New Year, observed. The EVE is the last weekday before the observed
        # holiday, and it closes early — which is not always Dec 24 / Dec 31, and that is the
        # whole reason this is computed rather than typed.
        for base in (dt.date(year, 12, 25), dt.date(year + 1, 1, 1)):
            obs = self._observed(base)
            closed.add(obs)
            eve = obs - dt.timedelta(days=1)
            while eve.weekday() >= 5 or eve in closed:
                eve -= dt.timedelta(days=1)
            early[eve] = 13

        # New Year's Day for THIS year is generated by the previous year's loop; generate it
        # here too so a calendar asked only about January is not silently blind to it.
        obs = self._observed(dt.date(year, 1, 1))
        closed.add(obs)

        # A date cannot be both. CLOSED wins — there is no session to end early.
        for day in closed:
            early.pop(day, None)
        self._cache[year] = (closed, early)
        return closed, early

    def is_closed(self, day: dt.date) -> bool:
        """No session at all — a weekend, or a full market holiday."""
        if day.weekday() >= 5:
            return True
        closed, _ = self._year(day.year)
        return day in closed

    def is_early_close(self, day: dt.date) -> bool:
        """Does this date trade, but end EARLIER than the ordinary close?

        🔴 **This exists because asking `close_hour_ny(day) is None` instead was a real bug.**
        That reads "the market does not trade today", and the caller wanted "today is a holiday",
        which are different questions with the same shape — so "Friday only" fired on every
        ordinary weekday and measured as "Every day" to four decimal places. The two rows were
        identical in a sweep, which is the only reason it was caught. Ask the question you mean.
        """
        if self.is_closed(day):
            return False
        _, early = self._year(day.year)
        return day in early

    def close_hour_ny(self, day: dt.date) -> Optional[int]:
        """The New York hour this date's session ends at, or `None` when it does not trade.

        An ordinary day returns the configured default rather than `None`, so `None` carries
        exactly one meaning — *there is nothing to close* — and never doubles as "unknown"
        (root rule 1). This calendar is generated, so there is no date it is unsure about.
        """
        if self.is_closed(day):
            return None
        _, early = self._year(day.year)
        return early.get(day, self._default)

    def is_last_before_long_break(self, day: dt.date) -> bool:
        """Does a weekend-length hole begin at the end of this date's session?

        True on an ordinary Friday, and on any session followed by two or more shut days — the
        Thursday before Good Friday, and the Thursday before a Friday the venue takes off. It is
        asked of the NEW YORK date: 16:45 New York on a Friday is Saturday 01:45 in Tokyo and is
        still the same session.
        """
        if self.is_closed(day):
            return False
        shut = 0
        probe = day + dt.timedelta(days=1)
        while self.is_closed(probe) and shut < 7:
            shut += 1
            probe += dt.timedelta(days=1)
        return shut >= 2


# ── the switch ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TimeFlatConfig:
    """The three numbers that decide when a bot goes flat. One meaning, every strategy."""

    mode: str = "Off"
    """`"Off"` / `"Friday only"` / `"Every day"`. Shipped `"Off"` everywhere, and spelled to
    match the Pine input in `realign_strategy.pine` exactly."""

    minutes_before: int = 15
    """How far ahead of the close the position is given up.

    ⚠ **It must comfortably exceed ONE BAR of the frame being traded**, because the close is a
    market order filled at the next bar's open on every strategy but SOS Fade's daily path. On
    the last bar before a break there is no next bar until the market reopens — which is the one
    case the rule exists to prevent. 15 minutes is 3 bars on the 5m and 1 bar on the 15m, so the
    15m frame is the tight one and is why `TimeFlatRule` refuses a window it cannot honour.
    """

    close_hour_ny: int = 17
    """The ordinary daily close, New York. Gold is 17:00; a holiday overrides it per date."""

    holidays: bool = True
    """Also flatten ahead of an early or holiday close. On by default once `mode` is not Off:
    a switch that protects 51 weekends a year and skips the three breaks with the same shape
    would be a rule with a hole in it that nobody would notice for a year."""


class TimeFlatRule:
    """Answers, for one bar: should this bot be asking to close?

    Stateless apart from a one-entry cache, so it is safe to hold on an execution object that is
    saved and restored — there is nothing in it a restart could get wrong.
    """

    def __init__(self, config: TimeFlatConfig, bar_minutes: int,
                 exit_delay_bars: int = 1) -> None:
        """`exit_delay_bars` is HOW MANY BARS LATE THE CALLER'S EXIT FILLS, and it is the whole
        reason this guard is a parameter rather than a constant.

        🔴 **The two exit timings in this repo need different windows, and hard-coding one
        refused a shipped bot.** SOS Fade's daily flat closes at THIS bar's own close, so a
        15-minute window on a 15-minute bar is exactly right: the 16:45 bar fires and the
        position is out at 17:00 — `exit_delay_bars=0`. Realign and the extreme leg arm a market
        order that fills at the NEXT bar's open, so the same window would fire on the session's
        last bar and fill after the break — `exit_delay_bars=1`, and 15 minutes on a 5m frame
        leaves three bars of room. A single rule for both would either refuse SOS Fade's working
        configuration or wave through the one that carries the gap.
        """
        if config.mode not in MODES:
            raise ValueError(f"time-flat mode {config.mode!r} not in {MODES}")
        if exit_delay_bars < 0:
            raise ValueError(f"exit_delay_bars must be 0 or more, got {exit_delay_bars!r}")
        # ⚠ **REFUSED, not clamped.** A window too narrow to leave room for the caller's exit to
        # FILL cannot get the position out before the break: the rule would run, log nothing, and
        # carry the trade through the gap it was switched on to avoid — a feature that is off
        # while reporting that it is on. Refusing at construction is the only place a person
        # still sees it.
        lead = bar_minutes * exit_delay_bars
        if config.mode != "Off" and config.minutes_before <= lead:
            raise ValueError(
                f"time-flat window {config.minutes_before}m leaves no room for an exit that "
                f"fills {exit_delay_bars} bar(s) later on a {bar_minutes}m frame: it could only "
                f"fire on the session's last bar, and the fill would land after the break"
            )
        self._cfg = config
        self._bar_minutes = int(bar_minutes)
        self._cal = HolidayCalendar(config.close_hour_ny) if config.holidays else None
        self._cached_day: Optional[Tuple[int, dt.date]] = None

    @property
    def active(self) -> bool:
        return self._cfg.mode != "Off"

    def due(self, time_ms: int) -> bool:
        """Is this bar inside the flatten window ahead of a close the rule cares about?

        ⚠ **The conversion to New York is done in full, not by assuming a whole-hour offset.**
        SOS Fade's own window gets away with reading minutes off the UTC clock because every NY
        offset is a whole number of hours; that shortcut is true for the hour and FALSE for the
        date, which is what a weekend rule has to get right. Doing it once, properly, here is
        cheaper than two rules that are each correct about a different half.
        """
        if not self.active:
            return False
        ny = dt.datetime.fromtimestamp(time_ms / 1000.0, tz=dt.timezone.utc).astimezone(NY)
        day = ny.date()

        close_hour = self._cfg.close_hour_ny
        early = False
        if self._cal is not None:
            if self._cal.is_closed(day):
                # No session today, so there is nothing to be flat before. In a replay there are
                # no bars here anyway; a live bot handed a stray tick must not act on it.
                return False
            early = self._cal.is_early_close(day)
            if early:
                close_hour = self._cal.close_hour_ny(day)

        if self._cfg.mode == "Friday only":
            long_break = self._cal.is_last_before_long_break(day) if self._cal is not None \
                else day.weekday() == 4
            # A mid-week holiday early close is not a weekend, but it IS a hole of the same
            # shape, and `holidays` is the switch that asked for it to be covered.
            if not long_break and not early:
                return False

        if ny.hour >= close_hour:
            return False
        mins_left = (close_hour - ny.hour) * 60 - ny.minute
        return 0 < mins_left <= self._cfg.minutes_before
