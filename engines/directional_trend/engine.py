"""directional_trend — the JARVIS panel's direction rows, streamable, for any bot.

Ported from `indicators/engines/mpc_jarvis.pine`:
  * BIAS W / D  — `f_biasState` + `f_htfBias` (lines ~1479-1516): the last CLOSED week/day judged
    against the one before it → Bullish / Bearish / Neutral with the panel's own text.
  * STR 4H / 15m / 1m — `f_mtfStruct` (lines ~1895-1913): the external structure engine run on
    each timeframe's own bars → last break direction + Shift / Expansion / Continuation.

--------------------------------------------------------------------------------------------------
Nothing here is a second implementation
--------------------------------------------------------------------------------------------------
The STR rows are `market_structure.StructureEngine`, instantiated once per timeframe. Pine's
`processMTF` is byte-for-byte the external half of the chart engine (its own comment says so and a
line-by-line diff on 2026-09-29 agreed), and the Python engine is gated against that chart engine.
The day / week / 4-hour boundaries are the liquidity engine's period keys, validated at parity
against the real export (18:00 New York roll for gold). Only the bias rule and the event counter
are new code, and both are ten lines of Pine.

--------------------------------------------------------------------------------------------------
NON-REPAINTING — the same deliberate deviation as the liquidity engine (Aaron, 2026-07-05)
--------------------------------------------------------------------------------------------------
Jarvis reads its higher timeframes with plain `request.security`, which on a live bar shows the
DEVELOPING 4H / 15m candle's state and can flip before it closes. A bot must never trade that.
Here a higher-timeframe bar exists only once it has CLOSED, published on the first bar of the next
period — the `[1]` + `lookahead_on` idiom, mirrored in `directional_trend_export.pine` so the gate
checks what a bot would actually read. The row that matches the bars being fed updates on the bar
itself, exactly as Jarvis sources that row from the live chart engine.

⚠ The cost, stated rather than hidden: a higher-timeframe row lands one fed bar after its candle
closes (1 minute late when fed 1m bars, 15 minutes when a 15m bot reads the 4H row).

--------------------------------------------------------------------------------------------------
Warm-up — "cannot know" is None, never Neutral
--------------------------------------------------------------------------------------------------
The first period seen is almost always PARTIAL (the stream started mid-day), so it is thrown away:
it is never fed to a structure engine and never used as bias context. A bias row needs two FULL
closed periods behind it — three weeks of history for the weekly row. A timeframe finer than the
bars fed (the 1m row on a 15m feed) is None for the life of the engine.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from liquidity.engine import (  # the validated TradingView period boundaries — reused, not retyped
    _DEFAULT_HTF_TZ,
    DEFAULT_HTF_ROLLOVER_HOURS,
    _key_day,
    _key_h4,
    _key_week,
)
from market_structure import Bar, StructureEngine
from market_structure.engine import DEFAULT_MAJOR_LENGTH  # Pine `majorLength`, typed once there
from sessions.engine import _resolve_tz

from .types import (
    BEARISH,
    BULLISH,
    DESC_CLOSE_ABOVE,
    DESC_CLOSE_BELOW,
    DESC_INSIDE,
    DESC_SWEPT_HIGH,
    DESC_SWEPT_LOW,
    EV_CONTINUATION,
    EV_EXPANSION,
    EV_NONE,
    EV_SHIFT,
    NEUTRAL,
    BiasRow,
    StructureRow,
    TrendSnapshot,
)

# Fed bars must tile both 15m and 4H cleanly.
SUPPORTED_BASE_MINUTES = (1, 3, 5, 15)


def bias_state(
    action_high: float,
    action_low: float,
    action_close: float,
    context_high: float,
    context_low: float,
    tf_prefix: str,
) -> BiasRow:
    """Pine `f_biasState`, verbatim in order of precedence: closure beats sweep, bull beats bear."""
    if action_close > context_high:
        return BiasRow(BULLISH, DESC_CLOSE_ABOVE, f"Close > Prev {tf_prefix} High")
    if action_close < context_low:
        return BiasRow(BEARISH, DESC_CLOSE_BELOW, f"Close < Prev {tf_prefix} Low")
    if action_high > context_high and action_close <= context_high:
        return BiasRow(BEARISH, DESC_SWEPT_HIGH, f"Swept {tf_prefix} High")
    if action_low < context_low and action_close >= context_low:
        return BiasRow(BULLISH, DESC_SWEPT_LOW, f"Swept {tf_prefix} Low")
    return BiasRow(NEUTRAL, DESC_INSIDE, f"Inside {tf_prefix} Range")


class _Candle:
    __slots__ = ("open", "high", "low", "close")

    def __init__(self, o: float, h: float, l: float, c: float) -> None:
        self.open, self.high, self.low, self.close = o, h, l, c

    def add(self, h: float, l: float, c: float) -> None:
        self.high = max(self.high, h)
        self.low = min(self.low, l)
        self.close = c


class _Periods:
    """Builds one higher timeframe's candles from the fed bars.

    A candle is emitted on the first bar of the NEXT period (non-repainting). The first period is
    discarded as partial — the stream almost never starts on a period boundary.
    """

    def __init__(self, key_fn: Callable[[datetime, int], object]) -> None:
        self._key_fn = key_fn
        self._key: object = None
        self._cur: Optional[_Candle] = None
        self._cur_full = False

    def update(
        self, local: datetime, ts_ms: int, o: float, h: float, l: float, c: float
    ) -> Optional[_Candle]:
        key = self._key_fn(local, ts_ms)
        if self._key is None:
            self._key, self._cur = key, _Candle(o, h, l, c)
            return None
        if key == self._key:
            self._cur.add(h, l, c)
            return None
        done = self._cur if self._cur_full else None
        self._key, self._cur, self._cur_full = key, _Candle(o, h, l, c), True
        return done


class _StructureTf:
    """`f_mtfStruct`: one canonical structure engine plus Pine's shift/expansion/continuation counter."""

    def __init__(self, major_length: int) -> None:
        self._eng = StructureEngine(major_length=major_length)
        self._n = 0
        self._ev = EV_NONE
        self._since_shift = 0
        self.row: Optional[StructureRow] = None

    def feed(self, o: float, h: float, l: float, c: float) -> None:
        x = self._eng.update(Bar(index=self._n, open=o, high=h, low=l, close=c)).external
        self._n += 1
        if x.bull_sos or x.bear_sos:
            self._ev = EV_SHIFT
            self._since_shift = 0
        elif x.bull_bos or x.bear_bos:
            self._since_shift += 1
            self._ev = EV_EXPANSION if self._since_shift == 1 else EV_CONTINUATION
        self.row = StructureRow(direction=int(self._eng.dir or 0), event=self._ev)


