#!/usr/bin/env python3
"""
algo — Interactive Algo Trading Control Panel
Run from your Mac terminal: python3 algo.py
Or install as a command: see INSTALL section at bottom of this file.

Connects to your VPS over SSH and manages all trading bots.
All status data is fetched in ONE batched SSH call per refresh.
Auto-refreshes every 30 seconds. Redraws in-place (no screen flash).
"""

import subprocess
import sys
import os
import select
import json as _json
import time as _time
import shutil
from datetime import datetime

# ── VPS Config ────────────────────────────────────────────────────────────────
VPS_HOST = "forexvps"
LOG_BASE = "C:\\algos\\markets"

TG_TOKEN = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
TG_CHAT  = "-1003977707258"

MARKET_PREFIXES = {
    "BOT_": "Bot",
    "SYS_": "System",
}

# Map task name → (market, instance, logfile) — used only by log viewer
LOG_MAP = {
    "BOT_SMC_TREND":       ("fx",      "gold_main",        "smc_trend_stdout.log"),
    "BOT_MEAN_REVERSION":  ("fx",      "gold_main",        "mean_reversion_stdout.log"),
    "BOT_SCALPER":         ("fx",      "gold_scalper",     "scalper_stdout.log"),
    "BOT_FFT":             ("fx",      "gold_fft",         "fft_stdout.log"),
    "BOT_FUTURES_ACCT1":   ("futures", "futures_account1", "bot_futures.log"),
    "BOT_FUTURES_ACCT2":   ("futures", "futures_account2", "bot_futures.log"),
    "BOT_FUTURES_ACCT3":   ("futures", "futures_account3", "bot_futures.log"),
    "BOT_FUTURES_ACCT4":   ("futures", "futures_account4", "bot_futures.log"),
    "BOT_FUTURES_ACCT5":   ("futures", "futures_account5", "bot_futures.log"),
    "SYS_TELEGRAM":        None,
}

# Display names — must match bot_state.py BOT_NAMES exactly
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
    "SYS_PNLTRACKER":      "P&L Tracker",
}

# Explicit display order — matches telegram /status and /balance
BOT_DISPLAY_ORDER = [
    "BOT_SMC_TREND", "BOT_MEAN_REVERSION", "BOT_SCALPER", "BOT_FFT",
    "BOT_FUTURES_ACCT1", "BOT_FUTURES_ACCT2", "BOT_FUTURES_ACCT3",
    "BOT_FUTURES_ACCT4", "BOT_FUTURES_ACCT5",
]

# bot_state.json key for each task
TASK_BOT_KEYS = {
    "BOT_SMC_TREND":      "smc_trend",
    "BOT_MEAN_REVERSION": "mean_reversion",
    "BOT_SCALPER":        "scalper",
    "BOT_FFT":            "fft",
}

# Hard-coded account types — update when live bots are added
TASK_ACCT_TYPE = {
    "BOT_SMC_TREND":      "DEMO",
    "BOT_MEAN_REVERSION": "DEMO",
    "BOT_SCALPER":        "DEMO",
    "BOT_FFT":            "DEMO",
    "BOT_FUTURES_ACCT1":  "DEMO",
}

# Script keyword used to identify the bot's Python process in the process list.
# Used to force-kill the process before restart (schtasks /end alone is not reliable).
TASK_SCRIPT_MAP = {
    "BOT_SMC_TREND":      "bot_smc_trend",
    "BOT_MEAN_REVERSION": "bot_mean_reversion",
    "BOT_SCALPER":        "bot_scalper",
    "BOT_FFT":            "bot_fft",
    "SYS_TELEGRAM":       "telegram_bot",
}

# Maps task scheduler name → telegram_bot.py BOTS key (for crash-alert suppression)
TASK_SUPPRESS_KEY_MAP = {
    "BOT_SMC_TREND":      "smc",
    "BOT_MEAN_REVERSION": "reversion",
    "BOT_SCALPER":        "scalper",
    "BOT_FFT":            "fft",
}

SCHEDULED_INFO = {
    "SYS_REPORTER":   "daily 4pm CT",
    "SYS_MONITOR":    "every 1 min",
    "SYS_PNLTRACKER": "every 1 min",
}

AUTO_REFRESH_SECS = 30

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
    DIM    = "\033[2m"
    RESET  = "\033[0m"
    ROYAL  = "\033[38;5;27m"

def green(s):  return f"{C.GREEN}{s}{C.RESET}"
def red(s):    return f"{C.RED}{s}{C.RESET}"
def yellow(s): return f"{C.YELLOW}{s}{C.RESET}"
def cyan(s):   return f"{C.CYAN}{s}{C.RESET}"
def bold(s):   return f"{C.BOLD}{s}{C.RESET}"
def gray(s):   return f"{C.GRAY}{s}{C.RESET}"
def blue(s):   return f"\033[94m{s}{C.RESET}"
def royal(s):  return f"{C.ROYAL}{s}{C.RESET}"
def dim(s):    return f"{C.DIM}{s}{C.RESET}"


