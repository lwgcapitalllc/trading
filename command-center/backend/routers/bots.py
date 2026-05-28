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
import time as _time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

import config as cfg
from models import BotCapUpdate, BotConfigSections, BotConfigUpdate, BotSnapshot, BotStatus, JobStatus, ProcessStatus

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

# Crash-alert suppress keys — must match telegram_bot.py / monitor.py
# (bot_key → the short key written to stop_suppress.json)
_SUPPRESS_KEYS: dict[str, str] = {
    "smc_trend":      "smc",
    "mean_reversion": "reversion",
    "scalper":        "scalper",
    "fft":            "fft",
}

# Risk caps per bot — mirrors bot_state.py BOT_THRESHOLDS.
# Update here whenever thresholds change in the algo.
_BOT_THRESHOLDS: dict[str, dict[str, float]] = {
    "smc_trend":      {"daily_goal": 2.0,  "daily_cap": 10.0, "weekly_cap": 20.0},
    "mean_reversion": {"daily_goal": 2.0,  "daily_cap": 10.0, "weekly_cap": 20.0},
    "scalper":        {"daily_goal": 10.0, "daily_cap": 8.0,  "weekly_cap": 20.0},
    "fft":            {"daily_goal": 2.0,  "daily_cap": 5.0,  "weekly_cap": 15.0},
}

# Telegram — same credentials as notify.py / algo.py
_TG_TOKEN = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
_TG_CHAT  = "-1003977707258"

# bot_key → display name for notifications
_KEY_DISPLAY: dict[str, str] = {v: _DISPLAY_NAMES[k] for k, v in _TASK_BOT_KEYS.items()}

# Thresholds — git-tracked file read by both command center and pnl_tracker (via bot_state.py).
_THRESHOLDS_JSON_PATH = cfg.MONOREPO_ROOT / "algos" / "shared" / "thresholds.json"


def _load_thresholds_json() -> dict[str, dict[str, float]]:
    if _THRESHOLDS_JSON_PATH.exists():
        try:
            return json.loads(_THRESHOLDS_JSON_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_thresholds_json(overrides: dict) -> None:
    _THRESHOLDS_JSON_PATH.write_text(json.dumps(overrides, indent=2))


def _get_thresholds(bot_key: str) -> dict[str, float]:
    base = dict(_BOT_THRESHOLDS.get(bot_key, {}))
    base.update(_load_thresholds_json().get(bot_key, {}))
    return base


# Maps (bot_key, cap_name) → [(section, field)] pairs to write into instance config.json.
# These are the fields the strategy engines actually read for hard stops.
_CAP_CONFIG_FIELDS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "smc_trend": {
        "daily_cap":  [("protection", "max_daily_loss_pct_bot1")],
        "weekly_cap": [("protection", "max_weekly_loss_pct_bot1")],
        "daily_goal": [],
    },
    "mean_reversion": {
        "daily_cap":  [("protection", "max_daily_loss_pct_bot2")],
        "weekly_cap": [("protection", "max_weekly_loss_pct_bot2")],
        "daily_goal": [],
    },
    "scalper": {
        "daily_cap":  [("bot_scalper", "daily_loss_cap_pct")],
        "weekly_cap": [("bot_scalper", "weekly_loss_cap_pct")],
        "daily_goal": [("bot_scalper", "daily_profit_target_pct")],
    },
    "fft": {
        "daily_cap":  [("bot_fft", "max_daily_loss_pct"), ("bot_fft", "daily_budget_pct")],
        "weekly_cap": [("bot_fft", "max_weekly_loss_pct")],
        "daily_goal": [],
    },
}


# ── Per-bot config file mapping ───────────────────────────────────────────────
# Maps bot_key → the instance config.json path and the strategy section name.
_BOT_INSTANCE_MAP: dict[str, dict] = {
    "smc_trend":      {"path": cfg.INSTANCES_DIR / "gold_main"    / "config.json", "section": "bot_smc_trend"},
    "mean_reversion": {"path": cfg.INSTANCES_DIR / "gold_main"    / "config.json", "section": "bot_mean_reversion"},
    "scalper":        {"path": cfg.INSTANCES_DIR / "gold_scalper" / "config.json", "section": "bot_scalper"},
    "fft":            {"path": cfg.INSTANCES_DIR / "gold_fft"     / "config.json", "section": "bot_fft"},
}


