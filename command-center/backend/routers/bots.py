"""
Bots router — /bots/*

Read endpoints:
  GET  /bots/snapshot                  — full VPS state via batched SSH
  GET  /bots/{bot_name}/log            — last N lines of stdout log
  GET  /bots/{bot_name}/params         — what this bot is configured with (read-only)

Runtime config:
  PATCH /bots/{bot_name}/runtime       — the levers allowed to move on a RUNNING bot
                                         (risk % only — see services/bot_params.py)

Global control actions (all bots):
  POST /bots/start                     — run SYS_STARTUP task
  POST /bots/stop                      — terminate each registered bot + delete lock
  POST /bots/restart                   — stop + 3s + start

  (There is no /bots/emergency route. This list claimed one until 2026-08-04; it was
   removed at some point and the docstring kept advertising it.)

Per-bot control actions:
  POST /bots/{bot_name}/start          — schtasks /run /tn {task_name}
  POST /bots/{bot_name}/stop           — wmic terminate by commandline match
  POST /bots/{bot_name}/restart        — per-bot stop + 3s + start
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import time as _time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

import config as cfg
from models import BotCapUpdate, BotConfigSections, BotConfigUpdate, BotDeployedVersion, BotParamsView, BotPromoteRequest, BotPromoteResult, BotRuntimeUpdate, BotSnapshot, BotStatus, JobStatus, ProcessStatus, TelegramUser, TelegramUserCreate, TelegramUserRoleUpdate
from services import bot_params, lab_db
from services.notify import send_telegram

router = APIRouter(prefix="/bots", tags=["bots"])

VPS_HOST = cfg.SSH_ALIAS

# Mirror algo.py's constants so behaviour matches the retired panel exactly.
# All first-attempt bots deleted 2026-06-22 (see algos/docs/BOT_DEPLOYMENT_INFRA.md);
# the suite restarted from scratch 2026-07-31 (algos/CLAUDE.md → "CLEAN SLATE").
#
# ⚠ `BOT_MPC_SOS_FADE` IS NOT A REAL SCHEDULED TASK. Every key in these maps is a task
# name because that is how the retired panel was keyed, but the live bot has no `BOT_*`
# task of its own: it boots through SYS_STARTUP → startup_coordinator.py, and the command
# center starts it through that same coordinator over WMI. `_parse_tasks` therefore never
# returns a status for it, which is harmless — `get_snapshot` already treats the PROCESS
# LIST as authoritative and only consults the task status as a secondary signal.
_BOT_DISPLAY_ORDER = ["BOT_MPC_SOS_FADE"]
_DISPLAY_NAMES = {
    "BOT_MPC_SOS_FADE":   "MPC SOS Fade",
    "SYS_TELEGRAM":       "Telegram",
    "SYS_REPORTER":       "Reporter",
    "SYS_MONITOR":        "Monitor",
    "SYS_PNLTRACKER":     "P&L Tracker",
}
# The bot_key is also the string matched against the VPS process commandline
# (`runner.py --bot mpc_sos_fade_demo`) — see `_is_python_running`.
_TASK_BOT_KEYS = {"BOT_MPC_SOS_FADE": "mpc_sos_fade_demo"}
_TASK_ACCT_TYPE = {"BOT_MPC_SOS_FADE": "demo"}
# task → (bot_key, instance dir, log filename). algos/live/runner.py names its log after
# the bot key, in the instance dir.
_LOG_MAP = {
    "BOT_MPC_SOS_FADE": ("mpc_sos_fade_demo", "mpc_sos_fade_demo", "mpc_sos_fade_demo.log"),
}
_SCHEDULED_JOBS = [
    JobStatus(name="Monitor",     schedule="every 1 min",  status="UNKNOWN"),
    JobStatus(name="P&L Tracker", schedule="every 1 min",  status="UNKNOWN"),
    JobStatus(name="Reporter",    schedule="daily 4pm CT", status="UNKNOWN"),
]

# Crash-alert suppress keys — must match telegram_bot.py / monitor.py
# (bot_key → the short key written to stop_suppress.json)
_SUPPRESS_KEYS: dict[str, str] = {"mpc_sos_fade_demo": "mpc_sos_fade_demo"}

# Risk caps per bot — mirrors bot_state.py BOT_THRESHOLDS.
# EMPTY ON PURPOSE. These are pnl_tracker's daily/weekly ALERT levels, and that job is
# disabled (algos/CLAUDE.md → "On hold"), so a number here would render a cap on the Bots
# page that nothing on the VPS enforces. The live bot's real risk lever is
# `strategy_params.exec_risk_pct` in its instance config — see the runtime panel below.
_BOT_THRESHOLDS: dict[str, dict[str, float]] = {}

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
# EMPTY for mpc_sos_fade_demo, and not an oversight: algos/live/ has no daily-cap or
# weekly-cap field to write. Its only account-level lever is per-trade risk, and the
# account-level allocator that would consume a daily budget is UNBUILT (root CLAUDE.md).
# Writing caps into a config the bot never reads is how a dashboard starts lying.
_CAP_CONFIG_FIELDS: dict[str, dict[str, list[tuple[str, str]]]] = {}


# ── Per-bot config file mapping ───────────────────────────────────────────────
# Maps bot_key → the instance config.json path and the strategy section name.
_BOT_INSTANCE_MAP: dict[str, dict] = {
    "mpc_sos_fade_demo": {
        "path": cfg.MONOREPO_ROOT / "algos" / "markets" / "fx" / "instances"
                / "mpc_sos_fade_demo" / "config.json",
        "section": "strategy_params",
    },
}


def _read_instance_config(bot_key: str) -> dict:
    info = _BOT_INSTANCE_MAP.get(bot_key)
    if not info or not info["path"].exists():
        raise HTTPException(status_code=404, detail=f"Config file not found for '{bot_key}'")
    return json.loads(info["path"].read_text(encoding="utf-8"))


def _write_instance_config(bot_key: str, data: dict) -> None:
    # ensure_ascii=False: the file is written as UTF-8 and its `_`-prefixed prose keys are
    # the reasoning behind every value in it. Escaping those to — turns the one part a
    # human actually reads into noise, and this file is edited by hand far more often than
    # it is written from here.
    info = _BOT_INSTANCE_MAP[bot_key]
    info["path"].write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")


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
    """Send a Telegram notification. Never raises.

    Delegates to `services/notify.py` — this router used to carry its own copy of the token,
    chat id and urllib call, which is how the credential ended up committed in six places at
    once. One sender, one credential lookup.
    """
    send_telegram(text)


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


_MARKER_RE = re.compile(r"(?<!\n)(===[A-Z0-9_]+===)")


def _parse_sections(raw: str, initial_section: str) -> dict[str, str]:
    # Put a glued marker back on its own line before splitting. `type` on Windows emits no
    # trailing newline, so a marker echoed after it arrives welded to the file's last
    # character — `}===TELEGRAM_START===` — and the startswith test below silently misses
    # it, merging two sections into one unparseable blob with no error anywhere.
    #
    # The FETCH command already guards this with `echo.` (see _fetch_vps_snapshot). This is
    # the second line of defence, because the failure is invisible: no exception, no empty
    # result, just a bot that shows RUNNING and reports nothing about itself. The pattern
    # is deliberately narrow (upper-case marker names only) so a `===` inside real payload
    # data cannot be mistaken for one.
    raw = _MARKER_RE.sub(r"\n\1", raw)

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

    # One `type` per registered instance's bot_state.json, plus the Telegram start marker.
    # Built from _BOT_STATE_SECTIONS so adding a bot never means editing this string —
    # the two drifting apart is how a registered bot silently reports no state forever.
    # Two cmd quirks, both of which silently merged sections rather than erroring:
    #
    # 1. `type X 2>nul`, never `if exist X (type X)`. A trailing `& next` BINDS to the
    #    if-block, so ONE missing state file swallows every section after it.
    # 2. `echo.` before every marker. `type` does not emit a trailing newline, so the next
    #    marker lands on the same line as the file's last character — `}===TELEGRAM_START===`
    #    — which `_parse_sections` does not recognise as a marker (it tests startswith).
    #    Both sections then merge into one unparseable blob and the bot silently reports no
    #    state at all. This only appears once a state file has CONTENT, so it cannot be
    #    caught before a bot has run once.
    parts = [f"echo. & echo ==={s.upper()}=== & type {_BOT_STATE_PATHS[s]} 2>nul"
             for s, _ in _BOT_STATE_SECTIONS]
    parts.append("echo. & echo ===TELEGRAM_START=== "
                 "& type C:\\trading\\algos\\telegram_start.json 2>nul")
    sections.update(_parse_sections(_ssh(" & ".join(parts)), "state_main"))
    return sections


# (section, [bot keys in that bot_state.json]). One entry per instance dir — a single
# bot_state.json can hold several bot keys, which is why the value is a list.
_BOT_STATE_SECTIONS: list[tuple[str, list[str]]] = [
    ("state_mpc_sos_fade", ["mpc_sos_fade_demo"]),
]

# section → the VPS path `_fetch_vps_snapshot` types. Windows paths, so this stays a
# literal string rather than anything derived from the Mac's filesystem.
_BOT_STATE_PATHS: dict[str, str] = {
    "state_mpc_sos_fade":
        r"C:\trading\algos\markets\fx\instances\mpc_sos_fade_demo\bot_state.json",
}


def _parse_bot_states(snap: dict[str, str]) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for section, keys in _BOT_STATE_SECTIONS:
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
        # schtasks reports the task's PATH, not its name — `\SYS_MONITOR`, with a leading
        # backslash (and `\Folder\Name` if one is ever nested). Matching the raw value
        # against _DISPLAY_NAMES therefore never hit, so this returned {} and EVERY job on
        # the Bots page read UNKNOWN from the day the router was written.
        name = parts[0].strip('"').lstrip("\\").rsplit("\\", 1)[-1]
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


_USERS_FILE_VPS = r"C:\trading\algos\users.json"


def _read_users_vps() -> dict:
    raw = _ssh(f"type {_USERS_FILE_VPS} 2>nul")
    if not raw:
        return {}
    try:
        return json.loads(raw).get("users", {})
    except Exception:
        return {}


def _write_users_vps(users: dict) -> None:
    payload = json.dumps({"users": users}, indent=2, ensure_ascii=True)
    b64 = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    _ssh(
        f"python -c \"import base64; open(r'C:/trading/algos/users.json', 'w', encoding='utf-8')"
        f".write(base64.b64decode(b'{b64}').decode())\""
    )


@router.get("/users", response_model=list[TelegramUser])
def list_users():
    users = _read_users_vps()
    return [TelegramUser(chat_id=k, **v) for k, v in users.items()]


@router.post("/users", status_code=201)
def add_user(body: TelegramUserCreate):
    users = _read_users_vps()
    if body.chat_id in users:
        raise HTTPException(status_code=409, detail="User already exists")
    users[body.chat_id] = {"name": body.name, "role": body.role, "added": date.today().isoformat()}
    _write_users_vps(users)
    return {"status": "ok"}


@router.delete("/users/{chat_id}")
def remove_user(chat_id: str):
    users = _read_users_vps()
    if chat_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    del users[chat_id]
    _write_users_vps(users)
    return {"status": "ok"}


@router.patch("/users/{chat_id}")
def update_user_role(chat_id: str, body: TelegramUserRoleUpdate):
    users = _read_users_vps()
    if chat_id not in users:
        raise HTTPException(status_code=404, detail="User not found")
    users[chat_id]["role"] = body.role
    _write_users_vps(users)
    return {"status": "ok"}


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
            # An MT5 login is an INT everywhere it matters — LiveConfig.account is typed
            # int and BotMT5.connect compares it numerically to refuse the wrong account.
            # It is only a string for display, so the coercion belongs here and nowhere
            # upstream: making the registries hold strings to satisfy a label would put a
            # display concern inside the account guard.
            account=str(state.get("account") or ""),
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
        # "Disabled" is its own answer, not a STOPPED. All three of these were switched
        # off deliberately until a live bot is registered (algos/CLAUDE.md → "On hold"),
        # and showing them as merely stopped reads as a fault the user should go fix.
        if t_status == "Running":
            status = "RUNNING"
        elif t_status == "Disabled":
            status = "DISABLED"
        elif t_status:
            status = "STOPPED"
        else:
            status = "UNKNOWN"
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
# All actions run over SSH.
#   stop  = kill each registered BOT process + delete the MT5 lock
#   start = run SYS_STARTUP scheduled task
#   restart = stop then start (with a 3-second gap)
#   emergency = kill the bots immediately, no lock cleanup (fastest path)
#
# Each endpoint returns { "status": "ok"|"error", "output": "<ssh stdout>" }.
# A 502 is raised when the SSH call itself fails or times out.

_LOCK_PATH  = r"C:\trading\algos\mt5_connect.lock"
_STARTUP_TN = "SYS_STARTUP"


def _kill_bot(bot_key: str) -> str:
    """Terminate ONE bot, matched on the `--bot <key>` in its process commandline.

    **Never `taskkill /f /im python.exe`.** That kills every Python process on the VPS: the
    trading bot, the Telegram bot, the MT5 backtest agent and the NT8 agent. It is how Stop
    took the whole box down, and on 2026-07-31 it is what killed the live bot — which then
    stayed dead for three days, because at the time nothing restarted it. It also silently
    breaks any in-flight lab backtest, since both agents are Python too.

    The bot key is already this repo's process identity — `monitor.is_running` matches on the
    same string, because `runner.py` is the entrypoint for EVERY live bot and the script name
    alone cannot tell two of them apart. Verified on the VPS 2026-08-04: this terminated the
    bot and left the Telegram bot and both agents running on their original PIDs.
    """
    return _ssh(
        f"wmic process where \"name='python.exe' and commandline like '%--bot {bot_key}%'\" "
        f"call terminate 2>nul"
    )


def _stop_procs(clear_lock: bool = True) -> str:
    """Stop every registered bot, and nothing else. Returns combined SSH output."""
    outs = [_kill_bot(key) for key in _SUPPRESS_KEYS]
    if clear_lock:
        # Only meaningful once the bots are actually gone — a live bot re-creates it.
        outs.append(_ssh(f"del {_LOCK_PATH} 2>nul"))
    return "\n".join(o for o in outs if o).strip()


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


# ── Which version is deployed, and promoting a new one ────────────────────────
#
# Aaron's requirement: "I wanna see the version of the bot that is running, so I can know
# exactly what version, and you could know too, so we could look at configs or parameters
# from that version so we're not confused."
#
# Everything here reads the VPS, never the local repo. The local repo is where NEW versions
# are built; it says nothing about what is deployed, and until 2026-08-03 the two were the
# same files — which is exactly the confusion being removed.

_VPS_REPO = r"C:\trading"
_VPS_INSTANCES = r"C:\trading\algos\markets\fx\instances"
_PROMOTE_PY = r"C:\trading\algos\tools\promote.py"


def _deployed_json(bot_key: str) -> dict:
    raw = _ssh(f"type {_VPS_INSTANCES}\\{bot_key}\\deployed.json 2>nul")
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


@router.get("/{bot_name}/version", response_model=BotDeployedVersion)
def get_bot_version(bot_name: str):
    """What this bot is actually running, plus how far the repo has moved past it."""
    _, bot_key = _resolve_bot(bot_name)
    rec = _deployed_json(bot_key)

    # One round trip for the three git/consistency facts. `--show` re-hashes the snapshot on
    # disk, which is the tamper check: the record can only be trusted if the files still
    # match it.
    raw = _ssh(
        f"cd {_VPS_REPO} & git rev-parse --short HEAD"
        f" & echo. & echo ===AHEAD=== & git rev-list --count {rec.get('promoted_commit') or 'HEAD'}..HEAD"
        f" & echo. & echo ===SHOW=== & {_PYTHON_EXE} {_PROMOTE_PY} --bot {bot_key} --show 2>nul"
    )
    parts = _parse_sections(raw, "head")
    try:
        ahead = int(parts.get("ahead", "0").strip().splitlines()[-1])
    except (ValueError, IndexError):
        ahead = 0

    # The live PROCESS's own report. If this disagrees with deployed.json, a promote has
    # happened since the bot started and it is still running the OLD code — the single most
    # misleading state this page can be in, so it is surfaced rather than reconciled away.
    running_hash = ""
    try:
        snap = _fetch_vps_snapshot()
        state = json.loads(snap.get("state_mpc_sos_fade", "{}") or "{}")
        running_hash = (state.get(bot_key) or {}).get("source_hash", "")
    except Exception:
        pass

    # Settings config.json states differently from what was deployed. Not an error — the
    # runtime panel writes exec_risk_pct to config.json on a running bot — but it is the gap
    # between "what the file says" and "what is trading", which is the whole point of this.
    drift: list[str] = []
    deployed_params = rec.get("strategy_params") or {}
    if deployed_params:
        try:
            current = _read_instance_config(bot_key).get("strategy_params", {})
            drift = sorted(k for k, v in current.items() if deployed_params.get(k, v) != v)
        except HTTPException:
            pass

    return BotDeployedVersion(
        frozen=bool(rec),
        hash=rec.get("strategy_source_hash", ""),
        commit=rec.get("promoted_commit", ""),
        promoted_at=rec.get("promoted_at", ""),
        strategy_package=rec.get("strategy_package", ""),
        strategy_class=rec.get("strategy_class", ""),
        strategy_version=rec.get("strategy_version", 0),
        files=rec.get("files", 0),
        params=deployed_params,
        repo_commit=parts.get("head", "").strip().splitlines()[0] if parts.get("head") else "",
        commits_ahead=ahead,
        snapshot_ok="SNAPSHOT MODIFIED" not in parts.get("show", ""),
        running_hash=running_hash,
        params_drift=drift,
    )


def _run_promote(bot_key: str, *, dry_run: bool, pull: bool, allow_dirty: bool) -> str:
    steps = []
    if pull:
        steps.append(f"cd {_VPS_REPO} & git pull origin main")
    flags = " --dry-run" if dry_run else ""
    flags += " --allow-dirty" if allow_dirty else ""
    steps.append(f"{_PYTHON_EXE} {_PROMOTE_PY} --bot {bot_key}{flags}")
    return _ssh(" & ".join(steps))


@router.post("/{bot_name}/promote/preview", response_model=BotPromoteResult)
def preview_bot_promote(bot_name: str, req: BotPromoteRequest):
    """Stage and verify a promote WITHOUT deploying it. The running bot is untouched.

    A real preview, not a file count: it copies the trees, imports the strategy out of the
    copy, builds it with the promoted parameters, and reports which settings would change —
    then deletes the staging. Those are the two questions worth answering before deploying
    ("does it import", "what changes"), and neither can be answered without staging.
    """
    _, bot_key = _resolve_bot(bot_name)
    try:
        out = _run_promote(bot_key, dry_run=True, pull=req.pull, allow_dirty=req.allow_dirty)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")
    return BotPromoteResult(ok="dry run" in out, output=out)


@router.post("/{bot_name}/promote", response_model=BotPromoteResult)
def promote_bot(bot_name: str, req: BotPromoteRequest):
    """Deploy the current VPS code to this bot, then restart it onto the new version.

    This is the ONLY action that changes what a bot trades. A pull does not, a restart does
    not, a lab experiment does not — see `algos/live/version.py`.
    """
    _, bot_key = _resolve_bot(bot_name)
    try:
        out = _run_promote(bot_key, dry_run=False, pull=req.pull, allow_dirty=req.allow_dirty)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="VPS SSH call timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS SSH failed: {e}")

    ok = "pinned" in out
    restarted = False
    if ok and req.restart:
        # Kill it and let SYS_MONITOR bring it back — that path is exercised every time the
        # watchdog fires, so it is the one most likely to work. The suppress key is NOT
        # written: this stop is meant to be undone, immediately.
        _kill_bot(bot_key)
        _time.sleep(2)
        _launch_bot(bot_key)
        restarted = True
    if ok:
        _notify_telegram(
            f"📦 *{_KEY_DISPLAY.get(bot_key, bot_key)}* promoted \\[command center\\]"
        )
    return BotPromoteResult(ok=ok, output=out, restarted=restarted)


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


@router.get("/{bot_name}/params", response_model=BotParamsView)
def get_bot_params(bot_name: str):
    """Everything this bot is configured with — what it trades, on which account, at which
    version, and with which parameters. Read-only.

    This is the answer to "what is that bot actually running?", which previously required
    an SSH session and a JSON file. Labels come from the LAB's scanned schema for the same
    strategy, so a knob is described identically here and in the Run modal.
    """
    _, bot_key = _resolve_bot(bot_name)
    data = _read_instance_config(bot_key)
    section = _BOT_INSTANCE_MAP[bot_key]["section"]

    # Cosmetic only — a strategy the lab has never scanned still renders every parameter
    # under its raw field name rather than dropping it.
    schema = None
    try:
        row = lab_db.get_strategy(data.get("strategy_package", ""))
        schema = (row or {}).get("param_schema")
    except Exception:
        pass

    return BotParamsView(**bot_params.build_view(bot_key, data, schema, section))


@router.patch("/{bot_name}/runtime")
def save_bot_runtime(bot_name: str, update: BotRuntimeUpdate):
    """Change the levers that are allowed to move on a running bot.

    Today that is `exec_risk_pct` alone — see `services/bot_params.py` for why the strategy
    parameters are deliberately not in this set.

    **The bot is NOT restarted.** It re-reads its own config at the top of a loop and
    applies the change only while FLAT (`algos/live/runner.py::_maybe_reload_runtime`), so
    a resize can never land mid-trade and leave a position being managed by rules that
    would not have opened it. That is also why this endpoint does not need to know whether
    a trade is open — the bot does, and it is the one holding the position.
    """
    _, bot_key = _resolve_bot(bot_name)
    info = _BOT_INSTANCE_MAP[bot_key]
    section = info["section"]

    try:
        values = bot_params.validate_runtime(update.values)
    except bot_params.RuntimeUpdateError as e:
        raise HTTPException(status_code=400, detail=str(e))

    data = _read_instance_config(bot_key)
    params = data.setdefault(section, {})
    before = {k: params.get(k) for k in values}
    if all(params.get(k) == v for k, v in values.items()):
        return {"status": "ok", "changed": False, "detail": "Already at those values."}

    params.update(values)
    _write_instance_config(bot_key, data)

    changed = ", ".join(f"{k} {before[k]} → {v}" for k, v in values.items())
    if not update.deploy:
        return {"status": "ok", "changed": True, "deployed": False, "detail": changed}

    try:
        _git_commit_push(info["path"], f"runtime: {bot_name} — {changed} [command center]")
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500,
                            detail=f"git push failed: {e.stderr.decode(errors='replace')}")
    try:
        out = _ssh("cd C:\\trading && git pull origin main")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"VPS git pull failed: {e}")

    display = _KEY_DISPLAY.get(bot_key, bot_key)
    # Plain text, no Markdown: bot keys and param names are full of underscores, and
    # Telegram drops the WHOLE message on an unbalanced entity rather than escaping it.
    _notify_telegram(f"{display} runtime updated [command center]\n{changed}\n"
                     f"Applies at the next bar the bot is flat.")
    return {"status": "ok", "changed": True, "deployed": True, "detail": changed,
            "output": out}


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
