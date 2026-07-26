"""Thin HTTP client over the VPS MT5 agent (algos/markets/fx/tools/mt5_agent.py).

Reads broker bars from the agent's GET /historical_data endpoint, reachable on
localhost:8766 via the SSH tunnel that command-center's start.sh opens. Stdlib
only (urllib) so the backtest package stays dependency-light and importable
anywhere. This is a data reader, not a second agent — the agent stays canonical.

Tick history (2yr deep on this broker) will back the fill model, but the agent
has no /ticks endpoint yet; adding one is A2 work, not A0.
"""

from __future__ import annotations

import datetime as _dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .cache import _normalize
from .timeframes import to_minutes

_DEFAULT_BASE_URL = "http://localhost:8766"

# ONE request can never exceed the terminal's "Max bars in chart" setting: past it MT5 does not
# clamp or return a partial answer, it fails the whole call with (-2, 'Terminal: Invalid params'),
# which surfaces as a bare 404 "no data" — indistinguishable from a symbol that has no history.
# Measured on PU Prime 2026-07-21, XAUUSD.s M15: 64,837 bars OK, ~70,000 (3 years) → -2. So the cap
# is the classic 65,000; we chunk under it with headroom rather than depend on a terminal setting
# nobody can see from here. Chunk length is derived from the timeframe against a 24h day, so the
# real (24/5 market) count always lands well below the budget.
_MAX_BARS_PER_REQUEST = 60_000
_MINUTES_PER_DAY = 1440

# A tick-mode backtest makes thousands of sequential calls over an SSH tunnel, so a transient drop
# is a matter of WHEN, not IF — one was observed ~5 months into a year-long run ("Remote end closed
# connection without response"), killing 40 minutes of work. Retrying is not papering over an
# error: a dropped connection is a statement about the tunnel, not about the data, and the honest
# response is to ask again. Only CONNECTION failures retry — an HTTP error is the agent answering,
# and asking a refused question again just gets refused again.
_RETRIES = 4
_BACKOFF_S = 1.5


class Mt5AgentError(RuntimeError):
    """The MT5 agent was unreachable or returned an error / no data."""


