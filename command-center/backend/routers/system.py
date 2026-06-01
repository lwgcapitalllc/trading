"""
System router — /system/health, /lab/progress, /lab/stop, /vps/* log proxies.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from models import SystemHealth, LabProgress
from services import vps_client
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
    nt8_running = False
    nt8_sa_visible = False
    last_compile_ok = False
    last_compile_at = None
    last_compile_errors: list[str] = []

    try:
        h = vps_client.health()
        vps_ok = h.get("status") == "ok"
    except Exception:
        pass

    if vps_ok:
        try:
            nth = vps_client.nt_health()
            nt8_running    = bool(nth.get("nt8_running") or nth.get("nt_running"))
            nt8_sa_visible = bool(nth.get("sa_visible"))
        except Exception:
            pass

        try:
            cs = vps_client.nt_compile_status()
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
        "vps_agent":            vps_ok,
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
                vps_client.cancel_job(job_id)
                stopped = True
            except Exception:
                pass
        clear_progress()
    return {"stopped": stopped, "job_id": job_id}


@router.post("/system/vps-agent/start")
def start_vps_agent():
    """Reconnect the SSH port-forward tunnel and restart vps_agent on the VPS.

    After laptop sleep the ssh -N tunnel process dies, breaking localhost:8765
    even though SSH itself still works. This endpoint kills the stale tunnel,
    spawns a fresh one, then fires the LucidFlexAgent scheduled task.
    """
    global _health_cache

    # Kill any stale tunnel process and spawn a fresh one.
    subprocess.run(["pkill", "-f", r"ssh -N.*forexvps"], capture_output=True)
    subprocess.Popen(
        ["ssh", "-N",
         "-o", "ServerAliveInterval=30",
         "-o", "ServerAliveCountMax=3",
         cfg.SSH_ALIAS],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Give the tunnel a moment to establish the port-forward before we use it.
    time.sleep(2)

    # Fire the scheduled task to (re)start vps_agent.py on the VPS.
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
             cfg.SSH_ALIAS, "schtasks /run /tn LucidFlexAgent"],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="SSH timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    if result.returncode != 0:
        raise HTTPException(status_code=502, detail=f"schtasks failed: {result.stderr.strip()}")
    _health_cache = None
    return {"status": "ok", "output": result.stdout.strip()}


@router.get("/vps/agent/log", response_class=PlainTextResponse)
def vps_agent_log(lines: int = 200) -> str:
    try:
        return vps_client.agent_log(lines=lines)
    except Exception as exc:
        raise HTTPException(502, f"VPS agent unreachable: {exc}")


@router.get("/vps/nt/log", response_class=PlainTextResponse)
def vps_nt_log(lines: int = 200) -> str:
    try:
        return vps_client.nt_log(lines=lines)
    except Exception as exc:
        raise HTTPException(502, f"VPS agent unreachable: {exc}")
