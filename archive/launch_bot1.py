"""
launch_bot1.py — Auto-launcher for Bot 1
Used by Windows Task Scheduler to start Bot 1 without needing keyboard input.
"""
import subprocess
import sys
from pathlib import Path

ALGOS_DIR = Path(__file__).parent
BOT1      = str(ALGOS_DIR / "bot1_smc_trend.py")
LOG_OUT   = str(ALGOS_DIR / "bot1_stdout.log")

with open(LOG_OUT, "a", encoding="utf-8") as out:
    proc = subprocess.Popen(
        [sys.executable, BOT1],
        stdin=subprocess.PIPE,
        stdout=out,
        stderr=out,
        cwd=str(ALGOS_DIR),
    )
    proc.stdin.write(b"CONFIRM\n")
    proc.stdin.flush()
    proc.stdin.close()
    proc.wait()   # keep this process alive until bot exits