def _read_instance_config(bot_key: str) -> dict:
    info = _BOT_INSTANCE_MAP.get(bot_key)
    if not info or not info["path"].exists():
        raise HTTPException(status_code=404, detail=f"Config file not found for '{bot_key}'")
    return json.loads(info["path"].read_text(encoding="utf-8"))


def _write_instance_config(bot_key: str, data: dict) -> None:
    info = _BOT_INSTANCE_MAP[bot_key]
    info["path"].write_text(json.dumps(data, indent=2), encoding="utf-8")


def _git_commit_push(file_paths: list[Path] | Path, message: str) -> str:
    """Stage files, commit if dirty, push. Returns output summary."""
    root = str(cfg.MONOREPO_ROOT)
    paths = [file_paths] if isinstance(file_paths, Path) else file_paths
    rels  = [str(p.relative_to(cfg.MONOREPO_ROOT)) for p in paths]
    for rel in rels:
        subprocess.run(["git", "-C", root, "add", rel], check=True, capture_output=True, timeout=15)
    status = subprocess.run(
        ["git", "-C", root, "status", "--porcelain"] + rels,
        capture_output=True, text=True, timeout=10,
    )
    if not status.stdout.strip():
        return "nothing to commit"
    subprocess.run(["git", "-C", root, "commit", "-m", message], check=True, capture_output=True, timeout=15)
    out = subprocess.run(
        ["git", "-C", root, "push", "origin", "main"],
        capture_output=True, text=True, timeout=30,
    )
    return (out.stdout + out.stderr).strip()


def _notify_telegram(text: str) -> None:
    """Send a Telegram notification.  Mirrors algo.py notify_telegram().  Never raises."""
    try:
        url  = f"https://api.telegram.org/bot{_TG_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": _TG_CHAT,
            "text":    text,
            "parse_mode": "Markdown",
        }).encode()
        urllib.request.urlopen(url, data=data, timeout=5)
    except Exception:
        pass


def _suppress_stop_alert(bot_key: str) -> None:
    """Write bot key to stop_suppress.json so the crash monitor skips alerting.
    Mirrors algo.py suppress_stop_alert(). MUST be called before killing the process.
    """
    suppress_key = _SUPPRESS_KEYS.get(bot_key)
    if not suppress_key:
        return
    _ssh(
        f'python -c "'
        f'import json,pathlib;'
        f"p=pathlib.Path(r'C:/trading/algos/stop_suppress.json');"
        f'k=json.loads(p.read_text()) if p.exists() else [];'
        f"k.append('{suppress_key}') if '{suppress_key}' not in k else None;"
        f'p.write_text(json.dumps(k))"'
    )


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
    # bot_state.py writes "started" as a Unix timestamp float (time.time()).
    # Fall back to ISO string fields used by older/alternate state writers.
    raw = state.get("started") or state.get("started_at") or state.get("start_time")
    if not raw:
        return None
    try:
        if isinstance(raw, (int, float)) and raw > 0:
            return int(_time.time() - raw)
        # ISO string fallback
        start = datetime.fromisoformat(str(raw)).replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - start).total_seconds())
    except Exception:
        return None


