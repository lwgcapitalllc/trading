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
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .cache import _normalize

_DEFAULT_BASE_URL = "http://localhost:8766"


class Mt5AgentError(RuntimeError):
    """The MT5 agent was unreachable or returned an error / no data."""


class Mt5Agent:
    """Fetches OHLC bars from the MT5 agent over HTTP."""

    def __init__(self, base_url: str = _DEFAULT_BASE_URL, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = _read_error(exc)
            raise Mt5AgentError(
                f"MT5 agent {exc.code} for {symbol} {tf_name} "
                f"[{start_date}, {end_date}]: {detail}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise Mt5AgentError(
                f"MT5 agent unreachable at {self.base_url} "
                f"(is the SSH tunnel up?): {exc}"
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


def _read_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(exc.read().decode("utf-8"))
        return body.get("error", str(body))
    except Exception:
        return exc.reason or "unknown"
