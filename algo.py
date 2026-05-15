#!/usr/bin/env python3
"""
algo — Interactive Algo Trading Control Panel
Run from your Mac terminal: python3 algo.py
Or install as a command: see INSTALL section at bottom of this file.

Connects to your VPS over SSH and manages all trading bots.
Automatically discovers bots by scanning Task Scheduler for tasks
prefixed with FX_, CRYPTO_, or FUTURES_.
"""

import subprocess
import sys
import os
from datetime import datetime

# ── VPS Config ────────────────────────────────────────────────────────────────
VPS_HOST    = "forexvps"          # SSH alias from ~/.ssh/config
LOG_BASE    = "C:\\algos\\markets" # Base path for log files on VPS

# Task name prefix → market label
MARKET_PREFIXES = {
    "FX_":      "FX",
    "CRYPTO_":  "Crypto",
    "FUTURES_": "Futures",
}

# Map task name patterns to log file paths
# Format: partial task name match → (market, pair, instance_folder)
LOG_MAP = {
    "FX_XAUUSD_Bot1":    ("fx", "xauusd_main",    "bot1.log"),
    "FX_XAUUSD_Bot2":    ("fx", "xauusd_main",    "bot2.log"),
    "FX_XAUUSD_Scalper": ("fx", "xauusd_scalper", "bot3.log"),
}

# ── Colors ────────────────────────────────────────────────────────────────────
class C:
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    GRAY   = "\033[90m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def green(s):  return f"{C.GREEN}{s}{C.RESET}"
def red(s):    return f"{C.RED}{s}{C.RESET}"
def yellow(s): return f"{C.YELLOW}{s}{C.RESET}"
def cyan(s):   return f"{C.CYAN}{s}{C.RESET}"
def bold(s):   return f"{C.BOLD}{s}{C.RESET}"
def gray(s):   return f"{C.GRAY}{s}{C.RESET}"


# ── SSH Helpers ───────────────────────────────────────────────────────────────
def ssh(cmd: str, capture=True) -> str:
    """Run a command on the VPS over SSH."""
    result = subprocess.run(
        ["ssh", VPS_HOST, cmd],
        capture_output=capture,
        text=True,
        timeout=30
    )
    return result.stdout.strip() if capture else ""

def ssh_ok(cmd: str) -> bool:
    """Run SSH command, return True if it succeeded."""
    result = subprocess.run(
        ["ssh", VPS_HOST, cmd],
        capture_output=True, text=True, timeout=30
    )
    return result.returncode == 0


# ── Task Discovery ────────────────────────────────────────────────────────────
def get_all_tasks() -> list[dict]:
    """
    Query VPS for all algo bot tasks and their actual running state.
    Checks if a python process is running with the bot script name,
    since Task Scheduler tasks exit after spawning the bot process.
    """
    # Get list of running python processes and their command lines
    running_scripts = set()
    raw_procs = ssh('wmic process where "name=\'python.exe\'" get commandline /format:list 2>nul')
    for line in raw_procs.splitlines():
        if "bot1_smc_trend" in line:    running_scripts.add("bot1")
        if "bot2_mean_reversion" in line: running_scripts.add("bot2")
        if "bot3_scalper" in line:       running_scripts.add("bot3")

    # Map task names to bot script keys
    TASK_BOT_MAP = {
        "FX_XAUUSD_Bot1":    "bot1",
        "FX_XAUUSD_Bot2":    "bot2",
        "FX_XAUUSD_Scalper": "bot3",
    }

    tasks = []
    raw = ssh("schtasks /query /fo CSV /nh 2>nul")
    for line in raw.splitlines():
        parts = line.strip().strip('"').split('","')
        if len(parts) < 3:
            continue
        name = parts[0].lstrip("\\")

        market_label = None
        for prefix, label in MARKET_PREFIXES.items():
            if name.startswith(prefix):
                market_label = label
                break
        if not market_label:
            continue

        # Check actual process running state
        bot_key = TASK_BOT_MAP.get(name)
        running = bot_key in running_scripts if bot_key else False

        name_parts = name.split("_", 2)
        pair = name_parts[1] if len(name_parts) > 1 else "?"
        role = name_parts[2] if len(name_parts) > 2 else "?"

        tasks.append({
            "name":    name,
            "market":  market_label,
            "pair":    pair,
            "role":    role,
            "running": running,
            "status":  "Running" if running else "Stopped",
        })

    return sorted(tasks, key=lambda x: (x["market"], x["pair"], x["role"]))