# ── LWG CAPITAL Banner ────────────────────────────────────────────────────────
BANNER = [
    "  ██╗     ██╗    ██╗ ██████╗      ██████╗ █████╗ ██████╗ ██╗████████╗ █████╗ ██╗   ",
    "  ██║     ██║    ██║██╔════╝     ██╔════╝██╔══██╗██╔══██╗██║╚══██╔══╝██╔══██╗██║   ",
    "  ██║     ██║ █╗ ██║██║  ███╗    ██║     ███████║██████╔╝██║   ██║   ███████║██║   ",
    "  ██║     ██║███╗██║██║   ██║    ██║     ██╔══██║██╔═══╝ ██║   ██║   ██╔══██║██║   ",
    "  ███████╗╚███╔███╔╝╚██████╔╝    ╚██████╗██║  ██║██║     ██║   ██║   ██║  ██║███████╗",
    "  ╚══════╝ ╚══╝╚══╝  ╚═════╝      ╚═════╝╚═╝  ╚═╝╚═╝     ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝",
]

def _get_term_width() -> int:
    cols = shutil.get_terminal_size(fallback=(100, 40)).columns
    return max(96, min(cols - 2, 140))


# ── SSH Helpers ───────────────────────────────────────────────────────────────
def ssh(cmd: str, capture=True) -> str:
    result = subprocess.run(
        ["ssh", VPS_HOST, cmd],
        capture_output=capture, text=True, timeout=30
    )
    return result.stdout.strip() if capture else ""

def ssh_ok(cmd: str) -> bool:
    result = subprocess.run(
        ["ssh", VPS_HOST, cmd],
        capture_output=True, text=True, timeout=30
    )
    return result.returncode == 0


# ── Batched VPS Snapshot ──────────────────────────────────────────────────────
def _parse_sections(raw: str, initial_section: str) -> dict:
    """Split raw SSH output into named sections using ===NAME=== delimiters."""
    sections: dict[str, str] = {}
    current = initial_section
    buf: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("===") and stripped.endswith("==="):
            sections[current] = "\n".join(buf).strip()
            current = stripped.strip("=").strip().lower().replace(" ", "_")
            buf = []
        else:
            buf.append(line)
    sections[current] = "\n".join(buf).strip()
    return sections


def fetch_vps_snapshot() -> dict:
    """
    Two SSH calls that fetch all status data needed for the panel.

    Call 1 (procs+tasks): wmic process list + schtasks CSV.
    Call 2 (state files): bot_state.json reads isolated — avoids Windows
    stdout-buffering issue where `type` output leaks into wrong sections
    when chained with `&` alongside other commands.

    Returns a merged dict of section_name → raw_string.
    """
    # Call 1: process list + task scheduler
    cmd1 = (
        "wmic process where \"name='python.exe'\" get commandline /format:list 2>nul"
        " & echo ===TASKS==="
        " & schtasks /query /fo CSV /nh 2>nul"
    )
    sections = _parse_sections(ssh(cmd1), "procs")

    # Call 2: bot state files.
    # Notes:
    #   - No `2>nul` with `type` in a `&` chain: Windows cmd.exe quirk causes
    #     `2>nul` to suppress stdout too. Use `if exist` to skip missing files.
    #   - `echo.` before each marker: `type` does not append a trailing newline,
    #     so the last `}` of a JSON file and the next marker land on the same
    #     line (e.g. `}===STATE_SCALPER===`), breaking the section parser.
    cmd2 = (
        "if exist C:\\algos\\markets\\fx\\instances\\gold_main\\bot_state.json"
        " (type C:\\algos\\markets\\fx\\instances\\gold_main\\bot_state.json)"
        " & echo. & echo ===STATE_SCALPER==="
        " & if exist C:\\algos\\markets\\fx\\instances\\gold_scalper\\bot_state.json"
        " (type C:\\algos\\markets\\fx\\instances\\gold_scalper\\bot_state.json)"
        " & echo. & echo ===STATE_FFT==="
        " & if exist C:\\algos\\markets\\fx\\instances\\gold_fft\\bot_state.json"
        " (type C:\\algos\\markets\\fx\\instances\\gold_fft\\bot_state.json)"
        " & echo. & echo ===TELEGRAM_START==="
        " & if exist C:\\algos\\telegram_start.json"
        " (type C:\\algos\\telegram_start.json)"
    )
    sections.update(_parse_sections(ssh(cmd2), "state_main"))

    return sections


def _parse_bot_states(snap: dict) -> dict:
    """
    Parse bot_state.json sections from snapshot.
    Returns {bot_key: state_dict} for all known bots.
    """
    states: dict[str, dict] = {}
    for section, keys in [
        ("state_main",    ["smc_trend", "mean_reversion"]),
        ("state_scalper", ["scalper"]),
        ("state_fft",     ["fft"]),
    ]:
        raw = snap.get(section, "")
        if not raw:
            continue
        try:
            data = _json.loads(raw)
            for k in keys:
                if k in data:
                    states[k] = data[k]
        except Exception:
            pass
    return states


