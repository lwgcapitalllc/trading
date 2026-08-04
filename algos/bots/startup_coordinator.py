"""
startup_coordinator.py — Sequential Bot Startup

Starts bots one at a time, waiting for each to confirm MT5 connection.
Writes bot_state.json with started timestamp — single source of truth
for uptime tracking across algo panel and Telegram.

Run via SYS_STARTUP task at boot, or manually:
    python C:/trading/algos/bots/startup_coordinator.py

Single-bot mode (Command Center per-bot start/restart):
    python C:/trading/algos/bots/startup_coordinator.py --bot <bot_name>

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

# (bot_key, display name, script, argv, log path, ready string, connect timeout)
#
# `argv` is the FULL argument list, not a config path. The old bots all took
# `--config <file>`; algos/live/runner.py takes `--bot <key>` and resolves its own
# instance dir, so the launcher can no longer assume one flag shape.
#
# ⚠ NO `--live` HERE, and that is the point. The runner defaults to dry run and requires
# `--live` to be typed, so a bot that boots with the VPS can never arm itself. Arming is a
# deliberate act — see algos/live/ and docs/LIVE_TRADING_PIPELINE.md step 9.
STARTUP_SEQUENCE = [
    (
        "mpc_sos_fade_demo",
        "MPC SOS Fade",
        str(ALGOS / "live" / "runner.py"),
        ["--bot", "mpc_sos_fade_demo"],
        str(ALGOS / "markets/fx/instances/mpc_sos_fade_demo/mpc_sos_fade_demo.log"),
        "Connected | #",
        180,
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
                        help="Start only this bot key (e.g. <bot_name>). "
                             "Skips lock clear and connection wait — bot detaches immediately.")
    args = parser.parse_args()

    # ── Single-bot mode ───────────────────────────────────────────────────────
    if args.bot:
        entry = next((e for e in STARTUP_SEQUENCE if e[0] == args.bot), None)
        if entry is None:
            keys = [e[0] for e in STARTUP_SEQUENCE]
            print(f"Unknown bot key '{args.bot}'. Available: {', '.join(keys)}")
            sys.exit(1)

        bot_key, name, script, argv, log_path, *_ = entry
        print(f"Starting {name} (single-bot mode)...")

        # This is the path the command center's per-bot Start button drives, which makes it the
        # likeliest way anyone produces a duplicate — pressing Start on a bot that is already
        # running is a completely reasonable thing to do. `runner.already_running()` would
        # refuse the second copy anyway, but it would do so in a boot log nobody opens; this
        # says it where the button's caller can see it, and skips `set_started`, which would
        # otherwise reset the uptime of the bot that is genuinely running.
        if bot_is_running(bot_key):
            print(f"  OK {name} is already running — left alone")
            return

        set_started(bot_key)

        # stdout/stderr to a FILE, never DEVNULL. A bot writes its own log once its logger
        # exists — but a failure BEFORE that (a bad import, a missing dependency, a config
        # that will not parse) has nowhere else to go, and DEVNULL made it vanish: the
        # coordinator printed "launched", nothing appeared in the bot's log, and there was
        # no process. That is the least diagnosable failure available.
        boot_log = Path(log_path).with_name(f"{bot_key}_boot.log")
        boot_log.parent.mkdir(parents=True, exist_ok=True)
        out = open(boot_log, "a", encoding="utf-8", errors="replace")
        subprocess.Popen(
            [PYTHON, script, *argv],
            cwd=str(BOTS),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=out,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        print(f"  OK {name} launched (boot output -> {boot_log})")
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

    for bot_key, name, script, argv, log_path, ready_str, timeout in STARTUP_SEQUENCE:
        print(f"Starting {name}...")

        # Already up? Leave it alone — the same rule the Telegram launch follows below, and
        # for a worse reason. Launching a second copy of a bot that is already trading gives
        # you TWO processes on one account and one magic number, both sizing full positions
        # off the same setup. Measured 2026-08-04: a SYS_STARTUP run while the bot was up
        # produced exactly that, and nothing anywhere reported it.
        if bot_is_running(bot_key):
            print(f"  ✓ Already running — left alone")
            continue

        # Write started timestamp BEFORE launching
        set_started(bot_key)

        size_before = get_log_size(log_path)

        subprocess.Popen(
            [PYTHON, script, *argv],
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

    start_telegram_if_needed()


def bot_is_running(bot_key: str) -> bool:
    """Is this bot's runner process alive right now?

    Matched on `--bot <bot_key>` in the commandline, because every live bot is the SAME script
    (`algos/live/runner.py`) — the script name identifies the fleet, only the key identifies the
    bot. This is the identity `monitor.py` and the command center's per-bot stop both use.

    ⚠ **Answers False when the process list cannot be read, unlike `telegram_is_running`.** The
    two failure directions are not equal here: a duplicate BOT is two positions on one account,
    a duplicate Telegram is refused by its own singleton guard. So this reports "not running"
    only when it can see the list and the bot is genuinely absent — an unreadable list is
    treated as RUNNING and the bot is left alone, and `runner.py`'s own guard is the backstop.
    """
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        print(f"  ! Could not read the process list ({e}) — assuming {bot_key} is up, not starting it")
        return True
    return f"--bot {bot_key}" in r.stdout


def telegram_is_running() -> bool:
    """Is a telegram_bot.py process alive right now?"""
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=10,
        )
        return "telegram_bot.py" in r.stdout
    except Exception as e:
        # Unreadable process list. Say NO, so the caller starts one: an extra Telegram is
        # refused by telegram_bot.py's own singleton guard, while a missing one is silence.
        print(f"  ! Could not read the process list ({e}) — assuming Telegram is down")
        return False


def start_telegram_if_needed() -> None:
    """Start the Telegram bot, but never restart a healthy one.

    **Restarting a trading bot must not take the alert channel down with it.** Until
    2026-08-04 this ran `start_telegram.py` unconditionally, and that script's first act is
    `kill_existing()` — force-kill any running telegram_bot.py, sleep 2, start fresh. So every
    Start/Restart from the Bots page, and every documented bot restart, killed Telegram and
    rebuilt it. A minute later SYS_MONITOR noticed the gap and sent "Telegram Bot Restarted".

    Nothing was ever wrong with it. Aaron had been reading those messages as crashes for weeks,
    which is worse than the downtime: **an alert channel that cries wolf stops being read**, and
    the moment you are restarting a bot is exactly when you want to hear from it.

    ⚠ **`SYS_TELEGRAM` deliberately keeps the force-restart.** That task's whole job is
    recovering a bot that is alive but wedged, and it is what SYS_MONITOR fires (up to 3 times)
    when Telegram is genuinely down. This skip is only about collateral damage from starting
    something else.
    """
    print("\nStarting Telegram...")
    if telegram_is_running():
        print("  ✓ Already running — left alone")
        return
    subprocess.Popen(
        [PYTHON, str(ALGOS / "notifications/start_telegram.py")],
        cwd=str(ALGOS),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    print("  ✓ Started")


if __name__ == "__main__":
    main()