def get_uptime(task_name: str) -> str:
    """
    Calculate how long a bot has been running by reading its log file.
    Finds the most recent startup line and calculates elapsed time.
    """
    if task_name not in LOG_MAP:
        return ""

    market, instance, logfile = LOG_MAP[task_name]
    path = f"C:\\algos\\markets\\{market}\\instances\\{instance}\\{logfile}"

    raw = ssh(f"type {path} 2>nul")
    if not raw:
        return ""

    # Find last startup line
    lines = raw.splitlines()
    start_time = None
    for line in reversed(lines):
        if "STARTING" in line or ("Balance" in line and "Risk" in line):
            try:
                ts_str     = line.split("|")[0].strip()[:19]
                start_time = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                break
            except Exception:
                continue

    if not start_time:
        return ""

    delta   = datetime.utcnow() - start_time
    hours   = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)

    if hours >= 24:
        days  = hours // 24
        hours = hours % 24
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


# ── Actions ───────────────────────────────────────────────────────────────────
def start_task(name: str) -> bool:
    ok = ssh_ok(f'schtasks /run /tn "{name}"')
    return ok

def stop_task(name: str) -> bool:
    ok = ssh_ok(f'schtasks /end /tn "{name}"')
    return ok

def emergency_stop_all(tasks: list[dict]):
    print(red("\n⚠  EMERGENCY STOP — killing all bots and python processes"))
    for t in tasks:
        ssh(f'schtasks /end /tn "{t["name"]}" 2>nul')
    ssh("taskkill /F /IM python.exe 2>nul")
    print(red("All bots killed."))
    print(yellow("Open MT5 to verify no positions are still open."))


# ── Log Viewer ────────────────────────────────────────────────────────────────
def view_log(task_name: str, lines: int = 40):
    """Stream last N lines of a bot's log file."""
    if task_name not in LOG_MAP:
        print(yellow(f"No log path configured for {task_name}"))
        print(gray("Add it to LOG_MAP in algo.py"))
        return

    market, instance, logfile = LOG_MAP[task_name]
    path = f"C:\\algos\\markets\\{market}\\instances\\{instance}\\{logfile}"
    print(gray(f"\nLog: {path}\n"))

    raw = ssh(f"type {path} 2>nul")
    if not raw:
        print(yellow("Log file is empty or not found."))
        return

    log_lines = raw.splitlines()
    shown = log_lines[-lines:] if len(log_lines) > lines else log_lines
    for line in shown:
        # Colorize log levels
        if "ERROR" in line:
            print(red(line))
        elif "WARNING" in line:
            print(yellow(line))
        elif "FILLED" in line or "ORDER" in line or "SIGNAL" in line:
            print(green(line))
        elif "BREAKEVEN" in line or "PARTIAL" in line or "TRAIL" in line:
            print(cyan(line))
        else:
            print(gray(line))


# ── Display ───────────────────────────────────────────────────────────────────
def clear():
    os.system("clear")

def print_header(tasks: list[dict]):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    print(bold(cyan("╔══════════════════════════════════════════════════════════╗")))
    print(bold(cyan("║")) + bold(f"  ALGO CONTROL PANEL") + gray(f"  {now}") + bold(cyan("                ║")))
    print(bold(cyan("╠══════════════════════════════════════════════════════════╣")))

    if not tasks:
        print(bold(cyan("║")) + yellow("  No bot tasks found on VPS") + bold(cyan("                           ║")))
    else:
        for t in tasks:
            status_icon = green("●") if t["running"] else red("○")
            status_text = green("RUNNING") if t["running"] else red("STOPPED")

            if t["running"] and t["name"] in LOG_MAP:
                uptime = get_uptime(t["name"])
                uptime_str = gray(f"  up {uptime}") if uptime else ""
            else:
                uptime_str = ""

            print(bold(cyan("║")) + f"  {status_icon} " +
                  bold(f"{t['market']}/") + cyan(f"{t['pair']}/") +
                  f"{t['role']:<18} {status_text}{uptime_str}")

    print(bold(cyan("╚══════════════════════════════════════════════════════════╝")))

def print_menu():
    print()
    print(bold("  ACTIONS"))
    print(f"  {bold('[1]')} Start all bots")
    print(f"  {bold('[2]')} Stop all bots")
    print(f"  {bold('[r]')} Restart all bots")
    print(f"  {bold('[3]')} {red('Emergency stop everything')}")
    print(f"  {bold('[4]')} Manage individual bot")
    print(f"  {bold('[5]')} View bot log")
    print(f"  {bold('[6]')} Refresh status")
    print(f"  {bold('[q]')} Quit")
    print()

def print_bot_menu(tasks: list[dict]):
    print(bold("\n  SELECT BOT:\n"))
    for i, t in enumerate(tasks, 1):
        status = green("● RUNNING") if t["running"] else red("○ STOPPED")
        print(f"  {bold(f'[{i}]')} {t['market']}/{t['pair']}/{t['role']:<20} {status}")
    print(f"  {bold('[b]')} Back")
    print()