def _fmt_uptime(delta_seconds: float) -> str:
    hours   = int(delta_seconds // 3600)
    minutes = int((delta_seconds % 3600) // 60)
    if hours >= 24:
        days  = hours // 24
        hours = hours % 24
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


# ── Task Discovery ────────────────────────────────────────────────────────────
def get_all_tasks(snap: dict) -> list[dict]:
    """
    Build task list from pre-fetched VPS snapshot.
    No SSH calls — all data comes from snapshot.
    """
    now = _time.time()

    # Running python processes
    running_scripts: set[str] = set()
    for line in snap.get("procs", "").splitlines():
        if "bot_smc_trend"      in line: running_scripts.add("bot1")
        if "bot_mean_reversion" in line: running_scripts.add("bot2")
        if "bot_scalper"        in line: running_scripts.add("bot3")
        if "bot_futures"        in line: running_scripts.add("bot4")
        if "bot_fft"            in line: running_scripts.add("bot5")
        if "telegram_bot"       in line: running_scripts.add("telegram")
        if "reporter"           in line: running_scripts.add("reporter")
        if "monitor"            in line: running_scripts.add("monitor")

    TASK_BOT_MAP = {
        "BOT_SMC_TREND":      "bot1",
        "BOT_MEAN_REVERSION": "bot2",
        "BOT_SCALPER":        "bot3",
        "BOT_FFT":            "bot5",
        "SYS_TELEGRAM":       "telegram",
        "SYS_PNLTRACKER":     "pnltracker",
        "BOT_FUTURES_ACCT1":  "bot4",
        "ALGO_FUTURES_ACCT2": "bot4",
        "ALGO_FUTURES_ACCT3": "bot4",
        "ALGO_FUTURES_ACCT4": "bot4",
        "ALGO_FUTURES_ACCT5": "bot4",
    }

    bot_states = _parse_bot_states(snap)

    # Telegram uptime from telegram_start.json
    telegram_uptime = ""
    tg_raw = snap.get("telegram_start", "")
    if tg_raw:
        try:
            started = float(_json.loads(tg_raw)["started"])
            telegram_uptime = _fmt_uptime(now - started)
        except Exception:
            pass

    tasks = []
    raw_tasks = snap.get("tasks", "")
    for line in raw_tasks.splitlines():
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

        bot_key_proc = TASK_BOT_MAP.get(name)
        running = bot_key_proc in running_scripts if bot_key_proc else False
        display = DISPLAY_NAMES.get(name, name)

        # Balance and uptime from pre-fetched bot state
        bot_key = TASK_BOT_KEYS.get(name)
        state   = bot_states.get(bot_key, {}) if bot_key else {}

        balance     = state.get("balance", 0.0) if state else 0.0
        daily_pct   = state.get("daily_pnl_pct", 0.0) if state else 0.0
        total_pct   = state.get("total_pnl_pct", 0.0) if state else 0.0
        account     = state.get("account", "—") if state else "—"
        if not account:
            account = "—"

        stalled = running and bool(bot_key) and state.get("status") == "stalled"

        uptime = ""
        if name == "SYS_TELEGRAM":
            uptime = telegram_uptime
        elif running and bot_key:
            started = state.get("started", 0) if state else 0
            if started:
                uptime = _fmt_uptime(now - started)

        tasks.append({
            "name":       name,
            "market":     market_label,
            "pair":       display,
            "running":    running,
            "stalled":    stalled,
            "status":     "Stalled" if stalled else ("Running" if running else "Stopped"),
            "acct_type":  TASK_ACCT_TYPE.get(name, "—"),
            "account":    account,
            "balance":    balance,
            "daily_pct":  daily_pct,
            "total_pct":  total_pct,
            "uptime":     uptime,
        })

    def _sort_key(t):
        try:
            return (0 if t["name"].startswith("BOT_") else 1,
                    BOT_DISPLAY_ORDER.index(t["name"]) if t["name"] in BOT_DISPLAY_ORDER else 999,
                    t["pair"])
        except Exception:
            return (1, 999, t["pair"])

    return sorted(tasks, key=_sort_key)


# ── Actions ───────────────────────────────────────────────────────────────────
def start_task(name: str) -> bool:
    return ssh_ok(f'schtasks /run /tn "{name}"')

def stop_task(name: str) -> bool:
    return ssh_ok(f'schtasks /end /tn "{name}"')

def stop_bot(name: str) -> bool:
    """Stop the scheduler task, force-kill the Python process, and wait until dead.
    Returns True if the process is confirmed gone. Use this everywhere — stop and restart."""
    stop_task(name)
    kill_bot_process(name)
    return wait_for_process_death(name, timeout=10)

def suppress_stop_alert(task_name: str):
    """Write bot key to VPS stop_suppress.json so the crash monitor skips alerting."""
    key = TASK_SUPPRESS_KEY_MAP.get(task_name)
    if not key:
        return
    ssh(
        f'python -c "'
        f'import json,pathlib;'
        f'p=pathlib.Path(r\'C:/algos/stop_suppress.json\');'
        f'k=json.loads(p.read_text()) if p.exists() else [];'
        f'k.append(\'{key}\') if \'{key}\' not in k else None;'
        f'p.write_text(json.dumps(k))"'
    )

def kill_bot_process(task_name: str):
    """Force-kill the specific bot's Python process after schtasks /end.

    schtasks /end stops the task entry but does not reliably terminate the running
    Python process. If the process is still alive when schtasks /run is called,
    Windows Task Scheduler refuses to start a new instance (default policy).
    %% is the cmd.exe escape for a literal % — without it, cmd.exe strips %script%
    to an empty string over SSH and the wmic LIKE query matches nothing.
    """
    script = TASK_SCRIPT_MAP.get(task_name, "")
    if not script:
        return
    ssh(
        f"wmic process where "
        f"\"name='python.exe' and commandline like '%%{script}%%'\" "
        f"call terminate 2>nul"
    )


def wait_for_process_death(task_name: str, timeout: int = 10) -> bool:
    """Poll until the bot's Python process is gone or timeout expires. Returns True if dead."""
    script = TASK_SCRIPT_MAP.get(task_name, "")
    if not script:
        return True
    for _ in range(timeout):
        _time.sleep(1)
        out = ssh(f"wmic process where \"name='python.exe'\" get commandline 2>nul")
        if script not in out:
            return True
    return False

def wait_for_state(task_name: str, want_running: bool, timeout: int = 8):
    """Poll VPS snapshot until task matches desired running state or timeout expires.
    Returns (confirmed: bool, updated_task: dict | None)."""
    for _ in range(timeout):
        _time.sleep(1)
        snap  = fetch_vps_snapshot()
        tasks = get_all_tasks(snap)
        match = next((t for t in tasks if t["name"] == task_name), None)
        if match and match["running"] == want_running:
            return True, match
    return False, None

def notify_telegram(text: str):
    import urllib.request, urllib.parse
    url  = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text, "parse_mode": "Markdown"}).encode()
    try:
        urllib.request.urlopen(url, data=data, timeout=5)
    except Exception:
        pass


