"""
telegram_bot.py — Telegram Command Handler
Location: notifications/telegram_bot.py

COMMANDS — all read-only:
  /status    — what is running, and for how long
  /balance   — account balance and P&L
  /help      — the command list
  /users     — who is authorized (admin only)

🔴 **There are no control commands here, deliberately (2026-08-05).** `/restart`, `/stop`,
`/emergency`, `/trades`, `/resume`, `/resetweek` and `/confirm` were deleted because not one of
them could do anything: `BOTS` and `TASK_NAMES` had been empty dicts since the June bot deletion,
and `/restart` and `/stop` therefore asked for a confirmation, acted on an empty list, and
reported SUCCESS. A control that appears to work is worse than a missing one. See
`handle_message` for the per-command reasoning.

Starting and stopping a bot is done from the command center, which can see how many copies are
running — the guard that stops a duplicate bot lives with the process, not with the button.

Run via Task Scheduler at startup (runs 24/7).
Install: pip install requests
"""

# `str | None` needs 3.10 at runtime; the VPS runs 3.11 and the test machine 3.9, so this file
# was importable on the box and not on a Mac. It had no tests until 2026-08-05, which is the only
# reason nobody hit it.
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

ALGOS_ROOT      = Path("C:/trading/algos")
# Telegram credentials are resolved from the environment or the git-ignored
# algos/credentials.json — never pasted here. See algos/shared/credentials.py.
# ADMIN_CHAT is the primary admin — always has access even if users.json is missing.
sys.path.insert(0, str(ALGOS_ROOT / "shared"))
from credentials import telegram_credentials  # noqa: E402
from notify import chat_for, HEALTH            # noqa: E402
from alert_format import alert                 # noqa: E402

TELEGRAM_TOKEN, GROUP_CHAT, ADMIN_CHAT = telegram_credentials()
USERS_FILE      = ALGOS_ROOT / "users.json"
OFFSET_FILE     = ALGOS_ROOT / "telegram_offset.json"
TELEGRAM_START  = ALGOS_ROOT / "telegram_start.json"
PID_FILE        = ALGOS_ROOT / "telegram_bot.pid"
TEXAS           = ZoneInfo("America/Chicago")
POLL_INTERVAL   = 10

# Commands allowed per role.
# ⚠ `/report`, `/demo`, `/live`, `/all` and `/force` were removed 2026-08-05 with
# `reporter.py`. The group shortcuts existed ONLY to pick an account set for a report, and
# `/force` only to push one out on a weekend — leaving any of them in this set would grant
# a role a command that no longer dispatches, which reads as a working permission.
ROLE_COMMANDS = {
    "admin":    {"/status", "/balance", "/help", "/users"},
    "readonly": {"/status", "/balance", "/help"},
}





_CRASH_CHECK_INTERVAL = 6   # kept for poll_count modulo — crash alerting is in monitor.py




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
    """Broadcast the startup ping — HEALTH, because it is this process announcing itself.

    Command REPLIES do not come through here; they go to `send_to`, addressed to whichever chat
    asked. That is deliberate and is not a routing decision at all: an answer belongs where the
    question was asked, and a `/balance` typed in the trades group would be baffling if the reply
    landed somewhere else.
    """
    dest, _dedicated = chat_for(HEALTH)
    if not TELEGRAM_TOKEN or not dest:
        print(f"Send dropped (Telegram not configured): {text[:80]}")
        return
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": dest, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")


def send_to(chat_id: str, text: str):
    """Reply to a specific chat — the one the command came from. Not routed by kind; see `send`."""
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



def acquire_singleton():
    """Exit immediately if another telegram_bot instance is already running.

    Checks the PID file and verifies the stored PID still belongs to a
    telegram_bot process.  Stale PID files (from a hard kill) are ignored.
    """
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            r = subprocess.run(
                ["wmic", "process", "where", f"processid={old_pid}", "get", "commandline"],
                capture_output=True, text=True, timeout=5
            )
            if "telegram_bot" in r.stdout:
                print(f"Another telegram_bot is already running (PID {old_pid}). Exiting.")
                sys.exit(0)
        except Exception:
            pass
    PID_FILE.write_text(str(os.getpid()))


def release_singleton():
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def is_running(script: str) -> bool:
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=10
        )
        return script in r.stdout
    except Exception:
        return False












# =============================================================================
# BOT CONTROL
# =============================================================================











# =============================================================================
# READ-ONLY COMMANDS
# =============================================================================

def cmd_status() -> str:
    """What is running, read off the bots' OWN state files rather than a registry in this file.

    🔴 It used to walk a `BOT_SCRIPTS = {}` literal defined two lines above the loop, so it could
    not list a trading bot at all — it printed a "Trading Bots" heading with nothing under it and
    then reported on the Telegram bot. `bot_state.read_all()` is written by the live runner every
    poll, so a bot appears here by RUNNING, which is the only registry that cannot go stale.

    ⚠ Three separate facts, never merged: the process exists, the heartbeat is fresh, and the MT5
    link is up. A bot can be alive and blind — that is exactly what happened on 2026-08-04, when
    the terminal restarted underneath it and every check in the system still said RUNNING.
    """
    from bot_state import read_all, get_uptime_str

    states = read_all()
    bots = {k: v for k, v in states.items() if isinstance(v, dict) and v.get("name")}
    lines = []

    if not bots:
        lines.append("No bot has written a state file. Either none is running, or none can write.")
    for key, st in sorted(bots.items()):
        alive = is_running(f"--bot {key}")
        # `mt5_link` is Optional[bool]: None means the bot never said, which is not the claim
        # "disconnected". Read `is False`, never falsy — the same rule the Bots page follows.
        blind = st.get("mt5_link") is False
        dot = "🔴" if not alive else ("🟠" if blind else "🟢")
        bits = [st["name"], "stopped" if not alive else get_uptime_str(key)]
        if alive and blind:
            bits.append("no MT5 link")
        bal = st.get("balance")
        if alive and bal is not None:
            bits.append(f"${bal:,.2f}")
        lines.append(f"{dot} " + " · ".join(str(b) for b in bits))

    tg = "🟢 Telegram bot · running" if is_running("telegram_bot.py") else "🔴 Telegram bot · stopped"
    lines.append(tg)
    return "\n".join(lines)


