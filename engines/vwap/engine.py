"""
vwap/engine.py — the session VWAP state machine.

One stateful streaming engine, fed one closed bar at a time (index + UTC timestamp + high/low/close
+ volume), returning that bar's VWAP EVENTS: the running session VWAP value, whether the session
re-anchored on this bar, and a derived close-vs-line cross. Ported from the single VWAP line in
indicators/engines/mpc_assistant.pine:

    hlc3       = (high + low + close) / 3                       (Pine built-in)
    vwapValue  = ta.vwap(hlc3)                                  (mpc line 852)

`ta.vwap(source)` with no explicit anchor is a SESSION-anchored VWAP: it accumulates
sum(source * volume) / sum(volume) and RESETS at the start of each new trading day. So this engine
is a plain volume-weighted running mean of hlc3 that clears its accumulator on the trading-day roll.

--------------------------------------------------------------------------------------------------
THE ANCHOR = the trading-day boundary (same knob as the liquidity engine's daily level)
--------------------------------------------------------------------------------------------------
Pine's default `ta.vwap` anchor is the start of the exchange's trading day — the SAME boundary
`request.security(..., "D", ...)` rolls on, which for VANTAGE:XAUUSD opens at 18:00 New York. This
engine reconstructs that boundary exactly as engines/liquidity/ does: convert the bar's UTC time to
`htf_timezone`, then shift the clock FORWARD by (24 - open_hour) so the session-open hour lands at
midnight, and cut the day on the calendar date of that shifted clock. The defaults
(`htf_timezone="America/New_York", htf_rollover_hours=18`) are the values validated at 100% Pine
parity for XAUUSD; both are calibration knobs, locked against the real export by the roll pulse in
tools/compare_vwap.py. A different instrument may open at a different hour (e.g. other FX at 17:00) —
pass its open hour then.

--------------------------------------------------------------------------------------------------
VOLUME
--------------------------------------------------------------------------------------------------
VWAP is the first engine that needs a VOLUME column in the feed (every prior engine used only
OHLC + timestamp). For XAUUSD this is tick volume — which is exactly what the Pine `ta.vwap` reads,
so parity is unaffected. A bar with zero/na volume contributes nothing; if a whole session has no
volume the value is None (Pine `na`), matching a divide-by-zero.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional

from sessions.engine import _resolve_tz  # shared Pine-timezone parser (GMT offset or IANA name)

from .types import VwapEvents

# Trading-day anchor timezone. Broker/exchange dependent — calibrated against the real export, the
# same way engines/liquidity/ calibrates its daily boundary. "America/New_York" + open hour 18 is
# the validated XAUUSD default; change here (or pass the constructor args) if the parity run's roll
# pulse shows the trading day opens elsewhere.
_DEFAULT_HTF_TZ = "America/New_York"


def _key_day(dt: datetime):
    """Trading-day key on the (already forward-shifted) clock — same helper the liquidity engine
    uses so the two engines cut the day on an identical boundary."""
    return (dt.year, dt.month, dt.day)


class VwapEngine:
    """Streaming session-VWAP.

    Build one per symbol/timeframe and feed it one closed bar at a time, in order. It keeps a
    volume-weighted running sum of hlc3 since the trading-day anchor and clears it on each new day.

    Public output per bar is a VwapEvents (see types.py): the VWAP value (Pine-validated), the
    re-anchor flag, and a derived close-vs-line cross.
    """

    def __init__(
        self,
        htf_timezone: str = _DEFAULT_HTF_TZ,
        htf_rollover_hours: int = 18,  # XAUUSD trading day opens 18:00 NY — validated at Pine parity
    ) -> None:
        self._tz: tzinfo = _resolve_tz(htf_timezone)
        # Shift the clock FORWARD so the session-open hour becomes midnight — this rolls an EVENING
        # open (gold's 18:00 NY) into the next calendar day, exactly like the liquidity engine.
        self._shift = timedelta(hours=(24 - (htf_rollover_hours % 24)) % 24)

        self._cur_key: Optional[object] = None
        self._sum_pv = 0.0  # sum(hlc3 * volume) since the anchor
        self._sum_v = 0.0  # sum(volume) since the anchor
        self._last_side: Optional[int] = None  # last non-zero side, for cross detection

    # ------------------------------------------------------------------
    def update(
        self, index: int, timestamp_ms: int, high: float, low: float, close: float, volume: float
    ) -> VwapEvents:
        """Feed one closed bar: its index, UTC open time (epoch milliseconds, == Pine `time`), the
        bar's high/low/close, and its volume. Returns this bar's VwapEvents."""
        ev = VwapEvents()

        # Trading-day clock: to the anchor timezone, then shift forward so an evening open cuts the
        # day correctly (see the module docstring).
        local = (
            datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc).astimezone(self._tz)
            + self._shift
        )
        key = _key_day(local)

        # Re-anchor on a new trading day (clear the accumulator). The very first fed bar sets the key
        # without pulsing `anchored` — there is no prior session to roll off (mirrors the export's
        # `dayRoll` being na/False on bar 0).
        if self._cur_key is None:
            self._cur_key = key
        elif key != self._cur_key:
            self._cur_key = key
            self._sum_pv = 0.0
            self._sum_v = 0.0
            ev.anchored = True

        # Accumulate this bar (volume-weighted hlc3) and compute the running VWAP.
        hlc3 = (high + low + close) / 3.0
        vol = volume if volume is not None else 0.0
        self._sum_pv += hlc3 * vol
        self._sum_v += vol
        ev.value = (self._sum_pv / self._sum_v) if self._sum_v > 0 else None

        # DERIVED (not Pine-validated): where the close sits vs the line, and a clean cross edge.
        if ev.value is not None:
            if close > ev.value:
                ev.side = 1
            elif close < ev.value:
                ev.side = -1
            else:
                ev.side = 0
            if ev.side != 0:
                if self._last_side == -1 and ev.side == 1:
                    ev.crossed_up = True
                elif self._last_side == 1 and ev.side == -1:
                    ev.crossed_down = True
                self._last_side = ev.side

        return ev

    # ------------------------------------------------------------------
    def value(self) -> Optional[float]:
        """The current session VWAP (state read); None until the first bar with volume."""
        return (self._sum_pv / self._sum_v) if self._sum_v > 0 else None