def emergency_stop_all(tasks: list[dict]):
    print(red("\n⚠  EMERGENCY STOP — killing all bots and python processes"))
    for t in tasks:
        ssh(f'schtasks /end /tn "{t["name"]}" 2>nul')
    ssh("taskkill /F /IM python.exe 2>nul")
    print(red("All bots killed."))
    print(yellow("Open MT5 to verify no positions are still open."))
    import time; time.sleep(3)
    start_task("SYS_TELEGRAM")
    print(green("Telegram bot restarted — you can still send commands."))


# ── Log Viewer ────────────────────────────────────────────────────────────────
def view_log(task_name: str, lines: int = 40):
    if task_name not in LOG_MAP:
        print(yellow(f"No log path configured for {task_name}"))
        return
    if LOG_MAP[task_name] is None:
        print(yellow(f"{task_name} has no log file."))
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
        if "ERROR"   in line: print(red(line))
        elif "WARNING" in line: print(yellow(line))
        elif "FILLED" in line or "ORDER" in line or "SIGNAL" in line: print(green(line))
        elif "BREAKEVEN" in line or "PARTIAL" in line or "TRAIL" in line: print(cyan(line))
        else: print(gray(line))


SCHEDULED_TASKS = {"SYS_REPORTER", "SYS_MONITOR", "SYS_PNLTRACKER"}

# ── Display ───────────────────────────────────────────────────────────────────
def clear():
    sys.stdout.write("\033[H\033[2J")
    sys.stdout.flush()

