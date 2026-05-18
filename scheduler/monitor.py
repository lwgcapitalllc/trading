"""
monitor.py — Bot Health Watchdog

Runs every 1 minute via SYS_MONITOR task.
Monitors bot processes and updates bot_state.json status field.
Sends Telegram alerts on status changes.

P&L alerts are handled by pnl_tracker.py — monitor only handles:
- Bot online/offline detection
- Telegram bot watchdog with auto-restart
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

sys.path.insert(0, str(Path("C:/algos/shared")))
from bot_state import (
    BOT_NAMES, read_bot, set_status, write_bot, read_all
)

TELEGRAM_TOKEN = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
ADMIN_CHAT     = "429207285"
ALGOS_ROOT     = Path("C:/algos")
TEXAS          = ZoneInfo("America/Chicago")

BOT_SCRIPTS = {
    "smc_trend":      "bot_smc_trend.py",
    "mean_reversion": "bot_mean_reversion.py",
    "scalper":        "bot_scalper.py",
    "fft":            "bot_fft.py",
}


def send_alert(message: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"Alert failed: {e}")


def is_running(script: str) -> bool:
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=10
        )
        return script in result.stdout
    except Exception:
        return False


def check_bot(bot_key: str):
    """Check one bot — update status in bot_state, alert on change."""
    script    = BOT_SCRIPTS[bot_key]
    name      = BOT_NAMES[bot_key]
    state     = read_bot(bot_key)
    running   = is_running(script)
    prev_status = state.get("status", "stopped")
    now_str   = datetime.now(TEXAS).strftime("%I:%M %p CT")

    if running:
        new_status = "running"
        if prev_status == "offline":
            send_alert(
                f"🟢 *ALERT — Bot Online*\n"
                f"{name} is running again\n"
                f"Time: {now_str}"
            )
    else:
        new_status = "offline"
        if prev_status == "running":
            send_alert(
                f"🚨 *ALERT — Bot Offline*\n"
                f"{name} stopped unexpectedly\n"
                f"Time: {now_str}\n"
                f"Action: run `algo restart` or use /restart"
            )

    if new_status != prev_status:
        set_status(bot_key, new_status)

    print(f"{bot_key}: {new_status}")


def check_telegram_bot():
    """Watchdog for Telegram bot — auto-restart up to 3 times."""
    running = is_running("telegram_bot.py")
    now_str = datetime.now(TEXAS).strftime("%I:%M %p CT")

    # Read restart state from a simple file
    state_file = ALGOS_ROOT / "telegram_monitor_state.json"
    import json
    try:
        tg_state = json.loads(state_file.read_text()) if state_file.exists() else {}
    except Exception:
        tg_state = {}

    if not running:
        tries = tg_state.get("restart_tries", 0)
        print(f"Telegram bot DOWN — attempt {tries+1}/3")

        if tries < 3:
            result = subprocess.run(
                ["schtasks", "/run", "/tn", "SYS_TELEGRAM"],
                capture_output=True, text=True, timeout=15
            )
            import time; time.sleep(5)
            if is_running("telegram_bot.py"):
                print("Telegram restarted OK")
                send_alert(
                    f"🟢 *ALERT — Telegram Bot Restarted*\n"
                    f"Was offline. Auto-restarted at {now_str}.\n"
                    f"Commands are available again."
                )
                tg_state = {"restart_tries": 0, "running": True}
            else:
                tg_state["restart_tries"] = tries + 1
        else:
            if not tg_state.get("max_retry_alerted"):
                send_alert(
                    f"🚨 *CRITICAL — Telegram Bot Down*\n"
                    f"Failed after 3 restart attempts.\n"
                    f"Manual action required.\n"
                    f"Time: {now_str}"
                )
                tg_state["max_retry_alerted"] = True
    else:
        tg_state = {"restart_tries": 0, "running": True, "max_retry_alerted": False}

    state_file.write_text(json.dumps(tg_state))


def main():
    # Telegram watchdog first
    try:
        check_telegram_bot()
    except Exception as e:
        print(f"Telegram watchdog error: {e}")

    # Check each bot
    for bot_key in BOT_SCRIPTS:
        try:
            check_bot(bot_key)
        except Exception as e:
            print(f"Error checking {bot_key}: {e}")

    print(f"Monitor done — {datetime.now(TEXAS).strftime('%I:%M %p CT')}")


if __name__ == "__main__":
    main()
