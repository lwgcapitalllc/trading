"""
start_telegram.py — Telegram Bot Launcher with Single-Instance Guard

Kills any existing telegram_bot.py process before starting a new one.
This prevents duplicate instances when the task is restarted manually.
Called by SYS_TELEGRAM Task Scheduler task instead of telegram_bot.py directly.
"""

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ALGOS = Path("C:/trading/algos")


def kill_existing():
    """Kill any running telegram_bot.py process."""
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "processid,commandline"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.splitlines():
            if "telegram_bot.py" in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid.isdigit():
                    subprocess.run(["taskkill", "/f", "/pid", pid], capture_output=True, timeout=5)
                    print(f"Killed existing telegram_bot.py (PID {pid})")
                    time.sleep(2)
    except Exception as e:
        print(f"Kill check error: {e}")


def main():
    kill_existing()
    import json as _json

    (ALGOS / "telegram_start.json").write_text(
        _json.dumps({"started": datetime.now(timezone.utc).timestamp()})
    )
    print("Starting telegram_bot.py...")
    script = ALGOS / "notifications" / "telegram_bot.py"
    python = sys.executable
    # Replace current process with telegram_bot.py
    subprocess.run([python, str(script)], cwd=str(ALGOS))


if __name__ == "__main__":
    main()