def print_header(tasks: list[dict], tab: str = "all", show_menu: bool = True):
    import re
    now = datetime.utcnow().strftime("%Y-%m-%d  %H:%M UTC")
    W   = _get_term_width()

    def strip_ansi(s: str) -> str:
        return re.sub(r'\033\[[0-9;]*m', '', s)

    def row(content: str) -> str:
        pad = max(0, W - len(strip_ansi(content)))
        return bold(royal("║")) + content + " " * pad + bold(royal("║"))

    def col(text: str, width: int) -> str:
        return f"{str(text):<{width}}"

    def div() -> str:
        return row("  " + gray("─" * (W - 4)))

    def section(label: str) -> str:
        return row(f"  {royal('▸')} {bold(label)}")

    def fmt_balance(balance: float) -> str:
        if balance <= 0:
            return col("—", W_BAL)
        return col(f"${balance:,.2f}", W_BAL)

    W_NAME   = 20
    W_ACCT   = 12
    W_TYPE   = 5
    W_BAL    = 12
    W_PNL    = 8
    W_STATUS = 10

    def col_hdr(is_sched: bool = False) -> str:
        info_lbl = "Schedule" if is_sched else "Uptime"
        return (
            f"    {col('Name', W_NAME)} "
            f"{col('Account', W_ACCT)} "
            f"{col('Type', W_TYPE)} "
            f"{col('Balance', W_BAL)} "
            f"{col('P&L%', W_PNL)} "
            f"{col('Status', W_STATUS)} "
            f"{info_lbl}"
        )

    def bot_row(t: dict, is_sched: bool = False) -> str:
        if is_sched:
            icon_char   = "◑"
            icon_fn     = royal
            status_text = "SCHEDULED"
            status_fn   = royal
            info        = gray(SCHEDULED_INFO.get(t["name"], ""))
            balance_str = col("—", W_BAL)
            pnl_str     = col("—", W_PNL)
        else:
            running = t["running"]
            stalled = t.get("stalled", False)
            if stalled:
                icon_char   = "◐"
                icon_fn     = yellow
                status_text = "STALLED"
                status_fn   = yellow
            elif running:
                icon_char   = "●"
                icon_fn     = green
                status_text = "RUNNING"
                status_fn   = green
            else:
                icon_char   = "○"
                icon_fn     = red
                status_text = "STOPPED"
                status_fn   = red
            balance_str = fmt_balance(t.get("balance", 0.0))

            tpct = t.get("total_pct", 0.0)
            if tpct == 0.0:
                pnl_str = col("—", W_PNL)
            else:
                sign    = "+" if tpct >= 0 else ""
                txt     = f"{sign}{tpct:.1f}%"
                pnl_fn  = green if tpct > 0 else red
                pnl_str = pnl_fn(col(txt, W_PNL))

            info = gray(t.get("uptime", ""))

        name_str   = col(t["pair"][:W_NAME], W_NAME)
        acct_str   = col(t.get("account", "—")[:W_ACCT], W_ACCT)
        type_str   = col(t.get("acct_type", "—")[:W_TYPE], W_TYPE)
        status_str = col(status_text, W_STATUS)

        return (
            f"  {icon_fn(icon_char)} "
            f"{name_str} "
            f"{gray(acct_str)} "
            f"{gray(type_str)} "
            f"{gray(balance_str)} "
            f"{pnl_str} "
            f"{status_fn(status_str)} "
            f"{info}"
        )

    # Tab bar
    tab_parts = []
    for key, lbl in [("all", "All"), ("demo", "Demo"), ("live", "Live")]:
        if key == tab:
            tab_parts.append(bold(f"▌{lbl}▐"))
        else:
            tab_parts.append(gray(f" {lbl} "))
    tab_bar = "  ".join(tab_parts)

    # Footer menu line
    menu_line = (
        f"  {bold(royal('[1]'))} Start All  "
        f"{bold(royal('[2]'))} Stop All  "
        f"{bold(royal('[r]'))} Restart  "
        f"{bold(royal('[3]'))} {red('Emergency')}  "
        f"{bold(royal('[4]'))} Manage  "
        f"{bold(royal('[5]'))} Log  "
        f"{bold(royal('[6]'))} Refresh  "
        f"{bold(royal('[q]'))} Quit"
    )

    # ── Top border + LWG CAPITAL banner ──────────────────────────────────────
    print(bold(royal("╔" + "═" * W + "╗")))
    print(row(""))
    for line in BANNER:
        print(row(bold(line)))
    print(row(""))

    # ── Info bar: time left, tab switcher ─────────────────────────────────────
    print(bold(royal("╠" + "═" * W + "╣")))
    time_str = gray(now)
    tab_vis  = len(strip_ansi(tab_bar))
    time_vis = 2 + len(strip_ansi(time_str))
    gap = max(1, W - time_vis - tab_vis - 2)
    print(row(f"  {time_str}" + " " * gap + tab_bar + " "))

    # ── Body ──────────────────────────────────────────────────────────────────
    print(bold(royal("╠" + "═" * W + "╣")))

    if not tasks:
        print(row(yellow("  No tasks found on VPS")))
    else:
        bots  = [t for t in tasks if t["name"].startswith("BOT_")]
        sys_t = [t for t in tasks if t["name"] == "SYS_TELEGRAM"]
        sched = [t for t in tasks if t["name"] in SCHEDULED_TASKS]

        if tab == "demo":
            bots        = [t for t in bots if t.get("acct_type", "").upper() in ("DEMO", "")]
            bot_section = "Trading Bots — Demo"
        elif tab == "live":
            bots        = [t for t in bots if t.get("acct_type", "").upper() == "LIVE"]
            bot_section = "Trading Bots — Live"
        else:
            bot_section = "Trading Bots"

        print(section(bot_section))
        print(div())
        if bots:
            print(row(gray(col_hdr())))
            print(div())
            for t in bots:
                print(row(bot_row(t)))
        else:
            print(row(f"  {gray('No bots for this account type.')}"))
            if tab == "live":
                print(row(f"  {gray('Set acct_type: live in config.json')}"))

        if tab == "all":
            if sys_t:
                print(row(""))
                print(section("Telegram"))
                print(div())
                print(row(gray(col_hdr())))
                print(div())
                for t in sys_t:
                    print(row(bot_row(t)))

            if sched:
                print(row(""))
                print(section("Scheduled Jobs"))
                print(div())
                print(row(gray(col_hdr(is_sched=True))))
                print(div())
                for t in sched:
                    print(row(bot_row(t, is_sched=True)))

    # ── Footer menu ───────────────────────────────────────────────────────────
    if show_menu:
        print(bold(royal("╠" + "═" * W + "╣")))
        print(row(menu_line))
    print(bold(royal("╚" + "═" * W + "╝")))


