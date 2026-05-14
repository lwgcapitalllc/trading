"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BOT CONTROLLER — XAUUSD Algo Suite                                        ║
║  Manages Bot 1 (SMC Trend) and Bot 2 (Mean Reversion)                      ║
║                                                                              ║
║  Usage (run this on the VPS):                                               ║
║    python controller.py start both      — start both bots                  ║
║    python controller.py start bot1      — start Bot 1 only                 ║
║    python controller.py start bot2      — start Bot 2 only                 ║
║    python controller.py stop both       — graceful stop both bots          ║
║    python controller.py stop bot1       — stop Bot 1 only                  ║
║    python controller.py stop bot2       — stop Bot 2 only                  ║
║    python controller.py emergency       — EMERGENCY: kill all + close MT5  ║
║    python controller.py status          — show what is running             ║
║    python controller.py restart both    — stop then start both             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import subprocess
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
ALGOS_DIR  = Path(__file__).parent
BOT1_SCRIPT = str(ALGOS_DIR / "bot1_smc_trend.py")
BOT2_SCRIPT = str(ALGOS_DIR / "bot2_mean_reversion.py")
PID_FILE    = ALGOS_DIR / "bot_pids.json"
LOG_FILE    = ALGOS_DIR / "controller.log"

# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{timestamp}] {msg}"
    # Safe print — ignore characters that can't encode over SSH
    print(line.encode("ascii", errors="replace").decode("ascii"))
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── PID management ────────────────────────────────────────────────────────────
def save_pids(pids: dict):
    with open(PID_FILE, "w") as f:
        json.dump(pids, f, indent=2)

def load_pids() -> dict:
    if PID_FILE.exists():
        with open(PID_FILE) as f:
            return json.load(f)
    return {}

def is_running(pid: int) -> bool:
    """Check if a process with given PID is still running (Windows compatible)."""
    try:
        import ctypes
        kernel32  = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle    = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle == 0:
            return False
        import ctypes.wintypes
        result = ctypes.wintypes.DWORD()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(result))
        kernel32.CloseHandle(handle)
        STILL_ACTIVE = 259
        return result.value == STILL_ACTIVE
    except Exception:
        return False

def get_status() -> dict:
    """Return current status of both bots."""
    pids = load_pids()
    status = {}
    for bot in ["bot1", "bot2"]:
        pid = pids.get(bot)
        if pid and is_running(pid):
            status[bot] = {"running": True, "pid": pid}
        else:
            status[bot] = {"running": False, "pid": None}
    return status

# ── Start ─────────────────────────────────────────────────────────────────────
def start_bot(bot_name: str):
    """Start a bot as a detached background process using Windows START command."""
    scripts = {"bot1": BOT1_SCRIPT, "bot2": BOT2_SCRIPT}
    script  = scripts.get(bot_name)
    if not script:
        log(f"Unknown bot: {bot_name}")
        return False

    # Check if already running via PID file
    pids = load_pids()
    pid  = pids.get(bot_name)
    if pid and is_running(pid):
        log(f"{bot_name.upper()} is already running (PID {pid}). Skipping.")
        return False

    log(f"Starting {bot_name.upper()}...")

    # Write a small launcher script that auto-confirms CONFIRM prompt
    launcher = ALGOS_DIR / f"_launch_{bot_name}.py"
    stdout_log = ALGOS_DIR / f"{bot_name}_stdout.log"
    with open(launcher, "w") as f:
        f.write(f"""import subprocess, sys, os
out = open(r"{stdout_log}", "a")
proc = subprocess.Popen(
    [sys.executable, r"{script}"],
    stdin=subprocess.PIPE,
    stdout=out,
    stderr=out,
)
proc.stdin.write(b"CONFIRM\\n")
proc.stdin.flush()
proc.stdin.close()
# Write PID to a temp file so controller can read it
with open(r"{ALGOS_DIR / f'_pid_{bot_name}.txt'}", "w") as pf:
    pf.write(str(proc.pid))
""")

    # Run launcher via cmd /c start to fully detach from SSH session
    cmd = f'cmd /c start /b "" "{sys.executable}" "{launcher}"'
    os.system(cmd)

    # Wait briefly for launcher to write the PID file
    import time as _time
    for _ in range(10):
        _time.sleep(1)
        pid_file = ALGOS_DIR / f"_pid_{bot_name}.txt"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                pid_file.unlink()
                launcher.unlink(missing_ok=True)
                pids = load_pids()
                pids[bot_name] = pid
                save_pids(pids)
                log(f"{bot_name.upper()} started successfully | PID={pid}")
                return True
            except Exception as e:
                log(f"PID read error: {e}")
                break

    launcher.unlink(missing_ok=True)
    log(f"Failed to confirm {bot_name.upper()} started. Check {bot_name}_stdout.log on VPS.")
    return False

