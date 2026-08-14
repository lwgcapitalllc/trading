"""Broker history floors — the earliest date a backtest may legitimately start.

WHY THIS EXISTS
---------------
MT5 does not error when a symbol has no history at the requested timeframe. It returns
the nearest COARSER timeframe's bars, still labelled as what you asked for. A backtest
fed daily bars as 15m does not crash — it produces a full trade list, a clean equity
curve, and a completely fictional answer. That is far worse than an exception.

Verified on Vantage XAUUSD 2026-07-26 by asking for January 2010 four ways:

    asked M1  -> 21 bars      (real would be ~29,000)
    asked M15 -> 21 bars      (real would be ~1,900)
    asked H1  -> 21 bars      (real would be ~480)
    asked D1  -> 21 bars      <- what all four actually served

21 = the trading days in that month. Every intraday request was handed D1.

THE FLOOR IS MEASURED, NEVER ASSUMED
------------------------------------
Depth is a property of the BROKER, and it changes: brokers extend history, and swapping
the terminal to a different broker changes it outright. So a hardcoded date is a bug
waiting to happen — it would let a deeper broker be needlessly truncated, and (worse) let
a shallower one inherit a floor it cannot honour.

`HistoryFloors.floor()` therefore PROBES the live terminal by binary search and caches the
answer keyed on `(server, symbol, timeframe)`, where `server` comes from the agent's
`/status` (e.g. "VantageMarkets-Demo"). Change broker and the key changes, so the old
measurement is never reused. `--refresh`/`refresh=True` re-probes on demand.

Probing asks one question — "does this single day return a plausible number of bars for
this timeframe?" — because bar DENSITY is the one thing that cannot lie. Do NOT use the
agent's `/data_availability` for this: it samples one bar from each end, so the
substitution above fools it completely. On 2026-07-26 it reported `earliest 2007-06-22`
for EVERY timeframe including M1, false by ~11 years.

Two independent defences, both needed:
  1. `assert_window()` — the measured floor, checked before any fetch. Cheap, actionable,
     and what the UI reads so a user is stopped at the date picker.
  2. `assert_bar_spacing()` — an empirical check on what actually came back. Backstop for
     an unprobed symbol, an unreachable agent, and the day a broker's depth shifts.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd

from .timeframes import to_minutes

# Timeframes at or above this are "daily" — a separate, usually much deeper floor.
_DAILY_MIN = 1440

# A day counts as REAL for a timeframe when it returns at least this fraction of the bars
# a 24h day would hold. Generous on purpose: the market runs ~23h/day, a probe can land on
# a half-session or a holiday, and the failure it must catch is off by a FACTOR (D1 served
# as M15 = 1 bar where 96 are due, H1 as M15 = 23 where 96 are due), never by a few percent.
_DENSITY_MIN = 0.35

# Nothing is searched before this — no retail FX/metals broker carries intraday from
# earlier, and it bounds the binary search to ~14 probes.
_SEARCH_FROM = _dt.date(2000, 1, 1)

# How far ahead the holiday-tolerant cluster test looks. Must cover a long weekend plus a
# holiday; `probe()` phase 2 undoes the early bias this creates.
_CLUSTER_SPAN = 7

# Fallback ONLY when the agent cannot be reached, and only for the broker it was measured
# on. Tagged with `server` so it is never applied to a different broker's terminal.
#
# Deliberately CONSERVATIVE: the probe puts M15 at 2018-09-13 and M1 at 2018-09-14, so the
# seed carries the later date for all intraday. Refusing one extra day costs nothing;
# allowing one day too early is exactly the fictional-backtest failure this module exists
# to prevent. The probe supersedes this whenever the terminal is reachable.
_SEED: dict[tuple[str, str], dict] = {
    ("VantageMarkets-Demo", "XAUUSD"): {
        "intraday": "2018-09-14",
        "daily": "2007-06-21",
        "verified": "2026-07-26",
    },
}


def _norm(symbol: str) -> str:
    """Broker suffixes (`.s`, `.a`) are the same underlying instrument's history."""
    return (symbol or "").upper().split(".")[0]


def _tf_name(minutes: int) -> str:
    """Minutes → the agent's timeframe token."""
    return {1: "M1", 5: "M5", 15: "M15", 30: "M30", 60: "H1", 240: "H4", 1440: "D1"}.get(
        minutes, f"M{minutes}"
    )