class Mt5Agent:
    """Fetches OHLC bars from the MT5 agent over HTTP."""

    def __init__(self, base_url: str = _DEFAULT_BASE_URL, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _fetch(self, url: str, what: str) -> dict:
        """GET + parse JSON, retrying transient connection failures with linear backoff."""
        last: Exception | None = None
        for attempt in range(_RETRIES):
            try:
                with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError:
                raise                                    # the agent answered — not transient
            except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
                last = exc
                if attempt < _RETRIES - 1:
                    time.sleep(_BACKOFF_S * (attempt + 1))
        raise Mt5AgentError(
            f"MT5 agent unreachable at {self.base_url} after {_RETRIES} attempts "
            f"({what}; is the SSH tunnel up?): {last}"
        ) from last

    def bars(
        self, symbol: str, tf_name: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch [start_date, end_date] (inclusive, YYYY-MM-DD) bars at tf_name.

        Long windows are split into chunks that each stay under the terminal's bar cap
        (see _MAX_BARS_PER_REQUEST) and stitched back together.

        Returns the canonical bar frame (DatetimeIndex 'time' + OHLC). Raises Mt5AgentError if the
        agent is down, or if the WHOLE window served no data. An individual chunk coming back empty
        is NOT an error: broker history simply starts somewhere, and a 3-year request against a
        2-year symbol should return the 2 years that exist rather than failing outright.
        """
        windows = _chunk_windows(start_date, end_date, tf_name)
        frames: list[pd.DataFrame] = []
        for w_start, w_end in windows:
            try:
                frames.append(self._bars_window(symbol, tf_name, w_start, w_end))
            except Mt5AgentError:
                if len(windows) == 1:
                    raise            # single-window request — the caller asked, the answer is no data
                continue             # a gap at the edge of history; other chunks may still answer
        if not frames:
            raise Mt5AgentError(
                f"MT5 agent returned no bars for {symbol} {tf_name} "
                f"[{start_date}, {end_date}] across {len(windows)} chunk(s)"
            )
        if len(frames) == 1:
            return frames[0]
        merged = pd.concat(frames)
        # Chunk bounds are inclusive on both ends, so adjacent chunks share their boundary day.
        return merged[~merged.index.duplicated(keep="first")].sort_index()

    def _bars_window(
        self, symbol: str, tf_name: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """One /historical_data call — the window must fit the terminal's bar cap."""
        query = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "timeframe": tf_name,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        url = f"{self.base_url}/historical_data?{query}"
        try:
            payload = self._fetch(url, f"{symbol} {tf_name} [{start_date}, {end_date}]")
        except urllib.error.HTTPError as exc:
            detail = _read_error(exc)
            raise Mt5AgentError(
                f"MT5 agent {exc.code} for {symbol} {tf_name} "
                f"[{start_date}, {end_date}]: {detail}"
            ) from exc

        if "error" in payload:
            raise Mt5AgentError(
                f"MT5 agent error for {symbol} {tf_name}: {payload['error']}"
            )
        bars = payload.get("bars", [])
        if not bars:
            raise Mt5AgentError(
                f"MT5 agent returned no bars for {symbol} {tf_name} "
                f"[{start_date}, {end_date}]"
            )
        return _normalize(pd.DataFrame(bars))

    def status(self) -> dict:
        """The terminal's identity — `{account, server, terminal_path, mt5_connected, …}`.

        `server` is what tells one BROKER from another ("VantageMarkets-Demo"). History
        depth is a property of the broker, so anything cached about depth must be keyed on
        this: swap the account to a different broker and a cached floor measured on the old
        one is worse than no answer, because it looks authoritative. Returns `{}` rather
        than raising — an unreachable agent means "identity unknown", which callers must
        already handle.
        """
        try:
            return self._fetch(f"{self.base_url}/status", "status")
        except Exception:
            return {}

    def bar_count(self, symbol: str, tf_name: str, start_date: str, end_date: str) -> int:
        """How many bars the broker serves for a window — 0 when it serves none.

        The cheap primitive history probing is built on. Unlike `bars()` this never
        raises on an empty answer: "no bars here" is the ANSWER when you are searching
        for where history begins, not a failure.
        """
        query = urllib.parse.urlencode({
            "symbol": symbol, "timeframe": tf_name,
            "start_date": start_date, "end_date": end_date,
        })
        try:
            payload = self._fetch(f"{self.base_url}/historical_data?{query}", "bar_count")
        except Exception:
            return 0
        if "error" in payload:
            return 0
        return int(payload.get("count") or len(payload.get("bars") or []))

    def ticks(self, symbol: str, start: str, end: str) -> list[dict]:
        """Fetch real bid/ask ticks in [start, end) — ISO datetimes in TRUE UTC.

        Returns a list of {"time", "bid", "ask"} dicts (the agent's wire shape); `backtest.data.ticks`
        owns the typed conversion. Pass the SMALLEST window that answers your question: gold is ~690k
        ticks/day, so a whole day is ~43MB and ~90s while a 5-minute bar is ~260KB and under a second.

        Unlike `bars`, an EMPTY result is not an error — weekends, holidays and the 17:00-NY gold
        break genuinely have no ticks, and raising there would make a real market gap look like a
        broken symbol.
        """
        query = urllib.parse.urlencode({"symbol": symbol, "start_date": start, "end_date": end})
        url = f"{self.base_url}/ticks?{query}"
        try:
            payload = self._fetch(url, f"{symbol} ticks [{start}, {end})")
        except urllib.error.HTTPError as exc:
            raise Mt5AgentError(
                f"MT5 agent {exc.code} for {symbol} ticks [{start}, {end}): {_read_error(exc)}"
            ) from exc

        if "error" in payload and payload["error"]:
            raise Mt5AgentError(f"MT5 agent error for {symbol} ticks: {payload['error']}")
        return payload.get("ticks", [])


def _chunk_windows(start_date: str, end_date: str, tf_name: str) -> list[tuple[str, str]]:
    """Split [start_date, end_date] into inclusive windows that each fit the bar cap.

    One window is returned for anything already small enough, so the common case makes exactly the
    same single call it always did.
    """
    start = _dt.date.fromisoformat(start_date)
    end = _dt.date.fromisoformat(end_date)
    if end < start:
        return [(start_date, end_date)]
    span_days = (end - start).days + 1
    chunk_days = max(1, (_MAX_BARS_PER_REQUEST * to_minutes(tf_name)) // _MINUTES_PER_DAY)
    if span_days <= chunk_days:
        return [(start_date, end_date)]

    windows: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        stop = min(cursor + _dt.timedelta(days=chunk_days - 1), end)
        windows.append((cursor.isoformat(), stop.isoformat()))
        cursor = stop + _dt.timedelta(days=1)
    return windows


def _read_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8"))
        # mt5_error is the terminal's own code — the difference between "this symbol has no
        # history" and "you asked for more bars than the terminal will serve in one call".
        detail = body.get("error", str(body))
        mt5_error = body.get("mt5_error")
        return f"{detail} [mt5: {mt5_error}]" if mt5_error else detail
    except Exception:
        return exc.reason or "unknown"
