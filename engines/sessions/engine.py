"""
sessions/engine.py — the trading-sessions / kill-zones / NY-range state machine.

One stateful streaming engine, fed one closed bar at a time (index + UTC timestamp + high/low),
returning that bar's clock flags plus session open/close edges. Unlike the other engines this one
is TIME-driven, not price-driven: its inputs are the bar's wall-clock timestamp (epoch
milliseconds, UTC — exactly Pine's `time`) and, for the running session/NY-range extremes, the
bar's high/low.

Ported from indicators/engines/mpc_assistant.pine, four blocks that all key off the clock:

  - session windows inAsia/inLondon/inNY .............. Pine 836-838   (time(session, tz))
  - SESSION H/L TRACKING (running asia/london/ny H/L) . Pine 1638-1646
  - KILL ZONES inKZ1/inKZ2/inKZ3 ..................... Pine 1861-1866  (NY hour/minute)
  - NY RANGE opening-range high/low .................. Pine 1824-1856  (0930-0935 NY, ≤5m)
  plus newDay / isMondayToFriday ..................... Pine 808-809.

Two deliberate deviations from the Pine source, both consistent with "emit events, not visuals":

  1. All box/line/label drawing is dropped — this emits flags + edges.
  2. The two "days-back" render gates (withinKZDays / withinNYRangeDays, Pine 847-850) are dropped.
     They only limit how many days of boxes Pine draws back from `timenow`, and depend on the
     non-reproducible export wall-clock; the underlying time flags and running extremes they gate
     are computed unconditionally here so the output is reproducible bar-for-bar.

Timezones: every window is DST-aware and stated in its own city's clock — Asia/Tokyo,
Europe/London, America/New_York for the sessions, and America/New_York for the kill zones, new-day,
weekday and NY-range windows — matching the Pine source exactly. Fixed GMT offsets ("GMT-4") are
still parsed (the mpc sessions used them until 2026-07-31, and a custom SessionSpec may) and are
resolved arithmetically; IANA names go through the stdlib `zoneinfo`.

The NY opening range is a ≤5m feature (Pine reads it off a 5-minute security). Feed this engine
5-minute-or-finer bars if you rely on ny_range_high/low; on a 5m feed the 0930-0935 window is a
single bar, exactly as Pine sees it. The session windows and kill zones are timeframe-agnostic.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Dict, Optional

from .types import SessionEvents, SessionRange, SessionSpec

try:  # zoneinfo is stdlib from 3.9; needed only for IANA (DST) zone names, not GMT offsets.
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

# NY kill-zone / new-day / weekday / NY-range clock is always "America/New_York" in the Pine source.
_NY_TZ_NAME = "America/New_York"

# NY opening-range windows, minutes-from-NY-midnight: 0930-0935 (window) and 0935-1600 (extend).
_NYR_WINDOW = (9 * 60 + 30, 9 * 60 + 35)  # inSession5 = time("5","0930-0935","America/New_York")
_NYR_EXTEND = (9 * 60 + 35, 16 * 60)  # inExtend5  = time("5","0935-1600","America/New_York")

_GMT_RE = re.compile(r"^GMT([+-]\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)


def _resolve_tz(name: str) -> tzinfo:
    """Turn a Pine timezone string into a tzinfo. Accepts a fixed GMT offset ("GMT-4", "GMT+5:30")
    or an IANA name ("America/New_York"). Pine's "GMT-4" means UTC-4 (verified against the mpc
    session windows: Tokyo 2000-0500 GMT-4 == 00:00-09:00 UTC)."""
    n = (name or "").strip()
    if n.upper() in ("UTC", "GMT", "GMT+0", "GMT-0", "GMT0"):
        return timezone.utc
    m = _GMT_RE.match(n)
    if m:
        hours = int(m.group(1))
        minutes = int(m.group(2) or 0)
        sign = 1 if hours >= 0 else -1
        return timezone(timedelta(hours=hours, minutes=sign * minutes))
    if ZoneInfo is None:  # pragma: no cover
        raise RuntimeError(f"zoneinfo unavailable; cannot resolve IANA timezone {name!r}")
    return ZoneInfo(n)


def _pine_dayofweek(dt: datetime) -> int:
    """Pine's dayofweek convention: Sunday=1 ... Saturday=7 (dayofweek.monday==2 ... friday==6)."""
    return (dt.isoweekday() % 7) + 1


