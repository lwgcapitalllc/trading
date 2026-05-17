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
ADMIN_CHAT      = "429207285"   # Primary admin — always has access even if users.json missing
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
                 "/users"},
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

pending_action = {"command": None, "label": None, "expires_at": None}



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
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": ADMIN_CHAT, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")


def load_users() -> dict:
    """
    Load users from users.json on VPS.
    Falls back to admin-only if file missing.
    Format: {"users": {"CHAT_ID": {"name": "...", "role": "admin|readonly"}}}
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


def get_role(chat_id: str) -> str | None:
    """Return role for chat_id or None if not authorized."""
    users = load_users()
    user  = users.get(chat_id)
    return user["role"] if user else None


def can(chat_id: str, command: str) -> bool:
    """True if the user's role allows this command."""
    role = get_role(chat_id)
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
    lines = []
    for key in bot_keys:
        task = TASK_NAMES.get(key)
        if not task:
            continue
        task_stop(task)
        time.sleep(3)
        ok = task_start(task)
        lines.append(f"{'✓' if ok else '✗'}  {BOTS[key]['name']}")
    return "\n".join(lines)


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
    now_tx = datetime.now(TEXAS).strftime("%b %d  %I:%M %p CT")
    lines  = [f"📊 *Bot Status*  _{now_tx}_", ""]

    lines.append("*Trading Bots*")
    for key, cfg in BOTS.items():
        running = is_running(cfg["script"])
        uptime  = get_uptime(cfg["log"]) if running else "—"
        dot     = "🟢" if running else "🔴"
        lines.append(f"{dot} `{cfg['name']:<16}` {uptime}")

    lines.append("")
    lines.append("*System*")
    tg_running = is_running("telegram_bot.py")
    dot        = "🟢" if tg_running else "🔴"
    # Get telegram uptime from offset file modification time
    tg_uptime  = ""
    if tg_running and OFFSET_FILE.exists():
        import os
        try:
            mtime = os.path.getmtime(str(OFFSET_FILE))
            delta = datetime.utcnow().timestamp() - mtime
            h = int(delta // 3600)
            m = int((delta % 3600) // 60)
            tg_uptime = f"{h}h {m}m"
        except Exception:
            tg_uptime = "running"
    lines.append(f"{dot} `{'Telegram':<16}` {tg_uptime if tg_running else 'Stopped'}")

    return "\n".join(lines)


def cmd_balance() -> str:
    now_tx = datetime.now(TEXAS).strftime("%b %d  %I:%M %p CT")
    lines  = [f"💰 *Account Balances*  _{now_tx}_", ""]

    for key, cfg in BOTS.items():
        equity  = load_json(cfg["equity"])
        balance = get_balance(equity)
        start   = get_start_balance(equity)
        growth  = ((balance - start) / start * 100) if start > 0 else 0
        arrow   = "↑" if growth > 0 else "↓" if growth < 0 else "—"
        sign    = "+" if growth >= 0 else ""
        lines.append(f"`{cfg['name']:<16}` *${balance:,.2f}*  {arrow} {sign}{growth:.1f}%")

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


def cmd_report(force: bool = False, group: str | None = None) -> str:
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
            # Stage a weekend+group prompt
            pending_action["command"]    = lambda: _ask_report_group(force=True)
            pending_action["label"]      = "Weekend Report Group"
            pending_action["expires_at"] = datetime.utcnow() + timedelta(seconds=120)
            day = now_tx.strftime("%A")
            return (
                f"📅 It's {day} — gold markets are closed\\.\n\n"
                f"Reply /demo, /live, or /all to send a report anyway\\."
            )
        else:
            # Stage a group prompt
            pending_action["command"]    = lambda: _ask_report_group(force=False)
            pending_action["label"]      = "Report Group"
            pending_action["expires_at"] = datetime.utcnow() + timedelta(seconds=120)
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


def _ask_report_group(force: bool = False) -> str:
    """Called when user confirms a pending report — now ask for group."""
    pending_action["command"]    = lambda: _run_reporter(group="all", force=force)
    pending_action["label"]      = "Report (All)"
    pending_action["expires_at"] = datetime.utcnow() + timedelta(seconds=120)
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


def cmd_users(chat_id: str) -> str:
    """Admin only — list all authorized users."""
    users  = load_users()
    now_tx = datetime.now(TEXAS).strftime("%b %d  %I:%M %p CT")
    lines  = [f"*Users*  _{now_tx}_", ""]
    for uid, info in users.items():
        name  = info.get("name", "Unknown")
        role  = info.get("role", "readonly").upper()
        added = info.get("added", "")
        you   = " \u2190 you" if uid == chat_id else ""
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
        "_Bot keys: smc  reversion  scalper  fft_"
    )


# =============================================================================
# CONTROL COMMANDS
# =============================================================================

def request_confirm(command_fn, label: str) -> str:
    pending_action["command"]    = command_fn
    pending_action["label"]      = label
    pending_action["expires_at"] = datetime.utcnow() + timedelta(seconds=CONFIRM_TIMEOUT)
    return (
        f"⚠️ *Confirm Required*\n\n"
        f"Action: _{label}_\n\n"
        f"Send /confirm within {CONFIRM_TIMEOUT}s to proceed\\.\n"
        f"Any other message cancels\\."
    )


def cmd_confirm() -> str:
    if not pending_action["command"]:
        return "No pending action."
    if datetime.utcnow() > pending_action["expires_at"]:
        pending_action["command"] = None
        return "⏰ Confirmation timed out. Action cancelled."
    fn    = pending_action["command"]
    label = pending_action["label"]
    pending_action["command"] = None
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

def send_to(chat_id: str, text: str):
    """Send a message to a specific chat ID."""
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")


def handle_message(text: str, chat_id: str) -> str:
    parts = text.strip().split()
    cmd   = parts[0].lower() if parts else ""
    role  = get_role(chat_id)

    def denied() -> str:
        return "You do not have permission to use that command."

    if cmd == "/status":        return cmd_status() if can(chat_id, cmd) else denied()
    if cmd == "/balance":       return cmd_balance() if can(chat_id, cmd) else denied()
    if cmd == "/trades":        return cmd_trades() if can(chat_id, cmd) else denied()
    if cmd == "/report":        return cmd_report(force=False, group=None) if can(chat_id, cmd) else denied()
    if cmd == "/help":          return cmd_help()
    if cmd == "/users":         return cmd_users(chat_id) if can(chat_id, cmd) else denied()
    if cmd == "/confirm":       return cmd_confirm() if can(chat_id, cmd) else denied()

    # Report group shortcuts
    if cmd in ("/demo", "/live", "/all"):
        if not can(chat_id, cmd):
            return denied()
        group = cmd.lstrip("/")
        if pending_action["command"] and datetime.utcnow() <= pending_action["expires_at"]:
            pending_action["command"] = None
            return _run_reporter(group=group, force=True)
        return cmd_report(force=False, group=group)

    if cmd == "/force":
        if not can(chat_id, cmd):
            return denied()
        if pending_action["command"] and datetime.utcnow() <= pending_action["expires_at"]:
            fn = pending_action["command"]
            pending_action["command"] = None
            return fn()
        return "No pending action."

    if cmd == "/emergency":
        if not can(chat_id, cmd):
            return denied()
        return request_confirm(do_emergency_stop,
                               "Emergency Stop — kill all bots")

    if cmd == "/restart":
        if not can(chat_id, cmd):
            return denied()
        bot_key = parse_bot_key(parts)
        if bot_key:
            name = BOTS[bot_key]["name"]
            return request_confirm(lambda k=bot_key: do_restart([k]),
                                   f"Restart {name}")
        return request_confirm(lambda: do_restart(list(BOTS.keys())),
                               "Restart All Bots")

    if cmd == "/stop":
        if not can(chat_id, cmd):
            return denied()
        bot_key = parse_bot_key(parts)
        if bot_key:
            name = BOTS[bot_key]["name"]
            return request_confirm(lambda k=bot_key: do_stop([k]),
                                   f"Stop {name}")
        return request_confirm(lambda: do_stop(list(BOTS.keys())),
                               "Stop All Bots")

    if pending_action["command"]:
        pending_action["command"] = None
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
                msg  = update.get("message", {})
                text = msg.get("text", "").strip()
                chat = str(msg.get("chat", {}).get("id", ""))
                if not text:
                    continue

                # Check authorization
                role = get_role(chat)
                if not role:
                    from_user = msg.get("from", {})
                    username  = from_user.get("username", "unknown")
                    name      = from_user.get("first_name", "")
                    print(f"UNAUTHORIZED: chat={chat} user=@{username} ({name}) text={text[:50]}")
                    # Send one-time rejection so they know it's locked
                    send_to(chat, "This bot is private. You are not authorized.")
                    continue
                response = handle_message(text, chat)
                send(response)
        except Exception as e:
            print(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
