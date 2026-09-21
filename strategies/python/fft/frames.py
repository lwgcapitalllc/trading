"""Higher-timeframe candles built from the chart's own bars, one bar at a time.

FFT trades off three frames — 1m, 5m and 15m — and the platform feeds one. So the 5m and 15m are
AGGREGATED here from the 1-minute bars, the way `backtest/tools/fft_first_touch_study.py` built them
with `backtest.data.resample.resample_up` (windows anchored to the epoch, labelled by their open).
Aggregating whole base bars is exact; nothing here invents a price.

🔴 **A CANDLE IS HANDED OUT THE MOMENT IT IS KNOWN TO BE CLOSED, AND NEVER EARLIER.** That is one
of two moments:

  * **its last minute closed** — the bar at 10:04 closes the 10:00 five-minute candle, so the order
    decided at 10:04's close already sees it. This is the ordinary case and it is what the study's
    "last CLOSED 5m bar" means.
  * **a bar from a LATER window arrived** — when 10:04 never printed (a quiet minute, the daily
    break, a weekend) the candle is only known complete once 10:05 or later shows up. It is handed
    out BEFORE that later bar is used for anything, because every price in it is older.

⚠ The second case is where the bot and the study can differ by a minute: the study reads the
candle as closed from 10:05 whether or not 10:04 existed, while a live bot cannot know 10:04 is not
coming until something else arrives. The bot's behaviour is the tradeable one; the study-matching
tool names every setup this moves.

⚠ **Generic on purpose.** Nothing here knows about FFT, fibs or structure — it turns a stream of
base bars into a stream of closed higher-timeframe candles, and remembers WHICH base bar made each
candle's high and low, which is the one fact a caller cannot rebuild afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Candle:
    """One closed higher-timeframe candle."""

    index: int  # 0-based sequence in THIS frame, the index its engines are fed
    start_ms: int  # the window's open time, UTC epoch ms
    open: float
    high: float
    low: float
    close: float
    first_bar: int  # chart-bar index of the first base bar in the window
    last_bar: int  # chart-bar index of the last base bar in the window
    high_bar: int  # chart-bar index that FIRST printed the window's high
    low_bar: int  # chart-bar index that FIRST printed the window's low


class ClockFrame:
    """Buckets base bars into `minutes`-wide candles on epoch-anchored windows."""

    def __init__(self, minutes: int, base_minutes: int = 1) -> None:
        if minutes <= base_minutes or minutes % base_minutes:
            raise ValueError(
                f"a {minutes}m frame cannot be built from {base_minutes}m bars — it must be a "
                f"larger whole multiple"
            )
        self.minutes = int(minutes)
        self._win_ms = int(minutes) * 60_000
        self._base_ms = int(base_minutes) * 60_000
        self._key: Optional[int] = None
        self._open = self._high = self._low = self._close = 0.0
        self._first = self._last = self._hi_bar = self._lo_bar = 0
        self._emitted = True  # nothing is being built yet
        self._count = 0
        # The candle being built, as far as it has got — for a caller that needs the window's
        # running low or high so far (the A+ sweep reads the fill's own window up to the fill).
        self.building_low = float("nan")
        self.building_high = float("nan")

    def _candle(self) -> Candle:
        c = Candle(
            index=self._count,
            start_ms=self._key * self._win_ms,
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            first_bar=self._first,
            last_bar=self._last,
            high_bar=self._hi_bar,
            low_bar=self._lo_bar,
        )
        self._count += 1
        self._emitted = True
        return c

    def close_by_arrival(self, ts_ms: int) -> Optional[Candle]:
        """Call BEFORE a new base bar is used: the candle a later window's bar proves complete."""
        if self._key is None or self._emitted:
            return None
        if ts_ms // self._win_ms != self._key:
            return self._candle()
        return None

    def add(
        self, index: int, ts_ms: int, o: float, h: float, lo: float, c: float
    ) -> Optional[Candle]:
        """Add one closed base bar. Returns the candle it completes, if it is its window's last."""
        key = ts_ms // self._win_ms
        if key != self._key:
            if self._key is not None and not self._emitted:
                raise RuntimeError(
                    "a new window started while the last one was never handed out — call "
                    "close_by_arrival() before add() for every bar"
                )
            if self._key is not None and key < self._key:
                raise ValueError(f"bars went backwards in time at bar {index}")
            self._key = key
            self._open, self._high, self._low, self._close = o, h, lo, c
            self._first = self._last = self._hi_bar = self._lo_bar = index
            self._emitted = False
        else:
            # First occurrence wins a tie, as `numpy.argmax` does in the study.
            if h > self._high:
                self._high, self._hi_bar = h, index
            if lo < self._low:
                self._low, self._lo_bar = lo, index
            self._close = c
            self._last = index
        self.building_high, self.building_low = self._high, self._low
        if ts_ms + self._base_ms >= (key + 1) * self._win_ms:
            return self._candle()
        return None

    def window_of(self, ts_ms: int) -> int:
        return ts_ms // self._win_ms


def feed(
    frame: ClockFrame, index: int, ts_ms: int, o: float, h: float, lo: float, c: float
) -> List[Candle]:
    """Both steps for one base bar, in the only safe order. Returns 0, 1 or 2 closed candles."""
    out: List[Candle] = []
    done = frame.close_by_arrival(ts_ms)
    if done is not None:
        out.append(done)
    done = frame.add(index, ts_ms, o, h, lo, c)
    if done is not None:
        out.append(done)
    return out
