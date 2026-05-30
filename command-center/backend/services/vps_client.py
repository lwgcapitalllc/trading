"""
Typed HTTP wrapper over the VPS agent (http://localhost:8765 via SSH tunnel).
All outbound calls to the agent go through this module.
"""

from __future__ import annotations

from typing import Any, Optional
import urllib.request
import urllib.error
import json

import config as cfg

_TIMEOUT = 10  # seconds for all agent calls


def _get(path: str, timeout: int = _TIMEOUT) -> dict:
    url = cfg.VPS_AGENT_TUNNEL.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        raise RuntimeError(f"VPS agent {path}: {exc}") from exc


def _post(path: str, body: Optional[dict] = None, timeout: int = _TIMEOUT) -> dict:
    url = cfg.VPS_AGENT_TUNNEL.rstrip("/") + path
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        raise RuntimeError(f"VPS agent POST {path}: {exc}") from exc


# ── Observability ─────────────────────────────────────────────────────────────

def health() -> dict:
    return _get("/health", timeout=5)


def nt_health() -> dict:
    return _get("/nt-health", timeout=8)


def nt_compile_status() -> dict:
    return _get("/nt-compile-status", timeout=8)


def agent_log(lines: int = 100) -> str:
    try:
        data = _get(f"/agent-log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


def nt_log(lines: int = 100) -> str:
    try:
        data = _get(f"/nt-log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


# ── Job control ───────────────────────────────────────────────────────────────

def start_backtest(job_spec: dict) -> dict:
    return _post("/backtest", job_spec, timeout=30)


def job_status(job_id: str) -> dict:
    return _get(f"/jobs/{job_id}/status")


def job_results(job_id: str) -> dict:
    return _get(f"/jobs/{job_id}/results")


def job_log(job_id: str, lines: int = 200) -> str:
    try:
        data = _get(f"/jobs/{job_id}/log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


def cancel_job(job_id: str) -> dict:
    return _post(f"/jobs/{job_id}/cancel")


def export_trades() -> dict:
    """Call /export-trades on the VPS agent. Returns {ok, csv, total_lines, log}.
    Longer timeout because the export automation takes ~12-15s."""
    return _get("/export-trades", timeout=60)
