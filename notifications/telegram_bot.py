"""
telegram_bot.py — Telegram Command Handler
Location: notifications/telegram_bot.py

READ-ONLY COMMANDS:
  /status          — all bots running/stopped with uptime
  /balance         — current balance per account
  /trades          — today's trade summary
  /report          — trigger daily report (weekdays only)
  /report-force    — trigger report even on weekends
  /help            — command list

CONTROL COMMANDS (require /confirm within 30 seconds):
  /restart         — restart all bots
  /restart smc     — restart specific bot (smc/reversion/scalper/fft)
  /stop            — stop all bots
  /stop smc        — stop specific bot
  /emergency       — kill everything immediately
  /confirm         — confirm pending action

Run via Task Scheduler at startup (runs 24/7).
Install: pip install requests
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

TELEGRAM_TOKEN  = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
ADMIN_CHAT      = "429207285"           # Primary admin — always has access even if users.json missing
GROUP_CHAT      = "-1003977707258"      # LWG Capital Algos Notifications — broadcast destination
ALGOS_ROOT      = Path("C:/algos")
USERS_FILE      = ALGOS_ROOT / "users.json"
OFFSET_FILE     = ALGOS_ROOT / "telegram_offset.json"
TELEGRAM_START  = ALGOS_ROOT / "telegram_start.json"
TEXAS           = ZoneInfo("America/Chicago")
POLL_INTERVAL   = 10
CONFIRM_TIMEOUT = 30

# Commands allowed per role
ROLE_COMMANDS = {
    "admin":    {"/status","/balance","/trades","/report","/demo","/live","/all",
                 "/force","/help","/restart","/stop","/emergency","/confirm",
                 "/users","/resume"},
    "readonly": {"/status","/balance","/trades","/report","/demo","/live","/all",
                 "/force","/help"},
}


TASK_NAMES = {
    "smc":       "BOT_SMC_TREND",
    "reversion": "BOT_MEAN_REVERSION",
    "scalper":   "BOT_SCALPER",
    "fft":       "BOT_FFT",
}

BOTS = {
    "smc": {
        "name":   "SMC Trend",
        "script": "bot_smc_trend.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/gold_main/gold_main_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/gold_main/bot_smc_trend.log",
    },
    "reversion": {
        "name":   "Mean Reversion",
        "script": "bot_mean_reversion.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/gold_main/gold_main_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/gold_main/bot_mean_reversion.log",
    },
    "scalper": {
        "name":   "Scalper",
        "script": "bot_scalper.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/gold_scalper/bot_scalper.log",
    },
    "fft": {
        "name":   "FFT",
        "script": "bot_fft.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/gold_fft/bot_fft.log",
    },
}

# Per-user pending actions — keyed by user_id so two users can't overwrite each other's confirm state
pending_actions: dict = {}


# =============================================================================
# TELEGRAM API
# =============================================================================

def get_updates(offset: int = 0) -> list:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        r = requests.get(url, params={"offset": offset, "timeout": 5}, timeout=10)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception:
        pass
    return []


def send(text: str):
    """Broadcast to the group (startup ping, unsolicited alerts)."""
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": GROUP_CHAT, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")


def send_to(chat_id: str, text: str):
    """Send a message to a specific chat ID."""
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")


def load_users() -> dict:
    """
    Load users from users.json on VPS.
    Falls back to admin-only if file missing.
    Format: {"users": {"USER_ID": {"name": "...", "role": "admin|readonly"}}}
    """
    if USERS_FILE.exists():
        try:
            with open(USERS_FILE) as f:
                return json.load(f).get("users", {})
        except Exception:
            pass
    # Fallback — admin only
    return {ADMIN_CHAT: {"name": "Admin", "role": "admin"}}


def save_users(users: dict):
    data = {"users": users}
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_role(user_id: str) -> str | None:
    """Return role for user_id or None if not authorized."""
    users = load_users()
    user  = users.get(user_id)
    return user["role"] if user else None


def can(user_id: str, command: str) -> bool:
    """True if the user's role allows this command."""
    role = get_role(user_id)
    if not role:
        return False
    return command in ROLE_COMMANDS.get(role, set())


def load_offset() -> int:
    if OFFSET_FILE.exists():
        with open(OFFSET_FILE) as f:
            return json.load(f).get("offset", 0)
    return 0


def save_offset(offset: int):
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)


# =============================================================================
# DATA HELPERS
# =============================================================================

def load_json(path: Path):
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def is_running(script: str) -> bool:
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=10
        )
        return script in r.stdout
    except Exception:
        return False


