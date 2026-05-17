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
    "BOT_": "Bot",
    "SYS_": "System",
}

# Map task name patterns to log file paths
# Format: partial task name match → (market, pair, instance_folder)
LOG_MAP = {
    # Trading bots
    "BOT_SMC_TREND":       ("fx",      "gold_main",        "bot_smc_trend.log"),
    "BOT_MEAN_REVERSION":  ("fx",      "gold_main",        "bot_mean_reversion.log"),
    "BOT_SCALPER":         ("fx",      "gold_scalper",     "bot_scalper.log"),
    "BOT_FFT":             ("fx",      "gold_fft",         "bot_fft.log"),
    "BOT_FUTURES_ACCT1":   ("futures", "futures_account1", "bot_futures.log"),
    "BOT_FUTURES_ACCT2":   ("futures", "futures_account2", "bot_futures.log"),
    "BOT_FUTURES_ACCT3":   ("futures", "futures_account3", "bot_futures.log"),
    "BOT_FUTURES_ACCT4":   ("futures", "futures_account4", "bot_futures.log"),
    "BOT_FUTURES_ACCT5":   ("futures", "futures_account5", "bot_futures.log"),
    # System — telegram uptime via offset file, not log
    "SYS_TELEGRAM":        None,
}

# Display names for panel — clean readable labels
DISPLAY_NAMES = {
    "BOT_SMC_TREND":       "SMC Trend",
    "BOT_MEAN_REVERSION":  "Mean Reversion",
    "BOT_SCALPER":         "Scalper",
    "BOT_FFT":             "FFT",
    "BOT_FUTURES_ACCT1":   "Futures Acct 1",
    "BOT_FUTURES_ACCT2":   "Futures Acct 2",
    "BOT_FUTURES_ACCT3":   "Futures Acct 3",
    "BOT_FUTURES_ACCT4":   "Futures Acct 4",
    "BOT_FUTURES_ACCT5":   "Futures Acct 5",
    "SYS_TELEGRAM":        "Telegram",
    "SYS_REPORTER":        "Reporter",
    "SYS_MONITOR":         "Monitor",
}

# Instance config paths for reading account_type and instrument
INSTANCE_CONFIGS = {
    "BOT_SMC_TREND":       r"C:\algos\markets\fx\instances\gold_main\config.json",
    "BOT_MEAN_REVERSION":  r"C:\algos\markets\fx\instances\gold_main\config.json",
    "BOT_SCALPER":         r"C:\algos\markets\fx\instances\gold_scalper\config.json",
    "BOT_FFT":             r"C:\algos\markets\fx\instances\gold_fft\config.json",
    "BOT_FUTURES_ACCT1":   r"C:\algos\markets\futures\instances\futures_account1\config.json",
}

