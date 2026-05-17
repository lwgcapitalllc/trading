"""
telegram_bot.py — Telegram Command Handler
Location: notifications/telegram_bot.py

Lets you monitor and control your bots from anywhere via Telegram.
Polls for new messages every 10 seconds and responds to commands.

READ-ONLY COMMANDS (instant response):
  /status              — all bots running/stopped with uptime
  /balance             — current balance on each account
  /trades              — today's trades summary across all bots
  /report              — trigger full daily report right now
  /help                — list all commands

CONTROL COMMANDS (require /confirm within 30 seconds):
  /restart             — restart all bots
  /restart bot1        — restart specific bot (bot1/bot2/bot3/bot5)
  /stop                — stop all bots
  /stop bot1           — stop specific bot
  /emergency           — EMERGENCY STOP — kills everything immediately
  /confirm             — confirms the last pending control command

Safety: all control commands require explicit /confirm before executing.
This prevents accidental restarts or stops when messaging on mobile.

Run via Task Scheduler at startup (runs 24/7 polling).
Install: pip install requests

Usage:
    python notifications/telegram_bot.py
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

TELEGRAM_TOKEN  = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
TELEGRAM_CHAT   = "429207285"
ALGOS_ROOT      = Path("C:/algos")
OFFSET_FILE     = ALGOS_ROOT / "telegram_offset.json"
TEXAS           = ZoneInfo("America/Chicago")
POLL_INTERVAL   = 10   # seconds
CONFIRM_TIMEOUT = 30   # seconds to confirm a control command

# Task names as registered in Windows Task Scheduler
TASK_NAMES = {
    "bot1": "BOT_SMC_TREND",
    "bot2": "BOT_MEAN_REVERSION",
    "bot3": "BOT_SCALPER",
    "bot5": "BOT_FFT",
}

BOTS = {
    "bot1": {
        "name":   "Bot 1 — SMC Trend",
        "emoji":  "📈",
        "script": "bot_smc_trend.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/gold_main/bot_smc_trend.log",
    },
    "bot2": {
        "name":   "Bot 2 — Mean Reversion",
        "emoji":  "↩️",
        "script": "bot_mean_reversion.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/gold_main/bot_mean_reversion.log",
    },
    "bot3": {
        "name":   "Bot 3 — EMA Scalper",
        "emoji":  "⚡",
        "script": "bot_scalper.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/gold_scalper/bot_scalper.log",
    },
    "bot5": {
        "name":   "Bot 5 — FFT Strategy",
        "emoji":  "🎯",
        "script": "bot_fft.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/gold_fft/bot_fft.log",
    },
}

# Pending confirmation state
pending_action = {
    "command":   None,   # what to execute on confirm
    "label":     None,   # human-readable description
    "expires_at": None,  # datetime when confirm window expires
}


# =============================================================================
# TELEGRAM API
# =============================================================================

def get_updates(offset: int = 0) -> list:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    try:
        r = requests.get(url, params={"offset": offset, "timeout": 5}, timeout=10)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception:
        pass
    return []


def send(text: str):
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")


def load_offset() -> int:
    if OFFSET_FILE.exists():
        with open(OFFSET_FILE) as f:
            return json.load(f).get("offset", 0)
    return 0


def save_offset(offset: int):
    with open(OFFSET_FILE, "w") as f:
        json.dump({"offset": offset}, f)


# =============================================================================
# DATA HELPERS
# =============================================================================

def load_json(path: Path):
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def is_running(script: str) -> bool:
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=10
        )
        return script in r.stdout
    except Exception:
        return False


def get_uptime(log_path: Path) -> str:
    if not log_path.exists():
        return "?"
    today = datetime.now(TEXAS).date().isoformat()
    start = None
    try:
        with open(log_path, errors="replace") as f:
            for line in f:
                if today[:10] in line and (
                    "STARTING" in line or
                    ("Balance" in line and "Risk" in line) or
                    ("Balance" in line and "AI:" in line)
                ):
                    try:
                        ts    = line.split("|")[0].strip()[:19]
                        start = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        continue
    except Exception:
        return "?"
    if not start:
        return "not started today"
    delta = datetime.utcnow() - start
    h = int(delta.total_seconds() // 3600)
    m = int((delta.total_seconds() % 3600) // 60)
    return f"{h}h {m}m"


def get_balance(equity) -> float:
    records = equity if isinstance(equity, list) else []
    if not records:
        return 0.0
    return float(records[-1].get("balance", records[-1].get("equity", 0)))


def get_today_trades(trades: list) -> list:
    today = datetime.now(TEXAS).date().isoformat()
    return [t for t in trades
            if t.get("closed_at") and t["closed_at"][:10] == today
            and t.get("outcome") in ("win", "loss", "breakeven")]


# =============================================================================
# BOT CONTROL FUNCTIONS
# =============================================================================

def task_start(task_name: str) -> bool:
    """Start a Task Scheduler task."""
    try:
        result = subprocess.run(
            ["schtasks", "/run", "/tn", task_name],
            capture_output=True, text=True, timeout=15
        )
        return result.returncode == 0
    except Exception:
        return False


def task_stop(task_name: str) -> bool:
    """Stop a Task Scheduler task and kill its process."""
    try:
        subprocess.run(
            ["schtasks", "/end", "/tn", task_name],
            capture_output=True, text=True, timeout=15
        )
        return True
    except Exception:
        return False


def do_restart(bot_keys: list) -> str:
    """Stop then start the given bots. Returns result message."""
    results = []
    for key in bot_keys:
        task = TASK_NAMES.get(key)
        if not task:
            continue
        cfg  = BOTS[key]
        task_stop(task)
        time.sleep(3)
        ok = task_start(task)
        results.append(f"{'✅' if ok else '❌'} {cfg['emoji']} {cfg['name']}")
    return "\n".join(results)


def do_stop(bot_keys: list) -> str:
    """Stop the given bots."""
    results = []
    for key in bot_keys:
        task = TASK_NAMES.get(key)
        if not task:
            continue
        cfg = BOTS[key]
        task_stop(task)
        results.append(f"⛔ {cfg['emoji']} {cfg['name']} stopped")
    return "\n".join(results)


def do_emergency_stop() -> str:
    """Kill all bot processes immediately via taskkill."""
    try:
        # Kill all python processes running bot scripts
        for key, cfg in BOTS.items():
            task = TASK_NAMES.get(key)
            if task:
                task_stop(task)
        # Force kill remaining python processes
        subprocess.run(
            ["taskkill", "/f", "/im", "python.exe"],
            capture_output=True, timeout=10
        )
        return "🚨 EMERGENCY STOP executed\nAll bot processes terminated\\."
    except Exception as e:
        return f"Emergency stop error: {e}"


# =============================================================================
# COMMAND HANDLERS — READ ONLY
# =============================================================================

def cmd_status() -> str:
    now_tx = datetime.now(TEXAS)
    lines  = [f"🤖 *Bot Status* — {now_tx.strftime('%I:%M %p CT')}", ""]
    for bot_key, cfg in BOTS.items():
        running = is_running(cfg["script"])
        uptime  = get_uptime(cfg["log"]) if running else "—"
        icon    = "🟢" if running else "🔴"
        status  = "RUNNING" if running else "STOPPED"
        lines.append(f"{icon} {cfg['emoji']} *{cfg['name']}*")
        lines.append(f"   {status} | up {uptime}")
    return "\n".join(lines)


def cmd_balance() -> str:
    now_tx = datetime.now(TEXAS)
    lines  = [f"💰 *Balances* — {now_tx.strftime('%I:%M %p CT')}", ""]
    for bot_key, cfg in BOTS.items():
        equity  = load_json(cfg["equity"])
        balance = get_balance(equity)
        records = equity if isinstance(equity, list) else []
        start   = float(records[0].get("balance", records[0].get("equity", 0))) if records else 0
        growth  = ((balance - start) / start * 100) if start > 0 else 0
        g_icon  = "📈" if growth > 0 else "📉" if growth < 0 else "➡️"
        lines.append(
            f"{cfg['emoji']} *{cfg['name']}*\n"
            f"   ${balance:,.2f} {g_icon} {growth:+.1f}%"
        )
    return "\n".join(lines)


def cmd_trades() -> str:
    now_tx  = datetime.now(TEXAS)
    lines   = [f"📊 *Today's Trades* — {now_tx.strftime('%I:%M %p CT')}", ""]
    total_w = total_l = total_be = total_t = 0
    for bot_key, cfg in BOTS.items():
        trades = load_json(cfg["trades"])
        today  = get_today_trades(trades)
        w  = sum(1 for t in today if t["outcome"] == "win")
        l  = sum(1 for t in today if t["outcome"] == "loss")
        be = sum(1 for t in today if t["outcome"] == "breakeven")
        wr = f"{w/len(today)*100:.0f}%" if today else "—"
        lines.append(
            f"{cfg['emoji']} *{cfg['name']}*\n"
            f"   {len(today)} trades | {w}W {l}L {be}BE | WR: {wr}"
        )
        total_w  += w
        total_l  += l
        total_be += be
        total_t  += len(today)
    lines.append(f"\n*Total: {total_t} trades | {total_w}W {total_l}L {total_be}BE*")
    return "\n".join(lines)


def cmd_report() -> str:
    try:
        subprocess.Popen(
            ["python", str(ALGOS_ROOT / "notifications/reporter.py")],
            cwd=str(ALGOS_ROOT)
        )
        return "📊 Generating reports\\. Check messages in a moment\\."
    except Exception as e:
        return f"Failed to run reporter: {e}"


def cmd_help() -> str:
    return (
        "🤖 *LWG Capital Bot Commands*\n\n"
        "*── READ ONLY ──*\n"
        "/status   — running/stopped with uptime\n"
        "/balance  — current balance per account\n"
        "/trades   — today's trades summary\n"
        "/report   — trigger full daily report now\n"
        "/help     — this message\n\n"
        "*── CONTROL (requires /confirm) ──*\n"
        "/restart          — restart all bots\n"
        "/restart bot1     — restart one bot\n"
        "/stop             — stop all bots\n"
        "/stop bot1        — stop one bot\n"
        "/emergency        — EMERGENCY STOP everything\n"
        "/confirm          — confirm pending action\n\n"
        "_Valid bot names: bot1, bot2, bot3, bot5_"
    )


# =============================================================================
# COMMAND HANDLERS — CONTROL (require confirmation)
# =============================================================================

def request_confirm(command_fn, label: str) -> str:
    """Stage a control command and ask for confirmation."""
    pending_action["command"]    = command_fn
    pending_action["label"]      = label
    pending_action["expires_at"] = datetime.utcnow() + timedelta(seconds=CONFIRM_TIMEOUT)
    return (
        f"⚠️ *Confirm required*\n"
        f"Action: *{label}*\n\n"
        f"Send /confirm within {CONFIRM_TIMEOUT} seconds to proceed\\.\n"
        f"Send anything else to cancel\\."
    )


def cmd_confirm() -> str:
    """Execute the pending confirmed command."""
    if not pending_action["command"]:
        return "No pending action to confirm\\."
    if datetime.utcnow() > pending_action["expires_at"]:
        pending_action["command"] = None
        return "⏰ Confirmation timed out\\. Action cancelled\\."

    fn    = pending_action["command"]
    label = pending_action["label"]
    pending_action["command"] = None

    result = fn()
    return f"✅ *{label}* executed\n\n{result}"


def parse_bot_key(parts: list) -> str | None:
    """Extract bot key from command parts e.g. ['/restart', 'bot1'] -> 'bot1'"""
    if len(parts) >= 2:
        key = parts[1].lower()
        if key in BOTS:
            return key
    return None


# =============================================================================
# MESSAGE ROUTER
# =============================================================================

def handle_message(text: str) -> str:
    text  = text.strip()
    parts = text.lower().split()
    cmd   = parts[0] if parts else ""

    # Read-only commands
    if cmd == "/status":   return cmd_status()
    if cmd == "/balance":  return cmd_balance()
    if cmd == "/trades":   return cmd_trades()
    if cmd == "/report":   return cmd_report()
    if cmd == "/help":     return cmd_help()

    # Confirm pending action
    if cmd == "/confirm":  return cmd_confirm()

    # Control commands — stage for confirmation
    if cmd == "/emergency":
        return request_confirm(
            do_emergency_stop,
            "EMERGENCY STOP — kill all bots immediately"
        )

    if cmd == "/restart":
        bot_key = parse_bot_key(parts)
        if bot_key:
            cfg = BOTS[bot_key]
            return request_confirm(
                lambda k=bot_key: do_restart([k]),
                f"Restart {cfg['name']}"
            )
        else:
            return request_confirm(
                lambda: do_restart(list(BOTS.keys())),
                "Restart ALL bots"
            )

    if cmd == "/stop":
        bot_key = parse_bot_key(parts)
        if bot_key:
            cfg = BOTS[bot_key]
            return request_confirm(
                lambda k=bot_key: do_stop([k]),
                f"Stop {cfg['name']}"
            )
        else:
            return request_confirm(
                lambda: do_stop(list(BOTS.keys())),
                "Stop ALL bots"
            )

    # Cancel any pending action on unrecognised input
    if pending_action["command"]:
        pending_action["command"] = None
        return f"Action cancelled\\. Unknown command: `{text}`\nSend /help for commands\\."

    return f"Unknown command: `{text}`\nSend /help for commands\\."


# =============================================================================
# MAIN LOOP
# =============================================================================

def main():
    print(f"Telegram bot started — polling every {POLL_INTERVAL}s")
    send(
        "🤖 *LWG Capital Bot online*\n"
        "Send /help for available commands\\."
    )
    offset = load_offset()

    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                save_offset(offset)

                msg  = update.get("message", {})
                text = msg.get("text", "").strip()
                chat = str(msg.get("chat", {}).get("id", ""))

                if not text or chat != TELEGRAM_CHAT:
                    continue

                response = handle_message(text)
                send(response)

        except Exception as e:
            print(f"Poll error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
