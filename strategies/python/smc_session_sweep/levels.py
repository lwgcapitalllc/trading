"""The previous day's and previous week's high and low, derived from the chart's own bars.

The Pine reads these through `request.security(sym, "D"/"W", [high[1], low[1]],
lookahead = barmerge.lookahead_on)`. ⚠ **`lookahead_on` here is not a peek into the future** — the
series asked for is already the PREVIOUS period's extreme, so the lookahead only makes yesterday's
finished high available from the first bar of today instead of trailing a period behind. Rebuilding
it from the chart reproduces that exactly, and reads no bar that has not closed.

**The day boundary is 17:00 New York, MEASURED not assumed.** Four candidate boundaries were
scored against `px_pdh`/`px_pdl` in the golden export: a UTC day matched 8,531 of 20,597 bars, a
New York calendar day 2,136, and the 17:00 New York close 20,321 — with every one of its 276
disagreements inside the first 276 bars, which is the first day warming up. After bar 500 it is
exact. The weekly boundary is the same clock and scores the same way: 1,380 disagreements, all of
them inside the first week, none after bar 2,000.

⚠ **A UTC day would have been the obvious guess and is wrong on more than half the bars.** It is
written down because the two look identical in a chart screenshot and differ on every trade whose
target is yesterday's low.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

__all__ = ["PrevPeriodLevels"]

_NY = ZoneInfo("America/New_York")
#: The trading day rolls at 17:00 New York, so shifting by seven hours puts a whole trading day
#: inside one calendar date and the rest is ordinary date arithmetic — DST included, because the
#: shift is applied AFTER converting to New York rather than as a fixed UTC offset.
_ROLL = timedelta(hours=7)

NAN = float("nan")


class PrevPeriodLevels:
    """Streaming: feed every chart bar, read the previous day's and week's extremes.

    Both come back as NaN until a full period has CLOSED — never as the current period's extreme
    so far, and never as zero. "Not known yet" and "the level is at zero" must not share a value,
    and a target silently set to 0.0 would make every long's reward look infinite.
    """

    def __init__(self) -> None:
        self._day_key: Optional[int] = None
        self._week_key: Optional[int] = None
        self._day_hi = self._day_lo = NAN
        self._week_hi = self._week_lo = NAN
        self.pdh = self.pdl = self.pwh = self.pwl = NAN

    @staticmethod
    def _keys(time_ms: int) -> Tuple[int, int]:
        local = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc).astimezone(_NY) + _ROLL
        day = local.date().toordinal()
        week = (local - timedelta(days=local.weekday())).date().toordinal()
        return day, week

    def update(self, time_ms: int, high: float, low: float) -> None:
        day, week = self._keys(time_ms)

        if day != self._day_key:
            if self._day_key is not None:
                self.pdh, self.pdl = self._day_hi, self._day_lo
            self._day_key = day
            self._day_hi, self._day_lo = high, low
        else:
            self._day_hi = max(self._day_hi, high)
            self._day_lo = min(self._day_lo, low)

        if week != self._week_key:
            if self._week_key is not None:
                self.pwh, self.pwl = self._week_hi, self._week_lo
            self._week_key = week
            self._week_hi, self._week_lo = high, low
        else:
            self._week_hi = max(self._week_hi, high)
            self._week_lo = min(self._week_lo, low)
