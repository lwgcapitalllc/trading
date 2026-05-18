"""
startup_coordinator.py — Sequential Bot Startup

Starts bots one at a time by launching Python directly (not via schtasks).
Waits for each bot to confirm MT5 connection before starting the next.
This prevents account mixing from simultaneous MT5 connections.

Run via SYS_STARTUP task at boot, or manually:
    python C:/algos/bots/startup_coordinator.py
"""

import subprocess
import sys
import time
from pathlib import Path

PYTHON = sys.executable
ALGOS  = Path("C:/algos")
BOTS   = Path("C:/algos/bots")

# (bot_name, script, config, stdout_log, ready_string, timeout_s)
STARTUP_SEQUENCE = [
    (
        "SMC Trend",
        r"C:\algos\bots\bot_smc_trend.py",
        r"C:\algos\markets\fx\instances\gold_main\config.json",
        r"C:\algos\markets\fx\instances\gold_main\smc_trend_stdout.log",
        "Connected | #700103491",
        90,
    ),
    (
        "Mean Reversion",
        r"C:\algos\bots\bot_mean_reversion.py",
        r"C:\algos\markets\fx\instances\gold_main\config.json",
        r"C:\algos\markets\fx\instances\gold_main\mean_reversion_stdout.log",
        "Connected | #700103491",
        90,
    ),
    (
        "Scalper",
        r"C:\algos\bots\bot_scalper.py",
        r"C:\algos\markets\fx\instances\gold_scalper\config.json",
        r"C:\algos\markets\fx\instances\gold_scalper\scalper_stdout.log",
        "Connected | #700107520",
        90,
    ),
    (
        "FFT",
        r"C:\algos\bots\bot_fft.py",
        r"C:\algos\markets\fx\instances\gold_fft\config.json",
        r"C:\algos\markets\fx\instances\gold_fft\fft_stdout.log",
        "Connected | #700107749",
        90,
    ),
]


def get_log_size(log_path: str) -> int:
    p = Path(log_path)
    return p.stat().st_size if p.exists() else 0


def wait_for_connection(log_path: str, ready_string: str,
                        size_before: int, timeout: int, name: str) -> bool:
    """Poll log for ready_string in content written AFTER we started the bot."""
    start = time.time()
    while time.time() - start < timeout:
        p = Path(log_path)
        if p.exists():
            content = p.read_text(errors="replace")
            new_content = content[size_before:]
            if ready_string in new_content:
                elapsed = time.time() - start
                print(f"  ✓ {name} connected ({elapsed:.0f}s)")
                return True
            if "ACCOUNT MISMATCH" in new_content:
                print(f"  ✗ {name} account mismatch — check logs")
                return False
            if "Failed to connect" in new_content:
                print(f"  ✗ {name} failed to connect")
                return False
        time.sleep(2)
    print(f"  ✗ {name} timed out after {timeout}s")
    return False


def main():
    print("=" * 60)
    print("  LWG Capital — Sequential Bot Startup")
    print("=" * 60)
    print()

    # Clear stale lock
    lock = Path(r"C:\algos\mt5_connect.lock")
    if lock.exists():
        lock.unlink()
        print("Cleared stale MT5 lock\n")

    processes = []
    all_ok = True

    for name, script, config, log_path, ready_str, timeout in STARTUP_SEQUENCE:
        print(f"Starting {name}...")
        size_before = get_log_size(log_path)

        # Launch bot directly — not via Task Scheduler
        proc = subprocess.Popen(
            [PYTHON, script, "--config", config],
            cwd=str(BOTS),
            creationflags=0x00000008,  # DETACHED_PROCESS on Windows
        )
        processes.append(proc)

        connected = wait_for_connection(log_path, ready_str, size_before, timeout, name)
        if not connected:
            all_ok = False

        # Small buffer between bots
        time.sleep(2)

    print()
    print("=" * 60)
    if all_ok:
        print("  All bots started successfully.")
    else:
        print("  Some bots had issues — check logs.")
    print("=" * 60)

    # Start Telegram
    print("\nStarting Telegram bot...")
    subprocess.Popen(
        [PYTHON, str(ALGOS / "notifications/start_telegram.py")],
        cwd=str(ALGOS)
    )
    print("  ✓ Telegram started")


if __name__ == "__main__":
    main()