def bot_action_menu(task: dict) -> str:
    status = green("RUNNING") if task["running"] else red("STOPPED")
    print(bold(f"\n  {task['market']}/{task['pair']}/{task['role']} — {status}\n"))
    print(f"  {bold('[1]')} Start")
    print(f"  {bold('[2]')} Stop")
    print(f"  {bold('[3]')} Restart")
    print(f"  {bold('[4]')} View log (last 40 lines)")
    print(f"  {bold('[5]')} View log (last 100 lines)")
    print(f"  {bold('[b]')} Back")
    print()
    return input("  Choice: ").strip().lower()


# ── Main Loop ─────────────────────────────────────────────────────────────────
def main():
    print(gray("Connecting to VPS..."))

    try:
        tasks = get_all_tasks()
    except subprocess.TimeoutExpired:
        print(red("SSH connection timed out. Check your VPS connection."))
        sys.exit(1)
    except FileNotFoundError:
        print(red("SSH not found. Make sure OpenSSH is installed."))
        sys.exit(1)

    while True:
        clear()
        print_header(tasks)
        print_menu()

        choice = input("  Choice: ").strip().lower()

        if choice == "1":
            clear()
            print(bold("\n  Starting all bots...\n"))
            for t in tasks:
                print(gray(f"  → Launching {t['name']}..."), end="", flush=True)
                start_task(t["name"])
                # Poll for up to 8 seconds to confirm process started
                confirmed = False
                for _ in range(8):
                    import time; time.sleep(1)
                    updated = get_all_tasks()
                    match = next((x for x in updated if x["name"] == t["name"]), None)
                    if match and match["running"]:
                        confirmed = True
                        break
                if confirmed:
                    print(f"\r  {green('✓')} {t['name']:<30} {green('RUNNING')}")
                else:
                    print(f"\r  {red('✗')} {t['name']:<30} {red('FAILED TO START')}")
            tasks = get_all_tasks()
            print()
            input(gray("  Press Enter to continue..."))

        elif choice == "2":
            clear()
            print(bold("\n  Stopping all bots...\n"))
            for t in tasks:
                print(gray(f"  → Stopping {t['name']}..."), end="", flush=True)
                stop_task(t["name"])
                # Poll for up to 8 seconds to confirm process stopped
                confirmed = False
                for _ in range(8):
                    import time; time.sleep(1)
                    updated = get_all_tasks()
                    match = next((x for x in updated if x["name"] == t["name"]), None)
                    if match and not match["running"]:
                        confirmed = True
                        break
                if confirmed:
                    print(f"\r  {green('✓')} {t['name']:<30} {green('STOPPED')}")
                else:
                    print(f"\r  {yellow('?')} {t['name']:<30} {yellow('MAY STILL BE RUNNING')}")
            tasks = get_all_tasks()
            print()
            input(gray("  Press Enter to continue..."))

        elif choice == "r":
            clear()
            print(bold("\n  Restarting all bots...\n"))
            # Stop all first
            print(gray("  Stopping..."))
            for t in tasks:
                stop_task(t["name"])
            ssh("taskkill /F /IM python.exe 2>nul")
            import time; time.sleep(4)
            # Start all with confirmation
            print(gray("  Starting...\n"))
            for t in tasks:
                print(gray(f"  -> Launching {t['name']}..."), end="", flush=True)
                start_task(t["name"])
                confirmed = False
                for _ in range(10):
                    import time; time.sleep(1)
                    updated = get_all_tasks()
                    match = next((x for x in updated if x["name"] == t["name"]), None)
                    if match and match["running"]:
                        confirmed = True
                        break
                if confirmed:
                    print(f"\r  {green('✓')} {t['name']:<30} {green('RUNNING')}")
                else:
                    print(f"\r  {red('✗')} {t['name']:<30} {red('FAILED TO START')}")
            tasks = get_all_tasks()
            print()
            input(gray("  Press Enter to continue..."))

            confirm = input(red("  Type YES to confirm emergency stop: ")).strip()
            if confirm == "YES":
                emergency_stop_all(tasks)
                import time; time.sleep(3)
                tasks = get_all_tasks()
                print()
                input(gray("\n  Press Enter to continue..."))
            else:
                print(gray("  Cancelled."))

        elif choice == "4":
            while True:
                clear()
                print_header(tasks)
                print_bot_menu(tasks)
                bot_choice = input("  Select bot: ").strip().lower()
                if bot_choice == "b":
                    break
                if not bot_choice.isdigit():
                    continue
                idx = int(bot_choice) - 1
                if idx < 0 or idx >= len(tasks):
                    continue

                task = tasks[idx]
                while True:
                    clear()
                    action = bot_action_menu(task)
                    if action == "b":
                        break
                    elif action == "1":
                        print(gray(f"\n  Starting {task['name']}..."), end="", flush=True)
                        start_task(task["name"])
                        confirmed = False
                        for _ in range(8):
                            import time; time.sleep(1)
                            updated = get_all_tasks()
                            match = next((x for x in updated if x["name"] == task["name"]), None)
                            if match and match["running"]:
                                confirmed = True
                                task = match
                                break
                        print(f"\r  {green('✓ RUNNING') if confirmed else red('✗ FAILED')}")
                        input(gray("  Press Enter..."))
                    elif action == "2":
                        print(gray(f"\n  Stopping {task['name']}..."), end="", flush=True)
                        stop_task(task["name"])
                        confirmed = False
                        for _ in range(8):
                            import time; time.sleep(1)
                            updated = get_all_tasks()
                            match = next((x for x in updated if x["name"] == task["name"]), None)
                            if match and not match["running"]:
                                confirmed = True
                                task = match
                                break
                        print(f"\r  {green('✓ STOPPED') if confirmed else yellow('? MAY STILL BE RUNNING')}")
                        input(gray("  Press Enter..."))
                    elif action == "3":
                        print(gray(f"\n  Restarting {task['name']}..."), end="", flush=True)
                        stop_task(task["name"])
                        import time; time.sleep(3)
                        start_task(task["name"])
                        confirmed = False
                        for _ in range(8):
                            time.sleep(1)
                            updated = get_all_tasks()
                            match = next((x for x in updated if x["name"] == task["name"]), None)
                            if match and match["running"]:
                                confirmed = True
                                task = match
                                break
                        print(f"\r  {green('✓ RESTARTED') if confirmed else red('✗ RESTART FAILED')}")
                        input(gray("  Press Enter..."))
                    elif action in ("4", "5"):
                        lines = 40 if action == "4" else 100
                        clear()
                        view_log(task["name"], lines)
                        input(gray("\n  Press Enter to continue..."))

                tasks = get_all_tasks()

        elif choice == "5":
            clear()
            print_header(tasks)
            print_bot_menu(tasks)
            bot_choice = input("  Select bot to view log: ").strip()
            if bot_choice.isdigit():
                idx = int(bot_choice) - 1
                if 0 <= idx < len(tasks):
                    clear()
                    view_log(tasks[idx]["name"])
                    input(gray("\n  Press Enter to continue..."))

        elif choice == "6":
            print(gray("  Refreshing..."))
            tasks = get_all_tasks()

        elif choice in ("q", "quit", "exit"):
            print(gray("\n  Bye.\n"))
            sys.exit(0)