def print_menu():
    pass  # menu is now embedded in the print_header footer


def print_bot_menu(tasks: list[dict]):
    print(bold("\n  SELECT BOT:\n"))
    for i, t in enumerate(tasks, 1):
        is_sched = t["name"] in SCHEDULED_TASKS
        if is_sched:
            status = royal("◑") + gray(" SCHEDULED")
        elif t.get("stalled"):
            status = yellow("◐ STALLED  ")
        elif t["running"]:
            status = green("● RUNNING  ")
        else:
            status = red("○ STOPPED  ")
        print(f"  {bold(royal(f'[{i}]'))} {t['pair']:<22} {status}")
    print(f"  {bold(royal('[b]'))} Back")
    print()

def print_bot_detail(task: dict):
    import re
    W = _get_term_width()

    def strip_ansi(s: str) -> str:
        return re.sub(r'\033\[[0-9;]*m', '', s)

    def row(content: str) -> str:
        pad = max(0, W - len(strip_ansi(content)))
        return bold(royal("║")) + content + " " * pad + bold(royal("║"))

    is_sched  = task["name"] in SCHEDULED_TASKS
    running   = task.get("running", False)
    stalled   = task.get("stalled", False)
    if is_sched:
        icon_str   = royal("◑")
        status_str = royal("SCHEDULED")
    elif stalled:
        icon_str   = yellow("◐")
        status_str = yellow("STALLED")
    elif running:
        icon_str   = green("●")
        status_str = green("RUNNING")
    else:
        icon_str   = red("○")
        status_str = red("STOPPED")

    acct_type = task.get("acct_type", "—")
    account   = task.get("account", "—")
    acct_disp = gray(f"{acct_type}  #{account}") if account != "—" else gray(acct_type)

    header = f"  {icon_str} {bold(task['pair'])} — {status_str}    {acct_disp}"

    balance = task.get("balance", 0.0)
    daily   = task.get("daily_pct", 0.0)
    total   = task.get("total_pct", 0.0)
    uptime  = task.get("uptime", "") or "—"

    bal_str    = f"${balance:,.2f}" if balance > 0 else "—"
    d_sign     = "+" if daily >= 0 else ""
    d_clr      = green if daily > 0 else (red if daily < 0 else gray)
    t_sign     = "+" if total >= 0 else ""
    t_clr      = green if total > 0 else (red if total < 0 else gray)

    data = (
        f"  Balance {gray(bal_str)}"
        f"    Daily P&L {d_clr(f'{d_sign}{daily:.1f}%')}"
        f"    Total P&L {t_clr(f'{t_sign}{total:.1f}%')}"
        f"    Uptime {gray(uptime)}"
    )

    print(bold(royal("╔" + "═" * W + "╗")))
    print(row(header))
    print(bold(royal("╠" + "═" * W + "╣")))
    print(row(data))
    print(bold(royal("╚" + "═" * W + "╝")))


def bot_action_menu(task: dict) -> str:
    print_bot_detail(task)
    print()
    print(f"  {bold(royal('[1]'))} Start")
    print(f"  {bold(royal('[2]'))} Stop")
    print(f"  {bold(royal('[3]'))} Restart")
    print(f"  {bold(royal('[4]'))} View log (last 40 lines)")
    print(f"  {bold(royal('[5]'))} View log (last 100 lines)")
    if task["name"] == "SYS_TELEGRAM":
        print(f"  {bold(royal('[u]'))} Manage users")
    print(f"  {bold(royal('[r]'))} Refresh")
    print(f"  {bold(royal('[b]'))} Back")
    print(f"  {bold(royal('[q]'))} Quit")
    print()
    return input("  Choice: ").strip().lower()


# ── Non-blocking Input with Live Countdown ────────────────────────────────────
def input_or_timeout(prompt: str, timeout: int):
    """
    Show a live countdown and wait for input.
    Returns None on timeout (triggers auto-refresh).
    Works on macOS/Linux via select.select.
    """
    end_time = _time.monotonic() + timeout
    while True:
        remaining = int(end_time - _time.monotonic())
        if remaining <= 0:
            print()
            return None
        sys.stdout.write(
            f"\r  {C.BOLD}Choice{C.RESET} "
            f"[{C.ROYAL}{remaining}{C.RESET}s]: "
        )
        sys.stdout.flush()
        ready, _, _ = select.select([sys.stdin], [], [], 1.0)
        if ready:
            return sys.stdin.readline().strip().lower()


# ── User Management ───────────────────────────────────────────────────────────
USERS_FILE_VPS = r"C:\algos\users.json"

def read_users() -> dict:
    raw = ssh(f"type {USERS_FILE_VPS} 2>nul")
    if not raw:
        return {}
    try:
        return _json.loads(raw).get("users", {})
    except Exception:
        return {}