# Scheduled job schedule descriptions
SCHEDULED_INFO = {
    "SYS_REPORTER": "daily 4pm CT",
    "SYS_MONITOR":  "every 1 min",
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
def blue(s):   return f"\033[94m{s}{C.RESET}"


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
        if "bot_smc_trend"     in line: running_scripts.add("bot1")
        if "bot_mean_reversion"in line: running_scripts.add("bot2")
        if "bot_scalper"       in line: running_scripts.add("bot3")
        if "bot_futures"     in line: running_scripts.add("bot4")
        if "bot_fft"           in line: running_scripts.add("bot5")
        if "telegram_bot"       in line: running_scripts.add("telegram")
        if "reporter"           in line: running_scripts.add("reporter")
        if "monitor"            in line: running_scripts.add("monitor")

    # Map task names to bot script keys
    TASK_BOT_MAP = {
        # FX
        "BOT_SMC_TREND":              "bot1",
        "BOT_MEAN_REVERSION":              "bot2",
        "BOT_SCALPER":           "bot3",
        "BOT_FFT":          "bot5",
        # Notifications
        "SYS_TELEGRAM":           "telegram",
        # Futures
        "BOT_FUTURES_ACCT1": "bot4",
        "ALGO_FUTURES_ACCT2": "bot4",
        "ALGO_FUTURES_ACCT3": "bot4",
        "ALGO_FUTURES_ACCT4": "bot4",
        "ALGO_FUTURES_ACCT5": "bot4",
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

        display = DISPLAY_NAMES.get(name, name)

        # Read account info from instance config (cached in task dict)
        acct_type  = "—"
        instrument = "—"
        account    = "—"
        if name in INSTANCE_CONFIGS:
            cfg_path = INSTANCE_CONFIGS[name]
            cfg_raw  = ssh(f"type {cfg_path} 2>nul")
            if cfg_raw:
                import json as _json
                try:
                    cfg        = _json.loads(cfg_raw)
                    acct_type  = cfg.get("account_type", "—").upper()
                    instrument = cfg.get("instrument",   "—")
                except Exception:
                    pass
            # Read account number from credentials.json
            cred_path = cfg_path.replace("config.json", "credentials.json")
            cred_raw  = ssh(f"type {cred_path} 2>nul")
            if cred_raw:
                try:
                    cred    = _json.loads(cred_raw)
                    account = str(cred.get("login", "—"))
                except Exception:
                    pass

        tasks.append({
            "name":       name,
            "market":     market_label,
            "pair":       display,
            "role":       "",
            "running":    running,
            "status":     "Running" if running else "Stopped",
            "acct_type":  acct_type,
            "instrument": instrument,
            "account":    account,
        })

    return sorted(tasks, key=lambda x: (x["market"], x["pair"], x["role"]))


def get_task_account_info(task_name: str) -> tuple:
    """
    Read account number, account_type, and instrument from the
    instance config.json on VPS. Returns (account, type, instrument).
    """
    if task_name not in INSTANCE_CONFIGS:
        return ("—", "—", "—")
    cfg_path = INSTANCE_CONFIGS[task_name]
    raw = ssh(f"type {cfg_path} 2>nul")
    if not raw:
        return ("—", "—", "—")
    import json as _json
    try:
        cfg = _json.loads(raw)
        acct_type  = cfg.get("account_type", "—").upper()
        instrument = cfg.get("instrument",   "—")
        return (acct_type, instrument)
    except Exception:
        return ("—", "—")


def get_uptime(task_name: str) -> str:
    """
    Calculate how long a bot has been running by reading its log file.
    For SYS_TELEGRAM, uses the offset file modification time instead.
    Scans log in reverse to find the most recent startup line.
    """
    if task_name not in LOG_MAP:
        return ""

    # Special case: Telegram uptime via offset file mtime
    if LOG_MAP[task_name] is None:
        raw = ssh("python -c \"import os,json; f='C:\\\\algos\\\\telegram_offset.json'; print(os.path.getmtime(f)) if os.path.exists(f) else print(0)\" 2>nul")
        try:
            mtime = float(raw.strip())
            if mtime == 0:
                return ""
            import time as _time
            delta   = _time.time() - mtime
            hours   = int(delta // 3600)
            minutes = int((delta % 3600) // 60)
            return f"{hours}h {minutes}m"
        except Exception:
            return ""

    market, instance, logfile = LOG_MAP[task_name]
    path = f"C:\\algos\\markets\\{market}\\instances\\{instance}\\{logfile}"

    raw = ssh(f"type {path} 2>nul")
    if not raw:
        return ""

    # Scan reversed — most recent startup line
    lines = raw.splitlines()
    start_time = None
    for line in reversed(lines):
        if ("STARTING" in line or
                ("Balance" in line and "Risk" in line) or
                ("Balance" in line and "AI:" in line)):
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
    # Restart telegram bot so you can still receive alerts and commands
    import time; time.sleep(3)
    start_task("SYS_TELEGRAM")
    print(green("Telegram bot restarted — you can still send commands."))


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


# Scheduled jobs — these run on a timer, not persistently
SCHEDULED_TASKS = {"SYS_REPORTER", "SYS_MONITOR"}

# ── Display ───────────────────────────────────────────────────────────────────
def clear():
    os.system("clear")

def print_header(tasks: list[dict], tab: str = "all"):
    """
    Render the control panel with guaranteed border alignment.
    Key rule: pad plain text to column width FIRST, then apply ANSI color.
    Never apply color before padding — f-string padding counts ANSI bytes
    as visible characters and throws off the right border.

    Layout: W=82 inner content, W+2=84 total with both ║ borders.
    3 sections (All tab): Trading Bots | Telegram | Scheduled Jobs
    Each section uses identical columns: Name | Account | Type | Inst | Status | Uptime/Schedule
    """
    import re
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    W   = 82  # inner content width; total panel width = W+2

    def strip_ansi(s: str) -> str:
        return re.sub(r'\033\[[0-9;]*m', '', s)

    def row(content: str) -> str:
        """Pad content so right border lands exactly at W+2."""
        pad = max(0, W - len(strip_ansi(content)))
        return bold(cyan("║")) + content + " " * pad + bold(cyan("║"))

    def col(text: str, width: int, color_fn=None) -> str:
        """Pad text to width, then optionally colorize. Never color before padding."""
        padded = f"{str(text):<{width}}"
        return color_fn(padded) if color_fn else padded

    # Tab bar — bold active tab
    tab_bar = "  ".join(
        bold(f"[{lbl}]") if key == tab else gray(f"[{lbl}]")
        for key, lbl in [("all","All"),("demo","Demo"),("live","Live")]
    )

    # Column header string (no color — just spacing reference)
    COL_HDR = f"  {'Name':<16}  {'Account':<12}  {'Type':<5}  {'Inst':<7}  {'Status':<9}  Uptime"
    SCH_HDR = f"  {'Name':<16}  {'Account':<12}  {'Type':<5}  {'Inst':<7}  {'Status':<9}  Schedule"

    print(bold(cyan("╔" + "═" * W + "╗")))
    print(row(f"  {bold('ALGO CONTROL PANEL')}  {gray(now)}    {tab_bar}"))
    print(bold(cyan("╠" + "═" * W + "╣")))

    if not tasks:
        print(row(yellow("  No tasks found on VPS")))
    else:
        bots  = [t for t in tasks if t["name"].startswith("BOT_")]
        sys_t = [t for t in tasks if t["name"] == "SYS_TELEGRAM"]
        sched = [t for t in tasks if t["name"] in SCHEDULED_TASKS]

        # Filter bots by tab
        if tab == "demo":
            bots    = [t for t in bots if t.get("acct_type","").upper() in ("DEMO","")]
            section = "Trading Bots — Demo"
        elif tab == "live":
            bots    = [t for t in bots if t.get("acct_type","").upper() == "LIVE"]
            section = "Trading Bots — Live"
        else:
            section = "Trading Bots"

        # ── Section: Trading Bots ─────────────────────────────────────────
        print(row(f"  {gray(section)}"))
        if bots:
            print(row(gray(COL_HDR)))
            for t in bots:
                icon  = green("●") if t["running"] else red("○")
                up    = ""
                if t["running"] and t["name"] in LOG_MAP and LOG_MAP[t["name"]]:
                    u = get_uptime(t["name"])
                    if u:
                        up = gray(u)
                print(row(
                    f"  {icon} "
                    f"{col(t['pair'][:16], 16)}  "
                    f"{col(t.get('account','—')[:12], 12, gray)}  "
                    f"{col(t.get('acct_type','—').upper()[:5], 5, gray)}  "
                    f"{col(t.get('instrument','—')[:7], 7, gray)}  "
                    f"{col('RUNNING' if t['running'] else 'STOPPED', 9, green if t['running'] else red)}  "
                    f"{up}"
                ))
        else:
            print(row(f"  {gray('No bots for this account type.')}"))
            if tab == "live":
                print(row(f"  {gray('Set account_type: live in a config.json')}"))

        # ── Sections: Telegram + Scheduled Jobs (All tab only) ────────────
        if tab == "all":
            if sys_t:
                print(row(""))
                print(row(f"  {gray('Telegram')}"))
                print(row(gray(COL_HDR)))
                for t in sys_t:
                    up = ""
                    if t["running"] and t["name"] in LOG_MAP:
                        u = get_uptime(t["name"])
                        if u:
                            up = gray(u)
                    print(row(
                        f"  {green('●') if t['running'] else red('○')} "
                        f"{col(t['pair'][:16], 16)}  "
                        f"{col('—', 12, gray)}  "
                        f"{col('—', 5, gray)}  "
                        f"{col('—', 7, gray)}  "
                        f"{col('RUNNING' if t['running'] else 'STOPPED', 9, green if t['running'] else red)}  "
                        f"{up}"
                    ))

            if sched:
                print(row(""))
                print(row(f"  {gray('Scheduled Jobs')}"))
                print(row(gray(SCH_HDR)))
                for t in sched:
                    schedule = gray(SCHEDULED_INFO.get(t["name"], ""))
                    print(row(
                        f"  {blue('◑')} "
                        f"{col(t['pair'][:16], 16)}  "
                        f"{col('—', 12, gray)}  "
                        f"{col('—', 5, gray)}  "
                        f"{col('—', 7, gray)}  "
                        f"{col('SCHEDULED', 9, cyan)}  "
                        f"{schedule}"
                    ))

    print(bold(cyan("╚" + "═" * W + "╝")))

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
    print(f"  {gray('[t1/t2/t3]')} {gray('Switch tab (All / Demo / Live)')}")
    print(f"  {bold('[q]')} Quit")
    print()

def print_bot_menu(tasks: list[dict]):
    print(bold("\n  SELECT BOT:\n"))
    for i, t in enumerate(tasks, 1):
        is_sched = t["name"] in SCHEDULED_TASKS
        if is_sched:
            status = blue("◑ SCHEDULED")
        else:
            status = green("● RUNNING") if t["running"] else red("○ STOPPED ")
        label = t["pair"]
        print(f"  {bold(f'[{i}]')} {label:<22} {status}")
    print(f"  {bold('[b]')} Back")
    print()

def bot_action_menu(task: dict) -> str:
    is_sched = task["name"] in SCHEDULED_TASKS
    if is_sched:
        status = blue("SCHEDULED")
    else:
        status = green("RUNNING") if task["running"] else red("STOPPED")
    print(bold(f"\n  {task['pair']} — {status}\n"))
    print(f"  {bold('[1]')} Start")
    print(f"  {bold('[2]')} Stop")
    print(f"  {bold('[3]')} Restart")
    print(f"  {bold('[4]')} View log (last 40 lines)")
    print(f"  {bold('[5]')} View log (last 100 lines)")
    if task["name"] == "SYS_TELEGRAM":
        print(f"  {bold('[u]')} Manage users")
    print(f"  {bold('[b]')} Back")
    print()
    return input("  Choice: ").strip().lower()


# ── User Management ───────────────────────────────────────────────────────────

USERS_FILE_VPS = r"C:\algos\users.json"


def read_users() -> dict:
    """Read users.json from VPS. Returns empty dict if missing."""
    raw = ssh(f"type {USERS_FILE_VPS} 2>nul")
    if not raw:
        return {}
    import json as _j
    try:
        return _j.loads(raw).get("users", {})
    except Exception:
        return {}


def write_users(users: dict):
    """Write users dict back to users.json on VPS."""
    import json as _j, tempfile, os
    data    = {"users": users}
    content = _j.dumps(data, indent=2)
    # Write via echo through SSH — escape for Windows cmd
    escaped = content.replace('"', '\\"').replace('\n', ' ')
    # Use Python on VPS to write the file (avoids shell escaping issues)
    py_cmd  = (
        f"python -c \""
        f"import json; "
        f"f=open(r'{USERS_FILE_VPS}','w'); "
        f"json.dump({_j.dumps(data)}, f, indent=2); "
        f"f.close(); "
        f"print('saved')\""
    )
    result = ssh(py_cmd)
    return "saved" in result


def manage_users_menu():
    """Full user management submenu — accessed from Telegram bot option."""
    while True:
        clear()
        users = read_users()

        print(bold("\n  USER MANAGEMENT\n"))

        if users:
            print(gray("  Current users:\n"))
            for uid, info in users.items():
                name  = info.get("name", "?")
                role  = info.get("role", "?").upper()
                added = info.get("added", "")
                date  = f"  {gray('added ' + added)}" if added else ""
                print(f"  {green('●') if role == 'ADMIN' else cyan('●')}  "
                      f"{name:<16}  {gray(uid):<14}  {bold(role)}{date}")
        else:
            print(gray("  No users configured yet.\n"))

        print()
        print(f"  {bold('[1]')} List users")
        print(f"  {bold('[2]')} Add user")
        print(f"  {bold('[3]')} Remove user")
        print(f"  {bold('[4]')} Change role")
        print(f"  {bold('[b]')} Back")
        print()

        choice = input("  Choice: ").strip().lower()

        if choice == "b":
            break

        elif choice == "1":
            # Already shown above — just pause
            print()
            input(gray("  Press Enter to continue..."))

        elif choice == "2":
            print(bold("\n  Add User\n"))
            print(gray("  Tip: ask them to message @userinfobot on Telegram to get their chat ID\n"))
            uid  = input("  Chat ID: ").strip()
            if not uid.isdigit():
                print(red("  Invalid chat ID — must be numbers only."))
                input(gray("  Press Enter...")); continue
            if uid in users:
                print(yellow(f"  User {uid} already exists. Use [4] to change their role."))
                input(gray("  Press Enter...")); continue
            name = input("  Name: ").strip()
            if not name:
                print(red("  Name cannot be empty.")); input(gray("  Press Enter...")); continue
            print(f"\n  Role: {bold('[1]')} admin   {bold('[2]')} readonly")
            r = input("  Role: ").strip()
            role = "admin" if r == "1" else "readonly"
            from datetime import datetime as _dt
            users[uid] = {
                "name":  name,
                "role":  role,
                "added": _dt.now().strftime("%Y-%m-%d"),
            }
            if write_users(users):
                print(green(f"\n  ✓ {name} added as {role.upper()}."))
            else:
                print(red("\n  Failed to save users.json on VPS."))
            input(gray("  Press Enter..."))

        elif choice == "3":
            if not users:
                print(yellow("  No users to remove.")); input(gray("  Press Enter...")); continue
            print(bold("\n  Remove User\n"))
            user_list = list(users.items())
            for i, (uid, info) in enumerate(user_list, 1):
                print(f"  {bold(f'[{i}]')} {info.get('name','?'):<16}  {gray(uid)}")
            print(f"  {bold('[b]')} Cancel")
            print()
            sel = input("  Select: ").strip().lower()
            if sel == "b":
                continue
            if sel.isdigit() and 1 <= int(sel) <= len(user_list):
                uid, info = user_list[int(sel) - 1]
                name = info.get("name", "?")
                confirm = input(f"  Remove {name}? (y/n): ").strip().lower()
                if confirm == "y":
                    del users[uid]
                    if write_users(users):
                        print(green(f"\n  ✓ {name} removed."))
                    else:
                        print(red("\n  Failed to save."))
                else:
                    print(gray("  Cancelled."))
            else:
                print(red("  Invalid selection."))
            input(gray("  Press Enter..."))

        elif choice == "4":
            if not users:
                print(yellow("  No users to update.")); input(gray("  Press Enter...")); continue
            print(bold("\n  Change Role\n"))
            user_list = list(users.items())
            for i, (uid, info) in enumerate(user_list, 1):
                role = info.get("role","?").upper()
                print(f"  {bold(f'[{i}]')} {info.get('name','?'):<16}  {gray(uid)}  {role}")
            print(f"  {bold('[b]')} Cancel")
            print()
            sel = input("  Select: ").strip().lower()
            if sel == "b":
                continue
            if sel.isdigit() and 1 <= int(sel) <= len(user_list):
                uid, info = user_list[int(sel) - 1]
                name = info.get("name", "?")
                current = info.get("role", "?").upper()
                print(f"\n  {name} — current role: {bold(current)}")
                print(f"  New role: {bold('[1]')} admin   {bold('[2]')} readonly")
                r = input("  Role: ").strip()
                if r not in ("1", "2"):
                    print(red("  Invalid.")); input(gray("  Press Enter...")); continue
                new_role = "admin" if r == "1" else "readonly"
                users[uid]["role"] = new_role
                if write_users(users):
                    print(green(f"\n  ✓ {name} updated to {new_role.upper()}."))
                else:
                    print(red("\n  Failed to save."))
            else:
                print(red("  Invalid selection."))
            input(gray("  Press Enter..."))
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

    active_tab = "all"

    while True:
        clear()
        print_header(tasks, active_tab)
        print_menu()

        choice = input("  Choice: ").strip().lower()

        # Tab switching
        if choice == "t1" or choice == "tab1":
            active_tab = "all"; continue
        if choice == "t2" or choice == "tab2":
            active_tab = "demo"; continue
        if choice == "t3" or choice == "tab3":
            active_tab = "live"; continue

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
            # Always restart telegram bot after any bot restart
            start_task("SYS_TELEGRAM")
            print(f"  {green('✓')} {'SYS_TELEGRAM':<30} {green('RESTARTED')}")
            tasks = get_all_tasks()
            print()
            input(gray("  Press Enter to continue..."))

        elif choice == "3":
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
                    elif action == "u" and task["name"] == "SYS_TELEGRAM":
                        manage_users_menu()

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
            # Always restart telegram bot
            start_task("SYS_TELEGRAM")
            print(f"{green('✓')} {'SYS_TELEGRAM':<35} {green('RESTARTED')}")

        elif cmd == "start":
            print(bold("Starting all bots..."))
            for t in tasks:
                start_task(t["name"])
                print(f"  -> {t['name']}")
            start_task("SYS_TELEGRAM")
            print(f"  -> ALGO_TELEGRAM")

        elif cmd == "stop":
            print(bold("Stopping all bots..."))
            for t in tasks:
                stop_task(t["name"])
            ssh("taskkill /F /IM python.exe 2>nul")
            print(green("All bots stopped."))

        elif cmd == "status":
            for t in tasks:
                is_sched = t["name"] in SCHEDULED_TASKS
                if is_sched:
                    icon = blue("◑ SCHEDULED")
                else:
                    icon = green("● RUNNING") if t["running"] else red("○ STOPPED")
                print(f"  {icon}  {t['pair']}")

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
