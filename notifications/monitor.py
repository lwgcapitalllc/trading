"""
monitor.py — Real-Time Bot Health Monitor + Alert System

Runs every 5 minutes via Task Scheduler.
Sends Telegram alerts immediately when:
  - A bot goes offline unexpectedly
  - A bot comes back online
  - Daily profit goal is hit
  - Daily loss cap is hit
  - Weekly loss cap is hit
  - Account balance drops significantly

State is tracked in monitor_state.json so it knows what changed.

Install: pip install requests
Run:     python monitor.py
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
    "bot1": {
        "name":        "Bot 1 — SMC Trend",
        "script":      "bot_smc_trend.py",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_equity.json",
        "daily":       ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_daily.json",
        "weekly":      ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_weekly.json",
        "daily_cap":   10.0,
        "weekly_cap":  20.0,
        "daily_goal":  2.0,
    },
    "bot2": {
        "name":        "Bot 2 — Mean Reversion",
        "script":      "bot_mean_reversion.py",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_equity.json",
        "daily":       ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_daily.json",
        "weekly":      ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_weekly.json",
        "daily_cap":   10.0,
        "weekly_cap":  20.0,
        "daily_goal":  2.0,
    },
    "bot3": {
        "name":        "Bot 3 — EMA Scalper",
        "script":      "bot_scalper.py",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_equity.json",
        "daily":       ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_daily.json",
        "weekly":      ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_weekly.json",
        "daily_cap":   8.0,
        "weekly_cap":  20.0,
        "daily_goal":  10.0,
    },
    "bot5": {
        "name":        "Bot 5 — FFT Strategy",
        "script":      "bot_fft.py",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_equity.json",
        "daily":       ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_daily.json",
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
    """Check one bot and send alerts if anything changed. Returns updated state."""
    cfg       = BOTS[bot_key]
    bot_state = state.get(bot_key, {})

    running   = is_running(cfg["script"])
    was_running = bot_state.get("running", None)

    # ── Running state change ──────────────────────────────────────────────
    if was_running is not None and running != was_running:
        if not running:
            send_alert(
                f"🚨 *BOT OFFLINE*\n"
                f"{cfg['name']} has stopped unexpectedly\\.\n"
                f"⏰ {datetime.now(TEXAS).strftime('%I:%M %p CT')}\n"
                f"Action: Run `algo restart` to bring it back up\\."
            )
        else:
            send_alert(
                f"✅ *BOT ONLINE*\n"
                f"{cfg['name']} is running again\\.\n"
                f"⏰ {datetime.now(TEXAS).strftime('%I:%M %p CT')}"
            )

    bot_state["running"] = running

    if not running:
        return bot_state

    # ── Balance checks ────────────────────────────────────────────────────
    equity  = load_json(cfg["equity"])
    balance = get_balance(equity)
    weekly_start = get_weekly_start(cfg["weekly"])

    if balance > 0 and weekly_start > 0:
        daily_pnl_pct  = bot_state.get("last_balance", balance)
        daily_dd       = (daily_pnl_pct - balance) / daily_pnl_pct * 100 if daily_pnl_pct > 0 else 0
        weekly_dd      = (weekly_start - balance) / weekly_start * 100 if weekly_start > 0 else 0
        daily_gain     = (balance - bot_state.get("day_start_balance", balance)) / bot_state.get("day_start_balance", balance) * 100 if bot_state.get("day_start_balance", 0) > 0 else 0

        # Reset day start balance at midnight
        if bot_state.get("last_date") != today:
            bot_state["day_start_balance"] = balance
            bot_state["last_date"]         = today
            bot_state["goal_alerted"]      = False
            bot_state["daily_cap_alerted"] = False
            bot_state["weekly_cap_alerted"]= False

        # ── Daily goal hit ────────────────────────────────────────────────
        if (daily_gain >= cfg["daily_goal"] and
                not bot_state.get("goal_alerted") and
                bot_state.get("day_start_balance", 0) > 0):
            send_alert(
                f"🎯 *DAILY GOAL HIT*\n"
                f"{cfg['name']}\n"
                f"Today: +{daily_gain:.1f}% (\\+${balance - bot_state['day_start_balance']:.2f})\n"
                f"Balance: ${balance:,.2f}\n"
                f"⏰ {datetime.now(TEXAS).strftime('%I:%M %p CT')}"
            )
            bot_state["goal_alerted"] = True

        # ── Daily loss cap ────────────────────────────────────────────────
        if (daily_gain <= -cfg["daily_cap"] and
                not bot_state.get("daily_cap_alerted") and
                bot_state.get("day_start_balance", 0) > 0):
            send_alert(
                f"🛑 *DAILY LOSS CAP HIT*\n"
                f"{cfg['name']}\n"
                f"Today: {daily_gain:.1f}% (${balance - bot_state['day_start_balance']:.2f})\n"
                f"Balance: ${balance:,.2f}\n"
                f"Bot is now managing open trades only\\. No new entries until tomorrow\\.\n"
                f"⏰ {datetime.now(TEXAS).strftime('%I:%M %p CT')}"
            )
            bot_state["daily_cap_alerted"] = True

        # ── Weekly loss cap ───────────────────────────────────────────────
        if (weekly_dd >= cfg["weekly_cap"] and
                not bot_state.get("weekly_cap_alerted")):
            send_alert(
                f"🚫 *WEEKLY LOSS CAP HIT*\n"
                f"{cfg['name']}\n"
                f"Weekly drawdown: \\-{weekly_dd:.1f}%\n"
                f"Balance: ${balance:,.2f} (started week at ${weekly_start:,.2f})\n"
                f"Bot entering 6hr cooldown\\.\n"
                f"⏰ {datetime.now(TEXAS).strftime('%I:%M %p CT')}"
            )
            bot_state["weekly_cap_alerted"] = True

        bot_state["last_balance"] = balance

    return bot_state


def check_telegram_bot(state: dict) -> dict:
    """
    Watchdog for the Telegram bot — the most critical system process.
    If it's not running, restart it immediately and alert via Telegram
    once it's back up. Retries up to 3 times before giving up.

    This runs every 5 minutes so the bot is never down for more than 5 min.
    """
    tg_state  = state.get("telegram_bot", {})
    running   = is_running("telegram_bot.py")
    max_tries = 3

    if not running:
        tries = tg_state.get("restart_tries", 0)
        print(f"Telegram bot is DOWN. Attempting restart ({tries+1}/{max_tries})...")

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
                            "✅ *Telegram Bot Auto\\-Restarted*\n"
                            f"Was offline\\. Restarted automatically at "
                            f"{datetime.now(TEXAS).strftime('%I:%M %p CT')}\\.\n"
                            f"Commands are available again\\."
                        )
                        tg_state["restart_tries"] = 0
                        tg_state["running"]        = True
                    else:
                        print("Restart attempt failed — process not detected.")
                        tg_state["restart_tries"] = tries + 1
                        tg_state["running"]        = False
            except Exception as e:
                print(f"Restart error: {e}")
                tg_state["restart_tries"] = tries + 1
        else:
            # Max retries reached — send alert if not already sent
            if not tg_state.get("max_retry_alerted"):
                send_alert(
                    "🚨 *Telegram Bot FAILED TO RESTART*\n"
                    f"Tried {max_tries} times\\. Manual intervention required\\.\n"
                    f"RDP into VPS and run: `schtasks /run /tn SYS_TELEGRAM`\n"
                    f"Or restart via algo panel on Mac\\."
                )
                tg_state["max_retry_alerted"] = True
            print(f"Max retries ({max_tries}) reached. Manual restart needed.")
    else:
        # Bot is running — reset counters
        tg_state["running"]           = True
        tg_state["restart_tries"]     = 0
        tg_state["max_retry_alerted"] = False

    return tg_state


def main():
    state = load_state()
    today = datetime.now(TEXAS).date().isoformat()

    # ── Watchdog: Telegram bot (highest priority — always check first) ─────
    try:
        state["telegram_bot"] = check_telegram_bot(state)
    except Exception as e:
        print(f"Telegram watchdog error: {e}")

    # ── Check all trading bots ─────────────────────────────────────────────
    for bot_key in BOTS:
        try:
            state[bot_key] = check_bot(bot_key, state, today)
        except Exception as e:
            print(f"Error checking {bot_key}: {e}")

    save_state(state)
    print(f"Monitor check complete — {datetime.now(TEXAS).strftime('%I:%M %p CT')}")


if __name__ == "__main__":
    main()