class _BiasTf:
    """`f_htfBias`: the last two FULL closed periods → a BiasRow."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._prev: Optional[_Candle] = None
        self.row: Optional[BiasRow] = None

    def closed(self, candle: _Candle) -> None:
        if self._prev is not None:
            self.row = bias_state(
                candle.high, candle.low, candle.close, self._prev.high, self._prev.low, self._prefix
            )
        self._prev = candle


class DirectionalTrend:
    """Feed closed bars of ONE timeframe (1, 3, 5 or 15 minutes); read `snapshot()` after each.

    Rows at or above the fed timeframe are built here; finer ones stay None. To get the 1m row,
    feed 1-minute bars.
    """

    def __init__(
        self,
        base_minutes: int,
        *,
        major_length: int = DEFAULT_MAJOR_LENGTH,
        htf_timezone: str = _DEFAULT_HTF_TZ,
        htf_rollover_hours: int = DEFAULT_HTF_ROLLOVER_HOURS,
    ) -> None:
        if base_minutes not in SUPPORTED_BASE_MINUTES:
            raise ValueError(
                f"base_minutes must be one of {SUPPORTED_BASE_MINUTES}, got {base_minutes!r}"
            )
        self._base = base_minutes
        self._tz = _resolve_tz(htf_timezone)
        self._shift = timedelta(hours=(24 - (htf_rollover_hours % 24)) % 24)
        self._last_ts: Optional[int] = None

        self._m1 = _StructureTf(major_length) if base_minutes == 1 else None
        self._m15 = _StructureTf(major_length)
        self._h4 = _StructureTf(major_length)
        self._daily = _BiasTf("D")
        self._weekly = _BiasTf("W")

        self._p15 = None if base_minutes == 15 else _Periods(lambda _l, ts: ts // 900_000)
        self._p4h = _Periods(lambda l, _ts: _key_h4(l))
        self._pd = _Periods(lambda l, _ts: _key_day(l))
        self._pw = _Periods(lambda l, _ts: _key_week(l))

    def update(
        self, timestamp_ms: int, open_: float, high: float, low: float, close: float
    ) -> TrendSnapshot:
        """Process one CLOSED bar, stamped with its OPEN time in epoch milliseconds, in order."""
        if self._last_ts is not None and timestamp_ms <= self._last_ts:
            raise ValueError(
                f"bars must arrive in time order: {timestamp_ms} after {self._last_ts}"
            )
        if timestamp_ms % (self._base * 60_000):
            raise ValueError(f"bar at {timestamp_ms} is not on a {self._base}-minute boundary")
        self._last_ts = timestamp_ms
        bar = (open_, high, low, close)
        local = (
            datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc).astimezone(self._tz)
            + self._shift
        )

        if self._m1 is not None:
            self._m1.feed(*bar)
        if self._p15 is None:
            self._m15.feed(*bar)
        else:
            done = self._p15.update(local, timestamp_ms, *bar)
            if done is not None:
                self._m15.feed(done.open, done.high, done.low, done.close)
        done = self._p4h.update(local, timestamp_ms, *bar)
        if done is not None:
            self._h4.feed(done.open, done.high, done.low, done.close)
        done = self._pd.update(local, timestamp_ms, *bar)
        if done is not None:
            self._daily.closed(done)
        done = self._pw.update(local, timestamp_ms, *bar)
        if done is not None:
            self._weekly.closed(done)
        return self.snapshot()

    def snapshot(self) -> TrendSnapshot:
        return TrendSnapshot(
            weekly=self._weekly.row,
            daily=self._daily.row,
            h4=self._h4.row,
            m15=self._m15.row,
            m1=self._m1.row if self._m1 is not None else None,
        )
