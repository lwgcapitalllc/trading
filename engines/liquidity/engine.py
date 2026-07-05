"""
liquidity/engine.py — the liquidity-levels state machine.

One stateful streaming engine, fed one closed bar at a time (index + UTC timestamp + high/low/close),
returning that bar's liquidity EVENTS: which levels were created, which price took (swept/broke),
which were evicted, and the full active set. Ported from the liquidity blocks of
indicators/mpc_assistant.pine:

  - DAILY / WEEKLY / MONTHLY LEVELS  .... mpc 1334-1506  (prev period high/low + mitigation)
  - PREVIOUS WEEKLY CLOSE (PWC)  ........ mpc 1508-1533  (prev week's close, a reference line)
  - H4 LIQUIDITY SWEEP TRACKER  ........ mpc 1535-1591  (prev H4 high/low + SSH/BSL sweep)
  - SESSION H/L TRACKING  .............. mpc 1593-1760  (Asia/London/NY high/low + mitigation)
  plus the "Hide Mitigated on New Day" tidy ... mpc 1344/1402/1460/1618 (newDay, NY).

The session high/low is NOT recomputed here — it is consumed from the canonical sessions engine
(engines/sessions/), which this engine composes and drives internally. That mirrors how the Pine
source keeps one running-session-H/L block and feeds the liquidity block off it; here the sessions
engine owns that block and emits a finalized SessionRange on each session close.

--------------------------------------------------------------------------------------------------
NON-REPAINTING — Aaron's explicit decision (2026-07-05)
--------------------------------------------------------------------------------------------------
The Pine source reads the day/week/month high/low via `request.security(..., high, lookahead_on)`,
which PEEKS at the whole period's future extreme and freezes it at the period's first bar (a
repaint that only shows up on saved history — the source already suppresses it on the live bar via
`not isLastDaily`). A streaming engine that feeds one closed bar at a time cannot peek ahead, and a
live bot must never trade a level built from future information. So every HTF level here is built
from the PREVIOUS, fully-completed period only: on the first bar of a new day/week/month the just-
finished period's high/low (and, for PWC, its final close) become the new level. This is exactly
what the source shows in real time (yesterday's completed high), made deterministic and streamable.
The parity harness (indicators/liquidity_export.pine) mirrors the same non-repainting reads, so the
Python↔Pine check still validates at 100% — the same "deliberate deviation, mirrored in the export"
move the sessions engine used for its render gates.

--------------------------------------------------------------------------------------------------
HTF period boundaries
--------------------------------------------------------------------------------------------------
Day / week / month / H4 buckets are cut in a single configurable timezone (`htf_timezone`), keyed on
a clock shifted so the session-open hour (`htf_rollover_hours`) lands at midnight. Day = calendar
date, week = ISO week, month = calendar month, H4 = 4-hour bucket — all on the shifted clock.
TradingView's "D"/"W"/"M"/"240" resolutions align to the instrument's exchange session, which is
broker-dependent: XAUUSD's session OPENS at 18:00 New York (its Sunday-evening bar is the first bar
of the new week, DST-aware), which is `htf_timezone="America/New_York", htf_rollover_hours=18`
(validated against the real export). Both are CALIBRATION knobs locked against the real export in
tools/compare_liquidity.py (like the other engines' `--warmup`). The "Hide Mitigated on New Day"
tidy keys off the NY calendar day (Pine `newDay`, America/New_York), which the composed sessions
engine already computes — that is a separate clock from the HTF boundary and is not configurable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from typing import Callable, Dict, List, Optional

from sessions import SessionEngine
from sessions.engine import _resolve_tz  # shared Pine-timezone parser (GMT offset or IANA name)

from .types import (
    BREAK_HIGH,
    BREAK_LOW,
    NONE,
    SWEEP_HIGH,
    SWEEP_LOW,
    LiquidityEvents,
    LiquidityLevel,
)

# HTF boundary timezone. Broker/exchange dependent — calibrated against the real export; see the
# module docstring. "America/New_York" is the working default for XAUUSD; change in one place here
# (or pass htf_timezone=) if the parity run shows the daily/weekly/monthly boundary sits elsewhere.
_DEFAULT_HTF_TZ = "America/New_York"


def _key_day(dt: datetime):
    return (dt.year, dt.month, dt.day)


def _key_week(dt: datetime):
    iso = dt.isocalendar()
    return (iso[0], iso[1])           # (ISO year, ISO week) — week starts Monday


def _key_month(dt: datetime):
    return (dt.year, dt.month)


def _key_h4(dt: datetime):
    return (dt.year, dt.month, dt.day, dt.hour // 4)   # 4-hour bucket from local midnight


class _PeriodTracker:
    """Running high/low/close for one HTF period (day/week/month/H4), rolling to a 'previous
    completed period' snapshot when the period key changes.

    Non-repainting: prev_* is only populated once a period has fully closed (a later bar carried a
    new key), so a consumer can only ever read a finished period's extremes — never the developing
    one. `update()` returns True on the bar a new period starts (i.e. prev_* just captured the
    period that ended)."""

    def __init__(self, key_fn: Callable[[datetime], object]) -> None:
        self.key_fn = key_fn
        self.cur_key: object = None
        self.cur_high: Optional[float] = None
        self.cur_low: Optional[float] = None
        self.cur_close: Optional[float] = None
        self.prev_high: Optional[float] = None
        self.prev_low: Optional[float] = None
        self.prev_close: Optional[float] = None

    def update(self, local_dt: datetime, high: float, low: float, close: float) -> bool:
        key = self.key_fn(local_dt)
        if self.cur_key is None:
            self.cur_key = key
            self.cur_high, self.cur_low, self.cur_close = high, low, close
            return False
        if key != self.cur_key:
            # the period we were accumulating just ended — freeze it as the "previous" period
            self.prev_high, self.prev_low, self.prev_close = self.cur_high, self.cur_low, self.cur_close
            self.cur_key = key
            self.cur_high, self.cur_low, self.cur_close = high, low, close
            return True
        self.cur_high = max(self.cur_high, high)   # type: ignore[type-var]
        self.cur_low = min(self.cur_low, low)      # type: ignore[type-var]
        self.cur_close = close
        return False


class LiquidityEngine:
    """Streaming liquidity-levels detector.

    Build one per symbol/timeframe and feed it one closed bar at a time, in order. It composes and
    drives its own sessions engine for the Asia/London/NY session-H/L levels, and reconstructs the
    day/week/month/H4 levels from the bar stream (non-repainting — see the module docstring).

    Defaults mirror the mpc_assistant.pine liquidity inputs: previous day/week/month H/L, PWC, the
    H4 sweep, and all three session H/Ls enabled; mitigated levels are dropped on a new NY day
    (`hide_mitigated_on_new_day`, Pine i_currentDayOnly = true).
    """

    def __init__(
        self,
        htf_timezone: str = _DEFAULT_HTF_TZ,
        htf_rollover_hours: int = 18,   # XAUUSD session opens 18:00 NY — validated at 100% Pine parity
        hide_mitigated_on_new_day: bool = True,
        enable_daily: bool = True,
        enable_weekly: bool = True,
        enable_monthly: bool = True,
        enable_pwc: bool = True,
        enable_h4: bool = True,
        enable_sessions: bool = True,
        session_engine: Optional[SessionEngine] = None,
    ) -> None:
        self._htf_tz: tzinfo = _resolve_tz(htf_timezone)
        # htf_rollover_hours = the local hour the trading day/week/month OPENS (the session open).
        # We shift the clock FORWARD so that open hour becomes midnight — this correctly rolls an
        # EVENING open (e.g. gold's 18:00 NY, whose Sunday-evening bar is the first bar of the new
        # week) into the next calendar day/week/month, not the one it sits in by wall-clock date.
        self._htf_shift = timedelta(hours=(24 - (htf_rollover_hours % 24)) % 24)
        self._hide_on_new_day = hide_mitigated_on_new_day
        self._enable = {
            "daily": enable_daily,
            "weekly": enable_weekly,
            "monthly": enable_monthly,
            "pwc": enable_pwc,
            "h4": enable_h4,
            "session": enable_sessions,
        }

        # Composed sessions engine — the single source of the session H/L + the NY new-day flag.
        self._sessions = session_engine if session_engine is not None else SessionEngine()

        self._daily = _PeriodTracker(_key_day)
        self._weekly = _PeriodTracker(_key_week)
        self._monthly = _PeriodTracker(_key_month)
        self._h4 = _PeriodTracker(_key_h4)

        # Active levels, keyed by a stable slot so a period roll replaces the right pair:
        #   "daily_high", "daily_low", "weekly_high", ... "pwc", "h4_high", "h4_low",
        #   "session_Asia_high", "session_Asia_low", ...
        self._active: Dict[str, LiquidityLevel] = {}
        self._next_id = 0

    # ------------------------------------------------------------------
    def update(self, index: int, timestamp_ms: int, high: float, low: float, close: float) -> LiquidityEvents:
        """Feed one closed bar: its index, UTC open time (epoch milliseconds, == Pine `time`), and
        the bar's high/low/close. Returns this bar's LiquidityEvents."""
        ev = LiquidityEvents()

        # Drive the composed sessions engine first — it gives us the NY new-day flag and the
        # finalized SessionRange on each session close.
        sess = self._sessions.update(index, timestamp_ms, high, low)

        # HTF period clock: convert to the boundary timezone, then shift forward so a non-midnight
        # session open (e.g. 18:00 NY for gold) cuts the day/week/month/H4 buckets correctly.
        local = (datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
                 .astimezone(self._htf_tz) + self._htf_shift)

        # 1. Hide-mitigated-on-new-day tidy (Pine newDay block, top of each liquidity block).
        if self._hide_on_new_day and sess.is_new_day:
            self._hide_mitigated(index, ev)

        # 2. Day / week / month period levels (create on a period roll), then PWC.
        self._roll_calendar(index, local, high, low, close, ev)

        # 3. H4 sweep levels (create on an H4 roll).
        self._roll_h4(index, local, high, low, close, ev)

        # 4. Session H/L levels (create on each session-close edge from the sessions engine).
        self._create_session_levels(index, sess, ev)

        # 5. Mitigation pass — every active level, after all creation (so a fresh level can be
        #    taken on its own creation bar, exactly as the Pine create-then-mitigate order allows).
        self._mitigate(index, high, low, close, ev)

        ev.active = list(self._active.values())
        return ev

    # ------------------------------------------------------------------
    def _new_level(self, index: int, ev: LiquidityEvents, slot: str, **kwargs) -> None:
        """Evict whatever occupies `slot` (a period roll / session re-open replaces it) and install a
        fresh level there, recording both the eviction and the creation edge."""
        old = self._active.pop(slot, None)
        if old is not None:
            ev.evicted.append(old)
        lvl = LiquidityLevel(created_index=index, id=self._next_id, **kwargs)
        self._next_id += 1
        self._active[slot] = lvl
        ev.created.append(lvl)

    def _roll_calendar(self, index: int, local: datetime, high: float, low: float, close: float,
                       ev: LiquidityEvents) -> None:
        """Daily / weekly / monthly previous-period H/L + PWC. On a period roll the just-completed
        period's extremes become the new PDH/PDL (etc.); PWC takes the completed week's final close.
        Daily uses the sweep rule; weekly/monthly use the close-through (break) rule (Pine 1427/1485).
        """
        if self._daily.update(local, high, low, close) and self._enable["daily"]:
            self._new_level(index, ev, "daily_high", kind="daily", side="high", name="PDH",
                            price=self._daily.prev_high, rule=SWEEP_HIGH)   # type: ignore[arg-type]
            self._new_level(index, ev, "daily_low", kind="daily", side="low", name="PDL",
                            price=self._daily.prev_low, rule=SWEEP_LOW)     # type: ignore[arg-type]

        if self._weekly.update(local, high, low, close):
            if self._enable["weekly"]:
                self._new_level(index, ev, "weekly_high", kind="weekly", side="high", name="PWH",
                                price=self._weekly.prev_high, rule=BREAK_HIGH)  # type: ignore[arg-type]
                self._new_level(index, ev, "weekly_low", kind="weekly", side="low", name="PWL",
                                price=self._weekly.prev_low, rule=BREAK_LOW)    # type: ignore[arg-type]
            if self._enable["pwc"]:
                # PWC — the previous week's final close. A reference line, never "mitigated" (Pine
                # only recolours it above/below; there is no sweep/break tracking).
                self._new_level(index, ev, "pwc", kind="pwc", side="close", name="PWC",
                                price=self._weekly.prev_close, rule=NONE)       # type: ignore[arg-type]

        if self._monthly.update(local, high, low, close) and self._enable["monthly"]:
            self._new_level(index, ev, "monthly_high", kind="monthly", side="high", name="PMH",
                            price=self._monthly.prev_high, rule=BREAK_HIGH)  # type: ignore[arg-type]
            self._new_level(index, ev, "monthly_low", kind="monthly", side="low", name="PML",
                            price=self._monthly.prev_low, rule=BREAK_LOW)    # type: ignore[arg-type]

    def _roll_h4(self, index: int, local: datetime, high: float, low: float, close: float,
                 ev: LiquidityEvents) -> None:
        """H4 sweep levels: on an H4 roll the previous H4 candle's high/low become the tracked
        levels (Pine h4PrevHigh/h4PrevLow), and the swept flags reset. Both use the sweep rule; the
        sweep, when it fires, carries the source's SSH/BSL label (Pine 1574/1585)."""
        if self._h4.update(local, high, low, close) and self._enable["h4"]:
            self._new_level(index, ev, "h4_high", kind="h4", side="high", name="H4 H",
                            price=self._h4.prev_high, rule=SWEEP_HIGH, sweep_label="BSL")  # type: ignore[arg-type]
            self._new_level(index, ev, "h4_low", kind="h4", side="low", name="H4 L",
                            price=self._h4.prev_low, rule=SWEEP_LOW, sweep_label="SSL")    # type: ignore[arg-type]

    def _create_session_levels(self, index: int, sess, ev: LiquidityEvents) -> None:
        """Turn each finished session (the sessions engine's `closed` SessionRange edges) into a
        pair of session-H/L levels. Asia/London/NY highs and lows all use the sweep rule
        (Pine 1691/1703)."""
        if not self._enable["session"]:
            return
        for rng in sess.closed:
            self._new_level(index, ev, f"session_{rng.name}_high", kind="session", side="high",
                            name=f"{rng.name} H", price=rng.high, rule=SWEEP_HIGH, session_name=rng.name)
            self._new_level(index, ev, f"session_{rng.name}_low", kind="session", side="low",
                            name=f"{rng.name} L", price=rng.low, rule=SWEEP_LOW, session_name=rng.name)

    def _mitigate(self, index: int, high: float, low: float, close: float, ev: LiquidityEvents) -> None:
        """Run every active level's mitigation rule on this bar; flag and emit the ones price takes.
        A level stays in `active` after mitigation (flagged) until a period roll or the new-day tidy
        removes it — mirroring the Pine dotted 'mitigated' line."""
        for lvl in self._active.values():
            if lvl.mitigated:
                continue
            if lvl.is_taken_by(high, low, close):
                lvl.mitigated = True
                lvl.mitigated_index = index
                ev.mitigated.append(lvl)

    def _hide_mitigated(self, index: int, ev: LiquidityEvents) -> None:
        """New-day tidy (Pine i_currentDayOnly): drop already-mitigated day/week/month/session
        levels from the active set. H4 and PWC are excluded — the source does not hide them here
        (H4 self-resets on its own roll; PWC is replaced on value change)."""
        for slot, lvl in list(self._active.items()):
            if lvl.mitigated and lvl.kind in ("daily", "weekly", "monthly", "session"):
                self._active.pop(slot)
                ev.evicted.append(lvl)

    # ------------------------------------------------------------------
    def active_levels(self) -> List[LiquidityLevel]:
        """Every currently-live level (state read), including mitigated-but-still-shown ones."""
        return list(self._active.values())