# ── Stop ──────────────────────────────────────────────────────────────────────
def stop_bot(bot_name: str, force: bool = False):
    """Gracefully stop a bot by PID."""
    pids   = load_pids()
    pid    = pids.get(bot_name)
    label  = bot_name.upper()

    if not pid:
        log(f"{label} — no PID on record. May not be running.")
        return

    if not is_running(pid):
        log(f"{label} — PID {pid} is not running. Already stopped.")
        pids[bot_name] = None
        save_pids(pids)
        return

    log(f"Stopping {label} (PID={pid}){'  [FORCE]' if force else ''}...")
    try:
        # Windows-compatible: use taskkill
        import subprocess
        result = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True, text=True
        )
        # Wait up to 10 seconds for process to die
        for _ in range(10):
            time.sleep(1)
            if not is_running(pid):
                break
        if is_running(pid):
            log(f"{label} did not stop. Try manually: taskkill /F /PID {pid}")
        else:
            log(f"{label} stopped successfully.")
    except Exception as e:
        log(f"Error stopping {label}: {e}")

    pids[bot_name] = None
    save_pids(pids)

# ── Emergency stop ────────────────────────────────────────────────────────────
def emergency_stop():
    """
    EMERGENCY: Kill both bots immediately.
    Note: This stops new entries but open trades are protected by broker stop losses.
    To close open positions, log into MT5 manually or use the MT5 terminal.
    """
    log("=" * 60)
    log("  EMERGENCY STOP INITIATED")
    log("=" * 60)
    stop_bot("bot1", force=True)
    stop_bot("bot2", force=True)
    log("Both bots killed.")
    log("IMPORTANT: Open positions are still protected by broker stop losses.")
    log("To close open positions manually, log into MT5 and close them there.")
    log("=" * 60)

# ── Print status ──────────────────────────────────────────────────────────────
def is_bot_alive(bot_name: str) -> bool:
    """
    Check if a bot is alive by reading its main activity log.
    Bot 1 writes to bot1_trend.log every 60s, Bot 2 to bot2_reversion.log.
    If the log was written to in the last 5 minutes, the bot is running.
    """
    import time as _time
    log_map  = {"bot1": "bot1_trend.log", "bot2": "bot2_reversion.log"}
    log_file = ALGOS_DIR / log_map.get(bot_name, f"{bot_name}.log")
    if not log_file.exists():
        return False
    age_seconds = _time.time() - log_file.stat().st_mtime
    return age_seconds < 300  # alive if written to in last 5 minutes

def get_uptime(bot_name: str) -> str:
    """Calculate uptime from the bot's main activity log."""
    log_map  = {"bot1": "bot1_trend.log", "bot2": "bot2_reversion.log"}
    log_file = ALGOS_DIR / log_map.get(bot_name, f"{bot_name}.log")
    if not log_file.exists():
        return "unknown"
    try:
        lines = log_file.read_text(errors="ignore").strip().split("\n")
        for line in reversed(lines):
            if "STARTING" in line or ("Balance" in line and "Risk" in line):
                ts_str     = line.split("|")[0].strip()[:19]
                from datetime import datetime
                start_time = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                delta      = datetime.utcnow() - start_time
                hours      = int(delta.total_seconds() // 3600)
                minutes    = int((delta.total_seconds() % 3600) // 60)
                return f"{hours}h {minutes}m"
    except Exception:
        pass
    return "unknown"

def print_status():
    """Print current status of both bots."""
    log_map = {"bot1": "bot1_trend.log", "bot2": "bot2_reversion.log"}
    log("-" * 55)
    log("  BOT STATUS REPORT")
    log("-" * 55)
    for bot in ["bot1", "bot2"]:
        alive  = is_bot_alive(bot)
        pids   = load_pids()
        pid    = pids.get(bot, "?")
        uptime = get_uptime(bot) if alive else "offline"
        if alive:
            log(f"  {bot.upper():<6} RUNNING   PID={pid}   uptime={uptime}")
        else:
            log(f"  {bot.upper():<6} STOPPED")

        # Show last line of main activity log
        lf = ALGOS_DIR / log_map.get(bot, f"{bot}.log")
        if lf.exists():
            lines = lf.read_text(errors="ignore").strip().split("\n")
            last  = lines[-1] if lines else "No log entries yet"
            log(f"  {bot.upper()} last: {last[-120:]}")
    log("-" * 55)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd  = sys.argv[1].lower()
    target = sys.argv[2].lower() if len(sys.argv) > 2 else "both"

    bots = []
    if target in ("both", "all"):
        bots = ["bot1", "bot2"]
    elif target in ("bot1", "1", "trend"):
        bots = ["bot1"]
    elif target in ("bot2", "2", "reversion", "revert"):
        bots = ["bot2"]

    if cmd == "start":
        if not bots:
            log("Specify: both | bot1 | bot2")
            sys.exit(1)
        for bot in bots:
            start_bot(bot)
            time.sleep(2)   # small gap between starts

    elif cmd == "stop":
        if not bots:
            log("Specify: both | bot1 | bot2")
            sys.exit(1)
        for bot in bots:
            stop_bot(bot)

    elif cmd in ("emergency", "kill", "panic"):
        emergency_stop()

    elif cmd in ("status", "check"):
        print_status()

    elif cmd == "restart":
        if not bots:
            log("Specify: both | bot1 | bot2")
            sys.exit(1)
        for bot in bots:
            stop_bot(bot)
        log("Waiting 5 seconds before restart...")
        time.sleep(5)
        for bot in bots:
            start_bot(bot)
            time.sleep(3)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

if __name__ == "__main__":
    main()
