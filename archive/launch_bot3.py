"""
launch_bot3.py — Auto-launcher for Bot 3 Scalper
Used by Windows Task Scheduler.
"""
import subprocess, sys
from pathlib import Path

ALGOS_DIR = Path(__file__).parent
BOT3      = str(ALGOS_DIR / "bot3_scalper.py")
LOG_OUT   = str(ALGOS_DIR / "bot3_stdout.log")

with open(LOG_OUT, "a", encoding="utf-8") as out:
    proc = subprocess.Popen(
        [sys.executable, BOT3],
        stdin=subprocess.PIPE,
        stdout=out,
        stderr=out,
        cwd=str(ALGOS_DIR),
    )
    proc.stdin.write(b"CONFIRM\n")
    proc.stdin.flush()
    proc.stdin.close()
    proc.wait()
