"""
startup_coordinator.py — Sequential Bot Startup with Terminal Reset

The ONLY reliable way to prevent MT5 account mixing when multiple
terminals are running:

1. Kill ALL terminal64.exe processes first
2. Start each bot one at a time — bot launches its own terminal via mt5_path
3. Wait for connection confirmed before starting the next bot

When a terminal is NOT running, mt5.initialize(path=...) launches it
fresh and is 100% reliable. The IPC race only happens when terminals
are already running simultaneously.

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

# Sequential startup order
# (display_name, script, config, stdout_log, ready_string, timeout_s)
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


def kill_all_terminals():
    """
    Kill ALL MT5 terminal64.exe processes.
    This is essential — when terminals are not running, mt5.initialize(path=...)
    launches the correct one fresh, making account assignment 100% reliable.
    """
    print("Killing all MT5 terminals...")
    result = subprocess.run(
        ["taskkill", "/f", "/im", "terminal64.exe"],
        capture_output=True, text=True
    )
    if "SUCCESS" in result.stdout or "not found" in result.stderr.lower():
        print("  ✓ MT5 terminals cleared")
    else:
        print(f"  (No terminals were running)")
    time.sleep(3)  # Give Windows time to fully release IPC handles


def clear_lock():
    lock = Path(r"C:\algos\mt5_connect.lock")
    if lock.exists():
        lock.unlink()
        print("  ✓ Cleared stale MT5 lock")


def get_log_size(log_path: str) -> int:
    p = Path(log_path)
    return p.stat().st_size if p.exists() else 0


def wait_for_connection(log_path: str, ready_string: str,
                        size_before: int, timeout: int, name: str) -> bool:
    """
    Poll the stdout log for the ready string in content written after bot started.
    Returns True if connected, False if timeout or error.
    """
    start = time.time()
    while time.time() - start < timeout:
        p = Path(log_path)
        if p.exists():
            try:
                content = p.read_text(errors="replace")
                new_content = content[size_before:]
                if ready_string in new_content:
                    elapsed = time.time() - start
                    print(f"  ✓ {name} connected in {elapsed:.0f}s")
                    return True
                if "ACCOUNT MISMATCH" in new_content:
                    print(f"  ✗ {name} account mismatch — retrying")
                    return False
                if "Failed to connect" in new_content:
                    print(f"  ✗ {name} failed to connect")
                    return False
            except Exception:
                pass
        time.sleep(2)

    print(f"  ✗ {name} timed out after {timeout}s")
    return False


def main():
    print("=" * 60)
    print("  LWG Capital — Sequential Bot Startup")
    print("=" * 60)
    print()

    # Step 1: Kill all terminals so each bot gets a fresh launch
    kill_all_terminals()
    clear_lock()
    print()

    all_ok = True

    for name, script, config, log_path, ready_str, timeout in STARTUP_SEQUENCE:
        print(f"Starting {name}...")

        # Record log size before starting
        size_before = get_log_size(log_path)

        # Launch bot — it will call mt5.initialize(path=...) which launches
        # its specific terminal fresh since all terminals are now closed
        proc = subprocess.Popen(
            [PYTHON, script, "--config", config],
            cwd=str(BOTS),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        # Wait for connection confirmed before starting next bot
        connected = wait_for_connection(log_path, ready_str, size_before, timeout, name)
        if not connected:
            all_ok = False
            print(f"  Warning: {name} did not confirm connection. Proceeding anyway.")

        # Short pause between bots — gives MT5 terminal time to fully register
        print()
        time.sleep(5)

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
        cwd=str(ALGOS),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    print("  ✓ Telegram started")
    print("\nStartup complete.")


if __name__ == "__main__":
    main()
