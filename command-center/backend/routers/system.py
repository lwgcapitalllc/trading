"""
System router — /system/health, /lab/progress, /lab/stop, /nt8/* log proxies.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from models import SystemHealth, LabProgress
from services import nt8_agent_client, mt5_agent_client
from services.backtest_runner import read_progress, clear_progress

import config as cfg

router = APIRouter(tags=["system"])

# ── In-memory caches ───────────────────────────────────────────────────────────

_health_cache: Optional[dict] = None
_health_cache_at: float = 0.0
_HEALTH_TTL = 10  # seconds

_ssh_ok: Optional[bool] = None
_ssh_checked_at: float = 0.0
_SSH_TTL = 30  # seconds


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── SSH tunnel check ───────────────────────────────────────────────────────────

def _check_ssh() -> bool:
    global _ssh_ok, _ssh_checked_at
    now = time.time()
    if _ssh_ok is not None and (now - _ssh_checked_at) < _SSH_TTL:
        return _ssh_ok
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes",
             cfg.SSH_ALIAS, "echo ok"],
            capture_output=True, text=True, timeout=5,
        )
        _ssh_ok = result.returncode == 0 and "ok" in result.stdout
    except Exception:
        _ssh_ok = False
    _ssh_checked_at = now
    return _ssh_ok


# ── Health aggregation ─────────────────────────────────────────────────────────

def _build_health() -> dict:
    ssh_ok = _check_ssh()

    vps_ok = False
    mt5_ok = False
    nt8_running = False
    nt8_sa_visible = False
    last_compile_ok = False
    last_compile_at = None
    last_compile_errors: list[str] = []

    try:
        h = nt8_agent_client.health()
        vps_ok = h.get("status") == "ok"
    except Exception:
        pass

    try:
        h5 = mt5_agent_client.health()
        mt5_ok = h5.get("status") == "ok"
    except Exception:
        pass

    if vps_ok:
        try:
            nth = nt8_agent_client.nt_health()
            nt8_running    = bool(nth.get("nt8_running") or nth.get("nt_running"))
            nt8_sa_visible = bool(nth.get("sa_visible"))
        except Exception:
            pass

        try:
            cs = nt8_agent_client.nt_compile_status()
            ok = cs.get("ok")
            last_compile_ok = bool(ok) if ok is not None else False
            last_compile_at = cs.get("at") or cs.get("checked_at")
            if isinstance(last_compile_at, (int, float)):
                last_compile_at = datetime.fromtimestamp(
                    last_compile_at, tz=timezone.utc
                ).isoformat()
            last_compile_errors = cs.get("errors", [])
        except Exception:
            pass

    return {
        "backend":              True,
        "ssh_tunnel":           ssh_ok,
        "nt8_agent":            vps_ok,
        "mt5_agent":            mt5_ok,
        "nt8_running":          nt8_running,
        "nt8_sa_visible":       nt8_sa_visible,
        "last_compile_ok":      last_compile_ok,
        "last_compile_at":      last_compile_at,
        "last_compile_errors":  last_compile_errors,
        "checked_at":           _now_iso(),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/system/health", response_model=SystemHealth)
def system_health() -> SystemHealth:
    global _health_cache, _health_cache_at
    now = time.time()
    if _health_cache is not None and (now - _health_cache_at) < _HEALTH_TTL:
        return SystemHealth(**_health_cache)
    data = _build_health()
    _health_cache = data
    _health_cache_at = now
    return SystemHealth(**data)


@router.get("/lab/progress", response_model=LabProgress)
def lab_progress() -> LabProgress:
    raw = read_progress()
    # compute heartbeat_age if there's an updated_at
    try:
        updated_at = float(raw.get("updated_at", 0))
        raw["heartbeat_age_seconds"] = time.time() - updated_at if updated_at else 0.0
    except Exception:
        raw["heartbeat_age_seconds"] = 0.0
    return LabProgress(**{
        k: raw.get(k)
        for k in LabProgress.model_fields
    })


@router.post("/lab/stop")
def lab_stop() -> dict:
    raw = read_progress()
    job_id = raw.get("job_id")
    stopped = False
    if raw.get("status") == "running":
        if job_id:
            try:
                nt8_agent_client.cancel_job(job_id)
                stopped = True
            except Exception:
                pass
        clear_progress()
    return {"stopped": stopped, "job_id": job_id}


def _restart_tunnel() -> None:
    """Kill any stale ssh -N tunnel and spawn a fresh one with both port forwards."""
    subprocess.run(["pkill", "-f", r"ssh -N.*forexvps"], capture_output=True)
    subprocess.Popen(
        ["ssh", "-N",
         "-L", "8765:127.0.0.1:8765",
         "-L", "8766:127.0.0.1:8766",
         "-o", "ServerAliveInterval=30",
         "-o", "ServerAliveCountMax=3",
         cfg.SSH_ALIAS],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(2)  # let the port-forwards establish before first use


def _schtasks_run(task_name: str) -> dict:
    """Fire a Windows scheduled task via SSH. Returns {status, output}."""
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
             cfg.SSH_ALIAS, f"schtasks /run /tn {task_name}"],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="SSH timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    if result.returncode != 0:
        raise HTTPException(status_code=502, detail=f"schtasks failed: {result.stderr.strip()}")
    return {"status": "ok", "output": result.stdout.strip()}


@router.post("/system/nt8-agent/start")
def start_nt8_agent():
    """Restart SSH tunnel (ports 8765 + 8766) and fire the NT8 agent scheduled task."""
    global _health_cache
    _restart_tunnel()
    out = _schtasks_run("LucidFlexAgent")
    _health_cache = None
    return out


@router.post("/system/mt5-agent/start")
def start_mt5_agent():
    """Restart SSH tunnel (ports 8765 + 8766) and fire the MT5 agent scheduled task."""
    global _health_cache
    _restart_tunnel()
    out = _schtasks_run("MT5AgentRDP")
    _health_cache = None
    return out


@router.get("/nt8/agent/log", response_class=PlainTextResponse)
def nt8_agent_log(lines: int = 200) -> str:
    try:
        return nt8_agent_client.agent_log(lines=lines)
    except Exception as exc:
        raise HTTPException(502, f"NT8 agent unreachable: {exc}")


@router.get("/nt8/nt/log", response_class=PlainTextResponse)
def nt8_nt_log(lines: int = 200) -> str:
    try:
        return nt8_agent_client.nt_log(lines=lines)
    except Exception as exc:
        raise HTTPException(502, f"NT8 agent unreachable: {exc}")
