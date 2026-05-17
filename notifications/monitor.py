"""
monitor.py — Real-Time Bot Health Monitor + Alert System

Runs every 1 minute via Task Scheduler.
Sends Telegram alerts immediately when:
  - A bot goes offline unexpectedly
  - A bot comes back online
  - Daily profit goal is hit
  - Daily loss cap is hit
  - Weekly loss cap is hit

State is tracked in monitor_state.json so it knows what changed.
The Telegram bot (SYS_TELEGRAM) is watched as a priority watchdog —
auto-restarted up to 3 times before sending a critical alert.

Install: pip install requests
Run:     python notifications/monitor.py
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

TELEGRAM_TOKEN = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
TELEGRAM_CHAT  = "429207285"
ALGOS_ROOT     = Path("C:/algos")
STATE_FILE     = ALGOS_ROOT / "monitor_state.json"
TEXAS          = ZoneInfo("America/Chicago")

BOTS = {
    "smc_trend": {
        "name":        "Bot SMC Trend",
        "script":      "bot_smc_trend.py",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_equity.json",
        "weekly":      ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_weekly.json",
        "daily_cap":   10.0,
        "weekly_cap":  20.0,
        "daily_goal":  2.0,
    },
    "mean_reversion": {
        "name":        "Bot Mean Reversion",
        "script":      "bot_mean_reversion.py",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_equity.json",
        "weekly":      ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_weekly.json",
        "daily_cap":   10.0,
        "weekly_cap":  20.0,
        "daily_goal":  2.0,
    },
    "scalper": {
        "name":        "Bot Scalper",
        "script":      "bot_scalper.py",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_equity.json",
        "weekly":      ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_weekly.json",
        "daily_cap":   8.0,
        "weekly_cap":  20.0,
        "daily_goal":  10.0,
    },
    "fft": {
        "name":        "Bot FFT",
        "script":      "bot_fft.py",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_equity.json",
        "weekly":      ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_weekly.json",
        "daily_cap":   5.0,
        "weekly_cap":  15.0,
        "daily_goal":  2.0,
    },
}


def send_alert(message: str):
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Alert failed: {e}")


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def is_running(script: str) -> bool:
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "commandline"],
            capture_output=True, text=True, timeout=10
        )
        return script in result.stdout
    except Exception:
        return False


def load_json(path: Path):
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def get_balance(equity) -> float:
    records = equity if isinstance(equity, list) else []
    if not records:
        return 0.0
    return float(records[-1].get("balance", records[-1].get("equity", 0)))


def get_weekly_start(weekly_path: Path) -> float:
    if not weekly_path.exists():
        return 0.0
    with open(weekly_path) as f:
        data = json.load(f)
    return float(data.get("weekly_start", 0))


def check_bot(bot_key: str, state: dict, today: str) -> dict:
    """
    Check one bot's health and send alerts if anything changed.

    Daily cap/goal calculations use day_start_balance which is set at
    midnight each day. On first run, day_start_balance is set to current
    balance to avoid false positives from stale equity data.
    """
    cfg       = BOTS[bot_key]
    bot_state = state.get(bot_key, {})

    running     = is_running(cfg["script"])
    was_running = bot_state.get("running", None)

    # ── Running state change alerts ───────────────────────────────────────
    if was_running is not None and running != was_running:
        now_str = datetime.now(TEXAS).strftime("%I:%M %p CT")
        if not running:
            send_alert(
                f"*ALERT — Bot Offline*\n"
                f"{cfg['name']} stopped unexpectedly\n"
                f"Time: {now_str}\n"
                f"Action: run `algo restart` or use /restart"
            )
        else:
            send_alert(
                f"*ALERT — Bot Online*\n"
                f"{cfg['name']} is running again\n"
                f"Time: {now_str}"
            )

    bot_state["running"] = running
    if not running:
        return bot_state

    # ── Balance and P&L checks ────────────────────────────────────────────
    equity       = load_json(cfg["equity"])
    balance      = get_balance(equity)
    weekly_start = get_weekly_start(cfg["weekly"])

    if balance <= 0:
        return bot_state

    # Reset day tracking at midnight or on first run
    if bot_state.get("last_date") != today:
        bot_state["day_start_balance"] = balance
        bot_state["last_date"]         = today
        bot_state["goal_alerted"]      = False
        bot_state["daily_cap_alerted"] = False
        bot_state["weekly_cap_alerted"]= False
        print(f"{bot_key}: New day — day start balance set to ${balance:,.2f}")

    day_start = bot_state.get("day_start_balance", balance)

    # Guard: if day_start is 0 or not set, set it now and skip this check
    if not day_start or day_start <= 0:
        bot_state["day_start_balance"] = balance
        return bot_state

    daily_gain = (balance - day_start) / day_start * 100
    weekly_dd  = (weekly_start - balance) / weekly_start * 100 if weekly_start > 0 else 0

    now_str = datetime.now(TEXAS).strftime("%I:%M %p CT")

    # ── Daily goal hit ─────────────────────────────────────────────────────
    if daily_gain >= cfg["daily_goal"] and not bot_state.get("goal_alerted"):
        send_alert(
            f"*ALERT — Daily Goal Hit*\n"
            f"{cfg['name']}\n"
            f"Today: +{daily_gain:.1f}% (+${balance - day_start:.2f})\n"
            f"Balance: ${balance:,.2f}\n"
            f"Time: {now_str}"
        )
        bot_state["goal_alerted"] = True

    # ── Daily loss cap hit ─────────────────────────────────────────────────
    if daily_gain <= -cfg["daily_cap"] and not bot_state.get("daily_cap_alerted"):
        send_alert(
            f"*ALERT — Daily Loss Cap Hit*\n"
            f"{cfg['name']}\n"
            f"Today: {daily_gain:.1f}% (-${day_start - balance:.2f})\n"
            f"Balance: ${balance:,.2f}\n"
            f"No new entries until tomorrow\n"
            f"Time: {now_str}"
        )
        bot_state["daily_cap_alerted"] = True

    # ── Weekly loss cap hit ────────────────────────────────────────────────
    if weekly_dd >= cfg["weekly_cap"] and not bot_state.get("weekly_cap_alerted"):
        send_alert(
            f"*ALERT — Weekly Loss Cap Hit*\n"
            f"{cfg['name']}\n"
            f"Weekly drawdown: -{weekly_dd:.1f}%\n"
            f"Balance: ${balance:,.2f} (week start: ${weekly_start:,.2f})\n"
            f"6-hour cooldown activated\n"
            f"Time: {now_str}"
        )
        bot_state["weekly_cap_alerted"] = True

    bot_state["last_balance"] = balance
    return bot_state


def check_telegram_bot(state: dict) -> dict:
    """
    Watchdog for SYS_TELEGRAM — most critical system process.
    Auto-restarts up to 3 times. Sends alert when back online.
    After 3 failures sends a critical alert requiring manual intervention.
    """
    tg_state  = state.get("telegram_bot", {})
    running   = is_running("telegram_bot.py")
    max_tries = 3
    now_str   = datetime.now(TEXAS).strftime("%I:%M %p CT")

    if not running:
        tries = tg_state.get("restart_tries", 0)
        print(f"Telegram bot is DOWN. Restart attempt {tries+1}/{max_tries}...")

        if tries < max_tries:
            try:
                result = subprocess.run(
                    ["schtasks", "/run", "/tn", "SYS_TELEGRAM"],
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0:
                    import time; time.sleep(5)
                    if is_running("telegram_bot.py"):
                        print("Telegram bot restarted successfully.")
                        send_alert(
                            f"*ALERT — Telegram Bot Restarted*\n"
                            f"Was offline\\. Auto-restarted at {now_str}\\.\n"
                            f"Commands are available again\\."
                        )
                        tg_state["restart_tries"] = 0
                        tg_state["running"]        = True
                    else:
                        tg_state["restart_tries"] = tries + 1
                        tg_state["running"]        = False
            except Exception as e:
                print(f"Restart error: {e}")
                tg_state["restart_tries"] = tries + 1
        else:
            if not tg_state.get("max_retry_alerted"):
                send_alert(
                    f"🚨 *CRITICAL — Telegram Bot Down*\n"
                    f"Failed to restart after {max_tries} attempts\\.\n"
                    f"Manual action required\\.\n"
                    f"RDP into VPS: `schtasks /run /tn SYS_TELEGRAM`\n"
                    f"Time: {now_str}"
                )
                tg_state["max_retry_alerted"] = True
    else:
        tg_state["running"]           = True
        tg_state["restart_tries"]     = 0
        tg_state["max_retry_alerted"] = False

    return tg_state


def main():
    state = load_state()
    today = datetime.now(TEXAS).date().isoformat()

    # Telegram bot watchdog — always check first
    try:
        state["telegram_bot"] = check_telegram_bot(state)
    except Exception as e:
        print(f"Telegram watchdog error: {e}")

    # Trading bot checks
    for bot_key in BOTS:
        try:
            state[bot_key] = check_bot(bot_key, state, today)
        except Exception as e:
            print(f"Error checking {bot_key}: {e}")

    save_state(state)
    print(f"Monitor check complete — {datetime.now(TEXAS).strftime('%I:%M %p CT')}")


if __name__ == "__main__":
    main()
