"""N-day momentum off the bars a strategy already steps through — a reusable entry check.

Momentum (rate of change) = the last completed trading day's close ÷ the close N trading days
before it, minus one. Its SIGN is the direction of the bigger move: +1 up, -1 down, 0 unchanged.
What a strategy does with it is the strategy's call; the technique and how to test it are in
`docs/MOMENTUM_FILTER.md`.

🔴 **ONLY COMPLETED DAYS COUNT.** The day the current bar belongs to is still forming, so its
close is held aside and never read. Reading it would be look-ahead, and look-ahead makes any
filter look good.

⚠ **A trading day ends at 17:00 New York**, the broker's roll and the boundary the sessions and
liquidity engines use — not midnight UTC. A bar belongs to the New York date of its open time
plus (24 − roll) hours, which puts Sunday's reopen on Monday and keeps DST out of the answer.
The Pine twin computes the same key with `year/month/dayofmonth(time + 7h, "America/New_York")`.

⚠ **`direction` is `None` until N + 1 days have completed** — "cannot tell yet", never "flat".
A caller decides what unknown means; realign refuses on it.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Deque, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover — Python < 3.9
    from backports.zoneinfo import ZoneInfo  # type: ignore

__all__ = ["DailyMomentum", "trading_day_key"]

_NY = ZoneInfo("America/New_York")
_HOUR_MS = 3_600_000


def trading_day_key(time_ms: int, roll_hour_ny: int = 17) -> int:
    """The trading day a bar opening at `time_ms` (UTC epoch ms) belongs to, as YYYYMMDD."""
    shifted = (time_ms + (24 - roll_hour_ny) * _HOUR_MS) / 1000.0
    d = datetime.fromtimestamp(shifted, tz=timezone.utc).astimezone(_NY)
    return d.year * 10000 + d.month * 100 + d.day


class DailyMomentum:
    """Daily closes built bar by bar, and the sign of the N-day move over the completed ones."""

    def __init__(self, lookback_days: int, roll_hour_ny: int = 17) -> None:
        if lookback_days < 1:
            raise ValueError(f"lookback_days must be >= 1, got {lookback_days!r}")
        if not 0 <= roll_hour_ny <= 23:
            raise ValueError(f"roll_hour_ny must be 0-23, got {roll_hour_ny!r}")
        self.lookback_days = lookback_days
        self.roll_hour_ny = roll_hour_ny
        # Only the last N + 1 completed closes are ever read.
        self._closes: Deque[float] = deque(maxlen=lookback_days + 1)
        self._day: Optional[int] = None
        self._day_close: Optional[float] = None
        # New York's offset is a whole number of hours, so the day can only change when the UTC
        # hour does — the timezone maths runs once an hour instead of on every bar.
        self._hour: Optional[int] = None

    def update(self, time_ms: int, close: float) -> None:
        """Feed one bar, in time order, BEFORE reading `direction` for a decision on that bar."""
        hour = time_ms // _HOUR_MS
        if hour != self._hour:
            self._hour = hour
            day = trading_day_key(time_ms, self.roll_hour_ny)
            if day != self._day:
                if self._day_close is not None:
                    self._closes.append(self._day_close)
                self._day = day
        self._day_close = close

    @property
    def direction(self) -> Optional[int]:
        """+1 / -1 / 0 for the N-day move over completed days, or None before enough exist."""
        if len(self._closes) <= self.lookback_days:
            return None
        ret = self._closes[-1] / self._closes[0] - 1.0
        return 1 if ret > 0 else -1 if ret < 0 else 0

    @property
    def completed_days(self) -> int:
        """How many completed closes are held (capped at N + 1). Reporting only."""
        return len(self._closes)
