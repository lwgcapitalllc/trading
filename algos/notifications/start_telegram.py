"""
start_telegram.py — Telegram Bot Launcher with Single-Instance Guard

Called by the SYS_TELEGRAM Task Scheduler task instead of telegram_bot.py directly.

🔴 **THE OLD GUARD FAILED OPEN, AND ON 2026-09-09 TWO COPIES OF THE CHAT BOT WERE FOUND RUNNING
ON THE BOX.** It established "am I alone" by enumerating processes with `wmic` under a 10s
timeout, inside a bare `try/except` that printed and carried on. So on a box under memory
pressure — which is exactly when a restart storm happens — `wmic` misses its timeout, the guard
prints one line nobody reads, and the launcher starts a SECOND bot beside the one already there.

**Why nothing ever noticed.** `monitor.py` asks `is_running("telegram_bot.py")`, which is a
yes/no. Two copies both answer yes, so no watchdog in this system can see a duplicate — and two
bots long-polling one Telegram token knock each other off the connection, each death looking to
the watchdog like an ordinary crash worth restarting. That is the loop behind five
"RESTARTED · Telegram bot" messages in three days.

**The guard is now a LOCK, not a survey.**

  * an exclusive lock on `telegram_launcher.lock`, held for the life of this process. A second
    launcher cannot take it and exits quietly. **It cannot time out and it cannot fail open** —
    the OS either grants the lock or it does not, and this process holds it for as long as the
    bot it started is alive (`subprocess.run` below blocks until the child exits).
  * `telegram_bot.pid` records the child's PID, so an ORPHAN left by a launcher that died can be
    killed by PID rather than by enumerating the process table. No timeout, nothing to swallow.

⚠ **The wmic sweep is KEPT as a backstop and is no longer the guard.** It catches an orphan from
before this file existed, or one whose PID file was lost. It still cannot be trusted, which is
why it is no longer the thing standing between us and a duplicate.

⚠ **A failure to take the lock exits 0, deliberately.** It means a healthy launcher is already
running, which is success from the task's point of view — and a task that reports failure every
minute is one everybody learns to ignore.

⚠ **Every swallowed failure now PRINTS what it could not do.** The old version's `except` said
`Kill check error` and continued into the exact state it existed to prevent.

Run:
    python C:/trading/algos/notifications/start_telegram.py
    python C:/trading/algos/notifications/start_telegram.py --status   # who holds the lock
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# DERIVED, not hardcoded — same reason as algos/shared/bot_state.py. A literal
# "C:/trading/algos" is correct on the VPS and silently wrong everywhere else, which makes
# this file untestable off the box.
ALGOS = Path(__file__).resolve().parent.parent

LOCK_FILE = ALGOS / "telegram_launcher.lock"
PID_FILE = ALGOS / "telegram_bot.pid"
START_FILE = ALGOS / "telegram_start.json"
BOT_SCRIPT = ALGOS / "notifications" / "telegram_bot.py"

# How long to give a killed bot to actually go away before starting its replacement. Telegram's
# long-poll connection is the shared resource: starting the new bot while the old one still holds
# it is the collision this whole file exists to prevent.
_KILL_SETTLE_SECS = 2


class LockNotAcquired(Exception):
    """Another launcher holds the lock. Not an error — the expected answer when one is running."""


def _lock_exclusive(handle) -> None:
    """Take an exclusive, non-blocking lock on an open file, or raise.

    Windows and POSIX have different calls and neither is importable on the other, so the import
    is per-branch. ⚠ **There is no third branch that silently succeeds** — a platform with no
    lock is a platform with no guard, and this function must never return normally without one.
    """
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def acquire_lock():
    """Return the held lock file handle, or raise LockNotAcquired.

    ⚠ **The handle is RETURNED and must be kept alive by the caller.** The lock lives as long as
    the file is open; letting the handle be garbage collected releases it and quietly restores
    the duplicate this file exists to prevent.
    """
    handle = open(LOCK_FILE, "a+")
    try:
        _lock_exclusive(handle)
    except OSError as e:
        handle.close()
        raise LockNotAcquired(str(e)) from e
    try:
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps({"pid": os.getpid(), "at": datetime.now(timezone.utc).isoformat()}))
        handle.flush()
    except OSError as e:
        # The lock is what matters and we hold it. Failing to record WHO holds it is worth a line
        # and nothing more — refusing here would trade a working guard for a cosmetic one.
        print(f"  ! holding the lock but could not record the holder: {e}")
    return handle


def _commandline_of(pid: int):
    """The commandline of one PID, or None if it could not be read.

    ⚠ **`None` is CANNOT ASK and the caller must not read it as "no such process".** Windows
    recycles PIDs, so a recorded PID may belong to something else entirely by the time we look —
    killing on an unread answer is how a launcher shoots an unrelated process.
    """
    try:
        r = subprocess.run(
            ["wmic", "process", "where", f"processid={int(pid)}", "get", "commandline"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def _kill(pid: int, why: str) -> bool:
    try:
        r = subprocess.run(["taskkill", "/f", "/pid", str(pid)], capture_output=True, timeout=10)
    except Exception as e:
        print(f"  ! could not kill PID {pid} ({why}): {e}")
        return False
    if r.returncode == 0:
        print(f"  killed PID {pid} ({why})")
        return True
    # Already gone is the ordinary case, not a fault.
    return False


def kill_recorded_bot() -> bool:
    """Kill the bot this launcher's predecessor started, by PID. Returns whether it killed one.

    🔴 **This is the path that does NOT depend on enumerating the process table**, which is the
    thing that failed. It reads one recorded number and verifies that number is still our bot
    before acting.
    """
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        return False  # no record, or unreadable — the sweep below is the backstop

    cmdline = _commandline_of(pid)
    if cmdline is None:
        print(f"  ! could not confirm what PID {pid} is; leaving it alone")
        return False
    if "telegram_bot.py" not in cmdline:
        return False  # PID was recycled, or the bot already exited. Not ours.
    return _kill(pid, "recorded bot from a previous launcher")


def sweep_stray_bots() -> int:
    """Backstop: kill any telegram_bot.py the PID file did not account for. Returns how many.

    ⚠ **This is NOT the single-instance guard any more and must never be treated as one.** It
    was, and it failed open under load. It is kept because an orphan predating the PID file, or
    one whose record was lost, has nothing else to catch it.
    """
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "processid,commandline"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        # Loud, because the old version's silence here is the whole incident.
        print(f"  ! could not sweep for stray bots: {e}")
        return 0

    killed = 0
    for line in result.stdout.splitlines():
        if "telegram_bot.py" not in line:
            continue
        parts = line.strip().split()
        if parts and parts[-1].isdigit():
            if _kill(int(parts[-1]), "stray bot found by sweep"):
                killed += 1
    return killed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Telegram bot launcher (single instance)")
    ap.add_argument(
        "--status", action="store_true", help="report who holds the lock, start nothing"
    )
    args = ap.parse_args(argv)

    if args.status:
        try:
            print(f"lock file: {LOCK_FILE}")
            print(f"  holder: {LOCK_FILE.read_text().strip() or '(empty)'}")
        except Exception as e:
            print(f"  no lock recorded ({e})")
        try:
            print(f"  recorded bot PID: {PID_FILE.read_text().strip()}")
        except Exception:
            print("  recorded bot PID: (none)")
        return 0

    try:
        lock = acquire_lock()
    except LockNotAcquired:
        # The expected answer when a launcher is already running. Exit 0: from the task's point
        # of view "it is already up" is success, and a task that fails every minute gets ignored.
        print("another launcher already holds the lock - nothing to do")
        return 0

    with lock:
        killed = kill_recorded_bot()
        killed = sweep_stray_bots() > 0 or killed
        if killed:
            time.sleep(_KILL_SETTLE_SECS)

        try:
            START_FILE.write_text(json.dumps({"started": datetime.now(timezone.utc).timestamp()}))
        except OSError as e:
            print(f"  ! could not write the start marker: {e}")

        print("Starting telegram_bot.py...")
        proc = subprocess.Popen([sys.executable, str(BOT_SCRIPT)], cwd=str(ALGOS))
        try:
            PID_FILE.write_text(str(proc.pid))
        except OSError as e:
            # The bot is running; we simply cannot record it. The lock still prevents a duplicate
            # launcher, and the sweep is still there for the orphan case.
            print(f"  ! started PID {proc.pid} but could not record it: {e}")

        # Blocking here is what holds the lock for the bot's lifetime. Do not background this.
        proc.wait()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
