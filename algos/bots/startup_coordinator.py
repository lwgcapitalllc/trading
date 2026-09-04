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
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

PYTHON = sys.executable
ALGOS = Path("C:/trading/algos")
BOTS = Path("C:/trading/algos/bots")

sys.path.insert(0, str(ALGOS / "shared"))
from bot_state import set_started, set_status

# (bot_key, display name, script, argv, log path, ready string, connect timeout)
#
# `argv` is the FULL argument list, not a config path. The old bots all took
# `--config <file>`; algos/live/runner.py takes `--bot <key>` and resolves its own
# instance dir, so the launcher can no longer assume one flag shape.
#
# 🔴 `--live` IS HERE, AS OF 2026-08-05, AND IT IS THE ONLY PLACE IT NEEDS TO BE.
#
# This line used to read "NO `--live` HERE, and that is the point" — the runner defaults to dry
# run and requires `--live` to be typed, so a bot that booted with the VPS could never arm
# itself. That guard did its job: the bot ran three days and 274 bars without an order. Aaron
# armed it deliberately on 2026-08-05, on the $2,000 PU Prime DEMO account, for the reason the
# dry run could not serve — the strategy takes ~2 trades a MONTH, so watching it decide nothing
# for weeks teaches nothing, and the broker facts this repo still has to measure (fill vs
# intended price, real spread, swap, commission) only exist once a real order goes to a real
# broker. See docs/LIVE_TRADING_PIPELINE.md step 9 and G5.
#
# ⚠ THIS ARGV IS THE SINGLE SOURCE FOR ALL THREE START PATHS, and that is why the flag belongs
# here rather than in one caller. SYS_STARTUP at boot, the SYS_MONITOR watchdog restarting a
# dead bot, and the command center's Start/Restart buttons ALL launch through this module —
# boot and the watchdog through the full sequence below, the buttons through `--bot` single
# mode — and both read this same tuple. Arming any one caller instead would mean a watchdog
# restart silently returning a live bot to dry run, which is the "two paths, one drifts" defect
# this repo keeps meeting; a bot that is live until something restarts it is worse than one
# that is honestly dry, because the ledger would keep filling and nothing would say the orders
# had stopped.
#
# ⚠ It follows that arming is now the DEFAULT for this bot on this box: every automatic
# recovery brings it back live. Disarming means deleting the flag here and restarting — not
# stopping the bot, which the watchdog will simply undo.
STARTUP_SEQUENCE = [
    (
        "sos_fade_demo",
        "SOS Fade",
        str(ALGOS / "live" / "runner.py"),
        ["--bot", "sos_fade_demo", "--live"],
        str(ALGOS / "markets/fx/instances/sos_fade_demo/sos_fade_demo.log"),
        "Connected | #",
        180,
    ),
    (
        "b_leg_demo",
        "B-LEG",
        str(ALGOS / "live" / "runner.py"),
        ["--bot", "b_leg_demo", "--live"],
        str(ALGOS / "markets/fx/instances/b_leg_demo/b_leg_demo.log"),
        "Connected | #",
        180,
    ),
    # ⚠ **Listed while on the BENCH, exactly as the sibling above is, and `bot_is_assigned`
    # skips it every pass.** Being here says a bot CAN be started; having an account says it
    # SHOULD be. Adding it only once somebody assigns it would mean the Bots page could put a bot
    # on an account that no boot sequence brings back after a reboot — and the symptom of that is
    # a bot that is simply absent, which nothing distinguishes from one nobody has armed yet.
    (
        "extreme_leg_demo",
        "Extreme Leg",
        str(ALGOS / "live" / "runner.py"),
        ["--bot", "extreme_leg_demo", "--live"],
        str(ALGOS / "markets/fx/instances/extreme_leg_demo/extreme_leg_demo.log"),
        "Connected | #",
        180,
    ),
]


def bot_is_assigned(bot_key: str) -> bool:
    """Whether this bot has an account to trade, read from its own instance config.

    `account: null` is the BENCH — registered, configured, and deliberately not on any account
    (see `algos/live/live_config.py`). Being listed in `STARTUP_SEQUENCE` says a bot CAN be
    started; having an account says it SHOULD be. Keeping those separate is what lets a bot be
    added to and removed from an account from the Bots page without editing this file — and
    without a removed bot being started again by the next boot or the next watchdog pass, which
    is the whole point: `runner.run()` refuses too, but it refuses after the process has been
    spawned, so the coordinator would go on spawning one every 60 seconds for ever.

    ⚠ **Unreadable answers True — the OPPOSITE default to the missing-account case**, and it is
    deliberate. A config this cannot parse is a bot whose state is unknown, and the runner's own
    checks (the version pin, the credentials lookup, this same guard) are all still in front of
    it; refusing here would silently keep a bot off the box because of a transient read, which is
    the failure that has no symptom. Of the two wrong answers, "spawn a process that refuses and
    says why" is recoverable and "quietly never start a live bot" is not.
    """
    cfg = ALGOS / "markets" / "fx" / "instances" / bot_key / "config.json"
    try:
        return json.loads(cfg.read_text(encoding="utf-8")).get("account") is not None
    except (OSError, json.JSONDecodeError, AttributeError):
        return True


