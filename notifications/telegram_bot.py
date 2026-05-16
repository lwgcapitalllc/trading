"""
telegram_bot.py — Telegram Command Handler

Lets you check your bots from anywhere via Telegram.
Polls for new messages every 10 seconds and responds to commands.

Commands:
  /status   — all bots running/stopped with uptime
  /balance  — current balance on each account
  /trades   — today's trades summary across all bots
  /report   — trigger a full report for all bots right now
  /help     — list commands

Run via Task Scheduler at startup (runs 24/7 polling).
Install: pip install requests

Usage:
    python telegram_bot.py
"""

import json
import subprocess
import sys
import time
from datetime import datetime
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
POLL_INTERVAL   = 10  # seconds

BOTS = {
    "bot1": {
        "name":   "Bot 1 — SMC Trend",
        "emoji":  "📈",
        "script": "bot1_smc_trend.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/xauusd_main/bot1_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/xauusd_main/bot1_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/xauusd_main/bot1.log",
    },
    "bot2": {
        "name":   "Bot 2 — Mean Reversion",
        "emoji":  "↩️",
        "script": "bot2_mean_reversion.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/xauusd_main/bot2_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/xauusd_main/bot2_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/xauusd_main/bot2.log",
    },
    "bot3": {
        "name":   "Bot 3 — EMA Scalper",
        "emoji":  "⚡",
        "script": "bot3_scalper.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/xauusd_scalper/bot3_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/xauusd_scalper/bot3_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/xauusd_scalper/bot3.log",
    },
    "bot5": {
        "name":   "Bot 5 — FFT Strategy",
        "emoji":  "🎯",
        "script": "bot5_fft.py",
        "equity": ALGOS_ROOT / "markets/fx/instances/xauusd_fft/bot5_equity.json",
        "trades": ALGOS_ROOT / "markets/fx/instances/xauusd_fft/bot5_trades.json",
        "log":    ALGOS_ROOT / "markets/fx/instances/xauusd_fft/bot5.log",
    },
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
# COMMAND HANDLERS
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
            f"   ${balance:,.2f} {g_icon} {growth:+.1f}% all time"
        )
    return "\n".join(lines)


def cmd_trades() -> str:
    now_tx = datetime.now(TEXAS)
    lines  = [f"📊 *Today's Trades* — {now_tx.strftime('%I:%M %p CT')}", ""]
    total_w = total_l = total_be = total_t = 0
    for bot_key, cfg in BOTS.items():
        trades  = load_json(cfg["trades"])
        today   = get_today_trades(trades)
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
    lines.append(f"\n*Total today: {total_t} trades | {total_w}W {total_l}L {total_be}BE*")
    return "\n".join(lines)


def cmd_help() -> str:
    return (
        "🤖 *LWG Capital Bot Commands*\n\n"
        "/status  — all bots running/stopped with uptime\n"
        "/balance — current balance on each account\n"
        "/trades  — today's trades summary\n"
        "/report  — trigger full daily report now\n"
        "/help    — this message"
    )


def cmd_report() -> str:
    """Trigger the reporter script."""
    try:
        subprocess.Popen(
            ["python", str(ALGOS_ROOT / "reporter.py")],
            cwd=str(ALGOS_ROOT)
        )
        return "📊 Generating reports... check messages in a moment."
    except Exception as e:
        return f"Failed to run reporter: {e}"


# =============================================================================
# MAIN LOOP
# =============================================================================

COMMANDS = {
    "/status":  cmd_status,
    "/balance": cmd_balance,
    "/trades":  cmd_trades,
    "/help":    cmd_help,
    "/report":  cmd_report,
}


def main():
    print(f"Telegram bot started — polling every {POLL_INTERVAL}s")
    send("🤖 *LWG Capital Bot online*\nSend /help for available commands\\.")
    offset = load_offset()

    while True:
        try:
            updates = get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                save_offset(offset)

                msg  = update.get("message", {})
                text = msg.get("text", "").strip().lower()
                chat = str(msg.get("chat", {}).get("id", ""))

                # Only respond to your own chat
                if chat != TELEGRAM_CHAT:
                    continue

                # Strip bot username suffix if present
                cmd = text.split("@")[0]

                if cmd in COMMANDS:
                    response = COMMANDS[cmd]()
                    send(response)
                elif text:
                    send(
                        f"Unknown command: `{text}`\n"
                        f"Send /help for available commands\\."
                    )

        except Exception as e:
            print(f"Poll error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