if __name__ == "__main__":
    # Support direct commands: algo restart, algo start, algo stop, algo status
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        try:
            tasks = get_all_tasks()
        except Exception as e:
            print(red(f"SSH connection failed: {e}"))
            sys.exit(1)

        if cmd == "restart":
            print(bold("Restarting all bots..."))
            for t in tasks:
                stop_task(t["name"])
            ssh("taskkill /F /IM python.exe 2>nul")
            import time; time.sleep(4)
            for t in tasks:
                print(gray(f"Starting {t['name']}..."), end="", flush=True)
                start_task(t["name"])
                confirmed = False
                for _ in range(10):
                    time.sleep(1)
                    updated = get_all_tasks()
                    match = next((x for x in updated if x["name"] == t["name"]), None)
                    if match and match["running"]:
                        confirmed = True
                        break
                print(f"\r{green('✓') if confirmed else red('✗')} {t['name']:<35} "
                      f"{green('RUNNING') if confirmed else red('FAILED')}")

        elif cmd == "start":
            print(bold("Starting all bots..."))
            for t in tasks:
                start_task(t["name"])
                print(f"  -> {t['name']}")

        elif cmd == "stop":
            print(bold("Stopping all bots..."))
            for t in tasks:
                stop_task(t["name"])
            ssh("taskkill /F /IM python.exe 2>nul")
            print(green("All bots stopped."))

        elif cmd == "status":
            for t in tasks:
                icon = green("● RUNNING") if t["running"] else red("○ STOPPED")
                print(f"  {icon}  {t['market']}/{t['pair']}/{t['role']}")

        else:
            print(f"Unknown command: {cmd}")
            print("Usage: algo [restart|start|stop|status]")
        sys.exit(0)

    main()


# ══════════════════════════════════════════════════════════════════════════════
# INSTALL AS A GLOBAL COMMAND
# Run this once in your Mac Terminal to use `algo` from anywhere:
#
#   chmod +x /Users/alwg/algos/algo.py
#   echo 'alias algo="python3 /Users/alwg/algos/algo.py"' >> ~/.zshrc
#   source ~/.zshrc
#
# Then just type: algo
# ══════════════════════════════════════════════════════════════════════════════