def clear_lock():
    lock = Path(r"C:\trading\algos\mt5_connect.lock")
    if lock.exists():
        lock.unlink()
        print("Cleared stale MT5 lock")


def live_log(log_path: str) -> Path:
    """The file the bot is ACTUALLY writing, for a configured log path.

    🔴 **`runner.py` writes one text log per UTC day since 2026-08-05** —
    `<bot>-YYYY-MM-DD.log`, via `DailyFileHandler` — so the plain `<bot>.log` named in
    `STARTUP_SEQUENCE` stopped being written and nothing here noticed. `wait_for_connection`
    would then have watched a file that never grows and reported *"timed out after 180s"* for a
    bot that had started perfectly, setting its status to `offline` in the same breath. **A
    healthy start reported as a failure is worse than a silent one — it sends you to fix a bot
    that is fine.**

    Resolved fresh on every poll rather than once, because the file does not exist yet at
    launch: the bot creates it on its first log line, which is the thing being waited for.
    Falls back to the configured path so a strategy or a tool that still writes a plain log
    keeps working.
    """
    p = Path(log_path)
    dated = sorted(p.parent.glob(f"{p.stem}-????-??-??.log"))
    return dated[-1] if dated else p


def log_baseline(log_path: str) -> Tuple[Path, int]:
    """Which file was being written before the launch, and how much was in it.

    ⚠ **The PATH has to travel with the size, and that is not fussiness.** With per-day logs the
    file the bot writes after launching is very often a DIFFERENT file from the one measured a
    moment earlier — every first start of a UTC day, and every start that crosses midnight. A
    size taken from yesterday's log applied as an offset into today's would slice the front off
    the new file and hide the very line being waited for, which reads as a bot that started and
    never connected.
    """
    p = live_log(log_path)
    return p, (p.stat().st_size if p.exists() else 0)


def wait_for_connection(
    log_path: str,
    ready_string: str,
    size_before: int,
    timeout: int,
    name: str,
    baseline_path: Optional[Path] = None,
) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        p = live_log(log_path)
        if p.exists():
            try:
                content = p.read_text(errors="replace")
                # A file the baseline was never measured against starts at 0 — it is new, so all
                # of it belongs to this run.
                offset = size_before if (baseline_path is None or p == baseline_path) else 0
                new_content = content[offset:]
                if ready_string in new_content:
                    print(f"  ✓ {name} connected in {time.time() - start:.0f}s")
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
    parser.add_argument(
        "--bot",
        default=None,
        help="Start only this bot key (e.g. <bot_name>). "
        "Skips lock clear and connection wait — bot detaches immediately.",
    )
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

        # This path is the command center's Start button, so REFUSING is right where the full
        # sequence merely skips: somebody pressed a button and is owed an answer, and the answer
        # is the action that fixes it. Exit 1 so the caller can tell this from a launch.
        if not bot_is_assigned(bot_key):
            print(
                f"  REFUSED {name} is not assigned to an account, so it has nothing to "
                f"trade. Add it to an account on Bots -> Accounts, then start it."
            )
            sys.exit(1)

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

        # On the bench — skip QUIETLY, and do not count it against `all_ok`. This is the boot
        # sequence and the watchdog's recovery path, both of which run unattended: a bot nobody
        # has assigned is a deliberate state, so treating it as a failed start would mark the
        # whole boot unhealthy every time and train everyone to ignore that signal.
        if not bot_is_assigned(bot_key):
            print("  - Not assigned to an account — skipped")
            continue

        # Already up? Leave it alone — the same rule the Telegram launch follows below, and
        # for a worse reason. Launching a second copy of a bot that is already trading gives
        # you TWO processes on one account and one magic number, both sizing full positions
        # off the same setup. Measured 2026-08-04: a SYS_STARTUP run while the bot was up
        # produced exactly that, and nothing anywhere reported it.
        if bot_is_running(bot_key):
            print("  ✓ Already running — left alone")
            continue

        # Write started timestamp BEFORE launching
        set_started(bot_key)

        baseline_path, size_before = log_baseline(log_path)

        subprocess.Popen(
            [PYTHON, script, *argv],
            cwd=str(BOTS),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        connected = wait_for_connection(
            log_path, ready_str, size_before, timeout, name, baseline_path=baseline_path
        )
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

    🔴 **It must also not match ITSELF, and until 2026-08-05 it did.** In single-bot mode this
    very process is `startup_coordinator.py --bot <key>`, so a substring search for
    `--bot <key>` found its own commandline and reported the bot as already running — **on the
    exact path the command center's Start button drives.** The bot could never be started that
    way, and the message said the reassuring thing: *"already running — left alone"*. Found by
    stopping the live bot for a deploy and being unable to start it again.

    So the match requires the RUNNER SCRIPT as well as the key. The key alone identifies which
    bot (every live bot is the same `runner.py`, so the script names the fleet); the script
    alone identifies which fleet. **Only the pair identifies a running bot**, and a coordinator
    holding the same key is not one.
    """
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        print(
            f"  ! Could not read the process list ({e}) — assuming {bot_key} is up, not starting it"
        )
        return True
    return any(f"--bot {bot_key}" in line and "runner.py" in line for line in r.stdout.splitlines())


def telegram_is_running() -> bool:
    """Is a telegram_bot.py process alive right now?"""
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True,
            text=True,
            timeout=10,
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
