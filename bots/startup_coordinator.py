"""
startup_coordinator.py — Sequential Bot Startup

Strategy:
1. Kill all MT5 terminals (terminal64.exe)
2. For each terminal group:
   a. Launch the MT5 terminal executable directly
   b. Wait for it to be ready (15s)
   c. Start the bot(s) for that terminal
   d. Wait for bot to confirm connection before moving to next group

This is the ONLY reliable approach:
- Coordinator (not the bot) launches the terminal
- Terminal is already running when bot calls mt5.initialize(path=...)
- No IPC race — each terminal is ready before its bot starts

Run via SYS_STARTUP task at boot:
    python C:/algos/bots/startup_coordinator.py
"""

import subprocess
import sys
import time
from pathlib import Path

PYTHON = sys.executable
ALGOS  = Path("C:/algos")
BOTS   = Path("C:/algos/bots")

# Terminal paths
MT5_MAIN    = r"C:\Program Files\PU Prime MT5 Terminal\terminal64.exe"
MT5_SCALPER = r"C:\MT5_Scalper\terminal64.exe"
MT5_FFT     = r"C:\MT5_FFT\terminal64.exe"

# Startup groups — each group shares a terminal
# (terminal_exe, terminal_ready_wait, [(name, script, config, log, ready_str, timeout)])
STARTUP_GROUPS = [
    (
        MT5_MAIN, 20,
        [
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
        ]
    ),
    (
        MT5_SCALPER, 20,
        [
            (
                "Scalper",
                r"C:\algos\bots\bot_scalper.py",
                r"C:\algos\markets\fx\instances\gold_scalper\config.json",
                r"C:\algos\markets\fx\instances\gold_scalper\scalper_stdout.log",
                "Connected | #700107520",
                90,
            ),
        ]
    ),
    (
        MT5_FFT, 20,
        [
            (
                "FFT",
                r"C:\algos\bots\bot_fft.py",
                r"C:\algos\markets\fx\instances\gold_fft\config.json",
                r"C:\algos\markets\fx\instances\gold_fft\fft_stdout.log",
                "Connected | #700107749",
                90,
            ),
        ]
    ),
]


def kill_all_terminals():
    print("Killing all MT5 terminals...")
    subprocess.run(
        ["taskkill", "/f", "/im", "terminal64.exe"],
        capture_output=True, text=True
    )
    time.sleep(3)
    print("  ✓ Terminals cleared")


def clear_lock():
    lock = Path(r"C:\algos\mt5_connect.lock")
    if lock.exists():
        lock.unlink()
        print("  ✓ Cleared stale MT5 lock")


def launch_terminal(exe_path: str, wait_seconds: int):
    """Launch MT5 terminal and wait for it to be ready."""
    print(f"  Launching {Path(exe_path).parent.name}...")
    subprocess.Popen(
        [exe_path],
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    print(f"  Waiting {wait_seconds}s for terminal to be ready...")
    time.sleep(wait_seconds)
    print(f"  ✓ Terminal ready")


def get_log_size(log_path: str) -> int:
    p = Path(log_path)
    return p.stat().st_size if p.exists() else 0


def wait_for_connection(log_path: str, ready_string: str,
                        size_before: int, timeout: int, name: str) -> bool:
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
                    print(f"  ✗ {name} account mismatch")
                    return False
                if "Failed to connect" in new_content:
                    print(f"  ✗ {name} failed to connect")
                    return False
            except Exception:
                pass
        time.sleep(2)
    print(f"  ✗ {name} timed out after {timeout}s")
    return False


def start_bot(script: str, config: str) -> subprocess.Popen:
    return subprocess.Popen(
        [PYTHON, script, "--config", config],
        cwd=str(BOTS),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def main():
    print("=" * 60)
    print("  LWG Capital — Sequential Bot Startup")
    print("=" * 60)
    print()

    kill_all_terminals()
    clear_lock()
    print()

    all_ok = True

    for terminal_exe, ready_wait, bots in STARTUP_GROUPS:
        print(f"--- {Path(terminal_exe).parent.name} ---")

        # Step 1: Launch terminal
        launch_terminal(terminal_exe, ready_wait)

        # Step 2: Start each bot for this terminal
        for name, script, config, log_path, ready_str, timeout in bots:
            print(f"Starting {name}...")
            size_before = get_log_size(log_path)
            start_bot(script, config)
            connected = wait_for_connection(log_path, ready_str, size_before, timeout, name)
            if not connected:
                all_ok = False
            time.sleep(3)

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
        cwd=str(ALGOS),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    print("  ✓ Telegram started")
    print("\nStartup complete.")


if __name__ == "__main__":
    main()
