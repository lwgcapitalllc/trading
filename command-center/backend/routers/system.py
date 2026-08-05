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
from services import runner_dispatch, mt5_agent_client, agent_supervisor
from services.backtest_runner import read_progress, clear_progress

import config as cfg

router = APIRouter(tags=["system"])

# ── In-memory caches ───────────────────────────────────────────────────────────

_health_cache: Optional[dict] = None
_health_cache_at: float = 0.0
_HEALTH_TTL = 10  # seconds

_vps_ok: Optional[bool] = None
_vps_checked_at: float = 0.0
_VPS_TTL = 30  # seconds


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── VPS reachability (NOT the tunnel — see below) ──────────────────────────────

def _check_vps() -> bool:
    """Cached `ssh forexvps echo ok`.

    ⚠ This is a BRAND NEW connection and says nothing about the port forwards.
    Until 2026-08-02 it was what the "SSH" dot reported, so the dot could sit
    green with a dead tunnel and two red agents — which sends you looking at the
    VPS when the problem is on this laptop. The tunnel is now measured directly
    (`agent_supervisor.tunnel_up`, port binding) and this answers the separate
    question of whether the VPS is reachable at all, which is what tells a dead
    tunnel apart from a dead network.
    """
    global _vps_ok, _vps_checked_at
    now = time.time()
    if _vps_ok is not None and (now - _vps_checked_at) < _VPS_TTL:
        return _vps_ok
    _vps_ok = agent_supervisor.vps_reachable()
    _vps_checked_at = now
    return _vps_ok


# ── Health aggregation ─────────────────────────────────────────────────────────

def _build_health() -> dict:
    tunnel_ok = agent_supervisor.tunnel_up()
    vps_ok_host = _check_vps()

    vps_ok = False
    mt5_ok = False
    mt5_connected: Optional[bool] = None
    mt5_server: Optional[str] = None
    mt5_account: Optional[int] = None
    nt8_running = False
    nt8_sa_visible = False
    last_compile_ok = False
    last_compile_at = None
    last_compile_errors: list[str] = []

    try:
        h = runner_dispatch.health()
        vps_ok = h.get("status") == "ok"
    except Exception:
        pass

    try:
        h5 = mt5_agent_client.health()
        mt5_ok = h5.get("status") == "ok"
    except Exception:
        pass

    if mt5_ok:
        # An agent that answers /health is not the same as a terminal that can
        # serve bars. Left unasked until 2026-08-02, so an MT5_Lab that had
        # dropped its broker connection showed green and failed at fetch time.
        # `None` stays None when the call fails — an unanswered question is not
        # a disconnected terminal.
        st = agent_supervisor.mt5_terminal_status()
        if st is not None:
            mt5_connected = st["connected"]
            mt5_server = st["server"]
            mt5_account = st["account"]

    if vps_ok:
        try:
            nth = runner_dispatch.nt_health()
            nt8_running    = bool(nth.get("nt8_running") or nth.get("nt_running"))
            nt8_sa_visible = bool(nth.get("sa_visible"))
        except Exception:
            pass

        try:
            cs = runner_dispatch.nt_compile_status()
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
        "ssh_tunnel":           tunnel_ok,
        "vps_reachable":        vps_ok_host,
        "nt8_agent":            vps_ok,
        "mt5_agent":            mt5_ok,
        "mt5_connected":        mt5_connected,
        "mt5_server":           mt5_server,
        "mt5_account":          mt5_account,
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
                runner_dispatch.cancel_job(job_id)
                stopped = True
            except Exception:
                pass
        clear_progress()
    return {"stopped": stopped, "job_id": job_id}


# `_restart_tunnel` and `_schtasks_run` moved to services/agent_supervisor.py on
# 2026-08-02. They are subprocess calls, which the layering rules put in
# services/ — and main.py was reaching ACROSS into this router to call one,
# which is how a second copy would eventually appear. These aliases stay so the
# manual dot-click path reads the same as it always did.
_restart_tunnel = agent_supervisor.restart_tunnel


def _schtasks_run(task_name: str) -> dict:
    try:
        return agent_supervisor.schtasks_run(task_name)
    except agent_supervisor.SchtaskError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


def _start_agent(task_name: str) -> dict:
    """Rebuild the tunnel, then fire the agent's task.

    The tunnel restart is not belt-and-braces: an `ssh -N -L` can survive
    holding both ports while forwarding into a dead agent, so restarting the
    agent alone leaves the dot red and looks like the click did nothing.
    """
    global _health_cache
    _restart_tunnel()
    out = _schtasks_run(task_name)
    _health_cache = None
    return out


@router.post("/system/nt8-agent/start")
def start_nt8_agent():
    """Restart SSH tunnel (ports 8765 + 8766) and fire the NT8 agent scheduled task."""
    return _start_agent(agent_supervisor.NT8_TASK)


@router.post("/system/mt5-agent/start")
def start_mt5_agent():
    """Restart SSH tunnel (ports 8765 + 8766) and fire the MT5 agent scheduled task."""
    return _start_agent(agent_supervisor.MT5_TASK)


@router.get("/system/activity")
def system_activity() -> dict:
    """Three booleans for the sidebar's running-dots: `{backtests, optimizations, stress_tests}`.

    The sidebar used to derive these client-side from the FULL runs / optimizations / stress-test
    lists, which it therefore polled on every page in the app — a ~137 KB response at 81 runs, two
    thirds of it strategy params, to decide whether to draw three dots.
    """
    from services import lab_db
    return lab_db.get_nav_activity()


@router.get("/system/readiness")
def system_readiness() -> dict:
    """The silently-degrading dependencies — news calendar cache, Telegram credentials.

    Reported at startup too; this endpoint exists so the answer is reachable
    without going back through the log.
    """
    from services import readiness
    return {"warnings": readiness.check(), "checked_at": _now_iso()}


@router.get("/nt8/agent/log", response_class=PlainTextResponse)
def nt8_agent_log(lines: int = 200) -> str:
    try:
        return runner_dispatch.agent_log(lines=lines)
    except Exception as exc:
        raise HTTPException(502, f"NT8 agent unreachable: {exc}")


@router.get("/nt8/nt/log", response_class=PlainTextResponse)
def nt8_nt_log(lines: int = 200) -> str:
    try:
        return runner_dispatch.nt_log(lines=lines)
    except Exception as exc:
        raise HTTPException(502, f"NT8 agent unreachable: {exc}")
