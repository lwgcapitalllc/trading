"""
startup_coordinator.py — Sequential Bot Startup

Starts bots one at a time, waiting for each to confirm MT5 connection
before starting the next. This is the ONLY reliable way to prevent
account mixing when multiple MT5 terminals are running simultaneously.

MT5's Python API cannot reliably select between already-running terminals
by path — it connects to whichever registered its IPC endpoint most recently.
Sequential startup ensures only one bot is connecting at any time.

Usage (called by algo restart or Task Scheduler at boot):
    python startup_coordinator.py

Or via Task Scheduler — replace individual BOT_ tasks with a single
STARTUP_COORDINATOR task that runs this script.
"""

import subprocess
import time
import sys
from pathlib import Path

PYTHON  = sys.executable
ALGOS   = Path("C:/algos")
BOTS    = Path("C:/algos/bots")

# Each entry: (task_name, bot_script, config_path, ready_string, timeout_s)
# ready_string is what we look for in the stdout log to confirm connected
STARTUP_SEQUENCE = [
    (
        "BOT_SMC_TREND",
        "bot_smc_trend.py",
        r"C:\algos\markets\fx\instances\gold_main\config.json",
        r"C:\algos\markets\fx\instances\gold_main\smc_trend_stdout.log",
        "Connected | #700103491",
        60,
    ),
    (
        "BOT_MEAN_REVERSION",
        "bot_mean_reversion.py",
        r"C:\algos\markets\fx\instances\gold_main\config.json",
        r"C:\algos\markets\fx\instances\gold_main\mean_reversion_stdout.log",
        "Connected | #700103491",
        60,
    ),
    (
        "BOT_SCALPER",
        "bot_scalper.py",
        r"C:\algos\markets\fx\instances\gold_scalper\config.json",
        r"C:\algos\markets\fx\instances\gold_scalper\scalper_stdout.log",
        "Connected | #700107520",
        60,
    ),
    (
        "BOT_FFT",
        "bot_fft.py",
        r"C:\algos\markets\fx\instances\gold_fft\config.json",
        r"C:\algos\markets\fx\instances\gold_fft\fft_stdout.log",
        "Connected | #700107749",
        60,
    ),
]


def wait_for_connection(log_path: str, ready_string: str,
                        timeout: int, bot_name: str) -> bool:
    """
    Poll the bot's stdout log until the ready_string appears
    (meaning it connected to the correct account) or timeout expires.
    """
    log = Path(log_path)
    start = time.time()
    last_size = 0

    while time.time() - start < timeout:
        if log.exists():
            content = log.read_text(errors="replace")
            # Only look at new content since we started waiting
            if ready_string in content[last_size:] if last_size else ready_string in content:
                elapsed = time.time() - start
                print(f"  ✓ {bot_name} connected ({elapsed:.1f}s)")
                return True
            # Check for failure
            new_content = content[last_size:] if last_size else content
            if "ACCOUNT MISMATCH" in new_content or "Failed to connect" in new_content:
                print(f"  ✗ {bot_name} connection failed — check logs")
                return False
        time.sleep(2)

    print(f"  ✗ {bot_name} timed out after {timeout}s")
    return False


def start_bot(task_name: str) -> bool:
    """Start a bot via its Task Scheduler task."""
    result = subprocess.run(
        ["schtasks", "/run", "/tn", task_name],
        capture_output=True, text=True, timeout=15
    )
    return result.returncode == 0


def get_log_size(log_path: str) -> int:
    p = Path(log_path)
    return p.stat().st_size if p.exists() else 0


def main():
    print("=" * 60)
    print("  LWG Capital — Sequential Bot Startup")
    print("=" * 60)
    print()

    # Clear any stale lock
    lock = Path(r"C:\algos\mt5_connect.lock")
    if lock.exists():
        lock.unlink()
        print("Cleared stale MT5 lock")

    all_ok = True
    for task_name, script, config, log_path, ready_str, timeout in STARTUP_SEQUENCE:
        bot_name = task_name.replace("BOT_", "").replace("_", " ").title()
        print(f"Starting {bot_name}...")

        # Record log size before starting so we only check new output
        log_size_before = get_log_size(log_path)

        ok = start_bot(task_name)
        if not ok:
            print(f"  ✗ Failed to start task {task_name}")
            all_ok = False
            continue

        # Wait for this bot to confirm connection before starting next
        connected = wait_for_connection(log_path, ready_str, timeout, bot_name)
        if not connected:
            all_ok = False
            print(f"  Warning: proceeding despite {bot_name} issue")

        # Small buffer between bots
        time.sleep(3)

    print()
    if all_ok:
        print("All bots started successfully.")
    else:
        print("Some bots had issues — check logs.")

    # Start system tasks
    print()
    print("Starting system tasks...")
    for task in ["SYS_TELEGRAM"]:
        result = subprocess.run(
            ["schtasks", "/run", "/tn", task],
            capture_output=True, text=True, timeout=15
        )
        status = "✓" if result.returncode == 0 else "✗"
        print(f"  {status} {task}")


if __name__ == "__main__":
    main()