def get_uptime(log_path: Path) -> str:
    """
    Calculate uptime by finding the MOST RECENT startup line in the log.
    Uses reversed scan to match algo.py panel behavior so uptimes are consistent.
    """
    if not log_path.exists():
        return "unknown"
    try:
        with open(log_path, errors="replace") as f:
            lines = f.readlines()
        for line in reversed(lines):
            if ("STARTING" in line or
                    ("Balance" in line and "Risk" in line) or
                    ("Balance" in line and "AI:" in line)):
                try:
                    ts    = line.split("|")[0].strip()[:19]
                    start = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    delta = datetime.utcnow() - start
                    h = int(delta.total_seconds() // 3600)
                    m = int((delta.total_seconds() % 3600) // 60)
                    return f"{h}h {m}m"
                except Exception:
                    continue
    except Exception:
        return "unknown"
    return "unknown"


def get_balance(equity) -> float:
    records = equity if isinstance(equity, list) else []
    if not records:
        return 0.0
    return float(records[-1].get("balance", records[-1].get("equity", 0)))


def get_start_balance(equity) -> float:
    """First equity record — the account starting balance."""
    records = equity if isinstance(equity, list) else []
    if not records:
        return 0.0
    return float(records[0].get("balance", records[0].get("equity", 0)))


def get_today_trades(trades: list) -> list:
    today = datetime.now(TEXAS).date().isoformat()
    return [t for t in trades
            if t.get("closed_at") and t["closed_at"][:10] == today
            and t.get("outcome") in ("win", "loss", "breakeven")]


# =============================================================================
# BOT CONTROL
# =============================================================================

def task_start(task_name: str) -> bool:
    try:
        result = subprocess.run(
            ["schtasks", "/run", "/tn", task_name],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except Exception:
        return False


def task_stop(task_name: str) -> bool:
    try:
        subprocess.run(
            ["schtasks", "/end", "/tn", task_name],
            capture_output=True, text=True, timeout=15
        )
        return True
    except Exception:
        return False


def do_restart(bot_keys: list) -> str:
    """
    Restart bots using the startup coordinator for sequential startup.
    This prevents MT5 account mixing by ensuring only one bot connects at a time.

    For individual bot restart: uses direct task start (no coordinator needed).
    For all bots: uses SYS_STARTUP coordinator which starts bots one by one
    and waits for each to confirm connection before starting the next.
    """
    # Individual bot restart — direct task start is fine
    if set(bot_keys) != set(BOTS.keys()):
        lines = []
        for key in bot_keys:
            task = TASK_NAMES.get(key)
            if not task:
                continue
            task_stop(task)
            # schtasks /end stops the task entry but does not reliably kill the
            # Python process. If the process is still alive when schtasks /run is
            # called, Task Scheduler refuses to start a new instance. Kill it
            # directly by matching the script name in the command line.
            script_name = BOTS[key].get("script", "")
            if script_name:
                subprocess.run(
                    ["wmic", "process", "where",
                     f"name='python.exe' and commandline like '%{script_name}%'",
                     "call", "terminate"],
                    capture_output=True, timeout=10
                )
            time.sleep(5)
            ok = task_start(task)
            lines.append(f"{'✓' if ok else '✗'}  {BOTS[key]['name']}")
        return "\n".join(lines)

    # Full restart — stop everything then use coordinator
    for key in BOTS.keys():
        task = TASK_NAMES.get(key)
        if task:
            task_stop(task)
    time.sleep(3)

    # Run startup coordinator — starts bots sequentially, waits for each connection
    ok = task_start("SYS_STARTUP")
    if ok:
        return (
            "Restarting all bots sequentially via startup coordinator.\n"
            "Each bot waits for MT5 connection before the next starts.\n"
            "_Check /status in ~2 minutes to confirm all running._"
        )
    else:
        return "Failed to start SYS_STARTUP coordinator. Try restarting manually."


def do_stop(bot_keys: list) -> str:
    lines = []
    for key in bot_keys:
        task = TASK_NAMES.get(key)
        if not task:
            continue
        task_stop(task)
        lines.append(f"✓  {BOTS[key]['name']} stopped")
    return "\n".join(lines)


def do_emergency_stop() -> str:
    for key in BOTS:
        task = TASK_NAMES.get(key)
        if task:
            task_stop(task)
    try:
        subprocess.run(["taskkill", "/f", "/im", "python.exe"],
                       capture_output=True, timeout=10)
    except Exception:
        pass
    return "All bot processes terminated."


# =============================================================================
# READ-ONLY COMMANDS
# =============================================================================

def cmd_status() -> str:
    import time as _time
    sys.path.insert(0, str(ALGOS_ROOT / "shared"))
    from bot_state import BOT_NAMES, get_uptime_str
    now_tx = datetime.now(TEXAS).strftime("%b %d  %I:%M %p CT")
    lines  = [f"📊 *Bot Status*  _{now_tx}_", ""]

    BOT_SCRIPTS = {
        "smc_trend":      "bot_smc_trend.py",
        "mean_reversion": "bot_mean_reversion.py",
        "scalper":        "bot_scalper.py",
        "fft":            "bot_fft.py",
    }

    lines.append("*Trading Bots*")
    for key, script in BOT_SCRIPTS.items():
        running = is_running(script)
        uptime  = get_uptime_str(key) if running else "—"
        dot     = "🟢" if running else "🔴"
        name    = BOT_NAMES.get(key, key)
        lines.append(f"{dot} `{name:<16}` {uptime}")

    lines.append("")
    lines.append("*System*")
    tg_running = is_running("telegram_bot.py")
    dot        = "🟢" if tg_running else "🔴"
    tg_uptime  = ""
    if tg_running and TELEGRAM_START.exists():
        try:
            import json as _json
            data      = _json.loads(TELEGRAM_START.read_text())
            started   = float(data["started"])
            delta     = _time.time() - started
            h = int(delta // 3600)
            m = int((delta % 3600) // 60)
            tg_uptime = f"{h}h {m}m"
        except Exception:
            tg_uptime = "running"
    lines.append(f"{dot} `{'Telegram':<16}` {tg_uptime if tg_running else 'Stopped'}")
    return "\n".join(lines)


def cmd_balance() -> str:
    sys.path.insert(0, str(ALGOS_ROOT / "shared"))
    from bot_state import read_all, BOT_STARTING_BALANCES, BOT_NAMES
    now_tx = datetime.now(TEXAS).strftime("%b %d  %I:%M %p CT")
    lines  = [f"💰 *Account Balances*  _{now_tx}_", ""]
    all_states = read_all()
    for key, state in all_states.items():
        balance = state.get("balance", BOT_STARTING_BALANCES.get(key, 1000.0))
        pct     = state.get("total_pnl_pct", 0.0)
        name    = BOT_NAMES.get(key, key)
        arrow   = "↑" if pct > 0 else "↓" if pct < 0 else "—"
        sign    = "+" if pct >= 0 else ""
        lines.append(f"`{name:<16}` *${balance:,.2f}*  {arrow} {sign}{pct:.1f}%")
    return "\n".join(lines)


def cmd_trades() -> str:
    now_tx  = datetime.now(TEXAS).strftime("%b %d  %I:%M %p CT")
    lines   = [f"📋 *Today's Trades*  _{now_tx}_", ""]
    total_w = total_l = total_be = total_t = 0

    for key, cfg in BOTS.items():
        trades = load_json(cfg["trades"])
        today  = get_today_trades(trades)
        w  = sum(1 for t in today if t["outcome"] == "win")
        l  = sum(1 for t in today if t["outcome"] == "loss")
        be = sum(1 for t in today if t["outcome"] == "breakeven")
        wr = f"{w/len(today)*100:.0f}%" if today else "—"
        lines.append(f"`{cfg['name']:<16}` {len(today)} trades  {w}W {l}L {be}BE  WR {wr}")
        total_w += w; total_l += l; total_be += be; total_t += len(today)

    lines.append("")
    lines.append(f"`{'Total':<16}` {total_t} trades  {total_w}W {total_l}L {total_be}BE")
    return "\n".join(lines)


def cmd_report(user_id: str, force: bool = False, group: str | None = None) -> str:
    """
    Trigger the daily report.
    - On weekdays: runs immediately for the requested group
    - On weekends: prompts /force first, then asks for group
    - group: None = ask user, "demo"/"live"/"all" = run directly
    """
    now_tx     = datetime.now(TEXAS)
    is_weekend = now_tx.weekday() >= 5

    # If no group specified, ask first
    if group is None:
        if is_weekend:
            pending_actions[user_id] = {
                "command":    lambda uid=user_id: _ask_report_group(uid, force=True),
                "label":      "Weekend Report Group",
                "expires_at": datetime.utcnow() + timedelta(seconds=120),
            }
            day = now_tx.strftime("%A")
            return (
                f"📅 It's {day} — gold markets are closed\\.\n\n"
                f"Reply /demo, /live, or /all to send a report anyway\\."
            )
        else:
            pending_actions[user_id] = {
                "command":    lambda uid=user_id: _ask_report_group(uid, force=False),
                "label":      "Report Group",
                "expires_at": datetime.utcnow() + timedelta(seconds=120),
            }
            return (
                f"📊 Which accounts?\n\n"
                f"Reply /demo, /live, or /all"
            )

    # Group specified — run the report
    if is_weekend and not force:
        return (
            f"📅 Weekend — markets closed\\.\n"
            f"Send /report then /demo, /live or /all to force\\."
        )
    return _run_reporter(group=group, force=force)


def _ask_report_group(user_id: str, force: bool = False) -> str:
    """Called when user confirms a pending report — now ask for group."""
    pending_actions[user_id] = {
        "command":    lambda: _run_reporter(group="all", force=force),
        "label":      "Report (All)",
        "expires_at": datetime.utcnow() + timedelta(seconds=120),
    }
    return "Reply /demo, /live, or /all"


def _run_reporter(group: str = "all", force: bool = False) -> str:
    try:
        args = ["python", str(ALGOS_ROOT / "notifications/reporter.py"),
                "--group", group]
        if force:
            args.append("--force")
        subprocess.Popen(args, cwd=str(ALGOS_ROOT))
        label = group.upper() if group != "all" else "All accounts"
        return f"📊 Generating {label} report\\. Check messages shortly\\."
    except Exception as e:
        return f"Failed to run reporter: {e}"


def cmd_users(user_id: str) -> str:
    """Admin only — list all authorized users."""
    users  = load_users()
    now_tx = datetime.now(TEXAS).strftime("%b %d  %I:%M %p CT")
    lines  = [f"*Users*  _{now_tx}_", ""]
    for uid, info in users.items():
        name  = info.get("name", "Unknown")
        role  = info.get("role", "readonly").upper()
        added = info.get("added", "")
        you   = " ← you" if uid == user_id else ""
        lines.append(f"`{uid}`  {name}  {role}{you}")
        if added:
            lines.append(f"  _Added {added}_")
    lines.append("")
    lines.append("_Manage users via the algo panel on your Mac_")
    return "\n".join(lines)


def cmd_help() -> str:
    return (
        "📖 *LWG Capital — Commands*\n\n"
        "*Read Only*\n"
        "`/status`         Running status and uptime\n"
        "`/balance`        Account balances\n"
        "`/trades`         Today's trade summary\n"
        "`/report`         Daily report — prompts for account group\n"
        "`/demo`           Report for demo accounts only\n"
        "`/live`           Report for live accounts only\n"
        "`/all`            Report for all accounts\n"
        "`/help`           This message\n\n"
        "*Admin Only*\n"
        "`/users`          List authorized users\n\n"
        "*Control*  _type /confirm within 30s_\n"
        "`/restart`        Restart all bots\n"
        "`/restart smc`    Restart one bot\n"
        "`/stop`           Stop all bots\n"
        "`/stop scalper`   Stop one bot\n"
        "`/emergency`      Kill everything immediately\n\n"
        "*Override*  _no confirm needed_\n"
        "`/resume scalper` Resume a locked bot (overrides peak protection)\n\n"
        "_Bot keys: smc  reversion  scalper  fft_"
    )


# =============================================================================
# CONTROL COMMANDS
# =============================================================================

def request_confirm(user_id: str, command_fn, label: str) -> str:
    pending_actions[user_id] = {
        "command":    command_fn,
        "label":      label,
        "expires_at": datetime.utcnow() + timedelta(seconds=CONFIRM_TIMEOUT),
    }
    return (
        f"⚠️ *Confirm Required*\n\n"
        f"Action: _{label}_\n\n"
        f"Send /confirm within {CONFIRM_TIMEOUT}s to proceed\\.\n"
        f"Any other message cancels\\."
    )


def cmd_confirm(user_id: str) -> str:
    action = pending_actions.get(user_id, {})
    if not action.get("command"):
        return "No pending action."
    if datetime.utcnow() > action["expires_at"]:
        pending_actions.pop(user_id, None)
        return "⏰ Confirmation timed out. Action cancelled."
    fn    = action["command"]
    label = action["label"]
    pending_actions.pop(user_id, None)
    result = fn()
    return f"✅ *{label}*\n\n{result}"


def parse_bot_key(parts: list) -> str | None:
    if len(parts) >= 2:
        key = parts[1].lower()
        if key in BOTS:
            return key
    return None


# =============================================================================
# MESSAGE ROUTER
# =============================================================================

def handle_message(text: str, chat_id: str, user_id: str) -> str:
    """
    chat_id — where to reply (group id or DM id)
    user_id — who sent it (their personal Telegram user id, used for auth)
    """
    parts = text.strip().split()
    cmd   = parts[0].lower() if parts else ""

    def denied() -> str:
        return "You do not have permission to use that command."

    if cmd == "/status":        return cmd_status() if can(user_id, cmd) else denied()
    if cmd == "/balance":       return cmd_balance() if can(user_id, cmd) else denied()
    if cmd == "/trades":        return cmd_trades() if can(user_id, cmd) else denied()
    if cmd == "/report":        return cmd_report(user_id, force=False, group=None) if can(user_id, cmd) else denied()
    if cmd == "/help":          return cmd_help()
    if cmd == "/users":         return cmd_users(user_id) if can(user_id, cmd) else denied()
    if cmd == "/confirm":       return cmd_confirm(user_id) if can(user_id, cmd) else denied()

    # Report group shortcuts
    if cmd in ("/demo", "/live", "/all"):
        if not can(user_id, cmd):
            return denied()
        group  = cmd.lstrip("/")
        action = pending_actions.get(user_id, {})
        if action.get("command") and datetime.utcnow() <= action["expires_at"]:
            pending_actions.pop(user_id, None)
            return _run_reporter(group=group, force=True)
        return cmd_report(user_id, force=False, group=group)

    if cmd == "/force":
        if not can(user_id, cmd):
            return denied()
        action = pending_actions.get(user_id, {})
        if action.get("command") and datetime.utcnow() <= action["expires_at"]:
            fn = action["command"]
            pending_actions.pop(user_id, None)
            return fn()
        return "No pending action."

    if cmd == "/emergency":
        if not can(user_id, cmd):
            return denied()
        return request_confirm(user_id, do_emergency_stop,
                               "Emergency Stop — kill all bots")

    if cmd == "/restart":
        if not can(user_id, cmd):
            return denied()
        bot_key = parse_bot_key(parts)
        if bot_key:
            name = BOTS[bot_key]["name"]
            return request_confirm(user_id, lambda k=bot_key: do_restart([k]),
                                   f"Restart {name}")
        return request_confirm(user_id, lambda: do_restart(list(BOTS.keys())),
                               "Restart All Bots")

    if cmd == "/stop":
        if not can(user_id, cmd):
            return denied()
        bot_key = parse_bot_key(parts)
        if bot_key:
            name = BOTS[bot_key]["name"]
            return request_confirm(user_id, lambda k=bot_key: do_stop([k]),
                                   f"Stop {name}")
        return request_confirm(user_id, lambda: do_stop(list(BOTS.keys())),
                               "Stop All Bots")

    if cmd == "/resume":
        if not can(user_id, cmd):
            return denied()
        bot_key = parse_bot_key(parts)
        if not bot_key:
            return "Usage: `/resume <bot>`\nBot keys: smc  reversion  scalper  fft"
        from bot_state import read_bot, write_bot
        state = read_bot(bot_key)
        name  = BOTS[bot_key]["name"]
        if not state.get("day_locked"):
            return f"{name} is not locked — no override needed."
        write_bot(bot_key, {"resume_trading": True})
        return (
            f"▶️ *Resume signal sent to {name}*\n"
            f"Bot will unlock within 60s and resume trading.\n"
            f"Peak protection is now OFF for the rest of today — trade carefully."
        )

    # Unknown command cancels this user's pending action
    if pending_actions.get(user_id, {}).get("command"):
        pending_actions.pop(user_id, None)
        return f"Action cancelled.\nUnknown command: `{cmd}`\nSend /help for commands."

    return f"Unknown command: `{cmd}`\nSend /help for commands."


# =============================================================================
# MAIN LOOP
# =============================================================================

def main():
    print(f"Telegram bot started — polling every {POLL_INTERVAL}s")
    send("🟢 *LWG Capital online*\nSend /help for available commands\\.")
    offset = load_offset()

    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                save_offset(offset)
                msg     = update.get("message", {})
                text    = msg.get("text", "").strip()
                chat_id = str(msg.get("chat", {}).get("id", ""))   # where to reply
                user_id = str(msg.get("from", {}).get("id", ""))   # who sent it
                if not text:
                    continue

                # Authorize by sender's user id, not the chat/group id
                role = get_role(user_id)
                if not role:
                    from_user = msg.get("from", {})
                    username  = from_user.get("username", "unknown")
                    name      = from_user.get("first_name", "")
                    print(f"UNAUTHORIZED: chat={chat_id} user={user_id} (@{username}) ({name}) text={text[:50]}")
                    send_to(chat_id, "This bot is private. You are not authorized.")
                    continue
                response = handle_message(text, chat_id, user_id)
                send_to(chat_id, response)
        except Exception as e:
            print(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
