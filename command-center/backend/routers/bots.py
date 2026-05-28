"""
Bots router — /bots/*

Read endpoints:
  GET  /bots/snapshot                  — full VPS state via batched SSH
  GET  /bots/{bot_name}/log            — last N lines of stdout log

Global control actions (all bots):
  POST /bots/start                     — run SYS_STARTUP task
  POST /bots/stop                      — delete lock + taskkill python.exe
  POST /bots/restart                   — stop + 3s + start
  POST /bots/emergency                 — immediate taskkill, no cleanup

Per-bot control actions:
  POST /bots/{bot_name}/start          — schtasks /run /tn {task_name}
  POST /bots/{bot_name}/stop           — wmic terminate by commandline match
  POST /bots/{bot_name}/restart        — per-bot stop + 3s + start
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

import config as cfg
from models import BotSnapshot, BotStatus, JobStatus, ProcessStatus

router = APIRouter(prefix="/bots", tags=["bots"])

VPS_HOST = cfg.SSH_ALIAS

# Mirror algo.py's constants so behaviour matches the retired panel exactly.
_BOT_DISPLAY_ORDER = [
    "BOT_SMC_TREND", "BOT_MEAN_REVERSION", "BOT_SCALPER", "BOT_FFT",
]
_DISPLAY_NAMES = {
    "BOT_SMC_TREND":      "SMC Trend",
    "BOT_MEAN_REVERSION": "Mean Reversion",
    "BOT_SCALPER":        "Scalper",
    "BOT_FFT":            "FFT",
    "SYS_TELEGRAM":       "Telegram",
    "SYS_REPORTER":       "Reporter",
    "SYS_MONITOR":        "Monitor",
    "SYS_PNLTRACKER":     "P&L Tracker",
}
_TASK_BOT_KEYS = {
    "BOT_SMC_TREND":      "smc_trend",
    "BOT_MEAN_REVERSION": "mean_reversion",
    "BOT_SCALPER":        "scalper",
    "BOT_FFT":            "fft",
}
_TASK_ACCT_TYPE = {
    "BOT_SMC_TREND":      "demo",
    "BOT_MEAN_REVERSION": "demo",
    "BOT_SCALPER":        "demo",
    "BOT_FFT":            "demo",
}
_LOG_MAP = {
    "BOT_SMC_TREND":      ("fx", "gold_main",    "smc_trend_stdout.log"),
    "BOT_MEAN_REVERSION": ("fx", "gold_main",    "mean_reversion_stdout.log"),
    "BOT_SCALPER":        ("fx", "gold_scalper", "scalper_stdout.log"),
    "BOT_FFT":            ("fx", "gold_fft",     "fft_stdout.log"),
}
_SCHEDULED_JOBS = [
    JobStatus(name="Monitor",     schedule="every 1 min",  status="UNKNOWN"),
    JobStatus(name="P&L Tracker", schedule="every 1 min",  status="UNKNOWN"),
    JobStatus(name="Reporter",    schedule="daily 4pm CT", status="UNKNOWN"),
]


def _ssh(cmd: str) -> str:
    result = subprocess.run(
        ["ssh", VPS_HOST, cmd],
        capture_output=True, timeout=30,
    )
    # Windows stdout is cp1252; decode with replacement so non-UTF-8 chars
    # (arrows, dashes, degree signs) don't raise UnicodeDecodeError → 500.
    return result.stdout.decode("utf-8", errors="replace").strip()


def _parse_sections(raw: str, initial_section: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current = initial_section
    buf: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("===") and stripped.endswith("==="):
            sections[current] = "\n".join(buf).strip()
            current = stripped.strip("=").strip().lower().replace(" ", "_")
            buf = []
        else:
            buf.append(line)
    sections[current] = "\n".join(buf).strip()
    return sections


def _fetch_vps_snapshot() -> dict[str, str]:
    """Single batched VPS fetch — replicates algo.py's fetch_vps_snapshot()."""
    cmd1 = (
        "wmic process where \"name='python.exe'\" get commandline /format:list 2>nul"
        " & echo ===TASKS==="
        " & schtasks /query /fo CSV /nh 2>nul"
    )
    sections = _parse_sections(_ssh(cmd1), "procs")

    instances_base = "C:\\trading\\algos\\markets\\fx\\instances"
    cmd2 = (
        f"if exist {instances_base}\\gold_main\\bot_state.json"
        f" (type {instances_base}\\gold_main\\bot_state.json)"
        " & echo. & echo ===STATE_SCALPER==="
        f" & if exist {instances_base}\\gold_scalper\\bot_state.json"
        f" (type {instances_base}\\gold_scalper\\bot_state.json)"
        " & echo. & echo ===STATE_FFT==="
        f" & if exist {instances_base}\\gold_fft\\bot_state.json"
        f" (type {instances_base}\\gold_fft\\bot_state.json)"
        " & echo. & echo ===TELEGRAM_START==="
        " & if exist C:\\trading\\algos\\telegram_start.json"
        " (type C:\\trading\\algos\\telegram_start.json)"
    )
    sections.update(_parse_sections(_ssh(cmd2), "state_main"))
    return sections


