"""feed.py — MT5 bars → the canonical frame the engines replay, and new-closed-bar detection.

Two jobs, both small and both easy to get subtly wrong:

1. **Shape.** `backtest/replay.iter_bars` wants a UTC `DatetimeIndex` with `open/high/low/close`
   columns, bars timestamped at their OPEN. That is exactly what MT5 gives once
   `BotMT5.get_candles` has converted the broker clock (see its docstring — the conversion is
   not optional and is where the 2-3 hour bug lived).

2. **Only ever hand over CLOSED bars.** `copy_rates_from_pos(…, 0, n)` returns the newest `n`
   bars and the LAST one is still forming. Feeding it to the engines would be repainting of the
   worst kind: the structure engine is a state machine, so a bar whose high later extends can
   promote a swing that then has to un-happen — and it cannot un-happen. Every read here drops
   the final row, and the runner only acts when a bar's timestamp is one it has not seen.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

# name → (MT5 timeframe constant name, seconds per bar). The constants are looked up off the
# module at call time so this file imports on a machine with no MetaTrader5 (tests, the Mac).
TIMEFRAMES = {
    "M1": ("TIMEFRAME_M1", 60),
    "M5": ("TIMEFRAME_M5", 300),
    "M15": ("TIMEFRAME_M15", 900),
    "M30": ("TIMEFRAME_M30", 1800),
    "H1": ("TIMEFRAME_H1", 3600),
    "H4": ("TIMEFRAME_H4", 14400),
    "D1": ("TIMEFRAME_D1", 86400),
}


def timeframe_for_minutes(minutes: int) -> str:
    """`5` → `"M5"`. The re-entry's fill clock is configured in MINUTES and the feed is
    addressed by NAME, and this is the one place the two meet.

    🔴 **It REFUSES a duration MT5 has no timeframe for rather than rounding to the nearest
    one.** A fill clock of 7 minutes silently served as 5m or 10m is a strategy replayed on a
    stream nobody chose — the lab would measure one thing and the bot would trade another, with
    the config file agreeing with neither. Same rule as an out-of-range stop ratio: refuse, name
    the legal set, and let a human decide.
    """
    want = int(minutes) * 60
    for name, (_const, secs) in TIMEFRAMES.items():
        if secs == want:
            return name
    legal = ", ".join(
        str(secs // 60) for _n, (_c, secs) in TIMEFRAMES.items() if secs % 60 == 0 and secs < 86400
    )
    raise ValueError(
        f"No MT5 timeframe is {minutes} minutes long, so no bar stream can be opened for it. "
        f"Legal minute values: {legal}."
    )


def timeframe_seconds(name: str) -> int:
    try:
        return TIMEFRAMES[name][1]
    except KeyError:
        raise ValueError(f"Unknown timeframe {name!r}. Use one of: {', '.join(TIMEFRAMES)}")


def mt5_timeframe(name: str, mt5_module) -> int:
    try:
        const = TIMEFRAMES[name][0]
    except KeyError:
        raise ValueError(f"Unknown timeframe {name!r}. Use one of: {', '.join(TIMEFRAMES)}")
    return getattr(mt5_module, const)


def to_canonical(df: pd.DataFrame) -> pd.DataFrame:
    """A `BotMT5.get_candles` frame → the canonical replay frame, WITHOUT the forming last bar.

    Returns an empty frame (not None, not a partial) when there is nothing usable, so a caller
    can always `len()` it.
    """
    if df is None or df.empty or "time" not in df.columns:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    out = df.iloc[:-1]  # drop the still-forming bar — see the module docstring
    if out.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    out = out.set_index(pd.DatetimeIndex(out["time"], name=None))
    out = out[["open", "high", "low", "close"]].astype(float)
    return out


class BarFeed:
    """Pulls closed bars for one symbol/timeframe and reports which ones are NEW.

    Holds exactly one piece of state — the open time of the last bar handed out — because that
    is the only thing that makes "new" meaningful across a poll, a reconnect, or a restart.
    """

    def __init__(self, bot_mt5, timeframe: str, symbol: Optional[str] = None) -> None:
        self._mt5 = bot_mt5
        self.timeframe = timeframe
        self.symbol = symbol or bot_mt5.symbol
        self.bar_seconds = timeframe_seconds(timeframe)
        self.last_bar_time: Optional[pd.Timestamp] = None

    def _tf_const(self):
        import MetaTrader5 as mt5

        return mt5_timeframe(self.timeframe, mt5)

    def history(self, count: int) -> pd.DataFrame:
        """The last `count` CLOSED bars, canonical. Used for warmup."""
        raw = self._mt5.get_candles(self._tf_const(), count + 1, self.symbol)
        return to_canonical(raw)

    def mark_seen(self, df: pd.DataFrame) -> None:
        """Record that everything in `df` has been processed. Called after warmup so the first
        live poll does not replay the last warmup bar as if it were new."""
        if len(df):
            self.last_bar_time = df.index[-1]

    def new_bars(self, lookback: int = 5) -> pd.DataFrame:
        """Closed bars strictly newer than the last one handed out. Usually 0 or 1 rows.

        `lookback` is deliberately several bars rather than one: a poll that is late (VPS
        hiccup, terminal reconnect, the bot restarting mid-session) must catch up rather than
        skip, and skipping a bar silently desynchronises the engines from the market for the
        rest of the session. If the gap is bigger than `lookback` the caller should re-warm
        from history instead — `gap_bars` below is how it finds out.
        """
        raw = self._mt5.get_candles(self._tf_const(), lookback + 1, self.symbol)
        df = to_canonical(raw)
        if df.empty:
            return df
        if self.last_bar_time is None:
            fresh = df.iloc[[-1]]
        else:
            fresh = df[df.index > self.last_bar_time]
        if len(fresh):
            self.last_bar_time = fresh.index[-1]
        return fresh

    def gap_bars(self) -> int:
        """How many bars have closed since the last one processed. 0 = up to date. A number
        larger than a poll interval's worth means the bot was asleep and must re-warm rather
        than resume — the engines are a state machine, and a hole in the stream is not a
        recoverable condition, it is a different market history."""
        if self.last_bar_time is None:
            return 0
        raw = self._mt5.get_candles(self._tf_const(), 2, self.symbol)
        df = to_canonical(raw)
        if df.empty:
            return 0
        delta = (df.index[-1] - self.last_bar_time).total_seconds()
        return max(0, int(delta // self.bar_seconds))