def write_users(users: dict):
    import base64
    data    = {"users": users}
    content = _json.dumps(data, indent=2)
    b64     = base64.b64encode(content.encode("utf-8")).decode("ascii")
    py_cmd = (
        f'python -c "'
        f"import base64; "
        f"open(r'{USERS_FILE_VPS}','wb').write(base64.b64decode('{b64}')); "
        f"print('saved')"
        f'"'
    )
    result = ssh(py_cmd)
    return "saved" in result

def manage_users_menu():
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
        print(f"  {bold(royal('[1]'))} List users")
        print(f"  {bold(royal('[2]'))} Add user")
        print(f"  {bold(royal('[3]'))} Remove user")
        print(f"  {bold(royal('[4]'))} Change role")
        print(f"  {bold(royal('[b]'))} Back")
        print()
        choice = input("  Choice: ").strip().lower()
        if choice == "b":
            break
        elif choice == "1":
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
            print(f"\n  Role: {bold(royal('[1]'))} admin   {bold(royal('[2]'))} readonly")
            r = input("  Role: ").strip()
            role = "admin" if r == "1" else "readonly"
            from datetime import datetime as _dt
            users[uid] = {"name": name, "role": role, "added": _dt.now().strftime("%Y-%m-%d")}
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
                print(f"  {bold(royal(f'[{i}]'))} {info.get('name','?'):<16}  {gray(uid)}")
            print(f"  {bold(royal('[b]'))} Cancel")
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
                print(f"  {bold(royal(f'[{i}]'))} {info.get('name','?'):<16}  {gray(uid)}  {role}")
            print(f"  {bold(royal('[b]'))} Cancel")
            print()
            sel = input("  Select: ").strip().lower()
            if sel == "b":
                continue
            if sel.isdigit() and 1 <= int(sel) <= len(user_list):
                uid, info = user_list[int(sel) - 1]
                name = info.get("name", "?")
                current = info.get("role", "?").upper()
                print(f"\n  {name} — current role: {bold(current)}")
                print(f"  New role: {bold(royal('[1]'))} admin   {bold(royal('[2]'))} readonly")
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
        snap  = fetch_vps_snapshot()
        tasks = get_all_tasks(snap)
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

        choice = input_or_timeout("", AUTO_REFRESH_SECS)

        # Auto-refresh on timeout
        if choice is None:
            snap  = fetch_vps_snapshot()
            tasks = get_all_tasks(snap)
            continue

        # Tab switching
        if choice in ("t1", "tab1"): active_tab = "all";  continue
        if choice in ("t2", "tab2"): active_tab = "demo"; continue
        if choice in ("t3", "tab3"): active_tab = "live"; continue

        if choice == "1":
            clear()
            print(bold("\n  Starting all bots...\n"))
            for t in tasks:
                print(gray(f"  → Launching {t['name']}..."), end="", flush=True)
                start_task(t["name"])
                confirmed, _ = wait_for_state(t["name"], want_running=True)
                print(f"\r  {green('✓') if confirmed else red('✗')} {t['name']:<30} "
                      f"{green('RUNNING') if confirmed else red('FAILED TO START')}")
            snap  = fetch_vps_snapshot()
            tasks = get_all_tasks(snap)
            print()
            input(gray("  Press Enter to continue..."))

        elif choice == "2":
            clear()
            print(bold("\n  Stopping all bots...\n"))
            for t in tasks:
                print(gray(f"  → Stopping {t['name']}..."), end="", flush=True)
                suppress_stop_alert(t["name"])
                stop_bot(t["name"])
                confirmed, _ = wait_for_state(t["name"], want_running=False)
                print(f"\r  {green('✓') if confirmed else yellow('?')} {t['name']:<30} "
                      f"{green('STOPPED') if confirmed else yellow('MAY STILL BE RUNNING')}")
            snap  = fetch_vps_snapshot()
            tasks = get_all_tasks(snap)
            print()
            input(gray("  Press Enter to continue..."))

        elif choice == "r":
            clear()
            print(bold("\n  Restarting all bots...\n"))
            print(gray("  Stopping all bots..."))
            for t in tasks:
                stop_task(t["name"])
            ssh("taskkill /F /IM python.exe 2>nul")
            import time; time.sleep(4)
            print(gray("  Launching startup coordinator (sequential startup)...\n"))
            start_task("SYS_STARTUP")
            print(gray("  Bots are starting sequentially. Each waits for MT5"))
            print(gray("  connection before the next starts (~2 min total).\n"))
            print(gray("  SYS_TELEGRAM will start automatically at the end."))
            print()
            input(gray("  Press Enter — then refresh in 2 minutes to confirm all running..."))

        elif choice == "3":
            confirm = input(red("  Type YES to confirm emergency stop: ")).strip()
            if confirm == "YES":
                emergency_stop_all(tasks)
                import time; time.sleep(3)
                snap  = fetch_vps_snapshot()
                tasks = get_all_tasks(snap)
                print()
                input(gray("\n  Press Enter to continue..."))
            else:
                print(gray("  Cancelled."))

        elif choice == "4":
            while True:
                clear()
                print_header(tasks, active_tab, show_menu=False)
                print_bot_menu(tasks)
                bot_choice = input("  Select bot: ").strip().lower()
                if bot_choice in ("q", "quit", "exit"):
                    sys.exit(0)
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
                    if action in ("q", "quit", "exit"):
                        sys.exit(0)
                    elif action == "b":
                        break
                    elif action == "1":
                        notify_telegram(f"▶️ *{task['pair']}* starting \\[control panel\\]")
                        print(gray(f"\n  Starting {task['name']}..."))
                        ok = start_task(task["name"])
                        print(gray(f"  Launched:  {green('✓') if ok else red('✗')}"))
                        confirmed, updated = wait_for_state(task["name"], want_running=True)
                        if updated: task = updated
                        print(f"  {green('✓ RUNNING') if confirmed else red('✗ FAILED')}")
                        if not confirmed:
                            notify_telegram(f"✗ *{task['pair']}* failed to start \\[control panel\\]")
                        input(gray("  Press Enter..."))
                    elif action == "2":
                        print(gray(f"\n  Stopping {task['name']}..."))
                        suppress_stop_alert(task["name"])
                        dead = stop_bot(task["name"])
                        print(gray(f"  Killed:    {green('✓') if dead else red('✗ (may still be running)')}"))
                        confirmed, updated = wait_for_state(task["name"], want_running=False)
                        if updated: task = updated
                        print(f"  {green('✓ STOPPED') if confirmed else yellow('? MAY STILL BE RUNNING')}")
                        notify_telegram(f"{'⏹' if confirmed else '?'} *{task['pair']}* {'stopped' if confirmed else 'stop unconfirmed'} \\[control panel\\]")
                        input(gray("  Press Enter..."))
                    elif action == "3":
                        notify_telegram(f"🔄 *{task['pair']}* restarting \\[control panel\\]")
                        print(gray(f"\n  Stopping {task['name']}..."))
                        dead = stop_bot(task["name"])
                        print(gray(f"  Killed:    {green('✓') if dead else red('✗ (may still be running)')}"))
                        print(gray(f"  Starting {task['name']}..."))
                        ok = start_task(task["name"])
                        print(gray(f"  Launched:  {green('✓') if ok else red('✗')}"))
                        confirmed, updated = wait_for_state(task["name"], want_running=True)
                        if updated: task = updated
                        print(f"  {green('✓ RESTARTED') if confirmed else red('✗ RESTART FAILED')}")
                        if not confirmed:
                            notify_telegram(f"✗ *{task['pair']}* restart failed \\[control panel\\]")
                        input(gray("  Press Enter..."))
                    elif action == "r":
                        snap2 = fetch_vps_snapshot()
                        match = next((t for t in get_all_tasks(snap2) if t["name"] == task["name"]), None)
                        if match: task = match
                    elif action in ("4", "5"):
                        lines = 40 if action == "4" else 100
                        clear()
                        view_log(task["name"], lines)
                        input(gray("\n  Press Enter to continue..."))
                    elif action == "u" and task["name"] == "SYS_TELEGRAM":
                        manage_users_menu()

                snap  = fetch_vps_snapshot()
                tasks = get_all_tasks(snap)

        elif choice == "5":
            clear()
            print_header(tasks, active_tab, show_menu=False)
            print_bot_menu(tasks)
            bot_choice = input("  Select bot to view log: ").strip().lower()
            if bot_choice in ("q", "quit", "exit"):
                sys.exit(0)
            if bot_choice.isdigit():
                idx = int(bot_choice) - 1
                if 0 <= idx < len(tasks):
                    clear()
                    view_log(tasks[idx]["name"])
                    input(gray("\n  Press Enter to continue..."))

        elif choice == "6":
            print(gray("  Refreshing..."))
            snap  = fetch_vps_snapshot()
            tasks = get_all_tasks(snap)

        elif choice in ("q", "quit", "exit"):
            print(gray("\n  Bye.\n"))
            sys.exit(0)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        try:
            snap  = fetch_vps_snapshot()
            tasks = get_all_tasks(snap)
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
                    snap2 = fetch_vps_snapshot()
                    upd   = get_all_tasks(snap2)
                    match = next((x for x in upd if x["name"] == t["name"]), None)
                    if match and match["running"]:
                        confirmed = True; break
                print(f"\r{green('✓') if confirmed else red('✗')} {t['name']:<35} "
                      f"{green('RUNNING') if confirmed else red('FAILED')}")
            start_task("SYS_TELEGRAM")
            print(f"{green('✓')} {'SYS_TELEGRAM':<35} {green('RESTARTED')}")

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
                is_sched = t["name"] in SCHEDULED_TASKS
                if is_sched:
                    icon = royal("◑") + gray(" SCHEDULED")
                elif t.get("stalled"):
                    icon = yellow("◐ STALLED")
                elif t["running"]:
                    icon = green("● RUNNING")
                else:
                    icon = red("○ STOPPED")
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
