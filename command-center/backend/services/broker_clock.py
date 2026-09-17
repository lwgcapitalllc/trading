"""The broker SERVER's clock → true UTC, for the one thing this app reads straight off MT5: deals.

MT5 stamps a deal's `time` / `time_msc` in the broker server's wall clock, written as though it
were an epoch. Read as UTC it is two or three hours wrong, and wrong by a different amount either
side of a daylight-saving change — so a trade would sit on the wrong candles and its excursion
would be measured over the wrong bars, with nothing on screen to say so.

⚠ **A MIRROR, not a new rule.** The rule is `algos/markets/fx/tools/broker_clock.py` (measured by
`backtest/tools/compare_feeds.py`: the server runs New York + 7h, so UTC+2 in winter and UTC+3 in
US summer time). This app may not import from `algos/` (the two are independent by the repo's
rule), so the arithmetic is repeated here and **`tests/test_broker_clock_parity.py` loads the
algos file by path and checks the two agree** on every hour across two DST changes. Change the
rule THERE and that test turns red here, which is the point.

⚠ **Bars need no conversion** — the MT5 agent already converts them before they reach the bar
cache. Only a deal read straight off the ledger needs this.
"""

from __future__ import annotations

import datetime as _dt
import os

_ENV = os.environ.get("BROKER_TZ_OFFSETS", "2,3")
try:
    STD_OFFSET, DST_OFFSET = (int(x.strip()) for x in _ENV.split(","))
except (ValueError, TypeError):
    STD_OFFSET, DST_OFFSET = 2, 3


def _nth_sunday(year: int, month: int, n: int) -> _dt.date:
    first = _dt.date(year, month, 1)
    first_sunday = first + _dt.timedelta(days=(6 - first.weekday()) % 7)
    return first_sunday + _dt.timedelta(weeks=n - 1)


def _dst_start_utc(year: int) -> _dt.datetime:
    """US summer time begins: second Sunday in March, 07:00 UTC."""
    return _dt.datetime.combine(_nth_sunday(year, 3, 2), _dt.time(7, 0))


def _dst_end_utc(year: int) -> _dt.datetime:
    """US summer time ends: first Sunday in November, 06:00 UTC."""
    return _dt.datetime.combine(_nth_sunday(year, 11, 1), _dt.time(6, 0))


def utc_offset_hours(when_utc: _dt.datetime) -> int:
    """Hours the server is ahead of UTC at a naive UTC instant. Half-open, like the original."""
    when = when_utc.replace(tzinfo=None)
    y = when.year
    return DST_OFFSET if _dst_start_utc(y) <= when < _dst_end_utc(y) else STD_OFFSET


def to_utc(broker_naive: _dt.datetime) -> _dt.datetime:
    """A naive server-clock datetime as naive UTC — inverted by search, gap clamped, as the original."""
    for off in (DST_OFFSET, STD_OFFSET):
        candidate = broker_naive - _dt.timedelta(hours=off)
        if utc_offset_hours(candidate) == off:
            return candidate
    return _dst_start_utc(broker_naive.year)


def server_ms_to_utc_ms(server_ms: int) -> int:
    """A deal's `time_msc` (server wall clock, as epoch ms) → true UTC epoch ms."""
    secs, ms = divmod(int(server_ms), 1000)
    naive = _dt.datetime(1970, 1, 1) + _dt.timedelta(seconds=secs)
    utc = to_utc(naive)
    return int((utc - _dt.datetime(1970, 1, 1)).total_seconds()) * 1000 + ms