def cmd_balance() -> str:
    sys.path.insert(0, str(ALGOS_ROOT / "shared"))
    from bot_state import read_all, BOT_NAMES
    now_tx = datetime.now(TEXAS).strftime("%b %d  %I:%M %p CT")
    lines  = [f"💰 *Account Balances*  _{now_tx}_", ""]
    all_states = read_all()
    for key, state in all_states.items():
        # ⚠ Both of these are read WITHOUT a numeric default, and that is the point.
        # `.get("balance", ...)` and `.get("total_pnl_pct", 0.0)` printed "$0.00 — +0.0%"
        # for a bot whose terminal had gone (a blind link returns no balance) and, until
        # 2026-08-05, for EVERY bot at every moment: `total_pnl_pct` was written by
        # `pnl_tracker.py`, which had been deleted, so this line reported dead flat on a
        # live account. A number nobody measured must not be printed as a measurement.
        balance = state.get("balance")
        pct     = state.get("total_pnl_pct")
        name    = BOT_NAMES.get(key, key)
        if balance is None:
            lines.append(f"`{name:<16}` _no MT5 link_")
            continue
        if pct is None:
            lines.append(f"`{name:<16}` *${balance:,.2f}*")
            continue
        arrow = "↑" if pct > 0 else "↓" if pct < 0 else "—"
        sign  = "+" if pct >= 0 else ""
        lines.append(f"`{name:<16}` *${balance:,.2f}*  {arrow} {sign}{pct:.1f}%")
    return "\n".join(lines)




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
    """Only what exists. A help text is a promise, and the previous one listed nine commands
    that could not work — which is how you find out at the moment you need one."""
    return (
        "*LWG Capital — Commands*\n\n"
        "`/status`   what is running, and for how long\n"
        "`/balance`  account balance and P&L\n"
        "`/help`     this list\n"
        "`/users`    who can use this bot (admin)\n\n"
        "_Starting, stopping and restarting a bot is done from the command center, "
        "which can see how many copies are actually running._"
    )





# =============================================================================
# MESSAGE ROUTER
# =============================================================================

def handle_message(text: str, chat_id: str, user_id: str) -> str:
    """
    chat_id — where to reply (group id or DM id)
    user_id — who sent it (their personal Telegram user id, used for auth)

    🔴 **Six commands were deleted on 2026-08-05 because none of them could do anything, and two
    of them said they had.** `BOTS` and `TASK_NAMES` had been empty dicts since the four
    first-attempt bots were deleted in June, so `/restart` and `/stop` asked for a confirmation,
    acted on an empty list, and reported success — a control that looks like it worked is worse
    than one that is missing. `/trades` read a per-bot trades file the live runner has never
    written, so it always answered zero. `/resume` and `/resetweek` drove `day_locked` and the
    weekly counters, which `pnl_tracker.py` used to write and nothing has written since it was
    deleted. `/emergency` matched on the same empty registry.

    `/confirm` went with them, and that is the subtle one: with no control command left, nothing
    can create a pending action, so it could only ever reply "No pending action." Keeping it
    would have left exactly the defect being removed, one level quieter.

    ⚠ **Control lives in the command center**, where the Bots page can see how many copies of a
    bot are actually running. That is not a limitation of this file — it is the reason the guard
    against starting a duplicate had to live in `startup_coordinator.py` too (2026-08-04). A
    phone command that cannot count processes cannot be made safe by adding a confirmation step.
    """
    parts = text.strip().split()
    cmd   = parts[0].lower() if parts else ""

    def denied() -> str:
        return "You do not have permission to use that command."

    if cmd == "/status":        return cmd_status() if can(user_id, cmd) else denied()
    if cmd == "/balance":       return cmd_balance() if can(user_id, cmd) else denied()
    if cmd == "/help":          return cmd_help()
    if cmd == "/users":         return cmd_users(user_id) if can(user_id, cmd) else denied()

    return f"Unknown command: {cmd}\nSend /help for the list."


def main():
    acquire_singleton()
    print(f"Telegram bot started — polling every {POLL_INTERVAL}s")
    try:
        send(alert("🟢", "COMMANDS ONLINE", "Telegram bot",
                   "It is listening again. Send /help for the list."))
        offset     = load_offset()
        poll_count = 0

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

                poll_count += 1

            except Exception as e:
                print(f"Poll error: {e}")
            time.sleep(POLL_INTERVAL)
    finally:
        release_singleton()


if __name__ == "__main__":
    main()