@router.get("/ping")
def vps_ping():
    try:
        out = _ssh("echo ok")
        return {"status": "ok" if "ok" in out else "error"}
    except (subprocess.TimeoutExpired, Exception):
        return {"status": "error"}


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

        # Process list is authoritative. If the process isn't in wmic output,
        # the bot is STOPPED — regardless of task_status or bot_state.json.
        # (bot_state.json is never updated after a hard kill, so it can show
        #  "running" indefinitely even after the process is dead.)
        running_in_procs = _is_python_running(snap, bot_key)
        if task_status == "Running" or running_in_procs:
            status = "RUNNING"
        else:
            status = "STOPPED"

        total_pnl = state.get("total_pnl_pct")
        if total_pnl is not None:
            try:
                total_pnl = float(total_pnl)
            except Exception:
                total_pnl = None

        thresholds = _get_thresholds(bot_key)

        bots.append(BotStatus(
            name=_DISPLAY_NAMES.get(task_name, task_name),
            account=state.get("account", ""),
            account_type=_TASK_ACCT_TYPE.get(task_name, "demo"),
            balance=state.get("balance"),
            status=status,
            uptime_seconds=_uptime_seconds(state) if status == "RUNNING" else None,
            total_pnl_pct=total_pnl,
            day_locked=bool(state.get("day_locked", False)),
            daily_pnl=state.get("daily_pnl"),
            daily_pnl_pct=state.get("daily_pnl_pct"),
            weekly_pnl=state.get("weekly_pnl"),
            weekly_pnl_pct=state.get("weekly_pnl_pct"),
            peak_balance=state.get("peak_balance") or None,
            trades_today=state.get("trades_today"),
            lock_reason=state.get("lock_reason") or None,
            last_updated=state.get("last_updated") or None,
            daily_goal_pct=thresholds.get("daily_goal"),
            daily_cap_pct=thresholds.get("daily_cap"),
            weekly_cap_pct=thresholds.get("weekly_cap"),
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
    _notify_telegram("▶️ All bots starting \\[command center\\]")
    return {"status": "ok", "output": out}


@router.post("/stop")
def stop_bots():
    """Delete the MT5 lock file and kill all python.exe processes on the VPS."""
    try:
        for bot_key in _SUPPRESS_KEYS:
            _suppress_stop_alert(bot_key)
        out = _stop_procs()
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    _notify_telegram("⏹ All bots stopped \\[command center\\]")
    return {"status": "ok", "output": out}


@router.post("/restart")
def restart_bots():
    """Stop all bots, wait 3 s, then run SYS_STARTUP."""
    try:
        for bot_key in _SUPPRESS_KEYS:
            _suppress_stop_alert(bot_key)
        stop_out = _stop_procs()
        _time.sleep(3)
        start_out = _start_task()
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    _notify_telegram("🔄 All bots restarting \\[command center\\]")
    return {"status": "ok", "output": f"{stop_out}\n{start_out}".strip()}



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


_COORDINATOR = r"C:\trading\algos\bots\startup_coordinator.py"
# WMI does not inherit the user's PATH — must use the full Python executable path.
_PYTHON_EXE  = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"

# Use wmic process call create so startup_coordinator runs under WMI — not
# under the SSH job object — meaning the bot it spawns survives when SSH closes.
# Direct SSH call kills children via job-object teardown despite CREATE_NEW_PROCESS_GROUP.
def _launch_bot(bot_key: str) -> str:
    """Fire startup_coordinator.py --bot <key> via WMI and return wmic output."""
    return _ssh(
        f'wmic process call create "{_PYTHON_EXE} {_COORDINATOR} --bot {bot_key}" 2>nul'
    )


@router.get("/{bot_name}/config", response_model=BotConfigSections)
def get_bot_config(bot_name: str):
    """Return the config sections for a bot from its instance config.json."""
    _, bot_key = _resolve_bot(bot_name)
    data    = _read_instance_config(bot_key)
    section = _BOT_INSTANCE_MAP[bot_key]["section"]
    return BotConfigSections(
        risk       = data.get("risk", {}),
        protection = data.get("protection", {}),
        strategy   = data.get(section, {}),
        regime     = data.get("regime", {}),
        dead_zone  = data.get("dead_zone", {}),
    )


@router.patch("/{bot_name}/config")
def save_bot_config(bot_name: str, update: BotConfigUpdate):
    """Write config sections to instance config.json.
    If deploy=True: git commit → push → VPS git pull → restart bot.
    """
    _, bot_key  = _resolve_bot(bot_name)
    info        = _BOT_INSTANCE_MAP[bot_key]
    section_key = info["section"]
    data        = _read_instance_config(bot_key)

    if update.risk       is not None: data.setdefault("risk", {}).update(update.risk)
    if update.protection is not None: data.setdefault("protection", {}).update(update.protection)
    if update.strategy   is not None: data.setdefault(section_key, {}).update(update.strategy)
    if update.regime     is not None: data.setdefault("regime", {}).update(update.regime)
    if update.dead_zone  is not None: data.setdefault("dead_zone", {}).update(update.dead_zone)

    _write_instance_config(bot_key, data)

    if update.deploy:
        try:
            _git_commit_push(
                info["path"],
                f"config: update {bot_name} from command center",
            )
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"git push failed: {e.stderr.decode(errors='replace')}")

        try:
            _ssh("cd C:\\trading && git pull origin main")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"VPS git pull failed: {e}")

        try:
            _suppress_stop_alert(bot_key)
            _ssh(f'wmic process where "commandline like \'%{bot_key}%\'" call terminate 2>nul')
            _time.sleep(3)
            _launch_bot(bot_key)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"VPS restart failed: {e}")

        display = _KEY_DISPLAY.get(bot_key, bot_key)
        _notify_telegram(f"🔄 *{display}* config updated + restarting \\[command center\\]")

    return {"status": "ok"}


