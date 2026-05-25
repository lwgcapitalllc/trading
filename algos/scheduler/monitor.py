"""
monitor.py — Telegram Bot Watchdog

Runs every 1 minute via SYS_MONITOR task.

Bot health monitoring (online/offline detection) is now event-driven:
  - Bots self-report on startup via shared/notify.py
  - telegram_bot.py detects crashes within ~60s via its poll loop
  - algo.py sends immediate notifications for control panel actions

This script only handles the one case that can't be event-driven:
the Telegram bot itself going offline (it can't watch itself).
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path("C:/trading/algos/shared")))
from notify import send_telegram

ALGOS_ROOT = Path("C:/trading/algos")
TEXAS      = ZoneInfo("America/Chicago")


def is_running(script: str) -> bool:
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=10
        )
        return script in result.stdout
    except Exception:
        return False


def check_telegram_bot():
    """Watchdog for Telegram bot — auto-restart up to 3 times."""
    running = is_running("telegram_bot.py")
    now_str = datetime.now(TEXAS).strftime("%I:%M %p CT")

    state_file = ALGOS_ROOT / "telegram_monitor_state.json"
    try:
        tg_state = json.loads(state_file.read_text()) if state_file.exists() else {}
    except Exception:
        tg_state = {}

    if not running:
        tries = tg_state.get("restart_tries", 0)
        print(f"Telegram bot DOWN — attempt {tries+1}/3")

        if tries < 3:
            subprocess.run(
                ["schtasks", "/run", "/tn", "SYS_TELEGRAM"],
                capture_output=True, text=True, timeout=15
            )
            import time; time.sleep(5)
            if is_running("telegram_bot.py"):
                print("Telegram restarted OK")
                send_telegram(
                    f"🟢 *ALERT — Telegram Bot Restarted*\n"
                    f"Was offline. Auto-restarted at {now_str}.\n"
                    f"Commands are available again."
                )
                tg_state = {"restart_tries": 0, "running": True}
            else:
                tg_state["restart_tries"] = tries + 1
        else:
            if not tg_state.get("max_retry_alerted"):
                send_telegram(
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
    try:
        check_telegram_bot()
    except Exception as e:
        print(f"Telegram watchdog error: {e}")

    print(f"Monitor done — {datetime.now(TEXAS).strftime('%I:%M %p CT')}")


if __name__ == "__main__":
    main()