def _in_window(minute_of_day: int, start: int, end: int) -> bool:
    """Membership in a [start, end) minute window; wraps past midnight when end <= start."""
    if start <= end:
        return start <= minute_of_day < end
    return minute_of_day >= start or minute_of_day < end


class _SessionTracker:
    """Running high/low for one configured session window (Pine's asiaHigh/asiaLow pair etc.).

    `high`/`low` persist across the gap between sessions exactly like Pine's `var float` — they are
    only reset on the first bar of the next session, so a consumer reading them between sessions
    sees the last session's extremes (this is what makes the every-bar parity check meaningful)."""

    def __init__(self, spec: SessionSpec, tz: tzinfo) -> None:
        self.spec = spec
        self.tz = tz
        self.in_session = False  # this becomes inX[1] on the next bar
        self.high: Optional[float] = None
        self.low: Optional[float] = None
        self.start_index: Optional[int] = None

    def contains(self, utc: datetime) -> bool:
        # NOTE: this is a pure time-of-day window with no day-of-week mask — Pine's
        # time(timeframe, session, tz) defaults to all 7 days ("1234567") when the session string
        # carries no ":days" suffix (the mpc session inputs carry none). CONFIRMED by the 5m parity
        # export (2026-07-04): 240 Sunday-evening bars that Pine flagged in-Asia all matched, so the
        # all-7-days default is correct. If a future export ever mismatches ONLY on weekend bars,
        # the default has changed to weekday-only and a dayofweek gate belongs here.
        local = utc.astimezone(self.tz)
        return _in_window(
            local.hour * 60 + local.minute, self.spec.start_minute, self.spec.end_minute
        )