def _expected_per_day(minutes: int) -> int:
    return max(1, (24 * 60) // minutes)


class HistoryFloorError(ValueError):
    """A requested window starts before the broker's real history for that timeframe."""


# ── the spacing backstop (pure — no agent, no cache) ────────────────────────────


def assert_bar_spacing(df: "pd.DataFrame", timeframe: str | int, symbol: str = "") -> None:
    """Raise `HistoryFloorError` if the returned bars are not the timeframe requested.

    The modal gap IS the timeframe — weekends and the daily close break produce larger
    gaps, and no legitimate gap is ever smaller than the bar interval.
    """
    if df is None or len(df.index) < 3:
        return
    minutes = to_minutes(timeframe)
    gaps = df.index.to_series().diff().dropna()
    if gaps.empty:
        return
    modal = int(gaps.mode().iloc[0].total_seconds() // 60)
    who = f"{symbol} " if symbol else ""
    if modal != minutes:
        raise HistoryFloorError(
            f"{who}bars are spaced {modal}m apart but {minutes}m was requested — the broker "
            f"substituted a coarser timeframe because it has no {minutes}m history for this "
            f"window. Refusing to return bars that would silently produce a fictional result."
        )
    closer = int((gaps < pd.Timedelta(minutes=minutes)).sum())
    if closer:
        raise HistoryFloorError(
            f"{who}{closer} bars are spaced closer than {minutes}m — the frame is not a clean "
            f"{minutes}m series."
        )


# ── measured floors ─────────────────────────────────────────────────────────────


class HistoryFloors:
    """Discovers and caches each broker's real history start, per symbol + timeframe."""

    def __init__(self, agent=None, cache_dir: str | Path | None = None):
        self._agent = agent
        if cache_dir is None:
            from .cache import BarCache

            cache_dir = BarCache().dir
        self.path = Path(cache_dir) / "history_floors.json"
        self._server: Optional[str] = None
        self._data: Optional[dict] = None

    # -- agent / identity ------------------------------------------------------
    @property
    def agent(self):
        if self._agent is None:
            from .mt5_agent import Mt5Agent

            self._agent = Mt5Agent()
        return self._agent

    def server(self) -> str:
        """The broker the terminal is currently on; "" when unknown/unreachable."""
        if self._server is None:
            try:
                self._server = str(self.agent.status().get("server") or "")
            except Exception:
                self._server = ""
        return self._server

    # -- cache ----------------------------------------------------------------
    def _load(self) -> dict:
        if self._data is None:
            try:
                self._data = json.loads(self.path.read_text())
            except Exception:
                self._data = {}
        return self._data

    def _save(self) -> None:
        # Atomic — a probe is expensive and a torn file would silently re-probe forever.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(self._data or {}, fh, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @staticmethod
    def _key(server: str, symbol: str, minutes: int) -> str:
        return f"{server}|{_norm(symbol)}|{minutes}"

    # -- probing --------------------------------------------------------------
    def _day_is_real(self, symbol: str, minutes: int, day: _dt.date) -> bool:
        """Does this ONE day return a plausible bar count for this timeframe?

        A coarser substitution fails by a factor (D1-as-M15 returns 1 of 96), so a
        generous density threshold separates them without tripping on holidays.
        """
        want = _expected_per_day(minutes) * _DENSITY_MIN
        iso = day.isoformat()
        try:
            n = self.agent.bar_count(symbol, _tf_name(minutes), iso, iso)
        except Exception:
            return False
        return n >= want

    def _first_real(self, symbol: str, minutes: int, day: _dt.date) -> bool:
        """`_day_is_real` over a small midweek cluster — one probe day can be a holiday
        or a half session, and a false 'no data' here would push the floor years late.

        Search-only: the tolerance biases EARLY, which `probe()` corrects in phase 2.
        """
        for offset in (0, 1, 2, 3, _CLUSTER_SPAN):
            d = day + _dt.timedelta(days=offset)
            if d.weekday() >= 5:  # skip weekends, never a full session
                continue
            if self._day_is_real(symbol, minutes, d):
                return True
        return False

    def probe(self, symbol: str, timeframe: str | int) -> Optional[_dt.date]:
        """Find the earliest date with REAL bars. None if the probe cannot run.

        Two phases, because they need opposite error tolerances:

        1. BINARY SEARCH using the holiday-tolerant cluster test. A single probe day can
           be a holiday or half session, and a false "no data" there would push the floor
           years late — so the cluster looks a few days ahead. That tolerance biases the
           result EARLY by up to the lookahead, which is the dangerous direction.
        2. FORWARD SCAN with the strict single-day test, from the bracket's low end, to
           land on the first day that genuinely has bars. This removes the bias.

        ~25 HTTP calls once per (broker, symbol, timeframe), then cached.
        Invariant during the search: `hi` is known-real, `lo` known-absent.
        """
        minutes = to_minutes(timeframe)
        today = _dt.date.today()
        hi = today - _dt.timedelta(days=7)
        if not self._first_real(symbol, minutes, hi):
            return None  # no recent data at all — agent down or bad symbol
        lo = _SEARCH_FROM
        if self._first_real(symbol, minutes, lo):
            return lo  # history reaches the search bound
        while (hi - lo).days > 3:
            mid = lo + (hi - lo) / 2
            if self._first_real(symbol, minutes, mid):
                hi = mid
            else:
                lo = mid

        # Phase 2 — exact. Scan forward past the cluster lookahead so the answer can never
        # sit before the first day that really has bars.
        day = lo
        limit = hi + _dt.timedelta(days=_CLUSTER_SPAN + 4)
        while day <= limit:
            if day.weekday() < 5 and self._day_is_real(symbol, minutes, day):
                return day
            day += _dt.timedelta(days=1)
        return hi

    # -- public ---------------------------------------------------------------
    def floor(self, symbol: str, timeframe: str | int, refresh: bool = False) -> Optional[_dt.date]:
        """The earliest date this (broker, symbol, timeframe) has REAL bars for.

        None means UNKNOWN — never "unlimited". The spacing backstop still applies.
        """
        minutes = to_minutes(timeframe)
        server = self.server()
        if not server:
            return self._seed(symbol, minutes, server=None)

        data = self._load()
        key = self._key(server, symbol, minutes)
        if not refresh and key in data:
            try:
                return _dt.date.fromisoformat(data[key]["floor"])
            except Exception:
                pass  # corrupt entry — fall through and re-probe

        found = self.probe(symbol, minutes)
        if found is None:
            return self._seed(symbol, minutes, server=server)
        data[key] = {
            "floor": found.isoformat(),
            "server": server,
            "symbol": _norm(symbol),
            "timeframe_minutes": minutes,
            "probed": _dt.date.today().isoformat(),
            "method": "bar-density binary search",
        }
        self._data = data
        try:
            self._save()
        except Exception:
            pass  # a cache we cannot write is slow, not wrong
        return found

    def _seed(self, symbol: str, minutes: int, server: Optional[str]) -> Optional[_dt.date]:
        """Last-resort fallback, used ONLY for the broker the seed was measured on.

        An unknown server means we cannot prove which broker is attached, so no seed
        applies — returning one would risk imposing Vantage's floor on someone else's
        deeper history (needless truncation) or shallower history (a fictional run).
        """
        if not server:
            return None
        entry = _SEED.get((server, _norm(symbol)))
        if not entry:
            return None
        return _dt.date.fromisoformat(entry["daily" if minutes >= _DAILY_MIN else "intraday"])

    def describe(self, symbol: str, timeframe: str | int, refresh: bool = False) -> Optional[dict]:
        """The whole record for a (symbol, timeframe) — what the API hands the UI, so the
        date picker's minimum and its explanatory text come from ONE measurement."""
        minutes = to_minutes(timeframe)
        fl = self.floor(symbol, minutes, refresh=refresh)
        if fl is None:
            return None
        server = self.server()
        entry = self._load().get(self._key(server, symbol, minutes)) or {}
        measured = bool(entry)
        return {
            "symbol": _norm(symbol),
            "timeframe_minutes": minutes,
            "earliest_date": fl.isoformat(),
            "broker": server,
            "verified": entry.get("probed")
            or _SEED.get((server, _norm(symbol)), {}).get("verified", ""),
            "source": "probed" if measured else "seed",
            "note": (
                f"{_norm(symbol)} has no real {minutes}-minute bars before {fl.isoformat()} on "
                f"{server or 'this broker'}. Earlier requests are served COARSER bars mislabelled "
                f"as {minutes}m, which would produce a plausible but fictional backtest."
            ),
        }

    def assert_window(
        self, symbol: str, timeframe: str | int, start_date: str, end_date: str | None = None
    ) -> None:
        """Raise `HistoryFloorError` if `start_date` precedes the measured floor."""
        try:
            start = _dt.date.fromisoformat(str(start_date)[:10])
        except ValueError:
            raise HistoryFloorError(f"start_date {start_date!r} is not YYYY-MM-DD")
        fl = self.floor(symbol, timeframe)
        if fl is None or start >= fl:
            return
        minutes = to_minutes(timeframe)
        raise HistoryFloorError(
            f"{_norm(symbol)} has no real {minutes}-minute history before {fl.isoformat()} on "
            f"{self.server() or 'this broker'} (measured, not assumed). You asked for "
            f"{start.isoformat()}. Requests before the floor are served COARSER bars mislabelled "
            f"as the timeframe you asked for, which would produce a plausible but fictional "
            f"backtest — so this is refused rather than run. Move the start date to "
            f"{fl.isoformat()} or later."
        )


# ── module-level convenience (lazy shared instance) ─────────────────────────────
_SHARED: Optional[HistoryFloors] = None


def shared() -> HistoryFloors:
    global _SHARED
    if _SHARED is None:
        _SHARED = HistoryFloors()
    return _SHARED


def floor_for(symbol: str, timeframe: str | int, refresh: bool = False) -> Optional[_dt.date]:
    return shared().floor(symbol, timeframe, refresh=refresh)


def describe(symbol: str, timeframe: str | int = 15, refresh: bool = False) -> Optional[dict]:
    return shared().describe(symbol, timeframe, refresh=refresh)


def assert_window(
    symbol: str, timeframe: str | int, start_date: str, end_date: str | None = None
) -> None:
    shared().assert_window(symbol, timeframe, start_date, end_date)
