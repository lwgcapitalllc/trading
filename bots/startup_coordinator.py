"""
startup_coordinator.py — Sequential Bot Startup

Does NOT kill or launch MT5 terminals — that causes Session 0 isolation
issues on Windows (scheduled tasks cannot launch GUI applications).

MT5 terminals must already be running with the correct accounts logged in.
This coordinator simply starts bots one at a time, waiting for each to
confirm MT5 connection before starting the next.

The lock file in each bot's connect() prevents simultaneous connections.
Combined with sequential startup, account mixing is prevented.

Run via SYS_STARTUP task at boot, or manually via /restart:
    python C:/algos/bots/startup_coordinator.py
"""

import subprocess
import sys
import time
from pathlib import Path

PYTHON = sys.executable
ALGOS  = Path("C:/algos")
BOTS   = Path("C:/algos/bots")

STARTUP_SEQUENCE = [
    (
        "SMC Trend",
        r"C:\algos\bots\bot_smc_trend.py",
        r"C:\algos\markets\fx\instances\gold_main\config.json",
        r"C:\algos\markets\fx\instances\gold_main\smc_trend_stdout.log",
        "Connected | #700103491",
        30,
    ),
    (
        "Mean Reversion",
        r"C:\algos\bots\bot_mean_reversion.py",
        r"C:\algos\markets\fx\instances\gold_main\config.json",
        r"C:\algos\markets\fx\instances\gold_main\mean_reversion_stdout.log",
        "Connected | #700103491",
        30,
    ),
    (
        "Scalper",
        r"C:\algos\bots\bot_scalper.py",
        r"C:\algos\markets\fx\instances\gold_scalper\config.json",
        r"C:\algos\markets\fx\instances\gold_scalper\scalper_stdout.log",
        "Connected | #700107520",
        30,
    ),
    (
        "FFT",
        r"C:\algos\bots\bot_fft.py",
        r"C:\algos\markets\fx\instances\gold_fft\config.json",
        r"C:\algos\markets\fx\instances\gold_fft\fft_stdout.log",
        "Connected | #700107749",
        30,
    ),
]


def clear_lock():
    lock = Path(r"C:\algos\mt5_connect.lock")
    if lock.exists():
        lock.unlink()
        print("Cleared stale MT5 lock")


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
                    print(f"  ✓ {name} connected in {time.time()-start:.0f}s")
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


def main():
    print("=" * 60)
    print("  LWG Capital — Sequential Bot Startup")
    print("=" * 60)
    print()

    clear_lock()

    all_ok = True

    for name, script, config, log_path, ready_str, timeout in STARTUP_SEQUENCE:
        print(f"Starting {name}...")
        size_before = get_log_size(log_path)

        # Write startup timestamp BEFORE waiting — so uptime is accurate
        # even if connection check times out
        import json as _json, time as _time
        ts_file = Path(log_path).parent / "startup_time.json"
        ts_file.write_text(_json.dumps({"started": _time.time()}))

        subprocess.Popen(
            [PYTHON, script, "--config", config],
            cwd=str(BOTS),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        connected = wait_for_connection(log_path, ready_str, size_before, timeout, name)
        if not connected:
            all_ok = False

        time.sleep(1)

    print()
    print("=" * 60)
    print("  All bots started." if all_ok else "  Some bots had issues.")
    print("=" * 60)

    print("\nStarting Telegram...")
    subprocess.Popen(
        [PYTHON, str(ALGOS / "notifications/start_telegram.py")],
        cwd=str(ALGOS),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    print("  ✓ Telegram started")


if __name__ == "__main__":
    main()