class SessionEngine:
    """Streaming trading-sessions / kill-zones / NY-range detector.

    Build one per symbol/timeframe and feed it one closed bar at a time, in order. Defaults mirror
    the mpc_assistant.pine inputs: Tokyo 0900-1800 Asia/Tokyo, London 0800-1700 Europe/London,
    New York 0800-1700 America/New_York; kill zones and the NY opening range on America/New_York time.

    Re-synced 2026-07-31 from the previous fixed-offset form (Tokyo 2000-0500, London 0400-1300,
    New York 0900-1800, all "GMT-4"). Each window is now stated in its OWN city's clock and follows
    that city's DST, which is a real behaviour change for two of the three — see the table in
    CLAUDE.md. Asia is unchanged in UTC terms; London and New York move one hour earlier under
    BST/EDT.
    """

    DEFAULT_SESSIONS = (
        SessionSpec.from_pine("Asia", "0900-1800", "Asia/Tokyo"),
        SessionSpec.from_pine("London", "0800-1700", "Europe/London"),
        SessionSpec.from_pine("NY", "0800-1700", "America/New_York"),
    )

    def __init__(
        self, sessions: Optional["list[SessionSpec]"] = None, ny_timezone: str = _NY_TZ_NAME
    ) -> None:
        specs = list(sessions) if sessions is not None else list(self.DEFAULT_SESSIONS)
        self._ny_tz = _resolve_tz(ny_timezone)
        self._trackers: Dict[str, _SessionTracker] = {
            s.name: _SessionTracker(s, _resolve_tz(s.tz_name)) for s in specs
        }

        self._prev_ny_dow: Optional[int] = None

        # NY opening-range state (Pine nyr_high_val / nyr_low_val, both var -> persist across day).
        self._nyr_high: Optional[float] = None
        self._nyr_low: Optional[float] = None
        self._prev_in_nyr_window = False  # Pine inSession5[1]

    # ------------------------------------------------------------------
    def update(self, index: int, timestamp_ms: int, high: float, low: float) -> SessionEvents:
        """Feed one closed bar: its index, UTC open time (epoch milliseconds, == Pine `time`), and
        the bar's high/low (needed only for the running session / NY-range extremes)."""
        utc = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
        ny = utc.astimezone(self._ny_tz)
        ny_minute_of_day = ny.hour * 60 + ny.minute
        ny_dow = _pine_dayofweek(ny)

        is_weekday = 2 <= ny_dow <= 6  # Pine isMondayToFriday
        is_new_day = self._prev_ny_dow is not None and ny_dow != self._prev_ny_dow  # Pine newDay
        self._prev_ny_dow = ny_dow

        events = SessionEvents(is_new_day=is_new_day, is_weekday=is_weekday)

        # ── Session windows + running H/L (Pine 836-838 + 1638-1646) ──
        self._update_sessions(index, utc, high, low, events)

        # ── Kill zones (Pine 1861-1866) — pure NY hour/minute, no days-back / drawing bookkeeping ──
        events.in_kz1 = ny.hour == 10
        events.in_kz2 = (ny.hour == 11 and ny.minute >= 45) or (ny.hour == 12 and ny.minute <= 14)
        events.in_kz3 = ny.hour == 13 and ny.minute <= 30

        # ── NY opening range (Pine 1824-1856) ──
        self._update_ny_range(ny_minute_of_day, is_weekday, high, low, events)

        return events

    # ------------------------------------------------------------------
    def _update_sessions(
        self, index: int, utc: datetime, high: float, low: float, events: SessionEvents
    ) -> None:
        """Session membership + the running-high/low port (Pine 1638-1646). On the first in-session
        bar reset the extremes to this bar's H/L and record an `opened`; while in-session expand
        them; on the first out-of-session bar finalize and record a `closed` SessionRange."""
        flags: Dict[str, bool] = {}
        for name, tr in self._trackers.items():
            now_in = tr.contains(utc)
            was_in = tr.in_session

            if now_in:
                if not was_in:  # Pine `not inX[1]` -> reset
                    tr.high, tr.low, tr.start_index = high, low, index
                    events.opened.append(name)
                else:  # expand
                    tr.high = max(tr.high, high)  # type: ignore[type-var]
                    tr.low = min(tr.low, low)  # type: ignore[type-var]
            elif was_in and tr.high is not None:  # Pine `not inX and inX[1]` -> finalize
                events.closed.append(
                    SessionRange(
                        name=name,
                        high=tr.high,
                        low=tr.low,
                        start_index=tr.start_index,
                        end_index=index - 1,
                    )  # type: ignore[arg-type]
                )

            tr.in_session = now_in
            flags[name] = now_in

        events.in_asia = flags.get("Asia", False)
        events.in_london = flags.get("London", False)
        events.in_ny = flags.get("NY", False)

    # ------------------------------------------------------------------
    def _update_ny_range(
        self,
        ny_minute_of_day: int,
        is_weekday: bool,
        high: float,
        low: float,
        events: SessionEvents,
    ) -> None:
        """NY opening-range port (Pine 1824-1856), drawing + days-back gate removed. On the first
        bar of the 0930-0935 NY window (a weekday) reset the range to this bar's H/L, then expand
        it across the window; the values persist (Pine `var`) through the rest of the day."""
        in_window = _in_window(ny_minute_of_day, *_NYR_WINDOW)  # inSession5
        in_extend = _in_window(ny_minute_of_day, *_NYR_EXTEND)  # inExtend5

        if in_window and is_weekday:
            if not self._prev_in_nyr_window:  # inSession5 and not inSession5[1]
                self._nyr_high, self._nyr_low = high, low  # reset (Pine 1825-1827)
            if self._nyr_low is None or low < self._nyr_low:  # expand (Pine 1834-1837)
                self._nyr_low = low
            if self._nyr_high is None or high > self._nyr_high:
                self._nyr_high = high
        self._prev_in_nyr_window = in_window

        events.in_ny_range_window = in_window
        events.in_ny_range_extend = in_extend
        events.ny_range_high = self._nyr_high
        events.ny_range_low = self._nyr_low

    # ------------------------------------------------------------------
    def current_range(self, name: str) -> Optional[SessionRange]:
        """The live high/low for a session as of now (in-progress if currently open, else the last
        session's finalized extremes), or None if it has never opened. `end_index` is always None
        here — this is a running read; the finalized span arrives on the `closed` edge event."""
        tr = self._trackers.get(name)
        if tr is None or tr.high is None:
            return None
        return SessionRange(
            name=name,
            high=tr.high,
            low=tr.low,
            start_index=tr.start_index,  # type: ignore[arg-type]
            end_index=None,
        )