def _parse_bot_states(snap: dict[str, str]) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for section, keys in [
        ("state_main",    ["smc_trend", "mean_reversion"]),
        ("state_scalper", ["scalper"]),
        ("state_fft",     ["fft"]),
    ]:
        raw = snap.get(section, "")
        if not raw:
            continue
        try:
            data = json.loads(raw)
            for k in keys:
                if k in data:
                    states[k] = data[k]
        except Exception:
            pass
    return states


def _parse_tasks(snap: dict[str, str]) -> dict[str, str]:
    """Return {task_name: status} from schtasks CSV."""
    tasks: dict[str, str] = {}
    for line in snap.get("tasks", "").splitlines():
        parts = line.split(",")
        if len(parts) < 3:
            continue
        name = parts[0].strip('"')
        status = parts[2].strip('"')
        if name in _DISPLAY_NAMES:
            tasks[name] = status
    return tasks


def _is_python_running(snap: dict[str, str], script_fragment: str) -> bool:
    return script_fragment.lower() in snap.get("procs", "").lower()


def _uptime_seconds(state: dict) -> int | None:
    started = state.get("started_at") or state.get("start_time")
    if not started:
        return None
    try:
        start = datetime.fromisoformat(started).replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - start).total_seconds())
    except Exception:
        return None


@router.get("/snapshot", response_model=BotSnapshot)
def get_snapshot():
    try:
        snap = _fetch_vps_snapshot()
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS fetch failed: {e}")

    bot_states = _parse_bot_states(snap)
    task_statuses = _parse_tasks(snap)
    now = datetime.now(timezone.utc)

    bots: list[BotStatus] = []
    for task_name in _BOT_DISPLAY_ORDER:
        bot_key = _TASK_BOT_KEYS.get(task_name, "")
        state = bot_states.get(bot_key, {})
        task_status = task_statuses.get(task_name, "")

        # Derive status from task scheduler + process list
        script_hint = bot_key.replace("_", "")
        running_in_procs = _is_python_running(snap, bot_key)
        if task_status == "Running" or running_in_procs:
            status = "RUNNING"
        elif task_status in ("Ready", ""):
            status = "STOPPED"
        else:
            status = state.get("status", "STOPPED").upper()

        pnl = state.get("daily_pnl_pct") or state.get("daily_pnl")
        if pnl is not None:
            try:
                pnl = float(pnl)
            except Exception:
                pnl = None

        bots.append(BotStatus(
            name=_DISPLAY_NAMES.get(task_name, task_name),
            account=state.get("account", ""),
            account_type=_TASK_ACCT_TYPE.get(task_name, "demo"),
            balance=state.get("balance"),
            status=status,
            uptime_seconds=_uptime_seconds(state) if status == "RUNNING" else None,
            daily_pnl_pct=pnl,
            day_locked=bool(state.get("day_locked", False)),
        ))

    # Scheduled jobs
    jobs: list[JobStatus] = []
    for job in _SCHEDULED_JOBS:
        task_key = {"Monitor": "SYS_MONITOR", "P&L Tracker": "SYS_PNLTRACKER",
                    "Reporter": "SYS_REPORTER"}.get(job.name)
        t_status = task_statuses.get(task_key, "") if task_key else ""
        status = "RUNNING" if t_status == "Running" else ("STOPPED" if t_status else "UNKNOWN")
        jobs.append(JobStatus(name=job.name, schedule=job.schedule, status=status))

    # Telegram
    tg_raw = snap.get("telegram_start", "")
    tg_status = "UNKNOWN"
    if tg_raw:
        try:
            tg_data = json.loads(tg_raw)
            tg_status = "RUNNING" if tg_data.get("running") else "STOPPED"
        except Exception:
            pass
    if _is_python_running(snap, "telegram"):
        tg_status = "RUNNING"

    telegram = ProcessStatus(name="Telegram", status=tg_status)

    return BotSnapshot(fetched_at=now, bots=bots, scheduled_jobs=jobs, telegram=telegram)


