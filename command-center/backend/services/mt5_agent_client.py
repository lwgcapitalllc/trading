"""
Typed HTTP wrapper over the MT5 agent (http://localhost:8766 via SSH tunnel).

Symmetric to the NT8-agent calls in runner_dispatch.py. All outbound calls to the
MT5 agent go through this module. runner_dispatch._resolve_runner() picks this
client vs the NT8 path based on strategy.runner.

MT5 agent URL shape differs from NT8 agent:
    NT8:  POST /backtest        GET /jobs/{id}/status    GET /jobs/{id}/results
    MT5:  POST /backtests       GET /backtests/{id}      GET /backtests/{id}/results
This module abstracts that difference — callers in runner_dispatch see identical signatures.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
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


def status() -> dict:
    """MT5 TERMINAL status — a different question from health().

    `/health` answers "is the Flask agent alive", which it is whether or not MT5
    is running or logged in. `/status` answers "is the terminal actually usable":
    `mt5_connected`, plus the account and server it is bound to. Every python
    backtest that needs uncached bars goes through this terminal, so an agent
    that responds while the terminal is disconnected is a run that will fail at
    fetch time with a green dot above it.
    """
    return _get("/status", timeout=8)


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


def start_native_optimization(opt_spec: dict) -> dict:
    """POST /native-optimize — run MT5 Strategy Tester in optimization mode."""
    return _post("/native-optimize", opt_spec, timeout=30)


def native_opt_results(job_id: str) -> dict:
    """GET /backtests/{job_id}/native-opt-results — fetch optimization combos after completion."""
    return _get(f"/backtests/{job_id}/native-opt-results")


def start_native_walkforward(wf_spec: dict) -> dict:
    """POST /native-walkforward — run MT5 Strategy Tester in forward (IS+OOS) mode."""
    return _post("/native-walkforward", wf_spec, timeout=30)


def native_wf_results(job_id: str) -> dict:
    """GET /backtests/{job_id}/native-wf-results — fetch IS/OOS forward results after completion."""
    return _get(f"/backtests/{job_id}/native-wf-results")


# ── Historical data ───────────────────────────────────────────────────────────


def get_historical_data(symbol: str, timeframe: str, start_date: str, end_date: str) -> dict:
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


# ── Strategy file management ───────────────────────────────────────────────────


def list_strategy_files() -> list[dict]:
    """GET /files/strategies — list .mq5/.ex5 in MT5 Experts folder."""
    return _get("/files/strategies")


def upload_strategy_file(filename: str, content: bytes, overwrite: bool) -> dict:
    """POST /files/strategies/<filename> — upload a .mq5 file (multipart)."""
    url = cfg.MT5_AGENT_TUNNEL.rstrip("/") + f"/files/strategies/{filename}"
    boundary = uuid.uuid4().hex
    body_parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode(),
        content,
        f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\n'
        f"{'true' if overwrite else 'false'}\r\n--{boundary}--\r\n".encode(),
    ]
    req = urllib.request.Request(
        url,
        data=b"".join(body_parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"MT5 upload {filename}: HTTP {exc.code} — {exc.read().decode()}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"MT5 upload {filename}: {exc}") from exc


def _delete_one(filename: str) -> dict:
    """DELETE /files/strategies/<filename> — delete a single .mq5 or .ex5 file."""
    url = cfg.MT5_AGENT_TUNNEL.rstrip("/") + f"/files/strategies/{filename}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"MT5 delete {filename}: HTTP {exc.code} — {exc.read().decode()}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"MT5 delete {filename}: {exc}") from exc


def delete_strategy_file(filename: str) -> dict:
    """Delete an MT5 strategy's whole footprint: BOTH the .mq5 source and its compiled
    .ex5 binary. MT5 loads the .ex5, and it outlives its source — deleting only the
    .mq5 leaves the strategy showing in the Navigator and Strategy Tester. So we remove
    both siblings. An already-absent sibling (HTTP 404) is fine; we only fail on a real
    error, or if neither file existed (surfaced as 404 so the caller treats it as
    already-gone)."""
    stem = filename.rsplit(".", 1)[0]
    deleted: list[str] = []
    errors: list[str] = []
    for name in (f"{stem}.mq5", f"{stem}.ex5"):
        try:
            _delete_one(name)
            deleted.append(name)
        except RuntimeError as exc:
            msg = str(exc)
            if "HTTP 404" in msg or "not found" in msg.lower():
                continue  # already gone — fine
            errors.append(msg)
    if errors:
        raise RuntimeError("; ".join(errors))
    if not deleted:
        raise RuntimeError(f"MT5 delete {stem}: HTTP 404 — no .mq5 or .ex5 found")
    return {"ok": True, "deleted": deleted}


def trigger_compile() -> dict:
    """POST /compile — trigger MetaEditor to compile all .mq5 files in Experts folder."""
    return _post("/compile", timeout=15)


def get_compile_status(compile_job_id: str) -> dict:
    """GET /compile/<id> — poll MetaEditor compile job status."""
    return _get(f"/compile/{compile_job_id}")
