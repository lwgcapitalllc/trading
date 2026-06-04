"""
Typed HTTP wrapper over the MT5 agent (http://localhost:8766 via SSH tunnel).

Symmetric to the NT8-agent calls in vps_client.py. All outbound calls to the
MT5 agent go through this module. vps_client._resolve_runner() picks this
client vs the NT8 path based on strategy.runner.

MT5 agent URL shape differs from NT8 agent:
    NT8:  POST /backtest        GET /jobs/{id}/status    GET /jobs/{id}/results
    MT5:  POST /backtests       GET /backtests/{id}      GET /backtests/{id}/results
This module abstracts that difference — callers in vps_client see identical signatures.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

import config as cfg

_TIMEOUT = 10


def _get(path: str, timeout: int = _TIMEOUT) -> dict:
    url = cfg.MT5_AGENT_TUNNEL.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        raise RuntimeError(f"MT5 agent {path}: {exc}") from exc


def _post(path: str, body: Optional[dict] = None, timeout: int = _TIMEOUT) -> dict:
    url = cfg.MT5_AGENT_TUNNEL.rstrip("/") + path
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        raise RuntimeError(f"MT5 agent POST {path}: {exc}") from exc


# ── Observability ──────────────────────────────────────────────────────────────

def health() -> dict:
    return _get("/health", timeout=5)


def agent_log(lines: int = 100) -> str:
    try:
        data = _get(f"/agent-log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


# ── Job control ────────────────────────────────────────────────────────────────

def start_backtest(job_spec: dict) -> dict:
    """POST /backtests — submit a backtest job to the MT5 agent."""
    return _post("/backtests", job_spec, timeout=30)


def job_status(job_id: str) -> dict:
    """GET /backtests/{job_id} — poll job state."""
    return _get(f"/backtests/{job_id}")


def job_results(job_id: str) -> dict:
    """GET /backtests/{job_id}/results — fetch completed results."""
    return _get(f"/backtests/{job_id}/results")


def job_log(job_id: str, lines: int = 200) -> str:
    """GET /backtests/{job_id}/log — tail job log."""
    try:
        data = _get(f"/backtests/{job_id}/log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


def cancel_job(job_id: str) -> dict:
    """POST /jobs/{job_id}/cancel — cancel a running job."""
    return _post(f"/jobs/{job_id}/cancel")


# ── Historical data ───────────────────────────────────────────────────────────

def get_historical_data(
    symbol: str, timeframe: str, start_date: str, end_date: str
) -> dict:
    """GET /historical_data — fetch OHLC bars from MT5 agent.

    Returns {"bars": [{"time": ISO, "open": f, "high": f, "low": f, "close": f}, ...],
             "symbol": str, "timeframe": str, "count": int}.
    Raises RuntimeError if the agent is unreachable or returns an error.
    """
    path = (
        f"/historical_data?symbol={symbol}&timeframe={timeframe}"
        f"&start_date={start_date}&end_date={end_date}"
    )
    return _get(path, timeout=30)


# ── Strategy file management (Step 9) ─────────────────────────────────────────

def list_strategy_files() -> list[dict]:
    """GET /files/strategies — list .mq5/.ex5 in MT5 Experts folder."""
    return _get("/files/strategies")
