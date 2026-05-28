"""
startup_coordinator.py — Sequential Bot Startup

Starts bots one at a time, waiting for each to confirm MT5 connection.
Writes bot_state.json with started timestamp — single source of truth
for uptime tracking across algo panel and Telegram.

Run via SYS_STARTUP task at boot, or manually:
    python C:/trading/algos/bots/startup_coordinator.py

Single-bot mode (Command Center per-bot start/restart):
    python C:/trading/algos/bots/startup_coordinator.py --bot smc_trend

In single-bot mode: skips lock clear, skips marking other bots stopped,
launches the bot and exits immediately (bot survives via CREATE_NEW_PROCESS_GROUP).
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

PYTHON = sys.executable
ALGOS  = Path("C:/trading/algos")
BOTS   = Path("C:/trading/algos/bots")

sys.path.insert(0, str(ALGOS / "shared"))
from bot_state import set_started, set_status

STARTUP_SEQUENCE = [
    (
        "smc_trend",
        "SMC Trend",
        r"C:\trading\algos\bots\bot_smc_trend.py",
        r"C:\trading\algos\markets\fx\instances\gold_main\config.json",
        r"C:\trading\algos\markets\fx\instances\gold_main\smc_trend_stdout.log",
        "Connected | #700103491",
        30,
    ),
    (
        "mean_reversion",
        "Mean Reversion",
        r"C:\trading\algos\bots\bot_mean_reversion.py",
        r"C:\trading\algos\markets\fx\instances\gold_main\config.json",
        r"C:\trading\algos\markets\fx\instances\gold_main\mean_reversion_stdout.log",
        "Connected | #700103491",
        30,
    ),
    (
        "scalper",
        "Scalper",
        r"C:\trading\algos\bots\bot_scalper.py",
        r"C:\trading\algos\markets\fx\instances\gold_scalper\config.json",
        r"C:\trading\algos\markets\fx\instances\gold_scalper\scalper_stdout.log",
        "Connected | #700107520",
        30,
    ),
    (
        "fft",
        "FFT",
        r"C:\trading\algos\bots\bot_fft.py",
        r"C:\trading\algos\markets\fx\instances\gold_fft\config.json",
        r"C:\trading\algos\markets\fx\instances\gold_fft\fft_stdout.log",
        "Connected | #700107749",
        30,
    ),
]


def clear_lock():
    lock = Path(r"C:\trading\algos\mt5_connect.lock")
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
                content     = p.read_text(errors="replace")
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
    parser = argparse.ArgumentParser(description="Start bots (all or single)")
    parser.add_argument("--bot", default=None,
                        help="Start only this bot key (e.g. smc_trend). "
                             "Skips lock clear and connection wait — bot detaches immediately.")
    args = parser.parse_args()

    # ── Single-bot mode ───────────────────────────────────────────────────────
    if args.bot:
        entry = next((e for e in STARTUP_SEQUENCE if e[0] == args.bot), None)
        if entry is None:
            keys = [e[0] for e in STARTUP_SEQUENCE]
            print(f"Unknown bot key '{args.bot}'. Available: {', '.join(keys)}")
            sys.exit(1)

        bot_key, name, script, config, *_ = entry
        print(f"Starting {name} (single-bot mode)…")
        set_started(bot_key)
        subprocess.Popen(
            [PYTHON, script, "--config", config],
            cwd=str(BOTS),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        print(f"  ✓ {name} launched")
        return

    # ── Full startup mode ─────────────────────────────────────────────────────
    print("=" * 60)
    print("  LWG Capital — Sequential Bot Startup")
    print("=" * 60)
    print()

    clear_lock()

    # Mark all bots as stopped at startup
    for bot_key, _, _, _, _, _, _ in STARTUP_SEQUENCE:
        set_status(bot_key, "stopped")

    all_ok = True

    for bot_key, name, script, config, log_path, ready_str, timeout in STARTUP_SEQUENCE:
        print(f"Starting {name}...")

        # Write started timestamp BEFORE launching
        set_started(bot_key)

        size_before = get_log_size(log_path)

        subprocess.Popen(
            [PYTHON, script, "--config", config],
            cwd=str(BOTS),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        connected = wait_for_connection(log_path, ready_str, size_before, timeout, name)
        if not connected:
            set_status(bot_key, "offline")
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
    print("  ✓ Done")


if __name__ == "__main__":
    main()