@router.patch("/{bot_name}/caps")
def save_bot_caps(bot_name: str, caps: BotCapUpdate):
    """Update risk caps: write thresholds.json + instance config.json, git push, VPS pull, restart bot."""
    _, bot_key = _resolve_bot(bot_name)

    # 1. thresholds.json — pnl_tracker alert levels (picked up on next 1-min run, no restart needed)
    thresholds = _load_thresholds_json()
    thresholds[bot_key] = {
        "daily_goal": caps.daily_goal_pct,
        "daily_cap":  caps.daily_cap_pct,
        "weekly_cap": caps.weekly_cap_pct,
    }
    _save_thresholds_json(thresholds)

    # 2. instance config.json — strategy engine hard stops (take effect on restart)
    instance_info = _BOT_INSTANCE_MAP[bot_key]
    config_data   = _read_instance_config(bot_key)
    field_map     = _CAP_CONFIG_FIELDS.get(bot_key, {})
    cap_values    = {"daily_cap": caps.daily_cap_pct, "weekly_cap": caps.weekly_cap_pct, "daily_goal": caps.daily_goal_pct}
    for cap_name, value in cap_values.items():
        for section, field in field_map.get(cap_name, []):
            config_data.setdefault(section, {})[field] = value
    _write_instance_config(bot_key, config_data)

    # 3. Git commit both files + push
    try:
        _git_commit_push(
            [_THRESHOLDS_JSON_PATH, instance_info["path"]],
            f"config: update {bot_name} risk caps from command center",
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"git push failed: {e.stderr.decode(errors='replace')}")

    # 4. VPS git pull
    try:
        _ssh("cd C:\\trading && git pull origin main")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS git pull failed: {e}")

    # 5. Restart the bot so new config.json values take effect
    try:
        _suppress_stop_alert(bot_key)
        _ssh(f'wmic process where "commandline like \'%{bot_key}%\'" call terminate 2>nul')
        _time.sleep(3)
        _launch_bot(bot_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS restart failed: {e}")

    display = _KEY_DISPLAY.get(bot_key, bot_key)
    _notify_telegram(f"📊 *{display}* risk caps updated + restarting \\[command center\\]")
    return {"status": "ok"}


@router.post("/{bot_name}/start")
def start_bot(bot_name: str):
    """Launch a single bot via startup_coordinator.py --bot <key> (via WMI).
    Individual BOT_* scheduled tasks are Disabled — schtasks /run does nothing.
    """
    _, bot_key = _resolve_bot(bot_name)
    try:
        out = _launch_bot(bot_key)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    display = _KEY_DISPLAY.get(bot_key, bot_key)
    _notify_telegram(f"▶️ *{display}* starting \\[command center\\]")
    return {"status": "ok", "output": out}


@router.post("/{bot_name}/stop")
def stop_bot(bot_name: str):
    """Kill only the python.exe process whose commandline contains this bot's key."""
    _, bot_key = _resolve_bot(bot_name)
    try:
        _suppress_stop_alert(bot_key)  # must run before kill so monitor skips crash alert
        out = _ssh(
            f'wmic process where "commandline like \'%{bot_key}%\'" call terminate 2>nul'
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    display = _KEY_DISPLAY.get(bot_key, bot_key)
    _notify_telegram(f"⏹ *{display}* stopped \\[command center\\]")
    return {"status": "ok", "output": out}


@router.post("/{bot_name}/restart")
def restart_bot(bot_name: str):
    """Kill this bot's process, wait 3 s, then relaunch via startup_coordinator --bot."""
    _, bot_key = _resolve_bot(bot_name)
    try:
        _suppress_stop_alert(bot_key)  # must run before kill so monitor skips crash alert
        stop_out = _ssh(
            f'wmic process where "commandline like \'%{bot_key}%\'" call terminate 2>nul'
        )
        _time.sleep(3)
        start_out = _launch_bot(bot_key)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    display = _KEY_DISPLAY.get(bot_key, bot_key)
    _notify_telegram(f"🔄 *{display}* restarting \\[command center\\]")
    return {"status": "ok", "output": f"{stop_out}\n{start_out}".strip()}