@router.get("/{bot_name}/log", response_class=PlainTextResponse)
def get_bot_log(bot_name: str, lines: int = 500):
    """Read the last N lines of a bot's stdout log over SSH."""
    # Find task name matching bot_name (display name)
    task_name = next(
        (t for t, dn in _DISPLAY_NAMES.items() if dn.lower() == bot_name.lower()),
        None,
    )
    if not task_name or task_name not in _LOG_MAP:
        raise HTTPException(status_code=404, detail=f"No log mapping for bot '{bot_name}'")

    _, instance, log_file = _LOG_MAP[task_name]
    log_path = f"C:\\trading\\algos\\markets\\fx\\instances\\{instance}\\{log_file}"

    try:
        raw = _ssh(f"type {log_path} 2>nul")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")

    if not raw:
        return f"Log file not found or empty: {log_path}"

    log_lines = raw.splitlines()
    return "\n".join(log_lines[-lines:])


# ── Control actions ───────────────────────────────────────────────────────────
#
# All actions run over SSH.  Sequence mirrors the VPS deploy workflow in CLAUDE.md:
#   stop  = delete lock file + taskkill all python.exe
#   start = run SYS_STARTUP scheduled task
#   restart = stop then start (with a 3-second gap)
#   emergency = immediate taskkill, no lock delete (fastest path)
#
# Each endpoint returns { "status": "ok"|"error", "output": "<ssh stdout>" }.
# A 502 is raised when the SSH call itself fails or times out.

_LOCK_PATH  = r"C:\trading\algos\mt5_connect.lock"
_STARTUP_TN = "SYS_STARTUP"


def _stop_procs() -> str:
    """Kill lock file + all python.exe processes.  Returns combined SSH output."""
    out = _ssh(f"del {_LOCK_PATH} 2>nul & taskkill /f /im python.exe 2>nul")
    return out


def _start_task() -> str:
    """Fire SYS_STARTUP scheduled task.  Returns SSH output."""
    return _ssh(f"schtasks /run /tn {_STARTUP_TN}")


@router.post("/start")
def start_bots():
    """Run the SYS_STARTUP scheduled task on the VPS."""
    try:
        out = _start_task()
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    return {"status": "ok", "output": out}


@router.post("/stop")
def stop_bots():
    """Delete the MT5 lock file and kill all python.exe processes on the VPS."""
    try:
        out = _stop_procs()
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    return {"status": "ok", "output": out}


@router.post("/restart")
def restart_bots():
    """Stop all bots, wait 3 s, then run SYS_STARTUP."""
    import time
    try:
        stop_out = _stop_procs()
        time.sleep(3)
        start_out = _start_task()
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    return {"status": "ok", "output": f"{stop_out}\n{start_out}".strip()}


@router.post("/emergency")
def emergency_stop():
    """Immediate taskkill of all python.exe — no lock-file cleanup."""
    try:
        out = _ssh("taskkill /f /im python.exe 2>nul")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    return {"status": "ok", "output": out}


# ── Per-bot control actions ───────────────────────────────────────────────────
#
# Routes registered AFTER the literal /start|stop|restart|emergency paths so
# FastAPI matches the literals first (no ambiguity).

def _resolve_bot(bot_name: str) -> tuple[str, str]:
    """Return (task_name, bot_key) for a display-name, or raise 404."""
    task_name = next(
        (t for t, dn in _DISPLAY_NAMES.items() if dn.lower() == bot_name.lower()),
        None,
    )
    if not task_name or task_name not in _TASK_BOT_KEYS:
        raise HTTPException(status_code=404, detail=f"Bot '{bot_name}' not found")
    return task_name, _TASK_BOT_KEYS[task_name]


@router.post("/{bot_name}/start")
def start_bot(bot_name: str):
    """Run the scheduled task for a single bot."""
    task_name, _ = _resolve_bot(bot_name)
    try:
        out = _ssh(f"schtasks /run /tn {task_name}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    return {"status": "ok", "output": out}


@router.post("/{bot_name}/stop")
def stop_bot(bot_name: str):
    """Kill only the python.exe process whose commandline contains this bot's key."""
    _, bot_key = _resolve_bot(bot_name)
    try:
        out = _ssh(
            f'wmic process where "commandline like \'%{bot_key}%\'" call terminate 2>nul'
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    return {"status": "ok", "output": out}


@router.post("/{bot_name}/restart")
def restart_bot(bot_name: str):
    """Kill this bot's process, wait 3 s, then re-run its scheduled task."""
    import time
    task_name, bot_key = _resolve_bot(bot_name)
    try:
        stop_out = _ssh(
            f'wmic process where "commandline like \'%{bot_key}%\'" call terminate 2>nul'
        )
        time.sleep(3)
        start_out = _ssh(f"schtasks /run /tn {task_name}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    return {"status": "ok", "output": f"{stop_out}\n{start_out}".strip()}
