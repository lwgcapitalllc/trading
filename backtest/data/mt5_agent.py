"""Thin HTTP client over the VPS MT5 agent (algos/markets/fx/tools/mt5_agent.py).

Reads broker bars from the agent's GET /historical_data endpoint, reachable on
localhost:8766 via the SSH tunnel that command-center's start.sh opens. Stdlib
only (urllib) so the backtest package stays dependency-light and importable
anywhere. This is a data reader, not a second agent — the agent stays canonical.

Tick history (2yr deep on this broker) will back the fill model, but the agent
has no /ticks endpoint yet; adding one is A2 work, not A0.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .cache import _normalize

_DEFAULT_BASE_URL = "http://localhost:8766"

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

        Returns the canonical bar frame (DatetimeIndex 'time' + OHLC). Raises
        Mt5AgentError if the agent is down or serves no data for the request.
        """
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


def _read_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8"))
        return body.get("error", str(body))
    except Exception:
        return exc.reason or "unknown"
